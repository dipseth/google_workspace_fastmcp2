"""Result processing utilities: RRF merging."""

from typing import Any, Dict, List

from config.enhanced_logging import setup_logger

logger = setup_logger()


def _merge_results_rrf(
    self,
    result_lists: List[List[Dict[str, Any]]],
    k: int = 60,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Merge multiple result lists using Reciprocal Rank Fusion.

    RRF formula: score = sum(1 / (k + rank)) across all lists

    This is useful when combining results from different search strategies
    (e.g., vector search + text search + symbol lookup).

    Args:
        result_lists: List of result lists to merge
        k: RRF constant (default 60, higher = more weight to lower ranks)
        limit: Maximum results to return

    Returns:
        Merged and re-ranked results
    """
    # Track RRF scores by result ID
    rrf_scores: Dict[str, float] = {}
    result_by_id: Dict[str, Dict[str, Any]] = {}

    for results in result_lists:
        for rank, result in enumerate(results, start=1):
            # Use id or full_path as unique identifier
            result_id = str(result.get("id") or result.get("full_path") or rank)

            # Calculate RRF contribution
            rrf_scores[result_id] = rrf_scores.get(result_id, 0) + 1 / (k + rank)

            # Store the result (keep first occurrence)
            if result_id not in result_by_id:
                result_by_id[result_id] = result

    # Sort by RRF score descending
    sorted_ids = sorted(
        rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True
    )

    # Build final results
    merged = []
    for result_id in sorted_ids[:limit]:
        result = result_by_id[result_id].copy()
        result["rrf_score"] = rrf_scores[result_id]
        merged.append(result)

    logger.debug(
        f"RRF merged {sum(len(r) for r in result_lists)} results into {len(merged)}"
    )
    return merged
