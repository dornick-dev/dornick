"""Zihin arayüzü sunucusu.

Bilinçli olarak yalnızca standart kütüphane: ne aiohttp, ne uvicorn, ne npm.
Canlı akış için WebSocket yerine SSE kullanılıyor — tek yönlü bir akış için
yeterli ve düz HTTP üzerinde çalıştığı için ek bağımlılık gerektirmiyor.

Sunucu ayrı bir thread'de döner; ajan asyncio döngüsünde çalışmaya devam
eder. İkisi arasındaki tek köprü olay günlüğünün abonelik kancası.

Yalnızca 127.0.0.1'e bağlanır. Burada ajanın belleği, hedefleri ve geçmiş
oturumları var — dışarı açılacak bir yüzey değil.
"""

from __future__ import annotations

import asyncio
import json
import queue
import re
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any, Protocol

from .. import listen, schedule as scheduling, settings, tanima, voice, watch
from ..config import Config
from ..events import Event, EventLog
from ..mind.store import Mind
from . import gate
from .graph import build_graph

STATIC = Path(__file__).parent / "static"
HEARTBEAT_S = 15.0
QUEUE_LIMIT = 500

# Servis edilen dosyalar açıkça listeleniyor: yol birleştirmeyi istekten
# türetmek dizin dışına çıkma açığının klasik yolu.
ASSETS = {
    "/app.css": "text/css; charset=utf-8",
    "/logo.png": "image/png",
    "/app.js": "text/javascript; charset=utf-8",
    # Dil katmanı: diğer betiklerden ÖNCE yüklenir (t() ve Dil.ekle onlarda).
    "/dil.js": "text/javascript; charset=utf-8",
    "/scene.js": "text/javascript; charset=utf-8",
    # Gerçek beyin geometrisi: seyreltilmiş nokta bulutu, 42 KB.
    "/brain.js": "text/javascript; charset=utf-8",
    "/md.js": "text/javascript; charset=utf-8",
    "/highlight.js": "text/javascript; charset=utf-8",
    "/settings.js": "text/javascript; charset=utf-8",
    "/viewer.js": "text/javascript; charset=utf-8",
    "/apps.js": "text/javascript; charset=utf-8",
    "/capsule.js": "text/javascript; charset=utf-8",
    "/history.js": "text/javascript; charset=utf-8",
    "/orchestra.js": "text/javascript; charset=utf-8",
    "/chrome.js": "text/javascript; charset=utf-8",
    "/speech.js": "text/javascript; charset=utf-8",
    "/listen.js": "text/javascript; charset=utf-8",
    "/camera.js": "text/javascript; charset=utf-8",
    "/drop.js": "text/javascript; charset=utf-8",
}

# Arayüze akıtılan meta olaylar. Gerisi (oturum başlangıcı, izin kaydı gibi)
# grafı kalabalıklaştırmaktan başka işe yaramıyor.
STREAMED_NOTES = frozenset(
    {
        "tool_start",
        "tool_end",
        "tool_cancelled",
        "permission",
        "goal_push",
        "goal_status",
        "mind_write",
        "mind_forget",
        "mind_link",
        "api_error",
        "interrupted",
        "empty_assistant_turn",
        "turn_limit",
        "refusal",
        "recall_trace",
        "queued",
    }
)


class Controller(Protocol):
    """Arayüzün ajanı sürmek için kullandığı yüzey.

    HTTP thread'inden çağrılır, ajan başka bir thread'in asyncio döngüsünde
    çalışır. Geçişi thread-safe yapmak uygulayanın sorumluluğu.
    """

    def submit(self, text: str, image: str = "") -> None: ...
    def resolve_approval(
        self, request_id: str, granted: bool, *, always: bool = False
    ) -> None: ...
    def interrupt(self) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...
    def reload(self, config: Config, *, force: bool = False) -> None: ...


class Hub:
    """Olay günlüğünü açık tarayıcı sekmelerine dağıtır."""

    def __init__(self) -> None:
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()

    def register(self) -> queue.Queue[str]:
        channel: queue.Queue[str] = queue.Queue(maxsize=QUEUE_LIMIT)
        with self._lock:
            self._clients.append(channel)
        return channel

    def unregister(self, channel: queue.Queue[str]) -> None:
        with self._lock:
            if channel in self._clients:
                self._clients.remove(channel)

    def publish(self, event: Event) -> None:
        if (payload := _payload(event)) is not None:
            self.emit(payload)

    def emit(self, payload: dict[str, Any]) -> None:
        """Günlükten gelmeyen olayları da yayınlar (metin akışı, onay isteği)."""
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            clients = tuple(self._clients)
        for channel in clients:
            try:
                channel.put_nowait(line)
            except queue.Full:
                # Yavaş sekme ajanı yavaşlatmasın; o sekme birkaç olay kaçırır.
                pass


def _payload(event: Event) -> dict[str, Any] | None:
    if event.kind == "message":
        # Araç sonuçları teknik olarak kullanıcı turudur ama sohbette
        # kullanıcı mesajı gibi görünmemeli — araç kartı zaten sonucu
        # gösteriyor.
        if event.meta.get("tool_results"):
            return None
        # Sürdürme dürtüsünü de kullanıcı yazmadı; sohbette görünmemeli.
        # Aynısı araçtan gelen görüntü ve harness notları için de geçerli.
        if event.meta.get("continuation") or event.meta.get("internal"):
            return None
        return {
            "type": "message",
            "role": event.role,
            "ts": event.ts,
            "text": _summarize(event.content),
        }
    if event.content in STREAMED_NOTES:
        return {"type": str(event.content), "ts": event.ts, **event.meta}
    return None


def _summarize(content: Any, limit: int = 400) -> str:
    if isinstance(content, str):
        return content[:limit]
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append(str(block.get("text", "")))
        elif kind == "tool_use":
            parts.append(f"→ {block.get('name')}")
        elif kind == "tool_result":
            parts.append("← sonuç")
    return " ".join(parts)[:limit]


# Bu boyutun üstündeki dosyanın gövdesi gönderilmiyor. Amaç ajanın ürettiği
# betiği/raporu göz atmak; bir veri dökümünü tarayıcıya yıkmak değil.
PREVIEW_LIMIT = 256 * 1024

# Sohbete bırakılabilecek azami dosya. Tarayıcı içeriği base64 ile
# taşıyor (üçte bir şişme) ve bellekte tutuluyor.
DROP_LIMIT = 25 * 1024 * 1024

# Gövdesi gösterilmeyecek uzantılar. Listede olmayan her şey metin gibi
# okunmaya çalışılıyor; çözülemezse ikili sayılıyor.
BINARY_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
     ".exe", ".dll", ".so", ".dylib", ".db", ".sqlite", ".wasm"}
)

# Gezinmede atlanan dizinler: ajanın ürettiği değil, araçların bıraktığı şeyler.
SKIPPED = frozenset({".git", "__pycache__", "node_modules", ".venv", ".mypy_cache"})


