"""CLI command implementations -- thin wrappers over the SDK.

Not one of these functions contains business logic. They resolve arguments,
call :class:`~p2pchase.sdk.sdk.P2PChaseSDK`, print, and return an exit code.
That is the whole contract of guidelines §4.1: a presentation layer that
decides things cannot be reused by the next presentation layer, and cannot be
tested without it.

Each returns a POSIX exit code, so ``p2pchase verify`` can be used in a shell
pipeline or a CI gate rather than only read by a human.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..sdk import P2PChaseSDK
from ..shared.config import load_config
from ..shared.paths import artifacts_dir

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2


def _sdk(args: Any) -> P2PChaseSDK:
    """Build an SDK from the parsed arguments, honouring every override."""
    return P2PChaseSDK.for_role(
        role=args.role,
        config_dir=getattr(args, "config_dir", None),
        output_dir=Path(args.output) if getattr(args, "output", None) else None,
        signing_secret=os.environ.get("P2PCHASE_SIGNING_SECRET", ""),
    )


def describe(args: Any) -> int:
    """Print this peer's identity, fingerprints and hardware."""
    print(json.dumps(_sdk(args).describe(), indent=2, ensure_ascii=False))
    return EXIT_OK


def check_config(args: Any) -> int:
    """Validate the configuration against Appendix F without playing.

    Loaded non-strictly on purpose. Every other command must refuse to start on
    an illegal config, but this one exists to *diagnose* it -- and a diagnostic
    that raises before it can print the diagnosis is useless exactly when it is
    needed.
    """
    sdk = P2PChaseSDK(load_config(getattr(args, "config_dir", None), args.role, strict=False))
    problems = sdk.config.problems
    print(f"role            : {sdk.config.role}")
    print(f"group           : {sdk.config.group_id} ({', '.join(sdk.config.members)})")
    print(f"config_sha256   : {sdk.config.config_sha256()}")
    print(f"scent           : {sdk.negotiation.scent_fingerprint()}")
    print(f"turn timeout    : {sdk.config.turn_timeout}s")
    print(f"watchdog        : {sdk.config.watchdog_timeout}s")
    print(f"sub-games       : {sdk.config.num_sub_games}")
    print(f"report recipient: {sdk.config.email['recipient']}")
    if problems:
        print("\nILLEGAL CONFIGURATION — this match may not be played:")
        for problem in problems:
            print(f"  - {problem}")
        return EXIT_CONFIG
    print("\nConfiguration is legal under Appendix F.")
    return EXIT_OK


def handshake(args: Any) -> int:
    """Print the fingerprints an opponent must match before a match starts."""
    print(json.dumps(_sdk(args).handshake().as_dict(), indent=2, ensure_ascii=False))
    return EXIT_OK


def local_match(args: Any) -> int:
    """Play a full local series and write all four artifacts."""
    sdk = _sdk(args)
    result = sdk.run_series(args.opponent, sub_games=args.sub_games, seed=args.seed)
    print(f"game_id : {result.game_id}")
    print(f"final   : {json.dumps(result.final_result, ensure_ascii=False)}")
    print(f"tokens  : {result.tokens}")
    print("\nartifacts written:")
    for path in result.paths:
        print(f"  {path}")
    return EXIT_OK


def verify(args: Any) -> int:
    """Replay one log and print the verification banner."""
    sdk = _sdk(args)
    print(sdk.replay_text(args.log, limit=args.limit))
    return EXIT_OK if sdk.verify_log(args.log).passed else EXIT_FAILED


def audit(args: Any) -> int:
    """Audit every log an opponent disclosed (rule 36)."""
    sdk = _sdk(args)
    paths = [Path(p) for p in args.logs] or sorted(artifacts_dir().glob("log_*.json"))
    if not paths:
        print("no log files given and none found in artifacts/")
        return EXIT_CONFIG
    passed, verdicts = sdk.audit_opponent(paths)
    for verdict in verdicts:
        print(f"{Path(verdict.path).name:<48} {verdict.banner}")
    print("\nALL LOGS VERIFIED" if passed else "\nAUDIT FAILED — see the failures above")
    return EXIT_OK if passed else EXIT_FAILED


def send_report(args: Any) -> int:
    """Compose and optionally send the result report (rules 33-35)."""
    sdk = _sdk(args)
    receipt = sdk.reporting.send_result_file(args.result, dry_run=not args.live)
    print(json.dumps(receipt.as_dict(), indent=2, ensure_ascii=False))
    if not args.live:
        print("\nDry run: nothing was sent. Re-run with --live to deliver.")
    return EXIT_OK if (receipt.sent or not args.live) else EXIT_FAILED


def authorize_gmail(args: Any) -> int:
    """Run the one-time OAuth consent flow. Human-invoked, never automatic."""
    from ..infra.gmail_sender import GmailNotConfiguredError, authorize

    try:
        path = authorize(port=args.port)
    except GmailNotConfiguredError as error:
        print(f"Gmail is not set up: {error}")
        return EXIT_CONFIG
    print(f"Token written to {path}. It is git-ignored and must stay that way (rule 40).")
    return EXIT_OK


def gate_status(args: Any) -> int:
    """Print Gatekeeper queue health."""
    print(json.dumps(_sdk(args).gate_status(), indent=2))
    return EXIT_OK
