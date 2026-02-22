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

import logging
from typing import TYPE_CHECKING, Any, List, Optional

from adapters.module_wrapper.dsl_parser import DSLNode, DSLParseResult

if TYPE_CHECKING:
    from adapters.module_wrapper.core import ModuleWrapper

logger = logging.getLogger(__name__)


class QueryBuilder:
    """Builds qdrant_client.models objects from parsed DSL trees."""

    def __init__(self, wrapper: "ModuleWrapper"):
        self.wrapper = wrapper
        self.parser = wrapper.get_dsl_parser()

    def parse_dsl(self, dsl: str) -> DSLParseResult:
        """Parse a DSL string into a DSLNode tree."""
        return self.parser.parse(dsl)

    def parse_and_build(self, dsl: str) -> Any:
        """Parse DSL string and build the corresponding qdrant object.

        Args:
            dsl: Parameterized DSL string, e.g.
                 'ƒ{must=[φ{key="tool_name", match=ʋ{value="search"}}]}'

        Returns:
            Instantiated qdrant_client.models object (e.g. Filter)

        Raises:
            ValueError: If DSL is invalid or component cannot be resolved
        """
        result = self.parse_dsl(dsl)
        if not result.is_valid:
            raise ValueError(f"Invalid DSL: {'; '.join(result.issues)}")
        if not result.root_nodes:
            raise ValueError("DSL parsed but produced no root nodes")

        return self.build(result.root_nodes[0])

    def build(self, node: DSLNode) -> Any:
        """Recursively build a qdrant_client.models object from a DSLNode.

        Args:
            node: Parsed DSLNode with component_name and params

        Returns:
            Instantiated object from the wrapped module
        """
        cls = self._resolve_class(node.component_name)

        kwargs = {}
        for key, value in node.params.items():
            kwargs[key] = self._build_value(value)

        try:
            return cls(**kwargs)
        except Exception as e:
            raise ValueError(
                f"Failed to instantiate {node.component_name}(**{kwargs}): {e}"
            ) from e

    def build_all(self, nodes: List[DSLNode]) -> List[Any]:
        """Build a list of qdrant objects from multiple DSLNodes."""
        return [self.build(node) for node in nodes]

    def _build_value(self, value: Any) -> Any:
        """Recursively convert DSL values to Python objects."""
        if isinstance(value, DSLNode):
            return self.build(value)
        elif isinstance(value, list):
            return [self._build_value(item) for item in value]
        else:
            return value  # primitives pass through

    def _resolve_class(self, component_name: str) -> type:
        """Resolve a component name to its actual class from the wrapped module.

        The wrapper.components dict maps full_path → ModuleComponent.
        We search by .name to find the right class.
        """
        # First try direct lookup by name (most components use simple names)
        for _path, comp in self.wrapper.components.items():
            if comp.name == component_name and comp.obj is not None:
                return comp.obj

        raise ValueError(
            f"Unknown component: '{component_name}'. "
            f"Available: {sorted(set(c.name for c in self.wrapper.components.values()))[:20]}"
        )
