"""Sesli araya girme (barge-in) davranışı.

Kural (kullanıcı koydu): süren bir turda yeni bir söz duyulunca tur İPTAL
EDİLMEZ — sıraya girer, tıpkı yazılan mesaj gibi. Yalnızca AÇIK bir durdurma
sözü ("dur", "yeter", "kes") süreni durdurur. Böylece "bir işlem yaparken bir
şey daha söyleyince eskiyi iptal ediyor" sorunu ortadan kalkıyor.
"""

from __future__ import annotations

from neocp.desktop import _is_close, _is_stop, _is_ack


def test_explicit_stop_words_are_recognized() -> None:
    for word in ("dur", "durdur", "yeter", "kes", "iptal", "vazgeç", "stop", "sus"):
        assert _is_stop(word), word
    # Kısa birleşik de durdurma sayılıyor.
    assert _is_stop("yeter dur")
    assert _is_stop("dur!")


def test_a_normal_request_is_not_a_stop() -> None:
    # İçinde "dur" geçen ama iş isteyen cümleler iptal DEĞİL — sıraya girmeli.
    for phrase in (
        "durumu anlat",
        "çorum durumu ne",
        "modbus cihazını oku",
        "dur artık bana rapor ver",
        "",
    ):
        assert not _is_stop(phrase), phrase


# -- kapatma sözleri -------------------------------------------------------
#
# Kapanış cevap almaz: "görüşürüz" diyene "rica ederim!" demek kapanan
# konuşmayı yeniden açmak olurdu. Pencere kapanır ve susulur.


def test_closing_words_end_the_conversation() -> None:
    for phrase in (
        "kapat", "görüşürüz", "sonra konuşuruz", "iyi geceler",
        "tamam görüşürüz", "teşekkürler kapat", "hoşça kal",
    ):
        assert _is_close(phrase), phrase


def test_ordinary_speech_is_not_a_close() -> None:
    # "tamam" tek başına kapanış DEĞİL: ajanın sorduğu bir sorunun cevabı
    # da "tamam" olabiliyor. "kapat" geçen iş cümleleri de öyle.
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
    """'teşekkürler' / 'tamamdır' / 'şimdi bakayım' modele gitmez —
    'rica ederim' döngüsü. 'tamam' tek başına evet de olabilir."""
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


# -- "neo ile kes" barge-in (neo konuşurken araya girme) -------------------


class _FakeListener:
    """transcribe_array'i sabit bir metin döndüren sahte tanıyıcı."""
    device = "cpu"

    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe_array(self, audio, rate=16_000) -> str:
        return self.text


def test_speaking_ignores_own_voice_without_the_wake_word() -> None:
    """neo konuşurken (deaf) yakalanan ses uyandırma sözü taşımıyorsa yok
    sayılıyor — echo iptali olmadan neo'nun kendi sesini "duymuyor"."""
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("hava bugün çok güzel"),
                heard=lambda h: heard.append(h))
    e._deaf_until = float("inf")   # TTS sürüyor (sağır)
    e._settle(object(), deaf=True)

    assert heard == []             # barge yok


def test_open_mode_is_also_deaf_while_tts_plays() -> None:
    """Serbest dinleme uyandırma kapısını kaldırır; TTS sırasında hâlâ sağır."""
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("hava bugün çok güzel"),
                heard=lambda h: heard.append(h), open=True)
    e._deaf_until = float("inf")
    e._settle(object(), deaf=True)
    assert heard == []


def test_the_wake_word_barges_in_while_speaking() -> None:
    """neo konuşurken "neo ..." denince: sağırlık kırılıyor, barge işaretli
    bir Heard geliyor (köprü önce TTS'i susturup komutu sıraya koyacak)."""
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("neo raporu oku"),
                heard=lambda h: heard.append(h))
    e._deaf_until = float("inf")
    e._settle(object(), deaf=True)

    assert len(heard) == 1
    assert heard[0].wake is True
    assert heard[0].barge is True
    assert "rapor" in heard[0].command
    assert e._deaf_until == 0.0     # sağırlık kırıldı


def test_energy_barge_keeps_the_sentence_without_the_wake_word() -> None:
    """Hoparlörün üstünden konuşunca cümle tutulur — 'neo' demeden,
    baştan kurmadan. Enerji eşiği kulağı açmış sayılır (`_barge_open`)."""
    from neocp import ear

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
    """TTS sürerken sohbet penceresi kapanmış olsa da araya giren söz
    Neo'ya söylenmiş sayılır."""
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("ışıkları kapat"),
                heard=lambda h: heard.append(h))
    e._barge_open = True
    e._tts_text = "tabii hemen bakıyorum"
    e._settle(object(), deaf=True)

    assert len(heard) == 1
    assert heard[0].command == "ışıkları kapat"


def test_tts_echo_transcript_is_dropped_even_after_energy_barge() -> None:
    """Enerji eşiği TTS'i yanlış kestiğinde tanıma hoparlör metnine
    benzer — kendi sözü yeni istek olmasın."""
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("hava bugün çok güzel"),
                heard=lambda h: heard.append(h))
    e._barge_open = True
    e._tts_text = "hava bugün çok güzel görünüyor"
    e._settle(object(), deaf=True)

    assert heard == []
    assert e._barge_open is False


