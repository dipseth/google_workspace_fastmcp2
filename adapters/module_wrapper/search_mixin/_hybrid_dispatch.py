"""Hybrid search dispatch: routes to rrf, multidim, learned, or recursive search."""

import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple

from config.enhanced_logging import setup_logger

logger = setup_logger()


def search_hybrid_dispatch(
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
    Dispatch to search_hybrid, search_hybrid_multidim, or search_hybrid_learned.

    Reads SEARCH_MODE from settings:
      - 'rrf' (default): Qdrant's native RRF fusion
      - 'multidim': multiplicative cross-dimensional scoring (H1: +9.5%)
      - 'learned': trained SimilarityScorerMW MLP (H2: 100% val acc on MW)

    Falls back to ENABLE_MULTIDIM_SEARCH for backwards compatibility.
    Same signature as search_hybrid / search_hybrid_multidim / search_hybrid_learned.
    """
    search_mode = "rrf"
    settings = None
    try:
        from config.settings import Settings
        settings = Settings()
        search_mode = settings.search_mode
        # Backwards compat: ENABLE_MULTIDIM_SEARCH overrides if search_mode is default
        if search_mode == "rrf" and settings.enable_multidim_search:
            search_mode = "multidim"
    except Exception:
        pass

    try:
        from middleware.langfuse_integration import set_sampling_trace_context
        set_sampling_trace_context(search_mode=search_mode)
    except ImportError:
        pass

    # Map mode names to methods
    _search_methods = {
        "recursive": self.search_hybrid_recursive,
        "learned": self.search_hybrid_learned,
        "multidim": self.search_hybrid_multidim,
        "rrf": self.search_hybrid,
    }

    # Build common kwargs (rrf doesn't take candidate_pool_size)
    _common_kwargs = dict(
        description=description,
        component_paths=component_paths,
        limit=limit,
        token_ratio=token_ratio,
        content_feedback=content_feedback,
        form_feedback=form_feedback,
        include_classes=include_classes,
    )
    _pool_kwargs = {**_common_kwargs, "candidate_pool_size": candidate_pool_size}

    # Run active mode
    active_mode = search_mode if search_mode in _search_methods else "rrf"

    # content_text only supported by learned/recursive
    if content_text and active_mode in ("learned", "recursive"):
        _pool_kwargs["content_text"] = content_text
    logger.info("Using search mode: %s", active_mode)
    kwargs = _pool_kwargs if active_mode != "rrf" else _common_kwargs
    result = _search_methods[active_mode](**kwargs)

    # Shadow scoring: run other modes and log comparison
    shadow_enabled = False
    try:
        shadow_enabled = settings.search_shadow_scoring
    except Exception:
        pass

    if shadow_enabled:
        self._run_shadow_scoring(
            active_mode=active_mode,
            active_result=result,
            search_methods=_search_methods,
            common_kwargs=_common_kwargs,
            pool_kwargs=_pool_kwargs,
            description=description,
        )

    return result


def _run_shadow_scoring(
    self,
    active_mode: str,
    active_result: Tuple,
    search_methods: dict,
    common_kwargs: dict,
    pool_kwargs: dict,
    description: str,
) -> None:
    """Run non-active search modes as shadow and log comparison metrics."""
    query_hash = hashlib.md5(description.encode()).hexdigest()[:12]

    def _top5(result_tuple):
        """Extract top-5 names+scores from a search result tuple."""
        all_results = []
        for bucket in result_tuple:
            if bucket:
                all_results.extend(bucket)
        seen = set()
        deduped = []
        for r in all_results:
            name = r.get("name", "")
            if name not in seen:
                seen.add(name)
                deduped.append(r)
        deduped.sort(key=lambda x: x.get("score", 0), reverse=True)
        return [(r.get("name", "?"), round(r.get("score", 0), 4)) for r in deduped[:5]]

    active_top5 = _top5(active_result)
    active_names = {n for n, _ in active_top5}
    shadow_results = {}

    for mode_name, method in search_methods.items():
        if mode_name == active_mode:
            continue
        try:
            t0 = time.monotonic()
            kwargs = pool_kwargs if mode_name != "rrf" else common_kwargs
            shadow_result = method(**kwargs)
            elapsed_ms = round((time.monotonic() - t0) * 1000)
            top5 = _top5(shadow_result)
            shadow_names = {n for n, _ in top5}
            overlap = len(active_names & shadow_names)
            shadow_results[mode_name] = {
                "top5": top5,
                "overlap_with_active": overlap,
                "latency_ms": elapsed_ms,
            }
        except Exception as e:
            shadow_results[mode_name] = {"error": str(e)}

    # Log structured comparison
    logger.info(
        "Shadow A/B comparison | query=%s | active=%s | active_top5=%s | shadows=%s",
        query_hash,
        active_mode,
        active_top5,
        shadow_results,
    )
