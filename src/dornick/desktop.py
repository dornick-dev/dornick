"""Desktop application.

The window is the operating system's own webview (WebView2 on Windows) —
exactly what Electron does, but without bundling Chromium. The UI is the
same HTML/CSS/JS; the engine is the same engine.

There are three threads and the boundaries are sharp:

    main thread     the window. pywebview's start() has to run on the main
                    thread and blocks until the window closes.
    asyncio thread  the agent loop.
    HTTP threads    the server; answers requests coming from the UI.

Crossing from the UI to the agent always goes through
`loop.call_soon_threadsafe` or `run_coroutine_threadsafe`. Crossing from
the agent to the UI goes through `Hub.emit` — which is locked internally.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from .backends import build_client
from . import (
    connectors as linking,
    ear as hearing,
    pricing as fiyatlama,
    lmstudio,
    environment,
    prefs,
    prompt,
    schedule as scheduling,
    settings,
    skills,
    recognition,
    tray as tray_module,
    watch as watching,
)
from .config import Config
from .context import ContextPolicy
from .loop import (
    Agent,
    AgentIO,
    BARGE_NOTE,
    clear_park,
    read_park,
    mark_orphan,
    scan_orphans,
)
from .mind import open_mind
from .permissions import PermissionEngine
from .session import Session
from .tools import build_registry
from .tools.base import ToolSpec
from .web import server as server_module
from .web.server import Hub, MindServer

WINDOW_TITLE = "Dornick"
WINDOW_BACKGROUND = "#0b0e14"

# Model used for the wake-word scan. Small and fast is enough: the thing
# being searched for is a single word.
SCOUT_SIZE = "base"

# The question sent to the agent when someone enters the room. Not a greeting
# but a **look** is asked for: see who arrived and, if familiar, greet by name.
# The name was called but nothing followed it ("dornick"). Calling the name
# and then going silent is the same as not hearing: the person across from
# you turns their head and says "yes?". Keeping it short matters — a long
# opening sentence is unnecessary here.
CALLED_ASK = (
    "Kullanıcı yalnızca adını söyledi, arkasından bir şey istemedi. "
    "Tek kelimelik bir karşılık ver (\"efendim\", \"buradayım\" gibi) ve "
    "sus. Araç kullanma, soru sorma, uzatma."
)

# Maximum boot duration. Generous: on first launch a recognition model may
# be downloaded, and that download takes minutes.
BOOT_TIMEOUT_S = 300.0

# The night's distillation call (recall/distil.py PROMPT carries the task;
# this only names the role). Bounded: a hung endpoint must not hold the
# night past the user's return.
NIGHT_SYSTEM = ("Sen dornick'in gece damıtıcısısın. Yalnız verilen kayıtlardan "
                "çalış; istenen biçimde, kısa ve kaynaklı yaz.")
NIGHT_MODEL_TIMEOUT_S = 120.0

GREET_ASK = (
    "Uzun bir sessizlikten sonra kamerada hareket oldu — biri geldi. "
    "`look now` ile bir kere bak ve kim olduğunu gör. Tanıdıysan kısaca "
    "selam ver; tanımadıysan ya da emin değilsen sessiz kal, boş yere "
    "konuşma."
)


# Explicit spoken cancel words: only these stop the running turn. Everything
# else (a new request) is not a cancel, it queues. "Only if I want what I
# just said to cancel the old one can it do that" — the rule the user set.
_STOP_WORDS = ("dur", "durdur", "yeter", "kes", "iptal", "vazgeç", "stop", "sus")


def _is_stop(text: str) -> bool:
    words = text.lower().replace("!", "").replace(".", "").split()
    # Short and consisting only of a stop word: "dur", "yeter dur" and so on.
    # "dur" occurring inside a long sentence (e.g. "durumu anlat") is not a cancel.
    return bool(words) and len(words) <= 2 and all(w in _STOP_WORDS for w in words)


# Closing words: they close the chat window. No reply is given — saying
# "you're welcome!" would reopen the conversation that just closed; a human
# doesn't keep answering a goodbye with a goodbye either. "tamam" alone is
# not on the list: it can also be the answer to a question the agent asked.
_CLOSE_WORDS = ("kapat", "kapan", "görüşürüz", "hoşça kalın", "hoşça kal",
                "hoşçakal", "iyi geceler", "sonra konuşuruz")

# Filler that may come alongside a closing word: "tamam görüşürüz",
# "teşekkürler kapat" also count as a close.
_CLOSE_PAD = frozenset(("tamam", "peki", "teşekkürler", "teşekkür", "ederim",
                        "sağ", "sağol", "ol", "çok", "iyi"))


def _is_close(text: str) -> bool:
    plain = " ".join(text.lower().replace("!", "").replace(".", "").replace(",", "").split())
    if not plain or len(plain.split()) > 4:
        return False
    for phrase in _CLOSE_WORDS:
        if phrase in plain:
            rest = plain.replace(phrase, " ").split()
            return all(w in _CLOSE_PAD for w in rest)
    return False


# Courtesy / waiting: does not go to the model. "teşekkürler" → "rica ederim"
# is an assistant loop; "şimdi bakayım" is not a request. "tamam" alone is
# absent — it can also be a yes to what the agent asked.
_ACK_CORE = frozenset((
    "teşekkürler", "teşekkür", "tesekkurler", "tesekkur",
    "sağol", "sagol", "sağolun", "sagolun", "eyvallah",
    "tamamdır", "thanks", "thx",
    "bakayım", "bakayim",
))
_ACK_PAD = frozenset((
    "çok", "cok", "ederim", "sağ", "sag", "ol", "tamam", "peki",
    "şimdi", "simdi", "bir", "dur", "you", "thank", "oldu", "ben",
))


def _is_ack(text: str) -> bool:
    raw = (text or "").lower().replace("!", "").replace(".", "").replace(",", "")
    raw = raw.replace("'", "")
    words = raw.split()
    if not words or len(words) > 5:
        return False
    joined = " ".join(words)
    if "thank you" in joined:
        return True
    glued = joined.replace("sağ ol", "sağol").replace("sag ol", "sağol")
    words = glued.split()
    if not any(w in _ACK_CORE for w in words):
        return False
    return all(w in _ACK_CORE or w in _ACK_PAD for w in words)


def inherit_last_model(mind: Any, session_id: str, sessions_dir: Any) -> str:
    """Writes the most recently pinned chat model into the new session.

    The catalogue choice lives in the chat meta; since `dornick --app` opens
    a new session on every launch, the pin was getting lost and the global
    old model kept coming back.
    """
    from pathlib import Path

    sid = str(session_id or "")
    mapping = (mind.session_meta() or {}) if mind is not None else {}
    if str((mapping.get(sid) or {}).get("model") or "").strip():
        return str(mapping[sid]["model"]).strip()
    files = sorted(
        Path(sessions_dir).glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        other = path.stem
        if other == sid:
            continue
        rec = mapping.get(other) or {}
        name = str(rec.get("model") or "").strip()
        if not name:
            continue
        mind.set_session_meta(
            sid, model=name, provider=str(rec.get("provider") or ""))
        return name
    return ""


async def _retire(client: Any) -> None:
    """Closes the client that was swapped out.

    Not closing it leaves an open connection; blowing up while closing
    must not stop the agent — the new client is already running.
    """
    try:
        await client.close()
    except Exception:
        pass


# Cap on the number of goals that enter the snapshot. The panel already
# shows only the first six openly; there is no point in carrying hundreds
# of stale goals on every page load.
GOAL_SNAPSHOT_LIMIT = 20


def _active_goals(agent: Any) -> list[dict[str, Any]]:
    """UI dump of the active goals (id + text + whether from this session).

    The goal panel is event-driven (goal_push/goal_status) but a page refresh
    misses the events; the snapshot hands the panel where it left off via
    this list. No mind, or unreadable — empty list: the panel stays hidden,
    the chat does not go down.

    The goal ledger is now filtered to the session (`mind.goals()` default):
    this was the root of the "who is creating these tasks" complaint — items
    from other chats never reach the panel. The `eski` field stays for UI
    compatibility; thanks to the filter it is practically always False.
    """
    mind = getattr(agent, "mind", None)
    if mind is None:
        return []
    current = getattr(mind, "session_id", "")
    try:
        return [
            {"id": g.id, "text": g.text,
             "eski": bool(current and g.session_id and g.session_id != current)}
            for g in mind.goals()[:GOAL_SNAPSHOT_LIMIT]
        ]
    except Exception:
        return []


# Rough token estimate: characters / this number. It never matches the real
# count coming from the provider and is not expected to — what the user
# wants to know is "how full am I", not the exact figure. That is why the
# UI says openly that it is an estimate (in the title).
ESTIMATE_DIVISOR = 4


def context_breakdown(agent: Any, prompt_total: int = 0) -> list[dict[str, Any]]:
    """Item-by-item estimate of the prompt window — Cursor's Context Usage.

    The provider only gives the TOTAL; the breakdown is characters/4. When a
    total exists, the fixed items are scaled so they don't exceed it, and
    the remainder is Conversation.
    """
    import json

    def tok(text: str) -> int:
        return max(0, len(text or "") // ESTIMATE_DIVISOR)

    system_tokens = soul_tokens = 0
    sys = getattr(agent, "_system", None) if agent is not None else None
    if sys is not None:
        system_tokens = tok(getattr(sys, "core", "") or "")
        soul_tokens = tok(getattr(sys, "identity", "") or "")

    # `task` / `task_say` / `task_status` are Cursor's "Subagent definitions"
    # item: keep them apart from the built-in tools, otherwise the Tool
    # definitions line bloats.
    _HELPER_TOOLS = {"task", "task_say", "task_status"}

    tool_tokens = skill_tokens = mcp_tokens = helper_tokens = 0
    registry = getattr(agent, "registry", None) if agent is not None else None
    if registry is not None and hasattr(registry, "all"):
        brief = bool(getattr(agent, "brief_schema", False))
        for spec in registry.all():
            try:
                schema = spec.api_schema()
                if brief and isinstance(schema, dict):
                    desc = str(schema.get("description") or "")
                    schema = {**schema, "description": desc.split("\n\n", 1)[0]}
                blob = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                continue
            n = tok(blob)
            src = str(getattr(spec, "source", None) or "")
            name = str(getattr(spec, "name", "") or "")
            if not name and isinstance(schema, dict):
                name = str(schema.get("name") or "")
            if src.startswith("mcp"):
                mcp_tokens += n
            elif src == "yetenek":
                skill_tokens += n
            elif name in _HELPER_TOOLS:
                helper_tokens += n
            else:
                tool_tokens += n

    parts: list[tuple[str, str, int]] = [
        ("sistem", "Sistem istemi", system_tokens),
        ("arac", "Araç tanımları", tool_tokens),
        ("ruh", "Ruh / kurallar", soul_tokens),
        ("yetenek", "Yetenekler", skill_tokens),
        ("mcp", "MCP ve dinamik araçlar", mcp_tokens),
        ("yardimci", "Yardımcı tanımları", helper_tokens),
    ]
    fixed = sum(n for _, _, n in parts)
    total = max(0, int(prompt_total or 0))
    if total and fixed > total:
        ratio = total / fixed
        parts = [(k, label, int(n * ratio)) for k, label, n in parts]
        fixed = sum(n for _, _, n in parts)
    chat_tokens = max(0, total - fixed) if total else 0
    parts.append(("sohbet", "Konuşma", chat_tokens))
    return [{"id": k, "ad": label, "n": n} for k, label, n in parts]


def _provider_name(agent: Any) -> str:
    """Provider identity to show in the UI (openrouter, ollama, …).

    `model.provider` is the backend type ("openai") and six different
    servers sit under it; telling the user "openai" while connected to
    OpenRouter would be wrong information. The address-based mapping is
    in `settings.provider_of`.
    """
    if agent is None:
        return ""
    try:
        from . import settings
        return settings.provider_of(agent.config.model)
    except Exception:
        return str(getattr(getattr(agent, "config", None), "model", None)
                   and agent.config.model.provider or "")


def _can_run(agent: Any) -> bool:
    """Can the agent actually authenticate?

    Even if the model comes as "oto"/default, without a key no work can be
    done; the UI shows the first-run guidance based on this. A local server
    (localhost/LM Studio) asks for no key — in that case it counts as
    runnable.
    """
    if agent is None:
        return False
    model = getattr(agent, "config", None)
    model = getattr(model, "model", None)
    if model is None:
        return False
    base = (getattr(model, "base_url", "") or "").lower()
    if any(h in base for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1")):
        return True
    env = getattr(model, "api_key_env", "") or ""
    if not env:
        return True   # provider that asks for no key
    if os.environ.get(env):
        return True
    try:
        from . import settings
        return bool(settings.load_keys(agent.config.state_dir).get(env))
    except Exception:
        return False


def _past_usage(agent: Any) -> dict[str, Any]:
    """Context + spend state of a resumed session.

    Proven wound: when the app was closed and reopened, or a conversation
    was resumed from history, the context bar and the cost chip in the dock
    started FROM ZERO. Yet the history is loaded — the user was losing both
    the fullness and the total spend. No model was called in this turn, so
    `_last_usage` is empty; the right source is the session log.

    Two separate figures:
      * `prompt_total` — the prompt of the LAST turn (context bar: how full
        the window is right now).
      * `girdi` — the sum of `prompt_total` over all turns (cost chip: the
        same conservative accounting as the live `_usage_yay`; reopening a
        conversation continues on top of the past instead of from zero).

    Source order:
      1. The `usage` meta of the assistant messages — the real figure the
         provider counted.
      2. Otherwise a rough estimate from the loaded messages (characters/4).
         The `tahmin` flag is carried to the UI: no made-up precision is
         being sold.

    In a new session both come out empty and the counter truly starts at zero.
    """
    empty = {"prompt_total": 0, "girdi": 0, "output": 0, "cagri": 0, "tahmin": False}
    session = getattr(agent, "session", None)
    if session is None:
        return empty
    try:
        messages = session.log.messages()
    except Exception:
        return empty

    calls = 0
    last: dict[str, Any] | None = None
    total_input = 0
    total_output = 0
    for ev in messages:
        if ev.role != "assistant":
            continue
        usage = ev.meta.get("usage")
        if isinstance(usage, dict) and usage.get("prompt_total"):
            last = usage
            calls += 1
            total_input += int(usage.get("prompt_total") or 0)
            total_output += int(usage.get("output") or 0)

    if last is not None:
        return {
            "prompt_total": int(last.get("prompt_total") or 0),
            "girdi": total_input,
            "output": total_output,
            "cagri": calls,
            "tahmin": False,
        }

    # No usage (old log or a provider that gives no counter): rough estimate.
    # Showing an approximation beats showing zero — as long as it is said
    # to be an estimate.
    #
    # The estimate is made FROM THE WINDOW, not from the raw log: the log is
    # never trimmed, and counting the compacted turns (the ones behind the
    # horizon) too was printing "182k token" for a small chat — a figure that
    # never shows up in the provider's panel (live wound, 01.09). `messages()`
    # is the projection of what the NEXT request will really carry; that is
    # the right base.
    try:
        window = session.messages()
    except Exception:
        window = [{"role": e.role, "content": e.content} for e in messages]
    chars = 0
    for message in window:
        chars += len(_text_body(message.get("content")))
    if not chars:
        return empty
    estimate = chars // ESTIMATE_DIVISOR
    return {"prompt_total": estimate, "girdi": estimate, "output": 0,
            "cagri": 0, "tahmin": True}


def _text_body(content: Any) -> str:
    """Text body of a message (for the estimate). Images are not counted.

    tool_result blocks are counted too: their content can be a plain string
    or a list of blocks and they really are carried in the request — the old
    version skipped them and showed the estimate systematically low.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block.get("type") == "tool_result":
            inner = block.get("content")
            if isinstance(inner, str):
                parts.append(inner)
            elif isinstance(inner, list):
                parts.append(_text_body(inner))
    return "\n".join(parts)


# UI language of the helper states. The ledger keeps the Turkish forms;
# the panel side expects the same words as the events (run/done/fail).
_CHANNEL_STATE = {"kosuyor": "run", "bitti": "done", "yetim": "yetim"}


def _local_endpoint(base_url: str) -> bool:
    """Is the model endpoint on the user's machine/network? (loopback + RFC-1918)

    The single criterion for whether a camera frame may leave for the cloud.
    Same definition as `_yerel_mi` in the night school — there must not be
    two different definitions of "local" in two places.
    """
    from urllib.parse import urlparse
    host = (urlparse(str(base_url or "")).hostname or "").casefold()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    return (host.startswith("192.168.") or host.startswith("10.")
            or host.endswith(".local"))


def _send_motion(bridge: Any, config: Config, hub: Hub,
                    sighting: watching.Sighting) -> None:
    """Motion event: analysed locally if there is a GPU, text goes to the model.

    If the GPU analysis succeeds the frame never leaves — the chat model
    reads the text. Without analysis, the old gate: a local model is free,
    the cloud needs cloud_ok. With the HUD off, no chat opens even if the
    watcher still produced a frame.
    """
    if not bool(getattr(config.camera, "enabled", False)):
        return
    cam = sighting.camera
    if callable(getattr(cam, "is_builtin", None)) and cam.is_builtin():
        lens = getattr(bridge, "lens", None)
        if lens is None or not (
            getattr(lens, "running", False) or getattr(lens, "live", False)
        ):
            return
    hub.emit({
        "type": "notice",
        "text": f"{sighting.camera.name}: hareket (%{int(sighting.change * 100)})",
    })
    from . import sight

    summary = ""
    if getattr(sighting.camera, "analyze", True):
        summary = sight.analyze_url(sighting.frame)
    try:
        watching.remember(config.state_dir, sighting.camera, summary or "hareket")
    except Exception:
        pass
    title = f"[{sighting.camera.name}] {sighting.ask}"
    if summary:
        bridge.submit(f"{title}\n\nYerel GPU analizi: {summary}")
        return
    model_url = str(getattr(bridge.agent.config.model, "base_url", "") or "") \
        if bridge.agent is not None else ""
    local = _local_endpoint(model_url)
    if not local and not config.camera.cloud_ok:
        hub.emit({
            "type": "notice",
            "text": (f"{sighting.camera.name}: kare BULUT modele gönderilmedi "
                     "(izin kapalı). Yerel model seç ya da Ayarlar › Kamera'dan "
                     "bulut iznini aç."),
        })
        return
    bridge.submit(title, sighting.frame)


def _drop_finished_channels(agent: Any) -> None:
    """Drops finished helpers from the ledger on session switch.

    "If that chat is over, so is it" (live complaint — the orchestra was
    filling up with finished records from old chats). Running ones and
    orphans (resumable) stay; finished/failed ones are not carried into
    the new chat.
    """
    try:
        children = getattr(agent, "_children", None) or {}
        for cid in [cid for cid, h in children.items()
                    if h.state not in ("kosuyor", "yetim")]:
            children.pop(cid, None)
    except Exception:
        pass


def _live_channels(agent: Any) -> list[dict[str, Any]]:
    """UI dump of the helper channels (the seed of the orchestra panel).

    The panel is event-driven (child_start/child_end) but on a page refresh
    or an app restart the events are missed and the panel could be left with
    ghost "running" cards. The single source of truth is the agent's ledger
    (`Agent._children`): the snapshot hands the panel where it left off via
    this list, and a "running" channel absent from the list is not drawn.
    The same seeding pattern as the goal panel (see _active_goals).
    """
    children = getattr(agent, "_children", None)
    if not children:
        return []
    try:
        return [
            {
                "id": h.id,
                "title": h.title,
                "model": h.model,
                "bg": bool(h.background),
                "kind": h.kind,
                "state": _CHANNEL_STATE.get(h.state, "fail"),
                "ozet": "" if h.state == "kosuyor" else (h.outcome or "")[:200],
            }
            for h in children.values()
        ]
    except Exception:
        return []


# Internal marker dropped into the queue: a background helper finished.
# When pump sees it (the agent is idle at that moment — the queue is serial)
# it opens a resume turn. An object, not text: it cannot be confused with
# any user message.
_CHILD_DONE = object()

# Park record found at boot (a long job left unfinished): when pump sees
# this it resumes the run from where it stopped.
_PARK_RESUME = object()


@dataclass(slots=True)
class Pending:
    """A pending permission request.

    The spec and args are kept alongside the future: when "always allow"
    is chosen, writing the rule needs to know which tool and which target
    it was.
    """

    future: asyncio.Future[bool]
    spec: ToolSpec
    args: dict[str, Any]


@dataclass(slots=False)
class Lane:
    """A session's independent run lane: agent + queue + busy flag.

    The core of parallel sessions (live request, 29.08): "when I say new
    conversation it waits for the old one to finish" — the single-agent /
    single-queue architecture locked session switching to the end of the
    running turn. Now every session has its own lane: its own Agent, its
    own queue, its own pump. The active lane streams to the UI; the ones
    behind write to their own session log and the transcript is loaded from
    there when the user returns.
    """

    sid: str
    agent: Any
    queue: asyncio.Queue
    busy: bool = False
    task: Any = None    # pump task (on the first lane Controller.pump runs it)


