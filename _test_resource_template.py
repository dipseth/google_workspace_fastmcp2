"""Quick test: parameterized resource template registration."""

import asyncio

from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig, app_config_to_meta_dict

mcp = FastMCP("test")


@mcp.resource(
    "ui://data-dashboard/{tool_name}",
    name="data_dashboard",
    title="Data Dashboard",
    description="Generic data dashboard",
)
def data_dashboard(tool_name: str) -> str:
    return f"<html><body>Dashboard for {tool_name}</body></html>"


@mcp.tool(name="list_things")
def list_things():
    return {"items": []}


async def main():
    lp = mcp.local_provider

    # Check templates
    templates = await lp.list_resource_templates()
    for t in templates:
        print(f"template: uri={t.uriTemplate}, name={t.name}")

    # Patch tool meta
    for key, component in lp._components.items():
        if not key.startswith("tool:"):
            continue
        tool_name = component.name
        component.meta = component.meta or {}
        component.meta["ui"] = app_config_to_meta_dict(
            AppConfig(resource_uri=f"ui://data-dashboard/{tool_name}")
        )
        print(f"patched: {tool_name} -> meta={component.meta}")

    # Verify via list_tools
    tools = await lp.list_tools()
    for t in tools:
        print(f"list_tools: {t.name} meta={t.meta}")


asyncio.run(main())
