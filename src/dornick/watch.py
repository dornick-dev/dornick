"""Camera watching.

The answer to "let it watch the cameras all the time and tell me when it
sees a problem".

The naive route would be asking the model about every frame, and that
route does not work: twenty frames a second, 1.5–4.8k tokens each. With a
local model that means dozens of requests a minute and the machine cannot
take it.

Instead the work is split in two:

    locally     is there motion? — the difference between downscaled grey
                frames. Takes microseconds, the model never wakes.
    on the GPU  if there is motion, **what** is there? — with an NVIDIA
                card YOLOv8n turns the frame into text; the image never
                leaves the machine.
    in the model  without a GPU the motion frame is asked about once
                (the cloud_ok gate).

So the model waits quietly and only looks when something changes. In an
empty room no request goes out for hours.

Two more brakes:
  * `cooldown` — while motion continues a question is not asked every
    second; it is asked once and then it stays quiet for a while.
  * `warmup`  — the first frames after the camera opens are skipped; while
    the exposure settles every frame looks like "motion".

The source can be a local camera index (0, 1) or an address: RTSP, HTTP,
MJPEG. OpenCV opens both with the same interface.
"""

from __future__ import annotations

import base64
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

INSTALL_HINT = "Kamera izleme için: pip install 'dornick[watch]'"


def hint() -> str:
    """Missing-feature message: in the installed layout the component is suggested, not pip."""
    from . import environment

    if environment.is_installed():
        return ("Kamera izleme bu kuruluma dahil edilmemiş. Kurulum "
                "sihirbazını yeniden çalıştırıp 'Kamera izleme' "
                "bileşenini işaretleyerek ekleyebilirsin.")
    return INSTALL_HINT

# The comparison is done at this size. Small is both fast and robust
# against shadow, noise and compression flicker.
COMPARE = (64, 48)

# Number of initial frames skipped so the camera settles its exposure.
WARMUP = 5


def available() -> bool:
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(slots=True)
class Camera:
    """A watched camera.

    source: "0" for a local camera, the full address for a network camera.
    sensitivity: 0..1. The higher, the smaller the change that triggers.
        0.06 does not miss a leaf stirring in a closed room but does not
        wake on noise either — the middle ground found by trial.
    cooldown_s: how long to stay quiet after an alert. So that a door left
        open does not report every second.
    ask: the question to ask the model. Empty asks for a general look.
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
    # usb = local device index; rtsp / http = network. In old records only
    # `source` is filled — connect_source uses it as is.
    kind: str = "usb"
    host: str = ""
    port: int = 0
    path: str = ""
    user: str = ""
    password: str = ""
    # True: with a GPU the frame is read locally by YOLOv8n. Without / with
    # an insufficient GPU it is a no-op anyway (no CPU fallback). False to
    # turn it off for one camera.
    analyze: bool = True

    def connect_source(self) -> Any:
        """The source given to OpenCV: an index, or a URL with credentials."""
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
        """API/UI: no password, the user:pass in the URL masked."""
        import re

        d = asdict(self)
        d["has_password"] = bool(d.pop("password", ""))
        src = str(d.get("source") or "")
        d["source"] = re.sub(r"(://)([^/@]+)@", r"\1***@", src)
        return d

    def is_builtin(self) -> bool:
        """Built-in webcam: index 0, no host."""
        if (self.host or "").strip():
            return False
        src = (self.source or "0").strip() or "0"
        kind = (self.kind or "usb").strip() or "usb"
        return src == "0" and kind == "usb"


def _watchable(cameras: list[Camera]) -> list[Camera]:
    """Cameras that fall to the watcher: enabled network/extra USB; the built-in webcam is the Lens's.

    The "Bilgisayar kamerası" (source 0) inside `cameras.json` was opening a
    second OpenCV session. Even with the HUD closed, frames were taken and
    "hareket oldu" was pushed into the chat; the model, via `look`, saw the
    Lens as closed.
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
    frame: str          # data: URL
    change: float       # 0..1, difference between frames
    ask: str


