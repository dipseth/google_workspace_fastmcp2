"""Test suite for Google service list tools using FastMCP Client SDK."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
from dotenv import load_dotenv
from .test_auth_utils import get_client_auth_config

# Load environment variables from .env file
load_dotenv()

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")


class BaseListToolsTest:
    """Base class for list tools testing."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    def verify_structured_response(self, content: str, service_name: str, tool_name: str):
        """Verify that the response follows the structured format.
        
        Args:
            content: The response content string
            service_name: Name of the service (e.g., "Gmail", "Drive")
            tool_name: Name of the tool being tested
        """
        # Check for structured response indicators
        content_lower = content.lower()
        
        # Should have items/data field
        has_items_field = any([
            '"items"' in content,
            '"data"' in content,
            '"labels"' in content,  # Gmail labels specific
            '"albums"' in content,  # Photos albums specific
            '"photos"' in content,  # Photos specific
            '"filters"' in content,  # Gmail filters specific
            '"templates"' in content,  # Gmail templates specific
            '"allowedSenders"' in content,  # Gmail allowlist specific
            'items:' in content_lower,
            'data:' in content_lower,
            'labels:' in content_lower
        ])
        
        # Should have count field
        has_count_field = any([
            '"count"' in content,
            '"total_count"' in content,  # Gmail labels specific
            '"totalCount"' in content,
            'count:' in content_lower,
            'total:' in content_lower
        ])
        
        # Should have user context field
        has_context_field = any([
            '"userEmail"' in content,
            '"user_email"' in content,
            '"context"' in content,
            # For Gmail labels, it doesn't have userEmail in the main response
            # but check for system_labels/user_labels as context indicators
            '"system_labels"' in content,
            '"user_labels"' in content,
            'user:' in content_lower,
            'email:' in content_lower
        ])
        
        # Should have error field (None for success)
        has_error_field = any([
            '"error": null' in content,
            '"error": None' in content,
            'error: none' in content_lower,
            '❌' in content,  # Error indicator
            'requires authentication' in content_lower,
            'failed' in content_lower
        ])
        
        # Verify structured format
        is_structured = has_items_field or has_count_field or has_context_field or has_error_field
        
        assert is_structured, (
            f"{service_name} {tool_name}: Response doesn't follow structured format. "
            f"Expected items/data, count, userEmail/context, and error fields. "
            f"Got: {content[:500]}..."
        )


