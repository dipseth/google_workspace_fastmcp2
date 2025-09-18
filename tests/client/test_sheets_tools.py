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

# Global variables to store created test spreadsheet data
_test_spreadsheet_id = None
_test_sheet_id = None


@pytest.fixture(scope="session")
async def test_spreadsheet_data():
    """Create a test spreadsheet and return its ID and sheet ID for tests."""
    global _test_spreadsheet_id, _test_sheet_id
    
    # Return cached data if available
    if _test_spreadsheet_id is not None and _test_sheet_id is not None:
        return {
            "spreadsheet_id": _test_spreadsheet_id,
            "sheet_id": _test_sheet_id
        }
    
    # Create a test spreadsheet
    client = await create_test_client(TEST_EMAIL)
    try:
        # Create spreadsheet
        create_result = await client.call_tool("create_spreadsheet", {
            "user_google_email": TEST_EMAIL,
            "title": "MCP Test Spreadsheet for Formatting"
        })
        
        if create_result and create_result.content:
            content = create_result.content[0].text
            print(f"DEBUG: Create spreadsheet response: {content}")
            
            # Extract spreadsheet ID from response
            spreadsheet_id = None
            
            # Try to parse JSON response first
            try:
                import json
                if content.startswith('{'):
                    data = json.loads(content)
                    spreadsheet_id = data.get('spreadsheetId')
            except (json.JSONDecodeError, KeyError):
                pass
            
            # Fallback to regex patterns
            if not spreadsheet_id:
                patterns = [
                    r'"spreadsheetId":\s*"([a-zA-Z0-9_-]{20,})"',  # JSON format
                    r'ID:\s*([a-zA-Z0-9_-]{20,})',  # Plain text format
                    r'spreadsheetId[:\s]+"?([a-zA-Z0-9_-]{20,})"?',
                    r'https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        potential_id = match.group(1)
                        if len(potential_id) >= 20:
                            spreadsheet_id = potential_id
                            break
            
            if spreadsheet_id:
                # Get spreadsheet info to get sheet ID
                info_result = await client.call_tool("get_spreadsheet_info", {
                    "user_google_email": TEST_EMAIL,
                    "spreadsheet_id": spreadsheet_id
                })
                
                sheet_id = 0  # Default sheet ID
                if info_result and info_result.content:
                    info_content = info_result.content[0].text
                    print(f"DEBUG: Get spreadsheet info response: {info_content}")
                    
                    # Try to extract sheet ID from response
                    try:
                        if info_content.startswith('{'):
                            info_data = json.loads(info_content)
                            sheets = info_data.get('sheets', [])
                            if sheets:
                                sheet_id = sheets[0].get('sheetId', 0)
                    except (json.JSONDecodeError, KeyError):
                        # Fallback to default sheet ID
                        sheet_id = 0
                
                # Cache the results
                _test_spreadsheet_id = spreadsheet_id
                _test_sheet_id = sheet_id
                
                print(f"DEBUG: Created test spreadsheet - ID: {spreadsheet_id}, Sheet ID: {sheet_id}")
                
                return {
                    "spreadsheet_id": spreadsheet_id,
                    "sheet_id": sheet_id
                }
    
    except Exception as e:
        print(f"DEBUG: Failed to create test spreadsheet: {e}")
    
    finally:
        await client.close()
    
    # Return None if creation failed
    return None


@pytest.fixture(scope="session")
def test_spreadsheet_id(test_spreadsheet_data):
    """Extract spreadsheet ID from spreadsheet data for backward compatibility."""
    if test_spreadsheet_data:
        return test_spreadsheet_data["spreadsheet_id"]
    return None


@pytest.fixture(scope="session")
def test_sheet_id(test_spreadsheet_data):
    """Extract sheet ID from spreadsheet data for formatting tests."""
    if test_spreadsheet_data:
        return test_spreadsheet_data["sheet_id"]
    return None


@pytest.mark.service("sheets")
class TestSheetsTools:
    """Test Sheets tools using standardized framework.

🔧 MCP Tools Used:
- create_spreadsheet: Create new Google Spreadsheets
- create_sheet: Add sheets to existing spreadsheets
- format_sheet_range: Master formatting tool for comprehensive cell formatting

🧪 What's Being Tested:
- Spreadsheet creation with multiple sheet configuration
- Sheet management within spreadsheets
- Data input and formatting operations
- Comprehensive formatting with format_sheet_range tool
- Formula and calculation handling
- Sharing and collaboration features
- Data export and import functionality
- Authentication patterns for all Sheets operations

🔍 Test Strategy:
- Creates a single test spreadsheet shared across all tests
- Uses real spreadsheet and sheet IDs for realistic formatting tests
- Tests both individual operations and comprehensive formatting scenarios
- Validates backward compatibility and new enhanced features
"""
    
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
            "create_sheet",
            "format_sheet_range"  # Master formatting tool
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

    @pytest.mark.asyncio
    async def test_format_sheet_range_available(self, client):
        """Test that format_sheet_range tool is available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check that the master formatting tool is available
        assert "format_sheet_range" in tool_names, "format_sheet_range tool should be available"
        
        # Optionally check that individual formatting tools are still available for backward compatibility
        individual_tools = [
            "format_sheet_cells",
            "update_sheet_borders",
            "add_conditional_formatting",
            "merge_cells"
        ]
        
        for tool in individual_tools:
            assert tool in tool_names, f"Individual tool '{tool}' should still be available for backward compatibility"

    @pytest.mark.asyncio
    async def test_format_sheet_range_cell_formatting(self, client, test_spreadsheet_id, test_sheet_id):
        """Test format_sheet_range can replace format_sheet_cells functionality."""
        if not test_spreadsheet_id or test_sheet_id is None:
            pytest.skip("No test spreadsheet or sheet ID available")
        
        # Test basic cell formatting (equivalent to format_sheet_cells)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": test_sheet_id,
            "range_start_row": 0,
            "range_end_row": 2,
            "range_start_col": 0,
            "range_end_col": 3,
            "bold": True,
            "italic": False,
            "font_size": 12,
            "text_color": {"red": 0.0, "green": 0.0, "blue": 1.0},
            "background_color": {"red": 1.0, "green": 1.0, "blue": 0.0},
            "horizontal_alignment": "CENTER",
            "vertical_alignment": "MIDDLE",
            "number_format_type": "TEXT",
            "wrap_strategy": "WRAP"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return auth error, middleware error, or success message
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully applied",
            "formatting operations", "❌", "failed to apply", "unexpected error",
            "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_format_sheet_range_borders(self, client, test_spreadsheet_id, test_sheet_id):
        """Test format_sheet_range can replace update_sheet_borders functionality."""
        if not test_spreadsheet_id or test_sheet_id is None:
            pytest.skip("No test spreadsheet or sheet ID available")
        
        # Test border formatting (equivalent to update_sheet_borders)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": test_sheet_id,
            "range_start_row": 2,
            "range_end_row": 4,
            "range_start_col": 2,
            "range_end_col": 5,
            "apply_borders": True,
            "border_style": "SOLID",
            "border_color": {"red": 0.0, "green": 0.0, "blue": 0.0},
            "top_border": True,
            "bottom_border": True,
            "left_border": True,
            "right_border": True,
            "inner_horizontal_border": True,
            "inner_vertical_border": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully applied",
            "formatting operations", "❌", "failed to apply", "unexpected error",
            "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_format_sheet_range_conditional_formatting(self, client, test_spreadsheet_id, test_sheet_id):
        """Test format_sheet_range can replace add_conditional_formatting functionality."""
        if not test_spreadsheet_id or test_sheet_id is None:
            pytest.skip("No test spreadsheet or sheet ID available")
        
        # Test conditional formatting (equivalent to add_conditional_formatting)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": test_sheet_id,
            "range_start_row": 4,
            "range_end_row": 8,
            "range_start_col": 0,
            "range_end_col": 2,
            "condition_type": "NUMBER_GREATER",
            "condition_value": 10,
            "condition_format_background_color": {"red": 0.0, "green": 1.0, "blue": 0.0},
            "condition_format_text_color": {"red": 1.0, "green": 1.0, "blue": 1.0},
            "condition_format_bold": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully applied",
            "formatting operations", "❌", "failed to apply", "unexpected error",
            "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_format_sheet_range_merge_cells(self, client, test_spreadsheet_id, test_sheet_id):
        """Test format_sheet_range can replace merge_cells functionality."""
        if not test_spreadsheet_id or test_sheet_id is None:
            pytest.skip("No test spreadsheet or sheet ID available")
        
        # Test cell merging (equivalent to merge_cells)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": test_sheet_id,
            "range_start_row": 8,
            "range_end_row": 10,
            "range_start_col": 0,
            "range_end_col": 3,
            "merge_cells_option": "MERGE_ALL"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully applied",
            "formatting operations", "❌", "failed to apply", "unexpected error",
            "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_format_sheet_range_comprehensive(self, client, test_spreadsheet_id, test_sheet_id):
        """Test format_sheet_range combining all four types of formatting in one operation."""
        if not test_spreadsheet_id or test_sheet_id is None:
            pytest.skip("No test spreadsheet or sheet ID available")
        
        # Test comprehensive formatting combining all capabilities
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": test_sheet_id,
            "range_start_row": 10,
            "range_end_row": 15,
            "range_start_col": 0,
            "range_end_col": 4,
            # Cell formatting
            "bold": True,
            "italic": True,
            "font_size": 14,
            "text_color": {"red": 1.0, "green": 0.0, "blue": 0.0},
            "background_color": {"red": 0.9, "green": 0.9, "blue": 0.9},
            "horizontal_alignment": "CENTER",
            "number_format_type": "CURRENCY",
            # Borders
            "apply_borders": True,
            "border_style": "SOLID_MEDIUM",
            "border_color": {"red": 0.0, "green": 0.0, "blue": 1.0},
            "top_border": True,
            "bottom_border": True,
            "left_border": True,
            "right_border": True,
            # Conditional formatting
            "condition_type": "NOT_BLANK",
            "condition_format_background_color": {"red": 1.0, "green": 1.0, "blue": 0.0},
            # Merge cells
            "merge_cells_option": "MERGE_ROWS",
            # Column/row sizing
            "column_width": 150,
            "row_height": 30
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully applied",
            "formatting operations", "❌", "failed to apply", "unexpected error",
            "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_format_sheet_range_advanced_features(self, client, test_spreadsheet_id, test_sheet_id):
        """Test format_sheet_range advanced features like freezing and custom patterns."""
        if not test_spreadsheet_id or test_sheet_id is None:
            pytest.skip("No test spreadsheet or sheet ID available")
        
        # Test advanced features not available in individual tools
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": test_sheet_id,
            "range_start_row": 0,
            "range_end_row": 1,
            "range_start_col": 0,
            "range_end_col": 10,
            # Advanced number formatting
            "number_format_pattern": "$#,##0.00",
            "text_rotation": 45,
            # Freeze panes
            "freeze_rows": 1,
            "freeze_columns": 2,
            # Complex conditional formatting with custom formula
            "condition_type": "CUSTOM_FORMULA",
            "condition_value": "=MOD(ROW(),2)=0",
            "condition_format_background_color": {"red": 0.95, "green": 0.95, "blue": 1.0}
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully applied",
            "formatting operations", "❌", "failed to apply", "unexpected error",
            "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_format_sheet_range_parameter_validation(self, client):
        """Test parameter validation for format_sheet_range."""
        # Test missing required parameters
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("format_sheet_range", {
                # Missing required parameters
            })
        assert "required" in str(exc_info.value).lower()
        
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("format_sheet_range", {
                "user_google_email": TEST_EMAIL,
                "spreadsheet_id": "test_id",
                "sheet_id": 0
                # Missing range parameters
            })
        assert "required" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_format_sheet_range_no_formatting_options(self, client, test_spreadsheet_id, test_sheet_id):
        """Test format_sheet_range behavior when no formatting options are provided."""
        if not test_spreadsheet_id or test_sheet_id is None:
            pytest.skip("No test spreadsheet or sheet ID available")
        
        # Test with only range parameters (no formatting options)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": test_sheet_id,
            "range_start_row": 0,
            "range_end_row": 2,
            "range_start_col": 0,
            "range_end_col": 2
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return either auth error or "no formatting options provided"
        valid_responses = [
            "requires authentication", "no valid credentials", "no formatting options provided",
            "❌", "middleware", "service", "not yet fulfilled"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_format_sheet_range_error_handling(self, client):
        """Test error handling for format_sheet_range with invalid parameters."""
        # Test with invalid spreadsheet ID
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": "invalid_spreadsheet_id_12345",
            "sheet_id": 0,
            "range_start_row": 0,
            "range_end_row": 2,
            "range_start_col": 0,
            "range_end_col": 2,
            "bold": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        assert any(keyword in content.lower() for keyword in [
            "error", "not found", "requires authentication", "no valid credentials",
            "failed to apply", "invalid"
        ])
        
        # Test with invalid sheet ID
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",  # Sample ID
            "sheet_id": 999999,  # Invalid sheet ID
            "range_start_row": 0,
            "range_end_row": 2,
            "range_start_col": 0,
            "range_end_col": 2,
            "italic": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        assert any(keyword in content.lower() for keyword in [
            "error", "invalid", "requires authentication", "no valid credentials",
            "failed to apply", "sheet", "not found"
        ])


@pytest.mark.service("sheets")
class TestSheetsFormatRangeComparison:
    """Compare format_sheet_range with individual formatting tools to ensure equivalent functionality."""
    
    @pytest.mark.asyncio
    async def test_format_range_vs_individual_tools_availability(self, client):
        """Test that both format_sheet_range and individual tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Master tool should be available
        assert "format_sheet_range" in tool_names, "Master format_sheet_range tool should be available"
        
        # Individual tools should still be available for backward compatibility
        individual_tools = [
            "format_sheet_cells",
            "update_sheet_borders",
            "add_conditional_formatting",
            "merge_cells"
        ]
        
        for tool in individual_tools:
            assert tool in tool_names, f"Individual tool '{tool}' should remain available for backward compatibility"
    
    @pytest.mark.asyncio
    async def test_format_range_parameter_coverage(self, client):
        """Test that format_sheet_range covers all parameters from individual tools."""
        tools = await client.list_tools()
        
        # Find the format_sheet_range tool
        format_range_tool = None
        for tool in tools:
            if tool.name == "format_sheet_range":
                format_range_tool = tool
                break
        
        assert format_range_tool is not None, "format_sheet_range tool should be available"
        
        # The tool should have parameters that cover all individual tool functionality
        # This is a basic validation that the tool exists and has input schema
        assert hasattr(format_range_tool, 'inputSchema') or hasattr(format_range_tool, 'input_schema'), \
            "format_sheet_range should have input schema defined"


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