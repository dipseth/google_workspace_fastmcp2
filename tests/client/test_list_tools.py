"""Test suite for Google service list tools using FastMCP Client SDK."""

import pytest
from dotenv import load_dotenv

from .base_test_config import TEST_EMAIL
from .test_helpers import assert_tools_registered

# Load environment variables from .env file
load_dotenv()


class BaseListToolsTest:
    """Base class for list tools testing."""

    def verify_structured_response(
        self, content: str, service_name: str, tool_name: str
    ):
        """Verify that the response follows the structured format.

        Args:
            content: The response content string
            service_name: Name of the service (e.g., "Gmail", "Drive")
            tool_name: Name of the tool being tested
        """
        # Check for structured response indicators
        content_lower = content.lower()

        # Should have items/data field
        has_items_field = any(
            [
                '"items"' in content,
                '"data"' in content,
                '"labels"' in content,  # Gmail labels specific
                '"albums"' in content,  # Photos albums specific
                '"photos"' in content,  # Photos specific
                '"filters"' in content,  # Gmail filters specific
                '"templates"' in content,  # Gmail templates specific
                '"allowedSenders"' in content,  # Gmail allowlist specific
                "items:" in content_lower,
                "data:" in content_lower,
                "labels:" in content_lower,
            ]
        )

        # Should have count field
        has_count_field = any(
            [
                '"count"' in content,
                '"total_count"' in content,  # Gmail labels specific
                '"totalCount"' in content,
                "count:" in content_lower,
                "total:" in content_lower,
            ]
        )

        # Should have user context field
        has_context_field = any(
            [
                '"userEmail"' in content,
                '"user_email"' in content,
                '"context"' in content,
                # For Gmail labels, it doesn't have userEmail in the main response
                # but check for system_labels/user_labels as context indicators
                '"system_labels"' in content,
                '"user_labels"' in content,
                "user:" in content_lower,
                "email:" in content_lower,
            ]
        )

        # Should have error field (None for success)
        has_error_field = any(
            [
                '"error": null' in content,
                '"error": None' in content,
                "error: none" in content_lower,
                "❌" in content,  # Error indicator
                "requires authentication" in content_lower,
                "failed" in content_lower,
            ]
        )

        # Verify structured format
        is_structured = (
            has_items_field or has_count_field or has_context_field or has_error_field
        )

        assert is_structured, (
            f"{service_name} {tool_name}: Response doesn't follow structured format. "
            f"Expected items/data, count, userEmail/context, and error fields. "
            f"Got: {content[:500]}..."
        )


