"""Tests for the parts of the harness that can break silently.

Every test here corresponds to a bug that is hard to notice in production:
a missing tool_result (400), a missed cache (silent cost), unpruned images
(context explosion), a skipped permission gate (security).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.context import place_breakpoints, prune_images
from dornick.events import EventLog
from dornick.permissions import Decision, PermissionEngine
from dornick.session import Session, cancelled_result
from dornick.tools import ToolContext, ToolRegistry, ToolResult, execute, object_schema
from dornick.tools.base import ToolSpec


# -- event log ---------------------------------------------------------


def test_event_log_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    with EventLog(path) as log:
        log.message("user", [{"type": "text", "text": "merhaba"}])
        log.note("tool_start", tool="shell")

    reopened = EventLog(path)
    assert len(reopened) == 2
    assert len(reopened.messages()) == 1
    assert reopened.notes("tool_start")[0].meta["tool"] == "shell"
    # The sequence number must continue where it left off, not collide.
    assert reopened.append("meta", content="x").seq == 2
    reopened.close()


def test_meta_keys_may_shadow_event_fields(tmp_path: Path) -> None:
    """Had meta been **kwargs, a field named "kind" would have dropped the call with a TypeError.

    Mind records really do send "kind"; this blew up in production on every
    memory write and the executor's broad except swallowed the error.
    """
    log = EventLog(tmp_path / "s.jsonl")
    event = log.note("mind_write", kind="preference", role="x", content="y")

    assert event.content == "mind_write"
    assert event.meta == {"kind": "preference", "role": "x", "content": "y"}
    log.close()


# -- session / interrupt safety ---------------------------------------


def _session(tmp_path: Path) -> Session:
    return Session(EventLog(tmp_path / "s.jsonl"), "test")


def test_pending_tool_uses_finds_unanswered(tmp_path: Path) -> None:
    s = _session(tmp_path)
    s.add_user_text("iki şey yap")
    s.add_assistant(
        [
            {"type": "tool_use", "id": "a", "name": "shell", "input": {"command": "ls"}},
            {"type": "tool_use", "id": "b", "name": "shell", "input": {"command": "pwd"}},
        ]
    )
    s.add_tool_results([{"type": "tool_result", "tool_use_id": "a", "content": "ok"}])

    pending = s.pending_tool_uses()
    assert [p.id for p in pending] == ["b"]

    # Once the cancellation result is injected nothing must be left open.
    s.add_tool_results([cancelled_result(p.id) for p in pending])
    assert s.pending_tool_uses() == []


def test_system_note_needs_user_turn_first(tmp_path: Path) -> None:
    s = _session(tmp_path)
    s.add_system_note("ilk mesaj olamaz")
    assert s.messages() == []

    s.add_user_text("selam")
    s.add_system_note("bu geçerli")
    assert [m["role"] for m in s.messages()] == ["user", "system"]


def test_resume_opens_the_last_used_session(tmp_path: Path) -> None:
    """`--resume` must continue the last USED session, not the last OPENED one.

    When the user went back to an old conversation from the history and
    carried on from there, sorting by name threw them into a completely
    different conversation on restart — this happened live, exactly so.
    """
    import os

    old = tmp_path / "20260827T095449Z.jsonl"   # opened first, used LAST
    new = tmp_path / "20260827T101349Z.jsonl"   # opened later, abandoned
    for path in (old, new):
        path.write_text("", encoding="utf-8")
    os.utime(new, (1_700_000_000, 1_700_000_000))
    os.utime(old, (1_700_003_600, 1_700_003_600))

    session = Session.latest(tmp_path)
    assert session is not None
    assert session.id == "20260827T095449Z"

    empty = tmp_path / "bos"
    empty.mkdir()
    assert Session.latest(empty) is None, "must not blow up on an empty folder"


# -- cache breakpoints ------------------------------------------------


def _msg(role: str, n: int) -> dict:
    return {"role": role, "content": [{"type": "text", "text": f"b{i}"} for i in range(n)]}


def test_breakpoints_respect_limit_and_cover_tail() -> None:
    messages = [_msg("user", 8) for _ in range(10)]  # 80 blocks
    place_breakpoints(messages, limit=3, stride=15)

    marked = [i for i, m in enumerate(messages) if "cache_control" in m["content"][-1]]
    assert len(marked) <= 3
    # The last message must always be marked: that is where the newly
    # written prefix is.
    assert len(messages) - 1 in marked


def test_breakpoint_gap_stays_under_lookback_window() -> None:
    """If the gap between two breakpoints exceeds 20 blocks the cache silently misses."""
    messages = [_msg("user", 4) for _ in range(12)]  # 48 blocks
    place_breakpoints(messages, limit=3, stride=15)

    cumulative, gaps, last = 0, [], 0
    for m in messages:
        cumulative += len(m["content"])
        if "cache_control" in m["content"][-1]:
            gaps.append(cumulative - last)
            last = cumulative

    assert gaps, "no breakpoint was placed"
    assert max(gaps) <= 20


def test_breakpoints_are_cleared_before_replacement() -> None:
    messages = [_msg("user", 5) for _ in range(6)]
    place_breakpoints(messages, limit=3, stride=15)
    messages.append(_msg("assistant", 5))
    place_breakpoints(messages, limit=3, stride=15)

    total = sum(
        1 for m in messages for b in m["content"] if "cache_control" in b
    )
    assert total <= 3, "old breakpoints were not cleared"


# -- image pruning ----------------------------------------------------


def _image() -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}}


def test_prune_images_keeps_only_recent() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": f"t{i}", "content": [_image()]}
            ],
        }
        for i in range(5)
    ]
    prune_images(messages, keep=2)

    kinds = [m["content"][0]["content"][0]["type"] for m in messages]
    assert kinds == ["text", "text", "text", "image", "image"]


# -- permissions ------------------------------------------------------


def _spec(name: str, mutates: bool) -> ToolSpec:
    async def handler(args, ctx):  # pragma: no cover - never called
        return ToolResult("ok")

    return ToolSpec(name, "d", object_schema({}), handler, mutates=mutates)


def test_deny_beats_allow() -> None:
    engine = PermissionEngine("yolo", allow=["*"], deny=["shell:rm *"])
    decision, _ = engine.evaluate(_spec("shell", True), {"command": "rm -rf /"})
    assert decision is Decision.DENY


def test_plan_mode_blocks_mutation_only() -> None:
    engine = PermissionEngine("plan", allow=[], deny=[])
    assert engine.evaluate(_spec("write_file", True), {"path": "a"})[0] is Decision.DENY
    assert engine.evaluate(_spec("read_file", False), {"path": "a"})[0] is Decision.ALLOW


def test_auto_mode_asks_only_for_mutation() -> None:
    engine = PermissionEngine("auto", allow=[], deny=[])
    assert engine.evaluate(_spec("shell", True), {"command": "ls"})[0] is Decision.ASK
    assert engine.evaluate(_spec("list_dir", False), {"path": "."})[0] is Decision.ALLOW


def test_remember_allow_creates_matching_rule() -> None:
    engine = PermissionEngine("ask", allow=[], deny=[])
    spec = _spec("shell", True)
    engine.remember_allow(spec, {"command": "git status"})
    assert engine.evaluate(spec, {"command": "git status"})[0] is Decision.ALLOW


# -- executor ---------------------------------------------------------


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(config=config, session=_session(tmp_path), cancel=asyncio.Event())


async def test_every_call_gets_a_result_even_when_unknown_or_denied(ctx: ToolContext) -> None:
    """A missing tool_result drops the next request with a 400."""
    from dornick.session import PendingToolUse

    registry = ToolRegistry()

    @registry.tool("ok_tool", "çalışır", object_schema({}))
    async def _ok(args, _ctx):
        return ToolResult("tamam")

    @registry.tool("bad_tool", "patlar", object_schema({}), mutates=True)
    async def _bad(args, _ctx):
        raise RuntimeError("beklenmedik")

    calls = [
        PendingToolUse("1", "ok_tool", {}),
        PendingToolUse("2", "yok_boyle_arac", {}),
        PendingToolUse("3", "bad_tool", {}),
    ]

    async def approve(spec, args):
        return False  # bad_tool will be denied

    blocks = await execute(
        calls,
        registry=registry,
        permissions=PermissionEngine("ask", allow=["ok_tool:*"], deny=[]),
        ctx=ctx,
        approve=approve,
    )

    assert [b["tool_use_id"] for b in blocks] == ["1", "2", "3"]
    assert blocks[0]["is_error"] is False
    assert "yok_boyle_arac" in blocks[1]["content"]  # unknown tool: instructive error
    assert blocks[2]["is_error"] is True  # denied


async def test_handler_exception_does_not_kill_the_loop(ctx: ToolContext) -> None:
    from dornick.session import PendingToolUse

    registry = ToolRegistry()

    @registry.tool("boom", "patlar", object_schema({}))
    async def _boom(args, _ctx):
        raise ValueError("içeride bir şey ters gitti")

    blocks = await execute(
        [PendingToolUse("1", "boom", {})],
        registry=registry,
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    assert blocks[0]["is_error"] is True
    assert "ValueError" in blocks[0]["content"]


async def test_stop_cancels_a_pending_approval(ctx: ToolContext) -> None:
    """Stop while a permission card is open: the turn does not hang on the approval wait.

    Live wound (01.09): when the card went unanswered nothing, Stop
    included, could rescue the turn — the wait is now raced against the
    cancel event.
    """
    from dornick.session import PendingToolUse

    registry = ToolRegistry()
    ran = False

    @registry.tool("sorulan", "sorar", object_schema({}), mutates=True)
    async def _asked(args, _ctx):
        nonlocal ran
        ran = True
        return ToolResult("olmamalıydı")

    async def unanswered_card(spec, args):
        await asyncio.sleep(3600)
        return True

    async def stop_soon():
        await asyncio.sleep(0.05)
        ctx.cancel.set()

    stop = asyncio.ensure_future(stop_soon())
    blocks = await asyncio.wait_for(
        execute(
            [PendingToolUse("1", "sorulan", {})],
            registry=registry,
            permissions=PermissionEngine("ask", allow=[], deny=[]),
            ctx=ctx,
            approve=unanswered_card,
        ),
        timeout=5,
    )
    await stop
    assert not ran, "an unapproved call must not run"
    assert blocks[0]["tool_use_id"] == "1"
    assert blocks[0]["is_error"] is True


# -- missing premise ---------------------------------------------------
#
# To the question "Yarın hava nasıl?" the model assumed Istanbul and
# answered. The user may not be in Istanbul and the assumption was hidden
# inside the answer: it was not even clear that it was wrong.


def test_the_prompt_says_what_day_it_is(tmp_path: Path) -> None:
    """The answer to a "tomorrow" question depends on what today is, and the
    model could not learn it from anywhere."""
    from datetime import datetime

    from dornick import prompt as builder

    text = builder._environment(Config.load(tmp_path))
    today = datetime.now().astimezone()

    assert f"{today:%d.%m.%Y}" in text
    assert builder.DAYS[today.weekday()] in text


def test_the_prompt_says_where_the_machine_is(tmp_path: Path) -> None:
    """The time zone tells the country — not the city. The distinction is
    deliberate: as much as the machine knows is given, the rest is asked."""
    from dornick import prompt as builder

    text = builder._environment(Config.load(tmp_path))
    assert "Saat dilimi:" in text and "UTC" in text


def test_the_day_name_is_turkish_whatever_the_system_language(tmp_path: Path) -> None:
    """`strftime("%A")` depends on the system language and can come back in
    English; we do not want mixed languages in the prompt."""
    from dornick import prompt as builder

    assert builder.DAYS[0] == "Pazartesi"
    assert all(day.isalpha() for day in builder.DAYS)


def test_the_prompt_forbids_inventing_a_missing_premise() -> None:
    """Writing a separate rule for every question does not scale; there is one principle."""
    from dornick import prompt as builder

    assert "Eksik öncül" in builder.IDENTITY
    # Three steps: look into your mind, find it yourself, if you can't, ask.
    assert "mind_recall" in builder.IDENTITY
    assert "tek cümlelik bir soru sor" in builder.IDENTITY


def test_the_prompt_forbids_the_youre_welcome_loop() -> None:
    """Thanks / okay / let me see → the 'you're welcome' assistant loop."""
    from dornick import prompt as builder

    assert "Rica ederim" in builder.IDENTITY
    assert "tamamdır" in builder.IDENTITY
    assert "cevap yazma" in builder.IDENTITY
    assert "Rica ederim" in builder.LEAN_IDENTITY


