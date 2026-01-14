"""Tests for Sheets value rendering options (value_render_option/date_time_render_option).

This validates the newly-exposed rendering parameters on the `read_sheet_values` tool.
The test is written to be robust in environments where OAuth is not configured:
- If authenticated, it should succeed and return structured data.
- If unauthenticated, it should return a valid auth/middleware error response.
"""

import json
import os
import pytest

from .base_test_config import TEST_EMAIL
from .test_helpers import ToolTestRunner

@pytest.fixture(scope="session")
def test_spreadsheet_id() -> str | None:
    """Spreadsheet ID for tests.

    Prefer using a stable, pre-created sheet ID from environment variables (same
    pattern as `TEST_DOCUMENT_ID` in other client tests).

    Expected env var:
    - TEST_GOOGLE_SHEET_ID
    """
    return os.getenv("TEST_GOOGLE_SHEET_ID")


@pytest.mark.service("sheets")
class TestSheetsValueRendering:
    @pytest.mark.asyncio
    async def test_read_sheet_values_value_render_options_auth_patterns(self, client, test_spreadsheet_id):
        """Test read_sheet_values accepts value_render_option/date_time_render_option under both auth patterns."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available (set TEST_GOOGLE_SHEET_ID)")

        runner = ToolTestRunner(client, TEST_EMAIL)

        results = await runner.test_auth_patterns(
            "read_sheet_values",
            {
                "spreadsheet_id": test_spreadsheet_id,
                "range_name": "A1:D10",
                "value_render_option": "FORMATTED_VALUE",
                "date_time_render_option": "FORMATTED_STRING",
            },
        )

        # Explicit email call should remain backward compatible (or return a valid auth error)
        assert results["backward_compatible"], "Explicit email pattern should work"

        # If explicit succeeded, do lightweight structure validation
        explicit = results["explicit_email"]
        if explicit.get("success") and explicit.get("content"):
            # Some servers return JSON as text; accept both json string and plain text
            content = explicit["content"]
            if content.strip().startswith("{"):
                parsed = json.loads(content)
                assert "spreadsheetId" in parsed
                assert "values" in parsed

        # Middleware path may be supported or may correctly fail with "param required" depending on test setup
        assert (
            results["middleware_supported"]
            or results["middleware_injection"].get("param_required_at_client")
            or results["middleware_injection"].get("success")
        ), "Middleware injection should work or be rejected with a parameter-required error"
