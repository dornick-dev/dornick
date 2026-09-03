"""Provider translation and OpenAI-compatible backend tests.

Format bugs are this layer's sneakiest class of bug: the server returns
400 but the cause is somewhere in the middle of the message array. Since
the translation is pure functions, all of it can be verified without a
network.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from dornick.backends import build_client
from dornick.backends.openai_backend import OpenAIBackend
from dornick.backends.translate import (
    map_finish_reason,
    parse_arguments,
    to_anthropic_blocks,
    to_openai_messages,
    to_openai_tools,
)
from dornick.config import ModelConfig
from dornick.context import Prepared

SYSTEM = [{"type": "text", "text": "çekirdek"}, {"type": "text", "text": "ruh"}]


# -- outbound translation ----------------------------------------------


def test_system_blocks_collapse_into_one_message() -> None:
    out = to_openai_messages(SYSTEM, [])
    assert out == [{"role": "system", "content": "çekirdek\n\nruh"}]


def test_tool_use_becomes_tool_calls() -> None:
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "bakıyorum"},
                {"type": "tool_use", "id": "t1", "name": "shell", "input": {"command": "ls"}},
            ],
        }
    ]
    assistant = to_openai_messages([], messages)[0]

    assert assistant["content"] == "bakıyorum"
    call = assistant["tool_calls"][0]
    assert call["id"] == "t1"
    assert call["function"]["name"] == "shell"
    assert json.loads(call["function"]["arguments"]) == {"command": "ls"}


def test_tool_results_precede_user_text() -> None:
    """OpenAI ordering is strict: tool messages must directly follow the
    assistant's tool_calls. If a user message slips in between, the server rejects."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "bir de şuna bak"},
                {"type": "tool_result", "tool_use_id": "t1", "content": "çıktı"},
            ],
        }
    ]
    out = to_openai_messages([], messages)

    assert [m["role"] for m in out] == ["tool", "user"]
    assert out[0]["tool_call_id"] == "t1"


def test_error_results_are_marked_for_the_model() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "yok", "is_error": True}
            ],
        }
    ]
    assert to_openai_messages([], messages)[0]["content"].startswith("HATA:")


def test_thinking_blocks_are_dropped() -> None:
    """Local models do not understand the thinking block; sending it causes errors."""
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "gizli akıl yürütme", "signature": "x"},
                {"type": "text", "text": "cevap"},
            ],
        }
    ]
    assistant = to_openai_messages([], messages)[0]
    assert assistant["content"] == "cevap"
    assert "gizli" not in json.dumps(assistant, ensure_ascii=False)


def test_images_become_data_urls() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "bu ne"},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": "AAA"},
                },
            ],
        }
    ]
    parts = to_openai_messages([], messages)[0]["content"]
    assert parts[1]["image_url"]["url"] == "data:image/png;base64,AAA"


def test_lone_text_is_sent_as_a_plain_string() -> None:
    """Some compatible servers only accept the array form when an image is present."""
    messages = [{"role": "user", "content": [{"type": "text", "text": "selam"}]}]
    assert to_openai_messages([], messages)[0]["content"] == "selam"


def test_image_inside_tool_result_degrades_to_a_note() -> None:
    """role=tool content must be a string; an image must not vanish silently."""
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": [
                        {"type": "text", "text": "ekran alındı"},
                        {"type": "image", "source": {"type": "base64", "data": "AAA"}},
                    ],
                }
            ],
        }
    ]
    content = to_openai_messages([], messages)[0]["content"]
    assert "ekran alındı" in content
    assert "görüntü" in content


def test_tool_schema_shape() -> None:
    tools = to_openai_tools(
        [{"name": "shell", "description": "d", "input_schema": {"type": "object"}}]
    )
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["parameters"] == {"type": "object"}


# -- inbound translation -----------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),          # markdown fence
        ('Tabii! {"a": 1}', {"a": 1}),                  # chatter prepended
        ("", {}),
        ("tamamen bozuk", {}),
        ('["liste"]', {}),                              # not a dict
    ],
)
def test_parse_arguments_repairs_common_local_model_mistakes(raw: str, expected: dict) -> None:
    assert parse_arguments(raw) == expected


def test_missing_call_id_is_synthesized() -> None:
    """tool_result matching depends on the id; if it is missing we must generate one."""
    blocks = to_anthropic_blocks("", [{"name": "shell", "arguments": "{}"}])
    assert blocks[0]["id"]


@pytest.mark.parametrize(
    ("finish", "expected"),
    [("stop", "end_turn"), ("tool_calls", "tool_use"), ("length", "max_tokens"), (None, "end_turn")],
)
def test_finish_reason_mapping(finish: str | None, expected: str) -> None:
    assert map_finish_reason(finish) == expected


# -- backend ----------------------------------------------------------


def chunk(
    content=None, tool_calls=None, finish=None, usage=None, reasoning=None, extra=None
) -> SimpleNamespace:
    delta = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning,
        model_extra=extra or {},
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish)], usage=usage
    )


