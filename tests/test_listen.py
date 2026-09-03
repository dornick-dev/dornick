"""Voice commands and the wake word.

Recognition itself is not tested here because it requires a model
download; what is tested is **how the word is understood**. An assistant
that wakes when a word like "neon" occurs is unusable, and one that leaves
the word inside the command starts looking for something called "dornick".
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from dornick import listen
from dornick.config import Config


# -- wake word ---------------------------------------------------------


def test_the_wake_word_is_heard() -> None:
    assert listen.heard_wake("dornick borsayı aç")


def test_case_and_punctuation_do_not_matter() -> None:
    """The recogniser can write "Dornick," or "dornick."."""
    assert listen.heard_wake("Dornick, borsayı aç")
    assert listen.heard_wake("DORNICK! uyan")


def test_a_much_longer_word_does_not_wake_it() -> None:
    """Not every word starting with the wake word should wake it."""
    assert not listen.heard_wake("neoklasik mimari")
    assert not listen.heard_wake("neolitik dönem")


def test_the_recogniser_splitting_the_word_still_wakes_it() -> None:
    """This was the real problem: the wake word is not a real word in
    Turkish and the recogniser can split it into pieces. The sentence
    "Dornick, dışarısı sıcak mı" can come out as "Dor nik dışarısı sıcak
    mı"; the fused window must still hear it (tolerance WAKE_SLACK)."""
    assert listen.heard_wake("Dor nick dışarısı sıcak mı?")
    assert listen.heard_wake("dor nick borsayı aç")
    assert listen.after_wake("Dor nick dışarısı sıcak mı?") == "dışarısı sıcak mı?"
    assert listen.after_wake("dor nick borsayı aç") == "borsayı aç"


def test_an_unrelated_sentence_does_not_wake_it() -> None:
    assert not listen.heard_wake("bugün hava çok güzel")


def test_an_empty_wake_word_never_matches() -> None:
    """An empty word must not mean "everything wakes it"; leaving it empty
    in the settings means turning waking off."""
    assert not listen.heard_wake("dornick uyan", wake="")
    assert not listen.heard_wake("herhangi bir şey", wake="   ")


def test_a_custom_wake_word_works() -> None:
    assert listen.heard_wake("jarvis raporu getir", wake="jarvis")
    assert not listen.heard_wake("dornick raporu getir", wake="jarvis")


# -- after the word ----------------------------------------------------


def test_the_word_itself_is_stripped() -> None:
    """Leaving the word in the command leads the model to look for
    something called "dornick"."""
    assert listen.after_wake("dornick borsayı aç") == "borsayı aç"


def test_punctuation_around_the_word_is_handled() -> None:
    assert listen.after_wake("Dornick, borsayı aç") == "borsayı aç"


def test_words_before_the_wake_word_are_dropped_too() -> None:
    """The recogniser can invent noise before it."""
    assert listen.after_wake("şey ııı dornick raporu getir") == "raporu getir"


def test_a_sentence_without_the_word_comes_back_whole() -> None:
    assert listen.after_wake("borsayı aç") == "borsayı aç"


def test_only_the_wake_word_leaves_nothing() -> None:
    """If only "dornick" was said there is no command to send."""
    assert listen.after_wake("dornick") == ""


# -- settings ----------------------------------------------------------


def test_the_microphone_is_off_until_asked_for(tmp_path: Path) -> None:
    """A program that turns the microphone on by itself is unacceptable."""
    assert not Config.load(tmp_path).listen.enabled


def test_settings_survive_a_restart(tmp_path: Path) -> None:
    from dornick import settings

    config = Config.load(tmp_path)
    config.ensure_dirs()
    settings.apply(config, {"listen": {"enabled": True, "wake": "jarvis", "size": "tiny"}})

    reloaded = Config.load(tmp_path).listen
    assert reloaded.enabled and reloaded.wake == "jarvis" and reloaded.size == "tiny"


def test_the_settings_page_knows_whether_the_package_is_installed(tmp_path: Path) -> None:
    from dornick import settings

    config = Config.load(tmp_path)
    config.ensure_dirs()
    shown = settings.snapshot(config)["listen"]

    assert shown["available"] == listen.available()
    assert shown["sizes"] == list(listen.SIZES)


