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

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "code_version": self.code_version,
            "schema_version": self.schema_version,
            "config_sha256": self.config_sha256,
            "scent_fingerprint": self.scent_fingerprint,
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

    def scent_fingerprint(self) -> str:
        """Hash of the emission kernel and decay rate both peers must share."""
        shared = self.config.shared
        return kernel_fingerprint(
            build_kernel(shared), float(shared["pheromones"]["pheromone_decay"])
        )

    def handshake(self, mcp_url: str = "") -> Handshake:
        """Our own published fingerprints."""
        return Handshake(
            group_id=self.config.group_id,
            group_name=self.config.group_name,
            code_version=CODE_VERSION,
            schema_version=str(self.config.shared.get("schema_version", "")),
            config_sha256=self.config.config_sha256(),
            scent_fingerprint=self.scent_fingerprint(),
            mcp_url=mcp_url or self.config.public_url or
            f"http://127.0.0.1:{self.config.my_port}/mcp",
            repos=self.config.repos,
        )

    def compare(self, theirs: Handshake | dict[str, Any]) -> Agreement:
        """Compare fingerprints and report every difference at once."""
        if isinstance(theirs, dict):
            theirs = Handshake.from_dict(theirs)
        ours = self.handshake()

        mismatches: list[str] = []
        for label, mine, yours in (
            ("config_sha256", ours.config_sha256, theirs.config_sha256),
            ("scent_fingerprint", ours.scent_fingerprint, theirs.scent_fingerprint),
        ):
            if mine != yours:
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
