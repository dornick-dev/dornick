"""Zihin arayüzü testleri.

Sunucu ayrı bir thread'de dönüyor ve ajanın asyncio döngüsüne dokunmuyor;
aradaki tek köprü olay günlüğünün abonelik kancası. Buradaki testler o
köprünün ve graf modelinin doğruluğunu tutuyor.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from neocp.events import EventLog
from neocp.mind import Mind, open_mind
from neocp.web import MindServer, build_graph
from neocp.web.server import Hub, _payload, _summarize


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


# -- graf modeli -------------------------------------------------------


def test_empty_mind_is_just_the_self_node(mind: Mind) -> None:
    graph = build_graph(mind)
    assert [n["id"] for n in graph["nodes"]] == ["self"]
    assert graph["edges"] == []


def test_graph_is_two_levels_deep(mind: Mind) -> None:
    """Yüzlerce hatırayı doğrudan merkeze bağlamak yıldız değil yumak üretir."""
    mind.remember("Fatih SCADA tarafında çalışıyor.", kind="user")
    mind.remember("Türkçe konuşuyor.", kind="preference")

    graph = build_graph(mind)
    ids = {n["id"] for n in graph["nodes"]}
    edges = {(e["source"], e["target"]) for e in graph["edges"]}

    assert "hub:user" in ids and "hub:preference" in ids
    assert ("self", "hub:user") in edges
    # Yaprak doğrudan merkeze bağlanmamalı.
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


# -- olay yayını -------------------------------------------------------


def test_only_interesting_notes_are_streamed() -> None:
    log = EventLog(Path("/dev/null")) if False else None  # tip ipucu için
    assert _payload(_note("tool_start", tool="shell")) is not None
    # Oturum başlangıcı arayüzü kalabalıklaştırmaktan başka işe yaramaz.
    assert _payload(_note("session_start")) is None


def test_tool_result_turns_are_not_shown_as_user_messages() -> None:
    """Araç sonucu teknik olarak kullanıcı turudur; sohbette öyle görünmemeli."""
    from neocp.events import Event, utcnow

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
    """Dışarıdan verilen hub günlüğe de abone olmalı.

    Sunucu kendi hub'ını kurup sonradan değiştirdiğinde abonelik eski hub'da
    kalıyordu: asistan metni geliyor, kullanıcı mesajı ve araç olayları
    sessizce kayboluyordu. Hiçbir hata vermiyordu.
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
    """Arayüz çökerse ajan çalışmaya devam etmeli."""
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


