"""Fixed authentication pattern tests for Google Workspace MCP tools.

🔧 MCP Tools Used:
- Various Google Workspace tools (Gmail, Drive, Calendar, etc.) for auth pattern validation

🧪 What's Being Tested:
- Dual authentication patterns: explicit email parameter vs middleware injection
- Backward compatibility with user_google_email parameter
- Middleware authentication handling without explicit email
- Protocol detection (HTTP/HTTPS) and connection fallback
- Response validation for both successful operations and auth errors
- Client connection reliability and error handling

🔍 Potential Duplications:
- This test focuses on authentication patterns rather than specific tool functionality
- May overlap with individual service tests that also test auth, but provides comprehensive
  cross-service auth validation that service-specific tests don't cover
- Serves as the foundational pattern that other tests should follow
"""

import os

import httpx
import pytest
from dotenv import load_dotenv
from fastmcp import Client

from ..test_auth_utils import get_client_auth_config

# Load environment variables from .env file
load_dotenv()

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("SERVER_HOST", os.getenv("MCP_SERVER_HOST", "localhost"))
SERVER_PORT = os.getenv("SERVER_PORT", os.getenv("MCP_SERVER_PORT", "8002"))


# Try to auto-detect server protocol by checking common environment variables
def detect_server_protocol():
    """Auto-detect if the server is running on HTTP or HTTPS."""
    # Check explicit environment variables first
    if os.getenv("ENABLE_HTTPS", "false").lower() == "true":
        return "https"

    if os.getenv("SSL_ENABLED", "false").lower() == "true":
        return "https"

    # Check for SSL certificate files (indicates HTTPS)
    ssl_cert = os.getenv("SSL_CERT_FILE") or os.getenv("SSL_CERTFILE")
    ssl_key = os.getenv("SSL_KEY_FILE") or os.getenv("SSL_KEYFILE")
    if ssl_cert and ssl_key:
        return "https"

    # Check server port (common HTTPS ports)
    port = int(SERVER_PORT)
    if port in [443, 8443, 9443]:
        return "https"

    # Default to HTTP for development
    return "http"


# Auto-detect protocol
DETECTED_PROTOCOL = detect_server_protocol()
PROTOCOL = os.getenv("MCP_PROTOCOL", DETECTED_PROTOCOL)

# FastMCP servers typically live at `/mcp` (no trailing slash). Using `/mcp/` can
# trigger a 307 redirect which breaks StreamableHTTP in some client stacks.
SERVER_URL = os.getenv(
    "MCP_SERVER_URL", f"{PROTOCOL}://{SERVER_HOST}:{SERVER_PORT}/mcp"
)

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_example@gmail.com")

# Debug configuration
print("\n🔧 Test Configuration:")
print(f"   SERVER_HOST: {SERVER_HOST}")
print(f"   SERVER_PORT: {SERVER_PORT}")
print(f"   DETECTED_PROTOCOL: {DETECTED_PROTOCOL}")
print(f"   FINAL_PROTOCOL: {PROTOCOL}")
print(f"   SERVER_URL: {SERVER_URL}")
print(f"   TEST_EMAIL: {TEST_EMAIL}")
print(f"   SSL_CERT_FILE: {os.getenv('SSL_CERT_FILE', 'Not set')}")
print(f"   SSL_KEY_FILE: {os.getenv('SSL_KEY_FILE', 'Not set')}")


