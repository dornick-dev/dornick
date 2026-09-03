"""Mind interface tests.

The server runs in its own thread and does not touch the agent's asyncio
loop; the only bridge between them is the event log's subscription hook.
The tests here hold the correctness of that bridge and of the graph model.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from dornick.events import EventLog
from dornick.mind import Mind, open_mind
from dornick.web import MindServer, build_graph
from dornick.web.server import Hub, _payload, _summarize


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


# -- graph model -------------------------------------------------------


def test_empty_mind_is_just_the_self_node(mind: Mind) -> None:
    graph = build_graph(mind)
    assert [n["id"] for n in graph["nodes"]] == ["self"]
    assert graph["edges"] == []


def test_graph_is_two_levels_deep(mind: Mind) -> None:
    """Wiring hundreds of memories straight to the centre produces a tangle, not a star."""
    mind.remember("Fatih SCADA tarafında çalışıyor.", kind="user")
    mind.remember("Türkçe konuşuyor.", kind="preference")

    graph = build_graph(mind)
    ids = {n["id"] for n in graph["nodes"]}
    edges = {(e["source"], e["target"]) for e in graph["edges"]}

    assert "hub:user" in ids and "hub:preference" in ids
    assert ("self", "hub:user") in edges
    # A leaf must not attach directly to the centre.
    assert not any(s == "self" and not t.startswith("hub:") for s, t in edges)


def test_hubs_appear_only_when_they_have_content(mind: Mind) -> None:
    mind.remember("bir ders", kind="lesson")
    groups = {n["id"] for n in build_graph(mind)["nodes"] if n.get("hub")}
    assert groups == {"hub:lesson"}


def test_nodes_carry_full_detail_but_short_labels(mind: Mind) -> None:
    long_text = "çok uzun bir hatıra metni " * 10
    mind.remember(long_text, kind="fact", title="kısa başlık")

    leaf = next(n for n in build_graph(mind)["nodes"] if n["group"] == "fact" and not n.get("hub"))
    assert leaf["label"] == "kısa başlık"
    assert leaf["detail"] == long_text.strip()


def test_goals_and_sessions_become_nodes(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    log = EventLog(sessions / "20260101T000000Z.jsonl")
    log.message("user", [{"type": "text", "text": "postgres yedeği al"}])
    log.close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    mind.push_goal("arayüzü bitir")

    groups = {n["group"] for n in build_graph(mind)["nodes"]}
    assert {"goal", "session"} <= groups


def test_stats_reflect_the_mind(mind: Mind) -> None:
    mind.remember("a", kind="fact")
    mind.remember("b", kind="user")
    mind.push_goal("hedef")

    stats = build_graph(mind)["stats"]
    assert stats["memories"] == 2
    assert stats["goals"] == 1


# -- event broadcast ---------------------------------------------------


def test_only_interesting_notes_are_streamed() -> None:
    log = EventLog(Path("/dev/null")) if False else None  # for the type hint
    assert _payload(_note("tool_start", tool="shell")) is not None
    # A session start does nothing but clutter the UI.
    assert _payload(_note("session_start")) is None


def test_tool_result_turns_are_not_shown_as_user_messages() -> None:
    """A tool result is technically a user turn; it must not look like one in the chat."""
    from dornick.events import Event, utcnow

    event = Event(
        seq=0,
        ts=utcnow(),
        kind="message",
        role="user",
        content=[{"type": "tool_result", "tool_use_id": "t1", "content": "çıktı"}],
        meta={"tool_results": True},
    )
    assert _payload(event) is None


def test_message_payload_summarizes_blocks() -> None:
    assert "→ shell" in _summarize(
        [{"type": "tool_use", "name": "shell", "input": {}}]
    )
    assert _summarize([{"type": "text", "text": "merhaba"}]) == "merhaba"


def test_hub_fans_out_to_every_client() -> None:
    hub = Hub()
    a, b = hub.register(), hub.register()
    hub.publish(_note("tool_start", tool="shell"))

    assert json.loads(a.get_nowait())["tool"] == "shell"
    assert json.loads(b.get_nowait())["tool"] == "shell"


def test_unregistered_client_stops_receiving() -> None:
    hub = Hub()
    channel = hub.register()
    hub.unregister(channel)
    hub.publish(_note("tool_start", tool="shell"))
    assert channel.empty()


def test_shared_hub_receives_log_events(tmp_path: Path, mind: Mind) -> None:
    """An injected hub must subscribe to the log as well.

    When the server built its own hub and swapped it later, the
    subscription stayed on the old hub: the assistant text arrived, the
    user message and the tool events silently vanished. No error at all.
    """
    hub = Hub()
    channel = hub.register()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, hub=hub)

    try:
        assert server.hub is hub
        log.note("tool_start", tool="shell")
        assert json.loads(channel.get_nowait())["tool"] == "shell"
    finally:
        server.stop()
        log.close()


def test_listener_failure_does_not_break_the_log(tmp_path: Path) -> None:
    """If the UI crashes the agent must keep working."""
    log = EventLog(tmp_path / "s.jsonl")
    log.subscribe(lambda _: (_ for _ in ()).throw(RuntimeError("arayüz öldü")))

    log.note("tool_start", tool="shell")
    assert len(log) == 1
    log.close()


def test_unsubscribe_detaches(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "s.jsonl")
    seen: list[str] = []
    off = log.subscribe(lambda e: seen.append(str(e.content)))

    log.note("tool_start")
    off()
    log.note("tool_end")

    assert seen == ["tool_start"]
    log.close()


# -- end to end --------------------------------------------------------


def test_server_serves_page_and_graph(tmp_path: Path, mind: Mind) -> None:
    mind.remember("Fatih SCADA tarafında.", kind="user")
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()

    def fetch(path: str) -> str:
        with urllib.request.urlopen(server.url + path, timeout=5) as response:
            return response.read().decode("utf-8")

    try:
        page = fetch("")
        assert "dornick" in page
        # If the page references assets those assets must be served too;
        # with one missing the UI silently opens empty.
        for asset in ("app.css", "app.js", "scene.js"):
            assert asset in page
            assert fetch(asset)

        assert "/api/events" in fetch("app.js")

        graph = json.loads(fetch("api/graph"))
        assert any(n["group"] == "user" for n in graph["nodes"])
    finally:
        server.stop()
        log.close()


def test_install_language_is_served_from_setup_json(tmp_path: Path, mind: Mind) -> None:
    """The setup wizard's language choice is read from /api/dil.

    localStorage cannot be written from the installer; the wizard drops
    setup.json into the workspace and dil.js reads it from here on first
    launch. The kurulum.json left by older versions is recognised too — an
    update must not lose the language choice. Without the file it falls
    back to the MACHINE's language (default English, Turkish on a Turkish
    machine — 02.09).
    """
    from dornick.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()

    def fetch() -> dict:
        with urllib.request.urlopen(server.url + "api/dil", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        # No wizard file: the machine language (whatever it is on this
        # machine) must come back — NOT empty, because the UI needs a default.
        assert fetch()["dil"] in ("tr", "en")
        # The old name on its own: backwards compatibility (existing installs).
        (tmp_path / "kurulum.json").write_text('{"dil": "en"}', encoding="utf-8")
        assert fetch() == {"dil": "en"}
        # The new name takes precedence.
        (tmp_path / "setup.json").write_text('{"dil": "tr"}', encoding="utf-8")
        assert fetch() == {"dil": "tr"}
        # A broken new file must not bring the server down; falls back to the old name.
        (tmp_path / "setup.json").write_text("{bozuk", encoding="utf-8")
        assert fetch() == {"dil": "en"}
        # A broken file on its own: silently back to the machine language.
        (tmp_path / "kurulum.json").unlink()
        assert fetch()["dil"] in ("tr", "en")
    finally:
        server.stop()
        log.close()


def test_unlisted_paths_are_not_served(tmp_path: Path, mind: Mind) -> None:
    """Deriving the path from the request is the classic road to a directory-traversal hole."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        for path in ("../server.py", "app.py", "static/app.js"):
            with pytest.raises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(server.url + path, timeout=5)
            assert caught.value.code == 404
    finally:
        server.stop()
        log.close()


