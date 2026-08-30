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


# -- keşif sağlamlaştırma ---------------------------------------------------
#
# Kullanıcının atölyesinde yaşanan hal: model manifesti YANLIŞ yerlere yazdı
# (atölye köküne, klasörsüz "llm-donanim-app.json" diye), doğru yerdeki
# uygulama çalışıyordu ama panelde görünmüyordu ve hiçbir şey kimseyi
# uyarmıyordu. Aşağısı o üç kusuru kilitliyor.


def test_kok_manifest_uygulama_sayilmaz_ve_uyarir(tmp_path: Path) -> None:
    """Atölye kökündeki `app.json` bir uygulama değil — atölye uygulama değil."""
    (tmp_path / "app.json").write_text(
        '{"name": "Market Lens", "type": "web", "entry": "borsa/static/index.html"}',
        encoding="utf-8",
    )
    (tmp_path / "pano.html").write_text("<title>Pano</title>", encoding="utf-8")

    data = apps.katalog(tmp_path)
    adlar = {p["name"] for p in data["projects"]}
    assert "Market Lens" not in adlar        # kök manifest kart olmadı
    assert "app.json" not in adlar           # dosya olarak da sızmadı
    assert "pano.html" in adlar              # gerisi normal keşfediliyor

    assert len(data["sorunlar"]) == 1
    sorun = data["sorunlar"][0]
    assert sorun["path"] == "app.json"
    assert "manifest uygulamanın kendi klasöründe olmalı" in sorun["uyari"]
    # Uyarı öğretiyor: nereye, neye göreli, örneğiyle.
    assert "app.json" in sorun["ogretici"] and "entry" in sorun["ogretici"]


def test_kokteki_basibos_manifest_de_yok_sayilir(tmp_path: Path) -> None:
    """`llm-donanim-app.json` gibi klasörsüz manifestler de uygulama değil."""
    (tmp_path / "llm-donanim-app.json").write_text(
        '{"name": "LLM Donanım", "entry": "site/llm-donanim.html"}', encoding="utf-8"
    )
    data = apps.katalog(tmp_path)
    assert data["projects"] == []
    assert [s["path"] for s in data["sorunlar"]] == ["llm-donanim-app.json"]


def test_kesif_uc_seviye_derine_iner(tmp_path: Path) -> None:
    """Manifest ilk seviyede olmak zorunda değil: 3 seviyeye kadar bulunur."""
    derin = tmp_path / "site" / "panolar" / "kuyu"
    derin.mkdir(parents=True)
    (derin / "index.html").write_text("<title>Kuyu</title>", encoding="utf-8")
    (derin / "app.json").write_text(
        '{"name": "Kuyu Panosu", "type": "web", "entry": "index.html", '
        '"scope": "in-app"}', encoding="utf-8"
    )
    items = {p["name"]: p for p in apps.projects(tmp_path)}
    assert "Kuyu Panosu" in items
    assert items["Kuyu Panosu"]["path"] == "site/panolar/kuyu"
    assert items["Kuyu Panosu"]["scope"] == "in-app"
    # Üst klasör yalnızca bir kap: uygulama tekrarlanmıyor.
    assert "site" not in items


def test_kesif_bagimlilik_copluklerine_inmez(tmp_path: Path) -> None:
    """node_modules/vendor içindeki paket manifestleri kullanıcı uygulaması değil."""
    paket = tmp_path / "proje" / "node_modules" / "sol"
    paket.mkdir(parents=True)
    (paket / "app.json").write_text('{"name": "sol paketi"}', encoding="utf-8")
    (tmp_path / "proje" / "index.html").write_text("<title>P</title>", encoding="utf-8")

    adlar = {p["name"] for p in apps.projects(tmp_path)}
    assert "sol paketi" not in adlar
    assert "proje" in adlar     # manifest bulunmadı → klasörün kendisi proje


def test_gecersiz_entry_uygulamayi_dusurmez_eksik_gosterir(tmp_path: Path) -> None:
    """Bozuk manifest listeden düşmüyor: "eksik" rozeti + NEDEN."""
    proj = tmp_path / "llm-donanim"
    proj.mkdir()
    (proj / "llm-donanim.html").write_text("<title>x</title>", encoding="utf-8")
    (proj / "app.json").write_text(
        '{"name": "LLM Donanım", "type": "web", "entry": "site/llm-donanım.html"}',
        encoding="utf-8",
    )
    p = {x["name"]: x for x in apps.projects(tmp_path)}["LLM Donanım"]
    assert p["eksik"] is True
    assert p["neden"] == "entry bulunamadı: site/llm-donanım.html"


