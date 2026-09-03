"""Chat surface equivalence: file mention, tasks, turn summary, budget brake.

Every test here holds the truth BEHIND a UI promise: if the menu promises
something, the server must have the counterpart and it must behave right.
The UI side (state machine, event contract) lives in `test_static.py`.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from dornick.config import Config
from dornick.events import EventLog
from dornick.mind import Mind, open_mind
from dornick.tools.checkpoint import KLASOR, Defter
from dornick.web import MindServer


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


def _setup(tmp_path: Path, mind: Mind, controller: object | None = None):
    """A server that is up + the things to close afterwards."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config, controller=controller)  # type: ignore[arg-type]
    server.start()
    return server, config, log


def _get(server: MindServer, path: str) -> dict:
    with urllib.request.urlopen(server.url + path.lstrip("/"), timeout=8) as answer:
        return json.loads(answer.read().decode("utf-8"))


def _post(server: MindServer, path: str, body: dict) -> dict:
    request = urllib.request.Request(
        server.url + path.lstrip("/"),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=8) as answer:
        return json.loads(answer.read().decode("utf-8"))


# -- `@` file mention ---------------------------------------------------


def test_the_file_search_finds_a_file_by_its_name(tmp_path: Path, mind: Mind) -> None:
    """The user typing `@` doesn't know the file's full path — they know its name."""
    server, config, log = _setup(tmp_path, mind)
    root = Path(config.workspace)
    (root / "derin" / "alt").mkdir(parents=True, exist_ok=True)
    (root / "derin" / "alt" / "olcum-raporu.md").write_text("veri", encoding="utf-8")
    try:
        reply = _get(server, "/api/files/search?q=olcum")
    finally:
        server.stop()
        log.close()

    paths = [f["path"] for f in reply["files"]]
    assert "derin/alt/olcum-raporu.md" in paths
    # The name comes too: full path in the chip, readable name in the list.
    assert any(f["name"] == "olcum-raporu.md" for f in reply["files"])


def test_the_file_search_skips_tool_droppings_and_hidden_folders(
    tmp_path: Path, mind: Mind
) -> None:
    """Searching inside `.git` and `node_modules` fills the list with junk and
    makes the wanted file invisible."""
    server, config, log = _setup(tmp_path, mind)
    root = Path(config.workspace)
    for dirty in (".git", "node_modules", "__pycache__", ".gizli"):
        (root / dirty).mkdir(parents=True, exist_ok=True)
        (root / dirty / "hedef.txt").write_text("x", encoding="utf-8")
    (root / "hedef.txt").write_text("x", encoding="utf-8")
    try:
        reply = _get(server, "/api/files/search?q=hedef")
    finally:
        server.stop()
        log.close()

    paths = [f["path"] for f in reply["files"]]
    assert paths == ["hedef.txt"], paths


def test_an_empty_query_offers_the_most_recently_touched_files(
    tmp_path: Path, mind: Mind
) -> None:
    """The user typing `@` most often wants the file they are working on."""
    import os
    import time

    server, config, log = _setup(tmp_path, mind)
    root = Path(config.workspace)
    for name in ("eski.txt", "yeni.txt"):
        (root / name).write_text("x", encoding="utf-8")
    now = time.time()
    os.utime(root / "eski.txt", (now - 9000, now - 9000))
    os.utime(root / "yeni.txt", (now, now))
    try:
        reply = _get(server, "/api/files/search?q=")
    finally:
        server.stop()
        log.close()

    paths = [f["path"] for f in reply["files"]]
    assert paths.index("yeni.txt") < paths.index("eski.txt")


# -- running tasks ------------------------------------------------------


class FakeBridge:
    """The surface the tasks endpoint expects — a tiny imitation of the bridge."""

    def __init__(self) -> None:
        self.stopped: list[str] = []

    def snapshot(self) -> dict:
        return {"busy": False}

    def tasks(self) -> dict:
        return {"gorevler": [{"id": "c:abc", "ad": "model eğitimi", "tur": "iş",
                              "durum": "kosuyor", "basladi": 1.0, "bitti": 0.0,
                              "ozet": "", "oturum": "", "durdurulabilir": True}],
                "kosan": 1}

    def stop_task(self, gid: str) -> dict:
        self.stopped.append(gid)
        return {"ok": True, "id": gid}


def test_the_task_list_and_the_stop_button_reach_the_bridge(
    tmp_path: Path, mind: Mind
) -> None:
    bridge = FakeBridge()
    server, _config, log = _setup(tmp_path, mind, bridge)
    try:
        listing = _get(server, "/api/gorevler")
        stop = _post(server, "/api/gorevler/durdur", {"id": "c:abc"})
    finally:
        server.stop()
        log.close()

    assert listing["kosan"] == 1
    assert listing["gorevler"][0]["ad"] == "model eğitimi"
    assert stop["ok"] is True
    assert bridge.stopped == ["c:abc"]


