"""Brain view, end to end (roadmap 6.5) — Playwright against a live server.

What these defend, in the browser rather than by grep:

* a recorded night replays and lights the nodes in the ORDER of the file,
* after `uyku.uyandi` no animation frame advances,
* clicking an identity sentence lights its evidence nodes,
* a 5k-event night at 60x plays without stutter (frame drop < 5%).

The night files are generated with `night_events.build()` and checked with
`validate()` — no hand-written events, so the fixture cannot drift from the
frozen schema.

Playwright and its Chromium are optional: without them the module skips
cleanly (`py -m playwright install chromium` puts the browser in place).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest

pw = pytest.importorskip("playwright.sync_api",
                         reason="playwright yok — tarayıcı testleri atlandı")

from dornick.config import Config          # noqa: E402
from dornick.events import EventLog        # noqa: E402
from dornick.mind import open_mind         # noqa: E402
from dornick.recall import identity, night_events as ne   # noqa: E402
from dornick.web import MindServer         # noqa: E402

START = datetime(2025, 6, 2, 23, 0, tzinfo=timezone.utc)


# -- fixtures ------------------------------------------------------------


@pytest.fixture(scope="module")
def browser() -> Iterator[object]:
    with pw.sync_playwright() as p:
        try:
            chromium = p.chromium.launch()
        except Exception as exc:  # the package is there, the browser is not
            pytest.skip(f"Playwright tarayıcısı yok: {str(exc).splitlines()[0][:120]}")
        yield chromium
        chromium.close()


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    cfg = Config.load(tmp_path)
    cfg.ensure_dirs()
    return cfg


@pytest.fixture()
def server(tmp_path: Path, config: Config) -> Iterator[MindServer]:
    mind = open_mind(tmp_path / "mind", config.sessions_dir, "cur")
    mind.remember("Fatih SCADA tarafında çalışıyor.", kind="user")
    log = EventLog(tmp_path / "s.jsonl")
    srv = MindServer(mind, log, port=0, config=config)
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()
        log.close()


@pytest.fixture()
def page(browser, server: MindServer):
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    # The brain as a PANEL (not ambient behind the chat): the region strips
    # and the night sheet live in the panel.
    context.add_init_script(
        'localStorage.setItem("dornick-brain-ambient", "kapali");'
        'localStorage.setItem("dornick-mind", "acik");'
        'localStorage.setItem("dornick-dil", "tr");')
    pg = context.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda err: errors.append(str(err)))
    pg.goto(server.url)
    pg.wait_for_function("typeof Scene !== 'undefined' && typeof Night !== 'undefined'"
                         " && typeof Regions !== 'undefined'")
    pg.wait_for_selector("#regions-tabs", state="attached")
    pg.errors = errors  # type: ignore[attr-defined]
    yield pg
    context.close()


# -- the recorded night ----------------------------------------------------


def write_night(state_dir: Path, date: str, events: list[dict]) -> Path:
    """Events built by the schema, validated by the schema, on disk."""
    path = ne.night_path(state_dir, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(ne.validate(event), ensure_ascii=False) + "\n")
    return path


def ticking() -> callable:
    moment = [START]

    def clock() -> datetime:
        moment[0] += timedelta(milliseconds=250)
        return moment[0]
    return clock


def small_night() -> tuple[list[dict], list[str]]:
    """A short night and the node order the view must light for it.

    tekrar.ileri lights its chain forward, tekrar.geri the same chain
    backwards, dikis the node in between, dokunus the touched node, damitma
    the sources then the new node.
    """
    clock = ticking()
    b = lambda kind, **f: ne.build(kind, clock, **f)   # noqa: E731
    events = [
        b("uyku.basladi", basinc=0.7, tahmini_uyanma="08:30", dongu_sayisi=2),
        b("uyku.dongu", no=1, faz="derin"),
        b("tekrar.ileri", oturum="s1", dizi=["n_a", "n_b", "n_c"],
          kenarlar=[["n_a", "n_b", 0.6], ["n_b", "n_c", 0.4]]),
        b("tekrar.geri", oturum="s1", sonuc="basari",
          paylar={"n_a": 0.5, "n_b": 0.3, "n_c": 0.2}),
        b("dikis", a="n_a", b="n_c", uzerinden="n_b", oturumlar=["s1", "s2"]),
        b("dokunus", id="n_d"),
        b("uyku.dongu", no=2, faz="rem"),
        b("damitma", kaynaklar=["n_a", "n_d"], yeni="n_new"),
        b("uyku.bitti", sebep="basinc", rapor={"session_count": 1, "new_edges": 2,
                                                "lessons_written": 1, "contradictions": 0}),
    ]
    expected = (["n_a", "n_b", "n_c"] + ["n_c", "n_b", "n_a"] + ["n_b"] + ["n_d"]
                + ["n_a", "n_d", "n_new"])
    return events, expected


def cut_night() -> list[dict]:
    """A night the user interrupts: the chain after `uyku.uyandi` must never light."""
    clock = ticking()
    b = lambda kind, **f: ne.build(kind, clock, **f)   # noqa: E731
    return [
        b("uyku.basladi", basinc=0.9, tahmini_uyanma="07:45", dongu_sayisi=3),
        b("uyku.dongu", no=1, faz="derin"),
        b("tekrar.ileri", oturum="s1", dizi=["k_1", "k_2", "k_3"], kenarlar=[]),
        b("uyku.uyandi", sebep="kullanici", dongu=1, tamamlanan=12, devreden=18,
          borc={"faz": "rem"}),
        b("tekrar.ileri", oturum="s2", dizi=["late_1", "late_2"], kenarlar=[]),
        b("dokunus", id="late_3"),
    ]


def big_night(sessions: int = 200) -> list[dict]:
    """≈5k events: the roadmap's 200-session night."""
    clock = ticking()
    b = lambda kind, **f: ne.build(kind, clock, **f)   # noqa: E731
    out = [b("uyku.basladi", basinc=1.0, tahmini_uyanma="08:00", dongu_sayisi=6)]
    for cycle in range(1, 7):
        out.append(b("uyku.dongu", no=cycle, faz="derin" if cycle < 4 else "rem"))
        for s in range(sessions // 6 + 1):
            sid = f"s{cycle}_{s}"
            chain = [f"{sid}_n{i}" for i in range(8)]
            out.append(b("tekrar.ileri", oturum=sid, dizi=chain,
                         kenarlar=[[chain[i], chain[i + 1], 0.5] for i in range(7)]))
            out.append(b("tekrar.geri", oturum=sid, sonuc="basari" if s % 3 else "basarisiz",
                         paylar={n: 1 / 8 for n in chain}))
            for k in range(7):
                out.append(b("dikis", a=chain[0], b=chain[7], uzerinden=chain[k + 1],
                             oturumlar=[sid]))
            for k in range(15):
                out.append(b("dokunus", id=f"{sid}_t{k}"))
            if cycle >= 4:
                out.append(b("damitma", kaynaklar=chain[:3], yeni=f"{sid}_d"))
    out.append(b("uyku.bitti", sebep="basinc", rapor={"session_count": sessions}))
    return out


# -- helpers ----------------------------------------------------------------


def open_details(page) -> None:
    """The night tab is one of the details: open the strip first."""
    if not page.evaluate("Regions.details()"):
        page.click("#brain-details-toggle")
    page.wait_for_selector('#regions-tabs button[data-sheet="night"]', state="visible")


def open_night_sheet(page, date: str, speed: int) -> None:
    open_details(page)
    page.click('#regions-tabs button[data-sheet="night"]')
    page.wait_for_selector("#night-select")
    page.select_option("#night-select", date)
    page.click(f'#night-speed button[data-speed="{speed}"]')
    page.click("#night-play")


# -- tests --------------------------------------------------------------


def test_a_recorded_night_lights_nodes_in_the_order_of_the_file(page, config: Config) -> None:
    events, expected = small_night()
    write_night(config.state_dir, "2025-06-02", events)

    open_night_sheet(page, "2025-06-02", 60)
    page.wait_for_function(
        f"Scene.litLog().length >= {len(expected)} && Night.stats().queued === 0"
        " && Scene.planned() === 0", timeout=20000)

    lit = page.evaluate("Scene.litLog()")
    assert lit == expected
    assert page.evaluate("Night.stats().played") == len(events)
    assert not page.errors, page.errors


def test_no_animation_frame_advances_after_the_night_is_cut(page, config: Config) -> None:
    write_night(config.state_dir, "2025-06-03", cut_night())

    open_night_sheet(page, "2025-06-03", 60)
    page.wait_for_function("Night.stats().frozen === true", timeout=20000)

    before = page.evaluate("[Scene.frames(), Night.stats().frames, Scene.frozen(), Scene.litLog()]")
    page.wait_for_timeout(700)
    after = page.evaluate("[Scene.frames(), Night.stats().frames, Scene.frozen(), Scene.litLog()]")
    assert before[2] is True and after[2] is True
    assert after[0] == before[0], "sahnenin olay saati ilerledi"
    assert after[1] == before[1], "gece döngüsü kare ilerletti"
    assert after[3] == before[3]
    # The chain after the cut never lit; what was queued stays faint.
    assert not any(node.startswith("late_") for node in after[3])
    assert page.evaluate("Night.stats().queued") == 2
    badge = page.text_content("#night-badge")
    assert "12/30" in badge and "tekrar edildi" in badge and "18" in badge and "kullanıcı" in badge
    assert not page.errors, page.errors


def test_clicking_an_identity_sentence_lights_its_evidence(page, config: Config) -> None:
    identity.save(config.state_dir, identity.Identity(
        [("41 işin 33'ünde önce test yazdı", ["ev_1", "ev_2", "ev_3"])]))

    page.click('#regions-tabs button[data-sheet="identity"]')
    page.wait_for_selector(".identity-sentence .identity-text")
    page.evaluate("Scene.clearLog()")
    page.click(".identity-sentence .identity-text")
    page.wait_for_function("Scene.litLog().length >= 3", timeout=10000)

    assert page.evaluate("Scene.litLog()") == ["ev_1", "ev_2", "ev_3"]
    assert not page.errors, page.errors


def test_the_simple_block_is_the_default_and_follows_the_night(page, config: Config) -> None:
    """Varsayılan: şerit kapalı, blokta düz cümle, yüzde tam sayı. Ayrıntılar
    açılınca şerit ve Gece sekmesi görünür, seçim localStorage'da. Gece
    bitince blok "N konuşma tekrar edildi, M ders çıkardı" der."""
    events, _ = small_night()
    write_night(config.state_dir, "2025-06-02", events)
    page.reload()
    page.wait_for_function("typeof Regions !== 'undefined' && Regions.sentence")

    assert page.evaluate("Regions.details()") is False
    assert page.is_hidden("#regions-bottom")
    assert page.is_hidden('#regions-tabs button[data-sheet="night"]')
    line = page.text_content("#brain-simple-line")
    assert line.startswith("Uyanık."), line
    pct = page.text_content("#brain-simple-pct")
    assert pct.startswith("%") and pct[1:].isdigit(), pct
    # The newest recorded night is named under the sentence.
    page.wait_for_function("!document.getElementById('brain-simple-last').hidden", timeout=10000)
    assert "1 konuşma tekrar edildi" in page.text_content("#brain-simple-last-text")

    open_details(page)
    assert page.is_visible("#regions-bottom")
    assert page.evaluate("localStorage.getItem('dornick-beyin-ayrinti')") == "acik"
    assert page.text_content("#thalamus-wake").startswith("Uyanıklık %")
    assert page.text_content("#thalamus-pressure").startswith("Basınç ")
    assert page.text_content("#amygdala-note") == "Sürpriz: sakin"

    open_night_sheet(page, "2025-06-02", 60)
    page.wait_for_function("Night.stats().played >= 9 && Night.stats().queued === 0", timeout=20000)
    last = page.text_content("#brain-simple-last-text")
    assert "1 konuşma tekrar edildi" in last and "1 ders çıkardı" in last, last
    assert page.text_content("#brain-simple-line").startswith("Uyanık."), "gece bitti: blok uyanık olmalı"
    assert not page.errors, page.errors


def test_a_five_thousand_event_night_replays_at_sixty_x_without_stutter(page, config: Config) -> None:
    events = big_night()
    assert len(events) >= 5000
    write_night(config.state_dir, "2025-06-04", events)

    open_night_sheet(page, "2025-06-04", 60)
    page.wait_for_function("Night.stats().played > 50", timeout=20000)
    # Measure over a window while the replay is busy: the whole night at
    # 60x is a minute; the stutter shows in the first seconds if at all.
    page.evaluate("window.__t0 = Night.stats()")
    page.wait_for_timeout(6000)
    stats = page.evaluate("(() => { const s = Night.stats(); const a = window.__t0;"
                          " return { frames: s.frames - a.frames, dropped: s.dropped - a.dropped,"
                          " played: s.played - a.played }; })()")
    assert stats["frames"] >= 60, stats
    assert stats["played"] > 0, stats
    assert stats["dropped"] / stats["frames"] < 0.05, stats
    assert not page.errors, page.errors
