"""
Type definitions for Google Sheets tool responses.

These TypedDict classes define the structure of data returned by Sheets tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional, NotRequired


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


class SpreadsheetListResponse(TypedDict, total=False):
    """Response structure for list_spreadsheets tool."""
    items: List[SpreadsheetInfo]  # Changed from 'spreadsheets' to 'items' for consistency
    count: int
    userEmail: str
    error: Optional[str]  # Optional error message for error responses


class SpreadsheetDetailsResponse(TypedDict, total=False):
    """Response structure for get_spreadsheet_info tool."""
    spreadsheetId: str
    title: str
    sheets: List[SheetInfo]
    sheetCount: int
    spreadsheetUrl: Optional[str]
    error: Optional[str]


class SheetValuesResponse(TypedDict, total=False):
    """Response structure for read_sheet_values tool."""
    spreadsheetId: str
    range: str
    values: List[List[str]]
    rowCount: int
    columnCount: int
    error: Optional[str]


class SheetModifyResponse(TypedDict, total=False):
    """Response structure for modify_sheet_values tool."""
    spreadsheetId: str
    range: str
    operation: str  # 'update', 'clear'
    updatedCells: Optional[int]
    updatedRows: Optional[int]
    updatedColumns: Optional[int]
    clearedRange: Optional[str]
    success: bool
    message: str
    error: Optional[str]


class CreateSpreadsheetResponse(TypedDict, total=False):
    """Response structure for create_spreadsheet tool."""
    spreadsheetId: str
    spreadsheetUrl: str
    title: str
    sheets: Optional[List[str]]  # Names of created sheets
    success: bool
    message: str
    error: Optional[str]


class CreateSheetResponse(TypedDict, total=False):
    """Response structure for create_sheet tool."""
    spreadsheetId: str
    sheetId: int
    sheetName: str
    success: bool
    message: str
    error: Optional[str]