"""Commit-Reveal over SHA-256 -- integrity without a judge.

Book chapter 5. There is no referee on this network, so trust is not assumed,
it is proved. Every step runs four mandatory phases in order:

  1. Commit          -- send ONLY ``H = SHA256(canonical_json(record))``.
  2. Acknowledge     -- the opponent confirms it is locked on that commitment.
  3. Reveal          -- send the move and the verbal hint. The nonce stays secret.
  4. Final Reveal    -- at the END of the match, all nonces are disclosed and
                        both sides re-hash every step (mutual audit).

Any mismatch between a recomputed hash and the hash announced at commit time
proves tampering. There is no room for interpretation and no statistical doubt:
SHA-256 is sensitive to a single bit. The forging team takes a technical loss --
score 0 -- regardless of what happened on the board (rules 17-19).

The nonce is what makes this safe. The move space is tiny (five moves), so
without a fresh random nonce per commitment an opponent could pre-hash every
possibility and crack the commitment instantly (dictionary attack). It is kept
absolutely secret until the final audit (rule 18).
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from typing import Any

NONCE_BYTES = 16


def canonical_json(payload: Any) -> str:
    """Deterministic serialisation: sorted keys, no incidental whitespace.

    Both peers must hash byte-identical input, so the representation cannot be
    left to chance -- key order and separators are pinned.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_payload(payload: Any) -> str:
    return sha256_hex(canonical_json(payload))


def new_nonce() -> str:
    """Cryptographically strong nonce.

    ``secrets``, never ``random`` -- the latter is predictable and would let an
    opponent reconstruct commitments.
    """
    return secrets.token_hex(NONCE_BYTES)


@dataclass
class CommitRecord:
    """One sealed step: the payload, its nonce, and the announced commitment.

    The payload is deliberately richer than the four fields named in the book's
    formula (state, move, intent, nonce): it also carries the verbal hint, the
    step number, the role and the sub-game number, exactly as the reference
    implementation seals them. What matters is that BOTH peers hash the same
    canonical object.
    """

    payload: dict[str, Any]
    nonce: str
    commit: str
    revealed: bool = False

    def sealed_view(self) -> dict[str, Any]:
        """What the opponent may see at commit time: the hash and nothing else."""
        return {"step": self.payload.get("step"), "commit": self.commit}

    def revealed_view(self) -> dict[str, Any]:
        """What the opponent may see at reveal time: content, but not the nonce."""
        body = {k: v for k, v in self.payload.items()}
        return {"payload": body, "commit": self.commit}

    def audit_view(self) -> dict[str, Any]:
        """Full disclosure for the end-of-match mutual audit."""
        return {"payload": self.payload, "nonce": self.nonce, "commit": self.commit}


def commit(payload: dict[str, Any], nonce: str | None = None) -> CommitRecord:
    """Seal a payload. Returns the record; send only ``record.commit`` now."""
    nonce = nonce or new_nonce()
    sealed = dict(payload)
    sealed["nonce"] = nonce
    return CommitRecord(payload=payload, nonce=nonce, commit=digest_payload(sealed))


def verify(payload: dict[str, Any], nonce: str, announced_commit: str) -> bool:
    """Re-synthesise the opponent's hash and compare in constant time."""
    sealed = dict(payload)
    sealed["nonce"] = nonce
    recomputed = digest_payload(sealed)
    return secrets.compare_digest(recomputed, announced_commit)


@dataclass
class AuditResult:
    """Outcome of a mutual log audit."""

    passed: bool
    verified_steps: int
    failed_steps: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verified_steps": self.verified_steps,
            "failed_steps": self.failed_steps,
        }


def audit_records(records: list[dict[str, Any]]) -> AuditResult:
    """Verify a whole disclosed log, step by step.

    ``records`` are audit views: ``{"payload": ..., "nonce": ..., "commit": ...}``.
    This is the function the Replay Viewer drives to show ``Verified OK``, and
    the same one each peer runs against its opponent's disclosed log at the end
    of a match (rule 36 -- the audit is a precondition for agreeing the result).
    """
    failed: list[int] = []
    verified = 0
    for index, record in enumerate(records):
        payload = record.get("payload")
        nonce = record.get("nonce")
        announced = record.get("commit")
        if not isinstance(payload, dict) or not isinstance(nonce, str) or not isinstance(announced, str):
            failed.append(int(payload.get("step", index)) if isinstance(payload, dict) else index)
            continue
        if verify(payload, nonce, announced):
            verified += 1
        else:
            failed.append(int(payload.get("step", index)))
    return AuditResult(passed=not failed, verified_steps=verified, failed_steps=failed)


def sign_declaration(payload: dict[str, Any], secret: str) -> str:
    """Sign the Step-0 hardware declaration so it cannot be back-dated.

    Book ch5.5: the machine spec, the code version, the group name and the
    sub-game number are packed into JSON and signed with a key fixed in
    advance, so a team cannot retroactively claim it ran on weaker hardware to
    farm the computational-fairness bonus.
    """
    blob = canonical_json(payload)
    return hashlib.sha256(f"{secret}|{blob}".encode("utf-8")).hexdigest()


def mutual_agreement_hash(result_summary: dict[str, Any]) -> str:
    """Hash both teams sign to certify they agree on the final result.

    Rule 35: if the two teams file contradictory reports -- or one fails to
    report at all -- the match is void and BOTH score 0. This digest is what
    each side puts in its own report so the lecturer can see they match.
    """
    return digest_payload(result_summary)
