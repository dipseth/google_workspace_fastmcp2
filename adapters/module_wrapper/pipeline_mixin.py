"""
TODO:
Make sure pipeline can support a paramter for warming up in intitiating.  this involves gnerating a bunch of random valid copmoment combinations use those (if approved by an outside process) to populate with additional instance_pattern points


Ingestion Pipeline Mixin

Provides the v7 ingestion pipeline for creating/updating Qdrant collections
with component, input, and relationship vectors.

This consolidates the logic from scripts/initialize_v7_collection.py into
the ModuleWrapper class so the pipeline can be run programmatically.
"""

import dataclasses
import hashlib
import inspect
import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from adapters.module_wrapper.ric_provider import IntrospectionProvider, RICTextProvider
from adapters.module_wrapper.types import (
    COLBERT_DIM as _COLBERT_DIM,
)
from adapters.module_wrapper.types import (
    RELATIONSHIPS_DIM as _RELATIONSHIPS_DIM,
)
from adapters.module_wrapper.types import (
    ComponentName,
    ComponentPath,
    EmbeddingVector,
    MultiVector,
    Payload,
    RelationshipList,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Re-export constants for backwards compatibility
COLBERT_DIM = _COLBERT_DIM  # ColBERT multi-vector
RELATIONSHIPS_DIM = _RELATIONSHIPS_DIM  # MiniLM dense vector


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def extract_input_values(component) -> str:
    """
    Extract input values text for the 'inputs' vector.

    For classes: field defaults, enum values, literal annotations
    For functions: parameter defaults
    For variables: the actual value representation
    """
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
        try:
            sig = inspect.signature(obj)
            for name, param in sig.parameters.items():
                if param.default is not inspect.Parameter.empty:
                    default_repr = repr(param.default)[:50]
                    parts.append(f"{name}={default_repr}")
        except (ValueError, TypeError):
            pass

    elif comp_type == "variable":
        if component.source:
            source = component.source[:200]
            parts.append(f"value: {source}")

    if not parts:
        parts.append(f"{component.name} {comp_type}")

    return ", ".join(parts)


def build_compact_relationship_text(
    component_name: ComponentName,
    relationships: RelationshipList,
    component_type: str = "class",
) -> str:
    """
    Build compact, structured relationship text for embedding.

    Converts verbose relationship descriptions into a compact format
    that embeds more efficiently.

    Example:
        Verbose: "DecoratedText with Icon, Button, OnClick"
        Compact: "DecoratedText[icon:Icon?, button:Button?, on_click:OnClick?]"
    """
    if not relationships:
        return f"{component_name}:{component_type}[]"

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
            fields = [f[0] for f in fields_by_child[child]]
            if len(set(fields)) == 1:
                parts.append(f"{fields[0]}:{child}×{count}")
            else:
                parts.append(f"{child}×{count}[{','.join(fields)}]")
            processed_children.add(child)
        else:
            parts.append(f"{field}:{child}{opt_marker}")

    return f"{component_name}[{', '.join(parts)}]"


def format_instance_params(params: dict) -> str:
    """Format instance_params for the inputs vector."""
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


# =============================================================================
# PIPELINE MIXIN
# =============================================================================


class PipelineMixin:
    """
    Mixin providing v7 ingestion pipeline functionality.

    Expects the following attributes on self:
    - module_name: str
    - components: Dict[str, ModuleComponent]
    - symbol_mapping: Dict[str, str]
    - client: Qdrant client
    - collection_name: str
    - extract_relationships_by_parent: method
    - get_structure_validator: method
    - get_symbol_wrapped_text: method
    - get_symbol_for_component: method
    """

    # --- Mixin dependency contract ---
    _MIXIN_PROVIDES = frozenset(
        {
            "run_ingestion_pipeline",
            "create_v7_collection",
            "verify_pipeline_results",
            "register_ric_provider",
            "get_ric_provider",
            "get_v7_collection_name",
            "set_v7_collection_name",
            "_ensure_pipeline_embedders",
        }
    )
    _MIXIN_REQUIRES = frozenset(
        {
            "module_name",
            "components",
            "symbol_mapping",
            "client",
            "collection_name",
            "extract_relationships_by_parent",
            "get_structure_validator",
            "get_symbol_wrapped_text",
            "get_symbol_for_component",
        }
    )
    _MIXIN_INIT_ORDER = 55

    # Pipeline state
    _v7_collection_name: Optional[str] = None
    _colbert_embedder: Any = None
    _relationships_embedder: Any = None

    # RIC provider registry
    _ric_providers: Dict[str, RICTextProvider] = {}
    _default_ric_provider: Optional[RICTextProvider] = None

    def register_ric_provider(self, provider: RICTextProvider) -> None:
        """Register a RIC text provider for a component type.

        Args:
            provider: A RICTextProvider implementation
        """
        self._ric_providers[provider.component_type] = provider
        logger.info(
            f"Registered RIC provider for component_type={provider.component_type!r}"
        )

    def get_ric_provider(self, component_type: str) -> RICTextProvider:
        """Get the RIC text provider for a component type.

        Falls back to the default IntrospectionProvider if no specific
        provider is registered for the given type.

        Args:
            component_type: e.g. "class", "function", "tool_response"

        Returns:
            The matching RICTextProvider
        """
        if component_type in self._ric_providers:
            return self._ric_providers[component_type]
        if self._default_ric_provider is None:
            self._default_ric_provider = IntrospectionProvider()
        return self._default_ric_provider

    def _build_provider_metadata(
        self,
        component,
        relationships_by_parent: Dict[str, list],
        structure_validator=None,
    ) -> Dict[str, Any]:
        """Build the metadata dict that providers consume.

        Constructs a flat dict from a ModuleComponent + pipeline context
        so providers don't need to know about ModuleComponent internals.

        Args:
            component: A ModuleComponent instance
            relationships_by_parent: Pre-computed relationship map
            structure_validator: Optional StructureValidator for enriched text

        Returns:
            Dict with all fields providers may need
        """
        comp_name = component.name
        comp_type = component.component_type
        rels = (
            relationships_by_parent.get(comp_name, []) if comp_type == "class" else []
        )
        symbols = getattr(self, "symbol_mapping", {}) or {}

        return {
            "component": component,
            "component_type": comp_type,
            "full_path": component.full_path,
            "module_path": component.module_path,
            "docstring": component.docstring or "",
            "source": component.source or "",
            "relationships": rels,
            "structure_validator": structure_validator,
            "symbols": getattr(structure_validator, "symbols", {})
            if structure_validator
            else symbols,
        }

    def get_v7_collection_name(self) -> str:
        """Get the v7 collection name for this module."""
        if self._v7_collection_name:
            return self._v7_collection_name

        # Default naming convention
        base = self.module_name.replace(".", "_")
        return f"mcp_{base}_v7"

    def set_v7_collection_name(self, name: str):
        """Set a custom v7 collection name."""
        self._v7_collection_name = name

    def create_v7_collection(
        self,
        collection_name: Optional[str] = None,
        force_recreate: bool = False,
    ) -> bool:
        """
        Create the v7 collection with three named vectors.

        Args:
            collection_name: Collection name (uses default if not provided)
            force_recreate: If True, delete and recreate existing collection

        Returns:
            True if collection exists or was created successfully
        """
        from qdrant_client.models import (
            Distance,
            HnswConfigDiff,
            KeywordIndexParams,
            KeywordIndexType,
            MultiVectorComparator,
            MultiVectorConfig,
            VectorParams,
        )

        if not self.client:
            logger.error("Cannot create collection: Qdrant client not available")
            return False

        target_name = collection_name or self.get_v7_collection_name()
        self._v7_collection_name = target_name

        collections = self.client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if target_name in collection_names:
            info = self.client.get_collection(target_name)
            logger.info(
                f"Collection {target_name} exists with {info.points_count} points"
            )

            if force_recreate:
                logger.warning(f"Force recreate enabled - deleting {target_name}...")
                self.client.delete_collection(target_name)
                collection_names.remove(target_name)
            else:
                return True

        logger.info(f"Creating {target_name} with three named vectors...")

        # Create collection with all three vectors
        self.client.create_collection(
            collection_name=target_name,
            vectors_config={
                "components": VectorParams(
                    size=COLBERT_DIM,
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(
                        comparator=MultiVectorComparator.MAX_SIM
                    ),
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
                ),
                "inputs": VectorParams(
                    size=COLBERT_DIM,
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(
                        comparator=MultiVectorComparator.MAX_SIM
                    ),
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
                ),
                "relationships": VectorParams(
                    size=RELATIONSHIPS_DIM,
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(m=32, ef_construct=200),
                ),
            },
        )

        # Create payload indexes
        logger.info("Creating payload indexes...")
        for field_name in [
            "name",
            "type",
            "module_path",
            "full_path",
            "symbol",
            "symbol_dsl",
        ]:
            self.client.create_payload_index(
                collection_name=target_name,
                field_name=field_name,
                field_schema=KeywordIndexParams(type=KeywordIndexType.KEYWORD),
            )
            logger.info(f"  Created index: {field_name}")

        logger.info(f"Created {target_name}")
        return True

    def _ensure_pipeline_embedders(self):
        """Ensure ColBERT and relationships embedders are initialized."""
        if self._colbert_embedder is None:
            from fastembed import LateInteractionTextEmbedding

            logger.info("Initializing ColBERT embedder for pipeline...")
            self._colbert_embedder = LateInteractionTextEmbedding(
                "colbert-ir/colbertv2.0"
            )

        if self._relationships_embedder is None:
            from fastembed import TextEmbedding

            logger.info("Initializing MiniLM embedder for relationships...")
            self._relationships_embedder = TextEmbedding(
                "sentence-transformers/all-MiniLM-L6-v2"
            )

    def run_ingestion_pipeline(
        self,
        collection_name: Optional[str] = None,
        force_recreate: bool = False,
        include_instance_patterns: bool = True,
        source_collection: Optional[str] = None,
        batch_size: int = 20,
    ) -> Dict[str, int]:
        """
        Run the full v7 ingestion pipeline.

        This is the main entry point for indexing a module into v7 format with
        three vectors: components, inputs, and relationships.

        Args:
            collection_name: Target v7 collection name
            force_recreate: If True, recreate the collection from scratch
            include_instance_patterns: If True, also migrate instance_patterns
            source_collection: Source collection for instance_patterns (if different)
            batch_size: Points to process per batch

        Returns:
            Dict with counts: {"components": N, "instance_patterns": N, "total": N}
        """
        from qdrant_client.models import PointStruct

        logger.info("=" * 60)
        logger.info(f"RUNNING V7 INGESTION PIPELINE FOR {self.module_name}")
        logger.info("=" * 60)

        # Step 1: Create collection
        target_name = collection_name or self.get_v7_collection_name()
        if not self.create_v7_collection(target_name, force_recreate):
            return {
                "components": 0,
                "instance_patterns": 0,
                "total": 0,
                "error": "Failed to create collection",
            }

        # Step 2: Initialize embedders
        self._ensure_pipeline_embedders()

        # Step 3: Get relationships
        logger.info("Extracting relationships...")
        relationships_by_parent = self.extract_relationships_by_parent(max_depth=5)
        logger.info(
            f"Found relationships for {len(relationships_by_parent)} parent classes"
        )

        # Step 4: Get structure validator for symbol-enriched text
        try:
            structure_validator = self.get_structure_validator()
            _ = structure_validator.relationships  # Pre-cache
            logger.info(f"Structure validator ready")
        except Exception as e:
            logger.warning(f"Could not initialize structure validator: {e}")
            structure_validator = None

        # Step 5: Index components
        logger.info(f"Indexing {len(self.components)} components...")
        points = []
        component_count = 0

        for i, (path, component) in enumerate(self.components.items()):
            try:
                # Provider-dispatched text generation
                provider = self.get_ric_provider(component.component_type)
                metadata = self._build_provider_metadata(
                    component, relationships_by_parent, structure_validator
                )

                # Generate raw text via provider
                component_text = provider.component_text(component.name, metadata)
                inputs_text = provider.inputs_text(component.name, metadata)
                relationship_text = provider.relationships_text(
                    component.name, metadata
                )

                # Symbol wrapping for ColBERT vectors (not for MiniLM relationships)
                component_symbol = self.get_symbol_for_component(component.name)
                component_text = self.get_symbol_wrapped_text(
                    component.name, component_text
                )
                inputs_text = self.get_symbol_wrapped_text(component.name, inputs_text)

                rels = metadata["relationships"]
                child_classes = (
                    list(set(r["child_class"] for r in rels)) if rels else []
                )

                # Generate embeddings
                comp_emb = list(self._colbert_embedder.embed([component_text]))[0]
                comp_vec = (
                    comp_emb.tolist()
                    if hasattr(comp_emb, "tolist")
                    else [list(v) for v in comp_emb]
                )

                inputs_emb = list(self._colbert_embedder.embed([inputs_text]))[0]
                inputs_vec = (
                    inputs_emb.tolist()
                    if hasattr(inputs_emb, "tolist")
                    else [list(v) for v in inputs_emb]
                )

                rel_emb = list(self._relationships_embedder.embed([relationship_text]))[
                    0
                ]
                rel_vec = (
                    rel_emb.tolist() if hasattr(rel_emb, "tolist") else list(rel_emb)
                )

                # Generate deterministic ID
                id_string = f"{target_name}:{path}"
                hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
                point_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

                # Build payload
                payload = component.to_dict()
                payload["indexed_at"] = datetime.now(UTC).isoformat()
                payload["inputs_text"] = inputs_text
                payload["relationship_text"] = relationship_text

                if component_symbol:
                    payload["symbol"] = component_symbol
                    payload["symbol_dsl"] = f"{component_symbol}={component.name}"
                    payload["embedding_format"] = "symbol_wrapped"

                if rels:
                    payload["relationships"] = {
                        "children": rels,
                        "child_classes": child_classes,
                        "max_depth": max(r["depth"] for r in rels),
                        "compact_text": relationship_text,
                    }

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
                component_count += 1

                # Batch upsert
                if len(points) >= batch_size:
                    self.client.upsert(collection_name=target_name, points=points)
                    logger.info(f"Indexed {i + 1} components...")
                    points = []

            except Exception as e:
                logger.warning(f"Error indexing component {path}: {e}")

        # Final batch
        if points:
            self.client.upsert(collection_name=target_name, points=points)

        logger.info(f"Indexed {component_count} components")

        # Step 6: Index instance patterns (optional)
        pattern_count = 0
        if include_instance_patterns:
            pattern_count = self._index_instance_patterns_v7(
                target_name,
                source_collection or self.collection_name,
                batch_size,
            )

        # Summary
        info = self.client.get_collection(target_name)
        total = info.points_count

        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info(f"  Components: {component_count}")
        logger.info(f"  Instance patterns: {pattern_count}")
        logger.info(f"  Total points: {total}")
        logger.info("=" * 60)

        return {
            "components": component_count,
            "instance_patterns": pattern_count,
            "total": total,
        }

    def _index_instance_patterns_v7(
        self,
        target_collection: str,
        source_collection: str,
        batch_size: int = 20,
    ) -> int:
        """
        Index instance_patterns from source collection into v7.

        Args:
            target_collection: Target v7 collection
            source_collection: Source collection with instance_patterns
            batch_size: Points to process per batch

        Returns:
            Number of instance_patterns indexed
        """
        from qdrant_client.models import PointStruct

        logger.info(f"Indexing instance_patterns from {source_collection}...")

        try:
            # Get instance_patterns from source
            all_points = self.client.scroll(
                collection_name=source_collection,
                limit=5000,
                with_payload=True,
            )[0]

            instance_patterns = [
                p for p in all_points if p.payload.get("type") == "instance_pattern"
            ]
            logger.info(f"Found {len(instance_patterns)} instance_patterns")

            if not instance_patterns:
                return 0

            points = []
            for i, p in enumerate(instance_patterns):
                try:
                    payload = dict(p.payload)

                    name = payload.get("name", "")
                    card_desc = (
                        payload.get("card_description", "")[:300]
                        if payload.get("card_description")
                        else ""
                    )
                    parent_paths = payload.get("parent_paths", []) or []
                    instance_params = payload.get("instance_params", {}) or {}

                    # Component text
                    component_text = f"Name: {name}\nType: instance_pattern"
                    if card_desc:
                        component_text += f"\nDescription: {card_desc}"
                    if parent_paths:
                        component_names = [pp.split(".")[-1] for pp in parent_paths[:5]]
                        component_text += f"\nComponents: {', '.join(component_names)}"

                    # Inputs text
                    inputs_text = format_instance_params(instance_params)

                    # Relationships text with DSL
                    if parent_paths:
                        relationship_text = self.build_dsl_from_paths(
                            parent_paths, card_desc
                        )
                    else:
                        relationship_text = f"{name} instance pattern"

                    # Generate embeddings
                    comp_emb = list(self._colbert_embedder.embed([component_text]))[0]
                    comp_vec = (
                        comp_emb.tolist()
                        if hasattr(comp_emb, "tolist")
                        else [list(v) for v in comp_emb]
                    )

                    inputs_emb = list(self._colbert_embedder.embed([inputs_text]))[0]
                    inputs_vec = (
                        inputs_emb.tolist()
                        if hasattr(inputs_emb, "tolist")
                        else [list(v) for v in inputs_emb]
                    )

                    rel_emb = list(
                        self._relationships_embedder.embed([relationship_text])
                    )[0]
                    rel_vec = (
                        rel_emb.tolist()
                        if hasattr(rel_emb, "tolist")
                        else list(rel_emb)
                    )

                    # Generate deterministic ID
                    id_string = f"{target_collection}:instance_pattern:{p.id}"
                    hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
                    point_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

                    payload["indexed_at"] = datetime.now(UTC).isoformat()
                    payload["inputs_text"] = inputs_text
                    payload["relationship_text"] = relationship_text

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
                        self.client.upsert(
                            collection_name=target_collection, points=points
                        )
                        logger.info(f"Indexed {i + 1} instance_patterns...")
                        points = []

                except Exception as e:
                    logger.warning(f"Error indexing instance_pattern: {e}")

            # Final batch
            if points:
                self.client.upsert(collection_name=target_collection, points=points)

            return len(instance_patterns)

        except Exception as e:
            logger.error(f"Failed to index instance_patterns: {e}")
            return 0

    def verify_pipeline_results(
        self,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify the v7 collection after pipeline run.

        Args:
            collection_name: Collection to verify

        Returns:
            Dict with verification results
        """
        target_name = collection_name or self.get_v7_collection_name()

        if not self.client:
            return {"error": "No Qdrant client"}

        try:
            info = self.client.get_collection(target_name)

            vectors = info.config.params.vectors
            vector_info = {}
            if isinstance(vectors, dict):
                for name, config in vectors.items():
                    hnsw = getattr(config, "hnsw_config", None)
                    multivec = getattr(config, "multivector_config", None)
                    vector_info[name] = {
                        "size": config.size,
                        "multivector": multivec is not None,
                        "hnsw_m": hnsw.m if hnsw else None,
                    }

            payload_schema = {
                field: str(schema.data_type)
                for field, schema in (info.payload_schema or {}).items()
            }

            return {
                "collection": target_name,
                "points_count": info.points_count,
                "vectors": vector_info,
                "payload_indexes": payload_schema,
                "status": str(info.status),
            }

        except Exception as e:
            return {"error": str(e)}


# Export for convenience
__all__ = [
    "PipelineMixin",
    "extract_input_values",
    "build_compact_relationship_text",
    "format_instance_params",
    "COLBERT_DIM",
    "RELATIONSHIPS_DIM",
    "RICTextProvider",
    "IntrospectionProvider",
]
