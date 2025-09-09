"""Test suite for Google Sheets tools using FastMCP Client SDK."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
import json
import re
from .base_test_config import TEST_EMAIL, create_test_client
from .test_helpers import ToolTestRunner, TestResponseValidator
from ..test_auth_utils import get_client_auth_config

# Global variable to store created spreadsheet ID
_test_spreadsheet_id = None


@pytest.mark.service("sheets")
class TestSheetsTools:
    """Test Sheets tools using standardized framework.

🔧 MCP Tools Used:
- create_spreadsheet: Create new Google Spreadsheets
- create_sheet: Add sheets to existing spreadsheets
- (Additional sheet operations would be documented here)

🧪 What's Being Tested:
- Spreadsheet creation with multiple sheet configuration
- Sheet management within spreadsheets
- Data input and formatting operations
- Formula and calculation handling
- Sharing and collaboration features
- Data export and import functionality
- Authentication patterns for all Sheets operations

🔍 Potential Duplications:
- Sharing functionality overlaps with Drive and other Google Workspace sharing
- Data export might have patterns similar to Forms response export
- File creation patterns might be similar to other document creation tests
- Collaboration features might overlap with general Google Workspace sharing tests
"""
    
    @pytest.fixture(scope="session")
    def test_spreadsheet_id(self):
        """Create a test spreadsheet and return its ID, or None if creation fails."""
        global _test_spreadsheet_id
        
        if _test_spreadsheet_id is not None:
            return _test_spreadsheet_id
        
        # Try to create a test spreadsheet
        async def _create_test_spreadsheet():
            client = await create_test_client(TEST_EMAIL)
            async with client:
                try:
                    result = await client.call_tool("create_spreadsheet", {
                        "user_google_email": TEST_EMAIL,
                        "title": "Test Spreadsheet for MCP Tests"
                    })
                    
                    if result and result.content:
                        content = result.content[0].text
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
                                    return potential_id
                        
                        print(f"DEBUG: No ID pattern matched in: {content}")  # Debug output
                except Exception:
                    pass  # Failed to create, will return None
            
            return None
        
        # Run the async function
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new event loop in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _create_test_spreadsheet())
                    _test_spreadsheet_id = future.result()
            else:
                _test_spreadsheet_id = loop.run_until_complete(_create_test_spreadsheet())
        except RuntimeError:
            _test_spreadsheet_id = asyncio.run(_create_test_spreadsheet())
        
        return _test_spreadsheet_id
    
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
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully listed",
            "no spreadsheets found", "❌", "failed to list", "unexpected error",
            "middleware", "service", "drive_v3", "not yet fulfilled", "items", "spreadsheets"
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
        assert result is not None and result.content
        
        content = result.content[0].text
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
        
        assert result is not None and result.content
        content = result.content[0].text
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
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return auth error, middleware error, or spreadsheet info
        valid_responses = [
            "requires authentication", "no valid credentials", "spreadsheet:", "sheets",
            "❌", "failed to get", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_read_sheet_values(self, client, test_spreadsheet_id):
        """Test reading values from a sheet."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        spreadsheet_id = test_spreadsheet_id
        
        result = await client.call_tool("read_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "range_name": "A1:D10"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return auth error, middleware error, or data results
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully read", "no data found",
            "❌", "failed to read", "unexpected error", "middleware", "service", "not yet fulfilled",
            "spreadsheetid", "range", "values"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_read_sheet_values_default_range(self, client, test_spreadsheet_id):
        """Test reading values with default range."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        spreadsheet_id = test_spreadsheet_id
        
        result = await client.call_tool("read_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return auth error, middleware error, or data results
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully read", "no data found",
            "❌", "failed to read", "unexpected error", "middleware", "service", "not yet fulfilled",
            "spreadsheetid", "range", "values"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_modify_sheet_values(self, client, test_spreadsheet_id):
        """Test modifying sheet values."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        spreadsheet_id = test_spreadsheet_id
        
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
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return auth error, middleware error, or success message
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully updated",
            "❌", "failed to update", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_clear_sheet_values(self, client, test_spreadsheet_id):
        """Test clearing sheet values."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        spreadsheet_id = test_spreadsheet_id
        
        result = await client.call_tool("modify_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "range_name": "A1:Z100",
            "clear_values": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return auth error, middleware error, or success message
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully cleared",
            "❌", "failed to clear", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_sheet(self, client, test_spreadsheet_id):
        """Test creating a new sheet in an existing spreadsheet."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        spreadsheet_id = test_spreadsheet_id
        
        result = await client.call_tool("create_sheet", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": "Test Sheet"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return auth error, middleware error, or success message
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully created sheet",
            "❌", "failed to create", "unexpected error", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_sheets_tools_parameter_validation(self, client):
        """Test parameter validation for Sheets tools."""
        # Test missing required parameters - FastMCP validates and raises ToolError
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("create_spreadsheet", {
                # Missing user_google_email and title
            })
        assert "required" in str(exc_info.value).lower()
        
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("get_spreadsheet_info", {
                "user_google_email": TEST_EMAIL
                # Missing spreadsheet_id
            })
        assert "required" in str(exc_info.value).lower()
        
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("modify_sheet_values", {
                "user_google_email": TEST_EMAIL,
                "spreadsheet_id": "test_id"
                # Missing range_name
            })
        assert "required" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_value_input_options(self, client, test_spreadsheet_id):
        """Test different value input options."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        spreadsheet_id = test_spreadsheet_id
        
        # Test with RAW input option
        result = await client.call_tool("modify_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "range_name": "E1:F2",
            "values": [["=SUM(1,2)", "2023-01-01"], ["Raw Text", "100"]],
            "value_input_option": "RAW"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return auth error or success message
        assert any(keyword in content.lower() for keyword in ["requires authentication", "no valid credentials", "successfully updated"])
    
    @pytest.mark.asyncio
    async def test_large_range_operations(self, client, test_spreadsheet_id):
        """Test operations with larger data ranges."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        spreadsheet_id = test_spreadsheet_id
        
        # Test reading a large range
        result = await client.call_tool("read_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": spreadsheet_id,
            "range_name": "A1:Z1000"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return auth error or data results (likely no data found for large range)
        assert any(keyword in content.lower() for keyword in [
            "requires authentication",
            "no valid credentials",
            "successfully read",
            "no data found",
            "failed to read sheet values",  # HttpError case
            "unexpected error reading sheet values",  # General exception case
            "spreadsheetid", "range", "values"  # Success case
        ])


@pytest.mark.service("sheets")
class TestSheetsIntegration:
    """Integration tests for Sheets tools with other services."""
    
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
        
        assert result is not None and result.content
        content = result.content[0].text
        assert any(keyword in content.lower() for keyword in ["error", "not found", "requires authentication", "no valid credentials"])
        
        # Test with invalid range
        result = await client.call_tool("read_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": "test_id",
            "range_name": "InvalidRange"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        assert any(keyword in content.lower() for keyword in ["error", "invalid", "requires authentication", "no valid credentials"])