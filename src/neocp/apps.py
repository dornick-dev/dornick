"""Uygulamalar: ajanın ürettiği şeyleri çalıştırılabilir kılan katman.

Ajan atölyede bir pano kuruyor, bir betik yazıyor, bir masaüstü aracı
yapıyor — ama bunlar dosya olarak kalınca kullanıcı için bir dosya
gezgininden farkı olmuyor. Bu modül atölyeyi **uygulama kataloğu** olarak
okuyor: her şeyi hiyerarşik bir ağaç olarak veriyor, her dosyayı türüne
göre sınıflıyor (web sitesi mi, çalıştırılabilir betik mi, belge mi) ve
başlığını çıkarıyor. Arayüz bunu bir panelde gösterip tıklanınca açıyor:
web olan uygulamanın içinde bir çerçevede, çalışan bir betik kendi
süreci olarak.

İki kaynak birlikte: **kendiliğinden sınıflama** (uzantı + içerik) çoğu
şeyi çözüyor; ajan daha fazlasını söylemek isterse bir `app.json`
manifesti bırakabiliyor (ad, tür, giriş dosyası, çalıştırma komutu, adres).
Manifest varsa o kazanıyor — ajan "bu bir web uygulaması, şu portta" diye
kendi söyleyebiliyor.

Güvenlik: çalıştırma **yalnızca atölyenin içindeki** dosyalarda serbest.
Ajanın kendi ürettiği şey; kullanıcının dosyalarını buradan başlatmıyoruz.
"""

from __future__ import annotations

import json
import re
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Taramada atlanan gürültü. Bunları göstermek katalogu kullanılmaz yapıyor.
SKIP = {"__pycache__", ".git", ".venv", "node_modules", ".idea", ".vscode"}
# neo'nun kendi altyapı klasörleri atölyede duruyor ama PROJE değil: bir "araç
# çalıştır" kartı olarak göstermek paneli kirletiyor (kullanıcı: "dosya yığını
# değil, proje"). yetenekler=beceriler, gelen=posta kutusu, gorseller=görseller,
# cihazlar=cihaz kayıtları.
INTERNAL = {"yetenekler", "gelen", "gorseller", "görseller", "cihazlar"}
# Bir uygulama OLMAYAN dosyalar: derleme artığı, ofis/ikili belge, geçici/kilit.
# Bunlar kart olarak görünmüyor (atölye klasöründen doğrudan erişilebilir).
SKIP_SUFFIX = {".pyc", ".pyo", ".log.migrated", ".docx", ".doc", ".xlsx",
               ".xls", ".pptx", ".ppt", ".tmp", ".bak", ".lock", ".swp"}

# Katalog derinliği. Sonsuz derin bir ağaç hem yavaş hem okunmaz; atölyede
# proje başına bir alt klasör bekleniyor, bu yeterli.
MAX_DEPTH = 5

# Uzantı → uygulama türü.
#   web   tarayıcıda/çerçevede açılan sayfa
#   run   çalıştırılabilir: betik, masaüstü aracı, komut dosyası
#   doc   okunan şey: veri, rapor, günlük
#
# Atölye tek dilli değil: ajan Python kadar Node, PHP, .NET, Java da
# üretebiliyor. Çalıştırıcı makinede yoksa launch açık bir hatayla söylüyor.
WEB = {".html", ".htm"}
RUN = {".py", ".pyw", ".ps1", ".bat", ".cmd", ".exe", ".sh",
       ".js", ".mjs", ".cjs", ".php", ".rb", ".jar"}
DOC = {".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml",
       ".toml", ".xml", ".svg"}

# Manifest dosyasının adı. Varsa klasör tek bir uygulama sayılıyor.
MANIFEST = "app.json"

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_NAME = re.compile(r"""^\s*NAME\s*=\s*["'](.+?)["']""", re.MULTILINE)
_DESC = re.compile(r"""^\s*DESCRIPTION\s*=\s*["'](.+?)["']""", re.MULTILINE)


@dataclass(slots=True)
class App:
    """Katalogdaki bir düğüm: klasör ya da dosya."""

    name: str                       # ekranda görünen ad
    path: str                       # atölyeye göreli yol (posix)
    type: str                       # folder | web | run | doc
    title: str = ""                 # dosyadan çıkarılan başlık
    run: str = ""                   # çalıştırma komutu (run türü için)
    url: str = ""                   # web uygulamasının adresi (manifest verirse)
    children: list["App"] = field(default_factory=list)


