"""Devices: a common format for the physical and remote things the agent connects to.

A PLC, a camera, an arm on a serial port, an MCP server — all very different
things, and writing a separate structure for each does not scale. Three
things are common, and the format pins down only those:

    what it is            kind + name + summary
    how to connect        link (free-form: each protocol has its own fields)
    where to touch it     points (addresses, endpoints, channels)

`link` is deliberately schemaless. Modbus has host/port, a serial port has
baud, MCP has a command line. Trying to force all of them into one schema
produces either a mould that fits no device or a dict that says nothing.

Records live inside the workshop, one JSON file each in the `cihazlar/`
folder. They can be added two ways, and both write to the same file:

    user   from the settings page or by dropping a file into the folder
    agent  during conversation with the `device` tool

A device does nothing on its own: it says what it is and where to connect.
The thing that does the work is the skill attached to it — the script the
agent writes for itself. The `skills` field ties the two together.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Folder inside the workshop where devices live.
FOLDER = "cihazlar"

# Device kinds. The list is closed: every kind has a counterpart on the
# stage, and leaving it free made "plc", "PLC" and "Plc" three separate kinds.
KINDS = ("plc", "camera", "serial", "usb", "network", "mcp", "other")

# The word shown under the kind on the stage. "tanımlı" is true for all of
# them but says nothing; when the user looks at the list they want to read
# what is what.
KIND_STATE = {
    "plc": "makine",
    "camera": "kamera",
    "serial": "seri port",
    "usb": "usb",
    "network": "ağ",
    "mcp": "mcp sunucusu",
    "other": "cihaz",
}

# Identity: it becomes the file name, so no path separators or spaces.
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,48}$")


class DeviceError(Exception):
    """Format error. The message is shown directly to the model and the user."""


@dataclass(slots=True)
class Point:
    """A touchable point of the device: an address, an endpoint, a channel.

    In industry the real information is here. This row is where the
    sentence "that address opens the door" goes.
    """

    name: str
    address: str = ""
    note: str = ""
    # Readable or writable. Writing to the wrong side has a physical
    # consequence, so it stands apart.
    access: str = "read"


@dataclass(slots=True)
class Device:
    id: str
    name: str
    kind: str = "other"
    summary: str = ""
    # How to connect. Schemaless: each protocol has its own fields.
    link: dict[str, Any] = field(default_factory=dict)
    points: list[Point] = field(default_factory=list)
    # The skills that drive this device. The thing that does the work is not
    # the device but the script attached to it; this field ties the two.
    skills: list[str] = field(default_factory=list)
    notes: str = ""
    # Who added it. It is not right for the agent to silently change or
    # delete a record the user wrote by hand.
    source: str = "dornick"


def folder(sandbox_root: Path) -> Path:
    return Path(sandbox_root) / FOLDER


# -- format ------------------------------------------------------------


def parse(raw: Any) -> Device:
    """Dict to device. Names what is missing or wrong.

    The error message goes to the model: saying "invalid" forces it to
    guess, saying which field is invalid and why fixes it.
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


# -- folder ------------------------------------------------------------


def load(sandbox_root: Path) -> tuple[list[Device], list[str]]:
    """All devices in the folder. (devices, errors)

    A broken file does not bring the list down: losing every device because
    of a half-written hand-edited JSON is far worse than that one file.
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
    """Writes the device. Updates an existing one, creates it otherwise."""
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


# -- narration ---------------------------------------------------------


def _where(device: Device) -> str:
    """Reduces the link to one line: "modbus-tcp 192.168.1.50:502"."""
    link = device.link
    protocol = str(link.get("protocol") or link.get("transport") or "")
    host = str(link.get("host") or link.get("url") or link.get("port_name") or
               link.get("command") or "")
    port = link.get("port")
    where = host + (f":{port}" if host and port else "")
    return " ".join(part for part in (protocol, where) if part)


def line(device: Device) -> str:
    """The single line shown in the list."""
    parts = [device.kind]
    if where := _where(device):
        parts.append(where)
    if device.points:
        parts.append(f"{len(device.points)} adres")
    if device.skills:
        parts.append("yetenek: " + ", ".join(device.skills))
    return f"{device.id}  {device.name} — " + " · ".join(parts)


def briefing(sandbox_root: Path) -> str:
    """The short summary that goes into the system prompt.

    Having the agent learn what it is connected to by calling a tool every
    time is both slow and pointless: it should know its own body. Detail
    (addresses, notes) is not here — `device action=show` gives that,
    because all the addresses of ten devices bloat the prompt.
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
