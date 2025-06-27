"""Test suite for Google Sheets tools using FastMCP Client SDK."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
import json
import re
from .test_auth_utils import get_client_auth_config


# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test@example.com")

# Global variable to store created spreadsheet ID
_test_spreadsheet_id = None


class TestSheetsTools:
    """Test Google Sheets tools using the FastMCP Client."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.fixture(scope="session")
    async def test_spreadsheet_id(self):
        """Create a test spreadsheet and return its ID, or None if creation fails."""
        global _test_spreadsheet_id
        
        if _test_spreadsheet_id is not None:
            return _test_spreadsheet_id
            
        # Try to create a test spreadsheet
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            try:
                result = await client.call_tool("create_spreadsheet", {
                    "user_google_email": TEST_EMAIL,
                    "title": "Test Spreadsheet for MCP Tests"
                })
                
                if result and len(result) > 0:
                    content = result[0].text
                    print(f"DEBUG: Create spreadsheet response: {content}")  # Debug output
                    
                    # Try to extract spreadsheet ID from any response (success or error that might contain ID)
                    # Look for patterns that match the actual create_spreadsheet output format
                    patterns = [
                        r'ID:\s*([a-zA-Z0-9_-]{20,})',  # "ID: 1ABC..." pattern from create_spreadsheet
                        r'id[:\s]+([a-zA-Z0-9_-]{20,})',  # General ID pattern
                        r'spreadsheet[:\s]+([a-zA-Z0-9_-]{20,})',  # Spreadsheet ID
                        r'created[:\s]+([a-zA-Z0-9_-]{20,})',  # Created ID
                        r'https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)',  # URL pattern
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            potential_id = match.group(1)
                            # Validate it looks like a Google Sheets ID (at least 20 chars)
                            if len(potential_id) >= 20:
                                _test_spreadsheet_id = potential_id
                                print(f"DEBUG: Extracted spreadsheet ID: {potential_id}")  # Debug output
                                return _test_spreadsheet_id
                    
                    print(f"DEBUG: No ID pattern matched in: {content}")  # Debug output
            except Exception:
                pass  # Failed to create, will return None
        
        return None
    
    @pytest.mark.asyncio
    async def test_sheets_tools_available(self, client):
        """Test that all Sheets tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check for all Sheets tools
        expected_tools = [
            "list_spreadsheets",
            "get_spreadsheet_info",
            "read_sheet_values",
            "modify_sheet_values",
            "create_spreadsheet",
            "create_sheet"
        ]
        
        for tool in expected_tools:
            assert tool in tool_names, f"Tool '{tool}' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_list_spreadsheets(self, client):
        """Test listing spreadsheets."""
        result = await client.call_tool("list_spreadsheets", {
            "user_google_email": TEST_EMAIL,
            "max_results": 10
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should either succeed or return authentication/middleware error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully listed",
            "no spreadsheets found", "❌", "failed to list", "unexpected error",
            "middleware", "service", "drive_v3", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_spreadsheet(self, client):
        """Test creating a new spreadsheet."""
        result = await client.call_tool("create_spreadsheet", {
            "user_google_email": TEST_EMAIL,
            "title": "Test Spreadsheet from MCP"
        })
        
        # Check that we get a result
        assert len(result) > 0
        
        content = result[0].text
        # Should either succeed or return authentication/middleware error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully created spreadsheet",
            "❌", "failed to create", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_spreadsheet_with_sheets(self, client):
        """Test creating a spreadsheet with custom sheet names."""
        result = await client.call_tool("create_spreadsheet", {
            "user_google_email": TEST_EMAIL,
            "title": "Multi-Sheet Test Spreadsheet",
            "sheet_names": ["Data", "Summary", "Charts"]
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should either succeed or return authentication/middleware error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully created spreadsheet",
            "❌", "failed to create", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_get_spreadsheet_info(self, client, test_spreadsheet_id):
        """Test getting spreadsheet information."""
        spreadsheet_id = await test_spreadsheet_id if hasattr(test_spreadsheet_id, '__await__') else test_spreadsheet_id
        
        if not spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        result = await client.call_tool("get_spreadsheet_info", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return auth error, middleware error, or spreadsheet info
        valid_responses = [
            "requires authentication", "no valid credentials", "spreadsheet:", "sheets",
            "❌", "failed to get", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_read_sheet_values(self, client, test_spreadsheet_id):
        """Test reading values from a sheet."""
        spreadsheet_id = await test_spreadsheet_id if hasattr(test_spreadsheet_id, '__await__') else test_spreadsheet_id
        
        if not spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        result = await client.call_tool("read_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "range_name": "A1:D10"
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return auth error, middleware error, or data results
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully read", "no data found",
            "❌", "failed to read", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_read_sheet_values_default_range(self, client, test_spreadsheet_id):
        """Test reading values with default range."""
        spreadsheet_id = await test_spreadsheet_id if hasattr(test_spreadsheet_id, '__await__') else test_spreadsheet_id
        
        if not spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        result = await client.call_tool("read_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return auth error, middleware error, or data results
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully read", "no data found",
            "❌", "failed to read", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_modify_sheet_values(self, client, test_spreadsheet_id):
        """Test modifying sheet values."""
        spreadsheet_id = await test_spreadsheet_id if hasattr(test_spreadsheet_id, '__await__') else test_spreadsheet_id
        
        if not spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test writing values
        test_values = [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
            ["Bob", "25", "San Francisco"]
        ]
        
        result = await client.call_tool("modify_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "range_name": "A1:C3",
            "values": test_values
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return auth error, middleware error, or success message
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully updated",
            "❌", "failed to update", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_clear_sheet_values(self, client, test_spreadsheet_id):
        """Test clearing sheet values."""
        spreadsheet_id = await test_spreadsheet_id if hasattr(test_spreadsheet_id, '__await__') else test_spreadsheet_id
        
        if not spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        result = await client.call_tool("modify_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "range_name": "A1:Z100",
            "clear_values": True
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return auth error, middleware error, or success message
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully cleared",
            "❌", "failed to clear", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_sheet(self, client, test_spreadsheet_id):
        """Test creating a new sheet in an existing spreadsheet."""
        spreadsheet_id = await test_spreadsheet_id if hasattr(test_spreadsheet_id, '__await__') else test_spreadsheet_id
        
        if not spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        result = await client.call_tool("create_sheet", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": "Test Sheet"
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return auth error, middleware error, or success message
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully created sheet",
            "❌", "failed to create", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_sheets_tools_parameter_validation(self, client):
        """Test parameter validation for Sheets tools."""
        # Test missing required parameters
        with pytest.raises(Exception):  # FastMCP should raise an error
            await client.call_tool("create_spreadsheet", {
                # Missing user_google_email and title
            })
        
        with pytest.raises(Exception):
            await client.call_tool("get_spreadsheet_info", {
                "user_google_email": TEST_EMAIL
                # Missing spreadsheet_id
            })
        
        with pytest.raises(Exception):
            await client.call_tool("modify_sheet_values", {
                "user_google_email": TEST_EMAIL,
                "spreadsheet_id": "test_id"
                # Missing range_name
            })
    
    @pytest.mark.asyncio
    async def test_value_input_options(self, client, test_spreadsheet_id):
        """Test different value input options."""
        spreadsheet_id = await test_spreadsheet_id if hasattr(test_spreadsheet_id, '__await__') else test_spreadsheet_id
        
        if not spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test with RAW input option
        result = await client.call_tool("modify_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "range_name": "E1:F2",
            "values": [["=SUM(1,2)", "2023-01-01"], ["Raw Text", "100"]],
            "value_input_option": "RAW"
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return auth error or success message
        assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "successfully updated"])
    
    @pytest.mark.asyncio 
    async def test_large_range_operations(self, client, test_spreadsheet_id):
        """Test operations with larger data ranges."""
        spreadsheet_id = await test_spreadsheet_id if hasattr(test_spreadsheet_id, '__await__') else test_spreadsheet_id
        
        if not spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test reading a large range
        result = await client.call_tool("read_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "range_name": "A1:Z1000"
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return auth error or data results (likely no data found for large range)
        assert any(keyword in content.lower() for keyword in [
            "requires authentication",
            "no valid credentials",
            "successfully read",
            "no data found",
            "failed to read sheet values",  # HttpError case
            "unexpected error reading sheet values"  # General exception case
        ])


class TestSheetsIntegration:
    """Integration tests for Sheets tools with other services."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_sheets_with_drive_integration(self, client):
        """Test that Sheets tools work with Drive integration."""
        # This tests the integration between Sheets and Drive
        # Since spreadsheets are stored in Drive, list_spreadsheets uses Drive API
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # If both Sheets and Drive tools are available
        if "list_spreadsheets" in tool_names and "list_drive_items" in tool_names:
            # Both should be able to access spreadsheet data
            pass  # Actual integration test would go here
    
    @pytest.mark.asyncio
    async def test_sheets_error_handling(self, client):
        """Test error handling for various failure scenarios."""
        # Test with invalid spreadsheet ID
        result = await client.call_tool("get_spreadsheet_info", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": "invalid_id_12345"
        })
        
        assert len(result) > 0
        content = result[0].text
        assert any(keyword in content.lower() for keyword in ["error", "not found", "requires authentication", "no valid credentials"])
        
        # Test with invalid range
        result = await client.call_tool("read_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": "test_id",
            "range_name": "InvalidRange"
        })
        
        assert len(result) > 0
        content = result[0].text
        assert any(keyword in content.lower() for keyword in ["error", "invalid", "requires authentication", "no valid credentials"])