def test_the_prompt_asks_before_forgetting_memories_tied_to_a_deleted_device() -> None:
    """When a device was deleted the memories silently stayed; the user had
    to say 'delete from memory too'. Asking is the rule: keep or delete?"""
    from dornick import prompt as builder

    assert "dursun mu, sileyim mi" in builder.IDENTITY


def test_big_open_ended_work_must_lead_with_a_visible_plan() -> None:
    """Proven skip: in a 55-minute job the first message came without a plan.

    The rule is no longer a suggestion but an ordering rule: the FIRST
    thing written is the module plan and the acceptance criteria; "the plan
    in your head does not count". In a long run the narration rhythm is
    binding too — a one-sentence status to the user at every milestone.
    """
    from dornick import prompt as builder

    flat = " ".join(builder.IDENTITY.split())   # independent of line breaks
    assert "İLK yazdığın şey modül planı ve kabul ölçütleridir" in flat
    assert "planı yazmadan koda başlama" in flat
    assert "kafandaki plan sayılmaz" in flat
    # Narration rhythm: the user must not stare at minutes of silence.
    assert "her kilometre taşında kullanıcıya bir cümle durum yaz" in flat


def test_the_long_run_checkpoint_also_addresses_the_user() -> None:
    """The checkpoint speaks to the user and end_turn is free once accepted."""
    from dornick.loop import CHECKPOINT_NOTE

    assert "kullanıcıya da yaz" in CHECKPOINT_NOTE
    assert "end_turn" in CHECKPOINT_NOTE
    assert "iş bitmeden durma" not in CHECKPOINT_NOTE


