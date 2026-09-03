"""Mind interface server.

Deliberately standard library only: no aiohttp, no uvicorn, no npm.
SSE is used instead of WebSocket for the live stream — enough for a
one-way stream and, since it runs over plain HTTP, needs no extra
dependency.

The server runs in its own thread; the agent keeps running in the asyncio
loop. The only bridge between the two is the event log's subscription hook.

Binds to 127.0.0.1 only. The agent's memory, goals and past sessions live
here — not a surface to expose outward.
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import queue
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from typing import Any, Protocol

from .. import (listen, environment, sandbox, schedule as scheduling, settings,
                recognition, voice, watch)
from ..config import Config
from ..events import Event, EventLog
from ..mind.store import Mind
from . import gate
from .graph import build_graph

STATIC = Path(__file__).parent / "static"
HEARTBEAT_S = 15.0
QUEUE_LIMIT = 500


def _attachment_disposition(title: str, suffix: str = ".html") -> str:
    """Content-Disposition: the HTTP header is latin-1; a Turkish title goes ASCII + RFC5987.

    `filename=` is ASCII only; `filename*=UTF-8''…` carries the percent-encoded real name.
    """
    raw = str(title or "download").strip() or "download"
    if suffix and not raw.lower().endswith(suffix.lower()):
        display = raw + suffix
    else:
        display = raw
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", display).strip("._") or "download"
    if suffix and not ascii_name.lower().endswith(suffix.lower()):
        ascii_name = ascii_name + suffix
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(display, safe='')}"
    )
# Cap on an item the user types by hand into the goal panel. It sits on a
# single line in the panel; a novel-length item is useless both in the
# panel and in the model's context.
GOAL_TEXT_LIMIT = 200

# Served files are listed explicitly: deriving the path join from the
# request is the classic road to a directory-traversal hole.
ASSETS = {
    "/app.css": "text/css; charset=utf-8",
    "/settings.css": "text/css; charset=utf-8",
    "/logo.png": "image/png",
    "/app.js": "text/javascript; charset=utf-8",
    # Language layer: loaded BEFORE the other scripts (t() and Dil.ekle live in them).
    "/dil.js": "text/javascript; charset=utf-8",
    "/scene.js": "text/javascript; charset=utf-8",
    # Real brain geometry: a decimated point cloud, 42 KB.
    "/brain.js": "text/javascript; charset=utf-8",
    "/md.js": "text/javascript; charset=utf-8",
    "/highlight.js": "text/javascript; charset=utf-8",
    "/settings.js": "text/javascript; charset=utf-8",
    "/viewer.js": "text/javascript; charset=utf-8",
    "/apps.js": "text/javascript; charset=utf-8",
    "/capsule.js": "text/javascript; charset=utf-8",
    "/history.js": "text/javascript; charset=utf-8",
    "/orchestra.js": "text/javascript; charset=utf-8",
    # Camera deck: the watch area (built-in + IP cameras).
    "/cameras.js": "text/javascript; charset=utf-8",
    "/watch.js": "text/javascript; charset=utf-8",
    # Running-tasks panel: background jobs, helpers, processes.
    "/gorevler.js": "text/javascript; charset=utf-8",
    # Composer surfaces: the `/` command book and the `@` file mention.
    "/komut.js": "text/javascript; charset=utf-8",
    # "What changed this turn" strip + undo.
    "/degisiklik.js": "text/javascript; charset=utf-8",
    "/git.js": "text/javascript; charset=utf-8",
    "/workdir.js": "text/javascript; charset=utf-8",
    "/chrome.js": "text/javascript; charset=utf-8",
    # Right-click menu (the user's laptop package): index.html loads it but
    # it had never entered the allow list — right-click was silently dead in
    # the product (404).
    "/menu.js": "text/javascript; charset=utf-8",
    "/speech.js": "text/javascript; charset=utf-8",
    "/listen.js": "text/javascript; charset=utf-8",
    "/camera.js": "text/javascript; charset=utf-8",
    "/drop.js": "text/javascript; charset=utf-8",
    "/workflow.js": "text/javascript; charset=utf-8",
    "/jobs.js": "text/javascript; charset=utf-8",
}

# Meta events streamed to the UI. The rest (session start, permission
# record and the like) do nothing but clutter the graph.
STREAMED_NOTES = frozenset(
    {
        "tool_start",
        "tool_end",
        "tool_cancelled",
        "permission",
        "goal_push",
        "goal_status",
        "mind_write",
        "mind_forget",
        "mind_link",
        "api_error",
        "interrupted",
        "empty_assistant_turn",
        "turn_limit",
        "refusal",
        "recall_trace",
        "queued",
        # Artifact published/updated: shows up as a card in the chat.
        "artifact",
        # Big job plan: approval card.
        "plan",
        # Device record deleted: the scene organ and the settings list must not go stale.
        "device_removed",
        # Git commit/push/publish: refresh the bar and the pane.
        "git",
    }
)


class Controller(Protocol):
    """The surface the UI uses to drive the agent.

    Called from the HTTP thread while the agent runs in another thread's
    asyncio loop. Making the crossing thread-safe is the implementer's job.
    """

    def submit(self, text: str, image: str = "") -> None: ...
    def resolve_approval(
        self, request_id: str, granted: bool, *, always: bool = False
    ) -> None: ...
    def interrupt(self) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...
    def reload(self, config: Config, *, force: bool = False) -> None: ...
    # The endpoints the bridge additionally offers but which are NOT
    # MANDATORY (tasks panel, budget brake, manual compaction) are not
    # here: `_controller_call` silently turns a missing method into None
    # and the endpoint turns that into an honest ok:false. Observe-only
    # bridges (preview, tests) are not forced to implement them.


class Hub:
    """Fans the event log out to the open browser tabs."""

    def __init__(self) -> None:
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()

    def register(self) -> queue.Queue[str]:
        channel: queue.Queue[str] = queue.Queue(maxsize=QUEUE_LIMIT)
        with self._lock:
            self._clients.append(channel)
        return channel

    def unregister(self, channel: queue.Queue[str]) -> None:
        with self._lock:
            if channel in self._clients:
                self._clients.remove(channel)

    def publish(self, event: Event, sid: str = "") -> None:
        if (payload := _payload(event)) is not None:
            if sid:
                payload.setdefault("sid", sid)
            self.emit(payload)

    def emit(self, payload: dict[str, Any]) -> None:
        """Also publishes events that do not come from the log (text stream, approval request)."""
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            clients = tuple(self._clients)
        for channel in clients:
            try:
                channel.put_nowait(line)
            except queue.Full:
                # A slow tab must not slow the agent down; that tab misses a few events.
                pass


def _machine_language() -> str:
    """Default UI language by the machine's language: "tr" or "en".

    Turkish on a Turkish Windows (or if the region is Türkiye); English
    everywhere else. Unreadable → English — that is the product's default.
    """
    try:
        import locale
        tag = ""
        try:
            tag = (locale.getdefaultlocale()[0] or "")
        except (ValueError, TypeError):
            tag = ""
        if not tag:
            try:
                tag = (locale.getlocale()[0] or "")
            except (ValueError, TypeError):
                tag = ""
        tag = tag.lower().replace("-", "_")
        if tag.startswith("tr") or tag.endswith("_tr") or "turkish" in tag:
            return "tr"
    except Exception:
        pass
    return "en"


def _payload(event: Event) -> dict[str, Any] | None:
    if event.kind == "message":
        # Tool results are technically a user turn but must not look like a
        # user message in the chat — the tool card already shows the result.
        if event.meta.get("tool_results"):
            return None
        # The continuation nudge was not typed by the user either; it must
        # not appear in the chat. Same for images coming from a tool and
        # harness notes.
        if event.meta.get("continuation") or event.meta.get("internal"):
            return None
        return {
            "type": "message",
            "role": event.role,
            "ts": event.ts,
            "text": _summarize(event.content),
        }
    if event.content in STREAMED_NOTES:
        return {"type": str(event.content), "ts": event.ts, **event.meta}
    return None


def _summarize(content: Any, limit: int = 400) -> str:
    if isinstance(content, str):
        return content[:limit]
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append(str(block.get("text", "")))
        elif kind == "tool_use":
            parts.append(f"→ {block.get('name')}")
        elif kind == "tool_result":
            parts.append("← sonuç")
    return " ".join(parts)[:limit]


# The body of a file above this size is not sent. The aim is glancing at a
# script/report the agent produced; not dumping a data file into the browser.
PREVIEW_LIMIT = 256 * 1024

# Largest file that can be dropped into the chat. The browser carries the
# content as base64 (a third of bloat) and keeps it in memory.
DROP_LIMIT = 25 * 1024 * 1024

# Extensions whose body is not shown. Everything not on the list is tried
# as text; if it does not decode it counts as binary.
BINARY_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".pdf", ".zip",
     ".gz", ".exe", ".dll", ".so", ".dylib", ".db", ".sqlite", ".wasm",
     ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".mp4", ".webm", ".mov", ".mkv",
     ".ttf", ".otf", ".woff", ".woff2"}
)

# `/api/raw` serves only these types BY NAME. The list is deliberately short
# and closed to media: letting the browser look at the content and guess
# the type (sniffing) could have treated a text file in the workspace as
# HTML and executed it. Everything not on the list is octet-stream —
# downloaded, not interpreted. `.svg` is here too: being XML it can carry
# script, but the viewer draws it with `<img>` — script does not run in an
# image.
RAW_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".ico": "image/x-icon", ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".m4a": "audio/mp4", ".flac": "audio/flac",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
}

# Directories skipped while browsing: things tools leave behind, not what the agent produced.
SKIPPED = frozenset({".git", "__pycache__", "node_modules", ".venv", ".mypy_cache"})

# The `@` file mention in the composer searches on every keystroke: the
# scan MUST be capped. Even in a huge workspace the typing flow is not
# interrupted — on hitting the cap whatever was found is returned and the
# UI says "narrow it down".
SEARCH_SCAN_CAP = 6000
SEARCH_LIMIT = 20

# Maximum text shown in the diff card. Anything larger is unreadable anyway,
# but piling it into the browser locks the panel.
DIFF_LIMIT = 200 * 1024


def _target_summary(args: Any, limit: int = 90) -> str:
    """One-line target from tool arguments: a path or a command.

    What is read in the task dump is "which file / which command" — not raw
    JSON. If no recognised field exists the first text value is used.
    """
    if not isinstance(args, dict):
        return ""
    for key in ("path", "command", "query", "url", "title", "id", "text"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            flat = " ".join(value.split())
            return flat if len(flat) <= limit else flat[:limit] + "…"
    return ""


def _plain_blocks(content: Any) -> list[str]:
    """A message's plain text blocks (tool calls and reasoning left out)."""
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [str(b.get("text") or "") for b in content
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]


def _report_html(text: str) -> str:
    """Turns a task report into safe HTML (light markdown).

    No full markdown engine; heading / list / link / code suffice — the
    report is read in the Viewer instead of sticking to the chat. ## Çıktı
    is a <details> closed by default — long setup logs must not bury the
    summary.
    """
    out: list[str] = []
    in_ul = False
    in_log = False
    log_buf: list[str] = []

    def flush_log() -> None:
        nonlocal in_log, log_buf
        if not in_log:
            return
        raw = "\n".join(log_buf).strip("\n")
        out.append(
            '<details class="log"><summary>Ham çıktı</summary>'
            f"<pre>{html.escape(raw)}</pre></details>"
        )
        in_log = False
        log_buf = []

    for raw_line in (text or "").replace("\r\n", "\n").split("\n"):
        s = raw_line.rstrip()
        # A raw Python trace is not a report — do not print it even if insan_is_raporu let it through.
        if s.startswith("Traceback (") or s.startswith("File \""):
            continue
        if s.startswith("## "):
            flush_log()
            if in_ul:
                out.append("</ul>"); in_ul = False
            heading = s[3:].strip()
            if heading.casefold() in ("çıktı", "cikti", "output"):
                in_log = True
                log_buf = []
                continue
            out.append("<h2>" + _inline_md(heading) + "</h2>")
        elif in_log:
            log_buf.append(raw_line)
        elif s.startswith("### "):
            if in_ul:
                out.append("</ul>"); in_ul = False
            out.append("<h3>" + _inline_md(s[4:]) + "</h3>")
        elif re.match(r"^[-*]\s+", s):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append("<li>" + _inline_md(re.sub(r"^[-*]\s+", "", s)) + "</li>")
        elif not s:
            if in_ul:
                out.append("</ul>"); in_ul = False
            out.append("<br>")
        else:
            if in_ul:
                out.append("</ul>"); in_ul = False
            out.append("<p>" + _inline_md(s) + "</p>")
    if in_ul:
        out.append("</ul>")
    flush_log()
    return "\n".join(out) or "<p><i>(boş rapor)</i></p>"


