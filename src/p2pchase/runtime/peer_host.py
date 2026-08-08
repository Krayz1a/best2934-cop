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

from ..mcp import contracts
from ..mcp.client import TransportError
from ..mcp.handlers import PeerHandlers
from ..mcp.server import build_server
from .peer import PeerOutcome, PeerRunner

LOGGER = logging.getLogger(__name__)

#: How long to keep knocking before deciding the opponent is not coming.
OPPONENT_WAIT_SEC = 120.0
KNOCK_INTERVAL_SEC = 1.0


async def _serve_forever(handlers: PeerHandlers, host: str, port: int, name: str) -> None:
    from ..mcp.accept_probe import probe_middleware

    server = build_server(handlers, name=name)
    LOGGER.info("peer server listening on http://%s:%d/mcp", host, port)
    await server.run_http_async(host=host, port=port, show_banner=False,
                                middleware=probe_middleware())


async def _await_opponent(runner: PeerRunner, url: str,
                          timeout: float = OPPONENT_WAIT_SEC) -> dict[str, Any]:
    """Knock until the opponent's server answers ``tools/list``.

    Two teams never press enter at the same instant, and refusing to wait would
    make the match a race. The wait is bounded because rule 6 charges both sides
    for a sub-game that never starts, so at some point not-playing has to be a
    decision rather than a hang.

    **Liveness is ``tools/list``, not a tool call.** This knocked with ``hello``
    until 2026-08-08, when it spent five minutes reporting imreeyal as down while
    they were up and pushing agreements at us: they publish no ``hello``, the
    ``Unknown tool`` came back as a :class:`TransportError`, and the loop below
    treats a transport fault as "not here yet". A peer that implements none of
    our names is still a peer. Collapsing "you do not implement this" into "you
    are not there" hides the first behind a retry of the second, and they have
    entirely different fixes.

    The greeting is now best-effort for the same reason. ``hello`` is a
    convenience that lets us see their locks a moment early; ``negotiate`` is the
    authority and re-derives everything from their ``group_id`` anyway. So a peer
    without ``hello`` returns an empty handshake here and proceeds, rather than
    being refused a match over a tool the league never agreed on.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    last = ""
    while asyncio.get_running_loop().time() < deadline:
        try:
            published = await runner.client.list_tools()
        except TransportError as error:
            last = str(error)
            LOGGER.info("opponent at %s not up yet; retrying", url)
            await asyncio.sleep(KNOCK_INTERVAL_SEC)
            continue
        LOGGER.info("opponent at %s is up; publishes %d tools: %s",
                    url, len(published), ", ".join(sorted(published)) or "(none)")
        if contracts.TOOL_HELLO not in published:
            LOGGER.info("no %r on their surface -- negotiate is the authority, proceeding",
                        contracts.TOOL_HELLO)
            return {}
        greeting = await runner.client.hello(runner.session.group_id)
        return dict(greeting.get("handshake", {}))
    raise TransportError(f"opponent at {url} never answered tools/list within "
                         f"{timeout:.0f}s: {last}")


async def declare_step0(runner: PeerRunner) -> str:
    """Declare our hardware and our role before move one (rules 24, 53).

    Returns the opponent's refusal, or ``""`` if they accepted. The refusal that
    matters is a role clash: both peers derive the assignment from the same rule
    (:mod:`p2pchase.domain.roles`), so if they read the pairing differently then
    one of the two implementations is wrong and the sub-game is unplayable. Two
    cops chase nobody. Finding that here costs a handshake; finding it at move
    one costs both teams a technical loss under rule 6.

    A peer that does not implement ``declare_step0`` at all is *not* refused --
    that would be inventing a requirement the rulebook does not make, and our own
    declaration is committed as step 0 of our chain either way, which is what
    rule 24 actually asks for.
    """
    from ..infra.sysinfo import build_step0
    from ..mcp import contracts

    session, config = runner.session, runner.config
    declaration = build_step0(
        group_name=config.group_name, sub_game_number=session.sub_game,
        llm_model=str(config.llm.get("model", "template")),
        signing_secret=runner.signing_secret, role=session.role,
        group_id=session.group_id,
    )
    try:
        answer = await runner.client.call(contracts.TOOL_STEP0, contracts.step0_payload(
            session.game_id, session.sub_game, session.group_id, session.role, declaration))
    except Exception as error:  # noqa: BLE001 -- an unimplemented tool is not a clash
        LOGGER.info("opponent did not accept a step-0 declaration (%s); continuing", error)
        return ""
    if answer.get("ok") is False:
        return str(answer.get("reason", "opponent refused our step-0 declaration"))
    LOGGER.info("step 0 declared: we are the %s, they hold the %s and read us as the %s",
                session.role, answer.get("responder_role") or "unstated",
                answer.get("caller_role") or "unstated")
    return ""


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
            # Step 0 before step 1, and it is the last cheap moment to find a
            # role clash: two peers that both think they are the cop chase
            # nobody, and rule 6 charges both teams for the sub-game that never
            # happens. See declare_step0 above.
            clash = await declare_step0(runner)
            if clash:
                LOGGER.error("refusing to play %s: %s", url, clash)
                return await runner.abort(f"role clash at step 0: {clash}", 0), handshake
            return await runner.run_sub_game(), handshake
        finally:
            await runner.client.close()
    finally:
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown noise
            LOGGER.debug("peer server stopped", exc_info=True)
