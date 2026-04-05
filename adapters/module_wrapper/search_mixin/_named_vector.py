"""Named vector search methods: search_named_vector, search_hybrid (basic RRF)."""

from typing import Any, Dict, List, Optional, Tuple

from adapters.module_wrapper.search_mixin._base import SearchMixin
from adapters.module_wrapper.types import RELATIONSHIPS_DIM as _RELATIONSHIPS_DIM
from config.enhanced_logging import setup_logger

logger = setup_logger()

RELATIONSHIPS_DIM = _RELATIONSHIPS_DIM


def search_named_vector(
    self,
    query: str,
    vector_name: str = "components",
    limit: int = 10,
    score_threshold: float = 0.3,
    token_ratio: float = 1.0,
    type_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search collection using a specific named vector.

    The collection has three named vectors:
    - components: ColBERT multi-vector for component identity
    - inputs: ColBERT multi-vector for parameter values
    - relationships: MiniLM single-vector for graph connections

    Args:
        query: Search query
        vector_name: Which vector to search ("components", "inputs", "relationships")
        limit: Maximum results
        score_threshold: Minimum similarity score
        token_ratio: Fraction of ColBERT tokens to use (for ColBERT vectors)
        type_filter: Optional filter for point type

    Returns:
        List of matching results
    """
    if not self.client:
        logger.warning("Cannot search: Qdrant client not available")
        return []

    try:
        from qdrant_client import models

        # Generate appropriate embedding based on vector type
        if vector_name == "relationships":
            # Use MiniLM for relationships vector
            query_vector = self._embed_with_minilm(query)
            if not query_vector:
                logger.warning("MiniLM embedding failed for named-vector search")
                return []
        else:
            # Use ColBERT for components/inputs vectors
            query_vector = self._embed_with_colbert(query, token_ratio)
            if not query_vector:
                logger.warning("ColBERT embedding failed for named-vector search")
                return []

        # Build filter
        filter_conditions = []
        if type_filter:
            filter_conditions.append(
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value=type_filter),
                )
            )

        query_filter = (
            models.Filter(must=filter_conditions) if filter_conditions else None
        )

        # Search
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            using=vector_name,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        # Process results
        processed = []
        for point in results.points:
            payload = point.payload or {}
            processed.append(
                {
                    "id": point.id,
                    "score": point.score,
                    "name": payload.get("name"),
                    "type": payload.get("type"),
                    "full_path": payload.get("full_path"),
                    "symbol": payload.get("symbol"),
                    "docstring": payload.get("docstring", "")[:200],
                    "parent_paths": payload.get("parent_paths", []),
                    "vector_name": vector_name,
                }
            )

        logger.info(
            f"Named-vector search found {len(processed)} results (vector={vector_name})"
        )
        return processed

    except Exception as e:
        logger.error(f"Named-vector search failed: {e}")
        return []


def search_hybrid(
    self,
    description: str,
    component_paths: Optional[List[str]] = None,
    limit: int = 10,
    token_ratio: float = 1.0,
    content_feedback: Optional[str] = None,
    form_feedback: Optional[str] = None,
    include_classes: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Hybrid search using all three named vectors with RRF fusion.

    Searches against:
    1. components vector - for component classes
    2. inputs vector - for usage patterns matching description
    3. relationships vector - for structural patterns

    Results are fused using Reciprocal Rank Fusion (RRF).

    Args:
        description: Natural language description of what to find
        component_paths: Optional list of component paths for relationship context
        limit: Maximum results
        token_ratio: Fraction of ColBERT tokens to use
        content_feedback: Filter for content_feedback field ("positive", "negative", None)
        form_feedback: Filter for form_feedback field ("positive", "negative", None)
        include_classes: Whether to include class results (default True)

    Returns:
        Tuple of (class_results, pattern_results, relationship_results)
    """
    if not self.client:
        logger.warning("Cannot search: Qdrant client not available")
        return [], [], []

    try:
        from qdrant_client import models

        # Generate embeddings
        component_vectors = self._embed_with_colbert(description, token_ratio)
        description_vectors = self._embed_with_colbert(description, token_ratio)

        if not component_vectors or not description_vectors:
            logger.warning("Embedding failed for hybrid search")
            return [], [], []

        # Generate relationship vector
        relationship_text = description
        if component_paths:
            # Enrich with component names
            comp_names = [p.split(".")[-1] for p in component_paths]
            relationship_text = f"{description} | {' '.join(comp_names)}"

        relationship_vector = self._embed_with_minilm(relationship_text)
        if not relationship_vector:
            relationship_vector = [0.0] * RELATIONSHIPS_DIM

        # Build prefetch list
        prefetch_list = []

        # Prefetch 1: Component classes (if requested)
        if include_classes:
            prefetch_list.append(
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
                )
            )

        # Prefetch 2: Instance patterns by inputs (with optional content_feedback filter)
        inputs_filter_conditions = [
            models.FieldCondition(
                key="type",
                match=models.MatchValue(value="instance_pattern"),
            )
        ]
        if content_feedback:
            inputs_filter_conditions.append(
                models.FieldCondition(
                    key="content_feedback",
                    match=models.MatchValue(value=content_feedback),
                )
            )

        prefetch_list.append(
            models.Prefetch(
                query=description_vectors,
                using="inputs",
                filter=models.Filter(must=inputs_filter_conditions),
                limit=limit,
            )
        )

        # Prefetch 3: Patterns by relationships (with optional form_feedback filter)
        if relationship_vector and relationship_vector != [0.0] * RELATIONSHIPS_DIM:
            rel_filter_conditions = [
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value="instance_pattern"),
                )
            ]
            if form_feedback:
                rel_filter_conditions.append(
                    models.FieldCondition(
                        key="form_feedback",
                        match=models.MatchValue(value=form_feedback),
                    )
                )

            prefetch_list.append(
                models.Prefetch(
                    query=relationship_vector,
                    using="relationships",
                    filter=models.Filter(must=rel_filter_conditions),
                    limit=limit,
                )
            )

        # Hybrid query with prefetch + RRF
        results = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=prefetch_list,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit * 3,
            with_payload=True,
        )

        # Separate results by type and feedback
        class_results = []
        pattern_results = []
        relationship_results = []

        for point in results.points:
            payload = point.payload or {}
            result = {
                "id": point.id,
                "score": point.score,
                "name": payload.get("name"),
                "type": payload.get("type"),
                "full_path": payload.get("full_path"),
                "symbol": payload.get("symbol"),
                "docstring": payload.get("docstring", "")[:200],
                "content_feedback": payload.get("content_feedback"),
                "form_feedback": payload.get("form_feedback"),
                "parent_paths": payload.get("parent_paths", []),
                "structure_description": payload.get("structure_description", ""),
                "card_description": payload.get("card_description", ""),
                "relationship_text": payload.get("relationship_text", ""),
                "instance_params": payload.get("instance_params", {}),
            }

            point_type = payload.get("type")
            if point_type == "instance_pattern":
                # Categorize by feedback
                if payload.get("content_feedback") == "positive":
                    pattern_results.append(result)
                if payload.get("form_feedback") == "positive":
                    relationship_results.append(result)
                # If neither explicitly positive but is a pattern, add to patterns
                if not pattern_results or result not in pattern_results:
                    if payload.get("feedback") == "positive" or (
                        payload.get("content_feedback") != "positive"
                        and payload.get("form_feedback") != "positive"
                    ):
                        pattern_results.append(result)
            else:
                class_results.append(result)

        # Log with feedback filter info
        filter_info = []
        if content_feedback:
            filter_info.append(f"content={content_feedback}")
        if form_feedback:
            filter_info.append(f"form={form_feedback}")
        filter_str = f" [{', '.join(filter_info)}]" if filter_info else ""

        logger.info(
            f"Hybrid search{filter_str}: {len(class_results)} classes, "
            f"{len(pattern_results)} patterns, {len(relationship_results)} relationships"
        )

        return (
            class_results[:limit],
            pattern_results[:limit],
            relationship_results[:limit],
        )

    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        return [], [], []