class Bridge:
    """Two-way bridge between the UI and the agent.

    The Controller surface is called from the HTTP thread, the AgentIO
    surface from the asyncio thread. Every crossing between the two is
    marked explicitly.
    """

    def __init__(self, hub: Hub, loop: asyncio.AbstractEventLoop) -> None:
        self.hub = hub
        self.loop = loop
        # Lanes: session id -> Lane. The active lane is the session the UI
        # looks at; the others may run in the background (parallel sessions).
        self.lanes: dict[str, Lane] = {}
        self._active_sid: str | None = None
        # Queue of the first lane — so a message can queue even before the
        # agent exists (boot race). When `agent` is assigned the lane takes
        # this queue over.
        self._first_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        # Switching sessions (new/resume) requires rebinding the event stream
        # to the new log; the server does that. _boot gives the reference later.
        self.server: Any = None
        self._pending: dict[str, Pending] = {}
        # The always-listening ear is attached later: during boot the bridge
        # is built before it.
        self.ear: Any = None
        self.lens: Any = None
        self.eyes: Any = None
        # Model change requested mid-turn. Pulling a streaming client out
        # from under a turn kills that answer; it is applied when the turn
        # ends. The whole config is kept because the system prompt is
        # refreshed together with the model.
        self._wanted_model: Any = None
        self._wanted_config: Config | None = None
        # Note to print to the UI on the pending client swap: a real model
        # change, or only a key/settings refresh.
        self._swap_note: str = ""
        # Call that brings the window back when the wake word is heard.
        # The desktop layer sets it; in the UI preview it stays None.
        self.on_wake: Any = None
        # System tray: Windows notification when a background task finishes.
        # The desktop `run()` attaches it; in preview / headless it is None.
        self.tray: Any = None
        # Scheduled tasks missed at boot: the scheduler waits until the
        # user decides (see schedule.run_forever `paused`).
        self._missed_ids: list[str] = []
        self._missed_fire: Any = None
        # Where boot currently stands. Talking before the model is loaded is
        # pointless: the UI keeps the input line closed using this.
        self.stage = "uyanıyor"
        self.ready = False
        # Cost chip: turn and session totals (tokens) + the price tag of the
        # selected model (USD/token, from the OpenRouter catalogue). The price
        # is fetched AT MOST once on a background thread; the turn never
        # waits on the network.
        self._price: dict[str, float] | None = None
        self._price_checked = False
        self._turn_usage = {"girdi": 0, "cikti": 0, "cagri": 0}
        self._session_usage = {"girdi": 0, "cikti": 0, "cagri": 0}
        # The past spend of a resumed session is seeded once; see
        # _seed_session_usage. No seed in a new session — the counter is
        # truly zero.
        self._session_seeded = False
        # Budget brake: upper limit for this session (USD). None = unlimited.
        # It lives not on the settings page but in the cost chip's popover —
        # next to the number. When the cap is reached the running turn stops
        # (see _budget_brake and loop.Agent._drive).
        self._budget_usd: float | None = None
        # Has the cap been reported once: the brake asked before every model
        # call must not print the same line dozens of times in a turn.
        self._budget_reported = False
        # The memory's night (recall/daemon.py): started once the mind is
        # open, stopped in _teardown. The config it reads its switch from is
        # refreshed on every settings save (see reload).
        self.sleeper: Any = None
        self._sleep_config: Config | None = None

    # -- lane surface ---------------------------------------------------
    #
    # The old single-agent fields (`agent`, `queue`, `_busy`) became
    # properties: 30+ call sites keep looking at the active lane unchanged.
    # The write path narrowed — `_busy` can no longer be assigned, busyness
    # is the lane's own flag (see _lane_status).

    def _lane_fields(self) -> None:
        # Tests build the bridge with `Bridge.__new__` without init; the lane
        # fields are completed lazily on first touch.
        if not hasattr(self, "lanes"):
            self.lanes = {}
            self._active_sid = None
        if not hasattr(self, "_first_queue"):
            self._first_queue = asyncio.Queue()

    @property
    def agent(self) -> Any:
        self._lane_fields()
        s = self.lanes.get(self._active_sid or "")
        return s.agent if s else None

    @agent.setter
    def agent(self, value: Any) -> None:
        # _boot compatibility: when the first agent is assigned the first lane
        # is built and takes over the queue accumulated since boot. None =
        # could not be built (model-less boot).
        self._lane_fields()
        if value is None:
            return
        sid = str(getattr(getattr(value, "session", None), "id", "") or "ilk")
        lane = Lane(sid=sid, agent=value, queue=self._first_queue,
                      busy=bool(getattr(self, "_busy_pending", False)))
        self._busy_pending = False
        self.lanes[sid] = lane
        self._active_sid = sid
        # Bind the stream gates to the lane: if this lane drops to the
        # background its events must not leak into the active chat. The
        # helper-done marker should also land in its own queue — not the
        # active lane's.
        try:
            value.io = self.io(lane)
            value.on_children_settled = (
                lambda s=lane: self.loop.call_soon_threadsafe(
                    self._lane_child_done, s))
        except Exception:
            pass

    def _lane(self) -> Lane | None:
        self._lane_fields()
        return self.lanes.get(self._active_sid or "")

    @property
    def queue(self) -> asyncio.Queue:
        s = self._lane()
        return s.queue if s else self._first_queue

    @property
    def _busy(self) -> bool:
        s = self._lane()
        if s is not None:
            return bool(s.busy)
        return bool(getattr(self, "_busy_pending", False))

    @_busy.setter
    def _busy(self, value: bool) -> None:
        # Test compatibility: tests that build the bridge by hand assign
        # busyness directly. The product never uses this path (see
        # _lane_status). If there is no lane yet the flag is held; the first
        # lane takes it over when built.
        s = self._lane()
        if s is not None:
            s.busy = bool(value)
        else:
            self._busy_pending = bool(value)

    def _lane_status(self, lane: Lane, busy: bool) -> None:
        """Records the lane's busyness and announces it on the right channels.

        The classic `status` is published only for the ACTIVE lane (the UI
        has a single composer); the `lane` event goes out for every lane —
        the sidebar shows which chats are running with a badge.
        """
        lane.busy = busy
        if lane.sid == self._active_sid:
            self.hub.emit({"type": "status", "busy": busy})
        self.hub.emit({"type": "lane", "id": lane.sid, "busy": busy})

    # -- called from the HTTP thread ------------------------------------

    def submit(self, text: str, image: str = "", *, queue: bool = False) -> None:
        """Hands the user message to the agent.

        Plain text arriving while the agent is BUSY now goes not to the queue
        but into the running turn's inbox: the message lands in front of the
        model as a harness note at the next step of the same turn
        ("interjection"). The user can change direction without waiting for
        the turn to end.

        The old queue behaviour is kept in three cases:
          * `queue=True` — sources such as scheduled tasks and the external
            gate, which must not mix into the middle of the running job.
          * A message with an image — an image block cannot enter a harness
            note (the system channel is plain text); the old queue keeps it
            simple.
          * The inbox is full — an interjection is a single gesture, not a
            flood.
        """
        if not image and _is_ack(text):
            return
        agent = self.agent
        if (self._busy and not queue and not image
                and agent is not None and not agent.inbox_full()):
            self.hub.emit({"type": "araya", "text": text})
            note = BARGE_NOTE.format(text=text)
            self.loop.call_soon_threadsafe(
                lambda: agent.take_note(note, encode=text))
            return
        # A message queued while the agent runs is not dropped, but its
        # waiting in line must show on screen: the user typed, hit enter and
        # it looked like nothing happened.
        if self._busy:
            self.hub.emit({"type": "queued", "text": text})
        asyncio.run_coroutine_threadsafe(self.queue.put((text, image)), self.loop)

    def child_done(self) -> None:
        """A background helper finished (called from the asyncio thread).

        The internal marker lands in the queue; when its turn comes (agent
        idle) a resume turn opens. If the agent is busy the marker waits in
        the queue for the turn to end — by then the result may already have
        been delivered by the note at the start of the turn, and `_resume`
        does not call the model for nothing. (Backward compat: active lane.
        The lane-specific path is `_lane_child_done` — every agent binds to
        its own lane.)
        """
        self.queue.put_nowait(_CHILD_DONE)

    def _lane_child_done(self, lane: Lane) -> None:
        lane.queue.put_nowait(_CHILD_DONE)

    def run_scheduled(self, task: Any) -> dict[str, Any]:
        """Runs a scheduled task as an Orchestra helper, not in the chat.

        Automation (`kind_ui=automation` + workflow_id) → workflow runner;
        simple task → silent spawn_scheduled. Every run is written to
        task_runs.
        """
        agent = self.agent
        if agent is None:
            return {"ok": False, "error": "ajan henüz hazır değil"}

        title = str(getattr(task, "title", "") or "görev")
        prompt = str(getattr(task, "prompt", "") or "")
        tid = str(getattr(task, "id", "") or "")
        kind_ui = str(getattr(task, "kind_ui", "") or "simple")
        workflow_id = str(getattr(task, "workflow_id", "") or "")

        if kind_ui == "automation" and workflow_id and hasattr(agent, "run_workflow"):
            try:
                # The task id is passed along: the run should be written to
                # the ledger the UI looks at (see the rationale inside
                # `run_workflow`).
                fut = asyncio.run_coroutine_threadsafe(
                    agent.run_workflow(workflow_id, tid), self.loop)
                result = fut.result(timeout=30)
                return result if isinstance(result, dict) else {"ok": True, "result": result}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        if not hasattr(agent, "spawn_scheduled"):
            return {"ok": False, "error": "zamanlanmış koşum yok"}
        if not prompt.strip():
            return {"ok": False, "error": "görev metni boş"}

        box: dict[str, Any] = {}
        done = threading.Event()

        def _start() -> None:
            try:
                handle = agent.spawn_scheduled(title, prompt, tid)
                book = getattr(agent, "schedule", None)
                if book is not None and tid:
                    book.mark_running(tid, handle.id)
                box.update({"ok": True, "id": handle.id, "title": handle.title,
                            "run_id": getattr(handle, "run_id", "")})
            except Exception as exc:
                box.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                done.set()

        self.loop.call_soon_threadsafe(_start)
        if not done.wait(15):
            return {"ok": False, "error": "zaman aşımı"}
        return box or {"ok": False, "error": "başlatılamadı"}

    def new_session(self) -> dict[str, Any]:
        """Starts a fresh conversation: new session, empty context."""
        return self._switch(None)

    def resume_session(self, sid: str) -> dict[str, Any]:
        """Resumes a past conversation: makes that session active, loads its
        context (past messages) and new messages are appended there."""
        return self._switch(sid)

    def open_path(self, path: str, *, message: str = "") -> dict[str, Any]:
        """Windows 'Open with Dornick': new chat + working folder, and nothing else.

        File → parent folder is the project; folder → the project directly.
        The path is written into the new session's meta. Only an EXPLICIT
        `message` enters the queue: opening a folder used to auto-send
        "Bu klasörü açtım … Ne yapmamı istersin?", and the agent answered
        its own question by reading files and drafting a plan before the
        user had typed a word (2026-09-04). A folder is a place, not a
        request; the first message is the user's.
        """
        from pathlib import Path

        raw = str(path or "").strip().strip('"')
        if not raw:
            return {"ok": False, "error": "yol boş"}
        target = Path(raw).expanduser()
        try:
            target = target.resolve()
        except OSError:
            return {"ok": False, "error": "yol çözülemedi"}
        if not target.exists():
            return {"ok": False, "error": "yol yok"}

        folder = target if target.is_dir() else target.parent
        seed = (message or "").strip()

        switched = self._switch(None)
        if not switched.get("ok"):
            return switched
        sid = str(switched.get("id") or "")
        agent = self.agent
        if agent is not None and sid and hasattr(agent.mind, "set_session_meta"):
            try:
                agent.mind.set_session_meta(
                    sid,
                    name=folder.name[:80] or "Dornick ile aç",
                    path=str(folder),
                )
                # Write it to the project-folder tag too: group it in the
                # history list.
                if hasattr(agent.mind, "set_project"):
                    agent.mind.set_project(sid, folder.name[:80] or "Dornick ile aç")
            except Exception:
                pass
            try:
                self._apply_session_context(sid)
            except Exception:
                pass

        # Seed message: via the chat queue (starts at once if the turn is idle).
        if seed:
            try:
                self.submit(seed)
            except Exception:
                pass
        try:
            self.hub.emit({"type": "jobs_refresh"})
            self.hub.emit({"type": "notice", "text": f"Açıldı: {folder}"})
        except Exception:
            pass
        return {"ok": True, "id": sid, "path": str(folder)}

    def apply_session_context(self, session_id: str) -> None:
        """External call (chat model picked/cleared): apply to the live agent."""
        self._apply_session_context(session_id)

    def _apply_session_context(self, session_id: str) -> None:
        """Applies the folder + model from the session meta to the live agent.

        Both are CHAT-specific and applied only IN MEMORY — the old version
        wrote the folder to disk through settings.apply; even when the new
        conversation had no path, the previous project's git bar
        (dornick / branch) stayed. The base is always the global setting on
        disk: a pin rides on top of it, and without a pin (or once deleted)
        the base comes back.
        """
        agent = self.agent
        if agent is None:
            return
        mind = agent.mind
        if not hasattr(mind, "session_meta"):
            return
        record = (mind.session_meta() or {}).get(session_id) or {}
        path = str(record.get("path") or "").strip()
        model_name = str(record.get("model") or "").strip()

        from dataclasses import replace as _replace

        from . import settings as saved_settings

        try:
            disk = saved_settings._from_disk(agent.config)
        except Exception:
            disk = agent.config

        # Folder: the chat's path if it has one, otherwise the global project.
        disk_project = str(disk.sandbox.project or "").strip()
        target_project = path or disk_project
        if target_project != str(agent.config.sandbox.project or "").strip():
            try:
                self.reload(_replace(
                    agent.config,
                    sandbox=_replace(agent.config.sandbox, project=target_project),
                ))
            except Exception:
                pass

        base = disk.model
        if model_name and saved_settings.batch_only_model(model_name):
            model_name = model_name.rsplit(":", 1)[0]
        target = _replace(base, name=model_name) if model_name else base
        if target != agent.config.model:
            try:
                # Fill in the catalogue window for the chat pin as well.
                if model_name:
                    try:
                        target = saved_settings.adopt_caps(agent.config, target)
                    except Exception:
                        pass
                self.reload(_replace(agent.config, model=target))
            except Exception:
                pass

        # The composer's git bar reads from the live config; unless refreshed
        # on session change the old repo/branch name hangs in the new chat.
        hub = getattr(self, "hub", None)
        if hub is not None:
            try:
                hub.emit({"type": "git"})
            except Exception:
                pass

    def _switch(self, sid: str | None) -> dict[str, Any]:
        """Switches the active session. sid None means new, otherwise that session.

        Parallel sessions (live request, 29.08): switching works EVEN WHILE
        BUSY. If the active lane is idle, the cheap path — the same agent
        binds to the new session (the lane count stays at 1). If busy, the
        running lane is NOT TOUCHED: a separate lane is found or built for
        the target; the old turn finishes in the background on its own lane,
        and the sidebar badge shows it running.
        """
        active = self._lane()
        agent = active.agent if active else None
        if agent is None or self.server is None:
            return {"ok": False, "error": "henüz hazır değil"}

        from pathlib import Path

        from .events import EventLog
        from .session import Session

        sessions_dir = agent.config.sessions_dir

        # Is the target already on a lane (running or waiting in the background)?
        if sid and sid in self.lanes and sid != self._active_sid:
            return self._activate(self.lanes[sid], resumed=True)

        if sid:
            path = Path(sessions_dir) / f"{sid}.jsonl"
            if not path.is_file():
                return {"ok": False, "error": "oturum bulunamadı"}
            session = Session(EventLog(path), sid)
            resumed = True
        else:
            session = Session.create(sessions_dir)
            resumed = False

        previous_sid = ""
        if agent.session is not None:
            previous_sid = str(getattr(agent.session, "id", "") or "")

        if active.busy:
            # The session is not pulled out from under a running lane: a NEW
            # lane for the target.
            try:
                fresh_lane = self._build_lane(session)
            except Exception as exc:
                return {"ok": False,
                        "error": f"şerit kurulamadı: {type(exc).__name__}: {exc}"}
            self._inherit_model(agent, previous_sid, session, resumed)
            return self._activate(fresh_lane, resumed=resumed)

        # Cheap path on an idle lane: the same agent binds to the new session.
        old_key = active.sid
        old_session = agent.session      # its log is closed below
        agent.session = session
        agent.mind.session_id = session.id
        agent._last_encoded = ""      # reset the instant-encode dedupe in the new session
        active.sid = session.id
        self.lanes.pop(old_key, None)
        self.lanes[session.id] = active
        self._active_sid = session.id
        self.server.rebind(session)
        # CLOSE the old session's log file. Windows won't let an open file be
        # moved: left open, the user got "WinError 32 — the file is being used
        # by another process" when trying to delete/archive that chat (live
        # wound, 02.09; seen both on my side and the user's). If another lane
        # holds the same session it is left alone.
        try:
            if (old_session is not None and old_session is not session
                    and not any(getattr(s.agent, "session", None) is old_session
                                for s in self.lanes.values())):
                old_session.close()
        except Exception:
            pass
        self._inherit_model(agent, previous_sid, session, resumed)
        # Chat-specific folder / model — apply on switch.
        try:
            self._apply_session_context(session.id)
        except Exception:
            pass
        _drop_finished_channels(agent)
        # Counters are chat-specific: the previous conversation's spend must
        # not linger in the new/other chat; a resumed chat gets its past total.
        self._reset_usage()
        if resumed:
            try:
                self._seed_session_usage(_past_usage(agent))
            except Exception:
                pass
        self.hub.emit({"type": "session_reset", "id": session.id, "resumed": resumed})
        self.hub.emit({"type": "channels", "channels": _live_channels(agent)})
        return {"ok": True, "id": session.id, "resumed": resumed}

    def _inherit_model(self, agent: Any, previous_sid: str, session: Any,
                     resumed: bool) -> None:
        """The new chat inherits the last chat's model — only if the last
        chat PINNED a model. For a user who doesn't pin, the flow is as
        before: whatever the global default is."""
        if resumed or not previous_sid or not hasattr(agent.mind, "session_meta"):
            return
        try:
            old_record = (agent.mind.session_meta() or {}).get(previous_sid) or {}
            if old_record.get("model"):
                agent.mind.set_session_meta(
                    session.id,
                    model=str(old_record["model"]),
                    provider=str(old_record.get("provider") or ""))
        except Exception:
            pass

    def _activate(self, lane: Lane, *, resumed: bool) -> dict[str, Any]:
        """Makes an existing lane the one the UI looks at.

        A running lane is not touched — only the broadcast target changes:
        the server binds to that session's log, the UI reloads the transcript
        from there, busyness and channels are printed from that lane's truth.
        """
        self._active_sid = lane.sid
        self.server.rebind(lane.agent.session)
        try:
            self._apply_session_context(lane.sid)
        except Exception:
            pass
        self._reset_usage()
        if resumed:
            try:
                self._seed_session_usage(_past_usage(lane.agent))
            except Exception:
                pass
        self.hub.emit({"type": "session_reset", "id": lane.sid,
                       "resumed": resumed})
        self.hub.emit({"type": "status", "busy": lane.busy})
        self.hub.emit({"type": "channels",
                       "channels": _live_channels(lane.agent)})
        return {"ok": True, "id": lane.sid, "resumed": resumed}

    def _build_lane(self, session: Any) -> Lane:
        """Builds an independent lane for a new session.

        The agent from scratch: its own mind (same SQLite, separate
        connection — session ids must not mix), its own registry, a CLEAN
        base configuration (a model pinned by another chat does not leak in
        here; the chat-specific pin arrives on activation through
        `_apply_session_context`). The model client is shared FROM THE CACHE
        for the same (name, address): on a local server two clients would
        make the model load twice; the shared client's gate already
        serialises requests.
        """
        template = self._lane()
        if template is None or template.agent is None:
            raise RuntimeError("kurulu şerit yok")
        cfg = settings._from_disk(template.agent.config)

        mind = open_mind(cfg.mind_dir, cfg.sessions_dir, session.id)
        registry = build_registry(mind, subagents=not prompt.is_lean(cfg))

        if not hasattr(self, "_clients"):
            self._clients: dict[tuple[str, str], Any] = {}
            old_model = template.agent.config.model
            self._clients[(old_model.name, str(old_model.base_url or ""))] = (
                template.agent.client)
        key = (cfg.model.name, str(cfg.model.base_url or ""))
        client = self._clients.get(key)
        if client is None:
            client = build_client(cfg.model)
            self._clients[key] = client

        lane = Lane(sid=session.id, agent=None, queue=asyncio.Queue())
        agent = Agent(
            config=cfg,
            session=session,
            registry=registry,
            client=client,
            io=self.io(lane),
            permissions=PermissionEngine.from_config(cfg.permissions),
            policy=ContextPolicy(cfg.context),
            schedule=getattr(template.agent, "schedule", None),
            mind=mind,
        )
        agent.on_children_settled = (
            lambda s=lane: self.loop.call_soon_threadsafe(
                self._lane_child_done, s))
        agent.on_retry_wait = self._swap_model
        lane.agent = agent
        self.lanes[session.id] = lane
        lane.task = self.loop.create_task(self._pump_lane(lane))
        return lane

    def compact_now(self) -> dict[str, Any]:
        """Compacts the context NOW (the `/sifirla` command in the composer).

        The same path also runs on its own: when the window nears full,
        `_relieve_pressure` already calls this. The only difference here is
        that the user makes the call — being able to say "the conversation
        got heavy, gather it up".

        Only while idle: summarising and replacing the history from under a
        streaming turn breaks that answer.
        """
        lane = self._lane()
        agent = lane.agent if lane else None
        if agent is None:
            return {"ok": False, "error": "henüz hazır değil"}
        if lane.busy:
            return {"ok": False, "error": "Dornick meşgul; tur bitince dene", "busy": True}

        async def _run() -> None:
            self._lane_status(lane, True)
            try:
                if not await agent._compact(reason="kullanıcı istedi"):
                    self._lane_emit(lane, {"type": "notice", "text":
                                   "Sıkıştıracak kadar geçmiş yok — bağlam zaten kısa."})
            except Exception as exc:   # compaction must not bring the app down
                self._lane_emit(lane, {"type": "notice",
                                          "text": f"{type(exc).__name__}: {exc}"})
            finally:
                self._lane_status(lane, False)
                self._lane_emit(lane, {"type": "turn_end"})

        asyncio.run_coroutine_threadsafe(_run(), self.loop)
        return {"ok": True}

    def wake(self) -> None:
        """The wake word was heard: if the window is hidden, bring it back.

        The page runs and the microphone listens even while the window is
        hidden; while the heard phrase is being answered the user needs to
        be able to see the answer.
        """
        if self.on_wake is not None:
            self.on_wake()

    def interrupt(self) -> None:
        if self.agent is not None:
            self.loop.call_soon_threadsafe(self.agent.interrupt)

    def resolve_approval(
        self, request_id: str, granted: bool, *, always: bool = False
    ) -> None:
        pending = self._pending.get(request_id)
        if pending is None or pending.future.done():
            return
        if always and granted and self.agent is not None:
            # The same tool and the same target must not be asked again. The
            # rule is written into the permission engine; the decision stays
            # outside the loop.
            rule =self.agent.permissions.remember_allow(pending.spec, pending.args)
            self.hub.emit({"type": "notice", "text": f"Kural eklendi: {rule}"})
        self.loop.call_soon_threadsafe(pending.future.set_result, granted)

    def reload(self, config: Config, *, force: bool = False) -> None:
        """Called when the settings page saves.

        Permission mode and context policy take effect at once. The model
        does too now: pressing "save", seeing nothing change, then
        discovering you have to close and reopen the program is not a good
        settings page.

        `force`: rebuild the client even if the model name/address stayed the
        same. Required on a key change — the API key is not part of
        `ModelConfig` (only the env name), so changing the key does not
        change `config.model` and the old client stayed with the old key;
        the new key only took effect after a restart. Now the client is
        refreshed on a key change too.

        The history is carried over to the new model — the user is told, it
        is not done silently. If we are mid-turn the change waits until the
        next model call (between tool rounds): the streaming answer is not cut.
        """
        agent = self.agent
        # The sleep daemon reads its on/off switch and the model's locality
        # from here, so a saved setting reaches the next night at once.
        self._sleep_config = config
        if agent is None:
            self.sync_camera(config)
            self.sync_hearing(config)
            self.hub.emit({
                "type": "voice",
                "enabled": bool(config.voice.enabled),
            })
            return

        was = agent.permissions.mode
        before = agent.config.model
        agent.permissions = PermissionEngine.from_config(config.permissions)

        # Pending permission cards are RE-EVALUATED under the new mode: a user
        # who switches to full authority expects the open card to approve
        # itself. The old version left the card hanging — the turn waited for
        # permission forever, even Stop didn't work (live wound, 01.09: "I
        # gave yolo permission, said full authority, and it just stayed").
        from .permissions import Decision as _Decision
        # getattr: preview/test bridges may be built with __new__.
        for pending_req in tuple(getattr(self, "_pending", {}).values()):
            if pending_req.future.done():
                continue
            try:
                decision, _rule = agent.permissions.evaluate(
                    pending_req.spec, pending_req.args)
            except Exception:
                continue
            if decision is _Decision.ALLOW or decision is _Decision.DENY:
                value = decision is _Decision.ALLOW
                fut = pending_req.future
                self.loop.call_soon_threadsafe(
                    lambda f=fut, d=value: None if f.done() else f.set_result(d))

        if was != config.permissions.mode:
            self.hub.emit({"type": "notice", "text": f"İzin kipi: {config.permissions.mode}"})
            # The dock chip and the plan-approve button should show the real
            # mode: a mode changed from OUTSIDE the settings page (another
            # tab, the external gate) must also reach the UI as an event —
            # the notice text is not machine-readable.
            self.hub.emit({"type": "mode", "mode": config.permissions.mode})

        model_changed = before != config.model
        if model_changed or force:
            # The client (and with it the system prompt) is rebuilt; if we
            # are mid-turn it is applied before the next client.turn.
            self._wanted_model = config.model
            self._wanted_config = config
            self._swap_note = (
                f"Model değişti: {config.model.name}. Konuşma geçmişi taşındı."
                if model_changed
                else "Ayarlar uygulandı — istemci tazelendi (anahtar/adres)."
            )
            if not self._busy:
                self._swap_model()
        else:
            # Same model but something else may have changed: a sense was
            # switched on, a device added, the context policy changed. These
            # must enter the next turn immediately — no restart needed.
            agent.reconfigure(config)
        # The camera switch is immediate: a settings save starts/stops the
        # Lens, no restart needed (LED/GPU must be able to go off mid-session).
        self.sync_camera(config)
        self.sync_hearing(config)
        self.hub.emit({
            "type": "voice",
            "enabled": bool(config.voice.enabled),
        })

    def _on_camera_motion(self, sighting: watching.Sighting) -> None:
        """Watcher motion: no chat opens while the HUD is off.

        The setting is read live — no closure bound to the flag at boot.
        """
        agent = getattr(self, "agent", None)
        cfg = getattr(agent, "config", None) if agent is not None else None
        if cfg is None:
            server = getattr(self, "server", None)
            cfg = getattr(server, "config", None) if server is not None else None
        if cfg is None or not bool(getattr(cfg.camera, "enabled", False)):
            return
        _send_motion(self, cfg, self.hub, sighting)

    def sync_camera(self, config: Config) -> dict[str, Any]:
        """Applies the camera switch to the hardware: Lens, watcher, LED, YOLO warmth.

        The HUD only turned the Lens off; the background watcher (Watcher)
        kept reading the cameras and printing motion messages into the chat.
        Both go through the same gate.
        """
        from . import sight, watch as watching

        want = bool(config.camera.enabled)
        server = getattr(self, "server", None)
        httpd = getattr(server, "_httpd", None) if server else None
        agent = getattr(self, "agent", None)
        lens = getattr(self, "lens", None)
        eyes = getattr(self, "eyes", None)
        live = False
        note = ""
        if want:
            if not watching.available():
                note = "opencv yok"
            else:
                if lens is None:
                    lens = watching.Lens()
                    self.lens = lens
                if not lens.running:
                    if lens.start():
                        live = True
                        threading.Thread(
                            target=sight.ensure_warmup, daemon=True,
                            name="dornick-sight-warm").start()
                    else:
                        note = "kamera açılamadı"
                else:
                    lens.unsnooze()
                    live = True
                if agent is not None:
                    agent.lens = lens
                if httpd is not None:
                    httpd.lens = lens
                if eyes is None:
                    eyes = watching.Watcher([], self._on_camera_motion)
                    self.eyes = eyes
                eyes.load_from(watching.load(config.state_dir))
                eyes.unsnooze()
                if eyes.start():
                    live = True
                if agent is not None:
                    agent.watcher = eyes
        else:
            if lens is not None:
                lens.stop()
            if eyes is not None:
                eyes.stop()
            if agent is not None:
                agent.lens = None
                agent.watcher = None
            if httpd is not None:
                httpd.lens = None
        if server is not None:
            server.lens = lens if want else None
        payload = {
            "type": "camera",
            "enabled": want,
            "live": live,
            "note": note,
        }
        hub = getattr(self, "hub", None)
        if hub is not None:
            hub.emit(payload)
        return payload

    def camera_power(self, on: bool) -> str:
        """Chat/HUD: turn the camera fully on or off (writes the setting too)."""
        from . import settings as settings_mod

        agent = getattr(self, "agent", None)
        server = getattr(self, "server", None)
        cfg = agent.config if agent is not None else getattr(server, "config", None)
        if cfg is None:
            return "Kamera ayarı yok."
        updated = settings_mod.apply(cfg, {"camera": {"enabled": bool(on)}})
        if server is not None:
            server.config = updated
        if agent is not None:
            agent.reconfigure(updated)
        result = self.sync_camera(updated)
        if on and result.get("live"):
            return (
                "Kamera açık. LED yanıyor. Sorduğunda yerel analiz metin "
                "olarak gelir; resim kendiliğinden modele gitmez."
            )
        if on:
            return "Kamera açılamadı" + (
                f": {result['note']}" if result.get("note") else ".")
        return "Kamera kapalı. Aygıt bırakıldı, LED söner."

    def sync_hearing(self, config: Config) -> dict[str, Any]:
        """Applies the listening switch to the hardware: Ear start/stop.

        Saving the setting alone was not enough — the flag changed, but the
        ear only opened after a restart; so only push-to-talk was heard.
        The ear opens if there is a wake word or open listening (`open`).
        """
        from . import listen as recogniser

        want = _hearing_wanted(config)
        server = getattr(self, "server", None)
        httpd = getattr(server, "_httpd", None) if server else None
        agent = getattr(self, "agent", None)
        ear = getattr(self, "ear", None)
        live = False
        note = ""

        def wire(next_ear: Any) -> None:
            self.ear = next_ear
            if httpd is not None:
                httpd.ear = next_ear
            if agent is not None:
                agent.ear = next_ear

        if want:
            if _ear_alive(ear):
                ear.open = bool(config.listen.open)
                ear.wake = config.listen.wake
                ear.unsnooze()
                live = True
                wire(ear)
            else:
                if ear is not None:
                    try:
                        ear.stop()
                    except Exception:
                        pass
                hub = getattr(self, "hub", None)
                if hub is None:
                    note = "hub yok"
                    wire(None)
                else:
                    ear = _open_ear(config, self, hub)
                    if ear is None:
                        note = "kulak açılamadı"
                        wire(None)
                    else:
                        live = True
                        wire(ear)
                        if httpd is not None:
                            server_module.warm_ear(httpd, config)
        else:
            if ear is not None:
                try:
                    ear.stop()
                except Exception:
                    pass
            wire(None)
            if not config.listen.enabled:
                note = ""
            elif not hearing.available():
                note = "mikrofon paketi yok"
            elif not recogniser.available():
                note = "tanıma paketi yok"
            elif not (config.listen.wake.strip() or config.listen.open):
                note = "uyandırma veya serbest dinleme yok"

        payload = {
            "type": "hearing",
            "enabled": bool(config.listen.enabled),
            "live": live,
            "open": bool(config.listen.open),
            "wake": bool(config.listen.wake.strip()),
            "snoozed": bool(self.ear is not None
                            and getattr(self.ear, "snoozed", False)),
            "note": note,
        }
        hub = getattr(self, "hub", None)
        if hub is not None:
            hub.emit(payload)
        return payload

    def hearing_power(self, on: bool) -> str:
        """HUD: turn listening on or off (writes the setting too).

        Turning it on also opens free listening: the heard sentence goes to
        the agent without waiting for the wake word. Turning it off releases
        the microphone.
        """
        from . import settings as settings_mod

        agent = getattr(self, "agent", None)
        server = getattr(self, "server", None)
        cfg = agent.config if agent is not None else getattr(server, "config", None)
        if cfg is None:
            return "Dinleme ayarı yok."
        updated = settings_mod.apply(cfg, {
            "listen": {"enabled": bool(on), "open": bool(on)},
        })
        if server is not None:
            server.config = updated
        if agent is not None:
            agent.reconfigure(updated)
        result = self.sync_hearing(updated)
        if on and result.get("live"):
            return (
                "Dinleme açık. Uyandırma sözü gerekmez — konuşman ajana gider."
            )
        if on:
            return "Kulak açılamadı" + (
                f": {result['note']}" if result.get("note") else ".")
        return "Dinleme kapalı. Mikrofon bırakıldı."

    def voice_power(self, on: bool) -> str:
        """HUD: turn the voice on or off (writes the setting too)."""
        from . import settings as settings_mod

        agent = getattr(self, "agent", None)
        server = getattr(self, "server", None)
        cfg = agent.config if agent is not None else getattr(server, "config", None)
        if cfg is None:
            return "Ses ayarı yok."
        updated = settings_mod.apply(cfg, {"voice": {"enabled": bool(on)}})
        if server is not None:
            server.config = updated
        if agent is not None:
            agent.reconfigure(updated)
        hub = getattr(self, "hub", None)
        if hub is not None:
            hub.emit({"type": "voice", "enabled": bool(on)})
        if on:
            return "Ses açık."
        return "Ses kapalı."

    def _swap_model(self) -> None:
        """Applies the pending model change.

        The old client is not closed here: closing is a coroutine and this
        call comes from the HTTP thread. It is left to the loop.
        """
        wanted = self._wanted_model
        pending = self._wanted_config
        self._wanted_model = None
        self._wanted_config = None
        agent = self.agent
        if wanted is None or agent is None:
            return

        from .backends import build_client

        try:
            fresh = build_client(wanted)
        except Exception as exc:
            self.hub.emit({"type": "notice", "text": f"Model değiştirilemedi: {exc}"})
            return

        old = agent.client
        agent.client = fresh
        # If the new model is LM Studio, load it with the right window and
        # pull the REAL loaded window into the setting — same as at boot: on
        # a live model change too (user switching from settings) the window
        # must match reality, otherwise compaction triggers late and the
        # prompt overflows. On a non-LM-Studio provider it silently does
        # nothing.
        if pending is not None:
            try:
                _prepare_model(pending)
            except Exception:
                pass
        # Client and system prompt are refreshed together: if the new model
        # has a narrow window it must switch to lean, the tool schemas must
        # shorten. If the two fall apart, one is set for the new model and
        # the other for the old.
        if pending is not None:
            agent.reconfigure(pending)
        # The new model's price must be asked again: showing spend with the
        # old tag would print a wrong figure. The next usage event fetches
        # a fresh tag in the background.
        self._price = None
        self._price_checked = False
        note = self._swap_note or f"Model değişti: {wanted.name}."
        self._swap_note = ""
        self.hub.emit({"type": "notice", "text": note})
        # Shared client cache (parallel lanes): don't close the old client if
        # ANOTHER lane is still using it — pulling the connection out from
        # under it drops the running turn. It is dropped from the cache only
        # when nobody uses it either.
        in_use = any(s.agent is not None and s.agent.client is old
                     for s in self.lanes.values())
        if not in_use:
            for key, cached in list(getattr(self, "_clients", {}).items()):
                if cached is old:
                    self._clients.pop(key, None)
            self.loop.call_soon_threadsafe(
                lambda: self.loop.create_task(_retire(old)))
        # The new client into the cache: a new lane opened on the same model
        # should share it.
        if hasattr(self, "_clients"):
            self._clients[(wanted.name, str(wanted.base_url or ""))] = fresh

    # -- the memory's night -----------------------------------------------

    def start_sleep(self, config: Config, mind: Any, *, factory: Any = None) -> Any:
        """Starts the sleep daemon (recall/daemon.py) once the mind is open.

        The daemon owns its thread; the bridge only hands it what it cannot
        know on its own: the live hub, the mind's caches, the distillation
        model, and the two privacy facts the distil gate needs — is the
        configured model local, and did the user consent to memory text
        reaching a hosted endpoint (the same consent the recognition loop
        uses). Those are callables so a settings change reaches a night
        that starts later, without a restart.

        `factory` lets a test stand a fake daemon in the real place.
        """
        global _POWER_LISTENER
        from .recall import daemon as sleep_daemon

        self._sleep_config = config
        make = factory or sleep_daemon.SleepDaemon
        self.sleeper = make(
            mind.store, config.sessions_dir, config.state_dir,
            hub=self.hub, caches=mind.clear_caches, model=self._night_model,
            local_model=lambda: (
                (c := self._sleep_settings()) is not None
                and lmstudio.is_local_url(c.model.base_url)),
            cloud_ok=lambda: bool(
                recognition.status(config.state_dir).get("learn_cloud_ok")),
            enabled=lambda: (
                (c := self._sleep_settings()) is None or bool(c.sleep.uyku_acik)),
        )
        self.sleeper.start()
        # Suspend/resume from the frame shell's WndProc (WM_POWERBROADCAST).
        _POWER_LISTENER = self._power_event
        return self.sleeper

    def stop_sleep(self, timeout: float = 5.0) -> bool:
        """Stops the daemon; a running night is asked to stop and joined."""
        global _POWER_LISTENER
        daemon = getattr(self, "sleeper", None)
        if daemon is None:
            return True
        if _POWER_LISTENER == getattr(self, "_power_event", None):
            _POWER_LISTENER = None
        try:
            return bool(daemon.stop(timeout))
        finally:
            self.sleeper = None

    def sleep_status(self) -> dict[str, Any] | None:
        """What GET /api/uyku should prefer; None when no daemon runs."""
        daemon = getattr(self, "sleeper", None)
        if daemon is None:
            return None
        try:
            return daemon.status()
        except Exception as err:
            return {"durum": "okunamadı", "hata": str(err)}

    def _sleep_settings(self) -> Config | None:
        cfg = getattr(self, "_sleep_config", None)
        if cfg is None:
            cfg = getattr(getattr(self, "agent", None), "config", None)
        return cfg

    def _power_event(self, kind: str) -> None:
        daemon = getattr(self, "sleeper", None)
        if daemon is None:
            return
        if kind == "suspend":
            daemon.os_suspended()
        elif kind == "resume":
            daemon.os_resumed()

    def _night_model(self, prompt: str) -> str:
        """One tool-less, history-less model call for the night's distillation.

        Called from the daemon thread; the request runs on the agent's loop,
        which is idle while a night runs (the user is away), and an async
        request would not block it anyway. The daemon calls this only after
        `distil.gate` allowed it: a local model, or explicit cloud consent.
        """
        from .context import Prepared

        agent = self.agent
        client = getattr(agent, "client", None)
        if client is None:
            raise RuntimeError("model yok")
        prepared = Prepared(
            system=[{"type": "text", "text": NIGHT_SYSTEM}],
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            betas=[], context_management=None)
        future = asyncio.run_coroutine_threadsafe(
            asyncio.wait_for(
                client.turn(prepared, [], cancel=asyncio.Event()),
                timeout=NIGHT_MODEL_TIMEOUT_S),
            self.loop)
        result = future.result(timeout=NIGHT_MODEL_TIMEOUT_S + 5)
        if result.error or result.interrupted:
            raise RuntimeError(result.error or "kesildi")
        return "\n".join(
            str(block.get("text", ""))
            for block in result.content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()

    def waking(self, stage: str, *, ready: bool = False) -> None:
        """Announces which step of boot we are at.

        The window must not sit empty while the model loads; it should say
        what is being waited for and come alive once ready.
        """
        self.stage = stage
        self.ready = ready
        self.hub.emit({"type": "waking", "stage": stage, "ready": ready})

    @property
    def busy(self) -> bool:
        return self._busy

    def snapshot(self) -> dict[str, Any]:
        agent = self.agent
        # If a turn ran in this process the live counter is right; if not
        # (resumed session, fresh boot) the truth is in the session log.
        live_total = int((getattr(agent, "_last_usage", None) or {}).get("prompt_total") or 0)
        past = ({"prompt_total": live_total, "output": 0, "cagri": 0, "tahmin": False}
                if live_total else _past_usage(agent) if agent
                else {"prompt_total": 0, "output": 0, "cagri": 0, "tahmin": False})
        # The cost chip's session total is seeded from the same source: new
        # turns are added ON TOP of it (see _usage_yay).
        self._seed_session_usage(past)
        return {
            "busy": self._busy,
            "ready": self.ready,
            "stage": self.stage,
            "session": agent.session.id if agent else "",
            "model": agent.config.model.name if agent else "",
            # Provider NAME for the UI: `model.provider` is the backend TYPE
            # ("openai") and writing "openai" while connected to OpenRouter
            # misleads. The real provider identity from the settings is
            # found by looking at the address.
            "provider": _provider_name(agent),
            # For the strip under the composer: thinking depth and context
            # window. Without the window the usage percentage can't be
            # computed.
            "effort": agent.config.model.effort if agent else "",
            "context_window": int(agent.config.model.context_window) if agent else 0,
            # The last turn's prompt total: on a page refresh — and after the
            # app is closed and reopened — the context gauge should start
            # where it left off, not from zero. If no turn ran in this process
            # (resumed session) the value comes from the session log; see
            # _past_usage.
            "prompt_total": past["prompt_total"],
            # Is the figure a rough estimate rather than the provider's real
            # count? The UI says so in the title — no made-up precision.
            "tahmin": past["tahmin"],
            # Item-by-item breakdown of the context box (system / tools /
            # soul / skills / MCP / conversation). The fixed items show even
            # without a total.
            "kirilim": context_breakdown(agent, past["prompt_total"]),
            # Cost chip: on a page refresh the spend gauge should start where
            # it left off, not from zero. None if the price is unknown — the
            # chip falls back to token counts.
            "fiyat": self._price,
            "kullanim": {
                "tur": dict(self._turn_usage),
                "oturum": dict(self._session_usage),
            },
            # Spend cap set for this session (USD) — None = unlimited. The
            # cost chip must not forget the cap on a page refresh.
            "butce": self._budget_usd,
            "mode": agent.permissions.mode if agent else "",
            # Active goals: on a page refresh the goal panel has missed the
            # event stream; the panel is seeded with this list and carries
            # on from where it left off.
            "goals": _active_goals(agent),
            # Helper channels: the orchestra panel is seeded from here for
            # the same reason — no ghost "running" card left behind, orphans
            # shown as "left unfinished".
            "channels": _live_channels(agent),
            "voice": bool(agent and agent.config.voice.enabled),
            # The voice character is applied in the browser: the synthesiser
            # produces a plain human voice, the layer rides on top of it.
            "character": float(agent.config.voice.character) if agent else 0.0,
            "listen": bool(agent and agent.config.listen.enabled),
            "wake": bool(agent and agent.config.listen.wake.strip()),
            "open": bool(agent and agent.config.listen.open),
            "ear": bool(_ear_alive(self.ear)),
            "snoozed": bool(self.ear is not None
                            and getattr(self.ear, "snoozed", False)),
            "camera": bool(agent and agent.config.camera.enabled),
            "tools": len(agent.registry) if agent else 0,
            # Version of the running copy: the top-bar brand tooltip feeds
            # from here. In the field, "which version is open?" must not go
            # unanswered.
            "surum": environment.version(),
            "kurulu": environment.is_installed(),
            # Can the agent actually authenticate (a key exists, or a local
            # server)? The UI shows the first-run guidance based on this —
            # even if the model comes as "oto", without a key no work is done.
            "can_run": _can_run(agent),
            # Working directory: the chat screen should show whether we are
            # in the workshop or in an attached folder. Empty project = the
            # workshop.
            "workspace": str(agent.config.workspace) if agent else "",
            "project": (str(getattr(agent.config.sandbox, "project", "") or "")
                        if agent else ""),
            # Tasks whose time passed while the program was closed (boot question).
            "missed_tasks": self._missed_tasks_payload(),
        }

    def missed_pending(self) -> bool:
        """Is a user decision pending for the missed tasks?"""
        return bool(self._missed_ids)

    def _missed_tasks_payload(self) -> list[dict[str, Any]]:
        if not self._missed_ids:
            return []
        book = getattr(self.agent, "schedule", None) if self.agent else None
        if book is None:
            return []
        from . import schedule as scheduling

        out: list[dict[str, Any]] = []
        for tid in self._missed_ids:
            task = book.get(tid)
            if task is not None:
                row = scheduling.payload([task])
                if row:
                    out.append(row[0])
        return out

    def resolve_missed(self, action: str) -> dict[str, Any]:
        """Missed tasks: run them now or skip them this once."""
        if not self._missed_ids:
            return {"ok": True, "resolved": 0}

        book = getattr(self.agent, "schedule", None) if self.agent else None
        if book is None:
            return {"ok": False, "error": "zamanlayıcı yok"}

        ids = list(self._missed_ids)
        act = str(action or "").strip().lower()
        count = 0

        if act in ("run", "missed_run", "yap"):
            claimed = book.due(only=ids)
            fire = self._missed_fire
            for task in claimed:
                try:
                    if fire is not None:
                        fire(task)
                    else:
                        self.run_scheduled(task)
                    count += 1
                except Exception as exc:
                    book.note_run(task.id, f"başlatılamadı: {type(exc).__name__}")
        elif act in ("skip", "missed_skip", "atla"):
            for tid in ids:
                if book.skip_occurrence(tid):
                    count += 1
        else:
            return {"ok": False, "error": "run veya skip gerekli"}

        self._missed_ids = []
        self.hub.emit({"type": "missed_resolved", "action": act, "count": count})
        if act.startswith("skip") or act == "atla":
            self.hub.emit({"type": "jobs_refresh"})
        return {"ok": True, "action": act, "count": count}

    # -- cost chip ------------------------------------------------------

    def _reset_usage(self) -> None:
        """When the active chat changes, the counters should belong to it.

        Bridge keeps a single counter; on switching from chat A to B the old
        total either stuck to B, or because of `_session_seeded` B's past
        was never loaded — the chip showed zero on every reopen (live
        complaint). Reset; the seed comes from the right log on the next
        snapshot / explicit seed call.
        """
        self._turn_usage = {"girdi": 0, "cikti": 0, "cagri": 0}
        self._session_usage = {"girdi": 0, "cikti": 0, "cagri": 0}
        self._session_seeded = False

    def _seed_session_usage(self, past: dict[str, Any]) -> None:
        """Seeds the resumed session's spend into the chip once.

        The same wound as the context bar: in a reopened conversation the
        chip also started from zero. The seed is placed ONLY once and only
        while no turn has run for this chat yet — otherwise every snapshot
        (page refresh) would inflate the total. `girdi` is the sum over all
        turns; the same language as the live `_usage_yay` accounting.
        """
        if self._session_seeded or self._session_usage["cagri"]:
            return
        if not past.get("cagri"):
            return
        self._session_seeded = True
        # Old logs may carry only prompt_total — backward compat.
        input_total = int(past.get("girdi") or past.get("prompt_total") or 0)
        self._session_usage = {
            "girdi": input_total,
            "cikti": int(past.get("output") or 0),
            "cagri": int(past.get("cagri") or 0),
        }

    def _usage_yay(self, report: dict[str, int]) -> None:
        """Accumulates the end-of-turn usage report and streams it to the hub.

        Event contract (the cost chip in the UI depends on it):
            {type: "usage", ...cache_report fields,
             tur:    {girdi, cikti, cagri},    total of this user turn
             oturum: {girdi, cikti, cagri},    total of the session
             fiyat:  {girdi, cikti} | None}    USD/token; None if unknown

        `girdi` is the whole prompt (prompt_total: cache included) — the
        estimate is deliberately conservative, the cache discount is not
        counted. If the price is None the chip shows token counts.
        """
        for counter in (self._turn_usage, self._session_usage):
            counter["girdi"] += int(report.get("prompt_total") or 0)
            counter["cikti"] += int(report.get("output") or 0)
            counter["cagri"] += 1
        self._fetch_price()
        breakdown = context_breakdown(self.agent, int(report.get("prompt_total") or 0))
        self.hub.emit({
            "type": "usage", **report,
            "tur": dict(self._turn_usage),
            "oturum": dict(self._session_usage),
            "fiyat": self._price,
            "kirilim": breakdown,
        })

    # -- budget brake ---------------------------------------------------

    def budget(self, usd: Any = None) -> dict[str, Any]:
        """Reads or sets this session's spend cap (HTTP thread).

        If `usd` is None/empty the cap is LIFTED (unlimited). Zero or
        negative also count as unlimited: there is no such request as
        "spend 0 dollars", there is a user who brushed the keyboard.

        The cap is not written to the settings file — deliberately. This is
        not a preference, it is a seat belt put on this session; tomorrow's
        conversation must not silently stop under yesterday's cap.
        """
        if usd is None or usd == "":
            self._budget_usd = None
        else:
            try:
                value = float(usd)
            except (TypeError, ValueError):
                return {"ok": False, "error": "Sayı bekleniyordu.",
                        "butce": self._budget_usd}
            self._budget_usd = value if value > 0 else None
        # The cap changed: the "reached" line may be printed once more.
        self._budget_reported = False
        return {"ok": True, "butce": self._budget_usd,
                "harcanan": self._spent()}

    def _spent(self) -> float | None:
        """Estimated spend of this session (USD). None if the price is unknown."""
        if not self._price:
            return None
        o = self._session_usage
        return o["girdi"] * self._price["girdi"] + o["cikti"] * self._price["cikti"]

    def _budget_brake(self) -> str:
        """Has the cap been reached? If so, the single line to print in the chat.

        The agent loop asks BEFORE every model call (see
        loop.AgentIO.budget_brake). No network here, no file: only the
        counter we have and the price tag we have.

        If the price is unknown (local server, model outside the catalogue)
        the brake DOES NOT RUN. Stopping the user's work over a made-up
        dollar figure would be worse than never setting the cap.
        """
        cap = self._budget_usd
        if not cap or self._budget_reported:
            return ""
        spent = self._spent()
        if spent is None or spent < cap:
            return ""
        self._budget_reported = True
        return (f"Bütçe sınırına ulaşıldı (${cap:.2f}) — "
                "devam etmek için sınırı yükselt.")

    # -- running tasks --------------------------------------------------

    def _child_in_background(self, cid: str) -> bool:
        """Was this channel running in the background (for the finished-channel notice)."""
        children = getattr(self.agent, "_children", None) or {}
        handle = children.get(cid)
        return bool(handle is not None and handle.background)

    def tasks(self) -> dict[str, Any]:
        """Single list of every running (and recently finished) job (HTTP thread).

        Two sources merge, because to the user both are "something running
        in the back":

          * `Agent._children` — background helpers (`kind="yardımcı"`) and
            background shell jobs (`kind="iş"`, the `shell` tool's
            `arka_plan: true` path).
          * `apps._PROCS` — detached processes: the `shell` tool's
            `background: true` path and apps launched from the panel.

        The duration is LIVE: the row carries the `basladi` stamp and the
        UI does the counting — no need to ask the server once a second.
        """
        from . import apps as catalog

        rows: list[dict[str, Any]] = []

        children = getattr(self.agent, "_children", None) or {}
        from .tools.shell import short_job_summary
        for h in children.values():
            summary = ""
            if h.state != "kosuyor":
                summary = short_job_summary(h.outcome or "", title=h.title)[:400]
            rows.append({
                "id": "c:" + h.id,
                "ad": h.title,
                "tur": h.kind,
                "durum": h.state,
                # For an orphan the real start is unknown (inherited from the
                # previous session): 0 is sent, the UI draws no duration.
                "basladi": 0.0 if h.state == "yetim" else h.started_ts,
                "bitti": h.ended_ts,
                "ozet": summary,
                "model": h.model,
                "oturum": h.session_id,
                "arka_plan": bool(h.background),
                "pid": None,
                "durdurulabilir": h.state == "kosuyor",
                "surdurulebilir": (
                    h.state in ("yetim", "bitti", "hata")
                    and bool(h.session_id)
                    and h.kind != "iş"
                ),
                "son_arac": h.last_tool if h.state == "kosuyor" else "",
                "son_hedef": h.last_goal if h.state == "kosuyor" else "",
                "wait": h.wait if h.state == "kosuyor" else None,
                "deliverable": h.deliverable,
                "usage": dict(h.usage) if h.usage else None,
            })

        for pid, info in list(catalog._PROCS.items()):
            proc = info.get("proc")
            if proc is None:
                continue
            finished = proc.poll() is not None
            command = str(info.get("path") or "")
            own = catalog.is_dornick_process(command) or catalog.is_dornick_process(
                str(info.get("run") or ""))
            rows.append({
                "id": "p:" + str(pid),
                "ad": "Dornick (kendisi)" if own else str(info.get("name") or command or pid),
                "tur": "süreç",
                "durum": "bitti" if finished else "kosuyor",
                "basladi": float(info.get("started") or 0.0),
                "bitti": 0.0,
                "ozet": "",
                "model": "",
                "oturum": "",
                "arka_plan": True,
                "pid": pid,
                "komut": command,
                # Killing its own copy from the panel would close the app.
                "durdurulabilir": (not finished) and not own,
            })

        # Running ones first, then the most recently finished: what the user
        # is looking for is almost always "what is running right now".
        rows.sort(key=lambda r: (r["durum"] != "kosuyor",
                                 -(r["bitti"] or r["basladi"])))
        return {"gorevler": rows,
                "kosan": sum(1 for r in rows if r["durum"] == "kosuyor")}

    def task_report(self, gid: str) -> dict[str, Any]:
        """Full helper/job text — to the Viewer when Orchestra/Tasks is clicked.

        Instead of long bulletins pasted into the chat: a short line in the
        panel, an artifact-like page on click.
        """
        gid = str(gid or "").strip()
        cid = gid[2:] if gid.startswith("c:") else gid
        if not cid or not re.match(r"^[A-Za-z0-9_-]+$", cid):
            return {"ok": False, "error": "Geçersiz görev kimliği."}
        children = getattr(self.agent, "_children", None) or {}
        handle = children.get(cid)
        if handle is None:
            return {"ok": False, "error": "Görev bulunamadı."}
        text = str(handle.outcome or "").strip()
        if not text and handle.state == "kosuyor":
            # While running, the current status instead of an empty report —
            # Viewer / Open report.
            parts: list[str] = ["Görev hâlâ çalışıyor."]
            if handle.wait:
                w = handle.wait
                line = "Model bekleniyor"
                if w.get("deneme") and w.get("toplam"):
                    line += f" ({w['deneme']}/{w['toplam']})"
                if w.get("saniye"):
                    line += f" · {w['saniye']}s"
                parts.append(line)
            elif handle.last_tool:
                line = f"Şu an: {handle.last_tool}"
                if handle.last_goal:
                    line += f" — {handle.last_goal}"
                parts.append(line)
            else:
                parts.append("Araç bekleniyor…")
            text = "\n".join(parts)
        else:
            from .tools.shell import human_job_report
            text = human_job_report(text, title=handle.title)
        deliverable = getattr(handle, "deliverable", None)
        if not deliverable and getattr(handle, "schedule_id", ""):
            try:
                from .loop import _infer_deliverable
                book = scheduling.Schedule(self.agent.config.state_dir)
                task = book.get(handle.schedule_id)
                if task is not None:
                    deliverable = _infer_deliverable(task.prompt or "", text)
                    if deliverable:
                        handle.deliverable = deliverable
            except Exception:
                pass
        return {
            "ok": True,
            "id": "c:" + handle.id,
            "title": handle.title,
            "state": handle.state,
            "metin": text or "(çıktı yok)",
            "deliverable": deliverable,
        }

    def stop_task(self, gid: str) -> dict[str, Any]:
        """Stops a single task. `gid` is the id from a tasks() row.

        Sends cancel to the live helper; also clears the scheduled 'koşuyor'
        ghost (so it doesn't stay stuck in the UI when there is no child /
        it has finished).
        """
        from . import apps as catalog

        gid = str(gid or "").strip()
        if gid.startswith("c:"):
            cid = gid[2:]
            if not cid or not re.match(r"^[A-Za-z0-9_-]+$", cid):
                return {"ok": False, "error": "Geçersiz görev kimliği."}
            children = getattr(self.agent, "_children", None) or {}
            handle = children.get(cid)

            if handle is not None and handle.state == "kosuyor":
                def _stop(h=handle) -> None:
                    h.cancel.set()
                    agent = h.agent
                    if agent is not None:
                        try:
                            agent.cancel.set()
                        except Exception:
                            pass
                self.loop.call_soon_threadsafe(_stop)

            # Ghost / live: the scheduled row must not stay at 'koşuyor'.
            cleared = self._clear_schedule_running(cid, handle)
            try:
                self.hub.emit({"type": "jobs_refresh"})
            except Exception:
                pass
            if handle is None:
                return {"ok": True, "id": gid, "cleared": True,
                        "note": "Kayıt temizlendi (canlı yardımcı yoktu)."}
            if handle.state != "kosuyor":
                return {"ok": True, "id": gid, "cleared": cleared,
                        "note": "Görev zaten bitmişti; durum güncellendi."}
            return {"ok": True, "id": gid, "cleared": cleared}

        if gid.startswith("p:"):
            try:
                pid = int(gid[2:])
            except ValueError:
                return {"ok": False, "error": "Geçersiz süreç kimliği."}
            return catalog.stop(pid)
        return {"ok": False, "error": "Geçersiz görev kimliği."}

    def _clear_schedule_running(
        self, child_id: str, handle: Any = None,
    ) -> bool:
        """Mark tasks with last_status=koşuyor + a matching last_child_id as 'kesildi'."""
        agent = self.agent
        if agent is None:
            return False
        book = getattr(agent, "schedule", None)
        if book is None:
            return False
        cleared = False
        state_dir = getattr(getattr(agent, "config", None), "state_dir", None)
        for task in book.all():
            if task.last_child_id != child_id:
                continue
            if task.last_status != "koşuyor":
                continue
            try:
                book.note_run(task.id, "kesildi")
                cleared = True
            except Exception:
                continue
            if state_dir is None:
                continue
            try:
                from . import task_runs
                from .loop import _report_with_meter, _run_meter

                if handle is not None and not getattr(handle, "ended_ts", 0):
                    try:
                        import time as _time
                        handle.ended_ts = _time.time()
                    except Exception:
                        pass
                meter = (
                    _run_meter(handle, agent.config)
                    if handle is not None else {}
                )
                for run in task_runs.list_runs(state_dir, task.id, limit=8):
                    if run.status != "koşuyor":
                        continue
                    if run.child_id and run.child_id != child_id:
                        continue
                    body = "Kullanıcı durdurdu."
                    if handle is not None and getattr(handle, "outcome", None):
                        body = str(handle.outcome)[:500] or body
                    report = body
                    if handle is not None:
                        report = _report_with_meter(
                            handle, agent.config, body)
                    elif meter.get("line"):
                        report = body + "\n\n---\n" + meter["line"]
                    task_runs.finish_run(
                        state_dir, task.id, run.id,
                        status="hata",
                        report=report,
                        child_id=child_id,
                        model=meter.get("model") or (
                            getattr(handle, "model", "") if handle else ""),
                        usage=meter.get("usage"),
                        cost_usd=meter.get("cost_usd"),
                        tools=meter.get("tools"),
                        duration_s=meter.get("duration_s"),
                        last_tool=meter.get("last_tool"),
                    )
            except Exception:
                pass
        return cleared

    def resume_task(self, gid: str, message: str = "") -> dict[str, Any]:
        """Resumes an orphaned / finished helper from its session on disk.

        HTTP wrapper of the `task_say` / `_child_say` path — `create_task`
        is needed on the agent loop.
        """
        gid = str(gid or "").strip()
        cid = gid[2:] if gid.startswith("c:") else gid
        if not cid or not re.match(r"^[A-Za-z0-9_-]+$", cid):
            return {"ok": False, "error": "Geçersiz görev kimliği."}

        agent = self.agent
        if agent is None:
            return {"ok": False, "error": "Ajan henüz hazır değil."}
        children = getattr(agent, "_children", None) or {}
        handle = children.get(cid)
        if handle is None:
            return {"ok": False, "error": "Görev bulunamadı."}
        if handle.kind == "iş":
            return {"ok": False, "error": "Arka plan süreci sürdürülemez."}
        if handle.state == "kosuyor":
            return {"ok": False, "error": "Bu görev zaten koşuyor."}
        if not handle.session_id:
            return {"ok": False, "error": "Oturum yok; sürdürülemiyor."}

        msg = (message or "").strip() or "Kaldığın yerden devam et."
        box: dict[str, Any] = {}
        done = threading.Event()

        def _start() -> None:
            try:
                ok, text = agent._child_say(cid, msg)
                box.update({"ok": bool(ok), "id": "c:" + cid,
                            "text": text or ""})
                if not ok:
                    box["error"] = text or "Sürdürülemedi."
            except Exception as exc:
                box.update({"ok": False,
                            "error": f"{type(exc).__name__}: {exc}"})
            finally:
                done.set()

        self.loop.call_soon_threadsafe(_start)
        if not done.wait(timeout=15):
            return {"ok": False, "error": "Sürdürme zaman aşımı."}
        return box if box else {"ok": False, "error": "Sürdürülemedi."}

    def gorev_iptal(self, gid: str) -> dict[str, Any]:
        """Drops an orphaned/finished helper from the ledger AND from the boot scan.

        Persistence: a `subagent_end` closure is written into the child's own
        log — `scan_orphans` never resurrects a log that has seen a closure.
        ("There is Continue but no Cancel" — live request, 31.08.)
        """
        gid = str(gid or "").strip()
        cid = gid[2:] if gid.startswith("c:") else gid
        if not cid or not re.match(r"^[A-Za-z0-9_-]+$", cid):
            return {"ok": False, "error": "Geçersiz görev kimliği."}
        agent = self.agent
        if agent is None:
            return {"ok": False, "error": "Ajan henüz hazır değil."}
        children = getattr(agent, "_children", None) or {}
        handle = children.get(cid)
        if handle is None:
            return {"ok": False, "error": "Görev bulunamadı."}
        if handle.state == "kosuyor":
            return {"ok": False, "error": "Koşan görev iptal edilmez — önce durdur."}
        sid = str(getattr(handle, "session_id", "") or "")
        if sid and re.match(r"^[A-Za-z0-9_-]+$", sid):
            try:
                path = Path(agent.config.sessions_dir) / f"{sid}.jsonl"
                line = json.dumps({
                    "kind": "meta", "role": None, "content": "subagent_end",
                    "meta": {"session": sid, "title": handle.title,
                             "summary": "kullanıcı iptal etti"},
                }, ensure_ascii=False)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass
        children.pop(cid, None)
        self.hub.emit({"type": "channels", "channels": _live_channels(agent)})
        return {"ok": True}

    def _fetch_price(self) -> None:
        """Fetches the selected model's price once, in the background.

        The network request is NOT in the turn's path: when the thread ends
        the `fiyat` event is published and the chip turns from token counts
        to dollars. A model missing from the catalogue is also looked up once
        and left alone — going out to the network every turn is not on.
        The flag resets when the model changes.
        """
        if self._price_checked:
            return
        agent = self.agent
        if agent is None:
            return
        self._price_checked = True
        model = agent.config.model
        state_dir = agent.config.state_dir

        def _run() -> None:
            try:
                label = fiyatlama.etiket(model, state_dir, ag=True)
            except Exception:
                return
            if label is not None:
                self._price = label
                self.hub.emit({"type": "fiyat", "fiyat": label})

        threading.Thread(target=_run, daemon=True).start()

    # -- asyncio thread ------------------------------------------------

    def io(self, lane: Any = None) -> AgentIO:
        """The agent's event surface. When `lane` is given, stream events go
        to the live broadcast ONLY while that lane is active — a background
        lane's text/tools do not mix into the active chat (the invisible
        pillar of parallel sessions). Approval requests are not gated: the
        background lane's permission must be asked too, otherwise the turn
        waits forever.
        """
        def publish(ev: dict[str, Any]) -> None:
            if lane is None or lane.sid == self._active_sid:
                # The event is stamped WITH THE SESSION ID: the gate (active
                # lane comparison) is instantaneous and can race during a
                # switch — a chunk waiting in the queue, or leaking right at
                # the moment of the switch, was flowing onto the screen of the
                # newly opened chat while carrying no id (live wound, 01.09:
                # "it even gets mixed up with the previous chat"). The UI now
                # DOES NOT DRAW an event that carries no id.
                sid = lane.sid if lane is not None else self._active_sid or ""
                if sid:
                    ev.setdefault("sid", sid)
                self.hub.emit(ev)

        return AgentIO(
            on_text=lambda chunk: publish({"type": "assistant_delta", "text": chunk}),
            on_thinking=lambda chunk: publish({"type": "thinking_delta", "text": chunk}),
            on_notice=lambda text: publish({"type": "notice", "text": text}),
            # Model outage: a structural wait event. The UI renders it as a
            # SINGLE live line in the work strip — no wall of errors printed
            # into the chat (see app.js "bekleme").
            on_wait=lambda payload: publish({"type": "bekleme", **payload}),
            # The cost chip shows the active chat: a background lane's spend
            # does not mix into the chip (it already sits in its own session
            # log).
            on_usage=(self._usage_yay if lane is None else
                      (lambda report: self._usage_yay(report)
                       if lane.sid == self._active_sid else None)),
            # Session title: the sidebar list should update without a page
            # refresh. Published for a background lane too — the title is the
            # chat's identity, not tied to the active screen.
            on_session_title=lambda sid, name: self.hub.emit(
                {"type": "session_title", "id": sid, "title": name}),
            # Budget brake: the loop asks before every model call. Since the
            # price and the counters are here, the decision is here too.
            budget_brake=self._budget_brake,
            # Orchestra channels: sub-agents should look live (conductor mode).
            on_child_start=lambda title, model, cid, bg=False: publish(
                {"type": "child_start", "title": title, "model": model, "id": cid,
                 "bg": bool(bg)}),
            on_child_tool=lambda title, tool, phase, target="": publish(
                {"type": "child_tool", "title": title, "tool": tool,
                 "phase": phase, "hedef": target or ""}),
            # `bg`: was this finished channel running in the background. The
            # tasks panel drops the "finished" notice into the chat ONLY for
            # background jobs — a synchronous helper's result is already
            # inside the answer.
            on_child_end=self._child_end,
            on_child_wait=lambda payload: publish(
                {"type": "child_wait", **(payload or {})}),
            approve=self._approve,
        )

    def _child_end(
        self,
        title: str,
        ok: bool,
        turns: int,
        tools: int,
        cid: str = "",
        summary: str = "",
    ) -> None:
        """A sub-channel finished: Orchestra + (if background) a Windows tray balloon."""
        bg = self._child_in_background(cid)
        deliverable = None
        children = getattr(self.agent, "_children", None) or {}
        handle = children.get(cid) if cid else None
        if handle is not None:
            deliverable = getattr(handle, "deliverable", None)
        usage = dict(getattr(handle, "usage", None) or {}) if handle else {}
        self.hub.emit({
            "type": "child_end", "title": title, "ok": ok, "turns": turns,
            "tools": tools, "id": cid, "ozet": summary, "bg": bg,
            "deliverable": deliverable,
            "model": getattr(handle, "model", "") if handle else "",
            "usage": usage or None,
        })
        # Let the user know even with the window closed — only background /
        # scheduled / automation jobs (a synchronous helper is already in
        # the chat).
        if not bg:
            return
        t = self.tray
        if t is None:
            return
        try:
            t.note(tray_module.task_notification_text(title, ok=bool(ok)))
        except Exception:
            pass

    async def _approve(
        self,
        spec: ToolSpec,
        args: dict[str, Any],
        channel: dict[str, Any] | None = None,
    ) -> bool:
        """Sends the permission request to the UI and waits for the answer.

        If the window closes before answering, this future never resolves;
        the pending ones are cancelled on the shutdown path (see
        cancel_pending).
        """
        request_id = uuid4().hex[:12]
        future: asyncio.Future[bool] = self.loop.create_future()
        self._pending[request_id] = Pending(future=future, spec=spec, args=dict(args))

        payload = {
            "type": "approval_request",
            "id": request_id,
            "tool": spec.name,
            "args": args,
            "mutates": spec.mutates,
        }
        # If the requester is a helper, its id/title go along too: the user
        # should see "[yardımcı: başlık]" in the dialog and know whom they
        # are granting permission to.
        if channel:
            payload["channel"] = channel
        self.hub.emit(payload)
        try:
            granted = await future
        except asyncio.CancelledError:
            return False
        finally:
            self._pending.pop(request_id, None)
            self.hub.emit({"type": "approval_done", "id": request_id})
        return granted

    def cancel_pending(self) -> None:
        for pending in tuple(self._pending.values()):
            if not pending.future.done():
                pending.future.cancel()
        self._pending.clear()

    async def pump(self) -> None:
        """Pump of the first lane (set up at boot; new lanes get their own
        pumps inside `_build_lane`)."""
        while True:
            lane = self._lane()
            if lane is None:
                # The agent is not built yet: wait on the boot queue.
                item = await self._first_queue.get()
                if self.agent is None:
                    continue
                lane = self._lane()
                if lane is None:
                    continue
                await self._pump_item(lane, item)
                continue
            await self._pump_lane(lane)
            return

    async def _pump_lane(self, lane: Lane) -> None:
        """A lane's pump: streams its own queue into its own agent.

        One pump per lane = seriality per lane; BETWEEN lanes, full
        parallelism. When the user switches to a new chat the old lane
        carries on with its turn here.
        """
        while True:
            item = await lane.queue.get()
            if lane.agent is None:
                continue
            await self._pump_item(lane, item)

    async def _pump_item(self, lane: Lane, item: Any) -> None:
        if item is _CHILD_DONE:
            await self._resume(lane)
        elif item is _PARK_RESUME:
            await self._resume_parked(lane)
        else:
            text, image = item
            await self._handle(text, image, lane=lane)

    async def _resume_parked(self, lane: Lane | None = None) -> None:
        """Resumes a parked (unfinished) run from where it stopped.

        The counterpart of the marker dropped into the queue when a park
        record is found at boot. `resume_after_interrupt` closes the
        unanswered tool_uses and drives the loop again; if the model is
        still unreachable the retry/park chain inside the same run is
        already in play.
        """
        lane = lane or self._lane()
        agent = lane.agent if lane else None
        if agent is None:
            return
        self._lane_status(lane, True)
        try:
            await agent.resume_after_interrupt()
        except Exception as exc:  # resuming must not bring the app down
            self._lane_emit(lane, {"type": "notice",
                                      "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._lane_status(lane, False)
            if self._wanted_model is not None and lane.sid == self._active_sid:
                self._swap_model()
            self._lane_emit(lane, {"type": "turn_end"})

    async def _resume(self, lane: Lane | None = None) -> None:
        """A helper finished and the agent is idle: the turn that weighs the result.

        If nothing is left to report (the result was already delivered at the
        start of the running turn) the model is not called at all — it is
        passed over silently.
        """
        lane = lane or self._lane()
        agent = lane.agent if lane else None
        if agent is None or not agent.has_unreported_children():
            return
        self._lane_status(lane, True)
        try:
            await agent.resume_for_children()
        except Exception as exc:  # the resume turn must not bring the app down
            self._lane_emit(lane, {"type": "notice",
                                      "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._lane_status(lane, False)
            if self._wanted_model is not None and lane.sid == self._active_sid:
                self._swap_model()
            self._lane_emit(lane, {"type": "turn_end"})

    def _lane_emit(self, lane: Lane, ev: dict[str, Any]) -> None:
        """Hands a lane event to the live stream ONLY while the lane is active.

        A background lane's text is already written to its own session log;
        had it also leaked into the live broadcast, two chats would mix on
        screen. When the user returns to the lane the transcript is loaded
        from the log — nothing is lost.
        """
        if lane.sid == self._active_sid:
            ev.setdefault("sid", lane.sid)   # see io().publish: the switch race
            self.hub.emit(ev)

    async def _handle(self, text: str, image: str = "", *,
                    lane: Lane | None = None) -> None:
        """Processes a single message on its lane (default: the active lane).

        Kept apart from pump deliberately: tests can run a turn without
        touching the queue and the endless loop.
        """
        lane = lane or self._lane()
        if lane is None or lane.agent is None:
            return
        self._lane_status(lane, True)
        agent = lane.agent
        # New user message = new turn: the chip's "this turn" total starts
        # from zero. The session total is untouched; resume turns (_resume,
        # park) count as continuation of the same work and don't reset. The
        # counter is reset only on the active lane — the chip shows the
        # active chat.
        if lane.sid == self._active_sid:
            self._turn_usage = {"girdi": 0, "cikti": 0, "cagri": 0}
        # New message = new attempt: if the cap is still exceeded the brake
        # should speak once more. Otherwise the user types and nothing happens.
        self._budget_reported = False
        try:
            # First run: while no provider is usable the model is NEVER
            # called — instead of a message that stays unanswered or ends
            # with an unintelligible API error, an assistant message that
            # points the way lands in the chat. If the user types again it
            # is repeated; but a message is answered once.
            if settings.unconfigured(agent.config.model):
                agent.session.add_user_text(text)
                agent.session.add_assistant(
                    [{"type": "text", "text": settings.SETUP_REDIRECT}]
                )
                self._lane_emit(lane,
                                  {"type": "setup_hint",
                                   "text": settings.SETUP_REDIRECT})
                return
            # The title does not wait for the END of the run: on the left, a
            # "crumb of the first words" hung for the whole of a long run.
            # The first user words are signal enough — but `run` may not have
            # written the message to the log yet; we pass the text directly
            # (race, live). The small call runs parallel to the main flow;
            # every error of it is swallowed. The call at the end of the run
            # is the fallback (if there is still no name, a more accurate
            # title from the answer).
            title_fn = getattr(agent, "_session_title", None)
            if title_fn is not None:
                title_task = asyncio.ensure_future(title_fn(text))
                title_task.add_done_callback(lambda t: t.exception())  # silent
            await agent.run(text, image)
        except Exception as exc:  # if the agent blows up on a request the app must not die
            self._lane_emit(lane, {"type": "notice",
                                   "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._lane_status(lane, False)
            # Answered: the conversation is open. Everything said during this
            # time counts as said to it, no need to repeat its name — you
            # don't start every sentence with the name of the person across
            # from you either.
            if self.ear is not None and lane.sid == self._active_sid:
                self.ear.engage()
            # If the model was changed during the turn, switch now.
            if self._wanted_model is not None and lane.sid == self._active_sid:
                self._swap_model()
            self._lane_emit(lane, {"type": "turn_end"})
            # A background lane finished: let the user know while they are in
            # another chat.
            if lane.sid != self._active_sid:
                title = ""
                try:
                    meta = (lane.agent.mind.session_meta() or {}).get(lane.sid) or {}
                    title = str(meta.get("ad") or "")
                except Exception:
                    pass
                self.hub.emit({"type": "notice",
                               "text": (f"Arka plandaki sohbet bitti: {title}"
                                        if title else
                                        "Arka plandaki sohbet cevabını bitirdi — "
                                        "kenar çubuğundan dönebilirsin.")})


@dataclass(slots=True)
class Runtime:
    bridge: Bridge
    server: MindServer
    agent: Agent
    session: Session
    client: Any
    url: str
    schedule: Any = None
    ticker: Any = None
    greeter: Any = None
    eyes: Any = None
    lens: Any = None
    ear: Any = None


def _allow_media() -> None:
    """Tells WebView2 to skip the media permission prompt.

    `--use-fake-ui-for-media-stream` is Chromium's "don't show the permission
    prompt, accept" flag. In our own window this is the right behaviour: the
    user has already turned the microphone/camera on in the settings and
    WebView2 has no surface on which it could ask.

    If the environment already has a value it is appended to: we don't want
    to wipe flags the user provided.
    """
    name = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"
    flag = "--use-fake-ui-for-media-stream"
    current = os.environ.get(name, "")
    if flag not in current:
        os.environ[name] = f"{current} {flag}".strip()


def _hearing_wanted(config: Config) -> bool:
    """Should the ear open: listening on, device and recognition present, wake word or open."""
    from . import listen as recogniser

    return bool(
        config.listen.enabled
        and hearing.available()
        and recogniser.available()
        and (config.listen.wake.strip() or config.listen.open)
    )


def close_senses(config: Config) -> Config:
    """Camera, microphone and spoken replies are off at boot.

    Turning them on from the HUD writes the setting; the next boot comes
    up off again.
    """
    return replace(
        config,
        voice=replace(config.voice, enabled=False),
        listen=replace(config.listen, enabled=False, open=False),
        camera=replace(config.camera, enabled=False),
    )


def _ear_alive(ear: Any) -> bool:
    """Is the ear thread still spinning? After stop() it gets rebuilt."""
    if ear is None:
        return False
    stop = getattr(ear, "_stop", None)
    if stop is not None and stop.is_set():
        return False
    thread = getattr(ear, "_thread", None)
    return thread is not None and thread.is_alive()


def _open_ear(config: Config, bridge: "Bridge", hub: Hub) -> Any:
    """Opens the always-listening ear.

    When the wake word is heard the window comes back and what follows the
    word goes straight to the agent. Nothing without the word is recorded,
    shown, or sent to the model.
    """
    from . import listen as recogniser

    # The domain vocabulary fills itself: the user's device and skill names
    # enter the recogniser's bias prompt. Spelling "Modbus" correctly in the
    # sentence "Modbus cihazını oku" depends on this — the recogniser turns
    # a proper name it never heard into the nearest real word.
    from dataclasses import replace as _replace

    words = [config.listen.vocab, "Modbus", "SCADA", "PLC", "register"]
    try:
        from . import devices as declared
        from . import skills as authored

        found_devices, _ = declared.load(config.open_sandbox().root)
        words += [d.name for d in found_devices]
        learned, _ = authored.discover(config.open_sandbox().root)
        words += [item.name for item in learned]
    except Exception:
        pass
    spoken = _replace(config.listen, vocab=", ".join(w for w in words if w))

    listener = recogniser.Listener(spoken)

    # The model is **not loaded** here. Loading can mean downloading —
    # `medium` is 1.5 GB — and holding boot for more than thirty seconds
    # meant the window never opened. Loading happens on the ear's own
    # thread, at the first utterance or in the background warm-up.
    #
    # The scout object is also built here but not loaded either; `Ear`
    # decides whether it is needed once the device is known.
    scout = recogniser.Listener(_replace(spoken, size=SCOUT_SIZE))

    def heard(said: hearing.Heard) -> None:
        hub.emit({"type": "notice", "text": f"Duydum: {said.text}"})
        bridge.wake()

        # "dornick ile kes" / energy barge: interrupted while dornick was
        # speaking — first silence the speech (the UI stops TTS), then the
        # command enters the normal flow (queue). The energy threshold may
        # already have cut it via `on_hush`; a second hush is harmless.
        if getattr(said, "barge", False):
            hub.emit({"type": "hush"})

        # The running turn is NOT CANCELLED — it queues (same behaviour as
        # text). The old version cut the turn on every heard phrase; the
        # user said "when I say one more thing while it does something, it
        # cancels the old one". The right thing is to think in parallel and
        # queue: the new phrase enters the queue, processed when the turn
        # ends. Cancel is asked for explicitly (stop button / spoken "dur");
        # the default is no longer cancel.
        text = (said.command or "").strip()
        if _is_stop(text):
            # Explicit cancel: a word like "dur", "yeter", "kes" stops the running one.
            if bridge.busy:
                bridge.interrupt()
            return

        if _is_close(text):
            # Close: the window closes and we go quiet. Silence is cheap under
            # uncertainty, a wrong answer is expensive — the user says
            # "dornick" if they want it.
            if ear is not None:
                ear.disengage()
            hub.emit({"type": "notice",
                      "text": "Sohbet kapandı — adıyla yeniden açılır."})
            return

        if _is_ack(text):
            # Thanks / "tamamdır" / "şimdi bakayım": does not go to the model,
            # no "rica ederim" loop opens. No "bakıyorum" clip either.
            return

        # If nothing is left of the phrase, only the name was called. Going
        # quiet there is the same as not hearing: the screen said "Duydum"
        # and nothing happened.
        if text:
            # Acknowledgement clip: the UI plays a short sound ("bakıyorum")
            # before the model produces its first word. Not played on a name
            # call (CALLED_ASK) — saying "bakıyorum" before "efendim" would be
            # odd.
            hub.emit({"type": "ack"})
        bridge.submit(text or CALLED_ASK)

    ear = hearing.Ear(
        listener,
        heard,
        scout=scout,
        wake=config.listen.wake,
        # With open listening on, the wake word is never searched for.
        open=config.listen.open,
        # The level goes to the UI: whether it hears should be visible.
        level=lambda loud: hub.emit({"type": "level", "value": round(loud, 4)}),
    )
    ear.on_hush = lambda: hub.emit({"type": "hush"})
    if not ear.start():
        return None
    def _hearing_snooze(off: bool) -> None:
        hub.emit({"type": "hearing", "snoozed": bool(off)})
        prefs.patch(config.state_dir, hearing_snoozed=bool(off))
    ear.on_snooze = _hearing_snooze
    how = "serbest dinleme" if config.listen.open else f"'{config.listen.wake}' ile uyanır"
    print(f"[dornick] kulak açık — {how}", flush=True)
    return ear


def _unfinished_work(sessions_dir: Any) -> str | None:
    """Is there crash residue: an unanswered tool_use left in the last session?

    The trace of a run left unfinished without a park record. Used only to
    inform (automatic resume depends on the park record); therefore best
    effort — silently None on an unreadable/corrupt log.
    """
    import json as _json
    from pathlib import Path as _Path

    try:
        files = sorted(_Path(sessions_dir).glob("*.jsonl"))
        if not files:
            return None
        requested: list[str] = []
        answered: set[str] = set()
        for line in files[-1].read_text(encoding="utf-8").splitlines():
            try:
                ev = _json.loads(line)
            except ValueError:
                continue
            meta = ev.get("meta") or {}
            # A helper (sub-agent) session: not a subject for the main list.
            if ev.get("content") == "subagent_start" and meta.get("parent"):
                return None
            if ev.get("kind") != "message":
                continue
            content = ev.get("content")
            if not isinstance(content, list):
                continue
            if ev.get("role") == "assistant":
                requested = [str(b.get("id")) for b in content
                             if isinstance(b, dict) and b.get("type") == "tool_use"]
            elif ev.get("role") == "user":
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        answered.add(str(b.get("tool_use_id")))
        if any(r not in answered for r in requested):
            return files[-1].stem
        return None
    except Exception:
        return None


def _prepare_model(config: Config) -> None:
    """Gets the model loaded with the window from the settings (LM Studio only).

    When LM Studio loads on its own it uses 4096 tokens — even if the model
    supports 262144. The system prompt plus the tool schemas already exceed
    that and the server silently drops the head of the prompt: the model
    forgets who it is.

    Surplus copies are removed in the same place: when a second request hits
    a busy model, LM Studio loads a second copy and memory doubles.

    If `local_optimize` is on (and the address is localhost): other models
    are unloaded, the context is lowered by VRAM/model size. If off, nothing
    is touched.

    Fails silently: without LM Studio the endpoints don't exist either, and
    that is normal.
    """
    if config.model.provider != "openai":
        return

    url = config.model.base_url
    name = config.model.name
    context = config.model.context_window

    optimize = bool(config.model.local_optimize) and lmstudio.is_local_url(url)
    if optimize:
        for gone in lmstudio.unload_others(url, name):
            print(f"[dornick] yerel opt: başka model boşaltıldı: {gone}", flush=True)
        # Measure VRAM after unloading — the previous model's room comes back.
        model = lmstudio.find(url, name)
        free_mb = None
        try:
            from . import gpu as gpu_module
            free_mb = gpu_module.primary_free_mb()
        except Exception:
            free_mb = None
        if model is not None:
            # If the model is already loaded the weights occupy VRAM —
            # subtracting the size again would be double counting and cut
            # the context needlessly.
            size_for_fit = 0 if model.instances else model.size_bytes
            fitted = lmstudio.suggest_context(
                context,
                max_context=model.max_context,
                size_bytes=size_for_fit,
                params_b=model.params_b,
                free_vram_mb=free_mb,
            )
            if fitted != context:
                print(
                    f"[dornick] yerel opt: bağlam {context} → {fitted}"
                    + (f" (VRAM boş {free_mb} MB)" if free_mb is not None else ""),
                    flush=True,
                )
                context = fitted

    for gone in lmstudio.drop_duplicates(url, name):
        print(f"[dornick] fazla kopya kaldırıldı: {gone}", flush=True)

    # We give the keep_loaded TTL if set, otherwise a generous default
    # (30 min): with its own default LM Studio unloaded the model quickly and
    # failed the next request with "Model unloaded". This way the model stays
    # loaded while the conversation continues.
    ttl = config.model.keep_loaded or 1800
    result = lmstudio.ensure_loaded(url, name, context, ttl=ttl)
    if result.get("state") == "loaded":
        print(f"[dornick] model {result['context']} token pencereyle yüklendi "
              f"({result.get('seconds', 0):.1f} sn)")
    elif result.get("state") == "capped":
        print(f"[dornick] pencere modelin sınırına çekildi: {result['context']}", flush=True)

    # Reflect the REAL loaded window into the SETTING. LM Studio may have
    # shrunk the requested window because of the model's limit or its own
    # configuration (e.g. 4096). If the setting stays above reality,
    # compaction doesn't trigger before overflow, the prompt exceeds the
    # model's limit and LM Studio threw a "model unloaded / context" error —
    # the user said "it stops when the context fills". Pulled down to
    # reality, the conversation is summarised and continues before filling
    # up, no new conversation needed.
    actual = result.get("context")
    if isinstance(actual, int) and actual > 0 and actual != config.model.context_window:
        from dataclasses import replace as _replace
        config.model = _replace(config.model, context_window=actual)
        print(f"[dornick] bağlam penceresi gerçeğe göre ayarlandı: {actual}", flush=True)


async def _boot(config: Config, port: int, resume: bool) -> Runtime:
    """Brings the application up.

    The order is deliberate: the server opens **first**, the heavy work
    comes after. That way the window shows at once and, while the model
    loads, the user looks at the wake-up sequence rather than a blank
    screen. The input line stays closed until the model is ready — writing
    to an agent that isn't ready means going unanswered.
    """
    config.ensure_dirs()
    # Camera, microphone and spoken replies start off. The user turns them
    # on from the HUD; the next session comes up off again — LED/ear/speaker
    # don't wake by themselves. If "on" stayed on disk, another settings save
    # would relight the sense mid-session.
    config = close_senses(config)
    if (config.state_dir / settings.CONFIG_FILE).exists():
        try:
            config = settings.apply(config, {
                "voice": {"enabled": False},
                "listen": {"enabled": False, "open": False},
                "camera": {"enabled": False},
            })
        except Exception:
            pass

    # Keys entered on the settings page are loaded into the environment: the
    # backends already read from there, no need to open a second path.
    settings.export_keys(config.state_dir)

    # Park record: in the previous run the model may have become unreachable
    # and the app closed while the work was on hold. If the record exists
    # THAT session is opened and below (once pump is set up) the run is
    # resumed automatically from where it stopped.
    park_session = None
    if parked := read_park(config.state_dir):
        p = config.sessions_dir / f"{parked.get('session', '')}.jsonl"
        if p.is_file():
            park_session = Session.resume(p)
        else:
            clear_park(config.state_dir)

    # No park record, but if an unanswered tool_use was left in the last
    # session (crash residue) the user is only informed — under uncertainty
    # we stay on the side of asking, no resuming on our own.
    unfinished = None if (park_session or resume) else _unfinished_work(config.sessions_dir)

    # Orphaned helpers: sub-agents that died together with the app while
    # running in the background last session (subagent_start present,
    # subagent_end missing). A separate wound from the park/unfinished work
    # — there the main run, here the children are half done. Found once and
    # a marker is dropped into the child log at once so a second boot does
    # not report the same orphan again; the news is given below (once the
    # agent is built) to both the user and the model.
    orphans = scan_orphans(config.sessions_dir)
    if orphans:
        mark_orphan(config.sessions_dir, orphans)

    session = park_session or (
        Session.latest(config.sessions_dir) if resume else None
    ) or Session.create(config.sessions_dir)
    hub = Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    mind = open_mind(config.mind_dir, config.sessions_dir, session.id)
    if not park_session and not resume:
        inherit_last_model(mind, session.id, config.sessions_dir)
    pin = str(((mind.session_meta() or {}).get(session.id) or {}).get("model") or "").strip()
    if pin and pin != config.model.name:
        from dataclasses import replace as _replace
        config = _replace(config, model=_replace(config.model, name=pin))
    book = scheduling.Schedule(config.state_dir)

    # The hub is shared: what the bridge publishes (text stream, approval
    # request) and what comes from the log (user message, tool events) must
    # land in the same stream.
    server = MindServer(
        mind,
        session.log,
        port=port,
        controller=bridge,
        hub=hub,
        config=config,
        schedule=book,
    )
    # The bridge needs the server to switch sessions (rebinding the event
    # stream); the reference is given here.
    bridge.server = server
    url = server.start()

    # -- the heavy part: the window is already open, the steps are visible --

    bridge.waking("zihin açılıyor")
    # On a narrow-window model the sub-agent tool is not registered at all:
    # its schema alone is 130 tokens, and in a 4096 window that room belongs
    # to the conversation.
    registry = build_registry(mind, subagents=not prompt.is_lean(config))

    bridge.waking("yetenekler yükleniyor")
    # Skills the agent wrote itself: loaded from the workshop on every boot.
    # A broken file does not block the others — a single typo must not
    # strip the agent of all its skills.
    # The standard skills shipped with the package are copied into the
    # workshop on first boot; afterwards they are the user's: they edit,
    # delete, we don't re-add.
    skills.seed(config.open_sandbox().root, config.state_dir)
    # Boot: no human present — only skills in the approved manifest load.
    # A random .py dropped into the workshop does not run by itself.
    learned, broken = skills.discover(config.open_sandbox().root, config.state_dir)
    added, _updated = skills.register(registry, learned)
    if added:
        print(f"[dornick] yetenekler yüklendi: {', '.join(added)}", flush=True)
    for problem in broken:
        print(f"[dornick] yetenek yüklenemedi: {problem.splitlines()[0]}", flush=True)

    # MCP connectors connect in the background: `npx` may download a package
    # the first time and boot must not wait for it. Once connected, the
    # tools land in the live registry — the next turn sees them.
    pool = linking.Pool()
    server._httpd.connectors = pool  # type: ignore[attr-defined]

    def _connect_mcp() -> None:
        found, problems = linking.load(config.state_dir)
        for problem in problems:
            print(f"[dornick] bağlayıcı: {problem}", flush=True)
        if not found:
            return
        pool.connect(found, config.state_dir)
        fresh, _gone = linking.register(registry, pool)
        if fresh:
            print(f"[dornick] MCP araçları: {', '.join(fresh)}", flush=True)
        for state in pool.status():
            if not state["ok"] and state["error"]:
                hub.emit({"type": "notice",
                          "text": f"Bağlayıcı {state['name']}: {state['error']}"})

    threading.Thread(target=_connect_mcp, daemon=True, name="dornick-mcp").start()

    bridge.waking(f"model yükleniyor · {config.model.name}")
    # Loading takes seconds and is a blocking call; it is moved to a separate
    # thread so it does not lock the loop.
    await asyncio.to_thread(_prepare_model, config)

    # If the model is not configured (first run: no key, no local server) the
    # window still opens: the settings page works independently of the agent
    # and that is exactly where the fix belongs. Before, when this blew up
    # the user never saw the window — someone fresh out of the setup wizard
    # cannot be left with "an invisible error".
    try:
        client = build_client(config.model)
    except Exception as exc:
        client = None
        agent = None
        print(f"[dornick] model istemcisi kurulamadı: {exc}", flush=True)
    else:
        agent = Agent(
            config=config,
            session=session,
            registry=registry,
            client=client,
            io=bridge.io(),
            permissions=PermissionEngine.from_config(config.permissions),
            policy=ContextPolicy(config.context),
            schedule=book,
            mind=mind,
        )
        # The bridge should hear when a background helper finishes: if the
        # agent is idle a resume turn that weighs the result opens. (The
        # lane-specific binding is set up in the `bridge.agent = agent`
        # assignment; the backward-compat line here was removed so it does
        # not overwrite it.)
        # On a model outage, apply the pending settings/model change before
        # every retry: when a broken address/key is fixed the parked run can
        # continue with the new client (normally the change waits for the
        # end of the turn; a parked turn never ends).
        agent.on_retry_wait = bridge._swap_model
    bridge.agent = agent

    # The memory's night (roadmap 3.10): the watchman thread that samples
    # pressure, learns when the user is around, and runs the night while
    # they are away. It needs the mind (open) and the agent (for the
    # distillation model); stopped in _teardown.
    try:
        bridge.start_sleep(config, mind)
    except Exception as exc:
        print(f"[dornick] uyku bekçisi başlatılamadı: {exc}", flush=True)

    # Always-on listening lives on the Python side: it can't live in the
    # browser because when the window is hidden Chromium throttles background
    # timers to once a minute and listening dies. Here it runs even while
    # sitting in the tray. A settings save uses the same gate
    # (`sync_hearing`) — otherwise only push-to-talk remains.
    if _hearing_wanted(config):
        bridge.waking("kulak açılıyor")
    bridge.sync_hearing(config)

    # The recognition model is warmed in the background: having the first
    # voice request wait for the download locked the whole UI.
    server_module.warm_ear(server._httpd, config)

    # Recognise me: the watchman of the personal fine-tuning loop. Scheduling
    # is in the product — no schtasks; the watchman looks every fifteen
    # minutes and, if its turn has come, starts the loop at low priority.
    # If the feature is off it never stirs.
    recognition.start_watcher(config.state_dir, hub)

    # The local camera's always-open buffer. Frames stay in memory and do not
    # go to the model by themselves; the `look` tool takes them on request.
    lens = None
    if config.camera.enabled and watching.available():
        bridge.waking("göz açılıyor")
        lens = watching.Lens()
        if lens.start():
            if agent is not None:
                agent.lens = lens
            # The UI should know too: to tell whether the camera organ on
            # the scene is really open it looks at this, not the setting.
            server._httpd.lens = lens  # type: ignore[attr-defined]
            print("[dornick] kamera tamponu açık", flush=True)
            from . import sight
            sight.ensure_warmup()
            lens.on_snooze = lambda off: prefs.patch(
                config.state_dir, sight_snoozed=bool(off)
            )
        else:
            lens = None

    bridge.lens = lens
    if agent is not None:
        agent.camera_power = bridge.camera_power

    if agent is None:
        bridge.waking(
            "model yapılandırılmamış — ayarlardan bir model seç ve anahtarını "
            "gir, sonra uygulamayı yeniden başlat"
        )
    else:
        bridge.waking("hazır", ready=True)

    loop = asyncio.get_running_loop()
    loop.create_task(bridge.pump())

    # Orphaned helpers: a single batched notice + ledger entry. With the
    # ledger entry the panel can draw the "left unfinished" row (snapshot
    # channels) and, if the user says "resume", the model can revive the
    # session on disk with `task_say` — adopt_orphans drops the harness note.
    if orphans:
        if agent is not None:
            agent.adopt_orphans(orphans)
        names = ", ".join(
            (y.get("title") or y.get("session") or "?") for y in orphans)
        hub.emit({"type": "notice", "text": (
            f"Geçen oturumdan {len(orphans)} yardımcı yarım kaldı: {names}. "
            "Uygulama kapanınca arka plan yardımcıları durur; istersen "
            "kaldıkları yerden sürdürebilirim.")})
        # A page loaded during boot may have pulled the snapshot before the
        # agent was built (channels empty at that moment); this event seeds
        # the panel with the real list — no need to refresh the window.
        hub.emit({"type": "channels", "channels": _live_channels(agent)})

    # Long job left unfinished: with a park record it resumes automatically;
    # with only crash residue (an unrecorded half turn) the user is informed
    # and the decision is theirs.
    if park_session is not None and agent is not None:
        hub.emit({"type": "notice",
                  "text": "Yarım kalmış uzun iş bulundu — kaldığı yerden sürdürülüyor."})
        loop.create_task(bridge.queue.put(_PARK_RESUME))
    elif unfinished:
        hub.emit({"type": "notice",
                  "text": f"Yarım kalmış bir iş görünüyor (oturum {unfinished}). "
                          "Geçmiş'ten açıp 'devam et' diyebilirsin."})

    # The scheduler runs on the agent's loop: a fired task lands not in the
    # chat queue but on a background helper — the report is in the Orchestra.
    def fire(task: Any) -> None:
        hub.emit({"type": "notice", "text": f"Zamanlanmış görev: {task.title}"})
        result = bridge.run_scheduled(task)
        if not result.get("ok"):
            book.note_run(task.id, f"başlatılamadı: {result.get('error') or '?'}")
            hub.emit({"type": "notice",
                      "text": f"Görev başlatılamadı: {task.title}"})

    bridge._missed_fire = fire
    missed = book.overdue()
    if missed:
        bridge._missed_ids = [t.id for t in missed]
        hub.emit({
            "type": "missed_tasks",
            "tasks": scheduling.payload(missed),
        })

    ticker = loop.create_task(scheduling.run_forever(
        book, fire, paused=bridge.missed_pending))

    # Arrival: when someone enters the room after a long silence the agent
    # looks once. Like a small child — puts itself on hold when nobody is
    # around, and looks at who came when something moves.
    async def greet() -> None:
        while True:
            await asyncio.sleep(2.0)
            cfg = getattr(bridge.agent, "config", None) if bridge.agent else None
            if cfg is None or not bool(getattr(cfg.camera, "enabled", False)):
                continue
            box = getattr(bridge.agent, "lens", None) if bridge.agent else None
            if box is not None and not bridge.busy and box.arrival():
                bridge.submit(GREET_ASK)

    greeter = loop.create_task(greet())

    # Cameras are watched in the background. The model does not look at
    # every frame: motion is measured locally and a question is asked only
    # when something changed. With a GPU the frame is analysed locally and
    # TEXT goes to the chat model; the image never leaves the machine.
    # Without a GPU, the old snapshot mode (frame + cloud_ok).
    def seen(sighting: watching.Sighting) -> None:
        bridge._on_camera_motion(sighting)

    eyes = watching.Watcher(
        watching.load(config.state_dir) if config.camera.enabled else [], seen)
    bridge.eyes = eyes
    # "Stop watching me" covers the network cameras too; calling its name
    # reopens them all. Ear, eye and watcher are a single "senses" whole.
    if bridge.agent is not None:
        bridge.agent.watcher = eyes
    if bridge.ear is not None:
        # "dornick" reopens the ear and the network cameras. The built-in
        # camera is opened with the HUD/chat switch — calling the name does
        # not relight the LED. With the HUD off, unsnooze does not start the
        # watcher; start() is tied to the HUD.
        bridge.ear.companions = [s for s in (eyes,) if s is not None]
    if config.camera.enabled and eyes.start():
        print(f"[dornick] {len(watching.load(config.state_dir))} kamera izleniyor", flush=True)
    eyes.on_snooze = lambda off: prefs.patch(
        config.state_dir, sight_snoozed=bool(off)
    )

    held = prefs.load(config.state_dir)
    if held.get("hearing_snoozed") and bridge.ear is not None:
        bridge.ear.snooze(0)
    if held.get("sight_snoozed"):
        if lens is not None:
            lens.snooze(0)
        eyes.snooze(0)

    return Runtime(
        bridge=bridge,
        server=server,
        agent=agent,
        session=session,
        client=client,
        url=url,
        schedule=book,
        ticker=ticker,
        greeter=greeter,
        eyes=eyes,
        lens=lens,
        ear=bridge.ear,
    )


def _handoff_open(port: int, path: str) -> bool:
    """Hand the path to a running dornick instance. True on success (don't open a new one)."""
    import json
    import urllib.error
    import urllib.request

    payload = json.dumps({"path": path}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{int(port)}/api/open",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        return bool(body.get("ok"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return False


def _kill_ghosts() -> None:
    """Closes the OTHER dornick desktop instances on this machine.

    The criterion is the command line: python + ("dornick" and "--app").
    Our own process and unrelated pythons are left alone. Silent, best
    effort — if the process list can't be read, boot continues anyway.
    """
    if sys.platform != "win32":
        return
    try:
        import json
        import subprocess

        from . import environment

        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or "
             "Name='pythonw.exe' or Name='dornick.exe'\" | "
             "Select-Object ProcessId,CommandLine | "
             "ConvertTo-Json"],
            capture_output=True, text=True, timeout=10, encoding="utf-8",
            errors="replace", **environment.quiet_flags(),
        ).stdout
        rows = json.loads(out or "[]")
        if isinstance(rows, dict):
            rows = [rows]
        me = os.getpid()
        from . import winicon
        skip = winicon.skip_pids() | {me}
        for row in rows:
            pid = row.get("ProcessId")
            cmd = (row.get("CommandLine") or "").lower()
            if not pid or pid in skip:
                continue
            if "dornick" in cmd and ("--app" in cmd or "desktop" in cmd):
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True,
                               **environment.quiet_flags())
                print(f"[dornick] eski örnek kapatıldı (PID {pid})", flush=True)
    except Exception:
        pass


def run(config: Config, *, port: int = 8765, resume: bool = False,
        open_path: str | None = None) -> int:
    """Opens the window and blocks until it closes."""
    # Taskbar identity: unless this is set, Windows shows the window in
    # python.exe's group and the icon stayed the PYTHON logo. Grouped under
    # its own identity, the window's own icon (the dornick logo) shows.
    # Task Manager / WebView2 child processes look at the PE icon instead —
    # hence a python(w) relaunches itself as the stamped dornick.exe.
    if sys.platform == "win32":
        try:
            import ctypes

            from .winicon import AUMID, ensure_toast_identity
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)
            ensure_toast_identity()
        except Exception:
            pass

    # 'Open with Dornick': if an instance is running, hand it over — so the
    # ghost hunt does not kill it.
    pending_open = str(open_path or "").strip() or None
    if pending_open and _handoff_open(port, pending_open):
        return 0

    # GHOST HUNT: old dornick instances left hidden in the tray seized the
    # port and the window targeting and left the new instance deaf — the
    # more the user said "I closed and reopened it" the more ghosts
    # multiplied, and no fix ever reached the screen (the real root of the
    # three-day wound). When a new instance opens it closes the old ones one
    # by one: every boot clean, a single instance.
    # BEFORE the relaunch so the stamped dornick.exe can be written: if a
    # running dornick.exe stays locked, the copy isn't stamped and the snake
    # stays in Task Manager.
    _kill_ghosts()
    if sys.platform == "win32":
        try:
            from . import winicon
            winicon.relaunch_as_host()
        except Exception:
            pass
    # WebView2 opens its own permission prompt for microphone and camera; in
    # an embedded window that prompt never shows and the request is silently
    # denied — the UI only said "microphone could not be opened".
    #
    # The flag is given only if the user turned it on in the settings:
    # granting media permission on our own while it is off would open an
    # authority nobody asked for.
    if config.listen.enabled or config.camera.enabled:
        _allow_media()

    try:
        import webview
    except ImportError:
        from . import environment
        raise SystemExit(
            "Bu kurulum eksik görünüyor (pencere paketi yok). Kurulum "
            "sihirbazını yeniden çalıştırmak eksiği onarır."
            if environment.is_installed() else
            "Masaüstü penceresi için pywebview gerekli: pip install 'dornick[app]'"
        ) from None

    loop = asyncio.new_event_loop()
    ready = threading.Event()
    box: dict[str, Any] = {}

    def spin() -> None:
        asyncio.set_event_loop(loop)

        async def setup() -> None:
            try:
                box["runtime"] = await _boot(config, port, resume)
            except Exception as exc:
                box["error"] = exc
            finally:
                ready.set()

        loop.create_task(setup())
        loop.run_forever()

    thread = threading.Thread(target=spin, daemon=True, name="dornick-agent")
    thread.start()

    # Boot may coincide with a model download (1.5 GB if the recognition
    # model is `medium`). A short timeout blew up as a `KeyError` in that
    # case: what the user saw was a stack trace, and the reason was written
    # nowhere.
    if not ready.wait(timeout=BOOT_TIMEOUT_S):
        loop.call_soon_threadsafe(loop.stop)
        raise SystemExit(
            f"Açılış {BOOT_TIMEOUT_S:.0f} saniyede bitmedi. Muhtemelen bir model "
            "indiriliyor; terminaldeki ilerlemeye bak ve indirme bitince yeniden "
            "başlat."
        )

    if error := box.get("error"):
        loop.call_soon_threadsafe(loop.stop)
        raise SystemExit(f"Başlatılamadı: {error}")

    runtime: Runtime = box["runtime"]

    # --open on a cold start: new chat + folder once boot has finished.
    if pending_open:
        try:
            runtime.bridge.open_path(pending_open)
        except Exception:
            pass

    # Native frame: the operating system's title bar and edges — so MOVING,
    # maximise/minimise, edge RESIZE and Windows snap all work like a normal
    # application. (The frameless form gave a holographic "one piece" feel
    # but gave none of these; the user asked for a normal window.) resizable
    # defaults to True.
    # frameless: pywebview sets FormBorderStyle.None — the client area
    # ALREADY fills the window completely (desktop leaking at the edges is
    # structurally impossible). The native behaviours are added separately:
    # box styles (snap/animation), HTCAPTION dragging (Aero snap included),
    # WM_SYSCOMMAND maximise/minimise and SC_SIZE edge resizing — all the
    # operating system's own loops.
    geo = prefs.window_args(prefs.load(config.state_dir))
    # DON'T pass maximized to create_window: frameless, the position drifts
    # to something like (101,101); shell + MaximizedBounds and then
    # _force_maximize seat it.
    want_max = bool(geo.get("maximized"))
    window = webview.create_window(
        WINDOW_TITLE,
        runtime.url,
        width=geo.get("width", 1360),
        height=geo.get("height", 880),
        x=geo.get("x"),
        y=geo.get("y"),
        maximized=False,
        min_size=(900, 600),
        background_color=WINDOW_BACKGROUND,
        frameless=True,
        # Default True: the WHOLE client area becomes a drag region — the
        # user grabbed the brain / the chat and moved the window. Moving is
        # only from the top strip (chrome.js → HTCAPTION); snap comes the
        # same way.
        easy_drag=False,
        # pywebview's default turns text SELECTION off: answers produced in
        # the packaged build couldn't be copied ("copy paste doesn't work" —
        # live, 31.08; invisible in the browser preview because there is no
        # pywebview there).
        text_select=True,
    )
    # Closing hides the window, it does not destroy it: the agent has work
    # that must keep going in the background (scheduled tasks, sub-agents
    # watching the cameras, the microphone waiting for the wake word). With
    # no tray, closing really closes — otherwise the program could never be
    # shut down.
    #
    # Exit guard: when Exit is chosen from the tray while the agent is in
    # the middle of a job, a native Yes/No dialog asks — the running job must
    # not die silently. On Yes, a clean shutdown: the park/orphan mechanisms
    # drop the trace and boot already offers to resume.
    # X and Exit land on the same `closing` event; `Shutdown` holds the
    # distinction. `hide` binds to `_hide_to_tray` defined below (balloon
    # included), but since that is born on later lines it is bound lazily
    # from here.
    shutdown = tray_module.Shutdown(
        hide=lambda: _hide_to_tray(),
        destroy=lambda: window.destroy(),
    )

    def _show_from_tray() -> None:
        """From the tray / wake: bring the window; jobs that finished in the
        background should show in the Tasks panel (refresh the list)."""
        window.show()
        _ensure_native_chrome()
        # The box may have broken while hidden (offset maximise); look once visible.
        threading.Timer(0.4, _heal_geometry).start()
        runtime.bridge.hub.emit({"type": "jobs_refresh"})

    def _open_jobs_from_tray() -> None:
        window.show()
        _ensure_native_chrome()
        threading.Timer(0.4, _heal_geometry).start()
        runtime.bridge.hub.emit({"type": "open_jobs"})

    tray = tray_module.Tray(
        show=_show_from_tray,
        hide=lambda: window.hide(),
        quit=shutdown.quit,
        busy=lambda: runtime.bridge.busy,
        confirm=_confirm_quit,
        jobs=_open_jobs_from_tray,
        # A confirmed Exit ends with the process under every condition: if
        # the GUI layer is locked, a hard landing after 12 s (live wound, 01.09).
        guard=tray_module.install_exit_guard,
    )
    live = tray.start()
    runtime.bridge.tray = tray

    # Single strip: the OS title bar is stripped (strip_caption, in
    # _titlebar_boot) and the window controls move to the app's own strip.
    # The native behaviours (edge resize, snap, taskbar) stay in the window
    # styles.
    window.expose(_wake(window))
    window.expose(paint_titlebar)

    global _MAIN_WINDOW
    _MAIN_WINDOW = window

    def minimize() -> None:
        _win_do("minimize")

    def maximize() -> bool:
        # Refresh the maximise bound for the current monitor (taskbar); the
        # return value is the new state — the UI draws its icon from it.
        _update_max_bounds()
        return _win_do("maximize")

    def drag() -> bool:
        # Return value: maximised after the drag? The strip icon follows it.
        _win_do("drag")
        _update_max_bounds()
        return _is_zoomed()

    def resize(edge: str) -> None:
        _win_do("resize:" + str(edge))

    def is_zoomed() -> bool:
        return _is_zoomed()

    def pano_oku() -> str:
        """Reads plain text from the Windows clipboard (ctypes; no extra dependency).

        The context menu's "Paste" feeds from here: pywebview disables
        WebView2's default menu in production and the browser clipboard-read
        permission cannot be asked inside WebView2 — the Python side can
        always read (native round, 31.08)."""
        import ctypes
        CF_UNICODETEXT = 13
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        # 64-bit trap: unless restype is declared the handle is TRUNCATED to
        # 32 bits and GlobalLock blows up on a garbage pointer (in the native
        # round the menu "Paste" silently returned empty, 31.08).
        u32.GetClipboardData.restype = ctypes.c_void_p
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        if not u32.OpenClipboard(0):
            return ""
        try:
            handle = u32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = k32.GlobalLock(handle)
            try:
                return ctypes.wstring_at(ptr) if ptr else ""
            finally:
                k32.GlobalUnlock(handle)
        except Exception:
            return ""
        finally:
            u32.CloseClipboard()

    def pano_yaz(text: str = "") -> bool:
        """Writes plain text to the Windows clipboard (for Copy/Cut)."""
        import ctypes
        CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
        data = str(text or "")
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        k32.GlobalAlloc.restype = ctypes.c_void_p
        k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        u32.SetClipboardData.restype = ctypes.c_void_p
        u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        if not u32.OpenClipboard(0):
            return False
        try:
            u32.EmptyClipboard()
            size = (len(data) + 1) * ctypes.sizeof(ctypes.c_wchar)
            hglob = k32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not hglob:
                return False
            ptr = k32.GlobalLock(hglob)
            ctypes.memmove(ptr, ctypes.create_unicode_buffer(data), size)
            k32.GlobalUnlock(hglob)
            u32.SetClipboardData(CF_UNICODETEXT, hglob)
            return True
        except Exception:
            return False
        finally:
            u32.CloseClipboard()

    def open_camera_window(cam: str = "") -> str:
        """Opens camera watching in a separate OS window; brings it forward if it exists."""
        global _CAM_WINDOW
        import threading
        import webview

        q = ("?cam=" + str(cam)) if cam else ""
        url = str(runtime.url).rstrip("/") + "/watch.html" + q
        existing = _CAM_WINDOW
        if existing is not None:
            try:
                existing.show()
                return "ok"
            except Exception:
                _CAM_WINDOW = None
        spawned = webview.create_window(
            "Dornick · Kamera",
            url,
            width=980,
            height=640,
            min_size=(480, 320),
            background_color=WINDOW_BACKGROUND,
            frameless=True,
            easy_drag=False,
            text_select=True,
        )
        _CAM_WINDOW = spawned

        def minimize() -> None:
            _win_do("minimize", spawned)

        def maximize() -> bool:
            _update_max_bounds_for(spawned)
            return _win_do("maximize", spawned)

        def drag() -> bool:
            _win_do("drag", spawned)
            _update_max_bounds_for(spawned)
            return _is_zoomed(spawned)

        def resize(edge: str) -> None:
            _win_do("resize:" + str(edge), spawned)

        def close() -> None:
            try:
                spawned.destroy()
            except Exception:
                pass

        def is_zoomed() -> bool:
            return _is_zoomed(spawned)

        for fn in (minimize, maximize, drag, resize, close, is_zoomed):
            try:
                spawned.expose(fn)
            except Exception:
                pass

        def _dress() -> None:
            hwnd = _hwnd_of(spawned)
            if not hwnd:
                return
            _apply_native_styles_hwnd(hwnd)
            _install_shell_on(hwnd)
            _update_max_bounds_for(spawned)

        def _dress_retry(n: int) -> None:
            _dress()
            if n > 0 and not _hwnd_of(spawned):
                threading.Timer(0.12, lambda: _dress_retry(n - 1)).start()

        try:
            spawned.events.loaded += _dress
            spawned.events.shown += _dress
        except Exception:
            pass
        _dress_retry(12)

        def _gone() -> None:
            global _CAM_WINDOW
            _CAM_WINDOW = None

        try:
            spawned.events.closed += _gone
        except Exception:
            pass
        return "ok"

    # X = hide, the app lives IN THE TRAY (Claude Code / desktop tradition):
    # the running job, scheduled tasks and the senses don't die with the
    # window. It used to hide only while the ear was on; but X cutting the
    # work short is a wound independent of the ear — a running task must not
    # die just because the window closed either. No ghost-process risk
    # remains: every boot closes the old instances (_kill_ghosts) and there
    # is a real Exit in the tray. If the tray could not open at all (no
    # package) X really closes — otherwise the program could never be shut
    # down.
    hide_on_close = live

    # A single balloon on the FIRST press of X: "keeps running in the
    # background". Regardless of busy or not — when the window vanishes the
    # user thinks the program closed, and that is the thing to teach.
    # `note_once` prevents repeats (a balloon on every hide = nagging).
    def _remember_window() -> None:
        """The window box should open as it was at close."""
        try:
            zoomed = _is_zoomed()
            w = int(window.width or 0)
            h = int(window.height or 0)
            x = int(window.x if window.x is not None else 0)
            y = int(window.y if window.y is not None else 0)
            # Offset near-fullscreen = broken maximise; don't write it again.
            if not zoomed and prefs.offset_fullscreen(x, y, w, h):
                zoomed = True
            # A fake maximise seated on the work area also counts as maximised.
            elif not zoomed and _fills_work_area(x, y, w, h):
                zoomed = True
            box: dict[str, Any] = {"maximized": zoomed}
            if not zoomed:
                box.update({"width": w, "height": h, "x": x, "y": y})
            prefs.patch(config.state_dir, window=box)
        except Exception:
            pass

    def _hide_to_tray() -> None:
        _remember_window()
        window.hide()
        tray.note_once(tray_module.BACKGROUND_NOTE)

    def close() -> None:
        _remember_window()
        if hide_on_close:
            _hide_to_tray()
        else:
            window.destroy()

    for fn in (minimize, maximize, drag, resize, close, is_zoomed,
               open_camera_window, pano_oku, pano_yaz):
        window.expose(fn)

    # The native close (X / Alt+F4) must NOT DESTROY the program, it should
    # hide to the tray: when pywebview's closing event returns False the
    # close is cancelled and the window hides — the same path as the X on
    # the app strip.
    if hide_on_close:
        def _hide_instead_of_close() -> bool:
            return shutdown.may_close()

        try:
            window.events.closing += _hide_instead_of_close
        except Exception:
            pass

    # When the wake word is heard the window comes back: the page keeps
    # running while hidden, the microphone keeps listening.
    runtime.bridge.on_wake = _show_from_tray

    if hide_on_close:
        print("[dornick] tepside çalışıyor — X pencereyi gizler; görevler arka "
              "planda sürer, Çıkış tepsiden", flush=True)
    else:
        print("[dornick] tepsi yok; pencereyi kapatmak programı da kapatır "
              "(arka plan görevleri için: pip install 'dornick[tray]')",
              flush=True)

    try:
        # Window/taskbar icon: from the single-source logo (the same mark as
        # the tray and the tab). pywebview winforms makes it form.Icon.
        from . import logo as logo_module
        webview.start(
            lambda: _titlebar_boot(want_max=want_max),
            icon=str(logo_module.ico_path()),
            private_mode=False,
            storage_path=str(config.state_dir / "webview"),
        )
    finally:
        _remember_window()
        tray.stop()
        _teardown(loop, runtime)
    return 0


def _ensure_native_chrome() -> None:
    """Guarantees the single strip: installs styles + shell if not installed.

    If the window is hidden at boot `_titlebar_boot` can return empty-handed;
    when the window was shown later (tray, wake) the OS title bar stayed on
    top of the app strip. The installs are idempotent: if already installed
    there is no cost.
    """
    try:
        if _apply_native_styles():
            _install_shell()
            _update_max_bounds()
            paint_titlebar(True)
    except Exception:
        pass


def _titlebar_boot(*, want_max: bool = False) -> None:
    """Runs after webview starts: retries until the window exists.

    Single strip: CAPTION+THICKFRAME styles in place (snap), the
    WM_NCCALCSIZE top margin given to the client (OS strip invisible),
    WM_NCHITTEST edge grips.

    `want_max`: if prefs say maximised, force maximise once MaximizedBounds
    is ready — create_window(maximized)+offset didn't hold when frameless;
    it fixed itself on minimise/opening the taskbar.
    """
    import time
    for _ in range(40):
        if _apply_native_styles():
            _install_shell()
            _update_max_bounds()
            paint_titlebar(True)
            if want_max:
                _force_maximize()
            else:
                _clamp_window_to_work()
            # Watch against late breakage: if after the boot placement the
            # box drifts to (100,100) at someone's hand, catch it and seat it.
            threading.Thread(target=_geometry_watch, daemon=True,
                             name="dornick-geometry-watch").start()
            return
        time.sleep(0.15)


# Main window reference: for the window-shell helpers (MaximizedBounds).
_MAIN_WINDOW: Any = None
# Separate camera watch window (create_window); None once closed.
_CAM_WINDOW: Any = None

# Shell references (WndProc callback + old proc) must not be GC'd.
_SHELL: dict[int, tuple[Any, int]] = {}

# OS suspend/resume (roadmap 3.10.9). WM_POWERBROADCAST reaches the frame
# shell's WndProc above; the sleep daemon subscribes through this hook so
# the switch stops counting while the lid is closed and re-reads the hour
# when it opens. No shell installed (a non-Windows desktop, or a window
# that was never dressed) means no signal — the daemon then treats the
# clock jump as lived time, which is the conservative error.
_POWER_LISTENER: Any = None
_PBT_APMSUSPEND = 0x0004
_PBT_APMRESUMESUSPEND = 0x0007
_PBT_APMRESUMEAUTOMATIC = 0x0012


def _power_broadcast(wp: int) -> None:
    listener = _POWER_LISTENER
    if listener is None:
        return
    try:
        if wp == _PBT_APMSUSPEND:
            listener("suspend")
        elif wp in (_PBT_APMRESUMEAUTOMATIC, _PBT_APMRESUMESUSPEND):
            listener("resume")
    except Exception:
        pass

# PRIVATE WinDLL: ctypes.windll is a process-wide SHARED cache — when
# pystray/pywebview wrote their own argtypes onto the same function objects
# our calls crashed with broken marshaling (the real root of the access
# violations; proven with a sabotaged stress test). This handle is ours alone.
_PRIV: dict[str, Any] = {}


def _user32() -> Any:
    if "u" not in _PRIV:
        import ctypes
        from ctypes import wintypes

        u = ctypes.WinDLL("user32", use_last_error=True)
        LRESULT = ctypes.c_longlong
        u.CallWindowProcW.restype = LRESULT
        u.CallWindowProcW.argtypes = [LRESULT, wintypes.HWND, ctypes.c_uint,
                                      wintypes.WPARAM, wintypes.LPARAM]
        u.SetWindowLongPtrW.restype = LRESULT
        u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, LRESULT]
        u.GetWindowLongPtrW.restype = LRESULT
        u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SendMessageW.restype = LRESULT
        u.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                   wintypes.WPARAM, wintypes.LPARAM]
        _PRIV["u"] = u
    return _PRIV["u"]


def _install_shell() -> bool:
    """Window shell: invisible frame, native behaviour (proven design).

    WS_THICKFRAME STAYS on the window: Windows grants edge resizing and snap
    only to a resizable window.

    Swallowing the frame ENTIRELY with WM_NCCALCSIZE→0 broke snap: Windows
    applied the snap size but NOT the position, the window kept following
    the mouse (verbatim in the isolated test: dragging to the left edge the
    client stayed at (-400,504) 960x1032, expected (0,0) 960x1032). Edge
    resizing was dead for the same reason (0 pixels in 3/3 runs). Windows
    looks at the REAL frame metrics to place a snapped/resized window; with
    the frame zeroed the arithmetic doesn't hold.

    So the frame is left IN PLACE and only the TOP margin is folded into the
    client: the side/bottom edges remain as Windows' invisible grips (they
    are invisible anyway — the window edge ends in the client), and no OS
    strip remains at the top. In the same isolated test snap seated the
    client at (1,0) 958x1031 and Windows' snap preview / Snap Assist panel
    appeared; resizing worked 3/3. When maximised no frame margin is wanted:
    since MaximizedBounds seats the window on the work area, client = window
    (→0) and maximise lands exactly on the work area.

    WM_NCHITTEST provides the edge grips. Passed a 5000+ message sabotaged
    stress test in a separate window with zero errors.
    """
    if sys.platform != "win32":
        return True
    targets = _dornick_windows(hidden_too=True)   # see _apply_native_styles
    if not targets:
        return False
    ok = False
    for hwnd in targets:
        if _install_shell_on(hwnd):
            ok = True
    return ok


def _install_shell_on(hwnd: int) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        u = _user32()
        if hwnd in _SHELL:
            return True

        LRESULT = ctypes.c_longlong
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint,
                                     wintypes.WPARAM, wintypes.LPARAM)
        old = u.GetWindowLongPtrW(hwnd, -4)   # GWLP_WNDPROC

        class NcCalcSize(ctypes.Structure):
            _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        def proc(h, msg, wp, lp):
            try:
                if msg == 0x0083 and wp:          # WM_NCCALCSIZE(TRUE)
                    p = ctypes.cast(lp, ctypes.POINTER(NcCalcSize)).contents
                    if u.IsZoomed(h):
                        # When a thick-framed window maximises, Windows pushes
                        # it ~8px OFF the screen; the real non-client hides
                        # that margin. Once we swallowed the frame in zoom the
                        # HUD/top strip drifted to -8 too. Lock the client to
                        # the monitor's WORK AREA.
                        mi = MonitorInfo()
                        mi.cbSize = ctypes.sizeof(MonitorInfo)
                        mon = u.MonitorFromRect(ctypes.byref(p.rgrc[0]), 2)
                        if (mon and u.GetMonitorInfoW(mon, ctypes.byref(mi))
                                and abs(p.rgrc[0].left - mi.rcWork.left) <= 64
                                and abs(p.rgrc[0].top - mi.rcWork.top) <= 64):
                            p.rgrc[0].left = mi.rcWork.left
                            p.rgrc[0].top = mi.rcWork.top
                            p.rgrc[0].right = mi.rcWork.right
                            p.rgrc[0].bottom = mi.rcWork.bottom
                        else:
                            # Fallback — and an OFFSET zoom: with the window
                            # zoomed at a broken position such as (100,100),
                            # the work-area lock shifted the client NEGATIVE
                            # relative to the window (live: content clipped
                            # on the left/top, desktop leaking). If offset,
                            # settle for the classic margin; seating the
                            # window is _heal_geometry's job.
                            p.rgrc[0].left += 8
                            p.rgrc[0].top += 8
                            p.rgrc[0].right -= 8
                            p.rgrc[0].bottom -= 8
                        return 0
                    top = p.rgrc[0].top
                    ret = u.CallWindowProcW(old, h, msg, wp, lp)
                    p.rgrc[0].top = top            # top margin to the client
                    return ret
                if msg == 0x0084:                  # WM_NCHITTEST
                    x = ctypes.c_short(lp & 0xFFFF).value
                    y = ctypes.c_short((lp >> 16) & 0xFFFF).value
                    r = wintypes.RECT()
                    u.GetWindowRect(h, ctypes.byref(r))
                    if not u.IsZoomed(h):
                        left = x < r.left + 8
                        right = x >= r.right - 8
                        top = y < r.top + 8
                        bottom = y >= r.bottom - 8
                        if top and left: return 13
                        if top and right: return 14
                        if bottom and left: return 16
                        if bottom and right: return 17
                        if left: return 10
                        if right: return 11
                        if top: return 12
                        if bottom: return 15
                if msg == 0x0218:                  # WM_POWERBROADCAST
                    _power_broadcast(int(wp))
            except Exception:
                pass
            return u.CallWindowProcW(old, h, msg, wp, lp)

        cb = WNDPROC(proc)
        u.SetWindowLongPtrW(hwnd, -4, ctypes.cast(cb, ctypes.c_void_p).value)
        _SHELL[hwnd] = (cb, old)
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_FRAMECHANGED)
        return True
    except Exception:
        return False


