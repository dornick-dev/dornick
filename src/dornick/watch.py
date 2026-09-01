"""Kamera izleme.

"Sürekli kameraları izlesin, sorun görünce haber versin" isteğinin karşılığı.

Naif yol her kareyi modele sormak olurdu ve o yol çalışmıyor: saniyede
yirmi kare, karesi 1.5–4.8k token. Yerel bir modelde dakikada onlarca istek
demek ve makine buna dayanmıyor.

Bunun yerine iş ikiye bölünüyor:

    yerelde   hareket var mı? — küçültülmüş gri kareler arasındaki fark.
              Mikrosaniyeler sürüyor, model hiç uyanmıyor.
    GPU'da    hareket varsa **ne** var? — NVIDIA kartı varsa YOLOv8n
              kareyi metne çevirir; görüntü makineden çıkmaz.
    modelde   GPU yoksa hareket karesi bir kez soruluyor (cloud_ok kapısı).

Yani model sessizce bekliyor ve yalnızca bir şey değiştiğinde bakıyor. Boş
bir odada saatlerce hiçbir istek gitmiyor.

İki fren daha var:
  * `cooldown` — hareket sürerken saniyede bir soru sorulmuyor; bir kez
    sorulup bir süre susuluyor.
  * `warmup`  — kamera açıldıktan sonraki ilk kareler atlanıyor; pozlama
    otururken her kare "hareket" gibi görünüyor.

Kaynak yerel bir kamera indeksi (0, 1) ya da bir adres olabilir: RTSP, HTTP,
MJPEG. OpenCV ikisini de aynı arayüzle açıyor.
"""

from __future__ import annotations

import base64
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

INSTALL_HINT = "Kamera izleme için: pip install 'dornick[watch]'"


def hint() -> str:
    """Eksik-özellik mesajı: kurulu düzende bileşen önerilir, pip değil."""
    from . import ortam

    if ortam.kurulu_mu():
        return ("Kamera izleme bu kuruluma dahil edilmemiş. Kurulum "
                "sihirbazını yeniden çalıştırıp 'Kamera izleme' "
                "bileşenini işaretleyerek ekleyebilirsin.")
    return INSTALL_HINT

# Karşılaştırma bu ölçüde yapılıyor. Küçük olması hem hızlı hem de gölge,
# gürültü ve sıkıştırma titremesine karşı dayanıklı.
COMPARE = (64, 48)

# Kameranın pozlamayı oturtması için atlanan ilk kare sayısı.
WARMUP = 5


def available() -> bool:
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(slots=True)
class Camera:
    """İzlenen bir kamera.

    source: yerel kamera için "0", ağ kamerası için tam adres.
    sensitivity: 0..1. Yükseldikçe daha küçük değişiklik tetikliyor.
        0.06 kapalı bir odada yaprak kımıldamasını kaçırmaz ama gürültüyle
        de uyanmaz — deneyerek bulunan orta yer.
    cooldown_s: bir uyarıdan sonra susulacak süre. Kapı açık kaldığında
        her saniye haber vermemek için.
    ask: modele sorulacak soru. Boşsa genel bir bakış isteniyor.
    """

    id: str
    name: str
    source: str = "0"
    enabled: bool = True
    sensitivity: float = 0.06
    cooldown_s: int = 60
    every_s: float = 1.0
    ask: str = ""
    last_seen: str = ""
    last_note: str = ""
    # usb = yerel aygıt indeksi; rtsp / http = ağ. Eski kayıtlarda yalnız
    # `source` dolu — connect_source onu olduğu gibi kullanır.
    kind: str = "usb"
    host: str = ""
    port: int = 0
    path: str = ""
    user: str = ""
    password: str = ""
    # True: GPU varsa kare yerelde YOLOv8n ile okunur. GPU yok/yetersizse
    # zaten no-op (CPU'ya düşmez). Kamerayı tek tek kapatmak için False.
    analyze: bool = True

    def connect_source(self) -> Any:
        """OpenCV'ye verilecek kaynak: indeks veya kimlikli URL."""
        from urllib.parse import quote

        if self.host.strip():
            scheme = "rtsp" if (self.kind or "rtsp") == "rtsp" else "http"
            if (self.kind or "") in ("http", "mjpeg"):
                scheme = "http"
            port = int(self.port or 0) or (554 if scheme == "rtsp" else 80)
            path = self.path.strip() or "/"
            if not path.startswith("/"):
                path = "/" + path
            auth = ""
            if self.user:
                auth = quote(self.user, safe="")
                if self.password:
                    auth += ":" + quote(self.password, safe="")
                auth += "@"
            return f"{scheme}://{auth}{self.host.strip()}:{port}{path}"
        src = (self.source or "0").strip() or "0"
        return int(src) if src.isdigit() else src

    def public_dict(self) -> dict[str, Any]:
        """API/UI: şifre yok, URL'deki user:pass maskeli."""
        import re

        d = asdict(self)
        d["has_password"] = bool(d.pop("password", ""))
        src = str(d.get("source") or "")
        d["source"] = re.sub(r"(://)([^/@]+)@", r"\1***@", src)
        return d

    def is_builtin(self) -> bool:
        """Dahili webcam: indeks 0, host yok."""
        if (self.host or "").strip():
            return False
        src = (self.source or "0").strip() or "0"
        kind = (self.kind or "usb").strip() or "usb"
        return src == "0" and kind == "usb"


