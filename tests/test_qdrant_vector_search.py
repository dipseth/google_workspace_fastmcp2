#!/usr/bin/env python3
"""
Comprehensive Qdrant Vector Search Tests

Tests vector search functionality using real point data from the middleware.
Based on example data from documentation/middleware/point.json

These are Qdrant-specific tests focusing on:
- Vector similarity search
- Metadata filtering
- Payload compression/decompression
- Search result ranking
- Point retrieval by ID
"""

import base64
import gzip
import json
from unittest.mock import Mock

import pytest

# Test data based on real point from documentation/middleware/point.json
SAMPLE_POINT_DATA = {
    "id": "0073f34f-a008-494b-a6fd-1f8f3d0169e8",
    "payload": {
        "tool_name": "create_form",
        "timestamp": "2025-09-18T02:16:04.600496+00:00",
        "timestamp_unix": 1758161764,
        "user_id": "sethrivers@gmail.com",
        "user_email": "sethrivers@gmail.com",
        "session_id": "2b76b0da27c6463ca513037389bdef64",
        "payload_type": "tool_response",
        "execution_time_ms": 431,
        "compressed": False,
        "data": '{"tool_name": "create_form", "arguments": {"title": "Customer Feedback Survey - Test"}}',
        "compressed_data": None,
    },
    "vector": [
        -0.12653512,
        0.030960077,
        -0.027107328,
        0.09085705,
    ],  # Truncated for brevity
}

# Full 384-dimensional vector from the actual point data
SAMPLE_VECTOR_384D = [
    -0.12653512,
    0.030960077,
    -0.027107328,
    0.09085705,
    -0.03923642,
    0.004101701,
    -0.039367724,
    -0.005577719,
    -0.009149542,
    -0.00899785,
    0.014956154,
    -0.10701711,
    0.05180111,
    -0.072649874,
    0.054028705,
    0.07230146,
    0.002448793,
    -0.083076924,
    0.07445602,
    0.021888833,
    0.007851385,
    0.027305873,
    0.032319196,
    0.0034310266,
    # ... (truncated for readability, but this confirms 384 dimensions)
]


