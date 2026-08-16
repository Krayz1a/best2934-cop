"""What a peer publishes about itself, and how to read another's.

Split out of :mod:`p2pchase.services.negotiation_service` when the commit-form
declaration pushed that file past the 150-line limit. The service decides
whether two greetings agree; this is the greeting itself, which is a different
job and a different reason to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..infra.sysinfo import git_commit


@dataclass
class Handshake:
    """What one peer publishes about itself before a match begins."""

    group_id: str
    group_name: str
    code_version: str
    schema_version: str
    config_sha256: str
    scent_fingerprint: str
    mcp_url: str
    #: Rules 37-38 and 53, declared where the opponent can actually read them.
    #: Both rode only our `hello` REPLY, which fires when a peer calls us -- so
    #: when we drive, neither ever left this machine. anrbj666's declaration
    #: artifact recorded `counted_games_played: 0` for us and `github_commit:
    #: "unknown"` in all six rows, and read it as a stale build. It was not:
    #: the fields were absent from the outbound handshake entirely, so a
    #: restart would have fixed nothing and we would have "fixed" it twice.
    counted_games_played: int = 0
    repos: dict[str, str] = field(default_factory=dict)
    #: The league's locked-model declaration for the ``scent_model`` family --
    #: a hash of the registered document, never the document itself. Defaults
    #: to empty because an opponent who declares nothing must still be
    #: playable; see :func:`p2pchase.domain.scent_models.lock_refuses`.
    scent_model_sha256: str = ""
    #: The kit's CORE agreement: the fourteen terms in the clear, a nonce, and
    #: ``SHA256(canonical_json(terms)|nonce)``. Everything above describes *us*;
    #: this is the only part that states the game we think we are playing, and
    #: it is what the rest of the league gates on. See
    #: :mod:`p2pchase.domain.core_terms`.
    terms: dict[str, Any] = field(default_factory=dict)
    #: How we seal a commitment, named AND spelled out. gal-roy1 had to assume
    #: ours on 2026-08-16 -- it happened to match, and they rightly said a
    #: counted audit should not rest on a lucky guess. The name alone is not
    #: enough: they call the same construction ``nonce_in_payload`` and we call
    #: it ``merged_nonce_v1``, so two peers can agree on the arithmetic and
    #: still fail to recognise it in each other's vocabulary. The formula is
    #: the part that cannot be misread.
    commit_form: str = ""
    commit_formula: str = ""
    nonce: str = ""
    signature: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "code_version": self.code_version,
            "schema_version": self.schema_version,
            "config_sha256": self.config_sha256,
            "scent_fingerprint": self.scent_fingerprint,
            "scent_model_sha256": self.scent_model_sha256,
            "mcp_url": self.mcp_url,
            "counted_games_played": self.counted_games_played,
            "github_commit": git_commit(),
            "repos": dict(self.repos),
            "terms": dict(self.terms),
            "commit_form": self.commit_form,
            "commit_formula": self.commit_formula,
            "nonce": self.nonce,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Handshake:
        """Read a greeting in either the league's flat shape or reference-v3's.

        The reference nests who-you-are under ``identity`` -- ``group_id``,
        ``group_name``, ``repos`` and an ``mcp_servers`` map -- and leaves the
        agreement itself (terms, nonce, signature, the locks) at the top level.
        Reading only the flat shape does not merely lose a label: ``compare``
        re-derives *our own* per-pair terms from ``theirs.group_id``, so an
        unread group id silently selects our default scent model. Against
        imreeyal that is the book's model where the reference's was agreed, and
        both peers declaring different values is precisely what the lock is
        built to refuse. We would have refused them for a physics disagreement
        manufactured by our own parser -- the same fault we had just warned them
        about, pointing the other way.

        ``mcp_servers`` is a role map rather than one URL, so it is not folded
        into ``mcp_url``; a greeting names one peer and guessing which role it
        speaks for would put a wrong endpoint in the record.
        """
        identity = payload.get("identity")
        identity = identity if isinstance(identity, dict) else {}

        def field_of(name: str) -> Any:
            value = payload.get(name)
            return identity.get(name, value) if value in (None, "", {}) else value

        return cls(
            group_id=str(field_of("group_id") or ""),
            group_name=str(field_of("group_name") or ""),
            code_version=str(field_of("code_version") or ""),
            schema_version=str(payload.get("schema_version", "")),
            config_sha256=str(payload.get("config_sha256", "")),
            scent_fingerprint=str(payload.get("scent_fingerprint", "")),
            scent_model_sha256=str(payload.get("scent_model_sha256", "")),
            mcp_url=str(payload.get("mcp_url", "")),
            repos=dict(field_of("repos") or {}),
            terms=dict(payload.get("terms", {})),
            commit_form=str(payload.get("commit_form", "")),
            commit_formula=str(payload.get("commit_formula", "")),
            nonce=str(payload.get("nonce", "")),
            signature=str(payload.get("signature", "")),
        )
