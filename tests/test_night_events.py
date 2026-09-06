"""The night event schema — frozen on purpose.

The brain view animates what the memory does. That only works if both sides
agree on a vocabulary, and the agreement has to break loudly: a renamed
field should turn a test red, not produce an animation that quietly stops
moving. So the schema here is a snapshot, and editing it is a decision.

The other rule these defend is that the view reads the event stream and
never `recall.db`. While the night is writing, a reader racing the writer
would show a half-consolidated graph and present it as the truth.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dornick.recall import night_events as ne

NOW = datetime(2025, 6, 2, 23, 0, tzinfo=timezone.utc)


def clock() -> datetime:
    return NOW


# -- the snapshot ------------------------------------------------------


def test_the_vocabulary_is_frozen() -> None:
    """If this test fails, the view's contract changed. That is the point."""
    assert ne.SCHEMA == {
        "sleep.started":  ("pressure", "wake_estimate", "cycle_count"),
        "sleep.cycle":    ("no", "phase"),
        "replay.forward": ("session", "sequence", "edges"),
        "replay.reverse": ("session", "outcome", "shares"),
        "stitch":         ("a", "b", "via", "sessions"),
        "touch":          ("id",),
        "distil":         ("sources", "new"),
        "sleep.woke":     ("reason", "cycle", "completed", "carried", "debt"),
        "sleep.ended":    ("reason", "report"),
        "awake.reverse":  ("session", "outcome"),
        "micro.started":  ("pressure",),
        "micro.ended":    ("completed",),
        "local.started":  ("region",),
        "local.ended":    ("shrunk", "skipped"),
    }


def test_every_event_carries_a_timestamp_and_a_type() -> None:
    event = ne.build("touch", clock, id="n_1")
    assert set(ne.SHARED) <= set(event)
    assert event["ts"].startswith("2025-06-02")


# -- the contract, both directions -------------------------------------


def test_an_unknown_event_is_refused() -> None:
    with pytest.raises(ne.SchemaError):
        ne.build("sleep.dream", clock)


def test_a_missing_field_is_refused() -> None:
    with pytest.raises(ne.SchemaError):
        ne.build("stitch", clock, a="n_1", b="n_2")      # no `via`


def test_an_extra_field_is_refused() -> None:
    """The view may only rely on what the schema promises, so nothing else
    is allowed to sneak in and become load-bearing."""
    with pytest.raises(ne.SchemaError):
        ne.build("touch", clock, id="n_1", colour="blue")


def test_reading_validates_the_same_contract() -> None:
    with pytest.raises(ne.SchemaError):
        ne.validate({"kind": "touch"})                  # no ts
    with pytest.raises(ne.SchemaError):
        ne.validate({"ts": "x", "kind": "touch"})       # no id
    ne.validate({"ts": "x", "kind": "touch", "id": "n_1"})


# -- writing and replaying ---------------------------------------------


def test_a_night_replays_in_the_order_it_happened(tmp_path: Path) -> None:
    """Live view and replay are the same code path; there is no second one."""
    log = ne.NightLog(tmp_path / "nights" / "2025-06-02.jsonl", clock)
    log.emit("sleep.started", pressure=1.2, wake_estimate="08:30", cycle_count=4)
    log.emit("replay.forward", session="s1", sequence=["n_1", "n_2"],
             edges=[["n_1", "n_2", 0.6]])
    log.emit("stitch", a="n_1", b="n_3", via="n_2", sessions=["s1", "s2"])
    log.emit("sleep.ended", reason="pressure", report={"replays": 1})

    read_back = list(ne.replay(tmp_path / "nights" / "2025-06-02.jsonl"))
    assert [e["kind"] for e in read_back] == [
        "sleep.started", "replay.forward", "stitch", "sleep.ended"]
    assert read_back[1]["sequence"] == ["n_1", "n_2"]


def test_a_truncated_log_replays_up_to_the_cut(tmp_path: Path) -> None:
    """A power cut mid-write should cost the last line, not the night."""
    path = tmp_path / "nights" / "2025-06-02.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"ts": "x", "kind": "touch", "id": "n_1"}) + "\n"
        + '{"ts": "x", "kind": "tou',      # cut off
        encoding="utf-8")
    assert [e["id"] for e in ne.replay(path)] == ["n_1"]


def test_a_live_listener_sees_what_the_file_gets(tmp_path: Path) -> None:
    seen: list[str] = []
    log = ne.NightLog(tmp_path / "nights" / "x.jsonl", clock,
                      listeners=[lambda e: seen.append(e["kind"])])
    log.emit("touch", id="n_1")
    assert seen == ["touch"]
    assert [e["kind"] for e in ne.replay(log.path)] == ["touch"]


def test_a_broken_view_does_not_stop_the_night(tmp_path: Path) -> None:
    def blow_up(_event):
        raise RuntimeError("the view crashed")

    log = ne.NightLog(tmp_path / "nights" / "x.jsonl", clock, listeners=[blow_up])
    log.emit("touch", id="n_1")
    assert [e["id"] for e in ne.replay(log.path)] == ["n_1"]


# -- what the morning panel reads --------------------------------------


def test_the_summary_counts_what_a_person_would_ask(tmp_path: Path) -> None:
    log = ne.NightLog(tmp_path / "nights" / "x.jsonl", clock)
    log.emit("sleep.started", pressure=1.0, wake_estimate="08:30", cycle_count=4)
    log.emit("sleep.cycle", no=1, phase="deep")
    log.emit("replay.forward", session="s1", sequence=["n_1"], edges=[["n_1", "n_2", 0.6]])
    log.emit("replay.forward", session="s2", sequence=["n_3"], edges=[])
    log.emit("stitch", a="n_1", b="n_3", via="n_2", sessions=["s1", "s2"])
    log.emit("distil", sources=["n_1", "n_3"], new="n_9")
    log.emit("sleep.woke", reason="user", cycle=2, completed=2,
             carried=5, debt={"phase": "rem"})

    summary = ne.summary(ne.replay(log.path))
    assert summary["replays"] == 2 and summary["edges"] == 1
    assert summary["stitches"] == 1 and summary["distilled"] == 1
    assert summary["woke"] == "user" and summary["carried"] == 5


def test_nights_are_listed_newest_first(tmp_path: Path) -> None:
    for date in ("2025-06-01", "2025-06-03", "2025-06-02"):
        ne.NightLog(tmp_path / "nights" / f"{date}.jsonl", clock).emit(
            "touch", id="n_1")
    assert ne.nights(tmp_path) == ["2025-06-03", "2025-06-02", "2025-06-01"]


def test_the_date_from_a_request_cannot_escape_the_folder(tmp_path: Path) -> None:
    """The date reaches this from an HTTP path; it is untrusted input."""
    path = ne.night_path(tmp_path, "../../etc/passwd")
    assert path.parent == tmp_path / "nights"
    assert ".." not in path.name
