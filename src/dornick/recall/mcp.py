"""Exposes the recall protocol as an MCP server.

The aim from the start was this: this memory should be usable not only
inside Dornick but wherever the model runs. MCP exists for exactly that —
Claude Desktop, Claude Code, Cursor or any other MCP-speaking client
registers this server and connects to the same `recall.db` file.

Transport is stdio: the client starts the process, one JSON-RPC message per
line goes back and forth. No extra dependency, no network, no port.

    stdin   requests
    stdout  protocol ONLY. A single stray `print` here breaks the client.
    stderr  log

Because WAL is on, both the agent and this server can be connected to the
same database at the same time: something the agent writes in a session can
be recalled in Claude Desktop instantly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .store import KINDS, RecallStore

# If the version the client asks for is among the supported ones it is
# accepted; otherwise ours is stated and the client finishes the negotiation.
PROTOCOL = "2025-06-18"
SUPPORTED = frozenset({"2025-06-18", "2025-03-26", "2024-11-05"})

SERVER = {"name": "dornick-recall", "version": "1.0.0"}

# JSON-RPC error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def tool_specs() -> list[dict[str, Any]]:
    """The tools exposed to the client.

    The descriptions are the only document the model will read: if when to
    use a tool is not written here, it is either never called or called on
    every message.
    """
    return [
        {
            "name": "recall",
            "description": (
                "Kalıcı bellekte arar. Önce birebir terim eşleşmesi, sonra "
                "çağrışımsal yakınlık; bulunanlardan bağlar üzerinden komşulara "
                "yayılır. Kullanıcı geçmişte konuşulmuş bir şeye atıf yaptığında "
                "('hani şu', 'geçen sefer', 'nasıl yapıyorduk') buraya bak."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Aranan şey."},
                    "limit": {
                        "type": "integer",
                        "description": "Azami kayıt (varsayılan 8).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "remember",
            "description": (
                "Kalıcı belleğe yazar. Yalnızca bir sonraki oturumda da doğru "
                "kalacak şeyler: kullanıcının tercihleri, kararlar, çıkarılan "
                "dersler, yordamlar. Geçici bağlamı yazma."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Kaydedilecek bilgi."},
                    "kind": {
                        "type": "string",
                        "enum": list(KINDS),
                        "description": "Kayıt türü (varsayılan fact).",
                    },
                    "title": {"type": "string", "description": "Kısa başlık."},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["content"],
            },
        },
        {
            "name": "neighbours",
            "description": (
                "Bir kaydın doğrudan bağlı olduğu kayıtlar. `recall` bir şey "
                "bulduktan sonra çevresini görmek için."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
        {
            "name": "forget",
            "description": (
                "Bir kaydı siler. Yanlış ya da artık geçerli olmayan bilgi için; "
                "silinen kayıt aramada bir daha çıkmaz."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
    ]


class Server:
    """Turns MCP requests into `RecallStore` calls."""

    def __init__(self, store: RecallStore) -> None:
        self.store = store
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "recall": self._recall,
            "remember": self._remember,
            "neighbours": self._neighbours,
            "forget": self._forget,
        }

    # -- protocol ------------------------------------------------------

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handles one message. Returns None for a notification — no reply
        must be written."""
        method = message.get("method")
        request_id = message.get("id")

        # Notifications have no id and expect no reply; writing one drops
        # the client into an "unmatched response" error.
        if request_id is None:
            return None

        if method == "initialize":
            return _ok(request_id, self._initialize(message.get("params") or {}))
        if method == "tools/list":
            return _ok(request_id, {"tools": tool_specs()})
        if method == "tools/call":
            return self._call(request_id, message.get("params") or {})
        if method == "ping":
            return _ok(request_id, {})

        return _fail(request_id, METHOD_NOT_FOUND, f"Bilinmeyen yöntem: {method}")

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        wanted = str(params.get("protocolVersion") or "")
        return {
            "protocolVersion": wanted if wanted in SUPPORTED else PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER,
        }

    def _call(self, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        handler = self.handlers.get(str(name))
        if handler is None:
            return _fail(request_id, INVALID_PARAMS, f"Bilinmeyen araç: {name}")

        try:
            text = handler(params.get("arguments") or {})
        except (ValueError, KeyError) as exc:
            # A tool error is not a protocol error: the model should be able
            # to read the error and correct itself, the client's connection
            # must not drop.
            return _ok(request_id, _content(str(exc), error=True))
        except Exception as exc:  # unexpected; still keep the connection alive
            return _ok(request_id, _content(f"{type(exc).__name__}: {exc}", error=True))

        return _ok(request_id, _content(text))

    # -- tools ---------------------------------------------------------

    def _recall(self, args: dict[str, Any]) -> str:
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("Boş sorgu. Ne aradığını `query` alanına yaz.")

        limit = max(1, min(int(args.get("limit") or 8), 40))
        found = self.store.recall(query, limit=limit)
        if not found.hits:
            return f"'{query}' için bellekte bir şey yok."

        lines = [f"'{query}' için {len(found.hits)} kayıt:"]
        for node in found.hits:
            lines.append(f"[{node.id}] ({node.kind}) {node.body}")
        return "\n".join(lines)

    def _remember(self, args: dict[str, Any]) -> str:
        content = str(args.get("content") or "").strip()
        if not content:
            raise ValueError("Boş içerik kaydedilmez.")

        node = self.store.remember(
            content,
            kind=str(args.get("kind") or "fact"),
            title=str(args.get("title") or ""),
            tags=[str(t) for t in (args.get("tags") or [])],
        )
        return f"Kaydedildi: [{node.id}] ({node.kind}) {node.title}"

    def _neighbours(self, args: dict[str, Any]) -> str:
        node_id = str(args.get("id") or "").strip()
        if not node_id:
            raise ValueError("Kayıt kimliği gerekli.")
        if self.store.peek(node_id) is None:
            raise ValueError(f"Kayıt yok: {node_id}")

        linked = self.store.neighbours(node_id)
        if not linked:
            return f"[{node_id}] hiçbir kayda bağlı değil."

        lines = [f"[{node_id}] komşuları:"]
        for node, weight in linked:
            lines.append(f"[{node.id}] ({node.kind}, {weight:.2f}) {node.headline()}")
        return "\n".join(lines)

    def _forget(self, args: dict[str, Any]) -> str:
        node_id = str(args.get("id") or "").strip()
        if not node_id:
            raise ValueError("Kayıt kimliği gerekli.")
        if not self.store.forget(node_id):
            raise ValueError(f"Silinecek kayıt bulunamadı: {node_id}")
        return f"[{node_id}] unutuldu."


# -- JSON-RPC shell ----------------------------------------------------


def _ok(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _fail(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _content(text: str, *, error: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if error:
        payload["isError"] = True
    return payload


def serve(store: RecallStore, stdin: Any = None, stdout: Any = None) -> None:
    """Reads line by line, answers line by line.

    Runs until the stream closes. A single broken line must not bring the
    server down: the client stays open for a long time, and forcing it to
    re-establish the connection because of one error is unnecessary.
    """
    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    server = Server(store)

    for line in source:
        line = line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _write(sink, _fail(None, PARSE_ERROR, f"Bozuk JSON: {exc}"))
            continue

        if not isinstance(message, dict):
            _write(sink, _fail(None, INVALID_REQUEST, "Mesaj bir nesne olmalı."))
            continue

        try:
            answer = server.handle(message)
        except Exception as exc:  # the protocol layer must not crash
            answer = _fail(message.get("id"), INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")

        if answer is not None:
            _write(sink, answer)


def _write(sink: Any, payload: dict[str, Any]) -> None:
    sink.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sink.flush()


def main(argv: list[str] | None = None) -> int:
    """`dornick recall-mcp [memory-path]`.

    If no path is given it falls back to the environment variable, and
    failing that to the shared memory in the user's home directory: the MCP
    client may be running in another directory, and the memory's location
    must not depend on that.
    """
    import os

    args = list(sys.argv[1:] if argv is None else argv)
    raw = args[0] if args else os.getenv("DORNICK_RECALL_DB")
    path = Path(raw).expanduser() if raw else Path.home() / ".dornick" / "recall.db"

    store = RecallStore(path)
    print(f"dornick-recall: {path}", file=sys.stderr, flush=True)
    try:
        serve(store)
    except KeyboardInterrupt:
        pass
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
