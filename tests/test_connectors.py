"""MCP connectors.

Most tests here are network-free: configuration parsing, name generation,
the registry bridge. One end-to-end test talks to a real subprocess — a
fake MCP server is started and the full path from handshake to tool call
is walked. That the transport is JSON-per-line can only be kept true this way.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from dornick import connectors
from dornick.tools.base import ToolRegistry, ToolSpec


# -- configuration ------------------------------------------------------


def test_the_claude_code_format_is_accepted() -> None:
    raw = json.dumps({
        "mcpServers": {
            "hesap": {"command": "npx", "args": ["-y", "bir-mcp"], "env": {"A": "1"}},
            "uzak": {"url": "https://ornek.com/mcp",
                     "headers": {"Authorization": "Bearer ${TOKEN}"}},
        }
    })
    found = connectors.parse(raw)

    assert [c.name for c in found] == ["hesap", "uzak"]
    assert found[0].kind == "stdio" and found[0].args == ["-y", "bir-mcp"]
    assert found[1].kind == "http" and found[1].headers["Authorization"].endswith("${TOKEN}")


def test_the_outer_wrapper_may_be_omitted() -> None:
    # The outer shell can be forgotten when copying from another client.
    found = connectors.parse('{"tekil": {"command": "echo"}}')
    assert [c.name for c in found] == ["tekil"]


def test_errors_name_the_field() -> None:
    for raw, hint in (
        ("{bozuk", "JSON"),
        ('{"a b": {"command": "x"}}', "ad"),
        ('{"a": {}}', "command"),
        ('{"a": {"command": "x", "url": "https://y"}}', "ikisi birden"),
        ('{"a": {"url": "ftp://y"}}', "http"),
        ('{"a": {"command": "x", "args": "tek"}}', "args"),
    ):
        with pytest.raises(connectors.ConnectorError) as caught:
            connectors.parse(raw)
        assert hint.lower() in str(caught.value).lower(), raw


def test_a_missing_secret_is_named_not_blanked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing `${NAME}` is not silently left empty: an empty
    Authorization header comes back as an "unauthorized" error with the
    cause invisible."""
    monkeypatch.delenv("HIC_YOK_TOKEN", raising=False)
    with pytest.raises(connectors.ConnectorError) as caught:
        connectors._expand("Bearer ${HIC_YOK_TOKEN}")
    assert "HIC_YOK_TOKEN" in str(caught.value)
    assert "Anahtarlar" in str(caught.value)

    monkeypatch.setenv("HIC_YOK_TOKEN", "gizli")
    assert connectors._expand("Bearer ${HIC_YOK_TOKEN}") == "Bearer gizli"


def test_save_refuses_broken_json(tmp_path: Path) -> None:
    with pytest.raises(connectors.ConnectorError):
        connectors.save(tmp_path, "{bozuk")
    assert not (tmp_path / connectors.FILE).exists()

    connectors.save(tmp_path, '{"mcpServers": {}}')
    assert connectors.read_raw(tmp_path).strip() == '{"mcpServers": {}}'


def test_disabled_servers_are_not_loaded(tmp_path: Path) -> None:
    connectors.save(tmp_path, json.dumps({
        "mcpServers": {
            "acik": {"command": "echo"},
            "kapali": {"command": "echo", "enabled": False},
        }
    }))
    found, problems = connectors.load(tmp_path)
    assert [c.name for c in found] == ["acik"]
    assert problems == []


# -- name generation ----------------------------------------------------


def test_tool_names_follow_the_claude_code_shape() -> None:
    assert connectors.tool_name("hesap", "topla") == "mcp__hesap__topla"
    # Characters outside the API alphabet become underscores; length is capped.
    assert connectors.tool_name("a", "çok uzun" + "x" * 100).startswith("mcp__a__")
    assert len(connectors.tool_name("a", "x" * 200)) <= 64


# -- SSE decoding -------------------------------------------------------


def test_http_bodies_decode_both_ways() -> None:
    plain = connectors._decode_http("application/json", '{"id": 1, "result": {}}')
    assert plain[0]["id"] == 1

    sse = "event: message\ndata: {\"id\": 2, \"result\": {}}\n\n"
    assert connectors._decode_http("text/event-stream", sse)[0]["id"] == 2

    assert connectors._decode_http("application/json", "") == []


# -- registry bridge ----------------------------------------------------