def test_anlamsiz_run_komutu_eksik_olarak_isaretlenir(tmp_path: Path) -> None:
    proj = tmp_path / "araç"
    proj.mkdir()
    (proj / "index.html").write_text("<title>x</title>", encoding="utf-8")
    (proj / "app.json").write_text(
        '{"name": "Araç", "entry": "index.html", "run": "birseyler-calistir --hemen"}',
        encoding="utf-8",
    )
    p = {x["name"]: x for x in apps.projects(tmp_path)}["Araç"]
    assert p["eksik"] is True
    assert "run komutu anlaşılmadı" in p["neden"]


def test_saglam_manifest_eksik_sayilmaz(tmp_path: Path) -> None:
    """Kullanıcının borsa-ara'sının birebir hali: geçerli, eksik değil."""
    proj = tmp_path / "borsa-ara"
    (proj / "static").mkdir(parents=True)
    (proj / "static" / "index.html").write_text("<title>Market</title>", encoding="utf-8")
    (proj / "app.py").write_text("app.run(host='127.0.0.1', port=8090)\n", encoding="utf-8")
    (proj / "app.json").write_text(
        '{"name": "Market Lens", "type": "web", "entry": "static/index.html", '
        '"run": "py app.py", "scope": "in-app", "desc": "Piyasa nabzı"}',
        encoding="utf-8",
    )
    p = {x["name"]: x for x in apps.projects(tmp_path)}["Market Lens"]
    assert p["eksik"] is False and p["neden"] == ""
    assert p["scope"] == "in-app"                     # SİSTEM İÇİ bölümüne gider
    assert p["desc"] == "Piyasa nabzı"
    assert p["port"] == 8090                          # kaynaktan okundu


def test_calisan_surec_uygulamaya_eslesir(tmp_path: Path) -> None:
    """Uygulamanın portu gerçekten dinleniyorsa kart CANLI olur.

    Kullanıcının halinin birebir kopyası: sunucu neo'nun süreç defterinde
    YOK (kendi başına, ayrı bir süreç olarak koşuyor) ama uygulamanın kartı
    yine de canlı görünmeli. Kanıt bir soket, tahmin değil.
    """
    import socket
    import subprocess
    import sys
    import time

    proj = tmp_path / "pano"
    proj.mkdir()
    (proj / "index.html").write_text("<title>x</title>", encoding="utf-8")

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    # Ayrı bir süreç: pytest'in KENDİ süreci "neo'nun kendisi" sayılıyor
    # (ve doğru olarak canlı rozeti almıyor) — sunucu dışarıda olmalı.
    sunucu = subprocess.Popen(
        [sys.executable, "-c",
         "import socket,time;s=socket.socket();"
         "s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
         f"s.bind(('127.0.0.1',{port}));s.listen(1);time.sleep(30)"],
    )
    try:
        for _ in range(50):        # dinlemeye başlamasını bekle
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

        (proj / "app.json").write_text(
            '{"name": "Pano", "type": "web", "entry": "index.html", '
            f'"run": "py app.py", "port": {port}}}', encoding="utf-8"
        )
        p = {x["name"]: x for x in apps.projects(tmp_path)}["Pano"]
        assert p["port"] == port
        assert p["address"] == f"http://127.0.0.1:{port}"
        assert p["pid"] == sunucu.pid
        assert p["stoppable"] is True

        # Çalışanlar listesi de bu uygulamayı görüyor (defterde olmasa bile).
        canli = {r["name"]: r for r in apps.running(tmp_path)}
        assert canli["Pano"]["address"] == f"http://127.0.0.1:{port}"
        assert canli["Pano"]["discovered"] is True
    finally:
        sunucu.kill()
        sunucu.wait(timeout=10)


