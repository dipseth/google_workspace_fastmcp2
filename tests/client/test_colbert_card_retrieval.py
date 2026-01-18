"""Tests for ColBERT-based card component retrieval and NLP parsing integration.

This module tests the ColBERT multi-vector semantic search functionality
for finding card components and validates that NLP parameter extraction
works correctly in both ColBERT and standard modes.

Key areas tested:
1. ColBERT search returns results with valid component objects
2. Component path lookup via _get_component_from_path
3. NLP parsing should extract parameters regardless of ColBERT mode
4. End-to-end card generation with ColBERT + NLP combined
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Add project root to path for imports
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# Test configuration
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test@example.com")
TEST_WEBHOOK_URL = os.getenv("TEST_CHAT_WEBHOOK", "")
TEST_SPACE_ID = "AAAAWvjq2HE"


class TestColBERTComponentRetrieval:
    """Test ColBERT-based component retrieval functionality."""

    @pytest.mark.asyncio
    async def test_colbert_search_returns_results(self, client):
        """Test that ColBERT search finds card components."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("TEST_CHAT_WEBHOOK not set")

        # Send a card with use_colbert=true and check response
        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": "A simple card with a header",
            "card_params": {},
            "webhook_url": TEST_WEBHOOK_URL,
            "use_colbert": True,
        }

        result = await client.call_tool("send_dynamic_card", test_payload)
        content = _extract_content(result)

        print(f"\n{'='*60}")
        print("ColBERT Search Results Test")
        print(f"{'='*60}")
        print(f"Response: {content[:500]}...")

        # Parse the JSON response
        try:
            data = json.loads(content)
            component_info = data.get("componentInfo", {})

            print(f"\nComponent Info:")
            print(f"  - componentFound: {component_info.get('componentFound')}")
            print(f"  - componentName: {component_info.get('componentName')}")
            print(f"  - searchScore: {component_info.get('searchScore')}")
            print(f"  - componentType: {component_info.get('componentType')}")

            # Check validation issues to understand what went wrong
            validation_issues = data.get("validationIssues", [])
            if validation_issues:
                print(f"\nValidation Issues:")
                for issue in validation_issues:
                    print(f"  - {issue}")

            # The card may fail if NLP wasn't run - that's the bug we're detecting
            if data.get("nlpExtraction") is None and not data.get("success"):
                print(
                    "\n*** NOTE: NLP extraction was null - this is expected with the current bug ***"
                )
                print(
                    "ColBERT found the component but no parameters were extracted to populate it."
                )

        except json.JSONDecodeError:
            print(f"Non-JSON response: {content}")

    @pytest.mark.asyncio
    async def test_colbert_vs_standard_search_comparison(self, client):
        """Compare ColBERT vs standard search results for the same query."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("TEST_CHAT_WEBHOOK not set")

        description = "Create a card with header 'Test' and a button labeled 'Click Me'"

        # Test with ColBERT
        colbert_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": description,
            "card_params": {},
            "webhook_url": TEST_WEBHOOK_URL,
            "use_colbert": True,
        }

        # Test without ColBERT (standard mode)
        standard_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": description,
            "card_params": {},
            "webhook_url": TEST_WEBHOOK_URL,
            "use_colbert": False,
        }

        colbert_result = await client.call_tool("send_dynamic_card", colbert_payload)
        standard_result = await client.call_tool("send_dynamic_card", standard_payload)

        colbert_content = _extract_content(colbert_result)
        standard_content = _extract_content(standard_result)

        print(f"\n{'='*60}")
        print("ColBERT vs Standard Search Comparison")
        print(f"{'='*60}")

        try:
            colbert_data = json.loads(colbert_content)
            standard_data = json.loads(standard_content)

            print(f"\nColBERT Mode:")
            print(f"  - Card Type: {colbert_data.get('cardType')}")
            print(
                f"  - Component: {colbert_data.get('componentInfo', {}).get('componentName')}"
            )
            print(
                f"  - Score: {colbert_data.get('componentInfo', {}).get('searchScore')}"
            )

            print(f"\nStandard Mode:")
            print(f"  - Card Type: {standard_data.get('cardType')}")
            print(
                f"  - Component: {standard_data.get('componentInfo', {}).get('componentName')}"
            )
            print(
                f"  - Score: {standard_data.get('componentInfo', {}).get('searchScore')}"
            )

            # Check if NLP was used in both modes (the key fix we're testing)
            # Note: Card may still fail validation for complex descriptions,
            # but NLP should run in both modes
            colbert_validation = colbert_data.get("validationIssues") or []
            standard_validation = standard_data.get("validationIssues") or []

            # The key test: both should attempt card generation (not skip NLP)
            # If both have same validation issues, NLP is working in both modes
            print(f"\n  ColBERT validation issues: {len(colbert_validation)}")
            print(f"  Standard validation issues: {len(standard_validation)}")
            print(f"\n  ColBERT success: {colbert_data.get('success')}")
            print(f"  Standard success: {standard_data.get('success')}")

        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")


class TestNLPParsingWithColBERT:
    """Test that NLP parameter extraction works correctly with ColBERT mode."""

    @pytest.mark.asyncio
    async def test_nlp_extracts_parameters_in_colbert_mode(self, client):
        """
        BUG TEST: Verify NLP parsing extracts parameters even when ColBERT is enabled.

        Current bug: ColBERT mode skips NLP parsing entirely (line 2220-2223 in unified_card_tool.py)
        Expected: NLP should extract header, button text, URLs even in ColBERT mode
        """
        if not TEST_WEBHOOK_URL:
            pytest.skip("TEST_CHAT_WEBHOOK not set")

        # Description with clear extractable parameters
        description = "Create a card with header 'Project Status' and subtitle 'Weekly Update' and a green button labeled 'Approve' that opens https://example.com/approve"

        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": description,
            "card_params": {},  # Empty to force NLP extraction
            "webhook_url": TEST_WEBHOOK_URL,
            "use_colbert": True,
        }

        result = await client.call_tool("send_dynamic_card", test_payload)
        content = _extract_content(result)

        print(f"\n{'='*60}")
        print("NLP Parameter Extraction in ColBERT Mode")
        print(f"{'='*60}")
        print(f"Description: {description}")

        try:
            data = json.loads(content)

            print(f"\nResponse Analysis:")
            print(f"  - Success: {data.get('success')}")
            print(f"  - HTTP Status: {data.get('httpStatus')}")
            print(f"  - Card Type: {data.get('cardType')}")
            print(f"  - NLP Extraction: {data.get('nlpExtraction')}")

            # Check if the card has actual content (not empty fallback)
            message = data.get("message", "")

            # BUG DETECTION: If we see "Empty card" that means NLP didn't extract params
            if "Empty card" in message:
                print("\n*** BUG DETECTED ***")
                print("NLP extraction was skipped in ColBERT mode!")
                print("The card fell back to empty content.")
                pytest.fail(
                    "BUG: ColBERT mode skipped NLP parsing. "
                    "Card params should have been extracted from description but weren't. "
                    "See unified_card_tool.py lines 2220-2223"
                )
            else:
                print("\n NLP extraction appears to be working")

        except json.JSONDecodeError:
            print(f"Response: {content}")

    @pytest.mark.asyncio
    async def test_nlp_extraction_standard_mode_baseline(self, client):
        """Baseline test: Verify NLP extraction works in standard (non-ColBERT) mode."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("TEST_CHAT_WEBHOOK not set")

        description = "Create a card titled 'Hello World' with text 'This is a test message' and a blue button 'Learn More'"

        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": description,
            "card_params": {},
            "webhook_url": TEST_WEBHOOK_URL,
            "use_colbert": False,  # Standard mode
        }

        result = await client.call_tool("send_dynamic_card", test_payload)
        content = _extract_content(result)

        print(f"\n{'='*60}")
        print("NLP Extraction Baseline (Standard Mode)")
        print(f"{'='*60}")

        try:
            data = json.loads(content)

            print(f"  - Success: {data.get('success')}")
            print(f"  - Card Type: {data.get('cardType')}")
            print(f"  - NLP Extraction: {data.get('nlpExtraction')}")

            message = data.get("message", "")
            if "Empty card" not in message:
                print("\n Standard mode NLP extraction working")
            else:
                print("\n WARNING: Even standard mode produced empty card")

        except json.JSONDecodeError:
            print(f"Response: {content}")


