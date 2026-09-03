"""The trace automations leave in memory.

Two promises are tested:

  1. A created workflow enters memory as a PROCEDURE and can be found later
     — the "I did this in an automation before" moment only comes if the
     record exists.
  2. A broken step enters memory as a LESSON, ALWAYS WITH THE SAME PATTERN.
     The fixed pattern is not just a matter of tidiness: these records are
     the input of the personal fine-tuning that runs at night, and an event
     written differently every time leaves no pattern to learn.
"""

from __future__ import annotations

from pathlib import Path

from dornick import workflow_mind, workflows


def _workflow(tmp_path: Path) -> workflows.Workflow:
    return workflows.save(tmp_path, {
        "id": "posta", "title": "Günlük posta özeti",
        "nodes": [
            {"id": "n1", "title": "E-postaları oku", "type": "mail_read",
             "secrets_needed": ["MAIL_TOKEN"]},
            {"id": "n2", "title": "Önemlileri seç", "type": "agent"},
            {"id": "n3", "title": "WhatsApp'tan at", "type": "http",
             "secrets_needed": ["WP_TOKEN"], "skill": "wp_gonder"},
        ],
        "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
    })


class _FakeMind:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def remember(self, content, *, kind="fact", title="", tags=()):
        self.records.append({"content": content, "kind": kind,
                             "title": title, "tags": tuple(tags)})
        return object()


def test_a_saved_automation_becomes_a_procedure(tmp_path: Path) -> None:
    mind = _FakeMind()
    assert workflow_mind.recall_workflow(mind, _workflow(tmp_path)) is True

    (record,) = mind.records
    assert record["kind"] == "procedure"
    assert record["title"] == "otomasyon:posta"
    assert workflow_mind.TAG in record["tags"]
    # The content must be readable months later: what it does, what it needs.
    assert "Günlük posta özeti" in record["content"]
    assert "mail_read" in record["content"] and "http" in record["content"]
    assert "MAIL_TOKEN" in record["content"] and "WP_TOKEN" in record["content"]
    assert "wp_gonder" in record["content"]


def test_a_big_graph_does_not_flood_the_memory(tmp_path: Path) -> None:
    """Dumping a fifty-node graph as is drowns association."""
    wf = workflows.save(tmp_path, {
        "id": "buyuk", "title": "Büyük",
        "nodes": [{"id": f"n{i}", "title": f"Adım {i}", "type": "shell"}
                  for i in range(40)],
        "edges": [],
    })
    text = workflow_mind.workflow_text(wf)
    assert "ve 28 adım daha" in text
    assert len(text) < 900


def test_the_lesson_shape_is_stable(tmp_path: Path) -> None:
    """The same event with the same pattern every time — so fine-tuning can see it."""
    wf = _workflow(tmp_path)
    first = workflow_mind.lesson_text(wf.id, wf.nodes[0], RuntimeError("bağlanamadı"))
    second = workflow_mind.lesson_text(wf.id, wf.nodes[0], RuntimeError("bağlanamadı"))
    assert first == second
    assert first.startswith("Otomasyon [posta] adımı hata verdi")
    assert "RuntimeError: bağlanamadı" in first

    mind = _FakeMind()
    workflow_mind.recall_lesson(mind, wf.id, wf.nodes[0], RuntimeError("bağlanamadı"))
    (record,) = mind.records
    assert record["kind"] == "lesson"
    assert workflow_mind.LESSON_TAG in record["tags"]
    # The workflow tag is there too: all lessons of a workflow can be found together.
    assert f"{workflow_mind.TAG}:posta" in record["tags"]


def test_no_mind_is_silent_not_fatal() -> None:
    """Without a memory the automation must still run — the record is secondary."""
    assert workflow_mind.recall_workflow(None, None) is False
    assert workflow_mind.recall_lesson(None, "x", None, RuntimeError("y")) is False
    assert workflow_mind.search_workflows(None, "posta") == []


def test_recall_returns_only_automations() -> None:
    """The search filters automation records; unrelated memories do not come back."""

    class _Memory:
        def __init__(self, title, tags):
            self.title, self.tags = title, tags

    class _Scored:
        def __init__(self, item):
            self.item = item

    class _Mind:
        def recall(self, _q, limit=8):
            return [
                _Scored(_Memory("kahve tarifi", ["mutfak"])),
                _Scored(_Memory("otomasyon:posta", [workflow_mind.TAG])),
                _Scored(_Memory("otomasyon:rapor", [])),
            ]

    found = workflow_mind.search_workflows(_Mind(), "posta")
    assert [m.title for m in found] == ["otomasyon:posta", "otomasyon:rapor"]


def test_a_broken_mind_never_breaks_the_caller() -> None:
    class _Broken:
        def remember(self, *a, **k):
            raise RuntimeError("zihin düştü")

        def recall(self, *a, **k):
            raise RuntimeError("zihin düştü")

    assert workflow_mind.recall_workflow(_Broken(), None) is False
    assert workflow_mind.search_workflows(_Broken(), "x") == []