@dataclass(slots=True)
class Project:
    """Atölyedeki bir PROJE — dosya değil, bir iş birimi.

    neo bir şey ürettiğinde (Modbus web client gibi) ortaya bir klasör
    çıkıyor: backend, frontend, README. Kullanıcı için asıl birim bu proje;
    tek tek dosyalar değil. Panel bunları kart olarak gösteriyor, tıklanınca
    "nasıl çalıştırılır" + Çalıştır beliriyor.
    """

    name: str
    path: str                 # atölyeye göreli (klasör ya da tek dosya)
    scope: str = ""           # "in-app" | "external" | "" (neo sormalı)
    kind: str = "tool"        # web | service | tool | doc
    entry: str = ""           # açılış dosyası (web: index.html)
    run: str = ""             # çalıştırma komutu
    url: str = ""             # manifest verirse canlı adres
    desc: str = ""            # tek cümle: bu uygulama NE YAPAR (kart üstünde)
    howto: str = ""           # README / nasıl çalıştırılır (kısa)
    single: bool = False      # tek dosyalık mı (klasör değil)


def projects(sandbox_root: Path, base: Path | None = None) -> list[dict[str, Any]]:
    """Atölyeyi PROJE birimlerine çevirir (dosya ağacı değil).

    Üst düzeydeki her klasör bir proje; manifest (app.json) varsa onu, yoksa
    sezgiyi kullanıyor (web mi servis mi, giriş dosyası, README). Üst düzeydeki
    tek dosyalar da (bir pano.html gibi) kendi başına birer proje.
    """
    root = sandbox_root.resolve()
    ref = (base or root).resolve()
    if not root.is_dir():
        return []

    out: list[Project] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return []

    for path in entries:
        # Gizli, iç altyapı, ya da geçici/kilit dosyaları (~$Word.docx, ~yedek)
        # projelerin arasında görünmesin.
        if path.name in SKIP or path.name.startswith(".") or path.name.startswith("~"):
            continue
        if path.is_dir():
            if path.name in INTERNAL:
                continue
            out.append(_project_from_folder(path, ref))
        elif path.is_file() and path.suffix.lower() not in SKIP_SUFFIX and path.name != MANIFEST:
            out.append(_project_from_file(path, ref))

    return [asdict(p) for p in out]


def _project_from_folder(folder: Path, root: Path) -> Project:
    manifest = _manifest_data(folder)
    kind, entry, run = _detect(folder)
    howto = _read_howto(folder)

    if manifest:
        scope = _scope(manifest.get("scope"))
        entry_rel = str(manifest.get("entry") or entry or "")
        return Project(
            name=str(manifest.get("name") or folder.name),
            path=_rel(folder, root),
            scope=scope,
            kind=str(manifest.get("type") or manifest.get("kind") or kind),
            entry=_rel(folder / entry_rel, root) if entry_rel else "",
            run=str(manifest.get("run") or run),
            url=str(manifest.get("url") or ""),
            desc=str(manifest.get("desc") or "") or _first_line(howto),
            howto=str(manifest.get("howto") or howto),
        )

    return Project(
        name=folder.name,
        path=_rel(folder, root),
        scope="",                        # manifest yok → neo kapsamı sormalı
        kind=kind,
        entry=_rel(folder / entry, root) if entry else "",
        run=run,
        desc=_first_line(howto),
        howto=howto,
    )


def _project_from_file(path: Path, root: Path) -> Project:
    suffix = path.suffix.lower()
    if suffix in WEB:
        title = _html_title(path)
        return Project(name=path.name, path=_rel(path, root), kind="web",
                       entry=_rel(path, root), scope="in-app", single=True,
                       desc=_first_line(title), howto=title)
    if suffix in RUN:
        title = _script_title(path)
        return Project(name=path.name, path=_rel(path, root), kind="tool",
                       entry=_rel(path, root), run=_run_line(path), single=True,
                       desc=_first_line(title), howto=title)
    return Project(name=path.name, path=_rel(path, root), kind="doc",
                   entry=_rel(path, root), single=True)


