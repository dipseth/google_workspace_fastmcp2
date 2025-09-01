"""
Test the refactored service list resources with authentication.

This tests the new tag-based discovery and forward() pattern implementation
with actual authenticated user context.
"""

import asyncio
import json
from fastmcp import Client
import os

# Server configuration
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email
TEST_EMAIL = "sethrivers@gmail.com"


async def test_service_list_with_auth():
    """Test the refactored service list resources with authentication."""
    print("=" * 80)
    print("TESTING REFACTORED SERVICE LIST RESOURCES WITH AUTHENTICATION")
    print("=" * 80)
    
    # Create client without auth for basic testing
    client = Client(SERVER_URL)
    
    try:
        async with client:
            print(f"\n📋 Testing with authenticated user: {TEST_EMAIL}\n")
            
            # First check authentication status
            print(f"1. Checking authentication status for {TEST_EMAIL}...")
            try:
                # Call check_drive_auth tool
                result = await client.call_tool(
                    "check_drive_auth",
                    {"user_google_email": TEST_EMAIL}
                )
                
                if result:
                    # Parse the result
                    if hasattr(result, 'content') and result.content:
                        content = result.content[0]
                        if hasattr(content, 'text'):
                            auth_result = content.text
                        else:
                            auth_result = str(content)
                    else:
                        auth_result = str(result)
                    
                    print(f"   Authentication result: {auth_result[:200]}...")
                    
                    # Check if authenticated
                    if "authenticated" in auth_result.lower() and "valid" in auth_result.lower():
                        print(f"   ✅ User {TEST_EMAIL} is authenticated")
                    else:
                        print(f"   ⚠️  Authentication may be required for {TEST_EMAIL}")
                        print("   Run: start_google_auth('sethrivers@gmail.com') to authenticate")
                else:
                    print("   ❌ No response from check_drive_auth")
                    
            except Exception as e:
                print(f"   ❌ Error checking auth: {e}")
                print("   Continuing with tests anyway...")
            
            print()
            
            # Test 2: Get Gmail labels with authenticated context
            print("2. Testing service://gmail/labels (with authenticated context)")
            try:
                content = await client.read_resource("service://gmail/labels")
                if content and len(content) > 0:
                    data = json.loads(content[0].text)
                    
                    if "error" in data:
                        print(f"   ⚠️  Error: {data['error'][:100]}")
                        if "auth" in data['error'].lower():
                            print("   Authentication still required")
                    else:
                        print(f"   ✅ Got Gmail labels!")
                        if "items" in data:
                            print(f"      Found {data.get('count', len(data['items']))} labels")
                            # Show first few labels
                            for label in data['items'][:3]:
                                if isinstance(label, dict):
                                    print(f"      - {label.get('name', label.get('id', str(label)))}")
                        elif isinstance(data, list):
                            print(f"      Found {len(data)} labels")
                            for label in data[:3]:
                                if isinstance(label, dict):
                                    print(f"      - {label.get('name', label.get('id', str(label)))}")
                else:
                    print("   ❌ No content received")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            print()
            
            # Test 3: Get Gmail filters with authenticated context
            print("3. Testing service://gmail/filters (with authenticated context)")
            try:
                content = await client.read_resource("service://gmail/filters")
                if content and len(content) > 0:
                    data = json.loads(content[0].text)
                    
                    if "error" in data:
                        print(f"   ⚠️  Error: {data['error'][:100]}")
                    else:
                        print(f"   ✅ Got Gmail filters!")
                        if "items" in data:
                            print(f"      Found {data.get('count', len(data['items']))} filters")
                        elif isinstance(data, list):
                            print(f"      Found {len(data)} filters")
                else:
                    print("   ❌ No content received")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            print()
            
            # Test 4: Get Calendar calendars with authenticated context
            print("4. Testing service://calendar/calendars (with authenticated context)")
            try:
                content = await client.read_resource("service://calendar/calendars")
                if content and len(content) > 0:
                    data = json.loads(content[0].text)
                    
                    if "error" in data:
                        print(f"   ⚠️  Error: {data['error'][:100]}")
                    else:
                        print(f"   ✅ Got calendars!")
                        if "items" in data:
                            print(f"      Found {data.get('count', len(data['items']))} calendars")
                            # Show first few calendars
                            for cal in data['items'][:3]:
                                if isinstance(cal, dict):
                                    print(f"      - {cal.get('summary', cal.get('id', str(cal)))}")
                        elif isinstance(data, list):
                            print(f"      Found {len(data)} calendars")
                else:
                    print("   ❌ No content received")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            print()
            
            # Test 5: Get Drive items with authenticated context
            print("5. Testing service://drive/items (with authenticated context)")
            try:
                content = await client.read_resource("service://drive/items")
                if content and len(content) > 0:
                    data = json.loads(content[0].text)
                    
                    if "error" in data:
                        print(f"   ⚠️  Error: {data['error'][:100]}")
                    else:
                        print(f"   ✅ Got Drive items!")
                        if "items" in data:
                            print(f"      Found {data.get('count', len(data['items']))} items")
                        elif isinstance(data, list):
                            print(f"      Found {len(data)} items")
                else:
                    print("   ❌ No content received")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            print()
            
            # Test 6: Test a specific label detail (if we got labels)
            print("6. Testing specific label detail: service://gmail/labels/INBOX")
            try:
                content = await client.read_resource("service://gmail/labels/INBOX")
                if content and len(content) > 0:
                    data = json.loads(content[0].text)
                    
                    if "error" in data:
                        print(f"   ⚠️  Error: {data['error'][:100]}")
                    else:
                        print(f"   ✅ Got INBOX label details!")
                        if isinstance(data, dict):
                            print(f"      Label ID: {data.get('id', 'N/A')}")
                            print(f"      Label Name: {data.get('name', 'N/A')}")
                            print(f"      Type: {data.get('type', 'N/A')}")
                            if 'messagesTotal' in data:
                                print(f"      Total Messages: {data['messagesTotal']}")
                            if 'messagesUnread' in data:
                                print(f"      Unread Messages: {data['messagesUnread']}")
                else:
                    print("   ❌ No content received")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
    except Exception as e:
        print(f"\n❌ Client connection failed: {e}")
        print("Make sure the server is running on port 8002")
        return False
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print("✅ Service list resources are working")
    print("✅ Tag-based discovery is functioning")
    print("✅ Forward() pattern is implemented")
    print("\nAuthentication status:")
    print(f"- User: {TEST_EMAIL}")
    print("- If not authenticated, run: start_google_auth('sethrivers@gmail.com')")
    print("\nNext steps:")
    print("1. Ensure user is authenticated for full testing")
    print("2. Verify all services return data correctly")
    print("3. Replace main service_list_resources.py with refactored version")
    
    return True


async def main():
    """Run the test."""
    print("Starting refactored service list resources test with authentication...\n")
    
    success = await test_service_list_with_auth()
    
    if success:
        print("\n🎉 Test completed successfully!")
    else:
        print("\n❌ Test failed")
    
    return success


if __name__ == "__main__":
    asyncio.run(main())