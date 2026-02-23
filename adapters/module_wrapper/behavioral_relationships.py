"""
Behavioral Relationship Strategy

Extracts relationships from the ToolRelationshipGraph instead of type hints.
Used for tool components (component_type="tool") where relationships are
derived from temporal co-occurrence patterns, not structural containment.

This is the counterpart to the existing structural extraction in
RelationshipsMixin._extract_relationships_from_class(), which inspects
class field type hints for containment relationships.
"""

import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# RELATIONSHIP STRATEGY PROTOCOL
# =============================================================================


@runtime_checkable
class RelationshipStrategy(Protocol):
    """Base protocol for relationship extraction strategies."""

    def extract(self, components: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract relationships from a set of components.

        Args:
            components: Dict mapping full_path -> ModuleComponent

        Returns:
            List of relationship dictionaries compatible with the pipeline.
        """
        ...

    def get_relationship_text(self, component_name: str) -> str:
        """Generate relationship text for embedding.

        Args:
            component_name: Name of the component

        Returns:
            Text suitable for the 'relationships' vector embedding.
        """
        ...


# =============================================================================
# STRUCTURAL STRATEGY (wrapper around existing logic)
# =============================================================================


class StructuralRelationshipStrategy:
    """Extracts relationships from class field type hints (containment).

    This wraps the existing RelationshipsMixin._extract_relationships_from_class()
    logic. It's used for component_type="class" components.

    The actual extraction is delegated to the mixin, so this class is a thin
    adapter that conforms to the RelationshipStrategy protocol.
    """

    def __init__(self, mixin_instance: Any):
        """
        Args:
            mixin_instance: A RelationshipsMixin instance (the ModuleWrapper)
        """
        self._mixin = mixin_instance

    def extract(self, components: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Delegates to RelationshipsMixin.extract_relationships()."""
        return self._mixin.extract_relationships()

    def get_relationship_text(self, component_name: str) -> str:
        """Build compact relationship text from structural relationships."""
        from adapters.module_wrapper.pipeline_mixin import (
            build_compact_relationship_text,
        )

        by_parent = self._mixin.extract_relationships_by_parent()
        rels = by_parent.get(component_name, [])
        comp = None
        for path, c in self._mixin.components.items():
            if c.name == component_name:
                comp = c
                break
        comp_type = comp.component_type if comp else "class"
        return build_compact_relationship_text(component_name, rels, comp_type)


# =============================================================================
# BEHAVIORAL STRATEGY (graph-based)
# =============================================================================


class BehavioralRelationshipStrategy:
    """Extracts relationships from ToolRelationshipGraph co-occurrence patterns.

    Used for component_type="tool" components where relationships are temporal
    (tool A called before/after tool B) rather than structural (class A contains field B).

    Produces relationship dicts compatible with the existing pipeline:
        {
            "parent_class": tool_name,
            "child_class": successor_tool_name,
            "field_name": "successor",
            "is_optional": True,
            "depth": 1,
            "relationship_path": "tool.successor",
            "json_path": "tool.successor",
            "nl_description": "send_message frequently followed by list_messages",
        }
    """

    def __init__(self, tool_graph: Any):
        """
        Args:
            tool_graph: A ToolRelationshipGraph instance
        """
        from adapters.module_wrapper.tool_relationship_graph import (
            ToolRelationshipGraph,
        )
        self._graph: ToolRelationshipGraph = tool_graph

    def extract(self, components: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract behavioral relationships for all tool components.

        Returns relationship dicts where:
        - "parent_class" = the tool
        - "child_class" = a frequent successor tool
        - "field_name" = "successor" (behavioral, not structural)
        """
        relationships = []

        for full_path, component in components.items():
            if getattr(component, "component_type", "") != "tool":
                continue

            tool_name = component.name
            successors = self._graph.get_successors(tool_name, top_n=5)

            for succ_name, count in successors:
                node_info = self._graph.get_node_info(tool_name)
                succ_info = self._graph.get_node_info(succ_name)
                service = node_info["service"] if node_info else ""
                succ_service = succ_info["service"] if succ_info else ""

                nl_desc = f"{tool_name} frequently followed by {succ_name}"
                if service and succ_service and service != succ_service:
                    nl_desc += f" (cross-service: {service} -> {succ_service})"
                elif service:
                    nl_desc += f" (within {service})"

                relationships.append({
                    "parent_class": tool_name,
                    "parent_module": f"tools.{service}" if service else "tools",
                    "parent_path": f"tools.{service}.{tool_name}" if service else f"tools.{tool_name}",
                    "child_class": succ_name,
                    "child_module": f"tools.{succ_service}" if succ_service else "tools",
                    "child_path": f"tools.{succ_service}.{succ_name}" if succ_service else f"tools.{succ_name}",
                    "field_name": "successor",
                    "is_optional": True,
                    "depth": 1,
                    "relationship_path": f"{tool_name}.successor.{succ_name}",
                    "json_path": f"{tool_name}.successor.{succ_name}",
                    "nl_description": nl_desc,
                    "co_occurrence_count": count,
                    "relationship_type": "behavioral",
                })

        return relationships

    def get_relationship_text(
        self,
        tool_name: str,
        user_email: str = "",
        session_id: str = "",
    ) -> str:
        """Generate relationship text from the tool co-occurrence graph.

        This is the text that gets embedded into the 'relationships' vector.
        """
        return self._graph.get_relationship_text(
            tool_name,
            user_email=user_email,
            session_id=session_id,
        )


__all__ = [
    "RelationshipStrategy",
    "StructuralRelationshipStrategy",
    "BehavioralRelationshipStrategy",
]
