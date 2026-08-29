"""The coding benchmark rig's own tests (`eval/coding/`).

A grader cannot be used unmeasured: a faulty ruler looks like the model
failing, and weeks go to the wrong place. These tests pin three things:

  1. **A correct solution scores high.** Reference solutions are generated
     inside the tests (never committed) and run through the grader.
  2. **A broken/missing delivery scores low** and raises the
     broken-delivery flag.
  3. **It never claims to have measured what it could not.** An
     unmeasurable axis returns `None` and leaves the denominator;
     unrequested work is never scored.

Behaviour extraction is exercised with a fake session log: no inventions —
where there is no evidence, "unextractable".
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RIG = ROOT / "eval" / "coding"
sys.path.insert(0, str(RIG))

import behavior  # noqa: E402
import grading  # noqa: E402


def grader(task_id: str):
    """Load one task's grader module."""
    path = RIG / "tasks" / task_id / "grader.py"
    spec = importlib.util.spec_from_file_location(f"grader_test_{task_id}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed(task_id: str, target: Path) -> Path:
    source = RIG / "tasks" / task_id / "seed"
    target.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    return target


# -- rig integrity ------------------------------------------------------


def test_nine_tasks_across_three_difficulties_and_languages() -> None:
    """Task-set contract: 9 tasks, three difficulties, three languages."""
    folders = sorted(p for p in (RIG / "tasks").iterdir() if p.is_dir())
    assert len(folders) == 9, [p.name for p in folders]

    difficulties: dict[str, int] = {}
    languages: set[str] = set()
    for p in folders:
        assert (p / "task.md").is_file(), f"{p.name}: no raw brief"
        assert (p / "grader.py").is_file(), f"{p.name}: no grader"
        m = grader(p.name)
        difficulties[m.DIFFICULTY] = difficulties.get(m.DIFFICULTY, 0) + 1
        languages.add(m.LANGUAGE)
        assert m.TITLE
    assert difficulties == {"easy": 3, "medium": 3, "hard": 3}, difficulties
    assert languages == {"python", "php", "node"}, languages


def test_raw_briefs_carry_no_discipline_coaching() -> None:
    """The brief must read like a user: "write tests first", "verify",
    "plan step by step" would fake the measurement — we measure whether
    the agent does those things unprompted."""
    banned = ("write tests first", "test-driven", "step by step plan",
              "don't forget to verify", "verify yourself", "checklist",
              "clean code principles")
    for p in sorted((RIG / "tasks").iterdir()):
        if not p.is_dir():
            continue
        text = (p / "task.md").read_text(encoding="utf-8").casefold()
        for pattern in banned:
            assert pattern not in text, f"{p.name}: coaching «{pattern}»"


# -- Axis / Scorecard honesty -------------------------------------------


def test_unmeasurable_axis_leaves_the_denominator() -> None:
    card = grading.Scorecard("x", [
        grading.Axis("works", 40, 40.0),
        grading.Axis("scope", 25, 25.0),
        grading.Axis("health", 20, None, reason="no php"),
        grading.Axis("tests", 15, 15.0),
    ])
    assert card.measured_ceiling == 80
    assert card.score == pytest.approx(100.0)
    assert card.unmeasured == ["code health"]


def test_unrequested_axis_reported_but_not_scored() -> None:
    axis = grading.Axis("tests", 15, 0.0, external=True)
    card = grading.Scorecard("x", [grading.Axis("works", 40, 20.0), axis])
    assert card.measured_ceiling == 40
    assert card.score == pytest.approx(50.0)
    assert "not requested" in axis.render()


def test_no_score_when_works_is_unmeasurable() -> None:
    """No score without the carrier axis.

    A rule from a real run: the agent left its own `php -S` open, the
    measurement found the port held, works/scope went "unmeasurable",
    only code health (20/20) remained, and the normalised score came out
    **100.0**. A delivery we never saw run cannot take full marks.
    """
    card = grading.Scorecard("z2", [
        grading.Axis("works", 40, None, reason="port was held"),
        grading.Axis("scope", 25, None, reason="port was held"),
        grading.Axis("health", 20, 20.0),
        grading.Axis("tests", 15, 0.0, external=True),
    ])
    assert card.score is None
    assert card.as_dict()["score"] is None
    # When works WAS measured, another unmeasurable axis does not block it.
    fine = grading.Scorecard("x", [
        grading.Axis("works", 40, 40.0),
        grading.Axis("health", 20, None, reason="no php"),
    ])
    assert fine.score == pytest.approx(100.0)


def test_score_none_when_nothing_measurable() -> None:
    card = grading.Scorecard("x", [grading.Axis(name, ceiling, None)
                                   for name, ceiling in grading.AXES.items()])
    assert card.score is None
    assert card.as_dict()["score"] is None


def test_broken_delivery_flag_comes_from_the_works_axis() -> None:
    broken = grading.Scorecard("x", [grading.Axis("works", 40, 0.0)])
    fine = grading.Scorecard("x", [grading.Axis("works", 40, 1.0)])
    unmeasured = grading.Scorecard("x", [grading.Axis("works", 40, None)])
    assert broken.broken_delivery
    assert not fine.broken_delivery
    assert not unmeasured.broken_delivery, "unmeasurable is not broken"


def test_tally_skipped_item_drops_from_ceiling_too() -> None:
    t = grading.Tally()
    t.item("a", 10, True)
    t.skip("b", "no tool")
    axis = t.axis("works", 40)
    assert axis.earned == pytest.approx(40.0), "a skip must not dilute"
    assert any("unmeasurable" in e for e in axis.evidence)


def test_tally_all_skipped_makes_the_axis_unmeasurable() -> None:
    t = grading.Tally()
    t.skip("a", "no php")
    axis = t.axis("works", 40)
    assert axis.earned is None and axis.reason


# -- code health --------------------------------------------------------


def test_health_unmeasurable_in_an_empty_workshop(tmp_path: Path) -> None:
    axis = grading.health_axis(tmp_path)
    assert axis.earned is None and "no source files" in axis.reason


def test_health_catches_broken_syntax(tmp_path: Path) -> None:
    (tmp_path / "clean.py").write_text("def f():\n    return 1\n",
                                       encoding="utf-8")
    clean = grading.health_axis(tmp_path)
    (tmp_path / "broken.py").write_text("def f(:\n  ???\n", encoding="utf-8")
    broken = grading.health_axis(tmp_path)
    assert broken.earned is not None and clean.earned is not None
    assert broken.earned < clean.earned


def test_duplication_sees_copy_paste(tmp_path: Path) -> None:
    block = "\n".join(f"    x{i} = {i} + 1" for i in range(8))
    (tmp_path / "a.py").write_text(f"def a():\n{block}\n", encoding="utf-8")
    single, _ = grading.duplication([tmp_path / "a.py"])
    (tmp_path / "b.py").write_text(f"def b():\n{block}\n", encoding="utf-8")
    double, blocks = grading.duplication(
        [tmp_path / "a.py", tmp_path / "b.py"])
    assert single == 0.0
    assert double > 0.3 and blocks >= 1


# -- test quality -------------------------------------------------------


def test_no_tests_is_a_real_zero_not_unmeasurable(tmp_path: Path) -> None:
    (tmp_path / "code.py").write_text("def f():\n    return 1\n",
                                      encoding="utf-8")
    axis = grading.tests_axis(tmp_path, critical=("f",))
    assert axis.earned == 0.0, "we looked and there were none — not unmeasurable"


def test_freebie_assertions_lower_the_score(tmp_path: Path) -> None:
    good = tmp_path / "good"
    bad = tmp_path / "bad"
    for place in (good, bad):
        place.mkdir()
        (place / "code.py").write_text("def add(a, b):\n    return a + b\n",
                                       encoding="utf-8")
    (good / "test_code.py").write_text(
        "from code import add\n"
        "def test_one():\n    assert add(1, 2) == 3\n"
        "def test_two():\n    assert add(-1, 1) == 0\n",
        encoding="utf-8")
    (bad / "test_code.py").write_text(
        "def test_one():\n    assert True\n"
        "def test_two():\n    assert True\n",
        encoding="utf-8")
    a = grading.tests_axis(good, critical=("add",))
    b = grading.tests_axis(bad, critical=("add",))
    assert a.earned is not None and b.earned is not None
    assert a.earned > b.earned


# -- task graders: correct solutions high, broken deliveries low --------


CORRECT_TCKN = (
    "def dogrula(no):\n"
    "    if not isinstance(no, str) or len(no) != 11 or not no.isdigit():\n"
    "        return False\n"
    "    d = [int(c) for c in no]\n"
    "    if d[0] == 0:\n"
    "        return False\n"
    "    tenth = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7\n"
    "             - (d[1] + d[3] + d[5] + d[7])) % 10\n"
    "    if tenth != d[9]:\n"
    "        return False\n"
    "    return sum(d[:10]) % 10 == d[10]\n"
)


def test_k1_correct_solution_scores_near_full(tmp_path: Path) -> None:
    m = grader("k1-module")
    (tmp_path / "tckn.py").write_text(CORRECT_TCKN, encoding="utf-8")
    (tmp_path / "test_tckn.py").write_text(
        "from tckn import dogrula\n"
        "def test_valid():\n    assert dogrula('10000000146') is True\n"
        "def test_invalid():\n    assert dogrula('12345678901') is False\n"
        "def test_garbage():\n    assert dogrula(None) is False\n",
        encoding="utf-8")
    card = grading.Scorecard("k1", m.score(tmp_path))
    assert card.axis("works").earned == pytest.approx(40.0)
    assert card.axis("scope").earned == pytest.approx(25.0)
    assert card.score is not None and card.score > 80


def test_k1_no_files_is_a_broken_delivery(tmp_path: Path) -> None:
    m = grader("k1-module")
    card = grading.Scorecard("k1", m.score(tmp_path))
    assert card.broken_delivery
    assert card.score == pytest.approx(0.0)


def test_k1_lying_module_cannot_pass_scope(tmp_path: Path) -> None:
    """A module that answers True to everything "works" but fails scope."""
    m = grader("k1-module")
    (tmp_path / "tckn.py").write_text("def dogrula(no):\n    return True\n",
                                      encoding="utf-8")
    card = grading.Scorecard("k1", m.score(tmp_path))
    assert card.axis("works").earned == pytest.approx(40.0)
    assert (card.axis("scope").earned or 0) < 13, "rejects nothing invalid"


@pytest.mark.skipif(not grading.has_php(), reason="php missing on this machine")
def test_k3_fixed_file_takes_full_scope(tmp_path: Path) -> None:
    m = grader("k3-repair")
    seed("k3-repair", tmp_path)
    text = (tmp_path / "fatura.php").read_text(encoding="utf-8")
    text = text.replace("return $tutar + $oran;",
                        "return $tutar * (1 + $oran / 100);")
    text = text.replace("count($satirlar) - 1", "count($satirlar)")
    (tmp_path / "fatura.php").write_text(text, encoding="utf-8")
    card = grading.Scorecard("k3", m.score(tmp_path))
    assert card.axis("scope").earned == pytest.approx(25.0)
    assert card.score is not None and card.score > 85


@pytest.mark.skipif(not grading.has_php(), reason="php missing on this machine")
def test_k3_untouched_seed_fails_scope(tmp_path: Path) -> None:
    m = grader("k3-repair")
    seed("k3-repair", tmp_path)
    card = grading.Scorecard("k3", m.score(tmp_path))
    # The file runs (callable) but no case matches.
    assert (card.axis("works").earned or 0) > 30
    assert (card.axis("scope").earned or 0) < 5


def test_z3_untouched_seed_fails_regression(tmp_path: Path) -> None:
    m = grader("z3-hidden-bug")
    seed("z3-hidden-bug", tmp_path)
    card = grading.Scorecard("z3", m.score(tmp_path))
    assert (card.axis("scope").earned or 0) < 6, "all three bugs still there"
    evidence = " ".join(card.axis("works").evidence)
    assert "regression suite fully green" in evidence


def test_z3_three_fixes_go_green(tmp_path: Path) -> None:
    m = grader("z3-hidden-bug")
    seed("z3-hidden-bug", tmp_path)
    path = tmp_path / "sepet" / "sepet.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '    sepet[urun] = {"adet": adet, "fiyat": float(fiyat)}',
        '    varsa = sepet.get(urun)\n'
        '    if varsa:\n'
        '        varsa["adet"] += adet\n'
        '    else:\n'
        '        sepet[urun] = {"adet": adet, "fiyat": float(fiyat)}')
    text = text.replace("if tutar > 1000:", "if tutar >= 1000:")
    text = text.replace("if tutar > 500:", "if tutar >= 500:")
    text = text.replace("return round(net)", "return round(net, 2)")
    path.write_text(text, encoding="utf-8")
    card = grading.Scorecard("z3", m.score(tmp_path))
    assert card.axis("scope").earned == pytest.approx(25.0)
    assert card.axis("works").earned == pytest.approx(40.0)


