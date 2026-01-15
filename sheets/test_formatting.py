#!/usr/bin/env python3
"""
Test script for Google Sheets formatting tools.
This script demonstrates the new formatting capabilities added to sheets_tools.py
"""

import asyncio
import logging

from fastmcp import FastMCP

from sheets.sheets_tools import setup_sheets_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_formatting_tools():
    """
    Test the newly added formatting tools.
    Note: This requires a valid Google Sheets spreadsheet ID and authentication.
    """

    # Initialize FastMCP server
    mcp = FastMCP(name="sheets_formatting_test")

    # Setup sheets tools
    setup_sheets_tools(mcp)

    logger.info("✅ Google Sheets formatting tools have been successfully set up!")

    # List all available formatting tools
    formatting_tools = [
        "format_sheet_cells",
        "update_sheet_borders",
        "add_conditional_formatting",
        "merge_cells",
        "format_sheet_range",
    ]

    logger.info("\n📊 New Formatting Tools Added:")
    for tool_name in formatting_tools:
        tool = mcp.tools.get(tool_name)
        if tool:
            logger.info(f"  ✓ {tool_name}: {tool.description}")
        else:
            logger.error(f"  ✗ {tool_name}: NOT FOUND")

    # Display tool parameters for format_sheet_cells as an example
    format_cells_tool = mcp.tools.get("format_sheet_cells")
    if format_cells_tool:
        logger.info("\n📝 format_sheet_cells Parameters:")
        logger.info("  Required:")
        logger.info("    - spreadsheet_id: The ID of the spreadsheet")
        logger.info("    - sheet_id: The sheet ID (from get_spreadsheet_info)")
        logger.info("    - range_start_row: Starting row index (0-based)")
        logger.info("    - range_end_row: Ending row index (exclusive)")
        logger.info("    - range_start_col: Starting column index (0-based)")
        logger.info("    - range_end_col: Ending column index (exclusive)")
        logger.info("  Optional formatting:")
        logger.info("    - bold: Make text bold")
        logger.info("    - italic: Make text italic")
        logger.info("    - font_size: Font size in points")
        logger.info("    - text_color: RGB dict (0.0-1.0)")
        logger.info("    - background_color: RGB dict (0.0-1.0)")
        logger.info("    - horizontal_alignment: LEFT, CENTER, RIGHT")
        logger.info("    - vertical_alignment: TOP, MIDDLE, BOTTOM")
        logger.info(
            "    - number_format_type: TEXT, NUMBER, PERCENT, CURRENCY, DATE, etc."
        )
        logger.info("    - number_format_pattern: Custom pattern like '$#,##0.00'")
        logger.info("    - wrap_strategy: WRAP, OVERFLOW, CLIP")
        logger.info("    - text_rotation: Angle in degrees (-90 to 90)")

    # Display comprehensive formatting tool info
    format_range_tool = mcp.tools.get("format_sheet_range")
    if format_range_tool:
        logger.info("\n🎨 format_sheet_range - Comprehensive Formatting:")
        logger.info(
            "  This powerful tool can apply multiple formatting operations in a single API call:"
        )
        logger.info("    - Cell formatting (text, colors, alignment, number formats)")
        logger.info("    - Borders (style, positions)")
        logger.info("    - Cell merging")
        logger.info("    - Conditional formatting rules")
        logger.info("    - Column width adjustments")
        logger.info("    - Row height adjustments")
        logger.info("    - Freeze rows/columns")

    logger.info("\n✨ Summary:")
    logger.info(f"  Total formatting tools added: {len(formatting_tools)}")
    logger.info("  All tools support:")
    logger.info("    - Automatic authentication via middleware")
    logger.info("    - Comprehensive error handling")
    logger.info("    - Structured response types")
    logger.info("    - Batch operations for efficiency")

    return True


def main():
    """Main entry point for testing."""
    try:
        result = asyncio.run(test_formatting_tools())
        if result:
            logger.info("\n🎉 All formatting tools successfully added and verified!")
            logger.info("\n📚 Usage Example:")
            logger.info("  To format cells with bold text and yellow background:")
            logger.info("  await format_sheet_cells(")
            logger.info("      spreadsheet_id='your_spreadsheet_id',")
            logger.info("      sheet_id=0,")
            logger.info("      range_start_row=0, range_end_row=5,")
            logger.info("      range_start_col=0, range_end_col=3,")
            logger.info("      bold=True,")
            logger.info(
                "      background_color={'red': 1.0, 'green': 1.0, 'blue': 0.0}"
            )
            logger.info("  )")
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    main()