# -- trimming old tool payloads ----------------------------------------


def _talk(n_old: int, big: str):
    """n_old old messages + 6 fresh messages; the first has a huge write_file turn."""
    from copy import deepcopy

    old = [
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "c1", "name": "write_file",
             "input": {"path": "site/index.html", "content": big}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "c1", "content": big}]},
    ] * max(1, n_old // 2)
    fresh = [{"role": "user", "content": [{"type": "text", "text": f"m{i}"}]}
             for i in range(6)]
    return deepcopy(old + fresh)


def test_old_tool_payloads_are_trimmed_but_the_tail_is_not() -> None:
    """Measured wound: the whole HTML entered the history in the write_file
    argument and went out again with EVERY SUBSEQUENT request (~12-14k of a
    51.6k prompt). The file is on disk; a trace in the history suffices —
    it can be opened with read_file if needed."""
    from dornick.context import TRIM_TOOL_CHARS, prune_tool_payloads

    big = "x" * 10_000
    messages = _talk(2, big)
    fresh_big = {"role": "assistant", "content": [
        {"type": "tool_use", "id": "c9", "name": "write_file",
         "input": {"path": "yeni.html", "content": big}}]}
    messages.append(fresh_big)

    prune_tool_payloads(messages)

    trimmed = messages[0]["content"][0]["input"]["content"]
    assert len(trimmed) < TRIM_TOOL_CHARS + 200
    assert "kısaltıldı" in trimmed
    assert trimmed.startswith("x")            # the head is kept
    assert trimmed.endswith("x")              # the tail is kept
    # Small arguments are untouched: the path stays as it is.
    assert messages[0]["content"][0]["input"]["path"] == "site/index.html"
    # The result block got shorter too.
    assert "kısaltıldı" in messages[1]["content"][0]["content"]
    # The FRESH huge content at the tail stays as it is.
    assert messages[-1]["content"][0]["input"]["content"] == big


def test_trimming_is_deterministic_for_the_cache() -> None:
    """The same history must come down to the same bytes on every request —
    so the prefix cache keeps holding from request to request."""
    import json

    from dornick.context import prune_tool_payloads

    big = "y" * 8_000
    a, b = _talk(4, big), _talk(4, big)
    prune_tool_payloads(a)
    prune_tool_payloads(b)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_browser_dumps_are_trimmed_more_aggressively() -> None:
    """Browser HTML dumps outside keep=2 are trimmed aggressively."""
    from dornick.context import TRIM_BROWSER_CHARS, prune_tool_payloads

    html = "<html>" + ("z" * 5_000) + "</html>"
    messages = [
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "b1", "content": html}]},
        {"role": "assistant", "content": "ok1"},
        {"role": "user", "content": "devam"},
        {"role": "assistant", "content": "ok2"},
        {"role": "user", "content": "son"},
        {"role": "assistant", "content": "ok3"},
    ]
    prune_tool_payloads(messages)
    trimmed = messages[0]["content"][0]["content"]
    assert len(trimmed) < TRIM_BROWSER_CHARS + 200
    assert "kısaltıldı" in trimmed


