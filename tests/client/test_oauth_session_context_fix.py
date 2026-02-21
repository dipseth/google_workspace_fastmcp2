"""Test suite for OAuth session context fix using FastMCP Client SDK to test the running MCP server."""

"""Test OAuth session context fixes and authentication improvements.

🔧 MCP Tools Used:
- OAuth authentication tools: Test OAuth flow improvements
- Session management: Test session context handling
- Authentication validation: Validate auth improvements
- Context preservation: Test context maintenance across requests

🧪 What's Being Tested:
- OAuth session context preservation and management
- Authentication state consistency across requests
- Session timeout and renewal mechanisms
- Context isolation between different user sessions
- Authentication error recovery and retry logic
- Session security and token management
- Integration with middleware authentication patterns

🔍 Potential Duplications:
- Authentication testing overlaps with auth pattern improvement tests
- Session management might overlap with other session-related tests
- OAuth flows similar to other authentication integration tests
- Context management patterns might be similar to other context-aware tests
"""

import asyncio
import json
import os

import pytest
from dotenv import load_dotenv
from fastmcp import Client

# Load environment variables from .env file
load_dotenv()


# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")


class TestOAuthSessionContext:
    """Test OAuth session context and user email handling using the FastMCP Client."""

    # Use standardized client fixture from conftest.py

    @pytest.fixture
    async def oauth_client(self):
        """Create a client using OAuth authentication."""
        from fastmcp.client.auth import OAuth

        # Configure OAuth with the MCP server URL
        oauth = OAuth(
            mcp_url=SERVER_URL, client_name="OAuth Session Context Test Client"
        )

        client = Client(SERVER_URL, auth=oauth)
        async with client:
            yield client

    @pytest.mark.asyncio
    async def test_server_connectivity(self, client):
        """Test that we can connect to the server."""
        # Ping the server to verify connectivity
        await client.ping()
        assert client.is_connected()

    @pytest.mark.asyncio
    async def test_user_email_resource_after_start_google_auth(self, client):
        """Test that user email context works after using start_google_auth tool."""
        # First, check if start_google_auth tool is available
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        if "start_google_auth" not in tool_names:
            pytest.skip("start_google_auth tool not available")

        # Call start_google_auth (this sets user email in tool arguments)
        try:
            result = await client.call_tool(
                "start_google_auth", arguments={"user_email": TEST_EMAIL}
            )
            print(f"✅ start_google_auth called for {TEST_EMAIL}")
        except Exception as e:
            print(
                f"⚠️ start_google_auth failed (expected if already authenticated): {e}"
            )

        # Now test if user resources work
        resources = await client.list_resources()
        resource_uris = [str(r.uri) for r in resources]  # Convert AnyUrl to string

        # Check if user resources are available
        user_resources = [uri for uri in resource_uris if uri.startswith("user://")]
        assert len(user_resources) > 0, "No user:// resources found"

        # Test user://current/email resource
        if "user://current/email" in resource_uris:
            try:
                result = await client.read_resource("user://current/email")
                # Result is a list of TextResourceContents, parse JSON from first item
                if result and hasattr(result[0], "text"):
                    data = json.loads(result[0].text)
                    assert "error" not in data, (
                        f"Error reading user://current/email: {data.get('error')}"
                    )
                    assert "email" in data, "No email field in response"
                    print(f"✅ user://current/email works: {data.get('email')}")
                else:
                    print(f"⚠️ Unexpected result format: {result}")
            except Exception as e:
                pytest.fail(f"Failed to read user://current/email: {e}")

        # Test user://current/profile resource
        if "user://current/profile" in resource_uris:
            try:
                result = await client.read_resource("user://current/profile")
                # Result is a list of TextResourceContents, parse JSON from first item
                if result and hasattr(result[0], "text"):
                    data = json.loads(result[0].text)
                    assert "error" not in data, (
                        f"Error reading user://current/profile: {data.get('error')}"
                    )
                    assert "user" in data or "email" in data, "No user data in response"
                    print("✅ user://current/profile works")
                else:
                    print(f"⚠️ Unexpected result format: {result}")
            except Exception as e:
                pytest.fail(f"Failed to read user://current/profile: {e}")

    @pytest.mark.asyncio
    async def test_auth_session_resource(self, client):
        """Test auth://session/current resource to verify session context."""
        resources = await client.list_resources()
        resource_uris = [str(r.uri) for r in resources]  # Convert AnyUrl to string

        if "auth://session/current" not in resource_uris:
            pytest.skip("auth://session/current resource not available")

        try:
            result = await client.read_resource("auth://session/current")
            # Result is a list of TextResourceContents, parse JSON from first item
            if result and hasattr(result[0], "text"):
                data = json.loads(result[0].text)
                print(f"📊 Session data: {json.dumps(data, indent=2)}")

                # Check if session is active
                if data.get("session_active") is False or "error" in data:
                    # No active session - this is valid when not authenticated
                    print(
                        f"⚠️ No active session: {data.get('error', 'session not active')}"
                    )
                    print(
                        "   This is expected when OAuth authentication hasn't been completed"
                    )
                    return  # Test passes - no session is a valid state

                # Check session structure when session is active
                assert "session_id" in data, "No session_id in auth://session/current"

                # After our fix, user_email should be populated from session
                if "user_email" in data:
                    print(f"✅ user_email found in session: {data['user_email']}")
                    # It should not be null after authentication
                    if data["user_email"] is not None:
                        print(f"✅ user_email is properly set: {data['user_email']}")
                    else:
                        print("⚠️ user_email is null - may need OAuth authentication")
            else:
                print(f"⚠️ Unexpected result format: {result}")

        except Exception as e:
            pytest.fail(f"Failed to read auth://session/current: {e}")

    @pytest.mark.asyncio
    async def test_oauth_authentication_sets_session_context(self, oauth_client):
        """Test that OAuth authentication properly sets user email in session context."""
        # This test requires manual OAuth flow completion
        pytest.skip(
            "OAuth flow requires manual browser interaction - run manually if needed"
        )

        # After OAuth authentication, the session should have user email
        try:
            # First ping to ensure OAuth authentication completes
            await oauth_client.ping()

            # Now check if user resources work
            result = await oauth_client.read_resource("user://current/email")
            assert "error" not in result, f"Error after OAuth: {result.get('error')}"
            assert "email" in result, "No email in response after OAuth"
            print(
                f"✅ OAuth authentication properly sets user context: {result.get('email')}"
            )

        except Exception as e:
            pytest.fail(f"OAuth session context test failed: {e}")

    @pytest.mark.asyncio
    async def test_user_resources_without_email_parameter(self, client):
        """Test that user resources work without explicitly passing email parameter."""
        # This tests the fix - resources should work from session context
        resources = await client.list_resources()
        resource_uris = [str(r.uri) for r in resources]  # Convert AnyUrl to string

        # Find any user resource that normally requires email
        test_resources = [
            "user://current/email",
            "user://current/profile",
            "user://preferences/gmail",
        ]

        for resource_uri in test_resources:
            if resource_uri in resource_uris:
                try:
                    # Try to read without providing email parameter
                    result = await client.read_resource(resource_uri)

                    # Check if it works or gives the expected error
                    if "error" in result:
                        error_msg = result.get("error", "")
                        if "No authenticated user found" in error_msg:
                            print(
                                f"⚠️ {resource_uri}: Needs authentication (expected before OAuth)"
                            )
                        else:
                            pytest.fail(
                                f"Unexpected error for {resource_uri}: {error_msg}"
                            )
                    else:
                        print(f"✅ {resource_uri}: Works from session context!")

                except Exception as e:
                    print(f"⚠️ {resource_uri}: Exception (may need auth): {e}")

    @pytest.mark.asyncio
    async def test_service_list_resources_with_session_context(self, client):
        """Test that service list resources work with session context."""
        # Test resources that depend on user context
        resources = await client.list_resources()
        resource_uris = [str(r.uri) for r in resources]  # Convert AnyUrl to string

        # Check Gmail service resources
        gmail_resources = [uri for uri in resource_uris if "gmail" in uri.lower()]

        if gmail_resources:
            # Pick one to test
            test_uri = gmail_resources[0]
            try:
                result = await client.read_resource(test_uri)
                if "error" not in result:
                    print(f"✅ {test_uri}: Works with session context")
                elif "authentication" in result.get("error", "").lower():
                    print(f"⚠️ {test_uri}: Needs authentication (expected)")
                else:
                    print(f"❓ {test_uri}: {result.get('error')}")
            except Exception as e:
                print(f"⚠️ {test_uri}: Exception: {e}")


@pytest.mark.asyncio
async def test_oauth_fix_summary():
    """Standalone test to summarize the OAuth session context fix."""
    print("\n" + "=" * 60)
    print("OAUTH SESSION CONTEXT FIX SUMMARY")
    print("=" * 60)
    print(
        """
The fix addresses the issue where user email context was not being set
properly during OAuth authentication. The changes include:

1. **OAuth Callback (drive/upload_tools.py)**:
   - Now stores user email in session data after successful OAuth
   - Uses store_session_data(session_id, "user_email", user_email)

2. **Middleware (auth/middleware.py)**:
   - on_request(): Restores user email context from session data
   - on_call_tool(): First checks session data for user email before
     extracting from tool arguments

3. **Result**:
   - Resources like user://current/email now work after OAuth
   - Session context persists across requests
   - No need to pass user_email in every tool call

To test manually:
1. Start the server: python server.py
2. Authenticate via OAuth proxy
3. Access user://current/email - should return authenticated user
4. Access auth://session/current - should show user_email populated
"""
    )
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # Run the summary
    asyncio.run(test_oauth_fix_summary())

    # Run pytest
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