def test_z3_loosening_the_test_earns_nothing(tmp_path: Path) -> None:
    """The escape hatch is welded shut: deleting the test cannot turn the
    regression green."""
    m = grader("z3-hidden-bug")
    seed("z3-hidden-bug", tmp_path)
    (tmp_path / "sepet" / "test_regresyon.py").write_text(
        "def test_all_good():\n    assert True\n", encoding="utf-8")
    card = grading.Scorecard("z3", m.score(tmp_path))
    evidence = " ".join(card.axis("works").evidence)
    assert "- regression suite fully green" in evidence, evidence


@pytest.mark.skipif(not grading.has_node(), reason="node missing on this machine")
def test_o3_seed_state_has_no_feature_but_green_regression(tmp_path: Path) -> None:
    m = grader("o3-feature")
    seed("o3-feature", tmp_path)
    card = grading.Scorecard("o3", m.score(tmp_path))
    evidence = " ".join(card.axis("works").evidence)
    assert "+ pristine tests green" in evidence
    assert (card.axis("scope").earned or 0) < 8, "lending not implemented yet"


# -- page health: where we actually got burned --------------------------


def test_z2_reads_the_login_forms_target() -> None:
    """Post wherever the form posts; assuming `index.php` unfairly zeroed
    a panel whose form posted to `giris.php`."""
    m = grader("z2-panel")
    assert m._target('<form method="post" action="giris.php">') == "giris.php"
    assert m._target('<form method="post" action="">') == "index.php"
    assert m._target('<form method="post">') == "index.php"
    assert m._target('<form action="/index.php?go=1">') == "index.php"


