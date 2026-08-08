"""Which tool each call actually invoked, in both directions.

We logged that an opponent call *happened* -- a service ran, a handshake was
compared -- and never which name it arrived under. On 2026-08-09 that cost us a
sub-game and an evening. Our log showed our negotiation path running thirteen
times, which we reported to imreeyal as "your peer called negotiate thirteen
times"; it was an inference, we said so, and the far more useful fact was the
one no line recorded at all: **our own client called nothing**. An absence is
invisible in a log that only records presences, and the missing outbound
``negotiate`` was the entire bug.

So both halves are logged here, and the outbound half is the point. A
per-direction, per-tool tally answers "who spoke, in what order" in one grep,
which is the question a stalled peer always turns out to be asking.

Middleware rather than a decorator on each tool, for the reason
:mod:`p2pchase.mcp.tool_guard` gives: a tool's signature *is* its published
schema, FastMCP builds the schema by inspecting it, and thirteen wrappers would
be thirteen chances to alter a signature we spent a week getting opponents to
accept. Nothing here touches arguments or results.

**Names only, never payloads.** A turn message carries a commitment whose whole
security argument is that nothing about the move leaks before the reveal (rule
18), and an audit carries the nonces. Logging bodies would put both in a file
that gets pasted into issue threads. The name and the size are enough to
reconstruct a conversation and cannot disclose a move.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

LOGGER = logging.getLogger(__name__)

#: Counts per direction, for the one-line summary at the end of a sub-game.
INBOUND: Counter[str] = Counter()
OUTBOUND: Counter[str] = Counter()


def record_outbound(tool: str) -> None:
    """Note that we called ``tool`` on the opponent."""
    OUTBOUND[tool] += 1
    LOGGER.info("-> calling %r on the opponent (call %d)", tool, OUTBOUND[tool])


def record_inbound(tool: str) -> None:
    """Note that the opponent called ``tool`` on us."""
    INBOUND[tool] += 1
    LOGGER.info("<- opponent called %r (call %d)", tool, INBOUND[tool])


def reset() -> None:
    """Forget both tallies. Used between sub-games and by tests."""
    INBOUND.clear()
    OUTBOUND.clear()


def _render(counts: Counter[str]) -> str:
    if not counts:
        return "(none)"
    return ", ".join(f"{name}x{count}" for name, count in sorted(counts.items()))


def summary() -> str:
    """One line naming every tool that crossed the wire, and how often.

    Written at the end of a sub-game whatever the outcome, and *especially* on
    a stall: the shape of the failure is usually visible in what is missing
    from one of the two lists.
    """
    return f"tools in: {_render(INBOUND)} | tools out: {_render(OUTBOUND)}"


def build_call_log() -> Any:
    """A FastMCP middleware that names each inbound tool call.

    Added beside the guard rather than inside it. The guard exists to stop an
    exception escaping and must stay the outermost thing anyone reasons about;
    folding a diagnostic into it would mean a bug in the diagnostic could take
    the refusal path down with it.
    """
    from fastmcp.server.middleware import Middleware

    class CallLog(Middleware):
        async def on_call_tool(self, context: Any, call_next: Any) -> Any:
            record_inbound(str(getattr(context.message, "name", "<unknown>")))
            return await call_next(context)

    return CallLog()
