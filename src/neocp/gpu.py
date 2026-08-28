"""Makine GPU belleği — yerel LLM bağlamını sığdırmak için.

Harici bağımlılık yok: `nvidia-smi` varsa okunuyor, yoksa boş liste.
CUDA/Whisper ile karışmasın diye `listen` içinde değil burada.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class GpuMemory:
    name: str
    total_mb: int
    free_mb: int
    used_mb: int


def nvidia_gpus() -> list[GpuMemory]:
    """`nvidia-smi` CSV çıktısı. Sürücü yoksa / komut yoksa []."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        from . import ortam

        # CREATE_NO_WINDOW: ayarlar kaydı / yerel opt VRAM ölçümü her
        # nvidia-smi'de ekranda siyah cmd parlatıyordu.
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
            **ortam.sessiz_bayraklar(),
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
    """İlk GPU'nun boş VRAM'i (MB). Yoksa None."""
    gpus = nvidia_gpus()
    return gpus[0].free_mb if gpus else None
