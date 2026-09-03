"""The agent's body: its senses and the modules it attached to itself.

The only rule here is that everything in the list really exists. A camera
standing on the stage, even faint, says "I have this"; drawing a device
that does not exist would be a lie that looks like it is working on screen.
"""

from __future__ import annotations

from pathlib import Path

from dornick import organs, skills
from dornick.config import Config


def test_the_senses_are_always_listed(tmp_path: Path) -> None:
    """They show even when off: what it has matters as much as what is
    off. An empty stage says "I have nothing"."""
    body = organs.inventory(Config.load(tmp_path))
    ids = {organ["id"] for organ in body}

    assert {"mic", "lens", "voice"} <= ids


def test_the_hand_is_part_of_the_body(tmp_path: Path) -> None:
    """Screen and hand are an organ: even if the machine does not support
    it, it must show as 'yok', not be absent entirely. The agent sees what
    it can do in its body."""
    hand = next(o for o in organs.inventory(Config.load(tmp_path)) if o["id"] == "hand")
    assert "screen" in hand["tools"] and "hand" in hand["tools"]


def test_a_closed_camera_says_so(tmp_path: Path, monkeypatch) -> None:
    # Must pass on a camera-less dev machine too: the probe is pinned, the
    # test checks the wording of the "present but off" state, not the device.
    monkeypatch.setattr(organs, "has_camera", lambda lens=None: True)
    config = Config.load(tmp_path)
    lens = next(o for o in organs.inventory(config) if o["id"] == "lens")

    assert not lens["live"]
    assert lens["state"] == "kapalı"


def test_an_open_camera_is_live(tmp_path: Path) -> None:
    """The real state, not the setting. A camera that looked on in the
    settings could be unopened and appeared to be working on screen."""

    class Open:
        live = True

    lens = next(
        o for o in organs.inventory(Config.load(tmp_path), lens=Open()) if o["id"] == "lens"
    )
    assert lens["live"] and lens["state"] == "açık"


def test_the_camera_is_used_by_the_look_tool(tmp_path: Path) -> None:
    """The UI learns from here which tool touches which organ; if it were
    guessed there, a new tool would silently stay unmatched."""
    lens = next(o for o in organs.inventory(Config.load(tmp_path)) if o["id"] == "lens")
    assert "look" in lens["tools"]
    assert "kamera" in lens["tools"]
    assert lens["name"] == "Bilgisayar kamerası"


def test_named_cameras_are_organs_the_model_can_call(tmp_path: Path) -> None:
    from dornick import watch

    config = Config.load(tmp_path)
    config.ensure_dirs()
    watch.save(config.state_dir, [
        watch.Camera(id="cam_1", name="bahçe", kind="rtsp", host="10.0.0.8",
                     last_note="kişi"),
    ])
    body = organs.inventory(config)
    cam = next(o for o in body if o["id"] == "cam:cam_1")
    assert cam["name"] == "bahçe"
    assert "kamera" in cam["tools"]
    assert "kişi" in cam["detail"]


def test_a_deaf_ear_is_not_listening(tmp_path: Path) -> None:
    """While the agent speaks the ear is closed. Showing "dinliyor" on the
    stage at that moment would look like it hears its own voice."""

    class Deafened:
        deaf = True

    mic = next(
        o for o in organs.inventory(Config.load(tmp_path), ear=Deafened()) if o["id"] == "mic"
    )
    assert mic["state"] == "sağır"
    assert not mic["live"]


def test_self_written_modules_become_organs(tmp_path: Path) -> None:
    """A skill the agent wrote for itself — map, PLC, USB, whatever it
    wrote — is part of its body. Not a hand-kept list: read from the files
    in the workshop."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    root = config.open_sandbox().root
    skills.scaffold(root, "plc", "Omron PLC adreslerinden değer okur")

    body = organs.inventory(config)
    plc = next((o for o in body if o["id"] == "skill:plc"), None)

    assert plc is not None
    assert plc["kind"] == organs.MODULE
    assert "plc" in plc["tools"]
    assert "Omron" in plc["detail"]


def test_a_broken_module_does_not_empty_the_body(tmp_path: Path) -> None:
    """A half-finished skill file must not bring down the whole organ
    list: the microphone not showing is a far worse failure than one broken
    file."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    root = config.open_sandbox().root
    folder = skills.folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "yarim.py").write_text("def run(", encoding="utf-8")

    ids = {organ["id"] for organ in organs.inventory(config)}
    assert {"mic", "lens", "voice"} <= ids


def test_the_workshop_is_the_only_place_modules_live(tmp_path: Path) -> None:
    """A Python file written outside the workshop does not count as a skill.

    Everything the agent writes for itself must stay in its own folder; a
    file that leaves it neither shows on the stage nor is ever loaded.
    """
    config = Config.load(tmp_path)
    config.ensure_dirs()
    outside = tmp_path / "kacak.py"
    outside.write_text(
        'NAME = "kacak"\nDESCRIPTION = "x"\nSCHEMA = {}\ndef run(a, c): return ""\n',
        encoding="utf-8",
    )

    ids = {organ["id"] for organ in organs.inventory(config)}
    assert "skill:kacak" not in ids