def _hwnd_of(window: Any) -> int:
    """HWND of the pywebview window; 0 if not born yet."""
    if window is None:
        return 0
    try:
        form = getattr(window, "native", None)
        if form is None:
            return 0
        handle = getattr(form, "Handle", None)
        if handle is None:
            return 0
        to64 = getattr(handle, "ToInt64", None)
        return int(to64()) if callable(to64) else int(handle)
    except Exception:
        return 0


def _update_max_bounds() -> None:
    _update_max_bounds_for(_MAIN_WINDOW)


def _update_max_bounds_for(window: Any) -> None:
    """Sets the maximise bound to the WORK AREA of the current monitor.

    Windows maximises a frameless window to full screen (over the taskbar)
    — the behaviour the user complained about first. WinForms'
    MaximizedBounds property solves this at the root: EVERY maximise path —
    Win+Up, snap to the top edge, and our own button — uses this bound.
    The work area of whichever monitor the window is on; refreshed after
    every drag so a monitor change stays correct.
    """
    if window is None or sys.platform != "win32":
        return
    try:
        form = window.native
        if form is None:
            return
        from System import Action  # type: ignore[import-not-found]
        from System.Drawing import Rectangle  # type: ignore[import-not-found]
        from System.Windows.Forms import Screen  # type: ignore[import-not-found]

        def apply() -> None:
            screen = Screen.FromControl(form)
            wa, sb = screen.WorkingArea, screen.Bounds
            # THE POSITION HAS TO BE RELATIVE TO THE MONITOR (WM_GETMINMAXINFO
            # ptMaxPosition semantics): given absolute, Windows adds the
            # monitor origin ONCE MORE and on the second monitor the window
            # maximised entirely OFF screen — this was the bug behind the
            # user's 'it vanishes when I press the square' (caught live:
            # expected (1920,-77), went to (3840,-154); proven on a separate
            # form that with the relative position it seats exactly on the
            # work area).
            form.MaximizedBounds = Rectangle(
                wa.X - sb.X, wa.Y - sb.Y, wa.Width, wa.Height)

        # WinForms properties from the UI thread: Invoke queues it there.
        form.Invoke(Action(apply))
    except Exception:
        pass


