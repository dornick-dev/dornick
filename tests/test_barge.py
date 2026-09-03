"""Voice barge-in behaviour.

Rule (set by the user): when a new utterance is heard during a running
turn the turn is NOT CANCELLED — it queues, just like a typed message. Only
an EXPLICIT stop word ("dur", "yeter", "kes") stops the running one. That
removes the problem "when I say one more thing while it is doing something
it cancels the old one".
"""

from __future__ import annotations

from dornick.desktop import _is_close, _is_stop, _is_ack


def test_explicit_stop_words_are_recognized() -> None:
    for word in ("dur", "durdur", "yeter", "kes", "iptal", "vazgeç", "stop", "sus"):
        assert _is_stop(word), word
    # A short compound counts as a stop too.
    assert _is_stop("yeter dur")
    assert _is_stop("dur!")


def test_a_normal_request_is_not_a_stop() -> None:
    # Sentences containing "dur" but asking for work are NOT a cancel — they must queue.
    for phrase in (
        "durumu anlat",
        "çorum durumu ne",
        "modbus cihazını oku",
        "dur artık bana rapor ver",
        "",
    ):
        assert not _is_stop(phrase), phrase


# -- closing words ---------------------------------------------------------
#
# A closing gets no reply: saying "rica ederim!" to someone who said
# "görüşürüz" would reopen the closing conversation. The window closes and
# it stays quiet.


def test_closing_words_end_the_conversation() -> None:
    for phrase in (
        "kapat", "görüşürüz", "sonra konuşuruz", "iyi geceler",
        "tamam görüşürüz", "teşekkürler kapat", "hoşça kal", "hoşça kalın",
    ):
        assert _is_close(phrase), phrase


def test_ordinary_speech_is_not_a_close() -> None:
    # "tamam" alone is NOT a closing: the answer to a question the agent
    # asked can be "tamam" too. Work sentences containing "kapat" likewise.
    for phrase in (
        "tamam",
        "teşekkürler",
        "pencereyi kapat",
        "kapat şu uygulamayı hemen lütfen",
        "görüşürüz demeden önce raporu bitir",
        "",
    ):
        assert not _is_close(phrase), phrase


def test_thanks_and_hold_on_are_acks_not_requests() -> None:
    """'teşekkürler' / 'tamamdır' / 'şimdi bakayım' do not go to the model —
    the 'rica ederim' loop. 'tamam' alone can be a yes too."""
    for phrase in (
        "teşekkürler",
        "çok teşekkürler",
        "teşekkür ederim",
        "sağol",
        "sağ ol",
        "eyvallah",
        "tamamdır",
        "tamamdır teşekkürler",
        "şimdi bakayım",
        "bir bakayım",
        "thanks",
        "thank you",
    ):
        assert _is_ack(phrase), phrase
    for phrase in (
        "tamam",
        "peki",
        "kamerayı aç",
        "teşekkürler raporu da gönder",
        "şimdi bakayım şunu da oku",
        "",
    ):
        assert not _is_ack(phrase), phrase


# -- "cut with dornick" barge-in (interrupting while dornick talks) ----------


class _FakeListener:
    """Fake recogniser whose transcribe_array returns a fixed text."""
    device = "cpu"

    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe_array(self, audio, rate=16_000) -> str:
        return self.text


def test_speaking_ignores_own_voice_without_the_wake_word() -> None:
    """Sound captured while dornick talks (deaf) is ignored if it does not
    carry the wake word — without echo cancellation dornick "does not hear"
    its own voice."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("hava bugün çok güzel"),
                heard=lambda h: heard.append(h))
    e._deaf_until = float("inf")   # TTS in progress (deaf)
    e._settle(object(), deaf=True)

    assert heard == []             # no barge


def test_open_mode_is_also_deaf_while_tts_plays() -> None:
    """Free listening removes the wake gate; still deaf during TTS."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("hava bugün çok güzel"),
                heard=lambda h: heard.append(h), open=True)
    e._deaf_until = float("inf")
    e._settle(object(), deaf=True)
    assert heard == []


def test_the_wake_word_barges_in_while_speaking() -> None:
    """When "dornick ..." is said while dornick talks: the deafness breaks,
    a Heard marked barge arrives (the bridge will first hush TTS and queue
    the command)."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("dornick raporu oku"),
                heard=lambda h: heard.append(h))
    e._deaf_until = float("inf")
    e._settle(object(), deaf=True)

    assert len(heard) == 1
    assert heard[0].wake is True
    assert heard[0].barge is True
    assert "rapor" in heard[0].command
    assert e._deaf_until == 0.0     # deafness broken


def test_energy_barge_keeps_the_sentence_without_the_wake_word() -> None:
    """Talking over the speaker keeps the sentence — without saying
    'dornick', without restarting. The energy threshold counts as having
    opened the ear (`_barge_open`)."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("kamerayı aç"),
                heard=lambda h: heard.append(h))
    e._deaf_until = float("inf")
    e._barge_open = True
    e._tts_text = "hava bugün çok güzel görünüyor"
    e._settle(object(), deaf=True)

    assert len(heard) == 1
    assert heard[0].wake is False
    assert heard[0].barge is True
    assert heard[0].command == "kamerayı aç"
    assert e._barge_open is False