def _first_line(text: str, limit: int = 110) -> str:
    """Kart üstünde görünen tek cümlelik özet: metnin ilk anlamlı satırı.

    Başlık işaretleri (#) soyuluyor; uzunsa kırpılıyor. "Çalıştır'a bastım ama
    bu uygulama NE YAPIYOR bilmiyorum" sorusunun cevabı bu satır.
    """
    for line in str(text or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line if len(line) <= limit else line[: limit - 1] + "…"
    return ""


def _manifest_data(folder: Path) -> dict[str, Any] | None:
    path = folder / MANIFEST
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _scope(value: Any) -> str:
    v = str(value or "").lower().replace("_", "-")
    if v in ("in-app", "internal", "sistem-ici", "sistem-içi", "içeride", "iceride"):
        return "in-app"
    if v in ("external", "dis", "dış", "dis-proje"):
        return "external"
    return ""


def _detect(folder: Path) -> tuple[str, str, str]:
    """Klasörün türünü, giriş dosyasını ve çalıştırma komutunu sezer.

    web  bir index.html varsa (çerçevede açılır)
    service  bir sunucu betiği varsa (app.py / main.py / server.py, Node
             sunucusu, package.json betiği, .NET projesi)
    tool  başka bir çalıştırılabilir betik

    Sezgi asgari tutuluyor: ajan daha iyisini biliyorsa `app.json`
    manifestiyle söylüyor ve manifest her zaman kazanıyor.
    """
    index = _find(folder, ("index.html", "index.htm"))
    server = _find(folder, ("app.py", "main.py", "server.py", "run.py",
                            "server.js", "app.js", "index.js", "main.js",
                            "index.php"))
    run = _package_run(folder) or (_run_line(server) if server else "")
    if not run:
        # .NET projesi: giriş dosyası değil proje dosyası çalıştırılıyor.
        csproj = _find(folder, None, {".csproj"})
        if csproj:
            return "service", _rel(csproj, folder), "dotnet run"
    if index and (server or run):
        # Hem sunucu hem sayfa: web uygulaması, sunucudan besleniyor.
        return "web", _rel(index, folder), run
    if index:
        return "web", _rel(index, folder), ""
    if server or run:
        entry = _rel(server, folder) if server else ""
        return "service", entry, run
    any_run = _find(folder, None, RUN)
    if any_run:
        return "tool", _rel(any_run, folder), _run_line(any_run)
    # index.html yok ama HTML var: en yenisi giriş. neo sayfaya çoğu zaman
    # kendi adını veriyor ("kuyu-depo.html") ve klasör girişsiz kalınca
    # Aç düğmesi sessizce hiçbir şey yapmıyordu.
    page = _newest(folder, WEB)
    if page:
        return "web", _rel(page, folder), ""
    return "doc", "", ""


def _package_run(folder: Path) -> str:
    """package.json varsa çalıştırma komutu: start ya da dev betiği.

    Node projesinin nasıl başlatıldığını en iyi kendi manifesti biliyor;
    tek tek dosya sezmeye çalışmaktan daha doğru.
    """
    path = folder / "package.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return ""
    if "start" in scripts:
        return "npm start"
    if "dev" in scripts:
        return "npm run dev"
    main = str(data.get("main") or "").strip()
    return f"node {main}" if main else ""


def _newest(folder: Path, suffixes: set[str]) -> Path | None:
    """Klasördeki (birkaç düzey) en yeni eşleşen dosya."""
    best: Path | None = None
    best_t = -1.0
    try:
        for path in folder.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix.lower() not in suffixes:
                continue
            t = path.stat().st_mtime
            if t > best_t:
                best, best_t = path, t
    except OSError:
        return None
    return best


def _find(folder: Path, names: tuple[str, ...] | None, suffixes: set[str] | None = None) -> Path | None:
    """Klasörde (birkaç düzey) ilk eşleşen dosya."""
    try:
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.name in SKIP or "__pycache__" in path.parts:
                continue
            if names and path.name.lower() in names:
                return path
            if suffixes and path.suffix.lower() in suffixes:
                return path
    except OSError:
        return None
    return None


def _read_howto(folder: Path) -> str:
    """README'nin ilk kısmı — "nasıl çalıştırılır" için."""
    for name in ("README.md", "README.txt", "readme.md", "OKU.md", "KULLANIM.md"):
        path = folder / name
        if path.is_file():
            return _head(path, 2000).strip()
    return ""


def catalog(sandbox_root: Path, base: Path | None = None) -> App:
    """Atölyeyi hiyerarşik uygulama ağacına çevirir.

    Kök her zaman bir klasör düğümü; altında dosyalar ve alt klasörler.
    Boş klasörler de görünüyor — ajan bir proje için klasör açıp henüz
    içini doldurmadıysa o da bir durum.

    `base` yolların neye göre verileceğini belirliyor. Arayüzün dosya okuma
    ucu (`/api/files`) çalışma alanına göre çözüyor; o yüzden sunucu base'i
    çalışma alanı veriyor ki bir web uygulaması tıklanınca gerçekten açılsın.
    Verilmezse atölyenin kendisi — testler bu sade hali kullanıyor.
    """
    root = sandbox_root
    ref = (base or root).resolve()
    node = App(name=root.name or "atolye", path=_rel(root, ref), type="folder")
    if root.is_dir():
        node.children = _scan(root, ref, 0)
    return node


def _scan(folder: Path, root: Path, depth: int) -> list[App]:
    if depth >= MAX_DEPTH:
        return []
    out: list[App] = []
    try:
        entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return []

    for path in entries:
        if path.name in SKIP or path.name.startswith("."):
            continue
        if path.is_dir():
            # Manifestli klasör tek bir uygulama: içini ayrı ayrı listelemek
            # yerine ajanın tarif ettiği uygulamayı gösteriyoruz.
            manifest = _manifest(path, root)
            if manifest is not None:
                out.append(manifest)
                continue
            node = App(name=path.name, path=_rel(path, root), type="folder")
            node.children = _scan(path, root, depth + 1)
            out.append(node)
        elif path.is_file():
            if path.suffix.lower() in SKIP_SUFFIX or path.name == MANIFEST:
                continue
            app = _file(path, root)
            if app is not None:
                out.append(app)
    return out


def _file(path: Path, root: Path) -> App | None:
    suffix = path.suffix.lower()
    if suffix in WEB:
        return App(name=path.name, path=_rel(path, root), type="web",
                   title=_html_title(path))
    if suffix in RUN:
        return App(name=path.name, path=_rel(path, root), type="run",
                   title=_script_title(path), run=_run_line(path))
    if suffix in DOC:
        return App(name=path.name, path=_rel(path, root), type="doc")
    # Tanınmayan uzantı da belge sayılıyor: görüntüleyici kaynak olarak açar.
    return App(name=path.name, path=_rel(path, root), type="doc")


def _manifest(folder: Path, root: Path) -> App | None:
    """`app.json` varsa klasörü tek bir uygulama olarak okur.

    Ajanın kendi tarifi kendiliğinden sınıflamayı geçersiz kılıyor: "bu bir
    web uygulaması, girişi site/index.html, şu adreste çalışıyor" diyebilsin.
    Bozuk bir manifest klasörü düşürmüyor — None dönüp normal tarama sürüyor.
    """
    path = folder / MANIFEST
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    kind = str(data.get("type") or "").lower()
    kind = kind if kind in ("web", "run", "doc") else "run"
    entry = str(data.get("entry") or "").strip()
    entry_path = (folder / entry) if entry else folder
    return App(
        name=str(data.get("name") or folder.name),
        path=_rel(entry_path, root),
        type=kind,
        title=str(data.get("description") or ""),
        run=str(data.get("run") or (_run_line(entry_path) if kind == "run" else "")),
        url=str(data.get("url") or ""),
    )


# -- başlık çıkarımı ----------------------------------------------------


def _html_title(path: Path) -> str:
    head = _head(path, 4000)
    match = _TITLE.search(head)
    return _clean(match.group(1)) if match else ""


def _script_title(path: Path) -> str:
    head = _head(path, 2000)
    # Yetenek dosyası NAME/DESCRIPTION taşıyor; sıradan betik bir docstring.
    if (m := _DESC.search(head)):
        return _clean(m.group(1))
    if (m := _NAME.search(head)):
        return _clean(m.group(1))
    return _docstring(head)


def _docstring(head: str) -> str:
    stripped = head.lstrip()
    for quote in ('"""', "'''"):
        if stripped.startswith(quote):
            end = stripped.find(quote, 3)
            body = stripped[3:end if end > 0 else None]
            return _clean(next((ln for ln in body.splitlines() if ln.strip()), ""))
    # Docstring yoksa ilk anlamlı YORUM satırı: neo'nun (ve insanların) yazdığı
    # betikler çoğu zaman "# Şunu yapar" ile başlıyor — kart özeti oradan.
    for line in stripped.splitlines()[:12]:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#!") or "coding" in line[:24]:
            continue   # shebang / kodlama bildirimi özet değil
        if line.startswith(("#", "//", "<#")):
            text = line.lstrip("#/<").strip()
            if len(text) > 3:
                return _clean(text)
            continue
        break   # koda geldik: özet yorumu yokmuş
    return ""


def _run_line(path: Path) -> str:
    """Bu dosyayı çalıştıran komutun okunur hali (arayüzde gösteriliyor)."""
    suffix = path.suffix.lower()
    if suffix in (".py", ".pyw"):
        return f"python {path.name}"
    if suffix == ".ps1":
        return f"powershell {path.name}"
    if suffix in (".bat", ".cmd", ".exe"):
        return path.name
    if suffix == ".sh":
        return f"bash {path.name}"
    if suffix in (".js", ".mjs", ".cjs"):
        return f"node {path.name}"
    if suffix == ".php":
        return f"php {path.name}"
    if suffix == ".rb":
        return f"ruby {path.name}"
    if suffix == ".jar":
        return f"java -jar {path.name}"
    return path.name


# -- çalıştırma ---------------------------------------------------------


# Başlatılan süreçler: PID → kayıt. Arayüz "çalışıyor" durumunu, canlı
# adresi ve durdurmayı buradan okuyor. `os.startfile` ile açılanlar (exe/bat)
# tutamaç vermediğinden izlenemiyor; yalnızca Popen ile başlayanlar burada.
_PROCS: dict[int, dict[str, Any]] = {}


def launch(sandbox_root: Path, rel_path: str, base: Path | None = None) -> dict[str, Any]:
    """Atölyedeki bir betiği/aracı/projeyi kendi süreci olarak başlatır.

    Yol atölyenin içinde olmalı: ajanın kendi ürettiği şey çalıştırılıyor,
    kullanıcının dosyaları değil. `base` yolun neye göre çözüleceği (katalog
    ile aynı); sınır her hâlde atölye. Süreç ayrılıyor (detached) — arayüz
    onu beklemiyor, başlattığını bildiriyor. İzlenebilenler `_PROCS`'a
    kaydediliyor ki sonradan durum/adres/durdurma mümkün olsun.

    Yol bir KLASÖRSE proje olarak başlar: manifestin (app.json) `run`
    komutu, yoksa sezilen komut, projenin kendi klasöründe çalıştırılır.
    Böylece `npm start`, `dotnet run` gibi çok adımlı çalıştırmalar da
    tek düğmeyle başlıyor — yalnızca Python betikleri değil.
    """
    root = sandbox_root.resolve()
    ref = (base or root).resolve()
    target = (ref / rel_path).resolve()
    if target != root and root not in target.parents:
        return {"ok": False, "error": "Atölye dışı: yalnızca kendi ürettiğin çalıştırılır."}

    # Aynı şey zaten çalışıyorsa ikincisini başlatma: kullanıcı "Çalıştır"a
    # iki kez basınca iki sunucunun aynı portu kapışması değil, çalışanın
    # gösterilmesi bekleniyor.
    for pid, info in _PROCS.items():
        if info.get("path") == rel_path and info["proc"].poll() is None:
            return {"ok": True, "pid": pid, "path": rel_path,
                    "already": True, "note": "Zaten çalışıyor."}

    if target.is_dir():
        manifest = _manifest_data(target)
        run_cmd = str((manifest or {}).get("run") or "").strip()
        kind, entry, detected = _detect(target)
        run_cmd = run_cmd or detected
        entry_path = (target / entry).resolve() if entry else None

        # Komut basit bir "yorumlayıcı + dosya" ise dosyayı KENDİMİZ
        # başlatıyoruz: manifest `run` satırı çoğu zaman insana yazılmış
        # ("py app.py  (127.0.0.1:5006)" gibi açıklamalı) ve kabuğa verilince
        # patlıyor. `npm start`, `dotnet run` gibi araç-zinciri komutları
        # kabuktan çalışıyor — onların betik dosyası yok.
        script = _script_of(run_cmd, target)
        if script is None and entry_path is not None and entry_path.is_file() \
                and entry_path.suffix.lower() in RUN:
            script = entry_path
        if script is not None:
            target = script
        elif run_cmd:
            try:
                proc = _spawn_command(run_cmd, target)
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            _PROCS[proc.pid] = {"proc": proc, "path": rel_path, "name": target.name,
                                "started": time.time(), "run": run_cmd}
            return {"ok": True, "run": run_cmd, "path": rel_path, "pid": proc.pid}
        else:
            return {"ok": False,
                    "error": "Çalıştırma komutu bulunamadı: app.json'a "
                             "bir `run` satırı ekletebilirsin (neo'ya sor)."}

    if not target.is_file():
        return {"ok": False, "error": f"Dosya yok: {rel_path}"}

    try:
        proc = _spawn(target)
    except Exception as exc:  # başlatma hatası arayüzü düşürmemeli
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    pid = getattr(proc, "pid", None)
    if proc is not None and pid is not None:
        _PROCS[pid] = {"proc": proc, "path": rel_path, "name": target.name,
                       "started": time.time()}
    return {"ok": True, "run": _run_line(target), "path": rel_path, "pid": pid}


def running() -> list[dict[str, Any]]:
    """Hâlâ çalışan, izlenebilen uygulamalar — canlı adresleriyle.

    Ölmüş süreçler ayıklanıyor. Adres (bir web sunucusu bağladıysa) netstat
    ile PID → dinlenen port eşleştirilerek bulunuyor; port henüz bağlanmadıysa
    boş döner ve sonraki yoklamada belirir.
    """
    out: list[dict[str, Any]] = []
    dead: list[int] = []
    # Süreç ağacı ve dinlenen portlar bir KEZ toplanıyor: her süreç için ayrı
    # ayrı sorgulamak yoklamayı ağırlaştırırdı.
    parents = _proc_parents()
    listen = _listening_ports()
    for pid, info in list(_PROCS.items()):
        proc = info["proc"]
        if proc.poll() is not None:   # bitmiş
            dead.append(pid)
            continue
        out.append({
            "pid": pid,
            "path": info["path"],
            "name": info["name"],
            "address": _address(pid, parents, listen),
            "started": info.get("started", 0),
            "run": info.get("run", ""),
        })
    for pid in dead:
        _PROCS.pop(pid, None)
    return out


def stop(pid: int) -> dict[str, Any]:
    """İzlenen bir süreci AĞACIYLA durdurur.

    Kayıtlı pid çoğu zaman bir sarmalayıcı (py başlatıcısı, PowerShell);
    `terminate()` yalnız onu öldürüyor, asıl sunucu torun süreç olarak
    yaşamaya devam ediyordu — kullanıcı "durdur diyorum, durmuyor" yaşıyordu
    (adres çözümündeki ağaç meselesinin ikizi). Windows'ta taskkill /T tüm
    ağacı indiriyor."""
    info = _PROCS.get(pid)
    if info is None:
        return {"ok": False, "error": "Bu süreç izlenmiyor ya da zaten bitmiş."}
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        else:
            info["proc"].terminate()
        # Öldü mü gerçekten? "Durdurdum" deyip çalışır bırakmak, kullanıcının
        # "durdur diyorum durmuyor" şikâyetinin ta kendisi. Kısa bir bekleme
        # ile doğrulanıyor; hâlâ yaşıyorsa dürüstçe hata dönülüyor.
        try:
            info["proc"].wait(timeout=3)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Süreç durdurulamadı — hâlâ çalışıyor. "
                                          "Tekrar dene ya da neo'ya söyle."}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    _PROCS.pop(pid, None)
    return {"ok": True, "pid": pid}


