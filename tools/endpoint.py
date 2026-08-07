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

There is no half-time handover any more. Both roles are served at once behind
``tools/frontdoor.py`` -- ``/cop/mcp`` and ``/thief/mcp`` on one reserved domain
-- so the endpoint is already answering for whichever role the next sub-game
assigns. ``take``, which used to move the tunnel between the two, now refuses:
under the odd/even convention the role flips every sub-game, and a tunnel that
follows it is torn down five times per series, each time exactly where the next
handshake lands.

``status`` is the one worth trusting: it proves reachability the same way the
opponent will discover it, by completing a handshake rather than by looking at a
process table. A listening socket is not an endpoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NGROK_API = "http://127.0.0.1:4040/api/tunnels"
#: Where the tunnel terminates: the shared front door, never a role's own port.
FRONT_PORT = 8800
#: Whose pairing terms the derivations below use. Overridable because the role
#: convention is per-opponent now: the thief's first sub-game is 4 against
#: gal-roy1 and 2 against imreeyal, and a hard-coded opponent would start the
#: peer on a number the other one's step 0 disagrees with.
OPPONENT = os.environ.get("P2PCHASE_OPPONENT", "gal-roy1")
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
    rather than fixed at 1. Which rule depends on the opponent: under the
    first-half convention the thief's first sub-game is 4, under odd/even it is
    2. Hard-coding either would start the peer on a number the opponent's next
    step 0 disagrees with.
    """
    sys.path.insert(0, str(REPO / "src"))
    from p2pchase.domain import roles

    setup = _setup()
    mine = setup["game"]["group_id"]
    convention = str(setup.get("opponents", {}).get(OPPONENT, {}).get(
        "role_convention", roles.DEFAULT_CONVENTION))
    return next((n for n in range(1, 7)
                 if roles.role_for(mine, OPPONENT, n, convention=convention) == _role()), 1)


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
    from fastmcp.client.transports import StreamableHttpTransport

    sys.path.insert(0, str(REPO / "src"))
    from p2pchase.mcp.client import TUNNEL_HEADERS

    # The URL already ends in the role's own path now (/cop/mcp, /thief/mcp),
    # so appending /mcp would ask the front door for a route that is not there
    # and report a healthy endpoint as a 404.
    endpoint = url if url.rstrip("/").endswith("/mcp") else url.rstrip("/") + "/mcp"

    async def ask() -> str:
        async with Client(StreamableHttpTransport(
                endpoint, headers=dict(TUNNEL_HEADERS))) as client:
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
    usually launched from a shell that never sourced ``.env``. The peer started
    here would otherwise sign its step-0 declaration with an empty secret and
    say nothing about it (rule 24, and ``declaration.py`` falls back to an
    unkeyed digest rather than failing).

    One parser, shared with the CLI: two copies of a config format drift, and
    the pair that disagrees here is a peer whose declaration verifies when
    launched one way and not the other.
    """
    sys.path.insert(0, str(REPO / "src"))
    from p2pchase.shared import dotenv

    return dotenv.environment(REPO)


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

    # Through the *published* URL, not the tunnel root: the tunnel now fronts
    # both roles, and its root proves nothing about the one this repo serves.
    group = _handshake(expected)
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
    if not _listening(FRONT_PORT):
        print("starting the front door...")
        _detached([str(REPO / ".venv" / "bin" / "python"), str(REPO / "tools" / "frontdoor.py")],
                  REPO / "logs" / "frontdoor.log")
        time.sleep(3)
    if not _tunnel_url():
        # The tunnel terminates on the FRONT DOOR, never on a role's own port.
        # Pointed at a role, it would serve that role alone and the other half
        # of the series would be unreachable at the address we published.
        print("starting the tunnel...")
        _detached(["ngrok", "http", str(FRONT_PORT), "--log", "stdout", "--log-format", "logfmt"],
                  REPO / "logs" / "ngrok.log")
    for _ in range(20):
        time.sleep(1)
        if _listening(port) and _tunnel_url():
            break
    return status()


def take() -> int:
    """Refuses. The handover it performed no longer exists -- and would now break.

    ``take`` moved the single tunnel from one role's port to the other's at half
    time. That was right while the role changed once per series. It is wrong
    twice over now.

    It is *unnecessary* because both roles are served at once, behind
    ``tools/frontdoor.py``, at ``/cop/mcp`` and ``/thief/mcp`` on one reserved
    domain. Nothing needs moving; the endpoint is already answering for whichever
    role the next sub-game assigns.

    It is *harmful* because the tunnel it would kill is now shared. Under the
    odd/even convention the role flips at every sub-game, so a repointing
    handover runs five times per series and drops the endpoint each time --
    precisely where the next handshake lands. imreeyal lost a window to that and
    told us so. Killing the agent here would take BOTH roles down, not one.

    Left in place rather than deleted because the command is written down in
    docs and in an opponent's notes, and a command that vanishes silently is
    worse than one that explains itself.
    """
    print("take: refused -- both roles are served at once and nothing needs moving.\n"
          "  cop    https://monogram-radio-blooper.ngrok-free.dev/cop/mcp\n"
          "  thief  https://monogram-radio-blooper.ngrok-free.dev/thief/mcp\n"
          "Run 'uv run python tools/frontdoor.py --check' to see both upstreams,\n"
          "or 'status' to prove this role reachable with a real handshake.")
    return 1


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command not in {"status", "up", "take"}:
        print(__doc__)
        sys.exit(2)
    sys.exit({"status": status, "up": up, "take": take}[command]())
