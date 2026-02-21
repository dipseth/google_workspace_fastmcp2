"""
Unit tests for TagBasedResourceMiddleware.

This test suite verifies the middleware-based approach for handling service:// URIs
that replaces the complex 1715-line ServiceListDiscovery implementation with a
simplified tag-based approach.

Tests cover:
1. Middleware URI pattern matching and interception
2. Tool discovery via tags and metadata
3. Authentication context injection
4. Response formatting consistency
5. Error handling and edge cases
6. Service metadata validation
"""

import json
import os

# Test imports
import sys
from typing import List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastmcp.server.middleware import MiddlewareContext

from middleware.tag_based_resource_middleware import TagBasedResourceMiddleware


class MockTool:
    """Mock tool for testing tool discovery."""

    def __init__(self, name: str, tags: Optional[List[str]] = None):
        self.name = name
        self.tags = tags or []
        self.call = AsyncMock()

    async def __call__(self, **kwargs):
        return await self.call(**kwargs)


class MockMessage:
    """Mock message for MiddlewareContext."""

    def __init__(self, uri: str):
        self.uri = uri


class MockFastMCPContext:
    """Mock FastMCP context for testing."""

    def __init__(self, tools: Optional[List[MockTool]] = None):
        self.tools = tools or []

    def get_tools(self) -> List[MockTool]:
        return self.tools