def open_path(sandbox_root: Path, rel_path: str, base: Path | None = None) -> dict[str, Any]:
    """Atölyedeki bir dosyayı/sayfayı SİSTEM DIŞINDA açar (varsayılan uygulama).

    Web sayfası için bu, kullanıcının gerçek tarayıcısı demek: kendi başına
    yeten (server istemeyen) bir sayfa `file://` olarak dosyadan açılır ve
    tam çalışır. Sunucu isteyen uygulamanın adresi ise zaten Çalışıyor
    bölümünden/kapsülden açılıyor — bu yol statikler için.
    """
    root = sandbox_root.resolve()
    ref = (base or root).resolve()
    target = (ref / rel_path).resolve()
    if target != root and root not in target.parents:
        return {"ok": False, "error": "Atölye dışı: yalnızca atölyedekiler açılır."}
    if not target.exists():
        return {"ok": False, "error": f"Yok: {rel_path}"}
    # Yalnızca tarayıcının işi olanlar: bir .docx'i "tarayıcıda aç" diye
    # Word'e fırlatmak yanlış beklenti kurar — o dosyalar zaten kendi
    # uygulamasında açılmak isteniyorsa ayrı bir yol.
    if target.suffix.lower() not in {".html", ".htm", ".svg"}:
        return {"ok": False, "error": "Bu bir web sayfası değil; tarayıcıda açılmaz."}
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
    except Exception as exc:
        return {"ok": False, "error": f"Açılamadı: {type(exc).__name__}: {exc}"}
    return {"ok": True, "opened": str(target)}