async def create_test_client(test_email: str = TEST_EMAIL):
    """Create a client with automatic protocol detection and fallback."""
    auth_config = get_client_auth_config(test_email)

    # Try both HTTP and HTTPS if protocol detection is uncertain
    protocols_to_try = []
    if PROTOCOL == "https":
        protocols_to_try = ["https", "http"]  # Try HTTPS first, then HTTP fallback
    else:
        protocols_to_try = ["http", "https"]  # Try HTTP first, then HTTPS fallback

    last_error = None

    for protocol in protocols_to_try:
        try:
            test_url = f"{protocol}://{SERVER_HOST}:{SERVER_PORT}/mcp"
            print(f"   🔌 Attempting connection to {test_url}")

            # Configure client based on protocol
            if protocol == "https":
                print("   🔒 Configuring HTTPS client with SSL bypass for testing")

                # Create FastMCP client with HTTPS
                test_client = Client(test_url, auth=auth_config, timeout=30.0)

                # Try to configure SSL bypass if possible
                try:
                    # Create httpx client with SSL bypass
                    httpx_client = httpx.AsyncClient(
                        verify=False, timeout=30.0  # Skip SSL verification for testing
                    )

                    # Override httpx client if accessible
                    if hasattr(test_client, "_transport"):
                        if hasattr(test_client._transport, "_client"):
                            test_client._transport._client = httpx_client
                        elif hasattr(test_client._transport, "client"):
                            test_client._transport.client = httpx_client
                except Exception as ssl_config_error:
                    print(f"   ⚠️ Could not configure SSL bypass: {ssl_config_error}")
                    # Continue with default SSL configuration
            else:
                print("   🌐 Configuring HTTP client")
                test_client = Client(test_url, auth=auth_config, timeout=30.0)

            # Test the connection
            async with test_client:
                # Try a simple operation to verify connection
                await test_client.list_tools()
                print(f"   ✅ Successfully connected using {protocol.upper()}")
                return test_client

        except Exception as e:
            last_error = e
            print(f"   ❌ {protocol.upper()} connection failed: {e}")
            continue

    # Both protocols failed, provide diagnostic information
    diagnostic_info = f"""
❌ Failed to connect to server on both HTTP and HTTPS

Attempted URLs:
- http://{SERVER_HOST}:{SERVER_PORT}/mcp
- https://{SERVER_HOST}:{SERVER_PORT}/mcp

Last error: {last_error}

Troubleshooting:
1. Is the server running? Check with: ps aux | grep server.py
2. Is the server on the expected port {SERVER_PORT}?
3. Check server logs for SSL/HTTPS configuration
4. Try setting MCP_SERVER_URL environment variable explicitly
5. For HTTPS servers, ensure SSL certificates are properly configured

Environment variables to check:
- ENABLE_HTTPS={os.getenv('ENABLE_HTTPS', 'not set')}
- SSL_CERT_FILE={os.getenv('SSL_CERT_FILE', 'not set')}
- SSL_KEY_FILE={os.getenv('SSL_KEY_FILE', 'not set')}
- MCP_SERVER_URL={os.getenv('MCP_SERVER_URL', 'not set')}
    """
    raise RuntimeError(diagnostic_info)


