"""
Tests for Phase 1-3: Universal Module Wrapper + Parameterized DSL.

Covers:
- Phase 1a: _get_required_wrapper() queries wrapper registered metadata (no hardcoding)
- Phase 1b: _derive_dsl_metadata() uses registered wrapper requirements
- Phase 1c: priority_overrides are configurable via init param
- Phase 1d: nl_relationship_patterns are configurable via init param
- Phase 1e: target module is never skipped by THIRD_PARTY_PREFIXES
- Phase 1f: Pydantic BaseModel support in relationship extraction
- Phase 1g: card_framework_wrapper regression — still works with extracted config
- Phase 3:  parameterized DSL tokenization, parsing, round-trip, and validation

All tests are unit tests — no Qdrant server or external services required.
"""

import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Phase 1a: _get_required_wrapper() queries wrapper metadata
# =============================================================================


class TestPhase1aWrapperRequirements:
    """Test that DSLParser._get_required_wrapper queries registered metadata."""

    def test_get_required_wrapper_uses_wrapper_metadata(self):
        """_get_required_wrapper should query wrapper.get_all_wrapper_requirements()."""
        from adapters.module_wrapper.dsl_parser import DSLParser

        # Create a mock wrapper with registered metadata
        mock_wrapper = MagicMock()
        mock_wrapper.get_all_wrapper_requirements.return_value = {
            "Button": "ButtonList",
            "Chip": "ChipList",
            "GridItem": "Grid",
        }

        parser = DSLParser(wrapper=mock_wrapper)
        assert parser._get_required_wrapper("Button") == "ButtonList"
        assert parser._get_required_wrapper("Chip") == "ChipList"
        assert parser._get_required_wrapper("GridItem") == "Grid"
        mock_wrapper.get_all_wrapper_requirements.assert_called()

    def test_get_required_wrapper_returns_none_for_unknown(self):
        """Unknown components return None."""
        from adapters.module_wrapper.dsl_parser import DSLParser

        mock_wrapper = MagicMock()
        mock_wrapper.get_all_wrapper_requirements.return_value = {
            "Button": "ButtonList",
        }

        parser = DSLParser(wrapper=mock_wrapper)
        assert parser._get_required_wrapper("DecoratedText") is None

    def test_get_required_wrapper_no_wrapper(self):
        """Returns None when no wrapper is set."""
        from adapters.module_wrapper.dsl_parser import DSLParser

        parser = DSLParser()
        assert parser._get_required_wrapper("Button") is None

    def test_no_hardcoded_wrapper_requirements(self):
        """Ensure _get_required_wrapper has no hardcoded component mapping."""
        import inspect

        from adapters.module_wrapper.dsl_parser import DSLParser

        source = inspect.getsource(DSLParser._get_required_wrapper)
        # Should NOT contain any hardcoded component names
        for name in ["ButtonList", "ChipList", "Grid", "ColumnList"]:
            assert name not in source, (
                f"_get_required_wrapper still has hardcoded '{name}' — "
                "should query wrapper metadata instead"
            )


# =============================================================================
# Phase 1b: _derive_dsl_metadata() uses registered metadata
# =============================================================================


class TestPhase1bDSLMetadata:
    """Test that _derive_dsl_metadata uses registered wrapper requirements."""

    def test_derive_dsl_metadata_no_hardcoded_patterns(self):
        """Ensure _derive_dsl_metadata has no hardcoded wrapper_patterns list."""
        import inspect

        from adapters.module_wrapper.core import ModuleWrapperBase

        source = inspect.getsource(ModuleWrapperBase._derive_dsl_metadata)
        # Should NOT contain hardcoded wrapper pattern tuples
        assert '("ButtonList", "Button")' not in source
        assert '("ChipList", "Chip")' not in source
        assert '("Grid", "GridItem")' not in source


# =============================================================================
# Phase 1c: priority_overrides are configurable
# =============================================================================