def fragment(index: int, *, id=None, name=None, arguments=None) -> SimpleNamespace:
    return SimpleNamespace(
        index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments)
    )


class FakeStream:
    """A stream that records whether it was closed."""

    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self.chunks = chunks
        self.closed = False

    def __aiter__(self):
        async def gen():
            for c in self.chunks:
                yield c

        return gen()

    async def close(self) -> None:
        self.closed = True


class FakeOpenAI:
    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self.seen: dict = {}
        self.stream = FakeStream(chunks)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.seen = kwargs
        return self.stream

    async def close(self) -> None:
        pass


def backend(chunks: list[SimpleNamespace], **overrides) -> tuple[OpenAIBackend, FakeOpenAI]:
    fake = FakeOpenAI(chunks)
    model = ModelConfig(
        name="local-model", provider="openai", base_url="http://localhost:1234/v1", **overrides
    )
    return OpenAIBackend(model, client=fake), fake


def prepared() -> Prepared:
    return Prepared(
        system=SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": "merhaba"}]}],
        betas=[],
        context_management=None,
    )


async def test_text_stream_is_assembled(monkeypatch) -> None:
    be, _ = backend([chunk(content="mer"), chunk(content="haba", finish="stop")])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())

    assert result.content == [{"type": "text", "text": "merhaba"}]
    assert result.stop_reason == "end_turn"


async def test_tool_call_assembled_from_fragments() -> None:
    """Arguments arrive in pieces; a joining bug silently produces broken JSON."""
    be, _ = backend(
        [
            chunk(tool_calls=[fragment(0, id="c1", name="shell", arguments='{"comm')]),
            chunk(tool_calls=[fragment(0, arguments='and": "ls"}')]),
            chunk(finish="tool_calls"),
        ]
    )
    result = await be.turn(prepared(), [], cancel=asyncio.Event())

    assert result.stop_reason == "tool_use"
    assert result.tool_uses() == [
        {"type": "tool_use", "id": "c1", "name": "shell", "input": {"command": "ls"}}
    ]


async def test_parallel_tool_calls_keep_their_slots() -> None:
    be, _ = backend(
        [
            chunk(
                tool_calls=[
                    fragment(0, id="a", name="read_file", arguments='{"path":"x"}'),
                    fragment(1, id="b", name="list_dir", arguments='{"path":"y"}'),
                ]
            ),
            chunk(finish="tool_calls"),
        ]
    )
    result = await be.turn(prepared(), [], cancel=asyncio.Event())
    assert [b["name"] for b in result.tool_uses()] == ["read_file", "list_dir"]


async def test_tool_calls_imply_tool_use_even_without_finish_reason() -> None:
    """Some compatible servers omit finish_reason; the loop would then
    mistake the turn for end_turn and stop without ever running the tool."""
    be, _ = backend([chunk(tool_calls=[fragment(0, id="c1", name="shell", arguments="{}")])])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())
    assert result.stop_reason == "tool_use"


async def test_cancel_stops_mid_stream() -> None:
    cancel = asyncio.Event()
    cancel.set()
    be, _ = backend([chunk(content="hiç görünmemeli", finish="stop")])

    result = await be.turn(prepared(), [], cancel=cancel)
    assert result.interrupted is True
    assert result.message is None


async def test_usage_is_carried_over() -> None:
    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=30)
    be, _ = backend([chunk(content="x", finish="stop", usage=usage)])

    result = await be.turn(prepared(), [], cancel=asyncio.Event())
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 30


async def test_usage_maps_cached_tokens_from_prompt_details() -> None:
    """OpenRouter/OpenAI prompt_tokens_details.cached_tokens → cache_read."""
    from dornick.backends.openai_backend import _usage
    from dornick.context import cache_report

    raw = SimpleNamespace(
        prompt_tokens=5000,
        completion_tokens=40,
        prompt_tokens_details=SimpleNamespace(cached_tokens=4200),
    )
    usage = _usage(raw)
    assert usage.cache_read_input_tokens == 4200
    assert usage.input_tokens == 800  # fresh = total - cache
    report = cache_report(usage)
    assert report["cache_read"] == 4200
    assert report["prompt_total"] == 5000


async def test_anthropic_only_parameters_are_not_sent_to_local_servers() -> None:
    """effort and thinking are 400 material on local servers."""
    be, fake = backend([chunk(content="x", finish="stop")], temperature=0.4)
    await be.turn(prepared(), [{"name": "shell", "description": "d", "input_schema": {}}], cancel=asyncio.Event())

    assert "output_config" not in fake.seen
    assert "thinking" not in fake.seen
    assert fake.seen["temperature"] == 0.4
    assert fake.seen["model"] == "local-model"


