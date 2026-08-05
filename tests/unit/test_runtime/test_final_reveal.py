"""Disclosing the step the sub-game ended in the middle of (rules 18, 36).

Found by the audit cross-check, in the rehearsal rather than in a unit test,
which is the point: on a capture the winning peer commits to a step, sends it,
and then the loser exits before the step completes. The commitment is in the
opponent's hands; the record was never appended to ours. Every test passed and
two honest peers produced a chain the other could legitimately call incomplete.

Nothing here is about catching a cheat. It is about not *looking* like one --
and about closing the loophole that "the final step need not be disclosed",
which is the one a cheat would actually want: commit, watch the round resolve,
then say nothing about it.
"""

from __future__ import annotations

import pytest

from p2pchase import constants
from p2pchase.domain.audit import audit_against_commitments
from p2pchase.runtime.peer_session import PeerSession


@pytest.fixture
def session(peer_config) -> PeerSession:
    return PeerSession(peer_config, constants.ROLE_COP, "a-vs-b", seed=5)


def test_a_committed_but_unapplied_step_is_still_disclosed(session):
    """The regression. The step is sealed and sent; ending here must not hide it."""
    commitment = session.prepare_step(1)  # committed, never applied
    disclosed = session.final_reveal()
    assert [record["commit"] for record in disclosed] == [commitment]


def test_the_opponents_audit_of_that_chain_passes(session):
    """The failure as the *opponent* experiences it: they hold a commitment we
    never explained. Cross-checked, our disclosure has to satisfy it."""
    commitment = session.prepare_step(1)
    verdict = audit_against_commitments(session.final_reveal(), {1: commitment})
    assert verdict.passed, verdict.as_dict()
    assert not verdict.withheld_steps


def test_a_completed_step_is_disclosed_exactly_once(session):
    """The pending slot is cleared when a step is applied, so a finished step
    must not appear twice -- a duplicated step is a corrupt chain, not a safer
    one."""
    session.prepare_step(1)
    session.apply_own_step()
    disclosed = session.final_reveal()
    assert len(disclosed) == 1
    assert [record["payload"]["step"] for record in disclosed] == [1]


def test_a_clean_ending_discloses_nothing_extra(session):
    """Guard against over-correcting: with no pending step there is nothing to
    add, and inventing a record would be its own kind of dishonesty."""
    session.prepare_step(1)
    session.apply_own_step()
    session.prepare_step(2)
    session.apply_own_step()
    assert len(session.final_reveal()) == 2
