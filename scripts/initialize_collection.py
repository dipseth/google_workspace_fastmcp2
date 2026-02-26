#!/usr/bin/env python3
"""
Initialize Card Collection

This script creates the collection with three named vectors:
1. components (128d) - Component identity: Name + Type + Path + Docstring + Symbol
2. inputs (128d) - Input values: Literals, defaults, enum values / instance_params
3. relationships (384d) - Graph: Parent-child connections, NL descriptions

Symbol embedding is integrated during ingestion:
- Each component gets a unique Unicode symbol (e.g., ᵬ=Button, §=Section)
- Symbols are embedded alongside component identity for semantic association
- Queries containing symbols (like "ᵬ[ᵬ×2]") match the right components

Usage:
    python scripts/initialize_collection.py
"""

import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


# Collection configuration
COLLECTION_NAME = "mcp_gchat_cards"

# Vector dimensions
COLBERT_DIM = 128  # ColBERT multi-vector
RELATIONSHIPS_DIM = 384  # MiniLM dense vector

# =============================================================================
# SYMBOL OVERRIDES (Optional - comment out to use auto-generated symbols)
# =============================================================================
# The SymbolGenerator in adapters/symbol_generator.py auto-generates symbols
# based on first letter using visually similar Unicode characters:
#   B → ["ᵬ", "Ƀ", "β", "ℬ", "ɓ"]  (for Button, ButtonList)
#   S → ["§", "ʂ", "ş", "ș", "σ"]  (for Section, SelectionInput)
#   G → ["ℊ", "ǵ", "ǧ", "γ", "ɠ"]  (for Grid, GridItem)
#
# These overrides are only needed if you want specific symbol assignments.
# Uncomment and import in index_components() if needed.
#
# Symbol overrides are NOT used - we rely on auto-generation based on:
# 1. Hierarchy priority (components with more children get priority)
# 2. Name length bonus (shorter names get their letter's first symbol)
# This ensures intuitive mappings like §=Section, ᵬ=Button automatically.


