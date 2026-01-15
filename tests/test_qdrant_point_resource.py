#!/usr/bin/env python3
"""
Test Qdrant Point Resource Access

Tests the qdrant://collection/{collection}/{point_id} resource URI pattern
to ensure point data can be retrieved successfully.
"""

import asyncio
import os

import pytest
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Load environment variables
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "").rstrip(".")
QDRANT_KEY = os.getenv("QDRANT_KEY", "")


@pytest.mark.asyncio
async def test_direct_point_retrieval():
    """Test direct retrieval of a point from Qdrant to verify connectivity."""

    if not QDRANT_URL or not QDRANT_KEY:
        pytest.skip("QDRANT_URL or QDRANT_KEY not configured")

    # Create client
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY, timeout=10)

    # Get collections
    collections = await asyncio.to_thread(client.get_collections)
    collection_names = [c.name for c in collections.collections]

    print(f"Available collections: {collection_names}")
    assert "mcp_tool_responses" in collection_names

    # Try to retrieve a specific point (from the error message)
    point_id = "88fc2b49-0e61-4617-a9cb-02812375394a"

    points = await asyncio.to_thread(
        client.retrieve,
        collection_name="mcp_tool_responses",
        ids=[point_id],
        with_payload=True,
        with_vectors=False,
    )

    print(f"Retrieved {len(points)} point(s)")

    if points:
        point = points[0]
        print(f"Point ID: {point.id}")
        print(f"Payload keys: {list(point.payload.keys()) if point.payload else []}")

        if point.payload:
            print(f"Tool name: {point.payload.get('tool_name')}")
            print(f"User email: {point.payload.get('user_email')}")
            print(f"Timestamp: {point.payload.get('timestamp')}")
    else:
        print(f"Point {point_id} not found in collection")

    assert len(points) > 0, f"Point {point_id} should exist"


@pytest.mark.asyncio
async def test_resource_handler_point_retrieval():
    """Test point retrieval through the resource handler."""

    if not QDRANT_URL or not QDRANT_KEY:
        pytest.skip("QDRANT_URL or QDRANT_KEY not configured")

    # Import resource handler components
    from middleware.qdrant_core.client import QdrantClientManager
    from middleware.qdrant_core.config import QdrantConfig
    from middleware.qdrant_core.resource_handler import QdrantResourceHandler
    from middleware.qdrant_core.search import QdrantSearchManager

    # Create config
    config = QdrantConfig(enabled=True, collection_name="mcp_tool_responses")

    # Create managers
    client_manager = QdrantClientManager(
        config=config,
        qdrant_url=QDRANT_URL,
        qdrant_api_key=QDRANT_KEY,
        auto_discovery=False,
    )

    # Initialize
    await client_manager.initialize()

    assert client_manager.is_available, "Client should be available"

    # Create search and resource managers
    search_manager = QdrantSearchManager(client_manager)
    resource_handler = QdrantResourceHandler(client_manager, search_manager)

    # Test point retrieval
    point_id = "88fc2b49-0e61-4617-a9cb-02812375394a"
    uri = f"qdrant://collection/mcp_tool_responses/{point_id}"

    result = await resource_handler.handle_qdrant_resource(uri)

    print(f"Resource handler result type: {type(result)}")
    print(f"Result: {result}")

    # Check if result is a Pydantic model
    from middleware.qdrant_types import QdrantPointDetailsResponse

    assert isinstance(result, QdrantPointDetailsResponse)

    # Verify point data
    assert result.qdrant_enabled == True
    assert result.collection_name == "mcp_tool_responses"
    assert result.point_id == point_id
    assert result.point_exists == True

    if result.response_data:
        print(f"Response data available: {type(result.response_data)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
