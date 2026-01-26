#!/usr/bin/env python3
"""
Prototype: Component Relationship Extraction for Qdrant

This script demonstrates how to extract component relationships from
card_framework using ModuleWrapper (consistent with SmartCardBuilder)
and type hints, building a graph that can be indexed in Qdrant.

Usage:
    python scripts/prototype_relationship_extraction.py
"""

import dataclasses
import inspect
import os
import sys
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

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


# =========================================================================
# CONFIGURATION - Following the Manifesto pattern
# =========================================================================

# Primitive types to skip (not relationships)
PRIMITIVE_TYPES = {str, int, float, bool, bytes, type(None)}

# Built-in module prefixes to skip
BUILTIN_PREFIXES = {"builtins", "typing", "collections", "abc"}

# Target module - same as SmartCardBuilder
TARGET_MODULE = "card_framework"

# Collection name for relationships (new collection)
RELATIONSHIP_COLLECTION = "mcp_component_relationships"


# =========================================================================
# RELATIONSHIP EXTRACTION - Reusable functions
# =========================================================================


def is_dataclass_type(cls: type) -> bool:
    """Check if a class is a dataclass."""
    return dataclasses.is_dataclass(cls) and isinstance(cls, type)


def unwrap_optional(field_type: type) -> Tuple[type, bool]:
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
        # Multiple non-None types - keep as Union
        return field_type, False

    return field_type, False


def is_component_type(field_type: type) -> bool:
    """Check if a type represents a component (not primitive)."""
    if field_type in PRIMITIVE_TYPES:
        return False

    if not inspect.isclass(field_type):
        return False

    module = getattr(field_type, "__module__", "")
    if any(module.startswith(prefix) for prefix in BUILTIN_PREFIXES):
        return False

    return True


def to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def generate_nl_description(parent: str, child: str) -> str:
    """
    Generate natural language description for a relationship.

    Following Manifesto: NL patterns stored as config, not hardcoded logic.
    """
    # NL_RELATIONSHIP_PATTERNS - Could be moved to top-level config
    patterns = {
        (
            "Image",
            "OnClick",
        ): "clickable image, image with click action, image that opens a link",
        (
            "DecoratedText",
            "OnClick",
        ): "clickable text, text with click action, clickable decorated text",
        (
            "DecoratedText",
            "Button",
        ): "text with button, decorated text with action button",
        ("DecoratedText", "Icon"): "text with icon, decorated text with icon",
        ("Button", "OnClick"): "button click action, button that opens link",
        ("Button", "Icon"): "button with icon, icon button",
        ("Grid", "OnClick"): "clickable grid, grid with click action",
        ("Chip", "OnClick"): "clickable chip, chip with click action",
    }

    key = (parent, child)
    if key in patterns:
        return patterns[key]

    # Generate generic description
    return f"{parent.lower()} with {child.lower()}, {parent.lower()} containing {child.lower()}"


