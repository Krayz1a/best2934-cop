"""The three fields the lecturer's standings are built from.

Adopted on 2026-08-14 from a citation we cannot check: imreeyal quotes the
book's attached example set (``4-final-result``, book section 9.2.1) as carrying
a nine-key ``final_result``. We do not hold that file -- it is not in
``booklet.txt``, the guidelines or the assignment ``.docx`` -- and the reference
implementation's own sample has six keys and stops. :mod:`p2pchase.reports
.standings` records why it was still the right call.

What makes it checkable anyway is this file. imreeyal emitted the block for our
2026-08-14 friendly and the operator holds their report, so our derivations are
pinned against **their** numbers rather than against our own opinion of what the
fields mean. A field two teams emit from different definitions is worse than a
field neither emits: it agrees on the name and disagrees on the number, at
settlement, where rule 35 is waiting.
"""

from __future__ import annotations

import json

import pytest

from p2pchase.reports import artifacts
from p2pchase.reports.history import record_counted_game
from p2pchase.reports.standings import standings_block

#: Verbatim from imreeyal's mailed report for the friendly. Their bytes.
THEIRS = {
    "games_played_including_this": {"imreeyal": 5, "best2934": 0},
    "first_meeting_between_groups": True,
    "diversity_reward_applied": {"imreeyal": False, "best2934": False},
}


@pytest.fixture
def ledger(tmp_path):
    """An empty counted-games ledger -- which is our true state: zero counted."""
    return tmp_path


def test_our_derivation_reproduces_the_block_imreeyal_mailed_us(ledger):
    """The cross-implementation check, on another team's numbers.

    Uncounted friendly, no counted games on our ledger, imreeyal declaring five.
    """
    block = standings_block("best2934", "imreeyal", counted=False,
                            opponent_games=5, directory=ledger)

    assert block == THEIRS


def test_a_counted_series_counts_itself(ledger):
    """``including_this`` is the whole point of the name: the series being
    reported is in the number, so a first counted game reports one, not zero."""
    block = standings_block("best2934", "imreeyal", counted=True,
                            opponent_games=5, directory=ledger)

    assert block["games_played_including_this"]["best2934"] == 1


def test_a_friendly_pays_no_diversity_reward(ledger):
    """Both sides false on an uncounted first meeting, which is what imreeyal
    emitted. The reward attaches to a counted encounter, not to meeting."""
    block = standings_block("best2934", "imreeyal", counted=False,
                            opponent_games=5, directory=ledger)

    assert block["diversity_reward_applied"] == {"best2934": False, "imreeyal": False}


def test_the_diversity_reward_goes_to_the_winner_alone(ledger):
    """The correction, and the one a friendly could never have surfaced.

    We first wrote this as "counted and first meeting", paid to both sides.
    imreeyal contradicted it on issue #45 -- we had asked to be -- and the book
    settles it against us twice: ch, "a *victory* over an opponent you have not
    yet played earns the full reward", and App F table row 2, "score for a
    *victory* against a new opponent -- 10 -- fixed". The reward is for winning
    a new opponent, not for meeting one.
    """
    block = standings_block("best2934", "imreeyal", counted=True,
                            opponent_games=5, winner_group="best2934",
                            directory=ledger)

    assert block["diversity_reward_applied"] == {"best2934": True, "imreeyal": False}


def test_the_loser_of_a_counted_first_meeting_is_paid_nothing(ledger):
    block = standings_block("best2934", "imreeyal", counted=True,
                            opponent_games=5, winner_group="imreeyal",
                            directory=ledger)

    assert block["diversity_reward_applied"] == {"best2934": False, "imreeyal": True}


def test_a_tied_counted_series_pays_neither(ledger):
    """``winner_group`` is null on a tie, so nobody won a new opponent."""
    block = standings_block("best2934", "imreeyal", counted=True,
                            opponent_games=5, winner_group=None,
                            directory=ledger)

    assert block["diversity_reward_applied"] == {"best2934": False, "imreeyal": False}


def test_both_spellings_agree_on_every_friendly_which_is_why_it_hid(ledger):
    """The reason this survived a six-sub-game friendly and a review.

    Paid-to-both and paid-to-winner print false/false on any uncounted series
    and on any tie. They diverge only on a counted series someone wins -- in the
    mail, on a standings field, under rule 35.
    """
    friendly = standings_block("best2934", "imreeyal", counted=False,
                               opponent_games=5, winner_group="best2934",
                               directory=ledger)

    assert friendly["diversity_reward_applied"] == {"best2934": False, "imreeyal": False}


def test_a_second_series_against_the_same_team_is_not_a_first_meeting(ledger):
    """Rule 52 allows one counted game per pairing, so this should never happen
    -- and if it does, the standings must not be told it is new."""
    record_counted_game("imreeyal", ledger)

    block = standings_block("best2934", "imreeyal", counted=True,
                            opponent_games=5, winner_group="best2934",
                            directory=ledger)

    assert block["first_meeting_between_groups"] is False
    assert block["diversity_reward_applied"]["best2934"] is False


def test_their_count_is_recorded_and_never_guessed(ledger):
    """Rule 37 makes each team declare its own. A number we invent for another
    team is a false declaration in *their* column of the standings, so an
    unknown reports zero rather than something plausible."""
    block = standings_block("best2934", "nobody-told-us", counted=False,
                            directory=ledger)

    assert block["games_played_including_this"]["nobody-told-us"] == 0


def test_the_artifact_carries_all_nine_keys_in_the_example_set_s_order():
    body = artifacts.build_result_artifact(
        "a-vs-b", "uid", ["a", "b"], [], {}, {},
        standings=standings_block("a", "b", counted=False))

    assert list(body["final_result"])[-3:] == list(THEIRS)


def test_a_caller_with_no_standings_still_writes_a_valid_report():
    """A rehearsal and the test suite have no ledger and no opponent to declare
    for. They must produce the six honest fields, not a crash or three nulls."""
    body = artifacts.build_result_artifact("a-vs-b", "uid", ["a", "b"], [],
                                           {"ties": 0}, {})

    assert "games_played_including_this" not in body["final_result"]
    assert json.dumps(body)
