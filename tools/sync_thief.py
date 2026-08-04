"""Re-derive the sibling `best2934-thief` repository from this one.

Rule 41 asks for one repository per role. The engine is symmetric, so the thief
repository is this one with `DEFAULT_ROLE` flipped, a README written from the
thief's side, and the project name in the doc headers changed. Keeping that
derivation in a script rather than in someone's memory is the point: a fix made
here reaches the thief repository by running this, and the two cannot silently
drift apart between now and the deadline.

Nothing is pushed and nothing is committed -- it writes the working tree and
prints what changed, leaving the commit to a human who can read the diff.

    uv run python tools/sync_thief.py [--target ../best2934-thief]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Never copied: git metadata, virtualenvs, caches and generated coverage HTML.
SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "coverage"}

CONSTANTS = "src/p2pchase/constants.py"
ROLE_LINE_COP = "DEFAULT_ROLE: Final[str] = ROLE_COP"
ROLE_LINE_THIEF = "DEFAULT_ROLE: Final[str] = ROLE_THIEF"

README_SUBS = [
    ("# best2934 — Cops and Robbers over a peer-to-peer network",
     "# best2934 — Cops and Robbers over a peer-to-peer network (thief)"),
    ("| Cop repository | https://github.com/Krayz1a/best2934-cop |\n"
     "| Thief repository | https://github.com/Krayz1a/best2934-thief |",
     "| Thief repository | https://github.com/Krayz1a/best2934-thief **(you are here)** |\n"
     "| Cop repository | https://github.com/Krayz1a/best2934-cop |"),
    ("git clone https://github.com/Krayz1a/best2934-cop.git\ncd best2934-cop",
     "git clone https://github.com/Krayz1a/best2934-thief.git\ncd best2934-thief"),
    ("### 1.1 Two repositories, one engine",
     "### 1.1 Why this repository looks identical to the cop's"),
    ("[`best2934-thief`](https://github.com/Krayz1a/best2934-thief) differs\nfrom this repository in a single line:",
     "This repository differs from\n[`best2934-cop`](https://github.com/Krayz1a/best2934-cop) in a single line:"),
    ("plus its README and the tuning in `config/thief/setup.json`",
     "plus this README and the tuning in `config/thief/setup.json`"),
    ("DEFAULT_ROLE: Final[str] = ROLE_COP       # ROLE_THIEF in best2934-thief",
     "DEFAULT_ROLE: Final[str] = ROLE_THIEF     # ROLE_COP in best2934-cop"),
    ("Running the thief from this checkout is one flag:\n\n```bash\n"
     "uv run p2pchase play --role thief --game-id best2934-vs-rival42\n```",
     "Running the cop from this checkout is one flag:\n\n```bash\n"
     "uv run p2pchase play --role police --game-id best2934-vs-rival42\n```"),
    ("**Companion repository:** the thief agent lives at\n"
     "[Krayz1a/best2934-thief](https://github.com/Krayz1a/best2934-thief) and shares\n"
     "this engine.",
     "**Companion repository:** the cop agent lives at\n"
     "[Krayz1a/best2934-cop](https://github.com/Krayz1a/best2934-cop) and shares this\n"
     "engine — see §1.1."),
    ("1. [What this is](#1-what-this-is) · [Two repositories, one engine](#11-two-repositories-one-engine)",
     "1. [What this is](#1-what-this-is) · "
     "[Why it looks identical to the cop's](#11-why-this-repository-looks-identical-to-the-cops)"),
]


def _copy(target: Path) -> None:
    """Mirror the working tree, leaving the target's .git alone."""
    for path in REPO.iterdir():
        if path.name in SKIP:
            continue
        destination = target / path.name
        if path.is_dir():
            shutil.rmtree(destination, ignore_errors=True)
            shutil.copytree(path, destination,
                            ignore=shutil.ignore_patterns(*SKIP))
        else:
            shutil.copy2(path, destination)


def _apply(path: Path, subs: list[tuple[str, str]], required: bool = True) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in subs:
        if old not in text:
            if required:
                sys.exit(f"sync aborted: expected text not found in {path.name}:\n  {old[:70]}")
            continue
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def sync(target: Path) -> None:
    """Copy this repository over ``target`` and re-apply the thief's differences."""
    if not (target / ".git").exists():
        sys.exit(f"{target} is not a git repository -- refusing to overwrite it")
    _copy(target)

    _apply(target / CONSTANTS, [(ROLE_LINE_COP, ROLE_LINE_THIEF)])
    _apply(target / "README.md", README_SUBS)
    _apply(target / "README.md", [("--role police", "--role thief")], required=False)
    # The one place the swap must NOT apply: the example that runs the *cop*
    # from the thief checkout, restored after the blanket substitution above.
    _apply(target / "README.md",
           [("uv run p2pchase play --role thief --game-id best2934-vs-rival42\n```\n\n---",
             "uv run p2pchase play --role police --game-id best2934-vs-rival42\n```\n\n---")],
           required=False)

    for name in ("PROMPTS.md", "TODO.md", "PLAN.md"):
        _apply(target / "docs" / name,
               [("**Project** `best2934-cop`",
                 "**Project** `best2934-thief` (same engine as `best2934-cop`)")],
               required=False)
    _apply(target / "docs" / "PRD.md",
           [("**Project** `best2934-cop` (paired with `best2934-thief`)",
             "**Project** `best2934-thief` (paired with `best2934-cop`)")], required=False)
    _apply(target / "docs" / "COMPLIANCE.md",
           [("**Project** `best2934-cop`", "**Project** `best2934-thief`")], required=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", default=str(REPO.parent / "best2934-thief"),
                        help="path to the thief repository (default: ../best2934-thief)")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    sync(target)
    print(f"synced {REPO.name} -> {target}")
    status = subprocess.run(["git", "-C", str(target), "status", "--short"],
                            capture_output=True, text=True, check=False)
    print(status.stdout or "  (no changes)")
    print("review the diff, run the gates in the target, then commit there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
