"""Scheduled tasks.

Two things can silently break here: a task never firing, and the same
task firing back-to-back. Neither raises an error — one never happens,
the other happens too much.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.schedule import MIN_INTERVAL_S, Schedule, Task, next_after, run_forever, validate


def task(**changes) -> Task:
    base = {"id": "", "title": "deneme", "prompt": "borsayı kontrol et"}
    return Task(**{**base, **changes})


@pytest.fixture()
def book(tmp_path: Path) -> Schedule:
    return Schedule(tmp_path)


# -- validation --------------------------------------------------------


def test_an_empty_prompt_is_refused() -> None:
    """An empty task is a task that silently does no work."""
    with pytest.raises(ValueError):
        validate(task(prompt="   "))


def test_too_frequent_is_refused() -> None:
    """An agent turn triggered every minute is both cost and noise."""
    with pytest.raises(ValueError):
        validate(task(kind="every", every_s=5))


def test_a_broken_clock_is_refused() -> None:
    with pytest.raises(ValueError):
        validate(task(kind="daily", at="sabah"))


def test_an_unknown_repeat_is_refused() -> None:
    with pytest.raises(ValueError):
        validate(task(kind="cron"))


# -- timing ------------------------------------------------------------


def test_interval_counts_from_now() -> None:
    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    assert next_after(task(kind="every", every_s=1800), now) == now + timedelta(minutes=30)


def test_daily_uses_local_time() -> None:
    """When the user says "9 in the morning" they mean their own clock, not UTC."""
    now = datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
    when = next_after(task(kind="daily", at="09:00"), now.astimezone(timezone.utc))

    assert when.astimezone().hour == 9
    assert when > now.astimezone(timezone.utc)


def test_a_time_that_already_passed_goes_to_tomorrow() -> None:
    now = datetime.now().astimezone().replace(hour=22, minute=0, second=0, microsecond=0)
    when = next_after(task(kind="daily", at="09:00"), now.astimezone(timezone.utc))

    assert when.astimezone().day != now.day or when.astimezone() > now


# -- ledger ------------------------------------------------------------


def test_a_new_task_gets_an_id_and_a_first_run(book: Schedule) -> None:
    created = book.add(task())

    assert created.id and created.next_run
    assert book.get(created.id) is not None


def test_tasks_survive_a_restart(book: Schedule, tmp_path: Path) -> None:
    book.add(task(title="sabah raporu", kind="daily", at="09:00"))

    again = Schedule(tmp_path)
    assert [t.title for t in again.all()] == ["sabah raporu"]


def test_nothing_is_due_before_its_time(book: Schedule) -> None:
    book.add(task(kind="every", every_s=3600))
    assert book.due() == []


def test_a_ripe_task_fires_once(book: Schedule) -> None:
    """The next time is advanced at trigger time, not after running: if
    the job runs long the same task must not fire a second time."""
    created = book.add(task(kind="every", every_s=MIN_INTERVAL_S))
    later = datetime.now(timezone.utc) + timedelta(hours=1)

    assert [t.id for t in book.due(later)] == [created.id]
    assert book.due(later) == []   # no longer ripe on a second look


def test_a_paused_task_never_fires(book: Schedule) -> None:
    created = book.add(task(kind="every", every_s=MIN_INTERVAL_S))
    book.update(created.id, enabled=False)

    assert book.due(datetime.now(timezone.utc) + timedelta(days=1)) == []


def test_changing_the_timing_moves_the_next_run(book: Schedule) -> None:
    """The new setting must not stay inert until the next trigger."""
    created = book.add(task(kind="every", every_s=7200))
    before = created.next_run

    updated = book.update(created.id, every_s=MIN_INTERVAL_S)
    assert updated is not None and updated.next_run < before


def test_removing_a_task(book: Schedule) -> None:
    created = book.add(task())
    assert book.remove(created.id)
    assert not book.remove(created.id)


def test_mark_running_binds_child_and_status(book: Schedule) -> None:
    """The ledger is bound so the detail panel gets 'koşuyor' + the report id."""
    created = book.add(task())
    book.mark_running(created.id, "ab12cd")
    got = book.get(created.id)
    assert got is not None
    assert got.last_child_id == "ab12cd"
    assert got.last_status == "koşuyor"
    book.note_run(created.id, "bitti")
    assert book.get(created.id).last_status == "bitti"
    assert book.get(created.id).last_child_id == "ab12cd"


def test_update_can_change_prompt_in_place(book: Schedule) -> None:
    """One should not have to delete and re-add."""
    created = book.add(task(prompt="eski metin"))
    updated = book.update(created.id, prompt="yeni metin", title="yeni ad")
    assert updated is not None
    assert updated.prompt == "yeni metin"
    assert updated.title == "yeni ad"
    assert updated.id == created.id


def test_the_id_cannot_be_overwritten(book: Schedule) -> None:
    created = book.add(task())
    book.update(created.id, id="baska")

    assert book.get(created.id) is not None


def test_a_hand_edited_file_does_not_break_startup(tmp_path: Path) -> None:
    """The file can be hand-edited; an unknown field must not render the
    program unable to open."""
    (tmp_path / "tasks.json").write_text(
        '[{"id": "job_1", "title": "x", "prompt": "y", "uydurma": 1}, "cop", {}]',
        encoding="utf-8",
    )
    assert [t.id for t in Schedule(tmp_path).all()] == ["job_1"]


def test_a_corrupt_file_is_survived(tmp_path: Path) -> None:
    (tmp_path / "tasks.json").write_text("bu json degil", encoding="utf-8")
    assert Schedule(tmp_path).all() == []


def test_the_description_reads_in_plain_turkish(book: Schedule) -> None:
    assert book.add(task(kind="daily", at="09:00")).describe() == "her gün 09:00"
    assert book.add(task(kind="every", every_s=3600)).describe() == "her 1 saatte"
    assert book.add(task(kind="every", every_s=900)).describe() == "her 15 dakikada"


# -- loop --------------------------------------------------------------


async def test_the_ticker_hands_ripe_tasks_to_the_queue(book: Schedule) -> None:
    """A triggered task does not run directly, it enters the queue: it
    must not barge in while the agent is mid-job."""
    # `add` computes the next moment itself; it is overwritten afterwards
    # to pull it into the past, otherwise the task would fire an hour later.
    created = book.add(task(kind="every", every_s=MIN_INTERVAL_S))
    book.update(created.id, next_run="2000-01-01T00:00:00+00:00")
    queued: list[Task] = []
    rounds = 0

    async def once(_seconds: float) -> None:
        nonlocal rounds
        rounds += 1
        if rounds > 1:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_forever(book, queued.append, sleep=once)

    assert [t.title for t in queued] == ["deneme"]


async def test_one_failing_task_does_not_stop_the_ticker(book: Schedule) -> None:
    created = book.add(task(title="patlayan"))
    book.update(created.id, next_run="2000-01-01T00:00:00+00:00")
    rounds = 0

    def boom(_task: Task) -> None:
        raise RuntimeError("kuyruk kapalı")

    async def once(_seconds: float) -> None:
        nonlocal rounds
        rounds += 1
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_forever(book, boom, sleep=once)

    assert rounds == 1
    assert book.all()[0].last_status == "başlatılamadı"


def test_overdue_peeks_without_advancing(book: Schedule) -> None:
    """Missed tasks must keep next_run fixed until the user decides."""
    created = book.add(task(kind="every", every_s=MIN_INTERVAL_S))
    book.update(created.id, next_run="2000-01-01T00:00:00+00:00")
    moment = datetime.now(timezone.utc)

    assert [t.id for t in book.overdue(moment)] == [created.id]
    assert book.get(created.id).next_run == "2000-01-01T00:00:00+00:00"
    assert book.overdue(moment) == book.overdue(moment)


def test_skip_occurrence_advances_to_next_slot(book: Schedule) -> None:
    created = book.add(task(kind="every", every_s=MIN_INTERVAL_S))
    book.update(created.id, next_run="2000-01-01T00:00:00+00:00")
    before = created.next_run
    moment = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)

    assert book.skip_occurrence(created.id, moment)
    got = book.get(created.id)
    assert got is not None
    assert got.next_run != before
    assert got.last_status == "atlandı"
    assert book.overdue(moment) == []


def test_due_only_claims_requested_ids(book: Schedule) -> None:
    a = book.add(task(title="a", kind="every", every_s=MIN_INTERVAL_S))
    b = book.add(task(title="b", kind="every", every_s=MIN_INTERVAL_S))
    book.update(a.id, next_run="2000-01-01T00:00:00+00:00")
    book.update(b.id, next_run="2000-01-01T00:00:00+00:00")
    moment = datetime(2000, 1, 2, tzinfo=timezone.utc)

    fired = book.due(moment, only=[a.id])
    assert [t.id for t in fired] == [a.id]
    assert book.overdue(moment) == [book.get(b.id)]


async def test_ticker_waits_while_paused(book: Schedule) -> None:
    created = book.add(task(kind="every", every_s=MIN_INTERVAL_S))
    book.update(created.id, next_run="2000-01-01T00:00:00+00:00")
    queued: list[Task] = []
    gate = {"on": True}
    rounds = 0

    async def once(_seconds: float) -> None:
        nonlocal rounds
        rounds += 1
        if rounds > 1:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_forever(book, queued.append, sleep=once,
                          paused=lambda: gate["on"])

    assert queued == []
    gate["on"] = False
    rounds = 0
    with pytest.raises(asyncio.CancelledError):
        await run_forever(book, queued.append, sleep=once,
                          paused=lambda: gate["on"])
    assert [t.id for t in queued] == [created.id]


# -- tool --------------------------------------------------------------


async def test_the_agent_can_set_up_an_automation(tmp_path: Path, book: Schedule) -> None:
    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.tools import ToolContext, ToolRegistry
    from dornick.tools import jobs

    registry = ToolRegistry()
    jobs.register(registry)
    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
        cancel=asyncio.Event(),
        schedule=book,
    )

    result = await registry.get("schedule").handler(
        {"action": "add", "title": "sabah", "prompt": "borsayı özetle",
         "kind": "daily", "at": "09:00"},
        ctx,
    )

    assert not result.is_error
    assert [t.title for t in book.all()] == ["sabah"]

    listing = await registry.get("schedule").handler({"action": "list"}, ctx)
    assert "her gün 09:00" in listing.content


async def test_the_agent_can_bind_a_workflow_to_a_schedule(
    tmp_path: Path, book: Schedule
) -> None:
    """The automation's load-bearing seam: a WORKFLOW must be bindable to time.

    With this seam broken everything looked like it worked — the scheduler
    carried the `kind_ui`/`workflow_id` fields, the runner branched on
    them, the UI showed a filter and a badge. But no path could WRITE
    those two fields: not the tool, not the API. The result was a feature
    nobody could set up and a branch never entered.
    """
    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.tools import ToolContext, ToolRegistry
    from dornick.tools import jobs

    registry = ToolRegistry()
    jobs.register(registry)
    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
        cancel=asyncio.Event(),
        schedule=book,
    )
    tool = registry.get("schedule").handler

    result = await tool(
        {"action": "add", "title": "sabah postası", "kind": "daily",
         "at": "08:30", "workflow_id": "posta-ozeti"},
        ctx,
    )
    assert not result.is_error, result.content
    (installed,) = book.all()
    assert installed.kind_ui == "automation"
    assert installed.workflow_id == "posta-ozeti"
    # In an automation the prompt is not a carrier field: empty must not be an error.
    assert installed.prompt == ""

    # Binding a workflow must change the type too — no inconsistent record
    # like "not an automation but has a workflow" may remain.
    simple = book.add(task(title="düz görev"))
    assert simple.kind_ui == "simple"
    updated = await tool(
        {"action": "update", "id": simple.id, "workflow_id": "baska-akis"}, ctx)
    assert not updated.is_error, updated.content
    assert book.get(simple.id).kind_ui == "automation"


def test_an_automation_without_a_flow_is_refused() -> None:
    """An automation without a workflow is a record that does nothing when triggered."""
    with pytest.raises(ValueError, match="akış kimliği"):
        validate(task(prompt="", kind_ui="automation"))
    # The rule for a simple task is unchanged: the text is still required.
    with pytest.raises(ValueError, match="Boş görev metni"):
        validate(task(prompt=""))


async def test_the_tool_says_so_when_there_is_no_scheduler(tmp_path: Path) -> None:
    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.tools import ToolContext, ToolRegistry
    from dornick.tools import jobs

    registry = ToolRegistry()
    jobs.register(registry)
    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
        cancel=asyncio.Event(),
    )

    result = await registry.get("schedule").handler({"action": "list"}, ctx)
    assert result.is_error
