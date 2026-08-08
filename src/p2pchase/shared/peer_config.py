"""One peer's complete view of its own configuration.

``PeerConfig`` deliberately exposes typed properties instead of letting callers
index raw dictionaries. Two reasons, both about failure modes: a typo in a
dotted key silently yields ``None`` at the worst possible moment, and the
defaults belong in one place rather than scattered across every call site.

The class also enforces the one value that is never the peer's to choose --
the address the agent reports to (Appendix F Table 20).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import constants
from ..domain import roles, scent_models, scoring
from ..domain.crypto import canonical_json, digest_payload
from .config_schema import AGREED_SECTIONS


@dataclass
class PeerConfig:
    """Everything one peer process needs to play a match.

    Input:  ``shared`` (the negotiated, byte-identical game terms),
            ``setup`` (this peer's private local settings),
            ``rate_limits`` (the gatekeeper contract).
    Output: typed accessors plus ``config_sha256`` for the pre-game lock.
    Setup:  ``role`` -- which side this process plays in the current sub-game.
    """

    role: str
    shared: dict[str, Any]
    setup: dict[str, Any]
    rate_limits: dict[str, Any] = field(default_factory=dict)
    shared_path: Path | None = None
    setup_path: Path | None = None
    problems: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- identity
    @property
    def _game(self) -> dict[str, Any]:
        return dict(self.setup.get("game", {}))

    @property
    def group_id(self) -> str:
        return str(self._game.get("group_id", "unknown-group"))

    @property
    def group_name(self) -> str:
        return str(self._game.get("group_name", self.group_id))

    @property
    def members(self) -> list[str]:
        return list(self._game.get("members", []))

    @property
    def repos(self) -> dict[str, str]:
        return dict(self._game.get("repos", {}))

    # -------------------------------------------------------------- network
    @property
    def _network(self) -> dict[str, Any]:
        return dict(self.setup.get("network", {}))

    @property
    def my_port(self) -> int:
        return int(self._network.get("my_port", 8801))

    @property
    def opponent_url(self) -> str:
        return str(self._network.get("opponent_url", ""))

    @property
    def public_url(self) -> str:
        """Tunnelled public URL, if one is configured (book rule 10)."""
        return str(self._network.get("public_url", ""))

    @property
    def turn_timeout(self) -> int:
        """Per-move deadline. The private setting may tighten the agreed one."""
        agreed = self.shared.get("network_and_league", {}).get("response_timeout_sec", 30)
        return int(self._network.get("turn_timeout_seconds", agreed))

    @property
    def watchdog_timeout(self) -> int:
        return int(self.shared.get("network_and_league", {}).get("watchdog_timeout_sec", 60))

    @property
    def num_sub_games(self) -> int:
        return int(self.shared.get("network_and_league", {}).get(
            "num_sub_games", constants.NUM_SUB_GAMES))

    # -------------------------------------------------------------- pairing
    def pairing(self, opponent: str) -> dict[str, Any]:
        """The terms agreed with ONE opponent, from the private setup file.

        Some terms the book leaves to inter-team agreement are genuinely
        per-pair rather than league-wide: which role convention orders the six
        sub-games, and which scent model the two peers run. We hold
        ``first_half`` with gal-roy1 and ``odd_even`` with imreeyal, and that is
        not a contradiction -- it is two pairings, each internally agreed.

        They live in ``setup.json`` rather than ``game.json`` on purpose. The
        agreed game terms are hashed into ``config_sha256`` and signed, so an
        extra key there changes a digest both peers have already verified;
        these are private, unsigned, and never cross the wire. What crosses is
        the *consequence* -- a role in ``declare_step0``, a model hash in the
        negotiate extras.
        """
        book = self.setup.get("opponents", {})
        return dict(book.get(str(opponent), {})) if isinstance(book, dict) else {}

    def role_convention(self, opponent: str) -> str:
        """Which sub-game ordering we agreed with this opponent."""
        return str(self.pairing(opponent).get("role_convention", roles.DEFAULT_CONVENTION))

    def scent_model(self, opponent: str) -> str:
        """Which registered scent model we agreed with this opponent."""
        return str(self.pairing(opponent).get("scent_model", scent_models.DEFAULT_MODEL))

    def tie_rule(self, opponent: str) -> str:
        """How a dead-level series is scored against this opponent.

        Three teams could each be conformant and each compute a different total
        for the same tied series, so this is a declared term rather than a
        derivable one. Undeclared is the only unsafe answer: it stays invisible
        until a series happens to tie, which never occurs in friendlies and
        costs both teams the match when it does (rule 35).
        """
        return str(self.pairing(opponent).get("tie_rule", scoring.SERIES_ADD))

    def counted_series(self, opponent: str) -> tuple[bool, str]:
        """Is a series against this opponent counted, and on whose sign-off?

        Returns ``(counted, reason)`` for :func:`p2pchase.reports.league
        .league_block`. Both come from the private ``setup.json``, which no code
        path writes -- arming the marker is a human editing a file, which is the
        only thing that should be able to turn a friendly into a counted game.

        Absent is uncounted. That is the safe direction and the only one the
        rulebook forgives: reporting a counted series as a friendly understates
        our own standing, while reporting a friendly as counted is a false
        declaration under rules 37-38 and costs both teams.
        """
        pairing = self.pairing(opponent)
        return (bool(pairing.get("counted", False)),
                str(pairing.get("counted_sign_off", "")))

    # ------------------------------------------------------------- strategy
    @property
    def strategy(self) -> dict[str, Any]:
        return dict(self.setup.get("strategy", {}))

    @property
    def trash_talk(self) -> dict[str, Any]:
        return dict(self.setup.get("trash_talk", {"provider": "template"}))

    @property
    def llm(self) -> dict[str, Any]:
        return dict(self.setup.get("llm", {}))

    @property
    def email(self) -> dict[str, Any]:
        """E-mail settings with the reporting address forced to the book value.

        A team cannot opt out of reporting by pointing the agent somewhere
        else, so the recipient is overwritten rather than defaulted.
        """
        cfg = dict(self.setup.get("email", {}))
        cfg["recipient"] = constants.AGENT_REPORT_EMAIL
        return cfg

    # ---------------------------------------------------------------- hashes
    def agreed_terms(self) -> dict[str, Any]:
        """The subset of the shared config that both peers signed."""
        return {k: self.shared[k] for k in AGREED_SECTIONS if k in self.shared}

    def config_sha256(self) -> str:
        """Digest of the agreed terms only -- the value both peers compare."""
        return digest_payload(self.agreed_terms())

    def canonical_shared(self) -> str:
        return canonical_json(self.agreed_terms())
