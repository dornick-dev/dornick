"""OpenAI-uyumlu backend: LM Studio, Ollama, vLLM, llama.cpp, OpenRouter.

Bu sunucuların hepsi aynı `/v1/chat/completions` sözleşmesini konuşur, o
yüzden tek backend yeter. Farklılıklar biçimde değil yetenekte: küçük
modeller araç argümanlarını bozuk JSON olarak üretebilir, bazıları görüntü
kabul etmez, çoğunda önbellek yoktur. Bunların hepsi burada ya da
`translate.py` içinde soğurulur; döngü farkı görmez.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from .. import otomod
from ..config import ModelConfig
from ..context import Prepared
from .base import (Callbacks, Interrupted, SimpleMessage, SimpleUsage,
                   Stalled, TurnResult, cancellable)
from .translate import (
    extract_inline_calls,
    map_finish_reason,
    to_anthropic_blocks,
    to_openai_messages,
    to_openai_tools,
)

INSTALL_HINT = (
    "OpenAI-uyumlu sağlayıcı için openai paketi gerekli: pip install 'neocp[local]'"
)


def _hint() -> str:
    """openai paketi kuruluma dahil; kuruluda yokluğu onarım gerektirir."""
    from .. import ortam

    if ortam.kurulu_mu():
        return ("openai paketi bu kurulumda eksik görünüyor. Kurulum "
                "sihirbazını yeniden çalıştırmak eksiği onarır.")
    return INSTALL_HINT

# Yerel sunucular anahtar doğrulamaz ama istemci boş dize kabul etmez.
PLACEHOLDER_KEY = "local"

# Keşif düşüşünün çıktı tavanı. 4096 token ≈ 300+ satır kod: bu görev
# sınıfında tek dosyalık yazmaların neredeyse tamamı sığıyor; sığmayan
# tur tam bütçeyle bir kez yineleniyor (aşağıda, turn içinde).
KESIF_TAVANI = 4096

# Çağrı-başı sessizlik penceresi (barındırılan uçlar): pencere boyunca tek
# parça gelmezse çağrı asılı sayılır, bir kez yeniden denenir. Ölçülen yara
# (29.08, z1): tek bir sağlayıcı çağrısı dakikalarca sustu ve tur ancak
# 900 sn'lik kapı tavanında koptu. 120 sn cömert bir ilk-token payı:
# önbelleksiz dev istemde bile barındırılan uç ya bu sürede akıtır ya hiç.
# Yerel uçlarda pencere YOK — CPU'daki LM Studio ilk token'a meşru olarak
# dakikalar harcayabilir; sabırsız bir kesim orada özellik değil hata olur.
CAGRI_SESSIZLIK_SN = 120.0


def _sessizlik_penceresi(base_url: str | None) -> float | None:
    from urllib.parse import urlparse
    host = (urlparse(str(base_url or "")).hostname or "").casefold()
    if (host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
            or host.startswith("192.168.") or host.startswith("10.")
            or host.endswith(".local")):
        return None
    return CAGRI_SESSIZLIK_SN

# Salt-okur araçlar: sonucu dünyayı değiştirmeyen, ardından tipik olarak
# ya bir okuma daha ya kısa bir yazma gelen araçlar. Liste bilinçli dar —
# yanlış üye eklemek (örn. shell) yazma turlarının çabasını kısar. Araç
# katmanındaki `mutates` bayrağına bağlanmıyor çünkü backend'e araçların
# yalnız API şeması iniyor; adlar üründe kararlı.
_SALT_OKUR = frozenset({"read_file", "read_many", "list_dir", "denetle"})


def _kesif_turu(messages: list[dict[str, Any]]) -> bool:
    """Son alışveriş yalnız salt-okur araç sonuçları mı taşıdı?

    Sondan geriye yürünür: kuyruk `tool` sonuçlarıysa, onları çağıran
    asistan turunun araç adlarına bakılır. Kuyrukta user/system varsa
    (taze kullanıcı mesajı, hafıza notu) keşif sayılmaz — ilk çağrının ve
    kullanıcıya dönen turların çabasına dokunulmaz.
    """
    gordu_tool = False
    for m in reversed(messages):
        role = m.get("role")
        if role == "tool":
            gordu_tool = True
            continue
        if role == "assistant" and gordu_tool:
            adlar = [((c.get("function") or {}).get("name") or "")
                     for c in (m.get("tool_calls") or [])]
            return bool(adlar) and all(ad in _SALT_OKUR for ad in adlar)
        return False
    return False


class OpenAIBackend:
    name = "openai"

    def __init__(self, model: ModelConfig, client: Any | None = None) -> None:
        self.model = model
        self._client = client or _make_client(model)
        # Sunucuya aynı anda kaç istek gideceğinin kapısı. Yerel sunucularda
        # bu 1: LM Studio meşgul bir modele ikinci istek gelince modelin
        # ikinci bir kopyasını yüklüyor ve bellek katlanıyor. Kapı burada,
        # döngüde değil — alt ajanlar da aynı istemciyi paylaşıyor.
        self._gate = asyncio.Semaphore(max(1, model.max_calls))
        # Sunucu `reasoning` alanını tanımıyorsa bir kez öğrenip bir daha
        # göndermiyoruz. Her istekte 400 alıp yeniden denemek, her cevaba
        # bir tur gecikme eklerdi.
        self._no_reasoning = model.can_think is False
        # Model görüntü kabul etmiyorsa aynı biçimde bir kez öğreniliyor:
        # metin-only bir modele geçildiğinde geçmişteki kareler istekte
        # kalıyor ve sunucu 404 veriyor. İlk hatadan sonra kareler sıyrılıp
        # bir daha gönderilmiyor. Katalog False dediyse baştan sıyır.
        self._no_vision = model.vision is False
        # İstem önbelleği işaretleri yalnız OpenRouter'da: ilk sistem +
        # son iki mesaja ephemeral nokta (OpenCode'un ölçülmüş kalıbı —
        # aynı model, aynı iş: %77 isabet, ~6,7x maliyet farkı). Başka
        # uçlara gönderilmiyor; OpenRouter'da bile reddeden olursa bir
        # kez öğrenilip kapatılıyor.
        self._cache_isaretli = "openrouter" in str(model.base_url or "").lower()
        self._cache_kapali = False
        # Oto kipi: adres OpenRouter ve ad "oto" ise istekler ücretsiz
        # havuzdan atılıyor (bkz. otomod). Başka sağlayıcı/model
        # isteklerine DOKUNULMUYOR. Sağlık defteri bellek-içi: arka arkaya
        # hata veren model bir süre havuzun sonuna itiliyor.
        self._oto = otomod.oto_mu(model)
        self._saglik = otomod.Saglik()
        # Oto kipinde en son hangi ucu seçtik. İçerik kusuru (şema ihlali,
        # sahte araç çağrısı) tur BİTTİKTEN sonra döngüde anlaşılıyor;
        # cezayı doğru modele yazabilmek için seçim burada saklanıyor.
        self._son_secilen = ""
        # Son akışın ham finish_reason'ı. `_stream` kırpılmış araç çağrısını
        # yine "tool_use" diye damgalıyor (çağrı varlığı belirleyici); keşif
        # tavanına çarpan turu yakalamak için ham değer burada saklanıyor.
        self._son_finish: str | None = None

    async def close(self) -> None:
        await self._client.close()

    async def turn(
        self,
        prepared: Prepared,
        tools: list[dict[str, Any]],
        *,
        cancel: Any,
        callbacks: Callbacks | None = None,
    ) -> TurnResult:
        callbacks = callbacks or Callbacks()
        callbacks.on_turn_start()

        messages = to_openai_messages(prepared.system, prepared.messages)
        # Model görüntü kabul etmediği öğrenildiyse kareleri baştan sıyır:
        # ilk turda öğrenildi, sonraki turlar boşa 404 yememeli.
        if self._no_vision:
            _strip_images(messages)
        if self._cache_isaretli and not self._cache_kapali:
            _cache_isaretle(messages)

        kwargs: dict[str, Any] = {
            "model": self.model.name,
            "messages": messages,
            "max_tokens": self.model.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
        if self.model.temperature is not None:
            kwargs["temperature"] = self.model.temperature

        extra: dict[str, Any] = {}

        if self.model.keep_loaded > 0:
            # Sunucular bunu farklı adlarla anlıyor: LM Studio `ttl`, Ollama
            # `keep_alive`. İkisi de gönderiliyor; tanımadığı alanı ikisi de
            # yok sayıyor. Yoksa model her istekten sonra bellekten düşüyor
            # ve bir sonraki cevap onlarca saniye yeniden yüklemeyi bekliyor.
            extra["ttl"] = self.model.keep_loaded
            extra["keep_alive"] = self.model.keep_loaded

        # Keşif düşüşü (B5): küçük ailede, son alışveriş YALNIZ salt-okur
        # araç sonuçları getirdiyse bu çağrı büyük ihtimalle bir sonraki
        # okuma ya da kısa bir yazma — duvar süresinin %89'unun model
        # gecikmesi olduğu ölçüldü (29.08 süpürümü) ve o gecikmenin aslanı
        # akıl yürütme. Böyle turlarda çaba low'a, çıktı tavanı KESIF_TAVANI'na
        # iner; tavana çarpan tur (finish=length) tam bütçeyle BİR kez
        # yinelenir — kalite tavana kurban edilmez, yalnız gecikme kırpılır.
        kesif = False
        if tools and not self._oto:
            from ..prompt import kucuk_aile
            if kucuk_aile(kwargs["model"]) and _kesif_turu(messages):
                kesif = True
                kwargs["max_tokens"] = min(self.model.max_tokens, KESIF_TAVANI)

        if (reasoning := self._reasoning(kesif=kesif)) is not None and not self._no_reasoning:
            extra["reasoning"] = reasoning

        # Oto kipi: model ücretsiz havuzun başından seçiliyor, sıradaki
        # birkaçı OpenRouter'ın yerel yedek zincirine (`models`) yazılıyor.
        # `provider.data_collection=deny`: ücretsiz uçların bir kısmı veriyi
        # eğitimde kullanabiliyor; reddeden uca yönlendirilsin.
        secilen = ""
        if self._oto:
            secilen, oto_ek = await asyncio.to_thread(self._oto_hazirla)
            if not secilen:
                return TurnResult(
                    error=(
                        "Oto havuzu kurulamadı: OpenRouter model listesine "
                        "ulaşılamadı ve önbellek boş. Ağı kontrol et ya da "
                        "Ayarlar › Model'den belirli bir model seç."
                    )
                )
            kwargs["model"] = secilen
            self._son_secilen = secilen
            extra.update(oto_ek)

        if extra:
            kwargs["extra_body"] = extra

        async with self._gate:
            try:
                try:
                    result = await self._stream(kwargs, cancel, callbacks)
                except Stalled:
                    # Asılı sağlayıcı çağrısı: tur tavanını yemeden bir kez
                    # taze bağlantıyla yinele. İkincisi de susarsa hata —
                    # oto kipinde sağlık defterine düşer, model sıraya iner.
                    try:
                        result = await self._stream(kwargs, cancel, callbacks)
                    except Stalled as exc:
                        result = TurnResult(error=(
                            f"{kwargs['model']} yanıt akıtmadı: {exc} "
                            "(iki deneme). Sağlayıcı asılı görünüyor."))
                if kesif and self._son_finish == "length":
                    # Tavana çarptı: kırpılmış araç argümanı/cevap işe
                    # yaramaz. Tam bütçe + normal çabayla tek yineleme.
                    kwargs["max_tokens"] = self.model.max_tokens
                    body = dict(kwargs.get("extra_body") or {})
                    if (tam := self._reasoning()) is not None and not self._no_reasoning:
                        body["reasoning"] = tam
                    if body:
                        kwargs["extra_body"] = body
                    result = await self._stream(kwargs, cancel, callbacks)
            except Exception:
                # İstek hiç kurulamadı (örn. bağlantı reddi): bu da o
                # modelin hanesine hata yazılır.
                if self._oto and secilen:
                    self._saglik.kaydet(secilen, False)
                raise

        # Zaman aşımı, boş yanıt ve hata aynı kefede: çağrı başarısız.
        # Kesme kullanıcının kararı, modelin suçu değil — sayılmıyor.
        if self._oto and secilen and not result.interrupted:
            self._saglik.kaydet(secilen, ok=not result.error)
        return result

    def kusurlu(self, sebep: str = "") -> None:
        """İçerik kusuru: tur teknik olarak başarılı ama boşa gitti.

        Döngü çağırıyor (bkz. `Agent._kusurlu`): şemaya uymayan araç
        çağrısı ya da gerçek çağrı yerine düz metin yazılmış çağrı XML'i.
        Ücretsiz havuzda bunlar hata kadar gerçek: araç çağıramayan bir uç
        işi ilerletmiyor, yalnızca tur harcıyor. Sağlık defterine
        başarısızlık olarak yazılıyor; eşiği aşan model havuzun sonuna
        itiliyor ve kendiliğinden eleniyor.

        Oto kipi dışında karşılığı yok: kullanıcı modeli kendi seçti,
        onu arkasından sıralamaya sokmak bize düşmez.
        """
        if self._oto and self._son_secilen:
            self._saglik.kaydet(self._son_secilen, False)

    def _oto_hazirla(self) -> tuple[str, dict[str, Any]]:
        """Oto kipinin istek parçaları: seçilen model + ek gövde alanları.

        Havuz sağlık sırasına göre diziliyor: cezalı modeller sona. Son
        seçim teşhis için önbellek dosyasına not ediliyor — "hangi modelle
        konuştum" sorusunun cevabı orada.
        """
        pool = self._saglik.sirala(otomod.havuz())
        if not pool:
            return "", {}
        ek: dict[str, Any] = {
            "provider": {"data_collection": "deny", "require_parameters": True},
        }
        if yedekler := pool[1:4]:
            ek["models"] = yedekler
        otomod.son_yaz(pool[0])
        return pool[0], ek

    def _heal(self, kwargs: dict[str, Any], exc: Exception) -> bool:
        """Bilinen bir reddi bir kez iyileştirir; iyileştirdiyse True.

        Aynı hatayı sonsuza kadar denememek için her tür bir kez: `reasoning`
        alanı ya da görüntü. İyileştirecek bir şey kalmadıysa False döner ve
        çağıran hatayı yükseltir.
        """
        if not self._no_reasoning and _rejects_reasoning(exc):
            self._no_reasoning = True
            body = kwargs.get("extra_body") or {}
            body.pop("reasoning", None)
            if body:
                kwargs["extra_body"] = body
            else:
                kwargs.pop("extra_body", None)
            return True

        if not self._no_vision and _rejects_image(exc):
            self._no_vision = True
            _strip_images(kwargs["messages"])
            return True

        # Önbellek işaretini tanımayan uç: işareti söküp bir daha gönderme.
        if (self._cache_isaretli and not self._cache_kapali
                and "cache_control" in str(exc).lower()):
            self._cache_kapali = True
            _cache_sok(kwargs["messages"])
            return True

        return False

    def _reasoning(self, kesif: bool = False) -> dict[str, Any] | None:
        """Düşünme ayarının sunucuya gönderilecek hali.

        Bu alan şimdiye kadar yalnızca Claude tarafında geçerliydi; qwen3
        gibi düşünen modeller kendi kararlarıyla akıl yürütüyordu ve ayar
        sayfasındaki "çaba" değeri hiçbir şey yapmıyordu.

        Farkı ölçtüm (qwen3-27b, OpenRouter, "üyan." gibi tek kelimelik bir
        istem):

            şu anki hal      ilk parça 2,53 sn   toplam 8,97 sn
            reasoning low    ilk parça 0,87 sn   toplam 1,60 sn
            reasoning off    ilk parça 0,94 sn   toplam 1,12 sn

        Selam vermek için dokuz saniye akıl yürütmek, asistanı gerçek
        zamanlı olmaktan çıkarıyor. `low` hem hızlı hem de kişiliği
        koruyor; tümden kapatmak modeli genel geçer kalıplara düşürüyor
        ("Size nasıl yardımcı olabilirim?").
        """
        if self.model.can_think is False:
            return None
        if not self.model.thinking:
            return {"enabled": False}
        # OpenRouter "low/medium/high" kabul ediyor; xhigh/max karşılığı yok.
        effort = {"xhigh": "high", "max": "high"}.get(self.model.effort, self.model.effort)
        # Küçük/hızlı ailede tavan medium: flash sınıfı modelde her araç
        # çağrısına yüksek-çaba akıl yürütme, 11 çağrılık işi 900 sn
        # tavanına taşıdı (28.08 kıyası; OpenCode aynı modeli düz koşup
        # 140 sn'de bitirdi). Kalite kapılardan geliyor, düşünme süresinden
        # değil — o koşuda iki taraf da 96+ aldı.
        if effort == "high":
            from ..prompt import kucuk_aile
            if kucuk_aile(self.model.name):
                effort = "medium"
        # Keşif turu: bir okumanın ardından gelen çağrıya orta/yüksek çaba
        # akıl yürütme, gecikmenin kendisi (B5 ölçümü). Tavana çarpan tur
        # zaten tam çabayla yineleniyor.
        if kesif and effort in ("medium", "high"):
            effort = "low"
        return {"effort": effort} if effort in ("low", "medium", "high") else None

    async def _stream(self, kwargs: dict[str, Any], cancel: Any, callbacks: Callbacks) -> TurnResult:
        text: list[str] = []
        reasoning: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish: str | None = None
        self._son_finish = None
        usage = SimpleUsage()
        stream = None

        # İki tür ret bir kez öğrenilip iyileştiriliyor: tanınmayan
        # `reasoning` alanı ve görüntü kabul etmeyen model. İkisi birden
        # gerekebilir (metin-only + reasoning'siz sunucu), o yüzden
        # denemeler bir döngüde: her hatada bir şey iyileştir, tekrar dene.
        stream = None
        for _ in range(3):
            try:
                stream = await self._client.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                if not self._heal(kwargs, exc):
                    raise
        if stream is None:  # pragma: no cover - döngü hep break ya da raise
            raise RuntimeError("istek kurulamadı")

        try:
            # `cancellable`: kesme yalnız parça gelince değil, parça BEKLERKEN
            # de yoklanıyor. İlk token'dan önceki uzun istem işleme sırasında
            # (önbelleksiz ilk tur) Durdur işlemiyordu — kökü burasıydı.
            async for chunk in cancellable(
                    stream, cancel,
                    stall_s=_sessizlik_penceresi(self.model.base_url)):
                if raw_usage := getattr(chunk, "usage", None):
                    usage = _usage(raw_usage)

                if not getattr(chunk, "choices", None):
                    continue

                choice = chunk.choices[0]
                finish = getattr(choice, "finish_reason", None) or finish
                _consume(getattr(choice, "delta", None), callbacks, text, reasoning, calls)

        except Interrupted:
            return TurnResult(interrupted=True, partial_text="".join(text))
        except Stalled:
            # Asılı çağrı çağırana yükselir: turn() bir kez yeniden dener,
            # ikincisi de susarsa hata TurnResult'a döner.
            raise
        except Exception as exc:  # openai paketi opsiyonel; tipe bağlanamayız
            return TurnResult(error=_explain(exc, self.model), partial_text="".join(text))
        finally:
            # Akış tüketilse de kesilse de kapatılmalı. Kapatılmazsa altındaki
            # httpx bağlantısı yorumlayıcı kapanırken toplanır ve
            # "generator didn't stop after athrow()" hatası verir.
            await _aclose(stream)

        self._son_finish = finish
        joined = "".join(text)
        gathered = [calls[i] for i in sorted(calls)]

        # Bazi yerel modeller arac cagrisini tool_calls alaninda degil, duz
        # metin icinde XML olarak uretiyor. Ayristirilmazsa cagri hic
        # calismiyor ve ham etiketler kullaniciya cevap gibi gorunuyor.
        joined, inline = extract_inline_calls(joined)
        if inline:
            for index, call in enumerate(inline):
                gathered.append({
                    "id": f"inline_{index}",
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                })

        blocks = to_anthropic_blocks(joined, gathered)

        if not blocks:
            # Düşünme modelleri turu bazen yalnızca reasoning kanalında
            # bitirir: plan yapar, "şimdi şunu yapmalıyım" der ve durur.
            #
            # Bunu cevap diye sunmak yanlıştı — kullanıcı akıl yürütmeyi
            # cevap sanıyor ve iş yarıda kalıyordu. Akıl yürütme cevap
            # değildir; geçmişe asistan turu olarak giriyor (model kendi
            # planını görsün diye) ama `empty_turn` ile işaretleniyor,
            # döngü de onu sürdürüyor.
            if thought := "".join(reasoning).strip():
                return TurnResult(
                    message=SimpleMessage(
                        content=[{"type": "text", "text": thought}],
                        stop_reason="empty_turn",
                        usage=usage,
                    ),
                    partial_text="",
                )
            else:
                return TurnResult(
                    error=(
                        f"{self.model.name} boş yanıt döndürdü "
                        f"(finish_reason={finish!r}). Model araç kullanımını "
                        "desteklemiyor olabilir ya da bağlam sınırına çarpmış."
                    )
                )

        # Sunucu finish_reason'ı atlarsa araç çağrısının varlığı belirleyicidir;
        # aksi halde döngü tool_use turunu end_turn sanıp erken durur.
        stop_reason = "tool_use" if gathered else map_finish_reason(finish)

        return TurnResult(
            message=SimpleMessage(content=blocks, stop_reason=stop_reason, usage=usage),
            partial_text="".join(text),
        )

    async def count_tokens(self, prepared: Prepared, tools: list[dict[str, Any]]) -> int:
        """Kaba tahmin.

        Uyumlu sunucularda token sayma uç noktası yok. Karakter/4 yaklaşımı
        raporlama için yeterli; maliyet hesabına dayanak yapma.
        """
        payload = to_openai_messages(prepared.system, prepared.messages)
        chars = sum(len(str(m.get("content") or "")) for m in payload)
        chars += sum(len(str(t)) for t in to_openai_tools(tools))
        return chars // 4


# ---------------------------------------------------------------------


def _make_client(model: ModelConfig) -> Any:
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover - kurulum yolu
        raise RuntimeError(_hint()) from exc

    key = os.getenv(model.api_key_env or "OPENAI_API_KEY") or PLACEHOLDER_KEY
    kwargs: dict[str, Any] = {"api_key": key}
    if model.base_url:
        kwargs["base_url"] = model.base_url

    # Zaman aşımı ve yeniden deneme. Varsayılan SDK zaman aşımı çok uzun ve
    # AKIŞ boşta kalınca (sağlayıcı yanıt vermeyi bırakınca) sistem dakikalarca
    # "düşünüyor" diye takılı kalıyordu — kullanıcı "upstream idle timeout"
    # hatası gelene kadar bekliyordu. `read` = ardışık iki bayt arası azami
    # boşluk: sağlıklı bir akış saniyeden kısa aralıkla token gönderir; bu
    # süre aşılırsa istek hızla düşer ve tur temiz biter (kilitlenmez). Yerel
    # bir model ilk token için biraz yavaş olabildiğinden cömert tutuldu.
    # `max_retries` geçici sağlayıcı hatalarını (429, kısa idle) yutuyor.
    try:
        import httpx

        kwargs["timeout"] = httpx.Timeout(90.0, connect=15.0)
    except Exception:
        kwargs["timeout"] = 90.0
    kwargs["max_retries"] = 2

    return AsyncOpenAI(**kwargs)


def _consume(
    delta: Any,
    callbacks: Callbacks,
    text: list[str],
    reasoning: list[str],
    calls: dict[int, dict[str, str]],
) -> None:
    if delta is None:
        return

    if chunk := getattr(delta, "content", None):
        text.append(chunk)
        callbacks.on_text(chunk)

    # Qwen3, DeepSeek-R1 ve türevleri düşünmeyi ayrı alanda akıtır. Alan adı
    # sunucudan sunucuya değişiyor; SDK tanımadığı alanları model_extra'ya koyar.
    if chunk := _reasoning_of(delta):
        reasoning.append(chunk)
        callbacks.on_thinking(chunk)

    for fragment in getattr(delta, "tool_calls", None) or []:
        slot = calls.setdefault(
            getattr(fragment, "index", 0),
            {"id": "", "name": "", "arguments": "", "ek": {}},
        )
        if identifier := getattr(fragment, "id", None):
            slot["id"] = identifier

        # Sağlayıcıya özel alanlar: TANIMADAN taşınıyor. Gemini düşünen
        # modellerde her araç çağrısına bir `thought_signature` iliştiriyor
        # ve SONRAKİ turda onu geri göndermeni ŞART koşuyor; göndermezsen
        # 400 veriyor ("missing a thought_signature in functionCall parts").
        # Alanın adını ve yerini sağlayıcıya göre kodlamak yerine bilmediğimiz
        # her şeyi olduğu gibi saklıyoruz — böyle bir alan ekleyen bir sonraki
        # sağlayıcıda da kırılmıyor.
        _ek_topla(slot["ek"], fragment)

        function = getattr(fragment, "function", None)
        if function is None:
            continue
        _ek_topla(slot["ek"], function)

        if name := getattr(function, "name", None):
            # Çoğu sunucu adı tek parça yollar, bazıları parçalar. Aynı parçayı
            # iki kez eklememek için sonek kontrolü yapıyoruz.
            if not slot["name"]:
                slot["name"] = name
                callbacks.on_tool_start(name)
            elif not slot["name"].endswith(name):
                slot["name"] += name

        if arguments := getattr(function, "arguments", None):
            slot["arguments"] += arguments


# SDK'nin modellemedigi alanlar `model_extra`da durur (pydantic). Araç
# çağrısında ne varsa oradan alıyoruz: adını bilmediğimiz bir alanı da
# taşıyabilmek için tek tek saymıyoruz.
_EK_ATLA = frozenset({"index", "id", "type", "name", "arguments", "function"})


def _ek_topla(kutu: dict[str, Any], nesne: Any) -> None:
    """Tanınmayan sağlayıcı alanlarını kutuya biriktirir (sessiz, en iyi çaba)."""
    try:
        fazla = getattr(nesne, "model_extra", None) or {}
    except Exception:
        return
    for anahtar, deger in fazla.items():
        if anahtar in _EK_ATLA or deger is None:
            continue
        # Akış parça parça geliyor; metin alanları ekleniyor, ötekiler
        # son gelen kazanıyor (imza tek parça geliyor).
        if isinstance(deger, str) and isinstance(kutu.get(anahtar), str):
            if not kutu[anahtar].endswith(deger):
                kutu[anahtar] += deger
        else:
            kutu[anahtar] = deger


# Alanı tanımayan bir sunucunun reddi. Sunucudan sunucuya metin değişiyor,
# o yüzden koda değil kelimeye bakılıyor: hepsi alanın adını söylüyor.
_REJECTED = ("reasoning", "unknown field", "unrecognized", "extra_body",
             "unexpected keyword", "additionalproperties")


def _rejects_reasoning(exc: Exception) -> bool:
    text = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status is not None and status not in (400, 404, 422):
        return False
    return "reasoning" in text or any(mark in text for mark in _REJECTED)


def _rejects_image(exc: Exception) -> bool:
    """Model görüntü kabul etmiyor mu?

    Metin-only bir modele geçildiğinde geçmişteki kamera/ekran kareleri
    hâlâ istekte oluyor ve sunucu reddediyor. OpenRouter'ın metni:
    'No endpoints found that support image input'. Sunucuya göre değişiyor,
    o yüzden koda değil kelimeye bakılıyor: hepsi görüntüden söz ediyor.
    """
    text = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status is not None and status not in (400, 404, 415, 422):
        return False
    return "image" in text and (
        "support" in text or "endpoint" in text or "multimodal" in text
        or "not accept" in text or "vision" in text
    )


# Görüntü sıyrıldığında yerine konan iz. Model göremiyor ama bir görüntünün
# orada olduğunu bilmesi, "az önce gösterdiğim" gibi göndermelere yardımcı.
_IMAGE_PLACEHOLDER = "[görüntü — bu model göremiyor]"


def _cache_isaretle(messages: list[dict[str, Any]]) -> None:
    """OpenRouter istem önbelleği: ilk sistem + son iki mesaja ephemeral.

    İşaret bir içerik PARÇASININ üstünde yaşar; düz metin içerik tek
    parçaya sarılır. En fazla üç nokta — Anthropic ailesinin dört-nokta
    sınırının güvenli altında, OpenRouter diğer modellerde işareti ya
    kullanır ya yok sayar.
    """
    isaret = {"type": "ephemeral"}
    adaylar = [m for m in messages if m.get("role") == "system"][:1]
    adaylar += [m for m in messages if m.get("role") != "system"][-2:]
    gorulen: set[int] = set()
    for m in adaylar:
        if id(m) in gorulen:
            continue
        gorulen.add(id(m))
        icerik = m.get("content")
        if isinstance(icerik, str):
            m["content"] = [{"type": "text", "text": icerik,
                             "cache_control": dict(isaret)}]
        elif isinstance(icerik, list) and icerik:
            son = icerik[-1]
            if isinstance(son, dict):
                son["cache_control"] = dict(isaret)


def _cache_sok(messages: list[dict[str, Any]]) -> None:
    """İşaretleri geri alır (uç kabul etmedi): parçalardan düşürülür."""
    for m in messages:
        icerik = m.get("content")
        if isinstance(icerik, list):
            for parca in icerik:
                if isinstance(parca, dict):
                    parca.pop("cache_control", None)


def _strip_images(messages: list[dict[str, Any]]) -> None:
    """OpenAI-biçimli mesajlardaki görüntü parçalarını metne çevirir (yerinde).

    Yeniden çeviriye gerek yok: zaten çevrilmiş mesajın içindeki
    `image_url` parçaları bir metin izine dönüştürülüyor. Parça listesi
    yalnızca görüntüden ibaretse mesaj düz metne iniyor.
    """
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        cleaned: list[dict[str, Any]] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                cleaned.append({"type": "text", "text": _IMAGE_PLACEHOLDER})
            else:
                cleaned.append(part)
        # Tek parça ve o da metinse düz dizeye indir: bazı sunucular tek
        # elemanlı içerik dizisinde titizleniyor.
        if len(cleaned) == 1 and cleaned[0].get("type") == "text":
            msg["content"] = cleaned[0]["text"]
        else:
            msg["content"] = cleaned


def _reasoning_of(delta: Any) -> str | None:
    """Düşünme metnini bulur.

    Alan adı sunucudan sunucuya değişiyor ve OpenAI şemasında yok; SDK
    tanımadığı alanları model_extra'ya koyar, oraya da bakmak gerekiyor.
    """
    for name in ("reasoning_content", "reasoning"):
        if value := getattr(delta, name, None):
            return str(value)
    extra = getattr(delta, "model_extra", None) or {}
    for name in ("reasoning_content", "reasoning"):
        if value := extra.get(name):
            return str(value)
    return None


def _usage(raw: Any) -> SimpleUsage:
    """OpenAI/OpenRouter usage → SimpleUsage (cache alanları dahil).

    `prompt_tokens` genelde önbellek + taze toplamıdır. `prompt_tokens_details.
    cached_tokens` varsa cache_read'e yazılır; input_tokens taze kısım kalır
    ki `cache_report.prompt_total` çift saymasın.
    """
    if isinstance(raw, dict):
        prompt = int(raw.get("prompt_tokens") or 0)
        output = int(raw.get("completion_tokens") or 0)
        nested = raw.get("prompt_tokens_details") or {}
        cached = int(nested.get("cached_tokens") or 0) if isinstance(nested, dict) else 0
        created = int(nested.get("cache_creation_tokens") or 0) if isinstance(nested, dict) else 0
    else:
        prompt = int(getattr(raw, "prompt_tokens", 0) or 0)
        output = int(getattr(raw, "completion_tokens", 0) or 0)
        cached = 0
        created = 0
        details = getattr(raw, "prompt_tokens_details", None)
        if isinstance(details, dict):
            cached = int(details.get("cached_tokens") or 0)
            created = int(details.get("cache_creation_tokens") or 0)
        elif details is not None:
            cached = int(getattr(details, "cached_tokens", 0) or 0)
            created = int(getattr(details, "cache_creation_tokens", 0) or 0)
        elif isinstance(getattr(raw, "model_extra", None), dict):
            nested = raw.model_extra.get("prompt_tokens_details") or {}
            if isinstance(nested, dict):
                cached = int(nested.get("cached_tokens") or 0)
                created = int(nested.get("cache_creation_tokens") or 0)

    fresh = max(0, prompt - cached - created) if (cached or created) else prompt
    return SimpleUsage(
        input_tokens=fresh,
        output_tokens=output,
        cache_read_input_tokens=cached,
        cache_creation_input_tokens=created,
    )


async def _aclose(stream: Any) -> None:
    if stream is None:
        return
    for name in ("close", "aclose"):
        closer = getattr(stream, name, None)
        if closer is None:
            continue
        try:
            result = closer()
            if hasattr(result, "__await__"):
                await result
        except Exception:  # kapatma hatası turu bastırmamalı
            pass
        return


def _explain(exc: Exception, model: ModelConfig) -> str:
    status = getattr(exc, "status_code", None)
    text = str(getattr(exc, "message", "") or exc)
    where = model.base_url or "OpenAI"

    if isinstance(exc, (ConnectionError, OSError)) or "Connection" in type(exc).__name__:
        return (
            f"{where} adresine bağlanılamadı. Sunucu açık mı? "
            "LM Studio'da 'Local Server' sekmesinden başlatman gerekiyor."
        )
    if status == 404:
        return (
            f"{where}: '{model.name}' modeli bulunamadı. "
            "LM Studio'da yüklü modelin tam kimliğini kullan."
        )
    # llama.cpp/LM Studio pencere taşmasını 400 ile ve kendi diliyle
    # bildiriyor. Ham hali kullanıcıya bir şey söylemiyor; içindeki sayı
    # tam olarak ayarlanması gereken değer.
    if match := re.search(r"n_ctx:\s*(\d+)", text):
        window = int(match.group(1))
        return (
            f"Model {window} token'lık pencereyle yüklü ama istem daha büyük. "
            "İki yerden biri düzeltilmeli:\n"
            f"  · LM Studio'da modeli daha büyük bir bağlamla yükle "
            f"(şu an {window}), ya da\n"
            f"  · Ayarlar › bağlam'dan pencereyi {window} yaz — o zaman "
            "konuşma dolmadan özetlenip sürüyor."
        )

    if status == 400 and "tool" in text.lower():
        return (
            f"{where}: sunucu araç çağrısını reddetti ({text}). "
            "Bu model araç kullanımını desteklemiyor olabilir."
        )
    return f"{where}: {text}" if status is None else f"{where} {status}: {text}"