def test_z2_extracts_field_names_from_the_form() -> None:
    m = grader("z2-panel")
    form = ('<input type="text" name="username">'
            '<input type="password" name="password">')
    assert m._field_names(form) == ("username", "password")
    # No fields found → common names, no crash.
    assert m._field_names("<p>no form</p>") == ("kullanici", "sifre")


def test_page_healthy_needs_more_than_a_200() -> None:
    full = grading.Response(200, "<html>" + "x" * 300 + "</html>", {}, "u")
    empty = grading.Response(200, "<html></html>", {}, "u")
    crashed = grading.Response(
        200, "<html>" + "x" * 300 + "<br />Fatal error: Call to undefined "
        "function baglan() in /panel/ozet.php on line 12</html>", {}, "u")
    warned = grading.Response(
        200, "y" * 300 + "Warning: Undefined variable $kullanici", {}, "u")
    assert grading.page_healthy(full)[0]
    assert not grading.page_healthy(empty)[0]
    assert not grading.page_healthy(crashed)[0]
    assert not grading.page_healthy(warned)[0]


# -- number/order helpers -----------------------------------------------


def test_has_number_accepts_turkish_and_english_formats() -> None:
    assert grading.has_number("Total: 47.553,25 TL", 47553.25)
    assert grading.has_number("Total: 47553.25 TL", 47553.25)
    assert grading.has_number("Total: 47,553.25 TL", 47553.25)
    # One cent of rounding drift accepted; an arithmetic error not.
    assert grading.has_number("Total: 47.553,26 TL", 47553.25)
    assert not grading.has_number("Total: 47.553,30 TL", 47553.25)
    assert not grading.has_number("Total: 4.755,25 TL", 47553.25)


