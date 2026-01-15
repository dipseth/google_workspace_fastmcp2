#!/usr/bin/env python3
"""
Test script to diagnose and fix Qdrant search issues.
"""

import logging

from fastembed import TextEmbedding
from qdrant_client import QdrantClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_qdrant_search():
    """Test different search methods to find the working one."""

    # Initialize client
    client = QdrantClient(host="localhost", port=6333)
    collection_name = "card_framework_components_fastembed"

    # Check collection info
    collection_info = client.get_collection(collection_name)
    logger.info(f"Collection info: {collection_info}")
    logger.info(f"Points count: {collection_info.points_count}")

    # Initialize embedder
    embedder = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

    # Generate a test query embedding
    query = "send card message"
    embedding_list = list(embedder.embed([query]))
    query_embedding = embedding_list[0] if embedding_list else None

    if query_embedding is None:
        logger.error("Failed to generate embedding")
        return

    # Convert to list
    if hasattr(query_embedding, "tolist"):
        query_vector = query_embedding.tolist()
    else:
        query_vector = list(query_embedding)

    logger.info(f"Query vector dimension: {len(query_vector)}")

    # Test 1: Try the old search method
    logger.info("\n=== Test 1: Using client.search() ===")
    try:
        search_results = client.search(
            collection_name=collection_name, query_vector=query_vector, limit=5
        )
        logger.info(f"Search results type: {type(search_results)}")
        logger.info(f"Number of results: {len(search_results)}")

        for i, result in enumerate(search_results[:3]):
            logger.info(f"Result {i+1}:")
            logger.info(f"  Score: {result.score}")
            if hasattr(result, "payload"):
                payload = result.payload
                if isinstance(payload, dict):
                    logger.info(f"  Name: {payload.get('name', 'N/A')}")
                    logger.info(f"  Path: {payload.get('full_path', 'N/A')}")
    except Exception as e:
        logger.error(f"client.search() failed: {e}")

    # Test 2: Try query_points with different parameters
    logger.info("\n=== Test 2: Using client.query_points() ===")
    try:
        # Try with 'query' parameter
        search_results = client.query_points(
            collection_name=collection_name, query=query_vector, limit=5
        )
        logger.info(f"QueryResponse type: {type(search_results)}")

        if hasattr(search_results, "points"):
            points = search_results.points
            logger.info(f"Number of points: {len(points)}")

            for i, result in enumerate(points[:3]):
                logger.info(f"Result {i+1}:")
                logger.info(f"  Score: {getattr(result, 'score', 'N/A')}")
                payload = getattr(result, "payload", {})
                if isinstance(payload, dict):
                    logger.info(f"  Name: {payload.get('name', 'N/A')}")
                    logger.info(f"  Path: {payload.get('full_path', 'N/A')}")
        else:
            logger.warning("QueryResponse has no 'points' attribute")
    except Exception as e:
        logger.error(f"client.query_points() failed: {e}")

    # Test 3: Try scrolling through points to verify they exist
    logger.info("\n=== Test 3: Scrolling through points ===")
    try:
        scroll_results = client.scroll(
            collection_name=collection_name,
            limit=5,
            with_payload=True,
            with_vectors=False,
        )
        points, next_page_offset = scroll_results
        logger.info(f"Scrolled {len(points)} points")

        for i, point in enumerate(points[:3]):
            logger.info(f"Point {i+1}:")
            logger.info(f"  ID: {point.id}")
            if hasattr(point, "payload"):
                payload = point.payload
                if isinstance(payload, dict):
                    logger.info(f"  Name: {payload.get('name', 'N/A')}")
                    logger.info(f"  Path: {payload.get('full_path', 'N/A')}")
    except Exception as e:
        logger.error(f"client.scroll() failed: {e}")

    # Test 4: Get a specific point by ID to verify structure
    logger.info("\n=== Test 4: Getting specific point ===")
    try:
        # Get the first point ID from scroll
        scroll_results = client.scroll(
            collection_name=collection_name,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        points, _ = scroll_results
        if points:
            point_id = points[0].id
            logger.info(f"Getting point with ID: {point_id}")

            retrieved_points = client.retrieve(
                collection_name=collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )

            if retrieved_points:
                point = retrieved_points[0]
                logger.info(f"Retrieved point ID: {point.id}")
                if hasattr(point, "payload"):
                    payload = point.payload
                    if isinstance(payload, dict):
                        logger.info(f"  Name: {payload.get('name', 'N/A')}")
                        logger.info(f"  Path: {payload.get('full_path', 'N/A')}")
                        logger.info(f"  Type: {payload.get('type', 'N/A')}")
    except Exception as e:
        logger.error(f"Point retrieval failed: {e}")


if __name__ == "__main__":
    test_qdrant_search()
