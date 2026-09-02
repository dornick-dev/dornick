"""The night's event stream — frozen, so the view can be built against it.

The brain view animates what the memory is doing. For that to be possible at
all, the two sides have to agree on a vocabulary, and the agreement has to
be the kind that breaks loudly rather than quietly: a renamed field should
fail a test, not produce an animation that silently stops moving.

So the schema here is **frozen**. `SCHEMA` is a snapshot; changing it is a
deliberate act that turns a test red, which is exactly the point. The view
reads only these events and never queries `recall.db` directly — while the
night is writing, a reader racing the writer would show a half-consolidated
graph and call it the truth.

The same stream serves live viewing and replay: the file on disk is the
event log, and replaying a night is reading it back in order. There is no
second code path to drift.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from .saat import Saat, duvar_saati

# Frozen event vocabulary (roadmap 3.10.5). Each entry lists the fields the
# view may rely on. A snapshot test compares this dict; editing it is a
# decision, not an accident.
SCHEMA: dict[str, tuple[str, ...]] = {
    "uyku.basladi":  ("basinc", "tahmini_uyanma", "dongu_sayisi"),
    "uyku.dongu":    ("no", "faz"),
    "tekrar.ileri":  ("oturum", "dizi", "kenarlar"),
    "tekrar.geri":   ("oturum", "sonuc", "paylar"),
    "dikis":         ("a", "b", "uzerinden", "oturumlar"),
    "dokunus":       ("id",),
    "damitma":       ("kaynaklar", "yeni"),
    "uyku.uyandi":   ("sebep", "dongu", "tamamlanan", "devreden", "borc"),
    "uyku.bitti":    ("sebep", "rapor"),
    "uyanik.ters":   ("oturum", "sonuc"),
    "mikro.basladi": ("basinc",),
    "mikro.bitti":   ("tamamlanan",),
    "yerel.basladi": ("bolge",),
    "yerel.bitti":   ("kuculen", "atlanan"),
}

# Every event carries these two on top of its own fields.
ORTAK = ("ts", "tur")


class SchemaError(ValueError):
    """An event that the view could not rely on."""


@dataclass(slots=True)
class NightLog:
    """Writes the night's events, one JSON object per line."""

    path: Path
    saat: Saat = duvar_saati
    listeners: list[Callable[[dict[str, Any]], None]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.listeners is None:
            self.listeners = []
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, tur: str, **fields: Any) -> dict[str, Any]:
        event = build(tur, self.saat, **fields)
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass        # the night still happened if its log could not be written
        for listener in tuple(self.listeners):
            try:
                listener(event)
            except Exception:
                pass    # a broken view must not stop consolidation
        return event


def build(tur: str, saat: Saat = duvar_saati, **fields: Any) -> dict[str, Any]:
    """One event, validated against the frozen schema before it exists."""
    if tur not in SCHEMA:
        raise SchemaError(f"şemada olmayan olay: {tur}")
    eksik = [ad for ad in SCHEMA[tur] if ad not in fields]
    if eksik:
        raise SchemaError(f"{tur}: eksik alan {', '.join(eksik)}")
    fazla = [ad for ad in fields if ad not in SCHEMA[tur]]
    if fazla:
        raise SchemaError(f"{tur}: şemada olmayan alan {', '.join(fazla)}")
    return {"ts": saat().isoformat(timespec="milliseconds"), "tur": tur, **fields}


def validate(event: dict[str, Any]) -> dict[str, Any]:
    """Read side of the same contract — used when replaying a file."""
    if not isinstance(event, dict):
        raise SchemaError("olay bir sözlük değil")
    for ad in ORTAK:
        if ad not in event:
            raise SchemaError(f"ortak alan eksik: {ad}")
    tur = event["tur"]
    if tur not in SCHEMA:
        raise SchemaError(f"şemada olmayan olay: {tur}")
    for ad in SCHEMA[tur]:
        if ad not in event:
            raise SchemaError(f"{tur}: eksik alan {ad}")
    return event


def replay(path: Path) -> Iterator[dict[str, Any]]:
    """Read a night back in order. Live view and replay share this shape.

    A malformed line is skipped rather than fatal: a night log truncated by
    a power cut should still replay up to the cut.
    """
    try:
        satirlar = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for satir in satirlar:
        if not satir.strip():
            continue
        try:
            yield validate(json.loads(satir))
        except (ValueError, SchemaError):
            continue


def nights(state_dir: Path) -> list[str]:
    """Which nights can be replayed, newest first."""
    klasor = Path(state_dir) / "gece"
    if not klasor.is_dir():
        return []
    return sorted((p.stem for p in klasor.glob("*.jsonl")), reverse=True)


def night_path(state_dir: Path, tarih: str) -> Path:
    """`.dornick/gece/<tarih>.jsonl`, with the date treated as untrusted."""
    guvenli = "".join(ch for ch in tarih if ch.isalnum() or ch in "-_")
    return Path(state_dir) / "gece" / f"{guvenli}.jsonl"


def summary(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The morning report: what the night did, in the numbers a person reads."""
    out = {"dongu": 0, "tekrar": 0, "kenar": 0, "dikis": 0, "damitik": 0,
           "dokunus": 0, "uyandi": "", "devreden": 0}
    for event in events:
        tur = event["tur"]
        if tur == "uyku.dongu":
            out["dongu"] = max(out["dongu"], int(event.get("no") or 0))
        elif tur == "tekrar.ileri":
            out["tekrar"] += 1
            out["kenar"] += len(event.get("kenarlar") or [])
        elif tur == "dikis":
            out["dikis"] += 1
        elif tur == "damitma":
            out["damitik"] += 1
        elif tur == "dokunus":
            out["dokunus"] += 1
        elif tur == "uyku.uyandi":
            out["uyandi"] = str(event.get("sebep") or "")
            out["devreden"] = int(event.get("devreden") or 0)
    return out
