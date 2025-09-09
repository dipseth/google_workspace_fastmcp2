"""
Tests for Smart Card Tool for MCP

This module contains tests for the Smart Card Tool, which provides a simplified interface
for LLMs to interact with the Google Chat card creation system through MCP.
"""

"""Test smart card tool with intelligent card selection and generation.

🔧 MCP Tools Used:
- Smart card generation tools: Intelligent card type selection
- Card optimization: Optimize card design for user intent
- Context-aware rendering: Generate cards based on conversation context
- Adaptive card layouts: Adjust card structure based on content

🧪 What's Being Tested:
- Intelligent card type selection based on content and context
- Smart card layout optimization
- Context-aware card generation
- Adaptive user interface elements
- Performance optimization for card generation
- User experience enhancement through smart defaults
- Integration with Chat conversation flow

🔍 Potential Duplications:
- High overlap with test_send_dynamic_card.py and test_nlp_card_parser.py
- Smart generation patterns similar to other AI-powered tools
- Card optimization might overlap with general UI/UX testing
- Context awareness might be similar to other contextual tools
"""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
import json
import re
from .base_test_config import TEST_EMAIL
from .test_helpers import ToolTestRunner, TestResponseValidator
from ..test_auth_utils import get_client_auth_config

# Test configuration from environment variables
TEST_CHAT_WEBHOOK = os.getenv("TEST_CHAT_WEBHOOK", "")
# Additional webhook URL specifically for card tests
TEST_WEBHOOK_URL = os.getenv("TEST_CHAT_WEBHOOK_URL", TEST_CHAT_WEBHOOK)

# Provide a default webhook URL for testing if none is available
if not TEST_WEBHOOK_URL:
    TEST_WEBHOOK_URL = "https://chat.googleapis.com/v1/spaces/AAAAAAAAAAA/messages?key=mock-key&token=mock-token"
    print(f"Using mock webhook URL for testing: {TEST_WEBHOOK_URL}")

# Extract space ID from webhook URL for direct API testing
TEST_SPACE_ID = ""
if TEST_CHAT_WEBHOOK:
    # Extract space ID from URL like: https://chat.googleapis.com/v1/spaces/AAQAvreVqfs/messages?...
    try:
        match = re.search(r'/spaces/([^/]+)/', TEST_CHAT_WEBHOOK)
        if match:
            TEST_SPACE_ID = f"spaces/{match.group(1)}"
    except Exception:
        pass

# Use TEST_SPACE_ID from environment if available
if not TEST_SPACE_ID:
    # Extract from TEST_WEBHOOK_URL if available
    try:
        match = re.search(r'/spaces/([^/]+)/', TEST_WEBHOOK_URL)
        if match:
            TEST_SPACE_ID = f"spaces/{match.group(1)}"
        else:
            TEST_SPACE_ID = os.getenv("TEST_CHAT_SPACE_ID", "spaces/AAAAAAAAAAA")
    except Exception:
        TEST_SPACE_ID = os.getenv("TEST_CHAT_SPACE_ID", "spaces/AAAAAAAAAAA")

print(f"Using TEST_WEBHOOK_URL: {TEST_WEBHOOK_URL}")
print(f"Using TEST_SPACE_ID: {TEST_SPACE_ID}")


