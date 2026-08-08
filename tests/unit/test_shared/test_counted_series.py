"""Where the counted/uncounted declaration comes from, and where it cannot.

The point of putting this in ``setup.json`` rather than behind a CLI flag is
that no code path writes it. Arming the league marker is a human editing a
file; every automated route to a counted declaration is a route by which a
friendly gets reported as a counted game (rules 37-38).

Absent means uncounted, always. A pairing nobody has written terms for is not
"probably counted" -- and the asymmetry is the reason: understating our own
standing is recoverable, and a false counted declaration is not.
"""

from __future__ import annotations

from p2pchase.reports.league import league_block
from p2pchase.shared.peer_config import PeerConfig

SIGN_OFF = "both operators signed off in writing, league issue #48"


def _config(shared_config, setup_payload, opponents: dict) -> PeerConfig:
    setup = dict(setup_payload)
    setup["opponents"] = opponents
    return PeerConfig(role="police", shared=shared_config, setup=setup)


def test_an_unknown_opponent_is_uncounted(peer_config):
    assert peer_config.counted_series("nobody-we-have-met") == (False, "")


def test_a_pairing_with_terms_but_no_marker_is_uncounted(shared_config, setup_payload):
    """The live shape: every pairing in setup.json today declares terms only."""
    config = _config(shared_config, setup_payload, {"imreeyal": {"tie_rule": "series_add"}})
    assert config.counted_series("imreeyal")[0] is False


def test_a_written_sign_off_is_read_back(shared_config, setup_payload):
    config = _config(shared_config, setup_payload,
                     {"imreeyal": {"counted": True, "counted_sign_off": SIGN_OFF}})
    assert config.counted_series("imreeyal") == (True, SIGN_OFF)


def test_the_declaration_is_per_pairing(shared_config, setup_payload):
    """One counted opponent must not arm the marker for a different one."""
    config = _config(shared_config, setup_payload, {
        "imreeyal": {"counted": True, "counted_sign_off": SIGN_OFF},
        "gal-roy1": {"tie_rule": "series_add"},
    })
    assert config.counted_series("imreeyal")[0] is True
    assert config.counted_series("gal-roy1")[0] is False


def test_arming_without_writing_down_why_still_produces_a_friendly(shared_config,
                                                                   setup_payload):
    """The two halves together: a bare ``counted: true`` reaches the block and
    is refused there, so the shortcut does not exist end to end either."""
    config = _config(shared_config, setup_payload, {"imreeyal": {"counted": True}})
    assert league_block(*config.counted_series("imreeyal"))["counted"] is False