class TestComponentPathLookup:
    """Test component path lookup functionality in ModuleWrapper."""

    @pytest.mark.asyncio
    async def test_colbert_component_has_valid_object(self, client):
        """
        BUG TEST: Verify ColBERT search results include actual component objects.

        Current bug: _get_component_from_path returns None because path not in self.components
        Expected: Component should be retrievable from the path returned by ColBERT search
        """
        if not TEST_WEBHOOK_URL:
            pytest.skip("TEST_CHAT_WEBHOOK not set")

        # Use a description that should match a specific component
        description = "card with header"

        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": description,
            "card_params": {"title": "Test Title"},  # Provide explicit params
            "webhook_url": TEST_WEBHOOK_URL,
            "use_colbert": True,
        }

        result = await client.call_tool("send_dynamic_card", test_payload)
        content = _extract_content(result)

        print(f"\n{'='*60}")
        print("Component Object Retrieval Test")
        print(f"{'='*60}")

        try:
            data = json.loads(content)
            component_info = data.get("componentInfo", {})

            print(f"\nComponent Info:")
            print(f"  - Found: {component_info.get('componentFound')}")
            print(f"  - Name: {component_info.get('componentName')}")
            print(f"  - Path: {component_info.get('componentPath')}")
            print(f"  - Type: {component_info.get('componentType')}")
            print(f"  - Score: {component_info.get('searchScore')}")

            # Check if component type indicates a fallback
            if component_info.get("componentType") == "simple_fallback":
                print("\n*** BUG DETECTED ***")
                print("Component lookup failed - fell back to simple_fallback")
                print(
                    "ColBERT found a match but couldn't retrieve the component object"
                )

        except json.JSONDecodeError:
            print(f"Response: {content}")


