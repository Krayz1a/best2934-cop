"""CLI commands that touch the network or open a window.

Separated from :mod:`p2pchase.cli.commands` for one practical reason: these
three need optional dependencies (FastMCP, Tkinter) that a grader checking out
the repository may not have installed. Keeping them apart means ``p2pchase
verify`` and ``p2pchase local-match`` still work on a bare checkout, and the
import error, when it comes, names the one thing that is missing.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from ..mcp.client import PeerClient
from ..mcp.handlers import PeerHandlers
from ..reports.naming import now_iso
from ..runtime.peer import PeerRunner
from ..runtime.peer_host import host_and_play
from ..runtime.peer_session import PeerSession
from ..sdk import P2PChaseSDK
from .commands import EXIT_CONFIG, EXIT_FAILED, EXIT_OK

LOGGER = logging.getLogger(__name__)


def _sdk(args: Any) -> P2PChaseSDK:
    return P2PChaseSDK.for_role(
        role=args.role,
        config_dir=getattr(args, "config_dir", None),
        signing_secret=os.environ.get("P2PCHASE_SIGNING_SECRET", ""),
    )


def serve(args: Any) -> int:
    """Run only the server half of this peer, until interrupted.

    Useful for letting an opponent check reachability and fingerprints before
    either side starts a sub-game -- but a match is played with ``play``, which
    serves and plays over one session. Serving here and playing in a second
    process would leave the turn loop waiting on an inbox it cannot see.

    Binds loopback by default. Publishing the port is the tunnel's job (ngrok /
    Localtonet, rule 10), so nothing is exposed to the internet by accident.
    """
    from ..mcp.server import MissingTransportError
    from ..mcp.server import serve as run_server

    sdk = _sdk(args)
    session = PeerSession(sdk.config, args.role, args.game_id, sub_game=args.sub_game)
    handlers = PeerHandlers(sdk.config, session)
    try:
        run_server(sdk.config, handlers, host=args.host, port=args.port)
    except MissingTransportError as error:
        print(error)
        return EXIT_CONFIG
    except KeyboardInterrupt:
        print("\nserver stopped")
    return EXIT_OK


def play(args: Any) -> int:
    """Play one sub-game against a live opponent over MCP.

    This process is the whole peer: it serves our tools and calls theirs, over
    one session. See :mod:`p2pchase.runtime.peer_host` for why that cannot be
    split across two processes.
    """
    sdk = _sdk(args)
    url = args.opponent_url or sdk.config.opponent_url
    if not url:
        print("no opponent URL: pass --opponent-url or set network.opponent_url")
        return EXIT_CONFIG

    session = PeerSession(sdk.config, args.role, args.game_id,
                          sub_game=args.sub_game, seed=args.seed)
    client = PeerClient(url, timeout=float(sdk.config.turn_timeout))
    runner = PeerRunner(sdk.config, session, client)
    handlers = PeerHandlers(sdk.config, session)
    port = args.port or sdk.config.my_port

    started = now_iso()
    outcome, handshake = asyncio.run(_play(runner, handlers, sdk, args.host, port, url))
    print(f"outcome        : {outcome.outcome}")
    print(f"steps          : {outcome.steps}")
    print(f"opponent audit : {outcome.opponent_audit.get('passed')}")
    if outcome.aborted:
        print(f"aborted        : {outcome.reason}")
    for path in _write_artifacts(sdk, session, args, handshake, outcome, started):
        print(f"artifact       : {path}")
    return EXIT_FAILED if outcome.aborted else EXIT_OK


def _write_artifacts(sdk: P2PChaseSDK, session: PeerSession, args: Any,
                     handshake: dict[str, Any], outcome: Any, started: str) -> list[Any]:
    """Persist what the sub-game produced, including an aborted one.

    An abort still wrote real commitments and still has to be explicable to the
    opponent, so it gets its artifacts too; a technical loss with no log is
    indistinguishable from a team that walked away. A failure to *write* is
    reported and swallowed -- the game already happened, and raising here would
    turn a disk problem into a lost match.
    """
    opponent = str(handshake.get("group_id") or args.opponent or "unknown")
    try:
        return sdk.record_networked_sub_game(
            args.game_id, args.sub_game, opponent, outcome, started, now_iso(),
            session.talk.tokens_used, handshake)
    except OSError as error:
        LOGGER.error("could not write the match artifacts: %s", error)
        print(f"WARNING: artifacts not written: {error}")
        return []


async def _play(runner: PeerRunner, handlers: PeerHandlers, sdk: P2PChaseSDK,
                host: str, port: int, url: str):
    """Handshake first, then play. A mismatch stops the match before move one."""
    def agree(handshake: dict[str, Any]) -> str:
        agreement = sdk.agree_with(handshake)
        return "" if agreement.agreed else "; ".join(agreement.mismatches)

    return await host_and_play(runner, handlers, host, port, url, agree)


def gui(args: Any) -> int:
    """Open the live view of THIS peer's local truth (rules 8, 9)."""
    from ..ui.live_view import LiveViewUnavailableError, run_live_view

    sdk = _sdk(args)
    try:
        run_live_view(sdk, sub_games=args.sub_games, seed=args.seed,
                      opponent=args.opponent, text_mode=args.text)
    except LiveViewUnavailableError as error:
        print(error)
        return EXIT_CONFIG
    return EXIT_OK
