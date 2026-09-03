"""OpenAI-compatible backend: LM Studio, Ollama, vLLM, llama.cpp, OpenRouter.

These servers all speak the same `/v1/chat/completions` contract, so one
backend is enough. The differences are in capability, not format: small
models may produce tool arguments as broken JSON, some accept no images,
most have no cache. All of that is absorbed here or in `translate.py`;
the loop sees no difference.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from .. import automode
from ..config import ModelConfig
from ..context import Prepared
from .base import (Callbacks, Interrupted, SimpleMessage, SimpleUsage,
                   Stalled, TurnResult, cancellable)
from .translate import (
    extract_inline_calls,
    map_finish_reason,
    to_anthropic_blocks,
    to_openai_messages,
    to_openai_tools,
)

INSTALL_HINT = (
    "OpenAI-uyumlu sağlayıcı için openai paketi gerekli: pip install 'dornick[local]'"
)


def _hint() -> str:
    """The openai package ships with the install; its absence on an installed copy needs repair."""
    from .. import environment

    if environment.is_installed():
        return ("openai paketi bu kurulumda eksik görünüyor. Kurulum "
                "sihirbazını yeniden çalıştırmak eksiği onarır.")
    return INSTALL_HINT

# Local servers don't validate the key but the client rejects an empty string.
PLACEHOLDER_KEY = "local"

# Output ceiling of the discovery drop. 4096 tokens ≈ 300+ lines of code:
# in this task class almost all single-file writes fit; a turn that does
# not fit is repeated once with the full budget (below, inside turn).
DISCOVERY_CAP = 4096

# Per-call silence window (hosted endpoints): if not a single chunk arrives
# during the window the call counts as hung and is retried once. Measured
# wound (29.08, z1): a single provider call went silent for minutes and the
# turn only broke at the 900 s gate ceiling. 120 s is a generous
# first-token allowance: even on a huge uncached prompt a hosted endpoint
# either streams within that time or never. Local endpoints get NO window —
# LM Studio on a CPU can legitimately spend minutes on the first token; an
# impatient cut there would be a bug, not a feature.
CALL_SILENCE_S = 120.0


def _silence_window(base_url: str | None) -> float | None:
    from urllib.parse import urlparse
    host = (urlparse(str(base_url or "")).hostname or "").casefold()
    if (host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
            or host.startswith("192.168.") or host.startswith("10.")
            or host.endswith(".local")):
        return None
    return CALL_SILENCE_S

# Read-only tools: tools whose result does not change the world, typically
# followed by either another read or a short write. The list is
# deliberately narrow — adding a wrong member (e.g. shell) would cut the
# effort of writing turns. It is not tied to the `mutates` flag in the
# tool layer because only the tools' API schema reaches the backend; the
# names are stable in the product.
_READ_ONLY = frozenset({"read_file", "read_many", "list_dir", "denetle"})


def _discovery_turn(messages: list[dict[str, Any]]) -> bool:
    """Did the last exchange carry only read-only tool results?

    Walk backwards from the end: if the tail is `tool` results, look at
    the tool names of the assistant turn that called them. If the tail has
    user/system messages (a fresh user message, a memory note) it does not
    count as discovery — the effort of the first call and of turns that
    return to the user is left untouched.
    """
    saw_tool = False
    for m in reversed(messages):
        role = m.get("role")
        if role == "tool":
            saw_tool = True
            continue
        if role == "assistant" and saw_tool:
            names = [((c.get("function") or {}).get("name") or "")
                     for c in (m.get("tool_calls") or [])]
            return bool(names) and all(name in _READ_ONLY for name in names)
        return False
    return False


class OpenAIBackend:
    name = "openai"

    def __init__(self, model: ModelConfig, client: Any | None = None) -> None:
        self.model = model
        self._client = client or _make_client(model)
        # Gate for how many requests go to the server at once. On local
        # servers this is 1: when a second request hits a busy model, LM
        # Studio loads a second copy of the model and memory doubles. The
        # gate lives here, not in the loop — subagents share the same client.
        self._gate = asyncio.Semaphore(max(1, model.max_calls))
        # If the server does not recognise the `reasoning` field we learn
        # it once and never send it again. Taking a 400 and retrying on
        # every request would add a round-trip of latency to every answer.
        self._no_reasoning = model.can_think is False
        # If the model accepts no images the same one-time learning applies:
        # after switching to a text-only model the frames from the history
        # stay in the request and the server returns 404. After the first
        # error the frames are stripped and never sent again. If the
        # catalog says False, strip from the start.
        self._no_vision = model.vision is False
        # Prompt-cache marks only on OpenRouter: an ephemeral point on the
        # first system + last two messages (OpenCode's measured pattern —
        # same model, same job: 77% hit rate, ~6.7x cost difference). Not
        # sent to other endpoints; even on OpenRouter a rejecting endpoint
        # is learned once and the marks are turned off.
        self._cache_marked = "openrouter" in str(model.base_url or "").lower()
        self._cache_off = False
        # Auto mode: if the address is OpenRouter and the name is "oto",
        # requests are drawn from the free pool (see automode). Other
        # provider/model requests are NOT touched. The health ledger is
        # in-memory: a model erroring back-to-back is pushed to the end of
        # the pool for a while.
        self._auto = automode.is_auto(model)
        self._health = automode.Health()
        # Which endpoint we selected last in auto mode. A content defect
        # (schema violation, fake tool call) is discovered in the loop
        # AFTER the turn ends; the selection is kept here so the penalty
        # can be written to the right model.
        self._last_selected = ""
        # Raw finish_reason of the last stream. `_stream` still stamps a
        # truncated tool call as "tool_use" (the call's presence decides);
        # the raw value is kept here to catch a turn that hit the
        # discovery cap.
        self._last_finish: str | None = None

    async def close(self) -> None:
        await self._client.close()

    async def turn(
        self,
        prepared: Prepared,
        tools: list[dict[str, Any]],
        *,
        cancel: Any,
        callbacks: Callbacks | None = None,
    ) -> TurnResult:
        callbacks = callbacks or Callbacks()
        callbacks.on_turn_start()

        messages = to_openai_messages(prepared.system, prepared.messages)
        # If we learned the model accepts no images, strip the frames from
        # the start: learned on the first turn, later turns should not eat
        # a pointless 404.
        if self._no_vision:
            _strip_images(messages)
        if self._cache_marked and not self._cache_off:
            _mark_cache(messages)

        kwargs: dict[str, Any] = {
            "model": self.model.name,
            "messages": messages,
            "max_tokens": self.model.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
        if self.model.temperature is not None:
            kwargs["temperature"] = self.model.temperature

        extra: dict[str, Any] = {}

        if self.model.keep_loaded > 0:
            # Servers understand this under different names: LM Studio
            # `ttl`, Ollama `keep_alive`. Both are sent; each ignores the
            # field it does not know. Without it the model drops out of
            # memory after every request and the next answer waits tens of
            # seconds for a reload.
            extra["ttl"] = self.model.keep_loaded
            extra["keep_alive"] = self.model.keep_loaded

        # Discovery drop (B5): in the small family, if the last exchange
        # brought ONLY read-only tool results, this call is most likely the
        # next read or a short write — 89% of wall time was measured to be
        # model latency (29.08 sweep) and the lion's share of that latency
        # is reasoning. On such turns effort drops to low and the output
        # ceiling to DISCOVERY_CAP; a turn that hits the ceiling
        # (finish=length) is repeated ONCE with the full budget — quality
        # is not sacrificed to the cap, only latency is trimmed.
        # Coding turn: on flash the high→medium cap is lifted (write quality).
        discovery = False
        encoding = False
        if tools and not self._auto:
            from ..prompt import coding_turn, small_family
            if small_family(kwargs["model"]):
                if _discovery_turn(messages):
                    discovery = True
                    kwargs["max_tokens"] = min(self.model.max_tokens, DISCOVERY_CAP)
                elif coding_turn(messages):
                    encoding = True

        if (reasoning := self._reasoning(discovery=discovery, encoding=encoding)) is not None and not self._no_reasoning:
            extra["reasoning"] = reasoning

        # Auto mode: the model is picked from the head of the free pool,
        # the next few are written into OpenRouter's native fallback chain
        # (`models`). `provider.data_collection=deny`: some free endpoints
        # may use the data for training; route to a refusing endpoint.
        selected = ""
        if self._auto:
            selected, auto_extra = await asyncio.to_thread(self._prepare_auto)
            if not selected:
                return TurnResult(
                    error=(
                        "Oto havuzu kurulamadı: OpenRouter model listesine "
                        "ulaşılamadı ve önbellek boş. Ağı kontrol et ya da "
                        "Ayarlar › Model'den belirli bir model seç."
                    )
                )
            kwargs["model"] = selected
            self._last_selected = selected
            extra.update(auto_extra)

        if extra:
            kwargs["extra_body"] = extra

        # The cancel flag is polled while waiting on the gate: when the
        # call holding the gate ran long (single channel is the default)
        # the queued turn stayed deaf to Stop.
        if cancel.is_set():
            return TurnResult(interrupted=True, partial_text="")
        async with self._gate:
            if cancel.is_set():
                return TurnResult(interrupted=True, partial_text="")
            try:
                try:
                    result = await self._stream(kwargs, cancel, callbacks)
                except Stalled:
                    # Hung provider call: retry once on a fresh connection
                    # before eating the turn ceiling. If the second one is
                    # silent too, it is an error — in auto mode it lands in
                    # the health ledger and the model moves down the queue.
                    try:
                        result = await self._stream(kwargs, cancel, callbacks)
                    except Stalled as exc:
                        result = TurnResult(error=(
                            f"{kwargs['model']} yanıt akıtmadı: {exc} "
                            "(iki deneme). Sağlayıcı asılı görünüyor."))
                if self._last_finish == "length" and (
                    discovery
                    or result.error
                    or not (result.partial_text or "").strip()
                ):
                    # The output ceiling filled and there is no usable
                    # content (or the discovery cap truncated). finish=length
                    # ≠ context full: most of the time reasoning ate
                    # max_tokens. Trying the same request 5 times is
                    # pointless; once with full budget + low effort.
                    kwargs["max_tokens"] = self.model.max_tokens
                    body = dict(kwargs.get("extra_body") or {})
                    if (soft := self._reasoning(discovery=True)) is not None and not self._no_reasoning:
                        body["reasoning"] = soft
                    elif not self._no_reasoning:
                        body.pop("reasoning", None)
                    if body:
                        kwargs["extra_body"] = body
                    elif "extra_body" in kwargs and not body:
                        kwargs.pop("extra_body", None)
                    result = await self._stream(kwargs, cancel, callbacks)
            except Exception:
                # The request never got built (e.g. connection refused):
                # this too is written as an error against that model.
                if self._auto and selected:
                    self._health.save(selected, False)
                raise

        # Timeout, empty response and error weigh the same: the call
        # failed. A cancel is the user's decision, not the model's fault —
        # it does not count.
        if self._auto and selected and not result.interrupted:
            self._health.save(selected, ok=not result.error)
        return result

    def kusurlu(self, reason: str = "") -> None:
        """Content defect: the turn technically succeeded but was wasted.

        The loop calls this (see `Agent._kusurlu`): a tool call that
        violates the schema, or call XML written as plain text instead of
        a real call. In the free pool these are as real as errors: an
        endpoint that cannot call tools does not advance the work, it only
        burns turns. It is written to the health ledger as a failure; a
        model crossing the threshold is pushed to the end of the pool and
        weeds itself out.

        Outside auto mode there is no equivalent: the user picked the
        model themselves; ranking it behind their back is not our place.
        """
        if self._auto and self._last_selected:
            self._health.save(self._last_selected, False)

    def _prepare_auto(self) -> tuple[str, dict[str, Any]]:
        """Auto mode's request pieces: the selected model + extra body fields.

        The pool is ordered by health: penalised models go last. The last
        selection is noted in the cache file for diagnosis — the answer to
        "which model did I talk to" lives there.
        """
        pool = self._health.rank(automode.pool())
        if not pool:
            return "", {}
        extra: dict[str, Any] = {
            "provider": {"data_collection": "deny", "require_parameters": True},
        }
        if fallbacks := pool[1:4]:
            extra["models"] = fallbacks
        automode.write_last(pool[0])
        return pool[0], extra

    def _heal(self, kwargs: dict[str, Any], exc: Exception) -> bool:
        """Heals a known rejection once; True if it healed something.

        Each kind once, so the same error is not retried forever: the
        `reasoning` field or images. If nothing is left to heal it returns
        False and the caller raises the error.
        """
        if not self._no_reasoning and _rejects_reasoning(exc):
            self._no_reasoning = True
            body = kwargs.get("extra_body") or {}
            body.pop("reasoning", None)
            if body:
                kwargs["extra_body"] = body
            else:
                kwargs.pop("extra_body", None)
            return True

        if not self._no_vision and _rejects_image(exc):
            self._no_vision = True
            _strip_images(kwargs["messages"])
            return True

        # Endpoint that does not recognise the cache mark: strip the mark
        # and never send it again.
        if (self._cache_marked and not self._cache_off
                and "cache_control" in str(exc).lower()):
            self._cache_off = True
            _unmark_cache(kwargs["messages"])
            return True

        return False

    def _reasoning(self, discovery: bool = False, encoding: bool = False) -> dict[str, Any] | None:
        """The thinking setting in the form sent to the server.

        Until now this field only applied on the Claude side; thinking
        models like qwen3 reasoned by their own choice and the "effort"
        value on the settings page did nothing.

        I measured the difference (qwen3-27b, OpenRouter, a one-word prompt
        like "üyan."):

            current state    first chunk 2.53 s   total 8.97 s
            reasoning low    first chunk 0.87 s   total 1.60 s
            reasoning off    first chunk 0.94 s   total 1.12 s

        Reasoning for nine seconds to say hello takes the assistant out of
        real time. `low` is both fast and keeps the personality; turning
        it off entirely drops the model into generic boilerplate
        ("Size nasıl yardımcı olabilirim?").
        """
        if self.model.can_think is False:
            return None
        if not self.model.thinking:
            return {"enabled": False}
        # OpenRouter accepts "low/medium/high"; xhigh/max have no equivalent.
        effort = {"xhigh": "high", "max": "high"}.get(self.model.effort, self.model.effort)
        # In the small/fast family the chat ceiling is medium (28.08: high
        # on every turn → 900 s). On a coding turn the ceiling is lifted —
        # high stays available for writing.
        if effort == "high":
            from ..prompt import small_family
            if small_family(self.model.name) and not encoding:
                effort = "medium"
        # Discovery turn: medium/high-effort reasoning on the call that
        # follows a read IS the latency (B5 measurement). A turn that hits
        # the cap is repeated at full effort anyway. Discovery outranks the
        # coding flag.
        if discovery and effort in ("medium", "high"):
            effort = "low"
        return {"effort": effort} if effort in ("low", "medium", "high") else None

    async def _stream(self, kwargs: dict[str, Any], cancel: Any, callbacks: Callbacks) -> TurnResult:
        text: list[str] = []
        reasoning: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish: str | None = None
        self._last_finish = None
        usage = SimpleUsage()
        stream = None

        # Two kinds of rejection are learned once and healed: an
        # unrecognised `reasoning` field and a model that accepts no
        # images. Both can be needed at once (text-only server without
        # reasoning), so the attempts sit in a loop: heal one thing per
        # error, try again.
        stream = None
        for _ in range(3):
            # The cancel flag is polled here too: request SETUP (the SDK
            # internally retries 2 more times) can take minutes, and Stop
            # was only handled once the stream started.
            if cancel.is_set():
                return TurnResult(interrupted=True, partial_text="")
            try:
                stream = await self._client.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                if not self._heal(kwargs, exc):
                    raise
        if stream is None:  # pragma: no cover - the loop always breaks or raises
            raise RuntimeError("istek kurulamadı")

        try:
            # `cancellable`: the cancel flag is polled not only when a chunk
            # arrives but also while WAITING for one. During the long prompt
            # processing before the first token (uncached first turn) Stop
            # did not work — this was the root.
            async for chunk in cancellable(
                    stream, cancel,
                    stall_s=_silence_window(self.model.base_url)):
                if raw_usage := getattr(chunk, "usage", None):
                    usage = _usage(raw_usage)

                if not getattr(chunk, "choices", None):
                    continue

                choice = chunk.choices[0]
                finish = getattr(choice, "finish_reason", None) or finish
                _consume(getattr(choice, "delta", None), callbacks, text, reasoning, calls)

        except Interrupted:
            return TurnResult(interrupted=True, partial_text="".join(text))
        except Stalled:
            # A hung call bubbles to the caller: turn() retries once, and
            # if the second one is silent too the error goes into TurnResult.
            raise
        except Exception as exc:  # the openai package is optional; can't bind to the type
            return TurnResult(error=_explain(exc, self.model), partial_text="".join(text))
        finally:
            # The stream must be closed whether consumed or cut. If not,
            # the underlying httpx connection gets collected at interpreter
            # shutdown and raises "generator didn't stop after athrow()".
            await _aclose(stream)

        self._last_finish = finish
        joined = "".join(text)
        gathered = [calls[i] for i in sorted(calls)]

        # Some local models produce the tool call not in the tool_calls
        # field but as XML inside plain text. If it is not parsed the call
        # never runs and the raw tags look like an answer to the user.
        joined, inline = extract_inline_calls(joined)
        if inline:
            for index, call in enumerate(inline):
                gathered.append({
                    "id": f"inline_{index}",
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                })

        blocks = to_anthropic_blocks(joined, gathered)

        if not blocks:
            # Thinking models sometimes finish a turn only in the reasoning
            # channel: they plan, say "now I should do this" and stop.
            #
            # Presenting that as an answer was wrong — the user mistook the
            # reasoning for the answer and the work stalled halfway.
            # Reasoning is not an answer; it enters the history as an
            # assistant turn (so the model can see its own plan) but is
            # marked with `empty_turn`, and the loop keeps going.
            if thought := "".join(reasoning).strip():
                return TurnResult(
                    message=SimpleMessage(
                        content=[{"type": "text", "text": thought}],
                        stop_reason="empty_turn",
                        usage=usage,
                    ),
                    partial_text="",
                )
            if finish == "length":
                # The output budget (max_tokens) filled; no content. This
                # is not the context window — reasoning often eats the
                # whole output allowance. api_error + 5 retries gives the
                # same result; with empty_turn the loop asks for a short
                # answer / tool call.
                return TurnResult(
                    message=SimpleMessage(
                        content=[{
                            "type": "text",
                            "text": (
                                "Çıktı bütçesi doldu; görünür cevap veya "
                                "araç çağrısı üretemedim."
                            ),
                        }],
                        stop_reason="empty_turn",
                        usage=usage,
                    ),
                    partial_text="",
                )
            return TurnResult(
                error=(
                    f"{self.model.name} boş yanıt döndürdü "
                    f"(finish_reason={finish!r}). Sağlayıcı içerik "
                    "göndermedi; modeli değiştirmek veya yeniden denemek gerekebilir."
                )
            )

        # If the server omits finish_reason, the presence of a tool call
        # decides; otherwise the loop mistakes a tool_use turn for end_turn
        # and stops early.
        stop_reason = "tool_use" if gathered else map_finish_reason(finish)

        return TurnResult(
            message=SimpleMessage(content=blocks, stop_reason=stop_reason, usage=usage),
            partial_text="".join(text),
        )

    async def count_tokens(self, prepared: Prepared, tools: list[dict[str, Any]]) -> int:
        """Rough estimate.

        Compatible servers have no token-counting endpoint. The chars/4
        approximation is enough for reporting; do not base cost
        calculations on it.
        """
        payload = to_openai_messages(prepared.system, prepared.messages)
        chars = sum(len(str(m.get("content") or "")) for m in payload)
        chars += sum(len(str(t)) for t in to_openai_tools(tools))
        return chars // 4


# ---------------------------------------------------------------------


def _make_client(model: ModelConfig) -> Any:
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover - install path
        raise RuntimeError(_hint()) from exc

    key = os.getenv(model.api_key_env or "OPENAI_API_KEY") or PLACEHOLDER_KEY
    kwargs: dict[str, Any] = {"api_key": key}
    if model.base_url:
        kwargs["base_url"] = model.base_url

    # Timeout and retries. The default SDK timeout is far too long, and
    # when the STREAM went idle (the provider stopped responding) the
    # system sat stuck on "thinking" for minutes — the user waited until
    # an "upstream idle timeout" error arrived. `read` = maximum gap
    # between two consecutive bytes: a healthy stream sends tokens at
    # sub-second intervals; if the gap is exceeded the request fails fast
    # and the turn ends cleanly (no deadlock). Kept generous because a
    # local model can be a bit slow to the first token.
    # `max_retries` swallows transient provider errors (429, short idle).
    try:
        import httpx

        kwargs["timeout"] = httpx.Timeout(90.0, connect=15.0)
    except Exception:
        kwargs["timeout"] = 90.0
    kwargs["max_retries"] = 2

    return AsyncOpenAI(**kwargs)


def _consume(
    delta: Any,
    callbacks: Callbacks,
    text: list[str],
    reasoning: list[str],
    calls: dict[int, dict[str, str]],
) -> None:
    if delta is None:
        return

    if chunk := getattr(delta, "content", None):
        text.append(chunk)
        callbacks.on_text(chunk)

    # Qwen3, DeepSeek-R1 and derivatives stream thinking in a separate
    # field. The field name varies from server to server; the SDK puts
    # unrecognised fields into model_extra.
    if chunk := _reasoning_of(delta):
        reasoning.append(chunk)
        callbacks.on_thinking(chunk)

    for fragment in getattr(delta, "tool_calls", None) or []:
        slot = calls.setdefault(
            getattr(fragment, "index", 0),
            {"id": "", "name": "", "arguments": "", "extra": {}},
        )
        if identifier := getattr(fragment, "id", None):
            slot["id"] = identifier

        # Provider-specific fields: carried WITHOUT recognising them.
        # Gemini attaches a `thought_signature` to every tool call in
        # thinking models and REQUIRES you to send it back on the NEXT
        # turn; if you don't, it returns 400 ("missing a thought_signature
        # in functionCall parts"). Instead of hard-coding the field's name
        # and place per provider, we keep everything we don't know as-is —
        # so the next provider that adds such a field doesn't break us either.
        _collect_extra(slot["extra"], fragment)

        function = getattr(fragment, "function", None)
        if function is None:
            continue
        _collect_extra(slot["extra"], function)

        if name := getattr(function, "name", None):
            # Most servers send the name in one piece, some split it. We
            # do a suffix check so the same piece is not appended twice.
            if not slot["name"]:
                slot["name"] = name
                callbacks.on_tool_start(name)
            elif not slot["name"].endswith(name):
                slot["name"] += name

        if arguments := getattr(function, "arguments", None):
            slot["arguments"] += arguments


# Fields the SDK does not model sit in `model_extra` (pydantic). We take
# whatever the tool call has from there: we don't enumerate them one by
# one, so a field whose name we don't know can be carried too.
_EXTRA_SKIP = frozenset({"index", "id", "type", "name", "arguments", "function"})


def _collect_extra(box: dict[str, Any], obj: Any) -> None:
    """Accumulates unrecognised provider fields into the box (silent, best effort)."""
    try:
        extras = getattr(obj, "model_extra", None) or {}
    except Exception:
        return
    for key, value in extras.items():
        if key in _EXTRA_SKIP or value is None:
            continue
        # The stream arrives piece by piece; text fields are appended, for
        # the rest the last one wins (the signature arrives in one piece).
        if isinstance(value, str) and isinstance(box.get(key), str):
            if not box[key].endswith(value):
                box[key] += value
        else:
            box[key] = value


# A server's rejection of a field it does not know. The text varies from
# server to server, so we look at words, not codes: they all name the field.
_REJECTED = ("reasoning", "unknown field", "unrecognized", "extra_body",
             "unexpected keyword", "additionalproperties")


def _rejects_reasoning(exc: Exception) -> bool:
    text = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status is not None and status not in (400, 404, 422):
        return False
    return "reasoning" in text or any(mark in text for mark in _REJECTED)


def _rejects_image(exc: Exception) -> bool:
    """Does the model refuse image input?

    After switching to a text-only model the camera/screen frames from the
    history are still in the request and the server rejects it.
    OpenRouter's text: 'No endpoints found that support image input'. It
    varies per server, so we look at words, not codes: they all mention
    images.
    """
    text = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status is not None and status not in (400, 404, 415, 422):
        return False
    return "image" in text and (
        "support" in text or "endpoint" in text or "multimodal" in text
        or "not accept" in text or "vision" in text
    )


# The trace left where an image was stripped. The model cannot see it, but
# knowing an image was there helps with references like "the one I just showed".
_IMAGE_PLACEHOLDER = "[görüntü — bu model göremiyor]"


def _mark_cache(messages: list[dict[str, Any]]) -> None:
    """OpenRouter prompt cache: ephemeral on the first system + last two messages.

    The mark lives on a content PART; plain-text content is wrapped in a
    single part. Three points at most — safely under the Anthropic
    family's four-point limit, and on other models OpenRouter either uses
    the mark or ignores it.
    """
    mark = {"type": "ephemeral"}
    candidates = [m for m in messages if m.get("role") == "system"][:1]
    candidates += [m for m in messages if m.get("role") != "system"][-2:]
    seen: set[int] = set()
    for m in candidates:
        if id(m) in seen:
            continue
        seen.add(id(m))
        content = m.get("content")
        if isinstance(content, str):
            m["content"] = [{"type": "text", "text": content,
                             "cache_control": dict(mark)}]
        elif isinstance(content, list) and content:
            last = content[-1]
            if isinstance(last, dict):
                last["cache_control"] = dict(mark)


def _unmark_cache(messages: list[dict[str, Any]]) -> None:
    """Reverts the marks (the endpoint refused them): dropped from the parts."""
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    part.pop("cache_control", None)


def _strip_images(messages: list[dict[str, Any]]) -> None:
    """Turns the image parts in OpenAI-format messages into text (in place).

    No re-translation needed: the `image_url` parts inside an
    already-translated message are converted into a text trace. If the
    part list consists only of images, the message drops to plain text.
    """
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        cleaned: list[dict[str, Any]] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                cleaned.append({"type": "text", "text": _IMAGE_PLACEHOLDER})
            else:
                cleaned.append(part)
        # If there is a single part and it is text, drop to a plain string:
        # some servers are fussy about a one-element content array.
        if len(cleaned) == 1 and cleaned[0].get("type") == "text":
            msg["content"] = cleaned[0]["text"]
        else:
            msg["content"] = cleaned


def _reasoning_of(delta: Any) -> str | None:
    """Finds the thinking text.

    The field name varies from server to server and is absent from the
    OpenAI schema; the SDK puts unrecognised fields into model_extra, so
    that has to be checked too.
    """
    for name in ("reasoning_content", "reasoning"):
        if value := getattr(delta, name, None):
            return str(value)
    extra = getattr(delta, "model_extra", None) or {}
    for name in ("reasoning_content", "reasoning"):
        if value := extra.get(name):
            return str(value)
    return None


def _usage(raw: Any) -> SimpleUsage:
    """OpenAI/OpenRouter usage → SimpleUsage (cache fields included).

    `prompt_tokens` is usually the cache + fresh total. If
    `prompt_tokens_details.cached_tokens` exists it is written to
    cache_read; input_tokens keeps the fresh part so
    `cache_report.prompt_total` does not double-count.
    """
    if isinstance(raw, dict):
        prompt = int(raw.get("prompt_tokens") or 0)
        output = int(raw.get("completion_tokens") or 0)
        nested = raw.get("prompt_tokens_details") or {}
        cached = int(nested.get("cached_tokens") or 0) if isinstance(nested, dict) else 0
        created = int(nested.get("cache_creation_tokens") or 0) if isinstance(nested, dict) else 0
    else:
        prompt = int(getattr(raw, "prompt_tokens", 0) or 0)
        output = int(getattr(raw, "completion_tokens", 0) or 0)
        cached = 0
        created = 0
        details = getattr(raw, "prompt_tokens_details", None)
        if isinstance(details, dict):
            cached = int(details.get("cached_tokens") or 0)
            created = int(details.get("cache_creation_tokens") or 0)
        elif details is not None:
            cached = int(getattr(details, "cached_tokens", 0) or 0)
            created = int(getattr(details, "cache_creation_tokens", 0) or 0)
        elif isinstance(getattr(raw, "model_extra", None), dict):
            nested = raw.model_extra.get("prompt_tokens_details") or {}
            if isinstance(nested, dict):
                cached = int(nested.get("cached_tokens") or 0)
                created = int(nested.get("cache_creation_tokens") or 0)

    fresh = max(0, prompt - cached - created) if (cached or created) else prompt
    return SimpleUsage(
        input_tokens=fresh,
        output_tokens=output,
        cache_read_input_tokens=cached,
        cache_creation_input_tokens=created,
    )


async def _aclose(stream: Any) -> None:
    if stream is None:
        return
    for name in ("close", "aclose"):
        closer = getattr(stream, name, None)
        if closer is None:
            continue
        try:
            result = closer()
            if hasattr(result, "__await__"):
                await result
        except Exception:  # a close error must not squash the turn
            pass
        return


def _explain(exc: Exception, model: ModelConfig) -> str:
    status = getattr(exc, "status_code", None)
    text = str(getattr(exc, "message", "") or exc)
    where = model.base_url or "OpenAI"

    if isinstance(exc, (ConnectionError, OSError)) or "Connection" in type(exc).__name__:
        return (
            f"{where} adresine bağlanılamadı. Sunucu açık mı? "
            "LM Studio'da 'Local Server' sekmesinden başlatman gerekiyor."
        )
    if status == 404:
        return (
            f"{where}: '{model.name}' modeli bulunamadı. "
            "LM Studio'da yüklü modelin tam kimliğini kullan."
        )
    # llama.cpp/LM Studio reports window overflow with a 400 and in its
    # own words. The raw form tells the user nothing; the number inside it
    # is exactly the value that needs adjusting.
    if match := re.search(r"n_ctx:\s*(\d+)", text):
        window = int(match.group(1))
        return (
            f"Model {window} token'lık pencereyle yüklü ama istem daha büyük. "
            "İki yerden biri düzeltilmeli:\n"
            f"  · LM Studio'da modeli daha büyük bir bağlamla yükle "
            f"(şu an {window}), ya da\n"
            f"  · Ayarlar › bağlam'dan pencereyi {window} yaz — o zaman "
            "konuşma dolmadan özetlenip sürüyor."
        )

    if status == 400 and "tool" in text.lower():
        return (
            f"{where}: sunucu araç çağrısını reddetti ({text}). "
            "Bu model araç kullanımını desteklemiyor olabilir."
        )
    return f"{where}: {text}" if status is None else f"{where} {status}: {text}"
