"""İçerik arama: `grep`.

Ajan "X nerede geçiyor?" sorusunu bugüne kadar ya kabuğa düşerek (findstr,
Select-String — her platformda farklı, her seferinde izin sorusu) ya da
dosyaları tek tek okuyarak cevaplıyordu. Tipli tek araç bunu bitiriyor:
saf Python (re + os.walk), harici ikili yok, çıktı biçimi hep aynı.

Okuma her yerde serbest olduğu için arama da her yerde serbest —
`mutates=False`, izin kapısına takılmaz.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema
from .files import _resolve

# Taramada atlanan dizinler: araç artıkları, sürüm kontrolü, çöp kutusu
# (transfer._ATLA / gate._ATLA ile aynı akıl). .dornick da burada: oturum
# günlükleri ve değişiklik görüntüleri aramayı çöple doldurur.
_ATLA = frozenset({".git", "__pycache__", "node_modules", ".venv",
                   ".mypy_cache", ".geri-donusum", ".dornick"})

VARSAYILAN_SONUC = 50
SONUC_TAVANI = 200
DOSYA_BASINA = 20            # tek dosya tüm bütçeyi yutmasın
CIKTI_TAVANI = 60_000        # karakter
DOSYA_BOYU_TAVANI = 4 * 1024 * 1024
_KOKLAMA = 8192              # ikili sezgisi için okunan baş kısım


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="grep",
        description="""
Dosyaların İÇİNDE metin arar (düzenli ifadeyle) ve eşleşmeleri
`yol:satır: içerik` biçiminde döndürür. Bir şeyin nerede geçtiğini bulmak
için dosyaları tek tek okuma; önce bununla ara, sonra ilgili dosyayı
read_file ile aç.

