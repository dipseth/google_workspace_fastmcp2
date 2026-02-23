"""
Tests for qdrant_client.models wrapping validation.

Validates that ModuleWrapper successfully wraps qdrant_client.models
and produces the outputs needed by Phase 4 (query_builder, executor, tools).

These tests use the REAL wrapper singleton, not mocks. They verify:
1. Wrapper initialization succeeds
2. Key Qdrant classes are indexed as components
3. Symbols are generated for key classes
4. Pydantic relationships are extracted (Filter → FieldCondition → MatchValue)
5. DSL parser works with real symbol mappings
6. Parameterized DSL round-trips through parse → build work with real classes
7. Built objects are real qdrant_client.models instances

No Qdrant server required — only wrapping + parsing + instantiation is tested.
"""

import pytest
from qdrant_client import models as qmodels

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def wrapper():
    """Get the real qdrant_client.models wrapper (singleton, cached across tests)."""
    from middleware.qdrant_core.qdrant_models_wrapper import (
        get_qdrant_models_wrapper,
    )

    return get_qdrant_models_wrapper(force_reinitialize=True)


@pytest.fixture(scope="module")
def parser(wrapper):
    """Get a DSL parser configured for qdrant_client.models."""
    return wrapper.get_dsl_parser()


@pytest.fixture(scope="module")
def symbols(wrapper):
    """Get the symbol mapping (component_name → symbol)."""
    return wrapper.symbol_mapping


@pytest.fixture(scope="module")
def reverse_symbols(wrapper):
    """Get the reverse symbol mapping (symbol → component_name)."""
    return wrapper.reverse_symbol_mapping


# =============================================================================
# 1. Wrapper Initialization
# =============================================================================


class TestWrapperInitialization:
    """Verify the wrapper initializes and indexes qdrant_client.models."""

    def test_wrapper_not_none(self, wrapper):
        assert wrapper is not None

    def test_components_populated(self, wrapper):
        assert wrapper.components is not None
        assert len(wrapper.components) > 0

    def test_has_class_components(self, wrapper):
        class_count = sum(
            1 for c in wrapper.components.values() if c.component_type == "class"
        )
        # qdrant_client.models has dozens of Pydantic model classes
        assert class_count >= 10, f"Expected >=10 classes, got {class_count}"

    def test_module_name(self, wrapper):
        assert "qdrant_client" in wrapper.module_name


# =============================================================================
# 2. Key Classes Indexed
# =============================================================================


# These are the classes Phase 4 QueryBuilder needs to instantiate
REQUIRED_CLASSES = [
    "Filter",
    "FieldCondition",
    "MatchValue",
    "MatchText",
    "MatchAny",
    "HasIdCondition",
    "IsEmptyCondition",
    "IsNullCondition",
    "Range",
]

# Nice-to-have but not strictly required for Phase 4
OPTIONAL_CLASSES = [
    "DatetimeRange",
    "GeoBoundingBox",
    "GeoRadius",
    "NestedCondition",
    "SearchParams",
    "QuantizationSearchParams",
]