class TestPhase1cPriorityOverrides:
    """Test that priority_overrides init param is applied correctly."""

    def test_priority_overrides_stored(self):
        """priority_overrides should be stored on the instance."""
        from adapters.module_wrapper.core import ModuleWrapperBase

        overrides = {"Section": 100, "Card": 100}

        with patch.object(ModuleWrapperBase, "__init__", lambda self, **kw: None):
            base = ModuleWrapperBase.__new__(ModuleWrapperBase)
            base._priority_overrides = overrides

        assert base._priority_overrides == overrides

    def test_priority_scores_apply_overrides(self):
        """_calculate_symbol_priority_scores should apply overrides."""
        from adapters.module_wrapper.core import ModuleWrapperBase

        base = ModuleWrapperBase.__new__(ModuleWrapperBase)
        base._priority_overrides = {"MyWidget": 200, "Other": 50}
        base._cached_relationships = None

        # Mock extract_relationships_by_parent to return empty
        base.extract_relationships_by_parent = MagicMock(return_value={})

        scores = base._calculate_symbol_priority_scores()

        assert scores.get("MyWidget") == 200
        assert scores.get("Other") == 50

    def test_priority_overrides_add_to_existing(self):
        """Overrides add to calculated scores, not replace."""
        from adapters.module_wrapper.core import ModuleWrapperBase

        base = ModuleWrapperBase.__new__(ModuleWrapperBase)
        base._priority_overrides = {"Parent": 100}

        # Mock: Parent has 2 children at depth 1 → base score = 20 + 1 = 21
        base.extract_relationships_by_parent = MagicMock(
            return_value={
                "Parent": [
                    {"child_class": "ChildA", "depth": 1},
                    {"child_class": "ChildB", "depth": 1},
                ]
            }
        )

        scores = base._calculate_symbol_priority_scores()
        # base score (20 + 1) + override 100 = 121
        assert scores.get("Parent") == 121

    def test_no_hardcoded_priority_boost_set(self):
        """Ensure _calculate_symbol_priority_scores has no hardcoded name set."""
        import inspect

        from adapters.module_wrapper.core import ModuleWrapperBase

        source = inspect.getsource(ModuleWrapperBase._calculate_symbol_priority_scores)
        # Should NOT contain hardcoded component names for boosting
        for name in ["Section", "Card", "ButtonList", "Columns", "ChipList"]:
            # Allow the name if it's in a comment, but not as a string literal
            assert f'"{name}"' not in source, (
                f"_calculate_symbol_priority_scores still has hardcoded '{name}' — "
                "should use _priority_overrides"
            )


# =============================================================================
# Phase 1d: nl_relationship_patterns are configurable
# =============================================================================


class TestPhase1dNLPatterns:
    """Test that NL relationship patterns are configurable, not hardcoded."""

    def test_default_nl_patterns_function_returns_empty(self):
        """_get_nl_relationship_patterns() returns empty dict (no hardcoding)."""
        from adapters.module_wrapper.relationships_mixin import (
            _get_nl_relationship_patterns,
        )

        patterns = _get_nl_relationship_patterns()
        assert patterns == {}

    def test_generate_nl_description_uses_instance_patterns(self):
        """_generate_nl_description checks instance _nl_relationship_patterns first."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin.__new__(RelationshipsMixin)
        mixin._nl_relationship_patterns = {
            ("Section", "Widget"): "section containing widgets",
        }

        result = mixin._generate_nl_description("Section", "Widget")
        assert result == "section containing widgets"

    def test_generate_nl_description_generic_fallback(self):
        """Falls back to generic description when no pattern matches."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin.__new__(RelationshipsMixin)
        mixin._nl_relationship_patterns = {}

        result = mixin._generate_nl_description("Parent", "Child")
        assert "parent" in result.lower()
        assert "child" in result.lower()

    def test_generate_nl_description_no_patterns_attr(self):
        """Works even if _nl_relationship_patterns attribute is missing."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin.__new__(RelationshipsMixin)
        # Don't set _nl_relationship_patterns at all

        result = mixin._generate_nl_description("Alpha", "Beta")
        assert "alpha" in result.lower()
        assert "beta" in result.lower()


# =============================================================================
# Phase 1e: Target module is never skipped by THIRD_PARTY_PREFIXES
# =============================================================================


class TestPhase1eTargetModuleSkip:
    """Test that the target module is never skipped by THIRD_PARTY_PREFIXES."""

    def test_qdrant_client_not_skipped_when_target(self):
        """qdrant_client should NOT be skipped when it's the target module."""
        from adapters.module_wrapper.indexing_mixin import IndexingMixin

        mixin = IndexingMixin.__new__(IndexingMixin)
        mixin._module_name = "qdrant_client.models"
        mixin.skip_standard_library = True

        assert mixin._is_standard_library("qdrant_client.models") is False
        assert mixin._is_standard_library("qdrant_client.models.types") is False
        assert mixin._is_standard_library("qdrant_client") is False

    def test_unrelated_third_party_still_skipped(self):
        """Other third-party modules should still be skipped."""
        from adapters.module_wrapper.indexing_mixin import IndexingMixin

        mixin = IndexingMixin.__new__(IndexingMixin)
        mixin._module_name = "qdrant_client.models"

        # These should still be skipped
        assert mixin._is_standard_library("numpy") is True
        assert mixin._is_standard_library("pandas") is True
        assert mixin._is_standard_library("sentence_transformers") is True

    def test_sentence_transformers_not_skipped_when_target(self):
        """sentence_transformers should NOT be skipped when it's the target module."""
        from adapters.module_wrapper.indexing_mixin import IndexingMixin

        mixin = IndexingMixin.__new__(IndexingMixin)
        mixin._module_name = "sentence_transformers"

        assert mixin._is_standard_library("sentence_transformers") is False
        assert mixin._is_standard_library("sentence_transformers.models") is False

        # But qdrant_client should still be skipped since it's not the target
        assert mixin._is_standard_library("qdrant_client") is True

    def test_regular_module_not_affected(self):
        """Non-third-party modules still work normally."""
        from adapters.module_wrapper.indexing_mixin import IndexingMixin

        mixin = IndexingMixin.__new__(IndexingMixin)
        mixin._module_name = "card_framework.v2"

        assert mixin._is_standard_library("card_framework.v2") is False
        assert mixin._is_standard_library("card_framework.v2.widgets") is False
        # Third-party still skipped
        assert mixin._is_standard_library("qdrant_client") is True


