"""Artifact deposu: kalıcı, adreslenebilir, güncellenebilir sayfalar.

Sohbet mesajı akıp gider; ajanın ürettiği asıl teslimat (rapor, pano,
görselleştirme) akıntıda kaybolmamalı. Artifact bunun için var: HTML bir
kez yayınlanır, kısa okunur bir kimlik alır ve hep aynı adreste yaşar —
`/artifact/<id>/`. Sonraki turlarda aynı kimliğe yeni sürüm yazılır; adres
değişmez, eski sürümler bir süre saklanır.

Depo atölyede değil `.neocp/artifacts/` altında: bu ajanın çalışma dosyası
değil, programın sunduğu bir yüzey (oturum ve zihin kayıtlarıyla aynı
mahalle). Atölye sınırı dosya araçlarını bağlıyor; burada yazma bu modülün
kendi yolları üzerinden yapılıyor ve kimlik sıkı bir desenden geçmeden
hiçbir yol kurulmuyor — istekten gelen bir `../` diske hiç dokunamıyor.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from . import canvas
from .events import utcnow

# state_dir altındaki depo klasörü.
FOLDER = "artifacts"

# Eski sürümlerin durduğu alt klasör ve tutulan sürüm sayısı. Sınırsız
# biriktirmek diski çöplüğe çevirir; beş sürüm "az önceki halime dön"
# için yeter.
VERSIONS = "surumler"
KEEP_VERSIONS = 5

# Silinen artifact'ın taşındığı yer: kalıcı silme yok, elle geri alınabilir.
TRASH = ".geri-donusum"

# Kimlik deseni: başlık slug'ı + 4 hex. Yol bu desenden geçmeden kurulmuyor;
# nokta, ayraç ve boşluk hiç giremiyor — dizin dışına çıkma buradan başlar.
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class ArtifactError(Exception):
    """Depo hatası. Araç katmanı bunu öğretici bir hataya çeviriyor."""


def folder(state_dir: Path) -> Path:
    return Path(state_dir) / FOLDER


def new_id(state_dir: Path, title: str) -> str:
    """Kısa, okunur, çakışmaz kimlik: baslik-slug-4hex.

    Slug tek başına yetmez: "Günlük rapor" her gün yayınlanır ve ikincisi
    ilkini sessizce ezerdi. 4 hex'lik ek çakışmayı pratikte bitiriyor;
    yine de denk gelirse yeniden çekiliyor.
    """
    slug = canvas.slug(title, fallback="artifact")[:40].strip("-") or "artifact"
    for _ in range(8):
        candidate = f"{slug}-{uuid.uuid4().hex[:4]}"
        if not (folder(state_dir) / candidate).exists():
            return candidate
    raise ArtifactError("Kimlik üretilemedi — depo klasörünü denetle.")


def _dir(state_dir: Path, artifact_id: str) -> Path:
    """Kimliği doğrulayıp klasörünü döndürür. Desen + çözümleme birlikte:
    desen `..` ve ayracı zaten kesiyor, çözümleme sembolik bağa karşı
    ikinci kilit."""
    if not ID_PATTERN.match(artifact_id or ""):
        raise ArtifactError(f"Geçersiz artifact kimliği: {artifact_id!r}")
    root = folder(state_dir).resolve()
    target = (root / artifact_id).resolve()
    if target.parent != root:
        raise ArtifactError(f"Geçersiz artifact kimliği: {artifact_id!r}")
    return target


def page_path(state_dir: Path, artifact_id: str) -> Path | None:
    """Servis edilecek sayfa; kimlik bozuksa ya da sayfa yoksa None.

    Sunucu bunun üzerinden servis ediyor: yol istekten değil buradan
    kuruluyor, kaçış denemesi diske hiç dokunmadan eleniyor.
    """
    try:
        page = _dir(state_dir, artifact_id) / "index.html"
    except ArtifactError:
        return None
    return page if page.is_file() else None


def read_meta(state_dir: Path, artifact_id: str) -> dict[str, Any]:
    path = _dir(state_dir, artifact_id) / "meta.json"
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactError(f"Artifact bulunamadı: {artifact_id}") from exc
    if not isinstance(meta, dict):
        raise ArtifactError(f"Artifact kaydı bozuk: {artifact_id}")
    return meta


def _write_meta(target: Path, meta: dict[str, Any]) -> None:
    (target / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def publish(state_dir: Path, title: str, html: str) -> dict[str, Any]:
    """Yeni bir artifact yayınlar; meta kaydını döndürür."""
    title = (title or "").strip()
    if not title:
        raise ArtifactError("`title` boş — artifact'ın bir adı olmalı.")
    if not (html or "").strip():
        raise ArtifactError("`html` boş — yayınlanacak bir sayfa yok.")

    artifact_id = new_id(state_dir, title)
    target = _dir(state_dir, artifact_id)
    target.mkdir(parents=True, exist_ok=True)
    (target / "index.html").write_text(html, encoding="utf-8")

    now = utcnow()
    meta = {"id": artifact_id, "title": title, "created": now,
            "updated": now, "surum": 1}
    _write_meta(target, meta)
    return meta


def update(state_dir: Path, artifact_id: str, html: str,
           title: str | None = None) -> dict[str, Any]:
    """Aynı kimliğe yeni sürüm yazar; adres değişmez.

    Eski sayfa `surumler/<n>.html` olarak saklanır (son KEEP_VERSIONS);
    yanlış bir güncelleme önceki hali kaybettirmemeli.
    """
    if not (html or "").strip():
        raise ArtifactError("`html` boş — güncellenecek bir sayfa yok.")
    target = _dir(state_dir, artifact_id)
    meta = read_meta(state_dir, artifact_id)

    page = target / "index.html"
    if page.is_file():
        versions = target / VERSIONS
        versions.mkdir(exist_ok=True)
        shutil.copy2(page, versions / f"{meta.get('surum', 1)}.html")
        _prune_versions(versions)

    page.write_text(html, encoding="utf-8")
    meta["surum"] = int(meta.get("surum", 1)) + 1
    meta["updated"] = utcnow()
    if title and title.strip():
        meta["title"] = title.strip()
    _write_meta(target, meta)
    return meta


def _prune_versions(versions: Path) -> None:
    kept = sorted(
        (p for p in versions.glob("*.html") if p.stem.isdigit()),
        key=lambda p: int(p.stem),
    )
    for stale in kept[:-KEEP_VERSIONS]:
        stale.unlink(missing_ok=True)


def listing(state_dir: Path) -> list[dict[str, Any]]:
    """Depodaki artifact'lar, son güncellenen en üstte.

    Bozuk bir kayıt (meta'sı silinmiş klasör) listeyi düşürmüyor —
    sessizce atlanıyor; çöp klasörü de görünmüyor.
    """
    root = folder(state_dir)
    rows: list[dict[str, Any]] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return rows
    for child in children:
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            meta = read_meta(state_dir, child.name)
        except ArtifactError:
            continue
        rows.append(meta)
    rows.sort(key=lambda m: str(m.get("updated", "")), reverse=True)
    return rows


def remove(state_dir: Path, artifact_id: str) -> dict[str, Any]:
    """Artifact'ı çöpe taşır — kalıcı silme yok, elle geri alınabilir."""
    target = _dir(state_dir, artifact_id)
    if not target.is_dir():
        raise ArtifactError(f"Artifact bulunamadı: {artifact_id}")
    trash = folder(state_dir) / TRASH
    trash.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().replace(":", "").replace(".", "")
    moved = trash / f"{artifact_id}-{stamp}"
    shutil.move(str(target), str(moved))
    return {"ok": True, "id": artifact_id, "moved": str(moved)}


def address(artifact_id: str) -> str:
    """Sayfanın arayüzdeki adresi. Tek yerde dursun: araç, sunucu ve
    arayüz aynı yolu söylemeli."""
    return f"/artifact/{artifact_id}/"
