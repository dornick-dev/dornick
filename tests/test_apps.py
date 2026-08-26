"""Uygulama kataloğu: atölyeyi çalıştırılabilir bir ağaca çevirir.

İki kural: her düğüm türüne göre sınıflanmalı (web/çalıştır/belge) ve
çalıştırma atölyenin dışına çıkmamalı — ajanın kendi ürettiği çalışır,
kullanıcının dosyaları değil.
"""

from __future__ import annotations

from pathlib import Path

from neocp import apps


def _tree(root: Path) -> dict:
    return apps.to_dict(apps.catalog(root))


def _flatten(node: dict) -> dict[str, dict]:
    out = {node["path"]: node}
    for child in node.get("children", []):
        out.update(_flatten(child))
    return out


def test_empty_workshop_is_an_empty_root(tmp_path: Path) -> None:
    tree = _tree(tmp_path)
    assert tree["type"] == "folder"
    assert tree["children"] == []


def test_html_is_a_web_app_with_its_title(tmp_path: Path) -> None:
    (tmp_path / "pano.html").write_text(
        "<html><head><title>Kuyu Panosu</title></head><body>x</body></html>",
        encoding="utf-8",
    )
    node = _flatten(_tree(tmp_path))["pano.html"]
    assert node["type"] == "web"
    assert node["title"] == "Kuyu Panosu"


def test_python_is_runnable_with_a_run_line(tmp_path: Path) -> None:
    (tmp_path / "kaydedici.py").write_text(
        '"""Kuyu seviyesini 10 sn\'de bir kaydeder."""\nprint(1)\n', encoding="utf-8"
    )
    node = _flatten(_tree(tmp_path))["kaydedici.py"]
    assert node["type"] == "run"
    assert "kaydedici.py" in node["run"]
    assert "10 sn" in node["title"]


def test_data_files_are_documents(tmp_path: Path) -> None:
    (tmp_path / "olcumler.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    node = _flatten(_tree(tmp_path))["olcumler.csv"]
    assert node["type"] == "doc"


def test_folders_nest(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<title>Site</title>", encoding="utf-8")
    flat = _flatten(_tree(tmp_path))
    assert flat["site"]["type"] == "folder"
    assert "site/index.html" in flat


def test_manifest_makes_a_folder_one_app(tmp_path: Path) -> None:
    """app.json varsa klasör tek bir uygulama; ajan kendi tarif eder."""
    site = tmp_path / "dashboard"
    site.mkdir()
    (site / "index.html").write_text("<title>x</title>", encoding="utf-8")
    (site / "app.json").write_text(
        '{"name": "Kuyu Panosu", "type": "web", "entry": "index.html", '
        '"url": "http://127.0.0.1:8730", "description": "canlı seviye"}',
        encoding="utf-8",
    )
    flat = _flatten(_tree(tmp_path))
    node = flat["dashboard/index.html"]
    assert node["name"] == "Kuyu Panosu"
    assert node["type"] == "web"
    assert node["url"] == "http://127.0.0.1:8730"
    # Manifestli klasörün içi ayrıca listelenmiyor: uygulama tek düğüm.
    assert "dashboard" not in flat


def test_noise_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_text("junk", encoding="utf-8")
    (tmp_path / ".hidden").write_text("x", encoding="utf-8")
    tree = _tree(tmp_path)
    assert tree["children"] == []


def test_launch_refuses_outside_the_workshop(tmp_path: Path) -> None:
    root = tmp_path / "atolye"
    root.mkdir()
    outside = tmp_path / "gizli.py"
    outside.write_text("print(1)", encoding="utf-8")
    result = apps.launch(root, "../gizli.py")
    assert not result["ok"]
    assert "dışı" in result["error"].lower() or "atölye" in result["error"].lower()


def test_launch_reports_missing_file(tmp_path: Path) -> None:
    result = apps.launch(tmp_path, "yok.py")
    assert not result["ok"]


# -- çalışan süreç izleme --------------------------------------------------


def test_launch_tracks_process_and_stop_ends_it(tmp_path: Path) -> None:
    """Başlatılan izlenebilir bir süreç `running`'de görünür, `stop` bitirir."""
    script = tmp_path / "bekle.py"
    # Kısa ömürlü değil: durum/durdurmayı deneyebilmek için bir süre yaşamalı.
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")

    res = apps.launch(tmp_path, "bekle.py")
    assert res["ok"]
    pid = res["pid"]
    assert isinstance(pid, int)

    running = apps.running()
    assert any(p["pid"] == pid and p["name"] == "bekle.py" for p in running)

    stopped = apps.stop(pid)
    assert stopped["ok"]
    # Durdurulan süreç artık listelenmiyor.
    assert all(p["pid"] != pid for p in apps.running())


def test_stop_unknown_pid_is_reported(tmp_path: Path) -> None:
    res = apps.stop(2_000_000_001)
    assert not res["ok"]


def test_projects_are_units_not_loose_files(tmp_path: Path) -> None:
    """Bir proje (klasör) tek bir birim; sezgi türü/girişi/README'yi bulur."""
    proj = tmp_path / "modbus-web-client"
    (proj / "backend").mkdir(parents=True)
    (proj / "backend" / "app.py").write_text("# flask", encoding="utf-8")
    (proj / "index.html").write_text("<title>Modbus</title>", encoding="utf-8")
    (proj / "README.md").write_text("# Modbus\npip install flask\npython backend/app.py",
                                    encoding="utf-8")
    (tmp_path / "pano.html").write_text("<title>Pano</title>", encoding="utf-8")

    items = {p["name"]: p for p in apps.projects(tmp_path)}

    mb = items["modbus-web-client"]
    assert mb["kind"] == "web"                     # index.html + sunucu → web
    assert mb["entry"].endswith("index.html")
    assert "app.py" in mb["run"]                   # sunucudan besleniyor
    assert "pip install" in mb["howto"]            # README yakalandı
    assert mb["scope"] == ""                       # manifest yok → neo sormalı

    pano = items["pano.html"]
    assert pano["kind"] == "web" and pano["single"] is True
    assert pano["scope"] == "in-app"               # tek sayfa çerçevede açılır


def test_manifest_sets_project_scope_and_howto(tmp_path: Path) -> None:
    proj = tmp_path / "pano"
    proj.mkdir()
    (proj / "index.html").write_text("<title>x</title>", encoding="utf-8")
    (proj / "app.json").write_text(
        '{"name": "Kuyu Panosu", "type": "web", "scope": "in-app", '
        '"url": "http://127.0.0.1:8730", "howto": "Başlat düğmesine bas"}',
        encoding="utf-8",
    )
    p = {x["name"]: x for x in apps.projects(tmp_path)}["Kuyu Panosu"]
    assert p["scope"] == "in-app"
    assert p["url"] == "http://127.0.0.1:8730"
    assert p["howto"] == "Başlat düğmesine bas"


def test_running_prunes_finished_processes(tmp_path: Path) -> None:
    """Kendiliğinden biten bir süreç bir sonraki yoklamada düşer."""
    script = tmp_path / "cik.py"
    script.write_text("pass\n", encoding="utf-8")
    res = apps.launch(tmp_path, "cik.py")
    pid = res["pid"]
    proc = apps._PROCS[pid]["proc"]
    proc.wait(timeout=10)          # bitmesini bekle
    assert all(p["pid"] != pid for p in apps.running())
