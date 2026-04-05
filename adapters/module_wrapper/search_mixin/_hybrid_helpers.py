"""Shared helpers for hybrid search: prefetch building, candidate grouping, structural features."""

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from config.enhanced_logging import setup_logger

logger = setup_logger()


def _build_prefetch_list(
    self,
    query_colbert,
    query_minilm,
    candidate_pool_size: int,
    include_classes: bool = True,
    content_feedback: Optional[str] = None,
    form_feedback: Optional[str] = None,
    query_content_minilm=None,
) -> list:
    """Build the Qdrant prefetch pipeline (shared by multidim/learned/recursive)."""
    from qdrant_client.models import (
        FieldCondition,
        Filter,
        MatchValue,
        Prefetch,
    )

    prefetch_list = []

    # Prefetch 1: Components (classes)
    comp_filter = (
        Filter(must=[FieldCondition(key="type", match=MatchValue(value="class"))])
        if include_classes else None
    )
    prefetch_list.append(
        Prefetch(query=query_colbert, using="components",
                 limit=candidate_pool_size, filter=comp_filter)
    )

    # Prefetch 2: Inputs (instance patterns + content feedback filter)
    inp_conditions = [
        FieldCondition(key="type", match=MatchValue(value="instance_pattern"))
    ]
    if content_feedback:
        inp_conditions.append(
            FieldCondition(key="content_feedback", match=MatchValue(value=content_feedback))
        )
    prefetch_list.append(
        Prefetch(query=query_colbert, using="inputs",
                 limit=candidate_pool_size, filter=Filter(must=inp_conditions))
    )

    # Prefetch 3: Relationships (form feedback filter)
    rel_conditions = [
        FieldCondition(key="type", match=MatchValue(value="instance_pattern"))
    ]
    if form_feedback:
        rel_conditions.append(
            FieldCondition(key="form_feedback", match=MatchValue(value=form_feedback))
        )
    prefetch_list.append(
        Prefetch(query=query_minilm, using="relationships",
                 limit=candidate_pool_size, filter=Filter(must=rel_conditions))
    )

    # Prefetch 4: Content (instance patterns with actual content vectors)
    if query_content_minilm:
        content_conditions = [
            FieldCondition(
                key="type", match=MatchValue(value="instance_pattern")
            ),
        ]
        prefetch_list.append(
            Prefetch(
                query=query_content_minilm,
                using="content",
                limit=candidate_pool_size,
                filter=Filter(must=content_conditions),
            )
        )

    return prefetch_list


def _query_grouped_candidates(
    self,
    query_colbert,
    query_minilm,
    candidate_pool_size: int = 20,
    content_feedback: Optional[str] = None,
    form_feedback: Optional[str] = None,
    group_size: int = 10,
    query_content_minilm=None,
) -> list:
    """Query Qdrant with grouped results, ensuring diversity across point types.

    Uses query_points_groups(group_by="type") to guarantee balanced
    representation of classes, instance_patterns, etc. Combined with
    prefetch + RRF fusion for multi-vector search.

    Returns a flat list of points (with .vector and .payload) from all groups.
    """
    from qdrant_client.models import (
        FieldCondition,
        Filter,
        Fusion,
        FusionQuery,
        MatchValue,
        Prefetch,
    )

    prefetch_list = self._build_prefetch_list(
        query_colbert, query_minilm, candidate_pool_size,
        include_classes=True,
        content_feedback=content_feedback,
        form_feedback=form_feedback,
        query_content_minilm=query_content_minilm,
    )

    try:
        grouped = self.client.query_points_groups(
            collection_name=self.collection_name,
            group_by="type",
            prefetch=prefetch_list,
            query=FusionQuery(fusion=Fusion.RRF),
            limit=5,               # up to 5 type groups (class, instance_pattern, function, etc.)
            group_size=group_size,  # points per group
            with_payload=True,
            with_vectors=True,
        )

        # Flatten groups into a single point list
        points = []
        group_counts = {}
        for group in grouped.groups:
            group_type = str(group.id)
            group_counts[group_type] = len(group.hits)
            for hit in group.hits:
                points.append(hit)

        logger.info(
            "Grouped query: %d points across %d groups: %s",
            len(points), len(group_counts), group_counts,
        )
        return points

    except Exception as e:
        # Fallback: query_points_groups may not be available on older Qdrant
        logger.warning("query_points_groups failed (%s), falling back to query_points", e)
        prefetch_list = self._build_prefetch_list(
            query_colbert, query_minilm, candidate_pool_size,
            include_classes=True,
            content_feedback=content_feedback,
            form_feedback=form_feedback,
        )
        results = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=prefetch_list,
            query=FusionQuery(fusion=Fusion.RRF),
            limit=candidate_pool_size * 3,
            with_payload=True,
            with_vectors=True,
        )
        return results.points