def test_has_number_does_not_glue_adjacent_lines() -> None:
    """Every number in a multi-line report must read separately. (Measured
    wound: a newline in the separator class made "47553.25\\n  2026" parse
    as one number and two of three correct months went missing.)"""
    text = ("Monthly revenue:\n  2026-01: 47553.25\n  2026-02: 33938.45\n"
            "  2026-03: 99286.90\n")
    for expected in (47553.25, 33938.45, 99286.90):
        assert grading.has_number(text, expected), expected


def test_in_order_only_passes_the_right_order() -> None:
    assert grading.in_order("1. Pompa 2. PLC 3. Sensor",
                            ["Pompa", "PLC", "Sensor"])
    assert not grading.in_order("1. PLC 2. Pompa 3. Sensor",
                                ["Pompa", "PLC", "Sensor"])


# -- behaviour extraction -----------------------------------------------


def write_log(path: Path, events: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False)
                              for e in events), encoding="utf-8")
    return path


def test_behavior_reads_the_verify_trail_from_the_shell(tmp_path: Path) -> None:
    path = write_log(tmp_path / "s.jsonl", [
        {"seq": 0, "kind": "meta", "content": "session_start", "meta": {}},
        {"seq": 1, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": "writing"}],
         "meta": {"usage": {"prompt_total": 1000, "output": 200}}},
        {"seq": 2, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "write_file", "input": {"path": "a.py"}}},
        {"seq": 3, "kind": "meta", "content": "tool_end",
         "meta": {"tool": "write_file", "error": False}},
        {"seq": 4, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "shell", "input": {"command": "py -m pytest -q"}}},
        {"seq": 5, "kind": "meta", "content": "tool_end",
         "meta": {"tool": "shell", "error": True}},
    ])
    b = behavior.extract(path)
    assert b["verified"] is True
    assert any("pytest" in x for x in b["verify_trail"])
    assert b["tool_calls"] == 2
    assert b["tool_errors"] == 1
    assert b["prompt_tokens_total"] == 1000
    assert b["output_tokens"] == 200


