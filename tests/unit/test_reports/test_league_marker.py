"""The counted/uncounted marker, and the two ways it must refuse to arm.

Raised by imreeyal on league issue #45 as a *shared* gap: the kit's own
``examples/pairing-artifacts/README.md`` asks every team to carry a ``league``
block as "the machine-readable counted/uncounted marker rule 52 hangs on", and
neither of us emitted one. Two artifacts silent about counted-ness are
indistinguishable from two friendlies, which is a problem in exactly one
direction -- the direction where a counted series quietly does not count.

Every test here is about the *other* direction, because that is the expensive
one. The kit: "a warm-up that copies them armed is a false declaration under
App. E rules 37-38." So the block defaults disarmed, arms only from a file a
human edits, and refuses to arm at all when nobody wrote down why.
"""

from __future__ import annotations

from p2pchase.reports import artifacts
from p2pchase.reports.league import DISARMED, UNSIGNED, league_block

SIGN_OFF = "signed off in writing by both operators on league issue #48"


def test_the_default_is_uncounted():
    """Called with nothing at all -- the shape every friendly produces."""
    assert league_block()["counted"] is False


def test_a_disarmed_block_still_says_why():
    """A bare ``false`` is a fact; the reason is what a reader can act on."""
    assert league_block()["reason"] == DISARMED


def test_every_block_names_the_rule_it_is_answering():
    for block in (league_block(), league_block(True, SIGN_OFF)):
        assert "52" in block["authority"]


def test_a_recorded_sign_off_arms_the_marker():
    block = league_block(True, SIGN_OFF)
    assert block["counted"] is True
    assert block["reason"] == SIGN_OFF


def test_arming_without_a_sign_off_disarms_itself():
    """The shape a copied fixture or a hurried flag produces.

    ``counted: true`` with nothing behind it asserts an agreement nobody can be
    pointed at. Refusing it costs a friendly nothing.
    """
    block = league_block(True, "")
    assert block["counted"] is False
    assert block["reason"] == UNSIGNED


def test_whitespace_is_not_a_sign_off():
    assert league_block(True, "   \n ")["counted"] is False


def test_the_refusal_explains_itself_rather_than_going_quiet():
    """A marker that silently flipped would be worse than one that never armed."""
    reason = league_block(True, "")["reason"]
    assert "disarmed" in reason and "37-38" in reason


def test_a_reason_without_counted_does_not_arm_anything():
    """Writing a note next to an unarmed marker must not arm it."""
    assert league_block(False, SIGN_OFF)["counted"] is False


def test_the_result_artifact_carries_the_block_by_default():
    """Not optional: omitting the marker and declaring a friendly differ."""
    body = artifacts.build_result_artifact("a-vs-b", "uid", ["a", "b"], [], {}, {})
    assert body["league"]["counted"] is False


def test_the_result_artifact_carries_an_armed_block_when_given_one():
    body = artifacts.build_result_artifact(
        "a-vs-b", "uid", ["a", "b"], [], {}, {},
        league=league_block(True, SIGN_OFF))
    assert body["league"] == {"counted": True, "reason": SIGN_OFF,
                              "authority": league_block()["authority"]}


def test_the_marker_is_outside_the_agreement_digest():
    """Two teams that disagree about counted-ness have a dispute, not a forgery.

    Rule 35 is about whether the two reports describe the same *match*. Folding
    the league marker into that digest would turn "we think this counted and
    you do not" into a hash mismatch indistinguishable from a rewritten log,
    and send both teams hunting for tampering that never happened.
    """
    friendly = artifacts.build_result_artifact("a-vs-b", "uid", ["a", "b"], [], {}, {})
    counted = artifacts.build_result_artifact(
        "a-vs-b", "uid", ["a", "b"], [], {}, {}, league=league_block(True, SIGN_OFF))
    assert friendly["mutual_agreement"]["sha256"] == counted["mutual_agreement"]["sha256"]
