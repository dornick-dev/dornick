"""Append-only event log.

This is the single source of truth. The conversation history, the mind
state, the audit trail — all of them are projections of this log. It is
written to disk as JSONL; every line decodes on its own, so the record
stays consistent even if the process dies mid-way.

There are two event families:

    kind="message"  a conversation turn going to the API (user/assistant/system).
                    content keeps the exact block structure the API expects —
                    thinking blocks included, and they must be sent back unchanged.

    kind="meta"     records that never reach the model: permission decision,
                    tool duration, error, context-compaction marker, user
                    interrupt. The audit trail and the mind visualisation read these.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

MESSAGE = "message"
META = "meta"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# Time is read from a single place (see recall/clock.py). The night pass
# looks at the stamps in the session log — which node was touched after
# which, where the ±60 minutes around a surprising event fall — and if
# those stamps came from the wall clock a ninety-day scenario could not be
# measured.
Clock = Callable[[], str]


@dataclass(slots=True)
class Event:
    seq: int
    ts: str
    kind: str
    role: str | None = None
    content: Any = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> Event:
        return cls(**json.loads(line))

    @property
    def is_message(self) -> bool:
        return self.kind == MESSAGE


class EventLog:
    """Line-buffered JSONL writer that stays open for the life of the process."""

    def __init__(self, path: Path, *, clock: Clock | None = None) -> None:
        self.path = path
        self._clock: Clock = clock or utcnow
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._events: list[Event] = list(_read(path)) if path.exists() else []
        self._seq = self._events[-1].seq + 1 if self._events else 0
        self._lock = threading.Lock()
        self._fh = path.open("a", encoding="utf-8", buffering=1)
        self._listeners: list[Callable[[Event], None]] = []

    def subscribe(self, listener: Callable[[Event], None]) -> Callable[[], None]:
        """Listens for new events. The returned callable cancels the subscription.

        The mind UI uses this: everything written to the log streams to the
        browser at the same time. An error in a listener does not block the
        log write — if the UI crashes the agent must keep running.
        """
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    # -- writing -------------------------------------------------------

    def append(
        self,
        kind: str,
        *,
        role: str | None = None,
        content: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> Event:
        """Appends an event.

        meta is deliberately an explicit dict, not **kwargs: otherwise a meta
        field named "kind", "role" or "content" would collide with this
        function's own parameters and the call would fail with TypeError.
        Mind records really do use "kind".
        """
        with self._lock:
            ev = Event(
                seq=self._seq,
                ts=self._clock(),
                kind=kind,
                role=role,
                content=content,
                meta=dict(meta or {}),
            )
            self._seq += 1
            self._events.append(ev)
            self._fh.write(ev.to_json() + "\n")
            # Flush to disk so the last turn is not lost on interrupt/crash.
            self._fh.flush()
            os.fsync(self._fh.fileno())

        for listener in tuple(self._listeners):
            try:
                listener(ev)
            except Exception:  # if the UI crashes the agent must keep running
                pass
        return ev

    def message(self, role: str, content: Any, **meta: Any) -> Event:
        return self.append(MESSAGE, role=role, content=content, meta=meta)

    def note(self, event_type: str, **data: Any) -> Event:
        return self.append(META, content=event_type, meta=data)

    # -- reading -------------------------------------------------------

    def __iter__(self) -> Iterator[Event]:
        return iter(tuple(self._events))

    def __len__(self) -> int:
        return len(self._events)

    def messages(self) -> list[Event]:
        return [e for e in self._events if e.is_message]

    def notes(self, event_type: str | None = None) -> list[Event]:
        out = [e for e in self._events if e.kind == META]
        if event_type is not None:
            out = [e for e in out if e.content == event_type]
        return out

    def tail(self, n: int) -> list[Event]:
        return list(self._events[-n:])

    def close(self) -> None:
        with self._lock:
            if not self._fh.closed:
                self._fh.close()

    def __enter__(self) -> EventLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _read(path: Path) -> Iterator[Event]:
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield Event.from_json(line)
            except (json.JSONDecodeError, TypeError) as exc:
                # Half-written last line: the process may have been killed
                # while writing. Skip quietly, but not silently.
                raise ValueError(f"{path}:{lineno} bozuk olay kaydı: {exc}") from exc
