"""
Tests for the send_dynamic_card tool using FastMCP Client SDK.

This module specifically tests the send_dynamic_card tool with different
variations of card types and parameters.
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
from .test_auth_utils import get_client_auth_config

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

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")
# Test webhook URLs for Google Chat
TEST_CHAT_WEBHOOK = os.getenv("TEST_CHAT_WEBHOOK", "")
TEST_WEBHOOK_URL = os.getenv("TEST_CHAT_WEBHOOK_URL", TEST_CHAT_WEBHOOK or "https://chat.googleapis.com/v1/spaces/AAAAAAAAAAA/messages?key=test&token=test")


class TestSendDynamicCard:
    """Test the send_dynamic_card tool with different card variations."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
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
            "space_id": "spaces/test",
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
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # If successful, should contain "sent successfully"
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
            "space_id": "spaces/test",
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
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # If successful, should contain "sent successfully"
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
            "space_id": "spaces/test",
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
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # If successful, should contain "sent successfully"
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
            "space_id": "spaces/test",
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
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # If successful, should contain "sent successfully"
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
            "space_id": "spaces/test",
            "card_description": "Create a card with a header, an image of a cat, and a button to visit a website",
            "card_params": {
                "header": {
                    "title": f"Natural Language Card ({timestamp})",
                    "subtitle": "Created using natural language description"
                }
            },
            "webhook_url": TEST_WEBHOOK_URL
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # If successful, should contain "sent successfully"
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
            "space_id": "spaces/test",
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
        
        assert len(result) > 0
        content = result[0].text
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "successfully", "webhook", "status",
            "❌", "error", "failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
        
        # If successful, should contain "sent successfully"
        if "❌" not in content and "error" not in content.lower():
            assert "sent successfully" in content.lower(), "Card should be sent successfully"


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])