def test_an_unknown_size_falls_back(tmp_path: Path) -> None:
    """A silly size in a hand-edited file must not bring the program down."""
    ear = listen.Listener(listen.ListenConfig(size="devasa"))
    if not listen.available():
        pytest.skip("recognition package not installed")

    # Really loading would download the model; we only verify the choice.
    assert ear.config.size not in listen.SIZES
    assert not ear.ready


# -- the always-listening ear ------------------------------------------


def test_the_ear_needs_the_audio_package() -> None:
    """Without the package it gives up silently; the program must keep running."""
    from dornick import ear

    silent = ear.Ear(listener=None, heard=lambda _h: None)
    if not ear.available():
        assert not silent.start()


def test_only_speech_crosses_the_threshold() -> None:
    """In a quiet room nothing should happen for hours: the recogniser does
    not wake, no text is produced, nothing goes to the model."""
    import numpy as np

    from dornick import ear

    quiet = np.random.normal(0, 0.001, 1600).astype("float32")
    speech = np.random.normal(0, 0.05, 1600).astype("float32")

    assert float(np.sqrt(np.mean(quiet * quiet))) < ear.SPEECH
    assert float(np.sqrt(np.mean(speech * speech))) > ear.SPEECH


def test_a_transcript_without_the_wake_word_is_dropped() -> None:
    """Nothing without the word is recorded, shown, or sent to the model.
    With an always-open microphone this is mandatory."""
    import numpy as np

    from dornick import ear

    class Deaf:
        def transcribe_array(self, samples, rate):
            return "bugün hava çok güzel"

    caught: list = []
    silent = ear.Ear(Deaf(), caught.append, wake="dornick")
    silent._settle(np.zeros(1600, dtype="float32"))

    assert caught == []


def test_the_wake_word_is_passed_on_without_itself() -> None:
    import numpy as np

    from dornick import ear

    class Hears:
        def transcribe_array(self, samples, rate):
            return "Dornick dışarısı sıcak mı?"

    caught: list = []
    listening = ear.Ear(Hears(), caught.append, wake="dornick")
    listening._settle(np.zeros(1600, dtype="float32"))

    assert len(caught) == 1
    assert caught[0].wake
    assert caught[0].command == "dışarısı sıcak mı?"


def test_a_failing_recogniser_does_not_kill_the_ear() -> None:
    import numpy as np

    from dornick import ear

    class Boom:
        def transcribe_array(self, samples, rate):
            raise RuntimeError("model düştü")

    caught: list = []
    listening = ear.Ear(Boom(), caught.append)
    listening._settle(np.zeros(1600, dtype="float32"))   # must not blow up

    assert caught == []


# -- latency -----------------------------------------------------------
#
# The complaint "it hears too late, I can't talk in real time" had two
# causes and both are held here.


def test_recognition_does_not_block_the_microphone() -> None:
    """Recognition cannot be done on the capture thread.

    Measurement: the `small` model on the CPU decodes a two-second
    utterance in 1.58 seconds. Done on the same thread, nothing is read
    from the microphone during that time, the device buffer fills and the
    rest of the speech drops — a sentence is heard, the one said right
    after is not.
    """
    import time

    from dornick import ear

    class Slow:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            time.sleep(0.4)
            return "dornick dur"

    listening = ear.Ear(Slow(), lambda _h: None, wake="dornick")
    listening.start()

    try:
        began = time.monotonic()
        listening._hand_over([0.0])
        # The hand-over must be instant: if the capture thread waits here, audio drops.
        assert time.monotonic() - began < 0.05
    finally:
        listening.stop()


def test_recognition_starts_on_the_first_silence() -> None:
    """Waiting 0.4 s for the end of the sentence and recognising AFTER was
    half the latency. It enters the queue at the first silence; HANG is
    only the 'is it continuing' confirmation."""
    import inspect

    from dornick import ear

    loop = inspect.getsource(ear.Ear._loop)
    settle = inspect.getsource(ear.Ear._settle)
    assert "if not quiet_since:" in loop
    assert "handed" in loop
    assert "given + HANG_S" in settle