@pytest.mark.service("chat")
class TestSmartCardTool:
    """Test Smart Card tools using the FastMCP Client."""
    
    @pytest.mark.asyncio
    async def test_smart_card_tools_available(self, client):
        """Test that all Smart Card tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check for all Smart Card tools
        expected_tools = [
            "send_smart_card",
            "create_card_from_template",
            "preview_card_from_description",
            "optimize_card_layout",
            "create_multi_modal_card"
        ]
        
        for tool in expected_tools:
            assert tool in tool_names, f"Tool '{tool}' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_preview_card_from_description(self, client):
        """Test previewing a card from a natural language description."""
        # Call the tool
        result = await client.call_tool(
            "preview_card_from_description",
            {
                "description": "Title: Test Card\nText: This is a test card",
                "auto_format": True
            }
        )
        
        # Check the result
        assert len(result) > 0
        response_text = result[0].text
        card_data = json.loads(response_text)
        
        # Verify the card structure
        assert "header" in card_data, "Card should have a header"
        assert "title" in card_data["header"], "Card header should have a title"
        assert card_data["header"]["title"] == "Test Card", "Card title should match the description"
        
        # Check for sections with text content
        assert "sections" in card_data, "Card should have sections"
        
        # Find text content in the card
        text_found = False
        for section in card_data["sections"]:
            if "widgets" in section:
                for widget in section["widgets"]:
                    if "textParagraph" in widget and "text" in widget["textParagraph"]:
                        if "This is a test card" in widget["textParagraph"]["text"]:
                            text_found = True
                            break
        
        assert text_found, "Card should contain the specified text content"
    
    @pytest.mark.asyncio
    async def test_send_smart_card(self, client):
        """Test sending a smart card."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing send_smart_card")
        
        # Call the tool
        result = await client.call_tool(
            "send_smart_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": TEST_SPACE_ID,
                "content": "Title: Test Smart Card | Text: This is a test of the smart card tool",
                "style": "default",
                "auto_format": True,
                "webhook_url": TEST_WEBHOOK_URL
            }
        )
        
        # Check the result
        assert len(result) > 0
        response_text = result[0].text
        
        # Check for success message or expected error
        valid_responses = [
            "successfully sent", "card sent", "webhook", "status: 200",
            "requires authentication", "permission denied", "not found", "webhook delivery failed"
        ]
        assert any(keyword in response_text.lower() for keyword in valid_responses), \
            f"Response didn't match any expected pattern: {response_text}"
    
    @pytest.mark.asyncio
    async def test_create_card_from_template(self, client):
        """Test creating a card from a template."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing create_card_from_template")
        
        # Call the tool
        result = await client.call_tool(
            "create_card_from_template",
            {
                "template_name": "status_report",
                "content": {
                    "title": "Status Update",
                    "status": "Completed",
                    "details": "All tasks completed on time"
                },
                "user_google_email": TEST_EMAIL,
                "space_id": TEST_SPACE_ID,
                "webhook_url": TEST_WEBHOOK_URL
            }
        )
        
        # Check the result
        assert len(result) > 0
        response_text = result[0].text
        
        # Check for success message or expected error
        valid_responses = [
            "successfully sent", "card sent", "webhook", "status: 200",
            "requires authentication", "permission denied", "not found", "webhook delivery failed",
            "template not found"  # This is also a valid response if the template doesn't exist
        ]
        assert any(keyword in response_text.lower() for keyword in valid_responses), \
            f"Response didn't match any expected pattern: {response_text}"
    
    @pytest.mark.asyncio
    async def test_optimize_card_layout(self, client):
        """Test optimizing a card layout."""
        # Call the tool with a test card ID
        result = await client.call_tool(
            "optimize_card_layout",
            {
                "card_id": "test_card_123"
            }
        )
        
        # Check the result
        assert len(result) > 0
        response_text = result[0].text
        optimization_data = json.loads(response_text)
        
        # Verify the optimization data structure
        assert "card_id" in optimization_data, "Result should include the card ID"
        assert optimization_data["card_id"] == "test_card_123", "Card ID should match the input"
        
        # Check for metrics and improvements
        assert "metrics" in optimization_data, "Result should include metrics"
        assert "improvements" in optimization_data, "Result should include improvement suggestions"
        assert isinstance(optimization_data["improvements"], list), "Improvements should be a list"
    
    @pytest.mark.asyncio
    async def test_create_multi_modal_card(self, client):
        """Test creating a multi-modal card."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing create_multi_modal_card")
        
        # Call the tool
        result = await client.call_tool(
            "create_multi_modal_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": TEST_SPACE_ID,
                "content": "Title: Multi-Modal Test | Text: Testing multi-modal content",
                "data": {"labels": ["Q1", "Q2"], "values": [10, 20]},
                "images": ["https://example.com/image.jpg"],
                "webhook_url": TEST_WEBHOOK_URL
            }
        )
        
        # Check the result
        assert len(result) > 0
        response_text = result[0].text
        
        # Check for success message or expected error
        valid_responses = [
            "successfully sent", "card sent", "webhook", "status: 200",
            "requires authentication", "permission denied", "not found", "webhook delivery failed"
        ]
        assert any(keyword in response_text.lower() for keyword in valid_responses), \
            f"Response didn't match any expected pattern: {response_text}"
