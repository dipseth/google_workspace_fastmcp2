#!/usr/bin/env python3
"""
Feedback Loop Boost Demonstration

This test shows how positive feedback on cards affects future Qdrant queries.
When you rate a card positively, it stores an instance_pattern with a
description_colbert embedding that boosts similar future queries.

Run with: CARD_COLLECTION=mcp_gchat_cards_v6 uv run python tests/test_feedback_boost_demo.py
"""

import os
import sys

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from config.settings import settings as _settings


def show_collection_stats():
    """Show current collection statistics."""
    print("\n" + "=" * 70)
    print("COLLECTION STATISTICS")
    print("=" * 70)

    from config.qdrant_client import get_qdrant_client
    from qdrant_client import models

    client = get_qdrant_client()
    collection = _settings.card_collection

    info = client.get_collection(collection)
    print(f"\nCollection: {collection}")
    print(f"Total points: {info.points_count}")

    # Count by type
    types_to_check = ["class", "function", "variable", "instance_pattern", "template"]
    print("\nPoints by type:")

    for point_type in types_to_check:
        try:
            count = client.count(
                collection_name=collection,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value=point_type),
                        )
                    ]
                ),
            ).count
            if count > 0:
                print(f"   {point_type}: {count}")
        except Exception:
            pass

    # Count positive feedback patterns
    positive_count = client.count(
        collection_name=collection,
        count_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value="instance_pattern"),
                ),
                models.FieldCondition(
                    key="feedback",
                    match=models.MatchValue(value="positive"),
                ),
            ]
        ),
    ).count
    print(f"\nPositive feedback patterns: {positive_count}")


def show_recent_patterns():
    """Show the most recent instance_patterns with feedback."""
    print("\n" + "=" * 70)
    print("RECENT FEEDBACK PATTERNS")
    print("=" * 70)

    from config.qdrant_client import get_qdrant_client
    from qdrant_client import models

    client = get_qdrant_client()
    collection = _settings.card_collection

    # Get recent instance_patterns
    results, _ = client.scroll(
        collection_name=collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value="instance_pattern"),
                )
            ]
        ),
        limit=10,
        with_payload=True,
    )

    if not results:
        print("\nNo instance_patterns found yet.")
        return

    print(f"\nFound {len(results)} instance_patterns:\n")
    for i, point in enumerate(results, 1):
        payload = point.payload
        desc = payload.get("card_description", "N/A")[:60]
        feedback = payload.get("feedback", "pending")
        pos_count = payload.get("positive_count", 0)
        neg_count = payload.get("negative_count", 0)
        point_type = payload.get("type", "unknown")

        emoji = "👍" if feedback == "positive" else "👎" if feedback == "negative" else "⏳"
        print(f"   {i}. {emoji} [{point_type}] \"{desc}...\"")
        print(f"      Feedback: {feedback} | +{pos_count} / -{neg_count}")
        print()


def query_with_feedback_comparison(test_queries):
    """
    Compare query results with and without feedback boosting.

    This demonstrates how the hybrid query (prefetch + RRF fusion)
    boosts results that have positive feedback.
    """
    print("\n" + "=" * 70)
    print("FEEDBACK BOOST COMPARISON")
    print("=" * 70)

    from gchat.feedback_loop import get_feedback_loop

    feedback_loop = get_feedback_loop()

    for query in test_queries:
        print(f"\n{'─' * 60}")
        print(f"Query: \"{query}\"")
        print("─" * 60)

        # Get proven params (this uses description_colbert search)
        proven = feedback_loop.get_proven_params_for_description(
            description=query,
            min_score=0.3,
        )

        if proven:
            print("\n✅ FOUND MATCHING PATTERN (feedback-boosted):")
            for key, value in proven.items():
                value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                print(f"      {key}: {value_str}")
        else:
            print("\n⚠️ No matching pattern found (score below threshold)")

        # Also show hybrid query results
        print("\n📊 Hybrid Query Results (component + pattern search):")
        # query_with_feedback takes (component_query, description)
        class_results, pattern_results = feedback_loop.query_with_feedback(
            component_query="card widget",  # Generic component search
            description=query,
            limit=5
        )

        if pattern_results:
            print("   Pattern matches (feedback-boosted):")
            for i, result in enumerate(pattern_results[:3], 1):
                name = result.get("name", "unknown")
                point_type = result.get("type", "unknown")
                feedback = result.get("feedback", "-")
                score = result.get("score", 0)

                feedback_emoji = "👍" if feedback == "positive" else ""
                print(f"      {i}. 📝 {name[:40]}... - score: {score:.3f} {feedback_emoji}")
        else:
            print("   No pattern matches")

        if class_results:
            print("   Component matches:")
            for i, result in enumerate(class_results[:2], 1):
                name = result.get("name", "unknown")
                point_type = result.get("type", "unknown")
                score = result.get("score", 0)
                print(f"      {i}. 🧩 {name} ({point_type}) - score: {score:.3f}")


