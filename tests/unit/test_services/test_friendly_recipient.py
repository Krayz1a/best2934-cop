"""You may redirect a report that does not count, and never one that does.

imreeyal require both peers to mail their result to each other and diff the two
files before anything counted -- rule 35 treats contradictory reports as harshly
as missing ones. They have never received one from us because our recipient is
fixed by Appendix F Table 20 and we had nowhere to send a friendly.

The fixed address exists so a team cannot opt out of being marked, so the
override must not become a way around it. It replaces rather than adds, and a
counted pairing refuses it outright.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.services import friendly_recipient
from p2pchase.shared.peer_config import PeerConfig

REPO = Path(__file__).resolve().parents[3]
THEIRS = "imreeyal@example.com"


def _config() -> PeerConfig:
    read = lambda name: json.loads(  # noqa: E731 -- two reads, one shape
        (REPO / "config" / "police" / name).read_text(encoding="utf-8"))
    return PeerConfig(role="police", shared=read("game.json"), setup=read("setup.json"))


def test_no_override_keeps_the_league_address():
    config = _config()
    recipient, refusal = friendly_recipient.resolve(config, "imreeyal", "")
    assert refusal == ""
    assert recipient == config.email["recipient"]


#: A pairing that is uncounted and cannot stop being one. These tests are about
#: the redirect itself, so pinning them to a real opponent makes them fail on
#: the morning that opponent is armed -- `imreeyal` was armed on 2026-08-15 and
#: took three of them down, then `gal-roy1` was armed on 2026-08-16 and took
#: two more. Naming the next unarmed opponent just queues up the third outage,
#: so this names nobody: `counted_series` returns False for an opponent absent
#: from the table, by the deliberate rule that absent is uncounted.
UNCOUNTED = "nobody-we-have-ever-played"


def test_a_friendly_goes_only_where_it_is_told():
    """Replaces, never adds. A friendly reaching the lecturer is a false submission."""
    config = _config()
    recipient, refusal = friendly_recipient.resolve(config, UNCOUNTED, THEIRS)
    assert refusal == ""
    assert recipient == THEIRS
    assert config.email["recipient"] not in recipient


def test_several_addresses_are_accepted():
    recipient, _ = friendly_recipient.resolve(
        _config(), UNCOUNTED, f" {THEIRS} , us@example.com ")
    assert recipient == f"{THEIRS}, us@example.com"


def test_blank_and_comma_noise_fall_back_to_the_fixed_address():
    config = _config()
    for override in (" ", ",", " , , "):
        recipient, refusal = friendly_recipient.resolve(config, "imreeyal", override)
        assert refusal == ""
        assert recipient == config.email["recipient"]


def test_a_counted_pairing_refuses_the_override(monkeypatch):
    """The protection that makes the override safe to have at all."""
    config = _config()
    monkeypatch.setattr(type(config), "counted_series",
                        lambda self, opponent: (True, "operators signed on issue #48"))
    recipient, refusal = friendly_recipient.resolve(config, "imreeyal", THEIRS)
    assert recipient == ""
    assert "COUNTED" in refusal
    assert "Table 20" in refusal


def test_the_refusal_quotes_the_sign_off_so_it_can_be_checked(monkeypatch):
    config = _config()
    monkeypatch.setattr(type(config), "counted_series",
                        lambda self, opponent: (True, "signed by both operators 2026-08-12"))
    _, refusal = friendly_recipient.resolve(config, "imreeyal", THEIRS)
    assert "signed by both operators 2026-08-12" in refusal


@pytest.mark.parametrize("opponent", ["imreeyal", "gal-roy1", "nobody"])
def test_the_override_tracks_each_pairing_s_real_counted_flag(opponent):
    """Read the shipped config and hold the invariant, not a snapshot of it.

    This began life as ``test_every_current_pairing_is_still_uncounted_so_
    friendlies_are_allowed`` -- a tripwire for a pairing being armed without
    anyone noticing. On 2026-08-15 imreeyal was armed on purpose, for our first
    counted series, and the tripwire fired exactly as designed.

    Asserting the *fact* again under a new name would just move the tripwire to
    the next flip. So it now asserts the property the fact was standing in for:
    an armed pairing refuses the redirect, an unarmed one allows it, whichever
    is which today.
    """
    config = _config()
    counted, _sign_off = config.counted_series(opponent)
    recipient, refusal = friendly_recipient.resolve(config, opponent, THEIRS)

    if counted:
        assert recipient == ""
        assert "COUNTED" in refusal
    else:
        assert refusal == ""
        assert recipient == THEIRS


def test_at_least_one_pairing_is_armed_now_that_a_counted_series_is_scheduled():
    """The counted flip is load-bearing: if it silently reverted, we would file
    a counted series into the friendly tree and mail nobody."""
    config = _config()
    armed = [o for o in ("imreeyal", "gal-roy1") if config.counted_series(o)[0]]

    assert "imreeyal" in armed
