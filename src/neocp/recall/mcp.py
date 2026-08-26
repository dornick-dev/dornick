"""Hatırlama protokolünü MCP sunucusu olarak açar.

Amaç baştan beri şuydu: bu bellek yalnızca neocp'nin içinde değil, modelin
çalıştığı her yerde kullanılabilsin. MCP tam olarak bunun için var — Claude
Desktop, Claude Code, Cursor ya da MCP konuşan başka bir istemci bu sunucuyu
tanımlayıp aynı `recall.db` dosyasına bağlanıyor.

Taşıma stdio: istemci süreci başlatıyor, satır başına bir JSON-RPC mesajı
gidip geliyor. Ek bağımlılık yok, ağ yok, port yok.

    stdin   istekler
    stdout  YALNIZCA protokol. Buraya kaçan tek bir `print` istemciyi bozar.
    stderr  günlük

WAL açık olduğu için aynı veritabanına ajan da bu sunucu da aynı anda
bağlanabiliyor: ajanın oturumda yazdığı bir şey Claude Desktop'ta anında
hatırlanabiliyor.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .store import KINDS, RecallStore

# İstemcinin istediği sürüm desteklenenlerdeyse o kabul ediliyor; değilse
# bizimki söyleniyor ve pazarlığı istemci bitiriyor.
PROTOCOL = "2025-06-18"
SUPPORTED = frozenset({"2025-06-18", "2025-03-26", "2024-11-05"})

SERVER = {"name": "neocp-recall", "version": "1.0.0"}

# JSON-RPC hata kodları.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def tool_specs() -> list[dict[str, Any]]:
    """İstemciye açılan araçlar.

    Açıklamalar modelin okuyacağı tek belge: ne zaman kullanılacağı burada
    yazmazsa araç ya hiç çağrılmıyor ya da her mesajda çağrılıyor.
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
    """MCP isteklerini `RecallStore` çağrılarına çevirir."""

    def __init__(self, store: RecallStore) -> None:
        self.store = store
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "recall": self._recall,
            "remember": self._remember,
            "neighbours": self._neighbours,
            "forget": self._forget,
        }

    # -- protokol ------------------------------------------------------

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Bir mesajı işler. Bildirim ise None döner — cevap yazılmamalı."""
        method = message.get("method")
        request_id = message.get("id")

        # Bildirimlerin id'si yok ve cevap beklemiyorlar; cevap yazmak
        # istemciyi "eşleşmeyen yanıt" hatasına düşürür.
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
            # Araç hatası protokol hatası değil: model hatayı okuyup
            # düzeltebilmeli, istemcinin bağlantısı kopmamalı.
            return _ok(request_id, _content(str(exc), error=True))
        except Exception as exc:  # beklenmeyen; yine de bağlantı sürsün
            return _ok(request_id, _content(f"{type(exc).__name__}: {exc}", error=True))

        return _ok(request_id, _content(text))

    # -- araçlar -------------------------------------------------------

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


# -- JSON-RPC kabuğu ---------------------------------------------------


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
    """Satır satır okur, satır satır cevaplar.

    Akış kapanana kadar sürüyor. Tek bir bozuk satır sunucuyu düşürmemeli:
    istemci uzun süre açık kalıyor ve bir hata yüzünden bağlantıyı yeniden
    kurmak zorunda bırakmak gereksiz.
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
        except Exception as exc:  # protokol katmanı çökmemeli
            answer = _fail(message.get("id"), INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")

        if answer is not None:
            _write(sink, answer)


def _write(sink: Any, payload: dict[str, Any]) -> None:
    sink.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sink.flush()


def main(argv: list[str] | None = None) -> int:
    """`neocp recall-mcp [bellek-yolu]`.

    Yol verilmezse ortam değişkenine, o da yoksa kullanıcının ev dizinindeki
    ortak belleğe düşüyor: MCP istemcisi başka bir dizinde çalışıyor olabilir
    ve belleğin yerinin buna bağlı olmaması gerekiyor.
    """
    import os

    args = list(sys.argv[1:] if argv is None else argv)
    raw = args[0] if args else os.getenv("NEOCP_RECALL_DB")
    path = Path(raw).expanduser() if raw else Path.home() / ".neocp" / "recall.db"

    store = RecallStore(path)
    print(f"neocp-recall: {path}", file=sys.stderr, flush=True)
    try:
        serve(store)
    except KeyboardInterrupt:
        pass
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
