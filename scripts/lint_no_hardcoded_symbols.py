#!/usr/bin/env python3
"""Lint check for hardcoded DSL symbols in module wrapper consumers.

Scans files that use the adapters/module_wrapper system for Unicode
characters from the DSL symbol pools (LETTER_SYMBOLS, FALLBACK_SYMBOLS).
These files should obtain symbols dynamically from the wrapper, never
hardcode them.

Usage:
    python scripts/lint_no_hardcoded_symbols.py
    python scripts/lint_no_hardcoded_symbols.py --verbose

Exit codes:
    0 - No violations found
    1 - Violations found
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve project root (parent of scripts/)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.module_wrapper.symbol_generator import (  # noqa: E402
    FALLBACK_SYMBOLS,
    LETTER_SYMBOLS,
)

# ---------------------------------------------------------------------------
# Build banned-character set + reverse lookup from the SSoT
# ---------------------------------------------------------------------------

# char -> list of letter labels (e.g. 'ρ' appears under both R and P)
_CHAR_TO_LETTERS: dict[str, list[str]] = {}
for _letter, _syms in LETTER_SYMBOLS.items():
    for _sym in _syms:
        _CHAR_TO_LETTERS.setdefault(_sym, []).append(_letter)
for _sym in FALLBACK_SYMBOLS:
    _CHAR_TO_LETTERS.setdefault(_sym, []).append("FALLBACK")

BANNED_CHARS: set[str] = set(_CHAR_TO_LETTERS.keys())

# Symbols with common non-DSL uses that should not trigger violations.
EXCLUDED_SYMBOLS: set[str] = {
    "©",  # copyright notices in license headers
}

BANNED_CHARS -= EXCLUDED_SYMBOLS

# ---------------------------------------------------------------------------
# Target files — module wrapper consumers / facades
#
# These files use the adapter/module_wrapper system and should get symbols
# dynamically, never hardcode them.  Add new wrapper facades here.
# ---------------------------------------------------------------------------
TARGET_FILES: list[str] = [
    "gchat/card_framework_wrapper.py",
    "middleware/qdrant_core/qdrant_models_wrapper.py",
]


def _label_for_char(char: str) -> str:
    """Return a human-readable label for a banned character."""
    letters = _CHAR_TO_LETTERS.get(char, ["?"])
    return "/".join(letters)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def scan_file(rel_path: Path) -> list[tuple[int, int, str, str]]:
    """Scan a single file for banned characters.

    Returns list of (line_number, column, char, label).
    """
    abs_path = PROJECT_ROOT / rel_path
    violations: list[tuple[int, int, str, str]] = []
    try:
        text = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations

    for lineno, line in enumerate(text.splitlines(), start=1):
        for col, ch in enumerate(line, start=1):
            if ch in BANNED_CHARS:
                violations.append((lineno, col, ch, _label_for_char(ch)))
    return violations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true", help="Show scanned file list")
    args = parser.parse_args()

    targets = [Path(p) for p in TARGET_FILES]
    missing = [p for p in targets if not (PROJECT_ROOT / p).exists()]
    if missing:
        for p in missing:
            print(f"WARNING: target file not found: {p}")

    scannable = [p for p in targets if (PROJECT_ROOT / p).exists()]

    if args.verbose:
        print(f"Scanning {len(scannable)} target file(s):")
        for p in scannable:
            print(f"  {p}")

    total_violations = 0
    for rel_path in scannable:
        hits = scan_file(rel_path)
        for lineno, col, char, label in hits:
            print(
                f"{rel_path}:{lineno}:{col}: DSL001 Hardcoded DSL symbol "
                f"'{char}' ({label}_LETTER) found "
                f"— use dynamic symbol lookup instead"
            )
            total_violations += 1

    if total_violations:
        print(f"\nFound {total_violations} violation(s).")
        return 1

    if args.verbose:
        print("No hardcoded DSL symbols found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
