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

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from .clock import Clock, wall_clock

# An old night is gzipped in deep sleep (sleep.compress_old_nights) and keeps
# this suffix on top of `.jsonl`. Listing and replay look through it: the
# view never learns whether a night was compressed.
COMPRESSED_SUFFIX = ".gz"

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
    clock: Clock = wall_clock
    listeners: list[Callable[[dict[str, Any]], None]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.listeners is None:
            self.listeners = []
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, kind: str, **fields: Any) -> dict[str, Any]:
        event = build(kind, self.clock, **fields)
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


def build(kind: str, clock: Clock = wall_clock, **fields: Any) -> dict[str, Any]:
    """One event, validated against the frozen schema before it exists."""
    if kind not in SCHEMA:
        raise SchemaError(f"şemada olmayan olay: {kind}")
    missing = [name for name in SCHEMA[kind] if name not in fields]
    if missing:
        raise SchemaError(f"{kind}: eksik alan {', '.join(missing)}")
    extra = [name for name in fields if name not in SCHEMA[kind]]
    if extra:
        raise SchemaError(f"{kind}: şemada olmayan alan {', '.join(extra)}")
    return {"ts": clock().isoformat(timespec="milliseconds"), "tur": kind, **fields}


def validate(event: dict[str, Any]) -> dict[str, Any]:
    """Read side of the same contract — used when replaying a file."""
    if not isinstance(event, dict):
        raise SchemaError("olay bir sözlük değil")
    for name in ORTAK:
        if name not in event:
            raise SchemaError(f"ortak alan eksik: {name}")
    kind = event["tur"]
    if kind not in SCHEMA:
        raise SchemaError(f"şemada olmayan olay: {kind}")
    for name in SCHEMA[kind]:
        if name not in event:
            raise SchemaError(f"{kind}: eksik alan {name}")
    return event


def replay(path: Path) -> Iterator[dict[str, Any]]:
    """Read a night back in order. Live view and replay share this shape.

    A malformed line is skipped rather than fatal: a night log truncated by
    a power cut should still replay up to the cut.
    """
    try:
        lines = _read_night(Path(path)).splitlines()
    except OSError:
        return
    for line in lines:
        if not line.strip():
            continue
        try:
            yield validate(json.loads(line))
        except (ValueError, SchemaError):
            continue


def _read_night(path: Path) -> str:
    """The night's text, whether it was compressed or not.

    A caller always asks for `<date>.jsonl`; if deep sleep has since gzipped
    that night, the `.gz` beside it is read instead. A gzip that turns out
    to be corrupt reads as empty rather than raising: a night that cannot
    be replayed is a missing night, not a broken view.
    """
    if path.suffix == COMPRESSED_SUFFIX:
        packed = path
    elif path.is_file():
        return path.read_text(encoding="utf-8")
    else:
        packed = compressed_path(path)
    try:
        with gzip.open(packed, "rt", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, EOFError, ValueError) as exc:
        if isinstance(exc, OSError) and not packed.exists():
            raise
        return ""


def compressed_path(path: Path) -> Path:
    """`<date>.jsonl.gz` for `<date>.jsonl`."""
    path = Path(path)
    return path.with_name(path.name + COMPRESSED_SUFFIX)


def compress(path: Path) -> Path:
    """Gzip one night in place: `<date>.jsonl` becomes `<date>.jsonl.gz`.

    The original is removed only after the compressed copy is complete, so
    a crash mid-way leaves the readable file, never neither. Already
    compressed (or missing) nights are left alone.
    """
    path = Path(path)
    target = compressed_path(path)
    if not path.is_file():
        return target
    with path.open("rb") as src, gzip.open(target, "wb") as dst:
        while chunk := src.read(1 << 16):
            dst.write(chunk)
    path.unlink()
    return target


def _night_name(path: Path) -> str:
    """The date a night file stands for, with or without the gzip suffix."""
    name = path.name
    if name.endswith(COMPRESSED_SUFFIX):
        name = name[: -len(COMPRESSED_SUFFIX)]
    return name[: -len(".jsonl")] if name.endswith(".jsonl") else name


def nights(state_dir: Path) -> list[str]:
    """Which nights can be replayed, newest first. Compressed ones included."""
    folder = Path(state_dir) / "gece"
    if not folder.is_dir():
        return []
    names = {_night_name(p) for p in folder.glob("*.jsonl")}
    names |= {_night_name(p) for p in folder.glob("*.jsonl" + COMPRESSED_SUFFIX)}
    return sorted(names, reverse=True)


def night_path(state_dir: Path, date: str) -> Path:
    """`.dornick/gece/<date>.jsonl`, with the date treated as untrusted."""
    safe = "".join(ch for ch in date if ch.isalnum() or ch in "-_")
    return Path(state_dir) / "gece" / f"{safe}.jsonl"


def summary(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The morning report: what the night did, in the numbers a person reads."""
    out = {"dongu": 0, "tekrar": 0, "kenar": 0, "dikis": 0, "damitik": 0,
           "dokunus": 0, "uyandi": "", "devreden": 0}
    for event in events:
        kind = event["tur"]
        if kind == "uyku.dongu":
            out["dongu"] = max(out["dongu"], int(event.get("no") or 0))
        elif kind == "tekrar.ileri":
            out["tekrar"] += 1
            out["kenar"] += len(event.get("kenarlar") or [])
        elif kind == "dikis":
            out["dikis"] += 1
        elif kind == "damitma":
            out["damitik"] += 1
        elif kind == "dokunus":
            out["dokunus"] += 1
        elif kind == "uyku.uyandi":
            out["uyandi"] = str(event.get("sebep") or "")
            out["devreden"] = int(event.get("devreden") or 0)
    return out
