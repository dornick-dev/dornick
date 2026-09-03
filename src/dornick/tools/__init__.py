"""Tool layer."""

from __future__ import annotations

from typing import Any

from .base import (
    Block,
    Handler,
    JobFailed,
    ToolContext,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    object_schema,
)
from .executor import execute

__all__ = [
    "Block",
    "Handler",
    "JobFailed",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "build_registry",
    "execute",
    "object_schema",
]


def build_registry(mind: Any = None, *, subagents: bool = True) -> ToolRegistry:
    """Builds a registry filled with the built-in tools.

    If `mind` is given the mind tools are added too — the agent becomes able
    to walk its own memory, goals and past sessions with a tool.

    `subagents=False` is used when a sub-agent builds its own registry: a
    sub-agent gets no sub-agent of its own. Never registering the tool is
    better than registering it and refusing — the model should not try a
    capability that does not exist.

    Tools coming from MCP servers are added to the same registry later; the
    loop does not know where a tool came from.
    """
    from . import (
        artifacts,
        browser,
        canvas,
        checkpoint,
        devices,
        eyes,
        files,
        git_tool,
        hands,
        hearing,
        camera,
        jobs,
        kod,
        runner,
        learn,
        mail,
        place,
        plan_tool,
        search,
        shell,
        web,
        workflow,
    )

    registry = ToolRegistry()
    shell.register(registry)
    # Git: commit/push/GitHub — so nobody drops to the shell for `git commit`.
    git_tool.register(registry)
    # File tools + `denetle`: written code passes through its language's own
    # checker the moment it is written and the result goes into the tool's
    # reply. No separate registration line — diagnosis is part of writing a
    # file, not a separate capability.
    files.register(registry)
    # Content search: one tool for "where does X occur?" instead of reading
    # file by file.
    search.register(registry)
    # Structural search: `grep` sees text, `semboller` separates definition
    # from use — to see the calls of the function whose signature you are
    # about to change.
    kod.register(registry)
    # Change ledger: lists and reverts the snapshots the file tools take
    # (undo/redo).
    checkpoint.register(registry)
    # Test runner: `denetle` looks at syntax, `kos` RUNS the code. This is
    # the only thing that catches type/behaviour errors.
    runner.register(registry)
    web.register(registry)
    jobs.register(registry)
    # Workflow graphs: schedule is a single prompt; workflow is nodes/edges.
    workflow.register(registry)
    # Big job plan (approval gate).
    plan_tool.register(registry)
    eyes.register(registry)
    # Camera capture: only if opencv is installed. The registration is also
    # checked inside the tool itself; here it never enters the list when a
    # component is missing.
    from .. import watch as watching
    if watching.available():
        camera.register(registry)
    # Screen and hand: only if capture is actually possible. Showing a hand
    # that does not exist in the list means making the model click for
    # nothing.
    if hands.available():
        hands.register(registry)
    # Browser (dornick chrome): registered if Chrome/Edge is installed; if
    # the user did not enable it the tool itself says "off".
    from .. import chrome as chromium

    if chromium.available():
        browser.register(registry)
    learn.register(registry)
    # Devices: the PLC, camera, serial port the user described once. If it
    # stays inside the conversation it is gone in the next session.
    devices.register(registry)
    # Location: the answer to "what's the weather tomorrow?" depends on it
    # and the model could not learn it from anywhere.
    place.register(registry)
    # Drawing on screen: some answers get lost when told in words.
    canvas.register(registry)
    # Artifact: durable delivery pages — the chat flows on, the artifact
    # stays at its address and is updated under the same identity.
    artifacts.register(registry)
    # Ear management: "stop listening to me" must be able to be a real action.
    hearing.register(registry)
    # The model list is only useful while there are sub-agents: without a
    # sub-agent there is nothing to pick.
    if subagents:
        learn.register_models(registry)
    # Mail tools only if an account is configured: showing an unconfigured
    # tool in the list steers the model towards a capability it lacks.
    if mail.configured():
        mail.register(registry)

    if subagents:
        from . import agents

        agents.register(registry)

    if mind is not None:
        from ..mind import register as register_mind

        register_mind(registry, mind)

    return registry
