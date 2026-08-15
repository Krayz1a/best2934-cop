"""Find documentation claims the tree cannot back up.

Three cheap, mechanical checks over every markdown file in a repo:

  1. every `p2pchase <subcommand>` named in prose is a real CLI subcommand;
  2. every `src/...py`, `tests/...py`, `docs/...md` path named is a real file;
  3. every `module/file.py` shorthand resolves under src/p2pchase/.

This class of error has bitten three times: a runbook naming `p2pchase
refresh-result` (never existed), COMPLIANCE.md marking rule 32 Met while the
send was operator-armed, and a summary count that drifted from its own table.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def cli_subcommands(repo: Path) -> set[str]:
    out = subprocess.run([str(repo / ".venv/bin/p2pchase"), "--help"],
                         capture_output=True, text=True, timeout=60).stdout
    match = re.search(r"\{([a-z0-9,\-]+)\}", out)
    return set(match.group(1).split(",")) if match else set()


def check(repo: Path) -> list[str]:
    problems: list[str] = []
    subs = cli_subcommands(repo)
    if not subs:
        return [f"{repo.name}: could not read CLI subcommands"]

    for md in sorted(repo.rglob("*.md")):
        if any(p in md.parts for p in (".venv", "node_modules", "results", "artifacts")):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        rel = md.relative_to(repo)

        for cmd in sorted(set(re.findall(r"p2pchase\s+([a-z][a-z0-9\-]{2,})", text))):
            if cmd not in subs and cmd not in {"play", "serve"}:
                problems.append(f"{rel}: names `p2pchase {cmd}` which is not a subcommand")

        for path in sorted(set(re.findall(r"`((?:src|tests|docs|tools|config)/[\w./\-]+)`", text))):
            # Require a file extension: `tools/list` is an MCP method name, not
            # a path, and a checker that cries wolf gets ignored -- which would
            # cost more than the class of bug it is meant to catch.
            if "." not in path.rsplit("/", 1)[-1]:
                continue
            if not (repo / path).exists():
                problems.append(f"{rel}: references missing path {path}")

        for mod in sorted(set(re.findall(r"`(\w+/\w+\.py)`", text))):
            if (repo / mod).exists() or (repo / "src/p2pchase" / mod).exists():
                continue
            problems.append(f"{rel}: references missing module {mod}")

    return problems


if __name__ == "__main__":
    total = 0
    # Defaults to the repository this script lives in, so it can be run as
    # `python tools/doccheck.py` from the repo root with no arguments.
    targets = sys.argv[1:] or [str(Path(__file__).resolve().parent.parent)]
    for name in targets:
        repo = Path(name)
        found = check(repo)
        total += len(found)
        print(f"=== {repo.name}: {len(found)} problem(s) ===")
        for line in found:
            print("  " + line)
    sys.exit(1 if total else 0)
