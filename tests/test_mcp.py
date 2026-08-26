"""Hatırlama protokolünün MCP yüzeyi.

Amaç baştan beri buydu: bu bellek yalnızca neocp'nin içinde değil, modelin
çalıştığı her yerde kullanılabilsin. Protokol hataları sinsi — istemci
"sunucu yanıt vermiyor" der ve sebebini söylemez — o yüzden çerçevenin
kendisi de test ediliyor, yalnızca araçlar değil.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from neocp.recall.mcp import PROTOCOL, SUPPORTED, Server, serve, tool_specs
from neocp.recall.store import RecallStore


@pytest.fixture()
def store(tmp_path: Path) -> RecallStore:
    box = RecallStore(tmp_path / "recall.db")
    yield box
    box.close()


@pytest.fixture()
def server(store: RecallStore) -> Server:
    return Server(store)


def ask(server: Server, method: str, params: dict | None = None, request_id: int = 1):
    return server.handle(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
    )


def call(server: Server, name: str, **arguments):
    answer = ask(server, "tools/call", {"name": name, "arguments": arguments})
    return answer["result"]


def text_of(result: dict) -> str:
    return "\n".join(block["text"] for block in result["content"])


# -- protokol ----------------------------------------------------------


def test_initialize_reports_tools(server: Server) -> None:
    result = ask(server, "initialize", {"protocolVersion": PROTOCOL})["result"]

    assert result["protocolVersion"] == PROTOCOL
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"]


def test_a_supported_version_the_client_asks_for_is_honoured(server: Server) -> None:
    older = "2024-11-05"
    assert older in SUPPORTED
    result = ask(server, "initialize", {"protocolVersion": older})["result"]
    assert result["protocolVersion"] == older


def test_an_unknown_version_falls_back_to_ours(server: Server) -> None:
    result = ask(server, "initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert result["protocolVersion"] == PROTOCOL


def test_notifications_get_no_answer(server: Server) -> None:
    """Bildirimlerin id'si yok ve cevap beklemiyorlar; cevap yazmak istemciyi
    'eşleşmeyen yanıt' hatasına düşürür."""
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_an_unknown_method_is_a_protocol_error(server: Server) -> None:
    answer = ask(server, "tools/uydurma")
    assert answer["error"]["code"] == -32601


def test_every_tool_declares_a_schema() -> None:
    """Şemasız araç istemcide görünmüyor ya da argümansız çağrılıyor."""
    for spec in tool_specs():
        assert spec["name"] and spec["description"]
        schema = spec["inputSchema"]
        assert schema["type"] == "object"
        assert schema["properties"]


def test_descriptions_say_when_to_use_the_tool() -> None:
    """Açıklama modelin okuyacağı tek belge: ne zaman kullanılacağı orada
    yazmazsa araç ya hiç çağrılmıyor ya da her mesajda çağrılıyor."""
    recall = next(s for s in tool_specs() if s["name"] == "recall")
    assert len(recall["description"]) > 120


# -- araçlar -----------------------------------------------------------


def test_remember_then_recall(server: Server) -> None:
    call(server, "remember", content="Postgres yedeği her gece 03:00'te alınıyor",
         kind="procedure")

    found = text_of(call(server, "recall", query="veritabanı yedeği"))
    assert "03:00" in found


def test_recall_says_so_when_nothing_matches(server: Server) -> None:
    result = call(server, "recall", query="hiç konuşulmamış bir konu")
    assert not result.get("isError")
    assert "yok" in text_of(result)


def test_an_empty_query_is_an_error_the_model_can_read(server: Server) -> None:
    """Araç hatası protokol hatası değil: model hatayı okuyup düzeltebilmeli,
    istemcinin bağlantısı kopmamalı."""
    result = call(server, "recall", query="   ")

    assert result["isError"]
    assert "query" in text_of(result)


def test_neighbours_walks_the_links(server: Server) -> None:
    call(server, "remember", content="Postgres yedeği gece alınıyor", kind="procedure")
    call(server, "remember", content="Postgres sunucusu Frankfurt'ta", kind="fact")

    ids = [
        line.split("]")[0].lstrip("[")
        for line in text_of(call(server, "recall", query="postgres")).splitlines()[1:]
    ]
    assert ids

    linked = text_of(call(server, "neighbours", id=ids[0]))
    assert "Postgres" in linked


def test_neighbours_of_a_missing_record_is_an_error(server: Server) -> None:
    result = call(server, "neighbours", id="n_yok")
    assert result["isError"]


def test_forget_removes_it_from_search(server: Server) -> None:
    saved = text_of(call(server, "remember", content="yanlış bir bilgi"))
    node_id = saved.split("]")[0].split("[")[-1]

    assert not call(server, "forget", id=node_id).get("isError")
    assert "yok" in text_of(call(server, "recall", query="yanlış bir bilgi"))


def test_an_unknown_tool_is_refused(server: Server) -> None:
    answer = ask(server, "tools/call", {"name": "uydurma", "arguments": {}})
    assert answer["error"]["code"] == -32602


# -- stdio kabuğu ------------------------------------------------------


def run_lines(store: RecallStore, *lines: str) -> list[dict]:
    out = io.StringIO()
    serve(store, io.StringIO("\n".join(lines) + "\n"), out)
    return [json.loads(line) for line in out.getvalue().splitlines() if line]


def test_one_message_per_line(store: RecallStore) -> None:
    answers = run_lines(
        store,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    )

    assert [a["id"] for a in answers] == [1, 2]
    assert answers[1]["result"]["tools"]


def test_a_broken_line_does_not_kill_the_server(store: RecallStore) -> None:
    """İstemci uzun süre açık kalıyor; tek bir bozuk satır yüzünden
    bağlantıyı yeniden kurmak zorunda bırakmak gereksiz."""
    answers = run_lines(
        store,
        "bu json degil",
        json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}),
    )

    assert answers[0]["error"]["code"] == -32700
    assert answers[1]["id"] == 7


def test_blank_lines_are_skipped(store: RecallStore) -> None:
    answers = run_lines(
        store, "", json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}), ""
    )
    assert len(answers) == 1


def test_notifications_produce_no_line(store: RecallStore) -> None:
    answers = run_lines(
        store, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    )
    assert answers == []


def test_the_same_database_is_shared_with_the_agent(tmp_path: Path) -> None:
    """WAL açık; ajanın oturumda yazdığı bir şey MCP istemcisinde anında
    hatırlanabilmeli. Amaç zaten belleği her yerde kullanabilmekti."""
    path = tmp_path / "recall.db"
    writer = RecallStore(path)
    writer.remember("Fatih SCADA tarafında çalışıyor", kind="user")

    reader = RecallStore(path)
    try:
        found = text_of(Server(reader).handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "recall", "arguments": {"query": "scada"}}}
        )["result"])
        assert "SCADA" in found
    finally:
        writer.close()
        reader.close()
