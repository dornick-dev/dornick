"""Reading and writing settings.

Two things can silently break here: the API key leaking to the browser and
a broken value being written to disk making the program unable to open
again. Neither gets noticed unless tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dornick import settings
from dornick.config import Config


@pytest.fixture()
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    # Real keys in the shell environment must not pollute the test.
    for entry in settings.PROVIDERS:
        if entry["env"]:
            monkeypatch.delenv(entry["env"], raising=False)
    # Key verification must not go to the network: no OpenRouter in the
    # test, a fake key would hit the live endpoint and get a 401.
    monkeypatch.setattr("dornick.automode.verify_key", lambda _candidate: "ok")
    cfg = Config(workspace=tmp_path, state_dir=tmp_path / ".dornick")
    cfg.ensure_dirs()
    return cfg


# -- snapshot ----------------------------------------------------------


def test_snapshot_never_carries_a_key(config: Config) -> None:
    """The settings page must never see the real key."""
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": "sk-gizli-deger"}})

    payload = json.dumps(settings.snapshot(config), ensure_ascii=False)
    assert "sk-gizli-deger" not in payload
    # But the "present" information must show, otherwise the user enters it again and again.
    entry = next(p for p in settings.snapshot(config)["providers"] if p["id"] == "anthropic")
    assert entry["has_key"]


def test_a_key_from_the_shell_counts_as_present(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the user gave the key in their shell the page must not say 'missing'."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-kabuktan")
    entry = next(p for p in settings.snapshot(config)["providers"] if p["id"] == "openai")

    assert entry["has_key"] and entry["from_env"]


def test_provider_is_recognized_from_the_address(config: Config) -> None:
    """Many providers speak the 'openai' protocol; which one is selected
    can only be told from the address."""
    updated = settings.apply(config, {"provider": "lmstudio"})
    assert settings.snapshot(updated)["provider"] == "lmstudio"

    updated = settings.apply(updated, {"provider": "openrouter"})
    assert settings.snapshot(updated)["provider"] == "openrouter"

    updated = settings.apply(updated, {"provider": "gemini"})
    assert settings.snapshot(updated)["provider"] == "gemini"
    assert updated.model.base_url.endswith("/v1beta/openai")
    assert updated.model.api_key_env == "GEMINI_API_KEY"


# -- writing -----------------------------------------------------------


def test_choosing_a_provider_sets_address_and_key_variable(config: Config) -> None:
    """Leaving the user to keep all three consistent by hand is an invitation to error."""
    updated = settings.apply(config, {"provider": "lmstudio"})

    assert updated.model.provider == "openai"
    assert updated.model.base_url == "http://localhost:1234/v1"
    assert updated.model.api_key_env is None

    nvidia = settings.apply(config, {"provider": "nvidia"})
    assert nvidia.model.base_url == "https://integrate.api.nvidia.com/v1"
    assert nvidia.model.api_key_env == "NVIDIA_API_KEY"

    deepseek = settings.apply(config, {"provider": "deepseek"})
    assert deepseek.model.base_url == "https://api.deepseek.com"
    assert deepseek.model.api_key_env == "DEEPSEEK_API_KEY"


def test_settings_survive_a_restart(config: Config) -> None:
    settings.apply(config, {
        "model": {"name": "qwen3.5-32b", "max_tokens": 8000, "context_window": 32_000},
        "permissions": {"mode": "yolo"},
    })

    reloaded = Config.load(config.workspace)
    assert reloaded.model.name == "qwen3.5-32b"
    assert reloaded.model.max_tokens == 8000
    assert reloaded.permissions.mode == "yolo"


def test_keys_are_stored_apart_from_the_config(config: Config) -> None:
    """config.json can end up in a project and fall into version control;
    the key must not be written there."""
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": "sk-gizli"}})

    assert "sk-gizli" not in (config.state_dir / "config.json").read_text(encoding="utf-8")
    assert "sk-gizli" in (config.state_dir / "keys.json").read_text(encoding="utf-8")


def test_the_mask_means_unchanged(config: Config) -> None:
    """The page never sees the real value so it cannot send it back either;
    treating a masked field as empty and deleting the key would be data loss."""
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": "sk-gizli"}})
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": settings.MASK}})

    assert settings.load_keys(config.state_dir)["ANTHROPIC_API_KEY"] == "sk-gizli"


def test_an_empty_value_deletes_the_key(config: Config) -> None:
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": "sk-gizli"}})
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": ""}})

    assert "ANTHROPIC_API_KEY" not in settings.load_keys(config.state_dir)


def test_saved_keys_reach_the_environment(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The backends read the key from the environment; no need to open a second path."""
    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-or-1"}})
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    assert settings.export_keys(config.state_dir) == 1
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-1"


