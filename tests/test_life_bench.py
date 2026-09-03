"""Can the life benchmark itself be measured?

Trusting a benchmark has two preconditions: it produces the same number
from the same input, and the dataset it measures is consistent. Both are
exercised here — if the numbers fluctuate the phase acceptance criteria are
meaningless, and if the dataset is inconsistent what gets measured is the
dataset's mistake, not the product.

It is also verified that the dataset **really builds what the clusters
promise**: is the long silence really silent, was the temporal-neighbourhood
pair used back to back in the same session, have the two ends of the stitch
never been experienced together. If these do not hold, the metrics do not
measure what they claim to measure.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH_PATH = ROOT / "eval" / "context_memory" / "life_bench.py"

# Minimum event counts from roadmap 0.2. Cluster -> (event kind, at least).
MINIMUMS = [
    ("A", "kaydet", 15), ("A", "sor", 30),
    ("B", "duzelt", 24),                      # 8 chains × 3 corrections
    ("C", "kaydet", 60),
    ("D", "kaydet", 6),
    ("E", "kaydet", 20),                      # 10 pairs
    ("F", "sor", 40),
    ("G", "kaydet", 5),
    ("H", "kaydet", 24), ("H", "sor", 12),    # 12 pairs
    ("I", "kaydet", 8), ("I", "sor", 8),
    ("J", "kaydet", 18), ("J", "sor", 6),     # 6 triples
    ("K", "kaydet", 20), ("K", "sor", 20),    # 10 isolated + 10 with schema
    ("N", "kaydet", 20), ("N", "sor", 10),    # 10 pairs + control
    ("O", "kaydet", 16), ("O", "sor", 8),     # 8 pairs + control
    ("L", "uyan", 9),                         # 3 cut points × 3
    ("Q", "arac", 10), ("Q", "sor", 10),
]

EVENT_KINDS = {"kaydet", "sor", "duzelt", "kullan", "arac", "sonuc", "sessiz", "uyan"}


def _bench():
    """Loads the bench as a module (eval/ is not a package)."""
    spec = importlib.util.spec_from_file_location("life_bench", BENCH_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["life_bench"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bench():
    return _bench()


@pytest.fixture(scope="module")
def holdout(bench):
    return bench.load_data("holdout")


@pytest.fixture(scope="module")
def main_set(bench):
    return bench.load_data("ana")


# -- determinism -------------------------------------------------------


def test_same_scenario_gives_same_result(bench, holdout) -> None:
    """No randomness: two runs must give exactly the same metrics."""
    first = bench.run(holdout)
    second = bench.run(holdout)
    # Duration measurements come from the wall clock — the only fluctuating
    # numbers, removed from the comparison. Every remaining metric must be
    # identical.
    for result in (first, second):
        for timing in ("gecikme_p95", "gece_suresi", "tur_bloklama"):
            result["metrikler"].pop(timing)
    assert first["metrikler"] == second["metrikler"]
    assert first["kume"] == second["kume"]
    assert first["sayim"] == second["sayim"]


def test_every_metric_is_number_or_none(bench, holdout) -> None:
    """`None` = "that version lacked the mechanism"; any other type is
    meaningless in the report."""
    result = bench.run(holdout)
    assert set(result["metrikler"]) == set(bench.TARGETS)
    for name, value in result["metrikler"].items():
        assert value is None or isinstance(value, (int, float)), name


def test_logs_are_written_in_the_products_own_format(bench, holdout, tmp_path) -> None:
    """The night pass (Phase 3) will read these logs: no invented format."""
    bench.run(holdout, root=tmp_path)
    logs = list((tmp_path / "sessions").glob("*.jsonl"))
    assert logs, "no session log written"

    import json

    kinds = set()
    for path in logs:
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            assert set(event) >= {"seq", "ts", "kind", "content", "meta"}
            if event["kind"] == "meta":
                kinds.add(event["content"])
    # What the night replay needs: what was touched, how the session ended.
    assert {"session_start", "mind_write", "mind_open", "prime", "sonuc"} <= kinds


def test_log_stamps_come_from_the_virtual_calendar(bench, holdout, tmp_path) -> None:
    """Had the session log written from the wall clock, ninety days could
    not be measured."""
    import json

    bench.run(holdout, root=tmp_path)
    stamps = []
    for path in (tmp_path / "sessions").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stamps.append(json.loads(line)["ts"])
    assert stamps
    assert all(s.startswith("2025-") for s in stamps)


# -- dataset consistency -----------------------------------------------


@pytest.mark.parametrize("name", ["ana", "holdout"])
def test_dataset_is_consistent(bench, name: str) -> None:
    data = bench.load_data(name)
    day_count = data["gun_sayisi"]
    written: dict[str, int] = {}
    for event in data["olaylar"]:
        day = event["gun"]
        assert 1 <= day <= day_count, event
        assert event["tur"] in EVENT_KINDS, event
        assert event["oturum"], event
        assert event["sira"] >= 1, event

        if event["tur"] in ("kaydet", "duzelt"):
            assert event["slug"] not in written, f"same slug twice: {event['slug']}"
            assert event["icerik"].strip(), event
            written[event["slug"]] = day
        if event["tur"] == "duzelt":
            assert event["eskisi"] in written, f"corrected record missing: {event['eskisi']}"
        if event["tur"] == "kullan":
            for slug in event["hedef"]:
                assert written.get(slug, 10**9) <= day, f"used before written: {slug}"
        if event["tur"] == "sor":
            for slug in [*event.get("beklenen", []), *event.get("yasak", []),
                         *event.get("acik", [])]:
                assert slug in written, f"undefined slug: {slug}"
                assert written[slug] <= day, f"asked before written: {slug}"
            for field in ("deney", "kontrol", "ustte", "altta"):
                if target := (event.get("olcum") or {}).get(field):
                    assert target in written, f"undefined measurement target: {target}"


@pytest.mark.parametrize("name", ["ana", "holdout"])
def test_every_session_closes_with_an_outcome(bench, name: str) -> None:
    """The night replay walks a session as a whole; a session without an
    outcome is noise, not a source (roadmap 3.1)."""
    data = bench.load_data(name)
    valid = {"basarili", "basarisiz", "duzeltildi", "acik"}
    open_sessions: dict[str, str] = {}
    for event in data["olaylar"]:
        if event["tur"] in ("sessiz", "uyan"):
            continue
        if event["tur"] == "sonuc":
            assert event["sonuc"] in valid, event
            open_sessions.pop(event["oturum"], None)
        else:
            open_sessions.setdefault(event["oturum"], event["tur"])
    assert not open_sessions, f"unclosed session: {sorted(open_sessions)[:5]}"


def test_main_dataset_meets_minimum_event_counts(bench, main_set) -> None:
    """The roadmap sets a floor for every cluster; the dataset must hold it."""
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for event in main_set["olaylar"]:
        counts[(event["kume"], event["tur"])] += 1
    missing = [(k, t, at_least, counts[(k, t)])
               for k, t, at_least in MINIMUMS if counts[(k, t)] < at_least]
    assert not missing, f"clusters below the minimum event count: {missing}"


def test_silent_days_really_exist(bench, main_set) -> None:
    """The forgetting curve can only be measured with days on which nothing
    happens."""
    busy = {e["gun"] for e in main_set["olaylar"] if e["tur"] != "sessiz"}
    silent = [d for d in range(1, main_set["gun_sayisi"] + 1) if d not in busy]
    assert len(silent) >= 20
    longest = streak = 0
    for day in range(1, main_set["gun_sayisi"] + 1):
        streak = streak + 1 if day in silent else 0
        longest = max(longest, streak)
    assert longest >= 7, "no uninterrupted week of silence"


def test_work_rhythm_is_weekday_office_hours(bench, main_set) -> None:
    """The M-cluster rhythm pattern is learned from here: weekdays 09:00-18:00."""
    for event in main_set["olaylar"]:
        if event["tur"] in ("sessiz", "uyan"):
            continue
        assert 9 <= event["saat"] <= 18, event
        assert (event["gun"] - 1) % 7 < 5, f"event landed on a weekend: {event}"


# -- what the clusters promise -----------------------------------------


def test_long_silence_cluster_is_really_silent(bench, main_set) -> None:
    """G: from its writing to its question the record must never be touched."""
    written = {e["slug"]: e["gun"] for e in main_set["olaylar"]
               if e["tur"] == "kaydet" and e["kume"] == "G"}
    used = {s for e in main_set["olaylar"] if e["tur"] == "kullan" for s in e["hedef"]}
    for event in main_set["olaylar"]:
        if event["tur"] == "sor" and event["kume"] == "G":
            for slug in event.get("acik", []):
                assert slug not in used
                assert event["gun"] - written[slug] >= 30, slug


def test_temporal_neighbour_pair_is_back_to_back_in_one_session(bench, main_set) -> None:
    """H: this order is the edge's only source. In different sessions the
    mechanism would not measure what it claims to."""
    sequence: dict[str, list[str]] = defaultdict(list)
    for event in main_set["olaylar"]:
        if event["tur"] == "kullan" and event["kume"] == "H":
            sequence[event["oturum"]].extend(event["hedef"])
    pairs = {tuple(v) for v in sequence.values() if len(v) == 2}
    assert len(pairs) >= 12
    for x, y in pairs:
        assert x.endswith("_x") and y.endswith("_y")
        assert x[:-2] == y[:-2]


def test_temporal_neighbour_pair_is_dissimilar_in_content(bench, main_set) -> None:
    """The whole point of H: content search must never be able to make this
    link."""
    text = {e["slug"]: e["icerik"] for e in main_set["olaylar"]
            if e["tur"] == "kaydet" and e["kume"] == "H"}
    for slug, content in text.items():
        if not slug.endswith("_x"):
            continue
        partner = text[slug[:-2] + "_y"]
        shared = ({w[:5].casefold() for w in content.split() if len(w) > 4}
                  & {w[:5].casefold() for w in partner.split() if len(w) > 4})
        assert not shared, f"{slug}: the pair is similar in content ({shared})"


def test_stitch_ends_never_experienced_together(bench, main_set) -> None:
    """J: A and C must never appear in the same session, otherwise it is
    repetition, not a stitch."""
    sequence: dict[str, set[str]] = defaultdict(set)
    for event in main_set["olaylar"]:
        if event["tur"] == "kullan" and event["kume"] == "J":
            sequence[event["oturum"]].update(event["hedef"])
    ends = {s.rsplit("_", 1)[0] for v in sequence.values() for s in v}
    assert len(ends) >= 6
    for stem in ends:
        for members in sequence.values():
            assert not {f"{stem}_a", f"{stem}_c"} <= members, stem


def test_isolated_record_is_never_used(bench, main_set) -> None:
    """K: the isolated arm must really be isolated; alone in its own session."""
    isolated = {e["slug"]: e["oturum"] for e in main_set["olaylar"]
                if e["tur"] == "kaydet" and e["kume"] == "K"
                and e["slug"].startswith("k_y")}
    assert len(isolated) >= 10
    used = {s for e in main_set["olaylar"] if e["tur"] == "kullan" for s in e["hedef"]}
    session_size: dict[str, int] = defaultdict(int)
    for event in main_set["olaylar"]:
        if event["tur"] in ("kaydet", "kullan"):
            session_size[event["oturum"]] += 1
    for slug, session in isolated.items():
        assert slug not in used, slug
        assert session_size[session] == 1, f"{slug} is not alone"


def test_reverse_replay_ties_same_memory_to_two_outcomes(bench, main_set) -> None:
    """I: the good procedure must be used in a successful session, the bad
    one in a failed session."""
    outcomes = {e["oturum"]: e["sonuc"] for e in main_set["olaylar"] if e["tur"] == "sonuc"}
    seen: dict[str, set[str]] = defaultdict(set)
    for event in main_set["olaylar"]:
        if event["tur"] == "kullan" and event["kume"] == "I":
            for slug in event["hedef"]:
                seen[slug].add(outcomes.get(event["oturum"], ""))
    good = [s for s in seen if s.endswith("_iyi")]
    assert len(good) >= 8
    for slug, outcome_set in seen.items():
        expected = "basarili" if slug.endswith("_iyi") else "basarisiz"
        assert outcome_set == {expected}, (slug, outcome_set)


def test_instant_lesson_question_is_in_the_same_session(bench, main_set) -> None:
    """Q: the question must be asked INSIDE the session the error came from
    — without waiting for the night."""
    faulty: dict[str, int] = {}
    for event in main_set["olaylar"]:
        if event["tur"] == "arac" and event["kume"] == "Q" and event.get("hata"):
            faulty[event["oturum"]] = event["sira"]
    assert len(faulty) >= 10
    questions = [e for e in main_set["olaylar"] if e["tur"] == "sor" and e["kume"] == "Q"]
    assert len(questions) >= 10
    for event in questions:
        assert event["oturum"] in faulty, event
        assert event["sira"] > faulty[event["oturum"]], event


def test_cut_points_split_in_three(bench, main_set) -> None:
    """L: three nights each cut at 30% / 60% / 90%."""
    percents = [e["baglam"]["yuzde"] for e in main_set["olaylar"] if e["tur"] == "uyan"]
    assert len(percents) >= 9
    for target in (30, 60, 90):
        assert percents.count(target) >= 3


# -- ablation surface --------------------------------------------------


def test_unknown_mechanism_is_rejected() -> None:
    from dornick.recall import switches

    with pytest.raises(ValueError):
        switches.configure(no_such_mechanism=False)
    assert switches.ACTIVE.activation is True


def test_disabled_mechanism_is_re_enabled_after_run(bench, holdout) -> None:
    from dornick.recall import switches

    bench.run(holdout, disabled=("activation",))
    assert switches.ACTIVE.activation is True


def test_ablation_names_line_up_with_targets(bench) -> None:
    """Every mechanism must have a switch, every metric a target."""
    from dornick.recall import switches

    assert set(switches.NAMES) == {"activation", "supersede", "weave", "distillation",
                                  "encoding", "context"}
    assert all(len(v) == 3 for v in bench.TARGETS.values())
