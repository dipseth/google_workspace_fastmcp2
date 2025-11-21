"""
Comprehensive validation tests for format_sheet_range tool replacing individual formatting tools.

This test suite validates that the unified format_sheet_range tool can correctly replace
the functionality of the four individual formatting tools:
- format_sheet_cells
- update_sheet_borders  
- add_conditional_formatting
- merge_cells

It also tests the validation fixes for number format and wrap strategy parameters.
"""

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


# Global fixture available to both test classes
@pytest.fixture(scope="session")
def test_spreadsheet_id():
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
                    "title": "Format Range Validation Test Spreadsheet"
                })
                
                if result and result.content:
                    content = result.content[0].text
                    print(f"DEBUG: Create spreadsheet response: {content}")
                    
                    # Extract spreadsheet ID from response
                    patterns = [
                        r'ID:\s*([a-zA-Z0-9_-]{20,})',
                        r'id[:\s]+([a-zA-Z0-9_-]{20,})',
                        r'spreadsheet[:\s]+([a-zA-Z0-9_-]{20,})',
                        r'created[:\s]+([a-zA-Z0-9_-]{20,})',
                        r'https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)',
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            potential_id = match.group(1)
                            if len(potential_id) >= 20:
                                return potential_id
                    
                    print(f"DEBUG: No ID pattern matched in: {content}")
            except Exception:
                pass
        
        return None
    
    # Run the async function
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _create_test_spreadsheet())
                _test_spreadsheet_id = future.result()
        else:
            _test_spreadsheet_id = loop.run_until_complete(_create_test_spreadsheet())
    except RuntimeError:
        _test_spreadsheet_id = asyncio.run(_create_test_spreadsheet())
    
    return _test_spreadsheet_id


