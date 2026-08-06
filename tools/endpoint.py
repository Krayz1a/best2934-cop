"""Is our peer actually reachable from the internet? Bring it up if not.

Rule 10 puts a league match across the public internet, which means "our peer is
up" is a claim about three things, not one: the server is listening, the tunnel
agent is running, and a real MCP client can complete a handshake through the
public URL. Any of the three can fail alone, and two of them fail *silently* --
the process keeps its port, or the agent exits and leaves the port untouched.

This exists because we told an opponent the endpoint was up and it had been dead
for nine hours. Both halves had been started from a shell that later went away,
and nothing checked. Rule 6 charges both teams for a sub-game that never starts,
so an opponent knocking at a dead endpoint is not only our loss.

    uv run python tools/endpoint.py status   # exit 0 only if all three pass
    uv run python tools/endpoint.py up       # start what is missing, then check
    uv run python tools/endpoint.py take     # move the public URL to THIS role

``take`` is the half-time handover: run it in best2934-thief before sub-game 4
and in best2934-cop before sub-game 1. The opponent's address never changes.

``status`` is the one worth trusting: it proves reachability the same way the
opponent will discover it, by completing a handshake rather than by looking at a
process table. A listening socket is not an endpoint.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NGROK_API = "http://127.0.0.1:4040/api/tunnels"
OPPONENT = "gal-roy1"
GAME_ID = f"best2934-vs-{OPPONENT}"


def _role() -> str:
    """The side *this repository* ships as (rule 41: one repo per role).

    Read from ``constants.DEFAULT_ROLE`` rather than hard-coded, because it is
    the single value that differs between best2934-cop and best2934-thief. A
    hard-coded side would have the thief repo checking the cop's endpoint and
    reporting it healthy, which is worse than not checking at all.
    """
    sys.path.insert(0, str(REPO / "src"))
    from p2pchase import constants

    return constants.DEFAULT_ROLE


def _sub_game() -> int:
    """The first sub-game this repository's role actually plays.

    Serving under a role the agreed rule does not assign for the sub-game is
    refused by the CLI, and rightly -- so the number is derived from the rule
    rather than fixed at 1. In best2934-cop that is sub-game 1; in
    best2934-thief, where we hold the thief, it is the first of the second half.
    """
    sys.path.insert(0, str(REPO / "src"))
    from p2pchase.domain import roles

    mine = _setup()["game"]["group_id"]
    return next((n for n in range(1, 7) if roles.role_for(mine, OPPONENT, n) == _role()), 1)


def _setup() -> dict:
    path = REPO / "config" / _role() / "setup.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _port() -> int:
    return int(_setup()["network"]["my_port"])


def _expected_url() -> str:
    return str(_setup()["network"]["public_url"])


def _listening(port: int) -> bool:
    import socket

    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _tunnel_url() -> str:
    """The public URL the agent is currently serving, or ``""`` if it is not."""
    try:
        with urllib.request.urlopen(NGROK_API, timeout=5) as response:
            tunnels = json.load(response).get("tunnels", [])
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    return str(tunnels[0]["public_url"]) if tunnels else ""


def _handshake(url: str) -> str:
    """Complete a real ``hello`` through the public URL. Returns the group id.

    The only check that means anything. A socket can be listening and a tunnel
    can be registered while the path between them is broken -- and that combined
    failure is exactly what an opponent hits and we do not.
    """
    import anyio
    from fastmcp import Client

    async def ask() -> str:
        async with Client(url.rstrip("/") + "/mcp") as client:
            answer = await client.call_tool("hello", {"payload": {}})
            served = str(answer.data.get("role", ""))
            if served and served != _role():
                return f"!WrongRole: the URL serves {served!r}, this repo is {_role()!r}"
            return str(answer.data.get("group_id", ""))

    try:
        return anyio.run(ask)
    except Exception as error:  # noqa: BLE001 -- any failure is "not reachable"
        return f"!{type(error).__name__}: {error}"


def _environment() -> dict[str, str]:
    """The parent environment, plus anything ``.env`` defines that it lacks.

    A detached process inherits the shell that launched it, and this one is
    usually launched from a shell that never sourced ``.env``. Nothing reads
    that file on our behalf -- the code goes straight to ``os.environ`` -- so a
    peer started here would sign its step-0 declaration with an empty secret and
    say nothing about it (rule 24, and ``declaration.py`` falls back to an
    unkeyed digest rather than failing). Reading it here is the difference
    between a signed declaration and a quietly unsigned one.

    The real environment wins, so an operator who exports a value by hand is
    never overridden by a stale file.
    """
    import os

    environment = dict(os.environ)
    source = REPO / ".env"
    if not source.exists():
        return environment
    for line in source.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        name, _, value = entry.partition("=")
        environment.setdefault(name.strip(), value.strip())
    return environment


def _detached(args: list[str], log: Path) -> None:
    """Start a process that outlives this one, and every shell above it.

    ``start_new_session`` is the whole point: both halves of this endpoint have
    already been lost once to a parent shell going away, which is a nine-hour
    outage nobody noticed.
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        subprocess.Popen(args, cwd=REPO, stdout=handle, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True,
                         env=_environment())


def status() -> int:
    port, expected = _port(), _expected_url()
    print(f"role                  {_role()} (from sub-game {_sub_game()})")
    serving = _listening(port)
    tunnel = _tunnel_url()
    print(f"peer server on :{port}  {'up' if serving else 'DOWN'}")
    print(f"tunnel agent          {tunnel or 'DOWN'}")

    if not (serving and tunnel):
        return 1
    if not expected.startswith(tunnel):
        print(f"URL CHANGED: config expects {expected}, agent serves {tunnel} -- "
              f"the opponent has the old one and must be told")
        return 1

    group = _handshake(tunnel)
    reachable = not group.startswith("!")
    print(f"public handshake      {group if reachable else group}")
    return 0 if reachable else 1


def up() -> int:
    port = _port()
    if not _listening(port):
        print("starting the peer server...")
        _detached([str(REPO / ".venv" / "bin" / "p2pchase"), "serve",
                   "--role", _role(), "--opponent", OPPONENT, "--port", str(port),
                   "--game-id", GAME_ID, "--sub-game", str(_sub_game())],
                  REPO / "logs" / "serve.log")
    if not _tunnel_url():
        print("starting the tunnel...")
        _detached(["ngrok", "http", str(port), "--log", "stdout", "--log-format", "logfmt"],
                  REPO / "logs" / "ngrok.log")
    for _ in range(20):
        time.sleep(1)
        if _listening(port) and _tunnel_url():
            break
    return status()


def take() -> int:
    """Point the public URL at *this* repository's role, and prove it landed.

    The series changes roles halfway (rule 12) and rule 41 puts the two roles in
    two repositories, but there is one reserved domain and a free tunnel agent
    serves one port. So the handover is: move the tunnel, not the URL. The
    opponent keeps the address it already has, which matters because a URL that
    changes between halves is the failure that cost this project a day.

    ``up`` deliberately will not do this. It leaves a running agent alone, and
    that is right when the agent is already ours -- but between halves the
    running agent is the *other* role's, pointed at a port this repo does not
    serve. Left alone, every check passes while the wrong peer answers.
    """
    if _tunnel_url():
        print("stopping the tunnel that serves the other role...")
        subprocess.run(["pkill", "-f", "ngrok http"], check=False)
        for _ in range(10):
            time.sleep(1)
            if not _tunnel_url():
                break
    return up()


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command not in {"status", "up", "take"}:
        print(__doc__)
        sys.exit(2)
    sys.exit({"status": status, "up": up, "take": take}[command]())
