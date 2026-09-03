"""The always-listening ear.

Listening used to live in the browser and it cannot stay there: when the
window is hidden Chromium throttles background timers to once a minute, so
the three-second chunk loop dies. The request "say 'hey dornick' while the
program is closed and let it wake up" has no answer in the browser — it
has one here.

As with the camera the work is split in two:

    locally     is there sound? — RMS energy. Takes microseconds, the
                recogniser never wakes. In a quiet room nothing happens
                for hours.
    recogniser  when speech ends that chunk is transcribed once.

Then the wake word is looked for. No word, the text is thrown away —
nobody has listened, nothing is written anywhere, nothing goes to the
model.

Audio never leaves the computer: capture is here, recognition is here.

There are two separate threads and that is mandatory. Recognition is a
blocking job — measurement: the `small` model on the CPU decodes a
two-second utterance in 1.58 seconds. Done on the same thread, nothing is
read from the microphone during that time, the device buffer fills and
**the rest of the speech drops**. What the user saw was exactly that: a
sentence is said, the second sentence said right after is never heard.

    capture thread      only reads and measures energy — microseconds
    recognition thread  takes from the queue and decodes — seconds

The queue is bounded. If the recogniser cannot keep up **the oldest
drops**: decoding a late sentence is not worth missing the new one being
said right then.
"""

from __future__ import annotations

import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

INSTALL_HINT = "Sürekli dinleme için: pip install 'dornick[listen]'"

# Sample rate the recogniser expects. Even if the device runs at another
# rate, sounddevice brings it down to this.
RATE = 16_000

# Block length. It must be short: if the start of speech lands in the
# middle of a block the first syllable is cut.
BLOCK = 1600           # 0.1 s

# Speech threshold (RMS, 0..1). The noise floor of a quiet room is usually
# under 0.002; normal speech above 0.02. 0.012 missed a low voice: the user
# repeats 2–3 times, the same sentence piles up in the queue.
SPEECH = 0.008

# After speech, this much silence means the sentence is over. Shorter cuts
# the sentence in the middle (breath pauses), longer means late reaction.
# Recognition now starts on the first silence; this span is only the
# "is it continuing" confirmation — so that half a sentence does not go
# when CUDA decodes in 0.2 s.
HANG_S = 0.40

# A sound shorter than this does not count as speech: cough, door,
# keyboard. Waking the recogniser for those is both wasted and makes it
# invent sentences out of silence.
MIN_S = 0.35

# Margin waited after the speaker goes quiet so it stops hearing its own
# voice. Room echo does not cut off at once. It was 0.5: the reply given
# the moment the agent stopped (without a wake word) was dropped entirely
# in this window and looked like "it didn't hear" — 0.25 is enough for the
# echo tail.
DEAF_TAIL_S = 0.25
# In free listening there is no wake gate: if the tail stays short the
# speaker echo counts as a new utterance and the agent answers itself.
DEAF_TAIL_OPEN_S = 0.7
# After going quiet, if the transcript still resembles the speaker sentence,
# drop it (room echo). The margin also covers capture + Whisper latency
# (~1.5 s recognition); when 2 s was not enough the speaker sentence
# "Duydum: evet, seni gör" became a new request.
ECHO_HOLD_S = 4.0
# The same utterance twice: the user thinks "it didn't hear" and repeats,
# Whisper lags and both land. Within this window a similar command is one
# request.
DUP_S = 4.5
# Echo baseline for energy barge: on an empty baseline the first TTS block
# exceeded BARGE_FLOOR and mistook its own voice for "the user barged in".
ECHO_PRIME = 6

# Speaker echo exceeds the SPEECH threshold too; the user speaking into the
# microphone is louder. Rising above the echo baseline cuts TTS at once —
# without saying "dornick", without restarting the sentence.
BARGE_HOLD_S = 0.32
BARGE_FLOOR = 0.028
ECHO_BLOCKS = 12

