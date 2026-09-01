"""Cihazlar: ajanın bağlandığı fiziksel ve uzak şeyler için ortak biçim.

Bir PLC, bir kamera, bir seri porttaki kol, bir MCP sunucusu — hepsi
birbirinden çok farklı şeyler ve her biri için ayrı bir yapı yazmak
ölçeklenmiyor. Ortak olan üç şey var, ve biçim yalnızca onları sabitliyor:

    ne olduğu      kind + name + summary
    nasıl bağlanılacağı   link (serbest: her protokolün kendi alanları var)
    neresine dokunulacağı points (adresler, uçlar, kanallar)

`link` bilerek şemasız. Modbus'un host/port'u var, seri portun baud'u,
MCP'nin komut satırı. Hepsini tek bir şemaya sokmaya çalışmak ya her
cihaza uymayan bir kalıp ya da hiçbir şey söylemeyen bir sözlük üretir.

Kayıtlar atölyenin içinde, `cihazlar/` klasöründe birer JSON dosyası.
İki yoldan da eklenebiliyor ve ikisi aynı dosyaya yazıyor:

    kullanıcı  ayarlar sayfasından ya da klasöre dosya bırakarak
    ajan       konuşma sırasında `device` aracıyla

Bir cihaz kendi başına bir şey yapmıyor: ne olduğunu ve nereye
bağlanılacağını söylüyor. İşi yapan şey ona bağlanan yetenek — ajanın
kendine yazdığı betik. `skills` alanı ikisini birbirine bağlıyor.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Atölye içinde cihazların durduğu klasör.
FOLDER = "cihazlar"

# Cihaz türleri. Liste kapalı: sahnede her türün bir karşılığı var ve
# serbest bırakmak "plc" ile "PLC" ile "Plc"yi üç ayrı tür yapıyordu.
KINDS = ("plc", "camera", "serial", "usb", "network", "mcp", "other")

# Sahnede türün altında görünen kelime. "tanımlı" hepsi için doğru ama
# hiçbir şey söylemiyor; kullanıcı listeye baktığında neyin ne olduğunu
# okumak istiyor.
KIND_STATE = {
    "plc": "makine",
    "camera": "kamera",
    "serial": "seri port",
    "usb": "usb",
    "network": "ağ",
    "mcp": "mcp sunucusu",
    "other": "cihaz",
}

# Kimlik: dosya adı oluyor, o yüzden yol ayracı ya da boşluk kabul yok.
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,48}$")


class DeviceError(Exception):
    """Biçim hatası. Mesajı doğrudan modele ve kullanıcıya gösteriliyor."""


@dataclass(slots=True)
class Point:
    """Cihazın dokunulabilir bir noktası: bir adres, bir uç, bir kanal.

    Sanayide asıl bilgi burada. "Şu adres kapıyı açıyor" cümlesinin
    gideceği yer bu satır.
    """

    name: str
    address: str = ""
    note: str = ""
    # Okunur mu, yazılır mı. Yanlış tarafa yazmak fiziksel bir sonuç
    # doğuruyor, o yüzden ayrı duruyor.
    access: str = "read"


@dataclass(slots=True)
class Device:
    id: str
    name: str
    kind: str = "other"
    summary: str = ""
    # Nasıl bağlanılacağı. Şemasız: her protokolün kendi alanları var.
    link: dict[str, Any] = field(default_factory=dict)
    points: list[Point] = field(default_factory=list)
    # Bu cihazı süren yetenekler. İşi yapan şey cihaz değil, ona bağlanan
    # betik; ikisini bu alan birbirine bağlıyor.
    skills: list[str] = field(default_factory=list)
    notes: str = ""
    # Kim ekledi. Kullanıcının elle yazdığı bir kaydı ajanın sessizce
    # değiştirmesi ya da silmesi doğru değil.
    source: str = "dornick"


def folder(sandbox_root: Path) -> Path:
    return Path(sandbox_root) / FOLDER


# -- biçim -------------------------------------------------------------


def parse(raw: Any) -> Device:
    """Sözlükten cihaza. Eksik ya da yanlış olanı adıyla söylüyor.

    Hata mesajı modele gidiyor: "geçersiz" demek onu tahmin etmeye
    zorluyor, hangi alanın neden geçersiz olduğunu söylemek düzeltiyor.
    """
    if not isinstance(raw, dict):
        raise DeviceError("Cihaz bir nesne olmalı.")

    ident = str(raw.get("id") or "").strip().lower()
    if not _ID.match(ident):
        raise DeviceError(
            "id küçük harf, rakam, tire ve alt çizgiden oluşmalı "
            f"(verilen: {raw.get('id')!r})."
        )

    name = str(raw.get("name") or "").strip()
    if not name:
        raise DeviceError("name boş olamaz: cihazın ekranda görünen adı.")

    kind = str(raw.get("kind") or "other").strip().lower()
    if kind not in KINDS:
        raise DeviceError(f"kind şunlardan biri olmalı: {', '.join(KINDS)}.")

    link = raw.get("link") or {}
    if not isinstance(link, dict):
        raise DeviceError("link bir nesne olmalı (host, port, protocol gibi alanlar).")

    points = []
    for index, item in enumerate(raw.get("points") or [], start=1):
        if not isinstance(item, dict):
            raise DeviceError(f"points[{index}] bir nesne olmalı.")
        label = str(item.get("name") or "").strip()
        if not label:
            raise DeviceError(f"points[{index}].name boş olamaz.")
        points.append(
            Point(
                name=label,
                address=str(item.get("address") or ""),
                note=str(item.get("note") or ""),
                access=str(item.get("access") or "read"),
            )
        )

    skills = [str(s).strip() for s in (raw.get("skills") or []) if str(s).strip()]

    return Device(
        id=ident,
        name=name,
        kind=kind,
        summary=str(raw.get("summary") or "").strip(),
        link=link,
        points=points,
        skills=skills,
        notes=str(raw.get("notes") or "").strip(),
        source=str(raw.get("source") or "dornick"),
    )


def to_dict(device: Device) -> dict[str, Any]:
    return asdict(device)


# -- klasör ------------------------------------------------------------


def load(sandbox_root: Path) -> tuple[list[Device], list[str]]:
    """Klasördeki bütün cihazlar. (cihazlar, hatalar)

    Bozuk bir dosya listeyi düşürmüyor: elle yazılmış yarım bir JSON
    yüzünden bütün cihazların kaybolması, o dosyadan çok daha kötü.
    """
    root = folder(sandbox_root)
    if not root.is_dir():
        return [], []

    devices: list[Device] = []
    broken: list[str] = []
    for path in sorted(root.glob("*.json")):
        try:
            devices.append(parse(json.loads(path.read_text(encoding="utf-8"))))
        except (DeviceError, json.JSONDecodeError, OSError) as exc:
            broken.append(f"{path.name}: {exc}")
    return devices, broken


def find(sandbox_root: Path, ident: str) -> Device | None:
    devices, _broken = load(sandbox_root)
    return next((d for d in devices if d.id == ident), None)


def save(sandbox_root: Path, raw: Any) -> Device:
    """Cihazı yazar. Var olanı günceller, yoksa oluşturur."""
    device = parse(raw)
    root = folder(sandbox_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{device.id}.json").write_text(
        json.dumps(to_dict(device), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return device


def remove(sandbox_root: Path, ident: str) -> bool:
    path = folder(sandbox_root) / f"{ident}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True


# -- anlatım -----------------------------------------------------------


def _where(device: Device) -> str:
    """Bağlantıyı tek satıra indirir: "modbus-tcp 192.168.1.50:502"."""
    link = device.link
    protocol = str(link.get("protocol") or link.get("transport") or "")
    host = str(link.get("host") or link.get("url") or link.get("port_name") or
               link.get("command") or "")
    port = link.get("port")
    where = host + (f":{port}" if host and port else "")
    return " ".join(part for part in (protocol, where) if part)


def line(device: Device) -> str:
    """Listede görünen tek satır."""
    parts = [device.kind]
    if where := _where(device):
        parts.append(where)
    if device.points:
        parts.append(f"{len(device.points)} adres")
    if device.skills:
        parts.append("yetenek: " + ", ".join(device.skills))
    return f"{device.id}  {device.name} — " + " · ".join(parts)


def briefing(sandbox_root: Path) -> str:
    """Sistem istemine giren kısa özet.

    Ajanın neye bağlı olduğunu her seferinde araç çağırarak öğrenmesi
    hem yavaş hem anlamsız: kendi bedenini biliyor olması gerekiyor.
    Ayrıntı (adresler, notlar) burada değil — onu `device action=show`
    veriyor, çünkü on cihazın bütün adresleri istemi şişiriyor.
    """
    devices, _broken = load(sandbox_root)
    if not devices:
        return ""

    rows = "\n".join("  " + line(device) for device in devices)
    return (
        "Bağlı cihazlar (ayrıntı için `device action=show id=...`):\n"
        f"{rows}\n"
        "Bir cihazla gerçekten iş yapmak için ona bir yetenek yaz "
        "(`skill action=new`): cihaz kaydı yalnızca nereye bağlanılacağını "
        "söyler, işi yapan betiktir."
    )
