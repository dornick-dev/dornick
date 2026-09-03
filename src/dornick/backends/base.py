"""Provider-independent model interface.

The rest of the harness does not know which model is speaking. The
Backend's job is to return the result in **Anthropic block format**, no
matter which API it talks to:

    {"type": "text", "text": ...}
    {"type": "tool_use", "id": ..., "name": ..., "input": {...}}

The reason for choosing this format as the common denominator is that the
session log has a single shape. The mind must be able to read past
sessions independently of the model — so that a job you discussed with
Opus today can be continued with a local model tomorrow.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Protocol, runtime_checkable

from ..context import Prepared
from ..session import blocks_to_dicts

TextSink = Callable[[str], None]


class Interrupted(Exception):
    """The user cut the stream — this is a decision, not an error.

    Backends catch this and return `TurnResult(interrupted=True)`; it must
    not fall into the generic error path (if it counts as an error,
    auto-mode writes a blacklist score for the model, and the UI shows it
    as "error").
    """


class Stalled(Exception):
    """The stream sank into silence: not a single chunk arrived during the window.

    Measured wound (29.08, z1): an 8-call turn hung against the 900 s GATE
    ceiling — a single provider call stayed open for minutes streaming
    nothing, and the timeout only broke at the turn's ceiling. The right
    place to cut is the CALL, not the turn: a long call that streams
    chunks is healthy (writing a big file), a call that stays SILENT for
    the whole window is hung.
    """


async def cancellable(stream: Any, cancel: Any,
                      *, stall_s: float | None = None) -> AsyncIterator[Any]:
    """Iterates the stream while ALSO listening to the cancel flag.

    `async for` only yields control when a chunk ARRIVES. Before the first
    token — request built, server processing the prompt — there are no
    chunks and the cancel flag was never polled. On the FIRST uncached
    turn, prompt processing can take minutes: the user pressed Stop and
    nothing happened (the root of the "stop doesn't work on the first
    conversation" wound). On later turns the cache sped up the first
    token, hiding the bug.

    Here every step is raced against the cancel wait: whichever comes
    first wins. When cancelled, `Interrupted` is raised; closing the
    stream remains the caller's responsibility (openai: _aclose,
    anthropic: context manager).

    `stall_s`: silence window between chunks. If the window fills,
    `Stalled` is raised — a hung provider call burns its own window, not
    the turn's ceiling. None is the old behaviour (no window).
    """
    iterator = stream.__aiter__()
    stop = asyncio.ensure_future(cancel.wait())
    try:
        while True:
            if stop.done():
                raise Interrupted
            step = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({step, stop}, timeout=stall_s,
                                         return_when=asyncio.FIRST_COMPLETED)
            if not done:
                # Window filled: no chunk, no cancel. The call is hung.
                step.cancel()
                with contextlib.suppress(BaseException):
                    await step
                raise Stalled(f"akış {stall_s:.0f} sn sessiz kaldı")
            if step not in done:
                # Cancel won: abort the half-finished read step.
                step.cancel()
                with contextlib.suppress(BaseException):
                    await step
                raise Interrupted
            try:
                chunk = step.result()
            except StopAsyncIteration:
                return
            yield chunk
    finally:
        stop.cancel()
        with contextlib.suppress(BaseException):
            await stop


@dataclass(slots=True)
class TurnResult:
    """The result of one model turn.

    If interrupted=True, message is None and the half-finished content was
    deliberately discarded: a partially received tool_use block has
    incomplete input JSON, and writing it into the history breaks the
    next request.
    """

    message: Any | None = None
    interrupted: bool = False
    error: str | None = None
    partial_text: str = ""

    @property
    def stop_reason(self) -> str | None:
        return getattr(self.message, "stop_reason", None)

    @property
    def content(self) -> list[dict[str, Any]]:
        """Returns the content blocks uniformly as dicts.

        Closing the gap between SDK objects and dicts once here keeps the
        loop and the session from having to consider both everywhere.
        No field is dropped, thinking blocks included — the API rejects
        modified blocks.
        """
        return blocks_to_dicts(getattr(self.message, "content", None) or [])

    @property
    def usage(self) -> Any:
        return getattr(self.message, "usage", None)

    def tool_uses(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]


@dataclass(slots=True)
class Callbacks:
    on_text: TextSink = lambda _: None
    on_thinking: TextSink = lambda _: None
    on_tool_start: Callable[[str], None] = lambda _: None
    on_turn_start: Callable[[], None] = lambda: None


@runtime_checkable
class Backend(Protocol):
    """The contract every provider must satisfy."""

    async def turn(
        self,
        prepared: Prepared,
        tools: list[dict[str, Any]],
        *,
        cancel: Any,
        callbacks: Callbacks | None = None,
    ) -> TurnResult: ...

    async def count_tokens(self, prepared: Prepared, tools: list[dict[str, Any]]) -> int: ...

    async def close(self) -> None: ...


@dataclass(slots=True)
class SimpleMessage:
    """Carrier standing in for the Anthropic response object.

    Local providers answer in their own formats; the backend converts them
    to this shape and the harness sees no difference.
    """

    content: list[dict[str, Any]]
    stop_reason: str
    usage: Any = None
    stop_details: Any = None


@dataclass(slots=True)
class SimpleUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
