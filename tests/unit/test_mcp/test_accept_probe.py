"""The 406 diagnostic. It must explain, and it must not interfere.

Both halves matter. Explaining turns a status code nobody remembers the meaning
of into a line naming the offending header -- which is the difference between
diagnosing a silent opponent in a minute and in three hours. Not interfering
matters more: this sits in front of every message of every match, so a probe
that swallowed a request or raised on an odd header would cost the match it was
added to protect.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from p2pchase.mcp.accept_probe import AcceptProbe, probe_middleware


class _App:
    """The ASGI app underneath. Records that it was reached, unchanged."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, scope, receive, send) -> None:
        self.calls.append(scope)


def _scope(accept: str | None, method: str = "POST") -> dict:
    headers = [(b"user-agent", b"peer/1.0")]
    if accept is not None:
        headers.append((b"accept", accept.encode()))
    return {"type": "http", "method": method, "headers": headers}


def _run(scope: dict) -> _App:
    app = _App()
    asyncio.run(AcceptProbe(app)(scope, None, None))
    return app


@pytest.mark.parametrize("accept", [
    None,
    "application/json",
    "*/*",
    "text/event-stream",
])
def test_a_header_that_will_be_refused_is_explained(accept, caplog):
    with caplog.at_level(logging.ERROR):
        app = _run(_scope(accept))

    assert app.calls, "the probe must never swallow the request"
    assert "406" in caplog.text
    assert "application/json, text/event-stream" in caplog.text


def test_an_acceptable_header_says_nothing(caplog):
    with caplog.at_level(logging.ERROR):
        app = _run(_scope("application/json, text/event-stream"))

    assert app.calls
    assert caplog.text == ""


def test_the_request_is_passed_through_untouched(caplog):
    """Diagnostic only. Being lenient here would mean answering with an event
    stream to a client that just said it cannot read one -- a worse failure than
    an honest refusal, because it fails later and quieter."""
    scope = _scope("application/json")
    app = _run(scope)
    assert app.calls == [scope]


def test_non_post_traffic_is_left_alone(caplog):
    """The SSE stream itself is a GET, and it legitimately accepts only one type."""
    with caplog.at_level(logging.ERROR):
        _run(_scope("text/event-stream", method="GET"))
    assert caplog.text == ""


def test_the_middleware_list_is_usable_by_the_server():
    assert len(probe_middleware()) == 1


def test_outbound_calls_carry_the_ngrok_interstitial_opt_out():
    """A readiness check that cannot fail is not a readiness check.

    ngrok's free tier answers a bare request with an HTML interstitial and
    status **200**. That is worse than an error in both directions: a dead peer
    reads as "200, alive", and a live peer can never show the 406 that proves an
    MCP server is really there. imreeyal lost a match window to it and told us.

    The interstitial is served on User-Agent, so our client -- not a browser --
    was already getting through. That is a property of a dependency's default
    header rather than a decision we made, which is exactly the kind of thing
    that changes under you on an upgrade.
    """
    from p2pchase.mcp.client import TUNNEL_HEADERS, PeerClient

    transport = PeerClient("https://example.ngrok-free.dev/mcp")._transport()
    assert TUNNEL_HEADERS["ngrok-skip-browser-warning"] == "1"
    assert transport.headers["ngrok-skip-browser-warning"] == "1"


def test_an_in_process_server_is_not_wrapped_in_an_http_transport():
    """The rehearsal and most of this suite hand ``PeerClient`` a live FastMCP
    object rather than a URL. Wrapping that in an HTTP transport raises before
    a single tool is called, which would trade a real gate for a header."""
    from fastmcp import FastMCP

    from p2pchase.mcp.client import PeerClient

    server = FastMCP("probe")
    assert PeerClient(server)._transport() is server
