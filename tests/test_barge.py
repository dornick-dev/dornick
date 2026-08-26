"""Sesli araya girme (barge-in) davranışı.

Kural (kullanıcı koydu): süren bir turda yeni bir söz duyulunca tur İPTAL
EDİLMEZ — sıraya girer, tıpkı yazılan mesaj gibi. Yalnızca AÇIK bir durdurma
sözü ("dur", "yeter", "kes") süreni durdurur. Böylece "bir işlem yaparken bir
şey daha söyleyince eskiyi iptal ediyor" sorunu ortadan kalkıyor.
"""

from __future__ import annotations

from neocp.desktop import _is_close, _is_stop


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
