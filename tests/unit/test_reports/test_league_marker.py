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

from pathlib import Path

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


def test_the_result_artifact_does_not_carry_the_block():
    """Reversed on 2026-08-12, deliberately, and this test is the record.

    The marker is not in the course template -- ``course_template_fields.json``
    is taken from the assignment's own sample run and lists twelve top-level
    keys without it. imreeyal proposed the field and withdrew it as their own
    mistake, having run four counted pairings without it.

    Both peers mail a result and diff the two copies before agreeing it, so a
    field one side invents is a difference to explain at the moment when an
    unexplained difference voids the sub-game for both teams (rule 35).
    """
    body = artifacts.build_result_artifact("a-vs-b", "uid", ["a", "b"], [], {}, {})
    assert "league" not in body


def test_an_armed_block_is_still_not_emitted():
    """Even passed explicitly. The caller cannot put it back by accident."""
    body = artifacts.build_result_artifact(
        "a-vs-b", "uid", ["a", "b"], [], {}, {},
        league=league_block(True, SIGN_OFF))
    assert "league" not in body


def test_counted_ness_is_still_decided_by_the_private_setup():
    """Dropping the field changed the report, not the decision.

    Whether a series counts is read from ``setup.json`` and armed by a human;
    no code path ever read the emitted block back. If that stops being true the
    marker has to come back in some form, so this is the test that would fail.
    """
    from p2pchase.reports.league import league_block as block
    assert block(True, SIGN_OFF)["counted"] is True
    assert block()["counted"] is False


def _template() -> dict:
    import json
    return json.loads(
        (Path(__file__).resolve().parents[3] / "tests" / "fixtures"
         / "course_template_fields.json").read_text(encoding="utf-8"))


def test_the_result_matches_the_course_template_exactly():
    """Not "almost", and no longer with one field of ours allowed through.

    ``repositories`` was that one field, and it moved into ``links.github`` on
    2026-08-14 -- links belong in ``links``, imreeyal already spells it that
    way, and it leaves nothing at the top level for either team to query.
    """
    body = artifacts.build_result_artifact("a-vs-b", "uid", ["a", "b"], [], {}, {})

    assert [k for k in body if k not in _template()["result_top"]] == []


def test_final_result_carries_the_template_keys_and_no_others():
    """The block nothing was checking, which is why two of ours lived in it.

    ``raw_score`` and ``tie_rule`` are useful and they are ours, and every
    report we filed carried both inside the grader's own aggregate. A rule 35
    diff is the worst place to discover a field the other side has never seen.
    """
    body = artifacts.build_result_artifact("a-vs-b", "uid", ["a", "b"], [],
                                           {"total_score": {}, "raw_score": {},
                                            "tie_rule": "series_add"}, {})

    assert list(body["final_result"]) == [
        name for name in _template()["result_final_result"]
        if name in body["final_result"]]
    assert "raw_score" not in body["final_result"]
    assert "tie_rule" not in body["final_result"]


def test_every_artifact_announces_the_template_s_schema_version():
    """All four of the reference's samples say 1.1. We said 1.2 on all four,
    because one constant was doing duty for two different documents -- our
    ``game.json`` is 1.2 and theirs is 1.3, which is the giveaway that the
    number was never ours to reuse."""
    body = artifacts.build_result_artifact("a-vs-b", "uid", ["a", "b"], [], {}, {})

    assert body["schema_version"] == _template()["artifact_schema_version"]


def test_the_four_repository_links_survive_the_move(peer_config):
    """Rule 49 asks for four links in the JSON; the move must not lose them."""
    repos = {"a": {"cop": "u1", "thief": "u2"}, "b": {"cop": "u3", "thief": "u4"}}
    body = artifacts.build_result_artifact("a-vs-b", "uid", ["a", "b"], [], {}, {},
                                           repositories=repos)

    assert body["links"]["github"] == repos
    assert "repositories" not in body


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
