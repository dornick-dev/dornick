"""Görev Durdur: hayalet koşuyor + ajan kapısında beklerken kesme."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from neocp.desktop import Bridge
from neocp.loop import ChildHandle
from neocp.schedule import Schedule, Task
from tests.test_loop import FakeClient, build_agent, registry, text_turn  # noqa: F401


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, ev: dict) -> None:
        self.events.append(ev)


@pytest.mark.asyncio
async def test_gorev_durdur_clears_ghost_running_schedule(
    tmp_path: Path, registry,
) -> None:
    """last_status=koşuyor ama çocuk yok → Durdur kaydı temizler."""
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

    result = await asyncio.to_thread(bridge.gorev_durdur, "c:dead01")
    assert result.get("ok") is True
    assert result.get("cleared") is True
    assert book.get("job_ml").last_status == "kesildi"


@pytest.mark.asyncio
async def test_gorev_durdur_archives_meter_on_stop(
    tmp_path: Path, registry,
) -> None:
    """Durdur: Son koşu'ya süre/token/araç diskte kalsın."""
    from neocp import task_runs

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
        arka_plan=True, sessiz=True, schedule_id="job_ml2",
        baslangic_ts=__import__("time").time() - 125,
        son_arac="web_search", son_hedef="BIST",
        tools_count=7,
        usage={"girdi": 8000, "cikti": 400, "cagri": 5},
    )
    run = task_runs.start_run(
        state, "job_ml2", title="Market Lens", child_id="live01")
    handle.run_id = run.id
    agent._register_child(handle)

    bridge = Bridge(_Hub(), asyncio.get_running_loop())
    bridge.agent = agent

    result = await asyncio.to_thread(bridge.gorev_durdur, "c:live01")
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
    """Kapı doluyken sıradaki yardımcı Durdur ile bitsin."""
    agent = build_agent(tmp_path, FakeClient(text_turn("ok")), registry)
    # Kapıyı kilitle: semafor 0.
    agent._agent_gate = asyncio.Semaphore(0)

    handle = ChildHandle(
        id="gate1", title="sırada", model="m", arka_plan=True, sessiz=True,
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
