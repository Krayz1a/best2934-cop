"""What our trail discloses, and when (interop item I-6).

The lag is the difference between the scent being evidence and the scent being
the answer. These assert the property that matters -- a sampled field must not
peak on the cell the emitter is standing on -- rather than the mechanics of the
delay line, which is the part that could be rewritten without anyone caring.
"""

from __future__ import annotations

from p2pchase.domain.board import build_board
from p2pchase.domain.own_state import build_own_state
from p2pchase.domain.scent_broadcast import LaggedTrail
from p2pchase.domain.smell import ScentMap


def test_the_delay_line_hands_back_the_previous_snapshot():
    trail = LaggedTrail(lag=1)
    trail.record({(0, 0): 0.9})
    assert trail.transmitted({(5, 5): 0.9}) == {(0, 0): 0.9}


def test_a_snapshot_is_copied_not_referenced():
    """``ScentMap.grid`` is mutated in place, so a reference would catch up."""
    live = {(0, 0): 0.9}
    trail = LaggedTrail(lag=1)
    trail.record(live)
    live[(0, 0)] = 0.1
    live[(4, 4)] = 0.9
    assert trail.transmitted(live) == {(0, 0): 0.9}


def test_nothing_is_transmitted_before_the_line_has_filled():
    """Silence is honest: we are being asked for a field from before the game."""
    assert LaggedTrail(lag=1).transmitted({(3, 3): 0.9}) == {}


def test_a_deeper_lag_holds_the_field_longer():
    trail = LaggedTrail(lag=2)
    trail.record({(0, 0): 0.1})
    trail.record({(1, 1): 0.2})
    assert trail.transmitted({(2, 2): 0.3}) == {(0, 0): 0.1}
    trail.record({(2, 2): 0.3})
    assert trail.transmitted({(3, 3): 0.4}) == {(1, 1): 0.2}


def test_the_history_never_grows_past_the_lag():
    """A whole board copy per turn for 35 turns times 6 sub-games, otherwise."""
    trail = LaggedTrail(lag=2)
    for step in range(20):
        trail.record({(step, step): 0.5})
    assert len(trail.history) == 2


def test_a_zero_lag_transmits_live_and_says_so():
    """Legal, agree-able, and the thing the lag exists to prevent."""
    trail = LaggedTrail(lag=0)
    trail.record({(0, 0): 0.9})
    assert trail.transmitted({(5, 5): 0.9}) == {(5, 5): 0.9}
    assert trail.history == [], "a zero lag should not accumulate snapshots"


def test_what_we_transmit_trails_behind_where_we_are_going(shared_config):
    """The whole point, measured the way our own trail-reading measures it.

    Not asserted on the peak cell: emission saturates at ``min(peak, ...)``, so
    after a few steps a wide patch of the board sits at exactly the same
    intensity and the strongest cell is a tie broken by dict ordering. The
    centroid is what actually carries the signal -- it is what
    :func:`displacement_heading` reads to infer an opponent's heading
    (ADR-006) -- and it is where the lag has to show up.

    Marching east, the transmitted centroid must sit strictly west of the live
    one. That gap is the whole defence: it is the difference between an
    opponent inferring where we were and reading off where we are.
    """
    state = build_own_state(shared_config, "police", build_board(shared_config))
    for _ in range(4):
        state.apply_own_move("E")
        state.end_of_full_turn()

    live = ScentMap(geometry=state.my_scent.geometry, grid=dict(state.my_scent.grid))
    lagged = ScentMap(geometry=state.my_scent.geometry,
                      grid=state.broadcast.transmitted(state.my_scent.grid))

    assert lagged.grid != live.grid
    assert lagged.centroid()[1] < live.centroid()[1], "the lag did not delay anything"


def test_the_transmitted_field_is_exactly_last_turns_field(shared_config):
    """Lagged by one full turn -- not blurred, not attenuated, just late."""
    state = build_own_state(shared_config, "police", build_board(shared_config))
    state.apply_own_move("E")
    state.end_of_full_turn()

    one_turn_ago = dict(state.my_scent.grid)
    state.apply_own_move("E")
    state.end_of_full_turn()

    assert state.broadcast.transmitted(state.my_scent.grid) == one_turn_ago
