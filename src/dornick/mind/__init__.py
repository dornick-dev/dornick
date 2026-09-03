"""The mind layer.

The surface through which the agent can navigate its own past, knowledge
and goals. The store is `store.Mind`, the tools exposed to the agent are
`tools.register`.

The same store will later be exposed as an MCP server too; then outside
agents (Claude Code included) will be able to read the same mind.
"""

from __future__ import annotations

from pathlib import Path

from ..recall.clock import Clock
from .store import Episode, Goal, Memory, Mind
from .tools import register

__all__ = ["Episode", "Goal", "Memory", "Mind", "open_mind", "register"]


def open_mind(
    mind_dir: Path,
    sessions_dir: Path,
    session_id: str = "",
    *,
    clock: Clock | None = None,
) -> Mind:
    """Opens the mind. Without `clock` the wall clock is used (see recall/clock.py)."""
    return Mind(mind_dir=mind_dir, sessions_dir=sessions_dir,
                session_id=session_id, clock=clock)
