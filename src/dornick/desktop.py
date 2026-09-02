"""Masaüstü uygulaması.

Pencere, işletim sisteminin kendi webview'ıdır (Windows'ta WebView2) —
Electron'un yaptığının aynısı, ama Chromium'u paketlemeden. Arayüz aynı
HTML/CSS/JS; motor da aynı motor.

Üç thread var ve sınırları net:

    ana thread      pencere. pywebview'in start()'ı ana thread'de çalışmak
                    zorunda ve pencere kapanana kadar bloke eder.
    asyncio thread  ajan döngüsü.
    HTTP thread'ler sunucu; arayüzden gelen istekleri karşılar.

Arayüzden ajana geçiş her zaman `loop.call_soon_threadsafe` ya da
`run_coroutine_threadsafe` üzerinden yapılır. Ajandan arayüze geçiş
`Hub.emit` üzerinden — o da kendi içinde kilitli.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from .backends import build_client
from . import (
    connectors as linking,
    ear as hearing,
    fiyat as fiyatlama,
    lmstudio,
    ortam,
    prefs,
    prompt,
    schedule as scheduling,
    settings,
    skills,
    tanima,
    tray as tray_module,
    watch as watching,
)
from .config import Config
from .context import ContextPolicy
from .loop import (
    Agent,
    AgentIO,
    BARGE_NOTE,
    clear_park,
    read_park,
    yetim_isaretle,
    yetim_tara,
)
from .mind import open_mind
from .permissions import PermissionEngine
from .session import Session
from .tools import build_registry
from .tools.base import ToolSpec
from .web import server as server_module
from .web.server import Hub, MindServer

WINDOW_TITLE = "Dornick"
WINDOW_BACKGROUND = "#0b0e14"

# Uyandirma taramasi icin kullanilan model. Kucuk ve hizli olmasi
# yeterli: aranan sey tek kelime.
SCOUT_SIZE = "base"

# Biri odaya girdiğinde ajana gidilen soru. Selam vermesi değil, **bakması**
# isteniyor: kim geldiğini görsün, tanıdıksa adıyla karşılasın.
# Adı çağrıldı ama arkasından bir şey söylenmedi ("dornick"). Adı çağrılıp
# susmak, duymamakla aynı şey: karşındaki insan başını çevirir ve "efendim"
# der. Kısa tutulması önemli — uzun bir açılış cümlesi burada gereksiz.
CALLED_ASK = (
    "Kullanıcı yalnızca adını söyledi, arkasından bir şey istemedi. "
    "Tek kelimelik bir karşılık ver (\"efendim\", \"buradayım\" gibi) ve "
    "sus. Araç kullanma, soru sorma, uzatma."
)

# Açılışın azami süresi. Cömert: ilk açılışta bir tanıma modeli inebiliyor
# ve o indirme dakikalar sürüyor.
BOOT_TIMEOUT_S = 300.0

GREET_ASK = (
    "Uzun bir sessizlikten sonra kamerada hareket oldu — biri geldi. "
    "`look now` ile bir kere bak ve kim olduğunu gör. Tanıdıysan kısaca "
    "selam ver; tanımadıysan ya da emin değilsen sessiz kal, boş yere "
    "konuşma."
)


# Açık sesli iptal sözleri: yalnızca bunlar süren turu durduruyor. Gerisi
# (yeni bir istek) iptal değil, sıraya girer. "Yeni söylediğim eskiyi iptal
# etmesini istiyorsa ancak öyle yapabilir" — kullanıcının koyduğu kural.
_STOP_WORDS = ("dur", "durdur", "yeter", "kes", "iptal", "vazgeç", "stop", "sus")


def _is_stop(text: str) -> bool:
    words = text.lower().replace("!", "").replace(".", "").split()
    # Kısa ve yalnızca durdurma sözünden ibaret: "dur", "yeter dur" gibi.
    # Uzun bir cümlenin içinde "dur" geçmesi (ör. "durumu anlat") iptal değil.
    return bool(words) and len(words) <= 2 and all(w in _STOP_WORDS for w in words)


# Kapatma sözleri: sohbet penceresini kapatır. Karşılık verilmez — "rica
# ederim!" demek kapanan konuşmayı yeniden açmak olurdu; insan da vedaya
# veda ile cevap verip durmaz. "tamam" tek başına listede yok: ajanın
# sorduğu bir sorunun cevabı da "tamam" olabiliyor.
_CLOSE_WORDS = ("kapat", "kapan", "görüşürüz", "hoşça kalın", "hoşça kal",
                "hoşçakal", "iyi geceler", "sonra konuşuruz")

# Kapatma sözünün yanında gelebilecek dolgu: "tamam görüşürüz",
# "teşekkürler kapat" da kapanış sayılıyor.
_CLOSE_PAD = frozenset(("tamam", "peki", "teşekkürler", "teşekkür", "ederim",
                        "sağ", "sağol", "ol", "çok", "iyi"))


def _is_close(text: str) -> bool:
    plain = " ".join(text.lower().replace("!", "").replace(".", "").replace(",", "").split())
    if not plain or len(plain.split()) > 4:
        return False
    for phrase in _CLOSE_WORDS:
        if phrase in plain:
            rest = plain.replace(phrase, " ").split()
            return all(w in _CLOSE_PAD for w in rest)
    return False


# Nezaket / bekleme: modele gitmez. "teşekkürler" → "rica ederim" bir
# asistan döngüsü; "şimdi bakayım" bir istek değil. "tamam" tek başına
# yok — ajanın sorduğu şeye evet de olabiliyor.
_ACK_CORE = frozenset((
    "teşekkürler", "teşekkür", "tesekkurler", "tesekkur",
    "sağol", "sagol", "sağolun", "sagolun", "eyvallah",
    "tamamdır", "thanks", "thx",
    "bakayım", "bakayim",
))
_ACK_PAD = frozenset((
    "çok", "cok", "ederim", "sağ", "sag", "ol", "tamam", "peki",
    "şimdi", "simdi", "bir", "dur", "you", "thank", "oldu", "ben",
))


def _is_ack(text: str) -> bool:
    raw = (text or "").lower().replace("!", "").replace(".", "").replace(",", "")
    raw = raw.replace("'", "")
    words = raw.split()
    if not words or len(words) > 5:
        return False
    joined = " ".join(words)
    if "thank you" in joined:
        return True
    glued = joined.replace("sağ ol", "sağol").replace("sag ol", "sağol")
    words = glued.split()
    if not any(w in _ACK_CORE for w in words):
        return False
    return all(w in _ACK_CORE or w in _ACK_PAD for w in words)


def inherit_last_model(mind: Any, session_id: str, sessions_dir: Any) -> str:
    """Yeni oturuma en son sabitlenmiş sohbet modelini yazar.

    Katalog seçimi sohbet metasındadır; `dornick --app` her açılışta yeni
    oturum açınca pin kayboluyor ve küresel eski model geri geliyordu.
    """
    from pathlib import Path

    sid = str(session_id or "")
    mapping = (mind.session_meta() or {}) if mind is not None else {}
    if str((mapping.get(sid) or {}).get("model") or "").strip():
        return str(mapping[sid]["model"]).strip()
    files = sorted(
        Path(sessions_dir).glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        other = path.stem
        if other == sid:
            continue
        rec = mapping.get(other) or {}
        name = str(rec.get("model") or "").strip()
        if not name:
            continue
        mind.set_session_meta(
            sid, model=name, provider=str(rec.get("provider") or ""))
        return name
    return ""


async def _retire(client: Any) -> None:
    """Değiştirilen istemciyi kapatır.

    Kapatmamak açık bağlantı bırakıyor; kapatırken patlaması ise ajanı
    durdurmamalı — yeni istemci zaten çalışıyor.
    """
    try:
        await client.close()
    except Exception:
        pass


# Snapshot'a giren hedef sayısının tavanı. Panel zaten ilk altısını açıkta
# gösteriyor; yüzlerce bayat hedefi her sayfa yüklemede taşımanın alemi yok.
GOAL_SNAPSHOT_LIMIT = 20


def _active_goals(agent: Any) -> list[dict[str, Any]]:
    """Aktif hedeflerin arayüz dökümü (id + metin + bu oturumdan mı).

    Hedef paneli olay güdümlü (goal_push/goal_status) ama sayfa yenilenince
    olaylar kaçmış oluyor; snapshot bu listeyle panele kaldığı yeri veriyor.
    Zihin yoksa ya da okunamıyorsa boş liste — panel görünmez, sohbet düşmez.

    Hedef defteri artık oturuma süzülü (`mind.goals()` varsayılanı):
    "bu görevleri kim oluşturuyor" şikâyetinin köküydü — başka sohbetlerin
    maddeleri panele hiç gelmez. `eski` alanı arayüz uyumluluğu için
    duruyor; süzgeç sayesinde pratikte hep False.
    """
    mind = getattr(agent, "mind", None)
    if mind is None:
        return []
    simdiki = getattr(mind, "session_id", "")
    try:
        return [
            {"id": g.id, "text": g.text,
             "eski": bool(simdiki and g.session_id and g.session_id != simdiki)}
            for g in mind.goals()[:GOAL_SNAPSHOT_LIMIT]
        ]
    except Exception:
        return []


# Kaba token tahmini: karakter / bu sayı. Sağlayıcıdan gelen gerçek sayıya
# hiçbir zaman denk gelmez ve gelmesi de beklenmiyor — kullanıcının bilmek
# istediği "ne kadar doluyum", tam rakam değil. Bu yüzden tahmin olduğu
# arayüzde açıkça söyleniyor (title'da).
TAHMIN_BOLEN = 4


def baglam_kirilim(agent: Any, prompt_total: int = 0) -> list[dict[str, Any]]:
    """İstem penceresinin kalem kalem tahmini — Cursor'un Context Usage'ı.

    Sağlayıcı yalnız TOPLAM veriyor; kırılım karakter/4. Toplam varsa
    sabitler ondan büyük çıkmasın diye orantılanır, kalan Konuşma'dır.
    """
    import json

    def tok(text: str) -> int:
        return max(0, len(text or "") // TAHMIN_BOLEN)

    sistem = ruh = 0
    sys = getattr(agent, "_system", None) if agent is not None else None
    if sys is not None:
        sistem = tok(getattr(sys, "core", "") or "")
        ruh = tok(getattr(sys, "identity", "") or "")

    # `task` / `task_say` / `task_status` Cursor'daki "Subagent definitions"
    # kalemi: yerleşik araçlardan ayrı dursun, yoksa Araç tanımları şişer.
    _YARDIMCI = {"task", "task_say", "task_status"}

    arac = yetenek = mcp = yardimci = 0
    registry = getattr(agent, "registry", None) if agent is not None else None
    if registry is not None and hasattr(registry, "all"):
        brief = bool(getattr(agent, "kisa_sema", False))
        for spec in registry.all():
            try:
                sema = spec.api_schema()
                if brief and isinstance(sema, dict):
                    desc = str(sema.get("description") or "")
                    sema = {**sema, "description": desc.split("\n\n", 1)[0]}
                blob = json.dumps(sema, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                continue
            n = tok(blob)
            src = str(getattr(spec, "source", None) or "")
            ad = str(getattr(spec, "name", "") or "")
            if not ad and isinstance(sema, dict):
                ad = str(sema.get("name") or "")
            if src.startswith("mcp"):
                mcp += n
            elif src == "yetenek":
                yetenek += n
            elif ad in _YARDIMCI:
                yardimci += n
            else:
                arac += n

    parcalar: list[tuple[str, str, int]] = [
        ("sistem", "Sistem istemi", sistem),
        ("arac", "Araç tanımları", arac),
        ("ruh", "Ruh / kurallar", ruh),
        ("yetenek", "Yetenekler", yetenek),
        ("mcp", "MCP ve dinamik araçlar", mcp),
        ("yardimci", "Yardımcı tanımları", yardimci),
    ]
    sabit = sum(n for _, _, n in parcalar)
    toplam = max(0, int(prompt_total or 0))
    if toplam and sabit > toplam:
        oran = toplam / sabit
        parcalar = [(k, ad, int(n * oran)) for k, ad, n in parcalar]
        sabit = sum(n for _, _, n in parcalar)
    sohbet = max(0, toplam - sabit) if toplam else 0
    parcalar.append(("sohbet", "Konuşma", sohbet))
    return [{"id": k, "ad": ad, "n": n} for k, ad, n in parcalar]


def _saglayici_adi(agent: Any) -> str:
    """Arayüzde gösterilecek sağlayıcı kimliği (openrouter, ollama, …).

    `model.provider` backend tipidir ("openai") ve altında altı farklı
    sunucu var; kullanıcıya "openai" demek OpenRouter'a bağlıyken yanlış
    bilgi olurdu. Adrese bakan eşleştirme `settings.provider_of`'ta.
    """
    if agent is None:
        return ""
    try:
        from . import settings
        return settings.provider_of(agent.config.model)
    except Exception:
        return str(getattr(getattr(agent, "config", None), "model", None)
                   and agent.config.model.provider or "")


def _calisabilir(agent: Any) -> bool:
    """Ajan gerçekten kimlik doğrulayabiliyor mu?

    Model "oto"/varsayılan gelse bile anahtar yoksa hiçbir iş yapılamaz;
    arayüz ilk-kurulum yönlendirmesini buna göre gösteriyor. Yerel sunucu
    (localhost/LM Studio) anahtar istemez — o durumda çalışabilir sayılır.
    """
    if agent is None:
        return False
    model = getattr(agent, "config", None)
    model = getattr(model, "model", None)
    if model is None:
        return False
    base = (getattr(model, "base_url", "") or "").lower()
    if any(h in base for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1")):
        return True
    env = getattr(model, "api_key_env", "") or ""
    if not env:
        return True   # anahtar istemeyen sağlayıcı
    if os.environ.get(env):
        return True
    try:
        from . import settings
        return bool(settings.load_keys(agent.config.state_dir).get(env))
    except Exception:
        return False


def _gecmis_kullanim(agent: Any) -> dict[str, Any]:
    """Sürdürülen bir oturumun bağlam + harcama durumu.

    Kanıtlanmış yara: uygulama kapanıp açılınca ya da geçmişten bir
    konuşma sürdürülünce dock'taki bağlam çubuğu ve maliyet çipi SIFIRDAN
    başlıyordu. Oysa geçmiş yüklü — kullanıcı hem doluluğu hem toplam
    harcamayı kaybediyordu. Bu turda hiç model çağrılmadığı için
    `_last_usage` boş; doğru kaynak oturum günlüğü.

    İki ayrı rakam:
      * `prompt_total` — SON turun istemi (bağlam çubuğu: şu an pencere
        ne kadar dolu).
      * `girdi` — tüm turların `prompt_total` toplamı (maliyet çipi:
        canlı `_usage_yay` ile aynı muhafazakâr muhasebe; konuşmayı
        yeniden açınca sıfırdan değil geçmişin üstünden).

    Kaynak sırası:
      1. Asistan mesajlarının `usage` meta'sı — sağlayıcının saydığı
         gerçek rakam.
      2. Yoksa yüklü mesajlardan kaba tahmin (karakter/4). `tahmin`
         bayrağı arayüze taşınıyor: uydurma bir kesinlik satılmıyor.

    Yeni oturumda ikisi de boş çıkar ve sayaç gerçekten sıfırdan başlar.
    """
    bos = {"prompt_total": 0, "girdi": 0, "output": 0, "cagri": 0, "tahmin": False}
    session = getattr(agent, "session", None)
    if session is None:
        return bos
    try:
        mesajlar = session.log.messages()
    except Exception:
        return bos

    cagri = 0
    son: dict[str, Any] | None = None
    toplam_girdi = 0
    toplam_cikti = 0
    for ev in mesajlar:
        if ev.role != "assistant":
            continue
        kullanim = ev.meta.get("usage")
        if isinstance(kullanim, dict) and kullanim.get("prompt_total"):
            son = kullanim
            cagri += 1
            toplam_girdi += int(kullanim.get("prompt_total") or 0)
            toplam_cikti += int(kullanim.get("output") or 0)

    if son is not None:
        return {
            "prompt_total": int(son.get("prompt_total") or 0),
            "girdi": toplam_girdi,
            "output": toplam_cikti,
            "cagri": cagri,
            "tahmin": False,
        }

    # Usage yok (eski günlük ya da sayaç vermeyen sağlayıcı): kaba tahmin.
    # Sıfır göstermektense yaklaşık göstermek doğru — yeter ki tahmin
    # olduğu söylensin.
    #
    # Tahmin PENCEREDEN yapılıyor, ham günlükten değil: günlük hiç
    # kısaltılmıyor ve sıkıştırılmış (ufkun gerisinde kalan) turları da
    # saymak, küçük bir sohbete "182k token" yazdırıyordu — sağlayıcı
    # panelinde hiç görünmeyen bir rakam (canlı yara, 01.09). `messages()`
    # bir SONRAKİ isteğin gerçekten taşıyacağı projeksiyondur; doğru taban o.
    try:
        pencere = session.messages()
    except Exception:
        pencere = [{"role": e.role, "content": e.content} for e in mesajlar]
    harf = 0
    for mesaj in pencere:
        harf += len(_metin_uzunlugu(mesaj.get("content")))
    if not harf:
        return bos
    tahmini = harf // TAHMIN_BOLEN
    return {"prompt_total": tahmini, "girdi": tahmini, "output": 0,
            "cagri": 0, "tahmin": True}


def _metin_uzunlugu(content: Any) -> str:
    """Bir mesajın metin gövdesi (tahmin için). Görüntüler sayılmıyor.

    tool_result blokları da sayılıyor: içerikleri düz dize ya da blok
    listesi olabiliyor ve istekte gerçekten taşınıyorlar — eski hal onları
    atlayıp tahmini sistemsiz biçimde düşük gösteriyordu.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parcalar = []
    for blok in content:
        if not isinstance(blok, dict):
            continue
        if isinstance(blok.get("text"), str):
            parcalar.append(blok["text"])
        elif blok.get("type") == "tool_result":
            ic = blok.get("content")
            if isinstance(ic, str):
                parcalar.append(ic)
            elif isinstance(ic, list):
                parcalar.append(_metin_uzunlugu(ic))
    return "\n".join(parcalar)


# Yardımcı durumlarının arayüz dili. Defterde Türkçe halleri duruyor;
# panel tarafı olaylarla aynı kelimeleri (run/done/fail) bekliyor.
_KANAL_DURUM = {"kosuyor": "run", "bitti": "done", "yetim": "yetim"}


def _yerel_uc(base_url: str) -> bool:
    """Model ucu kullanıcının makinesinde/ağında mı? (loopback + RFC-1918)

    Kamera karesinin buluta çıkıp çıkmayacağının tek ölçütü. Gece
    okulundaki `_yerel_mi` ile aynı tanım — iki yerde iki farklı "yerel"
    tanımı olmasın.
    """
    from urllib.parse import urlparse
    host = (urlparse(str(base_url or "")).hostname or "").casefold()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    return (host.startswith("192.168.") or host.startswith("10.")
            or host.endswith(".local"))


def _hareket_gonder(bridge: Any, config: Config, hub: Hub,
                    sighting: watching.Sighting) -> None:
    """Hareket olayı: GPU varsa yerelde analiz, modele metin.

    GPU analizi başarılıysa kare hiç gitmez — sohbet modeli metni okur.
    Analiz yoksa eski kapı: yerel model serbest, bulut için cloud_ok.
    HUD kapalıyken izleyici hâlâ bir kare üretmiş olsa bile sohbet açılmaz.
    """
    if not bool(getattr(config.camera, "enabled", False)):
        return
    cam = sighting.camera
    if callable(getattr(cam, "is_builtin", None)) and cam.is_builtin():
        lens = getattr(bridge, "lens", None)
        if lens is None or not (
            getattr(lens, "running", False) or getattr(lens, "live", False)
        ):
            return
    hub.emit({
        "type": "notice",
        "text": f"{sighting.camera.name}: hareket (%{int(sighting.change * 100)})",
    })
    from . import sight

    ozet = ""
    if getattr(sighting.camera, "analyze", True):
        ozet = sight.analyze_url(sighting.frame)
    try:
        watching.remember(config.state_dir, sighting.camera, ozet or "hareket")
    except Exception:
        pass
    baslik = f"[{sighting.camera.name}] {sighting.ask}"
    if ozet:
        bridge.submit(f"{baslik}\n\nYerel GPU analizi: {ozet}")
        return
    model_url = str(getattr(bridge.agent.config.model, "base_url", "") or "") \
        if bridge.agent is not None else ""
    yerel = _yerel_uc(model_url)
    if not yerel and not config.camera.cloud_ok:
        hub.emit({
            "type": "notice",
            "text": (f"{sighting.camera.name}: kare BULUT modele gönderilmedi "
                     "(izin kapalı). Yerel model seç ya da Ayarlar › Kamera'dan "
                     "bulut iznini aç."),
        })
        return
    bridge.submit(baslik, sighting.frame)


def _biten_kanallari_dusur(agent: Any) -> None:
    """Oturum geçişinde bitmiş yardımcıları defterden düşürür.

    "O sohbet bittiyse o da bitmiştir" (canlı şikâyet — orkestra eski
    sohbetlerin bitmiş kayıtlarıyla doluyordu). Koşanlar ve yetimler
    (sürdürülebilir) kalır; bitmiş/hatalı olanlar yeni sohbete taşınmaz.
    """
    try:
        children = getattr(agent, "_children", None) or {}
        for cid in [cid for cid, h in children.items()
                    if h.state not in ("kosuyor", "yetim")]:
            children.pop(cid, None)
    except Exception:
        pass


def _live_channels(agent: Any) -> list[dict[str, Any]]:
    """Yardımcı kanallarının arayüz dökümü (orkestra panelinin tohumu).

    Panel olay güdümlü (child_start/child_end) ama sayfa yenilenince ya da
    uygulama yeniden açılınca olaylar kaçmış oluyor ve panel hayalet
    "çalışıyor" kartlarıyla kalabiliyordu. Tek doğru kaynak ajanın defteri
    (`Agent._children`): snapshot bu listeyle panele kaldığı yeri veriyor,
    listede olmayan "çalışıyor" kanalı çizilmiyor. Hedef panelindeki
    tohumlama kalıbının aynısı (bkz. _active_goals).
    """
    children = getattr(agent, "_children", None)
    if not children:
        return []
    try:
        return [
            {
                "id": h.id,
                "title": h.title,
                "model": h.model,
                "bg": bool(h.arka_plan),
                "kind": h.kind,
                "state": _KANAL_DURUM.get(h.state, "fail"),
                "ozet": "" if h.state == "kosuyor" else (h.sonuc or "")[:200],
            }
            for h in children.values()
        ]
    except Exception:
        return []


# Kuyruğa düşen iç işaret: bir arka plan yardımcısı bitti. pump bunu
# görünce (ajan o an boş demektir — kuyruk seri) bir sürdürme turu açar.
# Metin değil nesne: hiçbir kullanıcı mesajıyla karışamaz.
_CHILD_DONE = object()

# Açılışta bulunan park kaydı (yarım kalmış uzun iş): pump bunu görünce
# koşuyu kaldığı yerden sürdürür.
_PARK_RESUME = object()


@dataclass(slots=True)
class Pending:
    """Bekleyen izin istegi.

    Future yaninda spec ve args da tutuluyor: "hep izin ver" secildiginde
    kurali yazmak icin hangi arac ve hangi hedef oldugu gerekiyor.
    """

    future: asyncio.Future[bool]
    spec: ToolSpec
    args: dict[str, Any]