@dataclass(slots=True)
class Eye:
    """Watcher of a single camera."""

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
        """A JPEG (data: URL) from the open capture. Empty if none."""
        if self._capture is None:
            return ""
        ok, frame = self._capture.read()
        if not ok:
            return ""
        return _encode(frame) or ""

    def look(self) -> Sighting | None:
        """Takes a frame. Returns the image if the change crossed the threshold."""
        import cv2

        if self._capture is None and not self.open():
            return None

        ok, frame = self._capture.read()
        if not ok:
            # A network camera may have dropped; let it reopen on the next round.
            self.close()
            return None

        small = cv2.cvtColor(cv2.resize(frame, COMPARE), cv2.COLOR_BGR2GRAY)

        if self._warm > 0:
            # While the exposure settles every frame looks like "motion".
            self._warm -= 1
            self._last = small
            return None

        previous, self._last = self._last, small
        if previous is None:
            return None

        change = float(cv2.absdiff(previous, small).mean()) / 255.0
        if change < self.camera.sensitivity:
            return None

        # While motion continues a question is not asked every second.
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
    """Turns the frame into a data: URL.

    Downscaling happens here: an image is 1.5–4.8k tokens in context and
    full resolution makes no difference.
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
    """Instant snapshot(s) from the camera: a list of data:image/jpeg;base64.

    Independent of the watch loop — the basis of the "take a few snapshots
    when asked and send them to the model" route (on a GPU-less machine the
    ONLY working mode). The camera opens, a few frames are skipped so the
    exposure settles, the wanted number of frames is taken and it closes:
    no camera is left open in the background.
    """
    import cv2  # noqa: F401 — open() needs it anyway; early check for hint()

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
    """'0' and the empty string are the same built-in camera."""
    x = (str(a or "").strip() or "0")
    y = (str(b or "").strip() or "0")
    return x == y


def preview_jpeg(source: str, lens: Any = None, warm: int = 0) -> bytes:
    """Deck tile: the open Lens buffer, otherwise a single snapshot.

    If the built-in camera is already open in the Lens, a second
    VideoCapture locks for 0.5–2 s on Windows DirectShow and races the
    open session.
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
    """Watches the cameras in the background.

    Runs on its own thread: OpenCV's read is a blocking call and locking the
    agent's asyncio loop is unacceptable.
    """

    def __init__(self, cameras: list[Camera], report: Callable[[Sighting], None]) -> None:
        self.report = report
        self._all = list(cameras)
        self._eyes = {c.id: Eye(camera=c) for c in _watchable(cameras)}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.armed = False

    def load_from(self, cameras: list[Camera]) -> None:
        """Reloads the saved cameras when the HUD opens; does not touch a running loop."""
        self._all = list(cameras)

    def start(self) -> bool:
        if not available():
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._eyes = {c.id: Eye(camera=c) for c in _watchable(self._all)}
        if not self._eyes:
            return False
        # stop() leaves the Event set; it cannot be reused.
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
        """A frame from a watched camera; does not open it a second time."""
        eye = self._eyes.get(camera_id)
        return eye.jpeg() if eye is not None else ""

    def _loop(self) -> None:
        while not self._stop.is_set():
            # While snoozed no camera is looked at and no sighting is
            # reported: "I'm not watching" covers the network cameras too.
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
                    # One camera's error must not stop the others.
                    eye.close()
            self._stop.wait(max(0.2, slowest))


# -- records -----------------------------------------------------------


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
    """Writes the motion summary to the record — the model reads it with `kamera action=yol`."""
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


# -- local camera buffer -----------------------------------------------
#
# The agent's "eye". The camera is always open and taking frames but **none
# of them goes to the model**: giving every frame to the model means dozens
# of requests a minute and thousands of tokens a second — unusable.
#
# Instead the frames sit here, in memory. When the model decides to look
# (the `look` tool) it takes a single frame. Motion in between is measured
# locally, so the question "did anything happen in the last minute" is
# answered without ever touching the model.

# This many frames a second. 8 so the preview stays smooth; YOLO runs not on
# every frame but only on a look/motion — the GPU does not burn from here.
LENS_FPS = 8.0

# Motion history kept in memory. Two minutes at 2 fps.
HISTORY = 240

# Backward **frame** window. This buffer is the answer to "what did I just
# show": the user may have shown something and lowered it, and opening the
# camera at that moment means being late. At 2 fps ten seconds is ~twenty
# frames; frames are kept as JPEG, a few MB in total — keeping raw frames
# would reach a hundred MB.
RECENT_S = 10.0

# If nothing stirs for this long the room counts as "empty". Motion after
# that is not an ordinary stir, it means **someone came**.
AWAY_S = 90.0

# Quiet period after an arrival notice. Reporting every time someone sits
# in the room and stirs is noise.
GREET_QUIET_S = 300.0


@dataclass(slots=True)
class Moment:
    at: float
    change: float


