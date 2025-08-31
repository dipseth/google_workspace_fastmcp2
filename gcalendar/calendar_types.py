"""
Type definitions for Google Calendar tool responses.

These TypedDict classes define the structure of data returned by Calendar tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional


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
    error: Optional[str]  # Optional error message for error responses


class EventListResponse(TypedDict):
    """Response structure for list_events tool."""
    events: List[EventInfo]
    count: int
    calendarId: str
    timeMin: Optional[str]
    timeMax: Optional[str]
    userEmail: str
    error: Optional[str]  # Optional error message for error responses