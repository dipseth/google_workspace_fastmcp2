"""Unit tests for ColBERT search and component retrieval.

These tests directly test the ModuleWrapper ColBERT functionality
without going through the full MCP server, allowing us to isolate
and debug specific issues with:

1. ColBERT search returning results
2. Component path lookup (_get_component_from_path)
3. Score thresholds and their effect on results
4. NLP parsing function behavior
"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional

import pytest
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestModuleWrapperColBERTSearch:
    """Test ColBERT search functionality in ModuleWrapper."""

    @pytest.fixture
    def colbert_wrapper(self):
        """Create a ModuleWrapper with ColBERT enabled for card framework."""
        from adapters.module_wrapper import ModuleWrapper

        # Check if Qdrant is configured
        qdrant_url = os.getenv("QDRANT_URL") or os.getenv("QDRANT_CLOUD_URL")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")

        if not qdrant_url:
            pytest.skip("QDRANT_URL not configured")

        try:
            wrapper = ModuleWrapper(
                module_name="card_framework",
                qdrant_url=qdrant_url,
                qdrant_api_key=qdrant_api_key,
                collection_name="card_framework_components_colbert",
                enable_colbert=True,
            )
            return wrapper
        except Exception as e:
            pytest.skip(f"Failed to initialize ModuleWrapper: {e}")

    def test_colbert_search_returns_results(self, colbert_wrapper):
        """Test that ColBERT search returns results for card-related queries."""
        queries = [
            "card with header",
            "button widget",
            "text paragraph",
            "peek card header",
        ]

        for query in queries:
            print(f"\n{'='*50}")
            print(f"Query: '{query}'")
            print(f"{'='*50}")

            results = colbert_wrapper.colbert_search(
                query=query,
                limit=5,
                score_threshold=0.1,  # Low threshold to see all matches
            )

            print(f"Found {len(results)} results:")
            for i, r in enumerate(results):
                print(f"  {i+1}. {r.get('name')} (score: {r.get('score', 0):.4f})")
                print(f"      path: {r.get('path')}")
                print(f"      component: {r.get('component')}")

            assert len(results) > 0, f"ColBERT should find results for '{query}'"

    def test_colbert_search_different_thresholds(self, colbert_wrapper):
        """Test how different score thresholds affect results."""
        query = "simple card with header and text"

        thresholds = [0.0, 0.1, 0.3, 0.5, 1.0, 5.0, 10.0, 20.0]

        print(f"\n{'='*60}")
        print(f"Query: '{query}'")
        print(f"Testing different score thresholds")
        print(f"{'='*60}")

        for threshold in thresholds:
            results = colbert_wrapper.colbert_search(
                query=query,
                limit=10,
                score_threshold=threshold,
            )
            print(f"\nThreshold {threshold}: {len(results)} results")
            if results:
                scores = [r.get('score', 0) for r in results]
                print(f"  Score range: {min(scores):.2f} - {max(scores):.2f}")

    def test_component_object_retrieval(self, colbert_wrapper):
        """Test that component objects are properly retrieved from search results."""
        query = "card header"

        results = colbert_wrapper.colbert_search(
            query=query,
            limit=5,
            score_threshold=0.1,
        )

        print(f"\n{'='*60}")
        print(f"Component Object Retrieval Test")
        print(f"{'='*60}")

        components_found = 0
        components_missing = 0

        for r in results:
            name = r.get('name')
            path = r.get('path')
            component = r.get('component')

            if component is not None:
                components_found += 1
                print(f"\n  {name}:")
                print(f"    Path: {path}")
                print(f"    Component type: {type(component).__name__}")
            else:
                components_missing += 1
                print(f"\n  {name}: COMPONENT IS NONE")
                print(f"    Path: {path}")

        print(f"\n\nSummary:")
        print(f"  Components found: {components_found}")
        print(f"  Components missing: {components_missing}")

        if components_missing > 0:
            print("\n*** BUG: Some components could not be retrieved from their paths ***")
            print("This causes ColBERT search to fail even when it finds matches.")

    def test_get_component_from_path_directly(self, colbert_wrapper):
        """Test _get_component_from_path method directly."""
        print(f"\n{'='*60}")
        print(f"Direct Component Path Lookup Test")
        print(f"{'='*60}")

        # First, let's see what paths are available in self.components
        print(f"\nAvailable component paths ({len(colbert_wrapper.components)}):")
        for path in list(colbert_wrapper.components.keys())[:10]:
            print(f"  - {path}")

        if len(colbert_wrapper.components) > 10:
            print(f"  ... and {len(colbert_wrapper.components) - 10} more")

        # Now do a ColBERT search and check if returned paths exist
        results = colbert_wrapper.colbert_search("header", limit=3)

        print(f"\nColBERT search returned paths:")
        for r in results:
            path = r.get('path')
            exists = path in colbert_wrapper.components
            print(f"  - {path}: {'EXISTS' if exists else 'NOT FOUND'}")


class TestNLPCardParser:
    """Test NLP card parsing functionality."""

    def test_nlp_parser_extracts_header(self):
        """Test that NLP parser extracts header/title from description."""
        try:
            from gchat.nlp_card_parser import (
                parse_enhanced_natural_language_description,
            )
        except ImportError:
            pytest.skip("Could not import nlp_card_parser")

        description = "Create a card titled 'Project Status' with subtitle 'Weekly Update'"

        print(f"\n{'='*60}")
        print(f"NLP Parser Header Extraction Test")
        print(f"{'='*60}")
        print(f"Description: {description}")

        result = parse_enhanced_natural_language_description(description)

        print(f"\nExtracted parameters:")
        for key, value in (result or {}).items():
            print(f"  {key}: {value}")

        assert result is not None, "NLP parser should extract parameters"
        # Check for title or header in extracted params
        has_title = any(k in result for k in ['title', 'header', 'header_title'])
        print(f"\nTitle/header extracted: {has_title}")

    def test_nlp_parser_extracts_buttons(self):
        """Test that NLP parser extracts button information."""
        try:
            from gchat.nlp_card_parser import (
                parse_enhanced_natural_language_description,
            )
        except ImportError:
            pytest.skip("Could not import nlp_card_parser")

        description = "Create a card with a green button labeled 'Approve' that opens https://example.com/approve"

        print(f"\n{'='*60}")
        print(f"NLP Parser Button Extraction Test")
        print(f"{'='*60}")
        print(f"Description: {description}")

        result = parse_enhanced_natural_language_description(description)

        print(f"\nExtracted parameters:")
        for key, value in (result or {}).items():
            print(f"  {key}: {value}")

        assert result is not None, "NLP parser should extract button parameters"

    def test_nlp_parser_extracts_sections(self):
        """Test that NLP parser extracts section information."""
        try:
            from gchat.nlp_card_parser import (
                parse_enhanced_natural_language_description,
            )
        except ImportError:
            pytest.skip("Could not import nlp_card_parser")

        description = """Create a card with sections:
            - 'User Info' section with text showing 'John Doe'
            - 'Actions' section with buttons 'Edit' and 'Delete'
        """

        print(f"\n{'='*60}")
        print(f"NLP Parser Section Extraction Test")
        print(f"{'='*60}")
        print(f"Description: {description[:100]}...")

        result = parse_enhanced_natural_language_description(description)

        print(f"\nExtracted parameters:")
        if result:
            for key, value in result.items():
                if isinstance(value, list):
                    print(f"  {key}: [{len(value)} items]")
                    for item in value[:2]:
                        print(f"    - {item}")
                else:
                    print(f"  {key}: {value}")
        else:
            print("  None extracted")


class TestColBERTWithNLPIntegration:
    """Test the integration of ColBERT search with NLP parsing."""

    @pytest.fixture
    def unified_card_functions(self):
        """Import the unified card tool functions."""
        try:
            from gchat.nlp_card_parser import (
                parse_enhanced_natural_language_description,
            )
            from gchat.unified_card_tool import (
                _find_card_component,
                _find_card_component_colbert,
            )

            return {
                "colbert_search": _find_card_component_colbert,
                "standard_search": _find_card_component,
                "nlp_parse": parse_enhanced_natural_language_description,
            }
        except ImportError as e:
            pytest.skip(f"Could not import unified_card_tool functions: {e}")

    @pytest.mark.asyncio
    async def test_colbert_search_function(self, unified_card_functions):
        """Test the _find_card_component_colbert function directly."""
        colbert_search = unified_card_functions["colbert_search"]

        query = "card with header and button"

        print(f"\n{'='*60}")
        print(f"Testing _find_card_component_colbert")
        print(f"{'='*60}")
        print(f"Query: {query}")

        results = await colbert_search(query, limit=5, score_threshold=0.1)

        print(f"\nResults: {len(results)}")
        for r in results:
            print(f"  - {r.get('name')}: score={r.get('score', 0):.4f}, component={r.get('component')}")

    @pytest.mark.asyncio
    async def test_colbert_plus_nlp_combined(self, unified_card_functions):
        """
        Test that ColBERT + NLP can work together.

        This is what SHOULD happen:
        1. ColBERT finds the right template/component
        2. NLP extracts parameters from the description
        3. Template is populated with extracted parameters
        """
        colbert_search = unified_card_functions["colbert_search"]
        nlp_parse = unified_card_functions["nlp_parse"]

        description = "Create a card titled 'Status Update' with text 'All systems operational' and a green 'Acknowledge' button"

        print(f"\n{'='*60}")
        print(f"ColBERT + NLP Combined Test")
        print(f"{'='*60}")
        print(f"Description: {description}")

        # Step 1: NLP extracts parameters
        print(f"\nStep 1: NLP Parameter Extraction")
        nlp_params = nlp_parse(description)
        print(f"  Extracted: {list(nlp_params.keys()) if nlp_params else 'None'}")
        if nlp_params:
            for k, v in nlp_params.items():
                print(f"    {k}: {v}")

        # Step 2: ColBERT finds component
        print(f"\nStep 2: ColBERT Component Search")
        results = await colbert_search(description, limit=3)
        print(f"  Found: {len(results)} components")
        for r in results:
            print(f"    - {r.get('name')} (score: {r.get('score', 0):.4f})")

        # Both should work
        assert nlp_params is not None, "NLP should extract parameters"
        assert len(results) > 0, "ColBERT should find components"

        print(f"\n BOTH ColBERT and NLP working independently")
        print(f"The bug is that they're not combined in ColBERT mode!")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
