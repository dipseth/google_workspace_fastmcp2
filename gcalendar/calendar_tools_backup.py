"""
Google Calendar MCP Tools for FastMCP2.

This module provides MCP tools for interacting with Google Calendar API.
Migrated from decorator-based pattern to FastMCP2 architecture.
"""

import datetime
from datetime import timezone
import logging
import asyncio
import re
from typing_extensions import List, Optional, Dict, Any, NotRequired
from googleapiclient.errors import HttpError
from fastmcp import FastMCP

from auth.service_helpers import get_service, request_service
from auth.context import get_injected_service
from .calendar_types import CalendarListResponse, EventListResponse, CalendarInfo, EventInfo

logger = logging.getLogger(__name__)


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

async def _get_calendar_service_with_fallback(user_google_email: str):
    """Get Calendar service with fallback to direct creation."""
    try:
        return await get_service("calendar", user_google_email)
    except Exception as e:
        logger.warning(f"Failed to get Calendar service via middleware: {e}")
        logger.info("Falling back to direct service creation")
        return await get_service("calendar", user_google_email)


async def _get_drive_service_with_fallback(user_google_email: str):
    """Get Drive service with fallback to direct creation."""
    try:
        return await get_service("drive", user_google_email)
    except Exception as e:
        logger.warning(f"Failed to get Drive service via middleware: {e}")
        logger.info("Falling back to direct service creation")
        return await get_service("drive", user_google_email)


