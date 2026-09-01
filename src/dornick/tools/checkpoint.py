"""Değişiklik defteri: yazma öncesi anlık görüntü + `undo` aracı.

write_file/edit_file/copy_in atölye İÇİNDEKİ bir dosyayı değiştirmeden hemen
önce buraya uğrar: dosyanın o anki hali
`.dornick/degisiklikler/<oturum>/<sıra>-<ad>` altına kopyalanır, kayıt
`kayit.jsonl`e düşer. `undo` aracı bu kayıtları listeler ve tersine uygular.

İki bilinçli karar:

  * Geri alma da kendini kaydeder. Böylece yanlış bir `restore` bir kez daha
    `restore` ile ileri alınabilir (redo) — tek yönlü bir merdiven değil.
  * Görüntü alınamaması yazmayı DURDURMAZ. 2 MB üstü dosyada kopya atlanır
    ve kayda not düşülür; undo o kaydı geri alamayacağını dürüstçe söyler.
    Emniyet kemeri takılamıyor diye arabayı durdurmak modeli kilitliyordu.

Birikinti: oturum klasörleri süreç başına bir kez, ilk kullanımda süzülür —
14 günden eski oturumların klasörü sessizce silinir. Transfer paketine bu
klasör girmez (state_dir atölyenin dışında; transfer._ATLA ayrıca .Dornick'i
tanır).
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema

KLASOR = "degisiklikler"
GORUNTU_TAVANI = 2 * 1024 * 1024   # bundan büyük dosyada görüntü atlanır
TEMIZLIK_GUN = 14
LISTE_TAVANI = 20

_GUVENSIZ = re.compile(r"[^\w.\-]+")

# Süreç başına bir kez temizlenen kökler ("açılışta" demenin pratik hali:
# ilk dosya yazımı geldiğinde, o kökte bir kez).
_temizlenen: set[Path] = set()


def defter(ctx: ToolContext) -> "Defter":
    return Defter(Path(ctx.config.state_dir) / KLASOR, ctx.session.id)


class Defter:
    """Bir oturumun değişiklik kayıtları. Gerçek kaynak diskteki kayit.jsonl —
    süreç yeniden başlasa da, araç katmanı yeniden kurulsa da kayıp yok."""

    def __init__(self, kok: Path, oturum: str) -> None:
        self.kok = kok
        self.dizin = kok / (_GUVENSIZ.sub("_", oturum or "oturum") or "oturum")
        self.kayit_yolu = self.dizin / "kayit.jsonl"

    # -- kayıt ---------------------------------------------------------

    def kaydet(self, path: Path, arac: str) -> None:
        """Dosya değişmeden HEMEN ÖNCE çağrılır; mevcut hali saklar.

        Henüz olmayan dosyada "yoktu" kaydı düşer — geri alma o dosyayı siler.
        """
        self._hazirla()
        kayitlar = self._oku()
        sira = (kayitlar[-1]["sira"] + 1) if kayitlar else 1
        kayit: dict[str, Any] = {
            "sira": sira,
            "dosya": str(path),
            "arac": arac,
            "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "goruntu": None,
            "yoktu": False,
            "atlandi": None,
        }
        try:
            if not path.exists():
                kayit["yoktu"] = True
            elif path.stat().st_size > GORUNTU_TAVANI:
                kayit["atlandi"] = "2 MB üstü, görüntü alınmadı"
            else:
                ad = f"{sira:04d}-{(_GUVENSIZ.sub('_', path.name) or 'dosya')[:80]}"
                shutil.copy2(path, self.dizin / ad)
                kayit["goruntu"] = ad
        except OSError as exc:
            kayit["goruntu"] = None
            kayit["atlandi"] = f"görüntü alınamadı: {exc}"
        with self.kayit_yolu.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")

    # -- geri alma -----------------------------------------------------

    def listele(self, tavan: int = LISTE_TAVANI) -> list[dict[str, Any]]:
        """Son kayıtlar, en yenisi önce."""
        return list(reversed(self._oku()[-tavan:]))

    def geri_al(self, n: int) -> tuple[list[str], str | None]:
        """Son n değişikliği tersine uygular; (yapılanlar, hata) döner.

        Önce HEPSİ denetlenir: görüntüsüz (atlanmış) bir kayıt varsa hiçbir
        şey yapılmaz — yarım geri alma, hiç geri almamaktan kötü.
        """
        kayitlar = self._oku()
        if not kayitlar:
            return [], "Bu oturumda kayıtlı değişiklik yok."
        if n > len(kayitlar):
            return [], (
                f"Bu oturumda {len(kayitlar)} değişiklik var, {n} geri alınamaz. "
                "Önce `undo` ile action=list yap."
            )

        secilen = kayitlar[-n:]
        for k in secilen:
            if k["goruntu"] is None and not k["yoktu"]:
                return [], (
                    f"{k['sira']}. kayıt geri alınamaz ({k['dosya']}): "
                    f"{k['atlandi'] or 'görüntü yok'}. Hiçbir şey geri alınmadı."
                )

        yapilan: list[str] = []
        for k in reversed(secilen):  # en yeniden en eskiye
            ok, mesaj = self._tek_geri(k)
            yapilan.append(mesaj)
            if not ok:
                return yapilan, mesaj
        return yapilan, None

    def geri_al_sira(self, sira: int) -> tuple[list[str], str | None]:
        """Tek bir kayıt sırasını geri alır (dosya bazlı Keep/Undo).

        Tur şeridindeki bir satırın Undo'su buraya düşer: diğer dosyalara
        dokunulmaz. Kayıt yoksa veya görüntüsüzse hiçbir şey yazılmaz.
        """
        kayitlar = self._oku()
        if not kayitlar:
            return [], "Bu oturumda kayıtlı değişiklik yok."
        k = next((x for x in kayitlar if int(x.get("sira") or 0) == int(sira)), None)
        if k is None:
            return [], f"{sira}. kayıt bulunamadı."
        if k["goruntu"] is None and not k["yoktu"]:
            return [], (
                f"{k['sira']}. kayıt geri alınamaz ({k['dosya']}): "
                f"{k['atlandi'] or 'görüntü yok'}."
            )
        ok, mesaj = self._tek_geri(k)
        return ([mesaj], None if ok else mesaj)

    def geri_al_dosya(self, dosya: str) -> tuple[list[str], str | None]:
        """Bu yol için en son kaydı geri alır (diff kartı Undo)."""
        hedef = Path(dosya)
        try:
            hedef_key = str(hedef.resolve()) if hedef.exists() else str(hedef)
        except OSError:
            hedef_key = str(hedef)
        hedef_norm = hedef_key.replace("\\", "/").lower()
        kayitlar = self._oku()
        for k in reversed(kayitlar):
            ham = str(k.get("dosya") or "")
            if not ham:
                continue
            p = Path(ham)
            try:
                key = str(p.resolve()) if p.exists() else ham
            except OSError:
                key = ham
            if key.replace("\\", "/").lower() == hedef_norm:
                return self.geri_al_sira(int(k["sira"]))
        return [], f"Bu oturumda {dosya!r} için kayıt yok."

    def _tek_geri(self, k: dict[str, Any]) -> tuple[bool, str]:
        """Tek kaydı uygular; (ok, mesaj). Redo için önce kaydet çağırır."""
        hedef = Path(k["dosya"])
        self.kaydet(hedef, "undo")
        try:
            if k["yoktu"]:
                hedef.unlink(missing_ok=True)
                return True, f"{k['sira']}. kayıt: {hedef} silindi (oluşturma geri alındı)."
            hedef.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.dizin / k["goruntu"], hedef)
            return True, f"{k['sira']}. kayıt: {hedef} eski haline döndü."
        except OSError as exc:
            return False, f"{k['sira']}. kayıt geri alınamadı: {exc}"

    # -- iç işler ------------------------------------------------------

    def _hazirla(self) -> None:
        self.dizin.mkdir(parents=True, exist_ok=True)
        if self.kok not in _temizlenen:
            _temizlenen.add(self.kok)
            _temizle(self.kok, koru=self.dizin)

    def _oku(self) -> list[dict[str, Any]]:
        try:
            metin = self.kayit_yolu.read_text(encoding="utf-8")
        except OSError:
            return []
        kayitlar = []
        for satir in metin.splitlines():
            try:
                kayitlar.append(json.loads(satir))
            except ValueError:
                continue  # yarım yazılmış satır defteri düşürmesin
        return kayitlar


def _temizle(kok: Path, koru: Path) -> None:
    """14 günden eski oturum klasörlerini sessizce siler."""
    esik = time.time() - TEMIZLIK_GUN * 86400
    try:
        cocuklar = list(kok.iterdir())
    except OSError:
        return
    for cocuk in cocuklar:
        try:
            if cocuk.is_dir() and cocuk != koru and cocuk.stat().st_mtime < esik:
                shutil.rmtree(cocuk, ignore_errors=True)
        except OSError:
            continue


# -- araç --------------------------------------------------------------


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="undo",
        description="""