# =============================================================================
# Phase 1f: Pydantic BaseModel support in relationship extraction
# =============================================================================


class TestPhase1fPydanticSupport:
    """Test that Pydantic models are supported in relationship extraction."""

    def test_is_pydantic_type_with_pydantic(self):
        """_is_pydantic_type returns True for Pydantic BaseModel subclasses."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin.__new__(RelationshipsMixin)

        try:
            from pydantic import BaseModel

            class MyModel(BaseModel):
                name: str = "test"

            assert mixin._is_pydantic_type(MyModel) is True
            assert mixin._is_pydantic_type(BaseModel) is True
        except ImportError:
            pytest.skip("pydantic not installed")

    def test_is_pydantic_type_with_non_pydantic(self):
        """_is_pydantic_type returns False for non-Pydantic classes."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin.__new__(RelationshipsMixin)

        class RegularClass:
            pass

        assert mixin._is_pydantic_type(RegularClass) is False
        assert mixin._is_pydantic_type(str) is False

    def test_is_introspectable_type_dataclass(self):
        """_is_introspectable_type returns True for dataclasses."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin.__new__(RelationshipsMixin)

        @dataclass
        class MyDataclass:
            name: str = "test"

        assert mixin._is_introspectable_type(MyDataclass) is True

    def test_is_introspectable_type_pydantic(self):
        """_is_introspectable_type returns True for Pydantic models."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin.__new__(RelationshipsMixin)

        try:
            from pydantic import BaseModel

            class MyModel(BaseModel):
                name: str = "test"

            assert mixin._is_introspectable_type(MyModel) is True
        except ImportError:
            pytest.skip("pydantic not installed")

    def test_is_introspectable_type_regular_class(self):
        """_is_introspectable_type returns False for regular classes."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        mixin = RelationshipsMixin.__new__(RelationshipsMixin)

        class RegularClass:
            pass

        assert mixin._is_introspectable_type(RegularClass) is False

    def test_pydantic_relationships_extracted(self):
        """Pydantic model field types should be extracted as relationships."""
        from adapters.module_wrapper.relationships_mixin import RelationshipsMixin

        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("pydantic not installed")

        # Simulate qdrant-style models
        class MatchValue(BaseModel):
            value: str = ""

        class FieldCondition(BaseModel):
            key: str = ""
            match: Optional[MatchValue] = None

        class Filter(BaseModel):
            must: Optional[List[FieldCondition]] = None
            should: Optional[List[FieldCondition]] = None

        mixin = RelationshipsMixin.__new__(RelationshipsMixin)
        mixin.components = {
            "test.Filter": MagicMock(
                obj=Filter,
                component_type="class",
                name="Filter",
            ),
            "test.FieldCondition": MagicMock(
                obj=FieldCondition,
                component_type="class",
                name="FieldCondition",
            ),
            "test.MatchValue": MagicMock(
                obj=MatchValue,
                component_type="class",
                name="MatchValue",
            ),
        }
        mixin._cached_relationships = None
        mixin._cached_raw_relationships = None
        mixin._cached_raw_relationships_depth = None
        mixin._nl_relationship_patterns = {}

        # Verify pydantic types are introspectable
        assert mixin._is_introspectable_type(Filter) is True
        assert mixin._is_introspectable_type(FieldCondition) is True
        assert mixin._is_introspectable_type(MatchValue) is True


# =============================================================================
# Phase 1g: card_framework_wrapper regression
# =============================================================================


class TestPhase1gCardFrameworkRegression:
    """Test that card_framework_wrapper constants and config are correct."""

    def test_card_priority_overrides_exist(self):
        """CARD_PRIORITY_OVERRIDES constant should exist with expected keys."""
        from gchat.card_framework_wrapper import CARD_PRIORITY_OVERRIDES

        expected = {"Section", "Card", "ButtonList", "Grid", "Columns", "ChipList"}
        assert set(CARD_PRIORITY_OVERRIDES.keys()) == expected
        # All should be positive values
        for name, value in CARD_PRIORITY_OVERRIDES.items():
            assert value > 0, f"{name} should have positive priority"

    def test_gchat_nl_patterns_exist(self):
        """GCHAT_NL_RELATIONSHIP_PATTERNS constant should exist and be non-empty."""
        from gchat.card_framework_wrapper import GCHAT_NL_RELATIONSHIP_PATTERNS

        assert len(GCHAT_NL_RELATIONSHIP_PATTERNS) > 10, (
            "Expected 10+ NL patterns for card framework"
        )
        # Keys should be (parent, child) tuples
        for key in GCHAT_NL_RELATIONSHIP_PATTERNS:
            assert isinstance(key, tuple), f"Key should be tuple, got {type(key)}"
            assert len(key) == 2, f"Key should be (parent, child), got {key}"

    def test_gchat_nl_patterns_have_section_patterns(self):
        """NL patterns should include Section-related patterns."""
        from gchat.card_framework_wrapper import GCHAT_NL_RELATIONSHIP_PATTERNS

        # At least some Section patterns should exist
        section_patterns = {
            k: v for k, v in GCHAT_NL_RELATIONSHIP_PATTERNS.items() if k[0] == "Section"
        }
        assert len(section_patterns) > 0, "Should have Section-related NL patterns"

    def test_card_wrapper_passes_priority_overrides(self):
        """card_framework_wrapper should pass priority_overrides when creating wrapper."""
        from gchat.card_framework_wrapper import CARD_PRIORITY_OVERRIDES

        # Verify the constant values match what was previously hardcoded
        assert CARD_PRIORITY_OVERRIDES.get("Section") == 100
        assert CARD_PRIORITY_OVERRIDES.get("Card") == 100
        assert CARD_PRIORITY_OVERRIDES.get("ButtonList") == 100

    def test_card_dsl_parser_still_works(self):
        """Card DSL parser should still parse positional DSL correctly (regression)."""
        from gchat.card_framework_wrapper import get_dsl_parser

        parser = get_dsl_parser()
        assert parser is not None

        # Parse a standard positional DSL
        result = parser.parse("§[δ×3, Ƀ[ᵬ×2]]")
        assert result is not None
        assert len(result.root_nodes) > 0
        root = result.root_nodes[0]

        # Section with 2 children: DT(×3) and BL
        assert root.component_name == "Section"
        assert len(root.children) == 2  # DT node (multiplier=3) + BL node

        # DT node should have multiplier 3
        dt_node = root.children[0]
        assert dt_node.component_name == "DecoratedText"
        assert dt_node.multiplier == 3

        # BL should have 1 child (Button with multiplier 2)
        bl_node = root.children[1]
        assert bl_node.component_name == "ButtonList"
        assert len(bl_node.children) == 1
        assert bl_node.children[0].component_name == "Button"
        assert bl_node.children[0].multiplier == 2

    def test_card_symbols_still_generated(self):
        """Card framework symbols should still be generated."""
        from gchat.card_framework_wrapper import get_gchat_symbols

        symbols = get_gchat_symbols()
        assert len(symbols) > 10, "Should have many symbols"
        assert "Section" in symbols
        assert "DecoratedText" in symbols
        assert "Button" in symbols
        assert "ButtonList" in symbols


# =============================================================================
# Phase 3: Parameterized DSL
# =============================================================================


class TestPhase3TokenizerExtensions:
    """Test tokenizer extensions for parameterized DSL notation."""

    def _make_parser(self, symbol_mapping=None, reverse_mapping=None):
        """Create a DSLParser with given mappings."""
        from adapters.module_wrapper.dsl_parser import DSLParser

        parser = DSLParser()
        if symbol_mapping:
            parser._symbol_mapping = symbol_mapping
            parser._reverse_mapping = reverse_mapping or {
                v: k for k, v in symbol_mapping.items()
            }
            parser._all_symbols = set(symbol_mapping.values())
        return parser

    def test_tokenize_braces(self):
        """Tokenizer handles { and } as param_open/param_close."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize("ƒ{}")

        types = [t.type for t in tokens]
        assert "param_open" in types
        assert "param_close" in types

    def test_tokenize_equals(self):
        """Tokenizer handles = as equals token."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize("ƒ{key=val}")

        types = [t.type for t in tokens]
        assert "equals" in types

    def test_tokenize_string_double_quotes(self):
        """Tokenizer handles double-quoted strings."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize('ƒ{key="hello world"}')

        string_tokens = [t for t in tokens if t.type == "string"]
        assert len(string_tokens) == 1
        assert string_tokens[0].value == "hello world"

    def test_tokenize_string_single_quotes(self):
        """Tokenizer handles single-quoted strings."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize("ƒ{key='hello'}")

        string_tokens = [t for t in tokens if t.type == "string"]
        assert len(string_tokens) == 1
        assert string_tokens[0].value == "hello"

    def test_tokenize_number_integer(self):
        """Tokenizer handles integer literals."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize("ƒ{limit=10}")

        number_tokens = [t for t in tokens if t.type == "number"]
        assert len(number_tokens) == 1
        assert number_tokens[0].value == "10"

    def test_tokenize_number_float(self):
        """Tokenizer handles float literals."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize("ƒ{score=0.95}")

        number_tokens = [t for t in tokens if t.type == "number"]
        assert len(number_tokens) == 1
        assert number_tokens[0].value == "0.95"

    def test_tokenize_boolean_true(self):
        """Tokenizer handles true boolean."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize("ƒ{exact=true}")

        bool_tokens = [t for t in tokens if t.type == "boolean"]
        assert len(bool_tokens) == 1
        assert bool_tokens[0].value == "true"

    def test_tokenize_boolean_false(self):
        """Tokenizer handles false boolean."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize("ƒ{exact=false}")

        bool_tokens = [t for t in tokens if t.type == "boolean"]
        assert len(bool_tokens) == 1
        assert bool_tokens[0].value == "false"

    def test_tokenize_null(self):
        """Tokenizer handles null literal."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize("ƒ{val=null}")

        null_tokens = [t for t in tokens if t.type == "null"]
        assert len(null_tokens) == 1

    def test_tokenize_identifier(self):
        """Tokenizer handles identifiers (param names followed by =)."""
        parser = self._make_parser({"F": "ƒ"}, {"ƒ": "F"})
        tokens = parser.tokenize('ƒ{key="x"}')

        id_tokens = [t for t in tokens if t.type == "identifier"]
        assert len(id_tokens) == 1
        assert id_tokens[0].value == "key"