async def test_reasoning_only_turn_is_marked_incomplete_not_answered() -> None:
    """Thinking models sometimes finish a turn only in the reasoning
    channel: they plan, say "now I should do this" and stop.

    Presenting that as an answer left the user hanging — in a real run the
    screen said "Şimdi bilgi toplayıp sunmalıyım:" and the conversation
    ended. The reasoning must enter the history (so the model sees its own
    plan) but must not count as an answer; the loop keeps the turn going
    when it sees `empty_turn`.
    """
    from dornick.backends import Callbacks

    shown: list[str] = []
    be, _ = backend([chunk(reasoning="Şimdi şunu yapmalıyım:", finish="stop")])
    result = await be.turn(
        prepared(), [], cancel=asyncio.Event(), callbacks=Callbacks(on_text=shown.append)
    )

    assert result.error is None
    assert result.stop_reason == "empty_turn"
    # It sits in the history...
    assert result.content == [{"type": "text", "text": "Şimdi şunu yapmalıyım:"}]
    # ...but it never flowed through the answer channel.
    assert shown == []


async def test_reasoning_in_model_extra_is_found() -> None:
    """The field is not in the OpenAI schema; the SDK puts it into model_extra."""
    be, _ = backend([chunk(extra={"reasoning_content": "gizli kanal"}, finish="stop")])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())
    assert result.content == [{"type": "text", "text": "gizli kanal"}]


async def test_completely_empty_response_is_an_error_not_an_empty_turn() -> None:
    """Writing an empty content array into the history breaks the next request."""
    be, _ = backend([chunk(finish="stop")])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())

    assert result.message is None
    assert "boş yanıt" in (result.error or "")
    assert "bağlam sınırına" not in (result.error or "")


async def test_empty_length_is_recoverable_not_context_error() -> None:
    """finish=length + empty content is not the context — it is the output
    budget. api_error with 5 retries repeats the same request; empty_turn continues."""
    be, _ = backend([chunk(finish="length")])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())

    assert result.error is None
    assert result.stop_reason == "empty_turn"
    assert "bütçesi" in (result.content[0]["text"] if result.content else "")


async def test_stream_is_closed_after_normal_completion() -> None:
    """If not closed, the httpx connection gets collected at shutdown and prints an error."""
    be, fake = backend([chunk(content="bitti", finish="stop")])
    await be.turn(prepared(), [], cancel=asyncio.Event())
    assert fake.stream.closed is True


async def test_stream_is_closed_when_cancelled() -> None:
    """Cancel DURING the stream: the open stream is closed. Cancel BEFORE
    the request: the request is never built — instead of pointlessly
    opening and closing a connection, Stop is handled instantly (live
    wound, 01.09: Stop was only handled once the stream started)."""
    # 1) During the stream: cut when the first chunk arrives, the stream closes.
    cancel = asyncio.Event()
    be, fake = backend([chunk(content="x"), chunk(content="y", finish="stop")])
    result = await be.turn(
        prepared(), [], cancel=cancel,
        callbacks=Callbacks(on_text=lambda _t: cancel.set()))
    assert result.interrupted is True
    assert fake.stream.closed is True

    # 2) Before the request: no request goes out at all.
    early = asyncio.Event()
    early.set()
    be2, fake2 = backend([chunk(content="x", finish="stop")])
    result2 = await be2.turn(prepared(), [], cancel=early)
    assert result2.interrupted is True
    assert fake2.seen == {}, "no request should be built on a cancelled turn"


def test_unknown_provider_fails_loudly() -> None:
    with pytest.raises(ValueError, match="Bilinmeyen sağlayıcı"):
        build_client(ModelConfig(provider="llamafile"))


# -- tool calls leaking into text --------------------------------------


def test_inline_tool_call_in_text_is_executed_not_shown() -> None:
    """Some local models produce the call in text, not in the tool_calls field.

    If it is not parsed the call never runs and the raw XML looks like an
    answer to the user — in a real run exactly this happened.
    """
    from dornick.backends.translate import extract_inline_calls

    raw = (
        "Tamam, kaydediyorum.\n"
        "<tool_call>\n<function=mind_memory>\n"
        "<parameter=action>\nsave\n</parameter>\n"
        "<parameter=content>\nFatih SCADA ile calisiyor.\n</parameter>\n"
        "</function>\n</tool_call>"
    )
    text, calls = extract_inline_calls(raw)

    assert text == "Tamam, kaydediyorum."
    assert "<tool_call>" not in text
    assert calls == [
        {"name": "mind_memory",
         "arguments": {"action": "save", "content": "Fatih SCADA ile calisiyor."}}
    ]


def test_inline_json_form_is_parsed() -> None:
    from dornick.backends.translate import extract_inline_calls

    text, calls = extract_inline_calls(
        'Bak: <tool_call>{"name": "shell", "arguments": {"command": "ls"}}</tool_call>'
    )
    assert text == "Bak:"
    assert calls == [{"name": "shell", "arguments": {"command": "ls"}}]