def _infer_component_paths(self, points) -> Optional[List[str]]:
    """Infer component_paths from instance_pattern payloads in Qdrant results.

    For NL queries (no DSL/component_paths), extracts parent_paths from
    top instance_pattern candidates and returns the consensus set.
    """
    comp_counts = Counter()
    for point in points:
        payload = point.payload or {}
        if payload.get("type") == "instance_pattern":
            pp = payload.get("parent_paths") or payload.get("component_paths") or []
            if isinstance(pp, list):
                comp_counts.update(pp)
    if not comp_counts:
        return None
    threshold = 2 if len(comp_counts) > 5 else 1
    raw_paths = [c for c, n in comp_counts.most_common() if n >= threshold]
    # Normalize to short names (DAG uses "Button" not "card_framework.v2.Button")
    paths = list({p.rsplit(".", 1)[-1] for p in raw_paths})
    if paths:
        logger.info(
            "Inferred component_paths from %d pattern entries: %s",
            sum(comp_counts.values()), paths[:10],
        )
    return paths or None


def _compute_structural_features(
    self, cand_name: str, query_components: set,
) -> tuple:
    """Compute 5 structural DAG features for a candidate.

    Returns: (is_parent, is_child, is_sibling, depth_ratio, n_shared_ancestors)
    """
    self._ensure_learned_dag()

    cand_children = self._learned_dag_children.get(cand_name, set())
    cand_parents = self._learned_dag_parents.get(cand_name, set())

    is_parent = 1.0 if (cand_children & query_components) else 0.0
    is_child = 1.0 if (cand_parents & query_components) else 0.0

    is_sibling = 0.0
    for qc in query_components:
        if self._learned_dag_parents.get(qc, set()) & cand_parents:
            is_sibling = 1.0
            break

    max_depth = max(self._learned_dag_depth.values()) if self._learned_dag_depth else 1
    depth_ratio = self._learned_dag_depth.get(cand_name, 0) / max_depth if max_depth > 0 else 0.0

    def _ancestors(name):
        anc = set()
        queue = list(self._learned_dag_parents.get(name, []))
        while queue:
            p = queue.pop(0)
            if p not in anc:
                anc.add(p)
                queue.extend(self._learned_dag_parents.get(p, []))
        return anc

    cand_anc = _ancestors(cand_name)
    query_anc = set()
    for qc in query_components:
        query_anc.update(_ancestors(qc))
    total = len(cand_anc | query_anc) or 1
    n_shared = len(cand_anc & query_anc) / total

    return (is_parent, is_child, is_sibling, depth_ratio, n_shared)


@staticmethod
def _compute_content_density(point) -> float:
    """Ratio of non-empty content fields in candidate payload.

    Returns 0.0 for class points (no content), 0.0-1.0 for
    instance patterns based on how many content fields are populated.
    """
    payload = point.payload or {}
    params = payload.get("instance_params", {})
    if not params or not isinstance(params, dict):
        return 0.0

    content_keys = [
        "title", "subtitle", "buttons", "items",
        "content_texts", "chips", "text",
    ]
    populated = 0
    for key in content_keys:
        val = params.get(key)
        if val:
            if isinstance(val, list) and len(val) > 0:
                populated += 1
            elif isinstance(val, str) and val.strip():
                populated += 1
    return populated / len(content_keys)


