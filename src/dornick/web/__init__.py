"""Mind interface.

Standard library only. No Node, npm or build step on the user's side:
`pip install` is enough, the interface is served as a single HTML file.
"""

from __future__ import annotations

from .graph import build_graph
from .server import MindServer

__all__ = ["MindServer", "build_graph"]
