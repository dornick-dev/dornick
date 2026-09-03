"""The agent's body: its senses and the modules it has attached to itself.

The web on the stage shows what the agent **knows**. This file shows what
the agent **can do**: microphone, cameras, speaker and the modules it wrote
for itself (map, PLC, USB — whatever it wrote).

Why a separate layer: a memory and a camera are not the same thing. A
memory is recalled, a camera is opened. Making both the same node type
left the question "what is it using right now" unanswered.

Nothing here is made up. Every organ shown in the list really has a
counterpart: the microphone exists if the microphone package is installed,
the camera exists if a camera is configured, the module exists if there is
a skill file in the workshop. Drawing something that does not exist, even
faintly, would be a lie that looks like it is working on screen.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Organ kinds. Each kind gets its own colour on the stage.
SENSE = "sense"      # sense: microphone, camera
SPEECH = "speech"    # speaker
MODULE = "module"    # a skill the agent wrote for itself
DEVICE = "device"    # registered device: PLC, remote camera, serial port, MCP


@dataclass(slots=True)
class Organ:
    id: str
    name: str
    kind: str
    # What it is — the line read on hover.
    detail: str
    # Its current state: "dinliyor", "kapalı", "açık". Must be short, it
    # fits under the label.
    state: str
    # Whether it is really running. This is the faint/bright distinction.
    live: bool = False
    # Names of the tools that use this organ. When a tool is called the
    # stage knows from this which organ lights up.
    tools: list[str] = field(default_factory=list)


# The camera probe really opens the device and was measured: 518 ms. The
# settings page cannot call this on every open, so the result is kept for
# a while. The microphone list is too cheap to measure (<0.1 ms), no
# caching there. It was 60 s; the UI probes the organs every 30 s and
# roughly every second request burnt half a second on the HTTP thread. A
# camera is not something plugged and unplugged — keeping it 5 minutes is
# safe.
_CAMERA_TTL = 300.0
_camera_seen: tuple[float, bool] | None = None


def has_microphone() -> bool:
    """Is there an audio device with input on the machine.

    Showing a non-existent microphone as switchable in the settings means
    making the user click a button that does not work — and nowhere does it
    say why it does not work.
    """
    try:
        import sounddevice
    except Exception:
        return False
    try:
        return any(d["max_input_channels"] > 0 for d in sounddevice.query_devices())
    except Exception:
        return False


def has_camera(lens: Any = None) -> bool:
    """Is there a camera on the machine.

    If there is an open buffer the question is already answered: the camera
    exists and is running. Otherwise the device is opened and closed briefly
    and the result is kept.
    """
    global _camera_seen
    import time

    if lens is not None and getattr(lens, "live", False):
        return True

    now = time.monotonic()
    if _camera_seen and now - _camera_seen[0] < _CAMERA_TTL:
        return _camera_seen[1]

    found = False
    try:
        import cv2

        capture = cv2.VideoCapture(0, getattr(cv2, "CAP_DSHOW", 0))
        found = bool(capture.isOpened())
        capture.release()
    except Exception:
        found = False

    _camera_seen = (now, found)
    return found


def _mic(config: Any, ear: Any) -> Organ:
    from . import ear as hearing

    # If an ear object EXISTS the package/device probe is not consulted: a
    # stream has been opened or an attempt was made, and its real state
    # (failure, deaf, listening) is more accurate than the probe. When the
    # probe got in the way, a real failure was reported as "yok".
    if ear is None:
        if not hearing.available():
            return Organ("mic", "Mikrofon", SENSE,
                         "ses paketi kurulu değil", "yok", False, [])
        if not has_microphone():
            return Organ("mic", "Mikrofon", SENSE,
                         "bu makinede giriş yapan bir ses aygıtı yok", "yok", False, [])
        # Hardware present but the user turned it off in settings: the
        # reason must be said. "Kapalı" alone reads like a failure; this is
        # a preference.
        if not bool(getattr(getattr(config, "listen", None), "enabled", False)):
            return Organ("mic", "Mikrofon", SENSE,
                         "kullanıcı ayarlardan kapatmış; o istemedikçe dinleme yok",
                         "kapalı", False, [])
        return Organ("mic", "Mikrofon", SENSE,
                     "sürekli dinleme kapalı", "kapalı", False, [])

    # The real state, not the optimistic one. Saying "dinliyor" when the
    # stream could not be opened makes the user talk to an ear that is not
    # there.
    if failure := getattr(ear, "failure", ""):
        return Organ("mic", "Mikrofon", SENSE,
                     f"mikrofon akışı açılamadı — {failure}", "arıza", False, [])
    if not getattr(ear, "live", True):
        return Organ("mic", "Mikrofon", SENSE,
                     "kulak henüz açılmadı ya da kapandı", "kapalı", False, [])

    if getattr(ear, "snoozed", False):
        return Organ("mic", "Mikrofon", SENSE,
                     "kullanıcı istedi diye susturuldu; \"dornick\" demek geri açar",
                     "susturuldu", False, [])

    word = getattr(getattr(config, "listen", None), "wake", "dornick")
    return Organ(
        "mic", "Mikrofon", SENSE,
        f"sürekli açık; yalnızca \"{word}\" geçen söz ajana gidiyor",
        "sağır" if ear.deaf else "dinliyor",
        not ear.deaf,
        [],
    )


_LENS_NAME = "Bilgisayar kamerası"
_LENS_TOOLS = ["look", "kamera"]


def _lens(config: Any, lens: Any) -> Organ:
    if lens is not None and getattr(lens, "snoozed", False):
        return Organ("lens", _LENS_NAME, SENSE,
                     "kullanıcı istedi diye susturuldu; \"dornick\" demek geri açar",
                     "susturuldu", False, list(_LENS_TOOLS))

    # If it is off in settings the device is NOT touched at all. The probe
    # really opens the camera briefly (the LED blinks) — for a user who
    # deliberately turned the camera off this means "I turned it off but the
    # light is on". For someone who turned it off the camera counts as
    # absent; whether it exists is only asked when it is turned on.
    if lens is None and not bool(getattr(getattr(config, "camera", None), "enabled", False)):
        return Organ("lens", _LENS_NAME, SENSE,
                     "kullanıcı ayarlardan kapatmış; o istemedikçe bakılmaz, "
                     "aygıt yoklanmaz", "kapalı", False, list(_LENS_TOOLS))

    live = lens is not None and getattr(lens, "live", False)
    if not live and not has_camera(lens):
        return Organ("lens", _LENS_NAME, SENSE,
                     "bu makinede kamera bulunamadı", "yok", False, list(_LENS_TOOLS))

    return Organ(
        "lens", _LENS_NAME, SENSE,
        _sight_detail("sürekli açık tampon; kareler kendiliğinden modele "
                      "gitmiyor, `look` veya `kamera kesit` istediğinde alınıyor"),
        "açık" if live else "kapalı",
        live,
        list(_LENS_TOOLS),
    )


def _voice(config: Any) -> Organ:
    from . import voice as speaking

    setting = getattr(config, "voice", None)
    on = bool(getattr(setting, "enabled", False)) and speaking.available()
    return Organ(
        "voice", "Ses", SPEECH,
        getattr(setting, "name", "") or "sesli konuşma",
        "açık" if on else "kapalı",
        on,
        [],
    )


def _sight_detail(base: str) -> str:
    """If GPU analysis is on the agent should know: text goes, not frames."""
    try:
        from . import sight as sight_mod
        if sight_mod.status().get("ready"):
            return (base + "; NVIDIA GPU yerelde nesneleri okuyor, "
                    "sohbet modeline metin gidiyor")
    except Exception:
        pass
    return base


def _cameras(config: Any) -> list[Organ]:
    """Externally connected cameras. Empty list if none is configured."""
    from . import watch as watching

    try:
        cameras = watching.load(Path(config.state_dir))
    except Exception:
        return []

    organs: list[Organ] = []
    for camera in cameras:
        if camera.is_builtin():
            # The built-in webcam is "Bilgisayar kamerası" in the `_lens` organ — duplicate.
            continue
        detail = _sight_detail(
            "izlenen kamera; hareket yerelde ölçülüyor, yalnızca bir şey "
            "değiştiğinde soru soruluyor")
        if note := (camera.last_note or "").strip():
            detail += f"; son: {note[:80]}"
        organs.append(Organ(
            f"cam:{camera.id}", camera.name, SENSE,
            detail,
            "izliyor" if getattr(camera, "enabled", True) else "duruyor",
            bool(getattr(camera, "enabled", True)),
            ["kamera"],
        ))
    return organs


def _modules(config: Any) -> list[Organ]:
    """The skills the agent wrote for itself.

    Drawing a map, reading a value from a PLC address, probing a device
    over USB: whichever it wrote stands here as an organ. Not a hand-kept
    list — read from the files in the workshop.
    """
    from . import skills as authored

    try:
        found, _broken = authored.discover(config.open_sandbox().root)
    except Exception:
        return []

    return [
        Organ(
            f"skill:{skill.name}", skill.name, MODULE,
            (skill.description or "").strip().splitlines()[0][:160],
            "hazır", True, [skill.name],
        )
        for skill in found
    ]


def _devices(config: Any) -> list[Organ]:
    """Registered devices: PLC, remote camera, arm on a serial port, MCP server.

    The record itself does nothing — it says where to connect. So it is not
    `live`: it is not verified as connected, only defined. It stands faint
    on the stage and lights up when the skill that drives it is called.
    """
    from . import devices as declared

    try:
        found, _broken = declared.load(config.open_sandbox().root)
    except Exception:
        return []

    return [
        Organ(
            f"device:{device.id}", device.name, DEVICE,
            device.summary or declared.line(device),
            declared.KIND_STATE.get(device.kind, "tanımlı"),
            False,
            # When the skill driving the device is called this organ lights
            # up on the stage: the box itself is not a tool, the script
            # attached to it is.
            list(device.skills),
        )
        for device in found
    ]


def _hand(config: Any) -> Organ:
    """Screen and hand: the agent being able to use the computer itself."""
    from .tools import hands as control

    if not control.available():
        return Organ("hand", "El", SENSE,
                     "ekran ve fare kontrolü bu makinede yok (Windows + Pillow gerekli)",
                     "yok", False, ["screen", "hand"])
    return Organ(
        "hand", "El", SENSE,
        "ekranı görür (`screen`), fareyi ve klavyeyi sürer (`hand`)",
        "hazır", True, ["screen", "hand"],
    )


def senses(config: Any, *, ear: Any = None, lens: Any = None) -> list[Organ]:
    """Senses and limbs: microphone, camera, voice, hand.

    The stage draws the whole inventory; the system prompt needs these
    four. Kept separate so the prompt does not count devices and modules a
    second time — they have their own sections.
    """
    return [_mic(config, ear), _lens(config, lens), _voice(config), _hand(config)]


def inventory(config: Any, *, ear: Any = None, lens: Any = None) -> list[dict[str, Any]]:
    """The agent's current body. The stage draws this."""
    organs = senses(config, ear=ear, lens=lens)
    organs += _cameras(config)
    organs += _devices(config)
    organs += _modules(config)
    return [asdict(organ) for organ in organs]