def warm_ear(server: Any, config: Config) -> None:
    """Tanıma modelini arka planda yükler.

    İlk çağrıya bırakılırsa o çağrı modeli indirirken (bir kez, ~70 sn) HTTP
    thread'ini tutuyor. Arka planda dinleme açıkken üç saniyede bir yeni
    istek geliyor ve hepsi aynı yerde birikiyor: tarayıcının bir kaynağa
    açabildiği altı bağlantı doluyor ve **her şey** sıraya giriyor —
    kullanıcının yazdığı mesaj bile gitmiyor.
    """
    if not config.listen.enabled or not listen.available():
        return

    def warm() -> None:
        try:
            _ear(server, config).load()
        except Exception:
            # Model inmediyse ilk gerçek istekte yeniden denenir.
            pass

    threading.Thread(target=warm, daemon=True, name="neo-ear").start()


def _ear(server: Any, config: Config) -> Any:
    """Tanıyıcıyı bir kez kurup saklar.

    Model her çağrıda yeniden yüklenirse bas-konuş kullanılamaz hale geliyor:
    her seferinde saniyeler. Ayar değişirse yeniden kuruluyor.
    """
    if not listen.available():
        return None
    ear = getattr(server, "_ear", None)
    if ear is None or ear.config != config.listen:
        ear = listen.Listener(config.listen)
        server._ear = ear  # type: ignore[attr-defined]
    return ear


def _as_json(raw: bytes) -> dict[str, Any]:
    """Gövdeyi JSON olarak okur. Değilse boş sözlük.

    Ses gibi ham gövdeler de aynı yoldan geçiyor; onlarda ayrıştırma
    başarısız oluyor ve olması gerektiği gibi.
    """
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8")) or {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _session_title(digest: str) -> str:
    """Konuşmanın başlığı: dijestin ilk birkaç kelimesi.

    Ayrı bir başlık üretmek için LLM çağırmak — her oturum için bir istek —
    pahalı ve gereksiz; ilk söz zaten konuyu veriyor.
    """
    flat = " ".join((digest or "").split())
    if not flat:
        return "(boş konuşma)"
    words = flat.split(" ")[:8]
    title = " ".join(words)
    return title if len(title) <= 60 else title[:60] + "…"


def _stem_date(stem: str) -> str:
    """20260610T090000Z -> 2026-06-10 09:00. Tanınmayanı olduğu gibi bırakır."""
    m = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})", stem or "")
    if not m:
        return stem
    y, mo, d, h, mi = m.groups()
    return f"{y}-{mo}-{d} {h}:{mi}"


def _relative(path: Path, root: Path) -> str:
    return "" if path == root else path.relative_to(root).as_posix()


