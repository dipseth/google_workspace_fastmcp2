"""Live integration test: API key credential isolation.

Connects to a running server using MCP_API_KEY and verifies that
the API key session CANNOT use credentials from an OAuth-authenticated user
without first running start_google_auth.

Usage:
    # Server must be running on https://localhost:8002
    uv run pytest tests/test_api_key_isolation_live.py -v -s
"""

import os

import httpx
import pytest
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

load_dotenv()

MCP_API_KEY = os.getenv("MCP_API_KEY", "")
SERVER_HOST = os.getenv("SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("SERVER_PORT", "8002")
SERVER_URL = f"https://{SERVER_HOST}:{SERVER_PORT}/mcp"

# Use a known email that has OAuth credentials saved on the server
# (the user who authenticated in the current session)
VICTIM_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_example@gmail.com")


def _make_httpx_factory(**kwargs):
    return httpx.AsyncClient(
        verify=False,
        headers=kwargs.get("headers"),
        timeout=kwargs.get("timeout") or httpx.Timeout(30.0),
        auth=kwargs.get("auth"),
        follow_redirects=kwargs.get("follow_redirects", True),
    )


@pytest.fixture
async def api_key_client():
    """Create a client authenticated only via MCP_API_KEY (no OAuth)."""
    if not MCP_API_KEY:
        pytest.skip("MCP_API_KEY not set")

    transport = StreamableHttpTransport(
        SERVER_URL,
        auth=MCP_API_KEY,
        httpx_client_factory=_make_httpx_factory,
    )
    client = Client(transport=transport)
    async with client:
        yield client


@pytest.mark.asyncio
async def test_api_key_cannot_use_oauth_user_credentials(api_key_client):
    """API key client should be BLOCKED from using another user's stored credentials.

    This tests the credential isolation: even though VICTIM_EMAIL has valid
    credentials saved on the server (from a prior OAuth session), the API key
    client should NOT be able to use them.
    """
    print(f"\n--- Testing credential isolation ---")
    print(f"    Server: {SERVER_URL}")
    print(f"    Auth: MCP_API_KEY")
    print(f"    Target email: {VICTIM_EMAIL}")

    with pytest.raises(ToolError, match="API key sessions can only access"):
        await api_key_client.call_tool(
            "check_drive_auth",
            {"user_google_email": VICTIM_EMAIL},
        )

    print("    PASS: API key client was blocked from using OAuth credentials")


@pytest.mark.asyncio
async def test_api_key_no_oauth_file_fallback(api_key_client):
    """API key client should NOT inherit email from .oauth_authentication.json.

    When no user_google_email is provided, the API key client should NOT
    auto-resolve to the last OAuth-authenticated user.
    """
    print(f"\n--- Testing OAuth file fallback is blocked ---")

    # Without user_google_email, the middleware may auto-inject from OAuth file
    # (for non-API-key sessions) or leave it empty. Either way, the API key
    # session should NOT successfully search Drive using another user's creds.
    with pytest.raises(
        ToolError, match="API key sessions can only access|credential|authenticate"
    ):
        await api_key_client.call_tool(
            "search_drive_files",
            {"query": "test"},
            # Intentionally NOT passing user_google_email
        )

    print("    PASS: No OAuth file fallback for API key session")
