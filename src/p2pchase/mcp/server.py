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
"""

from __future__ import annotations

import logging
from typing import Any

from ..shared.peer_config import PeerConfig
from .handlers import PeerHandlers

LOGGER = logging.getLogger(__name__)


class MissingTransport(RuntimeError):
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
        raise MissingTransport(
            "FastMCP is not installed. Run `uv sync` to install the peer transport."
        ) from exc

    mcp = FastMCP(name)

    @mcp.tool
    def hello() -> dict[str, Any]:
        """Identify this peer and publish its configuration fingerprints."""
        return handlers.hello({})

    @mcp.tool
    def negotiate(handshake: dict[str, Any]) -> dict[str, Any]:
        """Compare the caller's fingerprints with ours; refuse on mismatch."""
        return handlers.negotiate({"handshake": handshake})

    @mcp.tool
    def declare_step0(declaration: dict[str, Any]) -> dict[str, Any]:
        """Accept the caller's signed Step-0 hardware declaration."""
        return handlers.declare_step0(declaration)

    @mcp.tool
    def commit_step(game_id: str, sub_game_number: int, step: int,
                    commit: str) -> dict[str, Any]:
        """Receive one sealed step: the SHA-256 commitment and nothing else."""
        return handlers.commit_step({
            "game_id": game_id, "sub_game_number": sub_game_number,
            "step": step, "commit": commit,
        })

    @mcp.tool
    def acknowledge_step(game_id: str, sub_game_number: int, step: int) -> dict[str, Any]:
        """Confirm that we hold a commitment for this step."""
        return handlers.acknowledge_step({
            "game_id": game_id, "sub_game_number": sub_game_number, "step": step,
        })

    @mcp.tool
    def reveal_step(game_id: str, sub_game_number: int, step: int, move: str,
                    hint: str, barrier: list[int] | None = None) -> dict[str, Any]:
        """Receive the disclosed move, hint and barrier. The nonce stays sealed."""
        return handlers.reveal_step({
            "game_id": game_id, "sub_game_number": sub_game_number, "step": step,
            "move": move, "hint": hint, "barrier": barrier,
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
    def final_reveal(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Exchange complete audit views, nonces included, after the sub-game."""
        return handlers.final_reveal({"records": records or []})

    @mcp.tool
    def audit_result(records: list[dict[str, Any]]) -> dict[str, Any]:
        """Verify the caller's disclosed chain and return the verdict."""
        return handlers.audit_result({"records": records})

    @mcp.tool
    def agree_result(sha256: str, expected: str = "") -> dict[str, Any]:
        """Compare result digests; a mismatch voids the match for both sides."""
        return handlers.agree_result({"sha256": sha256, "expected": expected or sha256})

    @mcp.tool
    def abort(reason: str = "") -> dict[str, Any]:
        """Accept an abort so neither peer is left waiting on a dead match."""
        return handlers.abort({"reason": reason})

    return mcp


def serve(config: PeerConfig, handlers: PeerHandlers | None = None,
          host: str = "127.0.0.1", port: int | None = None) -> None:
    """Run the peer server until interrupted. Blocking.

    Binds ``127.0.0.1`` by default: exposing the port to the internet is the
    tunnel's job (ngrok / Localtonet), not this process's, so nothing is
    published by accident during development.
    """
    handlers = handlers or PeerHandlers(config)
    server = build_server(handlers, name=f"p2pchase-{config.group_id}-{config.role}")
    bind_port = port or config.my_port
    LOGGER.info("peer server listening on http://%s:%d/mcp (role=%s, group=%s)",
                host, bind_port, config.role, config.group_id)
    server.run(transport="http", host=host, port=bind_port)
