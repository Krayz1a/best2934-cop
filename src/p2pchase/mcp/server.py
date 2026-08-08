"""FastMCP server binding (book ch2, ch8; rules 1, 2, 10).

Each agent runs one of these, and each agent also runs a client that calls the
other one. That is the whole architecture: there is no server in the middle, no
referee and no shared process. Rule 1 requires two separate processes, rule 2
forbids shared memory between them, and rule 10 puts a league match across the
public internet through a tunnel -- so this server binds a real socket even when
both peers happen to be on one laptop.

The module is deliberately thin. Every tool below immediately delegates to
:class:`~p2pchase.mcp.handlers.PeerHandlers`, which knows nothing about MCP and
can therefore be tested without it. If you are looking for behaviour, it is
there, not here.

One thing here is *not* free to drift: a tool's parameters are its published
MCP schema, and FastMCP rejects a call carrying any argument the signature does
not name. So every key :mod:`p2pchase.mcp.contracts` puts on the wire must
appear below -- including the ones a handler ignores, such as ``sender_group``.
Omitting one does not degrade the message, it refuses it, and a refused
``commit_step`` is a technical loss at move one for both teams (rule 6).
``tests/integration/test_live_transport.py`` holds this to a real socket,
because an in-process client passes the dict through and can never see it.
"""

from __future__ import annotations

import logging
from typing import Any

from ..shared.peer_config import PeerConfig
from .handlers import PeerHandlers
from .interop import InteropAdapter
from .interop_server import register_interop

LOGGER = logging.getLogger(__name__)


class MissingTransportError(RuntimeError):
    """FastMCP is not installed -- an environment problem, not a code fault."""


