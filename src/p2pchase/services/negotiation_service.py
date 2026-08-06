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

from ..domain import scent_models
from ..domain.smell import build_kernel, kernel_fingerprint
from ..shared.config_schema import validate_shared
from ..shared.peer_config import PeerConfig
from ..shared.version import CODE_VERSION, peer_schema_compatible

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
    repos: dict[str, str] = field(default_factory=dict)
    #: The league's locked-model declaration for the ``scent_model`` family --
    #: a hash of the registered document, never the document itself. Defaults
    #: to empty because an opponent who declares nothing must still be
    #: playable; see :func:`p2pchase.domain.scent_models.lock_refuses`.
    scent_model_sha256: str = ""

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
            "repos": dict(self.repos),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Handshake:
        return cls(
            group_id=str(payload.get("group_id", "")),
            group_name=str(payload.get("group_name", "")),
            code_version=str(payload.get("code_version", "")),
            schema_version=str(payload.get("schema_version", "")),
            config_sha256=str(payload.get("config_sha256", "")),
            scent_fingerprint=str(payload.get("scent_fingerprint", "")),
            scent_model_sha256=str(payload.get("scent_model_sha256", "")),
            mcp_url=str(payload.get("mcp_url", "")),
            repos=dict(payload.get("repos", {})),
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

    def handshake(self, mcp_url: str = "", opponent: str = "") -> Handshake:
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
            mcp_url=mcp_url or self.config.public_url or
            f"http://127.0.0.1:{self.config.my_port}/mcp",
            repos=self.config.repos,
        )

    def compare(self, theirs: Handshake | dict[str, Any]) -> Agreement:
        """Compare fingerprints and report every difference at once."""
        if isinstance(theirs, dict):
            theirs = Handshake.from_dict(theirs)
        ours = self.handshake(opponent=theirs.group_id)

        mismatches: list[str] = []
        if ours.config_sha256 != theirs.config_sha256:
            mismatches.append(
                f"config_sha256: ours={ours.config_sha256} theirs={theirs.config_sha256}")

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
        if not peer_schema_compatible(ours.schema_version, theirs.schema_version):
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