def _apply_native_styles() -> bool:
    """Gives the frameless window a native window IDENTITY.

    WS_CAPTION is a must: Windows applies the Aero snap / edge-snap position
    correctly only to captioned windows. The visual OS strip is erased by
    the shell's WM_NCCALCSIZE top-swallow; the style flag stays in place.

    THICKFRAME + MIN/MAXIMIZEBOX + SYSMENU: edge resize, Win+arrow, taskbar
    animations. Win11 rounds the corners.
    """
    if sys.platform != "win32":
        return True
    try:
        # The HIDDEN window is a target too: when the app opened into the
        # tray (the window is born hidden) the visibility filter found
        # nothing and `_titlebar_boot` tried for six seconds and gave up —
        # the shell was never installed, and when the window was shown later
        # Windows' own title bar stayed ON TOP of the app's strip (live
        # wound, 02.09: "two strips at the top").
        targets = _dornick_windows(hidden_too=True)
        if not targets:
            return False
        for hwnd in targets:
            _apply_native_styles_hwnd(hwnd)
        return True
    except Exception:
        return False


def _apply_native_styles_hwnd(hwnd: int) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, _GWL_STYLE)
        style |= (
            _WS_CAPTION
            | _WS_THICKFRAME
            | _WS_MINIMIZEBOX
            | _WS_MAXIMIZEBOX
            | _WS_SYSMENU
        )
        user32.SetWindowLongW(hwnd, _GWL_STYLE, style)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_FRAMECHANGED)
        try:
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass
        return True
    except Exception:
        return False


