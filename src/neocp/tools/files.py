"""Dosya araçları.

Kabuktan `cat`/`echo` yerine bunları terfi ettirmenin sebebi: harness'a
tipli argümanlar verirler. Böylece yazma öncesi bayatlık kontrolü yapılabilir,
izin kuralları yola göre yazılabilir, arayüz diff gösterebilir. Opak bir
kabuk dizesinde bunların hiçbiri mümkün değil.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from .. import kancalar, kosum, tanilar
from ..sandbox import OutsideSandbox
from . import checkpoint
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

MAX_READ_CHARS = 60_000
MAX_LIST_ENTRIES = 400

# Elle denetimde tek turda bakılacak en fazla dosya. Bir klasörü denetlemek
# istenen şey; bütün depoyu taramak değil.
MAX_DENETIM_DOSYA = 60


def _resolve(raw: str, ctx: ToolContext) -> Path:
    """Göreli yolları atölyeye, mutlak yolları olduğu gibi çözer.

    Göreli yolun atölyeye düşmesi bilinçli: ajan çoğu zaman kendi işini
    yapıyor ve "site/index.html" yazdığında bunun kendi klasöründe olmasını
    bekliyor. Dışarıdaki bir dosyaya mutlak yolla erişiliyor — okumak zaten
    her yerde serbest.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if not ctx.sandbox.enabled:
        return ctx.workspace / path

    root = ctx.sandbox.root
    # Model atölyenin adını yola kendisi ekliyor ("atolye/site/index.html"):
    # sistem promptunda klasörün tam yolu yazıyor ve oradan çıkarım yapıyor.
    # Olduğu gibi birleştirmek `atolye/atolye/...` üretiyordu — dosya doğru
    # yere değil bir alt klasöre düşüyor ve kullanıcı aradığını bulamıyor.
    parts = path.parts
    if parts and parts[0] == root.name:
        path = Path(*parts[1:]) if len(parts) > 1 else Path()
    return root / path


def _guard(path: Path, ctx: ToolContext) -> ToolResult | None:
    """Yazma sınırı. İhlal varsa hatayı döndürür, yoksa None.

    Hata metni ne yapılacağını da söylüyor: modelin bir sonraki turda
    `copy_in`e yönelmesi için "izin yok" demek yetmiyor.
    """
    # Kanca dosyası her şeyden önce: atölyenin içinde bile olsa yazılamaz.
    #
    # Kancalar izin motorunun DIŞINDA çalışan, kullanıcının kendi
    # komutlarıdır. Bu ancak model o dosyaya dokunamıyorsa güvenli: aksi
    # halde kendisini engelleyen kancayı silerek ya da oraya kendi komutunu
    # yazarak izin kapısını tümüyle atlardı. Kural tek yerde ve tüm yazma
    # araçları buradan geçiyor.
    if kancalar.korunan_mu(path):
        return ToolResult.error(
            f"{path} kanca dosyasıdır ve yazmaya kapalıdır. Kancalar "
            "kullanıcının senin üzerinde kurduğu kurallardır; onay "
            "penceresi olmadan çalışırlar ve tam bu yüzden senin "
            "değiştirebileceğin bir yerde durmazlar. Bir kancanın "
            "değişmesi gerekiyorsa kullanıcıya söyle, kendin düzenleme."
        )
    try:
        ctx.sandbox.check(path)
    except OutsideSandbox as exc:
        return ToolResult.error(str(exc))
    return None


def _gozle(path: Path, ctx: ToolContext, arac: str) -> None:
    """Atölye içindeki dosya için değişiklik öncesi anlık görüntü.

    Görüntü alınamaması yazmayı DURDURMAZ: emniyet kemeri takılamıyor diye
    arabayı durdurmak modeli kilitler. `undo` görüntüsüz kaydı dürüstçe
    "geri alınamaz" diye raporlar.
    """
    try:
        if ctx.sandbox.contains(path):
            checkpoint.defter(ctx).kaydet(path, arac)
    except OSError:
        pass


# -- metin olmayan dosyalar ---------------------------------------------
#
# Kanıtlanmış yara: bir PNG'yi `read_file` ile açmak, modele bir ekran
# dolusu "��" gönderiyordu. Model bunu "dosya bozuk" diye okuyup
# kullanıcıya öyle söylüyordu — oysa dosya sapasağlamdı, biz yanlış
# gözle bakıyorduk.

