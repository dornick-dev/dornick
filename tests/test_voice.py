"""Sesli konuşma.

Ses üretimi ağa çıkıyor, o yüzden burada test edilen şey ağ değil: **neyin
sesletileceği**. Kod bloğunu sesli okumak ("üç ters tırnak powershell dolar
u r l eşittir…") bir asistanı anında dayanılmaz yapıyor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from neocp import voice
from neocp.config import Config


def test_code_blocks_are_not_read_aloud() -> None:
    text = """Betiği yazdım:

```powershell
$url = "https://api.coingecko.com/api/v3/markets"
Invoke-RestMethod -Uri $url
```

Çalıştırabilirsin."""
    said = voice.speakable(text)

    assert "Betiği yazdım" in said
    assert "Çalıştırabilirsin" in said
    assert "powershell" not in said
    assert "Invoke-RestMethod" not in said


def test_inline_code_is_dropped_too() -> None:
    said = voice.speakable("Dosyayı `borsa/cek.ps1` içine yazdım.")

    assert "Dosyayı" in said
    assert "cek.ps1" not in said


def test_tables_are_skipped() -> None:
    """Tabloyu sesli okumak sütun sütun anlamsız bir liste üretiyor."""
    said = voice.speakable("Sonuç:\n\n| Borsa | Hacim |\n|---|---|\n| Binance | 412880 |\n\nBitti.")

    assert "Sonuç" in said and "Bitti" in said
    assert "Binance" not in said


def test_a_link_is_read_by_its_text_not_its_address() -> None:
    said = voice.speakable("Ayrıntı [CoinGecko belgelerinde](https://docs.coingecko.com/x).")

    assert "CoinGecko belgelerinde" in said
    assert "https" not in said


def test_bare_addresses_and_paths_are_dropped() -> None:
    said = voice.speakable("Kaynak https://ornek.com/a/b ve C:/proje/src/main.py içinde.")

    assert "ornek.com" not in said
    assert "main.py" not in said
    assert "Kaynak" in said


def test_markdown_marks_do_not_get_spelled_out() -> None:
    said = voice.speakable("## Başlık\n\n**kalın** ve *eğik* ve ~~üstü çizili~~")

    assert "#" not in said and "*" not in said and "~" not in said
    assert "Başlık" in said and "kalın" in said


def test_a_message_that_is_only_code_says_nothing() -> None:
    """Sesletilecek bir şey kalmadıysa sessiz kalmalı; "kod bloğu" diye
    seslendirmek her cevapta tekrarlanan bir gürültü olurdu."""
    assert voice.speakable("```py\nprint(1)\n```") == ""


def test_long_answers_are_clipped() -> None:
    assert len(voice.speakable("cümle. " * 5_000)) <= voice.MAX_CHARS


def test_empty_input_is_safe() -> None:
    assert voice.speakable("") == ""
    assert voice.speakable(None) == ""  # type: ignore[arg-type]


# -- ayarlar -----------------------------------------------------------


def test_voice_is_off_until_asked_for(tmp_path: Path) -> None:
    """Kendiliğinden konuşmaya başlayan bir program rahatsız edici."""
    assert not Config.load(tmp_path).voice.enabled


def test_senses_open_turned_off(tmp_path: Path) -> None:
    """Açılışta kamera / mikrofon / ses kapalı — kayıtta açık kalsalar bile."""
    from dataclasses import replace
    from neocp.desktop import duyulari_kapat

    config = Config.load(tmp_path)
    config = replace(
        config,
        voice=replace(config.voice, enabled=True),
        listen=replace(config.listen, enabled=True, open=True),
        camera=replace(config.camera, enabled=True),
    )
    kapali = duyulari_kapat(config)
    assert not kapali.voice.enabled
    assert not kapali.listen.enabled
    assert not kapali.listen.open
    assert not kapali.camera.enabled


def test_boot_closes_senses_before_hardware() -> None:
    """Donanım açılmadan duyular kapatılır; izleyici kamera anahtarına bağlı."""
    import inspect
    from neocp import desktop

    src = inspect.getsource(desktop._boot)
    assert "duyulari_kapat" in src
    assert src.index("duyulari_kapat") < src.index("sync_hearing")
    assert src.index("duyulari_kapat") < src.index("Lens")
    assert "config.camera.enabled and eyes.start()" in src


def test_voice_settings_survive_a_restart(tmp_path: Path) -> None:
    from neocp import settings

    config = Config.load(tmp_path)
    config.ensure_dirs()
    settings.apply(config, {"voice": {"enabled": True, "name": "tr-TR-AhmetNeural",
                                      "rate": "+12%"}})

    reloaded = Config.load(tmp_path).voice
    assert reloaded.enabled and reloaded.name == "tr-TR-AhmetNeural"
    assert reloaded.rate == "+12%"


def test_the_settings_page_knows_whether_the_package_is_installed(tmp_path: Path) -> None:
    """Kurulu değilken ses ayarlarını göstermek, çalışmayan bir düğme
    göstermek demek."""
    from neocp import settings

    config = Config.load(tmp_path)
    config.ensure_dirs()
    assert settings.snapshot(config)["voice"]["available"] == voice.available()


@pytest.mark.skipif(not voice.available(), reason="ses paketi kurulu değil")
async def test_real_speech_comes_back_as_audio() -> None:
    """Ağa çıkıyor; ağ yoksa atlanıyor."""
    import asyncio

    try:
        audio = await asyncio.wait_for(
            voice.synthesize("Merhaba, bugün ne yapıyoruz?", voice.VoiceConfig()), timeout=20
        )
    except (asyncio.TimeoutError, Exception):
        pytest.skip("ses sunucusuna ulaşılamadı")

    # mp3 çerçevesi ya ID3 ile ya da senkron baytıyla başlar.
    assert len(audio) > 1000
    assert audio[:3] == b"ID3" or audio[0] == 0xFF


# -- tonlama -----------------------------------------------------------


def test_a_question_lifts_the_voice() -> None:
    """Türkçe seslerde SSML duygu stili yok (hepsi "General"), ama hız ve
    perde cümle cümle ayarlanabiliyor. Düz okumanın sebebi tek bir ayarın
    bütün cevaba uygulanmasıydı."""
    rate, pitch = voice.tone_of("Buyur, ne var?")
    assert pitch.startswith("+")


def test_an_exclamation_speeds_up() -> None:
    rate, _pitch = voice.tone_of("Harika!")
    assert int(rate.rstrip("%")) > 0


def test_an_ellipsis_slows_down() -> None:
    rate, pitch = voice.tone_of("Şöyle bir bakayım…")
    assert int(rate.rstrip("%")) < 0
    assert int(pitch.rstrip("Hz")) < 0


def test_a_long_sentence_takes_its_time() -> None:
    long = "Bu uzun bir açıklama cümlesi ve içinde epeyce ayrıntı var, " * 2
    rate, _pitch = voice.tone_of(long)
    assert int(rate.rstrip("%")) < 0


def test_a_plain_sentence_is_left_alone() -> None:
    assert voice.tone_of("Orta uzunlukta normal bir cümle burada duruyor.") == ("+0%", "+0Hz")


def test_the_users_setting_is_not_replaced() -> None:
    """Ayardaki hız kişisel bir tercih; tonlama onun üstüne biniyor."""
    assert voice._blend("+10%", "+8%", "%") == "+18%"
    assert voice._blend("-5Hz", "+6Hz", "Hz") == "+1Hz"


def test_a_broken_setting_does_not_crash() -> None:
    assert voice._blend("hızlı", "+8%", "%") == "hızlı"


# -- karakter ----------------------------------------------------------
#
# Sentezleyici gerçek bir insan sesi üretiyor ve tek başına düz duruyor:
# metin okuyan biri gibi, konuşan bir şey gibi değil. Türkçe seslerde
# SSML duygu stili de yok (hepsi "General"). Karakter sesin üstüne
# tarayıcıda biniyor; ayarı burada.


def test_the_voice_is_neither_a_recording_nor_a_person(tmp_path: Path) -> None:
    """Varsayılan iki ucun arasında: ne santral kaydı ne insan taklidi."""
    character = Config.load(tmp_path).voice.character
    assert 0 < character < 1


def test_the_character_survives_a_restart(tmp_path: Path) -> None:
    from neocp import settings

    config = Config.load(tmp_path)
    config.ensure_dirs()
    settings.apply(config, {"voice": {"character": 0.7}})

    assert Config.load(tmp_path).voice.character == 0.7


def test_a_problem_is_not_said_like_good_news() -> None:
    """Noktalama tek başına yetmiyor: "Bir sorun var." ile "Tamam, oldu."
    aynı noktayla bitiyor ve düz okunduğunda ikisi de aynı çıkıyordu."""
    bad_rate, bad_pitch = voice.tone_of("Bir sorun var, PLC cevap vermiyor.")
    good_rate, good_pitch = voice.tone_of("Tamam, oldu.")

    assert int(bad_pitch.rstrip("Hz")) < 0 < int(good_pitch.rstrip("Hz"))
    assert int(bad_rate.rstrip("%")) < int(good_rate.rstrip("%"))


def test_uncertainty_slows_down_without_dropping() -> None:
    """Emin olmamak ile kötü haber aynı şey değil: biri yavaşlar ama
    perdesi düşmez, diğeri ikisini birden yapar."""
    rate, pitch = voice.tone_of("Sanırım o adres yanlış.")
    assert int(rate.rstrip("%")) < 0
    assert int(pitch.rstrip("Hz")) >= 0


def test_the_cue_words_do_not_override_a_question() -> None:
    """Soru cümlesi her şeyden önce soru: içinde "sorun" geçse bile
    sonunda ses yükselmeli."""
    _rate, pitch = voice.tone_of("Bir sorun mu var?")
    assert pitch.startswith("+")
