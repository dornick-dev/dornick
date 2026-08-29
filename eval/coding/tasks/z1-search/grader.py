"""z1 — hard/Python: search/index with SQLite persistence.

The difficulty lives in three separate places, each measured separately:

  * **Persistence.** `bul` runs in a SEPARATE process. Keeping the index
    in memory inside one process does not satisfy the request; the index
    must survive a restart. There must also be a real SQLite file on
    disk — verified by reading its header ("SQLite format 3"), never by
    trusting an extension.
  * **Ranking.** In a two-word query, the note containing both must rank
    ABOVE one containing only one. The frozen corpus is built for this:
    "rulman titresim" co-occur only in kuyu-bakim.
  * **Silence.** A word that exists nowhere must not produce invented
    results. The code-side twin of the memory bench's "silence" metric.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import grading  # noqa: E402
from grading import Axis, Tally  # noqa: E402

TITLE = "Note search tool with SQLite persistence"
DIFFICULTY = "hard"
LANGUAGE = "python"
CRITICAL = ("ekle", "bul")

SINGLE = "salmastra"            # only in pompa-katalog.txt
SINGLE_EXPECTED = "pompa-katalog"
DOUBLE = "rulman titresim"      # together only in kuyu-bakim
DOUBLE_TOP = "kuyu-bakim"
DOUBLE_BELOW = "pompa-katalog"  # has only "rulman": must rank below
MISSING = "helikopter"


def _sqlite_file(root: Path) -> Path | None:
    """Find the real SQLite file on disk by its header (never by extension)."""
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in grading.SKIP_DIRS]
        for name in sorted(filenames):
            path = Path(dirpath) / name
            try:
                if path.stat().st_size < 16:
                    continue
                with path.open("rb") as fh:
                    if fh.read(16) == b"SQLite format 3\x00":
                        return path
            except OSError:
                continue
    return None


def score(root: Path) -> list[Axis]:
    tool = grading.find(root, "ara.py")
    notes = None
    for candidate in ("notlar", "Notlar"):
        place = root / candidate
        if place.is_dir():
            notes = place
            break
    if notes is None:
        for p in root.rglob("kuyu-bakim.txt"):
            notes = p.parent
            break

    w = Tally()
    add = single = double = empty = None
    if tool is None:
        for name, weight in (("ara.py exists", 5), ("ekle runs", 12),
                             ("SQLite file created", 8),
                             ("bul runs in a separate process", 15)):
            w.item(name, weight, False, "ara.py not found")
    else:
        w.item("ara.py exists", 5, True, str(tool.relative_to(root)))
        where = tool.parent
        target = str(notes) if notes else "notlar"
        add = grading.shell([sys.executable, tool.name, "ekle", target],
                            cwd=where, timeout=120)
        w.item("ekle runs", 12, add.ok, f"exit {add.code}; {add.brief(160)}")

        db = _sqlite_file(root)
        w.item("SQLite file created", 8, db is not None,
               str(db.relative_to(root)) if db
               else "no file with a SQLite header on disk")

        # SEPARATE process: the only honest proof of persistence.
        single = grading.shell([sys.executable, tool.name, "bul", SINGLE],
                               cwd=where, timeout=90)
        w.item("bul runs in a separate process", 15, single.ok,
               f"exit {single.code}; {single.brief(160)}")
        double = grading.shell([sys.executable, tool.name, "bul", DOUBLE],
                               cwd=where, timeout=90)
        empty = grading.shell([sys.executable, tool.name, "bul", MISSING],
                              cwd=where, timeout=90)
    works = w.axis("works", 40)

    s = Tally()
    single_text = single.both if single else ""
    s.item("single word finds the right note", 8,
           SINGLE_EXPECTED in single_text,
           f"«{SINGLE}» → expected {SINGLE_EXPECTED}; "
           f"output: {single_text[:120]!r}")

    double_text = double.both if double else ""
    top = double_text.find(DOUBLE_TOP)
    below = double_text.find(DOUBLE_BELOW)
    ranked = top >= 0 and (below < 0 or top < below)
    s.item("multi-word: full match ranks first", 10, ranked,
           f"«{DOUBLE}» → {DOUBLE_TOP} at {top}, {DOUBLE_BELOW} at {below}")

    empty_text = empty.both if empty else ""
    clean = bool(empty) and not any(
        name in empty_text for name in
        ("kuyu-bakim", "pompa-katalog", "teklif-kayseri", "sensor-arizasi",
         "toplanti-2mart", "egitim-plani"))
    s.item("missing word invents nothing", 7, clean,
           f"«{MISSING}» → output: {empty_text[:120]!r}")
    scope = s.axis("scope", 25)

    return [works, scope, grading.health_axis(root),
            grading.tests_axis(root, critical=CRITICAL)]


if __name__ == "__main__":
    raise SystemExit(grading.standalone(score, "z1-search"))
