"""The task-run archive.

The promise: a started run is written to disk, status/report is updated
when it finishes, and list_runs puts the newest first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dornick import task_runs
from dornick.schedule import Schedule, Task


def test_start_and_get_run(tmp_path: Path) -> None:
    run = task_runs.start_run(tmp_path, "job_abc", title="Sabah raporu", child_id="child_1")

    assert run.status == "koşuyor"
    assert run.started
    assert not run.finished

    again = task_runs.get_run(tmp_path, "job_abc", run.id)
    assert again is not None
    assert again.title == "Sabah raporu"
    assert again.child_id == "child_1"

    path = tmp_path / task_runs.FOLDER / "job_abc" / f"{run.id}.json"
    assert path.is_file()


def test_finish_run_archives_report(tmp_path: Path) -> None:
    run = task_runs.start_run(tmp_path, "job_x", title="Borsa")
    done = task_runs.finish_run(
        tmp_path,
        "job_x",
        run.id,
        status="bitti",
        report="BIST %1.2 yükseldi.\n" * 3,
        nodes_progress=[{"id": "n1", "status": "bitti"}],
        model="openai/gpt-4o-mini",
        usage={"girdi": 1200, "cikti": 400, "cagri": 3},
        cost_usd=0.0123,
        tools=12,
        duration_s=273,
        last_tool="browser · open",
    )

    assert done.status == "bitti"
    assert done.finished
    assert "BIST" in done.report
    assert done.nodes_progress and done.nodes_progress[0]["id"] == "n1"
    assert done.model == "openai/gpt-4o-mini"
    assert done.usage == {"girdi": 1200, "cikti": 400, "cagri": 3}
    assert done.cost_usd == pytest.approx(0.0123)
    assert done.tools == 12
    assert done.duration_s == 273
    assert done.last_tool == "browser · open"

    loaded = task_runs.get_run(tmp_path, "job_x", run.id)
    assert loaded is not None
    assert loaded.status == "bitti"
    assert loaded.model == "openai/gpt-4o-mini"
    assert loaded.usage and loaded.usage["cagri"] == 3
    assert loaded.tools == 12
    assert loaded.duration_s == 273
    assert loaded.last_tool == "browser · open"


def test_finish_run_error(tmp_path: Path) -> None:
    run = task_runs.start_run(tmp_path, "job_y")
    failed = task_runs.finish_run(tmp_path, "job_y", run.id, status="hata", report="timeout")
    assert failed.status == "hata"
    assert failed.report == "timeout"


def test_patch_run_updates_live_report(tmp_path: Path) -> None:
    run = task_runs.start_run(tmp_path, "job_live", title="Tarama")
    patched = task_runs.patch_run(
        tmp_path, "job_live", run.id,
        report="Araç: browser · open",
        nodes_progress=[{"id": "n1", "status": "koşuyor", "title": "Tara"}],
        model="gpt-test",
        usage={"girdi": 10, "cikti": 2, "cagri": 1},
    )
    assert patched is not None
    assert patched.status == "koşuyor"
    assert "browser" in patched.report
    assert patched.nodes_progress and patched.nodes_progress[0]["id"] == "n1"
    assert patched.model == "gpt-test"
    assert patched.usage and patched.usage["cagri"] == 1

    task_runs.finish_run(tmp_path, "job_live", run.id, status="bitti", report="bitti")
    assert task_runs.patch_run(tmp_path, "job_live", run.id, report="x") is None


def test_list_runs_newest_first_with_limit(tmp_path: Path) -> None:
    ids = []
    for i in range(5):
        run = task_runs.start_run(tmp_path, "job_z", title=f"tur {i}", run_id=f"run_{i:02d}")
        ids.append(run.id)
        task_runs.finish_run(tmp_path, "job_z", run.id, status="bitti", report=f"ok {i}")

    listed = task_runs.list_runs(tmp_path, "job_z", limit=3)
    assert len(listed) == 3
    # started is ISO — lexical order = time order; newest first.
    assert listed[0].started >= listed[1].started >= listed[2].started


def test_report_is_clipped(tmp_path: Path) -> None:
    run = task_runs.start_run(tmp_path, "job_clip")
    huge = "x" * (task_runs.REPORT_CLIP + 500)
    done = task_runs.finish_run(tmp_path, "job_clip", run.id, status="bitti", report=huge)
    assert len(done.report) <= task_runs.REPORT_CLIP
    assert done.report.endswith("…")


def test_unknown_status_refused(tmp_path: Path) -> None:
    run = task_runs.start_run(tmp_path, "job_bad")
    with pytest.raises(task_runs.TaskRunError):
        task_runs.finish_run(tmp_path, "job_bad", run.id, status="koşuyor")


def test_schedule_task_carries_workflow_fields(tmp_path: Path) -> None:
    """Slice 2: Task.kind_ui / workflow_id defaults and persistence."""
    book = Schedule(tmp_path)
    created = book.add(
        Task(
            id="",
            title="otomasyon",
            prompt="posta özetle",
            kind_ui="automation",
            workflow_id="posta-ozet-a1b2c3d4",
        )
    )
    assert created.kind_ui == "automation"
    assert created.workflow_id == "posta-ozet-a1b2c3d4"

    again = Schedule(tmp_path)
    loaded = again.get(created.id)
    assert loaded is not None
    assert loaded.kind_ui == "automation"
    assert loaded.workflow_id == "posta-ozet-a1b2c3d4"


def test_simple_task_defaults(tmp_path: Path) -> None:
    book = Schedule(tmp_path)
    created = book.add(Task(id="", title="basit", prompt="hava durumu"))
    assert created.kind_ui == "simple"
    assert created.workflow_id == ""
