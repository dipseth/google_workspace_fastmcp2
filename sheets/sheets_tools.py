"""
Google Sheets MCP Tools

This module provides MCP tools for interacting with Google Sheets API using the universal service architecture.
"""

import logging
import asyncio
import json
from typing_extensions import List, Optional, Any, Union, Annotated
from pydantic import Field

from fastmcp import FastMCP
from googleapiclient.errors import HttpError

# Import our custom type for consistent parameter definition
from tools.common_types import UserGoogleEmailSheets

from auth.service_helpers import request_service, get_injected_service, get_service
from .sheets_types import (
    SpreadsheetListResponse,
    SpreadsheetInfo,
    SpreadsheetDetailsResponse,
    SheetInfo,
    SheetValuesResponse,
    SheetModifyResponse,
    CreateSpreadsheetResponse,
    CreateSheetResponse,
    FormatCellsResponse,
    UpdateBordersResponse,
    ConditionalFormattingResponse,
    MergeCellsResponse,
    FormatRangeResponse
)

# Configure module logger
logger = logging.getLogger(__name__)


def _parse_json_list(value: Any, field_name: str) -> Optional[List[Any]]:
    """
    Helper function to parse JSON strings or return lists as-is.
    Used for handling MCP client inputs that send JSON strings instead of Python lists.
    
    Args:
        value: The value to parse (could be string, list, or None)
        field_name: Name of the field for error messages
        
    Returns:
        List if successful, None if value is None
        
    Raises:
        ValueError: If parsing fails or type is invalid
    """
    if value is None:
        return None
        
    # If it's already a list, validate and return it
    if isinstance(value, list):
        return value
    
    # If it's a string, try to parse as JSON
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            else:
                raise ValueError(f"Invalid JSON structure for {field_name}: expected list, got {type(parsed).__name__}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {field_name}: {e}. Expected valid JSON string or Python list.")
    
    raise ValueError(f"Invalid type for {field_name}: expected string (JSON) or list, got {type(value).__name__}")


async def _get_sheets_service_with_fallback(user_google_email: str):
    """
    Get Sheets service with fallback pattern.
    
    Args:
        user_google_email: User's Google email address
        
    Returns:
        Google Sheets service instance
    """
    try:
        # Try to get service from middleware injection
        service_key = request_service("sheets")
        service = get_injected_service(service_key)
        if service:
            logger.debug("Using middleware-injected Sheets service")
            return service
    except Exception as e:
        logger.warning(f"Middleware service injection failed: {e}")
    
    # Fallback to direct service creation
    logger.info("Falling back to direct Sheets service creation")
    from auth.service_manager import get_google_service
    from auth.compatibility_shim import CompatibilityShim
    
    # Get sheets scopes using compatibility shim
    try:
        shim = CompatibilityShim()
        sheets_scopes = [
            shim.get_legacy_scope_groups()["sheets_write"],
            shim.get_legacy_scope_groups()["sheets_read"]
        ]
    except Exception as e:
        logger.warning(f"Failed to get sheets scopes from compatibility shim: {e}")
        # Fallback to hardcoded scopes
        sheets_scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/spreadsheets.readonly"
        ]
    
    return await get_google_service(
        user_email=user_google_email,
        service_type="sheets",
        version="v4",
        scopes=sheets_scopes
    )


