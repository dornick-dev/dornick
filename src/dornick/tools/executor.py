"""Tool executor.

Its responsibilities:
  * meet an unknown tool with a teaching error
  * check the call against the schema BEFORE handing it to the handler (a
    missing/wrong field returns a message that explains the fix, not a
    raw exception)
  * pass every call through the permission gate and the user's hooks
  * run parallel-safe calls concurrently, the others sequentially
  * manage the timeout and the user interrupt
  * produce one tool_result for EVERY tool_use — if even one is missing
    the API returns 400
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

# The permission question is delegated to the UI. True -> run, False -> refuse.
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
    """Executes the calls and returns the tool_result blocks in input order."""
    results: dict[str, Block] = {}
    batch: list[PendingToolUse] = []

    async def flush() -> None:
        if not batch:
            return
        # Concurrency is bounded: the model can ask for ten tools in one
        # turn and starting all of them at once exhausts memory on a weak
        # machine. The limit comes from settings; sub-agents pass through
        # the same gate.
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
        # A call that is not parallel-safe: finish the accumulated batch first.
        await flush()
        if ctx.cancel.is_set():
            break
        results[call.id] = await _run_one(
            call, registry, permissions, ctx, approve, observe, timeout_s
        )

    await flush()

    # Interrupt or early exit: a cancel result for every unanswered tool_use.
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

    # The schema gate comes BEFORE the permission gate: the user must not be
    # asked to approve a broken call (asking "run write_file?" and then
    # blowing up on a missing field would waste the user's time).
    if (warning := schema_violation(spec, call.input)) is not None:
        observe("sema_ihlali", {"tool": spec.name, "id": call.id, "detail": warning})
        return ToolResult.error(warning).to_block(call.id)

    # A MUTATING call that reaches the hook file is refused before the
    # permission gate (the user should not be asked to approve something we
    # will refuse anyway). `tools/files.py` closed that path for the write
    # tools, but the shell is not a write tool — `Set-Content
    # .dornick/kancalar.json` did not pass through that gate.
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
        # Show the fixed-guard reason as is (a mode-independent refusal); a
        # generic "ask for permission" message would mislead — this gate
        # does not open with permission.
        if rule.startswith("sabit:koruma:"):
            return ToolResult.error(rule[len("sabit:koruma:"):]).to_block(call.id)
        return ToolResult.error(
            f"'{spec.name}' politika gereği engellendi ({rule}). "
            "Farklı bir yaklaşım dene ya da kullanıcıdan izin iste."
        ).to_block(call.id)

    if decision is Decision.ASK:
        # Waiting for approval is RACED against the user interrupt: if Stop
        # is pressed while the permission card is open the turn must not
        # hang in the wait. The old version only awaited the future — when
        # the card went unanswered nothing, Stop included, could rescue the
        # turn (live wound, 01.09: "it doesn't stop when I say stop the
        # chat").
        question = asyncio.ensure_future(approve(spec, call.input))
        interrupt = asyncio.ensure_future(ctx.cancel.wait())
        try:
            await asyncio.wait({question, interrupt}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            question.cancel()
            interrupt.cancel()
            return cancelled_result(call.id)
        interrupt.cancel()
        if not question.done():
            question.cancel()
            observe("tool_cancelled", {"tool": spec.name, "id": call.id})
            return cancelled_result(call.id)
        try:
            granted = question.result()
        except asyncio.CancelledError:
            return cancelled_result(call.id)
        except Exception:
            granted = False
        if not granted:
            return ToolResult.error(
                f"Kullanıcı '{spec.name}' çağrısını reddetti. Bu yolu tekrar deneme; "
                "ne yapmak istediğini açıkla ya da başka bir yol öner."
            ).to_block(call.id)

    # The user's own guard. It runs AFTER the permission gate: the hook is
    # the user's rule and the permission engine is the user's rule too — but
    # if the permission gate refused, running the hook would be a wasted
    # side effect (a formatting hook would try to format a file that was
    # never written).
    #
    # Hooks run OUTSIDE the permission engine: no approval prompt appears.
    # This is deliberate — a hook is a command the user wrote by hand into
    # their own file on their own disk, and the model cannot reach that file
    # through either gate: the write tools via `kancalar.is_protected`
    # (`tools/files.py`), the other mutating tools (the shell) via
    # `cagri_kancaya_dokunuyor_mu` above.
    hook_notes: list[str] = []
    try:
        verdict = await hooks.before_tool(
            ctx.config.state_dir, spec.name, call.input,
            session=ctx.session.id, cwd=_hook_cwd(ctx))
    except Exception as exc:  # pragma: no cover - the hook layer must not kill the tool
        verdict = hooks.Verdict(notes=[
            f"kanca katmanı çalışmadı ({type(exc).__name__}: {exc})"])
    hook_notes.extend(verdict.notes)

    if not verdict.allowed:
        observe("kanca_ret", {"tool": spec.name, "id": call.id,
                              "detail": verdict.reason})
        return ToolResult.error(verdict.reason).to_block(call.id)

    observe("tool_start", {"tool": spec.name, "input": call.input, "id": call.id})
    started = time.monotonic()
    # If the tool asked for its own timeout (e.g. shell was given
    # `timeout: 600`) the executor's general 180 s limit must not override
    # it: the model explicitly asks for time for a 10-minute build and the
    # old version killed it at 3 minutes. The general limit stays as is for
    # tools that do not ask for time.
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
    except Exception as exc:  # a tool error must not bring the model down
        # The raw exception text ("KeyError: 'path'") teaches the model
        # nothing; it even teaches something wrong — the model can read it
        # as "the tool is broken" and stop calling tools (proven: it then
        # wrote the call XML as plain text). The same information is wrapped
        # in a sentence that says what to do. No traceback: it has no place
        # in the model's context, it is already in the log.
        result = ToolResult.error(
            f"'{spec.name}' aracı çalışırken hata verdi — "
            f"{type(exc).__name__}: {exc}. Bu aracın hatası; çağrını gözden "
            "geçirip (alanlar, yollar, değerler) yeniden dene ya da başka "
            "bir yol izle."
        )

    # The tool finished: informational hooks. They have no veto — the work
    # is already done. Their output is appended to the tool result as single
    # lines so the model sees that `black` ran and the file was formatted.
    try:
        hook_notes.extend(await hooks.after_tool(
            ctx.config.state_dir, spec.name, call.input,
            session=ctx.session.id, cwd=_hook_cwd(ctx)))
    except Exception as exc:  # pragma: no cover
        hook_notes.append(f"kanca katmanı çalışmadı ({type(exc).__name__}: {exc})")

    if hook_notes:
        result = _append_hook_notes(result, hook_notes)

    elapsed = time.monotonic() - started
    note = {
        "tool": spec.name,
        "id": call.id,
        "ms": round(elapsed * 1000),
        "error": result.is_error,
        # One-line result summary so the UI can draw a trace like "⎿ 340
        # satır" under the tool row. NOT the raw output — first line +
        # volume; the output itself is already in the model's context, it is
        # not streamed to the user.
        "summary": _brief(result),
    }
    # Rich step card: when the step is expanded the UI can show the real
    # output (command output, read preview, exit code, the changed line).
    # Not the whole raw dump — head + tail for long output; clipped hard so
    # as not to bloat the hub and the browser DOM.
    if card := _card(result):
        note["detail"] = card
    # The touched path is carried to the UI so the viewer can refresh the
    # file whose job is done. The path the tool itself reports is more
    # accurate than the argument in the call — it arrives with the relative
    # path resolved.
    if path := result.detail.get("path"):
        note["path"] = str(path)
    observe("tool_end", note)

    # If the tool returned an image it cannot be carried in the block: the
    # OpenAI contract wants role=tool content to be a string. The loop sees
    # this and attaches it to the next user turn. `images` (a list) is for
    # camera captures: several frames can come out of one tool result.
    image = result.detail.get("image") or result.detail.get("images")
    if image:
        block = result.to_block(call.id)
        block["_image"] = image
        return block
    return result.to_block(call.id)


def _hook_cwd(ctx: ToolContext) -> str:
    """The hook's working directory: the workshop if there is one, else the workspace.

    It must be predictable — if the user uses a relative path in a hook
    they must know what it is relative to.
    """
    try:
        if ctx.sandbox.enabled:
            return str(ctx.sandbox.root)
    except Exception:  # pragma: no cover - the workshop cannot be opened
        pass
    return str(ctx.workspace)


def _append_hook_notes(result: ToolResult, notes: list[str]) -> ToolResult:
    """Appends the hook lines to the END of the tool result.

    If the content is a block list (an image-returning tool) no text is
    added: squeezing text between the blocks breaks the contract and a hook
    note on an image tool is rare anyway. It is still carried in the detail.
    """
    detail = {**result.detail, "kancalar": list(notes)}
    if not isinstance(result.content, str):
        return ToolResult(content=result.content, is_error=result.is_error,
                          detail=detail)
    tail = "\n".join(notes)
    body = f"{result.content}\n\n{tail}" if result.content.strip() else tail
    return ToolResult(content=body, is_error=result.is_error, detail=detail)


# Clipping limits of the card output: lines from the head/tail, total
# characters. In a pytest dump the interesting parts are the head (which
# tests) and the tail (the summary line); the middle is already in the
# model's context anyway.
CARD_HEAD = 60
CARD_TAIL = 20
CARD_CHARS = 12_000


def _card(result: ToolResult) -> dict[str, Any]:
    """The step card's payload: clipped output + small tool-specific fields.

    For image-returning tools the content is a block list; no text is
    pulled from there — the card carries no image, the image is already
    attached to the chat.
    """
    card: dict[str, Any] = {}
    # The exit badge on the shell card; the changed line on the edit card.
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
    """The result's one-line trace: first line + volume.

    For an image-returning tool the text can be empty; then the trace is
    empty too — the UI draws no line.
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