@dataclass(slots=False)
class Serit:
    """Bir oturumun bağımsız koşu şeridi: ajan + kuyruk + meşgul bayrağı.

    Paralel oturumların çekirdeği (canlı istek, 29.08): "yeni konuşma
    dediğimde eskinin bitmesini bekliyor" — tek ajan/tek kuyruk mimarisi
    oturum geçişini koşan turun bitişine kilitliyordu. Artık her oturumun
    kendi şeridi var: kendi Agent'ı, kendi kuyruğu, kendi pompası. Aktif
    şerit arayüze akar; arkadakiler kendi oturum günlüğüne yazar ve
    kullanıcı dönünce döküm oradan yüklenir.
    """

    sid: str
    agent: Any
    queue: asyncio.Queue
    busy: bool = False
    task: Any = None    # pompa görevi (ilk şeritte Controller.pump koşuyor)


class Bridge:
    """Arayüz ile ajan arasındaki iki yönlü köprü.

    Controller yüzeyi HTTP thread'inden, AgentIO yüzeyi asyncio thread'inden
    çağrılır. İkisi arasındaki her geçiş açıkça işaretli.
    """

    def __init__(self, hub: Hub, loop: asyncio.AbstractEventLoop) -> None:
        self.hub = hub
        self.loop = loop
        # Şeritler: oturum kimliği -> Serit. Aktif şerit arayüzün baktığı
        # oturum; diğerleri arka planda koşabilir (paralel oturumlar).
        self.seritler: dict[str, Serit] = {}
        self._aktif_sid: str | None = None
        # İlk şeridin kuyruğu — ajan henüz yokken de mesaj sıraya girebilsin
        # (açılış yarışı). `agent` atandığında şerit bu kuyruğu devralır.
        self._ilk_kuyruk: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        # Oturum değiştirmek (yeni/devam) olay akışını yeni günlüğe bağlamayı
        # gerektiriyor; bunu sunucu yapıyor. _boot referansı sonradan veriyor.
        self.server: Any = None
        self._pending: dict[str, Pending] = {}
        # Sürekli dinleyen kulak sonradan bağlanıyor: açılış sırasında
        # köprü ondan önce kuruluyor.
        self.ear: Any = None
        self.lens: Any = None
        self.eyes: Any = None
        # Turun ortasında istenen model değişikliği. Akan bir istemciyi
        # altından çekmek o cevabı öldürür; tur bitince uygulanıyor. Modelle
        # birlikte sistem promptu da tazelendiği için tüm config saklanıyor.
        self._wanted_model: Any = None
        self._wanted_config: Config | None = None
        # Bekleyen istemci değişiminde arayüze basılacak not: gerçek model
        # değişimi mi yoksa yalnız anahtar/ayar tazelemesi mi.
        self._swap_note: str = ""
        # Uyandırma sözü duyulunca pencereyi geri getiren çağrı.
        # Masaüstü katmanı kuruyor; arayüz önizlemesinde None kalıyor.
        self.on_wake: Any = None
        # Sistem tepsisi: arka plan görev bitince Windows bildirimi.
        # Masaüstü `run()` bağlar; önizleme / headless'ta None.
        self.tray: Any = None
        # Açılışta kaçırılan zamanlanmış görevler: kullanıcı karar verene
        # dek zamanlayıcı bekler (bkz. schedule.run_forever `paused`).
        self._missed_ids: list[str] = []
        self._missed_fire: Any = None
        # Açılış sırasında nerede olunduğu. Model yüklenmeden konuşmak
        # anlamsız: arayüz bu bilgiyle giriş satırını kapalı tutuyor.
        self.stage = "uyanıyor"
        self.ready = False
        # Maliyet çipi: tur ve oturum toplamları (token) + seçili modelin
        # fiyat etiketi (USD/token, OpenRouter kataloğundan). Fiyat arka
        # plan thread'inde EN FAZLA bir kez çekiliyor; tur ağ beklemiyor.
        self._fiyat: dict[str, float] | None = None
        self._fiyat_bakildi = False
        self._tur_kullanim = {"girdi": 0, "cikti": 0, "cagri": 0}
        self._oturum_kullanim = {"girdi": 0, "cikti": 0, "cagri": 0}
        # Sürdürülen oturumun geçmiş harcaması bir kez tohumlanır; bkz.
        # _oturum_tohumla. Yeni oturumda tohum yok — sayaç gerçekten sıfır.
        self._oturum_tohumlandi = False
        # Bütçe freni: bu oturum için üst sınır (USD). None = sınırsız.
        # Ayar sayfasında değil, maliyet çipinin açılır kutusunda duruyor —
        # rakamın yanında. Sınıra ulaşılınca koşan tur duruyor (bkz.
        # _butce_freni ve loop.Agent._drive).
        self._butce_usd: float | None = None
        # Sınır bir kez bildirildi mi: her model çağrısından önce sorulan
        # fren, aynı satırı turda onlarca kez basmasın.
        self._butce_bildirildi = False

    # -- şerit yüzeyi ---------------------------------------------------
    #
    # Eski tek-ajan alanları (`agent`, `queue`, `_busy`) özelliğe döndü:
    # 30+ çağrı yeri değişmeden aktif şeride bakmaya devam ediyor. Yazma
    # yolu daralttı — `_busy` artık atanamaz, meşguliyet şeridin kendi
    # bayrağı (bkz. _serit_durum).

    def _serit_alanlari(self) -> None:
        # Testler köprüyü `Bridge.__new__` ile init'siz kuruyor; şerit
        # alanları ilk dokunuşta tembelce tamamlanır.
        if not hasattr(self, "seritler"):
            self.seritler = {}
            self._aktif_sid = None
        if not hasattr(self, "_ilk_kuyruk"):
            self._ilk_kuyruk = asyncio.Queue()

    @property
    def agent(self) -> Any:
        self._serit_alanlari()
        s = self.seritler.get(self._aktif_sid or "")
        return s.agent if s else None

    @agent.setter
    def agent(self, value: Any) -> None:
        # _boot uyumu: ilk ajan atanınca ilk şerit kurulur ve açılıştan
        # beri biriken kuyruğu devralır. None = kurulamadı (modelsiz açılış).
        self._serit_alanlari()
        if value is None:
            return
        sid = str(getattr(getattr(value, "session", None), "id", "") or "ilk")
        serit = Serit(sid=sid, agent=value, queue=self._ilk_kuyruk,
                      busy=bool(getattr(self, "_busy_beklet", False)))
        self._busy_beklet = False
        self.seritler[sid] = serit
        self._aktif_sid = sid
        # Akış kapıları şeride bağlansın: bu şerit arka plana düşerse
        # olayları aktif sohbete sızmasın. Yardımcı-bitti işareti de kendi
        # kuyruğuna düşsün — aktif şeride değil.
        try:
            value.io = self.io(serit)
            value.on_children_settled = (
                lambda s=serit: self.loop.call_soon_threadsafe(
                    self._serit_child_done, s))
        except Exception:
            pass

    def _serit(self) -> Serit | None:
        self._serit_alanlari()
        return self.seritler.get(self._aktif_sid or "")

    @property
    def queue(self) -> asyncio.Queue:
        s = self._serit()
        return s.queue if s else self._ilk_kuyruk

    @property
    def _busy(self) -> bool:
        s = self._serit()
        if s is not None:
            return bool(s.busy)
        return bool(getattr(self, "_busy_beklet", False))

    @_busy.setter
    def _busy(self, value: bool) -> None:
        # Test uyumu: köprüyü elle kuran testler meşguliyeti doğrudan
        # atıyor. Üründe bu yol kullanılmıyor (bkz. _serit_durum). Şerit
        # henüz yoksa bayrak bekletilir; ilk şerit kurulunca devralır.
        s = self._serit()
        if s is not None:
            s.busy = bool(value)
        else:
            self._busy_beklet = bool(value)

    def _serit_durum(self, serit: Serit, busy: bool) -> None:
        """Şeridin meşguliyetini işler ve doğru kanallara duyurur.

        Klasik `status` yalnız AKTİF şerit için yayınlanır (arayüzün tek
        kompozeri var); `lane` olayı her şerit için gider — kenar çubuğu
        hangi sohbetlerin koştuğunu rozetle gösterir.
        """
        serit.busy = busy
        if serit.sid == self._aktif_sid:
            self.hub.emit({"type": "status", "busy": busy})
        self.hub.emit({"type": "lane", "id": serit.sid, "busy": busy})

    # -- HTTP thread'inden çağrılanlar ---------------------------------

    def submit(self, text: str, image: str = "", *, siraya: bool = False) -> None:
        """Kullanıcı mesajını ajana verir.

        Ajan MEŞGULKEN gelen düz metin artık kuyruğa değil, koşan turun
        gelen kutusuna giriyor: mesaj aynı turun bir sonraki adımında
        harness notu olarak modelin önüne düşüyor ("araya girme"). Kullanıcı
        turun bitmesini beklemeden yön değiştirebiliyor.

        Eski kuyruk davranışı üç durumda korunuyor:
          * `siraya=True` — zamanlanmış görev ve dış kapı gibi, koşan işin
            ortasına karışmaması gereken kaynaklar.
          * Görüntülü mesaj — görüntü bloğu harness notuna giremiyor
            (system kanalı düz metin); basit tutmak için eski kuyruk.
          * Gelen kutusu dolduysa — araya girme tekil bir jest, sel değil.
        """
        if not image and _is_ack(text):
            return
        agent = self.agent
        if (self._busy and not siraya and not image
                and agent is not None and not agent.inbox_full()):
            self.hub.emit({"type": "araya", "text": text})
            note = BARGE_NOTE.format(text=text)
            self.loop.call_soon_threadsafe(
                lambda: agent.take_note(note, encode=text))
            return
        # Ajan çalışırken sıraya giren mesaj atılmıyor ama sırada beklediği
        # ekranda görünmeli: kullanıcı yazıp enter'a basıyor ve hiçbir şey
        # olmuyor gibi duruyordu.
        if self._busy:
            self.hub.emit({"type": "queued", "text": text})
        asyncio.run_coroutine_threadsafe(self.queue.put((text, image)), self.loop)

    def child_done(self) -> None:
        """Bir arka plan yardımcısı bitti (asyncio thread'inden çağrılır).

        Kuyruğa iç işaret düşer; sırası gelince (ajan boşken) sürdürme
        turu açılır. Ajan meşgulse işaret turun bitmesini kuyrukta bekler —
        o zamana kadar sonuç zaten tur başındaki notla verilmiş olabilir,
        `_surdur` boşa model çağırmaz. (Geri uyum: aktif şerit. Şeride özel
        yol `_serit_child_done` — her ajan kendi şeridine bağlanır.)
        """
        self.queue.put_nowait(_CHILD_DONE)

    def _serit_child_done(self, serit: Serit) -> None:
        serit.queue.put_nowait(_CHILD_DONE)

    def run_scheduled(self, task: Any) -> dict[str, Any]:
        """Zamanlanmış görevi sohbete değil Orkestra yardımcısı olarak koşturur.

        Otomasyon (`kind_ui=automation` + workflow_id) → workflow runner;
        basit görev → sessiz spawn_scheduled. Her koşum task_runs'a yazılır.
        """
        agent = self.agent
        if agent is None:
            return {"ok": False, "error": "ajan henüz hazır değil"}

        title = str(getattr(task, "title", "") or "görev")
        prompt = str(getattr(task, "prompt", "") or "")
        tid = str(getattr(task, "id", "") or "")
        kind_ui = str(getattr(task, "kind_ui", "") or "simple")
        workflow_id = str(getattr(task, "workflow_id", "") or "")

        if kind_ui == "automation" and workflow_id and hasattr(agent, "run_workflow"):
            try:
                # Görev kimliği geçiyor: koşum, arayüzün baktığı deftere
                # yazılsın (bkz. `run_workflow` içindeki gerekçe).
                fut = asyncio.run_coroutine_threadsafe(
                    agent.run_workflow(workflow_id, tid), self.loop)
                result = fut.result(timeout=30)
                return result if isinstance(result, dict) else {"ok": True, "result": result}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        if not hasattr(agent, "spawn_scheduled"):
            return {"ok": False, "error": "zamanlanmış koşum yok"}
        if not prompt.strip():
            return {"ok": False, "error": "görev metni boş"}

        box: dict[str, Any] = {}
        done = threading.Event()

        def _start() -> None:
            try:
                handle = agent.spawn_scheduled(title, prompt, tid)
                book = getattr(agent, "schedule", None)
                if book is not None and tid:
                    book.mark_running(tid, handle.id)
                box.update({"ok": True, "id": handle.id, "title": handle.title,
                            "run_id": getattr(handle, "run_id", "")})
            except Exception as exc:
                box.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                done.set()

        self.loop.call_soon_threadsafe(_start)
        if not done.wait(15):
            return {"ok": False, "error": "zaman aşımı"}
        return box or {"ok": False, "error": "başlatılamadı"}

    def new_session(self) -> dict[str, Any]:
        """Taze bir konuşma başlatır: yeni oturum, boş bağlam."""
        return self._switch(None)

    def resume_session(self, sid: str) -> dict[str, Any]:
        """Geçmiş bir konuşmayı sürdürür: o oturumu aktif yapar, bağlamı
        (geçmiş mesajları) yükler ve yeni mesajlar oraya eklenir."""
        return self._switch(sid)

    def open_path(self, path: str, *, message: str = "") -> dict[str, Any]:
        """Windows 'Dornick ile aç': yeni sohbet + çalışma klasörü + isteğe bağlı tohum.

        Dosya → üst klasör proje; klasör → doğrudan proje. Yeni oturum meta'sına
        path yazılır; ardından isteğe bağlı kullanıcı mesajı kuyruğa girer.
        """
        from pathlib import Path

        raw = str(path or "").strip().strip('"')
        if not raw:
            return {"ok": False, "error": "yol boş"}
        target = Path(raw).expanduser()
        try:
            target = target.resolve()
        except OSError:
            return {"ok": False, "error": "yol çözülemedi"}
        if not target.exists():
            return {"ok": False, "error": "yol yok"}

        folder = target if target.is_dir() else target.parent
        seed = (message or "").strip()
        if not seed:
            if target.is_file():
                seed = f"Bu dosyayı açtım: {target}\nÇalışma klasörü: {folder}\nNe yapmamı istersin?"
            else:
                seed = f"Bu klasörü açtım: {folder}\nNe yapmamı istersin?"

        switched = self._switch(None)
        if not switched.get("ok"):
            return switched
        sid = str(switched.get("id") or "")
        agent = self.agent
        if agent is not None and sid and hasattr(agent.mind, "set_session_meta"):
            try:
                agent.mind.set_session_meta(
                    sid,
                    ad=folder.name[:80] or "Dornick ile aç",
                    path=str(folder),
                )
                # Proje klasörü etiketine de yaz: geçmiş listesinde gruplansın.
                if hasattr(agent.mind, "set_project"):
                    agent.mind.set_project(sid, folder.name[:80] or "Dornick ile aç")
            except Exception:
                pass
            try:
                self._apply_session_context(sid)
            except Exception:
                pass

        # Tohum mesajı: chat kuyruğu üzerinden (tur boşsa hemen başlar).
        if seed:
            try:
                self.submit(seed)
            except Exception:
                pass
        try:
            self.hub.emit({"type": "jobs_refresh"})
            self.hub.emit({"type": "notice", "text": f"Açıldı: {folder}"})
        except Exception:
            pass
        return {"ok": True, "id": sid, "path": str(folder)}

    def apply_session_context(self, session_id: str) -> None:
        """Dış çağrı (sohbet-modeli seçildi/temizlendi): canlıya uygula."""
        self._apply_session_context(session_id)

    def _apply_session_context(self, session_id: str) -> None:
        """Oturum metasındaki klasör + modeli canlıya uygular.

        İkisi de SOHBETE özeldir ve yalnız BELLEKTE uygulanır — eski hal
        klasörü settings.apply ile diske yazıyordu; yeni konuşmada path
        olmasa bile önceki projenin git çubuğu (dornick / dal) kalıyordu.
        Taban her zaman diskteki küresel ayar: pin varsa üstüne biner,
        pin yoksa (ya da silindiyse) taban geri gelir.
        """
        agent = self.agent
        if agent is None:
            return
        mind = agent.mind
        if not hasattr(mind, "session_meta"):
            return
        kayit = (mind.session_meta() or {}).get(session_id) or {}
        path = str(kayit.get("path") or "").strip()
        model_name = str(kayit.get("model") or "").strip()

        from dataclasses import replace as _degistir

        from . import settings as saved_settings

        try:
            disk = saved_settings._from_disk(agent.config)
        except Exception:
            disk = agent.config

        # Klasör: sohbet path'i varsa onu, yoksa küresel projeyi uygula.
        disk_proje = str(disk.sandbox.project or "").strip()
        hedef_proje = path or disk_proje
        if hedef_proje != str(agent.config.sandbox.project or "").strip():
            try:
                self.reload(_degistir(
                    agent.config,
                    sandbox=_degistir(agent.config.sandbox, project=hedef_proje),
                ))
            except Exception:
                pass

        taban = disk.model
        if model_name and saved_settings.batch_only_model(model_name):
            model_name = model_name.rsplit(":", 1)[0]
        hedef = _degistir(taban, name=model_name) if model_name else taban
        if hedef != agent.config.model:
            try:
                # Sohbet pininde de katalog penceresini doldur.
                if model_name:
                    try:
                        hedef = saved_settings.adopt_caps(agent.config, hedef)
                    except Exception:
                        pass
                self.reload(_degistir(agent.config, model=hedef))
            except Exception:
                pass

        # Composer git çubuğu canlı config'ten okunur; oturum değişince
        # yenilenmezse eski repo/dal adı yeni konuşmada asılı kalır.
        hub = getattr(self, "hub", None)
        if hub is not None:
            try:
                hub.emit({"type": "git"})
            except Exception:
                pass

    def _switch(self, sid: str | None) -> dict[str, Any]:
        """Aktif oturumu değiştirir. sid None ise yeni, değilse o oturum.

        Paralel oturumlar (canlı istek, 29.08): geçiş MEŞGULKEN DE çalışır.
        Aktif şerit boştaysa ucuz yol — aynı ajan yeni oturuma bağlanır
        (şerit sayısı 1'de kalır). Meşgulse koşan şeride DOKUNULMAZ: hedef
        için ayrı bir şerit bulunur ya da kurulur; eski tur kendi şeridinde
        arka planda biter, kenar çubuğu rozeti koştuğunu gösterir.
        """
        aktif = self._serit()
        agent = aktif.agent if aktif else None
        if agent is None or self.server is None:
            return {"ok": False, "error": "henüz hazır değil"}

        from pathlib import Path

        from .events import EventLog
        from .session import Session

        sessions_dir = agent.config.sessions_dir

        # Hedef zaten bir şeritte mi (arka planda koşuyor ya da bekliyor)?
        if sid and sid in self.seritler and sid != self._aktif_sid:
            return self._aktive_et(self.seritler[sid], resumed=True)

        if sid:
            path = Path(sessions_dir) / f"{sid}.jsonl"
            if not path.is_file():
                return {"ok": False, "error": "oturum bulunamadı"}
            session = Session(EventLog(path), sid)
            resumed = True
        else:
            session = Session.create(sessions_dir)
            resumed = False

        onceki_sid = ""
        if agent.session is not None:
            onceki_sid = str(getattr(agent.session, "id", "") or "")

        if aktif.busy:
            # Koşan şeridin altından oturum çekilmez: hedef için YENİ şerit.
            try:
                yeni = self._serit_kur(session)
            except Exception as exc:
                return {"ok": False,
                        "error": f"şerit kurulamadı: {type(exc).__name__}: {exc}"}
            self._model_devri(agent, onceki_sid, session, resumed)
            return self._aktive_et(yeni, resumed=resumed)

        # Boş şeritte ucuz yol: aynı ajan yeni oturuma bağlanır.
        eski_anahtar = aktif.sid
        eski_oturum = agent.session      # günlüğü aşağıda kapatılacak
        agent.session = session
        agent.mind.session_id = session.id
        agent._last_encoded = ""      # yeni oturumda anlık-encode tekrarını sıfırla
        aktif.sid = session.id
        self.seritler.pop(eski_anahtar, None)
        self.seritler[session.id] = aktif
        self._aktif_sid = session.id
        self.server.rebind(session)
        # Eski oturumun günlük dosyasını KAPAT. Windows açık bir dosyayı
        # taşıtmıyor: kapatılmayınca kullanıcı o sohbeti silmek/arşivlemek
        # istediğinde "WinError 32 — dosya başka bir işlem tarafından
        # kullanılıyor" hatası alıyordu (canlı yara, 02.09; hem bende hem
        # kullanıcıda görüldü). Başka bir şerit aynı oturumu tutuyorsa
        # dokunulmuyor.
        try:
            if (eski_oturum is not None and eski_oturum is not session
                    and not any(getattr(s.agent, "session", None) is eski_oturum
                                for s in self.seritler.values())):
                eski_oturum.close()
        except Exception:
            pass
        self._model_devri(agent, onceki_sid, session, resumed)
        # Sohbete özel klasör / model — geçişte uygula.
        try:
            self._apply_session_context(session.id)
        except Exception:
            pass
        _biten_kanallari_dusur(agent)
        # Sayaçlar sohbete özel: önceki konuşmanın harcaması yeni/öteki
        # sohbette kalmasın; sürdürülen sohbet geçmiş toplamını alsın.
        self._kullanim_sifirla()
        if resumed:
            try:
                self._oturum_tohumla(_gecmis_kullanim(agent))
            except Exception:
                pass
        self.hub.emit({"type": "session_reset", "id": session.id, "resumed": resumed})
        self.hub.emit({"type": "channels", "channels": _live_channels(agent)})
        return {"ok": True, "id": session.id, "resumed": resumed}

    def _model_devri(self, agent: Any, onceki_sid: str, session: Any,
                     resumed: bool) -> None:
        """Yeni sohbet son sohbetin modelini devralır — yalnız son sohbet
        bir model SABİTLEMİŞSE. Sabitlemeyen kullanıcıda akış eskisi gibi:
        küresel varsayılan neyse o."""
        if resumed or not onceki_sid or not hasattr(agent.mind, "session_meta"):
            return
        try:
            eski_kayit = (agent.mind.session_meta() or {}).get(onceki_sid) or {}
            if eski_kayit.get("model"):
                agent.mind.set_session_meta(
                    session.id,
                    model=str(eski_kayit["model"]),
                    provider=str(eski_kayit.get("provider") or ""))
        except Exception:
            pass

    def _aktive_et(self, serit: Serit, *, resumed: bool) -> dict[str, Any]:
        """Var olan bir şeridi arayüzün baktığı şerit yapar.

        Koşan şeride dokunulmaz — yalnız yayın hedefi değişir: sunucu o
        oturumun günlüğüne bağlanır, arayüz dökümü oradan yeniden yükler,
        meşguliyet ve kanallar o şeridin gerçeğinden basılır.
        """
        self._aktif_sid = serit.sid
        self.server.rebind(serit.agent.session)
        try:
            self._apply_session_context(serit.sid)
        except Exception:
            pass
        self._kullanim_sifirla()
        if resumed:
            try:
                self._oturum_tohumla(_gecmis_kullanim(serit.agent))
            except Exception:
                pass
        self.hub.emit({"type": "session_reset", "id": serit.sid,
                       "resumed": resumed})
        self.hub.emit({"type": "status", "busy": serit.busy})
        self.hub.emit({"type": "channels",
                       "channels": _live_channels(serit.agent)})
        return {"ok": True, "id": serit.sid, "resumed": resumed}

    def _serit_kur(self, session: Any) -> Serit:
        """Yeni bir oturum için bağımsız şerit kurar.

        Ajan sıfırdan: kendi zihni (aynı SQLite, ayrı bağlantı — oturum
        kimliği karışmasın), kendi kayıt defteri, TEMİZ taban yapılandırma
        (başka sohbetin sabitlediği model buraya sızmaz; sohbete özel pin
        aktivasyonda `_apply_session_context` ile gelir). Model istemcisi
        aynı (ad, adres) için ÖNBELLEKTEN paylaşılır: yerel sunucuda iki
        istemci modeli iki kez yükletirdi; paylaşılan istemcinin kapısı
        istekleri zaten sıraya koyar.
        """
        ornek = self._serit()
        if ornek is None or ornek.agent is None:
            raise RuntimeError("kurulu şerit yok")
        cfg = settings._from_disk(ornek.agent.config)

        mind = open_mind(cfg.mind_dir, cfg.sessions_dir, session.id)
        registry = build_registry(mind, subagents=not prompt.is_lean(cfg))

        if not hasattr(self, "_istemciler"):
            self._istemciler: dict[tuple[str, str], Any] = {}
            eski_model = ornek.agent.config.model
            self._istemciler[(eski_model.name, str(eski_model.base_url or ""))] = (
                ornek.agent.client)
        anahtar = (cfg.model.name, str(cfg.model.base_url or ""))
        client = self._istemciler.get(anahtar)
        if client is None:
            client = build_client(cfg.model)
            self._istemciler[anahtar] = client

        serit = Serit(sid=session.id, agent=None, queue=asyncio.Queue())
        agent = Agent(
            config=cfg,
            session=session,
            registry=registry,
            client=client,
            io=self.io(serit),
            permissions=PermissionEngine.from_config(cfg.permissions),
            policy=ContextPolicy(cfg.context),
            schedule=getattr(ornek.agent, "schedule", None),
            mind=mind,
        )
        agent.on_children_settled = (
            lambda s=serit: self.loop.call_soon_threadsafe(
                self._serit_child_done, s))
        agent.on_retry_wait = self._swap_model
        serit.agent = agent
        self.seritler[session.id] = serit
        serit.task = self.loop.create_task(self._pompa(serit))
        return serit

    def compact_now(self) -> dict[str, Any]:
        """Bağlamı ŞİMDİ sıkıştırır (kompozerdeki `/sifirla` komutu).

        Aynı yol kendiliğinden de işliyor: pencere dolmaya yaklaşınca
        `_relieve_pressure` bunu zaten çağırıyor. Buradaki tek fark kararı
        kullanıcının vermesi — "konuşma ağırlaştı, topla" diyebilmek.

        Yalnız boştayken: akan bir turun altından geçmişi özetleyip
        değiştirmek o cevabı bozar.
        """
        serit = self._serit()
        agent = serit.agent if serit else None
        if agent is None:
            return {"ok": False, "error": "henüz hazır değil"}
        if serit.busy:
            return {"ok": False, "error": "Dornick meşgul; tur bitince dene", "busy": True}

        async def _kos() -> None:
            self._serit_durum(serit, True)
            try:
                if not await agent._compact(reason="kullanıcı istedi"):
                    self._serit_yayin(serit, {"type": "notice", "text":
                                   "Sıkıştıracak kadar geçmiş yok — bağlam zaten kısa."})
            except Exception as exc:   # sıkıştırma uygulamayı düşürmemeli
                self._serit_yayin(serit, {"type": "notice",
                                          "text": f"{type(exc).__name__}: {exc}"})
            finally:
                self._serit_durum(serit, False)
                self._serit_yayin(serit, {"type": "turn_end"})

        asyncio.run_coroutine_threadsafe(_kos(), self.loop)
        return {"ok": True}

    def wake(self) -> None:
        """Uyandırma sözü duyuldu: pencere gizliyse geri gelsin.

        Pencere gizliyken de sayfa çalışıyor ve mikrofon dinliyor; duyulan
        söze cevap verilirken kullanıcının cevabı görebilmesi gerekiyor.
        """
        if self.on_wake is not None:
            self.on_wake()

    def interrupt(self) -> None:
        if self.agent is not None:
            self.loop.call_soon_threadsafe(self.agent.interrupt)

    def resolve_approval(
        self, request_id: str, granted: bool, *, always: bool = False
    ) -> None:
        pending = self._pending.get(request_id)
        if pending is None or pending.future.done():
            return
        if always and granted and self.agent is not None:
            # Ayni arac ve ayni hedef bir daha sorulmasin. Kural izin
            # motoruna yaziliyor; karar dongunun disinda kaliyor.
            rule = self.agent.permissions.remember_allow(pending.spec, pending.args)
            self.hub.emit({"type": "notice", "text": f"Kural eklendi: {rule}"})
        self.loop.call_soon_threadsafe(pending.future.set_result, granted)

    def reload(self, config: Config, *, force: bool = False) -> None:
        """Ayar sayfası kaydettiğinde çağrılır.

        İzin kipi ve bağlam politikası anında geçiyor. Model de artık
        geçiyor: "kaydet"e basıp hiçbir şeyin değişmediğini görmek, sonra
        programı kapatıp açmak gerektiğini keşfetmek iyi bir ayar sayfası
        değil.

        `force`: model adı/adresi aynı kalsa bile istemciyi yeniden kur.
        Anahtar değişiminde şart — API anahtarı `ModelConfig`'in parçası değil
        (yalnız env adı), o yüzden anahtarı değiştirmek `config.model`'i
        değiştirmiyor ve eski istemci eski anahtarla kalıyordu; yeni anahtar
        ancak yeniden başlatınca etkili oluyordu. Artık anahtar değişince de
        istemci tazeleniyor.

        Geçmiş yeni modele taşınıyor — kullanıcıya söyleniyor, sessizce
        yapılmıyor. Turun ortasındaysak değişiklik bir sonraki model
        çağrısına (araç turu arası) kadar bekler: akan stream kesilmez.
        """
        agent = self.agent
        if agent is None:
            self.sync_camera(config)
            self.sync_hearing(config)
            self.hub.emit({
                "type": "voice",
                "enabled": bool(config.voice.enabled),
            })
            return

        was = agent.permissions.mode
        before = agent.config.model
        agent.permissions = PermissionEngine.from_config(config.permissions)

        # Bekleyen izin kartları yeni kiple YENİDEN değerlendiriliyor: tam
        # yetkiye geçen kullanıcı açık kartın kendiliğinden onaylanmasını
        # bekliyor. Eski hal kartı asılı bırakıyordu — tur sonsuza dek izin
        # bekliyor, Durdur bile işlemiyordu (canlı yara, 01.09: "yolo izin
        # verdim, tam yetki dedim, sonra öyle kaldı").
        from .permissions import Decision as _Karar
        # getattr: önizleme/test köprüleri __new__ ile kurulabiliyor.
        for bekleyen in tuple(getattr(self, "_pending", {}).values()):
            if bekleyen.future.done():
                continue
            try:
                karar, _kural = agent.permissions.evaluate(
                    bekleyen.spec, bekleyen.args)
            except Exception:
                continue
            if karar is _Karar.ALLOW or karar is _Karar.DENY:
                deger = karar is _Karar.ALLOW
                fut = bekleyen.future
                self.loop.call_soon_threadsafe(
                    lambda f=fut, d=deger: None if f.done() else f.set_result(d))

        if was != config.permissions.mode:
            self.hub.emit({"type": "notice", "text": f"İzin kipi: {config.permissions.mode}"})
            # Dock çipi ve plan-onay düğmesi gerçek kipi göstersin: ayar
            # sayfası DIŞINDAN (başka sekme, dış kapı) değişen kip de
            # arayüze olay olarak düşmeli — notice metni makine okunur değil.
            self.hub.emit({"type": "mode", "mode": config.permissions.mode})

        model_changed = before != config.model
        if model_changed or force:
            # İstemci (ve onunla birlikte sistem promptu) yeniden kuruluyor;
            # tur ortasındaysak bir sonraki client.turn öncesi uygulanır.
            self._wanted_model = config.model
            self._wanted_config = config
            self._swap_note = (
                f"Model değişti: {config.model.name}. Konuşma geçmişi taşındı."
                if model_changed
                else "Ayarlar uygulandı — istemci tazelendi (anahtar/adres)."
            )
            if not self._busy:
                self._swap_model()
        else:
            # Model aynı ama başka bir şey değişmiş olabilir: duyu açıldı,
            # cihaz eklendi, bağlam politikası değişti. Bunlar bir sonraki
            # tura anında girmeli — yeniden başlatmaya gerek yok.
            agent.reconfigure(config)
        # Kamera anahtarı anında: ayar kaydı Lens'i start/stop eder, yeniden
        # başlatmaya gerek yok (LED/GPU oturum ortasında kapanabilmeli).
        self.sync_camera(config)
        self.sync_hearing(config)
        self.hub.emit({
            "type": "voice",
            "enabled": bool(config.voice.enabled),
        })

    def _on_camera_motion(self, sighting: watching.Sighting) -> None:
        """İzleyici hareketi: HUD kapalıysa sohbet açılmaz.

        Ayar anlık okunur — açılıştaki bayrağa kapanmış bir kapanış olmasın.
        """
        agent = getattr(self, "agent", None)
        cfg = getattr(agent, "config", None) if agent is not None else None
        if cfg is None:
            server = getattr(self, "server", None)
            cfg = getattr(server, "config", None) if server is not None else None
        if cfg is None or not bool(getattr(cfg.camera, "enabled", False)):
            return
        _hareket_gonder(self, cfg, self.hub, sighting)

    def sync_camera(self, config: Config) -> dict[str, Any]:
        """Kamera anahtarını donanıma uygular: Lens, izleyici, LED, YOLO ısısı.

        HUD yalnız Lens'i kapatıyordu; arka plan izleyici (Watcher) kameraları
        okumaya devam edip sohbete hareket mesajı basıyordu. İkisi aynı kapı.
        """
        from . import sight, watch as watching

        want = bool(config.camera.enabled)
        server = getattr(self, "server", None)
        httpd = getattr(server, "_httpd", None) if server else None
        agent = getattr(self, "agent", None)
        lens = getattr(self, "lens", None)
        eyes = getattr(self, "eyes", None)
        live = False
        note = ""
        if want:
            if not watching.available():
                note = "opencv yok"
            else:
                if lens is None:
                    lens = watching.Lens()
                    self.lens = lens
                if not lens.running:
                    if lens.start():
                        live = True
                        threading.Thread(
                            target=sight.ensure_warmup, daemon=True,
                            name="dornick-sight-warm").start()
                    else:
                        note = "kamera açılamadı"
                else:
                    lens.unsnooze()
                    live = True
                if agent is not None:
                    agent.lens = lens
                if httpd is not None:
                    httpd.lens = lens
                if eyes is None:
                    eyes = watching.Watcher([], self._on_camera_motion)
                    self.eyes = eyes
                eyes.load_from(watching.load(config.state_dir))
                eyes.unsnooze()
                if eyes.start():
                    live = True
                if agent is not None:
                    agent.watcher = eyes
        else:
            if lens is not None:
                lens.stop()
            if eyes is not None:
                eyes.stop()
            if agent is not None:
                agent.lens = None
                agent.watcher = None
            if httpd is not None:
                httpd.lens = None
        if server is not None:
            server.lens = lens if want else None
        payload = {
            "type": "camera",
            "enabled": want,
            "live": live,
            "note": note,
        }
        hub = getattr(self, "hub", None)
        if hub is not None:
            hub.emit(payload)
        return payload

    def camera_power(self, on: bool) -> str:
        """Sohbet/HUD: kamerayı tamamen aç veya kapat (ayarı da yazar)."""
        from . import settings as settings_mod

        agent = getattr(self, "agent", None)
        server = getattr(self, "server", None)
        cfg = agent.config if agent is not None else getattr(server, "config", None)
        if cfg is None:
            return "Kamera ayarı yok."
        updated = settings_mod.apply(cfg, {"camera": {"enabled": bool(on)}})
        if server is not None:
            server.config = updated
        if agent is not None:
            agent.reconfigure(updated)
        result = self.sync_camera(updated)
        if on and result.get("live"):
            return (
                "Kamera açık. LED yanıyor. Sorduğunda yerel analiz metin "
                "olarak gelir; resim kendiliğinden modele gitmez."
            )
        if on:
            return "Kamera açılamadı" + (
                f": {result['note']}" if result.get("note") else ".")
        return "Kamera kapalı. Aygıt bırakıldı, LED söner."

    def sync_hearing(self, config: Config) -> dict[str, Any]:
        """Dinleme anahtarını donanıma uygular: Ear start/stop.

        Ayar kaydı tek başına yetmiyordu — bayrak değişiyor, kulak ancak
        yeniden başlatınca açılıyordu; o yüzden yalnız bas-konuş duyuluyordu.
        Uyandırma sözü veya serbest dinleme (`open`) varsa kulak açılır.
        """
        from . import listen as recogniser

        want = _hearing_wanted(config)
        server = getattr(self, "server", None)
        httpd = getattr(server, "_httpd", None) if server else None
        agent = getattr(self, "agent", None)
        ear = getattr(self, "ear", None)
        live = False
        note = ""

        def wire(next_ear: Any) -> None:
            self.ear = next_ear
            if httpd is not None:
                httpd.ear = next_ear
            if agent is not None:
                agent.ear = next_ear

        if want:
            if _ear_alive(ear):
                ear.open = bool(config.listen.open)
                ear.wake = config.listen.wake
                ear.unsnooze()
                live = True
                wire(ear)
            else:
                if ear is not None:
                    try:
                        ear.stop()
                    except Exception:
                        pass
                hub = getattr(self, "hub", None)
                if hub is None:
                    note = "hub yok"
                    wire(None)
                else:
                    ear = _open_ear(config, self, hub)
                    if ear is None:
                        note = "kulak açılamadı"
                        wire(None)
                    else:
                        live = True
                        wire(ear)
                        if httpd is not None:
                            server_module.warm_ear(httpd, config)
        else:
            if ear is not None:
                try:
                    ear.stop()
                except Exception:
                    pass
            wire(None)
            if not config.listen.enabled:
                note = ""
            elif not hearing.available():
                note = "mikrofon paketi yok"
            elif not recogniser.available():
                note = "tanıma paketi yok"
            elif not (config.listen.wake.strip() or config.listen.open):
                note = "uyandırma veya serbest dinleme yok"

        payload = {
            "type": "hearing",
            "enabled": bool(config.listen.enabled),
            "live": live,
            "open": bool(config.listen.open),
            "wake": bool(config.listen.wake.strip()),
            "snoozed": bool(self.ear is not None
                            and getattr(self.ear, "snoozed", False)),
            "note": note,
        }
        hub = getattr(self, "hub", None)
        if hub is not None:
            hub.emit(payload)
        return payload

    def hearing_power(self, on: bool) -> str:
        """HUD: dinlemeyi aç veya kapat (ayarı da yazar).

        Açarken serbest dinleme de açılır: uyandırma sözü beklenmeden
        duyulan cümle ajana gider. Kapatınca mikrofon bırakılır.
        """
        from . import settings as settings_mod

        agent = getattr(self, "agent", None)
        server = getattr(self, "server", None)
        cfg = agent.config if agent is not None else getattr(server, "config", None)
        if cfg is None:
            return "Dinleme ayarı yok."
        updated = settings_mod.apply(cfg, {
            "listen": {"enabled": bool(on), "open": bool(on)},
        })
        if server is not None:
            server.config = updated
        if agent is not None:
            agent.reconfigure(updated)
        result = self.sync_hearing(updated)
        if on and result.get("live"):
            return (
                "Dinleme açık. Uyandırma sözü gerekmez — konuşman ajana gider."
            )
        if on:
            return "Kulak açılamadı" + (
                f": {result['note']}" if result.get("note") else ".")
        return "Dinleme kapalı. Mikrofon bırakıldı."

    def voice_power(self, on: bool) -> str:
        """HUD: sesi aç veya kapat (ayarı da yazar)."""
        from . import settings as settings_mod

        agent = getattr(self, "agent", None)
        server = getattr(self, "server", None)
        cfg = agent.config if agent is not None else getattr(server, "config", None)
        if cfg is None:
            return "Ses ayarı yok."
        updated = settings_mod.apply(cfg, {"voice": {"enabled": bool(on)}})
        if server is not None:
            server.config = updated
        if agent is not None:
            agent.reconfigure(updated)
        hub = getattr(self, "hub", None)
        if hub is not None:
            hub.emit({"type": "voice", "enabled": bool(on)})
        if on:
            return "Ses açık."
        return "Ses kapalı."

    def _swap_model(self) -> None:
        """Bekleyen model değişikliğini uygular.

        Eski istemci burada kapatılmıyor: kapatmak bir eşyordam ve bu
        çağrı HTTP thread'inden geliyor. Döngüye bırakılıyor.
        """
        wanted = self._wanted_model
        pending = self._wanted_config
        self._wanted_model = None
        self._wanted_config = None
        agent = self.agent
        if wanted is None or agent is None:
            return

        from .backends import build_client

        try:
            fresh = build_client(wanted)
        except Exception as exc:
            self.hub.emit({"type": "notice", "text": f"Model değiştirilemedi: {exc}"})
            return

        old = agent.client
        agent.client = fresh
        # Yeni model LM Studio'ysa doğru pencereyle yüklet ve GERÇEK yüklü
        # pencereyi ayara çek — boot'taki ile aynı: canlı model değişiminde de
        # (kullanıcı ayarlardan değiştirince) pencere gerçekle uyuşsun, yoksa
        # sıkıştırma geç tetiklenip istem taşıyor. LM Studio dışı sağlayıcıda
        # sessizce hiçbir şey yapmıyor.
        if pending is not None:
            try:
                _prepare_model(pending)
            except Exception:
                pass
        # İstemci ve sistem promptu birlikte tazeleniyor: yeni model dar
        # pencereliyse lean hale geçmeli, araç şemaları kısalmalı. İkisi
        # ayrı düşerse biri yeni modele biri eskisine göre kalır.
        if pending is not None:
            agent.reconfigure(pending)
        # Yeni modelin fiyatı yeniden sorulmalı: eski etiketle harcama
        # göstermek yanlış rakam basmak olur. Bir sonraki usage olayı
        # arka planda taze etiketi çektirir.
        self._fiyat = None
        self._fiyat_bakildi = False
        note = self._swap_note or f"Model değişti: {wanted.name}."
        self._swap_note = ""
        self.hub.emit({"type": "notice", "text": note})
        # Paylaşımlı istemci önbelleği (paralel şeritler): eski istemciyi
        # BAŞKA bir şerit hâlâ kullanıyorsa kapatma — altından bağlantı
        # çekmek koşan turu düşürür. Önbellekten de yalnız kimse
        # kullanmıyorsa düşülür.
        kullanan = any(s.agent is not None and s.agent.client is old
                       for s in self.seritler.values())
        if not kullanan:
            for anahtar, istemci in list(getattr(self, "_istemciler", {}).items()):
                if istemci is old:
                    self._istemciler.pop(anahtar, None)
            self.loop.call_soon_threadsafe(
                lambda: self.loop.create_task(_retire(old)))
        # Yeni istemci önbelleğe: aynı modele açılacak yeni şerit paylaşsın.
        if hasattr(self, "_istemciler"):
            self._istemciler[(wanted.name, str(wanted.base_url or ""))] = fresh

    def waking(self, stage: str, *, ready: bool = False) -> None:
        """Açılışın hangi adımında olunduğunu duyurur.

        Model yüklenirken pencere boş durmasın; ne beklendiği yazsın ve
        hazır olunca canlansın.
        """
        self.stage = stage
        self.ready = ready
        self.hub.emit({"type": "waking", "stage": stage, "ready": ready})

    @property
    def busy(self) -> bool:
        return self._busy

    def snapshot(self) -> dict[str, Any]:
        agent = self.agent
        # Bu süreçte bir tur koştuysa canlı sayaç doğrudur; koşmadıysa
        # (sürdürülen oturum, taze açılış) gerçek durum oturum günlüğünde.
        canli = int((getattr(agent, "_last_usage", None) or {}).get("prompt_total") or 0)
        gecmis = ({"prompt_total": canli, "output": 0, "cagri": 0, "tahmin": False}
                  if canli else _gecmis_kullanim(agent) if agent
                  else {"prompt_total": 0, "output": 0, "cagri": 0, "tahmin": False})
        # Maliyet çipinin oturum toplamı da aynı kaynaktan tohumlanıyor:
        # yeni turlar bunun ÜSTÜNE ekleniyor (bkz. _usage_yay).
        self._oturum_tohumla(gecmis)
        return {
            "busy": self._busy,
            "ready": self.ready,
            "stage": self.stage,
            "session": agent.session.id if agent else "",
            "model": agent.config.model.name if agent else "",
            # Sağlayıcı ADI arayüz için: `model.provider` backend TİPİdir
            # ("openai") ve OpenRouter'a bağlıyken "openai" yazmak yanıltıcı.
            # Ayarlardaki gerçek sağlayıcı kimliği adrese bakarak bulunuyor.
            "provider": _saglayici_adi(agent),
            # Kompozer altındaki şerit için: düşünme derinliği ve bağlam
            # penceresi. Pencere olmadan kullanım yüzdesi hesaplanamıyor.
            "effort": agent.config.model.effort if agent else "",
            "context_window": int(agent.config.model.context_window) if agent else 0,
            # Son turun istem toplamı: sayfa yenilenince — ve uygulama
            # kapanıp açılınca — bağlam göstergesi sıfırdan değil kaldığı
            # yerden başlasın. Bu süreçte hiç tur koşmadıysa (sürdürülen
            # oturum) değer oturum günlüğünden geliyor; bkz. _gecmis_kullanim.
            "prompt_total": gecmis["prompt_total"],
            # Rakam sağlayıcının saydığı gerçek değil, kaba bir tahmin mi?
            # Arayüz bunu title'da söylüyor — uydurma kesinlik satılmıyor.
            "tahmin": gecmis["tahmin"],
            # Bağlam kutusunun kalem kalem kırılımı (sistem / araç / ruh /
            # yetenek / MCP / konuşma). Toplam yokken de sabitler görünür.
            "kirilim": baglam_kirilim(agent, gecmis["prompt_total"]),
            # Maliyet çipi: sayfa yenilenince harcama göstergesi sıfırdan
            # değil kaldığı yerden başlasın. Fiyat bilinmiyorsa None —
            # çip token sayısına düşer.
            "fiyat": self._fiyat,
            "kullanim": {
                "tur": dict(self._tur_kullanim),
                "oturum": dict(self._oturum_kullanim),
            },
            # Bu oturum için konmuş harcama sınırı (USD) — None = sınırsız.
            # Sayfa yenilenince maliyet çipi sınırı unutmasın.
            "butce": self._butce_usd,
            "mode": agent.permissions.mode if agent else "",
            # Aktif hedefler: sayfa yenilenince hedef paneli olay akışını
            # kaçırmış oluyor; panel bu listeyle tohumlanıp kaldığı yerden
            # sürüyor.
            "goals": _active_goals(agent),
            # Yardımcı kanalları: orkestra paneli de aynı sebepten buradan
            # tohumlanıyor — hayalet "çalışıyor" kartı kalmasın, yetimler
            # "yarım kaldı" olarak görünsün.
            "channels": _live_channels(agent),
            "voice": bool(agent and agent.config.voice.enabled),
            # Sesin karakteri tarayıcıda uygulanıyor: sentezleyici düz bir
            # insan sesi üretiyor, katman onun üstüne biniyor.
            "character": float(agent.config.voice.character) if agent else 0.0,
            "listen": bool(agent and agent.config.listen.enabled),
            "wake": bool(agent and agent.config.listen.wake.strip()),
            "open": bool(agent and agent.config.listen.open),
            "ear": bool(_ear_alive(self.ear)),
            "snoozed": bool(self.ear is not None
                            and getattr(self.ear, "snoozed", False)),
            "camera": bool(agent and agent.config.camera.enabled),
            "tools": len(agent.registry) if agent else 0,
            # Çalışan kopyanın sürümü: üst bar marka ipucu buradan besleniyor.
            # Sahada "hangi sürüm açık?" sorusu cevapsız kalmasın.
            "surum": ortam.surum(),
            "kurulu": ortam.kurulu_mu(),
            # Ajan gerçekten kimlik doğrulayabiliyor mu (anahtar var ya da
            # yerel sunucu)? Arayüz ilk-kurulum yönlendirmesini buna göre
            # gösteriyor — model "oto" gelse bile anahtar yoksa iş yapılamaz.
            "can_run": _calisabilir(agent),
            # Çalışma dizini: sohbet ekranı atölyede mi yoksa bağlı bir
            # klasörde mi olduğunu göstersin. project boşsa atölyedeyiz.
            "workspace": str(agent.config.workspace) if agent else "",
            "project": (str(getattr(agent.config.sandbox, "project", "") or "")
                        if agent else ""),
            # Program kapalıyken zamanı geçmiş görevler (açılış sorusu).
            "missed_tasks": self._missed_tasks_payload(),
        }

    def missed_pending(self) -> bool:
        """Kaçırılan görevler için kullanıcı kararı bekleniyor mu?"""
        return bool(self._missed_ids)

    def _missed_tasks_payload(self) -> list[dict[str, Any]]:
        if not self._missed_ids:
            return []
        book = getattr(self.agent, "schedule", None) if self.agent else None
        if book is None:
            return []
        from . import schedule as scheduling

        out: list[dict[str, Any]] = []
        for tid in self._missed_ids:
            task = book.get(tid)
            if task is not None:
                row = scheduling.payload([task])
                if row:
                    out.append(row[0])
        return out

    def resolve_missed(self, action: str) -> dict[str, Any]:
        """Kaçırılan görevler: şimdi koştur veya bu seferlik atla."""
        if not self._missed_ids:
            return {"ok": True, "resolved": 0}

        book = getattr(self.agent, "schedule", None) if self.agent else None
        if book is None:
            return {"ok": False, "error": "zamanlayıcı yok"}

        ids = list(self._missed_ids)
        act = str(action or "").strip().lower()
        count = 0

        if act in ("run", "missed_run", "yap"):
            claimed = book.due(only=ids)
            fire = self._missed_fire
            for task in claimed:
                try:
                    if fire is not None:
                        fire(task)
                    else:
                        self.run_scheduled(task)
                    count += 1
                except Exception as exc:
                    book.note_run(task.id, f"başlatılamadı: {type(exc).__name__}")
        elif act in ("skip", "missed_skip", "atla"):
            for tid in ids:
                if book.skip_occurrence(tid):
                    count += 1
        else:
            return {"ok": False, "error": "run veya skip gerekli"}

        self._missed_ids = []
        self.hub.emit({"type": "missed_resolved", "action": act, "count": count})
        if act.startswith("skip") or act == "atla":
            self.hub.emit({"type": "jobs_refresh"})
        return {"ok": True, "action": act, "count": count}

    # -- maliyet çipi ---------------------------------------------------

    def _kullanim_sifirla(self) -> None:
        """Aktif sohbet değişince sayaçlar o sohbete ait olsun.

        Bridge tek sayaç tutuyor; sohbet A'dan B'ye geçince eski toplam
        ya B'ye yapışıyor ya da `_oturum_tohumlandi` yüzünden B'nin
        geçmişi hiç yüklenmiyordu — çip her yeniden açılışta sıfır
        görünüyordu (canlı şikâyet). Sıfırla; tohum bir sonraki
        snapshot / açık tohum çağrısında doğru günlükten gelir.
        """
        self._tur_kullanim = {"girdi": 0, "cikti": 0, "cagri": 0}
        self._oturum_kullanim = {"girdi": 0, "cikti": 0, "cagri": 0}
        self._oturum_tohumlandi = False

    def _oturum_tohumla(self, gecmis: dict[str, Any]) -> None:
        """Sürdürülen oturumun harcamasını çipe bir kez tohumlar.

        Bağlam çubuğuyla aynı yara: yeniden açılan bir konuşmada çip de
        sıfırdan başlıyordu. Tohum YALNIZCA bir kez ve yalnızca bu
        sohbet için hiç tur koşmamışken konuyor — yoksa her snapshot
        (sayfa yenileme) toplamı şişirirdi. `girdi` tüm turların
        toplamı; canlı `_usage_yay` muhasebesiyle aynı dil.
        """
        if self._oturum_tohumlandi or self._oturum_kullanim["cagri"]:
            return
        if not gecmis.get("cagri"):
            return
        self._oturum_tohumlandi = True
        # Eski günlükler yalnız prompt_total taşıyabilir — geriye uyum.
        girdi = int(gecmis.get("girdi") or gecmis.get("prompt_total") or 0)
        self._oturum_kullanim = {
            "girdi": girdi,
            "cikti": int(gecmis.get("output") or 0),
            "cagri": int(gecmis.get("cagri") or 0),
        }

    def _usage_yay(self, report: dict[str, int]) -> None:
        """Tur-sonu kullanım raporunu toplayarak hub'a akıtır.

        Olay sözleşmesi (arayüzdeki maliyet çipi buna bağlı):
            {type: "usage", ...cache_report alanları,
             tur:    {girdi, cikti, cagri},    bu kullanıcı turunun toplamı
             oturum: {girdi, cikti, cagri},    oturumun toplamı
             fiyat:  {girdi, cikti} | None}    USD/token; bilinmiyorsa None

        `girdi` istemin tamamı (prompt_total: önbellek dahil) — tahmin
        kasıtlı olarak muhafazakâr, önbellek indirimi sayılmıyor. Fiyat
        None ise çip token sayısı gösterir.
        """
        for hedef in (self._tur_kullanim, self._oturum_kullanim):
            hedef["girdi"] += int(report.get("prompt_total") or 0)
            hedef["cikti"] += int(report.get("output") or 0)
            hedef["cagri"] += 1
        self._fiyat_getir()
        kirilim = baglam_kirilim(self.agent, int(report.get("prompt_total") or 0))
        self.hub.emit({
            "type": "usage", **report,
            "tur": dict(self._tur_kullanim),
            "oturum": dict(self._oturum_kullanim),
            "fiyat": self._fiyat,
            "kirilim": kirilim,
        })

    # -- bütçe freni ----------------------------------------------------

    def butce(self, usd: Any = None) -> dict[str, Any]:
        """Bu oturumun harcama üst sınırını okur ya da kurar (HTTP thread).

        `usd` None/boş ise sınır KALKAR (sınırsız). Sıfır ya da negatif de
        sınırsız sayılıyor: "0 dolar harca" diye bir istek yok, elini
        klavyeye sürtmüş bir kullanıcı var.

        Sınır ayar dosyasına yazılmıyor — bilinçli. Bu bir tercih değil, bu
        oturuma konmuş bir emniyet kemeri; yarın açılan konuşma dün konan
        sınırla sessizce durmamalı.
        """
        if usd is None or usd == "":
            self._butce_usd = None
        else:
            try:
                deger = float(usd)
            except (TypeError, ValueError):
                return {"ok": False, "error": "Sayı bekleniyordu.",
                        "butce": self._butce_usd}
            self._butce_usd = deger if deger > 0 else None
        # Sınır değişti: "ulaşıldı" satırı bir kez daha basılabilsin.
        self._butce_bildirildi = False
        return {"ok": True, "butce": self._butce_usd,
                "harcanan": self._harcanan()}

    def _harcanan(self) -> float | None:
        """Bu oturumun tahmini harcaması (USD). Fiyat bilinmiyorsa None."""
        if not self._fiyat:
            return None
        o = self._oturum_kullanim
        return o["girdi"] * self._fiyat["girdi"] + o["cikti"] * self._fiyat["cikti"]

    def _butce_freni(self) -> str:
        """Sınıra ulaşıldı mı? Ulaşıldıysa sohbete basılacak tek satır.

        Ajan döngüsü her model çağrısından ÖNCE soruyor (bkz.
        loop.AgentIO.butce_freni). Burada ağ yok, dosya yok: yalnızca
        elimizdeki sayaç ile elimizdeki fiyat etiketi.

        Fiyat bilinmiyorsa (yerel sunucu, katalog dışı model) fren ÇALIŞMAZ.
        Uydurma bir dolar rakamıyla kullanıcının işini durdurmak, sınırı hiç
        koymamaktan kötü olurdu.
        """
        sinir = self._butce_usd
        if not sinir or self._butce_bildirildi:
            return ""
        harcanan = self._harcanan()
        if harcanan is None or harcanan < sinir:
            return ""
        self._butce_bildirildi = True
        return (f"Bütçe sınırına ulaşıldı (${sinir:.2f}) — "
                "devam etmek için sınırı yükselt.")

    # -- koşan görevler -------------------------------------------------

    def _cocuk_arka_plan(self, cid: str) -> bool:
        """Bu kanal arka planda mı koşuyordu (biten kanal bildirimi için)."""
        children = getattr(self.agent, "_children", None) or {}
        handle = children.get(cid)
        return bool(handle is not None and handle.arka_plan)

    def gorevler(self) -> dict[str, Any]:
        """Koşan (ve yakın zamanda bitmiş) her işin tek listesi (HTTP thread).

        İki kaynak birleşiyor, çünkü kullanıcı için ikisi de "arkada koşan
        bir şey":

          * `Agent._children` — arka plan yardımcıları (`kind="yardımcı"`)
            ve arka plan kabuk işleri (`kind="iş"`, `shell` aracının
            `arka_plan: true` yolu).
          * `apps._PROCS` — ayrılmış (detached) süreçler: `shell`in
            `background: true` yolu ve panelden başlatılan uygulamalar.

        Süre CANLI: satır `basladi` damgasını taşıyor, saymayı arayüz
        yapıyor — sunucuya saniyede bir sormaya gerek yok.
        """
        from . import apps as katalog

        rows: list[dict[str, Any]] = []

        children = getattr(self.agent, "_children", None) or {}
        from .tools.shell import kisa_is_ozeti
        for h in children.values():
            ozet = ""
            if h.state != "kosuyor":
                ozet = kisa_is_ozeti(h.sonuc or "", title=h.title)[:400]
            rows.append({
                "id": "c:" + h.id,
                "ad": h.title,
                "tur": h.kind,
                "durum": h.state,
                # Yetimde gerçek başlangıç bilinmiyor (geçen oturumdan
                # devralındı): 0 gönderiliyor, arayüz süre çizmiyor.
                "basladi": 0.0 if h.state == "yetim" else h.baslangic_ts,
                "bitti": h.bitis_ts,
                "ozet": ozet,
                "model": h.model,
                "oturum": h.session_id,
                "arka_plan": bool(h.arka_plan),
                "pid": None,
                "durdurulabilir": h.state == "kosuyor",
                "surdurulebilir": (
                    h.state in ("yetim", "bitti", "hata")
                    and bool(h.session_id)
                    and h.kind != "iş"
                ),
                "son_arac": h.son_arac if h.state == "kosuyor" else "",
                "son_hedef": h.son_hedef if h.state == "kosuyor" else "",
                "wait": h.wait if h.state == "kosuyor" else None,
                "deliverable": h.deliverable,
                "usage": dict(h.usage) if h.usage else None,
            })

        for pid, info in list(katalog._PROCS.items()):
            proc = info.get("proc")
            if proc is None:
                continue
            biten = proc.poll() is not None
            komut = str(info.get("path") or "")
            kendi = katalog.dornick_sureci_mi(komut) or katalog.dornick_sureci_mi(
                str(info.get("run") or ""))
            rows.append({
                "id": "p:" + str(pid),
                "ad": "Dornick (kendisi)" if kendi else str(info.get("name") or komut or pid),
                "tur": "süreç",
                "durum": "bitti" if biten else "kosuyor",
                "basladi": float(info.get("started") or 0.0),
                "bitti": 0.0,
                "ozet": "",
                "model": "",
                "oturum": "",
                "arka_plan": True,
                "pid": pid,
                "komut": komut,
                # Kendi kopyasını panelden öldürmek uygulamayı kapatmak olur.
                "durdurulabilir": (not biten) and not kendi,
            })

        # Koşanlar önce, sonra en yeni bitenler: kullanıcının aradığı şey
        # neredeyse hep "şu an ne dönüyor".
        rows.sort(key=lambda r: (r["durum"] != "kosuyor",
                                 -(r["bitti"] or r["basladi"])))
        return {"gorevler": rows,
                "kosan": sum(1 for r in rows if r["durum"] == "kosuyor")}

    def gorev_rapor(self, gid: str) -> dict[str, Any]:
        """Tam yardımcı/iş metni — Orkestra/Görevler tıklanınca Viewer'a.

        Sohbete yapıştırılan uzun bültenlerin yerine: panelde kısa satır,
        tıklanınca artifact benzeri sayfa.
        """
        gid = str(gid or "").strip()
        cid = gid[2:] if gid.startswith("c:") else gid
        if not cid or not re.match(r"^[A-Za-z0-9_-]+$", cid):
            return {"ok": False, "error": "Geçersiz görev kimliği."}
        children = getattr(self.agent, "_children", None) or {}
        handle = children.get(cid)
        if handle is None:
            return {"ok": False, "error": "Görev bulunamadı."}
        metin = str(handle.sonuc or "").strip()
        if not metin and handle.state == "kosuyor":
            # Koşarken boş rapor yerine anlık durum — Viewer / Raporu aç.
            parcalar: list[str] = ["Görev hâlâ çalışıyor."]
            if handle.wait:
                w = handle.wait
                satir = "Model bekleniyor"
                if w.get("deneme") and w.get("toplam"):
                    satir += f" ({w['deneme']}/{w['toplam']})"
                if w.get("saniye"):
                    satir += f" · {w['saniye']}s"
                parcalar.append(satir)
            elif handle.son_arac:
                satir = f"Şu an: {handle.son_arac}"
                if handle.son_hedef:
                    satir += f" — {handle.son_hedef}"
                parcalar.append(satir)
            else:
                parcalar.append("Araç bekleniyor…")
            metin = "\n".join(parcalar)
        else:
            from .tools.shell import insan_is_raporu
            metin = insan_is_raporu(metin, title=handle.title)
        deliverable = getattr(handle, "deliverable", None)
        if not deliverable and getattr(handle, "schedule_id", ""):
            try:
                from .loop import _infer_deliverable
                book = scheduling.Schedule(self.agent.config.state_dir)
                task = book.get(handle.schedule_id)
                if task is not None:
                    deliverable = _infer_deliverable(task.prompt or "", metin)
                    if deliverable:
                        handle.deliverable = deliverable
            except Exception:
                pass
        return {
            "ok": True,
            "id": "c:" + handle.id,
            "title": handle.title,
            "state": handle.state,
            "metin": metin or "(çıktı yok)",
            "deliverable": deliverable,
        }

    def gorev_durdur(self, gid: str) -> dict[str, Any]:
        """Tek bir görevi durdurur. `gid` gorevler() satırındaki kimlik.

        Canlı yardımcıya cancel yollar; planlanmış 'koşuyor' hayaletini de
        temizler (çocuk yoksa / bitmişse UI'da takılı kalmasın).
        """
        from . import apps as katalog

        gid = str(gid or "").strip()
        if gid.startswith("c:"):
            cid = gid[2:]
            if not cid or not re.match(r"^[A-Za-z0-9_-]+$", cid):
                return {"ok": False, "error": "Geçersiz görev kimliği."}
            children = getattr(self.agent, "_children", None) or {}
            handle = children.get(cid)

            if handle is not None and handle.state == "kosuyor":
                def _stop(h=handle) -> None:
                    h.cancel.set()
                    agent = h.agent
                    if agent is not None:
                        try:
                            agent.cancel.set()
                        except Exception:
                            pass
                self.loop.call_soon_threadsafe(_stop)

            # Hayalet / canlı: planlanmış satır 'koşuyor'da kalmasın.
            cleared = self._clear_schedule_running(cid, handle)
            try:
                self.hub.emit({"type": "jobs_refresh"})
            except Exception:
                pass
            if handle is None:
                return {"ok": True, "id": gid, "cleared": True,
                        "note": "Kayıt temizlendi (canlı yardımcı yoktu)."}
            if handle.state != "kosuyor":
                return {"ok": True, "id": gid, "cleared": cleared,
                        "note": "Görev zaten bitmişti; durum güncellendi."}
            return {"ok": True, "id": gid, "cleared": cleared}

        if gid.startswith("p:"):
            try:
                pid = int(gid[2:])
            except ValueError:
                return {"ok": False, "error": "Geçersiz süreç kimliği."}
            return katalog.stop(pid)
        return {"ok": False, "error": "Geçersiz görev kimliği."}

    def _clear_schedule_running(
        self, child_id: str, handle: Any = None,
    ) -> bool:
        """last_status=koşuyor + last_child_id eşleşen görevleri 'kesildi' yap."""
        agent = self.agent
        if agent is None:
            return False
        book = getattr(agent, "schedule", None)
        if book is None:
            return False
        cleared = False
        state_dir = getattr(getattr(agent, "config", None), "state_dir", None)
        for task in book.all():
            if task.last_child_id != child_id:
                continue
            if task.last_status != "koşuyor":
                continue
            try:
                book.note_run(task.id, "kesildi")
                cleared = True
            except Exception:
                continue
            if state_dir is None:
                continue
            try:
                from . import task_runs
                from .loop import _report_with_meter, _run_meter

                if handle is not None and not getattr(handle, "bitis_ts", 0):
                    try:
                        import time as _time
                        handle.bitis_ts = _time.time()
                    except Exception:
                        pass
                meter = (
                    _run_meter(handle, agent.config)
                    if handle is not None else {}
                )
                for run in task_runs.list_runs(state_dir, task.id, limit=8):
                    if run.status != "koşuyor":
                        continue
                    if run.child_id and run.child_id != child_id:
                        continue
                    body = "Kullanıcı durdurdu."
                    if handle is not None and getattr(handle, "sonuc", None):
                        body = str(handle.sonuc)[:500] or body
                    report = body
                    if handle is not None:
                        report = _report_with_meter(
                            handle, agent.config, body)
                    elif meter.get("line"):
                        report = body + "\n\n---\n" + meter["line"]
                    task_runs.finish_run(
                        state_dir, task.id, run.id,
                        status="hata",
                        report=report,
                        child_id=child_id,
                        model=meter.get("model") or (
                            getattr(handle, "model", "") if handle else ""),
                        usage=meter.get("usage"),
                        cost_usd=meter.get("cost_usd"),
                        tools=meter.get("tools"),
                        duration_s=meter.get("duration_s"),
                        last_tool=meter.get("last_tool"),
                    )
            except Exception:
                pass
        return cleared

    def gorev_devam(self, gid: str, message: str = "") -> dict[str, Any]:
        """Yetim / bitmiş yardımcıyı disk oturumundan sürdürür.

        `task_say` / `_child_say` yolunun HTTP sarmalayıcısı — ajan döngüsünde
        `create_task` gerekir.
        """
        gid = str(gid or "").strip()
        cid = gid[2:] if gid.startswith("c:") else gid
        if not cid or not re.match(r"^[A-Za-z0-9_-]+$", cid):
            return {"ok": False, "error": "Geçersiz görev kimliği."}

        agent = self.agent
        if agent is None:
            return {"ok": False, "error": "Ajan henüz hazır değil."}
        children = getattr(agent, "_children", None) or {}
        handle = children.get(cid)
        if handle is None:
            return {"ok": False, "error": "Görev bulunamadı."}
        if handle.kind == "iş":
            return {"ok": False, "error": "Arka plan süreci sürdürülemez."}
        if handle.state == "kosuyor":
            return {"ok": False, "error": "Bu görev zaten koşuyor."}
        if not handle.session_id:
            return {"ok": False, "error": "Oturum yok; sürdürülemiyor."}

        msg = (message or "").strip() or "Kaldığın yerden devam et."
        box: dict[str, Any] = {}
        done = threading.Event()

        def _start() -> None:
            try:
                ok, text = agent._child_say(cid, msg)
                box.update({"ok": bool(ok), "id": "c:" + cid,
                            "text": text or ""})
                if not ok:
                    box["error"] = text or "Sürdürülemedi."
            except Exception as exc:
                box.update({"ok": False,
                            "error": f"{type(exc).__name__}: {exc}"})
            finally:
                done.set()

        self.loop.call_soon_threadsafe(_start)
        if not done.wait(timeout=15):
            return {"ok": False, "error": "Sürdürme zaman aşımı."}
        return box if box else {"ok": False, "error": "Sürdürülemedi."}

    def gorev_iptal(self, gid: str) -> dict[str, Any]:
        """Yetim/bitmiş yardımcıyı defterden VE açılış taramasından düşürür.

        Kalıcılık: çocuğun kendi günlüğüne bir `subagent_end` kapanışı
        yazılır — `yetim_tara` kapanış gören günlüğü bir daha diriltmez.
        ("Devam et var ama iptal et yok" — canlı istek, 31.08.)
        """
        gid = str(gid or "").strip()
        cid = gid[2:] if gid.startswith("c:") else gid
        if not cid or not re.match(r"^[A-Za-z0-9_-]+$", cid):
            return {"ok": False, "error": "Geçersiz görev kimliği."}
        agent = self.agent
        if agent is None:
            return {"ok": False, "error": "Ajan henüz hazır değil."}
        children = getattr(agent, "_children", None) or {}
        handle = children.get(cid)
        if handle is None:
            return {"ok": False, "error": "Görev bulunamadı."}
        if handle.state == "kosuyor":
            return {"ok": False, "error": "Koşan görev iptal edilmez — önce durdur."}
        sid = str(getattr(handle, "session_id", "") or "")
        if sid and re.match(r"^[A-Za-z0-9_-]+$", sid):
            try:
                yol = Path(agent.config.sessions_dir) / f"{sid}.jsonl"
                satir = json.dumps({
                    "kind": "meta", "role": None, "content": "subagent_end",
                    "meta": {"session": sid, "title": handle.title,
                             "summary": "kullanıcı iptal etti"},
                }, ensure_ascii=False)
                with yol.open("a", encoding="utf-8") as fh:
                    fh.write(satir + "\n")
            except OSError:
                pass
        children.pop(cid, None)
        self.hub.emit({"type": "channels", "channels": _live_channels(agent)})
        return {"ok": True}

    def _fiyat_getir(self) -> None:
        """Seçili modelin fiyatını arka planda bir kez çeker.

        Ağ isteği turun yolunda DEĞİL: thread bitince `fiyat` olayı
        yayınlanıyor ve çip token sayısından dolara döner. Katalogda
        olmayan model için de bir kez bakılıp bırakılıyor — her turda
        yeniden ağa çıkmak olmaz. Model değişince bayrak sıfırlanır.
        """
        if self._fiyat_bakildi:
            return
        agent = self.agent
        if agent is None:
            return
        self._fiyat_bakildi = True
        model = agent.config.model
        state_dir = agent.config.state_dir

        def _kos() -> None:
            try:
                etiket = fiyatlama.etiket(model, state_dir, ag=True)
            except Exception:
                return
            if etiket is not None:
                self._fiyat = etiket
                self.hub.emit({"type": "fiyat", "fiyat": etiket})

        threading.Thread(target=_kos, daemon=True).start()

    # -- asyncio thread ------------------------------------------------

    def io(self, serit: Any = None) -> AgentIO:
        """Ajanın olay yüzeyi. `serit` verilirse akış olayları YALNIZ o
        şerit aktifken canlı yayına gider — arka şeridin metni/araçları
        aktif sohbete karışmaz (paralel oturumların görünmez direği).
        Onay istekleri kapılanmaz: arka şeridin izni de sorulmalı, yoksa
        tur sonsuza dek bekler.
        """
        def yay(ev: dict[str, Any]) -> None:
            if serit is None or serit.sid == self._aktif_sid:
                # Olay OTURUM KİMLİĞİYLE damgalanıyor: kapı (aktif şerit
                # karşılaştırması) anlıktır ve geçiş sırasında yarışabilir —
                # kuyrukta bekleyen ya da tam geçiş anında sızan bir parça,
                # kimliksizken yeni açılan sohbetin ekranına akıyordu
                # (canlı yara, 01.09: "bir önceki sohbetle karıştığı bile
                # oluyor"). Arayüz artık kimliği tutmayan olayı ÇİZMİYOR.
                sid = serit.sid if serit is not None else self._aktif_sid or ""
                if sid:
                    ev.setdefault("sid", sid)
                self.hub.emit(ev)

        return AgentIO(
            on_text=lambda chunk: yay({"type": "assistant_delta", "text": chunk}),
            on_thinking=lambda chunk: yay({"type": "thinking_delta", "text": chunk}),
            on_notice=lambda text: yay({"type": "notice", "text": text}),
            # Model kesintisi: yapısal bekleme olayı. Arayüz bunu çalışma
            # şeridinde TEK canlı satır olarak işler — sohbete hata duvarı
            # basılmaz (bkz. app.js "bekleme").
            on_wait=lambda payload: yay({"type": "bekleme", **payload}),
            # Maliyet çipi aktif sohbeti gösterir: arka şeridin harcaması
            # çipe karışmaz (kendi oturum günlüğünde zaten duruyor).
            on_usage=(self._usage_yay if serit is None else
                      (lambda rapor: self._usage_yay(rapor)
                       if serit.sid == self._aktif_sid else None)),
            # Oturum başlığı: kenar listesi sayfa yenilemeden güncellensin.
            # Arka şeritte de yayınlanır — başlık sohbet kimliğidir, aktif
            # ekrana bağlı değildir.
            on_session_title=lambda sid, ad: self.hub.emit(
                {"type": "session_title", "id": sid, "title": ad}),
            # Bütçe freni: döngü her model çağrısından önce soruyor. Fiyat
            # ve sayaçlar burada olduğu için karar da burada.
            butce_freni=self._butce_freni,
            # Orkestra kanalları: alt ajanlar canlı görünsün (şef modu).
            on_child_start=lambda title, model, cid, bg=False: yay(
                {"type": "child_start", "title": title, "model": model, "id": cid,
                 "bg": bool(bg)}),
            on_child_tool=lambda title, tool, phase, hedef="": yay(
                {"type": "child_tool", "title": title, "tool": tool,
                 "phase": phase, "hedef": hedef or ""}),
            # `bg`: bu biten kanal arka planda mı koşuyordu. Görevler paneli
            # sohbete "bitti" bildirimini YALNIZ arka plan işleri için
            # düşürüyor — senkron yardımcının sonucu zaten cevabın içinde.
            on_child_end=self._child_end,
            on_child_wait=lambda payload: yay(
                {"type": "child_wait", **(payload or {})}),
            approve=self._approve,
        )

    def _child_end(
        self,
        title: str,
        ok: bool,
        turns: int,
        tools: int,
        cid: str = "",
        ozet: str = "",
    ) -> None:
        """Alt kanal bitti: Orkestra + (arka plansa) Windows tepsi balonu."""
        bg = self._cocuk_arka_plan(cid)
        deliverable = None
        children = getattr(self.agent, "_children", None) or {}
        handle = children.get(cid) if cid else None
        if handle is not None:
            deliverable = getattr(handle, "deliverable", None)
        usage = dict(getattr(handle, "usage", None) or {}) if handle else {}
        self.hub.emit({
            "type": "child_end", "title": title, "ok": ok, "turns": turns,
            "tools": tools, "id": cid, "ozet": ozet, "bg": bg,
            "deliverable": deliverable,
            "model": getattr(handle, "model", "") if handle else "",
            "usage": usage or None,
        })
        # Pencere kapalı olsa da kullanıcı haberdar olsun — yalnız arka
        # plan / zamanlanmış / otomasyon işleri (senkron yardımcı zaten
        # sohbette).
        if not bg:
            return
        t = self.tray
        if t is None:
            return
        try:
            t.note(tray_module.gorev_bildirim_metni(title, ok=bool(ok)))
        except Exception:
            pass

    async def _approve(
        self,
        spec: ToolSpec,
        args: dict[str, Any],
        channel: dict[str, Any] | None = None,
    ) -> bool:
        """İzin isteğini arayüze gönderir ve cevabı bekler.

        Pencere cevap vermeden kapanırsa bu future asla çözülmez; kapanış
        yolunda bekleyenler iptal ediliyor (bkz. cancel_pending).
        """
        request_id = uuid4().hex[:12]
        future: asyncio.Future[bool] = self.loop.create_future()
        self._pending[request_id] = Pending(future=future, spec=spec, args=dict(args))

        payload = {
            "type": "approval_request",
            "id": request_id,
            "tool": spec.name,
            "args": args,
            "mutates": spec.mutates,
        }
        # İsteyen bir yardımcıysa kimliği/başlığı da gidiyor: kullanıcı
        # diyalogda "[yardımcı: başlık]" görsün, kime izin verdiğini bilsin.
        if channel:
            payload["channel"] = channel
        self.hub.emit(payload)
        try:
            granted = await future
        except asyncio.CancelledError:
            return False
        finally:
            self._pending.pop(request_id, None)
            self.hub.emit({"type": "approval_done", "id": request_id})
        return granted

    def cancel_pending(self) -> None:
        for pending in tuple(self._pending.values()):
            if not pending.future.done():
                pending.future.cancel()
        self._pending.clear()

    async def pump(self) -> None:
        """İlk şeridin pompası (açılışta kurulur; yeni şeritler kendi
        pompalarını `_serit_kur` içinde alır)."""
        while True:
            serit = self._serit()
            if serit is None:
                # Ajan henüz kurulmadı: açılış kuyruğundan bekle.
                item = await self._ilk_kuyruk.get()
                if self.agent is None:
                    continue
                serit = self._serit()
                if serit is None:
                    continue
                await self._pompa_isle(serit, item)
                continue
            await self._pompa(serit)
            return

    async def _pompa(self, serit: Serit) -> None:
        """Bir şeridin pompası: kendi kuyruğunu kendi ajanına akıtır.

        Şerit başına bir pompa = şerit başına serilik; şeritler ARASI ise
        tam paralellik. Kullanıcı yeni sohbete geçtiğinde eski şerit kendi
        turunu burada sürdürür.
        """
        while True:
            item = await serit.queue.get()
            if serit.agent is None:
                continue
            await self._pompa_isle(serit, item)

    async def _pompa_isle(self, serit: Serit, item: Any) -> None:
        if item is _CHILD_DONE:
            await self._surdur(serit)
        elif item is _PARK_RESUME:
            await self._park_surdur(serit)
        else:
            text, image = item
            await self._isle(text, image, serit=serit)

    async def _park_surdur(self, serit: Serit | None = None) -> None:
        """Park edilmiş (yarım kalmış) koşuyu kaldığı yerden sürdürür.

        Açılışta park kaydı bulunduğunda kuyruğa düşen işaretin karşılığı.
        `resume_after_interrupt` karşılıksız tool_use'ları kapatıp döngüyü
        yeniden sürer; model hâlâ ulaşılamıyorsa aynı koşu içinde yeniden
        deneme/park zinciri zaten devrede.
        """
        serit = serit or self._serit()
        agent = serit.agent if serit else None
        if agent is None:
            return
        self._serit_durum(serit, True)
        try:
            await agent.resume_after_interrupt()
        except Exception as exc:  # sürdürme uygulamayı düşürmemeli
            self._serit_yayin(serit, {"type": "notice",
                                      "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._serit_durum(serit, False)
            if self._wanted_model is not None and serit.sid == self._aktif_sid:
                self._swap_model()
            self._serit_yayin(serit, {"type": "turn_end"})

    async def _surdur(self, serit: Serit | None = None) -> None:
        """Bir yardımcı bitti ve ajan boşta: sonucu değerlendiren tur.

        Bildirilecek bir şey kalmadıysa (sonuç koşan turun başında zaten
        verildiyse) model hiç çağrılmaz — sessizce geçilir.
        """
        serit = serit or self._serit()
        agent = serit.agent if serit else None
        if agent is None or not agent.has_unreported_children():
            return
        self._serit_durum(serit, True)
        try:
            await agent.resume_for_children()
        except Exception as exc:  # sürdürme turu uygulamayı düşürmemeli
            self._serit_yayin(serit, {"type": "notice",
                                      "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._serit_durum(serit, False)
            if self._wanted_model is not None and serit.sid == self._aktif_sid:
                self._swap_model()
            self._serit_yayin(serit, {"type": "turn_end"})

    def _serit_yayin(self, serit: Serit, ev: dict[str, Any]) -> None:
        """Şerit olayını YALNIZ aktifken canlı akışa verir.

        Arka şeridin metni kendi oturum günlüğüne zaten yazılıyor; canlı
        yayına da sızsaydı iki sohbet ekranda birbirine karışırdı. Kullanıcı
        şeride dönünce döküm günlükten yüklenir — kayıp yok.
        """
        if serit.sid == self._aktif_sid:
            ev.setdefault("sid", serit.sid)   # bkz. io().yay: geçiş yarışı
            self.hub.emit(ev)

    async def _isle(self, text: str, image: str = "", *,
                    serit: Serit | None = None) -> None:
        """Tek mesajı kendi şeridinde işler (varsayılan: aktif şerit).

        pump'tan ayrı durması bilinçli: testler bir turu kuyruk ve sonsuz
        döngüye bulaşmadan koşturabiliyor.
        """
        serit = serit or self._serit()
        if serit is None or serit.agent is None:
            return
        self._serit_durum(serit, True)
        agent = serit.agent
        # Yeni kullanıcı mesajı = yeni tur: çipin "bu tur" toplamı sıfırdan
        # başlar. Oturum toplamına dokunulmuyor; sürdürme turları
        # (_surdur, park) aynı işin devamı sayılıp sıfırlamıyor. Sayaç
        # yalnız aktif şeritte sıfırlanıyor — çip aktif sohbeti gösteriyor.
        if serit.sid == self._aktif_sid:
            self._tur_kullanim = {"girdi": 0, "cikti": 0, "cagri": 0}
        # Yeni mesaj = yeni deneme: sınır hâlâ aşılmışsa fren bir kez daha
        # konuşsun. Yoksa kullanıcı yazıyor ve hiçbir şey olmuyor.
        self._butce_bildirildi = False
        try:
            # İlk kurulum: hiçbir sağlayıcı kullanılabilir değilken model
            # HİÇ çağrılmıyor — cevapsız kalan ya da anlaşılmaz bir API
            # hatasıyla biten bir mesaj yerine, sohbete yol gösteren bir
            # asistan mesajı düşüyor. Kullanıcı tekrar yazarsa yeniden
            # hatırlatılıyor; ama bir mesaj bir kez cevaplanıyor.
            if settings.yapilandirilmamis(agent.config.model):
                agent.session.add_user_text(text)
                agent.session.add_assistant(
                    [{"type": "text", "text": settings.KURULUM_YONLENDIRME}]
                )
                self._serit_yayin(serit,
                                  {"type": "setup_hint",
                                   "text": settings.KURULUM_YONLENDIRME})
                return
            # Başlık koşunun SONUNU beklemez: solda "ilk sözün kırıntısı"
            # uzun bir koşu boyunca asılı kalıyordu. İlk kullanıcı sözü
            # yeterli sinyal — ama `run` mesajı henüz günlüğe yazmamış
            # olabilir; metni doğrudan geçiriyoruz (yarış, canlı). Küçük
            # çağrı ana akışla paralel; her hatası yutulur. Koşu sonundaki
            # çağrı yedek (ad hâlâ yoksa, cevapla daha isabetli başlık).
            basla = getattr(agent, "_oturum_basligi", None)
            if basla is not None:
                gorev = asyncio.ensure_future(basla(text))
                gorev.add_done_callback(lambda t: t.exception())  # sessiz
            await agent.run(text, image)
        except Exception as exc:  # ajan bir istekte patlarsa uygulama ölmemeli
            self._serit_yayin(serit, {"type": "notice",
                                      "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._serit_durum(serit, False)
            # Karşılık verildi: sohbet açık. Bu süre boyunca söylenen
            # her şey ona söylenmiş sayılıyor, adını tekrarlamak
            # gerekmiyor — karşındaki insana da her cümlede adıyla
            # başlamıyorsun.
            if self.ear is not None and serit.sid == self._aktif_sid:
                self.ear.engage()
            # Tur sırasında model değiştirilmişse şimdi geçiliyor.
            if self._wanted_model is not None and serit.sid == self._aktif_sid:
                self._swap_model()
            self._serit_yayin(serit, {"type": "turn_end"})
            # Arka şerit bitti: kullanıcı başka sohbetteyken haberdar olsun.
            if serit.sid != self._aktif_sid:
                baslik = ""
                try:
                    meta = (serit.agent.mind.session_meta() or {}).get(serit.sid) or {}
                    baslik = str(meta.get("ad") or "")
                except Exception:
                    pass
                self.hub.emit({"type": "notice",
                               "text": (f"Arka plandaki sohbet bitti: {baslik}"
                                        if baslik else
                                        "Arka plandaki sohbet cevabını bitirdi — "
                                        "kenar çubuğundan dönebilirsin.")})


@dataclass(slots=True)
class Runtime:
    bridge: Bridge
    server: MindServer
    agent: Agent
    session: Session
    client: Any
    url: str
    schedule: Any = None
    ticker: Any = None
    greeter: Any = None
    eyes: Any = None
    lens: Any = None
    ear: Any = None


def _allow_media() -> None:
    """WebView2'ye medya izin penceresini atlamasını söyler.

    `--use-fake-ui-for-media-stream` Chromium'un "izin penceresini gösterme,
    kabul et" bayrağı. Kendi penceremizde bu doğru davranış: kullanıcı zaten
    ayarlardan mikrofonu/kamerayı açmış durumda ve WebView2'nin sorabileceği
    bir yüzeyi yok.

    Ortamda zaten bir değer varsa üstüne ekleniyor: kullanıcının verdiği
    bayrakları silmek istemiyoruz.
    """
    name = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"
    flag = "--use-fake-ui-for-media-stream"
    current = os.environ.get(name, "")
    if flag not in current:
        os.environ[name] = f"{current} {flag}".strip()


def _hearing_wanted(config: Config) -> bool:
    """Kulak açılsın mı: dinleme açık, aygıt ve tanıma var, uyandırma veya serbest."""
    from . import listen as recogniser

    return bool(
        config.listen.enabled
        and hearing.available()
        and recogniser.available()
        and (config.listen.wake.strip() or config.listen.open)
    )


def duyulari_kapat(config: Config) -> Config:
    """Açılışta kamera, mikrofon ve sesli yanıt kapalı.

    HUD'dan açılınca ayara yazılır; bir sonraki açılış yine kapalı gelir.
    """
    return replace(
        config,
        voice=replace(config.voice, enabled=False),
        listen=replace(config.listen, enabled=False, open=False),
        camera=replace(config.camera, enabled=False),
    )


def _ear_alive(ear: Any) -> bool:
    """Kulak thread'i hâlâ dönüyor mu? stop() sonrası yeniden kurulur."""
    if ear is None:
        return False
    stop = getattr(ear, "_stop", None)
    if stop is not None and stop.is_set():
        return False
    thread = getattr(ear, "_thread", None)
    return thread is not None and thread.is_alive()


def _open_ear(config: Config, bridge: "Bridge", hub: Hub) -> Any:
    """Sürekli dinleyen kulağı açar.

    Uyandırma sözü duyulduğunda pencere geri geliyor ve söz sonrası
    doğrudan ajana gidiyor. Söz geçmeyen hiçbir şey kaydedilmiyor,
    gösterilmiyor, modele gitmiyor.
    """
    from . import listen as recogniser

    # Alan sözlüğü kendiliğinden doluyor: kullanıcının cihaz ve yetenek
    # adları tanıyıcının bias istemine giriyor. "Modbus cihazını oku"
    # cümlesindeki "Modbus"un doğru yazılması buna bağlı — tanıyıcı
    # duymadığı özel adı en yakın gerçek kelimeye çeviriyor.
    from dataclasses import replace as _replace

    words = [config.listen.vocab, "Modbus", "SCADA", "PLC", "register"]
    try:
        from . import devices as declared
        from . import skills as authored

        found_devices, _ = declared.load(config.open_sandbox().root)
        words += [d.name for d in found_devices]
        learned, _ = authored.discover(config.open_sandbox().root)
        words += [item.name for item in learned]
    except Exception:
        pass
    spoken = _replace(config.listen, vocab=", ".join(w for w in words if w))

    listener = recogniser.Listener(spoken)

    # Model burada **yüklenmiyor**. Yüklemek indirme demek olabiliyor —
    # `medium` 1,5 GB — ve açılışı otuz saniyeden uzun bekletince pencere
    # hiç açılmıyordu. Yükleme kulağın kendi thread'inde, ilk konuşmada
    # ya da arka plandaki ısıtmada oluyor.
    #
    # Gözcü nesnesi de burada kuruluyor ama o da yüklenmiyor; gerekip
    # gerekmediğine, aygıt belli olduktan sonra `Ear` karar veriyor.
    scout = recogniser.Listener(_replace(spoken, size=SCOUT_SIZE))

    def heard(said: hearing.Heard) -> None:
        hub.emit({"type": "notice", "text": f"Duydum: {said.text}"})
        bridge.wake()

        # "dornick ile kes" / enerji barge: dornick konuşurken araya girildi —
        # önce konuşmayı sustur (arayüz TTS'i durduruyor), sonra komut normal
        # akışa (kuyruk) giriyor. Enerji eşiği zaten `on_hush` ile kesmiş
        # olabilir; ikinci hush zararsız.
        if getattr(said, "barge", False):
            hub.emit({"type": "hush"})

        # Süren tur İPTAL EDİLMİYOR — sıraya giriyor (metinle aynı davranış).
        # Eski hâl duyulan her sözde turu kesiyordu; kullanıcı "bir işlem
        # yaparken bir şey daha söyleyince eskiyi iptal ediyor" dedi. Doğrusu
        # paralel düşünüp sıraya almak: yeni söz kuyruğa girer, tur bitince
        # işlenir. İptali kullanıcı açıkça ister (durdur düğmesi / sesli
        # "dur"); varsayılan artık iptal değil.
        text = (said.command or "").strip()
        if _is_stop(text):
            # Açık iptal: "dur", "yeter", "kes" gibi bir söz süreni durdurur.
            if bridge.busy:
                bridge.interrupt()
            return

        if _is_close(text):
            # Kapanış: pencere kapanır ve susulur. Belirsizlikte susmak
            # ucuz, yanlış cevap pahalı — kullanıcı isterse "dornick" der.
            if ear is not None:
                ear.disengage()
            hub.emit({"type": "notice",
                      "text": "Sohbet kapandı — adıyla yeniden açılır."})
            return

        if _is_ack(text):
            # Teşekkür / "tamamdır" / "şimdi bakayım": modele gitmez,
            # "rica ederim" döngüsü açılmaz. "bakıyorum" klibi de yok.
            return

        # Sözden geriye bir şey kalmadıysa yalnızca adı çağrılmış demektir.
        # Orada susmak duymamakla aynı şey: ekranda "Duydum" yazıyor ve
        # hiçbir şey olmuyordu.
        if text:
            # Onay klibi: model ilk kelimesini üretmeden arayüz kısa bir ses
            # çalıyor ("bakıyorum"). Ad çağrısında (CALLED_ASK) çalınmıyor —
            # "efendim"den önce "bakıyorum" demek tuhaf olurdu.
            hub.emit({"type": "ack"})
        bridge.submit(text or CALLED_ASK)

    ear = hearing.Ear(
        listener,
        heard,
        scout=scout,
        wake=config.listen.wake,
        # Serbest dinleme açıksa uyandırma sözü hiç aranmıyor.
        open=config.listen.open,
        # Seviye arayüze gidiyor: duyup duymadığı görünmeli.
        level=lambda loud: hub.emit({"type": "level", "value": round(loud, 4)}),
    )
    ear.on_hush = lambda: hub.emit({"type": "hush"})
    if not ear.start():
        return None
    def _hearing_snooze(off: bool) -> None:
        hub.emit({"type": "hearing", "snoozed": bool(off)})
        prefs.patch(config.state_dir, hearing_snoozed=bool(off))
    ear.on_snooze = _hearing_snooze
    how = "serbest dinleme" if config.listen.open else f"'{config.listen.wake}' ile uyanır"
    print(f"[dornick] kulak açık — {how}", flush=True)
    return ear


def _yarim_is(sessions_dir: Any) -> str | None:
    """Çökme artığı var mı: son oturumda cevapsız tool_use kalmış mı?

    Park kaydı olmadan yarım kalmış bir koşunun izi. Yalnızca haber vermek
    için kullanılıyor (otomatik sürdürme park kaydına bağlı); o yüzden en
    iyi çaba — okunamayan/bozuk günlükte sessizce None.
    """
    import json as _json
    from pathlib import Path as _Path

    try:
        files = sorted(_Path(sessions_dir).glob("*.jsonl"))
        if not files:
            return None
        requested: list[str] = []
        answered: set[str] = set()
        for line in files[-1].read_text(encoding="utf-8").splitlines():
            try:
                ev = _json.loads(line)
            except ValueError:
                continue
            meta = ev.get("meta") or {}
            # Yardımcı (alt ajan) oturumu: ana listeye konu değil.
            if ev.get("content") == "subagent_start" and meta.get("parent"):
                return None
            if ev.get("kind") != "message":
                continue
            content = ev.get("content")
            if not isinstance(content, list):
                continue
            if ev.get("role") == "assistant":
                requested = [str(b.get("id")) for b in content
                             if isinstance(b, dict) and b.get("type") == "tool_use"]
            elif ev.get("role") == "user":
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        answered.add(str(b.get("tool_use_id")))
        if any(r not in answered for r in requested):
            return files[-1].stem
        return None
    except Exception:
        return None


def _prepare_model(config: Config) -> None:
    """Modeli ayarlardaki pencereyle yüklü hale getirir (yalnızca LM Studio).

    LM Studio kendiliğinden yüklerken 4096 token kullanıyor — model 262144
    desteklese bile. Sistem promptu artı araç şemaları bunu zaten aşıyor ve
    sunucu istemin başını sessizce atıyor: model kim olduğunu unutuyor.

    Aynı yerde fazla kopyalar da kaldırılıyor: meşgul bir modele ikinci
    istek gelince LM Studio ikinci bir kopya yüklüyor ve bellek katlanıyor.

    `local_optimize` açıksa (ve adres localhost ise): diğer modeller boşaltılır,
    VRAM/model boyutuna göre bağlam düşürülür. Kapalıysa dokunulmaz.

    Sessizce başarısız oluyor: LM Studio yoksa uçlar da yok ve bu normal.
    """
    if config.model.provider != "openai":
        return

    url = config.model.base_url
    name = config.model.name
    context = config.model.context_window

    optimize = bool(config.model.local_optimize) and lmstudio.is_local_url(url)
    if optimize:
        for gone in lmstudio.unload_others(url, name):
            print(f"[dornick] yerel opt: başka model boşaltıldı: {gone}", flush=True)
        # Boşaltmadan sonra VRAM ölç — önceki modelin yeri geri gelsin.
        model = lmstudio.find(url, name)
        free_mb = None
        try:
            from . import gpu as gpu_module
            free_mb = gpu_module.primary_free_mb()
        except Exception:
            free_mb = None
        if model is not None:
            # Model zaten yüklüyse VRAM'de ağırlık yer kaplıyor — size'ı
            # tekrar düşmek çifte sayım olur, bağlamı gereksiz keser.
            size_for_fit = 0 if model.instances else model.size_bytes
            fitted = lmstudio.suggest_context(
                context,
                max_context=model.max_context,
                size_bytes=size_for_fit,
                params_b=model.params_b,
                free_vram_mb=free_mb,
            )
            if fitted != context:
                print(
                    f"[dornick] yerel opt: bağlam {context} → {fitted}"
                    + (f" (VRAM boş {free_mb} MB)" if free_mb is not None else ""),
                    flush=True,
                )
                context = fitted

    for gone in lmstudio.drop_duplicates(url, name):
        print(f"[dornick] fazla kopya kaldırıldı: {gone}", flush=True)

    # keep_loaded ayarlanmışsa onu, yoksa cömert bir varsayılan (30 dk) TTL
    # veriyoruz: LM Studio kendi varsayılanıyla modeli çabuk boşaltıp sonraki
    # isteği "Model unloaded" ile düşürüyordu. Böylece konuşma sürerken model
    # yüklü kalıyor.
    ttl = config.model.keep_loaded or 1800
    result = lmstudio.ensure_loaded(url, name, context, ttl=ttl)
    if result.get("state") == "loaded":
        print(f"[dornick] model {result['context']} token pencereyle yüklendi "
              f"({result.get('seconds', 0):.1f} sn)")
    elif result.get("state") == "capped":
        print(f"[dornick] pencere modelin sınırına çekildi: {result['context']}", flush=True)

    # Gerçek yüklü pencereyi AYARA yansıt. LM Studio istenen pencereyi modelin
    # sınırı ya da kendi yapılandırması yüzünden küçültmüş olabilir (ör. 4096).
    # Ayar gerçeğin üstünde kalırsa sıkıştırma taşmadan tetiklenmiyor, istem
    # modelin sınırını aşıyor ve LM Studio "model unloaded / context" hatası
    # veriyordu — kullanıcı "context dolunca duruyor" diyordu. Gerçeğe çekince
    # konuşma dolmadan özetlenip sürüyor, yeni bir konuşmaya gerek kalmıyor.
    actual = result.get("context")
    if isinstance(actual, int) and actual > 0 and actual != config.model.context_window:
        from dataclasses import replace as _replace
        config.model = _replace(config.model, context_window=actual)
        print(f"[dornick] bağlam penceresi gerçeğe göre ayarlandı: {actual}", flush=True)


async def _boot(config: Config, port: int, resume: bool) -> Runtime:
    """Uygulamayı ayağa kaldırır.

    Sıra bilinçli: sunucu **önce** açılıyor, ağır işler sonra. Böylece
    pencere hemen görünüyor ve model yüklenirken boş bir ekrana değil,
    uyanma sırasına bakılıyor. Model hazır olmadan giriş satırı kapalı
    kalıyor — hazır olmayan bir ajana yazmak cevapsız kalmak demek.
    """
    config.ensure_dirs()
    # Kamera, mikrofon ve sesli yanıt kapalı açılır. Kullanıcı HUD'dan
    # açar; bir sonraki oturum yine kapalı gelir — LED/kulak/hoparlör
    # kendiliğinden uyanmaz. Diskte "açık" kalırsa başka bir ayar kaydı
    # oturum ortasında duyuyu geri yakardı.
    config = duyulari_kapat(config)
    if (config.state_dir / settings.CONFIG_FILE).exists():
        try:
            config = settings.apply(config, {
                "voice": {"enabled": False},
                "listen": {"enabled": False, "open": False},
                "camera": {"enabled": False},
            })
        except Exception:
            pass

    # Ayar sayfasindan girilen anahtarlar ortama yukleniyor: backend'ler
    # zaten oradan okuyor, ikinci bir yol acmaya gerek yok.
    settings.export_keys(config.state_dir)

    # Park kaydı: önceki koşuda model ulaşılamaz olmuş ve iş bekletilirken
    # uygulama kapanmış olabilir. Kayıt varsa O oturum açılır ve aşağıda
    # (pump kurulunca) koşu kaldığı yerden otomatik sürdürülür.
    park_session = None
    if parked := read_park(config.state_dir):
        p = config.sessions_dir / f"{parked.get('session', '')}.jsonl"
        if p.is_file():
            park_session = Session.resume(p)
        else:
            clear_park(config.state_dir)

    # Park kaydı yok ama son oturumda cevapsız tool_use kalmışsa (çökme
    # artığı) kullanıcıya yalnızca haber verilir — belirsiz durumda sorma
    # tarafında kalınıyor, kendiliğinden sürdürülmüyor.
    yarim = None if (park_session or resume) else _yarim_is(config.sessions_dir)

    # Yetim yardımcılar: geçen oturumda arka planda koşarken uygulamayla
    # birlikte ölen alt ajanlar (subagent_start var, subagent_end yok).
    # Park/yarım işten ayrı bir yara — orada ana koşu, burada çocuklar
    # yarım. Bir kez bulunur ve çocuk günlüğüne hemen işaret düşülür ki
    # ikinci açılış aynı yetimi yeniden bildirmesin; haber aşağıda (ajan
    # kurulunca) hem kullanıcıya hem modele veriliyor.
    yetimler = yetim_tara(config.sessions_dir)
    if yetimler:
        yetim_isaretle(config.sessions_dir, yetimler)

    session = park_session or (
        Session.latest(config.sessions_dir) if resume else None
    ) or Session.create(config.sessions_dir)
    hub = Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    mind = open_mind(config.mind_dir, config.sessions_dir, session.id)
    if not park_session and not resume:
        inherit_last_model(mind, session.id, config.sessions_dir)
    pin = str(((mind.session_meta() or {}).get(session.id) or {}).get("model") or "").strip()
    if pin and pin != config.model.name:
        from dataclasses import replace as _degistir
        config = _degistir(config, model=_degistir(config.model, name=pin))
    book = scheduling.Schedule(config.state_dir)

    # Hub paylaşılıyor: köprünün yayınladıkları (metin akışı, onay isteği) ile
    # günlükten gelenler (kullanıcı mesajı, araç olayları) aynı akışa düşmeli.
    server = MindServer(
        mind,
        session.log,
        port=port,
        controller=bridge,
        hub=hub,
        config=config,
        schedule=book,
    )
    # Köprü oturum değiştirmek için sunucuya (olay akışını yeniden bağlamak)
    # ihtiyaç duyuyor; referans burada veriliyor.
    bridge.server = server
    url = server.start()

    # -- ağır kısım: pencere zaten açık, adımlar görünüyor ---------------

    bridge.waking("zihin açılıyor")
    # Dar pencereli modelde alt ajan aracı hiç kaydedilmiyor: şeması
    # tek başına 130 token ve 4096'lık bir pencerede o yer konuşmanın.
    registry = build_registry(mind, subagents=not prompt.is_lean(config))

    bridge.waking("yetenekler yükleniyor")
    # Ajanın kendi yazdığı yetenekler: her açılışta atölyeden yükleniyor.
    # Bozuk bir dosya diğerlerini engellemiyor — tek bir yazım hatası ajanı
    # tüm yeteneklerinden etmemeli.
    # Paketle gelen standart yetenekler ilk açılışta atölyeye kopyalanıyor;
    # sonrası kullanıcının: düzenler, siler, yeniden eklemeyiz.
    skills.seed(config.open_sandbox().root, config.state_dir)
    # Açılış: insan yok — yalnız onaylı manifestteki yetenekler yüklenir.
    # Atölyeye düşürülmüş rastgele bir .py kendiliğinden çalışmaz.
    learned, broken = skills.discover(config.open_sandbox().root, config.state_dir)
    added, _updated = skills.register(registry, learned)
    if added:
        print(f"[dornick] yetenekler yüklendi: {', '.join(added)}", flush=True)
    for problem in broken:
        print(f"[dornick] yetenek yüklenemedi: {problem.splitlines()[0]}", flush=True)

    # MCP bağlayıcıları arka planda bağlanıyor: `npx` ilk seferde paket
    # indirebiliyor ve açılış bunu beklememeli. Bağlanınca araçlar canlı
    # deftere düşüyor — bir sonraki tur onları görüyor.
    pool = linking.Pool()
    server._httpd.connectors = pool  # type: ignore[attr-defined]

    def _connect_mcp() -> None:
        found, problems = linking.load(config.state_dir)
        for problem in problems:
            print(f"[dornick] bağlayıcı: {problem}", flush=True)
        if not found:
            return
        pool.connect(found, config.state_dir)
        fresh, _gone = linking.register(registry, pool)
        if fresh:
            print(f"[dornick] MCP araçları: {', '.join(fresh)}", flush=True)
        for state in pool.status():
            if not state["ok"] and state["error"]:
                hub.emit({"type": "notice",
                          "text": f"Bağlayıcı {state['name']}: {state['error']}"})

    threading.Thread(target=_connect_mcp, daemon=True, name="dornick-mcp").start()

    bridge.waking(f"model yükleniyor · {config.model.name}")
    # Yükleme saniyeler sürüyor ve bloklayan bir çağrı; döngüyü kilitlememesi
    # için ayrı bir thread'e alınıyor.
    await asyncio.to_thread(_prepare_model, config)

    # Model yapılandırılmamışsa (ilk kurulum: anahtar yok, yerel sunucu yok)
    # pencere yine de açılıyor: ayar sayfası ajandan bağımsız çalışıyor ve
    # düzeltmenin yeri tam olarak orası. Eskiden burası patlayınca kullanıcı
    # pencereyi hiç göremiyordu — kurulum sihirbazından çıkan birine "görünmez
    # bir hata" bırakılamaz.
    try:
        client = build_client(config.model)
    except Exception as exc:
        client = None
        agent = None
        print(f"[dornick] model istemcisi kurulamadı: {exc}", flush=True)
    else:
        agent = Agent(
            config=config,
            session=session,
            registry=registry,
            client=client,
            io=bridge.io(),
            permissions=PermissionEngine.from_config(config.permissions),
            policy=ContextPolicy(config.context),
            schedule=book,
            mind=mind,
        )
        # Arka plan yardımcısı bitince köprü haber alsın: ajan boştaysa
        # sonucu değerlendiren bir sürdürme turu açılır. (Şeride özel
        # bağlama `bridge.agent = agent` atamasında kuruluyor; buradaki
        # geri-uyum satırı onun ÜSTÜNE yazmasın diye kaldırıldı.)
        # Model kesintisinde her yeniden denemeden önce bekleyen ayar/model
        # değişikliği uygulansın: bozuk adres/anahtar düzeltildiğinde parklı
        # koşu yeni istemciyle sürebilsin (normalde değişim tur sonunu
        # bekler; parklı tur hiç bitmez).
        agent.on_retry_wait = bridge._swap_model
    bridge.agent = agent

    # Sürekli dinleme Python tarafında: tarayıcıda duramıyor çünkü pencere
    # gizlendiğinde Chromium arka plan zamanlayıcılarını dakikaya kısıyor ve
    # dinleme ölüyor. Burada tepside dururken de çalışıyor. Ayar kaydı
    # aynı kapıyı kullanır (`sync_hearing`) — yoksa yalnız bas-konuş kalır.
    if _hearing_wanted(config):
        bridge.waking("kulak açılıyor")
    bridge.sync_hearing(config)

    # Tanıma modeli arka planda ısıtılıyor: ilk sesli isteğin indirmeyi
    # beklemesi bütün arayüzü kilitliyordu.
    server_module.warm_ear(server._httpd, config)

    # Beni tanı: kişisel ince ayar döngüsünün bekçisi. Zamanlama üründe —
    # schtasks yok; bekçi on beş dakikada bir bakar, sırası geldiyse
    # döngüyü düşük öncelikli başlatır. Özellik kapalıysa hiç kımıldamaz.
    tanima.gozcu_baslat(config.state_dir, hub)

    # Yerel kameranın sürekli açık tamponu. Kareler bellekte duruyor ve
    # kendiliğinden modele gitmiyor; `look` aracı istediğinde alınıyor.
    lens = None
    if config.camera.enabled and watching.available():
        bridge.waking("göz açılıyor")
        lens = watching.Lens()
        if lens.start():
            if agent is not None:
                agent.lens = lens
            # Arayüz de bilsin: sahnedeki kamera organı gerçekten açık mı
            # diye ayara değil buna bakıyor.
            server._httpd.lens = lens  # type: ignore[attr-defined]
            print("[dornick] kamera tamponu açık", flush=True)
            from . import sight
            sight.ensure_warmup()
            lens.on_snooze = lambda off: prefs.patch(
                config.state_dir, sight_snoozed=bool(off)
            )
        else:
            lens = None

    bridge.lens = lens
    if agent is not None:
        agent.camera_power = bridge.camera_power

    if agent is None:
        bridge.waking(
            "model yapılandırılmamış — ayarlardan bir model seç ve anahtarını "
            "gir, sonra uygulamayı yeniden başlat"
        )
    else:
        bridge.waking("hazır", ready=True)

    loop = asyncio.get_running_loop()
    loop.create_task(bridge.pump())

    # Yetim yardımcılar: tek toplu bildirim + defter kaydı. Defter kaydıyla
    # panel "yarım kaldı" satırını çizebiliyor (snapshot kanalları) ve
    # kullanıcı "sürdür" derse model `task_say` ile diskteki oturumu
    # diriltebiliyor — harness notunu adopt_orphans düşürüyor.
    if yetimler:
        if agent is not None:
            agent.adopt_orphans(yetimler)
        adlar = ", ".join(
            (y.get("title") or y.get("session") or "?") for y in yetimler)
        hub.emit({"type": "notice", "text": (
            f"Geçen oturumdan {len(yetimler)} yardımcı yarım kaldı: {adlar}. "
            "Uygulama kapanınca arka plan yardımcıları durur; istersen "
            "kaldıkları yerden sürdürebilirim.")})
        # Açılış sırasında yüklenmiş sayfa snapshot'ı ajan kurulmadan çekmiş
        # olabilir (kanallar o an boş); panel bu olayla gerçek listeye
        # tohumlanıyor — pencereyi yenilemeye gerek kalmıyor.
        hub.emit({"type": "channels", "channels": _live_channels(agent)})

    # Yarım kalmış uzun iş: park kaydı varsa otomatik sürdürülür; yalnızca
    # çökme artığı (kayıtsız yarım tur) varsa haber verilir, karar kullanıcının.
    if park_session is not None and agent is not None:
        hub.emit({"type": "notice",
                  "text": "Yarım kalmış uzun iş bulundu — kaldığı yerden sürdürülüyor."})
        loop.create_task(bridge.queue.put(_PARK_RESUME))
    elif yarim:
        hub.emit({"type": "notice",
                  "text": f"Yarım kalmış bir iş görünüyor (oturum {yarim}). "
                          "Geçmiş'ten açıp 'devam et' diyebilirsin."})

    # Zamanlayıcı ajanın döngüsünde koşuyor: tetiklenen görev sohbet
    # kuyruğuna değil arka plan yardımcıya düşüyor — rapor Orkestra'da.
    def fire(task: Any) -> None:
        hub.emit({"type": "notice", "text": f"Zamanlanmış görev: {task.title}"})
        result = bridge.run_scheduled(task)
        if not result.get("ok"):
            book.note_run(task.id, f"başlatılamadı: {result.get('error') or '?'}")
            hub.emit({"type": "notice",
                      "text": f"Görev başlatılamadı: {task.title}"})

    bridge._missed_fire = fire
    missed = book.overdue()
    if missed:
        bridge._missed_ids = [t.id for t in missed]
        hub.emit({
            "type": "missed_tasks",
            "tasks": scheduling.payload(missed),
        })

    ticker = loop.create_task(scheduling.run_forever(
        book, fire, paused=bridge.missed_pending))

    # Geliş: uzun bir sessizlikten sonra biri odaya girdiğinde ajan bir kez
    # bakıyor. Küçük bir çocuk gibi — kimse yokken kendini beklemeye alıyor,
    # bir şey kımıldayınca kim geldiğine bakıyor.
    async def greet() -> None:
        while True:
            await asyncio.sleep(2.0)
            cfg = getattr(bridge.agent, "config", None) if bridge.agent else None
            if cfg is None or not bool(getattr(cfg.camera, "enabled", False)):
                continue
            box = getattr(bridge.agent, "lens", None) if bridge.agent else None
            if box is not None and not bridge.busy and box.arrival():
                bridge.submit(GREET_ASK)

    greeter = loop.create_task(greet())

    # Kameralar arka planda izleniyor. Model her kareye bakmıyor: hareket
    # yerelde ölçülüyor ve yalnızca bir şey değiştiğinde soru soruluyor.
    # GPU varsa kare yerelde analiz edilir, sohbet modeline METİN gider;
    # görüntü makineden çıkmaz. GPU yoksa eski kesit kipi (kare + cloud_ok).
    def seen(sighting: watching.Sighting) -> None:
        bridge._on_camera_motion(sighting)

    eyes = watching.Watcher(
        watching.load(config.state_dir) if config.camera.enabled else [], seen)
    bridge.eyes = eyes
    # "Beni izleme" ağ kameralarını da kapsıyor; sesleniş hepsini geri
    # açıyor. Kulak, göz ve izleyici tek bir "duyular" bütünü.
    if bridge.agent is not None:
        bridge.agent.watcher = eyes
    if bridge.ear is not None:
        # "dornick" kulağı ve ağ kameralarını geri açar. Dahili kamera
        # HUD/sohbet anahtarıyla açılır — sesleniş LED'i yeniden yakmaz.
        # HUD kapalıyken unsnooze izleyiciyi başlatmaz; start() HUD'a bağlı.
        bridge.ear.companions = [s for s in (eyes,) if s is not None]
    if config.camera.enabled and eyes.start():
        print(f"[dornick] {len(watching.load(config.state_dir))} kamera izleniyor", flush=True)
    eyes.on_snooze = lambda off: prefs.patch(
        config.state_dir, sight_snoozed=bool(off)
    )

    held = prefs.load(config.state_dir)
    if held.get("hearing_snoozed") and bridge.ear is not None:
        bridge.ear.snooze(0)
    if held.get("sight_snoozed"):
        if lens is not None:
            lens.snooze(0)
        eyes.snooze(0)

    return Runtime(
        bridge=bridge,
        server=server,
        agent=agent,
        session=session,
        client=client,
        url=url,
        schedule=book,
        ticker=ticker,
        greeter=greeter,
        eyes=eyes,
        lens=lens,
        ear=bridge.ear,
    )


def _handoff_open(port: int, path: str) -> bool:
    """Çalışan dornick örneğine yolu devret. Başarılıysa True (yeni örnek açma)."""
    import json
    import urllib.error
    import urllib.request

    payload = json.dumps({"path": path}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{int(port)}/api/open",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        return bool(body.get("ok"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return False


def _kill_ghosts() -> None:
    """Bu makinedeki DİĞER dornick masaüstü örneklerini kapatır.

    Ölçüt komut satırı: python + ("dornick" ve "--app"). Kendi sürecimiz ve
    alakasız pythonlar dokunulmaz. Sessizce, en iyi çaba — süreç listesi
    okunamazsa açılış yine devam eder.
    """
    if sys.platform != "win32":
        return
    try:
        import json
        import subprocess

        from . import ortam

        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or "
             "Name='pythonw.exe' or Name='dornick.exe'\" | "
             "Select-Object ProcessId,CommandLine | "
             "ConvertTo-Json"],
            capture_output=True, text=True, timeout=10, encoding="utf-8",
            errors="replace", **ortam.sessiz_bayraklar(),
        ).stdout
        rows = json.loads(out or "[]")
        if isinstance(rows, dict):
            rows = [rows]
        me = os.getpid()
        from . import winicon
        skip = winicon.skip_pids() | {me}
        for row in rows:
            pid = row.get("ProcessId")
            cmd = (row.get("CommandLine") or "").lower()
            if not pid or pid in skip:
                continue
            if "dornick" in cmd and ("--app" in cmd or "desktop" in cmd):
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True,
                               **ortam.sessiz_bayraklar())
                print(f"[dornick] eski örnek kapatıldı (PID {pid})", flush=True)
    except Exception:
        pass


def run(config: Config, *, port: int = 8765, resume: bool = False,
        open_path: str | None = None) -> int:
    """Pencereyi açar ve kapanana kadar bloke eder."""
    # Görev çubuğu kimliği: bu ayarlanmazsa Windows pencereyi python.exe'nin
    # grubunda gösteriyor ve simge PYTHON logosu kalıyordu. Kendi kimliğiyle
    # gruplanınca pencerenin kendi simgesi (dornick logosu) görünür.
    # Görev Yöneticisi / WebView2 alt süreçleri ise PE ikonuna bakar —
    # o yüzden python(w) ise damgalı dornick.exe olarak yeniden açılır.
    if sys.platform == "win32":
        try:
            import ctypes

            from .winicon import AUMID, ensure_toast_identity
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)
            ensure_toast_identity()
        except Exception:
            pass

    # 'Dornick ile aç': çalışan örnek varsa ona devret — hayalet avı öldürmesin.
    pending_open = str(open_path or "").strip() or None
    if pending_open and _handoff_open(port, pending_open):
        return 0

    # HAYALET AVI: tepside gizli kalmış eski dornick örnekleri portu ve pencere
    # hedeflemesini ele geçirip yeni örneği sağır bırakıyordu — kullanıcı
    # "kapattım açtım" dedikçe hayaletler çoğalıyor, hiçbir düzeltme ekrana
    # ulaşmıyordu (üç günlük yaranın gerçek kökü). Yeni örnek açılırken
    # eskileri tek tek kapatır: her açılış temiz, tek örnek.
    # Damgalı dornick.exe yazılabilsin diye relaunch'tan ÖNCE: çalışan dornick.exe
    # kilitli kalırsa kopya basılmaz, Görev Yöneticisi'nde yılan kalır.
    _kill_ghosts()
    if sys.platform == "win32":
        try:
            from . import winicon
            winicon.relaunch_as_host()
        except Exception:
            pass
    # WebView2 mikrofon ve kamera için kendi izin penceresini açar; gömülü
    # bir pencerede o pencere hiç görünmüyor ve istek sessizce reddediliyor
    # — arayüzde yalnızca "mikrofon açılamadı" yazıyordu.
    #
    # Bayrak yalnızca kullanıcı ayarlardan açtıysa veriliyor: kapalıyken
    # medya iznini kendiliğinden vermek, istenmemiş bir yetkiyi açmak olur.
    if config.listen.enabled or config.camera.enabled:
        _allow_media()

    try:
        import webview
    except ImportError:
        from . import ortam
        raise SystemExit(
            "Bu kurulum eksik görünüyor (pencere paketi yok). Kurulum "
            "sihirbazını yeniden çalıştırmak eksiği onarır."
            if ortam.kurulu_mu() else
            "Masaüstü penceresi için pywebview gerekli: pip install 'dornick[app]'"
        ) from None

    loop = asyncio.new_event_loop()
    ready = threading.Event()
    box: dict[str, Any] = {}

    def spin() -> None:
        asyncio.set_event_loop(loop)

        async def setup() -> None:
            try:
                box["runtime"] = await _boot(config, port, resume)
            except Exception as exc:
                box["error"] = exc
            finally:
                ready.set()

        loop.create_task(setup())
        loop.run_forever()

    thread = threading.Thread(target=spin, daemon=True, name="dornick-agent")
    thread.start()

    # Açılış bir model indirmesine denk gelebiliyor (tanıma modeli `medium`
    # ise 1,5 GB). Kısa bir zaman aşımı o durumda `KeyError` olarak
    # patlıyordu: kullanıcının gördüğü şey yığın izi oluyor, sebebi
    # hiçbir yerde yazmıyordu.
    if not ready.wait(timeout=BOOT_TIMEOUT_S):
        loop.call_soon_threadsafe(loop.stop)
        raise SystemExit(
            f"Açılış {BOOT_TIMEOUT_S:.0f} saniyede bitmedi. Muhtemelen bir model "
            "indiriliyor; terminaldeki ilerlemeye bak ve indirme bitince yeniden "
            "başlat."
        )

    if error := box.get("error"):
        loop.call_soon_threadsafe(loop.stop)
        raise SystemExit(f"Başlatılamadı: {error}")

    runtime: Runtime = box["runtime"]

    # Soğuk açılışta --open: boot bittikten sonra yeni sohbet + klasör.
    if pending_open:
        try:
            runtime.bridge.open_path(pending_open)
        except Exception:
            pass

    # Native çerçeve: işletim sisteminin başlık çubuğu ve kenarları — böylece
    # TAŞIMA, büyüt/küçült, kenardan RESIZE ve Windows snap hepsi normal bir
    # uygulama gibi çalışıyor. (Çerçevesiz hal holografik "tek parça" hissi
    # veriyordu ama bunların hiçbirini vermiyordu; kullanıcı normal pencere
    # istedi.) resizable varsayılan True.
    # frameless: pywebview FormBorderStyle.None kurar — istemci alan pencereyi
    # ZATEN tam doldurur (kenarlarda masaüstü sızması yapısal olarak imkânsız).
    # Native davranışlar ayrıca ekleniyor: kutu stilleri (snap/animasyon),
    # HTCAPTION sürükleme (Aero snap dahil), WM_SYSCOMMAND büyüt/küçült ve
    # SC_SIZE kenar boyutlandırma — hepsi işletim sisteminin kendi döngüleri.
    geo = prefs.window_args(prefs.load(config.state_dir))
    # maximized'ı create_window'a VERME: çerçevesizde konum (101,101) gibi
    # kayıyor; kabuk + MaximizedBounds sonrası _force_maximize oturtuyor.
    want_max = bool(geo.get("maximized"))
    window = webview.create_window(
        WINDOW_TITLE,
        runtime.url,
        width=geo.get("width", 1360),
        height=geo.get("height", 880),
        x=geo.get("x"),
        y=geo.get("y"),
        maximized=False,
        min_size=(900, 600),
        background_color=WINDOW_BACKGROUND,
        frameless=True,
        # Varsayılan True: TÜM istemci alanı sürükleme bölgesi olur — kullanıcı
        # beyinden / sohbetten tutup pencereyi taşıyordu. Taşıma yalnız üst
        # şeritten (chrome.js → HTCAPTION); snap de o yoldan geliyor.
        easy_drag=False,
        # pywebview varsayılanı metin SEÇİMİNİ kapatıyor: pakette üretilen
        # cevaplar kopyalanamıyordu ("kopyala yapıştır çalışmıyor" — canlı,
        # 31.08; tarayıcı önizlemede görünmez çünkü orada pywebview yok).
        text_select=True,
    )
    # Kapatma penceresi gizliyor, yok etmiyor: ajanın arka planda durması
    # gereken işleri var (zamanlanmış görevler, kameraları izleyen alt
    # ajanlar, uyandırma sözünü bekleyen mikrofon). Tepsi yoksa kapatma
    # gerçekten kapatıyor — yoksa program kapanmaz hale gelirdi.
    #
    # Çıkış bekçisi: tepsiden Çıkış seçildiğinde ajan bir işin ortasındaysa
    # native bir Evet/Hayır penceresi soruyor — süren iş sessizce ölmesin.
    # Evet'te temiz kapanış: park/yetim mekanizmaları izi düşürür ve açılış
    # sürdürmeyi zaten teklif eder.
    # X ile Çıkış aynı `closing` olayına düşüyor; ayrımı `Kapanis` tutuyor.
    # `gizle` aşağıda tanımlanan `_hide_to_tray`e bağlanıyor (balon dahil),
    # ama o daha ilerideki satırlarda doğduğu için buradan geç bağlanıyor.
    kapanis = tray_module.Kapanis(
        gizle=lambda: _hide_to_tray(),
        yok_et=lambda: window.destroy(),
    )

    def _show_from_tray() -> None:
        """Tepsiden / uyandırma: pencere gelsin; arka planda biten işler
        Görevler panelinde görünsün (liste tazelensin)."""
        window.show()
        _ensure_native_chrome()
        # Gizliyken kutu bozulmuş olabilir (kaymış büyütme); görünür olunca bak.
        threading.Timer(0.4, _heal_geometry).start()
        runtime.bridge.hub.emit({"type": "jobs_refresh"})

    def _open_jobs_from_tray() -> None:
        window.show()
        _ensure_native_chrome()
        threading.Timer(0.4, _heal_geometry).start()
        runtime.bridge.hub.emit({"type": "open_jobs"})

    tray = tray_module.Tray(
        show=_show_from_tray,
        hide=lambda: window.hide(),
        quit=kapanis.cik,
        busy=lambda: runtime.bridge.busy,
        confirm=_confirm_quit,
        jobs=_open_jobs_from_tray,
        # Onaylı Çıkış her koşulda süreçle biter: GUI katmanı kilitliyse
        # 12 sn sonra kesin iniş (canlı yara, 01.09).
        bekci=tray_module.cikis_bekcisi_kur,
    )
    live = tray.start()
    runtime.bridge.tray = tray

    # Tek şerit: OS başlık çubuğu sökülüyor (strip_caption, _titlebar_boot'ta)
    # ve pencere denetimleri app'in kendi şeridine geçiyor. Native davranışlar
    # (kenardan resize, snap, görev çubuğu) pencere stillerinde duruyor.
    window.expose(_wake(window))
    window.expose(paint_titlebar)

    global _MAIN_WINDOW
    _MAIN_WINDOW = window

    def minimize() -> None:
        _win_do("minimize")

    def maximize() -> bool:
        # Büyütme sınırı o anki monitöre göre tazelensin (görev çubuğu);
        # dönen değer yeni durum — arayüz ikonunu ona göre çiziyor.
        _update_max_bounds()
        return _win_do("maximize")

    def drag() -> bool:
        # Dönen değer: sürükleme sonrası büyütülü mü? Şerit ikonu buna göre.
        _win_do("drag")
        _update_max_bounds()
        return _is_zoomed()

    def resize(edge: str) -> None:
        _win_do("resize:" + str(edge))

    def is_zoomed() -> bool:
        return _is_zoomed()

    def pano_oku() -> str:
        """Windows panosundan düz metin okur (ctypes; ek bağımlılık yok).

        Sağ tık menüsünün "Yapıştır"ı buradan besleniyor: WebView2'nin
        varsayılan menüsünü pywebview üretimde kapatıyor ve tarayıcı
        pano-okuma izni WebView2 içinde sorulamıyor — Python tarafı her
        zaman okuyabilir (natif tur, 31.08)."""
        import ctypes
        CF_UNICODETEXT = 13
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        # 64-bit tuzak: restype bildirilmezse tutamaç 32-bit'e KIRPILIR ve
        # GlobalLock çöp işaretçiyle patlar (natif turda menü "Yapıştır"ı
        # sessizce boş dönüyordu, 31.08).
        u32.GetClipboardData.restype = ctypes.c_void_p
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        if not u32.OpenClipboard(0):
            return ""
        try:
            handle = u32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = k32.GlobalLock(handle)
            try:
                return ctypes.wstring_at(ptr) if ptr else ""
            finally:
                k32.GlobalUnlock(handle)
        except Exception:
            return ""
        finally:
            u32.CloseClipboard()

    def pano_yaz(metin: str = "") -> bool:
        """Windows panosuna düz metin yazar (Kopyala/Kes için)."""
        import ctypes
        CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
        veri = str(metin or "")
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        k32.GlobalAlloc.restype = ctypes.c_void_p
        k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        u32.SetClipboardData.restype = ctypes.c_void_p
        u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        if not u32.OpenClipboard(0):
            return False
        try:
            u32.EmptyClipboard()
            boyut = (len(veri) + 1) * ctypes.sizeof(ctypes.c_wchar)
            hglob = k32.GlobalAlloc(GMEM_MOVEABLE, boyut)
            if not hglob:
                return False
            ptr = k32.GlobalLock(hglob)
            ctypes.memmove(ptr, ctypes.create_unicode_buffer(veri), boyut)
            k32.GlobalUnlock(hglob)
            u32.SetClipboardData(CF_UNICODETEXT, hglob)
            return True
        except Exception:
            return False
        finally:
            u32.CloseClipboard()

    def open_camera_window(cam: str = "") -> str:
        """Kamera izlemeyi ayrı OS penceresinde açar; varsa öne getirir."""
        global _CAM_WINDOW
        import threading
        import webview

        q = ("?cam=" + str(cam)) if cam else ""
        url = str(runtime.url).rstrip("/") + "/watch.html" + q
        existing = _CAM_WINDOW
        if existing is not None:
            try:
                existing.show()
                return "ok"
            except Exception:
                _CAM_WINDOW = None
        spawned = webview.create_window(
            "Dornick · Kamera",
            url,
            width=980,
            height=640,
            min_size=(480, 320),
            background_color=WINDOW_BACKGROUND,
            frameless=True,
            easy_drag=False,
            text_select=True,
        )
        _CAM_WINDOW = spawned

        def minimize() -> None:
            _win_do("minimize", spawned)

        def maximize() -> bool:
            _update_max_bounds_for(spawned)
            return _win_do("maximize", spawned)

        def drag() -> bool:
            _win_do("drag", spawned)
            _update_max_bounds_for(spawned)
            return _is_zoomed(spawned)

        def resize(edge: str) -> None:
            _win_do("resize:" + str(edge), spawned)

        def close() -> None:
            try:
                spawned.destroy()
            except Exception:
                pass

        def is_zoomed() -> bool:
            return _is_zoomed(spawned)

        for fn in (minimize, maximize, drag, resize, close, is_zoomed):
            try:
                spawned.expose(fn)
            except Exception:
                pass

        def _dress() -> None:
            hwnd = _hwnd_of(spawned)
            if not hwnd:
                return
            _apply_native_styles_hwnd(hwnd)
            _install_shell_on(hwnd)
            _update_max_bounds_for(spawned)

        def _dress_retry(n: int) -> None:
            _dress()
            if n > 0 and not _hwnd_of(spawned):
                threading.Timer(0.12, lambda: _dress_retry(n - 1)).start()

        try:
            spawned.events.loaded += _dress
            spawned.events.shown += _dress
        except Exception:
            pass
        _dress_retry(12)

        def _gone() -> None:
            global _CAM_WINDOW
            _CAM_WINDOW = None

        try:
            spawned.events.closed += _gone
        except Exception:
            pass
        return "ok"

    # X = gizle, uygulama TEPSİDE yaşar (Claude Code / masaüstü geleneği):
    # süren iş, zamanlanmış görevler ve duyular pencereyle birlikte ölmez.
    # Eskiden yalnızca kulak açıkken gizleniyordu; ama X'in işi yarıda
    # kesmesi kulaktan bağımsız bir yara — koşan bir görev de pencere
    # kapandı diye ölmemeli. Hayalet-süreç riski kalmadı: her açılış
    # eski örnekleri kapatıyor (_kill_ghosts) ve tepsiden gerçek Çıkış var.
    # Tepsi hiç açılamadıysa (paket yok) X gerçekten kapatır — yoksa
    # program kapanmaz hale gelirdi.
    hide_on_close = live

    # X'e İLK basışta bir kez balon bildirimi: "arka planda çalışmaya devam
    # ediyor". Meşgul olup olmamasından bağımsız — pencere kaybolunca
    # kullanıcı programın kapandığını sanıyor ve asıl öğretilmesi gereken
    # şey bu. Tekrarı `note_once` engelliyor (her gizlenişte balon = dırdır).
    def _remember_window() -> None:
        """Pencere kutusu kapanıştaki gibi açılsın."""
        try:
            zoomed = _is_zoomed()
            w = int(window.width or 0)
            h = int(window.height or 0)
            x = int(window.x if window.x is not None else 0)
            y = int(window.y if window.y is not None else 0)
            # Offset’li neredeyse-tam-ekran = bozuk büyütme; bir daha yazma.
            if not zoomed and prefs.offset_fullscreen(x, y, w, h):
                zoomed = True
            # Work-area'ya oturan fake maximize da büyütülmüş sayılsın.
            elif not zoomed and _fills_work_area(x, y, w, h):
                zoomed = True
            box: dict[str, Any] = {"maximized": zoomed}
            if not zoomed:
                box.update({"width": w, "height": h, "x": x, "y": y})
            prefs.patch(config.state_dir, window=box)
        except Exception:
            pass

    def _hide_to_tray() -> None:
        _remember_window()
        window.hide()
        tray.note_once(tray_module.ARKA_PLAN_NOTU)

    def close() -> None:
        _remember_window()
        if hide_on_close:
            _hide_to_tray()
        else:
            window.destroy()

    for fn in (minimize, maximize, drag, resize, close, is_zoomed,
               open_camera_window, pano_oku, pano_yaz):
        window.expose(fn)

    # Native kapatma (X / Alt+F4) programı YOK ETMESİN, tepsiye gizlesin:
    # pywebview'in closing olayı False dönünce kapanış iptal olur ve pencere
    # gizlenir — app şeridindeki X ile aynı yol.
    if hide_on_close:
        def _hide_instead_of_close() -> bool:
            return kapanis.kapanabilir_mi()

        try:
            window.events.closing += _hide_instead_of_close
        except Exception:
            pass

    # Uyandırma sözü duyulduğunda pencere geri geliyor: gizliyken de sayfa
    # çalışmaya devam ediyor, mikrofon dinliyor.
    runtime.bridge.on_wake = _show_from_tray

    if hide_on_close:
        print("[dornick] tepside çalışıyor — X pencereyi gizler; görevler arka "
              "planda sürer, Çıkış tepsiden", flush=True)
    else:
        print("[dornick] tepsi yok; pencereyi kapatmak programı da kapatır "
              "(arka plan görevleri için: pip install 'dornick[tray]')",
              flush=True)

    try:
        # Pencere/görev çubuğu simgesi: tek kaynak logodan (tepsi ve sekmeyle
        # aynı işaret). pywebview winforms bunu form.Icon yapıyor.
        from . import logo as logo_module
        webview.start(
            lambda: _titlebar_boot(want_max=want_max),
            icon=str(logo_module.ico_path()),
            private_mode=False,
            storage_path=str(config.state_dir / "webview"),
        )
    finally:
        _remember_window()
        tray.stop()
        _teardown(loop, runtime)
    return 0


def _ensure_native_chrome() -> None:
    """Tek şeridi garanti eder: stiller + kabuk kurulu değilse kurar.

    Açılışta pencere gizliyse `_titlebar_boot` boşa dönebiliyor; pencere
    sonradan (tepsi, uyandırma) gösterildiğinde OS başlık çubuğu uygulama
    şeridinin üstünde kalıyordu. Kurulumlar bağışık (idempotent): zaten
    kuruluysa maliyeti yok.
    """
    try:
        if _apply_native_styles():
            _install_shell()
            _update_max_bounds()
            paint_titlebar(True)
    except Exception:
        pass


def _titlebar_boot(*, want_max: bool = False) -> None:
    """webview başladıktan sonra çalışır: pencere oluşana dek dener.

    Tek şerit: CAPTION+THICKFRAME stilleri yerinde (snap), WM_NCCALCSIZE üst
    payı istemciye (OS şeridi görünmez), WM_NCHITTEST kenar tutamakları.

    `want_max`: prefs büyütülmüş diyorsa MaximizedBounds hazır olduktan
    sonra zorla büyüt — create_window(maximized)+offset çerçevesizde
    tutmuyordu; küçült/görev çubuğu açınca düzelirdi.
    """
    import time
    for _ in range(40):
        if _apply_native_styles():
            _install_shell()
            _update_max_bounds()
            paint_titlebar(True)
            if want_max:
                _force_maximize()
            else:
                _clamp_window_to_work()
            # Geç bozulmaya karşı nöbet: açılış yerleşiminden sonra kutu
            # birileri tarafından (100,100)'e kayarsa yakala ve oturt.
            threading.Thread(target=_geometry_watch, daemon=True,
                             name="dornick-geometry-watch").start()
            return
        time.sleep(0.15)


# Ana pencere referansı: pencere-kabuk yardımcıları (MaximizedBounds) için.
_MAIN_WINDOW: Any = None
# Ayrı kamera izleme penceresi (create_window); kapanınca None.
_CAM_WINDOW: Any = None

# Kabuk referansları (WndProc callback + eski proc) GC'ye gitmesin.
_SHELL: dict[int, tuple[Any, int]] = {}

# ÖZEL WinDLL: ctypes.windll süreç-genelinde PAYLAŞILAN bir önbellek —
# pystray/pywebview aynı fonksiyon nesnelerine kendi argtypes'larını yazınca
# bizim çağrılarımız bozuk marshaling'le çöküyordu (access violation'ların
# gerçek kökü; sabotajlı stres testiyle kanıtlandı). Bu handle yalnız bizim.
_PRIV: dict[str, Any] = {}


def _user32() -> Any:
    if "u" not in _PRIV:
        import ctypes
        from ctypes import wintypes

        u = ctypes.WinDLL("user32", use_last_error=True)
        LRESULT = ctypes.c_longlong
        u.CallWindowProcW.restype = LRESULT
        u.CallWindowProcW.argtypes = [LRESULT, wintypes.HWND, ctypes.c_uint,
                                      wintypes.WPARAM, wintypes.LPARAM]
        u.SetWindowLongPtrW.restype = LRESULT
        u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, LRESULT]
        u.GetWindowLongPtrW.restype = LRESULT
        u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SendMessageW.restype = LRESULT
        u.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                   wintypes.WPARAM, wintypes.LPARAM]
        _PRIV["u"] = u
    return _PRIV["u"]


def _install_shell() -> bool:
    """Pencere kabuğu: görünmez çerçeve, native davranış (kanıtlanmış tasarım).

    WS_THICKFRAME pencerede DURUYOR: Windows kenardan boyutlandırmayı ve
    snap'i yalnız boyutlandırılabilir pencereye verir.

    Çerçeveyi WM_NCCALCSIZE→0 ile TAMAMEN yutmak snap'i bozuyordu: Windows
    yapıştırma boyutunu uyguluyor ama KONUMU uygulamıyordu, pencere fareyi
    izlemeye devam ediyordu (izole testte birebir: sol kenara sürüklerken
    istemci (-400,504) 960x1032'de kalıyor, beklenen (0,0) 960x1032). Kenardan
    boyutlandırma da aynı sebeple ölüydü (3/3 koşumda 0 piksel). Windows
    yapıştırılan/boyutlandırılan pencereyi yerleştirmek için GERÇEK çerçeve
    ölçülerine bakıyor; çerçeve sıfırlanınca hesap tutmuyor.

    Bu yüzden çerçeve YERİNDE bırakılıyor, yalnız ÜST payı istemciye
    katılıyor: yan/alt kenarlar Windows'un görünmez tutamakları olarak duruyor
    (zaten görünmezler — pencere kenarı istemcide bitiyor), üstte de OS şeridi
    kalmıyor. Aynı izole testte snap istemciyi (1,0) 958x1031'e oturttu ve
    Windows'un yapıştırma önizlemesi/Snap Assist paneli çıktı; boyutlandırma
    3/3 çalıştı. Büyütülmüşken çerçeve payı istenmiyor: MaximizedBounds
    pencereyi çalışma alanına oturttuğu için istemci = pencere (→0) ve
    büyütme birebir çalışma alanına denk geliyor.

    WM_NCHITTEST kenar tutamaklarını veriyor. Ayrı pencerede 5000+ mesajlık
    sabotajlı stres testinden sıfır hatayla geçti.
    """
    if sys.platform != "win32":
        return True
    targets = _dornick_windows(gizli_de=True)   # bkz. _apply_native_styles
    if not targets:
        return False
    ok = False
    for hwnd in targets:
        if _install_shell_on(hwnd):
            ok = True
    return ok


def _install_shell_on(hwnd: int) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        u = _user32()
        if hwnd in _SHELL:
            return True

        LRESULT = ctypes.c_longlong
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint,
                                     wintypes.WPARAM, wintypes.LPARAM)
        old = u.GetWindowLongPtrW(hwnd, -4)   # GWLP_WNDPROC

        class NcCalcSize(ctypes.Structure):
            _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        def proc(h, msg, wp, lp):
            try:
                if msg == 0x0083 and wp:          # WM_NCCALCSIZE(TRUE)
                    p = ctypes.cast(lp, ctypes.POINTER(NcCalcSize)).contents
                    if u.IsZoomed(h):
                        # Kalın çerçeveli pencere büyüyünce Windows ~8px ekran
                        # DIŞINA taşır; gerçek non-client o payı gizler. Biz
                        # zoom'da çerçeveyi yutunca HUD/üst şerit de -8'e
                        # kayıyordu. İstemciyi monitör ÇALIŞMA ALANINA kilitle.
                        mi = MonitorInfo()
                        mi.cbSize = ctypes.sizeof(MonitorInfo)
                        mon = u.MonitorFromRect(ctypes.byref(p.rgrc[0]), 2)
                        if (mon and u.GetMonitorInfoW(mon, ctypes.byref(mi))
                                and abs(p.rgrc[0].left - mi.rcWork.left) <= 64
                                and abs(p.rgrc[0].top - mi.rcWork.top) <= 64):
                            p.rgrc[0].left = mi.rcWork.left
                            p.rgrc[0].top = mi.rcWork.top
                            p.rgrc[0].right = mi.rcWork.right
                            p.rgrc[0].bottom = mi.rcWork.bottom
                        else:
                            # Yedek — ve KAYMIŞ zoom: pencere (100,100) gibi
                            # bozuk bir konumda zoom'lanmışken work-area kilidi
                            # istemciyi pencereye göre EKSİYE kaydırıyordu
                            # (canlı: içerik solda/üstte kırpık, masaüstü
                            # sızıyor). Kaymışsa klasik payla yetin; pencereyi
                            # yerine oturtmak _heal_geometry'nin işi.
                            p.rgrc[0].left += 8
                            p.rgrc[0].top += 8
                            p.rgrc[0].right -= 8
                            p.rgrc[0].bottom -= 8
                        return 0
                    top = p.rgrc[0].top
                    ret = u.CallWindowProcW(old, h, msg, wp, lp)
                    p.rgrc[0].top = top            # üst pay istemciye
                    return ret
                if msg == 0x0084:                  # WM_NCHITTEST
                    x = ctypes.c_short(lp & 0xFFFF).value
                    y = ctypes.c_short((lp >> 16) & 0xFFFF).value
                    r = wintypes.RECT()
                    u.GetWindowRect(h, ctypes.byref(r))
                    if not u.IsZoomed(h):
                        left = x < r.left + 8
                        right = x >= r.right - 8
                        top = y < r.top + 8
                        bottom = y >= r.bottom - 8
                        if top and left: return 13
                        if top and right: return 14
                        if bottom and left: return 16
                        if bottom and right: return 17
                        if left: return 10
                        if right: return 11
                        if top: return 12
                        if bottom: return 15
            except Exception:
                pass
            return u.CallWindowProcW(old, h, msg, wp, lp)

        cb = WNDPROC(proc)
        u.SetWindowLongPtrW(hwnd, -4, ctypes.cast(cb, ctypes.c_void_p).value)
        _SHELL[hwnd] = (cb, old)
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_FRAMECHANGED)
        return True
    except Exception:
        return False


