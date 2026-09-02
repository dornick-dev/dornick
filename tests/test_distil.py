"""Night step 6 — distillation, its privacy gate and its exam gate.

This is the only step of the night that produces a guess rather than a
record, and every test here follows from that. It needs a model, so a
model-less machine must lose it and nothing else. It would send memory text
somewhere, so consent decides whether it runs at all. And because it is an
inference, it is the only step the exam gate is allowed to undo.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.recall import aktivasyon as A
from dornick.recall import anahtar, distil, open_store, orgu

NOW = datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)


@pytest.fixture()
def clock() -> Clock:
    return Clock(NOW)


@pytest.fixture()
def store(tmp_path: Path, clock: Clock):
    s = open_store(tmp_path / "memory", saat=clock)
    yield s
    s.close()


def fake_model(answer: str):
    """A model that always says the same thing, and records what it was asked."""
    calls: list[str] = []

    def _call(prompt: str) -> str:
        calls.append(prompt)
        return answer

    _call.calls = calls          # type: ignore[attr-defined]
    return _call


def _episodes(store, n: int = 5) -> list[str]:
    """A cluster of related conversation dumps, linked as the night links them."""
    bodies = [
        "Kullanıcı raporların PDF çıktığını, müşterinin Excel istediğini söyledi.",
        "Rapor dönüştürme denendi, tablo bozuldu, dönüştürücü elendi.",
        "Rapor için doğrudan xlsx üretmeye karar verildi.",
        "Rapor şablonu üç sayfaya sabitlendi ve örnek dosya paylaşıldı.",
        "Rapor teslimi vardiya sonuna alındı, zamanlanmış görev yazıldı.",
    ][:n]
    ids = [store.remember(b, kind="episode", tags=["rapor"]).id for b in bodies]
    for i in range(len(ids) - 1):
        store.baglan(ids[i], ids[i + 1], weight=0.8, reason="aynı konu")
    return ids


# -- the privacy gate --------------------------------------------------


def test_no_model_means_the_step_is_skipped_and_says_so(store, clock) -> None:
    ids = _episodes(store)
    report = distil.distil(store, ids, model=None, saat=clock)
    assert report.status == "atlandı: yerel model yok"
    assert report.written == 0


def test_hosted_model_without_consent_never_runs(store, clock) -> None:
    """Memory text reaches a hosted endpoint only if the user turned it on."""
    model = fake_model("Raporlar xlsx olarak üretiliyor. [x]")
    ids = _episodes(store)
    report = distil.distil(store, ids, model=model, saat=clock,
                           local_model=False, cloud_ok=False)
    assert "bulut onayı kapalı" in report.status
    assert model.calls == []                  # not a single prompt left the box
    assert report.written == 0


def test_hosted_model_with_consent_runs(store, clock) -> None:
    ids = _episodes(store)
    model = fake_model(f"Raporlar artık xlsx üretiliyor. [{ids[0]}]")
    report = distil.distil(store, ids, model=model, saat=clock,
                           local_model=False, cloud_ok=True)
    assert model.calls
    assert report.written >= 1


def test_the_switch_turns_it_off(store, clock) -> None:
    ids = _episodes(store)
    model = fake_model("Bir şey. [x]")
    with anahtar.kapali("damitma"):
        report = distil.distil(store, ids, model=model, saat=clock)
    assert "damıtma kapalı" in report.status
    assert model.calls == []


def test_the_night_runs_its_first_five_steps_without_a_model(
        store, tmp_path, clock) -> None:
    """A model-less machine loses summaries, not consolidation."""
    from dornick.events import EventLog

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    a = store.remember("Vardiya defteri kasada duruyor.", kind="fact")
    b = store.remember("Modem PIN kodu kırmızı defterde.", kind="fact")
    log = EventLog(sessions / "s1.jsonl",
                   saat=lambda: clock().isoformat(timespec="milliseconds"))
    for node in (a, b):
        log.note("mind_open", memory_id=node.id)
    log.note("sonuc", sonuc="basarili")

    report = orgu.gece_gecisi(store, sessions, saat=clock,
                              filigran=tmp_path / "w.json", model=None)
    assert "yerel model yok" in report.damitma
    assert report.tekrar_edilen == 1
    assert report.yeni_kenar >= 1


# -- what distillation writes ------------------------------------------


def test_five_episodes_become_at_most_three_sourced_facts(store, clock) -> None:
    ids = _episodes(store, 5)
    model = fake_model(
        f"Raporlar xlsx olarak üretiliyor. [{ids[0]}]\n"
        f"Rapor şablonu üç sayfalı. [{ids[3]}]\n"
        f"Rapor teslimi vardiya sonunda. [{ids[4]}]\n"
        f"Fazladan bir satır daha. [{ids[1]}]\n")
    report = distil.distil(store, ids, model=model, saat=clock)

    assert report.written <= distil.MAX_KEEPERS
    facts = [n for n in store.by_kind("fact", limit=20) if "damıtık" in n.tags]
    assert len(facts) == report.written
    for fact in facts:
        sources = {n.id for n, _w, _r in store.komsular_gerekceli(fact.id)}
        assert sources & set(ids), "damıtık kayıt kaynaksız"


def test_distilled_fact_can_enter_the_prime_but_the_episode_cannot(
        store, tmp_path, clock) -> None:
    """The whole point of the step: the substance becomes injectable."""
    from dornick.loop import select_prime
    from dornick.mind import open_mind

    ids = _episodes(store, 5)
    model = fake_model(f"Raporlar xlsx olarak üretiliyor, PDF kullanılmıyor. [{ids[0]}]")
    distil.distil(store, ids, model=model, saat=clock)

    mind = open_mind(store.path.parent, tmp_path / "sessions", "t", saat=clock)
    try:
        hits = select_prime(mind, "Raporlar hangi formatta üretiliyor?", limit=5)
        kinds = {h.item.kind for h in hits}
        assert "fact" in kinds
        assert "episode" not in kinds
    finally:
        mind.store.close()


def test_source_episodes_are_pushed_back_not_deleted(store, clock) -> None:
    ids = _episodes(store, 5)
    before = store.peek(ids[0]).aktivasyon
    model = fake_model(f"Raporlar xlsx üretiliyor. [{ids[0]}]")
    distil.distil(store, ids, model=model, saat=clock)

    after = store.peek(ids[0])
    assert after is not None and after.deleted is False    # still there
    assert after.aktivasyon < before                        # but backgrounded


def test_contradictions_are_reported_never_resolved(store, tmp_path, clock) -> None:
    """A model's opinion must not overwrite something the user said."""
    ids = _episodes(store, 5)
    model = fake_model(f"ÇELİŞKİ: {ids[0]} vs {ids[2]}")
    report = distil.distil(store, ids, model=model, saat=clock,
                           state_dir=tmp_path)

    assert report.contradictions == 1
    lines = (tmp_path / "celiskiler.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["a"] == ids[0]
    # Nothing was superseded on the model's say-so:
    assert store.peek(ids[0]).superseded_by == ""


def test_an_unrelated_pair_is_weakened_not_cut(store, clock) -> None:
    ids = _episodes(store, 5)
    model = fake_model(f"İLİŞKİ: {ids[0]} {ids[1]} - ilişkisiz")
    distil.distil(store, ids, model=model, saat=clock)

    weights = {n.id: w for n, w, _r in store.komsular_gerekceli(ids[0])}
    assert weights[ids[1]] == pytest.approx(distil.UNRELATED_WEIGHT)


def test_a_relation_reason_lands_on_the_edge(store, clock) -> None:
    """SimHash cannot know synonyms; this is the embedding-free substitute."""
    ids = _episodes(store, 5)
    model = fake_model(f"İLİŞKİ: {ids[0]} {ids[1]} - ikisi de aynı raporun aşaması")
    distil.distil(store, ids, model=model, saat=clock)

    reasons = {n.id: r for n, _w, r in store.komsular_gerekceli(ids[0])}
    assert "aynı raporun aşaması" in reasons[ids[1]]


def test_a_model_that_crashes_does_not_take_the_night_with_it(store, clock) -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("model çöktü")

    ids = _episodes(store, 5)
    report = distil.distil(store, ids, model=boom, saat=clock)
    assert "model hatası" in report.status
    assert report.written == 0


# -- clustering --------------------------------------------------------


def test_clusters_stay_within_bounds(store, clock) -> None:
    ids = _episodes(store, 5)
    groups = distil.clusters(store, ids)
    assert groups
    for group in groups:
        assert distil.MIN_CLUSTER <= len(group) <= distil.MAX_CLUSTER


def test_a_lone_node_is_not_a_cluster(store, clock) -> None:
    lone = store.remember("Tek başına duran bir not.", kind="episode")
    assert distil.clusters(store, [lone.id]) == []


# -- the exam gate (3.7) -----------------------------------------------


def test_distilled_nodes_are_rolled_back_when_retrieval_gets_worse(
        store, clock) -> None:
    ids = _episodes(store, 5)
    model = fake_model(f"Raporlar xlsx üretiliyor. [{ids[0]}]")
    report = distil.distil(store, ids, model=model, saat=clock)
    assert report.written >= 1

    undone = distil.exam(store, report,
                         {"prime_precision": 0.60, "tuzak_sessizlik": 0.90},
                         {"prime_precision": 0.42, "tuzak_sessizlik": 0.90})

    assert undone == report.written
    assert "sınavı geçemedi" in report.status
    for node_id in report.node_ids:
        assert store.peek(node_id) is None          # tombstoned
    for node_id in ids:
        assert store.peek(node_id) is not None      # sources untouched


def test_a_night_that_helps_is_kept(store, clock) -> None:
    ids = _episodes(store, 5)
    model = fake_model(f"Raporlar xlsx üretiliyor. [{ids[0]}]")
    report = distil.distil(store, ids, model=model, saat=clock)

    undone = distil.exam(store, report,
                         {"prime_precision": 0.42, "tuzak_sessizlik": 0.90},
                         {"prime_precision": 0.55, "tuzak_sessizlik": 0.92})

    assert undone == 0
    assert all(store.peek(i) is not None for i in report.node_ids)


def test_the_exam_never_undoes_what_actually_happened(store, tmp_path,
                                                      clock) -> None:
    """Replay and credit assignment are records, not guesses: they stay."""
    from dornick.events import EventLog

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    a = store.remember("Gate kuyruğu boşaltılıyor.", kind="procedure")
    b = store.remember("Modem PIN kodu kırmızı defterde.", kind="fact")
    ids = _episodes(store, 5)
    log = EventLog(sessions / "s1.jsonl",
                   saat=lambda: clock().isoformat(timespec="milliseconds"))
    for node_id in (a.id, b.id, *ids):
        log.note("mind_open", memory_id=node_id)
    log.note("sonuc", sonuc="basarili")

    model = fake_model(f"Raporlar xlsx üretiliyor. [{ids[0]}]")
    sinav = iter([{"prime_precision": 0.60, "tuzak_sessizlik": 0.90},
                  {"prime_precision": 0.30, "tuzak_sessizlik": 0.90}])
    report = orgu.gece_gecisi(store, sessions, saat=clock,
                              filigran=tmp_path / "w.json", model=model,
                              state_dir=tmp_path, sinav=lambda: next(sinav))

    assert report.geri_alinan >= 1
    assert store.sicil(a.id) == (1, 0)              # credit survived
    assert b.id in {n.id for n, _w, _r in store.komsular_gerekceli(a.id)}
