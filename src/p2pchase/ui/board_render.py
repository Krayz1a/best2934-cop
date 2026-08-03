"""Rendering ONE peer's local truth (book rules 8, 9).

The constraint here is not cosmetic. Rule 8 forbids any view of the objective
board, and rule 9 makes rendering one an illegal information advantage that
disqualifies the project. So this module takes ``OwnState.local_view()`` -- a
dict that structurally cannot contain the opponent's position -- and nothing
else. There is no parameter through which the truth could be passed in.

What a player actually sees is therefore: their own cell, the declared barriers,
their own fading trail, and a probability cloud over where the opponent might
be. The cloud is the interesting part, and watching it sharpen and then smear
again as the trail decays is the clearest picture of what a Dec-POMDP feels like
from the inside.

Kept free of any GUI dependency so it can be unit-tested and so the terminal
renderer works on a machine with no Tkinter.
"""

from __future__ import annotations

from typing import Any

#: Light to dark. Index into this by probability to get a shade.
SHADES = " ·:+*#@"

GLYPH_ME = "A"
GLYPH_BARRIER = "█"


def shade_for(value: float, peak: float) -> str:
    """Map a probability to a shade, scaled against the current peak.

    Scaling against the peak rather than against 1.0 is what keeps the picture
    readable: a posterior spread over thirty cells never exceeds 0.1 anywhere,
    and against an absolute scale the whole board would render as blank.
    """
    if value <= 0 or peak <= 0:
        return SHADES[0]
    index = int(round((value / peak) * (len(SHADES) - 1)))
    return SHADES[max(0, min(len(SHADES) - 1, index))]


def belief_grid(view: dict[str, Any], grid_size: int = 7) -> list[list[str]]:
    """Build the character grid: barriers, own cell, belief shading."""
    belief = {
        (int(k.split(",")[0]), int(k.split(",")[1])): float(v)
        for k, v in view.get("belief", {}).items()
    }
    peak = max(belief.values(), default=0.0)
    barriers = {(int(b[0]), int(b[1])) for b in view.get("barriers", [])}
    me = tuple(view.get("my_position", (0, 0)))

    rows: list[list[str]] = []
    for r in range(grid_size):
        row = []
        for c in range(grid_size):
            if (r, c) == me:
                row.append(GLYPH_ME)
            elif (r, c) in barriers:
                row.append(GLYPH_BARRIER)
            else:
                row.append(shade_for(belief.get((r, c), 0.0), peak))
        rows.append(row)
    return rows


def render_board(view: dict[str, Any], grid_size: int = 7) -> str:
    """The board as text, with axis labels."""
    rows = belief_grid(view, grid_size)
    header = "    " + " ".join(str(c) for c in range(grid_size))
    lines = [header, "   +" + "-" * (grid_size * 2 - 1) + "+"]
    for index, row in enumerate(rows):
        lines.append(f" {index} |" + " ".join(row) + "|")
    lines.append("   +" + "-" * (grid_size * 2 - 1) + "+")
    return "\n".join(lines)


def render_status(view: dict[str, Any]) -> str:
    """The numbers a player needs beside the picture."""
    top = view.get("belief_top", [])
    best = f"{tuple(top[0][0])} p={top[0][1]:.3f}" if top else "unknown"
    return "\n".join([
        f"role            : {view.get('role', '?')}",
        f"step            : {view.get('step', 0)}",
        f"my position     : {tuple(view.get('my_position', ()))}",
        f"barriers left   : {view.get('barriers_left', 0)}",
        f"belief peak     : {best}",
        f"belief entropy  : {view.get('belief_entropy', 0):.3f} bits",
        f"hint trust      : {view.get('hint_trust', 0):.3f}",
        f"tokens used     : {view.get('tokens_used', 0)}",
    ])


def render_legend() -> str:
    """Explain the glyphs, and state plainly what is deliberately absent."""
    return (
        f"legend: {GLYPH_ME} = me   {GLYPH_BARRIER} = barrier   "
        f"'{SHADES[1]}'..'{SHADES[-1]}' = rising belief that the opponent is here\n"
        "the opponent's true position is NOT shown, because this peer does not "
        "have it (rules 8, 9)"
    )


def render_frame(view: dict[str, Any], grid_size: int = 7, banner: str = "") -> str:
    """One complete frame: banner, board, status, legend."""
    parts = []
    if banner:
        parts.append(banner)
    parts.extend([render_board(view, grid_size), "", render_status(view), "",
                  render_legend()])
    return "\n".join(parts)
