"""Can the character harness itself be trusted?

Roadmap 7.6 measures whether Dornick's character survives a change of
project, of day and of model. Before a single paid call is worth making,
the rig has to be shown to (1) validate its own decision set, (2) run end
to end on a deterministic fake model and give the same numbers twice,
(3) really pin `target = baseline` on the `--no-leverage` control arm so
the prompt carries no guidance line, and (4) parse answers without ever
guessing — an answer that does not name exactly one option is ambiguous,
not "probably the second one".
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_PATH = ROOT / "eval" / "karakter" / "run.py"


def _harness():
    """Loads the rig as a module (eval/ is not a package)."""
    spec = importlib.util.spec_from_file_location("karakter_run", RUN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["karakter_run"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def harness():
    return _harness()


@pytest.fixture(scope="module")
def decisions(harness):
    data, rows = harness.load_decisions()
    assert harness.validate_decisions(data) == []
    return rows


def _fakes(harness, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    return [harness.fake_model("sahte-a", ws), harness.fake_model("sahte-b", ws)]


# -- the decision set -----------------------------------------------------


def test_the_set_validates(harness) -> None:
    data, _rows = harness.load_decisions()
    assert harness.validate_decisions(data) == []


def test_thirty_decisions_six_per_axis_three_contexts_each(harness, decisions) -> None:
    assert len(decisions) == 30
    assert Counter(d.axis for d in decisions) == {axis: 6 for axis in harness.AXES}
    assert len({d.id for d in decisions}) == 30
    for d in decisions:
        assert len(d.contexts) == 3 and len(set(d.contexts)) == 3
        assert len(d.options) == 2 and d.options[0] != d.options[1]
        assert d.high in d.options and d.low in d.options and d.high != d.low


def test_six_mixed_decisions_pit_two_axes(harness, decisions) -> None:
    mixed = [d for d in decisions if d.mixed]
    assert len(mixed) == 6
    for d in mixed:
        assert d.secondary in harness.AXES and d.secondary != d.axis


def test_context_variants_do_not_change_the_decision(harness, decisions) -> None:
    """The three renderings differ in the context line only: same message,
    same options, same answer rule."""
    for d in decisions:
        rendered = [harness.render_message(d, v) for v in range(3)]
        assert len(set(rendered)) == 3
        for text in rendered:
            assert d.message in text and "KARAR:" in text
            assert d.options[0] in text and d.options[1] in text
        # Drop the context line and the three become one.
        tails = {text.split("\n\n", 1)[1] for text in rendered}
        assert len(tails) == 1


def test_the_validator_catches_a_broken_set(harness) -> None:
    data, _rows = harness.load_decisions()
    broken = json.loads(json.dumps(data))
    broken["kararlar"][0]["id"] = broken["kararlar"][1]["id"]
    broken["kararlar"][2]["yuksek"] = "yok böyle bir seçenek"
    broken["kararlar"][3]["baglamlar"] = ["a", "a", "b"]
    del broken["kararlar"][4]
    problems = harness.validate_decisions(broken)
    assert any("tekil" in p for p in problems)
    assert any("yuksek" in p for p in problems)
    assert any("bağlam" in p for p in problems)
    assert any("30 karar" in p for p in problems)


def test_the_sample_identity_document_obeys_the_identity_rules(harness) -> None:
    """The dry run's document must pass the same four rules the night
    enforces on the real one — otherwise the ablation measures a document
    the product could never have written."""
    from dornick.recall import identity

    parsed = identity.parse(harness.SAMPLE_IDENTITY)
    assert len(parsed.sentences) == harness.SAMPLE_IDENTITY.count("\n") + 1
    for text, evidence in parsed.sentences:
        identity.check(text, evidence)   # raises on an adjective or missing evidence


# -- the parser -------------------------------------------------------------


OPTIONS = ("sorarım", "yaparım")


@pytest.mark.parametrize("text, expected", [
    ("Gerekçe.\nKARAR: sorarım", "sorarım"),
    ("Gerekçe.\n**KARAR: yaparım**", "yaparım"),
    ("KARAR: «sorarım».", "sorarım"),
    ("karar: Yaparım", "yaparım"),
    ("Önce şunu düşündüm.\n\nKARAR: sorarım\n", "sorarım"),
    ("KARAR: bu durumda sorarım", "sorarım"),
])
def test_the_parser_reads_the_karar_line(harness, text: str, expected: str) -> None:
    assert harness.parse_decision(text, OPTIONS) == expected


@pytest.mark.parametrize("text", [
    "",
    "Sorarım herhalde.",                          # no KARAR line
    "KARAR: sorarım ya da yaparım",               # both options
    "KARAR: bilmem",                              # neither option
    "KARAR: sorarım\nKARAR: yaparım",             # two lines that disagree
    "KARAR:",                                     # empty label
])
def test_the_parser_refuses_ambiguity(harness, text: str) -> None:
    with pytest.raises(harness.Ambiguous):
        harness.parse_decision(text, OPTIONS)


def test_an_ambiguous_answer_never_counts_as_agreement(harness) -> None:
    assert harness._agreement([("a", "a"), (None, None), ("a", None)]) == pytest.approx(1 / 3, abs=1e-4)
    assert harness._agreement([]) is None


# -- end to end on the fake model -------------------------------------------


@pytest.fixture(scope="module")
def dry_result(harness, decisions, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("kuru")
    return harness.run(decisions, _fakes(harness, tmp), target=harness.DRY_TARGET,
                       identity_doc=harness.SAMPLE_IDENTITY, repeats=2,
                       root=tmp / "durum")


def test_every_metric_is_a_share_or_a_difference(harness, dry_result) -> None:
    metrics = dry_result["metrikler"]
    assert set(metrics) == set(harness.TARGETS)
    shares = {"tutarlilik_baglam", "tutarlilik_zaman", "tutarlilik_zaman_kimliksiz",
              "tutarlilik_model", "tutarlilik_model_kaldiracsiz",
              "sosyal_taban", "sosyal_ulasilan", "belirsiz_oran"}
    for name, value in metrics.items():
        assert value is None or isinstance(value, (int, float)), name
        if name in shares and value is not None:
            assert 0.0 <= value <= 1.0, name
        elif value is not None:                       # a difference of two shares
            assert -1.0 <= value <= 1.0, name
    for model in dry_result["modeller"].values():
        for axis, value in model["taban"].items():
            assert 0.0 <= value <= 1.0, axis
        for axis, value in model["ulasilan"].items():
            assert value is None or 0.0 <= value <= 1.0, axis


def test_the_call_count_matches_the_plan(harness, dry_result) -> None:
    """What the cost guard prints is what the run does."""
    assert dry_result["sayim"]["cagri"] == harness.plan_calls(2, 2, leverage_on=True)
    # Baseline is 30 decisions x 3 context variants (90 per model).
    assert harness.plan_calls(2, 3, leverage_on=True) == 840
    assert harness.plan_calls(1, 3, leverage_on=False) == 330


def test_each_arm_carries_the_prompt_it_claims(harness, dry_result) -> None:
    """The prompt marks come from the product's own `prompt.build`, so this
    is also the proof that leverage and identity really reach the model."""
    for model in dry_result["modeller"].values():
        arms = model["kollar"]
        assert arms["taban"] == {"kaldirac_satiri": False, "kimlik_blogu": False, "ornek_blogu": False}
        assert arms["tam"] == {"kaldirac_satiri": True, "kimlik_blogu": True, "ornek_blogu": False}
        assert arms["kaldiracsiz"] == {"kaldirac_satiri": False, "kimlik_blogu": True, "ornek_blogu": False}
        assert arms["kimliksiz"] == {"kaldirac_satiri": True, "kimlik_blogu": False, "ornek_blogu": False}


def test_the_ablations_move_the_right_way_on_the_fake(dry_result) -> None:
    """The fake is built so the mechanisms matter; if the rig cannot see
    that, it would not see it on a real model either."""
    m = dry_result["metrikler"]
    assert m["kaldirac_farki"] > 0
    assert m["kimlik_farki"] > 0
    assert m["belirsiz_oran"] == 0


def test_the_same_run_gives_the_same_numbers(harness, decisions, dry_result, tmp_path) -> None:
    again = harness.run(decisions, _fakes(harness, tmp_path), target=harness.DRY_TARGET,
                        identity_doc=harness.SAMPLE_IDENTITY, repeats=2,
                        root=tmp_path / "durum")
    assert again["metrikler"] == dry_result["metrikler"]
    assert again["modeller"] == dry_result["modeller"]


def test_the_control_arm_pins_target_to_the_measured_baseline(harness, decisions, tmp_path) -> None:
    """`--no-leverage`: target = baseline, leverage 1.0 on every axis, and
    the system prompt carries no guidance line — on any arm."""
    result = harness.run(decisions, _fakes(harness, tmp_path), target=harness.DRY_TARGET,
                         identity_doc=harness.SAMPLE_IDENTITY, repeats=2,
                         leverage_on=False, root=tmp_path / "durum")
    for name, model in result["modeller"].items():
        assert model["hedef"] == model["taban"], name
        assert set(model["kaldirac"].values()) == {1.0}, name
        assert "tam" not in model["kollar"]
        for arm, marks in model["kollar"].items():
            assert marks["kaldirac_satiri"] is False, (name, arm)
    # What was written to disk says the same thing.
    for state in (tmp_path / "durum").glob("*/kaldiracsiz/mizac.json"):
        saved = json.loads(state.read_text(encoding="utf-8"))
        assert saved["hedef"] == saved["taban"]
    assert result["metrikler"]["tutarlilik_model"] is None
    assert result["metrikler"]["kaldirac_farki"] is None
    assert result["metrikler"]["tutarlilik_model_kaldiracsiz"] is not None
    assert any("kaldıraçsız" in note for note in result["notlar"])


def test_the_leverage_arm_really_writes_the_target(harness, decisions, tmp_path) -> None:
    result = harness.run(decisions, _fakes(harness, tmp_path), target=harness.DRY_TARGET,
                         identity_doc=harness.SAMPLE_IDENTITY, repeats=1,
                         root=tmp_path / "durum")
    for model in result["modeller"].values():
        assert model["hedef"] == harness.DRY_TARGET.as_dict()
        assert model["hedef"] != model["taban"]
    assert result["metrikler"]["tutarlilik_zaman"] is None     # one repeat, no pairs


def test_the_baseline_is_read_by_the_products_own_measure(harness, decisions, tmp_path, monkeypatch) -> None:
    """The baseline arm goes through `temperament.measure()`, not a copy."""
    from dornick.recall import temperament

    seen: list[int] = []
    original = temperament.measure

    def spy(probes, answer):
        seen.append(len(probes))
        return original(probes, answer)

    monkeypatch.setattr(harness.temperament, "measure", spy)
    harness.run(decisions, _fakes(harness, tmp_path)[:1], target=harness.DRY_TARGET,
                identity_doc=harness.SAMPLE_IDENTITY, repeats=1, root=tmp_path / "durum")
    assert seen == [90]


def test_the_report_files_are_written_in_the_charts_style(harness, dry_result, tmp_path) -> None:
    json_path, md_path = harness.write_report("test", dry_result, tmp_path / "charts",
                                              command="py eval/karakter/run.py", source="sahte")
    assert json_path.name == "karakter-test.json" and md_path.name == "karakter-test.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["metrikler"] == dry_result["metrikler"]
    text = md_path.read_text(encoding="utf-8")
    assert text.startswith("# Karakter tutarlılığı — `test`")
    assert "| `tutarlilik_model` |" in text and ">= 0.8" in text
    assert "`sahte-a`" in text and "`sahte-b`" in text
    assert "yok" in text     # never blank


# -- the command line -----------------------------------------------------


def _cli(args: list[str], tmp_path: Path) -> subprocess.CompletedProcess:
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, str(RUN_PATH), *args, "--workspace", str(ws),
         "--charts", str(tmp_path / "charts")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=600)


def test_the_cli_runs_dry_and_prints_json(tmp_path) -> None:
    out = _cli(["--dry", "--json", "--repeats", "2"], tmp_path)
    assert out.returncode == 0, out.stderr[-2000:]
    result = json.loads(out.stdout)
    assert result["veri"] == "karakter-30"
    assert (tmp_path / "charts" / "karakter-kuru.json").exists()
    assert (tmp_path / "charts" / "karakter-kuru.md").exists()


def test_without_evet_the_cli_spends_nothing_and_names_the_price(tmp_path) -> None:
    """Real model ids without `--evet`: the call count is printed and the
    run falls back to the fake — no backend is ever built."""
    out = _cli(["--model", "anthropic:claude-opus-4-8", "--model2", "openai:yerel/model",
                "--repeats", "3", "--json"], tmp_path)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "840" in out.stderr and "--evet" in out.stderr
    result = json.loads(out.stdout)
    assert set(result["modeller"]) == {"sahte-a", "sahte-b"}
    assert result["sayim"]["cagri"] == 840


def test_the_model_spec_keeps_openrouter_colons(harness) -> None:
    assert harness.parse_model_spec("anthropic:claude-opus-4-8") == ("anthropic", "claude-opus-4-8")
    assert harness.parse_model_spec("openai:qwen/qwen3-32b:free") == ("openai", "qwen/qwen3-32b:free")
    assert harness.parse_model_spec("qwen/qwen3-32b:free") == (None, "qwen/qwen3-32b:free")


def test_a_real_model_config_is_cold_and_has_no_fallback(harness, tmp_path) -> None:
    """Temperature 0, thinking off, no fallback: a fallback would answer
    with another model behind the measurement's back."""
    config = harness.product_config("anthropic:claude-opus-4-8", workspace=tmp_path)
    assert config.model.provider == "anthropic"
    assert config.model.name == "claude-opus-4-8"
    assert config.model.temperature == 0.0
    assert config.model.thinking is False
    assert config.model.fallback_model == ""
    assert config.model.max_tokens == harness.MAX_TOKENS
    local = harness.product_config("openai:yerel", workspace=tmp_path,
                                   base_url="http://localhost:1234/v1")
    assert local.model.base_url == "http://localhost:1234/v1"


