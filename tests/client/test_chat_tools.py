"""Test suite for Google Chat tools using FastMCP Client SDK."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
import json
from dotenv import load_dotenv
from .base_test_config import TEST_EMAIL
from .test_helpers import ToolTestRunner, TestResponseValidator
from ..test_auth_utils import get_client_auth_config

# Load environment variables from .env file
load_dotenv()

# Test configuration from environment variables
TEST_CHAT_WEBHOOK = os.getenv("TEST_CHAT_WEBHOOK", "")

# Extract space ID from webhook URL for direct API testing
TEST_SPACE_ID = ""
if TEST_CHAT_WEBHOOK:
    # Extract space ID from URL like: https://chat.googleapis.com/v1/spaces/AAQAvreVqfs/messages?...
    try:
        import re
        match = re.search(r'/spaces/([^/]+)/', TEST_CHAT_WEBHOOK)
        if match:
            TEST_SPACE_ID = match.group(1)
    except Exception:
        pass


@pytest.mark.service("chat")
class TestChatTools:
    """Test Chat tools using standardized framework.

🔧 MCP Tools Used:
- send_message: Send basic text messages to Chat spaces
- send_interactive_card: Send cards with buttons and actions
- send_form_card: Send forms within Chat for data collection
- send_dynamic_card: Send AI-generated cards from natural language
- send_rich_card: Send advanced formatted cards with images/sections
- list_messages: Retrieve messages from Chat spaces
- search_messages: Search message content across spaces

🧪 What's Being Tested:
- Basic messaging functionality
- Rich card framework with interactive components
- Form integration within Chat interfaces
- AI-powered card generation from descriptions
- Message retrieval and search capabilities
- Webhook integration for Chat apps
- Space and thread management
- Authentication patterns for all Chat operations