# ============================================================================
# MAIN TOOL FUNCTIONS
# ============================================================================


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
            "openWorldHint": True
        }
    )
    async def list_calendars(user_google_email: str) -> CalendarListResponse:
        """
        Retrieves a list of calendars accessible to the authenticated user.

        Args:
            user_google_email (str): The user's Google email address. Required.

        Returns:
            CalendarListResponse: Structured calendar list with metadata.
        """
        logger.info(f"[list_calendars] Invoked. Email: '{user_google_email}'")

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
                    "foregroundColor": cal.get("foregroundColor")
                }
                calendars.append(calendar_info)
            
            logger.info(f"Successfully listed {len(calendars)} calendars for {user_google_email}.")
            
            return CalendarListResponse(
                calendars=calendars,
                count=len(calendars),
                userEmail=user_google_email,
                error=None
            )
            
        except HttpError as e:
            error_msg = f"Failed to list calendars: {e}"
            logger.error(f"[list_calendars] HTTP error: {e}")
            # Return structured error response
            return CalendarListResponse(
                calendars=[],
                count=0,
                userEmail=user_google_email,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[list_calendars] {error_msg}")
            # Return structured error response
            return CalendarListResponse(
                calendars=[],
                count=0,
                userEmail=user_google_email,
                error=error_msg
            )

    @mcp.tool(
        name="list_events",
        description="Retrieves a list of events from a specified Google Calendar within a given time range",
        tags={"calendar", "events", "get", "google","list"},
        annotations={
            "title": "Get Calendar Events",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_events(
        user_google_email: str,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 25,
    ) -> EventListResponse:
        """
        Retrieves a list of events from a specified Google Calendar within a given time range.

        Args:
            user_google_email (str): The user's Google email address. Required.
            calendar_id (str): The ID of the calendar to query. Use 'primary' for the user's primary calendar. Defaults to 'primary'. Calendar IDs can be obtained using `list_calendars`.
            time_min (Optional[str]): The start of the time range (inclusive) in RFC3339 format (e.g., '2024-05-12T10:00:00Z' or '2024-05-12'). If omitted, defaults to the current time.
            time_max (Optional[str]): The end of the time range (exclusive) in RFC3339 format. If omitted, events starting from `time_min` onwards are considered (up to `max_results`).
            max_results (int): The maximum number of events to return. Defaults to 25.

        Returns:
            EventListResponse: Structured event list with metadata.
        """
        logger.info(
            f"[list_events] Raw time parameters - time_min: '{time_min}', time_max: '{time_max}'"
        )

        try:
            calendar_service = await _get_calendar_service_with_fallback(user_google_email)
            
            # Ensure time_min and time_max are correctly formatted for the API
            formatted_time_min = _correct_time_format_for_api(time_min, "time_min")
            effective_time_min = formatted_time_min or (
                datetime.datetime.now(timezone.utc).isoformat() + "Z"
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
                # Default to 30 days from timeMin if not specified
                # This provides a reasonable default window for most use cases
                try:
                    if effective_time_min:
                        # Parse the timeMin to add 30 days
                        from datetime import datetime, timedelta
                        # Remove 'Z' and parse ISO format
                        time_str = effective_time_min.rstrip('Z')
                        # Handle both date and datetime formats
                        if 'T' in time_str:
                            time_min_dt = datetime.fromisoformat(time_str)
                        else:
                            # If it's just a date, parse it
                            time_min_dt = datetime.strptime(time_str, "%Y-%m-%d")
                        
                        # Add 30 days
                        time_max_dt = time_min_dt + timedelta(days=30)
                        
                        # Format back to RFC3339
                        effective_time_max = time_max_dt.isoformat() + 'Z'
                        logger.info(
                            f"time_max not provided, defaulting to 30 days from time_min: {effective_time_max}"
                        )
                except Exception as e:
                    logger.info(
                        f"Could not calculate default time_max (30 days from time_min): {e}. "
                        f"Omitting time_max to get all future events."
                    )
                    effective_time_max = None

            # Build API parameters dynamically to handle None values properly
            api_params = {
                "calendarId": calendar_id,
                "timeMin": effective_time_min,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime"
            }
            
            # Only add timeMax if it has a value (not None)
            if effective_time_max:
                api_params["timeMax"] = effective_time_max
                
            logger.info(
                f"[list_events] Final API parameters: {api_params}"
            )

            events_result = await asyncio.to_thread(
                lambda: calendar_service.events()
                .list(**api_params)
                .execute()
            )
            items = events_result.get("items", [])
            
            # Convert to structured format
            events: List[EventInfo] = []
            for item in items:
                # Extract attendee emails
                attendee_emails = None
                if "attendees" in item:
                    attendee_emails = [
                        attendee.get("email", "")
                        for attendee in item["attendees"]
                    ]
                
                event_info: EventInfo = {
                    "id": item.get("id", ""),
                    "summary": item.get("summary", "No Title"),
                    "description": item.get("description"),
                    "start": item["start"].get("dateTime", item["start"].get("date", "")),
                    "end": item["end"].get("dateTime", item["end"].get("date", "")),
                    "startTimeZone": item["start"].get("timeZone") if "start" in item else None,
                    "endTimeZone": item["end"].get("timeZone") if "end" in item else None,
                    "location": item.get("location"),
                    "htmlLink": item.get("htmlLink", ""),
                    "status": item.get("status"),
                    "creator": item.get("creator", {}).get("email") if "creator" in item else None,
                    "organizer": item.get("organizer", {}).get("email") if "organizer" in item else None,
                    "attendees": attendee_emails,
                    "attachments": item.get("attachments")
                }
                events.append(event_info)
            
            logger.info(f"Successfully retrieved {len(events)} events for {user_google_email}.")
            
            return EventListResponse(
                events=events,
                count=len(events),
                calendarId=calendar_id,
                timeMin=effective_time_min,
                timeMax=effective_time_max,
                userEmail=user_google_email,
                error=None
            )
            
        except HttpError as e:
            error_msg = f"Failed to get events: {e}"
            logger.error(f"[list_events] HTTP error: {e}")
            # Return structured error response
            return EventListResponse(
                events=[],
                count=0,
                calendarId=calendar_id,
                timeMin=effective_time_min if 'effective_time_min' in locals() else None,
                timeMax=effective_time_max if 'effective_time_max' in locals() else None,
                userEmail=user_google_email,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"[list_events] {error_msg}")
            # Return structured error response
            return EventListResponse(
                events=[],
                count=0,
                calendarId=calendar_id,
                timeMin=effective_time_min if 'effective_time_min' in locals() else None,
                timeMax=effective_time_max if 'effective_time_max' in locals() else None,
                userEmail=user_google_email,
                error=error_msg
            )

    @mcp.tool(
        name="create_event",
        description="Creates a new event in Google Calendar",
        tags={"calendar", "event", "create", "google"},
        annotations={
            "title": "Create Calendar Event",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_event(
        user_google_email: str,
        summary: str,
        start_time: str,
        end_time: str,
        calendar_id: str = "primary",
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        timezone: Optional[str] = None,
        attachments: Optional[List[str]] = None,
    ) -> str:
        """
        Creates a new event.

        Args:
            user_google_email (str): The user's Google email address. Required.
            summary (str): Event title.
            start_time (str): Start time (RFC3339, e.g., "2023-10-27T10:00:00-07:00" or "2023-10-27" for all-day).
            end_time (str): End time (RFC3339, e.g., "2023-10-27T11:00:00-07:00" or "2023-10-28" for all-day).
            calendar_id (str): Calendar ID (default: 'primary').
            description (Optional[str]): Event description.
            location (Optional[str]): Event location.
            attendees (Optional[List[str]]): Attendee email addresses.
            timezone (Optional[str]): Timezone (e.g., "America/New_York").
            attachments (Optional[List[str]]): List of Google Drive file URLs or IDs to attach to the event.

        Returns:
            str: Confirmation message of the successful event creation with event link.
        """
        logger.info(
            f"[create_event] Invoked. Email: '{user_google_email}', Summary: {summary}"
        )
        logger.info(f"[create_event] Incoming attachments param: {attachments}")
        
        try:
            calendar_service = await _get_calendar_service_with_fallback(user_google_email)
            
            # If attachments value is a string, split by comma and strip whitespace
            if attachments and isinstance(attachments, str):
                attachments = [a.strip() for a in attachments.split(',') if a.strip()]
                logger.info(f"[create_event] Parsed attachments list from string: {attachments}")
                
            event_body: Dict[str, Any] = {
                "summary": summary,
                "start": (
                    {"date": start_time}
                    if "T" not in start_time
                    else {"dateTime": start_time}
                ),
                "end": (
                    {"date": end_time} if "T" not in end_time else {"dateTime": end_time}
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
                    drive_service = await _get_drive_service_with_fallback(user_google_email)
                except Exception as e:
                    logger.warning(f"Could not get Drive service for MIME type lookup: {e}")
                    
                for att in attachments:
                    file_id = None
                    if att.startswith("https://"):
                        # Match /d/<id>, /file/d/<id>, ?id=<id>
                        match = re.search(r"(?:/d/|/file/d/|id=)([\w-]+)", att)
                        file_id = match.group(1) if match else None
                        logger.info(f"[create_event] Extracted file_id '{file_id}' from attachment URL '{att}'")
                    else:
                        file_id = att
                        logger.info(f"[create_event] Using direct file_id '{file_id}' for attachment")
                    if file_id:
                        file_url = f"https://drive.google.com/open?id={file_id}"
                        mime_type = "application/vnd.google-apps.drive-sdk"
                        title = "Drive Attachment"
                        # Try to get the actual MIME type and filename from Drive
                        if drive_service:
                            try:
                                file_metadata = await asyncio.to_thread(
                                    lambda: drive_service.files().get(fileId=file_id, fields="mimeType,name").execute()
                                )
                                mime_type = file_metadata.get("mimeType", mime_type)
                                filename = file_metadata.get("name")
                                if filename:
                                    title = filename
                                    logger.info(f"[create_event] Using filename '{filename}' as attachment title")
                                else:
                                    logger.info(f"[create_event] No filename found, using generic title")
                            except Exception as e:
                                logger.warning(f"Could not fetch metadata for file {file_id}: {e}")
                        event_body["attachments"].append({
                            "fileUrl": file_url,
                            "title": title,
                            "mimeType": mime_type,
                        })
                created_event = await asyncio.to_thread(
                    lambda: calendar_service.events().insert(
                        calendarId=calendar_id, body=event_body, supportsAttachments=True
                    ).execute()
                )
            else:
                created_event = await asyncio.to_thread(
                    lambda: calendar_service.events().insert(calendarId=calendar_id, body=event_body).execute()
                )
            link = created_event.get("htmlLink", "No link available")
            confirmation_message = f"Successfully created event '{created_event.get('summary', summary)}' for {user_google_email}. Link: {link}"
            logger.info(
                    f"Event created successfully for {user_google_email}. ID: {created_event.get('id')}, Link: {link}"
                )
            return confirmation_message
            
        except HttpError as e:
            error_msg = f"❌ Failed to create event: {e}"
            logger.error(f"[create_event] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[create_event] {error_msg}")
            return error_msg

    @mcp.tool(
        name="modify_event",
        description="Modifies an existing event in Google Calendar",
        tags={"calendar", "event", "modify", "update", "google"},
        annotations={
            "title": "Modify Calendar Event",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def modify_event(
        user_google_email: str,
        event_id: str,
        calendar_id: str = "primary",
        summary: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        timezone: Optional[str] = None,
    ) -> str:
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
            str: Confirmation message of the successful event modification with event link.
        """
        logger.info(
            f"[modify_event] Invoked. Email: '{user_google_email}', Event ID: {event_id}"
        )

        try:
            calendar_service = await _get_calendar_service_with_fallback(user_google_email)
            
            # Build the event body with only the fields that are provided
            event_body: Dict[str, Any] = {}
            if summary is not None:
                event_body["summary"] = summary
            if start_time is not None:
                event_body["start"] = (
                    {"date": start_time}
                    if "T" not in start_time
                    else {"dateTime": start_time}
                )
                if timezone is not None and "dateTime" in event_body["start"]:
                    event_body["start"]["timeZone"] = timezone
            if end_time is not None:
                event_body["end"] = (
                    {"date": end_time} if "T" not in end_time else {"dateTime": end_time}
                )
                if timezone is not None and "dateTime" in event_body["end"]:
                    event_body["end"]["timeZone"] = timezone
            if description is not None:
                event_body["description"] = description
            if location is not None:
                event_body["location"] = location
            if attendees is not None:
                event_body["attendees"] = [{"email": email} for email in attendees]
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
                    f"[modify_event] Timezone provided but start_time and end_time are missing. Timezone will not be applied unless start/end times are also provided."
                )

            if not event_body:
                message = "No fields provided to modify the event."
                logger.warning(f"[modify_event] {message}")
                return f"❌ {message}"

            # Log the event ID for debugging
            logger.info(
                f"[modify_event] Attempting to update event with ID: '{event_id}' in calendar '{calendar_id}'"
            )

            # Try to get the event first to verify it exists
            try:
                await asyncio.to_thread(
                    lambda: calendar_service.events().get(calendarId=calendar_id, eventId=event_id).execute()
                )
                logger.info(
                    f"[modify_event] Successfully verified event exists before update"
                )
            except HttpError as get_error:
                if get_error.resp.status == 404:
                    logger.error(
                        f"[modify_event] Event not found during pre-update verification: {get_error}"
                    )
                    message = f"Event not found during verification. The event with ID '{event_id}' could not be found in calendar '{calendar_id}'. This may be due to incorrect ID format or the event no longer exists."
                    return f"❌ {message}"
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
            return confirmation_message
            
        except HttpError as e:
            error_msg = f"❌ Failed to modify event: {e}"
            logger.error(f"[modify_event] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[modify_event] {error_msg}")
            return error_msg

    @mcp.tool(
        name="delete_event",
        description="Deletes an existing event from Google Calendar",
        tags={"calendar", "event", "delete", "google"},
        annotations={
            "title": "Delete Calendar Event",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def delete_event(
        user_google_email: str, 
        event_id: str, 
        calendar_id: str = "primary"
    ) -> str:
        """
        Deletes an existing event.

        Args:
            user_google_email (str): The user's Google email address. Required.
            event_id (str): The ID of the event to delete.
            calendar_id (str): Calendar ID (default: 'primary').

        Returns:
            str: Confirmation message of the successful event deletion.
        """
        logger.info(
            f"[delete_event] Invoked. Email: '{user_google_email}', Event ID: {event_id}"
        )

        try:
            calendar_service = await _get_calendar_service_with_fallback(user_google_email)
            
            # Log the event ID for debugging
            logger.info(
                f"[delete_event] Attempting to delete event with ID: '{event_id}' in calendar '{calendar_id}'"
            )

            # Try to get the event first to verify it exists
            try:
                await asyncio.to_thread(
                    lambda: calendar_service.events().get(calendarId=calendar_id, eventId=event_id).execute()
                )
                logger.info(
                    f"[delete_event] Successfully verified event exists before deletion"
                )
            except HttpError as get_error:
                if get_error.resp.status == 404:
                    logger.error(
                        f"[delete_event] Event not found during pre-delete verification: {get_error}"
                    )
                    message = f"Event not found during verification. The event with ID '{event_id}' could not be found in calendar '{calendar_id}'. This may be due to incorrect ID format or the event no longer exists."
                    return f"❌ {message}"
                else:
                    logger.warning(
                        f"[delete_event] Error during pre-delete verification, but proceeding with deletion: {get_error}"
                    )

            # Proceed with the deletion
            await asyncio.to_thread(
                lambda: calendar_service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            )

            confirmation_message = f"Successfully deleted event (ID: {event_id}) from calendar '{calendar_id}' for {user_google_email}."
            logger.info(f"Event deleted successfully for {user_google_email}. ID: {event_id}")
            return confirmation_message
            
        except HttpError as e:
            error_msg = f"❌ Failed to delete event: {e}"
            logger.error(f"[delete_event] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[delete_event] {error_msg}")
            return error_msg

    @mcp.tool(
        name="get_event",
        description="Retrieves the details of a single event by its ID from a specified Google Calendar",
        tags={"calendar", "event", "get", "google"},
        annotations={
            "title": "Get Calendar Event Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_event(
        user_google_email: str,
        event_id: str,
        calendar_id: str = "primary"
    ) -> str:
        """
        Retrieves the details of a single event by its ID from a specified Google Calendar.

        Args:
            user_google_email (str): The user's Google email address. Required.
            event_id (str): The ID of the event to retrieve. Required.
            calendar_id (str): The ID of the calendar to query. Defaults to 'primary'.

        Returns:
            str: A formatted string with the event's details.
        """
        logger.info(f"[get_event] Invoked. Email: '{user_google_email}', Event ID: {event_id}")
        
        try:
            calendar_service = await _get_calendar_service_with_fallback(user_google_email)
            
            event = await asyncio.to_thread(
                lambda: calendar_service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            )
            summary = event.get("summary", "No Title")
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            link = event.get("htmlLink", "No Link")
            description = event.get("description", "No Description")
            location = event.get("location", "No Location")
            attendees = event.get("attendees", [])
            attendee_emails = ", ".join([a.get("email", "") for a in attendees]) if attendees else "None"
            event_details = (
                f'Event Details:\n'
                f'- Title: {summary}\n'
                f'- Starts: {start}\n'
                f'- Ends: {end}\n'
                f'- Description: {description}\n'
                f'- Location: {location}\n'
                f'- Attendees: {attendee_emails}\n'
                f'- Event ID: {event_id}\n'
                f'- Link: {link}'
            )
            logger.info(f"[get_event] Successfully retrieved event {event_id} for {user_google_email}.")
            return event_details
            
        except HttpError as e:
            error_msg = f"❌ Failed to get event: {e}"
            logger.error(f"[get_event] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[get_event] {error_msg}")
            return error_msg
    
    # Log successful setup
    tool_count = 6  # Total number of Calendar tools
    logger.info(f"Successfully registered {tool_count} Google Calendar tools")