def _compute_learned_features(
    self,
    points,
    query_colbert,
    query_minilm,
    component_paths: Optional[List[str]] = None,
    query_content_minilm=None,
) -> tuple:
    """Compute features for all candidate points and return (features_list, points_data).

    Handles V1 (norms), V2 (structural), V3 (decomposed MaxSim),
    and V4 (V3 + content similarity) features.
    Returns:
        features_list: List of feature vectors (one per candidate)
        points_data: List of (sim_c, sim_r, sim_i, sim_content, point) tuples
    """
    import math

    features_list = []
    points_data = []
    query_components = set(component_paths) if component_paths else set()

    for point in points:
        vectors = point.vector or {}
        comp_vec = vectors.get("components") if isinstance(vectors, dict) else None
        inp_vec = vectors.get("inputs") if isinstance(vectors, dict) else None
        rel_vec = vectors.get("relationships") if isinstance(vectors, dict) else None
        content_vec = vectors.get("content") if isinstance(vectors, dict) else None

        # Compute similarities
        sim_c = 0.0
        sim_i = 0.0
        sim_r = 0.0
        sim_content = 0.0

        if comp_vec and query_colbert:
            sim_c = self._maxsim(query_colbert, comp_vec) if isinstance(comp_vec[0], list) else self._cosine_similarity(query_colbert[0], comp_vec)
        if inp_vec and query_colbert:
            sim_i = self._maxsim(query_colbert, inp_vec) if isinstance(inp_vec[0], list) else self._cosine_similarity(query_colbert[0], inp_vec)
        if rel_vec and query_minilm:
            if isinstance(rel_vec, list) and rel_vec and not isinstance(rel_vec[0], list):
                sim_r = self._cosine_similarity(query_minilm, rel_vec)
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

        if self._learned_feature_version >= 5:
            # V5: dual-head (17D) = V4 + content_density + content_form_alignment
            cand_name = (point.payload or {}).get("name", "")
            is_parent, is_child, is_sibling, depth_ratio, n_shared = \
                self._compute_structural_features(cand_name, query_components)

            if comp_vec and query_colbert and isinstance(comp_vec[0], list):
                sc_m, sc_x, sc_s, sc_cv = self._maxsim_decomposed(query_colbert, comp_vec)
            else:
                sc_m, sc_x, sc_s, sc_cv = sim_c, sim_c, 0.0, (1.0 if sim_c > 0.4 else 0.0)

            if inp_vec and query_colbert and isinstance(inp_vec[0], list):
                si_m, si_x, si_s, si_cv = self._maxsim_decomposed(query_colbert, inp_vec)
            else:
                si_m, si_x, si_s, si_cv = sim_i, sim_i, 0.0, (1.0 if sim_i > 0.4 else 0.0)

            # Content density: ratio of non-empty content fields
            content_density = self._compute_content_density(point)

            # Content-form alignment: query content vs candidate relationship
            content_form_alignment = 0.0
            if query_content_minilm and rel_vec:
                is_rel_dense = (
                    isinstance(rel_vec, list)
                    and rel_vec
                    and not isinstance(rel_vec[0], list)
                )
                if is_rel_dense:
                    content_form_alignment = self._cosine_similarity(
                        query_content_minilm, rel_vec
                    )

            features_list.append([
                sc_m, sc_x, sc_s, sc_cv,
                si_m, si_x, si_s, si_cv,
                sim_r,
                is_parent, is_child, is_sibling, depth_ratio, n_shared,
                sim_content,
                content_density,
                content_form_alignment,
            ])

        elif self._learned_feature_version == 4:
            # V4: V3 + content similarity (15D)
            cand_name = (point.payload or {}).get("name", "")
            is_parent, is_child, is_sibling, depth_ratio, n_shared = \
                self._compute_structural_features(cand_name, query_components)

            if comp_vec and query_colbert and isinstance(comp_vec[0], list):
                sc_m, sc_x, sc_s, sc_cv = self._maxsim_decomposed(query_colbert, comp_vec)
            else:
                sc_m, sc_x, sc_s, sc_cv = sim_c, sim_c, 0.0, (1.0 if sim_c > 0.4 else 0.0)

            if inp_vec and query_colbert and isinstance(inp_vec[0], list):
                si_m, si_x, si_s, si_cv = self._maxsim_decomposed(query_colbert, inp_vec)
            else:
                si_m, si_x, si_s, si_cv = sim_i, sim_i, 0.0, (1.0 if sim_i > 0.4 else 0.0)

            features_list.append([
                sc_m, sc_x, sc_s, sc_cv,
                si_m, si_x, si_s, si_cv,
                sim_r,
                is_parent, is_child, is_sibling, depth_ratio, n_shared,
                sim_content,
            ])

        elif self._learned_feature_version == 3:
            # V3: decomposed MaxSim + structural (14D)
            cand_name = (point.payload or {}).get("name", "")
            is_parent, is_child, is_sibling, depth_ratio, n_shared = \
                self._compute_structural_features(cand_name, query_components)

            if comp_vec and query_colbert and isinstance(comp_vec[0], list):
                sc_m, sc_x, sc_s, sc_cv = self._maxsim_decomposed(query_colbert, comp_vec)
            else:
                sc_m, sc_x, sc_s, sc_cv = sim_c, sim_c, 0.0, (1.0 if sim_c > 0.4 else 0.0)

            if inp_vec and query_colbert and isinstance(inp_vec[0], list):
                si_m, si_x, si_s, si_cv = self._maxsim_decomposed(query_colbert, inp_vec)
            else:
                si_m, si_x, si_s, si_cv = sim_i, sim_i, 0.0, (1.0 if sim_i > 0.4 else 0.0)

            features_list.append([
                sc_m, sc_x, sc_s, sc_cv,
                si_m, si_x, si_s, si_cv,
                sim_r,
                is_parent, is_child, is_sibling, depth_ratio, n_shared,
            ])

        elif self._learned_feature_version == 2:
            # V2: scalar MaxSim + structural
            cand_name = (point.payload or {}).get("name", "")
            is_parent, is_child, is_sibling, depth_ratio, n_shared = \
                self._compute_structural_features(cand_name, query_components)
            features_list.append([sim_c, sim_i, sim_r, is_parent, is_child, is_sibling, depth_ratio, n_shared])

        else:
            # V1: norm features (legacy)
            def _vec_norm(v):
                if not v:
                    return 0.0
                flat = []
                if isinstance(v[0], list):
                    for sub in v:
                        flat.extend(sub)
                else:
                    flat = v
                return math.sqrt(sum(x * x for x in flat))

            features_list.append([
                sim_c, sim_i, sim_r,
                _vec_norm(query_colbert), _vec_norm(query_colbert),
                _vec_norm(query_minilm) if query_minilm else 0.0,
                _vec_norm(comp_vec), _vec_norm(inp_vec), _vec_norm(rel_vec),
            ])

        points_data.append((sim_c, sim_r, sim_i, sim_content, point))

    return features_list, points_data