def test_a_backlog_drops_the_oldest_not_the_newest() -> None:
    """If the recogniser cannot keep up, the accumulating queue leaves the
    agent minutes behind. Decoding a late sentence is not worth missing the
    one being said right now."""
    from dornick import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)

    for index in range(ear.BACKLOG + 2):
        listening._hand_over(index)

    assert listening.backlog == ear.BACKLOG
    assert listening.dropped == 2
    # What remains are the newest. Queue items: (audio, deaf, echo, captured).
    item = listening._work.get_nowait()
    assert item[0] == 2 and item[1] is False and item[2] is False
    assert isinstance(item[3], float)


def test_the_recogniser_runs_on_the_graphics_card_when_it_can() -> None:
    """A recogniser running on the CPU is the reason for the "hears late" complaint.

    Measurement (real Turkish sentence, this machine): `small` on the CPU
    1.58 s, on the graphics card 0.18 s. Without a card it falls silently to
    the CPU — running slowly beats not running at all.
    """
    import inspect

    source = inspect.getsource(listen.Listener._open)
    assert 'device="cuda"' in source
    assert 'device="cpu"' in source


def test_endpointed_clips_skip_whisper_vad() -> None:
    """The ear already cut the sentence; Whisper's VAD both delays and eats
    the first syllable. It was part of the 'detects too late' complaint."""
    import inspect

    array = inspect.getsource(listen.Listener.transcribe_array)
    decode = inspect.getsource(listen.Listener._decode)
    assert "endpointed=True" in array
    assert "vad_filter=not endpointed" in decode
    assert "without_timestamps=True" in decode


def test_the_cuda_libraries_are_put_on_the_dll_path() -> None:
    """The pip-installed `nvidia-*` packages put the DLLs inside
    site-packages; they are not found from there on their own. Both are
    needed: `add_dll_directory` only works for loads that use the search
    flag, ctranslate2 calls plain `LoadLibrary`.

    Whisper and the camera analysis use the same DLL path (`gpu.cuda_libs_on_path`).
    """
    import inspect

    from dornick import gpu

    source = inspect.getsource(gpu.cuda_libs_on_path)
    assert "add_dll_directory" in source
    assert 'os.environ["PATH"]' in source
    assert "cuda_libs_on_path" in inspect.getsource(listen._cuda_ready)


def test_the_wake_word_can_come_last() -> None:
    """"nasılsın dornick?" — the word comes last.

    The previous state only took what came after the word and nothing
    remained: the screen said "duydum: nasılsın dornick?" and the agent
    never answered.
    """
    assert listen.after_wake("nasılsın dornick?") == "nasılsın?"
    assert listen.after_wake("kamerada ne görüyorsun dornick") == "kamerada ne görüyorsun"


def test_a_question_on_both_sides_of_the_name_stays_whole() -> None:
    """Live: "nasılsın dornick? iyi misin?" — the word in the middle; the
    previous state threw away "nasılsın" and sent only "iyi misin?"."""
    assert listen.after_wake("nasılsın dornick? iyi misin?") == "nasılsın? iyi misin?"
    assert listen.after_wake("hava nasıl dornick bugün ne yapıyoruz") == (
        "hava nasıl bugün ne yapıyoruz"
    )


def test_a_question_stays_a_question() -> None:
    """The mark after the word belongs to the sentence: thrown away with
    the word, the question turns into a plain sentence and the intonation
    breaks when spoken."""
    assert listen.after_wake("nasılsın dornick?").endswith("?")
    assert listen.after_wake("bugün nasıl gidiyor dornick!").endswith("!")


def test_only_the_name_leaves_nothing() -> None:
    """If only the name was called there is no command. Staying silent
    there is the same as not hearing — the desktop side answers this with a
    short reply."""
    assert listen.after_wake("dornick") == ""
    assert listen.after_wake("Dornick!") == ""


def test_being_called_by_name_still_gets_an_answer() -> None:
    """The screen saying "duydum" and nothing happening was the complaint:
    when only the name is called (empty command) a reply still comes."""
    import inspect

    from dornick import desktop

    source = inspect.getsource(desktop._open_ear)
    assert "CALLED_ASK" in source


