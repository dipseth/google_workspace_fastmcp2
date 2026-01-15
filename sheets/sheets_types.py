"""
Type definitions for Google Sheets tool responses.

These Pydantic BaseModel classes define the structure of data returned by Sheets tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from pydantic import BaseModel, Field
from typing_extensions import List, Optional


class SpreadsheetInfo(BaseModel):
    """Structure for a single spreadsheet entry."""

    id: str = Field(..., description="Unique identifier for the spreadsheet")
    name: str = Field(..., description="Display name of the spreadsheet")
    modifiedTime: Optional[str] = Field(
        None, description="Last modification time in ISO format"
    )
    webViewLink: Optional[str] = Field(
        None, description="Web view URL for the spreadsheet"
    )
    mimeType: str = Field(..., description="MIME type of the file")


class SheetInfo(BaseModel):
    """Structure for a single sheet within a spreadsheet."""

    sheetId: int = Field(..., description="Unique identifier for the sheet")
    title: str = Field(..., description="Title of the sheet")
    index: int = Field(..., description="Index position of the sheet")
    rowCount: int = Field(..., description="Number of rows in the sheet")
    columnCount: int = Field(..., description="Number of columns in the sheet")


class SpreadsheetListResponse(BaseModel):
    """Response structure for list_spreadsheets tool."""

    items: List[SpreadsheetInfo] = Field(
        ..., description="List of spreadsheet information"
    )
    count: int = Field(..., description="Total number of spreadsheets found")
    userEmail: str = Field(..., description="Email address of the requesting user")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class SpreadsheetDetailsResponse(BaseModel):
    """Response structure for get_spreadsheet_info tool."""

    spreadsheetId: str = Field(..., description="Unique identifier for the spreadsheet")
    title: str = Field(..., description="Title of the spreadsheet")
    sheets: List[SheetInfo] = Field(
        ..., description="List of sheets in the spreadsheet"
    )
    sheetCount: int = Field(..., description="Total number of sheets")
    spreadsheetUrl: Optional[str] = Field(
        None, description="Web URL for the spreadsheet"
    )
    error: Optional[str] = Field(None, description="Error message if operation failed")


class SheetValuesResponse(BaseModel):
    """Response structure for read_sheet_values tool."""

    spreadsheetId: str = Field(..., description="Unique identifier for the spreadsheet")
    range: str = Field(..., description="Range that was read from the sheet")
    values: List[List[str]] = Field(..., description="2D array of cell values")
    rowCount: int = Field(..., description="Number of rows returned")
    columnCount: int = Field(..., description="Number of columns returned")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class SheetModifyResponse(BaseModel):
    """Response structure for modify_sheet_values tool."""

    spreadsheetId: str = Field(..., description="Unique identifier for the spreadsheet")
    range: str = Field(..., description="Range that was modified")
    operation: str = Field(
        ..., description="Type of operation performed ('update', 'clear')"
    )
    updatedCells: Optional[int] = Field(None, description="Number of cells updated")
    updatedRows: Optional[int] = Field(None, description="Number of rows updated")
    updatedColumns: Optional[int] = Field(None, description="Number of columns updated")
    clearedRange: Optional[str] = Field(None, description="Range that was cleared")
    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class CreateSpreadsheetResponse(BaseModel):
    """Response structure for create_spreadsheet tool."""

    spreadsheetId: str = Field(
        ..., description="Unique identifier for the created spreadsheet"
    )
    spreadsheetUrl: str = Field(..., description="Web URL for the created spreadsheet")
    title: str = Field(..., description="Title of the created spreadsheet")
    sheets: Optional[List[str]] = Field(None, description="Names of created sheets")
    success: bool = Field(..., description="Whether the creation succeeded")
    message: str = Field(..., description="Success or error message")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class CreateSheetResponse(BaseModel):
    """Response structure for create_sheet tool."""

    spreadsheetId: str = Field(..., description="Unique identifier for the spreadsheet")
    sheetId: int = Field(..., description="Unique identifier for the created sheet")
    sheetName: str = Field(..., description="Name of the created sheet")
    success: bool = Field(..., description="Whether the creation succeeded")
    message: str = Field(..., description="Success or error message")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class FormatCellsResponse(BaseModel):
    """Response structure for format_sheet_cells tool."""

    spreadsheetId: str = Field(..., description="Unique identifier for the spreadsheet")
    sheetId: int = Field(..., description="Sheet ID where formatting was applied")
    range: str = Field(..., description="Cell range that was formatted")
    formattingApplied: dict = Field(
        ..., description="Summary of formatting options applied"
    )
    success: bool = Field(..., description="Whether the formatting succeeded")
    message: str = Field(..., description="Success or error message")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class UpdateBordersResponse(BaseModel):
    """Response structure for update_sheet_borders tool."""

    spreadsheetId: str = Field(..., description="Unique identifier for the spreadsheet")
    sheetId: int = Field(..., description="Sheet ID where borders were updated")
    range: str = Field(..., description="Cell range where borders were applied")
    borderStyle: str = Field(..., description="Border style that was applied")
    success: bool = Field(..., description="Whether the border update succeeded")
    message: str = Field(..., description="Success or error message")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class ConditionalFormattingResponse(BaseModel):
    """Response structure for add_conditional_formatting tool."""

    spreadsheetId: str = Field(..., description="Unique identifier for the spreadsheet")
    sheetId: int = Field(
        ..., description="Sheet ID where conditional formatting was added"
    )
    ruleId: Optional[int] = Field(None, description="ID of the created formatting rule")
    range: str = Field(..., description="Cell range where rule was applied")
    condition: str = Field(..., description="Condition type that was applied")
    success: bool = Field(..., description="Whether the rule addition succeeded")
    message: str = Field(..., description="Success or error message")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class MergeCellsResponse(BaseModel):
    """Response structure for merge_cells tool."""

    spreadsheetId: str = Field(..., description="Unique identifier for the spreadsheet")
    sheetId: int = Field(..., description="Sheet ID where cells were merged")
    range: str = Field(..., description="Cell range that was merged")
    mergeType: str = Field(..., description="Type of merge operation performed")
    success: bool = Field(..., description="Whether the merge succeeded")
    message: str = Field(..., description="Success or error message")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class FormatRangeResponse(BaseModel):
    """Response structure for format_sheet_range comprehensive formatting tool."""

    spreadsheetId: str = Field(..., description="Unique identifier for the spreadsheet")
    sheetId: int = Field(..., description="Sheet ID where formatting was applied")
    range: str = Field(..., description="Cell range that was formatted")
    requestsApplied: int = Field(
        ..., description="Number of formatting requests successfully applied"
    )
    formattingDetails: dict = Field(
        ..., description="Details of all formatting applied"
    )
    success: bool = Field(..., description="Whether the formatting succeeded")
    message: str = Field(..., description="Success or error message")
    error: Optional[str] = Field(None, description="Error message if operation failed")