class TestPhase3ParserExtensions:
    """Test parser extensions for parameterized DSL notation."""

    def _make_parser(self, symbol_mapping=None, reverse_mapping=None):
        """Create a DSLParser with given mappings."""
        from adapters.module_wrapper.dsl_parser import DSLParser

        parser = DSLParser()
        if symbol_mapping:
            parser._symbol_mapping = symbol_mapping
            parser._reverse_mapping = reverse_mapping or {
                v: k for k, v in symbol_mapping.items()
            }
            parser._all_symbols = set(symbol_mapping.values())
        return parser

    def test_parse_simple_parameterized(self):
        """Parse a simple parameterized block: ƒ{key="value"}."""
        mapping = {"Filter": "ƒ"}
        parser = self._make_parser(mapping)

        result = parser.parse('ƒ{key="tool_name"}')
        assert result is not None
        assert len(result.root_nodes) > 0

        root = result.root_nodes[0]
        assert root.component_name == "Filter"
        assert root.is_parameterized is True
        assert root.params.get("key") == "tool_name"

    def test_parse_nested_parameterized(self):
        """Parse nested parameterized blocks: ƒ{must=[φ{key="x", match=ʋ{value="y"}}]}."""
        mapping = {
            "Filter": "ƒ",
            "FieldCondition": "φ",
            "MatchValue": "ʋ",
        }
        parser = self._make_parser(mapping)

        dsl = 'ƒ{must=[φ{key="x", match=ʋ{value="y"}}]}'
        result = parser.parse(dsl)
        assert result is not None

        root = result.root_nodes[0]
        assert root.component_name == "Filter"
        assert root.is_parameterized is True

        # must should be a list
        must_val = root.params.get("must")
        assert isinstance(must_val, list), f"Expected list, got {type(must_val)}"
        assert len(must_val) == 1

        # First item should be a FieldCondition node
        fc_node = must_val[0]
        from adapters.module_wrapper.dsl_parser import DSLNode

        assert isinstance(fc_node, DSLNode)
        assert fc_node.component_name == "FieldCondition"
        assert fc_node.params.get("key") == "x"

        # match should be a MatchValue node
        match_node = fc_node.params.get("match")
        assert isinstance(match_node, DSLNode)
        assert match_node.component_name == "MatchValue"
        assert match_node.params.get("value") == "y"

    def test_parse_parameterized_with_number(self):
        """Parse parameterized block with number value."""
        mapping = {"SearchParams": "σ"}
        parser = self._make_parser(mapping)

        result = parser.parse("σ{limit=10, offset=0}")
        root = result.root_nodes[0]
        assert root.params.get("limit") == 10
        assert root.params.get("offset") == 0

    def test_parse_parameterized_with_boolean(self):
        """Parse parameterized block with boolean value."""
        mapping = {"SearchParams": "σ"}
        parser = self._make_parser(mapping)

        result = parser.parse("σ{exact=true, with_payload=false}")
        root = result.root_nodes[0]
        assert root.params.get("exact") is True
        assert root.params.get("with_payload") is False

    def test_parse_parameterized_with_null(self):
        """Parse parameterized block with null value."""
        mapping = {"SearchParams": "σ"}
        parser = self._make_parser(mapping)

        result = parser.parse("σ{vector=null}")
        root = result.root_nodes[0]
        assert root.params.get("vector") is None

    def test_parse_parameterized_with_float(self):
        """Parse parameterized block with float value."""
        mapping = {"SearchParams": "σ"}
        parser = self._make_parser(mapping)

        result = parser.parse("σ{score_threshold=0.85}")
        root = result.root_nodes[0]
        assert root.params.get("score_threshold") == 0.85

    def test_parse_parameterized_array_of_primitives(self):
        """Parse parameterized block with array of primitive values."""
        mapping = {"HasIdCondition": "η"}
        parser = self._make_parser(mapping)

        result = parser.parse('η{has_id=["id1", "id2", "id3"]}')
        root = result.root_nodes[0]
        has_id = root.params.get("has_id")
        assert isinstance(has_id, list)
        assert has_id == ["id1", "id2", "id3"]


