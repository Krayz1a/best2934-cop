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

from ..domain import roles
from ..mcp.client import PeerClient
from ..mcp.handlers import PeerHandlers
from ..reports.naming import make_game_id, now_iso
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


class RoleClashError(RuntimeError):
    """``--role`` contradicts the role the agreed rule derives for this sub-game."""


class GameIdClashError(RuntimeError):
    """Raised when --game-id contradicts the id the pairing derives."""


def _game_id_for(args: Any, config: Any) -> str:
    """The sorted, order-independent id for this pairing.

    Derived rather than typed, for the same reason the role is: there is
    exactly one right answer once --opponent names who we are playing, and the
    operator should not have to reproduce it at match time.

    Two real failures in one evening, both from a typed id:

    ``best2934-vs-anrbj666-f2`` -- a suffix added to keep two friendlies apart.
    ``opponent_in_game_id`` splits on ``-vs-``, so the opponent parsed as
    "anrbj666-f2", the pairing lookup missed, and every per-pairing term fell
    back to a default: first_half instead of odd_even, own instead of league.
    Sub-game 2 would have put two thieves on the board.

    ``best2934-vs-anrbj666`` -- unsorted. `make_game_id` has always sorted, and
    nothing called it. It was right against imreeyal and gal-roy1 for one
    reason: `best2934` sorts before both. anrbj666 is the first opponent ahead
    of us alphabetically and the first pairing where it could show -- as a
    digest disagreement rather than an error, because game_id leads the SPEC-6
    scope while `game_uid` hashes `sorted([a, b])` and was never wrong.

    A contradicting id is refused rather than corrected, matching the role
    rule: an operator who typed an id meant it, and a peer that quietly played
    under a different name is stranger to debug than a message.
    """
    opponent = str(getattr(args, "opponent", "") or "")
    typed = str(getattr(args, "game_id", "") or "")
    if not opponent or opponent == config.group_id:
        return typed
    derived = make_game_id(config.group_id, opponent)
    if typed in ("", "local-rehearsal", derived):
        return derived
    raise GameIdClashError(
        f"--game-id {typed!r} contradicts the id this pairing derives: "
        f"{derived!r}. The id is sorted so both peers reach the same name, and "
        f"it leads the mutual_agreement scope. Drop --game-id to let the "
        f"pairing decide.")


def _sdk_for_sub_game(args: Any) -> P2PChaseSDK:
    """Load the SDK for the side we are actually meant to be playing.

    Roles across a series are derived, not chosen (:mod:`p2pchase.domain.roles`),
    so once ``--opponent`` names who we are playing there is exactly one right
    answer and the operator should not have to work it out at the keyboard at
    match time. Omitting ``--role`` lets the rule pick, including which config
    directory to load.

    Naming a side that contradicts the rule is refused rather than silently
    corrected. Both are defensible; refusing wins because an operator who typed
    a role meant it, and a peer that quietly played the other side would be a
    stranger thing to debug than a message saying which side it should be.
    """
    sdk = _sdk(args)
    opponent = str(getattr(args, "opponent", "") or "")
    if not opponent or opponent == sdk.config.group_id:
        return sdk
    derived = roles.role_for(sdk.config.group_id, opponent,
                             int(getattr(args, "sub_game", 1)), sdk.config.num_sub_games,
                             sdk.config.role_convention(opponent))
    if derived == args.role:
        return sdk
    if getattr(args, "role_explicit", False):
        raise RoleClashError(
            f"--role {args.role} contradicts the agreed rule: sub-game "
            f"{args.sub_game} against {opponent} makes us the {derived}. "
            f"Drop --role to let the rule decide, or fix the sub-game number.")
    LOGGER.info("the role rule makes us the %s for sub-game %s against %s",
                derived, getattr(args, "sub_game", 1), opponent)
    args.role = derived
    return _sdk(args)


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

    try:
        sdk = _sdk_for_sub_game(args)
    except RoleClashError as error:
        print(error)
        return EXIT_CONFIG
    game_id = _game_id_for(args, sdk.config)
    session = PeerSession(sdk.config, args.role, game_id, sub_game=args.sub_game)
    handlers = PeerHandlers(sdk.config, session)
    try:
        run_server(sdk.config, handlers, host=args.host, port=args.port,
                   transport=getattr(args, "transport", "http"))
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
    try:
        sdk = _sdk_for_sub_game(args)
    except RoleClashError as error:
        print(error)
        return EXIT_CONFIG
    url = args.opponent_url or sdk.config.opponent_url
    if not url:
        print("no opponent URL: pass --opponent-url or set network.opponent_url")
        return EXIT_CONFIG
    print(f"role           : {args.role} (sub-game {args.sub_game})")

    game_id = _game_id_for(args, sdk.config)
    session = PeerSession(sdk.config, args.role, game_id,
                          sub_game=args.sub_game, seed=args.seed)
    client = PeerClient(url, timeout=float(sdk.config.turn_timeout))
    runner = PeerRunner(sdk.config, session, client,
                        signing_secret=os.environ.get("P2PCHASE_SIGNING_SECRET", ""))
    handlers = PeerHandlers(sdk.config, session)
    port = args.port or sdk.config.my_port

    started = now_iso()
    outcome, handshake = asyncio.run(_play(runner, handlers, sdk, args.host, port, url))
    print(f"outcome        : {outcome.outcome}")
    print(f"steps          : {outcome.steps}")
    print(f"opponent audit : {outcome.opponent_audit.get('passed')}")
    # The breakdown, not just the verdict: "False" alone cannot distinguish a
    # forged step from a withheld one, and those are different accusations.
    print(f"audit detail   : {outcome.opponent_audit}")
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
            # From the session, which was built with the DERIVED id --
            # never from args, which is what a typed id gets wrong.
            session.game_id, args.sub_game, opponent, outcome, started, now_iso(),
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
