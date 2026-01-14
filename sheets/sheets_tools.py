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
from config.enhanced_logging import setup_logger
logger = setup_logger()


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


def _parse_json_dict(value: Any, field_name: str) -> Optional[dict]:
    """
    Helper function to parse JSON strings or return dicts as-is.
    Used for handling MCP client inputs that send JSON strings instead of Python dicts.
    
    Args:
        value: The value to parse (could be string, dict, or None)
        field_name: Name of the field for error messages
        
    Returns:
        Dict if successful, None if value is None
        
    Raises:
        ValueError: If parsing fails or type is invalid
    """
    if value is None:
        return None
        
    # If it's already a dict, return it
    if isinstance(value, dict):
        return value
    
    # If it's a string, try to parse as JSON
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            else:
                raise ValueError(f"Invalid JSON structure for {field_name}: expected dict, got {type(parsed).__name__}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {field_name}: {e}. Expected valid JSON string or Python dict.")
    
    raise ValueError(f"Invalid type for {field_name}: expected string (JSON) or dict, got {type(value).__name__}")


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
        range_name: str = "A1:Z1000",
        value_render_option: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "How values should be rendered. One of: "
                    "FORMATTED_VALUE (default), UNFORMATTED_VALUE, FORMULA. "
                    "If omitted, the Google Sheets API default is used."
                ),
            ),
        ] = None,
        date_time_render_option: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "How dates, times, and durations should be rendered. One of: "
                    "SERIAL_NUMBER, FORMATTED_STRING. "
                    "If omitted, the Google Sheets API default is used."
                ),
            ),
        ] = None,
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
        logger.info(
            f"[read_sheet_values] Invoked. Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, "
            f"Range: {range_name}, value_render_option: {value_render_option}, date_time_render_option: {date_time_render_option}"
        )

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            # Optional rendering parameters (mirrors Google Sheets API Values.get)
            request_kwargs: dict = {
                "spreadsheetId": spreadsheet_id,
                "range": range_name,
            }
            if value_render_option:
                request_kwargs["valueRenderOption"] = value_render_option
            if date_time_render_option:
                request_kwargs["dateTimeRenderOption"] = date_time_render_option

            result = await asyncio.to_thread(
                sheets_service.spreadsheets().values().get(**request_kwargs).execute
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

        parsed_sheet_names: Optional[List[str]] = None

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            # Parse sheet_names parameter to handle JSON strings from MCP clients
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
                sheets=parsed_sheet_names or (sheet_names if isinstance(sheet_names, list) else None),
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
                sheets=parsed_sheet_names or (sheet_names if isinstance(sheet_names, list) else None),
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
        name="format_sheet_range",
        description="Apply comprehensive formatting to a range in Google Sheets with multiple formatting options in a single request - unified formatting tool that replaces format_sheet_cells, update_sheet_borders, add_conditional_formatting, and merge_cells",
        tags={"sheets", "format", "comprehensive", "unified", "batch", "google"},
        annotations={
            "title": "Unified Sheet Range Formatter",
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
        # Cell formatting options (replaces format_sheet_cells)
        cell_format: Optional[Union[str, dict]] = None,
        # Individual cell format parameters for convenience
        bold: Optional[bool] = None,
        italic: Optional[bool] = None,
        font_size: Optional[int] = None,
        text_color: Optional[Union[str, dict]] = None,  # {"red": 0.0-1.0, "green": 0.0-1.0, "blue": 0.0-1.0} or JSON string
        background_color: Optional[Union[str, dict]] = None,  # {"red": 0.0-1.0, "green": 0.0-1.0, "blue": 0.0-1.0} or JSON string
        horizontal_alignment: Optional[str] = None,  # "LEFT", "CENTER", "RIGHT"
        vertical_alignment: Optional[str] = None,  # "TOP", "MIDDLE", "BOTTOM"
        number_format_type: Optional[str] = None,  # "TEXT", "NUMBER", "PERCENT", "CURRENCY", "DATE", "TIME", "DATE_TIME", "SCIENTIFIC"
        number_format_pattern: Optional[str] = None,  # Custom pattern like "$#,##0.00"
        wrap_strategy: Optional[str] = None,  # "WRAP", "CLIP"
        text_rotation: Optional[int] = None,  # Angle in degrees (-90 to 90)
        # Border options (replaces update_sheet_borders)
        apply_borders: bool = False,
        border_style: Optional[str] = None,  # "SOLID", "DASHED", "DOTTED", "SOLID_MEDIUM", "SOLID_THICK", "DOUBLE"
        border_color: Optional[Union[str, dict]] = None,  # {"red": 0.0-1.0, "green": 0.0-1.0, "blue": 0.0-1.0} or JSON string
        border_positions: Optional[Union[str, dict]] = None,  # {"top": True, "bottom": True, "left": True, "right": True, "inner_horizontal": False, "inner_vertical": False} or JSON string
        # Individual border position parameters for convenience
        top_border: Optional[bool] = None,
        bottom_border: Optional[bool] = None,
        left_border: Optional[bool] = None,
        right_border: Optional[bool] = None,
        inner_horizontal_border: Optional[bool] = None,
        inner_vertical_border: Optional[bool] = None,
        # Merge options (replaces merge_cells)
        merge_cells_option: Optional[str] = None,  # "MERGE_ALL", "MERGE_ROWS", "MERGE_COLUMNS", "UNMERGE"
        # Conditional formatting options (replaces add_conditional_formatting)
        conditional_rules: Optional[List[dict]] = None,
        # Simple conditional formatting parameters for convenience
        condition_type: Optional[str] = None,  # "NUMBER_GREATER", "NUMBER_LESS", "NUMBER_EQ", "TEXT_CONTAINS", "TEXT_EQ", "BLANK", "NOT_BLANK", "CUSTOM_FORMULA"
        condition_value: Optional[Union[str, float]] = None,  # Value for comparison or formula
        condition_format_background_color: Optional[Union[str, dict]] = None,  # Background color when condition is met or JSON string
        condition_format_text_color: Optional[Union[str, dict]] = None,  # Text color when condition is met or JSON string
        condition_format_bold: Optional[bool] = None,  # Make text bold when condition is met
        condition_format_italic: Optional[bool] = None,  # Make text italic when condition is met
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
            
            # Parse JSON string parameters to dicts
            try:
                parsed_cell_format = _parse_json_dict(cell_format, "cell_format") if cell_format else None
                parsed_text_color = _parse_json_dict(text_color, "text_color") if text_color else None
                parsed_background_color = _parse_json_dict(background_color, "background_color") if background_color else None
                parsed_border_color = _parse_json_dict(border_color, "border_color") if border_color else None
                parsed_border_positions = _parse_json_dict(border_positions, "border_positions") if border_positions else None
                parsed_condition_bg_color = _parse_json_dict(condition_format_background_color, "condition_format_background_color") if condition_format_background_color else None
                parsed_condition_text_color = _parse_json_dict(condition_format_text_color, "condition_format_text_color") if condition_format_text_color else None
            except ValueError as e:
                return FormatRangeResponse(
                    spreadsheetId=spreadsheet_id,
                    sheetId=sheet_id,
                    range="",
                    requestsApplied=0,
                    formattingDetails={},
                    success=False,
                    message="",
                    error=str(e)
                )

            # 1. Cell formatting (combining cell_format dict with convenience parameters)
            final_cell_format = {}
            fields = []
            
            # Start with cell_format dict if provided
            if parsed_cell_format:
                final_cell_format.update(parsed_cell_format)
            
            # Override with convenience parameters (they take precedence)
            text_format_updates = {}
            if bold is not None:
                text_format_updates["bold"] = bold
                fields.append("userEnteredFormat.textFormat.bold")
            if italic is not None:
                text_format_updates["italic"] = italic
                fields.append("userEnteredFormat.textFormat.italic")
            if font_size is not None:
                text_format_updates["fontSize"] = font_size
                fields.append("userEnteredFormat.textFormat.fontSize")
            if parsed_text_color is not None:
                text_format_updates["foregroundColor"] = parsed_text_color
                fields.append("userEnteredFormat.textFormat.foregroundColor")
            
            # Merge text format updates
            if text_format_updates:
                if "textFormat" not in final_cell_format:
                    final_cell_format["textFormat"] = {}
                final_cell_format["textFormat"].update(text_format_updates)
            
            # Other convenience parameters
            if parsed_background_color is not None:
                final_cell_format["backgroundColor"] = parsed_background_color
                fields.append("userEnteredFormat.backgroundColor")
            if horizontal_alignment is not None:
                final_cell_format["horizontalAlignment"] = horizontal_alignment
                fields.append("userEnteredFormat.horizontalAlignment")
            if vertical_alignment is not None:
                final_cell_format["verticalAlignment"] = vertical_alignment
                fields.append("userEnteredFormat.verticalAlignment")
            if wrap_strategy is not None:
                final_cell_format["wrapStrategy"] = wrap_strategy
                fields.append("userEnteredFormat.wrapStrategy")
            if text_rotation is not None:
                final_cell_format["textRotation"] = {"angle": text_rotation}
                fields.append("userEnteredFormat.textRotation")
            # Number format - both type and pattern must be provided together
            if number_format_type and number_format_pattern:
                number_format = {
                    "type": number_format_type,
                    "pattern": number_format_pattern
                }
                fields.append("userEnteredFormat.numberFormat.type")
                fields.append("userEnteredFormat.numberFormat.pattern")
                final_cell_format["numberFormat"] = number_format
            elif number_format_type or number_format_pattern:
                # Return error if only one is provided
                return FormatRangeResponse(
                    spreadsheetId=spreadsheet_id,
                    sheetId=sheet_id,
                    range="",
                    requestsApplied=0,
                    formattingDetails={},
                    success=False,
                    message="",
                    error="Both number_format_type and number_format_pattern must be provided together, or neither."
                )
            
            # Create cell format request if we have any formatting
            if final_cell_format and fields:
                cell_format_request = {}
                
                # Build text format
                if "textFormat" in final_cell_format:
                    cell_format_request["textFormat"] = final_cell_format["textFormat"]
                
                # Other properties
                for prop in ["backgroundColor", "horizontalAlignment", "verticalAlignment",
                           "numberFormat", "wrapStrategy", "textRotation"]:
                    if prop in final_cell_format:
                        cell_format_request[prop] = final_cell_format[prop]
                
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
                formatting_details["cellFormat"] = final_cell_format

            # 2. Borders (combining border_positions dict with convenience parameters)
            if apply_borders:
                final_border_style = border_style or "SOLID"
                final_border_color = parsed_border_color or {"red": 0.0, "green": 0.0, "blue": 0.0}
                
                # Determine border positions
                final_border_positions = {}
                if parsed_border_positions:
                    final_border_positions = parsed_border_positions.copy()
                
                # Override with convenience parameters
                if top_border is not None:
                    final_border_positions["top"] = top_border
                if bottom_border is not None:
                    final_border_positions["bottom"] = bottom_border
                if left_border is not None:
                    final_border_positions["left"] = left_border
                if right_border is not None:
                    final_border_positions["right"] = right_border
                if inner_horizontal_border is not None:
                    final_border_positions["innerHorizontal"] = inner_horizontal_border
                if inner_vertical_border is not None:
                    final_border_positions["innerVertical"] = inner_vertical_border
                
                # Default to all borders if none specified
                if not final_border_positions:
                    final_border_positions = {"top": True, "bottom": True, "left": True, "right": True}
                
                border = {"style": final_border_style, "color": final_border_color}
                
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
                
                for position, apply in final_border_positions.items():
                    if apply:
                        border_request["updateBorders"][position] = border
                
                requests.append(border_request)
                formatting_details["borders"] = {
                    "style": final_border_style,
                    "color": final_border_color,
                    "positions": final_border_positions
                }

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

            # 6. Conditional formatting (combining conditional_rules with convenience parameters)
            final_conditional_rules = []
            if conditional_rules:
                final_conditional_rules.extend(conditional_rules)
            
            # Add simple conditional rule from convenience parameters
            if condition_type:
                condition = {}
                if condition_type in ["NUMBER_GREATER", "NUMBER_LESS", "NUMBER_EQ"]:
                    if condition_value is not None:
                        condition = {
                            "type": condition_type,
                            "values": [{"userEnteredValue": str(condition_value)}]
                        }
                elif condition_type in ["TEXT_CONTAINS", "TEXT_EQ"]:
                    if condition_value is not None:
                        condition = {
                            "type": condition_type,
                            "values": [{"userEnteredValue": str(condition_value)}]
                        }
                elif condition_type == "CUSTOM_FORMULA":
                    if condition_value is not None:
                        condition = {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": str(condition_value)}]
                        }
                elif condition_type in ["BLANK", "NOT_BLANK"]:
                    condition = {"type": condition_type}
                
                if condition:
                    # Build format for condition
                    format_dict = {}
                    if parsed_condition_bg_color:
                        format_dict["backgroundColor"] = parsed_condition_bg_color
                    if (parsed_condition_text_color or condition_format_bold is not None
                        or condition_format_italic is not None):
                        text_format = {}
                        if parsed_condition_text_color:
                            text_format["foregroundColor"] = parsed_condition_text_color
                        if condition_format_bold is not None:
                            text_format["bold"] = condition_format_bold
                        if condition_format_italic is not None:
                            text_format["italic"] = condition_format_italic
                        format_dict["textFormat"] = text_format
                    
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
                    final_conditional_rules.append(rule)
            
            # Add conditional formatting rules
            for rule in final_conditional_rules:
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": rule,
                        "index": 0  # Add at the beginning (highest priority)
                    }
                })
            
            if final_conditional_rules:
                formatting_details["conditionalFormatting"] = len(final_conditional_rules)

            # 7. Freeze rows/columns
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
