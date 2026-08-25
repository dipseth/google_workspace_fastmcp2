"""Tests for MCP Apps Phase 1 — ui:// resource and AppConfig metadata."""

import pytest
from fastmcp import Client, FastMCP
from fastmcp.apps import AppConfig

from tools.ui_apps import _build_manage_tools_html, setup_ui_apps


@pytest.fixture
def mcp_with_ui():
    """Create a minimal FastMCP server with UI apps registered."""
    mcp = FastMCP("test-ui")

    # Register a tool with ToolUI metadata (mirrors manage_tools)
    @mcp.tool(
        name="manage_tools",
        app=AppConfig(
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


def test_html_contains_groups_container():
    html = _build_manage_tools_html()
    assert 'id="groups-container"' in html


def test_html_contains_phase1_badge():
    html = _build_manage_tools_html()
    assert "Phase 1" in html
    assert "Read-Only" in html


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
            text = (
                contents[0].text if hasattr(contents[0], "text") else str(contents[0])
            )
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


class TestDashboardCellsAreScalar:
    """The renderer draws each cell with String(value).

    A dict cell therefore arrives as the literal "[object Object]" — which is
    what Gmail label colours ({textColor, backgroundColor}) and Gmail filter
    criteria/action did. The "type" in _DASHBOARD_CONFIGS is understood only by
    our own HTML dashboard, so the Prefab path has to flatten these itself.
    """

    @staticmethod
    def _rows(tool_name, data):
        from tools.ui_apps import (
            _build_prefab_data_dashboard,
            get_data_dashboard_config,
        )

        app = _build_prefab_data_dashboard(
            tool_name, data, get_data_dashboard_config(tool_name)
        )
        view = app.to_json()["view"]
        return view["children"][0]["children"][1]["rows"]

    def test_label_colour_renders_as_a_hex_string(self):
        rows = self._rows(
            "list_gmail_labels",
            {
                "labels": [
                    {
                        "name": "junk",
                        "type": "user",
                        "color": {
                            "textColor": "#ffffff",
                            "backgroundColor": "#ac2b16",
                        },
                        "messagesTotal": 118,
                        "messagesUnread": 2,
                        "threadsTotal": 117,
                    }
                ]
            },
        )
        assert rows[0]["color"] == "#ac2b16"

    def test_a_missing_colour_stays_empty(self):
        rows = self._rows(
            "list_gmail_labels",
            {"labels": [{"name": "CHAT", "type": "system", "color": None}]},
        )
        assert rows[0]["color"] is None

    def test_nested_filter_fields_are_flattened(self):
        rows = self._rows(
            "list_gmail_filters",
            {
                "filters": [
                    {
                        "id": "f1",
                        "criteria": {"from": "a@b.com"},
                        "action": {"addLabelIds": ["Label_1"]},
                    }
                ]
            },
        )
        assert rows[0]["criteria"] == "from: a@b.com"
        assert "Label_1" in rows[0]["action"]

    def test_rows_carry_only_the_displayed_columns(self):
        """Undisplayed keys ride to the model in structuredContent for nothing."""
        rows = self._rows(
            "list_gmail_labels",
            {
                "labels": [
                    {
                        "name": "CHAT",
                        "type": "system",
                        "id": "CHAT",
                        "threadsUnread": 0,
                        "messageListVisibility": "hide",
                    }
                ]
            },
        )
        assert set(rows[0]) == {
            "name",
            "type",
            "messagesTotal",
            "messagesUnread",
            "threadsTotal",
            "color",
        }

    def test_every_cell_is_renderable(self):
        from tools.ui_apps import _scalarize_cell

        for value in ({"a": 1}, ["x", "y"], ("x",), {"a": None}):
            out = _scalarize_cell(value)
            assert out is None or isinstance(out, str), value