class FakeSession:
    def __init__(self, name: str, tools: list[dict], expose: str = "defer") -> None:
        self.connector = connectors.Connector(name=name, command="echo", expose=expose)
        self.tools = tools
        self.error = ""
        self.ok = True
        self.called: list[tuple[str, dict]] = []

    def call(self, tool: str, arguments: dict) -> tuple[str, bool]:
        self.called.append((tool, arguments))
        return f"{tool}: tamam", False


def test_full_exposure_registers_tools_with_their_source() -> None:
    registry = ToolRegistry()
    pool = connectors.Pool()
    pool.sessions["hesap"] = FakeSession("hesap", [
        {"name": "topla", "description": "toplar",
         "inputSchema": {"type": "object", "properties": {}}},
    ], expose="full")

    added, dropped = connectors.register(registry, pool)
    assert added == ["mcp__hesap__topla"]
    assert dropped == []

    spec = registry.get("mcp__hesap__topla")
    assert spec is not None
    assert spec.source == "mcp:hesap"
    assert spec.mutates is True          # external server: must pass the permission gate
    assert "hesap" in spec.description   # the model should see where it came from


def test_deferred_is_the_default_and_registers_one_bridge() -> None:
    """The measured reason: Notion's 28 schemas were ~27,000 tokens and
    went with every message. The default is now deferral — only the bridge
    enters the registry."""
    import json as js

    registry = ToolRegistry()
    pool = connectors.Pool()
    pool.sessions["notion"] = FakeSession("notion", [
        {"name": f"arac-{i}", "description": "d" * 400,
         "inputSchema": {"type": "object", "properties": {"x": {"type": "string",
                         "description": "y" * 400}}}}
        for i in range(28)
    ])

    added, _ = connectors.register(registry, pool)
    assert added == [connectors.BRIDGE_TOOL]
    assert registry.get("mcp__notion__arac-0") is None

    # The schema going into the prompt must be small: one bridge, not 28 full schemas.
    bridge = registry.get(connectors.BRIDGE_TOOL)
    weight = len(js.dumps(bridge.api_schema(), ensure_ascii=False))
    assert weight < 4_000     # insurance against the ~27,000-token bloat
    assert "notion" in bridge.description
    assert "28 araç" in bridge.description


def test_a_gone_server_takes_its_tools_with_it() -> None:
    registry = ToolRegistry()
    pool = connectors.Pool()
    pool.sessions["hesap"] = FakeSession("hesap", [
        {"name": "topla", "inputSchema": {"type": "object"}},
    ], expose="full")
    connectors.register(registry, pool)

    pool.sessions.clear()
    added, dropped = connectors.register(registry, pool)
    assert added == []
    assert dropped == ["mcp__hesap__topla"]
    assert registry.get("mcp__hesap__topla") is None


def test_the_gone_server_also_takes_the_bridge() -> None:
    registry = ToolRegistry()
    pool = connectors.Pool()
    pool.sessions["notion"] = FakeSession("notion", [
        {"name": "ara", "inputSchema": {"type": "object"}},
    ])
    connectors.register(registry, pool)
    assert registry.get(connectors.BRIDGE_TOOL) is not None

    pool.sessions.clear()
    _, dropped = connectors.register(registry, pool)
    assert connectors.BRIDGE_TOOL in dropped
    assert registry.get(connectors.BRIDGE_TOOL) is None


def test_the_bridge_lists_describes_and_calls() -> None:
    """The bridge's three faces: short list → single schema → call. The
    schema is only paid for when asked."""
    import asyncio

    registry = ToolRegistry()
    pool = connectors.Pool()
    session = FakeSession("notion", [
        {"name": "ara", "description": "Çalışma alanında arar.\nUzun detay...",
         "inputSchema": {"type": "object",
                         "properties": {"query": {"type": "string"}},
                         "required": ["query"]}},
    ])
    pool.sessions["notion"] = session
    connectors.register(registry, pool)
    bridge = registry.get(connectors.BRIDGE_TOOL)

    listed = asyncio.run(bridge.handler({"action": "tools"}, None))
    assert "ara: Çalışma alanında arar." in listed.content
    assert "Uzun detay" not in listed.content          # the list stays short

    shown = asyncio.run(bridge.handler({"action": "describe", "tool": "ara"}, None))
    assert '"query"' in shown.content                   # the full schema lives here

    answer = asyncio.run(bridge.handler(
        {"action": "call", "tool": "ara", "args": {"query": "klor"}}, None))
    assert answer.content == "ara: tamam"
    assert session.called == [("ara", {"query": "klor"})]

    # A wrong tool name gives an instructive error, it does not bring the server down.
    missing = asyncio.run(bridge.handler({"action": "call", "tool": "yok",
                                          "args": {}}, None))
    assert missing.is_error and "tools" in missing.content


