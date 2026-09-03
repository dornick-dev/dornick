"""Portability: moving what dornick accumulated from one machine to another.

Two contracts: (1) the export→import round trip carries memories, links,
goals, skills without loss; (2) import is a MERGE — it does not overwrite:
the same memory does not enter twice (idempotent), the existing identity
(soul) is not crushed.
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

from dornick import recognition, transfer
from dornick.config import Config
from dornick.mind import open_mind


def _mind(root: Path):
    cfg = Config.load(root)
    cfg.ensure_dirs()
    mind = open_mind(cfg.mind_dir, cfg.sessions_dir, "cur")
    return cfg, mind


def test_export_then_import_carries_memories(tmp_path: Path) -> None:
    src_root = tmp_path / "makineA"
    dst_root = tmp_path / "makineB"

    cfg_a, mind_a = _mind(src_root)
    m1 = mind_a.remember("Çorum pompa verimi %72", kind="fact", title="pompa")
    m2 = mind_a.remember("Kuyu seviyesi alarmı 2.5m", kind="fact", title="alarm")
    mind_a.bridge(m1.id, m2.id, reason="aynı saha")
    # A skill file (in the workshop).
    skills = cfg_a.open_sandbox().root / "yetenekler"
    skills.mkdir(parents=True, exist_ok=True)
    (skills / "modbus.py").write_text("NAME='modbus'\n", encoding="utf-8")

    bundle = transfer.export_bundle(cfg_a, mind_a)
    assert isinstance(bundle, bytes) and len(bundle) > 0

    cfg_b, mind_b = _mind(dst_root)
    assert mind_b.store.count() == 0
    result = transfer.import_bundle(cfg_b, mind_b, bundle)

    assert result["ok"]
    assert result["memories"] == 2
    assert result["links"] >= 1
    assert result["skills"] == 1

    # The memories must really be searchable (the signature index was built).
    hits = mind_b.recall("pompa verimi")
    assert any("pompa" in h.item.title.lower() or "72" in h.item.content for h in hits)
    # The skill file is at the target.
    assert (cfg_b.open_sandbox().root / "yetenekler" / "modbus.py").is_file()


def test_import_is_idempotent(tmp_path: Path) -> None:
    """Importing the same package twice must not duplicate the memory."""
    cfg_a, mind_a = _mind(tmp_path / "A")
    mind_a.remember("tek bir anı", kind="fact")
    bundle = transfer.export_bundle(cfg_a, mind_a)

    cfg_b, mind_b = _mind(tmp_path / "B")
    first = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert first["memories"] == 1
    count_after_first = mind_b.store.count()

    second = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert second["memories"] == 0                 # nothing new
    assert mind_b.store.count() == count_after_first  # no duplication


def test_import_does_not_overwrite_existing_persona(tmp_path: Path) -> None:
    """If the target has a soul the incoming package must not crush it — the identity is preserved."""
    cfg_a, mind_a = _mind(tmp_path / "A")
    mind_a.remember("bir anı", kind="fact")
    persona_a = Path(cfg_a.workspace) / "persona.md"
    persona_a.write_text("Ben A'nın ruhuyum", encoding="utf-8")
    cfg_a.persona_path = persona_a
    bundle = transfer.export_bundle(cfg_a, mind_a)

    cfg_b, mind_b = _mind(tmp_path / "B")
    persona_b = Path(cfg_b.workspace) / "persona.md"
    persona_b.write_text("Ben B'nin ruhuyum", encoding="utf-8")
    cfg_b.persona_path = persona_b

    result = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert result["persona"] is False                       # untouched
    assert persona_b.read_text(encoding="utf-8") == "Ben B'nin ruhuyum"


def test_import_rejects_non_bundle(tmp_path: Path) -> None:
    cfg_b, mind_b = _mind(tmp_path / "B")
    result = transfer.import_bundle(cfg_b, mind_b, b"not a zip at all")
    assert not result["ok"]


# -- selective parts ---------------------------------------------------------


def _names(bundle: bytes) -> set[str]:
    return set(zipfile.ZipFile(io.BytesIO(bundle)).namelist())


def _fake_rig(monkeypatch, root: Path) -> Path:
    """Moves the training rig's personal files to a temporary place.

    The real rig is installed on this machine; so that the test does not
    touch the user's corpus (and runs on a machine without the rig too) the
    paths are monkeypatched — transfer/recognition read them at call time.
    """
    data = root / "duzenek" / "veri"
    data.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(recognition, "CORPUS", data / "kisisel_korpus.jsonl")
    monkeypatch.setattr(recognition, "WATERMARK", data / "kisisel_durum.json")
    return data


def test_selective_export_only_memories(tmp_path: Path, monkeypatch) -> None:
    """A memories-only package must carry nothing from the other parts."""
    _fake_rig(monkeypatch, tmp_path)
    cfg, mind = _mind(tmp_path / "A")
    mind.remember("bir anı", kind="fact")
    (cfg.open_sandbox().root / "proje.py").write_text("print(1)\n", encoding="utf-8")

    names = _names(transfer.export_bundle(cfg, mind, ["anilar"]))
    assert "recall.db" in names
    assert not any(n.startswith(("tanima/", "projeler/", "ayarlar/")) for n in names)

    # A request without parameters is the same (backwards compatibility).
    old = _names(transfer.export_bundle(cfg, mind))
    assert old == names


def test_export_never_contains_keys(tmp_path: Path, monkeypatch) -> None:
    """Keys must enter the archive in no part — even the full package is clean.

    The api_key_env in config.json is dropped too: not a single byte
    pointing at a key may remain inside the package.
    """
    data = _fake_rig(monkeypatch, tmp_path)
    (data / "kisisel_korpus.jsonl").write_text('{"girdi": "soru"}\n', encoding="utf-8")
    (data / "kisisel_durum.json").write_text('{"son_created": "x"}', encoding="utf-8")

    cfg, mind = _mind(tmp_path / "A")
    mind.remember("bir anı", kind="fact")
    (cfg.state_dir / "keys.json").write_text(
        json.dumps({"OPENROUTER_API_KEY": "sk-or-v1-cokgizli"}), encoding="utf-8")
    (cfg.state_dir / "config.json").write_text(json.dumps({
        "model": {"name": "m", "base_url": "https://openrouter.ai/api/v1",
                  "api_key_env": "OPENROUTER_API_KEY"},
    }), encoding="utf-8")
    (cfg.state_dir / "taban.npz").write_bytes(b"NPZ")

    bundle = transfer.export_bundle(cfg, mind, list(transfer.PARTS))
    names = _names(bundle)
    assert "ayarlar/config.json" in names and "tanima/taban.npz" in names
    assert "keys.json" not in names and not any("keys" in n for n in names)
    assert b"OPENROUTER" not in bundle
    assert b"sk-or" not in bundle


def test_selective_import_respects_part_filter(tmp_path: Path, monkeypatch) -> None:
    """Even with memories in the archive only the requested part must be processed."""
    data = _fake_rig(monkeypatch, tmp_path)
    (data / "kisisel_korpus.jsonl").write_text('{"girdi": "soru"}\n', encoding="utf-8")
    cfg_a, mind_a = _mind(tmp_path / "A")
    mind_a.remember("taşınmaması gereken anı", kind="fact")
    (cfg_a.state_dir / "taban.npz").write_bytes(b"KISISEL-NPZ")
    bundle = transfer.export_bundle(cfg_a, mind_a, ["anilar", "tanima"])

    cfg_b, mind_b = _mind(tmp_path / "B")
    result = transfer.import_bundle(cfg_b, mind_b, bundle, ["tanima"])
    assert result["ok"]
    assert result["memories"] == 0 and mind_b.store.count() == 0
    assert (cfg_b.state_dir / "taban.npz").read_bytes() == b"KISISEL-NPZ"


def test_import_recognition_without_rig_keeps_personal_files(
        tmp_path: Path, monkeypatch) -> None:
    """On a machine without the rig the personal files must not be lost: to tanima_yedek."""
    data = _fake_rig(monkeypatch, tmp_path)
    (data / "kisisel_korpus.jsonl").write_text('{"girdi": "soru"}\n', encoding="utf-8")
    (data / "kisisel_durum.json").write_text('{"son_created": "x"}', encoding="utf-8")
    cfg_a, mind_a = _mind(tmp_path / "A")
    (cfg_a.state_dir / "taban.npz").write_bytes(b"NPZ")
    bundle = transfer.export_bundle(cfg_a, mind_a, ["tanima"])

    # At the target the rig is "not installed": the path points at a non-existent folder.
    monkeypatch.setattr(recognition, "CORPUS", tmp_path / "yok" / "kisisel_korpus.jsonl")
    monkeypatch.setattr(recognition, "WATERMARK", tmp_path / "yok" / "kisisel_durum.json")
    cfg_b, mind_b = _mind(tmp_path / "B")
    result = transfer.import_bundle(cfg_b, mind_b, bundle, ["tanima"])
    assert result["ok"] and result["tanima"] == 3
    assert (cfg_b.state_dir / "taban.npz").is_file()
    assert (cfg_b.state_dir / "tanima_yedek" / "kisisel_korpus.jsonl").is_file()
    assert (cfg_b.state_dir / "tanima_yedek" / "kisisel_durum.json").is_file()


def test_roundtrip_projects_and_settings(tmp_path: Path, monkeypatch) -> None:
    """Workshop + settings are carried; the overwritten existing state is backed up."""
    _fake_rig(monkeypatch, tmp_path)
    cfg_a, mind_a = _mind(tmp_path / "A")
    workshop_a = cfg_a.open_sandbox().root
    (workshop_a / "web").mkdir(parents=True, exist_ok=True)
    (workshop_a / "web" / "index.html").write_text("<b>site</b>", encoding="utf-8")
    (workshop_a / "node_modules").mkdir(exist_ok=True)
    (workshop_a / "node_modules" / "sisman.js").write_text("x", encoding="utf-8")
    (cfg_a.state_dir / "config.json").write_text(json.dumps({
        "model": {"name": "m", "base_url": "https://openrouter.ai/api/v1",
                  "api_key_env": "OPENROUTER_API_KEY"},
    }), encoding="utf-8")
    bundle = transfer.export_bundle(cfg_a, mind_a, ["projeler", "ayarlar"])
    names = _names(bundle)
    assert "projeler/web/index.html" in names
    assert not any("node_modules" in n for n in names)   # residue stays out

    cfg_b, mind_b = _mind(tmp_path / "B")
    (cfg_b.state_dir / "config.json").write_text('{"eski": true}', encoding="utf-8")
    result = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert result["ok"] and result["projeler"] == 1 and result["ayarlar"] == 1
    assert (cfg_b.open_sandbox().root / "web" / "index.html").read_text(
        encoding="utf-8") == "<b>site</b>"
    # api_key_env did not enter the package but was re-derived from base_url on import.
    back = json.loads((cfg_b.state_dir / "config.json").read_text(encoding="utf-8"))
    assert back["model"]["api_key_env"] == "OPENROUTER_API_KEY"
    # The overwritten old config sits in the backup folder.
    backup = Path(result["yedek"])
    assert (backup / "ayarlar" / "config.json").read_text(encoding="utf-8") == '{"eski": true}'


# -- reset -------------------------------------------------------------------


def test_reset_memories_backs_up_then_clears(tmp_path: Path) -> None:
    """Memory reset: first a consistent backup, then an empty mind; goals stay."""
    cfg, mind = _mind(tmp_path / "A")
    mind.remember("silinecek anı bir", kind="fact")
    mind.remember("silinecek anı iki", kind="fact")
    mind.push_goal("kalacak hedef")

    result = transfer.reset_memories(cfg, mind)
    assert result["ok"] and result["silinen"] == 2
    assert mind.store.count() == 0
    assert mind.recall("silinecek") == []
    assert [g.text for g in mind.goals()] == ["kalacak hedef"]   # a goal is not a memory

    # The backup is a real memory copy: two records inside.
    copy = Path(result["yedek"]) / "anilar" / "recall.db"
    con = sqlite3.connect(copy)
    try:
        assert con.execute("SELECT COUNT(*) FROM node").fetchone()[0] == 2
    finally:
        con.close()


def test_recognition_reset_moves_files_and_falls_back(tmp_path: Path, monkeypatch) -> None:
    """Know-me reset: personal files go to the backup, the cache drops."""
    from dornick.recall import writer

    data = _fake_rig(monkeypatch, tmp_path)
    (data / "kisisel_korpus.jsonl").write_text('{"girdi": "soru"}\n', encoding="utf-8")
    (data / "kisisel_durum.json").write_text('{"son_created": "x"}', encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "taban.npz").write_bytes(b"KISISEL")

    result = recognition.reset(state)
    assert result["ok"] and sorted(result["tasinan"]) == [
        "kisisel_durum.json", "kisisel_korpus.jsonl", "taban.npz"]
    assert not (state / "taban.npz").exists()
    assert not (data / "kisisel_korpus.jsonl").exists()
    backup = Path(result["yedek"]) / "tanima"
    assert (backup / "taban.npz").read_bytes() == b"KISISEL"
    assert (backup / "kisisel_korpus.jsonl").is_file()
    # The cache dropped: the next enrichment will probe the disk again.
    assert writer._writer is None and writer._attempted is False

    # Second reset: nothing to move, no backup folder is opened.
    again = recognition.reset(state)
    assert again["ok"] and again["tasinan"] == [] and again["yedek"] == ""


def test_blank_target_adopts_persona(tmp_path: Path) -> None:
    """If the target's soul is empty the incoming soul is adopted — when moving to a new dornick."""
    cfg_a, mind_a = _mind(tmp_path / "A")
    mind_a.remember("bir anı", kind="fact")
    persona_a = Path(cfg_a.workspace) / "persona.md"
    persona_a.write_text("taşınan ruh", encoding="utf-8")
    cfg_a.persona_path = persona_a
    bundle = transfer.export_bundle(cfg_a, mind_a)

    cfg_b, mind_b = _mind(tmp_path / "B")   # no soul
    result = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert result["persona"] is True
    assert (Path(cfg_b.workspace) / "persona.md").read_text(encoding="utf-8") == "taşınan ruh"
