"""Context and cache policy.

One invariant rule: **the cache is a prefix match.** If any byte in the
prefix changes, everything after that point is invalidated. Render order is
tools -> system -> messages. Every decision here derives from that rule.

This module never modifies history in place; it produces a copy that goes
to the API. The event log keeps holding the raw truth.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .config import ContextConfig, ModelConfig

if TYPE_CHECKING:  # pragma: no cover
    from .prompt import SystemPrompt

Block = dict[str, Any]
Message = dict[str, Any]

EPHEMERAL: Block = {"type": "ephemeral"}

# Total breakpoint limit in an API request. One is reserved for the system prompt.
MAX_BREAKPOINTS = 4

# Server-side context editing beta flags.
CONTEXT_EDIT_BETA = "context-management-2025-06-27"
COMPACT_BETA = "compact-2026-01-12"

IMAGE_PLACEHOLDER = "[eski ekran görüntüsü bağlamdan çıkarıldı]"

# Trim threshold (chars) for old tool payloads and the untouched tail.
#
# The measured wound: while writing a web page the entire HTML enters the
# history in the `write_file` argument and is re-sent WITH EVERY SUBSEQUENT
# REQUEST — ~12-14k of a real 51,608-token prompt was this. The file is
# already sitting on disk; what the model needs in history is the trace of
# "what did I do", not the bytes themselves. It opens it with read_file if needed.
#
# The tail is preserved: the model may still refer to content it just
# wrote/read. Anthropic's server-side `clear_tool_uses` beta does the same
# job but only on the Anthropic backend; this path works on every backend.
TRIM_TOOL_CHARS = 1_600
TRIM_KEEP_MESSAGES = 6
# Browser / big-dump tools: trim more aggressively except for the last 1–2 messages.
TRIM_BROWSER_CHARS = 600
TRIM_BROWSER_KEEP = 2
TRIM_NOTE = "… [{gone:,} harf geçmişten kısaltıldı — gerekirse dosyadan/araçtan yeniden oku]"

# These tools' results carry HTML/DOM/network dumps; keeping them in history
# bloats the prompt in Market Lens style scans.
_HEAVY_TOOLS = frozenset({
    "browser", "fetch", "read_file", "write_file", "edit_file",
})


@dataclass(slots=True)
class Prepared:
    """Request parts ready to be sent to the API."""

    system: list[Block]
    messages: list[Message]
    betas: list[str]
    context_management: dict[str, Any] | None

    def request_kwargs(self, model: ModelConfig, tools: list[dict[str, Any]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model.name,
            "max_tokens": model.max_tokens,
            "system": self.system,
            "messages": drop_provider_fields(self.messages),
            "tools": tools,
            "output_config": {"effort": model.effort},
        }
        if (thinking := model.thinking_param()) is not None:
            kwargs["thinking"] = thinking
        if self.context_management:
            kwargs["context_management"] = self.context_management
        if self.betas:
            kwargs["betas"] = self.betas
        return kwargs

    @property
    def needs_beta_client(self) -> bool:
        return bool(self.betas)


class ContextPolicy:
    def __init__(self, cfg: ContextConfig) -> None:
        self.cfg = cfg

    def prepare(self, system: "SystemPrompt", messages: list[Message]) -> Prepared:
        system_blocks = build_system(system)
        prepared = copy.deepcopy(messages)
        prune_images(prepared, keep=self.cfg.keep_recent_images)
        prune_tool_payloads(prepared)
        place_breakpoints(
            prepared,
            limit=min(
                self.cfg.cache_message_breakpoints,
                MAX_BREAKPOINTS - len(system_blocks),
            ),
            stride=self.cfg.lookback_blocks,
        )

        betas: list[str] = []
        edits: list[Block] = []
        if self.cfg.clear_tool_uses:
            betas.append(CONTEXT_EDIT_BETA)
            edits.append({"type": "clear_tool_uses_20250919"})
        if self.cfg.compact:
            betas.append(COMPACT_BETA)
            edits.append({"type": "compact_20260112"})

        return Prepared(
            system=system_blocks,
            messages=prepared,
            betas=betas,
            context_management={"edits": edits} if edits else None,
        )


def drop_provider_fields(messages: list[Message]) -> list[Message]:
    """Strips provider-specific fields on the way to Anthropic.

    `tool_use` blocks carry OpenAI-compatible providers' own fields (like
    Gemini's `thought_signature`) — sending them back to that provider is
    MANDATORY, but Anthropic rejects fields it does not recognise. Since the
    same conversation can move between two providers (fallback model, model
    switch) this stripping is required.

    No needless copy: if no block carries such a field the list is returned
    as-is — which holds for the overwhelming majority of messages.
    """
    if not any(
        isinstance(b, dict) and "saglayici" in b
        for m in messages
        for b in (m.get("content") or [] if isinstance(m.get("content"), list) else [])
    ):
        return messages

    clean: list[Message] = []
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            clean.append(m)
            continue
        clean.append({
            **m,
            "content": [
                {k: v for k, v in b.items() if k != "saglayici"}
                if isinstance(b, dict) and "saglayici" in b else b
                for b in content
            ],
        })
    return clean


def build_system(system: "SystemPrompt") -> list[Block]:
    """Splits the system prompt into cached blocks.

    Two blocks, two breakpoints:

        [0] core     — byte-identical every session. The next session opened
                       in the same workspace reads this from the cache.
        [1] identity — the soul from the on-disk mind; changes between sessions.

    Because it is a prefix match, core stays valid when the soul changes.
    With a single block every new memory would drop the whole cache.

    Tools are rendered BEFORE the system, so the breakpoint at [0] covers
    them too. That is why you must never put anything that changes per turn
    here — clock, active window, session id — you would throw away
    everything after it.
    """
    blocks = [{"type": "text", "text": system.core, "cache_control": EPHEMERAL}]
    if system.identity:
        blocks.append({"type": "text", "text": system.identity, "cache_control": EPHEMERAL})
    return blocks


def place_breakpoints(messages: list[Message], *, limit: int, stride: int) -> None:
    """Places cache breakpoints into the message list (in place).

    Solves two things at once:

    1. **The 20-block lookback window.** Each breakpoint scans backwards at
       most 20 content blocks looking for the previous cache entry. In an
       agentic turn 15 tool calls mean 30 blocks — exceed the window and the
       cache silently misses and you pay full price. `stride` keeps this
       under 20.

    2. **Breakpoint drift.** If you only put the breakpoint at the end every
       turn, every request writes a new cache entry. The intermediate
       breakpoints are anchored to multiples of `stride` in the cumulative
       block count; so as the conversation grows they stay in place and
       read hits continue.
    """
    if limit <= 0 or not messages:
        return

    clear_breakpoints(messages)

    # The cumulative block index where each message ends.
    ends: list[int] = []
    total = 0
    for msg in messages:
        content = msg.get("content")
        total += len(content) if isinstance(content, list) else 1
        ends.append(total)

    targets: list[int] = []

    # The newest message always gets a breakpoint: this is the freshly written prefix.
    if _mark_last_block(messages[-1]):
        targets.append(len(messages) - 1)

    # Fixed breakpoints anchored backwards to multiples of stride.
    anchor = (total // stride) * stride
    while len(targets) < limit and anchor > 0:
        idx = _message_at(ends, anchor)
        if idx is not None and idx not in targets and _mark_last_block(messages[idx]):
            targets.append(idx)
        anchor -= stride


def clear_breakpoints(messages: list[Message]) -> None:
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict):
                block.pop("cache_control", None)


def _message_at(ends: list[int], block_index: int) -> int | None:
    for i, end in enumerate(ends):
        if end >= block_index:
            return i
    return None


def _mark_last_block(msg: Message) -> bool:
    """Puts cache_control on the message's last block. A message with text content cannot take one."""
    content = msg.get("content")
    if not isinstance(content, list) or not content:
        return False
    last = content[-1]
    if not isinstance(last, dict):
        return False
    last["cache_control"] = EPHEMERAL
    return True


