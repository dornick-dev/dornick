"""Zamanlanmış görevler.

İki şey burada sessizce bozulabiliyor: bir görevin hiç tetiklenmemesi ve
aynı görevin üst üste tetiklenmesi. İkisi de hata vermiyor — biri hiç
olmuyor, öteki fazla oluyor.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from neocp.schedule import MIN_INTERVAL_S, Schedule, Task, next_after, run_forever, validate


def task(**changes) -> Task:
    base = {"id": "", "title": "deneme", "prompt": "borsayı kontrol et"}
    return Task(**{**base, **changes})


@pytest.fixture()
def book(tmp_path: Path) -> Schedule:
    return Schedule(tmp_path)


# -- doğrulama ---------------------------------------------------------


def test_an_empty_prompt_is_refused() -> None:
    """Boş görev sessizce hiç iş yapmayan bir görevdir."""
    with pytest.raises(ValueError):
        validate(task(prompt="   "))


def test_too_frequent_is_refused() -> None:
    """Dakikada bir tetiklenen bir ajan turu hem maliyet hem gürültü."""
    with pytest.raises(ValueError):
        validate(task(kind="every", every_s=5))


def test_a_broken_clock_is_refused() -> None:
    with pytest.raises(ValueError):
        validate(task(kind="daily", at="sabah"))


def test_an_unknown_repeat_is_refused() -> None:
    with pytest.raises(ValueError):
        validate(task(kind="cron"))


# -- zamanlama ---------------------------------------------------------


def test_interval_counts_from_now() -> None:
    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    assert next_after(task(kind="every", every_s=1800), now) == now + timedelta(minutes=30)


def test_daily_uses_local_time() -> None:
    """Kullanıcı "sabah 9" derken UTC değil kendi saatini kastediyor."""
    now = datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
    when = next_after(task(kind="daily", at="09:00"), now.astimezone(timezone.utc))

    assert when.astimezone().hour == 9
    assert when > now.astimezone(timezone.utc)


def test_a_time_that_already_passed_goes_to_tomorrow() -> None:
    now = datetime.now().astimezone().replace(hour=22, minute=0, second=0, microsecond=0)
    when = next_after(task(kind="daily", at="09:00"), now.astimezone(timezone.utc))

    assert when.astimezone().day != now.day or when.astimezone() > now


# -- defter ------------------------------------------------------------


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
    """Sıradaki zaman tetiklenirken ilerletiliyor, çalıştırıldıktan sonra
    değil: iş uzun sürerse aynı görev ikinci kez tetiklenmemeli."""
    created = book.add(task(kind="every", every_s=MIN_INTERVAL_S))
    later = datetime.now(timezone.utc) + timedelta(hours=1)

    assert [t.id for t in book.due(later)] == [created.id]
    assert book.due(later) == []   # ikinci bakışta artık hazır değil


def test_a_paused_task_never_fires(book: Schedule) -> None:
    created = book.add(task(kind="every", every_s=MIN_INTERVAL_S))
    book.update(created.id, enabled=False)

    assert book.due(datetime.now(timezone.utc) + timedelta(days=1)) == []


def test_changing_the_timing_moves_the_next_run(book: Schedule) -> None:
    """Yeni ayar bir sonraki tetiklenmeye kadar geçersiz kalmamalı."""
    created = book.add(task(kind="every", every_s=7200))
    before = created.next_run

    updated = book.update(created.id, every_s=MIN_INTERVAL_S)
    assert updated is not None and updated.next_run < before


def test_removing_a_task(book: Schedule) -> None:
    created = book.add(task())
    assert book.remove(created.id)
    assert not book.remove(created.id)


def test_the_id_cannot_be_overwritten(book: Schedule) -> None:
    created = book.add(task())
    book.update(created.id, id="baska")

    assert book.get(created.id) is not None


def test_a_hand_edited_file_does_not_break_startup(tmp_path: Path) -> None:
    """Dosya elle düzenlenebiliyor; bilinmeyen alan programı açılmaz hale
    getirmemeli."""
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


# -- döngü -------------------------------------------------------------


async def test_the_ticker_hands_ripe_tasks_to_the_queue(book: Schedule) -> None:
    """Tetiklenen görev doğrudan koşmuyor, kuyruğa giriyor: ajan bir işin
    ortasındayken araya girmemeli."""
    # `add` sıradaki anı kendi hesaplıyor; geçmişe çekmek için sonradan
    # yazılıyor, yoksa görev bir saat sonra tetiklenirdi.
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


# -- araç --------------------------------------------------------------


async def test_the_agent_can_set_up_an_automation(tmp_path: Path, book: Schedule) -> None:
    from neocp.config import Config
    from neocp.events import EventLog
    from neocp.session import Session
    from neocp.tools import ToolContext, ToolRegistry
    from neocp.tools import jobs

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


async def test_the_tool_says_so_when_there_is_no_scheduler(tmp_path: Path) -> None:
    from neocp.config import Config
    from neocp.events import EventLog
    from neocp.session import Session
    from neocp.tools import ToolContext, ToolRegistry
    from neocp.tools import jobs

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
