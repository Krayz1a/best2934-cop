"""The game id is derived from the pairing, never typed at the keyboard.

Two failures in one evening, both from an operator-typed `--game-id`:

`best2934-vs-anrbj666-f2` -- a suffix added to keep two friendlies apart.
`opponent_in_game_id` splits on `-vs-`, so the opponent parsed as
"anrbj666-f2", the pairing lookup missed, and every per-pairing term fell back
to a default: `first_half` instead of `odd_even`, `own` instead of `league`.
Sub-game 1 was thief under both conventions by luck; sub-game 2 would have put
two thieves on the board.

`best2934-vs-anrbj666` -- unsorted. `make_game_id` has always sorted and
nothing called it. It was right against `imreeyal` and `gal-roy1` for exactly
one reason: `best2934` sorts before both of them. anrbj666 is the first
opponent alphabetically ahead of us, so the first pairing where it could
show -- and it showed as a digest disagreement rather than an error, because
`game_id` leads the SPEC-6 scope while `game_uid` hashes `sorted([a, b])` and
was never wrong. A construction order-independent in one place and
order-dependent in another works until it meets the alphabet.

Refusing rather than correcting matches how `--role` is already treated: an
operator who typed an id meant it, and a peer quietly playing under a
different name is stranger to debug than a message.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from p2pchase.cli.network_commands import GameIdClashError, _game_id_for


def _args(opponent="anrbj666", game_id="local-rehearsal"):
    return SimpleNamespace(opponent=opponent, game_id=game_id)


def test_the_derived_id_is_sorted_even_when_we_sort_second(peer_config):
    """The case that broke: an opponent alphabetically ahead of us."""
    peer_config.setup.setdefault("opponents", {}).setdefault("anrbj666", {})

    assert _game_id_for(_args(), peer_config).split("-vs-") == sorted(
        [peer_config.group_id, "anrbj666"])


def test_an_absent_id_is_derived_rather_than_left_empty(peer_config):
    assert _game_id_for(_args(game_id=""), peer_config) == _game_id_for(
        _args(), peer_config)


def test_the_correct_id_typed_explicitly_is_accepted(peer_config):
    derived = _game_id_for(_args(), peer_config)

    assert _game_id_for(_args(game_id=derived), peer_config) == derived


def test_an_unsorted_id_is_refused_and_names_the_right_one(peer_config):
    unsorted = f"{peer_config.group_id}-vs-anrbj666"

    with pytest.raises(GameIdClashError, match="anrbj666"):
        _game_id_for(_args(game_id=unsorted), peer_config)


def test_a_suffixed_id_is_refused(peer_config):
    """The `-f2` slip: a suffix silently becomes part of the opponent name."""
    with pytest.raises(GameIdClashError):
        _game_id_for(_args(game_id="anrbj666-vs-best2934-f2"), peer_config)


def test_the_refusal_explains_why_the_id_matters(peer_config):
    """A message an operator can act on beats one they have to interpret."""
    with pytest.raises(GameIdClashError) as caught:
        _game_id_for(_args(game_id="zzz-vs-aaa"), peer_config)

    text = str(caught.value)
    assert "sorted" in text
    assert "mutual_agreement" in text


def test_no_opponent_leaves_the_typed_id_alone(peer_config):
    """A rehearsal has no pairing to derive from, so nothing is imposed."""
    assert _game_id_for(_args(opponent="", game_id="local-rehearsal"),
                        peer_config) == "local-rehearsal"


def test_playing_ourselves_leaves_the_typed_id_alone(peer_config):
    assert _game_id_for(_args(opponent=peer_config.group_id, game_id="mine"),
                        peer_config) == "mine"


def test_the_derived_id_round_trips_to_the_opponent(peer_config):
    """Whatever we derive must resolve back, or the pairing lookup misses.

    This is the property the `-f2` id violated, and the reason it silently used
    another pairing's terms.
    """
    from p2pchase.reports.naming import opponent_in_game_id

    derived = _game_id_for(_args(), peer_config)

    assert opponent_in_game_id(derived, peer_config.group_id) == "anrbj666"