# Maximum duration of deafness. The previous state was `float("inf")` and
# relied on the "I finished speaking" news coming from the browser. If that
# news never came — the tab is refreshed, the audio context hangs and
# `onended` never fires — the ear stayed shut forever. The level bar on
# screen kept moving (that measurement is made before deafness), so from
# outside it looked like "hears but doesn't care".
#
# Now every deafness ends on its own. Sentences are short; if the speaker
# keeps talking the browser reports again on every sentence and the span
# is refreshed.
DEAF_MAX_S = 20.0

# Maximum length of a single utterance. A long monologue keeps the
# recogniser waiting and the wake word is at the start anyway.
MAX_S = 12.0

# Margin taken back from the start of speech: when the threshold is crossed
# the first syllable has already passed.
PRE_S = 0.4

# Conversation window. Once talking has started there is no need to say the
# name in every sentence: you do not start every sentence to a person with
# "Ahmet" either, you carry on while the conversation lasts.
#
# The wake word is required to **start** the conversation. After it starts,
# everything said during this span counts as said to it, and the span is
# refreshed on every reply. When it expires the word is required again —
# otherwise every conversation in the room starts going to the model.
#
# The span is deliberately long: pauses in the middle of a conversation to
# think, look, write something easily exceeded forty-five seconds and the
# window closed right in the middle of the conversation.
ENGAGED_S = 180.0

# Maximum time the conversation can stay open on a single wake.
#
# It was unbounded and the window fed itself: every utterance heard and
# every reply of the agent refreshed the span; while the user talked to
# teammates in a game every "merhaba" went to the model and the reply
# reopened the window. In a real log this loop lasted half an hour. Now,
# this long after the last "dornick", the window closes no matter what;
# to continue the name must be said again.
ENGAGED_MAX_S = 600.0

# Number of utterances waiting for recognition. Small on purpose: if the
# recogniser cannot keep up, the accumulating queue leaves the agent
# minutes behind. At the limit the oldest utterance drops — a late
# sentence is worth less than the one being said right now.
BACKLOG = 3


def available() -> bool:
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(slots=True)
class Heard:
    text: str
    wake: bool
    command: str
    at: float
    # Barged in with the wake word while dornick was talking (TTS): "cut with dornick".
    # On seeing this the bridge first hushes the speech, then handles the command.
    barge: bool = False


def _words(text: str) -> list[str]:
    """Words with punctuation stripped. 'gör.' and 'görüyorum' count as the same stem."""
    cleaned = re.sub(r"[^\w\s]", " ", (text or "").casefold(), flags=re.UNICODE)
    return [w for w in cleaned.split() if w]


def _kin(a: str, b: str) -> bool:
    """Same stem / inflection: gör–görüyorum–görürüm. Exact equality not required."""
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a) or a in b or b in a):
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= 4 and n >= 0.5 * min(len(a), len(b))


def echo_of_self(said: str, tts: str) -> bool:
    """Is what was heard the echo of the sentence playing on the speaker?

    If the energy threshold cuts TTS by mistake, the transcript drops here —
    so the agent does not take its own words for a new request. Whisper
    shortens or inflects the sentence ('evet, seni gör' / 'görürüm' ←
    'görüyorum'); because of punctuation and inflection a whole-sentence
    match is not enough.
    """
    a, b = _words(said), _words(tts)
    got, src = " ".join(a), " ".join(b)
    if len(got) < 4 or len(src) < 4:
        return False
    if got in src or src in got:
        return True
    if not a:
        return False
    hits = sum(1 for w in a if any(_kin(w, t) for t in b))
    if len(a) == 1:
        return hits == 1 and len(a[0]) >= 6
    if hits >= 2 and hits / len(a) >= 0.5:
        return True
    # A fragment of the speaker sentence: one or two words matched, the rest
    # is 1–3 letter junk. Live: "Sen nasılsın" → Whisper "sende sos".
    # At least one kin is required — otherwise "ok" is echo after every TTS.
    if 1 <= len(a) <= 4 and hits >= 1:
        leftover = [w for w in a if not any(_kin(w, t) for t in b)]
        if not leftover or all(len(w) <= 3 for w in leftover):
            return True
    return False


