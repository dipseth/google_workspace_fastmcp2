"""Pure math scoring functions for search result ranking."""

import math
from typing import List


def _maxsim(query_vecs: List[List[float]], doc_vecs: List[List[float]]) -> float:
    """ColBERT MaxSim: for each query token, find max cosine sim to any doc token.

    This implements ColBERT's "late interaction" scoring. The final score is
    the mean over query tokens of the max similarity to any document token.

    Args:
        query_vecs: List of query token embeddings (ColBERT multi-vector)
        doc_vecs: List of document token embeddings (ColBERT multi-vector)

    Returns:
        MaxSim score (0.0 to 1.0 range for normalized vectors)
    """
    if not query_vecs or not doc_vecs:
        return 0.0

    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    scores = []
    for q in query_vecs:
        best = max(_cosine(q, d) for d in doc_vecs)
        scores.append(best)
    return sum(scores) / len(scores)


def _maxsim_decomposed(
    query_vecs: List[List[float]],
    doc_vecs: List[List[float]],
    coverage_threshold: float = 0.4,
) -> tuple:
    """ColBERT MaxSim decomposed into (mean, max, std, coverage).

    Returns 4 statistics from the per-query-token max-similarity vector,
    giving the model distributional information about how tokens match.

    - mean: average token alignment (= standard MaxSim)
    - max: peak single-token match
    - std: matching consistency (low=uniform/semantic, high=peaked/structural)
    - coverage: fraction of query tokens with max_sim > coverage_threshold

    Args:
        query_vecs: List of query token embeddings (ColBERT multi-vector)
        doc_vecs: List of document token embeddings (ColBERT multi-vector)
        coverage_threshold: min similarity for a token to count as "covered"

    Returns:
        Tuple of (mean, max, std, coverage) floats
    """
    if not query_vecs or not doc_vecs:
        return (0.0, 0.0, 0.0, 0.0)

    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    per_token_max = []
    for q in query_vecs:
        best = max(_cosine(q, d) for d in doc_vecs)
        per_token_max.append(best)

    n = len(per_token_max)
    mean_val = sum(per_token_max) / n
    max_val = max(per_token_max)

    # Std deviation
    variance = sum((x - mean_val) ** 2 for x in per_token_max) / n
    std_val = math.sqrt(variance)

    # Coverage: fraction of tokens above threshold
    covered = sum(1 for x in per_token_max if x > coverage_threshold)
    coverage_val = covered / n

    return (mean_val, max_val, std_val, coverage_val)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two dense vectors.

    Args:
        a: First vector
        b: Second vector

    Returns:
        Cosine similarity (-1.0 to 1.0)
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
