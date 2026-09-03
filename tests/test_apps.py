"""App catalogue: turns the workshop into a runnable tree.

Two rules: every node must be classified by kind (web/run/doc) and running
must not step outside the workshop — the agent's own product runs, not the
user's files.
"""

from __future__ import annotations

from pathlib import Path

from dornick import apps


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
    """With app.json the folder is a single app; the agent describes it itself."""
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
    # The insides of a manifest-bearing folder are not listed separately: the app is a single node.
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


# -- running-process tracking ----------------------------------------------


def test_launch_tracks_process_and_stop_ends_it(tmp_path: Path) -> None:
    """A launched trackable process shows in `running`, `stop` ends it."""
    script = tmp_path / "bekle.py"
    # Not short-lived: it must live a while so state/stop can be tried.
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")

    res = apps.launch(tmp_path, "bekle.py")
    assert res["ok"]
    pid = res["pid"]
    assert isinstance(pid, int)

    running = apps.running()
    assert any(p["pid"] == pid and p["name"] == "bekle.py" for p in running)

    stopped = apps.stop(pid)
    assert stopped["ok"]
    # The stopped process is no longer listed.
    assert all(p["pid"] != pid for p in apps.running())


def test_stop_unknown_pid_is_reported(tmp_path: Path) -> None:
    res = apps.stop(2_000_000_001)
    assert not res["ok"]


def test_projects_are_units_not_loose_files(tmp_path: Path) -> None:
    """A project (folder) is a single unit; intuition finds kind/entry/README."""
    proj = tmp_path / "modbus-web-client"
    (proj / "backend").mkdir(parents=True)
    (proj / "backend" / "app.py").write_text("# flask", encoding="utf-8")
    (proj / "index.html").write_text("<title>Modbus</title>", encoding="utf-8")
    (proj / "README.md").write_text("# Modbus\npip install flask\npython backend/app.py",
                                    encoding="utf-8")
    (tmp_path / "pano.html").write_text("<title>Pano</title>", encoding="utf-8")

    items = {p["name"]: p for p in apps.projects(tmp_path)}

    mb = items["modbus-web-client"]
    assert mb["kind"] == "web"                     # index.html + server → web
    assert mb["entry"].endswith("index.html")
    assert "app.py" in mb["run"]                   # fed from the server
    assert "pip install" in mb["howto"]            # README captured
    assert mb["scope"] == ""                       # no manifest → dornick should ask

    pano = items["pano.html"]
    assert pano["kind"] == "web" and pano["single"] is True
    assert pano["scope"] == "in-app"               # a single page opens in the frame


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


# -- discovery hardening -----------------------------------------------------
#
# What happened in the user's workshop: the model wrote the manifest in the
# WRONG places (the workshop root, folder-less as "llm-donanim-app.json"),
# the app in the right place was running but did not show in the panel and
# nothing warned anyone. The tests below lock down those three flaws.


def test_root_manifest_is_not_an_app_and_warns(tmp_path: Path) -> None:
    """`app.json` at the workshop root is not an app — the workshop is not an app."""
    (tmp_path / "app.json").write_text(
        '{"name": "Market Lens", "type": "web", "entry": "borsa/static/index.html"}',
        encoding="utf-8",
    )
    (tmp_path / "pano.html").write_text("<title>Pano</title>", encoding="utf-8")

    data = apps.katalog(tmp_path)
    names = {p["name"] for p in data["projects"]}
    assert "Market Lens" not in names        # the root manifest did not become a card
    assert "app.json" not in names           # nor did it leak in as a file
    assert "pano.html" in names              # the rest is discovered normally

    assert len(data["sorunlar"]) == 1
    problem = data["sorunlar"][0]
    assert problem["path"] == "app.json"
    assert "manifest uygulamanın kendi klasöründe olmalı" in problem["uyari"]
    # The warning teaches: where, relative to what, with an example.
    assert "app.json" in problem["ogretici"] and "entry" in problem["ogretici"]


def test_stray_manifest_at_root_is_ignored_too(tmp_path: Path) -> None:
    """Folder-less manifests like `llm-donanim-app.json` are not apps either."""
    (tmp_path / "llm-donanim-app.json").write_text(
        '{"name": "LLM Donanım", "entry": "site/llm-donanim.html"}', encoding="utf-8"
    )
    data = apps.katalog(tmp_path)
    assert data["projects"] == []
    assert [s["path"] for s in data["sorunlar"]] == ["llm-donanim-app.json"]