def test_plain_text_is_left_alone() -> None:
    from dornick.backends.translate import extract_inline_calls

    assert extract_inline_calls("sadece bir cevap") == ("sadece bir cevap", [])


async def test_backend_turns_inline_calls_into_tool_use() -> None:
    be, _ = backend([
        chunk(content="Bakiyorum. <tool_call><function=list_dir>"),
        chunk(content="<parameter=path>src</parameter></function></tool_call>", finish="stop"),
    ])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())

    assert result.stop_reason == "tool_use"
    assert result.tool_uses() == [
        {"type": "tool_use", "id": "inline_0", "name": "list_dir", "input": {"path": "src"}}
    ]
    # The raw tag must not leak into the answer.
    assert "<tool_call>" not in result.content[0]["text"]


# -- thinking effort ---------------------------------------------------
#
# The "effort" setting was never sent to OpenAI-compatible servers:
# thinking models like qwen3 reasoned by their own choice and the value on
# the settings page did nothing. Measurement (qwen3-27b, OpenRouter,
# one-word prompt): high 8.97 s — low 1.60 s. Reasoning for nine seconds
# to say hello takes the assistant out of real time.


def _backend(**fields):
    from dornick.backends.openai_backend import OpenAIBackend
    from dornick.config import ModelConfig

    return OpenAIBackend(ModelConfig(**{"name": "qwen", **fields}), client=object())


def test_the_effort_setting_actually_reaches_the_server() -> None:
    assert _backend(effort="low")._reasoning() == {"effort": "low"}
    assert _backend(effort="high")._reasoning() == {"effort": "high"}


def test_turning_thinking_off_says_so_explicitly() -> None:
    """Not sending the field at all means "let the model think as it pleases"."""
    assert _backend(thinking=False)._reasoning() == {"enabled": False}


def test_a_model_that_cannot_think_omits_reasoning() -> None:
    """If the catalog says no thinking, sending the field means a 400 + a round-trip of latency."""
    be = _backend(can_think=False, thinking=True)
    assert be._reasoning() is None
    assert be._no_reasoning is True


def test_efforts_the_server_does_not_know_are_folded_down() -> None:
    """xhigh/max exist only on Claude; sending them as-is means a 400."""
    assert _backend(effort="xhigh")._reasoning() == {"effort": "high"}
    assert _backend(effort="max")._reasoning() == {"effort": "high"}
    assert _backend(effort="")._reasoning() is None


def test_a_server_that_rejects_the_field_is_recognised() -> None:
    """A server that does not know the field returns 400; the field is
    dropped once, retried, and never sent again."""
    from dornick.backends.openai_backend import _rejects_reasoning

    assert _rejects_reasoning(Exception("400: unknown field 'reasoning'"))
    assert _rejects_reasoning(Exception("Unrecognized request argument: extra_body"))
    # A real error must not be mistaken for a field error and silently swallowed.
    assert not _rejects_reasoning(Exception("rate limit exceeded"))


def test_the_field_is_only_dropped_once() -> None:
    """Taking a 400 and retrying on every request would add a round-trip
    of latency to every answer."""
    backend = _backend(effort="low")
    assert backend._no_reasoning is False


# -- image stripping on a text-only model (auto-heal) ------------------


class ImageRejectingOpenAI:
    """Image error on the first call, then success — imitates a text-only model."""

    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self.stream = FakeStream(chunks)
        self.calls: list[dict] = []
        self._fail_next = True
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail_next:
            self._fail_next = False
            exc = Exception("Error code: 404 - No endpoints found that support image input")
            exc.status_code = 404  # type: ignore[attr-defined]
            raise exc
        return self.stream

    async def close(self) -> None:
        pass


def _image_prepared() -> Prepared:
    return Prepared(
        system=SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "bak"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
        ]}],
        betas=[],
        context_management=None,
    )


async def test_text_only_model_strips_images_and_retries() -> None:
    """After switching to a text-only model the frame in the history gives
    a 404; the backend learns once, strips the frame and retries — the
    user never sees an error."""
    fake = ImageRejectingOpenAI([chunk(content="tamam", finish="stop")])
    model = ModelConfig(name="deepseek-flash", provider="openai", base_url="http://x/v1")
    be = OpenAIBackend(model, client=fake)

    result = await be.turn(_image_prepared(), [], cancel=asyncio.Event())

    assert result.content == [{"type": "text", "text": "tamam"}]
    assert len(fake.calls) == 2, "no retry after the error"
    second = str(fake.calls[1]["messages"])
    assert "image_url" not in second, "the image is still in the request"
    assert "göremiyor" in second, "the image trace was not placed"
    assert be._no_vision, "text-only was not learned"


async def test_learned_no_vision_strips_before_sending() -> None:
    """Once learned, later turns must not eat a pointless 404: the frames
    are stripped from the start."""
    fake = FakeOpenAI([chunk(content="ok", finish="stop")])
    model = ModelConfig(name="x", provider="openai", base_url="http://x/v1")
    be = OpenAIBackend(model, client=fake)
    be._no_vision = True

    await be.turn(_image_prepared(), [], cancel=asyncio.Event())

    assert "image_url" not in str(fake.seen["messages"])


