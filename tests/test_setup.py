"""Setup command tests.

The single goal here is a frictionless first launch: the user should not
have to type environment variables every time, nor be left alone with an
empty window and a wrong configuration.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dornick.cli import _has_model
from dornick.config import Config
from dornick.setup import Provider, discover, write_config


class Quiet:
    """A silent recorder standing in for the Console."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, *args: object) -> None:
        self.lines.append(" ".join(str(a) for a in args))


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    return Config.load(tmp_path)


def test_config_is_written_in_the_shape_config_load_expects(config: Config) -> None:
    """The written file must be readable back — otherwise setup is silently useless."""
    write_config(config, Provider("LM Studio", "openai", "qwen/q3", "http://localhost:1234/v1"))

    reloaded = Config.load(config.workspace)
    assert reloaded.model.provider == "openai"
    assert reloaded.model.name == "qwen/q3"
    assert reloaded.model.base_url == "http://localhost:1234/v1"


def test_switching_to_anthropic_clears_the_local_address(config: Config) -> None:
    """A leftover base_url would send Anthropic requests to the local server."""
    write_config(config, Provider("LM Studio", "openai", "yerel", "http://localhost:1234/v1"))
    write_config(config, Provider("Anthropic", "anthropic", "claude-opus-4-8"))

    assert Config.load(config.workspace).model.base_url is None


def test_other_settings_are_preserved(config: Config) -> None:
    config.ensure_dirs()
    path = config.state_dir / "config.json"
    path.write_text(
        json.dumps({"permissions": {"mode": "plan"}, "model": {"max_tokens": 4000}}),
        encoding="utf-8",
    )

    write_config(config, Provider("LM Studio", "openai", "yerel", "http://localhost:1234/v1"))

    reloaded = Config.load(config.workspace)
    assert reloaded.permissions.mode == "plan"
    assert reloaded.model.max_tokens == 4000
    assert reloaded.model.name == "yerel"


def test_discovery_survives_a_dead_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """A closed server must not bring setup down, it just must not be in the list."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("dornick.setup.CANDIDATES", (("Yok", "http://127.0.0.1:9/v1"),))
    assert discover() == []


def test_embedding_models_are_not_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    """An embedding model cannot chat; if it enters the list the user is misled."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("dornick.setup.CANDIDATES", (("Sahte", "http://x/v1"),))
    monkeypatch.setattr(
        "dornick.setup._models", lambda _url: ["qwen/q3", "text-embedding-nomic"]
    )

    assert [p.model for p in discover()] == ["qwen/q3"]


def test_anthropic_is_offered_only_with_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dornick.setup.CANDIDATES", ())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert [p.provider for p in discover()] == ["anthropic"]

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert discover() == []


# -- the gate before running -------------------------------------------


def test_unconfigured_run_is_blocked(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    """Launching without a key and without an address would blow up on the first message.

    Instead of leaving the user alone with an empty window, we stop here
    and say what needs doing.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # The fresh-install default is OpenRouter: without its key either, it's closed.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert _has_model(config) is False


def test_local_address_is_enough(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    write_config(config, Provider("LM Studio", "openai", "yerel", "http://localhost:1234/v1"))
    assert _has_model(Config.load(config.workspace)) is True


def test_anthropic_key_is_enough(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    # The default is now OpenRouter; Anthropic's sufficiency must be
    # measured under its own configuration.
    write_config(config, Provider("Anthropic", "anthropic", "claude-opus-4-8"))
    assert _has_model(Config.load(config.workspace)) is True