def test_changing_a_key_reaches_the_environment_immediately(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the user CHANGES the key from settings it must reach the running
    process's environment immediately — even if an old value is set. Otherwise
    the new key only took effect after restarting the program (that was a bug)."""
    import os

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-eski")
    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-yeni"}})
    assert os.environ["OPENROUTER_API_KEY"] == "sk-yeni"


def test_the_shell_wins_over_the_saved_key(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-dosyadan"}})
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-kabuktan")

    settings.export_keys(config.state_dir)
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "sk-kabuktan"


# -- validation --------------------------------------------------------


@pytest.mark.parametrize(
    ("patch", "why"),
    [
        ({"permissions": {"mode": "sinirsiz"}}, "permission mode"),
        ({"model": {"max_tokens": 10}}, "too-small max_tokens"),
        ({"provider": "yok-boyle-bir-sey"}, "unknown provider"),
        ({"model": {"uydurma_alan": 1}}, "unknown field"),
    ],
)
def test_a_bad_value_is_refused_before_it_reaches_disk(
    config: Config, patch: dict, why: str
) -> None:
    """A broken setting turns into a program that does not open; validation
    is here, not in the UI, because the file can be hand-edited too."""
    with pytest.raises(ValueError):
        settings.apply(config, patch)

    assert not (config.state_dir / "config.json").exists(), why


def test_an_oversized_max_tokens_is_clamped_not_refused(config: Config) -> None:
    """01.09 revision (model ceilings adopted automatically): a max_tokens
    larger than the window is no longer an ERROR — it is silently clamped
    to the window−reserve ceiling. Stopping the user with an error forced
    them to compute the ceiling by hand when switching models."""
    updated = settings.apply(config, {"model": {"max_tokens": 500_000}})
    window = int(updated.model.context_window or 0)
    if window > 0:
        assert updated.model.max_tokens < window
    assert updated.model.max_tokens >= 256


def test_a_partial_patch_leaves_the_rest_alone(config: Config) -> None:
    """The settings page sends partial patches ("I only changed the
    permission mode"); even if the second call holds a stale Config the
    untouched fields must not revert to their old values — the base is the disk."""
    settings.apply(config, {"model": {"name": "ilk-model"}, "permissions": {"mode": "yolo"}})
    updated = settings.apply(config, {"permissions": {"mode": "ask"}})

    assert updated.permissions.mode == "ask"
    assert updated.model.name == "ilk-model"
    assert Config.load(config.workspace).model.name == "ilk-model"


# -- live model change -------------------------------------------------
#
# Pressing "Save" and seeing nothing change, then discovering the program
# has to be closed and reopened, is not a good settings page.


class _FakeAgent:
    def __init__(self, config) -> None:  # noqa: ANN001
        self.config = config
        self.client = object()
        from dornick.permissions import PermissionEngine

        self.permissions = PermissionEngine.from_config(config.permissions)
        self.policy = None
        self.lean = False
        self.reconfigured = 0

    def reconfigure(self, config) -> None:  # noqa: ANN001
        # The observable contract of the real Agent.reconfigure: config is
        # updated, the core is rebuilt. In the test we also count how many
        # times it was called — a model-less save must apply immediately too.
        self.config = config
        self.reconfigured += 1


def _bridge(config):  # noqa: ANN001
    """Builds the bridge without a loop: what is checked here is the decision, not the coroutine."""
    import asyncio
    from dataclasses import replace

    from dornick.desktop import Bridge

    bridge = Bridge.__new__(Bridge)
    bridge.agent = _FakeAgent(config)
    bridge.hub = type("Hub", (), {"emit": lambda self, e: self.seen.append(e),
                                  "seen": []})()
    bridge.hub.seen = []
    bridge._busy = False
    bridge._wanted_model = None
    bridge._wanted_config = None
    bridge.loop = asyncio.new_event_loop()
    bridge.ear = None
    return bridge, replace


def test_changing_the_model_takes_effect_without_a_restart(tmp_path: Path) -> None:
    from dataclasses import replace

    from dornick.config import Config

    config = Config.load(tmp_path)
    bridge, _ = _bridge(config)
    before = bridge.agent.client

    bridge.reload(replace(config, model=replace(config.model, name="başka/model")))

    assert bridge.agent.client is not before
    assert bridge._wanted_model is None
    bridge.loop.close()


def test_a_change_mid_turn_waits_for_the_turn(tmp_path: Path) -> None:
    """Pulling a streaming client out from under kills that answer."""
    from dataclasses import replace

    from dornick.config import Config

    config = Config.load(tmp_path)
    bridge, _ = _bridge(config)
    bridge._busy = True
    before = bridge.agent.client

    bridge.reload(replace(config, model=replace(config.model, name="başka/model")))

    assert bridge.agent.client is before      # not changed yet
    assert bridge._wanted_model is not None   # but waiting

    bridge._busy = False
    bridge._swap_model()
    assert bridge.agent.client is not before
    bridge.loop.close()


def test_a_mode_change_reaches_the_page_as_an_event(tmp_path: Path) -> None:
    """The mode change was announced only with the notice text — text is
    not machine-readable. The dock chip and the plan-approve button can
    only track the real mode via a separate `mode` event (including a mode
    changed from outside the settings page — the outer gate, another tab)."""
    from dataclasses import replace

    from dornick.config import Config

    config = Config.load(tmp_path)
    bridge, _ = _bridge(config)

    bridge.reload(replace(config, permissions=replace(config.permissions, mode="plan")))

    assert {"type": "mode", "mode": "plan"} in bridge.hub.seen
    bridge.loop.close()


def test_settings_that_do_not_touch_the_model_leave_it_alone(tmp_path: Path) -> None:
    """Rebuilding the client on every save means refreshing the connection for nothing."""
    from dataclasses import replace

    from dornick.config import Config

    config = Config.load(tmp_path)
    bridge, _ = _bridge(config)
    before = bridge.agent.client

    bridge.reload(replace(config, voice=replace(config.voice, enabled=True)))

    assert bridge.agent.client is before
    # The client was not refreshed but the core was still rebuilt: the voice
    # was switched on, a sense changed — these must enter the next turn without a restart.
    assert bridge.agent.reconfigured == 1
    assert bridge.agent.config.voice.enabled
    bridge.loop.close()


# -- session switching: new / resume (live) ----------------------------


def _bridge_with_session(tmp_path):
    """A bridge with real config/mind/session; exercises session switching."""
    import asyncio
    from dornick.config import Config
    from dornick.desktop import Bridge
    from dornick.events import EventLog
    from dornick.mind import open_mind
    from dornick.permissions import PermissionEngine
    from dornick.session import Session

    config = Config.load(tmp_path)
    config.ensure_dirs()
    mind = open_mind(config.mind_dir, config.sessions_dir, "ilk")
    sess = Session.create(config.sessions_dir)

    agent = type("A", (), {})()
    agent.config = config
    agent.mind = mind
    agent.session = sess
    agent._last_encoded = "eski"
    agent.permissions = PermissionEngine.from_config(config.permissions)

    rebinds = []
    server = type("S", (), {"rebind": lambda self, s: rebinds.append(s.id)})()
    emits = []
    hub = type("H", (), {"emit": lambda self, e: emits.append(e)})()

    bridge = Bridge.__new__(Bridge)
    bridge.agent = agent
    bridge.server = server
    bridge.hub = hub
    bridge._busy = False
    bridge.loop = asyncio.new_event_loop()
    return bridge, agent, rebinds, emits


def test_new_session_swaps_and_rebinds(tmp_path):
    bridge, agent, rebinds, emits = _bridge_with_session(tmp_path)
    old_id = agent.session.id

    res = bridge.new_session()

    assert res["ok"] and res["id"] != old_id and not res["resumed"]
    assert agent.session.id == res["id"]
    assert agent.mind.session_id == res["id"]     # the mind's id moved too
    assert agent._last_encoded == ""              # encode dedup reset
    assert rebinds == [res["id"]]                 # the event stream was bound to the new log
    assert any(e["type"] == "session_reset" for e in emits)   # the channel
    # snapshot comes after session_reset (the orchestra seed)
    bridge.loop.close()


def test_resume_session_loads_existing(tmp_path):
    from dornick.events import EventLog
    bridge, agent, rebinds, emits = _bridge_with_session(tmp_path)
    # an existing session log
    log = EventLog(agent.config.sessions_dir / "20260610T090000Z.jsonl")
    log.append("message", role="user", content="çorum pompa verimi")
    log.close()

    res = bridge.resume_session("20260610T090000Z")

    assert res["ok"] and res["resumed"] and res["id"] == "20260610T090000Z"
    assert agent.session.id == "20260610T090000Z"
    assert agent.mind.session_id == "20260610T090000Z"
    assert rebinds[-1] == "20260610T090000Z"
    bridge.loop.close()


def test_resume_missing_session_is_reported(tmp_path):
    bridge, agent, *_ = _bridge_with_session(tmp_path)
    res = bridge.resume_session("yok_20990101T000000Z")
    assert not res["ok"] and "bulunamadı" in res["error"]
    bridge.loop.close()


def test_switching_away_while_busy_opens_a_parallel_lane(tmp_path):
    """The old contract was to refuse ("dornick is busy; try when the turn
    ends") — changed by a live request (29.08): the running lane is left
    alone, the new chat opens immediately in a SEPARATE lane."""
    bridge, agent, rebinds, _ = _bridge_with_session(tmp_path)
    agent.client = object()          # the lane factory shares the client
    old_session = agent.session.id
    bridge._busy = True
    res = bridge.new_session()
    assert res["ok"], res
    # The running lane is in place: the old agent's session did NOT change and is still busy.
    assert agent.session.id == old_session
    assert bridge.lanes[old_session].busy is True
    # The active lane is now the new session; its agent is another agent.
    assert bridge.agent is not agent
    assert res["id"] in bridge.lanes and rebinds[-1] == res["id"]
    bridge.loop.close()


def test_snapshot_carries_the_version(config: Config) -> None:
    """The read-only version line in Settings › Machine is fed from here.

    Which version was installed was invisible in the field; the field must
    match the real version in pyproject exactly — there is no second
    version source.
    """
    from dornick import environment

    snap = settings.snapshot(config)
    assert snap["surum"] == environment.version()
    assert snap["surum"] not in ("", "0.0.0")


def test_catalog_providers_have_unique_ids_and_openai_urls() -> None:
    """Presets must not collide; the openai protocol must be in the real endpoint pattern."""
    ids = [e["id"] for e in settings.PROVIDERS]
    assert len(ids) == len(set(ids))
    assert {"gemini", "nvidia", "deepseek", "groq", "mistral", "qwen"} <= set(ids)
    for entry in settings.PROVIDERS:
        if entry["provider"] != "openai" or not entry["base_url"]:
            continue
        url = str(entry["base_url"])
        assert url.startswith("http"), entry["id"]
        assert (
            "localhost" in url
            or url.rstrip("/").endswith("/v1")
            or url.rstrip("/").endswith("/openai")
            or "deepseek.com" in url
        ), entry


def test_openai_models_request_sends_bearer(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Endpoints like Gemini / Groq give 401/404 without a key; Bearer is required."""
    seen: dict[str, str] = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"data":[{"id":"gemini-2.5-flash"}]}'

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        seen["auth"] = req.get_header("Authorization") or ""
        seen["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test-gemini")
    updated = settings.apply(config, {"provider": "gemini", "name": "gemini-2.5-flash"})
    names = settings.available_models(updated)
    assert names == ["gemini-2.5-flash"]
    assert seen["auth"] == "Bearer sk-test-gemini"
    assert seen["url"].endswith("/v1beta/openai/models")

def test_background_lane_events_do_not_leak_into_the_active_chat(tmp_path):
    """The invisible pillar of parallel lanes: the background lane's
    text/tool events do not leak into the active chat; approval requests
    pass through from EVERY lane (otherwise the background turn waits forever)."""
    bridge, agent, rebinds, emits = _bridge_with_session(tmp_path)
    agent.client = object()
    bridge._busy = True
    res = bridge.new_session()
    assert res['ok']
    old = bridge.lanes[agent.session.id]
    new = bridge.lanes[res['id']]
    emits.clear()
    # The background lane's io: the text event does NOT reach the broadcast.
    background_io = bridge.io(old)
    background_io.on_text('sizmamali')
    assert emits == []
    # The active lane's io: the same event reaches the broadcast.
    front_io = bridge.io(new)
    front_io.on_text('gorunmeli')
    assert any(e.get('type') == 'assistant_delta' for e in emits)
    bridge.loop.close()


# -- catalogue capabilities --------------------------------------------


def _openrouter_entry(**extra: object) -> dict:
    row = {
        "id": "acme/sight",
        "name": "Sight",
        "context_length": 128_000,
        "architecture": {"input_modalities": ["text", "image"]},
        "supported_parameters": ["max_tokens", "tools", "reasoning"],
        "top_provider": {"context_length": 64_000},
    }
    row.update(extra)
    return row


def test_openrouter_catalog_adopts_window_vision_and_thinking(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OpenRouter `/models` tells these fields; an id-only row is not enough."""
    monkeypatch.setattr(settings.lmstudio, "models", lambda _u: [])
    monkeypatch.setattr(
        settings, "_openai_models_payload",
        lambda _c: ({"data": [_openrouter_entry()]}, None),
    )
    sight = next(r for r in settings.scan_models(config) if r["id"] == "acme/sight")
    assert sight["max_context"] == 128_000
    assert sight["vision"] is True
    assert sight["thinking"] is True
    assert sight["tools"] is True
    assert sight["name"] == "Sight"


def test_batch_only_models_are_hidden_from_chat_catalog(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `:batch` variant is specific to the Batch API; if selected chat gives 404."""
    monkeypatch.setattr(settings.lmstudio, "models", lambda _u: [])
    monkeypatch.setattr(
        settings, "_openai_models_payload",
        lambda _c: ({"data": [
            _openrouter_entry(id="google/gemini-flash"),
            _openrouter_entry(id="google/gemini-flash:batch", name="Gemini batch"),
            {"id": "acme/embed-v1", "type": "embeddings"},
        ]}, None),
    )
    ids = [r["id"] for r in settings.scan_models(config)]
    assert "google/gemini-flash" in ids
    assert "google/gemini-flash:batch" not in ids
    assert settings.batch_only_model("google/gemini-flash:batch")
    assert not settings.batch_only_model("google/gemini-flash:free")


def test_apply_strips_batch_suffix_to_sync_model(config: Config) -> None:
    updated = settings.apply(config, {
        "model": {"name": "google/gemini-3.7-flash:batch"},
    })
    assert updated.model.name == "google/gemini-3.7-flash"


def test_a_catalog_id_does_not_invent_caps(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The official OpenAI list gives only ids — window/vision are not invented."""
    monkeypatch.setattr(settings.lmstudio, "models", lambda _u: [])
    monkeypatch.setattr(
        settings, "_openai_models_payload",
        lambda _c: ({"data": [{"id": "gpt-4o", "object": "model"}]}, None),
    )
    row = next(r for r in settings.scan_models(config) if r["id"] == "gpt-4o")
    assert "max_context" not in row
    assert "vision" not in row
    assert "thinking" not in row
    assert "tools" not in row


def test_detect_caps_returns_catalog_fields_without_inventing(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        settings, "scan_models",
        lambda _c: [{"id": "acme/sight", "max_context": 128_000, "vision": True}],
    )
    config.model.name = "acme/sight"
    caps = settings.detect_caps(config)
    assert caps == {"max_context": 128_000, "vision": True}
    assert settings.detect_window(config) == 128_000


def test_detect_caps_is_empty_for_oto(config: Config) -> None:
    """Oto is a pool; a single model has no window."""
    config.model.name = "oto"
    assert settings.detect_caps(config) == {}
    assert settings.detect_window(config) is None


def test_apply_does_not_scan_the_catalog(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scan inside apply led to a 10 s timeout on OpenRouter."""
    monkeypatch.setattr(
        settings, "scan_models",
        lambda _c: (_ for _ in ()).throw(AssertionError("the catalogue must not be scanned")),
    )
    updated = settings.apply(config, {
        "model": {
            "name": "acme/sight",
            "context_window": 128_000,
            "vision": False,
            "can_think": False,
            "thinking": False,
        },
    })
    assert updated.model.vision is False
    assert updated.model.can_think is False
    reloaded = Config.load(config.workspace)
    assert reloaded.model.vision is False
    assert reloaded.model.can_think is False
    assert reloaded.model.context_window == 128_000


def test_apply_adopts_caps_when_model_id_changes(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a model is selected window/capabilities fill in without Detect."""
    monkeypatch.setattr(
        settings, "detect_caps",
        lambda _c: {"max_context": 99_000, "vision": True, "thinking": False},
    )
    updated = settings.apply(config, {"model": {"name": "acme/flash"}})
    assert updated.model.name == "acme/flash"
    assert updated.model.context_window == 99_000
    assert updated.model.vision is True
    assert updated.model.thinking is False
    assert updated.model.max_tokens <= 99_000 - settings._TOKEN_RESERVE


def test_a_model_that_cannot_think_omits_the_anthropic_field() -> None:
    from dornick.config import ModelConfig

    assert ModelConfig(can_think=False, thinking=True).thinking_param() is None
    assert ModelConfig(thinking=False).thinking_param() == {"type": "disabled"}


def test_anthropic_catalog_does_not_invent_a_window(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    config.model.provider = "anthropic"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"data":[{"id":"claude-opus-4-8","display_name":"Opus"}]}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    rows = settings.scan_models(config)
    assert rows[0]["id"] == "claude-opus-4-8"
    assert rows[0]["name"] == "Opus"
    assert "max_context" not in rows[0]
    assert rows[0]["vision"] is True
    assert rows[0]["thinking"] is True


def test_lmstudio_thinking_is_omitted_when_the_server_is_silent(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dornick import lmstudio

    monkeypatch.setattr(settings.lmstudio, "models", lambda _u: [
        lmstudio.Model(
            key="q", name="Q", max_context=8000, vision=False, tools=True,
            instances=[],
        ),
        lmstudio.Model(
            key="r", name="R", max_context=8000, vision=True, tools=True,
            thinking=True, instances=[],
        ),
    ])
    config.model.base_url = "http://localhost:1234/v1"
    rows = {r["id"]: r for r in settings.scan_models(config)}
    assert "thinking" not in rows["q"]
    assert rows["r"]["thinking"] is True
    assert rows["q"]["vision"] is False


def test_ollama_show_fills_caps_the_catalog_lacks(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dornick.config import ModelConfig

    config.model = ModelConfig(name="llama3", base_url="http://localhost:11434/v1")
    monkeypatch.setattr(settings, "scan_models", lambda _c: [{"id": "llama3"}])

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                "model_info": {"llama.context_length": 8192},
                "capabilities": ["completion", "tools"],
            }).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    caps = settings.detect_caps(config)
    assert caps["max_context"] == 8192
    assert caps["vision"] is False
    assert caps["thinking"] is False
    assert caps["tools"] is True


def test_ollama_show_is_skipped_when_the_catalog_already_knows(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dornick.config import ModelConfig

    config.model = ModelConfig(name="llama3", base_url="http://localhost:11434/v1")
    monkeypatch.setattr(settings, "scan_models", lambda _c: [{
        "id": "llama3", "max_context": 4096, "vision": True, "thinking": False,
    }])

    def _never(*a, **k):  # pragma: no cover
        raise AssertionError("/api/show should not have been called")

    monkeypatch.setattr("urllib.request.urlopen", _never)
    assert settings.detect_caps(config) == {
        "max_context": 4096, "vision": True, "thinking": False,
    }


def test_the_night_sleep_switch_round_trips(config: Config) -> None:
    """The settings page echoes the whole `sleep` section, label included;
    the flag lands on disk and comes back in the next snapshot."""
    assert settings.snapshot(config)["sleep"]["uyku_acik"] is True
    updated = settings.apply(config, {"sleep": {
        "uyku_acik": False, "label": settings.snapshot(config)["sleep"]["label"]}})
    assert updated.sleep.uyku_acik is False
    assert Config.load(config.workspace).sleep.uyku_acik is False
    assert settings.snapshot(updated)["sleep"]["uyku_acik"] is False
    assert settings.apply(updated, {"sleep": {"uyku_acik": True}}).sleep.uyku_acik is True
