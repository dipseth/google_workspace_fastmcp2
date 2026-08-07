#!/usr/bin/env python3
"""Lint check for MCP tool description quality.

Enforces the Glama-audit remediation playbook on a maintained list of tools:
every enforced description must carry a "Use when:" routing line, stay under
a length cap, and avoid marketing adjectives in place of mechanics. Tools not
yet on the enforced list produce warnings only, so coverage can grow without
breaking CI.

Checks both the full tool catalog (what ``get_schema``/``execute`` expose)
and the seven Code Mode meta-tools (what Glama introspects as of 2.5.0).

Usage:
    python scripts/lint_tool_descriptions.py
    python scripts/lint_tool_descriptions.py --verbose

Exit codes:
    0 - No violations found
    1 - Violations found
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Tools whose descriptions follow the playbook and must not regress.
# Add tools here as their descriptions get the playbook treatment.
ENFORCED_TOOLS: set[str] = {
    # Code Mode meta-tools (the front door since 2.5.0)
    "execute",
    "search",
    "tags",
    "get_schema",
    "semantic_search",
    "fetch_document",
    "tool_activity",
    # Photos
    "photos_smart_search",
    "photos_optimized_album_sync",
    "upload_photos",
    "upload_folder_photos",
    "search_photos",
    "list_album_photos",
    # Docs
    "search_docs",
    "get_doc_content",
    "list_docs_in_folder",
    # Drive
    "search_drive_files",
    "get_drive_file_content",
    # Chat
    "manage_space",
    "send_message",
    "send_dynamic_card",
    # Gmail
    "compose_dynamic_email",
    # System
    "manage_credentials",
    "health_check",
}

# Adjectives the audit flagged as replacing mechanics with marketing.
BANNED_ADJECTIVES = re.compile(
    r"\b(smart|optimized|advanced|powerful)\b", re.IGNORECASE
)

# Description length cap (characters). Tools exempted below legitimately
# carry reference material (sandbox helper list, dynamic DSL symbol table).
MAX_DESCRIPTION_CHARS = 1500
LENGTH_EXEMPT: set[str] = {"execute", "semantic_search"}


def _collect_tools() -> dict[str, str]:
    """Return {tool_name: description} for catalog tools + meta-tools."""
    from fastmcp.tools import Tool

    import server
    from tools.code_mode import EXECUTE_DESCRIPTION, get_discovery_tool_factories

    descriptions: dict[str, str] = {}

    for component in server.mcp.local_provider._components.values():
        if isinstance(component, Tool):
            descriptions[component.name] = component.description or ""

    async def _stub_catalog(ctx=None, **kwargs):
        return []

    for factory in get_discovery_tool_factories():
        tool = factory(_stub_catalog)
        descriptions[tool.name] = tool.description or ""
    descriptions["execute"] = EXECUTE_DESCRIPTION

    return descriptions


def check_description(name: str, desc: str, all_names: set[str]) -> list[str]:
    """Return a list of violation messages for one enforced tool."""
    problems: list[str] = []

    if not desc.strip():
        return [f"{name}: description is empty"]

    if "Use when:" not in desc:
        problems.append(f"{name}: missing 'Use when:' routing line")

    # Strip tool-name mentions (e.g. photos_smart_search) before the
    # adjective check so routing references don't trigger it.
    stripped = desc
    for other in all_names:
        stripped = stripped.replace(other, "")
    match = BANNED_ADJECTIVES.search(stripped)
    if match:
        problems.append(
            f"{name}: marketing adjective '{match.group(0)}' — state mechanics instead"
        )

    if name not in LENGTH_EXEMPT and len(desc) > MAX_DESCRIPTION_CHARS:
        problems.append(
            f"{name}: description is {len(desc)} chars (cap {MAX_DESCRIPTION_CHARS})"
        )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    descriptions = _collect_tools()
    all_names = set(descriptions.keys())

    missing = ENFORCED_TOOLS - all_names
    violations: list[str] = [
        f"{name}: enforced tool not found in catalog" for name in sorted(missing)
    ]

    for name in sorted(ENFORCED_TOOLS & all_names):
        violations.extend(check_description(name, descriptions[name], all_names))

    warnings = [
        name
        for name in sorted(all_names - ENFORCED_TOOLS)
        if "Use when:" not in descriptions[name]
    ]

    if args.verbose:
        for name in sorted(ENFORCED_TOOLS & all_names):
            print(f"  ✓ checked {name} ({len(descriptions[name])} chars)")

    if warnings:
        print(
            f"⚠ {len(warnings)} non-enforced tools lack a 'Use when:' line "
            "(advisory — add them to ENFORCED_TOOLS as they get the playbook treatment)"
        )
        if args.verbose:
            for name in warnings:
                print(f"    - {name}")

    if violations:
        print(f"\n✗ {len(violations)} tool description violation(s):")
        for violation in violations:
            print(f"  - {violation}")
        return 1

    print(f"✓ {len(ENFORCED_TOOLS & all_names)} enforced tool descriptions pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
