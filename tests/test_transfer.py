"""Taşınabilirlik: dornick'nun biriktirdiklerini bir makineden diğerine taşımak.

İki sözleşme: (1) dışa aktar→içe al gidiş-dönüşü anıları, bağları,
hedefleri, yetenekleri kaybetmeden taşıyor; (2) içe alma BİRLEŞTİRME —
üzerine yazmıyor: aynı anı iki kez girmiyor (idempotent), var olan kimlik
(ruh) ezilmiyor.
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

from dornick import recognition, transfer
from dornick.config import Config
from dornick.mind import open_mind


def _mind(root: Path):
    cfg = Config.load(root)
    cfg.ensure_dirs()
    mind = open_mind(cfg.mind_dir, cfg.sessions_dir, "cur")
    return cfg, mind


def test_export_then_import_carries_memories(tmp_path: Path) -> None:
    src_root = tmp_path / "makineA"
    dst_root = tmp_path / "makineB"

    cfg_a, mind_a = _mind(src_root)
    m1 = mind_a.remember("Çorum pompa verimi %72", kind="fact", title="pompa")
    m2 = mind_a.remember("Kuyu seviyesi alarmı 2.5m", kind="fact", title="alarm")
    mind_a.bridge(m1.id, m2.id, reason="aynı saha")
    # Bir yetenek dosyası (atölyede).
    skills = cfg_a.open_sandbox().root / "yetenekler"
    skills.mkdir(parents=True, exist_ok=True)
    (skills / "modbus.py").write_text("NAME='modbus'\n", encoding="utf-8")

    bundle = transfer.export_bundle(cfg_a, mind_a)
    assert isinstance(bundle, bytes) and len(bundle) > 0

    cfg_b, mind_b = _mind(dst_root)
    assert mind_b.store.count() == 0
    result = transfer.import_bundle(cfg_b, mind_b, bundle)

    assert result["ok"]
    assert result["memories"] == 2
    assert result["links"] >= 1
    assert result["skills"] == 1

    # Anılar gerçekten aranabilir olmalı (imza indeksi kuruldu).
    hits = mind_b.recall("pompa verimi")
    assert any("pompa" in h.item.title.lower() or "72" in h.item.content for h in hits)
    # Yetenek dosyası hedefte.
    assert (cfg_b.open_sandbox().root / "yetenekler" / "modbus.py").is_file()


def test_import_is_idempotent(tmp_path: Path) -> None:
    """Aynı paketi iki kez almak anıyı çoğaltmamalı."""
    cfg_a, mind_a = _mind(tmp_path / "A")
    mind_a.remember("tek bir anı", kind="fact")
    bundle = transfer.export_bundle(cfg_a, mind_a)

    cfg_b, mind_b = _mind(tmp_path / "B")
    first = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert first["memories"] == 1
    count_after_first = mind_b.store.count()

    second = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert second["memories"] == 0                 # yeni bir şey yok
    assert mind_b.store.count() == count_after_first  # çoğalmadı


def test_import_does_not_overwrite_existing_persona(tmp_path: Path) -> None:
    """Hedefin ruhu varsa gelen paket onu ezmemeli — kimlik korunur."""
    cfg_a, mind_a = _mind(tmp_path / "A")
    mind_a.remember("bir anı", kind="fact")
    persona_a = Path(cfg_a.workspace) / "persona.md"
    persona_a.write_text("Ben A'nın ruhuyum", encoding="utf-8")
    cfg_a.persona_path = persona_a
    bundle = transfer.export_bundle(cfg_a, mind_a)

    cfg_b, mind_b = _mind(tmp_path / "B")
    persona_b = Path(cfg_b.workspace) / "persona.md"
    persona_b.write_text("Ben B'nin ruhuyum", encoding="utf-8")
    cfg_b.persona_path = persona_b

    result = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert result["persona"] is False                       # dokunulmadı
    assert persona_b.read_text(encoding="utf-8") == "Ben B'nin ruhuyum"


def test_import_rejects_non_bundle(tmp_path: Path) -> None:
    cfg_b, mind_b = _mind(tmp_path / "B")
    result = transfer.import_bundle(cfg_b, mind_b, b"not a zip at all")
    assert not result["ok"]


# -- seçmeli parçalar ------------------------------------------------------


def _isimler(bundle: bytes) -> set[str]:
    return set(zipfile.ZipFile(io.BytesIO(bundle)).namelist())


def _sahte_duzenek(monkeypatch, root: Path) -> Path:
    """Eğitim düzeneğinin kişisel dosyalarını geçici bir yere taşır.

    Gerçek düzenek bu makinede kurulu; testin kullanıcının korpusuna
    dokunmaması (ve kurulu olmayan makinede de koşması) için yollar
    monkeypatch'leniyor — transfer/tanima onları çağrı anında okuyor.
    """
    veri = root / "duzenek" / "veri"
    veri.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(recognition, "KORPUS", veri / "kisisel_korpus.jsonl")
    monkeypatch.setattr(recognition, "WATERMARK", veri / "kisisel_durum.json")
    return veri


def test_selective_export_only_memories(tmp_path: Path, monkeypatch) -> None:
    """Yalnız-anılar paketi öteki parçalardan hiçbir şey taşımamalı."""
    _sahte_duzenek(monkeypatch, tmp_path)
    cfg, mind = _mind(tmp_path / "A")
    mind.remember("bir anı", kind="fact")
    (cfg.open_sandbox().root / "proje.py").write_text("print(1)\n", encoding="utf-8")

    names = _isimler(transfer.export_bundle(cfg, mind, ["anilar"]))
    assert "recall.db" in names
    assert not any(n.startswith(("tanima/", "projeler/", "ayarlar/")) for n in names)

    # Parametresiz istek de aynı (geriye uyumluluk).
    eski = _isimler(transfer.export_bundle(cfg, mind))
    assert eski == names


def test_export_never_contains_keys(tmp_path: Path, monkeypatch) -> None:
    """Anahtarlar hiçbir parçada arşive girmemeli — tam paket bile temiz.

    config.json'daki api_key_env de düşürülüyor: paketin içinde anahtara
    işaret eden tek bir bayt kalmamalı.
    """
    veri = _sahte_duzenek(monkeypatch, tmp_path)
    (veri / "kisisel_korpus.jsonl").write_text('{"girdi": "soru"}\n', encoding="utf-8")
    (veri / "kisisel_durum.json").write_text('{"son_created": "x"}', encoding="utf-8")

    cfg, mind = _mind(tmp_path / "A")
    mind.remember("bir anı", kind="fact")
    (cfg.state_dir / "keys.json").write_text(
        json.dumps({"OPENROUTER_API_KEY": "sk-or-v1-cokgizli"}), encoding="utf-8")
    (cfg.state_dir / "config.json").write_text(json.dumps({
        "model": {"name": "m", "base_url": "https://openrouter.ai/api/v1",
                  "api_key_env": "OPENROUTER_API_KEY"},
    }), encoding="utf-8")
    (cfg.state_dir / "taban.npz").write_bytes(b"NPZ")

    bundle = transfer.export_bundle(cfg, mind, list(transfer.PARCALAR))
    names = _isimler(bundle)
    assert "ayarlar/config.json" in names and "tanima/taban.npz" in names
    assert "keys.json" not in names and not any("keys" in n for n in names)
    assert b"OPENROUTER" not in bundle
    assert b"sk-or" not in bundle


def test_selective_import_respects_part_filter(tmp_path: Path, monkeypatch) -> None:
    """Arşivde anılar da olsa yalnız istenen parça işlenmeli."""
    veri = _sahte_duzenek(monkeypatch, tmp_path)
    (veri / "kisisel_korpus.jsonl").write_text('{"girdi": "soru"}\n', encoding="utf-8")
    cfg_a, mind_a = _mind(tmp_path / "A")
    mind_a.remember("taşınmaması gereken anı", kind="fact")
    (cfg_a.state_dir / "taban.npz").write_bytes(b"KISISEL-NPZ")
    bundle = transfer.export_bundle(cfg_a, mind_a, ["anilar", "tanima"])

    cfg_b, mind_b = _mind(tmp_path / "B")
    result = transfer.import_bundle(cfg_b, mind_b, bundle, ["tanima"])
    assert result["ok"]
    assert result["memories"] == 0 and mind_b.store.count() == 0
    assert (cfg_b.state_dir / "taban.npz").read_bytes() == b"KISISEL-NPZ"


def test_import_tanima_without_rig_keeps_personal_files(
        tmp_path: Path, monkeypatch) -> None:
    """Düzeneksiz makinede kişisel dosyalar kaybolmamalı: tanima_yedek'e."""
    veri = _sahte_duzenek(monkeypatch, tmp_path)
    (veri / "kisisel_korpus.jsonl").write_text('{"girdi": "soru"}\n', encoding="utf-8")
    (veri / "kisisel_durum.json").write_text('{"son_created": "x"}', encoding="utf-8")
    cfg_a, mind_a = _mind(tmp_path / "A")
    (cfg_a.state_dir / "taban.npz").write_bytes(b"NPZ")
    bundle = transfer.export_bundle(cfg_a, mind_a, ["tanima"])

    # Hedefte düzenek "kurulu değil": yol var olmayan bir klasörü gösteriyor.
    monkeypatch.setattr(recognition, "KORPUS", tmp_path / "yok" / "kisisel_korpus.jsonl")
    monkeypatch.setattr(recognition, "WATERMARK", tmp_path / "yok" / "kisisel_durum.json")
    cfg_b, mind_b = _mind(tmp_path / "B")
    result = transfer.import_bundle(cfg_b, mind_b, bundle, ["tanima"])
    assert result["ok"] and result["tanima"] == 3
    assert (cfg_b.state_dir / "taban.npz").is_file()
    assert (cfg_b.state_dir / "tanima_yedek" / "kisisel_korpus.jsonl").is_file()
    assert (cfg_b.state_dir / "tanima_yedek" / "kisisel_durum.json").is_file()


