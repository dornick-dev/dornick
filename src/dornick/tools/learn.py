"""Yetenek aracı — ajanın kendine yeni beceri kazandırması.

Her yeni işi elle araç olarak eklemek ölçeklenmiyor. Bir haritaya rota
çizmek, PLC adresinden değer okumak, USB'den gelen cihazı yoklamak: bunların
ortak yanı, hepsinin ajanın kendisinin yazabileceği kadar küçük olması.

Akış:

    skill action=write   tam dosyayı yazar, doğrular, yükler — asıl yol
    skill action=new     boş iskelet (yalnız ad+açıklama); gövde sonra write
    skill action=load    klasördekileri yeniden yükle
    skill action=list    yüklü yetenekler
    skill action=remove  dosyayı sil

Yetki açısından yeni bir kapı açmıyor: yetenek de `shell` gibi tam Python
çalıştırıyor. Farkı iş adlandırılmış, şemalı ve tekrar kullanılabilir olması.
"""

from __future__ import annotations

from typing import Any

from .. import skills
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Kendine yeni yetenek kazandırır. Bir yetenek, atölyendeki `yetenekler/`
klasöründe duran bir Python dosyası; yüklendiğinde senin araçlarından biri
olur ve bir daha yazmana gerek kalmaz.

Ne zaman kullan: aynı işi ikinci kez yapıyorsan, ya da kullanıcı bir cihaz /
biçim / servis tarif ettiyse (PLC adresleri, USB cihazı, harita çizimi, ikinci
bir kamera). Tek seferlik bir iş için yetenek yazma — `shell` ile yap.

Asıl yol `action=write`: `name` + `code` (tam Python dosyası). Doğrulanır
ve o anda araç olur — `edit_file` + `load` turu yok. Hata varsa mesajı
okuyup `write` ile düzelt.

Dosya örneği:
  NAME = "topla"
  DESCRIPTION = "İki sayıyı toplar."
  SCHEMA = {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}
  def run(args, ctx):
      return str(args["a"] + args["b"])

NAME, `name` ile aynı olmalı (küçük harf, alt çizgi). `ctx.sandbox.root`
atölye, dönen metin sana gelir.

Tanımadığın bir dış kaynak için yetenek yazarken — bir servis, bir cihaz,
bir veri akışı, her ne olursa — tarif bekleme, kaynağı önce kendin keşfet:

  1. Dokun: gerçek bir istek ya da okuma yap, ham cevabı gör.
  2. İncele: hangi alanlar var, değerler ne anlama geliyor, neresi sabit
     neresi değişiyor. Gerekirse farklı girdilerle birkaç kez yokla.
  3. Yeteneği bu gözleme göre yaz — varsaydığın biçime göre değil.
  4. Yükledikten sonra gerçek kaynağa karşı çalıştırıp sonucu doğrula.

Kullanıcının yalnızca bir adres vermesi eksik tarif değildir; gerisini
bulmak senin işin. Anlamlandıramadığın bir değeri kullanıcıya sorabilirsin,
ama sormadan önce kendi yoklamanı yapmış ol.

**Keşfini bir kez yap, sonra kaydet.** Bir cihazı ya da servisi ilk kez
okumak yavaştır: keşif, deneme, hata ayıklama tur tur sürer (her tur modele
gidip gelmek saniyeler). Ama bu emeği bir `skill` olarak kaydetmezsen, aynı
kullanıcı ikinci kez sorduğunda HER ŞEYİ baştan yaparsın — dakikalarca. Bir
cihazdan/servisten değer okumayı çözdüğün an, onu bir yeteneğe dök: adresi,
biçimi, bağlantı kurma yöntemini (ör. her okumada taze bağlantı) hepsi orada
kalsın. O zaman bir sonraki okuma tek bir araç çağrısı olur, saniyeler.
Atölyendeki `yetenekler/` klasörü boşsa, tekerleği her seferinde yeniden
icat ediyorsun demektir — bu en pahalı çalışma biçimidir.

Dosya biçimi:
  NAME / DESCRIPTION / SCHEMA (JSON Schema) / run(args, ctx) -> str