def create_collection(force_recreate: bool = False):
    """Create the collection with three named vectors and optimized HNSW configs."""
    from qdrant_client.models import (
        Distance,
        HnswConfigDiff,
        MultiVectorComparator,
        MultiVectorConfig,
        VectorParams,
    )

    from config.qdrant_client import get_qdrant_client

    client = get_qdrant_client()
    if not client:
        print("ERROR: Could not connect to Qdrant")
        return False

    # Check if collection exists
    collections = client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if COLLECTION_NAME in collection_names:
        info = client.get_collection(COLLECTION_NAME)
        print(f"Collection {COLLECTION_NAME} exists with {info.points_count} points")

        if force_recreate:
            print(f"Force recreate enabled - deleting {COLLECTION_NAME}...")
            client.delete_collection(COLLECTION_NAME)
            collection_names.remove(COLLECTION_NAME)
        else:
            # Show vector config
            vectors = info.config.params.vectors
            if isinstance(vectors, dict):
                print("Named vectors:")
                for name, config in vectors.items():
                    hnsw = getattr(config, "hnsw_config", None)
                    hnsw_str = f", m={hnsw.m}" if hnsw and hnsw.m else ""
                    print(f"  {name}: size={config.size}{hnsw_str}")
            return True

    print(f"Creating {COLLECTION_NAME} with three named vectors...")

    # HNSW Configuration Strategy:
    # - components/inputs: ColBERT multi-vector with MAX_SIM aggregation
    #   Default m=16 is fine for token-level matching
    # - relationships: Dense 384d for graph traversal queries
    #   Higher m=32 for better recall on relationship searches

    # Create collection with all three vectors
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            # Component identity: Name + Type + Path + Docstring
            "components": VectorParams(
                size=COLBERT_DIM,
                distance=Distance.COSINE,
                multivector_config=MultiVectorConfig(
                    comparator=MultiVectorComparator.MAX_SIM
                ),
                hnsw_config=HnswConfigDiff(
                    m=16,  # Default for multi-vector
                    ef_construct=100,
                ),
            ),
            # Input values: Literals, defaults, enums / instance_params
            "inputs": VectorParams(
                size=COLBERT_DIM,
                distance=Distance.COSINE,
                multivector_config=MultiVectorConfig(
                    comparator=MultiVectorComparator.MAX_SIM
                ),
                hnsw_config=HnswConfigDiff(
                    m=16,  # Default for multi-vector
                    ef_construct=100,
                ),
            ),
            # Graph: Parent-child relationships, NL descriptions
            # Higher m for better recall on relationship/graph queries
            "relationships": VectorParams(
                size=RELATIONSHIPS_DIM,
                distance=Distance.COSINE,
                hnsw_config=HnswConfigDiff(
                    m=32,  # Higher connectivity for relationship graph
                    ef_construct=200,  # More thorough index construction
                ),
            ),
        },
    )

    print(f"Created {COLLECTION_NAME}")

    # Create payload indexes for efficient filtering
    # Note: is_principal only available for numeric types (integer, float, datetime)
    # For keyword fields, we use standard indexes which enable fast Match filtering
    print("\nCreating payload indexes...")

    from qdrant_client.models import KeywordIndexParams, KeywordIndexType

    # name - Primary filter field for component lookups
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="name",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ name (keyword)")

    # type - Filter by component type (class, function, instance_pattern)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="type",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ type (keyword)")

    # module_path - Filter by module
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="module_path",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ module_path (keyword)")

    # full_path - Exact path matching
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="full_path",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ full_path (keyword)")

    # symbol - Fast symbol → component lookup (DSL resolution)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="symbol",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ symbol (keyword)")

    # symbol_dsl - Fast lookup by "ᵬ=Button" format
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="symbol_dsl",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ symbol_dsl (keyword)")

    # Verify
    info = client.get_collection(COLLECTION_NAME)
    vectors = info.config.params.vectors
    print("\nNamed vectors configured:")
    for name, config in vectors.items():
        hnsw = getattr(config, "hnsw_config", None)
        hnsw_str = f", m={hnsw.m}" if hnsw else ""
        multivec = getattr(config, "multivector_config", None)
        mv_str = " (multi-vector)" if multivec else ""
        print(f"  {name}: size={config.size}{hnsw_str}{mv_str}")

    print("\nPayload indexes configured:")
    for field, schema in info.payload_schema.items():
        print(f"  {field}: {schema.data_type}")

    return True


def extract_input_values(component) -> str:
    """
    Extract input values text for the 'inputs' vector.

    For classes: field defaults, enum values, literal annotations
    For functions: parameter defaults
    For variables: the actual value representation
    """
    import dataclasses
    import inspect

    parts = []
    obj = component.obj
    comp_type = component.component_type

    if comp_type == "class" and obj:
        # Check for enum values
        if hasattr(obj, "__members__"):
            members = list(obj.__members__.keys())[:10]
            if members:
                parts.append(f"enum values: {', '.join(members)}")

        # Check for dataclass fields with defaults
        if dataclasses.is_dataclass(obj):
            for field in dataclasses.fields(obj):
                if field.default is not dataclasses.MISSING:
                    parts.append(f"{field.name}={repr(field.default)}")
                elif field.default_factory is not dataclasses.MISSING:
                    parts.append(f"{field.name}=<factory>")

    elif comp_type == "function" and obj:
        # Get function signature defaults
        try:
            sig = inspect.signature(obj)
            for name, param in sig.parameters.items():
                if param.default is not inspect.Parameter.empty:
                    default_repr = repr(param.default)[:50]
                    parts.append(f"{name}={default_repr}")
        except (ValueError, TypeError):
            pass

    elif comp_type == "variable":
        # For variables, use the source or a representation
        if component.source:
            # Extract assignment value if present
            source = component.source[:200]
            parts.append(f"value: {source}")

    # If no specific inputs found, use a minimal description
    if not parts:
        parts.append(f"{component.name} {comp_type}")

    return ", ".join(parts)


