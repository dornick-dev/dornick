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

    ad: str
    onceki_hata: float = 0.0      # mean |outcome error|, days 8-14
    son_hata: float = 0.0         # mean |outcome error|, last 7 days
    dokunma: int = 0              # how often the user went there, last 30 days

    @property
    def progress(self) -> float:
        """Learning progress: error going down is the signal, not error size."""
        return round(self.onceki_hata - self.son_hata, 4)


def relevance(areas: Iterable[Area]) -> dict[str, float]:
    """Normalised user attention. Zero touches means zero budget, full stop."""
    alanlar = list(areas)
    toplam = sum(a.dokunma for a in alanlar)
    if not toplam:
        return {a.ad: 0.0 for a in alanlar}
    return {a.ad: round(a.dokunma / toplam, 4) for a in alanlar}


def scores(areas: Iterable[Area], *, yenilik: float = 0.5) -> dict[str, float]:
    """`mizac.yenilik × max(ilerleme, 0) × alaka`."""
    alanlar = list(areas)
    alaka = relevance(alanlar)
    return {a.ad: round(yenilik * max(a.progress, 0.0) * alaka[a.ad], 6)
            for a in alanlar}


def distribution(areas: Iterable[Area], *, yenilik: float = 0.5,
                 taban: float = ENTROPY_FLOOR) -> dict[str, float]:
    """Softmax over the scores, with an entropy floor on the weakest areas.

    An area the user never touches stays at zero even after the floor: the
    floor protects diversity inside the user's world, not outside it.
    """
    puan = scores(areas, yenilik=yenilik)
    ilgili = {ad: p for ad, p in puan.items() if p > 0.0}
    if not ilgili:
        return {ad: 0.0 for ad in puan}

    en_buyuk = max(ilgili.values())
    us = {ad: math.exp((p - en_buyuk) * 8.0) for ad, p in ilgili.items()}
    toplam = sum(us.values())
    yumusak = {ad: v / toplam for ad, v in us.items()}

    # The floor is spread over the lowest-scoring RELEVANT areas.
    sirali = sorted(ilgili, key=lambda ad: ilgili[ad])
    dilim = sirali[:max(1, len(sirali) // 2)]
    out = {ad: 0.0 for ad in puan}
    for ad, pay in yumusak.items():
        out[ad] = (1 - taban) * pay
    for ad in dilim:
        out[ad] += taban / len(dilim)
    return {ad: round(v, 4) for ad, v in out.items()}


def entropy(dist: dict[str, float]) -> float:
    """Normalised entropy of the distribution. The collapse alarm."""
    paylar = [p for p in dist.values() if p > 0]
    if len(paylar) <= 1:
        return 0.0
    toplam = sum(paylar)
    paylar = [p / toplam for p in paylar]
    h = -sum(p * math.log(p) for p in paylar)
    return round(h / math.log(len(paylar)), 4)


def allowed_actions(*, has_model: bool, web: bool = WEB_OPEN) -> list[str]:
    """What the curiosity window may do. The list is short on purpose.

    Nothing here reads file contents into memory: a `world` record gets the
    structure (which files, which test command, which README heading), never
    the text inside the user's files.
    """
    izin = ["dizin_yapisi", "test_komutu_kaniti", "kirilan_test_gecmisi"]
    if has_model:
        izin.append("arac_dokumani_ozeti")
    if web:
        izin.append("web")
    return izin


def picks(areas: Iterable[Area], *, yenilik: float = 0.5) -> list[str]:
    """Areas in the order curiosity would visit them."""
    dist = distribution(areas, yenilik=yenilik)
    return [ad for ad, pay in sorted(dist.items(), key=lambda kv: -kv[1]) if pay > 0]
