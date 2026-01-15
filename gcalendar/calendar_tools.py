"""
Google Calendar MCP Tools for FastMCP2.

This module provides MCP tools for interacting with Google Calendar API.
Migrated from decorator-based pattern to FastMCP2 architecture.
"""

import asyncio
import datetime
import json
import re
from datetime import timedelta, timezone
from functools import wraps
from typing import Union

from fastmcp import Context, FastMCP
from googleapiclient.errors import HttpError
from pydantic import Field
from typing_extensions import Annotated, Any, Dict, List, Optional

from auth.service_helpers import get_service
from config.enhanced_logging import setup_logger
from tools.common_types import UserGoogleEmailCalendar

from .calendar_types import (
    BulkCreateEventResponse,
    BulkEventResult,
    BulkOperationResult,
    BulkOperationsResponse,
    CalendarInfo,
    CalendarListResponse,
    CreateCalendarResponse,
    CreateEventResponse,
    DeleteEventResponse,
    EventData,
    EventInfo,
    EventListResponse,
    GetEventResponse,
    ModifyEventResponse,
    MoveEventResult,
    MoveEventsResponse,
)

logger = setup_logger()


# Export tools at module level for import compatibility
__all__ = [
    "list_calendars",
    "list_events",
    "create_event",
    "modify_event",
    "delete_event",
    "get_event",
    "create_calendar",
    "bulk_calendar_operations",
    "move_events_between_calendars",
    "setup_calendar_tools",
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _correct_time_format_for_api(
    time_str: Optional[str], param_name: str
) -> Optional[str]:
    """
    Helper function to ensure time strings for API calls are correctly formatted.

    Args:
        time_str: Time string to format
        param_name: Name of the parameter for logging

    Returns:
        Correctly formatted time string or None
    """
    if not time_str:
        return None

    logger.info(
        f"_correct_time_format_for_api: Processing {param_name} with value '{time_str}'"
    )

    # Handle date-only format (YYYY-MM-DD)
    if len(time_str) == 10 and time_str.count("-") == 2:
        try:
            # Validate it's a proper date
            datetime.datetime.strptime(time_str, "%Y-%m-%d")
            # For date-only, append T00:00:00Z to make it RFC3339 compliant
            formatted = f"{time_str}T00:00:00Z"
            logger.info(
                f"Formatting date-only {param_name} '{time_str}' to RFC3339: '{formatted}'"
            )
            return formatted
        except ValueError:
            logger.warning(
                f"{param_name} '{time_str}' looks like a date but is not valid YYYY-MM-DD. Using as is."
            )
            return time_str

    # Specifically address YYYY-MM-DDTHH:MM:SS by appending 'Z'
    if (
        len(time_str) == 19
        and time_str[10] == "T"
        and time_str.count(":") == 2
        and not (
            time_str.endswith("Z") or ("+" in time_str[10:]) or ("-" in time_str[10:])
        )
    ):
        try:
            # Validate the format before appending 'Z'
            datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
            logger.info(
                f"Formatting {param_name} '{time_str}' by appending 'Z' for UTC."
            )
            return time_str + "Z"
        except ValueError:
            logger.warning(
                f"{param_name} '{time_str}' looks like it needs 'Z' but is not valid YYYY-MM-DDTHH:MM:SS. Using as is."
            )
            return time_str

    # If it already has timezone info or doesn't match our patterns, return as is
    logger.info(f"{param_name} '{time_str}' doesn't need formatting, using as is.")
    return time_str


# ============================================================================
# SERVICE HELPER FUNCTIONS
# ============================================================================


async def _get_service_with_fallback(service_name: str, user_google_email: str):
    """
    Generic service getter with fallback to direct creation.

    Args:
        service_name: Name of the Google service (e.g., 'calendar', 'drive')
        user_google_email: User's email address

    Returns:
        Service object
    """
    try:
        return await get_service(service_name, user_google_email)
    except Exception as e:
        logger.warning(f"Failed to get {service_name} service via middleware: {e}")
        logger.info(f"Falling back to direct service creation for {service_name}")
        return await get_service(service_name, user_google_email)


async def _get_calendar_service_with_fallback(user_google_email: str):
    """Get Calendar service with fallback to direct creation."""
    return await _get_service_with_fallback("calendar", user_google_email)


async def _get_drive_service_with_fallback(user_google_email: str):
    """Get Drive service with fallback to direct creation."""
    return await _get_service_with_fallback("drive", user_google_email)


# ============================================================================
# ERROR HANDLING DECORATORS
# ============================================================================


def handle_calendar_errors(func):
    """Decorator to handle common calendar API errors."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HttpError as e:
            error_msg = f"❌ Failed in {func.__name__}: {e}"
            logger.error(f"[{func.__name__}] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error in {func.__name__}: {str(e)}"
            logger.error(f"[{func.__name__}] {error_msg}")
            return error_msg

    return wrapper


# ============================================================================
# BATCH OPERATION HELPERS
# ============================================================================


async def _batch_delete_events(
    calendar_service, event_ids: List[str], calendar_id: str = "primary"
) -> Dict[str, Any]:
    """
    Helper function to delete multiple events in batch.

    Args:
        calendar_service: Google Calendar service object
        event_ids: List of event IDs to delete
        calendar_id: Calendar ID (default: 'primary')

    Returns:
        Dictionary with results and errors
    """
    results = {"succeeded": [], "failed": [], "total": len(event_ids)}

    # Create batch request
    batch = calendar_service.new_batch_http_request()

    def callback(request_id, response, exception):
        """Callback for batch request."""
        if exception is not None:
            results["failed"].append(
                {"event_id": event_ids[int(request_id)], "error": str(exception)}
            )
        else:
            results["succeeded"].append(event_ids[int(request_id)])

    # Add delete requests to batch
    for idx, event_id in enumerate(event_ids):
        batch.add(
            calendar_service.events().delete(calendarId=calendar_id, eventId=event_id),
            request_id=str(idx),
            callback=callback,
        )

    # Execute batch request
    await asyncio.to_thread(batch.execute)

    return results


async def _batch_create_events(
    calendar_service,
    drive_service,
    events_data: List[Dict[str, Any]],
    calendar_id: str = "primary",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """
    Helper function to create multiple events in batch.

    Args:
        calendar_service: Google Calendar service object
        drive_service: Google Drive service object (for attachments)
        events_data: List of event data dictionaries
        calendar_id: Calendar ID (default: 'primary')
        ctx: Optional FastMCP context for progress reporting

    Returns:
        Dictionary with success and failure results
    """
    results = {"succeeded": [], "failed": [], "total": len(events_data)}

    # Create batch request
    batch = calendar_service.new_batch_http_request()

    # Store processed event bodies for the callback
    event_bodies = []

    def callback(request_id, response, exception):
        """Callback for batch request."""
        idx = int(request_id)
        event_data = events_data[idx]

        if exception is not None:
            failure_result: BulkEventResult = {
                "eventId": None,
                "summary": event_data.get("summary", "Unknown Event"),
                "start_time": event_data.get("start_time", ""),
                "htmlLink": None,
                "status": "failed",
                "error": str(exception),
                "input_data": event_data,
            }
            results["failed"].append(failure_result)
        else:
            success_result: BulkEventResult = {
                "eventId": response.get("id"),
                "summary": response.get(
                    "summary", event_data.get("summary", "Unknown Event")
                ),
                "start_time": event_data.get("start_time", ""),
                "htmlLink": response.get("htmlLink", ""),
                "status": "success",
                "error": None,
            }
            results["succeeded"].append(success_result)

    # Process each event and add to batch
    for idx, event_data in enumerate(events_data):
        # Report progress for each event being prepared
        if ctx:
            await ctx.report_progress(progress=idx, total=len(events_data))
            await ctx.info(
                f"Preparing event {idx + 1}/{len(events_data)}: {event_data.get('summary', 'No Title')}"
            )

        try:
            # Apply automatic timezone correction to timestamps
            corrected_start_time = _correct_time_format_for_api(
                event_data.get("start_time"), f"event[{idx}].start_time"
            )
            corrected_end_time = _correct_time_format_for_api(
                event_data.get("end_time"), f"event[{idx}].end_time"
            )

            # Build event body with corrected timestamps
            event_body: Dict[str, Any] = {
                "summary": event_data.get("summary", "No Title"),
                "start": (
                    {"date": corrected_start_time}
                    if "T" not in corrected_start_time
                    else {"dateTime": corrected_start_time}
                ),
                "end": (
                    {"date": corrected_end_time}
                    if "T" not in corrected_end_time
                    else {"dateTime": corrected_end_time}
                ),
            }

            # Add optional fields
            if event_data.get("description"):
                event_body["description"] = event_data["description"]
            if event_data.get("location"):
                event_body["location"] = event_data["location"]
            if event_data.get("timezone"):
                if "dateTime" in event_body["start"]:
                    event_body["start"]["timeZone"] = event_data["timezone"]
                if "dateTime" in event_body["end"]:
                    event_body["end"]["timeZone"] = event_data["timezone"]
            if event_data.get("attendees"):
                event_body["attendees"] = [
                    {"email": email} for email in event_data["attendees"]
                ]

            # Handle attachments
            if event_data.get("attachments") and drive_service:
                event_body["attachments"] = []
                attachments = event_data["attachments"]
                if isinstance(attachments, str):
                    attachments = [
                        a.strip() for a in attachments.split(",") if a.strip()
                    ]

                for att in attachments:
                    file_id = None
                    if att.startswith("https://"):
                        # Extract file ID from URL
                        match = re.search(r"(?:/d/|/file/d/|id=)([\w-]+)", att)
                        file_id = match.group(1) if match else None
                    else:
                        file_id = att

                    if file_id:
                        file_url = f"https://drive.google.com/open?id={file_id}"
                        mime_type = "application/vnd.google-apps.drive-sdk"
                        title = "Drive Attachment"

                        # Try to get metadata from Drive
                        try:
                            file_metadata = await asyncio.to_thread(
                                lambda: drive_service.files()
                                .get(fileId=file_id, fields="mimeType,name")
                                .execute()
                            )
                            mime_type = file_metadata.get("mimeType", mime_type)
                            filename = file_metadata.get("name")
                            if filename:
                                title = filename
                        except Exception:
                            pass  # Use defaults if metadata fetch fails

                        event_body["attachments"].append(
                            {
                                "fileUrl": file_url,
                                "title": title,
                                "mimeType": mime_type,
                            }
                        )

            event_bodies.append(event_body)

            # Add to batch
            if event_data.get("attachments"):
                batch.add(
                    calendar_service.events().insert(
                        calendarId=calendar_id,
                        body=event_body,
                        supportsAttachments=True,
                    ),
                    request_id=str(idx),
                    callback=callback,
                )
            else:
                batch.add(
                    calendar_service.events().insert(
                        calendarId=calendar_id, body=event_body
                    ),
                    request_id=str(idx),
                    callback=callback,
                )

        except Exception as e:
            # Handle individual event processing errors
            failure_result: BulkEventResult = {
                "eventId": None,
                "summary": event_data.get("summary", "Unknown Event"),
                "start_time": event_data.get("start_time", ""),
                "htmlLink": None,
                "status": "failed",
                "error": f"Pre-processing error: {str(e)}",
                "input_data": event_data,
            }
            results["failed"].append(failure_result)

    # Execute batch request
    if batch._order:  # Only execute if there are requests in the batch
        if ctx:
            await ctx.info(
                f"Executing batch creation for {len(batch._order)} events..."
            )
        await asyncio.to_thread(batch.execute)

    # Report final progress
    if ctx:
        await ctx.report_progress(progress=len(events_data), total=len(events_data))
        await ctx.info(
            f"Batch creation completed: {len(results['succeeded'])} succeeded, {len(results['failed'])} failed"
        )

    return results


# ============================================================================
# MAIN TOOL FUNCTIONS
# ============================================================================
# ============================================================================
# MODULE-LEVEL TOOL FUNCTIONS (Import-Compatible)
# ============================================================================


async def list_calendars(
    user_google_email: UserGoogleEmailCalendar = None,
) -> CalendarListResponse:
    """
    Retrieves a list of calendars accessible to the authenticated user.

    Args:
        user_google_email (str): The user's Google email address. Required.

    Returns:
        CalendarListResponse: Structured calendar list with metadata.
    """
    logger.info(f"[list_calendars] Invoked. Email: '{user_google_email}'")

    # Check for None/empty email
    if not user_google_email:
        error_msg = "user_google_email is required but was not provided (received None or empty string)"
        logger.error(f"[list_calendars] {error_msg}")
        return CalendarListResponse(
            calendars=[], count=0, userEmail=user_google_email or "", error=error_msg
        )

    try:
        calendar_service = await _get_calendar_service_with_fallback(user_google_email)

        calendar_list_response = await asyncio.to_thread(
            lambda: calendar_service.calendarList().list().execute()
        )
        items = calendar_list_response.get("items", [])

        # Convert to structured format
        calendars: List[CalendarInfo] = []
        for cal in items:
            calendar_info: CalendarInfo = {
                "id": cal.get("id", ""),
                "summary": cal.get("summary", "No Summary"),
                "description": cal.get("description"),
                "primary": cal.get("primary", False),
                "timeZone": cal.get("timeZone"),
                "backgroundColor": cal.get("backgroundColor"),
                "foregroundColor": cal.get("foregroundColor"),
            }
            calendars.append(calendar_info)

        logger.info(
            f"Successfully listed {len(calendars)} calendars for {user_google_email}."
        )

        return CalendarListResponse(
            calendars=calendars,
            count=len(calendars),
            userEmail=user_google_email,
            error=None,
        )

    except HttpError as e:
        error_msg = f"Failed to list calendars: {e}"
        logger.error(f"[list_calendars] HTTP error: {e}")
        # Return structured error response
        return CalendarListResponse(
            calendars=[], count=0, userEmail=user_google_email or "", error=error_msg
        )
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"[list_calendars] {error_msg}")
        # Return structured error response
        return CalendarListResponse(
            calendars=[], count=0, userEmail=user_google_email or "", error=error_msg
        )


def setup_calendar_tools(mcp: FastMCP) -> None:
    """
    Setup and register all Google Calendar tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up Google Calendar tools")

    @mcp.tool(
        name="list_calendars",
        description="Retrieves a list of calendars accessible to the authenticated user",
        tags={"calendar", "list", "google"},
        annotations={
            "title": "List Google Calendars",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def list_calendars_wrapper(
        user_google_email: UserGoogleEmailCalendar = None,
    ) -> CalendarListResponse:
        """Wrapper for the module-level list_calendars function."""
        return await list_calendars(user_google_email)

    @mcp.tool(
        name="create_calendar",
        description="Creates a new Google Calendar with specified properties",
        tags={"calendar", "create", "google"},
        annotations={
            "title": "Create New Calendar",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def create_calendar(
        summary: Annotated[
            str,
            Field(
                description="The name/title of the calendar",
                min_length=1,
                max_length=255,
            ),
        ],
        description: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional description of the calendar's purpose",
                max_length=1000,
            ),
        ] = None,
        time_zone: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Timezone for the calendar (e.g., 'America/New_York', 'Europe/London', 'UTC'). If not specified, uses the user's default timezone",
            ),
        ] = None,
        location: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Geographic location of the calendar (e.g., 'New York, NY', 'Conference Room A')",
                max_length=255,
            ),
        ] = None,
        user_google_email: UserGoogleEmailCalendar = None,
    ) -> CreateCalendarResponse:
        """
        Creates a new Google Calendar with specified properties.

        Args:
            user_google_email (str): The user's Google email address. Required.
            summary (str): The name/title of the calendar. Required.
            description (Optional[str]): Optional description of the calendar's purpose.
            time_zone (Optional[str]): Timezone for the calendar (e.g., 'America/New_York', 'UTC').
            location (Optional[str]): Geographic location of the calendar.

        Returns:
            CreateCalendarResponse: Structured response with created calendar details and status.
        """
        logger.info(
            f"[create_calendar] Creating calendar '{summary}' for {user_google_email}"
        )

        # Check for None/empty email
        if not user_google_email:
            error_msg = "user_google_email is required but was not provided (received None or empty string)"
            logger.error(f"[create_calendar] {error_msg}")
            return CreateCalendarResponse(
                success=False,
                calendarId=None,
                summary=summary,
                description=description,
                timeZone=time_zone,
                location=location,
                htmlLink=None,
                userEmail=user_google_email or "",
                message=f"❌ {error_msg}",
                error=error_msg,
            )

        try:
            calendar_service = await _get_calendar_service_with_fallback(
                user_google_email
            )

            # Build calendar body
            calendar_body: Dict[str, Any] = {"summary": summary.strip()}

            if description:
                calendar_body["description"] = description.strip()

            if time_zone:
                calendar_body["timeZone"] = time_zone

            if location:
                calendar_body["location"] = location.strip()

            # Create the calendar
            created_calendar = await asyncio.to_thread(
                lambda: calendar_service.calendars()
                .insert(body=calendar_body)
                .execute()
            )

            calendar_id = created_calendar.get("id")
            html_link = f"https://calendar.google.com/calendar/u/0?cid={calendar_id}"

            success_message = f"✅ Successfully created calendar '{created_calendar.get('summary')}' (ID: {calendar_id}) for {user_google_email}"
            logger.info(f"[create_calendar] {success_message}")

            return CreateCalendarResponse(
                success=True,
                calendarId=calendar_id,
                summary=created_calendar.get("summary"),
                description=created_calendar.get("description"),
                timeZone=created_calendar.get("timeZone"),
                location=created_calendar.get("location"),
                htmlLink=html_link,
                userEmail=user_google_email,
                message=success_message,
                error=None,
            )

        except HttpError as e:
            error_msg = f"Failed to create calendar: {e}"
            logger.error(f"[create_calendar] HTTP error: {e}")
            return CreateCalendarResponse(
                success=False,
                calendarId=None,
                summary=summary,
                description=description,
                timeZone=time_zone,
                location=location,
                htmlLink=None,
                userEmail=user_google_email,
                message=f"❌ {error_msg}",
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[create_calendar] {error_msg}")
            return CreateCalendarResponse(
                success=False,
                calendarId=None,
                summary=summary,
                description=description,
                timeZone=time_zone,
                location=location,
                htmlLink=None,
                userEmail=user_google_email,
                message=f"❌ {error_msg}",
                error=error_msg,
            )

    @mcp.tool(
        name="list_events",
        description="Retrieves a list of events from a specified Google Calendar within a given time range. By default, looks for events in the next 10 days starting from the current time.",
        tags={"calendar", "events", "get", "google", "list"},
        annotations={
            "title": "List Calendar Events",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def list_events(
        user_google_email: UserGoogleEmailCalendar = None,
        calendar_id: Annotated[
            str,
            Field(
                default="primary",
                description="The ID of the calendar to query. Use 'primary' for the user's primary calendar. Calendar IDs can be obtained using `list_calendars`",
            ),
        ] = "primary",
        time_min: Annotated[
            Optional[str],
            Field(
                default=None,
                description="The start of the time range (inclusive) in RFC3339 format (e.g., '2024-05-12T10:00:00Z' or '2024-05-12'). If omitted, defaults to the current time",
            ),
        ] = None,
        time_max: Annotated[
            Optional[str],
            Field(
                default=None,
                description="The end of the time range (exclusive) in RFC3339 format. If omitted, defaults to 10 days from the start time",
            ),
        ] = None,
        max_results: Annotated[
            int,
            Field(
                default=25,
                description="The maximum number of events to return",
                ge=1,
                le=2500,
            ),
        ] = 25,
    ) -> EventListResponse:
        """
        Retrieves a list of events from a specified Google Calendar within a given time range.
        By default, searches for events in the next 10 days starting from the current time.

        Args:
            user_google_email (str): The user's Google email address. Required.
            calendar_id (str): The ID of the calendar to query. Use 'primary' for the user's primary calendar. Defaults to 'primary'. Calendar IDs can be obtained using `list_calendars`.
            time_min (Optional[str]): The start of the time range (inclusive) in RFC3339 format (e.g., '2024-05-12T10:00:00Z' or '2024-05-12'). If omitted, defaults to the current time.
            time_max (Optional[str]): The end of the time range (exclusive) in RFC3339 format. If omitted, defaults to 10 days from the start time.
            max_results (int): The maximum number of events to return. Defaults to 25.

        Returns:
            EventListResponse: Structured event list with metadata.
        """
        logger.info(
            f"[list_events] Raw time parameters - time_min: '{time_min}', time_max: '{time_max}'"
        )

        # Check for None/empty email
        if not user_google_email:
            error_msg = "user_google_email is required but was not provided (received None or empty string)"
            logger.error(f"[list_events] {error_msg}")
            return EventListResponse(
                events=[],
                count=0,
                calendarId=calendar_id,
                timeMin=None,
                timeMax=None,
                userEmail=user_google_email or "",
                error=error_msg,
            )

        try:
            calendar_service = await _get_calendar_service_with_fallback(
                user_google_email
            )

            # Ensure time_min and time_max are correctly formatted for the API
            formatted_time_min = _correct_time_format_for_api(time_min, "time_min")
            effective_time_min = formatted_time_min or (
                datetime.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            if time_min is None:
                logger.info(
                    f"time_min not provided, defaulting to current UTC time: {effective_time_min}"
                )
            else:
                logger.info(
                    f"time_min processing: original='{time_min}', formatted='{formatted_time_min}', effective='{effective_time_min}'"
                )

            # Smart handling of timeMax with fallback logic
            effective_time_max = None
            if time_max:
                effective_time_max = _correct_time_format_for_api(time_max, "time_max")
                logger.info(
                    f"time_max processing: original='{time_max}', formatted='{effective_time_max}'"
                )
            else:
                # Default to 10 days from timeMin if not specified
                # This provides a reasonable default window for upcoming events
                try:
                    if effective_time_min:
                        # Parse the timeMin to add 10 days
                        # Remove 'Z' and parse ISO format
                        time_str = effective_time_min.rstrip("Z")
                        # Handle both date and datetime formats
                        if "T" in time_str:
                            time_min_dt = datetime.datetime.fromisoformat(time_str)
                        else:
                            # If it's just a date, parse it
                            time_min_dt = datetime.datetime.strptime(
                                time_str, "%Y-%m-%d"
                            )

                        # Add 10 days
                        time_max_dt = time_min_dt + timedelta(days=10)

                        # Format back to RFC3339 (handle timezone-aware datetimes correctly)
                        iso_string = time_max_dt.isoformat()
                        if iso_string.endswith("+00:00"):
                            # Replace +00:00 with Z for UTC
                            effective_time_max = iso_string.replace("+00:00", "Z")
                        elif (
                            "T" in iso_string
                            and not iso_string.endswith("Z")
                            and "+" not in iso_string
                            and "-" not in iso_string[-6:]
                        ):
                            # No timezone info, assume UTC and add Z
                            effective_time_max = iso_string + "Z"
                        else:
                            # Already has proper timezone info
                            effective_time_max = iso_string
                        logger.info(
                            f"time_max not provided, defaulting to 10 days from time_min: {effective_time_max}"
                        )
                except Exception as e:
                    logger.info(
                        f"Could not calculate default time_max (10 days from time_min): {e}. "
                        f"Omitting time_max to get all future events."
                    )
                    effective_time_max = None

            # Build API parameters dynamically to handle None values properly
            api_params = {
                "calendarId": calendar_id,
                "timeMin": effective_time_min,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }

            # Only add timeMax if it has a value (not None)
            if effective_time_max:
                api_params["timeMax"] = effective_time_max

            logger.info(f"[list_events] Final API parameters: {api_params}")

            events_result = await asyncio.to_thread(
                lambda: calendar_service.events().list(**api_params).execute()
            )
            items = events_result.get("items", [])

            # Convert to structured format
            events: List[EventInfo] = []
            for item in items:
                # Extract attendee emails
                attendee_emails = None
                if "attendees" in item:
                    attendee_emails = [
                        attendee.get("email", "") for attendee in item["attendees"]
                    ]

                event_info: EventInfo = {
                    "id": item.get("id", ""),
                    "summary": item.get("summary", "No Title"),
                    "description": item.get("description"),
                    "start": item["start"].get(
                        "dateTime", item["start"].get("date", "")
                    ),
                    "end": item["end"].get("dateTime", item["end"].get("date", "")),
                    "startTimeZone": (
                        item["start"].get("timeZone") if "start" in item else None
                    ),
                    "endTimeZone": (
                        item["end"].get("timeZone") if "end" in item else None
                    ),
                    "location": item.get("location"),
                    "htmlLink": item.get("htmlLink", ""),
                    "status": item.get("status"),
                    "creator": (
                        item.get("creator", {}).get("email")
                        if "creator" in item
                        else None
                    ),
                    "organizer": (
                        item.get("organizer", {}).get("email")
                        if "organizer" in item
                        else None
                    ),
                    "attendees": attendee_emails,
                    "attachments": item.get("attachments"),
                }
                events.append(event_info)

            logger.info(
                f"Successfully retrieved {len(events)} events for {user_google_email}."
            )

            return EventListResponse(
                events=events,
                count=len(events),
                calendarId=calendar_id,
                timeMin=effective_time_min,
                timeMax=effective_time_max,
                userEmail=user_google_email,
                error=None,
            )

        except HttpError as e:
            error_msg = f"Failed to get events: {e}"
            logger.error(f"[list_events] HTTP error: {e}")
            # Return structured error response
            return EventListResponse(
                events=[],
                count=0,
                calendarId=calendar_id,
                timeMin=(
                    effective_time_min if "effective_time_min" in locals() else None
                ),
                timeMax=(
                    effective_time_max if "effective_time_max" in locals() else None
                ),
                userEmail=user_google_email,
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[list_events] {error_msg}")
            # Return structured error response
            return EventListResponse(
                events=[],
                count=0,
                calendarId=calendar_id,
                timeMin=(
                    effective_time_min if "effective_time_min" in locals() else None
                ),
                timeMax=(
                    effective_time_max if "effective_time_max" in locals() else None
                ),
                userEmail=user_google_email,
                error=error_msg,
            )

    @mcp.tool(
        name="create_event",
        description="Create single or multiple events in Google Calendar. Supports both individual event creation (backward compatible) and bulk event creation for efficient batch operations. When creating multiple events, provides detailed success/failure reporting similar to the batch delete functionality.",
        tags={"calendar", "event", "create", "bulk", "google"},
        annotations={
            "title": "Create Calendar Event(s)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def create_event(
        ctx: Context,
        user_google_email: UserGoogleEmailCalendar = None,
        calendar_id: Annotated[
            str,
            Field(
                default="primary",
                description="Calendar ID where events will be created. Use 'primary' for the user's main calendar",
            ),
        ] = "primary",
        events: Annotated[
            Optional[Union[List[EventData], str]],
            Field(
                default=None,
                description="Array of event objects for bulk creation (or JSON string that will be parsed). Each event should contain: summary (required), start_time (required), end_time (required), and optional fields like description, location, attendees, timezone, attachments. When provided, uses bulk mode and ignores legacy single-event parameters",
            ),
        ] = None,
        # Legacy single-event parameters (backward compatibility)
        summary: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Event title/summary (legacy mode only - used when 'events' parameter is not provided)",
                min_length=1,
                max_length=1024,
            ),
        ] = None,
        start_time: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Event start time. Accepts: RFC3339 with timezone (e.g., '2025-01-01T10:00:00Z', '2025-01-01T10:00:00-05:00'), datetime without timezone (e.g., '2025-01-01T10:00:00' - will be treated as UTC), or date only for all-day events (e.g., '2025-01-01'). Missing timezone is automatically corrected to UTC. Legacy mode only",
            ),
        ] = None,
        end_time: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Event end time. Accepts: RFC3339 with timezone (e.g., '2025-01-01T11:00:00Z', '2025-01-01T11:00:00-05:00'), datetime without timezone (e.g., '2025-01-01T11:00:00' - will be treated as UTC), or date only for all-day events (e.g., '2025-01-02'). Missing timezone is automatically corrected to UTC. Legacy mode only",
            ),
        ] = None,
        description: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Event description/details. Supports plain text or basic HTML formatting (legacy mode only)",
                max_length=8192,
            ),
        ] = None,
        location: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Event location. Can be a physical address (e.g., '123 Main St, City, State') or virtual meeting link (e.g., 'https://meet.google.com/abc-defg-hij') (legacy mode only)",
                max_length=1024,
            ),
        ] = None,
        attendees: Annotated[
            Optional[List[str]],
            Field(
                default=None,
                description="List of attendee email addresses. Each attendee will receive an invitation (legacy mode only)",
                max_length=100,
            ),
        ] = None,
        timezone: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Timezone for the event (e.g., 'America/New_York', 'Europe/London', 'Asia/Tokyo', 'UTC'). Applied to both start and end times. If not specified, times are interpreted as UTC (legacy mode only)",
                pattern="^[A-Za-z]+/[A-Za-z_]+$",
            ),
        ] = None,
        attachments: Annotated[
            Optional[List[str]],
            Field(
                default=None,
                description="List of Google Drive file URLs (e.g., 'https://drive.google.com/file/d/FILE_ID') or direct file IDs to attach to the event. Files must be accessible to the calendar owner (legacy mode only)",
                max_length=25,
            ),
        ] = None,
    ) -> Union[CreateEventResponse, BulkCreateEventResponse]:
        """
        Create single or multiple events in Google Calendar.

        Args:
            user_google_email (str): The user's Google email address. Required.
            calendar_id (str): Calendar ID (default: 'primary').
            events (Optional[List[EventData]]): Array of events for bulk creation. If provided, uses bulk mode.

            # Legacy single-event parameters (backward compatibility):
            summary (Optional[str]): Event title (legacy mode only).
            start_time (Optional[str]): Start time (legacy mode only).
            end_time (Optional[str]): End time (legacy mode only).
            description (Optional[str]): Event description (legacy mode only).
            location (Optional[str]): Event location (legacy mode only).
            attendees (Optional[List[str]]): Attendee email addresses (legacy mode only).
            timezone (Optional[str]): Timezone (legacy mode only).
            attachments (Optional[List[str]]): Attachment file URLs/IDs (legacy mode only).

        Returns:
            Union[CreateEventResponse, BulkCreateEventResponse]: Single event response or bulk operation response.
        """
        # Check for None/empty email
        if not user_google_email:
            error_msg = "user_google_email is required but was not provided (received None or empty string)"
            logger.error(f"[create_event] {error_msg}")
            return CreateEventResponse(
                success=False,
                eventId=None,
                summary=None,
                htmlLink=None,
                start=None,
                end=None,
                calendarId=calendar_id,
                userEmail=user_google_email or "",
                message=f"❌ {error_msg}",
                error=error_msg,
            )

        # Parse events if it's a JSON string
        if events is not None and isinstance(events, str):
            try:
                import json

                parsed_events = json.loads(events)
                # Convert parsed dicts to EventData objects
                events = []
                for event_dict in parsed_events:
                    try:
                        event_data = EventData(**event_dict)
                        events.append(event_data)
                    except Exception as e:
                        logger.error(
                            f"[create_event] Failed to parse event data: {event_dict}. Error: {e}"
                        )
                        return BulkCreateEventResponse(
                            success=False,
                            totalProcessed=0,
                            eventsCreated=[],
                            eventsFailed=[],
                            calendarId=calendar_id,
                            userEmail=user_google_email,
                            message=f"❌ Failed to parse event data: {str(e)}",
                            error=f"Invalid event data format: {str(e)}",
                        )
                logger.info(
                    f"[create_event] Parsed JSON string into {len(events)} EventData objects"
                )
            except json.JSONDecodeError as e:
                logger.error(f"[create_event] Failed to parse JSON string: {e}")
                return BulkCreateEventResponse(
                    success=False,
                    totalProcessed=0,
                    eventsCreated=[],
                    eventsFailed=[],
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message=f"❌ Failed to parse JSON string: {str(e)}",
                    error=f"Invalid JSON format: {str(e)}",
                )
            except Exception as e:
                logger.error(f"[create_event] Unexpected error parsing events: {e}")
                return BulkCreateEventResponse(
                    success=False,
                    totalProcessed=0,
                    eventsCreated=[],
                    eventsFailed=[],
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message=f"❌ Unexpected error parsing events: {str(e)}",
                    error=f"Unexpected error: {str(e)}",
                )

        # Determine operation mode
        if events is not None:
            # BULK MODE: Create multiple events
            logger.info(
                f"[create_event] Bulk mode: {len(events)} events for {user_google_email}"
            )

            if not events:
                return BulkCreateEventResponse(
                    success=False,
                    totalProcessed=0,
                    eventsCreated=[],
                    eventsFailed=[],
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message="❌ No events provided for bulk creation",
                    error="No events provided",
                )

            try:
                calendar_service = await _get_calendar_service_with_fallback(
                    user_google_email
                )

                # Get Drive service for attachments (optional)
                drive_service = None
                try:
                    drive_service = await _get_drive_service_with_fallback(
                        user_google_email
                    )
                except Exception as e:
                    logger.warning(
                        f"Could not get Drive service for bulk operation: {e}"
                    )

                # Convert EventData Pydantic models to internal format with timezone correction
                events_data = []
                for i, event in enumerate(events):
                    # Apply automatic timezone correction
                    corrected_start = _correct_time_format_for_api(
                        event.start_time, f"events[{i}].start_time"
                    )
                    corrected_end = _correct_time_format_for_api(
                        event.end_time, f"events[{i}].end_time"
                    )

                    events_data.append(
                        {
                            "summary": event.summary,
                            "start_time": corrected_start,
                            "end_time": corrected_end,
                            "description": event.description,
                            "location": event.location,
                            "attendees": event.attendees,
                            "timezone": event.timezone,
                            "attachments": event.attachments,
                        }
                    )

                # Execute batch creation with progress reporting
                results = await _batch_create_events(
                    calendar_service, drive_service, events_data, calendar_id, ctx
                )

                # Format result message
                success_count = len(results["succeeded"])
                failure_count = len(results["failed"])
                total_count = results["total"]

                message_parts = [
                    "📊 **Bulk Event Creation Results**",
                    f"Total processed: {total_count}",
                    f"✅ Successfully created: {success_count}",
                    f"❌ Failed: {failure_count}",
                ]

                if results["succeeded"]:
                    message_parts.append("\n**Created Events (first 5):**")
                    for event in results["succeeded"][:5]:
                        message_parts.append(
                            f"  - {event['summary']} (ID: {event['eventId'][:8]}...)"
                        )
                    if len(results["succeeded"]) > 5:
                        message_parts.append(
                            f"  ... and {len(results['succeeded']) - 5} more"
                        )

                if results["failed"]:
                    message_parts.append("\n**Failed Events (first 3):**")
                    for event in results["failed"][:3]:
                        message_parts.append(
                            f"  - {event['summary']}: {event['error']}"
                        )
                    if len(results["failed"]) > 3:
                        message_parts.append(
                            f"  ... and {len(results['failed']) - 3} more failures"
                        )

                confirmation_message = "\n".join(message_parts)
                logger.info(
                    f"[create_event] Bulk operation completed: {success_count}/{total_count} succeeded"
                )

                return BulkCreateEventResponse(
                    success=(failure_count == 0),
                    totalProcessed=total_count,
                    eventsCreated=results["succeeded"],
                    eventsFailed=results["failed"],
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message=confirmation_message,
                    error=(
                        None
                        if failure_count == 0
                        else f"{failure_count} events failed to create"
                    ),
                )

            except Exception as e:
                error_msg = f"Bulk event creation failed: {str(e)}"
                logger.error(f"[create_event] Bulk operation error: {e}")
                return BulkCreateEventResponse(
                    success=False,
                    totalProcessed=len(events),
                    eventsCreated=[],
                    eventsFailed=[],
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message=f"❌ {error_msg}",
                    error=error_msg,
                )

        # LEGACY MODE: Single event creation (backward compatibility)
        elif summary and start_time and end_time:
            logger.info(
                f"[create_event] Legacy mode: Single event '{summary}' for {user_google_email}"
            )

            try:
                calendar_service = await _get_calendar_service_with_fallback(
                    user_google_email
                )

                # If attachments value is a string, split by comma and strip whitespace
                if attachments and isinstance(attachments, str):
                    attachments = [
                        a.strip() for a in attachments.split(",") if a.strip()
                    ]
                    logger.info(
                        f"[create_event] Parsed attachments list from string: {attachments}"
                    )

                # Apply automatic timezone correction to timestamps
                corrected_start_time = _correct_time_format_for_api(
                    start_time, "start_time"
                )
                corrected_end_time = _correct_time_format_for_api(end_time, "end_time")

                event_body: Dict[str, Any] = {
                    "summary": summary,
                    "start": (
                        {"date": corrected_start_time}
                        if "T" not in corrected_start_time
                        else {"dateTime": corrected_start_time}
                    ),
                    "end": (
                        {"date": corrected_end_time}
                        if "T" not in corrected_end_time
                        else {"dateTime": corrected_end_time}
                    ),
                }
                if location:
                    event_body["location"] = location
                if description:
                    event_body["description"] = description
                if timezone:
                    if "dateTime" in event_body["start"]:
                        event_body["start"]["timeZone"] = timezone
                    if "dateTime" in event_body["end"]:
                        event_body["end"]["timeZone"] = timezone
                if attendees:
                    event_body["attendees"] = [{"email": email} for email in attendees]

                if attachments:
                    # Accept both file URLs and file IDs. If a URL, extract the fileId.
                    event_body["attachments"] = []
                    drive_service = None
                    try:
                        drive_service = await _get_drive_service_with_fallback(
                            user_google_email
                        )
                    except Exception as e:
                        logger.warning(
                            f"Could not get Drive service for MIME type lookup: {e}"
                        )

                    for att in attachments:
                        file_id = None
                        if att.startswith("https://"):
                            # Match /d/<id>, /file/d/<id>, ?id=<id>
                            match = re.search(r"(?:/d/|/file/d/|id=)([\w-]+)", att)
                            file_id = match.group(1) if match else None
                            logger.info(
                                f"[create_event] Extracted file_id '{file_id}' from attachment URL '{att}'"
                            )
                        else:
                            file_id = att
                            logger.info(
                                f"[create_event] Using direct file_id '{file_id}' for attachment"
                            )
                        if file_id:
                            file_url = f"https://drive.google.com/open?id={file_id}"
                            mime_type = "application/vnd.google-apps.drive-sdk"
                            title = "Drive Attachment"
                            # Try to get the actual MIME type and filename from Drive
                            if drive_service:
                                try:
                                    file_metadata = await asyncio.to_thread(
                                        lambda: drive_service.files()
                                        .get(fileId=file_id, fields="mimeType,name")
                                        .execute()
                                    )
                                    mime_type = file_metadata.get("mimeType", mime_type)
                                    filename = file_metadata.get("name")
                                    if filename:
                                        title = filename
                                        logger.info(
                                            f"[create_event] Using filename '{filename}' as attachment title"
                                        )
                                    else:
                                        logger.info(
                                            "[create_event] No filename found, using generic title"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"Could not fetch metadata for file {file_id}: {e}"
                                    )
                            event_body["attachments"].append(
                                {
                                    "fileUrl": file_url,
                                    "title": title,
                                    "mimeType": mime_type,
                                }
                            )
                    created_event = await asyncio.to_thread(
                        lambda: calendar_service.events()
                        .insert(
                            calendarId=calendar_id,
                            body=event_body,
                            supportsAttachments=True,
                        )
                        .execute()
                    )
                else:
                    created_event = await asyncio.to_thread(
                        lambda: calendar_service.events()
                        .insert(calendarId=calendar_id, body=event_body)
                        .execute()
                    )
                link = created_event.get("htmlLink", "No link available")
                event_id = created_event.get("id")
                confirmation_message = f"Successfully created event '{created_event.get('summary', summary)}' for {user_google_email}. Link: {link}"
                logger.info(
                    f"Event created successfully for {user_google_email}. ID: {event_id}, Link: {link}"
                )

                return CreateEventResponse(
                    success=True,
                    eventId=event_id,
                    summary=created_event.get("summary", summary),
                    htmlLink=link,
                    start=start_time,
                    end=end_time,
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message=confirmation_message,
                    error=None,
                )

            except HttpError as e:
                error_msg = f"Failed to create event: {e}"
                logger.error(f"[create_event] HTTP error: {e}")
                return CreateEventResponse(
                    success=False,
                    eventId=None,
                    summary=summary,
                    htmlLink=None,
                    start=start_time,
                    end=end_time,
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message=f"❌ {error_msg}",
                    error=error_msg,
                )
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error(f"[create_event] {error_msg}")
                return CreateEventResponse(
                    success=False,
                    eventId=None,
                    summary=summary,
                    htmlLink=None,
                    start=start_time,
                    end=end_time,
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message=f"❌ {error_msg}",
                    error=error_msg,
                )

        # ERROR: Neither bulk nor legacy parameters provided
        else:
            error_msg = "Invalid parameters: Either provide 'events' array for bulk creation OR 'summary', 'start_time', 'end_time' for single event creation"
            logger.error(f"[create_event] {error_msg}")
            return CreateEventResponse(
                success=False,
                eventId=None,
                summary=None,
                htmlLink=None,
                start=None,
                end=None,
                calendarId=calendar_id,
                userEmail=user_google_email,
                message=f"❌ {error_msg}",
                error=error_msg,
            )

    @mcp.tool(
        name="modify_event",
        description="Modifies an existing event in Google Calendar",
        tags={"calendar", "event", "modify", "update", "google"},
        annotations={
            "title": "Modify Calendar Event",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def modify_event(
        event_id: Annotated[str, "The ID of the event to modify"],
        calendar_id: Annotated[
            str,
            Field(
                default="primary", description="Calendar ID where the event is located"
            ),
        ] = "primary",
        user_google_email: UserGoogleEmailCalendar = None,
        summary: Annotated[
            Optional[str], Field(default=None, description="New event title/summary")
        ] = None,
        start_time: Annotated[
            Optional[str],
            Field(
                default=None,
                description="New start time. Accepts: RFC3339 with timezone (e.g., '2023-10-27T10:00:00-07:00'), datetime without timezone (e.g., '2023-10-27T10:00:00' - will be treated as UTC), or date only for all-day events (e.g., '2023-10-27'). Missing timezone is automatically corrected to UTC",
            ),
        ] = None,
        end_time: Annotated[
            Optional[str],
            Field(
                default=None,
                description="New end time. Accepts: RFC3339 with timezone (e.g., '2023-10-27T11:00:00-07:00'), datetime without timezone (e.g., '2023-10-27T11:00:00' - will be treated as UTC), or date only for all-day events (e.g., '2023-10-28'). Missing timezone is automatically corrected to UTC",
            ),
        ] = None,
        description: Annotated[
            Optional[str],
            Field(default=None, description="New event description/details"),
        ] = None,
        location: Annotated[
            Optional[str],
            Field(
                default=None,
                description="New event location (e.g., '123 Main St' or 'https://meet.google.com/abc-defg-hij')",
            ),
        ] = None,
        attendees: Annotated[
            Optional[List[str]],
            Field(default=None, description="New list of attendee email addresses"),
        ] = None,
        timezone: Annotated[
            Optional[str],
            Field(
                default=None,
                description="New timezone for the event (e.g., 'America/New_York', 'UTC'). Applied to both start and end times",
            ),
        ] = None,
    ) -> ModifyEventResponse:
        """
        Modifies an existing event.

        Args:
            user_google_email (str): The user's Google email address. Required.
            event_id (str): The ID of the event to modify.
            calendar_id (str): Calendar ID (default: 'primary').
            summary (Optional[str]): New event title.
            start_time (Optional[str]): New start time (RFC3339, e.g., "2023-10-27T10:00:00-07:00" or "2023-10-27" for all-day).
            end_time (Optional[str]): New end time (RFC3339, e.g., "2023-10-27T11:00:00-07:00" or "2023-10-28" for all-day).
            description (Optional[str]): New event description.
            location (Optional[str]): New event location.
            attendees (Optional[List[str]]): New attendee email addresses.
            timezone (Optional[str]): New timezone (e.g., "America/New_York").

        Returns:
            ModifyEventResponse: Structured response with modified event details and status.
        """
        logger.info(
            f"[modify_event] Invoked. Email: '{user_google_email}', Event ID: {event_id}"
        )

        # Check for None/empty email
        if not user_google_email:
            error_msg = "user_google_email is required but was not provided (received None or empty string)"
            logger.error(f"[modify_event] {error_msg}")
            return ModifyEventResponse(
                success=False,
                eventId=event_id,
                summary=summary,
                htmlLink=None,
                calendarId=calendar_id,
                userEmail=user_google_email or "",
                fieldsModified=[],
                message=f"❌ {error_msg}",
                error=error_msg,
            )

        try:
            calendar_service = await _get_calendar_service_with_fallback(
                user_google_email
            )

            # Build the event body with only the fields that are provided
            event_body: Dict[str, Any] = {}
            fields_modified = []

            if summary is not None:
                event_body["summary"] = summary
                fields_modified.append("summary")
            if start_time is not None:
                # Apply automatic timezone correction
                corrected_start_time = _correct_time_format_for_api(
                    start_time, "start_time"
                )
                event_body["start"] = (
                    {"date": corrected_start_time}
                    if "T" not in corrected_start_time
                    else {"dateTime": corrected_start_time}
                )
                if timezone is not None and "dateTime" in event_body["start"]:
                    event_body["start"]["timeZone"] = timezone
                fields_modified.append("start_time")
            if end_time is not None:
                # Apply automatic timezone correction
                corrected_end_time = _correct_time_format_for_api(end_time, "end_time")
                event_body["end"] = (
                    {"date": corrected_end_time}
                    if "T" not in corrected_end_time
                    else {"dateTime": corrected_end_time}
                )
                if timezone is not None and "dateTime" in event_body["end"]:
                    event_body["end"]["timeZone"] = timezone
                fields_modified.append("end_time")
            if description is not None:
                event_body["description"] = description
                fields_modified.append("description")
            if location is not None:
                event_body["location"] = location
                fields_modified.append("location")
            if attendees is not None:
                event_body["attendees"] = [{"email": email} for email in attendees]
                fields_modified.append("attendees")
            if (
                timezone is not None
                and "start" not in event_body
                and "end" not in event_body
            ):
                # If timezone is provided but start/end times are not, we need to fetch the existing event
                # to apply the timezone correctly. This is a simplification; a full implementation
                # might handle this more robustly or require start/end with timezone.
                # For now, we'll log a warning and skip applying timezone if start/end are missing.
                logger.warning(
                    "[modify_event] Timezone provided but start_time and end_time are missing. Timezone will not be applied unless start/end times are also provided."
                )

            if not event_body:
                message = "No fields provided to modify the event."
                logger.warning(f"[modify_event] {message}")
                return ModifyEventResponse(
                    success=False,
                    eventId=event_id,
                    summary=None,
                    htmlLink=None,
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    fieldsModified=[],
                    message=f"❌ {message}",
                    error=message,
                )

            # Log the event ID for debugging
            logger.info(
                f"[modify_event] Attempting to update event with ID: '{event_id}' in calendar '{calendar_id}'"
            )

            # Try to get the event first to verify it exists
            try:
                await asyncio.to_thread(
                    lambda: calendar_service.events()
                    .get(calendarId=calendar_id, eventId=event_id)
                    .execute()
                )
                logger.info(
                    "[modify_event] Successfully verified event exists before update"
                )
            except HttpError as get_error:
                if get_error.resp.status == 404:
                    logger.error(
                        f"[modify_event] Event not found during pre-update verification: {get_error}"
                    )
                    message = f"Event not found during verification. The event with ID '{event_id}' could not be found in calendar '{calendar_id}'. This may be due to incorrect ID format or the event no longer exists."
                    return ModifyEventResponse(
                        success=False,
                        eventId=event_id,
                        summary=summary,
                        htmlLink=None,
                        calendarId=calendar_id,
                        userEmail=user_google_email,
                        fieldsModified=[],
                        message=f"❌ {message}",
                        error=message,
                    )
                else:
                    logger.warning(
                        f"[modify_event] Error during pre-update verification, but proceeding with update: {get_error}"
                    )

            # Proceed with the update
            updated_event = await asyncio.to_thread(
                lambda: calendar_service.events()
                .update(calendarId=calendar_id, eventId=event_id, body=event_body)
                .execute()
            )

            link = updated_event.get("htmlLink", "No link available")
            confirmation_message = f"Successfully modified event '{updated_event.get('summary', summary)}' (ID: {event_id}) for {user_google_email}. Link: {link}"
            logger.info(
                f"Event modified successfully for {user_google_email}. ID: {updated_event.get('id')}, Link: {link}"
            )

            return ModifyEventResponse(
                success=True,
                eventId=event_id,
                summary=updated_event.get("summary", summary),
                htmlLink=link,
                calendarId=calendar_id,
                userEmail=user_google_email,
                fieldsModified=fields_modified,
                message=confirmation_message,
                error=None,
            )

        except HttpError as e:
            error_msg = f"Failed to modify event: {e}"
            logger.error(f"[modify_event] HTTP error: {e}")
            return ModifyEventResponse(
                success=False,
                eventId=event_id,
                summary=summary,
                htmlLink=None,
                calendarId=calendar_id,
                userEmail=user_google_email,
                fieldsModified=[],
                message=f"❌ {error_msg}",
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[modify_event] {error_msg}")
            return ModifyEventResponse(
                success=False,
                eventId=event_id,
                summary=summary,
                htmlLink=None,
                calendarId=calendar_id,
                userEmail=user_google_email,
                fieldsModified=[],
                message=f"❌ {error_msg}",
                error=error_msg,
            )

    @mcp.tool(
        name="delete_event",
        description="Deletes one or more events from Google Calendar. Supports single event ID, comma-separated IDs, JSON array strings, or native list format for batch deletion.",
        tags={"calendar", "event", "delete", "batch", "google"},
        annotations={
            "title": "Delete Calendar Event(s)",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def delete_event(
        event_id: Annotated[
            Union[str, List[str]],
            Field(
                description="Single event ID, comma-separated string of IDs (e.g., 'id1,id2,id3'), JSON array string (e.g., '[\"id1\",\"id2\"]'), or list of event IDs"
            ),
        ],
        calendar_id: Annotated[
            str,
            Field(
                default="primary", description="Calendar ID from which to delete events"
            ),
        ] = "primary",
        user_google_email: UserGoogleEmailCalendar = None,
    ) -> DeleteEventResponse:
        """
        Deletes one or more events from Google Calendar.

        Args:
            user_google_email (str): The user's Google email address. Required.
            event_id (Union[str, List[str]]): Single event ID, comma-separated string of IDs, JSON array string, or list of event IDs.
            calendar_id (str): Calendar ID (default: 'primary').

        Returns:
            DeleteEventResponse: Structured response with deletion results and status.
        """

        # Parse event_id to handle different input formats
        event_ids = []
        if isinstance(event_id, str):
            # First check if it's a JSON array string
            event_id = event_id.strip()
            if event_id.startswith("[") and event_id.endswith("]"):
                try:
                    # Parse JSON array
                    parsed_ids = json.loads(event_id)
                    if isinstance(parsed_ids, list):
                        event_ids = [str(eid).strip() for eid in parsed_ids if eid]
                        logger.info(
                            f"[delete_event] Parsed JSON array with {len(event_ids)} event IDs"
                        )
                    else:
                        # If parsing succeeds but it's not a list, treat as single ID
                        event_ids = [event_id]
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(
                        f"[delete_event] Failed to parse as JSON array: {e}. Treating as single ID."
                    )
                    event_ids = [event_id]
            # Check if it's a comma-separated string
            elif "," in event_id:
                event_ids = [eid.strip() for eid in event_id.split(",") if eid.strip()]
                logger.info(
                    f"[delete_event] Parsed comma-separated string with {len(event_ids)} event IDs"
                )
            else:
                # Single event ID
                event_ids = [event_id.strip()]
                logger.info(f"[delete_event] Single event ID: {event_id}")
        elif isinstance(event_id, list):
            # Already a list, just clean up the IDs
            event_ids = [str(eid).strip() for eid in event_id if eid]
            logger.info(f"[delete_event] Received list with {len(event_ids)} event IDs")

        if not event_ids:
            return DeleteEventResponse(
                success=False,
                eventsDeleted=[],
                eventsFailed=[],
                totalProcessed=0,
                calendarId=calendar_id,
                userEmail=user_google_email,
                message="❌ No event IDs provided for deletion",
                error="No event IDs provided",
            )

        logger.info(
            f"[delete_event] Invoked. Email: '{user_google_email}', Event count: {len(event_ids)}"
        )

        # Check for None/empty email
        if not user_google_email:
            error_msg = "user_google_email is required but was not provided (received None or empty string)"
            logger.error(f"[delete_event] {error_msg}")
            return DeleteEventResponse(
                success=False,
                eventsDeleted=[],
                eventsFailed=[],
                totalProcessed=0,
                calendarId=calendar_id,
                userEmail=user_google_email or "",
                message=f"❌ {error_msg}",
                error=error_msg,
            )

        try:
            calendar_service = await _get_calendar_service_with_fallback(
                user_google_email
            )

            # Handle single event deletion
            if len(event_ids) == 1:
                event_id_single = event_ids[0]
                logger.info(
                    f"[delete_event] Single event deletion for ID: '{event_id_single}'"
                )

                # Try to get the event first to verify it exists
                try:
                    await asyncio.to_thread(
                        lambda: calendar_service.events()
                        .get(calendarId=calendar_id, eventId=event_id_single)
                        .execute()
                    )
                    logger.info(
                        "[delete_event] Successfully verified event exists before deletion"
                    )
                except HttpError as get_error:
                    if get_error.resp.status == 404:
                        logger.error(f"[delete_event] Event not found: {get_error}")
                        message = f"Event not found. The event with ID '{event_id_single}' could not be found in calendar '{calendar_id}'."
                        return DeleteEventResponse(
                            success=False,
                            eventsDeleted=[],
                            eventsFailed=[
                                {
                                    "event_id": event_id_single,
                                    "error": "Event not found",
                                }
                            ],
                            totalProcessed=1,
                            calendarId=calendar_id,
                            userEmail=user_google_email,
                            message=f"❌ {message}",
                            error=message,
                        )
                    else:
                        logger.warning(
                            f"[delete_event] Error during verification, proceeding: {get_error}"
                        )

                # Proceed with single deletion
                await asyncio.to_thread(
                    lambda: calendar_service.events()
                    .delete(calendarId=calendar_id, eventId=event_id_single)
                    .execute()
                )

                confirmation_message = f"✅ Successfully deleted event (ID: {event_id_single}) from calendar '{calendar_id}' for {user_google_email}."
                logger.info(f"Event deleted successfully. ID: {event_id_single}")
                return DeleteEventResponse(
                    success=True,
                    eventsDeleted=[event_id_single],
                    eventsFailed=[],
                    totalProcessed=1,
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message=confirmation_message,
                    error=None,
                )

            # Handle batch deletion for multiple events
            else:
                logger.info(
                    f"[delete_event] Batch deletion for {len(event_ids)} events"
                )
                logger.debug(f"[delete_event] Event IDs to delete: {event_ids}")

                # Use batch delete helper
                results = await _batch_delete_events(
                    calendar_service, event_ids, calendar_id
                )

                # Format result message
                success_count = len(results["succeeded"])
                failure_count = len(results["failed"])
                total_count = results["total"]

                message_parts = [
                    f"📊 **Batch Delete Results for {user_google_email}**",
                    f"Total events processed: {total_count}",
                    f"✅ Successfully deleted: {success_count}",
                    f"❌ Failed to delete: {failure_count}",
                ]

                if results["succeeded"]:
                    message_parts.append("\n**Deleted Event IDs:**")
                    for evt_id in results["succeeded"][:10]:  # Show first 10
                        message_parts.append(f"  - {evt_id}")
                    if len(results["succeeded"]) > 10:
                        message_parts.append(
                            f"  ... and {len(results['succeeded']) - 10} more"
                        )

                if results["failed"]:
                    message_parts.append("\n**Failed Deletions:**")
                    for failure in results["failed"][:5]:  # Show first 5 failures
                        message_parts.append(
                            f"  - {failure['event_id']}: {failure['error']}"
                        )
                    if len(results["failed"]) > 5:
                        message_parts.append(
                            f"  ... and {len(results['failed']) - 5} more failures"
                        )

                confirmation_message = "\n".join(message_parts)
                logger.info(
                    f"[delete_event] Batch operation completed: {success_count}/{total_count} succeeded"
                )

                return DeleteEventResponse(
                    success=(failure_count == 0),
                    eventsDeleted=results["succeeded"],
                    eventsFailed=results["failed"],
                    totalProcessed=total_count,
                    calendarId=calendar_id,
                    userEmail=user_google_email,
                    message=confirmation_message,
                    error=(
                        None
                        if failure_count == 0
                        else f"{failure_count} events failed to delete"
                    ),
                )

        except HttpError as e:
            error_msg = f"Failed to delete event(s): {e}"
            logger.error(f"[delete_event] HTTP error: {e}")
            return DeleteEventResponse(
                success=False,
                eventsDeleted=[],
                eventsFailed=[],
                totalProcessed=0,
                calendarId=calendar_id,
                userEmail=user_google_email,
                message=f"❌ {error_msg}",
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[delete_event] {error_msg}")
            return DeleteEventResponse(
                success=False,
                eventsDeleted=[],
                eventsFailed=[],
                totalProcessed=0,
                calendarId=calendar_id,
                userEmail=user_google_email,
                message=f"❌ {error_msg}",
                error=error_msg,
            )

    @mcp.tool(
        name="bulk_calendar_operations",
        description="Perform bulk operations on calendar events with filters (date range, title pattern, etc.)",
        tags={"calendar", "event", "bulk", "filter", "google"},
        annotations={
            "title": "Bulk Calendar Operations",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def bulk_calendar_operations(
        operation: Annotated[
            str,
            Field(description="Operation to perform", pattern="^(delete|list|export)$"),
        ],
        calendar_id: Annotated[
            str, Field(default="primary", description="Calendar ID to operate on")
        ] = "primary",
        time_min: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Start of time range in RFC3339 format (e.g., '2024-01-01T00:00:00Z'). Defaults to 30 days ago if not specified",
            ),
        ] = None,
        time_max: Annotated[
            Optional[str],
            Field(
                default=None,
                description="End of time range in RFC3339 format (e.g., '2024-12-31T23:59:59Z')",
            ),
        ] = None,
        title_pattern: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Regex pattern to match event titles (case-insensitive)",
            ),
        ] = None,
        location_pattern: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Regex pattern to match event locations (case-insensitive)",
            ),
        ] = None,
        attendee_email: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Filter events by specific attendee email address",
            ),
        ] = None,
        max_results: Annotated[
            int,
            Field(
                default=100,
                description="Maximum number of events to process",
                ge=1,
                le=2500,
            ),
        ] = 100,
        dry_run: Annotated[
            bool,
            Field(
                default=True,
                description="If True, only preview what would be affected without making changes",
            ),
        ] = True,
        user_google_email: UserGoogleEmailCalendar = None,
    ) -> BulkOperationsResponse:
        """
        Perform bulk operations on calendar events with various filters.

        Args:
            user_google_email (str): The user's Google email address. Required.
            operation (str): Operation to perform ('delete', 'list', 'export').
            calendar_id (str): Calendar ID (default: 'primary').
            time_min (Optional[str]): Start of time range (RFC3339 format).
            time_max (Optional[str]): End of time range (RFC3339 format).
            title_pattern (Optional[str]): Regex pattern to match event titles.
            location_pattern (Optional[str]): Regex pattern to match event locations.
            attendee_email (Optional[str]): Filter events by attendee email.
            max_results (int): Maximum number of events to process (default: 100).
            dry_run (bool): If True, only preview what would be affected (default: True).

        Returns:
            BulkOperationsResponse: Structured response with operation results and status.
        """
        logger.info(
            f"[bulk_calendar_operations] Operation: {operation}, Dry run: {dry_run}"
        )

        # Check for None/empty email
        if not user_google_email:
            error_msg = "user_google_email is required but was not provided (received None or empty string)"
            logger.error(f"[bulk_calendar_operations] {error_msg}")
            return BulkOperationsResponse(
                success=False,
                operation=operation,
                calendarId=calendar_id,
                userEmail=user_google_email or "",
                totalFound=0,
                totalMatched=0,
                totalProcessed=0,
                results=[],
                filters={
                    "timeMin": None,
                    "timeMax": None,
                    "titlePattern": title_pattern,
                    "locationPattern": location_pattern,
                    "attendeeEmail": attendee_email,
                },
                dryRun=dry_run,
                message=f"❌ {error_msg}",
                error=error_msg,
            )

        try:
            calendar_service = await _get_calendar_service_with_fallback(
                user_google_email
            )

            # Format time parameters
            formatted_time_min = (
                _correct_time_format_for_api(time_min, "time_min") if time_min else None
            )
            formatted_time_max = (
                _correct_time_format_for_api(time_max, "time_max") if time_max else None
            )

            # If no time range specified, default to last 30 days
            if not formatted_time_min:
                formatted_time_min = (
                    datetime.datetime.now(timezone.utc) - timedelta(days=30)
                ).isoformat() + "Z"

            # Build API parameters
            api_params = {
                "calendarId": calendar_id,
                "timeMin": formatted_time_min,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }

            if formatted_time_max:
                api_params["timeMax"] = formatted_time_max

            # Fetch events
            events_result = await asyncio.to_thread(
                lambda: calendar_service.events().list(**api_params).execute()
            )
            all_events = events_result.get("items", [])

            # Apply filters
            filtered_events = []
            for event in all_events:
                # Check title pattern
                if title_pattern:
                    if not re.search(
                        title_pattern, event.get("summary", ""), re.IGNORECASE
                    ):
                        continue

                # Check location pattern
                if location_pattern:
                    if not re.search(
                        location_pattern, event.get("location", ""), re.IGNORECASE
                    ):
                        continue

                # Check attendee email
                if attendee_email:
                    attendees = event.get("attendees", [])
                    if not any(
                        att.get("email", "").lower() == attendee_email.lower()
                        for att in attendees
                    ):
                        continue

                filtered_events.append(event)

            # Format results
            message_parts = [
                f"📊 **Bulk Operation: {operation.upper()}**",
                f"Calendar: {calendar_id}",
                f"Time range: {formatted_time_min[:10]} to {formatted_time_max[:10] if formatted_time_max else 'Future'}",
                f"Total events found: {len(all_events)}",
                f"Events matching filters: {len(filtered_events)}",
            ]

            if title_pattern:
                message_parts.append(f"Title pattern: '{title_pattern}'")
            if location_pattern:
                message_parts.append(f"Location pattern: '{location_pattern}'")
            if attendee_email:
                message_parts.append(f"Attendee filter: {attendee_email}")

            message_parts.append(
                f"\n**{'Preview' if dry_run else 'Processing'} Events:**"
            )

            # Show sample of affected events
            for idx, event in enumerate(filtered_events[:10]):
                start = event["start"].get("dateTime", event["start"].get("date", ""))
                message_parts.append(
                    f"{idx + 1}. {event.get('summary', 'No Title')} - {start[:16]} (ID: {event['id'][:8]}...)"
                )

            if len(filtered_events) > 10:
                message_parts.append(f"... and {len(filtered_events) - 10} more events")

            # Perform operation if not dry run
            if not dry_run and operation == "delete":
                event_ids = [event["id"] for event in filtered_events]
                if event_ids:
                    results = await _batch_delete_events(
                        calendar_service, event_ids, calendar_id
                    )
                    message_parts.append("\n**Deletion Results:**")
                    message_parts.append(f"✅ Deleted: {len(results['succeeded'])}")
                    message_parts.append(f"❌ Failed: {len(results['failed'])}")
            elif dry_run:
                message_parts.append("\n⚠️ **DRY RUN MODE** - No changes made")
                message_parts.append(
                    f"Set dry_run=false to execute the {operation} operation"
                )

            # Create structured results
            operation_results = []
            for event in filtered_events:
                result: BulkOperationResult = {
                    "eventId": event.get("id", ""),
                    "summary": event.get("summary", "No Title"),
                    "status": "preview" if dry_run else "pending",
                    "error": None,
                }
                operation_results.append(result)

            # Update status for completed operations
            if not dry_run and operation == "delete" and event_ids:
                for i, event_id in enumerate(event_ids):
                    if i < len(operation_results):
                        if event_id in results["succeeded"]:
                            operation_results[i]["status"] = "success"
                        else:
                            operation_results[i]["status"] = "failed"
                            # Find the error for this event
                            for failure in results["failed"]:
                                if failure["event_id"] == event_id:
                                    operation_results[i]["error"] = failure["error"]
                                    break

            return BulkOperationsResponse(
                success=True,
                operation=operation,
                calendarId=calendar_id,
                userEmail=user_google_email,
                totalFound=len(all_events),
                totalMatched=len(filtered_events),
                totalProcessed=(
                    len(event_ids)
                    if not dry_run and operation == "delete" and event_ids
                    else 0
                ),
                results=operation_results[:20],  # Limit results for response size
                filters={
                    "timeMin": formatted_time_min,
                    "timeMax": formatted_time_max,
                    "titlePattern": title_pattern,
                    "locationPattern": location_pattern,
                    "attendeeEmail": attendee_email,
                },
                dryRun=dry_run,
                message="\n".join(message_parts),
                error=None,
            )

        except Exception as e:
            error_msg = f"Bulk operation failed: {str(e)}"
            logger.error(f"[bulk_calendar_operations] {error_msg}")
            return BulkOperationsResponse(
                success=False,
                operation=operation,
                calendarId=calendar_id,
                userEmail=user_google_email,
                totalFound=0,
                totalMatched=0,
                totalProcessed=0,
                results=[],
                filters={
                    "timeMin": (
                        formatted_time_min if "formatted_time_min" in locals() else None
                    ),
                    "timeMax": (
                        formatted_time_max if "formatted_time_max" in locals() else None
                    ),
                    "titlePattern": title_pattern,
                    "locationPattern": location_pattern,
                    "attendeeEmail": attendee_email,
                },
                dryRun=dry_run,
                message=f"❌ {error_msg}",
                error=error_msg,
            )

    @mcp.tool(
        name="move_events_between_calendars",
        description="Move events from one calendar to another with optional filters",
        tags={"calendar", "event", "move", "migrate", "google"},
        annotations={
            "title": "Move Events Between Calendars",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def move_events_between_calendars(
        source_calendar_id: Annotated[str, "Source calendar ID to move events from"],
        target_calendar_id: Annotated[str, "Target calendar ID to move events to"],
        time_min: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Start of time range in RFC3339 format. Defaults to current time if not specified",
            ),
        ] = None,
        time_max: Annotated[
            Optional[str],
            Field(default=None, description="End of time range in RFC3339 format"),
        ] = None,
        title_pattern: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Regex pattern to match event titles for selective migration",
            ),
        ] = None,
        max_results: Annotated[
            int,
            Field(
                default=50, description="Maximum number of events to move", ge=1, le=500
            ),
        ] = 50,
        delete_from_source: Annotated[
            bool,
            Field(
                default=False,
                description="If True, delete events from source after copying (move). If False, only copy events (duplicate)",
            ),
        ] = False,
        user_google_email: UserGoogleEmailCalendar = None,
    ) -> MoveEventsResponse:
        """
        Move or copy events from one calendar to another.

        Args:
            user_google_email (str): The user's Google email address. Required.
            source_calendar_id (str): Source calendar ID.
            target_calendar_id (str): Target calendar ID.
            time_min (Optional[str]): Start of time range (RFC3339 format).
            time_max (Optional[str]): End of time range (RFC3339 format).
            title_pattern (Optional[str]): Regex pattern to match event titles.
            max_results (int): Maximum number of events to move (default: 50).
            delete_from_source (bool): If True, delete from source after copying (default: False).

        Returns:
            MoveEventsResponse: Structured response with move operation results and status.
        """
        logger.info(
            f"[move_events_between_calendars] Moving from {source_calendar_id} to {target_calendar_id}"
        )

        # Check for None/empty email
        if not user_google_email:
            error_msg = "user_google_email is required but was not provided (received None or empty string)"
            logger.error(f"[move_events_between_calendars] {error_msg}")
            return MoveEventsResponse(
                success=False,
                sourceCalendarId=source_calendar_id,
                targetCalendarId=target_calendar_id,
                userEmail=user_google_email or "",
                totalFound=0,
                totalCopied=0,
                totalDeleted=0,
                results=[],
                message=f"❌ {error_msg}",
                error=error_msg,
            )

        try:
            calendar_service = await _get_calendar_service_with_fallback(
                user_google_email
            )

            # Format time parameters
            formatted_time_min = (
                _correct_time_format_for_api(time_min, "time_min") if time_min else None
            )
            formatted_time_max = (
                _correct_time_format_for_api(time_max, "time_max") if time_max else None
            )

            if not formatted_time_min:
                formatted_time_min = (
                    datetime.datetime.now(timezone.utc).isoformat() + "Z"
                )

            # Build API parameters
            api_params = {
                "calendarId": source_calendar_id,
                "timeMin": formatted_time_min,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }

            if formatted_time_max:
                api_params["timeMax"] = formatted_time_max

            # Fetch events from source
            events_result = await asyncio.to_thread(
                lambda: calendar_service.events().list(**api_params).execute()
            )
            source_events = events_result.get("items", [])

            # Apply title filter if specified
            if title_pattern:
                source_events = [
                    event
                    for event in source_events
                    if re.search(title_pattern, event.get("summary", ""), re.IGNORECASE)
                ]

            # Copy events to target calendar
            copied_events: List[MoveEventResult] = []
            failed_copies: List[MoveEventResult] = []

            for event in source_events:
                try:
                    # Create new event body (remove readonly fields)
                    new_event = {
                        "summary": event.get("summary", "No Title"),
                        "description": event.get("description"),
                        "location": event.get("location"),
                        "start": event.get("start"),
                        "end": event.get("end"),
                        "attendees": event.get("attendees", []),
                        "reminders": event.get("reminders"),
                    }

                    # Remove None values
                    new_event = {k: v for k, v in new_event.items() if v is not None}

                    # Create event in target calendar
                    created = await asyncio.to_thread(
                        lambda: calendar_service.events()
                        .insert(calendarId=target_calendar_id, body=new_event)
                        .execute()
                    )

                    result: MoveEventResult = {
                        "originalId": event["id"],
                        "newId": created["id"],
                        "summary": event.get("summary", "No Title"),
                        "status": "copied",
                        "error": None,
                    }
                    copied_events.append(result)

                except Exception as e:
                    result: MoveEventResult = {
                        "originalId": event["id"],
                        "newId": None,
                        "summary": event.get("summary", "No Title"),
                        "status": "failed",
                        "error": str(e),
                    }
                    failed_copies.append(result)

            # Delete from source if requested
            deleted_count = 0
            delete_failures = []
            if delete_from_source and copied_events:
                event_ids_to_delete = [e["originalId"] for e in copied_events]
                delete_results = await _batch_delete_events(
                    calendar_service, event_ids_to_delete, source_calendar_id
                )
                deleted_count = len(delete_results["succeeded"])

                # Update status for deleted events
                for event_result in copied_events:
                    if event_result["originalId"] in delete_results["succeeded"]:
                        event_result["status"] = "moved"
                    else:
                        # Find the delete error
                        for failure in delete_results["failed"]:
                            if failure["event_id"] == event_result["originalId"]:
                                delete_failures.append(failure)
                                break

            # Format results message
            message_parts = [
                "📋 **Calendar Migration Results**",
                f"Source: {source_calendar_id}",
                f"Target: {target_calendar_id}",
                f"Events found: {len(source_events)}",
                f"✅ Successfully copied: {len(copied_events)}",
                f"❌ Failed to copy: {len(failed_copies)}",
            ]

            if delete_from_source:
                message_parts.append(f"🗑️ Deleted from source: {deleted_count}")
                if delete_failures:
                    message_parts.append(
                        f"⚠️ Failed to delete from source: {len(delete_failures)}"
                    )

            if copied_events:
                message_parts.append("\n**Copied Events (first 5):**")
                for event in copied_events[:5]:
                    message_parts.append(f"  - {event['summary']}")
                if len(copied_events) > 5:
                    message_parts.append(f"  ... and {len(copied_events) - 5} more")

            if failed_copies:
                message_parts.append("\n**Failed Copies:**")
                for failure in failed_copies[:3]:
                    message_parts.append(
                        f"  - {failure['summary']}: {failure['error']}"
                    )

            # Combine all results
            all_results = copied_events + failed_copies

            return MoveEventsResponse(
                success=(len(failed_copies) == 0),
                sourceCalendarId=source_calendar_id,
                targetCalendarId=target_calendar_id,
                userEmail=user_google_email,
                totalFound=len(source_events),
                totalCopied=len(copied_events),
                totalDeleted=deleted_count,
                results=all_results[:20],  # Limit results for response size
                message="\n".join(message_parts),
                error=(
                    None
                    if len(failed_copies) == 0
                    else f"{len(failed_copies)} events failed to copy"
                ),
            )

        except Exception as e:
            error_msg = f"Move operation failed: {str(e)}"
            logger.error(f"[move_events_between_calendars] {error_msg}")
            return MoveEventsResponse(
                success=False,
                sourceCalendarId=source_calendar_id,
                targetCalendarId=target_calendar_id,
                userEmail=user_google_email,
                totalFound=0,
                totalCopied=0,
                totalDeleted=0,
                results=[],
                message=f"❌ {error_msg}",
                error=error_msg,
            )

    @mcp.tool(
        name="get_event",
        description="Retrieves the details of a single event by its ID from a specified Google Calendar",
        tags={"calendar", "event", "get", "google"},
        annotations={
            "title": "Get Calendar Event Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_event(
        event_id: Annotated[str, "The ID of the event to retrieve"],
        calendar_id: Annotated[
            str,
            Field(
                default="primary",
                description="The ID of the calendar containing the event",
            ),
        ] = "primary",
        user_google_email: UserGoogleEmailCalendar = None,
    ) -> GetEventResponse:
        """
        Retrieves the details of a single event by its ID from a specified Google Calendar.

        Args:
            user_google_email (str): The user's Google email address. Required.
            event_id (str): The ID of the event to retrieve. Required.
            calendar_id (str): The ID of the calendar to query. Defaults to 'primary'.

        Returns:
            GetEventResponse: Structured response with event details and status.
        """
        logger.info(
            f"[get_event] Invoked. Email: '{user_google_email}', Event ID: {event_id}"
        )

        # Check for None/empty email
        if not user_google_email:
            error_msg = "user_google_email is required but was not provided (received None or empty string)"
            logger.error(f"[get_event] {error_msg}")
            return GetEventResponse(
                success=False,
                eventId=event_id,
                summary=None,
                description=None,
                start=None,
                end=None,
                startTimeZone=None,
                endTimeZone=None,
                location=None,
                htmlLink=None,
                status=None,
                creator=None,
                organizer=None,
                attendees=None,
                attachments=None,
                calendarId=calendar_id,
                userEmail=user_google_email or "",
                message=f"❌ {error_msg}",
                error=error_msg,
            )

        try:
            calendar_service = await _get_calendar_service_with_fallback(
                user_google_email
            )

            event = await asyncio.to_thread(
                lambda: calendar_service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )

            # Extract attendee emails
            attendee_emails = None
            if "attendees" in event:
                attendee_emails = [
                    attendee.get("email", "") for attendee in event["attendees"]
                ]

            # Extract start and end times
            start_time = event["start"].get("dateTime", event["start"].get("date", ""))
            end_time = event["end"].get("dateTime", event["end"].get("date", ""))

            logger.info(
                f"[get_event] Successfully retrieved event {event_id} for {user_google_email}."
            )

            return GetEventResponse(
                success=True,
                eventId=event_id,
                summary=event.get("summary", "No Title"),
                description=event.get("description"),
                start=start_time,
                end=end_time,
                startTimeZone=(
                    event["start"].get("timeZone") if "start" in event else None
                ),
                endTimeZone=event["end"].get("timeZone") if "end" in event else None,
                location=event.get("location"),
                htmlLink=event.get("htmlLink", ""),
                status=event.get("status"),
                creator=(
                    event.get("creator", {}).get("email")
                    if "creator" in event
                    else None
                ),
                organizer=(
                    event.get("organizer", {}).get("email")
                    if "organizer" in event
                    else None
                ),
                attendees=attendee_emails,
                attachments=event.get("attachments"),
                calendarId=calendar_id,
                userEmail=user_google_email,
                message=f"Successfully retrieved event '{event.get('summary', 'No Title')}' (ID: {event_id})",
                error=None,
            )

        except HttpError as e:
            error_msg = f"Failed to get event: {e}"
            logger.error(f"[get_event] HTTP error: {e}")
            return GetEventResponse(
                success=False,
                eventId=event_id,
                summary=None,
                description=None,
                start=None,
                end=None,
                startTimeZone=None,
                endTimeZone=None,
                location=None,
                htmlLink=None,
                status=None,
                creator=None,
                organizer=None,
                attendees=None,
                attachments=None,
                calendarId=calendar_id,
                userEmail=user_google_email,
                message=f"❌ {error_msg}",
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[get_event] {error_msg}")
            return GetEventResponse(
                success=False,
                eventId=event_id,
                summary=None,
                description=None,
                start=None,
                end=None,
                startTimeZone=None,
                endTimeZone=None,
                location=None,
                htmlLink=None,
                status=None,
                creator=None,
                organizer=None,
                attendees=None,
                attachments=None,
                calendarId=calendar_id,
                userEmail=user_google_email,
                message=f"❌ {error_msg}",
                error=error_msg,
            )

    # Log successful setup
    tool_count = 9  # Total number of Calendar tools (added create_calendar)
    logger.info(f"Successfully registered {tool_count} Google Calendar tools")
