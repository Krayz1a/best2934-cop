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

from .. import constants as K
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
            "num_sub_games", K.NUM_SUB_GAMES))

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
        cfg["recipient"] = K.AGENT_REPORT_EMAIL
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
