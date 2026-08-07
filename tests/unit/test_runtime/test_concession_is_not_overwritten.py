"""A conceded capture must survive whatever the opponent sends afterwards.

Taken from the wire, not imagined. gal-roy1 drove our cop through sub-game 1 on
7 August at 14:48 and sent two ``confirm_result`` calls inside the same second:

    14:48:30  the opponent has ended sub-game 1: CAPTURE
    14:48:30  opponent concedes capture at [5, 1]
    14:48:30  the opponent has ended sub-game 1: unstated

The second call carried no outcome. ``outcome or OUTCOME_SURVIVAL`` turned that
absence into a positive claim of survival and overwrote the concession, so the
sub-game our cop had just won was recorded as one the thief escaped.

The damage is not that we lose a point. Our own board still said ``capture``,
because :meth:`TurnLoop.concede` keeps it -- so one peer held two contradictory
answers, and rule 35 voids the match for *both* teams when the reports disagree.
gal-roy1 would have lost a game in which they did nothing wrong, over a message
they sent to be helpful.
"""

from __future__ import annotations

from p2pchase import constants
from p2pchase.runtime.peer_session import PeerSession

GAME = "best2934-vs-gal-roy1"


def _session(peer_config) -> PeerSession:
    return PeerSession(peer_config, constants.ROLE_COP, GAME, sub_game=1, seed=1)


def test_a_trailing_empty_confirm_does_not_erase_a_capture(peer_config):
    """gal-roy1's exact sequence: CAPTURE, then nothing."""
    session = _session(peer_config)

    session.on_opponent_finished("CAPTURE")
    session.on_opponent_finished("")

    assert session.opponent_finished == constants.OUTCOME_CAPTURE


def test_an_outcome_is_stored_in_the_casing_scoring_can_read(peer_config):
    """``award()`` raises on ``"CAPTURE"``, so the opponent's shift key scored us."""
    session = _session(peer_config)

    session.on_opponent_finished("CAPTURE")

    assert session.opponent_finished == constants.OUTCOME_CAPTURE
    assert constants.OUTCOME_CAPTURE in {constants.OUTCOME_CAPTURE,
                                         constants.OUTCOME_SURVIVAL,
                                         constants.OUTCOME_TECHNICAL_LOSS}


def test_an_unstated_ending_still_means_survival_when_it_comes_first(peer_config):
    """The default is right; it was only ever wrong as an overwrite.

    A peer that ran the horizon out has nothing to declare, and reading that
    silence as survival is what lets an honest thief stop talking.
    """
    session = _session(peer_config)

    session.on_opponent_finished("")

    assert session.opponent_finished == constants.OUTCOME_SURVIVAL


def test_a_contradicting_ending_is_refused_and_warned_about(peer_config, caplog):
    """Taking a concession back is the one direction worth shouting about."""
    session = _session(peer_config)
    session.on_opponent_finished("capture")

    with caplog.at_level("WARNING"):
        session.on_opponent_finished("survival")

    assert session.opponent_finished == constants.OUTCOME_CAPTURE
    assert "keeping the first" in caplog.text


def test_nothing_is_recorded_before_the_opponent_says_anything(peer_config):
    """The empty string has to stay falsy: ``peer.py`` branches on it."""
    assert not _session(peer_config).opponent_finished
