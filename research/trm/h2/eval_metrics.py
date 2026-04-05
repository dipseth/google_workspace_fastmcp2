"""Search evaluation metrics for TRM pipeline diagnostics.

Provides precision@K, recall@K, MRR, and NDCG for evaluating ranked
search results. Used by:
  - Diagnostic UI backend (ml_eval.py endpoints)
  - E2E pipeline tests

All functions accept lists of ranked results and relevance labels.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Union


def precision_at_k(
    ranked_relevant: Sequence[bool],
    k: int,
) -> float:
    """Precision@K: fraction of top-K results that are relevant.

    Args:
        ranked_relevant: Boolean sequence, True if result at that rank is relevant.
        k: Number of top results to consider.

    Returns:
        Precision value in [0.0, 1.0].
    """
    if k <= 0:
        return 0.0
    top_k = ranked_relevant[:k]
    if not top_k:
        return 0.0
    return sum(1 for r in top_k if r) / k


def recall_at_k(
    ranked_relevant: Sequence[bool],
    k: int,
    total_relevant: Optional[int] = None,
) -> float:
    """Recall@K: fraction of all relevant items found in top-K.

    Args:
        ranked_relevant: Boolean sequence, True if result at that rank is relevant.
        k: Number of top results to consider.
        total_relevant: Total number of relevant items. If None, counts from
            the full ranked_relevant sequence.

    Returns:
        Recall value in [0.0, 1.0].
    """
    if total_relevant is None:
        total_relevant = sum(1 for r in ranked_relevant if r)
    if total_relevant == 0:
        return 0.0
    top_k = ranked_relevant[:k]
    found = sum(1 for r in top_k if r)
    return found / total_relevant


def mrr(ranked_relevant_lists: Sequence[Sequence[bool]]) -> float:
    """Mean Reciprocal Rank across multiple queries.

    Args:
        ranked_relevant_lists: List of ranked_relevant sequences,
            one per query.

    Returns:
        MRR value in [0.0, 1.0].
    """
    if not ranked_relevant_lists:
        return 0.0
    total_rr = 0.0
    for ranked_relevant in ranked_relevant_lists:
        for i, is_rel in enumerate(ranked_relevant):
            if is_rel:
                total_rr += 1.0 / (i + 1)
                break
    return total_rr / len(ranked_relevant_lists)


def reciprocal_rank(ranked_relevant: Sequence[bool]) -> float:
    """Reciprocal rank for a single query.

    Args:
        ranked_relevant: Boolean sequence for one query.

    Returns:
        1/rank of first relevant result, or 0.0 if none found.
    """
    for i, is_rel in enumerate(ranked_relevant):
        if is_rel:
            return 1.0 / (i + 1)
    return 0.0


def dcg_at_k(
    relevance_scores: Sequence[Union[int, float]],
    k: int,
) -> float:
    """Discounted Cumulative Gain at K.

    Args:
        relevance_scores: Graded relevance scores in ranked order.
        k: Number of top results to consider.

    Returns:
        DCG value (non-negative).
    """
    dcg = 0.0
    for i, rel in enumerate(relevance_scores[:k]):
        dcg += rel / math.log2(i + 2)  # i+2 because log2(1) = 0
    return dcg


def ndcg_at_k(
    relevance_scores: Sequence[Union[int, float]],
    k: int,
) -> float:
    """Normalized DCG at K.

    Args:
        relevance_scores: Graded relevance scores in ranked order.
        k: Number of top results to consider.

    Returns:
        NDCG value in [0.0, 1.0].
    """
    actual_dcg = dcg_at_k(relevance_scores, k)
    ideal_scores = sorted(relevance_scores, reverse=True)
    ideal_dcg = dcg_at_k(ideal_scores, k)
    if ideal_dcg == 0.0:
        return 0.0
    return actual_dcg / ideal_dcg


def evaluate_ranked_results(
    ranked_relevant_lists: Sequence[Sequence[bool]],
    k_values: Sequence[int] = (1, 3, 5, 10),
) -> Dict[str, float]:
    """Compute a full evaluation report across multiple queries.

    Args:
        ranked_relevant_lists: List of ranked_relevant sequences, one per query.
        k_values: K values for precision@K and recall@K.

    Returns:
        Dict with keys like "precision@1", "recall@5", "mrr", etc.
    """
    results: Dict[str, float] = {}

    for k in k_values:
        p_scores = [precision_at_k(rr, k) for rr in ranked_relevant_lists]
        r_scores = [recall_at_k(rr, k) for rr in ranked_relevant_lists]
        results[f"precision@{k}"] = (
            sum(p_scores) / len(p_scores) if p_scores else 0.0
        )
        results[f"recall@{k}"] = (
            sum(r_scores) / len(r_scores) if r_scores else 0.0
        )

    results["mrr"] = mrr(ranked_relevant_lists)
    results["num_queries"] = float(len(ranked_relevant_lists))

    return results
