#!/usr/bin/env python3
"""Lint check for DAG-bypass patterns in card builder files.

Detects `if component_name ==` and `if component_name in` patterns in
card builder source files. These patterns indicate special-case branching
that should ideally go through the NetworkX DAG via get_field_for_child().

Existing occurrences are legitimate special cases (Image URL handling,
Grid columnCount, etc.) that can't easily move to the DAG. This lint
surfaces them as warnings so NEW additions are visible in PR diffs.

Error code: DSL002

Usage:
    python scripts/lint_no_dag_bypass.py
    python scripts/lint_no_dag_bypass.py --verbose

Exit codes:
    0 - Always (warnings only, never blocks)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Files to scan for DAG-bypass patterns
TARGET_FILES: list[str] = [
    "gchat/card_builder/builder_v2.py",
]

# Pattern: `if component_name ==` or `if component_name in`
# Also matches `elif component_name ==` / `elif component_name in`
DAG_BYPASS_RE = re.compile(
    r"\b(?:el)?if\s+component_name\s+(?:==|in\b)"
)


def scan_file(rel_path: Path) -> list[tuple[int, str]]:
    """Scan a file for DAG-bypass patterns.

    Returns list of (line_number, stripped_line).
    """
    abs_path = PROJECT_ROOT / rel_path
    violations: list[tuple[int, str]] = []
    try:
        text = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations

    in_docstring = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # Track triple-quote docstrings (simple toggle — sufficient for
        # single-file linting where we only care about code lines)
        triple_count = stripped.count('"""') + stripped.count("'''")
        if triple_count % 2 == 1:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        # Skip comment lines
        if stripped.startswith("#"):
            continue
        if DAG_BYPASS_RE.search(line):
            violations.append((lineno, stripped))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    targets = [Path(p) for p in TARGET_FILES]
    scannable = [p for p in targets if (PROJECT_ROOT / p).exists()]
    missing = [p for p in targets if p not in scannable]

    if missing:
        for p in missing:
            print(f"WARNING: target file not found: {p}")

    if args.verbose:
        print(f"Scanning {len(scannable)} file(s) for DAG-bypass patterns:")
        for p in scannable:
            print(f"  {p}")

    total = 0
    for rel_path in scannable:
        hits = scan_file(rel_path)
        for lineno, line in hits:
            print(
                f"{rel_path}:{lineno}: DSL002 DAG-bypass pattern: {line}"
            )
            total += 1

    if total:
        print(f"\n{total} DAG-bypass pattern(s) found (warning only).")
    elif args.verbose:
        print("No DAG-bypass patterns found.")

    # Always exit 0 — this lint is advisory, not blocking
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
