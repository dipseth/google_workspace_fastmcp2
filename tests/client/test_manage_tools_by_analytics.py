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
        assert "manage_tools_by_analytics" in tool_names, (
            "manage_tools_by_analytics tool should be available in server"
        )

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
        assert results["backward_compatible"], (
            "manage_tools_by_analytics should work with explicit user_google_email"
        )

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
        assert explicit_content is not None and len(explicit_content) > 0, (
            "Preview action should return descriptive content"
        )

    @pytest.mark.asyncio
    async def test_preview_handles_qdrant_states_gracefully(self, client):
        """Preview action should handle Qdrant availability or analytics state without crashing."""
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
        valid_indicators = [
            "qdrant not available",
            "failed to get analytics",
            "no tool usage data",
            "no tools found",
            "analytics-based tool management preview",
        ]
        assert any(indicator in lowered for indicator in valid_indicators), (
            "Preview should return a clear status message about Qdrant analytics "
            "availability or matched tools"
        )

        # If we reached the full preview output, validate core sections are present
        if "analytics-based tool management preview" in lowered:
            assert "filters applied" in lowered
            assert "matched tools" in lowered