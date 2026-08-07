"""Command-line entry point. Parses arguments and dispatches; decides nothing.

Every subcommand delegates to :mod:`p2pchase.cli.commands` or
:mod:`p2pchase.cli.network_commands`, which in turn delegate to the SDK
(guidelines §4.1). Omitted from coverage in ``pyproject.toml`` because there is
no behaviour here to cover -- only wiring.

    uv run p2pchase check-config --role police
    uv run p2pchase local-match --opponent rival42 --sub-games 6
    uv run p2pchase verify --log artifacts/log_<game>_g01.json
    uv run p2pchase serve --role police --game-id best2934-vs-rival42
    uv run p2pchase play  --role thief  --game-id best2934-vs-rival42
"""

from __future__ import annotations

import argparse
import logging
import sys

from .. import constants
from ..shared import dotenv
from . import commands, network_commands


def _add_common(parser: argparse.ArgumentParser) -> None:
    # Defaulted in main() rather than here, so a command can tell an explicit
    # ``--role`` from an omitted one. Over the network the agreed rule derives
    # the role from the sub-game number, and silently overriding a side the
    # operator actually asked for would be worse than refusing.
    parser.add_argument("--role", default=None,
                        choices=[constants.ROLE_COP, constants.ROLE_THIEF],
                        help=f"which side this process plays "
                             f"(default: {constants.DEFAULT_ROLE}, or the agreed "
                             f"role rule when --opponent is given)")
    parser.add_argument("--config-dir", default=None,
                        help="override the config directory (default: config/<role>)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="p2pchase",
        description="best2934 — distributed Cops-and-Robbers over a P2P network.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, handler, help_text in (
        ("describe", commands.describe, "print identity, fingerprints and hardware"),
        ("check-config", commands.check_config, "validate the config against Appendix F"),
        ("handshake", commands.handshake, "print the pre-game fingerprints"),
        ("gate-status", commands.gate_status, "print Gatekeeper queue health"),
    ):
        child = sub.add_parser(name, help=help_text)
        _add_common(child)
        child.set_defaults(func=handler)

    match = sub.add_parser("local-match", help="play a full local series and write artifacts")
    _add_common(match)
    match.add_argument("--opponent", default="rival", help="opponent group id")
    match.add_argument("--sub-games", type=int, default=None, help="sub-games to play")
    match.add_argument("--seed", type=int, default=0, help="seed for reproducibility")
    match.add_argument("--output", default=None, help="artifact directory")
    match.set_defaults(func=commands.local_match)

    verify = sub.add_parser("verify", help="replay one log and verify its commit chain")
    _add_common(verify)
    verify.add_argument("--log", required=True, help="path to a log JSON file")
    verify.add_argument("--limit", type=int, default=None, help="steps to print")
    verify.set_defaults(func=commands.verify)

    audit = sub.add_parser("audit", help="audit an opponent's disclosed logs (rule 36)")
    _add_common(audit)
    audit.add_argument("logs", nargs="*", help="log files (default: artifacts/log_*.json)")
    audit.set_defaults(func=commands.audit)

    report = sub.add_parser("send-report", help="send the result report (rules 33-35)")
    _add_common(report)
    report.add_argument("--result", required=True, help="path to result_<game_id>.json")
    report.add_argument("--live", action="store_true",
                        help="actually send; without it the report is only composed")
    report.set_defaults(func=commands.send_report)

    auth = sub.add_parser("authorize-gmail", help="run the one-time OAuth consent flow")
    _add_common(auth)
    auth.add_argument("--port", type=int, default=0, help="local callback port")
    auth.set_defaults(func=commands.authorize_gmail)

    serve = sub.add_parser("serve", help="run only the server half (diagnostics; `play` serves too)")
    _add_common(serve)
    serve.add_argument("--host", default="127.0.0.1", help="bind address")
    serve.add_argument("--port", type=int, default=None, help="bind port")
    serve.add_argument("--transport", choices=("http", "stdio"), default="http",
                       help="stdio speaks the same JSON-RPC on stdin/stdout, for a "
                            "raw TCP door behind socat (see mcp/server.serve)")
    serve.add_argument("--game-id", default="local-rehearsal", help="game id to serve")
    serve.add_argument("--sub-game", type=int, default=1, help="sub-game number")
    serve.add_argument("--opponent", default="",
                       help="opponent group id; with it, the agreed role rule picks the side")
    serve.set_defaults(func=network_commands.serve)

    play = sub.add_parser("play", help="serve our tools and play one sub-game")
    _add_common(play)
    play.add_argument("--opponent-url", default="", help="opponent's MCP endpoint")
    play.add_argument("--host", default="127.0.0.1", help="bind address for our own server")
    play.add_argument("--port", type=int, default=None, help="bind port (default: my_port)")
    play.add_argument("--game-id", default="local-rehearsal", help="agreed game id")
    play.add_argument("--sub-game", type=int, default=1, help="sub-game number")
    play.add_argument("--opponent", default="",
                      help="opponent group id; with it, the agreed role rule picks the side")
    play.add_argument("--seed", type=int, default=0, help="seed for reproducibility")
    play.set_defaults(func=network_commands.play)

    gui = sub.add_parser("gui", help="open the live belief view for this peer")
    _add_common(gui)
    gui.add_argument("--seed", type=int, default=0, help="seed for reproducibility")
    gui.add_argument("--sub-games", type=int, default=1, help="sub-games to watch")
    gui.add_argument("--opponent", default="rival", help="opponent group id")
    gui.add_argument("--text", action="store_true", help="force the terminal renderer")
    gui.set_defaults(func=network_commands.gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.role_explicit = args.role is not None
    args.role = args.role or constants.DEFAULT_ROLE
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-28s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Before dispatch, because the secrets in ``.env`` are read at the point of
    # use and both of the things that need them fail *quietly* when they are
    # missing: an unsigned step-0 declaration, and an OAuth client looked for at
    # a relative path nobody put one at. Names only in the log -- never values.
    loaded = dotenv.load()
    if loaded:
        logging.getLogger(__name__).debug("loaded from .env: %s", ", ".join(loaded))
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
