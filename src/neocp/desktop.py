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
import sys
import threading
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .backends import build_client
from . import (
    connectors as linking,
    ear as hearing,
    lmstudio,
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

WINDOW_TITLE = "neo"
WINDOW_BACKGROUND = "#0b0e14"

# Uyandirma taramasi icin kullanilan model. Kucuk ve hizli olmasi
# yeterli: aranan sey tek kelime.
SCOUT_SIZE = "base"

# Biri odaya girdiğinde ajana gidilen soru. Selam vermesi değil, **bakması**
# isteniyor: kim geldiğini görsün, tanıdıksa adıyla karşılasın.
# Adı çağrıldı ama arkasından bir şey söylenmedi ("neo"). Adı çağrılıp
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
_CLOSE_WORDS = ("kapat", "kapan", "görüşürüz", "hoşça kal", "hoşçakal",
                "iyi geceler", "sonra konuşuruz")

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


def _active_goals(agent: Any) -> list[dict[str, str]]:
    """Aktif hedeflerin arayüz dökümü (id + metin).

    Hedef paneli olay güdümlü (goal_push/goal_status) ama sayfa yenilenince
    olaylar kaçmış oluyor; snapshot bu listeyle panele kaldığı yeri veriyor.
    Zihin yoksa ya da okunamıyorsa boş liste — panel görünmez, sohbet düşmez.
    """
    mind = getattr(agent, "mind", None)
    if mind is None:
        return []
    try:
        return [
            {"id": g.id, "text": g.text}
            for g in mind.goals()[:GOAL_SNAPSHOT_LIMIT]
        ]
    except Exception:
        return []


# Yardımcı durumlarının arayüz dili. Defterde Türkçe halleri duruyor;
# panel tarafı olaylarla aynı kelimeleri (run/done/fail) bekliyor.
_KANAL_DURUM = {"kosuyor": "run", "bitti": "done", "yetim": "yetim"}


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


class Bridge:
    """Arayüz ile ajan arasındaki iki yönlü köprü.

    Controller yüzeyi HTTP thread'inden, AgentIO yüzeyi asyncio thread'inden
    çağrılır. İkisi arasındaki her geçiş açıkça işaretli.
    """

    def __init__(self, hub: Hub, loop: asyncio.AbstractEventLoop) -> None:
        self.hub = hub
        self.loop = loop
        self.agent: Agent | None = None
        # Oturum değiştirmek (yeni/devam) olay akışını yeni günlüğe bağlamayı
        # gerektiriyor; bunu sunucu yapıyor. _boot referansı sonradan veriyor.
        self.server: Any = None
        # Metin ve (varsa) kamera karesi birlikte kuyruğa giriyor.
        self.queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._pending: dict[str, Pending] = {}
        self._busy = False
        # Sürekli dinleyen kulak sonradan bağlanıyor: açılış sırasında
        # köprü ondan önce kuruluyor.
        self.ear: Any = None
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
        # Açılış sırasında nerede olunduğu. Model yüklenmeden konuşmak
        # anlamsız: arayüz bu bilgiyle giriş satırını kapalı tutuyor.
        self.stage = "uyanıyor"
        self.ready = False

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
        `_surdur` boşa model çağırmaz.
        """
        self.queue.put_nowait(_CHILD_DONE)

    def new_session(self) -> dict[str, Any]:
        """Taze bir konuşma başlatır: yeni oturum, boş bağlam."""
        return self._switch(None)

    def resume_session(self, sid: str) -> dict[str, Any]:
        """Geçmiş bir konuşmayı sürdürür: o oturumu aktif yapar, bağlamı
        (geçmiş mesajları) yükler ve yeni mesajlar oraya eklenir."""
        return self._switch(sid)

    def _switch(self, sid: str | None) -> dict[str, Any]:
        """Aktif oturumu değiştirir. sid None ise yeni, değilse o oturum.

        Yalnızca boştayken: akan bir turun altından oturumu çekmek cevabı
        ve bağlamı bozar. Değişiklik hem ajanı (oturum + zihin kimliği) hem
        de sunucuyu (olay akışını yeni günlüğe bağla) etkiliyor; arayüz
        `session_reset` ile eski dökümü temizleyip yenisini gösteriyor.
        """
        agent = self.agent
        if agent is None or self.server is None:
            return {"ok": False, "error": "henüz hazır değil"}
        if self._busy:
            return {"ok": False, "error": "neo meşgul; tur bitince dene", "busy": True}

        from pathlib import Path

        from .events import EventLog
        from .session import Session

        sessions_dir = agent.config.sessions_dir
        if sid:
            path = Path(sessions_dir) / f"{sid}.jsonl"
            if not path.is_file():
                return {"ok": False, "error": "oturum bulunamadı"}
            session = Session(EventLog(path), sid)
            resumed = True
        else:
            session = Session.create(sessions_dir)
            resumed = False

        agent.session = session
        agent.mind.session_id = session.id
        agent._last_encoded = ""      # yeni oturumda anlık-encode tekrarını sıfırla
        self.server.rebind(session)
        self.hub.emit({"type": "session_reset", "id": session.id, "resumed": resumed})
        return {"ok": True, "id": session.id, "resumed": resumed}

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
        yapılmıyor. Turun ortasındaysak değişiklik tur bitene kadar
        bekliyor: akan bir istemciyi altından çekmek o cevabı öldürür.
        """
        agent = self.agent
        if agent is None:
            return

        was = agent.permissions.mode
        before = agent.config.model
        agent.permissions = PermissionEngine.from_config(config.permissions)

        if was != config.permissions.mode:
            self.hub.emit({"type": "notice", "text": f"İzin kipi: {config.permissions.mode}"})
            # Dock çipi ve plan-onay düğmesi gerçek kipi göstersin: ayar
            # sayfası DIŞINDAN (başka sekme, dış kapı) değişen kip de
            # arayüze olay olarak düşmeli — notice metni makine okunur değil.
            self.hub.emit({"type": "mode", "mode": config.permissions.mode})

        model_changed = before != config.model
        if model_changed or force:
            # İstemci (ve onunla birlikte sistem promptu) yeniden kuruluyor;
            # tur ortasındaysak tur bitene kadar bekliyor.
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
        note = self._swap_note or f"Model değişti: {wanted.name}."
        self._swap_note = ""
        self.hub.emit({"type": "notice", "text": note})
        self.loop.call_soon_threadsafe(lambda: self.loop.create_task(_retire(old)))

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
        return {
            "busy": self._busy,
            "ready": self.ready,
            "stage": self.stage,
            "session": agent.session.id if agent else "",
            "model": agent.config.model.name if agent else "",
            "provider": agent.config.model.provider if agent else "",
            # Kompozer altındaki şerit için: düşünme derinliği ve bağlam
            # penceresi. Pencere olmadan kullanım yüzdesi hesaplanamıyor.
            "effort": agent.config.model.effort if agent else "",
            "context_window": int(agent.config.model.context_window) if agent else 0,
            # Son turun istem toplamı: sayfa yenilenince bağlam göstergesi
            # sıfırdan değil kaldığı yerden başlasın.
            "prompt_total": int((getattr(agent, "_last_usage", None) or {}).get("prompt_total") or 0) if agent else 0,
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
            "camera": bool(agent and agent.config.camera.enabled),
            "tools": len(agent.registry) if agent else 0,
        }

    # -- asyncio thread ------------------------------------------------

    def io(self) -> AgentIO:
        return AgentIO(
            on_text=lambda chunk: self.hub.emit({"type": "assistant_delta", "text": chunk}),
            on_thinking=lambda chunk: self.hub.emit({"type": "thinking_delta", "text": chunk}),
            on_notice=lambda text: self.hub.emit({"type": "notice", "text": text}),
            on_usage=lambda report: self.hub.emit({"type": "usage", **report}),
            # Orkestra kanalları: alt ajanlar canlı görünsün (şef modu).
            on_child_start=lambda title, model, cid, bg=False: self.hub.emit(
                {"type": "child_start", "title": title, "model": model, "id": cid,
                 "bg": bool(bg)}),
            on_child_tool=lambda title, tool, phase: self.hub.emit(
                {"type": "child_tool", "title": title, "tool": tool, "phase": phase}),
            on_child_end=lambda title, ok, turns, tools, cid="", ozet="": self.hub.emit(
                {"type": "child_end", "title": title, "ok": ok, "turns": turns,
                 "tools": tools, "id": cid, "ozet": ozet}),
            approve=self._approve,
        )

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
        """Arayüzden gelen mesajları sırayla ajana verir."""
        while True:
            item = await self.queue.get()
            if self.agent is None:
                continue
            if item is _CHILD_DONE:
                await self._surdur()
                continue
            if item is _PARK_RESUME:
                await self._park_surdur()
                continue
            text, image = item
            await self._isle(text, image)

    async def _park_surdur(self) -> None:
        """Park edilmiş (yarım kalmış) koşuyu kaldığı yerden sürdürür.

        Açılışta park kaydı bulunduğunda kuyruğa düşen işaretin karşılığı.
        `resume_after_interrupt` karşılıksız tool_use'ları kapatıp döngüyü
        yeniden sürer; model hâlâ ulaşılamıyorsa aynı koşu içinde yeniden
        deneme/park zinciri zaten devrede.
        """
        agent = self.agent
        if agent is None:
            return
        self._busy = True
        self.hub.emit({"type": "status", "busy": True})
        try:
            await agent.resume_after_interrupt()
        except Exception as exc:  # sürdürme uygulamayı düşürmemeli
            self.hub.emit({"type": "notice", "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._busy = False
            if self._wanted_model is not None:
                self._swap_model()
            self.hub.emit({"type": "status", "busy": False})
            self.hub.emit({"type": "turn_end"})

    async def _surdur(self) -> None:
        """Bir yardımcı bitti ve ajan boşta: sonucu değerlendiren tur.

        Bildirilecek bir şey kalmadıysa (sonuç koşan turun başında zaten
        verildiyse) model hiç çağrılmaz — sessizce geçilir.
        """
        agent = self.agent
        if agent is None or not agent.has_unreported_children():
            return
        self._busy = True
        self.hub.emit({"type": "status", "busy": True})
        try:
            await agent.resume_for_children()
        except Exception as exc:  # sürdürme turu uygulamayı düşürmemeli
            self.hub.emit({"type": "notice", "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._busy = False
            if self._wanted_model is not None:
                self._swap_model()
            self.hub.emit({"type": "status", "busy": False})
            self.hub.emit({"type": "turn_end"})

    async def _isle(self, text: str, image: str) -> None:
        """Tek mesajı işler.

        pump'tan ayrı durması bilinçli: testler bir turu kuyruk ve sonsuz
        döngüye bulaşmadan koşturabiliyor.
        """
        self._busy = True
        self.hub.emit({"type": "status", "busy": True})
        try:
            # İlk kurulum: hiçbir sağlayıcı kullanılabilir değilken model
            # HİÇ çağrılmıyor — cevapsız kalan ya da anlaşılmaz bir API
            # hatasıyla biten bir mesaj yerine, sohbete yol gösteren bir
            # asistan mesajı düşüyor. Kullanıcı tekrar yazarsa yeniden
            # hatırlatılıyor; ama bir mesaj bir kez cevaplanıyor.
            if settings.yapilandirilmamis(self.agent.config.model):
                self.agent.session.add_user_text(text)
                self.agent.session.add_assistant(
                    [{"type": "text", "text": settings.KURULUM_YONLENDIRME}]
                )
                self.hub.emit(
                    {"type": "setup_hint", "text": settings.KURULUM_YONLENDIRME}
                )
                return
            await self.agent.run(text, image)
        except Exception as exc:  # ajan bir istekte patlarsa uygulama ölmemeli
            self.hub.emit({"type": "notice", "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._busy = False
            # Karşılık verildi: sohbet açık. Bu süre boyunca söylenen
            # her şey ona söylenmiş sayılıyor, adını tekrarlamak
            # gerekmiyor — karşındaki insana da her cümlede adıyla
            # başlamıyorsun.
            if self.ear is not None:
                self.ear.engage()
            # Tur sırasında model değiştirilmişse şimdi geçiliyor.
            if self._wanted_model is not None:
                self._swap_model()
            self.hub.emit({"type": "status", "busy": False})
            self.hub.emit({"type": "turn_end"})


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

        # "neo ile kes": neo konuşurken uyandırma sözüyle araya girildi —
        # önce konuşmayı sustur (arayüz TTS'i durduruyor), sonra komut normal
        # akışa (kuyruk) giriyor.
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
            # ucuz, yanlış cevap pahalı — kullanıcı isterse "neo" der.
            if ear is not None:
                ear.disengage()
            hub.emit({"type": "notice",
                      "text": "Sohbet kapandı — adıyla yeniden açılır."})
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
    if not ear.start():
        return None
    how = "serbest dinleme" if config.listen.open else f"'{config.listen.wake}' ile uyanır"
    print(f"[neo] kulak açık — {how}", flush=True)
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

    Sessizce başarısız oluyor: LM Studio yoksa uçlar da yok ve bu normal.
    """
    if config.model.provider != "openai":
        return

    url = config.model.base_url
    for gone in lmstudio.drop_duplicates(url, config.model.name):
        print(f"[neo] fazla kopya kaldırıldı: {gone}", flush=True)

    # keep_loaded ayarlanmışsa onu, yoksa cömert bir varsayılan (30 dk) TTL
    # veriyoruz: LM Studio kendi varsayılanıyla modeli çabuk boşaltıp sonraki
    # isteği "Model unloaded" ile düşürüyordu. Böylece konuşma sürerken model
    # yüklü kalıyor.
    ttl = config.model.keep_loaded or 1800
    result = lmstudio.ensure_loaded(url, config.model.name, config.model.context_window, ttl=ttl)
    if result.get("state") == "loaded":
        print(f"[neo] model {result['context']} token pencereyle yüklendi "
              f"({result.get('seconds', 0):.1f} sn)")
    elif result.get("state") == "capped":
        print(f"[neo] pencere modelin sınırına çekildi: {result['context']}", flush=True)

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
        print(f"[neo] bağlam penceresi gerçeğe göre ayarlandı: {actual}", flush=True)


async def _boot(config: Config, port: int, resume: bool) -> Runtime:
    """Uygulamayı ayağa kaldırır.

    Sıra bilinçli: sunucu **önce** açılıyor, ağır işler sonra. Böylece
    pencere hemen görünüyor ve model yüklenirken boş bir ekrana değil,
    uyanma sırasına bakılıyor. Model hazır olmadan giriş satırı kapalı
    kalıyor — hazır olmayan bir ajana yazmak cevapsız kalmak demek.
    """
    config.ensure_dirs()
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
    skills.seed(config.open_sandbox().root)
    learned, broken = skills.discover(config.open_sandbox().root)
    added, _updated = skills.register(registry, learned)
    if added:
        print(f"[neo] yetenekler yüklendi: {', '.join(added)}", flush=True)
    for problem in broken:
        print(f"[neo] yetenek yüklenemedi: {problem.splitlines()[0]}", flush=True)

    # MCP bağlayıcıları arka planda bağlanıyor: `npx` ilk seferde paket
    # indirebiliyor ve açılış bunu beklememeli. Bağlanınca araçlar canlı
    # deftere düşüyor — bir sonraki tur onları görüyor.
    pool = linking.Pool()
    server._httpd.connectors = pool  # type: ignore[attr-defined]

    def _connect_mcp() -> None:
        found, problems = linking.load(config.state_dir)
        for problem in problems:
            print(f"[neo] bağlayıcı: {problem}", flush=True)
        if not found:
            return
        pool.connect(found, config.state_dir)
        fresh, _gone = linking.register(registry, pool)
        if fresh:
            print(f"[neo] MCP araçları: {', '.join(fresh)}", flush=True)
        for state in pool.status():
            if not state["ok"] and state["error"]:
                hub.emit({"type": "notice",
                          "text": f"Bağlayıcı {state['name']}: {state['error']}"})

    threading.Thread(target=_connect_mcp, daemon=True, name="neo-mcp").start()

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
        print(f"[neo] model istemcisi kurulamadı: {exc}", flush=True)
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
        # sonucu değerlendiren bir sürdürme turu açılır.
        agent.on_children_settled = bridge.child_done
        # Model kesintisinde her yeniden denemeden önce bekleyen ayar/model
        # değişikliği uygulansın: bozuk adres/anahtar düzeltildiğinde parklı
        # koşu yeni istemciyle sürebilsin (normalde değişim tur sonunu
        # bekler; parklı tur hiç bitmez).
        agent.on_retry_wait = bridge._swap_model
    bridge.agent = agent

    # Sürekli dinleme Python tarafında: tarayıcıda duramıyor çünkü pencere
    # gizlendiğinde Chromium arka plan zamanlayıcılarını dakikaya kısıyor ve
    # dinleme ölüyor. Burada tepside dururken de çalışıyor.
    ear = None
    if config.listen.enabled and config.listen.wake.strip() and hearing.available():
        bridge.waking("kulak açılıyor")
        ear = _open_ear(config, bridge, hub)
        # Konuşurken kulağı kapatabilmek için sunucunun ona erişmesi
        # gerekiyor.
        server._httpd.ear = ear  # type: ignore[attr-defined]
        # Tur bitince sohbet penceresini açan taraf köprü.
        bridge.ear = ear
        # `hearing` aracı kulağa ajanın içinden erişiyor: kullanıcı "beni
        # dinleme" dediğinde ajan gerçekten kapatabilmeli.
        if bridge.agent is not None:
            bridge.agent.ear = ear

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
            print("[neo] kamera tamponu açık", flush=True)
        else:
            lens = None

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

    # Zamanlayıcı ajanın döngüsünde koşuyor: tetiklenen görev doğrudan
    # çalışmıyor, kullanıcının mesaj kuyruğuna giriyor. Böylece ajan bir
    # işin ortasındayken araya girmiyor ve çıktı normal bir tur gibi akıyor.
    def fire(task: Any) -> None:
        hub.emit({"type": "notice", "text": f"Zamanlanmış görev: {task.title}"})
        book.note_run(task.id, "kuyruğa alındı")
        # `siraya`: zamanlanmış görev koşan bir turun ortasına karışmaz,
        # kendi turunu bekler — araya girme kullanıcının jesti.
        bridge.submit(task.prompt, siraya=True)

    ticker = loop.create_task(scheduling.run_forever(book, fire))

    # Geliş: uzun bir sessizlikten sonra biri odaya girdiğinde ajan bir kez
    # bakıyor. Küçük bir çocuk gibi — kimse yokken kendini beklemeye alıyor,
    # bir şey kımıldayınca kim geldiğine bakıyor.
    async def greet() -> None:
        while True:
            await asyncio.sleep(2.0)
            box = getattr(bridge.agent, "lens", None) if bridge.agent else None
            if box is not None and not bridge.busy and box.arrival():
                bridge.submit(GREET_ASK)

    greeter = loop.create_task(greet())

    # Kameralar arka planda izleniyor. Model her kareye bakmıyor: hareket
    # yerelde ölçülüyor ve yalnızca bir şey değiştiğinde soru soruluyor.
    # Boş bir odada saatlerce hiçbir istek gitmiyor.
    def seen(sighting: watching.Sighting) -> None:
        hub.emit({
            "type": "notice",
            "text": f"{sighting.camera.name}: hareket (%{int(sighting.change * 100)})",
        })
        bridge.submit(f"[{sighting.camera.name}] {sighting.ask}", sighting.frame)

    eyes = watching.Watcher(watching.load(config.state_dir), seen)
    # "Beni izleme" ağ kameralarını da kapsıyor; sesleniş hepsini geri
    # açıyor. Kulak, göz ve izleyici tek bir "duyular" bütünü.
    if bridge.agent is not None:
        bridge.agent.watcher = eyes
    if ear is not None:
        ear.companions = [s for s in (lens, eyes) if s is not None]
    if eyes.start():
        print(f"[neo] {len(watching.load(config.state_dir))} kamera izleniyor", flush=True)

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
        ear=ear,
    )


def _kill_ghosts() -> None:
    """Bu makinedeki DİĞER neo masaüstü örneklerini kapatır.

    Ölçüt komut satırı: python + ("neocp" ve "--app"). Kendi sürecimiz ve
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
             "Name='pythonw.exe'\" | Select-Object ProcessId,CommandLine | "
             "ConvertTo-Json"],
            capture_output=True, text=True, timeout=10, encoding="utf-8",
            errors="replace", **ortam.sessiz_bayraklar(),
        ).stdout
        rows = json.loads(out or "[]")
        if isinstance(rows, dict):
            rows = [rows]
        me = os.getpid()
        for row in rows:
            pid = row.get("ProcessId")
            cmd = (row.get("CommandLine") or "").lower()
            if not pid or pid == me:
                continue
            if "neocp" in cmd and ("--app" in cmd or "desktop" in cmd):
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True,
                               **ortam.sessiz_bayraklar())
                print(f"[neo] eski örnek kapatıldı (PID {pid})", flush=True)
    except Exception:
        pass


def run(config: Config, *, port: int = 8765, resume: bool = False) -> int:
    """Pencereyi açar ve kapanana kadar bloke eder."""
    # Görev çubuğu kimliği: bu ayarlanmazsa Windows pencereyi python.exe'nin
    # grubunda gösteriyor ve simge PYTHON logosu kalıyordu. Kendi kimliğiyle
    # gruplanınca pencerenin kendi simgesi (neo logosu) görünür.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("fatih.neo.app")
        except Exception:
            pass

    # HAYALET AVI: tepside gizli kalmış eski neo örnekleri portu ve pencere
    # hedeflemesini ele geçirip yeni örneği sağır bırakıyordu — kullanıcı
    # "kapattım açtım" dedikçe hayaletler çoğalıyor, hiçbir düzeltme ekrana
    # ulaşmıyordu (üç günlük yaranın gerçek kökü). Yeni örnek açılırken
    # eskileri tek tek kapatır: her açılış temiz, tek örnek.
    _kill_ghosts()
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
            "Masaüstü penceresi için pywebview gerekli: pip install 'neocp[app]'"
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

    thread = threading.Thread(target=spin, daemon=True, name="neocp-agent")
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
    window = webview.create_window(
        WINDOW_TITLE,
        runtime.url,
        width=1360,
        height=880,
        min_size=(900, 600),
        background_color=WINDOW_BACKGROUND,
        frameless=True,
        # Varsayılan True: TÜM istemci alanı sürükleme bölgesi olur — kullanıcı
        # beyinden / sohbetten tutup pencereyi taşıyordu. Taşıma yalnız üst
        # şeritten (chrome.js → HTCAPTION); snap de o yoldan geliyor.
        easy_drag=False,
    )
    # Kapatma penceresi gizliyor, yok etmiyor: ajanın arka planda durması
    # gereken işleri var (zamanlanmış görevler, kameraları izleyen alt
    # ajanlar, uyandırma sözünü bekleyen mikrofon). Tepsi yoksa kapatma
    # gerçekten kapatıyor — yoksa program kapanmaz hale gelirdi.
    tray = tray_module.Tray(
        show=lambda: window.show(),
        hide=lambda: window.hide(),
        quit=lambda: window.destroy(),
    )
    live = tray.start()

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

    # Tepsiye gizlenmek yalnızca arka planda gerçek bir iş varken anlamlı:
    # kulak (sürekli dinleme) açık. Kapalıyken X'in gizlemesi hayalet süreç
    # üretiyordu — kullanıcı kapandı sanıyor, eski kod portu tutup yeni
    # açılışları sabote ediyordu.
    hide_on_close = live and config.listen.enabled

    def close() -> None:
        if hide_on_close:
            window.hide()
        else:
            window.destroy()

    for fn in (minimize, maximize, drag, resize, close, is_zoomed):
        window.expose(fn)

    # Native kapatma (X) programı YOK ETMESİN, tepsiye gizlesin: ajanın arka
    # planda işleri var (zamanlanmış görevler, kamera izleyen alt ajanlar,
    # uyandırma sözünü bekleyen mikrofon). Tepsi yoksa normal kapanış geçerli.
    if hide_on_close:
        def _hide_instead_of_close() -> bool:
            window.hide()
            return False   # kapatmayı iptal et

        try:
            window.events.closing += _hide_instead_of_close
        except Exception:
            pass

    # Uyandırma sözü duyulduğunda pencere geri geliyor: gizliyken de sayfa
    # çalışmaya devam ediyor, mikrofon dinliyor.
    runtime.bridge.on_wake = lambda: window.show()

    if hide_on_close:
        print("[neo] tepside çalışıyor — pencereyi kapatmak programı kapatmaz", flush=True)
    elif live:
        print("[neo] tepsi açık; pencereyi kapatmak programı da kapatır", flush=True)

    try:
        # Pencere/görev çubuğu simgesi: tek kaynak logodan (tepsi ve sekmeyle
        # aynı işaret). pywebview winforms bunu form.Icon yapıyor.
        from . import logo as logo_module
        webview.start(_titlebar_boot, icon=str(logo_module.ico_path()))
    finally:
        tray.stop()
        _teardown(loop, runtime)
    return 0


def _titlebar_boot() -> None:
    """webview başladıktan sonra çalışır: pencere oluşana dek dener.

    Tek şerit: CAPTION+THICKFRAME stilleri yerinde (snap), WM_NCCALCSIZE üst
    payı istemciye (OS şeridi görünmez), WM_NCHITTEST kenar tutamakları.
    """
    import time
    for _ in range(40):
        if _apply_native_styles():
            _install_shell()
            _update_max_bounds()
            paint_titlebar(True)
            return
        time.sleep(0.15)


# Ana pencere referansı: pencere-kabuk yardımcıları (MaximizedBounds) için.
_MAIN_WINDOW: Any = None

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
    try:
        import ctypes
        from ctypes import wintypes

        u = _user32()
        targets = _neo_windows()
        if not targets:
            return False
        hwnd = targets[0]
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
                        if mon and u.GetMonitorInfoW(mon, ctypes.byref(mi)):
                            p.rgrc[0].left = mi.rcWork.left
                            p.rgrc[0].top = mi.rcWork.top
                            p.rgrc[0].right = mi.rcWork.right
                            p.rgrc[0].bottom = mi.rcWork.bottom
                        else:
                            # Yedek: klasik 8px içe al.
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


def _update_max_bounds() -> None:
    """Büyütme sınırını o anki monitörün ÇALIŞMA ALANINA ayarlar.

    Çerçevesiz bir pencereyi Windows tam ekrana (görev çubuğunun üstüne)
    büyütür — kullanıcının en başta şikayet ettiği davranış. WinForms'un
    MaximizedBounds özelliği bunu kökünden çözüyor: Win+Yukarı, üst kenara
    snap ve bizim düğmemiz dahil HER büyütme yolu bu sınırı kullanır.
    Pencere hangi monitördeyse onun çalışma alanı; her sürüklemeden sonra
    tazeleniyor ki monitör değişimi doğru kalsın.
    """
    window = _MAIN_WINDOW
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
        import ctypes

        user32 = ctypes.windll.user32
        targets = _neo_windows()
        if not targets:
            return False
        for hwnd in targets:
            style = user32.GetWindowLongW(hwnd, _GWL_STYLE)
            # CAPTION + THICKFRAME: snap önizlemesi ve yerleşim için ikisi de
            # gerekli (yalnız THICKFRAME yetmiyor — canlı A/B ile kanıtlandı).
            # Görsel payı kabuk (NCCALCSIZE üst yutma) alıyor; kenarda çizgi yok.
            style |= (
                _WS_CAPTION
                | _WS_THICKFRAME
                | _WS_MINIMIZEBOX
                | _WS_MAXIMIZEBOX
                | _WS_SYSMENU
            )
            user32.SetWindowLongW(hwnd, _GWL_STYLE, style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_FRAMECHANGED)
            # Yuvarlak köşe (Win11 22000+): DWMWA_WINDOW_CORNER_PREFERENCE=33,
            # DWMWCP_ROUND=2. Eski sürüm sessizce yok sayar.
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


def _is_zoomed() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        targets = _neo_windows()
        return bool(targets and ctypes.windll.user32.IsZoomed(targets[0]))
    except Exception:
        return False


def _win_do(action: str) -> bool:
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
        targets = _neo_windows()
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
            window = _MAIN_WINDOW
            form = getattr(window, "native", None) if window is not None else None
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


def _neo_windows() -> list[int]:
    """Bu süreçte 'neo' başlıklı görünür top-level pencerelerin HWND'leri.

    FindWindowW(None, title) tek bir eşleşme döndürüyor ve bazı kurulumlarda
    hiç bulamıyordu; EnumWindows tüm eşleşmeleri güvenle veriyor (canlı
    pencerede kanıtlandı).
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []
    my_pid = os.getpid()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        # YALNIZCA bu sürecin penceresi: iki neo örneği açıkken (ya da bir
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
        targets = _neo_windows()
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
    """Ekranın görev çubuğu hariç alanı (x, y, genişlik, yükseklik).

    Windows'ta SPI_GETWORKAREA. Çerçevesiz bir pencereyi `maximize()` ile
    büyütmek tüm monitörü (görev çubuğu dahil) kaplıyor; onun yerine pencereyi
    bu alana taşıyıp boyutlandırıyoruz — "senin gibi" normal, görev çubuğuna
    saygılı bir büyütme.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        SPI_GETWORKAREA = 0x0030
        if not ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
        ):
            return None
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    except Exception:
        return None


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

    return wake


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
