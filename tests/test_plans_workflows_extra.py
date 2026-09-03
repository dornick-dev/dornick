"""Smoke tests for the plan store and the workflow runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from dornick import plans, workflows
from dornick.workflow_run import _next_node


def test_plan_create_and_approve_flow(tmp_path: Path) -> None:
    p = plans.create(tmp_path, title="Büyük iş", steps=["a", "b", {"text": "c"}])
    assert p.status == "bekliyor"
    assert len(p.steps) == 3
    updated = plans.update(tmp_path, p.id, status="onaylandi")
    assert updated is not None and updated.status == "onaylandi"
    assert any(x["id"] == p.id for x in plans.listing(tmp_path))


def test_workflow_next_edge_prefers_exact_on() -> None:
    wf = workflows.parse({
        "id": "wf-test01",
        "title": "t",
        "nodes": [
            {"id": "a", "title": "A", "type": "custom"},
            {"id": "b", "title": "B", "type": "custom"},
            {"id": "c", "title": "C", "type": "custom"},
        ],
        "edges": [
            {"from": "a", "to": "b", "on": "ok"},
            {"from": "a", "to": "c", "on": "hata"},
        ],
    })
    assert _next_node(wf, "a", "ok") == "b"
    assert _next_node(wf, "a", "hata") == "c"


def test_workflow_save_assigns_id(tmp_path: Path) -> None:
    wf = workflows.save(tmp_path, {
        "title": "Telegram özeti",
        "nodes": [{"id": "n1", "title": "oku", "type": "custom",
                   "config": {"prompt": "oku"}, "secrets_needed": ["TELEGRAM_TOKEN"]}],
        "edges": [],
    })
    assert wf.id
    assert workflows.get(tmp_path, wf.id) is not None
