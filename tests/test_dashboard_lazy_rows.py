"""The dashboard card fetches its rows itself; the model never pays for them.

Hosts hand ``structuredContent`` to the model as well as to the iframe, so a
``DataTable`` embedded in the injected card cost ~80 tokens a row on every
call — ~5k tokens for 65 Gmail labels, most of it the colour swatches. Now the
middleware stashes the result under an unguessable key, the card ships with an
empty table, and an ``on_mount`` ``CallTool`` to the DashboardRows app tool
fills it in. A UI-initiated tool result reaches only the iframe.
"""

import json

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.providers.addressing import hashed_backend_name
from fastmcp.tools import ToolResult

from middleware import dashboard_cache_middleware as dc
from tools.ui_apps import (
    DASHBOARD_ROWS_APP,
    _build_prefab_data_dashboard,
    create_dashboard_rows_app,
    get_data_dashboard_config,
    serialize_dashboard_rows,
)

ROWS_TOOL = hashed_backend_name(DASHBOARD_ROWS_APP, "dashboard_rows")


def _labels(n: int) -> dict:
    return {
        "labels": [
            {
                "id": f"Label_{i}",
                "name": f"Project/Client {i}",
                "type": "user",
                "messagesTotal": i * 7,
                "messagesUnread": i % 5,
                "threadsTotal": i * 3,
                "threadsUnread": i % 3,
                "color": {"textColor": "#ffffff", "backgroundColor": f"#{i:06x}"},
                "messageListVisibility": "show",
            }
            for i in range(n)
        ],
        "count": n,
    }


def _find(node, type_name):
    """First component node of *type_name* in a serialized view."""
    if isinstance(node, dict):
        if node.get("type") == type_name:
            return node
        for v in node.values():
            found = _find(v, type_name)
            if found is not None:
                return found
    if isinstance(node, list):
        for v in node:
            found = _find(v, type_name)
            if found is not None:
                return found
    return None


def _mount_call(spec):
    """The toolCall the card fires when drawn. PrefabApp hoists ``on_mount``
    onto the view wrapper it serializes, not the Column we built."""
    mount = spec["view"].get("onMount")
    assert mount is not None, "the card must fetch its rows when drawn"
    calls = mount if isinstance(mount, list) else [mount]
    return next(c for c in calls if c.get("action") == "toolCall")


@pytest.fixture(autouse=True)
def _clean_stash(monkeypatch):
    monkeypatch.setattr(dc, "_rows_stash", {})
    monkeypatch.setattr(dc, "_rows_tool", None)


class TestLazyShell:
    def _shell(self, n=65, key="k-123"):
        cfg = get_data_dashboard_config("list_gmail_labels")
        app = _build_prefab_data_dashboard(
            "list_gmail_labels", _labels(n), cfg, rows_tool=ROWS_TOOL, rows_key=key
        )
        return app.to_json()

    def test_table_ships_empty_and_bound_to_state(self):
        spec = self._shell()
        table = _find(spec, "DataTable")
        assert table["rows"] == "{{ rows }}"
        assert [c["key"] for c in table["columns"]] == [
            c["key"] for c in get_data_dashboard_config("list_gmail_labels")["columns"]
        ]
        assert spec["state"] == {"rows": [], "loading": True, "error": ""}

    def test_on_mount_calls_the_rows_tool_with_the_key(self):
        spec = self._shell(key="secret-key")
        call = _mount_call(spec)
        assert call["tool"] == ROWS_TOOL
        assert call["arguments"] == {"key": "secret-key"}
        assert any(a.get("action") == "setState" for a in call["onSuccess"])

    def test_success_never_writes_the_error_state(self):
        """Regression: "Couldn't load this table: {{ $result.error }}" over a
        table that had in fact loaded — RESULT.error was set on success and an
        absent key left the template literal, which is a truthy string."""
        call = _mount_call(self._shell())
        touched = {
            a.get("key") for a in call["onSuccess"] if a.get("action") == "setState"
        }
        assert "error" not in touched
        assert "rows" in touched and "loading" in touched
        on_error = {
            a.get("key") for a in call["onError"] if a.get("action") == "setState"
        }
        assert "error" in on_error

    def test_shell_cost_does_not_grow_with_rows(self):
        small = len(json.dumps(self._shell(n=1)))
        large = len(json.dumps(self._shell(n=65)))
        assert large - small < 50, "row data must not leak into the shell"
        assert large < 2_500, f"shell is {large} bytes; the inline table was ~20k"

    def test_no_row_data_in_the_shell(self):
        assert "Project/Client" not in json.dumps(self._shell())

    def test_inline_without_a_key_is_unchanged(self):
        cfg = get_data_dashboard_config("list_gmail_labels")
        spec = _build_prefab_data_dashboard(
            "list_gmail_labels", _labels(3), cfg
        ).to_json()
        table = _find(spec, "DataTable")
        assert len(table["rows"]) == 3
        assert table["rows"][0]["color"]["type"] == "Span"
        assert "state" not in spec or not spec.get("state")