def remove(sandbox_root: Path, rel_path: str, base: Path | None = None) -> dict[str, Any]:
    """Bir projeyi atölyeden kaldırır — kalıcı silmez, geri-dönüşüme taşır.

    Kullanıcı panelden silebilmeli; ama tek tıkla bir projeyi kalıcı yok
    etmek tehlikeli. Proje `atolye/.geri-donusum/<zaman>-<ad>` altına
    taşınıyor: listeden düşer (nokta ile başlayan klasörler zaten
    atlanıyor), ama yanlışlıkla silinen şey elle geri alınabilir.
    """
    import shutil
    import time as _time

    root = sandbox_root.resolve()
    ref = (base or root).resolve()
    target = (ref / rel_path).resolve()
    if target == root or root not in target.parents:
        return {"ok": False, "error": "Atölye dışı: yalnızca atölyedekiler silinir."}
    if not target.exists():
        return {"ok": False, "error": f"Yok: {rel_path}"}

    bin_dir = root / ".geri-donusum"
    try:
        bin_dir.mkdir(exist_ok=True)
        stamp = _time.strftime("%Y%m%d-%H%M%S")
        dest = bin_dir / f"{stamp}-{target.name}"
        shutil.move(str(target), str(dest))
    except Exception as exc:
        # Çalışan bir süreç dosyayı kilitlemiş olabilir — açıkça söyle.
        return {"ok": False, "error": f"Taşınamadı ({type(exc).__name__}): önce durdurmayı dene."}
    return {"ok": True, "moved_to": str(dest.relative_to(root))}


