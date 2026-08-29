"""Coding benchmark runner: hands tasks to a real agent, produces the card.

Flow (per task, in order):

    build temp workspace → copy seed → start ISOLATED neo instance
    → give the raw brief through the external gate (POST /api/gate)
    → wait for the turn to finish → shut the instance down
    → grade the workshop → extract behaviour from the session log

Every task runs in its own temp workspace on its own neo instance (see
`instance.py`): the user's mind, workshop and open app are untouched, and
tasks never see each other's leftovers.

Usage:

    py eval/coding/runner.py --task k1-module,k2-cli
    py eval/coding/runner.py --difficulty easy,medium --repeat 1
    py eval/coding/runner.py --task all --model openai/gpt-5.6-luna

Parameters:
    --task        comma-separated task ids ("all" = everything)
    --difficulty  easy/medium/hard filter
    --model       OVERRIDES the model (without it, the model in the source
                  config.json is used as-is — measuring never edits settings)
    --repeat      how many times to run each task (to see the noise)
    --wait        maximum seconds for one turn
    --keep        do not delete the temp workspaces (for debugging)
    --previous    a previous result JSON; tasks not re-run are carried over
                  from it. For re-running a single task (a noisy one, or one
                  whose measurement was disturbed from outside) while still
                  producing a COMPLETE report. Carried rows are marked `†`
                  in the report — which number came from which run is never
                  hidden.

Output: `results/<time>-<model>.json` + human-readable `results/REPORT.md`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import behavior  # noqa: E402
import grading  # noqa: E402
from grading import Scorecard  # noqa: E402

TASKS_DIR = HERE / "tasks"
RESULTS_DIR = HERE / "results"

# Time allowed for the instance to boot. Model warm-up and skill loading
# take seconds; more if something needs downloading.
BOOT_S = 180.0
DEFAULT_WAIT = 900.0

# Must not collide with the user's open neo (8765) or its browser port (9222).
PORT_BASE = 8791
BROWSER_PORT_BASE = 9333


# -- task discovery -----------------------------------------------------


class Task:
    """A task folder on disk: raw brief + grader + optional seed."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.id = folder.name
        self.brief = (folder / "task.md").read_text(encoding="utf-8").strip()
        self.seed = folder / "seed"
        self._module = self._load()

    def _load(self) -> Any:
        path = self.folder / "grader.py"
        spec = importlib.util.spec_from_file_location(f"grader_{self.id}", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"grader failed to load: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @property
    def title(self) -> str:
        return getattr(self._module, "TITLE", self.id)

    @property
    def difficulty(self) -> str:
        return getattr(self._module, "DIFFICULTY", "?")

    @property
    def language(self) -> str:
        return getattr(self._module, "LANGUAGE", "?")

    def score(self, workshop: Path) -> list[grading.Axis]:
        return self._module.score(workshop)


def discover_tasks() -> list[Task]:
    return [Task(p) for p in sorted(TASKS_DIR.iterdir())
            if p.is_dir() and (p / "task.md").is_file()
            and (p / "grader.py").is_file()]


# -- isolated workspace -------------------------------------------------


def free_port(base: int) -> int:
    for port in range(base, base + 200):
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("no free port found")


def build_workspace(task: Task, source_state: Path, model: str | None,
                    browser_port: int) -> Path:
    """Temp workspace: its own `.neocp`, its own workshop, its own config."""
    workspace = Path(tempfile.mkdtemp(prefix=f"neocp-eval-{task.id}-"))
    state = workspace / ".neocp"
    state.mkdir(parents=True, exist_ok=True)
    workshop = workspace / "atolye"
    workshop.mkdir(parents=True, exist_ok=True)

    if task.seed.is_dir():
        shutil.copytree(task.seed, workshop, dirs_exist_ok=True)

    # The user's config is COPIED, never edited. The model comes through
    # as-is; only the things that would break the measurement or touch the
    # user's machine are turned off (voice, listening, camera, location),
    # and the browser port is shifted.
    config: dict[str, Any] = {}
    source_config = source_state / "config.json"
    if source_config.is_file():
        try:
            config = json.loads(source_config.read_text(encoding="utf-8"))
        except ValueError:
            config = {}
    if model:
        config.setdefault("model", {})["name"] = model
    config["voice"] = {"enabled": False}
    config["listen"] = {"enabled": False}
    config["camera"] = {"enabled": False}
    config["place"] = {"enabled": False}
    config.setdefault("browser", {})["port"] = browser_port
    # There is no such thing as an approval dialog during a measurement:
    # a turn stuck on approval measures the waiting, not the agent.
    config["permissions"] = {"mode": "yolo", "allow": [], "deny": []}
    (state / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    # Keys: without them the model cannot talk.
    source_keys = source_state / "keys.json"
    if source_keys.is_file():
        shutil.copyfile(source_keys, state / "keys.json")
    # Price-table cache: the cost report should not need the network.
    source_prices = source_state / "fiyat.json"
    if source_prices.is_file():
        shutil.copyfile(source_prices, state / "fiyat.json")

    # The external gate arrives open — it is the measurement's only voice.
    (state / "gate.json").write_text(json.dumps({"on": True}), encoding="utf-8")
    return workspace


class Instance:
    """Isolated neo instance (subprocess). Exits cleanly with the `with` block."""

    def __init__(self, workspace: Path, port: int) -> None:
        self.workspace = workspace
        self.port = port
        self.process: subprocess.Popen[str] | None = None
        self.url = ""
        self.session = ""
        self.log: list[str] = []
        self.error = ""
        self._drainer: threading.Thread | None = None

    def __enter__(self) -> "Instance":
        argv = [sys.executable, str(HERE / "instance.py"),
                "--workspace", str(self.workspace), "--port", str(self.port)]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        env.pop("NEOCP_WORKSPACE", None)
        env["NEOCP_STATE_DIR"] = str(self.workspace / ".neocp")
        self.process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", env=env, cwd=str(ROOT))
        deadline = time.time() + BOOT_S
        while time.time() < deadline:
            line = self.process.stdout.readline() if self.process.stdout else ""
            if not line:
                if self.process.poll() is not None:
                    self.error = "instance process died during boot"
                    break
                continue
            self.log.append(line.rstrip())
            print(f"    | {line.rstrip()}", flush=True)
            if line.startswith("READY "):
                parts = line.split()
                self.url = parts[1] if len(parts) > 1 else ""
                for p in parts[2:]:
                    if p.startswith("session="):
                        self.session = p.split("=", 1)[1]
                break
            if line.startswith("BOOT-FAILED "):
                self.error = line.strip()
                break
        else:
            self.error = f"instance not ready in {BOOT_S:.0f}s"
        self._drain()
        return self

    def _drain(self) -> None:
        """Keep draining the child's stdout after boot.

        Without draining, the child BLOCKS on `print` once the pipe fills
        and the turn silently freezes — neo prints `[neo] ...` lines
        throughout a turn, and a fifteen-minute turn fills a 64 KB pipe
        easily.
        """
        if self.process is None or self.process.stdout is None:
            return

        def loop() -> None:
            try:
                for line in self.process.stdout:  # type: ignore[union-attr]
                    self.log.append(line.rstrip())
                    del self.log[:-400]
            except Exception:
                pass

        self._drainer = threading.Thread(target=loop, daemon=True,
                                         name="neo-eval-log")
        self._drainer.start()

    def ask(self, text: str, wait_s: float) -> dict[str, Any]:
        """Give the raw brief through the gate; return the whole turn."""
        if not self.url and self.error:
            return {"ok": False, "error": self.error}
        body = json.dumps({"text": text, "bekle_sn": wait_s}).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/gate", data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=wait_s + 90) as answer:
                return json.loads(answer.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def __exit__(self, *_: Any) -> None:
        if self.process is None:
            return
        try:
            if self.process.stdin:
                self.process.stdin.write("stop\n")
                self.process.stdin.flush()
        except Exception:
            pass
        try:
            self.process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            self.process.kill()
        if self._drainer is not None:
            self._drainer.join(timeout=5)


# -- one run ------------------------------------------------------------


def run_once(task: Task, source_state: Path, model: str | None,
             wait_s: float, keep: bool) -> Scorecard:
    port = free_port(PORT_BASE)
    browser = free_port(BROWSER_PORT_BASE)
    workspace = build_workspace(task, source_state, model, browser)
    workshop = workspace / "atolye"
    notes: list[str] = []
    gate: dict[str, Any] = {}

    print(f"  workspace: {workspace}  port: {port}", flush=True)
    started = time.time()
    try:
        with Instance(workspace, port) as instance:
            if instance.error:
                notes.append(f"instance failed to open: {instance.error}")
                notes.extend(instance.log[-6:])
                before: dict[str, str] = {}
            else:
                # BEFORE the turn: what did boot put into the workshop?
                before = fingerprint(workshop)
                gate = instance.ask(task.brief, wait_s)
                if not gate.get("ok"):
                    notes.append(f"gate: {gate.get('error')}")
            session_id = gate.get("oturum") or instance.session

        count = write_exclusions(workshop, before)
        if count:
            notes.append(f"excluded from grading (untouched pre-turn files): {count}")

        log_path = workspace / ".neocp" / "sessions" / f"{session_id}.jsonl"
        b = behavior.extract(
            log_path, gate=gate,
            model_name=(model or _model_name(source_state)),
            state_dir=workspace / ".neocp")
        b["wall_clock_s"] = round(time.time() - started, 1)

        # Sweep BEFORE grading, not only in `finally`: the agent's own
        # detached service survives the instance and still holds its port,
        # and the grader then honestly reports "port held — cannot
        # measure". Measured twice on o2-service (29.08) before the order
        # was fixed. The `finally` sweep below stays as the safety net.
        leftovers = sweep_workspace(workspace, workshop, started)
        if leftovers:
            notes.append(f"{leftovers} leftover processes killed before grading")

        try:
            axes = task.score(workshop)
        except Exception as exc:  # a crashed grader never invents a zero
            notes.append(f"grader crashed: {type(exc).__name__}: {exc}")
            axes = [grading.Axis(name, ceiling, None, [],
                                 reason="grader crashed")
                    for name, ceiling in grading.AXES.items()]
        return Scorecard(task.id, axes, b, notes)
    finally:
        leftovers = sweep_workspace(workspace)
        if leftovers:
            print(f"  ({leftovers} processes survived the turn; killed)",
                  flush=True)
        if keep:
            print(f"  (workspace kept: {workspace})", flush=True)
        else:
            shutil.rmtree(workspace, ignore_errors=True)


def sweep_workspace(workspace: Path, workshop: Path | None = None,
                    started: float | None = None) -> int:
    """Kill every process still tied to this workspace; return the count.

    When the instance closes, neo itself goes down — but what it started
    did not: the agent's `php -S`, `node`, and neo's own Chrome (`close()`
    only drops the DevTools connection, deliberately, so user sessions
    stay warm). In a measurement this had two costs: one task scored a
    FALSE 100.0 because of a held port, and 18 orphan processes piled up
    in Temp because the profile folder could not be deleted.

    Two matching passes:
      1. The workspace path appears in the command line. The path is a
         unique temp directory, so the user's own Chrome or server can
         never match.
      2. (with `workshop` + `started`) a python/node/php process CREATED
         AFTER this rep began whose command line names a script that
         exists in the workshop. This catches the relative launch the
         path filter misses — the agent runs `py servis.py` with cwd in
         the workshop, and the command line carries no path at all.
         (Measured: o2-service graded "port held — cannot measure" twice
         because of exactly this survivor.)

    Outside Windows this quietly does nothing.
    """
    if sys.platform != "win32":
        return 0
    pattern = str(workspace).replace("'", "''")
    # `$_.ProcessId -ne $PID`: the PowerShell running the query carries
    # this path in its OWN command line — without the exclusion it would be
    # its own first victim and the count would never print.
    clauses = [f"($_.CommandLine -like '*{pattern}*')"]
    if workshop is not None and started is not None:
        # RECURSIVE: the agent parks its service in a subfolder
        # (kisa-link/servis.py) — a shallow glob missed the name and the
        # survivor held the port through grading a third time.
        names = sorted({p.name for p in workshop.rglob("*")
                        if p.suffix.lower() in (".py", ".js", ".mjs", ".php")
                        and not any(d in grading.SKIP_DIRS for d in p.parts)})
        if names:
            # Substring match on purpose: quoted launches ("servis.py") and
            # Start-Process command lines carry no leading space. A false
            # positive would be a python/node/php process born after this
            # rep whose command line happens to name a workshop file —
            # that is the leftover we are hunting, not a bystander.
            adlar = " -or ".join(
                f"($_.CommandLine -like '*{n.replace(chr(39), chr(39)*2)}*')"
                for n in names[:20])
            # CIM date comparison: only processes born after this rep began.
            baslangic = time.strftime("%Y%m%d%H%M%S",
                                      time.localtime(started))
            clauses.append(
                "(($_.Name -match '^(python|node|php)') -and "
                f"({adlar}) -and "
                "($_.CreationDate -ge [datetime]::ParseExact("
                f"'{baslangic}','yyyyMMddHHmmss',$null)))")
    script = (
        "$p = Get-CimInstance Win32_Process | Where-Object { "
        f"($_.ProcessId -ne $PID) -and ({' -or '.join(clauses)}) }}; "
        "$p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
        "-ErrorAction SilentlyContinue }; "
        "($p | Measure-Object).Count"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        ).stdout.strip()
        return int(out or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0  # even if cleanup failed, the measurement must be reported


def fingerprint(root: Path) -> dict[str, str]:
    """Content digest of every file in the workshop (relative POSIX path → sha1)."""
    import hashlib

    out: dict[str, str] = {}
    for folder, subdirs, files in os.walk(root):
        subdirs[:] = [d for d in subdirs if d not in grading.SKIP_DIRS]
        for name in files:
            path = Path(folder) / name
            try:
                out[path.relative_to(root).as_posix()] = hashlib.sha1(
                    path.read_bytes()).hexdigest()
            except OSError:
                continue
    return out


def write_exclusions(root: Path, before: dict[str, str]) -> int:
    """Exclude pre-turn files the agent did NOT touch from grading.

    The workshop is not empty when the turn starts: neo copies its seed
    skills at boot, and the task has its own seed files. Those are not the
    agent's work and they polluted the code-health score (measured: the
    entire complexity penalty of one early run came from a seed skill).
    If the agent EDITED a seed file its digest changes and the file stays
    in scope — repair tasks depend on that.
    """
    now = fingerprint(root)
    excluded = sorted(path for path, digest in before.items()
                      if now.get(path) == digest)
    (root / grading.EXCLUDE_FILE).write_text(
        json.dumps(excluded, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(excluded)


def _model_name(state: Path) -> str:
    try:
        data = json.loads((state / "config.json").read_text(encoding="utf-8"))
        return str((data.get("model") or {}).get("name") or "")
    except (OSError, ValueError):
        return ""


# -- report -------------------------------------------------------------


def _num(x: float | None, fmt: str = "{:.1f}") -> str:
    return "—" if x is None else fmt.format(x)


def write_report(result: dict[str, Any], path: Path) -> None:
    s: list[str] = []
    stamp = result["time"]
    s.append("# Coding Benchmark Report")
    s.append("")
    s.append(f"**Run:** {stamp} · **Model:** `{result['model']}` · "
             f"**Repetitions:** {result['repetitions']} · "
             f"**Rig:** `eval/coding/` (external gate + isolated instance)")
    s.append("")
    s.append("The score has four axes: **works** 40 · **requested scope** 25 · "
             "**code health** 20 · **test quality** 15. An unmeasurable axis "
             "also leaves the denominator; if the brief did not ask for the "
             "work (*not requested*) it is measured but not scored. The score "
             "column is normalised to 100.")
    s.append("")

    # -- main table
    s.append("## Score breakdown")
    s.append("")
    s.append("| task | difficulty | language | works (40) | scope (25) "
             "| health (20) | tests (15) | **score** |")
    s.append("|---|---|---|---|---|---|---|---|")
    for row in result["tasks"]:
        card = row["card"]
        cells = []
        for name in ("works", "scope", "health", "tests"):
            axis = next((x for x in card["axes"] if x["name"] == name), None)
            if axis is None:
                cells.append("—")
            elif axis["earned"] is None:
                cells.append("unmeasurable")
            else:
                label = f"{axis['earned']:.1f}"
                cells.append(f"{label}*" if axis["external"] else label)
        score = card["score"]
        sd = "unmeasurable" if score is None else f"**{score:.1f}**"
        if row.get("score_spread") is not None and result["repetitions"] > 1:
            sd += f" ±{row['score_spread']:.1f}"
        task_id = row["id"] + ("†" if row.get("carried_from") else "")
        s.append(f"| {task_id} | {row['difficulty']} | {row['language']} | "
                 + " | ".join(cells) + f" | {sd} |")
    s.append("")
    s.append("`*` = the brief did not ask for this; measured, reported, not scored.")
    carried = {r["id"]: r["carried_from"] for r in result["tasks"]
               if r.get("carried_from")}
    if carried:
        s.append("`†` = this row is carried over from a previous run: "
                 + ", ".join(f"{k} ({v})" for k, v in sorted(carried.items()))
                 + ".")
    s.append("")

    # -- behaviour table
    s.append("## Behaviour metrics (never scored)")
    s.append("")
    s.append("| task | turn finished | tool calls | tool errors | duration s "
             "| tokens (in/out) | cost $ | self-verified | wrote plan "
             "| broken deliveries |")
    s.append("|---|---|---|---|---|---|---|---|---|---|")
    for row in result["tasks"]:
        b = row["card"].get("behavior") or {}
        if b.get("unextractable"):
            s.append(f"| {row['id']} | " + " | ".join(["unextractable"] * 9) + " |")
            continue
        tokens = (f"{b.get('prompt_tokens_total') or '—'}/"
                  f"{b.get('output_tokens') or '—'}")
        # A workshop graded before the turn finished may be HALF-DONE;
        # the reader must know.
        finished = "yes" if b.get("gate_ok") else "**NO**"
        s.append(
            f"| {row['id']} | {finished} | {b.get('tool_calls', '—')} | "
            f"{b.get('tool_errors', '—')} | {_num(b.get('duration_s'))} | {tokens} | "
            f"{_num(b.get('cost_usd'), '{:.4f}')} | "
            f"{'yes' if b.get('verified') else 'no'} | "
            f"{'yes' if b.get('wrote_plan') else 'no'} | "
            f"{row.get('broken_deliveries', 0)}/{result['repetitions']} |")
    s.append("")
    unfinished = [r["id"] for r in result["tasks"]
                  if not (r["card"].get("behavior") or {}).get("gate_ok")]
    if unfinished:
        s.append(f"**Tasks graded before their turn finished:** "
                 f"{', '.join(unfinished)}. Their scores measure whatever was "
                 "in the workshop when time ran out, not the agent's FINISHED "
                 "work — biased downward.")
        s.append("")

    measured = [r["card"]["score"] for r in result["tasks"]
                if r["card"]["score"] is not None]
    if measured:
        s.append(f"**Mean score:** {sum(measured) / len(measured):.1f}/100 "
                 f"({len(measured)} tasks measured)")
        s.append("")
    if result.get("not_run"):
        s.append("**Not run:** " + ", ".join(result["not_run"]))
        s.append("")

    # -- noise warning: nobody should read the numbers without this
    s.append("## How solid are these numbers?")
    s.append("")
    if result["repetitions"] < 2:
        s.append("**A single run is noise.** Every score here comes from one "
                 "attempt; re-running the same task on the same model can move "
                 "it a few points, and much more on some tasks (tool errors, "
                 "timeouts). To claim an improvement, run with `--repeat 3` "
                 "and look at the ± spread. A large gap in a single run "
                 "(>15 points) means something; a small one (<5 points) is "
                 "indistinguishable from noise.")
    else:
        s.append(f"Every task ran {result['repetitions']} times; the ± in the "
                 "score column is the between-run spread (half of min–max). "
                 "Differences smaller than the spread are not improvements.")
    s.append("")
    s.append("Isolation: every run happened in its own temp workspace, with an "
             "**empty mind**, on its own neo instance. The user's memories do "
             "not ride along — this rig measures the coding pipeline, not "
             "memory's contribution to coding.")
    s.append("")

    # -- per-task evidence
    s.append("## Evidence")
    s.append("")
    for row in result["tasks"]:
        s.append(f"### {row['id']} — {row['title']}")
        s.append("")
        for axis in row["card"]["axes"]:
            label = grading.AXIS_TITLES.get(axis["name"], axis["name"])
            if axis["earned"] is None:
                s.append(f"- **{label}: unmeasurable** — {axis['reason']}")
            else:
                extra = " *(not requested)*" if axis["external"] else ""
                s.append(f"- **{label}: {axis['earned']:.1f}/{axis['ceiling']}**{extra}")
            for evidence in axis["evidence"]:
                s.append(f"  - `{evidence}`")
        b = row["card"].get("behavior") or {}
        if b.get("verify_trail"):
            s.append("- verification trail: " +
                     "; ".join(f"`{x}`" for x in b["verify_trail"][:4]))
        if b.get("tools"):
            s.append("- tools: " +
                     ", ".join(f"{k}×{v}" for k, v in b["tools"].items()))
        for note in row["card"].get("notes") or []:
            s.append(f"- ! {note}")
        s.append("")

    path.write_text("\n".join(s), encoding="utf-8")


# -- main ---------------------------------------------------------------


def _read_previous(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Read the carry-over file. Given a folder, pick the newest result JSON.

    Returns (content, error). A non-empty error means: do not start the run.
    """
    if path.is_dir():
        candidates = [p for p in path.glob("*.json") if p.is_file()]
        if not candidates:
            return None, f"no previous result: no .json inside {path}"
        # By mtime, not by name: a hand-placed file could sort last by name
        # and get picked by mistake.
        path = max(candidates, key=lambda p: p.stat().st_mtime)
        print(f"carry-over file: {path.name}")
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"previous result unreadable: {exc}"
    if not isinstance(content, dict) or "tasks" not in content:
        return None, f"previous result is not a run file: {path}"
    return content, ""


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--task", default="all")
    a.add_argument("--difficulty", default="")
    a.add_argument("--model", default="")
    a.add_argument("--repeat", type=int, default=1)
    a.add_argument("--wait", type=float, default=DEFAULT_WAIT)
    a.add_argument("--keep", action="store_true")
    a.add_argument("--state", default="",
                   help="config/keys source (default: the repo's .neocp)")
    a.add_argument("--previous", default="",
                   help="a previous result JSON (or a results folder: newest "
                        "is picked): tasks not re-run are carried over — for "
                        "re-running one task while producing a complete report")
    args = a.parse_args(argv)

    source_state = Path(args.state) if args.state else (ROOT / ".neocp")
    if not (source_state / "config.json").is_file():
        print(f"config not found: {source_state / 'config.json'}")
        return 2

    # The carry-over file is read BEFORE the run. Reading it at the end
    # meant discovering "wrong path" after hours of paid work.
    previous: dict[str, Any] | None = None
    if args.previous:
        previous, error = _read_previous(Path(args.previous))
        if error:
            print(error)
            return 2

    everything = discover_tasks()
    selected = everything
    if args.difficulty:
        wanted = {d.strip() for d in args.difficulty.split(",") if d.strip()}
        selected = [t for t in selected if t.difficulty in wanted]
    if args.task and args.task != "all":
        ids = {t.strip() for t in args.task.split(",") if t.strip()}
        selected = [t for t in selected if t.id in ids]
    if not selected:
        print("no tasks selected")
        return 2

    model = args.model or _model_name(source_state)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"coding benchmark · model {model} · {len(selected)} tasks × "
          f"{args.repeat} repetitions\n")

    rows: list[dict[str, Any]] = []
    for task in selected:
        print(f"[{task.id}] {task.title} ({task.difficulty}/{task.language})",
              flush=True)
        cards: list[Scorecard] = []
        for rep in range(args.repeat):
            if args.repeat > 1:
                print(f"  rep {rep + 1}/{args.repeat}", flush=True)
            cards.append(run_once(task, source_state, args.model or None,
                                  args.wait, args.keep))
        scores = [c.score for c in cards if c.score is not None]
        spread = ((max(scores) - min(scores)) / 2) if len(scores) > 1 else None
        # Only one card enters the report: the FIRST run, not a median —
        # there is no such thing as an average card, and the evidence dump
        # must belong to a real run.
        rows.append({
            "id": task.id, "title": task.title, "difficulty": task.difficulty,
            "language": task.language,
            "card": cards[0].as_dict(),
            "all_scores": scores,
            "score_spread": spread,
            "broken_deliveries": sum(1 for c in cards if c.broken_delivery),
        })
        first = cards[0].score
        print(f"  → {'unmeasurable' if first is None else f'{first:.1f}/100'}"
              + (f"  (all reps: {[round(x, 1) for x in scores]})"
                 if len(scores) > 1 else "") + "\n", flush=True)

    # Carry-over from a previous run: the way to re-run one task and still
    # produce a COMPLETE report. Carried rows are stamped `carried_from` —
    # which table row came from which run is never hidden.
    for row in rows:
        row["carried_from"] = ""
    if previous is not None:
        fresh = {r["id"] for r in rows}
        carried = [dict(r, carried_from=previous.get("time", "?"))
                   for r in previous.get("tasks", []) if r["id"] not in fresh]
        rows = sorted(rows + carried, key=lambda r: r["id"])
        if carried:
            print("carried over from the previous run: "
                  f"{', '.join(r['id'] for r in carried)}")

    ran = {r["id"] for r in rows}
    not_run = [t.id for t in everything if t.id not in ran]
    result = {
        "time": stamp, "model": model, "repetitions": args.repeat,
        "wait_s": args.wait, "tasks": rows,
        "not_run": not_run,
        "axis_ceilings": grading.AXES,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "-", model or "model")
    (RESULTS_DIR / f"{stamp}-{safe}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(result, RESULTS_DIR / "REPORT.md")
    print(f"result: {RESULTS_DIR / f'{stamp}-{safe}.json'}")
    print(f"report: {RESULTS_DIR / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
