"""k3 — easy/PHP: find and fix the bug in a given broken file.

The seed carries two bugs, both feeding the single wrong number the user
sees:
  * `kdv_ekle` ADDS the rate instead of MULTIPLYING (70 + 18 = 88 instead
    of 70 × 1.18)
  * the `fatura_toplami` loop skips the LAST line via `count($satirlar) - 1`

The second one is sneaky: it is possible to fix the first bug, get "close
to 82.60" and stop. That is why the grader's cases catch them SEPARATELY —
the single-line case is sensitive only to the loop bug, the different-rate
case only to the VAT bug.

The grader never invokes anything the agent wrote directly: it writes its
own probe script into its own temp folder and `require`s `fatura.php`.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import grading  # noqa: E402
from grading import Axis, Tally  # noqa: E402

TITLE = "Find and fix the PHP invoice bug"
DIFFICULTY = "easy"
LANGUAGE = "php"
CRITICAL = ("fatura_toplami", "kdv_ekle")

# (name, lines, rate, expected)
CASES = [
    ("three lines 18%", [(2, 10.0), (1, 30.0), (4, 5.0)], 18.0, 82.60),
    ("single line 20%", [(3, 7.5)], 20.0, 27.00),
    ("two lines 0%", [(2, 12.5), (2, 12.5)], 0.0, 50.00),
    ("empty order", [], 18.0, 0.00),
]

_PROBE = """<?php
require_once %(file)s;
// Cases are embedded as JSON text: PHP array syntax rejects a JSON object
// literal, json_decode is the one honest route.
$cases = json_decode(%(cases)s, true);
$out = [];
foreach ($cases as $c) {
    $lines = [];
    foreach ($c['lines'] as $l) {
        $lines[] = ['adet' => $l[0], 'fiyat' => $l[1]];
    }
    try {
        $out[] = fatura_toplami($lines, $c['rate']);
    } catch (Throwable $e) {
        $out[] = null;
    }
}
echo "###" . json_encode($out) . PHP_EOL;
"""


def _run_cases(file: Path) -> list[float | None] | None:
    cases = [{"lines": [list(l) for l in lines], "rate": rate}
             for _, lines, rate, _ in CASES]
    script = _PROBE % {
        "file": json.dumps(str(file)),
        "cases": json.dumps(json.dumps(cases)),
    }
    with tempfile.TemporaryDirectory(prefix="dornick-k3-") as tmp:
        path = Path(tmp) / "probe.php"
        path.write_text(script, encoding="utf-8")
        run = grading.shell(["php", str(path)], cwd=tmp, timeout=60)
    for line in run.both.splitlines():
        if line.startswith("###"):
            try:
                raw = json.loads(line[3:])
            except ValueError:
                return None
            return [None if v is None else float(v) for v in raw]
    return None


def score(root: Path) -> list[Axis]:
    if not grading.has_php():
        reason = "php missing on this machine"
        return [Axis("works", 40, None, [], reason=reason),
                Axis("scope", 25, None, [], reason=reason),
                grading.health_axis(root),
                Axis("tests", 15, None, [], reason=reason, external=True)]

    file = grading.find(root, "fatura.php")

    w = Tally()
    result: list[float | None] | None = None
    if file is None:
        w.item("fatura.php still there", 10, False, "not found in the workshop")
        w.item("php -l clean", 10, False, "no file")
        w.item("function callable from outside", 20, False, "no file")
    else:
        w.item("fatura.php still there", 10, True, str(file.relative_to(root)))
        lint = grading.shell(["php", "-l", str(file)], timeout=40)
        w.item("php -l clean", 10, lint.ok, lint.brief(140))
        result = _run_cases(file)
        w.item("function callable from outside", 20,
               result is not None and any(v is not None for v in result),
               "ok" if result else "require/call failed")
    works = w.axis("works", 40)

    s = Tally()
    weights = {0: 10.0, 1: 7.0, 2: 5.0, 3: 3.0}
    for i, (name, _lines, _rate, expected) in enumerate(CASES):
        got = result[i] if result and i < len(result) else None
        right = got is not None and abs(got - expected) < 0.005
        s.item(f"case: {name}", weights[i], right,
               f"expected {expected:.2f}, got "
               f"{'error' if got is None else f'{got:.2f}'}")
    scope = s.axis("scope", 25)

    return [works, scope, grading.health_axis(root),
            # The brief asked for no tests. Still measured: a test that
            # verifies your own fix is quality even when nobody asked.
            grading.tests_axis(root, critical=CRITICAL, external=True)]


if __name__ == "__main__":
    raise SystemExit(grading.standalone(score, "k3-repair"))
