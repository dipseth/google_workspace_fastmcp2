"""
Relationship Extraction Mixin

Provides relationship extraction from dataclass type hints
for the ModuleWrapper system.
"""

import dataclasses
import inspect
import logging
from collections import defaultdict
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from .core import BUILTIN_PREFIXES, PRIMITIVE_TYPES

logger = logging.getLogger(__name__)


def _get_nl_relationship_patterns() -> Dict[tuple, str]:
    """Get NL relationship patterns for generating natural language descriptions."""
    # These patterns describe how parent-child relationships work in Google Chat cards
    return {
        # Widget containers
        ("Section", "Widget"): "section containing widgets",
        ("Section", "DecoratedText"): "section with decorated text items",
        ("Section", "TextParagraph"): "section with text paragraphs",
        ("Section", "ButtonList"): "section with button list",
        ("Section", "Grid"): "section with grid layout",
        ("Section", "Image"): "section with image",
        ("Section", "Columns"): "section with column layout",
        ("Section", "Divider"): "section with divider",
        ("Section", "TextInput"): "section with text input field",
        ("Section", "DateTimePicker"): "section with date/time picker",
        ("Section", "SelectionInput"): "section with selection input",
        ("Section", "ChipList"): "section with chip list",
        # Click actions
        ("Image", "OnClick"): "clickable image, image with click action",
        ("Button", "OnClick"): "button click action, button that opens link",
        ("Chip", "OnClick"): "clickable chip",
        ("DecoratedText", "OnClick"): "clickable decorated text",
        ("GridItem", "OnClick"): "clickable grid item",
        # Button containers
        ("ButtonList", "Button"): "list of buttons",
        ("ChipList", "Chip"): "list of chips",
        # Layout
        ("Columns", "Column"): "multi-column layout",
        ("Column", "Widget"): "column containing widgets",
        ("Grid", "GridItem"): "grid with items",
        # Icons and styling
        ("Button", "Icon"): "button with icon",
        ("Chip", "Icon"): "chip with icon",
        ("DecoratedText", "Icon"): "decorated text with icon",
        ("DecoratedText", "Button"): "decorated text with button",
        ("DecoratedText", "SwitchControl"): "decorated text with switch/toggle",
        # Card structure
        ("Card", "Section"): "card with sections",
        ("Card", "CardHeader"): "card with header",
        ("Card", "CardFixedFooter"): "card with footer",
    }


# =============================================================================
# RELATIONSHIPS MIXIN
# =============================================================================


