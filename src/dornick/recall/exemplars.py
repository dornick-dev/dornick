"""Decision exemplars — character shown, not described.

Five real runs of the 7.6 harness (2026-09-04/05) said the same thing:
adjectival guidance ("be more cautious", even with a concrete rule) moves
two or three temperament axes and leaves the rest untouched — Claude Haiku
would not loosen "finish the job" or tighten "ask first" for any wording.
What a model does follow is precedent: a handful of its own earlier
decisions, in situations like the one at hand. The exemplars are recorded
decisions (situation → choice) of the character the user lived with — the
previous model's measured baseline, or the user's corrections — and they
render as "in situations like these you decided…".

They are not measurement leakage: the harness keeps a separate exemplar set
(`eval/character/exemplars.json`) that never appears among the measured
decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import legacy_names, legacy_values

FILE_NAME = "decision_exemplars.json"
MAX_EXEMPLARS = 12
MAX_CHARS = 220

EXEMPLAR_HEADER = "Önceki kararların (aynı karakter, benzer durumlar — böyle karar verdin):"


@dataclass(slots=True)
class Exemplar:
    axis: str
    situation: str
    decision: str

    def as_dict(self) -> dict[str, str]:
        return {"axis": self.axis, "situation": self.situation, "decision": self.decision}


def _path(state_dir: Path) -> Path:
    path = Path(state_dir) / FILE_NAME
    legacy_names.adopt(Path(state_dir) / "karar_ornekleri.json", path)
    return path


def _read(state_dir: Path) -> tuple[str, list[Any]]:
    path = _path(state_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", []
    if isinstance(data, dict):
        data = legacy_values.keys(data, legacy_values.EXEMPLAR_KEYS)
        return str(data.get("model_id") or ""), list(data.get("decisions") or [])
    return "", data if isinstance(data, list) else []


def load_model_id(state_dir: Path) -> str:
    """Which model's decisions the file holds ("" = unknown / old format)."""
    return _read(state_dir)[0]


def load(state_dir: Path) -> list[Exemplar]:
    """The recorded decisions; an empty list when the file is absent or broken."""
    _model, rows = _read(state_dir)
    out: list[Exemplar] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        # A file written before 1.5.5 says eksen/durum/karar and names the
        # axis in Turkish.
        row = legacy_values.keys(row, legacy_values.EXEMPLAR_KEYS)
        situation = str(row.get("situation") or "").strip()
        decision = str(row.get("decision") or "").strip()
        if situation and decision:
            axis = str(row.get("axis") or "")
            out.append(Exemplar(legacy_values.AXES.get(axis, axis), situation, decision))
    return out[:MAX_EXEMPLARS]


def save(state_dir: Path, exemplars: list[Exemplar], model_id: str = "") -> None:
    """Writes the decisions with the id of the model that made them."""
    path = _path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model_id": model_id,
                                "decisions": [e.as_dict() for e in exemplars[:MAX_EXEMPLARS]]},
                               ensure_ascii=False, indent=1), encoding="utf-8")


def render(exemplars: list[Exemplar]) -> str:
    """The prompt block; empty when there is nothing to show."""
    if not exemplars:
        return ""
    lines = [EXEMPLAR_HEADER]
    for e in exemplars[:MAX_EXEMPLARS]:
        situation = " ".join(e.situation.split())[:MAX_CHARS]
        lines.append(f"- {situation} → {e.decision}")
    return "\n".join(lines)
