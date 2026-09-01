"""o3 — medium/Node: add a feature to an existing project without breaking it.

The real measurement here is REGRESSION: the agent saying "the existing
tests pass" is not enough — the PRISTINE copy of the suite is run. The
workshop is copied to a temp folder, the seed's `kitaplik.test.js` is
written over whatever is there, and the suite runs in the copy. Getting
green by loosening a test is impossible in this setup.

The new behaviour is measured by the grader's own probe script, not by the
agent's tests.
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

TITLE = "Add lending to the library (existing tests must not break)"
DIFFICULTY = "medium"
LANGUAGE = "node"
CRITICAL = ("oduncVer", "iadeAl")
SEED_TEST = Path(__file__).resolve().parent / "seed" / "kitaplik.test.js"

_PROBE = """'use strict';
const { Kitaplik } = require(%(module)s);
const report = { loaded: true, steps: {} };
function step(name, fn) {
  try { report.steps[name] = { ok: true, value: fn() }; }
  catch (e) { report.steps[name] = { ok: false, error: String(e && e.message || e) }; }
}
const k = new Kitaplik();
step('setup', () => { k.ekle('978-1', 'Kuyu', 'Ahmet'); k.ekle('978-2', 'Zeytin', 'Ayse'); return k.sayi; });
step('oduncVer', () => k.oduncVer('978-1', 'Fatih'));
step('shows_in_list', () => JSON.stringify(k.liste()));
step('second_lend_must_throw', () => { k.oduncVer('978-1', 'Mehmet'); return 'DID-NOT-THROW'; });
step('missing_isbn_must_throw', () => { k.oduncVer('no-such', 'Fatih'); return 'DID-NOT-THROW'; });
step('iadeAl', () => k.iadeAl('978-1'));
step('relend_after_return', () => { k.oduncVer('978-1', 'Mehmet'); return 'ok'; });
step('list_after_return', () => JSON.stringify(k.liste()));
console.log('###' + JSON.stringify(report));
"""


def _probe(module: Path) -> dict | None:
    script = _PROBE % {"module": json.dumps(str(module).replace("\\", "/"))}
    with tempfile.TemporaryDirectory(prefix="dornick-o3-") as tmp:
        path = Path(tmp) / "probe.js"
        path.write_text(script, encoding="utf-8")
        run = grading.shell(["node", str(path)], cwd=tmp, timeout=60)
    for line in run.both.splitlines():
        if line.startswith("###"):
            try:
                return json.loads(line[3:])
            except ValueError:
                return None
    return None


def _regression(root: Path) -> grading.Run | None:
    """Run the seed's PRISTINE test suite in a copy of the workshop."""
    with tempfile.TemporaryDirectory(prefix="dornick-o3-reg-") as tmp:
        target = Path(tmp) / "workshop"
        try:
            shutil.copytree(root, target,
                            ignore=shutil.ignore_patterns(*grading.SKIP_DIRS))
        except OSError:
            return None
        module = grading.find(target, "kitaplik.js")
        if module is None:
            return None
        # The agent may have edited the test: the original is written over it.
        shutil.copyfile(SEED_TEST, module.parent / "kitaplik.test.js")
        return grading.shell(["node", "--test"], cwd=module.parent, timeout=120)


def score(root: Path) -> list[Axis]:
    if not grading.has_node():
        reason = "node missing on this machine"
        return [Axis("works", 40, None, [], reason=reason),
                Axis("scope", 25, None, [], reason=reason),
                grading.health_axis(root),
                Axis("tests", 15, None, [], reason=reason, external=True)]

    module = grading.find(root, "kitaplik.js")
    w = Tally()
    report: dict | None = None

    if module is None:
        for name, weight in (("kitaplik.js still there", 8),
                             ("node --check clean", 6),
                             ("module loads", 8),
                             ("pristine tests green", 18)):
            w.item(name, weight, False, "kitaplik.js not found")
    else:
        w.item("kitaplik.js still there", 8, True, str(module.relative_to(root)))
        check = grading.shell(["node", "--check", str(module)], timeout=40)
        w.item("node --check clean", 6, check.ok, check.brief(140))
        report = _probe(module)
        w.item("module loads", 8, report is not None,
               "ok" if report else "require blew up")
        reg = _regression(root)
        if reg is None or reg.code is None:
            w.skip("pristine tests green",
                   reg.crash if reg else "regression copy could not be built")
        else:
            w.item("pristine tests green", 18, reg.ok, reg.brief(180))
    works = w.axis("works", 40)

    s = Tally()
    steps = (report or {}).get("steps") or {}

    def passed(name: str) -> bool:
        return bool(steps.get(name, {}).get("ok"))

    def must_throw(name: str) -> bool:
        """A step EXPECTED to throw: throwing means pass.

        The precondition is necessary: with `oduncVer` MISSING entirely,
        the call also blows up with "is not a function" and a naive check
        read that as "threw correctly" — an agent that wrote nothing was
        collecting two items for free. The feature must first work, then
        hold its boundary.
        """
        if not passed("oduncVer"):
            return False
        d = steps.get(name)
        return bool(d) and not d.get("ok")

    s.item("oduncVer works", 6, passed("oduncVer"),
           str(steps.get("oduncVer", "step never ran"))[:120])
    listing = str(steps.get("shows_in_list", {}).get("value", ""))
    visible = passed("shows_in_list") and "Fatih" in listing
    s.item("liste shows who has the book", 5, visible,
           listing[:140] or "list unavailable")
    s.item("second lend throws", 6, must_throw("second_lend_must_throw"),
           str(steps.get("second_lend_must_throw", "step never ran"))[:120])
    s.item("missing ISBN throws", 4, must_throw("missing_isbn_must_throw"),
           str(steps.get("missing_isbn_must_throw", "step never ran"))[:120])
    s.item("iadeAl frees the book", 4,
           passed("iadeAl") and passed("relend_after_return"),
           str(steps.get("iadeAl", "step never ran"))[:120])
    scope = s.axis("scope", 25)

    tests = grading.tests_axis(root, critical=CRITICAL, external=True)
    tests.evidence.insert(0, "! the seed already ships a test suite — this "
                             "axis cannot isolate the agent's own "
                             "contribution, so it is not scored")

    return [works, scope, grading.health_axis(root), tests]


if __name__ == "__main__":
    raise SystemExit(grading.standalone(score, "o3-feature"))
