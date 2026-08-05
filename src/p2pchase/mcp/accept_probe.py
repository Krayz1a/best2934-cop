"""Why a peer got ``406 Not Acceptable`` from us, said out loud.

MCP's streamable-HTTP transport refuses a POST whose ``Accept`` header does not
name *both* ``application/json`` and ``text/event-stream``. The refusal comes
out of the SDK, before any of our code runs, and it says nothing in our log
beyond the status code. That is a bad way to lose a match: an opponent knocking
every thirty seconds and being turned away looks, from our side, exactly like an
opponent who never knocked at all -- and rule 6 charges both teams for the
sub-game that never starts.

We found this the slow way. A peer reached us, exchanged tools cleanly for four
minutes, went quiet, and came back three hours later POSTing every thirty
seconds to a wall of 406s. The only reason it was diagnosable at all is that the
server's output was going to a file by then; the only reason it was *quick* is
that someone happened to know what a 406 means here. This module removes the
second dependency.

It changes no behaviour. The request is passed straight through and the SDK
still refuses it -- being lenient here would mean answering with an event stream
to a client that just told us it cannot read one, which is a worse failure than
an honest refusal because it fails later and quieter.
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

#: What the transport requires, and what a refused client is missing.
REQUIRED_ACCEPT = ("application/json", "text/event-stream")


class AcceptProbe:
    """Pure-ASGI passthrough that explains the 406 the SDK is about to send."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("method") == "POST":
            self._check(scope)
        await self.app(scope, receive, send)

    def _check(self, scope: Any) -> None:
        headers = {key.decode("latin-1").lower(): value.decode("latin-1")
                   for key, value in scope.get("headers", [])}
        accept = headers.get("accept", "")
        missing = [kind for kind in REQUIRED_ACCEPT if kind not in accept]
        if not missing:
            return
        LOGGER.error(
            "a peer will be refused with 406: its Accept header is %r and the MCP "
            "streamable-HTTP transport needs both of %s (missing %s). Their client "
            "must send 'Accept: application/json, text/event-stream'. "
            "client=%s user-agent=%r",
            accept or "<absent>", ", ".join(REQUIRED_ACCEPT), ", ".join(missing),
            headers.get("x-forwarded-for", "unknown"), headers.get("user-agent", ""),
        )


def probe_middleware() -> list[Any]:
    """``[Middleware(AcceptProbe)]``, or ``[]`` where Starlette is unavailable.

    Empty rather than raising: this is a diagnostic, and a diagnostic that can
    stop a peer from serving would be worse than the silence it replaces.
    """
    try:
        from starlette.middleware import Middleware
    except ImportError:  # pragma: no cover - transport is optional at import time
        LOGGER.debug("starlette unavailable; serving without the Accept-header probe")
        return []
    return [Middleware(AcceptProbe)]
