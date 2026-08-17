#!/usr/bin/env python
"""Prove our reference-v3 handshake and audit cross a real socket.

    python tools/reference_rehearsal.py

The suite reaches the reference-v3 driver through in-memory ``Inboxes``, which
is the right shape for testing a round and blind to everything between the
driver and a peer: the HTTP transport, ``peer_host``'s dialect selection, and
the wiring that hands the driver its sealed step-0. Every one of those was
correct in a unit test on 2026-08-17 while anrbj666 read
``opponent_step_zero: null`` for the third day running -- the record was always
right and nobody was sending it.

So this stands a peer that publishes **their** surface and nothing of ours, on
a real port, and drives the real ``p2pchase play`` at it. The peer is silent on
purpose: it accepts and never answers. That is enough, because the two things
worth proving both happen at the edges of a sub-game rather than inside one --
the agreement goes out before move one, and ``exchange_chains`` submits our
audit on every path out including a stall. A silent peer reaches both in about
half a minute and needs no game logic to be trusted.

Exit status is 0 when both crossed and 1 when either did not. Nothing here
touches a real opponent or the network.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from fastmcp import FastMCP

from p2pchase.mcp.reference_v3_server import Inboxes, register_reference_v3

REPO = Path(__file__).resolve().parent.parent
#: Long enough for the handshake and a stall, short enough to run by hand.
KNOCK_WAIT_SEC = "15"
RUN_TIMEOUT_SEC = 180


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def stand_peer(port: int) -> Inboxes:
    """A peer publishing anrbj666's four tool names and playing nothing.

    ``negotiate`` is added here rather than coming from
    :func:`register_reference_v3`, because on our own server that queue is fed
    by :class:`PeerHandlers` -- we publish one ``negotiate`` for every dialect.
    A peer that did not publish it at all would fail our handshake for the
    wrong reason and prove nothing about the payload.
    """
    inboxes = Inboxes()
    mcp = FastMCP("fake-reference-peer")
    register_reference_v3(mcp, inboxes)

    @mcp.tool
    def negotiate(message: dict) -> dict:
        """Accept a pushed agreement. Their client ignores our answer anyway."""
        inboxes.agreements.append(dict(message))
        return {"ok": True}

    thread = threading.Thread(
        target=lambda: mcp.run(transport="http", host="127.0.0.1", port=port,
                               show_banner=False, log_level="error"),
        daemon=True, name="fake-peer")
    thread.start()
    time.sleep(3)
    return inboxes


def drive(peer_port: int, our_port: int) -> int:
    """Run the real entry point, so the dialect selection is exercised too."""
    environment = dict(os.environ, P2PCHASE_OPPONENT_WAIT_SEC=KNOCK_WAIT_SEC)
    completed = subprocess.run(
        [str(REPO / ".venv/bin/p2pchase"), "play", "--opponent", "rehearsal-peer",
         "--sub-game", "5",
         # No --game-id: the pairing derives a sorted one and our own guard
         # refuses a contradicting override, which is exactly what it is for.
         "--opponent-url", f"http://127.0.0.1:{peer_port}/mcp",
         "--port", str(our_port)],
        cwd=REPO, env=environment, capture_output=True, text=True,
        timeout=RUN_TIMEOUT_SEC, check=False)
    tail = (completed.stdout + completed.stderr).strip().splitlines()
    for line in tail[-25:]:
        print("    driver| " + line)
    return completed.returncode


def check_agreement(inboxes: Inboxes) -> list[str]:
    """SPEC 7.2, and the placement that decides whether they refuse us."""
    if not inboxes.agreements:
        return ["FAIL  no agreement arrived at all"]
    ours = inboxes.agreements[0]
    problems = []
    if not isinstance(ours.get("sub_game_number"), int):
        problems.append("FAIL  no sub_game_number at the top level")
    elif ours["sub_game_number"] != 5:
        problems.append(f"FAIL  declared sub-game {ours['sub_game_number']}, drove 5")
    if "sub_game_number" in (ours.get("terms") or {}):
        problems.append("FAIL  sub_game_number is inside terms -- they refuse "
                        "on an exact dict compare, so this breaks every wire")
    return problems or [f"ok    7.2 declared: sub-game {ours['sub_game_number']}, "
                        f"role {ours.get('role')!r}, and terms untouched"]


def check_audit(inboxes: Inboxes) -> list[str]:
    """Rule 53: the sealed step-0 must be the FIRST record we disclose."""
    if not inboxes.audits:
        return ["FAIL  no audit arrived at all"]
    records = inboxes.audits[0].get("records") or []
    if not records:
        return ["FAIL  the audit carried no records"]
    first = records[0]
    payload = first.get("payload") or {}
    if payload.get("type") != "system_spec":
        return [f"FAIL  first record is {payload.get('type')!r}, not the step-0 "
                f"declaration -- this is the anrbj666 opponent_step_zero bug"]
    if not first.get("commit"):
        return ["FAIL  the step-0 record is not sealed; an unsealed "
                "declaration proves nothing (rule 24)"]
    return [f"ok    step-0 first and sealed: sub-game "
            f"{payload.get('sub_game_number')}, role {payload.get('role')!r}"]


#: Physics we run that NEITHER the 14 hashed terms NOR the scent fingerprint
#: covers, mapped to the value the reference emits. A key here is a key nobody
#: agreed: the handshake cannot catch it, so it can only be caught on our own
#: machine, before a build reaches an opponent.
#:
#: `pheromone_transmit_lag` is the reason this exists. We ran 1 for a week while
#: our own comment claimed it was "agreed and frozen by config_sha256" -- but
#: anrbj666 compare `terms`, and the lag is in neither. It stayed invisible
#: while our thief was frozen, because a stationary emitter publishes its live
#: cell under any lag, and surfaced only when the thief started walking and
#: their physics gate refused 34 frames of 35. Three days and a series to find
#: something that is one assertion to hold.
UNHASHED_PHYSICS = {"pheromone_transmit_lag": 0}


def check_contract() -> list[str]:
    """Every physics value we run is either agreed or at the reference default."""
    from p2pchase.runtime.reference_handshake import signed_agreement
    from p2pchase.sdk.sdk import P2PChaseSDK

    sdk = P2PChaseSDK.for_role(role="thief")
    terms = signed_agreement(sdk.negotiation, "rehearsal-peer")["terms"]
    problems = []
    for key, reference in UNHASHED_PHYSICS.items():
        if key in terms:
            continue  # covered by the handshake; the opponent can refuse it
        ours = sdk.config.shared.get("pheromones", {}).get(key, reference)
        if ours != reference:
            problems.append(
                f"FAIL  {key}={ours!r} is in no agreed term and is not the "
                f"reference default {reference!r} -- nobody agreed to this")
    return problems or [
        f"ok    contract: {len(terms)} agreed terms, and every unhashed "
        f"physics key at the reference default"]


def main() -> int:
    peer_port, our_port = free_port(), free_port()
    print(f"standing a reference-v3 peer on 127.0.0.1:{peer_port}, "
          f"driving from :{our_port}")
    inboxes = stand_peer(peer_port)
    code = drive(peer_port, our_port)
    print(f"the driver exited {code} (a stall against a silent peer is expected)")

    results = check_contract() + check_agreement(inboxes) + check_audit(inboxes)
    print("\n".join(results))
    print(f"\ninbox counts: agreements={len(inboxes.agreements)} "
          f"turns={len(inboxes.turns)} audits={len(inboxes.audits)} "
          f"refusals={len(inboxes.refusals)}")
    if inboxes.refusals:
        print("their validator refused: " + json.dumps(list(inboxes.refusals)[:3]))
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