def test_roundtrip_projects_and_settings(tmp_path: Path, monkeypatch) -> None:
    """Atölye + ayarlar taşınıyor; ezilen mevcut hal yedeğe alınıyor."""
    _sahte_duzenek(monkeypatch, tmp_path)
    cfg_a, mind_a = _mind(tmp_path / "A")
    atolye_a = cfg_a.open_sandbox().root
    (atolye_a / "web").mkdir(parents=True, exist_ok=True)
    (atolye_a / "web" / "index.html").write_text("<b>site</b>", encoding="utf-8")
    (atolye_a / "node_modules").mkdir(exist_ok=True)
    (atolye_a / "node_modules" / "sisman.js").write_text("x", encoding="utf-8")
    (cfg_a.state_dir / "config.json").write_text(json.dumps({
        "model": {"name": "m", "base_url": "https://openrouter.ai/api/v1",
                  "api_key_env": "OPENROUTER_API_KEY"},
    }), encoding="utf-8")
    bundle = transfer.export_bundle(cfg_a, mind_a, ["projeler", "ayarlar"])
    names = _isimler(bundle)
    assert "projeler/web/index.html" in names
    assert not any("node_modules" in n for n in names)   # artıklar dışarıda

    cfg_b, mind_b = _mind(tmp_path / "B")
    (cfg_b.state_dir / "config.json").write_text('{"eski": true}', encoding="utf-8")
    result = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert result["ok"] and result["projeler"] == 1 and result["ayarlar"] == 1
    assert (cfg_b.open_sandbox().root / "web" / "index.html").read_text(
        encoding="utf-8") == "<b>site</b>"
    # api_key_env pakete girmedi ama içe alımda base_url'den geri türedi.
    geri = json.loads((cfg_b.state_dir / "config.json").read_text(encoding="utf-8"))
    assert geri["model"]["api_key_env"] == "OPENROUTER_API_KEY"
    # Ezilen eski config yedek klasöründe duruyor.
    yedek = Path(result["yedek"])
    assert (yedek / "ayarlar" / "config.json").read_text(encoding="utf-8") == '{"eski": true}'


