"""`kos` aracı: projenin kendi test düzeneğini bulup çalıştırır.

Bu araç `denetle`nin bittiği yerden başlıyor. `denetle` dilin sözdizimine
bakar; `kos` kodu GERÇEKTEN çalıştırır. Aradaki fark bir kullanıcı
şikâyetinin tamamı:

    public function index(): string { return redirect(); }

`php -l` bunu temiz bulur, tarayıcı TypeError verir. Testi koşan bir ajan
bunu tur kapanmadan görür.

İzin kipi kararı — `mutates=True`, gerekçesi:

    Test koşmak "dosya değiştirmez" diye başlar ama bu doğru değil. Bir
    test takımı geçiş (migration) koşturur, `writable/` temizler, önbellek
    yazar, veritabanı düşürüp kurar, ağa çıkar, e-posta gönderir. Üstelik
    çalıştırdığı kod BİZİM değil, projenin — yani kullanıcının makinesinde
    kullanıcının yetkileriyle koşan üçüncü taraf koddur. `shell` tam bu
    yüzden `mutates=True`; `kos` da keşfedilmiş bir komutu koşturan bir
    kabuktur. `mutates=False` demek, plan kipindeki bir ajanın kullanıcının
    test takımını (ve onun yan etkilerini) sessizce tetikleyebilmesi
    demekti. Sürtünmeyi izin kuralı çözer: kullanıcı bir kez "kos:*" der.

`parallel_safe=False`: iki test koşumu aynı anda aynı veritabanına,
aynı `writable/` klasörüne girer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import kosum
from .base import ToolContext, ToolRegistry, ToolResult, object_schema


def _kok_bul(args: dict[str, Any], ctx: ToolContext) -> Path:
    """Hangi projede koşacağız?

    Sıra: (1) modelin verdiği yol, (2) bu oturumda en son dosya yazılan
    proje, (3) atölye, (4) çalışma alanı. Her durumda sonuç metninde kökün
    tam yolu yazıyor — yanlış tahmin edilse bile model gördüğü an düzeltir.
    """
    if ham := (args.get("path") or "").strip():
        yol = Path(ham).expanduser()
        if not yol.is_absolute():
            temel = ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace
            yol = temel / yol
        return kosum.proje_koku(yol)
    if (son := kosum.son_proje()) is not None:
        return son
    return ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace


def _duzenek_ozeti(kok: Path) -> str:
    """Klasörde bulunan düzeneklerin listesi — koşmadan, bedava."""
    hepsi = kosum.tespit_hepsi(kok)
    if not hepsi:
        return kosum.tespit_metni(kok)

    satirlar = [f"{kok} altında bulunan düzenekler:"]
    for d in hepsi:
        etiket = "test" if d.tur == "test" else "sağlık denetimi"
        satirlar.append(f"  `{d.etiket}` — {etiket}, kanıt: {d.kanit}")
        for not_ in d.notlar:
            satirlar.append(f"      {not_}")
        if d.engel:
            satirlar.append(f"      koşulamaz: {d.engel}")
    satirlar.append("")
    satirlar.append("Bunlar tespit; hiçbiri koşturulmadı. Koşturmak için "
                    "`kos` aracını `sadece_tespit` olmadan çağır.")
    return "\n".join(satirlar)


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="kos",
        description="""
Projenin KENDİ test düzeneğini bulur ve çalıştırır; sonucu geçen/kalan
sayısı, başarısız testlerin adı ve dosya:satır bilgisiyle özetler.

Ne zaman kullan: kod yazdıktan ya da düzelttikten sonra, "bitti" demeden
önce. `denetle` yalnızca sözdizimine bakar — tip hataları, yanlış dönüş
değerleri ve bozuk davranış ancak kod ÇALIŞINCA ortaya çıkar.

Komut uydurulmaz: pytest yapılandırması, package.json'daki `scripts.test`,
phpunit, go.mod gibi gerçek dosya kanıtları aranır. Hiçbiri yoksa araç
"test düzeneği bulunamadı" der ve sana uydurma bir komut vermez.

