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

import httpx
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from ..test_auth_utils import get_client_auth_config

# NOTE on TLS for local tests:
# - `localhost+2.pem` is a *server* (leaf) cert. Clients generally need the *issuing CA/root*.
# - FastMCP 2.14.3 supports injecting an `httpx.AsyncClient` via `httpx_client_factory`.
#   We use that hook to set verify=False by default for local tests.
#
# If you *do* have a CA bundle you want httpx to trust (e.g. mkcert root CA), set:
#   MCP_CA_BUNDLE=/path/to/rootCA.pem
_CA_BUNDLE = os.getenv("MCP_CA_BUNDLE")
if _CA_BUNDLE:
    os.environ.setdefault("SSL_CERT_FILE", os.path.abspath(_CA_BUNDLE))
    os.environ.setdefault("REQUESTS_CA_BUNDLE", os.path.abspath(_CA_BUNDLE))

# Load environment variables from .env file
load_dotenv()

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("SERVER_HOST", os.getenv("MCP_SERVER_HOST", "localhost"))
SERVER_PORT = os.getenv("SERVER_PORT", os.getenv("MCP_SERVER_PORT", "8002"))

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_example@gmail.com")

# Test Google Slides presentation ID from environment variable
GOOGLE_SLIDE_PRESENTATION_ID = os.getenv("GOOGLE_SLIDE_PRESENTATION_ID", None)

# Test resource IDs from environment variables
TEST_DOCUMENT_ID = os.getenv("TEST_DOCUMENT_ID", None)
TEST_FOLDER_ID = os.getenv("TEST_FOLDER_ID", None)
TEST_FORM_ID = os.getenv("TEST_FORM_ID", None)
TEST_GOOGLE_SHEET_ID = os.getenv("TEST_GOOGLE_SHEET_ID", None)
TEST_CHAT_SPACE_ID = os.getenv("TEST_CHAT_SPACE_ID", None)


def detect_server_protocol():
    """Auto-detect if the server is running on HTTP or HTTPS."""
    # Check explicit environment variables first
    if os.getenv("ENABLE_HTTPS", "false").lower() == "true":
        return "https"

    if os.getenv("SSL_ENABLED", "false").lower() == "true":
        return "https"

    # If test suite is told to use an explicit MCP server URL, trust it.
    explicit_url = os.getenv("MCP_SERVER_URL")
    if explicit_url:
        return "https" if explicit_url.lower().startswith("https://") else "http"

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

# FastMCP servers typically live at `/mcp` (no trailing slash).
# Using `/mcp/` can trigger a 307 redirect which breaks StreamableHTTP in some client stacks.
SERVER_URL = os.getenv(
    "MCP_SERVER_URL", f"{PROTOCOL}://{SERVER_HOST}:{SERVER_PORT}/mcp"
)


def print_test_configuration():
    """Print the test configuration for debugging."""
    print("\n🔧 Test Configuration:")
    print(f"   SERVER_HOST: {SERVER_HOST}")
    print(f"   SERVER_PORT: {SERVER_PORT}")
    print(f"   DETECTED_PROTOCOL: {DETECTED_PROTOCOL}")
    print(f"   FINAL_PROTOCOL: {PROTOCOL}")
    print(f"   SERVER_URL: {SERVER_URL}")
    print(f"   TEST_EMAIL: {TEST_EMAIL}")
    print(
        f"   GOOGLE_SLIDE_PRESENTATION_ID: {GOOGLE_SLIDE_PRESENTATION_ID or 'Not set'}"
    )
    print(f"   SSL_CERT_FILE: {os.getenv('SSL_CERT_FILE', 'Not set')}")
    print(f"   SSL_KEY_FILE: {os.getenv('SSL_KEY_FILE', 'Not set')}")


async def create_test_client(test_email: str = TEST_EMAIL):
    """Create a client with automatic protocol detection and fallback.

    IMPORTANT (FastMCP 2.14.3):
    - Streamable HTTP uses `mcp.client.streamable_http.streamable_http_client()` which
      accepts an `http_client` argument.
    - FastMCP exposes this through `StreamableHttpTransport(..., httpx_client_factory=...)`.

    So for local tests we inject our own `httpx.AsyncClient(verify=False)` so HTTPS works
    even when the local dev cert is not trusted by Python/httpx.
    """

    auth_config = get_client_auth_config(test_email)

    protocols_to_try: list[str]
    if PROTOCOL == "https":
        protocols_to_try = ["https", "http"]
    else:
        protocols_to_try = ["http", "https"]

    last_error: Exception | None = None

    def _httpx_client_factory(**kwargs) -> httpx.AsyncClient:
        """Factory compatible with FastMCP/MCP http client factory signature.

        FastMCP passes kwargs such as:
        - headers
        - timeout
        - auth
        - follow_redirects

        We accept **kwargs to stay compatible across versions.
        """
        verify_tls = os.getenv("MCP_TEST_TLS_VERIFY", "false").lower() == "true"
        return httpx.AsyncClient(
            verify=verify_tls,
            headers=kwargs.get("headers"),
            timeout=kwargs.get("timeout") or httpx.Timeout(30.0),
            auth=kwargs.get("auth"),
            follow_redirects=kwargs.get("follow_redirects", True),
        )

    for protocol in protocols_to_try:
        test_url = f"{protocol}://{SERVER_HOST}:{SERVER_PORT}/mcp"
        print(f"   🔌 Attempting connection to {test_url}")

        try:
            verify_tls = os.getenv("MCP_TEST_TLS_VERIFY", "false").lower() == "true"

            if protocol == "https" and not verify_tls:
                print(
                    "   🔒 Using HTTPS with TLS verification disabled for local testing"
                )

            if protocol == "https":
                transport = StreamableHttpTransport(
                    test_url,
                    auth=auth_config,
                    httpx_client_factory=_httpx_client_factory,
                )
                test_client = Client(transport, timeout=30.0)
            else:
                # HTTP fallback uses default transport inference
                test_client = Client(test_url, auth=auth_config, timeout=30.0)

            async with test_client:
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