def _watchable(cameras: list[Camera]) -> list[Camera]:
    """İzleyiciye düşen kameralar: açık ağ/USB-ek; dahili webcam Lens'in.

    `cameras.json` içindeki "Bilgisayar kamerası" (kaynak 0) ikinci bir
    OpenCV oturumu açıyordu. HUD kapalıyken bile kare alınıp sohbete
    "hareket oldu" basılıyordu; model de `look` ile Lens'i kapalı görüyordu.
    """
    return [c for c in cameras if c.enabled and not c.is_builtin()]


DEFAULT_ASK = (
    "Bu kamerada bir hareket oldu. Kareye bak ve ne olduğunu tek cümleyle "
    "söyle. Sıradan bir şeyse (biri geçti, ışık değişti) kısa geç; dikkat "
    "gerektiren bir şey varsa (düşmüş biri, açık kalmış kapı, duman, "
    "tanımadığın biri) bunu açıkça yaz."
)


@dataclass(slots=True)
class Sighting:
    camera: Camera
    frame: str          # data: adresi
    change: float       # 0..1, kareler arası fark
    ask: str


@dataclass(slots=True)
class Eye:
    """Tek bir kameranın izleyicisi."""

    camera: Camera
    _last: Any = None
    _warm: int = 0
    _quiet_until: float = 0.0
    _capture: Any = field(default=None, repr=False)

    def open(self) -> bool:
        import cv2

        if self._capture is not None:
            return True
        source = self.camera.connect_source()
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            capture.release()
            return False
        self._capture = capture
        self._warm = WARMUP
        return True

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._last = None

    def jpeg(self) -> str:
        """Açık yakalamadan bir JPEG (data: URL). Yoksa boş."""
        if self._capture is None:
            return ""
        ok, frame = self._capture.read()
        if not ok:
            return ""
        return _encode(frame) or ""

    def look(self) -> Sighting | None:
        """Bir kare alır. Değişiklik eşiği aştıysa görüntüyü döndürür."""
        import cv2

        if self._capture is None and not self.open():
            return None

        ok, frame = self._capture.read()
        if not ok:
            # Ağ kamerası kopmuş olabilir; bir sonraki turda yeniden açılsın.
            self.close()
            return None

        small = cv2.cvtColor(cv2.resize(frame, COMPARE), cv2.COLOR_BGR2GRAY)

        if self._warm > 0:
            # Pozlama otururken her kare "hareket" gibi görünüyor.
            self._warm -= 1
            self._last = small
            return None

        previous, self._last = self._last, small
        if previous is None:
            return None

        change = float(cv2.absdiff(previous, small).mean()) / 255.0
        if change < self.camera.sensitivity:
            return None

        # Hareket sürerken saniyede bir soru sorulmuyor.
        now = time.monotonic()
        if now < self._quiet_until:
            return None
        self._quiet_until = now + max(5, self.camera.cooldown_s)

        return Sighting(
            camera=self.camera,
            frame=_encode(frame),
            change=round(change, 4),
            ask=self.camera.ask.strip() or DEFAULT_ASK,
        )


