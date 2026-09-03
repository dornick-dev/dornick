"""Speech to text.

The browser's own `SpeechRecognition` API is not used: it does not exist
in WebView2, and where it does exist it sends the audio to Google. Here
recognition is local — `faster-whisper` runs on the computer, the audio
goes nowhere.

The model is downloaded on first use (`tiny` ~75 MB, `small` ~500 MB) and
then stays on disk. That is why the first call takes long; the UI says so
too.

The wake word is a separate matter. Listening continuously and feeding
every sound to the model burns both CPU and battery. Instead the browser
sends short chunks, they are transcribed here, and if the wake word occurs
in them the session opens. The small model is enough for this job: what is
sought is a single word.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INSTALL_HINT = "Sesli komut için: pip install 'dornick[listen]'"


def hint() -> str:
    """Missing-feature message shown to the user.

    In the developer checkout a pip suggestion is right; suggesting pip to
    someone who went through the installer wizard is pointless — they are
    told to re-run the wizard (component: Dinleme).
    """
    from . import environment

    if environment.kurulu_mu():
        return ("Dinleme özelliği bu kuruluma dahil edilmemiş. Kurulum "
                "sihirbazını yeniden çalıştırıp 'Dinleme (mikrofon)' "
                "bileşenini işaretleyerek ekleyebilirsin.")
    return INSTALL_HINT

# Size/accuracy trade-off. `tiny` is enough for the wake word; for
# dictation `small` is visibly better.
# `large-v3` is in the list: it runs comfortably on a 12 GB card and the
# accuracy jump in Turkish is there. Chosen without a card it falls to the
# CPU and the settings page says how slow it is.
SIZES = ("tiny", "base", "small", "medium", "large-v3")

DEFAULT_WAKE = "dornick"

# Punctuation and case are ignored in the wake-word check: the recogniser
# can write "Dornick," or "dornick.".
_CLEAN = re.compile(r"[^\w\s]", re.UNICODE)


@dataclass(slots=True)
class ListenConfig:
    """Voice-command settings.

    enabled: ships off. A program that turns the microphone on by itself is
        unacceptable; turning it on is the user's decision.
    wake: the word sought while continuous listening is on. Empty means
        waking is off, only push-to-talk works.
    size: model size. Bigger is more accurate but slower and takes more room.
    language: like "tr". Left empty, the recogniser guesses on its own —
        for Turkish leaving it to the guess gives visibly worse results.
    open: free listening. While on, no wake word is ever needed: every
        sentence heard goes to the agent.

        Right for someone working alone at home — who else could they be
        asking when they say "hava nasıl?". But if there is a television in
        the room or people are talking to each other, everything heard goes
        to the model. So it ships off and turning it on is the user's
        decision.
    """

    enabled: bool = False
    wake: str = DEFAULT_WAKE
    size: str = "small"
    language: str = "tr"
    open: bool = False
    # Domain vocabulary: words specific to the user's world (device names,
    # "Modbus", "SCADA" and the like). Whisper wrote them as if it had never
    # heard them — "Modbus" came out "mod bus", "SCADA" "eskada". Can also
    # be typed by hand in the settings; device and skill names are added
    # automatically at startup.
    vocab: str = ""


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _cuda_ready() -> bool:
    """Is running on the graphics card possible.

    On Windows ctranslate2 looks for the CUDA libraries on the DLL path, and
    the pip-installed `nvidia-*` packages put them inside site-packages —
    so by default they cannot be found. The folders are registered here;
    otherwise the first utterance blows up with "cublas64_12.dll not found".
    """
    try:
        import ctranslate2

        if not ctranslate2.get_cuda_device_count():
            return False
    except Exception:
        return False

    from . import gpu as gpu_module

    return gpu_module.cuda_libs_on_path()


class Listener:
    """Owner of the recogniser.

    The model is loaded once and stays in memory for the life of the
    process: reloading on every call made push-to-talk unusable (seconds
    every time).
    """

    def __init__(self, config: ListenConfig) -> None:
        self.config = config
        self._model: Any = None
        self._loaded_size = ""
        # Which device it runs on: the settings page shows this, because a
        # recogniser running on the CPU is the reason for the "hears late"
        # complaint.
        self.device = ""
        # Self-measuring downshift (live complaint, 30.08: on a weak laptop
        # continuous listening fell 10-20 s behind). If the decode time
        # clearly exceeds the audio length twice in a row, one size step
        # down is taken — ONLY for this session; the user's settings file is
        # not written.
        self._force_size = ""
        self._slow_hits = 0

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> Any:
        """Loads the model. The first call may take long because of the download."""
        want = self._force_size or self.config.size
        if self._model is not None and self._loaded_size == want:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - install path
            raise RuntimeError(hint()) from exc

        size = want if want in SIZES else "small"
        self._model = self._open(WhisperModel, size)
        self._loaded_size = size
        return self._model

    # Size chain: on a CPU that comes out slow, one step down. `tiny` is
    # deliberately absent — a quality cliff in Turkish; base is still of
    # usable accuracy.
    _DOWNSHIFT = {"large": "medium", "medium": "small", "small": "base"}

    def _speed_verdict(self, audio_s: float, elapsed_s: float) -> str | None:
        """Returns the size to step down to if the CPU decode is slow; else None.

        Criterion: the decode is clearly longer than the audio itself (and
        >2.5 s) — not once but TWICE IN A ROW. A single slow decode may be
        warm-up/other load; the second is a pattern.
        """
        if self.device != "cpu":
            return None
        if elapsed_s <= max(2.5, 1.3 * max(audio_s, 0.1)):
            self._slow_hits = 0
            return None
        self._slow_hits += 1
        if self._slow_hits < 2:
            return None
        self._slow_hits = 0
        return self._DOWNSHIFT.get(self._loaded_size or self.config.size)

    def _maybe_downshift(self, audio_s: float, elapsed_s: float) -> None:
        smaller = self._speed_verdict(audio_s, elapsed_s)
        if not smaller:
            return
        print(f"[dornick] dinleme: işlemci yavaş ({elapsed_s:.1f} sn / "
              f"{audio_s:.1f} sn ses) — model {self._loaded_size} → {smaller} "
              "(bu oturum için; ayar değişmedi)", flush=True)
        self._force_size = smaller
        self._model = None          # the smaller size loads on the next decode

    def _open(self, WhisperModel: Any, size: str) -> Any:
        """Opens the model; on the graphics card if there is one.

        Measurement (two-second utterance, this machine): `small` on the
        CPU 1.58 s, `base` 0.42 s. In two-stage listening these two add up
        and a latency close to two seconds comes out per utterance — not a
        conversation, a walkie-talkie. On the graphics card the same job
        takes a tenth.

        Without a card, or with the CUDA libraries not installed, it falls
        silently to the CPU: running slowly beats not running at all.
        """
        if _cuda_ready():
            try:
                model = WhisperModel(size, device="cuda", compute_type="float16")
                # An install where loading succeeds but the first decode
                # blows up (missing cublas, say) is possible: let it show
                # here, not while the user is talking.
                import numpy as np

                list(model.transcribe(np.zeros(16_000, dtype="float32"), beam_size=1)[0])
                self.device = "cuda"
                return model
            except Exception:
                pass

        # int8 is clearly faster on the CPU and the accuracy difference is
        # not noticeable for this job.
        self.device = "cpu"
        return WhisperModel(size, device="cpu", compute_type="int8")

    def _bias(self) -> str | None:
        """Vocabulary hint to the recogniser.

        Whisper treats `initial_prompt` like the previous speech and leans
        towards the words in it. Putting the wake word here makes it
        audible.
        """
        wake = self.config.wake.strip()
        parts = [f"{wake}. {wake}, merhaba." if wake else ""]
        # Domain words: the recogniser leans towards them and the chance of
        # writing the user's jargon ("Modbus", device names) correctly
        # rises. Kept short — Whisper cuts the prompt at ~200 tokens and a
        # long list overshadows the real speech.
        if vocab := self.config.vocab.strip():
            parts.append(vocab[:400])
        return " ".join(p for p in parts if p) or None

    def transcribe_array(self, samples: Any, rate: int = 16_000) -> str:
        """Transcribes audio samples in memory.

        For continuous listening: opening and deleting a temporary file for
        every utterance is both needless and, done several times a second,
        wears the disk. faster-whisper accepts an array directly. The decode
        time is measured here: if the CPU falls behind the audio the size
        drops on its own.
        """
        import time as _time
        audio_s = float(getattr(samples, "shape", [0])[0] or 0) / max(rate, 1)
        t0 = _time.perf_counter()
        try:
            return self._decode(samples, endpointed=True)
        finally:
            self._maybe_downshift(audio_s, _time.perf_counter() - t0)

    def transcribe(self, audio: Path | str) -> str:
        """Transcribes an audio file."""
        return self._decode(str(audio))

    def _decode(self, audio: Any, *, endpointed: bool = False) -> str:
        model = self.load()
        language = self.config.language.strip() or None
        # The ear already cuts by energy; Whisper's VAD on top both delays
        # and eats the first syllable. A file (push-to-talk) may contain
        # silence — keep VAD there.
        kwargs: dict[str, Any] = dict(
            language=language,
            vad_filter=not endpointed,
            beam_size=1,
            initial_prompt=self._bias(),
            temperature=0.0,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.2,
            no_speech_threshold=0.55,
            log_prob_threshold=-0.7,
            without_timestamps=True,
        )
        try:
            segments, _info = model.transcribe(audio, **kwargs)
        except TypeError:
            for key in ("compression_ratio_threshold", "no_speech_threshold",
                        "log_prob_threshold", "without_timestamps"):
                kwargs.pop(key, None)
            segments, _info = model.transcribe(audio, **kwargs)
        return _join_segments(segments, self.config.vocab)


# While the word is heard the recogniser can fuse or extend it:
# "dornick" → "ne o", "ne oldu", "neyo". A fused window that starts with
# the word and is at most this much longer is accepted.
#
# The trade-off is deliberate: "neon" wakes it too. An assistant that never
# wakes is worse than one that occasionally wakes for nothing.
WAKE_SLACK = 3


def _words(text: str) -> list[str]:
    return _CLEAN.sub(" ", (text or "").lower()).split()


def _windows(words: list[str]) -> list[str]:
    """Single words and fused pairs.

    "ne oldu" arrives as two words; without joining it cannot be compared
    to the word.
    """
    out = list(words)
    out += [a + b for a, b in zip(words, words[1:])]
    return out


# Laughter syllable: a word made only of these letters, with at least two
# "h"s in it, is laughter ("ahahah", "ıhıhıh", "hahaha").
_LAUGH = re.compile(r"^[haeıiouöüj]+$")
_VOWELS = set("aeıiouöüâîû")
_BARE_URL = re.compile(
    r"(?:www\.)?[a-z0-9][a-z0-9.-]*\.(com|net|org|io|dev)$",
    re.I,
)
_JUNK = frozenset({
    "altyazı m.k", "altyazı mk", "altyazı m k", "altyazı mk.",
    "thanks for watching", "thank you for watching",
    "izlediğiniz için teşekkürler", "abone ol", "subscribe",
    # Whisper prints the YouTube sign-off on Turkish silence/echo.
    # A real farewell is "hoşça kal" / "görüşürüz".
    "hoşça kalın", "hosca kalin", "hoşçakalın", "hoscakalin",
})

# Short sounds that carry no meaning on their own: laughter syllables,
# assent murmurs, thinking filler. The list is deliberately short and only
# kicks in when the **whole** utterance consists of these — "ahah tamam
# devam et" passes normally.
_FILLER = frozenset({
    "ha", "he", "hı", "hi", "ho", "hu",
    "ah", "eh", "ıh", "ih", "oh", "öh", "uh", "üh",
    "hm", "hmm", "hmmm", "ee", "eee", "ıı", "ııı",
    "öö", "ööö", "aa", "aaa", "uu", "uuu",
})


def _groan(word: str) -> bool:
    """Cough/groan: the same vowel drawn out (öööö, eeee)."""
    letters = [c for c in word.lower() if c.isalpha()]
    if len(letters) < 4:
        return False
    top, n = Counter(letters).most_common(1)[0]
    if n / len(letters) >= 0.7 and top in _VOWELS:
        return True
    squeezed = re.sub(r"(.)\1+", r"\1", word)
    return len(word) >= 8 and len(squeezed) / len(word) <= 0.35


def chatter(text: str) -> bool:
    """Is the utterance speech, or laughter/mumbling/coughing?

    In free listening everything heard went to the agent, and when the
    user laughed the agent produced a reply to every laugh — while the user
    had said nothing to it. Laughing, saying "hı hı", thinking "hmm", the
    "öööö" that comes out on a cough are not speech; they never reach the
    agent.

    The criterion is deliberately narrow: an utterance with a single real
    word in it ("ahah tamam devam et") passes as is.
    """
    words = [w for w in (_CLEAN.sub("", p.lower()) for p in (text or "").split()) if w]
    if not words:
        return True

    for word in words:
        if word in _FILLER:
            continue
        if _LAUGH.match(word) and word.count("h") >= 2 and len(word) >= 4:
            continue
        if _groan(word):
            continue
        return False
    return True


def hallucinated(text: str, vocab: str = "") -> bool:
    """Is it something the recogniser invented when it did not understand?

    The domain vocabulary (Modbus, SCADA) is written into `initial_prompt`;
    on a cough/noise Whisper prints those words — sometimes as
    `modbus.com`. A lone vocabulary word or a bare address is not speech.
    """
    raw = (text or "").strip().strip(" .,;:")
    if not raw:
        return True
    flat = " ".join(raw.casefold().split())
    if flat in _JUNK:
        return True
    if _BARE_URL.fullmatch(raw.rstrip(".")):
        return True
    tokens = {
        w.strip(" ,.;").casefold()
        for w in re.split(r"[,;\n]+", vocab or "")
        if w.strip()
    }
    if not tokens:
        return False
    words = _CLEAN.sub(" ", flat).split()
    if len(words) != 1:
        return False
    word = words[0]
    host = word.split(".")[0]
    return word in tokens or host in tokens


def _keep_segment(segment: Any) -> bool:
    """Drop the junk segment Whisper is 'sure' about too.

    On a cough compression_ratio comes out high; with no speech no_speech
    rises. Both are a cheap gate before the text filter.
    """
    cr = float(getattr(segment, "compression_ratio", 0.0) or 0.0)
    if cr > 2.2:
        return False
    nsp = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
    lp = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
    if nsp > 0.55 and lp < -0.5:
        return False
    return True


def _join_segments(segments: Any, vocab: str = "") -> str:
    parts: list[str] = []
    for segment in segments:
        text = str(getattr(segment, "text", "") or "").strip()
        if not text or not _keep_segment(segment):
            continue
        if chatter(text) or hallucinated(text, vocab):
            continue
        parts.append(text)
    joined = " ".join(parts).strip()
    if not joined or chatter(joined) or hallucinated(joined, vocab):
        return ""
    return joined


def heard_wake(text: str, wake: str = DEFAULT_WAKE) -> bool:
    """Does the wake word occur in the text?

    An exact match is not enough: the recogniser turns "dornick" into
    "ne oldu", a real word in Turkish. If a fused window starts with the
    word and has not grown too long it counts as heard.
    """
    word = _CLEAN.sub(" ", (wake or "").lower()).strip().replace(" ", "")
    if not word:
        return False

    return any(
        window.startswith(word) and len(window) <= len(word) + WAKE_SLACK
        for window in _windows(_words(text))
    )


# Sentence-ending punctuation. When the wake word comes last ("nasılsın
# dornick?") this mark belongs to the sentence, not the word: thrown away
# with the word, the question turns into a plain sentence and the
# intonation breaks when spoken.
_ENDING = re.compile(r"[?!.…]+$")


def after_wake(text: str, wake: str = DEFAULT_WAKE) -> str:
    """The sentence with the wake word removed. "dornick, borsayı aç" → "borsayı aç"

    The word can be **anywhere** in the sentence. The previous state only
    took what came after the word, and in a sentence where the word came
    last like "nasılsın dornick?" nothing remained: the screen said "duydum:
    nasılsın dornick?" and the agent never answered.

    The word itself is not part of the command; sending it to the model
    leads to a search for something called "dornick". Because the
    recogniser may have split the word into two ("ne oldu") the pair window
    is skipped too.

    If the word is in the middle of the sentence ("nasılsın dornick? iyi
    misin?") both sides remain — the previous state, taking what came after
    "dornick", threw away "nasılsın".
    """
    word = _CLEAN.sub(" ", (wake or "").lower()).strip().replace(" ", "")
    if not word:
        return (text or "").strip()

    raw = (text or "").split()
    clean = [_CLEAN.sub("", piece.lower()) for piece in raw]

    for index, piece in enumerate(clean):
        pair = piece + (clean[index + 1] if index + 1 < len(clean) else "")
        if piece.startswith(word) and len(piece) <= len(word) + WAKE_SLACK:
            return _without(raw, index, index + 1)
        if pair.startswith(word) and len(pair) <= len(word) + WAKE_SLACK:
            return _without(raw, index, index + 2)

    return (text or "").strip()


def _pre_wake_noise(raw: list[str]) -> bool:
    """Is the part before the word recogniser noise, or a real sentence?

    "şey ııı dornick raporu getir" → noise. "nasılsın dornick? iyi misin?" → not.
    """
    if not raw:
        return True
    if chatter(" ".join(raw)):
        return True
    words = [w for w in (_CLEAN.sub("", p.lower()) for p in raw) if w]
    real = [w for w in words if w not in _FILLER and not _groan(w)]
    if not real:
        return True
    return len(real) == 1 and len(real[0]) <= 3


def _without(raw: list[str], start: int, stop: int) -> str:
    """Removes the word from the sentence.

    If there is something **after** the word: if what precedes is noise it
    is dropped ("şey ııı dornick raporu getir"); if it is a real sentence
    both remain ("nasılsın dornick? iyi misin?"). If what follows is empty,
    what precedes is the command ("nasılsın dornick?").
    """
    after = raw[stop:]
    if after:
        # The leading comma was the word's separator ("dornick, borsayı aç"), not the sentence's.
        after_text = " ".join(after).strip(" ,;:")
        before = raw[:start]
        # If the word is in the MIDDLE of the sentence ("nasılsın dornick?
        # iyi misin?") both sides are the command. If what precedes is only
        # recogniser noise ("şey ııı dornick …") it is dropped as before.
        if before and not _pre_wake_noise(before):
            if mark := _ENDING.search(raw[stop - 1]):
                before = before[:-1] + [before[-1] + mark.group()]
            return (" ".join(before) + " " + after_text).strip(" ,;:")
        return after_text

    before = raw[:start]
    # If the word ends the sentence its punctuation is given back to the sentence.
    if before and (mark := _ENDING.search(raw[stop - 1])):
        before = before[:-1] + [before[-1] + mark.group()]
    return " ".join(before).strip(" ,;:")
