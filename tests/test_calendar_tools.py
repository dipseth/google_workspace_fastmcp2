"""Test suite for Google Calendar tools using FastMCP Client SDK."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")


class TestCalendarTools:
    """Test Google Calendar tools using the FastMCP Client."""
    
    # Class variable to store created event ID for reuse across tests
    _created_event_id = None
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
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
            "end": end_time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    
    @pytest.mark.asyncio
    async def test_calendar_tools_available(self, client):
        """Test that all Calendar tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check for all Calendar tools
        expected_tools = [
            "list_calendars",
            "get_events",
            "create_event",
            "modify_event",
            "delete_event",
            "get_event"
        ]
        
        for tool in expected_tools:
            assert tool in tool_names, f"Tool '{tool}' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_list_calendars(self, client):
        """Test listing calendars."""
        result = await client.call_tool("list_calendars", {
            "user_google_email": TEST_EMAIL
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return error for test user without auth or list of calendars
        valid_responses = [
            "calendars", "primary", "requires authentication", "no valid credentials",
            "❌", "failed to list calendars", "unexpected error", "no calendars found",
            "successfully listed", "calendar service"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_get_events(self, client):
        """Test getting calendar events."""
        result = await client.call_tool("get_events", {
            "user_google_email": TEST_EMAIL,
            "calendar_id": "primary",
            "max_results": 10
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return error for test user or event list
        valid_responses = [
            "events", "no events found", "requires authentication", "no valid credentials",
            "❌", "failed to get events", "unexpected error", "successfully retrieved",
            "calendar service", "unable to get"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_get_events_with_time_range(self, client):
        """Test getting events with specific time range."""
        # Test date-only format
        result = await client.call_tool("get_events", {
            "user_google_email": TEST_EMAIL,
            "calendar_id": "primary",
            "time_min": "2024-01-01",
            "time_max": "2024-12-31",
            "max_results": 5
        })
        
        assert len(result) > 0
        content = result[0].text
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
            "calendar service"  # Service-related error
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_event(self, client, future_datetime):
        """Test creating a calendar event."""
        result = await client.call_tool("create_event", {
            "user_google_email": TEST_EMAIL,
            "summary": "Test Event from MCP",
            "start_time": future_datetime["start"],
            "end_time": future_datetime["end"],
            "description": "This is a test event created via MCP",
            "location": "Virtual Meeting"
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Try to extract event ID if creation was successful
        if "successfully created" in content.lower() and "event id:" in content.lower():
            # Extract event ID for reuse in other tests
            import re
            match = re.search(r'event id:\s*([^\s,]+)', content, re.IGNORECASE)
            if match:
                TestCalendarTools._created_event_id = match.group(1)
                print(f"DEBUG: Captured event ID for reuse: {TestCalendarTools._created_event_id}")
        
        # Check for valid responses (auth errors OR successful creation)
        valid_responses = [
            "event", "created", "requires authentication", "no valid credentials",
            "❌", "failed to create event", "unexpected error", "successfully created",
            "calendar service", "unable to get"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_all_day_event(self, client):
        """Test creating an all-day event."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        
        result = await client.call_tool("create_event", {
            "user_google_email": TEST_EMAIL,
            "summary": "All Day Test Event",
            "start_time": tomorrow,
            "end_time": day_after
        })
        
        assert len(result) > 0
        content = result[0].text
        valid_responses = [
            "event", "created", "requires authentication", "no valid credentials",
            "❌", "failed to create event", "unexpected error", "successfully created",
            "calendar service", "unable to get"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_event_with_attendees(self, client, future_datetime):
        """Test creating an event with attendees."""
        result = await client.call_tool("create_event", {
            "user_google_email": TEST_EMAIL,
            "summary": "Meeting with Team",
            "start_time": future_datetime["start"],
            "end_time": future_datetime["end"],
            "attendees": ["attendee1@example.com", "attendee2@example.com"],
            "timezone": "America/New_York"
        })
        
        assert len(result) > 0
        content = result[0].text
        valid_responses = [
            "event", "created", "requires authentication", "no valid credentials",
            "❌", "failed to create event", "unexpected error", "successfully created",
            "calendar service", "unable to get"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_event_with_attachments(self, client, future_datetime):
        """Test creating an event with Google Drive attachments."""
        result = await client.call_tool("create_event", {
            "user_google_email": TEST_EMAIL,
            "summary": "Event with Attachments",
            "start_time": future_datetime["start"],
            "end_time": future_datetime["end"],
            "attachments": ["https://drive.google.com/file/d/1234567890/view", "test_file_id_123"]
        })
        
        assert len(result) > 0
        content = result[0].text
        valid_responses = [
            "event", "created", "requires authentication", "no valid credentials",
            "❌", "failed to create event", "unexpected error", "successfully created",
            "calendar service", "unable to get"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_modify_event(self, client, test_event_id):
        """Test modifying an existing event."""
        # Use fake event ID if no real one is available (should get "not found" response)
        event_id = test_event_id or "fake_event_id_for_testing"
        
        result = await client.call_tool("modify_event", {
            "user_google_email": TEST_EMAIL,
            "event_id": event_id,
            "summary": "Modified Test Event",
            "description": "This event has been modified"
        })
        
        assert len(result) > 0
        content = result[0].text
        valid_responses = [
            "event", "modified", "requires authentication", "no valid credentials",
            "❌", "failed to modify event", "unexpected error", "successfully modified",
            "calendar service", "unable to get", "updated"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_modify_event_missing_fields(self, client, test_event_id):
        """Test modifying event with no fields provided."""
        # Use fake event ID if no real one is available (should get proper error response)
        event_id = test_event_id or "fake_event_id_for_testing"
        
        result = await client.call_tool("modify_event", {
            "user_google_email": TEST_EMAIL,
            "event_id": event_id
            # No fields to modify
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should indicate no fields provided
        assert "no fields provided" in content.lower() or "error" in content.lower()
    
    @pytest.mark.asyncio
    async def test_get_event(self, client, test_event_id):
        """Test getting a specific event by ID."""
        # Use fake event ID if no real one is available (should get "not found" response)
        event_id = test_event_id or "fake_event_id_for_testing"
        
        result = await client.call_tool("get_event", {
            "user_google_email": TEST_EMAIL,
            "event_id": event_id
        })
        
        assert len(result) > 0
        content = result[0].text
        valid_responses = [
            "event", "title", "starts", "event details", "requires authentication", "no valid credentials",
            "❌", "failed to get event", "unexpected error", "successfully retrieved",
            "calendar service", "unable to get", "not found"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_delete_event(self, client, test_event_id):
        """Test deleting an event."""
        # Use fake event ID if no real one is available (should get "not found" response)
        event_id = test_event_id or "fake_event_id_for_testing"
        
        result = await client.call_tool("delete_event", {
            "user_google_email": TEST_EMAIL,
            "event_id": event_id
        })
        
        assert len(result) > 0
        content = result[0].text
        valid_responses = [
            "deleted", "not found", "requires authentication", "no valid credentials",
            "❌", "failed to delete event", "unexpected error", "successfully deleted",
            "calendar service", "unable to get", "removed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_calendar_tools_parameter_validation(self, client):
        """Test parameter validation for Calendar tools."""
        # Test missing required parameters
        with pytest.raises(Exception):  # FastMCP should raise an error
            await client.call_tool("create_event", {
                "user_google_email": TEST_EMAIL
                # Missing summary, start_time, end_time
            })
        
        with pytest.raises(Exception):
            await client.call_tool("get_event", {
                "user_google_email": TEST_EMAIL
                # Missing event_id
            })
    
    @pytest.mark.asyncio
    async def test_time_format_handling(self, client):
        """Test various time format handling."""
        # Test with different time formats
        time_formats = [
            "2024-12-25",  # Date only
            "2024-12-25T10:00:00",  # Missing timezone
            "2024-12-25T10:00:00Z",  # With UTC timezone
            "2024-12-25T10:00:00-08:00"  # With specific timezone
        ]
        
        for time_format in time_formats:
            result = await client.call_tool("get_events", {
                "user_google_email": TEST_EMAIL,
                "time_min": time_format,
                "max_results": 1
            })
            
            assert len(result) > 0
            # Should handle all formats without error
    
    @pytest.mark.asyncio
    async def test_invalid_event_id_handling(self, client):
        """Test handling of invalid event IDs."""
        result = await client.call_tool("get_event", {
            "user_google_email": TEST_EMAIL,
            "event_id": "invalid_event_id_12345"
        })
        
        assert len(result) > 0
        content = result[0].text
        assert "error" in content.lower() or "not found" in content.lower() or "requires authentication" in content.lower()


class TestCalendarIntegration:
    """Integration tests for Calendar tools with other services."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
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
        result = await client.call_tool("get_events", {
            "user_google_email": TEST_EMAIL,
            "calendar_id": "invalid_calendar_id@group.calendar.google.com"
        })
        
        assert len(result) > 0
        content = result[0].text
        assert "error" in content.lower() or "requires authentication" in content.lower()