def test_builtin_tools_survive_a_reconnect() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="shell", description="yerleşik", input_schema={"type": "object"},
        handler=lambda a, c: None,
    ))
    connectors.register(registry, connectors.Pool())
    assert registry.get("shell") is not None


# -- end to end: a real subprocess -------------------------------------

FAKE_SERVER = r'''
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method, rid = msg.get("method"), msg.get("id")
    if rid is None:
        continue  # notification
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "sahte", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "topla", "description": "iki sayıyı toplar",
                             "inputSchema": {"type": "object", "properties": {
                                 "a": {"type": "number"}, "b": {"type": "number"}}}}]}
    elif method == "tools/call":
        args = msg["params"]["arguments"]
        result = {"content": [{"type": "text", "text": str(args["a"] + args["b"])}]}
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}) + "\n")
    sys.stdout.flush()
'''


def test_a_real_stdio_server_end_to_end(tmp_path: Path) -> None:
    """Handshake → tool list → call, with a real subprocess."""
    script = tmp_path / "sahte_mcp.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")

    session = connectors.Session(connectors.Connector(
        name="sahte", command=sys.executable, args=[str(script)],
    ))
    try:
        session.open()
        assert session.error == ""
        assert [t["name"] for t in session.tools] == ["topla"]

        text, failed = session.call("topla", {"a": 40, "b": 2})
        assert failed is False
        assert text == "42"
    finally:
        session.close()


def test_a_dead_command_reports_instead_of_hanging(tmp_path: Path) -> None:
    session = connectors.Session(connectors.Connector(
        name="yok", command=str(tmp_path / "boyle-bir-komut-yok.exe"),
    ))
    session.open()
    assert session.error != ""
    assert session.ok is False


# -- OAuth --------------------------------------------------------------


def test_pkce_pairs_are_wellformed() -> None:
    import base64
    import hashlib

    verifier, challenge = connectors._pkce()
    assert 43 <= len(verifier) <= 128            # RFC 7636 bounds
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    assert challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    # Every call is a fresh pair: a reused verifier defeats PKCE.
    assert connectors._pkce()[0] != verifier


def test_tokens_roundtrip_and_logout(tmp_path: Path) -> None:
    connectors._tokens_write(tmp_path, {"uzak": {"access_token": "a"}})
    assert connectors._tokens_read(tmp_path)["uzak"]["access_token"] == "a"

    assert connectors.forget_login(tmp_path, "uzak") is True
    assert connectors._tokens_read(tmp_path) == {}
    assert connectors.forget_login(tmp_path, "uzak") is False


def test_bearer_refreshes_a_stale_token(tmp_path: Path) -> None:
    """An expired token is refreshed silently; the user is not asked."""
    import time as clock

    connectors._tokens_write(tmp_path, {"uzak": {
        "access_token": "eski", "refresh_token": "yenileyici",
        "expires_at": clock.time() - 10,
        "token_endpoint": "https://as.ornek/token", "client_id": "cid",
        "resource": "https://mcp.ornek/mcp",
    }})

    asked = {}

    def fake_http(url, **kwargs):
        asked["url"] = url
        asked["form"] = kwargs.get("form")
        return {"access_token": "taze", "expires_in": 3600}

    got = connectors._bearer(tmp_path, "uzak", http=fake_http)
    assert got == "taze"
    assert asked["form"]["grant_type"] == "refresh_token"
    # The refreshed token was also written to disk: the next request should not go to the network.
    assert connectors._tokens_read(tmp_path)["uzak"]["access_token"] == "taze"


def test_bearer_keeps_the_old_token_when_refresh_fails(tmp_path: Path) -> None:
    import time as clock

    connectors._tokens_write(tmp_path, {"uzak": {
        "access_token": "eski", "refresh_token": "r",
        "expires_at": clock.time() - 10,
        "token_endpoint": "https://as.ornek/token", "client_id": "c",
    }})

    def broken(url, **kwargs):
        raise connectors.ConnectorError("ağ yok")

    # Let the server say the 401; the token is not deleted, the user hits 'Giriş yap'.
    assert connectors._bearer(tmp_path, "uzak", http=broken) == "eski"


