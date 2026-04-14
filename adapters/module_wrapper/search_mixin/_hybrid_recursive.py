"""Recursive refinement search with learned halt (UnifiedTRN) or heuristic halt."""

import time
from typing import Any, Dict, List, Optional, Tuple

from config.enhanced_logging import setup_logger

logger = setup_logger()


def search_hybrid_recursive(
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
    Recursive refinement search -- iteratively refines query vectors using
    top-K results from the learned scorer, then re-queries Qdrant.

    Supports three halt mechanisms:
      - UnifiedTRN halt head: learned sigmoid(halt_prob) > threshold
      - Dual-head heuristic: form + content convergence
      - Single-head heuristic: margin + name stability

    Uses RECURSIVE_MAX_CYCLES, RECURSIVE_HALT_MARGIN, RECURSIVE_ALPHA_INIT
    from settings.
    """
    # Load settings
    max_cycles = 3
    halt_margin = 0.5
    halt_prob_threshold = 0.7
    alpha_init = 0.7
    alpha_decay = 0.1
    content_pool_size = 10
    try:
        from config.settings import Settings
        _s = Settings()
        max_cycles = _s.recursive_max_cycles
        halt_margin = _s.recursive_halt_margin
        alpha_init = _s.recursive_alpha_init
        alpha_decay = _s.recursive_alpha_decay
        content_pool_size = _s.recursive_content_pool_size
        halt_prob_threshold = getattr(_s, "recursive_halt_prob_threshold", 0.7)
    except Exception:
        pass

    try:
        import torch
    except ImportError:
        logger.warning("torch not installed, falling back to learned")
        return self.search_hybrid_learned(
            description=description, component_paths=component_paths,
            limit=limit, token_ratio=token_ratio,
            content_feedback=content_feedback, form_feedback=form_feedback,
            include_classes=include_classes, candidate_pool_size=candidate_pool_size,
            content_text=content_text,
        )

    model = self._load_learned_model()
    if model is None:
        return self.search_hybrid_learned(
            description=description, component_paths=component_paths,
            limit=limit, token_ratio=token_ratio,
            content_feedback=content_feedback, form_feedback=form_feedback,
            include_classes=include_classes, candidate_pool_size=candidate_pool_size,
            content_text=content_text,
        )

    # Detect model type AFTER loading
    is_unified = self._learned_model_type == "unified"
    is_dual = self._learned_model_type == "dual_head"
    has_halt_head = is_unified  # only UnifiedTRN has a learned halt

    try:
        import numpy as np
        from qdrant_client.models import Fusion, FusionQuery
        from qdrant_client.models import Prefetch as QdrantPrefetch

        # --- Embed original query ---
        query_colbert_orig = self._embed_with_colbert(description, token_ratio)
        rel_text = description
        if component_paths:
            rel_text = f"{description} components: {', '.join(component_paths)}"
        query_minilm_orig = self._embed_with_minilm(rel_text)

        if not query_colbert_orig or not query_minilm_orig:
            return [], [], []

        # Embed content text if provided
        query_content_minilm = None
        if content_text:
            query_content_minilm = self._embed_with_minilm(content_text)

        query_colbert = query_colbert_orig
        query_minilm = query_minilm_orig
        cycle_log = []
        best_scored = None
        prev_top1_name = None
        prev_content_top1_name = None
        _next_cycle_points = None

        for cycle in range(max_cycles):
            t0 = time.monotonic()

            if _next_cycle_points is not None:
                cycle_points = _next_cycle_points
                _next_cycle_points = None
            else:
                prefetch_list = self._build_prefetch_list(
                    query_colbert, query_minilm, candidate_pool_size,
                    include_classes, content_feedback, form_feedback,
                    query_content_minilm=query_content_minilm,
                )
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    prefetch=prefetch_list,
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=candidate_pool_size * 3,
                    with_payload=True,
                    with_vectors=True,
                )
                cycle_points = results.points

            if not cycle_points:
                break

            # --- Infer component_paths (first cycle only) ---
            if cycle == 0 and not component_paths and self._learned_feature_version in (2, 3, 4, 5):
                component_paths = self._infer_component_paths(cycle_points)

            # --- Compute features ---
            features_list, points_data = self._compute_learned_features(
                cycle_points, query_colbert, query_minilm, component_paths,
                query_content_minilm=query_content_minilm,
            )

            if not features_list:
                break

            features_tensor = torch.tensor(features_list, dtype=torch.float32)

            # --- Model inference (architecture-dependent) ---
            with torch.no_grad():
                if is_unified:
                    # UnifiedTRN: structural(17D) + content(384D) → form/content/halt
                    content_emb = query_content_minilm if query_content_minilm else query_minilm
                    content_tensor = torch.tensor(
                        [content_emb] * len(features_list), dtype=torch.float32
                    )
                    result = model(features_tensor, content_tensor, mode="search")
                    form_scores_t = result["form_score"].squeeze(-1)
                    content_scores_t = result["content_score"].squeeze(-1)
                    halt_probs = result["halt_prob"].squeeze(-1)

                    # Adaptive alpha: form-dominant early, content grows
                    cycle_alpha = max(0.3, alpha_init - (cycle * alpha_decay))
                    scores_tensor = (
                        cycle_alpha * form_scores_t
                        + (1.0 - cycle_alpha) * content_scores_t
                    )
                    form_scores = form_scores_t.tolist()
                    content_scores = content_scores_t.tolist()
                    halt_probs_list = halt_probs.tolist()

                elif is_dual:
                    form_t, content_t = model(features_tensor)
                    form_scores_t = form_t.squeeze(-1)
                    content_scores_t = content_t.squeeze(-1)
                    cycle_alpha = max(0.3, alpha_init - (cycle * alpha_decay))
                    scores_tensor = (
                        cycle_alpha * form_scores_t
                        + (1.0 - cycle_alpha) * content_scores_t
                    )
                    form_scores = form_scores_t.tolist()
                    content_scores = content_scores_t.tolist()
                    halt_probs_list = None

                else:
                    scores_tensor = model(features_tensor).squeeze(-1)
                    form_scores = None
                    content_scores = None
                    cycle_alpha = None
                    halt_probs_list = None

            scores = scores_tensor.tolist()

            scored = sorted(
                zip(scores, points_data),
                key=lambda x: x[0], reverse=True,
            )

            # --- Cycle tracking ---
            top1_name = (scored[0][1][4].payload or {}).get("name", "?") if scored else "?"
            top1_score = scored[0][0] if scored else 0.0
            top2_score = scored[1][0] if len(scored) > 1 else 0.0
            margin = top1_score - top2_score
            elapsed = round((time.monotonic() - t0) * 1000)

            top_idx = scores.index(top1_score) if top1_score in scores else 0

            cycle_entry = {
                "cycle": cycle, "top1": top1_name,
                "top1_score": round(top1_score, 4),
                "margin": round(margin, 4),
                "n_candidates": len(scored), "latency_ms": elapsed,
            }

            if is_unified or is_dual:
                cycle_entry["form_top1_score"] = round(form_scores[top_idx], 4)
                cycle_entry["content_top1_score"] = round(content_scores[top_idx], 4)
                cycle_entry["cycle_alpha"] = round(cycle_alpha, 2)

                form_top1_idx = form_scores.index(max(form_scores))
                content_top1_idx = content_scores.index(max(content_scores))
                form_top1_name = (points_data[form_top1_idx][4].payload or {}).get("name", "?")
                content_top1_name = (points_data[content_top1_idx][4].payload or {}).get("name", "?")
                cycle_entry["form_top1"] = form_top1_name
                cycle_entry["content_top1"] = content_top1_name
            else:
                form_top1_name = top1_name
                content_top1_name = None

            if has_halt_head and halt_probs_list:
                top1_halt = halt_probs_list[top_idx]
                cycle_entry["halt_prob"] = round(top1_halt, 4)
                # Mean halt across top-5 for diagnostics
                top5_halt = sorted(
                    zip(scores, halt_probs_list), key=lambda x: x[0], reverse=True
                )[:5]
                cycle_entry["halt_prob_top5_mean"] = round(
                    sum(h for _, h in top5_halt) / len(top5_halt), 4
                )

            cycle_log.append(cycle_entry)

            # Reformat scored for _categorize_scored_results
            best_scored = [
                (sc, s_c, s_r, s_i, s_ct, pt)
                for sc, (s_c, s_r, s_i, s_ct, pt) in scored
            ]

            # --- Halt decision ---
            should_halt = False

            if has_halt_head and halt_probs_list and cycle > 0:
                # Learned halt: top-1 candidate's halt_prob exceeds threshold
                top1_halt = halt_probs_list[top_idx]
                if top1_halt > halt_prob_threshold:
                    logger.info(
                        "Recursive search: halt head triggered at cycle %d "
                        "(halt_prob=%.3f > %.3f, top1=%s)",
                        cycle, top1_halt, halt_prob_threshold, top1_name,
                    )
                    should_halt = True
                # Safety net: also halt on convergence even if halt head disagrees
                elif top1_name == prev_top1_name:
                    logger.info(
                        "Recursive search: converged at cycle %d "
                        "(top1=%s unchanged, halt_prob=%.3f)",
                        cycle, top1_name, top1_halt,
                    )
                    should_halt = True

            elif is_dual:
                # Dual-head heuristic halt
                form_converged = (
                    margin > halt_margin
                    or form_top1_name == prev_top1_name
                )
                content_converged = (
                    content_top1_name == prev_content_top1_name
                    if prev_content_top1_name is not None
                    else False
                )
                if cycle > 0 and form_converged and content_converged:
                    logger.info(
                        "Recursive search converged at cycle %d: "
                        "form_top1=%s, content_top1=%s (both stable)",
                        cycle, form_top1_name, content_top1_name,
                    )
                    should_halt = True

            else:
                # Single-head heuristic halt
                if margin > halt_margin:
                    logger.info("Recursive search halted at cycle %d: margin %.4f > %.4f",
                                cycle, margin, halt_margin)
                    should_halt = True
                elif top1_name == prev_top1_name and cycle > 0:
                    logger.info("Recursive search converged at cycle %d: top1=%s unchanged",
                                cycle, top1_name)
                    should_halt = True

            if should_halt:
                break

            prev_top1_name = top1_name
            prev_content_top1_name = content_top1_name if (is_unified or is_dual) else None

            # --- Refine for next cycle using Qdrant RecommendQuery ---
            if cycle < max_cycles - 1:
                top_k = min(5, len(scored))
                top_ids = [pt.id for _, (_, _, _, _, pt) in scored[:top_k]]
                bottom_ids = [pt.id for _, (_, _, _, _, pt) in scored[-3:]] if len(scored) > 5 else []

                try:
                    from qdrant_client.models import (
                        FieldCondition,
                        Filter,
                        MatchValue,
                        RecommendInput,
                        RecommendQuery,
                        RecommendStrategy,
                    )
                    rec_prefetch = QdrantPrefetch(
                        query=RecommendQuery(
                            recommend=RecommendInput(
                                positive=top_ids,
                                negative=bottom_ids if bottom_ids else None,
                                strategy=RecommendStrategy.AVERAGE_VECTOR,
                            )
                        ),
                        using="components",
                        limit=candidate_pool_size,
                    )

                    # Content-aware RecommendQuery
                    content_rec_prefetch = None
                    if (
                        (is_unified or is_dual)
                        and query_content_minilm
                        and self._collection_has_content_vector()
                    ):
                        content_rec_prefetch = QdrantPrefetch(
                            query=query_content_minilm,
                            using="content",
                            limit=content_pool_size,
                            filter=Filter(must=[
                                FieldCondition(
                                    key="type",
                                    match=MatchValue(value="instance_pattern"),
                                ),
                            ]),
                        )

                    base_prefetch = self._build_prefetch_list(
                        query_colbert_orig, query_minilm_orig, candidate_pool_size,
                        include_classes, content_feedback, form_feedback,
                    )
                    combined_prefetch = [rec_prefetch] + base_prefetch
                    if content_rec_prefetch:
                        combined_prefetch.insert(1, content_rec_prefetch)

                    rec_results = self.client.query_points(
                        collection_name=self.collection_name,
                        prefetch=combined_prefetch,
                        query=FusionQuery(fusion=Fusion.RRF),
                        limit=candidate_pool_size * 3,
                        with_payload=True,
                        with_vectors=True,
                    )
                    logger.info(
                        "Recursive cycle %d: recommend prefetch with %d positive, %d negative, "
                        "content_recommend=%s -> %d candidates",
                        cycle + 1, len(top_ids), len(bottom_ids),
                        bool(content_rec_prefetch), len(rec_results.points),
                    )
                    _next_cycle_points = rec_results.points
                except Exception as e:
                    logger.debug("RecommendQuery prefetch failed (%s), falling back to vector blending", e)

                    # Fallback: manual vector blending
                    alpha = alpha_init * (0.9 ** cycle)
                    top_comp_vecs = []
                    for _, (_, _, _, _, pt) in scored[:top_k]:
                        vecs = pt.vector or {}
                        cv = vecs.get("components") if isinstance(vecs, dict) else None
                        if cv and isinstance(cv[0], list):
                            top_comp_vecs.append(np.mean(cv, axis=0).tolist())
                    if top_comp_vecs:
                        top_mean = np.mean(top_comp_vecs, axis=0)
                        refined = (alpha * np.array(query_colbert_orig[0]) + (1 - alpha) * top_mean).tolist()
                        query_colbert = [refined] + query_colbert_orig[1:]

        # Log cycle summary
        logger.info(
            "Recursive search completed (%s, halt_head=%s): %d cycles | %s",
            self._learned_model_type, has_halt_head, len(cycle_log), cycle_log,
        )

        if best_scored is None:
            return [], [], []

        # --- Categorize and return ---
        class_results, pattern_results, relationship_results = \
            self._categorize_scored_results(
                best_scored, limit,
                extra_fields={"recursive_cycles": len(cycle_log)},
            )

        logger.info(
            "Recursive search: %d classes, %d patterns, %d relationships (from %d cycles)",
            len(class_results), len(pattern_results),
            len(relationship_results), len(cycle_log),
        )

        return class_results, pattern_results, relationship_results

    except Exception as e:
        logger.error(f"Recursive search failed: {e}", exc_info=True)
        logger.info("Falling back to learned search")
        return self.search_hybrid_learned(
            description=description, component_paths=component_paths,
            limit=limit, token_ratio=token_ratio,
            content_feedback=content_feedback, form_feedback=form_feedback,
            include_classes=include_classes, candidate_pool_size=candidate_pool_size,
        )