class TestKeyClassesIndexed:
    """Verify that key qdrant_client.models classes are indexed as components."""

    @pytest.mark.parametrize("class_name", REQUIRED_CLASSES)
    def test_required_class_indexed(self, wrapper, class_name):
        """Each required class must appear as a component."""
        matching = [
            name
            for name in wrapper.components
            if name == class_name or name.endswith(f".{class_name}")
        ]
        assert len(matching) > 0, (
            f"{class_name} not found in components. "
            f"Available: {sorted(wrapper.components.keys())[:20]}..."
        )

    @pytest.mark.parametrize("class_name", REQUIRED_CLASSES)
    def test_required_class_has_obj_ref(self, wrapper, class_name):
        """Each required class component must have a reference to the actual class."""
        matching = [
            wrapper.components[name]
            for name in wrapper.components
            if name == class_name or name.endswith(f".{class_name}")
        ]
        assert len(matching) > 0
        component = matching[0]
        assert component.obj is not None, (
            f"{class_name} component has no .obj reference"
        )
        # Verify it's actually a class (not a function or instance)
        assert isinstance(component.obj, type), (
            f"{class_name} .obj is {type(component.obj)}, expected a class"
        )

    @pytest.mark.parametrize("class_name", REQUIRED_CLASSES)
    def test_required_class_is_pydantic(self, wrapper, class_name):
        """Each required class should be a Pydantic BaseModel subclass."""
        from pydantic import BaseModel

        matching = [
            wrapper.components[name]
            for name in wrapper.components
            if name == class_name or name.endswith(f".{class_name}")
        ]
        component = matching[0]
        assert issubclass(component.obj, BaseModel), (
            f"{class_name} is not a Pydantic BaseModel subclass"
        )

    @pytest.mark.parametrize("class_name", OPTIONAL_CLASSES)
    def test_optional_class_indexed(self, wrapper, class_name):
        """Optional classes should also be indexed (soft check)."""
        matching = [
            name
            for name in wrapper.components
            if name == class_name or name.endswith(f".{class_name}")
        ]
        if not matching:
            pytest.skip(f"{class_name} not indexed (optional)")


# =============================================================================
# 3. Symbol Generation
# =============================================================================


class TestSymbolGeneration:
    """Verify symbols are generated for key classes."""

    def test_symbols_not_empty(self, symbols):
        assert len(symbols) > 0

    @pytest.mark.parametrize("class_name", REQUIRED_CLASSES)
    def test_required_class_has_symbol(self, symbols, class_name):
        """Each required class should have a symbol assigned."""
        # symbol_mapping keys might be full paths or short names
        matching = [
            (name, sym)
            for name, sym in symbols.items()
            if name == class_name or name.endswith(f".{class_name}")
        ]
        assert len(matching) > 0, (
            f"No symbol for {class_name}. "
            f"Available symbols: {list(symbols.keys())[:20]}..."
        )

    def test_symbols_are_unicode_or_fallback(self, symbols):
        """Primary symbols should be single Unicode chars; overflow uses multi-char fallbacks."""
        unicode_count = 0
        fallback_count = 0
        for name, sym in symbols.items():
            if len(sym) == 1 and ord(sym) > 127:
                unicode_count += 1
            else:
                # Fallback symbols like 'S_0', 'C_1' are acceptable when pool exhausted
                assert "_" in sym or len(sym) == 1, (
                    f"Symbol for {name} is '{sym}' — not Unicode and not a fallback pattern"
                )
                fallback_count += 1
        # qdrant_client.models has 300+ classes, so most get fallback symbols.
        # Key filter/query types should still get Unicode (they're indexed first).
        assert unicode_count > 0, "No Unicode symbols generated"
        assert unicode_count >= 50, (
            f"Expected >=50 Unicode symbols, got {unicode_count} "
            f"(fallbacks: {fallback_count})"
        )

    def test_symbols_unique(self, symbols):
        """All symbols should be unique (no two classes share a symbol)."""
        seen = {}
        for name, sym in symbols.items():
            if sym in seen:
                pytest.fail(
                    f"Duplicate symbol '{sym}': used by both {seen[sym]} and {name}"
                )
            seen[sym] = name

    def test_reverse_mapping_consistent(self, symbols, reverse_symbols):
        """reverse_symbol_mapping should be the inverse of symbol_mapping."""
        for name, sym in symbols.items():
            assert sym in reverse_symbols, f"Symbol '{sym}' not in reverse mapping"
            assert reverse_symbols[sym] == name, (
                f"Reverse mapping mismatch: {sym} → {reverse_symbols[sym]}, expected {name}"
            )


# =============================================================================
# 4. Relationship Extraction
# =============================================================================


