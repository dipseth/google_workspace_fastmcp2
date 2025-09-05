"""
Test the refactored service list resources with authentication.

This tests the new tag-based discovery and forward() pattern implementation
with actual authenticated user context.
"""

import pytest
import json
from .base_test_config import TEST_EMAIL
from .test_helpers import ToolTestRunner, TestResponseValidator, print_test_result


@pytest.mark.service("auth")
@pytest.mark.auth_required
class TestRefactoredWithAuth:
    """Test the refactored service list resources with authentication."""
    
    @pytest.mark.asyncio
    async def test_check_drive_authentication(self, client):
        """Test checking Drive authentication status."""
        print(f"Checking authentication status for {TEST_EMAIL}...")
        
        runner = ToolTestRunner(client, TEST_EMAIL)
        result = await runner.test_tool_with_explicit_email("check_drive_auth")
        
        print(f"Authentication result: {result['content'][:200]}...")
        
        # Verify we get a response about authentication
        assert result["success"], "Should get response from check_drive_auth"
        content = result["content"].lower()
        
        if "authenticated" in content and "valid" in content:
            print(f"✅ User {TEST_EMAIL} is authenticated")
        else:
            print(f"⚠️ Authentication may be required for {TEST_EMAIL}")
            
        print_test_result("Drive Auth Check", result)
    
    @pytest.mark.asyncio
    async def test_gmail_labels_with_auth(self, client):
        """Test Gmail labels resource with authentication."""
        print("Testing service://gmail/labels (with authenticated context)")
        
        content = await client.read_resource("service://gmail/labels")
        assert content and len(content) > 0, "Should receive content"
        
        data = json.loads(content[0].text)
        
        if "error" in data:
            print(f"⚠️ Error: {data['error'][:100]}")
            if "auth" in data['error'].lower():
                print("Authentication still required")
                # This is expected if not authenticated
                assert TestResponseValidator.is_valid_auth_response(data['error'])
        else:
            print("✅ Got Gmail labels!")
            if "items" in data:
                print(f"Found {data.get('count', len(data['items']))} labels")
                # Show first few labels
                for label in data['items'][:3]:
                    if isinstance(label, dict):
                        print(f"- {label.get('name', label.get('id', str(label)))}")
            elif isinstance(data, list):
                print(f"Found {len(data)} labels")
    
    @pytest.mark.asyncio
    async def test_gmail_filters_with_auth(self, client):
        """Test Gmail filters resource with authentication."""
        print("Testing service://gmail/filters (with authenticated context)")
        
        content = await client.read_resource("service://gmail/filters")
        assert content and len(content) > 0, "Should receive content"
        
        data = json.loads(content[0].text)
        
        if "error" in data:
            print(f"⚠️ Error: {data['error'][:100]}")
            assert TestResponseValidator.is_valid_auth_response(data['error'])
        else:
            print("✅ Got Gmail filters!")
            if "items" in data:
                print(f"Found {data.get('count', len(data['items']))} filters")
            elif isinstance(data, list):
                print(f"Found {len(data)} filters")
    
    @pytest.mark.asyncio
    async def test_calendar_calendars_with_auth(self, client):
        """Test Calendar calendars resource with authentication."""
        print("Testing service://calendar/calendars (with authenticated context)")
        
        content = await client.read_resource("service://calendar/calendars")
        assert content and len(content) > 0, "Should receive content"
        
        data = json.loads(content[0].text)
        
        if "error" in data:
            print(f"⚠️ Error: {data['error'][:100]}")
            assert TestResponseValidator.is_valid_auth_response(data['error'])
        else:
            print("✅ Got calendars!")
            if "items" in data:
                print(f"Found {data.get('count', len(data['items']))} calendars")
                # Show first few calendars
                for cal in data['items'][:3]:
                    if isinstance(cal, dict):
                        print(f"- {cal.get('summary', cal.get('id', str(cal)))}")
            elif isinstance(data, list):
                print(f"Found {len(data)} calendars")
    
    @pytest.mark.asyncio
    async def test_drive_items_with_auth(self, client):
        """Test Drive items resource with authentication."""
        print("Testing service://drive/items (with authenticated context)")
        
        content = await client.read_resource("service://drive/items")
        assert content and len(content) > 0, "Should receive content"
        
        data = json.loads(content[0].text)
        
        if "error" in data:
            print(f"⚠️ Error: {data['error'][:100]}")
            assert TestResponseValidator.is_valid_auth_response(data['error'])
        else:
            print("✅ Got Drive items!")
            if "items" in data:
                print(f"Found {data.get('count', len(data['items']))} items")
            elif isinstance(data, list):
                print(f"Found {len(data)} items")
    
    @pytest.mark.asyncio
    async def test_specific_gmail_label_detail(self, client):
        """Test specific Gmail label detail resource."""
        print("Testing specific label detail: service://gmail/labels/INBOX")
        
        content = await client.read_resource("service://gmail/labels/INBOX")
        assert content and len(content) > 0, "Should receive content"
        
        data = json.loads(content[0].text)
        
        if "error" in data:
            print(f"⚠️ Error: {data['error'][:100]}")
            assert TestResponseValidator.is_valid_auth_response(data['error'])
        else:
            print("✅ Got INBOX label details!")
            if isinstance(data, dict):
                print(f"Label ID: {data.get('id', 'N/A')}")
                print(f"Label Name: {data.get('name', 'N/A')}")
                print(f"Type: {data.get('type', 'N/A')}")
                if 'messagesTotal' in data:
                    print(f"Total Messages: {data['messagesTotal']}")
                if 'messagesUnread' in data:
                    print(f"Unread Messages: {data['messagesUnread']}")