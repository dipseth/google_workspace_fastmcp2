"""
Type definitions for Google Calendar tool responses.

These TypedDict classes define the structure of data returned by Calendar tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional, NotRequired, Annotated
from pydantic import BaseModel, Field


class CalendarInfo(TypedDict):
    """Structure for a single calendar entry."""
    id: str
    summary: str
    description: Optional[str]
    primary: bool
    timeZone: Optional[str]
    backgroundColor: Optional[str]
    foregroundColor: Optional[str]


class EventInfo(TypedDict):
    """Structure for a single calendar event."""
    id: str
    summary: str
    description: Optional[str]
    start: str  # ISO format datetime or date
    end: str    # ISO format datetime or date
    startTimeZone: Optional[str]
    endTimeZone: Optional[str]
    location: Optional[str]
    htmlLink: str
    status: Optional[str]
    creator: Optional[str]
    organizer: Optional[str]
    attendees: Optional[List[str]]  # List of email addresses
    attachments: Optional[List[dict]]


class CalendarListResponse(TypedDict):
    """Response structure for list_calendars tool."""
    calendars: List[CalendarInfo]
    count: int
    userEmail: str
    error: NotRequired[Optional[str]]   # Optional error message for error responses


class EventListResponse(TypedDict):
    """Response structure for list_events tool."""
    events: List[EventInfo]
    count: int
    calendarId: str
    timeMin: Optional[str]
    timeMax: Optional[str]
    userEmail: str
    error: NotRequired[Optional[str]]   # Optional error message for error responses


class CreateEventResponse(TypedDict):
    """Response structure for create_event tool."""
    success: bool
    eventId: Optional[str]
    summary: Optional[str]
    htmlLink: Optional[str]
    start: Optional[str]
    end: Optional[str]
    calendarId: str
    userEmail: str
    message: str
    error: NotRequired[Optional[str]] 


class ModifyEventResponse(TypedDict):
    """Response structure for modify_event tool."""
    success: bool
    eventId: str
    summary: Optional[str]
    htmlLink: Optional[str]
    calendarId: str
    userEmail: str
    fieldsModified: List[str]
    message: str
    error: NotRequired[Optional[str]] 


class DeleteEventResponse(TypedDict):
    """Response structure for delete_event tool."""
    success: bool
    eventsDeleted: List[str]
    eventsFailed: List[dict]  # List of {event_id, error} dicts
    totalProcessed: int
    calendarId: str
    userEmail: str
    message: str
    error: NotRequired[Optional[str]] 


class BulkOperationResult(TypedDict):
    """Structure for individual bulk operation results."""
    eventId: str
    summary: str
    status: str  # 'success', 'failed', 'skipped'
    error: NotRequired[Optional[str]] 


class BulkOperationsResponse(TypedDict):
    """Response structure for bulk_calendar_operations tool."""
    success: bool
    operation: str
    calendarId: str
    userEmail: str
    totalFound: int
    totalMatched: int
    totalProcessed: int
    results: List[BulkOperationResult]
    filters: dict  # Applied filters
    dryRun: bool
    message: str
    error: NotRequired[Optional[str]] 


class MoveEventResult(TypedDict):
    """Structure for individual move operation results."""
    originalId: str
    newId: Optional[str]
    summary: str
    status: str  # 'copied', 'deleted', 'failed'
    error: NotRequired[Optional[str]] 


class MoveEventsResponse(TypedDict):
    """Response structure for move_events_between_calendars tool."""
    success: bool
    sourceCalendarId: str
    targetCalendarId: str
    userEmail: str
    totalFound: int
    totalCopied: int
    totalDeleted: int
    results: List[MoveEventResult]
    message: str
    error: NotRequired[Optional[str]] 


class GetEventResponse(TypedDict):
    """Response structure for get_event tool."""
    success: bool
    eventId: str
    summary: Optional[str]
    description: Optional[str]
    start: Optional[str]
    end: Optional[str]
    startTimeZone: Optional[str]
    endTimeZone: Optional[str]
    location: Optional[str]
    htmlLink: Optional[str]
    status: Optional[str]
    creator: Optional[str]
    organizer: Optional[str]
    attendees: Optional[List[str]]
    attachments: Optional[List[dict]]
    calendarId: str
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class EventData(BaseModel):
    """Structure for individual event data in bulk creation."""
    summary: Annotated[str, Field(description="Event title/summary")]
    start_time: Annotated[str, Field(description="Event start time. Accepts: RFC3339 with timezone (e.g., '2025-01-01T10:00:00Z', '2025-01-01T10:00:00-05:00'), datetime without timezone (e.g., '2025-01-01T10:00:00' - will be automatically corrected to UTC by appending 'Z'), or date only for all-day events (e.g., '2025-01-01')")]
    end_time: Annotated[str, Field(description="Event end time. Accepts: RFC3339 with timezone (e.g., '2025-01-01T11:00:00Z', '2025-01-01T11:00:00-05:00'), datetime without timezone (e.g., '2025-01-01T11:00:00' - will be automatically corrected to UTC by appending 'Z'), or date only for all-day events (e.g., '2025-01-02')")]
    description: Annotated[Optional[str], Field(None, description="Event description/details")] = None
    location: Annotated[Optional[str], Field(None, description="Event location")] = None
    attendees: Annotated[Optional[List[str]], Field(None, description="List of attendee email addresses")] = None
    timezone: Annotated[Optional[str], Field(None, description="Timezone for the event (e.g., 'America/New_York', 'UTC'). Applied to both start and end times if they include time components. Note: If start_time/end_time don't include timezone info, they will be treated as UTC automatically")] = None
    attachments: Annotated[Optional[List[str]], Field(None, description="List of Google Drive file URLs or file IDs to attach to the event")] = None


class BulkEventResult(TypedDict):
    """Structure for individual bulk event creation results."""
    eventId: Optional[str]
    summary: str
    start_time: str
    htmlLink: Optional[str]
    status: str  # 'success', 'failed'
    error: NotRequired[Optional[str]]
    input_data: NotRequired[dict]  # Original input data for failed events


class BulkCreateEventResponse(TypedDict):
    """Response structure for bulk create_event operations."""
    success: bool
    totalProcessed: int
    eventsCreated: List[BulkEventResult]
    eventsFailed: List[BulkEventResult]
    calendarId: str
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class CreateCalendarResponse(TypedDict):
    """Response structure for create_calendar tool."""
    success: bool
    calendarId: Optional[str]
    summary: Optional[str]
    description: Optional[str]
    timeZone: Optional[str]
    location: Optional[str]
    htmlLink: Optional[str]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]