`path` vermezsen bu oturumda en son dosya yazdığın proje kullanılır.
`komut` verirsen tespit atlanır ve o komut koşar (dar bir dilim koşturmak
için: `py -m pytest -q tests/test_x.py`).
`sadece_tespit: true` hiçbir şey çalıştırmadan yalnızca ne bulunduğunu söyler.

Bir koşumun geçmesi "her şey çalışıyor" demek DEĞİLDİR; yalnızca koşulan
testlerin kapsadığı kadarını doğrular. Sonuç metni bunu her seferinde
yazıyor — kullanıcıya aktarırken de aynı sınırı koru.
        """,
        input_schema=object_schema(
            {
                "path": {
                    "type": "string",
                    "description": "Proje klasörü ya da içindeki bir dosya. "
                                   "Verilmezse en son dokunulan proje kullanılır.",
                },
                "komut": {
                    "type": "string",
                    "description": "Tespiti geçersiz kılan komut. Yalnızca "
                                   "gerçekten bildiğin bir komutu ver.",
                },
                "zaman_asimi": {
                    "type": "integer",
                    "description": "Saniye cinsinden süre tavanı "
                                   f"(varsayılan {int(kosum.VARSAYILAN_ZAMAN_ASIMI)}, "
                                   f"en fazla {int(kosum.MAX_ZAMAN_ASIMI)}).",
                },
                "sadece_tespit": {
                    "type": "boolean",
                    "description": "Hiçbir şey çalıştırma; yalnızca bu projede "
                                   "hangi düzeneğin bulunduğunu söyle.",
                },
            },
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def kos(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        kok = _kok_bul(args, ctx)
        if not kok.is_dir():
            return ToolResult.error(
                f"Klasör yok: {kok}. `path` ile var olan bir proje klasörü ver."
            )

        if args.get("sadece_tespit"):
            return ToolResult(content=_duzenek_ozeti(kok),
                              detail={"kok": str(kok), "tespit": True})

        zaman_asimi = float(args.get("zaman_asimi") or kosum.VARSAYILAN_ZAMAN_ASIMI)

        if komut := (args.get("komut") or "").strip():
            sonuc = await kosum.kos_komut(
                komut, kok, zaman_asimi=zaman_asimi, cancel=ctx.cancel)
            return _cevap(sonuc)

        duzenek = kosum.tespit(kok)
        if duzenek is None:
            # Kanıt yok. Uydurma komut üretmek yerine ne yapılacağını söyle.
            return ToolResult(content=kosum.tespit_metni(kok),
                              detail={"kok": str(kok), "duzenek": None})

        if not duzenek.kosulabilir:
            return ToolResult(
                content=(
                    f"{kok} altında `{duzenek.etiket}` düzeneği var "
                    f"(kanıt: {duzenek.kanit}) ama koşturulamıyor: "
                    f"{duzenek.engel}\n\nBu bir kod hatası değil, makinenin "
                    "durumu. Kullanıcıya bildir; kurulum kararı onun."
                ),
                detail={"kok": str(kok), "engel": duzenek.engel},
            )

        sonuc = await kosum.kos(duzenek, zaman_asimi=zaman_asimi, cancel=ctx.cancel)
        return _cevap(sonuc)


def _cevap(sonuc: kosum.Sonuc) -> ToolResult:
    """Sonucu araç cevabına çevirir.

    `is_error` yalnızca gerçekten kötü giden durumlarda: başarısız test,
    sıfırdan farklı çıkış kodu, zaman aşımı. "Düzenek yok" hata değil —
    bilgi; hata sayılırsa model kendi yazdığında bir kusur olduğunu sanır.
    """
    hatali = (
        sonuc.durum in ("zaman_asimi", "baslatilamadi", "kesildi")
        or sonuc.cikis_kodu != 0
        or sonuc.sayim.kalan > 0
    )
    return ToolResult(content=sonuc.metin(), is_error=hatali, detail=sonuc.detay())
