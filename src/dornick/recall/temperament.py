"""Temperament — measured from the model, corrected by the harness.

Temperament is not chosen and not seeded. It arrives with the remote model:
one model is cautious and asks before acting, another walks straight in, a
small local one gives up sooner. That is the genome-and-hardware layer —
the reward system's innate gains (Cloninger; Kagan). The harness's job is
to **measure** it and then learn the correction the user keeps making.

Three quantities, and keeping them apart is the whole design:

    taban     measured — what this model is, on an empty memory
    hedef     learned — where the user's corrections keep pushing it
    kaldirac  hedef / taban — what the harness applies to close the gap

Swapping models is a brain transplant: the hardware changes, the learned
corrections stay and are recomputed against the new baseline. That is why
`hedef` lives in config and survives a memory reset — amnesia takes the
narrative, not the temperament.

The leverage lands on **harness parameters, not prompts**: retry limits,
permission thresholds, exploration budget. A prompt is a request; a
threshold is a fact. Prompts are the last resort, not the first.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable

# Five axes, each in [0, 1], 0.5 neutral.
EKSENLER = ("yenilik", "sonuc", "sosyal", "sebat", "temkin")

# Plasticity decays but never reaches zero: the hundredth session moves the
# needle half as far as the first, the thousandth still moves it.
ETA_TABAN = 0.02
ETA_YARILANMA = 100.0

# Leverage is bounded. A harness that can multiply a threshold without limit
# would turn one measurement error into a broken product.
KALDIRAC_ALT = 0.25
KALDIRAC_UST = 4.0


@dataclass(frozen=True, slots=True)
class Temperament:
    yenilik: float = 0.5
    sonuc: float = 0.5
    sosyal: float = 0.5
    sebat: float = 0.5
    temkin: float = 0.5

    def as_dict(self) -> dict[str, float]:
        return {k: round(v, 4) for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Temperament:
        data = data or {}
        return cls(**{eksen: float(data.get(eksen, 0.5)) for eksen in EKSENLER})


def leverage(taban: Temperament, hedef: Temperament) -> dict[str, float]:
    """What the harness has to do to turn this model into that behaviour.

    A cautious model driven by a bold target needs its permission threshold
    lowered; a bold model with the same target needs it raised. The target
    does not move — only the correction does.
    """
    out: dict[str, float] = {}
    for eksen in EKSENLER:
        alt = max(0.05, getattr(taban, eksen))
        out[eksen] = round(max(KALDIRAC_ALT,
                               min(KALDIRAC_UST, getattr(hedef, eksen) / alt)), 4)
    return out


def eta(session_count: int) -> float:
    """How far one correction moves the target. Decays, never dies."""
    return round(ETA_TABAN / (1 + max(0, session_count) / ETA_YARILANMA), 6)


def correct(hedef: Temperament, eksen: str, direction: int,
            *, session_count: int = 0) -> Temperament:
    """One user correction nudges one axis. Manual settings always win."""
    if eksen not in EKSENLER:
        raise ValueError(f"Bilinmeyen eksen: {eksen}")
    adim = eta(session_count) * (1 if direction > 0 else -1)
    yeni = max(0.0, min(1.0, getattr(hedef, eksen) + adim))
    return replace(hedef, **{eksen: round(yeni, 6)})


# -- the probe ---------------------------------------------------------


@dataclass(slots=True)
class Probe:
    """One decision that separates one axis. Twenty of these make a baseline."""

    eksen: str
    istem: str
    # The answer that counts as "high" on this axis. Everything else is low.
    yuksek: str


def measure(probes: list[Probe], answer: Callable[[str], str]) -> Temperament:
    """Run the probe set on an EMPTY memory and read the axes off it.

    Empty is not an implementation detail: with memories loaded, the thing
    being measured would be the memories. This is meant to catch what the
    model brings before anything has happened to it.
    """
    sayim: dict[str, list[float]] = {eksen: [] for eksen in EKSENLER}
    for probe in probes:
        try:
            cevap = (answer(probe.istem) or "").strip().casefold()
        except Exception:
            continue
        sayim.setdefault(probe.eksen, []).append(
            1.0 if probe.yuksek.casefold() in cevap else 0.0)
    return Temperament(**{
        eksen: round(sum(degerler) / len(degerler), 4) if degerler else 0.5
        for eksen, degerler in sayim.items() if eksen in EKSENLER})


# -- persistence -------------------------------------------------------


def load(state_dir: Path) -> tuple[Temperament, Temperament, str]:
    """(taban, hedef, model_id). Missing file means neutral, not an error."""
    try:
        data = json.loads((Path(state_dir) / "mizac.json").read_text("utf-8"))
    except (OSError, ValueError):
        return Temperament(), Temperament(), ""
    taban = Temperament.from_dict(data.get("taban"))
    hedef = Temperament.from_dict(data.get("hedef") or data.get("taban"))
    return taban, hedef, str(data.get("model_id") or "")


def save(state_dir: Path, taban: Temperament, hedef: Temperament,
         model_id: str = "") -> None:
    path = Path(state_dir) / "mizac.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"taban": taban.as_dict(), "hedef": hedef.as_dict(),
                                "model_id": model_id}, ensure_ascii=False),
                    encoding="utf-8")


def on_model_change(state_dir: Path, yeni_taban: Temperament,
                    model_id: str) -> dict[str, float]:
    """The baseline is remeasured; the target stays; leverage is recomputed.

    This is the whole claim of the phase in one function: what the user
    taught survives the model that learned it.
    """
    _eski_taban, hedef, _eski_id = load(state_dir)
    save(state_dir, yeni_taban, hedef, model_id)
    return leverage(yeni_taban, hedef)