class RelationshipsMixin:
    """
    Mixin providing relationship extraction functionality.

    Expects the following attributes on self:
    - components: Dict[str, ModuleComponent]
    - client: Qdrant client
    - collection_name: str
    - embedder, colbert_embedder: Embedding models
    """

    # Cached properties
    _cached_relationships: Optional[Dict[str, List[str]]] = None

    def _is_dataclass_type(self, cls: type) -> bool:
        """Check if a class is a dataclass."""
        return dataclasses.is_dataclass(cls) and isinstance(cls, type)

    def _unwrap_optional(self, field_type: type) -> Tuple[type, bool]:
        """
        Unwrap Optional[X] to get X and whether it was optional.

        Returns:
            Tuple of (unwrapped_type, is_optional)
        """
        origin = get_origin(field_type)

        # Handle Optional[X] which is Union[X, None]
        if origin is Union:
            args = get_args(field_type)
            non_none_args = [t for t in args if t is not type(None)]
            if len(non_none_args) == 1:
                return non_none_args[0], True
            return field_type, False

        return field_type, False

    def _unwrap_container_type(self, field_type: type) -> List[type]:
        """
        Extract inner types from container types like List[T], Tuple[T, ...], Set[T].

        Returns:
            List of inner types (or the original type if not a container)
        """
        origin = get_origin(field_type)

        # Handle List[T], Tuple[T, ...], Set[T], FrozenSet[T]
        if origin in (list, tuple, set, frozenset):
            args = get_args(field_type)
            if args:
                return [a for a in args if a is not Ellipsis and a is not type(None)]
            return []

        # Handle Optional[List[T]]
        if origin is Union:
            args = get_args(field_type)
            non_none_args = [t for t in args if t is not type(None)]
            if len(non_none_args) == 1:
                return self._unwrap_container_type(non_none_args[0])

        return [field_type]

    def _is_component_type(self, field_type: type) -> bool:
        """Check if a type represents a component (not primitive)."""
        if field_type in PRIMITIVE_TYPES:
            return False

        if not inspect.isclass(field_type):
            return False

        module = getattr(field_type, "__module__", "")
        if any(module.startswith(prefix) for prefix in BUILTIN_PREFIXES):
            return False

        return True

    def _to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to camelCase."""
        components = snake_str.split("_")
        return components[0] + "".join(x.title() for x in components[1:])

    def _generate_nl_description(self, parent: str, child: str) -> str:
        """Generate natural language description for a relationship."""
        patterns = _get_nl_relationship_patterns()
        key = (parent, child)
        if key in patterns:
            return patterns[key]

        return f"{parent.lower()} with {child.lower()}, {parent.lower()} containing {child.lower()}"

    def _extract_relationships_from_class(
        self,
        cls: type,
        visited: Optional[Set[str]] = None,
        depth: int = 0,
        max_depth: int = 5,
        path_prefix: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Extract field relationships from a class using type hints.

        Args:
            cls: The class to analyze
            visited: Set of visited class names to prevent cycles
            depth: Current recursion depth
            max_depth: Maximum recursion depth
            path_prefix: Prefix for nested paths

        Returns:
            List of relationship dictionaries
        """
        if visited is None:
            visited = set()

        class_name = cls.__name__
        if class_name in visited or depth > max_depth:
            return []

        visited.add(class_name)
        relationships = []

        try:
            hints = get_type_hints(cls)
        except Exception as e:
            logger.debug(f"Could not get type hints for {class_name}: {e}")
            return []

        for field_name, field_type in hints.items():
            if field_name.startswith("_"):
                continue

            unwrapped_type, is_optional = self._unwrap_optional(field_type)
            inner_types = self._unwrap_container_type(unwrapped_type)

            for inner_type in inner_types:
                if not self._is_component_type(inner_type):
                    continue

                child_name = inner_type.__name__
                child_module = getattr(inner_type, "__module__", "")

                if path_prefix:
                    rel_path = f"{path_prefix}.{field_name}"
                else:
                    rel_path = f"{class_name.lower()}.{field_name}"

                json_field = self._to_camel_case(field_name)
                if path_prefix:
                    json_path = f"{path_prefix}.{json_field}"
                else:
                    json_path = f"{class_name[0].lower()}{class_name[1:]}.{json_field}"

                relationship = {
                    "parent_class": class_name,
                    "parent_module": cls.__module__,
                    "parent_path": f"{cls.__module__}.{class_name}",
                    "child_class": child_name,
                    "child_module": child_module,
                    "child_path": f"{child_module}.{child_name}",
                    "field_name": field_name,
                    "is_optional": is_optional,
                    "depth": depth + 1,
                    "relationship_path": rel_path,
                    "json_path": json_path,
                    "nl_description": self._generate_nl_description(
                        class_name, child_name
                    ),
                }
                relationships.append(relationship)

                # Recursively extract from child class
                if self._is_dataclass_type(inner_type):
                    child_relationships = self._extract_relationships_from_class(
                        inner_type,
                        visited=visited.copy(),
                        depth=depth + 1,
                        max_depth=max_depth,
                        path_prefix=json_path,
                    )
                    for child_rel in child_relationships:
                        child_rel["root_parent"] = class_name
                        child_rel["intermediate_path"] = rel_path
                    relationships.extend(child_relationships)

        return relationships

    def extract_relationships(self, max_depth: int = 5) -> List[Dict[str, Any]]:
        """
        Extract all component relationships from indexed components.

        Args:
            max_depth: Maximum nesting depth to traverse

        Returns:
            List of relationship dictionaries
        """
        all_relationships = []
        processed_classes = set()

        logger.info(
            f"Extracting relationships from {len(self.components)} components..."
        )

        for full_path, component in self.components.items():
            if component.component_type != "class":
                continue

            if component.name in processed_classes:
                continue

            cls = component.obj
            if cls is None or not inspect.isclass(cls):
                continue

            if not self._is_dataclass_type(cls):
                continue

            processed_classes.add(component.name)
            relationships = self._extract_relationships_from_class(
                cls, max_depth=max_depth
            )
            all_relationships.extend(relationships)

        logger.info(f"Extracted {len(all_relationships)} relationships")
        return all_relationships

    def extract_relationships_by_child(
        self, child_class: str, max_depth: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Extract relationships filtered by child class name.

        Args:
            child_class: Name of the child class to filter by
            max_depth: Maximum nesting depth to traverse

        Returns:
            List of relationships where the child matches
        """
        all_rels = self.extract_relationships(max_depth=max_depth)
        filtered = [r for r in all_rels if r["child_class"] == child_class]
        logger.info(f"Found {len(filtered)} {child_class} relationships")
        return filtered

    def extract_relationships_by_parent(
        self, max_depth: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract relationships grouped by parent component name.

        Args:
            max_depth: Maximum nesting depth to traverse

        Returns:
            Dict mapping parent_class name to list of its child relationships
        """
        all_rels = self.extract_relationships(max_depth=max_depth)

        by_parent: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for rel in all_rels:
            parent = rel["parent_class"]
            by_parent[parent].append(
                {
                    "child_class": rel["child_class"],
                    "field_name": rel["field_name"],
                    "json_path": rel["json_path"],
                    "depth": rel["depth"],
                    "is_optional": rel["is_optional"],
                    "nl_description": rel["nl_description"],
                    "root_parent": rel.get("root_parent"),
                }
            )

        logger.info(f"Grouped relationships for {len(by_parent)} parent components")
        return dict(by_parent)

    @property
    def relationships(self) -> Dict[str, List[str]]:
        """Get cached relationships grouped by parent component."""
        if self._cached_relationships is None:
            raw_rels = self.extract_relationships_by_parent(max_depth=5)
            self._cached_relationships = {
                parent: [r["child_class"] for r in children]
                for parent, children in raw_rels.items()
            }
        return self._cached_relationships

    @property
    def relationship_metadata(self) -> Dict[str, Any]:
        """Get metadata about relationships."""
        rels = self.relationships
        return {
            "total_parents": len(rels),
            "total_relationships": sum(len(children) for children in rels.values()),
            "parents_with_children": list(rels.keys())[:10],
        }

    def enrich_components_with_relationships(
        self,
        max_depth: int = 5,
        collection_name: Optional[str] = None,
    ) -> int:
        """
        Enrich existing component points with relationship metadata.

        Args:
            max_depth: Maximum nesting depth to traverse
            collection_name: Collection to update

        Returns:
            Number of components enriched
        """
        if collection_name is None:
            collection_name = self.collection_name

        if not self.client:
            logger.warning("No Qdrant client - cannot enrich components")
            return 0

        by_parent = self.extract_relationships_by_parent(max_depth=max_depth)

        if not by_parent:
            logger.info("No relationships to add")
            return 0

        try:
            # Scan collection for class components
            logger.info(
                f"Scanning collection {collection_name} for class components..."
            )
            class_name_to_ids: Dict[str, List[str]] = defaultdict(list)

            offset = None
            total_scanned = 0
            while True:
                scroll_result = self.client.scroll(
                    collection_name=collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                )
                points, next_offset = scroll_result

                if not points:
                    break

                for point in points:
                    payload = point.payload or {}
                    if payload.get("type") == "class":
                        name = payload.get("name")
                        if name:
                            class_name_to_ids[name].append(str(point.id))
                    total_scanned += 1

                if next_offset is None:
                    break
                offset = next_offset

            logger.info(
                f"Scanned {total_scanned} points, found {len(class_name_to_ids)} unique class names"
            )

            enriched_count = 0

            for parent_class, relationships in by_parent.items():
                point_ids = class_name_to_ids.get(parent_class, [])

                if not point_ids:
                    continue

                nl_descriptions = ", ".join(r["nl_description"] for r in relationships)

                relationships_payload = {
                    "children": relationships,
                    "child_classes": list(set(r["child_class"] for r in relationships)),
                    "max_depth": (
                        max(r["depth"] for r in relationships) if relationships else 0
                    ),
                    "nl_descriptions": nl_descriptions,
                }

                for point_id in point_ids:
                    try:
                        self.client.set_payload(
                            collection_name=collection_name,
                            payload={"relationships": relationships_payload},
                            points=[point_id],
                        )
                        enriched_count += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to enrich {parent_class} ({point_id}): {e}"
                        )

            logger.info(
                f"Enriched {enriched_count} components with relationship metadata"
            )
            return enriched_count

        except Exception as e:
            logger.error(f"Failed to enrich components: {e}", exc_info=True)
            return 0

    def get_relationship_tree(self, child_class: str) -> Dict[str, Any]:
        """
        Get a tree of all parents that can contain a child class.

        Args:
            child_class: Name of the child class

        Returns:
            Tree structure showing containment hierarchy
        """
        all_rels = self.extract_relationships()

        # Find all direct parents of this child
        direct_parents = [
            r["parent_class"] for r in all_rels if r["child_class"] == child_class
        ]

        # Build tree recursively
        def build_parent_tree(class_name: str, visited: Set[str]) -> Dict[str, Any]:
            if class_name in visited:
                return {"name": class_name, "cyclic": True}

            visited.add(class_name)

            parents = [
                r["parent_class"] for r in all_rels if r["child_class"] == class_name
            ]

            return {
                "name": class_name,
                "parents": [build_parent_tree(p, visited.copy()) for p in parents],
            }

        return {
            "child": child_class,
            "direct_parents": direct_parents,
            "tree": build_parent_tree(child_class, set()),
        }

    def print_relationship_tree(self, child_class: str) -> str:
        """
        Get a printable tree of parents for a child class.

        Args:
            child_class: Name of the child class

        Returns:
            Formatted tree string
        """
        tree = self.get_relationship_tree(child_class)

        lines = [f"Containment tree for: {child_class}"]
        lines.append(f"Direct parents: {', '.join(tree['direct_parents'])}")
        lines.append("")

        def format_tree(node: Dict, indent: int = 0) -> List[str]:
            result = []
            prefix = "  " * indent
            if node.get("cyclic"):
                result.append(f"{prefix}↺ {node['name']} (cyclic)")
            else:
                result.append(f"{prefix}→ {node['name']}")
                for parent in node.get("parents", []):
                    result.extend(format_tree(parent, indent + 1))
            return result

        lines.extend(format_tree(tree["tree"]))
        return "\n".join(lines)

    def invalidate_caches(self) -> None:
        """Invalidate all cached data including relationships."""
        self._cached_relationships = None
        # Also invalidate symbol caches if they exist
        if hasattr(self, "_symbol_mapping"):
            self._symbol_mapping = None
        if hasattr(self, "_reverse_symbol_mapping"):
            self._reverse_symbol_mapping = None
        if hasattr(self, "_dsl_metadata_cache"):
            self._dsl_metadata_cache = None
        logger.info("Caches invalidated")


# Export for convenience
__all__ = [
    "RelationshipsMixin",
]