def _report_cover(result: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """The report page's heading: the command must not be the h1, the task id must not stand out.

    Returns: (tab title, h1, badge HTML, summary text, command text).
    """
    raw_title = str(result.get("title") or "Rapor").strip()
    state = str(result.get("state") or "")
    command = raw_title[2:].strip() if raw_title.startswith("$ ") else ""
    if state == "hata":
        h1 = "İş başarısız"
        badge = '<span class="badge err">Başarısız</span>'
    elif state == "kosuyor":
        h1 = "İş sürüyor"
        badge = '<span class="badge">Sürüyor</span>'
    elif command:
        h1 = "İş tamamlandı"
        badge = '<span class="badge ok">Tamamlandı</span>'
    else:
        h1 = raw_title or "Rapor"
        badge = (
            '<span class="badge ok">Tamamlandı</span>' if state == "bitti"
            else ""
        )
    summary = ""
    for line in str(result.get("metin") or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("- "):
            continue
        summary = s
        break
    if not command and raw_title and raw_title != h1:
        # No command: carry the old title as meta — the raw title when there is no summary.
        if not summary:
            summary = raw_title
    return h1, h1, badge, summary, command


def _inline_md(s: str) -> str:
    t = html.escape(s)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        t,
    )
    return t


def _search_files(root: Path, want: str, *, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
    """Fast file search by name in the workspace (the `@` picker).

    Ordering follows what the user is looking for: name matches first, path
    matches after; within each group the short path leads (root files are
    more likely than their deep copies). An empty query means "most recently
    touched" — a user typing `@` usually wants the file they are working on.
    """
    import os

    in_name: list[tuple[int, str, float]] = []
    in_path: list[tuple[int, str, float]] = []
    everything: list[tuple[str, float]] = []
    scanned = 0
    overflowed = False

    for dirpath, dirnames, filenames in os.walk(root):
        # Hidden and tool folders: neither produced by the agent nor written by the user.
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIPPED and not d.startswith("."))
        for name in filenames:
            if name.startswith("."):
                continue
            scanned += 1
            if scanned > SEARCH_SCAN_CAP:
                overflowed = True
                break
            full = Path(dirpath) / name
            try:
                rel = full.relative_to(root).as_posix()
                mtime = full.stat().st_mtime
            except (OSError, ValueError):
                continue
            if not want:
                everything.append((rel, mtime))
            elif want in name.lower():
                in_name.append((len(rel), rel, mtime))
            elif want in rel.lower():
                in_path.append((len(rel), rel, mtime))
        if overflowed:
            break

    if not want:
        everything.sort(key=lambda r: -r[1])
        chosen = [rel for rel, _ in everything[:limit]]
    else:
        in_name.sort()
        in_path.sort()
        chosen = [rel for _, rel, _ in (in_name + in_path)[:limit]]
    return [{"path": rel, "name": rel.rsplit("/", 1)[-1]} for rel in chosen]


def warm_ear(server: Any, config: Config) -> None:
    """Loads the recognition model in the background.

    Left to the first call, that call holds the HTTP thread while the model
    downloads (once, ~70 s). With background listening on, a new request
    arrives every three seconds and they all pile up in the same place: the
    six connections the browser can open to one origin fill up and
    **everything** queues — even the message the user typed does not go.
    """
    if not config.listen.enabled or not listen.available():
        return

    def warm() -> None:
        try:
            _ear(server, config).load()
        except Exception:
            # If the model did not download it is retried on the first real request.
            pass

    threading.Thread(target=warm, daemon=True, name="dornick-ear").start()


def _ear(server: Any, config: Config) -> Any:
    """Builds the recogniser once and keeps it.

    Reloading the model on every call makes push-to-talk unusable: seconds
    each time. Rebuilt if the setting changes.
    """
    if not listen.available():
        return None
    ear = getattr(server, "_ear", None)
    if ear is None or ear.config != config.listen:
        ear = listen.Listener(config.listen)
        server._ear = ear  # type: ignore[attr-defined]
    return ear


def ear_gate(ear: Any, action: str) -> dict[str, Any]:
    """Composer microphone: mute / unmute the ear. Same gate as the agent's `senses` tool.

    Browser push-to-talk grabs the same microphone a second time and the
    continuous listening does not stop — stopping it was left to the agent
    tool.
    """
    if ear is None:
        return {"ok": True, "ear": False, "snoozed": False}
    act = (action or "status").strip()
    if act == "pause":
        ear.snooze(0)
    elif act == "resume":
        ear.unsnooze()
    elif act == "toggle":
        if ear.snoozed:
            ear.unsnooze()
        else:
            ear.snooze(0)
    return {
        "ok": True,
        "ear": True,
        "snoozed": bool(getattr(ear, "snoozed", False)),
    }


def _as_json(raw: bytes) -> dict[str, Any]:
    """Reads the body as JSON. Empty dict if it is not.

    Raw bodies such as audio pass through the same road; parsing fails for
    them, and rightly so.
    """
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8")) or {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _session_title(digest: str) -> str:
    """The conversation's title: the first few words of the digest.

    Calling the LLM to produce a separate title — one request per session —
    is expensive and unnecessary; the first utterance already gives the topic.
    """
    flat = " ".join((digest or "").split())
    if not flat:
        return "(boş konuşma)"
    words = flat.split(" ")
    # If the first utterance was a one-letter key slip ("e", "b" + Enter)
    # the title locked onto that letter; skip the crumb and start from the
    # first real word.
    while len(words) > 1 and len(words[0]) == 1 and not words[0].isdigit():
        words = words[1:]
    words = words[:8]
    title = " ".join(words)
    return title if len(title) <= 60 else title[:60] + "…"


def _stem_date(stem: str) -> str:
    """20260610T090000Z -> 2026-06-10 09:00. Leaves an unrecognised one as is."""
    m = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})", stem or "")
    if not m:
        return stem
    y, mo, d, h, mi = m.groups()
    return f"{y}-{mo}-{d} {h}:{mi}"


def _starting_places() -> list[dict[str, str]]:
    """The folder picker's opening list: drives and home.

    Drive letters on Windows, root and home elsewhere. The aim is answering
    "where do I start" on the first screen.
    """
    places: list[dict[str, str]] = []
    try:
        home = Path.home()
        places.append({"ad": f"~ ({home.name})", "yol": str(home)})
    except (OSError, RuntimeError):  # pragma: no cover - home may be undefined
        pass

    if os.name == "nt":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:\\")
            try:
                if drive.is_dir():
                    places.append({"ad": f"{letter}:", "yol": str(drive)})
            except OSError:  # pragma: no cover - drive not ready
                continue
    else:  # pragma: no cover - does not run on this machine
        places.append({"ad": "/", "yol": "/"})
    return places


def _project_kind(root: Path) -> str:
    """The label if the folder has a recognised test rig ("pytest" and the like).

    Detection already lives in the `testrun` module; here it is reduced to a
    readable label only. Empty string if none is found — no made-up label.
    """
    try:
        from .. import testrun

        rig = testrun.tespit(root)
    except Exception:  # pragma: no cover - detection is a convenience, stay quiet if it blows
        return ""
    return rig.etiket if rig is not None else ""


def _relative(path: Path, root: Path) -> str:
    return "" if path == root else path.relative_to(root).as_posix()


def _listing(directory: Path, root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    try:
        children = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return entries

    for child in children:
        if child.name in SKIPPED:
            continue
        try:
            info = child.stat()
        except OSError:
            continue
        entries.append({
            "name": child.name,
            "path": _relative(child, root),
            "dir": child.is_dir(),
            "size": 0 if child.is_dir() else info.st_size,
            "mtime": int(info.st_mtime),
        })
    return entries


def _file_payload(path: Path, root: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": _relative(path, root),
        "name": path.name,
        "file": True,
        "size": path.stat().st_size,
    }
    if path.suffix.lower() in BINARY_SUFFIXES:
        payload["binary"] = True
        return payload
    if payload["size"] > PREVIEW_LIMIT:
        payload["truncated"] = True

    try:
        payload["text"] = path.read_bytes()[:PREVIEW_LIMIT].decode("utf-8")
    except (OSError, UnicodeDecodeError):
        payload["binary"] = True
    return payload


class MindServer:
    def __init__(
        self,
        mind: Mind,
        log: EventLog,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        controller: Controller | None = None,
        hub: Hub | None = None,
        config: Config | None = None,
        schedule: Any = None,
    ) -> None:
        self.mind = mind
        # The settings page reads from and writes to this. Without it the
        # page does not open — as in a UI preview running without an agent.
        self.config = config
        # Scheduled tasks: an automation the agent set up must not run
        # hidden from the user, so it can be managed from the UI as well.
        self.schedule = schedule
        # The hub must be injectable: the desktop bridge publishes its own
        # events (text stream, approval request) over the same channel. If
        # the server built its own hub and swapped it later, the
        # subscription and the publishing would part ways and events from
        # the log would silently vanish.
        self.hub = hub or Hub()
        self._unsubscribe = log.subscribe(self.hub.publish)
        # Is the port REALLY free? On Windows ThreadingHTTPServer's default
        # SO_REUSEADDR silently allows binding a second time on top of an
        # occupied port — connections go to the OLD process and the window
        # showed whatever application held that port instead of dornick
        # (live, 29.08: on the laptop an old workshop panel held 8765 and
        # dornick opened with a page "not its own"). The fix is two-layered:
        # a server class with the takeover permission off + sliding to the
        # next free port when occupied. The real address is always read from
        # `url`; the window uses that too.
        last_error: OSError | None = None
        for candidate in range(int(port), int(port) + 20):
            try:
                self._httpd = _SoleOwnerServer((host, candidate), _Handler)
                if candidate != int(port):
                    print(f"[dornick] {port} portu dolu — arayüz {candidate} portunda",
                          flush=True)
                break
            except OSError as exc:
                last_error = exc
        else:
            raise OSError(
                f"{port}-{int(port) + 19} arası hiçbir port boş değil"
            ) from last_error
        self._httpd.daemon_threads = True
        # Handlers reach these through the server.
        self._httpd.mind = mind  # type: ignore[attr-defined]
        self._httpd.hub = self.hub  # type: ignore[attr-defined]
        self._httpd.controller = controller  # type: ignore[attr-defined]
        self._httpd.config = config  # type: ignore[attr-defined]
        self._httpd.schedule = schedule  # type: ignore[attr-defined]
        # The always-listening ear and the camera buffer are attached later:
        # during startup the server comes up before either of them.
        self._httpd.ear = None  # type: ignore[attr-defined]
        self._httpd.lens = None  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def rebind(self, session: Any) -> None:
        """Attaches the event stream to a new session's log.

        When switching to a new or resumed conversation, if the SSE stream
        kept listening to the old log the new messages never reached the UI.
        The old subscription is dropped and a new one is made; the mind's
        session id is updated too so new memories are written to the right
        session.
        """
        try:
            self._unsubscribe()
        except Exception:
            pass
        # Log events are stamped with the session id as well: the
        # subscription swap can race at the moment of switching and a queued
        # event of the old log could land on the new screen — the UI does
        # not draw one whose id does not match.
        sid = str(getattr(session, "id", "") or "")
        self._unsubscribe = session.log.subscribe(
            lambda ev, _sid=sid: self.hub.publish(ev, sid=_sid))
        self.mind.session_id = session.id
        self._httpd.mind = self.mind  # type: ignore[attr-defined]

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}/"

    def start(self) -> str:
        self._thread.start()
        return self.url

    def stop(self) -> None:
        self._unsubscribe()
        # shutdown() waits for the serve_forever loop to finish; if the loop
        # never started it waits forever. Stopping a server that was never
        # started must not hang silently.
        if self._thread.is_alive():
            self._httpd.shutdown()
        self._httpd.server_close()


