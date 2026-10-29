"""
Query Builder — DSLNode tree → qdrant_client.models object instantiation.

Walks a parameterized DSLNode tree produced by DSLParser and recursively
instantiates real qdrant_client.models objects (Filter, FieldCondition,
MatchValue, etc.) via the ModuleWrapper's component registry.

Usage:
    from middleware.qdrant_core.dsl_query_builder import QueryBuilder
    from middleware.qdrant_core.qdrant_models_wrapper import get_qdrant_models_wrapper

    wrapper = get_qdrant_models_wrapper()
    builder = QueryBuilder(wrapper)

    # Parse DSL → build real qdrant objects
    result = builder.parse_and_build('ƒ{must=[φ{key="tool_name", match=ʋ{value="search"}}]}')
    # result is a qdrant_client.models.Filter instance
"""

from adapters.module_wrapper.dsl_builder import DSLObjectBuilder


class QueryBuilder(DSLObjectBuilder):
    """Builds qdrant_client.models objects from parsed DSL trees.

    The builder itself is module-agnostic (``DSLObjectBuilder``); this name is kept
    for the qdrant search tools.
    """