def test_trimming_flows_through_prepare() -> None:
    """Really wired into the policy line: the prepared request shrinks, the
    raw log does not change."""
    from dornick.config import ContextConfig
    from dornick.context import ContextPolicy
    from dornick.prompt import SystemPrompt

    big = "z" * 20_000
    messages = _talk(2, big)
    before = sum(len(str(m)) for m in messages)

    policy = ContextPolicy(ContextConfig())
    prepared = policy.prepare(SystemPrompt(core="test", identity=""), messages)

    after = sum(len(str(m)) for m in prepared.messages)
    assert after < before * 0.4               # serious shrinkage
    # The raw history (the truth of the event log) is untouched.
    assert messages[0]["content"][0]["input"]["content"] == big


def test_prompt_tells_the_model_to_match_the_user_language() -> None:
    """The model must not answer in Turkish just because the instructions are in Turkish.

    Live wound (02.09): with the UI language English and the user writing
    in English the agent answered in Turkish — because the whole system
    prompt is Turkish. The rule is part of the voice: in the identity
    block, the first item under the "how do you speak" heading.
    """
    from dornick import prompt as builder

    identity = builder.IDENTITY
    assert "KULLANICININ YAZDIĞI DİLDE" in identity
    # The rule's place matters: it must be at the head of the voice section
    # to carry weight.
    how = identity.find("Nasıl konuşursun:")
    lang = identity.find("KULLANICININ YAZDIĞI DİLDE")
    real = identity.find("Gerçek biri gibi")
    assert how < lang < real, "the language rule must be at the head of the voice section"
    # Interim narration and produced files are in the same language too.
    assert "ara anlatım" in identity and "dosyaların içeriği" in identity


