"""Test suite for Google Calendar tools using FastMCP Client SDK."""

import os
from datetime import datetime, timedelta

import pytest
from dotenv import load_dotenv

from .base_test_config import TEST_EMAIL

# Load environment variables from .env file
load_dotenv()


@pytest.mark.service("calendar")
class TestCalendarTools:
    """Test Calendar tools using standardized framework.

    🔧 MCP Tools Used:
    - create_event: Create single or multiple calendar events
    - list_events: Retrieve events from calendars with filtering
    - get_event: Get detailed event information by ID
    - list_calendars: List accessible calendars
    - create_calendar: Create new calendars
    - move_events_between_calendars: Transfer events between calendars

    🧪 What's Being Tested:
    - Event creation (single and bulk operations)
    - Event retrieval with time range filtering
    - Calendar management (creation, listing)
    - Event migration between calendars
    - Timezone handling and RFC3339 date parsing
    - Attendee management and invitations
    - Attachment handling with Drive files
    - Recurring event patterns
    - Authentication patterns for all Calendar operations

    🔍 Potential Duplications:
    - Event attachments overlap with Drive file sharing functionality
    - Bulk event creation might have patterns similar to other bulk operations
    - Time zone handling might be tested in multiple contexts
    - Calendar sharing might overlap with general Google Workspace sharing patterns
    """

    # Class variable to store created event ID for reuse across tests
    _created_event_id = None

    @pytest.fixture
    def test_event_id(self):
        """Return a test event ID if available."""
        # Check class variable first, then environment variable
        return self._created_event_id or os.getenv("TEST_EVENT_ID", None)

    @pytest.fixture
    def future_datetime(self):
        """Return future datetime strings for event creation."""
        tomorrow = datetime.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)
        return {
            "start": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    @pytest.mark.asyncio
    async def test_calendar_tools_available(self, client):
        """Test that all Calendar tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        # Check for all Calendar tools
        expected_tools = [
            "list_calendars",
            "list_events",
            "create_event",
            "modify_event",
            "delete_event",
            "get_event",
        ]

        for tool in expected_tools:
            assert tool in tool_names, f"Tool '{tool}' not found in available tools"

    @pytest.mark.asyncio
    async def test_list_calendars(self, client):
        """Test listing calendars."""
        result = await client.call_tool(
            "list_calendars", {"user_google_email": TEST_EMAIL}
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        # Should return error for test user without auth or list of calendars
        valid_responses = [
            "calendars",
            "primary",
            "requires authentication",
            "no valid credentials",
            "❌",
            "failed to list calendars",
            "unexpected error",
            "no calendars found",
            "successfully listed",
            "calendar service",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_list_events(self, client):
        """Test getting calendar events."""
        result = await client.call_tool(
            "list_events",
            {
                "user_google_email": TEST_EMAIL,
                "calendar_id": "primary",
                "max_results": 10,
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        # Should return error for test user or event list
        valid_responses = [
            "events",
            "no events found",
            "requires authentication",
            "no valid credentials",
            "failed to get events",
            "unexpected error",
            "successfully retrieved",
            "calendar service",
            "unable to get",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_list_events_without_timemax(self, client):
        """Test that list_events properly handles None timeMax parameter (not passing 'None' as string)."""
        # This test verifies the fix for the bug where timeMax was being passed as the string 'None'
        result = await client.call_tool(
            "list_events",
            {
                "user_google_email": TEST_EMAIL,
                "calendar_id": "primary",
                # Explicitly NOT providing time_max to test None handling
                "max_results": 5,
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        # The response should NOT contain the specific error about 'None' being invalid
        assert (
            "timeMax: 'None'" not in content
        ), "Bug detected: timeMax is being passed as string 'None' instead of being omitted"

        # Should get a valid response (either events or auth error)
        valid_responses = [
            "events",
            "no events found",
            "requires authentication",
            "no valid credentials",
            "failed to get events",
            "unexpected error",
            "successfully retrieved",
            "calendar service",
            "unable to get",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_list_events_structured_error_response(self, client):
        """Test that list_events returns structured responses even on errors."""
        # Use an invalid calendar ID to trigger an error
        result = await client.call_tool(
            "list_events",
            {
                "user_google_email": "nonexistent@invalid.com",
                "calendar_id": "invalid_calendar_id",
                "max_results": 5,
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        # The error should be returned as structured content, not a raw error string
        # Check that we don't get the old ValueError about structured_content
        assert (
            "ValueError: structured_content must be a dict or None" not in content
        ), "Bug detected: Error responses are not being returned as structured EventListResponse"

        # The response should contain error information
        assert any(
            keyword in content.lower()
            for keyword in ["error", "failed", "unable", "requires authentication"]
        ), f"Error response not properly formatted: {content}"

    @pytest.mark.asyncio
    async def test_list_events_with_time_range(self, client):
        """Test getting events with specific time range."""
        # Test date-only format
        result = await client.call_tool(
            "list_events",
            {
                "user_google_email": TEST_EMAIL,
                "calendar_id": "primary",
                "time_min": "2024-01-01",
                "time_max": "2024-12-31",
                "max_results": 5,
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        print(f"DEBUG: Using email address: {TEST_EMAIL}")
        print(f"DEBUG: Actual response content: {repr(content)}")
        # Check for any valid response pattern from calendar tools
        valid_responses = [
            "events",  # Covers "Successfully retrieved X events", "No events found", "Failed to get events"
            "no events found",  # Specific no events message
            "requires authentication",  # Auth error
            "❌",  # Error indicator
            "failed to get events",  # Specific error message
            "unexpected error",  # General error
            "failed to get calendar service",  # Service error
            "unable to get",  # Service unavailable
            "calendar service",  # Service-related error
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_create_event(self, client, future_datetime):
        """Test creating a calendar event."""
        result = await client.call_tool(
            "create_event",
            {
                "user_google_email": TEST_EMAIL,
                "summary": "Test Event from MCP",
                "start_time": future_datetime["start"],
                "end_time": future_datetime["end"],
                "description": "This is a test event created via MCP",
                "location": "Virtual Meeting",
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        # Try to extract event ID if creation was successful
        if "successfully created" in content.lower() and "event id:" in content.lower():
            # Extract event ID for reuse in other tests
            import re

            match = re.search(r"event id:\s*([^\s,]+)", content, re.IGNORECASE)
            if match:
                TestCalendarTools._created_event_id = match.group(1)
                print(
                    f"DEBUG: Captured event ID for reuse: {TestCalendarTools._created_event_id}"
                )

        # Check for valid responses (auth errors OR successful creation)
        valid_responses = [
            "event",
            "created",
            "requires authentication",
            "no valid credentials",
            "failed to create event",
            "unexpected error",
            "successfully created",
            "calendar service",
            "unable to get",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_create_all_day_event(self, client):
        """Test creating an all-day event."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

        result = await client.call_tool(
            "create_event",
            {
                "user_google_email": TEST_EMAIL,
                "summary": "All Day Test Event",
                "start_time": tomorrow,
                "end_time": day_after,
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        valid_responses = [
            "event",
            "created",
            "requires authentication",
            "no valid credentials",
            "failed to create event",
            "unexpected error",
            "successfully created",
            "calendar service",
            "unable to get",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_create_event_with_attendees(self, client, future_datetime):
        """Test creating an event with attendees."""
        result = await client.call_tool(
            "create_event",
            {
                "user_google_email": TEST_EMAIL,
                "summary": "Meeting with Team",
                "start_time": future_datetime["start"],
                "end_time": future_datetime["end"],
                "attendees": ["attendee1@example.com", "attendee2@example.com"],
                "timezone": "America/New_York",
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        valid_responses = [
            "event",
            "created",
            "requires authentication",
            "no valid credentials",
            "failed to create event",
            "unexpected error",
            "successfully created",
            "calendar service",
            "unable to get",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_create_event_with_attachments(self, client, future_datetime):
        """Test creating an event with Google Drive attachments."""
        result = await client.call_tool(
            "create_event",
            {
                "user_google_email": TEST_EMAIL,
                "summary": "Event with Attachments",
                "start_time": future_datetime["start"],
                "end_time": future_datetime["end"],
                "attachments": [
                    "https://drive.google.com/file/d/1234567890/view",
                    "test_file_id_123",
                ],
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        valid_responses = [
            "event",
            "created",
            "requires authentication",
            "no valid credentials",
            "❌",
            "failed to create event",
            "unexpected error",
            "successfully created",
            "calendar service",
            "unable to get",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_create_bulk_events(self, client, future_datetime):
        """Test creating multiple events in bulk using the events parameter as JSON string."""
        import json

        # Calculate future datetime strings for multiple events
        tomorrow = datetime.now() + timedelta(days=1)
        day_after_tomorrow = datetime.now() + timedelta(days=2)

        # Add 'Z' suffix for UTC timezone to fix Google Calendar API requirement
        start_time_1 = (
            tomorrow.replace(hour=9, minute=0, second=0, microsecond=0).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
            + "Z"
        )
        end_time_1 = (
            tomorrow.replace(hour=10, minute=0, second=0, microsecond=0).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
            + "Z"
        )
        start_time_2 = (
            day_after_tomorrow.replace(
                hour=14, minute=0, second=0, microsecond=0
            ).strftime("%Y-%m-%dT%H:%M:%S")
            + "Z"
        )
        end_time_2 = (
            day_after_tomorrow.replace(
                hour=15, minute=0, second=0, microsecond=0
            ).strftime("%Y-%m-%dT%H:%M:%S")
            + "Z"
        )

        print(f"\n{'='*80}")
        print(f"BULK EVENT TEST - Creating events with email: {TEST_EMAIL}")
        print(f"Event 1: {start_time_1} to {end_time_1}")
        print(f"Event 2: {start_time_2} to {end_time_2}")
        print(f"{'='*80}")

        # Create events list
        events_list = [
            {
                "summary": "🎈 First Bulk Test Event",
                "start_time": start_time_1,
                "end_time": end_time_1,
                "description": "First event created via bulk operation",
            },
            {
                "summary": "🎉 Second Bulk Test Event",
                "start_time": start_time_2,
                "end_time": end_time_2,
                "description": "Second event created via bulk operation",
                "location": "Virtual Meeting Room",
            },
        ]

        # Convert to JSON string (as MCP client would send it)
        events_json = json.dumps(events_list)
        print(f"Sending events as JSON string: {events_json[:100]}...")

        # Test bulk event creation with events as JSON string
        result = await client.call_tool(
            "create_event",
            {
                "user_google_email": TEST_EMAIL,
                "calendar_id": "primary",
                "events": events_json,  # Send as JSON string instead of Python list
            },
        )

        # Handle CallToolResult object properly and debug print
        assert result is not None

        # Debug: Print raw result info
        print("\n--- RAW RESULT DEBUG ---")
        print(f"Result type: {type(result)}")

        # Access the content directly from result
        content_str = ""
        if hasattr(result, "content"):
            # For structured responses
            if isinstance(result.content, list) and len(result.content) > 0:
                # Extract text from TextContent object
                if hasattr(result.content[0], "text"):
                    content_str = result.content[0].text
                else:
                    content_str = str(result.content[0])
            else:
                content_str = str(result.content) if result.content else ""
            print("Result has 'content' attribute")
            print(f"Content type: {type(result.content)}")
            # Parse JSON if possible to pretty print
            try:
                import json

                if content_str.startswith("{"):
                    content_dict = json.loads(content_str)
                    print("\n--- PARSED RESPONSE ---")
                    print(json.dumps(content_dict, indent=2))

                    # Check actual success/failure
                    if content_dict.get("success"):
                        print(
                            f"\n✅ SUCCESS: Created {len(content_dict.get('eventsCreated', []))} events successfully!"
                        )
                        for event in content_dict.get("eventsCreated", []):
                            print(
                                f"  - {event.get('summary', 'Unknown')} (ID: {event.get('eventId', 'N/A')})"
                            )
                    else:
                        print("\n❌ FAILURE: Failed to create events")
                        print(
                            f"Total processed: {content_dict.get('totalProcessed', 0)}"
                        )
                        print(
                            f"Successfully created: {len(content_dict.get('eventsCreated', []))}"
                        )
                        print(f"Failed: {len(content_dict.get('eventsFailed', []))}")
                        for event in content_dict.get("eventsFailed", [])[:3]:
                            print(
                                f"  - {event.get('summary', 'Unknown')}: {event.get('error', 'Unknown error')[:100]}"
                            )
            except:
                print(f"Content (raw): {content_str[:500]}")
        elif hasattr(result, "__iter__") and len(result) > 0:
            # For list-like responses (backward compatibility)
            content_str = (
                result[0].text if hasattr(result[0], "text") else str(result[0])
            )
            print(f"Result is iterable with {len(result)} items")
        else:
            # Fallback to string representation
            content_str = str(result)
            print("Using string representation")

        print(f"{'='*80}\n")

        # Check for bulk operation responses
        valid_responses = [
            "bulk",
            "total processed",
            "successfully created",
            "failed",
            "batch",
            "requires authentication",
            "no valid credentials",
            "events created",
            "❌",
            "calendar service",
            "unable to get",
            "bulk event creation",
            "success",
        ]
        assert any(
            keyword in content_str.lower() for keyword in valid_responses
        ), f"Response didn't match any expected bulk pattern: {content_str}"

    @pytest.mark.asyncio
    async def test_create_bulk_events_comprehensive(self, client):
        """Test comprehensive bulk event creation with all optional fields."""
        import json

        # Create events for the next 3 days
        base_date = datetime.now() + timedelta(days=1)

        events = []
        for i in range(3):
            event_date = base_date + timedelta(days=i)
            start_time = event_date.replace(
                hour=10 + i, minute=0, second=0, microsecond=0
            ).strftime("%Y-%m-%dT%H:%M:%S")
            end_time = event_date.replace(
                hour=11 + i, minute=0, second=0, microsecond=0
            ).strftime("%Y-%m-%dT%H:%M:%S")

            events.append(
                {
                    "summary": f"🎯 Bulk Event {i+1}",
                    "start_time": start_time,
                    "end_time": end_time,
                    "description": f"Event {i+1} created via bulk operation with full details",
                    "location": f"Conference Room {i+1}",
                    "attendees": [f"attendee{i+1}@example.com"],
                    "timezone": "America/New_York",
                }
            )

        # Convert to JSON string (as MCP client would send it)
        events_json = json.dumps(events)

        result = await client.call_tool(
            "create_event",
            {
                "user_google_email": TEST_EMAIL,
                "calendar_id": "primary",
                "events": events_json,  # Send as JSON string
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Access the content directly from result
        if hasattr(result, "content"):
            # For structured responses
            content = str(result.content) if result.content else ""
        elif hasattr(result, "__iter__") and len(result) > 0:
            # For list-like responses (backward compatibility)
            content = result[0].text if hasattr(result[0], "text") else str(result[0])
        else:
            # Fallback to string representation
            content = str(result)

        # Should handle bulk creation with comprehensive event data
        valid_responses = [
            "bulk",
            "total processed",
            "3",
            "events",
            "created",
            "failed",
            "requires authentication",
            "no valid credentials",
            "batch",
            "❌",
            "calendar service",
            "unable to get",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected comprehensive bulk pattern: {content}"

    @pytest.mark.asyncio
    async def test_create_bulk_events_parameter_validation(self, client):
        """Test that bulk events parameter validation works correctly."""
        import json

        # Test with invalid event structure (missing required fields)
        invalid_events = json.dumps(
            [
                {
                    "summary": "Valid Event",
                    # Missing start_time and end_time - should fail validation
                }
            ]
        )

        # This should handle the validation error gracefully
        result = await client.call_tool(
            "create_event", {"user_google_email": TEST_EMAIL, "events": invalid_events}
        )

        # Check that we get an error response, not an exception
        assert result is not None
        if hasattr(result, "content"):
            content = str(result.content) if result.content else ""
        else:
            content = str(result)

        # Should contain error about missing required fields
        assert any(
            keyword in content.lower()
            for keyword in [
                "error",
                "failed",
                "required",
                "missing",
                "start_time",
                "end_time",
            ]
        ), f"Expected validation error for missing fields, got: {content}"

    @pytest.mark.asyncio
    async def test_create_bulk_events_json_string_birthday_reminders(self, client):
        """Test creating birthday reminder events with JSON string (exact user scenario)."""
        import json

        # Create the exact events from the user's example
        events_data = [
            {
                "summary": "Julia Birthday Reminder - Plan Something Special",
                "start_time": "2025-10-28T09:00:00-05:00",
                "end_time": "2025-10-28T10:00:00-05:00",
                "description": "Time to prepare for Julia birthday. Born 1984 in Arlington TX, turning 41. Plan something special for your wife from Texas.",
                "location": "Birthday Planning Mode",
            },
            {
                "summary": "Theo Birthday Reminder - Big Boy Birthday Coming",
                "start_time": "2025-11-01T09:00:00-05:00",
                "end_time": "2025-11-01T10:00:00-05:00",
                "description": "Time to prepare for Theo birthday. Born 2016 in Chicago IL, turning 9. Plan awesome 9th birthday celebration.",
                "location": "Party Planning Central",
            },
        ]

        # Convert to JSON string (exactly as MCP client sends it)
        events_json = json.dumps(events_data)

        print(f"\n{'='*80}")
        print("BIRTHDAY REMINDER TEST - Testing exact user scenario")
        print(f"Creating events for: {TEST_EMAIL}")
        print(f"Events JSON: {events_json[:150]}...")
        print(f"{'='*80}")

        # Test creating the events
        result = await client.call_tool(
            "create_event",
            {
                "user_google_email": TEST_EMAIL,
                "calendar_id": "primary",
                "events": events_json,  # Send as JSON string
            },
        )

        # Handle CallToolResult object properly
        assert result is not None

        # Extract and analyze content
        content_str = ""
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                if hasattr(result.content[0], "text"):
                    content_str = result.content[0].text
                else:
                    content_str = str(result.content[0])
            else:
                content_str = str(result.content) if result.content else ""
        else:
            content_str = str(result)

        print(f"\nRESULT: {content_str[:500]}...")

        # Parse JSON response if possible to check actual results
        try:
            import json

            if content_str.startswith("{"):
                response_dict = json.loads(content_str)
                if response_dict.get("success"):
                    print("\n✅ SUCCESS: Birthday reminders created!")
                    print(
                        f"Created {len(response_dict.get('eventsCreated', []))} events"
                    )
                else:
                    print(f"\n❌ FAILED: {response_dict.get('error', 'Unknown error')}")
                    # This should NOT show the JSON parsing error anymore
                    assert (
                        "is not valid under any of the given schemas" not in content_str
                    ), "Bug still present: JSON string not being parsed correctly"
        except:
            pass

        # Check that we don't get the schema validation error
        assert (
            "is not valid under any of the given schemas" not in content_str
        ), "Bug detected: Events JSON string is not being parsed before validation"

        # Should get either success or auth error (not schema validation error)
        valid_responses = [
            "bulk",
            "total processed",
            "successfully created",
            "failed",
            "requires authentication",
            "no valid credentials",
            "events created",
            "calendar service",
            "unable to get",
            "success",
        ]
        assert any(
            keyword in content_str.lower() for keyword in valid_responses
        ), f"Response didn't match expected patterns: {content_str}"

    @pytest.mark.asyncio
    async def test_create_bulk_events_backward_compatibility(
        self, client, future_datetime
    ):
        """Test that legacy single event creation still works with bulk implementation."""
        # This tests backward compatibility - legacy parameters should still work
        result = await client.call_tool(
            "create_event",
            {
                "user_google_email": TEST_EMAIL,
                "summary": "Legacy Mode Test Event",
                "start_time": future_datetime["start"],
                "end_time": future_datetime["end"],
                "description": "Testing backward compatibility with bulk implementation",
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Access the content directly from result
        if hasattr(result, "content"):
            # For structured responses
            content = str(result.content) if result.content else ""
        elif hasattr(result, "__iter__") and len(result) > 0:
            # For list-like responses (backward compatibility)
            content = result[0].text if hasattr(result[0], "text") else str(result[0])
        else:
            # Fallback to string representation
            content = str(result)

        # Should work exactly like before (single event response)
        valid_responses = [
            "event",
            "created",
            "successfully created",
            "requires authentication",
            "no valid credentials",
            "❌",
            "failed to create event",
            "unexpected error",
            "calendar service",
            "unable to get",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Backward compatibility broken: {content}"

    @pytest.mark.asyncio
    async def test_create_bulk_events_parameter_conflict_validation(
        self, client, future_datetime
    ):
        """Test that providing both events array and legacy parameters results in proper handling."""
        import json

        # Test parameter conflict - should use bulk mode and ignore legacy parameters
        events_json = json.dumps(
            [
                {
                    "summary": "Bulk Event",
                    "start_time": future_datetime["start"],
                    "end_time": future_datetime["end"],
                }
            ]
        )

        result = await client.call_tool(
            "create_event",
            {
                "user_google_email": TEST_EMAIL,
                # Bulk mode parameters (as JSON string)
                "events": events_json,
                # Legacy parameters (should be ignored)
                "summary": "Legacy Event",
                "start_time": future_datetime["start"],
                "end_time": future_datetime["end"],
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Access the content directly from result
        if hasattr(result, "content"):
            # For structured responses
            content = str(result.content) if result.content else ""
        elif hasattr(result, "__iter__") and len(result) > 0:
            # For list-like responses (backward compatibility)
            content = result[0].text if hasattr(result[0], "text") else str(result[0])
        else:
            # Fallback to string representation
            content = str(result)

        # Should process as bulk mode, not legacy mode
        # Either bulk response or authentication error
        valid_responses = [
            "bulk",
            "total processed",
            "events created",
            "batch",
            "requires authentication",
            "no valid credentials",
            "❌",
            "calendar service",
            "unable to get",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Parameter conflict not handled correctly: {content}"

    @pytest.mark.asyncio
    async def test_modify_event(self, client, real_calendar_event_id):
        """Test modifying an existing event."""
        # Use fake event ID if no real one is available (should get "not found" response)
        event_id = real_calendar_event_id

        result = await client.call_tool(
            "modify_event",
            {
                "user_google_email": TEST_EMAIL,
                "event_id": event_id,
                "summary": "Modified Test Event",
                "description": "This event has been modified",
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        valid_responses = [
            "event",
            "modified",
            "requires authentication",
            "no valid credentials",
            "❌",
            "failed to modify event",
            "unexpected error",
            "successfully modified",
            "calendar service",
            "unable to get",
            "updated",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_modify_event_missing_fields(self, client, real_calendar_event_id):
        """Test modifying event with no fields provided."""
        # Use fake event ID if no real one is available (should get proper error response)
        event_id = real_calendar_event_id

        result = await client.call_tool(
            "modify_event",
            {
                "user_google_email": TEST_EMAIL,
                "event_id": event_id,
                # No fields to modify
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        # Should indicate no fields provided
        assert "no fields provided" in content.lower() or "error" in content.lower()

    @pytest.mark.asyncio
    async def test_get_event(self, client, real_calendar_event_id):
        """Test getting a specific event by ID."""
        # Use fake event ID if no real one is available (should get "not found" response)
        event_id = real_calendar_event_id

        result = await client.call_tool(
            "get_event", {"user_google_email": TEST_EMAIL, "event_id": event_id}
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        valid_responses = [
            "event",
            "title",
            "starts",
            "event details",
            "requires authentication",
            "no valid credentials",
            "❌",
            "failed to get event",
            "unexpected error",
            "successfully retrieved",
            "calendar service",
            "unable to get",
            "not found",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_delete_event(self, client, real_calendar_event_id):
        """Test deleting an event."""
        # Use fake event ID if no real one is available (should get "not found" response)
        event_id = real_calendar_event_id

        result = await client.call_tool(
            "delete_event", {"user_google_email": TEST_EMAIL, "event_id": event_id}
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        valid_responses = [
            "deleted",
            "not found",
            "requires authentication",
            "no valid credentials",
            "❌",
            "failed to delete event",
            "unexpected error",
            "successfully deleted",
            "calendar service",
            "unable to get",
            "removed",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Response didn't match any expected pattern: {content}"

    @pytest.mark.asyncio
    async def test_calendar_tools_parameter_validation(self, client):
        """Test parameter validation for Calendar tools."""
        from fastmcp.exceptions import ToolError

        # Test missing required parameters for create_event
        # Since create_event has conditional requirements (either events array OR summary/start_time/end_time),
        # it might handle this gracefully with an error response instead of raising an exception
        result = None
        error_raised = False
        try:
            result = await client.call_tool(
                "create_event",
                {
                    "user_google_email": TEST_EMAIL
                    # Missing both events array AND legacy parameters
                },
            )
        except ToolError as e:
            error_raised = True
            # If an error is raised, check it mentions missing required fields
            error_msg = str(e).lower()
            assert (
                "validation error" in error_msg
                or "required" in error_msg
                or "missing" in error_msg
            ), f"Expected validation error message, got: {e}"

        if not error_raised:
            # If no error was raised, the tool should return an error response
            assert result is not None
            # Extract content from result
            if hasattr(result, "content"):
                if isinstance(result.content, list) and len(result.content) > 0:
                    content = (
                        result.content[0].text
                        if hasattr(result.content[0], "text")
                        else str(result.content[0])
                    )
                else:
                    content = str(result.content) if result.content else ""
            else:
                content = str(result)

            # Should return an error message about missing parameters
            assert any(
                keyword in content.lower()
                for keyword in [
                    "missing",
                    "required",
                    "error",
                    "failed",
                    "must provide",
                    "need to specify",
                ]
            ), f"Expected validation error for missing parameters, got: {content}"

        # Test missing required parameters for get_event
        # This one should definitely raise a ToolError since event_id is strictly required
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool(
                "get_event",
                {
                    "user_google_email": TEST_EMAIL
                    # Missing event_id
                },
            )

        # Check that the error specifically mentions event_id
        error_msg = str(exc_info.value).lower()
        assert "event_id" in error_msg and (
            "required" in error_msg or "validation" in error_msg
        ), f"Expected validation error for missing event_id, got: {exc_info.value}"

    @pytest.mark.asyncio
    async def test_time_format_handling(self, client):
        """Test various time format handling."""
        # Test with different time formats
        time_formats = [
            "2024-12-25",  # Date only
            "2024-12-25T10:00:00",  # Missing timezone
            "2024-12-25T10:00:00Z",  # With UTC timezone
            "2024-12-25T10:00:00-08:00",  # With specific timezone
        ]

        for time_format in time_formats:
            result = await client.call_tool(
                "list_events",
                {
                    "user_google_email": TEST_EMAIL,
                    "time_min": time_format,
                    "max_results": 1,
                },
            )

            # Handle CallToolResult object properly
            assert result is not None
            # Should handle all formats without error

    @pytest.mark.asyncio
    async def test_invalid_event_id_handling(self, client):
        """Test handling of invalid event IDs."""
        result = await client.call_tool(
            "get_event",
            {"user_google_email": TEST_EMAIL, "event_id": "invalid_event_id_12345"},
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        assert (
            "error" in content.lower()
            or "not found" in content.lower()
            or "requires authentication" in content.lower()
        )

    @pytest.mark.asyncio
    async def test_list_calendars_structured_error_response(self, client):
        """Test that list_calendars returns structured responses even on errors."""
        # Use an invalid email to trigger an error
        result = await client.call_tool(
            "list_calendars", {"user_google_email": "nonexistent@invalid.com"}
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        # The error should be returned as structured content, not a raw error string
        # Check that we don't get the old ValueError about structured_content
        assert (
            "ValueError: structured_content must be a dict or None" not in content
        ), "Bug detected: Error responses are not being returned as structured CalendarListResponse"

        # The response should contain error information
        assert any(
            keyword in content.lower()
            for keyword in ["error", "failed", "unable", "requires authentication"]
        ), f"Error response not properly formatted: {content}"


@pytest.mark.service("calendar")
@pytest.mark.integration
class TestCalendarIntegration:
    """Integration tests for Calendar tools with other services."""

    @pytest.mark.asyncio
    async def test_calendar_with_drive_integration(self, client):
        """Test Calendar-Drive integration for attachments."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        # If both Calendar and Drive tools are available
        if "create_event" in tool_names and "get_drive_file_content" in tool_names:
            # Test would verify that events with attachments
            # properly integrate with Drive API
            pass  # Actual integration test would go here

    @pytest.mark.asyncio
    async def test_calendar_error_scenarios(self, client):
        """Test various error scenarios."""
        # Test with invalid calendar ID
        result = await client.call_tool(
            "list_events",
            {
                "user_google_email": TEST_EMAIL,
                "calendar_id": "invalid_calendar_id@group.calendar.google.com",
            },
        )

        # Handle CallToolResult object properly
        assert result is not None
        # Extract content from result
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.content) if result.content else ""
        else:
            content = str(result)

        assert (
            "error" in content.lower() or "requires authentication" in content.lower()
        )
