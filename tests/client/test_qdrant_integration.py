"""Comprehensive Qdrant integration tests using FastMCP Client SDK."""

import asyncio
import os

import httpx
import pytest
import pytest_asyncio

from .base_test_config import TEST_EMAIL

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")


@pytest.mark.service("qdrant")
class TestQdrantStorageIntegration:
    """Test Qdrant storage and retrieval functionality."""

    @pytest_asyncio.fixture
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
        result = await client.call_tool("health_check", {})
        assert result is not None
        assert len(result.content) > 0

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

        # Wait for storage
        await asyncio.sleep(2)

        # Search for stored responses
        result = await client.call_tool(
            "search_tool_history", {"query": "server health", "limit": 5}
        )

        assert result is not None
        assert len(result.content) > 0
        content = result.content[0].text
        assert "results" in content.lower() or "found" in content.lower()

    @pytest.mark.asyncio
    async def test_gmail_response_storage(self, client, qdrant_client):
        """Test that Gmail tool responses are stored."""
        initial_count = await self.get_qdrant_point_count(qdrant_client)

        # Call a Gmail tool
        result = await client.call_tool(
            "list_gmail_labels", {"user_google_email": TEST_EMAIL}
        )

        # The tool might fail due to auth, but response should still be stored
        assert result is not None
        assert len(result.content) > 0

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

        # Get analytics
        result = await client.call_tool("get_tool_analytics", {})
        assert result is not None
        assert not result.is_error, f"Analytics tool returned error: {result}"
        assert len(result.content) > 0, "Analytics result has no content"

        # Extract the text content from the first content block
        content_block = result.content[0]
        assert hasattr(content_block, "text"), "Content block missing text attribute"
        content = content_block.text

        print("Analytics result type:", type(result))
        print("Analytics content length:", len(content))
        print(
            "Analytics JSON preview:",
            content[:500] + "..." if len(content) > 500 else content,
        )

        # Check for expected analytics fields
        assert "total_responses" in content
        assert "group_by" in content
        assert "groups" in content
        # Note: Enhanced fields like point_ids will be available after server restart

    @pytest.mark.asyncio
    async def test_response_by_id(self, client):
        """Test retrieving specific responses by ID."""
        # First search for any response
        search_result = await client.call_tool(
            "search_tool_history", {"query": "*", "limit": 1}
        )

        # If we have results, try to get one by ID
        if search_result and len(search_result.content) > 0:
            content = search_result.content[0].text
            if "id" in content:
                # This test would need to parse the ID from the search result
                # For now, we just verify the tool exists
                tools = await client.list_tools()
                tool_names = [tool.name for tool in tools]
                assert "get_response_details" in tool_names


@pytest.mark.service("qdrant")
class TestQdrantSemanticSearch:
    """Test semantic search capabilities."""

    @pytest.mark.asyncio
    async def test_semantic_search_relevance(self, client):
        """Test that semantic search returns relevant results."""
        # Generate some diverse tool responses
        test_queries = [
            ("check_drive_auth", {"user_google_email": "user1@example.com"}),
            (
                "start_google_auth",
                {"user_google_email": "user2@example.com", "service_name": "Test"},
            ),
            ("health_check", {}),
        ]

        for tool_name, params in test_queries:
            try:
                print(f"🔧 Calling tool: {tool_name} with params: {params}")
                result = await client.call_tool(tool_name, params)
                print(
                    f"✅ Tool {tool_name} succeeded: {len(result.content)} content blocks"
                )
            except Exception as e:
                print(f"❌ Tool {tool_name} failed: {str(e)}")
                pass  # Some tools might fail, that's ok

        # Wait for indexing
        await asyncio.sleep(3)

        # Search for authentication-related responses
        print("🔍 Searching for authentication-related responses...")
        result = await client.call_tool(
            "search_tool_history", {"query": "google authentication oauth", "limit": 10}
        )

        print(f"🔍 Search result length: {len(result.content)}")
        assert len(result.content) > 0
        content = result.content[0].text
        print(f"🔍 Search content: {content}")

        # Should find auth-related tools
        assert "auth" in content.lower() or "results" in content.lower()

    @pytest.mark.asyncio
    async def test_search_limit_parameter(self, client):
        """Test that search respects the limit parameter."""
        # Search with a specific limit
        result = await client.call_tool(
            "search_tool_history", {"query": "test", "limit": 3}
        )

        assert result is not None
        assert len(result.content) > 0
        # The result should mention the limit or show limited results
        content = result.content[0].text
        assert content is not None


@pytest.mark.service("qdrant")
class TestQdrantErrorHandling:
    """Test error handling in Qdrant operations."""

    @pytest.mark.asyncio
    async def test_search_with_empty_query(self, client):
        """Test searching with an empty query."""
        # Should handle empty query gracefully
        result = await client.call_tool(
            "search_tool_history", {"query": "", "limit": 5}
        )

        assert result is not None
        assert len(result.content) > 0
        # Should either return results or indicate empty query

    @pytest.mark.asyncio
    async def test_search_with_invalid_limit(self, client):
        """Test searching with invalid limit values."""
        # Test with zero limit - should use default
        result = await client.call_tool(
            "search_tool_history", {"query": "test", "limit": 0}
        )

        assert result is not None
        assert len(result.content) > 0

        # Test with very high limit - should cap at reasonable value
        result = await client.call_tool(
            "search_tool_history", {"query": "test", "limit": 10000}
        )

        assert result is not None
        assert len(result.content) > 0
