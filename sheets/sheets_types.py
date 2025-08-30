"""
Type definitions for Google Sheets tool responses.

These TypedDict classes define the structure of data returned by Sheets tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing import TypedDict, List, Optional


class SpreadsheetInfo(TypedDict):
    """Structure for a single spreadsheet entry."""
    id: str
    name: str
    modifiedTime: Optional[str]
    webViewLink: Optional[str]
    mimeType: str


class SheetInfo(TypedDict):
    """Structure for a single sheet within a spreadsheet."""
    sheetId: int
    title: str
    index: int
    rowCount: int
    columnCount: int


class SpreadsheetListResponse(TypedDict):
    """Response structure for list_spreadsheets tool."""
    spreadsheets: List[SpreadsheetInfo]
    count: int
    userEmail: str