def build_compact_relationship_text(
    component_name: str, relationships: List[Dict], component_type: str = "class"
) -> str:
    """
    Build compact, structured relationship text for embedding.

    Converts verbose relationship descriptions into a compact, pattern-friendly format
    that embeds more efficiently and produces better semantic matches.

    Examples:
        Verbose: "DecoratedText with Icon, Button, OnClick. decorated text with icon,
                  decorated text with button, decorated text containing onclick"
        Compact: "DecoratedText[icon:Icon?, button:Button?, on_click:OnClick?]"

        Verbose: "Grid with GridItem, GridItem, GridItem, GridItem"
        Compact: "Grid[4×GridItem]"

        Verbose: "Columns with Column, Column containing DecoratedText"
        Compact: "Columns[2×Column[widgets]]"

    Args:
        component_name: Name of the parent component
        relationships: List of relationship dicts with keys:
            - field_name: Field in parent that holds child
            - child_class: Name of child class
            - is_optional: Whether field is optional
            - depth: Nesting depth
        component_type: Type of component ("class", "function", etc.)

    Returns:
        Compact relationship text suitable for embedding
    """
    if not relationships:
        return f"{component_name}:{component_type}[]"

    # Group relationships by child class to detect repetition
    child_counts = {}
    fields_by_child = {}

    for rel in relationships:
        child = rel.get("child_class", "")
        field = rel.get("field_name", "")
        optional = rel.get("is_optional", True)

        if child:
            child_counts[child] = child_counts.get(child, 0) + 1
            if child not in fields_by_child:
                fields_by_child[child] = []
            fields_by_child[child].append((field, optional))

    # Build compact representation
    parts = []
    processed_children = set()

    for rel in relationships:
        child = rel.get("child_class", "")
        field = rel.get("field_name", "")
        optional = rel.get("is_optional", True)

        if child in processed_children:
            continue

        count = child_counts.get(child, 1)
        opt_marker = "?" if optional else ""

        if count > 1:
            # Multiple instances of same child type - use multiplier notation
            # e.g., "buttons:Button*3" or "items:GridItem*6"
            fields = [f[0] for f in fields_by_child[child]]
            if len(set(fields)) == 1:
                # Same field repeated (like list items)
                parts.append(f"{fields[0]}:{child}×{count}")
            else:
                # Different fields with same type
                parts.append(f"{child}×{count}[{','.join(fields)}]")
            processed_children.add(child)
        else:
            # Single instance
            parts.append(f"{field}:{child}{opt_marker}")

    return f"{component_name}[{', '.join(parts)}]"


def build_compact_structure_text(
    component_paths: List[str],
    structure_description: str = "",
    symbol_mapping: Optional[Dict[str, str]] = None,
    wrapper: Optional["ModuleWrapper"] = None,
) -> str:
    """
    Build compact structure text for instance patterns WITH DSL NOTATION.

    Delegates to ModuleWrapper.build_dsl_from_paths() which is the canonical
    implementation. This ensures consistent DSL notation across all ingestion paths.

    Examples:
        Paths: ["Section", "DecoratedText", "ButtonList", "Button"]
        DSL: "§[δ, Ƀ, ᵬ] | Section DecoratedText ButtonList Button"

        Paths: ["Section", "DecoratedText", "DecoratedText", "DecoratedText"]
        DSL: "§[δ×3] | Section DecoratedText×3"

    Args:
        component_paths: List of component paths or names
        structure_description: Optional natural language description
        symbol_mapping: DEPRECATED - ignored, uses wrapper.symbol_mapping
        wrapper: Optional ModuleWrapper instance (fetched if not provided)

    Returns:
        DSL-notation structure text suitable for embedding
    """
    # Use provided wrapper or get from card_framework_wrapper
    if wrapper is None:
        try:
            from gchat.card_framework_wrapper import get_card_framework_wrapper

            wrapper = get_card_framework_wrapper()
        except Exception:
            # Fallback if wrapper unavailable
            if not component_paths:
                return (
                    f"§[] | {structure_description[:100]}"
                    if structure_description
                    else "§[]"
                )
            names = [p.split(".")[-1] if "." in p else p for p in component_paths]
            return f"§[...] | {' '.join(names)}"

    # Use the canonical implementation from ModuleWrapper
    return wrapper.build_dsl_from_paths(component_paths, structure_description)


