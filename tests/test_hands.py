"""Hand and screen: coordinate conversion and key parsing.

The two pure functions here are the correctness core of the job. If
`to_screen` is wrong, every click lands next to the target; if
`parse_keys` is wrong, the shortcut does not take. Both are testable
independent of platform — the actual user32 calls are Windows-bound and
verified there by hand.
"""

from __future__ import annotations

import pytest

from dornick.tools import hands


def test_to_screen_maps_image_pixel_to_real_coordinate() -> None:
    # The image is half-scale and the screen starts at (100, 50): on a
    # shifted desktop (like a second monitor) the click must land right.
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
    # A Turkish character is one unit; an emoji (astral plane) is two (a
    # surrogate pair). Both must go complete, or the typed text corrupts.
    assert len(hands._utf16_units("ş")) == 1
    assert len(hands._utf16_units("😀")) == 2
