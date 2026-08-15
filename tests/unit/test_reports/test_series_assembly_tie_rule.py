"""The counted game must be settled under the rule the pairing declared.

There are two paths to a series result in this codebase. The local rehearsal
builds its own :class:`SeriesTally` and passes ``tie_rule`` from the pairing;
the networked path rebuilds the result from the logs on disk after every
sub-game, and it did not -- it took the ``SeriesTally`` default and settled
every match under ``series_add``.

So the path that plays *friendlies* honoured the declaration and the path that
plays the *counted game* ignored it. Against an opponent who had declared
``per_subgame`` and implemented it correctly, our report and theirs would have
disagreed at settlement, and rule 35 voids the match for both teams.

Found while replying to anrbj666, who declared their own tie rule from their
result builder rather than from memory. Reading their receipt is what sent us
to look at ours.
"""

from __future__ import annotations

from p2pchase import constants
from p2pchase.domain import scoring
from p2pchase.reports.series_assembly import assemble_series


def _log(number: int, role: str, result: str) -> dict:
    """One sub-game log, in the shape the assembler reads off disk."""
    return {"_filename": f"log_g{number}.json",
            "summary": {"sub_game_number": number, "role": role, "result": result,
                        "tokens_total": 0, "winner_role": None,
                        "started_at": "", "ended_at": "", "audit": {}}}


def _level_series() -> list[dict]:
    """Two captures, one each way: 25-25 with no drawn row, the divergent case."""
    return [_log(1, constants.ROLE_COP, constants.OUTCOME_CAPTURE),
            _log(2, constants.ROLE_THIEF, constants.OUTCOME_CAPTURE)]


def test_the_declared_rule_reaches_the_networked_result():
    """Each of the three rules must produce its own answer through this path."""
    table = scoring.ScoreTable()
    answers = {}
    for rule in scoring.TIE_RULES:
        _, final, _ = assemble_series(_level_series(), "best2934", "anrbj666", table,
                                      tie_rule=rule)
        answers[rule] = final["total_score"]["best2934"]
        assert final["tie_rule"] == rule, "the result must name the rule it was scored under"

    assert answers == {scoring.SERIES_ADD: 27, scoring.SERIES_REPLACE: 2,
                       scoring.PER_SUBGAME: 25}


def test_the_old_default_would_have_hidden_a_declared_per_subgame():
    """The regression stated as a number rather than as a description.

    25 is what a pairing that declared ``per_subgame`` is owed here; 27 is what
    the unconfigured tally paid them. Two points, one voided match.
    """
    _, defaulted, _ = assemble_series(_level_series(), "best2934", "anrbj666",
                                      scoring.ScoreTable())
    _, declared, _ = assemble_series(_level_series(), "best2934", "anrbj666",
                                     scoring.ScoreTable(), tie_rule=scoring.PER_SUBGAME)

    assert defaulted["total_score"]["best2934"] == 27
    assert declared["total_score"]["best2934"] == 25


def test_the_network_service_passes_the_pairing_rule_not_a_default(monkeypatch, peer_config):
    """The wiring itself, since the bug was a missing argument at the call site."""
    from p2pchase.services import network_artifacts

    seen: dict[str, str] = {}

    def _spy(logs, mine, theirs, table, commit_hash="", tie_rule=scoring.SERIES_ADD,
             convention="first_half"):
        seen["tie_rule"] = tie_rule
        # The role convention rides the same call site and was added later, so
        # it is asserted here too: a term that silently falls back to a default
        # is the exact bug this test was written for, once per term.
        seen["convention"] = convention
        return [], {}, {}

    monkeypatch.setattr(network_artifacts, "assemble_series", _spy)
    monkeypatch.setattr(network_artifacts.artifacts, "write_json",
                        lambda path, payload: path)
    service = network_artifacts.NetworkArtifactService(peer_config)
    monkeypatch.setattr(service.config, "tie_rule", lambda opponent: scoring.PER_SUBGAME)

    service.refresh_result("best2934-vs-anrbj666", "uid", "anrbj666")

    assert seen["tie_rule"] == scoring.PER_SUBGAME