def _address(
    pid: int,
    parents: dict[int, int] | None = None,
    listen: dict[int, list[int]] | None = None,
) -> str:
    """Sürecin (ya da TORUNLARININ) dinlediği yerel adres. Yoksa boş.

    Neden torunlar: başlattığımız süreç çoğu zaman bir sarmalayıcı — PowerShell
    (`shell` arka planı), `py` başlatıcısı, `npm`/`cmd`. Gerçek dinleyen soket
    bir çocuk/torun sürecin. Yalnızca tam pid'i aramak (eski hal) bu durumların
    HİÇBİRİNDE adresi bulamıyordu; kapsül de bu yüzden boş kalıyordu. Artık
    pid + tüm torunları içinde en küçük LISTENING portu seçiliyor.
    """
    if parents is None:
        parents = _proc_parents()
    if listen is None:
        listen = _listening_ports()
    family = _descendants(pid, parents)
    best: int | None = None
    for owner, ports in listen.items():
        if owner not in family:
            continue
        for port in ports:
            best = port if best is None else min(best, port)
    return f"http://localhost:{best}" if best else ""


def _proc_parents() -> dict[int, int]:
    """pid → ppid haritası. Süreç ağacında torunları bulmak için."""
    out: dict[int, int] = {}
    try:
        if sys.platform == "win32":
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | "
                 "Select-Object ProcessId,ParentProcessId | "
                 "ConvertTo-Csv -NoTypeInformation"],
                capture_output=True, text=True, timeout=5,
            )
            for line in res.stdout.splitlines()[1:]:
                parts = [p.strip().strip('"') for p in line.split(",")]
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    out[int(parts[0])] = int(parts[1])
        else:
            import os
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                try:
                    with open(f"/proc/{entry}/stat") as fh:
                        fields = fh.read().split()
                    out[int(entry)] = int(fields[3])
                except Exception:
                    continue
    except Exception:
        pass
    return out


