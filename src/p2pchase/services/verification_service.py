"""Log verification and mutual audit (book ch7.4-7.5, rules 19-20, 36).

Two jobs, and the difference between them is who is being checked.

:meth:`VerificationService.verify_own` re-runs our own commitments -- a
self-check that the log we are about to publish is internally consistent.

:meth:`VerificationService.audit_opponent` is the one the book cares about
(rule 36): after the match each team replays the other's log. A single altered
bit anywhere in a payload changes its digest completely, so tampering cannot
hide, and the verdict is arithmetic rather than opinion. Rule 19 makes a
mismatch a technical loss scoring zero -- which is why this service never
"warns" about a failed step. It fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.crypto import mutual_agreement_hash
from ..ui.replay import ReplayResult, load_log, render_text, verify_log

LOGGER = logging.getLogger(__name__)


@dataclass
class AuditVerdict:
    """The outcome of auditing one opponent log."""

    path: str
    game_id: str
    sub_game: int
    role: str
    passed: bool
    verified_steps: int
    total_steps: int
    failed_steps: list[int]
    banner: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "game_id": self.game_id,
            "sub_game_number": self.sub_game,
            "role": self.role,
            "passed": self.passed,
            "verified_steps": self.verified_steps,
            "total_steps": self.total_steps,
            "failed_steps": list(self.failed_steps),
            "banner": self.banner,
        }


def _verdict(path: Path, result: ReplayResult) -> AuditVerdict:
    return AuditVerdict(
        path=str(path),
        game_id=result.game_id,
        sub_game=result.sub_game,
        role=result.role,
        passed=result.passed,
        verified_steps=result.verified_steps,
        total_steps=len(result.verdicts),
        failed_steps=result.failed_steps,
        banner=result.banner(),
    )


class VerificationService:
    """Replays disclosed logs and decides whether they are trustworthy.

    Input:  paths to log JSON files.
    Output: :class:`AuditVerdict` objects and human-readable replay text.
    Setup:  none -- verification depends on nothing but the log and SHA-256,
            which is precisely what makes an opponent's audit meaningful.
    """

    def verify_file(self, path: Path | str) -> AuditVerdict:
        """Verify one log file's commit chain end to end."""
        path = Path(path)
        result = verify_log(load_log(path))
        verdict = _verdict(path, result)
        level = logging.INFO if verdict.passed else logging.ERROR
        LOGGER.log(level, "%s — %s", path.name, verdict.banner)
        return verdict

    def verify_own(self, paths: list[Path | str]) -> list[AuditVerdict]:
        """Self-check every log we are about to publish."""
        return [self.verify_file(path) for path in paths]

    def audit_opponent(self, paths: list[Path | str]) -> tuple[bool, list[AuditVerdict]]:
        """Audit an opponent's logs (rule 36). Returns (all_passed, verdicts)."""
        verdicts = [self.verify_file(path) for path in paths]
        return all(v.passed for v in verdicts), verdicts

    def render(self, path: Path | str, limit: int | None = None) -> str:
        """Human-readable replay -- the text the README screenshot captures."""
        return render_text(verify_log(load_log(Path(path))), limit=limit)

    @staticmethod
    def agreement_digest(summary: dict[str, Any]) -> str:
        """Fingerprint both teams compute over the agreed result (rule 35).

        Two matching digests prove the teams recorded the same match; a mismatch
        exposes a contradicting report, which voids the match for both sides.
        """
        return mutual_agreement_hash(summary)

    def confirm_agreement(self, ours: dict[str, Any], theirs_digest: str) -> bool:
        """True when the opponent's digest matches the one we computed."""
        mine = self.agreement_digest(ours)
        agreed = mine == theirs_digest
        if not agreed:
            LOGGER.error("result mismatch: ours=%s theirs=%s — rule 35 voids the match "
                         "for BOTH teams until this is reconciled", mine, theirs_digest)
        return agreed