def test_behavior_does_not_invent_verification(tmp_path: Path) -> None:
    path = write_log(tmp_path / "s.jsonl", [
        {"seq": 0, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "write_file", "input": {"path": "a.py"}}},
        {"seq": 1, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "shell", "input": {"command": "mkdir new"}}},
    ])
    b = behavior.extract(path)
    assert b["verified"] is False
    assert b["verify_trail"] == []
    assert b["prompt_tokens_total"] is None
    assert "unmeasured" in b["token_note"]


def test_behavior_counts_diagnostics_and_browser_as_verification(tmp_path: Path) -> None:
    path = write_log(tmp_path / "s.jsonl", [
        {"seq": 0, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "denetle", "input": {"path": "panel"}}},
        {"seq": 1, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "browser", "input": {"action": "goto"}}},
    ])
    b = behavior.extract(path)
    assert b["verified"] is True
    assert len(b["verify_trail"]) == 2


def test_behavior_plan_counts_only_before_the_first_tool(tmp_path: Path) -> None:
    plan = "Here is the plan:\n1. write the module\n2. write tests\n3. run\n"
    before = write_log(tmp_path / "a.jsonl", [
        {"seq": 0, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": plan}], "meta": {}},
        {"seq": 1, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "write_file", "input": {}}},
    ])
    after = write_log(tmp_path / "b.jsonl", [
        {"seq": 0, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "write_file", "input": {}}},
        {"seq": 1, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": plan}], "meta": {}},
    ])
    assert behavior.extract(before)["wrote_plan"] is True
    assert behavior.extract(after)["wrote_plan"] is False, \
        "a summary written after the work is not a plan"