# API'nin kabul ettiği görüntü türleri. Başkasını göndermek 400 döner;
# o yüzden listede olmayan bir uzantı görüntü yoluna hiç girmiyor.
GORSEL_TURLERI = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
}

# Görüntü tavanı. API base64 gövdesinde ~5 MB'ı reddediyor; base64 ham
# boyutu 4/3'e çıkardığı için ham tavan bunun dörtte üçünden biraz altta.
MAX_GORSEL = 3_500_000

# PDF'te tek turda çıkarılan varsayılan ve en fazla sayfa. Bir sözleşmenin
# tamamını bağlama boşaltmak, aranan paragrafı bulmayı kolaylaştırmıyor.
PDF_SAYFA = 10
PDF_MAX_SAYFA = 40
MAX_PDF_KARAKTER = 40_000


def _gorsel_mu(path: Path) -> bool:
    return path.suffix.lower() in GORSEL_TURLERI


def _boyut(sayi: int) -> str:
    if sayi >= 1_048_576:
        return f"{sayi / 1_048_576:.1f} MB"
    # Küçük dosyalarda "0 KB" yazmak yanlış bilgi: dosya boş değil.
    return f"{sayi / 1024:.0f} KB" if sayi >= 1024 else f"{sayi} bayt"


def _gorsel_oku(path: Path) -> ToolResult:
    """Görseli modele GÖRÜNTÜ olarak verir.

    Taşıma yolu hazırdı ve kullanılmıyordu: araç sonucu bir görüntü
    taşıyamıyor (API `tool_result` içeriğinin dize olmasını istiyor), ama
    yürütücü `detail["image"]`ı görüp bloğa `_image` olarak iliştiriyor ve
    döngü onu bir sonraki kullanıcı turuna görüntü bloğu olarak koyuyor —
    `look`/`screen` araçlarının yıllardır kullandığı yol. Buraya
    bağlanması bir satırlık iş; eksik olan yalnızca bağlantıydı.
    """
    import base64

    try:
        boyut = path.stat().st_size
    except OSError as exc:
        return ToolResult.error(f"Okunamadı: {exc}")

    if boyut > MAX_GORSEL:
        # Uydurma yok: görüntüyü gönderemiyorsak bunu söylüyoruz.
        return ToolResult(
            f"{path.name} bir görsel ({_boyut(boyut)}) ama modele "
            f"gönderilemeyecek kadar büyük (tavan {_boyut(MAX_GORSEL)}). "
            "İçeriğini göremiyorum; küçültülmüş bir kopyası verilirse "
            "bakabilirim.",
            is_error=True,
        )
    try:
        ham = path.read_bytes()
    except OSError as exc:
        return ToolResult.error(f"Okunamadı: {exc}")

    tur = GORSEL_TURLERI[path.suffix.lower()]
    veri = base64.b64encode(ham).decode("ascii")
    return ToolResult(
        content=f"{path.name} ({tur}, {_boyut(boyut)}) açıldı. Aşağıda görüyorsun.",
        detail={"path": str(path), "image": f"data:{tur};base64,{veri}"},
    )


