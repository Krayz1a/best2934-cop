"""The live view: watching one peer's belief evolve during a match.

Two renderers, one data source. Both consume ``OwnState.local_view()`` and
nothing else, which is how rules 8 and 9 are satisfied structurally rather than
by discipline -- there is no code path through which the objective board could
reach a renderer, because no renderer accepts it.

``tk``    a Tkinter canvas with the belief heat map. The screenshot the README
          requires (ch9.4.2) comes from here.
``text``  a terminal renderer, used when Tkinter is absent (it ships in the
          ``python3-tk`` system package on Debian and Ubuntu, not via pip) and
          whenever the run is headless, such as in CI.

The text mode is not a consolation prize. It makes the view usable over SSH and
testable in a unit test, neither of which a canvas manages.
"""

from __future__ import annotations

import logging
import time

from .board_render import render_frame
from .frames import match_frames, solo_frames

LOGGER = logging.getLogger(__name__)

CLEAR_SCREEN = "\033[2J\033[H"


class LiveViewUnavailable(RuntimeError):
    """No renderer can run here -- an environment problem, not a bug."""


def tkinter_available() -> bool:
    """Whether a Tkinter window can be opened in this environment."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return False
    return True


def frame_source(sdk, seed: int = 0, solo: bool = False, opponent: str = "them"):
    """Pick the generator that feeds the renderer.

    Defaults to a real two-sided sub-game: a solo run's belief only diffuses,
    so it shows the renderer working but says nothing about the game.
    """
    config = sdk.config
    if solo:
        return solo_frames(config.shared, config.role, config.strategy,
                           config.trash_talk, config.llm, seed=seed)
    return match_frames(config.shared, config.role, config.strategy,
                        config.trash_talk, config.llm, seed=seed,
                        group=config.group_id, opponent=opponent)


def run_text_view(sdk, seed: int = 0, delay: float = 0.08, solo: bool = False,
                  opponent: str = "them", quiet: bool = False) -> str:
    """Render the whole run in the terminal and return the final frame.

    ``quiet`` consumes every frame without printing, which is how a test or a
    screenshot script gets the final board without a flickering terminal.
    """
    grid_size = int(sdk.config.shared["board_and_agents"]["grid_size"])
    frame = ""
    for view, hint in frame_source(sdk, seed=seed, solo=solo, opponent=opponent):
        banner = (
            f"p2pchase live view — {sdk.config.group_id} as {sdk.config.role}\n"
            f"opponent says: {hint or '(nothing yet)'}\n"
        )
        frame = render_frame(view, grid_size, banner)
        if not quiet:
            print(CLEAR_SCREEN + frame, flush=True)
            if delay:
                time.sleep(delay)
    return frame


def run_live_view(sdk, sub_games: int = 1, seed: int = 0, opponent: str = "them",
                  text_mode: bool = False) -> None:
    """Open the live view in whichever renderer this machine supports."""
    del sub_games  # the live view watches one sub-game, not a whole series

    if text_mode or not tkinter_available():
        if not text_mode:
            LOGGER.warning(
                "Tkinter is not installed (it ships as the python3-tk system "
                "package, not via pip); falling back to the terminal renderer"
            )
        run_text_view(sdk, seed=seed, opponent=opponent)
        return

    from .gui.tk_view import run_tk_view

    run_tk_view(sdk, seed=seed, opponent=opponent)