def test_behavior_missing_log_is_unextractable(tmp_path: Path) -> None:
    b = behavior.extract(tmp_path / "missing.jsonl")
    assert "unextractable" in b and "verified" not in b


def test_behavior_carries_the_gate_answer(tmp_path: Path) -> None:
    path = write_log(tmp_path / "s.jsonl", [
        {"seq": 0, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "shell", "input": {"command": "ls"}}}])
    b = behavior.extract(path, gate={"ok": True, "gecen_sn": 42.5,
                                     "dosyalar": ["a.py", "b.py"]})
    assert b["duration_s"] == 42.5 and b["changed_files"] == 2 and b["gate_ok"]


def test_behavior_unknown_price_means_none(tmp_path: Path) -> None:
    path = write_log(tmp_path / "s.jsonl", [
        {"seq": 0, "kind": "message", "role": "assistant", "content": [],
         "meta": {"usage": {"prompt_total": 500, "output": 100}}}])
    b = behavior.extract(path, model_name="nothing/in-catalogue-9999",
                         state_dir=tmp_path)
    assert b["cost_usd"] is None, "no invented figure for an unknown price"


# -- report generation --------------------------------------------------


def test_report_writes_unmeasurable_and_the_noise_warning(tmp_path: Path) -> None:
    import runner

    card = grading.Scorecard("k1-module", [
        grading.Axis("works", 40, 40.0, ["+ tckn.py exists (10p)"]),
        grading.Axis("scope", 25, 12.5, []),
        grading.Axis("health", 20, None, [], reason="no php"),
        grading.Axis("tests", 15, 3.0, [], external=True),
    ], behavior={"tool_calls": 7, "verified": False, "gate_ok": False,
                 "wrote_plan": True, "cost_usd": None})
    result = {
        "time": "20260827T000000Z", "model": "trial/model", "repetitions": 1,
        "tasks": [{"id": "k1-module", "title": "T", "difficulty": "easy",
                   "language": "python", "card": card.as_dict(),
                   "score_spread": None, "broken_deliveries": 0,
                   "carried_from": ""}],
        "not_run": ["z2-panel"], "axis_ceilings": grading.AXES,
    }
    path = tmp_path / "REPORT.md"
    runner.write_report(result, path)
    text = path.read_text(encoding="utf-8")
    assert "unmeasurable" in text
    assert "A single run is noise" in text
    assert "Not run:** z2-panel" in text
    assert "12.5" in text and "3.0*" in text
    assert "empty mind" in text, "the isolation boundary must be in the report"
    assert "Tasks graded before their turn finished:** k1-module" in text, \
        "hiding a half-finished turn makes the score look better than it is"


def test_report_marks_carried_rows(tmp_path: Path) -> None:
    """When one task is re-run and the report is produced whole, the row
    from the older run must not be hidden — the reader must see which
    number is from when."""
    import runner

    def row(task_id: str, carried_from: str) -> dict:
        card = grading.Scorecard(task_id, [grading.Axis("works", 40, 40.0)],
                                 behavior={"gate_ok": True})
        return {"id": task_id, "title": task_id, "difficulty": "easy",
                "language": "python", "card": card.as_dict(),
                "score_spread": None, "broken_deliveries": 0,
                "carried_from": carried_from}

    path = tmp_path / "REPORT.md"
    runner.write_report({
        "time": "20260827T120000Z", "model": "m", "repetitions": 1,
        "tasks": [row("k1-module", ""), row("k2-cli", "20260827T100000Z")],
        "not_run": [], "axis_ceilings": grading.AXES,
    }, path)
    text = path.read_text(encoding="utf-8")
    assert "| k2-cli† |" in text
    assert "| k1-module |" in text
    assert "k2-cli (20260827T100000Z)" in text


@pytest.mark.skipif(sys.platform != "win32",
                    reason="the process sweep is Windows-specific")
