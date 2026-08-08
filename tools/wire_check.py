#!/usr/bin/env python
"""Compare an opponent's wire surface with ours before anyone dials.

Run this against a peer's URL and it answers the two questions nobody asked on
2026-08-08: *which tools do they publish*, and *what does each one call its
arguments*. Both teams had agreed fourteen hashed terms, three lock digests and
a signature scheme, and discovered at the T that the two surfaces shared exactly
one tool name -- and that the one they shared spelled its argument differently.

    python tools/wire_check.py https://cop.imreeyal.com/mcp

Exit status is 0 when we could call them, 1 when we could not, 2 when they did
not answer. "Could call them" deliberately means *some* tool we know how to
drive, not all of ours: a reference-v3 peer implements none of our eleven names
and is perfectly playable. A surface we cannot drive at all is the failure.

Nothing here is a game action, so it is safe to run against a live opponent mid
series -- it opens one session, reads ``tools/list``, and closes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

sys.path.insert(0, "src")

from p2pchase.mcp import contracts  # noqa: E402
from p2pchase.mcp.wire_survey import ToolSurface, survey_text  # noqa: E402

TUNNEL_HEADERS = {"ngrok-skip-browser-warning": "1"}


async def _survey(url: str, timeout: float) -> list[ToolSurface]:
    """One session, ``tools/list``, out. Never calls a tool."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    transport: Any = url
    if isinstance(url, str) and url.startswith("http"):
        transport = StreamableHttpTransport(url, headers=dict(TUNNEL_HEADERS))
    async with Client(transport, timeout=timeout) as client:
        tools = await client.list_tools()
    return [ToolSurface.from_tool(tool) for tool in tools]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="the opponent's MCP endpoint")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args(argv)

    try:
        surfaces = asyncio.run(_survey(args.url, args.timeout))
    except Exception as error:  # noqa: BLE001 -- any transport fault is one answer
        print(f"  {args.url}\n  did not answer tools/list: "
              f"{type(error).__name__}: {error}\n"
              f"  That is a transport problem, not a dialect one. 502 = edge up and origin\n"
              f"  down, 530 = tunnel down, 421 = Host header not rewritten.")
        return 2

    text, drivable = survey_text(args.url, surfaces, set(contracts.ALL_TOOLS),
                                 set(contracts.INTEROP_TOOLS))
    print(text)
    return 0 if drivable else 1


if __name__ == "__main__":  # pragma: no cover - a command line entry point
    raise SystemExit(main())