_GWL_STYLE = -16
_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_WS_MINIMIZEBOX = 0x00020000
_WS_MAXIMIZEBOX = 0x00010000
_WS_SYSMENU = 0x00080000
_SWP_FRAMECHANGED = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
_WM_NCLBUTTONDOWN = 0x00A1
_HTCAPTION = 2
_WM_SYSCOMMAND = 0x0112
_SC_MINIMIZE = 0xF020
_SC_MAXIMIZE = 0xF030
_SC_RESTORE = 0xF120
# Edge HT* — SC_SIZE was dead under FormBorderStyle.None; NCLBUTTONDOWN works.
_HT_EDGES = {
    "l": 10, "r": 11, "t": 12, "tl": 13, "tr": 14,
    "b": 15, "bl": 16, "br": 17,
}


def _is_zoomed(window: Any | None = None) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        hwnd = _hwnd_of(window) if window is not None else 0
        if not hwnd:
            targets = _dornick_windows()
            hwnd = targets[0] if targets else 0
        return bool(hwnd and ctypes.windll.user32.IsZoomed(hwnd))
    except Exception:
        return False


def _win_do(action: str, window: Any | None = None) -> bool:
    """Window actions from the app strip: drag / minimise / maximise / restore.

    Dragging is WM_NCLBUTTONDOWN + HTCAPTION: the OS move loop (Aero snap
    included). The JS bridge comes from another thread — we run SendMessage
    on the WinForms UI thread via BeginInvoke; otherwise the loop never
    starts while the mouse is down (user: 'I can't grab the top bar and
    drag').

    SendMessageW / ReleaseCapture from the private `_user32()` handle: when
    pywebview/pystray corrupted the shared ctypes.windll argtypes the call
    died silently.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        u = _user32()
        raw = ctypes.windll.user32
        hwnd = _hwnd_of(window) if window is not None else 0
        if not hwnd:
            targets = _dornick_windows()
            if not targets:
                return False
            hwnd = targets[0]

        def _drag_now() -> None:
            if raw.IsZoomed(hwnd):
                pt = wintypes.POINT()
                raw.GetCursorPos(ctypes.byref(pt))
                before = wintypes.RECT()
                raw.GetWindowRect(hwnd, ctypes.byref(before))
                span = max(before.right - before.left, 1)
                ratio = (pt.x - before.left) / span
                raw.ShowWindow(hwnd, 9)  # SW_RESTORE
                after = wintypes.RECT()
                raw.GetWindowRect(hwnd, ctypes.byref(after))
                w = after.right - after.left
                nx = int(pt.x - w * ratio)
                ny = pt.y - 28
                raw.SetWindowPos(hwnd, 0, nx, ny, 0, 0, 0x0001 | 0x0004)
            raw.ReleaseCapture()
            u.SendMessageW(hwnd, _WM_NCLBUTTONDOWN, _HTCAPTION, 0)

        def _resize_now(edge: int) -> None:
            if raw.IsZoomed(hwnd):
                return
            raw.ReleaseCapture()
            u.SendMessageW(hwnd, _WM_NCLBUTTONDOWN, edge, 0)

        def _on_ui(fn) -> None:
            """The move/resize loop must start on the UI thread."""
            win = window if window is not None else _MAIN_WINDOW
            form = getattr(win, "native", None) if win is not None else None
            if form is not None:
                try:
                    from System import Action  # type: ignore[import-not-found]
                    form.BeginInvoke(Action(fn))
                    return
                except Exception:
                    pass
            fn()

        if action == "drag":
            _on_ui(_drag_now)
        elif action == "minimize":
            u.SendMessageW(hwnd, _WM_SYSCOMMAND, _SC_MINIMIZE, 0)
        elif action == "maximize":
            if raw.IsZoomed(hwnd):
                u.SendMessageW(hwnd, _WM_SYSCOMMAND, _SC_RESTORE, 0)
            else:
                u.SendMessageW(hwnd, _WM_SYSCOMMAND, _SC_MAXIMIZE, 0)
            return bool(raw.IsZoomed(hwnd))
        elif action.startswith("resize:"):
            edge = _HT_EDGES.get(action.split(":", 1)[1])
            if edge:
                _on_ui(lambda e=edge: _resize_now(e))
        return False
    except Exception:
        return False


def _dornick_windows(*, hidden_too: bool = False) -> list[int]:
    """HWNDs of the visible top-level windows titled 'dornick' in this process.

    FindWindowW(None, title) returns a single match and on some setups found
    nothing at all; EnumWindows reliably gives every match (proven on the
    live window).

    `hidden_too=True` lifts the visibility filter: the one place that needs an
    owner HWND even while the window is hidden to the tray is `_confirm_quit`
    — and at exactly that moment the window is hidden.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []
    my_pid = os.getpid()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        if not hidden_too and not user32.IsWindowVisible(hwnd):
            return True
        # ONLY this process's window: with two dornick instances open (or a
        # test instance around) the buttons were driving the OTHER instance's
        # window — "I press, nothing happens / something else happens" was
        # exactly this.
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != my_pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value.strip().lower() == WINDOW_TITLE.lower():
            found.append(hwnd)
        return True

    user32.EnumWindows(_enum, 0)
    return found


