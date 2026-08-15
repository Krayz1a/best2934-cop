"""Pre-game negotiation: agreeing the physics before anyone moves (book ch4-5).

Without a referee, "we agreed on the rules" has to mean something checkable.
Two peers therefore exchange three fingerprints before the first move, and
refuse to play unless all three match:

``config_sha256``
    The agreed game parameters. Byte-identical on both sides (rule 11).

``scent_fingerprint``
    The 5x5 emission kernel and decay rate. This one is subtle and matters more
    than it looks: the pheromone field is the only *unforgeable* evidence in the
    game, and it is only unforgeable if both peers compute it identically. Two
    teams reading the same figure and rounding differently would produce silent,
    permanent disagreement about physical evidence.

``schema_version``
    The artifact schema, so neither side writes a log the other cannot verify.
    Compared on the MAJOR component only. This was an exact comparison and it
    was wrong: our opponent published 1.2 to our 1.1 and every handshake between
    two teams that agreed on all thirty-odd game parameters aborted before the
    first move, over a digit whose whole documented meaning is "optional keys
    were added". A major bump redefines existing keys and still refuses.

A mismatch is not negotiated away here. It is reported with the specific
parameters that differ, so the humans can fix the config and restart.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..domain import core_terms, scent_models
from ..domain.smell import build_kernel, kernel_fingerprint
from ..infra.sysinfo import git_commit
from ..reports.history import counted_games_played
from ..shared.config_schema import validate_shared
from ..shared.peer_config import PeerConfig
from ..shared.version import CODE_VERSION, peer_schema_compatible
from . import agreement_floor

LOGGER = logging.getLogger(__name__)


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
            nonce=str(payload.get("nonce", "")),
            signature=str(payload.get("signature", "")),
        )


@dataclass
class Agreement:
    """The verdict of comparing two handshakes."""

    agreed: bool
    mismatches: list[str] = field(default_factory=list)
    ours: dict[str, Any] = field(default_factory=dict)
    theirs: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "agreed": self.agreed,
            "mismatches": list(self.mismatches),
            "ours": dict(self.ours),
            "theirs": dict(self.theirs),
        }


class NegotiationService:
    """Builds our handshake and judges the opponent's.

    Input:  a loaded :class:`PeerConfig`; the opponent's handshake payload.
    Output: an :class:`Agreement` that either clears the match to start or names
            every parameter the two sides disagree about.
    Setup:  none beyond the config -- the whole point is that both peers reach
            the same verdict from public values alone.
    """

    def __init__(self, config: PeerConfig) -> None:
        self.config = config
        #: One nonce for this peer process, not one per call.
        #:
        #: A fresh nonce per ``hello`` looked more careful and was wrong. The
        #: opponent may greet us more than once -- a retry, a reconnect, a
        #: readiness probe -- and a greeting that answers differently each time
        #: is not a greeting they can hold us to: the agreement recorded in the
        #: declaration artifact would not be the one we served a minute later.
        #: Our own binding tests caught it, comparing two invocations.
        #:
        #: Freshness is not what the nonce is for here. Unlike a commitment
        #: there is nothing to brute-force -- the terms travel in the clear
        #: beside it -- so it exists to bind the signature to *this pairing*
        #: rather than to each packet. Process-scoped is exactly that scope.
        self._nonce = core_terms.new_nonce()

    def scent_fingerprint(self, opponent: str = "") -> str:
        """Hash of the emission kernel and decay rate both peers must share.

        Keyed on the opponent for the same reason the model lock is: under
        ``subtractive_chebyshev_v1`` the kernel is a falloff formula rather than
        the book's printed table, so publishing the book's fingerprint while
        emitting Chebyshev rings would be a declaration that does not describe
        what we run. Wrong in the direction that matters -- it would pass.
        """
        shared = self.config.shared
        model = self.config.scent_model(opponent)
        pheromones = shared["pheromones"]
        kernel = (scent_models.chebyshev_kernel(
                      int(pheromones.get("pheromone_grid_size", 5)),
                      float(pheromones.get("pheromone_center_intensity", 0.9)))
                  if model == scent_models.SUBTRACTIVE else build_kernel(shared))
        return kernel_fingerprint(kernel, float(pheromones["pheromone_decay"]))

    def handshake(self, mcp_url: str = "", opponent: str = "",
                  nonce: str = "") -> Handshake:
        """Our own published fingerprints.

        ``opponent`` selects the scent model, because that lock is agreed per
        pairing rather than per league -- we run the book's model with gal-roy1
        and the reference's with imreeyal. Absent an opponent we declare our
        default, which is what the very first outbound greeting carries; the
        moment we read their group id we re-derive and declare the model we
        actually agreed with *them*.
        """
        return Handshake(
            group_id=self.config.group_id,
            group_name=self.config.group_name,
            code_version=CODE_VERSION,
            schema_version=str(self.config.shared.get("schema_version", "")),
            config_sha256=self.config.config_sha256(),
            scent_fingerprint=self.scent_fingerprint(opponent),
            scent_model_sha256=scent_models.locked_sha256(self.config.scent_model(opponent)),
            counted_games_played=counted_games_played(),
            mcp_url=mcp_url or self.config.public_url or
            f"http://127.0.0.1:{self.config.my_port}/mcp",
            repos=self.config.repos,
            **core_terms.signed_agreement(self.config.shared, nonce or self._nonce),
        )

    def compare(self, theirs: Handshake | dict[str, Any]) -> Agreement:
        """Compare fingerprints and report every difference at once."""
        if isinstance(theirs, dict):
            theirs = Handshake.from_dict(theirs)
        ours = self.handshake(opponent=theirs.group_id)

        # The floor under every omission rule below. See
        # :mod:`p2pchase.services.agreement_floor`: each "refuse only if both
        # declare" guard is right on its own and together they made an empty
        # payload the most agreeable message we could receive.
        mismatches: list[str] = agreement_floor.refusals(theirs)

        # config_sha256 is a digest of OUR config's shape. It gets the same
        # omission rule as the two scent locks, and for a stronger reason than
        # politeness: it is not a league value at all.
        #
        # We made exactly this argument to imreeyal about their gate -- two
        # peers hashing differently-shaped objects can never match, so the
        # mismatch carries no information -- and did not apply it to our own,
        # where it was refusing them. A peer that sends no config_sha256
        # arrived with "" and was refused every time, so the two of us refused
        # each other in both directions and neither could open a sub-game.
        # The values are compared below, in the shape the league actually
        # agreed in; the digest is now corroboration between peers who happen
        # to share our layout, never the gate.
        if scent_models.lock_refuses(ours.config_sha256, theirs.config_sha256):
            mismatches.append(
                f"config_sha256: ours={ours.config_sha256} theirs={theirs.config_sha256}")

        # The fourteen CORE terms, compared as values. This is the check that
        # config_sha256 was standing in for and could not perform across
        # implementations.
        if theirs.terms:
            if not core_terms.signature_verifies(theirs.terms, theirs.nonce, theirs.signature):
                mismatches.append(
                    f"terms signature does not verify over the terms sent "
                    f"(nonce={theirs.nonce!r}); expected "
                    f"SHA256(canonical_json(terms)|nonce), a single pipe")
            mismatches.extend(core_terms.term_differences(ours.terms, theirs.terms))

        # The two scent locks are compared under the league's omission rule:
        # refuse only when BOTH peers declare and the values differ. Silence is
        # never refusal, in either direction.
        #
        # This is not politeness, it is the difference between having opponents
        # and not having them. `scent_fingerprint` is *our* construction, agreed
        # bilaterally with gal-roy1 and unknown to everyone else; comparing it
        # strictly meant any team that had simply never heard of it arrived with
        # an empty string and was refused at the handshake. We would have been
        # turning away the opponents rule 31 requires us to find, using a field
        # we invented, and reading it as their fault.
        for label, mine, yours in (
            ("scent_fingerprint", ours.scent_fingerprint, theirs.scent_fingerprint),
            ("scent_model_sha256", ours.scent_model_sha256, theirs.scent_model_sha256),
        ):
            if scent_models.lock_refuses(mine, yours):
                mismatches.append(f"{label}: ours={mine} theirs={yours}")

        # Major-only, not exact. An exact comparison aborted the handshake on a
        # MINOR bump, which by our own definition only ever adds optional keys --
        # so two peers that understood each other perfectly refused to play over
        # a digit. A major bump redefines existing keys and must still refuse.
        #
        # And only when they declare one. ``schema_version`` is ours, not the
        # league's: the reference-v3 wire does not carry the field at all, so
        # every peer speaking it arrived with "" and was refused for an
        # "incompatible major version" it had never claimed. That is the third
        # time this exact reasoning has had to be applied -- after the two scent
        # locks and ``config_sha256`` -- and the rule has been the same every
        # time: refuse when both peers declare and the values are incompatible,
        # never on silence. A malformed version is still a refusal; ``""`` is
        # not malformed, it is absent.
        if theirs.schema_version and not peer_schema_compatible(
                ours.schema_version, theirs.schema_version):
            mismatches.append(
                f"schema_version: ours={ours.schema_version} theirs={theirs.schema_version} "
                "(incompatible major version)"
            )

        if ours.group_id == theirs.group_id:
            mismatches.append(
                f"group_id collision: both peers claim {ours.group_id!r}; "
                "rule 3 requires a unique 8-character code per team"
            )

        for problem in validate_shared(self.config.shared):
            mismatches.append(f"our own config is illegal — {problem}")

        agreement = Agreement(not mismatches, mismatches, ours.as_dict(), theirs.as_dict())
        if agreement.agreed:
            LOGGER.info("handshake agreed with %s (config %s)",
                        theirs.group_id, ours.config_sha256[:16])
        else:
            LOGGER.error("handshake REFUSED: %s", "; ".join(mismatches))
        return agreement
