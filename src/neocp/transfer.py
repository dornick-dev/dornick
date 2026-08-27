"""Taşınabilirlik: neo'nun bir makinede biriktirdiklerini başka yere taşımak.

neo bir bilgisayarda yaşadıkça anılar biriktiriyor, bağlar örüyor, hedefler
tutuyor, kendine yetenekler yazıyor. Bunların hepsi diskte — ama bir
makineye mahkûm olmamalı. Bu modül hepsini tek bir taşınabilir pakete
(`.neobundle`, düz bir zip) koyuyor ve başka bir neo'ya **birleştiriyor**.

İlke birleştirme, üzerine yazma değil: aynı kimlikli anı iki kez girmiyor
(idempotent), yalnızca yeni olanlar ekleniyor. Böylece iki makinenin
öğrendikleri tek bir neo'da toplanabiliyor — biri diğerini silmeden. Ruh
(persona) korunuyor: hedef neo'nun bir kimliği varsa gelen paket onu
ezmiyor; yalnızca boşsa dolduruyor.

Paket içeriği (parçaya göre — bkz. PARCALAR):
    manifest.json     sürüm, tarih, sayımlar, seçilen parçalar
    recall.db         anılar + bağlar (imzalarıyla) — tutarlı kopya
    goals.jsonl       hedefler (varsa)
    persona.md        ruh metni (varsa)
    projects.json     oturum→proje eşlemesi (varsa)
    skills/<...>      yetenekler klasörü
    tanima/<...>      kişisel model (taban.npz) + eğitim düzeneğinin
                      kişisel dosyaları (korpus + filigran, varsa)
    projeler/<...>    atölyenin kendisi (üretilen projeler/dosyalar)
    ayarlar/<...>     config.json — ANAHTARSIZ (aşağıya bak)

ANAHTARLAR ASLA PAKETE GİRMEZ: keys.json hiçbir parçada yok ve ayarlar
parçasındaki config.json'dan anahtara işaret eden alan (api_key_env) da
düşürülüyor — içe alan taraf onu sağlayıcıdan yeniden türetiyor. Paket
elden ele dolaşabilecek bir dosya; içinde sır taşımamalı.

Oturum günlükleri (ham konuşmalar) DIŞARIDA: onlar "öğrenilenler" değil,
ham kayıt; büyük ve özel. İstenirse ayrı bir dışa aktarma işi olur.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from . import skills as skills_mod
from . import tanima as tanima_mod

BUNDLE_VERSION = 1

# Seçilebilen parçalar. "anilar" eski paketin tamamı (anılar, bağlar,
# hedefler, ruh, oturum→proje eşlemesi, yetenekler) — geriye uyumluluk:
# parça verilmeyen istek eskisiyle birebir aynı paketi üretiyor.
PARCALAR = ("anilar", "tanima", "projeler", "ayarlar")

# Zip içindeki sabit adlar.
_MANIFEST = "manifest.json"
_DB = "recall.db"
_GOALS = "goals.jsonl"
_PERSONA = "persona.md"
_PROJECTS = "projects.json"
_SKILLS = "skills/"
_TANIMA = "tanima/"
_PROJELER = "projeler/"
_AYARLAR = "ayarlar/"

# Atölye taramasında atlanan dizinler: araç artıkları, sürüm kontrolü,
# çöp kutusu (server.py'deki SKIPPED / gate._ATLA ile aynı akıl).
# .neocp da listede: değişiklik görüntüleri (.neocp/degisiklikler) ve diğer
# oturum artıkları pakete girmesin — atölye kökü bir gün state ile çakışsa bile.
_ATLA = frozenset({".git", "__pycache__", "node_modules", ".venv",
                   ".mypy_cache", ".geri-donusum", ".neocp"})


def export_bundle(config: Any, mind: Any,
                  parcalar: Sequence[str] | None = None) -> bytes:
    """Seçilen parçaları tek bir zip'e koyar ve baytlarını döndürür.

    `parcalar` verilmezse eski davranış: yalnızca "anilar" (eski paketin
    tamamı). Bilinmeyen adlar sessizce eleniyor — bozuk bir istek boş
    değil, bildiği kadarını içeren bir paket üretmeli.
    """
    secim = [p for p in (parcalar or ("anilar",)) if p in PARCALAR] or ["anilar"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        counts = {"memories": 0, "links": 0, "goals": 0, "skills": 0}

        if "anilar" in secim:
            # Bellek: tutarlı bir kopya (WAL dahil), geçici dosya üzerinden.
            with tempfile.TemporaryDirectory() as tmp:
                db_copy = Path(tmp) / _DB
                mind.store.backup_to(db_copy)
                zf.write(db_copy, _DB)
            counts["memories"] = _safe_count(lambda: mind.store.count())
            counts["links"] = _safe_count(lambda: len(mind.store.links()))

            # Hedefler.
            goals = config.mind_dir / "goals.jsonl"
            if goals.is_file():
                data = goals.read_text(encoding="utf-8")
                zf.writestr(_GOALS, data)
                counts["goals"] = sum(1 for ln in data.splitlines() if ln.strip())

            # Ruh (persona).
            persona = _persona_path(config)
            if persona and persona.is_file():
                zf.writestr(_PERSONA, persona.read_text(encoding="utf-8"))

            # Projeler (oturum→proje).
            projects = config.sessions_dir / "_projects.json"
            if projects.is_file():
                zf.writestr(_PROJECTS, projects.read_text(encoding="utf-8"))

            # Yetenekler.
            skills_dir = _skills_dir(config)
            if skills_dir and skills_dir.is_dir():
                for path in sorted(skills_dir.rglob("*")):
                    if path.is_file() and not _is_noise(path):
                        rel = path.relative_to(skills_dir).as_posix()
                        zf.writestr(_SKILLS + rel, path.read_bytes())
                        counts["skills"] += 1

        if "tanima" in secim:
            counts["tanima"] = _export_tanima(config, zf)

        if "projeler" in secim:
            counts["projeler"] = _export_projeler(config, zf)

        if "ayarlar" in secim:
            counts["ayarlar"] = _export_ayarlar(config, zf)

        manifest = {
            "kind": "neobundle",
            "version": BUNDLE_VERSION,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "counts": counts,
            "parcalar": secim,
        }
        zf.writestr(_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))

    return buf.getvalue()


def _export_tanima(config: Any, zf: zipfile.ZipFile) -> int:
    """Kişisel model + eğitim düzeneğinin kişisel dosyaları (varsa).

    Hepsi "varsa": henüz hiç eğitilmemiş bir makinede parça sessizce boş
    kalır — hata değil, taşınacak bir şey olmaması.
    """
    yazilan = 0
    kaynaklar = [
        (Path(config.state_dir) / "taban.npz", "taban.npz"),
        (tanima_mod.KORPUS, "kisisel_korpus.jsonl"),
        (tanima_mod.FILIGRAN, "kisisel_durum.json"),
    ]
    for kaynak, ad in kaynaklar:
        if kaynak.is_file():
            zf.write(kaynak, _TANIMA + ad)
            yazilan += 1
    return yazilan


def _export_projeler(config: Any, zf: zipfile.ZipFile) -> int:
    """Atölyenin kendisi: neo'nun ürettiği projeler ve dosyalar."""
    try:
        kok = Path(config.open_sandbox().root)
    except Exception:
        return 0
    yazilan = 0
    for path in sorted(kok.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(kok)
        if any(parca in _ATLA for parca in rel.parts):
            continue
        try:
            zf.write(path, _PROJELER + rel.as_posix())
        except OSError:
            continue  # o an kilitli/silinen dosya paketi düşürmesin
        yazilan += 1
    return yazilan


def _export_ayarlar(config: Any, zf: zipfile.ZipFile) -> int:
    """config.json — anahtarsız.

    keys.json HİÇBİR parçada yok; config'ten de anahtara işaret eden alan
    (model.api_key_env) düşürülüyor. İçe alan taraf onu base_url'den
    yeniden türetiyor — ortam değişkeni adı sır değil ama paketin içinde
    "anahtar" kelimesinin bile işi yok.
    """
    yol = Path(config.state_dir) / "config.json"
    if not yol.is_file():
        return 0
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if isinstance(veri.get("model"), dict):
        veri["model"].pop("api_key_env", None)
    zf.writestr(_AYARLAR + "config.json",
                json.dumps(veri, ensure_ascii=False, indent=2))
    return 1


def import_bundle(config: Any, mind: Any, data: bytes,
                  parcalar: Sequence[str] | None = None) -> dict[str, Any]:
    """Bir paketi bu neo'ya birleştirir. Anılar katılır, üzerine yazılmaz;
    dosya parçaları (tanima/projeler/ayarlar) üzerine yazmadan önce mevcut
    hali .neocp/yedek-<tarih>/ altına alır.

    `parcalar` verilirse pakette olsa bile yalnızca istenenler işlenir —
    tek arşivden seçerek geri yükleme. Dönen özet arayüzde gösteriliyor.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return {"ok": False, "error": "Geçersiz paket: zip açılamadı."}

    names = set(zf.namelist())
    if _MANIFEST not in names:
        return {"ok": False, "error": "Bu bir neo paketi değil (manifest yok)."}

    try:
        manifest = json.loads(zf.read(_MANIFEST))
    except (json.JSONDecodeError, KeyError):
        manifest = {}
    if manifest.get("kind") != "neobundle":
        return {"ok": False, "error": "Tanınmayan paket türü."}
    # Eski paketlerde parça kavramı yok: bellek dosyası şart. Seçmeli
    # paket (manifest "parcalar" taşıyor) belleksiz de geçerli olabilir.
    if "parcalar" not in manifest and _DB not in names:
        return {"ok": False, "error": "Bu bir neo paketi değil (bellek yok)."}

    istenen = set(p for p in (parcalar or PARCALAR) if p in PARCALAR)
    summary: dict[str, Any] = {"ok": True, "memories": 0, "links": 0,
                               "goals": 0, "skills": 0, "persona": False}
    # Yedek klasörü tembel: hiçbir şeyin üzerine yazılmayacaksa boş bir
    # yedek-<tarih> klasörü bile açılmasın.
    yedek: list[Path] = []

    if "anilar" in istenen:
        if _DB in names:
            # Bellek birleştirme: geçici dosyaya yazıp store'a kat.
            with tempfile.TemporaryDirectory() as tmp:
                db_in = Path(tmp) / _DB
                db_in.write_bytes(zf.read(_DB))
                merged = mind.store.merge_from(db_in)
                summary["memories"] = merged.get("nodes", 0)
                summary["links"] = merged.get("links", 0)

        # Hedefler: kimliğe göre yeni olanları ekle.
        if _GOALS in names:
            summary["goals"] = _merge_goals(config, mind, zf.read(_GOALS).decode("utf-8"))

        # Ruh: yalnızca hedef boşsa doldur — gelen paket kimliği ezmesin.
        if _PERSONA in names:
            summary["persona"] = _maybe_persona(config, zf.read(_PERSONA).decode("utf-8"))

        # Projeler (oturum→proje eşlemesi): katar, var olan atama korunur.
        if _PROJECTS in names:
            _merge_projects(config, zf.read(_PROJECTS).decode("utf-8"))

        # Yetenekler: dosyaları kopyala, var olanı ezme.
        summary["skills"] = _merge_skills(config, zf, names)

    if "tanima" in istenen:
        summary["tanima"] = _import_tanima(config, zf, names, yedek)

    if "projeler" in istenen:
        summary["projeler"] = _import_projeler(config, zf, names, yedek)

    if "ayarlar" in istenen:
        summary["ayarlar"] = _import_ayarlar(config, zf, names, yedek)

    if yedek:
        summary["yedek"] = str(yedek[0])
    return summary


# -- dosya parçaları: yedekli geri yükleme ---------------------------------


def yedek_klasoru(state_dir: Path) -> Path:
    """Zaman damgalı yedek klasörü — sıfırlama ve içe alma aynı adı kullanır."""
    return Path(state_dir) / f"yedek-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _yedekle(hedef: Path, state_dir: Path, yedek: list[Path], etiket: str) -> None:
    """Üzerine yazılacak dosyanın mevcut halini yedek klasörüne kopyalar."""
    if not hedef.is_file():
        return
    if not yedek:
        yedek.append(yedek_klasoru(state_dir))
    kopya = yedek[0] / etiket / hedef.name
    kopya.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(hedef, kopya)


def _import_tanima(config: Any, zf: zipfile.ZipFile, names: set[str],
                   yedek: list[Path]) -> int:
    """Kişisel model + kişisel eğitim dosyalarını geri koyar.

    taban.npz her koşulda .neocp'ye iner (ürünün okuduğu yer orası) ve
    taban önbelleği düşürülür ki 5 dakikalık yenilemeyi beklemeden devreye
    girsin. Korpus/filigran eğitim düzeneği kuruluysa yerine, değilse
    .neocp/tanima_yedek/ altına — düzeneksiz makinede kaybolmasınlar.
    """
    state_dir = Path(config.state_dir)
    duzenek_var = tanima_mod.KORPUS.parent.is_dir()
    yazilan = 0
    hedefler = {
        "taban.npz": state_dir / "taban.npz",
        "kisisel_korpus.jsonl": (tanima_mod.KORPUS if duzenek_var
                                 else state_dir / "tanima_yedek" / "kisisel_korpus.jsonl"),
        "kisisel_durum.json": (tanima_mod.FILIGRAN if duzenek_var
                               else state_dir / "tanima_yedek" / "kisisel_durum.json"),
    }
    for ad, hedef in hedefler.items():
        if _TANIMA + ad not in names:
            continue
        _yedekle(hedef, state_dir, yedek, "tanima")
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_bytes(zf.read(_TANIMA + ad))
        yazilan += 1
    if yazilan:
        # Gelen kişisel model hemen konuşsun; eskisinin önbelleği düşer.
        from .recall import taban
        taban.sifirla()
    return yazilan


def _import_projeler(config: Any, zf: zipfile.ZipFile, names: set[str],
                     yedek: list[Path]) -> int:
    """Atölye dosyalarını geri koyar; ezilenin mevcut hali önce yedeğe."""
    try:
        kok = Path(config.open_sandbox().root).resolve()
    except Exception:
        return 0
    yazilan = 0
    for name in sorted(names):
        if not name.startswith(_PROJELER) or name.endswith("/"):
            continue
        rel = name[len(_PROJELER):]
        if not rel:
            continue
        hedef = (kok / rel).resolve()
        # Klasör dışına taşma (zip-slip) koruması.
        if kok not in hedef.parents and hedef != kok:
            continue
        _yedekle(hedef, Path(config.state_dir), yedek, "projeler")
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_bytes(zf.read(name))
        yazilan += 1
    return yazilan


def _import_ayarlar(config: Any, zf: zipfile.ZipFile, names: set[str],
                    yedek: list[Path]) -> int:
    """config.json'u geri koyar (yeniden başlatınca geçerli olur).

    Anahtarlara dokunulmuyor: keys.json paketin dışında ve burada da hiç
    ele alınmıyor. Dışa aktarımda düşürülen api_key_env, base_url'den
    yeniden türetiliyor — yoksa sağlayıcı anahtarsız kalırdı.
    """
    ad = _AYARLAR + "config.json"
    if ad not in names:
        return 0
    try:
        veri = json.loads(zf.read(ad).decode("utf-8"))
    except (ValueError, KeyError):
        return 0
    model = veri.get("model")
    if isinstance(model, dict) and not model.get("api_key_env"):
        env = _anahtar_degiskeni(str(model.get("base_url") or ""))
        if env:
            model["api_key_env"] = env
    hedef = Path(config.state_dir) / "config.json"
    _yedekle(hedef, Path(config.state_dir), yedek, "ayarlar")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(veri, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return 1


def _anahtar_degiskeni(base_url: str) -> str:
    """base_url'den anahtarın ortam değişkeni adını türetir (settings listesi)."""
    from . import settings
    for entry in settings.PROVIDERS:
        if entry.get("env") and entry.get("base_url") and entry["base_url"] in base_url:
            return str(entry["env"])
    return ""


# -- sıfırlama -------------------------------------------------------------


def reset_memories(config: Any, mind: Any) -> dict[str, Any]:
    """Anıları ve bağları sıfırlar; önce tutarlı bir yedek alır.

    Yalnızca anılar: hedefler, ruh, oturum günlükleri ve yetenekler
    yerinde kalıyor — "beni unut" başka, "kim olduğunu unut" başka.
    Yedek .neocp/yedek-<tarih>/anilar/recall.db — geri dönüş yolu açık.
    """
    yedek = yedek_klasoru(config.state_dir)
    try:
        mind.store.backup_to(yedek / "anilar" / "recall.db")
    except Exception as exc:
        # Yedeksiz silinmez: yedek alınamıyorsa sıfırlama da yok.
        return {"ok": False, "error": f"Yedek alınamadı: {exc}"}
    silinen = mind.store.reset()
    return {"ok": True, "silinen": silinen, "yedek": str(yedek)}


# -- birleştirme yardımcıları ---------------------------------------------


def _merge_goals(config: Any, mind: Any, text: str) -> int:
    """Gelen hedefleri kimliğe göre katar; var olanlar korunur."""
    path = config.mind_dir / "goals.jsonl"
    existing_ids = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing_ids.add(json.loads(line).get("id"))
                except json.JSONDecodeError:
                    continue
    added = 0
    lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("id") in existing_ids:
            continue
        lines.append(json.dumps(record, ensure_ascii=False))
        existing_ids.add(record.get("id"))
        added += 1
    if lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
        # Canlı zihin de görsün (yeniden başlatmadan).
        _reload_goals(mind, path)
    return added


def _reload_goals(mind: Any, path: Path) -> None:
    try:
        from .mind.store import Goal, _load
        _load(path, Goal, mind._goals)
    except Exception:
        pass  # dosya yazıldı; en kötü ihtimalle sonraki açılışta görünür


def _maybe_persona(config: Any, text: str) -> bool:
    """Hedefin ruhu yoksa doldurur. Varsa dokunmuyor — kimlik ezilmez."""
    path = _persona_path(config)
    if path is None:
        path = Path(config.workspace) / "persona.md"
    if path.is_file() and path.read_text(encoding="utf-8").strip():
        return False
    if not text.strip():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _merge_projects(config: Any, text: str) -> None:
    path = config.sessions_dir / "_projects.json"
    current: dict[str, str] = {}
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    try:
        incoming = json.loads(text)
    except json.JSONDecodeError:
        return
    if not isinstance(incoming, dict):
        return
    # Var olan atama korunur; yalnızca eksik olanlar gelir.
    for sid, name in incoming.items():
        current.setdefault(str(sid), str(name))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_skills(config: Any, zf: zipfile.ZipFile, names: set[str]) -> int:
    skills_dir = _skills_dir(config)
    if skills_dir is None:
        return 0
    added = 0
    for name in names:
        if not name.startswith(_SKILLS) or name.endswith("/"):
            continue
        rel = name[len(_SKILLS):]
        if not rel:
            continue
        dest = (skills_dir / rel).resolve()
        # Klasör dışına taşma (zip-slip) koruması.
        if skills_dir.resolve() not in dest.parents and dest != skills_dir.resolve():
            continue
        if dest.exists():
            continue  # var olan yeteneği ezme
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(name))
        added += 1
    return added


# -- yol yardımcıları ------------------------------------------------------


def _persona_path(config: Any) -> Path | None:
    path = getattr(config, "persona_path", None)
    return Path(path) if path else None


def _skills_dir(config: Any) -> Path | None:
    try:
        root = config.open_sandbox().root
    except Exception:
        return None
    return Path(root) / skills_mod.FOLDER


def _is_noise(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo")


def _safe_count(fn) -> int:
    try:
        return int(fn())
    except Exception:
        return 0
