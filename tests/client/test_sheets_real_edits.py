"""Real-edit integration tests for Google Sheets.

These tests are intentionally *destructive* in the sense that they will write to
your spreadsheet.

Safety / gating:
- Requires `TEST_GOOGLE_SHEET_ID` to be set.
- Requires `ENABLE_SHEETS_WRITE_TESTS=1` to be set, otherwise tests skip.

Write strategy:
- Write to a low-risk range on the *first sheet* (no sheet name prefix) using a
  far-away area within common default grid limits (A–Z columns, 1000 rows).
- Current write target: `X900:Y901`.
- Immediately read the same range back and assert the written values are present.
"""

from __future__ import annotations

import os
import time

import pytest

from .base_test_config import TEST_EMAIL


@pytest.fixture(scope="session")
def test_spreadsheet_id() -> str | None:
    return os.getenv("TEST_GOOGLE_SHEET_ID")


@pytest.fixture(scope="session")
def allow_writes() -> bool:
    return os.getenv("ENABLE_SHEETS_WRITE_TESTS") == "1"


@pytest.mark.service("sheets")
@pytest.mark.integration
@pytest.mark.auth_required
class TestSheetsRealEdits:
    @pytest.mark.asyncio
    async def test_modify_then_read_roundtrip(
        self, client, test_spreadsheet_id, allow_writes
    ):
        """Write values to a real sheet and read them back (round-trip verification)."""
        if not test_spreadsheet_id:
            pytest.skip("Set TEST_GOOGLE_SHEET_ID to run real-edit Sheets tests")
        if not allow_writes:
            pytest.skip("Set ENABLE_SHEETS_WRITE_TESTS=1 to run real-edit Sheets tests")

        # Use a unique marker so you can visually confirm changes.
        marker = f"mcp_test_{int(time.time())}"

        # Keep within default grid limits (many sheets start at 1000 rows x 26 cols (A-Z)).
        # Using columns X-Y keeps us within A-Z.
        write_range = "X900:Y901"
        values = [
            [marker, "hello"],
            ["42", "world"],
        ]

        write_result = await client.call_tool(
            "modify_sheet_values",
            {
                "user_google_email": TEST_EMAIL,
                "spreadsheet_id": test_spreadsheet_id,
                "range_name": write_range,
                "values": values,
                "value_input_option": "RAW",
            },
        )
        assert write_result is not None and write_result.content

        write_text = write_result.content[0].text.lower()
        # If the server isn't authenticated, this cannot be a real-edit test.
        if "no valid credentials" in write_text or "authenticate first" in write_text:
            pytest.skip(
                f"Sheets write auth not configured: {write_result.content[0].text}"
            )

        # Read back and verify.
        read_result = await client.call_tool(
            "read_sheet_values",
            {
                "user_google_email": TEST_EMAIL,
                "spreadsheet_id": test_spreadsheet_id,
                "range_name": write_range,
                "value_render_option": "UNFORMATTED_VALUE",
            },
        )
        assert read_result is not None and read_result.content

        content = read_result.content[0].text.lower()
        if "no valid credentials" in content or "authenticate first" in content:
            pytest.skip(
                f"Sheets read auth not configured: {read_result.content[0].text}"
            )
        # The server may return structured or text; the marker should appear in the payload.
        assert (
            marker.lower() in content
        ), f"Expected marker '{marker}' to be present in readback: {content}"
