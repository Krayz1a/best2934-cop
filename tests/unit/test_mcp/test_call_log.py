"""Naming every tool that crossed the wire, in both directions.

The tally exists because of what a log of presences cannot show. On 2026-08-09
ours recorded thirteen runs of the negotiation service and we reported that to
an opponent as "your peer called negotiate thirteen times" -- an inference, and
we said so. The fact that would actually have found the bug was an absence:
**our client called nothing**. Nothing in a log of things that happened can say
that, which is why :func:`test_the_summary_names_a_direction_that_said_nothing`
is the test that matters here.
"""

from __future__ import annotations

import pytest

from p2pchase.mcp import call_log


@pytest.fixture(autouse=True)
def _clean():
    call_log.reset()
    yield
    call_log.reset()


def test_an_inbound_call_is_recorded_by_name():
    call_log.record_inbound("negotiate")
    assert call_log.INBOUND["negotiate"] == 1


def test_an_outbound_call_is_recorded_by_name():
    call_log.record_outbound("receive_turn")
    assert call_log.OUTBOUND["receive_turn"] == 1


def test_the_two_directions_do_not_share_a_tally():
    """Ours and theirs are the whole question; one number for both answers none."""
    call_log.record_inbound("negotiate")
    assert call_log.OUTBOUND["negotiate"] == 0


def test_repeats_are_counted_rather_than_collapsed():
    """Thirteen retries and one call are very different diagnoses."""
    for _ in range(13):
        call_log.record_inbound("negotiate")
    assert "negotiatex13" in call_log.summary()


def test_the_summary_names_a_direction_that_said_nothing():
    """The regression. Silence has to be printed, or it cannot be noticed.

    This is the line that would have named the 2026-08-09 stall in one look:
    they called us, we called nobody, and no log we had could say the second
    half out loud.
    """
    call_log.record_inbound("negotiate")
    summary = call_log.summary()
    assert "tools out: (none)" in summary
    assert "tools in: negotiatex1" in summary


def test_an_empty_summary_says_none_on_both_sides():
    assert call_log.summary() == "tools in: (none) | tools out: (none)"


def test_names_are_sorted_so_two_runs_are_diffable():
    call_log.record_inbound("submit_audit")
    call_log.record_inbound("negotiate")
    assert call_log.summary().index("negotiate") < call_log.summary().index("submit_audit")


def test_reset_clears_both_directions():
    call_log.record_inbound("a")
    call_log.record_outbound("b")
    call_log.reset()
    assert not call_log.INBOUND and not call_log.OUTBOUND


def test_the_client_records_the_tool_it_called(monkeypatch):
    """The outbound half, through the real :class:`PeerClient`.

    Recorded before the call rather than after it: a tool that fails to reach
    the opponent is precisely the one worth seeing in the tally, and logging on
    success only would have hidden a dead peer behind an empty list.
    """
    import asyncio

    from p2pchase.mcp.client import PeerClient, TransportError

    client = PeerClient("http://127.0.0.1:1/mcp", timeout=0.01)
    with pytest.raises(TransportError):
        asyncio.run(client.call("negotiate", {"message": {}}))
    assert call_log.OUTBOUND["negotiate"] == 1


def test_the_middleware_records_the_inbound_name():
    """Built as middleware, never as a decorator: a signature is a schema.

    Wrapping ``@mcp.tool`` would put a chance to alter a published argument
    name between us and every opponent, to solve a problem that has nothing to
    do with signatures -- the same reasoning as :mod:`p2pchase.mcp.tool_guard`.
    """
    import asyncio

    pytest.importorskip("fastmcp")
    middleware = call_log.build_call_log()

    class _Message:
        name = "receive_turn"

    class _Context:
        message = _Message()

    async def _next(_context):
        return "result"

    assert asyncio.run(middleware.on_call_tool(_Context(), _next)) == "result"
    assert call_log.INBOUND["receive_turn"] == 1


def test_a_nameless_call_is_recorded_rather_than_dropped():
    """An unrecognisable call is still evidence that somebody knocked."""
    import asyncio

    pytest.importorskip("fastmcp")
    middleware = call_log.build_call_log()

    class _Context:
        message = object()

    async def _next(_context):
        return None

    asyncio.run(middleware.on_call_tool(_Context(), _next))
    assert call_log.INBOUND["<unknown>"] == 1