def _hwnd_of(window: Any) -> int:
    """pywebview penceresinin HWND'si; henüz doğmadıysa 0."""
    if window is None:
        return 0
    try:
        form = getattr(window, "native", None)
        if form is None:
            return 0
        handle = getattr(form, "Handle", None)
        if handle is None:
            return 0
        to64 = getattr(handle, "ToInt64", None)
        return int(to64()) if callable(to64) else int(handle)
    except Exception:
        return 0


def _update_max_bounds() -> None:
    _update_max_bounds_for(_MAIN_WINDOW)


def _update_max_bounds_for(window: Any) -> None:
    """Büyütme sınırını o anki monitörün ÇALIŞMA ALANINA ayarlar.

    Çerçevesiz bir pencereyi Windows tam ekrana (görev çubuğunun üstüne)
    büyütür — kullanıcının en başta şikayet ettiği davranış. WinForms'un
    MaximizedBounds özelliği bunu kökünden çözüyor: Win+Yukarı, üst kenara
    snap ve bizim düğmemiz dahil HER büyütme yolu bu sınırı kullanır.
    Pencere hangi monitördeyse onun çalışma alanı; her sürüklemeden sonra
    tazeleniyor ki monitör değişimi doğru kalsın.
    """
    if window is None or sys.platform != "win32":
        return
    try:
        form = window.native
        if form is None:
            return
        from System import Action  # type: ignore[import-not-found]
        from System.Drawing import Rectangle  # type: ignore[import-not-found]
        from System.Windows.Forms import Screen  # type: ignore[import-not-found]

        def apply() -> None:
            screen = Screen.FromControl(form)
            wa, sb = screen.WorkingArea, screen.Bounds
            # KONUM MONİTÖRE GÖRELİ olmak zorunda (WM_GETMINMAXINFO
            # ptMaxPosition semantiği): mutlak verilince Windows monitör
            # orijinini BİR KEZ DAHA ekliyor ve pencere ikinci monitörde
            # tamamen ekran DIŞINA büyüyordu — kullanıcının 'kareye
            # basınca kayboluyor' yaşadığı hata buydu (canlı yakalandı:
            # (1920,-77) beklenirken (3840,-154)'e gitti; göreli konumla
            # birebir çalışma alanına oturduğu ayrı formda kanıtlandı).
            form.MaximizedBounds = Rectangle(
                wa.X - sb.X, wa.Y - sb.Y, wa.Width, wa.Height)

        # WinForms özellikleri UI thread'inden: Invoke oraya sıraya sokar.
        form.Invoke(Action(apply))
    except Exception:
        pass