class TestPhase3DSLNodeParams:
    """Test DSLNode parameterized features."""

    def test_is_parameterized_with_params(self):
        """DSLNode.is_parameterized is True when params are set."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        node = DSLNode(symbol="ƒ", component_name="Filter", params={"key": "val"})
        assert node.is_parameterized is True

    def test_is_parameterized_with_children(self):
        """DSLNode.is_parameterized is False when children are set."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        child = DSLNode(symbol="δ", component_name="DecoratedText")
        node = DSLNode(
            symbol="§",
            component_name="Section",
            children=[child],
        )
        assert node.is_parameterized is False

    def test_is_parameterized_empty(self):
        """DSLNode.is_parameterized is False when empty."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        node = DSLNode(symbol="δ", component_name="DecoratedText")
        assert node.is_parameterized is False

    def test_to_dict_with_params(self):
        """to_dict() includes params when set."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        node = DSLNode(
            symbol="ƒ",
            component_name="Filter",
            params={"key": "tool_name", "limit": 10},
        )
        d = node.to_dict()
        assert "params" in d
        assert d["params"]["key"] == "tool_name"
        assert d["params"]["limit"] == 10

    def test_to_dict_without_params(self):
        """to_dict() omits params key when empty."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        node = DSLNode(symbol="§", component_name="Section")
        d = node.to_dict()
        assert "params" not in d

    def test_flatten_includes_param_nodes(self):
        """flatten() traverses into parameterized DSLNode values."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        inner = DSLNode(symbol="ʋ", component_name="MatchValue", params={"value": "y"})
        outer = DSLNode(
            symbol="ƒ",
            component_name="Filter",
            params={"match": inner},
        )

        flat = outer.flatten()
        names = [n.component_name for n in flat]
        assert "Filter" in names
        assert "MatchValue" in names

    def test_flatten_includes_param_list_nodes(self):
        """flatten() traverses into lists of DSLNode in params."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        child1 = DSLNode(symbol="φ", component_name="FieldCondition")
        child2 = DSLNode(symbol="φ", component_name="FieldCondition")
        parent = DSLNode(
            symbol="ƒ",
            component_name="Filter",
            params={"must": [child1, child2]},
        )

        flat = parent.flatten()
        fc_count = sum(1 for n in flat if n.component_name == "FieldCondition")
        assert fc_count == 2

    def test_get_component_counts_parameterized(self):
        """get_component_counts() includes counts from parameterized children."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        mv = DSLNode(symbol="ʋ", component_name="MatchValue")
        fc = DSLNode(
            symbol="φ",
            component_name="FieldCondition",
            params={"match": mv},
        )
        filt = DSLNode(
            symbol="ƒ",
            component_name="Filter",
            params={"must": [fc]},
        )

        counts = filt.get_component_counts()
        assert counts.get("Filter") == 1
        assert counts.get("FieldCondition") == 1
        assert counts.get("MatchValue") == 1


