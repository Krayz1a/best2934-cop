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

#: The only payload fields a peer may disclose mid-game (interop item I-5).
#:
#: Everything else stays sealed until the final audit. Three fields are absent
#: on purpose, and the third is the one that actually mattered:
#:
#: ``move``
#:     A direction only locates an agent if you already know where it started,
#:     so this looks like the dangerous one and is the mildest of the three.
#: ``intent``
#:     The truth/lie flag. Disclosing it beside the hint it applies to would
#:     annotate every sentence with whether to believe it, which is the whole
#:     deception layer handed over for free (book ch5.3.1, ch7).
#: ``state``
#:     ``SHA256({step, role, position, board})``. Every field but ``position``
#:     is public -- step and role travel in the same message, and the board is
#:     grid size, axis convention and the barriers a cop must declare
#:     truthfully (rules 15, 16). That leaves 49 candidates. We brute-forced our
#:     own disclosed digest and recovered the exact cell in 49 hashes, every
#:     step, for both roles. The binding that stops a commitment being replayed
#:     in another context (ch5.3.1) was also a plaintext position broadcast.
#:
#: ``sub_game`` and ``barrier`` are named here but can no longer appear. Since we
#: adopted gal-roy1's payload shape it carries neither: there is no ``sub_game``
#: key at all, and a placement is encoded inside the sealed ``move`` as
#: ``BARRIER:r,c``. They are kept so that a peer still sending the older shape is
#: filtered rather than leaked, which is the job of an allow-list.
#:
#: The barrier is still declared openly every step, as rule 15 requires -- but
#: from the decision, via :meth:`~p2pchase.runtime.peer_session.PeerSession.
#: pending_declaration`, never from here. Reading it out of this view instead is
#: what silently stopped the networked peer declaring barriers at all; see
#: :meth:`~p2pchase.runtime.peer.PeerRunner._push_reveal`.
MID_GAME_FIELDS = ("step", "role", "sub_game", "hint", "barrier")


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
        """What the opponent may see at reveal time: :data:`MID_GAME_FIELDS` only.

        This used to disclose the whole payload, on the reasoning that a
        commitment the opponent already holds makes the content unforgeable
        anyway. True and beside the point -- unforgeable is not the same as
        secret, and the nonce is withheld until the audit (rule 18), so nothing
        disclosed here can even be *checked* until the match is over. The
        mid-game reveal buys no integrity; it only gives information away.

        So it now gives away exactly what the game requires and nothing more.
        The full payload is disclosed at the final audit, where the nonce makes
        it verifiable and the match is already decided.
        """
        body = {name: value for name, value in self.payload.items()
                if name in MID_GAME_FIELDS}
        return {"payload": body, "commit": self.commit}

    def audit_view(self) -> dict[str, Any]:
        """Full disclosure for the end-of-match mutual audit."""
        return {"payload": self.payload, "nonce": self.nonce, "commit": self.commit}


def commit(payload: dict[str, Any], nonce: str | None = None,
           form: str = "") -> CommitRecord:
    """Seal a payload. Returns the record; send only ``record.commit`` now.

    ``form`` names the construction this pairing agreed -- see
    :mod:`p2pchase.domain.kit_seal`. Empty means ours, which keeps every
    existing caller and every artifact already on disk unchanged.
    """
    from .kit_seal import DEFAULT_FORM, seal
    nonce = nonce or new_nonce()
    return CommitRecord(payload=payload, nonce=nonce,
                        commit=seal(payload, nonce, form or DEFAULT_FORM))


def verify(payload: dict[str, Any], nonce: str, announced_commit: str) -> bool:
    """Re-synthesise the opponent's hash and compare in constant time.

    Accepts *either* registered construction -- ours, with the nonce merged into
    the payload, or the league's ``canonical|nonce`` pipe. See
    :mod:`p2pchase.domain.kit_seal` for why both are sound and why refusing on
    the spelling cost us six sub-games' worth of audit against imreeyal.
    Imported inside the call because ``kit_seal`` imports this module.
    """
    from .kit_seal import opens
    return opens(payload, nonce, announced_commit)


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
    return hashlib.sha256(f"{secret}|{blob}".encode()).hexdigest()


def mutual_agreement_hash(result_summary: dict[str, Any]) -> str:
    """Hash both teams sign to certify they agree on the final result.

    Rule 35: if the two teams file contradictory reports -- or one fails to
    report at all -- the match is void and BOTH score 0. This digest is what
    each side puts in its own report so the lecturer can see they match.
    """
    return digest_payload(result_summary)
