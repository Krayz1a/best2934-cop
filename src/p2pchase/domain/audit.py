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

``unsolicited_steps``
    The mirror image, and the one we missed until an alternating match made it
    visible: a step disclosed at audit time that we never received a commitment
    for during play. Nothing binds it -- it can be written after the outcome is
    known, which is exactly what commit-reveal exists to prevent.

    It cannot simply be failed, because the *last* one is honest: whoever moves
    last in an alternating protocol always has a turn in flight when the
    sub-game ends. So the rule is positional rather than absolute -- a
    disclosure past the final commitment we hold is a turn we never got, and a
    disclosure in a *gap* below it is a step that was never played.

Credit where due: gal-roy1 hit the forgery case in their own audit and told us,
on the reasoning that rule 35 does not care which team forged a log -- if either
peer can forge one undetected, neither team's report is worth anything.
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
    unsolicited_steps: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verified_steps": self.verified_steps,
            "failed_steps": self.failed_steps,
            "forged_steps": self.forged_steps,
            "withheld_steps": self.withheld_steps,
            "unsolicited_steps": self.unsolicited_steps,
        }


#: Sealed records that are not moves. A peer may commit these for its own
#: integrity -- a hardware declaration, a status note, an equivocation report --
#: and we never receive them as turn commitments, because they are not turns.
NON_GAME_TYPES = frozenset({"system_spec", "step_zero", "control", "equivocation"})


def _step_of(record: dict[str, Any], fallback: int) -> int:
    payload = record.get("payload")
    if isinstance(payload, dict) and "step" in payload:
        try:
            return int(payload["step"])
        except (TypeError, ValueError):
            return fallback
    return fallback


def is_game_record(record: dict[str, Any], step: int) -> bool:
    """Is this a sealed *move*, or something else the peer committed?

    Told apart **by type, and by a step outside the game space** -- never by
    assuming a non-game record is numbered 0. imreeyal gave us this one from
    their own audit before it could cost us a match: uoh-sqak seals ``control``
    records *inside* the game step space, so their disclosed steps read
    ``[1, 2, 1, 2, 3, ... 35]``. Every audit between those two honest peers
    failed.

    Ours failed harder. A control record numbered 1 does not merely break a
    continuity run here -- it carries a different commitment from the turn we
    were handed at step 1, so the cross-check below called it ``forged`` and
    accused a peer that had done nothing wrong of rewriting history. That is
    the one verdict in this module nobody can talk their way out of afterwards.

    The exclusion is deliberately not a loophole. A non-game record is verified
    for self-consistency but does **not** count as its step having been
    disclosed, so relabelling a real move as ``control`` to escape the
    cross-check leaves that step withheld, which fails anyway. It buys a cheat
    nothing and costs an honest peer nothing, which is the correct shape.

    A step below 1 is excused too, typed or not: the game space is 1..N, so a
    record numbered outside it cannot be standing in for a move. That is
    uoh-sqak's own durable fix and it holds for peers we have never met.
    """
    payload = record.get("payload")
    kind = str(payload.get("type", "")) if isinstance(payload, dict) else ""
    return kind not in NON_GAME_TYPES and step >= 1


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
    unsolicited: list[int] = []
    verified = 0
    seen: set[int] = set()
    # The last step we were ever handed a seal for. Anything disclosed beyond it
    # is a turn that was still in flight when the sub-game ended; anything
    # disclosed *below* it that we never received is a step that never happened.
    last_sealed = max(received) if received else 0

    for index, record in enumerate(records):
        step = _step_of(record, index)
        payload, nonce, announced = (record.get("payload"), record.get("nonce"),
                                     record.get("commit"))
        if not is_game_record(record, step):
            # Sealed, so still checked -- but against itself only, and it does
            # not mark ``step`` as disclosed. See :func:`is_game_record`.
            if isinstance(payload, dict) and isinstance(nonce, str) \
                    and isinstance(announced, str) and verify(payload, nonce, announced):
                verified += 1
            else:
                failed.append(step)
            continue
        seen.add(step)
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
        if received and step not in received and step < last_sealed:
            # Unbound, and not the in-flight tail: invented after the fact.
            unsolicited.append(step)
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
                             withheld_steps=withheld,
                             unsolicited_steps=sorted(unsolicited))


def audit_records(records: list[dict[str, Any]]) -> AuditResult:
    """Self-consistency only. Kept for the replay path; see the module docstring."""
    checked = audit_against_commitments(records, None)
    return AuditResult(passed=checked.passed, verified_steps=checked.verified_steps,
                       failed_steps=checked.failed_steps)