def extract_relationships_from_class(
    cls: type,
    visited: Optional[Set[str]] = None,
    depth: int = 0,
    max_depth: int = 5,
    path_prefix: str = "",
) -> List[Dict[str, Any]]:
    """
    Extract field relationships from a class using type hints.

    This is the core relationship extraction logic that can be integrated
    into ModuleWrapper's ingestion flow.

    Args:
        cls: The class to analyze
        visited: Set of visited class names to prevent cycles
        depth: Current recursion depth
        max_depth: Maximum recursion depth
        path_prefix: Prefix for nested paths (e.g., "decoratedText.button")

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
        # Get type hints - this extracts field type annotations
        hints = get_type_hints(cls)
    except Exception as e:
        print(f"  Warning: Could not get type hints for {class_name}: {e}")
        return []

    for field_name, field_type in hints.items():
        # Skip private fields
        if field_name.startswith("_"):
            continue

        # Unwrap Optional[X]
        unwrapped_type, is_optional = unwrap_optional(field_type)

        # Check if this is a component reference
        if is_component_type(unwrapped_type):
            child_name = unwrapped_type.__name__
            child_module = getattr(unwrapped_type, "__module__", "")

            # Build the relationship path
            if path_prefix:
                rel_path = f"{path_prefix}.{field_name}"
            else:
                rel_path = f"{class_name.lower()}.{field_name}"

            # Convert to camelCase for JSON path
            json_field = to_camel_case(field_name)
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
                "nl_description": generate_nl_description(class_name, child_name),
            }
            relationships.append(relationship)

            # Recursively extract from child class
            if is_dataclass_type(unwrapped_type):
                child_relationships = extract_relationships_from_class(
                    unwrapped_type,
                    visited=visited.copy(),  # Copy to allow multiple paths
                    depth=depth + 1,
                    max_depth=max_depth,
                    path_prefix=json_path,
                )
                # Add parent context to child relationships
                for child_rel in child_relationships:
                    child_rel["root_parent"] = class_name
                    child_rel["intermediate_path"] = rel_path
                relationships.extend(child_relationships)

    return relationships


# =========================================================================
# MODULEWRAPPER INTEGRATION
# =========================================================================


def get_module_wrapper():
    """
    Get ModuleWrapper instance consistent with SmartCardBuilder.

    This uses the same initialization pattern as SmartCardBuilder._get_wrapper()
    """
    from adapters.module_wrapper import ModuleWrapper

    wrapper = ModuleWrapper(
        module_or_name=TARGET_MODULE,
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_api_key=os.getenv("QDRANT_KEY"),
        collection_name=os.getenv("CARD_COLLECTION", "mcp_gchat_cards_v6"),
        auto_initialize=True,  # Index components
        index_nested=True,  # Include nested classes
    )

    return wrapper


def extract_relationships_from_wrapper(wrapper) -> List[Dict[str, Any]]:
    """
    Extract relationships from all components discovered by ModuleWrapper.

    This leverages the existing component discovery flow.
    """
    all_relationships = []
    processed_classes = set()

    print(f"  ModuleWrapper has {len(wrapper.components)} indexed components")

    for full_path, component in wrapper.components.items():
        # Only process classes (not functions/variables)
        if component.component_type != "class":
            continue

        # Skip if already processed
        if component.name in processed_classes:
            continue

        # Get the actual class object
        cls = component.obj
        if cls is None or not inspect.isclass(cls):
            continue

        # Only process dataclasses
        if not is_dataclass_type(cls):
            continue

        processed_classes.add(component.name)
        print(f"  Analyzing: {component.name} ({full_path})")

        # Extract relationships
        relationships = extract_relationships_from_class(cls)
        all_relationships.extend(relationships)

    return all_relationships


# =========================================================================
# QDRANT POINT GENERATION
# =========================================================================


def generate_qdrant_points(
    relationships: List[Dict], dedupe: bool = True
) -> List[Dict]:
    """
    Generate Qdrant point structures from relationships.

    Args:
        relationships: List of relationship dicts
        dedupe: If True, deduplicate by (parent, field, child) tuple

    Returns:
        List of point dicts ready for Qdrant upsert
    """
    import hashlib
    import uuid

    points = []
    seen_ids = set()

    for rel in relationships:
        # Generate deterministic ID based on the full path
        id_string = f"{rel['parent_class']}:{rel['field_name']}:{rel['child_class']}:{rel['json_path']}"
        hash_bytes = hashlib.sha256(id_string.encode()).digest()[:16]
        point_id = str(uuid.UUID(bytes=hash_bytes))

        # Deduplicate
        if dedupe and point_id in seen_ids:
            continue
        seen_ids.add(point_id)

        point = {
            "id": point_id,
            "vector": f"<embedding of: {rel['nl_description']}>",
            "payload": {
                # Component info
                "parent_class": rel["parent_class"],
                "parent_module": rel["parent_module"],
                "parent_path": rel["parent_path"],
                "child_class": rel["child_class"],
                "child_module": rel["child_module"],
                "child_path": rel["child_path"],
                # Relationship info
                "field_name": rel["field_name"],
                "relationship_path": rel["relationship_path"],
                "json_path": rel["json_path"],
                "depth": rel["depth"],
                "is_optional": rel["is_optional"],
                # NL for semantic search
                "nl_description": rel["nl_description"],
                # Context for nested relationships
                "root_parent": rel.get("root_parent"),
                "intermediate_path": rel.get("intermediate_path"),
            },
        }
        points.append(point)

    return points


def filter_by_child_class(relationships: List[Dict], child_class: str) -> List[Dict]:
    """Filter relationships by child class name."""
    return [r for r in relationships if r["child_class"] == child_class]


# =========================================================================
# MAIN
# =========================================================================


def main():
    import json

    print("=" * 70)
    print("COMPONENT RELATIONSHIP EXTRACTION (via ModuleWrapper)")
    print("=" * 70)
    print()

    # Step 1: Initialize ModuleWrapper (same as SmartCardBuilder)
    print(f"Step 1: Initializing ModuleWrapper for {TARGET_MODULE}...")
    try:
        wrapper = get_module_wrapper()
        print(f"  ✅ ModuleWrapper initialized")
    except Exception as e:
        print(f"  ❌ Failed to initialize ModuleWrapper: {e}")
        print("  Falling back to direct module scan...")
        wrapper = None

    # Step 2: Extract relationships
    print()
    print("Step 2: Extracting relationships from type hints...")

    if wrapper and wrapper.components:
        all_relationships = extract_relationships_from_wrapper(wrapper)
    else:
        # Fallback: direct import
        print("  Using direct import fallback...")
        import importlib

        module = importlib.import_module("card_framework.v2")
        all_relationships = []
        for name in dir(module):
            obj = getattr(module, name)
            if is_dataclass_type(obj):
                print(f"  Analyzing: {name}")
                all_relationships.extend(extract_relationships_from_class(obj))

    print(f"  Found {len(all_relationships)} total relationships")
    print()

    # Step 3: Filter OnClick relationships
    print("Step 3: Filtering OnClick relationships...")
    onclick_rels = filter_by_child_class(all_relationships, "OnClick")
    print(f"  Found {len(onclick_rels)} OnClick relationships")
    print()

    # Step 4: Generate Qdrant points (deduped)
    print("Step 4: Generating Qdrant points...")
    points = generate_qdrant_points(onclick_rels, dedupe=True)
    print(f"  Generated {len(points)} unique points")
    print()

    # Step 5: Display OnClick relationship graph
    print("=" * 70)
    print("ONCLICK RELATIONSHIP GRAPH")
    print("=" * 70)
    print()

    # Group by depth
    by_depth = defaultdict(list)
    for point in points:
        by_depth[point["payload"]["depth"]].append(point)

    for depth in sorted(by_depth.keys()):
        print(f"Depth {depth}:")
        for point in by_depth[depth]:
            p = point["payload"]
            optional = "(optional)" if p["is_optional"] else "(required)"
            print(f"  {p['parent_class']}.{p['field_name']} → OnClick {optional}")
            print(f"    JSON path: {p['json_path']}")
            print(f'    NL: "{p["nl_description"]}"')
            if p.get("root_parent"):
                print(f"    Root: {p['root_parent']} via {p.get('intermediate_path')}")
            print()

    # Step 6: Show sample Qdrant points
    print("=" * 70)
    print("SAMPLE QDRANT POINTS")
    print("=" * 70)
    print()

    for i, point in enumerate(points[:3]):
        print(f"Point {i + 1}:")
        print(json.dumps(point, indent=2, default=str))
        print()

    # Step 7: Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"ModuleWrapper components: {len(wrapper.components) if wrapper else 'N/A'}")
    print(f"Total relationships found: {len(all_relationships)}")
    print(f"OnClick relationships: {len(onclick_rels)}")
    print(f"Unique Qdrant points: {len(points)}")
    print()
    print("Unique parents with OnClick:")
    parents = set(p["payload"]["parent_class"] for p in points)
    for parent in sorted(parents):
        count = sum(1 for p in points if p["payload"]["parent_class"] == parent)
        print(f"  - {parent}: {count} path(s)")

    print()
    print("=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("1. Add _extract_relationships() to ModuleWrapper ingestion flow")
    print("2. Create 'mcp_component_relationships' collection in Qdrant")
    print("3. Add query method: find_relationship('clickable image')")
    print("4. Integrate with SmartCardBuilder for dynamic nesting")

    return all_relationships, points


if __name__ == "__main__":
    main()