class Lens:
    """The always-open buffer of the local camera.

    A single frame sits in memory (the newest) with the motion history next
    to it. We do not accumulate frames: two minutes of video is hundreds of
    megabytes in memory and serves nothing — what is asked is "what is
    there now" or "did something just happen".
    """

    def __init__(self, source: str = "0", fps: float = LENS_FPS) -> None:
        self.source = source
        self.fps = fps
        self._eye = Eye(camera=Camera(id="lens", name="yerel", source=source,
                                      sensitivity=0.0, cooldown_s=0))
        self._frame: Any = None
        self._at = 0.0
        self._history: list[Moment] = []
        # Frames of the last RECENT_S seconds, as JPEG: (time, bytes).
        self._recent: list[tuple[float, bytes]] = []
        # Moment of the last real motion, a pending arrival and the quiet margin.
        self._last_move = time.monotonic()
        self._arrived = False
        self._greeted_until = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Snooze: when "don't watch me" is said, taking frames stops and the
        # buffer empties. The ear had the same gate, the eye did not — the
        # agent said "I'm not watching" and kept taking frames.
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
        """Closes the eye. Can be indefinite; saying "dornick" reopens it.

        Closing is not just not taking new frames: the frame in hand is
        deleted and the device is released (the LED goes off). Saying "I'm
        not watching" while keeping the camera open would be a half closure.
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
        """Full shutdown: the loop ends, the device is released, the buffer empties."""
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
        """Takes a single frame and refreshes the buffer.

        While snoozed no frame is taken and the device is released (the LED goes off).

        Standing apart from the loop is deliberate: a single step can be
        run without waiting and its behaviour measured.
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
                # The camera dropped; it reopens on the next step.
                self._eye.close()
                return

            small = cv2.cvtColor(cv2.resize(frame, COMPARE), cv2.COLOR_BGR2GRAY)
            change = 0.0
            if self._eye._last is not None:
                change = float(cv2.absdiff(self._eye._last, small).mean()) / 255.0
            self._eye._last = small

            # The frame enters the buffer as JPEG; compression is outside the
            # lock, the lock is only held while touching the list.
            ok, packed = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            raw = packed.tobytes() if ok else b""

            with self._lock:
                self._frame = frame
                self._at = time.time()
                self._history.append(Moment(at=self._at, change=change))
                # The history is bounded: a two-minute window is enough and
                # memory must not grow without limit.
                del self._history[:-HISTORY]
                if raw:
                    self._recent.append((self._at, raw))
                    while self._recent and self._at - self._recent[0][0] > RECENT_S:
                        self._recent.pop(0)
        except Exception:
            self._eye.close()

    # -- questions -----------------------------------------------------

    def jpeg_bytes(self) -> bytes:
        """The last JPEG for the preview. Does not reopen the camera."""
        with self._lock:
            return self._recent[-1][1] if self._recent else b""

    def snapshot(self) -> tuple[str, float]:
        """The newest frame and how many seconds ago it was taken."""
        with self._lock:
            if self._frame is None:
                return "", 0.0
            return _encode(self._frame), time.time() - self._at

    def recall(self, back_s: float) -> tuple[str, float]:
        """The best frame from the last `back_s` seconds and how many seconds ago it was taken.

        The answer to "what did I just show": if the user lowered what they
        showed, the current frame is empty. Of the frames in the window the
        **sharpest** is chosen — frames in motion are blurry, the frame
        taken while the shown thing is held still comes out sharp. On a tie
        the newer wins.
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
            # Sharpness measure: Laplacian variance. On a downscaled grey
            # frame — full resolution gives the same order and is ten times slower.
            gray = cv2.cvtColor(cv2.resize(frame, (320, 240)), cv2.COLOR_BGR2GRAY)
            score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            if score >= best_score:
                best_frame, best_at, best_score = frame, at, score

        if best_frame is None:
            # If the buffer is empty (camera just opened, was snoozed) the
            # last frame in hand is still an answer.
            return self.snapshot()
        return _encode(best_frame), now - best_at

    def arrival(self) -> bool:
        """Did someone come after a long silence?

        Like a small child: when nobody is in the room it settles into
        waiting, when something stirs it looks. Reporting every motion would
        be noise — what is reported is the **moment of arrival**.

        After reporting once it stays quiet for a while: reporting every
        time someone sits in the room and stirs is the same noise.
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
        """Motion summary of the last `seconds`. Without ever touching the model.

        The answer to "did something happen" is here: how many frames were
        looked at, what the peak change was, whether there was a busy moment.
        """
        now = time.time()
        with self._lock:
            window = [m for m in self._history if now - m.at <= seconds]

        if not window:
            return {"frames": 0, "peak": 0.0, "busy": 0, "quiet": True}

        peak = max(m.change for m in window)
        # A fixed threshold to weed out noise: below it camera jitter, above
        # it real motion.
        busy = sum(1 for m in window if m.change >= 0.04)
        return {
            "frames": len(window),
            "peak": round(peak, 3),
            "busy": busy,
            "quiet": busy == 0,
        }
