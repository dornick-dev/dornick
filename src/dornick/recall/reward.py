"""The reward signal — one scalar that decides what gets written deeply.

Dopamine is not pleasure; it is reward *prediction error* (Schultz). A test
that passes when you expected it to pass teaches almost nothing. The same
test passing when the procedure has failed four times before is the whole
lesson. Information gain draws on the same system (Kidd-Hayden), but raw
novelty chases noise — the sustainable form is *learning progress*
(Oudeyer-Kaplan): look where you are getting better, not where things are
merely new.

Three sources, one scalar, and one hard asymmetry:

    sonuc    outcome prediction error, against the procedure's own record
    bilgi    information gain — the general form of Faz 4's surprise
    sosyal   the user's reaction, and this one is capped

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

    sonuc: float = 0.0
    bilgi: float = 0.0
    sosyal: float = 0.0

    def total(self, temperament: Any = None) -> float:
        """Weighted by temperament — that is what temperament *is*: gains."""
        if temperament is None:
            return round(max(-1.0, min(1.0, self.sonuc + self.bilgi + self.sosyal)), 4)
        return round(max(-1.0, min(1.0,
                                   temperament.sonuc * self.sonuc
                                   + temperament.yenilik * self.bilgi
                                   + temperament.sosyal * self.sosyal)), 4)

    def as_dict(self) -> dict[str, float]:
        return {"sonuc": self.sonuc, "bilgi": self.bilgi, "sosyal": self.sosyal}


def expected_success(basari: int, hata: int) -> float:
    """A procedure's own record, Laplace-smoothed: (k+1)/(k+n+2)."""
    return round((basari + 1) / (basari + hata + 2), 4)


def outcome_error(succeeded: bool, *, basari: int = 0, hata: int = 0) -> float:
    """Prediction error: what happened minus what the record predicted.

    A routine success barely registers; an unexpected one lands hard. This
    is the whole reason the signal is an *error* and not a score.
    """
    beklenen = expected_success(basari, hata) if (basari or hata) else PRIOR_SUCCESS
    return round((1.0 if succeeded else 0.0) - beklenen, 4)


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
    basari: int = 0,
    hata: int = 0,
    surprise: float = 0.0,
    reaction: str = "",
) -> Reward:
    """Assemble one event's reward from what is actually known about it."""
    return Reward(
        sonuc=outcome_error(succeeded, basari=basari, hata=hata)
        if succeeded is not None else 0.0,
        bilgi=round(max(0.0, min(1.0, surprise)), 4),
        sosyal=social(reaction),
    )


def encoding_strength(value: float) -> float:
    """Faz 4's `guc`, in its general form: `0.4 + 0.6 * |odul|`.

    Both directions count. A costly mistake is written as deeply as a
    surprising success — arguably deeper, which is what the `lesson`
    multiplier already says.
    """
    from .activation import ENCODING_RANGE, ENCODING_FLOOR

    return round(ENCODING_FLOOR + ENCODING_RANGE * min(1.0, abs(value)), 4)
