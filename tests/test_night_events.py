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
        "uyku.basladi":  ("basinc", "tahmini_uyanma", "dongu_sayisi"),
        "uyku.dongu":    ("no", "faz"),
        "tekrar.ileri":  ("oturum", "dizi", "kenarlar"),
        "tekrar.geri":   ("oturum", "sonuc", "paylar"),
        "dikis":         ("a", "b", "uzerinden", "oturumlar"),
        "dokunus":       ("id",),
        "damitma":       ("kaynaklar", "yeni"),
        "uyku.uyandi":   ("sebep", "dongu", "tamamlanan", "devreden", "borc"),
        "uyku.bitti":    ("sebep", "rapor"),
        "uyanik.ters":   ("oturum", "sonuc"),
        "mikro.basladi": ("basinc",),
        "mikro.bitti":   ("tamamlanan",),
        "yerel.basladi": ("bolge",),
        "yerel.bitti":   ("kuculen", "atlanan"),
    }


def test_every_event_carries_a_timestamp_and_a_type() -> None:
    event = ne.build("dokunus", clock, id="n_1")
    assert set(ne.ORTAK) <= set(event)
    assert event["ts"].startswith("2025-06-02")


# -- the contract, both directions -------------------------------------


def test_an_unknown_event_is_refused() -> None:
    with pytest.raises(ne.SchemaError):
        ne.build("uyku.ruya", clock)


def test_a_missing_field_is_refused() -> None:
    with pytest.raises(ne.SchemaError):
        ne.build("dikis", clock, a="n_1", b="n_2")       # no `uzerinden`


def test_an_extra_field_is_refused() -> None:
    """The view may only rely on what the schema promises, so nothing else
    is allowed to sneak in and become load-bearing."""
    with pytest.raises(ne.SchemaError):
        ne.build("dokunus", clock, id="n_1", renk="mavi")


def test_reading_validates_the_same_contract() -> None:
    with pytest.raises(ne.SchemaError):
        ne.validate({"tur": "dokunus"})                  # no ts
    with pytest.raises(ne.SchemaError):
        ne.validate({"ts": "x", "tur": "dokunus"})       # no id
    ne.validate({"ts": "x", "tur": "dokunus", "id": "n_1"})


# -- writing and replaying ---------------------------------------------


def test_a_night_replays_in_the_order_it_happened(tmp_path: Path) -> None:
    """Live view and replay are the same code path; there is no second one."""
    log = ne.NightLog(tmp_path / "gece" / "2025-06-02.jsonl", clock)
    log.emit("uyku.basladi", basinc=1.2, tahmini_uyanma="08:30", dongu_sayisi=4)
    log.emit("tekrar.ileri", oturum="s1", dizi=["n_1", "n_2"],
             kenarlar=[["n_1", "n_2", 0.6]])
    log.emit("dikis", a="n_1", b="n_3", uzerinden="n_2", oturumlar=["s1", "s2"])
    log.emit("uyku.bitti", sebep="basinc", rapor={"tekrar": 1})

    okunan = list(ne.replay(tmp_path / "gece" / "2025-06-02.jsonl"))
    assert [e["tur"] for e in okunan] == [
        "uyku.basladi", "tekrar.ileri", "dikis", "uyku.bitti"]
    assert okunan[1]["dizi"] == ["n_1", "n_2"]


def test_a_truncated_log_replays_up_to_the_cut(tmp_path: Path) -> None:
    """A power cut mid-write should cost the last line, not the night."""
    path = tmp_path / "gece" / "2025-06-02.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"ts": "x", "tur": "dokunus", "id": "n_1"}) + "\n"
        + '{"ts": "x", "tur": "doku',      # cut off
        encoding="utf-8")
    assert [e["id"] for e in ne.replay(path)] == ["n_1"]


def test_a_live_listener_sees_what_the_file_gets(tmp_path: Path) -> None:
    gorulen: list[str] = []
    log = ne.NightLog(tmp_path / "gece" / "x.jsonl", clock,
                      listeners=[lambda e: gorulen.append(e["tur"])])
    log.emit("dokunus", id="n_1")
    assert gorulen == ["dokunus"]
    assert [e["tur"] for e in ne.replay(log.path)] == ["dokunus"]


def test_a_broken_view_does_not_stop_the_night(tmp_path: Path) -> None:
    def patla(_event):
        raise RuntimeError("arayüz çöktü")

    log = ne.NightLog(tmp_path / "gece" / "x.jsonl", clock, listeners=[patla])
    log.emit("dokunus", id="n_1")
    assert [e["id"] for e in ne.replay(log.path)] == ["n_1"]


# -- what the morning panel reads --------------------------------------


def test_the_summary_counts_what_a_person_would_ask(tmp_path: Path) -> None:
    log = ne.NightLog(tmp_path / "gece" / "x.jsonl", clock)
    log.emit("uyku.basladi", basinc=1.0, tahmini_uyanma="08:30", dongu_sayisi=4)
    log.emit("uyku.dongu", no=1, faz="derin")
    log.emit("tekrar.ileri", oturum="s1", dizi=["n_1"], kenarlar=[["n_1", "n_2", 0.6]])
    log.emit("tekrar.ileri", oturum="s2", dizi=["n_3"], kenarlar=[])
    log.emit("dikis", a="n_1", b="n_3", uzerinden="n_2", oturumlar=["s1", "s2"])
    log.emit("damitma", kaynaklar=["n_1", "n_3"], yeni="n_9")
    log.emit("uyku.uyandi", sebep="kullanici", dongu=2, tamamlanan=2,
             devreden=5, borc={"faz": "rem"})

    ozet = ne.summary(ne.replay(log.path))
    assert ozet["tekrar"] == 2 and ozet["kenar"] == 1
    assert ozet["dikis"] == 1 and ozet["damitik"] == 1
    assert ozet["uyandi"] == "kullanici" and ozet["devreden"] == 5


def test_nights_are_listed_newest_first(tmp_path: Path) -> None:
    for tarih in ("2025-06-01", "2025-06-03", "2025-06-02"):
        ne.NightLog(tmp_path / "gece" / f"{tarih}.jsonl", clock).emit(
            "dokunus", id="n_1")
    assert ne.nights(tmp_path) == ["2025-06-03", "2025-06-02", "2025-06-01"]


def test_the_date_from_a_request_cannot_escape_the_folder(tmp_path: Path) -> None:
    """The date reaches this from an HTTP path; it is untrusted input."""
    yol = ne.night_path(tmp_path, "../../etc/passwd")
    assert yol.parent == tmp_path / "gece"
    assert ".." not in yol.name
