"""k1 — easy/Python: a module plus its tests.

Chosen because it is easy to measure: TCKN validation is closed-form, has
one right answer, and the grader computes the truth ITSELF — it never
looks at the agent's output and says "probably correct".

We search for wherever the agent put the module (root or a subfolder);
file placement is not what this task measures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import grading  # noqa: E402
from grading import Axis, Tally  # noqa: E402

TITLE = "TCKN validation module + tests"
DIFFICULTY = "easy"
LANGUAGE = "python"
CRITICAL = ("dogrula",)


def _tckn(nine: str) -> str:
    """The grader's own truth: build a valid TCKN from nine digits."""
    d = [int(c) for c in nine]
    odd = d[0] + d[2] + d[4] + d[6] + d[8]
    even = d[1] + d[3] + d[5] + d[7]
    tenth = (odd * 7 - even) % 10
    eleventh = (sum(d) + tenth) % 10
    return nine + str(tenth) + str(eleventh)


# Frozen samples: generated here, but the generator is fixed, so is the result.
VALID = [_tckn(s) for s in ("123456789", "987654321", "100000001",
                            "555555555", "246813579")]
INVALID = [
    "12345678901",     # checksum fails
    "01234567890",     # starts with zero
    "1234567890",      # 10 digits
    "123456789012",    # 12 digits
    "1234567890a",     # contains a letter
    "",                # empty
]
# Garbage inputs the function must survive.
GARBAGE = ["None", "12 34 567 8901", "  ", "abcdefghijk"]


_PROBE = r"""
import json, sys
sys.path.insert(0, {folder!r})
import tckn
valid = {valid!r}
invalid = {invalid!r}
garbage = {garbage!r}
report = {{"import": True, "valid": [], "invalid": [], "garbage": [], "crashes": []}}
for no in valid:
    try:
        report["valid"].append(bool(tckn.dogrula(no)))
    except Exception as e:
        report["valid"].append(None); report["crashes"].append(f"{{no}}: {{e!r}}")
for no in invalid:
    try:
        report["invalid"].append(bool(tckn.dogrula(no)))
    except Exception as e:
        report["invalid"].append(None); report["crashes"].append(f"{{no}}: {{e!r}}")
for raw in garbage:
    value = None if raw == "None" else raw
    try:
        report["garbage"].append(bool(tckn.dogrula(value)))
    except Exception as e:
        report["garbage"].append(None); report["crashes"].append(f"{{raw}}: {{e!r}}")
print("###" + json.dumps(report))
"""


def _probe(folder: Path) -> grading.Run:
    script = _PROBE.format(folder=str(folder), valid=VALID,
                           invalid=INVALID, garbage=GARBAGE)
    return grading.shell([sys.executable, "-c", script], cwd=folder, timeout=60)


def _report(run: grading.Run) -> dict | None:
    for line in run.both.splitlines():
        if line.startswith("###"):
            try:
                return json.loads(line[3:])
            except ValueError:
                return None
    return None


def score(root: Path) -> list[Axis]:
    module = grading.find(root, "tckn.py")

    # -- WORKS --------------------------------------------------------
    w = Tally()
    report = None
    if module is None:
        w.item("tckn.py exists", 10, False, "not found in the workshop")
        w.item("module imports", 15, False, "no file")
        w.item("dogrula() is callable", 15, False, "no file")
    else:
        w.item("tckn.py exists", 10, True, str(module.relative_to(root)))
        run = _probe(module.parent)
        report = _report(run)
        w.item("module imports", 15, report is not None,
               "ok" if report else run.brief(160))
        if report is None:
            w.item("dogrula() is callable", 15, False, "import failed")
        else:
            no_crashes = not report["crashes"]
            ran = any(v is not None for v in report["valid"])
            w.item("dogrula() is callable", 15, ran and no_crashes,
                   "; ".join(report["crashes"][:2]) if report["crashes"] else "ok")
    works = w.axis("works", 40)

    # -- REQUESTED SCOPE ----------------------------------------------
    s = Tally()
    if report is None:
        s.item("valid numbers → True", 10, False, "module did not run")
        s.item("invalid numbers → False", 10, False, "module did not run")
        s.item("survives garbage input", 5, False, "module did not run")
    else:
        right_v = sum(1 for v in report["valid"] if v is True)
        s.ratio("valid numbers → True", 10, right_v / len(VALID),
                f"{right_v}/{len(VALID)}")
        right_i = sum(1 for v in report["invalid"] if v is False)
        s.ratio("invalid numbers → False", 10, right_i / len(INVALID),
                f"{right_i}/{len(INVALID)}")
        # Two separate items on purpose: not crashing is not enough — the
        # right answer for garbage is False. (A shell that just `return
        # True`d used to collect this item in full.)
        survived = sum(1 for v in report["garbage"] if v is not None)
        s.ratio("survives garbage input", 2, survived / len(GARBAGE),
                f"{survived}/{len(GARBAGE)} inputs raised nothing")
        right_g = sum(1 for v in report["garbage"] if v is False)
        s.ratio("garbage input → False", 3, right_g / len(GARBAGE),
                f"{right_g}/{len(GARBAGE)}")
    scope = s.axis("scope", 25)

    return [works, scope, grading.health_axis(root),
            grading.tests_axis(root, critical=CRITICAL)]


if __name__ == "__main__":
    raise SystemExit(grading.standalone(score, "k1-module"))
