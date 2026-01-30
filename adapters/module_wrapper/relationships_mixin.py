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

from .core import BUILTIN_PREFIXES, PRIMITIVE_TYPES, ModuleComponent

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
    _cached_raw_relationships: Optional[List[Dict[str, Any]]] = None
    _cached_raw_relationships_depth: Optional[int] = None

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

        Results are cached to avoid redundant computation across multiple calls.

        Args:
            max_depth: Maximum nesting depth to traverse

        Returns:
            List of relationship dictionaries
        """
        # Check cache - return if we have results for same or greater depth
        if (
            self._cached_raw_relationships is not None
            and self._cached_raw_relationships_depth is not None
            and self._cached_raw_relationships_depth >= max_depth
        ):
            logger.debug(
                f"Returning cached relationships ({len(self._cached_raw_relationships)} items)"
            )
            return self._cached_raw_relationships

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

        # Cache the results
        self._cached_raw_relationships = all_relationships
        self._cached_raw_relationships_depth = max_depth

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

        Optimized with:
        - Qdrant-level filtering to fetch only class components
        - Batch set_payload calls (one per parent class instead of per point)
        - Minimal payload fetching (only 'name' and 'type' fields)

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
            # Import Qdrant filter models
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            # Scan collection for class components using Qdrant-level filtering
            logger.info(
                f"Scanning collection {collection_name} for class components..."
            )
            class_name_to_ids: Dict[str, List[str]] = defaultdict(list)

            # Filter at Qdrant level for type=class
            class_filter = Filter(
                must=[FieldCondition(key="type", match=MatchValue(value="class"))]
            )

            offset = None
            total_scanned = 0
            while True:
                scroll_result = self.client.scroll(
                    collection_name=collection_name,
                    limit=100,
                    offset=offset,
                    scroll_filter=class_filter,  # Filter at Qdrant level
                    with_payload=["name", "type"],  # Only fetch needed fields
                )
                points, next_offset = scroll_result

                if not points:
                    break

                for point in points:
                    payload = point.payload or {}
                    name = payload.get("name")
                    if name:
                        class_name_to_ids[name].append(str(point.id))
                    total_scanned += 1

                if next_offset is None:
                    break
                offset = next_offset

            logger.info(
                f"Scanned {total_scanned} class points, found {len(class_name_to_ids)} unique class names"
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

                # Batch update: set_payload accepts multiple point IDs at once
                try:
                    self.client.set_payload(
                        collection_name=collection_name,
                        payload={"relationships": relationships_payload},
                        points=point_ids,  # All points for this parent class at once
                    )
                    enriched_count += len(point_ids)
                    logger.debug(
                        f"Enriched {len(point_ids)} points for {parent_class}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to enrich {parent_class} ({len(point_ids)} points): {e}"
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

    def get_field_for_child(
        self, parent: str, child: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get field metadata for where a child component belongs in a parent.

        This is a simple lookup for a single parent-child pair, useful for
        DSL rendering where you need to know which field to populate.

        Args:
            parent: Parent component name (e.g., "DecoratedText")
            child: Child component name (e.g., "Button")

        Returns:
            Dict with field_name, json_path, is_optional - or None if invalid relationship

        Example:
            >>> wrapper.get_field_for_child("DecoratedText", "Button")
            {"field_name": "button", "json_path": "decoratedText.button", "is_optional": True}

            >>> wrapper.get_field_for_child("DecoratedText", "Icon")
            {"field_name": "icon", "json_path": "decoratedText.startIcon", "is_optional": True}

            >>> wrapper.get_field_for_child("DecoratedText", "Grid")
            None  # Invalid relationship
        """
        by_parent = self.extract_relationships_by_parent()
        for rel in by_parent.get(parent, []):
            if rel["child_class"] == child:
                return {
                    "field_name": rel["field_name"],
                    "json_path": rel.get("json_path"),
                    "is_optional": rel.get("is_optional", True),
                }
        return None

    def invalidate_caches(self) -> None:
        """Invalidate all cached data including relationships."""
        self._cached_relationships = None
        self._cached_raw_relationships = None
        self._cached_raw_relationships_depth = None
        # Also invalidate symbol caches if they exist
        if hasattr(self, "_symbol_mapping"):
            self._symbol_mapping = None
        if hasattr(self, "_reverse_symbol_mapping"):
            self._reverse_symbol_mapping = None
        if hasattr(self, "_dsl_metadata_cache"):
            self._dsl_metadata_cache = None
        logger.info("Caches invalidated")

    def register_custom_components(
        self,
        custom_relationships: Dict[str, List[str]],
        generate_symbols: bool = True,
        custom_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, str]:
        """
        Register custom components that don't exist in the introspected module.

        This is useful for Google Chat API components (Carousel, NestedWidget, etc.)
        that exist in the API but not in the card_framework Python package.

        The method:
        1. Adds the custom relationships to the cached relationships
        2. Generates symbols for new components using SymbolGenerator
        3. Updates symbol_mapping and reverse_symbol_mapping
        4. Creates ModuleComponent objects so components appear in self.components

        Args:
            custom_relationships: Dict mapping component names to their children.
                                  e.g., {"Carousel": ["CarouselCard"],
                                         "CarouselCard": ["NestedWidget"]}
            generate_symbols: Whether to generate symbols for new components
            custom_metadata: Optional dict with metadata for each component.
                            e.g., {"Carousel": {"docstring": "...", "json_field": "carousel"}}

        Returns:
            Dict of generated symbols for the new components

        Example:
            >>> wrapper.register_custom_components(
            ...     custom_relationships={
            ...         "Carousel": ["CarouselCard"],
            ...         "CarouselCard": ["NestedWidget"],
            ...     },
            ...     custom_metadata={
            ...         "Carousel": {"docstring": "Scrollable cards", "json_field": "carousel"},
            ...     }
            ... )
            {"Carousel": "©", "CarouselCard": "¢", ...}
        """
        if not custom_relationships:
            return {}

        # Ensure relationships cache exists
        _ = self.relationships

        # Collect all unique component names (parents and children)
        all_custom_names: Set[str] = set()
        for parent, children in custom_relationships.items():
            all_custom_names.add(parent)
            all_custom_names.update(children)

        # Filter to only NEW components (not already in symbol_mapping)
        existing_symbols = getattr(self, "symbol_mapping", {}) or {}
        new_component_names = [
            name for name in all_custom_names if name not in existing_symbols
        ]

        generated_symbols = {}

        if generate_symbols and new_component_names:
            from adapters.module_wrapper.symbol_generator import SymbolGenerator

            # Create generator with existing symbols as "used" to avoid collisions
            generator = SymbolGenerator(module_prefix=None)

            # Pre-register existing symbols to prevent collisions
            for name, sym in existing_symbols.items():
                generator._used_symbols.add(sym)
                generator._component_to_symbol[name] = sym
                generator._symbol_to_component[sym] = name

            # Generate symbols for new components
            generated_symbols = generator.generate_symbols(new_component_names)

            # Update the wrapper's symbol mappings
            if hasattr(self, "symbol_mapping") and self.symbol_mapping is not None:
                self.symbol_mapping.update(generated_symbols)
            else:
                self.symbol_mapping = {**existing_symbols, **generated_symbols}

            if hasattr(self, "reverse_symbol_mapping") and self.reverse_symbol_mapping is not None:
                self.reverse_symbol_mapping.update(
                    {v: k for k, v in generated_symbols.items()}
                )
            else:
                self.reverse_symbol_mapping = {
                    v: k for k, v in self.symbol_mapping.items()
                }

            logger.info(
                f"Generated {len(generated_symbols)} symbols for custom components: "
                f"{list(generated_symbols.keys())}"
            )

        # Update relationships cache with custom relationships
        if self._cached_relationships is not None:
            for parent, children in custom_relationships.items():
                if parent in self._cached_relationships:
                    # Merge with existing, avoiding duplicates
                    existing = set(self._cached_relationships[parent])
                    existing.update(children)
                    self._cached_relationships[parent] = list(existing)
                else:
                    self._cached_relationships[parent] = children

            logger.info(
                f"Registered {len(custom_relationships)} custom component relationships"
            )

        # Create ModuleComponent objects for custom components so they appear
        # in self.components alongside native module components
        self._create_custom_module_components(custom_relationships, custom_metadata)

        # Invalidate DSL metadata cache since relationships changed
        if hasattr(self, "_dsl_metadata_cache"):
            self._dsl_metadata_cache = None

        return generated_symbols

    def _create_custom_module_components(
        self,
        custom_relationships: Dict[str, List[str]],
        custom_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """
        Create ModuleComponent objects for custom components.

        This makes custom components (like Carousel, CarouselCard, NestedWidget)
        appear in self.components alongside native module components, allowing
        them to be discovered and used like any other component.

        Args:
            custom_relationships: Dict mapping component names to their children
            custom_metadata: Optional dict with additional metadata per component
                             e.g., {"Carousel": {"docstring": "...", "json_field": "carousel"}}
        """
        if not hasattr(self, "components"):
            return

        # Get module name for path construction
        module_name = getattr(self, "module_name", "custom")
        # Use a consistent submodule path for custom API components
        custom_module_path = f"{module_name}.v2.api"

        # Collect all unique component names
        all_names: Set[str] = set()
        for parent, children in custom_relationships.items():
            all_names.add(parent)
            all_names.update(children)

        # Filter to components not already in self.components
        existing_paths = set(self.components.keys()) if self.components else set()
        existing_names = {path.split(".")[-1] for path in existing_paths}

        custom_metadata = custom_metadata or {}
        created_components: Dict[str, ModuleComponent] = {}

        for name in all_names:
            if name in existing_names:
                continue  # Skip if already exists

            # Get metadata for this component
            meta = custom_metadata.get(name, {})
            docstring = meta.get("docstring", f"Custom Google Chat API component: {name}")
            json_field = meta.get("json_field", name.lower())

            # Create a synthetic class object for the component
            # This allows get_component_by_path to return something usable
            synthetic_class = type(
                name,
                (),
                {
                    "__doc__": docstring,
                    "_json_field": json_field,
                    "_is_custom_component": True,
                    "_children": custom_relationships.get(name, []),
                }
            )

            # Create ModuleComponent
            component = ModuleComponent(
                name=name,
                obj=synthetic_class,
                module_path=custom_module_path,
                component_type="class",
                docstring=docstring,
                source="",  # No source for synthetic components
            )

            # Store in components dict
            full_path = f"{custom_module_path}.{name}"
            self.components[full_path] = component
            created_components[name] = component

            logger.debug(f"Created custom ModuleComponent: {full_path}")

        # Set up parent-child relationships between custom components
        for parent_name, children in custom_relationships.items():
            if parent_name not in created_components:
                continue
            parent_component = created_components[parent_name]
            for child_name in children:
                if child_name in created_components:
                    child_component = created_components[child_name]
                    parent_component.add_child(child_component)

        if created_components:
            logger.info(
                f"Created {len(created_components)} custom ModuleComponents: "
                f"{list(created_components.keys())}"
            )

    def index_custom_components(
        self,
        custom_components: Dict[str, Dict[str, Any]],
        collection_name: Optional[str] = None,
        module_name: Optional[str] = None,
        component_type: str = "class",
        custom_payload_fields: Optional[Dict[str, Any]] = None,
        generate_symbols: bool = True,
        update_existing: bool = True,
        use_multi_vector: bool = True,
    ) -> int:
        """
        Index custom components to Qdrant for persistence.

        This method creates "synthetic" ModuleComponent entries for components
        that don't exist in the introspected Python module but should be
        searchable and tracked. Works with any module wrapper, not just
        specific frameworks.

        For collections with 3 named vectors (components, inputs, relationships),
        this generates all 3 embeddings using the appropriate models:
        - components: ColBERT 128d (identity: name, type, path, docstring)
        - inputs: ColBERT 128d (values: defaults, parameters)
        - relationships: MiniLM 384d (graph: parent-child connections)

        Args:
            custom_components: Dict mapping component names to their metadata.
                Each entry can have:
                - "children": List of child component names (for relationships)
                - "docstring": Description of the component
                - "json_field": Optional JSON field name in API
                - Any other custom fields to include in payload
                Example: {
                    "MyComponent": {
                        "children": ["ChildA", "ChildB"],
                        "docstring": "Custom component description",
                        "json_field": "myComponent",
                        "category": "widgets"
                    }
                }
            collection_name: Qdrant collection to store in (defaults to self.collection_name)
            module_name: Module name for the components (defaults to self.module_name or "custom")
            component_type: Type to assign to components (default "class")
            custom_payload_fields: Additional fields to add to all component payloads
            generate_symbols: Whether to generate symbols for components (default True)
            update_existing: Whether to update existing components (default True, uses upsert)
            use_multi_vector: Whether to generate all 3 vectors for multi-vector collections
                             (components, inputs, relationships). Default True.

        Returns:
            Number of components indexed

        Example:
            >>> # Index API components not in the Python package
            >>> custom = {
            ...     "Carousel": {"children": ["CarouselCard"], "docstring": "Card carousel"},
            ...     "CarouselCard": {"children": ["NestedWidget"], "docstring": "Card in carousel"},
            ... }
            >>> count = wrapper.index_custom_components(custom)
            >>> print(f"Indexed {count} custom components")

            >>> # Index with custom module name and extra fields
            >>> count = wrapper.index_custom_components(
            ...     custom_components={"MyWidget": {"children": [], "docstring": "My widget"}},
            ...     module_name="my_module",
            ...     custom_payload_fields={"category": "custom", "version": "1.0"}
            ... )
        """
        import hashlib
        from datetime import UTC, datetime

        if collection_name is None:
            collection_name = getattr(self, "collection_name", None)

        if not collection_name:
            logger.warning("No collection_name available - cannot index custom components")
            return 0

        if not hasattr(self, "client") or not self.client:
            logger.warning("No Qdrant client - cannot index custom components")
            return 0

        if not hasattr(self, "embedder") or not self.embedder:
            logger.warning("No embedder available - cannot index custom components")
            return 0

        try:
            from .qdrant_mixin import _get_qdrant_imports

            _, qdrant_models = _get_qdrant_imports()
        except Exception as e:
            logger.error(f"Failed to import Qdrant models: {e}")
            return 0

        # Ensure we have symbols for these components (if requested)
        if generate_symbols:
            custom_relationships = {
                name: meta.get("children", []) for name, meta in custom_components.items()
            }
            generated_symbols = self.register_custom_components(
                custom_relationships, generate_symbols=True
            )
        else:
            generated_symbols = {}

        # Merge with existing symbols
        all_symbols = getattr(self, "symbol_mapping", {}) or {}
        all_symbols.update(generated_symbols)

        # Resolve module name
        resolved_module_name = module_name or getattr(self, "module_name", "custom")

        # Detect collection vector configuration
        has_multi_vector = False
        vector_names = []
        try:
            collection_info = self.client.get_collection(collection_name)
            vectors_config = collection_info.config.params.vectors
            if isinstance(vectors_config, dict):
                has_multi_vector = True
                vector_names = list(vectors_config.keys())
                logger.debug(f"Collection has named vectors: {vector_names}")
        except Exception as e:
            logger.debug(f"Could not detect vector config: {e}")

        # Initialize embedders for multi-vector collections
        colbert_embedder = None
        relationships_embedder = None

        if use_multi_vector and has_multi_vector and "components" in vector_names:
            try:
                from fastembed import LateInteractionTextEmbedding, TextEmbedding

                # ColBERT for components and inputs (128d multi-vector)
                colbert_embedder = LateInteractionTextEmbedding("colbert-ir/colbertv2.0")
                # MiniLM for relationships (384d dense)
                relationships_embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
                logger.info("Initialized ColBERT + MiniLM embedders for 3-vector indexing")
            except ImportError as e:
                logger.warning(f"FastEmbed models not available, falling back to single vector: {e}")
                has_multi_vector = False

        logger.info(f"Indexing {len(custom_components)} custom components to Qdrant (module: {resolved_module_name}, multi-vector: {has_multi_vector and use_multi_vector})...")

        points = []
        index_version = datetime.now(UTC).isoformat()

        for name, metadata in custom_components.items():
            children = metadata.get("children", [])
            docstring = metadata.get("docstring", f"Custom component: {name}")
            json_field = metadata.get("json_field", name[0].lower() + name[1:])

            # Get symbol for this component
            symbol = all_symbols.get(name, "")

            # === Build text for each vector ===

            # COMPONENTS: Identity (Name + Type + Path + Docstring)
            component_text = f"Name: {name}\nType: {component_type}\nPath: {resolved_module_name}.{name}"
            if docstring:
                component_text += f"\nDocumentation: {docstring}"
            # Symbol wrapping for ColBERT: "{symbol} {text} {symbol}"
            if symbol:
                component_text = f"{symbol} {component_text} {symbol}"

            # INPUTS: Values (defaults, parameters - for custom components, use docstring)
            inputs_text = f"{name} {component_type}"
            if json_field:
                inputs_text += f", json_field={json_field}"
            if symbol:
                inputs_text = f"{symbol} {inputs_text} {symbol}"

            # RELATIONSHIPS: Graph (parent-child connections with DSL notation)
            if children:
                child_parts = []
                for child in children:
                    child_sym = all_symbols.get(child, "")
                    if child_sym:
                        child_parts.append(f"{child_sym} {child}")
                    else:
                        child_parts.append(child)
                relationship_text = f"{symbol} {name} | contains {', '.join(child_parts)} | {symbol}[{','.join([all_symbols.get(c, c) for c in children])}]"
            else:
                relationship_text = f"{symbol} {name} | no children | {symbol}[]" if symbol else f"{name}:{component_type}[]"

            # === Generate embeddings ===
            try:
                if use_multi_vector and has_multi_vector and colbert_embedder and relationships_embedder:
                    # Generate all 3 vectors
                    comp_emb = list(colbert_embedder.embed([component_text]))[0]
                    comp_vec = comp_emb.tolist() if hasattr(comp_emb, "tolist") else [list(v) for v in comp_emb]

                    inputs_emb = list(colbert_embedder.embed([inputs_text]))[0]
                    inputs_vec = inputs_emb.tolist() if hasattr(inputs_emb, "tolist") else [list(v) for v in inputs_emb]

                    rel_emb = list(relationships_embedder.embed([relationship_text]))[0]
                    rel_vec = rel_emb.tolist() if hasattr(rel_emb, "tolist") else list(rel_emb)

                    vector_data = {
                        "components": comp_vec,
                        "inputs": inputs_vec,
                        "relationships": rel_vec,
                    }
                else:
                    # Single vector fallback using wrapper's embedder
                    embed_text = "\n".join([
                        f"Name: {name}",
                        f"Type: {component_type}",
                        f"Path: {resolved_module_name}.{name}",
                        f"Documentation: {docstring}",
                        f"Children: {', '.join(children) if children else 'none'}",
                    ])
                    embedding_list = list(self.embedder.embed([embed_text]))
                    embedding = embedding_list[0] if embedding_list else None

                    if embedding is None:
                        logger.warning(f"No embedding generated for {name}")
                        continue

                    vector_list = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

                    # Use appropriate vector name or unnamed
                    if has_multi_vector and "relationships" in vector_names:
                        vector_data = {"relationships": vector_list}
                    else:
                        vector_data = vector_list

            except Exception as e:
                logger.warning(f"Failed to generate embedding for {name}: {e}")
                continue

            # Create deterministic ID
            id_string = f"{collection_name}:{resolved_module_name}.{name}"
            hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
            component_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

            # Build payload
            payload = {
                "name": name,
                "type": component_type,
                "module_path": resolved_module_name,
                "full_path": f"{resolved_module_name}.{name}",
                "docstring": docstring,
                "source": "",  # No source for API-only components
                "indexed_at": index_version,
                "module_version": "custom",
                "is_custom_component": True,  # Flag to identify custom components
                "json_field": json_field,
                "inputs_text": inputs_text,  # Store for debugging
                "relationship_text": relationship_text,  # Store for debugging
            }

            # Add any extra fields from metadata (excluding reserved keys)
            reserved_keys = {"children", "docstring", "json_field"}
            for key, value in metadata.items():
                if key not in reserved_keys:
                    payload[key] = value

            # Add global custom payload fields
            if custom_payload_fields:
                payload.update(custom_payload_fields)

            # Add symbol (if symbol generation was enabled)
            if symbol:
                payload["symbol"] = symbol
                payload["symbol_dsl"] = f"{symbol}={name}"
                payload["embedding_format"] = "symbol_wrapped"

            # Add relationships
            if children:
                child_symbols = [all_symbols.get(c, "") for c in children]
                payload["relationships"] = {
                    "children": [{"child_class": c, "field_name": c.lower()} for c in children],
                    "child_classes": children,
                    "child_symbols": [s for s in child_symbols if s],
                    "max_depth": 1,
                    "nl_descriptions": f"{name.lower()} containing {', '.join(children).lower()}",
                    "compact_text": relationship_text,
                    "symbol_enriched": bool(symbol),
                }

            # Create point
            point = qdrant_models["PointStruct"](
                id=component_id,
                vector=vector_data,
                payload=payload,
            )
            points.append(point)

        if not points:
            logger.warning("No valid points to index")
            return 0

        # Upsert to Qdrant
        try:
            self.client.upsert(collection_name=collection_name, points=points)
            logger.info(f"Successfully indexed {len(points)} custom components to {collection_name}")
            return len(points)
        except Exception as e:
            logger.error(f"Failed to upsert custom components: {e}", exc_info=True)
            return 0


# Export for convenience
__all__ = [
    "RelationshipsMixin",
]
