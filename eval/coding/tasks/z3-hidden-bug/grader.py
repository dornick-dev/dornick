"""z3 — hard/Python: find and fix 3 hidden bugs in the seed project.

The three bugs in the seed:
  1. `ekle` OVERWRITES an existing product's quantity instead of adding.
  2. `indirim_orani` excludes the boundary (`>` should be `>=`) — spending
     exactly 1000 TL earns 5%.
  3. `toplam` rounds away the cents (`round(net)` instead of `round(net, 2)`).

The grader does two separate jobs, and both are escape-proof:

  * **Regression:** the SEED's `test_regresyon.py` is written over the
    copy of the workshop and run there. Loosening the test does nothing.
  * **Hidden cases:** each bug is probed with numbers that appear NOWHERE
    in the visible test. Hardcoding the visible test's expected values
    into the code does nothing either.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import grading  # noqa: E402
from grading import Axis, Tally  # noqa: E402

TITLE = "Find and fix the 3 hidden bugs in the cart module"
DIFFICULTY = "hard"
LANGUAGE = "python"
CRITICAL = ("ekle", "indirim_orani", "toplam")
SEED_TEST = (Path(__file__).resolve().parent / "seed" / "sepet"
             / "test_regresyon.py")

# Hidden cases: numbers absent from the visible test.
_PROBE = r"""
import json, sys
sys.path.insert(0, {folder!r})
import sepet as m
r = {{}}
def step(name, fn):
    try: r[name] = {{"ok": True, "value": fn()}}
    except Exception as e: r[name] = {{"ok": False, "error": repr(e)}}

def three_adds():
    s = {{}}
    m.ekle(s, "conta", 3.0, 1); m.ekle(s, "conta", 3.0, 2); m.ekle(s, "conta", 3.0, 4)
    return [m.kalem_sayisi(s), m.ara_toplam(s)]
step("adds_accumulate", three_adds)

step("edge_500", lambda: m.indirim_orani(500.0))
step("edge_1000", lambda: m.indirim_orani(1000.0))
step("edge_499", lambda: m.indirim_orani(499.99))

def fifteen_hundred():
    s = {{}}; m.ekle(s, "pompa", 750.0, 2); return m.toplam(s)
step("ten_percent", fifteen_hundred)

def cents():
    s = {{}}; m.ekle(s, "vida", 14.29, 7); return m.toplam(s)
step("cents_survive", cents)

def exactly_500():
    s = {{}}; m.ekle(s, "role", 250.0, 2); return m.toplam(s)
step("exact_500_discounted", exactly_500)

def negative():
    try:
        m.ekle({{}}, "x", 5.0, 0); return "DID-NOT-RAISE"
    except ValueError:
        return "ValueError"
step("guard_intact", negative)

print("###" + json.dumps(r))
"""


def _hidden(folder: Path) -> dict | None:
    run = grading.shell([sys.executable, "-c",
                         _PROBE.format(folder=str(folder))],
                        cwd=folder, timeout=60)
    for line in run.both.splitlines():
        if line.startswith("###"):
            try:
                return json.loads(line[3:])
            except ValueError:
                return None
    return None


def _regression(root: Path) -> grading.Run | None:
    """Run the seed's PRISTINE regression suite in a copy of the workshop."""
    with tempfile.TemporaryDirectory(prefix="neocp-z3-reg-") as tmp:
        target = Path(tmp) / "workshop"
        try:
            shutil.copytree(root, target,
                            ignore=shutil.ignore_patterns(*grading.SKIP_DIRS))
        except OSError:
            return None
        copy = grading.find(target, "sepet.py")
        if copy is None:
            return None
        shutil.copyfile(SEED_TEST, copy.parent / "test_regresyon.py")
        return grading.shell(
            [sys.executable, "-m", "pytest", "-q", "--no-header",
             "-p", "no:cacheprovider", "test_regresyon.py"],
            cwd=copy.parent, timeout=180)


def score(root: Path) -> list[Axis]:
    module = grading.find(root, "sepet.py")

    w = Tally()
    hidden: dict | None = None
    if module is None:
        for name, weight in (("sepet.py still there", 6),
                             ("module imports", 10),
                             ("pristine regression suite runs", 8),
                             ("regression suite fully green", 16)):
            w.item(name, weight, False, "sepet.py not found")
    else:
        w.item("sepet.py still there", 6, True, str(module.relative_to(root)))
        hidden = _hidden(module.parent)
        w.item("module imports", 10, hidden is not None,
               "ok" if hidden else "import blew up")
        reg = _regression(root)
        if reg is None or reg.code is None:
            w.skip("pristine regression suite runs",
                   reg.crash if reg else "regression copy could not be built")
            w.skip("regression suite fully green", "suite could not run")
        else:
            w.item("pristine regression suite runs", 8,
                   "passed" in reg.both or "failed" in reg.both,
                   reg.brief(120))
            w.item("regression suite fully green", 16, reg.ok, reg.brief(200))
    works = w.axis("works", 40)

    # -- hidden cases: each bug on its own --------------------------
    s = Tally()
    h = hidden or {}

    def value(name: str):
        d = h.get(name)
        return d.get("value") if d and d.get("ok") else None

    acc = value("adds_accumulate")
    s.item("bug 1: re-adding a product accumulates", 8,
           acc == [7, 21.0], f"expected [7, 21.0], got {acc!r}")

    edges = (value("edge_500"), value("edge_1000"), value("edge_499"))
    edges_right = (edges[0] == 0.05 and edges[1] == 0.10 and edges[2] == 0.0)
    s.item("bug 2: discount boundaries inclusive", 8, edges_right,
           f"500→{edges[0]!r} (0.05), 1000→{edges[1]!r} (0.10), "
           f"499.99→{edges[2]!r} (0.0)")

    cents = value("cents_survive")
    s.item("bug 3: total keeps the cents", 6,
           cents is not None and abs(float(cents) - 100.03) < 0.005,
           f"7 × 14.29 → expected 100.03, got {cents!r}")

    ten = value("ten_percent")
    exact = value("exact_500_discounted")
    s.item("hidden case: 1500 → 10%, 500 → 5%", 2,
           ten is not None and abs(float(ten) - 1350.0) < 0.005
           and exact is not None and abs(float(exact) - 475.0) < 0.005,
           f"1500→{ten!r} (1350.0), 500→{exact!r} (475.0)")

    s.item("existing guard survived (quantity 0 → ValueError)", 1,
           value("guard_intact") == "ValueError",
           str(h.get("guard_intact", "step never ran"))[:100])
    scope = s.axis("scope", 25)

    tests = grading.tests_axis(root, critical=CRITICAL, external=True)
    tests.evidence.insert(0, "! the regression suite ships with the seed — "
                             "this axis cannot isolate the agent's own "
                             "contribution, so it is not scored")

    return [works, scope, grading.health_axis(root), tests]


if __name__ == "__main__":
    raise SystemExit(grading.standalone(score, "z3-hidden-bug"))