def test_settings_reload_starts_the_python_ear() -> None:
    """If saving settings does not open the ear, whatever the user says
    only push-to-talk is heard — the browser PTT and the Python ear are
    separate."""
    import inspect

    from dornick import desktop

    reload_src = inspect.getsource(desktop.Bridge.reload)
    sync = inspect.getsource(desktop.Bridge.sync_hearing)
    boot = inspect.getsource(desktop._boot)
    wanted = inspect.getsource(desktop._hearing_wanted)
    power = inspect.getsource(desktop.Bridge.hearing_power)
    assert "self.sync_hearing(config)" in reload_src
    assert "_open_ear" in sync
    assert "listen.open" in sync
    assert "sync_hearing" in boot
    assert "ear=bridge.ear" in boot
    assert "listen.open" in wanted
    assert "wake.strip()" in wanted
    assert '"open": bool(on)' in power


def test_speaking_again_queues_instead_of_cancelling() -> None:
    """Rule (user): a new utterance during a running turn does NOT cancel,
    it queues — only an explicit stop word ("dur/yeter/kes") stops the
    running one."""
    import inspect

    from dornick import desktop

    source = inspect.getsource(desktop._open_ear)
    # The new utterance goes into the queue (submit), NO unconditional interrupt.
    assert "bridge.submit(" in source
    # Cancel only on an explicit stop word: interrupt sits in an _is_stop branch.
    assert "_is_stop(" in source
    assert not re.search(r"if bridge\.busy:\s*\n\s*bridge\.interrupt\(\)\s*\n\s*bridge\.submit",
                         source), "the unconditional barge-in must not have come back"


# -- deafness and the conversation window ------------------------------


def test_deafness_always_expires_on_its_own() -> None:
    """Deafness was `float("inf")` and relied on the "I finished speaking"
    news coming from the browser.

    If that news never came — the tab is refreshed, the audio context hangs
    and `onended` never fires — the ear stayed shut forever. The level bar
    kept moving (that measurement is made before deafness), so from outside
    it looked like "I see the signal but nothing happens".
    """
    from dornick import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening.speaking(True)

    assert listening.deaf
    assert listening._deaf_until < float("inf")
    assert listening._deaf_until - time.monotonic() <= ear.DEAF_MAX_S + 1


def test_the_wake_word_is_only_needed_to_start() -> None:
    """Once talking has started there is no need to say the name in every
    sentence: you do not start every sentence to a person with their name
    either."""
    from dornick import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "kamerada ne var"

    listening = ear.Ear(Hears(), caught.append, wake="dornick")

    # Conversation closed: no word, nothing passes.
    listening._settle([0.0])
    assert not caught

    # The agent replied: the conversation opened.
    listening.engage()
    listening._settle([0.0])

    assert len(caught) == 1
    assert caught[0].wake is False
    assert caught[0].command == "kamerada ne var"


def test_the_window_closes_again() -> None:
    """When the span expires the word is needed again — otherwise every
    conversation in the room starts going to the model."""
    from dornick import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening.engage(0.0)
    assert not listening.engaged

    listening.engage()
    assert listening.engaged
    listening.disengage()
    assert not listening.engaged


def test_the_turn_reopens_the_window() -> None:
    """If the window does not open when a reply is given, the user has to
    say "dornick" in every sentence."""
    import inspect

    from dornick import desktop

    # Message handling moved from pump to _isle (for the first-setup gate);
    # the call that opens the ear is now there.
    source = inspect.getsource(desktop.Bridge._isle)
    assert "self.ear.engage()" in source


def test_free_listening_needs_no_wake_word() -> None:
    """For someone working alone at home, who else could they be asking
    when they say "hava nasıl?". Expecting a wake word is a walkie-talkie,
    not an assistant."""
    from dornick import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "hava nasıl"

    free = ear.Ear(Hears(), caught.append, wake="dornick", open=True)
    free._settle([0.0])

    assert len(caught) == 1
    assert caught[0].command == "hava nasıl"
    assert caught[0].wake is False