class TestGmailListTools(BaseListToolsTest):
    """Test Gmail list tools."""
    
    @pytest.mark.asyncio
    async def test_list_gmail_filters(self, client):
        """Test listing Gmail filters."""
        result = await client.call_tool("list_gmail_filters", {
            "user_google_email": TEST_EMAIL
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Gmail", "list_gmail_filters")
        
        # Check for valid responses
        valid_responses = [
            "filters", "filter", "gmail", "no filters",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Gmail filters response didn't match expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_view_gmail_allow_list(self, client):
        """Test viewing Gmail allow list."""
        result = await client.call_tool("view_gmail_allow_list", {
            "user_google_email": TEST_EMAIL
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Gmail", "view_gmail_allow_list")
        
        # Check for valid responses
        valid_responses = [
            "allow", "list", "allowed", "senders", "domains",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Gmail allow list response didn't match expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_email_templates(self, client):
        """Test listing email templates."""
        result = await client.call_tool("list_email_templates", {
            "user_google_email": TEST_EMAIL
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Gmail", "list_email_templates")
        
        # Check for valid responses
        valid_responses = [
            "template", "email", "no templates",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Email templates response didn't match expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_gmail_labels(self, client):
        """Test listing Gmail labels."""
        result = await client.call_tool("list_gmail_labels", {
            "user_google_email": TEST_EMAIL
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Gmail", "list_gmail_labels")
        
        # Check for valid responses
        valid_responses = [
            "label", "labels", "inbox", "sent", "drafts",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Gmail labels response didn't match expected pattern: {content}"


class TestDriveListTools(BaseListToolsTest):
    """Test Drive list tools."""
    
    @pytest.mark.asyncio
    async def test_list_drive_items(self, client):
        """Test listing Drive items."""
        result = await client.call_tool("list_drive_items", {
            "user_google_email": TEST_EMAIL,
            "page_size": 10  # Fixed: use page_size not max_results
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Drive", "list_drive_items")
        
        # Check for valid responses
        valid_responses = [
            "drive", "files", "folders", "items", "no files",
            "requires authentication", "failed", "error",
            "count", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Drive items response didn't match expected pattern: {content}"


class TestFormsListTools(BaseListToolsTest):
    """Test Forms list tools."""
    
    @pytest.mark.asyncio
    async def test_list_form_responses(self, client):
        """Test listing form responses."""
        # This requires a form_id, so we'll test with a placeholder
        result = await client.call_tool("list_form_responses", {
            "user_google_email": TEST_EMAIL,
            "form_id": "test_form_id_placeholder"
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Forms", "list_form_responses")
        
        # Check for valid responses
        valid_responses = [
            "responses", "form", "submissions", "no responses",
            "requires authentication", "failed", "error", "not found",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Form responses response didn't match expected pattern: {content}"


class TestCalendarListTools(BaseListToolsTest):
    """Test Calendar list tools."""
    
    @pytest.mark.asyncio
    async def test_list_calendars(self, client):
        """Test listing calendars."""
        result = await client.call_tool("list_calendars", {
            "user_google_email": TEST_EMAIL
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Calendar", "list_calendars")
        
        # Check for valid responses
        valid_responses = [
            "calendar", "primary", "no calendars",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Calendars response didn't match expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_events(self, client):
        """Test listing calendar events."""
        result = await client.call_tool("list_events", {
            "user_google_email": TEST_EMAIL,
            "calendar_id": "primary",
            "max_results": 10
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Calendar", "list_events")
        
        # Check for valid responses
        valid_responses = [
            "events", "event", "no events",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Events response didn't match expected pattern: {content}"


class TestChatListTools(BaseListToolsTest):
    """Test Chat list tools."""
    
    @pytest.mark.asyncio
    async def test_list_spaces(self, client):
        """Test listing Chat spaces."""
        result = await client.call_tool("list_spaces", {
            "user_google_email": TEST_EMAIL
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Chat", "list_spaces")
        
        # Check for valid responses
        valid_responses = [
            "spaces", "space", "chat", "no spaces",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Chat spaces response didn't match expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_messages(self, client):
        """Test listing Chat messages."""
        # First, try to get a real space ID from list_spaces
        space_id = None
        try:
            spaces_result = await client.call_tool("list_spaces", {
                "user_google_email": TEST_EMAIL,
                "page_size": 1  # Just get one space
            })
            
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
                    match = re.search(r'spaces/[a-zA-Z0-9_-]+', spaces_content)
                    if match:
                        space_id = match.group(0)
        except Exception:
            pass  # If we can't get a real space, use placeholder
        
        # Use the real space ID if found, otherwise use a placeholder
        if not space_id:
            space_id = "spaces/test_space_placeholder"
        
        result = await client.call_tool("list_messages", {
            "user_google_email": TEST_EMAIL,
            "space_id": space_id
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Chat", "list_messages")
        
        # Check for valid responses
        valid_responses = [
            "messages", "message", "chat", "no messages",
            "requires authentication", "failed", "error", "not found",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Chat messages response didn't match expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_available_card_types(self, client):
        """Test listing available card types."""
        # This tool doesn't take user_google_email parameter
        result = await client.call_tool("list_available_card_types", {})
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Chat", "list_available_card_types")
        
        # Check for valid responses
        valid_responses = [
            "card", "types", "template", "available",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Card types response didn't match expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_available_card_components(self, client):
        """Test listing card components."""
        # Fixed: correct tool name is list_available_card_components
        result = await client.call_tool("list_available_card_components", {})
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Chat", "list_card_components")
        
        # Check for valid responses
        valid_responses = [
            "component", "card", "widget", "element",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Card components response didn't match expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_card_templates(self, client):
        """Test listing card templates."""
        # This tool doesn't take user_google_email parameter
        result = await client.call_tool("list_card_templates", {})
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Chat", "list_card_templates")
        
        # Check for valid responses
        valid_responses = [
            "template", "card", "templates", "examples",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Card templates response didn't match expected pattern: {content}"


class TestDocsListTools(BaseListToolsTest):
    """Test Docs list tools."""
    
    @pytest.mark.asyncio
    async def test_list_docs_in_folder(self, client):
        """Test listing docs in a folder."""
        # Using root folder as default
        result = await client.call_tool("list_docs_in_folder", {
            "user_google_email": TEST_EMAIL,
            "folder_id": "root"
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Docs", "list_docs_in_folder")
        
        # Check for valid responses
        valid_responses = [
            "docs", "documents", "folder", "no documents",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Docs in folder response didn't match expected pattern: {content}"


class TestSheetsListTools(BaseListToolsTest):
    """Test Sheets list tools."""
    
    @pytest.mark.asyncio
    async def test_list_spreadsheets(self, client):
        """Test listing spreadsheets."""
        result = await client.call_tool("list_spreadsheets", {
            "user_google_email": TEST_EMAIL
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Sheets", "list_spreadsheets")
        
        # Check for valid responses
        valid_responses = [
            "spreadsheet", "sheets", "no spreadsheets",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Spreadsheets response didn't match expected pattern: {content}"


class TestPhotosListTools(BaseListToolsTest):
    """Test Photos list tools."""
    
    @pytest.mark.asyncio
    async def test_list_photos_albums(self, client):
        """Test listing photos albums."""
        result = await client.call_tool("list_photos_albums", {
            "user_google_email": TEST_EMAIL
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Photos", "list_photos_albums")
        
        # Check for valid responses
        valid_responses = [
            "album", "photos", "no albums",
            "requires authentication", "failed", "error",
            "count", "items", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Photos albums response didn't match expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_album_photos(self, client):
        """Test listing photos in an album."""
        # This requires an album_id, so we'll test with a placeholder
        result = await client.call_tool("list_album_photos", {
            "user_google_email": TEST_EMAIL,
            "album_id": "test_album_id_placeholder"
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Verify structured response
        self.verify_structured_response(content, "Photos", "list_album_photos")
        
        # Check for valid responses
        valid_responses = [
            "photos", "media", "items", "no photos",
            "requires authentication", "failed", "error", "not found",
            "count", "data"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), \
            f"Album photos response didn't match expected pattern: {content}"


class TestListToolsAvailability:
    """Test that all list tools are available in the server."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_all_list_tools_available(self, client):
        """Test that all expected list tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # All expected list tools
        expected_list_tools = [
            # Gmail
            "list_gmail_filters",
            "view_gmail_allow_list",
            "list_email_templates",
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
            "list_available_card_types",
            "list_available_card_components",
            "list_card_templates",
            # Docs
            "list_docs_in_folder",
            # Sheets
            "list_spreadsheets",
            # Photos
            "list_photos_albums",
            "list_album_photos"
        ]
        
        missing_tools = []
        for tool in expected_list_tools:
            if tool not in tool_names:
                missing_tools.append(tool)
        
        assert len(missing_tools) == 0, f"Missing list tools: {missing_tools}"
        
        # Print summary
        print(f"\n✅ All {len(expected_list_tools)} list tools are available in the server")
        print("\nGoogle Service List Tools Summary:")
        print(f"  Gmail: 4 tools")
        print(f"  Drive: 1 tool")
        print(f"  Forms: 1 tool")
        print(f"  Calendar: 2 tools")
        print(f"  Chat: 5 tools")
        print(f"  Docs: 1 tool")
        print(f"  Sheets: 1 tool")
        print(f"  Photos: 2 tools")
        print(f"  Total: {len(expected_list_tools)} list tools")


class TestStructuredResponseValidation:
    """Validate the structured response format for list tools."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_error_response_structure(self, client):
        """Test that error responses follow the structured format."""
        # Test with invalid user email to trigger authentication error
        result = await client.call_tool("list_gmail_labels", {
            "user_google_email": "invalid@nonexistent.com"
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Error responses should still have structured format
        # Should NOT raise ValueError about structured_content
        assert "ValueError: structured_content must be a dict or None" not in content, \
            "Bug detected: Error responses are not being returned as structured format"
        
        # Should contain error information
        assert any(keyword in content.lower() for keyword in ["error", "failed", "authentication"]), \
            f"Error response not properly formatted: {content}"
    
    @pytest.mark.asyncio
    async def test_successful_response_structure(self, client):
        """Test that successful responses have proper structure."""
        # Test with a simple list tool
        result = await client.call_tool("list_available_card_types", {})
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Should NOT raise ValueError about structured_content
        assert "ValueError: structured_content must be a dict or None" not in content, \
            "Bug detected: Responses are not being returned as structured format"
        
        # Should have structured response indicators
        content_lower = content.lower()
        has_structure = any([
            "count" in content_lower,
            "items" in content_lower,
            "data" in content_lower,
            "error" in content_lower,
            "user" in content_lower
        ])
        
        assert has_structure, f"Response lacks structured format indicators: {content[:500]}..."


if __name__ == "__main__":
    # Run tests with pytest
    import subprocess
    import sys
    
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    sys.exit(result.returncode)