def build_server(handlers: PeerHandlers, name: str = "p2pchase-peer"):
    """Wrap handlers in a FastMCP server.

    The import is local so the rest of the package -- domain logic, the replay
    verifier, the whole test suite -- stays importable on a machine that has
    never installed the transport.
    """
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - optional at import time
        raise MissingTransportError(
            "FastMCP is not installed. Run `uv sync` to install the peer transport."
        ) from exc

    from .tool_guard import build_guard

    mcp = FastMCP(name)
    # Nothing below may raise across the wire: an escaping exception reaches the
    # opponent as an opaque transport failure and rule 6 charges *both* teams.
    mcp.add_middleware(build_guard())

    adapter = InteropAdapter(handlers)

    @mcp.tool
    def hello(payload: dict[str, Any] | None = None,
              group_id: str = "") -> dict[str, Any]:
        """Identify this peer and publish its configuration fingerprints.

        ``payload`` is optional: an opponent whose convention is one object per
        call sends ``{}``, and a signature naming no argument at all would
        *refuse* them, because FastMCP rejects any argument it does not declare.

        ``group_id`` is the same bet in the other direction, and we lost it once
        already -- the moment our own client started naming itself, it sent the
        field at the top level and FastMCP refused the call before any handler
        ran, exactly as this docstring had warned about the empty signature. A
        caller that names itself is answered with the locks agreed with *them*;
        both spellings are accepted, as with ``negotiate``.
        """
        named = payload or {}
        if group_id:
            named = dict(named, group_id=group_id)
        return adapter.hello(named)

    @mcp.tool
    def negotiate(handshake: dict[str, Any] | None = None,
                  payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Compare the caller's fingerprints with ours; refuse on mismatch.

        Both spellings, for the same reason as ``declare_step0`` -- and this one
        we learned the expensive way. gal-roy1 called this with ``payload`` on
        the first contact after a nine-hour outage; FastMCP refused it for a
        missing ``handshake`` before any handler ran, and the sub-game died at
        the handshake. A required positional argument is a bet that the opponent
        spells it our way.

        They nested the fields *and* a ``handshake`` key inside ``payload``,
        evidently trying to satisfy either convention. That cannot work from the
        caller's side: FastMCP matches top-level argument names only, so nesting
        is invisible to it. It has to be fixed here. We unwrap the inner key when
        it is present and otherwise read the wrapper itself as the handshake.
        """
        inner = payload.get("handshake") if isinstance(payload, dict) else None
        return handlers.negotiate({"handshake": handshake or inner or payload or {}})

    @mcp.tool
    def declare_step0(declaration: dict[str, Any] | None = None,
                      payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Accept the caller's signed Step-0 hardware declaration.

        Two spellings of the same argument, because two teams named it
        differently and the name is the published schema. Accepting both costs
        one ``or``; accepting one costs the match at the handshake (rule 6).
        """
        return handlers.declare_step0(declaration or payload or {})

    @mcp.tool
    def commit_step(game_id: str, sub_game_number: int, step: int, commit: str,
                    sender_group: str = "", sender_role: str = "") -> dict[str, Any]:
        """Receive one sealed step: the SHA-256 commitment and nothing else."""
        return handlers.commit_step({
            "game_id": game_id, "sub_game_number": sub_game_number,
            "step": step, "commit": commit,
            "sender_group": sender_group, "sender_role": sender_role,
        })

    @mcp.tool
    def acknowledge_step(game_id: str, sub_game_number: int, step: int) -> dict[str, Any]:
        """Confirm that we hold a commitment for this step."""
        return handlers.acknowledge_step({
            "game_id": game_id, "sub_game_number": sub_game_number, "step": step,
        })

    @mcp.tool
    def reveal_step(game_id: str, sub_game_number: int, step: int,
                    hint: str = "", move: str = "",
                    barrier: list[int] | None = None,
                    capture_claim: list[int] | None = None,
                    intent: str = "", sender_group: str = "",
                    sender_role: str = "") -> dict[str, Any]:
        """Receive the disclosed hint and any barrier. Move and nonce stay sealed.

        ``move`` and ``intent`` are optional and default to empty: since I-5
        neither peer discloses them mid-game. They stay in the signature because
        a signature *is* the published schema -- FastMCP rejects any argument it
        does not name -- so removing them would refuse a peer who still sends
        one. Making ``move`` required is what broke the rehearsal the moment we
        stopped sending it, in a way no in-process test could see.
        """
        return handlers.reveal_step({
            "game_id": game_id, "sub_game_number": sub_game_number, "step": step,
            "move": move, "hint": hint, "barrier": barrier,
            "capture_claim": capture_claim, "intent": intent,
            "sender_group": sender_group, "sender_role": sender_role,
        })

    @mcp.tool
    def sample_scent(game_id: str, sub_game_number: int, step: int,
                     cells: list[list[int]]) -> dict[str, Any]:
        """Report our pheromone intensity at the cells the caller names."""
        return handlers.sample_scent({
            "game_id": game_id, "sub_game_number": sub_game_number,
            "step": step, "cells": cells,
        })

    @mcp.tool
    def final_reveal(records: list[dict[str, Any]] | None = None, game_id: str = "",
                     sub_game_number: int = 0, sender_group: str = "",
                     outcome: str = "") -> dict[str, Any]:
        """Exchange complete audit views, nonces included, after the sub-game."""
        return handlers.final_reveal({
            "records": records or [], "game_id": game_id,
            "sub_game_number": sub_game_number, "sender_group": sender_group,
            "outcome": outcome,
        })

    @mcp.tool
    def audit_result(records: list[dict[str, Any]]) -> dict[str, Any]:
        """Verify the caller's disclosed chain and return the verdict."""
        return handlers.audit_result({"records": records})

    @mcp.tool
    def agree_result(sha256: str = "", expected: str = "",
                     payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Compare result digests; a mismatch voids the match for both sides.

        Our client sends the digests flat; gal-roy1 sends one ``payload``
        carrying ``{outcome, agreement}``. Both arrive here, and both are
        answered with the digest *and* the field list it covers -- two digests
        over different objects disagree every time, and rule 35 answers a
        disagreement by voiding the match for both teams.
        """
        if payload is not None:
            return adapter.agree_result(payload)
        return adapter.agree_result({"sha256": sha256, "expected": expected or sha256})

    @mcp.tool
    def abort(reason: str = "") -> dict[str, Any]:
        """Accept an abort so neither peer is left waiting on a dead match."""
        return handlers.abort({"reason": reason})

    register_interop(mcp, adapter)
    return mcp


def serve(config: PeerConfig, handlers: PeerHandlers | None = None,
          host: str = "127.0.0.1", port: int | None = None,
          transport: str = "http") -> None:
    """Run the peer server until interrupted. Blocking.

    Binds ``127.0.0.1`` by default: exposing the port to the internet is the
    tunnel's job (ngrok / Localtonet), not this process's, so nothing is
    published by accident during development.

    ``transport="stdio"`` speaks the same JSON-RPC on stdin/stdout instead of
    over HTTP, which is what makes a raw TCP door possible:

        socat TCP-LISTEN:9101,reuseaddr,fork EXEC:'p2pchase serve --transport stdio ...'

    gal-roy1 proposed this and the reasoning is sound. MCP's stdio transport is
    already newline-delimited JSON-RPC 2.0, so a socket carrying those bytes is
    a valid MCP transport -- the tools, schemas and dialect are untouched, and
    ``config_sha256`` with them. It removes the entire class of bugs that has
    cost this league its month: no session header to omit, no ``Accept`` to get
    wrong, no free-tier interstitial, no half-closed SSE stream.

    socat's ``fork`` is worth more than the transport. One process per
    connection means a peer *cannot* carry state between sub-games even by
    accident -- and we have shipped exactly that bug, a round counter that
    climbed 68, 103, 137, 172, 207, 240 across gal-roy1's attempts while every
    one of them was declined.

    HTTP stays primary and unchanged. This is a second door, not a move.
    """
    from .accept_probe import probe_middleware

    handlers = handlers or PeerHandlers(config)
    server = build_server(handlers, name=f"p2pchase-{config.group_id}-{config.role}")
    if transport == "stdio":
        # No host, no port, no middleware: stdin and stdout are the socket, and
        # anything written to stdout that is not JSON-RPC corrupts the stream.
        LOGGER.info("peer server on stdio (role=%s, group=%s)", config.role, config.group_id)
        server.run(transport="stdio")
        return
    bind_port = port or config.my_port
    LOGGER.info("peer server listening on http://%s:%d/mcp (role=%s, group=%s)",
                host, bind_port, config.role, config.group_id)
    server.run(transport="http", host=host, port=bind_port,
               middleware=probe_middleware())