def _descendants(pid: int, parents: dict[int, int]) -> set[int]:
    """pid ve tüm torunları."""
    family = {pid}
    changed = True
    while changed:
        changed = False
        for child, parent in parents.items():
            if parent in family and child not in family:
                family.add(child)
                changed = True
    return family


def _listening_ports() -> dict[int, list[int]]:
    """pid → LISTENING portları (netstat bir kez)."""
    out: dict[int, list[int]] = {}
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"] if sys.platform == "win32"
            else ["netstat", "-tlnp"],
            capture_output=True, text=True, timeout=3,
        )
    except Exception:
        return out
    for line in proc.stdout.splitlines():
        parts = line.split()
        if sys.platform == "win32":
            # Proto  Local  Foreign  State  PID
            if len(parts) < 5 or parts[3].upper() != "LISTENING":
                continue
            owner, local = parts[-1], parts[1]
        else:
            # Proto Recv Send Local Foreign State PID/Program
            if "LISTEN" not in line or "/" not in parts[-1]:
                continue
            owner, local = parts[-1].split("/", 1)[0], (parts[3] if len(parts) > 3 else "")
        port = local.rsplit(":", 1)[-1]
        if owner.isdigit() and port.isdigit():
            out.setdefault(int(owner), []).append(int(port))
    return out


