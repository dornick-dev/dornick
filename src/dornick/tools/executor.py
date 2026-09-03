"""Araç yürütücüsü.

Sorumlulukları:
  * bilinmeyen aracı öğretici hatayla karşılamak
  * çağrıyı handler'a vermeden ÖNCE şemaya vurmak (eksik/yanlış alan ham
    istisna değil, düzeltmeyi anlatan bir mesajla dönsün)
  * her çağrıyı izin kapısından ve kullanıcının kancalarından geçirmek
  * paralel-güvenli çağrıları eşzamanlı, diğerlerini sırayla koşturmak
  * zaman aşımı ve kullanıcı kesmesini yönetmek
  * HER tool_use için bir tool_result üretmek — biri bile eksikse API 400 döner
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Sequence

from .. import hooks
from ..permissions import Decision, PermissionEngine
from ..session import PendingToolUse, cancelled_result
from .base import Block, ToolContext, ToolRegistry, ToolResult, ToolSpec, schema_violation

DEFAULT_TIMEOUT_S = 180.0

# İzin sorusu arayüze delege edilir. True -> çalıştır, False -> reddet.
Approver = Callable[[ToolSpec, dict[str, Any]], Awaitable[bool]]
Observer = Callable[[str, dict[str, Any]], None]


async def execute(
    calls: Sequence[PendingToolUse],
    *,
    registry: ToolRegistry,
    permissions: PermissionEngine,
    ctx: ToolContext,
    approve: Approver,
    observe: Observer = lambda *_: None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[Block]:
    """Çağrıları yürütür ve giriş sırasıyla tool_result bloklarını döndürür."""
    results: dict[str, Block] = {}
    batch: list[PendingToolUse] = []

    async def flush() -> None:
        if not batch:
            return
        # Eşzamanlılık sınırlı: model bir turda on araç birden isteyebiliyor
        # ve hepsini aynı anda başlatmak zayıf bir makinede belleği tüketiyor.
        # Sınır ayarlardan geliyor; alt ajanlar da aynı kapıdan geçiyor.
        gate = asyncio.Semaphore(max(1, ctx.config.context.max_parallel))

        async def guarded(call: PendingToolUse):
            async with gate:
                return await _run_one(
                    call, registry, permissions, ctx, approve, observe, timeout_s
                )

        gathered = await asyncio.gather(*(guarded(c) for c in batch))
        for call, block in zip(batch, gathered):
            results[call.id] = block
        batch.clear()

    for call in calls:
        if ctx.cancel.is_set():
            break
        spec = registry.get(call.name)
        if spec is not None and spec.parallel_safe:
            batch.append(call)
            continue
        # Paralel-güvenli olmayan çağrı: önce biriken partiyi bitir.
        await flush()
        if ctx.cancel.is_set():
            break
        results[call.id] = await _run_one(
            call, registry, permissions, ctx, approve, observe, timeout_s
        )

    await flush()

    # Kesme ya da erken çıkış: karşılıksız kalan her tool_use'a iptal sonucu.
    return [results.get(c.id) or cancelled_result(c.id) for c in calls]


async def _run_one(
    call: PendingToolUse,
    registry: ToolRegistry,
    permissions: PermissionEngine,
    ctx: ToolContext,
    approve: Approver,
    observe: Observer,
    timeout_s: float,
) -> Block:
    spec = registry.get(call.name)
    if spec is None:
        available = ", ".join(t.name for t in registry.all())
        return ToolResult.error(
            f"'{call.name}' diye bir araç yok. Kullanılabilir araçlar: {available}"
        ).to_block(call.id)

    # Şema kapısı izin kapısından ÖNCE: bozuk bir çağrı için kullanıcıya
    # onay sorulmamalı ("write_file çalıştırılsın mı?" diye sorup sonra
    # eksik alandan patlamak, kullanıcının vaktini boşa harcamak olur).
    if (uyari := schema_violation(spec, call.input)) is not None:
        observe("sema_ihlali", {"tool": spec.name, "id": call.id, "detail": uyari})
        return ToolResult.error(uyari).to_block(call.id)

    # Kanca dosyasına uzanan DEĞİŞTİREN çağrı: izin kapısından önce reddedilir
    # (kullanıcıya zaten reddedeceğimiz bir şey için onay sorulmamalı).
    # `tools/files.py` yazma araçlarının yolunu kapatıyordu ama kabuk bir yazma
    # aracı değil — `Set-Content .dornick/kancalar.json` o kapıdan geçmiyordu.
    if spec.mutates and hooks.call_touches_hook(spec.name, call.input):
        observe("kanca_ret", {"tool": spec.name, "id": call.id,
                              "detail": "kanca dosyası"})
        return ToolResult.error(
            "Bu çağrı kanca dosyasına (.dornick/kancalar.json) uzanıyor ve "
            "engellendi. Kancalar kullanıcının senin üzerinde kurduğu "
            "kurallardır; onay penceresi olmadan çalışırlar ve tam bu yüzden "
            "senin değiştirebileceğin bir yerde durmazlar. İçeriğini görmek "
            "istiyorsan `read_file` ile oku; bir kancanın değişmesi "
            "gerekiyorsa kullanıcıya söyle."
        ).to_block(call.id)

    decision, rule = permissions.evaluate(spec, call.input)
    observe("permission", {"tool": spec.name, "decision": decision.value, "rule": rule})

    if decision is Decision.DENY:
        # Sabit koruma gerekçesini olduğu gibi göster (kip-bağımsız ret);
        # jenerik "izin iste" mesajı yanıltıcı olurdu — bu kapı izinle açılmaz.
        if rule.startswith("sabit:koruma:"):
            return ToolResult.error(rule[len("sabit:koruma:"):]).to_block(call.id)
        return ToolResult.error(
            f"'{spec.name}' politika gereği engellendi ({rule}). "
            "Farklı bir yaklaşım dene ya da kullanıcıdan izin iste."
        ).to_block(call.id)

    if decision is Decision.ASK:
        # Onay bekleyişi kullanıcı kesmesiyle YARIŞTIRILIYOR: izin kartı
        # açıkken Durdur'a basılırsa tur bekleyişte asılı kalmamalı. Eski
        # hal yalnız future'ı bekliyordu — kart cevapsız kaldığında Durdur
        # dahil hiçbir şey turu kurtaramıyordu (canlı yara, 01.09: "sohbeti
        # durdur dediğimde durmuyor").
        soru = asyncio.ensure_future(approve(spec, call.input))
        kesme = asyncio.ensure_future(ctx.cancel.wait())
        try:
            await asyncio.wait({soru, kesme}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            soru.cancel()
            kesme.cancel()
            return cancelled_result(call.id)
        kesme.cancel()
        if not soru.done():
            soru.cancel()
            observe("tool_cancelled", {"tool": spec.name, "id": call.id})
            return cancelled_result(call.id)
        try:
            granted = soru.result()
        except asyncio.CancelledError:
            return cancelled_result(call.id)
        except Exception:
            granted = False
        if not granted:
            return ToolResult.error(
                f"Kullanıcı '{spec.name}' çağrısını reddetti. Bu yolu tekrar deneme; "
                "ne yapmak istediğini açıkla ya da başka bir yol öner."
            ).to_block(call.id)

    # Kullanıcının kendi bekçisi. İzin kapısından SONRA çalışıyor: kanca
    # kullanıcının kuralı, izin motoru da kullanıcının kuralı — ama izin
    # kapısı reddettiyse kancayı koşturmak boşa yan etki olurdu (biçimlendirme
    # kancası hiç yazılmayan bir dosyayı biçimlendirmeye kalkardı).
    #
    # Kancalar izin motorunun DIŞINDA çalışır: onay penceresi çıkmaz. Bu
    # bilinçli — kanca kullanıcının kendi diskindeki kendi dosyasına kendi
    # eliyle yazdığı komuttur ve model o dosyaya iki kapıdan da uzanamaz:
    # yazma araçları `kancalar.korunan_mu` (`tools/files.py`), diğer
    # değiştiren araçlar (kabuk) yukarıdaki `cagri_kancaya_dokunuyor_mu`.
    kanca_notlari: list[str] = []
    try:
        karar = await hooks.before_tool(
            ctx.config.state_dir, spec.name, call.input,
            oturum=ctx.session.id, cwd=_kanca_dizini(ctx))
    except Exception as exc:  # pragma: no cover - kanca katmanı aracı öldürmesin
        karar = hooks.Karar(notlar=[
            f"kanca katmanı çalışmadı ({type(exc).__name__}: {exc})"])
    kanca_notlari.extend(karar.notlar)

    if not karar.izin:
        observe("kanca_ret", {"tool": spec.name, "id": call.id,
                              "detail": karar.gerekce})
        return ToolResult.error(karar.gerekce).to_block(call.id)

    observe("tool_start", {"tool": spec.name, "input": call.input, "id": call.id})
    started = time.monotonic()
    # Araç kendi zaman aşımını istediyse (ör. shell'e `timeout: 600` verildi)
    # yürütücünün 180 sn'lik genel sınırı onu ezmemeli: model 10 dakikalık
    # bir derleme için açıkça süre istiyor ve eski hal onu 3 dakikada
    # öldürüyordu. Genel sınır, süre istemeyen araçlar için aynen duruyor.
    wanted = call.input.get("timeout")
    if isinstance(wanted, (int, float)) and wanted > 0:
        timeout_s = max(timeout_s, float(wanted) + 30.0)
    try:
        result = await asyncio.wait_for(spec.handler(call.input, ctx), timeout=timeout_s)
    except asyncio.TimeoutError:
        result = ToolResult.error(
            f"'{spec.name}' {timeout_s:.0f} saniyede tamamlanmadı ve durduruldu. "
            "İşi daha küçük adımlara böl."
        )
    except asyncio.CancelledError:
        observe("tool_cancelled", {"tool": spec.name, "id": call.id})
        return cancelled_result(call.id)
    except Exception as exc:  # araç hatası modeli düşürmemeli
        # Ham istisna metni ("KeyError: 'path'") modele hiçbir şey
        # öğretmiyor; hatta yanlış bir şey öğretiyor — model bunu "araç
        # bozuk" diye okuyup araç çağırmayı bırakabiliyor (kanıtlandı:
        # ardından çağrı XML'ini düz metin yazdı). Aynı bilgi, ne
        # yapılacağını söyleyen bir cümleyle sarmalanıyor. Traceback
        # gitmiyor: modelin bağlamında yeri yok, günlükte zaten var.
        result = ToolResult.error(
            f"'{spec.name}' aracı çalışırken hata verdi — "
            f"{type(exc).__name__}: {exc}. Bu aracın hatası; çağrını gözden "
            "geçirip (alanlar, yollar, değerler) yeniden dene ya da başka "
            "bir yol izle."
        )

    # Araç bitti: bilgilendirme kancaları. Veto yetkileri yok — iş çoktan
    # oldu. Çıktıları araç sonucuna tek satır olarak ekleniyor ki model
    # `black` çalıştığını, dosyanın biçimlendirildiğini görsün.
    try:
        kanca_notlari.extend(await hooks.after_tool(
            ctx.config.state_dir, spec.name, call.input,
            oturum=ctx.session.id, cwd=_kanca_dizini(ctx)))
    except Exception as exc:  # pragma: no cover
        kanca_notlari.append(f"kanca katmanı çalışmadı ({type(exc).__name__}: {exc})")

    if kanca_notlari:
        result = _kanca_ekle(result, kanca_notlari)

    elapsed = time.monotonic() - started
    note = {
        "tool": spec.name,
        "id": call.id,
        "ms": round(elapsed * 1000),
        "error": result.is_error,
        # Tek satırlık sonuç özeti: arayüz araç satırının altına "⎿ 340 satır"
        # gibi bir iz çizebilsin. Ham çıktı DEĞİL — ilk satır + hacim; çıktının
        # kendisi zaten modelin bağlamında, kullanıcıya akıtılmıyor.
        "summary": _brief(result),
    }
    # Zengin adım kartı: adım açıldığında arayüz gerçek çıktıyı (komut
    # çıktısı, okuma önizlemesi, çıkış kodu, değişikliğin satırı)
    # gösterebilsin. Ham dökümün tamamı değil — uzun çıktıda baş + son;
    # hub'ı ve tarayıcı DOM'unu şişirmemek için sert kırpılıyor.
    if card := _card(result):
        note["detail"] = card
    # Dokunulan yol arayüze taşınıyor: görüntüleyici işi biten dosyayı
    # tazeleyebilsin. Aracın kendi bildirdiği yol, çağrıdaki argümandan
    # daha doğru — göreli yol çözülmüş halde geliyor.
    if path := result.detail.get("path"):
        note["path"] = str(path)
    observe("tool_end", note)

    # Araç bir görüntü döndürdüyse blokta taşınamıyor: OpenAI sözleşmesi
    # role=tool içeriğinin dize olmasını istiyor. Döngü bunu görüp bir
    # sonraki kullanıcı turuna iliştiriyor. `images` (liste) kamera
    # kesitleri için: birkaç kare tek araç sonucundan çıkabiliyor.
    image = result.detail.get("image") or result.detail.get("images")
    if image:
        block = result.to_block(call.id)
        block["_image"] = image
        return block
    return result.to_block(call.id)


def _kanca_dizini(ctx: ToolContext) -> str:
    """Kancanın çalışma dizini: atölye varsa orası, yoksa çalışma alanı.

    Öngörülebilir olması şart — kullanıcı kancasında göreli yol
    kullanacaksa neye göre olduğunu bilmeli.
    """
    try:
        if ctx.sandbox.enabled:
            return str(ctx.sandbox.root)
    except Exception:  # pragma: no cover - atölye açılamıyorsa
        pass
    return str(ctx.workspace)


def _kanca_ekle(result: ToolResult, notlar: list[str]) -> ToolResult:
    """Kanca satırlarını araç sonucunun SONUNA ekler.

    İçerik blok listesiyse (görüntü döndüren araç) metin eklenmiyor:
    blokların arasına metin sıkıştırmak sözleşmeyi bozar ve kanca notu
    bir görüntü aracında zaten nadir. Detayda yine de taşınıyor.
    """
    detay = {**result.detail, "kancalar": list(notlar)}
    if not isinstance(result.content, str):
        return ToolResult(content=result.content, is_error=result.is_error,
                          detail=detay)
    kuyruk = "\n".join(notlar)
    govde = f"{result.content}\n\n{kuyruk}" if result.content.strip() else kuyruk
    return ToolResult(content=govde, is_error=result.is_error, detail=detay)


# Kart çıktısının kırpma sınırları: baştan/sondan satır, toplam karakter.
# Bir pytest dökümünde ilginç olan baş (hangi testler) ve son (özet satırı);
# ortası zaten modelin bağlamında duruyor.
CARD_HEAD = 60
CARD_TAIL = 20
CARD_CHARS = 12_000


def _card(result: ToolResult) -> dict[str, Any]:
    """Adım kartının veri yükü: kırpılmış çıktı + araca özgü küçük alanlar.

    Görüntü dönen araçlarda content blok listesi olur; oradan metin
    çekilmiyor — kart görüntü taşımıyor, görüntü zaten sohbete iliştiriliyor.
    """
    card: dict[str, Any] = {}
    # Kabuk kartındaki çıkış rozeti; edit kartındaki değişiklik satırı.
    for key in ("exit_code", "line"):
        if (value := result.detail.get(key)) is not None:
            card[key] = value
    text = result.content.strip() if isinstance(result.content, str) else ""
    if text:
        lines = text.splitlines()
        if len(lines) > CARD_HEAD + CARD_TAIL + 1:
            skipped = len(lines) - CARD_HEAD - CARD_TAIL
            lines = (lines[:CARD_HEAD]
                     + [f"… ({skipped} satır atlandı) …"]
                     + lines[-CARD_TAIL:])
        output = "\n".join(lines)
        if len(output) > CARD_CHARS:
            output = output[:CARD_CHARS] + "…"
        card["output"] = output
    return card


def _brief(result: ToolResult, width: int = 90) -> str:
    """Sonucun tek satırlık izi: ilk satır + hacim.

    Görüntü dönen araçta metin boş olabiliyor; o zaman iz de boş — arayüz
    satır çizmiyor.
    """
    text = (result.content or "").strip()
    if not text:
        return ""
    lines = text.splitlines()
    first = lines[0].strip()
    if len(first) > width:
        first = first[:width] + "…"
    if len(lines) > 1:
        first += f"  (+{len(lines) - 1} satır)"
    return first
