"""What happens to the character when the model changes.

The roadmap's claim (7.2, 7.5): the character lives in the harness, not in
the model. Six real measurements (docs/hafiza-fazlar.md, 7.6) settled what
that takes in practice:

* the new model's temperament must be MEASURED, not assumed — same probes,
  bare prompt, no memory (temperament.measure);
* the target the user taught stays; what changes is the lever per axis;
* the lever's dose is per model and has to be learned in closed loop
  (temperament.calibrate) — one computed ratio overshoots one model and
  is ignored by another;
* precedent beats description: the previous model's own decisions, shown
  as "you decided so before", move the axes no rule sentence could.

So a model change costs three short probe passes — bare baseline, precedent
(first install only), levered re-measure — about thirty calls, run by the
sleep daemon when it notices the configured model differs from the one the
temperament file names. Nothing here touches the model's own words about
itself; every number is a count of choices.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import exemplars as exemplar_store
from . import temperament
from .temperament import AXIS_KEYS, Probe, Temperament

PROBES_FILE = Path(__file__).resolve().parents[1] / "assets" / "karar_sondalari.json"

AXIS_OF = {v: k for k, v in AXIS_KEYS.items()}

ANSWER_RULE = (
    "İki seçenek var: «{a}» ya da «{b}». İLK satırın YALNIZCA şu biçimde olsun "
    "ve seçeneğin tam metnini taşısın:\nKARAR: <seçenek>\n"
    "Sonra en fazla iki cümleyle gerekçeni yaz."
)

# ask(user_text, bare) -> reply. `bare`: the product prompt without the
# character block (no leverage, no identity, no precedent) — what the model
# brings on its own. The bridge supplies it; the daemon calls it.
Ask = Callable[[str, bool], str]


@dataclass(slots=True)
class ProbeDecision:
    id: str
    axis: str
    message: str
    options: tuple[str, str]
    high: str
    context: str

    @property
    def low(self) -> str:
        return self.options[1] if self.options[0] == self.high else self.options[0]

    def render(self) -> str:
        # The shipped contexts already carry their "Bağlam:" label.
        head = f"{self.context}\n\n" if self.context else ""
        a, b = self.options
        return head + self.message + "\n\n" + ANSWER_RULE.format(a=a, b=b)


def load_probes(path: Path = PROBES_FILE) -> list[ProbeDecision]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: list[ProbeDecision] = []
    for raw in data.get("kararlar", []):
        options = tuple(str(o) for o in raw.get("secenekler", ()))[:2]
        if len(options) != 2:
            continue
        contexts = [str(c) for c in raw.get("baglamlar", ())]
        out.append(ProbeDecision(
            id=str(raw.get("id", "")),
            axis=AXIS_OF.get(str(raw.get("eksen", "")), str(raw.get("eksen", ""))),
            message=str(raw.get("mesaj", "")),
            options=options,  # type: ignore[arg-type]
            high=str(raw.get("yuksek", "")),
            context=contexts[0] if contexts else "",
        ))
    return out


def parse_choice(reply: str, options: tuple[str, str]) -> str:
    """The option named on the KARAR line; "" when the reply does not decide."""
    junk = " *_`\"'«».:"
    lines = [ln.strip() for ln in (reply or "").splitlines() if ln.strip()]
    for line in lines:
        bare = line.strip(junk)
        if bare.casefold().startswith("karar"):
            label = bare[5:].strip(junk).casefold() if ":" in line or "：" in line else ""
            hits = [o for o in options if o.casefold() == label]
            if len(hits) == 1:
                return hits[0]
            hits = [o for o in options if o.casefold() in label]
            return hits[0] if len(hits) == 1 else ""
    if lines:
        last = lines[-1].strip(junk).casefold()
        hits = [o for o in options if o.casefold() == last]
        if len(hits) == 1:
            return hits[0]
    return ""


def probe_model(ask: Ask, probes: list[ProbeDecision], *, bare: bool) -> dict[str, str]:
    """Every probe once; returns decision id -> chosen option ("" = undecided)."""
    out: dict[str, str] = {}
    for probe in probes:
        try:
            reply = ask(probe.render(), bare)
        except Exception:
            reply = ""
        out[probe.id] = parse_choice(reply, probe.options)
    return out


def reached_from(answers: dict[str, str], probes: list[ProbeDecision]) -> dict[str, float | None]:
    """Share of high choices per axis — the shape `temperament.calibrate` reads."""
    tally: dict[str, list[float]] = {}
    for probe in probes:
        choice = answers.get(probe.id, "")
        if choice:
            tally.setdefault(probe.axis, []).append(1.0 if choice == probe.high else 0.0)
    return {axis: (sum(v) / len(v) if v else None) for axis, v in tally.items()}


def measure_baseline(ask: Ask, probes: list[ProbeDecision]) -> tuple[Temperament, dict[str, str]]:
    answers = probe_model(ask, probes, bare=True)
    by_prompt = {p.render(): p for p in probes}
    tprobes = [Probe(axis=p.axis, prompt=p.render(), high=p.high) for p in probes]

    def answer(prompt: str) -> str:
        return answers.get(by_prompt[prompt].id, "")

    return temperament.measure(tprobes, answer), answers


def precedent_from(answers: dict[str, str], probes: list[ProbeDecision]) -> list[exemplar_store.Exemplar]:
    out = []
    for probe in probes:
        choice = answers.get(probe.id, "")
        if choice:
            situation = f"{probe.context} {probe.message}".strip()
            out.append(exemplar_store.Exemplar(AXIS_KEYS.get(probe.axis, probe.axis), situation, choice))
    return out


@dataclass(slots=True)
class ChangeReport:
    model_id: str
    previous: str
    baseline: dict[str, float]
    reached: dict[str, float | None]
    gain: dict[str, float]
    precedent_recorded: bool
    calls: int


def handle_model_change(state_dir: Path, model_id: str, ask: Ask,
                        probes: list[ProbeDecision] | None = None) -> ChangeReport | None:
    """Runs the whole routine if `model_id` is not the model the character
    was last measured on. Returns None when nothing needed doing.

    Order matters: the precedent is recorded BEFORE the temperament file
    changes hands (so it is the old character's), the baseline is measured
    bare (so it is the new model's own), the gain is calibrated from a
    levered re-measure (so the dose fits this model).
    """
    if not model_id:
        return None
    _baseline, target, previous = temperament.load(state_dir)
    if previous == model_id:
        return None
    probes = probes or load_probes()
    calls = 0

    # 1. Bare baseline of the new model. A model that decided nothing has
    #    not been measured — stop before anything is written.
    baseline, bare_answers = measure_baseline(ask, probes)
    calls += len(probes)
    if not any(bare_answers.values()):
        raise RuntimeError(f"{model_id}: hiçbir sondada karar yok (model konuşmuyor?)")

    # 2. Precedent: only when there is none yet (first install) — the new
    #    model's own decisions are then the character. On a real change the
    #    previous model's decisions stay: they ARE the character to keep.
    recorded = False
    if not exemplar_store.load(state_dir):
        exemplar_store.save(state_dir, precedent_from(bare_answers, probes), model_id)
        recorded = True

    # 3. Target stays, baseline and model change hands, gain resets.
    temperament.on_model_change(state_dir, baseline, model_id)

    # 4. Levered re-measure and one calibration step.
    levered = probe_model(ask, probes, bare=False)
    calls += len(probes)
    reached = reached_from(levered, probes)
    gain = temperament.calibrate(baseline, target, reached)
    temperament.save_gain(state_dir, gain)
    return ChangeReport(model_id=model_id, previous=previous,
                        baseline=baseline.as_dict(),
                        reached={AXIS_KEYS.get(a, a): v for a, v in reached.items()},
                        gain={AXIS_KEYS.get(a, a): v for a, v in gain.items()},
                        precedent_recorded=recorded, calls=calls)
