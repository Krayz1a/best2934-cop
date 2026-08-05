"""The forged-log attack, and the cross-check that catches it (rules 18, 19, 36).

Every test here failed before ``audit_against_commitments`` existed. The old
audit re-hashed each disclosed record against the ``commit`` stored *inside that
record*, so a peer could rewrite its move, keep the nonce, recompute the hash,
and hand over a log that verified perfectly against its own new seal.

The distinction is the whole of commit-reveal: a commitment is only binding
because it was sent before the sender knew what it would need to have said.
Checking it against itself afterwards throws that away and keeps the ceremony.
"""

from __future__ import annotations

from p2pchase.domain.audit import audit_against_commitments, audit_records
from p2pchase.domain.crypto import commit


def _sealed(step: int, move: str) -> tuple[dict, str]:
    """One honest sealed step: its audit view, and the commitment sent live."""
    record = commit({"step": step, "role": "police", "move": move, "hint": "x"})
    return record.audit_view(), record.commit


def test_an_honest_log_passes(peer_config=None):
    view, live = _sealed(1, "N")
    verdict = audit_against_commitments([view], {1: live})
    assert verdict.passed
    assert verdict.verified_steps == 1
    assert not verdict.forged_steps and not verdict.withheld_steps


def test_a_rewritten_move_resealed_with_the_same_nonce_is_caught():
    """gal-roy1's attack, verbatim. This is the test that matters.

    The disclosed record is *internally perfect*: rehash its payload with its
    nonce and you get its commit. Only the live commitment exposes it.
    """
    honest, live = _sealed(4, "MOVE:N")
    forged = commit({"step": 4, "role": "police", "move": "MOVE:S", "hint": "x"},
                    nonce=honest["nonce"])

    # The forgery really is self-consistent -- the old audit passed it.
    assert audit_records([forged.audit_view()]).passed

    verdict = audit_against_commitments([forged.audit_view()], {4: live})
    assert not verdict.passed
    assert verdict.forged_steps == [4]


def test_a_step_that_was_committed_but_never_disclosed_fails():
    """Absence has to fail. If omission passed, the cheapest attack would be to
    simply leave the incriminating step out of the disclosure."""
    view, live = _sealed(1, "N")
    _, live_two = _sealed(2, "S")
    verdict = audit_against_commitments([view], {1: live, 2: live_two})
    assert not verdict.passed
    assert verdict.withheld_steps == [2]
    assert 2 in verdict.failed_steps


def test_a_forgery_and_an_omission_are_reported_as_different_faults():
    """One number cannot tell a rewritten step from a missing one, and the two
    call for different accusations."""
    honest, live_one = _sealed(1, "N")
    _, live_two = _sealed(2, "S")
    forged = commit({"step": 1, "role": "police", "move": "W", "hint": "x"},
                    nonce=honest["nonce"])
    verdict = audit_against_commitments([forged.audit_view()], {1: live_one, 2: live_two})
    assert verdict.forged_steps == [1]
    assert verdict.withheld_steps == [2]


def test_a_step_we_hold_no_commitment_for_is_still_hash_checked():
    """A record we have no live seal for is not automatically suspect -- the
    replay path has none at all -- but it must still verify against itself."""
    view, _ = _sealed(9, "N")
    assert audit_against_commitments([view], {}).passed
    view["commit"] = "0" * 64
    assert not audit_against_commitments([view], {}).passed


def test_the_replay_path_degrades_to_self_consistency_and_says_so():
    """``audit_records`` keeps the old semantics on purpose: a log read from
    disk has no live channel behind it, which is exactly why a replay is
    evidence about our own record rather than proof about theirs."""
    view, _ = _sealed(1, "N")
    assert audit_records([view]).passed


def _view(step: int, move: str = "N") -> dict:
    """Just the disclosed view -- the live commitment is read off it."""
    return _sealed(step, move)[0]


def test_the_turn_still_in_flight_is_accepted():
    """Whoever moves last in an alternating round has a turn nobody received.

    Failing it would fail every honest alternating match on its final step,
    which is the same mistake as failing an honest simultaneous match on its
    undisclosed pending step -- from the other side.
    """
    records = [_view(step) for step in (1, 2, 3)]
    received = {step: records[step - 1]["commit"] for step in (1, 2)}

    verdict = audit_against_commitments(records, received)
    assert verdict.passed is True
    assert verdict.unsolicited_steps == []


def test_a_step_invented_below_the_last_seal_is_caught():
    """The attack the tolerance above would otherwise open.

    A record we never received a commitment for is bound by nothing: it can be
    written after the outcome is known, which is precisely what commit-reveal
    exists to prevent. Tolerating the in-flight tail is safe only because a
    disclosure in a *gap* is not tolerated with it.
    """
    records = [_view(step) for step in (1, 2, 3)]
    received = {1: records[0]["commit"], 3: records[2]["commit"]}

    verdict = audit_against_commitments(records, received)
    assert verdict.passed is False
    assert verdict.unsolicited_steps == [2]
    assert verdict.forged_steps == []


def test_a_replay_from_disk_still_only_checks_itself():
    """No live channel, so no cross-check is possible and none is claimed."""
    verdict = audit_against_commitments([_view(1), _view(2)], None)
    assert verdict.passed is True
    assert verdict.unsolicited_steps == []
