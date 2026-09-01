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
import html
import json
import os
import queue
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from typing import Any, Protocol

from .. import (listen, ortam, sandbox, schedule as scheduling, settings,
                tanima, voice, watch)
from ..config import Config
from ..events import Event, EventLog
from ..mind.store import Mind
from . import gate
from .graph import build_graph

STATIC = Path(__file__).parent / "static"
HEARTBEAT_S = 15.0
QUEUE_LIMIT = 500


def _attachment_disposition(title: str, suffix: str = ".html") -> str:
    """Content-Disposition: HTTP header latin-1; Türkçe başlık ASCII + RFC5987.

    `filename=` yalnız ASCII; `filename*=UTF-8''…` yüzde kodlu gerçek ad.
    """
    raw = str(title or "download").strip() or "download"
    if suffix and not raw.lower().endswith(suffix.lower()):
        display = raw + suffix
    else:
        display = raw
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", display).strip("._") or "download"
    if suffix and not ascii_name.lower().endswith(suffix.lower()):
        ascii_name = ascii_name + suffix
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(display, safe='')}"
    )
# Kullanıcının hedef panelinden elle yazdığı maddenin tavanı. Panelde tek
# satır olarak duruyor; roman uzunluğunda bir madde ne panelde ne de
# modelin bağlamında işe yarar.
GOAL_TEXT_LIMIT = 200

# Servis edilen dosyalar açıkça listeleniyor: yol birleştirmeyi istekten
# türetmek dizin dışına çıkma açığının klasik yolu.
ASSETS = {
    "/app.css": "text/css; charset=utf-8",
    "/settings.css": "text/css; charset=utf-8",
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
    # Kamera güvertesi: izleme alanı (dahili + IP kameralar).
    "/cameras.js": "text/javascript; charset=utf-8",
    "/watch.js": "text/javascript; charset=utf-8",
    # Koşan görevler paneli: arka plan işleri, yardımcılar, süreçler.
    "/gorevler.js": "text/javascript; charset=utf-8",
    # Kompozer yüzeyleri: `/` komut defteri ve `@` dosya bahsi.
    "/komut.js": "text/javascript; charset=utf-8",
    # "Bu turda ne değişti" şeridi + geri alma.
    "/degisiklik.js": "text/javascript; charset=utf-8",
    "/git.js": "text/javascript; charset=utf-8",
    "/chrome.js": "text/javascript; charset=utf-8",
    # Sağ tık menüsü (kullanıcının laptop paketi): index.html yüklüyor ama
    # izin listesine hiç girmemişti — üründe sağ tık sessizce ölüydü (404).
    "/menu.js": "text/javascript; charset=utf-8",
    "/speech.js": "text/javascript; charset=utf-8",
    "/listen.js": "text/javascript; charset=utf-8",
    "/camera.js": "text/javascript; charset=utf-8",
    "/drop.js": "text/javascript; charset=utf-8",
    "/workflow.js": "text/javascript; charset=utf-8",
    "/jobs.js": "text/javascript; charset=utf-8",
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
        # Artifact yayınlandı/güncellendi: sohbette kart olarak görünür.
        "artifact",
        # Büyük iş planı: onay kartı.
        "plan",
        # Cihaz kaydı silindi: sahne organı ve ayarlar listesi bayat kalmasın.
        "device_removed",
        # Git commit/push/publish: çubuk ve pane tazelensin.
        "git",
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
    # Köprünün ayrıca sunduğu ama ZORUNLU OLMAYAN uçlar (görevler paneli,
    # bütçe freni, elle sıkıştırma) burada değil: `_controller_call`
    # olmayan metodu sessizce None'a çeviriyor ve uç nokta bunu dürüst bir
    # ok:false'a döndürüyor. Salt-gözlem köprüleri (önizleme, testler)
    # bunları uygulamak zorunda kalmıyor.


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

    def publish(self, event: Event, sid: str = "") -> None:
        if (payload := _payload(event)) is not None:
            if sid:
                payload.setdefault("sid", sid)
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
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".pdf", ".zip",
     ".gz", ".exe", ".dll", ".so", ".dylib", ".db", ".sqlite", ".wasm",
     ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".mp4", ".webm", ".mov", ".mkv",
     ".ttf", ".otf", ".woff", ".woff2"}
)

# `/api/raw` yalnızca bu türleri ADIYLA servis ediyor. Liste bilinçli olarak
# kısa ve medyaya kapalı: tarayıcının içeriğe bakıp tür tahmin etmesi
# (sniffing) çalışma alanındaki bir metin dosyasını HTML sayıp
# çalıştırabilirdi. Listede olmayan her şey octet-stream — indirilir,
# yorumlanmaz. `.svg` de burada: XML olduğu için betik taşıyabiliyor ama
# görüntüleyici onu `<img>` ile çiziyor — bir resimde betik çalışmıyor.
RAW_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".ico": "image/x-icon", ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".m4a": "audio/mp4", ".flac": "audio/flac",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
}

# Gezinmede atlanan dizinler: ajanın ürettiği değil, araçların bıraktığı şeyler.
SKIPPED = frozenset({".git", "__pycache__", "node_modules", ".venv", ".mypy_cache"})

# Kompozerdeki `@` dosya bahsi her tuşta arama yapıyor: tarama TAVANLI
# olmak zorunda. Dev bir çalışma alanında bile yazma akışı kesilmiyor —
# tavana çarpınca elde ne varsa o dönüyor ve arayüz "daralt" diyor.
SEARCH_SCAN_CAP = 6000
SEARCH_LIMIT = 20

# Fark kartında gösterilecek azami metin. Daha büyüğü zaten okunmuyor,
# ama tarayıcıya yığmak paneli kilitliyor.
DIFF_LIMIT = 200 * 1024