def test_similar_queries():
    """Test queries similar to the cards that received positive feedback."""
    print("\n" + "=" * 70)
    print("TESTING SIMILAR QUERIES")
    print("=" * 70)
    print("\nThese queries are similar to cards you rated positively.")
    print("The feedback loop should boost results that match proven patterns.\n")

    # Queries similar to the test cards
    similar_queries = [
        # Similar to: Product card showing price "$149.99" with label "Sale Price"
        "Show a product with price and buy button",
        "Create a pricing card with purchase option",

        # Similar to: Status card showing "Deployment Complete"
        "Display deployment status with success message",
        "Show system status card",

        # Similar to: Multi-section server info card
        "Show server metrics with uptime and latency",
        "Create a dashboard card with environment info",
    ]

    query_with_feedback_comparison(similar_queries)


def test_unrelated_queries():
    """Test queries unrelated to the feedback patterns."""
    print("\n" + "=" * 70)
    print("TESTING UNRELATED QUERIES (control group)")
    print("=" * 70)
    print("\nThese queries are NOT similar to your rated cards.")
    print("They should NOT match feedback patterns.\n")

    unrelated_queries = [
        "Create a calendar event card",
        "Show user profile information",
        "Display a weather forecast",
    ]

    query_with_feedback_comparison(unrelated_queries)


def main():
    """Run the feedback boost demonstration."""
    print("=" * 70)
    print("FEEDBACK LOOP BOOST DEMONSTRATION")
    print("=" * 70)
    print(f"\nUsing collection: {_settings.card_collection}")
    print("\nThis demo shows how positive feedback affects future queries:")
    print("1. When you rate a card 👍, it stores an instance_pattern")
    print("2. The pattern has a description_colbert embedding")
    print("3. Future similar queries are boosted via RRF (Reciprocal Rank Fusion)")
    print("4. Proven params from matching patterns are merged into new cards")

    # Step 1: Show collection stats
    show_collection_stats()

    # Step 2: Show recent patterns
    show_recent_patterns()

    # Step 3: Test similar queries (should match)
    test_similar_queries()

    # Step 4: Test unrelated queries (should not match)
    test_unrelated_queries()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
The feedback loop works as follows:

1. STORE: When you rate a card positively, store_instance_pattern() saves:
   - card_description → embedded with ColBERT → description_colbert vector
   - component_paths → which components were used
   - instance_params → the actual parameters that worked
   - feedback: "positive"

2. QUERY: When building a new card, query_with_feedback() uses:
   - Prefetch on "colbert" vector (component search)
   - Prefetch on "description_colbert" vector (pattern search)
   - RRF fusion to combine and re-rank results
   - Positive patterns get boosted in final ranking

3. MERGE: get_proven_params_for_description() finds matching patterns:
   - Searches description_colbert for similar descriptions
   - Returns instance_params from proven patterns
   - These params are merged into new card builds

This creates a learning loop where user feedback improves future results!
""")


if __name__ == "__main__":
    main()
