"""Translation between the Anthropic block format and the OpenAI chat format.

The two formats carry tool calls in different places:

    Anthropic   tool_use block in the assistant content
                tool_result block in the user content
    OpenAI      tool_calls array in the assistant message
                a separate role="tool" message, with tool_call_id

On the OpenAI side the ordering is strict: tool messages must **directly**
follow the tool_calls assistant message that requested them. If a user
message slips in between, the server rejects. That is why, when a user
turn has both tool_result and text, the tool messages are written first.

This module consists of pure functions and has no network access — format
bugs are the sneakiest class of bug, so being testable in isolation matters.
"""

from __future__ import annotations

import json
import re
from typing import Any

Block = dict[str, Any]
Message = dict[str, Any]

# Blocks specific to Anthropic with no OpenAI equivalent. Silently dropped:
# local models do not understand them and sending them causes errors.
DROPPED_BLOCK_TYPES = frozenset({"thinking", "redacted_thinking"})

IMAGE_IN_TOOL_RESULT = "[görüntü — bu sağlayıcı araç sonucunda görüntü kabul etmiyor]"

FINISH_REASONS = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


# -- outbound direction: Anthropic -> OpenAI ---------------------------


def to_openai_messages(system: list[Block], messages: list[Message]) -> list[Message]:
    out: list[Message] = []

    if system_text := "\n\n".join(
        b.get("text", "") for b in system if b.get("type") == "text"
    ).strip():
        out.append({"role": "system", "content": system_text})

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            continue

        if role == "assistant":
            out.append(_assistant_message(content))
        elif role == "system":
            # Mid-turn system notes (goal sync, harness notes) go with the
            # user role: the Anthropic family — even over OpenAI-compatible
            # endpoints — accepts system only at the head of the array
            # ("role 'system' must precede an 'assistant' message"), and
            # the OpenAI family reads the user-note just the same. One
            # format, zero provider sniffing.
            out.append({"role": "user",
                        "content": "[Sistem notu]\n" + _flatten_text(content)})
        else:
            out.extend(_user_messages(content))

    return out


def _assistant_message(content: list[Block]) -> Message:
    texts: list[str] = []
    tool_calls: list[Message] = []

    for block in content:
        kind = block.get("type")
        if kind in DROPPED_BLOCK_TYPES:
            continue
        if kind == "text":
            texts.append(block.get("text", ""))
        elif kind == "tool_use":
            call: Message = {
                "id": block.get("id", ""),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                },
            }
            # The provider's own fields are put back (see to_anthropic_blocks).
            # Known fields are not overwritten: the id and arguments are ours.
            for key, value in (block.get("saglayici") or {}).items():
                if key not in call:
                    call[key] = value
            tool_calls.append(call)

    message: Message = {"role": "assistant", "content": "\n".join(t for t in texts if t) or None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _user_messages(content: list[Block]) -> list[Message]:
    results = [b for b in content if b.get("type") == "tool_result"]
    rest = [b for b in content if b.get("type") != "tool_result"]

    # Tool results first: they must directly follow the assistant's tool_calls message.
    out: list[Message] = [
        {
            "role": "tool",
            "tool_call_id": r.get("tool_use_id", ""),
            "content": _tool_result_text(r),
        }
        for r in results
    ]

    if parts := _user_parts(rest):
        out.append({"role": "user", "content": parts})
    return out


def _user_parts(blocks: list[Block]) -> str | list[Block] | None:
    parts: list[Block] = []
    for block in blocks:
        kind = block.get("type")
        if kind == "text":
            parts.append({"type": "text", "text": block.get("text", "")})
        elif kind == "image":
            if url := _image_url(block):
                parts.append({"type": "image_url", "image_url": {"url": url}})

    if not parts:
        return None
    # If there is a single text part, send a plain string: some compatible
    # servers only accept the array form when an image is present.
    if len(parts) == 1 and parts[0]["type"] == "text":
        return parts[0]["text"]
    return parts


def _image_url(block: Block) -> str | None:
    source = block.get("source") or {}
    if source.get("type") == "base64":
        media = source.get("media_type", "image/png")
        return f"data:{media};base64,{source.get('data', '')}"
    if source.get("type") == "url":
        return source.get("url")
    return None


def _tool_result_text(result: Block) -> str:
    content = result.get("content")
    prefix = "HATA: " if result.get("is_error") else ""
    if isinstance(content, str):
        return prefix + content
    if isinstance(content, list):
        chunks = [
            block.get("text", "") if block.get("type") == "text" else IMAGE_IN_TOOL_RESULT
            for block in content
            if isinstance(block, dict)
        ]
        return prefix + "\n".join(c for c in chunks if c)
    return prefix + str(content or "")


def _flatten_text(content: list[Block]) -> str:
    return "\n".join(b.get("text", "") for b in content if b.get("type") == "text")


def repair_schema(schema: Any) -> Any:
    """Repairs the schema to the strictest of the providers.

    Today's only repair: an `array` without `items` gets a free-form
    `items`. Anthropic and OpenAI tolerate this; Gemini does not, and it
    rejects the ENTIRE tool list, NOT just the tool:

        GenerateContentRequest.tools[0].function_declarations[23]
        .parameters.properties[steps].items: missing field

    So one tool's omission makes Dornick completely unusable on that
    model. Fixing the schemas by hand is necessary but not sufficient: it
    is also caught here so the next tool written with the same mistake
    does not break things either.
    """
    if isinstance(schema, list):
        return [repair_schema(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    new_schema = {k: repair_schema(v) for k, v in schema.items()}
    if new_schema.get("type") == "array" and "items" not in new_schema:
        # Free-form content: we don't know what comes, and we don't invent it.
        new_schema["items"] = {}
    return new_schema


def to_openai_tools(tools: list[Block]) -> list[Message]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": repair_schema(
                    tool.get("input_schema") or {"type": "object", "properties": {}}),
            },
        }
        for tool in tools
    ]