def test_the_decision_line_is_asked_for_first(harness) -> None:
    """Deliberation first ran past the end of the reply on a tenth of the
    real answers; the decision must come before the reasoning."""
    rule = harness.ANSWER_RULE.format(a="A", b="B")
    assert rule.index("KARAR") < rule.index("gerekçe")


def test_token_soup_is_garbled_not_ambiguous(harness) -> None:
    soup = "DynamCes Coch活动阐述了심intemplate Elev تح 할-edice 锻炼音乐会 ki酒店的angunan"
    assert harness.is_garbled(soup)
    assert not harness.is_garbled("Bu durumda önce testi yazarım.\nKARAR: önce testi yazarım")
    assert not harness.is_garbled("kısa")


def test_closed_loop_calibrates_and_remeasures(harness, decisions, tmp_path) -> None:
    """Cycle 1 with the computed lever, gain from what it moved, cycle 2 with
    the calibrated lever; the report carries both and the deviation from the
    target must not grow on the fake."""
    result = harness.run(decisions, _fakes(harness, tmp_path), target=harness.DRY_TARGET,
                         identity_doc=harness.SAMPLE_IDENTITY, repeats=2,
                         root=tmp_path / "durum", closed_loop=True)
    assert result["kapali_cevrim"] is True
    assert result["sayim"]["cagri"] == harness.plan_calls(2, 2, leverage_on=True, closed_loop=True)
    for name, model in result["modeller"].items():
        cal = model["kalibrasyon"]
        assert set(cal["kazanc"]) == {"yenilik", "sonuc", "sosyal", "sebat", "temkin"}
        assert cal["sapma_2"] is not None and cal["sapma_1"] is not None
        assert cal["sapma_2"] <= cal["sapma_1"] + 0.05, name
        assert "tam2" in model["kollar"] and "kimliksiz" not in model["kollar"]
    assert result["metrikler"]["tutarlilik_model"] is not None



