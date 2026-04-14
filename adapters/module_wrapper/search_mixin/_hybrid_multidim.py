"""Multi-dimensional scoring search (Horizon 1 -- POC validated +9.5%)."""

from typing import Any, Dict, List, Optional, Tuple

from adapters.module_wrapper.types import RELATIONSHIPS_DIM as _RELATIONSHIPS_DIM
from config.enhanced_logging import setup_logger

logger = setup_logger()

RELATIONSHIPS_DIM = _RELATIONSHIPS_DIM


def search_hybrid_multidim(
    self,
    description: str,
    component_paths: Optional[List[str]] = None,
    limit: int = 10,
    token_ratio: float = 1.0,
    content_feedback: Optional[str] = None,
    form_feedback: Optional[str] = None,
    include_classes: bool = True,
    candidate_pool_size: int = 20,
    content_text: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Multi-dimensional scoring search using all four named vectors.

    Unlike search_hybrid (which uses Qdrant's native RRF rank fusion), this
    method uses Qdrant's prefetch pipeline to expand the candidate pool, then
    retrieves stored vectors (with_vectors=True) and performs client-side
    multiplicative cross-dimensional scoring. This is necessary because Qdrant's
    native fusion (RRF/DBSF) operates on ranks/scores from individual vectors,
    not on cross-dimensional similarity products.

    POC validated: +9.5% Top-1 accuracy over RRF fusion.

    Architecture (1 Qdrant round-trip for candidate collection):
        1. Embed query into 4 vectors (ColBERT for components/inputs, MiniLM for relationships/content)
        2. Single query_points call with prefetch pipeline + RRF fusion + with_vectors=True
           (Qdrant handles the 4 independent searches server-side and returns vectors)
        3. Client-side rerank: sim_c x sim_r x sim_i with content boost
        4. Apply feedback boost (positive -> x1.1, negative -> x0.8)
        5. Categorize into (class_results, content_patterns, form_patterns)

    Args:
        description: Natural language description of what to find
        component_paths: Optional list of component paths for relationship context
        limit: Maximum results per category
        token_ratio: Fraction of ColBERT tokens to use
        content_feedback: Filter for content_feedback field
        form_feedback: Filter for form_feedback field
        include_classes: Whether to include class results (default True)
        candidate_pool_size: How many candidates to retrieve per vector (default 20)
        content_text: Actual user content for content vector search (button texts, labels, etc.)

    Returns:
        Tuple of (class_results, content_patterns, form_patterns)
        Same signature as search_hybrid() for caller compatibility.
    """
    if not self.client:
        logger.warning("Cannot search: Qdrant client not available")
        return [], [], []

    try:
        from qdrant_client import models

        # --- Step 1: Embed query into 3 vectors ---
        query_colbert = self._embed_with_colbert(description, token_ratio)
        if not query_colbert:
            logger.warning("ColBERT embedding failed for multidim search")
            return [], [], []

        relationship_text = description
        if component_paths:
            comp_names = [p.split(".")[-1] for p in component_paths]
            relationship_text = f"{description} | {' '.join(comp_names)}"

        query_minilm = self._embed_with_minilm(relationship_text)
        if not query_minilm:
            query_minilm = [0.0] * RELATIONSHIPS_DIM

        # Embed content text if provided (same MiniLM model, 384D)
        query_content_minilm = None
        if content_text:
            query_content_minilm = self._embed_with_minilm(content_text)

        # --- Step 2: Build prefetch pipeline (same pattern as search_hybrid) ---
        # Qdrant executes these searches server-side in a single round-trip.
        pool = candidate_pool_size
        prefetch_list = []

        # Prefetch 1: Components (classes)
        if include_classes:
            prefetch_list.append(
                models.Prefetch(
                    query=query_colbert,
                    using="components",
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="class"),
                            )
                        ]
                    ),
                    limit=pool,
                )
            )

        # Prefetch 2: Inputs (instance patterns + content_feedback filter)
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
                query=query_colbert,
                using="inputs",
                filter=models.Filter(must=inputs_filter_conditions),
                limit=pool,
            )
        )

        # Prefetch 3: Relationships (instance patterns + form_feedback filter)
        if query_minilm and query_minilm != [0.0] * RELATIONSHIPS_DIM:
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
                    query=query_minilm,
                    using="relationships",
                    filter=models.Filter(must=rel_filter_conditions),
                    limit=pool,
                )
            )

        # Prefetch 4: Content (instance patterns with actual content vectors)
        if query_content_minilm:
            prefetch_list.append(
                models.Prefetch(
                    query=query_content_minilm,
                    using="content",
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(
                                    value="instance_pattern"
                                ),
                            ),
                        ]
                    ),
                    limit=pool,
                )
            )

        # Single Qdrant call: prefetch expands pool, RRF deduplicates,
        # with_vectors=True returns stored vectors for client-side reranking.
        results = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=prefetch_list,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=pool * 3,  # Get full candidate pool
            with_payload=True,
            with_vectors=True,
        )

        if not results.points:
            logger.info("Multidim search: no candidates found")
            return [], [], []

        # --- Step 3: Client-side cross-dimensional reranking ---
        # Qdrant's RRF gave us a deduplicated candidate pool with vectors.
        # Now we rescore using multiplicative cross-dim similarity.
        scored = []
        for point in results.points:
            vectors = point.vector or {}
            payload = point.payload or {}

            # Get stored vectors (handle both dict and None)
            comp_vec = vectors.get("components") if isinstance(vectors, dict) else None
            inp_vec = vectors.get("inputs") if isinstance(vectors, dict) else None
            rel_vec = vectors.get("relationships") if isinstance(vectors, dict) else None
            content_vec = vectors.get("content") if isinstance(vectors, dict) else None

            # Compute cross-dimensional similarities
            sim_c = 0.0
            sim_i = 0.0
            sim_r = 0.0
            sim_content = 0.0

            if comp_vec and query_colbert:
                if isinstance(comp_vec[0], list):
                    # Multi-vector (ColBERT): use MaxSim
                    sim_c = self._maxsim(query_colbert, comp_vec)
                else:
                    # Dense vector fallback
                    sim_c = self._cosine_similarity(query_colbert[0], comp_vec)

            if inp_vec and query_colbert:
                if isinstance(inp_vec[0], list):
                    sim_i = self._maxsim(query_colbert, inp_vec)
                else:
                    sim_i = self._cosine_similarity(query_colbert[0], inp_vec)

            if rel_vec and query_minilm:
                if isinstance(rel_vec, list) and rel_vec and not isinstance(rel_vec[0], list):
                    sim_r = self._cosine_similarity(query_minilm, rel_vec)
                elif isinstance(rel_vec, list) and rel_vec and isinstance(rel_vec[0], list):
                    sim_r = self._maxsim([query_minilm], rel_vec)

            if content_vec and query_content_minilm:
                is_dense = (
                    isinstance(content_vec, list)
                    and content_vec
                    and not isinstance(content_vec[0], list)
                )
                if is_dense:
                    sim_content = self._cosine_similarity(
                        query_content_minilm, content_vec
                    )

            # Multiplicative fusion -- rewards cross-dimensional consistency
            # Add small epsilon to avoid zero-products from missing vectors
            eps = 0.01
            score = (sim_c + eps) * (sim_r + eps) * (sim_i + eps)

            # Content boost (additive, not multiplicative -- zero content = no change)
            if sim_content > 0.0:
                score *= (1.0 + sim_content)

            # --- Step 4: Feedback boost ---
            cf = payload.get("content_feedback")
            ff = payload.get("form_feedback")
            if cf == "positive":
                score *= 1.1
            elif cf == "negative":
                score *= 0.8
            if ff == "positive":
                score *= 1.1
            elif ff == "negative":
                score *= 0.8

            scored.append((score, sim_c, sim_r, sim_i, sim_content, point))

        # Sort by cross-dimensional score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # --- Step 5: Categorize results ---
        class_results = []
        pattern_results = []
        relationship_results = []

        for score, sim_c, sim_r, sim_i, sim_ct, point in scored:
            payload = point.payload or {}
            result = {
                "id": point.id,
                "score": score,
                "sim_components": sim_c,
                "sim_relationships": sim_r,
                "sim_inputs": sim_i,
                "sim_content": sim_ct,
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
            if point_type == "class":
                class_results.append(result)
            elif point_type == "instance_pattern":
                if payload.get("content_feedback") == "positive":
                    pattern_results.append(result)
                if payload.get("form_feedback") == "positive":
                    relationship_results.append(result)
                # Patterns without explicit positive feedback go to pattern_results
                if result not in pattern_results:
                    if payload.get("content_feedback") != "positive" and payload.get(
                        "form_feedback"
                    ) != "positive":
                        pattern_results.append(result)
            else:
                class_results.append(result)

        # Log results
        filter_info = []
        if content_feedback:
            filter_info.append(f"content={content_feedback}")
        if form_feedback:
            filter_info.append(f"form={form_feedback}")
        filter_str = f" [{', '.join(filter_info)}]" if filter_info else ""

        logger.info(
            f"Multidim search{filter_str}: {len(class_results)} classes, "
            f"{len(pattern_results)} patterns, {len(relationship_results)} relationships "
            f"(from {len(results.points)} candidates)"
        )

        return (
            class_results[:limit],
            pattern_results[:limit],
            relationship_results[:limit],
        )

    except Exception as e:
        logger.error(f"Multi-dimensional search failed: {e}", exc_info=True)
        return [], [], []
