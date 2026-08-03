"""Peer-to-peer transport: this agent is simultaneously server and client.

``contracts`` names the tools, ``handlers`` implements them free of any MCP
dependency, and ``server`` / ``client`` are thin bindings over FastMCP.
"""

from . import contracts
from .handlers import PeerHandlers

__all__ = ["PeerHandlers", "contracts"]