def test_the_target_can_be_the_first_models_baseline(harness, decisions, tmp_path) -> None:
    """The product's real scenario: B must become A. A gets no lever (it is
    already the target); B is levered toward A's measured baseline."""
    result = harness.run(decisions, _fakes(harness, tmp_path), target=harness.DRY_TARGET,
                         identity_doc=harness.SAMPLE_IDENTITY, repeats=2,
                         root=tmp_path / "durum", closed_loop=True, target_from_first=True)
    assert result["hedef_ilk_model"] is True
    a, b = list(result["modeller"].values())
    assert a["hedef"] == a["taban"]
    assert b["hedef"] == a["taban"]
    assert set(a["kaldirac"].values()) == {1.0}
    assert result["metrikler"]["tutarlilik_model"] is not None


def test_precedent_from_model_a_reaches_only_model_b_levered_arms(harness, decisions, tmp_path) -> None:
    """A answers the held-out set once; B's tam/tam2 arms carry the block,
    the control arm does not, and A never sees its own precedent."""
    held = harness.load_exemplar_decisions()
    assert len(held) == 10 and len({d.axis for d in held}) == 5
    assert not {d.id for d in held} & {d.id for d in decisions}
    result = harness.run(decisions, _fakes(harness, tmp_path), target=harness.DRY_TARGET,
                         identity_doc=harness.SAMPLE_IDENTITY, repeats=2,
                         root=tmp_path / "durum", closed_loop=True, target_from_first=True,
                         exemplars=True, held_out=held)
    assert result["ornekli"] is True
    assert result["sayim"]["cagri"] == harness.plan_calls(2, 2, leverage_on=True,
                                                           closed_loop=True, exemplars=10)
    a, b = list(result["modeller"].values())
    assert all(not m["ornek_blogu"] for m in a["kollar"].values())
    assert b["kollar"]["tam"]["ornek_blogu"] and b["kollar"]["tam2"]["ornek_blogu"]
    assert not b["kollar"]["kaldiracsiz"]["ornek_blogu"]