def index_components():
    """Index card_framework components with deterministic symbol-wrapped embeddings."""
    import hashlib

    from fastembed import LateInteractionTextEmbedding, TextEmbedding
    from qdrant_client.models import PointStruct

    from adapters.module_wrapper import ModuleWrapper
    from adapters.structure_validator import StructureValidator
    from config.qdrant_client import get_qdrant_client

    print("\n" + "=" * 60)
    print("INDEXING COMPONENTS (WITH SYMBOL-ENRICHED EMBEDDINGS)")
    print("=" * 60)

    # Initialize wrapper - use existing v6 to discover components
    wrapper = ModuleWrapper(
        module_or_name="card_framework",
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_api_key=os.getenv("QDRANT_KEY"),
        collection_name="mcp_gchat_cards_v6",
        auto_initialize=True,
        index_nested=True,
    )

    # Generate symbols automatically based on hierarchy priority + name length
    # No explicit overrides - the algorithm should produce intuitive mappings
    print("\nGenerating symbols (auto-generated)...")
    symbol_mapping = wrapper.symbol_mapping  # Uses priority + length bonus
    print(f"  Symbol mapping generated: {len(symbol_mapping)} symbols")

    # Initialize structure validator for symbol-enriched relationship text
    # This creates text like: "Ƀ ButtonList | contains ᵬ Button | Ƀ[ᵬ]"
    print("\nInitializing structure validator for symbol-enriched relationships...")
    structure_validator = StructureValidator(wrapper)
    # Pre-cache relationships (symbols already cached via wrapper.symbol_mapping)
    _ = structure_validator.relationships
    print(
        f"  Validator ready with {len(structure_validator.relationships)} parent relationships"
    )

    # Initialize embedders
    print("\nInitializing embedders...")
    colbert_embedder = LateInteractionTextEmbedding("colbert-ir/colbertv2.0")
    relationships_embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    print("  ColBERT embedder ready (128d multi-vector)")
    print("  MiniLM embedder ready (384d dense)")

    print(f"\nLoaded {len(wrapper.components)} components")

    # Extract relationships
    print("\nExtracting relationships...")
    relationships_by_parent = wrapper.extract_relationships_by_parent(max_depth=5)
    print(f"  Found relationships for {len(relationships_by_parent)} parent classes")

    # Index components
    client = get_qdrant_client()
    points = []
    batch_size = 20

    print("\nGenerating embeddings and creating points...")
    for i, (path, component) in enumerate(wrapper.components.items()):
        # === COMPONENTS VECTOR: Identity (Name + Type + Path + Docstring) ===
        # Build the base component text
        component_text = f"Name: {component.name}\nType: {component.component_type}\nPath: {component.full_path}"
        if component.docstring:
            component_text += f"\nDocumentation: {component.docstring[:500]}"

        # Get symbol for this component (if it has one)
        component_symbol = wrapper.get_symbol_for_component(component.name)

        # Apply deterministic symbol wrapping for ColBERT embedding
        # Format: "{symbol} {text} {symbol}" - ALWAYS this format if symbol exists
        # This creates strong bidirectional token-level association
        component_text = wrapper.get_symbol_wrapped_text(component.name, component_text)

        # === INPUTS VECTOR: Values (defaults, enums, literals) ===
        inputs_text = extract_input_values(component)
        # Also wrap inputs with symbol for consistent matching
        inputs_text = wrapper.get_symbol_wrapped_text(component.name, inputs_text)

        # === RELATIONSHIPS VECTOR: Graph (parent-child connections) ===
        # Use symbol-enriched format for better embedding efficiency
        # Format: "Ƀ ButtonList | contains ᵬ Button | Ƀ[ᵬ]"
        # This embeds symbols alongside relationships so semantic search works with DSL
        rels = (
            relationships_by_parent.get(component.name, [])
            if component.component_type == "class"
            else []
        )
        if (
            component.component_type == "class"
            and component.name in structure_validator.symbols
        ):
            # Use symbol-enriched relationship text
            relationship_text = structure_validator.get_enriched_relationship_text(
                component.name
            )
        else:
            # Fall back to compact format for non-class components
            relationship_text = build_compact_relationship_text(
                component.name, rels, component.component_type
            )
        # Extract child_classes for payload (still useful for filtering)
        child_classes = list(set(r["child_class"] for r in rels)) if rels else []

        # Generate embeddings
        comp_emb = list(colbert_embedder.embed([component_text]))[0]
        comp_vec = (
            comp_emb.tolist()
            if hasattr(comp_emb, "tolist")
            else [list(v) for v in comp_emb]
        )

        inputs_emb = list(colbert_embedder.embed([inputs_text]))[0]
        inputs_vec = (
            inputs_emb.tolist()
            if hasattr(inputs_emb, "tolist")
            else [list(v) for v in inputs_emb]
        )

        rel_emb = list(relationships_embedder.embed([relationship_text]))[0]
        rel_vec = rel_emb.tolist() if hasattr(rel_emb, "tolist") else list(rel_emb)

        # Generate deterministic ID
        id_string = f"{COLLECTION_NAME}:{path}"
        hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
        point_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

        # Build payload
        payload = component.to_dict()
        payload["indexed_at"] = "symbol_wrapped"  # Deterministic symbol wrapping
        payload["inputs_text"] = (
            inputs_text  # Store for debugging (includes symbol wrapping)
        )
        payload["relationship_text"] = relationship_text  # Store symbol-enriched format

        # Store symbol in payload for DSL lookups and reverse mapping
        if component_symbol:
            payload["symbol"] = component_symbol
            payload["symbol_dsl"] = (
                f"{component_symbol}={component.name}"  # e.g., "ᵬ=Button"
            )
            payload["embedding_format"] = (
                "symbol_wrapped"  # Indicates "{sym} {text} {sym}" format
            )

        if rels:
            payload["relationships"] = {
                "children": rels,
                "child_classes": child_classes,
                "max_depth": max(r["depth"] for r in rels),
                "compact_text": relationship_text,  # Symbol-enriched representation
                "symbol_enriched": component.component_type == "class"
                and component.name in structure_validator.symbols,
            }

        # Create point with three vectors
        point = PointStruct(
            id=point_id,
            vector={
                "components": comp_vec,
                "inputs": inputs_vec,
                "relationships": rel_vec,
            },
            payload=payload,
        )
        points.append(point)

        # Batch upsert
        if len(points) >= batch_size:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            print(f"  Indexed {i + 1} components...")
            points = []

    # Final batch
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)

    # Verify
    info = client.get_collection(COLLECTION_NAME)
    print(f"\n✅ Indexed {info.points_count} points into {COLLECTION_NAME}")

    return info.points_count


