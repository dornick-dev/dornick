"""Device tool — the agent recording what it is connected to.

The user describes a device once: "this PC's IP is this, you will speak
Modbus over that port, this address opens the gate." If that knowledge
stays inside the conversation it is gone by the next session and has to
be retold every time.

It is recorded here — in a shared format, inside the workshop. The
record does nothing by itself: it says where to connect. What does the
work is the skill bound to it (`skill action=new`). The two are separate
because over time a device may get several skills, and one skill may
work with several devices.

The user can also write the same files by hand (from the settings page
or by dropping JSON into the folder). That is why there is a single
format: both sides write to the same place.
"""

from __future__ import annotations

import json
from typing import Any

from .. import devices
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Bağlı cihazlarını kaydeder ve okur: PLC, kamera, seri porttaki kol, USB
aygıtı, uzak servis.

Ne zaman kullan: kullanıcı bir cihaz tarif ettiğinde (IP, port, protokol,
adres, hangi adres ne yapıyor) **hemen** kaydet. Bir sonraki oturumda o
bilgi yalnızca burada duruyor.

  list    cihazlarını göster
  show    bir cihazın bütün ayrıntısı (adresler, notlar)
  save    ekle ya da güncelle
  remove  sil — kaydı kaldırır, ilgili anıları SİLMEZ. Zihinde bu
          cihaza dair kayıt varsa kullanıcıya sor: dursun mu, sileyim
          mi? Onay olmadan `mind_memory forget` etme.

Kayıt tek başına bir şey yapmıyor — nereye bağlanılacağını söylüyor. O
cihazla iş yapmak için ona bir yetenek yaz (`skill action=new`) ve
yeteneğin adını `skills` alanına koy.

