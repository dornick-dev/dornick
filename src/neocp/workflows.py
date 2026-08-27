"""İş akışı (workflow) deposu.

Bir otomasyon yalnızca bir prompt metni değil: düğümler ve kenarlar
olarak duran bir grafik. Depo `.neocp/workflows/<id>.json` altında;
ayar sayfası ve ajan aynı dosyaları okuyup yazıyor.

Düğüm türleri kapalı bir enum değil (`mail_read`, `http`, `skill`,
`shell`, `agent`, `custom`, …): yeni bir düğüm türü eklemek için
depo şemasını kırmak gerekmiyor — koşucu bilmediği türü reddeder.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .events import utcnow

FOLDER = "workflows"

# Kimlik dosya adı oluyor; yol ayracı ve boşluk kabul yok.
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,48}$")


class WorkflowError(Exception):
    """Biçim hatası. Mesajı modele ve kullanıcıya gösteriliyor."""


@dataclass(slots=True)
class WorkflowNode:
    """Grafikteki tek bir adım.

    type: açık string — koşucu hangi türleri bildiğini kendi bilir.
    config: türe özel serbest nesne.
    secrets_needed: bu adımın istediği gizli anahtar adları.
    skill: `skill` türü için yetenek adı; diğerlerinde boş kalabilir.
    position: editör konumu ({"x": …, "y": …}); koşucu umursamaz.
    """

    id: str
    title: str = ""
    type: str = "custom"
    config: dict[str, Any] = field(default_factory=dict)
    secrets_needed: list[str] = field(default_factory=list)
    skill: str = ""
    position: dict[str, Any] = field(default_factory=dict)
    # Kullanıcı bu adımı ELLE düzenledi mi? Kendini onarma buna bakıyor:
    # modelin, kullanıcının bilerek yazdığı bir adımı arkasından yeniden
    # yazması, "düzeltme" değil sessizce geri alma olurdu.
    elle: bool = False


@dataclass(slots=True)
class WorkflowEdge:
    """İki düğüm arasındaki geçiş.

    `from_` JSON'da `from` olarak yazılır — `from` Python anahtar sözcüğü.
    on: hangi koşulda (ör. "ok", "hata", ""); boş = her zaman.
    """

    from_: str
    to: str
    on: str = ""


@dataclass(slots=True)
class Workflow:
    id: str
    title: str
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)
    updated: str = ""


def folder(state_dir: Path) -> Path:
    return Path(state_dir) / FOLDER


def new_id(state_dir: Path, title: str = "") -> str:
    """Kısa, çakışmaz kimlik: isteğe bağlı slug + 8 hex."""
    from . import canvas

    slug = canvas.slug(title, fallback="wf")[:24].strip("-") or "wf"
    root = folder(state_dir)
    for _ in range(8):
        candidate = f"{slug}-{uuid.uuid4().hex[:8]}"
        if not _ID.match(candidate):
            candidate = f"wf-{uuid.uuid4().hex[:8]}"
        if not (root / f"{candidate}.json").exists():
            return candidate
    raise WorkflowError("Kimlik üretilemedi — workflows klasörünü denetle.")


def _path(state_dir: Path, workflow_id: str) -> Path:
    ident = str(workflow_id or "").strip().lower()
    if not _ID.match(ident):
        raise WorkflowError(f"Geçersiz workflow kimliği: {workflow_id!r}")
    root = folder(state_dir).resolve()
    target = (root / f"{ident}.json").resolve()
    if target.parent != root:
        raise WorkflowError(f"Geçersiz workflow kimliği: {workflow_id!r}")
    return target


# -- biçim -------------------------------------------------------------


def _parse_node(raw: Any, index: int) -> WorkflowNode:
    if not isinstance(raw, dict):
        raise WorkflowError(f"nodes[{index}] bir nesne olmalı.")
    nid = str(raw.get("id") or "").strip()
    if not nid:
        raise WorkflowError(f"nodes[{index}].id boş olamaz.")
    config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
    position = raw.get("position") if isinstance(raw.get("position"), dict) else {}
    secrets = raw.get("secrets_needed") or []
    if not isinstance(secrets, list):
        raise WorkflowError(f"nodes[{index}].secrets_needed bir liste olmalı.")
    return WorkflowNode(
        id=nid,
        title=str(raw.get("title") or "").strip(),
        type=str(raw.get("type") or "custom").strip() or "custom",
        config=dict(config),
        secrets_needed=[str(s).strip() for s in secrets if str(s).strip()],
        skill=str(raw.get("skill") or "").strip(),
        position=dict(position),
        elle=bool(raw.get("elle")),
    )


def _parse_edge(raw: Any, index: int) -> WorkflowEdge:
    if not isinstance(raw, dict):
        raise WorkflowError(f"edges[{index}] bir nesne olmalı.")
    # JSON `from`; eski / Python yanından `from_` de kabul.
    src = str(raw.get("from") if "from" in raw else raw.get("from_") or "").strip()
    dst = str(raw.get("to") or "").strip()
    if not src or not dst:
        raise WorkflowError(f"edges[{index}] from ve to zorunlu.")
    return WorkflowEdge(from_=src, to=dst, on=str(raw.get("on") or "").strip())


def parse(raw: Any) -> Workflow:
    """Sözlükten workflow. Temel yapı: nodes ve edges listeleri."""
    if not isinstance(raw, dict):
        raise WorkflowError("Workflow bir nesne olmalı.")

    ident = str(raw.get("id") or "").strip().lower()
    if not _ID.match(ident):
        raise WorkflowError(
            "id küçük harf, rakam, tire ve alt çizgiden oluşmalı "
            f"(verilen: {raw.get('id')!r})."
        )

    title = str(raw.get("title") or "").strip()
    if not title:
        raise WorkflowError("title boş olamaz.")

    nodes_raw = raw.get("nodes")
    edges_raw = raw.get("edges")
    if not isinstance(nodes_raw, list):
        raise WorkflowError("nodes bir liste olmalı.")
    if not isinstance(edges_raw, list):
        raise WorkflowError("edges bir liste olmalı.")

    nodes = [_parse_node(item, i) for i, item in enumerate(nodes_raw, start=1)]
    edges = [_parse_edge(item, i) for i, item in enumerate(edges_raw, start=1)]

    return Workflow(
        id=ident,
        title=title,
        nodes=nodes,
        edges=edges,
        updated=str(raw.get("updated") or ""),
    )


def to_dict(wf: Workflow) -> dict[str, Any]:
    """Disk / API biçimi: kenarda `from` anahtarı."""
    return {
        "id": wf.id,
        "title": wf.title,
        "nodes": [asdict(n) for n in wf.nodes],
        "edges": [{"from": e.from_, "to": e.to, "on": e.on} for e in wf.edges],
        "updated": wf.updated,
    }


def validate(raw: Any) -> Workflow:
    """Temel yapı doğrulaması — parse ile aynı kapı."""
    return parse(raw)


# -- depo --------------------------------------------------------------


def list_all(state_dir: Path) -> list[Workflow]:
    """Klasördeki bütün akışlar. Bozuk dosya listeyi düşürmez."""
    root = folder(state_dir)
    if not root.is_dir():
        return []

    found: list[Workflow] = []
    for path in sorted(root.glob("*.json")):
        try:
            found.append(parse(json.loads(path.read_text(encoding="utf-8"))))
        except (WorkflowError, json.JSONDecodeError, OSError, TypeError):
            continue
    return found


def get(state_dir: Path, workflow_id: str) -> Workflow | None:
    try:
        path = _path(state_dir, workflow_id)
    except WorkflowError:
        return None
    if not path.is_file():
        return None
    try:
        return parse(json.loads(path.read_text(encoding="utf-8")))
    except (WorkflowError, json.JSONDecodeError, OSError, TypeError):
        return None


def save(state_dir: Path, raw: Any) -> Workflow:
    """Akışı yazar. Var olanı günceller, yoksa oluşturur."""
    data = dict(raw) if isinstance(raw, dict) else raw
    if isinstance(data, dict) and not str(data.get("id") or "").strip():
        data = {**data, "id": new_id(state_dir, str(data.get("title") or ""))}
    wf = parse(data)
    wf.updated = utcnow()
    path = _path(state_dir, wf.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(to_dict(wf), ensure_ascii=False, indent=2) + "\n"
    temp = path.with_suffix(".tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(path)
    return wf


def remove(state_dir: Path, workflow_id: str) -> bool:
    try:
        path = _path(state_dir, workflow_id)
    except WorkflowError:
        return False
    if not path.is_file():
        return False
    path.unlink()
    return True
