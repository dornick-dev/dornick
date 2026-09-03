"""Devices: a common format for the connected physical and remote things.

A PLC, a camera, an arm on a serial port, an MCP server — all very
different from each other. The only thing the format pins down is what the
three have in common: what it is, how to connect, where to touch it.

The checks here hold both sides at once: the file the user writes by hand
and the record the agent writes with the tool go to the same place in the
same format.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dornick import devices


def test_a_device_needs_an_id_a_name_and_a_known_kind() -> None:
    """The error message goes to the model. Saying "invalid" forces it to
    guess; saying which field is invalid and why fixes it."""
    with pytest.raises(devices.DeviceError, match="id"):
        devices.parse({"name": "kapı"})

    with pytest.raises(devices.DeviceError, match="name"):
        devices.parse({"id": "kapi"})

    with pytest.raises(devices.DeviceError, match="kind"):
        devices.parse({"id": "kapi", "name": "kapı", "kind": "buzdolabı"})


def test_an_id_cannot_escape_the_folder() -> None:
    """The identity becomes the file name: if a path separator is accepted
    it can write outside the workshop."""
    for bad in ("../kacak", "a/b", "C:\\x", "büyük Harf", ""):
        with pytest.raises(devices.DeviceError):
            devices.parse({"id": bad, "name": "x"})


def test_the_link_is_deliberately_free_form() -> None:
    """Modbus has host/port, a serial port has baud, MCP has a command
    line. Forcing all of them into one schema produces either a mould that
    fits no device or a dict that says nothing."""
    serial = devices.parse({
        "id": "kol", "name": "kol", "kind": "serial",
        "link": {"protocol": "serial", "port_name": "COM3", "baud": 9600},
    })
    assert serial.link["baud"] == 9600

    with pytest.raises(devices.DeviceError, match="link"):
        devices.parse({"id": "kol", "name": "kol", "link": "COM3"})


def test_a_point_says_whether_it_is_written_to() -> None:
    """Writing to the wrong side has a physical consequence."""
    device = devices.parse({
        "id": "kapi", "name": "kapı", "kind": "plc",
        "points": [{"name": "kapı aç", "address": "%QX0.1", "access": "write"}],
    })
    assert device.points[0].access == "write"
    # Read when unspecified: writing by default is dangerous.
    assert devices.parse({
        "id": "a", "name": "a", "points": [{"name": "sıcaklık"}]
    }).points[0].access == "read"


def test_a_device_survives_a_restart(tmp_path: Path) -> None:
    devices.save(tmp_path, {
        "id": "kapi-plc", "name": "kapı PLC", "kind": "plc",
        "link": {"protocol": "modbus-tcp", "host": "192.168.1.50", "port": 502},
        "points": [{"name": "kapı aç", "address": "%QX0.1", "access": "write"}],
        "skills": ["kapi"],
    })

    found, broken = devices.load(tmp_path)
    assert not broken
    assert found[0].id == "kapi-plc"
    assert found[0].points[0].address == "%QX0.1"
    assert found[0].skills == ["kapi"]


def test_devices_live_inside_the_workshop(tmp_path: Path) -> None:
    devices.save(tmp_path, {"id": "a", "name": "a"})
    written = list((tmp_path / devices.FOLDER).glob("*.json"))
    assert [p.name for p in written] == ["a.json"]


def test_a_broken_file_does_not_hide_the_others(tmp_path: Path) -> None:
    """Losing every device because of a half-written hand-edited JSON is
    far worse than that one file."""
    devices.save(tmp_path, {"id": "saglam", "name": "sağlam"})
    (devices.folder(tmp_path) / "bozuk.json").write_text("{ yarim", encoding="utf-8")

    found, broken = devices.load(tmp_path)
    assert [d.id for d in found] == ["saglam"]
    assert len(broken) == 1 and "bozuk.json" in broken[0]


def test_the_file_is_readable_by_a_person(tmp_path: Path) -> None:
    """The user writes to the same files by hand too: an unreadable file
    does not satisfy the "let me add one too" request."""
    devices.save(tmp_path, {"id": "kapi", "name": "kapı PLC'si", "kind": "plc"})
    raw = (devices.folder(tmp_path) / "kapi.json").read_text(encoding="utf-8")

    assert "kapı PLC'si" in raw          # readable Turkish, not an escape sequence
    assert json.loads(raw)["kind"] == "plc"


def test_the_briefing_stays_short(tmp_path: Path) -> None:
    """Having the agent learn what it is connected to by calling a tool on
    every turn is both slow and pointless. But all the addresses of ten
    devices bloat the prompt too: summary line by line, detail on request."""
    for index in range(5):
        devices.save(tmp_path, {
            "id": f"cihaz{index}", "name": f"cihaz {index}", "kind": "plc",
            "points": [{"name": f"adres {n}", "address": f"%QX0.{n}"} for n in range(20)],
        })

    text = devices.briefing(tmp_path)
    assert "cihaz0" in text
    assert "20 adres" in text
    # The addresses themselves are not in the summary.
    assert "%QX0.7" not in text


def test_no_devices_means_no_briefing(tmp_path: Path) -> None:
    """An empty heading ("Bağlı cihazlar: yok") takes space in every
    prompt and says nothing."""
    assert devices.briefing(tmp_path) == ""


def test_related_memories_are_the_ones_about_that_device(tmp_path: Path) -> None:
    """When a device was removed its measurement/address memories lingered
    silently; the user had to say 'delete it from memory too'. Removal
    shows the related memories and asks — it does not forget on its own."""
    from dornick.config import Config
    from dornick.mind import open_mind
    from dornick.tools.devices import related_memories

    config = Config.load(tmp_path)
    config.ensure_dirs()
    mind = open_mind(config.mind_dir, config.sessions_dir, "t")
    mind.remember("Depo yüksekliği 4.2 m, birim cm.", title="depo yüksekliği")
    mind.remember("Bugün hava güneşli.", title="hava")
    device = devices.parse({
        "id": "depo-seviye",
        "name": "Depo seviye ölçer",
        "kind": "plc",
        "points": [{"name": "seviye", "address": "404195"}],
    })

    hits = related_memories(mind, device)
    titles = {m.title for m in hits}
    assert "depo yüksekliği" in titles
    assert "hava" not in titles


def test_removing_a_device_asks_before_forgetting_memories(tmp_path: Path) -> None:
    import asyncio

    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.mind import open_mind
    from dornick.session import Session
    from dornick.tools import ToolContext, ToolRegistry
    from dornick.tools import devices as device_tool

    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
        cancel=asyncio.Event(),
    )
    devices.save(ctx.sandbox.root, {
        "id": "depo-seviye", "name": "Depo seviye ölçer", "kind": "plc",
    })
    mind = open_mind(config.mind_dir, config.sessions_dir, "t")
    mind.remember("Depo seviye adresi 404195.", title="depo adresi")

    registry = ToolRegistry()
    device_tool.register(registry)
    result = asyncio.run(registry.get("device").handler(
        {"action": "remove", "id": "depo-seviye"}, ctx))

    assert devices.find(ctx.sandbox.root, "depo-seviye") is None
    assert "sileyim mi" in result.content
    assert "depo adresi" in result.content
    assert "forget" in result.content
    # The memory stays — no confirmation.
    left = [m.title for m in mind.memories() if not m.deleted]
    assert "depo adresi" in left
