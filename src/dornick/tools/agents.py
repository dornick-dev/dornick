"""Subagent tools.

The agent being able to spawn helpers is not a convenience, it is a
context matter. A job like "walk the twenty files in that folder and
find which one mentions X" produces thirty tool calls, and the output
of all thirty piles into the main conversation's window. Yet the only
thing that should remain is the answer itself.

The subagent works in its own session with its own history; only the
result returns to the main agent. So this tool splits **context** far
more than it splits work.

There are two modes:

    waiting     (default) `task` waits until the result arrives — for
                short jobs whose result is needed right away.
    background  `task` returns immediately, the helper runs behind; when
                done the result is reported to the main agent. For
                long-running jobs or ones whose result is not needed
                immediately. A running helper is steered with `task_say`
                and its status queried with `task_status`.

There are two limits:

    depth       A subagent gets no subagents of its own. Otherwise a
                single request would fan out like a tree and nobody
                would know how much work was being done.
    permission  The subagent is bound to the same permission engine. A
                gate that can be skipped by saying "I am a subagent" is
                not a gate.
"""

from __future__ import annotations

from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Bir işi kendi bağlamında yürütmesi için alt ajan (yardımcı) başlatır.
Yardımcı senin araçlarınla çalışır, kendi oturumunda ilerler ve ara
adımları senin bağlamını doldurmaz — sana sonucu döner: bekleyerek
başlattıysan hemen, arka planda başlattıysan bittiğinde bildirilerek.

Ne zaman kullan (genel kural: bağımsız, paralelleştirilebilir ya da uzun
soluklu işleri yardımcılara devret):
- Arama/tarama işleri: "şu dizinde X geçen dosyaları bul"
- Çok adımlı ama sonucu kısa işler: "bu üç kaynağı oku ve karşılaştır"
- Birbirinden bağımsız parçalar: birkaç yardımcıyı aynı turda başlat,
  paralel çalışırlar
- Sonucuna hemen ihtiyacın yoksa `arka_plan: true` ver ve beklemeden kendi
  işine devam et — bitince haber gelir. Koşan yardımcıya `task_say` ile
  yön verebilirsin.

Ne zaman kullanma:
- Tek araç çağrısıyla biten iş: doğrudan yap, yardımcı pahalı
- Kullanıcıyla konuşulması gereken iş: yardımcı kullanıcıyı göremiyor