class _SoleOwnerServer(ThreadingHTTPServer):
    """A server that is the sole owner of its port.

    On Windows SO_REUSEADDR accepts binding on top of a port another process
    is listening on WITHOUT an error, and the traffic flows to the first
    owner. With it off, binding on an occupied port fails honestly; the
    layer above can then slide to a free port.
    """

    allow_reuse_address = sys.platform != "win32"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:
        """Do not litter the terminal with request logs — the agent's output lives there."""

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """Sends an error — without Turkish messages crashing the status line.

        The HTTP status line must be latin-1. Sending "Sesli komut kapalı"
        made the stdlib raise `UnicodeEncodeError`, the handler died and the
        connection closed **without a reply**. On the client side this
        looked like "nothing happens".

        The fix: an ASCII counterpart on the status line, the real text in
        the body. The UI reads the body anyway.
        """
        reason = (message or "").encode("ascii", "replace").decode("ascii")
        super().send_error(code, reason or None, explain=message)

    def handle_one_request(self) -> None:
        """Swallow a dropped connection quietly.

        When a browser tab closes or a keep-alive socket times out,
        socketserver prints a huge stack trace. This is a normal event; it
        must not look like an error in the agent's terminal.
        """
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - stdlib interface
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            self._file("index.html", "text/html; charset=utf-8")
        elif route in ("/watch.html", "/watch"):
            self._file("watch.html", "text/html; charset=utf-8")
        elif route == "/logo.png":
            self._logo_png()
        elif route in ASSETS:
            self._file(route.lstrip("/"), ASSETS[route])
        elif route == "/api/graph":
            self._json(build_graph(self.server.mind))  # type: ignore[attr-defined]
        elif route == "/api/organs":
            self._organs()
        elif route == "/api/state":
            self._json(self._controller_call("snapshot") or {"busy": False})
        elif route == "/api/uyku":
            self._sleep_status()
        elif route == "/api/gece":
            self._night_list()
        elif route.startswith("/api/gece/"):
            self._night_replay(route[len("/api/gece/"):])
        elif route == "/api/gate":
            config = getattr(self.server, "config", None)
            on = gate.status(config.state_dir) if config is not None else False
            self._json({"on": on})
        elif route == "/api/tanima":
            config = getattr(self.server, "config", None)
            d = (recognition.status(config.state_dir) if config is not None
                 else {"on": False, "son_kosu": ""})
            self._json({"on": d["on"], "kosuyor": recognition.running(),
                        "hazir": recognition.hazir(), "son": d["son_kosu"],
                        "learn_cloud_ok": d.get("learn_cloud_ok", False)})
        elif route == "/api/dil":
            # The UI language the setup wizard chose. localStorage cannot be
            # written from the installer; the wizard drops setup.json into
            # the workspace and dil.js reads it from here on first launch
            # and writes it to itself. Older versions left the same file
            # under the name kurulum.json; if setup.json is missing that one
            # is consulted too — existing installs do not break. If the
            # wizard left no language, the MACHINE's language is consulted:
            # Turkish if Türkiye/Turkish, English otherwise. A Turkish
            # default made the product look closed to the world (user
            # request, 02.09) — the source strings stay Turkish, only the
            # default display language changes.
            config = getattr(self.server, "config", None)
            lang = ""
            if config is not None:
                for name in ("setup.json", "kurulum.json"):
                    try:
                        lang = str(json.loads(
                            (config.workspace / name).read_text(encoding="utf-8")
                        ).get("dil") or "")
                    except (OSError, ValueError):
                        lang = ""
                    if lang:
                        break
            self._json({"dil": lang or _machine_language()})
        elif route == "/api/settings":
            self._settings()
        elif route == "/api/files":
            self._files()
        elif route == "/api/files/search":
            self._files_search()
        elif route == "/api/gorevler":
            self._json(self._controller_call("tasks") or {"gorevler": [], "kosan": 0})
        elif route == "/api/gorevler/dokum":
            self._task_dump()
        elif route == "/api/gorevler/rapor":
            self._task_report()
        elif route == "/api/jobs":
            self._jobs_list()
        elif route == "/api/jobs/runs":
            self._jobs_runs()
        elif route == "/api/workflows":
            self._workflows_list()
        elif route == "/api/plans":
            self._plans_list()
        elif route == "/api/git":
            self._git_status()
        elif route.startswith("/gorev-rapor/"):
            self._task_report_page(route)
        elif route == "/api/degisiklikler":
            self._changes()
        elif route == "/api/degisiklikler/fark":
            self._change_diff()
        elif route == "/api/camera/frame":
            self._camera_frame()
        elif route == "/api/raw":
            self._raw_file()
        elif route == "/api/gozat":
            self._browse()
        elif route == "/api/apps":
            self._apps()
        elif route == "/api/projects":
            self._projects()
        elif route == "/api/apps/running":
            self._apps_running()
        elif route == "/api/artifacts":
            self._artifacts_list()
        elif route.startswith("/artifact/"):
            self._artifact_page(route)
        elif route == "/api/transfer/export":
            self._transfer_export()
        elif route == "/api/sessions":
            self._sessions()
        elif route == "/api/session":
            self._session()
        elif route == "/api/events":
            self._stream()
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802 - stdlib interface
        route = self.path.split("?", 1)[0]
        # The body is read once. Parsing it as JSON first and then trying to
        # read the raw form again left requests hanging forever: the audio
        # request's body is raw audio, not JSON, and the second read waits
        # for bytes that will never come. Once that request held a thread
        # the browser's connection quota filled and **everything** locked up.
        raw = self._raw()
        body = _as_json(raw)

        # Cross-origin protection: if a foreign page in ANOTHER browser tab
        # of the user's fires a state-changing POST at 127.0.0.1 (drive-by
        # CSRF) it is rejected. Our own UI is same-origin → passes; with no
        # Origin/Referer at all (curl, tests, benchmark, local automation)
        # it passes — at the HTTP layer a local process cannot be told apart
        # from the UI, and that road is already guarded by the shell
        # permission gate. The real and preventable threat being closed is
        # a foreign ORIGIN (security audit, 01.09).
        if self._is_cross_origin():
            self.send_error(403, "Capraz koken istegi reddedildi")
            return

        # Settings are independent of the agent: the agent may never have
        # started because the model was misconfigured, and this is exactly
        # the place to fix that.
        if route == "/api/settings":
            self._save_settings(body)
            return
        if route == "/api/detect-window":
            self._detect_window()
            return
        if route == "/api/loaded":
            self._loaded()
            return
        if route == "/api/models":
            self._models(body)
            return
        if route == "/api/tasks":
            self._tasks(body)
            return
        if route == "/api/jobs":
            self._jobs_action(body)
            return
        if route == "/api/workflows":
            self._workflows_action(body)
            return
        if route == "/api/plans":
            self._plans_action(body)
            return
        if route == "/api/git":
            self._git_action(body)
            return
        if route == "/api/rules":
            self._rules(body)
            return
        if route == "/api/cameras":
            self._cameras(body)
            return
        if route == "/api/devices":
            self._devices(body)
            return
        if route == "/api/skills":
            self._skills(body)
            return
        if route == "/api/connectors":
            self._connectors(body)
            return
        if route == "/api/apps/run":
            self._run_app(body)
            return
        if route == "/api/apps/stop":
            from .. import apps as catalog
            pid = (body or {}).get("pid")
            if not isinstance(pid, int):
                self._json({"ok": False, "error": "`pid` gerekli"})
                return
            self._json(catalog.stop(pid))
            return
        if route == "/api/apps/remove":
            # Deleting from the panel: not permanent — moves to the
            # workshop's .geri-donusum. `base` is required: project paths
            # arrive relative to the workspace ("atolye/…"); resolving
            # without base missed as atolye/atolye/….
            from .. import apps as catalog
            config = getattr(self.server, "config", None)
            path = str((body or {}).get("path") or "").strip()
            if config is None or not path:
                self._json({"ok": False, "error": "`path` gerekli"})
                return
            self._json(catalog.remove(config.open_sandbox().root, path,
                                      base=Path(config.workspace)))
            return
        if route == "/api/apps/open":
            # Open OUTSIDE the system (default application/browser): a
            # static web page works fully from a file, without a server.
            from .. import apps as catalog
            config = getattr(self.server, "config", None)
            path = str((body or {}).get("path") or "").strip()
            if config is None or not path:
                self._json({"ok": False, "error": "`path` gerekli"})
                return
            self._json(catalog.open_path(config.open_sandbox().root, path,
                                         base=self._opening_base(config)))
            return
        if route == "/api/apps/file-open":
            # Open the file in the system's DEFAULT application (PDF, docx,
            # png…). The short road to a report the agent produced (live
            # wound, 02.09).
            from .. import apps as catalog
            config = getattr(self.server, "config", None)
            path = str((body or {}).get("path") or "").strip()
            if config is None or not path:
                self._json({"ok": False, "error": "`path` gerekli"})
                return
            self._json(catalog.sistemde_ac(config.open_sandbox().root, path,
                                           base=self._opening_base(config)))
            return
        if route == "/api/apps/reveal":
            # "Show folder": opens the application's place on disk in the
            # file explorer. The user should not have to find by hand the
            # path written on the card.
            from .. import apps as catalog
            config = getattr(self.server, "config", None)
            path = str((body or {}).get("path") or "").strip()
            if config is None or not path:
                self._json({"ok": False, "error": "`path` gerekli"})
                return
            self._json(catalog.reveal(config.open_sandbox().root, path,
                                      base=self._opening_base(config)))
            return
        if route == "/api/artifacts":
            self._artifacts_edit(body)
            return
        if route == "/api/disari-ac":
            self._open_outside(body)
            return
        if route == "/api/artifact/indir":
            self._artifact_download(body)
            return
        if route == "/api/transfer/import":
            self._transfer_import(raw)
            return
        if route == "/api/reset":
            self._reset(body)
            return
        if route == "/api/gorevler/durdur":
            result = self._controller_call("stop_task", str((body or {}).get("id") or ""))
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Görev durdurma desteklenmiyor."})
            return
        if route == "/api/gorevler/devam":
            result = self._controller_call(
                "resume_task",
                str((body or {}).get("id") or ""),
                str((body or {}).get("message") or ""),
            )
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Görev sürdürme desteklenmiyor."})
            return
        if route == "/api/gorevler/iptal":
            result = self._controller_call(
                "gorev_iptal", str((body or {}).get("id") or ""))
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Görev iptali desteklenmiyor."})
            return
        if route == "/api/degisiklikler/geri":
            self._change_undo(body)
            return
        if route == "/api/butce":
            result = self._controller_call("butce", (body or {}).get("usd"))
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Bütçe freni bu köprüde yok."})
            return
        if route == "/api/compact":
            result = self._controller_call("compact_now")
            self._json(result if isinstance(result, dict)
                       else {"ok": False, "error": "Sıkıştırma bu köprüde yok."})
            return
        if route == "/api/session/new":
            # A live new session depends on the bridge: the event stream has
            # to be re-attached to the new log. If the bridge does not
            # support it (e.g. an observe-only preview) it honestly returns
            # ok:false.
            result = self._controller_call("new_session")
            self._json(result if isinstance(result, dict) else {"ok": False})
            return
        if route == "/api/open":
            # Windows 'Open with Dornick' / second-instance handoff.
            path = str((body or {}).get("path") or "").strip()
            message = str((body or {}).get("message") or "")
            controller = getattr(self.server, "controller", None)
            fn = getattr(controller, "open_path", None) if controller else None
            if not callable(fn):
                self._json({"ok": False, "error": "açma desteği yok"})
                return
            self._json(fn(path, message=message))
            return
        if route == "/api/session/resume":
            sid = str((body or {}).get("id") or "").strip()
            if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
                self._json({"ok": False, "error": "geçersiz oturum"})
                return
            result = self._controller_call("resume_session", sid)
            self._json(result if isinstance(result, dict) else {"ok": False})
            return
        if route == "/api/session/project":
            mind = getattr(self.server, "mind", None)
            sid = str((body or {}).get("id") or "").strip()
            if mind is None or not hasattr(mind, "set_project"):
                self._json({"ok": False, "error": "proje desteği yok"})
                return
            if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
                self._json({"ok": False, "error": "geçersiz oturum"})
                return
            mapping = mind.set_project(sid, str((body or {}).get("project") or ""))
            self._json({"ok": True, "projects": sorted(set(mapping.values()))})
            return
        if route == "/api/session/meta":
            # Naming and tagging a conversation. The raw log does not change
            # — only the mapping file beside it (see mind.store).
            mind = getattr(self.server, "mind", None)
            sid = str((body or {}).get("id") or "").strip()
            if mind is None or not hasattr(mind, "set_session_meta"):
                self._json({"ok": False, "error": "oturum meta desteği yok"})
                return
            if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
                self._json({"ok": False, "error": "geçersiz oturum"})
                return
            # A field that was NOT SENT is left untouched: a request that
            # only changes tags must not erase the name.
            name = body.get("ad") if isinstance(body, dict) else None
            tags = body.get("etiketler") if isinstance(body, dict) else None
            path = body.get("path") if isinstance(body, dict) else None
            model = body.get("model") if isinstance(body, dict) else None
            provider = body.get("provider") if isinstance(body, dict) else None
            # `:batch` is a 404 in live chat — reduce to the synchronous id.
            if isinstance(model, str) and model.strip():
                from ..settings import batch_only_model
                if batch_only_model(model):
                    model = model.strip().rsplit(":", 1)[0]
            record = mind.set_session_meta(
                sid,
                ad=None if name is None else str(name),
                etiketler=None if not isinstance(tags, list) else tags,
                path=None if path is None else str(path),
                model=None if model is None else str(model),
                provider=None if provider is None else str(provider),
            )
            # If the chat model changed on the ACTIVE session it is applied
            # at once — no "I saved it but it still talks with the old model".
            if model is not None or provider is not None:
                controller = getattr(self.server, "controller", None)
                active = str(getattr(mind, "session_id", "") or "")
                if controller is not None and sid == active                         and hasattr(controller, "apply_session_context"):
                    try:
                        controller.apply_session_context(sid)
                    except Exception:
                        pass
            self._json({"ok": True, "meta": record})
            return
        if route == "/api/session/archive":
            # Drop from the list, move the log to sessions/.arsiv. No
            # permanent deletion. A running lane's log is not moved; the
            # open chat first switches to a new empty session, then the old
            # one is archived.
            mind = getattr(self.server, "mind", None)
            sid = str((body or {}).get("id") or "").strip()
            if mind is None or not hasattr(mind, "archive_session"):
                self._json({"ok": False, "error": "arşiv desteği yok"})
                return
            if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
                self._json({"ok": False, "error": "geçersiz oturum"})
                return
            controller = getattr(self.server, "controller", None)
            lanes = getattr(controller, "seritler", None) or {}
            lane = lanes.get(sid) if isinstance(lanes, dict) else None
            if lane is not None and getattr(lane, "busy", False):
                self._json({"ok": False,
                            "error": "koşan sohbet arşivlenemez — tur bitince dene"})
                return
            current = str(getattr(mind, "session_id", "") or "")
            if sid == current:
                result = self._controller_call("new_session")
                if not isinstance(result, dict) or not result.get("ok"):
                    self._json(result if isinstance(result, dict) else {
                        "ok": False, "error": "yeni sohbete geçilemedi",
                    })
                    return
            self._json(mind.archive_session(sid))
            return
        if route == "/api/surum":
            # The update check is MANUAL only: the button under Settings ›
            # Machine. There is deliberately no check that goes out to the
            # network by itself in the background. POST: an action that hits
            # the network — must not be triggered by accident via GET.
            self._json(environment.check_update())
            return
        if route == "/api/guncelle":
            self._run_update()
            return
        if route == "/api/klasor/olustur":
            self._create_folder(body)
            return
        if route == "/api/gate":
            self._gate(body)
            return
        if route == "/api/tanima":
            self._recognition(body)
            return
        if route == "/api/goals":
            self._goals(body)
            return
        if route == "/api/drop":
            self._drop(body)
            return
        if route == "/api/speak":
            self._speak(body)
            return
        if route == "/api/voices":
            self._voices()
            return
        if route == "/api/hear":
            self._hear(raw)
            return
        if route == "/api/speaking":
            # The ear closes while the agent speaks: the sound from the
            # speaker came back into the microphone and the assistant heard
            # its own sentence and tried to answer it.
            ear = getattr(self.server, "ear", None) or getattr(
                getattr(self.server, "controller", None), "ear", None)
            if ear is not None:
                ear.speaking(bool(body.get("on")), text=str(body.get("text") or ""))
            self._json({"ok": True})
            return
        if route == "/api/senses":
            action = str((body or {}).get("action") or "status")
            what = str((body or {}).get("what") or "hearing")
            ctrl = getattr(self.server, "controller", None)
            if action in ("on", "off", "power"):
                on = action == "on" or (
                    action == "power" and bool((body or {}).get("enabled")))
                if action == "off":
                    on = False
                fn = getattr(ctrl, "voice_power" if what == "voice" else "hearing_power", None)
                if fn is None:
                    self._json({"ok": False, "error": "anahtar yok"})
                    return
                note = fn(on)
                self._json({"ok": True, "note": note, "enabled": on})
                return
            self._json(ear_gate(
                getattr(self.server, "ear", None),
                action,
            ))
            return
        if route == "/api/wake":
            # The wake word was heard on the browser side (listen.js): if
            # the window is hidden it must come back, otherwise the answer
            # flows in an invisible window. The Python-side ear calls the
            # bridge directly; this was the browser side's only road and
            # the route DID NOT EXIST — the request silently returned 404.
            # The behaviour that brings the window forward already lives in
            # the bridge (Bridge.wake → on_wake); this only opens the door.
            # If the bridge does not support waking (observe-only preview)
            # honestly ok:false — saying "done" is worse than not doing it.
            can_wake = callable(
                getattr(getattr(self.server, "controller", None), "wake", None))
            if can_wake:
                self._controller_call("wake")
            self._json({"ok": can_wake})
            return

        controller = getattr(self.server, "controller", None)
        if controller is None:
            self.send_error(503, "Ajan bağlı değil")
            return

        if route == "/api/chat":
            text = str(body.get("text") or "").strip()
            # A frame from the camera can be sent without text too ("look at this").
            image = str(body.get("image") or "")
            if not text and not image:
                self._json({"ok": False, "error": "boş mesaj"})
                return
            # A WRITTEN stop counts as an interrupt too. The spoken "dur" and
            # the Stop button cut the turn, but typing "durdur" into the
            # composer went into the QUEUE like an ordinary message — the
            # user lived "I said stop, it is still running". The same words
            # (one-to-one with desktop._is_stop) trigger an interrupt here
            # as well; not processed as a message.
            if not image:
                from ..desktop import _is_stop
                if _is_stop(text):
                    controller.interrupt()
                    hub = getattr(self.server, "hub", None)
                    if hub is not None:
                        hub.emit({"type": "notice", "text": "Durduruldu."})
                    self._json({"ok": True, "stopped": True})
                    return
            controller.submit(text, image)
        elif route == "/api/approve":
            controller.resolve_approval(
                str(body.get("id") or ""),
                bool(body.get("granted")),
                always=bool(body.get("always")),
            )
        elif route == "/api/interrupt":
            controller.interrupt()
        else:
            self.send_error(404)
            return

        self._json({"ok": True})

    # -- outer gate -----------------------------------------------------

    def _gate(self, body: dict[str, Any]) -> None:
        """Outer gate: switch on/off or ask a question.

        If the body has `on` the switch is flipped (comes from the settings
        page); if it has `text` and the gate is open, the message is handed
        to the agent and we wait until the turn ends, returning ALL output.
        Both on one endpoint because both are faces of the same concept and
        the tool outside memorises a single address.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        if "on" in (body or {}):
            gate.configure(config.state_dir, bool(body.get("on")))
            self._json({"ok": True, "on": gate.status(config.state_dir)})
            return

        if not gate.status(config.state_dir):
            self._json({"ok": False, "error": "dış kapı kapalı — ayarlar › makine'den açılır"})
            return

        text = str((body or {}).get("text") or "").strip()
        if not text:
            self._json({"ok": False, "error": "`text` gerekli"})
            return
        controller = getattr(self.server, "controller", None)
        hub = getattr(self.server, "hub", None)
        if controller is None or hub is None:
            self.send_error(503, "Ajan bağlı değil")
            return

        try:
            root = config.open_sandbox().root
        except Exception:
            root = None
        try:
            wait_s = float(body.get("bekle_sn") or gate.DEFAULT_WAIT_S)
        except (TypeError, ValueError):
            wait_s = gate.DEFAULT_WAIT_S
        try:
            self._json(gate.ask(
                controller=controller,
                hub=hub,
                text=text,
                image=str(body.get("image") or ""),
                wait_s=wait_s,
                sandbox_root=root,
            ))
        except Exception as exc:
            # An error at the gate must not silently cut the outside tool's
            # connection; the reason must go out as JSON.
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    # -- recognise me ---------------------------------------------------

    def _sleep_status(self) -> None:
        """What the thalamus ring reads: pressure, debt, rhythm, status.

        The UI does NOT LOOK at `recall.db` directly. A UI reading while the
        night writes would show a half-consolidated graph as if it were
        true; this endpoint and the event stream are the only road without
        that race.
        """
        config = getattr(self.server, "config", None)
        mind = getattr(self.server, "mind", None)
        if config is None or mind is None:
            self._json({"durum": "bilinmiyor"})
            return
        try:
            from ..recall import awake, sleep

            pressure = sleep.pressure(mind.store, config.sessions_dir,
                                      watermark=config.state_dir / "filigran.json")
            clock, pending = awake.sleep_debt(
                config.sessions_dir,
                watermark=config.state_dir / "filigran.json")
            self._json({
                "basinc": pressure.as_dict(),
                "esik": {"ust": sleep.UPPER_THRESHOLD, "alt": sleep.LOWER_THRESHOLD},
                "borc": {"saat": round(clock, 2), "oturum": pending},
                "sicak_oran": mind.store.hot_share(),
            })
        except Exception as err:
            self._json({"durum": "okunamadı", "hata": str(err)})

    def _night_list(self) -> None:
        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"geceler": []})
            return
        from ..recall import night_events

        self._json({"geceler": night_events.nights(config.state_dir)})

    def _night_replay(self, date: str) -> None:
        """One night's events, in the order they happened. This is the replay."""
        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"olaylar": [], "ozet": {}})
            return
        from ..recall import night_events

        path = night_events.night_path(config.state_dir, date)
        events = list(night_events.replay(path))
        self._json({"tarih": path.stem, "olaylar": events,
                    "ozet": night_events.summary(events)})

    def _recognition(self, body: dict[str, Any]) -> None:
        """Recognise me: switch on/off or start right now.

        If the body has `on` the switch is flipped (comes from the settings
        page) and on switching on it is tried once without waiting for the
        watchdog; if it has `simdi` it is started skipping the interval
        condition — the road for live verification and the "don't wait for
        the night" request. Same pattern as the gate (`/api/gate`): one
        endpoint, two faces.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        hub = getattr(self.server, "hub", None)

        if "learn_cloud_ok" in (body or {}):
            # Privacy consent: explicit permission for night labelling with
            # the cloud model. Separate branch — does not come together with
            # "on", it drops on its own from the sub-switch on the settings
            # page.
            recognition.set_cloud_consent(config.state_dir,
                                      bool(body.get("learn_cloud_ok")))
            self._json({"ok": True,
                        "learn_cloud_ok": bool(body.get("learn_cloud_ok"))})
            return
        if "on" in (body or {}):
            recognition.configure(config.state_dir, bool(body.get("on")))
            # The icon in the top bar should blink together with the switch:
            # the state change is announced over SSE too — the settings page
            # and the chat tab are separate clients, one cannot see the other.
            if hub is not None:
                hub.emit({"type": "tanima",
                          "state": "acik" if body.get("on") else "kapali"})
            if body.get("on") and hub is not None:
                recognition.maybe_start(config.state_dir, hub)
        elif (body or {}).get("simdi"):
            # "Train now" MUST NOT STAY SILENT: the result goes back to the
            # user. The old state showed nothing on pressing the button —
            # while the loop started, said "too little new data" within a
            # second and exited.
            reason = ("duzenek_yok" if hub is None
                      else recognition.maybe_start(config.state_dir, hub, zorla=True))
            d = recognition.status(config.state_dir)
            self._json({"ok": reason == "basladi", "sebep": reason,
                        "on": d["on"], "kosuyor": recognition.running(),
                        "hazir": recognition.hazir(), "son": d["son_kosu"]})
            return

        d = recognition.status(config.state_dir)
        self._json({"ok": True, "on": d["on"], "kosuyor": recognition.running(),
                    "hazir": recognition.hazir(), "son": d["son_kosu"]})

    # -- settings -------------------------------------------------------

    def _settings(self) -> None:
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        self._json(settings.snapshot(config))

    def _save_settings(self, body: dict[str, Any]) -> None:
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        try:
            updated = settings.apply(config, body)
        except (ValueError, OSError) as exc:
            # Silently swallowing a broken value turns into a program that
            # does not start; the reason must be visible on the settings page.
            self._json({"ok": False, "error": str(exc)})
            return

        self.server.config = updated  # type: ignore[attr-defined]
        # If the key changed the client must be rebuilt: since the key is
        # not part of ModelConfig the model looks "unchanged" and the old
        # client stayed with the old key. `force` makes it refresh.
        keys_changed = bool(body.get("keys"))
        if (controller := getattr(self.server, "controller", None)) is not None:
            reload = getattr(controller, "reload", None)
            if reload is not None:
                try:
                    reload(updated, force=keys_changed)
                except TypeError:
                    # Old signature (no force) — apply anyway.
                    reload(updated)

        self._json({"ok": True, "settings": settings.snapshot(updated)})

    def _detect_window(self) -> None:
        """Asks the server for the model's real context window.

        A wrong window setting never triggers compaction and the server
        silently drops the head of the prompt; instead of guessing we ask.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        caps = settings.detect_caps(config)
        payload: dict[str, Any] = {
            "window": caps.get("max_context") if isinstance(caps.get("max_context"), int) else None,
        }
        for key in ("thinking", "vision", "tools"):
            if key in caps:
                payload[key] = caps[key]
        self._json(payload)

    def _loaded(self) -> None:
        """Models sitting loaded on the server. Several copies of the same
        model means memory going to waste."""
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        self._json({"models": settings.loaded_models(config)})

    def _models(self, body: dict[str, Any] | None = None) -> None:
        """The model ids the server offers; typing them by hand invites mistakes.

        A provider not yet saved can be queried too. On the settings page,
        when a provider was clicked the change was not saved yet and the
        catalogue came from the old server: the user switched to LM Studio
        and saw OpenRouter's model list.
        """
        from dataclasses import replace

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        wanted = {
            key: value
            for key, value in (body or {}).items()
            if key in ("base_url", "provider", "api_key_env") and value is not None
        }
        if wanted:
            config = replace(config, model=replace(config.model, **wanted))

        self._json(settings.scan_models_result(config))

    # -- watched cameras --------------------------------------------------

    def _cameras(self, body: dict[str, Any]) -> None:
        """Lists and edits the watched cameras.

        A change takes effect after a restart: the watcher runs in its own
        thread and adding/removing a camera while it runs means stepping
        into the middle of an open stream.
        """
        from uuid import uuid4

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        cameras = watch.load(config.state_dir)
        action = str(body.get("action") or "list")
        camera_id = str(body.get("id") or "")

        if action == "power":
            on = bool(body.get("enabled"))
            ctrl = getattr(self.server, "controller", None)
            power = getattr(ctrl, "camera_power", None) if ctrl else None
            if power is None:
                self._json({"ok": False, "error": "kamera anahtarı yok"})
                return
            msg = power(on)
            lens = (
                getattr(ctrl, "lens", None)
                or getattr(self.server, "lens", None)
                or getattr(getattr(self.server, "_httpd", None), "lens", None)
            )
            self._json({
                "ok": True,
                "note": msg,
                "enabled": on,
                "live": bool(getattr(lens, "running", False)),
            })
            return

        if action == "add":
            kind = str(body.get("kind") or "usb").strip() or "usb"
            source = str(body.get("source") or "").strip()
            host = str(body.get("host") or "").strip()
            if kind == "usb":
                source = source or str(body.get("index") or "0").strip() or "0"
            cameras.append(
                watch.Camera(
                    id=f"cam_{uuid4().hex[:8]}",
                    name=str(body.get("name") or "").strip()
                         or ("Bilgisayar kamerası" if kind == "usb" and source in ("", "0")
                             else "kamera"),
                    source=source,
                    kind=kind,
                    host=host,
                    port=int(body.get("port") or 0),
                    path=str(body.get("path") or "").strip(),
                    user=str(body.get("user") or "").strip(),
                    password=str(body.get("password") or ""),
                    sensitivity=float(body.get("sensitivity") or 0.06),
                    cooldown_s=int(body.get("cooldown_s") or 60),
                    ask=str(body.get("ask") or ""),
                    analyze=bool(body["analyze"]) if "analyze" in body else True,
                )
            )
        elif action == "update":
            known = set(watch.Camera.__dataclass_fields__)
            for camera in cameras:
                if camera.id != camera_id:
                    continue
                new_pass = body.get("password")
                for name, value in body.items():
                    if name in known and name not in ("id", "password"):
                        setattr(camera, name, value)
                if new_pass:
                    camera.password = str(new_pass)
        elif action == "remove":
            cameras = [c for c in cameras if c.id != camera_id]

        if action in ("add", "update", "remove"):
            watch.save(config.state_dir, cameras)

        # The hardware truth is visible (live request): with a GPU it is a
        # candidate for the continuous watch/processing stage; without one
        # the only mode is "snapshot when asked". The minimum expectation is
        # written too — the user should be able to read from the screen
        # what is off and why.
        try:
            from .. import gpu as gpu_mod
            gpus = [{"name": g.name, "total_mb": g.total_mb,
                     "free_mb": g.free_mb} for g in gpu_mod.nvidia_gpus()]
        except Exception:
            gpus = []
        from .. import sight as sight_mod
        if config.camera.enabled:
            sight_mod.ensure_warmup()
        eye = sight_mod.status()
        has_gpu = any(g["total_mb"] >= 4096 for g in gpus)
        if eye.get("ready"):
            mode = "gpu"
        elif has_gpu:
            mode = "izleme"
        else:
            mode = "kesit"
        self._json({
            "ok": True,
            "available": watch.available(),
            # Master switch of local camera use (Settings › Camera): the
            # status icon at the top is fed from here.
            "enabled": bool(config.camera.enabled),
            "live": bool(getattr(getattr(self.server, "lens", None), "running", False)
                         or getattr(getattr(getattr(self.server, "controller", None), "lens", None), "running", False)),
            "cloud_ok": bool(getattr(config.camera, "cloud_ok", False)),
            "cameras": [c.public_dict() for c in cameras],
            "gpus": gpus,
            "sight": eye,
            # gpu: local analysis runs on CUDA, text goes to the model.
            # izleme: a card exists but the session has not / never opened.
            # kesit: no GPU — a frame when asked.
            "vision_mode": mode,
            "min_spec": "Sürekli izleme/işleme için ≥4 GB VRAM'li NVIDIA GPU; "
                        "yoksa sorulduğunda kesit alınır.",
        })

    # -- permission rules -------------------------------------------------

    def _rules(self, body: dict[str, Any]) -> None:
        """Lists and edits the permission rules.

        Rules are shaped `tool:target-pattern`. "Always allow" writes a line
        here; without a place where the user could take back a granted
        permission, that button was a one-way door.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        action = str(body.get("action") or "list")
        rule = str(body.get("rule") or "").strip()
        side = "deny" if body.get("side") == "deny" else "allow"

        rules = {"allow": list(config.permissions.allow), "deny": list(config.permissions.deny)}
        if action == "add" and rule:
            if rule not in rules[side]:
                rules[side].append(rule)
        elif action == "remove" and rule:
            rules[side] = [r for r in rules[side] if r != rule]

        if action in ("add", "remove"):
            try:
                updated = settings.apply(config, {"permissions": rules})
            except (ValueError, OSError) as exc:
                self._json({"ok": False, "error": str(exc), **self._rule_view(config)})
                return
            self.server.config = updated  # type: ignore[attr-defined]
            controller = getattr(self.server, "controller", None)
            if controller is not None and hasattr(controller, "reload"):
                controller.reload(updated)
            config = updated

        self._json({"ok": True, **self._rule_view(config)})

    def _rule_view(self, config: Config) -> dict[str, Any]:
        return {
            "mode": config.permissions.mode,
            "allow": list(config.permissions.allow),
            "deny": list(config.permissions.deny),
            "modes": list(settings.PERMISSION_MODES),
        }

    # -- scheduled tasks --------------------------------------------------

    def _tasks(self, body: dict[str, Any]) -> None:
        """Lists and edits the tasks.

        One endpoint: every UI operation passes through the same place and
        gets the list back in its current state. Separate endpoints left a
        stale list in the UI.
        """
        book = getattr(self.server, "schedule", None)
        if book is None:
            self.send_error(503, "Zamanlayıcı çalışmıyor")
            return

        action = str(body.get("action") or "list")
        task_id = str(body.get("id") or "")

        try:
            if action == "add":
                # If a workflow id is given the task is an automation. These
                # two fields used to be DROPPED here: the scheduler, the
                # runner and the UI knew `kind_ui`/`workflow_id` but no road
                # could write them — automations could not be set up, the
                # filter stayed empty forever.
                flow = str(body.get("workflow_id") or "").strip()
                book.add(
                    scheduling.Task(
                        id="",
                        title=str(body.get("title") or "").strip() or "adsız görev",
                        prompt=str(body.get("prompt") or ""),
                        kind=str(body.get("kind") or "every"),
                        every_s=int(body.get("every_s") or 3600),
                        at=str(body.get("at") or "09:00"),
                        kind_ui="automation" if flow else "simple",
                        workflow_id=flow,
                    )
                )
            elif action == "update":
                fields = {k: v for k, v in body.items() if k not in ("action", "id")}
                book.update(task_id, **fields)
            elif action == "remove":
                book.remove(task_id)
            elif action == "run":
                # Manual run: a background helper without waiting for the time.
                task = book.get(task_id)
                controller = getattr(self.server, "controller", None)
                if task is None or controller is None:
                    self.send_error(404, "Görev yok")
                    return
                if hasattr(controller, "run_scheduled"):
                    result = controller.run_scheduled(task)
                    if not isinstance(result, dict) or not result.get("ok"):
                        self._json({
                            "ok": False,
                            "error": str((result or {}).get("error") or "başlatılamadı"),
                            "tasks": scheduling.payload(book.all()),
                        })
                        return
                else:
                    book.note_run(task_id, "elle çalıştırıldı")
                    controller.submit(task.prompt)
            elif action in ("missed_run", "missed_skip"):
                result = self._controller_call(
                    "resolve_missed",
                    "run" if action == "missed_run" else "skip",
                )
                if not isinstance(result, dict) or not result.get("ok"):
                    self._json({
                        "ok": False,
                        "error": str((result or {}).get("error") or "işlenemedi"),
                        "tasks": scheduling.payload(book.all()),
                    })
                    return
        except (ValueError, TypeError) as exc:
            self._json({"ok": False, "error": str(exc), "tasks": scheduling.payload(book.all())})
            return

        self._json({"ok": True, "tasks": scheduling.payload(book.all())})

    def _jobs_list(self) -> None:
        """Main-screen Tasks: scheduled jobs + summary of the latest runs."""
        from .. import task_runs

        book = getattr(self.server, "schedule", None)
        config = getattr(self.server, "config", None)
        if book is None or config is None:
            self._json({"ok": False, "error": "zamanlayıcı yok", "tasks": []})
            return
        rows = []
        for task in scheduling.payload(book.all()):
            tid = task.get("id") or ""
            runs = []
            try:
                runs = [task_runs.to_dict(r) for r in
                        task_runs.list_runs(config.state_dir, tid, limit=5)]
            except Exception:
                runs = []
            task["recent_runs"] = runs
            rows.append(task)
        self._json({"ok": True, "tasks": rows})

    def _jobs_runs(self) -> None:
        """One task's run archive: ?id=<task_id>&run=<run_id?>"""
        from .. import task_runs

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "yapılandırma yok"})
            return
        q = parse_qs(urlparse(self.path).query)
        tid = (q.get("id") or [""])[0]
        rid = (q.get("run") or [""])[0]
        if not tid:
            self._json({"ok": False, "error": "id gerekli"})
            return
        try:
            if rid:
                run = task_runs.get_run(config.state_dir, tid, rid)
                if run is None:
                    self._json({"ok": False, "error": "koşum yok"})
                    return
                self._json({"ok": True, "run": task_runs.to_dict(run)})
                return
            runs = [task_runs.to_dict(r) for r in
                    task_runs.list_runs(config.state_dir, tid, limit=80)]
            self._json({"ok": True, "runs": runs})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)})

    def _jobs_action(self, body: dict[str, Any]) -> None:
        """Run / update from the main screen — same book as /api/tasks."""
        self._tasks(body)

    def _workflows_list(self) -> None:
        from .. import workflows

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "workflows": []})
            return
        rows = []
        for wf in workflows.list_all(config.state_dir):
            rows.append({
                "id": wf.id, "title": wf.title,
                "nodes": len(wf.nodes), "edges": len(wf.edges),
                "updated": wf.updated,
            })
        self._json({"ok": True, "workflows": rows})

    def _workflows_action(self, body: dict[str, Any]) -> None:
        from .. import workflows

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "yapılandırma yok"})
            return
        action = str((body or {}).get("action") or "").strip()
        try:
            if action == "get":
                wf = workflows.get(config.state_dir, str(body.get("id") or ""))
                if wf is None:
                    self._json({"ok": False, "error": "akış yok"})
                    return
                self._json({"ok": True, "workflow": workflows.to_dict(wf)})
                return
            if action == "save":
                payload = body.get("workflow") or body
                wf = workflows.save(config.state_dir, payload)
                # A workflow saved from the UI enters memory too: if the
                # save road depended on the tool, the "I did this before"
                # memory would sometimes come and sometimes not.
                from .. import workflow_mind
                workflow_mind.akisi_hatirla(getattr(self.server, "mind", None), wf)
                self._json({"ok": True, "workflow": workflows.to_dict(wf)})
                return
            if action == "remove":
                ok = workflows.remove(config.state_dir, str(body.get("id") or ""))
                self._json({"ok": ok})
                return
            if action == "run":
                # Manual run, the SAME ROAD the scheduler uses: `run_scheduled`
                # with a calendar-less Task. This has to be so — if a
                # manually run workflow and a scheduled one took different
                # roads the two would break separately and one would work
                # while the other did not. An id-less Task does not dirty
                # the book: `mark_running` and `note_run` write nothing on
                # an empty id.
                wid = str(body.get("id") or "")
                controller = getattr(self.server, "controller", None)
                if controller is None or not hasattr(controller, "run_scheduled"):
                    self._json({"ok": False, "error": "koşturucu yok"})
                    return
                from ..schedule import Task
                temp_task = Task(id="", title=wid, prompt=".", kind_ui="automation",
                                 workflow_id=wid)
                result = controller.run_scheduled(temp_task)
                self._json(result if isinstance(result, dict)
                           else {"ok": False, "error": "koşturulamadı"})
                return
            self._json({"ok": False, "error": "bilinmeyen eylem"})
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _plans_list(self) -> None:
        from .. import plans as plan_store

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": True, "plans": []})
            return
        self._json({"ok": True, "plans": plan_store.listing(config.state_dir)})

    def _plans_action(self, body: dict[str, Any]) -> None:
        from .. import plans as plan_store

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "yapılandırma yok"})
            return
        action = str((body or {}).get("action") or "").strip()
        try:
            if action == "create":
                plan = plan_store.create(
                    config.state_dir,
                    title=str(body.get("title") or "Plan"),
                    steps=body.get("steps") or [],
                )
                self._json({"ok": True, "plan": plan_store.to_dict(plan)})
                # SSE: let the UI draw the Plan card.
                hub = getattr(self.server, "hub", None)
                if hub is not None:
                    hub.emit({"type": "plan", **plan_store.to_dict(plan)})
                return
            if action == "update":
                plan = plan_store.update(
                    config.state_dir, str(body.get("id") or ""),
                    status=body.get("status"),
                    steps=body.get("steps"),
                    title=body.get("title"),
                )
                if plan is None:
                    self._json({"ok": False, "error": "plan yok"})
                    return
                self._json({"ok": True, "plan": plan_store.to_dict(plan)})
                hub = getattr(self.server, "hub", None)
                if hub is not None:
                    hub.emit({"type": "plan", **plan_store.to_dict(plan)})
                return
            if action == "approve":
                plan = plan_store.update(
                    config.state_dir, str(body.get("id") or ""),
                    status="onaylandi")
                if plan is None:
                    self._json({"ok": False, "error": "plan yok"})
                    return
                # Approval → continuation note to the agent.
                controller = getattr(self.server, "controller", None)
                if controller is not None and hasattr(controller, "submit"):
                    controller.submit(
                        f"[Plan onaylandı · {plan.id}] {plan.title}. "
                        f"Adımları uygula:\n" + "\n".join(
                            f"- {s.get('text') or s}" for s in (plan.steps or [])),
                        siraya=True)
                self._json({"ok": True, "plan": plan_store.to_dict(plan)})
                hub = getattr(self.server, "hub", None)
                if hub is not None:
                    hub.emit({"type": "plan", **plan_store.to_dict(plan)})
                return
            if action == "cancel":
                plan = plan_store.update(
                    config.state_dir, str(body.get("id") or ""),
                    status="iptal")
                self._json({"ok": True, "plan": plan_store.to_dict(plan) if plan else None})
                return
            self._json({"ok": False, "error": "bilinmeyen eylem"})
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _git_status(self) -> None:
        from .. import git as gitmod

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": True, "present": False})
            return
        snap = gitmod.snapshot(config)
        if not snap.get("present"):
            # Even without a repo the working folder should show in the bar:
            # "Open repo" and "open folder" live there (live request,
            # 31.08). ONLY the assigned project: the workshop is a scratch
            # area, not a repo surface ("it must not open a repo for the
            # workshop" — 01.09).
            try:
                box = config.open_sandbox()
                if box.project is not None:
                    snap = {**snap, "root": str(box.project),
                            "name": Path(box.project).name}
            except Exception:
                pass
        self._json(snap)

    def _git_action(self, body: dict[str, Any]) -> None:
        from .. import git as gitmod

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "yapılandırma yok"})
            return
        action = str((body or {}).get("action") or "").strip()
        root = gitmod.repo_root(config)
        try:
            if action == "diff":
                if root is None:
                    self._json({"ok": False, "error": "git deposu yok"})
                    return
                path = str(body.get("path") or "") or None
                self._json(gitmod.diff(root, path))
                return
            if action in ("commit", "push", "pull", "create_repo", "publish", "init"):
                result = self._git_mutate(gitmod, config, root, action, body or {})
                self._json(result)
                if result.get("ok"):
                    hub = getattr(self.server, "hub", None)
                    if hub is not None:
                        hub.emit({"type": "git", "action": action})
                return
            self._json({"ok": False, "error": "bilinmeyen eylem"})
        except gitmod.GitError as exc:
            self._json({"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _git_mutate(
        self, gitmod: Any, config: Any, root: Any, action: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        box = config.open_sandbox()
        if root is None:
            root = box.project or box.root
        private = body.get("private")
        if private is None:
            private = True
        name = str(body.get("name") or "").strip()
        if action == "init":
            return {"ok": True, **gitmod.init(root)}
        if action == "commit":
            paths = body.get("paths")
            if not isinstance(paths, list):
                paths = None
            snap = gitmod.commit(root, str(body.get("message") or ""), paths=paths)
            return {"ok": True, **snap}
        if action == "push":
            return {"ok": True, **gitmod.push(root)}
        if action == "pull":
            return {"ok": True, **gitmod.pull(root)}
        if action == "create_repo":
            created = gitmod.create_repo(
                name or (root.name if root is not None else ""),
                private=bool(private),
                source=root,
                state_dir=config.state_dir,
            )
            return {"ok": True, **created}
        snap = gitmod.publish(
            root, name=name, private=bool(private), state_dir=config.state_dir,
        )
        return {"ok": True, **snap}

    # -- goal stack -------------------------------------------------------

    def _goals(self, body: dict[str, Any]) -> None:
        """The goal panel's management endpoint: finish, drop, clear all.

        The panel used to be display-only and the user rightly asked:
        "where do these get added, where are they cleared?" The agent adds
        with `mind_goals`; the user had nothing in hand and goals left over
        from old sessions kept piling up. Now the user can write to the same
        book too — the same road the agent uses (set_goal_status), no
        separate reality is produced.

        Actions: done (completed), drop (remove), clear (drop all active ones).
        """
        mind = getattr(self.server, "mind", None)
        if mind is None or not hasattr(mind, "set_goal_status"):
            self._json({"ok": False, "error": "hedef desteği yok"})
            return

        action = str((body or {}).get("action") or "").strip()
        if action == "add":
            # The list is now two-sided: the agent writes with `mind_goals`,
            # the user from here. The same book — we do not produce a
            # separate reality, the agent sees its own item too.
            text = str((body or {}).get("text") or "").strip()
            if not text:
                self._json({"ok": False, "error": "boş madde"})
                return
            try:
                goal = mind.push_goal(text[:GOAL_TEXT_LIMIT])
            except Exception as exc:
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            self._json({"ok": True, "id": goal.id, "text": goal.text})
            return

        if action == "clear":
            try:
                for goal in mind.goals():
                    mind.set_goal_status(goal.id, "dropped", "kullanıcı temizledi")
            except Exception as exc:
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            self._json({"ok": True, "goals": []})
            return

        if action not in ("done", "drop"):
            self._json({"ok": False, "error": "bilinmeyen eylem"})
            return

        gid = str((body or {}).get("id") or "").strip()
        if not gid or not re.match(r"^[A-Za-z0-9_-]+$", gid):
            self._json({"ok": False, "error": "geçersiz hedef"})
            return
        try:
            updated = mind.set_goal_status(
                gid, "done" if action == "done" else "dropped",
                "kullanıcı işaretledi")
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return
        if updated is None:
            self._json({"ok": False, "error": "hedef bulunamadı"})
            return
        self._json({"ok": True, "id": gid, "status": updated.status})

    # -- files dropped into the chat ---------------------------------------

    def _drop(self, body: dict[str, Any]) -> None:
        """Writes a dragged or pasted file into the workshop.

        The browser does not give the local file's **path**, only its
        content — for security. So the file is copied into the workshop and
        the agent is given the path: from there it can open and inspect it
        with `read_file`.

        Images are separate: they are attached to the message directly and
        the model can look at them. They still remain as files too.
        """
        import base64
        import re

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        name = re.sub(r"[^\w.\- ]", "_", str(body.get("name") or "dosya")).strip() or "dosya"
        payload = str(body.get("data") or "")
        _, _, encoded = payload.partition(",")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception:
            self._json({"ok": False, "error": "dosya çözülemedi"})
            return

        if len(raw) > DROP_LIMIT:
            self._json({"ok": False, "error": f"dosya çok büyük (en fazla {DROP_LIMIT // 1024 // 1024} MB)"})
            return

        folder = config.open_sandbox().root / "gelen"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        # A same-named file is not overwritten: a dropped file silently
        # erasing the previous one is data loss.
        stem, suffix, index = target.stem, target.suffix, 2
        while target.exists():
            target = folder / f"{stem}-{index}{suffix}"
            index += 1

        try:
            target.write_bytes(raw)
        except OSError as exc:
            self._json({"ok": False, "error": str(exc)})
            return

        self._json({"ok": True, "path": str(target), "name": target.name, "bytes": len(raw)})

    # -- voice -------------------------------------------------------------

    def _speak(self, body: dict[str, Any]) -> None:
        """Turns text into speech and returns it as mp3.

        Speech synthesis goes out to the network and can take seconds; this
        request keeps an HTTP thread busy but does not touch the agent's
        loop — the server is threaded anyway.
        """
        config = getattr(self.server, "config", None)
        if config is None or not config.voice.enabled:
            self.send_error(409, "Sesli konuşma kapalı")
            return

        text = str(body.get("text") or "")

        # Clip: short acknowledgement sounds ("bakıyorum") must not go out
        # to the network and be regenerated every time — produced once, kept
        # on disk, instant afterwards. The key includes the voice settings
        # too: if the voice or the rate changes the old clip is not used.
        cached = None
        if body.get("clip") and text:
            import hashlib

            key = hashlib.sha1("|".join((
                config.voice.name, config.voice.rate,
                config.voice.pitch, text,
            )).encode("utf-8")).hexdigest()
            cached = config.state_dir / "clips" / f"{key}.mp3"
            if cached.exists():
                self._send(200, "audio/mpeg", cached.read_bytes())
                return

        try:
            audio = asyncio.run(voice.synthesize(text, config.voice))
        except RuntimeError as exc:  # package not installed
            self.send_error(501, str(exc))
            return
        except Exception:
            # No network, no voice; the text stays in place, work must not stop.
            self.send_error(503, "Ses üretilemedi")
            return

        if not audio:
            # Nothing left to say (it was only a code block, say).
            self._send(204, "audio/mpeg", b"")
            return
        if cached is not None:
            try:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(audio)
            except OSError:
                pass  # if the disk cannot be written the clip goes on uncached
        self._send(200, "audio/mpeg", audio)

    def _voices(self) -> None:
        config = getattr(self.server, "config", None)
        prefix = (config.voice.name.split("-")[0] if config else "tr")
        try:
            listing = asyncio.run(voice.voices(prefix))
        except Exception:
            listing = []
        self._json({"voices": listing})

    def _hear(self, audio: bytes) -> None:
        """Transcribes the incoming audio chunk.

        The body is raw audio (webm/opus); not JSON, because base64 means a
        third of growth and wasted work. Recognition is local — the audio
        goes nowhere.
        """
        config = getattr(self.server, "config", None)
        if config is None or not config.listen.enabled:
            self.send_error(409, "Sesli komut kapalı")
            return

        if not audio:
            self.send_error(400, "Boş ses")
            return

        ear = _ear(self.server, config)
        if ear is None:
            self.send_error(501, listen.hint())
            return

        # The recogniser wants a file path; the chunk is small and temporary.
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as handle:
            handle.write(audio)
            clip = Path(handle.name)

        try:
            said = ear.transcribe(clip)
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)})
            return
        finally:
            clip.unlink(missing_ok=True)

        wake = config.listen.wake
        self._json({
            "ok": True,
            "text": said,
            "wake": listen.heard_wake(said, wake),
            # The wake word itself is not part of the command.
            "command": listen.after_wake(said, wake),
        })

    # -- files the agent produced ---------------------------------------

    def _devices(self, body: dict[str, Any]) -> None:
        """Device records: list, write, delete.

        Writes to the same files as the agent. Keeping two separate stores
        meant the agent not seeing a PLC the user added — the whole point of
        a device is that both of them know it.
        """
        from .. import devices as declared

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        root = config.open_sandbox().root
        action = str(body.get("action") or "list")

        if action == "save":
            raw = dict(body.get("device") or {})
            # A record added from the settings page belongs to the user: the
            # agent cannot delete it on its own.
            raw.setdefault("source", "elle")
            try:
                declared.save(root, raw)
            except declared.DeviceError as exc:
                self._json({"ok": False, "error": str(exc)})
                return

        elif action == "remove":
            declared.remove(root, str(body.get("id") or ""))

        found, broken = declared.load(root)
        self._json({
            "ok": True,
            "kinds": list(declared.KINDS),
            "devices": [declared.to_dict(device) for device in found],
            "broken": broken,
        })

    def _skills(self, body: dict[str, Any]) -> None:
        """Skills: list, create, read, write, delete.

        The user can add and edit too — a skill is not only something the
        agent writes for itself. Every change is applied to the live
        registry as well: a saved skill exists as a tool on the next turn, a
        deleted one does not.
        """
        from .. import skills as authored

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        # Live registry: the change is applied to the session at once. With
        # no agent (observe-only preview) the file work still runs.
        agent = getattr(getattr(self.server, "controller", None), "agent", None)
        registry = getattr(agent, "registry", None)

        root = config.open_sandbox().root
        action = str(body.get("action") or "list")
        name = str(body.get("name") or "").strip().lower()
        error = ""

        if action == "remove":
            path = authored.folder(root) / f"{name}.py"
            if path.is_file():
                path.unlink()
            if registry is not None:
                registry.unregister(name)

        elif action == "new":
            try:
                authored.scaffold(root, name, str(body.get("description") or "").strip())
            except authored.SkillError as exc:
                error = str(exc)

        elif action == "read":
            path = authored.folder(root) / f"{name}.py"
            if not path.is_file():
                self._json({"ok": False, "error": f"Dosya yok: {name}.py"})
                return
            self._json({"ok": True, "name": name, "code": path.read_text(encoding="utf-8")})
            return

        elif action == "write":
            try:
                authored.save(root, name, str(body.get("code") or ""))
            except authored.SkillError as exc:
                error = str(exc)

        found, broken = authored.discover(root)
        if registry is not None:
            authored.register(registry, found)
        self._json({
            "ok": not error,
            "error": error,
            "skills": [
                {
                    "name": skill.name,
                    "description": (skill.description or "").strip(),
                    "path": str(authored.folder(root) / f"{skill.name}.py"),
                }
                for skill in found
            ],
            "broken": broken,
        })

    def _connectors(self, body: dict[str, Any]) -> None:
        """MCP connectors: list, save, reconnect.

        The record is a single JSON text — Claude Code's `mcpServers`
        format. Saving covers reconnecting too: a server that sits in the
        file but is not connected counts as non-existent.
        """
        from .. import connectors as linking

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        pool = getattr(self.server, "connectors", None)
        agent = getattr(getattr(self.server, "controller", None), "agent", None)
        registry = getattr(agent, "registry", None)

        action = str(body.get("action") or "list")
        problems: list[str] = []
        note = ""

        if action == "save":
            try:
                linking.save(config.state_dir, str(body.get("raw") or ""))
            except linking.ConnectorError as exc:
                self._json({"ok": False, "error": str(exc)})
                return

        if action == "login":
            # OAuth: the browser opens, the user signs in, the token is
            # stored. This request waits until the login finishes — the
            # server is threaded, it does not stall other requests.
            name = str(body.get("name") or "")
            found, _ = linking.load(config.state_dir)
            target = next((c for c in found if c.name == name), None)
            if target is None:
                self._json({"ok": False, "error": f"Sunucu yok: {name}"})
                return
            # The login address drops into the chat too: the browser may
            # have opened in the background or invisibly — with the address
            # on screen the user can copy it and open it themselves.
            hub = getattr(self.server, "hub", None)

            def tell(url: str) -> None:
                if hub is not None:
                    hub.emit({"type": "notice",
                              "text": "Giriş sayfası tarayıcıda açılıyor. "
                                      "Açılmadıysa bu adresi kendin aç:\n" + url})

            try:
                note = linking.login(target, config.state_dir, announce=tell)
            except linking.ConnectorError as exc:
                self._json({"ok": False, "error": str(exc)})
                return

        if action == "logout":
            if linking.forget_login(config.state_dir, str(body.get("name") or "")):
                note = "Çıkış yapıldı."

        if action in ("save", "reload", "login", "logout") and pool is not None:
            # Connecting can take seconds (npx may download a package); the
            # settings page waits and the returned list shows the real state.
            found, problems = linking.load(config.state_dir)
            pool.connect(found, config.state_dir)
            if registry is not None:
                linking.register(registry, pool)

        self._json({
            "ok": True,
            "note": note,
            "raw": linking.read_raw(config.state_dir),
            "servers": pool.status() if pool is not None else [],
            "problems": problems,
        })

    def _organs(self) -> None:
        """The agent's current body: its senses and the modules it wrote for itself.

        The scene draws this faded and lights it up when used. It is read
        from here, not from settings: a camera that looks on in the settings
        may not have actually opened and would sit on screen as if working.
        """
        from .. import organs as body

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"organs": []})
            return

        self._json({
            "organs": body.inventory(
                config,
                ear=getattr(self.server, "ear", None),
                lens=getattr(self.server, "lens", None),
            )
        })

    def _files(self) -> None:
        """Walks the workspace.

        The path comes from the request, so it is resolved and verified to
        stay under the workspace: climbing up with `..` is the classic road
        to a directory-traversal hole.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        query = parse_qs(urlparse(self.path).query)
        root = Path(config.workspace).resolve()
        target = (root / (query.get("path", [""])[0] or "")).resolve()

        if root != target and root not in target.parents:
            self.send_error(403, "Çalışma alanı dışı")
            return

        if target.is_file():
            self._json(_file_payload(target, root))
            return
        if not target.is_dir():
            self.send_error(404)
            return

        self._json({
            "path": _relative(target, root),
            "parent": None if target == root else _relative(target.parent, root),
            "entries": _listing(target, root),
        })

    def _files_search(self) -> None:
        """`@` file mention: fast search by name in the workspace.

        `/api/files` lists one directory; this endpoint searches the WHOLE
        space. It passes through the same gate: the root is the workspace,
        there is no path that could leave it (the only thing coming from the
        request is the search text, not a path).
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        want = (parse_qs(urlparse(self.path).query).get("q", [""])[0] or "").strip().lower()
        root = Path(config.workspace).resolve()
        self._json({"q": want, "files": _search_files(root, want)})

    def _task_dump(self) -> None:
        """A helper's STEP list: `?oturum=<id>`.

        `/api/session` gives a conversation's TEXT turns — that is not the
        question asked when looking at a helper: "what did it do?". Here
        the tool calls are included, in order: which tool it called with
        which target, whether it succeeded, how many ms it took. The source
        is the helper's own session log; no second book is kept.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "Yapılandırma yüklü değil"})
            return
        sid = parse_qs(urlparse(self.path).query).get("oturum", [""])[0]
        if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
            self._json({"ok": False, "error": "geçersiz oturum"})
            return
        path = Path(config.sessions_dir) / f"{sid}.jsonl"
        if not path.is_file():
            self._json({"ok": False, "error": "Oturum günlüğü bulunamadı."})
            return

        steps: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if not (line := line.strip()):
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    meta = ev.get("meta") or {}
                    if ev.get("content") == "tool_start":
                        steps.append({
                            "tur": "arac",
                            "ad": str(meta.get("tool") or ""),
                            "hedef": _target_summary(meta.get("input")),
                        })
                    elif ev.get("content") == "tool_end" and steps:
                        # Closes the last open tool step: opening a separate
                        # row would double the list, unreadable.
                        last = steps[-1]
                        if last.get("tur") == "arac" and "hata" not in last:
                            last["hata"] = bool(meta.get("error"))
                            last["ms"] = int(meta.get("ms") or 0)
                    elif ev.get("role") == "assistant" and ev.get("kind") == "message":
                        if meta.get("internal") or meta.get("continuation"):
                            continue
                        text = "\n".join(_plain_blocks(ev.get("content"))).strip()
                        if text:
                            steps.append({"tur": "soz", "metin": text[:2000]})
        except OSError as exc:
            self._json({"ok": False, "error": f"Günlük okunamadı: {exc}"})
            return
        # A long run can have hundreds of steps; the last 200 are enough.
        self._json({"ok": True, "oturum": sid, "adimlar": steps[-200:]})

    def _task_report(self) -> None:
        """Full helper/job text: `?id=c:<cid>` — the panels open it in the Viewer."""
        result = self._controller_call(
            "task_report",
            parse_qs(urlparse(self.path).query).get("id", [""])[0],
        )
        self._json(result if isinstance(result, dict)
                   else {"ok": False, "error": "Rapor bu köprüde yok."})

    def _task_report_page(self, route: str) -> None:
        """Artifact-like page: /gorev-rapor/<cid>/ → HTML report."""
        cid = route[len("/gorev-rapor/"):].strip("/")
        # Only the raw id in the URL; the API side accepts the c: prefix too.
        result = self._controller_call("task_report", cid)
        if not isinstance(result, dict) or not result.get("ok"):
            self.send_error(404, str((result or {}).get("error") or "Rapor yok"))
            return
        title_doc, h1, badge, summary, command = _report_cover(result)
        title = html.escape(title_doc)
        text = str(result.get("metin") or "")
        body = _report_html(text)
        deliverable = result.get("deliverable") if isinstance(result.get("deliverable"), dict) else None
        app_block = ""
        if deliverable and deliverable.get("kind") == "app" and deliverable.get("url"):
            app_url = html.escape(str(deliverable["url"]))
            app_block = (
                f'<p class="cta"><a class="btn" href="{app_url}" target="_blank" rel="noopener">'
                f"Canlı uygulamayı aç</a></p>"
                f'<iframe class="live" src="{app_url}" title="Canlı uygulama"></iframe>'
            )
        elif deliverable and deliverable.get("kind") == "artifact" and deliverable.get("url"):
            art = html.escape(str(deliverable["url"]))
            app_block = (
                f'<p class="cta"><a class="btn" href="{art}">Yayınlanan raporu aç</a></p>'
            )
        meta_bits = []
        if badge:
            meta_bits.append(f'<p class="meta">{badge}</p>')
        if summary:
            meta_bits.append(f'<p class="ozet">{html.escape(summary)}</p>')
        if command:
            shown = command if len(command) <= 120 else command[:117] + "…"
            meta_bits.append(
                f'<p class="cmd"><code title="{html.escape(command)}">'
                f"{html.escape(shown)}</code></p>"
            )
        meta_html = "\n".join(meta_bits)
        page = (
            "<!doctype html><html lang=tr><head><meta charset=utf-8>"
            f"<title>{title}</title>"
            "<style>"
            "html,body{margin:0;background:#0b1218;color:#dceefc;"
            "font:16px/1.65 system-ui,Segoe UI,sans-serif}"
            "html{scrollbar-width:thin;scrollbar-color:rgba(79,227,255,.35) transparent}"
            "::-webkit-scrollbar{width:8px;height:8px}"
            "::-webkit-scrollbar-thumb{background:rgba(79,227,255,.3);border-radius:4px}"
            "main{max-width:640px;margin:0 auto;padding:36px 28px 56px}"
            "h1{font:600 26px/1.25 system-ui;margin:0 0 10px;color:#eaf6ff}"
            ".meta{font:13px/1.5 system-ui;color:#8fb0cc;margin:0 0 10px}"
            ".ozet{font:15px/1.55 system-ui;color:#dceefc;margin:0 0 12px}"
            ".cmd{margin:0 0 22px}"
            ".cmd code,.meta code{font:12.5px/1.45 ui-monospace,Consolas,monospace;"
            "background:#05121d;padding:4px 9px;border-radius:6px;color:#c5e4ff;"
            "display:inline-block;max-width:100%;word-break:break-word}"
            ".badge{display:inline-block;padding:2px 9px;border-radius:999px;"
            "font:600 11px/1.4 system-ui;letter-spacing:.02em;"
            "background:#1a2a38;color:#8fb0cc;vertical-align:middle}"
            ".badge.err{background:#ff4d6d22;color:#ff8aa0}"
            ".badge.ok{background:#3dffa018;color:#8affc1}"
            ".cta{margin:0 0 16px}"
            ".btn{display:inline-block;padding:8px 14px;border-radius:8px;"
            "background:#4fe3ff22;color:#4fe3ff;text-decoration:none;font:600 13px system-ui}"
            ".btn:hover{background:#4fe3ff33}"
            "iframe.live{width:100%;height:min(70vh,720px);border:1px solid #1e3a4c;"
            "border-radius:10px;background:#061018;margin:0 0 22px}"
            ".rapor{word-break:break-word}"
            ".rapor p{margin:.55em 0}"
            ".rapor h2{font:600 15px/1.3 system-ui;margin:1.5em 0 .4em;color:#a8e8ff}"
            ".rapor h3{font:600 14px/1.3 system-ui;margin:1.2em 0 .4em;color:#a8e8ff}"
            ".rapor ul{padding-left:1.2em;margin:.5em 0}"
            ".rapor li{margin:.25em 0}"
            ".rapor a{color:#4fe3ff}"
            ".rapor code{font:13px ui-monospace,Consolas,monospace;"
            "background:#05121d;padding:1px 5px;border-radius:4px}"
            ".rapor details.log{margin:1.2em 0;border:1px solid #1e3a4c;"
            "border-radius:8px;background:#061018;padding:8px 12px}"
            ".rapor details.log summary{cursor:pointer;color:#8fb0cc;"
            "font:600 12.5px/1.4 system-ui;user-select:none}"
            ".rapor details.log pre{margin:10px 0 4px;white-space:pre-wrap;"
            "word-break:break-word;font:12px/1.5 ui-monospace,Consolas,monospace;"
            "color:#a8c4d8;max-height:min(50vh,420px);overflow:auto}"
            "</style></head><body><main>"
            f"<h1>{html.escape(h1)}</h1>"
            f"{meta_html}"
            f"{app_block}"
            f"<div class=rapor>{body}</div>"
            "</main></body></html>"
        ).encode("utf-8")
        self._send(200, "text/html; charset=utf-8", page)

    # -- change ledger ---------------------------------------------------

    def _ledger(self) -> Any:
        """This session's change ledger (`tools/checkpoint.Defter`).

        The tool layer writes the ledger (write_file/edit_file/copy_in
        before every change); this ONLY reads it and calls the undo road the
        `undo` tool uses. No second source of truth is produced: what the
        panel sees is what the agent sees.
        """
        from ..tools.checkpoint import KLASOR, Defter

        config = getattr(self.server, "config", None)
        if config is None:
            return None
        mind = getattr(self.server, "mind", None)
        sid = str(getattr(mind, "session_id", "") or "")
        if not sid:
            snap = self._controller_call("snapshot") or {}
            sid = str(snap.get("session") or "")
        if not sid:
            return None
        return Defter(Path(config.state_dir) / KLASOR, sid)

    def _changes(self) -> None:
        """Files written/edited in this session.

        With `?since=N` only the records after N are returned — the "what
        changed this turn" strip in the UI uses exactly that: it takes `son`
        at the start of the turn and asks for what came after once the turn
        ends.
        """
        ledger = self._ledger()
        if ledger is None:
            self._json({"son": 0, "kayitlar": []})
            return
        try:
            since = int(parse_qs(urlparse(self.path).query).get("since", ["0"])[0])
        except ValueError:
            since = 0
        records = ledger.list_entries(tavan=200)      # newest first
        last = records[0]["sira"] if records else 0
        out = []
        for k in records:
            if since and k["sira"] <= since:
                continue
            file_path = str(k.get("dosya") or "")
            out.append({
                "sira": k["sira"],
                "dosya": file_path,
                "ad": file_path.replace("\\", "/").rsplit("/", 1)[-1],
                "arac": k.get("arac") or "",
                "zaman": k.get("zaman") or "",
                "yoktu": bool(k.get("yoktu")),
                "atlandi": k.get("atlandi") or "",
                # A record without a snapshot cannot be undone; the UI does
                # not hide that, it says so next to the row.
                "gerialinabilir": bool(k.get("goruntu")) or bool(k.get("yoktu")),
            })
        self._json({"son": last, "kayitlar": out})

    def _change_diff(self) -> None:
        """A single record's diff: `?sira=N` → {eski, yeni}.

        `eski` is the snapshot in the ledger, `yeni` the file's CURRENT
        state. So what is shown is "what happened since this record" — the
        very change the user will see on pressing the undo button.
        """
        ledger = self._ledger()
        if ledger is None:
            self._json({"ok": False, "error": "Değişiklik defteri yok."})
            return
        try:
            seq = int(parse_qs(urlparse(self.path).query).get("sira", ["0"])[0])
        except ValueError:
            seq = 0
        record = next((k for k in ledger.list_entries(tavan=200) if k["sira"] == seq), None)
        if record is None:
            self._json({"ok": False, "error": "Kayıt bulunamadı."})
            return

        def _read(path: Path) -> tuple[str, bool]:
            try:
                data = path.read_bytes()[:DIFF_LIMIT]
            except OSError:
                return "", False
            try:
                # Line endings are normalised: the diff renderer splits on
                # "\n" and on Windows an invisible "\r" stayed at the end of
                # every line — even unchanged lines looked changed. This is
                # a DISPLAY endpoint; it does not touch the disk.
                return data.decode("utf-8").replace("\r\n", "\n"), True
            except UnicodeDecodeError:
                return "", False

        file_path = Path(str(record.get("dosya") or ""))
        old, old_ok = ("", True) if record.get("yoktu") else (
            _read(ledger.dizin / str(record.get("goruntu")))
            if record.get("goruntu") else ("", False))
        new, new_ok = _read(file_path) if file_path.exists() else ("", True)
        self._json({
            "ok": True,
            "sira": seq,
            "dosya": str(file_path),
            "ad": file_path.name,
            "eski": old,
            "yeni": new,
            "yoktu": bool(record.get("yoktu")),
            # No diff is drawn for a binary or unreadable file; the reason is written.
            "metin": bool(old_ok and new_ok),
            "atlandi": record.get("atlandi") or "",
        })

    def _change_undo(self, body: dict[str, Any]) -> None:
        """Undoes a change — the road the `undo` tool uses.

        Body options:
          * `{n}` — the last n records (turn undo)
          * `{sira}` — a single record (file Keep/Undo)
          * `{siralar: [...]}` — several records (bulk undo other than Accept All)

        Confirmation is in the UI. On a record without a snapshot the ledger
        writes nothing (the n road) or rejects that row (the sira road).
        """
        ledger = self._ledger()
        if ledger is None:
            self._json({"ok": False, "error": "Değişiklik defteri yok."})
            return
        body = body or {}
        hub = getattr(self.server, "hub", None)
        done: list[str] = []
        error: str | None = None

        if body.get("sira") is not None or body.get("siralar") is not None:
            raw_seqs = body.get("siralar")
            if raw_seqs is None:
                raw_seqs = [body.get("sira")]
            if not isinstance(raw_seqs, list) or not raw_seqs:
                self._json({"ok": False, "error": "Geçersiz sira listesi."})
                return
            seqs: list[int] = []
            for x in raw_seqs:
                try:
                    seqs.append(int(x))
                except (TypeError, ValueError):
                    self._json({"ok": False, "error": "Geçersiz sira."})
                    return
            # Newest to oldest: the right order if the same file has stacked records.
            for seq in sorted(seqs, reverse=True):
                part, err = ledger.undo_sequence(seq)
                done.extend(part)
                if err:
                    error = err
                    break
        elif body.get("dosya"):
            done, error = ledger.undo_file(str(body.get("dosya") or ""))
        else:
            try:
                n = int(body.get("n") or 1)
            except (TypeError, ValueError):
                n = 1
            n = max(1, min(n, 200))
            done, error = ledger.undo(n)

        if error:
            self._json({"ok": False, "error": error, "yapilan": done})
            return
        if hub is not None:
            hub.emit({"type": "notice",
                      "text": f"Geri alındı: {len(done)} değişiklik eski haline döndü."})
        self._json({"ok": True, "yapilan": done})

    def _camera_frame(self) -> None:
        """ONE fresh frame (JPEG) from a camera — the watch area's preview.

        No continuous stream (MJPEG/WebRTC). If the built-in camera is
        already open in the Lens buffer that JPEG is used — opening the same
        device a second time locks the deck on Windows. Network cameras are
        a single snapshot.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        if not watch.available():
            self.send_error(501, "opencv kurulu değil")
            return
        query = parse_qs(urlparse(self.path).query)
        source = (query.get("source", [""])[0] or "").strip()
        cid = (query.get("id", [""])[0] or "").strip()
        cam = None
        if cid:
            cam = next((c for c in watch.load(config.state_dir)
                        if c.id == cid), None)
            if cam is None:
                self.send_error(404, "kamera yok")
                return
            source = str(cam.connect_source())
        source = source or "0"

        lens = getattr(self.server, "lens", None)
        if lens is None:
            ctrl = getattr(self.server, "controller", None)
            lens = getattr(ctrl, "lens", None) if ctrl else None
        payload = watch.preview_jpeg(source, lens=lens)
        if not payload:
            if lens is not None and watch.same_source(
                    getattr(lens, "source", "0"), source):
                self.send_error(503, "kamera henüz hazır değil")
                return
            self.send_error(502, "kamera açılamadı")
            return
        summary = ""
        want_boxes = (query.get("boxes", ["0"])[0] or "0") not in ("0", "false", "")
        if cam is None:
            cam = next((c for c in watch.load(config.state_dir)
                        if c.is_builtin()), None)
        analyze = True if cam is None else bool(getattr(cam, "analyze", True))
        if want_boxes and analyze:
            from .. import sight as sight_mod
            payload, summary = sight_mod.annotate_jpeg(
                payload, key=cid or source or "0")
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Expose-Headers", "X-Dornick-Sight")
        if summary:
            self.send_header("X-Dornick-Sight", quote(summary, safe=" ,()-"))
        self.end_headers()
        self.wfile.write(payload)

    def _raw_file(self) -> None:
        """A file's RAW bytes: the viewer's image/audio/video/PDF endpoint.

        `/api/files` returns text; a PNG came from there only as a "binary
        file" and the panel could not show the image. This endpoint passes
        through the same GATE: the path comes from the request, so it is
        resolved and verified to stay under the workspace (climbing up with
        `..` is the classic road to a directory-traversal hole).

        The content type is given BY EXTENSION and only from a known media
        list: letting the browser look at the content and decide for itself
        (sniffing) could have treated a text file as HTML and executed it.
        An unrecognised extension is `application/octet-stream` — i.e.
        downloaded, not interpreted. `X-Content-Type-Options: nosniff`
        seals that.
        """
        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        query = parse_qs(urlparse(self.path).query)
        root = Path(config.workspace).resolve()
        target = (root / (query.get("path", [""])[0] or "")).resolve()

        if root != target and root not in target.parents:
            self.send_error(403, "Çalışma alanı dışı")
            return
        if not target.is_file():
            self.send_error(404)
            return

        kind = RAW_TYPES.get(target.suffix.lower(), "application/octet-stream")
        try:
            size = target.stat().st_size
        except OSError:
            self.send_error(404)
            return

        # Range request: video/audio players use this to seek. A single
        # range is enough; an unparseable header is ignored and the whole
        # file is sent.
        start, end = 0, size - 1
        partial = False
        if size and (raw_range := self.headers.get("Range", "")).startswith("bytes="):
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", raw_range.strip())
            if match and (match.group(1) or match.group(2)):
                if match.group(1):
                    start = int(match.group(1))
                    if match.group(2):
                        end = int(match.group(2))
                else:                                   # "bytes=-500": from the end
                    start = max(0, size - int(match.group(2)))
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                partial = True

        length = end - start + 1 if size else 0
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        if query.get("download", [""])[0]:
            # The end of the "download the report" link in the chat: the
            # attachment header forces the browser to save instead of
            # interpreting. The name is thinned to ASCII — raw UTF-8 on the
            # header line breaks in some clients.
            clean = re.sub(r"[^\w.\-]", "_", target.name) or "dosya"
            self.send_header("Content-Disposition",
                             f'attachment; filename="{clean}"')
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        # Chunk by chunk: loading a video file into memory would bring the server down.
        try:
            with target.open("rb") as handle:
                handle.seek(start)
                left = length
                while left > 0:
                    chunk = handle.read(min(64 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (OSError, BrokenPipeError, ConnectionError):
            # The headers are gone; the only thing to do here is stay quiet.
            self.close_connection = True

    def _browse(self) -> None:
        """Folder explorer: lists FOLDERS for choosing a project.

        Why a separate endpoint: `/api/files` stays inside the workspace and
        the project is exactly a place OUTSIDE it. A native folder dialog
        cannot be used either (the desktop layer is a separate process), so
        the picker lives inside the browser itself.

        Not a new exposure class: reading is already free everywhere in this
        program (the agent's `list_dir` does exactly this). Only folder
        NAMES are returned here — no file content, the file list only as a
        count. The write side is unaffected: choosing does not grant write
        permission, SAVING the setting does.
        """
        query = parse_qs(urlparse(self.path).query)
        requested = (query.get("yol", [""])[0] or "").strip()

        if not requested:
            # Start: drives (Windows) or root + home.
            self._json({"yol": "", "ust": None, "klasorler": _starting_places()})
            return

        try:
            target = Path(requested).expanduser().resolve()
        except OSError:
            self._json({"hata": "Bu yol çözümlenemedi."})
            return
        if not target.is_dir():
            self._json({"hata": f"Böyle bir klasör yok: {target}"})
            return

        folders: list[dict[str, Any]] = []
        file_count = 0
        try:
            for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
                try:
                    if child.is_dir():
                        # Hidden/tool folders are noise in the picker: not
                        # shown-but-pushed-to-the-end — hidden. Whoever wants
                        # them can type the path by hand.
                        if child.name.startswith(".") or child.name in SKIPPED:
                            continue
                        folders.append({"ad": child.name, "yol": str(child)})
                    else:
                        file_count += 1
                except OSError:
                    continue
        except OSError as exc:
            self._json({"hata": f"Klasör okunamadı: {exc}"})
            return

        config = getattr(self.server, "config", None)
        status = config.state_dir if config is not None else None
        self._json({
            "yol": str(target),
            "ust": str(target.parent) if target.parent != target else None,
            "klasorler": folders[:400],
            "dosya": file_count,
            # Can it be chosen and what should be said if it is: the user
            # should see it BEFORE SAVING.
            "engel": sandbox.root_block(target) or "",
            "uyari": sandbox.root_warning(target, state_dir=status),
            "tur": _project_kind(target),
        })

    def _apps(self) -> None:
        """Serves the workshop as a catalogue of runnable applications.

        Empty root without a sandbox: the agent's workshop may not have opened yet.
        """
        from .. import apps as catalog

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"root": None})
            return
        try:
            root = config.open_sandbox().root
            # base is the workspace: paths are relative to the same root as
            # `/api/files` so a web app really opens when clicked.
            tree = catalog.catalog(root, base=Path(config.workspace))
        except Exception as exc:
            self._json({"root": None, "error": str(exc)})
            return
        self._json({"root": catalog.to_dict(tree)})

    def _projects(self) -> None:
        """Serves the workshop as PROJECT units (not a file tree).

        Every project is a unit of work: a folder Dornick produced (like a
        Modbus web client) or a standalone file. The panel shows them as
        cards; clicking reveals how to run it + Run.
        """
        from .. import apps as catalog

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"projects": []})
            return
        try:
            root = config.open_sandbox().root
            data = catalog.katalog(root, base=Path(config.workspace))
        except Exception as exc:
            self._json({"projects": [], "sorunlar": [], "error": str(exc)})
            return
        # `sorunlar`: stray manifests at the workshop root. The panel shows
        # them in a separate "problematic" section with the reason — a
        # manifest written to the wrong place must not vanish silently.
        self._json(data)

    def _apps_running(self) -> None:
        """Running, watchable applications (with their live addresses).

        Empty list without a bridge/workshop: the panel shows that as
        "nothing running". The workshop root is passed so a server that is
        NOT in the process book but belongs to the workshop (if dornick was
        restarted) also shows as live.
        """
        from .. import apps as catalog

        config = getattr(self.server, "config", None)
        root = base = None
        try:
            if config is not None:
                root = config.open_sandbox().root
                base = Path(config.workspace)
        except Exception:
            root = base = None
        try:
            self._json({"running": catalog.running(root, base)})
        except Exception as exc:
            self._json({"running": [], "error": str(exc)})

    # -- artifacts -------------------------------------------------------

    def _artifacts_list(self) -> None:
        """Published artifacts: id, title, version, updated.

        Empty list without a store — the gallery shows that as "none yet".
        """
        from .. import artifacts

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"artifacts": []})
            return
        self._json({"artifacts": artifacts.listing(config.state_dir)})

    def _artifacts_edit(self, body: dict[str, Any]) -> None:
        """The gallery's only write endpoint: {"action": "remove", "id": ...}.

        No permanent deletion — the store moves to the bin; confirmation is
        in the UI (two-step button). The reply carries the current list in
        every case so the panel does not go stale.
        """
        from .. import artifacts

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        action = str((body or {}).get("action") or "")
        if action != "remove":
            self._json({"ok": False, "error": "`action` remove olmalı",
                        "artifacts": artifacts.listing(config.state_dir)})
            return
        try:
            artifacts.remove(config.state_dir, str((body or {}).get("id") or ""))
        except (artifacts.ArtifactError, OSError) as exc:
            self._json({"ok": False, "error": str(exc),
                        "artifacts": artifacts.listing(config.state_dir)})
            return
        self._json({"ok": True, "artifacts": artifacts.listing(config.state_dir)})

    def _open_outside(self, body: dict[str, Any]) -> None:
        """Opens an in-app page in the user's REAL browser.

        Proven wound (31.08): the agent stated the artifact address with the
        default port 8765, the server was running on a shifted port and the
        user saw "connection refused". The real port is known only here, in
        the server itself — the address is built from here, not from the
        request. The path MUST be RELATIVE: this endpoint only opens pages
        THIS server serves; it cannot be a door for opening an outside
        address in the user's browser.
        """
        import webbrowser

        path = str((body or {}).get("path") or "").strip()
        if not path.startswith("/") or path.startswith("//"):
            self._json({"ok": False, "error": "Yalnız uygulama içi yol açılır"})
            return
        host, port = self.server.server_address[:2]
        url = f"http://{host}:{port}{path}"
        try:
            ok = webbrowser.open(url)
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return
        self._json({"ok": bool(ok), "url": url})

    def _artifact_download(self, body: dict[str, Any]) -> None:
        """Saves the artifact into the Downloads folder; returns the FULL path.

        Window WebView2: blob + <a download> click died silently without
        opening a download window — the user lived "I can't download"
        (live, 31.08). The server itself writes to disk; the UI shows the
        returned path. An existing file is not overwritten — a new
        counter-suffixed name is opened.
        """
        import shutil

        from .. import artifacts

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "Yapılandırma yüklü değil"})
            return
        aid = str((body or {}).get("id") or "").strip()
        if not aid:
            m = re.match(r"^/artifact/([a-z0-9-]+)/?", str((body or {}).get("path") or ""))
            if m:
                aid = m.group(1)
        page = artifacts.page_path(config.state_dir, aid)
        if page is None:
            self._json({"ok": False, "error": "Artifact yok"})
            return
        try:
            meta = artifacts.read_meta(config.state_dir, aid)
        except artifacts.ArtifactError:
            meta = {}
        raw_name = str(meta.get("title") or aid).strip() or aid
        stem = re.sub(r"[^\w .-]+", "_", raw_name, flags=re.UNICODE).strip(" ._") or aid
        folder = Path.home() / "Downloads"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            folder = config.state_dir
        target = folder / f"{stem}.html"
        n = 2
        while target.exists():
            target = folder / f"{stem}-{n}.html"
            n += 1
        try:
            shutil.copyfile(page, target)
        except OSError as exc:
            self._json({"ok": False, "error": f"Kaydedilemedi: {exc}"})
            return
        self._json({"ok": True, "path": str(target)})

    def _artifact_page(self, route: str) -> None:
        """Artifact page: /artifact/<id>/ → index.html.

        The path comes from the request but the disk path is not built from
        the request: the id passes through the store module's strict
        pattern and that the resolved path stays under the store is
        verified there once more (the principle of the ASSETS pattern: what
        is served is a verified record, not request text). The page is
        rendered as is — scripts included; the content is on the local
        machine, a page the user's own agent produced.
        """
        from .. import artifacts

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return

        artifact_id = route[len("/artifact/"):].strip("/")
        page = artifacts.page_path(config.state_dir, artifact_id)
        if page is None:
            self.send_error(404, "Artifact yok")
            return
        try:
            body = page.read_bytes()
        except OSError:
            self.send_error(404, "Artifact okunamadı")
            return
        # ?download=1 → download as a file (HTML standard delivery).
        want_dl = "download=1" in (urlparse(self.path).query or "")
        if want_dl:
            try:
                meta = artifacts.read_meta(config.state_dir, artifact_id)
            except artifacts.ArtifactError:
                meta = {}
            raw_name = str(meta.get("title") or artifact_id).strip() or artifact_id
            self._send(
                200, "text/html; charset=utf-8", body,
                headers={"Content-Disposition": _attachment_disposition(raw_name, ".html")},
            )
            return
        self._send(200, "text/html; charset=utf-8", body)

    def _parts(self) -> list[str] | None:
        """The part selection in the request: ?parcalar=anilar,tanima → list.

        None if the parameter is absent — export/import fall back to the
        old (default) behaviour; unknown names are weeded out by the
        transfer module.
        """
        raw = parse_qs(urlparse(self.path).query).get("parcalar", [""])[0]
        selection = [p.strip() for p in raw.split(",") if p.strip()]
        return selection or None

    def _transfer_export(self) -> None:
        """Downloads what Dornick has accumulated as a portable bundle.

        Selective with `?parcalar=anilar,tanima,projeler,ayarlar`: when
        moving to a server only what is needed is packed. A request without
        the parameter produces exactly the same bundle as before (backwards
        compatibility).
        """
        from .. import transfer

        config = getattr(self.server, "config", None)
        mind = getattr(self.server, "mind", None)
        if config is None or mind is None:
            self.send_error(503, "Bellek bağlı değil")
            return
        try:
            data = transfer.export_bundle(config, mind, self._parts())
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)})
            return
        stamp = _stem_date(getattr(mind, "session_id", "")).replace(" ", "_").replace(":", "")
        name = f"dornick-{stamp or 'paket'}.neobundle"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _transfer_import(self, raw: bytes) -> None:
        """Merges an uploaded bundle into this Dornick.

        Memories are joined (not overwritten); while file parts are
        restored, the existing state that would be crushed is first moved
        under .dornick/yedek-<date>/. `?parcalar=...` processes only the
        requested parts even if the bundle has more.
        """
        from .. import transfer

        config = getattr(self.server, "config", None)
        mind = getattr(self.server, "mind", None)
        if config is None or mind is None:
            self._json({"ok": False, "error": "Bellek bağlı değil"})
            return
        if not raw:
            self._json({"ok": False, "error": "Boş yükleme"})
            return
        try:
            result = transfer.import_bundle(config, mind, raw, self._parts())
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return
        self._json(result)

    def _reset(self, body: dict[str, Any]) -> None:
        """Reset: {"hedef": "anilar"} or {"hedef": "tanima"}.

        Neither is destruction but a move: the current state goes under
        .dornick/yedek-<date>/, then a clean start. Confirmation is in the
        UI (two-step button); here the only safeguard is recognising the
        target name.
        """
        from .. import transfer

        config = getattr(self.server, "config", None)
        if config is None:
            self.send_error(503, "Yapılandırma yüklü değil")
            return
        hub = getattr(self.server, "hub", None)
        target = str((body or {}).get("hedef") or "")

        if target == "anilar":
            mind = getattr(self.server, "mind", None)
            if mind is None:
                self._json({"ok": False, "error": "Bellek bağlı değil"})
                return
            result = transfer.reset_memories(config, mind)
            if result.get("ok") and hub is not None:
                hub.emit({"type": "notice",
                          "text": f"Anılar sıfırlandı ({result['silinen']} kayıt) — "
                                  f"yedek: {result['yedek']}"})
        elif target == "tanima":
            result = recognition.reset(config.state_dir)
            if result.get("ok") and hub is not None:
                text = ("Beni tanı sıfırlandı — taban modele dönüldü"
                        + (f" · yedek: {result['yedek']}" if result.get("yedek") else ""))
                hub.emit({"type": "notice", "text": text})
        else:
            self._json({"ok": False, "error": "`hedef` anilar ya da tanima olmalı"})
            return
        self._json(result)

    def _run_app(self, body: dict[str, Any]) -> None:
        """Launches a script/tool in the workshop.

        Only the inside of the workshop can be run; the boundary is verified
        once more inside `apps.launch`.
        """
        from .. import apps as catalog

        config = getattr(self.server, "config", None)
        if config is None:
            self._json({"ok": False, "error": "Yapılandırma yüklü değil"})
            return
        path = str((body or {}).get("path") or "").strip()
        if not path:
            self._json({"ok": False, "error": "`path` gerekli"})
            return
        root = config.open_sandbox().root
        self._json(catalog.launch(root, path, base=Path(config.workspace)))

    def _sessions(self) -> None:
        """The list of past conversations. NOT brain/memory — raw sessions.

        A conversation is not a memory: memories form from conversations
        separately. This list is the conversations themselves; the net on
        the scene is the memories distilled from them.
        """
        mind = getattr(self.server, "mind", None)
        if mind is None:
            self._json({"sessions": []})
            return
        current = getattr(mind, "session_id", "")
        projects = mind.projects() if hasattr(mind, "projects") else {}
        meta = mind.session_meta() if hasattr(mind, "session_meta") else {}
        controller = getattr(self.server, "controller", None)
        busy = bool(getattr(controller, "_busy", False))
        # Parallel lanes: EVERY chat running in the background must show as
        # "running" in the list — not only the active one. The sidebar
        # badge comes from here.
        running: set[str] = set()
        try:
            for sid, lane in (getattr(controller, "seritler", None) or {}).items():
                if getattr(lane, "busy", False):
                    running.add(sid)
        except Exception:
            pass

        # With `?ara=` the search also runs INSIDE THE TRANSCRIPTS: the
        # sought word is usually not in the title but in the middle of the
        # conversation.
        query = parse_qs(urlparse(self.path).query).get("ara", [""])[0].strip()
        inside = {}
        if query and hasattr(mind, "search_transcripts"):
            try:
                inside = mind.search_transcripts(query)
            except Exception:
                inside = {}   # search is a convenience; if it blows the list still comes

        out = []
        project_names: set[str] = set(projects.values())
        for ep in mind.sessions():
            record = meta.get(ep.session_id) or {}
            is_current = ep.session_id == current
            path = record.get("path") or ""
            project = projects.get(ep.session_id, "")
            # Folder attached but no project label: group by the folder
            # name (old records / chats with only a path assigned).
            if not project and path:
                leaf = Path(str(path)).name.strip()
                if leaf:
                    project = leaf
                    project_names.add(leaf)
            out.append({
                "id": ep.session_id,
                # The user-given name if any; otherwise derived from the digest.
                "title": record.get("ad") or _session_title(ep.digest),
                "named": bool(record.get("ad")),
                "tags": record.get("etiketler") or [],
                "date": _stem_date(ep.session_id),
                "turns": ep.turns,
                "tools": ep.tools[:6],
                "preview": ep.digest[:160],
                "current": is_current,
                # açık = currently selected; koşuyor = EVERY lane whose turn
                # is running (active or background); biten = the rest.
                "status": ("koşuyor" if ((is_current and busy)
                                         or ep.session_id in running)
                           else ("açık" if is_current else "biten")),
                "project": project,
                "path": path,
                "model": record.get("model") or "",
                "provider": record.get("provider") or "",
                "hits": inside.get(ep.session_id, []),
            })

        tags = sorted({e for k in meta.values() for e in (k.get("etiketler") or [])})
        self._json({
            "sessions": out,
            "projects": sorted(project_names),
            "tags": tags,
            "searched": bool(query),
        })

    def _session(self) -> None:
        """One session's conversation transcript (for viewing)."""
        mind = getattr(self.server, "mind", None)
        if mind is None:
            self._json({"turns": []})
            return
        sid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
        # No path/name injection: the id may only be letters/digits/-/_.
        if not sid or not re.match(r"^[A-Za-z0-9_-]+$", sid):
            self.send_error(400, "geçersiz oturum")
            return
        self._json({"id": sid, "turns": mind.transcript(sid)})

    def _raw(self) -> bytes:
        """Reads the body once.

        Reading twice is impossible: the first read consumes the stream, the
        second waits for bytes that will never come and the request hangs.
        """
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b''

    def _is_cross_origin(self) -> bool:
        """Does the request come from a FOREIGN origin?

        True only if an Origin (else Referer) HEADER EXISTS and its origin
        does not match our host:port. With no header at all it returns
        False: the shell, tests, benchmark and local automation send no
        Origin and telling them apart from the UI is impossible at the HTTP
        layer anyway. What is closed is the cross-origin browser POST
        (drive-by CSRF).
        """
        origin = self.headers.get("Origin") or ""
        if not origin:
            ref = self.headers.get("Referer") or ""
            if not ref:
                return False
            origin = ref
        try:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
        except ValueError:
            return True  # unparseable origin: reject on the safe side
        host = (parsed.hostname or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            return True
        try:
            our_port = int(self.server.server_address[1])
        except (AttributeError, IndexError, TypeError, ValueError):
            return False  # if we cannot know the port the host match is enough
        # If the origin states a port it must match; if not (rarely) the host is enough.
        return parsed.port is not None and int(parsed.port) != our_port

    def _controller_call(self, name: str, *args: Any) -> Any:
        controller = getattr(self.server, "controller", None)
        fn = getattr(controller, name, None) if controller else None
        # A missing method (e.g. an observe-only preview or a bridge that
        # does not support new_session) is silently None: the endpoint
        # turns that into ok:false, does not throw 500.
        return fn(*args) if callable(fn) else None

    # -- response formats -----------------------------------------------

    def _logo_png(self) -> None:
        from ..logo import png_path
        try:
            body = png_path().read_bytes()
        except OSError:
            self.send_error(404)
            return
        self._send(200, "image/png", body)

    def _file(self, name: str, content_type: str) -> None:
        try:
            body = (STATIC / name).read_bytes()
        except OSError:
            self.send_error(404)
            return
        self._send(200, content_type, body)

    def _json(self, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(200, "application/json; charset=utf-8", body)

    def _opening_base(self, config: Any) -> Path:
        """The base relative paths are resolved against: the attached
        project if there is one, else the workspace.

        When the agent writes into an attached folder the card carries a
        path relative to that folder, not "atolye/…"; with the base pinned
        to the workspace "Show in folder" could not find the file (live
        wound, 02.09).
        """
        try:
            project = str(getattr(config.sandbox, "project", "") or "").strip()
            if project:
                path = Path(project).expanduser()
                if path.is_dir():
                    return path
        except Exception:
            pass
        return Path(config.workspace)

    def _create_folder(self, body: dict[str, Any] | None) -> None:
        """Creates a new working folder (and returns its path).

        The "New folder" flow on the chat screen: the user picks a parent
        directory and gives a name, the folder is opened here. It may be
        OUTSIDE the workshop too — the choice is the user's consent (that is
        the sandbox's rule as well). Still, the `kok_engeli` filter applies:
        a drive root, system directories like Windows/Program Files and the
        home directory itself are refused.
        """
        from .. import sandbox as sandbox_mod

        parent = str((body or {}).get("ust") or "").strip()
        name = str((body or {}).get("ad") or "").strip()
        if not parent or not name:
            self._json({"ok": False, "hata": "üst klasör ve ad gerekli"})
            return
        # The name must be a single segment: no climbing to the parent via a path separator or `..`.
        if any(sep in name for sep in ("/", "\\")) or name in (".", ".."):
            self._json({"ok": False, "hata": "Klasör adı yol içeremez"})
            return
        try:
            root = Path(parent).expanduser().resolve()
            target = (root / name).resolve()
        except OSError:
            self._json({"ok": False, "hata": "Yol çözümlenemedi"})
            return
        if root != target.parent:
            self._json({"ok": False, "hata": "Klasör seçilen dizinin altında olmalı"})
            return
        if not root.is_dir():
            self._json({"ok": False, "hata": f"Üst klasör yok: {root}"})
            return
        # The check is on the PARENT directory: the target does not exist
        # yet and `kok_engeli` rejects a non-existent path with "no such
        # folder". The real question is "is opening this folder in a safe
        # place?" anyway — the parent directory answers that.
        if (block := sandbox_mod.root_block(root)) is not None:
            self._json({"ok": False, "hata": block})
            return
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._json({"ok": False, "hata": f"oluşturulamadı: {exc}"})
            return
        self._json({"ok": True, "yol": str(target),
                    "uyari": sandbox_mod.root_warning(target) or ""})

    def _run_update(self) -> None:
        """Downloads the new version and launches the setup wizard.

        The address DOES NOT COME FROM THE CLIENT: the server asks the
        GitHub release API again and takes the trusted download link from
        there (a poisoned URL cannot be injected). The download runs in the
        background; progress flows to the UI over SSE (the "guncelleme"
        event). When done the wizard opens; closing the running application
        is the wizard's own job (PrepareToInstall → "Close and continue").
        """
        import tempfile
        import threading

        info = environment.check_update()
        if not info.get("yeni") or not info.get("indirme"):
            self._json({"ok": False,
                        "hata": info.get("hata") or "İndirilecek güncelleme yok"})
            return

        hub = getattr(self.server, "hub", None)

        def announce(ev: dict) -> None:
            if hub is not None:
                try:
                    hub.emit({"type": "guncelleme", **ev})
                except Exception:
                    pass

        def run() -> None:
            try:
                announce({"asama": "indiriliyor", "yuzde": 0, "yeni": info["yeni"]})
                folder = Path(tempfile.gettempdir()) / "dornick-guncelleme"

                def progress(downloaded: int, total: int) -> None:
                    percent = int(downloaded * 100 / total) if total else 0
                    announce({"asama": "indiriliyor", "yuzde": percent,
                              "indirilen": downloaded, "toplam": total})

                path = environment.download_update(
                    info["indirme"], folder,
                    beklenen_boyut=int(info.get("boyut") or 0),
                    ad=str(info.get("ad") or ""), progress=progress)
                announce({"asama": "kuruluyor", "yeni": info["yeni"]})
                environment.start_update(path)
                announce({"asama": "acildi", "yeni": info["yeni"]})
            except Exception as exc:  # network/verification/launch — honest error to the UI
                announce({"asama": "hata", "hata": f"{type(exc).__name__}: {exc}"})

        threading.Thread(target=run, name="dornick-guncelle", daemon=True).start()
        self._json({"ok": True, "yeni": info["yeni"]})

    def _send(self, status: int, content_type: str, body: bytes,
              headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _stream(self) -> None:
        channel = self.server.hub.register()  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        # In HTTP/1.1 the end of the body is determined either by
        # Content-Length, by chunked, or by the connection closing. Since
        # the length is unknown, saying "keep-alive" left the body unframed:
        # the browser buffered the stream and the reply arrived in bulk.
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")   # for intervening proxies
        self.end_headers()
        self.close_connection = True

        try:
            while True:
                try:
                    line = channel.get(timeout=HEARTBEAT_S)
                except queue.Empty:
                    # Comment line: keeps the connection alive, the client ignores it.
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # tab closed
        finally:
            self.server.hub.unregister(channel)  # type: ignore[attr-defined]
