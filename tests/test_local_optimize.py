"""Local LLM optimisation: fitting the context, unloading the other model."""

from __future__ import annotations

from dornick import lmstudio


def test_suggest_context_caps_to_max_without_vram() -> None:
    assert lmstudio.suggest_context(200_000, max_context=32_768) == 32_768
    assert lmstudio.suggest_context(8_192, max_context=262_144) == 8_192


def test_suggest_context_fits_to_vram() -> None:
    # ~5.6 GB Q4 9B + limited free VRAM → the context cannot be 200k.
    fitted = lmstudio.suggest_context(
        200_000,
        max_context=262_144,
        size_bytes=5_629_108_499,
        params_b=9.0,
        free_vram_mb=7000,
    )
    assert fitted <= 32_768
    assert fitted >= lmstudio.JIT_CONTEXT


def test_suggest_context_tiny_vram_falls_to_jit() -> None:
    fitted = lmstudio.suggest_context(
        65_536,
        max_context=262_144,
        size_bytes=5_629_108_499,
        params_b=9.0,
        free_vram_mb=5200,  # barely room for the model
    )
    assert fitted == lmstudio.JIT_CONTEXT


def test_is_local_url() -> None:
    assert lmstudio.is_local_url("http://localhost:1234/v1")
    assert lmstudio.is_local_url("http://127.0.0.1:11434/v1")
    assert not lmstudio.is_local_url("https://openrouter.ai/api/v1")
    assert not lmstudio.is_local_url(None)


def test_unload_others_keeps_selected(monkeypatch) -> None:
    kept: list[str] = []
    unloaded: list[str] = []

    models = [
        lmstudio.Model(
            key="a", name="A", max_context=8_000, vision=False, tools=True,
            instances=[lmstudio.Instance(id="i-a", context=4096)],
            size_bytes=1, params_b=1.0,
        ),
        lmstudio.Model(
            key="b", name="B", max_context=8_000, vision=False, tools=True,
            instances=[
                lmstudio.Instance(id="i-b1", context=4096),
                lmstudio.Instance(id="i-b2", context=8192),
            ],
            size_bytes=1, params_b=1.0,
        ),
    ]
    monkeypatch.setattr(lmstudio, "models", lambda _u: models)
    monkeypatch.setattr(
        lmstudio, "unload",
        lambda _u, iid: unloaded.append(iid) or True,
    )

    gone = lmstudio.unload_others("http://localhost:1234/v1", "a")
    assert set(gone) == {"i-b1", "i-b2"}
    assert "i-a" not in unloaded


def test_local_optimize_forces_max_calls(tmp_path, monkeypatch) -> None:
    from dornick import settings
    from dornick.config import Config

    monkeypatch.setattr("dornick.automode.verify_key", lambda _a: "ok")
    cfg = Config(workspace=tmp_path, state_dir=tmp_path / ".dornick")
    cfg.ensure_dirs()
    updated = settings.apply(cfg, {
        "provider": "lmstudio",
        "model": {"local_optimize": True, "name": "qwen"},
    })
    assert updated.model.local_optimize is True
    assert updated.model.max_calls == 1