def test_turn_carries_a_language_reminder(tmp_path: Path) -> None:
    """The reply-language reminder goes to THIS TURN'S REQUEST, not the session log.

    Live wound (02.09): because the whole system prompt and most memories
    are Turkish the model answered in Turkish even to someone writing in
    English. The reminder is placed where the model reads last. NOT writing
    it to the log is a must: the "one system note per turn" quota belongs
    to the recall note (`_prime_recall`) — the tests caught this in a
    regression.
    """
    from types import SimpleNamespace

    from dornick.loop import Agent

    session = _session(tmp_path)
    session.add_user_text("baslangic")

    agent = Agent.__new__(Agent)
    agent.session = session

    # English input → English reminder, without touching the log.
    before = len(session.messages())
    agent._language_note("Please write a short report about solar batteries.")
    assert len(session.messages()) == before, "must not be written to the log"

    prepared = SimpleNamespace(messages=[])
    agent._add_language_reminder(prepared)
    assert prepared.messages and prepared.messages[-1]["role"] == "system"
    assert "SAME language" in str(prepared.messages[-1]["content"])

    # Turkish input → Turkish reminder.
    agent._language_note("Bana güneş pilleri hakkında kısa bir rapor yazar mısın?")
    prepared2 = SimpleNamespace(messages=[])
    agent._add_language_reminder(prepared2)
    assert "TÜRKÇE" in str(prepared2.messages[-1]["content"])

    # No inference on a very short input: nothing is added.
    agent._language_note("ok")
    prepared3 = SimpleNamespace(messages=[])
    agent._add_language_reminder(prepared3)
    assert prepared3.messages == []