# -- inbound direction: OpenAI -> Anthropic ----------------------------


def to_anthropic_blocks(text: str, tool_calls: list[dict[str, Any]]) -> list[Block]:
    blocks: list[Block] = []
    if text.strip():
        blocks.append({"type": "text", "text": text})
    for index, call in enumerate(tool_calls):
        block: Block = {
            "type": "tool_use",
            # Some compatible servers send no id; if missing we generate
            # one, because tool_result matching depends on it.
            "id": call.get("id") or f"call_{index}",
            "name": call.get("name", ""),
            "input": parse_arguments(call.get("arguments", "")),
        }
        # Provider-specific fields (like Gemini's `thought_signature`) are
        # kept on the block and sent back VERBATIM on the next turn. If
        # they get lost, Gemini rejects the tool call: "Function call is
        # missing a thought_signature in functionCall parts."
        if extra := call.get("extra"):
            block["saglayici"] = dict(extra)
        blocks.append(block)
    return blocks


def parse_arguments(raw: str) -> dict[str, Any]:
    """Parses tool arguments, repairing small models' frequent mistakes.

    Local models often wrap the arguments in a markdown fence or leave
    them half-finished. If unparseable, an empty dict is returned: the
    tool then gives an instructive "required field missing" error and the
    model fixes it on the next turn — better than dropping the request.
    """
    text = (raw or "").strip()
    if not text:
        return {}

    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    for candidate in (text, text[text.find("{") : text.rfind("}") + 1]):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    return {}


def map_finish_reason(reason: str | None) -> str:
    return FINISH_REASONS.get(reason or "", "end_turn")


# -- tool calls leaking into text --------------------------------------
#
# Some local models produce the tool call not in the `tool_calls` field but
# inside plain text. When the server does not parse it, the call never runs
# and the raw tags are shown to the user as an answer. Two forms were seen:
#
#   <tool_call>{"name": "x", "arguments": {...}}</tool_call>
#   <tool_call><function=x><parameter=k>v</parameter></function></tool_call>

_TOOL_CALL = re.compile(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", re.S)
_FUNCTION = re.compile(r"<function=([\w.\-]+)>\s*(.*?)\s*(?:</function>|$)", re.S)
_PARAMETER = re.compile(r"<parameter=([\w.\-]+)>\s*(.*?)\s*(?:</parameter>|$)", re.S)


def extract_inline_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Separates tool calls embedded in text.

    Returns the cleaned text and the calls found. An unparseable block is
    not left in the text: showing the user raw tags is bad in every case.
    """
    if "<tool_call>" not in text and "<function=" not in text:
        return text, []

    calls: list[dict[str, Any]] = []

    def take(match: re.Match[str]) -> str:
        body = match.group(1)
        parsed = _as_call(body)
        if parsed is not None:
            calls.append(parsed)
        return ""

    cleaned = _TOOL_CALL.sub(take, text)
    # Some also produce <function=...> directly, without the fence.
    cleaned = _FUNCTION.sub(lambda m: take_function(m, calls), cleaned)
    return cleaned.strip(), calls


def take_function(match: re.Match[str], calls: list[dict[str, Any]]) -> str:
    calls.append({"name": match.group(1), "arguments": _params(match.group(2))})
    return ""


def _as_call(body: str) -> dict[str, Any] | None:
    if (inner := _FUNCTION.search(body)) is not None:
        return {"name": inner.group(1), "arguments": _params(inner.group(2))}

    parsed = parse_arguments(body)
    name = parsed.get("name") or parsed.get("function")
    if not name:
        return None
    arguments = parsed.get("arguments") or parsed.get("parameters") or {}
    if isinstance(arguments, str):
        arguments = parse_arguments(arguments)
    return {"name": str(name), "arguments": arguments if isinstance(arguments, dict) else {}}


def _params(body: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name, raw in _PARAMETER.findall(body):
        text = raw.strip()
        # If numbers and booleans arrive as strings, the tool schema rejects them.
        if text.lower() in ("true", "false"):
            values[name] = text.lower() == "true"
        elif re.fullmatch(r"-?\d+", text):
            values[name] = int(text)
        else:
            values[name] = text
    return values
