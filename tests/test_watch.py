"""Camera watching.

The naive route would be asking the model about every frame, and that
route does not work: twenty frames a second, 1.5–4.8k tokens each. The
tests here hold **when the model wakes** — a wrong threshold means either
dozens of requests a minute in an empty room, or a camera that never wakes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dornick import watch

pytestmark = pytest.mark.skipif(not watch.available(), reason="image package not installed")


def frames(*shades: int):
    """Flat-coloured frames. No real image is needed for the difference computation."""
    import numpy as np

    return [np.full((120, 160, 3), shade, dtype=np.uint8) for shade in shades]


class FakeCapture:
    """Fake camera returning the given frames in order."""

    def __init__(self, images: list) -> None:
        self.images = list(images)
        self.released = False

    def isOpened(self) -> bool:  # noqa: N802 - OpenCV interface
        return True

    def read(self):
        if not self.images:
            return False, None
        return True, self.images.pop(0)

    def release(self) -> None:
        self.released = True


def eye(monkeypatch: pytest.MonkeyPatch, images: list, **changes) -> watch.Eye:
    import cv2

    camera = watch.Camera(id="c1", name="deneme", **changes)
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_a: FakeCapture(images))
    return watch.Eye(camera=camera)


def look_all(watcher: watch.Eye, count: int) -> list:
    return [seen for _ in range(count) if (seen := watcher.look()) is not None]


# -- motion threshold --------------------------------------------------


def test_a_still_scene_never_wakes_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """In an empty room no request should go out for hours."""
    still = frames(*([40] * 20))
    assert look_all(eye(monkeypatch, still), 20) == []


def test_a_real_change_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    # Warm-up frames, then a clear change.
    images = frames(*([40] * watch.WARMUP), 40, 200)
    seen = look_all(eye(monkeypatch, images), len(images))

    assert len(seen) == 1
    assert seen[0].change > 0.5
    assert seen[0].frame.startswith("data:image/jpeg;base64,")


def test_the_warmup_frames_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """After the camera opens, while the exposure settles every frame looks
    like "motion"; if the first frames are not skipped every opening is a
    false alarm."""
    images = frames(10, 90, 170, 250, 30, 30, 30)
    seen = look_all(eye(monkeypatch, images), len(images))

    assert seen == []


def test_a_tiny_flicker_does_not_wake_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shadow, noise and compression flicker are not motion."""
    images = frames(*([40] * watch.WARMUP), 40, 42)
    assert look_all(eye(monkeypatch, images), len(images)) == []


def test_sensitivity_can_be_lowered(monkeypatch: pytest.MonkeyPatch) -> None:
    images = frames(*([40] * watch.WARMUP), 40, 42)
    assert look_all(eye(monkeypatch, images, sensitivity=0.001), len(images))


# -- quiet margin ------------------------------------------------------


def test_continuing_motion_asks_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A door left open must not report every second."""
    images = frames(*([40] * watch.WARMUP), 40, 200, 40, 200, 40, 200)
    seen = look_all(eye(monkeypatch, images, cooldown_s=600), len(images))

    assert len(seen) == 1


def test_a_short_cooldown_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero quiet time on a frame with continuing motion means dozens of
    requests a second; the floor value protects."""
    images = frames(*([40] * watch.WARMUP), 40, 200, 40, 200)
    seen = look_all(eye(monkeypatch, images, cooldown_s=0), len(images))

    assert len(seen) == 1


# -- resilience --------------------------------------------------------


def test_a_dropped_stream_closes_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """A network camera can drop; it must reopen on the next round."""
    watcher = eye(monkeypatch, frames(40))
    watcher.look()
    watcher.look()          # no frames left → drop

    assert watcher._capture is None


def test_one_broken_camera_does_not_stop_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    import cv2

    class Boom(FakeCapture):
        def read(self):
            raise RuntimeError("sürücü çöktü")

    monkeypatch.setattr(cv2, "VideoCapture", lambda *_a: Boom([]))
    reported: list = []
    watcher = watch.Watcher([watch.Camera(id="c1", name="bozuk", source="1")], reported.append)

    # One round of the loop: the error must be swallowed, the call must return.
    watcher._eyes["c1"].camera.every_s = 0.01
    watcher._stop.set()
    watcher._loop()

    assert reported == []


