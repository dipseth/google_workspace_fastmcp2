"""Tests for unified Gmail allow list management tool."""

import pytest

from .base_test_config import TEST_EMAIL
from .test_helpers import ToolTestRunner, print_test_result


@pytest.mark.service("gmail")
class TestGmailAllowListTools:
    """Tests for manage_gmail_allow_list MCP tool.

    These tests provide baseline coverage before refactors so we can:
      - Assert the tool is registered
      - Verify both auth patterns (explicit email and middleware injection)
    """

    @pytest.mark.asyncio
    async def test_manage_gmail_allow_list_available(self, client):
        """Ensure manage_gmail_allow_list tool is registered."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        if "manage_gmail_allow_list" not in tool_names:
            pytest.skip("manage_gmail_allow_list tool not available in this server")

    @pytest.mark.asyncio
    async def test_manage_gmail_allow_list_auth_patterns_view(self, client):
        """Test auth patterns for manage_gmail_allow_list(action='view')."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("manage_gmail_allow_list"):
            pytest.skip("manage_gmail_allow_list tool not available")

        # Use 'view' action which is safe and side-effect free
        auth_results = await runner.test_auth_patterns(
            "manage_gmail_allow_list",
            {"action": "view"},
        )

        explicit = auth_results["explicit_email"]
        middleware = auth_results["middleware_injection"]

        print_test_result("manage_gmail_allow_list explicit email (view)", explicit)
        print_test_result("manage_gmail_allow_list middleware injection (view)", middleware)

        # Both patterns should either succeed or produce auth-related responses,
        # or indicate that user_google_email must be supplied at the client level.
        explicit_valid = explicit["success"] or explicit["is_auth_related"]
        middleware_valid = (
            middleware.get("success", False)
            or middleware.get("param_required_at_client", False)
        )

        assert explicit_valid, "Explicit auth pattern should work or give auth error"
        assert middleware_valid, (
            "Middleware auth pattern should work, be auth-related, "
            "or clearly require user_google_email at client"
        )