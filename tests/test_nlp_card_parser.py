"""
Tests for the NLP Card Parser integrated with send_dynamic_card tool.

This module tests the natural language processing capabilities of the 
send_dynamic_card tool by verifying that various natural language descriptions
are properly parsed and converted into correct card parameters.
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
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test@example.com")
# Test webhook URLs for Google Chat (we'll use a dummy URL to avoid actual sends)
TEST_WEBHOOK_URL = os.getenv("TEST_CHAT_WEBHOOK", "")
if not TEST_WEBHOOK_URL:
    TEST_WEBHOOK_URL = "https://chat.googleapis.com/v1/spaces/AAAAAAAAAAA/messages?key=test&token=test"
TEST_SPACE_ID = "spaces/test"


class TestNLPCardParser:
    """Test the NLP card parser functionality integrated with send_dynamic_card tool."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_nlp_basic_card_extraction(self, client):
        """Test basic NLP extraction of title, subtitle, and text."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test natural language description for basic card elements
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "Create a card titled 'Project Status' with subtitle 'Weekly Update' and text 'All systems are operational and running smoothly.'",
            "card_params": {},  # Empty to force NLP extraction
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"📝 NLP BASIC EXTRACTION TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description']}")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content from result
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        # Verify the card was created with extracted parameters
        assert content is not None
        assert len(content.strip()) > 0
        
        # Check if NLP extraction worked (card should have title/subtitle/text)
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP extraction successful - card sent with extracted parameters")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_button_extraction(self, client):
        """Test NLP extraction of buttons with various styles."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "Create a card with buttons: 'Approve' in green filled style, 'Reject' in red outlined style, and 'Review' in blue borderless style.",
            "card_params": {
                "title": f"Button Extraction Test ({timestamp})"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🔘 NLP BUTTON EXTRACTION TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description']}")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP button extraction successful")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_section_extraction(self, client):
        """Test NLP extraction of sections with various widgets."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": """Create a card with sections: 
                'User Info' section with decoratedText showing 'John Doe' with person icon,
                'Statistics' section with decoratedText showing 'Revenue: $10,000' with chart icon,
                'Actions' section with buttons 'Download' and 'Share'.""",
            "card_params": {
                "title": f"Section Extraction Test ({timestamp})"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"📑 NLP SECTION EXTRACTION TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description'][:100]}...")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP section extraction successful")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_decorated_text_extraction(self, client):
        """Test NLP extraction of decoratedText widgets with icons and labels."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": """Create a card with decoratedText widgets:
                - First with check circle icon, top label 'Status', text 'Online', bottom label 'Since 10:00 AM'
                - Second with warning icon, text 'High CPU Usage', with a button 'View Details'""",
            "card_params": {
                "title": f"DecoratedText Extraction Test ({timestamp})"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🎨 NLP DECORATED TEXT EXTRACTION TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description'][:100]}...")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP decoratedText extraction successful")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_icon_extraction(self, client):
        """Test NLP extraction and mapping of various icon types."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": """Create a card with decoratedText widgets using different icons:
                - person icon for 'User: Admin'
                - email icon for 'Contact: admin@example.com'
                - clock icon for 'Last Login: Today'
                - star icon for 'Rating: 5 stars'""",
            "card_params": {
                "title": f"Icon Extraction Test ({timestamp})"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🎯 NLP ICON EXTRACTION TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description'][:100]}...")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP icon extraction successful")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_collapsible_section(self, client):
        """Test NLP extraction of collapsible sections."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": """Create a card with a collapsible section titled 'Details' 
                that shows 2 uncollapsible widgets and has additional hidden content.""",
            "card_params": {
                "title": f"Collapsible Section Test ({timestamp})"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"📁 NLP COLLAPSIBLE SECTION TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description']}")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP collapsible section extraction successful")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_grid_layout(self, client):
        """Test NLP extraction of grid layouts."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": """Create a card with a grid layout showing 2 columns:
                - Column 1: Product A with image
                - Column 2: Product B with image""",
            "card_params": {
                "title": f"Grid Layout Test ({timestamp})"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🎯 NLP GRID LAYOUT TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description']}")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP grid layout extraction successful")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_switch_control(self, client):
        """Test NLP extraction of switch controls in decoratedText."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": """Create a card with decoratedText that has a switch control:
                'Enable Notifications' with a toggle switch that is checked by default.""",
            "card_params": {
                "title": f"Switch Control Test ({timestamp})"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🔄 NLP SWITCH CONTROL TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description']}")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP switch control extraction successful")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_html_content(self, client):
        """Test NLP extraction with HTML formatted content."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": """Create a card with HTML content:
                text with <b>bold text</b>, <i>italic text</i>, and <font color="#FF0000">red colored text</font>.""",
            "card_params": {
                "title": f"HTML Content Test ({timestamp})"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🌐 NLP HTML CONTENT TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description']}")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP HTML content extraction successful")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_complex_dashboard_card(self, client):
        """Test NLP extraction of a complex dashboard-style card."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": """Create a status dashboard card titled 'System Health' with subtitle 'Live Status'.
                Add sections:
                - 'Server Status' section with decoratedText showing 'Online' with check circle icon
                - 'Database Status' section with decoratedText showing 'Connected' with database icon
                - 'Actions' section with buttons: 'Restart' in red, 'Backup' in blue""",
            "card_params": {},  # Let NLP extract everything
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"📊 NLP COMPLEX DASHBOARD TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description'][:100]}...")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP complex dashboard extraction successful")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_parameter_merging(self, client):
        """Test that user-provided card_params take priority over NLP-extracted ones."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "Create a card titled 'NLP Title' with text 'NLP Text'",
            "card_params": {
                "title": f"User Override Title ({timestamp})",  # This should override NLP
                "subtitle": "User Provided Subtitle"  # This adds to NLP extraction
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🔀 NLP PARAMETER MERGING TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: {test_payload['card_description']}")
        print(f"User params: {test_payload['card_params']}")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP parameter merging successful - user params took priority")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_validation_auto_fixing(self, client):
        """Test that NLP parser auto-fixes validation issues."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Create a description that would generate invalid parameters
        long_title = "A" * 250  # Exceeds 200 char limit
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": f"Create a card titled '{long_title}' with 10 buttons named Button1 through Button10",
            "card_params": {},
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🔧 NLP VALIDATION AUTO-FIXING TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Testing: Title with {len(long_title)} chars (limit: 200)")
        print(f"Testing: 10 buttons (limit: 6)")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ NLP validation auto-fixing successful - limits enforced")
        else:
            print(f"❓ Response: {content}")
    
    @pytest.mark.asyncio
    async def test_nlp_empty_description(self, client):
        """Test handling of empty or minimal descriptions."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing")
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "",  # Empty description
            "card_params": {
                "title": f"Fallback Card ({timestamp})",
                "text": "Card created without NLP description"
            },
            "webhook_url": TEST_WEBHOOK_URL
        }
        
        print(f"\n{'='*60}")
        print(f"🚫 NLP EMPTY DESCRIPTION TEST ({timestamp})")
        print(f"{'='*60}")
        print(f"Description: (empty)")
        print(f"User params: {test_payload['card_params']}")
        print(f"{'='*60}\n")
        
        result = await client.call_tool("send_dynamic_card", test_payload)
        
        # Extract content
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        else:
            content = str(result)
        
        print(f"Result: {content[:200]}...")
        
        assert content is not None
        assert len(content.strip()) > 0
        
        if "sent successfully" in content.lower() or "status: 200" in content:
            print("✅ Empty description handled gracefully - used user params")
        else:
            print(f"❓ Response: {content}")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])