def _apply_native_styles() -> bool:
    """Çerçevesiz pencereye native pencere KİMLİĞİ kazandırır.

    WS_CAPTION şart: Aero snap / kenara yapıştırma konumunu Windows yalnız
    başlıklı (caption'lı) pencerelerde doğru uygular. Görsel OS şeridi
    kabuğun WM_NCCALCSIZE üst-yutmasıyla silinir; stil bayrağı yerinde kalır.

    THICKFRAME + MIN/MAXIMIZEBOX + SYSMENU: kenar resize, Win+ok, görev
    çubuğu animasyonları. Win11 köşeleri yuvarlatılır.
    """
    if sys.platform != "win32":
        return True
    try:
        # GİZLİ pencere de hedef: uygulama tepsiye açıldığında (pencere
        # gizli doğar) görünürlük süzgeci hiçbir şey bulamıyordu ve
        # `_titlebar_boot` altı saniye deneyip vazgeçiyordu — kabuk hiç
        # kurulmuyor, pencere sonradan gösterilince Windows'un kendi
        # başlık çubuğu uygulamanın şeridinin ÜSTÜNDE kalıyordu
        # (canlı yara, 02.09: "üstte iki şerit").
        targets = _dornick_windows(gizli_de=True)
        if not targets:
            return False
        for hwnd in targets:
            _apply_native_styles_hwnd(hwnd)
        return True
    except Exception:
        return False


