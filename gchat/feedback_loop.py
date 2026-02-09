"""
Feedback Loop for SmartCardBuilder

This module implements a feedback-driven learning system that:
1. Stores successful card patterns as "instance_pattern" points in Qdrant
2. Uses hybrid queries (prefetch + RRF fusion) to find proven patterns
3. Links feedback to existing component classes via parent_path
4. Supports dual feedback: content (values) and form (structure)

Architecture (v7):
- Single collection: mcp_gchat_cards_v7
- Three named vectors per point:
  - components: Component identity (Name + Type + Path + Docstring)
  - inputs: Parameter values (defaults, enums, instance_params)
  - relationships: Graph connections (parent-child, NL descriptions)
- Point types:
  - "class", "function", "variable": Module components
  - "instance_pattern": Successful usage patterns with feedback

Feedback Types:
- content_feedback: Affects `inputs` vector searches (parameter values, defaults)
  Example: "The price format was correct" or "Wrong date format used"
- form_feedback: Affects `relationships` vector searches (card structure, nesting)
  Example: "Good layout with buttons below text" or "Image should be above title"
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config.enhanced_logging import setup_logger
from config.settings import settings

logger = setup_logger()

# Get collection name from settings (configurable via CARD_COLLECTION env var)
COLLECTION_NAME = settings.card_collection
COLBERT_DIM = 128  # ColBERT embedding dimension
RELATIONSHIPS_DIM = 384  # MiniLM embedding dimension for relationships

# Max instance patterns to keep (configurable via MAX_INSTANCE_PATTERNS env var)
# Oldest patterns are deleted when limit is exceeded
MAX_INSTANCE_PATTERNS = int(os.getenv("MAX_INSTANCE_PATTERNS", "500"))

# Feedback types
FEEDBACK_CONTENT = "content"  # Affects inputs vector (values)
FEEDBACK_FORM = "form"  # Affects relationships vector (structure)


class FeedbackLoop:
    """
    Manages the feedback loop for SmartCardBuilder.

    Responsibilities:
    - Initialize inputs vector in collection (one-time)
    - Store instance_pattern points when cards get feedback
    - Query with hybrid prefetch + RRF to boost proven patterns
    """

    def __init__(self):
        self._client = None
        self._embedder = None  # ColBERT for components/inputs
        self._relationship_embedder = None  # MiniLM for relationships
        self._initialized = False
        self._description_vector_ready = False
        self._wrapper = None  # ModuleWrapper for SearchMixin methods
        self._component_cache = None  # Tiered component cache
        self._variation_generator = None  # Variation generator for pattern expansion

    def _get_wrapper(self):
        """
        Get the CardFrameworkWrapper for SearchMixin-based searches.

        Returns:
            ModuleWrapper or None if unavailable
        """
        if self._wrapper is None:
            try:
                from gchat.card_framework_wrapper import get_card_framework_wrapper

                self._wrapper = get_card_framework_wrapper()
                logger.info("FeedbackLoop: Using wrapper for SearchMixin methods")
            except Exception as e:
                logger.debug(f"FeedbackLoop: Wrapper not available: {e}")
        return self._wrapper

    def _get_component_cache(self):
        """
        Get the tiered component cache.

        Uses wrapper's cache if available, otherwise creates standalone cache.

        Returns:
            ComponentCache instance
        """
        if self._component_cache is None:
            wrapper = self._get_wrapper()
            if wrapper and hasattr(wrapper, "_get_component_cache"):
                # Use wrapper's cache (shared)
                self._component_cache = wrapper._get_component_cache()
                logger.debug("FeedbackLoop: Using wrapper's component cache")
            else:
                # Create standalone cache
                try:
                    from adapters.module_wrapper.component_cache import (
                        get_component_cache,
                    )

                    self._component_cache = get_component_cache()
                    logger.debug("FeedbackLoop: Using standalone component cache")
                except Exception as e:
                    logger.debug(f"FeedbackLoop: Component cache not available: {e}")
        return self._component_cache

    def _cache_pattern(
        self,
        pattern: Dict[str, Any],
        key: Optional[str] = None,
    ) -> Optional[str]:
        """
        Cache a pattern for fast retrieval.

        Stores the pattern in the tiered cache (L1 memory → L2 pickle).
        This allows subsequent retrievals to skip Qdrant entirely.

        Args:
            pattern: Pattern dict with component_paths, instance_params, etc.
            key: Optional cache key (defaults to card_id or generated)

        Returns:
            Cache key used, or None if caching failed
        """
        cache = self._get_component_cache()
        if not cache:
            return None

        try:
            # Determine key
            if not key:
                key = pattern.get("card_id") or pattern.get("id")
                if not key:
                    import hashlib

                    desc = pattern.get("card_description", "")
                    key = f"pattern:{hashlib.sha256(desc.encode()).hexdigest()[:12]}"

            # Use wrapper's cache_from_qdrant_pattern if available
            wrapper = self._get_wrapper()
            if wrapper and hasattr(wrapper, "cache_from_qdrant_pattern"):
                wrapper.cache_from_qdrant_pattern(pattern, key)
            else:
                cache.put_from_pattern(pattern, key)

            logger.debug(f"Cached pattern: {key}")
            return key

        except Exception as e:
            logger.warning(f"Failed to cache pattern: {e}")
            return None

    def get_cached_pattern(
        self,
        key: str,
        component_paths: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a cached pattern by key.

        Returns cached pattern with hydrated component_classes for
        instant instantiation without path reconstruction.

        Args:
            key: Cache key (card_id, pattern ID, or description hash)
            component_paths: Optional paths for L3 reconstruction

        Returns:
            Dict with component_classes, instance_params, etc., or None
        """
        cache = self._get_component_cache()
        if not cache:
            return None

        entry = cache.get(key, component_paths)
        if not entry:
            return None

        # Return as dict for compatibility
        return {
            "key": entry.key,
            "component_paths": entry.component_paths,
            "instance_params": entry.instance_params,
            "dsl_notation": entry.dsl_notation,
            "structure_description": entry.structure_description,
            "component_classes": entry.component_classes,
            "_is_hydrated": entry._is_hydrated,
            "_from_cache": True,
        }

    def _get_variation_generator(self):
        """
        Get the variation generator for pattern expansion.

        Prefer using wrapper methods directly (generate_pattern_variations below).
        This is maintained for backwards compatibility.

        Returns:
            VariationGenerator instance
        """
        if self._variation_generator is None:
            try:
                from adapters.module_wrapper.variation_generator import (
                    get_variation_generator,
                )

                self._variation_generator = get_variation_generator()
                logger.debug("FeedbackLoop: Variation generator initialized")
            except Exception as e:
                logger.debug(f"FeedbackLoop: Variation generator not available: {e}")
        return self._variation_generator

    def generate_pattern_variations(
        self,
        pattern: Dict[str, Any],
        num_structure_variations: int = 3,
        num_param_variations: int = 2,
        cache_variations: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate and cache variations of a pattern.

        Uses the DAG structure to create valid structural variations and
        parameter variations. All variations are cached for fast retrieval.

        Prefers using the wrapper's InstancePatternMixin methods directly.

        Args:
            pattern: Source pattern with component_paths and instance_params
            num_structure_variations: Number of structural variations
            num_param_variations: Number of parameter variations per structure
            cache_variations: Whether to cache generated variations

        Returns:
            Dict with family info and variation keys, or None if failed
        """
        # Try wrapper's methods first (generic InstancePatternMixin)
        wrapper = self._get_wrapper()
        if wrapper and hasattr(wrapper, "generate_pattern_variations"):
            try:
                from adapters.module_wrapper.instance_pattern_mixin import (
                    InstancePattern,
                )

                # Convert dict pattern to InstancePattern
                component_paths = pattern.get("component_paths") or pattern.get(
                    "parent_paths", []
                )
                instance_params = pattern.get("instance_params", {})
                description = pattern.get("card_description", "")
                pattern_id = pattern.get("card_id") or pattern.get("id", "")

                instance_pattern = InstancePattern(
                    pattern_id=pattern_id,
                    component_paths=component_paths,
                    instance_params=instance_params,
                    description=description,
                    dsl_notation=pattern.get("dsl_notation"),
                    feedback=pattern.get("feedback") or pattern.get("content_feedback"),
                )

                family = wrapper.generate_pattern_variations(
                    pattern=instance_pattern,
                    num_structure_variations=num_structure_variations,
                    num_param_variations=num_param_variations,
                    cache_variations=cache_variations,
                )

                if family:
                    return {
                        "parent_key": family.parent_id,
                        "num_variations": family.size,
                        "cache_keys": family.cache_keys,
                        "variation_types": [
                            v.variation_type for v in family.variations
                        ],
                    }
            except Exception as e:
                logger.debug(f"Wrapper variation generation failed, falling back: {e}")

        # Fallback to variation_generator module
        generator = self._get_variation_generator()
        if not generator:
            return None

        try:
            family = generator.generate_variations(
                pattern=pattern,
                num_structure_variations=num_structure_variations,
                num_param_variations=num_param_variations,
                cache_variations=cache_variations,
            )

            return {
                "parent_key": family.parent_key,
                "num_variations": family.size,
                "cache_keys": family.cache_keys,
                "variation_types": [v.variation_type for v in family.variations],
            }

        except Exception as e:
            logger.warning(f"Failed to generate variations: {e}")
            return None

    def get_cached_variation(
        self,
        parent_key: str,
        variation_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a cached variation from a family.

        Prefers using the wrapper's InstancePatternMixin methods directly.

        Args:
            parent_key: The parent pattern's cache key
            variation_type: Optional type filter ("structure", "parameter", "original")

        Returns:
            Variation dict with component_classes, or None
        """
        # Try wrapper's methods first (generic InstancePatternMixin)
        wrapper = self._get_wrapper()
        if wrapper and hasattr(wrapper, "get_cached_variation"):
            try:
                result = wrapper.get_cached_variation(parent_key, variation_type)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Wrapper get_cached_variation failed, falling back: {e}")

        # Fallback to variation_generator module
        generator = self._get_variation_generator()
        if not generator:
            return None

        if variation_type:
            variation = generator.get_variation_by_type(parent_key, variation_type)
        else:
            variation = generator.get_random_variation(parent_key)

        if not variation:
            return None

        # Get from cache (will hydrate component classes)
        return self.get_cached_pattern(
            variation.cache_key,
            variation.component_paths,
        )

    def _get_client(self):
        """Get Qdrant client singleton."""
        if self._client is None:
            try:
                from config.qdrant_client import get_qdrant_client

                self._client = get_qdrant_client()
            except Exception as e:
                logger.warning(f"Failed to get Qdrant client: {e}")
        return self._client

    def _get_embedder(self):
        """Get ColBERT embedder singleton."""
        if self._embedder is None:
            try:
                from fastembed import LateInteractionTextEmbedding

                self._embedder = LateInteractionTextEmbedding(
                    model_name="colbert-ir/colbertv2.0"
                )
                logger.info("✅ ColBERT embedder loaded for feedback loop")
            except Exception as e:
                logger.warning(f"Failed to load ColBERT embedder: {e}")
        return self._embedder

    def _get_relationship_embedder(self):
        """Get MiniLM embedder singleton for relationship vectors."""
        if self._relationship_embedder is None:
            try:
                from fastembed import TextEmbedding

                self._relationship_embedder = TextEmbedding(
                    model_name="sentence-transformers/all-MiniLM-L6-v2"
                )
                logger.info("✅ MiniLM embedder loaded for relationships")
            except Exception as e:
                logger.warning(f"Failed to load MiniLM embedder: {e}")
        return self._relationship_embedder

    def _embed_description(
        self, description: str, token_ratio: float = 1.0
    ) -> List[List[float]]:
        """
        Embed a card description using ColBERT.

        ColBERT generates one 128d vector per token. MaxSim scoring computes:
        - For each query token: find max similarity to any doc token
        - Sum these maxes → final score

        Fewer query tokens = less computation on Qdrant side, so we support
        truncating to the first N% of tokens for performance optimization.

        Args:
            description: Card description text to embed
            token_ratio: Fraction of tokens to keep (0.0-1.0, default 1.0 = all tokens).
                         Values < 1.0 truncate to first N% of tokens for faster queries.

        Returns:
            List of token vectors (multi-vector embedding)
        """
        embedder = self._get_embedder()
        if not embedder:
            return []

        try:
            # ColBERT query embedding (multi-vector)
            vectors_raw = list(embedder.query_embed(description))[0]
            vectors = [vec.tolist() for vec in vectors_raw]

            # Truncate to first N% of tokens if token_ratio < 1.0
            if token_ratio < 1.0:
                cutoff = max(1, int(len(vectors) * token_ratio))
                vectors = vectors[:cutoff]

            return vectors
        except Exception as e:
            logger.warning(f"Failed to embed description: {e}")
            return []

    def _embed_relationships(
        self, parent_paths: List[str], structure_description: str = ""
    ) -> List[float]:
        """
        Embed relationship/structure information using MiniLM.

        Creates a compact text representation of the card structure from parent_paths
        and optional structure description, then embeds with MiniLM (384d).

        Uses compact format for better embedding efficiency:
            Verbose: "Card structure with: DecoratedText, ButtonList. Components: DecoratedText contains ButtonList"
            Compact: "Card[DecoratedText, ButtonList] :: description"

        Args:
            parent_paths: List of component paths used (e.g., ["card_framework.v2.widgets.DecoratedText"])
            structure_description: Optional natural language description of structure

        Returns:
            Single 384d vector for relationships
        """
        embedder = self._get_relationship_embedder()
        if not embedder:
            return [0.0] * RELATIONSHIPS_DIM

        try:
            # Build compact structure text
            structure_text = self._build_compact_structure_text(
                parent_paths, structure_description
            )

            # Embed with MiniLM (single vector)
            vectors_raw = list(embedder.embed([structure_text]))[0]
            return vectors_raw.tolist()

        except Exception as e:
            logger.warning(f"Failed to embed relationships: {e}")
            return [0.0] * RELATIONSHIPS_DIM

    def _build_compact_structure_text(
        self, component_paths: List[str], structure_description: str = ""
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

        Returns:
            DSL notation + component names for better embedding matching
        """
        try:
            from gchat.card_framework_wrapper import get_card_framework_wrapper

            wrapper = get_card_framework_wrapper()
            return wrapper.build_dsl_from_paths(component_paths, structure_description)
        except Exception as e:
            logger.warning(f"Failed to use ModuleWrapper for DSL: {e}, using fallback")
            # Fallback to basic format if wrapper unavailable
            if not component_paths:
                return (
                    f"§[] | {structure_description[:100]}"
                    if structure_description
                    else "§[]"
                )
            names = [p.split(".")[-1] if "." in p else p for p in component_paths]
            return f"§[...] | {' '.join(names)}"

    def _get_dsl_symbols(self) -> Dict[str, str]:
        """
        Get DSL symbol mappings from ModuleWrapper.

        Returns:
            Dict mapping component name → DSL symbol
        """
        if not hasattr(self, "_dsl_symbols_cache") or self._dsl_symbols_cache is None:
            try:
                from gchat.card_framework_wrapper import get_card_framework_wrapper

                wrapper = get_card_framework_wrapper()
                validator = wrapper.get_structure_validator()
                # symbols maps name → symbol
                self._dsl_symbols_cache = validator.symbols
                logger.debug(f"Loaded {len(self._dsl_symbols_cache)} DSL symbols")
            except Exception as e:
                logger.warning(f"Could not load DSL symbols: {e}")
                # Fallback to empty dict - will use first char of component name
                self._dsl_symbols_cache = {}

        return self._dsl_symbols_cache

    def _check_collection_exists(self) -> bool:
        """Check if the collection exists in Qdrant."""
        client = self._get_client()
        if not client:
            return False

        try:
            collections = client.get_collections().collections
            return any(c.name == COLLECTION_NAME for c in collections)
        except Exception as e:
            logger.warning(f"Failed to check collections: {e}")
            return False

    def _create_collection_with_vectors(self) -> bool:
        """
        Create the collection with both named vectors (colbert + inputs).

        This enables the collection to store both component embeddings and
        card description embeddings for the feedback loop.
        """
        client = self._get_client()
        if not client:
            return False

        try:
            from qdrant_client.models import (
                Distance,
                MultiVectorComparator,
                MultiVectorConfig,
                PayloadSchemaType,
                VectorParams,
            )

            logger.info(f"📦 Creating collection: {COLLECTION_NAME}")
            logger.info(f"   Named vectors: components, inputs, relationships")
            logger.info(f"   ColBERT ({COLBERT_DIM}d): components, inputs")
            logger.info(f"   MiniLM ({RELATIONSHIPS_DIM}d): relationships")

            # Create collection with v7 named vectors (all three)
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "components": VectorParams(
                        size=COLBERT_DIM,
                        distance=Distance.COSINE,
                        multivector_config=MultiVectorConfig(
                            comparator=MultiVectorComparator.MAX_SIM
                        ),
                    ),
                    "inputs": VectorParams(
                        size=COLBERT_DIM,
                        distance=Distance.COSINE,
                        multivector_config=MultiVectorConfig(
                            comparator=MultiVectorComparator.MAX_SIM
                        ),
                    ),
                    "relationships": VectorParams(
                        size=RELATIONSHIPS_DIM,
                        distance=Distance.COSINE,
                        # Single vector (not multi-vector) for MiniLM
                    ),
                },
            )
            logger.info(f"   ✅ Created collection: {COLLECTION_NAME}")

            # Create payload indexes for efficient filtering
            logger.info(f"📑 Creating payload indexes...")

            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="type",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info(f"   ✅ Created index on 'type' field")

            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="feedback",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info(f"   ✅ Created index on 'feedback' field (legacy)")

            # New dual feedback indexes
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="content_feedback",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info(f"   ✅ Created index on 'content_feedback' field")

            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="form_feedback",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info(f"   ✅ Created index on 'form_feedback' field")

            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="card_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info(f"   ✅ Created index on 'card_id' field")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to create collection: {e}")
            return False

    def _migrate_module_components(
        self, source_collection: str = "card_framework_components_colbert_v2"
    ) -> int:
        """
        Migrate module components from a source collection to the new collection.

        This copies all non-instance_pattern points (classes, functions, etc.)
        and adds placeholder inputs vectors.

        Args:
            source_collection: Name of the source collection with indexed module

        Returns:
            Number of components migrated
        """
        client = self._get_client()
        if not client:
            return 0

        # Check if source collection exists
        try:
            collections = client.get_collections().collections
            if not any(c.name == source_collection for c in collections):
                logger.warning(
                    f"⚠️ Source collection {source_collection} not found, skipping module migration"
                )
                return 0
        except Exception as e:
            logger.warning(f"⚠️ Could not check source collection: {e}")
            return 0

        try:
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                MatchValue,
                PointStruct,
            )

            # Get source collection info
            source_info = client.get_collection(source_collection)
            total_points = source_info.points_count
            logger.info(
                f"📋 Migrating module components from {source_collection} ({total_points} points)"
            )

            # Scroll through source collection and copy non-pattern points
            offset = None
            migrated = 0
            batch_size = 100

            while True:
                results, next_offset = client.scroll(
                    collection_name=source_collection,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                    scroll_filter=Filter(
                        must_not=[
                            FieldCondition(
                                key="type",
                                match=MatchValue(value="instance_pattern"),
                            ),
                            FieldCondition(
                                key="type",
                                match=MatchValue(value="template"),
                            ),
                        ]
                    ),
                )

                if not results:
                    break

                # Convert points for new collection
                new_points = []
                for point in results:
                    # Get existing component vectors
                    component_vectors = point.vector
                    if isinstance(component_vectors, dict):
                        component_vectors = component_vectors.get("components", [])

                    if not component_vectors:
                        continue

                    # Create placeholder for inputs (single zero vector)
                    placeholder_inputs = [[0.0] * COLBERT_DIM]
                    # Create placeholder for relationships (single zero vector)
                    placeholder_relationships = [0.0] * RELATIONSHIPS_DIM

                    new_point = PointStruct(
                        id=point.id,
                        vector={
                            "components": component_vectors,
                            "inputs": placeholder_inputs,
                            "relationships": placeholder_relationships,
                        },
                        payload=point.payload,
                    )
                    new_points.append(new_point)

                # Upsert batch to new collection
                if new_points:
                    client.upsert(
                        collection_name=COLLECTION_NAME,
                        points=new_points,
                    )
                    migrated += len(new_points)
                    logger.info(f"   📦 Migrated {migrated} module components...")

                if next_offset is None:
                    break
                offset = next_offset

            logger.info(f"✅ Module migration complete: {migrated} components")
            return migrated

        except Exception as e:
            logger.error(f"❌ Module migration failed: {e}")
            return 0

    def _warm_start_collection(self) -> int:
        """
        Warm-start the collection with known-good card patterns.

        These patterns provide immediate value by boosting queries that match
        proven card structures from the test suite. Includes both content
        and form feedback.

        Returns:
            Number of patterns successfully stored
        """
        # Known-good patterns extracted from test suite
        warm_start_patterns = [
            # Pattern 1: Simple DecoratedText card
            {
                "card_description": 'First section titled "Details" showing "Test content" with label "Label"',
                "component_paths": [
                    "card_framework.v2.widgets.decorated_text.DecoratedText",
                ],
                "instance_params": {
                    "text": "Test content",
                    "top_label": "Label",
                    "wrap_text": True,
                },
                "content_feedback": "positive",
                "form_feedback": "positive",
                "structure_description": "Simple text display with label",
                "source": "warmstart::decorated_text",
            },
            # Pattern 2: Card with action buttons
            {
                "card_description": 'Card with action buttons showing "Click a button below" with two buttons "Button 1" and "Button 2"',
                "component_paths": [
                    "card_framework.v2.widgets.decorated_text.DecoratedText",
                    "card_framework.v2.widgets.button_list.ButtonList",
                ],
                "instance_params": {
                    "title": "Action Card",
                    "section_header": "Actions",
                    "items": [{"text": "Click a button below", "top_label": "Info"}],
                    "buttons": [
                        {"text": "Button 1", "url": "https://example.com/1"},
                        {"text": "Button 2", "url": "https://example.com/2"},
                    ],
                },
                "content_feedback": "positive",
                "form_feedback": "positive",
                "structure_description": "Text with button list below for actions",
                "source": "warmstart::button_list",
            },
            # Pattern 3: Product card with price
            {
                "card_description": 'Product card showing price "$99.99" with a "Buy Now" button',
                "component_paths": [
                    "card_framework.v2.widgets.decorated_text.DecoratedText",
                    "card_framework.v2.widgets.button_list.ButtonList",
                ],
                "instance_params": {
                    "text": "$99.99",
                    "top_label": "Price",
                    "buttons": [{"text": "Buy Now", "url": "https://example.com/buy"}],
                },
                "content_feedback": "positive",
                "form_feedback": "positive",
                "structure_description": "Price display with purchase button",
                "source": "warmstart::product_card",
            },
            # Pattern 4: Status card with icon
            {
                "card_description": 'Status card showing "Success" with a green checkmark icon',
                "component_paths": [
                    "card_framework.v2.widgets.decorated_text.DecoratedText",
                ],
                "instance_params": {
                    "text": "Success",
                    "top_label": "Status",
                    "start_icon": {"known_icon": "CONFIRMATION_NUMBER_ICON"},
                },
                "content_feedback": "positive",
                "form_feedback": "positive",
                "structure_description": "Status indicator with icon",
                "source": "warmstart::status_card",
            },
        ]

        logger.info(
            f"🌱 Warm-starting collection with {len(warm_start_patterns)} known-good patterns..."
        )

        stored = 0
        for pattern in warm_start_patterns:
            try:
                point_id = self.store_instance_pattern(
                    card_description=pattern["card_description"],
                    component_paths=pattern["component_paths"],
                    instance_params=pattern["instance_params"],
                    content_feedback=pattern["content_feedback"],
                    form_feedback=pattern["form_feedback"],
                    structure_description=pattern.get("structure_description"),
                    user_email="warmstart@system.local",
                    card_id=f"warmstart-{pattern['source'].split('::')[1]}",
                )
                if point_id:
                    stored += 1
                    logger.debug(f"   ✅ Stored: {pattern['source']}")
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to store {pattern['source']}: {e}")

        logger.info(
            f"🌱 Warm-start complete: {stored}/{len(warm_start_patterns)} patterns stored"
        )
        return stored

    def ensure_description_vector_exists(self) -> bool:
        """
        Ensure the collection exists with both named vectors.

        If the collection doesn't exist, it will be created and warm-started
        with known-good patterns. This enables automatic setup on first use.

        Returns:
            True if collection is ready, False otherwise
        """
        if self._description_vector_ready:
            return True

        client = self._get_client()
        if not client:
            return False

        try:
            # Check if collection exists
            if not self._check_collection_exists():
                logger.info(f"📦 Collection {COLLECTION_NAME} not found, creating...")

                # Create the collection with proper vector config
                if not self._create_collection_with_vectors():
                    return False

                # Mark as ready before migrations (so store_instance_pattern works)
                self._description_vector_ready = True

                # Migrate module components from source collection (if available)
                self._migrate_module_components()

                # Warm-start with known-good patterns
                self._warm_start_collection()

                return True

            # Collection exists - verify it has the right vectors
            collection_info = client.get_collection(COLLECTION_NAME)
            vectors_config = collection_info.config.params.vectors

            # Check if all required vectors exist
            if isinstance(vectors_config, dict):
                has_inputs = "inputs" in vectors_config
                has_relationships = "relationships" in vectors_config

                if has_inputs and has_relationships:
                    logger.debug(
                        "✅ inputs and relationships vectors exist in collection"
                    )
                    self._description_vector_ready = True
                    return True
                elif has_inputs:
                    # Legacy v7 without relationships - still usable
                    logger.warning(
                        "⚠️ relationships vector not found, form feedback will be limited"
                    )
                    self._description_vector_ready = True
                    return True

            # Vector not found - collection may need migration
            logger.error(
                f"❌ inputs vector not found in {COLLECTION_NAME}. "
                f"Run: uv run python scripts/migrate_colbert_collection_for_feedback.py"
            )
            return False

        except Exception as e:
            logger.error(f"❌ Failed to verify inputs vector: {e}")
            return False

    def store_instance_pattern(
        self,
        card_description: str,
        component_paths: List[str],
        instance_params: Dict[str, Any],
        feedback: Optional[
            str
        ] = None,  # Legacy: "positive", "negative", or None (pending)
        content_feedback: Optional[str] = None,  # "positive", "negative", or None
        form_feedback: Optional[str] = None,  # "positive", "negative", or None
        user_email: Optional[str] = None,
        card_id: Optional[str] = None,
        structure_description: Optional[
            str
        ] = None,  # Optional NL description of structure
        pattern_type: str = "content",  # "content" (main card) or "feedback_ui" (feedback section)
        generate_variations: bool = False,  # Generate and cache variations
        num_structure_variations: int = 3,  # Number of structural variations
        num_param_variations: int = 2,  # Parameter variations per structure
    ) -> Optional[str]:
        """
        Store a card usage pattern as an instance_pattern point.

        Args:
            card_description: Original card description text
            component_paths: List of component paths used (e.g., ["card_framework.v2.widgets.decorated_text.DecoratedText"])
            instance_params: Parameters used to instantiate components
            feedback: Legacy combined feedback (for backwards compatibility)
            content_feedback: Feedback on values/params ("positive", "negative", or None)
            form_feedback: Feedback on structure/layout ("positive", "negative", or None)
            user_email: User who created the card
            card_id: ID of the card (for linking feedback buttons)
            structure_description: Optional NL description of card structure for better embedding
            pattern_type: Type of pattern - "content" for main card, "feedback_ui" for feedback section

        Returns:
            Point ID if stored successfully, None on error
        """
        # Ensure the vector exists
        if not self.ensure_description_vector_exists():
            logger.warning("Cannot store pattern: inputs vector not ready")
            return None

        client = self._get_client()
        if not client:
            return None

        # Embed the description for inputs vector (content)
        description_vectors = self._embed_description(card_description)
        if not description_vectors:
            logger.warning("Cannot store pattern: failed to embed description")
            return None

        # Get ColBERT vectors for component identity
        # For now, we'll use the description vectors (simplified)
        colbert_vectors = description_vectors

        # Build DSL notation for searchability and embedding
        dsl_relationship_text = self._build_compact_structure_text(
            component_paths, structure_description or ""
        )

        # Embed relationships/structure using MiniLM
        relationship_vector = self._embed_relationships(
            component_paths, structure_description or ""
        )

        # Generate point ID
        point_id = str(uuid.uuid4())

        # Handle backwards compatibility: if legacy feedback is provided, apply to both
        if feedback and not content_feedback and not form_feedback:
            content_feedback = feedback
            form_feedback = feedback

        try:
            from qdrant_client.models import PointStruct

            # Create the point with all three v7 vectors
            point = PointStruct(
                id=point_id,
                vector={
                    "components": colbert_vectors,
                    "inputs": description_vectors,
                    "relationships": relationship_vector,
                },
                payload={
                    "name": f"instance_pattern_{point_id[:8]}",
                    "type": "instance_pattern",
                    "pattern_type": pattern_type,  # "content" or "feedback_ui" for filtering
                    "parent_paths": component_paths,  # Links to existing class points
                    "instance_params": instance_params,
                    "card_description": card_description,
                    # DSL notation for text search (e.g., "§[δ×3, Ƀ[ᵬ×2]] | Section DecoratedText×3...")
                    "relationship_text": dsl_relationship_text,
                    # Dual feedback fields
                    "content_feedback": content_feedback,  # Affects inputs searches
                    "form_feedback": form_feedback,  # Affects relationships searches
                    # Legacy field for backwards compatibility
                    "feedback": feedback or content_feedback,
                    "user_email": user_email,
                    "card_id": card_id,
                    "structure_description": structure_description,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            # Upsert the point
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=[point],
            )

            logger.info(
                f"✅ Stored instance_pattern [{pattern_type}]: {point_id[:8]}... "
                f"(content={content_feedback}, form={form_feedback})"
            )

            # Cache the pattern for fast retrieval
            cache_key = card_id or point_id
            pattern_data = {
                "id": point_id,
                "card_id": card_id,
                "component_paths": component_paths,
                "instance_params": instance_params,
                "card_description": card_description,
                "dsl_notation": dsl_relationship_text,
                "structure_description": structure_description,
                "content_feedback": content_feedback,
                "form_feedback": form_feedback,
            }
            self._cache_pattern(pattern=pattern_data, key=cache_key)

            # Generate variations if requested and pattern has positive feedback
            if generate_variations and (
                content_feedback == "positive" or form_feedback == "positive"
            ):
                variation_result = self.generate_pattern_variations(
                    pattern=pattern_data,
                    num_structure_variations=num_structure_variations,
                    num_param_variations=num_param_variations,
                    cache_variations=True,
                )
                if variation_result:
                    logger.info(
                        f"📦 Generated {variation_result['num_variations']} variations "
                        f"for {cache_key}"
                    )

            # Cleanup old patterns if we exceed the limit
            self._cleanup_old_instance_patterns()

            return point_id

        except Exception as e:
            logger.error(f"❌ Failed to store instance_pattern: {e}")
            return None

    def _cleanup_old_instance_patterns(self) -> int:
        """
        Remove oldest instance_pattern points when count exceeds MAX_INSTANCE_PATTERNS.

        Keeps the most recent patterns (by timestamp), deletes oldest ones.
        Patterns with positive feedback are preserved longer (deleted last).

        Returns:
            Number of patterns deleted
        """
        client = self._get_client()
        if not client:
            return 0

        try:
            from qdrant_client import models

            # Count current instance_patterns
            count_result = client.count(
                collection_name=COLLECTION_NAME,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        )
                    ]
                ),
            )
            current_count = count_result.count

            if current_count <= MAX_INSTANCE_PATTERNS:
                return 0  # Under limit, no cleanup needed

            # Calculate how many to delete
            to_delete = current_count - MAX_INSTANCE_PATTERNS

            logger.info(
                f"🧹 Cleaning up instance_patterns: {current_count} > {MAX_INSTANCE_PATTERNS} limit, "
                f"deleting {to_delete} oldest"
            )

            # Scroll through instance_patterns sorted by timestamp (oldest first)
            # We prioritize keeping patterns with positive feedback
            patterns_to_delete = []

            # First pass: get patterns without positive feedback (delete these first)
            results, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        )
                    ],
                    must_not=[
                        models.FieldCondition(
                            key="content_feedback",
                            match=models.MatchValue(value="positive"),
                        ),
                        models.FieldCondition(
                            key="form_feedback",
                            match=models.MatchValue(value="positive"),
                        ),
                    ],
                ),
                limit=to_delete + 100,  # Get extra in case we need more
                with_payload=["timestamp", "card_id"],
            )

            # Sort by timestamp (oldest first) and take what we need
            sorted_results = sorted(
                results,
                key=lambda p: (
                    p.payload.get("timestamp", "2000-01-01")
                    if p.payload
                    else "2000-01-01"
                ),
            )
            patterns_to_delete = [p.id for p in sorted_results[:to_delete]]

            # If we still need more, get patterns with positive feedback (oldest first)
            if len(patterns_to_delete) < to_delete:
                remaining = to_delete - len(patterns_to_delete)
                results, _ = client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="instance_pattern"),
                            )
                        ],
                        should=[
                            models.FieldCondition(
                                key="content_feedback",
                                match=models.MatchValue(value="positive"),
                            ),
                            models.FieldCondition(
                                key="form_feedback",
                                match=models.MatchValue(value="positive"),
                            ),
                        ],
                    ),
                    limit=remaining + 50,
                    with_payload=["timestamp", "card_id"],
                )
                sorted_results = sorted(
                    results,
                    key=lambda p: (
                        p.payload.get("timestamp", "2000-01-01")
                        if p.payload
                        else "2000-01-01"
                    ),
                )
                patterns_to_delete.extend([p.id for p in sorted_results[:remaining]])

            # Delete the patterns in batches (Qdrant has limits on batch size)
            deleted_count = 0
            batch_size = 100
            if patterns_to_delete:
                for i in range(0, len(patterns_to_delete), batch_size):
                    batch = patterns_to_delete[i : i + batch_size]
                    client.delete(
                        collection_name=COLLECTION_NAME,
                        points_selector=models.PointIdsList(points=batch),
                    )
                    deleted_count += len(batch)
                logger.info(f"🧹 Deleted {deleted_count} old instance_patterns")

            return deleted_count

        except Exception as e:
            logger.error(f"❌ Failed to cleanup instance_patterns: {e}")
            return 0

    def update_feedback(
        self,
        card_id: str,
        feedback: Optional[str] = None,  # Legacy combined feedback
        content_feedback: Optional[str] = None,  # "positive" or "negative" for values
        form_feedback: Optional[str] = None,  # "positive" or "negative" for structure
    ) -> bool:
        """
        Update the feedback for an existing instance_pattern point by card_id.

        Supports both legacy single-feedback and new dual-feedback modes:
        - Legacy: Pass `feedback` to update both content and form
        - Dual: Pass `content_feedback` and/or `form_feedback` separately

        Args:
            card_id: The card_id stored in the pattern's payload
            feedback: Legacy combined feedback ("positive" or "negative")
            content_feedback: Feedback on values/params (affects inputs searches)
            form_feedback: Feedback on structure/layout (affects relationships searches)

        Returns:
            True if updated successfully
        """
        client = self._get_client()
        if not client:
            return False

        # Handle backwards compatibility
        if feedback and not content_feedback and not form_feedback:
            content_feedback = feedback
            form_feedback = feedback

        if not content_feedback and not form_feedback:
            logger.warning("No feedback provided to update")
            return False

        from qdrant_client import models

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                # First, find the point by card_id in payload
                results, _ = client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="card_id",
                                match=models.MatchValue(value=card_id),
                            ),
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="instance_pattern"),
                            ),
                        ]
                    ),
                    limit=1,
                    with_payload=True,
                )

                if not results:
                    logger.warning(f"⚠️ No pattern found with card_id: {card_id[:8]}...")
                    return False

                point = results[0]
                point_id = point.id
                existing_payload = point.payload or {}

                # Build update payload
                update_payload = {
                    "feedback_timestamp": datetime.now().isoformat(),
                }

                # Update content feedback if provided
                if content_feedback:
                    update_payload["content_feedback"] = content_feedback
                    # Update legacy field for backwards compatibility
                    update_payload["feedback"] = content_feedback

                # Update form feedback if provided
                if form_feedback:
                    update_payload["form_feedback"] = form_feedback

                # Apply the update
                client.set_payload(
                    collection_name=COLLECTION_NAME,
                    payload=update_payload,
                    points=[point_id],
                )

                logger.info(
                    f"✅ Updated feedback for card {card_id[:8]}... "
                    f"(content={content_feedback}, form={form_feedback})"
                )

                # Check for promotion if both feedbacks are positive
                both_positive = (
                    content_feedback == "positive"
                    or existing_payload.get("content_feedback") == "positive"
                ) and (
                    form_feedback == "positive"
                    or existing_payload.get("form_feedback") == "positive"
                )
                if both_positive:
                    # Refresh point payload for promotion check
                    results, _ = client.scroll(
                        collection_name=COLLECTION_NAME,
                        scroll_filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="card_id",
                                    match=models.MatchValue(value=card_id),
                                ),
                            ]
                        ),
                        limit=1,
                        with_payload=True,
                    )
                    if results:
                        self._check_and_promote(results[0])

                return True

            except Exception as e:
                is_grpc_unavailable = "UNAVAILABLE" in str(e) or "Connection reset" in str(e)
                if is_grpc_unavailable and attempt < max_attempts - 1:
                    logger.warning(
                        f"⚠️ gRPC connection reset on feedback update, retrying... ({e})"
                    )
                    # Force client reconnect
                    self._client = None
                    client = self._get_client()
                    if not client:
                        logger.error("❌ Failed to reconnect Qdrant client")
                        return False
                    continue
                logger.error(f"❌ Failed to update feedback: {e}")
                return False

    def _check_and_promote(self, point) -> bool:
        """
        Check if a pattern should be promoted based on feedback count.

        Promotion thresholds:
        - 3+ positive feedbacks: Promote to type="template" in Qdrant
        - 10+ positive feedbacks: Promote to YAML file

        Args:
            point: The Qdrant point with payload

        Returns:
            True if promoted
        """
        payload = point.payload
        point_id = point.id

        # Get current positive count (increment it)
        current_count = payload.get("positive_count", 0) + 1

        client = self._get_client()
        if not client:
            return False

        try:
            # Update the count
            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={"positive_count": current_count},
                points=[point_id],
            )

            # Check promotion thresholds
            current_type = payload.get("type", "instance_pattern")

            if current_count >= 10 and current_type == "template":
                # Promote to YAML file
                return self._promote_to_file(point_id, payload, current_count)

            elif current_count >= 3 and current_type == "instance_pattern":
                # Promote to template type in Qdrant
                return self._promote_to_template(point_id, payload, current_count)

            logger.debug(
                f"Pattern {str(point_id)[:8]}... has {current_count} positive feedbacks"
            )

            # Propagate positive feedback to enrich original components
            if payload.get("content_feedback") == "positive":
                self._propagate_positive_feedback_to_components(point)

            return False

        except Exception as e:
            logger.warning(f"Failed to check promotion: {e}")
            return False

    def _propagate_positive_feedback_to_components(self, instance_pattern_point) -> int:
        """
        Enrich original component points with successful input values.

        When an instance_pattern receives positive content_feedback, propagate
        the successful values back to the original component points. This allows
        the system to learn over time - components' `inputs` vectors grow to
        include real-world successful values, not just module defaults.

        Args:
            instance_pattern_point: The instance_pattern point with positive feedback

        Returns:
            Number of components enriched
        """
        payload = instance_pattern_point.payload
        parent_paths = payload.get("parent_paths", [])
        instance_params = payload.get("instance_params", {})
        card_description = payload.get("card_description", "")

        if not parent_paths or not instance_params:
            logger.debug("No parent_paths or instance_params to propagate")
            return 0

        enriched_count = 0
        client = self._get_client()
        if not client:
            return 0

        for path in parent_paths:
            # Extract component name from path
            component_name = path.split(".")[-1] if "." in path else path

            # Find the original component point
            component_point = self._find_component_by_path(path)
            if not component_point:
                logger.debug(f"Could not find component point for {path}")
                continue

            # Get the params used for this component
            # instance_params might be keyed by component name or full path
            component_params = instance_params.get(component_name, {})
            if not component_params:
                component_params = instance_params.get(path, {})
            if not component_params:
                # Try to find params that look like they belong to this component
                for key, val in instance_params.items():
                    if component_name.lower() in key.lower():
                        component_params = val if isinstance(val, dict) else {key: val}
                        break

            if not component_params:
                continue

            # Update the component's inputs vector and metadata
            success = self._update_component_with_example(
                component_point,
                component_params,
                card_description,
            )
            if success:
                enriched_count += 1

        if enriched_count > 0:
            logger.info(
                f"✅ Propagated positive feedback to {enriched_count} component(s)"
            )

        return enriched_count

    def _find_component_by_path(self, path: str):
        """
        Find a component point by its full path.

        Args:
            path: Full component path (e.g., "card_framework.v2.widgets.DecoratedText")

        Returns:
            Qdrant point or None
        """
        client = self._get_client()
        if not client:
            return None

        try:
            from qdrant_client import models

            # Search by full_path in payload
            results, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="full_path",
                            match=models.MatchValue(value=path),
                        ),
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="class"),
                        ),
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=True,
            )

            if results:
                return results[0]

            # Fallback: try searching by name
            component_name = path.split(".")[-1] if "." in path else path
            results, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="name",
                            match=models.MatchValue(value=component_name),
                        ),
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="class"),
                        ),
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=True,
            )

            return results[0] if results else None

        except Exception as e:
            logger.debug(f"Error finding component {path}: {e}")
            return None

    def _update_component_with_example(
        self,
        component_point,
        example_params: Dict[str, Any],
        description: str,
    ) -> bool:
        """
        Update a component point with example parameters from positive feedback.

        This method:
        1. Adds example_params to the component's metadata
        2. Updates the component's `inputs` vector to include the new values

        Args:
            component_point: The original component's Qdrant point
            example_params: Parameters that were used successfully
            description: The card description (for context)

        Returns:
            True if updated successfully
        """
        client = self._get_client()
        if not client:
            return False

        point_id = component_point.id
        payload = component_point.payload or {}
        component_name = payload.get("name", "unknown")

        try:
            # 1. Update metadata with example_params
            existing_examples = payload.get("example_params", [])
            if not isinstance(existing_examples, list):
                existing_examples = []

            # Add new example (avoid duplicates by checking param keys)
            example_entry = {
                "params": example_params,
                "description": description[:100],
                "timestamp": datetime.now().isoformat(),
            }

            # Check for duplicate (same param keys and values)
            is_duplicate = any(
                ex.get("params") == example_params for ex in existing_examples
            )

            if not is_duplicate:
                existing_examples.append(example_entry)
                # Keep only last 10 examples to avoid unbounded growth
                existing_examples = existing_examples[-10:]

                # 2. Update the inputs vector with new values
                # Build text from example params for embedding
                params_text = self._format_params_for_embedding(example_params)
                if params_text:
                    new_inputs_vector = self._embed_description(params_text)

                    if new_inputs_vector:
                        # Get existing inputs vector
                        existing_vectors = component_point.vector or {}
                        existing_inputs = existing_vectors.get("inputs", [])

                        # Merge vectors: average the embeddings
                        # This gradually shifts the vector toward successful values
                        merged_inputs = self._merge_input_vectors(
                            existing_inputs, new_inputs_vector
                        )

                        # Update both payload and vector
                        from qdrant_client.models import PointVectors

                        client.set_payload(
                            collection_name=COLLECTION_NAME,
                            payload={
                                "example_params": existing_examples,
                                "last_enriched": datetime.now().isoformat(),
                                "enrichment_count": payload.get("enrichment_count", 0)
                                + 1,
                            },
                            points=[point_id],
                        )

                        # Update the inputs vector
                        client.update_vectors(
                            collection_name=COLLECTION_NAME,
                            points=[
                                PointVectors(
                                    id=point_id,
                                    vector={"inputs": merged_inputs},
                                )
                            ],
                        )

                        logger.debug(
                            f"✅ Enriched {component_name} with example params "
                            f"(total examples: {len(existing_examples)})"
                        )
                        return True

            return False

        except Exception as e:
            logger.warning(f"Failed to update component {component_name}: {e}")
            return False

    def _format_params_for_embedding(self, params: Dict[str, Any]) -> str:
        """
        Format parameters as text for ColBERT embedding.

        Args:
            params: Dictionary of parameter names to values

        Returns:
            Text representation suitable for embedding
        """
        parts = []
        for key, value in params.items():
            if value is not None:
                # Handle different value types
                if isinstance(value, str):
                    parts.append(f"{key}={value}")
                elif isinstance(value, (int, float, bool)):
                    parts.append(f"{key}={value}")
                elif isinstance(value, dict):
                    # Nested dict - flatten key parts
                    for k, v in value.items():
                        if v is not None:
                            parts.append(f"{key}.{k}={v}")
                elif isinstance(value, list):
                    parts.append(f"{key}=[{len(value)} items]")

        return ", ".join(parts) if parts else ""

    def _merge_input_vectors(
        self,
        existing: List[float],
        new: List[float],
        learning_rate: float = 0.3,
    ) -> List[float]:
        """
        Merge existing inputs vector with new example vector.

        Uses exponential moving average to gradually incorporate new values
        while preserving learned patterns from previous examples.

        Args:
            existing: Current inputs vector
            new: New vector from positive feedback
            learning_rate: How much weight to give new vector (0.0-1.0)
                          Higher = faster learning, more volatile
                          Lower = slower learning, more stable

        Returns:
            Merged vector
        """
        if not existing or len(existing) == 0:
            return new

        if not new or len(new) == 0:
            return existing

        # Handle ColBERT multi-vector format (list of lists)
        if isinstance(existing[0], list) and isinstance(new[0], list):
            # Multi-vector: merge each sub-vector
            merged = []
            for i in range(min(len(existing), len(new))):
                merged_sub = [
                    (1 - learning_rate) * e + learning_rate * n
                    for e, n in zip(existing[i], new[i])
                ]
                merged.append(merged_sub)
            return merged
        else:
            # Single vector: simple weighted average
            return [
                (1 - learning_rate) * e + learning_rate * n
                for e, n in zip(existing, new)
            ]

    def _promote_to_template(
        self, point_id: str, payload: Dict[str, Any], count: int
    ) -> bool:
        """
        Promote an instance_pattern to a template in Qdrant.

        This changes the type from "instance_pattern" to "template" and
        structures the data for use by TemplateComponent.

        Args:
            point_id: Qdrant point ID
            payload: Current payload
            count: Current positive feedback count

        Returns:
            True if promoted successfully
        """
        client = self._get_client()
        if not client:
            return False

        try:
            # Generate template name from description
            description = payload.get("card_description", "")[:50]
            safe_name = "".join(
                c if c.isalnum() or c == " " else "_" for c in description
            )
            safe_name = "_".join(safe_name.split())[:30]
            template_name = f"approved_{safe_name}_{str(point_id)[:8]}"

            # Build components list from parent_paths and instance_params
            components = []
            parent_paths = payload.get("parent_paths", [])
            instance_params = payload.get("instance_params", {})

            # Map instance_params to component definitions
            # This is a simplified mapping - could be more sophisticated
            for path in parent_paths:
                comp_def = {"path": path, "params": {}}

                # Try to infer which params belong to this component
                if "DecoratedText" in path:
                    comp_def["params"] = {
                        k: v
                        for k, v in instance_params.items()
                        if k in ["text", "top_label", "bottom_label", "wrap_text"]
                    }
                elif "ButtonList" in path:
                    if "buttons" in instance_params:
                        comp_def["params"] = {"buttons": instance_params["buttons"]}
                elif "Image" in path:
                    if "image_url" in instance_params:
                        comp_def["params"] = {"image_url": instance_params["image_url"]}

                if comp_def["params"]:
                    components.append(comp_def)

            # Update payload to template format
            template_payload = {
                "type": "template",
                "name": template_name,
                "full_path": f"card_framework.templates.{template_name}",
                "components": components,
                "defaults": instance_params,
                "layout": {"type": "standard"},
                "source_description": payload.get("card_description"),
                "source_card_id": payload.get("card_id"),
                "positive_count": count,
                "promoted_at": datetime.now().isoformat(),
            }

            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload=template_payload,
                points=[point_id],
            )

            logger.info(f"🎉 Promoted to template: {template_name} (count={count})")
            return True

        except Exception as e:
            logger.error(f"Failed to promote to template: {e}")
            return False

    def _promote_to_file(
        self, point_id: str, payload: Dict[str, Any], count: int
    ) -> bool:
        """
        Promote a template to a YAML file.

        This creates a permanent template file that ModuleWrapper can load,
        providing faster access and offline availability.

        Args:
            point_id: Qdrant point ID
            payload: Current payload (should be type="template")
            count: Current positive feedback count

        Returns:
            True if promoted successfully
        """
        try:
            from gchat.template_component import get_template_registry

            registry = get_template_registry()

            # Build template data for YAML
            template_data = {
                "name": payload.get("name"),
                "components": payload.get("components", []),
                "defaults": payload.get("defaults", {}),
                "layout": payload.get("layout", {"type": "standard"}),
                "metadata": {
                    "source_description": payload.get("source_description"),
                    "source_card_id": payload.get("source_card_id"),
                    "positive_count": count,
                    "promoted_to_file_at": datetime.now().isoformat(),
                    "qdrant_point_id": str(point_id),
                },
            }

            # Save to file
            filepath = registry.save_template_to_file(
                payload.get("name"), template_data
            )

            # Update Qdrant to mark as file-promoted
            client = self._get_client()
            if client:
                client.set_payload(
                    collection_name=COLLECTION_NAME,
                    payload={
                        "promoted_to_file": True,
                        "file_path": filepath,
                        "promoted_to_file_at": datetime.now().isoformat(),
                    },
                    points=[point_id],
                )

            logger.info(f"📁 Promoted to file: {filepath} (count={count})")
            return True

        except Exception as e:
            logger.error(f"Failed to promote to file: {e}")
            return False

    def _query_via_wrapper(
        self,
        description: str,
        component_paths: Optional[List[str]] = None,
        limit: int = 10,
        token_ratio: float = 1.0,
    ) -> Optional[
        Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]
    ]:
        """
        Query using wrapper's SearchMixin methods (preferred when available).

        Uses wrapper.search_v7_hybrid() with feedback filters for cleaner
        code and better consistency with the SearchMixin architecture.

        Returns:
            Tuple of (class_results, content_patterns, form_patterns) or None if unavailable
        """
        wrapper = self._get_wrapper()
        if not wrapper:
            return None

        try:
            # Use wrapper's search_v7_hybrid with positive feedback filters
            class_results, content_patterns, form_patterns = wrapper.search_v7_hybrid(
                description=description,
                component_paths=component_paths,
                limit=limit,
                token_ratio=token_ratio,
                content_feedback="positive",  # Only get positive content patterns
                form_feedback="positive",  # Only get positive form patterns
                include_classes=True,
            )

            logger.info(
                f"🔍 Wrapper search: {len(class_results)} classes, "
                f"{len(content_patterns)} content (+), {len(form_patterns)} form (+)"
            )

            return class_results, content_patterns, form_patterns

        except Exception as e:
            logger.warning(f"Wrapper search failed, falling back to direct: {e}")
            return None

    def query_with_feedback(
        self,
        component_query: str,
        description: str,
        component_paths: Optional[List[str]] = None,
        limit: int = 10,
        use_negative_feedback: bool = True,
        token_ratio: float = 1.0,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Legacy feedback query — delegates to query_with_discovery().

        Kept for backward compatibility. Prefer query_with_discovery() directly.
        """
        return self.query_with_discovery(
            component_query=component_query,
            description=description,
            component_paths=component_paths,
            limit=limit,
            token_ratio=token_ratio,
        )

    def _query_with_feedback_legacy(
        self,
        component_query: str,
        description: str,
        component_paths: Optional[List[str]] = None,
        limit: int = 10,
        use_negative_feedback: bool = True,
        token_ratio: float = 1.0,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Legacy hybrid query using prefetch + RRF fusion + negative demotion.

        Superseded by query_with_discovery() which uses Qdrant's Discovery API
        for native vector-space feedback constraints instead of binary filters
        and post-hoc score demotion.

        Uses prefetch + RRF fusion to:
        1. Find component classes by path (normal ColBERT search on 'components')
        2. Find successful patterns by description (positive content_feedback on 'inputs')
        3. Find successful patterns by structure (positive form_feedback on 'relationships')
        4. Fuse results with RRF, then demote components associated with negatives

        Note: Prefers wrapper.search_v7_hybrid() when available for better consistency
        with SearchMixin architecture. Falls back to direct Qdrant queries.

        Args:
            component_query: Query for component search (e.g., "v2.widgets.decorated_text.DecoratedText class")
            description: Card description for content pattern matching
            component_paths: Optional list of component paths for structure pattern matching
            limit: Max results
            use_negative_feedback: Whether to incorporate negative patterns (default True)
            token_ratio: Fraction of ColBERT tokens to use (0.0-1.0, default 1.0 = all tokens).
                         Lower values reduce Qdrant computation for faster queries.

        Returns:
            Tuple of (class_results, content_pattern_results, form_pattern_results)
        """
        # Try wrapper-based search first (cleaner, uses SearchMixin)
        # Skip if negative feedback is needed (wrapper doesn't handle demotion yet)
        if not use_negative_feedback:
            wrapper_result = self._query_via_wrapper(
                description=description,
                component_paths=component_paths,
                limit=limit,
                token_ratio=token_ratio,
            )
            if wrapper_result:
                return wrapper_result

        # Fall back to direct Qdrant queries (supports negative demotion)
        client = self._get_client()
        embedder = self._get_embedder()

        if not client or not embedder:
            return [], [], []

        try:
            from qdrant_client import models

            # Embed component query (also apply token truncation)
            component_vectors = self._embed_description(component_query, token_ratio)

            # Embed description for content (inputs) search (apply same truncation)
            description_vectors = self._embed_description(description, token_ratio)

            if not description_vectors:
                # Fallback to simple component search
                return self._simple_component_search(component_vectors, limit), [], []

            # Build prefetch list
            prefetch_list = [
                # Prefetch 1: Component classes by path (v7 components vector)
                models.Prefetch(
                    query=component_vectors,
                    using="components",
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="class"),
                            )
                        ]
                    ),
                    limit=limit * 2,
                ),
                # Prefetch 2: Successful patterns by content (positive content_feedback)
                models.Prefetch(
                    query=description_vectors,
                    using="inputs",
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="instance_pattern"),
                            ),
                            models.FieldCondition(
                                key="content_feedback",
                                match=models.MatchValue(value="positive"),
                            ),
                        ]
                    ),
                    limit=limit,
                ),
            ]

            # Prefetch 3: Patterns by form/structure (positive form_feedback)
            # Only add if we have component paths to build relationship embedding
            relationship_vector = None
            if component_paths:
                relationship_vector = self._embed_relationships(component_paths)
            else:
                # Try to infer structure from description
                relationship_vector = self._embed_relationships([], description)

            if relationship_vector and relationship_vector != [0.0] * RELATIONSHIPS_DIM:
                prefetch_list.append(
                    models.Prefetch(
                        query=relationship_vector,
                        using="relationships",
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="type",
                                    match=models.MatchValue(value="instance_pattern"),
                                ),
                                models.FieldCondition(
                                    key="form_feedback",
                                    match=models.MatchValue(value="positive"),
                                ),
                            ]
                        ),
                        limit=limit,
                    )
                )

            # Hybrid query with prefetch + RRF using proper Qdrant models
            results = client.query_points(
                collection_name=COLLECTION_NAME,
                prefetch=prefetch_list,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit * 3,  # Fetch more to allow for separation and demotion
                with_payload=True,
            )

            # Separate results by type and feedback source
            class_results = []
            content_pattern_results = []
            form_pattern_results = []

            for point in results.points:
                result = {
                    "id": point.id,
                    "score": point.score,
                    **point.payload,
                }

                if point.payload.get("type") == "instance_pattern":
                    # Categorize by which feedback is positive
                    content_fb = point.payload.get("content_feedback")
                    form_fb = point.payload.get("form_feedback")

                    if content_fb == "positive":
                        content_pattern_results.append(result)
                    if form_fb == "positive":
                        form_pattern_results.append(result)
                    # If neither is explicitly positive, add to content by default
                    if content_fb != "positive" and form_fb != "positive":
                        # Check legacy feedback field
                        if point.payload.get("feedback") == "positive":
                            content_pattern_results.append(result)
                else:
                    class_results.append(result)

            # Apply negative feedback demotion if enabled (for both content and form)
            if use_negative_feedback:
                class_results, negative_content_count = self._apply_negative_demotion(
                    class_results, description_vectors, limit, feedback_type="content"
                )
                # Also apply form-based demotion if we have relationship vector
                negative_form_count = 0
                if (
                    relationship_vector
                    and relationship_vector != [0.0] * RELATIONSHIPS_DIM
                ):
                    class_results, negative_form_count = (
                        self._apply_negative_demotion_form(
                            class_results, relationship_vector, limit
                        )
                    )

                logger.info(
                    f"🔍 Hybrid query: {len(class_results)} classes, "
                    f"{len(content_pattern_results)} content patterns (+), "
                    f"{len(form_pattern_results)} form patterns (+), "
                    f"{negative_content_count} content negatives, "
                    f"{negative_form_count} form negatives applied"
                )
            else:
                class_results = class_results[:limit]
                logger.info(
                    f"🔍 Hybrid query: {len(class_results)} classes, "
                    f"{len(content_pattern_results)} content patterns, "
                    f"{len(form_pattern_results)} form patterns"
                )

            return class_results, content_pattern_results, form_pattern_results

        except Exception as e:
            logger.error(f"❌ Hybrid query failed: {e}")
            # Fallback to simple search
            return (
                self._simple_component_search(
                    self._embed_description(component_query) or [], limit
                ),
                [],
                [],
            )

    def query_with_discovery(
        self,
        component_query: str,
        description: str,
        component_paths: Optional[List[str]] = None,
        limit: int = 10,
        token_ratio: float = 1.0,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Query using Qdrant's Discovery API for feedback-aware vector search.

        Discovery API constrains the search space using positive/negative feedback
        point IDs as ContextPairs, while targeting a specific embedding. This replaces
        the prefetch+filter+demotion pipeline with native vector-space constraints:

        - Points are scored by: (1) how many positive zones they're in, then
          (2) similarity to target embedding
        - No post-hoc score multiplication needed

        Runs two Discovery queries:
        1. Content Discovery: target=description embedding on 'inputs' vector,
           context=content_feedback point IDs
        2. Form Discovery: target=relationship embedding on 'relationships' vector,
           context=form_feedback point IDs

        Component class search remains a standard vector query (no feedback dimension).

        Falls back to standard vector search when no feedback point IDs exist.

        Args:
            component_query: Query for component search (e.g., component description)
            description: Card description for content pattern matching
            component_paths: Optional component paths for structure pattern matching
            limit: Max results per query
            token_ratio: Fraction of ColBERT tokens to use (0.0-1.0)

        Returns:
            Tuple of (class_results, content_pattern_results, form_pattern_results)
        """
        client = self._get_client()
        embedder = self._get_embedder()

        if not client or not embedder:
            return [], [], []

        try:
            from qdrant_client import models

            # --- Component class search (unchanged, no feedback dimension) ---
            component_vectors = self._embed_description(component_query, token_ratio)
            class_results = self._simple_component_search(component_vectors, limit)

            # --- Embed targets ---
            description_vectors = self._embed_description(description, token_ratio)
            if not description_vectors:
                return class_results, [], []

            relationship_vector = None
            if component_paths:
                relationship_vector = self._embed_relationships(component_paths)
            else:
                relationship_vector = self._embed_relationships([], description)

            instance_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="instance_pattern"),
                    )
                ]
            )
            search_params = models.SearchParams(hnsw_ef=128)

            # --- Content Discovery (inputs vector) ---
            content_pos_ids, content_neg_ids = self._find_feedback_pattern_ids(
                description, feedback_type="content"
            )
            content_results = []

            if content_pos_ids or content_neg_ids:
                context_pairs = self._build_context_pairs(
                    content_pos_ids, content_neg_ids, max_pairs=5
                )
                if context_pairs:
                    content_query = client.query_points(
                        collection_name=COLLECTION_NAME,
                        query=models.DiscoverQuery(
                            discover=models.DiscoverInput(
                                target=description_vectors,
                                context=context_pairs,
                            )
                        ),
                        using="inputs",
                        query_filter=instance_filter,
                        search_params=search_params,
                        limit=limit,
                        with_payload=True,
                    )
                    content_results = [
                        {"id": p.id, "score": p.score, **(p.payload or {})}
                        for p in content_query.points
                    ]

            # Fallback: standard vector search if no feedback or no results
            if not content_results:
                fallback = client.query_points(
                    collection_name=COLLECTION_NAME,
                    query=description_vectors,
                    using="inputs",
                    query_filter=instance_filter,
                    limit=limit,
                    with_payload=True,
                )
                content_results = [
                    {"id": p.id, "score": p.score, **(p.payload or {})}
                    for p in fallback.points
                ]

            # --- Form Discovery (relationships vector) ---
            form_pos_ids, form_neg_ids = self._find_feedback_pattern_ids(
                description, feedback_type="form"
            )
            form_results = []

            if (
                relationship_vector
                and relationship_vector != [0.0] * RELATIONSHIPS_DIM
            ):
                if form_pos_ids or form_neg_ids:
                    context_pairs = self._build_context_pairs(
                        form_pos_ids, form_neg_ids, max_pairs=5
                    )
                    if context_pairs:
                        form_query = client.query_points(
                            collection_name=COLLECTION_NAME,
                            query=models.DiscoverQuery(
                                discover=models.DiscoverInput(
                                    target=relationship_vector,
                                    context=context_pairs,
                                )
                            ),
                            using="relationships",
                            query_filter=instance_filter,
                            search_params=search_params,
                            limit=limit,
                            with_payload=True,
                        )
                        form_results = [
                            {"id": p.id, "score": p.score, **(p.payload or {})}
                            for p in form_query.points
                        ]

                # Fallback: standard vector search if no feedback or no results
                if not form_results:
                    fallback = client.query_points(
                        collection_name=COLLECTION_NAME,
                        query=relationship_vector,
                        using="relationships",
                        query_filter=instance_filter,
                        limit=limit,
                        with_payload=True,
                    )
                    form_results = [
                        {"id": p.id, "score": p.score, **(p.payload or {})}
                        for p in fallback.points
                    ]

            logger.info(
                f"🔍 Discovery query: {len(class_results)} classes, "
                f"{len(content_results)} content patterns, "
                f"{len(form_results)} form patterns "
                f"(content ctx: +{len(content_pos_ids)}/-{len(content_neg_ids)}, "
                f"form ctx: +{len(form_pos_ids)}/-{len(form_neg_ids)})"
            )

            return class_results, content_results, form_results

        except Exception as e:
            logger.error(f"❌ Discovery query failed: {e}")
            return (
                self._simple_component_search(
                    self._embed_description(component_query) or [], limit
                ),
                [],
                [],
            )

    @staticmethod
    def _build_context_pairs(
        positive_ids: List[str],
        negative_ids: List[str],
        max_pairs: int = 5,
    ) -> List:
        """
        Build ContextPair list from positive/negative point IDs.

        Each positive ID paired with each negative ID creates len(pos) x len(neg)
        pairs. To keep latency reasonable, we cap at max_pairs by taking the first
        N positive and negative IDs that produce at most max_pairs combinations.

        If only positives or only negatives exist, Discovery API requires at least
        one pair, so we return an empty list (caller should fall back to standard search).

        Returns:
            List of ContextPair objects, or empty list if pairs can't be formed.
        """
        if not positive_ids or not negative_ids:
            return []

        # Cap IDs so that pos_count * neg_count <= max_pairs
        # Use sqrt distribution: take ~sqrt(max_pairs) from each side
        import math

        from qdrant_client import models
        per_side = max(1, int(math.sqrt(max_pairs)))
        pos_subset = positive_ids[:per_side]
        neg_subset = negative_ids[:per_side]

        pairs = []
        for pos_id in pos_subset:
            for neg_id in neg_subset:
                pairs.append(
                    models.ContextPair(positive=pos_id, negative=neg_id)
                )
                if len(pairs) >= max_pairs:
                    return pairs

        return pairs

    def _apply_negative_demotion(
        self,
        class_results: List[Dict[str, Any]],
        description_vectors: List[List[float]],
        limit: int,
        demotion_factor: float = 0.5,
        feedback_type: str = "content",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Demote class results associated with negative content feedback patterns.

        This finds negative patterns similar to the description, extracts their
        parent_paths (component classes used), and demotes those classes in
        the results.

        Args:
            class_results: Initial class results from RRF fusion
            description_vectors: Embedded description vectors
            limit: Final result limit
            demotion_factor: Score multiplier for demoted results (0.5 = 50% penalty)
            feedback_type: "content" to filter by content_feedback field

        Returns:
            Tuple of (demoted_results, negative_pattern_count)
        """
        client = self._get_client()
        if not client or not description_vectors:
            return class_results[:limit], 0

        try:
            from qdrant_client import models

            # Determine feedback field based on type
            feedback_field = (
                "content_feedback" if feedback_type == "content" else "feedback"
            )

            # Find negative patterns similar to this description
            negative_results = client.query_points(
                collection_name=COLLECTION_NAME,
                query=description_vectors,
                using="inputs",
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        ),
                        models.FieldCondition(
                            key=feedback_field,
                            match=models.MatchValue(value="negative"),
                        ),
                    ]
                ),
                limit=10,
                with_payload=True,
                score_threshold=0.3,
            )

            if not negative_results.points:
                return class_results[:limit], 0

            # Extract parent_paths from negative patterns - these are components to avoid
            negative_paths = set()
            for point in negative_results.points:
                parent_paths = point.payload.get("parent_paths", [])
                negative_paths.update(parent_paths)

            if not negative_paths:
                return class_results[:limit], len(negative_results.points)

            logger.debug(
                f"🚫 Found {len(negative_paths)} component paths from "
                f"{len(negative_results.points)} negative content patterns"
            )

            # Demote classes that match negative patterns
            for result in class_results:
                full_path = result.get("full_path", "")
                if any(neg_path in full_path for neg_path in negative_paths):
                    result["score"] *= demotion_factor
                    result["_demoted_by_negative_content"] = True
                    logger.debug(f"📉 Demoted (content): {full_path}")

            # Re-sort by adjusted score and limit
            class_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            return class_results[:limit], len(negative_results.points)

        except Exception as e:
            logger.error(f"Negative content demotion failed: {e}")
            return class_results[:limit], 0

    def _apply_negative_demotion_form(
        self,
        class_results: List[Dict[str, Any]],
        relationship_vector: List[float],
        limit: int,
        demotion_factor: float = 0.5,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Demote class results associated with negative form/structure feedback.

        This finds negative patterns with similar structure (relationships vector),
        extracts their parent_paths, and demotes those classes.

        Args:
            class_results: Class results (potentially already demoted by content)
            relationship_vector: 384d MiniLM embedding of structure
            limit: Final result limit
            demotion_factor: Score multiplier for demoted results (0.5 = 50% penalty)

        Returns:
            Tuple of (demoted_results, negative_pattern_count)
        """
        client = self._get_client()
        if not client or not relationship_vector:
            return class_results[:limit], 0

        try:
            from qdrant_client import models

            # Find negative patterns with similar structure
            negative_results = client.query_points(
                collection_name=COLLECTION_NAME,
                query=relationship_vector,
                using="relationships",
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        ),
                        models.FieldCondition(
                            key="form_feedback",
                            match=models.MatchValue(value="negative"),
                        ),
                    ]
                ),
                limit=10,
                with_payload=True,
                score_threshold=0.3,
            )

            if not negative_results.points:
                return class_results[:limit], 0

            # Extract parent_paths from negative patterns - these structures to avoid
            negative_paths = set()
            for point in negative_results.points:
                parent_paths = point.payload.get("parent_paths", [])
                negative_paths.update(parent_paths)

            if not negative_paths:
                return class_results[:limit], len(negative_results.points)

            logger.debug(
                f"🚫 Found {len(negative_paths)} component paths from "
                f"{len(negative_results.points)} negative form patterns"
            )

            # Demote classes that match negative patterns
            for result in class_results:
                full_path = result.get("full_path", "")
                if any(neg_path in full_path for neg_path in negative_paths):
                    # Apply additional demotion (compounds with content demotion)
                    result["score"] *= demotion_factor
                    result["_demoted_by_negative_form"] = True
                    logger.debug(f"📉 Demoted (form): {full_path}")

            # Re-sort by adjusted score and limit
            class_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            return class_results[:limit], len(negative_results.points)

        except Exception as e:
            logger.error(f"Negative form demotion failed: {e}")
            return class_results[:limit], 0

    def _simple_component_search(
        self, vectors: List[List[float]], limit: int
    ) -> List[Dict[str, Any]]:
        """Fallback: simple ColBERT search for components."""
        client = self._get_client()
        if not client or not vectors:
            return []

        try:
            from qdrant_client import models

            results = client.query_points(
                collection_name=COLLECTION_NAME,
                query=vectors,
                using="components",  # v7 identity vector
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="class"),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
            )

            return [{"id": p.id, "score": p.score, **p.payload} for p in results.points]
        except Exception as e:
            logger.error(f"Simple search failed: {e}")
            return []

    def _find_feedback_pattern_ids(
        self,
        description: str,
        limit: int = 10,
        min_score: float = 0.3,
        feedback_type: str = "content",
    ) -> Tuple[List[str], List[str]]:
        """
        Find positive and negative pattern point IDs to use as examples.

        Uses scroll to get ALL patterns with feedback, then lets the recommend
        API handle similarity ranking. No payload-based filtering for scoring -
        we just need to identify which points have positive vs negative feedback.

        Args:
            description: Card description (unused - keeping for API compatibility)
            limit: Max patterns per feedback type to use as examples
            min_score: Unused - keeping for API compatibility
            feedback_type: "content" or "form" - determines which feedback field to use

        Returns:
            Tuple of (positive_ids, negative_ids) - point IDs to use as examples
        """
        client = self._get_client()
        if not client:
            return [], []

        # Determine which feedback field to check
        feedback_field = (
            "content_feedback" if feedback_type == "content" else "form_feedback"
        )

        positive_ids = []
        negative_ids = []

        try:
            from qdrant_client import models

            # Scroll to get positive feedback point IDs
            # This just identifies WHICH points have positive feedback
            # The recommend API will handle the actual similarity ranking
            positive_results, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        ),
                        models.FieldCondition(
                            key=feedback_field,
                            match=models.MatchValue(value="positive"),
                        ),
                    ]
                ),
                limit=limit,
                with_payload=False,  # We only need IDs
            )
            positive_ids = [str(p.id) for p in positive_results]

            # Scroll to get negative feedback point IDs
            negative_results, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        ),
                        models.FieldCondition(
                            key=feedback_field,
                            match=models.MatchValue(value="negative"),
                        ),
                    ]
                ),
                limit=limit,
                with_payload=False,  # We only need IDs
            )
            negative_ids = [str(p.id) for p in negative_results]

            logger.info(
                f"🔍 {feedback_type.title()} feedback examples: "
                f"{len(positive_ids)} positive, {len(negative_ids)} negative"
            )

            return positive_ids, negative_ids

        except Exception as e:
            logger.error(f"Failed to find {feedback_type} feedback pattern IDs: {e}")
            return [], []

    def get_proven_params_for_description(
        self,
        description: str,
        min_score: float = 0.5,
        check_negative: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Find proven instance_params for a similar description.

        This is a convenience method that:
        1. Searches for similar positive patterns
        2. Checks for similar negative patterns (optional)
        3. Only returns params if positive score > negative score
        4. Returns the instance_params from the best match

        Args:
            description: Card description to match
            min_score: Minimum similarity score
            check_negative: If True, check negative patterns and skip if they score higher

        Returns:
            instance_params dict if found, None otherwise
        """
        client = self._get_client()
        if not client:
            return None

        description_vectors = self._embed_description(description)
        if not description_vectors:
            return None

        try:
            from qdrant_client import models

            # Query for positive patterns
            positive_results = client.query_points(
                collection_name=COLLECTION_NAME,
                query=description_vectors,
                using="inputs",
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        ),
                        models.FieldCondition(
                            key="feedback",
                            match=models.MatchValue(value="positive"),
                        ),
                    ]
                ),
                limit=1,
                with_payload=True,
                score_threshold=min_score,
            )

            if not positive_results.points:
                return None

            best_positive = positive_results.points[0]
            positive_score = best_positive.score

            # Check for negative patterns if enabled
            if check_negative:
                negative_results = client.query_points(
                    collection_name=COLLECTION_NAME,
                    query=description_vectors,
                    using="inputs",
                    query_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="instance_pattern"),
                            ),
                            models.FieldCondition(
                                key="feedback",
                                match=models.MatchValue(value="negative"),
                            ),
                        ]
                    ),
                    limit=1,
                    with_payload=True,
                    score_threshold=min_score,
                )

                if negative_results.points:
                    best_negative = negative_results.points[0]
                    negative_score = best_negative.score

                    # If negative pattern is more similar, skip proven params
                    if negative_score >= positive_score:
                        logger.warning(
                            f"⚠️ Negative pattern ({negative_score:.3f}) >= "
                            f"positive ({positive_score:.3f}), skipping proven params"
                        )
                        return None

                    logger.info(
                        f"✅ Positive ({positive_score:.3f}) beats "
                        f"negative ({negative_score:.3f})"
                    )

            logger.info(
                f"✅ Found proven pattern (score={positive_score:.3f}): "
                f"{best_positive.payload.get('card_description', '')[:50]}..."
            )
            return best_positive.payload.get("instance_params")

        except Exception as e:
            logger.error(f"Pattern lookup failed: {e}")
            return None

    def get_feedback_stats(self, description: str = None) -> Dict[str, Any]:
        """
        Get statistics about feedback patterns, optionally filtered by description similarity.

        Returns counts and samples for both content and form feedback types.

        Args:
            description: Optional description to find relevant patterns

        Returns:
            Dict with content_feedback and form_feedback stats
        """
        client = self._get_client()
        if not client:
            return {
                "content": {"positive_count": 0, "negative_count": 0},
                "form": {"positive_count": 0, "negative_count": 0},
                "error": "No client",
            }

        try:
            from qdrant_client import models

            stats = {
                "content": {
                    "positive_count": 0,
                    "negative_count": 0,
                    "positive_samples": [],
                    "negative_samples": [],
                },
                "form": {
                    "positive_count": 0,
                    "negative_count": 0,
                    "positive_samples": [],
                    "negative_samples": [],
                },
                # Legacy totals for backwards compatibility
                "positive_count": 0,
                "negative_count": 0,
            }

            # Count patterns by feedback type for both content and form
            for feedback_category in ["content", "form"]:
                feedback_field = f"{feedback_category}_feedback"
                for feedback_value in ["positive", "negative"]:
                    count_result = client.count(
                        collection_name=COLLECTION_NAME,
                        count_filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="type",
                                    match=models.MatchValue(value="instance_pattern"),
                                ),
                                models.FieldCondition(
                                    key=feedback_field,
                                    match=models.MatchValue(value=feedback_value),
                                ),
                            ]
                        ),
                    )
                    stats[feedback_category][
                        f"{feedback_value}_count"
                    ] = count_result.count

            # Calculate legacy totals (max of content/form for each)
            stats["positive_count"] = max(
                stats["content"]["positive_count"], stats["form"]["positive_count"]
            )
            stats["negative_count"] = max(
                stats["content"]["negative_count"], stats["form"]["negative_count"]
            )

            # If description provided, find similar patterns for both content and form
            if description:
                # Content samples (using inputs vector)
                description_vectors = self._embed_description(description)
                if description_vectors:
                    for feedback_value in ["positive", "negative"]:
                        results = client.query_points(
                            collection_name=COLLECTION_NAME,
                            query=description_vectors,
                            using="inputs",
                            query_filter=models.Filter(
                                must=[
                                    models.FieldCondition(
                                        key="type",
                                        match=models.MatchValue(
                                            value="instance_pattern"
                                        ),
                                    ),
                                    models.FieldCondition(
                                        key="content_feedback",
                                        match=models.MatchValue(value=feedback_value),
                                    ),
                                ]
                            ),
                            limit=3,
                            with_payload=True,
                        )
                        stats["content"][f"{feedback_value}_samples"] = [
                            {
                                "score": p.score,
                                "description": p.payload.get("card_description", "")[
                                    :100
                                ],
                            }
                            for p in results.points
                        ]

                # Form samples (using relationships vector)
                relationship_vector = self._embed_relationships([], description)
                if (
                    relationship_vector
                    and relationship_vector != [0.0] * RELATIONSHIPS_DIM
                ):
                    for feedback_value in ["positive", "negative"]:
                        results = client.query_points(
                            collection_name=COLLECTION_NAME,
                            query=relationship_vector,
                            using="relationships",
                            query_filter=models.Filter(
                                must=[
                                    models.FieldCondition(
                                        key="type",
                                        match=models.MatchValue(
                                            value="instance_pattern"
                                        ),
                                    ),
                                    models.FieldCondition(
                                        key="form_feedback",
                                        match=models.MatchValue(value=feedback_value),
                                    ),
                                ]
                            ),
                            limit=3,
                            with_payload=True,
                        )
                        stats["form"][f"{feedback_value}_samples"] = [
                            {
                                "score": p.score,
                                "description": p.payload.get("card_description", "")[
                                    :100
                                ],
                                "structure": p.payload.get("structure_description", ""),
                            }
                            for p in results.points
                        ]

            logger.info(
                f"📊 Feedback stats: "
                f"content(+{stats['content']['positive_count']}/-{stats['content']['negative_count']}), "
                f"form(+{stats['form']['positive_count']}/-{stats['form']['negative_count']})"
            )
            return stats

        except Exception as e:
            logger.error(f"Failed to get feedback stats: {e}")
            return {
                "content": {"positive_count": 0, "negative_count": 0},
                "form": {"positive_count": 0, "negative_count": 0},
                "error": str(e),
            }


# Singleton instance
_feedback_loop: Optional[FeedbackLoop] = None


def get_feedback_loop() -> FeedbackLoop:
    """Get the singleton FeedbackLoop instance."""
    global _feedback_loop
    if _feedback_loop is None:
        _feedback_loop = FeedbackLoop()
    return _feedback_loop