class TestTagBasedResourceMiddleware:
    """Test the TagBasedResourceMiddleware functionality."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance for testing."""
        return TagBasedResourceMiddleware(enable_debug_logging=True)

    @pytest.fixture
    def mock_context(self):
        """Create mock MiddlewareContext."""
        context = Mock(spec=MiddlewareContext)
        context.message = MockMessage("service://gmail/lists")
        context.fastmcp_context = MockFastMCPContext()
        return context

    @pytest.fixture
    def mock_call_next(self):
        """Mock call_next function."""
        return AsyncMock()

    @pytest.fixture
    def sample_tools(self):
        """Create sample tools with appropriate tags."""
        return [
            MockTool("list_gmail_filters", ["list", "gmail", "filters"]),
            MockTool("get_gmail_filter", ["get", "gmail", "filters"]),
            MockTool("list_gmail_labels", ["list", "gmail", "labels"]),
            MockTool("list_drive_items", ["list", "drive", "items"]),
            MockTool("get_drive_file_content", ["get", "drive", "items"]),
            MockTool("list_calendars", ["list", "calendar", "calendars"]),
            MockTool("list_events", ["list", "calendar", "events"]),
            MockTool("get_event", ["get", "calendar", "events"]),
        ]

    # ===== URI Pattern Detection Tests =====

    def test_service_uri_pattern_matching(self, middleware):
        """Test the SERVICE_URI_PATTERN regex."""
        pattern = middleware.SERVICE_URI_PATTERN

        # Valid patterns
        valid_cases = [
            ("service://gmail/lists", ("gmail", "lists", None)),
            ("service://gmail/filters", ("gmail", "filters", None)),
            ("service://gmail/filters/123", ("gmail", "filters", "123")),
            ("service://drive/items/file_id_123", ("drive", "items", "file_id_123")),
            (
                "service://calendar/events/event_123",
                ("calendar", "events", "event_123"),
            ),
            ("service://docs/documents", ("docs", "documents", None)),
        ]

        for uri, expected in valid_cases:
            match = pattern.match(uri)
            assert match is not None, f"Should match valid URI: {uri}"
            assert match.group("service") == expected[0]
            assert match.group("list_type") == expected[1]
            assert match.group("id") == expected[2]

    def test_invalid_service_uri_patterns(self, middleware):
        """Test invalid URI patterns."""
        pattern = middleware.SERVICE_URI_PATTERN

        invalid_cases = [
            "service://",
            "service:///lists",
            "service://gmail/",
            "service://gmail//",
            "not-service://gmail/lists",
            "service:/gmail/lists",  # Missing slash
            "service:///gmail/lists",  # Extra slash
        ]

        for uri in invalid_cases:
            match = pattern.match(uri)
            assert match is None, f"Should not match invalid URI: {uri}"

    # ===== Middleware Integration Tests =====

    @pytest.mark.asyncio
    async def test_middleware_passes_through_non_service_uris(
        self, middleware, mock_context, mock_call_next
    ):
        """Test that non-service URIs are passed through to next middleware."""
        # Setup non-service URI
        mock_context.message.uri = "user://current/email"
        mock_call_next.return_value = {"test": "passed_through"}

        # Call middleware
        result = await middleware.on_read_resource(mock_context, mock_call_next)

        # Verify call_next was called and result passed through
        mock_call_next.assert_called_once_with(mock_context)
        assert result == {"test": "passed_through"}

    @pytest.mark.asyncio
    async def test_middleware_intercepts_service_uris(
        self, middleware, mock_context, mock_call_next
    ):
        """Test that service URIs are intercepted by middleware."""
        # Setup service URI
        mock_context.message.uri = "service://gmail/lists"

        # Call middleware
        result = await middleware.on_read_resource(mock_context, mock_call_next)

        # Verify call_next was NOT called
        mock_call_next.assert_not_called()

        # Verify result is from middleware
        assert "text" in result
        assert "contents" in result

    @pytest.mark.asyncio
    async def test_invalid_service_uri_format_error(
        self, middleware, mock_context, mock_call_next
    ):
        """Test error handling for invalid service URI format."""
        mock_context.message.uri = "service://invalid"

        result = await middleware.on_read_resource(mock_context, mock_call_next)

        assert "text" in result
        assert "Error:" in result["text"]
        assert len(result["contents"]) > 0

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert "Invalid service URI format" in content["message"]

    # ===== Service Lists Endpoint Tests =====

    @pytest.mark.asyncio
    async def test_handle_service_lists_gmail(
        self, middleware, mock_context, sample_tools
    ):
        """Test service lists endpoint for Gmail."""
        mock_context.message.uri = "service://gmail/lists"
        mock_context.fastmcp_context = MockFastMCPContext(sample_tools)

        result = await middleware._handle_service_lists("gmail", mock_context)

        # Verify response structure
        assert "text" in result
        assert "contents" in result
        assert len(result["contents"]) > 0

        content = json.loads(result["contents"][0]["text"])
        assert content["service"] == "gmail"
        assert "service_metadata" in content
        assert "list_types" in content
        assert "total_list_types" in content

        # Verify Gmail specific metadata
        assert content["service_metadata"]["display_name"] == "Gmail"
        assert content["service_metadata"]["icon"] == "📧"

        # Verify available list types based on tools
        list_types = content["list_types"]
        assert "filters" in list_types
        assert "labels" in list_types

        # Verify list type structure
        filters_info = list_types["filters"]
        assert filters_info["display_name"] == "Email Filters"
        assert filters_info["tool_name"] == "list_gmail_filters"
        assert filters_info["supports_get"] is True
        assert filters_info["id_field"] == "filter_id"

    @pytest.mark.asyncio
    async def test_handle_service_lists_unsupported_service(
        self, middleware, mock_context
    ):
        """Test service lists endpoint for unsupported service."""
        result = await middleware._handle_service_lists(
            "unsupported_service", mock_context
        )

        # Verify error response
        assert "text" in result
        assert "Error:" in result["text"]

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert "Unsupported service: unsupported_service" in content["message"]
        assert "Supported services:" in content["help"]

    @pytest.mark.asyncio
    async def test_handle_service_lists_filters_by_available_tools(
        self, middleware, mock_context
    ):
        """Test that service lists filters by actually available tools."""
        # Only provide filters tool, not labels tool
        tools = [MockTool("list_gmail_filters", ["list", "gmail", "filters"])]
        mock_context.fastmcp_context = MockFastMCPContext(tools)

        result = await middleware._handle_service_lists("gmail", mock_context)

        content = json.loads(result["contents"][0]["text"])
        list_types = content["list_types"]

        # Should only have filters, not labels
        assert "filters" in list_types
        assert "labels" not in list_types

    # ===== List Items Endpoint Tests =====

    @pytest.mark.asyncio
    @patch("middleware.tag_based_resource_middleware.get_user_email_context")
    async def test_handle_list_items_success(
        self, mock_get_user_email, middleware, mock_context, sample_tools
    ):
        """Test successful list items handling."""
        mock_get_user_email.return_value = "test@example.com"
        mock_context.fastmcp_context = MockFastMCPContext(sample_tools)

        # Mock tool call result
        filters_tool = next(t for t in sample_tools if t.name == "list_gmail_filters")
        filters_tool.call.return_value = {"filters": [{"id": "1", "criteria": "test"}]}

        result = await middleware._handle_list_items("gmail", "filters", mock_context)

        # Verify tool was called with correct parameters
        filters_tool.call.assert_called_once_with(user_google_email="test@example.com")

        # Verify response structure
        assert "text" in result
        assert "contents" in result

        content = json.loads(result["contents"][0]["text"])
        assert content["service"] == "gmail"
        assert content["list_type"] == "filters"
        assert content["tool_called"] == "list_gmail_filters"
        assert content["user_email"] == "test@example.com"
        assert "result" in content
        assert content["result"]["filters"][0]["id"] == "1"

    @pytest.mark.asyncio
    @patch("middleware.tag_based_resource_middleware.get_user_email_context")
    async def test_handle_list_items_no_user_email(
        self, mock_get_user_email, middleware, mock_context
    ):
        """Test list items handling when no user email in context."""
        mock_get_user_email.return_value = None

        result = await middleware._handle_list_items("gmail", "filters", mock_context)

        # Verify error response
        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert "User email not found in context" in content["message"]

    @pytest.mark.asyncio
    async def test_handle_list_items_unsupported_service(
        self, middleware, mock_context
    ):
        """Test list items for unsupported service."""
        result = await middleware._handle_list_items(
            "unsupported", "filters", mock_context
        )

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert "Unsupported service: unsupported" in content["message"]

    @pytest.mark.asyncio
    async def test_handle_list_items_unsupported_list_type(
        self, middleware, mock_context
    ):
        """Test list items for unsupported list type."""
        result = await middleware._handle_list_items(
            "gmail", "unsupported_list", mock_context
        )

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert (
            "Unsupported list type 'unsupported_list' for service 'gmail'"
            in content["message"]
        )
        assert "Available list types:" in content["help"]

    @pytest.mark.asyncio
    async def test_handle_list_items_no_list_tool(self, middleware, mock_context):
        """Test list items for list type without list tool."""
        # Test with slides/presentations which has no list_tool in SERVICE_METADATA
        result = await middleware._handle_list_items(
            "slides", "presentations", mock_context
        )

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert "No list tool configured for slides/presentations" in content["message"]

    # ===== Specific Item Endpoint Tests =====

    @pytest.mark.asyncio
    @patch("middleware.tag_based_resource_middleware.get_user_email_context")
    async def test_handle_specific_item_success(
        self, mock_get_user_email, middleware, mock_context, sample_tools
    ):
        """Test successful specific item handling."""
        mock_get_user_email.return_value = "test@example.com"
        mock_context.fastmcp_context = MockFastMCPContext(sample_tools)

        # Mock tool call result
        get_tool = next(t for t in sample_tools if t.name == "get_gmail_filter")
        get_tool.call.return_value = {
            "filter_id": "123",
            "criteria": {"from": "test@test.com"},
        }

        result = await middleware._handle_specific_item(
            "gmail", "filters", "123", mock_context
        )

        # Verify tool was called with correct parameters
        get_tool.call.assert_called_once_with(
            user_google_email="test@example.com", filter_id="123"
        )

        # Verify response structure
        content = json.loads(result["contents"][0]["text"])
        assert content["service"] == "gmail"
        assert content["list_type"] == "filters"
        assert content["item_id"] == "123"
        assert content["tool_called"] == "get_gmail_filter"
        assert content["user_email"] == "test@example.com"
        assert "result" in content
        assert content["result"]["filter_id"] == "123"

    @pytest.mark.asyncio
    async def test_handle_specific_item_no_get_tool(self, middleware, mock_context):
        """Test specific item for list type without get tool."""
        # Test with gmail/labels which has no get_tool in SERVICE_METADATA
        result = await middleware._handle_specific_item(
            "gmail", "labels", "123", mock_context
        )

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert "No get tool configured for gmail/labels" in content["message"]

    # ===== Tool Discovery Tests =====

    @pytest.mark.asyncio
    async def test_get_available_tools_success(
        self, middleware, mock_context, sample_tools
    ):
        """Test successful tool discovery."""
        mock_context.fastmcp_context = MockFastMCPContext(sample_tools)

        available_tools = await middleware._get_available_tools(mock_context)

        expected_tool_names = {tool.name for tool in sample_tools}
        assert available_tools == expected_tool_names

    @pytest.mark.asyncio
    async def test_get_available_tools_no_context(self, middleware):
        """Test tool discovery when no FastMCP context available."""
        mock_context = Mock(spec=MiddlewareContext)
        mock_context.fastmcp_context = None

        available_tools = await middleware._get_available_tools(mock_context)

        assert available_tools == set()

    @pytest.mark.asyncio
    async def test_get_available_tools_exception(self, middleware, mock_context):
        """Test tool discovery when exception occurs."""
        # Mock context that raises exception
        mock_context.fastmcp_context.get_tools.side_effect = Exception("Test error")

        available_tools = await middleware._get_available_tools(mock_context)

        assert available_tools == set()

    # ===== Tool Calling Tests =====

    @pytest.mark.asyncio
    async def test_call_tool_with_context_success(
        self, middleware, mock_context, sample_tools
    ):
        """Test successful tool calling."""
        mock_context.fastmcp_context = MockFastMCPContext(sample_tools)

        filters_tool = next(t for t in sample_tools if t.name == "list_gmail_filters")
        filters_tool.call.return_value = {"success": True}

        result = await middleware._call_tool_with_context(
            mock_context,
            "list_gmail_filters",
            {"user_google_email": "test@example.com"},
        )

        assert result == {"success": True}
        filters_tool.call.assert_called_once_with(user_google_email="test@example.com")

    @pytest.mark.asyncio
    async def test_call_tool_with_context_no_fastmcp_context(self, middleware):
        """Test tool calling when no FastMCP context available."""
        mock_context = Mock(spec=MiddlewareContext)
        mock_context.fastmcp_context = None

        with pytest.raises(RuntimeError, match="FastMCP context not available"):
            await middleware._call_tool_with_context(mock_context, "test_tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_with_context_tool_not_found(
        self, middleware, mock_context, sample_tools
    ):
        """Test tool calling when tool not found."""
        mock_context.fastmcp_context = MockFastMCPContext(sample_tools)

        with pytest.raises(RuntimeError, match="Tool 'nonexistent_tool' not found"):
            await middleware._call_tool_with_context(
                mock_context, "nonexistent_tool", {}
            )

    @pytest.mark.asyncio
    async def test_call_tool_with_context_tool_call_fails(
        self, middleware, mock_context, sample_tools
    ):
        """Test tool calling when tool call fails."""
        mock_context.fastmcp_context = MockFastMCPContext(sample_tools)

        filters_tool = next(t for t in sample_tools if t.name == "list_gmail_filters")
        filters_tool.call.side_effect = Exception("Tool failed")

        with pytest.raises(Exception, match="Tool failed"):
            await middleware._call_tool_with_context(
                mock_context, "list_gmail_filters", {}
            )

    # ===== Error Response Tests =====

    def test_create_error_response_with_help(self, middleware):
        """Test error response creation with help message."""
        result = middleware._create_error_response("Test error", "Test help")

        assert "text" in result
        assert "Error: Test error" in result["text"]
        assert len(result["contents"]) > 0

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert content["message"] == "Test error"
        assert content["help"] == "Test help"
        assert "timestamp" in content

    def test_create_error_response_without_help(self, middleware):
        """Test error response creation without help message."""
        result = middleware._create_error_response("Test error")

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert content["message"] == "Test error"
        assert "help" not in content

    # ===== Service Metadata Tests =====

    def test_service_metadata_completeness(self, middleware):
        """Test that SERVICE_METADATA contains expected services."""
        expected_services = [
            "gmail",
            "drive",
            "calendar",
            "docs",
            "sheets",
            "chat",
            "forms",
            "slides",
            "photos",
        ]

        for service in expected_services:
            assert service in middleware.SERVICE_METADATA, f"Missing service: {service}"

            service_meta = middleware.SERVICE_METADATA[service]
            assert "display_name" in service_meta
            assert "icon" in service_meta
            assert "description" in service_meta
            assert "list_types" in service_meta

    def test_service_metadata_list_types_structure(self, middleware):
        """Test that list types have proper structure."""
        for service_name, service_meta in middleware.SERVICE_METADATA.items():
            list_types = service_meta.get("list_types", {})

            for list_type_name, list_type_info in list_types.items():
                assert "display_name" in list_type_info
                assert "description" in list_type_info

                # Either list_tool or get_tool should be present
                has_list_tool = list_type_info.get("list_tool") is not None
                has_get_tool = list_type_info.get("get_tool") is not None
                assert has_list_tool or has_get_tool, (
                    f"No tools for {service_name}/{list_type_name}"
                )

                if "id_field" in list_type_info:
                    assert isinstance(list_type_info["id_field"], str)
                    assert list_type_info["id_field"].endswith("_id")

    # ===== Integration Tests =====

    @pytest.mark.asyncio
    @patch("middleware.tag_based_resource_middleware.get_user_email_context")
    async def test_full_workflow_service_lists(
        self, mock_get_user_email, middleware, mock_call_next, sample_tools
    ):
        """Test full workflow for service lists endpoint."""
        mock_get_user_email.return_value = "test@example.com"

        # Setup context
        context = Mock(spec=MiddlewareContext)
        context.message = MockMessage("service://gmail/lists")
        context.fastmcp_context = MockFastMCPContext(sample_tools)

        result = await middleware.on_read_resource(context, mock_call_next)

        # Verify call_next was not called
        mock_call_next.assert_not_called()

        # Verify response structure
        assert "text" in result
        assert "contents" in result

        content = json.loads(result["contents"][0]["text"])
        assert content["service"] == "gmail"
        assert "list_types" in content

    @pytest.mark.asyncio
    @patch("middleware.tag_based_resource_middleware.get_user_email_context")
    async def test_full_workflow_list_items(
        self, mock_get_user_email, middleware, mock_call_next, sample_tools
    ):
        """Test full workflow for list items endpoint."""
        mock_get_user_email.return_value = "test@example.com"

        # Setup context and tool response
        context = Mock(spec=MiddlewareContext)
        context.message = MockMessage("service://gmail/filters")
        context.fastmcp_context = MockFastMCPContext(sample_tools)

        filters_tool = next(t for t in sample_tools if t.name == "list_gmail_filters")
        filters_tool.call.return_value = {"filters": []}

        result = await middleware.on_read_resource(context, mock_call_next)

        # Verify tool was called
        filters_tool.call.assert_called_once_with(user_google_email="test@example.com")

        # Verify response
        content = json.loads(result["contents"][0]["text"])
        assert content["service"] == "gmail"
        assert content["list_type"] == "filters"
        assert content["tool_called"] == "list_gmail_filters"

    @pytest.mark.asyncio
    @patch("middleware.tag_based_resource_middleware.get_user_email_context")
    async def test_full_workflow_specific_item(
        self, mock_get_user_email, middleware, mock_call_next, sample_tools
    ):
        """Test full workflow for specific item endpoint."""
        mock_get_user_email.return_value = "test@example.com"

        # Setup context and tool response
        context = Mock(spec=MiddlewareContext)
        context.message = MockMessage("service://gmail/filters/123")
        context.fastmcp_context = MockFastMCPContext(sample_tools)

        get_tool = next(t for t in sample_tools if t.name == "get_gmail_filter")
        get_tool.call.return_value = {"id": "123", "criteria": {}}

        result = await middleware.on_read_resource(context, mock_call_next)

        # Verify tool was called with correct parameters
        get_tool.call.assert_called_once_with(
            user_google_email="test@example.com", filter_id="123"
        )

        # Verify response
        content = json.loads(result["contents"][0]["text"])
        assert content["service"] == "gmail"
        assert content["list_type"] == "filters"
        assert content["item_id"] == "123"
        assert content["tool_called"] == "get_gmail_filter"

    # ===== Error Handling Edge Cases =====

    @pytest.mark.asyncio
    async def test_exception_handling_in_main_method(
        self, middleware, mock_context, mock_call_next
    ):
        """Test exception handling in main on_read_resource method."""
        # Force an exception in the parsing logic
        mock_context.message.uri = "service://gmail/lists"

        # Mock _handle_service_lists to raise exception
        with patch.object(
            middleware, "_handle_service_lists", side_effect=Exception("Test error")
        ):
            result = await middleware.on_read_resource(mock_context, mock_call_next)

        # Should return error response
        assert "text" in result
        assert "Error:" in result["text"]

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert "Error processing service resource" in content["message"]

    @pytest.mark.asyncio
    async def test_service_root_access_not_implemented(
        self, middleware, mock_context, mock_call_next
    ):
        """Test that service root access returns not implemented error."""
        mock_context.message.uri = "service://gmail"

        result = await middleware.on_read_resource(mock_context, mock_call_next)

        content = json.loads(result["contents"][0]["text"])
        assert content["error"] is True
        assert "Service root access not implemented" in content["message"]
        assert "Use service://{service}/lists" in content["help"]

    # ===== Performance and Initialization Tests =====

    def test_middleware_initialization(self):
        """Test middleware initialization with different settings."""
        # Default initialization
        middleware1 = TagBasedResourceMiddleware()
        assert middleware1.enable_debug_logging is False

        # Debug enabled
        middleware2 = TagBasedResourceMiddleware(enable_debug_logging=True)
        assert middleware2.enable_debug_logging is True

    def test_service_metadata_lookup_performance(self, middleware):
        """Test that service metadata lookup is efficient."""
        # This is a simple performance test
        import time

        start_time = time.time()
        for _ in range(1000):
            # Simulate metadata lookups
            assert "gmail" in middleware.SERVICE_METADATA
            gmail_meta = middleware.SERVICE_METADATA["gmail"]
            assert "list_types" in gmail_meta

        elapsed = time.time() - start_time
        # Should complete lookups very quickly (< 0.1 seconds for 1000 lookups)
        assert elapsed < 0.1, f"Metadata lookups too slow: {elapsed}s"

    # ===== Complex URI Tests =====

    @pytest.mark.asyncio
    async def test_complex_item_ids(self, middleware, mock_context, mock_call_next):
        """Test handling of complex item IDs with special characters."""
        test_ids = [
            "simple_id",
            "id-with-dashes",
            "id.with.dots",
            "id_with_underscores",
            "123456789",
            "mixed_id-123.test",
        ]

        for item_id in test_ids:
            mock_context.message.uri = f"service://gmail/filters/{item_id}"

            result = await middleware.on_read_resource(mock_context, mock_call_next)

            # Should handle gracefully (either process or error appropriately)
            assert "text" in result
            assert "contents" in result

            content = json.loads(result["contents"][0]["text"])
            # Should either succeed or fail with authentication error
            if content.get("error"):
                assert "User email not found" in content["message"]
            else:
                assert content["item_id"] == item_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
