"""Binding the opponent's dialect onto our own server (ADR-019).

:mod:`p2pchase.mcp.interop` does the translating; this module is the part that
makes a real opponent's call actually arrive. Splitting them is not tidiness:
the adapter is pure and unit-testable, the binding needs FastMCP, and only the
binding can get the *names* wrong in a way no unit test would notice.

Three of gal-roy1's six tool names collide with ours -- ``hello``,
``declare_step0`` and ``agree_result`` -- and FastMCP cannot register two tools
under one name. We cannot rename ours out of the way either, because our own
client calls them and because they call theirs by name. So those three are
resolved *in* :mod:`p2pchase.mcp.server` by widening the signature to accept
both spellings, and only the three non-colliding names are registered here.

That split is worth stating plainly, because it is the kind of thing that looks
arbitrary six months later: a name that exists once is bound here, a name that
exists twice is bound there. Both dialects reach the same handlers either way,
so a match played through either surface is the same match (rule 36).
"""

from __future__ import annotations

import logging
from typing import Any

from . import contracts
from .interop import InteropAdapter

LOGGER = logging.getLogger(__name__)

#: Registered here because nothing of ours already claims these names.
#: Derived rather than listed: the split *is* "does one of our tools already own
#: this name", so computing it means a new dialect tool cannot be added to one
#: list and forgotten in the other.
DISTINCT_TOOLS = tuple(name for name in contracts.INTEROP_TOOLS
                       if name not in contracts.ALL_TOOLS)
#: Registered in :mod:`p2pchase.mcp.server`, with widened signatures.
SHARED_NAMES = tuple(name for name in contracts.INTEROP_TOOLS
                     if name in contracts.ALL_TOOLS)


def register_interop(mcp: Any, adapter: InteropAdapter) -> tuple[str, ...]:
    """Add the opponent's non-colliding tool names to a built server.

    Returns the names registered, so a caller -- or a test -- can assert the
    published surface rather than trust that this function was reached.
    """

    @mcp.tool
    def propose_config(payload: dict[str, Any]) -> dict[str, Any]:
        """Their name for ``negotiate``: compare configs and refuse on mismatch."""
        return adapter.propose_config(payload)

    @mcp.tool
    def submit_turn(payload: dict[str, Any]) -> dict[str, Any]:
        """One alternating turn in, ours back in ``reply_turn``."""
        return adapter.submit_turn(payload)

    @mcp.tool
    def confirm_result(payload: dict[str, Any]) -> dict[str, Any]:
        """A conceded ending, so the winner of a piggybacked capture learns it won."""
        return adapter.confirm_result(payload)

    @mcp.tool
    def final_audit(payload: dict[str, Any]) -> dict[str, Any]:
        """Their name for ``final_reveal``: every nonce, both ways (rule 18)."""
        return adapter.final_audit(payload)

    LOGGER.info("interop tools published: %s", ", ".join(DISTINCT_TOOLS))
    return DISTINCT_TOOLS
