"""Hatırlama protokolü.

Belleğe erişimin tek sözleşmesi. Dornick'in kendisi de, MCP üzerinden
bağlanan başka bir ajan da (Claude Code dahil) aynı yüzeyi kullanır.

Sözleşme kademeli — model her şeyi almaz, gezinir:

    recall(sorgu)   başlıklar + aktivasyonun uğradığı yol
    open(kimlik)    tam kayıt; izi güçlendirir
    expand(kimlik)  komşulara bak
    remember(...)   yeni kayıt, isteğe bağlı bağlarla
    link(a, b)      çağrışım kur
    forget(kimlik)  mezar taşı bırak

`recall` yalnızca sonuç değil **iz** de döndürüyor: hangi düğüm hangi
düğümden uyandı, hangi sırayla. Arayüz bunu canlandırınca hatırlamanın
kendisi görünür oluyor.
"""

from __future__ import annotations

from pathlib import Path

from .saat import Saat, duvar_saati
from .store import (
    DEFAULT_CACHE_BYTES,
    KINDS,
    Node,
    Recollection,
    RecallStore,
    Step,
)

__all__ = [
    "DEFAULT_CACHE_BYTES",
    "Saat",
    "duvar_saati",
    "KINDS",
    "Node",
    "RecallStore",
    "Recollection",
    "Step",
    "open_store",
]


def open_store(
    directory: Path,
    *,
    cache_bytes: int = DEFAULT_CACHE_BYTES,
    saat: Saat | None = None,
) -> RecallStore:
    """Belleği açar. `saat` verilmezse duvar saati (bkz. saat.py)."""
    return RecallStore(directory / "recall.db", cache_bytes=cache_bytes, saat=saat)
