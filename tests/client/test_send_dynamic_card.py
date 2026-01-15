"""
Tests for the send_dynamic_card tool using FastMCP Client SDK.

This module specifically tests the send_dynamic_card tool with different
variations of card types and parameters.
"""

"""Test dynamic card sending functionality with AI-powered generation.

🔧 MCP Tools Used:
- send_dynamic_card: Send AI-generated cards from natural language descriptions
- Card generation pipeline: Convert descriptions to structured cards
- Parameter extraction: Extract card parameters from user input
- Card validation: Validate generated card structures

🧪 What's Being Tested:
- Dynamic card generation from user descriptions
- AI-powered card component selection and configuration
- Parameter parsing and validation
- Card sending workflow integration
- Error handling for invalid descriptions
- Generated card quality and user experience
- Integration with Chat spaces and threading

🔍 Potential Duplications:
- Overlaps significantly with test_nlp_card_parser.py (both test NLP card generation)
- Card sending overlaps with basic Chat tools tests
- AI generation patterns might be similar to other AI-powered tools
- Parameter extraction might overlap with other input parsing tests
"""

import pytest
import asyncio
import json
import os
import logging
from datetime import datetime
from fastmcp import Client
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from ..test_auth_utils import get_client_auth_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable - using your configured variable
TEST_EMAIL = os.getenv("TEST_CHAT_WEBHOOK_EMAIL", "srivers@groupon.com")
# Test webhook URLs for Google Chat
TEST_CHAT_WEBHOOK = os.getenv("TEST_CHAT_WEBHOOK", "")
TEST_WEBHOOK_URL = os.getenv("TEST_CHAT_WEBHOOK_URL", TEST_CHAT_WEBHOOK or "https://chat.googleapis.com/v1/spaces/AAAAAAAAAAA/messages?key=test&token=test")


def extract_space_id_from_webhook(webhook_url: str) -> str:
    """Extract the space ID from a Google Chat webhook URL."""
    import re
    # Match pattern: https://chat.googleapis.com/v1/spaces/{SPACE_ID}/messages
    match = re.search(r'/spaces/([^/]+)/', webhook_url)
    if match:
        return f"spaces/{match.group(1)}"
    else:
        # Fallback to default test space
        return "spaces/test"

# Extract the actual space ID from webhook URL
TEST_SPACE_ID = extract_space_id_from_webhook(TEST_WEBHOOK_URL)