def format_instance_params(params: dict) -> str:
    """
    Format instance_params for the inputs vector.

    Consistent with extract_input_values() for components,
    this extracts the actual parameter values used.
    """
    if not params:
        return "empty parameters"

    def safe_str(val, max_len=50):
        if val is None:
            return None
        s = str(val)
        return s[:max_len] if len(s) > max_len else s

    parts = []

    if params.get("title"):
        parts.append(f"title={safe_str(params['title'])}")
    if params.get("subtitle"):
        parts.append(f"subtitle={safe_str(params['subtitle'])}")
    if params.get("image_url"):
        parts.append(f"image_url={safe_str(params['image_url'])}")

    buttons = params.get("buttons", [])
    if buttons and isinstance(buttons, list):
        btn_texts = []
        for btn in buttons[:5]:
            if isinstance(btn, dict):
                btn_texts.append(f"{btn.get('text', 'button')}->{btn.get('url', '')}")
            else:
                btn_texts.append(safe_str(btn))
        parts.append(f"buttons=[{', '.join(btn_texts)}]")

    items = params.get("items", [])
    if items and isinstance(items, list):
        item_texts = []
        for item in items[:5]:
            if isinstance(item, dict):
                item_texts.append(safe_str(item.get("text", str(item))))
            else:
                item_texts.append(safe_str(item))
        parts.append(f"items=[{', '.join(filter(None, item_texts))}]")

    sections = params.get("sections", [])
    if sections and isinstance(sections, list):
        parts.append(f"sections={len(sections)}")

    if params.get("grid") or params.get("columns"):
        parts.append("layout=grid")

    return ", ".join(parts) if parts else "basic card"