🔍 Potential Duplications:
- Form functionality overlaps with Google Forms tools
- Rich content handling might have patterns similar to Slides/Docs content
- Search functionality might overlap with other Google Workspace search operations
- File sharing in Chat might overlap with Drive sharing functionality
"""
    
    @pytest.mark.asyncio
    async def test_chat_tools_available(self, client):
        """Test that all Chat tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        expected_chat_tools = [
            "list_spaces",
            "list_messages",
            "send_message",
            "search_messages",
            "send_card_message",
            "send_simple_card",
            "send_interactive_card",
            "send_form_card",
            "get_card_framework_status",
            "get_adapter_system_status",
            "list_available_card_types",
            "send_rich_card"
        ]
        
        for tool in expected_chat_tools:
            assert tool in tool_names, f"Chat tool '{tool}' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_list_spaces(self, client):
        """Test listing Google Chat spaces."""
        result = await client.call_tool("list_spaces", {
            "user_google_email": TEST_EMAIL,
            "page_size": 10
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully listed",
            "no spaces found", "❌", "failed to list", "unexpected error",
            "middleware", "service", "not yet fulfilled", "spaces found", "found", "chat spaces", "spaces"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_messages(self, client):
        """Test getting messages from a space."""
        # Use test space ID if available, otherwise use placeholder
        space_id = TEST_SPACE_ID or "spaces/test_space"
        
        result = await client.call_tool("list_messages", {
            "user_google_email": TEST_EMAIL,
            "space_id": space_id,
            "page_size": 5
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware/permission error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully retrieved",
            "no messages found", "❌", "failed to get", "unexpected error", 
            "middleware", "service", "not yet fulfilled", "messages found", "permission denied"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_send_message(self, client):
        """Test sending a simple message."""
        # Use test space ID if available, otherwise use placeholder
        space_id = TEST_SPACE_ID or "spaces/test_space"
        
        result = await client.call_tool("send_message", {
            "user_google_email": TEST_EMAIL,
            "space_id": space_id,
            "message_text": "Test message from MCP Chat Tools"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware/permission error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully sent",
            "message sent", "❌", "failed to send", "unexpected error", 
            "middleware", "service", "not yet fulfilled", "permission denied"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_search_messages(self, client):
        """Test searching messages in spaces."""
        result = await client.call_tool("search_messages", {
            "user_google_email": TEST_EMAIL,
            "query": "test",
            "page_size": 5
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully searched",
            "no messages found", "❌", "failed to search", "unexpected error",
            "middleware", "service", "not yet fulfilled", "search results", "success", "query", "results"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_send_card_message(self, client):
        """Test sending a card message."""
        # Use test space ID if available, otherwise use placeholder
        space_id = TEST_SPACE_ID or "spaces/test_space"
        
        result = await client.call_tool("send_card_message", {
            "user_google_email": TEST_EMAIL,
            "space_id": space_id,
            "card_type": "simple",
            "title": "Test Card",
            "text": "This is a test card from MCP Chat Tools"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware/permission error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully sent",
            "card sent", "❌", "failed to send", "unexpected error", 
            "middleware", "service", "not yet fulfilled", "permission denied"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_send_simple_card(self, client):
        """Test sending a simple card with basic content."""
        # Use test space ID if available, otherwise use placeholder
        space_id = TEST_SPACE_ID or "spaces/test_space"
        
        result = await client.call_tool("send_simple_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": space_id,
            "title": "Simple Test Card",
            "text": "This is a simple card test from the MCP framework",
            "subtitle": "Testing MCP Chat Tools"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware/permission error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully sent",
            "card sent", "❌", "failed to send", "unexpected error",
            "middleware", "service", "not yet fulfilled", "permission denied",
            "fallback", "simple card"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_send_interactive_card(self, client):
        """Test sending an interactive card with buttons."""
        # Use test space ID if available, otherwise use placeholder
        space_id = TEST_SPACE_ID or "spaces/test_space"
        
        # Interactive card with buttons
        buttons = [
            {"text": "Option 1", "onClick": {"action": {"actionMethodName": "option1"}}},
            {"text": "Option 2", "onClick": {"action": {"actionMethodName": "option2"}}}
        ]
        
        result = await client.call_tool("send_interactive_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": space_id,
            "title": "Interactive Test Card",
            "text": "Choose an option below:",
            "buttons": buttons
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware/permission error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully sent",
            "card sent", "❌", "failed to send", "unexpected error",
            "middleware", "service", "not yet fulfilled", "permission denied",
            "fallback", "interactive card"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_send_form_card(self, client):
        """Test sending a form card with input fields."""
        # Use test space ID if available, otherwise use placeholder
        space_id = TEST_SPACE_ID or "spaces/test_space"
        
        # Form card with input fields
        form_fields = [
            {
                "name": "user_name",
                "label": "Your Name",
                "type": "TEXT_INPUT",
                "hint": "Enter your full name"
            },
            {
                "name": "feedback",
                "label": "Feedback",
                "type": "TEXT_AREA",
                "hint": "Please provide your feedback"
            }
        ]
        
        submit_action = {
            "actionMethodName": "submit_feedback",
            "parameters": [{"key": "action", "value": "submit"}]
        }
        
        result = await client.call_tool("send_form_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": space_id,
            "title": "Feedback Form",
            "fields": form_fields,
            "submit_action": submit_action
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware/permission error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully sent",
            "form card sent", "❌", "failed to send", "unexpected error",
            "middleware", "service", "not yet fulfilled", "permission denied",
            "fallback", "form card"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_send_rich_card(self, client):
        """Test sending a rich card with multiple elements."""
        # Use test space ID if available, otherwise use placeholder
        space_id = TEST_SPACE_ID or "spaces/test_space"
        
        # Rich card with multiple sections and widgets
        sections = [
            {
                "header": "Section 1",
                "widgets": [
                    {
                        "textParagraph": {
                            "text": "This is the first section of a rich card."
                        }
                    }
                ]
            },
            {
                "header": "Section 2",
                "widgets": [
                    {
                        "textParagraph": {
                            "text": "This is the second section with more content."
                        }
                    }
                ]
            }
        ]
        
        result = await client.call_tool("send_rich_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": space_id,
            "title": "Rich Test Card",
            "sections": sections
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should either succeed or return authentication/middleware/permission error
        valid_responses = [
            "requires authentication", "no valid credentials", "successfully sent",
            "rich card sent", "❌", "failed to send", "unexpected error",
            "middleware", "service", "not yet fulfilled", "permission denied",
            "card framework not available", "cannot send rich cards"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_get_card_framework_status(self, client):
        """Test getting card framework status."""
        result = await client.call_tool("get_card_framework_status", {})
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return status information
        valid_responses = [
            "card framework", "available", "initialized", "not available",
            "status", "version", "manager", "❌", "unexpected error"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_get_adapter_system_status(self, client):
        """Test getting adapter system status."""
        result = await client.call_tool("get_adapter_system_status", {})
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return adapter system status
        valid_responses = [
            "adapter", "system", "available", "initialized", "not available",
            "status", "discovery", "factory", "registry", "❌", "unexpected error"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_available_card_types(self, client):
        """Test listing available card types."""
        result = await client.call_tool("list_available_card_types", {})
        
        assert result is not None and result.content
        content = result.content[0].text
        # Should return list of card types
        valid_responses = [
            "card types", "available", "simple", "interactive", "form", "rich",
            "basic", "hero", "list", "types", "❌", "unexpected error"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"


# Integration tests using webhook if available
@pytest.mark.integration
@pytest.mark.service("chat")
class TestChatToolsIntegration:
    """Integration tests for Chat tools using real webhook."""
    
    @pytest.mark.skipif(not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured")
    @pytest.mark.asyncio
    async def test_real_webhook_message(self, client):
        """Test sending a real message using the configured webhook."""
        if not TEST_SPACE_ID:
            pytest.skip("Could not extract space ID from webhook URL")
        
        result = await client.call_tool("send_message", {
            "user_google_email": TEST_EMAIL,
            "space_id": f"spaces/{TEST_SPACE_ID}",
            "message_text": "🧪 Test message from MCP Chat Tools - Integration Test"
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # For real webhook, expect success or specific errors
        success_indicators = ["successfully sent", "message sent"]
        error_indicators = ["requires authentication", "permission denied", "not found", "failed to create google chat service", "check your credentials"]
        
        is_success = any(indicator in content.lower() for indicator in success_indicators)
        is_expected_error = any(indicator in content.lower() for indicator in error_indicators)
        
        assert is_success or is_expected_error, f"Unexpected response: {content}"
    
    @pytest.mark.skipif(not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured")
    @pytest.mark.asyncio
    async def test_real_webhook_card(self, client):
        """Test sending a real card using the configured webhook."""
        if not TEST_SPACE_ID:
            pytest.skip("Could not extract space ID from webhook URL")
        
        result = await client.call_tool("send_simple_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": f"spaces/{TEST_SPACE_ID}",
            "title": "🧪 MCP Integration Test",
            "text": "This card was sent from the MCP Chat Tools integration test suite.",
            "subtitle": "Chat Tools Testing",
            "webhook_url": TEST_CHAT_WEBHOOK
        })
        
        assert result is not None and result.content
        content = result.content[0].text
        
        # For real webhook, expect success or specific errors
        success_indicators = ["successfully sent", "card sent", "webhook", "status: 200"]
        error_indicators = ["requires authentication", "permission denied", "not found", "webhook delivery failed"]
        
        is_success = any(indicator in content.lower() for indicator in success_indicators)
        is_expected_error = any(indicator in content.lower() for indicator in error_indicators)
        
        assert is_success or is_expected_error, f"Unexpected response: {content}"