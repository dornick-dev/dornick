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
(`eval/karakter/ornekler.json`) that never appears among the measured
decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FILE_NAME = "karar_ornekleri.json"
MAX_EXEMPLARS = 12
MAX_CHARS = 220

EXEMPLAR_HEADER = "Önceki kararların (aynı karakter, benzer durumlar — böyle karar verdin):"


@dataclass(slots=True)
class Exemplar:
    axis: str
    situation: str
    decision: str

    def as_dict(self) -> dict[str, str]:
        return {"eksen": self.axis, "durum": self.situation, "karar": self.decision}


def load(state_dir: Path) -> list[Exemplar]:
    """The recorded decisions; an empty list when the file is absent or broken."""
    path = Path(state_dir) / FILE_NAME
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[Exemplar] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        situation = str(row.get("durum") or "").strip()
        decision = str(row.get("karar") or "").strip()
        if situation and decision:
            out.append(Exemplar(str(row.get("eksen") or ""), situation, decision))
    return out[:MAX_EXEMPLARS]


def save(state_dir: Path, exemplars: list[Exemplar]) -> None:
    path = Path(state_dir) / FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([e.as_dict() for e in exemplars[:MAX_EXEMPLARS]],
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
