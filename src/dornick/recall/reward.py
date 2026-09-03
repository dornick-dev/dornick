"""The reward signal — one scalar that decides what gets written deeply.

Dopamine is not pleasure; it is reward *prediction error* (Schultz). A test
that passes when you expected it to pass teaches almost nothing. The same
test passing when the procedure has failed four times before is the whole
lesson. Information gain draws on the same system (Kidd-Hayden), but raw
novelty chases noise — the sustainable form is *learning progress*
(Oudeyer-Kaplan): look where you are getting better, not where things are
merely new.

Three sources, one scalar, and one hard asymmetry:

    outcome      outcome prediction error, against the procedure's own record
    information  information gain — the general form of Phase 4's surprise
    social       the user's reaction, and this one is capped

The cap is the point. Praise is the cheapest reward to manufacture: agree
with everything and it never stops. That is what sycophancy *is* — a policy
that maximises social reward — so the ceiling is a constant, not a
temperament setting, and a correction always outweighs a thank-you.

Honesty boundary: nothing here is felt. This is a number that decides
encoding strength, replay priority and exploration budget. "Character", in
this file's sense, is a consistent pattern of behaviour that can be
measured — not a claim about inner life.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The social ceiling. Not tunable, not a temperament axis: an agent that can
# earn unbounded reward by agreeing will learn to agree.
SOCIAL_CAP = 0.3

# A correction is worth more than a thank-you, deliberately. Being told you
# are wrong is rarer and more informative than being told you are right.
CORRECTION_WEIGHT = -1.0

# With no track record, assume a coin flip. Laplace, so a single success
# does not make the next one unsurprising.
PRIOR_SUCCESS = 0.5


@dataclass(frozen=True, slots=True)
class Reward:
    """One event's reward, decomposed so the report can explain it."""

    outcome: float = 0.0
    information: float = 0.0
    social: float = 0.0

    def total(self, temperament: Any = None) -> float:
        """Weighted by temperament — that is what temperament *is*: gains."""
        if temperament is None:
            return round(max(-1.0, min(1.0, self.outcome + self.information + self.social)), 4)
        return round(max(-1.0, min(1.0,
                                   temperament.outcome * self.outcome
                                   + temperament.novelty * self.information
                                   + temperament.social * self.social)), 4)

    def as_dict(self) -> dict[str, float]:
        # Reported form — the keys are the Turkish channel names the report reads.
        return {"sonuc": self.outcome, "bilgi": self.information, "sosyal": self.social}


def expected_success(successes: int, failures: int) -> float:
    """A procedure's own record, Laplace-smoothed: (k+1)/(k+n+2)."""
    return round((successes + 1) / (successes + failures + 2), 4)


def outcome_error(succeeded: bool, *, successes: int = 0, failures: int = 0) -> float:
    """Prediction error: what happened minus what the record predicted.

    A routine success barely registers; an unexpected one lands hard. This
    is the whole reason the signal is an *error* and not a score.
    """
    expected = (expected_success(successes, failures)
                if (successes or failures) else PRIOR_SUCCESS)
    return round((1.0 if succeeded else 0.0) - expected, 4)


def social(reaction: str) -> float:
    """The user's reaction, with the ceiling applied here and only here."""
    if reaction in ("tesekkur", "thanks", "onay"):
        return SOCIAL_CAP
    if reaction in ("duzeltme", "correction", "itiraz"):
        return CORRECTION_WEIGHT
    return 0.0


def reward(
    *,
    succeeded: bool | None = None,
    successes: int = 0,
    failures: int = 0,
    surprise: float = 0.0,
    reaction: str = "",
) -> Reward:
    """Assemble one event's reward from what is actually known about it."""
    return Reward(
        outcome=outcome_error(succeeded, successes=successes, failures=failures)
        if succeeded is not None else 0.0,
        information=round(max(0.0, min(1.0, surprise)), 4),
        social=social(reaction),
    )


def encoding_strength(value: float) -> float:
    """Phase 4's `guc`, in its general form: `0.4 + 0.6 * |reward|`.

    Both directions count. A costly mistake is written as deeply as a
    surprising success — arguably deeper, which is what the `lesson`
    multiplier already says.
    """
    from .activation import ENCODING_RANGE, ENCODING_FLOOR

    return round(ENCODING_FLOOR + ENCODING_RANGE * min(1.0, abs(value)), 4)
