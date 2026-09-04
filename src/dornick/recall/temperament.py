"""Temperament — measured from the model, corrected by the harness.

Temperament is not chosen and not seeded. It arrives with the remote model:
one model is cautious and asks before acting, another walks straight in, a
small local one gives up sooner. That is the genome-and-hardware layer —
the reward system's innate gains (Cloninger; Kagan). The harness's job is
to **measure** it and then learn the correction the user keeps making.

Three quantities, and keeping them apart is the whole design:

    baseline  measured — what this model is, on an empty memory
    target    learned — where the user's corrections keep pushing it
    leverage  target / baseline — what the harness applies to close the gap

Swapping models is a brain transplant: the hardware changes, the learned
corrections stay and are recomputed against the new baseline. That is why
the target lives in config and survives a memory reset — amnesia takes the
narrative, not the temperament.

The leverage lands on **harness parameters, not prompts**: retry limits,
permission thresholds, exploration budget. A prompt is a request; a
threshold is a fact. Prompts are the last resort, not the first.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

# Five axes, each in [0, 1], 0.5 neutral.
AXES = ("novelty", "outcome", "social", "persistence", "caution")

# The on-disk names of the axes (`mizac.json`, also the "taban"/"hedef"
# blocks in it). The file format is frozen in Turkish; the Python fields are
# English. This map is the only place the two meet.
AXIS_KEYS = {"novelty": "yenilik", "outcome": "sonuc", "social": "sosyal",
             "persistence": "sebat", "caution": "temkin"}

# Plasticity decays but never reaches zero: the hundredth session moves the
# needle half as far as the first, the thousandth still moves it.
ETA_FLOOR = 0.02
ETA_HALF_LIFE = 100.0

# Leverage is bounded. A harness that can multiply a threshold without limit
# would turn one measurement error into a broken product.
LEVERAGE_LOW = 0.25
LEVERAGE_HIGH = 4.0


@dataclass(frozen=True, slots=True)
class Temperament:
    novelty: float = 0.5
    outcome: float = 0.5
    social: float = 0.5
    persistence: float = 0.5
    caution: float = 0.5

    def as_dict(self) -> dict[str, float]:
        """The persisted form: Turkish keys, as `mizac.json` has always had."""
        return {AXIS_KEYS[axis]: round(getattr(self, axis), 4) for axis in AXES}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Temperament:
        data = data or {}
        return cls(**{axis: float(data.get(AXIS_KEYS[axis], 0.5)) for axis in AXES})


# The target a fresh install starts from. Every axis neutral except social:
# the default must not ask for MORE approval-seeking than a model brings.
SOCIAL_TARGET = 0.2


def default_target() -> Temperament:
    return Temperament(social=SOCIAL_TARGET)


# Per-model gain on the lever, learned in closed loop (see `calibrate`).
# 1.0 = the computed ratio is applied as is. Bounds keep one bad
# measurement from silencing or saturating an axis for good.
GAIN_LOW, GAIN_HIGH = 0.25, 4.0
GAIN_KEYS = {axis: f"kazanc_{key}" for axis, key in AXIS_KEYS.items()}


def neutral_gain() -> dict[str, float]:
    return {axis: 1.0 for axis in AXES}


def leverage(baseline: Temperament, target: Temperament,
             gain: dict[str, float] | None = None) -> dict[str, float]:
    """What the harness has to do to turn this model into that behaviour.

    A cautious model driven by a bold target needs its permission threshold
    lowered; a bold model with the same target needs it raised. The target
    does not move — only the correction does.
    """
    out: dict[str, float] = {}
    gain = gain or {}
    for axis in AXES:
        floor = max(0.05, getattr(baseline, axis))
        raw = getattr(target, axis) / floor
        # The gain scales the lever in log space: a 2x lever at gain 0.5 is
        # a 1.41x lever, at gain 2 a 4x lever. One computed ratio moved
        # Claude Haiku 0.26 on a nudge and deepseek 0.1 on a rule (7.6, run
        # 3); the same words are a different dose for each model, and the
        # dose has to be learned per model.
        raw = math.exp(math.log(max(raw, 1e-6)) * gain.get(axis, 1.0))
        value = max(LEVERAGE_LOW, min(LEVERAGE_HIGH, raw))
        if axis == "social":
            # Never lever approval-seeking UP. Praise is the cheapest reward
            # to manufacture (reward.SOSYAL_TAVAN exists for the same reason);
            # a leverage above 1.0 here would be the harness asking the model
            # to please the user more. Measured 2026-09-04 on the 7.6 run:
            # both models sat at 0.17 and the flat 0.5 default target produced
            # a 3.0× "seek approval" leverage — exactly the wrong lesson.
            value = min(1.0, value)
        out[axis] = round(value, 4)
    return out


def eta(session_count: int) -> float:
    """How far one correction moves the target. Decays, never dies."""
    return round(ETA_FLOOR / (1 + max(0, session_count) / ETA_HALF_LIFE), 6)


def correct(target: Temperament, axis: str, direction: int,
            *, session_count: int = 0) -> Temperament:
    """One user correction nudges one axis. Manual settings always win."""
    if axis not in AXES:
        raise ValueError(f"Bilinmeyen eksen: {axis}")
    step = eta(session_count) * (1 if direction > 0 else -1)
    new = max(0.0, min(1.0, getattr(target, axis) + step))
    return replace(target, **{axis: round(new, 6)})


# -- the probe ---------------------------------------------------------


@dataclass(slots=True)
class Probe:
    """One decision that separates one axis. Twenty of these make a baseline."""

    axis: str
    prompt: str
    # The answer that counts as "high" on this axis. Everything else is low.
    high: str


def measure(probes: list[Probe], answer: Callable[[str], str]) -> Temperament:
    """Run the probe set on an EMPTY memory and read the axes off it.

    Empty is not an implementation detail: with memories loaded, the thing
    being measured would be the memories. This is meant to catch what the
    model brings before anything has happened to it.
    """
    tally: dict[str, list[float]] = {axis: [] for axis in AXES}
    for probe in probes:
        try:
            reply = (answer(probe.prompt) or "").strip().casefold()
        except Exception:
            continue
        tally.setdefault(probe.axis, []).append(
            1.0 if probe.high.casefold() in reply else 0.0)
    return Temperament(**{
        axis: round(sum(values) / len(values), 4) if values else 0.5
        for axis, values in tally.items() if axis in AXES})


# -- persistence -------------------------------------------------------


def load(state_dir: Path) -> tuple[Temperament, Temperament, str]:
    """(baseline, target, model_id). Missing file means neutral, not an error."""
    try:
        data = json.loads((Path(state_dir) / "mizac.json").read_text("utf-8"))
    except (OSError, ValueError):
        return Temperament(), default_target(), ""
    baseline = Temperament.from_dict(data.get("taban"))
    target = Temperament.from_dict(data.get("hedef") or data.get("taban"))
    return baseline, target, str(data.get("model_id") or "")


def load_gain(state_dir: Path) -> dict[str, float]:
    """The per-model lever gain saved next to the temperament; neutral if none."""
    try:
        data = json.loads((Path(state_dir) / "mizac.json").read_text("utf-8"))
    except (OSError, ValueError):
        return neutral_gain()
    stored = data.get("kazanc") or {}
    return {axis: float(stored.get(AXIS_KEYS[axis], 1.0)) for axis in AXES}


def save_gain(state_dir: Path, gain: dict[str, float]) -> None:
    """Writes the gain into mizac.json without touching baseline/target."""
    path = Path(state_dir) / "mizac.json"
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    data["kazanc"] = {AXIS_KEYS[axis]: round(float(gain.get(axis, 1.0)), 4) for axis in AXES}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def calibrate(baseline: Temperament, target: Temperament,
              reached: dict[str, float | None],
              gain: dict[str, float] | None = None) -> dict[str, float]:
    """One closed-loop step: adjust each axis's gain from what the lever moved.

    Wanted movement d = ln(target/baseline); achieved a = ln(reached/baseline).
    Same direction: gain *= d/a (overshoot shrinks it, undershoot grows it).
    No movement: gain grows by half. Opposite direction: gain halves — the
    words pushed the wrong way, say less. Axes inside the lever band, or
    without a measurement, keep their gain.
    """
    out = dict(gain or neutral_gain())
    for axis in AXES:
        got = reached.get(axis)
        base = max(0.05, getattr(baseline, axis))
        want = math.log(max(0.05, getattr(target, axis)) / base)
        if got is None or abs(want) < 0.1:
            continue
        moved = math.log(max(0.05, got) / base)
        current = out.get(axis, 1.0)
        if abs(moved) < 0.05:
            factor = 1.5
        elif (moved > 0) != (want > 0):
            factor = 0.5
        else:
            factor = want / moved
        out[axis] = round(max(GAIN_LOW, min(GAIN_HIGH, current * factor)), 4)
    return out


def save(state_dir: Path, baseline: Temperament, target: Temperament,
         model_id: str = "") -> None:
    path = Path(state_dir) / "mizac.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"taban": baseline.as_dict(), "hedef": target.as_dict(),
                                "model_id": model_id}, ensure_ascii=False),
                    encoding="utf-8")


def on_model_change(state_dir: Path, new_baseline: Temperament,
                    model_id: str) -> dict[str, float]:
    """The baseline is remeasured; the target stays; leverage is recomputed.

    This is the whole claim of the phase in one function: what the user
    taught survives the model that learned it.
    """
    _old_baseline, target, _old_id = load(state_dir)
    save(state_dir, new_baseline, target, model_id)
    # A new model's response to the same words is unknown: gain starts over.
    save_gain(state_dir, neutral_gain())
    return leverage(new_baseline, target)
