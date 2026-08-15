"""The artifact's audit row is the grader's two fields, not our six.

Our logs carry a six-field diagnostic. Appendix F's per-sub-game row is
``{"log_verified": ..., "tampered": ...}``. imreeyal raised this as the same
category as `raw_score` and `tie_rule`, which we had already dropped from the
artifact on exactly this argument: the counted report goes to the marker, so
template-shaped is the only safe shape there.

The diagnostics are not lost -- they stay in the logs, which the opponent
audits and which travel with the report.
"""

from __future__ import annotations

from p2pchase.reports.series_assembly import template_audit

SIX_FIELD = {
    "passed": True, "verified_steps": 36, "failed_steps": [],
    "forged_steps": [], "withheld_steps": [], "unsolicited_steps": [],
}


def test_only_the_two_template_fields_survive():
    assert set(template_audit(SIX_FIELD)) == {"log_verified", "tampered"}


def test_a_clean_audit_is_verified_and_untampered():
    assert template_audit(SIX_FIELD) == {"log_verified": True, "tampered": False}


def test_a_failed_audit_is_reported_as_not_verified():
    assert template_audit({**SIX_FIELD, "passed": False})["log_verified"] is False


def test_forged_steps_are_tampering():
    assert template_audit({**SIX_FIELD, "forged_steps": [4]})["tampered"] is True


def test_withheld_steps_are_tampering():
    assert template_audit({**SIX_FIELD, "withheld_steps": [9]})["tampered"] is True


def test_a_plain_failure_is_not_an_accusation():
    """`tampered` is a claim about the opponent, so it needs forged or withheld steps.

    An audit that failed with neither is our own bookkeeping, and reporting it
    as tampering would accuse a team in a document the lecturer reads.
    """
    audit = template_audit({**SIX_FIELD, "passed": False, "failed_steps": [2]})
    assert audit == {"log_verified": False, "tampered": False}


def test_an_absent_audit_degrades_to_unverified_rather_than_verified():
    """The safe default: silence is not a passing audit."""
    assert template_audit({}) == {"log_verified": False, "tampered": False}


def test_the_values_are_real_booleans_for_the_template():
    audit = template_audit(SIX_FIELD)
    assert all(isinstance(v, bool) for v in audit.values())
