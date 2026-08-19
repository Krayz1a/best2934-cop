"""One commit stamped across a two-process series names the wrong code.

anrbj666 found this on our T5 friendly report: all six rows carried the cop
head, but g1/g3/g5 were played by the thief process at a different commit,
which their own per-window negotiate records held. Outside the signed
consensus scope so nothing voided -- but the document goes to the lecturer
under our name and answers "which code played this" wrongly in half its rows.
"""

from __future__ import annotations

from p2pchase.domain.scoring import build_score_table
from p2pchase.reports.series_assembly import assemble_series, commit_for

COP = "f3cefdb43ff70dffbddcbed8f930bea46f74919a"
THIEF = "fa7a8de3c1cfeaaf5cf93480a22bccef1b041672"


def _log(number: int, role: str, commit: str = "") -> dict:
    summary = {"sub_game_number": number, "role": role, "result": "survival",
               "winner_role": role, "steps": 35, "tokens_total": 0}
    if commit:
        summary["github_commit"] = commit
    return {"_filename": f"log_a-vs-b_g{number:02d}.json", "summary": summary}


def _series(**kwargs) -> list:
    logs = [_log(n, "thief" if n % 2 else "police", **kwargs) for n in (1, 2)]
    return logs


def test_each_row_carries_the_commit_its_own_log_recorded():
    logs = [_log(1, "thief", THIEF), _log(2, "police", COP)]
    outcomes, _final, _tokens = assemble_series(logs, "best2934", "anrbj666",
                                                build_score_table({}))
    assert [o.github_commit["best2934"] for o in outcomes] == [THIEF, COP]


def test_two_roles_never_collapse_onto_one_commit():
    """The exact defect: same value in both rows is the bug, not the fix."""
    logs = [_log(1, "thief", THIEF), _log(2, "police", COP)]
    outcomes, _final, _tokens = assemble_series(logs, "best2934", "anrbj666",
                                                build_score_table({}))
    recorded = {o.github_commit["best2934"] for o in outcomes}
    assert len(recorded) == 2, f"both rows collapsed onto {recorded}"


def test_a_role_mapping_answers_for_logs_written_before_the_field_existed():
    logs = [_log(1, "thief"), _log(2, "police")]
    outcomes, _final, _tokens = assemble_series(
        logs, "best2934", "anrbj666", build_score_table({}),
        {"thief": THIEF, "police": COP})
    assert [o.github_commit["best2934"] for o in outcomes] == [THIEF, COP]


def test_the_logs_own_value_beats_the_callers_mapping():
    """The process that played it knows better than the rebuild does."""
    assert commit_for({"role": "thief", "github_commit": THIEF},
                      {"thief": "stale", "police": "stale"}) == THIEF


def test_a_bare_string_still_works_for_a_single_role_series():
    assert commit_for({"role": "police"}, COP) == COP