def test_no_processes_survive_the_workspace(tmp_path: Path) -> None:
    """When the turn ends, processes tied to the workspace go down — and
    ONLY those.

    They used not to: the agent's `php -S` and neo's own Chrome lived on
    after the turn. The cost landed on the measurement — one task took a
    FALSE 100.0 off a held port, and undeletable profile folders piled up
    in Temp.
    """
    import subprocess
    import time

    import runner

    def _long(inside: str) -> subprocess.Popen:
        # The path must reach the command line RAW: doubled backslashes via
        # `!r` do not mimic the real situation (`instance.py --workspace
        # C:\...`) and the sweep's pattern misses — the trap the first
        # version of this test fell into.
        return subprocess.Popen(
            [sys.executable, "-c",
             f'import time; _ = r"{inside}"; time.sleep(120)'])

    workspace = tmp_path / "ws"
    workspace.mkdir()
    tied = _long(str(workspace))    # workspace path in the command line
    stranger = _long("unrelated")
    try:
        time.sleep(1.5)
        assert tied.poll() is None and stranger.poll() is None

        assert runner.sweep_workspace(workspace) == 1
        time.sleep(1.0)
        assert tied.poll() is not None, "the tied process had to be killed"
        assert stranger.poll() is None, "an unrelated process must NEVER be"

        assert runner.sweep_workspace(workspace) == 0, \
            "an empty workspace must count zero"
    finally:
        for p in (tied, stranger):
            p.kill()


def test_carry_over_file_is_validated_before_the_run(tmp_path: Path) -> None:
    """A wrong `--previous` must surface BEFORE the run.

    It used to be read at the end: hours of paid work, then "wrong path"
    and everything in the bin. Given a folder, the newest run is picked so
    the user does not have to type timestamps.
    """
    import runner

    content, error = runner._read_previous(tmp_path / "missing.json")
    assert content is None and "unreadable" in error

    (tmp_path / "empty").mkdir()
    content, error = runner._read_previous(tmp_path / "empty")
    assert content is None and "no .json" in error

    (tmp_path / "wrong.json").write_text('{"other": 1}', encoding="utf-8")
    content, error = runner._read_previous(tmp_path / "wrong.json")
    assert content is None and "not a run file" in error

    # `wrong.json` sits in the folder and sorts last by name: picking by
    # name would have chosen this non-run file.
    for stamp in ("20260827T111835Z", "20260827T100000Z"):
        (tmp_path / f"{stamp}-m.json").write_text(
            json.dumps({"time": stamp, "tasks": []}), encoding="utf-8")
    content, error = runner._read_previous(tmp_path)
    assert error == "", error
    assert content is not None and content["time"] == "20260827T100000Z", \
        "the most recently WRITTEN run must be picked from a folder"


def test_excluded_files_leave_the_measurement(tmp_path: Path) -> None:
    """Files placed at boot that the agent did NOT touch must not enter
    code health; a file it touched must."""
    import runner

    skills = tmp_path / "yetenekler"
    skills.mkdir()
    (skills / "pdf_uret.py").write_text(
        "def run(a, c):\n" + "".join(
            f"{'    ' * (i + 1)}if a.get('{i}'):\n" for i in range(8))
        + "        " * 4 + "    return 1\n", encoding="utf-8")
    seeded = tmp_path / "seed_code.py"
    seeded.write_text("def old():\n    return 1\n", encoding="utf-8")

    before = runner.fingerprint(tmp_path)
    # The agent's turn: writes its own file, edits the seed, skips the skill.
    (tmp_path / "mine.py").write_text("def new():\n    return 2\n",
                                      encoding="utf-8")
    seeded.write_text("def old():\n    return 42\n", encoding="utf-8")

    assert runner.write_exclusions(tmp_path, before) == 1
    remaining = {p.name for p in grading.sources(tmp_path)}
    assert remaining == {"mine.py", "seed_code.py"}, remaining


