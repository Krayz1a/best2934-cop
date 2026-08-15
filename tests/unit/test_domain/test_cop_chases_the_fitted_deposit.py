"""The cop chases the fitted cell when it has one, and nothing changes until it does.

Measured on our own tapes: under `multiplicative_book_v1` the posterior does
converge -- to distance 1 by step 31 -- but 31 is past the point where a
35-step cap leaves room to convert, and we took 0 captures in 17 games. Fitting
the deposit out of the same field names the cell outright, and a chaser walking
at it caught all eight recovered trajectories by step 19.

`track_deposit` is off by default. The code landing and the cop's behaviour
changing are two decisions, and the second one wants wire evidence.
"""

from __future__ import annotations

from p2pchase.domain.board import build_board
from p2pchase.domain.cop_brain import CopBrain
from p2pchase.domain.own_state import build_own_state
from p2pchase.domain.smell import BOOK_FIGURE_KERNEL
from p2pchase.domain.trail_inversion import _predict as predict


def _state(config, tracking: bool):
    """Built the way the peer builds it: strategy is OURS, config is AGREED.

    Passing the flag inside `config` is what the first version of this file did,
    and it passed while the production flag was unreachable -- game.json has no
    strategy block at all, so the peer could never have turned it on.
    """
    return build_own_state(config, "police", build_board(config),
                           strategy={"track_deposit": tracking})


def _field(centre, previous=None):
    return predict(previous or {}, centre, BOOK_FIGURE_KERNEL, 0.9, 0.10)


def test_tracking_is_off_by_default(shared_config):
    state = build_own_state(shared_config, "police", build_board(shared_config))

    assert state.track_deposit is False


def test_the_flag_is_read_from_our_setup_and_not_the_agreed_config(shared_config):
    """The agreed config never carries it, so reading it there means never on."""
    cfg = dict(shared_config)
    cfg["strategy"] = {"track_deposit": True}

    assert build_own_state(cfg, "police", build_board(cfg)).track_deposit is False


def test_with_tracking_off_no_deposit_is_ever_fitted(shared_config):
    """The dark path: the field is sampled exactly as it was before."""
    state = _state(shared_config, tracking=False)

    state.sample_opponent_scent(_field((2, 2)))
    state.sample_opponent_scent(_field((2, 3), _field((2, 2))))

    assert state.opponent_deposit is None


def test_the_first_sample_alone_fits_nothing(shared_config):
    """One field is a state, not a transition. There is nothing to decay from."""
    state = _state(shared_config, tracking=True)

    state.sample_opponent_scent(_field((2, 2)))

    assert state.opponent_deposit is None


def test_a_second_sample_fits_the_deposit(shared_config):
    state = _state(shared_config, tracking=True)
    first = _field((2, 2))

    state.sample_opponent_scent(first)
    state.sample_opponent_scent(_field((2, 3), first))

    assert state.opponent_deposit == (2, 3)


def test_the_cop_targets_the_fitted_cell_over_the_belief(shared_config):
    """The point of the exercise: an exact answer beats a distribution."""
    state = _state(shared_config, tracking=True)
    state.opponent_deposit = (5, 5)
    state.belief.reset(known_start=(0, 6))

    assert CopBrain._target_cell(state) == (5, 5)


def test_the_cop_falls_back_to_the_belief_with_no_reading(shared_config):
    state = _state(shared_config, tracking=True)
    state.belief.reset(known_start=(0, 6))

    assert state.opponent_deposit is None
    assert CopBrain._target_cell(state) == (0, 6)


def test_the_reference_model_is_left_alone(shared_config):
    """Its field decays to one unique peak that already IS the answer."""
    state = build_own_state(shared_config, "police", build_board(shared_config),
                            scent_model="subtractive_chebyshev_v1",
                            strategy={"track_deposit": True})
    first = _field((2, 2))

    state.sample_opponent_scent(first)
    state.sample_opponent_scent(_field((2, 3), first))

    assert state.opponent_deposit is None


def test_a_walked_trail_is_followed_cell_by_cell(shared_config):
    """Consecutive fits must trace the walk, not the saturated path behind it."""
    state = _state(shared_config, tracking=True)
    walk = [(1, 1), (1, 2), (2, 2), (2, 3), (3, 3)]
    previous, fitted = None, []
    for centre in walk:
        current = _field(centre, previous)
        state.sample_opponent_scent(current)
        fitted.append(state.opponent_deposit)
        previous = current

    assert fitted == [None, *walk[1:]]


def test_movement_closes_on_the_fitted_cell(shared_config):
    """The line that actually mattered.

    `_target_cell` feeds the barrier choice and the rationale; movement scored
    the belief-weighted expectation and never read it. Replaying the real brain
    against real trajectories caught 0 of 8 until this changed.
    """
    state = _state(shared_config, tracking=True)
    state.position = (3, 3)
    state.opponent_deposit = (6, 3)

    assert CopBrain({})._pick_move(state) == "S"


def test_a_near_uniform_belief_no_longer_parks_the_cop(shared_config):
    """The measured failure: five steps, then STAY on (3, 3) for 28 more.

    A saturated book-model field leaves the posterior near-uniform, every move
    scores alike, and the mobility term settles the cop on the centre of the
    board. Correct under ignorance, ruinous when the field names the thief.
    """
    state = _state(shared_config, tracking=True)
    state.position = (3, 3)
    state.belief.reset()                      # no information at all
    state.opponent_deposit = (0, 3)

    assert CopBrain({})._pick_move(state) == "N"


def test_no_barrier_is_placed_while_we_have_a_fix(shared_config):
    """A barrier costs the turn, and the thief spends that turn moving.

    Worth it against a cloud -- sealing space is how an unknown thief becomes
    findable. Against a fitted cell it swapped a certain step for a speculative
    one, and sealed the cell between the cop and the thief.
    """
    state = _state(shared_config, tracking=True)
    state.position = (3, 3)
    state.opponent_deposit = (4, 4)

    assert CopBrain({})._decide_move(state).barrier is None


def test_barriers_survive_when_there_is_no_fix(shared_config):
    """The suppression is scoped to having a fix, not a removal of the lever."""
    state = _state(shared_config, tracking=False)
    state.position = (3, 3)
    state.belief.reset(known_start=(4, 4))

    assert state.opponent_deposit is None
    assert CopBrain({})._choose_barrier(state, (4, 4), 2) is not None
