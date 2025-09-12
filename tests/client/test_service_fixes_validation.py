"""
Focused integration tests to validate fixes for service list resources.

This test file specifically validates the fixes made for:
1. Gmail filters - parameter filtering to prevent TypeError
2. Gmail labels - proper tool calling 
3. Calendar events - removing id_field to call real tool instead of returning examples
4. Calendar calendars - ensuring proper functionality

These tests verify that service://{service}/{list_type} resources properly call
the underlying tools and return real data instead of errors or example data.
"""

import pytest
import asyncio
import json
import os
import ssl
import httpx
from typing import Any, Dict, List
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from ..test_auth_utils import get_client_auth_config


# Server configuration - Updated for HTTPS
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8000"))
SERVER_URL = os.getenv("MCP_SERVER_URL", f"https://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")


class TestServiceListResourceFixes:
    """Test service fixes and validation improvements across Google Workspace services.

🔧 MCP Tools Used:
- Service validation tools: Validate service functionality after fixes
- Cross-service testing: Test interactions between different services
- Error recovery: Test improved error handling and recovery mechanisms
- Service health checks: Validate service availability and performance

🧪 What's Being Tested:
- Service bug fixes and regression prevention
- Improved error handling and user experience
- Service reliability and stability improvements
- Cross-service compatibility and integration
- Performance optimizations and efficiency gains
- Validation of service API compliance
- Error recovery and graceful degradation

🔍 Potential Duplications:
- Service testing overlaps with individual service test files
- Validation patterns similar to other validation and compliance tests
- Error handling might overlap with other error handling tests
- Cross-service testing similar to integration tests
"""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        auth_config = get_client_auth_config(TEST_EMAIL)
        
        # Set environment variables to disable SSL verification
        original_verify = os.environ.get('HTTPX_VERIFY')
        original_ssl_verify = os.environ.get('SSL_VERIFY')
        
        os.environ['HTTPX_VERIFY'] = 'false'
        os.environ['SSL_VERIFY'] = 'false'
        
        try:
            # Create transport
            transport = StreamableHttpTransport(
                SERVER_URL,
                auth=auth_config
            )
            
            client = Client(transport)
            async with client:
                yield client
        finally:
            # Restore original environment
            if original_verify is not None:
                os.environ['HTTPX_VERIFY'] = original_verify
            else:
                os.environ.pop('HTTPX_VERIFY', None)
                
            if original_ssl_verify is not None:
                os.environ['SSL_VERIFY'] = original_ssl_verify
            else:
                os.environ.pop('SSL_VERIFY', None)
    
    @pytest.mark.asyncio
    async def test_gmail_filters_no_parameter_error(self, client):
        """Test that Gmail filters resource doesn't throw parameter errors."""
        # Get the service lists to ensure filters is available
        content = await client.read_resource("service://gmail/lists")
        data = json.loads(content[0].text)
        
        # Verify filters is in the list types
        list_types = [lt["name"] for lt in data.get("list_types", [])]
        assert "filters" in list_types, "Gmail filters should be available"
        
        # Try to access the filters resource - this previously caused TypeError
        content = await client.read_resource("service://gmail/filters")
        data = json.loads(content[0].text)
        
        # Should not have a TypeError - either success or auth error
        if "error" in data:
            # Should be auth error, not parameter error
            error_msg = data["error"].lower()
            assert "typeerror" not in error_msg, f"Got TypeError: {data['error']}"
            assert "parameter" not in error_msg or "auth" in error_msg, f"Should be auth error: {data['error']}"
        else:
            # Success - should have proper structure
            assert "service" in data
            assert data["service"] == "gmail"
            assert "list_type" in data
            assert data["list_type"] == "filters"
    
    @pytest.mark.asyncio
    async def test_gmail_labels_working(self, client):
        """Test that Gmail labels resource works correctly."""
        # Check service lists includes labels
        content = await client.read_resource("service://gmail/lists")
        data = json.loads(content[0].text)
        
        list_types = [lt["name"] for lt in data.get("list_types", [])]
        assert "labels" in list_types, "Gmail labels should be available"
        
        # Try to access the labels resource
        content = await client.read_resource("service://gmail/labels")
        data = json.loads(content[0].text)
        
        # Should not have parameter errors
        if "error" in data:
            error_msg = data["error"].lower()
            assert "typeerror" not in error_msg, f"Got TypeError: {data['error']}"
            assert "parameter" not in error_msg or "auth" in error_msg, f"Should be auth error: {data['error']}"
        else:
            # Success - should have proper structure
            assert "service" in data
            assert data["service"] == "gmail"
            assert "list_type" in data
            assert data["list_type"] == "labels"
    
    @pytest.mark.asyncio 
    async def test_calendar_events_returns_real_data_not_examples(self, client):
        """Test that calendar events calls real tool instead of returning example data."""
        # Check service lists includes events
        content = await client.read_resource("service://calendar/lists")
        data = json.loads(content[0].text)
        
        list_types = [lt["name"] for lt in data.get("list_types", [])]
        assert "events" in list_types, "Calendar events should be available"
        
        # Try to access the events resource
        content = await client.read_resource("service://calendar/events")
        data = json.loads(content[0].text)
        
        # Should not return example data with is_example=True
        if "items" in data and data["items"]:
            for item in data["items"]:
                if isinstance(item, dict):
                    # Should not have example flag
                    assert not item.get("is_example", False), "Should not return example data"
                    # Should not have example IDs from config
                    if "id" in item:
                        assert item["id"] not in ["event_123abc", "recurring_456def"], "Should not return config example IDs"
        
        # Should either succeed with real data or have auth error
        if "error" in data:
            error_msg = data["error"].lower()
            # Should be auth error, not "no default IDs" or similar
            assert "example" not in error_msg, f"Should not return example data error: {data['error']}"
            assert "id" not in error_msg or "auth" in error_msg, f"Should be auth error: {data['error']}"
        else:
            # Success - should have proper structure
            assert "service" in data
            assert data["service"] == "calendar"
            assert "list_type" in data
            assert data["list_type"] == "events"
    
    @pytest.mark.asyncio
    async def test_calendar_calendars_working(self, client):
        """Test that calendar calendars resource works correctly."""
        # Check service lists includes calendars
        content = await client.read_resource("service://calendar/lists")
        data = json.loads(content[0].text)
        
        list_types = [lt["name"] for lt in data.get("list_types", [])]
        assert "calendars" in list_types, "Calendar calendars should be available"
        
        # Try to access the calendars resource  
        content = await client.read_resource("service://calendar/calendars")
        data = json.loads(content[0].text)
        
        # Should not have parameter errors
        if "error" in data:
            error_msg = data["error"].lower()
            assert "typeerror" not in error_msg, f"Got TypeError: {data['error']}"
            assert "parameter" not in error_msg or "auth" in error_msg, f"Should be auth error: {data['error']}"
        else:
            # Success - should have proper structure
            assert "service" in data
            assert data["service"] == "calendar"
            assert "list_type" in data
            assert data["list_type"] == "calendars"
    
    @pytest.mark.asyncio
    async def test_configuration_correctness(self, client):
        """Test that the tool configurations have been fixed correctly."""
        # Test Gmail filters configuration
        content = await client.read_resource("service://gmail/lists")
        data = json.loads(content[0].text)
        
        filters_config = next(
            (lt for lt in data.get("list_types", []) if lt["name"] == "filters"),
            None
        )
        assert filters_config is not None, "Gmail filters config should exist"
        # Filters should not require an ID field
        assert not filters_config.get("has_detail_view", True), "Filters should not require ID"
        
        # Test Gmail labels configuration  
        labels_config = next(
            (lt for lt in data.get("list_types", []) if lt["name"] == "labels"),
            None
        )
        assert labels_config is not None, "Gmail labels config should exist"
        
        # Test Calendar configuration
        content = await client.read_resource("service://calendar/lists")
        data = json.loads(content[0].text)
        
        events_config = next(
            (lt for lt in data.get("list_types", []) if lt["name"] == "events"), 
            None
        )
        assert events_config is not None, "Calendar events config should exist"
        # Events should now NOT require an ID (we removed id_field)
        # The has_detail_view should be False since we set id_field to None
        
        calendars_config = next(
            (lt for lt in data.get("list_types", []) if lt["name"] == "calendars"),
            None  
        )
        assert calendars_config is not None, "Calendar calendars config should exist"
    
    @pytest.mark.asyncio
    async def test_tools_exist_and_callable(self, client):
        """Test that the underlying tools exist and are properly configured."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Test that required tools exist
        required_tools = [
            "list_gmail_filters",
            "list_gmail_labels", 
            "list_events",
            "list_calendars"
        ]
        
        for tool_name in required_tools:
            assert tool_name in tool_names, f"Tool {tool_name} should be available"
            
            # Get the tool details
            tool = next((t for t in tools if t.name == tool_name), None)
            assert tool is not None, f"Tool {tool_name} should be found"
            
            # Tool should have proper schema
            assert hasattr(tool, 'inputSchema'), f"Tool {tool_name} should have input schema"
            assert tool.inputSchema is not None, f"Tool {tool_name} should have non-null input schema"
    
    @pytest.mark.asyncio 
    async def test_direct_tool_calls_work(self, client):
        """Test that we can call the underlying tools directly to verify they work."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Test direct tool calls with proper parameters
        if "list_gmail_filters" in tool_names:
            try:
                result = await client.call_tool("list_gmail_filters", {
                    "user_google_email": TEST_EMAIL
                })
                # Should get some result (even if auth error)
                assert result is not None
            except Exception as e:
                # Should not be a parameter error
                assert "parameter" not in str(e).lower() or "auth" in str(e).lower()
        
        if "list_gmail_labels" in tool_names:
            try:
                result = await client.call_tool("list_gmail_labels", {
                    "user_google_email": TEST_EMAIL
                })
                assert result is not None
            except Exception as e:
                assert "parameter" not in str(e).lower() or "auth" in str(e).lower()
        
        if "list_events" in tool_names:
            try:
                result = await client.call_tool("list_events", {
                    "user_google_email": TEST_EMAIL
                })
                assert result is not None
            except Exception as e:
                assert "parameter" not in str(e).lower() or "auth" in str(e).lower()
        
        if "list_calendars" in tool_names:
            try:
                result = await client.call_tool("list_calendars", {
                    "user_google_email": TEST_EMAIL
                })
                assert result is not None
            except Exception as e:
                assert "parameter" not in str(e).lower() or "auth" in str(e).lower()