def _encode(frame: Any, max_edge: int = 800, quality: int = 78) -> str:
    """Kareyi data: adresine çevirir.

    Küçültme burada: bir görüntü bağlamda 1.5–4.8k token ve tam çözünürlük
    fark ettirmiyor.
    """
    import cv2

    height, width = frame.shape[:2]
    scale = min(1.0, max_edge / max(height, width))
    if scale < 1.0:
        frame = cv2.resize(frame, (int(width * scale), int(height * scale)))

    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")


def snapshot(source: str, count: int = 1, gap_s: float = 0.6,
             warm: int = 3) -> list[str]:
    """Kameradan anlık kesit(ler): data:image/jpeg;base64 listesi.

    İzleme döngüsünden bağımsız — "sorduğumuzda birkaç kesit alıp modele"
    yolunun temeli (GPU'suz makinede TEK çalışma kipi bu). Kamera açılır,
    pozlama otursun diye birkaç kare atlanır, istenen sayıda kare alınır
    ve kapatılır: arkada açık kamera bırakılmaz.
    """
    import cv2  # noqa: F401 — open() zaten ister; hint() için erken kontrol

    eye = Eye(Camera(id="kesit", name="kesit", source=str(source)))
    if not eye.open():
        return []
    try:
        for _ in range(max(0, warm)):
            eye._capture.read()
        frames: list[str] = []
        for i in range(max(1, min(int(count), 4))):
            if i:
                time.sleep(max(0.1, gap_s))
            ok, frame = eye._capture.read()
            if not ok:
                break
            if encoded := _encode(frame):
                frames.append(encoded)
        return frames
    finally:
        eye.close()


def same_source(a: str, b: str) -> bool:
    """'0' ve boş string aynı dahili kamera."""
    x = (str(a or "").strip() or "0")
    y = (str(b or "").strip() or "0")
    return x == y


def preview_jpeg(source: str, lens: Any = None, warm: int = 0) -> bytes:
    """Güverte karosu: açık Lens tamponu, yoksa tek kesit.

    Dahili kamera zaten Lens'te açıksa ikinci VideoCapture Windows
    DirectShow'da 0.5–2 sn kilitler ve açık oturumla yarışır.
    """
    src = (source or "0").strip() or "0"
    if lens is not None and same_source(getattr(lens, "source", "0"), src):
        getter = getattr(lens, "jpeg_bytes", None)
        return getter() if callable(getter) else b""
    frames = snapshot(src, 1, warm=warm)
    if not frames:
        return b""
    return base64.b64decode(frames[0].partition(",")[2])


class Watcher:
    """Kameraları arka planda izler.

    Kendi thread'inde dönüyor: OpenCV'nin okuması bloklayan bir çağrı ve
    ajanın asyncio döngüsünü kilitlemesi kabul edilemez.
    """

    def __init__(self, cameras: list[Camera], report: Callable[[Sighting], None]) -> None:
        self.report = report
        self._all = list(cameras)
        self._eyes = {c.id: Eye(camera=c) for c in _watchable(cameras)}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.armed = False

    def load_from(self, cameras: list[Camera]) -> None:
        """HUD açılınca kayıtlı kameraları yeniden yükler; dönen döngüye dokunmaz."""
        self._all = list(cameras)

    def start(self) -> bool:
        if not available():
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._eyes = {c.id: Eye(camera=c) for c in _watchable(self._all)}
        if not self._eyes:
            return False
        # stop() Event'i set bırakıyor; yeniden kullanılamaz.
        self._stop = threading.Event()
        self.armed = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="dornick-watch")
        self._thread.start()
        return True

    def stop(self) -> None:
        self.armed = False
        self._stop.set()
        for eye in list(self._eyes.values()):
            eye.close()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        self._eyes = {}

    @property
    def snoozed(self) -> bool:
        return time.monotonic() < getattr(self, "_snooze_until", 0.0)

    def snooze(self, seconds: float = 0.0) -> None:
        self._snooze_until = (
            time.monotonic() + seconds if seconds > 0 else float("inf")
        )
        from . import prefs as prefs_mod
        prefs_mod.tell(getattr(self, "on_snooze", None), True)

    def unsnooze(self) -> None:
        was = self.snoozed
        self._snooze_until = 0.0
        if was:
            from . import prefs as prefs_mod
            prefs_mod.tell(getattr(self, "on_snooze", None), False)

    def peek(self, camera_id: str) -> str:
        """İzlenen kameradan kare; ikinci kez açmaz."""
        eye = self._eyes.get(camera_id)
        return eye.jpeg() if eye is not None else ""

    def _loop(self) -> None:
        while not self._stop.is_set():
            # Susturulmuşken hiçbir kameraya bakılmıyor ve hiçbir görüş
            # bildirilmiyor: "izlemiyorum" ağ kameralarını da kapsıyor.
            if self.snoozed or not self.armed:
                self._stop.wait(1.0)
                continue
            slowest = 1.0
            for eye in self._eyes.values():
                slowest = min(slowest, eye.camera.every_s)
                try:
                    if sighting := eye.look():
                        if self.armed:
                            self.report(sighting)
                except Exception:
                    # Tek bir kameranın hatası ötekileri durdurmamalı.
                    eye.close()
            self._stop.wait(max(0.2, slowest))