def test_dinlenmeyen_port_canli_gostermez(tmp_path: Path) -> None:
    """Port ilan edilmiş ama kimse dinlemiyorsa uygulama DURDU."""
    proj = tmp_path / "pano"
    proj.mkdir()
    (proj / "index.html").write_text("<title>x</title>", encoding="utf-8")
    (proj / "app.json").write_text(
        '{"name": "Pano", "type": "web", "entry": "index.html", "port": 65123}',
        encoding="utf-8",
    )
    p = {x["name"]: x for x in apps.projects(tmp_path)}["Pano"]
    assert p["address"] == "" and p["pid"] == 0


def test_bos_atolye(tmp_path: Path) -> None:
    data = apps.katalog(tmp_path)
    assert data == {"projects": [], "sorunlar": []}
    assert apps.katalog(tmp_path / "yok") == {"projects": [], "sorunlar": []}


def test_neo_kendi_sureci_taninir() -> None:
    """Model kafası karışıp neo'yu başlatırsa bu tanınmalı."""
    assert apps.neo_sureci_mi("neocp --web 8873 -C D:\\Projects\\Fatih\\neocp")
    assert apps.neo_sureci_mi("python -m neocp --web 8080")
    assert apps.neo_sureci_mi(
        '"C:\\Py\\python.exe" "C:\\Py\\Scripts\\neocp.exe" --web 8873')
    assert apps.neo_sureci_mi(r'"C:\neo\python\neo.exe" -m neocp --app')
    # Kullanıcının uygulaması neo değil — yanlış alarm olmamalı.
    assert not apps.neo_sureci_mi("py app.py")
    assert not apps.neo_sureci_mi("python D:\\Projects\\Fatih\\neocp\\atolye\\borsa-ara\\app.py")


def test_neo_kendi_kopyasi_uygulama_gibi_listelenmez(tmp_path: Path) -> None:
    """Model neo'yu başlatırsa panel onu "uygulaman" diye göstermemeli.

    Kullanıcının yaşadığı hal: model `neocp --web 8873` çalıştırdı, kabuk
    aracı bunu süreç defterine yazdı, panel de neo'nun bir kopyasını
    uygulama olarak listeledi ("ne saçmaladı").
    """
    import subprocess
    import sys
    import time

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    apps._PROCS[proc.pid] = {
        "proc": proc, "path": "neocp --web 8873 -C D:\\Projects\\Fatih\\neocp",
        "name": "neocp", "started": time.time(),
    }
    try:
        row = next(r for r in apps.running() if r["pid"] == proc.pid)
        assert row["self"] is True
        assert row["stoppable"] is False
        assert row["name"] == "neo (kendisi)"
        # Panelden durdurulamaz: neo kendi bacağına sıkmasın.
        red = apps.stop(proc.pid)
        assert not red["ok"] and "kendi süreci" in red["error"]
    finally:
        apps._PROCS.pop(proc.pid, None)
        proc.kill()
        proc.wait(timeout=10)


async def test_shell_neo_yu_yeniden_baslatmayi_reddeder(tmp_path: Path) -> None:
    """Kabuk aracı `neocp` başlatma girişimini NEDENİYLE geri çevirir."""
    import asyncio

    from neocp.config import Config
    from neocp.events import EventLog
    from neocp.session import Session
    from neocp.tools import ToolContext, ToolRegistry
    from neocp.tools import shell as shell_tool

    reg = ToolRegistry()
    shell_tool.register(reg)
    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(config=config, session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
                      cancel=asyncio.Event())

    res = await reg.get("shell").handler({"command": "neocp --web 8873"}, ctx)
    assert res.is_error
    assert "kendini yeniden başlatma" in res.content
    # Kullanıcının kendi uygulaması engellenmiyor.
    ok = await reg.get("shell").handler({"command": "echo merhaba"}, ctx)
    assert not ok.is_error


def test_reveal_atolye_disina_cikmaz(tmp_path: Path) -> None:
    root = tmp_path / "atolye"
    root.mkdir()
    res = apps.reveal(root, "../gizli")
    assert not res["ok"]


def test_running_prunes_finished_processes(tmp_path: Path) -> None:
    """Kendiliğinden biten bir süreç bir sonraki yoklamada düşer."""
    script = tmp_path / "cik.py"
    script.write_text("pass\n", encoding="utf-8")
    res = apps.launch(tmp_path, "cik.py")
    pid = res["pid"]
    proc = apps._PROCS[pid]["proc"]
    proc.wait(timeout=10)          # bitmesini bekle
    assert all(p["pid"] != pid for p in apps.running())