def prune_images(messages: list[Message], *, keep: int) -> None:
    """Replaces every image except the newest `keep` with text.

    A screenshot is roughly 1.5k-4.8k tokens. In a thirty-step task, if you
    do not prune, the context fills halfway through. The last few images are
    enough for the model to answer "what did I just see".
    """
    if keep < 0:
        return

    holders = [
        (block, container)
        for msg in messages
        for block, container in _iter_image_blocks(msg)
    ]
    for block, container in holders[: max(0, len(holders) - keep)]:
        index = container.index(block)
        container[index] = {"type": "text", "text": IMAGE_PLACEHOLDER}


def prune_tool_payloads(
    messages: list[Message],
    *,
    cap: int = TRIM_TOOL_CHARS,
    keep: int = TRIM_KEEP_MESSAGES,
) -> None:
    """Trims old tool payloads: giant arguments and bloated results.

    The last `keep` messages are UNTOUCHED — the model may refer to content
    it just saw. Older than that: texts exceeding `cap` in tool_use inputs
    and tool_result contents are trimmed keeping head+tail. Browser / fetch /
    file dumps get a tighter keep+cap.
    """
    if cap <= 0:
        return

    def shorten(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        head = limit * 2 // 3
        tail = limit // 3
        note = TRIM_NOTE.format(gone=len(text) - head - tail)
        return text[:head] + note + text[-tail:]

    # The general window first.
    _prune_range(messages, end_keep=keep, cap=cap, shorten=shorten)
    # Heavy tools: shorter tail + lower ceiling.
    _prune_range(
        messages,
        end_keep=TRIM_BROWSER_KEEP,
        cap=TRIM_BROWSER_CHARS,
        shorten=shorten,
        only_heavy=True,
    )


def _prune_range(
    messages: list[Message],
    *,
    end_keep: int,
    cap: int,
    shorten,
    only_heavy: bool = False,
) -> None:
    for msg in messages[: max(0, len(messages) - end_keep)]:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = str(block.get("name") or "")
                if only_heavy and name not in _HEAVY_TOOLS:
                    continue
                arguments = block.get("input")
                if isinstance(arguments, dict):
                    for key, value in arguments.items():
                        if isinstance(value, str) and len(value) > cap:
                            arguments[key] = shorten(value, cap)
            elif block.get("type") == "tool_result":
                if only_heavy and not _result_looks_heavy(block):
                    continue
                inner = block.get("content")
                if isinstance(inner, str) and len(inner) > cap:
                    block["content"] = shorten(inner, cap)
                elif isinstance(inner, list):
                    for sub in inner:
                        if (isinstance(sub, dict) and sub.get("type") == "text"
                                and isinstance(sub.get("text"), str)
                                and len(sub["text"]) > cap):
                            sub["text"] = shorten(sub["text"], cap)


def _result_looks_heavy(block: dict[str, Any]) -> bool:
    """A tool_result has no name; count it as a browser dump by HTML/DOM/URL hints."""
    inner = block.get("content")
    text = inner if isinstance(inner, str) else ""
    if isinstance(inner, list):
        parts = []
        for sub in inner:
            if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                parts.append(sub["text"])
        text = "\n".join(parts)
    # Very large dumps always count as heavy.
    if len(text) > TRIM_TOOL_CHARS:
        return True
    head = text[:400].lower()
    return any(k in head for k in (
        "<html", "<!doctype", "http://", "https://", "konsol",
        "başarısız istek", "dom", "screenshot", "ekran",
    ))


def _iter_image_blocks(msg: Message):
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image":
            yield block, content
        elif block.get("type") == "tool_result":
            inner = block.get("content")
            if isinstance(inner, list):
                for sub in inner:
                    if isinstance(sub, dict) and sub.get("type") == "image":
                        yield sub, inner


def cache_report(usage: Any) -> dict[str, int]:
    """Extracts cache health from the usage object.

    If read stays at 0 constantly there is a silent breaker: a changing
    value in the system prompt, a tool list that changes mid-session, or a
    lookback gap exceeding 20 blocks.
    """
    get = (lambda k: getattr(usage, k, 0) or 0) if usage is not None else (lambda k: 0)
    read = get("cache_read_input_tokens")
    write = get("cache_creation_input_tokens")
    fresh = get("input_tokens")
    return {
        "cache_read": read,
        "cache_write": write,
        "uncached": fresh,
        "output": get("output_tokens"),
        # The real prompt size is the sum of the three; input_tokens is only the residue.
        "prompt_total": read + write + fresh,
    }