def test_energy_barge_without_an_open_chat_still_hears() -> None:
    """Even if the conversation window has closed while TTS runs, the
    interrupting utterance counts as said to Dornick."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("ışıkları kapat"),
                heard=lambda h: heard.append(h))
    e._barge_open = True
    e._tts_text = "tabii hemen bakıyorum"
    e._settle(object(), deaf=True)

    assert len(heard) == 1
    assert heard[0].command == "ışıkları kapat"


def test_tts_echo_transcript_is_dropped_even_after_energy_barge() -> None:
    """When the energy threshold cuts TTS wrongly the transcript resembles
    the speaker text — its own words must not become a new request."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("hava bugün çok güzel"),
                heard=lambda h: heard.append(h))
    e._barge_open = True
    e._tts_text = "hava bugün çok güzel görünüyor"
    e._settle(object(), deaf=True)

    assert heard == []
    assert e._barge_open is False


def test_open_mode_drops_own_voice_after_the_tts_tail() -> None:
    """In free listening the room echo after the speaker went quiet passed
    the wake gate and made the agent's own sentence a new request."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("hava bugün çok güzel"),
                heard=lambda h: heard.append(h), open=True)
    e.speaking(True, "hava bugün çok güzel görünüyor")
    e.speaking(False)
    e._deaf_until = 0.0
    e._settle(object(), deaf=False)

    assert heard == []


def test_open_mode_still_hears_a_new_request_after_tts() -> None:
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("kamerayı aç"),
                heard=lambda h: heard.append(h), open=True)
    e.speaking(True, "hava bugün çok güzel görünüyor")
    e.speaking(False)
    e._deaf_until = 0.0
    e._settle(object(), deaf=False)

    assert len(heard) == 1
    assert heard[0].command == "kamerayı aç"


def test_energy_barge_waits_until_echo_is_primed() -> None:
    """The first TTS block exceeded BARGE_FLOOR on an empty baseline and
    took its own voice for a barge-in."""
    from dornick import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    assert not e._barge_loud(0.08)
    e._echo.extend([0.030] * (ear.ECHO_PRIME - 1))
    assert not e._barge_loud(0.08)
    e._echo.append(0.030)
    assert e._barge_loud(0.08)


def test_consecutive_tts_sentences_keep_the_echo_baseline() -> None:
    from dornick import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e.speaking(True, "birinci cümle")
    e._echo.extend([0.03] * ear.ECHO_PRIME)
    e.speaking(True, "ikinci cümle")
    assert len(e._echo) == ear.ECHO_PRIME
    assert "birinci" in e._tts_text and "ikinci" in e._tts_text


def test_echo_of_self_matches_overlap_not_unrelated_speech() -> None:
    from dornick import ear

    assert ear.echo_of_self("hava bugün güzel", "hava bugün çok güzel görünüyor")
    assert not ear.echo_of_self("kamerayı aç", "hava bugün çok güzel")
    assert not ear.echo_of_self("ok", "merhaba")


def test_whisper_shortens_and_inflects_tts_and_that_is_still_echo() -> None:
    """Live: 'Evet, seni görüyorum…' on the speaker, Whisper writes 'evet,
    seni gör' / 'görürüm' — the whole sentence does not match, still echo."""
    from dornick import ear

    tts = "Evet, seni görüyorum. Kameraya bakıyorsun; gözlük ve sakalın kadrajda."
    assert ear.echo_of_self("evet, seni gör.", tts)
    assert ear.echo_of_self("evet, seni görürüm.", tts)
    assert not ear.echo_of_self("kamerayı kapat", tts)


def test_a_repeated_utterance_is_one_prompt() -> None:
    """When a low voice is missed the user says it 2–3 times; when Whisper
    lagged the same sentence landed in the chat twice."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("kamerayı aç"),
                heard=lambda h: heard.append(h), open=True)
    e._settle(object())
    e._settle(object())
    assert len(heard) == 1
    assert heard[0].command == "kamerayı aç"


def test_a_new_request_after_the_repeat_window_still_lands() -> None:
    import time
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("kamerayı aç"),
                heard=lambda h: heard.append(h), open=True)
    e._settle(object())
    e._last_ask_at = time.monotonic() - ear.DUP_S - 0.1
    e._settle(object())
    assert len(heard) == 2


def test_a_late_transcript_yields_to_a_newer_utterance() -> None:
    """If recognition takes 1–2 min the user says 'dornick'; the old
    sentence and the name must not land at once — the last word wins."""
    import time
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("günaydın elimde ne tutuyorum"),
                heard=lambda h: heard.append(h), open=True)
    old = time.monotonic() - 90
    e._latest_at = time.monotonic()
    e._settle(object(), captured=old)
    assert heard == []


def test_echo_stamp_at_capture_survives_slow_asr() -> None:
    """Even if ECHO_HOLD has expired by the time Whisper finishes, the stamped segment drops."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("evet, seni gör."),
                heard=lambda h: heard.append(h), open=True)
    e._tts_text = "Evet, seni görüyorum. Kameraya bakıyorsun"
    e._tts_until = 0.0
    e._settle(object(), deaf=False, echo=True)
    assert heard == []