async def test_known_no_vision_strips_on_the_first_turn() -> None:
    """If the catalog says no vision, no 404 is expected on the first turn."""
    fake = FakeOpenAI([chunk(content="ok", finish="stop")])
    model = ModelConfig(
        name="x", provider="openai", base_url="http://x/v1", vision=False,
    )
    be = OpenAIBackend(model, client=fake)

    await be.turn(_image_prepared(), [], cancel=asyncio.Event())

    assert be._no_vision
    assert "image_url" not in str(fake.seen["messages"])


# -- cancel: before the first token ------------------------------------
#
# The wound: cancel was only polled when a chunk ARRIVED. On the FIRST
# uncached turn prompt processing can take minutes and there are no chunks
# in that time — Stop did nothing (the root of the "stop doesn't work on
# the first conversation" report). `cancellable` races every step against
# the cancel wait.


class _SilentStream:
    """A stream that never sends the first token: the server is processing the prompt."""

    def __init__(self) -> None:
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(3600)

    async def close(self) -> None:
        self.closed = True


async def test_cancellable_fires_while_waiting_for_the_first_chunk() -> None:
    from dornick.backends.base import Interrupted, cancellable

    cancel = asyncio.Event()

    async def consume() -> None:
        async for _ in cancellable(_SilentStream(), cancel):
            raise AssertionError("no chunk should have arrived")

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.01)
    assert not task.done(), "the stream should be waiting"
    cancel.set()
    with pytest.raises(Interrupted):
        await asyncio.wait_for(task, timeout=2)


async def test_cancellable_passes_chunks_through_untouched() -> None:
    from dornick.backends.base import cancellable

    cancel = asyncio.Event()
    got = []
    async for c in cancellable(FakeStream([chunk(content="a"), chunk(content="b")]).__aiter__(), cancel):
        got.append(c.choices[0].delta.content)
    assert got == ["a", "b"]


async def test_interrupt_before_first_token_returns_interrupted() -> None:
    """End to end: the turn itself can be cancelled while waiting for a
    chunk and the result is `interrupted` — not an error (no error must be
    written to the auto-mode ledger)."""

    class SilentOpenAI:
        def __init__(self) -> None:
            self.stream = _SilentStream()
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create))

        async def _create(self, **kwargs):
            return self.stream

        async def close(self) -> None:
            pass

    fake = SilentOpenAI()
    model = ModelConfig(name="x", provider="openai", base_url="http://x/v1")
    be = OpenAIBackend(model, client=fake)

    cancel = asyncio.Event()
    task = asyncio.ensure_future(be.turn(prepared(), [], cancel=cancel))
    await asyncio.sleep(0.01)
    assert not task.done()

    cancel.set()
    result = await asyncio.wait_for(task, timeout=2)

    assert result.interrupted is True
    assert result.error is None
    assert fake.stream.closed, "a cancelled stream must be closed"


def test_mid_turn_system_note_becomes_a_user_note():
    """The Anthropic family accepts system only at the head of the array;
    mid-turn notes must go as user-notes — otherwise Claude models return 400."""
    from dornick.backends.translate import to_openai_messages

    messages = [
        {"role": "user", "content": [{"type": "text", "text": "merhaba"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "selam"}]},
        {"role": "system", "content": [{"type": "text", "text": "hedef notu"}]},
    ]
    out = to_openai_messages([{"type": "text", "text": "sistem promptu"}], messages)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "user"]
    assert out[-1]["content"].startswith("[Sistem notu]")


# -- fallback model ----------------------------------------------------
#
# While a long job runs, credits run out (402) or the model id in the
# settings becomes invalid. The provider gives the same answer on every
# request: waiting achieves nothing and a job hours in the making is left
# half-done. If a fallback model is defined, the turn continues there
# instead of dying.

from dornick.backends.base import Callbacks, TurnResult      # noqa: E402
from dornick.backends.fallback import FallbackBackend, is_permanent   # noqa: E402


class _FakeBackend:
    """A backend imitation that returns the given results in order."""

    def __init__(self, name: str, results: list[TurnResult]) -> None:
        self.name = name
        self._results = list(results)
        self.calls = 0
        self.closed = False

    async def turn(self, prepared, tools, *, cancel=None, callbacks=None) -> TurnResult:
        self.calls += 1
        return self._results.pop(0) if self._results else TurnResult(error="senaryo bitti")

    async def count_tokens(self, prepared, tools) -> int:
        return 0

    async def close(self) -> None:
        self.closed = True


