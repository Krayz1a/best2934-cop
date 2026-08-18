"""The SDK: the single entry point for every consumer (guidelines §4.1).

    External consumers (GUI / CLI / tests / future integrations)
                              |
                              v
                        +-----------+
                        |    SDK    |  <-- single entry point for ALL logic
                        +-----+-----+
                              |
                              v
                    +---------------------+
                    |  Domain services    |  match, verification,
                    |                     |  negotiation, reporting
                    +---------+-----------+
                              |
                              v
                    +---------------------+
                    |  Infrastructure     |  Gatekeeper, Gmail, sysinfo, files
                    +---------------------+

The rule this enforces is that no consumer reaches past this class. The CLI
parses arguments and prints; the GUI draws. Neither decides anything, because
business logic that lives in a presentation layer cannot be tested without that
layer and cannot be reused by the next one.

Services are constructed lazily so that importing the SDK costs nothing --
useful in tests, and useful for a CLI subcommand that only needs one of them.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .. import constants
from ..infra.sysinfo import collect_hardware, git_commit
from ..services.match_service import MatchService, SeriesResult
from ..services.negotiation_service import Agreement, Handshake, NegotiationService
from ..services.network_artifacts import NetworkArtifactService
from ..services.reporting_service import DeliveryReceipt, ReportingService
from ..services.verification_service import AuditVerdict, VerificationService
from ..shared.config import load_config
from ..shared.peer_config import PeerConfig
from ..shared.version import CODE_VERSION

LOGGER = logging.getLogger(__name__)


class P2PChaseSDK:
    """Every operation this project can perform, in one object.

    Input:  a role and, optionally, an explicit config directory.
    Output: results from the four domain services.
    Setup:  ``output_dir`` for artifacts, ``signing_secret`` for the Step-0
            hardware declaration (read from the environment by the CLI, never
            from a config file).
    """

    def __init__(self, config: PeerConfig, output_dir: Path | None = None,
                 signing_secret: str = "") -> None:
        self.config = config
        self.output_dir = output_dir
        self.signing_secret = signing_secret
        self._match: MatchService | None = None
        self._network_artifacts: NetworkArtifactService | None = None
        self._verification: VerificationService | None = None
        self._negotiation: NegotiationService | None = None
        self._reporting: ReportingService | None = None

    @classmethod
    def for_role(cls, role: str = constants.DEFAULT_ROLE,
                 config_dir: Path | str | None = None,
                 output_dir: Path | None = None, signing_secret: str = "") -> P2PChaseSDK:
        """Load configuration for one role and build an SDK around it."""
        return cls(load_config(config_dir, role), output_dir, signing_secret)

    # ------------------------------------------------------------- services
    @property
    def network_artifacts(self) -> NetworkArtifactService:
        if self._network_artifacts is None:
            self._network_artifacts = NetworkArtifactService(self.config, self.output_dir)
        return self._network_artifacts

    @property
    def match(self) -> MatchService:
        if self._match is None:
            self._match = MatchService(self.config, self.output_dir, self.signing_secret)
        return self._match

    @property
    def verification(self) -> VerificationService:
        if self._verification is None:
            self._verification = VerificationService()
        return self._verification

    @property
    def negotiation(self) -> NegotiationService:
        if self._negotiation is None:
            self._negotiation = NegotiationService(self.config)
        return self._negotiation

    @property
    def reporting(self) -> ReportingService:
        if self._reporting is None:
            self._reporting = ReportingService(self.config)
        return self._reporting

    # ------------------------------------------------------------- identity
    def describe(self) -> dict[str, Any]:
        """Everything an opponent or a grader may reasonably want to know."""
        return {
            "code_version": CODE_VERSION,
            "role": self.config.role,
            "group_id": self.config.group_id,
            "group_name": self.config.group_name,
            "members": self.config.members,
            "repos": self.config.repos,
            "github_commit": git_commit(),
            "config_sha256": self.config.config_sha256(),
            "scent_fingerprint": self.negotiation.scent_fingerprint(),
            "hardware": collect_hardware().as_dict(),
            "config_problems": list(self.config.problems),
        }

    # ---------------------------------------------------------- negotiation
    def handshake(self, mcp_url: str = "") -> Handshake:
        """Our published fingerprints, for the pre-game exchange."""
        return self.negotiation.handshake(mcp_url)

    def agree_with(self, theirs: Handshake | dict[str, Any]) -> Agreement:
        """Compare fingerprints and decide whether the match may start."""
        return self.negotiation.compare(theirs)

    # ---------------------------------------------------------------- match
    def run_series(self, opponent_group: str, sub_games: int | None = None,
                   seed: int = 0) -> SeriesResult:
        """Play a full local series and write all four artifacts."""
        return self.match.run_series(opponent_group, sub_games, seed)

    def record_networked_sub_game(self, game_id: str, sub_game: int, opponent: str,
                                  outcome: Any, started_at: str, ended_at: str,
                                  tokens: int, handshake: dict[str, Any] | None = None,
                                  ) -> list[Path]:
        """Write the artifacts a *live* sub-game produced (rules 20, 32-35, 49).

        The local rehearsal gets its artifacts from ``run_series``. A networked
        match plays one sub-game per process, so it has to hand them over here
        instead -- otherwise a real league game would leave nothing to replay,
        audit or report.

        Built with :meth:`~p2pchase.services.network_artifacts
        .NetworkArtifactService.for_opponent` rather than the cached
        :attr:`network_artifacts` property, which defaults ``counted`` to
        ``False`` because it has no opponent to look one up by.

        That default cost us the opening sub-game of our first counted series.
        We flipped `counted` for imreeyal, announced it, and verified twice that
        the service honoured it -- through ``for_opponent``, which we had wired
        into the *opponent-driven* path. We drive this pairing, and the driver
        came through here. So the counted sub-game was written into the
        friendly tree, on top of a friendly log of the same name, and
        ``refresh_result`` then assembled one counted sub-game with five
        friendly ones into a result that looked untouched because both openers
        happened to be police-survival.

        The quarantine tests were not wrong; they covered the service. Nothing
        covered how the driver built it.
        """
        # `opponent` decides the seal form -- see MatchService.step_zero.
        step_zero = self.match.step_zero(sub_game, opponent=opponent)
        service = NetworkArtifactService.for_opponent(self.config, opponent,
                                                      self.output_dir)
        return service.record_sub_game(
            game_id, sub_game, self.config.role, opponent, outcome,
            started_at, ended_at, tokens, handshake, step_zero)

    # --------------------------------------------------------- verification
    def verify_log(self, path: Path | str) -> AuditVerdict:
        """Verify one disclosed log's commit chain."""
        return self.verification.verify_file(path)

    def audit_opponent(self, paths: list[Path | str]) -> tuple[bool, list[AuditVerdict]]:
        """Audit an opponent's logs after the match (rule 36)."""
        return self.verification.audit_opponent(paths)

    def replay_text(self, path: Path | str, limit: int | None = None) -> str:
        """Human-readable replay report."""
        return self.verification.render(path, limit)

    # ------------------------------------------------------------ reporting
    def send_report(self, result: dict[str, Any], dry_run: bool = True) -> DeliveryReceipt:
        """E-mail one result report through the Gatekeeper."""
        return self.reporting.send_result(result, dry_run=dry_run)

    def gate_status(self) -> dict[str, Any]:
        """Gatekeeper queue health, for monitoring and the GUI status bar."""
        return self.reporting.gatekeeper.get_queue_status().as_dict()