class TestRelationshipExtraction:
    """Verify Pydantic field relationships are extracted."""

    def test_relationships_not_empty(self, wrapper):
        rels = wrapper.relationships
        assert rels is not None
        assert len(rels) > 0

    def test_filter_has_relationships(self, wrapper):
        """Filter should have extracted relationships (at least simple Optional fields).

        NOTE: Complex Union fields like must/should/must_not (Union[List[T], T, None])
        are not yet unwrapped by the relationship extractor. Only simple Optional fields
        like min_should: Optional[MinShould] are extracted.
        """
        rels = wrapper.relationships
        filter_children = None
        for parent, children in rels.items():
            if parent == "Filter" or parent.endswith(".Filter"):
                filter_children = children
                break

        assert filter_children is not None, (
            f"No relationships found for Filter. Parents: {list(rels.keys())[:20]}..."
        )
        # MinShould is extracted from Filter.min_should (simple Optional field)
        child_names = [
            c if isinstance(c, str) else c.get("child_class", "")
            for c in filter_children
        ]
        min_should_found = any("MinShould" in str(c) for c in child_names)
        assert min_should_found, f"MinShould not in Filter's children: {child_names}"

    def test_fieldcondition_has_relationships(self, wrapper):
        """FieldCondition should have extracted relationships for simple Optional fields.

        NOTE: The match field (Union[MatchValue, MatchText, ...]) is a complex Union,
        so Match* types are not extracted. Only simple Optional fields like
        geo_bounding_box, geo_radius, etc. are extracted.
        """
        rels = wrapper.relationships
        fc_children = None
        for parent, children in rels.items():
            if parent == "FieldCondition" or parent.endswith(".FieldCondition"):
                fc_children = children
                break

        if fc_children is None:
            pytest.skip("FieldCondition relationships not found")

        # At least some children should be present (Geo types, ValuesCount, etc.)
        assert len(fc_children) > 0, "No children extracted for FieldCondition"
        child_names_str = str(fc_children)
        geo_found = any(kw in child_names_str for kw in ("Geo", "ValuesCount", "Range"))
        assert geo_found, (
            f"Expected Geo/ValuesCount in FieldCondition children: {fc_children}"
        )


# =============================================================================
# 5. DSL Parser with Real Symbols
# =============================================================================


class TestDSLParserRealSymbols:
    """Verify DSL parser works with real qdrant_client.models symbol mappings."""

    def _get_symbol(self, symbols, class_name):
        """Look up symbol for a class name (handles path prefixes)."""
        for name, sym in symbols.items():
            if name == class_name or name.endswith(f".{class_name}"):
                return sym
        return None

    def test_parser_exists(self, parser):
        assert parser is not None

    def test_parse_single_symbol(self, parser, symbols):
        """Parse a single parameterized symbol."""
        sym = self._get_symbol(symbols, "Filter")
        assert sym is not None, "No symbol for Filter"

        result = parser.parse(f"{sym}{{must=null}}")
        assert result is not None
        assert len(result.root_nodes) > 0
        root = result.root_nodes[0]
        assert "Filter" in root.component_name
        assert root.is_parameterized is True

    def test_parse_filter_with_fieldcondition(self, parser, symbols):
        """Parse a realistic Filter → FieldCondition → MatchValue DSL."""
        f_sym = self._get_symbol(symbols, "Filter")
        fc_sym = self._get_symbol(symbols, "FieldCondition")
        mv_sym = self._get_symbol(symbols, "MatchValue")

        if not all([f_sym, fc_sym, mv_sym]):
            pytest.skip(
                f"Missing symbols: Filter={f_sym}, FieldCondition={fc_sym}, MatchValue={mv_sym}"
            )

        dsl = f'{f_sym}{{must=[{fc_sym}{{key="tool_name", match={mv_sym}{{value="search"}}}}]}}'
        result = parser.parse(dsl)

        assert result is not None
        assert len(result.root_nodes) > 0

        root = result.root_nodes[0]
        assert "Filter" in root.component_name
        assert root.is_parameterized is True

        # Check nested structure
        must_val = root.params.get("must")
        assert isinstance(must_val, list), f"Expected list, got {type(must_val)}"
        assert len(must_val) == 1

        from adapters.module_wrapper.dsl_parser import DSLNode

        fc_node = must_val[0]
        assert isinstance(fc_node, DSLNode)
        assert "FieldCondition" in fc_node.component_name
        assert fc_node.params.get("key") == "tool_name"

        match_node = fc_node.params.get("match")
        assert isinstance(match_node, DSLNode)
        assert "MatchValue" in match_node.component_name
        assert match_node.params.get("value") == "search"

    def test_dsl_round_trip(self, parser, symbols):
        """Parse DSL → compact string → re-parse should be equivalent."""
        f_sym = self._get_symbol(symbols, "Filter")
        fc_sym = self._get_symbol(symbols, "FieldCondition")
        mv_sym = self._get_symbol(symbols, "MatchValue")

        if not all([f_sym, fc_sym, mv_sym]):
            pytest.skip("Missing symbols")

        original_dsl = f'{f_sym}{{must=[{fc_sym}{{key="tool_name", match={mv_sym}{{value="search"}}}}]}}'
        result1 = parser.parse(original_dsl)
        compact = result1.root_nodes[0].to_compact_dsl()
        result2 = parser.parse(compact)

        assert result2 is not None
        assert len(result2.root_nodes) > 0
        assert (
            result2.root_nodes[0].component_name == result1.root_nodes[0].component_name
        )