def test_free_listening_is_off_until_asked_for(tmp_path: Path) -> None:
    """If there is a television in the room everything heard goes to the model."""
    assert not Config.load(tmp_path).listen.open


def test_the_conversation_window_outlasts_a_pause() -> None:
    """Forty-five seconds was short: pauses in the middle of a conversation
    to think, look, write something easily exceeded it and the window
    closed right in the middle of the conversation."""
    from dornick import ear

    assert ear.ENGAGED_S >= 120


# -- laughter and mumbling ---------------------------------------------


def test_laughter_is_not_a_message() -> None:
    """In free listening, when the user laughed the agent produced a reply
    to every laugh — while nothing had been said to it. Laughing is not speech."""
    for sound in ("ahahahah", "ıhıhıh.", "hahaha", "he he he", "hmm", "hı hı"):
        assert listen.chatter(sound), sound


def test_real_speech_is_not_mistaken_for_laughter() -> None:
    """The narrowness of the filter matters: a single real word is enough.
    "harika" and "hava" carry an h but are not laughter."""
    for said in ("hava nasıl", "harika oldu", "ahah tamam devam et", "depoya bak"):
        assert not listen.chatter(said), said


def test_a_cough_is_not_a_message() -> None:
    """A cough became 'öööö' in Whisper and a phantom utterance landed in the chat."""
    groaning = "ö" * 80
    assert listen.chatter(groaning)
    assert listen.chatter("eeeeee")
    assert not listen.chatter("öğretmen geldi")


def test_a_prompt_leak_is_not_a_message() -> None:
    """When it did not understand it invented 'modbus.com' from the vocabulary — that is not a command."""
    vocab = "Modbus, SCADA, PLC, register"
    assert listen.hallucinated("modbus.com", vocab)
    assert listen.hallucinated("Modbus", vocab)
    assert listen.hallucinated("Altyazı M.K.")
    assert listen.hallucinated("hoşça kalın")
    assert listen.hallucinated("hoşça kalın.")
    assert not listen.hallucinated("hoşça kal")
    assert not listen.hallucinated("Modbus cihazını oku", vocab)
    assert not listen.hallucinated("hava nasıl", vocab)


def test_a_cough_never_reaches_the_agent() -> None:
    from dornick import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "ö" * 80

    listening = ear.Ear(Hears(), caught.append, wake="dornick", open=True)
    listening._settle([0.0])
    assert not caught


def test_a_hallucinated_url_never_reaches_the_agent() -> None:
    from dornick import ear
    from types import SimpleNamespace

    caught: list[ear.Heard] = []

    class Hears:
        config = SimpleNamespace(vocab="Modbus, SCADA, PLC")

        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "modbus.com"

    listening = ear.Ear(Hears(), caught.append, wake="dornick", open=True)
    listening._settle([0.0])
    assert not caught


def test_laughter_never_reaches_the_agent() -> None:
    from dornick import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "ahahahah"

    listening = ear.Ear(Hears(), caught.append, wake="dornick", open=True)
    listening._settle([0.0])

    assert not caught


def test_laughter_does_not_keep_the_window_open() -> None:
    """Laughing does not keep the conversation open: the window is only
    refreshed by real speech, otherwise the span never expires between laughs."""
    from dornick import ear

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "hahaha"

    listening = ear.Ear(Hears(), lambda _h: None, wake="dornick")
    listening.engage(0.0)
    listening._settle([0.0])

    assert not listening.engaged


def test_calling_it_while_laughing_still_works() -> None:
    """"dornick hahaha" is a deliberate call: if the name occurs it passes."""
    from dornick import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "dornick hahaha"

    listening = ear.Ear(Hears(), caught.append, wake="dornick")
    listening._settle([0.0])

    assert len(caught) == 1 and caught[0].wake


# -- microphone failure -------------------------------------------------


def test_a_dead_stream_is_not_reported_as_listening() -> None:
    """When the stream could not be opened the thread died silently and the
    organ kept saying "dinliyor": the user says "uyan dornick", nothing
    happens and the reason was written nowhere."""
    from dornick import ear, organs
    from dornick.config import Config

    class Broken:
        deaf = False
        live = False
        failure = "PortAudioError: aygıt başka bir programda"

    mic = next(
        o for o in organs.inventory(Config.load(Path(".")), ear=Broken())
        if o["id"] == "mic"
    )
    assert mic["state"] == "arıza"
    assert "PortAudioError" in mic["detail"]
    assert not mic["live"]


