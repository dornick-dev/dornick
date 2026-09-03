"""Permission engine.

Critical design decision: this gate is **outside the loop**. It is not
something the model approves, it is something the harness enforces. Bury
the policy in the agent's logic and the model becomes able to talk it
around.

Rule format: "tool_name:argument-pattern" (fnmatch).
    "shell:git *"     git commands
    "shell:*"         every shell command
    "write_file:*"    every file write
    "*"               everything

Deny always wins.
"""

from __future__ import annotations

import json
from enum import Enum
from fnmatch import fnmatch
from typing import Any, TYPE_CHECKING

from . import guards

if TYPE_CHECKING:  # pragma: no cover
    from .tools.base import ToolSpec

# Arguments that represent "what a tool targets", in priority order.
# `komut`: the field of the `kos` tool that overrides detection. Without it
# here a hand-given command would appear to the gate as `path` — the rule
# would match the folder, not the command, and a "run tests in that folder"
# permission would become permission for ANY command in that folder.
SUBJECT_KEYS = ("command", "komut", "path", "url", "target", "query", "pattern")


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PermissionEngine:
    def __init__(self, mode: str, allow: list[str], deny: list[str]) -> None:
        if mode not in ("auto", "ask", "plan", "yolo"):
            raise ValueError(f"Bilinmeyen izin modu: {mode}")
        self.mode = mode
        self.allow = list(allow)
        self.deny = list(deny)

    @classmethod
    def from_config(cls, cfg: Any) -> PermissionEngine:
        return cls(cfg.mode, cfg.allow, cfg.deny)

    def evaluate(self, spec: "ToolSpec", args: dict[str, Any]) -> tuple[Decision, str]:
        subject = f"{spec.name}:{describe(args)}"

        # Fixed guards BEFORE EVERYTHING: even the user's allow/yolo
        # loosening cannot open these. Secret files, writes to mode/gate
        # files and startup persistence — opening them collapses the
        # security model.
        mutation = bool(spec.mutates) and not _safe_action(spec, args)
        if (reason := guards.sabit_ret(spec.name, mutation, args)) is not None:
            # The reason travels in the rule string (with a sentinel prefix):
            # the executor shows it to the model as-is instead of the generic
            # "blocked by policy" — the model should know what it cannot do
            # and why.
            return Decision.DENY, "sabit:koruma:" + reason

        if rule := _first_match(subject, self.deny):
            return Decision.DENY, rule

        if rule := _first_match(subject, self.allow):
            return Decision.ALLOW, rule

        if self.mode == "yolo":
            return Decision.ALLOW, "mode:yolo"

        # The agent writing to its OWN notebook does not count as a mutation:
        # opening a confirmation window for `mind_memory save` (or flatly
        # denying it in plan mode) was stalling the mind — while the
        # conversation transcript flowed, persistent memory wrote no
        # preference/lesson/fact for two days. Deleting (forget) is still a
        # mutation and stays gated.
        mutating = spec.mutates and not _safe_action(spec, args)

        if self.mode == "plan":
            if mutating:
                return Decision.DENY, "mode:plan"
            return Decision.ALLOW, "mode:plan"

        if self.mode == "auto":
            return (Decision.ASK if mutating else Decision.ALLOW), "mode:auto"

        # mode == "ask": everything is asked. The ONE exception is actions
        # the tool explicitly declares safe (the agent writing to its own
        # notebook) — otherwise every memory becomes a confirmation window
        # and the model stops saving. Real work like reading/writing keeps
        # being asked here exactly as before.
        if _safe_action(spec, args):
            return Decision.ALLOW, "mode:ask"
        return Decision.ASK, "mode:ask"

    def remember_allow(self, spec: "ToolSpec", args: dict[str, Any]) -> str:
        """The rule produced when the user says 'don't ask again'."""
        rule = f"{spec.name}:{describe(args)}" if describe(args) else f"{spec.name}:*"
        if rule not in self.allow:
            self.allow.append(rule)
        return rule


def describe(args: dict[str, Any]) -> str:
    """Extracts a matchable one-line subject from the arguments."""
    for key in SUBJECT_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    if not args:
        return ""
    return json.dumps(args, ensure_ascii=False, sort_keys=True)[:200]


def _safe_action(spec: "ToolSpec", args: dict[str, Any]) -> bool:
    """Is this call an action the tool declared it may perform unconfirmed?

    On multi-action tools (an `action` enum) a single `mutates` flag is too
    coarse: `mind_memory save` is the agent writing to its own notebook,
    `forget` is permanent deletion. Putting both in the same basket stalled
    the mind.
    """
    safe = getattr(spec, "safe_actions", ()) or ()
    if not safe:
        return False
    return str(args.get("action") or "") in safe


def _first_match(subject: str, rules: list[str]) -> str | None:
    tool = subject.split(":", 1)[0]
    for rule in rules:
        if rule == "*" or fnmatch(subject, rule) or fnmatch(tool, rule):
            return rule
    return None
