"""One public address, both roles, no changeover between sub-games.

Rule 41 puts each role in its own repository, so we run two peer processes. Until
now one tunnel pointed at whichever of them the current half of the series
needed, and it was moved at half time. That worked because the role convention
we had agreed swapped once, at sub-game 4.

It does not survive the convention the rest of the league plays. Under odd/even
the role flips at *every* sub-game -- cop on 1/3/5, thief on 2/4/6 -- so a
tunnel that follows the role is moved five times, and each move drops the
endpoint for a second or two exactly where the next handshake lands. An opponent
whose connect budget is 60s reads that as a protocol fault and scores a sub-game
nobody played. imreeyal lost a window to precisely this and told us so.

The property that actually matters is not how many addresses we publish. It is
that the endpoint is **already answering for whatever role comes next**, with no
infrastructure move in between. So both peers stay up permanently and this
process routes by path:

    https://<domain>/cop/mcp     -> 127.0.0.1:8801   (best2934-cop)
    https://<domain>/thief/mcp   -> 127.0.0.1:8802   (best2934-thief)
    https://<domain>/mcp         -> 127.0.0.1:8801   legacy, see below

``/mcp`` is kept because gal-roy1 holds that URL and we cannot reach them to
hand them a new one. It answers as the cop, which is what it has always been for
sub-games 1-3.

    uv run python tools/frontdoor.py            # serve on 127.0.0.1:8800
    uv run python tools/frontdoor.py --check    # report both upstreams

Streaming is forwarded rather than buffered. MCP's transport is
streamable-HTTP, so a proxy that collects the whole response before answering
turns every server-sent event into a message that arrives after the turn it
belonged to.
"""

from __future__ import annotations

import argparse
import sys

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

FRONT_PORT = 8800
UPSTREAM = {"cop": "http://127.0.0.1:8801/mcp", "thief": "http://127.0.0.1:8802/mcp"}

#: Connection-level headers that describe *this* hop and must not be relayed.
#: ``host`` goes too: the upstream must see its own address, not the tunnel's.
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "upgrade", "host",
              "proxy-authenticate", "proxy-authorization", "te", "trailer",
              "content-length"}

#: No read timeout. A peer holding a session open between turns is the normal
#: case, not a hang, and cutting it at 30s would break the very sub-games this
#: process exists to keep playable.
TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)


def _forwardable(headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


async def _proxy(request: Request, role: str) -> StreamingResponse:
    """Relay one request to a peer, streaming both directions."""
    body = await request.body()
    client = httpx.AsyncClient(timeout=TIMEOUT)
    upstream = client.build_request(
        request.method, UPSTREAM[role],
        headers=_forwardable(request.headers), content=body,
        params=dict(request.query_params))
    try:
        response = await client.send(upstream, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        return JSONResponse(
            {"jsonrpc": "2.0", "id": "server-error",
             "error": {"code": -32001,
                       "message": f"the {role} peer is not answering: {exc}"}},
            status_code=502)

    async def stream():
        try:
            async for chunk in response.aiter_raw():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(stream(), status_code=response.status_code,
                             headers=_forwardable(response.headers))


async def cop(request: Request):
    return await _proxy(request, "cop")


async def thief(request: Request):
    return await _proxy(request, "thief")


async def health(request: Request) -> JSONResponse:
    """Which roles are actually answering, for an opponent or for us.

    Deliberately not a process check. A listening socket is not an endpoint --
    that assumption is what let us tell an opponent we were up while we had
    been dead for nine hours.
    """
    return JSONResponse({"group_id": "best2934", "roles": await _upstream_status()})


async def _upstream_status() -> dict[str, str]:
    """Ask each peer whether it speaks MCP, by the answer only it can give.

    A 406 is the *healthy* reading here: the transport requires an Accept of
    both JSON and text/event-stream, so a bare GET that reaches a live MCP
    server is refused by the server itself. Anything else is either not our
    peer or not running.
    """
    verdicts = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for role, url in UPSTREAM.items():
            try:
                answer = await client.get(url)
                verdicts[role] = "up" if answer.status_code == 406 else f"http {answer.status_code}"
            except httpx.HTTPError as exc:
                verdicts[role] = f"down ({exc.__class__.__name__})"
    return verdicts


app = Starlette(routes=[
    Route("/cop/mcp", cop, methods=["GET", "POST", "DELETE"]),
    Route("/thief/mcp", thief, methods=["GET", "POST", "DELETE"]),
    Route("/mcp", cop, methods=["GET", "POST", "DELETE"]),
    Route("/health", health, methods=["GET"]),
])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=FRONT_PORT)
    parser.add_argument("--check", action="store_true", help="report upstreams and exit")
    args = parser.parse_args()

    if args.check:
        import asyncio

        status = asyncio.run(_upstream_status())
        for role, verdict in status.items():
            print(f"  {role:6s} {UPSTREAM[role]:28s} {verdict}")
        return 0 if all(v == "up" for v in status.values()) else 1

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
