"""No exception leaves a tool call. Ever (rule 6).

Every handler in this codebase already answers rather than raises -- a refusal
is a structured response, not a traceback. This is the guard for what none of
them anticipated: the genuinely unexpected exception, from a library, a typo on
a rare branch, an opponent's payload shaped in a way we never imagined.

Without it such a fault escapes to FastMCP, which returns a transport-level
error the opponent cannot distinguish from a crash -- and rule 6 makes a stalled
sub-game a technical loss for *both* teams. Our fault becomes their loss too,
which is the part that makes this their business as well as ours. gal-roy1 asked
for it after two runs of theirs died at round 14 against us. The cause turned out
to be elsewhere entirely, but the request was right on its own merits: they are
entitled to insist we cannot take them down with us, and we are entitled to the
same of them.

A guard at this boundary is not a substitute for handling errors where they
happen. It is the difference between losing a move and losing a match.
"""

from __future__ import annotations

import logging
from typing import Any

from . import contracts

LOGGER = logging.getLogger(__name__)


def _root_cause(error: BaseException) -> BaseException:
    """The exception that actually happened, not the one wrapping it.

    FastMCP re-raises a tool fault as ``ToolError: Error calling tool 'x': ...``,
    so reporting the outermost type tells an opponent only that something went
    wrong inside a tool -- which they already knew. The chained cause is the
    part worth putting on the wire.
    """
    seen: set[int] = set()
    while error.__cause__ is not None and id(error) not in seen:
        seen.add(id(error))
        error = error.__cause__
    return error


def build_guard() -> Any:
    """A FastMCP middleware turning any escaping exception into a refusal.

    Middleware rather than a decorator on each tool, because a tool's signature
    *is* its published schema: FastMCP builds the schema by inspecting it and
    refuses any argument the signature does not name. Wrapping thirteen
    functions would put thirteen chances to alter a signature between us and the
    opponent, to solve a problem that is not about signatures at all.
    """
    from fastmcp.server.middleware import Middleware
    from fastmcp.tools.tool import ToolResult

    class ToolGuard(Middleware):
        async def on_call_tool(self, context: Any, call_next: Any) -> Any:
            try:
                return await call_next(context)
            except Exception as error:  # noqa: BLE001 -- that is the entire point
                tool = getattr(context.message, "name", "<unknown>")
                # Logged with the traceback, answered without it: the opponent
                # needs to know we refused and roughly why, and does not need
                # our stack. exc_info keeps the diagnosis on our side, where the
                # log now lives in a file rather than a terminal nobody kept.
                LOGGER.exception("unhandled fault in tool %r; answering with a refusal", tool)
                root = _root_cause(error)
                refusal = contracts.error(
                    f"internal fault in {tool}: {type(root).__name__}: {root}",
                    tool=tool, fault=True)
                # A ToolResult, not a bare dict. Returning the dict raises
                # inside FastMCP's own result handling -- which would replace
                # one escaping exception with another, in the one place that
                # exists to stop exceptions escaping. ``is_error`` stays False
                # on purpose: this *is* the answer, and flagging it as a
                # protocol error would put it back in the category the peer
                # cannot tell from a crash.
                return ToolResult(structured_content=refusal)

    return ToolGuard()
