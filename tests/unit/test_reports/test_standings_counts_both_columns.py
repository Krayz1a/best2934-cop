"""`games_played_including_this` must include this game in BOTH columns.

We added the series to our own column and emitted the opponent's declared count
untouched. So our first counted series filed `{best2934: 1, imreeyal: 5}` while
imreeyal filed `{imreeyal: 6, best2934: 1}` for the same match.

imreeyal predicted the correct value on league issue #45 *before* the series was
played. We shipped the wrong one anyway, and it reached the lecturer in message
`1a005d476b4d5da0` on 2026-08-15 before either team's cross-diff caught it.

Two reports of one match disagreeing on a standings field is the rule-35 shape
however small the field -- and "small" is precisely why nobody reads it until it
is the thing that voids a match.
"""

from __future__ import annotations

import pytest

from p2pchase.reports.standings import standings_block


def _block(counted=True, opponent_games=5, winner=None, directory=None):
    return standings_block("best2934", "imreeyal", counted, opponent_games,
                           winner, directory)


def test_this_series_is_added_to_the_opponent_column(tmp_path):
    """The exact defect, in the exact numbers that were filed."""
    played = _block(directory=tmp_path)["games_played_including_this"]

    assert played == {"best2934": 1, "imreeyal": 6}


def test_a_friendly_adds_nothing_to_either_column(tmp_path):
    """Only a counted series counts, on both sides."""
    played = _block(counted=False, directory=tmp_path)["games_played_including_this"]

    assert played == {"best2934": 0, "imreeyal": 5}


def test_an_undeclared_opponent_count_still_includes_this_series(tmp_path):
    """Zero prior is an honest unknown, but the game we just played is known."""
    played = _block(opponent_games=0, directory=tmp_path)["games_played_including_this"]

    assert played["imreeyal"] == 1


@pytest.mark.parametrize("prior", [0, 1, 5, 12])
def test_both_columns_move_together(prior, tmp_path):
    """Whatever they declared, this series shifts both columns by the same one."""
    friendly = standings_block("best2934", "imreeyal", False, prior, None, tmp_path)
    counted = standings_block("best2934", "imreeyal", True, prior, None, tmp_path)

    a = friendly["games_played_including_this"]
    b = counted["games_played_including_this"]
    assert b["imreeyal"] - a["imreeyal"] == 1
    assert b["best2934"] - a["best2934"] == 1


def test_the_opponent_column_is_never_derived_from_our_ledger(tmp_path):
    """Rule 37: each team declares its own. We record theirs, we do not invent it.

    Our own count comes from our artifacts on disk; theirs can only come from
    what they told us. The fix adds this series to their declaration -- it does
    not start counting their history for them.
    """
    low = _block(opponent_games=0, directory=tmp_path)["games_played_including_this"]
    high = _block(opponent_games=9, directory=tmp_path)["games_played_including_this"]

    assert low["best2934"] == high["best2934"] == 1
    assert (low["imreeyal"], high["imreeyal"]) == (1, 10)


def test_the_diversity_reward_is_unaffected_by_the_count_fix(tmp_path):
    """A tie still pays nobody -- the correction must not disturb that reading."""
    assert _block(winner=None, directory=tmp_path)["diversity_reward_applied"] == {
        "best2934": False, "imreeyal": False}
    assert _block(winner="best2934", directory=tmp_path)["diversity_reward_applied"] == {
        "best2934": True, "imreeyal": False}
