"""Curiosity — where the agent looks when nobody asked it to.

Raw novelty is a bad objective: it chases noise, and noise is infinite. The
sustainable form is **learning progress** (Oudeyer-Kaplan) — look where you
have been getting better lately, not where things are merely new. Multiply
that by whether the user has touched the area at all, and the loop closes:
progress draws attention, attention produces competence, and "the dornick
that is into SCADA" falls out of the reward history rather than being
declared.

Two guards keep the loop from eating itself:

* **Relevance gates everything.** An area the user has not touched in a
  month gets no budget, however interesting it looks. Curiosity that leaves
  the user's world is just a background process burning their battery.
* **An entropy floor** keeps one area from taking everything. Without it the
  distribution collapses onto the first thing that worked and everything
  else withers.

And two things it will not do: go to the network (the curiosity window is
local-file only unless the user opens it), and copy file *contents* into
`world` records. Structure and metadata only — a curious agent must not
become an exfiltration path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable

# 80% of the budget follows the score, 20% is spread evenly over the lowest
# scoring areas. Without that floor the distribution collapses.
ENTROPY_FLOOR = 0.2

# The curiosity slice of a REM cycle.
CURIOSITY_MINUTES = 3

# Web access during the curiosity window. Off, and it is not a preference:
# the window runs unattended.
WEB_OPEN = False


@dataclass(slots=True)
class Area:
    """One area's numbers, all of them measured rather than assigned."""

    name: str
    earlier_error: float = 0.0    # mean |outcome error|, days 8-14
    recent_error: float = 0.0     # mean |outcome error|, last 7 days
    touches: int = 0              # how often the user went there, last 30 days

    @property
    def progress(self) -> float:
        """Learning progress: error going down is the signal, not error size."""
        return round(self.earlier_error - self.recent_error, 4)


def relevance(areas: Iterable[Area]) -> dict[str, float]:
    """Normalised user attention. Zero touches means zero budget, full stop."""
    items = list(areas)
    total = sum(a.touches for a in items)
    if not total:
        return {a.name: 0.0 for a in items}
    return {a.name: round(a.touches / total, 4) for a in items}


def scores(areas: Iterable[Area], *, novelty: float = 0.5) -> dict[str, float]:
    """`temperament.novelty × max(progress, 0) × relevance`."""
    items = list(areas)
    weight = relevance(items)
    return {a.name: round(novelty * max(a.progress, 0.0) * weight[a.name], 6)
            for a in items}


def distribution(areas: Iterable[Area], *, novelty: float = 0.5,
                 floor: float = ENTROPY_FLOOR) -> dict[str, float]:
    """Softmax over the scores, with an entropy floor on the weakest areas.

    An area the user never touches stays at zero even after the floor: the
    floor protects diversity inside the user's world, not outside it.
    """
    score = scores(areas, novelty=novelty)
    relevant = {name: p for name, p in score.items() if p > 0.0}
    if not relevant:
        return {name: 0.0 for name in score}

    top = max(relevant.values())
    powers = {name: math.exp((p - top) * 8.0) for name, p in relevant.items()}
    total = sum(powers.values())
    soft = {name: v / total for name, v in powers.items()}

    # The floor is spread over the lowest-scoring RELEVANT areas.
    ranked = sorted(relevant, key=lambda name: relevant[name])
    slice_ = ranked[:max(1, len(ranked) // 2)]
    out = {name: 0.0 for name in score}
    for name, share in soft.items():
        out[name] = (1 - floor) * share
    for name in slice_:
        out[name] += floor / len(slice_)
    return {name: round(v, 4) for name, v in out.items()}


def entropy(dist: dict[str, float]) -> float:
    """Normalised entropy of the distribution. The collapse alarm."""
    shares = [p for p in dist.values() if p > 0]
    if len(shares) <= 1:
        return 0.0
    total = sum(shares)
    shares = [p / total for p in shares]
    h = -sum(p * math.log(p) for p in shares)
    return round(h / math.log(len(shares)), 4)


def allowed_actions(*, has_model: bool, web: bool = WEB_OPEN) -> list[str]:
    """What the curiosity window may do. The list is short on purpose.

    Nothing here reads file contents into memory: a `world` record gets the
    structure (which files, which test command, which README heading), never
    the text inside the user's files.
    """
    allowed = ["dizin_yapisi", "test_komutu_kaniti", "kirilan_test_gecmisi"]
    if has_model:
        allowed.append("arac_dokumani_ozeti")
    if web:
        allowed.append("web")
    return allowed


def picks(areas: Iterable[Area], *, novelty: float = 0.5) -> list[str]:
    """Areas in the order curiosity would visit them."""
    dist = distribution(areas, novelty=novelty)
    return [name for name, share in sorted(dist.items(), key=lambda kv: -kv[1]) if share > 0]
