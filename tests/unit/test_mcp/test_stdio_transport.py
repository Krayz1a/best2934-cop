"""The stdio transport, which is what makes a raw TCP door possible.

gal-roy1 proposed carrying the match over a plain socket instead of HTTP, on the
grounds that every transport bug either team shipped this month was an HTTP bug
rather than a game bug -- a forgotten ``mcp-session-id``, a missing ``Accept``, a
free-tier interstitial, a half-closed SSE stream. MCP's stdio transport is
already newline-delimited JSON-RPC 2.0, so a socket carrying those bytes is a
valid MCP transport and nothing above it changes.

Verified for real before these tests were written: ``socat`` in front of
``serve --transport stdio``, dialled by gal-roy1's own published client code
unmodified, returned all 15 tools and a correct ``hello``. What is pinned here
is the part a live check cannot pin cheaply -- that asking for stdio never binds
a port, and that asking for HTTP is completely unaffected.
"""

from __future__ import annotations

from p2pchase.mcp import server as server_module


class _Recorder:
    """Stands in for the FastMCP server and records how it was run."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _run(monkeypatch, peer_config, **kwargs) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(server_module, "build_server", lambda *a, **k: recorder)
    server_module.serve(peer_config, handlers=object(), **kwargs)
    return recorder


def test_stdio_never_binds_a_port(monkeypatch, peer_config):
    """stdin and stdout are the socket; a host or port here would be a bug.

    This is the whole safety property. Exposing the port is the tunnel's job
    (rule 10), and a stdio server that also opened a listener would publish one
    without anyone asking for it.
    """
    recorder = _run(monkeypatch, peer_config, transport="stdio", port=8801)

    assert recorder.calls == [{"transport": "stdio"}]


def test_http_is_untouched_and_still_the_default(monkeypatch, peer_config):
    """A second door, not a move. HTTP stays primary and unchanged."""
    recorder = _run(monkeypatch, peer_config, host="127.0.0.1", port=8801)

    call = recorder.calls[0]
    assert call["transport"] == "http"
    assert call["host"] == "127.0.0.1" and call["port"] == 8801
    assert "middleware" in call, "the Accept probe middleware must survive"
