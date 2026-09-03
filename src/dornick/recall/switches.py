"""On/off switches for the memory mechanisms.

Their only purpose is measurement: the life benchmark
(eval/context_memory/life_bench.py) must be able to switch each mechanism off
one by one and produce a Pareto table. If switching a mechanism off breaks no
metric, that mechanism has not earned its complexity and gets removed — this
file makes that decision measurable.

The switches are **process-wide** and default to on: product behaviour is
identical to what it was before this module was added. Only the benchmark
changes the settings; there is no `configure()` call in product code.

Why it lives in product code rather than in the bench: the measured path must
be the product's own path. An "activation-less version" copied into the bench
silently drifts and what gets measured is no longer the product (see
scale_bench.py's parametric copy-equality check, same reasoning).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, fields, replace
from typing import Iterator


@dataclass(frozen=True, slots=True)
class Switches:
    """Which mechanism is on. All on by default."""

    # Phase 1 — time-based activation (ACT-R base level).
    activation: bool = True
    # Phase 2 — supersede: dropping the old version of an updated record from seeding.
    supersede: bool = True
    # Phase 3 — night consolidation: re-weaving and distillation.
    weave: bool = True
    distillation: bool = True
    # Phase 4 — encoding strength (surprise).
    encoding: bool = True
    # Phase 5 — context bonus.
    context: bool = True


ACTIVE = Switches()

# The names the bench accepts for its `--disable` flag. Read from a single
# source so an unknown name is not swallowed silently.
NAMES: tuple[str, ...] = tuple(f.name for f in fields(Switches))


def configure(**disabled: bool) -> None:
    """Changes the switches process-wide. For measurement only."""
    global ACTIVE
    unknown = set(disabled) - set(NAMES)
    if unknown:
        raise ValueError(f"Bilinmeyen mekanik: {', '.join(sorted(unknown))}")
    ACTIVE = replace(ACTIVE, **disabled)


def reset() -> None:
    """Returns everything to the default (on)."""
    global ACTIVE
    ACTIVE = Switches()


@contextmanager
def disabled(*names: str) -> Iterator[Switches]:
    """Switches the given mechanisms off for the block, back on at exit."""
    global ACTIVE
    previous = ACTIVE
    try:
        configure(**{name: False for name in names})
        yield ACTIVE
    finally:
        ACTIVE = previous