def test_a_bridge_without_the_task_surface_answers_honestly(
    tmp_path: Path, mind: Mind
) -> None:
    """An observe-only bridge (preview) doesn't have to implement these
    endpoints: it should return an honest ok:false, not a 500."""
    server, _config, log = _setup(tmp_path, mind, SimpleNamespace(snapshot=lambda: {}))
    try:
        assert _get(server, "/api/gorevler") == {"gorevler": [], "kosan": 0}
        assert _post(server, "/api/gorevler/durdur", {"id": "c:x"})["ok"] is False
        assert _post(server, "/api/butce", {"usd": 5})["ok"] is False
        assert _post(server, "/api/compact", {})["ok"] is False
    finally:
        server.stop()
        log.close()


def test_a_helper_run_can_be_read_step_by_step(tmp_path: Path, mind: Mind) -> None:
    """When looking at a helper the question asked is 'what did it do?' —
    tool steps, not text turns."""
    server, config, log = _setup(tmp_path, mind)
    child = Path(config.sessions_dir) / "yardimci1.jsonl"
    child.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {"seq": 1, "kind": "meta", "role": None, "content": "tool_start",
         "meta": {"tool": "read_file", "input": {"path": "a.py"}}},
        {"seq": 2, "kind": "meta", "role": None, "content": "tool_end",
         "meta": {"tool": "read_file", "error": False, "ms": 12}},
        {"seq": 3, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": "Dosyayı okudum."}], "meta": {}},
        {"seq": 4, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": "iç not"}], "meta": {"internal": True}},
    ]
    child.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in lines),
                     encoding="utf-8")
    try:
        reply = _get(server, "/api/gorevler/dokum?oturum=yardimci1")
    finally:
        server.stop()
        log.close()

    assert reply["ok"] is True
    steps = reply["adimlar"]
    assert steps[0] == {"tur": "arac", "ad": "read_file", "hedef": "a.py",
                        "hata": False, "ms": 12}
    assert steps[1] == {"tur": "soz", "metin": "Dosyayı okudum."}
    # If an internal note doesn't reach the chat it must not reach the transcript either.
    assert len(steps) == 2


def test_the_step_log_refuses_a_path_shaped_session_id(
    tmp_path: Path, mind: Mind
) -> None:
    server, _config, log = _setup(tmp_path, mind)
    try:
        reply = _get(server, "/api/gorevler/dokum?oturum=../../gizli")
    finally:
        server.stop()
        log.close()
    assert reply["ok"] is False


def test_a_failed_job_report_page_reads_like_a_report_not_a_trace(
    tmp_path: Path, mind: Mind
) -> None:
    """Viewer report: 'İş başarısız' + package name; no traceback, no c:id."""
    from dornick.tools.shell import job_report

    class StubBridge:
        def snapshot(self) -> dict:
            return {"busy": False}

        def task_report(self, gid: str) -> dict:
            return {
                "ok": True,
                "id": "c:70032d",
                "title": "$ py tarama_modbus.py",
                "state": "hata",
                "metin": job_report(
                    command="py tarama_modbus.py",
                    code=1,
                    text="ModuleNotFoundError: No module named 'pymodbus'",
                ),
            }

    server, _config, log = _setup(tmp_path, mind, StubBridge())
    try:
        with urllib.request.urlopen(
            server.url + "gorev-rapor/70032d/", timeout=8
        ) as answer:
            page = answer.read().decode("utf-8")
    finally:
        server.stop()
        log.close()

    assert "İş başarısız" in page
    assert "pymodbus" in page
    assert "pip install pymodbus" in page
    assert "Traceback" not in page
    assert "c:70032d" not in page
    assert "<h1>$ py tarama_modbus.py</h1>" not in page


def test_a_successful_job_report_page_leads_with_summary_not_logs(
    tmp_path: Path, mind: Mind
) -> None:
    """Success page: summary + command; the raw log inside details."""
    from dornick.tools.shell import success_report

    log = (
        "Downloading package from builds.dotnet.microsoft.com\n"
        "Extracting the archive.\n"
        "dotnet-sdk-8.0.424-win-x64 installed.\n"
    )

    class StubBridge:
        def snapshot(self) -> dict:
            return {"busy": False}

        def task_report(self, gid: str) -> dict:
            return {
                "ok": True,
                "id": "c:abc123",
                "title": "$ $ErrorActionPreference='Stop'; ./dotnet-install.ps1",
                "state": "bitti",
                "metin": success_report(
                    command="$ErrorActionPreference='Stop'; ./dotnet-install.ps1",
                    text=log,
                ),
            }

    server, _config, logf = _setup(tmp_path, mind, StubBridge())
    try:
        with urllib.request.urlopen(
            server.url + "gorev-rapor/abc123/", timeout=8
        ) as answer:
            page = answer.read().decode("utf-8")
    finally:
        server.stop()
        logf.close()

    assert "İş tamamlandı" in page
    assert 'class="ozet"' in page
    assert "dotnet-sdk-8.0.424" in page
    assert 'class="cmd"' in page
    assert "dotnet-install" in page
    assert '<details class="log">' in page
    assert "Ham çıktı" in page
    assert "Downloading package" in page
    # The log must not cover the summary: details closed by default (no open).
    assert '<details class="log" open' not in page


