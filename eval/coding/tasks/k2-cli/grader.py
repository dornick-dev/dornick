"""k2 — easy/Node: a CLI tool.

A CLI "working" means four externally measurable things: it accepts its
commands, its exit codes are right, it writes state to disk, and it does
not quietly report success on a command it does not know. The last one
matters: an error that exits 0 poisons every script that uses the tool.

Persistence is measured across SEPARATE processes — keeping the list in
memory inside one process does not satisfy "nothing is lost".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import grading  # noqa: E402
from grading import Axis, Tally  # noqa: E402

TITLE = "Node todo-list CLI"
DIFFICULTY = "easy"
LANGUAGE = "node"
CRITICAL = ("ekle", "liste", "bitir")

ONE = "süt al"
TWO = "faturayı öde"


def score(root: Path) -> list[Axis]:
    script = grading.find(root, "gorev.js", "gorev.mjs")
    if not grading.has_node():
        missing = Axis("works", 40, None, [], reason="node missing on this machine")
        return [missing,
                Axis("scope", 25, None, [], reason="node missing on this machine"),
                grading.health_axis(root),
                Axis("tests", 15, None, [], reason="node missing on this machine")]

    w = Tally()
    if script is None:
        for name, weight in (("gorev.js exists", 10), ("ekle works", 10),
                             ("liste works", 10),
                             ("unknown command errors", 10)):
            w.item(name, weight, False, "gorev.js not found")
        s = Tally()
        for name, weight in (("added items are listed", 10),
                             ("bitir changes the list", 8),
                             ("persists in gorevler.json", 7)):
            s.item(name, weight, False, "gorev.js not found")
        return [w.axis("works", 40), s.axis("scope", 25),
                grading.health_axis(root),
                grading.tests_axis(root, critical=CRITICAL, external=True)]

    where = script.parent
    name = script.name
    w.item("gorev.js exists", 10, True, str(script.relative_to(root)))

    # Clean slate: the agent may have added items while trying its own
    # tool, and those leftovers make the measurement unreadable. Measured
    # wound: in the list the agent left behind, item 1 was ALREADY done;
    # `bitir 1` changed nothing and a working feature lost points for
    # "no change". Persistence is measured with OUR additions from here
    # on — deleting does not weaken the measurement.
    leftover = grading.find(root, "gorevler.json")
    if leftover is not None:
        try:
            leftover.unlink()
            w.evidence.append("! the agent's leftover gorevler.json was "
                              "deleted before measuring (clean slate)")
        except OSError:
            pass

    add1 = grading.shell(["node", name, "ekle", ONE], cwd=where, timeout=45)
    add2 = grading.shell(["node", name, "ekle", TWO], cwd=where, timeout=45)
    w.item("ekle works", 10, add1.ok and add2.ok,
           add1.brief(140) if not add1.ok else f"exit {add1.code}/{add2.code}")

    list1 = grading.shell(["node", name, "liste"], cwd=where, timeout=45)
    w.item("liste works", 10, list1.ok, list1.brief(140))

    nonsense = grading.shell(["node", name, "zıpla"], cwd=where, timeout=45)
    w.item("unknown command errors", 10,
           nonsense.code is not None and nonsense.code != 0,
           f"exit code {nonsense.code}")
    works = w.axis("works", 40)

    # -- scope --------------------------------------------------------
    s = Tally()
    first_output = list1.both
    s.item("added items are listed", 10,
           ONE in first_output and TWO in first_output,
           f"«{ONE}»: {ONE in first_output}, «{TWO}»: {TWO in first_output}")

    done = grading.shell(["node", name, "bitir", "1"], cwd=where, timeout=45)
    list2 = grading.shell(["node", name, "liste"], cwd=where, timeout=45)
    changed = (done.ok and list2.ok
               and list2.both.strip() != first_output.strip()
               and TWO in list2.both)
    s.item("bitir changes the list (the other item stays)", 8, changed,
           "bitir exit " + str(done.code) +
           ("; list unchanged" if list2.both.strip() == first_output.strip()
            else "; list changed"))

    record = grading.find(root, "gorevler.json")
    persisted = False
    detail = "no gorevler.json"
    if record is not None:
        content = grading.read(record)
        persisted = ONE in content and TWO in content
        detail = f"{record.name}, {len(content)} chars"
        try:
            json.loads(content)
        except ValueError:
            detail += " (not valid JSON)"
            persisted = False
    s.item("persists in gorevler.json", 7, persisted, detail)
    scope = s.axis("scope", 25)

    return [works, scope, grading.health_axis(root),
            # The brief asked for no tests: measured, reported, not scored.
            grading.tests_axis(root, critical=CRITICAL, external=True)]


if __name__ == "__main__":
    raise SystemExit(grading.standalone(score, "k2-cli"))