def test_the_failure_reason_is_recorded_not_swallowed() -> None:
    """`except Exception: return` left an undiagnosable failure."""
    import inspect

    from dornick import ear

    source = inspect.getsource(ear.Ear._loop)
    assert "self.failure" in source
    assert "self.live" in source


# -- snooze and the window ceiling -------------------------------------
#
# Real log: while the user played a game every word said to teammates
# flowed to the model, the agent produced a reply to each; when the user
# said "don't listen to me" it said "I'm off" and kept listening.


def _hears(text="merhaba"):
    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return text

    return Hears()


def test_snooze_actually_silences() -> None:
    """Saying "I'm off" is only true when it is really off."""
    from dornick import ear

    caught = []
    listening = ear.Ear(_hears(), caught.append, wake="dornick", open=True)
    listening.snooze()

    listening._settle([0.0])
    assert not caught
    assert not listening.engaged     # even free listening does not pass


def test_the_wake_word_pierces_the_snooze() -> None:
    """Shutting fully would mean being uncallable: "dornick" always opens it."""
    from dornick import ear

    caught = []
    listening = ear.Ear(_hears("dornick geldim"), caught.append, wake="dornick")
    listening.snooze()
    listening._settle([0.0])

    assert len(caught) == 1
    assert not listening.snoozed     # the call lifted the snooze


def test_a_timed_snooze_expires() -> None:
    from dornick import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening.snooze(0.0001)
    import time as clock

    # On Windows the time.monotonic() resolution is ~15 ms; a 10 ms sleep
    # sometimes does not advance the clock at all and the tiny snooze looked
    # "not expired" (flaky). 50 ms safely exceeds the granularity.
    clock.sleep(0.05)
    assert not listening.snoozed


def test_engage_cannot_reopen_a_snoozed_ear() -> None:
    """If the end-of-turn refresh pierces the snooze, "I'm off" is a lie again."""
    from dornick import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening.snooze()
    listening.engage()

    assert not listening.engaged


def test_the_window_cannot_be_kept_open_forever() -> None:
    """The window fed itself: every utterance and every reply pushed the
    span forward, room talk flowed to the model forever — it lasted half an
    hour in the log. The ceiling is ENGAGED_MAX_S after the last wake."""
    import time as clock

    from dornick import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening._wake_at = clock.monotonic() - ear.ENGAGED_MAX_S  # ceiling passed
    listening.engage()

    assert not listening.engaged


def test_senses_tool_pauses_hearing_and_sight_together() -> None:
    """"Don't listen to me and don't watch me" is a single intent: making
    it call two tools separately means one gets forgotten. In a real log
    exactly that happened — the ear went quiet, the agent said "I'm not
    watching" but the camera kept taking frames."""
    import asyncio

    from dornick import ear
    from dornick.tools import build_registry

    registry = build_registry(subagents=False)
    listening = ear.Ear(listener=None, heard=lambda _h: None, open=True)

    class Sight:
        snoozed = False

        def snooze(self, seconds=0.0):  # noqa: ANN001, ANN202
            self.snoozed = True

        def unsnooze(self):  # noqa: ANN202
            self.snoozed = False

    seeing = Sight()

    class Ctx:
        ear = listening
        lens = seeing
        watcher = None

    result = asyncio.run(registry.get("senses").handler({"action": "pause"}, Ctx()))
    assert listening.snoozed and seeing.snoozed
    assert "kulak" in result.content and "göz" in result.content

    asyncio.run(registry.get("senses").handler({"action": "resume"}, Ctx()))
    assert not listening.snoozed and not seeing.snoozed