Varsayılan kök atölyendir; `path` ile herhangi bir dizinde ya da tek bir
dosyada arayabilirsin (okuma her yerde serbest). `glob` dosyaları süzer:
"**/*.py" gibi bir desen hem alt dizinlerde hem kökte çalışır. İkili
dosyalar ve araç artığı dizinler (.git, node_modules, __pycache__...)
kendiliğinden atlanır.
        """,
        input_schema=object_schema(
            {
                "pattern": {
                    "type": "string",
                    "description": "Aranacak düzenli ifade (Python re sözdizimi).",
                },
                "path": {
                    "type": "string",
                    "description": "Aranacak dizin ya da dosya (varsayılan: atölye kökü).",
                },
                "glob": {
                    "type": "string",
                    "description": 'Dosya süzgeci, ör. "**/*.py" ya da "*.md" (varsayılan: tümü).',
                },
                "context": {
                    "type": "integer",
                    "description": "Eşleşmenin çevresinden gösterilecek satır sayısı (0-3, varsayılan 0).",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"Azami eşleşme sayısı (varsayılan {VARSAYILAN_SONUC}, tavan {SONUC_TAVANI}).",
                },
            },
            required=["pattern"],
        ),
    )
    async def grep(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        desen = str(args.get("pattern") or "")
        if not desen:
            return ToolResult.error("Boş desen. Ne aradığını `pattern` alanına yaz.")
        try:
            rx = re.compile(desen)
        except re.error as exc:
            return ToolResult.error(
                f"Düzenli ifade derlenemedi: {exc}. Özel karakterleri (( ) [ ] . * + ?) "
                "kaçırmayı unutma; düz metin arıyorsan re.escape edilmiş halini gönder."
            )

        kok = _resolve(str(args.get("path") or "."), ctx)
        if not kok.exists():
            return ToolResult.error(f"Yol yok: {kok}")

        baglam = max(0, min(int(args.get("context") or 0), 3))
        tavan = max(1, min(int(args.get("max_results") or VARSAYILAN_SONUC), SONUC_TAVANI))

        def _tara() -> tuple[list[str], int, int, bool]:
            return _search(kok, rx, args.get("glob"), baglam, tavan, ctx.cancel)

        try:
            bloklar, eslesme, dosya_sayisi, kirpildi = await asyncio.to_thread(_tara)
        except OSError as exc:
            return ToolResult.error(f"Aranamadı: {exc}")

        if not eslesme:
            return ToolResult(
                content=f"'{desen}' için eşleşme yok ({kok}).",
                detail={"pattern": desen, "matches": 0},
            )

        baslik = f"'{desen}' için {eslesme} eşleşme ({dosya_sayisi} dosya):"
        if kirpildi:
            baslik += " (kırpıldı — daraltmak için glob ya da daha özgül bir desen ver)"
        govde = "\n\n".join(bloklar)
        if len(govde) > CIKTI_TAVANI:
            govde = govde[:CIKTI_TAVANI] + "\n… çıktı tavanı aşıldı, gerisi kırpıldı."
        return ToolResult(
            content=f"{baslik}\n\n{govde}",
            detail={"pattern": desen, "matches": eslesme, "files": dosya_sayisi},
        )


# -- tarama ------------------------------------------------------------


def _search(
    kok: Path,
    rx: re.Pattern[str],
    glob: str | None,
    baglam: int,
    tavan: int,
    cancel: asyncio.Event,
) -> tuple[list[str], int, int, bool]:
    """Dosyaları gezer; (dosya blokları, eşleşme, dosya sayısı, kırpıldı mı) döner."""
    bloklar: list[str] = []
    toplam = 0
    dosyali = 0
    kirpildi = False
    karakter = 0

    for yol, rel in _dosyalar(kok, glob):
        if cancel.is_set() or toplam >= tavan or karakter >= CIKTI_TAVANI:
            kirpildi = kirpildi or toplam >= tavan
            break
        satirlar = _oku(yol)
        if satirlar is None:
            continue

        blok: list[str] = []
        dosyada = 0
        for no, satir in enumerate(satirlar, 1):
            if not rx.search(satir):
                continue
            dosyada += 1
            toplam += 1
            if dosyada > DOSYA_BASINA:
                blok.append(f"{rel}: … dosyada daha fazla eşleşme var, kırpıldı.")
                kirpildi = True
                toplam -= 1  # kırpılan eşleşme sayılmaz
                break
            if baglam:
                bas = max(0, no - 1 - baglam)
                for i in range(bas, no - 1):
                    blok.append(f"{rel}-{i + 1}- {satirlar[i].rstrip()}")
            blok.append(f"{rel}:{no}: {satir.rstrip()}")
            if baglam:
                son = min(len(satirlar), no + baglam)
                for i in range(no, son):
                    blok.append(f"{rel}-{i + 1}- {satirlar[i].rstrip()}")
            if toplam >= tavan:
                kirpildi = True
                break
        if blok:
            dosyali += 1
            parca = "\n".join(blok)
            karakter += len(parca)
            bloklar.append(parca)

    return bloklar, toplam, dosyali, kirpildi


def _dosyalar(kok: Path, glob: str | None):
    """Aranacak dosyaları sırayla verir: (mutlak yol, görünen yol)."""
    if kok.is_file():
        yield kok, str(kok)
        return
    for dirpath, dirnames, filenames in os.walk(kok):
        dirnames[:] = sorted(d for d in dirnames if d not in _ATLA)
        for ad in sorted(filenames):
            yol = Path(dirpath) / ad
            rel = yol.relative_to(kok).as_posix()
            # "**/*.py" fnmatch'te kökteki dosyayı tutmuyor; ada ayrıca
            # bakmak hem onu hem "*.py" gibi kısa desenleri kurtarıyor.
            if glob and not (fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(ad, glob)):
                continue
            yield yol, rel


def _oku(yol: Path) -> list[str] | None:
    """Metin dosyasının satırları; ikili ya da dev dosyada None."""
    try:
        if yol.stat().st_size > DOSYA_BOYU_TAVANI:
            return None
        with yol.open("rb") as f:
            bas = f.read(_KOKLAMA)
        if b"\0" in bas:  # ikili sezgisi: null bayt metinde olmaz
            return None
        return yol.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
