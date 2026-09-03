"""Makine GPU belleği — yerel LLM bağlamını sığdırmak için.

Harici bağımlılık yok: `nvidia-smi` varsa okunuyor, yoksa boş liste.
CUDA/Whisper ile karışmasın diye `listen` içinde değil burada.

`cuda_libs_on_path`: pip `nvidia-*` paketlerinin DLL klasörlerini
Windows arama yoluna ekler. Whisper (ctranslate2) ve kamera analizi
(onnxruntime) aynı DLL'leri arıyor.
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
    """Testlerin sahte nvidia-smi görmesi için."""
    global _gpu_at, _gpu_rows
    _gpu_at, _gpu_rows = 0.0, None


def nvidia_gpus() -> list[GpuMemory]:
    """`nvidia-smi` CSV çıktısı. Sürücü yoksa / komut yoksa [].

    Kamera güvertesi bu listeyi sık soruyor; her istekte nvidia-smi
    (4 sn timeout) HTTP iş parçacığını kilitliyordu. 20 sn önbellek.
    """
    global _gpu_at, _gpu_rows
    now = time.monotonic()
    if _gpu_rows is not None and now - _gpu_at < _GPU_TTL:
        return _gpu_rows
    rows = _read_nvidia_gpus()
    _gpu_at, _gpu_rows = now, rows
    return rows


def _read_nvidia_gpus() -> list[GpuMemory]:
    """`nvidia-smi` CSV çıktısı. Sürücü yoksa / komut yoksa []."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        from . import environment

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
    """İlk GPU'nun boş VRAM'i (MB). Yoksa None."""
    gpus = nvidia_gpus()
    return gpus[0].free_mb if gpus else None


def cuda_libs_on_path() -> bool:
    """pip `nvidia-*` DLL klasörlerini Windows arama yoluna ekler.

    Windows'ta ctranslate2 / onnxruntime CUDA kütüphanelerini DLL
    yolundan arıyor ve pip ile kurulan `nvidia-*` paketleri onları
    site-packages içine koyuyor — yani varsayılan olarak bulunamıyorlar.
    Klasörler burada tanıtılıyor; yoksa "cublas64_12.dll bulunamadı"
    diye ilk kullanımda patlıyor.

    İki yol birden gerekiyor. `add_dll_directory` yalnızca arama
    bayrağı kullanan yüklemelerde işe yarıyor; ctranslate2 düz
    `LoadLibrary` çağırdığı için klasörün PATH'te de olması şart.
    """
    if not hasattr(os, "add_dll_directory"):  # Windows dışı: sistem yolu yeter
        return True

    try:
        import nvidia
    except ImportError:
        # Kart var ama kütüphaneler yok. Sistemde CUDA kurulu olabilir.
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