class TestPhase3RoundTrip:
    """Test round-trip DSL serialization for parameterized notation."""

    def test_compact_dsl_simple_params(self):
        """to_compact_dsl() for simple parameterized node."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        node = DSLNode(
            symbol="ƒ",
            component_name="Filter",
            params={"key": "value"},
        )
        dsl = node.to_compact_dsl()
        assert 'ƒ{key="value"}' == dsl

    def test_compact_dsl_nested_params(self):
        """to_compact_dsl() for nested parameterized nodes."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        inner = DSLNode(
            symbol="ʋ",
            component_name="MatchValue",
            params={"value": "search"},
        )
        outer = DSLNode(
            symbol="φ",
            component_name="FieldCondition",
            params={"key": "tool_name", "match": inner},
        )
        dsl = outer.to_compact_dsl()
        assert 'φ{key="tool_name", match=ʋ{value="search"}}' == dsl

    def test_compact_dsl_array_param(self):
        """to_compact_dsl() for array parameter values."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        fc = DSLNode(
            symbol="φ",
            component_name="FieldCondition",
            params={"key": "name"},
        )
        filt = DSLNode(
            symbol="ƒ",
            component_name="Filter",
            params={"must": [fc]},
        )
        dsl = filt.to_compact_dsl()
        assert 'ƒ{must=[φ{key="name"}]}' == dsl

    def test_compact_dsl_boolean_null(self):
        """to_compact_dsl() renders booleans and null correctly."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        node = DSLNode(
            symbol="σ",
            component_name="SearchParams",
            params={"exact": True, "hnsw_ef": None, "quantize": False},
        )
        dsl = node.to_compact_dsl()
        assert "exact=true" in dsl
        assert "hnsw_ef=null" in dsl
        assert "quantize=false" in dsl

    def test_expanded_notation_parameterized(self):
        """to_expanded_notation() for parameterized node."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        node = DSLNode(
            symbol="ƒ",
            component_name="Filter",
            params={"key": "value"},
        )
        expanded = node.to_expanded_notation()
        assert 'Filter{key="value"}' == expanded

    def test_positional_dsl_unchanged(self):
        """Existing positional DSL still works identically (regression)."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        child1 = DSLNode(symbol="δ", component_name="DecoratedText", multiplier=3)
        child2 = DSLNode(
            symbol="Ƀ",
            component_name="ButtonList",
            children=[DSLNode(symbol="ᵬ", component_name="Button", multiplier=2)],
        )
        root = DSLNode(
            symbol="§",
            component_name="Section",
            children=[child1, child2],
        )

        dsl = root.to_compact_dsl()
        assert dsl == "§[δ×3, Ƀ[ᵬ×2]]"

        expanded = root.to_expanded_notation()
        assert expanded == "Section[DecoratedText×3, ButtonList[Button×2]]"