def _apply_native_styles_hwnd(hwnd: int) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, _GWL_STYLE)
        style |= (
            _WS_CAPTION
            | _WS_THICKFRAME
            | _WS_MINIMIZEBOX
            | _WS_MAXIMIZEBOX
            | _WS_SYSMENU
        )
        user32.SetWindowLongW(hwnd, _GWL_STYLE, style)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_FRAMECHANGED)
        try:
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass
        return True
    except Exception:
        return False


_GWL_STYLE = -16
_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_WS_MINIMIZEBOX = 0x00020000
_WS_MAXIMIZEBOX = 0x00010000
_WS_SYSMENU = 0x00080000
_SWP_FRAMECHANGED = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
_WM_NCLBUTTONDOWN = 0x00A1
_HTCAPTION = 2
_WM_SYSCOMMAND = 0x0112
_SC_MINIMIZE = 0xF020
_SC_MAXIMIZE = 0xF030
_SC_RESTORE = 0xF120
# Kenar HT* — SC_SIZE FormBorderStyle.None'da ölüydü; NCLBUTTONDOWN çalışıyor.
_HT_EDGES = {
    "l": 10, "r": 11, "t": 12, "tl": 13, "tr": 14,
    "b": 15, "bl": 16, "br": 17,
}


def _is_zoomed(window: Any | None = None) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        hwnd = _hwnd_of(window) if window is not None else 0
        if not hwnd:
            targets = _dornick_windows()
            hwnd = targets[0] if targets else 0
        return bool(hwnd and ctypes.windll.user32.IsZoomed(hwnd))
    except Exception:
        return False


