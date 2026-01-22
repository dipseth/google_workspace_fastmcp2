"""
Feedback Loop for SmartCardBuilder

This module implements a feedback-driven learning system that:
1. Stores successful card patterns as "instance_pattern" points in Qdrant
2. Uses hybrid queries (prefetch + RRF fusion) to find proven patterns
3. Links feedback to existing component classes via parent_path

Architecture:
- Single collection: card_framework_components_colbert
- Two named vectors per point:
  - colbert: Component path embedding (existing)
  - description_colbert: Card description embedding (new, for instance_patterns)
- Point types:
  - "class", "function", "variable": Original module elements
  - "instance_pattern": NEW - successful usage patterns with feedback
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


class FeedbackLoop:
    """
    Manages the feedback loop for SmartCardBuilder.

    Responsibilities:
    - Initialize description_colbert vector in collection (one-time)
    - Store instance_pattern points when cards get feedback
    - Query with hybrid prefetch + RRF to boost proven patterns
    """

    def __init__(self):
        self._client = None
        self._embedder = None
        self._initialized = False
        self._description_vector_ready = False

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

    def _embed_description(self, description: str) -> List[List[float]]:
        """
        Embed a card description using ColBERT.

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
            return vectors
        except Exception as e:
            logger.warning(f"Failed to embed description: {e}")
            return []

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
        Create the collection with both named vectors (colbert + description_colbert).

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
            logger.info(f"   Named vectors: colbert, description_colbert")
            logger.info(
                f"   Dimension: {COLBERT_DIM}, Distance: COSINE, Comparator: MAX_SIM"
            )

            # Create collection with both named vectors
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "colbert": VectorParams(
                        size=COLBERT_DIM,
                        distance=Distance.COSINE,
                        multivector_config=MultiVectorConfig(
                            comparator=MultiVectorComparator.MAX_SIM
                        ),
                    ),
                    "description_colbert": VectorParams(
                        size=COLBERT_DIM,
                        distance=Distance.COSINE,
                        multivector_config=MultiVectorConfig(
                            comparator=MultiVectorComparator.MAX_SIM
                        ),
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
            logger.info(f"   ✅ Created index on 'feedback' field")

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
        and adds placeholder description_colbert vectors.

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
                    # Get existing colbert vectors
                    colbert_vectors = point.vector
                    if isinstance(colbert_vectors, dict):
                        colbert_vectors = colbert_vectors.get("colbert", [])

                    if not colbert_vectors:
                        continue

                    # Create placeholder for description_colbert (single zero vector)
                    placeholder_vector = [[0.0] * COLBERT_DIM]

                    new_point = PointStruct(
                        id=point.id,
                        vector={
                            "colbert": colbert_vectors,
                            "description_colbert": placeholder_vector,
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
        proven card structures from the test suite.

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
                "feedback": "positive",
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
                "feedback": "positive",
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
                "feedback": "positive",
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
                "feedback": "positive",
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
                    feedback=pattern["feedback"],
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

            # Check if description_colbert exists
            if isinstance(vectors_config, dict):
                if "description_colbert" in vectors_config:
                    logger.debug("✅ description_colbert vector exists in collection")
                    self._description_vector_ready = True
                    return True

            # Vector not found - collection may need migration
            logger.error(
                f"❌ description_colbert vector not found in {COLLECTION_NAME}. "
                f"Run: uv run python scripts/migrate_colbert_collection_for_feedback.py"
            )
            return False

        except Exception as e:
            logger.error(f"❌ Failed to verify description_colbert vector: {e}")
            return False

    def store_instance_pattern(
        self,
        card_description: str,
        component_paths: List[str],
        instance_params: Dict[str, Any],
        feedback: Optional[str] = None,  # "positive", "negative", or None (pending)
        user_email: Optional[str] = None,
        card_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Store a card usage pattern as an instance_pattern point.

        Args:
            card_description: Original card description text
            component_paths: List of component paths used (e.g., ["card_framework.v2.widgets.decorated_text.DecoratedText"])
            instance_params: Parameters used to instantiate components
            feedback: "positive", "negative", or None
            user_email: User who created the card
            card_id: ID of the card (for linking feedback buttons)

        Returns:
            Point ID if stored successfully, None on error
        """
        # Ensure the vector exists
        if not self.ensure_description_vector_exists():
            logger.warning("Cannot store pattern: description_colbert vector not ready")
            return None

        client = self._get_client()
        if not client:
            return None

        # Embed the description
        description_vectors = self._embed_description(card_description)
        if not description_vectors:
            logger.warning("Cannot store pattern: failed to embed description")
            return None

        # Get ColBERT vectors from the first component path (to inherit component identity)
        # For now, we'll use the description vectors for both (simplified)
        # In a more advanced version, we'd look up the parent class's colbert vectors
        colbert_vectors = description_vectors  # Simplified: use same vectors

        # Generate point ID
        point_id = str(uuid.uuid4())

        try:
            from qdrant_client.models import PointStruct

            # Create the point
            point = PointStruct(
                id=point_id,
                vector={
                    "colbert": colbert_vectors,
                    "description_colbert": description_vectors,
                },
                payload={
                    "name": f"instance_pattern_{point_id[:8]}",
                    "type": "instance_pattern",
                    "parent_paths": component_paths,  # Links to existing class points
                    "instance_params": instance_params,
                    "card_description": card_description,
                    "feedback": feedback,
                    "user_email": user_email,
                    "card_id": card_id,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            # Upsert the point
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=[point],
            )

            logger.info(
                f"✅ Stored instance_pattern: {point_id[:8]}... (feedback={feedback})"
            )
            return point_id

        except Exception as e:
            logger.error(f"❌ Failed to store instance_pattern: {e}")
            return None

    def update_feedback(self, card_id: str, feedback: str) -> bool:
        """
        Update the feedback for an existing instance_pattern point by card_id.

        Args:
            card_id: The card_id stored in the pattern's payload
            feedback: "positive" or "negative"

        Returns:
            True if updated successfully
        """
        client = self._get_client()
        if not client:
            return False

        try:
            from qdrant_client import models

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

            point_id = results[0].id

            # Update the feedback
            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={
                    "feedback": feedback,
                    "feedback_timestamp": datetime.now().isoformat(),
                },
                points=[point_id],
            )

            logger.info(
                f"✅ Updated feedback for card {card_id[:8]}... (point {str(point_id)[:8]}...): {feedback}"
            )

            # Check for promotion if positive feedback
            if feedback == "positive":
                self._check_and_promote(results[0])

            return True

        except Exception as e:
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
            return False

        except Exception as e:
            logger.warning(f"Failed to check promotion: {e}")
            return False

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

    def query_with_feedback(
        self,
        component_query: str,
        description: str,
        limit: int = 10,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Hybrid query: Find components + boost with proven patterns.

        Uses prefetch + RRF fusion to:
        1. Find component classes by path (normal ColBERT search)
        2. Find successful patterns by description similarity
        3. Fuse results with RRF

        Args:
            component_query: Query for component search (e.g., "v2.widgets.decorated_text.DecoratedText class")
            description: Card description for pattern matching
            limit: Max results

        Returns:
            Tuple of (class_results, pattern_results)
        """
        client = self._get_client()
        embedder = self._get_embedder()

        if not client or not embedder:
            return [], []

        try:
            from qdrant_client import models

            # Embed component query
            component_vectors_raw = list(embedder.query_embed(component_query))[0]
            component_vectors = [vec.tolist() for vec in component_vectors_raw]

            # Embed description
            description_vectors = self._embed_description(description)

            if not description_vectors:
                # Fallback to simple component search
                return self._simple_component_search(component_vectors, limit), []

            # Hybrid query with prefetch + RRF using proper Qdrant models
            results = client.query_points(
                collection_name=COLLECTION_NAME,
                prefetch=[
                    # Prefetch 1: Component classes by path
                    models.Prefetch(
                        query=component_vectors,
                        using="colbert",
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
                    # Prefetch 2: Successful patterns by description
                    models.Prefetch(
                        query=description_vectors,
                        using="description_colbert",
                        filter=models.Filter(
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
                        limit=limit,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
            )

            # Separate results by type
            class_results = []
            pattern_results = []

            for point in results.points:
                result = {
                    "id": point.id,
                    "score": point.score,
                    **point.payload,
                }

                if point.payload.get("type") == "instance_pattern":
                    pattern_results.append(result)
                else:
                    class_results.append(result)

            logger.info(
                f"🔍 Hybrid query: {len(class_results)} classes, "
                f"{len(pattern_results)} patterns (feedback-boosted)"
            )

            return class_results, pattern_results

        except Exception as e:
            logger.error(f"❌ Hybrid query failed: {e}")
            # Fallback to simple search
            return (
                self._simple_component_search(
                    self._embed_description(component_query) or [], limit
                ),
                [],
            )

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
                using="colbert",
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

    def get_proven_params_for_description(
        self,
        description: str,
        min_score: float = 0.5,
    ) -> Optional[Dict[str, Any]]:
        """
        Find proven instance_params for a similar description.

        This is a convenience method that:
        1. Searches for similar positive patterns
        2. Returns the instance_params from the best match

        Args:
            description: Card description to match
            min_score: Minimum similarity score

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

            results = client.query_points(
                collection_name=COLLECTION_NAME,
                query=description_vectors,
                using="description_colbert",
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

            if results.points:
                best = results.points[0]
                logger.info(
                    f"✅ Found proven pattern (score={best.score:.3f}): "
                    f"{best.payload.get('card_description', '')[:50]}..."
                )
                return best.payload.get("instance_params")

            return None

        except Exception as e:
            logger.error(f"Pattern lookup failed: {e}")
            return None


# Singleton instance
_feedback_loop: Optional[FeedbackLoop] = None


def get_feedback_loop() -> FeedbackLoop:
    """Get the singleton FeedbackLoop instance."""
    global _feedback_loop
    if _feedback_loop is None:
        _feedback_loop = FeedbackLoop()
    return _feedback_loop
