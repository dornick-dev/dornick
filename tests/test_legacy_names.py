"""Files and folders that had Turkish names before 1.5.1 are adopted once.

The promise: an install made with the old product keeps every byte of its
state after the update — the file is renamed, never copied or re-created,
and the old name is never looked at again once the new one exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dornick import apps, artifacts, hooks, legacy_names, recognition, skills
from dornick.config import Config
from dornick.recall import exemplars, identity, temperament
from dornick.sandbox import Sandbox


# -- the primitive ------------------------------------------------------


def test_adopt_renames_only_when_the_new_name_is_missing(tmp_path: Path) -> None:
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text("x", encoding="utf-8")
    assert legacy_names.adopt(old, new) is True
    assert new.read_text(encoding="utf-8") == "x" and not old.exists()
    # Second call: nothing to do; an old file that reappears is NOT adopted
    # over an existing new one (the new one is the truth now).
    old.write_text("stale", encoding="utf-8")
    assert legacy_names.adopt(old, new) is False
    assert new.read_text(encoding="utf-8") == "x" and old.exists()


def test_adopt_is_quiet_when_nothing_is_there(tmp_path: Path) -> None:
    assert legacy_names.adopt(tmp_path / "a", tmp_path / "b") is False


# -- .dornick files -----------------------------------------------------


@pytest.mark.parametrize("old,new", sorted(legacy_names.STATE_FILES.items()))
def test_every_legacy_state_file_is_adopted_by_config_load(tmp_path: Path, old: str, new: str) -> None:
    state = tmp_path / ".dornick"
    state.mkdir()
    (state / old).write_text("{}", encoding="utf-8")

    Config.load(tmp_path)

    assert (state / new).is_file(), f"{old} was not adopted as {new}"
    assert not (state / old).exists()


def test_the_state_file_table_has_no_turkish_target(tmp_path: Path) -> None:
    for new in legacy_names.STATE_FILES.values():
        assert new.isascii() and new == new.lower()


def test_temperament_reads_the_old_file_once(tmp_path: Path) -> None:
    base = temperament.Temperament(caution=0.9)
    (tmp_path / "mizac.json").write_text(
        json.dumps({"taban": base.as_dict(), "hedef": base.as_dict(), "model_id": "m"}),
        encoding="utf-8")
    baseline, _target, model_id = temperament.load(tmp_path)
    assert model_id == "m" and baseline.caution == pytest.approx(0.9)
    assert (tmp_path / "temperament.json").is_file() and not (tmp_path / "mizac.json").exists()


def test_identity_reads_the_old_file_once(tmp_path: Path) -> None:
    (tmp_path / "kimlik.md").write_text("- Sabah erken kalkarım. [n1]\n", encoding="utf-8")
    loaded = identity.load(tmp_path)
    assert loaded.sentences, "the narrative must survive the rename"
    assert (tmp_path / "identity.md").is_file() and not (tmp_path / "kimlik.md").exists()


def test_exemplars_read_the_old_file_once(tmp_path: Path) -> None:
    (tmp_path / "karar_ornekleri.json").write_text(json.dumps({
        "model_id": "m",
        "kararlar": [{"eksen": "temkin", "durum": "d", "karar": "k"}]}), encoding="utf-8")
    assert [e.decision for e in exemplars.load(tmp_path)] == ["k"]
    assert (tmp_path / "decision_exemplars.json").is_file()
    assert not (tmp_path / "karar_ornekleri.json").exists()


def test_the_old_hook_file_is_read_and_still_fenced(tmp_path: Path) -> None:
    state = tmp_path / ".dornick"
    state.mkdir()
    (state / "kancalar.json").write_text(
        json.dumps([{"when": "before", "tool": "shell", "command": "echo x"}]), encoding="utf-8")
    assert hooks.file_path(state).name == "hooks.json"
    assert (state / "hooks.json").is_file() and not (state / "kancalar.json").exists()
    # A write aimed at either name is refused — the fence has no hole named "old".
    for name in ("hooks.json", "kancalar.json"):
        assert hooks.is_protected(Path(".dornick") / name)
        assert hooks.call_touches_hook("shell", {"command": f"Set-Content .dornick/{name} '[]'"})


def test_permission_rules_saved_under_old_tool_names_still_apply() -> None:
    from dornick.permissions import PermissionEngine
    engine = PermissionEngine("ask", ["kos:*", "semboller:*", "shell:git *"], ["denetle:*"])
    assert engine.allow == ["run:*", "symbols:*", "shell:git *"]
    assert engine.deny == ["inspect:*"]


# -- the workshop -------------------------------------------------------


def test_the_old_workshop_folder_is_adopted_under_the_new_name(tmp_path: Path) -> None:
    old = tmp_path / "atolye"
    (old / "proje").mkdir(parents=True)
    (old / "proje" / "app.py").write_text("print(1)", encoding="utf-8")

    box = Sandbox.open(tmp_path)

    assert box.root == (tmp_path / "workshop").resolve()
    assert (tmp_path / "workshop" / "proje" / "app.py").is_file()
    assert not old.exists()


def test_an_explicit_directory_setting_is_left_alone(tmp_path: Path) -> None:
    """A user who pinned `sandbox.directory` to a name of their own keeps it."""
    (tmp_path / "atolye").mkdir()
    box = Sandbox.open(tmp_path, "benim")
    assert box.root.name == "benim" and (tmp_path / "atolye").is_dir()


def test_workshop_internals_are_adopted(tmp_path: Path) -> None:
    root = tmp_path / "workshop"
    (root / "yetenekler").mkdir(parents=True)
    (root / "yetenekler" / "x.py").write_text("NAME='x'", encoding="utf-8")
    (root / "yetenekler" / ".tohumlar").write_text("archive.py\n", encoding="utf-8")
    (root / ".geri-donusum").mkdir()

    Sandbox.open(tmp_path)

    assert (root / "skills" / "x.py").is_file() and not (root / "yetenekler").exists()
    assert (root / ".recycle-bin").is_dir() and not (root / ".geri-donusum").exists()
    # The seed marker follows the folder and is read under its new name.
    assert (root / "skills" / ".tohumlar").is_file()
    skills.seed(root)
    assert (root / "skills" / ".seeded").is_file() and not (root / "skills" / ".tohumlar").exists()
    assert "archive.py" in (root / "skills" / ".seeded").read_text(encoding="utf-8")


def test_skills_folder_adopts_the_old_name_without_config(tmp_path: Path) -> None:
    (tmp_path / "yetenekler").mkdir()
    place = skills.folder(tmp_path)
    assert place.name == "skills" and not (tmp_path / "yetenekler").exists()


def test_the_old_recycle_bin_keeps_receiving_archived_apps(tmp_path: Path) -> None:
    root = tmp_path / "workshop"
    (root / ".geri-donusum").mkdir(parents=True)
    (root / "eski-app").mkdir()
    (root / "eski-app" / "app.py").write_text("", encoding="utf-8")
    reply = apps.remove(root, "eski-app")
    assert reply.get("ok"), reply
    assert (root / ".recycle-bin").is_dir() and not (root / ".geri-donusum").exists()
    assert any(p.name.endswith("eski-app") for p in (root / ".recycle-bin").iterdir())


def test_skip_lists_know_both_recycle_bin_names() -> None:
    assert {".recycle-bin", ".geri-donusum"} <= apps.DISCOVERY_SKIP


# -- artifacts ----------------------------------------------------------


def test_artifact_versions_folder_is_adopted_on_update(tmp_path: Path) -> None:
    meta = artifacts.publish(tmp_path, "Sayfa", "<h1>1</h1>")
    folder = artifacts.folder(tmp_path) / meta["id"]
    (folder / "surumler").mkdir()
    (folder / "surumler" / "0.html").write_text("<h1>0</h1>", encoding="utf-8")

    artifacts.update(tmp_path, meta["id"], "<h1>2</h1>")

    assert (folder / "versions" / "0.html").is_file()
    assert (folder / "versions" / "1.html").is_file()
    assert not (folder / "surumler").exists()


# -- the training rig ---------------------------------------------------


def test_the_installed_rig_moves_from_egitim_to_training(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "app"
    old = root / "egitim"
    (old / "betikler").mkdir(parents=True)
    (old / "betikler" / "08_kisisel_dongu.py").write_text("", encoding="utf-8")
    (old / "veri").mkdir()
    (old / "veri" / "kisisel_durum.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recognition, "_INSTALL_ROOT", root)
    monkeypatch.setattr(recognition, "_INSTALL_SCRIPT", root / "training" / "betikler" / "08_kisisel_dongu.py")
    monkeypatch.setattr(recognition, "_LEGACY_INSTALL_SCRIPT", old / "betikler" / "08_kisisel_dongu.py")

    assert recognition.migrate_rig() is True
    assert (root / "training" / "veri" / "kisisel_durum.json").is_file()
    assert not old.exists()


def test_only_personal_files_move_when_the_new_rig_is_already_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """After the installer wrote `training/`, the old `egitim/veri` still
    holds the personal corpus and watermark: those move, the rest is the
    installer's to remove."""
    root = tmp_path / "app"
    old, new = root / "egitim", root / "training"
    for base in (old, new):
        (base / "betikler").mkdir(parents=True)
        (base / "betikler" / "08_kisisel_dongu.py").write_text("", encoding="utf-8")
    (old / "veri").mkdir()
    (old / "veri" / "kisisel_korpus.jsonl").write_text("{}\n", encoding="utf-8")
    (old / "veri" / "kisisel_durum.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recognition, "_INSTALL_ROOT", root)
    monkeypatch.setattr(recognition, "_INSTALL_SCRIPT", new / "betikler" / "08_kisisel_dongu.py")
    monkeypatch.setattr(recognition, "_LEGACY_INSTALL_SCRIPT", old / "betikler" / "08_kisisel_dongu.py")

    assert recognition.migrate_rig() is True
    assert (new / "veri" / "kisisel_korpus.jsonl").read_text(encoding="utf-8") == "{}\n"
    assert (new / "veri" / "kisisel_durum.json").is_file()
    assert old.is_dir() and not (old / "veri" / "kisisel_durum.json").exists()
    # Running again: nothing left to move.
    assert recognition.migrate_rig() is False
