"""Our transmitted field, diffed against the model we co-sign at negotiate.

``scent_model_sha256`` is exchanged and compared at handshake, so declaring
``multiplicative_book_v1`` is a promise about every frame we put on the wire.
Nothing checked that the promise was kept: the hash covers the *spec document*,
never the implementation, so our peers signed a model our physics did not obey
and every window passed handshake on the way to being refused.

anrbj666 refused 45 of 45 scent readings on 2026-08-17 and settled all six
sub-games TAMPERED. Two independent deviations were behind it, and the first
fix -- the call-order one -- was necessary but not sufficient:

1. the field was read before ``apply_own_step``, so it trailed the disclosed
   move by one emission (see ``test_transmitted_field_is_current``);
2. an opening deposit at the start cell that the spec does not have. It was
   never decayed before the first move's deposit, leaving every subsequent
   frame one decay factor high -- cell (2,3) at 0.82 where the model says
   0.758, the gap shrinking by exactly x0.9 a turn.

This test re-implements the locked spec from its own parameters and diffs it
against what we would actually send. It is deliberately not written against our
own helpers: a conformance check that imports the thing it is checking proves
only that the code agrees with itself.
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from p2pchase.domain import scent_models
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.interop import InteropAdapter
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.shared.config import PeerConfig
from p2pchase.shared.config_schema import DEFAULT_SHARED

MODEL = "multiplicative_book_v1"
GRID = 7


def _spec_step(field: dict, centre: tuple[int, int], params: dict) -> dict:
    """One turn of ``tau' = clamp((1 - rho) * tau + delta, 0, cap)``.

    Decay first, then deposit -- the ``order`` the locked document declares.
    """
    kernel, rho, cap = params["kernel"], params["decay_rho"], params["clamp"][1]
    mid = params["field_size"] // 2
    out = {cell: (1.0 - rho) * value for cell, value in field.items()}
    for dr in range(-mid, mid + 1):
        for dc in range(-mid, mid + 1):
            cell = (centre[0] + dr, centre[1] + dc)
            if 0 <= cell[0] < GRID and 0 <= cell[1] < GRID:
                out[cell] = out.get(cell, 0.0) + kernel[dr + mid][dc + mid]
    return {cell: max(0.0, min(cap, value)) for cell, value in out.items()}


def _thief_loop(seed: int):
    """A thief on the anrbj666 pairing's physics: book model, no delay line."""
    setup = json.loads(
        (pathlib.Path(__file__).parents[3] / "config/police/setup.json").read_text()
    )
    # deepcopy, not deep_merge: `deep_merge({}, DEFAULT_SHARED)` hands back the
    # module-level nested dicts by reference, so assigning into ["pheromones"]
    # rewrites the defaults for every test that runs after this one. It did --
    # it silently switched an unrelated I-6 test to lag 0 and failed it.
    shared = copy.deepcopy(DEFAULT_SHARED)
    shared["pheromones"]["pheromone_transmit_lag"] = 0
    config = PeerConfig(role="police", shared=shared, setup=setup)
    session = PeerSession(config, "thief", "best2934-vs-anrbj666",
                          sub_game=1, seed=seed)
    return session, InteropAdapter(PeerHandlers(config, session)).turns(session)


@pytest.mark.parametrize("seed", [1, 5, 9])
def test_every_transmitted_frame_matches_the_locked_model(seed):
    """Cell for cell, for a whole sub-game's worth of turns.

    The tolerance is 1e-6 because :meth:`TurnLoop.trail` rounds to six decimals
    on the way out; anything looser would hide a real drift.
    """
    params = scent_models.locked_doc(MODEL)["params"]
    assert params["initial_field"] == "empty", "the premise this test rests on"

    session, loop = _thief_loop(seed)
    field: dict = {}
    for step in range(1, 20):
        turn = loop.take_turn(step)
        field = _spec_step(field, tuple(session.state.position), params)
        ours = {tuple(int(n) for n in cell.split(",")): value
                for cell, value in turn["scent_grid"].items()}
        for cell in set(field) | set(ours):
            assert field.get(cell, 0.0) == pytest.approx(ours.get(cell, 0.0), abs=1e-6), (
                f"step {step}, cell {cell}: the frame we transmit disagrees with "
                f"the model our handshake co-signs ({MODEL})"
            )


def test_the_opening_field_is_empty():
    """The specific deviation, named rather than left to the diff above.

    A deposit made before the first move is never decayed by it, so it does not
    merely add a cell -- it lifts the whole field for the rest of the sub-game.
    """
    session, loop = _thief_loop(seed=1)
    assert session.state.my_scent.grid == {}, (
        "no emission before the first move: both locked models declare "
        "initial_field 'empty'"
    )
    assert loop.take_turn(1)["scent_grid"], "and the first move must deposit"