def _listing(directory: Path, root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    try:
        children = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return entries

    for child in children:
        if child.name in SKIPPED:
            continue
        try:
            info = child.stat()
        except OSError:
            continue
        entries.append({
            "name": child.name,
            "path": _relative(child, root),
            "dir": child.is_dir(),
            "size": 0 if child.is_dir() else info.st_size,
            "mtime": int(info.st_mtime),
        })
    return entries


def _file_payload(path: Path, root: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": _relative(path, root),
        "name": path.name,
        "file": True,
        "size": path.stat().st_size,
    }
    if path.suffix.lower() in BINARY_SUFFIXES:
        payload["binary"] = True
        return payload
    if payload["size"] > PREVIEW_LIMIT:
        payload["truncated"] = True

    try:
        payload["text"] = path.read_bytes()[:PREVIEW_LIMIT].decode("utf-8")
    except (OSError, UnicodeDecodeError):
        payload["binary"] = True
    return payload


class MindServer:
    def __init__(
        self,
        mind: Mind,
        log: EventLog,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        controller: Controller | None = None,
        hub: Hub | None = None,
        config: Config | None = None,
        schedule: Any = None,
    ) -> None:
        self.mind = mind
        # Ayar sayfasi buradan okuyup buraya yaziyor. Yoksa sayfa
        # acilmiyor — ajansiz calisan bir arayuz onizlemesinde oldugu gibi.
        self.config = config
        # Zamanlanmış görevler: ajanın kurduğu bir otomasyon kullanıcıdan
        # gizli çalışmamalı, o yüzden arayüzden de yönetilebiliyor.
        self.schedule = schedule
        # Hub dışarıdan verilebilmeli: masaüstü köprüsü kendi olaylarını
        # (metin akışı, onay isteği) aynı kanaldan yayınlıyor. Sunucu kendi
        # hub'ını kurup sonradan değiştirmek abonelik ile yayını ayırır ve
        # günlükten gelen olaylar sessizce kaybolur.
        self.hub = hub or Hub()
        self._unsubscribe = log.subscribe(self.hub.publish)
        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        self._httpd.daemon_threads = True
        # Handler'lar server üzerinden erişiyor.
        self._httpd.mind = mind  # type: ignore[attr-defined]
        self._httpd.hub = self.hub  # type: ignore[attr-defined]
        self._httpd.controller = controller  # type: ignore[attr-defined]
        self._httpd.config = config  # type: ignore[attr-defined]
        self._httpd.schedule = schedule  # type: ignore[attr-defined]
        # Sürekli dinleyen kulak ve kamera tamponu sonradan bağlanıyor:
        # açılış sırasında sunucu ikisinden de önce ayağa kalkıyor.
        self._httpd.ear = None  # type: ignore[attr-defined]
        self._httpd.lens = None  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def rebind(self, session: Any) -> None:
        """Olay akışını yeni bir oturumun günlüğüne bağlar.

        Yeni ya da devam eden bir konuşmaya geçildiğinde SSE akışı eski
        günlüğü dinlemeye devam ederse yeni mesajlar arayüze hiç ulaşmıyor.
        Eski abonelik bırakılıp yenisi kuruluyor; zihnin oturum kimliği de
        güncelleniyor ki yeni anılar doğru oturuma yazılsın.
        """
        try:
            self._unsubscribe()
        except Exception:
            pass
        self._unsubscribe = session.log.subscribe(self.hub.publish)
        self.mind.session_id = session.id
        self._httpd.mind = self.mind  # type: ignore[attr-defined]

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}/"

    def start(self) -> str:
        self._thread.start()
        return self.url

    def stop(self) -> None:
        self._unsubscribe()
        # shutdown() serve_forever döngüsünün bitmesini bekler; döngü hiç
        # başlamadıysa sonsuza kadar bekler. Başlatılmamış bir sunucuyu
        # kapatmak sessizce asılmamalı.
        if self._thread.is_alive():
            self._httpd.shutdown()
        self._httpd.server_close()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:
        """Terminali istek kaydıyla kirletme — ajanın çıktısı orada."""

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """Hata gönderir — Türkçe mesajlar durum satırını çökertmeden.

        HTTP durum satırı latin-1 olmak zorunda. "Sesli komut kapalı"
        gönderince stdlib `UnicodeEncodeError` atıyor, handler ölüyor ve
        bağlantı **cevapsız** kapanıyor. İstemci tarafında bu "hiçbir şey
        olmuyor" gibi görünüyordu.

        Çözüm: durum satırına ASCII bir karşılık, gerçek metin gövdeye.
        Gövdeyi zaten arayüz okuyor.
        """
        reason = (message or "").encode("ascii", "replace").decode("ascii")
        super().send_error(code, reason or None, explain=message)

    def handle_one_request(self) -> None:
        """Kopan bağlantıyı sessizce yut.

        Tarayıcı sekmesi kapandığında ya da keep-alive soketi zaman
        aşımına uğradığında socketserver koca bir yığın izi basıyor.
        Bu normal bir olay; ajanın terminalinde hata gibi görünmemeli.
        """
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - stdlib arayüzü
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            self._file("index.html", "text/html; charset=utf-8")
        elif route in ASSETS:
            self._file(route.lstrip("/"), ASSETS[route])
        elif route == "/api/graph":
            self._json(build_graph(self.server.mind))  # type: ignore[attr-defined]
        elif route == "/api/organs":
            self._organs()
        elif route == "/api/state":
            self._json(self._controller_call("snapshot") or {"busy": False})
        elif route == "/api/gate":
            config = getattr(self.server, "config", None)
            on = gate.durum(config.state_dir) if config is not None else False
            self._json({"on": on})
        elif route == "/api/tanima":
            config = getattr(self.server, "config", None)
            d = (tanima.durum(config.state_dir) if config is not None
                 else {"on": False, "son_kosu": ""})
            self._json({"on": d["on"], "kosuyor": tanima.kosuyor(),
                        "hazir": tanima.hazir(), "son": d["son_kosu"]})
        elif route == "/api/dil":
            # Kurulum sihirbazının seçtiği arayüz dili. localStorage'a
            # kurulumdan yazılamıyor; sihirbaz çalışma alanına kurulum.json
            # bırakıyor, ilk açılışta dil.js buradan okuyup kendine yazıyor.
            # Dosya yoksa boş dönülüyor — dil.js Türkçe'ye düşer.
            config = getattr(self.server, "config", None)
            dil = ""
            if config is not None:
                try:
                    dil = str(json.loads(
                        (config.workspace / "kurulum.json").read_text(encoding="utf-8")
                    ).get("dil") or "")
                except (OSError, ValueError):
                    dil = ""
            self._json({"dil": dil})
        elif route == "/api/settings":
            self._settings()
        elif route == "/api/files":
            self._files()
        elif route == "/api/apps":
            self._apps()
        elif route == "/api/projects":
            self._projects()
        elif route == "/api/apps/running":
            self._apps_running()
        elif route == "/api/transfer/export":
            self._transfer_export()
        elif route == "/api/sessions":
            self._sessions()
        elif route == "/api/session":
            self._session()
        elif route == "/api/events":
            self._stream()
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802 - stdlib arayüzü
        route = self.path.split("?", 1)[0]
        # Gövde bir kez okunuyor. Önce JSON diye ayrıştırıp sonra ham hali
        # tekrar okumaya kalkmak istekleri sonsuza kadar askıda bırakıyordu:
        # ses isteğinin gövdesi JSON değil ham ses ve ikinci okuma hiç
        # gelmeyecek baytları bekliyor. O istek bir thread'i tutunca
        # tarayıcının bağlantı kotası doluyor ve **her şey** kilitleniyordu.
        raw = self._raw()
        body = _as_json(raw)

        # Ayarlar ajandan bağımsız: model yanlış yapılandırıldığı için ajan
        # hiç açılmamış olabilir ve düzeltmenin yeri tam olarak burası.
        if route == "/api/settings":
            self._save_settings(body)
            return
        if route == "/api/detect-window":
            self._detect_window()
            return
        if route == "/api/loaded":
            self._loaded()
            return
        if route == "/api/models":
            self._models(body)
            return
        if route == "/api/tasks":
            self._tasks(body)
            return
        if route == "/api/rules":
            self._rules(body)
            return
        if route == "/api/cameras":
            self._cameras(body)
            return
        if route == "/api/devices":
            self._devices(body)
            return
        if route == "/api/skills":
            self._skills(body)
            return
        if route == "/api/connectors":
            self._connectors(body)
            return
        if route == "/api/apps/run":
            self._run_app(body)
            return
        if route == "/api/apps/stop":
            from .. import apps as catalog
            pid = (body or {}).get("pid")
            if not isinstance(pid, int):
                self._json({"ok": False, "error": "`pid` gerekli"})
                return
            self._json(catalog.stop(pid))
            return
        if route == "/api/apps/remove":
            # Panelden silme: kalıcı değil — atölyedeki .geri-donusum'a taşır.
            # `base` şart: proje yolları çalışma alanına göre ("atolye/…")
            # geliyor; base'siz çözmek atolye/atolye/… diye ıskalıyordu.
            from .. import apps as catalog
            config = getattr(self.server, "config", None)
            path = str((body or {}).get("path") or "").strip()
            if config is None or not path:
                self._json({"ok": False, "error": "`path` gerekli"})
                return
            self._json(catalog.remove(config.open_sandbox().root, path,
                                      base=Path(config.workspace)))
            return
        if route == "/api/apps/open":
            # Sistem DIŞINDA aç (varsayılan uygulama/tarayıcı): statik web
            # sayfası server'sız, dosyadan tam çalışır.
            from .. import apps as catalog
            config = getattr(self.server, "config", None)
            path = str((body or {}).get("path") or "").strip()
            if config is None or not path:
                self._json({"ok": False, "error": "`path` gerekli"})
                return
            self._json(catalog.open_path(config.open_sandbox().root, path,
                                         base=Path(config.workspace)))
            return
        if route == "/api/transfer/import":
            self._transfer_import(raw)
            return
        if route == "/api/reset":
            self._reset(body)
            return
        if route == "/api/session/new":
            # Canlı yeni oturum köprüye bağlı: olay akışının yeni günlüğe
            # yeniden bağlanması gerekiyor. Köprü bunu desteklemiyorsa (ör.
            # salt-gözlem önizlemesi) dürüstçe ok:false dönüyor.
            result = self._controller_call("new_session")
            self._json(result if isinstance(result, dict) else {"ok": False})
            return
        if route == "/api/session/resume":
            sid = str((body or {}).get("id") or "").strip()
            if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
                self._json({"ok": False, "error": "geçersiz oturum"})
                return
            result = self._controller_call("resume_session", sid)
            self._json(result if isinstance(result, dict) else {"ok": False})
            return
        if route == "/api/session/project":
            mind = getattr(self.server, "mind", None)
            sid = str((body or {}).get("id") or "").strip()
            if mind is None or not hasattr(mind, "set_project"):
                self._json({"ok": False, "error": "proje desteği yok"})
                return
            if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
                self._json({"ok": False, "error": "geçersiz oturum"})
                return
            mapping = mind.set_project(sid, str((body or {}).get("project") or ""))
            self._json({"ok": True, "projects": sorted(set(mapping.values()))})
            return
        if route == "/api/gate":
            self._gate(body)
            return
        if route == "/api/tanima":
            self._tanima(body)
            return
        if route == "/api/drop":
            self._drop(body)
            return
        if route == "/api/speak":
            self._speak(body)
            return
        if route == "/api/voices":
            self._voices()
            return
        if route == "/api/hear":
            self._hear(raw)
            return
        if route == "/api/speaking":
            # Ajan konuşurken kulak kapanıyor: hoparlörden çıkan ses
            # mikrofona geri geliyor ve asistan kendi cümlesini duyup
            # cevap vermeye kalkıyordu.
            if (ear := getattr(self.server, "ear", None)) is not None:
                ear.speaking(bool(body.get("on")))
            self._json({"ok": True})
            return

        controller = getattr(self.server, "controller", None)
        if controller is None:
            self.send_error(503, "Ajan bağlı değil")
            return

        if route == "/api/chat":
            text = str(body.get("text") or "").strip()
            # Kameradan gelen kare metinsiz de gönderilebiliyor ("şuna bak").
            image = str(body.get("image") or "")
            if not text and not image:
                self._json({"ok": False, "error": "boş mesaj"})
                return
            # YAZILI durdurma da kesme sayılır. Sesli "dur" ve Durdur düğmesi
            # turu kesiyordu ama composer'a "durdur" yazmak sıradan bir mesaj
            # gibi KUYRUĞA giriyordu — kullanıcı "durdur dedim, hâlâ çalışıyor"
            # yaşıyordu. Aynı sözler (desktop._is_stop ile bire bir) burada da
            # kesme tetikliyor; mesaj olarak işlenmiyor.
            if not image:
                from ..desktop import _is_stop
                if _is_stop(text):
                    controller.interrupt()
                    hub = getattr(self.server, "hub", None)
                    if hub is not None:
                        hub.emit({"type": "notice", "text": "Durduruldu."})
                    self._json({"ok": True, "stopped": True})
                    return
            controller.submit(text, image)
        elif route == "/api/approve":
            controller.resolve_approval(
                str(body.get("id") or ""),
                bool(body.get("granted")),
                always=bool(body.get("always")),
            )
        elif route == "/api/interrupt":
            controller.interrupt()
        else:
            self.send_error(404)
            return

        self._json({"ok": True})

    # -- dış kapı -------------------------------------------------------

    def _gate(self, body: dict[str, Any]) -> None:
        """Dış kapı: aç/kapa ya da soru sor.

        Gövdede `on` varsa anahtar çevriliyor (ayar sayfasından gelir);
        `text` varsa kapı açıksa mesaj ajana veriliyor ve tur bitene kadar
        beklenip TÜM çıktı döndürülüyor. İkisi aynı uçta çünkü ikisi de
        aynı kavramın yüzü ve dışarıdaki araç tek adres ezberliyor.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        if "on" in (body or {}):
            gate.ayarla(config.state_dir, bool(body.get("on")))
            self._json({"ok": True, "on": gate.durum(config.state_dir)})
            return

        if not gate.durum(config.state_dir):
            self._json({"ok": False, "error": "dış kapı kapalı — ayarlar › makine'den açılır"})
            return

        text = str((body or {}).get("text") or "").strip()
        if not text:
            self._json({"ok": False, "error": "`text` gerekli"})
            return
        controller = getattr(self.server, "controller", None)
        hub = getattr(self.server, "hub", None)
        if controller is None or hub is None:
            self.send_error(503, "Ajan bağlı değil")
            return

        try:
            root = config.open_sandbox().root
        except Exception:
            root = None
        try:
            bekle = float(body.get("bekle_sn") or gate.VARSAYILAN_BEKLE_SN)
        except (TypeError, ValueError):
            bekle = gate.VARSAYILAN_BEKLE_SN
        try:
            self._json(gate.sor(
                controller=controller,
                hub=hub,
                text=text,
                image=str(body.get("image") or ""),
                bekle_sn=bekle,
                sandbox_root=root,
            ))
        except Exception as exc:
            # Kapıdaki hata dışarıdaki aracın bağlantısını sessizce
            # koparmamalı; sebep JSON olarak gitmeli.
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    # -- beni tanı ------------------------------------------------------

    def _tanima(self, body: dict[str, Any]) -> None:
        """Beni tanı: aç/kapa ya da hemen başlat.

        Gövdede `on` varsa anahtar çevriliyor (ayar sayfasından gelir) ve
        açılışta bekçiyi beklemeden bir kez denenir; `simdi` varsa aralık
        şartı atlanarak başlatılır — canlı doğrulamanın ve "geceyi bekleme"
        isteğinin yolu. Kapı (`/api/gate`) ile aynı kalıp: tek uç, iki yüz.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        hub = getattr(self.server, "hub", None)

        if "on" in (body or {}):
            tanima.ayarla(config.state_dir, bool(body.get("on")))
            # Üst bardaki ikon anahtarla birlikte yanıp sönsün: durum
            # değişikliği de SSE'den duyuruluyor — ayar sayfası ve sohbet
            # sekmesi ayrı istemciler, biri diğerini göremiyor.
            if hub is not None:
                hub.emit({"type": "tanima",
                          "state": "acik" if body.get("on") else "kapali"})
            if body.get("on") and hub is not None:
                tanima.belki_baslat(config.state_dir, hub)
        elif (body or {}).get("simdi") and hub is not None:
            tanima.belki_baslat(config.state_dir, hub, zorla=True)

        d = tanima.durum(config.state_dir)
        self._json({"ok": True, "on": d["on"], "kosuyor": tanima.kosuyor(),
                    "hazir": tanima.hazir(), "son": d["son_kosu"]})

    # -- ayarlar --------------------------------------------------------

    def _settings(self) -> None:
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        self._json(settings.snapshot(config))

    def _save_settings(self, body: dict[str, Any]) -> None:
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        try:
            updated = settings.apply(config, body)
        except (ValueError, OSError) as exc:
            # Bozuk bir değeri sessizce yutmak, açılmayan bir programa
            # dönüşüyor; sebebi ayar sayfasında görünmeli.
            self._json({"ok": False, "error": str(exc)})
            return

        self.server.config = updated  # type: ignore[attr-defined]
        # Anahtar değiştiyse istemci yeniden kurulmalı: anahtar ModelConfig'in
        # parçası olmadığından model "değişmemiş" görünüyor ve eski istemci
        # eski anahtarla kalıyordu. `force` bunu tazeletiyor.
        keys_changed = bool(body.get("keys"))
        if (controller := getattr(self.server, "controller", None)) is not None:
            reload = getattr(controller, "reload", None)
            if reload is not None:
                try:
                    reload(updated, force=keys_changed)
                except TypeError:
                    # Eski imza (force'suz) — yine de uygula.
                    reload(updated)

        self._json({"ok": True, "settings": settings.snapshot(updated)})

    def _detect_window(self) -> None:
        """Modelin gerçek bağlam penceresini sunucuya sorar.

        Yanlış bir pencere ayarı sıkıştırmayı hiç tetiklemiyor ve sunucu
        istemin başını sessizce atıyor; tahmin ettirmek yerine soruyoruz.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        self._json({"window": settings.detect_window(config)})

    def _loaded(self) -> None:
        """Sunucuda yüklü duran modeller. Aynı modelin birden çok kopyası
        varsa bellek boşa gidiyor demektir."""
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        self._json({"models": settings.loaded_models(config)})

    def _models(self, body: dict[str, Any] | None = None) -> None:
        """Sunucunun sunduğu model kimlikleri; elle yazmak hataya davetiye.

        Henüz kaydedilmemiş bir sağlayıcı da sorulabiliyor. Ayar sayfasında
        sağlayıcıya tıklandığında değişiklik daha kaydedilmemiş oluyordu ve
        katalog eski sunucudan geliyordu: kullanıcı LM Studio'ya geçip
        OpenRouter'ın model listesini görüyordu.
        """
        from dataclasses import replace

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        wanted = {
            key: value
            for key, value in (body or {}).items()
            if key in ("base_url", "provider", "api_key_env") and value is not None
        }
        if wanted:
            config = replace(config, model=replace(config.model, **wanted))

        self._json({"models": settings.scan_models(config)})

    # -- izlenen kameralar ------------------------------------------------

    def _cameras(self, body: dict[str, Any]) -> None:
        """İzlenen kameraları listeler ve düzenler.

        Değişiklik yeniden başlatınca geçerli oluyor: izleyici kendi
        thread'inde dönüyor ve çalışırken kamera eklemek/çıkarmak açık bir
        akışın ortasına girmek demek.
        """
        from dataclasses import asdict
        from uuid import uuid4

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        cameras = watch.load(config.state_dir)
        action = str(body.get("action") or "list")
        camera_id = str(body.get("id") or "")

        if action == "add":
            cameras.append(
                watch.Camera(
                    id=f"cam_{uuid4().hex[:8]}",
                    name=str(body.get("name") or "").strip() or "kamera",
                    source=str(body.get("source") or "0").strip(),
                    sensitivity=float(body.get("sensitivity") or 0.06),
                    cooldown_s=int(body.get("cooldown_s") or 60),
                    ask=str(body.get("ask") or ""),
                )
            )
        elif action == "update":
            known = set(watch.Camera.__dataclass_fields__)
            for camera in cameras:
                if camera.id != camera_id:
                    continue
                for name, value in body.items():
                    if name in known and name != "id":
                        setattr(camera, name, value)
        elif action == "remove":
            cameras = [c for c in cameras if c.id != camera_id]

        if action in ("add", "update", "remove"):
            watch.save(config.state_dir, cameras)

        self._json({
            "ok": True,
            "available": watch.available(),
            "cameras": [asdict(c) for c in cameras],
        })

    # -- izin kuralları ---------------------------------------------------

    def _rules(self, body: dict[str, Any]) -> None:
        """İzin kurallarını listeler ve düzenler.

        Kurallar `araç:hedef-deseni` biçiminde. "Hep izin ver" dendiğinde
        buraya bir satır yazılıyor; kullanıcının verdiği izni geri
        alabileceği bir yer olmadan o düğme tek yönlü bir kapı oluyordu.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        action = str(body.get("action") or "list")
        rule = str(body.get("rule") or "").strip()
        side = "deny" if body.get("side") == "deny" else "allow"

        rules = {"allow": list(config.permissions.allow), "deny": list(config.permissions.deny)}
        if action == "add" and rule:
            if rule not in rules[side]:
                rules[side].append(rule)
        elif action == "remove" and rule:
            rules[side] = [r for r in rules[side] if r != rule]

        if action in ("add", "remove"):
            try:
                updated = settings.apply(config, {"permissions": rules})
            except (ValueError, OSError) as exc:
                self._json({"ok": False, "error": str(exc), **self._rule_view(config)})
                return
            self.server.config = updated  # type: ignore[attr-defined]
            controller = getattr(self.server, "controller", None)
            if controller is not None and hasattr(controller, "reload"):
                controller.reload(updated)
            config = updated

        self._json({"ok": True, **self._rule_view(config)})

    def _rule_view(self, config: Config) -> dict[str, Any]:
        return {
            "mode": config.permissions.mode,
            "allow": list(config.permissions.allow),
            "deny": list(config.permissions.deny),
            "modes": list(settings.PERMISSION_MODES),
        }

    # -- zamanlanmış görevler --------------------------------------------

    def _tasks(self, body: dict[str, Any]) -> None:
        """Görevleri listeler ve düzenler.

        Tek uç: arayüzün her işlemi aynı yerden geçiyor ve listeyi güncel
        haliyle geri alıyor. Ayrı uçlar arayüzde bayat liste bırakıyordu.
        """
        book = getattr(self.server, "schedule", None)
        if book is None:
            self.send_error(503, "Zamanlayıcı çalışmıyor")
            return

        action = str(body.get("action") or "list")
        task_id = str(body.get("id") or "")

        try:
            if action == "add":
                book.add(
                    scheduling.Task(
                        id="",
                        title=str(body.get("title") or "").strip() or "adsız görev",
                        prompt=str(body.get("prompt") or ""),
                        kind=str(body.get("kind") or "every"),
                        every_s=int(body.get("every_s") or 3600),
                        at=str(body.get("at") or "09:00"),
                    )
                )
            elif action == "update":
                fields = {k: v for k, v in body.items() if k not in ("action", "id")}
                book.update(task_id, **fields)
            elif action == "remove":
                book.remove(task_id)
            elif action == "run":
                # Elle çalıştırma: zamanı beklemeden kuyruğa bırakıyor.
                task = book.get(task_id)
                controller = getattr(self.server, "controller", None)
                if task is None or controller is None:
                    self.send_error(404, "Görev yok")
                    return
                book.note_run(task_id, "elle çalıştırıldı")
                controller.submit(task.prompt)
        except (ValueError, TypeError) as exc:
            self._json({"ok": False, "error": str(exc), "tasks": scheduling.payload(book.all())})
            return

        self._json({"ok": True, "tasks": scheduling.payload(book.all())})

    # -- sohbete bırakılan dosyalar ---------------------------------------

    def _drop(self, body: dict[str, Any]) -> None:
        """Sürüklenen ya da yapıştırılan dosyayı atölyeye yazar.

        Tarayıcı yerel dosyanın **yolunu** vermiyor, yalnızca içeriğini —
        güvenlik gereği. O yüzden dosya atölyeye kopyalanıyor ve ajana yol
        veriliyor: oradan `read_file` ile açıp inceleyebiliyor.

        Görüntüler ayrı: onlar mesaja doğrudan iliştiriliyor ve model
        bakabiliyor. Yine de dosya olarak da kalıyor.
        """
        import base64
        import re

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        name = re.sub(r"[^\w.\- ]", "_", str(body.get("name") or "dosya")).strip() or "dosya"
        payload = str(body.get("data") or "")
        _, _, encoded = payload.partition(",")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception:
            self._json({"ok": False, "error": "dosya çözülemedi"})
            return

        if len(raw) > DROP_LIMIT:
            self._json({"ok": False, "error": f"dosya çok büyük (en fazla {DROP_LIMIT // 1024 // 1024} MB)"})
            return

        folder = config.open_sandbox().root / "gelen"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        # Aynı adlı dosya varsa üzerine yazmıyoruz: bırakılan bir dosyanın
        # öncekini sessizce silmesi veri kaybı.
        stem, suffix, index = target.stem, target.suffix, 2
        while target.exists():
            target = folder / f"{stem}-{index}{suffix}"
            index += 1

        try:
            target.write_bytes(raw)
        except OSError as exc:
            self._json({"ok": False, "error": str(exc)})
            return

        self._json({"ok": True, "path": str(target), "name": target.name, "bytes": len(raw)})

    # -- ses -------------------------------------------------------------

    def _speak(self, body: dict[str, Any]) -> None:
        """Metni sese çevirir ve mp3 olarak döndürür.

        Ses üretimi ağa çıkıyor ve saniyeler sürebiliyor; bu istek HTTP
        thread'ini meşgul ediyor ama ajanın döngüsüne dokunmuyor —
        sunucu zaten thread'li.
        """
        config = getattr(self.server, "config", None)
        if config is None or not config.voice.enabled:
            self.send_error(409, "Sesli konuşma kapalı")
            return

        text = str(body.get("text") or "")

        # Klip: kısa onay sesleri ("bakıyorum") her seferinde ağa çıkıp
        # yeniden üretilmesin — bir kez üretilip diskte duruyor, sonrası
        # anında dönüyor. Anahtar ses ayarlarını da içeriyor: ses ya da
        # hız değişirse eski klip kullanılmıyor.
        cached = None
        if body.get("clip") and text:
            import hashlib

            key = hashlib.sha1("|".join((
                config.voice.name, config.voice.rate,
                config.voice.pitch, text,
            )).encode("utf-8")).hexdigest()
            cached = config.state_dir / "clips" / f"{key}.mp3"
            if cached.exists():
                self._send(200, "audio/mpeg", cached.read_bytes())
                return

        try:
            audio = asyncio.run(voice.synthesize(text, config.voice))
        except RuntimeError as exc:  # paket kurulu değil
            self.send_error(501, str(exc))
            return
        except Exception:
            # Ağ yoksa ses de yok; metin yerinde duruyor, iş durmamalı.
            self.send_error(503, "Ses üretilemedi")
            return

        if not audio:
            # Söylenecek bir şey kalmamış (yalnızca kod bloğuydu gibi).
            self._send(204, "audio/mpeg", b"")
            return
        if cached is not None:
            try:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(audio)
            except OSError:
                pass  # disk yazılamıyorsa klip önbelleksiz devam eder
        self._send(200, "audio/mpeg", audio)

    def _voices(self) -> None:
        config = getattr(self.server, "config", None)
        prefix = (config.voice.name.split("-")[0] if config else "tr")
        try:
            listing = asyncio.run(voice.voices(prefix))
        except Exception:
            listing = []
        self._json({"voices": listing})

    def _hear(self, audio: bytes) -> None:
        """Gelen ses parçasını yazıya çevirir.

        Gövde ham ses (webm/opus); JSON değil, çünkü base64'e çevirmek
        üçte bir büyüme ve boşuna iş. Tanıma yerel — ses hiçbir yere
        gitmiyor.
        """
        config = getattr(self.server, "config", None)
        if config is None or not config.listen.enabled:
            self.send_error(409, "Sesli komut kapalı")
            return

        if not audio:
            self.send_error(400, "Boş ses")
            return

        ear = _ear(self.server, config)
        if ear is None:
            self.send_error(501, listen.INSTALL_HINT)
            return

        # Tanıyıcı dosya yolu istiyor; parça küçük ve geçici.
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as handle:
            handle.write(audio)
            clip = Path(handle.name)

        try:
            said = ear.transcribe(clip)
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)})
            return
        finally:
            clip.unlink(missing_ok=True)

        wake = config.listen.wake
        self._json({
            "ok": True,
            "text": said,
            "wake": listen.heard_wake(said, wake),
            # Uyandırma sözünün kendisi komutun parçası değil.
            "command": listen.after_wake(said, wake),
        })

    # -- ajanın ürettiği dosyalar ---------------------------------------

    def _devices(self, body: dict[str, Any]) -> None:
        """Cihaz kayıtları: listele, yaz, sil.

        Ajanla aynı dosyalara yazıyor. İki ayrı depo tutmak, kullanıcının
        eklediği bir PLC'yi ajanın görmemesi demekti — cihazın anlamı
        zaten ikisinin de bilmesi.
        """
        from .. import devices as declared

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        root = config.open_sandbox().root
        action = str(body.get("action") or "list")

        if action == "save":
            raw = dict(body.get("device") or {})
            # Ayarlar sayfasından eklenen kayıt kullanıcınındır: ajan onu
            # kendiliğinden silemiyor.
            raw.setdefault("source", "elle")
            try:
                declared.save(root, raw)
            except declared.DeviceError as exc:
                self._json({"ok": False, "error": str(exc)})
                return

        elif action == "remove":
            declared.remove(root, str(body.get("id") or ""))

        found, broken = declared.load(root)
        self._json({
            "ok": True,
            "kinds": list(declared.KINDS),
            "devices": [declared.to_dict(device) for device in found],
            "broken": broken,
        })

    def _skills(self, body: dict[str, Any]) -> None:
        """Yetenekler: listele, oluştur, oku, yaz, sil.

        Kullanıcı da ekleyip düzenleyebiliyor — yetenek yalnızca ajanın
        kendine yazdığı şey değil. Her değişiklik canlı deftere de işleniyor:
        kaydedilen yetenek bir sonraki turda araç olarak var, silinen yok.
        """
        from .. import skills as authored

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        # Canlı defter: değişiklik oturuma anında işlensin. Ajan yoksa
        # (salt-gözlem önizlemesi) dosya işleri yine de çalışıyor.
        agent = getattr(getattr(self.server, "controller", None), "agent", None)
        registry = getattr(agent, "registry", None)

        root = config.open_sandbox().root
        action = str(body.get("action") or "list")
        name = str(body.get("name") or "").strip().lower()
        error = ""

        if action == "remove":
            path = authored.folder(root) / f"{name}.py"
            if path.is_file():
                path.unlink()
            if registry is not None:
                registry.unregister(name)

        elif action == "new":
            try:
                authored.scaffold(root, name, str(body.get("description") or "").strip())
            except authored.SkillError as exc:
                error = str(exc)

        elif action == "read":
            path = authored.folder(root) / f"{name}.py"
            if not path.is_file():
                self._json({"ok": False, "error": f"Dosya yok: {name}.py"})
                return
            self._json({"ok": True, "name": name, "code": path.read_text(encoding="utf-8")})
            return

        elif action == "write":
            code = str(body.get("code") or "")
            if not name or not code.strip():
                self._json({"ok": False, "error": "`name` ve `code` gerekli."})
                return
            path = authored.folder(root) / f"{name}.py"
            path.write_text(code, encoding="utf-8")
            # Yazılan dosya hemen deneniyor: hata varsa kullanıcı kaydettiği
            # anda görüyor, ajan çağırdığında değil.
            try:
                authored.load_file(path)
            except authored.SkillError as exc:
                error = str(exc)

        found, broken = authored.discover(root)
        if registry is not None:
            authored.register(registry, found)
        self._json({
            "ok": not error,
            "error": error,
            "skills": [
                {
                    "name": skill.name,
                    "description": (skill.description or "").strip(),
                    "path": str(authored.folder(root) / f"{skill.name}.py"),
                }
                for skill in found
            ],
            "broken": broken,
        })

    def _connectors(self, body: dict[str, Any]) -> None:
        """MCP bağlayıcıları: listele, kaydet, yeniden bağlan.

        Kayıt tek bir JSON metni — Claude Code'un `mcpServers` biçimi.
        Kaydetmek yeniden bağlanmayı da kapsıyor: dosyada duran ama
        bağlanmamış bir sunucu, yok hükmünde.
        """
        from .. import connectors as linking

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        pool = getattr(self.server, "connectors", None)
        agent = getattr(getattr(self.server, "controller", None), "agent", None)
        registry = getattr(agent, "registry", None)

        action = str(body.get("action") or "list")
        problems: list[str] = []
        note = ""

        if action == "save":
            try:
                linking.save(config.state_dir, str(body.get("raw") or ""))
            except linking.ConnectorError as exc:
                self._json({"ok": False, "error": str(exc)})
                return

        if action == "login":
            # OAuth: tarayıcı açılır, kullanıcı girer, jeton saklanır.
            # Bu istek giriş bitene kadar bekler — sunucu thread'li, başka
            # istekleri durdurmuyor.
            name = str(body.get("name") or "")
            found, _ = linking.load(config.state_dir)
            target = next((c for c in found if c.name == name), None)
            if target is None:
                self._json({"ok": False, "error": f"Sunucu yok: {name}"})
                return
            # Giriş adresi sohbete de düşüyor: tarayıcı arka planda ya da
            # görünmeden açılmış olabilir — adres ekranda olursa kullanıcı
            # kopyalayıp kendisi açabilir.
            hub = getattr(self.server, "hub", None)

            def tell(url: str) -> None:
                if hub is not None:
                    hub.emit({"type": "notice",
                              "text": "Giriş sayfası tarayıcıda açılıyor. "
                                      "Açılmadıysa bu adresi kendin aç:\n" + url})

            try:
                note = linking.login(target, config.state_dir, announce=tell)
            except linking.ConnectorError as exc:
                self._json({"ok": False, "error": str(exc)})
                return

        if action == "logout":
            if linking.forget_login(config.state_dir, str(body.get("name") or "")):
                note = "Çıkış yapıldı."

        if action in ("save", "reload", "login", "logout") and pool is not None:
            # Bağlanmak saniyeler sürebilir (npx paket indirebiliyor); ayar
            # sayfası bekliyor ve dönen liste gerçek durumu gösteriyor.
            found, problems = linking.load(config.state_dir)
            pool.connect(found, config.state_dir)
            if registry is not None:
                linking.register(registry, pool)

        self._json({
            "ok": True,
            "note": note,
            "raw": linking.read_raw(config.state_dir),
            "servers": pool.status() if pool is not None else [],
            "problems": problems,
        })

    def _organs(self) -> None:
        """Ajanın o anki bedeni: duyuları ve kendine yazdığı modüller.

        Sahne bunu soluk olarak çiziyor ve kullanıldığında canlandırıyor.
        Ayarlardan değil buradan okunuyor: ayarda açık görünen bir kamera
        gerçekten açılmamış olabilir ve ekranda çalışıyormuş gibi durur.
        """
        from .. import organs as body

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"organs": []})
            return

        self._json({
            "organs": body.inventory(
                config,
                ear=getattr(self.server, "ear", None),
                lens=getattr(self.server, "lens", None),
            )
        })

    def _files(self) -> None:
        """Çalışma alanını gezdirir.

        Yol istekten geliyor, o yüzden çözümlenip çalışma alanının altında
        kaldığı doğrulanıyor: `..` ile yukarı çıkmak dizin dışına çıkma
        açığının klasik yolu.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        query = parse_qs(urlparse(self.path).query)
        root = Path(config.workspace).resolve()
        target = (root / (query.get("path", [""])[0] or "")).resolve()

        if root != target and root not in target.parents:
            self.send_error(403, "Çalışma alanı dışı")
            return

        if target.is_file():
            self._json(_file_payload(target, root))
            return
        if not target.is_dir():
            self.send_error(404)
            return

        self._json({
            "path": _relative(target, root),
            "parent": None if target == root else _relative(target.parent, root),
            "entries": _listing(target, root),
        })

    def _apps(self) -> None:
        """Atölyeyi çalıştırılabilir uygulama kataloğu olarak verir.

        Sandbox yoksa boş kök: ajanın atölyesi henüz açılmamış olabilir.
        """
        from .. import apps as catalog

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"root": None})
            return
        try:
            root = config.open_sandbox().root
            # base çalışma alanı: yollar `/api/files` ile aynı köke göreli
            # olsun ki bir web uygulaması tıklanınca gerçekten açılabilsin.
            tree = catalog.catalog(root, base=Path(config.workspace))
        except Exception as exc:
            self._json({"root": None, "error": str(exc)})
            return
        self._json({"root": catalog.to_dict(tree)})

    def _projects(self) -> None:
        """Atölyeyi PROJE birimleri olarak verir (dosya ağacı değil).

        Her proje bir iş birimi: neo'nun ürettiği bir klasör (Modbus web
        client gibi) ya da tek başına bir dosya. Panel bunları kart olarak
        gösteriyor; tıklanınca nasıl çalıştırılacağı + Çalıştır beliriyor.
        """
        from .. import apps as catalog

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"projects": []})
            return
        try:
            root = config.open_sandbox().root
            items = catalog.projects(root, base=Path(config.workspace))
        except Exception as exc:
            self._json({"projects": [], "error": str(exc)})
            return
        self._json({"projects": items})

    def _apps_running(self) -> None:
        """Çalışan, izlenebilen uygulamalar (canlı adresleriyle).

        Köprü/atölye yoksa boş liste: panel bunu "çalışan yok" gösteriyor.
        """
        from .. import apps as catalog

        try:
            self._json({"running": catalog.running()})
        except Exception as exc:
            self._json({"running": [], "error": str(exc)})

    def _parcalar(self) -> list[str] | None:
        """İstekteki parça seçimi: ?parcalar=anilar,tanima → liste.

        Parametre yoksa None — dışa/içe aktarma eski (varsayılan)
        davranışına düşer; bilinmeyen adları transfer modülü eliyor.
        """
        raw = parse_qs(urlparse(self.path).query).get("parcalar", [""])[0]
        secim = [p.strip() for p in raw.split(",") if p.strip()]
        return secim or None

    def _transfer_export(self) -> None:
        """neo'nun biriktirdiklerini taşınabilir bir paket olarak indirir.

        `?parcalar=anilar,tanima,projeler,ayarlar` ile seçmeli: sunucuya
        taşınırken yalnızca gerekenler paketlenir. Parametresiz istek
        eskisiyle birebir aynı paketi üretir (geriye uyumluluk).
        """
        from .. import transfer

        config = getattr(self.server, "config", None)
        mind = getattr(self.server, "mind", None)
        if config is None or mind is None:
            self.send_error(503, "Bellek bağlı değil")
            return
        try:
            data = transfer.export_bundle(config, mind, self._parcalar())
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)})
            return
        stamp = _stem_date(getattr(mind, "session_id", "")).replace(" ", "_").replace(":", "")
        name = f"neo-{stamp or 'paket'}.neobundle"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _transfer_import(self, raw: bytes) -> None:
        """Yüklenen bir paketi bu neo'ya birleştirir.

        Anılar katılır (üzerine yazılmaz); dosya parçaları geri yüklenirken
        ezilecek mevcut hal önce .neocp/yedek-<tarih>/ altına alınır.
        `?parcalar=...` pakette olsa bile yalnızca istenenleri işletir.
        """
        from .. import transfer

        config = getattr(self.server, "config", None)
        mind = getattr(self.server, "mind", None)
        if config is None or mind is None:
            self._json({"ok": False, "error": "Bellek bağlı değil"})
            return
        if not raw:
            self._json({"ok": False, "error": "Boş yükleme"})
            return
        try:
            result = transfer.import_bundle(config, mind, raw, self._parcalar())
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return
        self._json(result)

    def _reset(self, body: dict[str, Any]) -> None:
        """Sıfırlama: {"hedef": "anilar"} ya da {"hedef": "tanima"}.

        İkisi de yıkım değil taşıma: mevcut hal .neocp/yedek-<tarih>/
        altına gidiyor, sonra temiz başlanıyor. Onay arayüzde (iki adımlı
        düğme); burada tek güvence hedef adının tanınması.
        """
        from .. import transfer

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        hub = getattr(self.server, "hub", None)
        hedef = str((body or {}).get("hedef") or "")

        if hedef == "anilar":
            mind = getattr(self.server, "mind", None)
            if mind is None:
                self._json({"ok": False, "error": "Bellek bağlı değil"})
                return
            result = transfer.reset_memories(config, mind)
            if result.get("ok") and hub is not None:
                hub.emit({"type": "notice",
                          "text": f"Anılar sıfırlandı ({result['silinen']} kayıt) — "
                                  f"yedek: {result['yedek']}"})
        elif hedef == "tanima":
            result = tanima.sifirla(config.state_dir)
            if result.get("ok") and hub is not None:
                metin = ("Beni tanı sıfırlandı — taban modele dönüldü"
                         + (f" · yedek: {result['yedek']}" if result.get("yedek") else ""))
                hub.emit({"type": "notice", "text": metin})
        else:
            self._json({"ok": False, "error": "`hedef` anilar ya da tanima olmalı"})
            return
        self._json(result)

    def _run_app(self, body: dict[str, Any]) -> None:
        """Atölyedeki bir betiği/aracı başlatır.

        Yalnızca atölyenin içi çalıştırılabiliyor; sınır `apps.launch`
        içinde bir kez daha doğrulanıyor.
        """
        from .. import apps as catalog

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "Yapılandırma yüklü değil"})
            return
        path = str((body or {}).get("path") or "").strip()
        if not path:
            self._json({"ok": False, "error": "`path` gerekli"})
            return
        root = config.open_sandbox().root
        self._json(catalog.launch(root, path, base=Path(config.workspace)))

    def _sessions(self) -> None:
        """Geçmiş konuşmaların listesi. Beyin/anı DEĞİL — ham oturumlar.

        Bir konuşma bir anı demek değil: anılar konuşmalardan ayrıca oluşuyor.
        Bu liste konuşmaların kendisi; sahnedeki ağ ise onlardan süzülen
        anılar.
        """
        mind = getattr(self.server, "mind", None)
        if mind is None:
            self._json({"sessions": []})
            return
        current = getattr(mind, "session_id", "")
        projects = mind.projects() if hasattr(mind, "projects") else {}
        out = []
        for ep in mind.sessions():
            out.append({
                "id": ep.session_id,
                "title": _session_title(ep.digest),
                "date": _stem_date(ep.session_id),
                "turns": ep.turns,
                "tools": ep.tools[:6],
                "preview": ep.digest[:160],
                "current": ep.session_id == current,
                "project": projects.get(ep.session_id, ""),
            })
        self._json({"sessions": out, "projects": sorted(set(projects.values()))})

    def _session(self) -> None:
        """Bir oturumun konuşma dökümü (görüntüleme için)."""
        mind = getattr(self.server, "mind", None)
        if mind is None:
            self._json({"turns": []})
            return
        sid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
        # Yol/ad enjeksiyonu olmasın: kimlik yalnızca harf/rakam/-/_ olabilir.
        if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
            self.send_error(400, "geçersiz oturum")
            return
        self._json({"id": sid, "turns": mind.transcript(sid)})

    def _raw(self) -> bytes:
        """Gövdeyi bir kez okur.

        İki kez okumak mümkün değil: ilk okuma akışı tüketiyor, ikincisi hiç
        gelmeyecek baytları bekliyor ve istek askıda kalıyor.
        """
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b''

    def _controller_call(self, name: str, *args: Any) -> Any:
        controller = getattr(self.server, "controller", None)
        fn = getattr(controller, name, None) if controller else None
        # Olmayan bir metot (ör. salt-gözlem önizlemesi ya da new_session
        # desteklemeyen bir köprü) sessizce None: uç nokta bunu ok:false'a
        # çeviriyor, 500 atmıyor.
        return fn(*args) if callable(fn) else None

    # -- yanıt biçimleri -----------------------------------------------

    def _file(self, name: str, content_type: str) -> None:
        try:
            body = (STATIC / name).read_bytes()
        except OSError:
            self.send_error(404)
            return
        self._send(200, content_type, body)

    def _json(self, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(200, "application/json; charset=utf-8", body)

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _stream(self) -> None:
        channel = self.server.hub.register()  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        # HTTP/1.1'de gövdenin sonu ya Content-Length ile ya chunked ile ya da
        # bağlantının kapanmasıyla belirlenir. Uzunluk bilinmediği için
        # "keep-alive" demek gövdeyi çerçevesiz bırakıyordu: tarayıcı akışı
        # tamponluyor ve cevap toptan geliyordu.
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")   # araya giren vekiller için
        self.end_headers()
        self.close_connection = True

        try:
            while True:
                try:
                    line = channel.get(timeout=HEARTBEAT_S)
                except queue.Empty:
                    # Yorum satırı: bağlantıyı canlı tutar, istemci yok sayar.
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # sekme kapandı
        finally:
            self.server.hub.unregister(channel)  # type: ignore[attr-defined]