def test_open_mode_drops_own_voice_after_the_tts_tail() -> None:
    """Serbest dinlemede hoparlör sustuktan sonra oda yankısı uyandırma
    kapısından geçip ajanın kendi cümlesini yeni istek yapıyordu."""
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("hava bugün çok güzel"),
                heard=lambda h: heard.append(h), open=True)
    e.speaking(True, "hava bugün çok güzel görünüyor")
    e.speaking(False)
    e._deaf_until = 0.0
    e._settle(object(), deaf=False)

    assert heard == []


def test_open_mode_still_hears_a_new_request_after_tts() -> None:
    from neocp import ear

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
    """TTS'in ilk bloğu boş tabanda BARGE_FLOOR'u aşıp kendi sesini
    araya girme sanıyordu."""
    from neocp import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    assert not e._barge_loud(0.08)
    e._echo.extend([0.030] * (ear.ECHO_PRIME - 1))
    assert not e._barge_loud(0.08)
    e._echo.append(0.030)
    assert e._barge_loud(0.08)


def test_consecutive_tts_sentences_keep_the_echo_baseline() -> None:
    from neocp import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e.speaking(True, "birinci cümle")
    e._echo.extend([0.03] * ear.ECHO_PRIME)
    e.speaking(True, "ikinci cümle")
    assert len(e._echo) == ear.ECHO_PRIME
    assert "birinci" in e._tts_text and "ikinci" in e._tts_text


def test_echo_of_self_matches_overlap_not_unrelated_speech() -> None:
    from neocp import ear

    assert ear.echo_of_self("hava bugün güzel", "hava bugün çok güzel görünüyor")
    assert not ear.echo_of_self("kamerayı aç", "hava bugün çok güzel")
    assert not ear.echo_of_self("ok", "merhaba")


def test_whisper_shortens_and_inflects_tts_and_that_is_still_echo() -> None:
    """Canlı: 'Evet, seni görüyorum…' hoparlörde, Whisper 'evet, seni gör'
    / 'görürüm' yazıyor — tam cümle eşleşmez, yine yankı."""
    from neocp import ear

    tts = "Evet, seni görüyorum. Kameraya bakıyorsun; gözlük ve sakalın kadrajda."
    assert ear.echo_of_self("evet, seni gör.", tts)
    assert ear.echo_of_self("evet, seni görürüm.", tts)
    assert not ear.echo_of_self("kamerayı kapat", tts)


def test_a_repeated_utterance_is_one_prompt() -> None:
    """Kısık ses kaçınca kullanıcı 2–3 kez söylüyor; Whisper gecikince
    aynı cümle iki kez sohbete düşüyordu."""
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("kamerayı aç"),
                heard=lambda h: heard.append(h), open=True)
    e._settle(object())
    e._settle(object())
    assert len(heard) == 1
    assert heard[0].command == "kamerayı aç"


def test_a_new_request_after_the_repeat_window_still_lands() -> None:
    import time
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("kamerayı aç"),
                heard=lambda h: heard.append(h), open=True)
    e._settle(object())
    e._last_ask_at = time.monotonic() - ear.DUP_S - 0.1
    e._settle(object())
    assert len(heard) == 2


def test_a_late_transcript_yields_to_a_newer_utterance() -> None:
    """Tanıma 1–2 dk sürerse kullanıcı 'neo' der; eski cümle ile ad
    aynı anda düşmesin — son söz kazanır."""
    import time
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("günaydın elimde ne tutuyorum"),
                heard=lambda h: heard.append(h), open=True)
    old = time.monotonic() - 90
    e._latest_at = time.monotonic()
    e._settle(object(), captured=old)
    assert heard == []


def test_echo_stamp_at_capture_survives_slow_asr() -> None:
    """Whisper bitene kadar ECHO_HOLD dolmuş olsa da damgalı segment düşer."""
    from neocp import ear

    heard = []
    e = ear.Ear(listener=_FakeListener("evet, seni gör."),
                heard=lambda h: heard.append(h), open=True)
    e._tts_text = "Evet, seni görüyorum. Kameraya bakıyorsun"
    e._tts_until = 0.0
    e._settle(object(), deaf=False, echo=True)
    assert heard == []


def test_speaking_false_skips_the_echo_tail_during_barge() -> None:
    """Hush sonrası DEAF_TAIL cümlenin devamını yine sağır bırakırdı."""
    from neocp import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e.speaking(True, "merhaba nasılsın")
    assert e.deaf
    e._barge_open = True
    e.speaking(False)
    assert not e.deaf
    assert e._deaf_until == 0.0


def test_speaking_false_keeps_the_echo_tail_without_barge() -> None:
    from neocp import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e.speaking(True, "merhaba")
    e.speaking(False)
    assert e.deaf


def test_trip_barge_hushes_immediately() -> None:
    from neocp import ear

    calls: list[int] = []
    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e.on_hush = lambda: calls.append(1)
    e.speaking(True, "selam")
    e._trip_barge()

    assert calls == [1]
    assert e._barge_open is True
    assert not e.deaf


def test_barge_loud_sits_above_the_echo_floor() -> None:
    from neocp import ear

    e = ear.Ear(listener=_FakeListener(""), heard=lambda _h: None)
    e._echo.extend([0.010] * 12)
    assert not e._barge_loud(0.020)
    assert e._barge_loud(0.040)


def test_desktop_hushes_as_soon_as_energy_trips() -> None:
    import inspect

    from neocp import desktop

    source = inspect.getsource(desktop._open_ear)
    assert "on_hush" in source
    assert '{"type": "hush"}' in source