# -- "what changed this turn" + undo ------------------------------------


def _write_ledger(config: Config, target: Path, old: str, new: str) -> Defter:
    """The same thing the tool layer does: take a snapshot BEFORE changing."""
    ledger = Defter(Path(config.state_dir) / KLASOR, "cur")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(old, encoding="utf-8")
    ledger.save(target, "edit_file")
    target.write_text(new, encoding="utf-8")
    return ledger


def test_the_ledger_lists_what_changed_and_from_where(
    tmp_path: Path, mind: Mind
) -> None:
    server, config, log = _setup(tmp_path, mind)
    target = Path(config.workspace) / "rapor.md"
    try:
        _write_ledger(config, target, "bir\niki\n", "bir\nÜÇ\n")
        everything = _get(server, "/api/degisiklikler")
        assert everything["son"] == 1
        assert everything["kayitlar"][0]["ad"] == "rapor.md"
        assert everything["kayitlar"][0]["arac"] == "edit_file"
        assert everything["kayitlar"][0]["gerialinabilir"] is True

        # Turn boundary: AFTER this record is empty.
        assert _get(server, "/api/degisiklikler?since=1")["kayitlar"] == []

        # A second change brings only the new record.
        _write_ledger(config, target, "bir\nÜÇ\n", "bir\nDÖRT\n")
        later = _get(server, "/api/degisiklikler?since=1")
        assert [k["sira"] for k in later["kayitlar"]] == [2]
    finally:
        server.stop()
        log.close()


def test_the_diff_shows_the_snapshot_against_what_is_on_disk_now(
    tmp_path: Path, mind: Mind
) -> None:
    server, config, log = _setup(tmp_path, mind)
    target = Path(config.workspace) / "rapor.md"
    try:
        _write_ledger(config, target, "eski hâl\n", "yeni hâl\n")
        diff = _get(server, "/api/degisiklikler/fark?sira=1")
    finally:
        server.stop()
        log.close()

    assert diff["ok"] is True and diff["metin"] is True
    assert diff["eski"] == "eski hâl\n"
    assert diff["yeni"] == "yeni hâl\n"


def test_undoing_the_turn_puts_the_files_back(tmp_path: Path, mind: Mind) -> None:
    """Undo goes through the `undo` tool's path: same ledger, same result."""
    server, config, log = _setup(tmp_path, mind)
    one = Path(config.workspace) / "bir.txt"
    two = Path(config.workspace) / "iki.txt"
    try:
        _write_ledger(config, one, "A", "A-değişti")
        _write_ledger(config, two, "B", "B-değişti")
        reply = _post(server, "/api/degisiklikler/geri", {"n": 2})
        assert reply["ok"] is True
        assert one.read_text(encoding="utf-8") == "A"
        assert two.read_text(encoding="utf-8") == "B"
    finally:
        server.stop()
        log.close()


def test_a_new_file_is_undone_by_deleting_it(tmp_path: Path, mind: Mind) -> None:
    """A 'did not exist' record in the ledger: undo reverts the creation."""
    server, config, log = _setup(tmp_path, mind)
    fresh = Path(config.workspace) / "taze.txt"
    try:
        ledger = Defter(Path(config.state_dir) / KLASOR, "cur")
        ledger.save(fresh, "write_file")     # the file does not exist yet
        fresh.write_text("içerik", encoding="utf-8")
        record = _get(server, "/api/degisiklikler")["kayitlar"][0]
        assert record["yoktu"] is True
        assert _post(server, "/api/degisiklikler/geri", {"n": 1})["ok"] is True
        assert not fresh.exists()
    finally:
        server.stop()
        log.close()


