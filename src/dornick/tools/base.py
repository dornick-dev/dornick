"""Tool types and the registry.

The tool schema is the only documentation the model ever sees. Two design
rules:

  1. Few, powerful tools. Dozens of flat tools drown the model; group
     related actions under a single `action` enum.
  2. Errors must teach. Not "element not found" but "element not found —
     the screen may have changed, take a fresh capture". The model corrects
     itself on the next turn; you win a turn.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Config
    from ..session import Session

Block = dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    """The result of one tool call.

    content may be plain text or a list of blocks (a block list is required
    for tools that return images).
    """

    content: str | list[Block]
    is_error: bool = False
    # Extra information that does not go to the model — it goes to the log
    # and to the mind UI.
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def error(cls, message: str, **detail: Any) -> ToolResult:
        return cls(content=message, is_error=True, detail=detail)

    def to_block(self, tool_use_id: str) -> Block:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": self.content,
            "is_error": self.is_error,
        }


class JobFailed(Exception):
    """A background job finished but failed.

    The message is the user report — not a raw traceback. `_job_round`
    turns this into the `hata` status; otherwise the run would look
    'completed'.
    """


@dataclass(slots=True)
class ToolContext:
    config: "Config"
    session: "Session"
    # User interrupt. Long-running tools should poll this periodically.
    cancel: asyncio.Event

    # Sub-agent launcher. The loop wires it; the tool layer does not know
    # `Agent` (knowing it would be an import cycle) and when None the `task`
    # tool is not registered at all.
    spawn: Callable[[str, str, str], Awaitable[str]] | None = None

    # Background helper launcher: returns the ledger record (handle) right
    # away, the job runs in the background and the main agent is notified
    # when it finishes. When None the `task` tool's `arka_plan` option does
    # not work.
    spawn_bg: Callable[[str, str, str], Any] | None = None

    # Late message to a running or finished helper (task_say) and the
    # helpers' status summary (task_status). The loop provides them; None
    # inside a sub-agent.
    child_say: Callable[[str, str], tuple[bool, str]] | None = None
    child_status: Callable[[str], str] | None = None

    # Moves a long but FINITE job (build, install, test run) to the
    # background: writes it to the ledger, and when it finishes its output
    # is reported to the agent with a harness note. Tools like `shell` use
    # this for their `arka_plan` option. The runner receives its own cancel
    # flag; the main interrupt sets all of them.
    job_bg: Callable[[str, Callable[[asyncio.Event], Awaitable[str]]], Any] | None = None

    # Scheduled task ledger. The loop provides it; when None the `schedule`
    # tool declares itself unavailable.
    schedule: Any = None

    # Automation graph runner (workflow run). When None the tool returns a stub.
    run_workflow: Callable[[str], Awaitable[Any]] | None = None

    # The local camera's always-open buffer. Frames sit here and do not go
    # to the model on their own; the `look` tool fetches them on request.
    lens: Any = None

    # The always-listening ear. The `senses` tool mutes through this — an
    # agent that could not close its ear kept listening while saying "I'm
    # off".
    ear: Any = None

    # Watcher of the network cameras. "Don't watch me" covers them too.
    watcher: Any = None

    # HUD/chat camera switch: True turns it on, False releases the device.
    camera_power: Callable[[bool], str] | None = None

    # The workshop opens on first access: creating the folder is a side
    # effect and should happen when it is really needed, not every time a
    # ToolContext is built.
    _sandbox: Any = None

    @property
    def workspace(self) -> Path:
        return self.config.workspace

    @property
    def sandbox(self) -> Any:
        """The agent's own folder. Writing is free only here."""
        if self._sandbox is None:
            self._sandbox = self.config.open_sandbox()
        return self._sandbox


Handler = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler
    # Does it change system state? The permission engine looks at this.
    mutates: bool = False
    # Actions (the `action` field) that do NOT require approval even when
    # `mutates` is set.
    #
    # Proven wound: the agent writing to its OWN notebook (`mind_memory
    # save`) counted as a mutation. Result: an approval prompt to the user
    # for every memory, and in plan mode an outright DENY. For two days the
    # mind recorded no preference/lesson/fact — the conversation transcript
    # kept flowing while durable memory stopped. Writing to your own notebook
    # is not a system mutation; DELETING (forget) still is and stays gated.
    safe_actions: tuple[str, ...] = ()
    # Can it run concurrently with other tools in the same turn?
    parallel_safe: bool = True
    # Which MCP server it came from (None for local tools).
    source: str | None = None

    def api_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"Araç zaten kayıtlı: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def replace(self, spec: ToolSpec) -> ToolSpec:
        """Puts the fresh version of an existing skill on top of the old one.

        Skills only: when the agent fixed a file it had written and reloaded
        it, the old in-memory version kept running — the agent noticed,
        said "the cached version uses the old code" and dropped to the shell
        every time. Overwriting a built-in tool, however, is forbidden: a
        skill named `shell` would replace the permission gate.
        """
        current = self._tools.get(spec.name)
        if current is not None and current.source != spec.source:
            raise ValueError(f"Yerleşik aracın üzerine yazılamaz: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def unregister(self, name: str) -> bool:
        """Drops a skill from the registry. Built-in tools cannot be dropped."""
        spec = self._tools.get(name)
        if spec is None or spec.source is None:
            return False
        del self._tools[name]
        return True

    def tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        *,
        mutates: bool = False,
        parallel_safe: bool = True,
        safe_actions: tuple[str, ...] = (),
    ) -> Callable[[Handler], Handler]:
        def decorate(fn: Handler) -> Handler:
            self.register(
                ToolSpec(
                    name=name,
                    description=description.strip(),
                    input_schema=input_schema,
                    handler=fn,
                    mutates=mutates,
                    parallel_safe=parallel_safe,
                    safe_actions=safe_actions,
                )
            )
            return fn

        return decorate

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def all(self) -> list[ToolSpec]:
        """Sorted by name. The order must be deterministic.

        Tools are rendered at position 0 of the request; if their order
        changes the whole cache is invalidated.
        """
        return [self._tools[k] for k in sorted(self._tools)]

    def api_schemas(self, *, brief: bool = False) -> list[dict[str, Any]]:
        """The tools' API schema.

        `brief` is for small-window models: only the first paragraph of the
        description is sent. On a 4096-token model the tool descriptions
        alone eat a quarter of the window and leave no room for the
        conversation.
        """
        schemas = [t.api_schema() for t in self.all()]
        if not brief:
            return schemas

        for schema in schemas:
            schema["description"] = _first_paragraph(schema.get("description", ""))
        return schemas


