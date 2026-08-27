"""İş akışı deposu ve aracı.

Vaat: akış diske yazılıp geri okunuyor, liste bozulmadan geliyor,
nodes/edges yapısı doğrulanıyor ve `from` kenar anahtarı JSON'da kalıyor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from neocp import workflows
from neocp.config import Config
from neocp.events import EventLog
from neocp.session import Session
from neocp.tools import ToolContext, ToolRegistry
from neocp.tools import workflow as workflow_tool


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


# -- depo --------------------------------------------------------------


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
    """Türler kapalı enum değil — bilinmeyen bir string de kayda girer."""
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


# -- araç --------------------------------------------------------------


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


# -- canlı ilerleme -----------------------------------------------------
#
# "Çalışırken nerede olduğunu göreceğim" şartının test edilebilir hâli.


class _SahteIO:
    def on_child_tool(self, *a, **k) -> None:
        pass


class _SahteAjan:
    """Koşucunun agent'tan gerçekten istediği kadarı."""

    def __init__(self, state_dir) -> None:
        self.io = _SahteIO()
        self.mind = None

        class _C:
            pass

        self.config = _C()
        self.config.state_dir = state_dir


class _SahteTutamac:
    title = "deneme"
    schedule_id = ""
    run_id = ""
    model = ""


async def test_progress_is_reported_when_a_node_STARTS(tmp_path: Path) -> None:
    """İlerleme adım BAŞLARKEN de bildirilmeli, yalnız biterken değil.

    Yalnız bitişte bildirmek, uzun süren bir adım boyunca ekranda koşan
    hiçbir şey göstermiyordu: önceki düğüm yeşil, sonraki henüz yok — akış
    şeması tam izlenmek istenen anda ölü duruyordu.
    """
    from neocp.workflow_run import execute_workflow

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

    goruntuler: list[list[dict]] = []
    rapor, progress, ok = await execute_workflow(
        wf, _SahteAjan(tmp_path), _SahteTutamac(),
        on_progress=lambda p: goruntuler.append(p))

    assert ok, rapor
    # "a" düğümünü KOŞARKEN gösteren en az bir görüntü olmalı.
    kosarken = [g for g in goruntuler
                if any(s["id"] == "a" and s["status"] == "koşuyor" for s in g)]
    assert kosarken, "hiçbir görüntüde koşan adım yok — canlı takip imkânsız"
    # Ve o ilk görüntüde ikinci düğüm henüz hiç görünmemeli.
    assert all(s["id"] != "b" for s in kosarken[0])
    # Son görüntüde ikisi de bitmiş olmalı.
    assert {s["id"]: s["status"] for s in goruntuler[-1]} == {"a": "bitti", "b": "bitti"}


async def test_a_broken_progress_listener_never_kills_the_run(tmp_path: Path) -> None:
    """İzlemek koşmaktan önemli değil: dinleyici patlarsa akış sürmeli."""
    from neocp.workflow_run import execute_workflow

    wf = workflows.save(tmp_path, {
        "id": "saglam", "title": "Sağlam",
        "nodes": [{"id": "a", "title": "Tek", "type": "shell",
                   "config": {"command": "echo bir"}}],
        "edges": [],
    })

    def patlar(_p):
        raise RuntimeError("dinleyici öldü")

    _rapor, progress, ok = await execute_workflow(
        wf, _SahteAjan(tmp_path), _SahteTutamac(), on_progress=patlar)
    assert ok
    assert [s["status"] for s in progress] == ["bitti"]


# -- kendini onarma -----------------------------------------------------
#
# Onarım gerçek bir düzeltme; ama sınırsız onarım, gece boyunca kendi
# kendini bozan bir otomasyon demek. Sınırların testi burada.


class _OnaranAjan(_SahteAjan):
    """`_spawn` çağrıldığında verilen JSON'u döndüren ajan."""

    def __init__(self, state_dir, cevap: str) -> None:
        super().__init__(state_dir)
        self.cevap = cevap
        self.istemler: list[str] = []

    async def _spawn(self, baslik: str, istem: str, _model: str) -> str:
        self.istemler.append(istem)
        return self.cevap


def _bozuk_akis(tmp_path: Path, *, elle: bool = False):
    return workflows.save(tmp_path, {
        "id": "onar", "title": "Onarım denemesi",
        "nodes": [{"id": "a", "title": "Bozuk adım", "type": "shell",
                   "config": {"command": "kesinlikle-olmayan-komut-xyz"},
                   "elle": elle}],
        "edges": [],
    })


async def test_a_failing_step_is_repaired_and_retried(tmp_path: Path) -> None:
    """Onarım gerçekten çalışıyor: config düzeliyor ve adım yeniden koşuyor."""
    from neocp.workflow_run import execute_workflow

    wf = _bozuk_akis(tmp_path)
    ajan = _OnaranAjan(tmp_path, '{"command": "echo duzeldi"}')

    rapor, progress, ok = await execute_workflow(wf, ajan, _SahteTutamac())

    assert ok, rapor
    (adim,) = progress
    assert adim["status"] == "bitti"
    assert adim.get("onarim"), "ne değiştiği rapora yazılmalı — sessiz onarım sürprizdir"
    # Değişiklik DİSKE de yazılmış olmalı; yoksa yarın aynı hata.
    assert workflows.get(tmp_path, "onar").nodes[0].config["command"] == "echo duzeldi"


async def test_a_hand_edited_step_is_never_rewritten(tmp_path: Path) -> None:
    """Kullanıcının elle yazdığı adımı model arkasından değiştiremez.

    Bu bir düzeltme değil, sessizce geri alma olurdu.
    """
    from neocp.workflow_run import execute_workflow

    wf = _bozuk_akis(tmp_path, elle=True)
    ajan = _OnaranAjan(tmp_path, '{"command": "echo duzeldi"}')

    _rapor, progress, ok = await execute_workflow(wf, ajan, _SahteTutamac())

    assert not ok
    assert progress[0]["status"] == "hata"
    assert not ajan.istemler, "elle düzenlenmiş adım için onarım İSTENMEMELİ"
    assert workflows.get(tmp_path, "onar").nodes[0].config["command"] \
        == "kesinlikle-olmayan-komut-xyz"


async def test_repair_is_attempted_once_per_step(tmp_path: Path) -> None:
    """Onarım da tutmazsa adım hata veriyor; ikinci kez denenmiyor."""
    from neocp.workflow_run import execute_workflow

    wf = _bozuk_akis(tmp_path)
    ajan = _OnaranAjan(tmp_path, '{"command": "yine-olmayan-komut-xyz"}')

    _rapor, progress, ok = await execute_workflow(wf, ajan, _SahteTutamac())

    assert not ok
    assert len(ajan.istemler) == 1, "adım başına tek onarım denemesi"
    assert "onarım denendi" in progress[0]["detail"]


async def test_an_unusable_repair_answer_changes_nothing(tmp_path: Path) -> None:
    """Model JSON yerine laf ederse hiçbir şey değişmemeli — tahmin yok."""
    from neocp.workflow_run import execute_workflow

    wf = _bozuk_akis(tmp_path)
    ajan = _OnaranAjan(tmp_path, "bilmiyorum, belki yolu kontrol et")

    _rapor, progress, ok = await execute_workflow(wf, ajan, _SahteTutamac())

    assert not ok
    assert not progress[0].get("onarim")
    assert workflows.get(tmp_path, "onar").nodes[0].config["command"] \
        == "kesinlikle-olmayan-komut-xyz"
