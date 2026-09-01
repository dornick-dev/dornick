"""Cihazlar: bağlı fiziksel ve uzak şeyler için ortak biçim.

Bir PLC, bir kamera, bir seri porttaki kol, bir MCP sunucusu — hepsi
birbirinden çok farklı. Biçimin sabitlediği tek şey, üçünün ortak olması:
ne olduğu, nasıl bağlanılacağı, neresine dokunulacağı.

Buradaki kontroller iki tarafı birden tutuyor: kullanıcının elle yazdığı
dosya ile ajanın araçla yazdığı kayıt aynı yere ve aynı biçimde gidiyor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dornick import devices


def test_a_device_needs_an_id_a_name_and_a_known_kind() -> None:
    """Hata mesajı modele gidiyor. "geçersiz" demek onu tahmin etmeye
    zorluyor; hangi alanın neden geçersiz olduğunu söylemek düzeltiyor."""
    with pytest.raises(devices.DeviceError, match="id"):
        devices.parse({"name": "kapı"})

    with pytest.raises(devices.DeviceError, match="name"):
        devices.parse({"id": "kapi"})

    with pytest.raises(devices.DeviceError, match="kind"):
        devices.parse({"id": "kapi", "name": "kapı", "kind": "buzdolabı"})


def test_an_id_cannot_escape_the_folder() -> None:
    """Kimlik dosya adı oluyor: yol ayracı kabul edilirse atölyenin
    dışına yazılabilir."""
    for bad in ("../kacak", "a/b", "C:\\x", "büyük Harf", ""):
        with pytest.raises(devices.DeviceError):
            devices.parse({"id": bad, "name": "x"})


def test_the_link_is_deliberately_free_form() -> None:
    """Modbus'un host/port'u var, seri portun baud'u, MCP'nin komut
    satırı. Hepsini tek bir şemaya sokmak ya her cihaza uymayan bir kalıp
    ya da hiçbir şey söylemeyen bir sözlük üretir."""
    serial = devices.parse({
        "id": "kol", "name": "kol", "kind": "serial",
        "link": {"protocol": "serial", "port_name": "COM3", "baud": 9600},
    })
    assert serial.link["baud"] == 9600

    with pytest.raises(devices.DeviceError, match="link"):
        devices.parse({"id": "kol", "name": "kol", "link": "COM3"})


def test_a_point_says_whether_it_is_written_to() -> None:
    """Yanlış tarafa yazmak fiziksel bir sonuç doğuruyor."""
    device = devices.parse({
        "id": "kapi", "name": "kapı", "kind": "plc",
        "points": [{"name": "kapı aç", "address": "%QX0.1", "access": "write"}],
    })
    assert device.points[0].access == "write"
    # Belirtilmemişse okuma: varsayılan olarak yazmak tehlikeli.
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
    """Elle yazılmış yarım bir JSON yüzünden bütün cihazların kaybolması,
    o dosyadan çok daha kötü."""
    devices.save(tmp_path, {"id": "saglam", "name": "sağlam"})
    (devices.folder(tmp_path) / "bozuk.json").write_text("{ yarim", encoding="utf-8")

    found, broken = devices.load(tmp_path)
    assert [d.id for d in found] == ["saglam"]
    assert len(broken) == 1 and "bozuk.json" in broken[0]


def test_the_file_is_readable_by_a_person(tmp_path: Path) -> None:
    """Kullanıcı da aynı dosyalara elle yazıyor: okunamayan bir dosya
    "ben de ekleyebileyim" isteğini karşılamıyor."""
    devices.save(tmp_path, {"id": "kapi", "name": "kapı PLC'si", "kind": "plc"})
    raw = (devices.folder(tmp_path) / "kapi.json").read_text(encoding="utf-8")

    assert "kapı PLC'si" in raw          # kaçış dizisi değil, okunur Türkçe
    assert json.loads(raw)["kind"] == "plc"


def test_the_briefing_stays_short(tmp_path: Path) -> None:
    """Ajanın neye bağlı olduğunu her turda araç çağırarak öğrenmesi hem
    yavaş hem anlamsız. Ama on cihazın bütün adresleri de istemi
    şişiriyor: özet satır satır, ayrıntı istendiğinde."""
    for index in range(5):
        devices.save(tmp_path, {
            "id": f"cihaz{index}", "name": f"cihaz {index}", "kind": "plc",
            "points": [{"name": f"adres {n}", "address": f"%QX0.{n}"} for n in range(20)],
        })

    text = devices.briefing(tmp_path)
    assert "cihaz0" in text
    assert "20 adres" in text
    # Adreslerin kendisi özette yok.
    assert "%QX0.7" not in text


def test_no_devices_means_no_briefing(tmp_path: Path) -> None:
    """Boş bir başlık ("Bağlı cihazlar: yok") her istemde yer kaplıyor
    ve hiçbir şey söylemiyor."""
    assert devices.briefing(tmp_path) == ""


def test_related_memories_are_the_ones_about_that_device(tmp_path: Path) -> None:
    """Cihaz silinince ölçüm/adres anıları sessizce kalıyordu; kullanıcı
    'hafızadan da sil' demek zorunda kalıyordu. Silme, ilgili anıları
    gösterir ve sorar — kendiliğinden forget etmez."""
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
    # Anı duruyor — onay yok.
    left = [m.title for m in mind.memories() if not m.deleted]
    assert "depo adresi" in left
