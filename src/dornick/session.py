"""Session: projects the event log onto the API message list.

The API is stateless — the whole history is re-sent every turn. There is no
such thing as "memory"; there is the list kept here. This class is the sole
owner of that list.

Two strict API rules are enforced here:

  1. The results of *all* tool_use blocks in an assistant turn must come
     back in *a single* user message. Splitting them across messages quietly
     trains the model not to call tools in parallel.
  2. No tool_use may be left unanswered. If one is, the next request gets a
     400. Even on interrupt (ESC) a cancellation result must be injected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import compaction
from .events import Event, EventLog

Block = dict[str, Any]

# The marker context compaction leaves behind. The message projection starts
# from here; the log itself stays untouched.
HORIZON = "context_reset"


@dataclass(slots=True)
class PendingToolUse:
    id: str
    name: str
    input: dict[str, Any]


class Session:
    def __init__(self, log: EventLog, session_id: str) -> None:
        self.log = log
        self.id = session_id

    # -- factory -------------------------------------------------------

    @classmethod
    def create(cls, sessions_dir: Path) -> Session:
        base = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # The id has second resolution: if two sessions open within the same
        # second (e.g. the new-conversation button right after startup) both
        # would write to the same file and the "new" conversation would pile
        # onto the old one. On collision a short suffix is appended — the
        # format is not broken, uniqueness is guaranteed.
        session_id = base
        for suffix in range(1, 100):
            if not (sessions_dir / f"{session_id}.jsonl").exists():
                break
            session_id = f"{base[:-1]}-{suffix}Z"
        path = sessions_dir / f"{session_id}.jsonl"
        log = EventLog(path)
        log.note("session_start", session_id=session_id)
        return cls(log, session_id)

    @classmethod
    def resume(cls, path: Path) -> Session:
        log = EventLog(path)
        log.note("session_resume")
        return cls(log, path.stem)

    @classmethod
    def latest(cls, sessions_dir: Path) -> Session | None:
        """The session `--resume` continues: the most recently USED one.

        Sorting by name gave the most recently OPENED one. The two are
        usually the same session — but not when the user went back to an
        older conversation in history and continued from there: in that
        case a restart threw the user into another conversation they had
        left in the first half of the day. Since the file is written on
        every event, mtime means "last activity".
        """
        files = list(sessions_dir.glob("*.jsonl"))
        if not files:
            return None
        # On equal mtime the name is the second key: the order must not be ambiguous.
        return cls.resume(max(files, key=lambda p: (p.stat().st_mtime, p.name)))

    # -- writing -------------------------------------------------------

    def add_user_text(self, text: str) -> None:
        self.log.message("user", [{"type": "text", "text": text}])

    def add_user_blocks(self, blocks: list[Block], *, internal: bool = False) -> None:
        """Adds blocks to a user turn.

        `internal` is for turns the user did not write: an image coming from
        a tool or a note the harness added. The UI does not show these in
        the chat — text the user did not write looks like a reply.
        """
        self.log.message("user", blocks, internal=internal)

    def add_assistant(self, content: Iterable[Any], **meta: Any) -> None:
        """Stores the API response's content as-is.

        No block is edited, thinking blocks included — the API rejects
        modified blocks and all of them must go back while continuing on the
        same model.
        """
        self.log.message("assistant", blocks_to_dicts(content), **meta)

    def add_tool_results(self, results: list[Block]) -> None:
        """Adds all tool results as ONE user message."""
        if not results:
            return
        self.log.message("user", results, tool_results=True)

    def add_system_note(self, text: str) -> None:
        """Mid-conversation operator directive.

        Goes into messages[] as role="system" (Opus 4.8). Using this instead
        of editing the top-level system field preserves the cache and the
        channel cannot be spoofed: text embedded in user content can be
        forged, role="system" cannot.

        Constraint: it cannot be the first message and must follow a user message.
        """
        if not self._can_take_system_note():
            self.log.note("system_note_skipped", text=text)
            return
        self.log.message("system", text)

    def add_harness_note(self, text: str) -> None:
        """The harness's mid-turn note: a helper finished, the user interjected.

        Differs from `add_system_note` in two places:
          * It is not lost. A system note must follow a user message; if
            that does not hold (e.g. two notes back to back) this note goes
            in through the user channel — it is not dropped.
          * It is invisible. The `internal` flag keeps it hidden in the UI:
            text the user did not write must not sit in the chat like a
            message (the interjecting message's bubble was already drawn by
            the `araya` event).
        """
        if self._can_take_system_note():
            self.log.message("system", text, internal=True)
        else:
            self.log.message("user", [{"type": "text", "text": text}], internal=True)

    def add_continuation_note(self, text: str) -> None:
        """Nudge to continue a reply that hit the ceiling.

        `add_system_note` cannot be used here: a system note must follow a
        user message, whereas after the cut-off turn the last message is
        the assistant's own. So it goes through the user channel.

        The `continuation` flag is for the UI: a message the user did not
        write must not look like a user message in the chat.
        """
        self.log.message("user", [{"type": "text", "text": text}], continuation=True)

    # -- reading -------------------------------------------------------

    def messages(self) -> list[dict[str, Any]]:
        """The message list going to the API.

        The log is never shortened — compaction only leaves a horizon marker
        and this projection starts from there. The raw truth keeps sitting
        on disk: extracting a past-session summary, hunting for an error and
        re-weaving the mind are all done from that file.
        """
        horizon = self._horizon()
        if horizon is None:
            return [{"role": e.role, "content": e.content} for e in self.log.messages()]

        return [
            compaction.carry_over(str(horizon.meta.get("summary", ""))),
            *(
                {"role": e.role, "content": e.content}
                for e in self.log.messages()
                if e.seq >= int(horizon.meta.get("from_seq", 0))
            ),
        ]

    def _horizon(self) -> Event | None:
        """The latest context compaction. If none, the window is open from the session start."""
        marks = self.log.notes(HORIZON)
        return marks[-1] if marks else None

    def _live_events(self) -> list[Event]:
        """The message events sitting in the current window."""
        events = self.log.messages()
        if (horizon := self._horizon()) is None:
            return events
        floor = int(horizon.meta.get("from_seq", 0))
        return [e for e in events if e.seq >= floor]

    # -- compaction ----------------------------------------------------

    def compaction_plan(self, *, keep: int = compaction.KEEP_MESSAGES) -> tuple[int, str] | None:
        """Prepares what will be summarised: (seq of the first kept message, transcript).

        None means there is no safe cut point — not enough completed turns
        have accumulated in the window to cut yet.
        """
        events = self._live_events()
        projected = [{"role": e.role, "content": e.content} for e in events]
        cut = compaction.cut_point(projected, keep=keep)
        if cut <= 0:
            # Middle of a single run: the real user turn may only be at the
            # start. Cutting at an assistant boundary is also safe — a long
            # job does not have to die because the window filled.
            cut = compaction.work_cut(projected, keep=keep)
        if cut <= 0:
            return None
        return events[cut].seq, compaction.transcript(projected[:cut])

    def compact(self, summary: str, from_seq: int) -> None:
        """Puts the window behind the summary.

        No deletion: only where the projection starts is marked.
        """
        self.log.note(HORIZON, summary=summary, from_seq=from_seq)

    def pending_tool_uses(self) -> list[PendingToolUse]:
        """tool_use blocks whose result has not come back yet.

        Looks at the last assistant turn; works out which tool_use_ids were
        answered in the user turn that follows. Used to produce cancellation
        results for the missing ones after an interrupt.
        """
        msgs = self.log.messages()
        if not msgs:
            return []

        last_assistant = next((e for e in reversed(msgs) if e.role == "assistant"), None)
        if last_assistant is None:
            return []

        requested = [
            PendingToolUse(id=b["id"], name=b["name"], input=b.get("input") or {})
            for b in last_assistant.content
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if not requested:
            return []

        answered: set[str] = set()
        for e in msgs:
            if e.seq <= last_assistant.seq or e.role != "user":
                continue
            for b in e.content if isinstance(e.content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    answered.add(b.get("tool_use_id", ""))

        return [t for t in requested if t.id not in answered]

    def block_count(self) -> int:
        total = 0
        for e in self.log.messages():
            total += len(e.content) if isinstance(e.content, list) else 1
        return total

    def _can_take_system_note(self) -> bool:
        msgs = self._live_events()
        return bool(msgs) and msgs[-1].role == "user"

    def close(self) -> None:
        self.log.note("sonuc", sonuc=self.outcome())
        self.log.note("session_end")
        self.log.close()

    def outcome(self) -> str:
        """How did the session end? The night replay's prioritisation looks at this.

        Four values, all derived from traces already sitting in the log:

            basarisiz   the last verification tool broke or a tool errored
            duzeltildi  the user corrected — a `lesson` was written or a
                        record was superseded
            acik        a goal was left open
            basarili    if none of the above

        `basarisiz` and `duzeltildi` are the sessions that teach the most
        (Mattar-Daw: gain × need); the night replays them first.
        """
        last_error = False
        for event in self.log.notes("tool_end"):
            last_error = bool(event.meta.get("error"))
        if last_error:
            return "basarisiz"
        for event in self.log.notes("mind_write"):
            if event.meta.get("kind") == "lesson" or event.meta.get("supersedes"):
                return "duzeltildi"
        open_goals = {o.meta.get("goal_id") for o in self.log.notes("goal_push")}
        open_goals -= {o.meta.get("goal_id") for o in self.log.notes("goal_status")}
        return "acik" if open_goals else "basarili"


def blocks_to_dicts(content: Iterable[Any]) -> list[Block]:
    """Turns SDK block objects into dicts that can be sent back to the API."""
    out: list[Block] = []
    for block in content:
        if isinstance(block, dict):
            out.append(block)
        elif hasattr(block, "model_dump"):
            out.append(block.model_dump(exclude_none=True))
        else:
            raise TypeError(f"Beklenmeyen içerik bloğu: {type(block).__name__}")
    return out


def cancelled_result(tool_use_id: str, reason: str = "Kullanıcı işlemi kesti.") -> Block:
    """The mandatory cancellation result for a tool_use left unanswered after an interrupt."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": reason,
        "is_error": True,
    }
