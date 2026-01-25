#!/usr/bin/env python3
"""
Initialize mcp_gchat_cards_v7 Collection

This script creates the v7 collection with three named vectors:
1. components (128d) - Component identity: Name + Type + Path + Docstring
2. inputs (128d) - Input values: Literals, defaults, enum values / instance_params
3. relationships (384d) - Graph: Parent-child connections, NL descriptions

Usage:
    python scripts/initialize_v7_collection.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


# Collection configuration
V7_COLLECTION_NAME = "mcp_gchat_cards_v7"

# Vector dimensions
COLBERT_DIM = 128  # ColBERT multi-vector
RELATIONSHIPS_DIM = 384  # MiniLM dense vector


def create_v7_collection(force_recreate: bool = False):
    """Create the v7 collection with three named vectors and optimized HNSW configs."""
    from config.qdrant_client import get_qdrant_client
    from qdrant_client.models import (
        Distance,
        VectorParams,
        MultiVectorConfig,
        MultiVectorComparator,
        HnswConfigDiff,
    )

    client = get_qdrant_client()
    if not client:
        print("ERROR: Could not connect to Qdrant")
        return False

    # Check if collection exists
    collections = client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if V7_COLLECTION_NAME in collection_names:
        info = client.get_collection(V7_COLLECTION_NAME)
        print(f"Collection {V7_COLLECTION_NAME} exists with {info.points_count} points")

        if force_recreate:
            print(f"Force recreate enabled - deleting {V7_COLLECTION_NAME}...")
            client.delete_collection(V7_COLLECTION_NAME)
            collection_names.remove(V7_COLLECTION_NAME)
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

    print(f"Creating {V7_COLLECTION_NAME} with three named vectors...")

    # HNSW Configuration Strategy:
    # - components/inputs: ColBERT multi-vector with MAX_SIM aggregation
    #   Default m=16 is fine for token-level matching
    # - relationships: Dense 384d for graph traversal queries
    #   Higher m=32 for better recall on relationship searches

    # Create collection with all three vectors
    client.create_collection(
        collection_name=V7_COLLECTION_NAME,
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

    print(f"Created {V7_COLLECTION_NAME}")

    # Create payload indexes for efficient filtering
    # Note: is_principal only available for numeric types (integer, float, datetime)
    # For keyword fields, we use standard indexes which enable fast Match filtering
    print("\nCreating payload indexes...")

    from qdrant_client.models import KeywordIndexParams, KeywordIndexType

    # name - Primary filter field for component lookups
    client.create_payload_index(
        collection_name=V7_COLLECTION_NAME,
        field_name="name",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ name (keyword)")

    # type - Filter by component type (class, function, instance_pattern)
    client.create_payload_index(
        collection_name=V7_COLLECTION_NAME,
        field_name="type",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ type (keyword)")

    # module_path - Filter by module
    client.create_payload_index(
        collection_name=V7_COLLECTION_NAME,
        field_name="module_path",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ module_path (keyword)")

    # full_path - Exact path matching
    client.create_payload_index(
        collection_name=V7_COLLECTION_NAME,
        field_name="full_path",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
        ),
    )
    print("  ✅ full_path (keyword)")

    # Verify
    info = client.get_collection(V7_COLLECTION_NAME)
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
    import inspect
    import dataclasses

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


def index_components_v7():
    """Index card_framework components into v7 with three vectors."""
    from adapters.module_wrapper import ModuleWrapper
    from fastembed import TextEmbedding, LateInteractionTextEmbedding
    from config.qdrant_client import get_qdrant_client
    from qdrant_client.models import PointStruct
    import hashlib

    print("\n" + "=" * 60)
    print("INDEXING COMPONENTS INTO V7")
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
        component_text = f"Name: {component.name}\nType: {component.component_type}\nPath: {component.full_path}"
        if component.docstring:
            component_text += f"\nDocumentation: {component.docstring[:500]}"

        # === INPUTS VECTOR: Values (defaults, enums, literals) ===
        inputs_text = extract_input_values(component)

        # === RELATIONSHIPS VECTOR: Graph (parent-child connections) ===
        rels = relationships_by_parent.get(component.name, []) if component.component_type == "class" else []
        if rels:
            child_classes = list(set(r["child_class"] for r in rels))
            nl_descriptions = ", ".join(r["nl_description"] for r in rels)
            relationship_text = f"{component.name} with {', '.join(child_classes)}. {nl_descriptions}"
        else:
            relationship_text = f"{component.name} {component.component_type}"

        # Generate embeddings
        comp_emb = list(colbert_embedder.embed([component_text]))[0]
        comp_vec = comp_emb.tolist() if hasattr(comp_emb, "tolist") else [list(v) for v in comp_emb]

        inputs_emb = list(colbert_embedder.embed([inputs_text]))[0]
        inputs_vec = inputs_emb.tolist() if hasattr(inputs_emb, "tolist") else [list(v) for v in inputs_emb]

        rel_emb = list(relationships_embedder.embed([relationship_text]))[0]
        rel_vec = rel_emb.tolist() if hasattr(rel_emb, "tolist") else list(rel_emb)

        # Generate deterministic ID
        id_string = f"{V7_COLLECTION_NAME}:{path}"
        hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
        point_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

        # Build payload
        payload = component.to_dict()
        payload["indexed_at"] = "v7_restructured"
        payload["inputs_text"] = inputs_text  # Store for debugging
        if rels:
            payload["relationships"] = {
                "children": rels,
                "child_classes": child_classes,
                "max_depth": max(r["depth"] for r in rels),
                "nl_descriptions": nl_descriptions,
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
            client.upsert(collection_name=V7_COLLECTION_NAME, points=points)
            print(f"  Indexed {i + 1} components...")
            points = []

    # Final batch
    if points:
        client.upsert(collection_name=V7_COLLECTION_NAME, points=points)

    # Verify
    info = client.get_collection(V7_COLLECTION_NAME)
    print(f"\n✅ Indexed {info.points_count} points into {V7_COLLECTION_NAME}")

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


def index_instance_patterns_v7(colbert_embedder=None, relationships_embedder=None):
    """
    Index instance_patterns from v6 into v7.

    Uses the same three-vector structure as components:
    - components: Identity (name, type, description, parent components)
    - inputs: Actual parameter values used (instance_params)
    - relationships: Which components were instantiated together
    """
    from fastembed import TextEmbedding, LateInteractionTextEmbedding
    from config.qdrant_client import get_qdrant_client
    from qdrant_client.models import PointStruct
    import hashlib

    print("\n" + "=" * 60)
    print("INDEXING INSTANCE PATTERNS INTO V7")
    print("=" * 60)

    client = get_qdrant_client()

    # Get instance_patterns from v6
    v6_all = client.scroll(
        collection_name="mcp_gchat_cards_v6",
        limit=5000,
        with_payload=True,
    )[0]

    instance_patterns = [p for p in v6_all if p.payload.get("type") == "instance_pattern"]
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
        card_desc = payload.get("card_description", "")[:300] if payload.get("card_description") else ""
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

        # === RELATIONSHIPS VECTOR: Component connections ===
        if parent_paths:
            component_names = [pp.split(".")[-1] for pp in parent_paths]
            relationship_text = f"instance pattern using {', '.join(component_names[:5])}"
        else:
            relationship_text = f"{name} instance pattern"

        # Generate embeddings
        comp_emb = list(colbert_embedder.embed([component_text]))[0]
        comp_vec = comp_emb.tolist() if hasattr(comp_emb, "tolist") else [list(v) for v in comp_emb]

        inputs_emb = list(colbert_embedder.embed([inputs_text]))[0]
        inputs_vec = inputs_emb.tolist() if hasattr(inputs_emb, "tolist") else [list(v) for v in inputs_emb]

        rel_emb = list(relationships_embedder.embed([relationship_text]))[0]
        rel_vec = rel_emb.tolist() if hasattr(rel_emb, "tolist") else list(rel_emb)

        # Generate deterministic ID (consistent with components)
        id_string = f"{V7_COLLECTION_NAME}:instance_pattern:{p.id}"
        hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
        point_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

        # Update payload
        payload["indexed_at"] = "v7_restructured"
        payload["inputs_text"] = inputs_text

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
            client.upsert(collection_name=V7_COLLECTION_NAME, points=points)
            print(f"  Indexed {i + 1} instance_patterns...")
            points = []

    # Final batch
    if points:
        client.upsert(collection_name=V7_COLLECTION_NAME, points=points)

    # Verify
    info = client.get_collection(V7_COLLECTION_NAME)
    print(f"\n✅ v7 now has {info.points_count} total points")

    return len(instance_patterns)


def test_v7_search():
    """Test searching with all three vectors."""
    from config.qdrant_client import get_qdrant_client
    from fastembed import TextEmbedding, LateInteractionTextEmbedding

    print("\n" + "=" * 60)
    print("TESTING V7 SEARCH (ALL VECTORS)")
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
            collection_name=V7_COLLECTION_NAME, query=vec, using="components", limit=2, with_payload=["name", "component_type"]
        )
        print(f"  '{query}' → {[p.payload.get('name') for p in results.points]}")

    # Test inputs vector (values search)
    print("\n--- INPUTS VECTOR (Values) ---")
    for query in ["default=None", "enum values SPINNER", "function with url parameter"]:
        emb = list(colbert.embed([query]))[0]
        vec = emb.tolist() if hasattr(emb, "tolist") else [list(v) for v in emb]
        results = client.query_points(
            collection_name=V7_COLLECTION_NAME, query=vec, using="inputs", limit=2, with_payload=["name", "inputs_text"]
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
            collection_name=V7_COLLECTION_NAME, query=vec, using="relationships", limit=2, with_payload=["name", "relationships"]
        )
        print(f"  '{query}' →")
        for p in results.points:
            rels = p.payload.get("relationships", {})
            children = rels.get("child_classes", [])
            print(f"    {p.payload.get('name')} (children: {children})")


def main():
    print("=" * 60)
    print("V7 COLLECTION INITIALIZATION")
    print("=" * 60)

    # Step 1: Create collection with HNSW configs
    print("\nStep 1: Creating collection...")
    if not create_v7_collection(force_recreate=True):
        return

    # Step 2: Index module components
    print("\nStep 2: Indexing module components...")
    component_count = index_components_v7()

    # Step 3: Index instance patterns (from v6)
    print("\nStep 3: Indexing instance patterns...")
    pattern_count = index_instance_patterns_v7()

    if component_count > 0 or pattern_count > 0:
        # Step 4: Test search
        print("\nStep 4: Testing search...")
        test_v7_search()

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