class TestServiceListResourceErrorHandling:
    """Test that error handling is consistent and helpful."""
    
    # Use standardized client fixture from conftest.py
    # Note: This test class may need special SSL configuration if issues arise
    
    @pytest.mark.asyncio
    async def test_helpful_error_messages(self, client):
        """Test that error messages are helpful and not internal errors."""
        test_cases = [
            "service://gmail/filters",
            "service://gmail/labels",
            "service://calendar/events", 
            "service://calendar/calendars"
        ]
        
        for resource_uri in test_cases:
            content = await client.read_resource(resource_uri)
            data = json.loads(content[0].text)
            
            if "error" in data:
                error_msg = data["error"]
                
                # Should not be internal errors
                assert "TypeError" not in error_msg, f"Should not expose TypeError: {error_msg}"
                assert "AttributeError" not in error_msg, f"Should not expose AttributeError: {error_msg}"
                assert "traceback" not in error_msg.lower(), f"Should not expose traceback: {error_msg}"
                
                # Should be user-friendly
                assert len(error_msg) > 10, f"Error message too short: {error_msg}"
                
                # Should have helpful suggestions if auth error
                if "auth" in error_msg.lower() or "email" in error_msg.lower():
                    assert "suggestions" in data, f"Auth errors should have suggestions"
                    assert len(data["suggestions"]) > 0, f"Should have at least one suggestion"


if __name__ == "__main__":
    # Run tests with asyncio
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])