def test_senses_sight_uses_camera_power_when_present() -> None:
    """The same gate as the HUD: when the chat says 'kamerayı kapat' the device is released."""
    import asyncio

    from dornick.tools import build_registry

    registry = build_registry(subagents=False)
    called: list[bool] = []

    class Ctx:
        ear = None
        lens = None
        watcher = None

        @staticmethod
        def camera_power(on: bool) -> str:
            called.append(on)
            return "Kamera kapalı." if not on else "Kamera açık."

    result = asyncio.run(registry.get("senses").handler(
        {"action": "pause", "what": "sight"}, Ctx()))
    assert called == [False]
    assert "Kamera kapalı" in result.content
    asyncio.run(registry.get("senses").handler(
        {"action": "resume", "what": "sight"}, Ctx()))
    assert called == [False, True]


def test_the_wake_word_reopens_every_sense() -> None:
    """"I'll call when I'm back" means a single call: on hearing "dornick"
    the eye must reopen too, the user must not name sense by sense."""
    from dornick import ear

    class Sight:
        snoozed = True

        def unsnooze(self):  # noqa: ANN202
            self.snoozed = False

    seeing = Sight()
    listening = ear.Ear(_hears("dornick geldim"), lambda _h: None, wake="dornick")
    listening.companions = [seeing]
    listening.snooze()
    listening._settle([0.0])

    assert not listening.snoozed
    assert not seeing.snoozed


def test_ear_gate_toggles_without_asking_the_agent() -> None:
    """The composer microphone must be able to cut the ear without waiting for the agent tool."""
    from dornick.web.server import ear_gate

    class Fake:
        snoozed = False

        def snooze(self, seconds=0.0):  # noqa: ANN001, ANN202
            self.snoozed = True

        def unsnooze(self):  # noqa: ANN202
            self.snoozed = False

    assert ear_gate(None, "toggle") == {"ok": True, "ear": False, "snoozed": False}
    ear = Fake()
    assert ear_gate(ear, "toggle")["snoozed"] is True
    assert ear.snoozed
    assert ear_gate(ear, "toggle")["snoozed"] is False
    assert not ear.snoozed
    ear_gate(ear, "pause")
    assert ear.snoozed
    ear_gate(ear, "resume")
    assert not ear.snoozed


def test_snooze_notifies_the_ui() -> None:
    """The button and the agent tool are the same gate: the UI must see the snooze."""
    from dornick import ear as hearing

    seen: list[bool] = []
    listening = hearing.Ear(listener=None, heard=lambda _h: None)
    listening.on_snooze = seen.append
    listening.snooze()
    listening.unsnooze()
    assert seen == [True, False]

def test_slow_cpu_downshifts_the_model_after_two_hits() -> None:
    """Live complaint (30.08): on a weak laptop continuous listening was
    10-20 s behind. If the decode time clearly exceeds the audio twice in
    a row the size steps down one notch (small->base) — session only, the
    settings file is not written. A single slow decode (warm-up) does not
    downshift; the GPU never downshifts."""
    from dornick.listen import Listener, ListenConfig
    l = Listener(ListenConfig(size='small'))
    l.device = 'cpu'
    l._loaded_size = 'small'
    # 2 s audio, 8 s decode: once -> no downshift yet
    assert l._speed_verdict(2.0, 8.0) is None
    # second time -> down to base
    assert l._speed_verdict(2.0, 9.0) == 'base'
    # a fast decode resets the counter
    l._slow_hits = 1
    assert l._speed_verdict(2.0, 1.0) is None
    assert l._slow_hits == 0
    # never on the GPU
    l.device = 'cuda'
    assert l._speed_verdict(2.0, 30.0) is None
    # nothing below base (tiny deliberately excluded)
    l.device = 'cpu'
    l._loaded_size = 'base'
    l._slow_hits = 1
    assert l._speed_verdict(2.0, 9.0) is None


def test_downshift_is_session_only_and_reloads_smaller() -> None:
    from dornick.listen import Listener, ListenConfig
    cfg = ListenConfig(size='small')
    l = Listener(cfg)
    l.device = 'cpu'
    l._loaded_size = 'small'
    l._model = object()
    l._slow_hits = 1
    l._maybe_downshift(2.0, 9.0)
    assert l._force_size == 'base'
    assert l._model is None            # the next decode loads the smaller one
    assert cfg.size == 'small'         # the user's setting did not change