def test_server_binds_loopback_only(tmp_path: Path, mind: Mind) -> None:
    """The agent's memory lives here; not a surface to expose outward."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    try:
        assert server.url.startswith("http://127.0.0.1:")
    finally:
        server.stop()
        log.close()


def _note(kind: str, **meta: object):
    from dornick.events import Event, utcnow

    return Event(seq=0, ts=utcnow(), kind="meta", content=kind, meta=meta)


def test_event_stream_is_framed_so_it_is_not_buffered(tmp_path: Path, mind: Mind) -> None:
    """In HTTP/1.1 the end of the body is determined by Content-Length,
    chunked, or the connection closing. Since the length is unknown, saying
    "keep-alive" left the body unframed: the browser buffered the stream and
    the reply arrived in bulk.
    """
    import http.client

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    host, port = server.url.split("//")[1].rstrip("/").split(":")

    try:
        conn = http.client.HTTPConnection(host, int(port), timeout=5)
        conn.request("GET", "/api/events")
        response = conn.getresponse()

        assert response.getheader("Content-Type").startswith("text/event-stream")
        assert response.getheader("Connection") == "close"
        assert response.getheader("Content-Length") is None

        # When an event is published it must be readable at once.
        log.note("tool_start", tool="shell")
        assert b"tool_start" in response.readline() + response.readline()
        conn.close()
    finally:
        server.stop()
        log.close()


def test_a_raw_body_is_not_consumed_twice(tmp_path: Path, mind: Mind) -> None:
    """The body is read once.

    Parsing it as JSON first and then trying to read the raw form again
    left requests hanging forever: the audio request's body is raw audio,
    not JSON, and the second read waits for bytes that will never come.
    Once that request held a thread the browser's connection quota filled
    and the microphone, settings, chat — everything locked up.
    """
    import http.client

    from dornick.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    host, port = server.url.split("//")[1].rstrip("/").split(":")

    try:
        conn = http.client.HTTPConnection(host, int(port), timeout=8)
        # A non-JSON body: the same thing the audio request carries.
        conn.request("POST", "/api/hear", body=b"\x1aE\xdf\xa3 ham ses",
                     headers={"Content-Type": "audio/webm"})
        # If it hangs the timeout blows here; which status code comes back
        # does not matter, that it **comes back** does.
        assert conn.getresponse().status in (409, 400, 501, 503)
        conn.close()

        # The server is still up: a stuck request used to bring the others down too.
        conn = http.client.HTTPConnection(host, int(port), timeout=8)
        conn.request("GET", "/api/graph")
        assert conn.getresponse().status == 200
        conn.close()
    finally:
        server.stop()
        log.close()


def test_turkish_error_messages_do_not_kill_the_connection(
    tmp_path: Path, mind: Mind
) -> None:
    """The HTTP status line must be latin-1.

    Sending "Sesli komut kapalı" made the stdlib raise UnicodeEncodeError,
    the handler died and the connection closed **without a reply**. On the
    client side this looks like "nothing happens" — not even an error
    message arrives.
    """
    import http.client

    from dornick.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    host, port = server.url.split("//")[1].rstrip("/").split(":")

    try:
        conn = http.client.HTTPConnection(host, int(port), timeout=8)
        # Voice command off: a Turkish error message must come back.
        conn.request("POST", "/api/hear", body=b"ham ses",
                     headers={"Content-Type": "audio/webm"})
        answer = conn.getresponse()

        assert answer.status == 409
        # The real text is in the body: it does not fit on the status line.
        assert "kapalı" in answer.read().decode("utf-8", "replace")
        conn.close()

        # The server stayed up: a crashing handler used to drop the connection.
        conn = http.client.HTTPConnection(host, int(port), timeout=8)
        conn.request("GET", "/api/graph")
        assert conn.getresponse().status == 200
        conn.close()
    finally:
        server.stop()
        log.close()


def test_the_body_is_served_even_before_anything_is_open(tmp_path: Path, mind: Mind) -> None:
    """The scene organs read from here. If the endpoint does not answer, no
    device shows on screen — the agent stands bodiless."""
    from dornick.config import Config

    log = EventLog(tmp_path / "s.jsonl")
    config = Config.load(tmp_path)
    config.ensure_dirs()
    server = MindServer(mind, log, port=0, config=config)
    server.start()

    try:
        with urllib.request.urlopen(server.url + "api/organs", timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        server.stop()
        log.close()

    ids = {organ["id"] for organ in body["organs"]}
    assert {"mic", "lens", "voice"} <= ids


def test_the_body_survives_a_server_without_settings(tmp_path: Path, mind: Mind) -> None:
    """In a preview running without settings the page must still open: a
    missing structure is an empty list, not an error."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()

    try:
        with urllib.request.urlopen(server.url + "api/organs", timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        server.stop()
        log.close()

    assert body == {"organs": []}


# -- version visibility ------------------------------------------------


def test_bridge_snapshot_carries_the_version() -> None:
    """/api/state's "surum" field: the brand hint in the top bar comes from here.

    The version must be visible even when the agent never started — in the
    field, "which copy is open?" is asked exactly on broken launches.
    """
    import asyncio

    from dornick import environment
    from dornick.desktop import Bridge

    loop = asyncio.new_event_loop()
    try:
        status = Bridge(Hub(), loop).snapshot()
        assert status["surum"] == environment.version()
        assert isinstance(status["kurulu"], bool)
    finally:
        loop.close()


def test_the_version_check_endpoint_works_without_network(
    tmp_path: Path, mind: Mind, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/surum checks on the server side; the test never goes to the network."""
    from dornick.web import server as server_module

    monkeypatch.setattr(
        server_module.environment, "check_update",
        lambda: {"ok": True, "mevcut": "0.2.2", "yeni": "0.3.0",
                 "url": "https://ornek/yayin", "hata": ""})

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        request = urllib.request.Request(
            server.url + "api/surum", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        assert data["yeni"] == "0.3.0" and data["url"] == "https://ornek/yayin"
    finally:
        server.stop()
        log.close()


# -- raw file endpoint (/api/raw) --------------------------------------
#
# `/api/files` returns text: a PNG came from there only as a "binary file"
# and the viewer could not show the image. This endpoint gives the raw
# bytes — but through the same gate: the path is verified, the type is
# given by extension and from a short list.

# 1x1 transparent PNG (real bytes, not fake): so type and length can be tested.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def test_raw_serves_real_bytes_with_a_declared_type(tmp_path: Path, mind: Mind) -> None:
    """Whether the viewer can REALLY open an image depends on this."""
    from dornick.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    (tmp_path / "kare.png").write_bytes(TINY_PNG)

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    try:
        with urllib.request.urlopen(server.url + "api/raw?path=kare.png", timeout=5) as response:
            body = response.read()
            assert response.headers["Content-Type"] == "image/png"
            # The browser must not look at the content and invent its own type.
            assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert body == TINY_PNG
    finally:
        server.stop()
        log.close()


def test_raw_refuses_to_leave_the_workspace(tmp_path: Path, mind: Mind) -> None:
    """Deriving the path from the request is the classic road to a
    directory-traversal hole: a request climbing up with `..` must NOT get the file."""
    from dornick.config import Config

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (tmp_path / "sir.txt").write_text("gizli", encoding="utf-8")

    config = Config.load(workspace)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(server.url + "api/raw?path=../sir.txt", timeout=5)
        assert caught.value.code == 403
        # A missing file is 404: "absent" and "forbidden" are separate answers.
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(server.url + "api/raw?path=yok.png", timeout=5)
        assert missing.value.code == 404
    finally:
        server.stop()
        log.close()


def test_raw_never_serves_a_workspace_file_as_html(tmp_path: Path, mind: Mind) -> None:
    """Serving a page the agent wrote as html on the MAIN origin would expose
    the program's DOM and the `/api` endpoints to that page. An unknown
    type is downloaded, not interpreted."""
    from dornick.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    (tmp_path / "sayfa.html").write_text("<script>alert(1)</script>", encoding="utf-8")

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    try:
        with urllib.request.urlopen(server.url + "api/raw?path=sayfa.html", timeout=5) as response:
            assert response.headers["Content-Type"] == "application/octet-stream"
    finally:
        server.stop()
        log.close()


def test_raw_supports_ranges_so_media_can_seek(tmp_path: Path, mind: Mind) -> None:
    """Audio/video players ask for a range in order to seek."""
    import http.client

    from dornick.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    (tmp_path / "ses.mp3").write_bytes(bytes(range(256)))

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    try:
        host, port = server.url.split("//")[1].rstrip("/").split(":")
        conn = http.client.HTTPConnection(host, int(port), timeout=5)
        conn.request("GET", "/api/raw?path=ses.mp3", headers={"Range": "bytes=10-19"})
        response = conn.getresponse()
        body = response.read()
        assert response.status == 206
        assert response.getheader("Content-Range") == "bytes 10-19/256"
        assert body == bytes(range(10, 20))
        conn.close()
    finally:
        server.stop()
        log.close()


# -- session identity and transcript search (endpoints) ----------------


def _write_session(sessions_dir: Path, sid: str, turns: list[tuple[str, str]]) -> None:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"kind": "note", "name": "session_start"})]
    for role, text in turns:
        lines.append(json.dumps({
            "kind": "message", "role": role,
            "content": [{"type": "text", "text": text}],
        }, ensure_ascii=False))
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_naming_a_session_reaches_the_listing(tmp_path: Path, mind: Mind) -> None:
    """A named conversation must show in the list under that name; unnamed,
    the title is still derived from the conversation's first utterance."""
    _write_session(mind.sessions_dir, "20260101T000000Z",
                   [("user", "Kayseri OSB için SCADA teklifi hazırla")])

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        def listing() -> dict:
            with urllib.request.urlopen(server.url + "api/sessions", timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))

        first = listing()["sessions"][0]
        assert not first["named"] and "SCADA" in first["title"]

        request = urllib.request.Request(
            server.url + "api/session/meta",
            data=json.dumps({"id": "20260101T000000Z", "ad": "Kayseri teklifi",
                             "etiketler": ["scada", "teklif"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            assert json.loads(response.read().decode("utf-8"))["ok"] is True

        data = listing()
        row = data["sessions"][0]
        assert row["title"] == "Kayseri teklifi" and row["named"]
        assert row["tags"] == ["scada", "teklif"]
        # The panel's filter list: the existing tags.
        assert data["tags"] == ["scada", "teklif"]
    finally:
        server.stop()
        log.close()


def test_the_meta_endpoint_refuses_a_path_shaped_id(tmp_path: Path, mind: Mind) -> None:
    """The id turns into a file name: a request climbing up with `..` must
    not be able to write outside the directory."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        request = urllib.request.Request(
            server.url + "api/session/meta",
            data=json.dumps({"id": "../gizli", "ad": "x"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        assert data["ok"] is False
    finally:
        server.stop()
        log.close()


def test_archiving_a_session_drops_it_from_the_listing(
        tmp_path: Path, mind: Mind) -> None:
    """Right-click Archive: the log moves to .arsiv, the list no longer sees
    it. The id turns into a file name — no escaping with `..`."""
    _write_session(mind.sessions_dir, "20260101T000000Z",
                   [("user", "pompa bakımı"), ("assistant", "tamam")])

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        request = urllib.request.Request(
            server.url + "api/session/archive",
            data=json.dumps({"id": "20260101T000000Z"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            assert json.loads(response.read().decode("utf-8"))["ok"] is True

        with urllib.request.urlopen(server.url + "api/sessions", timeout=5) as response:
            ids = [s["id"] for s in json.loads(response.read().decode("utf-8"))["sessions"]]
        assert "20260101T000000Z" not in ids
        assert (mind.sessions_dir / ".arsiv" / "20260101T000000Z.jsonl").is_file()

        bad = urllib.request.Request(
            server.url + "api/session/archive",
            data=json.dumps({"id": "../gizli"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(bad, timeout=5) as response:
            assert json.loads(response.read().decode("utf-8"))["ok"] is False
    finally:
        server.stop()
        log.close()


def test_the_listing_searches_inside_transcripts(tmp_path: Path, mind: Mind) -> None:
    """Search used to filter only the title; if the word occurred in the
    middle of the conversation the list could not find it."""
    _write_session(mind.sessions_dir, "20260101T000000Z",
                   [("user", "selam"), ("assistant", "Modbus kayıtlarını okudum.")])
    _write_session(mind.sessions_dir, "20260102T000000Z", [("user", "hava nasıl")])

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        with urllib.request.urlopen(server.url + "api/sessions?ara=modbus", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        assert data["searched"] is True
        matched = {s["id"]: s["hits"] for s in data["sessions"] if s["hits"]}
        assert set(matched) == {"20260101T000000Z"}
        assert "Modbus" in matched["20260101T000000Z"][0]["text"]

        # A request without a search behaves as before: the hits field is empty, the list is full.
        with urllib.request.urlopen(server.url + "api/sessions", timeout=5) as response:
            plain = json.loads(response.read().decode("utf-8"))
        assert plain["searched"] is False
        assert all(not s["hits"] for s in plain["sessions"])
        assert len(plain["sessions"]) == 2
    finally:
        server.stop()
        log.close()


# -- folder explorer (project selection) -------------------------------
#
# `/api/files` stays inside the workspace; the project is exactly a place
# OUTSIDE it and a native folder dialog cannot be used.


def test_the_browser_lists_folders_anywhere_but_only_folders(
    tmp_path: Path, mind: Mind
) -> None:
    root = tmp_path / "kod"
    (root / "proje" / "src").mkdir(parents=True)
    (root / ".gizli").mkdir()
    (root / "not.txt").write_text("x", encoding="utf-8")

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        address = server.url + "api/gozat?yol=" + urllib.parse.quote(str(root))
        with urllib.request.urlopen(address, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        names = [k["ad"] for k in data["klasorler"]]
        assert names == ["proje"]          # folders only, hidden ones weeded out
        assert data["dosya"] == 1          # files only as a COUNT
        assert data["ust"] == str(tmp_path)
        assert data["engel"] == ""         # selectable
        # File names or contents never come back.
        assert "not.txt" not in json.dumps(data)
    finally:
        server.stop()
        log.close()


def test_the_browser_says_when_a_folder_cannot_be_a_project(
    tmp_path: Path, mind: Mind
) -> None:
    """The user must see it BEFORE SAVING: the block is written on the selection screen."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        root = Path(tmp_path.anchor or "/")
        address = server.url + "api/gozat?yol=" + urllib.parse.quote(str(root))
        with urllib.request.urlopen(address, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        assert data["engel"]

        # A missing folder: an error, not a crash.
        missing = server.url + "api/gozat?yol=" + urllib.parse.quote(str(tmp_path / "yok"))
        with urllib.request.urlopen(missing, timeout=5) as response:
            assert json.loads(response.read().decode("utf-8"))["hata"]

        # A request without a path: the starting places (drives / home).
        with urllib.request.urlopen(server.url + "api/gozat", timeout=5) as response:
            start = json.loads(response.read().decode("utf-8"))
        assert start["klasorler"] and start["ust"] is None
    finally:
        server.stop()
        log.close()


def test_the_settings_snapshot_carries_the_project_state(
    tmp_path: Path, mind: Mind
) -> None:
    """The settings page must be able to draw the project: the chosen path,
    the resolved root, recent projects and (if any) the reason."""
    from dornick import settings as settings_module
    from dornick.config import Config

    project = tmp_path / "musteri"
    project.mkdir()
    config = Config.load(tmp_path)
    config.ensure_dirs()
    updated = settings_module.apply(config, {"sandbox": {"project": str(project)}})

    box = settings_module.snapshot(updated)["sandbox"]
    assert box["project"] == str(project)
    assert box["project_root"] == str(project.resolve())
    assert box["project_error"] == ""
    assert str(project) in box["recent"]


# -- opening outside and artifact download (31.08 live wounds) ----------


def _post_json(server: MindServer, path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        server.url.rstrip("/") + path, data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


# -- cross-origin protection (security audit, 01.09) -------------------
#
# If a foreign page in ANOTHER browser tab of the user's fires a
# state-changing POST at 127.0.0.1 (drive-by CSRF) it is rejected. Our own
# UI (same origin) and local callers that send no Origin (curl, test,
# benchmark) pass — telling them apart at the HTTP layer is impossible, and
# that road is already guarded by the shell permission gate.


def _post_raw(server: MindServer, path: str, headers: dict) -> int:
    """Raw POST; returns the HTTP status code (403 included)."""
    data = b"{}"
    h = {"Content-Type": "application/json", **headers}
    request = urllib.request.Request(
        server.url.rstrip("/") + path, data=data, headers=h)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_the_update_endpoint_downloads_reports_progress_and_launches(
    tmp_path: Path, mind: Mind, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In-app update end to end: /api/guncelle detects the version,
    downloads it (progress flows over SSE) and launches the setup wizard.

    No .exe is really run — `start_update` is mocked; the address comes
    from the server's own check as well (the client does not supply it)."""
    import threading

    from dornick.web import server as server_module

    monkeypatch.setattr(
        server_module.environment, "check_update",
        lambda: {"ok": True, "mevcut": "1.0.0", "yeni": "9.9.9",
                 "url": "https://github.com/dornick-dev/dornick/releases/tag/v9.9.9",
                 "indirme": "https://github.com/dornick-dev/dornick/releases/download/v9.9.9/dornick-setup-9.9.9.exe",
                 "boyut": 2 * 1024 * 1024, "ad": "dornick-setup-9.9.9.exe",
                 "hata": ""})

    downloaded = tmp_path / "dornick-setup-9.9.9.exe"

    def fake_download(url, folder, *, expected_size=0, name="", progress=None):
        assert "github.com" in url          # address from the server, trusted
        if progress:
            progress(expected_size // 2, expected_size)
            progress(expected_size, expected_size)
        downloaded.write_bytes(b"MZ" + b"0" * 1024)
        return downloaded

    monkeypatch.setattr(server_module.environment, "download_update", fake_download)

    launched: dict = {}
    finished = threading.Event()

    def fake_launch(path):
        launched["path"] = str(path)
        finished.set()

    monkeypatch.setattr(server_module.environment, "start_update", fake_launch)

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    channel = server.hub.register()   # SSE listener: progress events
    server.start()
    try:
        response = _post_json(server, "/api/guncelle", {})
        assert response["ok"] is True and response["yeni"] == "9.9.9"
        assert finished.wait(5), "download/launch thread did not finish in time"
        assert launched["path"].endswith("dornick-setup-9.9.9.exe")

        # SSE events: at least one "indiriliyor" percentage and one install stage.
        events = []
        import queue as _q
        try:
            while True:
                events.append(json.loads(channel.get_nowait()))
        except _q.Empty:
            pass
        stages = [o.get("asama") for o in events if o.get("type") == "guncelleme"]
        assert "indiriliyor" in stages
        assert "kuruluyor" in stages and "acildi" in stages
    finally:
        server.stop()
        log.close()


def test_the_update_endpoint_politely_refuses_without_a_new_version(
    tmp_path: Path, mind: Mind, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no update to download /api/guncelle returns ok:false; download
    or launch is NEVER attempted."""
    from dornick.web import server as server_module

    monkeypatch.setattr(
        server_module.environment, "check_update",
        lambda: {"ok": True, "mevcut": "1.0.0", "yeni": "", "url": "",
                 "indirme": "", "boyut": 0, "ad": "", "hata": ""})

    def boom(*a, **k):  # if called the test breaks
        raise AssertionError("güncelleme yokken indirme denenmemeli")

    monkeypatch.setattr(server_module.environment, "download_update", boom)

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        response = _post_json(server, "/api/guncelle", {})
        assert response["ok"] is False
    finally:
        server.stop()
        log.close()


def test_create_folder_creates_and_refuses_bad_targets(
    tmp_path: Path, mind: Mind
) -> None:
    """"New folder" on the chat screen: the named folder is opened; a name
    containing a path and dangerous roots are refused (user request, 02.09)."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        parent = tmp_path / "projeler"
        parent.mkdir()
        c = _post_json(server, "/api/klasor/olustur",
                       {"ust": str(parent), "ad": "yeni-is"})
        assert c["ok"] is True
        assert (parent / "yeni-is").is_dir()
        assert c["yol"].endswith("yeni-is")

        # The name cannot contain a path: an attempt to escape to the parent directory.
        bad = _post_json(server, "/api/klasor/olustur",
                         {"ust": str(parent), "ad": "../disari"})
        assert bad["ok"] is False
        assert not (tmp_path / "disari").exists()

        # Missing field.
        assert _post_json(server, "/api/klasor/olustur", {"ust": str(parent)})["ok"] is False
    finally:
        server.stop()
        log.close()


def test_the_language_endpoint_falls_back_to_the_machine_language(
    tmp_path: Path, mind: Mind, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the wizard left no language the machine's language is consulted:
    "tr" on a Turkish machine, "en" everywhere else (default English — user request)."""
    from dornick.web import server as server_module

    monkeypatch.setattr(server_module, "_machine_language", lambda: "en")
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        with urllib.request.urlopen(server.url + "api/dil", timeout=5) as response:
            assert json.loads(response.read().decode("utf-8"))["dil"] == "en"
    finally:
        server.stop()
        log.close()


def test_machine_language_is_tr_on_a_turkish_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turkish on the tr_TR locale, English on any other locale."""
    import locale

    from dornick.web import server as server_module

    monkeypatch.setattr(locale, "getdefaultlocale", lambda: ("tr_TR", "cp1254"))
    assert server_module._machine_language() == "tr"
    monkeypatch.setattr(locale, "getdefaultlocale", lambda: ("en_US", "utf-8"))
    assert server_module._machine_language() == "en"
    # Unreadable → English.
    def boom():
        raise ValueError("yok")
    monkeypatch.setattr(locale, "getdefaultlocale", boom)
    monkeypatch.setattr(locale, "getlocale", boom)
    assert server_module._machine_language() == "en"


def test_foreign_origin_post_is_rejected(tmp_path: Path, mind: Mind) -> None:
    """Foreign origin → 403; same origin and origin-less request → pass."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        ours = server.url.rstrip("/")   # http://127.0.0.1:PORT
        # Foreign origin: must be rejected.
        assert _post_raw(server, "/api/surum",
                         {"Origin": "https://evil.example"}) == 403
        # Same origin (the UI itself): must pass.
        assert _post_raw(server, "/api/surum", {"Origin": ours}) == 200
        # No origin at all (curl/test/benchmark): must pass.
        assert _post_raw(server, "/api/surum", {}) == 200
        # Rejected even when only the Referer is foreign.
        assert _post_raw(server, "/api/surum",
                         {"Referer": "https://evil.example/x"}) == 403
    finally:
        server.stop()
        log.close()


def test_open_outside_opens_only_local_pages(
    tmp_path: Path, mind: Mind, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only THIS server's page goes to the real browser — with the real port.

    The agent stated the artifact address with the default 8765; the server
    was running on a shifted port and the user saw "connection refused".
    The address is built from where the server itself bound, not from the
    request; an outside address is never opened from this endpoint.
    """
    import webbrowser

    from dornick.config import Config

    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)

    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    try:
        assert _post_json(server, "/api/disari-ac", {"path": "https://kotu.example/"})["ok"] is False
        assert _post_json(server, "/api/disari-ac", {"path": "//kotu.example/x"})["ok"] is False
        assert opened == []

        out = _post_json(server, "/api/disari-ac", {"path": "/artifact/x-1a2b/"})
        assert out["ok"] is True
        assert opened == [out["url"]]
        assert out["url"].startswith("http://127.0.0.1:")
        assert out["url"].endswith("/artifact/x-1a2b/")
        # The real port: whatever port the server bound to.
        assert out["url"] == server.url.rstrip("/") + "/artifact/x-1a2b/"
    finally:
        server.stop()
        log.close()


def test_artifact_download_saves_to_downloads_with_full_path(
    tmp_path: Path, mind: Mind, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The download is written to disk BY THE SERVER and the full path is returned.

    In the WebView2 window blob + <a download> died silently; the user lived
    "I can't download, I can't see the file path". An existing file is not
    overwritten — a counter-suffixed name is opened.
    """
    import pathlib

    from dornick import artifacts
    from dornick.config import Config

    home = tmp_path / "ev"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))

    config = Config.load(tmp_path)
    config.ensure_dirs()
    meta = artifacts.publish(
        config.state_dir, "Küçük Rapor",
        "<!doctype html><meta charset='utf-8'><h1>rapor</h1>",
    )
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    try:
        address = f"/artifact/{meta['id']}/"
        first = _post_json(server, "/api/artifact/indir", {"path": address})
        assert first["ok"] is True
        path = Path(first["path"])
        assert path.is_file() and path.parent == home / "Downloads"
        assert "rapor" in path.read_text(encoding="utf-8")

        # A second download does not crush the first.
        second = _post_json(server, "/api/artifact/indir", {"path": address})
        assert second["ok"] is True and second["path"] != first["path"]

        # An id escape does not touch the disk.
        escape = _post_json(server, "/api/artifact/indir", {"path": "/artifact/../gizli/"})
        assert escape["ok"] is False
    finally:
        server.stop()
        log.close()
