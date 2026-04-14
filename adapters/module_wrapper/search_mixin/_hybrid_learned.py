"""Learned scorer hybrid search (supports UnifiedTRN, DualHead, and SingleHead)."""

from typing import Any, Dict, List, Optional, Tuple

from config.enhanced_logging import setup_logger

logger = setup_logger()


def search_hybrid_learned(
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
    Search using a trained learned scorer for reranking.

    Supports three model architectures (auto-detected):
      - UnifiedTRN: structural(17D) + content(384D) → form/content/halt heads
      - DualHeadScorerMW: features(17D) → form_score + content_score
      - SimilarityScorerMW: features(9D) → single score

    Same prefetch pipeline as search_hybrid_multidim, but replaces
    multiplicative scoring with a trained reranker.
    """
    if not self._require_qdrant("search_hybrid_learned"):
        return [], [], []

    try:
        import torch
    except ImportError:
        logger.warning("torch not installed, falling back to multidim")
        return self.search_hybrid_multidim(
            description=description,
            component_paths=component_paths,
            limit=limit,
            token_ratio=token_ratio,
            content_feedback=content_feedback,
            form_feedback=form_feedback,
            include_classes=include_classes,
            candidate_pool_size=candidate_pool_size,
            content_text=content_text,
        )

    # Load model with domain awareness
    wrapper_domain = getattr(
        getattr(self, "domain_config", None), "domain_label", None
    ) or getattr(self, "_domain_id", None)
    model = self._load_learned_model(domain=wrapper_domain)
    if model is None:
        logger.warning("Learned scorer not available, falling back to multidim")
        return self.search_hybrid_multidim(
            description=description,
            component_paths=component_paths,
            limit=limit,
            token_ratio=token_ratio,
            content_feedback=content_feedback,
            form_feedback=form_feedback,
            include_classes=include_classes,
            candidate_pool_size=candidate_pool_size,
            content_text=content_text,
        )

    # Domain mismatch guard: don't use a gchat model to score email components
    cls = type(self)
    model_domain = cls._learned_model_domain
    if model_domain and wrapper_domain and model_domain != wrapper_domain:
        logger.info(
            f"Learned scorer domain '{model_domain}' != wrapper domain "
            f"'{wrapper_domain}', falling back to multidim"
        )
        return self.search_hybrid_multidim(
            description=description,
            component_paths=component_paths,
            limit=limit,
            token_ratio=token_ratio,
            content_feedback=content_feedback,
            form_feedback=form_feedback,
            include_classes=include_classes,
            candidate_pool_size=candidate_pool_size,
            content_text=content_text,
        )

    try:
        # --- Step 1: Embed query ---
        query_colbert = self._embed_with_colbert(description, token_ratio)

        rel_text = description
        if component_paths:
            rel_text = f"{description} components: {', '.join(component_paths)}"

        query_minilm = self._embed_with_minilm(rel_text)

        if not query_colbert or not query_minilm:
            logger.warning("Could not embed query for learned search")
            return [], [], []

        # Embed content text if provided (same MiniLM model, 384D)
        query_content_minilm = None
        if content_text:
            query_content_minilm = self._embed_with_minilm(content_text)

        # --- Step 2: Grouped prefetch + query Qdrant ---
        points = self._query_grouped_candidates(
            query_colbert,
            query_minilm,
            candidate_pool_size,
            content_feedback=content_feedback,
            form_feedback=form_feedback,
            group_size=candidate_pool_size,
            query_content_minilm=query_content_minilm,
        )

        if not points:
            logger.info("Learned search: no candidates found")
            return [], [], []

        # --- Step 2.5: Infer component_paths for NL queries ---
        if not component_paths and self._learned_feature_version in (2, 3, 4, 5):
            component_paths = self._infer_component_paths(points)

        # --- Step 3: Compute features + scoring ---
        features_list, points_list = self._compute_learned_features(
            points,
            query_colbert,
            query_minilm,
            component_paths,
            query_content_minilm=query_content_minilm,
        )

        features_tensor = torch.tensor(features_list, dtype=torch.float32)
        is_unified = self._learned_model_type == "unified"
        is_dual = self._learned_model_type == "dual_head"

        with torch.no_grad():
            if is_unified:
                # UnifiedTRN: split features into structural(17D) + content(384D)
                # Content embedding = query MiniLM, broadcast to all candidates
                content_emb = (
                    query_content_minilm if query_content_minilm else query_minilm
                )
                content_tensor = torch.tensor(
                    [content_emb] * len(features_list), dtype=torch.float32
                )
                result = model(features_tensor, content_tensor, mode="search")
                form_scores = result["form_score"].squeeze(-1).tolist()
                content_scores = result["content_score"].squeeze(-1).tolist()
                # Alpha blend
                alpha = 1.0 if not content_text else 0.6
                try:
                    from config.settings import Settings as _S

                    alpha = _S().dual_head_form_weight
                except Exception:
                    pass
                learned_scores = [
                    alpha * f + (1 - alpha) * c
                    for f, c in zip(form_scores, content_scores)
                ]

            elif is_dual:
                form_t, content_t = model(features_tensor)
                form_scores = form_t.squeeze(-1).tolist()
                content_scores = content_t.squeeze(-1).tolist()
                alpha = 1.0 if not content_text else 0.6
                try:
                    from config.settings import Settings as _S

                    alpha = _S().dual_head_form_weight
                except Exception:
                    pass
                learned_scores = [
                    alpha * f + (1 - alpha) * c
                    for f, c in zip(form_scores, content_scores)
                ]

            else:
                scores_tensor = model(features_tensor).squeeze(-1)
                learned_scores = scores_tensor.tolist()
                form_scores = learned_scores
                content_scores = [0.0] * len(learned_scores)

        # Apply feedback boost
        scored = []
        for idx, (sim_c, sim_r, sim_i, sim_ct, point) in enumerate(points_list):
            score = learned_scores[idx]
            payload = point.payload or {}
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
            scored.append((score, sim_c, sim_r, sim_i, sim_ct, point))

        scored.sort(key=lambda x: x[0], reverse=True)

        # --- Step 3b: Per-candidate score logging (shadow A/B) ---
        try:
            from config.settings import Settings as _S

            if _S().search_shadow_scoring:
                import hashlib

                _qh = hashlib.md5(description.encode()).hexdigest()[:12]
                _top20 = [
                    {
                        "rank": i + 1,
                        "name": (p.payload or {}).get("name", "?"),
                        "score": round(sc, 4),
                        "sim_c": round(s_c, 4),
                    }
                    for i, (sc, s_c, _sr, _si, _sct, p) in enumerate(scored[:20])
                ]
                logger.info(
                    "Learned scorer candidates | query=%s | top20=%s", _qh, _top20
                )
        except Exception:
            pass

        # --- Step 4: Categorize and return ---
        class_results, pattern_results, relationship_results = (
            self._categorize_scored_results(scored, limit)
        )

        logger.info(
            "Learned search (%s): %d classes, %d patterns, %d relationships (from %d candidates)",
            self._learned_model_type,
            len(class_results),
            len(pattern_results),
            len(relationship_results),
            len(points),
        )

        return class_results, pattern_results, relationship_results

    except Exception as e:
        logger.error(f"Learned search failed: {e}", exc_info=True)
        logger.info("Falling back to multi-dimensional search")
        return self.search_hybrid_multidim(
            description=description,
            component_paths=component_paths,
            limit=limit,
            token_ratio=token_ratio,
            content_feedback=content_feedback,
            form_feedback=form_feedback,
            include_classes=include_classes,
            candidate_pool_size=candidate_pool_size,
        )
