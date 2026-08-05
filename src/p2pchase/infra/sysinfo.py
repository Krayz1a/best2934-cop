"""Step-0 hardware declaration and computational fairness (book ch5.5).

A contest between agents raises a fairness question: should a laptop compete on
equal terms with a workstation running a heavy local model? The league answers
by normalising scores -- rewarding algorithmic efficiency over raw hardware --
which only works if every team declares its machine honestly, before play.

So before the first move each peer collects its OS, CPU, RAM and GPU, together
with the code version, group name, sub-game number and the exact GitHub commit
being played (rule 53), packs it into canonical JSON, and signs it. Signing
before the match is what stops a team retroactively claiming weaker hardware to
farm the fairness bonus (rule 24 -- failure forfeits eligibility for it).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Any

from .. import constants
from ..domain.crypto import sign_declaration


@dataclass
class HardwareSpec:
    os: str
    cpu_type: str
    cpu_cores: int
    cpu_freq_mhz: int
    ram_gb: float
    gpu_type: str
    gpu_cores_or_cuda: str
    vram_gb: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cpu_name() -> str:
    """Human-readable CPU model, best effort across platforms."""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def _gpu() -> tuple[str, str, float]:
    """(name, core/CUDA note, VRAM GiB). Reports honestly when there is none."""
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout.strip().splitlines()
            if out:
                name, vram = (part.strip() for part in out[0].split(","))
                return name, "CUDA (core count not exposed by driver)", round(int(vram) / 1024, 1)
        except (subprocess.SubprocessError, ValueError):
            pass
    return "none (CPU only)", "n/a", 0.0


def collect_hardware() -> HardwareSpec:
    cpu_freq = 0
    ram_gb = 0.0
    try:
        import psutil

        freq = psutil.cpu_freq()
        cpu_freq = int(freq.max or freq.current) if freq else 0
        ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        try:
            ram_gb = round(
                os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3), 1
            )
        except (ValueError, OSError):
            ram_gb = 0.0

    gpu_name, gpu_cores, vram = _gpu()
    return HardwareSpec(
        os=f"{platform.system()} {platform.release()}",
        cpu_type=_cpu_name(),
        cpu_cores=os.cpu_count() or 1,
        cpu_freq_mhz=cpu_freq,
        ram_gb=ram_gb,
        gpu_type=gpu_name,
        gpu_cores_or_cuda=gpu_cores,
        vram_gb=vram,
    )


def git_commit(repo_dir: str | None = None) -> str:
    """The exact commit being played this match.

    Rule 53: code may change between matches, but every match must record the
    commit that actually played, so the grader can reproduce that version. A
    dirty tree is flagged rather than silently reported as clean.
    """
    try:
        args = ["git", "rev-parse", "HEAD"]
        head = subprocess.run(
            args, cwd=repo_dir, capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir, capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        return f"{head}-dirty" if dirty else head
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def build_step0(
    group_name: str,
    sub_game_number: int,
    llm_model: str,
    signing_secret: str,
    repo_dir: str | None = None,
    role: str = "",
    group_id: str = "",
) -> dict[str, Any]:
    """The signed Step-0 record, written as step 0 of the match log.

    ``role`` and ``group_id`` ride inside the signed payload rather than beside
    it, because the role is the one field an opponent may want to argue about
    afterwards. Both peers derive the assignment from the same rule
    (:mod:`p2pchase.domain.roles`), so a signed, committed declaration of which
    side we believed we were playing turns a post-hoc dispute into a lookup.
    They default to empty for the callers that build a declaration outside a
    sub-game, where there is no role to state.
    """
    payload = {
        "step": 0,
        "type": "system_spec",
        "spec": collect_hardware().as_dict(),
        "model": llm_model,
        "code_version": constants.CODE_VERSION,
        "group_name": group_name,
        "group_id": group_id or group_name,
        "role": role,
        "sub_game_number": sub_game_number,
        "github_commit": git_commit(repo_dir),
    }
    payload["signature"] = sign_declaration(payload, signing_secret)
    return payload
