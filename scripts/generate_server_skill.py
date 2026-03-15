#!/usr/bin/env python3
"""Generate the server-level google-workspace-mcp SKILL.md.

Initializes the card and email wrappers, reads their live symbol maps, and
writes ~/.claude/skills/google-workspace-mcp/SKILL.md (or --output-dir).

Usage:
    python scripts/generate_server_skill.py
    python scripts/generate_server_skill.py --output-dir /tmp/skills
    python scripts/generate_server_skill.py --verify

Exit codes:
    0 - Success (and lint clean if --verify)
    1 - Generation or lint failure
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / ".claude" / "skills",
        help="Output directory (default: ~/.claude/skills)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run lint_no_hardcoded_symbols check on the generator after writing",
    )
    args = parser.parse_args()

    try:
        from gchat.wrapper_setup import get_card_framework_wrapper
        from gmail.email_wrapper_setup import get_email_wrapper
        from skills.server_skill_generator import write_server_skill

        card_wrapper = get_card_framework_wrapper()
        email_wrapper = get_email_wrapper()
        skill_dir = write_server_skill(
            Path(args.output_dir).expanduser(), card_wrapper, email_wrapper
        )
        print(f"Generated: {skill_dir / 'SKILL.md'}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.verify:
        scripts_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(scripts_dir))
        from lint_no_hardcoded_symbols import scan_file  # noqa: PLC0415

        rel = Path("skills/server_skill_generator.py")
        hits = scan_file(rel)
        if hits:
            for lineno, col, char, label in hits:
                print(
                    f"{rel}:{lineno}:{col}: DSL001 Hardcoded symbol '{char}' ({label})"
                )
            return 1
        print("Lint check passed: no hardcoded symbols in generator.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
