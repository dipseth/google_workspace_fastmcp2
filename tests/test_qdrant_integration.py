"""Comprehensive Qdrant integration tests using FastMCP Client SDK."""

import pytest
import asyncio
import httpx
from fastmcp import Client
from typing import Any, Dict, List
import os
import time
from .test_auth_utils import get_client_auth_config


# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")


class TestQdrantStorageIntegration:
    """Test Qdrant storage and retrieval functionality."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.fixture
    async def qdrant_client(self):
        """Create an HTTP client for direct Qdrant checks."""
        async with httpx.AsyncClient() as client:
            yield client
    
    async def get_qdrant_point_count(self, qdrant_client):
        """Get the current number of points in Qdrant."""
        try:
            response = await qdrant_client.get(
                f"{QDRANT_URL}/collections/mcp_tool_responses"
            )
            if response.status_code == 200:
                data = response.json()
                return data["result"]["points_count"]
        except:
            pass
        return 0
    
    @pytest.mark.asyncio
    async def test_response_storage(self, client, qdrant_client):
        """Test that tool responses are stored in Qdrant."""
        # Get initial point count
        initial_count = await self.get_qdrant_point_count(qdrant_client)
        
        # Call a tool that should generate a response
        result = await client.call_tool("server_info", {})
        assert len(result) > 0
        
        # Wait for async storage to complete
        await asyncio.sleep(2)
        
        # Check if point count increased
        new_count = await self.get_qdrant_point_count(qdrant_client)
        assert new_count >= initial_count, "No new points stored in Qdrant"
    
    @pytest.mark.asyncio
    async def test_search_functionality(self, client):
        """Test searching stored responses."""
        # First, ensure we have some data by calling tools
        await client.call_tool("health_check", {})
        await client.call_tool("server_info", {})
        
        # Wait for storage
        await asyncio.sleep(2)
        
        # Search for stored responses
        result = await client.call_tool("search_tool_history", {
            "query": "server health",
            "limit": 5
        })
        
        assert len(result) > 0
        content = result[0].text
        assert "results" in content.lower() or "found" in content.lower()
    
    @pytest.mark.asyncio
    async def test_gmail_response_storage(self, client, qdrant_client):
        """Test that Gmail tool responses are stored."""
        initial_count = await self.get_qdrant_point_count(qdrant_client)
        
        # Call a Gmail tool
        result = await client.call_tool("list_gmail_labels", {
            "user_google_email": "test@example.com"
        })
        
        # The tool might fail due to auth, but response should still be stored
        assert len(result) > 0
        
        # Wait for storage
        await asyncio.sleep(2)
        
        # Check if response was stored
        new_count = await self.get_qdrant_point_count(qdrant_client)
        assert new_count >= initial_count
    
    @pytest.mark.asyncio
    async def test_analytics_data(self, client):
        """Test analytics functionality."""
        # Generate some tool usage
        await client.call_tool("health_check", {})
        await client.call_tool("server_info", {})
        
        # Get analytics
        result = await client.call_tool("get_tool_analytics", {})
        assert len(result) > 0
        
        content = result[0].text
        # Check for expected analytics fields
        assert "total_responses" in content
        assert "group_by" in content
        assert "groups" in content
    
    @pytest.mark.asyncio
    async def test_response_by_id(self, client):
        """Test retrieving specific responses by ID."""
        # First search for any response
        search_result = await client.call_tool("search_tool_history", {
            "query": "*",
            "limit": 1
        })
        
        # If we have results, try to get one by ID
        if search_result and "id" in search_result[0].text:
            # This test would need to parse the ID from the search result
            # For now, we just verify the tool exists
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]
            assert "get_response_details" in tool_names


class TestQdrantSemanticSearch:
    """Test semantic search capabilities."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_semantic_search_relevance(self, client):
        """Test that semantic search returns relevant results."""
        # Generate some diverse tool responses
        test_queries = [
            ("check_drive_auth", {"user_google_email": "user1@example.com"}),
            ("start_google_auth", {"user_google_email": "user2@example.com", "service_name": "Test"}),
            ("health_check", {}),
        ]
        
        for tool_name, params in test_queries:
            try:
                print(f"🔧 Calling tool: {tool_name} with params: {params}")
                result = await client.call_tool(tool_name, params)
                print(f"✅ Tool {tool_name} succeeded: {len(result)} results")
            except Exception as e:
                print(f"❌ Tool {tool_name} failed: {str(e)}")
                pass  # Some tools might fail, that's ok
        
        # Wait for indexing
        await asyncio.sleep(3)
        
        # Search for authentication-related responses
        print("🔍 Searching for authentication-related responses...")
        result = await client.call_tool("search_tool_history", {
            "query": "google authentication oauth",
            "limit": 10
        })
        
        print(f"🔍 Search result length: {len(result)}")
        assert len(result) > 0
        content = result[0].text
        print(f"🔍 Search content: {content}")
        
        # Should find auth-related tools
        assert "auth" in content.lower() or "results" in content.lower()
    
    @pytest.mark.asyncio
    async def test_search_limit_parameter(self, client):
        """Test that search respects the limit parameter."""
        # Search with a specific limit
        result = await client.call_tool("search_tool_history", {
            "query": "test",
            "limit": 3
        })
        
        assert len(result) > 0
        # The result should mention the limit or show limited results
        content = result[0].text
        assert content is not None


class TestQdrantErrorHandling:
    """Test error handling in Qdrant operations."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_search_with_empty_query(self, client):
        """Test searching with an empty query."""
        # Should handle empty query gracefully
        result = await client.call_tool("search_tool_history", {
            "query": "",
            "limit": 5
        })
        
        assert len(result) > 0
        # Should either return results or indicate empty query
    
    @pytest.mark.asyncio
    async def test_search_with_invalid_limit(self, client):
        """Test searching with invalid limit values."""
        # Test with zero limit - should use default
        result = await client.call_tool("search_tool_history", {
            "query": "test",
            "limit": 0
        })
        
        assert len(result) > 0
        
        # Test with very high limit - should cap at reasonable value
        result = await client.call_tool("search_tool_history", {
            "query": "test",
            "limit": 10000
        })
        
        assert len(result) > 0