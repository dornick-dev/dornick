"""Zihin arayüzü testleri.

Sunucu ayrı bir thread'de dönüyor ve ajanın asyncio döngüsüne dokunmuyor;
aradaki tek köprü olay günlüğünün abonelik kancası. Buradaki testler o
köprünün ve graf modelinin doğruluğunu tutuyor.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
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


# -- sürüm görünürlüğü -------------------------------------------------


def test_bridge_snapshot_surumu_tasir() -> None:
    """/api/state'in "surum" alanı: üst bardaki marka ipucu buradan.

    Ajan hiç açılmamışken bile sürüm görünmeli — sahada "hangi kopya
    açık?" sorusu tam da bozuk açılışlarda soruluyor.
    """
    import asyncio

    from neocp import ortam
    from neocp.desktop import Bridge

    loop = asyncio.new_event_loop()
    try:
        durum = Bridge(Hub(), loop).snapshot()
        assert durum["surum"] == ortam.surum()
        assert isinstance(durum["kurulu"], bool)
    finally:
        loop.close()


def test_surum_denetimi_ucu_agsiz_calisir(
    tmp_path: Path, mind: Mind, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/surum sunucu tarafında denetler; test ağa hiç çıkmaz."""
    from neocp.web import server as server_module

    monkeypatch.setattr(
        server_module.ortam, "guncelleme_denetle",
        lambda: {"ok": True, "mevcut": "0.2.2", "yeni": "0.3.0",
                 "url": "https://ornek/yayin", "hata": ""})

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        istek = urllib.request.Request(
            server.url + "api/surum", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(istek, timeout=5) as cevap:
            veri = json.loads(cevap.read().decode("utf-8"))
        assert veri["yeni"] == "0.3.0" and veri["url"] == "https://ornek/yayin"
    finally:
        server.stop()
        log.close()


# -- ham dosya ucu (/api/raw) ------------------------------------------
#
# `/api/files` metin döndürüyor: bir PNG oradan yalnızca "ikili dosya"
# olarak geliyordu ve görüntüleyici görseli gösteremiyordu. Bu uç ham
# baytları veriyor — ama aynı kapıdan: yol doğrulanıyor, tür uzantıdan
# ve kısa bir listeden veriliyor.

# 1x1 saydam PNG (gerçek bayt, sahte değil): tür ve uzunluk sınanabilsin.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def test_raw_serves_real_bytes_with_a_declared_type(tmp_path: Path, mind: Mind) -> None:
    """Görüntüleyicinin bir görseli GERÇEKTEN açabilmesi buna bağlı."""
    from neocp.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    (tmp_path / "kare.png").write_bytes(TINY_PNG)

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    try:
        with urllib.request.urlopen(server.url + "api/raw?path=kare.png", timeout=5) as cevap:
            gövde = cevap.read()
            assert cevap.headers["Content-Type"] == "image/png"
            # Tarayıcı içeriğe bakıp kendi türünü uydurmasın.
            assert cevap.headers["X-Content-Type-Options"] == "nosniff"
        assert gövde == TINY_PNG
    finally:
        server.stop()
        log.close()


def test_raw_refuses_to_leave_the_workspace(tmp_path: Path, mind: Mind) -> None:
    """Yolu istekten türetmek dizin dışına çıkma açığının klasik yolu:
    `..` ile yukarı çıkan bir istek dosyayı ALMAMALI."""
    from neocp.config import Config

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
        # Olmayan dosya 404: "yok" ile "yasak" ayrı cevaplar.
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(server.url + "api/raw?path=yok.png", timeout=5)
        assert missing.value.code == 404
    finally:
        server.stop()
        log.close()


def test_raw_never_serves_a_workspace_file_as_html(tmp_path: Path, mind: Mind) -> None:
    """Ajanın yazdığı bir sayfayı ANA kökte html olarak servis etmek, o
    sayfaya programın DOM'unu ve `/api` uçlarını açardı. Bilinmeyen tür
    indirilir, yorumlanmaz."""
    from neocp.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    (tmp_path / "sayfa.html").write_text("<script>alert(1)</script>", encoding="utf-8")

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    try:
        with urllib.request.urlopen(server.url + "api/raw?path=sayfa.html", timeout=5) as cevap:
            assert cevap.headers["Content-Type"] == "application/octet-stream"
    finally:
        server.stop()
        log.close()


def test_raw_supports_ranges_so_media_can_seek(tmp_path: Path, mind: Mind) -> None:
    """Ses/video oynatıcıları ileri sarmak için menzil istiyor."""
    import http.client

    from neocp.config import Config

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
        cevap = conn.getresponse()
        gövde = cevap.read()
        assert cevap.status == 206
        assert cevap.getheader("Content-Range") == "bytes 10-19/256"
        assert gövde == bytes(range(10, 20))
        conn.close()
    finally:
        server.stop()
        log.close()


# -- oturum kimliği ve döküm araması (uçlar) ---------------------------


def _oturum_yaz(sessions_dir: Path, sid: str, turlar: list[tuple[str, str]]) -> None:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"kind": "note", "name": "session_start"})]
    for role, text in turlar:
        lines.append(json.dumps({
            "kind": "message", "role": role,
            "content": [{"type": "text", "text": text}],
        }, ensure_ascii=False))
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_naming_a_session_reaches_the_listing(tmp_path: Path, mind: Mind) -> None:
    """Ad verilmiş konuşma listede o adla görünmeli; verilmemişse başlık
    yine konuşmanın ilk sözünden türetiliyor."""
    _oturum_yaz(mind.sessions_dir, "20260101T000000Z",
                [("user", "Kayseri OSB için SCADA teklifi hazırla")])

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        def liste() -> dict:
            with urllib.request.urlopen(server.url + "api/sessions", timeout=5) as cevap:
                return json.loads(cevap.read().decode("utf-8"))

        ilk = liste()["sessions"][0]
        assert not ilk["named"] and "SCADA" in ilk["title"]

        istek = urllib.request.Request(
            server.url + "api/session/meta",
            data=json.dumps({"id": "20260101T000000Z", "ad": "Kayseri teklifi",
                             "etiketler": ["scada", "teklif"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(istek, timeout=5) as cevap:
            assert json.loads(cevap.read().decode("utf-8"))["ok"] is True

        veri = liste()
        satir = veri["sessions"][0]
        assert satir["title"] == "Kayseri teklifi" and satir["named"]
        assert satir["tags"] == ["scada", "teklif"]
        # Panelin süzgeç listesi: var olan etiketler.
        assert veri["tags"] == ["scada", "teklif"]
    finally:
        server.stop()
        log.close()


def test_the_meta_endpoint_refuses_a_path_shaped_id(tmp_path: Path, mind: Mind) -> None:
    """Kimlik dosya adına dönüşüyor: `..` ile yukarı çıkan bir istek
    dizin dışına yazamamalı."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        istek = urllib.request.Request(
            server.url + "api/session/meta",
            data=json.dumps({"id": "../gizli", "ad": "x"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(istek, timeout=5) as cevap:
            veri = json.loads(cevap.read().decode("utf-8"))
        assert veri["ok"] is False
    finally:
        server.stop()
        log.close()


def test_the_listing_searches_inside_transcripts(tmp_path: Path, mind: Mind) -> None:
    """Arama bugüne kadar yalnızca başlığı süzüyordu; söz konuşmanın
    ortasında geçiyorsa liste onu bulamıyordu."""
    _oturum_yaz(mind.sessions_dir, "20260101T000000Z",
                [("user", "selam"), ("assistant", "Modbus kayıtlarını okudum.")])
    _oturum_yaz(mind.sessions_dir, "20260102T000000Z", [("user", "hava nasıl")])

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        with urllib.request.urlopen(server.url + "api/sessions?ara=modbus", timeout=5) as cevap:
            veri = json.loads(cevap.read().decode("utf-8"))
        assert veri["searched"] is True
        eslesen = {s["id"]: s["hits"] for s in veri["sessions"] if s["hits"]}
        assert set(eslesen) == {"20260101T000000Z"}
        assert "Modbus" in eslesen["20260101T000000Z"][0]["text"]

        # Aramasız istek eskisi gibi: eşleşme alanı boş, liste tam.
        with urllib.request.urlopen(server.url + "api/sessions", timeout=5) as cevap:
            duz = json.loads(cevap.read().decode("utf-8"))
        assert duz["searched"] is False
        assert all(not s["hits"] for s in duz["sessions"])
        assert len(duz["sessions"]) == 2
    finally:
        server.stop()
        log.close()


# -- klasör gezgini (proje seçimi) -------------------------------------
#
# `/api/files` çalışma alanının içinde kalıyor; proje tam olarak onun
# DIŞINDA bir yer ve native bir klasör diyaloğu kullanılamıyor.


def test_the_browser_lists_folders_anywhere_but_only_folders(
    tmp_path: Path, mind: Mind
) -> None:
    kok = tmp_path / "kod"
    (kok / "proje" / "src").mkdir(parents=True)
    (kok / ".gizli").mkdir()
    (kok / "not.txt").write_text("x", encoding="utf-8")

    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        adres = server.url + "api/gozat?yol=" + urllib.parse.quote(str(kok))
        with urllib.request.urlopen(adres, timeout=5) as cevap:
            veri = json.loads(cevap.read().decode("utf-8"))

        adlar = [k["ad"] for k in veri["klasorler"]]
        assert adlar == ["proje"]          # yalnız klasörler, gizliler elenmiş
        assert veri["dosya"] == 1          # dosyalar yalnızca SAYI olarak
        assert veri["ust"] == str(tmp_path)
        assert veri["engel"] == ""         # seçilebilir
        # Dosya adları ya da içerikleri hiç dönmüyor.
        assert "not.txt" not in json.dumps(veri)
    finally:
        server.stop()
        log.close()


def test_the_browser_says_when_a_folder_cannot_be_a_project(
    tmp_path: Path, mind: Mind
) -> None:
    """Kullanıcı KAYDETMEDEN önce görmeli: seçim ekranında engel yazıyor."""
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0)
    server.start()
    try:
        kok = Path(tmp_path.anchor or "/")
        adres = server.url + "api/gozat?yol=" + urllib.parse.quote(str(kok))
        with urllib.request.urlopen(adres, timeout=5) as cevap:
            veri = json.loads(cevap.read().decode("utf-8"))
        assert veri["engel"]

        # Olmayan klasör: hata, çökme değil.
        yok = server.url + "api/gozat?yol=" + urllib.parse.quote(str(tmp_path / "yok"))
        with urllib.request.urlopen(yok, timeout=5) as cevap:
            assert json.loads(cevap.read().decode("utf-8"))["hata"]

        # Yolsuz istek: başlangıç yerleri (sürücüler / ev).
        with urllib.request.urlopen(server.url + "api/gozat", timeout=5) as cevap:
            bas = json.loads(cevap.read().decode("utf-8"))
        assert bas["klasorler"] and bas["ust"] is None
    finally:
        server.stop()
        log.close()


def test_the_settings_snapshot_carries_the_project_state(
    tmp_path: Path, mind: Mind
) -> None:
    """Ayar sayfası projeyi çizebilmeli: seçili yol, çözülmüş kök, son
    projeler ve (varsa) sebep."""
    from neocp import settings as settings_module
    from neocp.config import Config

    proje = tmp_path / "musteri"
    proje.mkdir()
    config = Config.load(tmp_path)
    config.ensure_dirs()
    updated = settings_module.apply(config, {"sandbox": {"project": str(proje)}})

    kutu = settings_module.snapshot(updated)["sandbox"]
    assert kutu["project"] == str(proje)
    assert kutu["project_root"] == str(proje.resolve())
    assert kutu["project_error"] == ""
    assert str(proje) in kutu["recent"]