def test_discovery_descends_three_levels(tmp_path: Path) -> None:
    """The manifest need not be at the first level: found up to 3 levels down."""
    deep = tmp_path / "site" / "panolar" / "kuyu"
    deep.mkdir(parents=True)
    (deep / "index.html").write_text("<title>Kuyu</title>", encoding="utf-8")
    (deep / "app.json").write_text(
        '{"name": "Kuyu Panosu", "type": "web", "entry": "index.html", '
        '"scope": "in-app"}', encoding="utf-8"
    )
    items = {p["name"]: p for p in apps.projects(tmp_path)}
    assert "Kuyu Panosu" in items
    assert items["Kuyu Panosu"]["path"] == "site/panolar/kuyu"
    assert items["Kuyu Panosu"]["scope"] == "in-app"
    # The parent folder is only a container: the app is not repeated.
    assert "site" not in items


def test_discovery_does_not_enter_dependency_junk(tmp_path: Path) -> None:
    """Package manifests inside node_modules/vendor are not user apps."""
    package = tmp_path / "proje" / "node_modules" / "sol"
    package.mkdir(parents=True)
    (package / "app.json").write_text('{"name": "sol paketi"}', encoding="utf-8")
    (tmp_path / "proje" / "index.html").write_text("<title>P</title>", encoding="utf-8")

    names = {p["name"] for p in apps.projects(tmp_path)}
    assert "sol paketi" not in names
    assert "proje" in names     # no manifest found → the folder itself is the project


def test_invalid_entry_does_not_drop_the_app_but_marks_it_incomplete(tmp_path: Path) -> None:
    """A broken manifest does not drop from the list: "eksik" badge + REASON."""
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


def test_meaningless_run_command_is_marked_incomplete(tmp_path: Path) -> None:
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


def test_sound_manifest_is_not_incomplete(tmp_path: Path) -> None:
    """The exact form of the user's borsa-ara: valid, not incomplete."""
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
    assert p["scope"] == "in-app"                     # goes to the IN-APP section
    assert p["desc"] == "Piyasa nabzı"
    assert p["port"] == 8090                          # read from source