# -- uçtan uca ---------------------------------------------------------


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
        assert "neo" in page
        # Sayfa varlıklara referans veriyorsa o varlıklar da servis edilmeli;
        # biri eksikse arayüz sessizce boş açılır.
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
    """Kurulum sihirbazının dil seçimi /api/dil'den okunuyor.

    localStorage'a kurulumdan yazılamaz; sihirbaz çalışma alanına
    setup.json bırakır ve dil.js ilk açılışta buradan okur. Eski
    sürümlerin bıraktığı kurulum.json da tanınır — güncelleme dil
    seçimini kaybettirmemeli. Dosya yoksa boş dönmeli — arayüz
    Türkçe'ye düşer.
    """
    from neocp.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()

    def fetch() -> dict:
        with urllib.request.urlopen(server.url + "api/dil", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        assert fetch() == {"dil": ""}
        # Eski ad tek başına: geriye uyumluluk (mevcut kurulumlar).
        (tmp_path / "kurulum.json").write_text('{"dil": "en"}', encoding="utf-8")
        assert fetch() == {"dil": "en"}
        # Yeni ad öncelikli.
        (tmp_path / "setup.json").write_text('{"dil": "tr"}', encoding="utf-8")
        assert fetch() == {"dil": "tr"}
        # Bozuk yeni dosya sunucuyu düşürmemeli; eski ada düşülür.
        (tmp_path / "setup.json").write_text("{bozuk", encoding="utf-8")
        assert fetch() == {"dil": "en"}
        # Tek başına bozuk dosya: sessizce Türkçe'ye dönülür.
        (tmp_path / "kurulum.json").unlink()
        assert fetch() == {"dil": ""}
    finally:
        server.stop()
        log.close()


def test_unlisted_paths_are_not_served(tmp_path: Path, mind: Mind) -> None:
    """Yolu istekten türetmek dizin dışına çıkma açığının klasik yolu."""
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
    """Burada ajanın belleği var; dışarı açılacak bir yüzey değil."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    try:
        assert server.url.startswith("http://127.0.0.1:")
    finally:
        server.stop()
        log.close()


def _note(kind: str, **meta: object):
    from neocp.events import Event, utcnow

    return Event(seq=0, ts=utcnow(), kind="meta", content=kind, meta=meta)


def test_event_stream_is_framed_so_it_is_not_buffered(tmp_path: Path, mind: Mind) -> None:
    """HTTP/1.1'de govdenin sonu Content-Length, chunked ya da baglantinin
    kapanmasiyla belirlenir. Uzunluk bilinmedigi icin "keep-alive" demek
    govdeyi cercevesiz birakiyordu: tarayici akisi tampona aliyor ve cevap
    toptan geliyordu.
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

        # Olay yayinlandiginda hemen okunabilmeli.
        log.note("tool_start", tool="shell")
        assert b"tool_start" in response.readline() + response.readline()
        conn.close()
    finally:
        server.stop()
        log.close()


def test_a_raw_body_is_not_consumed_twice(tmp_path: Path, mind: Mind) -> None:
    """Gövde bir kez okunuyor.

    Önce JSON diye ayrıştırıp sonra ham hali tekrar okumaya kalkmak istekleri
    sonsuza kadar askıda bırakıyordu: ses isteğinin gövdesi JSON değil ham
    ses ve ikinci okuma hiç gelmeyecek baytları bekliyor. O istek bir
    thread'i tutunca tarayıcının bağlantı kotası doluyor ve mikrofon,
    ayarlar, sohbet — hepsi kilitleniyordu.
    """
    import http.client

    from neocp.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    host, port = server.url.split("//")[1].rstrip("/").split(":")

    try:
        conn = http.client.HTTPConnection(host, int(port), timeout=8)
        # JSON olmayan bir gövde: ses isteğinin taşıdığı şeyin aynısı.
        conn.request("POST", "/api/hear", body=b"\x1aE\xdf\xa3 ham ses",
                     headers={"Content-Type": "audio/webm"})
        # Askıda kalırsa burada timeout patlar; hangi durum kodu döndüğü
        # önemli değil, **döndüğü** önemli.
        assert conn.getresponse().status in (409, 400, 501, 503)
        conn.close()

        # Sunucu hâlâ ayakta: takılan bir istek ötekileri de düşürüyordu.
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
    """HTTP durum satırı latin-1 olmak zorunda.

    "Sesli komut kapalı" gönderince stdlib UnicodeEncodeError atıyor,
    handler ölüyor ve bağlantı **cevapsız** kapanıyordu. İstemci tarafında
    bu "hiçbir şey olmuyor" gibi görünüyor — hata mesajı bile gelmiyor.
    """
    import http.client

    from neocp.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    host, port = server.url.split("//")[1].rstrip("/").split(":")

    try:
        conn = http.client.HTTPConnection(host, int(port), timeout=8)
        # Sesli komut kapalı: Türkçe bir hata mesajı dönmeli.
        conn.request("POST", "/api/hear", body=b"ham ses",
                     headers={"Content-Type": "audio/webm"})
        answer = conn.getresponse()

        assert answer.status == 409
        # Gerçek metin gövdede: durum satırına sığmıyor.
        assert "kapalı" in answer.read().decode("utf-8", "replace")
        conn.close()

        # Sunucu ayakta kaldı: çöken bir handler bağlantıyı düşürüyordu.
        conn = http.client.HTTPConnection(host, int(port), timeout=8)
        conn.request("GET", "/api/graph")
        assert conn.getresponse().status == 200
        conn.close()
    finally:
        server.stop()
        log.close()


def test_the_body_is_served_even_before_anything_is_open(tmp_path: Path, mind: Mind) -> None:
    """Sahne organları buradan okuyor. Uç nokta cevap vermezse ekranda
    hiçbir aygıt görünmüyor — ajan gövdesiz duruyor."""
    from neocp.config import Config

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
    """Ayarsız çalışan bir önizlemede sayfa yine açılmalı: eksik yapı
    hata değil boş liste."""
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
