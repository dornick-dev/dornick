"""Anthropic blok biçimi ile OpenAI sohbet biçimi arasında çeviri.

İki biçim araç çağrılarını farklı yerlerde taşır:

    Anthropic   asistan içeriğinde tool_use bloğu
                kullanıcı içeriğinde tool_result bloğu
    OpenAI      asistan mesajında tool_calls dizisi
                ayrı bir role="tool" mesajı, tool_call_id ile

OpenAI tarafında sıralama katıdır: tool mesajları, kendilerini isteyen
tool_calls'lu asistan mesajını **doğrudan** izlemek zorundadır. Araya bir
user mesajı girerse sunucu reddeder. Bu yüzden bir kullanıcı turunda hem
tool_result hem metin varsa, önce tool mesajları yazılır.

Bu modül saf fonksiyonlardan oluşur ve ağ erişimi yoktur — biçim hataları
en sinsi hata sınıfı olduğu için ayrı test edilebilmesi önemli.
"""

from __future__ import annotations

import json
import re
from typing import Any

Block = dict[str, Any]
Message = dict[str, Any]

# Anthropic'e özgü, OpenAI karşılığı olmayan bloklar. Sessizce düşürülür:
# yerel modeller bunları anlamaz ve göndermek hataya yol açar.
DROPPED_BLOCK_TYPES = frozenset({"thinking", "redacted_thinking"})

IMAGE_IN_TOOL_RESULT = "[görüntü — bu sağlayıcı araç sonucunda görüntü kabul etmiyor]"

FINISH_REASONS = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


# -- giden yön: Anthropic -> OpenAI ------------------------------------


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
            out.append({"role": "system", "content": _flatten_text(content)})
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
            tool_calls.append(
                {
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                    },
                }
            )

    message: Message = {"role": "assistant", "content": "\n".join(t for t in texts if t) or None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _user_messages(content: list[Block]) -> list[Message]:
    results = [b for b in content if b.get("type") == "tool_result"]
    rest = [b for b in content if b.get("type") != "tool_result"]

    # Araç sonuçları önce: asistanın tool_calls mesajını doğrudan izlemeliler.
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
    # Tek metin parçası varsa düz dize gönder: bazı uyumlu sunucular dizi
    # biçimini yalnızca görüntü varken kabul ediyor.
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


def to_openai_tools(tools: list[Block]) -> list[Message]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


# -- dönen yön: OpenAI -> Anthropic ------------------------------------


def to_anthropic_blocks(text: str, tool_calls: list[dict[str, Any]]) -> list[Block]:
    blocks: list[Block] = []
    if text.strip():
        blocks.append({"type": "text", "text": text})
    for index, call in enumerate(tool_calls):
        blocks.append(
            {
                "type": "tool_use",
                # Bazı uyumlu sunucular id göndermiyor; eksikse üretiyoruz,
                # çünkü tool_result eşleşmesi buna dayanıyor.
                "id": call.get("id") or f"call_{index}",
                "name": call.get("name", ""),
                "input": parse_arguments(call.get("arguments", "")),
            }
        )
    return blocks


def parse_arguments(raw: str) -> dict[str, Any]:
    """Araç argümanlarını çözer, küçük modellerin sık hatalarını onarır.

    Yerel modeller argümanları sık sık markdown çitiyle sarar ya da yarım
    bırakır. Çözülemezse boş sözlük döner: araç o zaman "zorunlu alan eksik"
    diye öğretici bir hata verir ve model bir sonraki turda düzeltir —
    isteği düşürmekten iyidir.
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


# -- metne sizan arac cagrilari ----------------------------------------
#
# Bazi yerel modeller arac cagrisini `tool_calls` alaninda degil, duz metin
# icinde uretiyor. Sunucu bunu ayristirmadiginda cagri hic calismiyor ve ham
# etiketler kullaniciya cevap gibi gosteriliyor. Iki bicim gorulduu:
#
#   <tool_call>{"name": "x", "arguments": {...}}</tool_call>
#   <tool_call><function=x><parameter=k>v</parameter></function></tool_call>

_TOOL_CALL = re.compile(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", re.S)
_FUNCTION = re.compile(r"<function=([\w.\-]+)>\s*(.*?)\s*(?:</function>|$)", re.S)
_PARAMETER = re.compile(r"<parameter=([\w.\-]+)>\s*(.*?)\s*(?:</parameter>|$)", re.S)


def extract_inline_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Metne gomulu arac cagrilarini ayirir.

    Geriye temizlenmis metin ve bulunan cagrilar doner. Cozulemeyen bir blok
    metinde birakilmaz: kullaniciya ham etiket gostermek her durumda kotu.
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
    # Cit olmadan dogrudan <function=...> uretenler de var.
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
        # Sayi ve mantiksal degerler dize olarak gelirse arac semasi reddeder.
        if text.lower() in ("true", "false"):
            values[name] = text.lower() == "true"
        elif re.fullmatch(r"-?\d+", text):
            values[name] = int(text)
        else:
            values[name] = text
    return values
