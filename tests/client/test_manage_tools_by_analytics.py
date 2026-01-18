"""Test manage_tools_by_analytics tool using standardized client framework."""

import pytest

from .base_test_config import TEST_EMAIL
from .test_helpers import ToolTestRunner


@pytest.mark.service("qdrant")
class TestManageToolsByAnalytics:
    """Tests for Qdrant analytics-based tool management."""

    @pytest.mark.asyncio
    async def test_tool_available(self, client):
        """Ensure manage_tools_by_analytics tool is registered."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        assert (
            "manage_tools_by_analytics" in tool_names
        ), "manage_tools_by_analytics tool should be available in server"

    @pytest.mark.asyncio
    async def test_auth_patterns_preview_action(self, client):
        """Test both auth patterns for manage_tools_by_analytics with preview action."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Use non-destructive preview action with conservative limits
        base_params = {
            "action": "preview",
            "service_filter": None,
            "limit": 5,
            "min_usage_count": 1,
        }

        results = await runner.test_auth_patterns(
            "manage_tools_by_analytics",
            base_params,
        )

        # Explicit email path should be backward compatible
        assert results[
            "backward_compatible"
        ], "manage_tools_by_analytics should work with explicit user_google_email"

        # Middleware injection may or may not be supported; both outcomes are acceptable
        middleware_result = results["middleware_injection"]
        assert results["middleware_supported"] or (
            middleware_result.get("param_required_at_client")
        ), (
            "Middleware injection should either work or clearly require "
            "user_google_email at client level"
        )

        # Response should be non-empty and reasonably sized for preview
        explicit_content = results["explicit_email"]["content"]
        assert (
            explicit_content is not None and len(explicit_content) > 0
        ), "Preview action should return descriptive content"

    @pytest.mark.asyncio
    async def test_preview_handles_qdrant_states_gracefully(self, client):
        """Preview action should handle Qdrant availability or analytics state without crashing."""
        # First verify the tool is registered (may not be in list_tools if disabled,
        # but should exist in registry)
        from .test_helpers import assert_tools_registered

        await assert_tools_registered(
            client, ["manage_tools_by_analytics"], context="Analytics tool"
        )

        result = await client.call_tool(
            "manage_tools_by_analytics",
            {
                "user_google_email": TEST_EMAIL,
                "action": "preview",
                "service_filter": None,
                "limit": 5,
                "min_usage_count": 1,
            },
        )

        assert result is not None
        content = result.content[0].text if result.content else ""

        assert len(content) > 0, "Preview response should not be empty"

        lowered = content.lower()
        # These indicators match the actual messages returned by ManageToolsByAnalyticsResponse:
        # - "Qdrant not available - cannot analyze tool usage data"
        # - "Failed to retrieve analytics data"
        # - "No tool usage data found in Qdrant. Analytics database may be empty."
        # - "No tools found... with usage count >= ..."
        # - "Preview: Found X tool(s) matching criteria..."
        # - "Tool management by analytics failed" (exception case)
        valid_indicators = [
            "qdrant not available",
            "failed to retrieve analytics",
            "no tool usage data",
            "no tools found",
            "preview: found",
            "tool management by analytics failed",
        ]
        assert any(indicator in lowered for indicator in valid_indicators), (
            f"Preview should return a clear status message about Qdrant analytics "
            f"availability or matched tools. Got: {content[:200]}"
        )

        # If we got a successful preview with tools, validate the response structure
        if "preview: found" in lowered and "tool(s) matching criteria" in lowered:
            # The response is a structured ManageToolsByAnalyticsResponse
            # Check that it contains expected JSON fields
            assert (
                "toolsmatched" in lowered
                or "tools_matched" in lowered
                or '"action"' in content.lower()
            )
