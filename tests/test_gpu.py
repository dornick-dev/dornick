"""GPU ölçümü konsol penceresi açtırmasın."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from neocp import gpu, ortam


def test_nvidia_gpus_uses_create_no_window() -> None:
    """Ayar kaydı / VRAM ölçümü nvidia-smi ile siyah cmd parlatmasın."""
    with patch("neocp.gpu.shutil.which", return_value="nvidia-smi"), patch(
        "neocp.gpu.subprocess.check_output", return_value="GPU,8192,4096,4096\n"
    ) as check:
        rows = gpu.nvidia_gpus()
    assert len(rows) == 1
    assert rows[0].name == "GPU"
    kwargs = check.call_args.kwargs
    for key, val in ortam.sessiz_bayraklar().items():
        assert kwargs.get(key) == val