def test_a_single_file_can_be_undone_by_sequence(tmp_path: Path, mind: Mind) -> None:
    """Cursor Keep/Undo: undoing one file doesn't touch the other."""
    server, config, log = _setup(tmp_path, mind)
    one = Path(config.workspace) / "bir.txt"
    two = Path(config.workspace) / "iki.txt"
    try:
        _write_ledger(config, one, "A", "A2")
        _write_ledger(config, two, "B", "B2")
        records = _get(server, "/api/degisiklikler")["kayitlar"]
        # Newest first: two=sira2, one=sira1
        seq_one = next(k["sira"] for k in records if k["ad"] == "bir.txt")
        assert _post(server, "/api/degisiklikler/geri", {"sira": seq_one})["ok"] is True
        assert one.read_text(encoding="utf-8") == "A"
        assert two.read_text(encoding="utf-8") == "B2"
        assert _post(server, "/api/degisiklikler/geri",
                     {"dosya": str(two)})["ok"] is True
        assert two.read_text(encoding="utf-8") == "B"
    finally:
        server.stop()
        log.close()


# -- budget brake -------------------------------------------------------


class FakePricedBridge:
    """The smallest imitation that isolates the Bridge's budget arithmetic.

    The real Bridge wants an asyncio loop, a hub and an agent; what is
    tested here is only the **decision**: looking at the counter we have
    and the price we have, saying "stop" or not.
    """

    from dornick.desktop import Bridge

    budget = Bridge.budget
    _spent = Bridge._spent
    _budget_brake = Bridge._budget_brake

    def __init__(self, input_tokens: int, output_tokens: int, pricing: dict | None) -> None:
        self._session_usage = {"girdi": input_tokens, "cikti": output_tokens, "cagri": 1}
        self._price = pricing
        self._budget_usd = None
        self._budget_reported = False


def test_the_brake_stays_silent_without_a_cap() -> None:
    bridge = FakePricedBridge(1_000_000, 0, {"girdi": 1e-5, "cikti": 3e-5})
    assert bridge._budget_brake() == ""


def test_the_brake_speaks_once_the_session_passes_the_cap() -> None:
    # 1M input × $10/M = $10 spent; cap $5.
    bridge = FakePricedBridge(1_000_000, 0, {"girdi": 1e-5, "cikti": 3e-5})
    bridge.budget(5)
    message = bridge._budget_brake()
    assert "Bütçe sınırına ulaşıldı ($5.00)" in message
    assert "sınırı yükselt" in message
    # The same line is not printed over and over.
    assert bridge._budget_brake() == ""
    # Once the cap is raised the brake lifts: the work must be able to go on.
    bridge.budget(50)
    assert bridge._budget_brake() == ""


def test_the_brake_will_not_stop_work_on_a_made_up_price() -> None:
    """If the price is unknown (local server, model outside the catalogue),
    stopping the user's work over a made-up dollar figure would be worse
    than never setting the cap."""
    bridge = FakePricedBridge(10_000_000, 10_000_000, None)
    bridge.budget(1)
    assert bridge._budget_brake() == ""


def test_an_empty_or_zero_cap_means_no_cap() -> None:
    bridge = FakePricedBridge(1_000_000, 0, {"girdi": 1e-5, "cikti": 3e-5})
    assert bridge.budget("")["butce"] is None
    assert bridge.budget(0)["butce"] is None
    assert bridge.budget(-3)["butce"] is None
    assert bridge.budget("abc")["ok"] is False
    assert bridge.budget("2.5")["butce"] == 2.5


# -- does the brake really stop the turn --------------------------------


def test_the_turn_stops_when_the_brake_speaks(tmp_path: Path) -> None:
    """Fake usage: once the cap is exceeded the model is not called EVEN ONCE
    and the user message stays in the history — no half-done work is lost."""
    from tests.test_loop import FakeClient, build_agent, text_turn
    from dornick.tools import ToolRegistry

    client = FakeClient(text_turn("koşmamalıydım"))
    agent = build_agent(tmp_path, client, ToolRegistry())
    notes: list[str] = []
    agent.io.on_notice = notes.append
    agent.io.butce_freni = lambda: "Bütçe sınırına ulaşıldı ($5.00) — devam etmek için sınırı yükselt."

    stats = asyncio.run(agent.run("bir şey yap"))

    assert client.seen_messages == []          # the model was never called
    assert stats.interrupted is True
    assert notes and "Bütçe sınırına ulaşıldı" in notes[0]
    # The message is in the history: once the cap is raised the conversation
    # continues from where it left off.
    texts = json.dumps(agent.session.messages(), ensure_ascii=False)
    assert "bir şey yap" in texts


def test_the_turn_runs_normally_when_there_is_no_cap(tmp_path: Path) -> None:
    from tests.test_loop import FakeClient, build_agent, text_turn
    from dornick.tools import ToolRegistry

    client = FakeClient(text_turn("tamamdır"))
    agent = build_agent(tmp_path, client, ToolRegistry())

    stats = asyncio.run(agent.run("bir şey yap"))

    assert len(client.seen_messages) == 1
    assert stats.interrupted is False
