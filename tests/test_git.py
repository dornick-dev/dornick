"""Git motoru, aracı ve GitHub yayın kapısı.

Ağa çıkılmaz: geçici repo, status/commit, boş mesaj reddi, `gh` yokken
öğretici hata. İzin kapısı commit'i sorar, status'u sormaz.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pytest

from dornick import git as gitmod
from dornick import environment
from dornick.config import Config
from dornick.events import EventLog
from dornick.permissions import Decision, PermissionEngine
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry, build_registry
from dornick.tools import git_tool

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="git yok")


def _run(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True,
        **environment.quiet_flags(),
    )


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run(path, "init")
    _run(path, "config", "user.email", "dornick@test")
    _run(path, "config", "user.name", "dornick")
    return path


def _ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test"),
        cancel=asyncio.Event(),
    )


# -- motor -------------------------------------------------------------


def test_status_counts_plus_and_minus_on_a_new_file(tmp_path: Path) -> None:
    root = _repo(tmp_path / "proj")
    (root / "a.txt").write_text("hello\nworld\n", encoding="utf-8")

    snap = gitmod.status(root)

    assert snap["dirty"]
    assert snap["name"] == "proj"
    assert snap["plus"] >= 2
    assert snap["minus"] == 0
    paths = [f["path"] for f in snap["files"]]
    assert "a.txt" in paths


def test_commit_clears_dirty_and_empty_message_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path / "proj")
    (root / "a.txt").write_text("x\n", encoding="utf-8")

    with pytest.raises(gitmod.GitError, match="boş"):
        gitmod.commit(root, "   ")

    snap = gitmod.commit(root, "ilk kayıt")
    assert not snap["dirty"]
    assert snap["files"] == []


def test_create_repo_teaches_when_gh_and_token_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sahte yayın yok: gh yok + anahtar yok = öğretici hata, ağ yok."""
    real_which = shutil.which

    def which(name: str) -> str | None:
        if name == "gh":
            return None
        return real_which(name)

    monkeypatch.setattr(gitmod.shutil, "which", which)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(gitmod.settings, "load_keys", lambda *_a, **_k: {})

    def boom(*_a, **_k):
        raise AssertionError("ağa çıkıldı")

    monkeypatch.setattr(gitmod.urllib.request, "urlopen", boom)

    with pytest.raises(gitmod.GitError, match="gh auth login"):
        gitmod.create_repo("deneme", state_dir=tmp_path)


def test_snapshot_hides_the_bar_when_there_is_no_repo(tmp_path: Path) -> None:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    assert gitmod.snapshot(config) == {"ok": True, "present": False}


def test_snapshot_finds_git_above_the_workshop(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "not.txt").write_text("x\n", encoding="utf-8")
    config = Config.load(tmp_path)
    config.ensure_dirs()
    # 01.09 sözleşmesi: çubuk yalnız ATANMIŞ projede repo görür — atölye
    # karalama alanı ("atölye için repo açmaması lazım", canlı).
    config.sandbox.project = str(tmp_path)
    snap = gitmod.snapshot(config)
    assert snap["present"] and snap["ok"]
    assert snap["dirty"]


# -- araç --------------------------------------------------------------


def test_prompt_names_git_as_an_ability() -> None:
    from dornick.prompt import ABILITIES
    assert any(title == "Git" and "git" in names for title, _what, names in ABILITIES)


def test_tool_mutates_but_status_is_safe() -> None:
    spec = build_registry(subagents=False).get("git")
    assert spec is not None and spec.mutates
    assert "status" in spec.safe_actions
    assert "commit" not in spec.safe_actions

    engine = PermissionEngine("auto", [], [])
    allow, _ = engine.evaluate(spec, {"action": "status"})
    assert allow is Decision.ALLOW
    ask, _ = engine.evaluate(spec, {"action": "commit"})
    assert ask is Decision.ASK


def test_tool_commit_notes_git_for_the_bar(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    ctx = _ctx(tmp_path)
    registry = ToolRegistry()
    git_tool.register(registry)

    result = asyncio.run(registry.get("git").handler(
        {"action": "commit", "message": "araçtan"}, ctx,
    ))

    assert not result.is_error
    notes = ctx.session.log.notes("git")
    assert notes and notes[-1].meta.get("action") == "commit"


def test_tool_empty_commit_message_is_an_error(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    ctx = _ctx(tmp_path)
    registry = ToolRegistry()
    git_tool.register(registry)

    result = asyncio.run(registry.get("git").handler(
        {"action": "commit", "message": ""}, ctx,
    ))
    assert result.is_error
    assert "boş" in result.content
    assert not ctx.session.log.notes("git")


def test_http_git_get_and_commit(tmp_path: Path) -> None:
    from dornick.mind import open_mind
    from dornick.web import MindServer

    _repo(tmp_path)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    config = Config.load(tmp_path)
    config.ensure_dirs()
    config.sandbox.project = str(tmp_path)   # çubuk yalnız projede (01.09)
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    try:
        with urllib.request.urlopen(server.url + "api/git", timeout=5) as resp:
            data = json.loads(resp.read().decode())
        assert data["present"] and data["dirty"]
        req = urllib.request.Request(
            server.url + "api/git",
            data=json.dumps({"action": "commit", "message": "http"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            out = json.loads(resp.read().decode())
        assert out["ok"] and not out["dirty"]
    finally:
        server.stop()
        log.close()


def test_the_bar_ignores_a_repo_in_the_scratch_workshop(tmp_path: Path) -> None:
    """Atölye reposu çubuğa ÇIKMAZ: "+407 Commit · Yayınla" yarası (01.09).
    Ajanın aracı ise scratch_ok=True ile atölyede çalışmayı sürdürür."""
    _repo(tmp_path)
    (tmp_path / "x.txt").write_text("x\n", encoding="utf-8")
    config = Config.load(tmp_path)
    config.ensure_dirs()

    assert gitmod.repo_root(config) is None
    assert gitmod.snapshot(config) == {"ok": True, "present": False}
    assert gitmod.repo_root(config, scratch_ok=True) is not None
