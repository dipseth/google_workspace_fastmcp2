"""Snapshot test for tool parameter schemas.

Guards against parameters silently dropping out of generated JSON schemas
(the ``get_doc_content`` class of bug from the Glama audit): every tool's
parameter names are snapshotted to ``tests/data/tool_schema_snapshot.json``.

On an intentional schema change, regenerate the snapshot:

    UPDATE_TOOL_SCHEMA_SNAPSHOT=1 uv run pytest tests/test_tool_schemas.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SNAPSHOT_PATH = Path(__file__).parent / "data" / "tool_schema_snapshot.json"


def _current_schemas() -> dict[str, list[str]]:
    from fastmcp.tools import Tool

    import server

    schemas: dict[str, list[str]] = {}
    for component in server.mcp.local_provider._components.values():
        if isinstance(component, Tool):
            properties = (component.parameters or {}).get("properties", {})
            schemas[component.name] = sorted(properties.keys())
    return schemas


def test_tool_parameter_schemas_match_snapshot():
    current = _current_schemas()
    assert current, "no tools found on server.mcp.local_provider"

    if (
        os.environ.get("UPDATE_TOOL_SCHEMA_SNAPSHOT") == "1"
        or not SNAPSHOT_PATH.exists()
    ):
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        if os.environ.get("UPDATE_TOOL_SCHEMA_SNAPSHOT") == "1":
            return  # explicit regeneration

    snapshot: dict[str, list[str]] = json.loads(SNAPSHOT_PATH.read_text())

    removed_tools = sorted(set(snapshot) - set(current))
    changed = {
        name: {
            "missing_params": sorted(set(params) - set(current[name])),
            "new_params": sorted(set(current[name]) - set(params)),
        }
        for name, params in snapshot.items()
        if name in current and sorted(params) != current[name]
    }

    problems = []
    if removed_tools:
        problems.append(f"tools removed since snapshot: {removed_tools}")
    for name, diff in changed.items():
        problems.append(f"{name}: {diff}")

    assert not problems, (
        "Tool schemas diverged from snapshot (parameters may have silently "
        "dropped out). If intentional, regenerate with "
        "UPDATE_TOOL_SCHEMA_SNAPSHOT=1 uv run pytest tests/test_tool_schemas.py\n"
        + "\n".join(problems)
    )
