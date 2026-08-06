"""Dress rehearsal: a whole sub-game between four real processes, over sockets.

This is the check to run before a league match, and the only one that exercises
what a match actually exercises. The test suite reaches the handlers in-process;
that catches protocol bugs but it cannot catch transport bugs, because there is
no transport. A payload key the FastMCP tool signature does not declare, a
value FastMCP round-trips differently, a port already bound -- all of it is
invisible until something crosses a socket, and by then it is a live match and
rule 6 is charging both teams for the stall.

So: two servers and two clients, four processes, two ports, one sub-game.

    uv run python tools/rehearsal.py [--keep]

The opponent here is a *sparring partner*: a copy of this configuration under a
different group code, because rule 45 makes the code unique per team and the
handshake rightly refuses to play a mirror of itself. Both sides run under
scratch roots (``P2PCHASE_ROOT``), so a rehearsal writes no artifact that could
later be mistaken for a counted game -- rules 37 and 52 turn that mistake into a
false declaration.

Exit status is 0 only if both sides finished, agreed on the outcome, and each
passed the other's audit.

Localhost stands in for the tunnel. Rule 10 puts a real match across the public
internet, which changes the latency and nothing else about the protocol; what
this proves is that the protocol survives a socket at all.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Defaulted to the real ports so the rehearsal exercises the same binding a
#: match does, but overridable because the gate is worth running *while* the
#: league endpoint is serving. Taking the public endpoint down to run a check
#: is how an opponent finds a dead peer, and rule 6 charges the stall to both
#: teams -- we have already paid for that lesson once.
OUR_PORT = int(os.environ.get("P2PCHASE_REHEARSAL_PORT", "8801"))
THEIR_PORT = int(os.environ.get("P2PCHASE_REHEARSAL_PEER_PORT", str(OUR_PORT + 1)))
GAME_ID = "rehearsal-not-a-counted-game"
SPARRING_GROUP = "spar0001"


def _url(port: int) -> str:
    return f"http://127.0.0.1:{port}/mcp"


def _scratch_root(base: Path, name: str, group_id: str | None) -> Path:
    """A private project root: our real config, optionally under another code."""
    root = base / name
    shutil.copytree(REPO / "config", root / "config")
    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    if group_id is None:
        return root
    for setup in (root / "config").rglob("setup.json"):
        data = json.loads(setup.read_text(encoding="utf-8"))
        data["game"]["group_id"] = group_id
        data["game"]["group_name"] = f"{group_id} (sparring partner)"
        setup.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return root


def _run(root: Path, *args: str) -> subprocess.Popen:
    """Launch one CLI process rooted at ``root``, in this interpreter's env."""
    env = dict(os.environ, P2PCHASE_ROOT=str(root))
    return subprocess.Popen([sys.executable, "-m", "p2pchase", *args], cwd=REPO, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _busy(port: int) -> bool:
    """Is something already listening here? A clearer failure than a bind error."""
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _field(output: str, prefix: str) -> str:
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def _play(roots: dict[str, Path], timeout: float) -> dict[str, tuple[int, str]]:
    """Both peers at once -- the protocol is symmetric and must stay that way.

    Each ``play`` process serves its own tools and calls the other's, so this is
    two processes rather than four: one whole peer each, exactly the shape a
    league match has.
    """
    players = {
        "us (cop)": _run(roots["us"], "play", "--role", "police", "--game-id", GAME_ID,
                         "--port", str(OUR_PORT), "--opponent-url", _url(THEIR_PORT)),
        "them (thief)": _run(roots["them"], "play", "--role", "thief", "--game-id", GAME_ID,
                             "--port", str(THEIR_PORT), "--opponent-url", _url(OUR_PORT)),
    }
    results = {}
    for name, process in players.items():
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            output = (process.communicate()[0] or "") + "\nTIMED OUT"
        results[name] = (process.returncode, output or "")
    return results


def _verdict(results: dict[str, tuple[int, str]]) -> int:
    """Both sides finished, both audits passed, and the outcomes agree."""
    problems = []
    for name, (code, output) in results.items():
        if code != 0:
            problems.append(f"{name} exited {code}: {_field(output, 'aborted') or 'see log'}")
        if _field(output, "opponent audit") != "True":
            problems.append(f"{name} did not pass the opponent's audit")

    outcomes = {name: _field(output, "outcome") for name, (_, output) in results.items()}
    if not all(outcomes.values()):
        problems.append(f"missing outcome line: {outcomes}")
    elif len(set(outcomes.values())) != 1:
        # Rule 35: two peers that describe the same ending differently have no
        # agreed result to report, and the match is void for both.
        problems.append(f"the two peers disagree about the ending: {outcomes}")

    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        return 1
    print(f"PASS: both peers finished with {next(iter(outcomes.values()))!r}, "
          f"and each passed the other's audit.")
    return 0


def rehearse(timeout: float, keep: bool) -> int:
    base = Path(tempfile.mkdtemp(prefix="p2pchase-rehearsal-"))
    roots = {"us": _scratch_root(base, "us", None),
             "them": _scratch_root(base, "them", SPARRING_GROUP)}
    for port in (OUR_PORT, THEIR_PORT):
        if _busy(port):
            print(f"FAIL: port {port} is already in use; stop whatever is on it first")
            return 1
    print(f"starting two peers on {OUR_PORT} and {THEIR_PORT}; playing one sub-game...")
    results = _play(roots, timeout)

    for name, (code, output) in results.items():
        print(f"\n----- {name} (exit {code}) -----")
        for prefix in ("outcome", "steps", "opponent audit", "audit detail", "aborted"):
            if _field(output, prefix):
                print(f"  {prefix:<15}: {_field(output, prefix)}")
        if not _field(output, "outcome"):
            # It did not even reach the summary, so the summary cannot explain
            # it. The tail is the only thing that can.
            print("  no summary; last lines of its output:")
            for line in output.strip().splitlines()[-12:]:
                print(f"    {line}")
    print()
    status = _verdict(results)
    if keep:
        print(f"\nartifacts kept under {base}")
    else:
        shutil.rmtree(base, ignore_errors=True)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="seconds to allow one sub-game (default: 300)")
    parser.add_argument("--keep", action="store_true",
                        help="keep the scratch roots so the artifacts can be inspected")
    args = parser.parse_args()
    return rehearse(args.timeout, args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
