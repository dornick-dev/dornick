"""The chat renders what the model said — Playwright against a live server.

Live wound (05.09, packaged 1.5.0): an answer that mentioned a file path
streamed, then vanished, and the loader knot stayed although the session
log held the full reply. md.js still called its translation helper under
the old Turkish name (`ceviri`) when it built a path chip; the
ReferenceError aborted the render and the turn never closed on screen.
A grep cannot see an undefined identifier — only a browser can — so the
shapes that failed are drawn here with the page's error budget at zero.

Playwright and its Chromium are optional: without them the module skips
cleanly (`py -m playwright install chromium` puts the browser in place).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

pw = pytest.importorskip("playwright.sync_api",
                         reason="playwright yok — tarayıcı testleri atlandı")

from dornick.config import Config          # noqa: E402
from dornick.events import EventLog        # noqa: E402
from dornick.mind import open_mind         # noqa: E402
from dornick.web import MindServer         # noqa: E402


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
def server(tmp_path: Path) -> Iterator[MindServer]:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    mind = open_mind(tmp_path / "mind", config.sessions_dir, "cur")
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
    context.add_init_script('localStorage.setItem("dornick-dil", "tr");')
    pg = context.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda err: errors.append(str(err)))
    pg.goto(server.url)
    pg.wait_for_function("typeof Markdown !== 'undefined' && typeof History !== 'undefined'")
    pg.errors = errors  # type: ignore[attr-defined]
    yield pg
    context.close()


# What the model actually answered on 05.09 — file paths in backticks, a
# produced file, a source list. Every one of these opens a chip.
ANSWER = (
    "Hatırladıklarım:\n\n"
    "- `D:\\Projects\\Envest\\MergenHubWebSite` klasörünü açıp inceledik\n"
    "- Envest raporu: `raporlar/envest-genel-rapor.pdf`\n"
    "- Ekran görüntüsü: `raporlar/panel.png`\n"
    "- [Rapor](raporlar/envest-genel-rapor.pdf) · [Arşiv](raporlar/paket.zip)\n"
    "- Python + PostgreSQL yığını\n\n"
    "Kaynaklar:\n"
    "1. https://envest.com.tr\n"
)

DRAW = """(text) => {
  const box = document.createElement("div");
  document.body.append(box);
  Markdown.into(box, text);
  return { nodes: box.querySelectorAll("*").length,
           chips: box.querySelectorAll('[title*="Tıkla"]').length,
           text: box.textContent };
}"""


def test_an_answer_with_file_paths_renders_without_a_page_error(page) -> None:
    out = page.evaluate(DRAW, ANSWER)
    assert page.errors == [], page.errors
    assert out["nodes"] > 4
    assert out["chips"] >= 3                    # viewer, browser and download chips all threw
    assert "PostgreSQL" in out["text"]          # nothing after the chip was lost


def test_a_transcript_with_file_paths_loads_without_a_page_error(page, server: MindServer) -> None:
    """The same wound on the other door: reopening a chat replays its turns
    through the same renderer (app.js loadTranscript)."""
    page.evaluate("""() => {
      const msgs = document.getElementById("messages") || document.body;
      for (const t of ["merhaba", "%s"]) {
        const box = document.createElement("div");
        msgs.append(box);
        Markdown.into(box, t);
      }
    }""" % ANSWER.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"'))
    assert page.errors == [], page.errors
