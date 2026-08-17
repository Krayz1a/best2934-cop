"""The scent field we put on the wire must include this step's own emission.

anrbj666 refused 100% of our scent readings on 2026-08-17 (34/34 from our
thief, 11/11 from our cop) and read every sub-game as TAMPERED. We had spent
the day blaming ``pheromone_transmit_lag``, set it to 0, and shipped -- and the
refusals got worse rather than better, which is the tell that the lag was never
the whole story.

It was the call order. ``TurnLoop.take_turn`` read ``trail()`` while building
the message and only then called ``apply_own_step``, which is what moves us and
deposits at the new cell. So every frame we transmitted was the field as of the
*previous* step, one emission behind the move we were announcing in the very
same message -- a lag of one baked into the ordering, surviving any config
value. Setting the lag to 0 removed the delay line and left this untouched.

The reference settles it (``peer/turn_sender.py``): ``apply_move``, then
``deposit`` at the new position, then ``snapshot`` into the message. Move,
emit, send -- in that order.
"""

from __future__ import annotations

import pytest

from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.interop import InteropAdapter
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.shared.config import PeerConfig
from p2pchase.shared.config_schema import deep_merge


def _lag_zero(config):
    """The anrbj666 pairing's physics: no delay line at all.

    Pinned here rather than taken from the fixture because the shipped default
    is still 1 -- that is the value agreed with gal-roy1 as interop item I-6,
    and it is not ours to change from a test about a different opponent. Under
    lag 1 this whole file would pass for the wrong reason: the delay line hides
    the ordering bug by trailing a step deliberately.
    """
    shared = deep_merge({}, config.shared)
    shared["pheromones"]["pheromone_transmit_lag"] = 0
    return PeerConfig(role=config.role, shared=shared, setup=config.setup)


def _at(scent_grid: dict[str, float], cell) -> float:
    """Intensity the transmitted field carries at ``cell``, 0.0 if absent.

    Deliberately not "where does the field peak": under the book's additive
    kernel several cells saturate at the centre intensity at once, so the peak
    is a tie broken by dict order and says nothing about which cell we are
    standing on. The fresh deposit is what identifies the current cell.
    """
    return float(scent_grid.get(f"{cell[0]},{cell[1]}", 0.0))


def test_the_transmitted_field_carries_this_steps_emission(peer_config):
    """The regression itself: the landed cell must carry a fresh deposit.

    With the emission read a step late the cell the move settles on holds only
    whatever the *previous* step's kernel spilled onto it -- a real value, just
    the wrong one -- so an opponent recomputing our physics from our own
    reveals refuses the frame. That is the refusal, reproduced.
    """
    config = _lag_zero(peer_config)
    session = PeerSession(config, "thief", "best2934-vs-anrbj666",
                          sub_game=1, seed=1)
    loop = InteropAdapter(PeerHandlers(config, session)).turns(session)

    centre = config.shared["pheromones"]["pheromone_center_intensity"]
    turn = loop.take_turn(1)
    landed = tuple(session.state.position)

    assert turn["scent_grid"], "a field emitted by moving cannot be empty"
    assert _at(turn["scent_grid"], landed) == pytest.approx(centre), (
        f"the cell this step's move settled on ({landed}) must carry a fresh "
        "full-strength deposit; a lower value means the field we transmitted "
        "predates the move we disclosed in the same message"
    )


def test_the_field_keeps_up_across_consecutive_steps(peer_config):
    """One step could pass by luck if the opener happens not to move.

    Walking several steps pins it: an off-by-one that survives the first
    assertion cannot survive the deposit landing late on every turn.
    """
    config = _lag_zero(peer_config)
    session = PeerSession(config, "thief", "best2934-vs-anrbj666",
                          sub_game=1, seed=3)
    loop = InteropAdapter(PeerHandlers(config, session)).turns(session)

    centre = config.shared["pheromones"]["pheromone_center_intensity"]
    for step in range(1, 5):
        turn = loop.take_turn(step)
        landed = tuple(session.state.position)
        session.end_of_turn()
        assert _at(turn["scent_grid"], landed) == pytest.approx(centre), (
            f"step {step}: transmitted field trails our disclosed position"
        )
