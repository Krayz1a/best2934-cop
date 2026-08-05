"""Serving and playing in one process, over one session.

A peer is not a client *or* a server; it is both at once, and it has to be both
inside a single process. Our client pushes commitments outward while the
opponent's client pushes theirs into our server, and the turn loop cannot take a
step until it can see what arrived. Those are the same session or they are
nothing: two processes, one holding the loop and one holding the inbox, would
have the loop waiting at step 1 for a commitment sitting in another process's
memory -- which is a 30-second deadline and a technical loss for both teams
(rule 6), from a topology mistake rather than anything either side did wrong.

Rule 1 is about the *cop and the thief* being separate processes, and they are:
one of these per team, two per match, no shared memory between them (rule 2).

Both halves share one asyncio event loop rather than a thread each. The session
is mutated from both -- inbound handlers and the outbound loop -- and a single
loop makes those mutations cooperative, so the interleaving is the protocol's
rather than the scheduler's.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..mcp.client import TransportError
from ..mcp.handlers import PeerHandlers
from ..mcp.server import build_server
from .peer import PeerOutcome, PeerRunner

LOGGER = logging.getLogger(__name__)

#: How long to keep knocking before deciding the opponent is not coming.
OPPONENT_WAIT_SEC = 120.0
KNOCK_INTERVAL_SEC = 1.0


async def _serve_forever(handlers: PeerHandlers, host: str, port: int, name: str) -> None:
    server = build_server(handlers, name=name)
    LOGGER.info("peer server listening on http://%s:%d/mcp", host, port)
    await server.run_http_async(host=host, port=port, show_banner=False)


async def _await_opponent(runner: PeerRunner, url: str,
                          timeout: float = OPPONENT_WAIT_SEC) -> dict[str, Any]:
    """Knock until the opponent's server answers ``hello``.

    Two teams never press enter at the same instant, and refusing to wait would
    make the match a race. The wait is bounded because rule 6 charges both sides
    for a sub-game that never starts, so at some point not-playing has to be a
    decision rather than a hang.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    last = ""
    while asyncio.get_running_loop().time() < deadline:
        try:
            return dict((await runner.client.hello()).get("handshake", {}))
        except TransportError as error:
            last = str(error)
            LOGGER.info("opponent at %s not up yet; retrying", url)
            await asyncio.sleep(KNOCK_INTERVAL_SEC)
    raise TransportError(f"opponent at {url} never answered within {timeout:.0f}s: {last}")


async def host_and_play(runner: PeerRunner, handlers: PeerHandlers, host: str, port: int,
                        url: str, on_handshake) -> tuple[PeerOutcome, dict[str, Any]]:
    """Bring our server up, wait for theirs, play one sub-game, then stop.

    ``on_handshake`` decides whether the opponent's fingerprints are acceptable
    (rule 11); it returns ``""`` to accept or the reason to refuse. Refusing is
    an abort, not an exception: the opponent is owed an explanation it can read.
    """
    name = f"p2pchase-{runner.session.group_id}-{runner.session.role}"
    server_task = asyncio.create_task(_serve_forever(handlers, host, port, name))
    try:
        handshake = await _await_opponent(runner, url)
        refusal = on_handshake(handshake)
        if refusal:
            LOGGER.error("refusing to play %s: %s", url, refusal)
            return await runner.abort(f"configuration mismatch at handshake: {refusal}", 0), handshake
        LOGGER.info("handshake agreed with %s", handshake.get("group_id"))
        # One session for the whole sub-game: see PeerClient.open.
        await runner.client.open()
        try:
            return await runner.run_sub_game(), handshake
        finally:
            await runner.client.close()
    finally:
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown noise
            LOGGER.debug("peer server stopped", exc_info=True)
