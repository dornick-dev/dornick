"""Mind store.

Four surfaces:

    semantic    learned facts, preferences, lessons      -> memories.jsonl
    procedural  procedures that worked (kind="procedure") -> memories.jsonl
    working     the goal stack                            -> goals.jsonl
    episodic    event logs of past sessions               -> sessions/*.jsonl

Episodic memory has no store of its own — the session logs already are it.
The mind lays a search surface over them. This is a direct payoff of the
decision to keep the event log as the single source of truth.

The write format is append-only JSONL everywhere: a later record with the
same id supersedes the earlier one. There is no such thing as deletion, there
are tombstones — what the mind forgot and when is part of the mind too.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from ..recall import Step, open_store
from ..recall.clock import Clock, stamp, wall_clock
from .search import Scored, excerpt, rank

# "episode" differs from the others: the agent does not write it by hand,
# context compaction does. It does not enter the soul (soul() picks kinds one
# by one) but it can come back through association — that is why compaction
# is persistent.
MEMORY_KINDS = ("fact", "preference", "lesson", "procedure", "user", "voice",
                "episode", "world", "self")
GOAL_STATES = ("active", "done", "dropped")

# Maximum number of records (per kind) that go into the soul digest. The soul
# is part of the system prompt; if it grows without bound every session
# starts more expensive.
SOUL_LIMIT = 8

# A correction made within this many days is guaranteed a place in the soul.
# Ranking by activation does the right thing — a procedure in regular use
# really is more alive than a week-old correction. But a correction is not an
# ordinary memory: the reason the soul sits in the system prompt is so the
# agent does not act on a stale rule. The reserved share does not exceed half
# — the soul is not a list of corrections.
FRESH_CORRECTION_DAYS = 7

# Maximum number of sessions scanned by the episodic search. As the logs grow
# this gets replaced with an index.
MAX_SCANNED_SESSIONS = 60


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


@dataclass(slots=True)
class Memory:
    id: str
    ts: str
    kind: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    session_id: str = ""
    deleted: bool = False
    # In the active set? A cold record is found by search but does not enter
    # the bootstrap.
    hot: bool = True
    # Which record this one replaced. The soul reserves room for a correction
    # made this week: a correction is not an ordinary memory, it is a CHANGE.
    supersedes: str = ""
    context: dict = field(default_factory=dict)

    def searchable(self) -> str:
        return f"{self.title}\n{self.content}\n{' '.join(self.tags)}"

    def render(self) -> str:
        tags = f" [{', '.join(self.tags)}]" if self.tags else ""
        return f"({self.kind}) {self.title}{tags}\n{self.content}"


@dataclass(slots=True)
class Goal:
    id: str
    ts: str
    text: str
    status: str = "active"
    session_id: str = ""
    note: str = ""


@dataclass(slots=True)
class Soul:
    """The identity that survives across sessions.

    Derived from the mind on disk and placed into the system prompt at the
    start of a session. The agent's answer to "who am I, who is this user,
    what have I learned so far" — held without calling any tool.

    Procedures contribute titles only — detail comes via `mind_recall`.
    Piling everything into the prompt is the opposite of progressive
    disclosure and starts every session needlessly expensive.
    """

    persona: str
    user: list[Memory]
    preferences: list[Memory]
    lessons: list[Memory]
    voice: list[Memory]
    procedures: list[Memory]
    goals: list[Goal]
    sessions: int
    first_seen: str

    @property
    def is_blank(self) -> bool:
        return not any(
            (self.persona, self.user, self.preferences, self.lessons, self.voice,
             self.procedures, self.goals)
        )

    def render(self) -> str:
        if self.is_blank:
            # The first-meeting directive lives here, not in IDENTITY: written
            # into the permanent identity it would still say "let's get
            # acquainted" in the hundredth session. The moment the soul fills
            # up this block drops out by itself.
            return (
                "Bu kullanıcıyla ilk kez karşılaşıyorsun; diskteki zihnin henüz "
                "boş. Bu bir eksiklik değil, bir başlangıç — tanışmaya istekli "
                "ol.\n\n"
                "İlk konuşmada:\n"
                "- Kısa ve kendinden emin ol: kendini bir cümleyle tanıt, ne "
                "işe yaradığını bir iki somut örnekle söyle ve dur. Yetenek ya "
                "da donanım envanteri sayma; eksik duyularından (mikrofon, "
                "kamera, ses) kendiliğinden hiç söz etme.\n"
                "- En fazla tek doğal soru sor: adını — o da zaten "
                "söylemediyse (\"adın ne?\" yeter, hitap kalıbı sorulmaz). "
                "Söylenmiş bilgiyi yeniden sorma. Adını öğrenince "
                "`mind_memory` ile kaydet (kind=user); ikinci oturumda ona "
                "adıyla hitap edebilmelisin.\n"
                "- Ne üzerinde çalıştığını, seni ne için kullanmak istediğini "
                "zamanla öğren — sorgu listesi gibi değil.\n\n"
                "Kaydettiğin, kullanıcının söylediği olsun — senin tahminin "
                "değil. Sistem promptunda zaten yazan (çalışma alanı, tarih, "
                "işletim sistemi) hatıra değildir; onlar her oturumda hazır."
            )

        parts = [self._history_line()]
        if self.persona:
            parts.append(self.persona)

        # Speaking style comes first: what sets the tone of the answer must be
        # read before the content of the answer.
        if self.voice:
            parts.append(
                "Bu kullanıcıyla nasıl konuştuğun:\n"
                + "\n".join(f"- {m.content}" for m in self.voice)
            )

        for title, items in (
            ("Kullanıcı hakkında bildiklerin", self.user),
            ("Kullanıcının tercihleri", self.preferences),
            ("Çıkardığın dersler", self.lessons),
        ):
            if items:
                parts.append(f"{title}:\n" + "\n".join(f"- {m.content}" for m in items))

        if self.procedures:
            titles = "\n".join(f"- {m.title}" for m in self.procedures)
            parts.append(
                f"Bildiğin yordamlar (detay için mind_recall):\n{titles}"
            )

        if self.goals:
            # The ledger is now filtered to the session: only the open items
            # of the RESUMED conversation land here. The framing sentence is
            # essential — a bare list reads to a small model like an
            # instruction that pre-empts the first message.
            parts.append(
                "Bu sohbetin açık hedefleri (hatırlatma, talimat değil — "
                "gündemi kullanıcının son sözü belirler):\n"
                + "\n".join(f"- [{g.id}] {g.text}" for g in self.goals)
            )

        return "\n\n".join(parts)

    def _history_line(self) -> str:
        if self.sessions <= 1:
            return "Aşağıdakiler diskteki zihninden geliyor — önceki oturumlarda öğrendiklerin."
        since = self.first_seen[:10] if self.first_seen else "bir süredir"
        return (
            f"Aşağıdakiler diskteki zihninden geliyor: {self.sessions} oturumdur "
            f"({since} tarihinden beri) bu kullanıcıyla çalışıyorsun."
        )


@dataclass(slots=True)
class Episode:
    session_id: str
    started: str
    turns: int
    tools: list[str]
    digest: str
    # A subagent's (helper's) session? The helper's log opens with a
    # `subagent_start(parent=...)` note; the chat list hides these — the
    # user's conversation history is their own conversations, not the
    # helpers' intermediate work.
    child: bool = False

    def searchable(self) -> str:
        return f"{self.digest}\n{' '.join(self.tools)}"


class Mind:
    def __init__(
        self,
        mind_dir: Path,
        sessions_dir: Path,
        session_id: str = "",
        *,
        clock: Clock | None = None,
    ) -> None:
        self.dir = mind_dir
        # The mind and the recall store must see the SAME clock: if the goal
        # ledger and the node stamps come from different calendars the
        # freshness ordering breaks silently (see recall/clock.py).
        self._clock: Clock = clock or wall_clock
        self.sessions_dir = sessions_dir
        self.session_id = session_id
        self.dir.mkdir(parents=True, exist_ok=True)

        self._context: dict = {}
        self._goals: dict[str, Goal] = {}
        self._episode_cache: dict[str, tuple[int, Episode]] = {}
        # Transcript cache (keyed by mtime): the deep search used to re-parse
        # 40 sessions on every exchange, and the running chat's transcript was
        # re-read on every pass as well. If the file has not changed the
        # result is returned as is.
        self._transcript_cache: dict[str, tuple[int, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

        # Memories live in the indexed store: search is an index lookup, not
        # a scan. Goals stay JSONL — their number is bounded, scanning costs
        # nothing.
        self.store = open_store(self.dir, clock=self._clock)
        self.last_trace: list[Step] = []
        self._migrate_jsonl()
        # The signatures on disk are pulled into RAM in the background before
        # the first message even arrives: the first recall must not wait for
        # the index to be built.
        self.store.warm()

        _load(self.dir / "goals.jsonl", Goal, self._goals)

    def _now(self) -> str:
        """The "now" stamp written to disk — from the same clock as the store."""
        return stamp(self._clock)

    def _migrate_jsonl(self) -> None:
        """Moves legacy memories.jsonl records into the indexed store once."""
        legacy = self.dir / "memories.jsonl"
        if not legacy.exists() or self.store.count():
            return
        old: dict[str, Memory] = {}
        _load(legacy, Memory, old)
        for memory in old.values():
            if memory.deleted:
                continue
            self.store.remember(
                memory.content,
                kind=memory.kind,
                title=memory.title,
                tags=memory.tags,
                session=memory.session_id,
            )
        legacy.rename(legacy.with_suffix(".jsonl.migrated"))

    # -- semantic / procedural ----------------------------------------

    def remember(
        self,
        content: str,
        *,
        kind: str = "fact",
        title: str = "",
        tags: Iterable[str] = (),
        context: dict | None = None,
        night: bool = False,
    ) -> Memory:
        """Writes the memory; the harness attaches the context, not the model.

        If the context were the model's declaration, the answer to "which
        project were we in" would be a guess too. Yet which project we are in
        at that moment is one of the few things the harness knows for certain.
        """
        if kind not in MEMORY_KINDS:
            raise ValueError(f"Bilinmeyen bellek türü: {kind}")
        # `self` is derived only from outcome events; the model's declaration
        # about itself is not recorded (see recall/subjects.py).
        from ..recall.subjects import guard_model_write

        guard_model_write(kind, from_night=night)
        node = self.store.remember(
            content,
            kind=kind,
            title=title,
            tags=tags,
            session=self.session_id,
            context=context if context is not None else self.context(),
        )
        return _from_node(node)

    def context(self) -> dict:
        """The current session's context. Set from outside via `set_context`."""
        return dict(self._context)

    def set_context(self, context: dict | None) -> None:
        self._context = dict(context or {})

    def update(
        self,
        old_id: str,
        content: str,
        *,
        kind: str = "",
        title: str = "",
        tags: Iterable[str] = (),
    ) -> Memory:
        """Writes a new record in place of an old one; the old one falls into history, not deleted.

        The mechanism that replaces the "delete the old one and write the
        current one" advice in the tool description. Deleting was irreversible
        and sat behind the approval gate; this is not — nothing gets lost.
        """
        if kind and kind not in MEMORY_KINDS:
            raise ValueError(f"Bilinmeyen bellek türü: {kind}")
        node = self.store.update(old_id, content, kind=kind, title=title,
                                   tags=tags, session=self.session_id)
        return _from_node(node)

    def conflict_candidate(self, content: str, kind: str) -> Memory | None:
        """Might this record be updating an earlier one on the same topic?"""
        node = self.store.conflict_candidate(content, kind)
        return _from_node(node) if node is not None else None

    def bridge(self, src: str, dst: str, reason: str = "") -> tuple[Memory, Memory] | None:
        """Deliberately links two memories to each other.

        The automatic weave (`_weave`) looks at content similarity — it says
        "these resemble each other". The link here is different: the agent
        says **why** they are linked and that reason sits on the edge.

        In practice the difference is this: "3.71M yesterday, 3.72M today" as
        two separate records may not even resemble each other, but once linked
        as "the next day of the same measurement" a time series forms and
        association can walk that chain.
        """
        first, second = self.store.peek(src), self.store.peek(dst)
        if first is None or second is None:
            return None
        self.store.link(src, dst, weight=1.0, reason=reason.strip() or "ajan bağladı")
        return _from_node(first), _from_node(second)

    def series(self, tag: str, *, limit: int = 20) -> list[Memory]:
        """Records carrying the same tag, oldest to newest.

        A measurement's shape over time: every observation saved with the
        "btc-fiyat" tag arrives in order. This is the answer to "what happened
        from yesterday to today" — not recalling one by one and sorting in
        one's head.
        """
        wanted = tag.strip().lower()
        if not wanted:
            return []
        found = [
            _from_node(node)
            # The time series wants history: superseded versions come too.
            # That is the answer to "what happened from yesterday to today".
            for node in self.store.by_kind_any(limit=500, all_versions=True)
            if wanted in [t.lower() for t in node.tags]
        ]
        found.sort(key=lambda m: m.ts)
        return found[-limit:]

    def forget(self, memory_id: str) -> Memory | None:
        node = self.store.peek(memory_id)
        if node is None or not self.store.forget(memory_id):
            return None
        return _from_node(node, deleted=True)

    def memories(self, kind: str | None = None) -> list[Memory]:
        """Records, newest to oldest. For listing and the UI.

        The soul does NOT use this order (see `_live`): a list is shown to the
        user chronologically, but which eight records enter the system prompt
        is chosen by liveness, not freshness.
        """
        kinds = [kind] if kind else list(MEMORY_KINDS)
        out: list[Memory] = []
        for k in kinds:
            out.extend(_from_node(n) for n in self.store.by_kind(k, limit=200))
        return sorted(out, key=lambda m: m.ts, reverse=True)

    def _live(self, kind: str, limit: int) -> list[Memory]:
        """The most alive records of a kind — the order the soul picks.

        `by_kind` now sorts by activation; the only job here is NOT to BREAK
        that order. The old version went through `memories()`, which re-sorted
        by freshness for listing — so the soul carried the eight most recently
        written records regardless of how much they were used.
        """
        from ..recall import switches
        from ..recall.clock import parse

        if not switches.ACTIVE.activation:
            # Ablation: the pre-Phase-1 path — listing order (freshness).
            return self.memories(kind)[:limit]

        candidates = [_from_node(n) for n in self.store.by_kind(kind, limit=limit * 3)]
        now = self._clock()
        reserved = limit // 2

        def _fresh_correction(m: Memory) -> bool:
            if not m.supersedes:
                return False
            moment = parse(m.ts)
            return moment is not None and (now - moment).days < FRESH_CORRECTION_DAYS

        fresh = [m for m in candidates if _fresh_correction(m)][:reserved]
        chosen_ids = {m.id for m in fresh}
        # The cap cuts both ways: it RESERVES room for corrections and also
        # stops them from TAKING more than half the room. A week with eight
        # corrections must not turn the soul into a change list — the record
        # of who you are outlives the record of what changed.
        rest = [m for m in candidates
                if m.id not in chosen_ids and not _fresh_correction(m)]
        overflow = [m for m in candidates
                    if m.id not in chosen_ids and _fresh_correction(m)]
        selected = (fresh + rest)[:limit]
        if len(selected) < limit:
            selected += overflow[:limit - len(selected)]
        return selected

    def recall(self, query: str, *, kind: str | None = None, limit: int = 8,
               context: dict | None = None) -> list[Scored]:
        """Seeded from the index, spread over the links.

        The path the activation travelled stays in `last_trace`; once the tool
        layer writes it to the event log the UI can animate the recall.
        """
        # Explicit search is NOT FILTERED by context: context is only the job
        # of the spontaneous bootstrap. The model must be able to ask "what
        # did we do in kobyte", even while in the koru1000 session. The caller
        # supplies the context if it wants it.
        recollection = self.store.recall(query, limit=limit * 2, context=context)
        self.last_trace = recollection.trace

        hits = [n for n in recollection.hits if not kind or n.kind == kind][:limit]
        activation = {step.node: step.activation for step in recollection.trace}
        return [
            Scored(item=_from_node(node), score=activation.get(node.id, 0.0), matched=[])
            for node in hits
        ]

    # -- working memory -----------------------------------------------

    def push_goal(self, text: str) -> Goal:
        goal = Goal(id=_new_id("goal"), ts=self._now(), text=text.strip(), session_id=self.session_id)
        self._write("goals.jsonl", goal)
        self._goals[goal.id] = goal
        return goal

    def set_goal_status(self, goal_id: str, status: str, note: str = "") -> Goal | None:
        if status not in GOAL_STATES:
            raise ValueError(f"Bilinmeyen hedef durumu: {status}")
        goal = self._goals.get(goal_id)
        if goal is None:
            return None
        updated = Goal(**{**asdict(goal), "status": status, "ts": self._now(), "note": note})
        self._write("goals.jsonl", updated)
        self._goals[goal_id] = updated
        return updated

    def goals(self, *, active_only: bool = True, all_sessions: bool = False) -> list[Goal]:
        """The goal ledger is the CONVERSATION's ledger, not the mind's.

        Live wound: at the end of the PDF conversation the agent saw a "home
        automation" goal opened in another conversation and started chatting
        about it — and the acceptance gate got into a "is it done" haggle
        over items from unrelated conversations. The default view is filtered
        to the active session; places that look at the whole mind, like the
        brain graph, ask for `all_sessions=True`.
        """
        items = list(self._goals.values())
        if active_only:
            items = [g for g in items if g.status == "active"]
        if not all_sessions:
            items = [g for g in items if g.session_id == self.session_id]
        return sorted(items, key=lambda g: g.ts)

    def goal_digest(self) -> str:
        """One-line summary of the active goals.

        The agent gets this back through the operator channel (role="system"),
        so it does not forget what it is trying to do in the middle of a long
        task.
        """
        active = self.goals()
        if not active:
            return ""
        lines = [f"{i}. {g.text}" for i, g in enumerate(active, 1)]
        return "Aktif hedefler:\n" + "\n".join(lines)

    # -- soul ----------------------------------------------------------

    def soul(self, persona: str = "", limit: int = SOUL_LIMIT) -> Soul:
        """The identity digest loaded at the start of a session.

        The agent finds this ready-made rather than by calling a tool — it
        should not have to "think about remembering" first in order to
        remember who it is.
        """
        return Soul(
            persona=persona.strip(),
            user=self._live("user", limit),
            preferences=self._live("preference", limit),
            lessons=self._live("lesson", limit),
            voice=self._live("voice", limit),
            procedures=self._live("procedure", limit),
            goals=self.goals(),
            sessions=self._session_count(),
            first_seen=self._first_seen(),
        )

    def _session_count(self) -> int:
        if not self.sessions_dir.is_dir():
            return 0
        return sum(1 for _ in self.sessions_dir.glob("*.jsonl"))

    def _first_seen(self) -> str:
        stems = sorted(p.stem for p in self.sessions_dir.glob("*.jsonl")) if self.sessions_dir.is_dir() else []
        if stems:
            return _stem_to_date(stems[0])
        oldest = min((m.ts for m in self.memories()), default="")
        return oldest[:10]

    # -- episodic ------------------------------------------------------

    def episodes(self, query: str, *, limit: int = 5, include_current: bool = False) -> list[Scored]:
        """Search across past sessions.

        The current session is excluded by default: it is already in the
        context, bringing it back does nothing but spend tokens.
        """
        pool = [
            ep
            for ep in self._scan_sessions()
            if include_current or ep.session_id != self.session_id
        ]
        return rank(
            query,
            pool,
            text_of=lambda e: e.searchable(),
            time_of=lambda e: e.started,
            limit=limit,
            now=self._clock(),
        )

    def episode(self, session_id: str) -> Episode | None:
        return next((e for e in self._scan_sessions() if e.session_id == session_id), None)

    def sessions(self, limit: int = 60) -> list[Episode]:
        """All past sessions, newest to oldest. The chat list uses this.

        Differs from `episodes` in having no query: browsing, not search. An
        empty session (single message, no digest) does not enter the list —
        opening something empty on click is not a good chat list.
        """
        # Helper (subagent) sessions do not enter the list: the user's chat
        # history is their own conversations — not the intermediate work of
        # helpers running in the background. Their logs stay on disk and they
        # are present in search.
        eps = [e for e in self._scan_sessions() if not e.child]
        eps.sort(key=lambda e: e.started, reverse=True)
        return eps[:limit]

    def transcript(self, session_id: str) -> list[dict[str, Any]]:
        """A session's conversation transcript: turns + the turn's TRACE.

        Alongside the text turns, thinking blocks and tool steps are returned
        too — so the strip visible in the live chat ("✻ Düşündü", step lines)
        does not vanish on reopen (live wound, 01.09: "files, thoughts, steps
        etc. don't come back"). An assistant turn carries these fields:

          text     what was said (may be empty: if the turn was cut by a tool)
          dusunme  that turn's reasoning (if any; a single text)
          adimlar  tool steps [{tool, ozet}] (if any)

        The harness's own notes are excluded. This is the root of a proven
        leak: the live stream was filtered by the hub (`_payload`), but the
        TRANSCRIPT was not — when a session was resumed or opened from
        history, inner nudges like "You wrote your plan but did not apply
        it…" fell into the chat as USER MESSAGES. The markers are already in
        the log (`internal`, `continuation`, `tool_results`); the only thing
        missing was looking at them here too.
        """
        path = self.sessions_dir / f"{session_id}.jsonl"
        if not path.is_file():
            return []
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        if mtime:
            cached = self._transcript_cache.get(session_id)
            if cached and cached[0] == mtime:
                return cached[1]
        out: list[dict[str, Any]] = []
        thoughts: list[str] = []
        steps: list[dict[str, str]] = []

        def _close_turn(text: str = "") -> None:
            """Attaches the accumulated trace (thinking + steps) to an assistant turn."""
            nonlocal thoughts, steps
            if not (text or thoughts or steps):
                return
            turn: dict[str, Any] = {"role": "assistant", "text": text}
            if thoughts:
                turn["dusunme"] = "\n\n———\n\n".join(thoughts)[:20000]
            if steps:
                turn["adimlar"] = steps[:200]
            out.append(turn)
            thoughts = []
            steps = []

        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if not (line := line.strip()):
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    role = event.get("role")
                    if role not in ("user", "assistant"):
                        continue
                    if _harness_note(event):
                        continue
                    content = event.get("content")
                    if role == "assistant":
                        thoughts.extend(_thinking_blocks(content))
                        steps.extend(_step_summaries(content))
                        text = "\n".join(_plain_text(content)).strip()
                        if text:
                            _close_turn(text)
                        continue
                    text = "\n".join(_plain_text(content)).strip()
                    if text:
                        # If an orphan trace precedes the new user utterance
                        # (turn was cut) it attaches to a textless assistant turn.
                        _close_turn()
                        out.append({"role": "user", "text": text})
        except OSError:
            return []
        _close_turn()
        if mtime:
            self._transcript_cache[session_id] = (mtime, out)
            # Do not grow without bound: the oldest entries are dropped
            # (search keeps 40).
            while len(self._transcript_cache) > 64:
                self._transcript_cache.pop(next(iter(self._transcript_cache)))
        return out

    # -- projects (chat folders) -------------------------------------------
    #
    # Attaching a conversation to a project: a navigation convenience, NOT a
    # memory. The assignment is a simple mapping file (session → project
    # name); the logs do not change. Memories still form separately from the
    # conversations.

    def _projects_path(self) -> Path:
        return self.sessions_dir / "_projects.json"

    def projects(self) -> dict[str, str]:
        """Session → project name mapping. Unassigned ones are absent."""
        path = self._projects_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def set_project(self, session_id: str, project: str) -> dict[str, str]:
        """Attaches a session to a project; an empty name removes the attachment."""
        with self._lock:
            mapping = self.projects()
            name = (project or "").strip()
            if name:
                mapping[session_id] = name
            else:
                mapping.pop(session_id, None)
            try:
                self.sessions_dir.mkdir(parents=True, exist_ok=True)
                self._projects_path().write_text(
                    json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            return mapping

    # -- session identity (name + tags) ------------------------------------
    #
    # Until now the title was derived from the first words of the digest:
    # cheap, but not a name the user chose. Someone looking for "where was
    # that CMS job?" is looking for the name they gave it.
    #
    # Name and tags live in `_oturumlar.json`, in the SAME pattern as
    # projects: a separate mapping file, never touching the raw logs. The log
    # must be immutable — memories are produced from it, and a hand-edited
    # name would mean rewriting history.

    def _meta_path(self) -> Path:
        return self.sessions_dir / "_oturumlar.json"

    def session_meta(self) -> dict[str, dict[str, Any]]:
        """Session → {ad, etiketler, path, model, provider}.

        Sessions without a record are absent. `path` is the working folder;
        `model`/`provider` the model specific to this chat (applied on switch).
        """
        path = self._meta_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            tags = value.get("etiketler")
            out[str(key)] = {
                "ad": str(value.get("ad") or ""),
                "etiketler": [str(e) for e in tags] if isinstance(tags, list) else [],
                "path": str(value.get("path") or "").strip(),
                "model": str(value.get("model") or "").strip(),
                "provider": str(value.get("provider") or "").strip(),
            }
        return out

    def set_session_meta(
        self,
        session_id: str,
        *,
        name: str | None = None,
        tags: list[str] | None = None,
        path: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Writes name / tags / folder / model; a field given as None is left untouched.

        An empty name falls back to the derived title. If everything is empty
        the record is deleted.
        """
        with self._lock:
            mapping = self.session_meta()
            record = mapping.get(session_id, {
                "ad": "", "etiketler": [], "path": "", "model": "", "provider": "",
            })
            if name is not None:
                record["ad"] = " ".join(str(name).split())[:80]
            if tags is not None:
                clean: list[str] = []
                for tag in tags:
                    flat = " ".join(str(tag).split()).strip().lower()[:24]
                    if flat and flat not in clean:
                        clean.append(flat)
                record["etiketler"] = clean[:8]
            if path is not None:
                record["path"] = str(path or "").strip()[:500]
            if model is not None:
                record["model"] = str(model or "").strip()[:120]
            if provider is not None:
                record["provider"] = str(provider or "").strip()[:40]

            if (record.get("ad") or record.get("etiketler")
                    or record.get("path") or record.get("model")
                    or record.get("provider")):
                mapping[session_id] = record
            else:
                mapping.pop(session_id, None)

            try:
                self.sessions_dir.mkdir(parents=True, exist_ok=True)
                self._meta_path().write_text(
                    json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            result = mapping.get(session_id, {
                "ad": "", "etiketler": [], "path": "", "model": "", "provider": "",
            })
        # Outside the lock: once a folder is attached, fill the project folder
        # too (like Cursor Repositories — conversations grouped under the
        # folder name). Do not overwrite a manually given project name.
        if path is not None:
            folder = str(path or "").strip()
            if folder and not self.projects().get(session_id):
                leaf = Path(folder).name.strip()[:80]
                if leaf:
                    self.set_project(session_id, leaf)
        return result

    def archive_session(self, session_id: str) -> dict[str, Any]:
        """Removes the session from the list; moves the log to sessions/.arsiv.

        No permanent deletion — the same idea as the .geri-donusum in the
        applications panel: a wrong click must be undoable. The open session
        is not moved (switch to another chat first); otherwise the running
        strip's log would be lost.
        """
        sid = str(session_id or "").strip()
        if not sid:
            return {"ok": False, "error": "geçersiz oturum"}
        if sid == self.session_id:
            return {"ok": False, "error": "açık sohbet arşivlenemez — önce başka birine geç"}
        src = self.sessions_dir / f"{sid}.jsonl"
        if not src.is_file():
            return {"ok": False, "error": "oturum bulunamadı"}
        with self._lock:
            dest_dir = self.sessions_dir / ".arsiv"
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / f"{sid}.jsonl"
                if dest.exists():
                    dest = dest_dir / f"{sid}-{uuid4().hex[:8]}.jsonl"
                try:
                    src.replace(dest)
                except PermissionError:
                    # Windows will not move an open file. The real cause was
                    # the log not being closed and that was fixed at the root
                    # (see desktop._switch); here there is also a single retry
                    # against the race: if the close was a moment late the
                    # user should not see an error.
                    import time
                    time.sleep(0.4)
                    src.replace(dest)
            except OSError as exc:
                return {"ok": False, "error": (
                    f"taşınamadı: {exc}. Dosya hâlâ açıksa sohbeti kapatıp "
                    "(başka bir sohbete geçip) yeniden dene.")}
            self._episode_cache.pop(sid, None)
            self._transcript_cache.pop(sid, None)
            meta = self.session_meta()
            if sid in meta:
                meta.pop(sid, None)
                try:
                    self._meta_path().write_text(
                        json.dumps(meta, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                except OSError:
                    pass
            projects = self.projects()
            if sid in projects:
                projects.pop(sid, None)
                try:
                    self._projects_path().write_text(
                        json.dumps(projects, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                except OSError:
                    pass
        return {"ok": True, "id": sid}

    # -- transcript search -------------------------------------------------

    def search_transcripts(
        self,
        query: str,
        *,
        limit: int = 40,
        per_session: int = 3,
    ) -> dict[str, list[dict[str, str]]]:
        """Searches for text INSIDE the session logs.

        Until now the panel's search box only filtered the title: the answer
        to "where did we talk about the stock-market scan" did not show up in
        the list because the phrase was not in the title, it was in the
        middle of the conversation.

        The limits are deliberate and for cheapness: only the LAST `limit`
        sessions are scanned (older ones have already been distilled into
        memories), at most `per_session` matches come back per session, and
        the lines are clipped. The aim is to answer "which conversation was
        it"; not to be a full-text search engine.
        """
        needle = " ".join((query or "").split()).lower()
        if len(needle) < 2:
            return {}

        found: dict[str, list[dict[str, str]]] = {}
        for episode in self.sessions()[:limit]:
            hits: list[dict[str, str]] = []
            for turn in self.transcript(episode.session_id):
                text = turn.get("text") or ""
                at = text.lower().find(needle)
                if at < 0:
                    continue
                hits.append({"role": turn.get("role", ""), "text": _surroundings(text, at, len(needle))})
                if len(hits) >= per_session:
                    break
            if hits:
                found[episode.session_id] = hits
        return found

    def clear_caches(self) -> int:
        """Drop the transcript and episode caches; returns how many entries went.

        Both caches are keyed by file mtime, so dropping them costs nothing
        but a re-parse on the next lookup — which is exactly why deep sleep
        (and local sleep, which takes no lock on the graph) may call this
        while nothing else may: it frees RAM without touching a single
        record. Roadmap 3.10.10.
        """
        with self._lock:
            dropped = len(self._episode_cache) + len(self._transcript_cache)
            self._episode_cache.clear()
            self._transcript_cache.clear()
        return dropped

    def _scan_sessions(self) -> list[Episode]:
        if not self.sessions_dir.is_dir():
            return []
        paths = sorted(self.sessions_dir.glob("*.jsonl"), reverse=True)[:MAX_SCANNED_SESSIONS]
        out: list[Episode] = []
        for path in paths:
            try:
                mtime = path.stat().st_mtime_ns
            except OSError:
                continue
            cached = self._episode_cache.get(path.stem)
            if cached and cached[0] == mtime:
                out.append(cached[1])
                continue
            episode = _digest_session(path)
            if episode is not None:
                self._episode_cache[path.stem] = (mtime, episode)
                out.append(episode)
        return out

    def links(self) -> list[tuple[str, str, float]]:
        """Association links between memories. The UI draws the network with this."""
        return self.store.links()

    def close(self) -> None:
        self.store.close()

    # -- writing -------------------------------------------------------

    def _write(self, filename: str, record: Any) -> None:
        path = self.dir / filename
        with self._lock, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


# ---------------------------------------------------------------------


def _load(path: Path, kind: type, into: dict[str, Any]) -> None:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not (line := line.strip()):
                continue
            try:
                record = kind(**json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue  # field from a newer version or a half-written line: skip
            into[record.id] = record  # a later record supersedes the earlier one



def _from_node(node, *, deleted: bool = False) -> Memory:
    """Converts a store record into the legacy Memory shape.

    The UI, soul and graph layers expect this shape; it is converted in a
    single place so the store change does not leak into them.
    """
    return Memory(
        id=node.id,
        ts=node.created,
        kind=node.kind,
        title=node.title,
        content=node.body,
        tags=list(node.tags),
        session_id=node.session,
        deleted=deleted,
        hot=bool(getattr(node, "hot", True)),
        context=dict(getattr(node, "context", {}) or {}),
        supersedes=str(getattr(node, "supersedes", "") or ""),
    )

def _stem_to_date(stem: str) -> str:
    """20260822T203420Z -> 2026-08-22. An unrecognised format is left as is."""
    digits = stem[:8]
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return stem


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "(başlıksız)")


def _digest_session(path: Path) -> Episode | None:
    """Reduces a session log to a single searchable digest."""
    started = ""
    turns = 0
    tools: list[str] = []
    fragments: list[str] = []
    child = False

    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not (line := line.strip()):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                started = started or event.get("ts", "")

                if event.get("kind") == "meta":
                    if event.get("content") == "tool_start":
                        name = event.get("meta", {}).get("tool")
                        if name and name not in tools:
                            tools.append(name)
                    # The birth note in the helper's own log: the `parent`
                    # field exists only in the child (the matching note in the
                    # main agent writes `session`).
                    elif (event.get("content") == "subagent_start"
                          and event.get("meta", {}).get("parent")):
                        child = True
                    continue

                role = event.get("role")
                if role == "assistant":
                    turns += 1
                if role not in ("user", "assistant"):
                    continue
                fragments.extend(_text_of(event.get("content")))
    except OSError:
        return None

    if not fragments:
        return None

    return Episode(
        session_id=path.stem,
        started=started,
        turns=turns,
        tools=tools,
        digest=" ".join(fragments)[:8000],
        child=child,
    )


# The log markers of turns the user did not write. All three say the same
# thing: the harness put this line here, it must not look like a message in
# the chat.
HARNESS_MARKERS = ("internal", "continuation", "tool_results")


def _surroundings(text: str, at: int, length: int, span: int = 60) -> str:
    """Extracts a readable quote from around the match.

    Returning the whole turn would turn the list into a wall; the searched
    word must appear with its context so that "which conversation was it" is
    understood at a glance.
    """
    flat = " ".join(text.split())
    # Whitespace normalisation shifts the index; re-finding the quote in the
    # normalised text is more accurate than a sliding window.
    pos = flat.lower().find(text[at:at + length].strip().lower())
    if pos < 0:
        pos = 0
    start = max(0, pos - span)
    end = min(len(flat), pos + length + span)
    return ("…" if start else "") + flat[start:end].strip() + ("…" if end < len(flat) else "")


def _harness_note(event: dict[str, Any]) -> bool:
    """Is this log line the harness's own note?

    They are written like user turns (some HAVE to go through the user
    channel — see `Session.add_continuation_note`), but the user did not
    write them; shown in the transcript the user would read a sentence that
    never came out of their mouth.
    """
    meta = event.get("meta")
    if not isinstance(meta, dict):
        return False
    return any(meta.get(marker) for marker in HARNESS_MARKERS)


def _plain_text(content: Any) -> list[str]:
    """Text blocks only — tool calls and thinking excluded.

    Differs from `_text_of`: that one also turns tool_use into text for
    search; here a conversation transcript to be shown to a human is wanted,
    so only the actual words are taken.
    """
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [str(b.get("text", "")) for b in content
            if isinstance(b, dict) and b.get("type") == "text"]


def _thinking_blocks(content: Any) -> list[str]:
    """Thinking blocks in assistant content — for the transcript strip.

    The Anthropic shape is `{"type": "thinking", "thinking": ...}`; the
    translator layer may also write into the `text` field, both are checked.
    """
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "thinking":
            text = str(b.get("thinking") or b.get("text") or "").strip()
            if text:
                out.append(text)
    return out


# Input fields looked for in the step summary, in order of meaningfulness:
# command and path are the pair that tell a human the most.
_STEP_FIELDS = ("command", "path", "query", "url", "action", "name", "text")


def _step_summaries(content: Any) -> list[dict[str, str]]:
    """Tool calls in assistant content — the step lines of the transcript strip.

    NOT the whole input, a one-line summary is returned: carrying the huge
    content of a `write_file` call in the transcript would bloat the page by
    megabytes; it is enough that "what was done" reads like in the live strip.
    """
    if not isinstance(content, list):
        return []
    out: list[dict[str, str]] = []
    for b in content:
        if not isinstance(b, dict) or b.get("type") != "tool_use":
            continue
        inputs = b.get("input")
        summary = ""
        if isinstance(inputs, dict):
            for field_name in _STEP_FIELDS:
                value = inputs.get(field_name)
                if isinstance(value, str) and value.strip():
                    summary = " ".join(value.split())
                    break
        if len(summary) > 160:
            summary = summary[:160].rstrip() + "…"
        out.append({"tool": str(b.get("name") or ""), "ozet": summary})
    return out


def _text_of(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            out.append(str(block.get("text", "")))
        elif block.get("type") == "tool_use":
            out.append(f"{block.get('name', '')} {json.dumps(block.get('input', {}), ensure_ascii=False)}")
    return out


def render_hits(hits: list[Scored], *, text_of, header: str) -> str:
    if not hits:
        return f"{header}: sonuç yok."
    lines = [header + ":"]
    for hit in hits:
        lines.append(excerpt(text_of(hit.item), hit.matched))
    return "\n\n".join(lines)