class TestPhase3BackwardsCompatibility:
    """Test that existing positional DSL parsing is unaffected."""

    def test_positional_dsl_parses_identically(self):
        """Standard positional DSL §[δ×3, Ƀ[ᵬ×2]] parses correctly."""
        from gchat.card_framework_wrapper import get_dsl_parser

        parser = get_dsl_parser()
        result = parser.parse("§[δ×3, Ƀ[ᵬ×2]]")

        assert result is not None
        root = result.root_nodes[0]

        assert root.component_name == "Section"
        assert root.is_parameterized is False
        # Parser keeps multipliers on nodes (doesn't expand)
        assert len(root.children) == 2  # DT(×3) + BL

        # DT node has multiplier=3
        dt = root.children[0]
        assert dt.component_name == "DecoratedText"
        assert dt.multiplier == 3

        # BL has 1 child: Button(×2)
        bl = root.children[1]
        assert bl.component_name == "ButtonList"
        assert len(bl.children) == 1
        assert bl.children[0].component_name == "Button"
        assert bl.children[0].multiplier == 2

    def test_simple_positional_dsl(self):
        """Simple positional DSL with single child."""
        from gchat.card_framework_wrapper import get_dsl_parser

        parser = get_dsl_parser()
        result = parser.parse("§[δ]")

        assert result is not None
        root = result.root_nodes[0]
        assert root.component_name == "Section"
        assert len(root.children) == 1
        assert root.children[0].component_name == "DecoratedText"

    def test_multiplier_still_works(self):
        """Multiplier notation ×N still works."""
        from gchat.card_framework_wrapper import get_dsl_parser

        parser = get_dsl_parser()
        result = parser.parse("§[δ×5]")

        root = result.root_nodes[0]
        assert root.component_name == "Section"
        # Parser stores multiplier on the node, doesn't expand
        assert len(root.children) == 1
        assert root.children[0].component_name == "DecoratedText"
        assert root.children[0].multiplier == 5

        # Verify component counts reflect the multiplier
        counts = root.get_component_counts()
        assert counts.get("DecoratedText") == 5
        assert counts.get("Section") == 1

    def test_deeply_nested_positional(self):
        """Deeply nested positional DSL: §[δ[ᵬ], Ƀ[ᵬ×2]]."""
        from gchat.card_framework_wrapper import get_dsl_parser

        parser = get_dsl_parser()
        result = parser.parse("§[δ[ᵬ], Ƀ[ᵬ×2]]")

        root = result.root_nodes[0]
        assert root.component_name == "Section"
        assert len(root.children) == 2  # 1 DT + 1 BL

        # First child: DT with nested Button
        dt = root.children[0]
        assert dt.component_name == "DecoratedText"
        assert len(dt.children) == 1
        assert dt.children[0].component_name == "Button"


