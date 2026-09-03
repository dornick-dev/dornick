"""Outer gate: the HTTP endpoint through which other agents can drive Dornick programmatically.

The purpose is evaluation: an external tool (test runner, scoring agent,
script) writes into the chat like a user, waits for the turn to finish and
receives ALL of the output — the reply text, the tools used, the files that
changed in the workshop during that turn.

The gate is OFF by default and is only enabled from settings; the state is
kept in `gate.json` so it is remembered across restarts. The server already
listens on 127.0.0.1 only — even with the gate open there is no surface
outside the machine.

Collecting the reply runs over two channels, both of them existing
infrastructure:
  * The event log (EventLog.subscribe) — the FULL text of assistant messages
    and the tool calls come from here. The hub's "message" event is clipped
    at 400 characters, so collecting text from the hub was not enough.
  * The hub — the turn boundary ("turn_end") is published only to the hub,
    never written to the log; so we listen for the end there.

Matching: the text we submit lands in the log as a user message; the first
"turn_end" AFTER that is our turn (the queue is FIFO, turns are serial).
Any turn_end arriving before it belongs to other turns and is ignored.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

FILE = "gate.json"

# Directories skipped in the changed-file scan: tool residue, version control.
_SKIP = frozenset({".git", "__pycache__", "node_modules", ".venv", ".geri-donusum"})

# Maximum time to wait for a turn. Long research turns take minutes; but an
# HTTP request that waits forever leaks a thread as well.
DEFAULT_WAIT_S = 600.0
MAX_WAIT_S = 1800.0

# Cap on the file list in the reply: there is no point in enumerating a build output.
FILE_CAP = 200


def status(state_dir: Path) -> bool:
    try:
        return bool(json.loads((state_dir / FILE).read_text(encoding="utf-8")).get("on"))
    except (OSError, ValueError):
        return False


def configure(state_dir: Path, on: bool) -> None:
    (state_dir / FILE).write_text(json.dumps({"on": bool(on)}), encoding="utf-8")


def _texts(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(b.get("text", "")) for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    )


def _changed_files(root: Path, threshold: float) -> list[str]:
    """Files written in the workshop since the turn started (relative path, newest first)."""
    found: list[tuple[float, str]] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP and not d.startswith(".")]
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    mt = path.stat().st_mtime
                except OSError:
                    continue
                if mt >= threshold:
                    found.append((mt, path.relative_to(root).as_posix()))
                    if len(found) >= FILE_CAP:
                        raise StopIteration
    except StopIteration:
        pass
    found.sort(reverse=True)
    return [path for _, path in found]


def ask(
    *,
    controller: Any,
    hub: Any,
    text: str,
    image: str = "",
    wait_s: float = DEFAULT_WAIT_S,
    sandbox_root: Path | None = None,
) -> dict[str, Any]:
    """Hands the message to the agent, waits for the turn to finish, returns all output.

    Blocks in the HTTP thread; since ThreadingHTTPServer gives every request
    its own thread, other requests are unaffected.
    """
    agent = getattr(controller, "agent", None)
    log = getattr(getattr(agent, "session", None), "log", None)
    if log is None:
        return {"ok": False, "error": "ajan hazır değil"}

    wait_s = max(5.0, min(float(wait_s or DEFAULT_WAIT_S), MAX_WAIT_S))
    started = time.time()
    # `busy` is a property on the desktop bridge, may be a method on another controller.
    busy = getattr(controller, "busy", False)
    was_queued = bool(busy() if callable(busy) else busy)

    message_seen = threading.Event()
    awaiting_approval = threading.Event()
    parts: list[str] = []
    tools: list[str] = []

    def listen(ev: Any) -> None:
        if not message_seen.is_set():
            if (
                ev.is_message
                and ev.role == "user"
                and not ev.meta.get("tool_results")
                and not ev.meta.get("continuation")
                and not ev.meta.get("internal")
                and _texts(ev.content).strip() == text.strip()
            ):
                message_seen.set()
            return
        if ev.is_message and ev.role == "assistant" and isinstance(ev.content, list):
            for block in ev.content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and str(block.get("text", "")).strip():
                    parts.append(str(block["text"]))
                elif block.get("type") == "tool_use":
                    tools.append(str(block.get("name", "")))
        elif ev.kind == "meta" and ev.content == "permission":
            # Only a permission that was REALLY asked of the user counts. In
            # `yolo` mode every tool leaves a permission event too; counting
            # all of them as "awaiting approval" made the timeout message
            # point at the wrong place ("approve the permission") every time.
            if str((ev.meta or {}).get("decision") or "") == "ask":
                awaiting_approval.set()

    unsubscribe = log.subscribe(listen)
    channel: queue.Queue[str] = hub.register()
    try:
        # `siraya`: the outer gate's message does NOT barge into the middle
        # of a running turn, it waits for its own — the matching (user
        # message → turn_end) only works that way. Fallback for bridges with
        # the old signature.
        try:
            controller.submit(str(text), str(image or ""), siraya=True)
        except TypeError:
            controller.submit(str(text), str(image or ""))
        deadline = started + wait_s
        finished = False
        while time.time() < deadline:
            try:
                line = channel.get(timeout=min(2.0, max(0.1, deadline - time.time())))
            except queue.Empty:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "turn_end" and message_seen.is_set():
                finished = True
                break
    finally:
        unsubscribe()
        hub.unregister(channel)

    if not finished:
        reason = "tur zaman aşımına uğradı"
        if awaiting_approval.is_set():
            reason += " — bir araç izni onay bekliyor (yetki kipini gevşetin ya da onaylayın)"
        return {"ok": False, "error": reason, "gecen_sn": round(time.time() - started, 1)}

    files: list[str] = []
    if sandbox_root is not None:
        files = _changed_files(Path(sandbox_root), started)

    return {
        "ok": True,
        "yanit": "\n\n".join(parts).strip(),
        "araclar": tools,
        "dosyalar": files,
        "kuyrukta_bekledi": was_queued,
        "gecen_sn": round(time.time() - started, 1),
        "oturum": getattr(getattr(agent, "session", None), "id", ""),
    }