def test_speaking_false_skips_the_echo_tail_during_barge() -> None:
    """After a hush, DEAF_TAIL would leave the rest of the sentence deaf again."""
    from dornick import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e.speaking(True, "merhaba nasılsın")
    assert e.deaf
    e._barge_open = True
    e.speaking(False)
    assert not e.deaf
    assert e._deaf_until == 0.0


def test_speaking_false_keeps_the_echo_tail_without_barge() -> None:
    from dornick import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e.speaking(True, "merhaba")
    e.speaking(False)
    assert e.deaf


def test_trip_barge_hushes_immediately() -> None:
    from dornick import ear

    calls: list[int] = []
    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e.on_hush = lambda: calls.append(1)
    e.speaking(True, "selam")
    e._trip_barge()

    assert calls == [1]
    assert e._barge_open is True
    assert not e.deaf


def test_barge_loud_sits_above_the_echo_floor() -> None:
    from dornick import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e._echo.extend([0.035] * 12)
    assert not e._barge_loud(0.040)
    assert e._barge_loud(0.080)


def test_desktop_hushes_as_soon_as_energy_trips() -> None:
    import inspect

    from dornick import desktop

    source = inspect.getsource(desktop._open_ear)
    assert "on_hush" in source
    assert '{"type": "hush"}' in source


def test_tts_onset_on_a_quiet_floor_is_not_barge() -> None:
    """While the speaker is not yet heard the room floor is ~0.01, TTS
    0.08 — it was cutting its own voice."""
    from dornick import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e._echo.extend([0.006] * ear.ECHO_PRIME)
    assert not e._barge_loud(0.08)


def test_whisper_goodbye_after_tts_is_echo_not_a_request() -> None:
    """Live: after merhaba the speaker went quiet, Whisper printed 'hoşça
    kalın', the agent said goodbye — nobody had said goodbye."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("hoşça kalın."),
                 heard=lambda h: heard.append(h), open=True)
    e.speaking(True, "Merhaba Fatih. Ben Dornick.")
    e.speaking(False)
    e._deaf_until = 0.0
    e._settle(object(), deaf=False, echo=True)
    assert heard == []


def test_a_garbled_tts_fragment_is_not_a_barge_request() -> None:
    """When the energy threshold cut TTS, Whisper wrote 'soni' — barged in."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("soni"),
                heard=lambda h: heard.append(h))
    e._barge_open = True
    e._tts_text = "Merhaba Fatih. Ben Dornick; kod, SCADA işleri"
    e._settle(object(), deaf=True)

    assert heard == []
    assert e._barge_open is False


def test_a_real_yes_during_echo_still_lands() -> None:
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("evet"),
                heard=lambda h: heard.append(h), open=True)
    e.speaking(True, "kamerayı açmamı ister misin")
    e.speaking(False)
    e._deaf_until = 0.0
    e._settle(object(), deaf=False, echo=True)
    assert len(heard) == 1
    assert heard[0].command == "evet"


def test_garbled_how_are_you_after_tts_is_echo() -> None:
    """Live: the speaker said 'Sen nasılsın; bugün nasıl gidiyor?', Whisper
    wrote 'sende sos' — two words, one kin, the rest junk."""
    from dornick import ear

    tts = "İyiyim, buradayım. Sen nasılsın; bugün nasıl gidiyor?"
    assert ear.echo_of_self("sende sos", tts)
    heard = []
    e = ear.Ear(listener=_FakeListener("sende sos"),
                heard=lambda h: heard.append(h), open=True)
    e.speaking(True, tts)
    e.speaking(False)
    e._deaf_until = 0.0
    e._settle(object(), deaf=False, echo=True)
    assert heard == []


def test_a_real_reply_is_not_echo_junk_just_because_it_is_one_word() -> None:
    """In the echo window 'anladım' dropped for being one word — it did not hear."""
    from dornick import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("anladım"),
                heard=lambda h: heard.append(h), open=True)
    e.speaking(True, "kamerayı açmamı ister misin")
    e.speaking(False)
    e._deaf_until = 0.0
    e._settle(object(), deaf=False, echo=True)
    assert len(heard) == 1
    assert heard[0].command == "anladım"


def test_ok_is_not_echo_of_unrelated_tts() -> None:
    from dornick import ear

    assert not ear.echo_of_self("ok", "merhaba")


def test_tail_loud_ignores_decaying_speaker_but_hears_the_mic() -> None:
    from dornick import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e._echo.extend([0.035] * ear.ECHO_PRIME)
    assert not e._tail_loud(0.012)
    assert e._tail_loud(0.060)