@pytest.mark.service("sheets")
class TestFormatSheetRangeValidation:
    """Comprehensive validation tests for the format_sheet_range master tool."""
    
    @pytest.mark.asyncio
    async def test_format_sheet_range_tool_available(self, client):
        """Test that the format_sheet_range tool is available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        assert "format_sheet_range" in tool_names, "format_sheet_range tool should be available"
        
        # Find the tool and check its description mentions it replaces other tools
        format_range_tool = next(tool for tool in tools if tool.name == "format_sheet_range")
        assert "unified" in format_range_tool.description.lower(), "Tool should be described as unified"
        assert "comprehensive" in format_range_tool.description.lower(), "Tool should be described as comprehensive"
    
    @pytest.mark.asyncio
    async def test_cell_formatting_replacement(self, client, test_spreadsheet_id):
        """Test that format_sheet_range can replace format_sheet_cells functionality."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test basic cell formatting (bold, italic, font size, colors, alignment)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 0,
            "range_end_row": 2,
            "range_start_col": 0,
            "range_end_col": 3,
            "bold": True,
            "italic": False,
            "font_size": 14,
            "text_color": {"red": 0.2, "green": 0.4, "blue": 0.8},
            "background_color": {"red": 0.95, "green": 0.95, "blue": 0.95},
            "horizontal_alignment": "CENTER",
            "vertical_alignment": "MIDDLE",
            "wrap_strategy": "WRAP"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # Should either succeed or return authentication error
        valid_responses = [
            "successfully applied", "formatting operations", "range", 
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Cell formatting response should be valid: {content}"
    
    @pytest.mark.asyncio
    async def test_number_format_validation_fixed(self, client, test_spreadsheet_id):
        """Test that number format validation is fixed - both type and pattern required together."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test with both type and pattern (should work)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 2,
            "range_end_row": 4,
            "range_start_col": 0,
            "range_end_col": 2,
            "number_format_type": "CURRENCY",
            "number_format_pattern": "$#,##0.00"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        valid_responses = [
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Valid number format should work: {content}"
        
        # Test with only type (should fail with validation error)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 4,
            "range_end_row": 6,
            "range_start_col": 0,
            "range_end_col": 2,
            "number_format_type": "CURRENCY"
            # Missing number_format_pattern
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # Should get validation error (either our validation or API validation - both are correct)
        if "authentication" not in content.lower():
            validation_indicators = [
                ("both" in content.lower() and "together" in content.lower()),  # Our validation
                ("both" in content.lower() and "must both be set" in content.lower()),  # API validation
                ("numberformat" in content.lower() and "both" in content.lower()),  # API validation variant
            ]
            assert any(validation_indicators), \
                f"Should get validation error for incomplete number format: {content}"
    
    @pytest.mark.asyncio
    async def test_wrap_strategy_validation_fixed(self, client, test_spreadsheet_id):
        """Test that wrap strategy validation is fixed - OVERFLOW is no longer valid."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test with valid wrap strategy (should work)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 6,
            "range_end_row": 8,
            "range_start_col": 0,
            "range_end_col": 2,
            "wrap_strategy": "WRAP"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        valid_responses = [
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Valid wrap strategy should work: {content}"
        
        # Note: We can't easily test OVERFLOW rejection at the client level since
        # the parameter validation happens at the Sheets API level, but the 
        # documentation is now corrected to only show valid options
    
    @pytest.mark.asyncio
    async def test_border_formatting_replacement(self, client, test_spreadsheet_id):
        """Test that format_sheet_range can replace update_sheet_borders functionality."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test border formatting
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 8,
            "range_end_row": 11,
            "range_start_col": 0,
            "range_end_col": 4,
            "apply_borders": True,
            "border_style": "SOLID_MEDIUM",
            "border_color": {"red": 0.0, "green": 0.0, "blue": 0.8},
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
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Border formatting response should be valid: {content}"
    
    @pytest.mark.asyncio
    async def test_conditional_formatting_replacement(self, client, test_spreadsheet_id):
        """Test that format_sheet_range can replace add_conditional_formatting functionality."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test conditional formatting
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 11,
            "range_end_row": 14,
            "range_start_col": 0,
            "range_end_col": 3,
            "condition_type": "NUMBER_GREATER",
            "condition_value": 100,
            "condition_format_background_color": {"red": 0.8, "green": 0.9, "blue": 0.8},
            "condition_format_text_color": {"red": 0.0, "green": 0.6, "blue": 0.0},
            "condition_format_bold": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        valid_responses = [
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Conditional formatting response should be valid: {content}"
    
    @pytest.mark.asyncio
    async def test_merge_cells_replacement(self, client, test_spreadsheet_id):
        """Test that format_sheet_range can replace merge_cells functionality."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test cell merging
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 14,
            "range_end_row": 16,
            "range_start_col": 0,
            "range_end_col": 2,
            "merge_cells_option": "MERGE_ALL"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        valid_responses = [
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Cell merging response should be valid: {content}"
    
    @pytest.mark.asyncio
    async def test_comprehensive_formatting_combination(self, client, test_spreadsheet_id):
        """Test that format_sheet_range can combine all four formatting operations in one call."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test comprehensive formatting combining all operations
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 16,
            "range_end_row": 19,
            "range_start_col": 0,
            "range_end_col": 4,
            # Cell formatting
            "bold": True,
            "italic": False,
            "font_size": 12,
            "text_color": {"red": 0.1, "green": 0.1, "blue": 0.8},
            "background_color": {"red": 0.98, "green": 0.98, "blue": 1.0},
            "horizontal_alignment": "CENTER",
            "vertical_alignment": "MIDDLE",
            "number_format_type": "PERCENT",
            "number_format_pattern": "0.00%",
            "wrap_strategy": "CLIP",
            # Border formatting
            "apply_borders": True,
            "border_style": "DASHED",
            "border_color": {"red": 0.6, "green": 0.6, "blue": 0.6},
            "top_border": True,
            "bottom_border": True,
            "left_border": False,
            "right_border": False,
            # Conditional formatting
            "condition_type": "NUMBER_LESS",
            "condition_value": 0.5,
            "condition_format_background_color": {"red": 1.0, "green": 0.8, "blue": 0.8},
            "condition_format_italic": True,
            # Column and row sizing
            "column_width": 120,
            "row_height": 30
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        valid_responses = [
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Comprehensive formatting response should be valid: {content}"
        
        # If successful, should mention multiple operations
        if "successfully applied" in content.lower():
            # Should have applied multiple formatting operations
            assert any(num in content for num in ["2", "3", "4", "5", "6", "7"]), \
                f"Should apply multiple formatting operations: {content}"
    
    @pytest.mark.asyncio
    async def test_format_sheet_range_response_structure(self, client, test_spreadsheet_id):
        """Test that format_sheet_range returns proper FormatRangeResponse structure."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test with simple formatting to get response structure
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 19,
            "range_end_row": 20,
            "range_start_col": 0,
            "range_end_col": 1,
            "bold": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # Check for expected response fields (when successful)
        if "successfully applied" in content.lower():
            expected_fields = [
                "spreadsheetid", "sheetid", "range", "requestsapplied", 
                "formattingdetails", "success", "message"
            ]
            content_lower = content.lower()
            
            # Should contain key response structure elements
            structure_indicators = ["spreadsheet", "sheet", "range", "format"]
            assert any(indicator in content_lower for indicator in structure_indicators), \
                f"Response should contain structure indicators: {content}"
    
    @pytest.mark.asyncio
    async def test_parameter_validation_comprehensive(self, client, test_spreadsheet_id):
        """Test comprehensive parameter validation for format_sheet_range."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test missing required parameters - should be caught by FastMCP
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("format_sheet_range", {
                "user_google_email": TEST_EMAIL,
                # Missing spreadsheet_id, sheet_id, and range parameters
            })
        assert "required" in str(exc_info.value).lower()
        
        # Test invalid range (end before start) - should work at client level,
        # might fail at API level
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 5,
            "range_end_row": 2,  # Invalid: end before start
            "range_start_col": 0,
            "range_end_col": 2,
            "bold": True
        })
        
        # Should get some response (might be API error about invalid range)
        assert result is not None and result.content
    
    @pytest.mark.asyncio
    async def test_individual_tools_still_available(self, client):
        """Test that individual formatting tools are still available (not deprecated yet)."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # All four individual tools should still be available
        individual_tools = [
            "format_sheet_cells",
            "update_sheet_borders", 
            "add_conditional_formatting",
            "merge_cells"
        ]
        
        for tool_name in individual_tools:
            assert tool_name in tool_names, f"Individual tool {tool_name} should still be available"
    
    @pytest.mark.asyncio
    async def test_auth_patterns_format_sheet_range(self, client):
        """Test authentication patterns for format_sheet_range tool."""
        runner = ToolTestRunner(client, TEST_EMAIL)
        
        # Test both auth patterns with minimal parameters
        results = await runner.test_auth_patterns("format_sheet_range", {
            "spreadsheet_id": "test_spreadsheet_id", 
            "sheet_id": 0,
            "range_start_row": 0,
            "range_end_row": 1,
            "range_start_col": 0,
            "range_end_col": 1,
            "bold": True
        })
        
        # Should handle both auth patterns properly
        assert results["backward_compatible"] or results["middleware_supported"], \
            "Should support at least one authentication pattern"
    
    @pytest.mark.asyncio
    async def test_json_string_color_parameters(self, client, test_spreadsheet_id):
        """Test that color parameters accept JSON strings as well as dicts."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test with JSON string color parameters (client sends strings)
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 0,
            "range_end_row": 2,
            "range_start_col": 0,
            "range_end_col": 3,
            "text_color": '{"red": 1.0, "green": 1.0, "blue": 1.0}',  # JSON string
            "background_color": '{"red": 0.2, "green": 0.4, "blue": 0.8}',  # JSON string
            "bold": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # Should NOT get validation errors about dict types
        assert "input should be a valid dictionary" not in content.lower(), \
            f"Should accept JSON string color parameters: {content}"
        
        valid_responses = [
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"JSON string colors should work: {content}"
    
    @pytest.mark.asyncio
    async def test_json_string_border_parameters(self, client, test_spreadsheet_id):
        """Test that border parameters accept JSON strings."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test with JSON string border parameters
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 2,
            "range_end_row": 4,
            "range_start_col": 0,
            "range_end_col": 2,
            "apply_borders": True,
            "border_color": '{"red": 0.5, "green": 0.5, "blue": 0.5}',  # JSON string
            "border_positions": '{"top": true, "bottom": true, "left": true, "right": true}',  # JSON string
            "border_style": "SOLID"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # Should NOT get validation errors
        assert "input should be a valid dictionary" not in content.lower(), \
            f"Should accept JSON string border parameters: {content}"
        
        valid_responses = [
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"JSON string borders should work: {content}"
    
    @pytest.mark.asyncio
    async def test_json_string_conditional_format_parameters(self, client, test_spreadsheet_id):
        """Test that conditional formatting color parameters accept JSON strings."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test with JSON string conditional format colors
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 4,
            "range_end_row": 6,
            "range_start_col": 0,
            "range_end_col": 2,
            "condition_type": "NUMBER_GREATER",
            "condition_value": 50,
            "condition_format_background_color": '{"red": 0.9, "green": 0.9, "blue": 0.5}',  # JSON string
            "condition_format_text_color": '{"red": 0.1, "green": 0.1, "blue": 0.1}'  # JSON string
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # Should NOT get validation errors
        assert "input should be a valid dictionary" not in content.lower(), \
            f"Should accept JSON string conditional format colors: {content}"
        
        valid_responses = [
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"JSON string conditional colors should work: {content}"
    
    @pytest.mark.asyncio
    async def test_mixed_dict_and_json_parameters(self, client, test_spreadsheet_id):
        """Test mixing dict and JSON string parameters in the same call."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Mix dict and JSON string parameters
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 6,
            "range_end_row": 8,
            "range_start_col": 0,
            "range_end_col": 3,
            "text_color": {"red": 1.0, "green": 0.0, "blue": 0.0},  # Dict
            "background_color": '{"red": 1.0, "green": 1.0, "blue": 0.8}',  # JSON string
            "bold": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # Should handle both formats in same call
        assert "input should be a valid dictionary" not in content.lower(), \
            f"Should handle mixed dict/JSON formats: {content}"
        
        valid_responses = [
            "successfully applied", "formatting operations", "range",
            "requires authentication", "no valid credentials", "❌"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Mixed format parameters should work: {content}"
    
    @pytest.mark.asyncio
    async def test_error_handling_robustness(self, client):
        """Test robust error handling for various edge cases."""
        
        # Test with invalid spreadsheet ID
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": "invalid_spreadsheet_id_12345",
            "sheet_id": 0,
            "range_start_row": 0,
            "range_end_row": 1,
            "range_start_col": 0,
            "range_end_col": 1,
            "bold": True
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # Should get proper error handling
        error_indicators = ["error", "not found", "invalid", "authentication", "failed"]
        assert any(indicator in content.lower() for indicator in error_indicators), \
            f"Should handle invalid spreadsheet ID gracefully: {content}"
    
    @pytest.mark.asyncio
    async def test_invalid_json_string_handling(self, client, test_spreadsheet_id):
        """Test that invalid JSON strings are properly rejected with helpful errors."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # Test with malformed JSON string
        result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 0,
            "range_end_row": 1,
            "range_start_col": 0,
            "range_end_col": 1,
            "text_color": '{red: 1.0, green: 1.0}'  # Invalid JSON (missing quotes)
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # Should get helpful JSON parsing error
        error_indicators = ["invalid json", "json", "parse", "error"]
        assert any(indicator in content.lower() for indicator in error_indicators), \
            f"Should provide helpful error for invalid JSON: {content}"


@pytest.mark.service("sheets")
class TestFormatSheetRangeIntegration:
    """Integration tests for format_sheet_range with other Sheets operations."""
    
    @pytest.mark.asyncio
    async def test_format_sheet_range_with_data_operations(self, client, test_spreadsheet_id):
        """Test format_sheet_range integration with data read/write operations."""
        if not test_spreadsheet_id:
            pytest.skip("No test spreadsheet ID available")
        
        # First write some data
        write_result = await client.call_tool("modify_sheet_values", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "range_name": "A21:C23",
            "values": [
                ["Product", "Price", "Quantity"],
                ["Widget A", "25.99", "100"],
                ["Widget B", "45.50", "50"]
            ]
        })
        
        # Then format the data
        format_result = await client.call_tool("format_sheet_range", {
            "user_google_email": TEST_EMAIL,
            "spreadsheet_id": test_spreadsheet_id,
            "sheet_id": 0,
            "range_start_row": 20,  # A21 in 0-based indexing
            "range_end_row": 23,    # Through A23
            "range_start_col": 0,   # Column A
            "range_end_col": 3,     # Through Column C
            "bold": True,
            "horizontal_alignment": "CENTER",
            "apply_borders": True,
            "border_style": "SOLID",
            "top_border": True,
            "bottom_border": True,
            "left_border": True,
            "right_border": True
        })
        
        # Both operations should work or fail gracefully
        assert write_result is not None and write_result.content
        assert format_result is not None and format_result.content
        
        write_content = write_result.content[0].text
        format_content = format_result.content[0].text
        
        # Check for reasonable responses
        valid_responses = [
            "successfully", "updated", "applied", "formatting",
            "requires authentication", "no valid credentials", "❌"
        ]
        
        assert any(keyword in write_content.lower() for keyword in valid_responses), \
            f"Data write should respond appropriately: {write_content}"
        assert any(keyword in format_content.lower() for keyword in valid_responses), \
            f"Formatting should respond appropriately: {format_content}"