def _win_do(action: str, window: Any | None = None) -> bool:
    """Pencere eylemleri app şeridinden: sürükle / küçült / büyüt / geri al.

    Sürükleme WM_NCLBUTTONDOWN + HTCAPTION: OS taşıma döngüsü (Aero snap dahil).
    JS köprüsü başka thread'den gelir — SendMessage'i WinForms UI thread'inde
    BeginInvoke ile çalıştırıyoruz; aksi halde fare basılıyken döngü hiç
    başlamıyor (kullanıcı 'üst bardan tutup sürükleyemiyorum').

    SendMessageW / ReleaseCapture özel `_user32()` handle'ından: paylaşılan
    ctypes.windll argtypes'ı pywebview/pystray bozunca çağrı sessizce ölüyordu.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        u = _user32()
        raw = ctypes.windll.user32
        hwnd = _hwnd_of(window) if window is not None else 0
        if not hwnd:
            targets = _dornick_windows()
            if not targets:
                return False
            hwnd = targets[0]

        def _drag_now() -> None:
            if raw.IsZoomed(hwnd):
                pt = wintypes.POINT()
                raw.GetCursorPos(ctypes.byref(pt))
                before = wintypes.RECT()
                raw.GetWindowRect(hwnd, ctypes.byref(before))
                span = max(before.right - before.left, 1)
                ratio = (pt.x - before.left) / span
                raw.ShowWindow(hwnd, 9)  # SW_RESTORE
                after = wintypes.RECT()
                raw.GetWindowRect(hwnd, ctypes.byref(after))
                w = after.right - after.left
                nx = int(pt.x - w * ratio)
                ny = pt.y - 28
                raw.SetWindowPos(hwnd, 0, nx, ny, 0, 0, 0x0001 | 0x0004)
            raw.ReleaseCapture()
            u.SendMessageW(hwnd, _WM_NCLBUTTONDOWN, _HTCAPTION, 0)

        def _resize_now(edge: int) -> None:
            if raw.IsZoomed(hwnd):
                return
            raw.ReleaseCapture()
            u.SendMessageW(hwnd, _WM_NCLBUTTONDOWN, edge, 0)

        def _on_ui(fn) -> None:
            """Taşıma/boyutlandırma döngüsü UI thread'inde başlamalı."""
            win = window if window is not None else _MAIN_WINDOW
            form = getattr(win, "native", None) if win is not None else None
            if form is not None:
                try:
                    from System import Action  # type: ignore[import-not-found]
                    form.BeginInvoke(Action(fn))
                    return
                except Exception:
                    pass
            fn()

        if action == "drag":
            _on_ui(_drag_now)
        elif action == "minimize":
            u.SendMessageW(hwnd, _WM_SYSCOMMAND, _SC_MINIMIZE, 0)
        elif action == "maximize":
            if raw.IsZoomed(hwnd):
                u.SendMessageW(hwnd, _WM_SYSCOMMAND, _SC_RESTORE, 0)
            else:
                u.SendMessageW(hwnd, _WM_SYSCOMMAND, _SC_MAXIMIZE, 0)
            return bool(raw.IsZoomed(hwnd))
        elif action.startswith("resize:"):
            edge = _HT_EDGES.get(action.split(":", 1)[1])
            if edge:
                _on_ui(lambda e=edge: _resize_now(e))
        return False
    except Exception:
        return False