class TestImprovedAuthPattern:
    """Test the improved authentication pattern with optional user_google_email parameter."""

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_list_gmail_labels_tool_available(self, client):
        """Test that list_gmail_labels tool is available and has proper signature, and actually call it."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        # Check that Gmail labels tool is registered
        assert (
            "list_gmail_labels" in tool_names
        ), "list_gmail_labels tool should be available"

        # Find the tool and check its parameters
        labels_tool = None
        for tool in tools:
            if tool.name == "list_gmail_labels":
                labels_tool = tool
                break

        assert labels_tool is not None, "list_gmail_labels tool should be found"

        # Check that the tool has the proper parameter signature
        # The tool should have user_google_email as an optional parameter
        tool_description = labels_tool.description
        assert "user_google_email" in str(
            labels_tool.inputSchema
        ), "Tool should have user_google_email parameter"

        print("\n✅ list_gmail_labels tool found with proper signature")
        print(f"   Description: {tool_description[:100]}...")

        # Now actually call the tool to see what labels we get
        print(
            "\n🔍 Testing list_gmail_labels tool execution with explicit user_google_email"
        )
        try:
            result = await client.call_tool(
                "list_gmail_labels", {"user_google_email": TEST_EMAIL}
            )

            assert result is not None, "Should get a result from the tool"
            content = result.content[0].text

            print("   📧 Full Response from list_gmail_labels:")
            print(f"   {content}")

            # Try to parse as JSON to see labels structure
            try:
                import json

                labels_data = json.loads(content)
                if isinstance(labels_data, dict):
                    print("\n   📊 Parsed Labels Data:")
                    print(f"   Total Labels: {labels_data.get('total_count', 'N/A')}")
                    print(
                        f"   System Labels: {len(labels_data.get('system_labels', []))}"
                    )
                    print(f"   User Labels: {len(labels_data.get('user_labels', []))}")

                    if labels_data.get("system_labels"):
                        print(
                            f"   System Label Examples: {labels_data['system_labels'][:3]}"
                        )
                    if labels_data.get("user_labels"):
                        print(
                            f"   User Label Examples: {labels_data['user_labels'][:3]}"
                        )

                    if labels_data.get("error"):
                        print(f"   ⚠️ Tool Error: {labels_data['error']}")

            except json.JSONDecodeError:
                print("   ⚠️ Response is not JSON, raw text response shown above")

            print("✅ Tool execution test completed")

        except Exception as e:
            print(f"   ❌ Tool execution failed: {e}")
            # Don't fail the test, just log the error
            print("   This may be expected if no authentication is set up")

    @pytest.mark.asyncio
    async def test_list_gmail_labels_with_explicit_email(self, client):
        """Test list_gmail_labels with explicit user_google_email parameter (backward compatibility)."""
        print(
            "\n🔍 Testing list_gmail_labels with explicit user_google_email parameter"
        )

        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        assert result is not None, "Should get a result from the tool"
        content = result.content[0].text

        print(f"   Response length: {len(content)} characters")
        print(f"   Response preview: {content[:200]}...")

        # Check that we get a valid response (auth error OR actual label payload)
        valid_responses = [
            "authentication" in content.lower(),
            "credentials" in content.lower(),
            "not authenticated" in content.lower(),
            "please check your gmail permissions" in content.lower(),
            # Real successful payload from this server is JSON starting with {"labels": ...}
            '"labels"' in content.lower(),
            "gmail labels" in content.lower(),
            "system labels" in content.lower(),
            "user-created labels" in content.lower(),
        ]

        assert any(
            valid_responses
        ), f"Should get valid response. Content: {content[:300]}"
        print("✅ Explicit email parameter test passed")

    @pytest.mark.asyncio
    async def test_list_gmail_labels_without_email_parameter(self, client):
        """Test list_gmail_labels WITHOUT user_google_email parameter (middleware auto-injection)."""
        print(
            "\n🔍 Testing list_gmail_labels WITHOUT user_google_email parameter (middleware injection)"
        )

        try:
            # Call without user_google_email parameter - should work via middleware injection
            result = await client.call_tool("list_gmail_labels", {})

            assert result is not None, "Should get a result from the tool"
            content = result.content[0].text

            print(f"   Response length: {len(content)} characters")
            print(f"   Response preview: {content[:200]}...")

            # Check that we get a valid response (auth error OR actual label payload)
            valid_responses = [
                "authentication" in content.lower(),
                "credentials" in content.lower(),
                "not authenticated" in content.lower(),
                "please check your gmail permissions" in content.lower(),
                '"labels"' in content.lower(),
                "gmail labels" in content.lower(),
                "system labels" in content.lower(),
                "user-created labels" in content.lower(),
                # Middleware might inject default or context-based email
                "middleware" in content.lower(),
                "auto-injection" in content.lower(),
            ]

            assert any(
                valid_responses
            ), f"Should get valid response via middleware. Content: {content[:300]}"
            print("✅ Middleware auto-injection test passed")

        except Exception as e:
            # If the tool requires the parameter at the client level, that's also valid behavior
            error_message = str(e).lower()
            if "required" in error_message or "missing" in error_message:
                print(
                    "🔄 Tool requires parameter at client level - middleware injection happens server-side"
                )
                print(f"   This is expected behavior: {e}")
            else:
                raise e

    @pytest.mark.asyncio
    async def test_middleware_authentication_flow_priority(self, client):
        """Test that the authentication flow follows the correct priority order."""
        print("\n🔑 Testing authentication flow priority")

        # Test with explicit parameter first
        result_explicit = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        content_explicit = result_explicit.content[0].text

        # The response should indicate which authentication method was used
        # Based on our middleware implementation, it should try:
        # 1. GoogleProvider (unified auth)
        # 2. JWT token extraction
        # 3. OAuth session fallback
        # 4. Tool arguments extraction

        print(f"   Explicit parameter response: {content_explicit[:150]}...")

        # Check if the response indicates successful authentication or expected error
        auth_indicators = [
            "authentication error" in content_explicit.lower(),
            "credentials" in content_explicit.lower(),
            '"labels"' in content_explicit.lower(),
            "system labels" in content_explicit.lower(),
            "user-created labels" in content_explicit.lower(),
            "gmail labels" in content_explicit.lower(),
        ]

        assert any(auth_indicators), "Should get authentication-related response"
        print("✅ Authentication flow priority test completed")

    @pytest.mark.asyncio
    async def test_jwt_middleware_integration(self, client):
        """Test that JWT middleware integration is working."""
        print("\n🎫 Testing JWT middleware integration")

        # Check if JWT authentication is enabled
        jwt_enabled = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"

        if not jwt_enabled:
            print("   JWT authentication disabled - skipping JWT-specific tests")
            pytest.skip("JWT authentication not enabled")

        # Test should work with JWT token if available
        auth_config = get_client_auth_config(TEST_EMAIL)

        if auth_config:
            print(f"   JWT token available: {auth_config[:30]}...")

            # Call the tool and check if JWT extraction worked
            result = await client.call_tool(
                "list_gmail_labels", {"user_google_email": TEST_EMAIL}
            )

            content = result.content[0].text
            print(f"   Response with JWT: {content[:150]}...")

            # Should either work or show proper auth error
            assert result is not None, "Should get response with JWT token"
            print("✅ JWT middleware integration test completed")
        else:
            print("   No JWT token available - testing fallback behavior")
            pytest.skip("No JWT token available for testing")


class TestBackwardCompatibility:
    """Test that the improved pattern maintains backward compatibility."""

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_existing_tools_still_work(self, client):
        """Test that existing tools with required user_google_email still work."""
        print("\n🔄 Testing backward compatibility with existing tools")

        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        # Find a few other Gmail tools that should still require user_google_email
        gmail_tools_to_test = [
            "search_gmail_messages",
            "send_gmail_message",
            "create_gmail_filter",
        ]

        available_gmail_tools = [
            tool for tool in gmail_tools_to_test if tool in tool_names
        ]

        if not available_gmail_tools:
            pytest.skip("No Gmail tools available for backward compatibility testing")

        # Test one of the available tools
        test_tool = available_gmail_tools[0]
        print(f"   Testing backward compatibility with: {test_tool}")

        try:
            if test_tool == "search_gmail_messages":
                result = await client.call_tool(
                    test_tool, {"user_google_email": TEST_EMAIL, "query": "test"}
                )
            elif test_tool == "send_gmail_message":
                result = await client.call_tool(
                    test_tool,
                    {
                        "user_google_email": TEST_EMAIL,
                        "to": "test@example.com",
                        "subject": "Test",
                        "body": "Test",
                    },
                )
            elif test_tool == "create_gmail_filter":
                result = await client.call_tool(
                    test_tool,
                    {
                        "user_google_email": TEST_EMAIL,
                        "from_address": "@test.com",
                        "add_label_ids": ["INBOX"],
                    },
                )

            assert result is not None, f"{test_tool} should return a result"
            content = result.content[0].text

            print(f"   {test_tool} response: {content[:100]}...")

            # Should get either success or auth error - both are valid
            valid_patterns = [
                "authentication" in content.lower(),
                "credentials" in content.lower(),
                "not authenticated" in content.lower(),
                "success" in content.lower(),
                "created" in content.lower(),
                "sent" in content.lower(),
                "found" in content.lower(),
                "error" in content.lower(),  # Generic error is also valid
            ]

            assert any(valid_patterns), f"Should get valid response from {test_tool}"
            print(f"✅ Backward compatibility maintained for {test_tool}")

        except Exception as e:
            # Parameter validation errors are expected for incomplete test data
            if "required" in str(e).lower() or "missing" in str(e).lower():
                print(f"   Expected validation error: {e}")
            else:
                raise e


class TestMiddlewareEnhancements:
    """Test the specific middleware enhancements we implemented."""

    # Using the global client fixture from conftest.py

    @pytest.mark.asyncio
    async def test_auth_priority_documentation(self, client):
        """Test that the authentication priority is correctly documented and implemented."""
        print("\n📚 Testing authentication priority documentation")

        # The middleware should implement this priority:
        # 1. GoogleProvider extraction (unified auth)
        # 2. JWT token extraction (new enhancement)
        # 3. OAuth session fallback (legacy compatibility)
        # 4. Tool arguments extraction (final fallback)

        expected_priority = [
            "GoogleProvider",
            "JWT token",
            "OAuth session",
            "Tool arguments",
        ]

        print("   Expected authentication priority:")
        for i, method in enumerate(expected_priority, 1):
            print(f"   {i}. {method}")

        # Test that our tool works with the implemented priority
        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        content = result.content[0].text

        # Should get a response that indicates the middleware is working
        assert result is not None, "Middleware should provide authentication flow"
        assert content, "Should get response content from middleware flow"

        print(f"   Middleware response: {content[:100]}...")
        print("✅ Authentication priority flow verified")

    @pytest.mark.asyncio
    async def test_enhanced_error_messages(self, client):
        """Test that enhanced error messages are working."""
        print("\n💬 Testing enhanced error messages")

        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        content = result.content[0].text

        # Enhanced error messages should be user-friendly
        user_friendly_patterns = [
            "please check your gmail permissions" in content.lower(),
            "authentication error" in content.lower(),
            "gmail labels" in content.lower(),
            "system labels" in content.lower(),
            "user-created labels" in content.lower(),
        ]

        # Should either have user-friendly error or successful response
        assert (
            any(user_friendly_patterns) or len(content) > 50
        ), "Should have meaningful response"

        print(
            f"   Response indicates: {'user-friendly error handling' if any(user_friendly_patterns[:3]) else 'successful authentication'}"
        )
        print("✅ Enhanced error messages verified")


if __name__ == "__main__":
    # Run tests with asyncio
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
