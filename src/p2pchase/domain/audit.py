"""Auditing a disclosed log against what was actually committed (rules 18, 19, 36).

Split out of :mod:`p2pchase.domain.crypto` when a defect made the distinction
worth its own module. The old audit re-hashed each disclosed record and compared
it to the ``commit`` field *inside that same record*. That is self-consistency,
not proof, and it certifies nothing:

    live   commit = sha256(canonical({step, move: "N", ..., nonce}))
    audit  disclose {step, move: "S", ...}, same nonce, commit RECOMPUTED

Rehash the disclosed payload with the disclosed nonce and it matches the
disclosed commit. Verdict: passed. The move was rewritten after the fact and
the audit called the log clean. Commit-reveal only binds anything if the
disclosed commitment is checked against the commitment that arrived *during
play*, when the mover could not yet know what it would need to have said.

Two failure modes, kept apart because they mean different things:

``forged_steps``
    A step whose disclosed commitment differs from the one we received live.
    Someone rewrote history.

``withheld_steps``
    A step we hold a live commitment for that never appeared in the disclosure.
    Absence must fail; otherwise the cheapest attack is to omit the bad step.

Credit where due: gal-roy1 hit this in their own audit and told us, on the
reasoning that rule 35 does not care which team forged a log -- if either peer
can forge one undetected, neither team's report is worth anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .crypto import AuditResult, verify


@dataclass
class CrossCheckedAudit:
    """A verdict that says *why* it failed, not merely that it did."""

    passed: bool
    verified_steps: int
    failed_steps: list[int] = field(default_factory=list)
    forged_steps: list[int] = field(default_factory=list)
    withheld_steps: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verified_steps": self.verified_steps,
            "failed_steps": self.failed_steps,
            "forged_steps": self.forged_steps,
            "withheld_steps": self.withheld_steps,
        }


def _step_of(record: dict[str, Any], fallback: int) -> int:
    payload = record.get("payload")
    if isinstance(payload, dict) and "step" in payload:
        try:
            return int(payload["step"])
        except (TypeError, ValueError):
            return fallback
    return fallback


def audit_against_commitments(
    records: list[dict[str, Any]],
    received: dict[int, str] | None = None,
) -> CrossCheckedAudit:
    """Verify a disclosed log, cross-checked against live commitments.

    ``received`` maps step -> the commitment the opponent sent us during play.
    When it is ``None`` the check degrades to self-consistency only, which is
    what the Replay Viewer does with a log file from disk -- there is no live
    channel to cross-check against, and that limit is the reason a replay is
    evidence about *our* record and not proof about theirs.
    """
    failed: list[int] = []
    forged: list[int] = []
    verified = 0
    seen: set[int] = set()

    for index, record in enumerate(records):
        step = _step_of(record, index)
        seen.add(step)
        payload, nonce, announced = (record.get("payload"), record.get("nonce"),
                                     record.get("commit"))
        if not isinstance(payload, dict) or not isinstance(nonce, str) \
                or not isinstance(announced, str):
            failed.append(step)
            continue
        if received is not None and step in received and announced != received[step]:
            # The disclosed seal is not the seal we were handed at the time.
            # Recomputing the hash here would only confirm their new story.
            forged.append(step)
            failed.append(step)
            continue
        if verify(payload, nonce, announced):
            verified += 1
        else:
            failed.append(step)

    withheld = sorted(set(received or {}) - seen)
    failed.extend(step for step in withheld if step not in failed)
    return CrossCheckedAudit(passed=not failed, verified_steps=verified,
                             failed_steps=sorted(failed), forged_steps=sorted(forged),
                             withheld_steps=withheld)


def audit_records(records: list[dict[str, Any]]) -> AuditResult:
    """Self-consistency only. Kept for the replay path; see the module docstring."""
    checked = audit_against_commitments(records, None)
    return AuditResult(passed=checked.passed, verified_steps=checked.verified_steps,
                       failed_steps=checked.failed_steps)