def setup_sheets_tools(mcp: FastMCP) -> None:
    """
    Setup and register all Google Sheets tools with the MCP server.
    
    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up Google Sheets tools")
    
    @mcp.tool(
        name="list_spreadsheets",
        description="List spreadsheets from Google Drive that the user has access to",
        tags={"sheets", "drive", "list", "google"},
        annotations={
            "title": "List Google Spreadsheets",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_spreadsheets(
        user_google_email: UserGoogleEmailSheets = None,
        max_results: int = 25
    ) -> SpreadsheetListResponse:
        """
        Lists spreadsheets from Google Drive that the user has access to.

        Args:
            user_google_email (str): The user's Google email address. Required.
            max_results (int): Maximum number of spreadsheets to return. Must be between 1 and 1000. Defaults to 25.

        Returns:
            SpreadsheetListResponse: Structured list of spreadsheets with metadata.
        """
        logger.info(f"[list_spreadsheets] Invoked. Email: '{user_google_email}', max_results: {max_results}")
        
        # Validate max_results parameter
        if max_results < 1:
            max_results = 1
            logger.warning(f"max_results was less than 1, setting to 1")
        elif max_results > 1000:
            max_results = 1000
            logger.warning(f"max_results was greater than 1000, setting to 1000")

        try:
            # Get Drive service (spreadsheets are stored in Drive)
            drive_service_key = request_service("drive")
            
            try:
                # Try to get the injected service from middleware
                drive_service = get_injected_service(drive_service_key)
                logger.info(f"Successfully retrieved injected Drive service for {user_google_email}")
                
            except RuntimeError as e:
                if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
                    # Middleware injection failed, fall back to direct service creation
                    logger.warning(f"Middleware injection unavailable, falling back to direct service creation for {user_google_email}")
                    
                    try:
                        # Use the same helper function pattern as Gmail
                        drive_service = await get_service("drive", user_google_email)
                        logger.info(f"Successfully created Drive service directly for {user_google_email}")
                        
                    except Exception as direct_error:
                        logger.error(f"Direct Drive service creation failed for {user_google_email}: {direct_error}")
                        return SpreadsheetListResponse(
                            items=[],
                            count=0,
                            userEmail=user_google_email,
                            error=f"Failed to create Google Drive service. Please check your credentials and permissions."
                        )
                else:
                    # Different type of RuntimeError, log and fail
                    logger.error(f"Drive service injection error for {user_google_email}: {e}")
                    return SpreadsheetListResponse(
                        items=[],
                        count=0,
                        userEmail=user_google_email,
                        error=f"Drive service injection error: {e}"
                    )
                    
            except Exception as e:
                logger.error(f"Unexpected error getting Drive service for {user_google_email}: {e}")
                return SpreadsheetListResponse(
                    items=[],
                    count=0,
                    userEmail=user_google_email,
                    error=f"Unexpected error getting Drive service: {e}"
                )

            files_response = await asyncio.to_thread(
                drive_service.files()
                .list(
                    q="mimeType='application/vnd.google-apps.spreadsheet'",
                    pageSize=max_results,
                    fields="files(id,name,modifiedTime,webViewLink)",
                    orderBy="modifiedTime desc",
                )
                .execute
            )

            files = files_response.get("files", [])
            
            # Convert to structured format
            spreadsheets: List[SpreadsheetInfo] = []
            for file in files:
                spreadsheet_info: SpreadsheetInfo = {
                    "id": file.get("id", ""),
                    "name": file.get("name", "Unknown"),
                    "modifiedTime": file.get("modifiedTime"),
                    "webViewLink": file.get("webViewLink"),
                    "mimeType": "application/vnd.google-apps.spreadsheet"
                }
                spreadsheets.append(spreadsheet_info)

            logger.info(f"Successfully listed {len(spreadsheets)} spreadsheets for {user_google_email}.")
            
            return SpreadsheetListResponse(
                items=spreadsheets,  # Changed from 'spreadsheets' to 'items' to match TypedDict
                count=len(spreadsheets),
                userEmail=user_google_email
            )
        
        except HttpError as e:
            error_msg = f"Failed to list spreadsheets: {e}"
            logger.error(f"❌ {error_msg}")
            return SpreadsheetListResponse(
                items=[],
                count=0,
                userEmail=user_google_email,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error listing spreadsheets: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return SpreadsheetListResponse(
                items=[],
                count=0,
                userEmail=user_google_email,
                error=error_msg
            )

    @mcp.tool(
        name="get_spreadsheet_info",
        description="Get information about a specific spreadsheet including its sheets",
        tags={"sheets", "info", "metadata", "google"},
        annotations={
            "title": "Get Spreadsheet Information",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_spreadsheet_info(
        spreadsheet_id: str,
        user_google_email: UserGoogleEmailSheets = None
    ) -> SpreadsheetDetailsResponse:
        """
        Gets information about a specific spreadsheet including its sheets.

        Args:
            user_google_email (str): The user's Google email address. Required.
            spreadsheet_id (str): The ID of the spreadsheet to get info for. Required.

        Returns:
            SpreadsheetDetailsResponse: Structured spreadsheet information including title and sheets list.
        """
        logger.info(f"[get_spreadsheet_info] Invoked. Email: '{user_google_email}', Spreadsheet ID: {spreadsheet_id}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            spreadsheet = await asyncio.to_thread(
                sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute
            )

            title = spreadsheet.get("properties", {}).get("title", "Unknown")
            sheets = spreadsheet.get("sheets", [])
            spreadsheet_url = spreadsheet.get("spreadsheetUrl")

            sheets_info: List[SheetInfo] = []
            for sheet in sheets:
                sheet_props = sheet.get("properties", {})
                sheet_info: SheetInfo = {
                    "sheetId": sheet_props.get("sheetId", 0),
                    "title": sheet_props.get("title", "Unknown"),
                    "index": sheet_props.get("index", 0),
                    "rowCount": sheet_props.get("gridProperties", {}).get("rowCount", 0),
                    "columnCount": sheet_props.get("gridProperties", {}).get("columnCount", 0)
                }
                sheets_info.append(sheet_info)

            logger.info(f"Successfully retrieved info for spreadsheet {spreadsheet_id} for {user_google_email}.")
            
            return SpreadsheetDetailsResponse(
                spreadsheetId=spreadsheet_id,
                title=title,
                sheets=sheets_info,
                sheetCount=len(sheets),
                spreadsheetUrl=spreadsheet_url
            )
        
        except HttpError as e:
            error_msg = f"Failed to get spreadsheet info: {e}"
            logger.error(f"❌ {error_msg}")
            return SpreadsheetDetailsResponse(
                spreadsheetId=spreadsheet_id,
                title="",
                sheets=[],
                sheetCount=0,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error getting spreadsheet info: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return SpreadsheetDetailsResponse(
                spreadsheetId=spreadsheet_id,
                title="",
                sheets=[],
                sheetCount=0,
                error=error_msg
            )

    @mcp.tool(
        name="read_sheet_values",
        description="Read values from a specific range in a Google Sheet",
        tags={"sheets", "read", "values", "data", "google"},
        annotations={
            "title": "Read Sheet Values",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def read_sheet_values(
        spreadsheet_id: str,
        user_google_email: UserGoogleEmailSheets = None,
        range_name: str = "A1:Z1000"
    ) -> SheetValuesResponse:
        """
        Reads values from a specific range in a Google Sheet.

        Args:
            user_google_email (str): The user's Google email address. Required.
            spreadsheet_id (str): The ID of the spreadsheet. Required.
            range_name (str): The range to read (e.g., "Sheet1!A1:D10", "A1:D10"). Defaults to "A1:Z1000".

        Returns:
            SheetValuesResponse: Structured response with the values from the specified range.
        """
        logger.info(f"[read_sheet_values] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, Range: {range_name}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            result = await asyncio.to_thread(
                sheets_service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_name)
                .execute
            )

            values = result.get("values", [])
            
            # Calculate row and column counts
            row_count = len(values)
            column_count = max(len(row) for row in values) if values else 0
            
            logger.info(f"Successfully read {row_count} rows from range '{range_name}' for {user_google_email}.")
            
            return SheetValuesResponse(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                values=values,
                rowCount=row_count,
                columnCount=column_count
            )
        
        except HttpError as e:
            error_msg = f"Failed to read sheet values: {e}"
            logger.error(f"❌ {error_msg}")
            return SheetValuesResponse(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                values=[],
                rowCount=0,
                columnCount=0,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error reading sheet values: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return SheetValuesResponse(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                values=[],
                rowCount=0,
                columnCount=0,
                error=error_msg
            )

    @mcp.tool(
        name="modify_sheet_values",
        description="Modify values in a specific range of a Google Sheet - can write, update, or clear values",
        tags={"sheets", "write", "update", "clear", "google"},
        annotations={
            "title": "Modify Sheet Values",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def modify_sheet_values(
        spreadsheet_id: str,
        range_name: str,
        values: Annotated[
            Optional[Union[str, List[List[str]]]],
            Field(
                default=None,
                description="2D array of values to write/update. Can be Python list [[\"cell1\", \"cell2\"], [\"cell3\", \"cell4\"]] or JSON string '[[\"cell1\", \"cell2\"], [\"cell3\", \"cell4\"]]'. Required unless clear_values=True."
            )
        ] = None,
        value_input_option: Annotated[
            str,
            Field(
                default="USER_ENTERED",
                description="How to interpret input values: 'RAW' (values not parsed) or 'USER_ENTERED' (values parsed as if typed by user)"
            )
        ] = "USER_ENTERED",
        clear_values: Annotated[
            bool,
            Field(
                default=False,
                description="If True, clears the range instead of writing values. When True, 'values' parameter is ignored."
            )
        ] = False,
        user_google_email: UserGoogleEmailSheets = None
    ) -> SheetModifyResponse:
        """
        Modifies values in a specific range of a Google Sheet - can write, update, or clear values.

        Args:
            spreadsheet_id (str): The ID of the spreadsheet. Required.
            range_name (str): The range to modify (e.g., "Sheet1!A1:D10", "A1:D10"). Required.
            values (Optional[Union[str, List[List[str]]]]): 2D array of values to write/update. Can be Python list or JSON string. Required unless clear_values=True.
            value_input_option (str): How to interpret input values ("RAW" or "USER_ENTERED"). Defaults to "USER_ENTERED".
            clear_values (bool): If True, clears the range instead of writing values. Defaults to False.
            user_google_email (str): The user's Google email address. Auto-injected by middleware if not provided.

        Returns:
            SheetModifyResponse: Structured response with details of the modification operation.
        """
        operation = "clear" if clear_values else "write"
        logger.info(f"[modify_sheet_values] Invoked. Operation: {operation}, Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, Range: {range_name}")

        try:
            # Parse values parameter to handle JSON strings from MCP clients
            parsed_values = None
            if values is not None:
                try:
                    parsed_values = _parse_json_list(values, "values")
                    # Validate that it's a 2D array of strings
                    if parsed_values and not all(isinstance(row, list) and all(isinstance(cell, str) for cell in row) for row in parsed_values):
                        return SheetModifyResponse(
                            spreadsheetId=spreadsheet_id,
                            range=range_name,
                            operation="error",
                            success=False,
                            message="",
                            error="Values must be a 2D array of strings (List[List[str]])."
                        )
                except ValueError as e:
                    return SheetModifyResponse(
                        spreadsheetId=spreadsheet_id,
                        range=range_name,
                        operation="error",
                        success=False,
                        message="",
                        error=str(e)
                    )

            if not clear_values and not parsed_values:
                return SheetModifyResponse(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    operation="error",
                    success=False,
                    message="",
                    error="Either 'values' must be provided or 'clear_values' must be True."
                )

            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            if clear_values:
                result = await asyncio.to_thread(
                    sheets_service.spreadsheets()
                    .values()
                    .clear(spreadsheetId=spreadsheet_id, range=range_name)
                    .execute
                )

                cleared_range = result.get("clearedRange", range_name)
                logger.info(f"Successfully cleared range '{cleared_range}' for {user_google_email}.")
                
                return SheetModifyResponse(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    operation="clear",
                    clearedRange=cleared_range,
                    success=True,
                    message=f"Successfully cleared range '{cleared_range}' in spreadsheet {spreadsheet_id}."
                )
            else:
                body = {"values": parsed_values}

                result = await asyncio.to_thread(
                    sheets_service.spreadsheets()
                    .values()
                    .update(
                        spreadsheetId=spreadsheet_id,
                        range=range_name,
                        valueInputOption=value_input_option,
                        body=body,
                    )
                    .execute
                )

                updated_cells = result.get("updatedCells", 0)
                updated_rows = result.get("updatedRows", 0)
                updated_columns = result.get("updatedColumns", 0)

                logger.info(f"Successfully updated {updated_cells} cells for {user_google_email}.")
                
                return SheetModifyResponse(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    operation="update",
                    updatedCells=updated_cells,
                    updatedRows=updated_rows,
                    updatedColumns=updated_columns,
                    success=True,
                    message=f"Successfully updated range '{range_name}' in spreadsheet {spreadsheet_id}. Updated: {updated_cells} cells, {updated_rows} rows, {updated_columns} columns."
                )
        
        except HttpError as e:
            error_msg = f"Failed to modify sheet values: {e}"
            logger.error(f"❌ {error_msg}")
            return SheetModifyResponse(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                operation="clear" if clear_values else "update",
                success=False,
                message="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error modifying sheet values: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return SheetModifyResponse(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                operation="clear" if clear_values else "update",
                success=False,
                message="",
                error=error_msg
            )

    @mcp.tool(
        name="create_spreadsheet",
        description="Create a new Google Spreadsheet",
        tags={"sheets", "create", "new", "google"},
        annotations={
            "title": "Create New Spreadsheet",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_spreadsheet(
        title: str,
        user_google_email: UserGoogleEmailSheets = None,
        sheet_names: Annotated[
            Optional[Union[str, List[str]]],
            Field(
                default=None,
                description="List of sheet names to create. Can be Python list [\"Sheet1\", \"Sheet2\"] or JSON string '[\"Sheet1\", \"Sheet2\"]'. If not provided, creates one sheet with default name."
            )
        ] = None
    ) -> CreateSpreadsheetResponse:
        """
        Creates a new Google Spreadsheet.

        Args:
            title (str): The title of the new spreadsheet. Required.
            user_google_email (str): The user's Google email address. Auto-injected by middleware if not provided.
            sheet_names (Optional[Union[str, List[str]]]): List of sheet names to create. Can be Python list or JSON string. If not provided, creates one sheet with default name.

        Returns:
            CreateSpreadsheetResponse: Structured response with information about the newly created spreadsheet.
        """
        logger.info(f"[create_spreadsheet] Invoked. Email: '{user_google_email}', Title: {title}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            # Parse sheet_names parameter to handle JSON strings from MCP clients
            parsed_sheet_names = None
            if sheet_names is not None:
                try:
                    parsed_sheet_names = _parse_json_list(sheet_names, "sheet_names")
                    # Validate that all items are strings
                    if parsed_sheet_names and not all(isinstance(name, str) for name in parsed_sheet_names):
                        return CreateSpreadsheetResponse(
                            spreadsheetId="",
                            spreadsheetUrl="",
                            title=title,
                            sheets=sheet_names,
                            success=False,
                            message="",
                            error="All sheet names must be strings."
                        )
                except ValueError as e:
                    return CreateSpreadsheetResponse(
                        spreadsheetId="",
                        spreadsheetUrl="",
                        title=title,
                        sheets=sheet_names,
                        success=False,
                        message="",
                        error=str(e)
                    )

            spreadsheet_body = {
                "properties": {
                    "title": title
                }
            }

            if parsed_sheet_names:
                spreadsheet_body["sheets"] = [
                    {"properties": {"title": sheet_name}} for sheet_name in parsed_sheet_names
                ]

            spreadsheet = await asyncio.to_thread(
                sheets_service.spreadsheets().create(body=spreadsheet_body).execute
            )

            spreadsheet_id = spreadsheet.get("spreadsheetId")
            spreadsheet_url = spreadsheet.get("spreadsheetUrl")

            logger.info(f"Successfully created spreadsheet for {user_google_email}. ID: {spreadsheet_id}")
            
            return CreateSpreadsheetResponse(
                spreadsheetId=spreadsheet_id,
                spreadsheetUrl=spreadsheet_url,
                title=title,
                sheets=parsed_sheet_names,
                success=True,
                message=f"Successfully created spreadsheet '{title}' for {user_google_email}. ID: {spreadsheet_id}"
            )
        
        except HttpError as e:
            error_msg = f"Failed to create spreadsheet: {e}"
            logger.error(f"❌ {error_msg}")
            return CreateSpreadsheetResponse(
                spreadsheetId="",
                spreadsheetUrl="",
                title=title,
                sheets=parsed_sheet_names,
                success=False,
                message="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error creating spreadsheet: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return CreateSpreadsheetResponse(
                spreadsheetId="",
                spreadsheetUrl="",
                title=title,
                sheets=parsed_sheet_names,
                success=False,
                message="",
                error=error_msg
            )

    @mcp.tool(
        name="create_sheet",
        description="Create a new sheet within an existing spreadsheet",
        tags={"sheets", "create", "add", "google"},
        annotations={
            "title": "Create New Sheet",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_sheet(
        spreadsheet_id: str,
        sheet_name: str,
        user_google_email: UserGoogleEmailSheets = None
    ) -> CreateSheetResponse:
        """
        Creates a new sheet within an existing spreadsheet.

        Args:
            user_google_email (str): The user's Google email address. Required.
            spreadsheet_id (str): The ID of the spreadsheet. Required.
            sheet_name (str): The name of the new sheet. Required.

        Returns:
            CreateSheetResponse: Structured response with confirmation of the sheet creation.
        """
        logger.info(f"[create_sheet] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, Sheet: {sheet_name}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            request_body = {
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": sheet_name
                            }
                        }
                    }
                ]
            }

            response = await asyncio.to_thread(
                sheets_service.spreadsheets()
                .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
                .execute
            )

            sheet_id = response["replies"][0]["addSheet"]["properties"]["sheetId"]

            logger.info(f"Successfully created sheet for {user_google_email}. Sheet ID: {sheet_id}")
            
            return CreateSheetResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                sheetName=sheet_name,
                success=True,
                message=f"Successfully created sheet '{sheet_name}' (ID: {sheet_id}) in spreadsheet {spreadsheet_id}."
            )
        
        except HttpError as e:
            error_msg = f"Failed to create sheet: {e}"
            logger.error(f"❌ {error_msg}")
            return CreateSheetResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=0,
                sheetName=sheet_name,
                success=False,
                message="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error creating sheet: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return CreateSheetResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=0,
                sheetName=sheet_name,
                success=False,
                message="",
                error=error_msg
            )

    @mcp.tool(
        name="format_sheet_cells",
        description="Format cells in a Google Sheet with various styling options (text, colors, alignment, number formats)",
        tags={"sheets", "format", "style", "cells", "google"},
        annotations={
            "title": "Format Sheet Cells",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def format_sheet_cells(
        spreadsheet_id: str,
        sheet_id: int,
        range_start_row: int,
        range_end_row: int,
        range_start_col: int,
        range_end_col: int,
        bold: Optional[bool] = None,
        italic: Optional[bool] = None,
        font_size: Optional[int] = None,
        text_color: Optional[dict] = None,  # {"red": 0.0-1.0, "green": 0.0-1.0, "blue": 0.0-1.0}
        background_color: Optional[dict] = None,  # {"red": 0.0-1.0, "green": 0.0-1.0, "blue": 0.0-1.0}
        horizontal_alignment: Optional[str] = None,  # "LEFT", "CENTER", "RIGHT"
        vertical_alignment: Optional[str] = None,  # "TOP", "MIDDLE", "BOTTOM"
        number_format_type: Optional[str] = None,  # "TEXT", "NUMBER", "PERCENT", "CURRENCY", "DATE", "TIME", "DATE_TIME", "SCIENTIFIC"
        number_format_pattern: Optional[str] = None,  # Custom pattern like "$#,##0.00"
        wrap_strategy: Optional[str] = None,  # "WRAP", "OVERFLOW", "CLIP"
        text_rotation: Optional[int] = None,  # Angle in degrees (-90 to 90)
        user_google_email: UserGoogleEmailSheets = None
    ) -> FormatCellsResponse:
        """
        Format cells in a Google Sheet with various styling options.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_id: The sheet ID (can be found via get_spreadsheet_info)
            range_start_row: Starting row index (0-based)
            range_end_row: Ending row index (exclusive)
            range_start_col: Starting column index (0-based)
            range_end_col: Ending column index (exclusive)
            bold: Make text bold
            italic: Make text italic
            font_size: Font size in points (typically 8-72)
            text_color: Text color as RGB dict (values 0.0-1.0)
            background_color: Background color as RGB dict (values 0.0-1.0)
            horizontal_alignment: Text horizontal alignment
            vertical_alignment: Text vertical alignment
            number_format_type: Predefined number format type
            number_format_pattern: Custom number format pattern
            wrap_strategy: Text wrapping strategy
            text_rotation: Text rotation angle in degrees
            user_google_email: User's Google email address

        Returns:
            FormatCellsResponse with details of applied formatting
        """
        logger.info(f"[format_sheet_cells] Formatting cells in spreadsheet {spreadsheet_id}, sheet {sheet_id}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            # Build the CellFormat object
            cell_format = {}
            fields = []
            
            # Text format
            text_format = {}
            if bold is not None:
                text_format["bold"] = bold
                fields.append("userEnteredFormat.textFormat.bold")
            if italic is not None:
                text_format["italic"] = italic
                fields.append("userEnteredFormat.textFormat.italic")
            if font_size is not None:
                text_format["fontSize"] = font_size
                fields.append("userEnteredFormat.textFormat.fontSize")
            if text_color is not None:
                text_format["foregroundColor"] = text_color
                fields.append("userEnteredFormat.textFormat.foregroundColor")
            
            if text_format:
                cell_format["textFormat"] = text_format
            
            # Background color
            if background_color is not None:
                cell_format["backgroundColor"] = background_color
                fields.append("userEnteredFormat.backgroundColor")
            
            # Alignment
            if horizontal_alignment:
                cell_format["horizontalAlignment"] = horizontal_alignment
                fields.append("userEnteredFormat.horizontalAlignment")
            if vertical_alignment:
                cell_format["verticalAlignment"] = vertical_alignment
                fields.append("userEnteredFormat.verticalAlignment")
            
            # Number format
            if number_format_type or number_format_pattern:
                number_format = {}
                if number_format_type:
                    number_format["type"] = number_format_type
                    fields.append("userEnteredFormat.numberFormat.type")
                if number_format_pattern:
                    number_format["pattern"] = number_format_pattern
                    fields.append("userEnteredFormat.numberFormat.pattern")
                cell_format["numberFormat"] = number_format
            
            # Wrap strategy
            if wrap_strategy:
                cell_format["wrapStrategy"] = wrap_strategy
                fields.append("userEnteredFormat.wrapStrategy")
            
            # Text rotation
            if text_rotation is not None:
                cell_format["textRotation"] = {"angle": text_rotation}
                fields.append("userEnteredFormat.textRotation")
            
            # Create the request
            if cell_format and fields:
                requests = [{
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": range_start_row,
                            "endRowIndex": range_end_row,
                            "startColumnIndex": range_start_col,
                            "endColumnIndex": range_end_col
                        },
                        "cell": {
                            "userEnteredFormat": cell_format
                        },
                        "fields": ",".join(fields)
                    }
                }]
                
                body = {"requests": requests}
                response = await asyncio.to_thread(
                    sheets_service.spreadsheets()
                    .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
                    .execute
                )
                
                # Build summary of applied formatting
                formatting_applied = {
                    "bold": bold,
                    "italic": italic,
                    "fontSize": font_size,
                    "textColor": text_color,
                    "backgroundColor": background_color,
                    "horizontalAlignment": horizontal_alignment,
                    "verticalAlignment": vertical_alignment,
                    "numberFormat": f"{number_format_type or 'custom'}: {number_format_pattern}" if (number_format_type or number_format_pattern) else None,
                    "wrapStrategy": wrap_strategy,
                    "textRotation": text_rotation
                }
                # Remove None values
                formatting_applied = {k: v for k, v in formatting_applied.items() if v is not None}
                
                range_str = f"R{range_start_row+1}C{range_start_col+1}:R{range_end_row}C{range_end_col}"
                
                logger.info(f"Successfully formatted cells in range {range_str}")
                return FormatCellsResponse(
                    spreadsheetId=spreadsheet_id,
                    sheetId=sheet_id,
                    range=range_str,
                    formattingApplied=formatting_applied,
                    success=True,
                    message=f"Successfully formatted cells in range {range_str}"
                )
            else:
                return FormatCellsResponse(
                    spreadsheetId=spreadsheet_id,
                    sheetId=sheet_id,
                    range="",
                    formattingApplied={},
                    success=False,
                    message="No formatting options provided"
                )
        
        except HttpError as e:
            error_msg = f"Failed to format cells: {e}"
            logger.error(f"❌ {error_msg}")
            return FormatCellsResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                formattingApplied={},
                success=False,
                message="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error formatting cells: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return FormatCellsResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                formattingApplied={},
                success=False,
                message="",
                error=error_msg
            )

    @mcp.tool(
        name="update_sheet_borders",
        description="Update borders for a range of cells in a Google Sheet",
        tags={"sheets", "borders", "format", "style", "google"},
        annotations={
            "title": "Update Sheet Borders",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def update_sheet_borders(
        spreadsheet_id: str,
        sheet_id: int,
        range_start_row: int,
        range_end_row: int,
        range_start_col: int,
        range_end_col: int,
        border_style: str = "SOLID",  # "SOLID", "DASHED", "DOTTED", "SOLID_MEDIUM", "SOLID_THICK", "DOUBLE"
        border_color: Optional[dict] = None,  # {"red": 0.0-1.0, "green": 0.0-1.0, "blue": 0.0-1.0}
        top: bool = True,
        bottom: bool = True,
        left: bool = True,
        right: bool = True,
        inner_horizontal: bool = False,
        inner_vertical: bool = False,
        user_google_email: UserGoogleEmailSheets = None
    ) -> UpdateBordersResponse:
        """
        Update borders for a range of cells in a Google Sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_id: The sheet ID
            range_start_row: Starting row index (0-based)
            range_end_row: Ending row index (exclusive)
            range_start_col: Starting column index (0-based)
            range_end_col: Ending column index (exclusive)
            border_style: Style of the border
            border_color: Border color as RGB dict (default: black)
            top: Apply top border
            bottom: Apply bottom border
            left: Apply left border
            right: Apply right border
            inner_horizontal: Apply inner horizontal borders
            inner_vertical: Apply inner vertical borders
            user_google_email: User's Google email address

        Returns:
            UpdateBordersResponse with details of applied borders
        """
        logger.info(f"[update_sheet_borders] Updating borders in spreadsheet {spreadsheet_id}, sheet {sheet_id}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            # Default to black if no color provided
            if border_color is None:
                border_color = {"red": 0.0, "green": 0.0, "blue": 0.0}

            # Build the border object
            border = {
                "style": border_style,
                "color": border_color
            }

            # Create the request
            request = {
                "updateBorders": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": range_start_row,
                        "endRowIndex": range_end_row,
                        "startColumnIndex": range_start_col,
                        "endColumnIndex": range_end_col
                    }
                }
            }

            # Add borders based on parameters
            if top:
                request["updateBorders"]["top"] = border
            if bottom:
                request["updateBorders"]["bottom"] = border
            if left:
                request["updateBorders"]["left"] = border
            if right:
                request["updateBorders"]["right"] = border
            if inner_horizontal:
                request["updateBorders"]["innerHorizontal"] = border
            if inner_vertical:
                request["updateBorders"]["innerVertical"] = border

            body = {"requests": [request]}
            response = await asyncio.to_thread(
                sheets_service.spreadsheets()
                .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
                .execute
            )

            range_str = f"R{range_start_row+1}C{range_start_col+1}:R{range_end_row}C{range_end_col}"
            
            logger.info(f"Successfully updated borders for range {range_str}")
            return UpdateBordersResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range=range_str,
                borderStyle=border_style,
                success=True,
                message=f"Successfully updated borders for range {range_str} with style {border_style}"
            )
        
        except HttpError as e:
            error_msg = f"Failed to update borders: {e}"
            logger.error(f"❌ {error_msg}")
            return UpdateBordersResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                borderStyle=border_style,
                success=False,
                message="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error updating borders: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return UpdateBordersResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                borderStyle=border_style,
                success=False,
                message="",
                error=error_msg
            )

    @mcp.tool(
        name="add_conditional_formatting",
        description="Add conditional formatting rules to a Google Sheet",
        tags={"sheets", "conditional", "format", "rules", "google"},
        annotations={
            "title": "Add Conditional Formatting",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def add_conditional_formatting(
        spreadsheet_id: str,
        sheet_id: int,
        range_start_row: int,
        range_end_row: int,
        range_start_col: int,
        range_end_col: int,
        condition_type: str,  # "NUMBER_GREATER", "NUMBER_LESS", "NUMBER_EQ", "TEXT_CONTAINS", "TEXT_EQ", "BLANK", "NOT_BLANK", "CUSTOM_FORMULA"
        value: Optional[Union[str, float]] = None,  # Value for comparison or formula
        format_background_color: Optional[dict] = None,  # {"red": 0.0-1.0, "green": 0.0-1.0, "blue": 0.0-1.0}
        format_text_color: Optional[dict] = None,  # {"red": 0.0-1.0, "green": 0.0-1.0, "blue": 0.0-1.0}
        format_bold: Optional[bool] = None,
        format_italic: Optional[bool] = None,
        user_google_email: UserGoogleEmailSheets = None
    ) -> ConditionalFormattingResponse:
        """
        Add conditional formatting rules to a Google Sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_id: The sheet ID
            range_start_row: Starting row index (0-based)
            range_end_row: Ending row index (exclusive)
            range_start_col: Starting column index (0-based)
            range_end_col: Ending column index (exclusive)
            condition_type: Type of condition to apply
            value: Value for comparison (for NUMBER/TEXT conditions) or formula (for CUSTOM_FORMULA)
            format_background_color: Background color when condition is met
            format_text_color: Text color when condition is met
            format_bold: Make text bold when condition is met
            format_italic: Make text italic when condition is met
            user_google_email: User's Google email address

        Returns:
            ConditionalFormattingResponse with details of the created rule
        """
        logger.info(f"[add_conditional_formatting] Adding conditional formatting to spreadsheet {spreadsheet_id}, sheet {sheet_id}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            # Build the condition
            condition = {}
            if condition_type == "NUMBER_GREATER":
                condition = {
                    "type": "NUMBER_GREATER",
                    "values": [{"userEnteredValue": str(value)}]
                }
            elif condition_type == "NUMBER_LESS":
                condition = {
                    "type": "NUMBER_LESS",
                    "values": [{"userEnteredValue": str(value)}]
                }
            elif condition_type == "NUMBER_EQ":
                condition = {
                    "type": "NUMBER_EQ",
                    "values": [{"userEnteredValue": str(value)}]
                }
            elif condition_type == "TEXT_CONTAINS":
                condition = {
                    "type": "TEXT_CONTAINS",
                    "values": [{"userEnteredValue": str(value)}]
                }
            elif condition_type == "TEXT_EQ":
                condition = {
                    "type": "TEXT_EQ",
                    "values": [{"userEnteredValue": str(value)}]
                }
            elif condition_type == "BLANK":
                condition = {"type": "BLANK"}
            elif condition_type == "NOT_BLANK":
                condition = {"type": "NOT_BLANK"}
            elif condition_type == "CUSTOM_FORMULA":
                condition = {
                    "type": "CUSTOM_FORMULA",
                    "values": [{"userEnteredValue": str(value)}]
                }
            else:
                return ConditionalFormattingResponse(
                    spreadsheetId=spreadsheet_id,
                    sheetId=sheet_id,
                    range="",
                    condition=condition_type,
                    success=False,
                    message="",
                    error=f"Invalid condition type: {condition_type}"
                )

            # Build the format
            format_dict = {}
            if format_background_color:
                format_dict["backgroundColor"] = format_background_color
            if format_text_color or format_bold is not None or format_italic is not None:
                text_format = {}
                if format_text_color:
                    text_format["foregroundColor"] = format_text_color
                if format_bold is not None:
                    text_format["bold"] = format_bold
                if format_italic is not None:
                    text_format["italic"] = format_italic
                format_dict["textFormat"] = text_format

            # Create the rule
            rule = {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": range_start_row,
                    "endRowIndex": range_end_row,
                    "startColumnIndex": range_start_col,
                    "endColumnIndex": range_end_col
                }],
                "booleanRule": {
                    "condition": condition,
                    "format": format_dict
                }
            }

            request = {
                "addConditionalFormatRule": {
                    "rule": rule,
                    "index": 0  # Add at the beginning (highest priority)
                }
            }

            body = {"requests": [request]}
            response = await asyncio.to_thread(
                sheets_service.spreadsheets()
                .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
                .execute
            )

            range_str = f"R{range_start_row+1}C{range_start_col+1}:R{range_end_row}C{range_end_col}"
            
            logger.info(f"Successfully added conditional formatting rule to range {range_str}")
            return ConditionalFormattingResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range=range_str,
                condition=f"{condition_type}: {value}" if value else condition_type,
                success=True,
                message=f"Successfully added conditional formatting rule to range {range_str}"
            )
        
        except HttpError as e:
            error_msg = f"Failed to add conditional formatting: {e}"
            logger.error(f"❌ {error_msg}")
            return ConditionalFormattingResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                condition=condition_type,
                success=False,
                message="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error adding conditional formatting: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return ConditionalFormattingResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                condition=condition_type,
                success=False,
                message="",
                error=error_msg
            )

    @mcp.tool(
        name="merge_cells",
        description="Merge or unmerge cells in a Google Sheet",
        tags={"sheets", "merge", "cells", "format", "google"},
        annotations={
            "title": "Merge Cells",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def merge_cells(
        spreadsheet_id: str,
        sheet_id: int,
        range_start_row: int,
        range_end_row: int,
        range_start_col: int,
        range_end_col: int,
        merge_type: str = "MERGE_ALL",  # "MERGE_ALL", "MERGE_ROWS", "MERGE_COLUMNS", or "UNMERGE"
        user_google_email: UserGoogleEmailSheets = None
    ) -> MergeCellsResponse:
        """
        Merge or unmerge cells in a Google Sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_id: The sheet ID
            range_start_row: Starting row index (0-based)
            range_end_row: Ending row index (exclusive)
            range_start_col: Starting column index (0-based)
            range_end_col: Ending column index (exclusive)
            merge_type: Type of merge operation:
                - "MERGE_ALL": Merge all cells in range into one
                - "MERGE_ROWS": Merge cells in each row separately
                - "MERGE_COLUMNS": Merge cells in each column separately
                - "UNMERGE": Unmerge all cells in range
            user_google_email: User's Google email address

        Returns:
            MergeCellsResponse with details of the merge operation
        """
        logger.info(f"[merge_cells] {merge_type} operation on spreadsheet {spreadsheet_id}, sheet {sheet_id}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            # Create the appropriate request based on merge_type
            if merge_type == "UNMERGE":
                request = {
                    "unmergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": range_start_row,
                            "endRowIndex": range_end_row,
                            "startColumnIndex": range_start_col,
                            "endColumnIndex": range_end_col
                        }
                    }
                }
            else:
                request = {
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": range_start_row,
                            "endRowIndex": range_end_row,
                            "startColumnIndex": range_start_col,
                            "endColumnIndex": range_end_col
                        },
                        "mergeType": merge_type
                    }
                }

            body = {"requests": [request]}
            response = await asyncio.to_thread(
                sheets_service.spreadsheets()
                .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
                .execute
            )

            range_str = f"R{range_start_row+1}C{range_start_col+1}:R{range_end_row}C{range_end_col}"
            
            operation = "unmerged" if merge_type == "UNMERGE" else "merged"
            logger.info(f"Successfully {operation} cells in range {range_str}")
            
            return MergeCellsResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range=range_str,
                mergeType=merge_type,
                success=True,
                message=f"Successfully {operation} cells in range {range_str} with type {merge_type}"
            )
        
        except HttpError as e:
            error_msg = f"Failed to merge/unmerge cells: {e}"
            logger.error(f"❌ {error_msg}")
            return MergeCellsResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                mergeType=merge_type,
                success=False,
                message="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error merging/unmerging cells: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return MergeCellsResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                mergeType=merge_type,
                success=False,
                message="",
                error=error_msg
            )

    @mcp.tool(
        name="format_sheet_range",
        description="Apply comprehensive formatting to a range in Google Sheets with multiple formatting options in a single request",
        tags={"sheets", "format", "comprehensive", "batch", "google"},
        annotations={
            "title": "Format Sheet Range (Comprehensive)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def format_sheet_range(
        spreadsheet_id: str,
        sheet_id: int,
        range_start_row: int,
        range_end_row: int,
        range_start_col: int,
        range_end_col: int,
        # Cell formatting options
        cell_format: Optional[dict] = None,
        # Border options
        apply_borders: bool = False,
        border_style: Optional[str] = None,
        border_positions: Optional[dict] = None,  # {"top": True, "bottom": True, "left": True, "right": True}
        # Merge options
        merge_cells_option: Optional[str] = None,  # "MERGE_ALL", "MERGE_ROWS", "MERGE_COLUMNS"
        # Conditional formatting
        conditional_rules: Optional[List[dict]] = None,
        # Column width
        column_width: Optional[int] = None,
        # Row height
        row_height: Optional[int] = None,
        # Freeze rows/columns
        freeze_rows: Optional[int] = None,
        freeze_columns: Optional[int] = None,
        user_google_email: UserGoogleEmailSheets = None
    ) -> FormatRangeResponse:
        """
        Apply comprehensive formatting to a range in Google Sheets.
        This is a powerful tool that can apply multiple formatting operations in a single API call.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_id: The sheet ID
            range_start_row: Starting row index (0-based)
            range_end_row: Ending row index (exclusive)
            range_start_col: Starting column index (0-based)
            range_end_col: Ending column index (exclusive)
            cell_format: Dictionary with cell formatting options like:
                {
                    "bold": True,
                    "italic": False,
                    "fontSize": 12,
                    "textColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"},
                    "wrapStrategy": "WRAP"
                }
            apply_borders: Whether to apply borders
            border_style: Style of borders ("SOLID", "DASHED", "DOTTED", etc.)
            border_positions: Which borders to apply
            merge_cells_option: Merge type if merging cells
            conditional_rules: List of conditional formatting rules
            column_width: Width in pixels for columns in range
            row_height: Height in pixels for rows in range
            freeze_rows: Number of rows to freeze from top
            freeze_columns: Number of columns to freeze from left
            user_google_email: User's Google email address

        Returns:
            FormatRangeResponse with details of all applied formatting
        """
        logger.info(f"[format_sheet_range] Applying comprehensive formatting to spreadsheet {spreadsheet_id}, sheet {sheet_id}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            requests = []
            formatting_details = {}

            # 1. Cell formatting
            if cell_format:
                cell_format_request = {}
                fields = []
                
                # Build text format
                text_format = {}
                if "bold" in cell_format:
                    text_format["bold"] = cell_format["bold"]
                    fields.append("userEnteredFormat.textFormat.bold")
                if "italic" in cell_format:
                    text_format["italic"] = cell_format["italic"]
                    fields.append("userEnteredFormat.textFormat.italic")
                if "fontSize" in cell_format:
                    text_format["fontSize"] = cell_format["fontSize"]
                    fields.append("userEnteredFormat.textFormat.fontSize")
                if "textColor" in cell_format:
                    text_format["foregroundColor"] = cell_format["textColor"]
                    fields.append("userEnteredFormat.textFormat.foregroundColor")
                
                if text_format:
                    cell_format_request["textFormat"] = text_format
                
                # Other cell format properties
                if "backgroundColor" in cell_format:
                    cell_format_request["backgroundColor"] = cell_format["backgroundColor"]
                    fields.append("userEnteredFormat.backgroundColor")
                if "horizontalAlignment" in cell_format:
                    cell_format_request["horizontalAlignment"] = cell_format["horizontalAlignment"]
                    fields.append("userEnteredFormat.horizontalAlignment")
                if "verticalAlignment" in cell_format:
                    cell_format_request["verticalAlignment"] = cell_format["verticalAlignment"]
                    fields.append("userEnteredFormat.verticalAlignment")
                if "numberFormat" in cell_format:
                    cell_format_request["numberFormat"] = cell_format["numberFormat"]
                    fields.append("userEnteredFormat.numberFormat")
                if "wrapStrategy" in cell_format:
                    cell_format_request["wrapStrategy"] = cell_format["wrapStrategy"]
                    fields.append("userEnteredFormat.wrapStrategy")
                
                if cell_format_request and fields:
                    requests.append({
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": range_start_row,
                                "endRowIndex": range_end_row,
                                "startColumnIndex": range_start_col,
                                "endColumnIndex": range_end_col
                            },
                            "cell": {"userEnteredFormat": cell_format_request},
                            "fields": ",".join(fields)
                        }
                    })
                    formatting_details["cellFormat"] = cell_format

            # 2. Borders
            if apply_borders and border_style:
                border = {"style": border_style}
                if not border_positions:
                    border_positions = {"top": True, "bottom": True, "left": True, "right": True}
                
                border_request = {
                    "updateBorders": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": range_start_row,
                            "endRowIndex": range_end_row,
                            "startColumnIndex": range_start_col,
                            "endColumnIndex": range_end_col
                        }
                    }
                }
                
                for position, apply in border_positions.items():
                    if apply:
                        border_request["updateBorders"][position] = border
                
                requests.append(border_request)
                formatting_details["borders"] = {"style": border_style, "positions": border_positions}

            # 3. Merge cells
            if merge_cells_option:
                requests.append({
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": range_start_row,
                            "endRowIndex": range_end_row,
                            "startColumnIndex": range_start_col,
                            "endColumnIndex": range_end_col
                        },
                        "mergeType": merge_cells_option
                    }
                })
                formatting_details["merge"] = merge_cells_option

            # 4. Column width
            if column_width is not None:
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": range_start_col,
                            "endIndex": range_end_col
                        },
                        "properties": {"pixelSize": column_width},
                        "fields": "pixelSize"
                    }
                })
                formatting_details["columnWidth"] = column_width

            # 5. Row height
            if row_height is not None:
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": range_start_row,
                            "endIndex": range_end_row
                        },
                        "properties": {"pixelSize": row_height},
                        "fields": "pixelSize"
                    }
                })
                formatting_details["rowHeight"] = row_height

            # 6. Freeze rows/columns
            if freeze_rows is not None or freeze_columns is not None:
                grid_properties = {}
                if freeze_rows is not None:
                    grid_properties["frozenRowCount"] = freeze_rows
                if freeze_columns is not None:
                    grid_properties["frozenColumnCount"] = freeze_columns
                
                requests.append({
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": grid_properties
                        },
                        "fields": ",".join([f"gridProperties.{k}" for k in grid_properties.keys()])
                    }
                })
                formatting_details["freeze"] = {"rows": freeze_rows, "columns": freeze_columns}

            # Execute all requests
            if requests:
                body = {"requests": requests}
                response = await asyncio.to_thread(
                    sheets_service.spreadsheets()
                    .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
                    .execute
                )
                
                range_str = f"R{range_start_row+1}C{range_start_col+1}:R{range_end_row}C{range_end_col}"
                
                logger.info(f"Successfully applied {len(requests)} formatting operations to range {range_str}")
                return FormatRangeResponse(
                    spreadsheetId=spreadsheet_id,
                    sheetId=sheet_id,
                    range=range_str,
                    requestsApplied=len(requests),
                    formattingDetails=formatting_details,
                    success=True,
                    message=f"Successfully applied {len(requests)} formatting operations to range {range_str}"
                )
            else:
                return FormatRangeResponse(
                    spreadsheetId=spreadsheet_id,
                    sheetId=sheet_id,
                    range="",
                    requestsApplied=0,
                    formattingDetails={},
                    success=False,
                    message="No formatting options provided"
                )
        
        except HttpError as e:
            error_msg = f"Failed to apply comprehensive formatting: {e}"
            logger.error(f"❌ {error_msg}")
            return FormatRangeResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                requestsApplied=0,
                formattingDetails={},
                success=False,
                message="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error applying comprehensive formatting: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return FormatRangeResponse(
                spreadsheetId=spreadsheet_id,
                sheetId=sheet_id,
                range="",
                requestsApplied=0,
                formattingDetails={},
                success=False,
                message="",
                error=error_msg
            )

    logger.info("✅ Google Sheets tools setup complete")