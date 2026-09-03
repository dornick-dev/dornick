"""Recall protocol.

The single contract for accessing memory. Dornick itself and any other agent
connecting over MCP (Claude Code included) use the same surface.

The contract is tiered — the model does not get everything, it navigates:

    recall(query)   titles + the path activation travelled
    open(id)        full record; strengthens the trace
    expand(id)      look at the neighbours
    remember(...)   new record, with optional links
    link(a, b)      establish an association
    forget(id)      leave a tombstone

`recall` returns not only results but also the **trace**: which node woke
from which node, in what order. When the UI animates it, remembering itself
becomes visible.
"""

from __future__ import annotations

from pathlib import Path

from . import activation, switches
from .clock import Clock, wall_clock
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
    "activation",
    "switches",
    "Clock",
    "wall_clock",
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
    clock: Clock | None = None,
) -> RecallStore:
    """Opens the memory. Wall clock if `clock` is not given (see clock.py)."""
    return RecallStore(directory / "recall.db", cache_bytes=cache_bytes, clock=clock)
