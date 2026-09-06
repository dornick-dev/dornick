"""What is stored and compared speaks English: state values, schema keys,
tool parameters — and the old files still open.

`test_english_names.py` guards identifiers, `test_wire_names.py` the routes
and events. This file guards the third layer: the VALUES the code compares
against (a task state, a sleep state, a helper kind), the KEYS of every
file Dornick writes (temperament, exemplars, hooks, the change ledger, the
night stream…) and the model-facing tool parameters. A Turkish word in any
of them fails here.

The second half is the promise made to existing installs: every file
format that changed in 1.5.5 is read back from its OLD form and comes out
in the new one, byte for byte the same data.
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from dornick import (artifacts, config as config_module, events, hooks, legacy_values,
                     permissions, plans, pricing, recognition, schedule, task_runs,
                     workflows)
from dornick.mind import open_mind
from dornick.recall import (activation, character, exemplars, night_events, sleep,
                            temperament, weave)
from dornick.tools import checkpoint
from dornick.tools.base import ToolRegistry

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dornick"

# The words the old values and keys were made of. Whole words only.
TURKISH = frozenset("""
kosuyor koşuyor bitti hata yetim kesildi iptal bekliyor onaylandi yapiliyor atlandi atlandı
baslatilamadi başlatılamadı onariliyor onarılıyor zaman_asimi kostu temiz yok acik açık biten
basarisiz duzeltildi basarili rutin yardimci yardımcı iş is süreç surec uyanik uykulu uyuyor
uyaniyor kestirme derin hafif yazildi acildi basari sema yakalandi damitildi girdi cikti cagri
yenilik sonuc sosyal sebat temkin taban hedef kazanc kararlar eksen durum karar mesaj secenekler
yuksek baglamlar aciklama surum ad etiketler sira dosya arac zaman goruntu yoktu olay komut
arac_oncesi arac_sonrasi faz devreden islenen son_kosu eski yeni sebep dil uyku_acik tur basinc
tahmini_uyanma dongu_sayisi oturum dizi kenarlar paylar uzerinden oturumlar kaynaklar dongu
tamamlanan borc rapor bolge kuculen atlanan sadece_tespit sorgu seviye arka_plan adet tanim
kullanim hepsi konsol ag liste yol kesit uyari sistem ruh yetenek sohbet etiket kayit elle eksik
neden sorunlar fiyatlar anilar tanima projeler ayarlar kafa kat gomme konum kapanis
""".split())


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-zçğıöşü_]+", str(text).lower()) if w}


def _turkish(*values: object) -> set[str]:
    found: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            found |= _turkish(*value.keys(), *value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            found |= _turkish(*value)
        elif isinstance(value, str):
            found |= _words(value) & TURKISH
    return found


# -- 1. the values the code compares against ------------------------------


def test_every_legacy_map_points_at_english() -> None:
    """The maps are the ONLY place the old words live — and only as keys."""
    tables = [v for k, v in vars(legacy_values).items()
              if k.isupper() and isinstance(v, dict)]
    assert len(tables) > 25
    def check(table: dict, trail: tuple = ()) -> None:
        for old, new in table.items():
            if isinstance(new, dict):          # per-tool, per-field tables
                check(new, trail + (old,))
            else:
                assert not _turkish(new), trail + (old, new)

    for table in tables:
        check(table)


def test_state_constants_are_english() -> None:
    assert not _turkish(task_runs.STATUSES, plans.STATUSES, hooks.EVENTS,
                        temperament.AXES, activation.LABELS,
                        [s.value for s in sleep.State], [p.value for p in sleep.Phase],
                        list(weave.GAIN))
    assert task_runs.STATUSES == ("running", "done", "error")
    assert plans.STATUSES == ("waiting", "approved", "in_progress", "done", "cancelled")
    assert [s.value for s in sleep.State] == ["awake", "sleepy", "asleep", "waking"]


def test_the_night_schema_is_english() -> None:
    assert not _turkish(night_events.SCHEMA, night_events.SHARED)
    assert night_events.SHARED == ("ts", "kind")
    assert set(night_events.SCHEMA) == set(legacy_values.NIGHT_KINDS.values())


def test_the_python_sources_compare_against_no_turkish_state() -> None:
    """`state == "…"`, `status = "…"`, `.state in (…)` across the product."""
    pattern = re.compile(r'(?:state|status|kind|level|source)\s*(?:==|!=|=|in \()\s*\(?"([^"]+)"')
    bad: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        if path.name == "legacy_values.py":
            continue
        for value in pattern.findall(path.read_text(encoding="utf-8")):
            if _turkish(value):
                bad.setdefault(str(path.relative_to(ROOT)), set()).add(value)
    assert not bad, bad


def test_the_browser_compares_against_no_turkish_state() -> None:
    pattern = re.compile(r'\.(?:state|status|kind|last_status|sleep)\s*(?:===|!==)\s*"([^"]+)"')
    bad: dict[str, set[str]] = {}
    for path in (SRC / "web" / "static").glob("*.js"):
        for value in pattern.findall(path.read_text(encoding="utf-8")):
            if _turkish(value):
                bad.setdefault(path.name, set()).add(value)
    assert not bad, bad


def test_css_state_classes_are_english() -> None:
    css = (SRC / "web" / "static" / "app.css").read_text(encoding="utf-8")
    classes = set(re.findall(r"\.(?:task|orch-ch|orch-status|plan-step|ctx-seg|ctx-dot|thalamus)\.([a-zçğıöşü_-]+)", css))
    classes |= set(re.findall(r'data-(?:state|category)="([^"]+)"', css))
    assert not _turkish(classes), _turkish(classes)


# -- 2. the keys of the files Dornick writes ------------------------------


def test_the_files_dornick_writes_have_english_keys(tmp_path: Path) -> None:
    state = tmp_path
    temperament.save(state, temperament.Temperament(novelty=0.3), temperament.default_target(), "m")
    temperament.save_gain(state, temperament.neutral_gain())
    exemplars.save(state, [exemplars.Exemplar("caution", "d", "k")], "m")
    run = task_runs.start_run(state, "job_a", title="t", child_id="c")
    task_runs.finish_run(state, "job_a", run.id, status="done", usage={"input": 1, "output": 2, "calls": 1})
    plans.create(state, title="P", steps=["a"])
    meta = artifacts.publish(state, "Pano", "<p>x</p>")
    artifacts.update(state, meta["id"], "<p>y</p>")
    written = {
        "temperament.json": json.loads((state / "temperament.json").read_text("utf-8")),
        "decision_exemplars.json": json.loads((state / "decision_exemplars.json").read_text("utf-8")),
        "task-run": json.loads(next((state / "task-runs").rglob("*.json")).read_text("utf-8")),
        "plan": json.loads(next((state / "plans").glob("*.json")).read_text("utf-8")),
        "artifact meta": artifacts.read_meta(state, meta["id"]),
    }
    for name, data in written.items():
        assert not _turkish(list(data)), (name, _turkish(list(data)))
    assert set(written["temperament.json"]) == {"baseline", "target", "model_id", "gain"}
    assert set(written["temperament.json"]["baseline"]) == set(temperament.AXES)
    assert set(written["decision_exemplars.json"]["decisions"][0]) == {"axis", "situation", "decision"}
    assert set(written["task-run"]["usage"]) == {"input", "output", "calls"}
    assert written["artifact meta"]["version"] == 2


def test_a_night_is_written_in_the_new_vocabulary(tmp_path: Path) -> None:
    log = night_events.NightLog(tmp_path / "nights" / "2026-09-06.jsonl")
    event = log.emit("sleep.started", pressure=0.2, wake_estimate="07:00", cycle_count=3)
    assert set(event) == {"ts", "kind", "pressure", "wake_estimate", "cycle_count"}
    line = json.loads((tmp_path / "nights" / "2026-09-06.jsonl").read_text("utf-8"))
    assert line["kind"] == "sleep.started"


def test_session_log_notes_are_english(tmp_path: Path) -> None:
    """Every note the product writes, by name, from the sources."""
    names = set()
    for path in SRC.rglob("*.py"):
        names |= set(re.findall(r'\.note\("([a-z_ışğçöü]+)"', path.read_text(encoding="utf-8")))
    assert len(names) > 30
    assert not _turkish(names), _turkish(names)


def test_the_shipped_probe_set_has_english_keys() -> None:
    data = json.loads(character.PROBES_FILE.read_text(encoding="utf-8"))
    assert set(data) == {"name", "description", "decisions"}
    for row in data["decisions"]:
        assert set(row) == {"id", "axis", "message", "options", "high", "contexts"}
        assert row["axis"] in temperament.AXES
    for name in ("decisions.json", "exemplars.json"):
        rows = json.loads((ROOT / "eval" / "character" / name).read_text(encoding="utf-8"))["decisions"]
        assert all(r["axis"] in temperament.AXES for r in rows)


def test_the_shipped_writer_bundle_is_named_in_english() -> None:
    np = pytest.importorskip("numpy")
    bundle = np.load(SRC / "assets" / "base.npz", allow_pickle=False)
    assert "_config" in bundle.files and "_ayar" not in bundle.files
    assert {"embed", "pos", "final.w", "final.b"} <= set(bundle.files)
    assert not _turkish(bundle.files)
    assert set(json.loads(bytes(bundle["_config"]).decode("utf-8"))) == {"ctx", "d", "layers", "heads"}


# -- 3. the model-facing tool parameters ----------------------------------


def _every_tool_spec() -> list:
    from dornick.tools import build_registry
    return list(build_registry(None).all())


def test_tool_parameters_and_enum_values_are_english() -> None:
    bad: dict[str, set[str]] = {}
    specs = _every_tool_spec()
    assert len(specs) > 20
    for spec in specs:
        schema = spec.api_schema().get("input_schema") or {}
        for name, definition in (schema.get("properties") or {}).items():
            words = _turkish(name) | _turkish(definition.get("enum") or [])
            if words:
                bad.setdefault(spec.name, set()).update(words)
    assert not bad, bad


def test_the_renamed_parameters_are_where_the_map_says() -> None:
    by_name = {s.name: s for s in _every_tool_spec()}
    for tool, params in legacy_values.TOOL_PARAMS.items():
        props = by_name[tool].api_schema()["input_schema"]["properties"]
        for old, new in params.items():
            assert new in props and old not in props, (tool, old, new)
    for tool, fields in legacy_values.TOOL_ENUMS.items():
        props = by_name[tool].api_schema()["input_schema"]["properties"]
        for field, values in fields.items():
            assert set(values.values()) <= set(props[field]["enum"]), (tool, field)


# -- 4. migrations: the old file in, the new keys out ---------------------


def test_old_temperament_file_loads_and_is_rewritten(tmp_path: Path) -> None:
    (tmp_path / "temperament.json").write_text(json.dumps({
        "taban": {"yenilik": 0.3, "sonuc": 0.6, "sosyal": 0.1, "sebat": 0.7, "temkin": 0.9},
        "hedef": {"yenilik": 0.8, "sonuc": 0.6, "sosyal": 0.2, "sebat": 0.7, "temkin": 0.5},
        "kazanc": {"yenilik": 2.0, "sonuc": 1.0, "sosyal": 1.0, "sebat": 0.5, "temkin": 1.0},
        "model_id": "old-model"}), encoding="utf-8")
    baseline, target, model_id = temperament.load(tmp_path)
    assert (baseline.novelty, baseline.caution, target.novelty, model_id) == (0.3, 0.9, 0.8, "old-model")
    assert temperament.load_gain(tmp_path)["novelty"] == 2.0
    temperament.save_gain(tmp_path, temperament.load_gain(tmp_path))
    data = json.loads((tmp_path / "temperament.json").read_text("utf-8"))
    assert set(data) == {"baseline", "target", "gain", "model_id"} and "taban" not in data
    assert data["gain"]["novelty"] == 2.0 and data["baseline"]["caution"] == 0.9


def test_old_exemplar_file_loads(tmp_path: Path) -> None:
    (tmp_path / "decision_exemplars.json").write_text(json.dumps({
        "model_id": "m", "kararlar": [{"eksen": "temkin", "durum": "Tarih yok.", "karar": "sorarım"}]}),
        encoding="utf-8")
    (rows,) = exemplars.load(tmp_path)
    assert (rows.axis, rows.situation, rows.decision) == ("caution", "Tarih yok.", "sorarım")


def test_old_probe_file_loads(tmp_path: Path) -> None:
    (tmp_path / "p.json").write_text(json.dumps({"ad": "x", "kararlar": [{
        "id": "k1", "eksen": "yenilik", "mesaj": "m", "secenekler": ["a", "b"], "yuksek": "b",
        "baglamlar": ["Bağlam: c"]}]}), encoding="utf-8")
    (probe,) = character.load_probes(tmp_path / "p.json")
    assert (probe.axis, probe.high, probe.context) == ("novelty", "b", "Bağlam: c")


def test_old_night_file_replays_upgraded(tmp_path: Path) -> None:
    lines = [
        {"ts": "t1", "tur": "uyku.basladi", "basinc": 0.5, "tahmini_uyanma": "08:30", "dongu_sayisi": 2},
        {"ts": "t2", "tur": "uyku.dongu", "no": 1, "faz": "derin"},
        {"ts": "t3", "tur": "tekrar.ileri", "oturum": "s1", "dizi": ["n1"], "kenarlar": [["n1", "n2", 0.5]]},
        {"ts": "t4", "tur": "uyku.uyandi", "sebep": "kullanici", "dongu": 1, "tamamlanan": 1,
         "devreden": 3, "borc": {"faz": "rem", "devreden": 3}},
        {"ts": "t5", "tur": "uyku.bitti", "sebep": "basinc", "rapor": {"replayed": 1}},
    ]
    path = tmp_path / "nights" / "2026-01-01.jsonl"
    path.parent.mkdir()
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    replayed = list(night_events.replay(path))
    assert [e["kind"] for e in replayed] == ["sleep.started", "sleep.cycle", "replay.forward",
                                             "sleep.woke", "sleep.ended"]
    assert replayed[1]["phase"] == "deep" and replayed[2]["edges"] == [["n1", "n2", 0.5]]
    assert replayed[3]["reason"] == "user" and replayed[3]["debt"] == {"phase": "rem", "carried": 3}
    assert replayed[4]["reason"] == "pressure" and replayed[4]["report"] == {"replayed": 1}
    assert not any(_turkish(list(e)) for e in replayed)
    summary = night_events.summary(replayed)
    assert summary["replays"] == 1 and summary["woke"] == "user" and summary["carried"] == 3
    # The file itself is untouched.
    assert json.loads(path.read_text("utf-8").splitlines()[0])["tur"] == "uyku.basladi"
    # A gzipped old night reads the same way.
    with gzip.open(tmp_path / "nights" / "2025-12-31.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(lines[0]) + "\n")
    (packed,) = night_events.replay(tmp_path / "nights" / "2025-12-31.jsonl")
    assert packed["kind"] == "sleep.started" and packed["pressure"] == 0.5


def test_old_sleep_debt_and_watermark_load(tmp_path: Path) -> None:
    (tmp_path / "sleep_debt.json").write_text(json.dumps({"faz": "rem", "devreden": 4, "ts": "x"}), "utf-8")
    assert sleep._debt_read(tmp_path) == {"phase": "rem", "carried": 4, "ts": "x"}  # noqa: SLF001
    wm = tmp_path / "w.json"
    wm.write_text(json.dumps({"islenen": {"s1": "t"}, "son_kosu": "t2"}), "utf-8")
    assert weave._read_watermark(wm) == {"processed": {"s1": "t"}, "last_run": "t2"}  # noqa: SLF001


def test_old_session_log_notes_read_as_the_new_names(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in [
        {"seq": 0, "ts": "t", "kind": "meta", "role": None, "content": "baslik", "meta": {"ad": "Başlık"}},
        {"seq": 1, "ts": "t", "kind": "meta", "role": None, "content": "sonuc", "meta": {"sonuc": "basarisiz"}},
        {"seq": 2, "ts": "t", "kind": "meta", "role": None, "content": "ters_tekrar_kostu",
         "meta": {"oturum": "s", "sonuc": "basarili"}},
        {"seq": 3, "ts": "t", "kind": "meta", "role": None, "content": "goal_status",
         "meta": {"goal_id": "g", "durum": "done"}},
    ]) + "\n", encoding="utf-8")
    log = events.EventLog(path)
    notes = {e.content: e.meta for e in log.notes()}
    assert notes == {"title": {"name": "Başlık"}, "outcome": {"outcome": "failed"},
                     "reverse_replay_done": {"session": "s", "outcome": "succeeded"},
                     "goal_status": {"goal_id": "g", "status": "done"}}
    log.close()


def test_old_task_run_plan_and_schedule_records_load(tmp_path: Path) -> None:
    folder = tmp_path / "task-runs" / "job_x"
    folder.mkdir(parents=True)
    (folder / "r1.json").write_text(json.dumps({
        "id": "r1", "task_id": "job_x", "status": "koşuyor", "started": "t",
        "usage": {"girdi": 10, "cikti": 2, "cagri": 1}}), "utf-8")
    run = task_runs.get_run(tmp_path, "job_x", "r1")
    assert run.status == "running" and run.usage == {"input": 10, "output": 2, "calls": 1}
    done = task_runs.finish_run(tmp_path, "job_x", "r1", status="done")
    assert json.loads((folder / "r1.json").read_text("utf-8"))["status"] == "done"
    assert done.status == "done"

    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "p1.json").write_text(json.dumps({
        "id": "p1", "title": "P", "status": "onaylandi",
        "steps": [{"id": "s1", "text": "a", "status": "yapiliyor"}, {"id": "s2", "text": "b", "status": "bekliyor"}]}),
        "utf-8")
    plan = plans.get(tmp_path, "p1")
    assert plan.status == "approved"
    assert [s["status"] for s in plan.steps] == ["in_progress", "waiting"]

    book = schedule.Schedule(tmp_path)
    book.path.parent.mkdir(parents=True, exist_ok=True)
    book.path.write_text(json.dumps([{"id": "job_y", "title": "Y", "kind": "daily", "at": "09:00",
                                      "prompt": "p", "last_status": "başlatılamadı"}]), "utf-8")
    book = schedule.Schedule(tmp_path)
    assert book.get("job_y").last_status == "failed_to_start"


def test_old_workflow_file_reads_edge_conditions_and_manual_steps() -> None:
    wf = workflows.parse({"id": "w", "title": "W",
                          "nodes": [{"id": "a", "type": "shell", "elle": True}, {"id": "b", "type": "shell"}],
                          "edges": [{"from": "a", "to": "b", "on": "hata"}]})
    assert wf.nodes[0].manual is True and wf.edges[0].on == "error"


def test_old_hooks_file_loads_and_old_env_names_stay(tmp_path: Path) -> None:
    (tmp_path / "hooks.json").write_text(json.dumps([
        {"olay": "arac_oncesi", "arac": "write_file", "komut": "echo x", "zaman_asimi": 5},
        {"olay": "arac_sonrasi", "komut": "echo y"}]), "utf-8")
    loaded = hooks.load(tmp_path)
    assert [(h.event, h.tool, h.command, h.timeout) for h in loaded] == [
        ("before_tool", "write_file", "echo x", 5.0), ("after_tool", "*", "echo y", hooks.DEFAULT_TIMEOUT)]
    env = hooks._environment("write_file", {"path": "C:/a.py"}, "sess")  # noqa: SLF001
    assert env["DORNICK_TOOL"] == env["DORNICK_ARAC"] == "write_file"
    assert env["DORNICK_PATH"] == env["DORNICK_YOL"] == "C:/a.py"
    assert env["DORNICK_SESSION"] == env["DORNICK_OTURUM"] == "sess"


def test_old_change_ledger_is_adopted_and_read(tmp_path: Path) -> None:
    folder = tmp_path / "changes" / "cur"
    folder.mkdir(parents=True)
    target = tmp_path / "a.txt"
    target.write_text("new", encoding="utf-8")
    (folder / "0001-a.txt").write_text("old", encoding="utf-8")
    (folder / "kayit.jsonl").write_text(json.dumps({
        "sira": 1, "dosya": str(target), "arac": "write_file", "zaman": "t",
        "goruntu": "0001-a.txt", "yoktu": False, "atlandi": None}) + "\n", "utf-8")
    ledger = checkpoint.Ledger(tmp_path / "changes", "cur")
    assert not (folder / "kayit.jsonl").exists() and (folder / "ledger.jsonl").is_file()
    (record,) = ledger.list_entries()
    assert record == {"seq": 1, "file": str(target), "tool": "write_file", "time": "t",
                      "snapshot": "0001-a.txt", "missing": False, "skipped": None}
    done, error = ledger.undo(1)
    assert error is None and target.read_text(encoding="utf-8") == "old"
    assert json.loads((folder / "ledger.jsonl").read_text("utf-8").splitlines()[-1])["seq"] == 2


def test_old_config_session_meta_artifact_prices_and_recognition_load(tmp_path: Path) -> None:
    state = tmp_path / ".dornick"
    state.mkdir()
    (state / "config.json").write_text(json.dumps({"sleep": {"uyku_acik": False}}), "utf-8")
    cfg = config_module.Config.load(tmp_path)
    assert cfg.sleep.enabled is False

    sessions = state / "sessions"
    sessions.mkdir()
    (sessions / "_oturumlar.json").write_text(json.dumps({
        "s1": {"ad": "CMS", "etiketler": ["cms"], "path": "", "model": "", "provider": ""}}), "utf-8")
    mind = open_mind(state / "mind", sessions, "s1")
    assert mind.session_meta()["s1"]["name"] == "CMS" and mind.session_meta()["s1"]["tags"] == ["cms"]
    assert (sessions / "_sessions.json").is_file() and not (sessions / "_oturumlar.json").exists()
    mind.set_session_meta("s1", tags=["cms", "acil"])
    saved = json.loads((sessions / "_sessions.json").read_text("utf-8"))["s1"]
    assert saved["name"] == "CMS" and saved["tags"] == ["cms", "acil"] and "ad" not in saved

    meta = artifacts.publish(state, "Pano", "<p>x</p>")
    folder = artifacts.folder(state) / meta["id"]
    (folder / "meta.json").write_text(
        json.dumps({**{k: v for k, v in meta.items() if k != "version"}, "surum": 3}), "utf-8")
    assert artifacts.read_meta(state, meta["id"])["version"] == 3
    assert artifacts.update(state, meta["id"], "<p>y</p>")["version"] == 4

    (state / pricing.PRICE_FILE).write_text(json.dumps({
        "ts": 10 ** 12, "fiyatlar": {"m/a": {"girdi": 1e-6, "cikti": 2e-6}}}), "utf-8")
    assert pricing.table(state, now=lambda: 10 ** 12 + 1)["m/a"] == {"input": 1e-6, "output": 2e-6}

    (state / recognition.FILE).write_text(json.dumps({"on": True, "son_kosu": "2026-01-01"}), "utf-8")
    assert recognition.status(state) == {"on": True, "last_run": "2026-01-01", "learn_cloud_ok": False}


def test_old_use_log_entries_read_as_new_labels() -> None:
    uses = activation.parse_use_log(json.dumps([
        {"t": "2026-01-01T00:00:00", "w": 1.0, "etiket": "yazildi"},
        {"t": "2026-01-02T00:00:00", "w": -0.5, "etiket": "hata"},
        {"t": "2026-01-03T00:00:00", "w": 0.5, "label": "opened"},
    ]))
    assert [u.label for u in uses] == ["written", "error", "opened"]


def test_old_writer_bundle_names_load(tmp_path: Path) -> None:
    np = pytest.importorskip("numpy")
    from dornick.recall.writer import BaseWriter
    weights = {"gomme": np.zeros((3, 2), np.float32), "konum": np.zeros((4, 2), np.float32),
               "son.w": np.ones(2, np.float32), "son.b": np.zeros(2, np.float32),
               "_ayar": np.frombuffer(json.dumps({"ctx": 4, "d": 2, "kat": 0, "kafa": 1}).encode(), np.uint8)}
    np.savez(tmp_path / "old.npz", **weights)
    writer = BaseWriter(tmp_path / "old.npz")
    assert set(writer.w) == {"embed", "pos", "final.w", "final.b"} and writer.heads == 1
    assert writer.a == {"ctx": 4, "d": 2, "layers": 0, "heads": 1}


def test_old_tool_arguments_and_rules_keep_their_meaning() -> None:
    assert legacy_values.tool_args("run", {"komut": "pytest", "sadece_tespit": True, "zaman_asimi": 9}) == {
        "command": "pytest", "detect_only": True, "timeout": 9}
    assert legacy_values.tool_args("symbols", {"sorgu": "f", "tur": "tanim", "dil": "php"}) == {
        "query": "f", "kind": "definitions", "language": "php"}
    assert legacy_values.tool_args("browser", {"action": "konsol", "seviye": "hata"}) == {
        "action": "console", "level": "errors"}
    assert legacy_values.tool_args("camera", {"action": "kesit", "adet": 2}) == {"action": "capture", "count": 2}
    assert legacy_values.tool_args("task", {"task": "x", "arka_plan": True}) == {"task": "x", "background": True}
    assert legacy_values.tool_args("shell", {"command": "x", "arka_plan": True}) == {"command": "x", "job": True}
    # A new-name argument wins over an old one carried beside it.
    assert legacy_values.tool_args("run", {"komut": "old", "command": "new"}) == {"command": "new"}

    engine = permissions.PermissionEngine("ask", allow=["run:pytest*"], deny=[])
    spec = SimpleNamespace(name="run", mutates=True, safe_actions=())
    decision, rule = engine.evaluate(spec, {"komut": "pytest -q"})
    assert decision is permissions.Decision.ALLOW and rule == "run:pytest*"