def _hedef_ozeti(args: Any, limit: int = 90) -> str:
    """Araç argümanlarından tek satırlık hedef: yol ya da komut.

    Görev dökümünde okunan şey "hangi dosyaya / hangi komutla" — ham JSON
    değil. Tanınan bir alan yoksa ilk metin değeri kullanılıyor.
    """
    if not isinstance(args, dict):
        return ""
    for key in ("path", "command", "query", "url", "title", "id", "text"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            flat = " ".join(value.split())
            return flat if len(flat) <= limit else flat[:limit] + "…"
    return ""


def _plain_blocks(content: Any) -> list[str]:
    """Bir mesajın düz metin blokları (araç çağrıları ve muhakeme dışarıda)."""
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [str(b.get("text") or "") for b in content
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]


def _rapor_html(metin: str) -> str:
    """Görev raporunu güvenli HTML'e çevirir (hafif markdown).

    Tam markdown motoru yok; başlık / liste / link / kod yeter — rapor
    sohbete yapışmak yerine Viewer'da okunur. ## Çıktı varsayılan kapalı
    <details> — uzun kurulum logları özeti örtmesin.
    """
    out: list[str] = []
    in_ul = False
    in_log = False
    log_buf: list[str] = []

    def flush_log() -> None:
        nonlocal in_log, log_buf
        if not in_log:
            return
        raw = "\n".join(log_buf).strip("\n")
        out.append(
            '<details class="log"><summary>Ham çıktı</summary>'
            f"<pre>{html.escape(raw)}</pre></details>"
        )
        in_log = False
        log_buf = []

    for ham in (metin or "").replace("\r\n", "\n").split("\n"):
        s = ham.rstrip()
        # Ham Python izi rapor değil — insan_is_raporu kaçırırsa bile basma.
        if s.startswith("Traceback (") or s.startswith("File \""):
            continue
        if s.startswith("## "):
            flush_log()
            if in_ul:
                out.append("</ul>"); in_ul = False
            baslik = s[3:].strip()
            if baslik.casefold() in ("çıktı", "cikti", "output"):
                in_log = True
                log_buf = []
                continue
            out.append("<h2>" + _inline_md(baslik) + "</h2>")
        elif in_log:
            log_buf.append(ham)
        elif s.startswith("### "):
            if in_ul:
                out.append("</ul>"); in_ul = False
            out.append("<h3>" + _inline_md(s[4:]) + "</h3>")
        elif re.match(r"^[-*]\s+", s):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append("<li>" + _inline_md(re.sub(r"^[-*]\s+", "", s)) + "</li>")
        elif not s:
            if in_ul:
                out.append("</ul>"); in_ul = False
            out.append("<br>")
        else:
            if in_ul:
                out.append("</ul>"); in_ul = False
            out.append("<p>" + _inline_md(s) + "</p>")
    if in_ul:
        out.append("</ul>")
    flush_log()
    return "\n".join(out) or "<p><i>(boş rapor)</i></p>"


def _rapor_kapak(result: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Rapor sayfasının başlığı: komut h1 olmasın, görev id'si öne çıkmasın.

    Dönen: (sekme başlığı, h1, badge HTML, özet metin, komut metin).
    """
    ham = str(result.get("title") or "Rapor").strip()
    state = str(result.get("state") or "")
    komut = ham[2:].strip() if ham.startswith("$ ") else ""
    if state == "hata":
        h1 = "İş başarısız"
        badge = '<span class="badge err">Başarısız</span>'
    elif state == "kosuyor":
        h1 = "İş sürüyor"
        badge = '<span class="badge">Sürüyor</span>'
    elif komut:
        h1 = "İş tamamlandı"
        badge = '<span class="badge ok">Tamamlandı</span>'
    else:
        h1 = ham or "Rapor"
        badge = (
            '<span class="badge ok">Tamamlandı</span>' if state == "bitti"
            else ""
        )
    ozet = ""
    for line in str(result.get("metin") or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("- "):
            continue
        ozet = s
        break
    if not komut and ham and ham != h1:
        # Komut yoksa eski başlığı meta olarak taşıma — ozet yoksa ham.
        if not ozet:
            ozet = ham
    return h1, h1, badge, ozet, komut


def _inline_md(s: str) -> str:
    t = html.escape(s)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        t,
    )
    return t


def _search_files(root: Path, want: str, *, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
    """Çalışma alanında ada göre hızlı dosya araması (`@` seçicisi).

    Sıralama kullanıcının aradığı şeye göre: adında geçenler önce, yol
    içinde geçenler sonra; her grupta kısa yol önde (kök dosyalar derindeki
    kopyalarından daha muhtemel). Sorgu boşsa "en son dokunulanlar" —
    `@` yazan kullanıcı çoğu zaman üzerinde çalıştığı dosyayı istiyor.
    """
    import os

    adda: list[tuple[int, str, float]] = []
    yolda: list[tuple[int, str, float]] = []
    hepsi: list[tuple[str, float]] = []
    tarandi = 0
    tasti = False

    for dirpath, dirnames, filenames in os.walk(root):
        # Gizli ve araç klasörleri: ne ajanın ürettiği ne kullanıcının yazdığı.
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIPPED and not d.startswith("."))
        for name in filenames:
            if name.startswith("."):
                continue
            tarandi += 1
            if tarandi > SEARCH_SCAN_CAP:
                tasti = True
                break
            full = Path(dirpath) / name
            try:
                rel = full.relative_to(root).as_posix()
                mtime = full.stat().st_mtime
            except (OSError, ValueError):
                continue
            if not want:
                hepsi.append((rel, mtime))
            elif want in name.lower():
                adda.append((len(rel), rel, mtime))
            elif want in rel.lower():
                yolda.append((len(rel), rel, mtime))
        if tasti:
            break

    if not want:
        hepsi.sort(key=lambda r: -r[1])
        secilen = [rel for rel, _ in hepsi[:limit]]
    else:
        adda.sort()
        yolda.sort()
        secilen = [rel for _, rel, _ in (adda + yolda)[:limit]]
    return [{"path": rel, "name": rel.rsplit("/", 1)[-1]} for rel in secilen]


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

    threading.Thread(target=warm, daemon=True, name="dornick-ear").start()


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


def ear_gate(ear: Any, action: str) -> dict[str, Any]:
    """Kompozer mikrofonu: kulağı sustur / aç. Ajan `senses` aracıyla aynı kapı.

    Tarayıcı bas-konuş aynı mikrofona ikinci kez yapışır ve sürekli
    dinleme durmaz — durdurmak ajan aracına kalıyordu.
    """
    if ear is None:
        return {"ok": True, "ear": False, "snoozed": False}
    act = (action or "status").strip()
    if act == "pause":
        ear.snooze(0)
    elif act == "resume":
        ear.unsnooze()
    elif act == "toggle":
        if ear.snoozed:
            ear.unsnooze()
        else:
            ear.snooze(0)
    return {
        "ok": True,
        "ear": True,
        "snoozed": bool(getattr(ear, "snoozed", False)),
    }


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
    words = flat.split(" ")
    # İlk söz tek harflik bir tuş kazasıysa ("e", "b" + Enter) başlık o
    # harfe kilitleniyordu; kırıntıyı atlayıp ilk gerçek kelimeden başla.
    while len(words) > 1 and len(words[0]) == 1 and not words[0].isdigit():
        words = words[1:]
    words = words[:8]
    title = " ".join(words)
    return title if len(title) <= 60 else title[:60] + "…"


def _stem_date(stem: str) -> str:
    """20260610T090000Z -> 2026-06-10 09:00. Tanınmayanı olduğu gibi bırakır."""
    m = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})", stem or "")
    if not m:
        return stem
    y, mo, d, h, mi = m.groups()
    return f"{y}-{mo}-{d} {h}:{mi}"


def _baslangic_yerleri() -> list[dict[str, str]]:
    """Klasör seçicinin açılış listesi: sürücüler ve ev.

    Windows'ta sürücü harfleri, ötekilerde kök ve ev. Amaç "nereden
    başlayacağım" sorusunu ilk ekranda cevaplamak.
    """
    yerler: list[dict[str, str]] = []
    try:
        ev = Path.home()
        yerler.append({"ad": f"~ ({ev.name})", "yol": str(ev)})
    except (OSError, RuntimeError):  # pragma: no cover - ev tanımsız olabilir
        pass

    if os.name == "nt":
        for harf in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            surucu = Path(f"{harf}:\\")
            try:
                if surucu.is_dir():
                    yerler.append({"ad": f"{harf}:", "yol": str(surucu)})
            except OSError:  # pragma: no cover - hazır olmayan sürücü
                continue
    else:  # pragma: no cover - bu makinede koşmuyor
        yerler.append({"ad": "/", "yol": "/"})
    return yerler


def _proje_turu(kok: Path) -> str:
    """Klasörde tanınan bir koşum düzeneği varsa etiketi ("pytest" gibi).

    Tespit `kosum` modülünde zaten var; burada yalnızca okunur bir etikete
    indirgeniyor. Bulunamazsa boş dize — uydurma etiket yok.
    """
    try:
        from .. import kosum

        duzenek = kosum.tespit(kok)
    except Exception:  # pragma: no cover - tespit bir kolaylık, patlarsa sus
        return ""
    return duzenek.etiket if duzenek is not None else ""


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
        # Port GERÇEKTEN boş mu? Windows'ta ThreadingHTTPServer'ın
        # varsayılan SO_REUSEADDR'ı dolu portun üstüne sessizce ikinci kez
        # bağlanmaya izin veriyor — bağlantılar ESKİ sürece gidiyor ve
        # pencere dornick yerine o portu tutan uygulamayı gösteriyordu (canlı,
        # 29.08: laptopta eski bir atölye paneli 8765'i tutuyordu ve dornick
        # "kendi olmayan" bir sayfayla açıldı). Çözüm iki katlı: gasp izni
        # kapalı bir sunucu sınıfı + doluysa sıradaki boş porta kayma.
        # Gerçek adres her zaman `url`'den okunur; pencere de onu kullanır.
        son_hata: OSError | None = None
        for aday in range(int(port), int(port) + 20):
            try:
                self._httpd = _TekSahipSunucu((host, aday), _Handler)
                if aday != int(port):
                    print(f"[dornick] {port} portu dolu — arayüz {aday} portunda",
                          flush=True)
                break
            except OSError as exc:
                son_hata = exc
        else:
            raise OSError(
                f"{port}-{int(port) + 19} arası hiçbir port boş değil"
            ) from son_hata
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
        # Günlük olayları da oturum kimliğiyle damgalanıyor: abonelik
        # değişimi geçiş anında yarışabilir ve eski günlüğün kuyruktaki
        # olayı yeni ekrana düşebilirdi — arayüz kimliği tutmayanı çizmiyor.
        sid = str(getattr(session, "id", "") or "")
        self._unsubscribe = session.log.subscribe(
            lambda ev, _sid=sid: self.hub.publish(ev, sid=_sid))
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


class _TekSahipSunucu(ThreadingHTTPServer):
    """Portun tek sahibi olan sunucu.

    Windows'ta SO_REUSEADDR başka bir sürecin dinlediği portun üstüne
    bağlanmayı hata VERMEDEN kabul ediyor ve trafik ilk sahibe akıyor.
    Kapatınca bağlanma dolu portta dürüstçe patlıyor; üst katman da boş
    porta kayabiliyor.
    """

    allow_reuse_address = sys.platform != "win32"


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
        elif route in ("/watch.html", "/watch"):
            self._file("watch.html", "text/html; charset=utf-8")
        elif route == "/logo.png":
            self._logo_png()
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
                        "hazir": tanima.hazir(), "son": d["son_kosu"],
                        "learn_cloud_ok": d.get("learn_cloud_ok", False)})
        elif route == "/api/dil":
            # Kurulum sihirbazının seçtiği arayüz dili. localStorage'a
            # kurulumdan yazılamıyor; sihirbaz çalışma alanına setup.json
            # bırakıyor, ilk açılışta dil.js buradan okuyup kendine yazıyor.
            # Eski sürümler aynı dosyayı kurulum.json adıyla bırakmıştı;
            # setup.json yoksa ona da bakılır — mevcut kurulumlar kırılmaz.
            # Hiçbiri yoksa boş dönülüyor — dil.js Türkçe'ye düşer.
            config = getattr(self.server, "config", None)
            dil = ""
            if config is not None:
                for ad in ("setup.json", "kurulum.json"):
                    try:
                        dil = str(json.loads(
                            (config.workspace / ad).read_text(encoding="utf-8")
                        ).get("dil") or "")
                    except (OSError, ValueError):
                        dil = ""
                    if dil:
                        break
            self._json({"dil": dil})
        elif route == "/api/settings":
            self._settings()
        elif route == "/api/files":
            self._files()
        elif route == "/api/files/search":
            self._files_search()
        elif route == "/api/gorevler":
            self._json(self._controller_call("gorevler") or {"gorevler": [], "kosan": 0})
        elif route == "/api/gorevler/dokum":
            self._gorev_dokumu()
        elif route == "/api/gorevler/rapor":
            self._gorev_raporu()
        elif route == "/api/jobs":
            self._jobs_list()
        elif route == "/api/jobs/runs":
            self._jobs_runs()
        elif route == "/api/workflows":
            self._workflows_list()
        elif route == "/api/plans":
            self._plans_list()
        elif route == "/api/git":
            self._git_status()
        elif route.startswith("/gorev-rapor/"):
            self._gorev_rapor_sayfasi(route)
        elif route == "/api/degisiklikler":
            self._degisiklikler()
        elif route == "/api/degisiklikler/fark":
            self._degisiklik_farki()
        elif route == "/api/camera/frame":
            self._camera_frame()
        elif route == "/api/raw":
            self._raw_file()
        elif route == "/api/gozat":
            self._gozat()
        elif route == "/api/apps":
            self._apps()
        elif route == "/api/projects":
            self._projects()
        elif route == "/api/apps/running":
            self._apps_running()
        elif route == "/api/artifacts":
            self._artifacts_list()
        elif route.startswith("/artifact/"):
            self._artifact_page(route)
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

        # Çapraz-köken koruması: kullanıcının BAŞKA bir tarayıcı sekmesindeki
        # yabancı bir sayfa 127.0.0.1'e durum değiştiren bir POST atarsa
        # (drive-by CSRF) reddedilir. Kendi arayüzümüz aynı-köken → geçer;
        # Origin/Referer hiç yoksa (curl, testler, benchmark, yerel otomasyon)
        # geçer — HTTP katmanında yerel süreç arayüzden ayırt edilemez, o yol
        # zaten kabuk izin kapısıyla korunuyor. Kapatılan gerçek ve önlenebilir
        # tehdit yabancı KÖKEN (güvenlik denetimi, 01.09).
        if self._capraz_koken_mi():
            self.send_error(403, "Capraz koken istegi reddedildi")
            return

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
        if route == "/api/jobs":
            self._jobs_action(body)
            return
        if route == "/api/workflows":
            self._workflows_action(body)
            return
        if route == "/api/plans":
            self._plans_action(body)
            return
        if route == "/api/git":
            self._git_action(body)
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
        if route == "/api/apps/reveal":
            # "Klasörü göster": uygulamanın diskteki yerini dosya gezgininde
            # açar. Kartta yazan yolu kullanıcının elle bulması gerekmesin.
            from .. import apps as catalog
            config = getattr(self.server, "config", None)
            path = str((body or {}).get("path") or "").strip()
            if config is None or not path:
                self._json({"ok": False, "error": "`path` gerekli"})
                return
            self._json(catalog.reveal(config.open_sandbox().root, path,
                                      base=Path(config.workspace)))
            return
        if route == "/api/artifacts":
            self._artifacts_edit(body)
            return
        if route == "/api/disari-ac":
            self._disari_ac(body)
            return
        if route == "/api/artifact/indir":
            self._artifact_indir(body)
            return
        if route == "/api/transfer/import":
            self._transfer_import(raw)
            return
        if route == "/api/reset":
            self._reset(body)
            return
        if route == "/api/gorevler/durdur":
            result = self._controller_call("gorev_durdur", str((body or {}).get("id") or ""))
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Görev durdurma desteklenmiyor."})
            return
        if route == "/api/gorevler/devam":
            result = self._controller_call(
                "gorev_devam",
                str((body or {}).get("id") or ""),
                str((body or {}).get("message") or ""),
            )
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Görev sürdürme desteklenmiyor."})
            return
        if route == "/api/gorevler/iptal":
            result = self._controller_call(
                "gorev_iptal", str((body or {}).get("id") or ""))
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Görev iptali desteklenmiyor."})
            return
        if route == "/api/degisiklikler/geri":
            self._degisiklik_geri(body)
            return
        if route == "/api/butce":
            result = self._controller_call("butce", (body or {}).get("usd"))
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Bütçe freni bu köprüde yok."})
            return
        if route == "/api/compact":
            result = self._controller_call("compact_now")
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Sıkıştırma bu köprüde yok."})
            return
        if route == "/api/session/new":
            # Canlı yeni oturum köprüye bağlı: olay akışının yeni günlüğe
            # yeniden bağlanması gerekiyor. Köprü bunu desteklemiyorsa (ör.
            # salt-gözlem önizlemesi) dürüstçe ok:false dönüyor.
            result = self._controller_call("new_session")
            self._json(result if isinstance(result, dict) else {"ok": False})
            return
        if route == "/api/open":
            # Windows 'Dornick ile aç' / ikinci örnek handoff.
            path = str((body or {}).get("path") or "").strip()
            message = str((body or {}).get("message") or "")
            controller = getattr(self.server, "controller", None)
            fn = getattr(controller, "open_path", None) if controller else None
            if not callable(fn):
                self._json({"ok": False, "error": "açma desteği yok"})
                return
            self._json(fn(path, message=message))
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
        if route == "/api/session/meta":
            # Konuşmaya ad verme ve etiketleme. Ham günlük değişmiyor —
            # yalnızca yanındaki eşleme dosyası (bkz. mind.store).
            mind = getattr(self.server, "mind", None)
            sid = str((body or {}).get("id") or "").strip()
            if mind is None or not hasattr(mind, "set_session_meta"):
                self._json({"ok": False, "error": "oturum meta desteği yok"})
                return
            if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
                self._json({"ok": False, "error": "geçersiz oturum"})
                return
            # Alan GÖNDERİLMEDİYSE dokunulmuyor: yalnızca etiket değiştiren
            # bir istek adı silmemeli.
            ad = body.get("ad") if isinstance(body, dict) else None
            etiketler = body.get("etiketler") if isinstance(body, dict) else None
            path = body.get("path") if isinstance(body, dict) else None
            model = body.get("model") if isinstance(body, dict) else None
            provider = body.get("provider") if isinstance(body, dict) else None
            # `:batch` canlı sohbette 404 — senkron kimliğe indir.
            if isinstance(model, str) and model.strip():
                from ..settings import batch_only_model
                if batch_only_model(model):
                    model = model.strip().rsplit(":", 1)[0]
            kayit = mind.set_session_meta(
                sid,
                ad=None if ad is None else str(ad),
                etiketler=None if not isinstance(etiketler, list) else etiketler,
                path=None if path is None else str(path),
                model=None if model is None else str(model),
                provider=None if provider is None else str(provider),
            )
            # Sohbet-modeli AKTİF oturumda değiştiyse hemen uygulanır —
            # "kaydettim ama hâlâ eski modelle konuşuyor" olmasın.
            if model is not None or provider is not None:
                controller = getattr(self.server, "controller", None)
                aktif = str(getattr(mind, "session_id", "") or "")
                if controller is not None and sid == aktif                         and hasattr(controller, "apply_session_context"):
                    try:
                        controller.apply_session_context(sid)
                    except Exception:
                        pass
            self._json({"ok": True, "meta": kayit})
            return
        if route == "/api/session/archive":
            # Listeden çıkar, günlüğü sessions/.arsiv'e taşı. Kalıcı silme
            # yok. Koşan şeridin günlüğü taşınmaz; açık sohbet önce yeni
            # boş oturuma geçer, sonra eski arşivlenir.
            mind = getattr(self.server, "mind", None)
            sid = str((body or {}).get("id") or "").strip()
            if mind is None or not hasattr(mind, "archive_session"):
                self._json({"ok": False, "error": "arşiv desteği yok"})
                return
            if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
                self._json({"ok": False, "error": "geçersiz oturum"})
                return
            controller = getattr(self.server, "controller", None)
            seritler = getattr(controller, "seritler", None) or {}
            serit = seritler.get(sid) if isinstance(seritler, dict) else None
            if serit is not None and getattr(serit, "busy", False):
                self._json({"ok": False,
                            "error": "koşan sohbet arşivlenemez — tur bitince dene"})
                return
            current = str(getattr(mind, "session_id", "") or "")
            if sid == current:
                result = self._controller_call("new_session")
                if not isinstance(result, dict) or not result.get("ok"):
                    self._json(result if isinstance(result, dict) else {
                        "ok": False, "error": "yeni sohbete geçilemedi",
                    })
                    return
            self._json(mind.archive_session(sid))
            return
        if route == "/api/surum":
            # Güncelleme denetimi YALNIZ elle: Ayarlar › Makine'deki düğme.
            # Arka planda kendiliğinden ağa çıkan denetim bilerek yok.
            # POST: ağa çıkan bir eylem — GET'le yanlışlıkla tetiklenmesin.
            self._json(ortam.guncelleme_denetle())
            return
        if route == "/api/guncelle":
            self._guncelle()
            return
        if route == "/api/gate":
            self._gate(body)
            return
        if route == "/api/tanima":
            self._tanima(body)
            return
        if route == "/api/goals":
            self._goals(body)
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
            ear = getattr(self.server, "ear", None) or getattr(
                getattr(self.server, "controller", None), "ear", None)
            if ear is not None:
                ear.speaking(bool(body.get("on")), text=str(body.get("text") or ""))
            self._json({"ok": True})
            return
        if route == "/api/senses":
            action = str((body or {}).get("action") or "status")
            what = str((body or {}).get("what") or "hearing")
            ctrl = getattr(self.server, "controller", None)
            if action in ("on", "off", "power"):
                on = action == "on" or (
                    action == "power" and bool((body or {}).get("enabled")))
                if action == "off":
                    on = False
                fn = getattr(ctrl, "voice_power" if what == "voice" else "hearing_power", None)
                if fn is None:
                    self._json({"ok": False, "error": "anahtar yok"})
                    return
                note = fn(on)
                self._json({"ok": True, "note": note, "enabled": on})
                return
            self._json(ear_gate(
                getattr(self.server, "ear", None),
                action,
            ))
            return
        if route == "/api/wake":
            # Uyandırma sözü tarayıcı tarafında duyuldu (listen.js): pencere
            # gizliyse geri gelmeli, yoksa cevap görünmeyen bir pencerede
            # akıyor. Python tarafındaki kulak köprüyü doğrudan çağırıyor;
            # tarayıcı tarafının tek yolu buydu ve rota YOKTU — istek sessizce
            # 404 dönüyordu. Pencereyi getiren davranış köprüde zaten var
            # (Bridge.wake → on_wake); burası yalnızca kapıyı açıyor.
            # Köprü uyandırmayı desteklemiyorsa (salt-gözlem önizlemesi)
            # dürüstçe ok:false — "yaptım" demek yapmamaktan kötü.
            uyandirilabilir = callable(
                getattr(getattr(self.server, "controller", None), "wake", None))
            if uyandirilabilir:
                self._controller_call("wake")
            self._json({"ok": uyandirilabilir})
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

        if "learn_cloud_ok" in (body or {}):
            # Mahremiyet onayı: bulut modelle gece etiketlemesine açık izin.
            # Ayrı dal — "on" ile birlikte gelmez, ayar sayfasındaki alt
            # anahtardan tek başına düşer.
            tanima.bulut_onayi_ayarla(config.state_dir,
                                      bool(body.get("learn_cloud_ok")))
            self._json({"ok": True,
                        "learn_cloud_ok": bool(body.get("learn_cloud_ok"))})
            return
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
        elif (body or {}).get("simdi"):
            # "Şimdi eğit" SESSİZ KALMASIN: sonuç kullanıcıya dönüyor.
            # Eski hal düğmeye basınca hiçbir şey göstermiyordu — oysa
            # döngü başlayıp bir saniyede "yeni veri az" deyip çıkıyordu.
            sebep = ("duzenek_yok" if hub is None
                     else tanima.belki_baslat(config.state_dir, hub, zorla=True))
            d = tanima.durum(config.state_dir)
            self._json({"ok": sebep == "basladi", "sebep": sebep,
                        "on": d["on"], "kosuyor": tanima.kosuyor(),
                        "hazir": tanima.hazir(), "son": d["son_kosu"]})
            return

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
        caps = settings.detect_caps(config)
        payload: dict[str, Any] = {
            "window": caps.get("max_context") if isinstance(caps.get("max_context"), int) else None,
        }
        for key in ("thinking", "vision", "tools"):
            if key in caps:
                payload[key] = caps[key]
        self._json(payload)

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

        self._json(settings.scan_models_result(config))

    # -- izlenen kameralar ------------------------------------------------

    def _cameras(self, body: dict[str, Any]) -> None:
        """İzlenen kameraları listeler ve düzenler.

        Değişiklik yeniden başlatınca geçerli oluyor: izleyici kendi
        thread'inde dönüyor ve çalışırken kamera eklemek/çıkarmak açık bir
        akışın ortasına girmek demek.
        """
        from uuid import uuid4

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        cameras = watch.load(config.state_dir)
        action = str(body.get("action") or "list")
        camera_id = str(body.get("id") or "")

        if action == "power":
            on = bool(body.get("enabled"))
            ctrl = getattr(self.server, "controller", None)
            power = getattr(ctrl, "camera_power", None) if ctrl else None
            if power is None:
                self._json({"ok": False, "error": "kamera anahtarı yok"})
                return
            msg = power(on)
            lens = (
                getattr(ctrl, "lens", None)
                or getattr(self.server, "lens", None)
                or getattr(getattr(self.server, "_httpd", None), "lens", None)
            )
            self._json({
                "ok": True,
                "note": msg,
                "enabled": on,
                "live": bool(getattr(lens, "running", False)),
            })
            return

        if action == "add":
            kind = str(body.get("kind") or "usb").strip() or "usb"
            source = str(body.get("source") or "").strip()
            host = str(body.get("host") or "").strip()
            if kind == "usb":
                source = source or str(body.get("index") or "0").strip() or "0"
            cameras.append(
                watch.Camera(
                    id=f"cam_{uuid4().hex[:8]}",
                    name=str(body.get("name") or "").strip()
                         or ("Bilgisayar kamerası" if kind == "usb" and source in ("", "0")
                             else "kamera"),
                    source=source,
                    kind=kind,
                    host=host,
                    port=int(body.get("port") or 0),
                    path=str(body.get("path") or "").strip(),
                    user=str(body.get("user") or "").strip(),
                    password=str(body.get("password") or ""),
                    sensitivity=float(body.get("sensitivity") or 0.06),
                    cooldown_s=int(body.get("cooldown_s") or 60),
                    ask=str(body.get("ask") or ""),
                    analyze=bool(body["analyze"]) if "analyze" in body else True,
                )
            )
        elif action == "update":
            known = set(watch.Camera.__dataclass_fields__)
            for camera in cameras:
                if camera.id != camera_id:
                    continue
                new_pass = body.get("password")
                for name, value in body.items():
                    if name in known and name not in ("id", "password"):
                        setattr(camera, name, value)
                if new_pass:
                    camera.password = str(new_pass)
        elif action == "remove":
            cameras = [c for c in cameras if c.id != camera_id]

        if action in ("add", "update", "remove"):
            watch.save(config.state_dir, cameras)

        # Donanım gerçeği görünür (canlı istek): GPU varsa sürekli
        # izleme/işleme aşamasına aday; yoksa tek kip "sorulunca kesit".
        # Asgari beklenti de yazıyor — kullanıcı neyin neden kapalı
        # olduğunu ekrandan okuyabilmeli.
        try:
            from .. import gpu as gpu_mod
            gpus = [{"name": g.name, "total_mb": g.total_mb,
                     "free_mb": g.free_mb} for g in gpu_mod.nvidia_gpus()]
        except Exception:
            gpus = []
        from .. import sight as sight_mod
        if config.camera.enabled:
            sight_mod.ensure_warmup()
        goz = sight_mod.status()
        gpu_var = any(g["total_mb"] >= 4096 for g in gpus)
        if goz.get("ready"):
            kip = "gpu"
        elif gpu_var:
            kip = "izleme"
        else:
            kip = "kesit"
        self._json({
            "ok": True,
            "available": watch.available(),
            # Yerel kamera kullanımı ana anahtarı (Ayarlar › Kamera):
            # üstteki durum ikonu buradan besleniyor.
            "enabled": bool(config.camera.enabled),
            "live": bool(getattr(getattr(self.server, "lens", None), "running", False)
                         or getattr(getattr(getattr(self.server, "controller", None), "lens", None), "running", False)),
            "cloud_ok": bool(getattr(config.camera, "cloud_ok", False)),
            "cameras": [c.public_dict() for c in cameras],
            "gpus": gpus,
            "sight": goz,
            # gpu: CUDA'da yerel analiz çalışıyor, modele metin gidiyor.
            # izleme: kart var ama oturum henüz/hiç açılmadı.
            # kesit: GPU yok — sorulunca kare.
            "vision_mode": kip,
            "min_spec": "Sürekli izleme/işleme için ≥4 GB VRAM'li NVIDIA GPU; "
                        "yoksa sorulduğunda kesit alınır.",
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
                # Akış kimliği verildiyse görev otomasyondur. Bu iki alan
                # eskiden burada DÜŞÜYORDU: zamanlayıcı, koşucu ve arayüz
                # `kind_ui`/`workflow_id` biliyordu ama onları yazabilen
                # hiçbir yol yoktu — otomasyon kurulamıyor, süzgeç hep boş
                # kalıyordu.
                akis = str(body.get("workflow_id") or "").strip()
                book.add(
                    scheduling.Task(
                        id="",
                        title=str(body.get("title") or "").strip() or "adsız görev",
                        prompt=str(body.get("prompt") or ""),
                        kind=str(body.get("kind") or "every"),
                        every_s=int(body.get("every_s") or 3600),
                        at=str(body.get("at") or "09:00"),
                        kind_ui="automation" if akis else "simple",
                        workflow_id=akis,
                    )
                )
            elif action == "update":
                fields = {k: v for k, v in body.items() if k not in ("action", "id")}
                book.update(task_id, **fields)
            elif action == "remove":
                book.remove(task_id)
            elif action == "run":
                # Elle çalıştırma: zamanı beklemeden arka plan yardımcı.
                task = book.get(task_id)
                controller = getattr(self.server, "controller", None)
                if task is None or controller is None:
                    self.send_error(404, "Görev yok")
                    return
                if hasattr(controller, "run_scheduled"):
                    result = controller.run_scheduled(task)
                    if not isinstance(result, dict) or not result.get("ok"):
                        self._json({
                            "ok": False,
                            "error": str((result or {}).get("error") or "başlatılamadı"),
                            "tasks": scheduling.payload(book.all()),
                        })
                        return
                else:
                    book.note_run(task_id, "elle çalıştırıldı")
                    controller.submit(task.prompt)
            elif action in ("missed_run", "missed_skip"):
                result = self._controller_call(
                    "resolve_missed",
                    "run" if action == "missed_run" else "skip",
                )
                if not isinstance(result, dict) or not result.get("ok"):
                    self._json({
                        "ok": False,
                        "error": str((result or {}).get("error") or "işlenemedi"),
                        "tasks": scheduling.payload(book.all()),
                    })
                    return
        except (ValueError, TypeError) as exc:
            self._json({"ok": False, "error": str(exc), "tasks": scheduling.payload(book.all())})
            return

        self._json({"ok": True, "tasks": scheduling.payload(book.all())})

    def _jobs_list(self) -> None:
        """Ana ekran Görevler: zamanlanmış işler + son koşum özeti."""
        from .. import task_runs

        book = getattr(self.server, "schedule", None)
        config = getattr(self.server, "config", None)
        if book is None or config is None:
            self._json({"ok": False, "error": "zamanlayıcı yok", "tasks": []})
            return
        rows = []
        for task in scheduling.payload(book.all()):
            tid = task.get("id") or ""
            runs = []
            try:
                runs = [task_runs.to_dict(r) for r in
                        task_runs.list_runs(config.state_dir, tid, limit=5)]
            except Exception:
                runs = []
            task["recent_runs"] = runs
            rows.append(task)
        self._json({"ok": True, "tasks": rows})

    def _jobs_runs(self) -> None:
        """Tek görevin koşum arşivi: ?id=<task_id>&run=<run_id?>"""
        from .. import task_runs

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "yapılandırma yok"})
            return
        q = parse_qs(urlparse(self.path).query)
        tid = (q.get("id") or [""])[0]
        rid = (q.get("run") or [""])[0]
        if not tid:
            self._json({"ok": False, "error": "id gerekli"})
            return
        try:
            if rid:
                run = task_runs.get_run(config.state_dir, tid, rid)
                if run is None:
                    self._json({"ok": False, "error": "koşum yok"})
                    return
                self._json({"ok": True, "run": task_runs.to_dict(run)})
                return
            runs = [task_runs.to_dict(r) for r in
                    task_runs.list_runs(config.state_dir, tid, limit=80)]
            self._json({"ok": True, "runs": runs})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)})

    def _jobs_action(self, body: dict[str, Any]) -> None:
        """Ana ekrandan Çalıştır / güncelle — /api/tasks ile aynı defter."""
        self._tasks(body)

    def _workflows_list(self) -> None:
        from .. import workflows

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "workflows": []})
            return
        rows = []
        for wf in workflows.list_all(config.state_dir):
            rows.append({
                "id": wf.id, "title": wf.title,
                "nodes": len(wf.nodes), "edges": len(wf.edges),
                "updated": wf.updated,
            })
        self._json({"ok": True, "workflows": rows})

    def _workflows_action(self, body: dict[str, Any]) -> None:
        from .. import workflows

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "yapılandırma yok"})
            return
        action = str((body or {}).get("action") or "").strip()
        try:
            if action == "get":
                wf = workflows.get(config.state_dir, str(body.get("id") or ""))
                if wf is None:
                    self._json({"ok": False, "error": "akış yok"})
                    return
                self._json({"ok": True, "workflow": workflows.to_dict(wf)})
                return
            if action == "save":
                payload = body.get("workflow") or body
                wf = workflows.save(config.state_dir, payload)
                # Arayüzden kaydedilen akış da hafızaya girsin: kayıt yolu
                # araca göre değişirse, "daha önce yapmıştım" anı bazen
                # geliyor bazen gelmiyor olurdu.
                from .. import workflow_mind
                workflow_mind.akisi_hatirla(getattr(self.server, "mind", None), wf)
                self._json({"ok": True, "workflow": workflows.to_dict(wf)})
                return
            if action == "remove":
                ok = workflows.remove(config.state_dir, str(body.get("id") or ""))
                self._json({"ok": ok})
                return
            if action == "run":
                # Elle çalıştırma, zamanlayıcının kullandığı YOLUN AYNISI:
                # takvimsiz bir Task ile `run_scheduled`. Böyle olması şart —
                # elle koşan akış ile zamanlı koşan akış farklı yollardan
                # giderse ikisi ayrı ayrı bozulur ve biri çalışırken diğeri
                # çalışmaz. Kimliksiz Task defteri kirletmiyor: `mark_running`
                # ve `note_run` boş id'de hiçbir şey yazmıyor.
                wid = str(body.get("id") or "")
                controller = getattr(self.server, "controller", None)
                if controller is None or not hasattr(controller, "run_scheduled"):
                    self._json({"ok": False, "error": "koşturucu yok"})
                    return
                from ..schedule import Task
                gecici = Task(id="", title=wid, prompt=".", kind_ui="automation",
                              workflow_id=wid)
                result = controller.run_scheduled(gecici)
                self._json(result if isinstance(result, dict)
                           else {"ok": False, "error": "koşturulamadı"})
                return
            self._json({"ok": False, "error": "bilinmeyen eylem"})
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _plans_list(self) -> None:
        from .. import plans as plan_store

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": True, "plans": []})
            return
        self._json({"ok": True, "plans": plan_store.listing(config.state_dir)})

    def _plans_action(self, body: dict[str, Any]) -> None:
        from .. import plans as plan_store

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "yapılandırma yok"})
            return
        action = str((body or {}).get("action") or "").strip()
        try:
            if action == "create":
                plan = plan_store.create(
                    config.state_dir,
                    title=str(body.get("title") or "Plan"),
                    steps=body.get("steps") or [],
                )
                self._json({"ok": True, "plan": plan_store.to_dict(plan)})
                # SSE: arayüz Plan kartını çizsin.
                hub = getattr(self.server, "hub", None)
                if hub is not None:
                    hub.emit({"type": "plan", **plan_store.to_dict(plan)})
                return
            if action == "update":
                plan = plan_store.update(
                    config.state_dir, str(body.get("id") or ""),
                    status=body.get("status"),
                    steps=body.get("steps"),
                    title=body.get("title"),
                )
                if plan is None:
                    self._json({"ok": False, "error": "plan yok"})
                    return
                self._json({"ok": True, "plan": plan_store.to_dict(plan)})
                hub = getattr(self.server, "hub", None)
                if hub is not None:
                    hub.emit({"type": "plan", **plan_store.to_dict(plan)})
                return
            if action == "approve":
                plan = plan_store.update(
                    config.state_dir, str(body.get("id") or ""),
                    status="onaylandi")
                if plan is None:
                    self._json({"ok": False, "error": "plan yok"})
                    return
                # Onay → ajana devam notu.
                controller = getattr(self.server, "controller", None)
                if controller is not None and hasattr(controller, "submit"):
                    controller.submit(
                        f"[Plan onaylandı · {plan.id}] {plan.title}. "
                        f"Adımları uygula:\n" + "\n".join(
                            f"- {s.get('text') or s}" for s in (plan.steps or [])),
                        siraya=True)
                self._json({"ok": True, "plan": plan_store.to_dict(plan)})
                hub = getattr(self.server, "hub", None)
                if hub is not None:
                    hub.emit({"type": "plan", **plan_store.to_dict(plan)})
                return
            if action == "cancel":
                plan = plan_store.update(
                    config.state_dir, str(body.get("id") or ""),
                    status="iptal")
                self._json({"ok": True, "plan": plan_store.to_dict(plan) if plan else None})
                return
            self._json({"ok": False, "error": "bilinmeyen eylem"})
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _git_status(self) -> None:
        from .. import git as gitmod

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": True, "present": False})
            return
        snap = gitmod.snapshot(config)
        if not snap.get("present"):
            # Depo yokken de çalışma klasörü çubukta görünsün: "Repo aç"
            # ve "klasörü aç" oradan yaşıyor (canlı istek, 31.08). YALNIZ
            # atanmış proje: atölye karalama alanıdır, repo yüzeyi değil
            # ("atölye için repo açmaması lazım" — 01.09).
            try:
                box = config.open_sandbox()
                if box.project is not None:
                    snap = {**snap, "root": str(box.project),
                            "name": Path(box.project).name}
            except Exception:
                pass
        self._json(snap)

    def _git_action(self, body: dict[str, Any]) -> None:
        from .. import git as gitmod

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "yapılandırma yok"})
            return
        action = str((body or {}).get("action") or "").strip()
        root = gitmod.repo_root(config)
        try:
            if action == "diff":
                if root is None:
                    self._json({"ok": False, "error": "git deposu yok"})
                    return
                path = str(body.get("path") or "") or None
                self._json(gitmod.diff(root, path))
                return
            if action in ("commit", "push", "pull", "create_repo", "publish", "init"):
                result = self._git_mutate(gitmod, config, root, action, body or {})
                self._json(result)
                if result.get("ok"):
                    hub = getattr(self.server, "hub", None)
                    if hub is not None:
                        hub.emit({"type": "git", "action": action})
                return
            self._json({"ok": False, "error": "bilinmeyen eylem"})
        except gitmod.GitError as exc:
            self._json({"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _git_mutate(
        self, gitmod: Any, config: Any, root: Any, action: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        box = config.open_sandbox()
        if root is None:
            root = box.project or box.root
        private = body.get("private")
        if private is None:
            private = True
        name = str(body.get("name") or "").strip()
        if action == "init":
            return {"ok": True, **gitmod.init(root)}
        if action == "commit":
            paths = body.get("paths")
            if not isinstance(paths, list):
                paths = None
            snap = gitmod.commit(root, str(body.get("message") or ""), paths=paths)
            return {"ok": True, **snap}
        if action == "push":
            return {"ok": True, **gitmod.push(root)}
        if action == "pull":
            return {"ok": True, **gitmod.pull(root)}
        if action == "create_repo":
            created = gitmod.create_repo(
                name or (root.name if root is not None else ""),
                private=bool(private),
                source=root,
                state_dir=config.state_dir,
            )
            return {"ok": True, **created}
        snap = gitmod.publish(
            root, name=name, private=bool(private), state_dir=config.state_dir,
        )
        return {"ok": True, **snap}

    # -- hedef yığını -----------------------------------------------------

    def _goals(self, body: dict[str, Any]) -> None:
        """Hedef panelinin yönetim ucu: bitir, bırak, tümünü temizle.

        Panel eskiden salt gösterimdi ve kullanıcı haklı olarak soruyordu:
        "bunlar nereden ekleniyor, nereden temizleniyor?" Ajan `mind_goals`
        ile ekliyor; kullanıcının elinde hiçbir şey yoktu ve eski
        oturumlardan kalan hedefler birikip duruyordu. Artık aynı deftere
        kullanıcı da yazabiliyor — ajanın kullandığı yolun (set_goal_status)
        aynısı, ayrı bir gerçeklik üretilmiyor.

        Eylemler: done (tamamlandı), drop (kaldır), clear (aktif olanların
        tümünü bırak).
        """
        mind = getattr(self.server, "mind", None)
        if mind is None or not hasattr(mind, "set_goal_status"):
            self._json({"ok": False, "error": "hedef desteği yok"})
            return

        action = str((body or {}).get("action") or "").strip()
        if action == "add":
            # Liste artık iki taraflı: ajan `mind_goals` ile yazıyor,
            # kullanıcı da buradan. Aynı defter — ayrı bir gerçeklik
            # üretmiyoruz, ajan kendi maddesini de görüyor.
            metin = str((body or {}).get("text") or "").strip()
            if not metin:
                self._json({"ok": False, "error": "boş madde"})
                return
            try:
                goal = mind.push_goal(metin[:GOAL_TEXT_LIMIT])
            except Exception as exc:
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            self._json({"ok": True, "id": goal.id, "text": goal.text})
            return

        if action == "clear":
            try:
                for goal in mind.goals():
                    mind.set_goal_status(goal.id, "dropped", "kullanıcı temizledi")
            except Exception as exc:
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            self._json({"ok": True, "goals": []})
            return

        if action not in ("done", "drop"):
            self._json({"ok": False, "error": "bilinmeyen eylem"})
            return

        gid = str((body or {}).get("id") or "").strip()
        if not gid or not re.match(r"^[A-Za-z0-9_-]+$", gid):
            self._json({"ok": False, "error": "geçersiz hedef"})
            return
        try:
            updated = mind.set_goal_status(
                gid, "done" if action == "done" else "dropped",
                "kullanıcı işaretledi")
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return
        if updated is None:
            self._json({"ok": False, "error": "hedef bulunamadı"})
            return
        self._json({"ok": True, "id": gid, "status": updated.status})

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
            self.send_error(501, listen.hint())
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
            try:
                authored.save(root, name, str(body.get("code") or ""))
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

    def _files_search(self) -> None:
        """`@` dosya bahsi: çalışma alanında ada göre hızlı arama.

        `/api/files` bir dizini listeliyor; bu uç TÜM alanda arıyor. Aynı
        kapıdan geçiyor: kök çalışma alanı, dışına çıkacak bir yol yok
        (istekten gelen tek şey arama metni, bir yol değil).
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        want = (parse_qs(urlparse(self.path).query).get("q", [""])[0] or "").strip().lower()
        root = Path(config.workspace).resolve()
        self._json({"q": want, "files": _search_files(root, want)})

    def _gorev_dokumu(self) -> None:
        """Bir yardımcının ADIM listesi: `?oturum=<id>`.

        `/api/session` bir konuşmanın METİN turlarını veriyor — bir
        yardımcıya bakarken sorulan soru o değil: "ne yaptı?". Burada
        araç çağrıları da var, sırayla: hangi aracı hangi hedefle çağırdı,
        başardı mı, kaç ms sürdü. Kaynak yardımcının kendi oturum günlüğü;
        ikinci bir defter tutulmuyor.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "Yapılandırma yüklü değil"})
            return
        sid = parse_qs(urlparse(self.path).query).get("oturum", [""])[0]
        if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
            self._json({"ok": False, "error": "geçersiz oturum"})
            return
        path = Path(config.sessions_dir) / f"{sid}.jsonl"
        if not path.is_file():
            self._json({"ok": False, "error": "Oturum günlüğü bulunamadı."})
            return

        adimlar: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as fh:
                for satir in fh:
                    if not (satir := satir.strip()):
                        continue
                    try:
                        ev = json.loads(satir)
                    except ValueError:
                        continue
                    meta = ev.get("meta") or {}
                    if ev.get("content") == "tool_start":
                        adimlar.append({
                            "tur": "arac",
                            "ad": str(meta.get("tool") or ""),
                            "hedef": _hedef_ozeti(meta.get("input")),
                        })
                    elif ev.get("content") == "tool_end" and adimlar:
                        # Son açık araç adımını kapatıyor: ayrı bir satır
                        # açmak listeyi ikiye katlar, okunmaz.
                        son = adimlar[-1]
                        if son.get("tur") == "arac" and "hata" not in son:
                            son["hata"] = bool(meta.get("error"))
                            son["ms"] = int(meta.get("ms") or 0)
                    elif ev.get("role") == "assistant" and ev.get("kind") == "message":
                        if meta.get("internal") or meta.get("continuation"):
                            continue
                        metin = "\n".join(_plain_blocks(ev.get("content"))).strip()
                        if metin:
                            adimlar.append({"tur": "soz", "metin": metin[:2000]})
        except OSError as exc:
            self._json({"ok": False, "error": f"Günlük okunamadı: {exc}"})
            return
        # Uzun bir koşuda yüzlerce adım olabiliyor; son 200 yeter.
        self._json({"ok": True, "oturum": sid, "adimlar": adimlar[-200:]})

    def _gorev_raporu(self) -> None:
        """Tam yardımcı/iş metni: `?id=c:<cid>` — paneller Viewer'a açar."""
        result = self._controller_call(
            "gorev_rapor",
            parse_qs(urlparse(self.path).query).get("id", [""])[0],
        )
        self._json(result if isinstance(result, dict)
                   else {"ok": False, "error": "Rapor bu köprüde yok."})

    def _gorev_rapor_sayfasi(self, route: str) -> None:
        """Artifact benzeri sayfa: /gorev-rapor/<cid>/ → HTML rapor."""
        cid = route[len("/gorev-rapor/"):].strip("/")
        # URL'de yalnız ham id; API tarafı c: öneki de kabul eder.
        result = self._controller_call("gorev_rapor", cid)
        if not isinstance(result, dict) or not result.get("ok"):
            self.send_error(404, str((result or {}).get("error") or "Rapor yok"))
            return
        title_doc, h1, badge, ozet, komut = _rapor_kapak(result)
        title = html.escape(title_doc)
        metin = str(result.get("metin") or "")
        body = _rapor_html(metin)
        deliverable = result.get("deliverable") if isinstance(result.get("deliverable"), dict) else None
        app_block = ""
        if deliverable and deliverable.get("kind") == "app" and deliverable.get("url"):
            app_url = html.escape(str(deliverable["url"]))
            app_block = (
                f'<p class="cta"><a class="btn" href="{app_url}" target="_blank" rel="noopener">'
                f"Canlı uygulamayı aç</a></p>"
                f'<iframe class="live" src="{app_url}" title="Canlı uygulama"></iframe>'
            )
        elif deliverable and deliverable.get("kind") == "artifact" and deliverable.get("url"):
            art = html.escape(str(deliverable["url"]))
            app_block = (
                f'<p class="cta"><a class="btn" href="{art}">Yayınlanan raporu aç</a></p>'
            )
        meta_bits = []
        if badge:
            meta_bits.append(f'<p class="meta">{badge}</p>')
        if ozet:
            meta_bits.append(f'<p class="ozet">{html.escape(ozet)}</p>')
        if komut:
            goster = komut if len(komut) <= 120 else komut[:117] + "…"
            meta_bits.append(
                f'<p class="cmd"><code title="{html.escape(komut)}">'
                f"{html.escape(goster)}</code></p>"
            )
        meta_html = "\n".join(meta_bits)
        page = (
            "<!doctype html><html lang=tr><head><meta charset=utf-8>"
            f"<title>{title}</title>"
            "<style>"
            "html,body{margin:0;background:#0b1218;color:#dceefc;"
            "font:16px/1.65 system-ui,Segoe UI,sans-serif}"
            "html{scrollbar-width:thin;scrollbar-color:rgba(79,227,255,.35) transparent}"
            "::-webkit-scrollbar{width:8px;height:8px}"
            "::-webkit-scrollbar-thumb{background:rgba(79,227,255,.3);border-radius:4px}"
            "main{max-width:640px;margin:0 auto;padding:36px 28px 56px}"
            "h1{font:600 26px/1.25 system-ui;margin:0 0 10px;color:#eaf6ff}"
            ".meta{font:13px/1.5 system-ui;color:#8fb0cc;margin:0 0 10px}"
            ".ozet{font:15px/1.55 system-ui;color:#dceefc;margin:0 0 12px}"
            ".cmd{margin:0 0 22px}"
            ".cmd code,.meta code{font:12.5px/1.45 ui-monospace,Consolas,monospace;"
            "background:#05121d;padding:4px 9px;border-radius:6px;color:#c5e4ff;"
            "display:inline-block;max-width:100%;word-break:break-word}"
            ".badge{display:inline-block;padding:2px 9px;border-radius:999px;"
            "font:600 11px/1.4 system-ui;letter-spacing:.02em;"
            "background:#1a2a38;color:#8fb0cc;vertical-align:middle}"
            ".badge.err{background:#ff4d6d22;color:#ff8aa0}"
            ".badge.ok{background:#3dffa018;color:#8affc1}"
            ".cta{margin:0 0 16px}"
            ".btn{display:inline-block;padding:8px 14px;border-radius:8px;"
            "background:#4fe3ff22;color:#4fe3ff;text-decoration:none;font:600 13px system-ui}"
            ".btn:hover{background:#4fe3ff33}"
            "iframe.live{width:100%;height:min(70vh,720px);border:1px solid #1e3a4c;"
            "border-radius:10px;background:#061018;margin:0 0 22px}"
            ".rapor{word-break:break-word}"
            ".rapor p{margin:.55em 0}"
            ".rapor h2{font:600 15px/1.3 system-ui;margin:1.5em 0 .4em;color:#a8e8ff}"
            ".rapor h3{font:600 14px/1.3 system-ui;margin:1.2em 0 .4em;color:#a8e8ff}"
            ".rapor ul{padding-left:1.2em;margin:.5em 0}"
            ".rapor li{margin:.25em 0}"
            ".rapor a{color:#4fe3ff}"
            ".rapor code{font:13px ui-monospace,Consolas,monospace;"
            "background:#05121d;padding:1px 5px;border-radius:4px}"
            ".rapor details.log{margin:1.2em 0;border:1px solid #1e3a4c;"
            "border-radius:8px;background:#061018;padding:8px 12px}"
            ".rapor details.log summary{cursor:pointer;color:#8fb0cc;"
            "font:600 12.5px/1.4 system-ui;user-select:none}"
            ".rapor details.log pre{margin:10px 0 4px;white-space:pre-wrap;"
            "word-break:break-word;font:12px/1.5 ui-monospace,Consolas,monospace;"
            "color:#a8c4d8;max-height:min(50vh,420px);overflow:auto}"
            "</style></head><body><main>"
            f"<h1>{html.escape(h1)}</h1>"
            f"{meta_html}"
            f"{app_block}"
            f"<div class=rapor>{body}</div>"
            "</main></body></html>"
        ).encode("utf-8")
        self._send(200, "text/html; charset=utf-8", page)

    # -- değişiklik defteri ---------------------------------------------

    def _defter(self) -> Any:
        """Bu oturumun değişiklik defteri (`tools/checkpoint.Defter`).

        Defteri araç katmanı yazıyor (write_file/edit_file/copy_in her
        değişiklikten önce), burası YALNIZCA okuyor ve `undo` aracının
        kullandığı geri alma yolunu çağırıyor. İkinci bir gerçek kaynak
        üretilmiyor: panelin gördüğü şey ajanın gördüğüyle aynı.
        """
        from ..tools.checkpoint import KLASOR, Defter

        config = getattr(self.server, "config", None)
        if config is None:
            return None
        mind = getattr(self.server, "mind", None)
        sid = str(getattr(mind, "session_id", "") or "")
        if not sid:
            snap = self._controller_call("snapshot") or {}
            sid = str(snap.get("session") or "")
        if not sid:
            return None
        return Defter(Path(config.state_dir) / KLASOR, sid)

    def _degisiklikler(self) -> None:
        """Bu oturumda yazılan/düzenlenen dosyalar.

        `?since=N` verilirse yalnızca N'den sonraki kayıtlar döner —
        arayüzdeki "bu turda ne değişti" şeridi tam olarak bunu kullanıyor:
        tur başında `son`u alıyor, tur bitince ondan sonrasını soruyor.
        """
        defter = self._defter()
        if defter is None:
            self._json({"son": 0, "kayitlar": []})
            return
        try:
            since = int(parse_qs(urlparse(self.path).query).get("since", ["0"])[0])
        except ValueError:
            since = 0
        kayitlar = defter.listele(tavan=200)      # en yenisi önce
        son = kayitlar[0]["sira"] if kayitlar else 0
        out = []
        for k in kayitlar:
            if since and k["sira"] <= since:
                continue
            dosya = str(k.get("dosya") or "")
            out.append({
                "sira": k["sira"],
                "dosya": dosya,
                "ad": dosya.replace("\\", "/").rsplit("/", 1)[-1],
                "arac": k.get("arac") or "",
                "zaman": k.get("zaman") or "",
                "yoktu": bool(k.get("yoktu")),
                "atlandi": k.get("atlandi") or "",
                # Görüntüsü olmayan kayıt geri alınamıyor; arayüz bunu
                # gizlemiyor, satırın yanında söylüyor.
                "gerialinabilir": bool(k.get("goruntu")) or bool(k.get("yoktu")),
            })
        self._json({"son": son, "kayitlar": out})

    def _degisiklik_farki(self) -> None:
        """Tek bir kaydın farkı: `?sira=N` → {eski, yeni}.

        `eski` defterdeki anlık görüntü, `yeni` dosyanın ŞU ANKİ hali.
        Yani gösterilen şey "bu kayıttan bu yana ne oldu" — kullanıcının
        geri alma düğmesine basınca göreceği değişimin aynısı.
        """
        defter = self._defter()
        if defter is None:
            self._json({"ok": False, "error": "Değişiklik defteri yok."})
            return
        try:
            sira = int(parse_qs(urlparse(self.path).query).get("sira", ["0"])[0])
        except ValueError:
            sira = 0
        kayit = next((k for k in defter.listele(tavan=200) if k["sira"] == sira), None)
        if kayit is None:
            self._json({"ok": False, "error": "Kayıt bulunamadı."})
            return

        def _oku(path: Path) -> tuple[str, bool]:
            try:
                data = path.read_bytes()[:DIFF_LIMIT]
            except OSError:
                return "", False
            try:
                # Satır sonu normalleştiriliyor: fark çizici "\n" ile
                # bölüyor ve Windows'ta her satırın ucunda görünmez bir
                # "\r" kalıyordu — değişmemiş satırlar bile değişmiş gibi
                # duruyordu. Bu bir GÖRÜNTÜ ucu; diske dokunmuyor.
                return data.decode("utf-8").replace("\r\n", "\n"), True
            except UnicodeDecodeError:
                return "", False

        dosya = Path(str(kayit.get("dosya") or ""))
        eski, eski_ok = ("", True) if kayit.get("yoktu") else (
            _oku(defter.dizin / str(kayit.get("goruntu")))
            if kayit.get("goruntu") else ("", False))
        yeni, yeni_ok = _oku(dosya) if dosya.exists() else ("", True)
        self._json({
            "ok": True,
            "sira": sira,
            "dosya": str(dosya),
            "ad": dosya.name,
            "eski": eski,
            "yeni": yeni,
            "yoktu": bool(kayit.get("yoktu")),
            # İkili ya da okunamayan dosyada fark çizilmiyor; sebebi yazıyor.
            "metin": bool(eski_ok and yeni_ok),
            "atlandi": kayit.get("atlandi") or "",
        })

    def _degisiklik_geri(self, body: dict[str, Any]) -> None:
        """Değişiklik geri alır — `undo` aracının kullandığı yol.

        Gövde seçenekleri:
          * `{n}` — son n kayıt (tur undo)
          * `{sira}` — tek kayıt (dosya Keep/Undo)
          * `{siralar: [...]}` — birden fazla kayıt (Accept All dışı toplu undo)

        Onay arayüzde. Görüntüsüz kayıtta defter hiçbir şey yazmaz (n yolu)
        ya da o satırı reddeder (sira yolu).
        """
        defter = self._defter()
        if defter is None:
            self._json({"ok": False, "error": "Değişiklik defteri yok."})
            return
        body = body or {}
        hub = getattr(self.server, "hub", None)
        yapilan: list[str] = []
        hata: str | None = None

        if body.get("sira") is not None or body.get("siralar") is not None:
            ham = body.get("siralar")
            if ham is None:
                ham = [body.get("sira")]
            if not isinstance(ham, list) or not ham:
                self._json({"ok": False, "error": "Geçersiz sira listesi."})
                return
            siralar: list[int] = []
            for x in ham:
                try:
                    siralar.append(int(x))
                except (TypeError, ValueError):
                    self._json({"ok": False, "error": "Geçersiz sira."})
                    return
            # En yeniden eskiye: aynı dosyada üst üste kayıt varsa doğru sıra.
            for sira in sorted(siralar, reverse=True):
                parca, err = defter.geri_al_sira(sira)
                yapilan.extend(parca)
                if err:
                    hata = err
                    break
        elif body.get("dosya"):
            yapilan, hata = defter.geri_al_dosya(str(body.get("dosya") or ""))
        else:
            try:
                n = int(body.get("n") or 1)
            except (TypeError, ValueError):
                n = 1
            n = max(1, min(n, 200))
            yapilan, hata = defter.geri_al(n)

        if hata:
            self._json({"ok": False, "error": hata, "yapilan": yapilan})
            return
        if hub is not None:
            hub.emit({"type": "notice",
                      "text": f"Geri alındı: {len(yapilan)} değişiklik eski haline döndü."})
        self._json({"ok": True, "yapilan": yapilan})

    def _camera_frame(self) -> None:
        """Bir kameradan TEK taze kare (JPEG) — izleme alanının önizlemesi.

        Sürekli akış (MJPEG/WebRTC) yok. Dahili kamera zaten Lens
        tamponunda açıksa o JPEG kullanılır — aynı aygıtı ikinci kez
        açmak Windows'ta güverteyi kilitler. Ağ kameraları tek kesit.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        if not watch.available():
            self.send_error(501, "opencv kurulu değil")
            return
        query = parse_qs(urlparse(self.path).query)
        kaynak = (query.get("source", [""])[0] or "").strip()
        cid = (query.get("id", [""])[0] or "").strip()
        cam = None
        if cid:
            cam = next((c for c in watch.load(config.state_dir)
                        if c.id == cid), None)
            if cam is None:
                self.send_error(404, "kamera yok")
                return
            kaynak = str(cam.connect_source())
        kaynak = kaynak or "0"

        lens = getattr(self.server, "lens", None)
        if lens is None:
            ctrl = getattr(self.server, "controller", None)
            lens = getattr(ctrl, "lens", None) if ctrl else None
        payload = watch.preview_jpeg(kaynak, lens=lens)
        if not payload:
            if lens is not None and watch.same_source(
                    getattr(lens, "source", "0"), kaynak):
                self.send_error(503, "kamera henüz hazır değil")
                return
            self.send_error(502, "kamera açılamadı")
            return
        ozet = ""
        want_boxes = (query.get("boxes", ["0"])[0] or "0") not in ("0", "false", "")
        if cam is None:
            cam = next((c for c in watch.load(config.state_dir)
                        if c.is_builtin()), None)
        analyze = True if cam is None else bool(getattr(cam, "analyze", True))
        if want_boxes and analyze:
            from .. import sight as sight_mod
            payload, ozet = sight_mod.annotate_jpeg(
                payload, key=cid or kaynak or "0")
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Expose-Headers", "X-Dornick-Sight")
        if ozet:
            self.send_header("X-Dornick-Sight", quote(ozet, safe=" ,()-"))
        self.end_headers()
        self.wfile.write(payload)

    def _raw_file(self) -> None:
        """Bir dosyanın HAM baytları: görüntüleyicinin görsel/ses/video/PDF ucu.

        `/api/files` metin döndürüyor; bir PNG oradan yalnızca "ikili dosya"
        olarak geliyordu ve panel görseli gösteremiyordu. Bu uç aynı KAPIDAN
        geçiyor: yol istekten geliyor, o yüzden çözümlenip çalışma alanının
        altında kaldığı doğrulanıyor (`..` ile yukarı çıkmak dizin dışına
        çıkma açığının klasik yolu).

        İçerik türü UZANTIDAN veriliyor ve yalnızca bilinen bir medya
        listesinden: tarayıcının içeriğe bakıp kendi kararını vermesi
        (sniffing) bir metin dosyasını HTML sayıp çalıştırabilirdi.
        Tanınmayan uzantı `application/octet-stream` — yani indirilir,
        yorumlanmaz. `X-Content-Type-Options: nosniff` bunu mühürlüyor.
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
        if not target.is_file():
            self.send_error(404)
            return

        kind = RAW_TYPES.get(target.suffix.lower(), "application/octet-stream")
        try:
            size = target.stat().st_size
        except OSError:
            self.send_error(404)
            return

        # Menzil isteği: video/ses oynatıcıları ileri sarabilmek için bunu
        # kullanıyor. Tek menzil yeterli; anlaşılmayan başlık yok sayılıp
        # dosyanın tamamı gönderiliyor.
        start, end = 0, size - 1
        partial = False
        if size and (raw_range := self.headers.get("Range", "")).startswith("bytes="):
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", raw_range.strip())
            if match and (match.group(1) or match.group(2)):
                if match.group(1):
                    start = int(match.group(1))
                    if match.group(2):
                        end = int(match.group(2))
                else:                                   # "bytes=-500": sondan
                    start = max(0, size - int(match.group(2)))
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                partial = True

        length = end - start + 1 if size else 0
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        if query.get("download", [""])[0]:
            # Sohbetteki "raporu indir" bağının ucu: attachment başlığı
            # tarayıcıyı yorumlamak yerine kaydetmeye zorlar. Ad ASCII'ye
            # inceltiliyor — başlık satırına ham UTF-8 koymak bazı
            # istemcilerde kırılıyor.
            temiz = re.sub(r"[^\w.\-]", "_", target.name) or "dosya"
            self.send_header("Content-Disposition",
                             f'attachment; filename="{temiz}"')
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        # Parça parça: bir video dosyasını belleğe almak sunucuyu düşürürdü.
        try:
            with target.open("rb") as handle:
                handle.seek(start)
                left = length
                while left > 0:
                    chunk = handle.read(min(64 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (OSError, BrokenPipeError, ConnectionError):
            # Başlıklar gitti; burada yapılabilecek tek şey susmak.
            self.close_connection = True

    def _gozat(self) -> None:
        """Klasör gezgini: proje seçmek için KLASÖRLERİ listeler.

        Neden ayrı bir uç: `/api/files` çalışma alanının içinde kalıyor ve
        proje tam olarak onun DIŞINDA bir yer. Native bir klasör diyaloğu
        da kullanılamıyor (masaüstü katmanı ayrı bir işte), o yüzden seçici
        tarayıcının kendi içinde.

        Yeni bir maruziyet sınıfı değil: okuma bu programda zaten her yerde
        serbest (ajanın `list_dir`i tam da bunu yapıyor). Burada yalnızca
        klasör ADLARI dönüyor — dosya içeriği yok, dosya listesi yalnızca
        sayı olarak. Yazma tarafı bundan etkilenmiyor: seçmek yazma iznini
        vermiyor, ayarı KAYDETMEK veriyor.
        """
        query = parse_qs(urlparse(self.path).query)
        istenen = (query.get("yol", [""])[0] or "").strip()

        if not istenen:
            # Başlangıç: sürücüler (Windows) ya da kök + ev.
            self._json({"yol": "", "ust": None, "klasorler": _baslangic_yerleri()})
            return

        try:
            hedef = Path(istenen).expanduser().resolve()
        except OSError:
            self._json({"hata": "Bu yol çözümlenemedi."})
            return
        if not hedef.is_dir():
            self._json({"hata": f"Böyle bir klasör yok: {hedef}"})
            return

        klasorler: list[dict[str, Any]] = []
        dosya = 0
        try:
            for child in sorted(hedef.iterdir(), key=lambda p: p.name.lower()):
                try:
                    if child.is_dir():
                        # Gizli/araç klasörleri seçicide gürültü: gösteriliyor
                        # ama sona atılıyor değil — gizleniyor. İsteyen yolu
                        # elle yazabilir.
                        if child.name.startswith(".") or child.name in SKIPPED:
                            continue
                        klasorler.append({"ad": child.name, "yol": str(child)})
                    else:
                        dosya += 1
                except OSError:
                    continue
        except OSError as exc:
            self._json({"hata": f"Klasör okunamadı: {exc}"})
            return

        config = getattr(self.server, "config", None)
        durum = config.state_dir if config is not None else None
        self._json({
            "yol": str(hedef),
            "ust": str(hedef.parent) if hedef.parent != hedef else None,
            "klasorler": klasorler[:400],
            "dosya": dosya,
            # Seçilebilir mi ve seçilirse ne söylenmeli: kullanıcı KAYDETMEDEN
            # önce görsün.
            "engel": sandbox.kok_engeli(hedef) or "",
            "uyari": sandbox.kok_uyarisi(hedef, state_dir=durum),
            "tur": _proje_turu(hedef),
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

        Her proje bir iş birimi: Dornick'in ürettiği bir klasör (Modbus web
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
            data = catalog.katalog(root, base=Path(config.workspace))
        except Exception as exc:
            self._json({"projects": [], "sorunlar": [], "error": str(exc)})
            return
        # `sorunlar`: atölye kökündeki başıboş manifestler. Panel bunları
        # ayrı bir "sorunlu" bölümünde nedeniyle gösteriyor — yanlış yere
        # yazılmış bir manifest sessizce kaybolmasın.
        self._json(data)

    def _apps_running(self) -> None:
        """Çalışan, izlenebilen uygulamalar (canlı adresleriyle).

        Köprü/atölye yoksa boş liste: panel bunu "çalışan yok" gösteriyor.
        Atölye kökü veriliyor ki süreç defterinde OLMAYAN ama atölyeye ait
        bir sunucu (dornick yeniden başlatılmışsa) da canlı görünsün.
        """
        from .. import apps as catalog

        config = getattr(self.server, "config", None)
        root = base = None
        try:
            if config is not None:
                root = config.open_sandbox().root
                base = Path(config.workspace)
        except Exception:
            root = base = None
        try:
            self._json({"running": catalog.running(root, base)})
        except Exception as exc:
            self._json({"running": [], "error": str(exc)})

    # -- artifact'lar ----------------------------------------------------

    def _artifacts_list(self) -> None:
        """Yayınlanmış artifact'lar: kimlik, başlık, sürüm, güncellenme.

        Depo yoksa boş liste — galeri bunu "henüz yok" gösteriyor.
        """
        from .. import artifacts

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"artifacts": []})
            return
        self._json({"artifacts": artifacts.listing(config.state_dir)})

    def _artifacts_edit(self, body: dict[str, Any]) -> None:
        """Galerinin tek yazma ucu: {"action": "remove", "id": ...}.

        Kalıcı silme yok — depo çöpe taşıyor; onay arayüzde (iki adımlı
        düğme). Cevap her durumda güncel listeyi de taşıyor ki panel
        bayat kalmasın.
        """
        from .. import artifacts

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        action = str((body or {}).get("action") or "")
        if action != "remove":
            self._json({"ok": False, "error": "`action` remove olmalı",
                        "artifacts": artifacts.listing(config.state_dir)})
            return
        try:
            artifacts.remove(config.state_dir, str((body or {}).get("id") or ""))
        except (artifacts.ArtifactError, OSError) as exc:
            self._json({"ok": False, "error": str(exc),
                        "artifacts": artifacts.listing(config.state_dir)})
            return
        self._json({"ok": True, "artifacts": artifacts.listing(config.state_dir)})

    def _disari_ac(self, body: dict[str, Any]) -> None:
        """Uygulama içi bir sayfayı kullanıcının GERÇEK tarayıcısında açar.

        Kanıtlanmış yara (31.08): ajan artifact adresini varsayılan 8765
        portuyla söylüyordu, sunucu kaymış portta koşuyordu ve kullanıcı
        "bağlantı reddedildi" görüyordu. Gerçek port yalnız burada,
        sunucunun kendisinde biliniyor — adres istekten değil buradan
        kurulur. Yol GÖRELİ olmak zorunda: bu uç yalnız BU sunucunun
        servis ettiği sayfaları açar; dışarıdan gelen bir adresi kullanıcı
        tarayıcısında açtırmanın kapısı olamaz.
        """
        import webbrowser

        path = str((body or {}).get("path") or "").strip()
        if not path.startswith("/") or path.startswith("//"):
            self._json({"ok": False, "error": "Yalnız uygulama içi yol açılır"})
            return
        host, port = self.server.server_address[:2]
        url = f"http://{host}:{port}{path}"
        try:
            ok = webbrowser.open(url)
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return
        self._json({"ok": bool(ok), "url": url})

    def _artifact_indir(self, body: dict[str, Any]) -> None:
        """Artifact'ı İndirilenler klasörüne kaydeder; TAM yolu döndürür.

        Pencere WebView2: blob + <a download> tıklaması indirme penceresi
        açmadan sessizce ölüyordu — kullanıcı "indiremiyorum" yaşıyordu
        (canlı, 31.08). Diske sunucu kendisi yazar; arayüz dönen yolu
        gösterir. Var olan dosya ezilmez — sayaçlı yeni ad açılır.
        """
        import shutil

        from .. import artifacts

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "Yapılandırma yüklü değil"})
            return
        aid = str((body or {}).get("id") or "").strip()
        if not aid:
            m = re.match(r"^/artifact/([a-z0-9-]+)/?", str((body or {}).get("path") or ""))
            if m:
                aid = m.group(1)
        page = artifacts.page_path(config.state_dir, aid)
        if page is None:
            self._json({"ok": False, "error": "Artifact yok"})
            return
        try:
            meta = artifacts.read_meta(config.state_dir, aid)
        except artifacts.ArtifactError:
            meta = {}
        raw_name = str(meta.get("title") or aid).strip() or aid
        stem = re.sub(r"[^\w .-]+", "_", raw_name, flags=re.UNICODE).strip(" ._") or aid
        folder = Path.home() / "Downloads"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            folder = config.state_dir
        target = folder / f"{stem}.html"
        n = 2
        while target.exists():
            target = folder / f"{stem}-{n}.html"
            n += 1
        try:
            shutil.copyfile(page, target)
        except OSError as exc:
            self._json({"ok": False, "error": f"Kaydedilemedi: {exc}"})
            return
        self._json({"ok": True, "path": str(target)})

    def _artifact_page(self, route: str) -> None:
        """Artifact sayfası: /artifact/<id>/ → index.html.

        Yol istekten geliyor ama diske istekten kurulmuyor: kimlik depo
        modülünün sıkı deseninden geçiyor ve çözümlenen yolun depo altında
        kaldığı orada bir daha doğrulanıyor (ASSETS kalıbındaki ilke:
        servis edilen şey istek metni değil, doğrulanmış bir kayıt).
        Sayfa olduğu gibi render ediliyor — betikler dahil; içerik yerel
        makinede, kullanıcının kendi ajanının ürettiği sayfa.
        """
        from .. import artifacts

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        artifact_id = route[len("/artifact/"):].strip("/")
        page = artifacts.page_path(config.state_dir, artifact_id)
        if page is None:
            self.send_error(404, "Artifact yok")
            return
        try:
            body = page.read_bytes()
        except OSError:
            self.send_error(404, "Artifact okunamadı")
            return
        # ?download=1 → dosya olarak indir (HTML standart teslimat).
        want_dl = "download=1" in (urlparse(self.path).query or "")
        if want_dl:
            try:
                meta = artifacts.read_meta(config.state_dir, artifact_id)
            except artifacts.ArtifactError:
                meta = {}
            raw_name = str(meta.get("title") or artifact_id).strip() or artifact_id
            self._send(
                200, "text/html; charset=utf-8", body,
                headers={"Content-Disposition": _attachment_disposition(raw_name, ".html")},
            )
            return
        self._send(200, "text/html; charset=utf-8", body)

    def _parcalar(self) -> list[str] | None:
        """İstekteki parça seçimi: ?parcalar=anilar,tanima → liste.

        Parametre yoksa None — dışa/içe aktarma eski (varsayılan)
        davranışına düşer; bilinmeyen adları transfer modülü eliyor.
        """
        raw = parse_qs(urlparse(self.path).query).get("parcalar", [""])[0]
        secim = [p.strip() for p in raw.split(",") if p.strip()]
        return secim or None

    def _transfer_export(self) -> None:
        """Dornick'in biriktirdiklerini taşınabilir bir paket olarak indirir.

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
        name = f"dornick-{stamp or 'paket'}.neobundle"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _transfer_import(self, raw: bytes) -> None:
        """Yüklenen bir paketi bu Dornick'e birleştirir.

        Anılar katılır (üzerine yazılmaz); dosya parçaları geri yüklenirken
        ezilecek mevcut hal önce .dornick/yedek-<tarih>/ altına alınır.
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

        İkisi de yıkım değil taşıma: mevcut hal .dornick/yedek-<tarih>/
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
        meta = mind.session_meta() if hasattr(mind, "session_meta") else {}
        controller = getattr(self.server, "controller", None)
        busy = bool(getattr(controller, "_busy", False))
        # Paralel şeritler: arka planda koşan HER sohbet listede "koşuyor"
        # görünmeli — yalnız aktif olan değil. Kenar çubuğu rozeti buradan.
        kosanlar: set[str] = set()
        try:
            for sid, serit in (getattr(controller, "seritler", None) or {}).items():
                if getattr(serit, "busy", False):
                    kosanlar.add(sid)
        except Exception:
            pass

        # `?ara=` verilirse arama DÖKÜMLERİN İÇİNDE de yapılıyor: aranan söz
        # çoğu zaman başlıkta değil konuşmanın ortasında geçiyor.
        sorgu = parse_qs(urlparse(self.path).query).get("ara", [""])[0].strip()
        icinde = {}
        if sorgu and hasattr(mind, "search_transcripts"):
            try:
                icinde = mind.search_transcripts(sorgu)
            except Exception:
                icinde = {}   # arama bir kolaylık; patlarsa liste yine gelsin

        out = []
        proje_adlari: set[str] = set(projects.values())
        for ep in mind.sessions():
            kayit = meta.get(ep.session_id) or {}
            is_current = ep.session_id == current
            yol = kayit.get("path") or ""
            proje = projects.get(ep.session_id, "")
            # Klasör bağlı ama proje etiketi yoksa klasör adıyla grupla
            # (eski kayıtlar / yalnız path atanmış sohbetler).
            if not proje and yol:
                leaf = Path(str(yol)).name.strip()
                if leaf:
                    proje = leaf
                    proje_adlari.add(leaf)
            out.append({
                "id": ep.session_id,
                # Kullanıcının verdiği ad varsa o; yoksa dijestten türetilen.
                "title": kayit.get("ad") or _session_title(ep.digest),
                "named": bool(kayit.get("ad")),
                "tags": kayit.get("etiketler") or [],
                "date": _stem_date(ep.session_id),
                "turns": ep.turns,
                "tools": ep.tools[:6],
                "preview": ep.digest[:160],
                "current": is_current,
                # açık = şu an seçili; koşuyor = turu süren HER şerit
                # (aktif ya da arka plan); biten = diğerleri.
                "status": ("koşuyor" if ((is_current and busy)
                                         or ep.session_id in kosanlar)
                           else ("açık" if is_current else "biten")),
                "project": proje,
                "path": yol,
                "model": kayit.get("model") or "",
                "provider": kayit.get("provider") or "",
                "hits": icinde.get(ep.session_id, []),
            })

        etiketler = sorted({e for k in meta.values() for e in (k.get("etiketler") or [])})
        self._json({
            "sessions": out,
            "projects": sorted(proje_adlari),
            "tags": etiketler,
            "searched": bool(sorgu),
        })

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

    def _capraz_koken_mi(self) -> bool:
        """İstek YABANCI bir kökenden mi geliyor?

        True yalnızca Origin (yoksa Referer) BAŞLIĞI VARSA ve kökeni bizim
        host:port'umuzla uyuşmuyorsa. Başlık hiç yoksa False döner: kabuk,
        test, benchmark ve yerel otomasyon Origin göndermez ve bunları
        arayüzden ayırt etmek HTTP katmanında zaten mümkün değil. Kapatılan
        şey çapraz-köken tarayıcı POST'u (drive-by CSRF).
        """
        koken = self.headers.get("Origin") or ""
        if not koken:
            ref = self.headers.get("Referer") or ""
            if not ref:
                return False
            koken = ref
        try:
            from urllib.parse import urlparse
            ayr = urlparse(koken)
        except ValueError:
            return True  # ayrıştırılamayan köken: güvenli tarafta reddet
        host = (ayr.hostname or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            return True
        try:
            bizim_port = int(self.server.server_address[1])
        except (AttributeError, IndexError, TypeError, ValueError):
            return False  # portu bilemiyorsak host eşleşmesi yeter
        # Köken portu belirtmişse eşleşmeli; belirtmemişse (nadiren) host yeter.
        return ayr.port is not None and int(ayr.port) != bizim_port

    def _controller_call(self, name: str, *args: Any) -> Any:
        controller = getattr(self.server, "controller", None)
        fn = getattr(controller, name, None) if controller else None
        # Olmayan bir metot (ör. salt-gözlem önizlemesi ya da new_session
        # desteklemeyen bir köprü) sessizce None: uç nokta bunu ok:false'a
        # çeviriyor, 500 atmıyor.
        return fn(*args) if callable(fn) else None

    # -- yanıt biçimleri -----------------------------------------------

    def _logo_png(self) -> None:
        from ..logo import png_path
        try:
            body = png_path().read_bytes()
        except OSError:
            self.send_error(404)
            return
        self._send(200, "image/png", body)

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

    def _guncelle(self) -> None:
        """Yeni sürümü indirir ve kurulum sihirbazını başlatır.

        Adres İSTEMCİDEN GELMEZ: sunucu GitHub yayın API'sini yeniden
        sorup güvenilir indirme bağlantısını oradan alır (zehirlenmiş bir
        URL enjekte edilemez). İndirme arka planda; ilerleme SSE ile
        ("guncelleme" olayı) arayüze akar. Bitince sihirbaz açılır; çalışan
        uygulamayı kapatmayı sihirbazın kendisi (PrepareToInstall → "Kapat
        ve devam") üstlenir.
        """
        import tempfile
        import threading

        bilgi = ortam.guncelleme_denetle()
        if not bilgi.get("yeni") or not bilgi.get("indirme"):
            self._json({"ok": False,
                        "hata": bilgi.get("hata") or "İndirilecek güncelleme yok"})
            return

        hub = getattr(self.server, "hub", None)

        def duyur(ev: dict) -> None:
            if hub is not None:
                try:
                    hub.emit({"type": "guncelleme", **ev})
                except Exception:
                    pass

        def kos() -> None:
            try:
                duyur({"asama": "indiriliyor", "yuzde": 0, "yeni": bilgi["yeni"]})
                dizin = Path(tempfile.gettempdir()) / "dornick-guncelleme"

                def ilerleme(indirilen: int, toplam: int) -> None:
                    yuzde = int(indirilen * 100 / toplam) if toplam else 0
                    duyur({"asama": "indiriliyor", "yuzde": yuzde,
                           "indirilen": indirilen, "toplam": toplam})

                yol = ortam.guncelleme_indir(
                    bilgi["indirme"], dizin,
                    beklenen_boyut=int(bilgi.get("boyut") or 0),
                    ad=str(bilgi.get("ad") or ""), ilerleme=ilerleme)
                duyur({"asama": "kuruluyor", "yeni": bilgi["yeni"]})
                ortam.guncellemeyi_baslat(yol)
                duyur({"asama": "acildi", "yeni": bilgi["yeni"]})
            except Exception as exc:  # ağ/doğrulama/başlatma — arayüze dürüst hata
                duyur({"asama": "hata", "hata": f"{type(exc).__name__}: {exc}"})

        threading.Thread(target=kos, name="dornick-guncelle", daemon=True).start()
        self._json({"ok": True, "yeni": bilgi["yeni"]})

    def _send(self, status: int, content_type: str, body: bytes,
              headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
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