# -- kayıt -------------------------------------------------------------


def load(state_dir: Any) -> list[Camera]:
    import json
    from pathlib import Path

    path = Path(state_dir) / "cameras.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    known = set(Camera.__dataclass_fields__)
    out: list[Camera] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        cam = Camera(**{k: v for k, v in entry.items() if k in known})
        src = (cam.source or "").casefold()
        if not cam.host and cam.kind == "usb":
            if src.startswith("rtsp://"):
                cam.kind = "rtsp"
            elif src.startswith("http://") or src.startswith("https://"):
                cam.kind = "http"
        out.append(cam)
    return out


def save(state_dir: Any, cameras: list[Camera]) -> None:
    import json
    from pathlib import Path

    path = Path(state_dir) / "cameras.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps([asdict(c) for c in cameras], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def remember(state_dir: Any, camera: Camera, note: str) -> None:
    """Hareket özetini kayda yazar — model `kamera action=yol` ile okur."""
    from datetime import datetime

    camera.last_note = (note or "").strip()[:240]
    camera.last_seen = datetime.now().astimezone().isoformat(timespec="seconds")
    cameras = load(state_dir)
    found = False
    for entry in cameras:
        if entry.id != camera.id:
            continue
        entry.last_note = camera.last_note
        entry.last_seen = camera.last_seen
        found = True
        break
    if found:
        save(state_dir, cameras)


# -- yerel kamera tamponu ----------------------------------------------
#
# Ajanın "gözü". Kamera sürekli açık ve kare alıyor ama **hiçbiri modele
# gitmiyor**: her kareyi modele vermek dakikada onlarca istek ve saniyede
# binlerce token demek — kullanılamaz.
#
# Bunun yerine kareler burada, bellekte duruyor. Model bakmaya karar
# verdiğinde (`look` aracı) tek bir kare alıyor. Aradaki hareket yerelde
# ölçülüyor, yani "son bir dakikada bir şey oldu mu" sorusu modele hiç
# uğramadan cevaplanıyor.

# Saniyede bu kadar kare. Önizleme akıcı dursun diye 8; YOLO her karede
# değil, yalnız bakış/harekette çalışır — GPU buradan yanmaz.
LENS_FPS = 8.0

# Bellekte tutulan hareket geçmişi. 2 fps'te iki dakika.
HISTORY = 240

# Geriye dönük **kare** penceresi. "Az önce ne gösterdim" sorusunun cevabı
# bu tampon: kullanıcı bir şeyi gösterip indirmiş olabiliyor ve o an kamerayı
# açmak geç kalmak demek. 2 fps'te on saniye ~yirmi kare; kareler JPEG
# olarak tutuluyor, toplamı birkaç MB — ham kare tutmak yüz MB'ı bulurdu.
RECENT_S = 10.0

# Bu kadar süre hiçbir şey kımıldamazsa oda "boş" sayılıyor. Sonrasında
# gelen hareket sıradan bir kıpırtı değil, **biri geldi** demek.
AWAY_S = 90.0

