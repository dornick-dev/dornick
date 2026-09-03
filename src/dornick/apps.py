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

from . import environment

# Taramada atlanan gürültü. Bunları göstermek katalogu kullanılmaz yapıyor.
SKIP = {"__pycache__", ".git", ".venv", "node_modules", ".idea", ".vscode"}
# Dornick'in kendi altyapı klasörleri atölyede duruyor ama PROJE değil: bir "araç
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

# Keşif kaç seviye iner. Bir uygulama atölyenin dibinde de olabiliyor
# (`site/panolar/kuyu/app.json`); tek seviye bakmak onu görünmez yapıyordu.
# Üç seviye insan eliyle kurulan her yerleşimi yakalıyor, daha derini
# kütüphane/derleme çöplüğü oluyor.
PROJE_DERINLIK = 3

# Derin keşifte hiç inilmeyen klasörler: bağımlılık/derleme/çöp. Bunların
# içindeki bir `app.json` kullanıcının uygulaması değil, bir paketin kendi
# manifesti — kart olarak göstermek katalogu kirletiyor.
KESIF_ATLA = SKIP | {"vendor", "dist", "build", "site-packages", ".geri-donusum",
                     "bower_components", "target", "obj", "bin"}

# Manifest yanlış yere yazıldığında ya da doğrulama düştüğünde MODELE dönen
# metin. Kural değil TARİF veriyor: nereye, neye göreli, örneğiyle. Model bu
# cümleyi okuyup manifesti doğru yere taşıyabilsin diye tek yerde duruyor.
MANIFEST_OGRETICI = (
    "Uygulama manifesti uygulamanın KENDİ klasöründe `app.json` olmalı; "
    "`entry` o klasöre göreli. Örnek: atolye/borsa-ara/app.json → "
    '{"entry": "static/index.html", "run": "py app.py"}'
)

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

    dornick bir şey ürettiğinde (Modbus web client gibi) ortaya bir klasör
    çıkıyor: backend, frontend, README. Kullanıcı için asıl birim bu proje;
    tek tek dosyalar değil. Panel bunları kart olarak gösteriyor, tıklanınca
    "nasıl çalıştırılır" + Çalıştır beliriyor.
    """

    name: str
    path: str                 # atölyeye göreli (klasör ya da tek dosya)
    scope: str = ""           # "in-app" | "external" | "" (dornick sormalı)
    kind: str = "tool"        # web | service | tool | doc
    entry: str = ""           # açılış dosyası (web: index.html)
    run: str = ""             # çalıştırma komutu
    url: str = ""             # manifest verirse canlı adres
    desc: str = ""            # tek cümle: bu uygulama NE YAPAR (kart üstünde)
    howto: str = ""           # README / nasıl çalıştırılır (kısa)
    single: bool = False      # tek dosyalık mı (klasör değil)
    # Doğrulama: manifest bir şey vaat edip tutmuyorsa uygulama listeden
    # DÜŞMÜYOR — "eksik" rozetiyle ve NEDENİYLE duruyor. Sessizce kaybolmak
    # ("uygulamamı yaptım ama panelde yok") tam da düzeltilen kusurdu.
    eksik: bool = False
    neden: str = ""
    # Canlı durum: bu uygulamaya ait çalışan bir süreç var mı.
    pid: int = 0
    address: str = ""         # "http://127.0.0.1:8090"
    port: int = 0             # tespit edilen/ilan edilen port
    stoppable: bool = False   # panelden durdurulabilir mi (Dornick'in kendisi değil)


def projects(sandbox_root: Path, base: Path | None = None) -> list[dict[str, Any]]:
    """Atölyeyi PROJE birimlerine çevirir (dosya ağacı değil).

    Geriye dönük yüzey: yalnız proje listesi. Başıboş manifest uyarılarını da
    isteyen çağıran `katalog()` kullanıyor.
    """
    return katalog(sandbox_root, base)["projects"]


def katalog(sandbox_root: Path, base: Path | None = None,
            canli: bool = True) -> dict[str, Any]:
    """Atölyenin uygulama kataloğu: projeler + manifest sorunları.

    Bir uygulama = içinde `app.json` olan bir KLASÖR (en fazla
    `PROJE_DERINLIK` seviye derinde) ya da kendi başına yeten bir dosya
    (bir pano.html, bir betik). Manifesti olmayan üst düzey klasörler de
    sezgiyle proje sayılıyor — atölye manifest yazmadan da kullanılabilmeli.

    Atölye KÖKÜNDEKİ manifestler uygulama DEĞİL: atölye bir uygulama değil,
    uygulamaların yaşadığı yer. Kökteki `app.json` ya da `llm-donanim-app.json`
    gibi başıboş dosyalar yok sayılıyor ve `sorunlar` altında NEDENİYLE
    bildiriliyor — model manifesti yanlış yere yazdığında sessizlik değil,
    öğretici bir uyarı alıyor.
    """
    root = sandbox_root.resolve()
    ref = (base or root).resolve()
    if not root.is_dir():
        return {"projects": [], "sorunlar": []}

    sorunlar = _basibos_manifestler(root)
    basibos = {s["path"] for s in sorunlar}

    out: list[Project] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return {"projects": [], "sorunlar": sorunlar}

    for path in entries:
        # Gizli, iç altyapı, ya da geçici/kilit dosyaları (~$Word.docx, ~yedek)
        # projelerin arasında görünmesin.
        if path.name in SKIP or path.name.startswith(".") or path.name.startswith("~"):
            continue
        if path.is_dir():
            if path.name in INTERNAL or path.name in KESIF_ATLA:
                continue
            out.extend(_klasor_projeleri(path, ref))
        elif path.is_file() and path.suffix.lower() not in SKIP_SUFFIX \
                and path.name != MANIFEST and path.name not in basibos:
            out.append(_project_from_file(path, ref))

    if canli:
        _canli_isaretle(out, root, ref)
    return {"projects": [asdict(p) for p in out], "sorunlar": sorunlar}


def _basibos_manifestler(root: Path) -> list[dict[str, str]]:
    """Atölye KÖKÜNDE duran, bir uygulamaya ait olmayan manifestler.

    İki hal: (1) `atolye/app.json` — atölyenin tamamını tek uygulama gibi
    tarif ediyor; (2) `atolye/llm-donanim-app.json` — klasörsüz, uydurma
    adlı bir manifest. İkisi de keşfe girmiyor; kullanıcıya ve modele tek
    satır uyarı + `MANIFEST_OGRETICI` dönüyor.
    """
    out: list[dict[str, str]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return out
    for path in entries:
        if not path.is_file():
            continue
        ad = path.name
        if ad != MANIFEST and not ad.lower().endswith("-app.json"):
            continue
        out.append({
            "path": ad,
            "uyari": f"atolye/{ad} geçersiz — manifest uygulamanın kendi "
                     "klasöründe olmalı",
            "ogretici": MANIFEST_OGRETICI,
        })
    return out


def _klasor_projeleri(folder: Path, ref: Path) -> list[Project]:
    """Bir üst düzey klasörden çıkan proje(ler).

    Kendi manifesti varsa: tek proje, o. Yoksa altında (en fazla
    `PROJE_DERINLIK` seviye) manifestli klasörler aranıyor; bulunursa asıl
    uygulamalar ONLAR — üst klasör yalnızca bir kap, kart olarak
    tekrarlanmıyor. Hiç manifest yoksa eski davranış: klasörün kendisi
    sezgiyle bir proje.
    """
    if (folder / MANIFEST).is_file():
        return [_project_from_folder(folder, ref)]
    ic = _manifestli_klasorler(folder, PROJE_DERINLIK - 1)
    if ic:
        return [_project_from_folder(p, ref) for p in ic]
    return [_project_from_folder(folder, ref)]


def _manifestli_klasorler(folder: Path, kalan: int) -> list[Path]:
    """`folder` altında manifest taşıyan klasörler (en fazla `kalan` seviye)."""
    if kalan <= 0:
        return []
    out: list[Path] = []
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return out
    for path in entries:
        if not path.is_dir() or path.name.startswith(".") or path.name in KESIF_ATLA:
            continue
        if (path / MANIFEST).is_file():
            out.append(path)          # manifestli klasörün İÇİNE inilmiyor
            continue
        out.extend(_manifestli_klasorler(path, kalan - 1))
    return out


def _project_from_folder(folder: Path, root: Path) -> Project:
    manifest = _manifest_data(folder)
    kind, entry, run = _detect(folder)
    howto = _read_howto(folder)

    if manifest:
        scope = _scope(manifest.get("scope"))
        entry_rel = str(manifest.get("entry") or entry or "")
        run_cmd = str(manifest.get("run") or run)
        # Ajan GUI/.NET uygulamasını sıkça `tool` yazar → UI "betik" der.
        # Diskteki gerçek WinExe/masüstü sezgisi kazanır.
        mkind = str(manifest.get("type") or manifest.get("kind") or kind)
        if kind == "desktop" and mkind in ("tool", "service", "betik", "script"):
            mkind = "desktop"
            if not run_cmd.strip() and run:
                run_cmd = run
            if not entry_rel and entry:
                entry_rel = entry
        neden = _dogrula(folder, entry_rel, run_cmd)
        return Project(
            name=str(manifest.get("name") or folder.name),
            path=_rel(folder, root),
            scope=scope,
            kind=mkind,
            entry=_rel(folder / entry_rel, root) if entry_rel else "",
            run=run_cmd,
            url=str(manifest.get("url") or ""),
            desc=str(manifest.get("desc") or "") or _first_line(howto),
            howto=str(manifest.get("howto") or howto),
            eksik=bool(neden),
            neden=neden,
            port=_port_ipucu(folder, manifest, entry_rel),
        )

    return Project(
        name=folder.name,
        path=_rel(folder, root),
        scope="",                        # manifest yok → dornick kapsamı sormalı
        kind=kind,
        entry=_rel(folder / entry, root) if entry else "",
        run=run,
        desc=_first_line(howto),
        howto=howto,
        port=_port_ipucu(folder, None, entry),
    )


def _dogrula(folder: Path, entry_rel: str, run_cmd: str) -> str:
    """Manifest vaadini tutuyor mu? Tutmuyorsa NEDENİ (yoksa boş metin).

    Uygulama listeden düşmüyor — "eksik" rozetiyle nedeniyle duruyor. Yanlış
    yazılmış bir `entry` ("site/llm-donanım.html" ama dosya `llm-donanim.html")
    eskiden sessizce boş bir Aç düğmesi oluyordu; artık nedeni kartta yazıyor.
    """
    if entry_rel:
        try:
            if not (folder / entry_rel).exists():
                return f"entry bulunamadı: {entry_rel}"
        except OSError:
            return f"entry okunamadı: {entry_rel}"
    if run_cmd.strip() and not _komut_anlamli(run_cmd, folder):
        return f"run komutu anlaşılmadı: {run_cmd.strip()}"
    if not entry_rel and not run_cmd.strip():
        return "ne `entry` ne `run` var — uygulama nasıl açılacağı belirsiz"
    return ""


# Bir çalıştırma komutunun ilk kelimesi olarak anlamlı sayılan araçlar.
# Liste temkinli: tanımadığımız bir komut, PATH'te varsa ya da klasörde bir
# dosyaya karşılık geliyorsa yine geçerli sayılıyor — amaç yanlış alarm değil,
# apaçık bozuk komutu ("bir şeyler çalıştır") yakalamak.
_BILINEN_KOMUTLAR = {"npm", "npx", "yarn", "pnpm", "dotnet", "java", "make",
                     "cargo", "go", "deno", "bun", "flask", "uvicorn",
                     "gunicorn", "streamlit", "rails", "composer"}


def _komut_anlamli(run_cmd: str, folder: Path) -> bool:
    import shutil as _shutil

    tokens = run_cmd.split()
    if not tokens:
        return False
    head = tokens[0].lower().removesuffix(".exe")
    if head in _SIMPLE_RUNNERS or head in _BILINEN_KOMUTLAR:
        return True
    try:
        if (folder / tokens[0]).exists():
            return True
    except OSError:
        pass
    return bool(_shutil.which(tokens[0]))


# Kaynak/metin içinde ilan edilmiş port. Sırayla denenen kalıplar; hepsi
# "port" kelimesine ya da bir adrese bağlı — çıplak sayı yakalanmıyor
# (bir sürüm numarasını port sanmak yanlış canlı rozeti doğururdu).
_PORT_KALIPLARI = (
    re.compile(r"""port\s*[=:]\s*["']?(\d{4,5})""", re.IGNORECASE),
    re.compile(r"""--port[\s=]+(\d{4,5})"""),
    re.compile(r"""\.listen\(\s*(\d{4,5})"""),
    re.compile(r"""(?:localhost|127\.0\.0\.1|0\.0\.0\.0)[:/](\d{4,5})"""),
)


def _port_ipucu(folder: Path, manifest: dict[str, Any] | None, entry_rel: str) -> int:
    """Bu uygulamanın hangi portta yaşadığı — ilan edilmiş ya da kaynakta yazılı.

    Sıra: manifestteki `port`/`url`, sonra `run`/`howto` metni, en son giriş
    ya da sunucu dosyasının kaynağı (`app.run(..., port=8090)`). Canlı rozeti
    bu portun gerçekten DİNLENİYOR olmasına bakıyor; tahmin değil kanıt.
    """
    if manifest:
        try:
            acik = int(str(manifest.get("port") or "").strip() or 0)
            if 1 <= acik <= 65535:
                return acik
        except ValueError:
            pass
        for alan in ("url", "run", "howto", "desc"):
            bulunan = _porttan(str(manifest.get(alan) or ""))
            if bulunan:
                return bulunan

    adaylar: list[Path] = []
    if entry_rel:
        adaylar.append(folder / entry_rel)
    for ad in ("app.py", "main.py", "server.py", "run.py",
               "server.js", "app.js", "index.js", "main.js"):
        adaylar.append(folder / ad)
    for aday in adaylar:
        try:
            if not aday.is_file() or aday.suffix.lower() not in RUN:
                continue
        except OSError:
            continue
        bulunan = _porttan(_head(aday, 20000))
        if bulunan:
            return bulunan
    return 0


def _porttan(text: str) -> int:
    for kalip in _PORT_KALIPLARI:
        match = kalip.search(text or "")
        if match:
            deger = int(match.group(1))
            if 1024 <= deger <= 65535:
                return deger
    return 0


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


def _atlanan_yol(path: Path) -> bool:
    """Derleme/bağımlılık çöplüğü — giriş dosyası buradan seçilmez."""
    return any(part in KESIF_ATLA or part == "__pycache__" for part in path.parts)


def _csproj_masaustu(csproj: Path) -> bool:
    """WinExe / WinForms / WPF — konsol servisi değil masaüstü uygulama."""
    try:
        text = csproj.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(imza in text for imza in (
        "WinExe", "UseWindowsForms", "UseWPF",
        "Microsoft.NET.Sdk.WindowsDesktop",
    ))


def _desktop_exe(folder: Path) -> Path | None:
    """Klasördeki asıl GUI .exe — bin/obj gürültüsünden değil, tercihen kök.

    ScadaStudio gibi .NET WinExe projelerde 'Başlat' çoğu zaman yanlış
    betiğe veya sessiz bir sürece bağlanıyordu; gerçek exe `os.startfile`
    ile açılmalı.
    """
    if not folder.is_dir():
        return None
    ad = folder.name
    dogrudan = folder / f"{ad}.exe"
    if dogrudan.is_file():
        return dogrudan
    adaylar: list[Path] = []
    try:
        for path in folder.rglob("*.exe"):
            if not path.is_file() or _atlanan_yol(path):
                continue
            # obj/ ara çıktıları ve vshost gürültüsü.
            if "obj" in path.parts or ".vshost." in path.name.lower():
                continue
            adaylar.append(path)
    except OSError:
        return None
    if not adaylar:
        return None
    # Ada uyan > publish > Release > en yeni.
    def skor(p: Path) -> tuple:
        parts = {x.lower() for x in p.parts}
        return (
            0 if p.stem.lower() == ad.lower() else 1,
            0 if "publish" in parts else 1,
            0 if "release" in parts else 1,
            -p.stat().st_mtime,
        )
    adaylar.sort(key=skor)
    return adaylar[0]


def _detect(folder: Path) -> tuple[str, str, str]:
    """Klasörün türünü, giriş dosyasını ve çalıştırma komutunu sezer.

    web       index.html (+ isteğe bağlı sunucu)
    service   sunucu betiği / Node / API
    desktop   WinExe / GUI .exe (masaüstü uygulama)
    tool      konsol betiği
    doc       belge

    Sezgi asgari tutuluyor: ajan daha iyisini biliyorsa `app.json`
    manifestiyle söylüyor ve manifest her zaman kazanıyor — ama ajanın
    GUI uygulamayı `tool` yazması yumuşakça düzeltilir (bkz. proje kurucu).
    """
    index = _find(folder, ("index.html", "index.htm"))
    server = _find(folder, ("app.py", "main.py", "server.py", "run.py",
                            "server.js", "app.js", "index.js", "main.js",
                            "index.php"))
    run = _package_run(folder) or (_run_line(server) if server else "")
    csproj = _find(folder, None, {".csproj"})
    if csproj and _csproj_masaustu(csproj):
        exe = _desktop_exe(folder)
        if exe:
            return "desktop", _rel(exe, folder), ""
        return "desktop", _rel(csproj, folder), f'dotnet run --project "{csproj.name}"'
    if not run and csproj:
        return "service", _rel(csproj, folder), "dotnet run"
    if index and (server or run):
        return "web", _rel(index, folder), run
    if index:
        return "web", _rel(index, folder), ""
    if server or run:
        entry = _rel(server, folder) if server else ""
        return "service", entry, run
    # GUI exe (csproj yok / publish klasörü): betik değil masaüstü.
    exe = _desktop_exe(folder)
    if exe:
        return "desktop", _rel(exe, folder), ""
    any_run = _find(folder, None, RUN)
    if any_run:
        return "tool", _rel(any_run, folder), _run_line(any_run)
    page = _newest(folder, WEB)
    if page:
        return "web", _rel(page, folder), ""
    return "doc", "", ""


def _find(folder: Path, names: tuple[str, ...] | None, suffixes: set[str] | None = None) -> Path | None:
    """Klasörde (birkaç düzey) ilk eşleşen dosya — derleme çöplüğü hariç."""
    try:
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.name in SKIP or _atlanan_yol(path):
                continue
            if names and path.name.lower() in names:
                return path
            if suffixes and path.suffix.lower() in suffixes:
                return path
    except OSError:
        return None
    return None


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
            if not path.is_file() or _atlanan_yol(path):
                continue
            if path.suffix.lower() not in suffixes:
                continue
            t = path.stat().st_mtime
            if t > best_t:
                best, best_t = path, t
    except OSError:
        return None
    return best


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
    # Docstring yoksa ilk anlamlı YORUM satırı: Dornick'in (ve insanların) yazdığı
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

    Yol bir KLASÖRSE proje olarak başlar: masaüstü .exe varsa `os.startfile`
    (pencere açılsın); yoksa manifest `run` / sezilen komut. Böylece
    WinExe .NET uygulaması "başladı" deyip arayüzsüz kalmaz.
    """
    root = sandbox_root.resolve()
    ref = (base or root).resolve()
    target = (ref / rel_path).resolve()
    if target != root and root not in target.parents:
        return {"ok": False, "error": "Atölye dışı: yalnızca kendi ürettiğin çalıştırılır."}

    klasor = target if target.is_dir() else (target.parent if target.is_file() else None)
    gui = _desktop_exe(klasor) if klasor is not None else None

    # Aynı şey zaten çalışıyorsa: web/servis için ikincisini başlatma.
    # Masaüstü GUI'de "already" sessiz başarı yanlış — pencereyi yeniden aç.
    for pid, info in list(_PROCS.items()):
        if info.get("path") == rel_path and info["proc"].poll() is None:
            if gui is not None:
                try:
                    import os
                    os.startfile(str(gui))  # type: ignore[attr-defined]
                except Exception as exc:
                    return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                return {"ok": True, "pid": pid, "path": rel_path,
                        "already": True, "note": "Pencere yeniden açıldı."}
            return {"ok": True, "pid": pid, "path": rel_path,
                    "already": True, "note": "Zaten çalışıyor."}

    if target.is_dir():
        # Masaüstü uygulaması: gerçek .exe'yi aç — dotnet/ps1 sarmalayıcısı
        # CREATE_NO_WINDOW ile daha önce başlatılmış olabilir.
        if gui is not None:
            try:
                import os
                os.startfile(str(gui))  # type: ignore[attr-defined]
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            return {"ok": True, "run": gui.name, "path": rel_path, "pid": None,
                    "note": "Masaüstü uygulaması açıldı."}

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
                             "bir `run` satırı ekletebilirsin (Dornick'e sor). "
                             + MANIFEST_OGRETICI}

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


def running(sandbox_root: Path | None = None,
            base: Path | None = None) -> list[dict[str, Any]]:
    """Hâlâ çalışan, izlenebilen uygulamalar — canlı adresleriyle.

    Ölmüş süreçler ayıklanıyor. Adres (bir web sunucusu bağladıysa) netstat
    ile PID → dinlenen port eşleştirilerek bulunuyor; port henüz bağlanmadıysa
    boş döner ve sonraki yoklamada belirir.

    Dornick'in KENDİ süreçleri bu listeden düşüyor. Model kafası karışıp
    `dornick --web 8873` çalıştırdığında panel Dornick'in bir kopyasını
    "uygulaman" diye listeliyordu; kullanıcının gördüğü şey kendi
    programının klonuydu. Kendi kopyası ayrı bir satır olarak, DURDURULAMAZ
    biçimde görünüyor — gizlemek de yanlış olurdu, kullanıcı orada bir şey
    çalıştığını bilmeli.
    """
    out: list[dict[str, Any]] = []
    dead: list[int] = []
    # Süreç ağacı, komut satırları ve dinlenen portlar bir KEZ toplanıyor:
    # her süreç için ayrı ayrı sorgulamak yoklamayı ağırlaştırırdı.
    bilgi = _proc_bilgi()
    parents = {pid: v["ppid"] for pid, v in bilgi.items()}
    listen = _listening_ports()
    for pid, info in list(_PROCS.items()):
        proc = info["proc"]
        if proc.poll() is not None:   # bitmiş
            dead.append(pid)
            continue
        # Kaydın kendi metni en güvenilir işaret (kabuk aracı komutu olduğu
        # gibi yazıyor); ağaç taraması yedek.
        kendi = (is_dornick_process(str(info.get("path") or ""))
                 or is_dornick_process(str(info.get("run") or ""))
                 or _dornick_ailesi(pid, bilgi))
        out.append({
            "pid": pid,
            "path": info["path"],
            "name": "Dornick (kendisi)" if kendi else info["name"],
            "address": _address(pid, parents, listen),
            "started": info.get("started", 0),
            "run": info.get("run", ""),
            "self": kendi,
            "stoppable": not kendi,
        })
    for pid in dead:
        _PROCS.pop(pid, None)

    # Defterde OLMAYAN ama atölyeye ait çalışan sunucular: dornick yeniden
    # başlatıldığında ya da uygulamayı kullanıcı elle koşturduğunda süreç
    # `_PROCS`'ta yok — panel "hiçbir şey çalışmıyor" diyordu, oysa
    # uygulama 8090'da hizmet veriyordu. Proje portu gerçekten dinleniyorsa
    # o uygulama CANLI sayılıyor.
    if sandbox_root is not None:
        bilinen = {row["pid"] for row in out}
        for row in _kesfedilen_sunucular(sandbox_root, bilgi, listen, base):
            if row["pid"] not in bilinen:
                out.append(row)
                bilinen.add(row["pid"])
    return out


def _kesfedilen_sunucular(
    sandbox_root: Path,
    bilgi: dict[int, dict[str, Any]],
    listen: dict[int, list[int]],
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Atölyedeki projelerin ilan ettiği portları DİNLEYEN süreçler.

    Kanıt bir soket: proje "8090'da yaşıyorum" diyor, 8090'ı dinleyen bir
    süreç var ve o süreç Dornick'in kendisi değil → uygulama çalışıyor.

    Yollar `base`'e göre veriliyor (panel proje yollarıyla eşleştiriyor);
    farklı köke göre üretilen iki yol aynı uygulamayı iki kez gösterirdi.
    """
    out: list[dict[str, Any]] = []
    try:
        items = katalog(sandbox_root, base, canli=False)["projects"]
    except Exception:
        return out
    sahip: dict[int, int] = {}     # port → pid
    for pid, ports in listen.items():
        for port in ports:
            sahip.setdefault(port, pid)
    for p in items:
        port = int(p.get("port") or 0)
        pid = sahip.get(port, 0)
        if not port or not pid or _dornick_ailesi(pid, bilgi):
            continue
        _KESFEDILEN.add(pid)
        out.append({
            "pid": pid,
            "path": p.get("path", ""),
            "name": p.get("name", ""),
            "address": f"http://127.0.0.1:{port}",
            "started": 0,
            "run": p.get("run", ""),
            "self": False,
            "stoppable": True,
            "discovered": True,
        })
    return out


def _canli_isaretle(items: list[Project], root: Path, ref: Path) -> None:
    """Projelere canlı durumu işler: pid, adres, durdurulabilirlik.

    İki kaynak birlikte: (1) süreç defteri (`_PROCS`) — Dornick'in kendi
    başlattıkları; (2) ilan edilen portun gerçekten dinleniyor olması —
    dornick yeniden başlatılsa da, uygulamayı kullanıcı elle koşturmuş olsa da
    çalışan şey görünüyor.
    """
    izlenen: dict[str, int] = {}
    for pid, info in _PROCS.items():
        if info["proc"].poll() is None:
            izlenen[str(info.get("path") or "")] = pid
    ilan = {p.port for p in items if p.port}
    if not items or (not izlenen and not ilan):
        return   # eşleşecek hiçbir şey yok: süreç sorgusu bile açma

    try:
        listen = _listening_ports()
    except Exception:
        return
    sahip: dict[int, int] = {}
    for pid, ports in listen.items():
        for port in ports:
            sahip.setdefault(port, pid)
    if not izlenen and not (ilan & set(sahip)):
        return   # ilan edilen portların hiçbiri dinlenmiyor

    bilgi = _proc_bilgi()
    parents = {pid: v["ppid"] for pid, v in bilgi.items()}

    for p in items:
        pid = izlenen.get(p.path) or (izlenen.get(p.entry) if p.entry else 0) or 0
        if pid:
            p.pid = pid
            p.address = _address(pid, parents, listen)
            p.stoppable = not _dornick_ailesi(pid, bilgi)
        if p.port and not p.address:
            dinleyen = sahip.get(p.port, 0)
            if dinleyen and not _dornick_ailesi(dinleyen, bilgi):
                p.pid = p.pid or dinleyen
                p.address = f"http://127.0.0.1:{p.port}"
                p.stoppable = True
                _KESFEDILEN.add(dinleyen)


# Dornick'in kendi süreçleri: komut satırında `dornick` geçen her şey. Model
# uygulamasını başlatmak yerine Dornick'i başlattığında (`dornick --web 8873`)
# panel onu "uygulaman" diye listeliyordu — kullanıcı kendi programının
# klonuna bakıyordu. Bu kalıp o kopyayı tanıyor.
# Dikkat (01.09, ad değişiminde yakalandı): `dornick` artık hem paket hem
# KLASÖR adı. Çıplak yol parçası eşleşirse, proje klasöründen açılmış her
# kabuğun altındaki süreçler "kendisi" sayılıyordu. İz yalnız GERÇEK
# çalıştırma imzalarını tanır: `-m dornick`, `dornick.exe/.cmd`, ya da
# komut satırının başındaki çıplak `dornick`.
_DORNICK_IZI = re.compile(
    r"(-m\s+dornick(?=[\s\"']|$))"
    r"|((^|[\\/\s\"'])dornick\.(exe|cmd)(?=[\s\"']|$))"
    r"|(^\s*\"?dornick\"?(?=[\s\"']|$))",
    re.IGNORECASE)

# Port kanıtıyla keşfedilmiş (defterde olmayan) süreçler. `stop()` yalnızca
# bir kez görülmüş bir pid'i durdurabilsin diye tutuluyor: panel rastgele bir
# sistem sürecini öldüremez.
_KESFEDILEN: set[int] = set()


def is_dornick_process(cmdline: str) -> bool:
    """Bu komut satırı Dornick'in kendisini mi başlatıyor? (dışarıdan da kullanılır)"""
    return bool(_DORNICK_IZI.search(cmdline or ""))


def _dornick_ailesi(pid: int, bilgi: dict[int, dict[str, Any]]) -> bool:
    """pid ya da ATALARINDAN biri dornick mu?

    Sarmalayıcıya bakmak yetmiyor: `powershell -Command "dornick --web 8873"`
    zincirinde asıl dornick torun süreç. Zincir yukarı taranıyor.
    """
    if pid == os.getpid():
        return True
    gorulen: set[int] = set()
    cur = pid
    while cur and cur not in gorulen:
        gorulen.add(cur)
        kayit = bilgi.get(cur)
        if kayit is None:
            break
        if is_dornick_process(str(kayit.get("cmd") or "")):
            return True
        cur = int(kayit.get("ppid") or 0)
    # Torunlarda dornick var mı (sarmalayıcı pid defterde, dornick çocuğunda)
    for cocuk, kayit in bilgi.items():
        if kayit.get("ppid") == pid and is_dornick_process(str(kayit.get("cmd") or "")):
            return True
    return False


def stop(pid: int) -> dict[str, Any]:
    """İzlenen bir süreci AĞACIYLA durdurur.

    Kayıtlı pid çoğu zaman bir sarmalayıcı (py başlatıcısı, PowerShell);
    `terminate()` yalnız onu öldürüyor, asıl sunucu torun süreç olarak
    yaşamaya devam ediyordu — kullanıcı "durdur diyorum, durmuyor" yaşıyordu
    (adres çözümündeki ağaç meselesinin ikizi). Windows'ta taskkill /T tüm
    ağacı indiriyor."""
    info = _PROCS.get(pid)
    if info is None:
        # Defterde yok ama PORT KANITIYLA keşfedilmişse durdurulabilir: dornick
        # yeniden başlatıldığında uygulamalar "durdurulamaz" hale geliyordu.
        # Rastgele bir sistem sürecini öldürmemek için yalnızca `running()`
        # tarafından bir kez görülmüş pid'ler kabul ediliyor.
        if pid not in _KESFEDILEN:
            return {"ok": False, "error": "Bu süreç izlenmiyor ya da zaten bitmiş."}
        if _dornick_ailesi(pid, _proc_bilgi()):
            return {"ok": False, "error": "Bu Dornick'in kendi süreci — panelden durdurulmuyor."}
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=10,
                               **environment.quiet_flags())
            else:
                os.kill(pid, 15)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        _KESFEDILEN.discard(pid)
        return {"ok": True, "pid": pid}
    # Defterdeki kaydın kendi metni yetiyor (süreç ağacını sorgulamaya gerek
    # yok): kabuk aracı komutu olduğu gibi yazıyor, `dornick --web 8873` orada
    # görünüyor.
    if is_dornick_process(str(info.get("path") or "")) or is_dornick_process(str(info.get("run") or "")):
        return {"ok": False, "error": "Bu Dornick'in kendi süreci — panelden durdurulmuyor."}
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=10,
                           **environment.quiet_flags())
        else:
            info["proc"].terminate()
        # Öldü mü gerçekten? "Durdurdum" deyip çalışır bırakmak, kullanıcının
        # "durdur diyorum durmuyor" şikâyetinin ta kendisi. Kısa bir bekleme
        # ile doğrulanıyor; hâlâ yaşıyorsa dürüstçe hata dönülüyor.
        try:
            info["proc"].wait(timeout=3)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Süreç durdurulamadı — hâlâ çalışıyor. "
                                          "Tekrar dene ya da Dornick'e söyle."}
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
    izin = _acilabilir_mi(sandbox_root, rel_path, base)
    if isinstance(izin, dict):
        return izin
    target = izin
    # Yalnızca tarayıcının işi olanlar: bir .docx'i "tarayıcıda aç" diye
    # Word'e fırlatmak yanlış beklenti kurar — o dosyalar zaten kendi
    # uygulamasında açılmak isteniyorsa `sistemde_ac` var.
    if target.suffix.lower() not in {".html", ".htm", ".svg"}:
        return {"ok": False, "error": "Bu bir web sayfası değil; tarayıcıda açılmaz."}
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
    except Exception as exc:
        return {"ok": False, "error": f"Açılamadı: {type(exc).__name__}: {exc}"}
    return {"ok": True, "opened": str(target)}


# Açılabilir alan: atölye + kullanıcının BAĞLADIĞI proje klasörü.
#
# Eski hal yalnız atölyeydi ve ajan bağlı bir klasöre rapor yazdığında
# "Klasörde göster"/"Aç" düğmeleri "Atölye dışı" diye reddediyordu —
# kullanıcı ürettiği dosyaya ulaşamıyordu (canlı yara, 02.09). Proje
# klasörünü kullanıcı kendi seçiyor; orası da onun alanı.
def _izinli_kokler(sandbox_root: Path, base: Path | None = None) -> list[Path]:
    kokler = [sandbox_root.resolve()]
    if base is not None:
        try:
            kokler.append(base.resolve())
        except OSError:
            pass
    return kokler


def _acilabilir_mi(sandbox_root: Path, rel_path: str,
                   base: Path | None = None) -> Any:
    """Hedefi çözer ve izinli mi diye bakar. Path ya da hata sözlüğü döner."""
    kokler = _izinli_kokler(sandbox_root, base)
    ref = (base or sandbox_root).resolve()
    try:
        target = (ref / rel_path).resolve() if rel_path else ref
    except OSError:
        return {"ok": False, "error": f"Yol çözümlenemedi: {rel_path}"}
    if not any(target == k or k in target.parents for k in kokler):
        return {"ok": False,
                "error": "Çalışma alanı dışı: yalnızca atölyedeki ya da "
                         "bağlı klasördeki dosyalar açılır."}
    if not target.exists():
        return {"ok": False, "error": f"Yok: {rel_path}"}
    return target


def sistemde_ac(sandbox_root: Path, rel_path: str,
                base: Path | None = None) -> dict[str, Any]:
    """Dosyayı işletim sisteminin VARSAYILAN uygulamasında açar.

    PDF, docx, xlsx, png… — ajanın ürettiği her dosya için "aç" düğmesinin
    arkasındaki uç. `open_path` yalnız web sayfası açıyordu; bir raporu
    okumak isteyen kullanıcıya "bu bir web sayfası değil" demek cevap
    değildi (canlı yara, 02.09).
    """
    izin = _acilabilir_mi(sandbox_root, rel_path, base)
    if isinstance(izin, dict):
        return izin
    target = izin
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:  # pragma: no cover - Windows dışı yol
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:
        return {"ok": False, "error": f"Açılamadı: {type(exc).__name__}: {exc}"}
    return {"ok": True, "opened": str(target)}


def reveal(sandbox_root: Path, rel_path: str, base: Path | None = None) -> dict[str, Any]:
    """Uygulamanın klasörünü dosya gezgininde açar.

    "Nerede bu şey?" panelin en sık sorulan sorusu: kart bir yol yazıyor ama
    kullanıcı onu diskte bulmak için elle geziniyordu. Dosya verilirse
    klasörü açılıyor (dosya seçili).
    """
    root = sandbox_root.resolve()
    izin = _acilabilir_mi(sandbox_root, rel_path, base)
    if isinstance(izin, dict):
        return izin
    target = izin
    try:
        if sys.platform == "win32":
            if target.is_dir():
                os.startfile(str(target))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target if target.is_dir() else target.parent)])
    except Exception as exc:
        return {"ok": False, "error": f"Açılamadı: {type(exc).__name__}: {exc}"}
    return {"ok": True, "shown": _rel(target, root)}


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
    return {pid: v["ppid"] for pid, v in _proc_bilgi().items()}


def _proc_bilgi() -> dict[int, dict[str, Any]]:
    """pid → {ppid, cmd}. Süreç ağacı VE komut satırları tek sorguda.

    Komut satırı gerekiyor çünkü Dornick'in kendi kopyasını (`dornick --web ...`)
    kullanıcının uygulamasından ancak o ayırıyor. Ayrı bir sorgu daha açmak
    4 saniyelik yoklamayı iki katına çıkarırdı; aynı sorguya bir alan
    eklemek bedavaya yakın.

    Ayraç `|`: CSV, komut satırındaki virgüllerde bozuluyordu.
    """
    out: dict[int, dict[str, Any]] = {}
    try:
        if sys.platform == "win32":
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | ForEach-Object { "
                 "\"$($_.ProcessId)|$($_.ParentProcessId)|"
                 "$($_.CommandLine -replace '[\\r\\n\\|]',' ')\" }"],
                # errors="replace": komut satırlarında konsol kod sayfasının
                # çözemediği baytlar olabiliyor (çökme değil, bozuk karakter
                # kabul edilir — aradığımız iz `dornick` zaten ASCII).
                capture_output=True, text=True, errors="replace", timeout=8,
                **environment.quiet_flags(),
            )
            for line in res.stdout.splitlines():
                parts = line.split("|", 2)
                if len(parts) >= 2 and parts[0].strip().isdigit() \
                        and parts[1].strip().isdigit():
                    out[int(parts[0])] = {
                        "ppid": int(parts[1]),
                        "cmd": parts[2].strip() if len(parts) > 2 else "",
                    }
        else:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                try:
                    with open(f"/proc/{entry}/stat") as fh:
                        fields = fh.read().split()
                    try:
                        with open(f"/proc/{entry}/cmdline", "rb") as ch:
                            cmd = ch.read().replace(b"\0", b" ").decode(
                                "utf-8", "replace").strip()
                    except OSError:
                        cmd = ""
                    out[int(entry)] = {"ppid": int(fields[3]), "cmd": cmd}
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
            capture_output=True, text=True, errors="replace", timeout=3,
            **environment.quiet_flags(),
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
            f"Kurulumu Dornick'ten isteyebilirsin."
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
