"""The task-run archive.

Every time a scheduled task fires, a run record is written: when it
started, whether it finished, the helper's id, a short report. The
Orchestra / Tasks panel reads from here — not a chat bubble.

Store: `{state_dir}/task-runs/<task_id>/<run_id>.json`
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .events import utcnow

FOLDER = "task-runs"

# Statuses are Turkish: the panel and the tool use the same words.
STATUSES = ("koşuyor", "bitti", "hata")

# Truncation for the report panel; hoarding without bounds bloats the disk.
REPORT_CLIP = 8000

_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,64}$")


class TaskRunError(Exception):
    """Format / store error."""


@dataclass(slots=True)
class TaskRun:
    id: str
    task_id: str
    started: str = ""
    finished: str = ""
    status: str = "koşuyor"
    child_id: str = ""
    title: str = ""
    report: str = ""
    nodes_progress: list[dict[str, Any]] | None = field(default=None)
    # Same units as the chat dock: model name, tokens, estimated USD.
    model: str = ""
    usage: dict[str, int] | None = field(default=None)
    cost_usd: float | None = None
    # Tool count and duration (s) — so they stay on the board after the app closes.
    tools: int = 0
    duration_s: int = 0
    last_tool: str = ""


def folder(state_dir: Path) -> Path:
    return Path(state_dir) / FOLDER


def _safe_id(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not _ID.match(text):
        raise TaskRunError(f"Geçersiz {label}: {value!r}")
    return text


def _task_dir(state_dir: Path, task_id: str) -> Path:
    tid = _safe_id(task_id, "task_id")
    root = folder(state_dir).resolve()
    target = (root / tid).resolve()
    if target.parent != root:
        raise TaskRunError(f"Geçersiz task_id: {task_id!r}")
    return target


def _run_path(state_dir: Path, task_id: str, run_id: str) -> Path:
    rid = _safe_id(run_id, "run_id")
    parent = _task_dir(state_dir, task_id)
    target = (parent / f"{rid}.json").resolve()
    if target.parent != parent.resolve():
        raise TaskRunError(f"Geçersiz run_id: {run_id!r}")
    return target


def _clip(text: str, limit: int = REPORT_CLIP) -> str:
    flat = str(text or "")
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def parse(raw: Any) -> TaskRun:
    if not isinstance(raw, dict):
        raise TaskRunError("Koşum kaydı bir nesne olmalı.")
    rid = _safe_id(str(raw.get("id") or ""), "id")
    tid = _safe_id(str(raw.get("task_id") or ""), "task_id")
    status = str(raw.get("status") or "koşuyor").strip()
    if status not in STATUSES:
        raise TaskRunError(f"status şunlardan biri olmalı: {', '.join(STATUSES)}")

    progress = raw.get("nodes_progress")
    if progress is not None and not isinstance(progress, list):
        raise TaskRunError("nodes_progress bir liste olmalı.")

    usage_raw = raw.get("usage")
    usage: dict[str, int] | None = None
    if isinstance(usage_raw, dict):
        usage = {
            "girdi": int(usage_raw.get("girdi") or 0),
            "cikti": int(usage_raw.get("cikti") or 0),
            "cagri": int(usage_raw.get("cagri") or 0),
        }

    cost_raw = raw.get("cost_usd")
    cost: float | None
    try:
        cost = float(cost_raw) if cost_raw is not None and cost_raw != "" else None
    except (TypeError, ValueError):
        cost = None

    return TaskRun(
        id=rid,
        task_id=tid,
        started=str(raw.get("started") or ""),
        finished=str(raw.get("finished") or ""),
        status=status,
        child_id=str(raw.get("child_id") or ""),
        title=str(raw.get("title") or "").strip(),
        report=_clip(raw.get("report") or ""),
        nodes_progress=[dict(p) for p in progress if isinstance(p, dict)] if progress else None,
        model=str(raw.get("model") or "").strip(),
        usage=usage,
        cost_usd=cost,
        tools=int(raw.get("tools") or 0),
        duration_s=int(raw.get("duration_s") or 0),
        last_tool=str(raw.get("last_tool") or "").strip(),
    )


def to_dict(run: TaskRun) -> dict[str, Any]:
    data = asdict(run)
    if data.get("nodes_progress") is None:
        data.pop("nodes_progress", None)
    if data.get("usage") is None:
        data.pop("usage", None)
    if data.get("cost_usd") is None:
        data.pop("cost_usd", None)
    if not data.get("tools"):
        data.pop("tools", None)
    if not data.get("duration_s"):
        data.pop("duration_s", None)
    if not data.get("last_tool"):
        data.pop("last_tool", None)
    return data


def _write(path: Path, run: TaskRun) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(to_dict(run), ensure_ascii=False, indent=2) + "\n"
    temp = path.with_suffix(".tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(path)


def start_run(
    state_dir: Path,
    task_id: str,
    *,
    title: str = "",
    child_id: str = "",
    run_id: str = "",
) -> TaskRun:
    """A new run: status=koşuyor, started=now."""
    tid = _safe_id(task_id, "task_id")
    rid = _safe_id(run_id, "run_id") if run_id else f"run_{uuid.uuid4().hex[:10]}"
    run = TaskRun(
        id=rid,
        task_id=tid,
        started=utcnow(),
        finished="",
        status="koşuyor",
        child_id=str(child_id or ""),
        title=str(title or "").strip(),
        report="",
        nodes_progress=None,
    )
    _write(_run_path(state_dir, tid, rid), run)
    return run


def finish_run(
    state_dir: Path,
    task_id: str,
    run_id: str,
    *,
    status: str = "bitti",
    report: str = "",
    child_id: str | None = None,
    nodes_progress: list[dict[str, Any]] | None = None,
    model: str | None = None,
    usage: dict[str, int] | None = None,
    cost_usd: float | None = None,
    tools: int | None = None,
    duration_s: int | None = None,
    last_tool: str | None = None,
) -> TaskRun:
    """Closes the run. status must be bitti|hata (koşuyor is not left behind)."""
    if status not in ("bitti", "hata"):
        raise TaskRunError("finish_run status 'bitti' veya 'hata' olmalı.")

    existing = get_run(state_dir, task_id, run_id)
    if existing is None:
        raise TaskRunError(f"Koşum yok: {task_id}/{run_id}")

    existing.status = status
    existing.finished = utcnow()
    if report:
        existing.report = _clip(report)
    if child_id is not None:
        existing.child_id = str(child_id)
    if nodes_progress is not None:
        existing.nodes_progress = [dict(p) for p in nodes_progress if isinstance(p, dict)]
    if model is not None:
        existing.model = str(model or "").strip()
    if usage is not None:
        existing.usage = {
            "girdi": int(usage.get("girdi") or 0),
            "cikti": int(usage.get("cikti") or 0),
            "cagri": int(usage.get("cagri") or 0),
        }
    if cost_usd is not None:
        existing.cost_usd = float(cost_usd)
    if tools is not None:
        existing.tools = int(tools)
    if duration_s is not None:
        existing.duration_s = int(duration_s)
    if last_tool is not None:
        existing.last_tool = str(last_tool or "").strip()[:200]

    _write(_run_path(state_dir, task_id, run_id), existing)
    return existing


def patch_run(
    state_dir: Path,
    task_id: str,
    run_id: str,
    *,
    report: str | None = None,
    nodes_progress: list[dict[str, Any]] | None = None,
    model: str | None = None,
    usage: dict[str, int] | None = None,
    last_error: str | None = None,
    tools: int | None = None,
    duration_s: int | None = None,
    last_tool: str | None = None,
    cost_usd: float | None = None,
) -> TaskRun | None:
    """Live-updates a running run (status stays koşuyor).

    None if missing / finished. So the last-run panel is not empty mid-run.
    """
    existing = get_run(state_dir, task_id, run_id)
    if existing is None or existing.status != "koşuyor":
        return None

    if report is not None:
        existing.report = _clip(report)
    if last_error:
        # The error line goes to the head of the report; panels should see a short summary.
        err = _clip(last_error, 400)
        body = existing.report or ""
        existing.report = _clip(f"Hata: {err}\n{body}" if body else f"Hata: {err}")
    if nodes_progress is not None:
        existing.nodes_progress = [
            dict(p) for p in nodes_progress if isinstance(p, dict)]
    if model is not None:
        existing.model = str(model or "").strip()
    if usage is not None:
        existing.usage = {
            "girdi": int(usage.get("girdi") or 0),
            "cikti": int(usage.get("cikti") or 0),
            "cagri": int(usage.get("cagri") or 0),
        }
    if cost_usd is not None:
        existing.cost_usd = float(cost_usd)
    if tools is not None:
        existing.tools = int(tools)
    if duration_s is not None:
        existing.duration_s = int(duration_s)
    if last_tool is not None:
        existing.last_tool = str(last_tool or "").strip()[:200]

    _write(_run_path(state_dir, task_id, run_id), existing)
    return existing


def get_run(state_dir: Path, task_id: str, run_id: str) -> TaskRun | None:
    try:
        path = _run_path(state_dir, task_id, run_id)
    except TaskRunError:
        return None
    if not path.is_file():
        return None
    try:
        return parse(json.loads(path.read_text(encoding="utf-8")))
    except (TaskRunError, json.JSONDecodeError, OSError, TypeError):
        return None


def list_runs(state_dir: Path, task_id: str, limit: int = 50) -> list[TaskRun]:
    """A task's runs: newest first, at most `limit` records."""
    try:
        parent = _task_dir(state_dir, task_id)
    except TaskRunError:
        return []
    if not parent.is_dir():
        return []

    runs: list[TaskRun] = []
    for path in parent.glob("*.json"):
        try:
            runs.append(parse(json.loads(path.read_text(encoding="utf-8"))))
        except (TaskRunError, json.JSONDecodeError, OSError, TypeError):
            continue

    runs.sort(key=lambda r: r.started or "", reverse=True)
    cap = max(1, int(limit or 50))
    return runs[:cap]
