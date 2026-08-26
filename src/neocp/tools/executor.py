"""Araç yürütücüsü.

Sorumlulukları:
  * bilinmeyen aracı öğretici hatayla karşılamak
  * her çağrıyı izin kapısından geçirmek
  * paralel-güvenli çağrıları eşzamanlı, diğerlerini sırayla koşturmak
  * zaman aşımı ve kullanıcı kesmesini yönetmek
  * HER tool_use için bir tool_result üretmek — biri bile eksikse API 400 döner
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Sequence

from ..permissions import Decision, PermissionEngine
from ..session import PendingToolUse, cancelled_result
from .base import Block, ToolContext, ToolRegistry, ToolResult, ToolSpec

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

    decision, rule = permissions.evaluate(spec, call.input)
    observe("permission", {"tool": spec.name, "decision": decision.value, "rule": rule})

    if decision is Decision.DENY:
        return ToolResult.error(
            f"'{spec.name}' politika gereği engellendi ({rule}). "
            "Farklı bir yaklaşım dene ya da kullanıcıdan izin iste."
        ).to_block(call.id)

    if decision is Decision.ASK:
        try:
            granted = await approve(spec, call.input)
        except asyncio.CancelledError:
            return cancelled_result(call.id)
        if not granted:
            return ToolResult.error(
                f"Kullanıcı '{spec.name}' çağrısını reddetti. Bu yolu tekrar deneme; "
                "ne yapmak istediğini açıkla ya da başka bir yol öner."
            ).to_block(call.id)

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
        result = ToolResult.error(f"{type(exc).__name__}: {exc}")

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
    # Dokunulan yol arayüze taşınıyor: görüntüleyici işi biten dosyayı
    # tazeleyebilsin. Aracın kendi bildirdiği yol, çağrıdaki argümandan
    # daha doğru — göreli yol çözülmüş halde geliyor.
    if path := result.detail.get("path"):
        note["path"] = str(path)
    observe("tool_end", note)

    # Araç bir görüntü döndürdüyse blokta taşınamıyor: OpenAI sözleşmesi
    # role=tool içeriğinin dize olmasını istiyor. Döngü bunu görüp bir
    # sonraki kullanıcı turuna iliştiriyor.
    if image := result.detail.get("image"):
        block = result.to_block(call.id)
        block["_image"] = image
        return block
    return result.to_block(call.id)


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
