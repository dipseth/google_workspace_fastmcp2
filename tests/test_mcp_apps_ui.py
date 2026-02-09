"""Tests for MCP Apps Phase 1 — ui:// resource and ToolUI metadata."""

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.apps import ResourceUI, ToolUI

from tools.ui_apps import _build_manage_tools_html, setup_ui_apps


@pytest.fixture
def mcp_with_ui():
    """Create a minimal FastMCP server with UI apps registered."""
    mcp = FastMCP("test-ui")

    # Register a tool with ToolUI metadata (mirrors manage_tools)
    @mcp.tool(
        name="manage_tools",
        ui=ToolUI(
            resource_uri="ui://manage-tools-dashboard",
            visibility=["app", "model"],
        ),
    )
    def manage_tools_stub() -> str:
        return "stub"

    setup_ui_apps(mcp)
    return mcp


# ── HTML builder tests ─────────────────────────────────────────────


def test_html_is_valid_document():
    html = _build_manage_tools_html()
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "<head>" in html
    assert "<body>" in html


def test_html_contains_tool_grid():
    html = _build_manage_tools_html()
    assert 'id="tool-grid"' in html


def test_html_contains_phase1_badge():
    html = _build_manage_tools_html()
    assert "Phase 1: Read-Only" in html


def test_html_contains_mcp_tools_placeholder():
    html = _build_manage_tools_html()
    assert "window.__MCP_TOOLS__" in html


# ── In-process client tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_has_ui_meta(mcp_with_ui):
    async with Client(mcp_with_ui) as client:
        tools = await client.list_tools()
        manage = next(t for t in tools if t.name == "manage_tools")
        assert manage.meta is not None
        ui = manage.meta.get("ui", {})
        assert ui.get("resourceUri") == "ui://manage-tools-dashboard"
        assert ui.get("visibility") == ["app", "model"]


@pytest.mark.asyncio
async def test_resource_exists(mcp_with_ui):
    async with Client(mcp_with_ui) as client:
        resources = await client.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "ui://manage-tools-dashboard" in uris


@pytest.mark.asyncio
async def test_resource_serves_html(mcp_with_ui):
    async with Client(mcp_with_ui) as client:
        contents = await client.read_resource("ui://manage-tools-dashboard")
        # read_resource returns a list of content items or a string
        if isinstance(contents, list):
            text = contents[0].text if hasattr(contents[0], "text") else str(contents[0])
        else:
            text = str(contents)
        assert "<!DOCTYPE html>" in text
        assert "tool-grid" in text


@pytest.mark.asyncio
async def test_resource_has_correct_mime(mcp_with_ui):
    async with Client(mcp_with_ui) as client:
        resources = await client.list_resources()
        dashboard = next(
            r for r in resources if str(r.uri) == "ui://manage-tools-dashboard"
        )
        # ui:// scheme should resolve to text/html;profile=mcp-app
        assert dashboard.mimeType is not None
        assert "text/html" in dashboard.mimeType


@pytest.mark.asyncio
async def test_resource_ui_meta(mcp_with_ui):
    async with Client(mcp_with_ui) as client:
        resources = await client.list_resources()
        dashboard = next(
            r for r in resources if str(r.uri) == "ui://manage-tools-dashboard"
        )
        assert dashboard.meta is not None
        ui = dashboard.meta.get("ui", {})
        assert ui.get("prefersBorder") is True
