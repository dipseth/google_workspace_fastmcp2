"""Reminders on events and notification settings on calendars."""

from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client, FastMCP
from pydantic import ValidationError

from gcalendar import calendar_tools
from gcalendar.calendar_types import EventData, EventReminder, reminders_body

EMAIL = "user@example.com"


def test_default_clears_overrides():
    # A patch that only flips useDefault would leave old overrides behind,
    # and the API rejects defaults combined with overrides.
    assert reminders_body("default") == {"useDefault": True, "overrides": []}


def test_empty_list_means_no_reminders():
    assert reminders_body([]) == {"useDefault": False, "overrides": []}


def test_overrides_are_passed_through():
    body = reminders_body(
        [
            EventReminder(method="popup", minutes=10),
            EventReminder(method="email", minutes=1440),
        ]
    )
    assert body == {
        "useDefault": False,
        "overrides": [
            {"method": "popup", "minutes": 10},
            {"method": "email", "minutes": 1440},
        ],
    }


@pytest.mark.parametrize(
    "reminders",
    [
        [{"method": "sms", "minutes": 10}],
        [{"method": "popup", "minutes": -1}],
        [{"method": "popup", "minutes": 40321}],
        [{"method": "popup", "minutes": 1}] * 6,
        "none",
    ],
)
def test_invalid_reminders_are_rejected(reminders):
    with pytest.raises(ValidationError):
        EventData(
            summary="x",
            start_time="2030-01-01T10:00:00Z",
            duration="30m",
            reminders=reminders,
        )


@pytest.fixture
def service():
    """A Calendar service whose calls echo the request body back."""
    svc = MagicMock()

    def echo(**kwargs):
        request = MagicMock()
        request.execute.return_value = {
            "id": kwargs.get("eventId") or kwargs.get("calendarId") or "new-id",
            "summary": "Echo",
            "htmlLink": "https://example.com/e",
            **kwargs.get("body", {}),
        }
        return request

    svc.events.return_value.patch.side_effect = echo
    svc.events.return_value.insert.side_effect = echo
    svc.calendarList.return_value.patch.side_effect = echo
    svc.calendars.return_value.get.return_value.execute.return_value = {
        "id": "user@example.com"
    }
    return svc


@pytest.fixture
async def client(service):
    mcp = FastMCP("calendar-test")
    calendar_tools.setup_calendar_tools(mcp)

    async def fake_service(_email):
        return service

    with patch.object(
        calendar_tools, "_get_calendar_service_with_fallback", fake_service
    ):
        async with Client(mcp) as c:
            yield c


async def test_modify_event_sets_reminders(client, service):
    result = await client.call_tool(
        "modify_event",
        {
            "event_id": "evt1",
            "user_google_email": EMAIL,
            "reminders": [{"method": "popup", "minutes": 15}],
        },
    )
    assert result.structured_content["success"] is True
    assert result.structured_content["fieldsModified"] == ["reminders"]
    assert service.events.return_value.patch.call_args.kwargs["body"] == {
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 15}],
        }
    }


async def test_modify_event_resets_to_calendar_default(client, service):
    await client.call_tool(
        "modify_event",
        {"event_id": "evt1", "user_google_email": EMAIL, "reminders": "default"},
    )
    assert service.events.return_value.patch.call_args.kwargs["body"] == {
        "reminders": {"useDefault": True, "overrides": []}
    }


async def test_create_event_without_reminders_leaves_them_to_the_calendar(
    client, service
):
    await client.call_tool(
        "create_event",
        {
            "user_google_email": EMAIL,
            "summary": "Plain",
            "start_time": "2030-01-01T10:00:00Z",
            "end_time": "2030-01-01T11:00:00Z",
        },
    )
    assert (
        "reminders" not in service.events.return_value.insert.call_args.kwargs["body"]
    )


async def test_create_event_with_reminders(client, service):
    await client.call_tool(
        "create_event",
        {
            "user_google_email": EMAIL,
            "summary": "Quiet",
            "start_time": "2030-01-01T10:00:00Z",
            "end_time": "2030-01-01T11:00:00Z",
            "reminders": [],
        },
    )
    body = service.events.return_value.insert.call_args.kwargs["body"]
    assert body["reminders"] == {"useDefault": False, "overrides": []}


async def test_modify_calendar_changes_only_what_is_passed(client, service):
    result = await client.call_tool(
        "modify_calendar",
        {
            "user_google_email": EMAIL,
            "default_reminders": [{"method": "popup", "minutes": 30}],
        },
    )
    # calendarList.patch rejects the 'primary' alias, so the real id is sent
    assert service.calendarList.return_value.patch.call_args.kwargs == {
        "calendarId": "user@example.com",
        "body": {"defaultReminders": [{"method": "popup", "minutes": 30}]},
    }
    assert result.structured_content["fieldsModified"] == ["default_reminders"]
    assert result.structured_content["defaultReminders"] == [
        {"method": "popup", "minutes": 30}
    ]


async def test_modify_calendar_notifications(client, service):
    result = await client.call_tool(
        "modify_calendar",
        {
            "user_google_email": EMAIL,
            "calendar_id": "team@group.calendar.google.com",
            "notifications": ["eventCancellation", "agenda", "agenda"],
        },
    )
    assert service.calendarList.return_value.patch.call_args.kwargs["body"] == {
        "notificationSettings": {
            "notifications": [
                {"type": "eventCancellation", "method": "email"},
                {"type": "agenda", "method": "email"},
            ]
        }
    }
    assert result.structured_content["notifications"] == ["eventCancellation", "agenda"]


async def test_modify_calendar_can_turn_everything_off(client, service):
    await client.call_tool(
        "modify_calendar",
        {"user_google_email": EMAIL, "default_reminders": [], "notifications": []},
    )
    assert service.calendarList.return_value.patch.call_args.kwargs["body"] == {
        "defaultReminders": [],
        "notificationSettings": {"notifications": []},
    }


async def test_modify_calendar_with_nothing_to_change(client, service):
    result = await client.call_tool("modify_calendar", {"user_google_email": EMAIL})
    assert result.structured_content["success"] is False
    service.calendarList.return_value.patch.assert_not_called()
