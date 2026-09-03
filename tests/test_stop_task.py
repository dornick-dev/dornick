"""Stop task: a ghost 'running' entry + cutting a helper waiting at the agent gate."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from dornick.desktop import Bridge
from dornick.loop import ChildHandle
from dornick.schedule import Schedule, Task
from tests.test_loop import FakeClient, build_agent, registry, text_turn  # noqa: F401


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, ev: dict) -> None:
        self.events.append(ev)


@pytest.mark.asyncio
async def test_stop_task_clears_ghost_running_schedule(
    tmp_path: Path, registry,
) -> None:
    """last_status=koşuyor but no child → Stop clears the record."""
    book = Schedule(tmp_path)
    task = Task(
        id="job_ml", title="Market Lens", prompt="tara",
        last_status="koşuyor", last_child_id="dead01",
    )
    book.add(task)

    agent = build_agent(tmp_path, FakeClient(), registry)
    agent.schedule = book
    bridge = Bridge(_Hub(), asyncio.get_running_loop())
    bridge.agent = agent

    result = await asyncio.to_thread(bridge.stop_task, "c:dead01")
    assert result.get("ok") is True
    assert result.get("cleared") is True
    assert book.get("job_ml").last_status == "kesildi"


@pytest.mark.asyncio
async def test_stop_task_archives_meter_on_stop(
    tmp_path: Path, registry,
) -> None:
    """Stop: duration/tokens/tools stay on disk for 'Last run'."""
    from dornick import task_runs

    book = Schedule(tmp_path)
    task = Task(
        id="job_ml2", title="Market Lens", prompt="tara",
        last_status="koşuyor", last_child_id="live01",
    )
    book.add(task)

    agent = build_agent(tmp_path, FakeClient(), registry)
    agent.schedule = book
    state = agent.config.state_dir
    handle = ChildHandle(
        id="live01", title="Market Lens", model="openai/gpt-test",
        background=True, quiet=True, schedule_id="job_ml2",
        started_ts=__import__("time").time() - 125,
        last_tool="web_search", last_goal="BIST",
        tools_count=7,
        usage={"girdi": 8000, "cikti": 400, "cagri": 5},
    )
    run = task_runs.start_run(
        state, "job_ml2", title="Market Lens", child_id="live01")
    handle.run_id = run.id
    agent._register_child(handle)

    bridge = Bridge(_Hub(), asyncio.get_running_loop())
    bridge.agent = agent

    result = await asyncio.to_thread(bridge.stop_task, "c:live01")
    assert result.get("ok") is True

    done = task_runs.get_run(state, "job_ml2", run.id)
    assert done is not None
    assert done.status == "hata"
    assert "Kullanıcı durdurdu" in (done.report or "")
    assert done.usage and done.usage["girdi"] == 8000
    assert done.tools == 7
    assert done.duration_s >= 120
    assert "web_search" in (done.last_tool or "")
    assert "tok" in (done.report or "") or "tur" in (done.report or "")


@pytest.mark.asyncio
async def test_child_waiting_at_agent_gate_can_be_stopped(
    tmp_path: Path, registry,
) -> None:
    """While the gate is full, the queued helper should end via Stop."""
    agent = build_agent(tmp_path, FakeClient(text_turn("ok")), registry)
    # Lock the gate: semaphore 0.
    agent._agent_gate = asyncio.Semaphore(0)

    handle = ChildHandle(
        id="gate1", title="sırada", model="m", background=True, quiet=True,
    )
    agent._register_child(handle)

    async def stopper() -> None:
        await asyncio.sleep(0.05)
        handle.cancel.set()

    stop_task = asyncio.create_task(stopper())
    out = await agent._child_round(handle, "iş yap")
    await stop_task

    assert out == "(kesildi)"
    assert handle.state == "hata"
