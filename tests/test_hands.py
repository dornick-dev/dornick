"""El ve ekran: koordinat çevirisi ve tuş ayrıştırma.

Buradaki iki saf fonksiyon işin doğruluk çekirdeği. `to_screen` yanlışsa
her tıklama hedefin yanına düşer; `parse_keys` yanlışsa kısayol tutmaz.
İkisi de platformdan bağımsız test edilebiliyor — asıl user32 çağrıları
Windows'a bağlı ve orada elle doğrulanıyor.
"""

from __future__ import annotations

import pytest

from neocp.tools import hands


def test_to_screen_maps_image_pixel_to_real_coordinate() -> None:
    # Görüntü yarı ölçekli ve ekran (100, 50)'den başlıyor: ikinci ekran
    # gibi kaydırılmış bir masaüstünde tıklamanın doğru yere düşmesi şart.
    frame = {"origin": (100, 50), "scale": 0.5, "size": (700, 400)}
    assert hands.to_screen(0, 0, frame) == (100, 50)
    assert hands.to_screen(200, 100, frame) == (500, 250)


def test_to_screen_is_identity_at_full_scale_and_origin() -> None:
    frame = {"origin": (0, 0), "scale": 1.0, "size": (1920, 1080)}
    assert hands.to_screen(960, 540, frame) == (960, 540)


def test_parse_keys_reads_a_modifier_combo() -> None:
    keys = hands.parse_keys("ctrl+c")
    assert keys[0] == hands.VK["ctrl"]
    assert len(keys) == 2


def test_parse_keys_named_keys() -> None:
    assert hands.parse_keys("enter") == [hands.VK["enter"]]
    assert hands.parse_keys("alt+tab") == [hands.VK["alt"], hands.VK["tab"]]
    assert hands.parse_keys("f5") == [hands.VK["f5"]]


def test_parse_keys_rejects_unknown_token() -> None:
    with pytest.raises(ValueError):
        hands.parse_keys("ctrl+nope")


def test_utf16_units_handles_astral_and_turkish() -> None:
    # Türkçe karakter tek birim; emoji (astral düzlem) iki birim (surrogate
    # çifti). İkisi de eksiksiz gitmeli, yoksa yazılan metin bozulur.
    assert len(hands._utf16_units("ş")) == 1
    assert len(hands._utf16_units("😀")) == 2