def test_discovery_walks_resource_then_authorization_server() -> None:
    pages = {
        "https://mcp.ornek/.well-known/oauth-protected-resource":
            {"authorization_servers": ["https://as.ornek"]},
        "https://as.ornek/.well-known/oauth-authorization-server":
            {"authorization_endpoint": "https://as.ornek/yetki",
             "token_endpoint": "https://as.ornek/token"},
    }

    def fake_http(url, **kwargs):
        if url not in pages:
            raise connectors.ConnectorError("404")
        return pages[url]

    meta = connectors._oauth_discover("https://mcp.ornek/mcp", fake_http)
    assert meta["authorization_endpoint"] == "https://as.ornek/yetki"


def test_discovery_names_the_alternative_when_there_is_no_oauth() -> None:
    def nothing(url, **kwargs):
        raise connectors.ConnectorError("404")

    with pytest.raises(connectors.ConnectorError) as caught:
        connectors._oauth_discover("https://mcp.ornek/mcp", nothing)
    # Not a blind "didn't work": it describes the fixed-token path.
    assert "headers" in str(caught.value)


def test_login_end_to_end_with_a_real_callback(tmp_path: Path) -> None:
    """Discovery → registration → browser → code → token, with a real listener.

    The "browser" is fake: it reads the state from the given authorization
    address and fires a real HTTP request at the redirect address — the
    listener itself is tested, the rest of the flow with fake http."""
    import threading
    import urllib.parse
    import urllib.request

    def fake_http(url, **kwargs):
        if url.endswith("/oauth-protected-resource"):
            return {"authorization_servers": ["https://as.ornek"]}
        if url.endswith("/oauth-authorization-server"):
            return {"authorization_endpoint": "https://as.ornek/yetki",
                    "token_endpoint": "https://as.ornek/token",
                    "registration_endpoint": "https://as.ornek/kayit"}
        if url.endswith("/kayit"):
            assert kwargs["body"]["token_endpoint_auth_method"] == "none"
            return {"client_id": "istemci-1"}
        if url.endswith("/token"):
            form = kwargs["form"]
            assert form["grant_type"] == "authorization_code"
            assert form["code"] == "kod-42"
            assert form["code_verifier"]          # PKCE is verified at the exchange
            return {"access_token": "erisim", "refresh_token": "tazele",
                    "expires_in": 3600}
        raise connectors.ConnectorError("beklenmeyen: " + url)

    def fake_browse(auth_url):
        parts = urllib.parse.urlsplit(auth_url)
        query = urllib.parse.parse_qs(parts.query)
        redirect = query["redirect_uri"][0]
        state = query["state"][0]
        back = redirect + "?" + urllib.parse.urlencode({"code": "kod-42", "state": state})
        threading.Thread(
            target=lambda: urllib.request.urlopen(back, timeout=5).read(),
            daemon=True,
        ).start()

    said = connectors.login(
        connectors.Connector(name="uzak", url="https://mcp.ornek/mcp"),
        tmp_path, http=fake_http, browse=fake_browse, timeout=10,
    )
    assert "tamam" in said.lower()

    saved = connectors._tokens_read(tmp_path)["uzak"]
    assert saved["access_token"] == "erisim"
    assert saved["refresh_token"] == "tazele"
    assert saved["client_id"] == "istemci-1"


def test_a_401_asks_for_login_instead_of_erroring(tmp_path: Path) -> None:
    """When the remote server returns 401, the error is a call to log in, not 'HTTP 401'."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Deny(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Bearer resource_metadata="x"')
            self.end_headers()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Deny)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        session = connectors.Session(
            connectors.Connector(name="uzak", url=f"http://127.0.0.1:{port}/mcp"),
            tmp_path,
        )
        session.open()
        if not (session.ok is False and "Giriş" in (session.error or "")):
            # Under full-suite load (Windows socket pressure) the first
            # attempt can occasionally come back with a different network
            # error (seen in two full runs on 31.08; never in an
            # isolated/single-file run). If the behaviour is broken, the
            # second attempt stays red too.
            session = connectors.Session(
                connectors.Connector(name="uzak", url=f"http://127.0.0.1:{port}/mcp"),
                tmp_path,
            )
            session.open()
        assert session.ok is False
        assert "Giriş" in session.error
        assert "Giriş yap" in session.error
    finally:
        server.shutdown()
        server.server_close()