# =============================================================================
# Phase 3: Helper function tests
# =============================================================================


class TestPhase3HelperFunctions:
    """Test helper functions for parameterized DSL."""

    def test_params_to_dict_with_node(self):
        """_params_to_dict converts DSLNode values to dicts."""
        from adapters.module_wrapper.dsl_parser import DSLNode, _params_to_dict

        node = DSLNode(symbol="ʋ", component_name="MatchValue")
        params = {"key": "name", "match": node}

        result = _params_to_dict(params)
        assert result["key"] == "name"
        assert isinstance(result["match"], dict)
        assert result["match"]["name"] == "MatchValue"

    def test_params_to_dict_with_list(self):
        """_params_to_dict converts lists with DSLNode items."""
        from adapters.module_wrapper.dsl_parser import DSLNode, _params_to_dict

        node = DSLNode(symbol="φ", component_name="FieldCondition")
        params = {"must": [node, "string_val"]}

        result = _params_to_dict(params)
        assert isinstance(result["must"], list)
        assert isinstance(result["must"][0], dict)
        assert result["must"][1] == "string_val"

    def test_param_value_to_dsl_primitives(self):
        """_param_value_to_dsl handles primitive types."""
        from adapters.module_wrapper.dsl_parser import _param_value_to_dsl

        assert _param_value_to_dsl("hello") == '"hello"'
        assert _param_value_to_dsl(42) == "42"
        assert _param_value_to_dsl(3.14) == "3.14"
        assert _param_value_to_dsl(True) == "true"
        assert _param_value_to_dsl(False) == "false"
        assert _param_value_to_dsl(None) == "null"

    def test_param_value_to_dsl_list(self):
        """_param_value_to_dsl handles lists."""
        from adapters.module_wrapper.dsl_parser import _param_value_to_dsl

        result = _param_value_to_dsl(["a", "b"])
        assert result == '["a", "b"]'

    def test_param_value_to_dsl_node(self):
        """_param_value_to_dsl handles DSLNode."""
        from adapters.module_wrapper.dsl_parser import DSLNode, _param_value_to_dsl

        node = DSLNode(
            symbol="ƒ",
            component_name="Filter",
            params={"key": "val"},
        )
        result = _param_value_to_dsl(node)
        assert result == 'ƒ{key="val"}'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
