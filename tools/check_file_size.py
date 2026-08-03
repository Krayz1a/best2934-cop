"""Automated enforcement of the 150-line rule (guidelines §3.2, Table 5).

The rule counts *code* lines: blank lines and comment lines do not count, and
neither do docstrings, which are documentation rather than logic. Counting them
would punish exactly the behaviour the guidelines ask for elsewhere -- detailed
docstrings on every function, class and module.

Run as part of the quality gate:

    uv run python tools/check_file_size.py src tests

Exits non-zero and names every offending file, so a single run reports all
violations instead of one per invocation.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

LIMIT = 150


def docstring_lines(tree: ast.AST) -> set[int]:
    """Line numbers occupied by module, class and function docstrings."""
    lines: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def count_code_lines(path: Path) -> int:
    """Code lines in one file, excluding blanks, comments and docstrings."""
    source = path.read_text(encoding="utf-8")
    skip = docstring_lines(ast.parse(source))
    return sum(
        1
        for number, line in enumerate(source.splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#") and number not in skip
    )


def scan(roots: list[str]) -> list[tuple[int, Path]]:
    """Every Python file under ``roots``, largest first."""
    found: list[tuple[int, Path]] = []
    for root in roots:
        for path in sorted(Path(root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            found.append((count_code_lines(path), path))
    return sorted(found, reverse=True)


def main(argv: list[str]) -> int:
    roots = argv[1:] or ["src", "tests"]
    results = scan(roots)
    if not results:
        print(f"no Python files found under {', '.join(roots)}")
        return 1

    violations = [(n, p) for n, p in results if n > LIMIT]
    for count, path in violations:
        print(f"FAIL  {count:>4} lines (limit {LIMIT})  {path}")

    largest = results[0]
    print(
        f"\n{len(results)} files scanned, {len(violations)} over the {LIMIT}-line limit. "
        f"Largest: {largest[1]} at {largest[0]} lines."
    )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