def _dornick_windows(*, gizli_de: bool = False) -> list[int]:
    """Bu süreçte 'dornick' başlıklı görünür top-level pencerelerin HWND'leri.

    FindWindowW(None, title) tek bir eşleşme döndürüyor ve bazı kurulumlarda
    hiç bulamıyordu; EnumWindows tüm eşleşmeleri güvenle veriyor (canlı
    pencerede kanıtlandı).

    `gizli_de=True` görünürlük süzgecini kaldırıyor: pencere tepsiye
    gizlenmişken de bir sahip (owner) HWND'sine ihtiyaç duyan tek yer
    `_confirm_quit` — ve tam o an pencere gizli oluyor.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []
    my_pid = os.getpid()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        if not gizli_de and not user32.IsWindowVisible(hwnd):
            return True
        # YALNIZCA bu sürecin penceresi: iki dornick örneği açıkken (ya da bir
        # test örneği varken) düğmeler ÖTEKİ örneğin penceresini yönetiyordu —
        # "basıyorum, olmuyor / başka bir şey oluyor" tam buydu.
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != my_pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value.strip().lower() == WINDOW_TITLE.lower():
            found.append(hwnd)
        return True

    user32.EnumWindows(_enum, 0)
    return found


def paint_titlebar(dark: bool = True) -> bool:
    """Native başlık çubuğunu uygulamanın temasına boyar (Windows 11 DWM).

    Native çerçeve normal pencere davranışını (taşı/büyüt/resize/snap) veriyor
    ama işletim sisteminin açık başlık çubuğu koyu holografik gövdeyle
    çelişiyordu ("bu yukarı sistemle uyumsuz oldu"). DWM ile başlık çubuğunu
    koyu/açık yapıyoruz; arayüzdeki tema düğmesi de bunu çağırıyor ki OS çubuğu
    ile uygulama teması birlikte dönsün. Pencere henüz yoksa False döner ki
    çağıran tekrar denesin.
    """
    if sys.platform != "win32":
        return True   # başka platformda yapılacak bir şey yok, "tamam" say
    try:
        import ctypes

        user32 = ctypes.windll.user32
        dwm = ctypes.windll.dwmapi
        targets = _dornick_windows()
        if not targets:
            return False   # pencere henüz oluşmadı — çağıran tekrar denesin

        def _set(hwnd: int, attr: int, value: int) -> None:
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        for hwnd in targets:
            # Immersive dark mode — hem yeni (20) hem eski (19) indeks; hangisi
            # bu yapıda geçerliyse o tutuyor.
            for attr in (20, 19):
                _set(hwnd, attr, 1 if dark else 0)
            # Tam renk (Win11 22000+): COLORREF 0x00BBGGRR. Koyu #0b0e14/#dceefc,
            # açık #e7edf4/#1a2836. Eski yapıda sessizce yok sayılır.
            _set(hwnd, 35, 0x00140E0B if dark else 0x00F4EDE7)  # caption zemini
            _set(hwnd, 36, 0x00FCEEDC if dark else 0x0036281A)  # başlık yazısı
            # Başlık çubuğunu hemen yeniden çizmeye zorla (FRAMECHANGED).
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
        return True
    except Exception:
        return False


def _minimize(window: Any) -> Any:
    def minimize() -> None:
        window.minimize()

    return minimize


def _work_area() -> tuple[int, int, int, int] | None:
    """Ekranın görev çubuğu hariç alanı (x, y, genişlik, yükseklik)."""
    return prefs.work_area()


def _force_maximize() -> None:
    """Çalışma alanına oturt — native SW_MAXIMIZE çerçevesizde kaydırıyordu.

    create_window(maximized=True) / ShowWindow(SW_MAXIMIZE) IsZoomed=True
    bırakıp HWND'yi (101,101) gibi bırakıyordu (sol masaüstü boşluğu).
    Küçült/geri aç düzeltiyordu. Açılışta doğrudan work-area kutusu
    veriyoruz; prefs `maximized` bayrağı _remember_window ile korunur.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        raw = ctypes.windll.user32
        hwnd = _hwnd_of(_MAIN_WINDOW)
        if not hwnd:
            targets = _dornick_windows()
            hwnd = targets[0] if targets else 0
        if not hwnd:
            return
        area = _work_area()
        if not area:
            return
        ax, ay, aw, ah = area
        _update_max_bounds()
        # SW_RESTORE: önceki bozuk zoom state'ini bırak.
        if raw.IsZoomed(hwnd):
            raw.ShowWindow(hwnd, 9)
        # SWP_NOZORDER|SWP_SHOWWINDOW
        raw.SetWindowPos(hwnd, 0, ax, ay, aw, ah, 0x0004 | 0x0040)
        r = wintypes.RECT()
        raw.GetWindowRect(hwnd, ctypes.byref(r))
        if (
            abs(r.left - ax) > prefs.OFFSET_SLACK
            or abs(r.top - ay) > prefs.OFFSET_SLACK
            or abs((r.right - r.left) - aw) > prefs.OFFSET_SLACK * 2
        ):
            raw.SetWindowPos(hwnd, 0, ax, ay, aw, ah, 0x0004 | 0x0040)
    except Exception:
        pass


