"""Scheduled tasks.

"Check the market every morning", "prepare the report on Fridays" — these
are jobs the agent can do on its own, but someone has to keep the clock.
This is that clock.

Three design decisions:

    visible    Tasks sit on disk as plain JSON and are listed on the
               settings page. An automation the agent set up running
               hidden from the user is unacceptable — they must be able
               to see what it is, when it runs, and what happened last.
    background A task whose time has come is not a chat bubble: it runs
               as a background helper. The report is in Orchestra /
               Tasks; clicking opens the Viewer. The main chat stays a
               Q&A space.
    quiet      A finished scheduled job does not force the main agent
               into a "report it" turn — it does not spill into the chat
               unless the user asks.

Cron syntax is deliberately absent. Writing the five-star expression
correctly is not the user's job; "every N minutes" and "every day at
HH:MM" cover everything wanted in practice, and both read at a glance.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as clock, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4

TASKS_FILE = "tasks.json"

# Two repeat forms. These instead of a cron expression: easy to read and
# validate, and they cover everything wanted in practice.
KINDS = ("every", "daily")

# A task cannot run more often than this. An agent turn triggered every
# minute is both cost and noise.
MIN_INTERVAL_S = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Task:
    """A single scheduled job.

    prompt: the text sent to the agent. No different from a message the
        user typed — so it must be complete; something like "do it again"
        is useless.
    at: "HH:MM" (local time) for `daily`. Unused for `every`.
    every_s: seconds for `every`.
    """

    id: str
    title: str
    prompt: str
    kind: str = "every"
    every_s: int = 3600
    at: str = "09:00"
    enabled: bool = True
    created: str = field(default_factory=lambda: _now().isoformat(timespec="seconds"))
    last_run: str = ""
    last_status: str = ""
    # Id of the last (or running) helper — "open the report" / status in the detail view.
    last_child_id: str = ""
    # The next trigger; must be persisted, otherwise past tasks re-fire
    # every time the program opens.
    next_run: str = ""
    # UI type: simple = a single prompt; automation = a workflow graph.
    kind_ui: str = "simple"  # simple | automation
    # The bound workflow id when kind_ui=automation; empty for simple.
    workflow_id: str = ""

    def describe(self) -> str:
        if self.kind == "daily":
            return f"her gün {self.at}"
        if self.every_s % 3600 == 0:
            return f"her {self.every_s // 3600} saatte"
        return f"her {max(1, self.every_s // 60)} dakikada"


def validate(task: Task) -> Task:
    """A broken task is a task that silently never runs."""
    if task.kind not in KINDS:
        raise ValueError(f"Bilinmeyen tekrar biçimi: {task.kind}. Geçerli: {', '.join(KINDS)}")
    # The two task types carry different fields: a simple task carries a
    # prompt, an automation a workflow id. Demanding a prompt from
    # automations too pushed callers to invent a meaningless value like
    # `prompt="."` — and that value meant the runner silently executing
    # the "." prompt if the workflow ever went missing.
    if task.kind_ui == "automation":
        if not task.workflow_id.strip():
            raise ValueError("Otomasyon görevi bir akış kimliği (workflow_id) ister.")
    elif not task.prompt.strip():
        raise ValueError("Boş görev metni. Ajana ne söyleneceğini yaz.")
    if task.kind == "every" and task.every_s < MIN_INTERVAL_S:
        raise ValueError(f"En sık {MIN_INTERVAL_S} saniyede bir çalışabilir.")
    if task.kind == "daily":
        _parse_clock(task.at)
    return task


def _parse_clock(text: str) -> clock:
    try:
        hour, minute = (int(p) for p in str(text).split(":", 1))
        return clock(hour=hour, minute=minute)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Saat 'HH:MM' biçiminde olmalı: {text!r}") from exc


def next_after(task: Task, moment: datetime) -> datetime:
    """The first trigger after the given moment.

    `daily` is computed in local time: when the user says "9 in the
    morning" they mean their own clock, not UTC.
    """
    if task.kind == "every":
        return moment + timedelta(seconds=max(MIN_INTERVAL_S, task.every_s))

    wanted = _parse_clock(task.at)
    local = moment.astimezone()
    target = local.replace(hour=wanted.hour, minute=wanted.minute, second=0, microsecond=0)
    if target <= local:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


class Schedule:
    """The owner of the task list.

    Read from both the UI thread and the agent's loop; hence locked, and
    it writes to disk on every change. The list is short (tens of tasks),
    the write cost is negligible.
    """

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / TASKS_FILE
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._load()

    # -- reading -------------------------------------------------------

    def all(self) -> list[Task]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda t: (not t.enabled, t.next_run or "~"))

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def overdue(self, moment: datetime | None = None) -> list[Task]:
        """Overdue tasks — `next_run` is NOT advanced.

        For showing triggers missed while the program was closed: the
        order in the ledger must not change until the user says "do it
        now / skip".
        """
        moment = moment or _now()
        with self._lock:
            ripe = [
                task for task in self._tasks.values()
                if task.enabled and task.next_run
                and datetime.fromisoformat(task.next_run) <= moment
            ]
        return sorted(ripe, key=lambda t: t.next_run or "")

    def due(
        self,
        moment: datetime | None = None,
        *,
        only: Iterable[str] | None = None,
    ) -> list[Task]:
        """Tasks whose time has come. Their next times are advanced too.

        The advance happens here, not after running: if the job runs long
        the same task must not fire a second time.

        `only`: just these ids (for those missed at startup).
        """
        moment = moment or _now()
        want = set(only) if only is not None else None
        fired: list[Task] = []

        with self._lock:
            for task in self._tasks.values():
                if want is not None and task.id not in want:
                    continue
                if not task.enabled or not task.next_run:
                    continue
                if datetime.fromisoformat(task.next_run) > moment:
                    continue
                task.next_run = next_after(task, moment).isoformat(timespec="seconds")
                fired.append(task)
            if fired:
                self._write()
        return fired

    def skip_occurrence(self, task_id: str, moment: datetime | None = None) -> bool:
        """Skip this trigger without running; move to the next slot."""
        moment = moment or _now()
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or not task.enabled or not task.next_run:
                return False
            if datetime.fromisoformat(task.next_run) > moment:
                return False
            task.next_run = next_after(task, moment).isoformat(timespec="seconds")
            task.last_status = "atlandı"
            self._write()
        return True

    # -- writing -------------------------------------------------------

    def add(self, task: Task) -> Task:
        validate(task)
        task.id = task.id or f"job_{uuid4().hex[:8]}"
        task.next_run = next_after(task, _now()).isoformat(timespec="seconds")
        with self._lock:
            self._tasks[task.id] = task
            self._write()
        return task

    def update(self, task_id: str, **changes: Any) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None

            known = set(Task.__dataclass_fields__)
            for name, value in changes.items():
                if name in known and name != "id":
                    setattr(task, name, value)
            validate(task)

            # If the timing changed, the next moment must change too;
            # otherwise the new setting stays inert until the next trigger.
            if {"kind", "every_s", "at", "enabled"} & set(changes):
                task.next_run = next_after(task, _now()).isoformat(timespec="seconds")

            self._write()
            return task

    def remove(self, task_id: str) -> bool:
        with self._lock:
            gone = self._tasks.pop(task_id, None) is not None
            if gone:
                self._write()
        return gone

    def note_run(self, task_id: str, status: str) -> None:
        with self._lock:
            if task := self._tasks.get(task_id):
                task.last_run = _now().isoformat(timespec="seconds")
                task.last_status = status[:200]
                self._write()

    def mark_running(self, task_id: str, child_id: str) -> None:
        """The task got bound to a background helper — the detail panel should show 'koşuyor'."""
        with self._lock:
            if task := self._tasks.get(task_id):
                task.last_child_id = str(child_id or "")
                task.last_run = _now().isoformat(timespec="seconds")
                task.last_status = "koşuyor"
                self._write()

    # -- disk ----------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        known = set(Task.__dataclass_fields__)
        for entry in raw if isinstance(raw, list) else []:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            # Dropping unknown fields keeps a hand-edited file from
            # rendering the program unable to open.
            self._tasks[entry["id"]] = Task(**{k: v for k, v in entry.items() if k in known})

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(t) for t in self._tasks.values()], ensure_ascii=False, indent=2)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(payload, encoding="utf-8")
        temp.replace(self.path)


async def run_forever(
    schedule: Schedule,
    submit: Callable[[Task], None],
    *,
    tick_s: float = 20.0,
    sleep: Callable[[float], Any] | None = None,
    paused: Callable[[], bool] | None = None,
) -> None:
    """Launches due tasks with `submit` (background helper).

    The old path was the chat queue; now `submit` should be
    `run_scheduled` on the bridge — output lands in Orchestra, not the chat.

    `paused`: while True, nothing fires — tasks missed at startup wait
    until the user says "do it now / skip".
    """
    import asyncio

    naptime = sleep or asyncio.sleep
    while True:
        if not (paused and paused()):
            for task in schedule.due():
                try:
                    submit(task)
                except Exception:  # a single task must not bring the scheduler down
                    schedule.note_run(task.id, "başlatılamadı")
        await naptime(tick_s)


def payload(tasks: Iterable[Task]) -> list[dict[str, Any]]:
    """The form sent to the UI: the readable description attached too."""
    return [{**asdict(task), "describe": task.describe()} for task in tasks]
