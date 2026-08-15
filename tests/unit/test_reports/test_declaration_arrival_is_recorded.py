"""What ARRIVED, separately from what our parse made of it.

`opponent_declared_sub_games` was added so a numbering disagreement could be
attributed from an artifact instead of argued from two teams' recollections. It
could not do it. The extractor is
``int(payload.get("sub_game_number", 0) or 0)``, so a **missing** key and a
declared ``0`` both land as ``0``.

On 2026-08-16 the gal-roy1 throwaway logged exactly that -- ``[0]`` on the
first sub-game and the key absent on the second -- and the reading was
consistent with three different stories: they sent 0, they sent nothing, or
they sent it under a spelling we do not read. We had to tell them so rather
than answer the question they had asked twice.

Only the arriving key names separate those, and only the first of the three is
theirs to answer for.
"""

from __future__ import annotations

from p2pchase.reports.match_log import build_log_artifact


def _log(**kwargs):
    return build_log_artifact(
        "best2934-vs-gal-roy1", "uid-1", 2, "best2934", "thief", "gal-roy1",
        "capture", "police", [], "2026-08-16T00:00:00+00:00",
        "2026-08-16T00:00:49+00:00", 0, {}, **kwargs)["summary"]


def test_the_arriving_keys_are_recorded():
    summary = _log(declaration_keys=[["group_id", "sub_game_number"]])

    assert summary["opponent_declaration_keys"] == [["group_id", "sub_game_number"]]


def test_an_opening_with_no_number_is_distinguishable_from_no_opening():
    """The case the value alone collapses.

    Keys present and no declared number reads: they opened, and nothing we
    recognise carried a sub-game number. That is a sentence about *them*.
    """
    summary = _log(declaration_keys=[["game_id", "group_id"]])

    assert "opponent_declared_sub_games" not in summary
    assert summary["opponent_declaration_keys"] == [["game_id", "group_id"]]


def test_a_declared_zero_still_shows_its_key():
    """The other story: they really did send 0. Now it looks different."""
    summary = _log(declared_sub_games=[0],
                   declaration_keys=[["group_id", "sub_game_number"]])

    assert summary["opponent_declared_sub_games"] == [0]
    assert "sub_game_number" in summary["opponent_declaration_keys"][0]


def test_a_spelling_we_do_not_read_is_visible():
    """The third story, and the one we would otherwise never see."""
    summary = _log(declaration_keys=[["group_id", "subGameNumber"]])

    assert "opponent_declared_sub_games" not in summary
    assert "subGameNumber" in summary["opponent_declaration_keys"][0]


def test_every_opening_is_kept_in_arrival_order():
    """A retry and a fresh sub-game both open; both are evidence."""
    summary = _log(declaration_keys=[["sub_game_number"], ["game_id"]])

    assert summary["opponent_declaration_keys"] == [["sub_game_number"], ["game_id"]]


def test_a_peer_that_never_opened_adds_no_key():
    """Omission stays omission -- an empty list is not a finding."""
    assert "opponent_declaration_keys" not in _log()