# Real one-word replies in the echo window (evet/tamam/aç).
# Anything else is a TTS fragment like "soni" or a Whisper invention.
_SHORT_OK = frozenset({
    "evet", "hayır", "hayir", "yok", "var", "peki", "tamam", "olur", "olmaz",
    "aç", "ac", "kapat", "dur", "devam", "neden", "nasıl", "nasil", "niye",
    "iyi", "selam", "ha", "anladım", "anladim",
})
_ECHO_FAREWELL = frozenset({
    "hoşça kal", "hoşça kalın", "hosca kal", "hosca kalin",
    "görüşürüz", "gorusuruz", "güle güle", "gule gule",
    "iyi geceler", "iyi günler", "iyi gunler", "sonra konuşuruz",
})


def echo_junk(said: str, wake: str = "") -> bool:
    """Speaker echo / silence invention — even when it does not resemble
    the speaker text.

    `echo_of_self` only catches resemblance to the TTS sentence. When
    Whisper printed 'hoşça kalın' on echo (live: a farewell after merhaba)
    or wrote a fragment like 'soni', there was no match and the utterance
    became a new request.
    """
    from . import listen as recogniser

    if recogniser.heard_wake(said, wake or "dornick"):
        return False
    if recogniser.hallucinated(said) or recogniser.chatter(said):
        return True
    words = _words(said)
    if not words:
        return True
    flat = " ".join(words)
    if flat in _ECHO_FAREWELL:
        return True
    if len(words) <= 3 and any(p in flat for p in _ECHO_FAREWELL):
        return True
    # A one-word fragment ("soni") is not a request. "anladım" / "nasılsın"
    # are real replies — dropping those too became "sometimes it never hears".
    if len(words) == 1 and words[0] not in _SHORT_OK and len(words[0]) <= 4:
        return True
    return False


