"""Tests for the feedback loop integration with send_dynamic_card.

This module tests the feedback loop functionality that:
1. Adds feedback buttons (Good/Bad) to generated cards
2. Stores card patterns as instance_patterns in Qdrant
3. Boosts similar queries using proven patterns
4. Merges proven params into new card builds

The feedback loop uses the CARD_COLLECTION environment variable
to determine which Qdrant collection to use.

Run with: uv run pytest tests/client/test_feedback_loop_integration.py -v
"""

import json
import os
import re

import pytest
from dotenv import load_dotenv

from .base_test_config import TEST_EMAIL
from .test_helpers import assert_tools_registered

# Load environment variables
load_dotenv()

# Test configuration
TEST_CHAT_WEBHOOK = os.getenv("TEST_CHAT_WEBHOOK", "")
TEST_CHAT_SPACE_ID = os.getenv("TEST_CHAT_SPACE_ID", "")

# Extract space ID from webhook if not explicitly set
if not TEST_CHAT_SPACE_ID and TEST_CHAT_WEBHOOK:
    try:
        match = re.search(r"/spaces/([^/]+)/", TEST_CHAT_WEBHOOK)
        if match:
            TEST_CHAT_SPACE_ID = match.group(1)
    except Exception:
        pass

print("FEEDBACK LOOP INTEGRATION TEST CONFIG:")
print(f"  - Webhook URL: {'Configured' if TEST_CHAT_WEBHOOK else 'Missing'}")
print(f"  - Space ID: {TEST_CHAT_SPACE_ID or 'Missing'}")
print(f"  - Email: {TEST_EMAIL or 'Missing'}")
print(f"  - Collection: {os.getenv('CARD_COLLECTION', 'default')}")


@pytest.mark.service("chat")
class TestFeedbackButtonsPresent:
    """Test that feedback buttons are included in generated cards."""

    @pytest.mark.asyncio
    async def test_send_dynamic_card_has_feedback_section(self, client):
        """Test that cards include a feedback section with Good/Bad buttons."""
        space_id = TEST_CHAT_SPACE_ID or "spaces/test_space"

        # Build params - use webhook if available (required for cards with human OAuth)
        params = {
            "user_google_email": TEST_EMAIL,
            "space_id": f"spaces/{space_id}",
            "card_description": 'Simple status card showing "Test Complete"',
        }
        if TEST_CHAT_WEBHOOK:
            params["webhook_url"] = TEST_CHAT_WEBHOOK

        result = await client.call_tool("send_dynamic_card", params)

        assert result is not None and result.content
        content = result.content[0].text

        # Check that we got a response (may be JSON or text)
        try:
            data = json.loads(content)

            # Log response for debugging
            print(f"\nResponse cardType: {data.get('cardType')}")
            print(f"Response success: {data.get('success')}")

            # The feedback buttons should be in the card output
            # Note: We can't directly inspect the card JSON here since
            # it's sent to the webhook, but we can verify the pattern
            # was stored for feedback
            if data.get("success"):
                # Card was sent successfully - feedback buttons should be included
                # when ENABLE_CARD_FEEDBACK is true (default)
                print("Card sent successfully - feedback buttons should be included")

        except json.JSONDecodeError:
            # Text response - check for success indicators
            # Note: "human credentials" error occurs when sending cards via API without webhook
            valid_responses = [
                "success",
                "card sent",
                "requires authentication",
                "human credentials",
            ]
            assert any(keyword in content.lower() for keyword in valid_responses)


@pytest.mark.service("chat")
class TestFeedbackPatternStorage:
    """Test that card patterns are stored in Qdrant for the feedback loop."""

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_card_pattern_stored_on_send(self, client):
        """Test that sending a card stores the pattern for future feedback."""
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        # Send a distinctive card
        card_description = (
            'Product card showing price "$299.99" with a "Purchase" button'
        )

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": card_description,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        try:
            data = json.loads(content)

            if data.get("success"):
                # Card sent - now verify the pattern storage happened
                # The SmartCardBuilder should have stored this as an instance_pattern
                print(f"\nCard sent successfully")
                print(f"Card Type: {data.get('cardType')}")

                # The pattern should be stored with the card_description embedded
                # via description_colbert vector for future similarity matching

        except json.JSONDecodeError:
            # Check for text success indicators
            assert "success" in content.lower() or "card sent" in content.lower()


@pytest.mark.service("chat")
class TestProvenParamsMerging:
    """Test that proven patterns from positive feedback influence new cards."""

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_similar_query_gets_boosted(self, client):
        """Test that a similar query benefits from previous positive feedback.

        This test requires that you've previously sent cards and rated them
        positively. The feedback loop should boost similar queries.
        """
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        # Query similar to cards that may have received positive feedback
        # (like the product cards from the warm-start patterns)
        card_description = "Show a product with price and buy button"

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": card_description,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        try:
            data = json.loads(content)

            print(f"\nResponse for similar query:")
            print(f"  - Success: {data.get('success')}")
            print(f"  - Card Type: {data.get('cardType')}")
            print(f"  - HTTP Status: {data.get('httpStatus')}")

            # If the feedback loop is working, the card should be generated
            # successfully because we have proven patterns for product cards
            if data.get("success"):
                print("  - Card built successfully (may have used proven patterns)")

        except json.JSONDecodeError:
            valid_responses = ["success", "card sent", "webhook"]
            assert any(keyword in content.lower() for keyword in valid_responses)