def index_instance_patterns(colbert_embedder=None, relationships_embedder=None):
    """
    Index instance_patterns from source collection.

    Uses the same three-vector structure as components:
    - components: Identity (name, type, description, parent components)
    - inputs: Actual parameter values used (instance_params)
    - relationships: Which components were instantiated together
    """
    import hashlib

    from fastembed import LateInteractionTextEmbedding, TextEmbedding
    from qdrant_client.models import PointStruct

    from config.qdrant_client import get_qdrant_client

    print("\n" + "=" * 60)
    print("INDEXING INSTANCE PATTERNS")
    print("=" * 60)

    client = get_qdrant_client()

    # Get instance_patterns from v6
    v6_all = client.scroll(
        collection_name="mcp_gchat_cards_v6",
        limit=5000,
        with_payload=True,
    )[0]

    instance_patterns = [
        p for p in v6_all if p.payload.get("type") == "instance_pattern"
    ]
    print(f"\nFound {len(instance_patterns)} instance_patterns in v6")

    if not instance_patterns:
        print("No instance_patterns to migrate")
        return 0

    # Reuse embedders if provided (efficiency)
    if colbert_embedder is None:
        print("\nInitializing embedders...")
        colbert_embedder = LateInteractionTextEmbedding("colbert-ir/colbertv2.0")
    if relationships_embedder is None:
        relationships_embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")

    points = []
    batch_size = 20

    print("\nGenerating embeddings and creating points...")
    for i, p in enumerate(instance_patterns):
        payload = dict(p.payload)

        name = payload.get("name", "")
        card_desc = (
            payload.get("card_description", "")[:300]
            if payload.get("card_description")
            else ""
        )
        parent_paths = payload.get("parent_paths", []) or []
        instance_params = payload.get("instance_params", {}) or {}

        # === COMPONENTS VECTOR: Identity ===
        component_text = f"Name: {name}\nType: instance_pattern"
        if card_desc:
            component_text += f"\nDescription: {card_desc}"
        if parent_paths:
            component_names = [pp.split(".")[-1] for pp in parent_paths[:5]]
            component_text += f"\nComponents: {', '.join(component_names)}"

        # === INPUTS VECTOR: Actual parameter values ===
        inputs_text = format_instance_params(instance_params)

        # === RELATIONSHIPS VECTOR: Component connections WITH DSL NOTATION ===
        # Use DSL notation so queries like "§[δ×3, Ƀ]" match these patterns
        if parent_paths:
            relationship_text = build_compact_structure_text(
                parent_paths,
                card_desc,
                symbol_mapping=None,  # Will fetch from wrapper
            )
        else:
            relationship_text = f"{name} instance pattern"

        # Generate embeddings
        comp_emb = list(colbert_embedder.embed([component_text]))[0]
        comp_vec = (
            comp_emb.tolist()
            if hasattr(comp_emb, "tolist")
            else [list(v) for v in comp_emb]
        )

        inputs_emb = list(colbert_embedder.embed([inputs_text]))[0]
        inputs_vec = (
            inputs_emb.tolist()
            if hasattr(inputs_emb, "tolist")
            else [list(v) for v in inputs_emb]
        )

        rel_emb = list(relationships_embedder.embed([relationship_text]))[0]
        rel_vec = rel_emb.tolist() if hasattr(rel_emb, "tolist") else list(rel_emb)

        # Generate deterministic ID (consistent with components)
        id_string = f"{COLLECTION_NAME}:instance_pattern:{p.id}"
        hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
        point_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

        # Update payload
        payload["indexed_at"] = "dsl_enriched"
        payload["inputs_text"] = inputs_text
        payload["relationship_text"] = (
            relationship_text  # DSL notation for semantic search
        )

        # Create point with three vectors (same structure as components)
        point = PointStruct(
            id=point_id,
            vector={
                "components": comp_vec,
                "inputs": inputs_vec,
                "relationships": rel_vec,
            },
            payload=payload,
        )
        points.append(point)

        if len(points) >= batch_size:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            print(f"  Indexed {i + 1} instance_patterns...")
            points = []

    # Final batch
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)

    # Verify
    info = client.get_collection(COLLECTION_NAME)
    print(f"\n✅ Collection now has {info.points_count} total points")

    return len(instance_patterns)