def _categorize_scored_results(
    self,
    scored: list,
    limit: int,
    extra_fields: Optional[dict] = None,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Categorize scored candidates into class, pattern, and relationship buckets.

    Args:
        scored: List of (score, sim_c, sim_r, sim_i, sim_content, point) tuples,
                sorted by score desc.
        limit: Max results per bucket.
        extra_fields: Additional fields to add to each result dict.

    Returns:
        (class_results, pattern_results, relationship_results)
    """
    class_results = []
    pattern_results = []
    relationship_results = []

    for entry in scored:
        # Support both 5-tuple (legacy) and 6-tuple (with sim_content)
        if len(entry) == 6:
            score, sim_c, sim_r, sim_i, sim_ct, point = entry
        else:
            score, sim_c, sim_r, sim_i, point = entry
            sim_ct = 0.0
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
        if extra_fields:
            result.update(extra_fields)

        point_type = payload.get("type")
        if point_type == "class":
            class_results.append(result)
        elif point_type == "instance_pattern":
            if payload.get("content_feedback") == "positive":
                pattern_results.append(result)
            if payload.get("form_feedback") == "positive":
                relationship_results.append(result)
            if result not in pattern_results:
                if payload.get("content_feedback") != "positive" and payload.get("form_feedback") != "positive":
                    pattern_results.append(result)
        else:
            class_results.append(result)

    return (
        class_results[:limit],
        pattern_results[:limit],
        relationship_results[:limit],
    )