def _setup(primary_results, fallback_results=None):
    """The fallback wrapper + two fake backends."""
    model = ModelConfig(name="asil", fallback_model="yedek")
    made: dict[str, _FakeBackend] = {}

    def build(cfg: ModelConfig) -> _FakeBackend:
        results = primary_results if cfg.name == "asil" else (fallback_results or [])
        made[cfg.name] = _FakeBackend(cfg.name, results)
        return made[cfg.name]

    return FallbackBackend(model, build), made


def _ok(text: str = "tamam") -> TurnResult:
    return TurnResult(message=SimpleNamespace(content=[{"type": "text", "text": text}],
                                              stop_reason="end_turn", usage=None))


def test_permanent_and_transient_errors_are_told_apart() -> None:
    """The measure is a single question: if the same request were sent
    again shortly, would the result change?

    If it would (connection, 429, 5xx) the loop's retry ladder is the
    right place; falling to the fallback would mean permanently switching
    to a weaker model on a provider hiccup.
    """
    for permanent in ("openrouter 402: insufficient credits",
                      "qwen3.1-14b is not a valid model ID",
                      "openrouter 404: model bulunamadı",
                      "403: unsupported_country"):
        assert is_permanent(permanent), permanent

    for transient in ("Connection error", "openrouter 429: rate limited",
                      "openrouter 500: upstream", "timeout", "", None):
        assert not is_permanent(transient), transient


def test_a_permanent_failure_continues_on_the_fallback() -> None:
    client, made = _setup([TurnResult(error="openrouter 402: insufficient credits")], [_ok("yedek konuştu")])

    said: list[str] = []
    result = asyncio.run(client.turn(None, [], cancel=None,
                                     callbacks=Callbacks(on_text=said.append)))

    assert result.error is None
    assert made["yedek"].calls == 1
    assert client.switched
    # The user must see what happened: a silent model change means a job
    # whose quality silently degraded.
    assert any("yedek" in line for line in said)


def test_the_notice_never_enters_the_answer_content() -> None:
    """The line goes through the DISPLAY channel: writing a sentence the
    model never said into the history would be mistaken for the model's
    own words on later turns."""
    client, _ = _setup([TurnResult(error="402: payment required")], [_ok("asıl cevap")])
    result = asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))
    text = " ".join(b.get("text", "") for b in result.content)
    assert "yedek modelle" not in text
    assert text == "asıl cevap"


def test_a_transient_failure_is_left_to_the_retry_ladder() -> None:
    """A transient error must never reach the fallback: the loop already retries it."""
    client, made = _setup([TurnResult(error="Connection error")], [_ok()])
    result = asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))

    assert result.error == "Connection error"
    assert "yedek" not in made          # the fallback client was never built
    assert not client.switched


def test_an_interruption_is_a_decision_not_a_failure() -> None:
    client, made = _setup([TurnResult(interrupted=True)], [_ok()])
    result = asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))
    assert result.interrupted and "yedek" not in made


def test_once_switched_the_main_model_is_not_tried_again() -> None:
    """Retrying the primary on every turn doubles the turn into two
    requests, and if credits are out it never recovers."""
    client, made = _setup([TurnResult(error="402: no credit")], [_ok(), _ok()])
    asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))
    asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))

    assert made["asil"].calls == 1      # never tried on the second turn
    assert made["yedek"].calls == 2


def test_without_a_fallback_nothing_changes() -> None:
    """Without a fallback today's behaviour must stay as-is: the error surfaces."""
    plain = build_client(ModelConfig(name="asil"))
    assert not isinstance(plain, FallbackBackend)
    # Wrapping is pointless when the fallback equals the primary: same model twice.
    same = build_client(ModelConfig(name="asil", fallback_model="asil"))
    assert not isinstance(same, FallbackBackend)


def test_the_fallback_client_keeps_the_provider_and_address() -> None:
    """Fallback means "another model at the same door". Silently falling to
    a different provider would make it invisible which key is being spoken with."""
    seen: list[ModelConfig] = []

    def build(cfg: ModelConfig):
        seen.append(cfg)
        return _FakeBackend(cfg.name, [_ok()])

    model = ModelConfig(name="asil", fallback_model="yedek",
                        base_url="http://localhost:1234/v1", api_key_env="LOCAL_KEY")
    client = FallbackBackend(model, build)
    client.switched = True
    asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))

    fallback = seen[-1]
    assert fallback.name == "yedek"
    assert fallback.base_url == "http://localhost:1234/v1"
    assert fallback.api_key_env == "LOCAL_KEY"
    # The fallback has no fallback: no infinite chain.
    assert fallback.fallback_model == ""


def test_closing_releases_both_clients() -> None:
    client, made = _setup([TurnResult(error="402")], [_ok()])
    asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))
    asyncio.run(client.close())
    assert made["asil"].closed and made["yedek"].closed


def test_the_fallback_field_survives_a_settings_round_trip(tmp_path) -> None:
    """If the field is not written to config.json and read back, the
    settings page looks like it works but nothing changes."""
    from dornick import settings
    from dornick.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    updated = settings.apply(config, {"model": {"fallback_model": "yedek-model"}})
    assert updated.model.fallback_model == "yedek-model"
    assert Config.load(tmp_path).model.fallback_model == "yedek-model"


