"""Machine GPU memory — to fit the local LLM context.

No external dependency: read from `nvidia-smi` when present, otherwise an
empty list. Lives here rather than inside `listen` so it does not get
tangled with CUDA/Whisper.

`cuda_libs_on_path`: adds the DLL folders of the pip `nvidia-*` packages
to the Windows search path. Whisper (ctranslate2) and the camera analysis
(onnxruntime) look for the same DLLs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class GpuMemory:
    name: str
    total_mb: int
    free_mb: int
    used_mb: int


_GPU_TTL = 20.0
_gpu_at = 0.0
_gpu_rows: list[GpuMemory] | None = None


def _cache_clear() -> None:
    """So tests can see a fake nvidia-smi."""
    global _gpu_at, _gpu_rows
    _gpu_at, _gpu_rows = 0.0, None


def nvidia_gpus() -> list[GpuMemory]:
    """`nvidia-smi` CSV output. No driver / no command → [].

    The camera deck asks for this list often; running nvidia-smi (4 s
    timeout) on every request was locking the HTTP thread. 20 s cache.
    """
    global _gpu_at, _gpu_rows
    now = time.monotonic()
    if _gpu_rows is not None and now - _gpu_at < _GPU_TTL:
        return _gpu_rows
    rows = _read_nvidia_gpus()
    _gpu_at, _gpu_rows = now, rows
    return rows


def _read_nvidia_gpus() -> list[GpuMemory]:
    """`nvidia-smi` CSV output. No driver / no command → []."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        from . import environment

        # CREATE_NO_WINDOW: saving settings / measuring local-opt VRAM was
        # flashing a black cmd window on every nvidia-smi call.
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,memory.used",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            timeout=4,
            text=True,
            encoding="utf-8",
            errors="replace",
            **environment.quiet_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return []

    out: list[GpuMemory] = []
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            out.append(
                GpuMemory(
                    name=parts[0],
                    total_mb=int(float(parts[1])),
                    free_mb=int(float(parts[2])),
                    used_mb=int(float(parts[3])),
                )
            )
        except ValueError:
            continue
    return out


def primary_free_mb() -> int | None:
    """Free VRAM of the first GPU (MB). None when there is none."""
    gpus = nvidia_gpus()
    return gpus[0].free_mb if gpus else None


def cuda_libs_on_path() -> bool:
    """Adds the pip `nvidia-*` DLL folders to the Windows search path.

    On Windows ctranslate2 / onnxruntime look for the CUDA libraries on the
    DLL path, and the pip-installed `nvidia-*` packages put them inside
    site-packages — so by default they cannot be found. The folders are
    registered here; otherwise the first use blows up with
    "cublas64_12.dll not found".

    Both routes are needed at once. `add_dll_directory` only works for loads
    that use the search flag; ctranslate2 calls plain `LoadLibrary`, so the
    folder must also be on PATH.
    """
    if not hasattr(os, "add_dll_directory"):  # non-Windows: the system path is enough
        return True

    try:
        import nvidia
    except ImportError:
        # Card present but libraries missing. CUDA may be installed system-wide.
        return True

    found: list[str] = []
    for parent in nvidia.__path__:
        root = Path(parent)
        for folder in root.rglob("bin"):
            if not folder.is_dir():
                continue
            found.append(str(folder))
            try:
                os.add_dll_directory(str(folder))
            except OSError:
                pass

    if found:
        path = os.environ.get("PATH", "")
        missing = [f for f in found if f not in path]
        if missing:
            os.environ["PATH"] = os.pathsep.join(missing) + os.pathsep + path
    return True
