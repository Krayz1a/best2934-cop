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
import json
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

#: Streamable-HTTP refuses anything that will not take both media types.
ACCEPT = {"Accept": "application/json, text/event-stream",
          "Content-Type": "application/json"}

HELLO = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "best2934-frontdoor", "version": "1"}}}


def _forwardable(headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


def _is_bare_tools_list(request: Request, body: bytes) -> bool:
    """A sessionless ``tools/list`` -- the league's most common readiness probe.

    A stateful MCP server answers this with ``400 Bad Request: Missing session
    ID``, which is correct and useless. imreeyal's gate reads that reply as
    "something is serving, but it is not a cop-thief peer" and refuses the
    window against a perfectly healthy peer -- deterministically, 12 times out
    of 12. They fixed their gate and told us, but the next team will not: they
    will conclude we are not a peer and never say why. That is a quiet way to
    lose an opponent, and rule 6 charges us for the stall either way.

    So we answer it, and answer it *honestly* -- see :func:`_probe_tools`. A
    spec-compliant client never reaches this path, because it sends
    ``initialize`` first and carries the session id afterwards.
    """
    if request.method != "POST" or request.headers.get("mcp-session-id"):
        return False
    try:
        message = json.loads(body)
    except (ValueError, TypeError):
        return False
    return isinstance(message, dict) and message.get("method") == "tools/list"


async def _probe_tools(role: str, message_id) -> JSONResponse:
    """Run a real handshake upstream and return the peer's real tool list.

    Emphatically not a canned answer. A readiness probe exists to find out
    whether the peer is alive, so replying from a hardcoded list would turn the
    one check the league runs against us into a check that can never fail --
    strictly worse than the 400 it replaces, because it would report us healthy
    while we were dead. Every field here comes from the live peer, and if the
    peer is down this fails exactly as it should.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        session = await _open_session(client, UPSTREAM[role])
        listed = await client.post(UPSTREAM[role],
                                   headers={**ACCEPT, "mcp-session-id": session},
                                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        await client.delete(UPSTREAM[role], headers={"mcp-session-id": session})
    body = _sse_payload(listed.text)
    return JSONResponse({"jsonrpc": "2.0", "id": message_id,
                         "result": body.get("result", {})})


async def _open_session(client: httpx.AsyncClient, url: str) -> str:
    """Complete a handshake upstream and return the session id it issued.

    Whoever calls this owns the ``DELETE``. Sessions are server-side state that
    a peer holds until it is told to let go, and 255 of them accumulated in
    each of our two peers today -- see :func:`_upstream_status` for a third of
    that total, and for why the tidy-looking probe was the leak.
    """
    opened = await client.post(url, headers=ACCEPT, json=HELLO)
    session = opened.headers.get("mcp-session-id", "")
    if not session:
        raise httpx.HTTPError("upstream refused a session")
    await client.post(url, headers={**ACCEPT, "mcp-session-id": session},
                      json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return session


def _sse_payload(text: str) -> dict:
    """Pull the JSON out of a streamable-HTTP reply, which arrives as SSE."""
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(text) if text.strip() else {}


async def _proxy(request: Request, role: str) -> StreamingResponse:
    """Relay one request to a peer, streaming both directions."""
    body = await request.body()
    if _is_bare_tools_list(request, body):
        try:
            return await _probe_tools(role, json.loads(body).get("id"))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": "server-error",
                 "error": {"code": -32001,
                           "message": f"the {role} peer is not answering: {exc}"}},
                status_code=502)
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
    """Ask each peer whether it speaks MCP, by opening a session and closing it.

    This used to send a bare ``GET`` and read the resulting **406** as healthy:
    the transport requires an Accept of both JSON and text/event-stream, so a
    live MCP server refuses a plain GET itself, and nothing else answers that
    way. Clever, cheap, and it was quietly poisoning the process it checked.

    FastMCP allocates the session *before* it inspects Accept, so every probe
    created a transport that was then abandoned -- no session id ever came back
    to us, so there was nothing to ``DELETE``. 83 of the cop's 261 orphaned
    sessions today were ours, and 71 of the thief's 249. The monitor was a
    third of the leak it existed to notice.

    So the probe now completes a real handshake and hangs up after it, which
    costs one extra local round trip and is a strictly better question besides:
    a 406 only proved something was listening and fussy about media types,
    while a session id proves the peer can actually start a sub-game.

    Deliberately still not a process check. A listening socket is not an
    endpoint -- that assumption is what let us tell an opponent we were up
    while we had been dead for nine hours.
    """
    verdicts = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for role, url in UPSTREAM.items():
            try:
                session = await _open_session(client, url)
                await client.delete(url, headers={"mcp-session-id": session})
                verdicts[role] = "up"
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