def object_schema(
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


# -- schema validation --------------------------------------------------
#
# Proven chain: the model called `write_file` without `path` → `args["path"]`
# blew up inside the tool → the model received a RAW `KeyError: 'path'` →
# the model took it as "the tool is broken" and wrote the call XML as plain
# text instead of a real call → raw XML on the user's screen.
#
# The first link of the chain is broken here: BEFORE the handler is called
# the call is checked against the schema and, if it does not fit, the model
# gets INSTRUCTIONS rather than an exception — which field is missing, what
# you gave, what the schema is. From one place: the same guarantee for every
# tool, no per-tool patches needed.

# JSON Schema types → Python counterparts. `number` accepts int too (in JSON
# 1 is both integer and number); since `bool` is a subclass of int it is
# filtered out separately in the numeric checks.
_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def _type_matches(value: Any, kind: str) -> bool:
    expected = _JSON_TYPES.get(kind)
    if expected is None:
        return True   # a type we don't know: stay out of it
    if kind in ("number", "integer") and isinstance(value, bool):
        return False  # True is not a number; if the model mixed them up, say so
    return isinstance(value, expected)


def _schema_summary(schema: dict[str, Any], limit: int = 6) -> str:
    """The schema on one line: "path (string, zorunlu), text (string)".

    The model having already seen the schema is not enough — seeing it
    again next to the error makes the fix possible in the same turn.
    """
    props = schema.get("properties")
    if not isinstance(props, dict):
        return ""
    required = set(schema.get("required") or [])
    parts: list[str] = []
    for name, definition in list(props.items())[:limit]:
        kind = (definition or {}).get("type", "any") if isinstance(definition, dict) else "any"
        label = f"{name} ({kind}"
        if name in required:
            label += ", zorunlu"
        parts.append(label + ")")
    if len(props) > limit:
        parts.append("…")
    return ", ".join(parts)


def schema_violation(spec: ToolSpec, args: dict[str, Any]) -> str | None:
    """Does the call fit the schema? None if it does, a teaching message if not.

    Only the three violations the model can actually fix are checked:
    missing required field, wrong type, value outside the enum. Extra
    fields are not an error — rejecting a call for an extra field would
    break a working tool.
    """
    schema = spec.input_schema or {}
    props = schema.get("properties")
    if not isinstance(props, dict):
        return None
    summary = _schema_summary(schema)
    tail = f" Şema: {summary}." if summary else ""
    given = ", ".join(args) or "hiçbiri"

    missing = [name for name in (schema.get("required") or []) if name not in args]
    if missing:
        fields = ", ".join(f"`{name}`" for name in missing)
        plural = "alanları zorunlu" if len(missing) > 1 else "alanı zorunlu"
        return (
            f"'{spec.name}' çağrın eksik: {fields} {plural}. "
            f"Verdiğin alanlar: {given}.{tail} "
            "Aracı bu alanları ekleyerek yeniden çağır."
        )

    for name, value in args.items():
        definition = props.get(name)
        if not isinstance(definition, dict):
            continue
        if (options := definition.get("enum")) and value not in options:
            valid = ", ".join(str(s) for s in options)
            return (
                f"'{spec.name}' çağrısında `{name}` için geçerli değerler: "
                f"{valid}. Sen {value!r} verdin. Birini seçip yeniden çağır."
            )
        kind = definition.get("type")
        if isinstance(kind, str) and not _type_matches(value, kind):
            return (
                f"'{spec.name}' çağrısında `{name}` alanı {kind} olmalı; sen "
                f"{type(value).__name__} verdin.{tail} "
                "Değeri doğru tipte verip yeniden çağır."
            )
    return None


def _first_paragraph(text: str, limit: int = 220) -> str:
    """The essence of a description: up to the first blank line.

    What the tool does is in the first paragraph; the rest is when to use
    it and examples. When space is tight the first one must survive.
    """
    head = (text or "").strip().split("\n\n", 1)[0]
    head = " ".join(head.split())
    return head if len(head) <= limit else head[:limit].rsplit(" ", 1)[0] + "…"