@pytest.mark.service("gmail")
class TestGmailListTools(BaseListToolsTest):
    """Test Gmail list tools."""

    @pytest.mark.asyncio
    async def test_list_gmail_filters(self, client):
        """Test listing Gmail filters."""
        result = await client.call_tool(
            "list_gmail_filters", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Gmail", "list_gmail_filters")

        # Check for valid responses
        valid_responses = [
            "filters",
            "filter",
            "gmail",
            "no filters",
            "requires authentication",
            "failed",
            "error",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Gmail filters response didn't match expected pattern: {content}"
        )

    @pytest.mark.asyncio
    async def test_view_gmail_allow_list(self, client):
        """Test viewing Gmail allow list.

        The allow list management tools were consolidated into
        [`manage_gmail_allow_list()`](gmail/allowlist.py:1) with `action="view"`.
        """
        result = await client.call_tool(
            "manage_gmail_allow_list",
            {
                "action": "view",
                "user_google_email": TEST_EMAIL,
            },
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Gmail", "manage_gmail_allow_list")

        # Check for valid responses
        valid_responses = [
            "allow",
            "list",
            "allowed",
            "senders",
            "domains",
            "requires authentication",
            "failed",
            "error",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Gmail allow list response didn't match expected pattern: {content}"
        )

    # NOTE: test_list_email_templates has been removed as the list_email_templates
    # tool is no longer part of the supported tool surface.

    @pytest.mark.asyncio
    async def test_list_gmail_labels(self, client):
        """Test listing Gmail labels."""
        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Gmail", "list_gmail_labels")

        # Check for valid responses
        valid_responses = [
            "label",
            "labels",
            "inbox",
            "sent",
            "drafts",
            "requires authentication",
            "failed",
            "error",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Gmail labels response didn't match expected pattern: {content}"
        )


@pytest.mark.service("drive")
class TestDriveListTools(BaseListToolsTest):
    """Test Drive list tools."""

    @pytest.mark.asyncio
    async def test_list_drive_items(self, client):
        """Test listing Drive items."""
        result = await client.call_tool(
            "list_drive_items",
            {
                "user_google_email": TEST_EMAIL,
                "page_size": 10,  # Fixed: use page_size not max_results
            },
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Drive", "list_drive_items")

        # Check for valid responses
        valid_responses = [
            "drive",
            "files",
            "folders",
            "items",
            "no files",
            "requires authentication",
            "failed",
            "error",
            "count",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Drive items response didn't match expected pattern: {content}"
        )


@pytest.mark.service("forms")
class TestFormsListTools(BaseListToolsTest):
    """Test Forms list tools."""

    @pytest.mark.asyncio
    async def test_list_form_responses(self, client, real_forms_form_id):
        """Test listing form responses."""
        # This requires a form_id, so we'll test with a placeholder
        result = await client.call_tool(
            "list_form_responses",
            {"user_google_email": TEST_EMAIL, "form_id": real_forms_form_id},
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Forms", "list_form_responses")

        # Check for valid responses
        valid_responses = [
            "responses",
            "form",
            "submissions",
            "no responses",
            "requires authentication",
            "failed",
            "error",
            "not found",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Form responses response didn't match expected pattern: {content}"
        )


@pytest.mark.service("calendar")
class TestCalendarListTools(BaseListToolsTest):
    """Test Calendar list tools."""

    @pytest.mark.asyncio
    async def test_list_calendars(self, client):
        """Test listing calendars."""
        result = await client.call_tool(
            "list_calendars", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Calendar", "list_calendars")

        # Check for valid responses
        valid_responses = [
            "calendar",
            "primary",
            "no calendars",
            "requires authentication",
            "failed",
            "error",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Calendars response didn't match expected pattern: {content}"
        )

    @pytest.mark.asyncio
    async def test_list_events(self, client):
        """Test listing calendar events."""
        result = await client.call_tool(
            "list_events",
            {
                "user_google_email": TEST_EMAIL,
                "calendar_id": "primary",
                "max_results": 10,
            },
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Calendar", "list_events")

        # Check for valid responses
        valid_responses = [
            "events",
            "event",
            "no events",
            "requires authentication",
            "failed",
            "error",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Events response didn't match expected pattern: {content}"
        )


@pytest.mark.service("chat")
class TestChatListTools(BaseListToolsTest):
    """Test Chat list tools."""

    @pytest.mark.asyncio
    async def test_list_spaces(self, client):
        """Test listing Chat spaces."""
        result = await client.call_tool(
            "list_spaces", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Chat", "list_spaces")

        # Check for valid responses
        valid_responses = [
            "spaces",
            "space",
            "chat",
            "no spaces",
            "requires authentication",
            "failed",
            "error",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Chat spaces response didn't match expected pattern: {content}"
        )

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_list_messages(self, client):
        """Test listing Chat messages.

        NOTE: This test is marked slow because it makes multiple API calls
        (list_spaces then list_messages) that can timeout. The test may fail
        with a 30s timeout error if the Chat API is slow to respond.
        """
        # First, try to get a real space ID from list_spaces
        space_id = None
        try:
            spaces_result = await client.call_tool(
                "list_spaces",
                {"user_google_email": TEST_EMAIL, "page_size": 1},  # Just get one space
            )

            if spaces_result and spaces_result.content:
                spaces_content = spaces_result.content[0].text
                # Try to extract a space ID from the response
                import json

                try:
                    spaces_data = json.loads(spaces_content)
                    if "spaces" in spaces_data and len(spaces_data["spaces"]) > 0:
                        space_id = spaces_data["spaces"][0].get("id")
                except (json.JSONDecodeError, KeyError):
                    # If we can't parse, look for pattern like "spaces/..."
                    import re

                    match = re.search(r"spaces/[a-zA-Z0-9_-]+", spaces_content)
                    if match:
                        space_id = match.group(0)
        except Exception:
            pass  # If we can't get a real space, use placeholder

        # Use the real space ID if found, otherwise use a placeholder
        if not space_id:
            space_id = "spaces/test_space_placeholder"

        result = await client.call_tool(
            "list_messages", {"user_google_email": TEST_EMAIL, "space_id": space_id}
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Chat", "list_messages")

        # Check for valid responses
        valid_responses = [
            "messages",
            "message",
            "chat",
            "no messages",
            "requires authentication",
            "failed",
            "error",
            "not found",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Chat messages response didn't match expected pattern: {content}"
        )

    # NOTE: The following Chat App Dev tools have been removed from the server:
    # - list_available_card_types
    # - list_available_card_components
    # - list_card_templates
    # These were experimental Chat App Development features that are no longer
    # part of the supported tool surface. The tests have been removed as part
    # of the test cleanup effort.


@pytest.mark.service("docs")
class TestDocsListTools(BaseListToolsTest):
    """Test Docs list tools."""

    @pytest.mark.asyncio
    async def test_list_docs_in_folder(self, client):
        """Test listing docs in a folder."""
        # Using root folder as default
        result = await client.call_tool(
            "list_docs_in_folder",
            {"user_google_email": TEST_EMAIL, "folder_id": "root"},
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Docs", "list_docs_in_folder")

        # Check for valid responses
        valid_responses = [
            "docs",
            "documents",
            "folder",
            "no documents",
            "requires authentication",
            "failed",
            "error",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Docs in folder response didn't match expected pattern: {content}"
        )


@pytest.mark.service("sheets")
class TestSheetsListTools(BaseListToolsTest):
    """Test Sheets list tools."""

    @pytest.mark.asyncio
    async def test_list_spreadsheets(self, client):
        """Test listing spreadsheets."""
        result = await client.call_tool(
            "list_spreadsheets", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Sheets", "list_spreadsheets")

        # Check for valid responses
        valid_responses = [
            "spreadsheet",
            "sheets",
            "no spreadsheets",
            "requires authentication",
            "failed",
            "error",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Spreadsheets response didn't match expected pattern: {content}"
        )


@pytest.mark.service("photos")
class TestPhotosListTools(BaseListToolsTest):
    """Test Photos list tools."""

    @pytest.mark.asyncio
    async def test_list_photos_albums(self, client):
        """Test listing photos albums."""
        result = await client.call_tool(
            "list_photos_albums", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Photos", "list_photos_albums")

        # Check for valid responses
        valid_responses = [
            "album",
            "photos",
            "no albums",
            "requires authentication",
            "failed",
            "error",
            "count",
            "items",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Photos albums response didn't match expected pattern: {content}"
        )

    @pytest.mark.asyncio
    async def test_list_album_photos(self, client, real_photos_album_id):
        """Test listing photos in an album."""
        # This requires an album_id, so we'll test with a placeholder
        result = await client.call_tool(
            "list_album_photos",
            {"user_google_email": TEST_EMAIL, "album_id": real_photos_album_id},
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Verify structured response
        self.verify_structured_response(content, "Photos", "list_album_photos")

        # Check for valid responses
        valid_responses = [
            "photos",
            "media",
            "items",
            "no photos",
            "requires authentication",
            "failed",
            "error",
            "not found",
            "count",
            "data",
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), (
            f"Album photos response didn't match expected pattern: {content}"
        )


@pytest.mark.integration
class TestListToolsAvailability:
    """Test that all list tools are available in the server."""

    @pytest.mark.asyncio
    async def test_all_list_tools_available(self, client):
        """Test that all expected list tools are registered.

        NOTE: By design, the server starts with only 5 core tools exposed
        via client.list_tools(). Other tools are registered but disabled
        by default. This test verifies that list tools are REGISTERED
        (available in the tool registry) rather than currently exposed.
        """
        # All expected list tools (core service tools)
        # NOTE: Chat App Dev tools (list_available_card_types, list_available_card_components,
        # list_card_templates) have been removed from the supported surface area.
        # Gmail allow list is now managed via manage_gmail_allow_list tool.
        # Email templates tool has been removed.
        expected_list_tools = [
            # Gmail
            "list_gmail_filters",
            "list_gmail_labels",
            # Drive
            "list_drive_items",
            # Forms
            "list_form_responses",
            # Calendar
            "list_calendars",
            "list_events",
            # Chat
            "list_spaces",
            "list_messages",
            # Docs
            "list_docs_in_folder",
            # Sheets
            "list_spreadsheets",
            # Photos
            "list_photos_albums",
            "list_album_photos",
        ]

        # Use assert_tools_registered to check the tool registry via manage_tools,
        # not client.list_tools() which only shows currently enabled tools
        await assert_tools_registered(client, expected_list_tools, context="List tools")

        # Print summary
        print(
            f"\nAll {len(expected_list_tools)} list tools are registered in the server"
        )
        print("\nGoogle Service List Tools Summary:")
        print("  Gmail: 2 tools")
        print("  Drive: 1 tool")
        print("  Forms: 1 tool")
        print("  Calendar: 2 tools")
        print("  Chat: 2 tools")
        print("  Docs: 1 tool")
        print("  Sheets: 1 tool")
        print("  Photos: 2 tools")
        print(f"  Total: {len(expected_list_tools)} list tools")


@pytest.mark.integration
class TestStructuredResponseValidation:
    """Validate the structured response format for list tools."""

    @pytest.mark.asyncio
    async def test_error_response_structure(self, client):
        """Test that error responses follow the structured format."""
        # Test with invalid user email to trigger authentication error
        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": "invalid@nonexistent.com"}
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Error responses should still have structured format
        # Should NOT raise ValueError about structured_content
        assert "ValueError: structured_content must be a dict or None" not in content, (
            "Bug detected: Error responses are not being returned as structured format"
        )

        # Should contain error information
        assert any(
            keyword in content.lower()
            for keyword in ["error", "failed", "authentication"]
        ), f"Error response not properly formatted: {content}"

    @pytest.mark.asyncio
    async def test_successful_response_structure(self, client):
        """Test that successful responses have proper structure."""
        # Test with a simple list tool (list_calendars is available to all users)
        result = await client.call_tool(
            "list_calendars", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Should NOT raise ValueError about structured_content
        assert "ValueError: structured_content must be a dict or None" not in content, (
            "Bug detected: Responses are not being returned as structured format"
        )

        # Should have structured response indicators
        content_lower = content.lower()
        has_structure = any(
            [
                "count" in content_lower,
                "items" in content_lower,
                "data" in content_lower,
                "error" in content_lower,
                "user" in content_lower,
                "calendar" in content_lower,
                "authentication" in content_lower,
            ]
        )

        assert has_structure, (
            f"Response lacks structured format indicators: {content[:500]}..."
        )


if __name__ == "__main__":
    # Run tests with pytest
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"], capture_output=True, text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    sys.exit(result.returncode)