save için alanlar:
  id       kısa kimlik, küçük harf (kapi-plc)
  name     görünen ad (kapı PLC'si)
  kind     plc | camera | serial | usb | network | mcp | other
  summary  bir cümlede ne olduğu
  link     nasıl bağlanılacağı — serbest nesne
           {"protocol": "modbus-tcp", "host": "192.168.1.50", "port": 502}
           {"protocol": "rtsp", "url": "rtsp://..."}
           {"protocol": "serial", "port_name": "COM3", "baud": 9600}
  points   dokunulacak noktalar (adresler):
           [{"name": "kapı aç", "address": "%QX0.1", "access": "write",
             "note": "1 yazınca açılıyor"}]
  skills   bu cihazı süren yeteneklerin adları
  notes    kullanıcının söylediği, biçime sığmayan her şey

Bilmediğin bir alanı uydurma — boş bırak ve kullanıcıya sor. Yanlış bir
adres fiziksel bir sonuç doğuruyor.
"""


def _dump(device: devices.Device) -> str:
    """A readable full dump of one device."""
    lines = [f"{device.name}  ({device.id})", f"tür: {device.kind}"]
    if device.summary:
        lines.append(device.summary)
    if device.link:
        lines.append("bağlantı: " + json.dumps(device.link, ensure_ascii=False))
    if device.points:
        lines.append(f"\n{len(device.points)} nokta:")
        for point in device.points:
            row = f"  {point.name}"
            if point.address:
                row += f"  [{point.address}]"
            row += f"  ({point.access})"
            if point.note:
                row += f" — {point.note}"
            lines.append(row)
    if device.skills:
        lines.append("\nyetenekler: " + ", ".join(device.skills))
    if device.notes:
        lines.append("\nnotlar: " + device.notes)
    lines.append(f"\nekleyen: {device.source}")
    return "\n".join(lines)


def _needles(device: devices.Device) -> list[str]:
    """The fragments to look for when searching memories about this device.

    Short, generic words (plc, tcp) stick to everything; id, name,
    address and host are enough. Measurement/level records usually carry
    the device name.
    """
    bits: list[str] = []
    for raw in (device.id, device.name, device.summary):
        text = " ".join(str(raw or "").replace("-", " ").split()).casefold()
        if len(text) >= 3:
            bits.append(text)
        for word in text.split():
            if len(word) >= 4:
                bits.append(word)
    for point in device.points:
        for raw in (point.name, point.address):
            text = " ".join(str(raw or "").split()).casefold()
            if len(text) >= 3:
                bits.append(text)
    host = str((device.link or {}).get("host") or (device.link or {}).get("url") or "")
    host = host.strip().casefold()
    if len(host) >= 4:
        bits.append(host)
    # Dedupe but keep the order: the first match is the more specific one (id, name).
    seen: set[str] = set()
    out: list[str] = []
    for bit in bits:
        if bit not in seen:
            seen.add(bit)
            out.append(bit)
    return out


def related_memories(mind: Any, device: devices.Device, *, limit: int = 8) -> list[Any]:
    """The related memories left in the mind after the device record is deleted."""
    tokens = _needles(device)
    if mind is None or not tokens:
        return []
    try:
        items = mind.memories()
    except Exception:
        return []
    found: list[Any] = []
    for mem in items:
        if getattr(mem, "deleted", False):
            continue
        blob = (getattr(mem, "searchable", lambda: "")() or "").casefold()
        if any(token in blob for token in tokens):
            found.append(mem)
            if len(found) >= limit:
                break
    return found


def _ask_about_memories(device: devices.Device, hits: list[Any]) -> str:
    if not hits:
        return (
            f"{device.id} silindi. Zihinde bu cihaza dair kayıt görünmüyor."
        )
    lines = [
        f"{device.id} kaydı sistemden silindi.",
        "Zihinde hâlâ buna dair kayıtlar var — onay olmadan silme:",
    ]
    for mem in hits:
        title = (getattr(mem, "title", "") or "").strip() or (getattr(mem, "id", "") or "")
        ident = getattr(mem, "id", "")
        lines.append(f"  · {title}  ({ident})")
    lines.append(
        "Kullanıcıya sor: bu anılar dursun mu, sileyim mi? "
        "Evet derse `mind_memory action=forget` ile id'leri sil."
    )
    return "\n".join(lines)


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="device",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["list", "show", "save", "remove"],
                    "description": "list: hepsi. show: biri. save: ekle/güncelle. remove: sil.",
                },
                "id": {"type": "string", "description": "Cihaz kimliği (show, remove, save)."},
                "name": {"type": "string", "description": "Görünen ad (save)."},
                "kind": {
                    "type": "string",
                    "enum": list(devices.KINDS),
                    "description": "Cihaz türü (save).",
                },
                "summary": {"type": "string", "description": "Bir cümlede ne olduğu (save)."},
                "link": {
                    "type": "object",
                    "description": "Nasıl bağlanılacağı — protocol, host, port gibi (save).",
                },
                "points": {
                    "type": "array",
                    "description": "Adresler: name, address, access, note (save).",
                    "items": {"type": "object"},
                },
                "skills": {
                    "type": "array",
                    "description": "Bu cihazı süren yeteneklerin adları (save).",
                    "items": {"type": "string"},
                },
                "notes": {"type": "string", "description": "Biçime sığmayan her şey (save)."},
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def device(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = ctx.sandbox.root
        action = str(args.get("action") or "")

        if action == "list":
            found, broken = devices.load(root)
            if not found and not broken:
                return ToolResult(
                    "Kayıtlı cihazın yok. Kullanıcı bir cihaz tarif ettiğinde "
                    "`action=save` ile kaydet."
                )
            lines = [f"{len(found)} cihaz:"]
            lines += ["  " + devices.line(item) for item in found]
            if broken:
                lines.append("\nokunamayan dosyalar:\n" + "\n".join(broken))
            return ToolResult("\n".join(lines))

        ident = str(args.get("id") or "").strip().lower()

        if action == "show":
            if not ident:
                return ToolResult.error("`id` gerekli.")
            found = devices.find(root, ident)
            if found is None:
                return ToolResult.error(f"Böyle bir cihaz yok: {ident}")
            return ToolResult(_dump(found))

        if action == "save":
            # When overwriting an existing record, fields not given are
            # preserved: making the model rewrite the whole device to add a
            # single address is both long and prone to losing data.
            existing = devices.find(root, ident) if ident else None
            raw = devices.to_dict(existing) if existing else {"id": ident, "source": "dornick"}

            for field in ("name", "kind", "summary", "link", "points", "skills", "notes"):
                if args.get(field) is not None:
                    raw[field] = args[field]
            raw["id"] = ident or raw.get("id", "")

            try:
                saved = devices.save(root, raw)
            except devices.DeviceError as exc:
                return ToolResult.error(str(exc))

            return ToolResult(
                content=(
                    f"{'Güncellendi' if existing else 'Kaydedildi'}: {devices.line(saved)}\n"
                    + ("" if saved.skills else
                       "Bu cihazla iş yapmak için ona bir yetenek yaz: `skill action=new`.")
                ),
                detail={"id": saved.id},
            )

        if action == "remove":
            if not ident:
                return ToolResult.error("`id` gerekli.")
            found = devices.find(root, ident)
            if found is None:
                return ToolResult.error(f"Böyle bir cihaz yok: {ident}")
            # The agent deleting a record the user wrote by hand on its own
            # is not right; if wanted, the user deletes it from settings.
            if found.source != "dornick":
                return ToolResult.error(
                    f"{ident} kullanıcı tarafından eklenmiş. Silmek istiyorsa "
                    "ayarlar › cihazlar bölümünden silebilir."
                )
            devices.remove(root, ident)
            hits: list[Any] = []
            try:
                from ..mind import open_mind
                mind = open_mind(
                    ctx.config.mind_dir,
                    ctx.config.sessions_dir,
                    getattr(ctx.session, "id", "") or "",
                )
                hits = related_memories(mind, found)
            except Exception:
                hits = []
            try:
                ctx.session.log.note("device_removed", id=ident)
            except Exception:
                pass
            return ToolResult(
                _ask_about_memories(found, hits),
                detail={"id": ident, "memories": [getattr(m, "id", "") for m in hits]},
            )

        return ToolResult.error(f"Bilinmeyen işlem: {action}")
