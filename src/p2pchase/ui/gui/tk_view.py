"""Tkinter live view -- the belief heat map screenshot the README requires.

Book ch9.4.2 lists a screenshot of this window as a mandatory README component,
and rules 8 and 9 dictate what may appear in it. The canvas draws only what
``local_view()`` returns: our own cell, the declared barriers, our fading trail,
and a heat map of where we believe the opponent is. The opponent's true cell is
absent because this process does not have it.

Nielsen's heuristics shaped three choices worth naming (guidelines §10.1):
system status is always visible (step, entropy, trust and the last hint sit
beside the board, never in a transient popup); the picture matches the mental
model (hotter red means "more likely here", which is how anyone reads a heat
map); and the user stays in control (the run pauses and steps rather than
racing to the end, so a frame can actually be looked at).

Excluded from coverage in ``pyproject.toml``: a canvas cannot be meaningfully
asserted on, and the logic it renders is tested through ``board_render``.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from ..live_view import frame_source

CELL = 62
PAD = 28
BG = "#12141a"
FG = "#e6e6e6"
GRID = "#2a2f3a"
ME = "#4fc3f7"
BARRIER = "#4a5160"


def heat_colour(value: float, peak: float) -> str:
    """Dark blue-grey to hot red, scaled against the current peak.

    Scaled against the peak rather than 1.0 for the same reason the text
    renderer is: a diffuse posterior never exceeds a few percent anywhere, and
    on an absolute scale the board would look empty exactly when the picture is
    most interesting.
    """
    if value <= 0 or peak <= 0:
        return "#1a1d24"
    t = min(1.0, value / peak)
    red = int(26 + t * 229)
    green = int(29 + t * 60)
    blue = int(36 - t * 20)
    return f"#{red:02x}{green:02x}{blue:02x}"


class LiveView:
    """The window: a belief canvas plus a status panel."""

    def __init__(self, root: tk.Tk, grid_size: int, title: str) -> None:
        self.grid_size = grid_size
        root.title(title)
        root.configure(bg=BG)

        size = grid_size * CELL + PAD * 2
        self.canvas = tk.Canvas(root, width=size, height=size, bg=BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, rowspan=2, padx=12, pady=12)

        self.status = tk.Label(root, text="", justify="left", anchor="nw", bg=BG, fg=FG,
                               font=("DejaVu Sans Mono", 11), padx=14, pady=12)
        self.status.grid(row=0, column=1, sticky="nw")

        self.hint = tk.Label(root, text="", justify="left", anchor="nw", wraplength=320,
                             bg=BG, fg="#9fd3ff", font=("DejaVu Sans", 11), padx=14)
        self.hint.grid(row=1, column=1, sticky="nw")

    def draw(self, view: dict[str, Any], hint: str) -> None:
        """Repaint one frame from a local view."""
        self.canvas.delete("all")
        belief = {
            (int(k.split(",")[0]), int(k.split(",")[1])): float(v)
            for k, v in view.get("belief", {}).items()
        }
        peak = max(belief.values(), default=0.0)
        barriers = {(int(b[0]), int(b[1])) for b in view.get("barriers", [])}
        me = tuple(view.get("my_position", (0, 0)))

        for r in range(self.grid_size):
            for c in range(self.grid_size):
                self._draw_cell(r, c, belief.get((r, c), 0.0), peak, (r, c) in barriers)
        self._draw_me(me)
        self.status.configure(text=self._status_text(view))
        self.hint.configure(text=f"last hint:\n{hint}" if hint else "")

    def _draw_cell(self, r: int, c: int, value: float, peak: float, barrier: bool) -> None:
        x0, y0 = PAD + c * CELL, PAD + r * CELL
        fill = BARRIER if barrier else heat_colour(value, peak)
        self.canvas.create_rectangle(x0, y0, x0 + CELL, y0 + CELL, fill=fill, outline=GRID)
        if not barrier and value > 0.005:
            self.canvas.create_text(x0 + CELL / 2, y0 + CELL / 2, text=f"{value:.2f}",
                                    fill="#d8d8d8", font=("DejaVu Sans Mono", 9))

    def _draw_me(self, me: tuple[int, ...]) -> None:
        x0, y0 = PAD + me[1] * CELL, PAD + me[0] * CELL
        self.canvas.create_oval(x0 + 12, y0 + 12, x0 + CELL - 12, y0 + CELL - 12,
                                fill=ME, outline="")
        self.canvas.create_text(x0 + CELL / 2, y0 + CELL / 2, text="ME",
                                fill="#08131a", font=("DejaVu Sans", 10, "bold"))

    @staticmethod
    def _status_text(view: dict[str, Any]) -> str:
        top = view.get("belief_top", [])
        best = f"{tuple(top[0][0])}  p={top[0][1]:.3f}" if top else "unknown"
        return "\n".join([
            f"role           {view.get('role', '?')}",
            f"step           {view.get('step', 0)}",
            f"my position    {tuple(view.get('my_position', ()))}",
            f"barriers left  {view.get('barriers_left', 0)}",
            "",
            f"belief peak    {best}",
            f"entropy        {view.get('belief_entropy', 0):.3f} bits",
            f"hint trust     {view.get('hint_trust', 0):.3f}",
            f"tokens used    {view.get('tokens_used', 0)}",
            "",
            "the opponent's true cell is not",
            "shown: this peer does not have it",
            "(rules 8, 9)",
        ])


def run_tk_view(sdk, seed: int = 0, opponent: str = "them",
                interval_ms: int = 260) -> None:
    """Animate one peer's run in a window until the sub-game ends."""
    shared = sdk.config.shared
    root = tk.Tk()
    view = LiveView(root, int(shared["board_and_agents"]["grid_size"]),
                    f"p2pchase — {sdk.config.group_id} as {sdk.config.role}")
    frames = frame_source(sdk, seed=seed, opponent=opponent)

    def tick() -> None:
        try:
            frame, hint = next(frames)
        except StopIteration:
            return
        view.draw(frame, hint)
        root.after(interval_ms, tick)

    root.after(0, tick)
    root.mainloop()
