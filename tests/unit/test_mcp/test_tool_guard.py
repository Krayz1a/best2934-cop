"""The last line before a fault of ours becomes a technical loss for both.

Rule 6 is the reason this exists rather than tidiness. An exception escaping a
tool call reaches the opponent as a transport error they cannot tell from a
crash, and the stalled sub-game is charged to *both* teams -- so our bug becomes
their loss, which is why gal-roy1 was entitled to ask for it.

What is checked here is that the guard answers, names the tool, and does not
interfere with a call that works.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from p2pchase.mcp.tool_guard import build_guard


def _context(tool: str = "reveal_step"):
    return SimpleNamespace(message=SimpleNamespace(name=tool))


def _run(guard, context, call_next):
    """The guard answers with a ToolResult, not a bare dict.

    Returning the dict raises inside FastMCP's own result handling, which
    would replace one escaping exception with another in the single place
    that exists to stop exceptions escaping. So the tests read the same
    structure the wire carries.
    """
    result = asyncio.run(guard.on_call_tool(context, call_next))
    return getattr(result, "structured_content", result)


def test_a_working_call_passes_straight_through():
    async def call_next(context):
        return {"ok": True, "step": 3}

    assert _run(build_guard(), _context(), call_next) == {"ok": True, "step": 3}


def test_an_unexpected_fault_becomes_a_refusal_naming_the_tool(caplog):
    async def call_next(context):
        raise ZeroDivisionError("division by zero")

    with caplog.at_level(logging.ERROR):
        answer = _run(build_guard(), _context("sample_scent"), call_next)

    assert answer["ok"] is False
    assert answer["fault"] is True
    assert answer["tool"] == "sample_scent"
    assert "ZeroDivisionError" in answer["reason"]


def test_the_traceback_stays_on_our_side(caplog):
    """They need to know we refused and roughly why. They do not need our stack,
    and the log is where a diagnosis belongs now that it goes to a file."""
    async def call_next(context):
        raise RuntimeError("something nobody anticipated")

    with caplog.at_level(logging.ERROR):
        answer = _run(build_guard(), _context(), call_next)

    assert "Traceback" in caplog.text
    assert "Traceback" not in answer["reason"]


@pytest.mark.parametrize("failure", [KeyError("cells"), TypeError, ValueError("bad step")])
def test_no_kind_of_exception_escapes(failure):
    async def call_next(context):
        raise failure

    answer = _run(build_guard(), _context(), call_next)
    assert answer["ok"] is False
