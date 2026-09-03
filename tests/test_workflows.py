"""Workflow store and tool.

The promise: a workflow is written to disk and read back, the listing
arrives intact, the nodes/edges structure is validated, and the `from`
edge key stays in the JSON.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dornick import workflows
from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import workflow as workflow_tool


def _sample(**changes) -> dict:
    base = {
        "id": "posta-ozet-a1b2c3d4",
        "title": "Posta özeti",
        "nodes": [
            {
                "id": "n1",
                "title": "Oku",
                "type": "mail_read",
                "config": {"folder": "INBOX"},
                "secrets_needed": ["mail"],
                "skill": "",
                "position": {"x": 10, "y": 20},
            },
            {
                "id": "n2",
                "title": "Özetle",
                "type": "skill",
                "config": {},
                "secrets_needed": [],
                "skill": "ozet_csv",
                "position": {"x": 200, "y": 20},
            },
        ],
        "edges": [{"from": "n1", "to": "n2", "on": "ok"}],
    }
    return {**base, **changes}


# -- store -------------------------------------------------------------


def test_save_and_get_roundtrip(tmp_path: Path) -> None:
    saved = workflows.save(tmp_path, _sample())
    again = workflows.get(tmp_path, saved.id)

    assert again is not None
    assert again.title == "Posta özeti"
    assert len(again.nodes) == 2
    assert again.nodes[0].type == "mail_read"
    assert again.edges[0].from_ == "n1"
    assert again.edges[0].to == "n2"
    assert again.updated


def test_list_all_and_remove(tmp_path: Path) -> None:
    a = workflows.save(tmp_path, _sample(id="wf-alpha-11111111", title="Alpha"))
    b = workflows.save(tmp_path, _sample(id="wf-beta-22222222", title="Beta"))

    ids = {w.id for w in workflows.list_all(tmp_path)}
    assert ids == {a.id, b.id}

    assert workflows.remove(tmp_path, a.id) is True
    assert workflows.get(tmp_path, a.id) is None
    assert [w.id for w in workflows.list_all(tmp_path)] == [b.id]


def test_new_id_is_unique(tmp_path: Path) -> None:
    first = workflows.new_id(tmp_path, "Günlük Rapor")
    workflows.save(tmp_path, _sample(id=first, title="Günlük Rapor"))
    second = workflows.new_id(tmp_path, "Günlük Rapor")
    assert first != second


def test_save_allocates_id_when_missing(tmp_path: Path) -> None:
    raw = _sample()
    del raw["id"]
    saved = workflows.save(tmp_path, raw)
    assert saved.id
    assert workflows.get(tmp_path, saved.id) is not None


def test_nodes_and_edges_must_be_lists(tmp_path: Path) -> None:
    with pytest.raises(workflows.WorkflowError, match="nodes"):
        workflows.validate(_sample(nodes="yok"))
    with pytest.raises(workflows.WorkflowError, match="edges"):
        workflows.validate(_sample(edges=None))


def test_open_node_types_are_accepted(tmp_path: Path) -> None:
    """Types are not a closed enum — an unknown string is recorded too."""
    saved = workflows.save(
        tmp_path,
        _sample(
            id="wf-custom-99999999",
            nodes=[{"id": "x", "title": "X", "type": "my_future_node"}],
            edges=[],
        ),
    )
    assert saved.nodes[0].type == "my_future_node"


def test_to_dict_uses_from_key(tmp_path: Path) -> None:
    saved = workflows.save(tmp_path, _sample())
    data = workflows.to_dict(saved)
    assert data["edges"][0]["from"] == "n1"
    assert "from_" not in data["edges"][0]


# -- tool --------------------------------------------------------------


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    import asyncio

    config = Config(workspace=tmp_path, state_dir=tmp_path)
    session = Session(EventLog(tmp_path / "events.jsonl"), "test")
    return ToolContext(config=config, session=session, cancel=asyncio.Event())


@pytest.mark.asyncio
async def test_workflow_tool_create_list_get(ctx: ToolContext) -> None:
    registry = ToolRegistry()
    workflow_tool.register(registry)
    spec = registry.get("workflow")
    assert spec is not None

    created = await spec.handler(
        {"action": "create", "title": "Deneme", "nodes": [], "edges": []},
        ctx,
    )
    assert "Oluşturuldu" in created.content
    wid = created.detail["id"]

    listed = await spec.handler({"action": "list"}, ctx)
    assert wid in listed.content

    got = await spec.handler({"action": "get", "id": wid}, ctx)
    assert "Deneme" in got.content

    stub = await spec.handler({"action": "run", "id": wid}, ctx)
    assert stub.detail.get("stub") is True


# -- live progress ------------------------------------------------------
#
# The testable form of the "I will see where it is while it runs" requirement.


class _FakeIO:
    def on_child_tool(self, *a, **k) -> None:
        pass

    async def approve(self, spec, args) -> bool:
        # In tests approval is always granted; the real gate (permissions)
        # does not ask in yolo anyway — this is only in case a path still
        # falls to ASK.
        return True


class _FakeAgent:
    """Exactly as much of the agent as the runner really needs.

    After the security review (01.09) the shell/skill/mail nodes go
    through the real permission engine (executor.execute); that is why
    the fake agent carries a real registry + permission engine + session.
    Mode `yolo`: the tests measure the node execution, NOT the gate.
    """

    def __init__(self, state_dir) -> None:
        import asyncio

        from dornick.config import Config
        from dornick.events import EventLog
        from dornick.permissions import PermissionEngine
        from dornick.session import Session
        from dornick.tools import build_registry

        self.io = _FakeIO()
        self.mind = None
        self.config = Config(workspace=state_dir, state_dir=state_dir)
        self.config.ensure_dirs()
        self.session = Session(EventLog(state_dir / "wf-events.jsonl"), "wf")
        self.registry = build_registry()
        self.permissions = PermissionEngine("yolo", allow=[], deny=[])
        self.schedule = None
        self.cancel = asyncio.Event()

    def _observe(self, *_a, **_k) -> None:
        pass


class _FakeHandle:
    title = "deneme"
    schedule_id = ""
    run_id = ""
    model = ""


async def test_progress_is_reported_when_a_node_STARTS(tmp_path: Path) -> None:
    """Progress must be reported when a step STARTS too, not only when it ends.

    Reporting only at the end showed nothing running on screen during a
    long step: the previous node green, the next one not there yet — the
    flow diagram sat dead exactly at the moment we most wanted to watch.
    """
    from dornick.workflow_run import execute_workflow

    wf = workflows.save(tmp_path, {
        "id": "canli", "title": "Canlı akış",
        "nodes": [
            {"id": "a", "title": "Birinci", "type": "shell",
             "config": {"command": "echo bir"}},
            {"id": "b", "title": "İkinci", "type": "shell",
             "config": {"command": "echo iki"}},
        ],
        "edges": [{"from": "a", "to": "b", "on": "ok"}],
    })

    snapshots: list[list[dict]] = []
    report, progress, ok = await execute_workflow(
        wf, _FakeAgent(tmp_path), _FakeHandle(),
        on_progress=lambda p: snapshots.append(p))

    assert ok, report
    # There must be at least one snapshot showing node "a" WHILE RUNNING.
    running = [g for g in snapshots
               if any(s["id"] == "a" and s["status"] == "koşuyor" for s in g)]
    assert running, "no snapshot shows a running step — live tracking impossible"
    # And in that first snapshot the second node must not appear at all yet.
    assert all(s["id"] != "b" for s in running[0])
    # In the last snapshot both must be finished.
    assert {s["id"]: s["status"] for s in snapshots[-1]} == {"a": "bitti", "b": "bitti"}


async def test_a_broken_progress_listener_never_kills_the_run(tmp_path: Path) -> None:
    """Watching does not outrank running: if the listener blows up, the flow goes on."""
    from dornick.workflow_run import execute_workflow

    wf = workflows.save(tmp_path, {
        "id": "saglam", "title": "Sağlam",
        "nodes": [{"id": "a", "title": "Tek", "type": "shell",
                   "config": {"command": "echo bir"}}],
        "edges": [],
    })

    def blows_up(_p):
        raise RuntimeError("dinleyici öldü")

    _report, progress, ok = await execute_workflow(
        wf, _FakeAgent(tmp_path), _FakeHandle(), on_progress=blows_up)
    assert ok
    assert [s["status"] for s in progress] == ["bitti"]


# -- self-repair --------------------------------------------------------
#
# A repair is a real fix; but unlimited repair means an automation that
# keeps breaking itself all night long. The limits are tested here.


class _RepairingAgent(_FakeAgent):
    """An agent that returns the given JSON when `_spawn` is called."""

    def __init__(self, state_dir, reply: str) -> None:
        super().__init__(state_dir)
        self.reply = reply
        self.prompts: list[str] = []

    async def _spawn(self, title: str, prompt: str, _model: str) -> str:
        self.prompts.append(prompt)
        return self.reply


def _broken_flow(tmp_path: Path, *, hand_edited: bool = False):
    return workflows.save(tmp_path, {
        "id": "onar", "title": "Onarım denemesi",
        "nodes": [{"id": "a", "title": "Bozuk adım", "type": "shell",
                   "config": {"command": "kesinlikle-olmayan-komut-xyz"},
                   "elle": hand_edited}],
        "edges": [],
    })


async def test_a_failing_step_is_repaired_and_retried(tmp_path: Path) -> None:
    """The repair really works: the config is fixed and the step runs again."""
    from dornick.workflow_run import execute_workflow

    wf = _broken_flow(tmp_path)
    agent = _RepairingAgent(tmp_path, '{"command": "echo duzeldi"}')

    report, progress, ok = await execute_workflow(wf, agent, _FakeHandle())

    assert ok, report
    (step,) = progress
    assert step["status"] == "bitti"
    assert step.get("onarim"), "what changed must be in the report — a silent repair is a surprise"
    # The change must also be written to DISK; otherwise the same error tomorrow.
    assert workflows.get(tmp_path, "onar").nodes[0].config["command"] == "echo duzeldi"


async def test_a_hand_edited_step_is_never_rewritten(tmp_path: Path) -> None:
    """The model cannot rewrite a step the user wrote by hand behind their back.

    That would not be a fix but a silent revert.
    """
    from dornick.workflow_run import execute_workflow

    wf = _broken_flow(tmp_path, hand_edited=True)
    agent = _RepairingAgent(tmp_path, '{"command": "echo duzeldi"}')

    _report, progress, ok = await execute_workflow(wf, agent, _FakeHandle())

    assert not ok
    assert progress[0]["status"] == "hata"
    assert not agent.prompts, "no repair must be REQUESTED for a hand-edited step"
    assert workflows.get(tmp_path, "onar").nodes[0].config["command"] \
        == "kesinlikle-olmayan-komut-xyz"


async def test_repair_is_attempted_once_per_step(tmp_path: Path) -> None:
    """If the repair does not stick either, the step fails; no second attempt."""
    from dornick.workflow_run import execute_workflow

    wf = _broken_flow(tmp_path)
    agent = _RepairingAgent(tmp_path, '{"command": "yine-olmayan-komut-xyz"}')

    _report, progress, ok = await execute_workflow(wf, agent, _FakeHandle())

    assert not ok
    assert len(agent.prompts) == 1, "one repair attempt per step"
    assert "onarım denendi" in progress[0]["detail"]


async def test_an_unusable_repair_answer_changes_nothing(tmp_path: Path) -> None:
    """If the model chats instead of returning JSON, nothing must change — no guessing."""
    from dornick.workflow_run import execute_workflow

    wf = _broken_flow(tmp_path)
    agent = _RepairingAgent(tmp_path, "bilmiyorum, belki yolu kontrol et")

    _report, progress, ok = await execute_workflow(wf, agent, _FakeHandle())

    assert not ok
    assert not progress[0].get("onarim")
    assert workflows.get(tmp_path, "onar").nodes[0].config["command"] \
        == "kesinlikle-olmayan-komut-xyz"


# -- security: nodes do not skip the permission gate ---------------------
#
# A proven chain (security review, 01.09): the workflow's http/shell/skill
# nodes called subprocess/urllib/handler directly and never saw the
# permission engine or the hooks. The most dangerous: POSTing to the local
# API with an http node and flipping the mode to yolo. Non-read http is now
# subject to APPROVAL.


class _RefusingAgent(_FakeAgent):
    """An agent that REFUSES every approval — to measure whether the gate
    was actually asked."""

    def __init__(self, state_dir) -> None:
        super().__init__(state_dir)
        self.asked: list[dict] = []

        class _RefuseIO(_FakeIO):
            def __init__(self, record):
                self.record = record

            async def approve(self, spec, args):
                self.record.append(args)
                return False

        self.io = _RefuseIO(self.asked)


async def test_http_post_node_requires_approval(tmp_path: Path) -> None:
    """An http node doing POST does not run unapproved: on refusal the step
    fails and no request goes out. The local-API-to-yolo self-escalation
    chain breaks right here."""
    from dornick.workflow_run import execute_workflow

    wf = workflows.save(tmp_path, {
        "id": "kacak", "title": "Kaçış denemesi",
        "nodes": [{"id": "a", "title": "Kipi kır", "type": "http",
                   "config": {"url": "http://127.0.0.1:8765/api/settings",
                              "method": "POST",
                              "body": {"permissions": {"mode": "yolo"}}}}],
        "edges": [],
    })
    agent = _RefusingAgent(tmp_path)

    _report, progress, ok = await execute_workflow(wf, agent, _FakeHandle())

    assert not ok, "a refused http node must not count as successful"
    assert progress[0]["status"] == "hata"
    assert agent.asked, "approval SHOULD have been asked for the http POST"
    # The local-address warning must have made it into the approval text.
    assert "YEREL" in (agent.asked[0].get("istek") or "")