def _pdf_oku(path: Path, offset: Any, limit: Any) -> ToolResult:
    """PDF'in ilk sayfalarının METNİNİ çıkarır.

    İki dürüstlük kuralı:
      * Metinsiz (taranmış) PDF'te "boş" demiyoruz — sayfaların görüntü
        olduğunu ve metin katmanı taşımadığını söylüyoruz. "Boş" demek,
        modelin dosyayı içeriksiz sanmasına yol açardı.
      * Kaç sayfanın okunduğu ve kaç sayfa olduğu her zaman yazılıyor;
        model 3. sayfayı okuyup 200 sayfalık raporu özetlediğini
        sanmasın.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return ToolResult(
            f"{path.name} bir PDF ama okuyamıyorum: `pypdf` bu makinede "
            "kurulu değil. İçeriği hakkında tahminde bulunmayacağım — "
            "kullanıcıya bildir.",
            is_error=True,
        )

    try:
        okuyucu = PdfReader(str(path))
        toplam = len(okuyucu.pages)
    except Exception as exc:
        return ToolResult(
            f"{path.name} açılamadı ({type(exc).__name__}: {exc}). Dosya "
            "bozuk ya da parola korumalı olabilir.",
            is_error=True,
        )

    if toplam == 0:
        return ToolResult(f"{path.name} sayfa içermiyor.", is_error=True)

    bas = max(1, int(offset or 1))
    kac = max(1, min(int(limit or PDF_SAYFA), PDF_MAX_SAYFA))
    son = min(toplam, bas + kac - 1)
    if bas > toplam:
        return ToolResult.error(
            f"{path.name} {toplam} sayfa; {bas}. sayfa yok. `offset` değerini "
            f"1 ile {toplam} arasında ver."
        )

    parcalar: list[str] = []
    dolu = 0
    for no in range(bas, son + 1):
        try:
            metin = (okuyucu.pages[no - 1].extract_text() or "").strip()
        except Exception:  # tek bozuk sayfa dosyanın tamamını düşürmesin
            metin = ""
        if metin:
            dolu += 1
        parcalar.append(f"--- sayfa {no} ---\n{metin or '(bu sayfada metin yok)'}")

    govde = "\n\n".join(parcalar)
    if len(govde) > MAX_PDF_KARAKTER:
        govde = govde[:MAX_PDF_KARAKTER] + "\n… (kırpıldı)"

    basli = f"{path.name} — {toplam} sayfa, {bas}-{son} arası okundu."
    if dolu == 0:
        return ToolResult(
            f"{basli}\n\nBu sayfalar METİN KATMANI TAŞIMIYOR — büyük "
            "olasılıkla taranmış görüntüler. İçeriğini okuyamadım; ne "
            "yazdığını uydurma. Sayfayı görsel olarak incelemek gerekirse "
            "kullanıcıdan bir ekran görüntüsü iste.",
            detail={"path": str(path), "sayfa": toplam, "metinsiz": True},
        )

    kuyruk = ""
    if son < toplam:
        kuyruk = (f"\n\n[{toplam} sayfanın {bas}-{son} arası. Devamı için "
                  f"offset={son + 1}.]")
    return ToolResult(
        content=f"{basli}\n\n{govde}{kuyruk}",
        detail={"path": str(path), "sayfa": toplam, "okunan": [bas, son]},
    )


async def _kosum_eki(path: Path, yazim: int) -> str:
    """Yazma sonrası tek satırlık koşum hatırlatması (yoksa boş dize).

    Tanı bir adım attı ama tavanı sözdizimi: `php -l` bildirilen dönüş
    tipiyle uyuşmayan bir `return`u görmez, tip hatası ancak kod koşunca
    patlar. Bunu gören tek şey testi ÇALIŞTIRMAK — ve çoğu projede o
    düzenek zaten var, ajan onu bilmiyordu.

    Testi burada kendiliğinden koşturmuyoruz: koşum saniyeler, bazen
    dakikalar sürer ve ajan aynı dosyaya arka arkaya yazar — aradaki her
    koşum boşa giderdi. Onun yerine düzeneğin VARLIĞINI bildiriyoruz.
    Bilgi bedava, koşum pahalı, karar modelin.
    """
    try:
        return await asyncio.to_thread(kosum.hatirlatma, path, yazim=yazim)
    except Exception:  # pragma: no cover - hatırlatma hiçbir zaman engel olmaz
        return ""


async def _tani_eki(path: Path) -> tuple[str, dict[str, Any]]:
    """Yazılan dosyanın tanısı: (araç sonucuna eklenecek metin, detay).

    Bu, modülün en önemli yeri. Ajanın en pahalı hata sınıfı "yazdım,
    çalıştırmadım, bitti dedim" — hata dosyada durur, tur kapanır, kullanıcı
    sayfayı açınca patlar. Dilin kendi denetleyicisini yazma biter bitmez
    koşturup sonucu ARACIN CEVABINA koymak bu zinciri kırıyor: model bir
    sonraki turda hatayı görür ve daha kimse fark etmeden düzeltir.

    Tanı asla yazmayı geçersiz kılmaz: dosya diskte, sonuç başarılı. Tanı
    yalnızca bir NOT ekler. Denetleyici çöktüyse hiçbir şey eklenmez —
    tanının kendi arızası, çalışan bir aracı bozmamalı.
    """
    try:
        tani = await asyncio.to_thread(tanilar.denetle, path)
    except Exception:  # pragma: no cover - tanı katmanı hiçbir zaman engel olmaz
        return "", {}
    if tani is None:
        return "", {}
    return "\n\n" + tani.metin(), {"tani": tani.detay()}


def _esnek_esle(text: str, old: str, new: str):
    """Tam eşleşme yoksa toleranslı arama. (start, end, new, not) ya da
    ("coklu", N) ya da None.

    Ölçülen yara (28.08 üçlü kıyası, z1): 18 hatalı aracın 7'si "aranan
    metin dosyada yok"tu ve hepsi boşluk/girinti/satır-sonu farkıydı —
    içerik doğruydu. Model dosyayı yeniden okuyup turu yakıyordu. Sıra:
    satır-sonu normalizasyonu → kuyruk boşluğu → tek-tip girinti kayması.
    Her adımda eşleşme TEK olmalı; birden fazlaysa belirsizlik hatası
    (yanlış yeri sessizce değiştirmekten her zaman iyidir).
    """
    o2 = old.replace("\r\n", "\n").replace("\r", "\n")
    n2 = new.replace("\r\n", "\n").replace("\r", "\n")
    if o2 != old:
        say = text.count(o2)
        if say == 1:
            i = text.index(o2)
            return i, i + len(o2), n2, "satır sonları normalize edildi"
        if say > 1:
            return ("coklu", say)

    old_lines = o2.split("\n")
    fl = text.split("\n")
    n = len(old_lines)
    if not n or len(fl) < n:
        return None
    offs = [0]
    for ln in fl[:-1]:
        offs.append(offs[-1] + len(ln) + 1)

    def aralik(i):
        return offs[i], offs[i + n - 1] + len(fl[i + n - 1])

    # Kuyruk boşlukları: satır içeriği aynı, satır sonundaki boşluk farklı.
    hedef = [l.rstrip() for l in old_lines]
    adaylar = [i for i in range(len(fl) - n + 1)
               if [l.rstrip() for l in fl[i:i + n]] == hedef]
    if len(adaylar) == 1:
        b, e = aralik(adaylar[0])
        return b, e, n2, "kuyruk boşlukları göz ardı edildi"
    if len(adaylar) > 1:
        return ("coklu", len(adaylar))

    # Tek-tip girinti kayması: içerik aynı, tüm dolu satırlarda girinti
    # farkı SABİT. `new` de aynı kaymayla yeniden girintilenir — modelin
    # old'u yanlış girintiliyse new'i de aynı biçimde yanlıştır.
    icerik = [l.strip() for l in old_lines]

    def girinti(l):
        return l[: len(l) - len(l.lstrip())]

    uyanlar = []
    for i in range(len(fl) - n + 1):
        pencere = fl[i:i + n]
        if [l.strip() for l in pencere] != icerik:
            continue
        fark = None
        ek = ""
        uydu = True
        for a, b in zip(old_lines, pencere):
            if not a.strip():
                continue
            d = len(girinti(b)) - len(girinti(a))
            if fark is None:
                fark = d
                if d > 0:
                    ek = girinti(b)[: d]
            elif d != fark:
                uydu = False
                break
        if uydu and fark is not None and fark != 0:
            uyanlar.append((i, fark, ek))
    if len(uyanlar) > 1:
        return ("coklu", len(uyanlar))
    if len(uyanlar) == 1:
        i, fark, ek = uyanlar[0]
        b, e = aralik(i)
        yeni_satirlar = []
        for l in n2.split("\n"):
            if not l.strip():
                yeni_satirlar.append(l)
            elif fark > 0:
                yeni_satirlar.append(ek + l)
            else:
                kes = min(-fark, len(girinti(l)))
                yeni_satirlar.append(l[kes:])
        return b, e, "\n".join(yeni_satirlar), f"girinti {fark:+d} kaydırılarak eşleşti"
    return None


def register(registry: ToolRegistry) -> None:
    # Yazma öncesi bayatlık kontrolü için: yol -> son okunduğundaki mtime_ns.
    seen: dict[Path, int] = {}
    # Bu oturumda en son değiştirilen dosya: `denetle` yolsuz çağrılırsa
    # bakacağı yer. Model "kodu yazdım, bir kontrol edeyim" diyebilsin.
    son_yazilan: list[Path] = []
    # Dosya başına yazım sayısı. Aynı dosyaya üçüncü kez yazmak "gözle
    # düzeltmeye çalışıyorum ve göremiyorum" demek; koşum hatırlatması
    # orada sertleşiyor.
    yazim_sayaci: dict[Path, int] = {}

    @registry.tool(
        name="read_file",
        description="""
