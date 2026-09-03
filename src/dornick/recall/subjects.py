"""Three subjects — the user, the world, and itself.

Until now there was one subject. Everything the agent knew was filed as
something about the user, which quietly turned observations into
preferences: "opened the log first" became "prefers reading logs". Three
subjects, and the rule that separates them is about **origin**, not topic:

    user    only what the user SAID. An observation goes to `world`.
    world   only what the agent OBSERVED, and every one carries its source
            (a path, a URL, a command). Confidence halves every two weeks:
            the world moves and a fact about it goes stale.
    self    only what OUTCOMES showed. Never the model's own claim about
            itself — a model asked whether it is careful will say yes.

The `self` rule is the sharp one and it is enforced in code, not in a
prompt: `mind_memory save kind=self` is refused. A record of competence has
to be earned by results, and it carries the model id that earned it, so a
model swap does not inherit another model's track record.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .clock import Clock, parse, wall_clock

# A world fact halves in confidence every two weeks; at 30 days it is marked
# unverified and can no longer be injected automatically.
CONFIDENCE_HALF_LIFE_DAYS = 14.0
STALE_DAYS = 30

# Evaluative adjectives may not appear in a `self` record. "Careful" is a
# claim; "wrote tests first in 33 of 41 tasks" is a count. Only the second
# can be checked, and only the second survives a model change.
BANNED_ADJECTIVES = (
    "dikkatli", "meraklı", "meraklı", "iyi", "kötü", "başarılı", "zeki",
    "yaratıcı", "sabırlı", "titiz", "özenli", "yetenekli", "usta",
    "careful", "curious", "good", "smart", "creative", "patient",
)

_DIGIT = re.compile(r"\d")


class SelfWriteRefused(PermissionError):
    """Raised when something other than outcome replay tries to write `self`."""


# -- world -------------------------------------------------------------


def world_record(body: str, *, source: str, clock: Clock | None = None) -> dict[str, Any]:
    """A world fact needs a source. Without one it is a rumour, not an
    observation, and rumours do not get to age gracefully."""
    if not source or not source.strip():
        raise ValueError("`world` kaydı kaynaksız yazılamaz (yol, URL ya da komut)")
    clock = clock or wall_clock
    return {"body": body, "kaynak": source.strip(),
            "dogrulama": clock().isoformat(timespec="milliseconds")}


def confidence(verified_at: str | None, *, clock: Clock | None = None) -> float:
    """0.5 ** (days / 14). The world moves; a fact about it decays."""
    clock = clock or wall_clock
    moment = parse(verified_at)
    if moment is None:
        return 0.0
    days = max(0.0, (clock() - moment).total_seconds() / 86400.0)
    return round(0.5 ** (days / CONFIDENCE_HALF_LIFE_DAYS), 4)


def is_stale(verified_at: str | None, *, clock: Clock | None = None) -> bool:
    """Older than 30 days unverified: still searchable, no longer injected."""
    clock = clock or wall_clock
    moment = parse(verified_at)
    return moment is None or (clock() - moment).days >= STALE_DAYS


def world_label(verified_at: str | None, *, clock: Clock | None = None) -> str:
    """What `mind_recall` shows next to it, so the model can decide to check."""
    clock = clock or wall_clock
    moment = parse(verified_at)
    if moment is None:
        return " (doğrulanmadı)"
    days = (clock() - moment).days
    return f" ({days} gündür doğrulanmadı)" if days >= 1 else ""


# -- self --------------------------------------------------------------


@dataclass(slots=True)
class SelfRecord:
    """A competence record. Countable only — no adjectives, ever."""

    area: str
    tool: str = ""
    successes: int = 0
    failures: int = 0
    mean_attempts: float = 0.0
    recurring_error: str = ""
    model_id: str = ""

    def line(self) -> str:
        total = self.successes + self.failures
        # "başarılı" is deliberately not used: the adjective our own rule bans
        # may not pass in our own output either (the test enforces this).
        piece = f"{self.area}: {total} işin {self.successes} tanesi geçti"
        if self.tool:
            piece += f" ({self.tool})"
        if self.recurring_error:
            piece += f"; tekrar eden hata: {self.recurring_error}"
        return piece

    def as_dict(self) -> dict[str, Any]:
        # Record form — the keys are the Turkish meta names, like `world_record`'s.
        return {"alan": self.area, "arac": self.tool, "basari": self.successes,
                "hata": self.failures, "ort_deneme": self.mean_attempts,
                "tekrar_eden_hata": self.recurring_error,
                "model_id": self.model_id}


def check_self_line(line: str) -> str:
    """Reject an evaluative adjective. Returns the line if it is countable.

    "I am careful" cannot be verified, cannot be corrected, and survives no
    model change. "In 41 tasks I wrote tests first 33 times" can be all
    three.
    """
    lowered = line.casefold()
    for adjective in BANNED_ADJECTIVES:
        if re.search(rf"\b{re.escape(adjective)}\b", lowered):
            raise ValueError(
                f"`self` satırında değerlendirici sıfat: '{adjective}'. "
                "Yalnız sayılabilir ifade yazılır.")
    if not _DIGIT.search(line):
        raise ValueError("`self` satırı sayı içermeli: sicil bir iddia değil, "
                         "bir sayımdır.")
    return line


def guard_model_write(kind: str, *, from_night: bool = False) -> None:
    """`self` is written by outcome replay, never by the model itself."""
    if kind == "self" and not from_night:
        raise SelfWriteRefused(
            "`self` kaydı yalnız sonuç olaylarından türetilir; modelin kendi "
            "hakkındaki beyanı kaydedilmez.")


def visible_self(records: list[SelfRecord], model_id: str) -> list[SelfRecord]:
    """Only this model's record reaches the soul.

    A track record earned by another model is not this model's competence.
    The old rows stay searchable and labelled — the right behaviour for
    someone who has had a brain transplant.
    """
    return [r for r in records if not r.model_id or r.model_id == model_id]
