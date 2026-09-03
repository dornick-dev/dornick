"""Spoken speech.

The operating system's own synthesizer (SAPI on Windows) talks like a robot
— it feels like talking to a switchboard recording rather than an
assistant. Microsoft's neural voices are used here: for Turkish
`tr-TR-EmelNeural` and `tr-TR-AhmetNeural`, both in a real human tone.

The price is the internet: the audio is produced in the cloud. Without a
network, speech shuts off silently and the text stays in place — the
absence of a voice must not stop the work.

The text to be spoken is not the same as the text on screen. Reading a
code block aloud is meaningless ("three backticks powershell dollar u r l
equals…"), and so is a table. `speakable()` drops those and what remains is
what can be spoken.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# The speech-producing package is optional: if it is not installed speech
# stays off and the program keeps running.
INSTALL_HINT = "Sesli konuşma için: pip install 'dornick[voice]'"


def hint() -> str:
    """Missing-package message: in the installed layout, suggest repair, not pip.

    edge-tts is part of the installer package; its absence in an install
    means an incomplete/broken install — re-running the wizard repairs it.
    """
    from . import environment

    if environment.is_installed():
        return ("Ses paketi bu kurulumda eksik görünüyor. Kurulum "
                "sihirbazını yeniden çalıştırmak eksiği onarır.")
    return INSTALL_HINT

DEFAULT_VOICE = "tr-TR-EmelNeural"

# Maximum characters spoken in one go. Long text means both latency and an
# uninterruptible monologue; it is sent sentence by sentence anyway.
MAX_CHARS = 1200

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`]*`")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_MARK = re.compile(r"[*_#>~]+")
_PATH = re.compile(r"\S*[\\/]\S*[\\/]\S*")
_BLANK = re.compile(r"\n{2,}")
_SPACES = re.compile(r"[ \t]{2,}")


@dataclass(slots=True)
class VoiceConfig:
    """Spoken-speech settings.

    enabled: ships off. A program that starts talking on its own is
        annoying; turning it on is the user's decision.
    rate/pitch: edge-tts format ("+0%", "-10%", "+5Hz"). Speed varies a lot
        per person — some find 1.0 slow.
    """

    enabled: bool = False
    name: str = DEFAULT_VOICE
    rate: str = "+0%"
    pitch: str = "+0Hz"
    # Character of the voice: 0 pure human, 1 fully machine. The synthesizer
    # produces a human voice and reads flatly; this value adds a layer on
    # top of the voice in the browser (doubling, timbre, a slight tremor).
    # It sits somewhere in the middle: neither a switchboard recording nor
    # an exact human imitation.
    character: float = 0.35


def available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def speakable(text: str, limit: int = MAX_CHARS) -> str:
    """Extracts what will be spoken from the on-screen text.

    Reading a code block aloud is meaningless; so are tables, addresses and
    file paths. They are dropped and nothing is put in their place: saying
    "code block" would be a noise repeated in every answer.
    """
    out = _FENCE.sub(" ", text or "")
    out = _TABLE_ROW.sub(" ", out)
    out = _INLINE_CODE.sub(" ", out)
    # In a link the thing to read is the text, not the address.
    out = _LINK.sub(r"\1", out)
    out = _URL.sub(" ", out)
    out = _PATH.sub(" ", out)
    out = _MARK.sub("", out)
    out = _SPACES.sub(" ", out)
    out = _BLANK.sub("\n", out)
    out = "\n".join(line.strip() for line in out.splitlines() if line.strip())
    return out[:limit].strip()


# Tone of the sentence. Turkish voices have no SSML emotion style (all are
# "General"), but rate and pitch can be adjusted per sentence. This is a
# real intonation — not acting, but it does end the flat reading.
#
# Values kept small: exaggerated, it sounds weird rather than human.
TONES: tuple[tuple[str, int, int], ...] = (
    # (when, rate %, pitch Hz)
    ("soru", 2, 4),        # question: the voice rises at the end
    ("unlem", 8, 6),       # excitement: a bit faster, a bit higher
    ("uyari", -3, -4),     # problem/error: slows and lowers, turns serious
    ("tereddut", -5, 1),   # unsure: slow but pitch slightly up
    ("bulus", 6, 5),       # found it / done: livens up
    ("duraklama", -6, -2), # ellipsis: slows, lowers
    ("uzun", -4, -1),      # long sentence: narration tempo
    ("kisa", 4, 2),        # short sentence: lively
)

# Sentence length counted as long.
LONG = 90

# Content cues. Punctuation alone is not enough: "Bir sorun var." and
# "Tamam, oldu." end with the same full stop but must not be said in the
# same tone.
#
# The list is deliberately short. A long word list catches the wrong
# sentence and produces an odd intonation; the ones here are harmless even
# when they misfire.
CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("uyari", ("sorun", "hata", "başarısız", "çalışmıyor", "dikkat",
               "uyarı", "olmadı", "bulamadım", "yapamadım")),
    ("tereddut", ("sanırım", "galiba", "belki", "emin değilim",
                  "olabilir", "muhtemelen", "bakmam lazım")),
    ("bulus", ("buldum", "tamam", "oldu", "hazır", "bitti", "çalışıyor",
               "başardık", "harika")),
)


def tone_of(text: str) -> tuple[str, str]:
    """Rate and pitch by sentence. Returned in edge-tts format.

    The reason for the flat reading was one setting applied to the whole
    answer: a question and an exclamation came out in the same tone.
    """
    words = (text or "").strip()
    if not words:
        return "+0%", "+0Hz"

    # Question and exclamation first: they determine the whole sentence.
    # Then content, length last — "Bir sorun var." and "Tamam, oldu." end
    # with the same full stop and read flatly both came out the same.
    lower = words.lower()
    if words.endswith("…") or words.endswith("..."):
        key = "duraklama"
    elif words.endswith("?"):
        key = "soru"
    elif words.endswith("!"):
        key = "unlem"
    elif found := next((k for k, cues in CUES if any(c in lower for c in cues)), ""):
        key = found
    elif len(words) > LONG:
        key = "uzun"
    elif len(words) < 30:
        key = "kisa"
    else:
        return "+0%", "+0Hz"

    _, rate, pitch = next(t for t in TONES if t[0] == key)
    return f"{rate:+d}%", f"{pitch:+d}Hz"


def _blend(base: str, shift: str, unit: str) -> str:
    """Adds the sentence's tone to the user's setting.

    The rate in the setting is a personal preference; the intonation rides
    on top of it, it does not replace it.
    """
    try:
        first = int(str(base).rstrip(unit).replace("+", "") or 0)
        second = int(str(shift).rstrip(unit).replace("+", "") or 0)
    except ValueError:
        return base
    return f"{first + second:+d}{unit}"


async def synthesize(text: str, config: VoiceConfig) -> bytes:
    """Turns text into mp3. Returns empty when there is nothing to say."""
    if not (words := speakable(text)):
        return b""

    try:
        import edge_tts
    except ImportError as exc:  # pragma: no cover - install path
        raise RuntimeError(hint()) from exc

    rate, pitch = tone_of(words)
    speech = edge_tts.Communicate(
        words,
        config.name or DEFAULT_VOICE,
        rate=_blend(config.rate or "+0%", rate, "%"),
        pitch=_blend(config.pitch or "+0Hz", pitch, "Hz"),
    )
    return b"".join([chunk["data"] async for chunk in speech.stream() if chunk["type"] == "audio"])


async def voices(prefix: str = "") -> list[dict[str, Any]]:
    """Available voices. With `prefix` given, filters by language ("tr")."""
    try:
        import edge_tts
    except ImportError:
        return []

    try:
        listing = await edge_tts.list_voices()
    except Exception:  # no network, no voice list either
        return []

    return [
        {
            "id": voice["ShortName"],
            "locale": voice["Locale"],
            "gender": voice.get("Gender", ""),
            # The voice's character is the most useful information when choosing.
            "tone": ", ".join(voice.get("VoiceTag", {}).get("VoicePersonalities", [])),
        }
        for voice in listing
        if not prefix or voice["Locale"].lower().startswith(prefix.lower())
    ]
