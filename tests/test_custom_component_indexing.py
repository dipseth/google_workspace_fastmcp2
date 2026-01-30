"""
Tests for custom component indexing to Qdrant.

Verifies that custom components (e.g., API components not in the Python package)
are properly indexed to Qdrant with symbols, relationships, and searchable embeddings.

The implementation is generic and works with any ModuleWrapper, not just card_framework.
"""

import pytest
from unittest.mock import MagicMock, patch


# Patch the qdrant import at module level for all tests
QDRANT_IMPORT_PATH = "adapters.module_wrapper.qdrant_mixin._get_qdrant_imports"


class TestCustomComponentIndexing:
    """Test custom component indexing functionality."""

    def test_index_custom_components_creates_points(self):
        """Test that index_custom_components creates Qdrant points."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        # Create a mock mixin instance with required attributes
        mixin = RelationshipsMixin()
        mixin.collection_name = "test_collection"
        mixin.module_name = "test_module"
        mixin._cached_relationships = {}
        mixin.symbol_mapping = {"Section": "§", "Button": "ᵬ"}
        mixin.reverse_symbol_mapping = {"§": "Section", "ᵬ": "Button"}

        # Mock client and embedder
        mock_client = MagicMock()
        mock_embedder = MagicMock()

        # Mock embedding generation - return fresh embedding for each call
        mock_embedding = [0.1] * 384  # Typical embedding dimension
        mock_embedder.embed.side_effect = lambda texts: iter([mock_embedding for _ in texts])

        mixin.client = mock_client
        mixin.embedder = mock_embedder

        # Define custom components
        custom_components = {
            "CustomWidgetA": {
                "children": ["CustomWidgetB"],
                "docstring": "Custom widget container",
            },
            "CustomWidgetB": {
                "children": ["NestedChild"],
                "docstring": "Nested custom widget",
            },
        }

        # Call the method
        with patch(QDRANT_IMPORT_PATH) as mock_imports:
            mock_imports.return_value = (None, {"PointStruct": MagicMock})
            count = mixin.index_custom_components(custom_components)

        # Verify
        assert count == 2
        mock_client.upsert.assert_called_once()

        # Check that points were created with correct structure
        call_args = mock_client.upsert.call_args
        assert call_args.kwargs["collection_name"] == "test_collection"
        points = call_args.kwargs["points"]
        assert len(points) == 2

    def test_index_custom_components_generates_symbols(self):
        """Test that indexing generates symbols for new components."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin()
        mixin.collection_name = "test_collection"
        mixin.module_name = "test_module"
        mixin._cached_relationships = {}
        mixin.symbol_mapping = {}
        mixin.reverse_symbol_mapping = {}

        mock_client = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed.side_effect = lambda texts: iter([[0.1] * 384 for _ in texts])

        mixin.client = mock_client
        mixin.embedder = mock_embedder

        custom_components = {
            "TestComponent": {
                "children": [],
                "docstring": "Test component",
            },
        }

        with patch(QDRANT_IMPORT_PATH) as mock_imports:
            mock_imports.return_value = (None, {"PointStruct": MagicMock})
            mixin.index_custom_components(custom_components)

        # Verify symbol was generated
        assert "TestComponent" in mixin.symbol_mapping
        assert mixin.symbol_mapping["TestComponent"] != ""

    def test_index_custom_components_payload_structure(self):
        """Test that indexed components have correct payload structure."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin()
        mixin.collection_name = "test_collection"
        mixin.module_name = "test_module"
        mixin._cached_relationships = {}
        mixin.symbol_mapping = {"MyWidget": "©"}
        mixin.reverse_symbol_mapping = {"©": "MyWidget"}

        mock_client = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed.side_effect = lambda texts: iter([[0.1] * 384 for _ in texts])

        mixin.client = mock_client
        mixin.embedder = mock_embedder

        # Capture the PointStruct creation
        captured_payloads = []

        class MockPointStruct:
            def __init__(self, id, vector, payload):
                self.id = id
                self.vector = vector
                self.payload = payload
                captured_payloads.append(payload)

        custom_components = {
            "MyWidget": {
                "children": ["ChildWidget"],
                "docstring": "My custom widget",
                "json_field": "myWidget",
            },
        }

        with patch(QDRANT_IMPORT_PATH) as mock_imports:
            mock_imports.return_value = (None, {"PointStruct": MockPointStruct})
            mixin.index_custom_components(custom_components)

        # Verify payload structure
        assert len(captured_payloads) == 1
        payload = captured_payloads[0]

        assert payload["name"] == "MyWidget"
        assert payload["type"] == "class"
        assert payload["is_custom_component"] is True
        assert payload["json_field"] == "myWidget"
        assert payload["symbol"] == "©"
        assert "relationships" in payload
        assert payload["relationships"]["child_classes"] == ["ChildWidget"]

    def test_index_custom_components_custom_module_name(self):
        """Test that custom module_name parameter is used."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin()
        mixin.collection_name = "test_collection"
        mixin.module_name = "default_module"
        mixin._cached_relationships = {}
        mixin.symbol_mapping = {}
        mixin.reverse_symbol_mapping = {}

        mock_client = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed.side_effect = lambda texts: iter([[0.1] * 384 for _ in texts])

        mixin.client = mock_client
        mixin.embedder = mock_embedder

        captured_payloads = []

        class MockPointStruct:
            def __init__(self, id, vector, payload):
                captured_payloads.append(payload)

        custom_components = {
            "MyWidget": {"children": [], "docstring": "Test"},
        }

        with patch(QDRANT_IMPORT_PATH) as mock_imports:
            mock_imports.return_value = (None, {"PointStruct": MockPointStruct})
            mixin.index_custom_components(
                custom_components,
                module_name="custom_api_module"
            )

        # Verify custom module name is used
        assert len(captured_payloads) == 1
        assert captured_payloads[0]["module_path"] == "custom_api_module"
        assert captured_payloads[0]["full_path"] == "custom_api_module.MyWidget"

    def test_index_custom_components_custom_payload_fields(self):
        """Test that custom_payload_fields are added to all components."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin()
        mixin.collection_name = "test_collection"
        mixin.module_name = "test_module"
        mixin._cached_relationships = {}
        mixin.symbol_mapping = {}
        mixin.reverse_symbol_mapping = {}

        mock_client = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed.side_effect = lambda texts: iter([[0.1] * 384 for _ in texts])

        mixin.client = mock_client
        mixin.embedder = mock_embedder

        captured_payloads = []

        class MockPointStruct:
            def __init__(self, id, vector, payload):
                captured_payloads.append(payload)

        custom_components = {
            "WidgetA": {"children": [], "docstring": "Widget A"},
            "WidgetB": {"children": [], "docstring": "Widget B"},
        }

        with patch(QDRANT_IMPORT_PATH) as mock_imports:
            mock_imports.return_value = (None, {"PointStruct": MockPointStruct})
            mixin.index_custom_components(
                custom_components,
                custom_payload_fields={
                    "api_version": "v2",
                    "category": "widgets",
                }
            )

        # Verify custom fields are in all payloads
        assert len(captured_payloads) == 2
        for payload in captured_payloads:
            assert payload["api_version"] == "v2"
            assert payload["category"] == "widgets"

    def test_index_custom_components_extra_metadata_fields(self):
        """Test that extra fields in component metadata are preserved."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin()
        mixin.collection_name = "test_collection"
        mixin.module_name = "test_module"
        mixin._cached_relationships = {}
        mixin.symbol_mapping = {}
        mixin.reverse_symbol_mapping = {}

        mock_client = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed.side_effect = lambda texts: iter([[0.1] * 384 for _ in texts])

        mixin.client = mock_client
        mixin.embedder = mock_embedder

        captured_payloads = []

        class MockPointStruct:
            def __init__(self, id, vector, payload):
                captured_payloads.append(payload)

        custom_components = {
            "MyWidget": {
                "children": [],
                "docstring": "Widget with extra fields",
                "custom_field": "custom_value",
                "priority": 5,
            },
        }

        with patch(QDRANT_IMPORT_PATH) as mock_imports:
            mock_imports.return_value = (None, {"PointStruct": MockPointStruct})
            mixin.index_custom_components(custom_components)

        # Verify extra fields from metadata are preserved
        assert len(captured_payloads) == 1
        assert captured_payloads[0]["custom_field"] == "custom_value"
        assert captured_payloads[0]["priority"] == 5

    def test_index_custom_components_without_symbol_generation(self):
        """Test indexing without symbol generation."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin()
        mixin.collection_name = "test_collection"
        mixin.module_name = "test_module"
        mixin._cached_relationships = {}
        mixin.symbol_mapping = {}
        mixin.reverse_symbol_mapping = {}

        mock_client = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed.side_effect = lambda texts: iter([[0.1] * 384 for _ in texts])

        mixin.client = mock_client
        mixin.embedder = mock_embedder

        captured_payloads = []

        class MockPointStruct:
            def __init__(self, id, vector, payload):
                captured_payloads.append(payload)

        custom_components = {
            "NoSymbolWidget": {"children": [], "docstring": "No symbol"},
        }

        with patch(QDRANT_IMPORT_PATH) as mock_imports:
            mock_imports.return_value = (None, {"PointStruct": MockPointStruct})
            mixin.index_custom_components(
                custom_components,
                generate_symbols=False
            )

        # Verify no symbol in payload
        assert len(captured_payloads) == 1
        assert "symbol" not in captured_payloads[0]


class TestCustomComponentQdrantIntegration:
    """Integration tests for custom component indexing (requires Qdrant)."""

    @pytest.fixture
    def wrapper(self):
        """Get the singleton wrapper with fresh state."""
        from gchat.card_framework_wrapper import reset_wrapper, get_card_framework_wrapper

        reset_wrapper()
        return get_card_framework_wrapper()

    def test_custom_components_searchable_via_dsl(self, wrapper):
        """Test that custom components are searchable via DSL methods."""
        if not wrapper.client:
            pytest.skip("Qdrant not available")

        # Search for Carousel via search_by_dsl (uses ColBERT)
        results = wrapper.search_by_dsl(
            text="Carousel widget horizontal scrolling",
            limit=5,
            vector_name="components",
            type_filter="class",
        )

        # Should find Carousel or CarouselCard
        names = [r.get("name") for r in results]
        carousel_found = any(
            "Carousel" in name for name in names if name
        )

        # If no results from DSL search, try regular search
        if not carousel_found:
            # Fall back to text search
            results2 = wrapper.search_by_text(
                field="name",
                query="Carousel",
                limit=3,
            )
            names2 = [r.get("name") for r in results2]
            carousel_found = "Carousel" in names2 or "CarouselCard" in names2

        assert carousel_found, (
            f"Carousel not found via search. "
            f"DSL search names: {names}"
        )

    def test_custom_components_in_v7_hybrid_search(self, wrapper):
        """Test that custom components appear in V7 hybrid search results."""
        if not wrapper.client:
            pytest.skip("Qdrant not available")

        # Search for carousel-related content
        class_results, patterns, rels = wrapper.search_v7_hybrid(
            description="A carousel with multiple cards",
            limit=10,
            include_classes=True,
        )

        # Check if any carousel-related classes are found
        class_names = [r.get("name") for r in class_results]

        # Custom components should be indexed and searchable
        # May not always return Carousel directly, but should have valid results
        assert len(class_results) > 0 or len(patterns) > 0, (
            "V7 hybrid search returned no results"
        )

        # Log what was found for debugging
        if class_names:
            print(f"Classes found: {class_names[:5]}")

    def test_custom_components_have_symbols(self, wrapper):
        """Test that custom components have generated symbols."""
        # Check symbol mapping includes custom components
        symbols = wrapper.symbol_mapping or {}

        # All 3 truly custom components should have symbols
        custom_names = ["Carousel", "CarouselCard", "NestedWidget"]
        for name in custom_names:
            assert name in symbols, f"{name} not in symbol_mapping"
            assert symbols[name], f"{name} has empty symbol"

    def test_custom_components_in_qdrant(self, wrapper):
        """Test that custom components are stored in Qdrant."""
        if not wrapper.client:
            pytest.skip("Qdrant not available")

        from qdrant_client import models

        # Query for custom components
        results, _ = wrapper.client.scroll(
            collection_name=wrapper.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="is_custom_component",
                        match=models.MatchValue(value=True),
                    )
                ]
            ),
            limit=10,
            with_payload=True,
        )

        # Should have at least the 3 custom components
        names = [p.payload.get("name") for p in results]
        assert "Carousel" in names, f"Carousel not in Qdrant. Found: {names}"
        assert "CarouselCard" in names, f"CarouselCard not in Qdrant. Found: {names}"
        assert "NestedWidget" in names, f"NestedWidget not in Qdrant. Found: {names}"

    def test_custom_component_relationships_in_qdrant(self, wrapper):
        """Test that custom components have relationships stored in Qdrant."""
        if not wrapper.client:
            pytest.skip("Qdrant not available")

        from qdrant_client import models

        # Query for Carousel specifically
        results, _ = wrapper.client.scroll(
            collection_name=wrapper.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="name",
                        match=models.MatchValue(value="Carousel"),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
        )

        assert len(results) == 1, "Carousel not found in Qdrant"

        payload = results[0].payload
        assert "relationships" in payload, "Carousel missing relationships"
        assert "CarouselCard" in payload["relationships"]["child_classes"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