# -- sıfırlama -------------------------------------------------------------


def test_reset_memories_backs_up_then_clears(tmp_path: Path) -> None:
    """Anı sıfırlama: önce tutarlı yedek, sonra boş zihin; hedefler kalır."""
    cfg, mind = _mind(tmp_path / "A")
    mind.remember("silinecek anı bir", kind="fact")
    mind.remember("silinecek anı iki", kind="fact")
    mind.push_goal("kalacak hedef")

    result = transfer.reset_memories(cfg, mind)
    assert result["ok"] and result["silinen"] == 2
    assert mind.store.count() == 0
    assert mind.recall("silinecek") == []
    assert [g.text for g in mind.goals()] == ["kalacak hedef"]   # hedef anı değil

    # Yedek gerçek bir bellek kopyası: iki kayıt içinde.
    kopya = Path(result["yedek"]) / "anilar" / "recall.db"
    con = sqlite3.connect(kopya)
    try:
        assert con.execute("SELECT COUNT(*) FROM node").fetchone()[0] == 2
    finally:
        con.close()


def test_tanima_reset_moves_files_and_falls_back(tmp_path: Path, monkeypatch) -> None:
    """Beni tanı sıfırlama: kişisel dosyalar yedeğe, önbellek düşer."""
    from dornick.recall import writer

    veri = _sahte_duzenek(monkeypatch, tmp_path)
    (veri / "kisisel_korpus.jsonl").write_text('{"girdi": "soru"}\n', encoding="utf-8")
    (veri / "kisisel_durum.json").write_text('{"son_created": "x"}', encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "taban.npz").write_bytes(b"KISISEL")

    result = recognition.reset(state)
    assert result["ok"] and sorted(result["tasinan"]) == [
        "kisisel_durum.json", "kisisel_korpus.jsonl", "taban.npz"]
    assert not (state / "taban.npz").exists()
    assert not (veri / "kisisel_korpus.jsonl").exists()
    yedek = Path(result["yedek"]) / "tanima"
    assert (yedek / "taban.npz").read_bytes() == b"KISISEL"
    assert (yedek / "kisisel_korpus.jsonl").is_file()
    # Önbellek düştü: bir sonraki zenginleştirme diski yeniden yoklayacak.
    assert writer._writer is None and writer._denendi is False

    # İkinci sıfırlama: taşınacak bir şey yok, yedek klasörü açılmaz.
    tekrar = recognition.reset(state)
    assert tekrar["ok"] and tekrar["tasinan"] == [] and tekrar["yedek"] == ""


def test_blank_target_adopts_persona(tmp_path: Path) -> None:
    """Hedefin ruhu boşsa gelen ruh benimseniyor — yeni bir dornick'ya taşınırken."""
    cfg_a, mind_a = _mind(tmp_path / "A")
    mind_a.remember("bir anı", kind="fact")
    persona_a = Path(cfg_a.workspace) / "persona.md"
    persona_a.write_text("taşınan ruh", encoding="utf-8")
    cfg_a.persona_path = persona_a
    bundle = transfer.export_bundle(cfg_a, mind_a)

    cfg_b, mind_b = _mind(tmp_path / "B")   # ruh yok
    result = transfer.import_bundle(cfg_b, mind_b, bundle)
    assert result["persona"] is True
    assert (Path(cfg_b.workspace) / "persona.md").read_text(encoding="utf-8") == "taşınan ruh"
