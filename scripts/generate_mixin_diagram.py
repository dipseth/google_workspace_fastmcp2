#!/usr/bin/env python3
"""
Generate Mermaid dependency diagram for ModuleWrapper mixins.

Usage:
    python scripts/generate_mixin_diagram.py          # Print to stdout
    python scripts/generate_mixin_diagram.py --table   # Print markdown table
    python scripts/generate_mixin_diagram.py --all     # Print both
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from adapters.module_wrapper import ModuleWrapper
from adapters.module_wrapper.mixin_meta import (
    generate_mermaid_dependency_graph,
    generate_provides_requires_table,
    validate_mixin_dependencies,
)


def main():
    parser = argparse.ArgumentParser(
        description="Generate ModuleWrapper mixin dependency diagrams"
    )
    parser.add_argument(
        "--table", action="store_true", help="Print markdown table instead of Mermaid"
    )
    parser.add_argument(
        "--all", action="store_true", help="Print both Mermaid and table"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Run dependency validation"
    )
    args = parser.parse_args()

    if args.validate or args.all:
        issues = validate_mixin_dependencies(ModuleWrapper)
        if issues:
            print("## Dependency Issues\n")
            for issue in issues:
                print(f"  - {issue}")
            print()
        else:
            print("## Dependency Validation: PASSED\n")

    if args.table or args.all:
        print("## Mixin Contracts\n")
        print(generate_provides_requires_table(ModuleWrapper))
        print()

    if not args.table or args.all:
        print("## Dependency Graph\n")
        print("```mermaid")
        print(generate_mermaid_dependency_graph(ModuleWrapper))
        print("```")


if __name__ == "__main__":
    main()