# -- records -----------------------------------------------------------


def test_cameras_survive_a_restart(tmp_path: Path) -> None:
    watch.save(tmp_path, [watch.Camera(id="c1", name="giriş", source="rtsp://x/1")])
    again = watch.load(tmp_path)

    assert [c.name for c in again] == ["giriş"]
    assert again[0].source == "rtsp://x/1"


def test_a_hand_edited_file_does_not_break_startup(tmp_path: Path) -> None:
    (tmp_path / "cameras.json").write_text(
        '[{"id": "c1", "name": "x", "uydurma": 1}, "cop", {}]', encoding="utf-8"
    )
    assert [c.id for c in watch.load(tmp_path)] == ["c1"]


def test_a_corrupt_file_is_survived(tmp_path: Path) -> None:
    (tmp_path / "cameras.json").write_text("bu json degil", encoding="utf-8")
    assert watch.load(tmp_path) == []


def test_a_disabled_camera_is_not_watched() -> None:
    watcher = watch.Watcher(
        [watch.Camera(id="c1", name="a", source="1"),
         watch.Camera(id="c2", name="b", source="2", enabled=False)],
        lambda _s: None,
    )
    assert list(watcher._eyes) == ["c1"]


def test_the_builtin_webcam_is_not_watched() -> None:
    """The built-in camera is the Lens's job; a second OpenCV was pushing motion into the chat."""
    watcher = watch.Watcher(
        [watch.Camera(id="usb", name="Bilgisayar kamerası", source="0")],
        lambda _s: None,
    )
    assert watcher._eyes == {}
    assert not watcher.start()


def test_watcher_can_start_again_after_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Closing and reopening the HUD must restart the watcher; the stop Event stayed set."""
    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", lambda *_a: FakeCapture(frames(40, 40, 40)))
    watcher = watch.Watcher(
        [watch.Camera(id="c1", name="a", source="1", every_s=0.05)],
        lambda _s: None,
    )
    assert watcher.start()
    watcher.stop()
    assert watcher._eyes == {}
    assert watcher.start()
    assert watcher._thread is not None and watcher._thread.is_alive()
    watcher.stop()
    assert watcher._eyes == {}


def test_the_default_question_says_what_matters() -> None:
    """The model must not say "there are some things"; it must single out what needs attention."""
    assert "dikkat" in watch.DEFAULT_ASK.lower()


# -- local camera buffer -----------------------------------------------


def lens(monkeypatch: pytest.MonkeyPatch, images: list) -> watch.Lens:
    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", lambda *_a: FakeCapture(images))
    return watch.Lens(fps=1000)   # return without waiting in the test


def test_the_buffer_keeps_only_the_latest_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two minutes of video is hundreds of megabytes in memory and serves
    nothing; what is asked is "what is there now"."""
    box = lens(monkeypatch, frames(10, 90, 200))
    for _ in range(3):
        box.step()

    frame, age = box.snapshot()
    assert frame.startswith("data:image/jpeg;base64,")
    assert age < 5
    # Raw frames are not accumulated; the backward window is JPEG and bounded.
    assert len(box._history) <= watch.HISTORY
    assert len(box._recent) <= 3


def test_recall_prefers_the_sharp_frame() -> None:
    """"What did I just show": if the user lowered what they showed, the
    current frame is empty. The SHARPEST frame in the window must be chosen
    — frames in motion are blurry, the frame taken while the shown thing is
    held still is sharp."""
    import time as clock

    import cv2
    import numpy as np

    def packed(image) -> bytes:
        ok, raw = cv2.imencode(".jpg", image)
        assert ok
        return raw.tobytes()

    rng = np.random.default_rng(7)
    sharp = rng.integers(0, 255, (120, 160, 3), dtype=np.uint8)   # detailed → sharp
    blurry = np.full((120, 160, 3), 90, dtype=np.uint8)           # flat → blurry

    box = watch.Lens()
    now = clock.time()
    # The sharp frame is the OLD one: just "take the newest" does not give the right answer.
    box._recent = [(now - 3.0, packed(sharp)), (now - 1.0, packed(blurry))]

    frame, age = box.recall(5.0)
    assert frame.startswith("data:image/jpeg;base64,")
    assert age > 2.0   # the chosen one is the sharp frame from three seconds ago


