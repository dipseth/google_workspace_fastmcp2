"""
Test Processing of Actual Problematic Data from point.json

This test specifically processes the exact problematic data from
documentation/middleware/point.json to validate that the sanitization fixes
resolve the triple JSON serialization issue and improve search quality.
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from middleware.qdrant_core.config import QdrantConfig
from middleware.qdrant_core.storage import (
    QdrantStorageManager,
    sanitize_for_json,
)


class TestProblematicDataProcessing:
    """Test processing of the actual problematic data from point.json."""

    def load_problematic_point_data(self) -> Dict[str, Any]:
        """Load the actual problematic data from documentation/middleware/point.json."""
        with open("documentation/middleware/point.json", "r") as f:
            return json.load(f)

    def test_point_json_data_sanitization_improvement(self):
        """Test that point.json data is properly sanitized and improved."""

        # Load the actual problematic data
        point_data = self.load_problematic_point_data()

        # Extract the problematic escaped JSON from the payload
        payload_data_str = point_data["payload"]["data"]
        payload_data = json.loads(payload_data_str)

        # Extract the deeply nested escaped JSON response
        response_data = payload_data["response"]
        nested_response = response_data[0]["text"]

        print("\n🔍 Original nested response (first 200 chars):")
        print(f"   {nested_response[:200]}...")

        # Count escape characters in original
        original_escape_count = nested_response.count("\\")
        print(f"📊 Original escape character count: {original_escape_count}")

        # Apply sanitization with structure preservation
        sanitized_response = sanitize_for_json(nested_response, preserve_structure=True)

        print(f"\n🔧 Sanitized response type: {type(sanitized_response)}")

        if isinstance(sanitized_response, dict):
            print("✅ Successfully parsed JSON string to structured data!")
            print(f"   Keys: {list(sanitized_response.keys())}")

            # Verify structure was preserved
            assert "success" in sanitized_response
            assert "message" in sanitized_response
            assert sanitized_response["success"] == False

            # The message should be more readable
            message = sanitized_response["message"]
            print(f"📄 Sanitized message (first 150 chars): {message[:150]}...")

            # Count escapes in the sanitized message
            sanitized_escape_count = message.count("\\")
            print(f"📊 Sanitized message escape count: {sanitized_escape_count}")

            # Should have significantly fewer escape characters
            assert (
                sanitized_escape_count < original_escape_count / 2
            ), f"Expected significant escape reduction: {sanitized_escape_count} < {original_escape_count / 2}"

        else:
            # If still a string, should at least have some improvement
            print("⚠️ Still a string, but checking for improvements...")
            sanitized_str = str(sanitized_response)
            sanitized_escape_count = sanitized_str.count("\\")
            print(f"📊 Sanitized escape count: {sanitized_escape_count}")

            # Should have some improvement
            assert (
                sanitized_escape_count <= original_escape_count
            ), "Sanitization should not increase escape characters"

    def test_embedding_text_quality_comparison(self):
        """Test that embedding text quality improves with the sanitized data."""

        # Load problematic data
        point_data = self.load_problematic_point_data()
        payload_data = json.loads(point_data["payload"]["data"])

        # Extract original and sanitized versions
        original_response = payload_data["response"][0]["text"]
        sanitized_response = sanitize_for_json(
            original_response, preserve_structure=True
        )

        # Generate embedding text for both versions (simulating what Qdrant storage does)
        def generate_embedding_text(tool_name, args, response):
            return f"Tool: {tool_name}\nArguments: {json.dumps(args)}\nResponse: {str(response)[:1000]}"

        tool_name = payload_data["tool_name"]
        tool_args = payload_data["arguments"]

        original_embed_text = generate_embedding_text(
            tool_name, tool_args, original_response
        )
        sanitized_embed_text = generate_embedding_text(
            tool_name, tool_args, sanitized_response
        )

        print(f"\n📏 Original embedding text length: {len(original_embed_text)}")
        print(f"📏 Sanitized embedding text length: {len(sanitized_embed_text)}")

        # Analyze escape character reduction
        original_escapes = original_embed_text.count("\\")
        sanitized_escapes = sanitized_embed_text.count("\\")

        print(
            f"📊 Embedding text escape reduction: {original_escapes} → {sanitized_escapes}"
        )

        # Should have fewer escape characters
        assert (
            sanitized_escapes < original_escapes
        ), f"Expected escape reduction in embedding text: {sanitized_escapes} < {original_escapes}"

        # Should contain meaningful content
        assert "create_form" in sanitized_embed_text
        assert "Failed to create form" in sanitized_embed_text

        # Should not have triple-escaped quotes
        assert (
            '\\\\"' not in sanitized_embed_text
        ), "Should not have triple-escaped quotes"

    @pytest.mark.asyncio
    async def test_full_pipeline_processing_with_problematic_data(self):
        """Test the complete storage pipeline with the actual problematic data."""

        # Create mock storage manager
        config = QdrantConfig(
            host="localhost", ports=[6333], collection_name="test_problematic_data"
        )

        mock_client_manager = MagicMock()
        mock_client_manager.config = config
        mock_client_manager.client = MagicMock()
        mock_client_manager.embedder = MagicMock()
        mock_client_manager.embedder.encode = MagicMock(return_value=MagicMock())
        mock_client_manager.embedder.encode.return_value.tolist = MagicMock(
            return_value=[0.1] * 384
        )
        mock_client_manager.is_available = True
        mock_client_manager.is_initialized = True
        mock_client_manager._should_compress = MagicMock(return_value=False)

        storage_manager = QdrantStorageManager(mock_client_manager)

        # Load and process the problematic data
        point_data = self.load_problematic_point_data()
        payload_data = json.loads(point_data["payload"]["data"])

        # Store using the fixed pipeline
        await storage_manager._store_response_with_params(
            tool_name=payload_data["tool_name"],
            tool_args=payload_data["arguments"],
            response=payload_data[
                "response"
            ],  # This contains the problematic nested JSON
            execution_time_ms=payload_data.get("execution_time_ms", 431),
            session_id=payload_data.get("session_id", "test_session"),
            user_email=payload_data.get("user_email", "test@example.com"),
        )

        # Verify the storage was attempted
        mock_client_manager.client.upsert.assert_called_once()

        # Extract the stored point data
        call_args = mock_client_manager.client.upsert.call_args
        stored_points = call_args[1]["points"]
        stored_point = stored_points[0]
        stored_payload = stored_point.payload

        print("\n✅ Successfully processed problematic data through fixed pipeline!")
        print(f"📦 Stored payload keys: {list(stored_payload.keys())}")

        # Verify improved data structure
        if "response_data" in stored_payload:
            response_data = stored_payload["response_data"]
            if isinstance(response_data, dict) and "response" in response_data:
                stored_response = response_data["response"][0]
                stored_text = stored_response.get("text", "")

                print(f"📄 Stored response type: {type(stored_text)}")

                if isinstance(stored_text, dict):
                    print("🎉 SUCCESS: Nested JSON was parsed to structured data!")
                    assert "success" in stored_text
                    assert "message" in stored_text
                else:
                    print("ℹ️ Response stored as string (acceptable fallback)")
                    assert len(str(stored_text)) > 0

    def test_search_quality_metrics_improvement(self):
        """Test concrete search quality metrics improvement."""

        # Load problematic data
        point_data = self.load_problematic_point_data()
        payload_data = json.loads(point_data["payload"]["data"])
        original_response = payload_data["response"][0]["text"]

        # Process with sanitization
        sanitized_response = sanitize_for_json(
            original_response, preserve_structure=True
        )

        # Define search queries that should match this content
        test_queries = [
            "form creation error",
            "API validation failed",
            "HttpError 400",
            "batchUpdate required",
            "Google Forms API",
        ]

        # Simple relevance scoring
        def calculate_relevance(query, content):
            content_str = str(content).lower()
            query_words = query.lower().split()
            score = sum(1 for word in query_words if word in content_str)
            return score

        print("\n📊 Search Quality Comparison:")
        print(f"{'Query':<25} {'Original':<10} {'Sanitized':<10} {'Improvement':<12}")
        print("-" * 60)

        total_original_score = 0
        total_sanitized_score = 0

        for query in test_queries:
            original_score = calculate_relevance(query, original_response)
            sanitized_score = calculate_relevance(query, sanitized_response)
            improvement = sanitized_score - original_score

            print(
                f"{query:<25} {original_score:<10} {sanitized_score:<10} {improvement:>+3}"
            )

            total_original_score += original_score
            total_sanitized_score += sanitized_score

        print("-" * 60)
        print(
            f"{'TOTAL':<25} {total_original_score:<10} {total_sanitized_score:<10} {total_sanitized_score - total_original_score:>+3}"
        )

        # Sanitized version should have equal or better search relevance
        assert (
            total_sanitized_score >= total_original_score
        ), f"Expected search quality improvement: {total_sanitized_score} >= {total_original_score}"

    def test_storage_efficiency_metrics(self):
        """Test storage efficiency improvements."""

        # Load problematic data
        point_data = self.load_problematic_point_data()
        original_data_str = point_data["payload"]["data"]

        # Parse and re-sanitize
        payload_data = json.loads(original_data_str)
        sanitized_payload = sanitize_for_json(payload_data, preserve_structure=True)
        sanitized_data_str = json.dumps(sanitized_payload, default=str)

        # Compare storage efficiency
        original_size = len(original_data_str)
        sanitized_size = len(sanitized_data_str)

        print("\n💾 Storage Efficiency Comparison:")
        print(f"   Original size: {original_size:,} bytes")
        print(f"   Sanitized size: {sanitized_size:,} bytes")
        print(f"   Size difference: {sanitized_size - original_size:+,} bytes")
        print(f"   Efficiency ratio: {sanitized_size / original_size:.3f}")

        # Sanitized should be more or equally efficient
        size_ratio = sanitized_size / original_size
        assert (
            size_ratio <= 1.1
        ), f"Sanitized data should not be significantly larger: {size_ratio:.3f} <= 1.1"

        # Count escape characters as a measure of "cleanliness"
        original_escapes = original_data_str.count("\\")
        sanitized_escapes = sanitized_data_str.count("\\")

        print(f"   Original escape chars: {original_escapes}")
        print(f"   Sanitized escape chars: {sanitized_escapes}")
        print(
            f"   Escape reduction: {((original_escapes - sanitized_escapes) / original_escapes * 100):.1f}%"
        )

        # Should have fewer escape characters (cleaner data)
        assert (
            sanitized_escapes <= original_escapes
        ), "Sanitization should not increase escape characters"


if __name__ == "__main__":
    # Run the test suite
    pytest.main([__file__, "-v", "-s"])
