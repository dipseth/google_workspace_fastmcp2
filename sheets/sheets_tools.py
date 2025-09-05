"""
Google Sheets MCP Tools

This module provides MCP tools for interacting with Google Sheets API using the universal service architecture.
"""

import logging
import asyncio
from typing_extensions import List, Optional, Any

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
    CreateSheetResponse
)

# Configure module logger
logger = logging.getLogger(__name__)


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
        values: Optional[List[List[str]]] = None,
        value_input_option: str = "USER_ENTERED",
        clear_values: bool = False,
        user_google_email: UserGoogleEmailSheets = None
    ) -> SheetModifyResponse:
        """
        Modifies values in a specific range of a Google Sheet - can write, update, or clear values.

        Args:
            user_google_email (str): The user's Google email address. Required.
            spreadsheet_id (str): The ID of the spreadsheet. Required.
            range_name (str): The range to modify (e.g., "Sheet1!A1:D10", "A1:D10"). Required.
            values (Optional[List[List[str]]]): 2D array of values to write/update. Required unless clear_values=True.
            value_input_option (str): How to interpret input values ("RAW" or "USER_ENTERED"). Defaults to "USER_ENTERED".
            clear_values (bool): If True, clears the range instead of writing values. Defaults to False.

        Returns:
            SheetModifyResponse: Structured response with details of the modification operation.
        """
        operation = "clear" if clear_values else "write"
        logger.info(f"[modify_sheet_values] Invoked. Operation: {operation}, Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, Range: {range_name}")

        try:
            if not clear_values and not values:
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
                body = {"values": values}

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
        sheet_names: Optional[List[str]] = None
    ) -> CreateSpreadsheetResponse:
        """
        Creates a new Google Spreadsheet.

        Args:
            user_google_email (str): The user's Google email address. Required.
            title (str): The title of the new spreadsheet. Required.
            sheet_names (Optional[List[str]]): List of sheet names to create. If not provided, creates one sheet with default name.

        Returns:
            CreateSpreadsheetResponse: Structured response with information about the newly created spreadsheet.
        """
        logger.info(f"[create_spreadsheet] Invoked. Email: '{user_google_email}', Title: {title}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            spreadsheet_body = {
                "properties": {
                    "title": title
                }
            }

            if sheet_names:
                spreadsheet_body["sheets"] = [
                    {"properties": {"title": sheet_name}} for sheet_name in sheet_names
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
                sheets=sheet_names,
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
                sheets=sheet_names,
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
                sheets=sheet_names,
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

    logger.info("✅ Google Sheets tools setup complete")