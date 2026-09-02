"""Zihin katmanı.

Ajanın kendi geçmişini, bilgisini ve hedeflerini gezinebileceği yüzey.
Depo `store.Mind`, ajana açılan araçlar `tools.register`.

Aynı depo ileride MCP sunucusu olarak da açılacak; o zaman dışarıdaki
ajanlar da (Claude Code dahil) aynı zihni okuyabilecek.
"""

from __future__ import annotations

from pathlib import Path

from ..recall.saat import Saat
from .store import Episode, Goal, Memory, Mind
from .tools import register

__all__ = ["Episode", "Goal", "Memory", "Mind", "open_mind", "register"]


def open_mind(
    mind_dir: Path,
    sessions_dir: Path,
    session_id: str = "",
    *,
    saat: Saat | None = None,
) -> Mind:
    """Zihni açar. `saat` verilmezse duvar saati (bkz. recall/saat.py)."""
    return Mind(mind_dir=mind_dir, sessions_dir=sessions_dir,
                session_id=session_id, saat=saat)