# -- round trip of provider-specific fields -----------------------------
#
# Gemini attaches a `thought_signature` to every tool call in thinking
# models and REQUIRES you to send it back on the NEXT turn. Since dornick
# calls the tool and sends the answer back within one turn, this landed
# exactly on our path and the field got lost in translation:
#
#   400 — Function call is missing a thought_signature in functionCall parts.
#
# The fix is not to MODEL the field but not to LOSE it: we carry even a
# field whose name we don't know, so the next provider adding such a field
# doesn't break us.


def test_provider_fields_survive_the_round_trip() -> None:
    from dornick.backends.translate import to_anthropic_blocks, to_openai_messages

    blocks = to_anthropic_blocks("", [{
        "id": "call_1", "name": "mind_memory", "arguments": '{"kind": "fact"}',
        "extra": {"thought_signature": "ABC123", "extra_content": {"google": {"x": 1}}},
    }])
    (block,) = blocks
    assert block["saglayici"]["thought_signature"] == "ABC123"

    messages = to_openai_messages([], [{"role": "assistant", "content": blocks}])
    (call,) = messages[0]["tool_calls"]
    assert call["thought_signature"] == "ABC123"
    assert call["extra_content"] == {"google": {"x": 1}}
    # The id and arguments are OURS: the provider field does not overwrite them.
    assert call["id"] == "call_1"
    assert call["function"]["name"] == "mind_memory"


def test_a_call_without_provider_fields_is_unchanged() -> None:
    """On a provider without the field, not a single character of output may change."""
    from dornick.backends.translate import to_anthropic_blocks, to_openai_messages

    blocks = to_anthropic_blocks("", [
        {"id": "c1", "name": "shell", "arguments": '{"command": "ls"}'}])
    assert "saglayici" not in blocks[0]
    (call,) = to_openai_messages([], [{"role": "assistant", "content": blocks}])[0]["tool_calls"]
    assert set(call) == {"id", "type", "function"}


def test_provider_fields_never_reach_anthropic() -> None:
    """Anthropic rejects fields it does not know; since the same
    conversation can move between two providers (fallback model, model
    switching), weeding is a must."""
    from dornick.context import drop_provider_fields

    messages = [
        {"role": "user", "content": [{"type": "text", "text": "selam"}]},
        {"role": "assistant", "content": [
            {"type": "text", "text": "bakıyorum"},
            {"type": "tool_use", "id": "c1", "name": "shell", "input": {"command": "ls"},
             "saglayici": {"thought_signature": "ABC123"}},
        ]},
    ]
    clean = drop_provider_fields(messages)
    tool = clean[1]["content"][1]
    assert "saglayici" not in tool
    assert tool["id"] == "c1" and tool["input"] == {"command": "ls"}
    # The source list must NOT change: the same conversation also goes down the OpenAI path.
    assert "saglayici" in messages[1]["content"][1]


def test_stripping_does_not_copy_when_there_is_nothing_to_strip() -> None:
    """Without the field the list comes back as-is — no deep copy on every request."""
    from dornick.context import drop_provider_fields

    messages = [{"role": "user", "content": [{"type": "text", "text": "selam"}]}]
    assert drop_provider_fields(messages) is messages


def test_every_array_in_a_tool_schema_declares_items() -> None:
    """When Gemini sees an array without `items` it rejects the ENTIRE
    tool list, NOT just the tool — so one tool's omission makes dornick
    completely unusable on that model. This happened verbatim in production:

        function_declarations[23].parameters.properties[steps].items: missing
        function_declarations[37].parameters.properties[nodes].items: missing
    """
    import pathlib
    import tempfile

    from dornick.config import Config
    from dornick.tools import build_registry

    cfg = Config.load(pathlib.Path(tempfile.mkdtemp()))
    cfg.ensure_dirs()
    registry = build_registry(cfg)

    def missing_items(schema, path=""):
        if not isinstance(schema, dict):
            return []
        found = []
        if schema.get("type") == "array" and "items" not in schema:
            found.append(path or "(root)")
        for name, sub in (schema.get("properties") or {}).items():
            found += missing_items(sub, f"{path}.{name}" if path else name)
        if isinstance(schema.get("items"), dict):
            found += missing_items(schema["items"], path + "[]")
        return found

    defective = {s.name: e for s in registry.all() if (e := missing_items(s.input_schema))}
    assert not defective, f"`items` missing: {defective}"


