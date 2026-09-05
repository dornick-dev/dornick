"""The character follows the model: what happens on a model change.

Six real measurements settled the recipe (docs/hafiza-fazlar.md, 7.6):
measure the new model bare, keep the target, keep the previous model's
decisions as precedent, learn the lever's dose in closed loop. Here the
model is a fake with an innate temperament; what is tested is the ORDER and
the files, not the model.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dornick.recall import character, exemplars, temperament
from dornick.recall.temperament import Temperament


def _fake_ask(innate: dict[str, float], *, levered_shift: float = 0.0):
    """Answers the probes from an innate high-share per axis; a levered
    (non-bare) prompt shifts every axis by `levered_shift`."""
    probes = {p.render(): p for p in character.load_probes()}
    calls = {"bare": 0, "full": 0}

    def ask(text: str, bare: bool) -> str:
        calls["bare" if bare else "full"] += 1
        probe = probes[text]
        share = innate.get(probe.axis, 0.5) + (0.0 if bare else levered_shift)
        # Deterministic per probe: the first probe of an axis goes high when
        # share >= 0.5, the second when share >= 0.75.
        rank = int(probe.id[-1]) if probe.id[-1].isdigit() else 1
        high = share >= (0.5 if rank == 1 else 0.75)
        return f"KARAR: {probe.high if high else probe.low}\nGerekçe kısa."

    ask.calls = calls  # type: ignore[attr-defined]
    return ask


def test_probes_ship_with_the_product() -> None:
    probes = character.load_probes()
    assert len(probes) == 10
    assert {p.axis for p in probes} == set(temperament.AXES)
    assert all(len(p.options) == 2 and p.high in p.options for p in probes)


def test_parse_choice_reads_the_decision_line_first() -> None:
    assert character.parse_choice("KARAR: sorarım\nÇünkü...", ("sorarım", "yaparım")) == "sorarım"
    assert character.parse_choice("**KARAR:** yaparım", ("sorarım", "yaparım")) == "yaparım"
    assert character.parse_choice("Sorarım herhalde.", ("sorarım", "yaparım")) == ""
    assert character.parse_choice("sorarım", ("sorarım", "yaparım")) == "sorarım"


def test_first_install_measures_bare_and_records_the_models_own_precedent(tmp_path: Path) -> None:
    ask = _fake_ask({"caution": 0.9, "novelty": 0.2})
    report = character.handle_model_change(tmp_path, "model-a", ask)
    assert report is not None and report.precedent_recorded
    base, target, model_id = temperament.load(tmp_path)
    assert model_id == "model-a"
    assert base.caution > 0.5 > base.novelty                 # measured, not assumed
    assert target.as_dict() == temperament.default_target().as_dict()   # untouched
    assert exemplars.load_model_id(tmp_path) == "model-a"
    assert len(exemplars.load(tmp_path)) == 10
    assert ask.calls == {"bare": 10, "full": 10}             # baseline + levered re-measure
    assert temperament.load_gain(tmp_path)                    # calibrated once


def test_a_second_call_for_the_same_model_does_nothing(tmp_path: Path) -> None:
    ask = _fake_ask({"caution": 0.9})
    assert character.handle_model_change(tmp_path, "model-a", ask) is not None
    assert character.handle_model_change(tmp_path, "model-a", ask) is None
    assert ask.calls == {"bare": 10, "full": 10}


def test_a_model_change_keeps_the_target_and_the_old_precedent(tmp_path: Path) -> None:
    character.handle_model_change(tmp_path, "model-a", _fake_ask({"caution": 0.9, "novelty": 0.2}))
    taught = Temperament(caution=0.6, novelty=0.4, social=0.2)
    base_a, _t, _m = temperament.load(tmp_path)
    temperament.save(tmp_path, base_a, taught, "model-a")
    temperament.save_gain(tmp_path, {"caution": 2.0})
    before = exemplars.load(tmp_path)

    report = character.handle_model_change(tmp_path, "model-b", _fake_ask({"caution": 0.2, "novelty": 0.9}))
    assert report is not None and not report.precedent_recorded
    base_b, target, model_id = temperament.load(tmp_path)
    assert model_id == "model-b"
    assert target.as_dict() == taught.as_dict()               # what the user taught survives
    assert base_b.caution < 0.5 < base_a.caution              # re-measured
    assert [e.decision for e in exemplars.load(tmp_path)] == [e.decision for e in before]
    assert exemplars.load_model_id(tmp_path) == "model-a"    # the old character stays the precedent
    gain = temperament.load_gain(tmp_path)
    assert gain["caution"] != 2.0                             # reset, then calibrated for B


def test_calibration_uses_what_the_levered_prompt_moved(tmp_path: Path) -> None:
    """A model that ignores the lever gets a bigger dose; one that moves
    exactly keeps it."""
    character.handle_model_change(tmp_path, "model-a", _fake_ask({"caution": 0.5}))
    base, _t, _m = temperament.load(tmp_path)
    temperament.save(tmp_path, base, Temperament(caution=0.9), "model-a")
    report = character.handle_model_change(tmp_path, "model-deaf", _fake_ask({"caution": 0.5}, levered_shift=0.0))
    assert report is not None
    assert report.gain["temkin"] > 1.0                        # no movement -> more


def test_exemplar_file_keeps_the_model_id_and_reads_the_old_list_form(tmp_path: Path) -> None:
    exemplars.save(tmp_path, [exemplars.Exemplar("temkin", "durum", "sorarım")], "model-a")
    assert exemplars.load_model_id(tmp_path) == "model-a"
    (tmp_path / exemplars.FILE_NAME).write_text(
        json.dumps([{"eksen": "temkin", "durum": "eski", "karar": "sorarım"}]), encoding="utf-8")
    assert exemplars.load_model_id(tmp_path) == ""
    assert exemplars.load(tmp_path)[0].decision == "sorarım"


# -- the daemon runs it ---------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.moment


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


@pytest.fixture()
def daemon(tmp_path: Path):
    from dornick.recall import daemon as D
    from dornick.recall import open_store

    store = open_store(tmp_path / "memory")
    hub = _Hub()
    name = {"value": "model-a"}
    d = D.SleepDaemon(store, tmp_path / "sessions", tmp_path / "state", clock=_Clock(),
                      hub=hub, probe=_fake_ask({"caution": 0.8}),
                      model_name=lambda: name["value"], enabled=False)
    yield d, hub, name
    store.close()


def test_the_daemon_measures_a_new_model_on_its_tick(daemon) -> None:
    d, hub, name = daemon
    d.tick()
    assert temperament.load(d.state_dir)[2] == "model-a"
    kinds = [e["olay"] for e in hub.events if e.get("type") == "karakter"]
    assert kinds == ["karakter.olcum"]
    d.tick()
    assert len([e for e in hub.events if e.get("type") == "karakter"]) == 1   # once


def test_a_settings_change_is_picked_up_on_the_next_tick(daemon) -> None:
    d, hub, name = daemon
    d.tick()
    name["value"] = "model-b"
    d.model_changed()
    d.tick()
    assert temperament.load(d.state_dir)[2] == "model-b"
    assert exemplars.load_model_id(d.state_dir) == "model-a"


def test_a_failing_model_is_retried_later_not_every_minute(tmp_path: Path) -> None:
    from dornick.recall import daemon as D
    from dornick.recall import open_store

    calls = {"n": 0}

    def broken(text: str, bare: bool) -> str:
        calls["n"] += 1
        raise RuntimeError("model yok")

    store = open_store(tmp_path / "memory")
    try:
        clock = _Clock()
        hub = _Hub()
        d = D.SleepDaemon(store, tmp_path / "sessions", tmp_path / "state", clock=clock,
                          hub=hub, probe=broken, model_name=lambda: "model-x", enabled=False)
        d.tick()
        first = calls["n"]
        assert first > 0
        d.tick()
        assert calls["n"] == first                              # backed off
        assert temperament.load(d.state_dir)[2] == ""           # nothing written
    finally:
        store.close()