def test_unittest_style_assertions_are_counted(tmp_path: Path) -> None:
    """Reviewer-caught artifact: assertTrue/assertIn/assertRaises were
    invisible to the assertion counter - nine green unittest asserts
    scored 0 assertions and the suite lost points for style."""
    (tmp_path / "mymod.py").write_text(
        "def add(a, b):" + chr(10) + "    return a + b" + chr(10),
        encoding="utf-8")
    satirlar = [
        "import unittest",
        "from mymod import add",
        "class T(unittest.TestCase):",
        "    def test_one(self):",
        "        self.assertEqual(add(1, 2), 3)",
        "    def test_two(self):",
        "        self.assertIn(3, [add(1, 2)])",
        "    def test_three(self):",
        "        self.assertRaises(TypeError, add, None, 1)",
        "if __name__ == \"__main__\":",
        "    unittest.main()",
    ]
    (tmp_path / "test_mymod.py").write_text(
        chr(10).join(satirlar) + chr(10), encoding="utf-8")
    axis = grading.tests_axis(tmp_path, critical=("add",))
    evidence = " ".join(axis.evidence)
    assert "0 assertions" not in evidence, evidence
    assert any(f"{n} assertions" in evidence for n in (3, 4)), evidence

def test_behavior_splits_wall_time_into_tool_and_model(tmp_path: Path) -> None:
    path = write_log(tmp_path / 's.jsonl', [
        {'seq': 0, 'kind': 'meta', 'content': 'tool_start',
         'meta': {'tool': 'shell', 'input': {'command': 'ls'}}},
        {'seq': 1, 'kind': 'meta', 'content': 'tool_end',
         'meta': {'tool': 'shell', 'error': False, 'ms': 1500}},
        {'seq': 2, 'kind': 'meta', 'content': 'tool_end',
         'meta': {'tool': 'shell', 'error': False, 'ms': 500}},
    ])
    b = behavior.extract(path, gate={'ok': True, 'gecen_sn': 10.0,
                                     'dosyalar': []})
    assert b['tool_time_s'] == 2.0
    assert b['model_time_s'] == 8.0


def test_behavior_counts_injected_and_used_primes(tmp_path: Path) -> None:
    # Two memories injected; only the report-folder one is acted on later.
    note = ('Kullanicinin son mesaji zihninde arandi; asagidakiler '
            'kendiliginden hatirlandi. Ilgiliyse kullan.' + chr(10)
            + '- [fact] quarterly report lives under reports/final' + chr(10)
            + '- [fact] deploy password rotates monthly via vault')
    path = write_log(tmp_path / 's.jsonl', [
        {'seq': 0, 'kind': 'message', 'role': 'user', 'content': 'find it',
         'meta': {}},
        {'seq': 1, 'kind': 'message', 'role': 'system', 'content': note,
         'meta': {}},
        {'seq': 2, 'kind': 'meta', 'content': 'tool_start',
         'meta': {'tool': 'read_file',
                  'input': {'path': 'reports/final/q3.md'}}},
    ])
    b = behavior.extract(path)
    assert b['primes_injected'] == 2
    assert b['primes_used'] == 1, 'vault memory was never touched'


def test_behavior_no_primes_reports_none_not_zero(tmp_path: Path) -> None:
    path = write_log(tmp_path / 's.jsonl', [
        {'seq': 0, 'kind': 'meta', 'content': 'tool_start',
         'meta': {'tool': 'shell', 'input': {'command': 'ls'}}}])
    b = behavior.extract(path)
    assert b['primes_injected'] is None and b['primes_used'] is None


def test_behavior_collects_the_top_error_patterns(tmp_path: Path) -> None:
    err = {'type': 'tool_result', 'is_error': True,
           'content': 'edit_file: old_string not found in panel.js'}
    ok = {'type': 'tool_result', 'is_error': False, 'content': 'done'}
    path = write_log(tmp_path / 's.jsonl', [
        {'seq': 0, 'kind': 'message', 'role': 'user',
         'content': [err, err, ok], 'meta': {}},
    ])
    b = behavior.extract(path)
    assert len(b['error_kinds']) == 1
    (kalip, adet), = b['error_kinds'].items()
    assert 'old_string' in kalip and adet == 2