Bir dosyayı okur. Metin dosyalarında uzun içerik için `offset` ve `limit`
ile satır aralığı verilebilir; çıktı satır numaralı gelir.

Görsel dosyaları (png, jpg, gif, webp) GERÇEKTEN GÖRÜRSÜN: dosya sana
görüntü olarak gelir. Ekran görüntüsü, tasarım dosyası, hata fotoğrafı —
"okuyamıyorum" deme, aç ve bak.

PDF'lerde ilk sayfaların metni çıkarılır. Taranmış (metinsiz) bir PDF'te
bunu açıkça söyler; o durumda içeriği uydurma.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dosya yolu (göreli ya da mutlak)."},
                "offset": {"type": "integer", "description": "Başlangıç satırı (1'den başlar). PDF'te başlangıç sayfası."},
                "limit": {"type": "integer", "description": "Okunacak satır sayısı. PDF'te sayfa sayısı."},
            },
            required=["path"],
        ),
    )
    async def read_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(args["path"], ctx)
        if not path.exists():
            return ToolResult.error(f"Dosya yok: {path}")
        if path.is_dir():
            return ToolResult.error(f"{path} bir dizin. İçeriği için list_dir kullan.")

        # Metin olmayan biçimler kendi yollarından: bir PNG'yi utf-8 diye
        # okumak modele bir ekran dolusu çöp gönderiyordu ("��…"),
        # ve model o çöpe bakıp dosyanın bozuk olduğunu sanıyordu.
        if _gorsel_mu(path):
            return await asyncio.to_thread(_gorsel_oku, path)
        if path.suffix.lower() == ".pdf":
            return await asyncio.to_thread(
                _pdf_oku, path, args.get("offset"), args.get("limit"))

        def _read() -> tuple[str, int]:
            data = path.read_text(encoding="utf-8", errors="replace")
            return data, path.stat().st_mtime_ns

        try:
            text, mtime = await asyncio.to_thread(_read)
        except OSError as exc:
            return ToolResult.error(f"Okunamadı: {exc}")

        seen[path] = mtime

        lines = text.splitlines()
        offset = max(1, int(args.get("offset") or 1))
        limit = int(args.get("limit") or len(lines))
        window = lines[offset - 1 : offset - 1 + limit]

        numbered = "\n".join(f"{offset + i:>6}\t{line}" for i, line in enumerate(window))
        if len(numbered) > MAX_READ_CHARS:
            numbered = (
                numbered[:MAX_READ_CHARS]
                + f"\n\n... kırpıldı. Devamı için offset={offset + len(window) // 2} kullan."
            )

        footer = ""
        if offset > 1 or offset - 1 + limit < len(lines):
            footer = f"\n\n[{len(lines)} satırın {offset}-{offset + len(window) - 1} arası]"

        return ToolResult(content=(numbered or "(dosya boş)") + footer)

    @registry.tool(
        name="write_file",
        description="""
Dosyayı verilen içerikle yazar; yoksa oluşturur, varsa üzerine yazar.

Var olan bir dosyanın üzerine yazmadan önce onu read_file ile okumuş olman
gerekir. Bu, senin görmediğin değişiklikleri sessizce ezmeni engeller.
Küçük değişiklikler için write_file yerine edit_file kullan.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dosya yolu."},
                "content": {"type": "string", "description": "Dosyanın tam yeni içeriği."},
            },
            required=["path", "content"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def write_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(args["path"], ctx)
        if refused := _guard(path, ctx):
            return refused
        content = args.get("content", "")

        if path.exists():
            if path not in seen:
                return ToolResult.error(
                    f"{path} zaten var ve bu oturumda okunmadı. "
                    "Üzerine yazmadan önce read_file ile oku."
                )
            if path.stat().st_mtime_ns != seen[path]:
                return ToolResult.error(
                    f"{path} sen okuduktan sonra değişti. Tekrar oku, sonra yaz."
                )

        def _write() -> int:
            # Yazmadan hemen önce anlık görüntü: `undo` ancak böyle mümkün.
            _gozle(path, ctx, "write_file")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return path.stat().st_mtime_ns

        try:
            seen[path] = await asyncio.to_thread(_write)
        except OSError as exc:
            return ToolResult.error(f"Yazılamadı: {exc}")

        son_yazilan[:] = [path]
        yazim_sayaci[path] = yazim_sayaci.get(path, 0) + 1
        kosum.dokunuldu(path)
        tani_metni, tani_detay = await _tani_eki(path)
        kosum_metni = await _kosum_eki(path, yazim_sayaci[path])
        return ToolResult(
            content=f"{path} yazıldı ({len(content.splitlines())} satır)."
                    + tani_metni + (f"\n{kosum_metni}" if kosum_metni else ""),
            detail={"path": str(path), "bytes": len(content.encode("utf-8")),
                    **tani_detay},
        )

    @registry.tool(
        name="edit_file",
        description="""
Bir dosyada tam metin değişimi yapar. `old` metni dosyada tam olarak bir kez
geçmelidir — sıfır ya da birden fazla eşleşmede işlem yapılmaz ve hata döner.
Boşluk farkları hoş görülür: satır sonu (CRLF/LF), satır sonundaki boşluk ve
TEK-TİP girinti kayması eşleşmeyi bozmaz (yine tek eşleşme şartıyla; kayma
`new`e de uygulanır). İçerik farkı hoş görülmez.
Benzersiz kılmak için etrafından yeterince bağlam al.

Aynı dosyada birden fazla değişiklik için `edits` ver: [{old, new}, ...].
Uygulama ATOMİKTİR — önce hepsi doğrulanır, biri bile tutmazsa hiçbiri
uygulanmaz ve hangi maddenin neden tutmadığı söylenir.

Dosyayı önce read_file ile okumuş olman gerekir.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dosya yolu."},
                "old": {"type": "string", "description": "Değiştirilecek tam metin (tekli kullanım)."},
                "new": {"type": "string", "description": "Yerine yazılacak metin (tekli kullanım)."},
                "edits": {
                    "type": "array",
                    "description": "Çoklu değişiklik: [{old, new}, ...]. Hepsi ya da hiçbiri.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old": {"type": "string"},
                            "new": {"type": "string"},
                        },
                        "required": ["old", "new"],
                    },
                },
            },
            required=["path"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def edit_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(args["path"], ctx)
        if refused := _guard(path, ctx):
            return refused

        edits = args.get("edits")
        if edits:
            pairs = [(e.get("old"), e.get("new")) for e in edits if isinstance(e, dict)]
            if len(pairs) != len(edits):
                return ToolResult.error("`edits` maddeleri {old, new} nesneleri olmalı.")
        elif "old" in args and "new" in args:
            pairs = [(args["old"], args["new"])]
        else:
            return ToolResult.error(
                "Ya `old`+`new` (tek değişiklik) ya da `edits` (çoklu) vermelisin."
            )

        if not path.exists():
            return ToolResult.error(f"Dosya yok: {path}")
        if path not in seen:
            return ToolResult.error(f"{path} bu oturumda okunmadı. Önce read_file ile oku.")

        text = await asyncio.to_thread(path.read_text, encoding="utf-8")

        # Önce HEPSİ doğrulanır; hata metni maddeyi numarasıyla gösterir ki
        # model neyi düzelteceğini bilsin. Hiçbir şey henüz yazılmadı.
        spans: list[tuple[int, int, str, int]] = []  # (baş, son, yeni, madde no)
        notlar: list[str] = []   # toleransla eşleşenlerin izahı — mesaja girer
        coklu = len(pairs) > 1
        for no, (old, new) in enumerate(pairs, 1):
            hangi = f"{no}. madde: " if coklu else ""
            hicbiri = " Hiçbir değişiklik uygulanmadı." if coklu else ""
            if not isinstance(old, str) or not isinstance(new, str) or not old:
                return ToolResult.error(
                    f"{hangi}`old` ve `new` dolu birer metin olmalı.{hicbiri}"
                )
            count = text.count(old)
            if count == 0:
                # Boşluk/girinti/satır-sonu toleransı: içerik doğruysa tur
                # yakılmaz. Eşleşme yine TEK olmak zorunda.
                esnek = _esnek_esle(text, old, new)
                if isinstance(esnek, tuple) and esnek and esnek[0] == "coklu":
                    return ToolResult.error(
                        f"{hangi}Aranan metin (boşluk toleransıyla) {esnek[1]} kez "
                        f"geçiyor, hangisi olduğu belirsiz. Bağlam ekleyerek "
                        f"benzersizleştir.{hicbiri}"
                    )
                if esnek is None:
                    return ToolResult.error(
                        f"{hangi}Aranan metin dosyada yok. Girintiyi ve satır sonlarını "
                        f"birebir eşleştir; emin değilsen dosyayı tekrar oku.{hicbiri}"
                    )
                b, e, yeni_metin, notu = esnek
                spans.append((b, e, yeni_metin, no))
                notlar.append(f"{hangi}{notu}")
                continue
            if count > 1:
                return ToolResult.error(
                    f"{hangi}Aranan metin {count} kez geçiyor, hangisi olduğu belirsiz. "
                    f"Öncesinden/sonrasından bağlam ekleyerek benzersizleştir.{hicbiri}"
                )
            start = text.index(old)
            spans.append((start, start + len(old), new, no))

        # Sıra bağımsız çakışma kontrolü: iki madde aynı bölgeye dokunuyorsa
        # sonuç maddelerin sırasına bağlı olurdu — bu bir belirsizlik, hata.
        spans.sort()
        for (b1, s1, _, n1), (b2, _, _, n2) in zip(spans, spans[1:]):
            if b2 < s1:
                return ToolResult.error(
                    f"{n1}. ve {n2}. maddeler çakışıyor (aynı metin bölgesini "
                    "değiştiriyorlar). Maddeleri birleştir. Hiçbir değişiklik uygulanmadı."
                )

        def _apply() -> int:
            # Yazmadan hemen önce anlık görüntü: `undo` ancak böyle mümkün.
            _gozle(path, ctx, "edit_file")
            yeni = text
            # Sondan başa: önceki değişimler sonrakilerin konumunu kaydırmasın.
            for start, end, new, _ in reversed(spans):
                yeni = yeni[:start] + new + yeni[end:]
            path.write_text(yeni, encoding="utf-8")
            return path.stat().st_mtime_ns

        seen[path] = await asyncio.to_thread(_apply)
        # Değişikliğin başladığı satır: arayüzdeki adım kartı diff'i gerçek
        # satır numaralarıyla çizebilsin. Çoklu değişiklikte İLK değişikliğin
        # satırı (arayüz sözleşmesi).
        line = text[: spans[0][0]].count("\n") + 1
        mesaj = (
            f"{path} güncellendi ({len(spans)} değişiklik)."
            if len(spans) > 1
            else f"{path} güncellendi."
        )
        if notlar:
            # Tolerans devreye girdiyse model bilsin: bir dahaki old'u
            # dosyadaki gerçek biçimden alması gerektiğinin işareti.
            mesaj += " (" + "; ".join(notlar) + ")"
        son_yazilan[:] = [path]
        yazim_sayaci[path] = yazim_sayaci.get(path, 0) + 1
        kosum.dokunuldu(path)
        tani_metni, tani_detay = await _tani_eki(path)
        kosum_metni = await _kosum_eki(path, yazim_sayaci[path])
        return ToolResult(
            content=mesaj + tani_metni + (f"\n{kosum_metni}" if kosum_metni else ""),
            detail={"path": str(path), "line": line, **tani_detay},
        )

    @registry.tool(
        name="copy_in",
        description="""
Dışarıdaki bir dosyayı ya da klasörü atölyene kopyalar. Orijinaline
dokunulmaz. Atölye dışına yazamadığın için, üzerinde çalışman gereken bir
dosya varsa yolu budur.

`to` verilmezse dosya atölyenin köküne kendi adıyla düşer.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Kopyalanacak kaynak yolu."},
                "to": {
                    "type": "string",
                    "description": "Atölye içinde hedef yol (göreli).",
                },
            },
            required=["path"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def copy_in(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        source = Path(args["path"]).expanduser()
        if not source.is_absolute():
            source = ctx.workspace / source
        if not source.exists():
            return ToolResult.error(f"Kaynak yok: {source}")

        target = _resolve(args.get("to") or source.name, ctx)
        if refused := _guard(target, ctx):
            return refused
        if target.exists():
            return ToolResult.error(
                f"{target} zaten var. Üzerine yazmak istiyorsan başka bir ad ver "
                "ya da önce sil."
            )

        def _copy() -> int:
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                # Dizin kopyası defterde tutulmuyor: onlarca dosyayı tek
                # "yoktu" kaydına sığdırmak geri almayı yalancı yapardı.
                shutil.copytree(source, target)
                return sum(1 for _ in target.rglob("*") if _.is_file())
            # Hedef henüz yok ("yoktu" kaydı düşer); günün birinde üzerine
            # yazma serbest kalırsa aynı çağrı mevcut hali de saklar.
            _gozle(target, ctx, "copy_in")
            shutil.copy2(source, target)
            return 1

        try:
            count = await asyncio.to_thread(_copy)
        except OSError as exc:
            return ToolResult.error(f"Kopyalanamadı: {exc}")

        # Kopya okunmuş sayılıyor: az önce bu süreç yazdı, bayatlık kontrolü
        # burada modeli gereksiz bir read_file turuna zorlardı.
        if target.is_file():
            seen[target] = target.stat().st_mtime_ns

        return ToolResult(
            content=f"{source} → {target} ({count} dosya).",
            detail={"path": str(target), "files": count},
        )

    @registry.tool(
        name="list_dir",
        description="""
Bir dizinin içeriğini listeler. `pattern` verilirse glob deseniyle özyinelemeli
arar (örn. "**/*.py"). Dizinler sonunda / ile gösterilir.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dizin yolu."},
                "pattern": {"type": "string", "description": "Özyinelemeli glob deseni."},
            },
            required=["path"],
        ),
    )
    async def list_dir(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = _resolve(args["path"], ctx)
        if not root.is_dir():
            return ToolResult.error(f"Dizin yok: {root}")

        pattern = args.get("pattern")

        def _scan() -> list[str]:
            entries = sorted(root.glob(pattern)) if pattern else sorted(root.iterdir())
            return [
                f"{p.relative_to(root)}{'/' if p.is_dir() else ''}"
                for p in entries[:MAX_LIST_ENTRIES]
            ]

        try:
            names = await asyncio.to_thread(_scan)
        except OSError as exc:
            return ToolResult.error(f"Listelenemedi: {exc}")

        if not names:
            return ToolResult(content="(boş)")

        body = "\n".join(names)
        if len(names) == MAX_LIST_ENTRIES:
            body += f"\n\n... ilk {MAX_LIST_ENTRIES} girdi gösterildi, daha var."
        return ToolResult(content=f"{root}\n{body}")

    @registry.tool(
        name="denetle",
        description="""
Kodu, dilinin kendi denetleyicisiyle sınar ve bulduğu hataları satır
numaralarıyla döndürür (Python derleyicisi/ruff, `php -l`, `node --check`,
tsc, JSON/YAML ayrıştırıcıları).

`path` bir dosya ya da klasör olabilir; verilmezse en son yazdığın dosyaya
bakar. Klasörde `pattern` ile daraltabilirsin (örn. "*.php").

Ne zaman kullan: bir dosyayı düzenledikten sonra — yazma araçları tanıyı
zaten kendiliğinden ekler, ama elle yazdığın ya da kabuktan ürettiğin
kodu buradan sınarsın.

Dikkat: temiz sonuç "kod çalışıyor" demek DEĞİLDİR. Denetleyiciler
çoğunlukla sözdizimine bakar; tip hataları ve çalışma zamanı davranışı
ancak kodu gerçekten koşturunca ortaya çıkar. Hangi denetleyicinin baktığı
cevapta yazar.
        """,
        input_schema=object_schema(
            {
                "path": {
                    "type": "string",
                    "description": "Denetlenecek dosya ya da klasör. "
                                   "Boş bırakılırsa en son yazılan dosya.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Klasör denetiminde ad deseni (örn. \"*.py\").",
                },
            },
        ),
    )
    async def denetle(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ham = (args.get("path") or "").strip()
        if ham:
            hedef = _resolve(ham, ctx)
        elif son_yazilan:
            hedef = son_yazilan[0]
        else:
            return ToolResult.error(
                "Bu oturumda henüz bir dosya yazmadın, denetlenecek bir şey yok. "
                "Denetlemek istediğin dosyayı `path` ile ver."
            )

        if not hedef.exists():
            return ToolResult.error(f"Yol yok: {hedef}")

        desen = args.get("pattern") or None
        if hedef.is_dir():
            yollar = await asyncio.to_thread(
                tanilar.toplu_yollar, hedef, desen=desen, tavan=MAX_DENETIM_DOSYA
            )
            kok: Path | None = hedef
        else:
            yollar, kok = [hedef], hedef.parent

        if not yollar:
            return ToolResult(
                content=f"{hedef} altında denetlenebilir dosya yok. "
                        "Tanınan uzantılar: " + ", ".join(sorted(tanilar.UZANTILAR)) + "."
            )

        taniler = await asyncio.to_thread(tanilar.denetle_coklu, yollar)
        if not taniler:
            # Tek dosya ve uzantısı tanınmıyor: uydurma yapma, dürüstçe söyle.
            return ToolResult(
                content=f"{hedef} için bir denetleyici tanımıyorum "
                        f"({hedef.suffix or 'uzantısız'}). Kontrol edilmedi."
            )

        hatali = sum(1 for t in taniler if t.durum == "hata")
        return ToolResult(
            content=tanilar.ozet(taniler, kok=kok),
            detail={
                "path": str(hedef),
                "hatali": hatali,
                "taniler": [t.detay() for t in taniler],
            },
        )