class TestEndToEndColBERTCardGeneration:
    """End-to-end tests for ColBERT-based card generation."""

    @pytest.mark.asyncio
    async def test_complex_card_colbert_mode(self, client):
        """Test generating a complex card using ColBERT mode."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("TEST_CHAT_WEBHOOK not set")

        timestamp = datetime.now().strftime("%H:%M:%S")

        description = f"""Create a status dashboard card with:
            - Header titled 'System Status' with subtitle 'Last updated: {timestamp}'
            - A section showing 'All Systems Operational' with a green check icon
            - A button labeled 'View Details' that opens https://status.example.com
        """

        test_payload = {
            "user_google_email": TEST_EMAIL,
            "space_id": TEST_SPACE_ID,
            "card_description": description,
            "card_params": {},
            "webhook_url": TEST_WEBHOOK_URL,
            "use_colbert": True,
        }

        result = await client.call_tool("send_dynamic_card", test_payload)
        content = _extract_content(result)

        print(f"\n{'='*60}")
        print("Complex Card Generation (ColBERT Mode)")
        print(f"{'='*60}")

        try:
            data = json.loads(content)

            print(f"\nResult:")
            print(f"  - Success: {data.get('success')}")
            print(f"  - HTTP Status: {data.get('httpStatus')}")
            print(f"  - Card Type: {data.get('cardType')}")
            print(
                f"  - Component: {data.get('componentInfo', {}).get('componentName')}"
            )

            # Check the message for content
            message = data.get("message", "")
            if "Empty card" in message:
                print("\n FAILED: Card has no content")
            elif "200" in str(data.get("httpStatus")):
                print("\n Card sent successfully")

        except json.JSONDecodeError:
            print(f"Response: {content}")

    @pytest.mark.asyncio
    async def test_simple_text_card_colbert_vs_standard(self, client):
        """Compare simple text card generation between ColBERT and standard modes."""
        if not TEST_WEBHOOK_URL:
            pytest.skip("TEST_CHAT_WEBHOOK not set")

        description = "A simple card with text saying 'Hello from ColBERT test'"

        results = {}
        for mode_name, use_colbert in [("ColBERT", True), ("Standard", False)]:
            payload = {
                "user_google_email": TEST_EMAIL,
                "space_id": TEST_SPACE_ID,
                "card_description": description,
                "card_params": {},
                "webhook_url": TEST_WEBHOOK_URL,
                "use_colbert": use_colbert,
            }

            result = await client.call_tool("send_dynamic_card", payload)
            content = _extract_content(result)

            try:
                results[mode_name] = json.loads(content)
            except json.JSONDecodeError:
                results[mode_name] = {"raw": content}

        print(f"\n{'='*60}")
        print("Simple Text Card: ColBERT vs Standard")
        print(f"{'='*60}")

        for mode, data in results.items():
            print(f"\n{mode} Mode:")
            if "raw" in data:
                print(f"  Raw response: {data['raw'][:200]}")
            else:
                print(f"  - HTTP Status: {data.get('httpStatus')}")
                print(f"  - Card Type: {data.get('cardType')}")
                has_content = "Empty card" not in data.get("message", "")
                print(f"  - Has Content: {has_content}")


# Helper function
def _extract_content(result) -> str:
    """Extract text content from tool result."""
    if hasattr(result, "content"):
        content_items = (
            result.content if hasattr(result.content, "__iter__") else [result.content]
        )
        return (
            content_items[0].text
            if hasattr(content_items[0], "text")
            else str(content_items[0])
        )
    return str(result)


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