def test_search():
    """Test searching with all three vectors."""
    from fastembed import LateInteractionTextEmbedding, TextEmbedding

    from config.qdrant_client import get_qdrant_client

    print("\n" + "=" * 60)
    print("TESTING SEARCH (ALL VECTORS)")
    print("=" * 60)

    client = get_qdrant_client()
    colbert = LateInteractionTextEmbedding("colbert-ir/colbertv2.0")
    minilm = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")

    # Test components vector (identity search)
    print("\n--- COMPONENTS VECTOR (Identity) ---")
    for query in ["Image widget", "Button class", "OnClick action"]:
        emb = list(colbert.embed([query]))[0]
        vec = emb.tolist() if hasattr(emb, "tolist") else [list(v) for v in emb]
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vec,
            using="components",
            limit=2,
            with_payload=["name", "component_type"],
        )
        print(f"  '{query}' → {[p.payload.get('name') for p in results.points]}")

    # Test inputs vector (values search)
    print("\n--- INPUTS VECTOR (Values) ---")
    for query in ["default=None", "enum values SPINNER", "function with url parameter"]:
        emb = list(colbert.embed([query]))[0]
        vec = emb.tolist() if hasattr(emb, "tolist") else [list(v) for v in emb]
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vec,
            using="inputs",
            limit=2,
            with_payload=["name", "inputs_text"],
        )
        print(f"  '{query}' →")
        for p in results.points:
            inputs = p.payload.get("inputs_text", "")[:60]
            print(f"    {p.payload.get('name')}: {inputs}")

    # Test relationships vector (graph search)
    print("\n--- RELATIONSHIPS VECTOR (Graph) ---")
    for query in ["clickable image", "button with icon", "card with header"]:
        emb = list(minilm.embed([query]))[0]
        vec = emb.tolist() if hasattr(emb, "tolist") else list(emb)
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vec,
            using="relationships",
            limit=2,
            with_payload=["name", "relationships"],
        )
        print(f"  '{query}' →")
        for p in results.points:
            rels = p.payload.get("relationships", {})
            children = rels.get("child_classes", [])
            print(f"    {p.payload.get('name')} (children: {children})")

    # Test symbol-enriched relationships (DSL matching)
    print("\n--- SYMBOL-ENRICHED RELATIONSHIPS (DSL) ---")
    for query in ["Ƀ[ᵬ]", "§ Section contains", "ℊ Grid contains ǵ GridItem"]:
        emb = list(minilm.embed([query]))[0]
        vec = emb.tolist() if hasattr(emb, "tolist") else list(emb)
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vec,
            using="relationships",
            limit=2,
            with_payload=["name", "symbol", "relationships"],
        )
        print(f"  '{query}' →")
        for p in results.points:
            sym = p.payload.get("symbol", "?")
            name = p.payload.get("name", "?")
            rels = p.payload.get("relationships", {})
            compact = rels.get("compact_text", "")[:60] if rels else ""
            print(f"    {sym}={name}: {compact}")


def main():
    print("=" * 60)
    print("COLLECTION INITIALIZATION")
    print("=" * 60)

    # Step 1: Create collection with HNSW configs
    print("\nStep 1: Creating collection...")
    if not create_collection(force_recreate=True):
        return

    # Step 2: Index module components
    print("\nStep 2: Indexing module components...")
    component_count = index_components()

    # Step 3: Index instance patterns (from v6)
    print("\nStep 3: Indexing instance patterns...")
    pattern_count = index_instance_patterns()

    if component_count > 0 or pattern_count > 0:
        # Step 4: Test search
        print("\nStep 4: Testing search...")
        test_search()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Module components: {component_count}")
    print(f"  Instance patterns: {pattern_count}")
    print(f"  Total points: {component_count + pattern_count}")
    print("\n  Vector Indexes (HNSW):")
    print("    - components: Identity (m=16, ColBERT 128d)")
    print("    - inputs: Values (m=16, ColBERT 128d)")
    print("    - relationships: Graph (m=32, MiniLM 384d)")
    print("\n  Payload Indexes (keyword):")
    print("    - name - filter by component name")
    print("    - type - filter by class/function/instance_pattern")
    print("    - module_path - filter by module")
    print("    - full_path - exact path matching")
    print("=" * 60)


if __name__ == "__main__":
    main()
