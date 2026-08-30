"""Unit tests for create_spreadsheet's sheet_names handling.

Guards the fix for a client-reported crash: passing ``sheet_names`` as a bare
string (``"Roster"``) raised a Pydantic ValidationError on
CreateSpreadsheetResponse because the error path echoed the raw string into a
``List[str]`` field. A bare string is now accepted as a single sheet name, and
the response model coerces a stray string into a one-item list regardless.
"""

import pytest
from fastmcp import Client, FastMCP

import sheets.sheets_tools as sheets_tools
from sheets.sheets_tools import _parse_str_list, setup_sheets_tools
from sheets.sheets_types import CreateSpreadsheetResponse


class TestParseStrList:
    def test_bare_string_is_one_item(self):
        assert _parse_str_list("Roster", "sheet_names") == ["Roster"]

    def test_bare_string_with_comma_is_still_one_item(self):
        # Sheet titles may contain commas; a list is the explicit multi-sheet path.
        assert _parse_str_list("Roster, 2026", "sheet_names") == ["Roster, 2026"]

    def test_bare_string_that_is_valid_json_scalar_is_one_item(self):
        assert _parse_str_list("2024", "sheet_names") == ["2024"]
        assert _parse_str_list("true", "sheet_names") == ["true"]

    def test_json_encoded_string_is_unwrapped(self):
        assert _parse_str_list('"Roster"', "sheet_names") == ["Roster"]

    def test_json_encoded_list(self):
        assert _parse_str_list('["A", "B"]', "sheet_names") == ["A", "B"]

    def test_list_passthrough(self):
        assert _parse_str_list(["A", "B"], "sheet_names") == ["A", "B"]

    def test_none_passthrough(self):
        assert _parse_str_list(None, "sheet_names") is None

    def test_rejects_non_string_items(self):
        with pytest.raises(ValueError, match="must be strings"):
            _parse_str_list([1, "A"], "sheet_names")
        with pytest.raises(ValueError, match="must be strings"):
            _parse_str_list("[1]", "sheet_names")

    def test_rejects_non_string_non_list(self):
        with pytest.raises(ValueError, match="Invalid type"):
            _parse_str_list(42, "sheet_names")


class TestCreateSpreadsheetResponseCoercion:
    def _response(self, sheets):
        return CreateSpreadsheetResponse(
            spreadsheetId="id",
            spreadsheetUrl="https://example.test/sheet",
            title="t",
            sheets=sheets,
            success=True,
            message="",
        )

    def test_string_is_coerced_to_list(self):
        assert self._response("Roster").sheets == ["Roster"]

    def test_list_unchanged(self):
        assert self._response(["A", "B"]).sheets == ["A", "B"]

    def test_none_unchanged(self):
        assert self._response(None).sheets is None


class _FakeSheetsService:
    """Just enough of the googleapiclient surface for spreadsheets().create()."""

    def __init__(self):
        self.bodies = []

    def spreadsheets(self):
        return self

    def create(self, body):
        self.bodies.append(body)
        return self

    def execute(self):
        return {
            "spreadsheetId": "fake-id",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/fake-id",
        }


class TestCreateSpreadsheetTool:
    """The client's exact repro, end to end through the MCP tool."""

    @pytest.fixture
    def fake_service(self, monkeypatch):
        service = _FakeSheetsService()

        async def _get_service(_email):
            return service

        monkeypatch.setattr(
            sheets_tools, "_get_sheets_service_with_fallback", _get_service
        )
        return service

    async def _create(self, **params):
        mcp = FastMCP("test-sheets")
        setup_sheets_tools(mcp)
        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_spreadsheet",
                {"title": "Playing Time Calculator", **params},
            )
        return result.structured_content

    @pytest.mark.asyncio
    async def test_bare_string_sheet_name_creates_one_sheet(self, fake_service):
        out = await self._create(
            sheet_names="Roster", user_google_email="coach@example.com"
        )
        assert out["success"] is True, out
        assert out["sheets"] == ["Roster"]
        assert fake_service.bodies == [
            {
                "properties": {"title": "Playing Time Calculator"},
                "sheets": [{"properties": {"title": "Roster"}}],
            }
        ]

    @pytest.mark.asyncio
    async def test_list_still_works(self, fake_service):
        out = await self._create(
            sheet_names=["Roster", "Grid"], user_google_email="coach@example.com"
        )
        assert out["success"] is True, out
        assert out["sheets"] == ["Roster", "Grid"]
        assert [s["properties"]["title"] for s in fake_service.bodies[0]["sheets"]] == [
            "Roster",
            "Grid",
        ]

    @pytest.mark.asyncio
    async def test_bad_items_return_clean_error_not_a_crash(self, fake_service):
        out = await self._create(
            sheet_names="[1, 2]", user_google_email="coach@example.com"
        )
        assert out["success"] is False
        assert "must be strings" in out["error"]
        assert out["sheets"] is None
        assert fake_service.bodies == []