class TestSerializedRows:
    def test_rows_are_projected_and_swatches_are_nodes(self):
        cfg = get_data_dashboard_config("list_gmail_labels")
        rows = serialize_dashboard_rows("list_gmail_labels", _labels(2), cfg)
        assert len(rows) == 2
        assert set(rows[0]) == {c["key"] for c in cfg["columns"]}, "hidden keys dropped"
        swatch = rows[0]["color"]
        assert isinstance(swatch, dict) and swatch["type"] == "Span"
        assert swatch["style"]["backgroundColor"] == "#000000"
        json.dumps(rows)  # must be wire-safe


class TestStash:
    def test_round_trip(self):
        key = dc.stash_dashboard_data("list_gmail_labels", {"labels": [1]})
        assert dc.get_stashed_dashboard(key) == ("list_gmail_labels", {"labels": [1]})

    def test_unknown_key(self):
        assert dc.get_stashed_dashboard("nope") is None

    def test_keys_are_unguessable_and_distinct(self):
        a = dc.stash_dashboard_data("t", {})
        b = dc.stash_dashboard_data("t", {})
        assert a != b and len(a) >= 32

    def test_expired_key_is_gone(self, monkeypatch):
        key = dc.stash_dashboard_data("t", {"x": 1})
        real = dc.time.time
        monkeypatch.setattr(dc.time, "time", lambda: real() + dc._ROWS_STASH_TTL + 1)
        assert dc.get_stashed_dashboard(key) is None
        assert key not in dc._rows_stash

    def test_oldest_evicted_at_capacity(self):
        first = dc.stash_dashboard_data("t", {"n": 0})
        for i in range(1, dc._ROWS_STASH_MAX + 1):
            dc.stash_dashboard_data("t", {"n": i})
        assert dc.get_stashed_dashboard(first) is None
        assert len(dc._rows_stash) <= dc._ROWS_STASH_MAX

    def test_clear_dashboard_cache_empties_the_stash(self):
        dc.stash_dashboard_data("t", {})
        dc.clear_dashboard_cache()
        assert dc._rows_stash == {}


class TestMiddlewareInjection:
    def _inject(self, data):
        result = ToolResult(content=json.dumps(data), structured_content=data)
        dc.DashboardCacheMiddleware._inject_prefab_dashboard(
            result, "list_gmail_labels", data
        )
        return result.structured_content

    def test_shell_when_rows_tool_is_mounted(self):
        dc.set_rows_tool(ROWS_TOOL)
        spec = self._inject(_labels(40))
        assert _find(spec, "DataTable")["rows"] == "{{ rows }}"
        (key,) = dc._rows_stash
        assert _mount_call(spec)["arguments"] == {"key": key}
        assert "Project/Client" not in json.dumps(spec)

    def test_empty_result_draws_inline_and_stashes_nothing(self):
        """manage_tools action=enable has no toolList: no "Loading 0 rows…"."""
        dc.set_rows_tool(ROWS_TOOL)
        spec = self._inject({"labels": [], "count": 0})
        assert _find(spec, "DataTable")["rows"] == []
        assert "onMount" not in spec["view"]
        assert "Loading" not in json.dumps(spec)
        assert dc._rows_stash == {}

    def test_inline_when_no_rows_tool(self):
        spec = self._inject(_labels(4))
        assert len(_find(spec, "DataTable")["rows"]) == 4
        assert dc._rows_stash == {}, "nothing to stash when nothing will fetch it"


class TestRowsAppEndToEnd:
    """The card's fetch, as the host would make it: a hashed tool, by key."""

    def _server(self):
        mcp = FastMCP("dash-test")
        app = create_dashboard_rows_app()
        assert app is not None
        mcp.add_provider(app)
        return mcp

    async def test_mounting_registers_the_wire_name(self):
        self._server()
        assert dc.get_rows_tool() == ROWS_TOOL

    async def test_card_fetches_exactly_its_result(self):
        mcp = self._server()
        key = dc.stash_dashboard_data("list_gmail_labels", _labels(3))
        async with Client(mcp) as client:
            out = (await client.call_tool(ROWS_TOOL, {"key": key})).structured_content
        assert out["count"] == 3
        assert out["rows"][1]["name"] == "Project/Client 1"
        assert out["rows"][1]["color"]["type"] == "Span"
        assert "id" not in out["rows"][0]

    async def test_expired_or_forged_key_is_an_error_result(self):
        """An error *result*, so the card's on_error branch shows it."""
        from fastmcp.exceptions import ToolError

        mcp = self._server()
        async with Client(mcp) as client:
            with pytest.raises(ToolError, match="expired"):
                await client.call_tool(ROWS_TOOL, {"key": "forged"})

    async def test_rows_tool_is_not_offered_to_the_model(self):
        mcp = self._server()
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
        assert ROWS_TOOL not in names
        assert "dashboard_rows" not in names