def paint_titlebar(dark: bool = True) -> bool:
    """Paints the native title bar in the app's theme (Windows 11 DWM).

    The native frame gives normal window behaviour (move/maximise/resize/
    snap) but the operating system's light title bar clashed with the dark
    holographic body ("this top part became inconsistent with the system").
    We make the title bar dark/light through DWM; the theme button in the UI
    calls this too so the OS bar and the app theme turn together. Returns
    False if the window doesn't exist yet so the caller retries.
    """
    if sys.platform != "win32":
        return True   # nothing to do on another platform, count it as "done"
    try:
        import ctypes

        user32 = ctypes.windll.user32
        dwm = ctypes.windll.dwmapi
        targets = _dornick_windows()
        if not targets:
            return False   # the window doesn't exist yet — the caller retries

        def _set(hwnd: int, attr: int, value: int) -> None:
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        for hwnd in targets:
            # Immersive dark mode — both the new (20) and the old (19) index;
            # whichever is valid on this build sticks.
            for attr in (20, 19):
                _set(hwnd, attr, 1 if dark else 0)
            # Full colour (Win11 22000+): COLORREF 0x00BBGGRR. Dark
            # #0b0e14/#dceefc, light #e7edf4/#1a2836. Silently ignored on
            # an older build.
            _set(hwnd, 35, 0x00140E0B if dark else 0x00F4EDE7)  # caption background
            _set(hwnd, 36, 0x00FCEEDC if dark else 0x0036281A)  # title text
            # Force the title bar to redraw at once (FRAMECHANGED).
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
        return True
    except Exception:
        return False