def _spawn(target: Path):
    suffix = target.suffix.lower()
    cwd = str(target.parent)

    if suffix in (".bat", ".cmd", ".exe") or (suffix == "" and sys.platform == "win32"):
        # Kendi başına çalışabilen dosya: doğrudan başlat. Tutamaç yok, bu
        # yüzden izlenemez (durum/durdurma bunlara uygulanmıyor).
        import os
        os.startfile(str(target))  # type: ignore[attr-defined]
        return None

    if suffix == ".ps1":
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(target)]
    elif suffix == ".sh":
        cmd = ["bash", str(target)]
    elif suffix in (".js", ".mjs", ".cjs"):
        cmd = [_runtime("node"), str(target)]
    elif suffix == ".php":
        cmd = [_runtime("php"), str(target)]
    elif suffix == ".rb":
        cmd = [_runtime("ruby"), str(target)]
    elif suffix == ".jar":
        cmd = [_runtime("java"), "-jar", str(target)]
    elif suffix == ".pyw":
        cmd = [_python(windowless=True), str(target)]
    else:  # .py ve gerisi
        cmd = [_python(), str(target)]

    # Yeni konsol: betiğin çıktısı kendi penceresinde görünsün, arayüzün
    # süreciyle karışmasın. GUI/pencereli araçlar zaten konsol açmıyor.
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return subprocess.Popen(cmd, cwd=cwd, creationflags=flags)


# Doğrudan dosya başlatmayla birebir aynı işi yapan yorumlayıcılar. Bu
# listedeki bir komutun betik dosyasını kendimiz başlatıyoruz; kabuk (ve
# komut satırındaki olası açıklama artıkları) devreden çıkıyor.
_SIMPLE_RUNNERS = {"py", "python", "python3", "pythonw", "powershell", "pwsh",
                   "bash", "sh", "node", "php", "ruby"}


def _script_of(run_cmd: str, folder: Path) -> Path | None:
    """Komut basit bir "yorumlayıcı + betik" ise betiğin yolunu verir.

    "py app.py  (127.0.0.1:5006)" → app.py. "npm start" → None (araç
    zinciri, kabuktan çalışmalı). "python -m http.server" → None (dosya yok).
    """
    tokens = run_cmd.split()
    if not tokens or tokens[0].lower() not in _SIMPLE_RUNNERS:
        return None
    for token in tokens[1:]:
        candidate = folder / token
        try:
            if candidate.is_file() and candidate.suffix.lower() in RUN:
                return candidate.resolve()
        except OSError:
            continue
    return None


def _spawn_command(command: str, cwd: Path) -> "subprocess.Popen":
    """Bir çalıştırma KOMUTUNU (npm start, dotnet run) proje klasöründe başlatır.

    Kabuktan geçiyor çünkü komutlar araç zinciri (npm → node) kuruyor; süreç
    defterine sarmalayıcının pid'i düşse de adres çözümü ve durdurma zaten
    süreç AĞACINA bakıyor.
    """
    if sys.platform == "win32":
        import shutil as _shutil
        exe = _shutil.which("pwsh") or _shutil.which("powershell") or "powershell.exe"
        cmd = [exe, "-NoProfile", "-Command", command]
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    else:
        cmd = ["/bin/sh", "-lc", command]
        flags = 0
    return subprocess.Popen(cmd, cwd=str(cwd), creationflags=flags)


def _runtime(name: str) -> str:
    """Çalıştırıcıyı bulur; yoksa NE KURULACAĞINI söyleyen bir hata atar."""
    import shutil as _shutil

    found = _shutil.which(name)
    if not found:
        raise FileNotFoundError(
            f"'{name}' bu makinede kurulu değil ya da PATH'te yok. "
            f"Kurulumu neo'dan isteyebilirsin."
        )
    return found


def _python(windowless: bool = False) -> str:
    runner = Path(sys.executable)
    if windowless:
        quiet = runner.with_name("pythonw.exe")
        if quiet.exists():
            return str(quiet)
    return str(runner)


# -- yardımcılar --------------------------------------------------------


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return path.name


def _head(path: Path, limit: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _clean(text: str) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= 120 else flat[:120] + "…"


def to_dict(app: App) -> dict[str, Any]:
    """API'ye giden biçim. Boş alanlar da gidiyor; arayüz varlığına bakıyor."""
    return asdict(app)