`ctx.sandbox.root` atölyenin yolu, `ctx.config` ayarlar. Dönen metin sana
araç sonucu olarak gelir.
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="skill",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["write", "new", "load", "list", "remove"],
                    "description": (
                        "write: tam dosyayı yaz, doğrula, yükle (asıl yol). "
                        "new: boş iskelet. load: klasördekileri yükle. "
                        "list: yüklü olanları göster. remove: dosyayı sil."
                    ),
                },
                "name": {"type": "string", "description": "Yetenek adı (write, new, remove)."},
                "description": {
                    "type": "string",
                    "description": "Ne yaptığı — bu metin senin araç açıklaman olacak (new).",
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Tam Python dosyası (write). NAME, DESCRIPTION, SCHEMA "
                        "ve run(args, ctx) içermeli."
                    ),
                },
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def skill(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = ctx.sandbox.root
        action = str(args.get("action") or "")

        if action == "write" or (action == "new" and str(args.get("code") or "").strip()):
            name = str(args.get("name") or "").strip()
            if not name:
                return ToolResult.error("`name` gerekli. Yeteneğe bir ad ver.")
            try:
                skill = skills.save(root, name, str(args.get("code") or ""))
            except skills.SkillError as exc:
                return ToolResult.error(str(exc))
            added, updated = skills.register(registry, [skill])
            loaded = skill.name
            state = "yazıldı ve yüklendi" if loaded in added else (
                "yazıldı ve tazelendi" if loaded in updated else "yazıldı"
            )
            return ToolResult(
                content=(
                    f"{skill.path.name} {state}. "
                    "Bir sonraki turdan itibaren araç olarak çağırabilirsin."
                ),
                detail={"path": str(skill.path), "loaded": added, "updated": updated},
            )

        if action == "new":
            name = str(args.get("name") or "").strip()
            if not name:
                return ToolResult.error("`name` gerekli. Yeteneğe bir ad ver.")
            try:
                path = skills.scaffold(root, name, str(args.get("description") or ""))
            except skills.SkillError as exc:
                return ToolResult.error(str(exc))

            return ToolResult(
                content=(
                    f"İskelet açıldı: {path}\n"
                    "Gövdeyi `skill action=write name=" + path.stem + " code=...` "
                    "ile yaz — doğrulanır ve yüklenir."
                ),
                detail={"path": str(path)},
            )

        if action == "load":
            found, broken = skills.discover(root)
            added, updated = skills.register(registry, found)

            lines: list[str] = []
            if added:
                lines.append(f"Yüklendi: {', '.join(added)}")
            if updated:
                # Dosya düzeltilip yeniden yüklendi: eski hali gitti, bir
                # sonraki çağrı taze kodu çalıştırıyor. Bunu açıkça söylemek
                # gerekiyor — model eskiden "belki hâlâ eski kod" diye
                # kabuğa düşüyordu.
                lines.append(
                    f"Tazelendi: {', '.join(updated)} — bir sonraki çağrı "
                    "dosyanın yeni halini çalıştırır."
                )
            skipped = [s.name for s in found if s.name not in added and s.name not in updated]
            if skipped:
                lines.append(f"Adı yerleşik bir araçla çakışıyor, atlandı: {', '.join(skipped)}")
            if broken:
                # Hata metni ayrıntılı: modelin kendi yazdığı kodu
                # düzeltebilmesi için satır numarası lazım.
                lines.append("Yüklenemeyenler:\n" + "\n\n".join(broken))
            if not lines:
                lines.append(
                    "Klasörde yetenek yok. `action=new` ile bir iskelet aç."
                )

            # Yeni araçlar bir sonraki istekte şemalarıyla gidiyor; model
            # bunu bilsin, aynı turda çağırmaya kalkmasın.
            if added:
                lines.append("Bir sonraki turdan itibaren araç olarak çağırabilirsin.")
            return ToolResult(content="\n".join(lines),
                              detail={"loaded": added, "updated": updated})

        if action == "list":
            found, broken = skills.discover(root)
            if not found and not broken:
                return ToolResult("Henüz bir yeteneğin yok.")

            lines = [f"{len(found)} yetenek:"]
            for item in found:
                state = "yüklü" if item.name in registry else "yüklenmemiş"
                lines.append(f"- {item.name} ({state}) — {_head(item.description)}")
            if broken:
                lines.append(f"\n{len(broken)} dosya bozuk:\n" + "\n\n".join(broken))
            return ToolResult("\n".join(lines))

        if action == "remove":
            name = str(args.get("name") or "").strip().lower()
            path = skills.folder(root) / f"{name}.py"
            if not path.is_file():
                return ToolResult.error(f"Yetenek dosyası yok: {path.name}")
            path.unlink()
            # Kayıt da düşüyor: dosyası silinmiş bir aracın çağrılabilir
            # kalması, silmenin yarım kalması demekti.
            gone = registry.unregister(name)
            return ToolResult(
                content=f"{path.name} silindi"
                + (" ve araç defterden düştü." if gone else ".")
            )

        return ToolResult.error("`action` write, new, load, list ya da remove olmalı.")


def _head(text: str, limit: int = 90) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


MODELS_DESCRIPTION = """
Sunucudaki modelleri ve yeteneklerini listeler: bağlam penceresi, görüntü
okuyup okumadığı, araç kullanıp kullanmadığı, o an yüklü olup olmadığı.

Alt ajan başlatırken buna bak: tarama işini küçük ve hızlı bir modele,
görüntü gerektiren işi görüntü okuyan bir modele ver. `task` aracının
`model` alanına buradaki kimliği yaz.
"""


def register_models(registry: ToolRegistry) -> None:
    @registry.tool(
        name="models",
        description=MODELS_DESCRIPTION,
        input_schema=object_schema({}),
    )
    async def models(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        from .. import settings

        found = settings.scan_models(ctx.config)
        if not found:
            return ToolResult(
                "Sunucu model listesi vermiyor. Kendi modelinle çalışmaya devam et."
            )

        lines = [f"{len(found)} model:"]
        for entry in found:
            # LM Studio olmayan bir sunucuda yalnızca ad var.
            if "max_context" not in entry:
                lines.append(f"- {entry['id']}")
                continue
            lines.append("- " + _describe(entry))

        lines.append(
            "Alt ajan başlatırken `task` aracının `model` alanına buradaki "
            "kimliği yazabilirsin."
        )
        return ToolResult("\n".join(lines), detail={"count": len(found)})


def _describe(entry: dict[str, Any]) -> str:
    can = [name for flag, name in (("tools", "araç"), ("vision", "görüntü")) if entry.get(flag)]
    loaded = entry.get("loaded") or []
    state = (
        "yüklü " + ", ".join(_thousands(i["context"]) for i in loaded)
        if loaded
        else "yüklü değil"
    )
    return (
        f"{entry['id']} · en fazla {_thousands(entry['max_context'])} token · "
        f"{' + '.join(can) or 'yalnızca metin'} · {state}"
    )


def _thousands(value: int) -> str:
    return f"{value:,}".replace(",", ".")
