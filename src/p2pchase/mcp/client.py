"""MCP client: the half of a peer that calls the other peer.

Both agents run one of these alongside their server, which is what makes the
architecture genuinely peer-to-peer rather than client/server with extra steps.

Two behaviours here are load-bearing:

*Every call is deadline-bounded.* Rule 6 makes an unfinished sub-game a
technical loss for both teams, so a call that never returns is worse than a call
that fails. :class:`PeerClient` carries the agreed response timeout and applies
it to every request.

*A refusal is data, not an exception.* The handlers on the far side answer with
``{"ok": false, "reason": ...}``, and :meth:`PeerClient.call` returns that
verbatim. Only transport failures raise, so the orchestrator can tell "you sent
me something I cannot accept" apart from "you are not there".

The :class:`LoopbackClient` at the bottom talks to a handler object directly. It
exists so the protocol can be exercised end to end in tests without a socket --
never as a way to play a real match, which rules 1 and 2 forbid.
"""

from __future__ import annotations

import logging
from typing import Any

from . import contracts
from .handlers import PeerHandlers

LOGGER = logging.getLogger(__name__)


class TransportError(RuntimeError):
    """The opponent could not be reached, or answered unintelligibly."""


class PeerClient:
    """Calls tools on the opponent's MCP server.

    Input:  a tool name and a payload.
    Output: the opponent's response dict.
    Setup:  ``url`` (their public MCP endpoint) and ``timeout`` (the agreed
            response deadline).
    """

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        if not url:
            raise ValueError("opponent_url is empty; set it in config/<role>/setup.json")
        self.url = url
        self.timeout = timeout
        self._client = None
        self._open = False

    def _connect(self):
        if self._client is None:
            try:
                from fastmcp import Client
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise TransportError(
                    "FastMCP is not installed. Run `uv sync` to install the transport."
                ) from exc
            self._client = Client(self.url, timeout=self.timeout)
        return self._client

    async def open(self) -> None:
        """Hold one session open for the whole sub-game.

        Both peers send and receive on every step, so a connection per message
        means two peers repeatedly tearing down and rebuilding sessions at the
        same instant while each is also serving the other. That is a race, and
        it deadlocked a rehearsal at a different step every time. One session,
        opened once, removes the race and about a hundred handshakes with it.
        """
        await self._connect().__aenter__()
        self._open = True

    async def close(self) -> None:
        """Release the session. Safe to call when it was never opened.

        Never raises. The commonest time to close is right after the opponent
        finished and exited, so the session being already dead is the normal
        case -- and losing a completed sub-game's artifacts to a teardown error
        would be an absurd way to lose a match.
        """
        if self._open and self._client is not None:
            self._open = False
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001 -- the peer may already be gone
                LOGGER.debug("closing the peer session failed", exc_info=True)

    async def call(self, tool: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Invoke one tool on the opponent and return its structured answer."""
        client = self._connect()
        try:
            # Connecting is inside the guard on purpose: an opponent whose
            # server is not up yet fails *here*, not at call_tool, and a caller
            # that is waiting for them to appear must see one kind of error.
            if self._open:
                result = await client.call_tool(tool, payload or {})
            else:
                async with client:
                    result = await client.call_tool(tool, payload or {})
        except Exception as error:  # noqa: BLE001 -- re-raised as a transport fault
            raise TransportError(f"{tool} failed: {type(error).__name__}: {error}") from error
        return _unwrap(result)

    async def hello(self) -> dict[str, Any]:
        return await self.call(contracts.TOOL_HELLO)

    async def negotiate(self, handshake: dict[str, Any]) -> dict[str, Any]:
        return await self.call(contracts.TOOL_NEGOTIATE, {"handshake": handshake})


def _unwrap(result: Any) -> dict[str, Any]:
    """Normalise whatever the transport returns into a plain dict.

    FastMCP versions differ in whether a tool result arrives as structured
    content, a data attribute, or text blocks. Rather than pin one shape, we
    accept any of them -- an opponent's transport version is not something we
    control, and losing a match to a library upgrade would be absurd.
    """
    for attribute in ("structured_content", "data", "content"):
        value = getattr(result, attribute, None)
        if isinstance(value, dict):
            return value
    if isinstance(result, dict):
        return result
    text = getattr(result, "text", None) or str(result)
    return {"ok": False, "reason": f"unrecognised tool result: {text[:200]}"}


class LoopbackClient:
    """In-process client that calls a handler object directly.

    For tests and the two-terminal rehearsal only. A real match must cross a
    socket between two processes (rules 1, 2).
    """

    def __init__(self, handlers: PeerHandlers) -> None:
        self.handlers = handlers
        self._map = handlers.as_map()

    async def call(self, tool: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        handler = self._map.get(tool)
        if handler is None:
            return contracts.error(f"unknown tool {tool!r}")
        return handler(payload or {})

    async def hello(self) -> dict[str, Any]:
        return await self.call(contracts.TOOL_HELLO)

    async def negotiate(self, handshake: dict[str, Any]) -> dict[str, Any]:
        return await self.call(contracts.TOOL_NEGOTIATE, {"handshake": handshake})
