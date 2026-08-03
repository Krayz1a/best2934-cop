"""Strategy: pursuit, evasion, barrier economics and rationed deception."""

from __future__ import annotations

import pytest

from p2pchase import constants
from p2pchase.domain.brains import BrainBase, Decision, load_brain
from p2pchase.domain.cop_brain import CopBrain
from p2pchase.domain.thief_brain import ThiefBrain


class CustomBrain(BrainBase):
    role = "police"

    def _pick_move(self, state):
        return "STAY"


def test_the_default_cop_and_thief_are_loaded_when_nothing_is_configured(shared_config):
    assert isinstance(load_brain("police", {}, shared_config), CopBrain)
    assert isinstance(load_brain("thief", {}, shared_config), ThiefBrain)


def test_a_custom_brain_can_be_named_by_path(shared_config):
    """Appendix F Table 22: the extension point is a dotted path, nothing more."""
    brain = load_brain("police", {"brain": f"{__name__}:CustomBrain"}, shared_config)
    assert isinstance(brain, CustomBrain)


def test_the_books_key_spelling_also_works(shared_config):
    brain = load_brain("police", {"police_class": f"{__name__}:CustomBrain"}, shared_config)
    assert isinstance(brain, CustomBrain)


def test_a_malformed_path_is_refused(shared_config):
    with pytest.raises(ValueError, match="package.module:Class"):
        load_brain("police", {"brain": "nonsense"}, shared_config)


def test_a_class_that_is_not_a_brain_is_refused(shared_config):
    with pytest.raises(TypeError, match="does not inherit"):
        load_brain("police", {"brain": "pathlib:Path"}, shared_config)


def test_tuning_weights_come_from_config_not_from_the_class(shared_config):
    brain = load_brain("police", {"idle_penalty": 9.5}, shared_config)
    assert brain._tuned("idle_penalty", 0.35) == pytest.approx(9.5)


def test_an_unparsable_weight_falls_back_to_the_default(shared_config):
    brain = load_brain("police", {"idle_penalty": "banana"}, shared_config)
    assert brain._tuned("idle_penalty", 0.35) == pytest.approx(0.35)


def test_the_turn_counter_advances(cop_state, shared_config):
    brain = CopBrain(shared_config, {})
    brain.decide(cop_state)
    brain.decide(cop_state)
    assert brain.turn_index == 2


def test_the_cop_produces_a_legal_decision(cop_state, shared_config):
    decision = CopBrain(shared_config, {}).decide(cop_state)
    assert isinstance(decision, Decision)
    assert decision.move in constants.MOVE_SET
    assert decision.rationale


def test_a_barrier_is_always_paid_for_by_forgoing_the_move(cop_state, shared_config):
    """The privilege is bought with a turn; a moving cop may not also wall."""
    brain = CopBrain(shared_config, {})
    for _ in range(30):
        decision = brain.decide(cop_state)
        if decision.barrier is not None:
            assert decision.move == "STAY"
        cop_state.apply_own_move(decision.move, decision.barrier)
        cop_state.end_of_full_turn()


def test_a_barrier_declaration_is_never_a_lie(cop_state, shared_config):
    """Rules 15, 16: barrier declarations are truthful, always."""
    brain = CopBrain(shared_config, {})
    for _ in range(30):
        decision = brain.decide(cop_state)
        if decision.barrier is not None:
            assert decision.intent == constants.INTENT_TRUTH
            return
        cop_state.apply_own_move(decision.move, decision.barrier)
        cop_state.end_of_full_turn()


def test_a_distant_thief_does_not_justify_spending_a_barrier(cop_state, shared_config):
    """A speculative wall wastes a resource that is finite for the whole game."""
    brain = CopBrain(shared_config, {"barrier_engage_range": 0})
    cop_state.belief.collapse((6, 6))
    assert brain.decide(cop_state).barrier is None


def test_the_endgame_reserve_is_held_back(cop_state, shared_config):
    brain = CopBrain(shared_config, {"barrier_endgame_reserve": 99})
    cop_state.belief.collapse((0, 3))
    assert brain.decide(cop_state).barrier is None


def test_an_exhausted_quota_ends_barrier_placement(cop_state, shared_config):
    brain = CopBrain(shared_config, {})
    cop_state.board.max_barriers = 0
    cop_state.belief.collapse((0, 1))
    assert brain.decide(cop_state).barrier is None


def test_the_cop_closes_on_its_belief_peak(cop_state, shared_config):
    brain = CopBrain(shared_config, {"barrier_engage_range": -1})
    cop_state.belief.collapse((6, 6))
    before = cop_state.board.shortest_path_length(cop_state.position, (6, 6))
    cop_state.apply_own_move(brain.decide(cop_state).move)
    after = cop_state.board.shortest_path_length(cop_state.position, (6, 6))
    assert after < before


def test_the_thief_produces_a_legal_decision(thief_state, shared_config):
    decision = ThiefBrain(shared_config, {}).decide(thief_state)
    assert decision.move in constants.MOVE_SET
    assert decision.barrier is None  # only the cop may wall


def test_the_thief_backs_away_from_an_adjacent_cop(thief_state, shared_config):
    brain = ThiefBrain(shared_config, {})
    thief_state.position = (3, 3)
    thief_state.belief.collapse((3, 4))
    decision = brain.decide(thief_state)
    target = thief_state.board.target_of(thief_state.position, decision.move)
    assert thief_state.board.manhattan(target, (3, 4)) >= 1


def test_deception_is_rationed_not_sprayed(thief_state, shared_config):
    """A thief that lies every turn just trains the cop to ignore it."""
    brain = ThiefBrain(shared_config, {})
    thief_state.belief.collapse((3, 4))  # cop believed to be adjacent
    intents = []
    for _ in range(8):
        intents.append(brain.decide(thief_state).intent)
    assert constants.INTENT_LIE in intents
    assert constants.INTENT_TRUTH in intents


def test_a_distant_cop_is_told_the_truth(thief_state, shared_config):
    brain = ThiefBrain(shared_config, {})
    thief_state.position = (0, 0)
    thief_state.belief.collapse((6, 6))
    assert brain.decide(thief_state).intent == constants.INTENT_TRUTH


def test_bluffing_is_configurable(thief_state, shared_config):
    brain = ThiefBrain(shared_config, {"bluff_range": 0})
    thief_state.belief.collapse((3, 4))
    assert brain.decide(thief_state).intent == constants.INTENT_TRUTH
