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

_SAYI = re.compile(r"\d")


class SelfWriteRefused(PermissionError):
    """Raised when something other than outcome replay tries to write `self`."""


# -- world -------------------------------------------------------------


def world_record(body: str, *, kaynak: str, clock: Clock | None = None) -> dict[str, Any]:
    """A world fact needs a source. Without one it is a rumour, not an
    observation, and rumours do not get to age gracefully."""
    if not kaynak or not kaynak.strip():
        raise ValueError("`world` kaydı kaynaksız yazılamaz (yol, URL ya da komut)")
    clock = clock or wall_clock
    return {"body": body, "kaynak": kaynak.strip(),
            "dogrulama": clock().isoformat(timespec="milliseconds")}


def confidence(dogrulama: str | None, *, clock: Clock | None = None) -> float:
    """0.5 ** (days / 14). The world moves; a fact about it decays."""
    clock = clock or wall_clock
    an = parse(dogrulama)
    if an is None:
        return 0.0
    gun = max(0.0, (clock() - an).total_seconds() / 86400.0)
    return round(0.5 ** (gun / CONFIDENCE_HALF_LIFE_DAYS), 4)


def is_stale(dogrulama: str | None, *, clock: Clock | None = None) -> bool:
    """Older than 30 days unverified: still searchable, no longer injected."""
    clock = clock or wall_clock
    an = parse(dogrulama)
    return an is None or (clock() - an).days >= STALE_DAYS


def world_label(dogrulama: str | None, *, clock: Clock | None = None) -> str:
    """What `mind_recall` shows next to it, so the model can decide to check."""
    clock = clock or wall_clock
    an = parse(dogrulama)
    if an is None:
        return " (doğrulanmadı)"
    gun = (clock() - an).days
    return f" ({gun} gündür doğrulanmadı)" if gun >= 1 else ""


# -- self --------------------------------------------------------------


@dataclass(slots=True)
class SelfRecord:
    """A competence record. Countable only — no adjectives, ever."""

    alan: str
    arac: str = ""
    basari: int = 0
    hata: int = 0
    ort_deneme: float = 0.0
    tekrar_eden_hata: str = ""
    model_id: str = ""

    def line(self) -> str:
        toplam = self.basari + self.hata
        # "başarılı" bilerek kullanılmıyor: kendi kuralımızın yasakladığı
        # sıfat, kendi çıktımızda da geçemez (test bunu zorluyor).
        parca = f"{self.alan}: {toplam} işin {self.basari} tanesi geçti"
        if self.arac:
            parca += f" ({self.arac})"
        if self.tekrar_eden_hata:
            parca += f"; tekrar eden hata: {self.tekrar_eden_hata}"
        return parca

    def as_dict(self) -> dict[str, Any]:
        return {"alan": self.alan, "arac": self.arac, "basari": self.basari,
                "hata": self.hata, "ort_deneme": self.ort_deneme,
                "tekrar_eden_hata": self.tekrar_eden_hata,
                "model_id": self.model_id}


def check_self_line(line: str) -> str:
    """Reject an evaluative adjective. Returns the line if it is countable.

    "I am careful" cannot be verified, cannot be corrected, and survives no
    model change. "In 41 tasks I wrote tests first 33 times" can be all
    three.
    """
    dusuk = line.casefold()
    for sifat in BANNED_ADJECTIVES:
        if re.search(rf"\b{re.escape(sifat)}\b", dusuk):
            raise ValueError(
                f"`self` satırında değerlendirici sıfat: '{sifat}'. "
                "Yalnız sayılabilir ifade yazılır.")
    if not _SAYI.search(line):
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