def test_running_process_is_matched_to_the_app(tmp_path: Path) -> None:
    """If the app's port is really listened on, the card becomes LIVE.

    An exact copy of the user's situation: the server is NOT in dornick's
    process ledger (running on its own, as a separate process) but the
    app's card must still look live. The proof is a socket, not a guess.
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

    # A separate process: pytest's OWN process counts as "dornick itself"
    # (and correctly gets no live badge) — the server must be outside.
    server = subprocess.Popen(
        [sys.executable, "-c",
         "import socket,time;s=socket.socket();"
         "s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
         f"s.bind(('127.0.0.1',{port}));s.listen(1);time.sleep(30)"],
    )
    try:
        for _ in range(50):        # wait for it to start listening
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
        assert p["pid"] == server.pid
        assert p["stoppable"] is True

        # The running list sees this app too (even though it is not in the ledger).
        live = {r["name"]: r for r in apps.running(tmp_path)}
        assert live["Pano"]["address"] == f"http://127.0.0.1:{port}"
        assert live["Pano"]["discovered"] is True
    finally:
        server.kill()
        server.wait(timeout=10)


def test_unlistened_port_does_not_show_live(tmp_path: Path) -> None:
    """Port declared but nobody listening: the app is STOPPED."""
    proj = tmp_path / "pano"
    proj.mkdir()
    (proj / "index.html").write_text("<title>x</title>", encoding="utf-8")
    (proj / "app.json").write_text(
        '{"name": "Pano", "type": "web", "entry": "index.html", "port": 65123}',
        encoding="utf-8",
    )
    p = {x["name"]: x for x in apps.projects(tmp_path)}["Pano"]
    assert p["address"] == "" and p["pid"] == 0


def test_empty_workshop(tmp_path: Path) -> None:
    data = apps.katalog(tmp_path)
    assert data == {"projects": [], "sorunlar": []}
    assert apps.katalog(tmp_path / "yok") == {"projects": [], "sorunlar": []}


def test_dornick_own_process_is_recognised() -> None:
    """If the model gets confused and starts dornick, this must be recognised."""
    assert apps.is_dornick_process("dornick --web 8873 -C D:\\Projects\\Fatih\\dornick")
    assert apps.is_dornick_process("python -m dornick --web 8080")
    assert apps.is_dornick_process(
        '"C:\\Py\\python.exe" "C:\\Py\\Scripts\\dornick.exe" --web 8873')
    assert apps.is_dornick_process(r'"C:\dornick\python\dornick.exe" -m dornick --app')
    # The user's app is not dornick — no false alarm.
    assert not apps.is_dornick_process("py app.py")
    assert not apps.is_dornick_process("python D:\\Projects\\Fatih\\dornick\\atolye\\borsa-ara\\app.py")


def test_dornick_own_copy_is_not_listed_as_an_app(tmp_path: Path) -> None:
    """If the model starts dornick the panel must not show it as "your app".

    What the user lived through: the model ran `dornick --web 8873`, the
    shell tool wrote it into the process ledger, and the panel listed a
    copy of dornick as an app ("what nonsense").
    """
    import subprocess
    import sys
    import time

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    apps._PROCS[proc.pid] = {
        "proc": proc, "path": "dornick --web 8873 -C D:\\Projects\\Fatih\\dornick",
        "name": "dornick", "started": time.time(),
    }
    try:
        row = next(r for r in apps.running() if r["pid"] == proc.pid)
        assert row["self"] is True
        assert row["stoppable"] is False
        assert row["name"] == "Dornick (kendisi)"
        # Cannot be stopped from the panel: dornick must not shoot its own leg.
        refused = apps.stop(proc.pid)
        assert not refused["ok"] and "kendi süreci" in refused["error"]
    finally:
        apps._PROCS.pop(proc.pid, None)
        proc.kill()
        proc.wait(timeout=10)


async def test_shell_refuses_to_restart_dornick(tmp_path: Path) -> None:
    """The shell tool turns down an attempt to start `dornick` WITH A REASON."""
    import asyncio

    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.tools import ToolContext, ToolRegistry
    from dornick.tools import shell as shell_tool

    reg = ToolRegistry()
    shell_tool.register(reg)
    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(config=config, session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
                      cancel=asyncio.Event())

    res = await reg.get("shell").handler({"command": "dornick --web 8873"}, ctx)
    assert res.is_error
    assert "kendini yeniden başlatma" in res.content
    # The user's own app is not blocked.
    ok = await reg.get("shell").handler({"command": "echo merhaba"}, ctx)
    assert not ok.is_error


def test_reveal_does_not_leave_the_workshop(tmp_path: Path) -> None:
    root = tmp_path / "atolye"
    root.mkdir()
    res = apps.reveal(root, "../gizli")
    assert not res["ok"]


def test_running_prunes_finished_processes(tmp_path: Path) -> None:
    """A process that ends on its own drops on the next poll."""
    script = tmp_path / "cik.py"
    script.write_text("pass\n", encoding="utf-8")
    res = apps.launch(tmp_path, "cik.py")
    pid = res["pid"]
    proc = apps._PROCS[pid]["proc"]
    proc.wait(timeout=10)          # wait for it to finish
    assert all(p["pid"] != pid for p in apps.running())


def test_winexe_csproj_is_desktop_not_tool(tmp_path: Path) -> None:
    """A WinExe .NET project is desktop, not a script — the ScadaStudio class."""
    proj = tmp_path / "ScadaStudio"
    proj.mkdir()
    (proj / "ScadaStudio.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        "  <PropertyGroup><OutputType>WinExe</OutputType>"
        "<TargetFramework>net8.0-windows</TargetFramework>"
        "<UseWindowsForms>true</UseWindowsForms></PropertyGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    # So bin noise does not pick the wrong exe.
    junk = proj / "bin" / "Debug" / "net8.0-windows"
    junk.mkdir(parents=True)
    (junk / "helper.exe").write_bytes(b"MZ")
    kind, entry, run = apps._detect(proj)
    assert kind == "desktop"
    assert entry.endswith(".csproj") or entry.endswith(".exe")
    assert "dotnet" in run or entry.endswith(".exe")


def test_folder_named_exe_is_desktop(tmp_path: Path) -> None:
    proj = tmp_path / "ScadaStudio Studio"
    proj.mkdir()
    (proj / "ScadaStudio Studio.exe").write_bytes(b"MZ")
    (proj / "readme.txt").write_text("x", encoding="utf-8")
    kind, entry, _run = apps._detect(proj)
    assert kind == "desktop"
    assert entry.endswith("ScadaStudio Studio.exe")


def test_manifest_tool_soft_corrects_to_desktop(tmp_path: Path) -> None:
    """Even if the agent writes type=tool a WinExe counts as desktop."""
    proj = tmp_path / "Studio"
    proj.mkdir()
    (proj / "Studio.csproj").write_text(
        "<Project Sdk=\"Microsoft.NET.Sdk\">"
        "<PropertyGroup><OutputType>WinExe</OutputType></PropertyGroup>"
        "</Project>\n",
        encoding="utf-8",
    )
    (proj / "app.json").write_text(
        '{"name": "Studio", "type": "tool", "scope": "external", "desc": "SCADA"}',
        encoding="utf-8",
    )
    p = apps._project_from_folder(proj, tmp_path)
    assert p.kind == "desktop"


def test_bin_obj_ignored_when_finding_scripts(tmp_path: Path) -> None:
    """A .py/.exe inside bin/obj does not count as the entry."""
    proj = tmp_path / "app"
    proj.mkdir()
    (proj / "bin").mkdir()
    (proj / "bin" / "noise.py").write_text("print(1)\n", encoding="utf-8")
    (proj / "main.py").write_text("print('ok')\n", encoding="utf-8")
    kind, entry, _ = apps._detect(proj)
    assert kind == "service"
    assert entry.endswith("main.py")