def test_the_converter_repairs_a_schema_that_slipped_through() -> None:
    """Fixing the schemas by hand is necessary but not sufficient: when
    the next tool is written with the same mistake, a broken schema must
    still not reach the provider."""
    from dornick.backends.translate import to_openai_tools

    (tool,) = to_openai_tools([{
        "name": "deneme",
        "description": "d",
        "input_schema": {
            "type": "object",
            "properties": {
                "liste": {"type": "array"},
                "ic": {"type": "object", "properties": {"derin": {"type": "array"}}},
                "saglam": {"type": "array", "items": {"type": "string"}},
            },
        },
    }])
    fields = tool["function"]["parameters"]["properties"]
    assert fields["liste"]["items"] == {}
    assert fields["ic"]["properties"]["derin"]["items"] == {}
    # A schema that is already correct is NOT touched.
    assert fields["saglam"]["items"] == {"type": "string"}


# -- prompt cache marks (OpenRouter) -----------------------------------
#
# The measured pattern taken from the OpenCode review: an ephemeral point
# on the first system + last two messages. Going unmarked was measured as
# a ~6.7x cost difference on the same model/same job (kiyas-opencode-2608.md).


def test_cache_markers_land_on_system_and_last_two() -> None:
    from dornick.backends.openai_backend import _mark_cache

    messages = [
        {"role": "system", "content": "sistem istemi"},
        {"role": "user", "content": "ilk soru"},
        {"role": "assistant", "content": "cevap"},
        {"role": "tool", "content": "araç çıktısı", "tool_call_id": "t1"},
    ]
    _mark_cache(messages)

    # System: plain text is wrapped in a single part and marked.
    system = messages[0]["content"]
    assert isinstance(system, list) and system[0]["cache_control"] == {"type": "ephemeral"}
    assert system[0]["text"] == "sistem istemi"
    # The last two (assistant + tool) are marked; the first user message is NOT.
    assert isinstance(messages[1]["content"], str)
    assert messages[2]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert messages[3]["content"][0]["cache_control"] == {"type": "ephemeral"}
    # Three points in total: under the Anthropic family's limit of 4.
    points = sum(
        1
        for m in messages
        if isinstance(m.get("content"), list)
        for p in m["content"]
        if isinstance(p, dict) and "cache_control" in p
    )
    assert points == 3


def test_cache_markers_can_be_stripped_after_rejection() -> None:
    from dornick.backends.openai_backend import _mark_cache, _unmark_cache

    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]
    _mark_cache(messages)
    _unmark_cache(messages)
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            assert all("cache_control" not in p for p in content if isinstance(p, dict))


def test_cache_markers_only_for_openrouter_base() -> None:
    """No mark ever goes to endpoints like LM Studio / Ollama: the flag comes from the address."""
    import re
    from pathlib import Path

    source = (Path(__file__).parent.parent / "src/dornick/backends/openai_backend.py").read_text(encoding="utf-8")
    assert re.search(r'_cache_marked = "openrouter" in', source)
    assert "_mark_cache(messages)" in source

# -- per-call silence window --------------------------------------------
#
# Measured wound (29.08, z1): a single provider call went silent for
# minutes and the turn only broke at the 900 s gate ceiling. The place to
# cut is the CALL, not the turn: a long call streaming chunks is healthy,
# one silent for the whole window is hung.


async def test_a_silent_stream_raises_stalled_within_the_window() -> None:
    from dornick.backends.base import Stalled, cancellable
    cancel = asyncio.Event()
    with pytest.raises(Stalled):
        async for _ in cancellable(_SilentStream(), cancel, stall_s=0.05):
            raise AssertionError('no chunk should have arrived')


async def test_healthy_chunks_flow_despite_the_window() -> None:
    from dornick.backends.base import cancellable
    cancel = asyncio.Event()
    got = []
    async for c in cancellable(FakeStream([chunk(content='a'),
                                           chunk(content='b')]).__aiter__(),
                               cancel, stall_s=5.0):
        got.append(c.choices[0].delta.content)
    assert got == ['a', 'b']


async def test_stalled_call_is_retried_once_then_reported() -> None:
    # First call hung, second healthy: the turn result must come out normal.
    from dornick.backends import openai_backend as ob
    from types import SimpleNamespace
    from dornick.config import ModelConfig
    old = ob.CALL_SILENCE_S
    ob.CALL_SILENCE_S = 0.05
    try:
        streams = [_SilentStream(), FakeStream([chunk(content='tamam')])]
        async def create(**kwargs):
            return streams.pop(0)
        fake = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        model = ModelConfig(name='m', provider='openai',
                            base_url='https://openrouter.ai/api/v1')
        b = OpenAIBackend(model, client=fake)
        r = await b.turn(prepared(), [], cancel=asyncio.Event())
        assert r.error is None
        assert r.message.content[0]['text'] == 'tamam'
    finally:
        ob.CALL_SILENCE_S = old


async def test_local_endpoints_have_no_silence_window() -> None:
    from dornick.backends.openai_backend import _silence_window
    assert _silence_window('http://localhost:1234/v1') is None
    assert _silence_window('http://192.168.1.7:8080/v1') is None
    assert _silence_window('https://openrouter.ai/api/v1') == 120.0

