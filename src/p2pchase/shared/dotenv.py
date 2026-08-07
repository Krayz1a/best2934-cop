"""Read ``.env`` into the process environment, once, at entry.

Nothing else in the codebase reads that file: config loading and
:mod:`p2pchase.infra.gmail_sender` both go straight to ``os.environ``
(guidelines §7.4 -- secrets come from the environment, never from a config
file). That is the right rule, but it leaves a gap, because the operator who
wrote the secret into ``.env`` did not also export it into their shell. The
symptom is silent in both places it matters:

* ``P2PCHASE_SIGNING_SECRET`` absent -- ``declaration.py`` falls back to an
  unkeyed digest and the step-0 declaration goes out *unsigned* (rule 24).
* ``P2PCHASE_GMAIL_CREDENTIALS`` absent -- the OAuth client is looked for at
  the relative default ``credentials.json``, which is deliberately not there,
  and the consent flow refuses with a message about a file the operator
  already has.

The real environment always wins, so an exported value is never overridden by
a stale file, and a value already set is never re-read.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import paths

ENV_FILENAME = ".env"


def parse(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines, ignoring blanks and ``#`` comments.

    Deliberately not a general dotenv implementation: no ``export`` prefix, no
    interpolation, no multi-line values. Everything this project puts in the
    file is a single flat token, and a parser that quietly accepts more than
    the format it documents is a parser that disagrees with the shell.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        name, _, value = entry.partition("=")
        name = name.strip()
        if name:
            values[name] = value.strip().strip('"').strip("'")
    return values


def environment(root: Path | None = None,
                base: dict[str, str] | None = None) -> dict[str, str]:
    """The given environment, plus anything ``.env`` defines that it lacks."""
    merged = dict(os.environ if base is None else base)
    source = (paths.project_root() if root is None else Path(root)) / ENV_FILENAME
    if not source.exists():
        return merged
    for name, value in parse(source.read_text(encoding="utf-8")).items():
        merged.setdefault(name, value)
    return merged


def load(root: Path | None = None) -> list[str]:
    """Apply ``.env`` to ``os.environ`` and return the names it filled in.

    Returns the names, not the values: callers want to *log* what was loaded,
    and these are secrets. ``P2PCHASE_SIGNING_SECRET`` in a terminal scrollback
    is the failure this file exists to help avoid, not one to add.
    """
    resolved = environment(root)
    filled = sorted(name for name in resolved if name not in os.environ)
    for name in filled:
        os.environ[name] = resolved[name]
    return filled
