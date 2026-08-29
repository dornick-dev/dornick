"""o1 — medium/Python: CSV → report + CLI.

The right answer is the grader's own arithmetic: the truth is derived from
the task's FROZEN seed CSV, never from the agent's output. If the agent
corrupted the file, the numbers will not match — and they should not.

No format is dictated: "47.553,25" and "47553.25" are both accepted. What
we measure is the number being right; the decimal separator is taste. The
one thing we do demand is ORDER: the top three products must be sorted
high to low.
"""

from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import grading  # noqa: E402
from grading import Axis, Tally  # noqa: E402

TITLE = "CSV sales report + CLI"
DIFFICULTY = "medium"
LANGUAGE = "python"
CRITICAL = ("rapor", "ciro", "ay")
SEED_CSV = Path(__file__).resolve().parent / "seed" / "satislar.csv"
CHOSEN_MONTH = "2026-03"


def truth() -> dict[str, object]:
    """The right answer computed from the frozen seed."""
    month_rev: collections.Counter[str] = collections.Counter()
    product_rev: collections.Counter[str] = collections.Counter()
    month_product: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter)
    with SEED_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            amount = int(row["adet"]) * float(row["birim_fiyat"])
            month = row["tarih"][:7]
            month_rev[month] += amount
            product_rev[row["urun"]] += amount
            month_product[month][row["urun"]] += amount
    return {
        "month_rev": {m: round(v, 2) for m, v in month_rev.items()},
        "top3": [p for p, _ in product_rev.most_common(3)],
        "month_top3": [p for p, _ in month_product[CHOSEN_MONTH].most_common(3)],
    }


def score(root: Path) -> list[Axis]:
    tool = grading.find(root, "rapor.py")
    csv_path = grading.find(root, "satislar.csv")
    t = truth()

    w = Tally()
    full: grading.Run | None = None
    monthly: grading.Run | None = None
    if tool is None:
        for name, weight in (("rapor.py exists", 8), ("runs on the csv", 16),
                             ("output not empty", 8), ("--ay runs", 8)):
            w.item(name, weight, False, "rapor.py not found")
    else:
        w.item("rapor.py exists", 8, True, str(tool.relative_to(root)))
        arg = str(csv_path) if csv_path else "satislar.csv"
        full = grading.shell([sys.executable, tool.name, arg],
                             cwd=tool.parent, timeout=90)
        w.item("runs on the csv", 16, full.ok,
               f"exit {full.code}; {full.brief(160)}")
        w.item("output not empty", 8, len(full.out.strip()) > 20,
               f"{len(full.out.strip())} chars")
        monthly = grading.shell([sys.executable, tool.name, arg,
                                 "--ay", CHOSEN_MONTH],
                                cwd=tool.parent, timeout=90)
        w.item("--ay runs", 8, monthly.ok,
               f"exit {monthly.code}; {monthly.brief(120)}")
    works = w.axis("works", 40)

    s = Tally()
    full_text = full.both if full else ""
    month_rev: dict[str, float] = t["month_rev"]  # type: ignore[assignment]
    matched = [m for m, v in month_rev.items()
               if grading.has_number(full_text, v, 0.02)]
    s.ratio("monthly totals right", 10, len(matched) / max(1, len(month_rev)),
            f"{len(matched)}/{len(month_rev)} months matched: "
            f"{', '.join(sorted(matched)) or 'none'}")

    top3: list[str] = t["top3"]  # type: ignore[assignment]
    all_present = all(p.casefold() in full_text.casefold() for p in top3)
    ordered = grading.in_order(full_text, top3)
    s.item("top 3 products present", 5, all_present, ", ".join(top3))
    s.item("the three sorted high to low", 5, all_present and ordered,
           "order held" if ordered else "order broken or product missing")

    month_text = monthly.both if monthly else ""
    chosen_right = grading.has_number(month_text,
                                      month_rev.get(CHOSEN_MONTH, -1), 0.02)
    others = [m for m in month_rev if m != CHOSEN_MONTH]
    leaked = [m for m in others
              if grading.has_number(month_text, month_rev[m], 0.02)]
    s.item(f"--ay {CHOSEN_MONTH} gives the right month", 3, chosen_right,
           f"expected {month_rev.get(CHOSEN_MONTH)}")
    # The filter point is only granted when the right month CAME: a tool
    # that prints nothing does not count as "filtered the other months" —
    # that would be a free point.
    s.item("--ay filters the other months", 2, chosen_right and not leaked,
           "the right month never came" if not chosen_right
           else (f"leaked months: {', '.join(leaked)}" if leaked else "clean"))
    scope = s.axis("scope", 25)

    return [works, scope, grading.health_axis(root),
            grading.tests_axis(root, critical=CRITICAL, external=True)]


if __name__ == "__main__":
    raise SystemExit(grading.standalone(score, "o1-report"))