def _minimize(window: Any) -> Any:
    def minimize() -> None:
        window.minimize()

    return minimize


def _work_area() -> tuple[int, int, int, int] | None:
    """The screen area excluding the taskbar (x, y, width, height)."""
    return prefs.work_area()


def _force_maximize() -> None:
    """Seat on the work area — the native SW_MAXIMIZE drifted when frameless.

    create_window(maximized=True) / ShowWindow(SW_MAXIMIZE) left IsZoomed=True
    and left the HWND at something like (101,101) (desktop gap on the left).
    Minimise/restore fixed it. At boot we give the work-area box directly;
    the prefs `maximized` flag is preserved by _remember_window.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        raw = ctypes.windll.user32
        hwnd = _hwnd_of(_MAIN_WINDOW)
        if not hwnd:
            targets = _dornick_windows()
            hwnd = targets[0] if targets else 0
        if not hwnd:
            return
        area = _work_area()
        if not area:
            return
        ax, ay, aw, ah = area
        _update_max_bounds()
        # SW_RESTORE: let go of the previous broken zoom state.
        if raw.IsZoomed(hwnd):
            raw.ShowWindow(hwnd, 9)
        # SWP_NOZORDER|SWP_SHOWWINDOW
        raw.SetWindowPos(hwnd, 0, ax, ay, aw, ah, 0x0004 | 0x0040)
        r = wintypes.RECT()
        raw.GetWindowRect(hwnd, ctypes.byref(r))
        if (
            abs(r.left - ax) > prefs.OFFSET_SLACK
            or abs(r.top - ay) > prefs.OFFSET_SLACK
            or abs((r.right - r.left) - aw) > prefs.OFFSET_SLACK * 2
        ):
            raw.SetWindowPos(hwnd, 0, ax, ay, aw, ah, 0x0004 | 0x0040)
    except Exception:
        pass


def _monitor_work_area(hwnd: int) -> tuple[int, int, int, int] | None:
    """Work area of the monitor the window is ON.

    `prefs.work_area` only knows the PRIMARY monitor; a window maximised on
    the second monitor must not be taken for "offset" and dragged to the
    primary screen — the comparison must be against the window's own
    monitor.
    """
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _MI(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        raw = ctypes.windll.user32
        mon = raw.MonitorFromWindow(hwnd, 2)   # MONITOR_DEFAULTTONEAREST
        if not mon:
            return None
        mi = _MI()
        mi.cbSize = ctypes.sizeof(_MI)
        if not raw.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        wa = mi.rcWork
        return (wa.left, wa.top, wa.right - wa.left, wa.bottom - wa.top)
    except Exception:
        return None


def _heal_geometry() -> bool:
    """Catches an offset maximise and seats it — the "minimise/restore" gesture in code.

    Live wound (31.08): at boot the window came near-full size but offset to
    something like (100,100) — desktop leaking from the left/top, and if
    zoomed the content was clipped to the left too; it fixed itself when the
    user minimised and restored by hand. Here the same gesture in code: if an
    offset zoom or an offset near-full box is seen, restore + seat on the
    work area of the window's OWN monitor.

    Doesn't touch a proper window; doesn't interfere during a drag either
    (does nothing while the left mouse button is down). Returns whether
    anything was fixed.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        raw = ctypes.windll.user32
        hwnd = _hwnd_of(_MAIN_WINDOW)
        if not hwnd:
            targets = _dornick_windows()
            hwnd = targets[0] if targets else 0
        if not hwnd or not raw.IsWindowVisible(hwnd) or raw.IsIconic(hwnd):
            return False
        if raw.GetAsyncKeyState(0x01) & 0x8000:   # may be a drag
            return False

        r = wintypes.RECT()
        raw.GetWindowRect(hwnd, ctypes.byref(r))
        x, y = r.left, r.top
        w, h = r.right - r.left, r.bottom - r.top

        area = _monitor_work_area(hwnd) or _work_area()
        if not area:
            return False
        ax, ay, aw, ah = area
        shifted = (abs(x - ax) > prefs.OFFSET_SLACK
                   or abs(y - ay) > prefs.OFFSET_SLACK)
        if raw.IsZoomed(hwnd):
            if not shifted:
                return False
        elif not prefs.offset_fullscreen(x, y, w, h, area):
            return False

        _update_max_bounds()
        if raw.IsZoomed(hwnd):
            raw.ShowWindow(hwnd, 9)   # SW_RESTORE: let go of the broken zoom state
        # SWP_NOZORDER | SWP_SHOWWINDOW
        raw.SetWindowPos(hwnd, 0, ax, ay, aw, ah, 0x0004 | 0x0040)
        return True
    except Exception:
        return False


