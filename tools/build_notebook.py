"""Generate ``notebooks/analysis.ipynb`` from ``notebooks/analysis.py``.

The analysis lives in a plain ``.py`` file so it can be linted, executed in CI
and reviewed in a diff. A notebook is the required deliverable, so this script
converts one into the other rather than keeping two copies in sync by hand.

Cell markers, matching the widely-used percent format:

    # %%              -> a code cell
    # %% [markdown]   -> a markdown cell (leading "# " stripped from each line)

    uv run python tools/build_notebook.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "notebooks" / "analysis.py"
TARGET = ROOT / "notebooks" / "analysis.ipynb"


def _strip_markdown(lines: list[str]) -> list[str]:
    """Turn ``# prose`` comment lines back into plain markdown."""
    out = []
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("# "):
            out.append(stripped[2:])
        elif stripped == "#":
            out.append("")
        else:
            out.append(stripped)
    return out


def _cell(kind: str, lines: list[str]) -> dict | None:
    """Build one notebook cell, or None if it holds nothing but blank lines."""
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return None

    if kind == "markdown":
        body = _strip_markdown(lines)
        return {"cell_type": "markdown", "metadata": {},
                "source": [f"{line}\n" for line in body[:-1]] + [body[-1]]}
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [],
            "source": [f"{line}\n" for line in lines[:-1]] + [lines[-1]]}


def split_cells(text: str) -> list[dict]:
    """Split percent-format source into notebook cells."""
    cells: list[dict] = []
    kind = "code"
    buffer: list[str] = []

    for raw in text.splitlines():
        if raw.startswith("# %%"):
            cell = _cell(kind, buffer)
            if cell is not None:
                cells.append(cell)
            buffer = []
            kind = "markdown" if "[markdown]" in raw else "code"
            continue
        buffer.append(raw)

    cell = _cell(kind, buffer)
    if cell is not None:
        cells.append(cell)
    return cells


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    # Drop the module docstring: it explains the .py file, not the notebook.
    body = text.split('"""', 2)[-1] if text.startswith('"""') else text

    notebook = {
        "cells": split_cells(body),
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    TARGET.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    counts = {"code": 0, "markdown": 0}
    for cell in notebook["cells"]:
        counts[cell["cell_type"]] += 1
    print(f"{TARGET.relative_to(ROOT)}: {counts['code']} code cells, "
          f"{counts['markdown']} markdown cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
