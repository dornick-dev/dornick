"""Night pass — replay, credit, stitching, reweaving, downscaling.

Until now night school did *training*; it did no *replay*. The real work
the brain does at night is replaying the day's sequences, and none of what
falls out of that existed in dornick:

* every edge was "similar content" — there was no **experienced together**
  bond;
* the `uses` counter gave the memory that led to the wrong answer the same
  point as the one that led to the right answer — no credit assignment;
* `_weave` froze at write time, the graph depended on order;
* nothing that strengthened by day ever shrank, edges bloated.

The tests here push on each of these five steps separately. Step 6
(distillation) is a separate PR; only its **gate** is tested here: without
a model it is skipped and the first five steps still run.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.events import EventLog
from dornick.recall import activation as A
from dornick.recall import open_store, weave

NOW = datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc)   # a Monday


class Calendar:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)

    def text(self) -> str:
        return self.moment.isoformat(timespec="milliseconds")


@pytest.fixture()
def calendar() -> Calendar:
    return Calendar(NOW)


@pytest.fixture()
def store(tmp_path: Path, calendar: Calendar):
    s = open_store(tmp_path / "memory", clock=calendar)
    yield s
    s.close()


@pytest.fixture()
def sessions(tmp_path: Path) -> Path:
    path = tmp_path / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def watermark(tmp_path: Path) -> Path:
    return tmp_path / "filigran.json"


class Log:
    """A helper that writes one session's event log — the product's own EventLog."""

    def __init__(self, folder: Path, session: str, calendar: Calendar) -> None:
        self.log = EventLog(folder / f"{session}.jsonl", clock=calendar.text)
        self.log.note("session_start", session_id=session)
        self.calendar = calendar

    def touch(self, node_id: str, event: str = "mind_open", **meta) -> Log:
        self.calendar.advance(minutes=1)
        self.log.note(event, memory_id=node_id, **meta)
        return self

    def tool(self, name: str, *, error: bool = False, summary: str = "") -> Log:
        self.calendar.advance(minutes=1)
        self.log.note("tool_start", tool=name, input={})
        self.log.note("tool_end", tool=name, error=error, ms=10, ozet=summary)
        return self

    def close(self, outcome: str = "basarili") -> Log:
        self.calendar.advance(minutes=1)
        self.log.note("sonuc", sonuc=outcome)
        self.log.close()
        return self


def _night(store, sessions, watermark, calendar, **kw):
    return weave.night_pass(store, sessions, clock=calendar, watermark=watermark, **kw)


# -- Step 2: temporal adjacency ----------------------------------------


def test_pair_used_back_to_back_in_one_session_is_linked(
        store, sessions, watermark, calendar) -> None:
    """"What was the thing I used while doing that report" is not findable by content."""
    a = store.remember("Vardiya raporu şablonu üç sayfalı bir Excel dosyası.",
                       kind="fact")
    b = store.remember("Kırmızı defterin arkasında modem PIN kodu yazıyor.",
                       kind="fact")
    Log(sessions, "s1", calendar).touch(a.id).touch(b.id).close()

    report = _night(store, sessions, watermark, calendar)
    assert report.new_edges >= 1

    neighbours = {n.id: r for n, _w, r in store.neighbours_with_reasons(a.id)}
    assert b.id in neighbours
    assert "birlikte kullanıldı" in neighbours[b.id]


def test_temporal_adjacency_does_not_leak_into_the_prime(store, sessions, watermark, calendar) -> None:
    """The edge enriches explicit search, it does not pollute automatic injection."""
    from dornick.loop import select_prime
    from dornick.mind import open_mind

    a = store.remember("Vardiya raporu şablonu üç sayfalı Excel dosyası.", kind="fact")
    b = store.remember("Kırmızı defterin arkasında modem PIN kodu yazıyor.", kind="fact")
    Log(sessions, "s1", calendar).touch(a.id).touch(b.id).close()
    _night(store, sessions, watermark, calendar)

    mind = open_mind(store.path.parent, sessions, "t", clock=calendar)
    try:
        hits = select_prime(mind, "Vardiya raporu şablonu kaç sayfaydı?", limit=5)
        assert b.id not in {h.item.id for h in hits}
        explicit = {h.item.id for h in mind.recall("Vardiya raporu şablonu", limit=5)}
        assert b.id in explicit
    finally:
        mind.store.close()


def test_repeated_co_use_strengthens_the_edge(
        store, sessions, watermark, calendar) -> None:
    """Things often used together must bond strongly; not freeze at the max."""
    a = store.remember("Terfi istasyonu yolu yağmurda çamur oluyor.", kind="fact")
    middle = store.remember("Kırtasiye siparişi perşembe verilir.", kind="fact")
    b = store.remember("Faturalar muhasebeye ayın yirmisinde gönderiliyor.",
                       kind="fact")

    def _weight() -> float:
        return dict((n.id, w) for n, w, _r in store.neighbours_with_reasons(a.id))[b.id]

    # The pair at distance two is measured: the adjacent pair starts at 0.6
    # and the weight ceiling is 1.0 — "double" is mathematically impossible there.
    Log(sessions, "once", calendar).touch(a.id).touch(middle.id).touch(b.id).close()
    _night(store, sessions, watermark, calendar)
    single = _weight()

    for i in range(4):
        calendar.advance(days=1)
        (Log(sessions, f"repeat{i}", calendar)
         .touch(a.id).touch(middle.id).touch(b.id).close())
        _night(store, sessions, watermark, calendar)

    assert _weight() > single * 2


# -- Step 2b: schema refresh -------------------------------------------


def test_neighbour_of_what_was_used_is_refreshed(store, sessions, watermark, calendar) -> None:
    """The old consolidates not by scanning but by being linked to a schema."""
    x = store.remember("Terfi hattı basınç sınırı altı bar.", kind="fact")
    y = store.remember("Terfi hattı basıncı manometreden okunuyor.", kind="fact")
    w = store.remember("Kapı kilidi silindirli.", kind="fact")
    store.link(x.id, y.id, weight=0.8, reason="benzer icerik")

    calendar.advance(days=30)
    Log(sessions, "s1", calendar).touch(y.id).close()
    _night(store, sessions, watermark, calendar)

    assert any(k.label == A.SCHEMA for k in store.use_log(x.id))
    assert not any(k.label == A.SCHEMA for k in store.use_log(w.id))


def test_schema_refresh_raises_activation(
        store, sessions, watermark, calendar) -> None:
    x = store.remember("Dozaj tankı kapasitesi bin litre.", kind="fact")
    y = store.remember("Dozaj tankı seviyesi haftalık kontrol ediliyor.", kind="fact")
    control = store.remember("Merdiven korkuluğu galvanizli.", kind="fact")
    store.link(x.id, y.id, weight=0.8, reason="benzer icerik")

    calendar.advance(days=30)
    Log(sessions, "s1", calendar).touch(y.id).close()
    _night(store, sessions, watermark, calendar)

    assert store.peek(x.id).activation > store.peek(control.id).activation


# -- Step 3: reverse replay --------------------------------------------


def test_memory_that_led_to_success_ranks_above_the_one_that_led_to_failure(
        store, sessions, watermark, calendar) -> None:
    good = store.remember("Gate servisi yeniden başlatılırken kuyruk boşaltılıyor.",
                          kind="procedure")
    bad = store.remember("Gate servisi doğrudan kill ile durduruluyor.",
                         kind="procedure")
    Log(sessions, "ok", calendar).touch(good.id).tool("kos").close("basarili")
    calendar.advance(days=1)
    Log(sessions, "hata", calendar).touch(bad.id).tool(
        "kos", error=True, summary="3 test kırıldı").close("basarisiz")

    _night(store, sessions, watermark, calendar)

    result = store.recall("Gate servisi yeniden başlatma", limit=8)
    ranked = [n.id for n in result.hits]
    assert ranked.index(good.id) < ranked.index(bad.id)
    assert store.track_record(good.id) == (1, 0)
    assert store.track_record(bad.id) == (0, 1)


def test_a_lesson_sits_next_to_the_path_that_led_to_failure(
        store, sessions, watermark, calendar) -> None:
    bad = store.remember("Şema göçü doğrudan üretimde koşuluyor.", kind="procedure")
    Log(sessions, "hata", calendar).touch(bad.id).tool(
        "kos", error=True, summary="göç yarıda kaldı").close("basarisiz")
    report = _night(store, sessions, watermark, calendar)

    assert report.lessons_written >= 1
    lessons = [n for n in store.by_kind("lesson", limit=10)]
    assert lessons
    assert bad.id in {n.id for n, _w, _r in store.neighbours_with_reasons(lessons[0].id)}


def test_successful_sequence_writes_a_procedure(store, sessions, watermark, calendar) -> None:
    three = [store.remember(f"Adım {i}: saha kontrolü {i}.", kind="fact")
             for i in range(3)]
    g = Log(sessions, "ok", calendar)
    for n in three:
        g.touch(n.id)
    g.tool("kos").tool("dosya_yaz").close("basarili")

    report = _night(store, sessions, watermark, calendar)
    assert report.procedures_written >= 1


def test_mixed_record_beats_never_touched(
        store, sessions, watermark, calendar) -> None:
    record = store.remember("Bellek sızıntısı tracemalloc ile bulunuyor.",
                            kind="procedure")
    untouched = store.remember("Priz grubu topraklı tip.", kind="fact")
    for i in range(3):
        calendar.advance(days=1)
        Log(sessions, f"ok{i}", calendar).touch(record.id).close("basarili")
    calendar.advance(days=1)
    Log(sessions, "hata", calendar).touch(record.id).tool(
        "kos", error=True, summary="patladı").close("basarisiz")
    _night(store, sessions, watermark, calendar)

    assert store.track_record(record.id) == (3, 1)
    assert store.peek(record.id).activation > store.peek(untouched.id).activation


def test_open_goal_writes_where_you_left_off(store, sessions, watermark, calendar) -> None:
    a = store.remember("Kurulum paketi imzalanacak.", kind="fact")
    Log(sessions, "acik", calendar).touch(a.id).close("acik")
    _night(store, sessions, watermark, calendar)
    assert store.by_kind("goal", limit=5)


# -- Step 4: stitching -------------------------------------------------


def test_a_sequence_never_experienced_is_stitched(store, sessions, watermark, calendar) -> None:
    """Monday A→B, Thursday B→C. A and C were never experienced together."""
    # Filler: in a small memory `_weave` links everything to everything and
    # no gap is left to stitch. That is not the case in a real memory.
    for text in ("Kırtasiye siparişi perşembe veriliyor.",
                 "Ofis bitkileri haftada iki kez sulanıyor.",
                 "Kapı zilinin pili bitmek üzere.",
                 "Yemek kartı her ayın ilk günü yükleniyor.",
                 "Asansör bakımı her çeyrekte yapılıyor.",
                 "Yazıcı kartuşu uyumlu marka alınıyor."):
        store.remember(text, kind="fact")
    a = store.remember("Karatay deposu seviye ölçümü saatte bir alınıyor.", kind="fact")
    b = store.remember("Ölçüm verisi gece yarısı özetleniyor.", kind="fact")
    c = store.remember("Bordro dosyası muhasebeye kapalı zarfla veriliyor.",
                       kind="fact")
    assert c.id not in {n.id for n, _w, _r in store.neighbours_with_reasons(a.id)}
    Log(sessions, "pzt", calendar).touch(a.id).touch(b.id).close()
    calendar.advance(days=1)
    Log(sessions, "prs", calendar).touch(b.id).touch(c.id).close()

    report = _night(store, sessions, watermark, calendar)
    assert report.stitched >= 1

    reasons = {n.id: r for n, _w, r in store.neighbours_with_reasons(a.id)}
    assert c.id in reasons
    assert b.id in reasons[c.id]          # the node stitched through is named


# -- Step 5: reweaving and downscaling ---------------------------------


def test_untouched_edge_melts_every_night(store, sessions, watermark, calendar) -> None:
    a = store.remember("Kavanoz kapakları paslanıyor.", kind="fact")
    b = store.remember("Ütü masasının ayağı gevşek.", kind="fact")
    store.link(a.id, b.id, weight=1.0, reason="elle")
    before = dict((n.id, w) for n, w, _r in store.neighbours_with_reasons(a.id))[b.id]

    for i in range(20):
        calendar.advance(days=1)
        _night(store, sessions, watermark, calendar)
    after = dict((n.id, w) for n, w, _r in store.neighbours_with_reasons(a.id))[b.id]

    expected = before * (1 - weave.EPSILON) ** 20
    assert after == pytest.approx(expected, rel=0.05)


def test_edge_below_the_floor_is_deleted(store, sessions, watermark, calendar) -> None:
    """An edge may be deleted, a node may not: an edge is a road, not knowledge."""
    a = store.remember("Semt pazarı perşembe kuruluyor.", kind="fact")
    b = store.remember("Sokak lambası akşamları geç yanıyor.", kind="fact")
    store.link(a.id, b.id, weight=weave.EDGE_FLOOR + 0.001, reason="zayıf")
    calendar.advance(days=1)
    report = _night(store, sessions, watermark, calendar)

    assert report.edges_removed >= 1
    assert b.id not in {n.id for n, _w, _r in store.neighbours_with_reasons(a.id)}
    assert store.peek(a.id) is not None and store.peek(b.id) is not None


def test_edge_touched_every_night_stays_above_the_floor(
        store, sessions, watermark, calendar) -> None:
    a = store.remember("Jeneratör otomatiği el konumunda bırakılmamalı.", kind="fact")
    b = store.remember("Toplantı odası projektörü HDMI ile çalışıyor.", kind="fact")
    for i in range(20):
        calendar.advance(days=1)
        Log(sessions, f"g{i}", calendar).touch(a.id).touch(b.id).close()
        _night(store, sessions, watermark, calendar)
    weight = dict((n.id, w) for n, w, _r in store.neighbours_with_reasons(a.id))[b.id]
    assert weight > weave.EDGE_FLOOR * 3


def test_reweaving_breaks_order_dependence(tmp_path: Path) -> None:
    """The same hundred nodes written in reverse order should yield a similar graph."""
    bodies = [f"Saha notu {i}: pompa {i} bakım kaydı ve ölçüm sonucu." % ()
              for i in range(40)]

    def _graph(order: list[str], name: str) -> set[tuple[str, str]]:
        calendar = Calendar(NOW)
        st = open_store(tmp_path / name, clock=calendar)
        session_dir = tmp_path / f"{name}-sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        try:
            ids = {}
            for body in order:
                ids[body] = st.remember(body, kind="fact").id
            for i in range(5):
                calendar.advance(days=1)
                g = Log(session_dir, f"g{i}", calendar)
                for body in order[i * 8:(i + 1) * 8]:
                    g.touch(ids[body])
                g.close()
                weave.night_pass(st, session_dir, clock=calendar,
                                 watermark=tmp_path / f"{name}.json")
            inverse = {v: k for k, v in ids.items()}
            return {tuple(sorted((inverse[a], inverse[b])))
                    for a, b, _w in st.links(limit=5000)}
        finally:
            st.close()

    forward = _graph(bodies, "forward")
    backward = _graph(list(reversed(bodies)), "backward")
    overlap = len(forward & backward) / max(len(forward | backward), 1)
    assert overlap >= 0.5, f"overlap {overlap:.2f}"


# -- priority, budget, watermark ---------------------------------------


def test_failed_session_is_replayed_before_routine(
        store, sessions, watermark, calendar) -> None:
    a = store.remember("Rutin saha notu.", kind="fact")
    b = store.remember("Göç sırasında veri kayboldu.", kind="fact")
    Log(sessions, "rutin", calendar).touch(a.id).close("basarili")
    Log(sessions, "kotu", calendar).touch(b.id).tool(
        "kos", error=True, summary="kırıldı").close("basarisiz")

    ranked = weave.prioritised_sessions(store, sessions, clock=calendar, watermark=watermark)
    assert ranked[0].id == "kotu"


def test_remaining_sessions_carry_over_when_the_budget_runs_out(
        store, sessions, watermark, calendar) -> None:
    """The remainder is not skipped, it moves to the next night."""
    for i in range(6):
        n = store.remember(f"Saha kaydı {i}.", kind="fact")
        Log(sessions, f"s{i}", calendar).touch(n.id).close()

    report = _night(store, sessions, watermark, calendar, budget_s=0.0)
    assert report.carried_over > 0
    assert report.replayed <= 1          # the first unit still completes

    second = _night(store, sessions, watermark, calendar, budget_s=300.0)
    assert second.replayed >= report.carried_over - 1


def test_processed_session_is_not_replayed_the_second_night(
        store, sessions, watermark, calendar) -> None:
    """No double counting: the same session must not pay out twice."""
    n = store.remember("Kurulum paketi imzalandı.", kind="fact")
    Log(sessions, "s1", calendar).touch(n.id).close("basarili")
    _night(store, sessions, watermark, calendar)
    first_record = store.track_record(n.id)

    calendar.advance(days=1)
    second = _night(store, sessions, watermark, calendar)
    assert second.replayed == 0
    assert store.track_record(n.id) == first_record


def test_watermark_is_written_to_disk(store, sessions, watermark, calendar) -> None:
    n = store.remember("Bir kayıt.", kind="fact")
    Log(sessions, "s1", calendar).touch(n.id).close()
    _night(store, sessions, watermark, calendar)
    status = json.loads(watermark.read_text(encoding="utf-8"))
    assert "s1" in status["islenen"]


def test_unclosed_session_is_not_replayed(store, sessions, watermark, calendar) -> None:
    """A session without an outcome is not a source: it may still be running."""
    n = store.remember("Yarım kalan iş.", kind="fact")
    Log(sessions, "acik", calendar).touch(n.id)      # no close()
    report = _night(store, sessions, watermark, calendar)
    assert report.replayed == 0


# -- retroactive capture -----------------------------------------------


def test_calm_record_next_to_a_surprising_event_is_captured(
        store, sessions, watermark, calendar) -> None:
    # Being ordinary is a matter of context: a record with no look-alikes is surprising.
    for text in ("Sabah kahvesi mutfakta içildi.",
                 "Sabah kahvesi bahçede içildi.",
                 "Sabah kahvesi toplantıda içildi."):
        store.remember(text, kind="fact")
    calm = store.remember("Sabah kahvesi ofiste içildi.", kind="fact")
    calendar.advance(minutes=10)
    surprising = store.remember(
        "Ana pano yandı; bütün saha elektriksiz kaldı ve üretim durdu.",
        kind="lesson")
    g = Log(sessions, "s1", calendar)
    g.touch(calm.id).touch(surprising.id).close("basarisiz")
    _night(store, sessions, watermark, calendar)

    assert any(k.label == A.CAPTURED for k in store.use_log(calm.id))


def test_distant_record_is_not_captured(store, sessions, watermark, calendar) -> None:
    """±60 minutes is a boundary, not a slogan."""
    for text in ("Yeni kalem kutusu rafa kondu.", "Yeni kalem kutusu çekmeceye kondu.",
                 "Yeni kalem kutusu dolaba kondu."):
        store.remember(text, kind="fact")
    distant = store.remember("Yeni kalem kutusu masaya kondu.", kind="fact")
    calendar.advance(minutes=200)
    surprising = store.remember(
        "Veritabanı bozuldu; son iki günün ölçümü kayboldu.", kind="lesson")
    g = Log(sessions, "s1", calendar)
    g.touch(distant.id)
    calendar.advance(minutes=200)
    g.touch(surprising.id).close("basarisiz")
    _night(store, sessions, watermark, calendar)

    assert not any(k.label == A.CAPTURED for k in store.use_log(distant.id))


# -- distillation gate (Step 6 is a separate PR) -----------------------


def test_without_a_model_distillation_is_skipped_but_the_night_runs(
        store, sessions, watermark, calendar) -> None:
    a = store.remember("Bir kayıt.", kind="fact")
    b = store.remember("Başka bir kayıt.", kind="fact")
    Log(sessions, "s1", calendar).touch(a.id).touch(b.id).close()
    report = _night(store, sessions, watermark, calendar, model=None)
    assert "atlandı" in report.distillation
    assert report.replayed == 1          # the first five steps still ran


# -- ablation ----------------------------------------------------------


def test_night_writes_no_edge_while_weave_is_off(
        store, sessions, watermark, calendar) -> None:
    from dornick.recall import switches

    a = store.remember("Pano etiketleri Brother ile basılıyor.", kind="fact")
    b = store.remember("Ofis bitkileri haftada iki kez sulanıyor.", kind="fact")
    Log(sessions, "s1", calendar).touch(a.id).touch(b.id).close()
    with switches.disabled("weave"):
        report = _night(store, sessions, watermark, calendar)
    assert report.replayed == 0
    assert b.id not in {n.id for n, _w, _r in store.neighbours_with_reasons(a.id)}