def _geometry_watch(seconds: float = 12.0) -> None:
    """Keeps an eye on the window box for a short while after boot.

    A broken maximise can also occur AFTER `_force_maximize` (the WebView2 /
    pywebview start-up moves the position late); a single shot was not
    enough — the user saw the window clipped and minimised/reopened it by
    hand. This watch catches the late breakage and fixes it, then ends on
    its own.
    """
    import time
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        time.sleep(0.6)
        _heal_geometry()


def _fills_work_area(x: int, y: int, w: int, h: int) -> bool:
    """Does the window fill the work area (fake maximise)."""
    area = _work_area()
    if not area:
        return False
    ax, ay, aw, ah = area
    return (
        abs(x - ax) <= prefs.OFFSET_SLACK
        and abs(y - ay) <= prefs.OFFSET_SLACK
        and w >= aw * prefs.NEAR_FULL
        and h >= ah * prefs.NEAR_FULL
    )


def _clamp_window_to_work() -> None:
    """If the un-maximised window is outside the work area, pull it inside."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        from .prefs import MIN_H, MIN_W

        area = _work_area()
        if not area:
            return
        ax, ay, aw, ah = area
        hwnd = _hwnd_of(_MAIN_WINDOW)
        if not hwnd:
            targets = _dornick_windows()
            hwnd = targets[0] if targets else 0
        if not hwnd:
            return
        raw = ctypes.windll.user32
        if raw.IsZoomed(hwnd):
            return
        r = wintypes.RECT()
        raw.GetWindowRect(hwnd, ctypes.byref(r))
        cur_w = r.right - r.left
        cur_h = r.bottom - r.top
        x, y = r.left, r.top
        if prefs.offset_fullscreen(x, y, cur_w, cur_h, area):
            _force_maximize()
            return
        w = min(max(cur_w, MIN_W), aw)
        h = min(max(cur_h, MIN_H), ah)
        nx = max(ax, min(x, ax + max(aw - w, 0)))
        ny = max(ay, min(y, ay + max(ah - h, 0)))
        if (nx, ny, w, h) != (x, y, cur_w, cur_h):
            raw.SetWindowPos(hwnd, 0, nx, ny, w, h, 0x0004)  # SWP_NOZORDER
    except Exception:
        pass


def _maximize(window: Any) -> Any:
    """Maximise / restore — respectful of the taskbar (not full screen).

    On a frameless window `window.maximize()` gave a full screen that covered
    the taskbar too. Instead we move and resize the window to the screen's
    work area (taskbar excluded); a second click returns to the previous
    position/size. That solves both "it maximises but won't shrink back" and
    "it grabbed the taskbar" together. If the work area can't be obtained
    (non-Windows or an error) it falls back to `maximize()`.
    """
    state: dict[str, Any] = {"box": None}

    def maximize() -> None:
        if state["box"] is not None:
            x, y, w, h = state["box"]
            state["box"] = None
            try:
                window.move(x, y)
                window.resize(w, h)
            except Exception:
                try:
                    window.restore()
                except Exception:
                    pass
            return

        area = _work_area()
        if area is None:
            window.maximize()
            state["box"] = None
            return
        try:
            state["box"] = (window.x, window.y, window.width, window.height)
            window.move(area[0], area[1])
            window.resize(area[2], area[3])
        except Exception:
            state["box"] = None
            window.maximize()

    return maximize


def _close(window: Any, *, tray: bool = False) -> Any:
    """The close button.

    If the tray is running it hides: the background jobs go on. Without a
    tray it really closes — otherwise the program could never be shut down
    and the user would have to kill it from the task manager.
    """

    def close() -> None:
        window.hide() if tray else window.destroy()

    return close


def _wake(window: Any) -> Any:
    def wake() -> None:
        window.show()
        threading.Timer(0.4, _heal_geometry).start()

    return wake


def _confirm_quit(question: str) -> bool:
    """Exit confirmation: a native Yes/No dialog (safe from the tray thread).

    It has to show even while the window is hidden; MB_TOPMOST +
    MB_SETFOREGROUND bring it forward. Off Windows, or when the dialog can't
    be built, True: the user's explicit Exit gesture must not turn into the
    "I can't quit" trap.

    An OWNER window is given. An ownerless (hWnd=0) MessageBox gets its own
    taskbar button, and that button's icon was not the app's but the
    process default — i.e. Python's snake. An owned box opens no separate
    button. If no window is found (not born yet or destroyed) we fall back to
    0: a question with the wrong icon beats a question never asked.
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        MB_YESNO = 0x0004
        MB_ICONWARNING = 0x0030
        MB_TOPMOST = 0x00040000
        MB_SETFOREGROUND = 0x00010000
        IDYES = 6
        try:
            owners = _dornick_windows(hidden_too=True)
        except Exception:
            owners = []
        answer = ctypes.windll.user32.MessageBoxW(
            owners[0] if owners else 0, question, WINDOW_TITLE,
            MB_YESNO | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND,
        )
        return answer == IDYES
    except Exception:
        return True


def _teardown(loop: asyncio.AbstractEventLoop, runtime: Runtime) -> None:
    for job in (runtime.ticker, runtime.greeter):
        if job is not None:
            loop.call_soon_threadsafe(job.cancel)
    if runtime.eyes is not None:
        runtime.eyes.stop()
    if runtime.lens is not None:
        runtime.lens.stop()
    if runtime.ear is not None:
        runtime.ear.stop()
    runtime.bridge.cancel_pending()
    # A night in progress finishes its unit and stops; the rest is debt.
    try:
        runtime.bridge.stop_sleep()
    except Exception:
        pass
    # Open MCP sessions hold child processes; left unclosed, ghosts remain.
    pool = getattr(runtime.server._httpd, "connectors", None)
    if pool is not None:
        pool.close()
    runtime.server.stop()
    runtime.session.close()

    # On a model-less boot the client was never built (see _boot).
    if runtime.client is not None:
        closing = asyncio.run_coroutine_threadsafe(runtime.client.close(), loop)
        try:
            closing.result(timeout=5)
        except Exception:
            pass
    loop.call_soon_threadsafe(loop.stop)
