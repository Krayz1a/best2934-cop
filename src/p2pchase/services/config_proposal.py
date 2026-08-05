"""Answering a proposed configuration, rather than comparing two fingerprints.

``propose_config`` looked like our ``negotiate`` and is not the same operation,
which cost us a preflight. Our comparator read the caller's payload as a
*handshake* -- group id, config digest, scent fingerprint -- found none of those
fields in ``{"config": {...}}``, and reported three mismatches against empty
strings. The refusal was internally consistent and completely wrong.

The distinction, which gal-roy1 put better than we had it:

    ``config_sha256`` exists to prove the two CANONICALISATIONS agree. They
    send an object, we hash *that object*, and matching digests mean our JSON
    encodings are identical. It is not a test that their defaults equal ours.

Read as a defaults test, the check can only ever pass against a peer whose
config file is byte-identical to ours -- which no independently written group's
file will be, and which would make rule 11 unsatisfiable rather than satisfied.
Read as a canonicalisation test, adopting their object is what makes both peers
byte-identical, which is what rule 11 actually asks for.

What we still refuse is a proposal that is *illegal*: Appendix F's PERMANENT
terms may not change at all and its MINIMUM floors may be raised but never
lowered (rule 12). Agreeing to those would be a disqualification we consented
to. So the answer is "yes to your encoding, and here is every term of yours
that breaks the book" -- never a bare no.
"""

from __future__ import annotations

import logging
from typing import Any

from ..domain.crypto import canonical_json, sha256_hex
from ..shared.config_schema import validate_shared
from ..shared.peer_config import PeerConfig

LOGGER = logging.getLogger(__name__)


def config_digest(config: dict[str, Any]) -> str:
    """The digest of a proposed config, under our canonical encoding."""
    return sha256_hex(canonical_json(config))


def differing_terms(theirs: dict[str, Any], ours: dict[str, Any],
                    path: str = "") -> list[str]:
    """Every term where the two configs disagree, named in full.

    Reported but not refused. A difference is information for the humans -- a
    digest tells you *that* two configs differ and never *what* about, and we
    have now watched both teams lose time to exactly that.
    """
    problems: list[str] = []
    for key in sorted(set(theirs) | set(ours)):
        if key.startswith("_"):
            continue  # remarks and schema prose are commentary, not terms
        here = f"{path}.{key}" if path else key
        mine, yours = ours.get(key), theirs.get(key)
        if isinstance(mine, dict) and isinstance(yours, dict):
            problems.extend(differing_terms(yours, mine, here))
        elif mine != yours:
            problems.append(f"{here}: ours={mine!r} theirs={yours!r}")
    return problems


class ConfigProposalService:
    """Judges a config an opponent proposes we both play under (rules 11, 12)."""

    def __init__(self, config: PeerConfig) -> None:
        self.config = config

    def answer(self, proposed: dict[str, Any]) -> dict[str, Any]:
        """Accept their encoding, or say exactly which book term forbids it."""
        theirs = config_digest(proposed)
        # Both digests must be over the same SHAPE or comparing them is
        # meaningless. ``config_sha256`` in our own handshake covers
        # ``agreed_terms`` -- a subset, excluding derived naming metadata --
        # while a proposing peer hashes its whole file. Reporting the subset
        # digest here next to a whole-object digest would show two numbers that
        # differ for a reason that has nothing to do with either config, which
        # is precisely the confusion this field exists to remove. Both are
        # sent, each labelled with what it covers.
        ours = config_digest(self.config.shared)
        illegal = validate_shared(proposed)
        differences = differing_terms(proposed, self.config.shared)

        if illegal:
            LOGGER.error("refusing a proposed config: %s", "; ".join(illegal))
        elif differences:
            LOGGER.info("accepting a proposed config that differs from ours in %d term(s)",
                        len(differences))

        return {
            "ok": not illegal,
            "accepted": not illegal,
            # Their object under our encoding -- the number they asked for.
            "config_sha256": theirs,
            # Ours, same shape, so a canonicalisation mismatch is diagnosable
            # from a single message rather than from a second round trip.
            "our_config_sha256": ours,
            # The subset our ``hello`` publishes. Named explicitly because a
            # peer comparing it to a whole-file digest would mismatch forever
            # and conclude our configs disagree when only our scopes do.
            "our_agreed_terms_sha256": self.config.config_sha256(),
            "digest_covers": "the whole proposed config object, canonical JSON",
            "illegal_terms": illegal,
            "differing_terms": differences,
            "mismatches": illegal,
        }
