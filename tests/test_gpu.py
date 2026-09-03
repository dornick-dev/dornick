"""The GPU measurement must not open a console window."""

from __future__ import annotations

import pytest

from dornick import gpu, environment


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    gpu._cache_clear()
    yield
    gpu._cache_clear()


def test_nvidia_gpus_uses_create_no_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Saving settings / measuring VRAM must not flash a black cmd via nvidia-smi."""
    seen: dict = {}

    def capture(*_a, **kwargs):
        seen.update(kwargs)
        return "GPU,8192,4096,4096\n"

    monkeypatch.setattr(gpu.shutil, "which", lambda _n: "nvidia-smi")
    monkeypatch.setattr(gpu.subprocess, "check_output", capture)
    rows = gpu.nvidia_gpus()
    assert len(rows) == 1
    assert rows[0].name == "GPU"
    for key, val in environment.quiet_flags().items():
        assert seen.get(key) == val


def test_nvidia_gpus_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """The camera deck asked for the list every 1.5 s; each time nvidia-smi
    could lock the HTTP thread for 4 s."""
    n = {"n": 0}

    def capture(*_a, **_k):
        n["n"] += 1
        return "GPU,8192,4096,4096\n"

    monkeypatch.setattr(gpu.shutil, "which", lambda _n: "nvidia-smi")
    monkeypatch.setattr(gpu.subprocess, "check_output", capture)
    assert gpu.nvidia_gpus()[0].name == "GPU"
    assert gpu.nvidia_gpus()[0].free_mb == 4096
    assert n["n"] == 1
