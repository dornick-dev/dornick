"""dornick — an agent harness that can use the computer.

Layers:
    config      configuration
    events      append-only event log (the carrier of episodic memory)
    session     projects events into API messages
    tools       tool registry and executor
    permissions pre-action policy gate
    context     cache breakpoints and context pruning
    client      Anthropic API wrapper (streaming, cancel)
    loop        the agent loop
"""

# The single source of truth is pyproject.toml — no version is written
# here by hand (what is written gets forgotten: the 0.1.0 relic was born
# that way). environment.version() reads and caches it.
from .environment import version as _version

__version__ = _version()