def _monitor_work_area(hwnd: int) -> tuple[int, int, int, int] | None:
    """Pencerenin ÜZERİNDE olduğu monitörün çalışma alanı.

    `prefs.work_area` yalnız ANA monitörü bilir; ikinci monitörde büyütülmüş
    bir pencereyi "kaymış" sanıp ana ekrana çekmek olmaz — kıyas pencerenin
    kendi monitörüne göre yapılmalı.
    """
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _MI(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        raw = ctypes.windll.user32
        mon = raw.MonitorFromWindow(hwnd, 2)   # MONITOR_DEFAULTTONEAREST
        if not mon:
            return None
        mi = _MI()
        mi.cbSize = ctypes.sizeof(_MI)
        if not raw.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        wa = mi.rcWork
        return (wa.left, wa.top, wa.right - wa.left, wa.bottom - wa.top)
    except Exception:
        return None


def _heal_geometry() -> bool:
    """Kaymış büyütmeyi yakalayıp oturtur — "küçült/geri aç" jestinin kod hali.

    Canlı yara (31.08): açılışta pencere near-full boyutta ama (100,100) gibi
    kaymış geliyordu — sol/üstten masaüstü sızıyor, zoom'luysa içerik de sola
    kırpılıyordu; kullanıcı elle küçültüp geri açınca düzeliyordu. Burada aynı
    jest kodla: kaymış zoom ya da kaymış near-full kutu görülürse restore +
    pencerenin KENDİ monitörünün çalışma alanına oturt.

    Düzgün pencereye dokunmaz; sürükleme sırasında da karışmaz (sol fare tuşu
    basılıysa hiçbir şey yapmaz). Döner: bir şey düzeltildi mi.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        raw = ctypes.windll.user32
        hwnd = _hwnd_of(_MAIN_WINDOW)
        if not hwnd:
            targets = _dornick_windows()
            hwnd = targets[0] if targets else 0
        if not hwnd or not raw.IsWindowVisible(hwnd) or raw.IsIconic(hwnd):
            return False
        if raw.GetAsyncKeyState(0x01) & 0x8000:   # sürükleme olabilir
            return False

        r = wintypes.RECT()
        raw.GetWindowRect(hwnd, ctypes.byref(r))
        x, y = r.left, r.top
        w, h = r.right - r.left, r.bottom - r.top

        area = _monitor_work_area(hwnd) or _work_area()
        if not area:
            return False
        ax, ay, aw, ah = area
        kaymis = (abs(x - ax) > prefs.OFFSET_SLACK
                  or abs(y - ay) > prefs.OFFSET_SLACK)
        if raw.IsZoomed(hwnd):
            if not kaymis:
                return False
        elif not prefs.offset_fullscreen(x, y, w, h, area):
            return False

        _update_max_bounds()
        if raw.IsZoomed(hwnd):
            raw.ShowWindow(hwnd, 9)   # SW_RESTORE: bozuk zoom durumunu bırak
        # SWP_NOZORDER | SWP_SHOWWINDOW
        raw.SetWindowPos(hwnd, 0, ax, ay, aw, ah, 0x0004 | 0x0040)
        return True
    except Exception:
        return False


def _geometry_watch(seconds: float = 12.0) -> None:
    """Açılıştan sonra pencere kutusunu kısa süre kollar.

    Bozuk büyütme `_force_maximize`'dan SONRA da oluşabiliyor (WebView2 /
    pywebview açılışı konumu geç oynatıyor); tek atış yetmiyordu — kullanıcı
    pencereyi kesik görüp elle küçültüp açıyordu. Bu nöbet geç bozulmayı
    yakalayıp düzeltir, sonra kendiliğinden biter.
    """
    import time
    son = time.monotonic() + seconds
    while time.monotonic() < son:
        time.sleep(0.6)
        _heal_geometry()


def _fills_work_area(x: int, y: int, w: int, h: int) -> bool:
    """Pencere çalışma alanını dolduruyor mu (fake maximize)."""
    area = _work_area()
    if not area:
        return False
    ax, ay, aw, ah = area
    return (
        abs(x - ax) <= prefs.OFFSET_SLACK
        and abs(y - ay) <= prefs.OFFSET_SLACK
        and w >= aw * prefs.NEAR_FULL
        and h >= ah * prefs.NEAR_FULL
    )


def _clamp_window_to_work() -> None:
    """Büyütülmemiş pencere çalışma alanı dışındaysa içeri çek."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        from .prefs import MIN_H, MIN_W

        area = _work_area()
        if not area:
            return
        ax, ay, aw, ah = area
        hwnd = _hwnd_of(_MAIN_WINDOW)
        if not hwnd:
            targets = _dornick_windows()
            hwnd = targets[0] if targets else 0
        if not hwnd:
            return
        raw = ctypes.windll.user32
        if raw.IsZoomed(hwnd):
            return
        r = wintypes.RECT()
        raw.GetWindowRect(hwnd, ctypes.byref(r))
        cur_w = r.right - r.left
        cur_h = r.bottom - r.top
        x, y = r.left, r.top
        if prefs.offset_fullscreen(x, y, cur_w, cur_h, area):
            _force_maximize()
            return
        w = min(max(cur_w, MIN_W), aw)
        h = min(max(cur_h, MIN_H), ah)
        nx = max(ax, min(x, ax + max(aw - w, 0)))
        ny = max(ay, min(y, ay + max(ah - h, 0)))
        if (nx, ny, w, h) != (x, y, cur_w, cur_h):
            raw.SetWindowPos(hwnd, 0, nx, ny, w, h, 0x0004)  # SWP_NOZORDER
    except Exception:
        pass


def _maximize(window: Any) -> Any:
    """Büyüt / geri al — görev çubuğuna saygılı (tam ekran değil).

    Çerçevesiz pencerede `window.maximize()` görev çubuğunu da kaplayan bir
    tam ekran veriyordu. Onun yerine pencereyi ekranın çalışma alanına (görev
    çubuğu hariç) taşıyıp boyutlandırıyoruz; ikinci tık önceki konum/boyuta
    döndürüyor. Böylece hem "büyütüyor ama küçültmüyor" hem de "görev çubuğunu
    kaptı" sorunları birlikte çözülüyor. Çalışma alanı alınamazsa (Windows
    dışı ya da hata) `maximize()`'e düşülüyor.
    """
    state: dict[str, Any] = {"box": None}

    def maximize() -> None:
        if state["box"] is not None:
            x, y, w, h = state["box"]
            state["box"] = None
            try:
                window.move(x, y)
                window.resize(w, h)
            except Exception:
                try:
                    window.restore()
                except Exception:
                    pass
            return

        area = _work_area()
        if area is None:
            window.maximize()
            state["box"] = None
            return
        try:
            state["box"] = (window.x, window.y, window.width, window.height)
            window.move(area[0], area[1])
            window.resize(area[2], area[3])
        except Exception:
            state["box"] = None
            window.maximize()

    return maximize


def _close(window: Any, *, tray: bool = False) -> Any:
    """Kapatma düğmesi.

    Tepsi çalışıyorsa gizliyor: arka plandaki işler sürsün. Tepsi yoksa
    gerçekten kapatıyor — aksi halde program kapanmaz hale gelirdi ve
    kullanıcının onu görev yöneticisinden öldürmesi gerekirdi.
    """

    def close() -> None:
        window.hide() if tray else window.destroy()

    return close


def _wake(window: Any) -> Any:
    def wake() -> None:
        window.show()
        threading.Timer(0.4, _heal_geometry).start()

    return wake


def _confirm_quit(question: str) -> bool:
    """Çıkış onayı: native Evet/Hayır penceresi (tepsi thread'inden güvenli).

    Pencere gizliyken de görünmesi gerekiyor; MB_TOPMOST + MB_SETFOREGROUND
    onu öne getiriyor. Windows dışı ya da diyalog kurulamayan durumda True:
    kullanıcının açık Çıkış jesti "çıkamıyorum" tuzağına dönüşmesin.

    SAHİP pencere veriliyor. Sahipsiz (hWnd=0) bir MessageBox kendi görev
    çubuğu düğmesini alıyor ve o düğmenin simgesi uygulamanınki değil,
    sürecin varsayılanı — yani Python'un yılan simgesi — oluyordu. Sahipli
    bir kutu ayrı düğme açmıyor. Pencere bulunamazsa (henüz doğmamış ya da
    yok edilmiş) 0'a düşüyoruz: yanlış simgeli bir soru, sorulmayan bir
    sorudan iyidir.
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        MB_YESNO = 0x0004
        MB_ICONWARNING = 0x0030
        MB_TOPMOST = 0x00040000
        MB_SETFOREGROUND = 0x00010000
        IDYES = 6
        try:
            sahipler = _dornick_windows(gizli_de=True)
        except Exception:
            sahipler = []
        answer = ctypes.windll.user32.MessageBoxW(
            sahipler[0] if sahipler else 0, question, WINDOW_TITLE,
            MB_YESNO | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND,
        )
        return answer == IDYES
    except Exception:
        return True


def _teardown(loop: asyncio.AbstractEventLoop, runtime: Runtime) -> None:
    for job in (runtime.ticker, runtime.greeter):
        if job is not None:
            loop.call_soon_threadsafe(job.cancel)
    if runtime.eyes is not None:
        runtime.eyes.stop()
    if runtime.lens is not None:
        runtime.lens.stop()
    if runtime.ear is not None:
        runtime.ear.stop()
    runtime.bridge.cancel_pending()
    # Açık MCP oturumları alt süreç tutuyor; kapatılmazsa hayalet kalıyor.
    pool = getattr(runtime.server._httpd, "connectors", None)
    if pool is not None:
        pool.close()
    runtime.server.stop()
    runtime.session.close()

    # Model yapılandırılmamış açılışta istemci hiç kurulmadı (bkz. _boot).
    if runtime.client is not None:
        closing = asyncio.run_coroutine_threadsafe(runtime.client.close(), loop)
        try:
            closing.result(timeout=5)
        except Exception:
            pass
    loop.call_soon_threadsafe(loop.stop)
