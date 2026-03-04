"""
Type definitions for Google Calendar tool responses.

These TypedDict classes define the structure of data returned by Calendar tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

import datetime as _dt
import re
from datetime import timedelta

from pydantic import BaseModel, BeforeValidator, Field, model_validator
from typing_extensions import Annotated, List, NotRequired, Optional, TypedDict

# ---------------------------------------------------------------------------
# Duration parsing  (accepts str, int/float seconds, or existing timedelta)
# ---------------------------------------------------------------------------
_DURATION_UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "w": "weeks",
}


def parse_duration(v: object) -> timedelta:
    """Convert a human-friendly value into a :class:`~datetime.timedelta`.

    Accepted inputs:
        * ``timedelta`` — returned as-is
        * ``int | float`` — treated as **seconds**
        * ``str`` — a number followed by a unit letter:
          ``s`` (seconds), ``m`` (minutes), ``h`` (hours),
          ``d`` (days), ``w`` (weeks).  Floats are supported
          (e.g. ``'1.5h'``).

    Examples::

        parse_duration('30m')    # timedelta(minutes=30)
        parse_duration('1.5h')   # timedelta(hours=1.5)
        parse_duration('2d')     # timedelta(days=2)
        parse_duration(3600)     # timedelta(seconds=3600)

    Raises :class:`ValueError` on unrecognised input.
    """
    if isinstance(v, timedelta):
        return v
    if isinstance(v, (int, float)):
        return timedelta(seconds=v)
    if isinstance(v, str):
        if m := re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smhdw])", v.strip()):
            return timedelta(**{_DURATION_UNITS[m[2]]: float(m[1])})
    raise ValueError(
        f"Invalid duration: {v!r}  (expected e.g. '30s', '5m', '2h', '1.5d', '1w')"
    )


#: Pydantic-aware Duration type.  Use as a field type in BaseModel classes
#: when you need a ``timedelta`` that also accepts human strings / raw seconds.
Duration = Annotated[timedelta, BeforeValidator(parse_duration)]


def resolve_end_time(start_time: str, dur: timedelta) -> str:
    """Compute *end_time* from *start_time* + *dur*.

    Preserves the same format as *start_time*:
    * date-only (``YYYY-MM-DD``) → date-only (rounds up to whole days, minimum 1)
    * datetime with offset/Z → datetime with same suffix
    * naive datetime → naive datetime
    """
    # Date-only → date-only
    if len(start_time) == 10 and start_time.count("-") == 2:
        start_date = _dt.datetime.strptime(start_time, "%Y-%m-%d").date()
        total_days = max(int(-(-dur.total_seconds() // 86400)), 1)  # ceiling, min 1
        return (start_date + _dt.timedelta(days=total_days)).strftime("%Y-%m-%d")

    # Split datetime from offset suffix
    base, suffix = start_time, ""
    if base.endswith("Z"):
        base, suffix = base[:-1], "Z"
    elif re.search(r"[+-]\d{2}:\d{2}$", base):
        suffix = base[-6:]
        base = base[:-6]

    start_dt = _dt.datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    end_dt = start_dt + dur
    return end_dt.strftime("%Y-%m-%dT%H:%M:%S") + suffix


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
    end: str  # ISO format datetime or date
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
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class EventListResponse(TypedDict):
    """Response structure for list_events tool."""

    events: List[EventInfo]
    count: int
    calendarId: str
    timeMin: Optional[str]
    timeMax: Optional[str]
    userEmail: str
    error: NotRequired[Optional[str]]  # Optional error message for error responses


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
    start_time: Annotated[
        str,
        Field(
            description="Event start time. IMPORTANT: Always specify timezone to avoid time offset issues. Preferred formats: (1) datetime with offset: '2025-01-01T10:00:00-05:00', (2) datetime with Z for UTC: '2025-01-01T10:00:00Z', (3) date only for all-day events: '2025-01-01'. Naive datetimes (e.g., '2025-01-01T10:00:00') will be localized using the timezone field or the server's default timezone."
        ),
    ]
    end_time: Annotated[
        Optional[str],
        Field(
            None,
            description="Event end time. Required unless 'duration' is provided. IMPORTANT: Always specify timezone to avoid time offset issues. Preferred formats: (1) datetime with offset: '2025-01-01T11:00:00-05:00', (2) datetime with Z for UTC: '2025-01-01T11:00:00Z', (3) date only for all-day events: '2025-01-02'. Naive datetimes (e.g., '2025-01-01T11:00:00') will be localized using the timezone field or the server's default timezone.",
        ),
    ] = None
    duration: Annotated[
        Optional[str],
        Field(
            None,
            description="Event duration as alternative to end_time. Format: a number + unit — '30s', '5m', '2h', '1.5d', '1w'. Ignored if end_time is also provided.",
        ),
    ] = None
    description: Annotated[
        Optional[str], Field(None, description="Event description/details")
    ] = None
    location: Annotated[Optional[str], Field(None, description="Event location")] = None
    attendees: Annotated[
        Optional[List[str]], Field(None, description="List of attendee email addresses")
    ] = None
    timezone: Annotated[
        Optional[str],
        Field(
            None,
            description="STRONGLY RECOMMENDED when using naive datetimes. IANA timezone name (e.g., 'America/New_York', 'America/Chicago', 'UTC'). Naive datetimes in start_time/end_time will be interpreted in this timezone. Without this, the server's DEFAULT_TIMEZONE setting is used. Has no effect when start_time/end_time already contain an offset (Z or ±HH:MM).",
        ),
    ] = None
    recurrence: Annotated[
        Optional[List[str]],
        Field(
            None,
            description="List of RRULE, EXRULE, RDATE, or EXDATE strings for recurring events (e.g., ['RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR']). See RFC 5545 for format details.",
        ),
    ] = None
    attachments: Annotated[
        Optional[List[str]],
        Field(
            None,
            description="List of Google Drive file URLs or file IDs to attach to the event",
        ),
    ] = None

    @model_validator(mode="after")
    def _resolve_end_time(self) -> "EventData":
        """Compute end_time from start_time + duration when end_time is absent."""
        if self.end_time:
            return self  # explicit end_time takes precedence

        if not self.duration:
            raise ValueError("Either 'end_time' or 'duration' must be provided.")

        dur = parse_duration(self.duration)
        self.end_time = resolve_end_time(self.start_time, dur)
        return self


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