class Ear:
    """Keeps the microphone always open, transcribes only what is spoken.

    Runs on its own thread and recognition happens there too: both are
    blocking jobs and must not touch the agent's loop.
    """

    def __init__(
        self,
        listener: Any,
        heard: Callable[[Heard], None],
        *,
        wake: str = "dornick",
        level: Callable[[float], None] | None = None,
        scout: Any = None,
        open: bool = False,
    ) -> None:
        self.listener = listener
        # Free listening: the wake word is never looked for. Right for
        # someone working alone at home — who else could they be asking when
        # they say "hava nasıl?".
        self.open = open
        # Small, fast model for the wake scan. Measurement: `base` catches
        # the word in 0.47 seconds, `small` decodes correctly in 1.43
        # seconds. Using both together is both quick and accurate: first
        # the small one checks "did the word occur", if so the big one
        # decodes the sentence.
        self.scout = scout or listener
        self.heard = heard
        self.wake = wake
        self.level = level
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # The only link between capture and recognition. Recognition is a
        # blocking job and cannot be done on the capture thread: during that
        # time nothing is read from the microphone and the rest of the
        # speech drops.
        self._work: queue.Queue[Any] = queue.Queue(maxsize=BACKLOG)
        self._dropped = 0
        self._loud = 0.0
        # Its own voice. The microphone heard the speech coming out of the
        # speaker and thought "someone is talking" — with an always-open
        # microphone that means an assistant talking to itself.
        self._deaf_until = 0.0
        # Until when the conversation is open. Within this span the wake
        # word is not looked for.
        self._engaged_until = 0.0
        # Moment of the last wake: the window cannot be refreshed beyond
        # ENGAGED_MAX_S past this.
        self._wake_at = 0.0
        # The other senses (like the eye) to open along with a wake.
        # "I'll call when I'm back" means a single call: "dornick" reopens
        # them all, the user does not have to name sense by sense.
        self.companions: list[Any] = []
        # Snooze. When the user says "don't listen to me" the agent turns
        # this on with the `hearing` tool. Before there was no such gate and
        # the agent said "I'm off" and kept listening — claiming to have
        # done something it could not do, the worst kind of lie. The wake
        # word pierces the snooze: the user can always call it back by
        # saying "dornick".
        self._snooze_until = 0.0
        # The microphone's real state. When the stream could not be opened
        # the thread died silently and the organ still said "dinliyor": the
        # user says "uyan dornick", nothing happens and the reason was
        # written nowhere.
        self.live = False
        self.failure = ""
        self._barge_open = False
        self._tts_text = ""
        self._tts_until = 0.0
        self._echo: deque[float] = deque(maxlen=ECHO_BLOCKS)
        self._last_ask = ""
        self._last_ask_at = 0.0
        # Moment of the most recently captured utterance: if recognition
        # takes minutes the old result must not land together with the new
        # utterance (both at once when the user says "dornick").
        self._latest_at = 0.0

    def speaking(self, on: bool, text: str = "") -> None:
        """Closes the ear while the agent talks.

        The sound coming out of the speaker comes back into the microphone.
        Echo cancellation at the OS level does not always work, and when it
        does not the assistant hears its own sentence and tries to reply.

        If the user talks over the speaker the energy threshold breaks the
        deafness (`_trip_barge`). If `speaking(False)` arrives at that
        moment the tail margin (`DEAF_TAIL_S`) would leave the rest of the
        sentence deaf again — the tail is skipped so the rest of the
        interrupting utterance is heard.
        """
        now = time.monotonic()
        if on:
            already = now < self._deaf_until
            self._deaf_until = now + DEAF_MAX_S
            chunk = (text or "").strip()
            if chunk:
                if already and self._tts_text:
                    merged = (self._tts_text + " " + chunk).strip()
                    self._tts_text = merged[-280:]
                else:
                    self._tts_text = chunk
            self._tts_until = now + DEAF_MAX_S + ECHO_HOLD_S
            # Consecutive sentences are the same speech: wiping the baseline
            # pushed the first TTS block above BARGE_FLOOR again and its own
            # voice was taken for a "barge-in".
            if not already:
                self._barge_open = False
                self._echo.clear()
            return
        if self._barge_open:
            self._deaf_until = 0.0
            return
        tail = DEAF_TAIL_OPEN_S if self.open else DEAF_TAIL_S
        self._deaf_until = now + tail
        self._tts_until = now + ECHO_HOLD_S

    def _barge_loud(self, loud: float) -> bool:
        """Above the speaker echo, is the user talking into the microphone?

        If the baseline is room noise the speaker has not yet reached the
        microphone — the first TTS block exceeded BARGE_FLOOR and cut its
        own voice (live: 'soni' + barged in, the speaker split its own
        sentence).
        """
        if len(self._echo) < ECHO_PRIME:
            return False
        ordered = sorted(self._echo)
        base = ordered[len(ordered) // 2]
        if base < BARGE_FLOOR:
            return False
        return loud >= max(BARGE_FLOOR, base * 1.8 + 0.008)

    def _tail_loud(self, loud: float) -> bool:
        """TTS is over: is this energy room echo or microphone speech?

        Echo exceeds the SPEECH threshold (0.008) for a long time; when
        every excess after going quiet became a new utterance, Whisper
        wrote the speaker tail as 'sende sos'. The user talking into the
        microphone rises above the baseline — not as much as cutting TTS
        (1.8x) requires.
        """
        if len(self._echo) < ECHO_PRIME:
            return loud >= SPEECH
        ordered = sorted(self._echo)
        base = ordered[len(ordered) // 2]
        return loud >= max(SPEECH * 2.2, base * 1.35 + 0.006)

    def _echoing(self) -> bool:
        """Is the speaker sentence still in the air / in the recognition queue?"""
        return bool(self._tts_text) and time.monotonic() < self._tts_until

    def _repeat_ask(self, command: str) -> bool:
        """Is it a repeat of the command just handled — the same utterance piled in the queue."""
        text = (command or "").strip()
        if not text:
            return False
        now = time.monotonic()
        prev = self._last_ask
        if prev and now - self._last_ask_at < DUP_S:
            if (echo_of_self(text, prev) or echo_of_self(prev, text)):
                return True
            a, b = " ".join(_words(text)), " ".join(_words(prev))
            if a and b and (a == b or a in b or b in a):
                return True
        self._last_ask = text
        self._last_ask_at = now
        return False

    def _trip_barge(self) -> None:
        """Cut TTS at once, open the ear — do not wait for recognition."""
        self._barge_open = True
        self._deaf_until = 0.0
        hush = getattr(self, "on_hush", None)
        if hush is None:
            return
        try:
            hush()
        except Exception:
            pass

    @property
    def deaf(self) -> bool:
        return time.monotonic() < self._deaf_until

    @property
    def snoozed(self) -> bool:
        """Snoozed — only the wake word passes."""
        return time.monotonic() < self._snooze_until

    def snooze(self, seconds: float = 0.0) -> None:
        """Silences the ear. Can be indefinite; saying "dornick" always opens it.

        The indefinite form is not an endless wait: its exit is tied not to
        an uncertain event but to the wake word or a `resume` call.
        """
        self._snooze_until = (
            time.monotonic() + seconds if seconds > 0 else float("inf")
        )
        self._engaged_until = 0.0
        from . import prefs as prefs_mod
        prefs_mod.tell(getattr(self, "on_snooze", None), True)

    def unsnooze(self) -> None:
        was = self.snoozed
        self._snooze_until = 0.0
        if was:
            from . import prefs as prefs_mod
            prefs_mod.tell(getattr(self, "on_snooze", None), False)

    @property
    def engaged(self) -> bool:
        """Is the conversation open — no wake word needed during this span."""
        if self.snoozed:
            return False
        return self.open or time.monotonic() < self._engaged_until

    def engage(self, seconds: float = ENGAGED_S) -> None:
        """Opens the conversation or refreshes its span.

        Called when the agent gives a reply: the conversation has started,
        and expecting the name afterwards is like expecting every sentence
        to start with "Ahmet".

        Two limits. Never opens while snoozed. And the refresh cannot go
        beyond ENGAGED_MAX_S past the last wake: if it could, every
        utterance heard and every reply given pushed the window forward and
        room talk flowed to the model forever — in a real log it lasted
        half an hour.
        """
        if self.snoozed:
            return
        wanted = time.monotonic() + max(0.0, seconds)
        if self._wake_at:
            wanted = min(wanted, self._wake_at + ENGAGED_MAX_S)
        self._engaged_until = wanted

    def disengage(self) -> None:
        self._engaged_until = 0.0

    @property
    def loudness(self) -> float:
        """Last measured sound level. The UI shows this."""
        return self._loud

    @property
    def backlog(self) -> int:
        """Number of utterances waiting for recognition. Non-zero means the agent is behind."""
        return self._work.qsize()

    @property
    def dropped(self) -> int:
        """Number of utterances dropped because the recogniser could not keep up."""
        return self._dropped

    def start(self) -> bool:
        if not available():
            return False
        # Recognition starts first: when capture puts the first utterance in
        # the queue it should find a running worker opposite.
        threading.Thread(target=self._recognise, daemon=True, name="dornick-ear-asr").start()
        # Warm-up: model loading (download on first setup + opening from
        # disk) must not ride on the back of the FIRST UTTERANCE — live
        # complaint (30.08): the first sentence lagged 10-20 s and most of
        # that was loading. In the background, without blocking startup; if
        # it crashes the first utterance loads the old way.
        def _warm() -> None:
            try:
                self.listener.load()
                if self.scout is not self.listener:
                    self.scout.load()
            except Exception:
                pass
        threading.Thread(target=_warm, daemon=True, name="dornick-ear-warm").start()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="dornick-ear")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    # -- loop ----------------------------------------------------------

    def _loop(self) -> None:
        import numpy as np
        import sounddevice as sd

        speech: list[Any] = []
        recent: list[Any] = []          # the blocks right before speech
        quiet_since = 0.0
        started = 0.0
        deaf_seg = False                # is the segment being captured during TTS
        handed = False                  # has this utterance entered the recognition queue

        try:
            stream = sd.InputStream(
                samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK
            )
            stream.start()
        except Exception as exc:
            # No microphone or another program holds it. The program keeps
            # running but the reason is now recorded: the previous state
            # returned silently and the organ kept saying "dinliyor".
            self.failure = f"{type(exc).__name__}: {exc}"
            self.live = False
            return

        self.live = True
        self.failure = ""

        try:
            while not self._stop.is_set():
                try:
                    block, _overflow = stream.read(BLOCK)
                except Exception:
                    self._stop.wait(0.5)
                    continue

                mono = block[:, 0]
                loud = float(np.sqrt(np.mean(mono * mono)))
                self._loud = loud
                if self.level is not None:
                    self.level(loud)

                now = time.monotonic()
                deaf = now < self._deaf_until
                # While Dornick talks the SPEECH threshold catches the echo
                # too. When the user talks over the speaker the energy rises
                # above the baseline; at that moment TTS is cut and the same
                # buffer keeps listening.
                waiting = deaf and not self._barge_open and not self.snoozed

                if waiting:
                    if not speech:
                        self._echo.append(loud)
                    if self._barge_loud(loud):
                        if not speech:
                            speech = [mono.copy()]
                            started = now
                            deaf_seg = True
                            handed = False
                        else:
                            speech.append(mono.copy())
                        quiet_since = 0.0
                        if now - started >= BARGE_HOLD_S:
                            self._trip_barge()
                    elif speech:
                        if now - started < BARGE_HOLD_S:
                            speech, quiet_since, started, deaf_seg = (
                                [], 0.0, 0.0, False
                            )
                            handed = False
                        else:
                            speech.append(mono.copy())
                            if not quiet_since:
                                quiet_since = now
                                if now - started >= MIN_S and not handed:
                                    self._hand_over(
                                        np.concatenate(speech), deaf_seg
                                    )
                                    handed = True
                            if now - quiet_since >= HANG_S or now - started >= MAX_S:
                                if now - started >= MIN_S and not handed:
                                    self._hand_over(
                                        np.concatenate(speech), deaf_seg
                                    )
                                speech, quiet_since, started = [], 0.0, 0.0
                                handed = False
                    recent = []
                    continue

                # The speaker went quiet but the room still rings. The SPEECH
                # threshold catches the tail too; Whisper takes it for a new
                # utterance.
                if (self._echoing() and not self._barge_open
                        and not self.snoozed and not speech):
                    self._echo.append(loud)
                    if not self._tail_loud(loud):
                        recent = []
                        continue

                if loud >= SPEECH:
                    if not speech:
                        # When the threshold is crossed the first syllable
                        # has already passed; the blocks right before are
                        # taken too.
                        speech = list(recent)
                        started = now
                        deaf_seg = deaf
                        handed = False
                    elif quiet_since:
                        # Not a breath pause, the sentence continues — the
                        # in-flight recognition must not send half a sentence.
                        self._latest_at = now
                        handed = False
                    speech.append(mono.copy())
                    quiet_since = 0.0
                elif speech:
                    speech.append(mono.copy())
                    if not quiet_since:
                        # First silence: let recognition start, the
                        # end-of-sentence confirmation overlaps recognition
                        # for HANG_S.
                        quiet_since = now
                        if now - started >= MIN_S and not handed:
                            self._hand_over(np.concatenate(speech), deaf_seg)
                            handed = True
                    if now - quiet_since >= HANG_S or now - started >= MAX_S:
                        # Very short sounds are not speech: cough, door,
                        # keyboard. We do not wake the recogniser for those.
                        if now - started >= MIN_S and not handed:
                            self._hand_over(np.concatenate(speech), deaf_seg)
                        speech, quiet_since, started = [], 0.0, 0.0
                        handed = False
                elif not deaf:
                    recent.append(mono.copy())
                    del recent[: -int(PRE_S * RATE / BLOCK) or None]
                else:
                    recent = []
        finally:
            self.live = False
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _hand_over(self, audio: Any, deaf: bool = False) -> None:
        """Hands the utterance to the recognition thread. Never waits.

        Waiting even a millisecond on the capture thread means the sound
        arriving in that time drops. If the queue is full the oldest
        utterance is thrown away: decoding a late sentence is not worth
        missing the one being said right now.

        `deaf`: the segment was captured while dornick was talking (TTS). If
        the energy threshold opened the ear (`_barge_open`) the whole
        sentence is kept; otherwise recognition only looks for the wake word.

        The echo stamp is set at capture time: Whisper takes 1–2 s, and even
        if ECHO_HOLD has expired by then the speaker sentence does not
        become a new request.
        """
        echo = bool(deaf or self._barge_open or self._echoing())
        captured = time.monotonic()
        self._latest_at = captured
        while True:
            try:
                self._work.put_nowait((audio, deaf, echo, captured))
                return
            except queue.Full:
                try:
                    self._work.get_nowait()
                    self._dropped += 1
                except queue.Empty:
                    return

    def _recognise(self) -> None:
        """Takes from the queue and decodes. Free to block: nobody waits here."""
        while not self._stop.is_set():
            try:
                item = self._work.get(timeout=0.25)
            except queue.Empty:
                continue
            # Throw away old utterances waiting in the queue: if the user
            # repeated, only the last one counts. Otherwise when Whisper
            # finishes, the sentence from minutes ago and "dornick" land at
            # the same time.
            while True:
                try:
                    item = self._work.get_nowait()
                    self._dropped += 1
                except queue.Empty:
                    break
            audio, deaf = item[0], item[1]
            echo = item[2] if len(item) > 2 else bool(deaf)
            captured = item[3] if len(item) > 3 else time.monotonic()
            try:
                self._settle(audio, deaf, echo=echo, captured=captured)
            except Exception:
                # An error in the recogniser must not leave the ear deaf.
                continue

    def _settle(self, audio: Any, deaf: bool = False, *, echo: bool = False,
                captured: float | None = None) -> None:
        """An utterance ended: look for the wake word, if it occurred decode the sentence.

        Two stages, because they are different jobs. For the "did the word
        occur" question the small model is enough and four times faster;
        but having it decode the command produces a meaningless sentence.
        Measurement: `base` 0.47 s, `small` 1.43 s.
        """
        from . import listen as recogniser

        given = captured
        captured = time.monotonic() if captured is None else captured
        # If a newer utterance was captured, do not recognise this one —
        # when Whisper lagged, the sentence from minutes ago and "dornick"
        # landed in the chat at the same time.
        if captured < self._latest_at:
            self._barge_open = False
            return

        # The scout is only useful on the CPU. Measurement (real Turkish
        # sentence, this machine): on the CPU `small` 1.58 s, `base` 0.42 s
        # — two stages total 2 s and the gain is large. On the graphics card
        # `small` 0.18 s, `base` 0.12 s: running both makes 0.30 s, so the
        # scout **slows things down**.
        #
        # The decision is made here because which device is in use only
        # becomes known after the model loads, and loading at startup kept
        # the window shut for the length of a download.
        #
        # The scout's job is the GATE: did the word occur, is it echo, are
        # we snoozed. When the conversation is already open (open/engaged)
        # there is no gate — every utterance goes to the big model anyway
        # and the scout was only 0.42 s of extra waiting. In that case a
        # single pass straight with the big model: ~1.6 s per sentence
        # instead of ~2.0 s.
        gate_needed = deaf or self.snoozed or not (self.open or self.engaged)
        scout = self.scout if gate_needed else self.listener
        if scout is not self.listener and getattr(self.listener, "device", "") == "cuda":
            scout = self.listener

        try:
            scan = scout.transcribe_array(audio, RATE)
        except Exception:
            return

        if not scan.strip():
            return

        vocab = str(getattr(getattr(self.listener, "config", None), "vocab", "") or "")

        # While the conversation is open the word is not looked for: once
        # talking has started there is no need to say the name in every
        # sentence.
        woken = recogniser.heard_wake(scan, self.wake)
        barged = bool(self._barge_open)

        # BARGE-IN: sound captured while dornick talks. If the energy
        # threshold opened the ear (`_barge_open`) no wake word is needed —
        # the user spoke over the speaker, the sentence is kept. Otherwise
        # only "dornick" can barge in; without it the echo is ignored.
        if deaf and not barged:
            if not woken:
                return
            self._deaf_until = 0.0
            barged = True
        elif barged:
            self._deaf_until = 0.0

        # While snoozed only the wake word passes — and the moment it does
        # the snooze lifts: saying "dornick" is calling it back.
        if self.snoozed:
            if not woken:
                return
            self.unsnooze()

        if woken:
            self._wake_at = time.monotonic()
            # The call reopens the ear (and companions: network cameras).
            # The built-in camera is the HUD/chat switch; "dornick" does not light it.
            for sense in self.companions:
                try:
                    sense.unsnooze()
                except Exception:
                    pass

        if not woken and not self.open and not self.engaged and not barged:
            # No word and the conversation is closed: it ends here. The big
            # model never wakes, the text is written nowhere, nothing goes
            # to the model.
            return

        # Cough / mumble / invented address — do not wake the big model either.
        if not woken and (recogniser.chatter(scan)
                          or recogniser.hallucinated(scan, vocab)):
            self._barge_open = False
            return

        # Now decode properly. On a short utterance the second model adds
        # ~1.4 s (CPU) and there is no gain on a sentence like "merhaba dornick".
        try:
            said = scan
            if scout is not self.listener and len(scan.split()) > 12:
                said = self.listener.transcribe_array(audio, RATE)
        except Exception:
            said = scan

        if not (said or "").strip():
            self._barge_open = False
            return

        # Laughter, coughing and a word the recogniser invented are not
        # speech. In free listening, when the user laughed the agent
        # produced a reply to every laugh — while nothing had been said to
        # it. If called by the word it passes: "dornick hahaha" is
        # deliberate. The window is not refreshed either: laughing does not
        # keep the conversation open.
        if not woken and (recogniser.chatter(said)
                          or recogniser.hallucinated(said, vocab)):
            self._barge_open = False
            return

        # If the energy threshold cut TTS by mistake — or in free listening
        # the room echo after the speaker went quiet became a new utterance
        # — the transcript resembles the sentence on the speaker. Its own
        # words are not a request. Whisper can also print something on echo
        # that does not resemble the TTS ('hoşça kalın', 'soni') — that is
        # not a request either.
        echoing = barged or echo or self._echoing()
        if echoing and (
            echo_of_self(said, self._tts_text)
            or echo_of_self(scan, self._tts_text)
            or echo_junk(said, self.wake)
            or echo_junk(scan, self.wake)
        ):
            self._barge_open = False
            return

        if woken:
            # The big model may have written the word differently; both are
            # searched so the command is not lost.
            command = (recogniser.after_wake(said, self.wake) or
                       recogniser.after_wake(scan, self.wake))
        else:
            # Middle of the conversation: everything said is the command.
            command = said.strip()

        if self._repeat_ask(command or said.strip()):
            self._barge_open = False
            return

        if captured < self._latest_at:
            self._barge_open = False
            return

        # If handed over at the first silence: recognition overlaps HANG,
        # but when CUDA finishes in 0.2 s wait for confirmation so a breath
        # pause does not become half a sentence.
        if given is not None:
            hold = given + HANG_S
            while time.monotonic() < hold:
                if captured < self._latest_at:
                    self._barge_open = False
                    return
                if self._stop.wait(0.04):
                    return
            if captured < self._latest_at:
                self._barge_open = False
                return

        # The conversation continues: the window is refreshed.
        self.engage()
        self._barge_open = False

        self.heard(Heard(text=said, wake=woken, command=command,
                         at=time.time(), barge=barged or deaf))