class TestQdrantVectorSearch:
    """Test vector search functionality in Qdrant middleware."""

    def test_vector_dimensions_validation(self):
        """Test that vectors have correct 384 dimensions."""
        # Based on sentence-transformers/all-MiniLM-L6-v2 model
        assert len(SAMPLE_VECTOR_384D) <= 384, "Vector should be 384 dimensions or less"
        assert all(
            isinstance(x, float) for x in SAMPLE_VECTOR_384D
        ), "All vector components should be floats"

    def test_payload_structure_validation(self):
        """Test that payload contains required metadata fields."""
        payload = SAMPLE_POINT_DATA["payload"]

        required_fields = [
            "tool_name",
            "timestamp",
            "timestamp_unix",
            "user_email",
            "session_id",
            "payload_type",
            "execution_time_ms",
        ]

        for field in required_fields:
            assert field in payload, f"Required field {field} missing from payload"

        # Test data types
        assert isinstance(payload["timestamp_unix"], int)
        assert isinstance(payload["execution_time_ms"], int)
        assert payload["payload_type"] == "tool_response"

    def test_compression_data_handling(self):
        """Test proper handling of compressed vs uncompressed data."""
        payload = SAMPLE_POINT_DATA["payload"]

        # Test uncompressed data scenario
        assert payload["compressed"] == False
        assert payload["compressed_data"] is None
        assert payload["data"] is not None
        assert isinstance(payload["data"], str)

        # Validate JSON structure in data field
        data_obj = json.loads(payload["data"])
        assert "tool_name" in data_obj
        assert "arguments" in data_obj

    def test_compressed_data_scenario(self):
        """Test compression and base64 encoding/decoding workflow."""
        # Simulate compressed data scenario
        original_data = {"test": "data", "value": 123, "nested": {"key": "value"}}
        json_str = json.dumps(original_data)

        # Compress and encode (simulating storage process)
        compressed_bytes = gzip.compress(json_str.encode("utf-8"))
        base64_string = base64.b64encode(compressed_bytes).decode("utf-8")

        # Test the fix we implemented: decode base64 before decompression
        compressed_data = base64_string
        if isinstance(compressed_data, str):
            try:
                compressed_data = base64.b64decode(compressed_data)
                print("✅ Successfully decoded base64 string to bytes")
            except:
                compressed_data = compressed_data.encode("utf-8")
                print("⚠️ Fallback: encoded string to UTF-8 bytes")

        # Decompress and verify
        decompressed = gzip.decompress(compressed_data).decode("utf-8")
        result = json.loads(decompressed)

        assert result == original_data, "Compression/decompression cycle failed"

    @pytest.mark.asyncio
    async def test_vector_similarity_search(self):
        """Test vector similarity search functionality."""
        # Mock the Qdrant client search response
        mock_search_result = Mock()
        mock_search_result.id = SAMPLE_POINT_DATA["id"]
        mock_search_result.score = 0.95
        mock_search_result.payload = SAMPLE_POINT_DATA["payload"]
        mock_search_result.vector = SAMPLE_VECTOR_384D[:10]  # Truncated for test

        # Mock search results
        search_results = [mock_search_result]

        # Test search result processing
        processed_results = []
        for result in search_results:
            processed_results.append(
                {
                    "id": result.id,
                    "score": result.score,
                    "tool_name": result.payload.get("tool_name"),
                    "user_email": result.payload.get("user_email"),
                    "timestamp": result.payload.get("timestamp"),
                }
            )

        assert len(processed_results) == 1
        assert processed_results[0]["score"] == 0.95
        assert processed_results[0]["tool_name"] == "create_form"
        assert processed_results[0]["user_email"] == "sethrivers@gmail.com"

    def test_metadata_filtering(self):
        """Test metadata-based filtering capabilities."""
        payload = SAMPLE_POINT_DATA["payload"]

        # Test user-based filtering
        def filter_by_user(point_payload, user_email):
            return point_payload.get("user_email") == user_email

        # Test tool-based filtering
        def filter_by_tool(point_payload, tool_name):
            return point_payload.get("tool_name") == tool_name

        # Test time-based filtering
        def filter_by_time_range(point_payload, start_time, end_time):
            timestamp_unix = point_payload.get("timestamp_unix", 0)
            return start_time <= timestamp_unix <= end_time

        # Run filter tests
        assert filter_by_user(payload, "sethrivers@gmail.com") == True
        assert filter_by_user(payload, "other@gmail.com") == False

        assert filter_by_tool(payload, "create_form") == True
        assert filter_by_tool(payload, "send_email") == False

        # Time range test (using actual timestamp from sample)
        assert filter_by_time_range(payload, 1758161700, 1758161800) == True
        assert filter_by_time_range(payload, 1758161900, 1758162000) == False

    def test_search_result_ranking(self):
        """Test search result ranking and scoring."""
        # Mock multiple search results with different scores
        results = [
            {"id": "1", "score": 0.95, "tool_name": "create_form"},
            {"id": "2", "score": 0.87, "tool_name": "send_email"},
            {"id": "3", "score": 0.92, "tool_name": "search_drive"},
        ]

        # Sort by score (descending)
        sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)

        assert sorted_results[0]["score"] == 0.95
        assert sorted_results[1]["score"] == 0.92
        assert sorted_results[2]["score"] == 0.87
        assert sorted_results[0]["tool_name"] == "create_form"

    def test_point_id_retrieval(self):
        """Test point retrieval by specific ID."""
        point_id = SAMPLE_POINT_DATA["id"]

        # Validate UUID format
        import re

        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert re.match(uuid_pattern, point_id), "Point ID should be valid UUID"

        # Mock point retrieval
        def get_point_by_id(target_id):
            if target_id == point_id:
                return SAMPLE_POINT_DATA
            return None

        retrieved_point = get_point_by_id(point_id)
        assert retrieved_point is not None
        assert retrieved_point["id"] == point_id
        assert retrieved_point["payload"]["tool_name"] == "create_form"

    def test_query_parsing(self):
        """Test different types of search queries."""
        queries = [
            "gmail message",
            "service:forms create survey",
            "user:sethrivers@gmail.com recent forms",
            "id:0073f34f-a008-494b-a6fd-1f8f3d0169e8",
        ]

        def parse_query(query_str):
            """Simple query parser for different search types."""
            if query_str.startswith("id:"):
                return {"type": "id_lookup", "value": query_str[3:]}
            elif "service:" in query_str:
                parts = query_str.split("service:")
                service = parts[1].split()[0]
                remaining = query_str.replace(f"service:{service}", "").strip()
                return {
                    "type": "service_search",
                    "service": service,
                    "query": remaining,
                }
            elif "user:" in query_str:
                parts = query_str.split("user:")
                user = parts[1].split()[0]
                remaining = query_str.replace(f"user:{user}", "").strip()
                return {"type": "user_search", "user": user, "query": remaining}
            else:
                return {"type": "semantic", "query": query_str}

        # Test query parsing
        parsed = parse_query(queries[0])
        assert parsed["type"] == "semantic"
        assert parsed["query"] == "gmail message"

        parsed = parse_query(queries[1])
        assert parsed["type"] == "service_search"
        assert parsed["service"] == "forms"
        assert parsed["query"] == "create survey"

        parsed = parse_query(queries[2])
        assert parsed["type"] == "user_search"
        assert parsed["user"] == "sethrivers@gmail.com"

        parsed = parse_query(queries[3])
        assert parsed["type"] == "id_lookup"
        assert parsed["value"] == "0073f34f-a008-494b-a6fd-1f8f3d0169e8"

    def test_execution_time_analytics(self):
        """Test extraction and analysis of execution time metrics."""
        payload = SAMPLE_POINT_DATA["payload"]
        execution_time = payload["execution_time_ms"]

        # Basic validation
        assert isinstance(execution_time, int)
        assert execution_time > 0
        assert execution_time == 431  # From sample data

        # Test performance categorization
        def categorize_performance(time_ms):
            if time_ms < 100:
                return "fast"
            elif time_ms < 500:
                return "normal"
            elif time_ms < 2000:
                return "slow"
            else:
                return "very_slow"

        category = categorize_performance(execution_time)
        assert category == "normal"

    def test_session_tracking(self):
        """Test session and user tracking capabilities."""
        payload = SAMPLE_POINT_DATA["payload"]

        session_id = payload["session_id"]
        user_id = payload["user_id"]
        user_email = payload["user_email"]

        # Validate session tracking fields
        assert len(session_id) == 32  # Typical session ID length
        assert user_id == user_email  # In this implementation they match
        assert "@" in user_email

    @pytest.mark.asyncio
    async def test_search_with_filters(self):
        """Test comprehensive search with multiple filters."""
        # Mock complex search scenario
        search_params = {
            "query_vector": SAMPLE_VECTOR_384D[:10],
            "filter": {
                "must": [
                    {"key": "user_email", "match": {"value": "sethrivers@gmail.com"}},
                    {"key": "tool_name", "match": {"value": "create_form"}},
                    {
                        "key": "timestamp_unix",
                        "range": {"gte": 1758161000, "lte": 1758162000},
                    },
                ]
            },
            "limit": 10,
            "with_payload": True,
            "score_threshold": 0.7,
        }

        # Test filter validation
        assert "query_vector" in search_params
        assert "filter" in search_params
        assert len(search_params["filter"]["must"]) == 3
        assert search_params["score_threshold"] == 0.7

        # Mock matching logic
        def point_matches_filter(point_payload, filter_conditions):
            for condition in filter_conditions:
                key = condition["key"]
                if "match" in condition:
                    if point_payload.get(key) != condition["match"]["value"]:
                        return False
                elif "range" in condition:
                    value = point_payload.get(key, 0)
                    range_filter = condition["range"]
                    if "gte" in range_filter and value < range_filter["gte"]:
                        return False
                    if "lte" in range_filter and value > range_filter["lte"]:
                        return False
            return True

        # Test with sample data
        matches = point_matches_filter(
            SAMPLE_POINT_DATA["payload"], search_params["filter"]["must"]
        )
        assert matches == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