`task` alanını eksiksiz yaz: yardımcı bu konuşmayı görmüyor, yalnızca senin
verdiğin metni görüyor. Ne aradığını, nerede arayacağını ve neyi döndürmesini
istediğini açıkça söyle.
"""

SAY_DESCRIPTION = """
Koşan ya da bitmiş bir yardımcıya mesaj gönderir. Koşana: mesaj yardımcının
bir sonraki adımına not olarak girer (yön değiştirme, ek bilgi, kapsam
daraltma). Bitmişe: yardımcının oturumu diskten açılır ve mesajla arka
planda sürdürülür — bitince sonucu sana bildirilir. Kimlikleri `task`
başlatırken aldın; unuttuysan `task_status` ile bak.
"""

STATUS_DESCRIPTION = """
Yardımcıların durum özetini verir: kimlik, başlık, durum (koşuyor · bitti ·
hata) ve bitmişlerde sonucun başı. `id` verirsen yalnız o yardımcıyı gösterir.
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="task",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "title": {
                    "type": "string",
                    "description": "Kısa etiket; arayüzde bu görünüyor.",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Alt ajana verilecek eksiksiz yönerge. Bu konuşmayı "
                        "görmüyor; gereken bağlamı buraya yaz."
                    ),
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Alt ajanın kullanacağı model. Boşsa seninkini "
                        "kullanır. Basit tarama işini küçük ve hızlı bir "
                        "modele, görüntü gerektiren işi görüntü okuyan bir "
                        "modele ver — hangi modellerin ne yapabildiğini "
                        "`models` ile öğren. KİMLİĞİ UYDURMA: emin "
                        "değilsen bu alanı boş bırak (ana model kullanılır) "
                        "ya da önce `models` ile bak."
                    ),
                },
                "arka_plan": {
                    "type": "boolean",
                    "description": (
                        "true: yardımcı arka planda koşar, bu araç hemen "
                        "döner ve sen beklemeden devam edersin; sonucu "
                        "bitince sana bildirilir. Varsayılan false: sonuç "
                        "gelene kadar beklenir."
                    ),
                },
            },
            required=["task"],
        ),
        # Its side effects happen through the tools, and all of those already
        # pass the permission gate; the tool itself changes nothing.
        mutates=False,
        # Independent subagents must be able to run in parallel within the
        # same turn — that is where the real gain is.
        parallel_safe=True,
    )
    async def task(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if ctx.spawn is None:
            return ToolResult.error(
                "Alt ajan başlatılamıyor: en fazla bir seviye derinlik var ve "
                "sen zaten bir alt ajansın. İşi kendin yap."
            )

        instruction = str(args.get("task") or "").strip()
        if not instruction:
            return ToolResult.error("Boş görev. Alt ajanın ne yapacağını `task` alanına yaz.")

        title = str(args.get("title") or "").strip() or _headline(instruction)
        model, warning = _validate_model(str(args.get("model") or ""), ctx)

        if bool(args.get("arka_plan")) and ctx.spawn_bg is not None:
            handle = ctx.spawn_bg(title, instruction, model)
            return ToolResult(
                content=warning + (
                    f"yardımcı başlatıldı · id={handle.id} · başlık={handle.title} — "
                    "bitince sonucu sana bildirilecek; beklemeden işine devam et. "
                    "Koşarken `task_say` ile yön verebilir, `task_status` ile "
                    "durumunu sorabilirsin."
                ),
                detail={"title": handle.title, "id": handle.id, "arka_plan": True},
            )

        answer = await ctx.spawn(title, instruction, model)
        if not answer.strip():
            return ToolResult.error(
                warning
                + f"'{title}' alt ajanı bir sonuç döndürmeden bitti. "
                "Görevi daha açık yazıp tekrar dene."
            )
        return ToolResult(content=warning + answer, detail={"title": title})

    @registry.tool(
        name="task_say",
        description=SAY_DESCRIPTION,
        input_schema=object_schema(
            {
                "id": {
                    "type": "string",
                    "description": "Yardımcının kimliği (task başlatırken verildi).",
                },
                "message": {
                    "type": "string",
                    "description": "İletilecek mesaj: yön, ek bilgi, yeni istek.",
                },
            },
            required=["id", "message"],
        ),
        mutates=False,
        parallel_safe=True,
    )
    async def task_say(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if ctx.child_say is None:
            return ToolResult.error(
                "Yardımcıya mesaj gönderilemiyor: sen zaten bir alt ajansın."
            )
        message = str(args.get("message") or "").strip()
        if not message:
            return ToolResult.error("Boş mesaj. Ne iletmek istediğini `message` alanına yaz.")
        ok, text = ctx.child_say(str(args.get("id") or ""), message)
        return ToolResult(content=text) if ok else ToolResult.error(text)

    @registry.tool(
        name="task_status",
        description=STATUS_DESCRIPTION,
        input_schema=object_schema(
            {
                "id": {
                    "type": "string",
                    "description": "Boşsa tüm yardımcılar; doluysa yalnız o kimlik.",
                },
            },
        ),
        mutates=False,
        parallel_safe=True,
    )
    async def task_status(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if ctx.child_status is None:
            return ToolResult.error("Durum sorulamıyor: sen zaten bir alt ajansın.")
        return ToolResult(content=ctx.child_status(str(args.get("id") or "")))


def _headline(text: str, limit: int = 60) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


# --- model validation ----------------------------------------------------
#
# The model can hand the helper a MADE-UP id. Seen in the field:
# `qwen3.1-14b` — no such model at the provider, the helper gets a 400 on
# its first request and the turn burns for nothing. The error blows up in
# the subagent's log; the main agent only sees "the helper failed" and
# does not know why.
#
# Rule: if an id was given, compare it against the catalog BEFORE spawn.
#   - catalog empty (no network, server gives no list) → validation is
#     SKIPPED; making the tool unusable on an offline machine would be worse
#   - id in the catalog → passes as-is
#   - only the letter case differs → corrected to the catalog's spelling
#   - not in the catalog → the helper starts with the MAIN model (the job
#     does not die) and the tool's reply teaches what happened


def _catalog(ctx: ToolContext) -> list[str]:
    """The provider's REAL model ids; empty list if unreachable.

    "Oto" (the free model pool) is removed from the catalog: it is a mode,
    not a model, and it gets added to the list even when the provider
    returns none. If it is all that remains, there is effectively no
    catalog — validating against it would declare EVERY real id of the
    provider "invalid".
    """
    try:
        from .. import settings
        from ..config import OTO_MODEL

        return [
            ident
            for entry in settings.scan_models(ctx.config)
            if isinstance(entry, dict) and (ident := str(entry.get("id") or ""))
            and ident != OTO_MODEL
        ]
    except Exception:
        # Validation is a convenience; if it blows up, the job itself must not stop.
        return []


def _validate_model(model: str, ctx: ToolContext) -> tuple[str, str]:
    """Returns (model to use, warning to hand the main agent)."""
    model = model.strip()
    if not model:
        return "", ""

    catalog = _catalog(ctx)
    if not catalog:
        return model, ""      # no network / server gives no list: validation skipped
    if model in catalog:
        return model, ""

    # If only the letter case differs this is not a fabrication but a
    # spelling slip: we correct to the catalog's form and continue silently.
    for candidate in catalog:
        if candidate.lower() == model.lower():
            return candidate, ""

    from difflib import get_close_matches

    close = get_close_matches(model, catalog, n=3, cutoff=0.6)
    hint = (" Bunu mu demek istedin: " + ", ".join(f"`{a}`" for a in close) + "."
            if close else "")
    return "", (
        f"`{model}` geçerli bir model kimliği değil. Yardımcıyı ana modelle "
        f"başlatıyorum.{hint} Kullanılabilir modelleri `models` aracıyla "
        "görebilirsin.\n\n"
    )
