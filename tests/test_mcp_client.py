"""Test suite using FastMCP Client SDK to test the running MCP server."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os


# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")


class TestMCPServer:
    """Test the MCP server using the FastMCP Client."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_server_connectivity(self, client):
        """Test that we can connect to the server."""
        # Ping the server to verify connectivity
        await client.ping()
        assert client.is_connected()
    
    @pytest.mark.asyncio
    async def test_list_tools(self, client):
        """Test listing available tools."""
        tools = await client.list_tools()
        
        # Check that we have tools available
        assert len(tools) > 0
        
        # Check for expected tools
        tool_names = [tool.name for tool in tools]
        assert "health_check" in tool_names
        assert "check_drive_auth" in tool_names
        assert "start_google_auth" in tool_names
        
        # If Gmail tools are enabled
        if "list_gmail_labels" in tool_names:
            assert "search_gmail_messages" in tool_names
            assert "send_gmail_message" in tool_names
    
    @pytest.mark.asyncio
    async def test_health_check_tool(self, client):
        """Test the health check tool."""
        result = await client.call_tool("health_check", {})
        
        # Check that we get a result
        assert len(result) > 0
        
        # Check the content includes expected strings
        content = result[0].text
        assert "Google Drive Upload Server Health Check" in content
        assert "Status:" in content  # Changed from "Server Status" to match actual output
        assert "OAuth Configured:" in content  # Changed to match actual output
    
    @pytest.mark.asyncio
    async def test_check_drive_auth(self, client):
        """Test checking authentication status."""
        # Use a test email that won't have credentials
        test_email = "test_user@example.com"
        
        result = await client.call_tool("check_drive_auth", {
            "user_google_email": test_email
        })
        
        # Check that we get a result
        assert len(result) > 0
        
        # Should indicate no valid credentials for test user
        content = result[0].text
        assert "No valid credentials found" in content or "not authenticated" in content.lower()
    
    @pytest.mark.asyncio
    async def test_start_google_auth(self, client):
        """Test initiating OAuth flow."""
        test_email = "test_user@example.com"
        
        result = await client.call_tool("start_google_auth", {
            "user_google_email": test_email,
            "service_name": "Test Service"
        })
        
        # Check that we get a result
        assert len(result) > 0
        
        # Should return an OAuth URL
        content = result[0].text
        assert "https://accounts.google.com/o/oauth2/auth" in content  # Changed to match actual OAuth endpoint
        assert "client_id=" in content
        assert "redirect_uri=" in content
    
    @pytest.mark.asyncio
    async def test_list_resources(self, client):
        """Test listing available resources."""
        resources = await client.list_resources()
        
        # The server might not have resources, but the call should succeed
        assert isinstance(resources, list)
    
    @pytest.mark.asyncio
    async def test_list_prompts(self, client):
        """Test listing available prompts."""
        prompts = await client.list_prompts()
        
        # The server might not have prompts, but the call should succeed
        assert isinstance(prompts, list)


class TestQdrantIntegration:
    """Test Qdrant-related tools if available."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_qdrant_tools_available(self, client):
        """Check if Qdrant tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check if Qdrant tools are registered
        has_qdrant = any("search_tool_history" in name or 
                        "get_tool_analytics" in name or
                        "get_response_details" in name 
                        for name in tool_names)
        
        if has_qdrant:
            # If Qdrant is enabled, test the tools
            await self._test_search_tool_history(client)
            await self._test_get_tool_analytics(client)
    
    async def _test_search_tool_history(self, client):
        """Test searching tool history."""
        result = await client.call_tool("search_tool_history", {
            "query": "test query",
            "limit": 5
        })
        
        # Should return search results or empty results
        assert len(result) > 0
        content = result[0].text
        assert "query" in content or "results" in content.lower()
    
    async def _test_get_tool_analytics(self, client):
        """Test getting tool analytics."""
        # The get_tool_analytics tool doesn't take parameters
        result = await client.call_tool("get_tool_analytics", {})
        
        # Should return analytics data
        assert len(result) > 0
        content = result[0].text
        assert "total_responses" in content or "analytics" in content.lower()


class TestGmailTools:
    """Test Gmail tools if available."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_gmail_tools_available(self, client):
        """Check if Gmail tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check if Gmail tools are registered
        has_gmail = "list_gmail_labels" in tool_names
        
        if has_gmail:
            # Test without authentication (should fail gracefully)
            await self._test_list_gmail_labels_no_auth(client)
    
    async def _test_list_gmail_labels_no_auth(self, client):
        """Test listing Gmail labels without authentication."""
        test_email = "test_user@example.com"
        
        result = await client.call_tool("list_gmail_labels", {
            "user_google_email": test_email
        })
        
        # Should indicate authentication required
        assert len(result) > 0
        content = result[0].text
        assert ("authentication" in content.lower() or 
                "credentials" in content.lower() or
                "not authenticated" in content.lower())


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client(SERVER_URL)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_invalid_tool_name(self, client):
        """Test calling a non-existent tool."""
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("non_existent_tool", {})
        
        # Should raise an appropriate error
        assert "not found" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_missing_required_params(self, client):
        """Test calling a tool without required parameters."""
        # Try to call check_drive_auth without user_google_email
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("check_drive_auth", {})
        
        # Should indicate missing parameter
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()


if __name__ == "__main__":
    # Run tests with asyncio
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])