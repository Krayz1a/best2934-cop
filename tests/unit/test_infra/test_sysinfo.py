"""The Step-0 hardware declaration (rule 24, rule 53).

The fairness bonus is only meaningful if the declaration is honest and made
before play. That makes two properties worth pinning: the declaration must be
*complete* (a blank field is an undeclared advantage), and its signature must
change when its contents change, so a machine cannot be revised afterwards.

None of this may crash on a machine without a GPU, without ``git``, or without
``psutil`` -- a grader's environment is not ours, and a declaration that raises
takes the whole match with it.
"""

from __future__ import annotations

from p2pchase.infra.sysinfo import (
    HardwareSpec,
    build_step0,
    collect_hardware,
    git_commit,
)


def test_the_declaration_names_every_field_the_league_asks_for():
    spec = collect_hardware()
    assert isinstance(spec, HardwareSpec)
    declared = spec.as_dict()
    assert set(declared) == {
        "os", "cpu_type", "cpu_cores", "cpu_freq_mhz",
        "ram_gb", "gpu_type", "gpu_cores_or_cuda", "vram_gb",
    }
    assert declared["cpu_cores"] >= 1
    assert declared["os"].strip()
    assert declared["cpu_type"].strip()


def test_absent_hardware_is_declared_rather_than_omitted():
    """A machine with no GPU must say so. Silence reads as a hidden advantage."""
    spec = collect_hardware()
    assert spec.gpu_type.strip()
    assert spec.vram_gb >= 0.0


def test_a_missing_repository_reports_unknown_instead_of_raising(tmp_path):
    assert git_commit(str(tmp_path)) in ("unknown", "")


def test_step_zero_carries_the_identity_the_grader_reproduces_from():
    payload = build_step0("best2934", 1, "template", "secret")
    assert payload["step"] == 0
    assert payload["type"] == "system_spec"
    assert payload["group_name"] == "best2934"
    assert payload["sub_game_number"] == 1
    assert payload["model"] == "template"
    assert payload["github_commit"]  # rule 53: the commit that actually played
    assert payload["signature"]


def test_the_same_declaration_signs_identically():
    """Determinism is what makes the signature checkable at all."""
    a = build_step0("best2934", 1, "template", "secret")
    b = build_step0("best2934", 1, "template", "secret")
    assert a["signature"] == b["signature"]


def test_editing_a_declaration_invalidates_its_signature():
    """Retroactively claiming weaker hardware has to be visible (rule 24)."""
    honest = build_step0("best2934", 1, "template", "secret")
    tampered = dict(honest)
    tampered["spec"] = dict(honest["spec"], cpu_cores=1, ram_gb=1.0)

    from p2pchase.domain.crypto import sign_declaration

    recomputed = sign_declaration(
        {k: v for k, v in tampered.items() if k != "signature"}, "secret"
    )
    assert recomputed != honest["signature"]


def test_a_different_secret_produces_a_different_signature():
    assert (build_step0("g", 1, "m", "one")["signature"]
            != build_step0("g", 1, "m", "two")["signature"])