# Geliş bildiriminden sonra susulacak süre. Biri odada oturup kıpırdadıkça
# her seferinde haber vermek gürültü.
GREET_QUIET_S = 300.0


@dataclass(slots=True)
class Moment:
    at: float
    change: float


class Lens:
    """Yerel kameranın sürekli açık tamponu.

    Tek bir kare bellekte duruyor (en yenisi) ve yanında hareket geçmişi.
    Kareleri biriktirmiyoruz: iki dakikalık video bellekte yüzlerce megabayt
    ve hiçbir işe yaramıyor — sorulan şey "şu an ne var" ya da "az önce bir
    şey oldu mu".
    """

    def __init__(self, source: str = "0", fps: float = LENS_FPS) -> None:
        self.source = source
        self.fps = fps
        self._eye = Eye(camera=Camera(id="lens", name="yerel", source=source,
                                      sensitivity=0.0, cooldown_s=0))
        self._frame: Any = None
        self._at = 0.0
        self._history: list[Moment] = []
        # Son RECENT_S saniyenin kareleri, JPEG olarak: (zaman, bayt).
        self._recent: list[tuple[float, bytes]] = []
        # Son gerçek hareketin anı, bekleyen geliş ve susma payı.
        self._last_move = time.monotonic()
        self._arrived = False
        self._greeted_until = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Susturma: "beni izleme" dendiğinde kare almak duruyor ve tampon
        # boşalıyor. Kulakta aynı kapı vardı, gözde yoktu — ajan
        # "izlemiyorum" deyip kare almaya devam ediyordu.
        self._snooze_until = 0.0

    def start(self) -> bool:
        if not available():
            return False
        if self.running:
            return True
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="dornick-lens")
        self._thread.start()
        return True

    @property
    def running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    @property
    def snoozed(self) -> bool:
        return time.monotonic() < self._snooze_until

    def snooze(self, seconds: float = 0.0) -> None:
        """Gözü kapatır. Süresiz de olabilir; "dornick" demek geri açar.

        Kapatmak yalnızca yeni kare almamak değil: eldeki kare silinir ve
        aygıt bırakılır (LED söner). "İzlemiyorum" deyip kamerayı açık
        tutmak yarım bir kapanma olurdu.
        """
        self._snooze_until = (
            time.monotonic() + seconds if seconds > 0 else float("inf")
        )
        with self._lock:
            self._frame = None
            self._history.clear()
            self._recent.clear()
        self._eye.close()
        from . import prefs as prefs_mod
        prefs_mod.tell(getattr(self, "on_snooze", None), True)

    def unsnooze(self) -> None:
        was = self.snoozed
        self._snooze_until = 0.0
        if was:
            from . import prefs as prefs_mod
            prefs_mod.tell(getattr(self, "on_snooze", None), False)

    def stop(self) -> None:
        """Tam kapatma: döngü biter, aygıt bırakılır, tampon boşalır."""
        self._stop.set()
        self._eye.close()
        t = self._thread
        self._thread = None
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2.0)
        self._snooze_until = 0.0
        with self._lock:
            self._frame = None
            self._history.clear()
            self._recent.clear()

    @property
    def live(self) -> bool:
        with self._lock:
            return self._frame is not None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.step()
            self._stop.wait(1.0 / max(0.2, self.fps))

    def step(self) -> None:
        """Tek bir kare alır ve tamponu tazeler.

        Susturulmuşken kare alınmıyor ve aygıt bırakılıyor (LED söner).

        Döngüden ayrı durması bilinçli: bekleme olmadan tek adım
        çalıştırılabiliyor ve davranışı ölçülebiliyor.
        """
        if self.snoozed:
            if self._eye._capture is not None:
                self._eye.close()
            return
        import cv2

        try:
            if self._eye._capture is None and not self._eye.open():
                return

            ok, frame = self._eye._capture.read()
            if not ok:
                # Kamera koptu; bir sonraki adımda yeniden açılır.
                self._eye.close()
                return

            small = cv2.cvtColor(cv2.resize(frame, COMPARE), cv2.COLOR_BGR2GRAY)
            change = 0.0
            if self._eye._last is not None:
                change = float(cv2.absdiff(self._eye._last, small).mean()) / 255.0
            self._eye._last = small

            # Kare tampona JPEG olarak giriyor; sıkıştırma kilidin dışında,
            # kilit yalnızca listeyi tutarken tutuluyor.
            ok, packed = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            raw = packed.tobytes() if ok else b""

            with self._lock:
                self._frame = frame
                self._at = time.time()
                self._history.append(Moment(at=self._at, change=change))
                # Geçmiş sınırlı: iki dakikalık pencere yeterli ve bellek
                # sınırsız büyümemeli.
                del self._history[:-HISTORY]
                if raw:
                    self._recent.append((self._at, raw))
                    while self._recent and self._at - self._recent[0][0] > RECENT_S:
                        self._recent.pop(0)
        except Exception:
            self._eye.close()

    # -- sorular -------------------------------------------------------

    def jpeg_bytes(self) -> bytes:
        """Önizleme için son JPEG. Kamerayı yeniden açmaz."""
        with self._lock:
            return self._recent[-1][1] if self._recent else b""

    def snapshot(self) -> tuple[str, float]:
        """En yeni kare ve kaç saniye önce alındığı."""
        with self._lock:
            if self._frame is None:
                return "", 0.0
            return _encode(self._frame), time.time() - self._at

    def recall(self, back_s: float) -> tuple[str, float]:
        """Son `back_s` saniyeden en iyi kare ve kaç saniye önce alındığı.

        "Az önce ne gösterdim" sorusunun cevabı: kullanıcı gösterdiğini
        indirmişse şu anki kare boş. Pencere içindeki karelerden **en net**
        olanı seçiliyor — hareket halindeki kareler bulanık, gösterilen şey
        elde sabit dururken çekilen kare net çıkıyor. Eşitlikte yeni olan
        kazanıyor.
        """
        import cv2
        import numpy as np

        now = time.time()
        with self._lock:
            window = [(at, raw) for at, raw in self._recent if now - at <= back_s]

        best_frame, best_at, best_score = None, 0.0, -1.0
        for at, raw in window:
            frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            # Netlik ölçüsü: Laplace varyansı. Küçültülmüş gri kare üstünde
            # — tam çözünürlük aynı sırayı verip on kat yavaş.
            gray = cv2.cvtColor(cv2.resize(frame, (320, 240)), cv2.COLOR_BGR2GRAY)
            score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            if score >= best_score:
                best_frame, best_at, best_score = frame, at, score

        if best_frame is None:
            # Tampon boşsa (kamera yeni açıldı, susturulmuştu) eldeki son
            # kare yine de bir cevap.
            return self.snapshot()
        return _encode(best_frame), now - best_at

    def arrival(self) -> bool:
        """Uzun bir sessizlikten sonra biri geldi mi?

        Küçük bir çocuk gibi: odada kimse yokken kendini beklemeye alıyor,
        bir şey kımıldayınca bakıyor. Her hareketi bildirmek gürültü olurdu
        — bildirilen şey **gelme anı**.

        Bir kez bildirdikten sonra bir süre susuyor: biri odada oturup
        kıpırdadıkça her seferinde haber vermek aynı gürültü.
        """
        if self.snoozed:
            return False
        now = time.monotonic()
        with self._lock:
            if now < self._greeted_until:
                return False
            if not self._arrived:
                return False
            self._arrived = False
            self._greeted_until = now + GREET_QUIET_S
        return True

    def motion(self, seconds: float = 60.0) -> dict[str, Any]:
        """Son `seconds` içindeki hareket özeti. Modele hiç uğramadan.

        "Bir şey oldu mu" sorusunun cevabı burada: kaç kare bakıldı, en
        yüksek değişim ne, hareketli an var mıydı.
        """
        now = time.time()
        with self._lock:
            window = [m for m in self._history if now - m.at <= seconds]

        if not window:
            return {"frames": 0, "peak": 0.0, "busy": 0, "quiet": True}

        peak = max(m.change for m in window)
        # Gürültüyü ayıklamak için sabit bir eşik: bunun altı kamera
        # titremesi, üstü gerçek hareket.
        busy = sum(1 for m in window if m.change >= 0.04)
        return {
            "frames": len(window),
            "peak": round(peak, 3),
            "busy": busy,
            "quiet": busy == 0,
        }
