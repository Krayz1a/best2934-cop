"""The deception channel, end to end (book ch6.5, rules 26, 27).

This is the test the whole verbal layer stands or falls on. Lying is only a
strategy if it can be *detected*, and detection is only a defence if it
actually changes what we believe. Both halves are checked here against a real
two-sided match rather than a hand-built fixture, because the failure this
suite exists to catch was invisible in unit tests: an earlier version
cross-examined the opponent's revealed *move*, which is sealed in the
commitment and therefore always truthful, so trust rose to its ceiling in every
match and the thief's deception was inert.
"""

from __future__ import annotations

import pytest

from p2pchase import constants
from p2pchase.domain.belief import TRUST_CEILING, TRUST_INITIAL
from p2pchase.domain.thief_brain import ThiefBrain
from p2pchase.runtime.local_match import build_side, exchange_scent, play_half_turn
from p2pchase.runtime.match_side import Side


class CompulsiveLiar(ThiefBrain):
    """A thief that lies every single turn. Bad strategy, ideal test subject."""

    def _choose_intent(self, state) -> str:
        return constants.INTENT_LIE


class CompulsiveTruthTeller(ThiefBrain):
    """The control group: identical movement, never a false claim."""

    def _choose_intent(self, state) -> str:
        return constants.INTENT_TRUTH


def _play(shared_config, thief_brain: ThiefBrain, steps: int = 20) -> tuple[Side, Side]:
    """Run a real match with the thief's honesty policy swapped out."""
    import random

    rng = random.Random(7)
    talk = {"provider": "template", "seed": 7}
    cop = build_side(shared_config, constants.ROLE_COP, "best2934-cop", {}, talk, {})
    thief = build_side(shared_config, constants.ROLE_THIEF, "rival999", {}, talk, {})
    thief.brain = thief_brain

    for step in range(1, steps + 1):
        for side, opponent in ((cop, thief), (thief, cop)):
            play_half_turn(side, opponent, step, 1, "Manhattan", 15, rng)
        exchange_scent(cop, thief)
        if cop.state.position == thief.state.position:
            break
        cop.state.end_of_full_turn()
        thief.state.end_of_full_turn()
    return cop, thief


def test_a_thief_that_always_lies_is_caught(shared_config):
    """The cop must actually notice, not merely be given the chance to."""
    cop, thief = _play(shared_config, CompulsiveLiar())

    assert thief.lies_told > 0, "the test subject never actually lied"
    belief = cop.state.belief
    assert belief.hints_seen > 0, "no claim was ever cross-examined"
    assert belief.hints_contradicted > 0, "every lie went undetected"


def test_being_caught_collapses_trust_toward_the_floor(shared_config):
    """Detection has to have consequences or it is just bookkeeping."""
    cop, _thief = _play(shared_config, CompulsiveLiar())
    assert cop.state.belief.trust < TRUST_INITIAL


def test_an_honest_opponent_keeps_its_credibility(shared_config):
    """The estimator must not simply distrust everyone -- that would make it
    useless as a discriminator and would punish a truthful opponent."""
    cop, _thief = _play(shared_config, CompulsiveTruthTeller())
    assert cop.state.belief.trust > TRUST_INITIAL
    assert cop.state.belief.trust <= TRUST_CEILING


def test_the_liar_ends_less_believed_than_the_truth_teller(shared_config):
    """The claim that matters is comparative: same movement policy, same seed,
    same board -- only the honesty of the sentences differs."""
    liar_cop, _ = _play(shared_config, CompulsiveLiar())
    honest_cop, _ = _play(shared_config, CompulsiveTruthTeller())
    assert liar_cop.state.belief.trust < honest_cop.state.belief.trust


def test_a_lie_changes_the_sentence_and_never_the_sealed_move(shared_config):
    """Rule 18's whole point: the commitment is honest, the talk need not be."""
    from p2pchase.strategy.hint_decoder import opposite

    thief = build_side(shared_config, constants.ROLE_THIEF, "rival", {},
                       {"provider": "template", "seed": 3}, {})
    liar, honest = CompulsiveLiar(), CompulsiveTruthTeller()

    lying = liar.decide(thief.state)
    truthful = honest.decide(thief.state)

    # Same state, same movement policy: the chosen move is identical. Only the
    # heading the hint will assert differs.
    assert lying.move == truthful.move
    assert truthful.spoken_heading == truthful.move
    assert lying.spoken_heading == opposite(lying.move)


@pytest.mark.parametrize("brain", [CompulsiveLiar, CompulsiveTruthTeller])
def test_both_honesty_policies_still_produce_a_verifiable_log(shared_config, brain):
    """Deception is a strategy, never an excuse to break the commit chain."""
    from p2pchase.domain.crypto import audit_records

    cop, thief = _play(shared_config, brain())
    assert audit_records(cop.records).passed
    assert audit_records(thief.records).passed
