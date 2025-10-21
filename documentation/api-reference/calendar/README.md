# Calendar API Reference

Complete API documentation for all Google Calendar tools in the FastMCP Google MCP Server.

## 🎉 Recent Updates & Improvements

### ✅ Move Events Between Calendars - Fixed & Production Ready
- **Fixed Type Validation**: Resolved "originalId is a required property" error by correcting field names in response structure
- **Bulk Event Operations**: Support for moving multiple events with filters and batch processing
- **Enhanced Error Handling**: Better validation and structured responses for all calendar operations

### 🔧 Recent Fixes
- **Fixed `move_events_between_calendars`**: Corrected field names (`originalEventId` → `originalId`, `newEventId` → `newId`) to match type definitions
- **HTML Description Support**: Calendar event descriptions support basic HTML formatting for rich content
- **Time Format Auto-correction**: Automatic timezone handling and RFC3339 format correction for date/time parameters
- **Improved Batch Operations**: Enhanced bulk operations with detailed success/failure reporting

## Available Tools

| Tool Name | Description |
|-----------|-------------|
| [`list_calendars`](#list_calendars) | List all accessible calendars |
| [`create_calendar`](#create_calendar) | Create new Google Calendar |
| [`list_events`](#list_events) | Get events from calendar with time range |
| [`create_event`](#create_event) | Create single or multiple events (bulk support) |
| [`modify_event`](#modify_event) | Update existing event properties |
| [`delete_event`](#delete_event) | Delete single or multiple events (batch support) |
| [`get_event`](#get_event) | Get detailed information about specific event |
| [`bulk_calendar_operations`](#bulk_calendar_operations) | Bulk operations with advanced filtering |
| [`move_events_between_calendars`](#move_events_between_calendars) | Move/copy events between calendars |

---

## list_calendars

Retrieves a list of calendars accessible to the authenticated user.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |

### Returns

```json
{
  "calendars": [
    {
      "id": "primary",
      "summary": "John Doe",
      "description": "Personal calendar",
      "primary": true,
      "timeZone": "America/New_York",
      "backgroundColor": "#9fe1e7",
      "foregroundColor": "#000000"
    },
    {
      "id": "calendar@group.calendar.google.com",
      "summary": "Work Calendar",
      "description": "Team meetings and deadlines",
      "primary": false,
      "timeZone": "America/New_York",
      "backgroundColor": "#7986cb",
      "foregroundColor": "#ffffff"
    }
  ],
  "count": 2,
  "userEmail": "user@gmail.com",
  "error": null
}
```

### Example Usage

```python
# List all calendars
calendars = await list_calendars(
    user_google_email="user@gmail.com"
)

# Find work calendar
work_calendar = next(
    (cal for cal in calendars["calendars"] if "Work" in cal["summary"]), 
    None
)
```

---

## create_calendar

Creates a new Google Calendar with specified properties.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `summary` | string | Yes | Calendar name/title (1-255 chars) | - |
| `description` | string | No | Calendar description (max 1000 chars) | - |
| `time_zone` | string | No | Timezone (e.g., 'America/New_York', 'UTC') | User default |
| `location` | string | No | Geographic location (max 255 chars) | - |

### Returns

```json
{
  "success": true,
  "calendarId": "abc123@group.calendar.google.com",
  "summary": "Project Alpha Calendar",
  "description": "Calendar for Project Alpha milestones",
  "timeZone": "America/New_York",
  "location": "New York Office",
  "htmlLink": "https://calendar.google.com/calendar/u/0?cid=abc123",
  "userEmail": "user@gmail.com",
  "message": "✅ Successfully created calendar 'Project Alpha Calendar'",
  "error": null
}
```

### Example Usage

```python
# Create project calendar
calendar = await create_calendar(
    user_google_email="user@gmail.com",
    summary="Q4 Marketing Campaign",
    description="Calendar for tracking Q4 marketing activities and deadlines",
    time_zone="America/New_York",
    location="Marketing Department"
)

# Create simple personal calendar
personal = await create_calendar(
    user_google_email="user@gmail.com",
    summary="Personal Goals 2025"
)
```

---

## list_events

Retrieves events from a specified Google Calendar within a time range.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `calendar_id` | string | No | Calendar ID ('primary' for main calendar) | `"primary"` |
| `time_min` | string | No | Start time (RFC3339 format) | Current time |
| `time_max` | string | No | End time (RFC3339 format) | - |
| `max_results` | integer | No | Max events to return (1-2500) | 25 |

### Time Format Support

```
# RFC3339 with timezone
2025-09-01T14:00:00-05:00    # Sep 1, 2025 2:00 PM EST
2025-09-01T19:00:00Z         # Same time in UTC

# Date only (all-day events)
2025-09-01                   # All day Sep 1, 2025

# Auto-corrected formats
2025-09-01T14:00:00         # Automatically becomes UTC (Z appended)
```

### Returns

```json
{
  "events": [
    {
      "id": "event123",
      "summary": "Team Standup",
      "description": "Daily standup meeting",
      "start": "2025-09-01T09:00:00-05:00",
      "end": "2025-09-01T09:30:00-05:00",
      "startTimeZone": "America/Chicago",
      "endTimeZone": "America/Chicago",
      "location": "Conference Room A",
      "htmlLink": "https://calendar.google.com/event?eid=...",
      "status": "confirmed",
      "creator": "user@gmail.com",
      "organizer": "user@gmail.com",
      "attendees": ["team@company.com"],
      "attachments": []
    }
  ],
  "count": 1,
  "calendarId": "primary",
  "timeMin": "2025-09-01T00:00:00Z",
  "timeMax": "2025-09-02T00:00:00Z",
  "userEmail": "user@gmail.com",
  "error": null
}
```

### Example Usage

```python
# Get today's events
events = await list_events(
    user_google_email="user@gmail.com",
    time_min="2025-09-01T00:00:00Z",
    time_max="2025-09-01T23:59:59Z"
)

# Get this week's work calendar events
work_events = await list_events(
    user_google_email="user@gmail.com",
    calendar_id="work@company.com",
    time_min="2025-09-01T00:00:00Z",
    time_max="2025-09-07T23:59:59Z",
    max_results=100
)
```

---

## create_event

Create single or multiple events with support for bulk operations and rich HTML descriptions.

### Parameters (Legacy Single Event Mode)

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `calendar_id` | string | No | Target calendar ID | `"primary"` |
| `summary` | string | Yes* | Event title (*required in legacy mode) | - |
| `start_time` | string | Yes* | Start time (RFC3339) | - |
| `end_time` | string | Yes* | End time (RFC3339) | - |
| `description` | string | No | Event description (supports HTML!) | - |
| `location` | string | No | Event location or meeting link | - |
| `attendees` | array[string] | No | Attendee email addresses (max 100) | - |
| `timezone` | string | No | Event timezone | UTC |
| `attachments` | array[string] | No | Drive file URLs/IDs (max 25) | - |

### Parameters (Bulk Mode)

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `events` | array/string | Yes* | Array of EventData objects (*for bulk mode) | - |

### HTML Description Support 🎨

Google Calendar supports basic HTML formatting in event descriptions:

**Supported HTML Tags:**
- `<h1>`, `<h2>`, `<h3>` - Headers
- `<b>bold</b>` - Bold text
- `<i>italic</i>` - Italic text
- `<u>underline</u>` - Underlined text
- `<font color="#FF0000">colored text</font>` - Colored text
- `<br/>` - Line breaks
- `<ul><li>item</li></ul>` - Lists
- `<a href="...">links</a>` - Hyperlinks
- `<blockquote>quotes</blockquote>` - Block quotes
- `<hr>` - Horizontal rules

### Returns

```json
{
  "success": true,
  "eventId": "abc123",
  "summary": "Team Meeting",
  "htmlLink": "https://calendar.google.com/event?eid=...",
  "start": "2025-09-02T14:00:00-05:00",
  "end": "2025-09-02T15:00:00-05:00",
  "calendarId": "primary",
  "userEmail": "user@gmail.com",
  "message": "✅ Successfully created event 'Team Meeting'",
  "error": null
}
```

### Example Usage

```python
# Simple event
event = await create_event(
    user_google_email="user@gmail.com",
    summary="Doctor Appointment",
    start_time="2025-09-15T10:00:00-05:00",
    end_time="2025-09-15T11:00:00-05:00",
    location="123 Medical Plaza"
)

# Rich HTML event with formatting
formatted_event = await create_event(
    user_google_email="user@gmail.com",
    summary="🎨 Project Kickoff Meeting",
    start_time="2025-09-20T14:00:00Z",
    end_time="2025-09-20T16:00:00Z",
    description="""
    <h2>📋 Meeting Agenda</h2>
    <ul>
        <li><b>Project Overview</b> - Goals and timeline</li>
        <li><i>Team Introductions</i> - Roles and responsibilities</li>
        <li><u>Next Steps</u> - Action items</li>
    </ul>
    
    <p><font color="#FF0000">Important:</font> Please review the project brief before attending.</p>
    
    <blockquote>
    "Success is not final, failure is not fatal: it is the courage to continue that counts."
    </blockquote>
    
    <p>📄 <a href="https://drive.google.com/file/d/123">Project Brief Document</a></p>
    """,
    attendees=["team@company.com", "manager@company.com"],
    location="Conference Room A"
)

# Bulk event creation
bulk_events = await create_event(
    user_google_email="user@gmail.com",
    calendar_id="work@company.com",
    events=[
        {
            "summary": "Sprint Planning",
            "start_time": "2025-09-02T09:00:00Z",
            "end_time": "2025-09-02T11:00:00Z",
            "description": "Plan upcoming 2-week sprint",
            "attendees": ["dev-team@company.com"]
        },
        {
            "summary": "Code Review",
            "start_time": "2025-09-03T14:00:00Z",
            "end_time": "2025-09-03T15:00:00Z",
            "location": "Virtual - Google Meet"
        }
    ]
)
```

---

## modify_event

Modifies an existing event in Google Calendar.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `event_id` | string | Yes | ID of event to modify | - |
| `calendar_id` | string | No | Calendar containing the event | `"primary"` |
| `summary` | string | No | New event title | - |
| `start_time` | string | No | New start time (RFC3339) | - |
| `end_time` | string | No | New end time (RFC3339) | - |
| `description` | string | No | New description (HTML supported) | - |
| `location` | string | No | New location | - |
| `attendees` | array[string] | No | New attendee list | - |
| `timezone` | string | No | New timezone | - |

### Returns

```json
{
  "success": true,
  "eventId": "abc123",
  "summary": "Updated Meeting Title",
  "htmlLink": "https://calendar.google.com/event?eid=...",
  "calendarId": "primary",
  "userEmail": "user@gmail.com",
  "fieldsModified": ["summary", "start_time", "location"],
  "message": "✅ Successfully modified event 'Updated Meeting Title'",
  "error": null
}
```

### Example Usage

```python
# Update meeting time and location
result = await modify_event(
    user_google_email="user@gmail.com",
    event_id="abc123",
    start_time="2025-09-15T15:00:00-05:00",
    end_time="2025-09-15T16:00:00-05:00",
    location="New Conference Room B"
)

# Add attendees and update description
result = await modify_event(
    user_google_email="user@gmail.com",
    event_id="abc123",
    description="<h3>Updated Agenda</h3><p>Added new discussion items.</p>",
    attendees=["john@company.com", "jane@company.com", "mike@company.com"]
)
```

---

## delete_event

Deletes one or more events from Google Calendar with support for batch operations.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `event_id` | string/array | Yes | Event ID(s) to delete | - |
| `calendar_id` | string | No | Calendar containing events | `"primary"` |

### Event ID Formats

```python
# Single event
"abc123"

# Comma-separated string
"abc123,def456,ghi789"

# JSON array string
'["abc123", "def456", "ghi789"]'

# Native array
["abc123", "def456", "ghi789"]
```

### Returns

```json
{
  "success": true,
  "eventsDeleted": ["abc123", "def456"],
  "eventsFailed": [
    {
      "event_id": "ghi789",
      "error": "Event not found"
    }
  ],
  "totalProcessed": 3,
  "calendarId": "primary",
  "userEmail": "user@gmail.com",
  "message": "📊 Batch Delete Results: 2 succeeded, 1 failed",
  "error": null
}
```

### Example Usage

```python
# Delete single event
result = await delete_event(
    user_google_email="user@gmail.com",
    event_id="abc123"
)

# Delete multiple events
result = await delete_event(
    user_google_email="user@gmail.com",
    event_id=["event1", "event2", "event3"]
)

# Delete with comma-separated string
result = await delete_event(
    user_google_email="user@gmail.com",
    event_id="old_event1,old_event2,cancelled_meeting"
)
```

---

## get_event

Retrieves detailed information about a specific event.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `event_id` | string | Yes | ID of event to retrieve | - |
| `calendar_id` | string | No | Calendar containing the event | `"primary"` |

### Returns

```json
{
  "success": true,
  "eventId": "abc123",
  "summary": "Team Meeting",
  "description": "Weekly team sync meeting",
  "start": "2025-09-02T14:00:00-05:00",
  "end": "2025-09-02T15:00:00-05:00",
  "startTimeZone": "America/Chicago",
  "endTimeZone": "America/Chicago",
  "location": "Conference Room A",
  "htmlLink": "https://calendar.google.com/event?eid=...",
  "status": "confirmed",
  "creator": "user@gmail.com",
  "organizer": "user@gmail.com",
  "attendees": ["team@company.com"],
  "attachments": [
    {
      "filename": "agenda.pdf",
      "mimeType": "application/pdf",
      "fileId": "drive_file_123"
    }
  ],
  "calendarId": "primary",
  "userEmail": "user@gmail.com",
  "message": "✅ Successfully retrieved event 'Team Meeting'",
  "error": null
}
```

### Example Usage

```python
# Get event details
event_details = await get_event(
    user_google_email="user@gmail.com",
    event_id="abc123"
)

# Access specific properties
title = event_details["summary"]
location = event_details["location"]
attendees = event_details["attendees"]
```

---

## bulk_calendar_operations

Perform bulk operations on calendar events with advanced filtering.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `operation` | string | Yes | Operation: `delete`, `list`, or `export` | - |
| `calendar_id` | string | No | Calendar to operate on | `"primary"` |
| `time_min` | string | No | Start of time range (RFC3339) | 30 days ago |
| `time_max` | string | No | End of time range (RFC3339) | - |
| `title_pattern` | string | No | Regex pattern for event titles | - |
| `location_pattern` | string | No | Regex pattern for locations | - |
| `attendee_email` | string | No | Filter by attendee email | - |
| `max_results` | integer | No | Max events to process (1-2500) | 100 |
| `dry_run` | boolean | No | Preview only (no changes) | `true` |

### Filter Examples

```python
# Find all "test" events (case-insensitive)
title_pattern = "(?i)test"

# Find events in conference rooms
location_pattern = "(?i)conference room"

# Find events with specific attendee
attendee_email = "manager@company.com"

# Combine multiple filters
title_pattern = "(?i)(meeting|standup|review)"
location_pattern = "(?i)(room|virtual|zoom)"
```

### Returns

```json
{
  "success": true,
  "operation": "delete",
  "calendarId": "primary",
  "userEmail": "user@gmail.com",
  "totalFound": 50,
  "totalMatched": 15,
  "totalProcessed": 15,
  "results": [
    {
      "eventId": "abc123",
      "summary": "Test Event",
      "status": "deleted"
    }
  ],
  "filters": {
    "timeMin": "2025-08-01T00:00:00Z",
    "timeMax": "2025-08-31T23:59:59Z",
    "titlePattern": "(?i)test"
  },
  "dryRun": false,
  "message": "📊 Bulk Operation Results: 15 events processed",
  "error": null
}
```

### Example Usage

```python
# Preview deletion of old test events
preview = await bulk_calendar_operations(
    user_google_email="user@gmail.com",
    operation="delete",
    title_pattern="(?i)(test|temp|draft)",
    time_max="2025-08-31T23:59:59Z",
    dry_run=True  # Preview only
)

# Actually delete after review
if preview["totalMatched"] < 10:  # Safety check
    result = await bulk_calendar_operations(
        user_google_email="user@gmail.com",
        operation="delete",
        title_pattern="(?i)(test|temp|draft)",
        time_max="2025-08-31T23:59:59Z",
        dry_run=False  # Execute
    )

# Find all events with specific attendee
attendee_events = await bulk_calendar_operations(
    user_google_email="user@gmail.com",
    operation="list",
    attendee_email="external@client.com",
    time_min="2025-01-01T00:00:00Z"
)
```

---

## move_events_between_calendars

Move or copy events from one calendar to another with filtering options. **Recently Fixed! 🎉**

### 🔧 Recent Fixes
- **✅ Type Validation Fixed**: Resolved "originalId is a required property" error
- **✅ Field Name Correction**: Fixed field names in response structure to match type definitions
- **✅ Production Ready**: Fully tested and working for calendar migrations

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `source_calendar_id` | string | Yes | Source calendar ID | - |
| `target_calendar_id` | string | Yes | Target calendar ID | - |
| `time_min` | string | No | Start of time range (RFC3339) | Current time |
| `time_max` | string | No | End of time range (RFC3339) | - |
| `title_pattern` | string | No | Regex pattern for selective migration | - |
| `max_results` | integer | No | Max events to move (1-500) | 50 |
| `delete_from_source` | boolean | No | Delete from source after copying | `false` |

### Returns

```json
{
  "success": true,
  "sourceCalendarId": "primary",
  "targetCalendarId": "work@company.com",
  "userEmail": "user@gmail.com",
  "totalFound": 10,
  "totalCopied": 8,
  "totalDeleted": 8,
  "results": [
    {
      "originalId": "abc123",
      "newId": "xyz789",
      "summary": "Team Meeting",
      "status": "moved"
    }
  ],
  "message": "📋 Calendar Migration Results: 8 events moved successfully",
  "error": null
}
```

### Example Usage

```python
# Copy events to backup calendar (keep originals)
backup = await move_events_between_calendars(
    user_google_email="user@gmail.com",
    source_calendar_id="primary",
    target_calendar_id="backup@personal.com",
    time_min="2025-01-01T00:00:00Z",
    time_max="2025-12-31T23:59:59Z",
    delete_from_source=False  # Copy only
)

# Move test events to test calendar
test_migration = await move_events_between_calendars(
    user_google_email="user@gmail.com",
    source_calendar_id="primary",
    target_calendar_id="test_calendar@company.com",
    title_pattern="(?i)(test|demo|sample)",
    delete_from_source=True  # Actually move
)

# Migrate work events to dedicated calendar
work_migration = await move_events_between_calendars(
    user_google_email="user@gmail.com",
    source_calendar_id="primary",
    target_calendar_id="work@company.com",
    title_pattern="(?i)(meeting|standup|review|presentation)",
    time_min="2025-09-01T00:00:00Z",
    max_results=100,
    delete_from_source=True
)
```

---

## Common Error Codes

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `AUTH_REQUIRED` | User needs to authenticate | Run `start_google_auth` |
| `INSUFFICIENT_PERMISSION` | Missing Calendar scopes | Re-authenticate with proper scopes |
| `EVENT_NOT_FOUND` | Event ID doesn't exist | Verify event ID and calendar |
| `CALENDAR_NOT_FOUND` | Calendar ID doesn't exist | Check calendar ID with `list_calendars` |
| `TIME_FORMAT_ERROR` | Invalid time format | Use RFC3339 format (auto-corrected) |
| `QUOTA_EXCEEDED` | Calendar API quota exceeded | Wait for quota reset |
| `INVALID_ATTENDEE` | Invalid attendee email | Check email format |
| `ACCESS_DENIED` | No permission to calendar | Check sharing permissions |

## Time Format Guidelines

### Supported Formats

```python
# RFC3339 with timezone (recommended)
"2025-09-01T14:00:00-05:00"    # 2 PM Eastern
"2025-09-01T19:00:00Z"         # 7 PM UTC

# Auto-corrected formats
"2025-09-01T14:00:00"          # Becomes "2025-09-01T14:00:00Z"

# Date only (all-day events)
"2025-09-01"                   # Becomes "2025-09-01T00:00:00Z"
```

### Timezone Handling

- **Automatic Correction**: Missing timezone info is corrected to UTC
- **Flexible Input**: Accepts various formats and auto-corrects them
- **Timezone Parameter**: Can specify timezone separately for both start/end times

## Best Practices

1. **Event Creation**: Use HTML formatting in descriptions for rich content
2. **Bulk Operations**: Use batch tools for multiple events to reduce API calls
3. **Time Formats**: Use RFC3339 with timezone for precision
4. **Calendar Migration**: Test with `dry_run=true` before bulk operations
5. **Error Handling**: Check for quota limits and implement retries
6. **Attendee Management**: Validate email formats before adding attendees
7. **HTML Content**: Use supported tags for rich event descriptions

## Rate Limits

Calendar API quotas:
- **Daily quota**: 1,000,000 requests per day
- **Per-user rate limit**: 100 requests per 100 seconds per user
- **Burst limit**: 1000 requests per 100 seconds

Quota costs:
- Read operations: 1 unit
- Write operations: 5 units
- Batch operations: 1 unit per item

---

For more information, see the [main API documentation](../README.md) or [Google Calendar API documentation](https://developers.google.com/calendar/api/v3/reference).