def test_recall_falls_back_to_the_snapshot() -> None:
    """With an empty buffer (camera just opened) the last frame in hand is still an answer."""
    box = watch.Lens()
    assert box.recall(5.0) == ("", 0.0)


def test_snooze_also_clears_the_recent_frames() -> None:
    """Holding ten seconds of frames in memory while saying "I'm not
    watching" would be a half closure — the snooze must empty the backward
    window too."""
    import time as clock

    box = watch.Lens()
    box._recent = [(clock.time(), b"x")]
    box.snooze(10)
    assert box._recent == []
    assert box._eye._capture is None


def test_lens_stop_can_start_again() -> None:
    """HUD close/open: start after stop must be able to set up the loop again."""
    box = watch.Lens()
    box.stop()
    assert not box.running
    if not watch.available():
        return
    box.start()
    box.stop()
    assert not box.running


def test_an_empty_buffer_says_so() -> None:
    box = watch.Lens()
    assert box.snapshot() == ("", 0.0)
    assert not box.live


def test_motion_answers_without_a_frame() -> None:
    """The question "did something happen" must be answerable without ever
    touching the model: in an empty room not a single image should go."""
    import time as clock

    box = watch.Lens()
    now = clock.time()
    box._history = [watch.Moment(at=now - i, change=0.001) for i in range(30)]

    seen = box.motion(60)
    assert seen["quiet"]
    assert seen["busy"] == 0


def test_motion_reports_a_busy_window() -> None:
    import time as clock

    box = watch.Lens()
    now = clock.time()
    box._history = [watch.Moment(at=now - i, change=0.2 if i < 5 else 0.001) for i in range(30)]

    seen = box.motion(60)
    assert not seen["quiet"]
    assert seen["busy"] == 5
    assert seen["peak"] >= 0.2


def test_motion_ignores_what_fell_out_of_the_window() -> None:
    import time as clock

    box = watch.Lens()
    now = clock.time()
    box._history = [watch.Moment(at=now - 300, change=0.9)]

    assert box.motion(60)["frames"] == 0


# -- deck preview ------------------------------------------------------


def test_preview_uses_the_lens_buffer_not_a_second_open(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Reopening the built-in camera while the Lens is open locks on Windows."""
    monkeypatch.setattr(watch, "snapshot", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("snapshot should not run while Lens owns the device")
    ))

    class FakeLens:
        source = "0"

        def jpeg_bytes(self) -> bytes:
            return b"\xff\xd8fake"

    assert watch.preview_jpeg("0", lens=FakeLens()) == b"\xff\xd8fake"
    assert watch.preview_jpeg("", lens=FakeLens()) == b"\xff\xd8fake"


def test_preview_does_not_reopen_while_lens_owns_an_empty_buffer(
        monkeypatch: pytest.MonkeyPatch) -> None:
    called = []
    monkeypatch.setattr(watch, "snapshot", lambda *_a, **_k: called.append(1) or [])

    class FakeLens:
        source = "0"

        def jpeg_bytes(self) -> bytes:
            return b""

    assert watch.preview_jpeg("0", lens=FakeLens()) == b""
    assert called == []


def test_preview_falls_back_to_snapshot_without_lens(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        watch, "snapshot",
        lambda *_a, **_k: ["data:image/jpeg;base64,UEs="],
    )
    import base64
    assert watch.preview_jpeg("rtsp://cam") == base64.b64decode("UEs=")


def test_lens_jpeg_bytes_are_the_last_packed_frame(
        monkeypatch: pytest.MonkeyPatch) -> None:
    box = lens(monkeypatch, frames(10, 200))
    box.step()
    raw = box.jpeg_bytes()
    assert raw[:2] == b"\xff\xd8"
    assert raw == box._recent[-1][1]
