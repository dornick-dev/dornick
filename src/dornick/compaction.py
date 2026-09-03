"""What happens when the context fills up.

The model window is finite, the conversation is not. When the window fills
there are three options: drop (throw away the oldest — the agent forgets
why it is there), refuse ("context full, open a new session" — cutting the
user's work in half) or **summarise and carry on**. The third is done here.

Compaction writes to two places at once, and that is the whole idea:

    to the context   the summary becomes the first message of the new window — the conversation is not cut
    to the mind      the same summary lands in persistent memory — it survives the session closing

Without the second, compaction would just be controlled forgetting. Because
it is also written to the mind, a word passing in an unrelated conversation
months later can bring this summary back by association.

The cut point cannot be picked at random. The API requires two things: every
tool_use must receive its result and the window must start with a user
turn. That is why the cut always falls in front of a real user message —
user turns carrying tool results cannot be cut points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Message = dict[str, Any]

# Compaction triggers when this fraction of the window is full. Waiting
# until the ceiling does not work: the summary request itself must also
# fit in the window.
PRESSURE = 0.75

# Minimum number of messages carried over verbatim after compaction. The
# summary says "what was discussed", these messages say "what just happened".
KEEP_MESSAGES = 6

SUMMARY_SYSTEM = """Sen bir oturum özetleyicisin. Sana bir ajan oturumunun
dökümü veriliyor. Görevin, oturumun kaldığı yerden kesintisiz devam
edebilmesi için gereken her şeyi kaydetmek.

Şunları mutlaka koru:
  - kullanıcının ne istediği ve neden istediği
  - alınan kararlar ve gerekçeleri
  - dokunulan dosyalar, komutlar, adresler, kimlikler — birebir
  - denenip işe yaramayan yollar (tekrar denenmesin)
  - şu an yarım kalan iş ve bir sonraki adım

Şunları atla: nezaket cümleleri, tekrarlar, uzun araç çıktılarının gövdesi.

Düz Türkçe yaz, madde madde. Kendinden bahsetme, özetlediğini söyleme —
doğrudan içerikle başla."""

SUMMARY_REQUEST = """Aşağıdaki oturum dökümünü yukarıdaki kurallara göre özetle.

--- DÖKÜM BAŞLANGICI ---
{transcript}
--- DÖKÜM SONU ---"""

# First message of the new window. It says explicitly what it is so the
# model does not mistake it for a user request.
CARRY_OVER = """[önceki bağlamın özeti — konuşma buradan devam ediyor]

{summary}

[özet sonu. Bir soru sorulmadıysa yanıt verme; kaldığın işe devam et.]"""


@dataclass(slots=True)
class Pressure:
    """How much of the window is full."""

    used: int
    window: int

    @property
    def ratio(self) -> float:
        return self.used / self.window if self.window > 0 else 0.0

    @property
    def full(self) -> bool:
        return self.ratio >= PRESSURE

    @property
    def percent(self) -> int:
        return int(self.ratio * 100)


def measure(usage: dict[str, int], window: int) -> Pressure:
    """Derives window fullness from the usage report.

    `prompt_total` is used, not `input_tokens`: the latter counts only the
    residue that did not hit the cache and stays small even when the window
    is full.
    """
    return Pressure(used=int(usage.get("prompt_total") or 0), window=window)


def cut_point(messages: list[Message], *, keep: int = KEEP_MESSAGES) -> int:
    """The index the cut lands on. 0 means there is nothing to compact.

    Walking backwards, we step back far enough to leave `keep` messages and
    from there look forward for the first **real** user message. It must be
    real: a user turn carrying tool results is the continuation of an
    assistant turn, and cutting in front of it leaves an unanswered tool_use.
    """
    if len(messages) <= keep:
        return 0

    for index in range(len(messages) - keep, 0, -1):
        if _is_user_turn(messages[index]):
            return index
    return 0


def work_cut(messages: list[Message], *, keep: int = KEEP_MESSAGES) -> int:
    """Cut for the MIDDLE of a single run: in front of an assistant message.

    In a single run of a hundred tools the only real user turn is at the very
    start — `cut_point` returns 0 and compaction could never run: when the
    window filled, the run died with "open a new session". Yet the front of
    an assistant message is also a safe cut: that message's tool_uses and
    their results stay together in the window, the earlier ones fold into
    the summary together; the carry_over (user) message already opens the
    window anyway.

    `cut_point` is still tried first (a real user turn is a better
    boundary); this is only the fallback for the case it cannot find one.
    """
    if len(messages) <= keep:
        return 0
    for index in range(len(messages) - keep, 0, -1):
        if messages[index].get("role") == "assistant":
            return index
    return 0


def _is_user_turn(message: Message) -> bool:
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return bool(content)
    # A turn carrying a tool result does not count as the user's own turn.
    return not any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )


def transcript(messages: list[Message], *, tool_output_limit: int = 400) -> str:
    """Turns the messages into plain text for the summariser.

    Tool outputs are trimmed: a whole directory listing is noise for the
    summary, not information, but its first lines show which tool was asked
    what.
    """
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "?"))
        for piece in _render(message.get("content"), tool_output_limit):
            lines.append(f"{role}: {piece}")
    return "\n".join(lines)


def _render(content: Any, limit: int) -> list[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []

    out: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            out.append(str(block.get("text", "")))
        elif kind == "tool_use":
            out.append(f"[araç: {block.get('name')} {_short(block.get('input'), 200)}]")
        elif kind == "tool_result":
            out.append(f"[sonuç: {_short(block.get('content'), limit)}]")
        # thinking blocks are skipped: what belongs in the summary is the
        # conclusions, not the road taken to reach them.
    return [piece for piece in out if piece.strip()]


def _short(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + f"… (+{len(text) - limit} karakter)"


def carry_over(summary: str) -> Message:
    """Turns the summary into the first message of the new window."""
    return {"role": "user", "content": [{"type": "text", "text": CARRY_OVER.format(summary=summary)}]}
