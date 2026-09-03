"""Time-based activation — how alive a trace is right now.

The previous version counted `uses`, and a count knows nothing about time: a
record written three hundred days ago was as strong as yesterday's, and a
heavily used old record could keep a fresh correction out of the soul. A
counter is not a model of remembering, it is a statistic.

The formula here is ACT-R's base-level equation, in its weighted form:

    B = ln( Σ w_k · t_k^(-d) )

`t_k` is the time elapsed since each use, `d` the decay exponent, `w_k` the
weight of that use. It gives four things at once:

    recency      a recent use contributes a lot
    frequency    every use adds a separate term to the sum
    spacing      the same number of uses spread over time leaves a stronger
                 trace (the spaced-repetition effect) — bunched uses all
                 age at the same moment
    accountability
                 the weight may be negative: a use that led to a failure
                 weakens the trace (Phase 3 reverse replay). In Phase 1 every
                 weight is 1.0 and the formula reduces to classic ACT-R.

Invariant: **nothing is lost.** "Forgetting" here means the activation drops
below a threshold; the record stays on disk and stays findable by explicit
search. That is why the seeding factor drops to a half, not to zero
(`SEED_FLOOR`): even the most forgotten record keeps half of its score — it
falls behind, it does not vanish. Even when the weighted sum goes below zero
(failures only) a constant floor is returned — the memory that led to a
failure is not erased either; it stays behind with a `lesson` next to it.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence

from . import switches
from .clock import parse

# Decay exponent. The standard value in the ACT-R literature is 0.5, and that
# value was fitted to laboratory data on the scale of seconds to minutes;
# here `t` is measured in hours across months, and in that regime 0.5 is too
# slow: a week-old correction stayed below a procedure that had been used
# regularly for months.
# Calibration (life bench, 2026-09-02, `--etiket f1`): 0.5 / 0.6 / 0.8 /
# 0.9 / 1.0 / 1.1 were swept. `taze_ruh` 0.68 → 0.72 → 0.78 → 0.81 → 0.82 →
# 0.83; `prime_precision` peaks at 0.9 (0.2634), after 1.0 `yasak_sizinti`
# goes from 57 to 58. The knee was chosen.
# See docs/hafiza-fazlar.md "Faz 1 kalibrasyonu".
DECAY = 0.9

# `t` is measured in hours, not days: two uses on the same day, morning and
# evening, must still be distinguishable.
BASE_SECONDS = 3600.0

# Lower bound (36 seconds) that prevents division by zero and stops "used a
# moment ago" from going to infinity. Future-dated stamps are clipped here
# too — on a machine whose clock was set back, a use may appear to come from
# the future.
MIN_ELAPSED_HOURS = 0.01

# A record with no uses at all, or whose net weight has dropped below zero.
# The mathematically correct value is -infinity; a constant, since one cannot
# multiply by infinity.
NO_BASE = -10.0

# Scale of the sigmoid that squashes B into a 0..1 factor.
# Calibration (life bench, 2026-09-02): SCALE ∈ {0.75, 1.0, 1.5, 2.0, 3.0,
# 4.0, 5.0} was swept; the metrics do not separate on the 1.0–4.0 plateau
# (difference ≤ 0.002), the extremes are slightly worse. The calibration's
# own finding is this: the results are INSENSITIVE to this constant — the
# benefit of the mechanism comes from the ranking knowing about time, not
# from the steepness of the sigmoid. The middle of the plateau was chosen.
SCALE = 2.0

# The share of the seeding score that stays independent of activation. 0.5:
# even the most forgotten record keeps half of its score. Had it been zero,
# old records would have dropped out of search entirely — a violation of the
# tombstone philosophy.
SEED_FLOOR = 0.5

# Maximum number of stamps kept in the use history (roadmap 1.1). The column
# must not grow without bound; terms beyond thirty uses do not change the sum
# appreciably — the oldest ones already contribute the least.
MAX_USES = 30

# Use labels. Phase 1 writes only the first two; the rest belong to Phase 3
# (reverse replay, schema refresh, capture) and Phase 4. The field is opened
# in this shape from the start so later phases do not change the schema.
WRITTEN = "yazildi"
OPENED = "acildi"
SUCCESS = "basari"
FAILURE = "hata"
SCHEMA = "sema"
CAPTURED = "yakalandi"
# Distillation source: its essence was moved into a short `fact`, itself
# pulled into the background. It needs its own label — had it counted as
# `sema`, the measurement of schema refresh would have been confused with the
# pull-back of distillation (measured: `sema_tazeleme` went negative).
DISTILLED = "damitildi"
LABELS = (WRITTEN, OPENED, SUCCESS, FAILURE, SCHEMA, CAPTURED, DISTILLED)


@dataclass(frozen=True, slots=True)
class Use:
    """One moment at which a trace woke up."""

    t: datetime
    w: float = 1.0
    etiket: str = OPENED

    def as_dict(self) -> dict[str, Any]:
        return {"t": self.t.isoformat(timespec="milliseconds"),
                "w": round(self.w, 4), "etiket": self.etiket}


def base_activation(use_log: Sequence[Use], now: datetime) -> float:
    """B = ln( Σ w_k · t_k^(-d) ). `NO_BASE` if the sum is ≤ 0."""
    total = 0.0
    for k in use_log:
        elapsed = max((now - k.t).total_seconds() / BASE_SECONDS, MIN_ELAPSED_HOURS)
        total += k.w * elapsed ** (-DECAY)
    return math.log(total) if total > 0.0 else NO_BASE


def activation_factor(b: float) -> float:
    """Squashes B into the (0, 1) interval: sigmoid(B / SCALE)."""
    x = max(-60.0, min(60.0, b / SCALE))
    return 1.0 / (1.0 + math.exp(-x))


def seed_factor(b: float) -> float:
    """The seeding score is multiplied by this: between `SEED_FLOOR` and 1.

    1.0 while the mechanism is switched off — the ablation run must go
    through the product's own code, not through an "activation-less version"
    copied into the bench.
    """
    if not switches.ACTIVE.activation:
        return 1.0
    return SEED_FLOOR + (1.0 - SEED_FLOOR) * activation_factor(b)


def spread_factor(b: float) -> float:
    """The share a neighbour passes on while association spreads.

    NO floor here: a forgotten node should not conduct the path. This does
    not contradict keeping half in seeding — there the record ITSELF is
    being searched for, here it is merely being passed through.
    """
    if not switches.ACTIVE.activation:
        return 1.0
    return activation_factor(b)


# -- on-disk format ----------------------------------------------------


def parse_use_log(
    raw: Any,
    *,
    created: str | None = None,
    last_used: str | None = None,
    uses: int = 0,
) -> list[Use]:
    """Turns the on-disk use history into something readable.

    It has to be robust to three formats at once:

    * the weighted entries this version writes (`{"t", "w", "etiket"}`),
    * a plain list of ISO stamps (a memory written before the format changed),
    * an old memory where the column never existed — then it is roughly
      back-filled from `created` + `last_used` × `uses`.

    The third is mandatory: if adding the column made every old memory count
    as "never used" all at once, the memory a user accumulated over years
    would behave as if it had been reset by a single version upgrade.
    """
    entries = _entries(raw)
    if entries:
        return entries
    return _backfill(created, last_used, uses)


def _entries(raw: Any) -> list[Use]:
    if isinstance(raw, str):
        if not raw.strip():
            return []
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, list):
        return []
    out: list[Use] = []
    for entry in raw:
        if isinstance(entry, dict):
            moment = parse(entry.get("t") if isinstance(entry.get("t"), str) else None)
            if moment is None:
                continue
            try:
                w = float(entry.get("w", 1.0))
            except (TypeError, ValueError):
                w = 1.0
            label = str(entry.get("etiket") or OPENED)
            out.append(Use(moment, w, label))
        elif isinstance(entry, str):
            if (moment := parse(entry)) is not None:
                out.append(Use(moment, 1.0, OPENED))
    out.sort(key=lambda k: k.t)
    return out


def _backfill(created: str | None, last_used: str | None,
              uses: int) -> list[Use]:
    """Rough use history of a record that has no column.

    The moment of writing is the first use; the remaining `uses` are piled
    onto the moment of last use. The real distribution is unknown — rather
    than inventing the unknown, the most conservative assumption: they all
    happened at once (bunched use leaves a weaker trace than spaced use).
    """
    out: list[Use] = []
    if (written := parse(created)) is not None:
        out.append(Use(written, 1.0, WRITTEN))
    if (last := parse(last_used)) is not None:
        remaining = max(0, min(int(uses or 0), MAX_USES - len(out)))
        out.extend(Use(last, 1.0, OPENED) for _ in range(remaining))
    out.sort(key=lambda k: k.t)
    return out


def encode(use_log: Iterable[Use]) -> str:
    """JSON to be written to disk. The last `MAX_USES` entries are kept."""
    items = list(use_log)[-MAX_USES:]
    return json.dumps([k.as_dict() for k in items], ensure_ascii=False)


def append_use(use_log: Iterable[Use], moment: datetime, *, w: float = 1.0,
         etiket: str = OPENED) -> str:
    """Appends a new use to the history and returns the JSON to write to disk."""
    return encode([*use_log, Use(moment, float(w), etiket)])


# Phase 4 — encoding strength. Every record used to be born with the same
# weight: when "I saved the same thing five times" was said, the fifth record
# was at full strength too. Strength now comes from surprise — what resembles
# the known is encoded weakly, what is new is encoded strongly. The floor is
# never zero: hearing a known thing again is information too.
ENCODING_FLOOR = 0.4
ENCODING_RANGE = 0.6
# Learning from failure weighs more: the same body is encoded more strongly
# as a `lesson`.
LESSON_FACTOR = 1.5


def encoding_strength(surprise: float, *, kind: str = "fact",
                 supersedes: str = "") -> float:
    """Birth weight of a new record.

    `supersedes` gets full strength: a correction must not be encoded weakly
    however much it resembles what it corrects — it is a correction precisely
    because it resembles it.
    """
    if not switches.ACTIVE.encoding:
        return 1.0
    if supersedes:
        return 1.0
    strength = ENCODING_FLOOR + ENCODING_RANGE * max(0.0, min(1.0, surprise))
    if kind == "lesson":
        strength = min(1.0, strength * LESSON_FACTOR)
    return round(strength, 4)


def first_stamp(created: str, strength: float = 1.0) -> str:
    """Use history of a new record: the moment of writing is the first use.

    The weight is the encoding strength (Phase 4): `base_activation` already
    takes a weighted sum, so the schema does not change — only the `w` of the
    first entry does.
    """
    return json.dumps([{"t": created, "w": round(float(strength), 4),
                        "etiket": WRITTEN}], ensure_ascii=False)


def track_record(use_log: Sequence[Use]) -> tuple[int, int]:
    """(successes, failures) counter — shown to the model in `mind_recall` output."""
    successes = sum(1 for k in use_log if k.etiket == SUCCESS)
    failures = sum(1 for k in use_log if k.etiket == FAILURE)
    return successes, failures
