"""Make ``python -m p2pchase`` equivalent to the ``p2pchase`` console script.

The console script is what the README documents and what a human should type.
This exists for the case where a *program* launches the CLI -- notably
``tools/rehearsal.py``, which spawns four processes and must be certain they run
in this interpreter's environment rather than whichever ``p2pchase`` happens to
be first on PATH.
"""

from __future__ import annotations

from .cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
