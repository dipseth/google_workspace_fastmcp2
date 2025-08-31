"""
Google Sheets MCP Tools

This module provides MCP tools for interacting with Google Sheets API using the universal service architecture.
"""

import logging
import asyncio
from typing_extensions import List, Optional, Any

from fastmcp import FastMCP
from googleapiclient.errors import HttpError

from auth.service_helpers import request_service, get_injected_service, get_service
from .sheets_types import SpreadsheetListResponse, SpreadsheetInfo

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
        user_google_email: str,
        max_results: int = 25
    ) -> SpreadsheetListResponse:
        """
        Lists spreadsheets from Google Drive that the user has access to.

        Args:
            user_google_email (str): The user's Google email address. Required.
            max_results (int): Maximum number of spreadsheets to return. Defaults to 25.

        Returns:
            SpreadsheetListResponse: Structured list of spreadsheets with metadata.
        """
        logger.info(f"[list_spreadsheets] Invoked. Email: '{user_google_email}'")

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
                        return f"❌ Failed to create Google Drive service for {user_google_email}. Please check your credentials and permissions."
                else:
                    # Different type of RuntimeError, log and fail
                    logger.error(f"Drive service injection error for {user_google_email}: {e}")
                    return f"❌ Drive service injection error for {user_google_email}: {e}"
                    
            except Exception as e:
                logger.error(f"Unexpected error getting Drive service for {user_google_email}: {e}")
                return f"❌ Unexpected error getting Drive service for {user_google_email}: {e}"

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
            error_msg = f"❌ Failed to list spreadsheets: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error listing spreadsheets: {str(e)}"
            logger.error(error_msg)
            return error_msg

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
        user_google_email: str,
        spreadsheet_id: str
    ) -> str:
        """
        Gets information about a specific spreadsheet including its sheets.

        Args:
            user_google_email (str): The user's Google email address. Required.
            spreadsheet_id (str): The ID of the spreadsheet to get info for. Required.

        Returns:
            str: Formatted spreadsheet information including title and sheets list.
        """
        logger.info(f"[get_spreadsheet_info] Invoked. Email: '{user_google_email}', Spreadsheet ID: {spreadsheet_id}")

        try:
            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            spreadsheet = await asyncio.to_thread(
                sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute
            )

            title = spreadsheet.get("properties", {}).get("title", "Unknown")
            sheets = spreadsheet.get("sheets", [])

            sheets_info = []
            for sheet in sheets:
                sheet_props = sheet.get("properties", {})
                sheet_name = sheet_props.get("title", "Unknown")
                sheet_id = sheet_props.get("sheetId", "Unknown")
                grid_props = sheet_props.get("gridProperties", {})
                rows = grid_props.get("rowCount", "Unknown")
                cols = grid_props.get("columnCount", "Unknown")

                sheets_info.append(
                    f"  - \"{sheet_name}\" (ID: {sheet_id}) | Size: {rows}x{cols}"
                )

            text_output = (
                f"Spreadsheet: \"{title}\" (ID: {spreadsheet_id})\n"
                f"Sheets ({len(sheets)}):\n"
                + "\n".join(sheets_info) if sheets_info else "  No sheets found"
            )

            logger.info(f"Successfully retrieved info for spreadsheet {spreadsheet_id} for {user_google_email}.")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Failed to get spreadsheet info: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error getting spreadsheet info: {str(e)}"
            logger.error(error_msg)
            return error_msg

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
        user_google_email: str,
        spreadsheet_id: str,
        range_name: str = "A1:Z1000"
    ) -> str:
        """
        Reads values from a specific range in a Google Sheet.

        Args:
            user_google_email (str): The user's Google email address. Required.
            spreadsheet_id (str): The ID of the spreadsheet. Required.
            range_name (str): The range to read (e.g., "Sheet1!A1:D10", "A1:D10"). Defaults to "A1:Z1000".

        Returns:
            str: The formatted values from the specified range.
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
            if not values:
                return f"No data found in range '{range_name}' for {user_google_email}."

            # Format the output as a readable table
            formatted_rows = []
            for i, row in enumerate(values, 1):
                # Pad row with empty strings to show structure
                padded_row = row + [""] * max(0, len(values[0]) - len(row)) if values else row
                formatted_rows.append(f"Row {i:2d}: {padded_row}")

            text_output = (
                f"Successfully read {len(values)} rows from range '{range_name}' in spreadsheet {spreadsheet_id} for {user_google_email}:\n"
                + "\n".join(formatted_rows[:50])  # Limit to first 50 rows for readability
                + (f"\n... and {len(values) - 50} more rows" if len(values) > 50 else "")
            )

            logger.info(f"Successfully read {len(values)} rows for {user_google_email}.")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Failed to read sheet values: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error reading sheet values: {str(e)}"
            logger.error(error_msg)
            return error_msg

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
        user_google_email: str,
        spreadsheet_id: str,
        range_name: str,
        values: Optional[List[List[str]]] = None,
        value_input_option: str = "USER_ENTERED",
        clear_values: bool = False
    ) -> str:
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
            str: Confirmation message of the successful modification operation.
        """
        operation = "clear" if clear_values else "write"
        logger.info(f"[modify_sheet_values] Invoked. Operation: {operation}, Email: '{user_google_email}', Spreadsheet: {spreadsheet_id}, Range: {range_name}")

        try:
            if not clear_values and not values:
                return "❌ Either 'values' must be provided or 'clear_values' must be True."

            sheets_service = await _get_sheets_service_with_fallback(user_google_email)

            if clear_values:
                result = await asyncio.to_thread(
                    sheets_service.spreadsheets()
                    .values()
                    .clear(spreadsheetId=spreadsheet_id, range=range_name)
                    .execute
                )

                cleared_range = result.get("clearedRange", range_name)
                text_output = f"✅ Successfully cleared range '{cleared_range}' in spreadsheet {spreadsheet_id} for {user_google_email}."
                logger.info(f"Successfully cleared range '{cleared_range}' for {user_google_email}.")
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

                text_output = (
                    f"✅ Successfully updated range '{range_name}' in spreadsheet {spreadsheet_id} for {user_google_email}. "
                    f"Updated: {updated_cells} cells, {updated_rows} rows, {updated_columns} columns."
                )
                logger.info(f"Successfully updated {updated_cells} cells for {user_google_email}.")

            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Failed to modify sheet values: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error modifying sheet values: {str(e)}"
            logger.error(error_msg)
            return error_msg

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
        user_google_email: str,
        title: str,
        sheet_names: Optional[List[str]] = None
    ) -> str:
        """
        Creates a new Google Spreadsheet.

        Args:
            user_google_email (str): The user's Google email address. Required.
            title (str): The title of the new spreadsheet. Required.
            sheet_names (Optional[List[str]]): List of sheet names to create. If not provided, creates one sheet with default name.

        Returns:
            str: Information about the newly created spreadsheet including ID and URL.
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

            text_output = (
                f"✅ Successfully created spreadsheet '{title}' for {user_google_email}. "
                f"ID: {spreadsheet_id} | URL: {spreadsheet_url}"
            )

            logger.info(f"Successfully created spreadsheet for {user_google_email}. ID: {spreadsheet_id}")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Failed to create spreadsheet: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error creating spreadsheet: {str(e)}"
            logger.error(error_msg)
            return error_msg

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
        user_google_email: str,
        spreadsheet_id: str,
        sheet_name: str
    ) -> str:
        """
        Creates a new sheet within an existing spreadsheet.

        Args:
            user_google_email (str): The user's Google email address. Required.
            spreadsheet_id (str): The ID of the spreadsheet. Required.
            sheet_name (str): The name of the new sheet. Required.

        Returns:
            str: Confirmation message of the successful sheet creation.
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

            text_output = (
                f"✅ Successfully created sheet '{sheet_name}' (ID: {sheet_id}) in spreadsheet {spreadsheet_id} for {user_google_email}."
            )

            logger.info(f"Successfully created sheet for {user_google_email}. Sheet ID: {sheet_id}")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Failed to create sheet: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error creating sheet: {str(e)}"
            logger.error(error_msg)
            return error_msg

    logger.info("✅ Google Sheets tools setup complete")