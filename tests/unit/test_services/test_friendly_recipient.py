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


def test_a_friendly_goes_only_where_it_is_told():
    """Replaces, never adds. A friendly reaching the lecturer is a false submission."""
    config = _config()
    recipient, refusal = friendly_recipient.resolve(config, "imreeyal", THEIRS)
    assert refusal == ""
    assert recipient == THEIRS
    assert config.email["recipient"] not in recipient


def test_several_addresses_are_accepted():
    recipient, _ = friendly_recipient.resolve(
        _config(), "imreeyal", f" {THEIRS} , us@example.com ")
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
def test_every_current_pairing_is_still_uncounted_so_friendlies_are_allowed(opponent):
    """If this fails, a pairing was armed and the override stopped working there."""
    recipient, refusal = friendly_recipient.resolve(_config(), opponent, THEIRS)
    assert refusal == ""
    assert recipient == THEIRS