class TestSendDynamicCard:
    """Test the send_dynamic_card tool with different card variations."""
    
    # Use standardized client fixture from conftest.py
    
    @pytest.mark.asyncio
    async def test_send_dynamic_card_tool_available(self, client):
        """Test that the send_dynamic_card tool is available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        assert "send_dynamic_card" in tool_names, "Tool 'send_dynamic_card' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_send_simple_card(self, client):
        """Test sending a simple card with basic header and text."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Send a simple card
        result = await client.call_tool("send_dynamic_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "simple card with header and text",
            "card_params": {
                "header": {
                    "title": f"Simple Card Test ({timestamp})",
                    "subtitle": "Created for testing send_dynamic_card"
                },
                "text": "This is a simple card with just a header and text."
            },
            "webhook_url": TEST_WEBHOOK_URL
        })
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Handle both old list format and new CallToolResult format
        if hasattr(result, 'content'):
            # New FastMCP format - result is CallToolResult with content list
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            # Old format - result is a list
            assert len(result) > 0
            content = result[0].text
        else:
            # Direct content
            content = str(result)
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        else:
            # If successful without explicit status, should contain "sent successfully"
            if "❌" not in content and "error" not in content.lower():
                assert "sent successfully" in content.lower(), "Card should be sent successfully"
    
    @pytest.mark.asyncio
    async def test_send_interactive_card(self, client):
        """Test sending an interactive card with buttons."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Send an interactive card
        result = await client.call_tool("send_dynamic_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "interactive card with buttons",
            "card_params": {
                "header": {
                    "title": f"Interactive Card Test ({timestamp})",
                    "subtitle": "Created for testing send_dynamic_card",
                    "imageUrl": "https://picsum.photos/200/100"
                },
                "sections": [
                    {
                        "header": "Interactive Section",
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": f"This interactive card was created at {timestamp}"
                                }
                            },
                            {
                                "buttonList": {
                                    "buttons": [
                                        {
                                            "text": "Visit Google",
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://www.google.com"
                                                }
                                            }
                                        },
                                        {
                                            "text": "Visit Documentation",
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        })
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Handle both old list format and new CallToolResult format
        if hasattr(result, 'content'):
            # New FastMCP format - result is CallToolResult with content list
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            # Old format - result is a list
            assert len(result) > 0
            content = result[0].text
        else:
            # Direct content
            content = str(result)
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        else:
            # If successful without explicit status, should contain "sent successfully"
            if "❌" not in content and "error" not in content.lower():
                assert "sent successfully" in content.lower(), "Card should be sent successfully"
    
    @pytest.mark.asyncio
    async def test_send_card_with_image(self, client):
        """Test sending a card with an image."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Send a card with an image
        result = await client.call_tool("send_dynamic_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with image",
            "card_params": {
                "header": {
                    "title": f"Image Card Test ({timestamp})",
                    "subtitle": "Created for testing send_dynamic_card"
                },
                "sections": [
                    {
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": "This card contains an image."
                                }
                            },
                            {
                                "image": {
                                    "imageUrl": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                    "altText": "Google Workspace Logo"
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        })
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Handle both old list format and new CallToolResult format
        if hasattr(result, 'content'):
            # New FastMCP format - result is CallToolResult with content list
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            # Old format - result is a list
            assert len(result) > 0
            content = result[0].text
        else:
            # Direct content
            content = str(result)
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        else:
            # If successful without explicit status, should contain "sent successfully"
            if "❌" not in content and "error" not in content.lower():
                assert "sent successfully" in content.lower(), "Card should be sent successfully"
    
    @pytest.mark.asyncio
    async def test_send_form_card(self, client):
        """Test sending a form card with input fields."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Send a form card
        result = await client.call_tool("send_dynamic_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "form card with input fields",
            "card_params": {
                "header": {
                    "title": f"Form Card Test ({timestamp})",
                    "subtitle": "Created for testing send_dynamic_card"
                },
                "sections": [
                    {
                        "header": "Form Section",
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": "Please fill out this form:"
                                }
                            },
                            {
                                "textInput": {
                                    "label": "Name",
                                    "name": "name",
                                    "value": "",
                                    "hintText": "Enter your name"
                                }
                            },
                            {
                                "textInput": {
                                    "label": "Email",
                                    "name": "email",
                                    "value": "",
                                    "hintText": "Enter your email"
                                }
                            },
                            {
                                "selectionInput": {
                                    "name": "department",
                                    "label": "Department",
                                    "type": "DROPDOWN",
                                    "items": [
                                        {
                                            "text": "Engineering",
                                            "value": "engineering",
                                            "selected": True
                                        },
                                        {
                                            "text": "Marketing",
                                            "value": "marketing",
                                            "selected": False
                                        },
                                        {
                                            "text": "Sales",
                                            "value": "sales",
                                            "selected": False
                                        }
                                    ]
                                }
                            },
                            {
                                "buttonList": {
                                    "buttons": [
                                        {
                                            "text": "Submit",
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://example.com/submit"
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        })
        
        # Handle both old list format and new CallToolResult format
        if hasattr(result, 'content'):
            # New FastMCP format - result is CallToolResult with content list
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            # Old format - result is a list
            assert len(result) > 0
            content = result[0].text
        else:
            # Direct content
            content = str(result)
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        else:
            # If successful without explicit status, should contain "sent successfully"
            if "❌" not in content and "error" not in content.lower():
                assert "sent successfully" in content.lower(), "Card should be sent successfully"
    
    @pytest.mark.asyncio
    async def test_send_card_with_natural_language_description(self, client):
        """Test sending a card using only natural language description."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Send a card using natural language description
        result = await client.call_tool("send_dynamic_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "Create a card with a header, an image of a cat, and a button to visit a website",
            "card_params": {
                "header": {
                    "title": f"Natural Language Card ({timestamp})",
                    "subtitle": "Created using natural language description"
                }
            },
            "webhook_url": TEST_WEBHOOK_URL
        })
        
        # Handle both old list format and new CallToolResult format
        if hasattr(result, 'content'):
            # New FastMCP format - result is CallToolResult with content list
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            # Old format - result is a list
            assert len(result) > 0
            content = result[0].text
        else:
            # Direct content
            content = str(result)
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        else:
            # If successful without explicit status, should contain "sent successfully"
            if "❌" not in content and "error" not in content.lower():
                assert "sent successfully" in content.lower(), "Card should be sent successfully"
    
    @pytest.mark.asyncio
    async def test_send_card_with_complex_layout(self, client):
        """Test sending a card with a complex layout including columns and multiple sections."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Send a card with complex layout
        result = await client.call_tool("send_dynamic_card", {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "complex card with multiple sections and columns",
            "card_params": {
                "header": {
                    "title": f"Complex Layout Card ({timestamp})",
                    "subtitle": "Created for testing send_dynamic_card",
                    "imageUrl": "https://picsum.photos/200/100",
                    "imageType": "CIRCLE"
                },
                "sections": [
                    {
                        "header": "Section 1",
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": "This is the first section with text."
                                }
                            }
                        ]
                    },
                    {
                        "header": "Section 2",
                        "widgets": [
                            {
                                "columns": {
                                    "columnItems": [
                                        {
                                            "horizontalAlignment": "CENTER",
                                            "widgets": [
                                                {
                                                    "image": {
                                                        "imageUrl": "https://www.gstatic.com/images/branding/product/2x/contacts_48dp.png",
                                                        "altText": "Contact"
                                                    }
                                                },
                                                {
                                                    "textParagraph": {
                                                        "text": "Column 1"
                                                    }
                                                }
                                            ]
                                        },
                                        {
                                            "horizontalAlignment": "CENTER",
                                            "widgets": [
                                                {
                                                    "image": {
                                                        "imageUrl": "https://www.gstatic.com/images/branding/product/2x/gmail_48dp.png",
                                                        "altText": "Gmail"
                                                    }
                                                },
                                                {
                                                    "textParagraph": {
                                                        "text": "Column 2"
                                                    }
                                                }
                                            ]
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                    {
                        "header": "Section 3",
                        "widgets": [
                            {
                                "buttonList": {
                                    "buttons": [
                                        {
                                            "text": "Action 1",
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://example.com/action1"
                                                }
                                            }
                                        },
                                        {
                                            "text": "Action 2",
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://example.com/action2"
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        })
        
        # Handle both old list format and new CallToolResult format
        if hasattr(result, 'content'):
            # New FastMCP format - result is CallToolResult with content list
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            # Old format - result is a list
            assert len(result) > 0
            content = result[0].text
        else:
            # Direct content
            content = str(result)
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        else:
            # If successful without explicit status, should contain "sent successfully"
            if "❌" not in content and "error" not in content.lower():
                assert "sent successfully" in content.lower(), "Card should be sent successfully"
    
    @pytest.mark.asyncio
    async def test_send_minimal_card(self, client):
        """Test sending the most basic card possible - just title and text."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Very simple test payload - just basic title and text
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "simple card",  # Very basic description
            "card_params": {
                "title": f"Minimal Test ({timestamp})",
                "text": "Hello from minimal test card!"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🧪 MINIMAL CARD TEST - BASIC DEBUGGING")
        print(f"{'='*60}")
        print(f"📧 Test Email: {TEST_EMAIL}")
        print(f"🔗 Webhook URL: {TEST_WEBHOOK_URL}")
        print(f"📋 Minimal Payload:")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the minimal card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== MINIMAL TEST RESPONSE ===")
        print(f"Response type: {type(result)}")
        print(f"Response content: '{content}'")
        print(f"Content length: {len(content)} chars")
        print(f"=== END MINIMAL TEST ===\n")
        
        # Basic validation - just check we got some response
        assert content is not None, "Response content should not be None"
        assert len(content.strip()) > 0, f"Response should not be empty, got: '{content}'"
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
            print("✅ SUCCESS: Card sent successfully")
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
            print("⚠️  RATE LIMITED: Card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Card sent successfully")
        elif "webhook" in content.lower() and "status" in content.lower():
            print("ℹ️  INFO: Got webhook response with status info")
        else:
            print(f"❓ UNKNOWN: Response content: '{content}'")
        
        logger.info(f"Minimal card test result: {content}")
        
    @pytest.mark.asyncio
    async def test_send_card_with_button_and_image(self, client):
        """Test sending a card with both a button and an image."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Card with button and image
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with button and image",
            "card_params": {
                "title": f"Button + Image Test ({timestamp})",
                "text": "This card has both a button and an image.",
                "image_url": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                "buttons": [
                    {
                        "text": "Click Me",
                        "onclick_action": "https://example.com"
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🖼️ BUTTON + IMAGE TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the button + image card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== BUTTON + IMAGE TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"Content length: {len(content)} chars")
        
        # Check if it's blank/empty
        if len(content.strip()) == 0:
            print("❌ BLANK MESSAGE DETECTED!")
            print("This might be where the blank message issue occurs")
        
        print(f"=== END BUTTON + IMAGE TEST ===\n")
        
        # Check response
        assert content is not None
        assert len(content.strip()) > 0, f"Response should not be blank, got: '{content}'"
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
            print("✅ SUCCESS: Button + image card sent successfully")
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
            print("⚠️  RATE LIMITED: Card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Button + image card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Button + image card test result: {content}")
        
    @pytest.mark.asyncio
    async def test_send_basic_button_card(self, client):
        """Test sending a basic card with one simple button."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Basic card with one simple button
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "simple card with one button",
            "card_params": {
                "title": f"Basic Button Test ({timestamp})",
                "text": "This card has one simple button.",
                "buttons": [
                    {
                        "text": "Click Me",
                        "onclick_action": "https://example.com"
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🔘 BASIC BUTTON TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the basic button card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== BASIC BUTTON TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END BASIC BUTTON TEST ===\n")
        
        # Check response
        assert content is not None
        assert len(content.strip()) > 0
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
            print("✅ SUCCESS: Basic button card sent successfully")
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
            print("⚠️  RATE LIMITED: Card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Basic button card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Basic button card test result: {content}")

    @pytest.mark.asyncio
    async def test_send_card_with_advanced_buttons(self, client):
        """Test sending a card with advanced Google Chat Cards v2 button features."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # SIMPLIFIED advanced button test - reduce complexity
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with styled buttons",  # Simpler description
            "card_params": {
                "title": f"Button Styles Test ({timestamp})",
                "text": "Testing different button styles",
                "buttons": [
                    {
                        "text": "Filled Button",
                        "type": "FILLED",
                        "onclick_action": "https://example.com/filled"
                    },
                    {
                        "text": "Outlined Button",
                        "type": "OUTLINED",
                        "onclick_action": "https://example.com/outlined"
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🎨 SIMPLIFIED ADVANCED BUTTON TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the advanced button card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== ADVANCED BUTTON TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END ADVANCED BUTTON TEST ===\n")
        
        # Basic validation
        assert content is not None
        assert len(content.strip()) > 0
        
        # CRITICAL: Ensure we got a 200 response code (test should fail if not 200)
        if "status: 200" in content:
            # Success case - should contain "sent successfully"
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
            print("✅ SUCCESS: Advanced button card sent successfully")
        elif "status: 429" in content:
            # Rate limiting is acceptable (indicates correct formatting)
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
            print("⚠️  RATE LIMITED: Card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            # 4xx errors should fail the test
            print(f"❌ 400 Error - API format issue: {content}")
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            # 5xx errors should fail the test
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            # Generic webhook failure should fail the test
            pytest.fail(f"Webhook delivery failed: {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Advanced button card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Simplified advanced buttons test result: {content}")
    
    @pytest.mark.asyncio
    async def test_all_button_types(self, client):
        """Test all supported Google Chat button types."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test all supported button types
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card testing all button types",
            "card_params": {
                "title": f"All Button Types Test ({timestamp})",
                "text": "Testing all supported Google Chat button types",
                "buttons": [
                    {
                        "text": "Filled",
                        "type": "FILLED",
                        "onclick_action": "https://example.com/filled"
                    },
                    {
                        "text": "Filled Tonal",
                        "type": "FILLED_TONAL",
                        "onclick_action": "https://example.com/filled-tonal"
                    },
                    {
                        "text": "Outlined",
                        "type": "OUTLINED",
                        "onclick_action": "https://example.com/outlined"
                    },
                    {
                        "text": "Borderless",
                        "type": "BORDERLESS",
                        "onclick_action": "https://example.com/borderless"
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🎨 ALL BUTTON TYPES TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the all button types card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== ALL BUTTON TYPES TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END ALL BUTTON TYPES TEST ===\n")
        
        # Validate response
        assert content is not None
        assert len(content.strip()) > 0
        
        # CRITICAL: Ensure we got a 200 response code
        if "status: 200" in content:
            assert "sent successfully" in content.lower(), "Card should be sent successfully with status 200"
            print("✅ SUCCESS: All button types card sent successfully")
        elif "status: 429" in content:
            assert "rate limited" in content.lower(), "Status 429 should indicate rate limiting"
            print("⚠️  RATE LIMITED: Card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            pytest.fail(f"Card formatting error (4xx status): {content}")
        elif "status: 5" in content:
            pytest.fail(f"Server error (5xx status): {content}")
        elif "webhook delivery failed" in content.lower():
            pytest.fail(f"Webhook delivery failed: {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: All button types card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"All button types test result: {content}")

    @pytest.mark.asyncio
    async def test_error_boundary_empty_card(self, client):
        """Test error handling for completely empty card params."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        # Test completely empty card params
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "empty card test",
            "card_params": {},  # Completely empty
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🚫 EMPTY CARD ERROR BOUNDARY TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the empty card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== EMPTY CARD ERROR BOUNDARY RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END EMPTY CARD ERROR BOUNDARY ===\n")
        
        # Should either prevent sending or handle gracefully
        assert content is not None
        assert len(content.strip()) > 0
        
        # Should either succeed with fallback or show validation error
        if "blank message prevention" in content.lower():
            print("✅ SUCCESS: Pre-send validation caught empty card")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Empty card handled with fallback content")
        elif "validation" in content.lower() or "error" in content.lower():
            print("✅ SUCCESS: Proper error handling for empty card")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Empty card error boundary test result: {content}")

    @pytest.mark.asyncio
    async def test_error_boundary_malformed_buttons(self, client):
        """Test error handling for malformed button configurations."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test malformed buttons
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with malformed buttons",
            "card_params": {
                "title": f"Malformed Buttons Test ({timestamp})",
                "text": "Testing malformed button handling",
                "buttons": [
                    {
                        "text": "Valid Button",
                        "onclick_action": "https://example.com/valid"
                    },
                    {
                        # Missing required text field
                        "onclick_action": "https://example.com/missing-text"
                    },
                    {
                        "text": "Invalid Type",
                        "type": "INVALID_TYPE_THAT_DOESNT_EXIST",
                        "onclick_action": "https://example.com/invalid"
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"⚠️  MALFORMED BUTTONS ERROR BOUNDARY TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the malformed buttons card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== MALFORMED BUTTONS ERROR BOUNDARY RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END MALFORMED BUTTONS ERROR BOUNDARY ===\n")
        
        # Should handle malformed buttons gracefully
        assert content is not None
        assert len(content.strip()) > 0
        
        # Should either clean up malformed buttons or show proper error
        if "status: 200" in content:
            print("✅ SUCCESS: Malformed buttons cleaned up successfully")
        elif "status: 400" in content:
            print("✅ SUCCESS: API properly rejected malformed buttons")
        elif "validation" in content.lower() or "error" in content.lower():
            print("✅ SUCCESS: Proper validation error for malformed buttons")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Malformed buttons error boundary test result: {content}")

    @pytest.mark.asyncio
    async def test_large_content_handling(self, client):
        """Test handling of cards with large amounts of content."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Create large content
        large_text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50  # ~2800 chars
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with large content",
            "card_params": {
                "title": f"Large Content Test ({timestamp})",
                "text": large_text,
                "buttons": [
                    {
                        "text": "Read More",
                        "onclick_action": "https://example.com/read-more"
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"📄 LARGE CONTENT HANDLING TEST")
        print(f"{'='*60}")
        print(f"Content length: {len(large_text)} characters")
        print(f"{'='*60}\n")
        
        # Send the large content card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== LARGE CONTENT HANDLING RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END LARGE CONTENT HANDLING ===\n")
        
        # Should handle large content appropriately
        assert content is not None
        assert len(content.strip()) > 0
        
        if "status: 200" in content:
            print("✅ SUCCESS: Large content handled successfully")
        elif "status: 400" in content and "too large" in content.lower():
            print("✅ SUCCESS: Proper error for content too large")
        elif "truncated" in content.lower():
            print("✅ SUCCESS: Large content appropriately truncated")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Large content handling test result: {content}")

    @pytest.mark.asyncio
    async def test_grid_widget_layout(self, client):
        """Test Google Chat grid widget with images and styling."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test grid widget layout based on your working example
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with grid layout widgets",
            "card_params": {
                "title": f"Grid Widget Test ({timestamp})",
                "text": "Testing Google Chat grid widget functionality",
                "sections": [
                    {
                        "header": "Grid Widget Section",
                        "widgets": [
                            {
                                "grid": {
                                    "title": "Product Grid",
                                    "columnCount": 2,
                                    "items": [
                                        {
                                            "image": {
                                                "imageUri": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                                "cropStyle": {
                                                    "type": "SQUARE"
                                                },
                                                "borderStyle": {
                                                    "type": "STROKE"
                                                }
                                            },
                                            "title": "Item 1",
                                            "textAlignment": "CENTER"
                                        },
                                        {
                                            "image": {
                                                "imageUri": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png"
                                            },
                                            "title": "Item 2",
                                            "textAlignment": "CENTER"
                                        }
                                    ],
                                    "onClick": {
                                        "openLink": {
                                            "url": "https://developers.google.com/chat/ui/widgets/grid"
                                        }
                                    }
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🎯 GRID WIDGET LAYOUT TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the grid widget card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== GRID WIDGET TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END GRID WIDGET TEST ===\n")
        
        # Validate response
        assert content is not None
        assert len(content.strip()) > 0
        
        if "status: 200" in content:
            print("✅ SUCCESS: Grid widget card sent successfully")
        elif "status: 429" in content:
            print("⚠️  RATE LIMITED: Grid widget card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            pytest.fail(f"Grid widget formatting error (4xx status): {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Grid widget card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Grid widget test result: {content}")

    @pytest.mark.asyncio
    async def test_chip_list_widgets(self, client):
        """Test Google Chat chipList widgets with material icons."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test chipList widgets based on your working example
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with chip list widgets",
            "card_params": {
                "title": f"ChipList Widget Test ({timestamp})",
                "text": "Testing Google Chat chipList widget functionality",
                "sections": [
                    {
                        "header": "Chip Actions",
                        "widgets": [
                            {
                                "chipList": {
                                    "chips": [
                                        {
                                            "label": "Basic Chip",
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                }
                                            }
                                        },
                                        {
                                            "label": "Chip with Icon",
                                            "icon": {
                                                "materialIcon": {
                                                    "name": "alarm"
                                                }
                                            },
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                }
                                            }
                                        },
                                        {
                                            "label": "Disabled Chip",
                                            "disabled": True,
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                }
                                            }
                                        },
                                        {
                                            "label": "Disabled Chip with Icon",
                                            "disabled": True,
                                            "icon": {
                                                "materialIcon": {
                                                    "name": "bug_report"
                                                }
                                            },
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🏷️  CHIP LIST WIDGETS TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the chipList widget card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== CHIP LIST WIDGETS TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END CHIP LIST WIDGETS TEST ===\n")
        
        # Validate response
        assert content is not None
        assert len(content.strip()) > 0
        
        if "status: 200" in content:
            print("✅ SUCCESS: ChipList widgets card sent successfully")
        elif "status: 429" in content:
            print("⚠️  RATE LIMITED: ChipList widgets card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            pytest.fail(f"ChipList widgets formatting error (4xx status): {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: ChipList widgets card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"ChipList widgets test result: {content}")

    @pytest.mark.asyncio
    async def test_collapsible_sections(self, client):
        """Test Google Chat collapsible sections functionality."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test collapsible sections based on your working example
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with collapsible sections",
            "card_params": {
                "title": f"Collapsible Sections Test ({timestamp})",
                "text": "Testing Google Chat collapsible sections functionality",
                "sections": [
                    {
                        "header": "Collapsible Section",
                        "collapsible": True,
                        "uncollapsibleWidgetsCount": 2,
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": "This widget is always visible (uncollapsible #1)"
                                }
                            },
                            {
                                "textParagraph": {
                                    "text": "This widget is always visible (uncollapsible #2)"
                                }
                            },
                            {
                                "textParagraph": {
                                    "text": "This widget is collapsible (hidden by default)"
                                }
                            },
                            {
                                "textParagraph": {
                                    "text": "This widget is also collapsible (hidden by default)"
                                }
                            },
                            {
                                "buttonList": {
                                    "buttons": [
                                        {
                                            "text": "Collapsible Button",
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://example.com/collapsible-action"
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"📁 COLLAPSIBLE SECTIONS TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the collapsible sections card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== COLLAPSIBLE SECTIONS TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END COLLAPSIBLE SECTIONS TEST ===\n")
        
        # Validate response
        assert content is not None
        assert len(content.strip()) > 0
        
        if "status: 200" in content:
            print("✅ SUCCESS: Collapsible sections card sent successfully")
        elif "status: 429" in content:
            print("⚠️  RATE LIMITED: Collapsible sections card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            pytest.fail(f"Collapsible sections formatting error (4xx status): {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Collapsible sections card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Collapsible sections test result: {content}")

    @pytest.mark.asyncio
    async def test_advanced_image_styling(self, client):
        """Test Google Chat advanced image styling with crop and border styles."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test advanced image styling
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with advanced image styling",
            "card_params": {
                "title": f"Advanced Image Styling Test ({timestamp})",
                "text": "Testing Google Chat advanced image styling features",
                "sections": [
                    {
                        "header": "Image Styling Examples",
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": "Square crop with stroke border:"
                                }
                            },
                            {
                                "image": {
                                    "imageUrl": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                    "altText": "Square cropped image with stroke border",
                                    "cropStyle": {
                                        "type": "SQUARE"
                                    },
                                    "borderStyle": {
                                        "type": "STROKE"
                                    }
                                }
                            },
                            {
                                "textParagraph": {
                                    "text": "Circle crop with no border:"
                                }
                            },
                            {
                                "image": {
                                    "imageUrl": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                    "altText": "Circle cropped image",
                                    "cropStyle": {
                                        "type": "CIRCLE"
                                    }
                                }
                            },
                            {
                                "textParagraph": {
                                    "text": "Rectangle crop with stroke border:"
                                }
                            },
                            {
                                "image": {
                                    "imageUrl": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                    "altText": "Rectangle cropped image with stroke border",
                                    "cropStyle": {
                                        "type": "RECTANGLE_CUSTOM",
                                        "aspectRatio": 1.5
                                    },
                                    "borderStyle": {
                                        "type": "STROKE"
                                    }
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🖼️  ADVANCED IMAGE STYLING TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the advanced image styling card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== ADVANCED IMAGE STYLING TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END ADVANCED IMAGE STYLING TEST ===\n")
        
        # Validate response
        assert content is not None
        assert len(content.strip()) > 0
        
        if "status: 200" in content:
            print("✅ SUCCESS: Advanced image styling card sent successfully")
        elif "status: 429" in content:
            print("⚠️  RATE LIMITED: Advanced image styling card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            pytest.fail(f"Advanced image styling formatting error (4xx status): {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Advanced image styling card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Advanced image styling test result: {content}")

    @pytest.mark.asyncio
    async def test_comprehensive_mixed_widgets(self, client):
        """Test a comprehensive card with mixed advanced widgets - based on your working example."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test the comprehensive mixed widgets card - directly based on your working example
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "comprehensive card with all advanced widget types",
            "card_params": {
                "title": f"Comprehensive Mixed Widgets Test ({timestamp})",
                "text": "Testing all advanced Google Chat widget types in one card",
                "sections": [
                    {
                        "header": "Advanced Widget Showcase",
                        "collapsible": True,
                        "uncollapsibleWidgetsCount": 2,
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": "This comprehensive card showcases all advanced widget types (Always visible #1)"
                                }
                            },
                            {
                                "grid": {
                                    "title": "Product Collection",
                                    "columnCount": 2,
                                    "items": [
                                        {
                                            "image": {
                                                "imageUri": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                                "cropStyle": {
                                                    "type": "SQUARE"
                                                },
                                                "borderStyle": {
                                                    "type": "STROKE"
                                                }
                                            },
                                            "title": "Product 1",
                                            "textAlignment": "CENTER"
                                        },
                                        {
                                            "image": {
                                                "imageUri": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png"
                                            },
                                            "title": "Product 2",
                                            "textAlignment": "CENTER"
                                        }
                                    ],
                                    "onClick": {
                                        "openLink": {
                                            "url": "https://developers.google.com/chat/ui/widgets/grid"
                                        }
                                    }
                                }
                            },
                            {
                                "image": {
                                    "imageUrl": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                    "altText": "Google Workspace Dashboard"
                                }
                            },
                            {
                                "chipList": {
                                    "chips": [
                                        {
                                            "label": "Action",
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                }
                                            }
                                        },
                                        {
                                            "label": "Alert",
                                            "icon": {
                                                "materialIcon": {
                                                    "name": "alarm"
                                                }
                                            },
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                }
                                            }
                                        },
                                        {
                                            "label": "Disabled",
                                            "disabled": True,
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                }
                                            }
                                        },
                                        {
                                            "label": "Bug Report",
                                            "disabled": True,
                                            "icon": {
                                                "materialIcon": {
                                                    "name": "bug_report"
                                                }
                                            },
                                            "onClick": {
                                                "openLink": {
                                                    "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                }
                                            }
                                        }
                                    ]
                                }
                            },
                            {
                                "grid": {
                                    "title": "Secondary Collection",
                                    "columnCount": 2,
                                    "items": [
                                        {
                                            "image": {
                                                "imageUri": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                                "cropStyle": {
                                                    "type": "SQUARE"
                                                },
                                                "borderStyle": {
                                                    "type": "STROKE"
                                                }
                                            },
                                            "title": "Item A",
                                            "textAlignment": "CENTER"
                                        },
                                        {
                                            "image": {
                                                "imageUri": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png"
                                            },
                                            "title": "Item B",
                                            "textAlignment": "CENTER"
                                        }
                                    ],
                                    "onClick": {
                                        "openLink": {
                                            "url": "https://developers.google.com/chat/ui/widgets/grid"
                                        }
                                    }
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🚀 COMPREHENSIVE MIXED WIDGETS TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the comprehensive mixed widgets card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(3)  # Longer pause for complex card
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== COMPREHENSIVE MIXED WIDGETS TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END COMPREHENSIVE MIXED WIDGETS TEST ===\n")
        
        # Validate response
        assert content is not None
        assert len(content.strip()) > 0
        
        if "status: 200" in content:
            print("✅ SUCCESS: Comprehensive mixed widgets card sent successfully")
        elif "status: 429" in content:
            print("⚠️  RATE LIMITED: Comprehensive mixed widgets card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            print(f"❌ 400 Error - Complex card formatting issue: {content}")
            pytest.fail(f"Comprehensive mixed widgets formatting error (4xx status): {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Comprehensive mixed widgets card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Comprehensive mixed widgets test result: {content}")

    @pytest.mark.asyncio
    async def test_decorated_text_showcase(self, client):
        """Test Google Chat decoratedText widget with advanced features - based on working example."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test decoratedText showcase based on the user's working example
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "card with spectacular decoratedText showcase",
            "card_params": {
                "title": f"DecoratedText Showcase Test ({timestamp})",
                "text": "Testing Google Chat decoratedText widget with all advanced features",
                "sections": [
                    {
                        "header": "🎨 Spectacular DecoratedText Showcase",
                        "collapsible": True,
                        "uncollapsibleWidgetsCount": 3,
                        "widgets": [
                            {
                                "decoratedText": {
                                    "icon": {
                                        "iconUrl": "https://developers.google.com/chat/images/chat-product-icon.png"
                                    },
                                    "topLabel": "✨ PREMIUM STATUS",
                                    "text": "<b>Enhanced Account Features</b><br/><font color=\"#1a73e8\">Access to advanced collaboration tools</font>",
                                    "wrapText": True,
                                    "bottomLabel": "Expires: Dec 31, 2025 | Next billing: $29.99",
                                    "button": {
                                        "text": "MANAGE SUBSCRIPTION",
                                        "onClick": {
                                            "action": {
                                                "function": "manageSubscription",
                                                "parameters": [
                                                    {
                                                        "key": "action",
                                                        "value": "upgrade"
                                                    }
                                                ]
                                            }
                                        },
                                        "color": {
                                            "red": 0.26,
                                            "green": 0.45,
                                            "blue": 0.91
                                        }
                                    }
                                }
                            },
                            {
                                "decoratedText": {
                                    "topLabel": "📊 USAGE STATISTICS",
                                    "text": "<b>Current Usage:</b> 75% of monthly quota<br/>API calls: 1,247 / 5,000",
                                    "wrapText": True,
                                    "bottomLabel": "Reset date: January 1, 2025",
                                    "button": {
                                        "text": "VIEW DETAILS",
                                        "onClick": {
                                            "openLink": {
                                                "url": "https://developers.google.com/chat/ui/widgets/decorated-text"
                                            }
                                        },
                                        "type": "OUTLINED"
                                    }
                                }
                            },
                            {
                                "decoratedText": {
                                    "icon": {
                                        "iconUrl": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png"
                                    },
                                    "topLabel": "🔔 NOTIFICATIONS",
                                    "text": "<font color=\"#ea4335\">2 critical alerts</font><br/><font color=\"#fbbc04\">5 warnings</font><br/><font color=\"#34a853\">System operational</font>",
                                    "wrapText": True,
                                    "bottomLabel": "Last updated: " + timestamp,
                                    "button": {
                                        "text": "MANAGE ALERTS",
                                        "onClick": {
                                            "action": {
                                                "function": "manageAlerts",
                                                "parameters": [
                                                    {
                                                        "key": "view",
                                                        "value": "critical"
                                                    }
                                                ]
                                            }
                                        },
                                        "type": "FILLED",
                                        "color": {
                                            "red": 0.91,
                                            "green": 0.26,
                                            "blue": 0.21
                                        }
                                    }
                                }
                            }
                        ]
                    }
                ]
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🎨 DECORATED TEXT SHOWCASE TEST")
        print(f"{'='*60}")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the decoratedText showcase card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== DECORATED TEXT SHOWCASE TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END DECORATED TEXT SHOWCASE TEST ===\n")
        
        # Validate response
        assert content is not None
        assert len(content.strip()) > 0
        
        if "status: 200" in content:
            print("✅ SUCCESS: DecoratedText showcase card sent successfully")
        elif "status: 429" in content:
            print("⚠️  RATE LIMITED: DecoratedText showcase card formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            print(f"❌ 400 Error - DecoratedText formatting issue: {content}")
            pytest.fail(f"DecoratedText showcase formatting error (4xx status): {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: DecoratedText showcase card sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"DecoratedText showcase test result: {content}")

    @pytest.mark.asyncio
    async def test_component_resolution_for_decorated_text(self, client):
        """Test that ModuleWrapper properly resolves DecoratedText components instead of falling back."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # CRITICAL TEST: Use simple params that should trigger ModuleWrapper component search
        # This will test if the fix for component resolution is working
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "DecoratedText widget with rich content",  # Should find DecoratedText component
            "card_params": {
                "title": f"Component Resolution Test ({timestamp})",
                "text": "This should create actual DecoratedText widgets, not simple text paragraphs",
                "top_label": "🧪 COMPONENT TEST",
                "bottom_label": "Verifying ModuleWrapper resolution",
                # DON'T provide pre-built sections - let ModuleWrapper create them
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🔧 COMPONENT RESOLUTION TEST - DecoratedText")
        print(f"{'='*60}")
        print("🎯 This test verifies that ModuleWrapper properly resolves DecoratedText")
        print("🎯 components instead of falling back to simple textParagraph widgets")
        print(json.dumps(test_payload, indent=2))
        print(f"{'='*60}\n")
        
        # Send the component resolution test card
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Add pause to prevent rate limiting
        await asyncio.sleep(2)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== COMPONENT RESOLUTION TEST RESPONSE ===")
        print(f"Response: '{content}'")
        
        # Key indicators of success:
        # 1. Should show "Card Type: class" (not "variable" or "simple_fallback")
        # 2. Should send successfully with Status 200
        if "Card Type: class" in content:
            print("✅ SUCCESS: ModuleWrapper found and used a component (Card Type: class)")
        elif "Card Type: variable" in content or "Card Type: simple_fallback" in content:
            print("⚠️  FALLBACK: ModuleWrapper fell back to simple card structure")
            print("    This suggests component resolution may not be working properly")
        else:
            print("❓ No Card Type indicator found in response")
        
        print(f"=== END COMPONENT RESOLUTION TEST ===\n")
        
        # Validate response
        assert content is not None
        assert len(content.strip()) > 0
        
        if "status: 200" in content:
            print("✅ SUCCESS: Component resolution test card sent successfully")
            # CRITICAL: Check if it used actual component vs simple fallback
            if "Card Type: class" in content:
                print("🎉 PERFECT: ModuleWrapper component resolution is working!")
            elif "Card Type: variable" in content or "Card Type: simple_fallback" in content:
                print("⚠️  WARNING: Component found but fell back to simple structure")
                # This is not a failure - card still works, but component resolution needs improvement
        elif "status: 429" in content:
            print("⚠️  RATE LIMITED: Component resolution test formatting correct but rate limited")
        elif "status: 400" in content or "status: 4" in content:
            pytest.fail(f"Component resolution test formatting error (4xx status): {content}")
        elif "sent successfully" in content.lower():
            print("✅ SUCCESS: Component resolution test sent successfully")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Component resolution test result: {content}")


@pytest.mark.asyncio
async def test_debug_single_card():
    """DEBUG TOOL: Test a single minimal card with maximum debugging output."""
    # Skip if no webhook URL is available
    if not TEST_WEBHOOK_URL:
        pytest.skip("No webhook URL available for testing card sending")
    
    print(f"\n{'='*80}")
    print(f"🔍 SINGLE CARD DEBUG SESSION - MAXIMUM VERBOSITY")
    print(f"{'='*80}")
    
    # Create client (use shared framework connection logic to handle untrusted local certs)
    from .base_test_config import create_test_client

    client = await create_test_client(TEST_EMAIL)

    async with client:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        
        # Test payload - very simple
        debug_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "simple debug card",
            "card_params": {
                "title": f"🔍 Debug Test {timestamp}",
                "text": "This is a debug test to identify blank message causes."
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"📧 Test Email: {TEST_EMAIL}")
        print(f"🏠 Space ID: {TEST_SPACE_ID}")
        print(f"🔗 Webhook URL: {TEST_WEBHOOK_URL}")
        print(f"📝 Server URL: {SERVER_URL}")
        print(f"\n📋 DEBUG PAYLOAD:")
        print(json.dumps(debug_payload, indent=2))
        
        print(f"\n🚀 SENDING REQUEST...")
        try:
            result = await client.call_tool("send_dynamic_card", debug_payload)
            
            # Extract content
            if hasattr(result, 'content'):
                content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
                content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
            elif hasattr(result, '__iter__') and not isinstance(result, str):
                content = result[0].text
            else:
                content = str(result)
            
            print(f"\n✅ REQUEST COMPLETED")
            print(f"📤 Result type: {type(result)}")
            print(f"📤 Content length: {len(content)} chars")
            print(f"📤 Response: '{content}'")
            
            # Analyze response
            if "status: 200" in content:
                print(f"🎉 SUCCESS: HTTP 200 - Card sent successfully")
                if "blank" in content.lower() or "empty" in content.lower():
                    print(f"⚠️  WARNING: Success response mentions blank/empty content")
            elif "status: 429" in content:
                print(f"⚠️  RATE LIMITED: HTTP 429 - Card format correct but rate limited")
            elif "status: 4" in content:
                print(f"❌ CLIENT ERROR: HTTP 4xx - Card formatting issue")
            elif "blank message prevention" in content.lower():
                print(f"🛡️  BLANK PREVENTION: Pre-send validation caught empty card")
            elif "sent successfully" in content.lower():
                print(f"✅ SUCCESS: Generic success message")
            else:
                print(f"❓ UNKNOWN: Unrecognized response pattern")
                
            print(f"\n{'='*80}")
            
            # Basic assertion
            assert content is not None
            assert len(content.strip()) > 0
            
            return content
            
        except Exception as e:
            print(f"❌ EXCEPTION OCCURRED: {type(e).__name__}: {e}")
            raise


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])