Atölyedeki dosya değişikliklerini yönetir. write_file/edit_file/copy_in her
değişiklikten önce dosyanın o anki halini otomatik saklar; bu araç o
kayıtları listeler ve geri alır.

  list     bu oturumun son değişiklikleri (sıra, dosya, araç, zaman)
  restore  son n değişikliği tersine uygular (varsayılan 1); yeni oluşturulmuş
           bir dosyanın geri alınması dosyayı siler

Geri alma da kendini kaydeder: yanlış geri aldıysan bir kez daha `restore`
ile ileri dönebilirsin (redo).
        """,
        input_schema=object_schema(
            {
                "action": {"type": "string", "enum": ["list", "restore"]},
                "n": {
                    "type": "integer",
                    "description": "restore: geri alınacak değişiklik sayısı (varsayılan 1).",
                },
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def undo(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        d = defter(ctx)
        action = str(args.get("action") or "")

        if action == "list":
            kayitlar = await asyncio.to_thread(d.listele)
            if not kayitlar:
                return ToolResult(content="Bu oturumda kayıtlı değişiklik yok.")
            satirlar = [f"Son {len(kayitlar)} değişiklik (en yenisi önce):", ""]
            for k in kayitlar:
                iz = f"{k['sira']:>4}. {k['dosya']} — {k['arac']} ({k['zaman']})"
                if k["yoktu"]:
                    iz += " [dosya yoktu, yeni oluşturuldu]"
                elif k["atlandi"]:
                    iz += f" [{k['atlandi']}]"
                satirlar.append(iz)
            return ToolResult(content="\n".join(satirlar), detail={"count": len(kayitlar)})

        if action == "restore":
            n = max(1, int(args.get("n") or 1))
            yapilan, hata = await asyncio.to_thread(d.geri_al, n)
            if hata:
                govde = "\n".join(yapilan + [hata])
                return ToolResult.error(govde)
            return ToolResult(
                content="\n".join(yapilan),
                detail={"restored": len(yapilan)},
            )

        return ToolResult.error(
            f"Bilinmeyen action: {action!r}. 'list' ya da 'restore' kullan."
        )