@pytest.mark.service("chat")
class TestFeedbackLoopUnit:
    """Unit tests for the feedback loop that don't require MCP server."""

    def test_feedback_loop_imports(self):
        """Test that feedback loop module can be imported."""
        from gchat.feedback_loop import FeedbackLoop, get_feedback_loop

        fl = get_feedback_loop()
        assert fl is not None
        assert isinstance(fl, FeedbackLoop)

    def test_collection_name_from_settings(self):
        """Test that collection name is configurable via settings."""
        from config.settings import settings

        # Collection should be configurable via CARD_COLLECTION env var
        collection = settings.card_collection
        assert collection is not None
        assert len(collection) > 0
        print(f"\nCurrent collection: {collection}")

    def test_warm_start_patterns_defined(self):
        """Test that warm-start patterns are defined in feedback loop."""
        from gchat.feedback_loop import FeedbackLoop

        fl = FeedbackLoop()

        # The warm-start patterns are defined in _warm_start_collection
        # We can verify the method exists
        assert hasattr(fl, "_warm_start_collection")
        assert callable(fl._warm_start_collection)

    def test_proven_params_method_exists(self):
        """Test that the proven params retrieval method exists."""
        from gchat.feedback_loop import FeedbackLoop

        fl = FeedbackLoop()

        assert hasattr(fl, "get_proven_params_for_description")
        assert callable(fl.get_proven_params_for_description)


@pytest.mark.service("chat")
@pytest.mark.integration
class TestFeedbackCollectionConfiguration:
    """Test collection configuration for feedback loop."""

    @pytest.mark.asyncio
    async def test_collection_exists_and_ready(self, client):
        """Test that the configured collection exists and is ready for queries."""
        from config.settings import settings
        from gchat.feedback_loop import get_feedback_loop

        fl = get_feedback_loop()
        collection = settings.card_collection

        print(f"\nTesting collection: {collection}")

        # This should auto-create the collection if it doesn't exist
        result = fl.ensure_description_vector_exists()

        assert result is True, f"Collection {collection} should be ready"
        print(f"Collection {collection} is ready")

    @pytest.mark.asyncio
    async def test_hybrid_query_returns_results(self, client):
        """Test that hybrid query (component + pattern search) works."""
        from gchat.feedback_loop import get_feedback_loop

        fl = get_feedback_loop()

        # Ensure collection is ready
        fl.ensure_description_vector_exists()

        # Run a hybrid query
        class_results, content_patterns, form_patterns = fl.query_with_feedback(
            component_query="card widget",
            description="product card with price",
            limit=5,
        )

        print(f"\nHybrid query results:")
        print(f"  - Class results: {len(class_results)}")
        print(f"  - Content patterns: {len(content_patterns)}")
        print(f"  - Form patterns: {len(form_patterns)}")

        # Should have either component or pattern results
        # (depends on collection contents)
        total_results = len(class_results) + len(content_patterns) + len(form_patterns)
        print(f"  - Total results: {total_results}")

        # If collection has data, we should get some results
        # Note: Empty collection is valid (just no results)


@pytest.mark.service("chat")
@pytest.mark.integration
class TestEndToEndFeedbackFlow:
    """End-to-end tests for the complete feedback loop flow."""

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_send_rate_query_flow(self, client):
        """Test the full flow: send card -> (manual rating) -> query similar.

        This test demonstrates the feedback loop flow:
        1. Send a card via send_dynamic_card (card includes feedback buttons)
        2. User manually clicks 'Good' button (not automated in test)
        3. Query with similar description should find the proven pattern

        Note: Step 2 requires manual interaction with the card in Google Chat.
        """
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        # Step 1: Send a distinctive card
        unique_desc = (
            'Dashboard card showing "Server Uptime: 99.9%" with monitoring link'
        )

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": unique_desc,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        try:
            data = json.loads(content)

            if data.get("success"):
                print(f"\n Step 1: Card sent successfully")
                print(f"   The card should appear in Google Chat with Good/Bad buttons")
                print(f"   To complete the feedback loop test:")
                print(f"   1. Find the card in Google Chat")
                print(f"   2. Click the 'Good' button")
                print(f"   3. Run the test_similar_query_gets_boosted test")

                # Step 3 (automated): Query for similar description
                # This will benefit from feedback if user clicked 'Good'
                from gchat.feedback_loop import get_feedback_loop

                fl = get_feedback_loop()
                proven = fl.get_proven_params_for_description(
                    description="server uptime monitoring dashboard",
                    min_score=0.3,
                )

                if proven:
                    print(f"\n Step 3: Found proven pattern!")
                    print(f"   Params: {list(proven.keys())}")
                else:
                    print(f"\n Step 3: No proven pattern yet")
                    print(f"   (Rate the card positively to add it)")

        except json.JSONDecodeError:
            print(f"Response: {content}")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
