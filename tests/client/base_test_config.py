"""Base configuration for standardized client testing framework.

🔧 MCP Tools Used:
- N/A (Configuration module - no direct MCP tool usage)
- Enables testing of all MCP tools through client connection management

🧪 What's Being Tested:
- Server connection reliability (HTTP/HTTPS protocol detection)
- SSL certificate handling and bypass for testing
- Environment variable configuration
- Client initialization and connection fallback
- Protocol detection and automatic switching
- Error handling for connection failures

🔍 Potential Duplications:
- No duplications - this is the foundational configuration used by all other tests
- Provides shared connection logic to eliminate duplication across test files
- Centralizes environment configuration to avoid repetition

Note: This is a framework support file used by all client tests.
"""

import os
import ssl
import httpx
from fastmcp import Client
from dotenv import load_dotenv
from ..test_auth_utils import get_client_auth_config

# Load environment variables from .env file
load_dotenv()

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("SERVER_HOST", os.getenv("MCP_SERVER_HOST", "localhost"))
SERVER_PORT = os.getenv("SERVER_PORT", os.getenv("MCP_SERVER_PORT", "8002"))

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_example@gmail.com")

# Test Google Slides presentation ID from environment variable
GOOGLE_SLIDE_PRESENTATION_ID = os.getenv("GOOGLE_SLIDE_PRESENTATION_ID", None)


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

# FastMCP servers use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"{PROTOCOL}://{SERVER_HOST}:{SERVER_PORT}/mcp/")


def print_test_configuration():
    """Print the test configuration for debugging."""
    print(f"\n🔧 Test Configuration:")
    print(f"   SERVER_HOST: {SERVER_HOST}")
    print(f"   SERVER_PORT: {SERVER_PORT}")
    print(f"   DETECTED_PROTOCOL: {DETECTED_PROTOCOL}")
    print(f"   FINAL_PROTOCOL: {PROTOCOL}")
    print(f"   SERVER_URL: {SERVER_URL}")
    print(f"   TEST_EMAIL: {TEST_EMAIL}")
    print(f"   GOOGLE_SLIDE_PRESENTATION_ID: {GOOGLE_SLIDE_PRESENTATION_ID or 'Not set'}")
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
            test_url = f"{protocol}://{SERVER_HOST}:{SERVER_PORT}/mcp/"
            print(f"   🔌 Attempting connection to {test_url}")
            
            # Configure client based on protocol
            if protocol == "https":
                print(f"   🔒 Configuring HTTPS client with SSL bypass for testing")
                
                # Create FastMCP client with HTTPS
                test_client = Client(
                    test_url,
                    auth=auth_config,
                    timeout=30.0
                )
                
                # Try to configure SSL bypass if possible
                try:
                    # Create httpx client with SSL bypass
                    httpx_client = httpx.AsyncClient(
                        verify=False,  # Skip SSL verification for testing
                        timeout=30.0
                    )
                    
                    # Override httpx client if accessible
                    if hasattr(test_client, '_transport'):
                        if hasattr(test_client._transport, '_client'):
                            test_client._transport._client = httpx_client
                        elif hasattr(test_client._transport, 'client'):
                            test_client._transport.client = httpx_client
                except Exception as ssl_config_error:
                    print(f"   ⚠️ Could not configure SSL bypass: {ssl_config_error}")
                    # Continue with default SSL configuration
            else:
                print(f"   🌐 Configuring HTTP client")
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
- http://{SERVER_HOST}:{SERVER_PORT}/mcp/
- https://{SERVER_HOST}:{SERVER_PORT}/mcp/

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