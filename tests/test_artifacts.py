"""Artifact deposu, aracı ve servis ucu.

Vaat üç cümle: yayınlanan sayfa kalıcı bir adreste yaşar, aynı kimliğe
yazılan güncelleme adresi değiştirmez ve istekten gelen hiçbir yol deponun
dışına çıkamaz. Buradaki testler bu üç cümlenin sınırlarını kolluyor.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from dornick import artifacts
from dornick.config import Config
from dornick.events import EventLog
from dornick.mind import Mind, open_mind
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import artifacts as artifact_tools
from dornick.web import MindServer


# -- depo --------------------------------------------------------------


def test_publish_writes_page_and_meta(tmp_path: Path) -> None:
    meta = artifacts.publish(tmp_path, "Günlük Rapor", "<!DOCTYPE html><p>x</p>")

    target = tmp_path / artifacts.FOLDER / meta["id"]
    assert (target / "index.html").read_text(encoding="utf-8").endswith("<p>x</p>")
    saved = json.loads((target / "meta.json").read_text(encoding="utf-8"))
    assert saved["title"] == "Günlük Rapor"
    assert saved["surum"] == 1
    assert saved["created"] == saved["updated"]


def test_id_is_a_readable_slug_with_a_suffix(tmp_path: Path) -> None:
    """Kimlik okunur olmalı (başlıktan) ama tek başına slug yetmez:
    "Günlük rapor" her gün yayınlanır ve ikincisi ilkini ezerdi."""
    meta = artifacts.publish(tmp_path, "Günlük Şişli Raporu", "<p>x</p>")

    assert meta["id"].startswith("gunluk-sisli-raporu-")
    suffix = meta["id"].rsplit("-", 1)[1]
    assert len(suffix) == 4 and all(c in "0123456789abcdef" for c in suffix)
    # Aynı başlıkla ikinci yayın ayrı bir artifact.
    other = artifacts.publish(tmp_path, "Günlük Şişli Raporu", "<p>y</p>")
    assert other["id"] != meta["id"]


def test_publish_requires_title_and_html(tmp_path: Path) -> None:
    with pytest.raises(artifacts.ArtifactError):
        artifacts.publish(tmp_path, "", "<p>x</p>")
    with pytest.raises(artifacts.ArtifactError):
        artifacts.publish(tmp_path, "başlık", "   ")


def test_update_keeps_the_address_and_archives_the_old_page(tmp_path: Path) -> None:
    meta = artifacts.publish(tmp_path, "Pano", "<p>v1</p>")
    updated = artifacts.update(tmp_path, meta["id"], "<p>v2</p>")

    assert updated["id"] == meta["id"]          # adres değişmez
    assert updated["surum"] == 2
    target = tmp_path / artifacts.FOLDER / meta["id"]
    assert "v2" in (target / "index.html").read_text(encoding="utf-8")
    # Eski sürüm kaybolmadı: surumler/1.html olarak duruyor.
    assert "v1" in (target / artifacts.VERSIONS / "1.html").read_text(encoding="utf-8")


def test_update_can_rename(tmp_path: Path) -> None:
    meta = artifacts.publish(tmp_path, "Eski Ad", "<p>x</p>")
    updated = artifacts.update(tmp_path, meta["id"], "<p>y</p>", title="Yeni Ad")
    assert updated["title"] == "Yeni Ad"


def test_only_the_last_versions_are_kept(tmp_path: Path) -> None:
    """Sınırsız sürüm biriktirmek diski çöplüğe çevirir; son beş yeter."""
    meta = artifacts.publish(tmp_path, "Pano", "<p>v1</p>")
    for n in range(2, 10):
        artifacts.update(tmp_path, meta["id"], f"<p>v{n}</p>")

    versions = tmp_path / artifacts.FOLDER / meta["id"] / artifacts.VERSIONS
    kept = sorted(int(p.stem) for p in versions.glob("*.html"))
    assert len(kept) == artifacts.KEEP_VERSIONS
    assert kept == [4, 5, 6, 7, 8]              # en yeni beş eski sürüm


def test_update_of_an_unknown_id_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(artifacts.ArtifactError):
        artifacts.update(tmp_path, "yok-abcd", "<p>x</p>")


def test_listing_is_newest_first_and_skips_junk(tmp_path: Path) -> None:
    a = artifacts.publish(tmp_path, "Birinci", "<p>1</p>")
    b = artifacts.publish(tmp_path, "İkinci", "<p>2</p>")
    artifacts.update(tmp_path, a["id"], "<p>1b</p>")   # a artık daha taze

    # Bozuk kayıt (meta'sız klasör) ve çöp klasörü listeyi düşürmemeli.
    (tmp_path / artifacts.FOLDER / "bozuk-kayit").mkdir()
    (tmp_path / artifacts.FOLDER / artifacts.TRASH).mkdir()

    rows = artifacts.listing(tmp_path)
    assert [m["id"] for m in rows] == [a["id"], b["id"]]


def test_listing_survives_a_missing_store(tmp_path: Path) -> None:
    assert artifacts.listing(tmp_path / "hicyok") == []


def test_paths_cannot_escape_the_store(tmp_path: Path) -> None:
    """Yol istekten kurulmuyor: kimlik desenden geçmeden diske dokunulmaz."""
    meta = artifacts.publish(tmp_path, "Pano", "<p>x</p>")

    assert artifacts.page_path(tmp_path, meta["id"]) is not None
    for bad in ("../config", "..", "a/b", "a\\b", "A-BUYUK", ".gizli", "", "x" * 100):
        assert artifacts.page_path(tmp_path, bad) is None


def test_remove_moves_to_trash_not_oblivion(tmp_path: Path) -> None:
    meta = artifacts.publish(tmp_path, "Pano", "<p>x</p>")
    result = artifacts.remove(tmp_path, meta["id"])

    assert result["ok"]
    assert artifacts.listing(tmp_path) == []
    # Kalıcı silme yok: içerik çöpte duruyor, elle geri alınabilir.
    trash = tmp_path / artifacts.FOLDER / artifacts.TRASH
    moved = list(trash.iterdir())
    assert len(moved) == 1 and (moved[0] / "index.html").is_file()

    with pytest.raises(artifacts.ArtifactError):
        artifacts.remove(tmp_path, meta["id"])


# -- araç --------------------------------------------------------------


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    artifact_tools.register(reg)
    return reg


async def call(registry: ToolRegistry, ctx: ToolContext, **args):
    return await registry.get("artifact").handler(args, ctx)


def test_tool_is_a_mutation(registry: ToolRegistry) -> None:
    """İzin motoru buna bakıyor: yayın bir yazma işlemi, sorulmadan geçmemeli."""
    spec = registry.get("artifact")
    assert spec is not None and spec.mutates


def test_tool_publish_returns_id_and_announces(registry, ctx) -> None:
    result = asyncio.run(call(
        registry, ctx, action="publish", title="Atölye Özeti",
        html="<!DOCTYPE html><p>rapor</p>",
    ))

    assert not result.is_error
    meta = result.detail["artifact"]
    assert f"/artifact/{meta['id']}/" in result.content
    # Aynı id ile güncelleme yönergesi modele söyleniyor.
    assert "update" in result.content
    # Kart olayı günlüğe düştü: sunucu bunu SSE'ye taşıyor.
    notes = ctx.session.log.notes("artifact")
    assert len(notes) == 1
    assert notes[0].meta["id"] == meta["id"]
    assert notes[0].meta["surum"] == 1
    assert notes[0].meta["action"] == "publish"


def test_tool_update_bumps_the_version(registry, ctx) -> None:
    first = asyncio.run(call(
        registry, ctx, action="publish", title="Pano", html="<p>v1</p>",
    ))
    artifact_id = first.detail["artifact"]["id"]

    result = asyncio.run(call(
        registry, ctx, action="update", id=artifact_id, html="<p>v2</p>",
    ))

    assert not result.is_error
    assert "v2" in result.content and artifact_id in result.content
    assert ctx.session.log.notes("artifact")[-1].meta["surum"] == 2


def test_tool_list_shows_what_was_published(registry, ctx) -> None:
    empty = asyncio.run(call(registry, ctx, action="list"))
    assert "Henüz" in empty.content

    asyncio.run(call(registry, ctx, action="publish", title="Pano", html="<p>x</p>"))
    listed = asyncio.run(call(registry, ctx, action="list"))
    assert "pano-" in listed.content and "v1" in listed.content


def test_tool_errors_teach(registry, ctx) -> None:
    missing = asyncio.run(call(registry, ctx, action="publish", title="x"))
    assert missing.is_error and "html" in missing.content

    unknown = asyncio.run(call(registry, ctx, action="update", id="yok-abcd", html="<p>x</p>"))
    assert unknown.is_error and "list" in unknown.content

    weird = asyncio.run(call(registry, ctx, action="yayimla"))
    assert weird.is_error and "publish" in weird.content


# -- servis ------------------------------------------------------------


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


def _server(tmp_path: Path, mind: Mind) -> tuple[MindServer, EventLog, Config]:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()
    return server, log, config


def test_artifact_pages_are_served_at_a_stable_address(tmp_path: Path, mind: Mind) -> None:
    server, log, config = _server(tmp_path, mind)
    meta = artifacts.publish(config.state_dir, "Pano", "<!DOCTYPE html><p>canlı</p>")
    try:
        for route in (f"artifact/{meta['id']}/", f"artifact/{meta['id']}"):
            with urllib.request.urlopen(server.url + route, timeout=5) as response:
                assert "text/html" in response.headers["Content-Type"]
                assert "canlı" in response.read().decode("utf-8")
    finally:
        server.stop()
        log.close()


def test_artifact_download_sends_attachment_header(tmp_path: Path, mind: Mind) -> None:
    """?download=1 → Content-Disposition; HTML standart dışa aktarma."""
    server, log, config = _server(tmp_path, mind)
    meta = artifacts.publish(config.state_dir, "Günlük Özet", "<!DOCTYPE html><p>x</p>")
    try:
        with urllib.request.urlopen(
            server.url + f"artifact/{meta['id']}/?download=1", timeout=5
        ) as response:
            disp = response.headers.get("Content-Disposition") or ""
            assert "attachment" in disp
            assert ".html" in disp
            # HTTP header latin-1: tüm satır encode edilebilmeli; UTF-8 ad filename*'da.
            disp.encode("latin-1")
            assert "filename*=UTF-8''" in disp
            assert "x" in response.read().decode("utf-8")
    finally:
        server.stop()
        log.close()


def test_escape_attempts_get_a_404(tmp_path: Path, mind: Mind) -> None:
    """Yol istekten geliyor; depo dışına çıkma denemesi diske dokunmadan 404."""
    server, log, config = _server(tmp_path, mind)
    (config.state_dir / "config.json").write_text("{}", encoding="utf-8")
    try:
        for route in ("artifact/../config.json", "artifact/..%2fconfig.json",
                      "artifact/a/b/", "artifact/yok-abcd/", "artifact/"):
            with pytest.raises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(server.url + route, timeout=5)
            assert caught.value.code == 404, route
    finally:
        server.stop()
        log.close()


def test_gallery_endpoints_list_and_remove(tmp_path: Path, mind: Mind) -> None:
    server, log, config = _server(tmp_path, mind)
    meta = artifacts.publish(config.state_dir, "Pano", "<p>x</p>")
    try:
        with urllib.request.urlopen(server.url + "api/artifacts", timeout=5) as response:
            rows = json.loads(response.read().decode("utf-8"))["artifacts"]
        assert [m["id"] for m in rows] == [meta["id"]]

        request = urllib.request.Request(
            server.url + "api/artifacts",
            data=json.dumps({"action": "remove", "id": meta["id"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            answer = json.loads(response.read().decode("utf-8"))
        assert answer["ok"] and answer["artifacts"] == []
    finally:
        server.stop()
        log.close()


def test_artifact_notes_reach_the_stream(tmp_path: Path) -> None:
    """Kart olayı SSE'ye taşınmalı: not günlüğe düşer, hub yayınlar."""
    from dornick.events import Event, utcnow
    from dornick.web.server import _payload

    note = Event(seq=0, ts=utcnow(), kind="meta", content="artifact",
                 meta={"id": "pano-1a2b", "title": "Pano", "surum": 2,
                       "action": "update", "address": "/artifact/pano-1a2b/"})
    payload = _payload(note)
    assert payload is not None
    assert payload["type"] == "artifact"
    assert payload["id"] == "pano-1a2b" and payload["surum"] == 2