# =============================================================================
# 6. DSLNode → Real qdrant_client.models Instantiation
# =============================================================================


class TestDSLNodeToQdrantObjects:
    """
    The critical test: can we walk a parsed DSLNode tree and instantiate
    real qdrant_client.models objects?

    This validates the core contract that Phase 4 QueryBuilder depends on.
    """

    def _get_symbol(self, symbols, class_name):
        for name, sym in symbols.items():
            if name == class_name or name.endswith(f".{class_name}"):
                return sym
        return None

    def _resolve_class(self, wrapper, component_name):
        """Resolve a component name to its actual class, like QueryBuilder will."""
        component = wrapper.components.get(component_name)
        if component and component.obj:
            return component.obj
        # Try with path prefix
        for name, comp in wrapper.components.items():
            if name.endswith(f".{component_name}") or name == component_name:
                if comp.obj:
                    return comp.obj
        return None

    def _build_from_node(self, wrapper, node):
        """Recursively build qdrant objects from DSLNode (mimics QueryBuilder.build)."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        cls = self._resolve_class(wrapper, node.component_name)
        if cls is None:
            raise ValueError(f"Cannot resolve class for: {node.component_name}")

        kwargs = {}
        for key, value in node.params.items():
            if isinstance(value, DSLNode):
                kwargs[key] = self._build_from_node(wrapper, value)
            elif isinstance(value, list):
                kwargs[key] = [
                    self._build_from_node(wrapper, item)
                    if isinstance(item, DSLNode)
                    else item
                    for item in value
                ]
            else:
                kwargs[key] = value

        return cls(**kwargs)

    def test_build_match_value(self, wrapper, symbols):
        """Build a MatchValue from DSLNode."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        mv_sym = self._get_symbol(symbols, "MatchValue")
        assert mv_sym is not None

        node = DSLNode(
            symbol=mv_sym,
            component_name="MatchValue",
            params={"value": "search"},
        )
        obj = self._build_from_node(wrapper, node)
        assert isinstance(obj, qmodels.MatchValue)
        assert obj.value == "search"

    def test_build_field_condition(self, wrapper, symbols):
        """Build a FieldCondition with nested MatchValue."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        fc_sym = self._get_symbol(symbols, "FieldCondition")
        mv_sym = self._get_symbol(symbols, "MatchValue")
        assert fc_sym and mv_sym

        mv_node = DSLNode(
            symbol=mv_sym,
            component_name="MatchValue",
            params={"value": "gmail"},
        )
        fc_node = DSLNode(
            symbol=fc_sym,
            component_name="FieldCondition",
            params={"key": "tool_name", "match": mv_node},
        )
        obj = self._build_from_node(wrapper, fc_node)
        assert isinstance(obj, qmodels.FieldCondition)
        assert obj.key == "tool_name"
        assert isinstance(obj.match, qmodels.MatchValue)
        assert obj.match.value == "gmail"

    def test_build_filter_with_must(self, wrapper, symbols):
        """Build a complete Filter(must=[FieldCondition(...)]) — the core use case."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        f_sym = self._get_symbol(symbols, "Filter")
        fc_sym = self._get_symbol(symbols, "FieldCondition")
        mv_sym = self._get_symbol(symbols, "MatchValue")
        assert all([f_sym, fc_sym, mv_sym])

        mv_node = DSLNode(
            symbol=mv_sym,
            component_name="MatchValue",
            params={"value": "search"},
        )
        fc_node = DSLNode(
            symbol=fc_sym,
            component_name="FieldCondition",
            params={"key": "tool_name", "match": mv_node},
        )
        filter_node = DSLNode(
            symbol=f_sym,
            component_name="Filter",
            params={"must": [fc_node]},
        )

        obj = self._build_from_node(wrapper, filter_node)

        # Verify types
        assert isinstance(obj, qmodels.Filter)
        assert obj.must is not None
        assert len(obj.must) == 1
        assert isinstance(obj.must[0], qmodels.FieldCondition)
        assert obj.must[0].key == "tool_name"
        assert isinstance(obj.must[0].match, qmodels.MatchValue)
        assert obj.must[0].match.value == "search"

    def test_build_filter_from_parsed_dsl(self, wrapper, parser, symbols):
        """End-to-end: parse DSL string → build real qdrant objects."""
        f_sym = self._get_symbol(symbols, "Filter")
        fc_sym = self._get_symbol(symbols, "FieldCondition")
        mv_sym = self._get_symbol(symbols, "MatchValue")

        if not all([f_sym, fc_sym, mv_sym]):
            pytest.skip("Missing symbols")

        dsl = f'{f_sym}{{must=[{fc_sym}{{key="tool_name", match={mv_sym}{{value="search"}}}}]}}'
        result = parser.parse(dsl)
        root_node = result.root_nodes[0]

        obj = self._build_from_node(wrapper, root_node)

        assert isinstance(obj, qmodels.Filter)
        assert len(obj.must) == 1
        fc = obj.must[0]
        assert isinstance(fc, qmodels.FieldCondition)
        assert fc.key == "tool_name"
        assert isinstance(fc.match, qmodels.MatchValue)
        assert fc.match.value == "search"

    def test_build_filter_multiple_conditions(self, wrapper, parser, symbols):
        """Parse and build a filter with multiple must conditions."""
        f_sym = self._get_symbol(symbols, "Filter")
        fc_sym = self._get_symbol(symbols, "FieldCondition")
        mv_sym = self._get_symbol(symbols, "MatchValue")

        if not all([f_sym, fc_sym, mv_sym]):
            pytest.skip("Missing symbols")

        dsl = (
            f"{f_sym}{{must=["
            f'{fc_sym}{{key="tool_name", match={mv_sym}{{value="search"}}}},'
            f'{fc_sym}{{key="user_email", match={mv_sym}{{value="test@example.com"}}}}'
            f"]}}"
        )
        result = parser.parse(dsl)
        obj = self._build_from_node(wrapper, result.root_nodes[0])

        assert isinstance(obj, qmodels.Filter)
        assert len(obj.must) == 2
        assert obj.must[0].key == "tool_name"
        assert obj.must[1].key == "user_email"

    def test_build_match_text(self, wrapper, symbols):
        """Build a MatchText object (text search, not exact match)."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        mt_sym = self._get_symbol(symbols, "MatchText")
        if not mt_sym:
            pytest.skip("No symbol for MatchText")

        node = DSLNode(
            symbol=mt_sym,
            component_name="MatchText",
            params={"text": "hello world"},
        )
        obj = self._build_from_node(wrapper, node)
        assert isinstance(obj, qmodels.MatchText)
        assert obj.text == "hello world"

    def test_build_has_id_condition(self, wrapper, symbols):
        """Build a HasIdCondition with list of IDs."""
        from adapters.module_wrapper.dsl_parser import DSLNode

        hid_sym = self._get_symbol(symbols, "HasIdCondition")
        if not hid_sym:
            pytest.skip("No symbol for HasIdCondition")

        node = DSLNode(
            symbol=hid_sym,
            component_name="HasIdCondition",
            params={"has_id": ["id1", "id2", "id3"]},
        )
        obj = self._build_from_node(wrapper, node)
        assert isinstance(obj, qmodels.HasIdCondition)
        assert obj.has_id == ["id1", "id2", "id3"]


# =============================================================================
# 7. Symbol Discoverability (for qdrant_search_v2_symbols tool)
# =============================================================================


class TestSymbolDiscoverability:
    """Verify the wrapper provides enough info for the symbols tool."""

    def test_dsl_metadata_available(self, wrapper):
        """wrapper.dsl_metadata should return structure info."""
        meta = wrapper.dsl_metadata
        assert meta is not None
        assert isinstance(meta, dict)

    def test_relationships_available_as_dict(self, wrapper):
        """relationships should be accessible as parent → children dict."""
        rels = wrapper.relationships
        assert isinstance(rels, dict)
        # Should have at least a few parents
        assert len(rels) >= 1

    def test_symbol_table_for_tool_output(self, symbols, reverse_symbols):
        """Verify we can produce a symbol → class name table for the symbols tool."""
        # This is what qdrant_search_v2_symbols will return
        table = {sym: name for name, sym in symbols.items()}
        assert len(table) > 0

        # Verify key entries exist
        filter_entry = None
        for sym, name in table.items():
            if "Filter" in name:
                filter_entry = (sym, name)
                break
        assert filter_entry is not None, "Filter not in symbol table"


# =============================================================================
# 8. Advanced Query Types (RecommendQuery, FusionQuery, OrderBy, Prefetch)
# =============================================================================


class TestAdvancedQueryTypes:
    """
    Test DSL parsing and building of advanced query types that use full class
    names (not Unicode symbols) for query_dsl / prefetch_dsl parameters.

    These types were added in the query_dsl/prefetch_dsl executor extension:
    - RecommendQuery → recommend similar points by positive/negative IDs
    - FusionQuery → combine results from multiple prefetch stages (RRF, DBSF)
    - OrderBy → sort by payload field
    - Prefetch → multi-stage query with nested filter
    """

    def _get_symbol(self, symbols, class_name):
        """Look up symbol for a class name (handles path prefixes)."""
        for name, sym in symbols.items():
            if name == class_name or name.endswith(f".{class_name}"):
                return sym
        return None

    # -- QueryBuilder integration --

    def test_recommend_query_parse_and_build(self, wrapper):
        """Parse RecommendQuery DSL and build real qdrant object."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        dsl = "RecommendQuery{recommend=RecommendInput{positive=[1, 2, 3]}}"
        obj = builder.parse_and_build(dsl)

        assert isinstance(obj, qmodels.RecommendQuery)
        assert isinstance(obj.recommend, qmodels.RecommendInput)
        assert obj.recommend.positive == [1, 2, 3]

    def test_recommend_query_with_negative(self, wrapper):
        """RecommendQuery with both positive and negative examples."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        dsl = "RecommendQuery{recommend=RecommendInput{positive=[1, 2], negative=[10, 20]}}"
        obj = builder.parse_and_build(dsl)

        assert isinstance(obj, qmodels.RecommendQuery)
        assert obj.recommend.positive == [1, 2]
        assert obj.recommend.negative == [10, 20]

    def test_fusion_query_rrf(self, wrapper):
        """Parse FusionQuery with RRF fusion and build real object."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        dsl = 'FusionQuery{fusion="rrf"}'
        obj = builder.parse_and_build(dsl)

        assert isinstance(obj, qmodels.FusionQuery)
        assert obj.fusion == qmodels.Fusion.RRF

    def test_fusion_query_dbsf(self, wrapper):
        """Parse FusionQuery with DBSF fusion."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        dsl = 'FusionQuery{fusion="dbsf"}'
        obj = builder.parse_and_build(dsl)

        assert isinstance(obj, qmodels.FusionQuery)
        assert obj.fusion == qmodels.Fusion.DBSF

    def test_order_by_desc(self, wrapper):
        """Parse OrderBy with descending direction."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        dsl = 'OrderBy{key="timestamp", direction="desc"}'
        obj = builder.parse_and_build(dsl)

        assert isinstance(obj, qmodels.OrderBy)
        assert obj.key == "timestamp"
        assert obj.direction == qmodels.Direction.DESC

    def test_order_by_asc(self, wrapper):
        """Parse OrderBy with ascending direction."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        dsl = 'OrderBy{key="score", direction="asc"}'
        obj = builder.parse_and_build(dsl)

        assert isinstance(obj, qmodels.OrderBy)
        assert obj.key == "score"
        assert obj.direction == qmodels.Direction.ASC

    def test_order_by_key_only(self, wrapper):
        """Parse OrderBy with just a key (direction defaults to None)."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        dsl = 'OrderBy{key="created_at"}'
        obj = builder.parse_and_build(dsl)

        assert isinstance(obj, qmodels.OrderBy)
        assert obj.key == "created_at"

    def test_prefetch_with_filter(self, wrapper, symbols):
        """Parse Prefetch with a nested Filter using real symbols."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        f_sym = self._get_symbol(symbols, "Filter")
        fc_sym = self._get_symbol(symbols, "FieldCondition")
        mv_sym = self._get_symbol(symbols, "MatchValue")
        if not all([f_sym, fc_sym, mv_sym]):
            pytest.skip("Missing filter symbols")

        builder = QueryBuilder(wrapper)
        dsl = (
            f'Prefetch{{filter={f_sym}{{must=[{fc_sym}{{key="service", '
            f'match={mv_sym}{{value="gmail"}}}}]}}, limit=5}}'
        )
        obj = builder.parse_and_build(dsl)

        assert isinstance(obj, qmodels.Prefetch)
        assert isinstance(obj.filter, qmodels.Filter)
        assert obj.limit == 5
        assert len(obj.filter.must) == 1
        assert obj.filter.must[0].key == "service"

    def test_prefetch_simple(self, wrapper):
        """Parse Prefetch with just a limit (no filter)."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        dsl = "Prefetch{limit=20}"
        obj = builder.parse_and_build(dsl)

        assert isinstance(obj, qmodels.Prefetch)
        assert obj.limit == 20

    # -- DSL parser level tests (multi-char identifiers) --

    def test_parser_handles_multi_char_component(self, parser):
        """DSL parser correctly tokenizes multi-char class names like RecommendQuery."""
        result = parser.parse("RecommendQuery{recommend=RecommendInput{positive=[1]}}")
        assert result is not None
        assert result.is_valid, f"Parse failed: {result.issues}"
        assert len(result.root_nodes) == 1

        root = result.root_nodes[0]
        assert root.component_name == "RecommendQuery"
        assert root.is_parameterized is True

        recommend_node = root.params.get("recommend")
        from adapters.module_wrapper.dsl_parser import DSLNode

        assert isinstance(recommend_node, DSLNode)
        assert recommend_node.component_name == "RecommendInput"

    def test_parser_handles_string_enum_values(self, parser):
        """DSL parser preserves string values that Pydantic coerces to enums."""
        result = parser.parse('FusionQuery{fusion="rrf"}')
        assert result.is_valid
        root = result.root_nodes[0]
        assert root.component_name == "FusionQuery"
        assert root.params["fusion"] == "rrf"

    def test_parser_handles_nested_multi_char_in_braces(self, parser, symbols):
        """Multi-char identifiers work inside parameterized braces (nested context)."""
        f_sym = self._get_symbol(symbols, "Filter")
        if not f_sym:
            pytest.skip("No Filter symbol")

        dsl = f"Prefetch{{filter={f_sym}{{must=null}}, limit=10}}"
        result = parser.parse(dsl)
        assert result.is_valid, f"Parse failed: {result.issues}"

        root = result.root_nodes[0]
        assert root.component_name == "Prefetch"
        assert root.params["limit"] == 10

    # -- build_all for multiple prefetch objects --

    def test_build_all_multiple_prefetches(self, wrapper, symbols):
        """QueryBuilder.build_all handles a list of Prefetch nodes."""
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)

        dsl1 = "Prefetch{limit=5}"
        dsl2 = "Prefetch{limit=10}"

        r1 = builder.parse_dsl(dsl1)
        r2 = builder.parse_dsl(dsl2)
        assert r1.is_valid and r2.is_valid

        objects = builder.build_all(r1.root_nodes + r2.root_nodes)
        assert len(objects) == 2
        assert all(isinstance(o, qmodels.Prefetch) for o in objects)
        assert objects[0].limit == 5
        assert objects[1].limit == 10

    # -- End-to-end: executor dry_run --

    def test_executor_dry_run_with_query_dsl(self, wrapper, symbols):
        """Executor.execute_dsl dry_run with query_dsl parses without hitting Qdrant."""
        from unittest.mock import MagicMock

        from middleware.qdrant_core.dsl_executor import SearchV2Executor
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        mock_cm = MagicMock()

        executor = SearchV2Executor(mock_cm, builder)

        f_sym = self._get_symbol(symbols, "Filter")
        fc_sym = self._get_symbol(symbols, "FieldCondition")
        mv_sym = self._get_symbol(symbols, "MatchValue")
        if not all([f_sym, fc_sym, mv_sym]):
            pytest.skip("Missing filter symbols")

        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            executor.execute_dsl(
                dsl=f'{f_sym}{{must=[{fc_sym}{{key="tool_name", match={mv_sym}{{value="search"}}}}]}}',
                query_dsl="RecommendQuery{recommend=RecommendInput{positive=[1, 2, 3]}}",
                dry_run=True,
            )
        )

        assert response.error is None, f"Dry run error: {response.error}"
        assert response.query_type == "dry_run"
        assert "filter:" in response.built_filter_repr
        assert "query:" in response.built_filter_repr
        assert "RecommendQuery" in response.built_filter_repr

    def test_executor_dry_run_with_prefetch_dsl(self, wrapper, symbols):
        """Executor dry_run with prefetch_dsl builds Prefetch objects."""
        from unittest.mock import MagicMock

        from middleware.qdrant_core.dsl_executor import SearchV2Executor
        from middleware.qdrant_core.dsl_query_builder import QueryBuilder

        builder = QueryBuilder(wrapper)
        mock_cm = MagicMock()

        executor = SearchV2Executor(mock_cm, builder)

        f_sym = self._get_symbol(symbols, "Filter")
        fc_sym = self._get_symbol(symbols, "FieldCondition")
        mv_sym = self._get_symbol(symbols, "MatchValue")
        if not all([f_sym, fc_sym, mv_sym]):
            pytest.skip("Missing filter symbols")

        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            executor.execute_dsl(
                dsl=f'{f_sym}{{must=[{fc_sym}{{key="service", match={mv_sym}{{value="gmail"}}}}]}}',
                query_dsl='FusionQuery{fusion="rrf"}',
                prefetch_dsl="Prefetch{limit=20}",
                dry_run=True,
            )
        )

        assert response.error is None, f"Dry run error: {response.error}"
        assert response.query_type == "dry_run"
        assert "prefetch:" in response.built_filter_repr
        assert "query:" in response.built_filter_repr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
