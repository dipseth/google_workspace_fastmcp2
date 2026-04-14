"""Recursive Vector Arithmetic engine for RIC embeddings.

Implements Option B from the TRM/MW analysis: iterative refinement
via vector operations on existing RIC embeddings, with no training required.

The core loop mirrors TRM's recursive process:
  z_H (components)     ↔ TRM's answer state
  z_L (relationships)  ↔ TRM's reasoning state
  x   (inputs)         ↔ TRM's input injection (constant)

Each cycle:
  1. Inject input context into component state: z_H' = norm(z_H + α·x)
  2. Search Qdrant with current states
  3. Cross-pollinate: z_L absorbs component matches, z_H absorbs relationship matches
  4. EMA smoothing to prevent drift
  5. Halt check: did top-K ranking stabilize?
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    ScoredPoint,
)

logger = logging.getLogger(__name__)


def normalize(v: np.ndarray) -> np.ndarray:
    """L2-normalize a vector. Returns zero vector if norm is 0."""
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-10 else v


@dataclass
class CycleInfo:
    """Diagnostic info for one refinement cycle."""

    cycle: int
    top_ids: list[int]
    comp_scores: list[float]
    rel_scores: list[float]
    inp_scores: list[float]
    z_H_drift: float  # distance from original z_H
    z_L_drift: float  # distance from original z_L


@dataclass
class SearchResult:
    """Result of a recursive RIC search."""

    top_ids: list[int]
    top_payloads: list[dict]
    rrf_scores: dict[int, float]
    cycles_used: int
    halted_early: bool
    cycle_history: list[CycleInfo] = field(default_factory=list)


def single_pass_search(
    client: QdrantClient,
    collection_name: str,
    z_H: np.ndarray,
    z_L: np.ndarray,
    x: np.ndarray,
    top_k: int = 5,
    rrf_k: int = 60,
) -> SearchResult:
    """Single-pass RIC search with RRF fusion (no recursion). Baseline."""
    comp_results = _search_vector(client, collection_name, z_H, "components", top_k)
    rel_results = _search_vector(client, collection_name, z_L, "relationships", top_k)
    inp_results = _search_vector(client, collection_name, x, "inputs", top_k)

    rrf_scores, payloads = _rrf_fuse(
        [comp_results, rel_results, inp_results], rrf_k, top_k
    )

    sorted_ids = sorted(rrf_scores.keys(), key=lambda i: rrf_scores[i], reverse=True)

    return SearchResult(
        top_ids=sorted_ids[:top_k],
        top_payloads=[payloads[i] for i in sorted_ids[:top_k] if i in payloads],
        rrf_scores=rrf_scores,
        cycles_used=1,
        halted_early=False,
    )


def multi_dimensional_search(
    client: QdrantClient,
    collection_name: str,
    z_H: np.ndarray,
    z_L: np.ndarray,
    x: np.ndarray,
    top_k: int = 5,
    candidate_pool: int = 20,
    scoring: str = "multiplicative",
) -> SearchResult:
    """Multi-dimensional reranking: expand candidates, score across ALL 3 dimensions.

    Unlike RRF (rank-based fusion), this computes actual cosine similarity
    of each candidate against the query on all 3 vectors, then combines.

    Args:
        scoring: "multiplicative" (product of similarities) or
                 "harmonic" (harmonic mean of similarities)
    """
    # Expand candidate pool
    comp_results = _search_vector(
        client,
        collection_name,
        z_H,
        "components",
        candidate_pool,
        with_vectors=True,
    )
    rel_results = _search_vector(
        client,
        collection_name,
        z_L,
        "relationships",
        candidate_pool,
        with_vectors=True,
    )
    inp_results = _search_vector(
        client,
        collection_name,
        x,
        "inputs",
        candidate_pool,
        with_vectors=True,
    )

    # Collect all unique candidates with their vectors
    candidates: dict[int, dict] = {}
    for results in [comp_results, rel_results, inp_results]:
        for point in results:
            if point.id not in candidates and point.vector:
                candidates[point.id] = {
                    "vector": point.vector,
                    "payload": point.payload,
                }

    # Score each candidate across all 3 dimensions
    scored: dict[int, float] = {}
    for pid, data in candidates.items():
        vec = data["vector"]
        if not isinstance(vec, dict):
            continue

        comp_vec = np.array(vec.get("components", []), dtype=np.float32)
        rel_vec = np.array(vec.get("relationships", []), dtype=np.float32)
        inp_vec = np.array(vec.get("inputs", []), dtype=np.float32)

        if comp_vec.size == 0 or rel_vec.size == 0 or inp_vec.size == 0:
            continue

        sim_c = _cosine_sim(z_H, comp_vec)
        sim_r = _cosine_sim(z_L, rel_vec)
        sim_i = _cosine_sim(x, inp_vec)

        if scoring == "multiplicative":
            # Product rewards consistency across all dimensions
            scored[pid] = max(0, sim_c) * max(0, sim_r) * max(0, sim_i)
        elif scoring == "harmonic":
            sims = [max(1e-10, s) for s in [sim_c, sim_r, sim_i]]
            scored[pid] = 3.0 / sum(1.0 / s for s in sims)
        else:
            scored[pid] = (sim_c + sim_r + sim_i) / 3.0

    sorted_ids = sorted(scored.keys(), key=lambda i: scored[i], reverse=True)
    payloads = {
        pid: data["payload"] for pid, data in candidates.items() if data["payload"]
    }

    return SearchResult(
        top_ids=sorted_ids[:top_k],
        top_payloads=[payloads[pid] for pid in sorted_ids[:top_k] if pid in payloads],
        rrf_scores=scored,
        cycles_used=1,
        halted_early=False,
    )


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def recursive_search(
    client: QdrantClient,
    collection_name: str,
    z_H: np.ndarray,
    z_L: np.ndarray,
    x: np.ndarray,
    max_cycles: int = 6,
    alpha: float = 0.3,
    beta: float = 0.3,
    ema_decay: float = 0.9,
    top_k: int = 5,
    rrf_k: int = 60,
    strategy: str = "best_match",
) -> SearchResult:
    """Recursive vector-arithmetic refinement over RIC embeddings.

    Args:
        client: Qdrant client
        collection_name: Collection to search
        z_H: Component state vector (384D) — "what IS the answer"
        z_L: Relationship state vector (384D) — "how things connect"
        x: Input context vector (384D) — constant, injected each cycle
        max_cycles: Maximum refinement iterations
        alpha: Input injection strength
        beta: Cross-pollination strength (step size toward target)
        ema_decay: Weight for new state vs original (prevents drift)
        top_k: Number of results per search
        rrf_k: RRF constant (dampens extreme ranks)
        strategy: Refinement strategy:
            - "centroid": Move toward centroid of cross-dimensional matches
            - "best_match": Move toward best cross-dimensional match (default)
            - "score_weighted": Score-weighted centroid of cross-dimensional matches
            - "consistency": Rerank by cross-dimensional consistency, use best as query

    Returns:
        SearchResult with fused rankings and diagnostic history
    """
    z_H_original = z_H.copy()
    z_L_original = z_L.copy()
    prev_top_ids: list[int] | None = None
    cycle_history: list[CycleInfo] = []

    # Track the latest results for final fusion
    comp_results: list[ScoredPoint] = []
    rel_results: list[ScoredPoint] = []
    inp_results: list[ScoredPoint] = []

    for cycle in range(max_cycles):
        # --- Step 1: Input injection ---
        z_H_injected = normalize(z_H + alpha * x)

        # --- Step 2: Search with current states ---
        comp_results = _search_vector(
            client,
            collection_name,
            z_H_injected,
            "components",
            top_k,
            with_vectors=True,
        )
        rel_results = _search_vector(
            client,
            collection_name,
            z_L,
            "relationships",
            top_k,
            with_vectors=True,
        )
        inp_results = _search_vector(
            client,
            collection_name,
            x,
            "inputs",
            top_k,
        )

        # --- Step 3: Refine states based on strategy ---
        z_H_new, z_L_new = _apply_strategy(
            strategy, z_H, z_L, comp_results, rel_results, beta
        )

        # --- Step 4: EMA smoothing (anchor to original) ---
        z_H = ema_decay * z_H_new + (1 - ema_decay) * z_H_original
        z_L = ema_decay * z_L_new + (1 - ema_decay) * z_L_original

        # --- Step 5: Diagnostics ---
        top_ids = [r.id for r in comp_results[:top_k]]
        z_H_drift = float(np.linalg.norm(z_H - z_H_original))
        z_L_drift = float(np.linalg.norm(z_L - z_L_original))

        cycle_info = CycleInfo(
            cycle=cycle,
            top_ids=top_ids,
            comp_scores=[r.score for r in comp_results[:top_k]],
            rel_scores=[r.score for r in rel_results[:top_k]],
            inp_scores=[r.score for r in inp_results[:top_k]],
            z_H_drift=z_H_drift,
            z_L_drift=z_L_drift,
        )
        cycle_history.append(cycle_info)

        # --- Step 6: Halt check ---
        if top_ids == prev_top_ids:
            logger.debug(f"Halted at cycle {cycle}: ranking stabilized")
            break
        prev_top_ids = top_ids

    # Final RRF fusion
    rrf_scores, payloads = _rrf_fuse(
        [comp_results, rel_results, inp_results], rrf_k, top_k
    )
    sorted_ids = sorted(rrf_scores.keys(), key=lambda i: rrf_scores[i], reverse=True)

    return SearchResult(
        top_ids=sorted_ids[:top_k],
        top_payloads=[payloads[i] for i in sorted_ids[:top_k] if i in payloads],
        rrf_scores=rrf_scores,
        cycles_used=cycle + 1 if cycle_history else 0,
        halted_early=(len(cycle_history) < max_cycles),
        cycle_history=cycle_history,
    )


# --- Refinement Strategies ---


def _apply_strategy(
    strategy: str,
    z_H: np.ndarray,
    z_L: np.ndarray,
    comp_results: list[ScoredPoint],
    rel_results: list[ScoredPoint],
    beta: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply a refinement strategy to update z_H and z_L.

    All strategies use cross-pollination: component search results
    inform relationship state, and vice versa.
    """
    if strategy == "centroid":
        return _strategy_centroid(z_H, z_L, comp_results, rel_results, beta)
    elif strategy == "best_match":
        return _strategy_best_match(z_H, z_L, comp_results, rel_results, beta)
    elif strategy == "score_weighted":
        return _strategy_score_weighted(z_H, z_L, comp_results, rel_results, beta)
    elif strategy == "consistency":
        return _strategy_consistency(z_H, z_L, comp_results, rel_results, beta)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


def _strategy_centroid(
    z_H: np.ndarray,
    z_L: np.ndarray,
    comp_results: list[ScoredPoint],
    rel_results: list[ScoredPoint],
    beta: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Original centroid cross-pollination. Moves toward mean of top-K."""
    rel_from_comp = _extract_named_vectors(comp_results, "relationships")
    comp_from_rel = _extract_named_vectors(rel_results, "components")

    z_L_new = z_L
    if rel_from_comp.size > 0:
        centroid = np.mean(rel_from_comp, axis=0)
        z_L_new = normalize(z_L + beta * centroid)

    z_H_new = z_H
    if comp_from_rel.size > 0:
        centroid = np.mean(comp_from_rel, axis=0)
        z_H_new = normalize(z_H + beta * centroid)

    return z_H_new, z_L_new


def _strategy_best_match(
    z_H: np.ndarray,
    z_L: np.ndarray,
    comp_results: list[ScoredPoint],
    rel_results: list[ScoredPoint],
    beta: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Move toward the top-1 cross-dimensional match (query by example).

    Instead of averaging all top-K (losing specificity), use only the
    single best match. This preserves the sharpness of the signal.
    """
    z_L_new = z_L
    if comp_results and comp_results[0].vector:
        vec = comp_results[0].vector
        if isinstance(vec, dict) and "relationships" in vec:
            target = np.array(vec["relationships"], dtype=np.float32)
            # Move z_L toward the relationship vector of the best component match
            z_L_new = normalize(z_L + beta * (target - z_L))

    z_H_new = z_H
    if rel_results and rel_results[0].vector:
        vec = rel_results[0].vector
        if isinstance(vec, dict) and "components" in vec:
            target = np.array(vec["components"], dtype=np.float32)
            # Move z_H toward the component vector of the best relationship match
            z_H_new = normalize(z_H + beta * (target - z_H))

    return z_H_new, z_L_new


def _strategy_score_weighted(
    z_H: np.ndarray,
    z_L: np.ndarray,
    comp_results: list[ScoredPoint],
    rel_results: list[ScoredPoint],
    beta: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Score-weighted cross-pollination. Higher-scoring matches contribute more."""
    z_L_new = z_L
    rel_vecs = _extract_named_vectors(comp_results, "relationships")
    if rel_vecs.size > 0:
        scores = np.array(
            [r.score for r in comp_results[: len(rel_vecs)]], dtype=np.float32
        )
        # Softmax-like weighting
        weights = np.exp(scores * 5)  # temperature=0.2
        weights /= weights.sum()
        weighted_centroid = np.average(rel_vecs, axis=0, weights=weights)
        z_L_new = normalize(z_L + beta * (weighted_centroid - z_L))

    z_H_new = z_H
    comp_vecs = _extract_named_vectors(rel_results, "components")
    if comp_vecs.size > 0:
        scores = np.array(
            [r.score for r in rel_results[: len(comp_vecs)]], dtype=np.float32
        )
        weights = np.exp(scores * 5)
        weights /= weights.sum()
        weighted_centroid = np.average(comp_vecs, axis=0, weights=weights)
        z_H_new = normalize(z_H + beta * (weighted_centroid - z_H))

    return z_H_new, z_L_new


def _strategy_consistency(
    z_H: np.ndarray,
    z_L: np.ndarray,
    comp_results: list[ScoredPoint],
    rel_results: list[ScoredPoint],
    beta: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Cross-dimensional consistency reranking.

    Find the point that appears in both component AND relationship results
    (cross-dimensional consistency), then use that point's vectors as the
    new query. If no overlap, fall back to best_match.
    """
    comp_ids = {r.id: r for r in comp_results}
    rel_ids = {r.id: r for r in rel_results}

    # Find overlapping points (appear in both searches)
    overlap = set(comp_ids.keys()) & set(rel_ids.keys())

    if overlap:
        # Score overlap by combined RRF-like rank
        best_id = None
        best_score = -1
        for pid in overlap:
            comp_rank = next(i for i, r in enumerate(comp_results) if r.id == pid)
            rel_rank = next(i for i, r in enumerate(rel_results) if r.id == pid)
            # Combined inverse rank
            score = 1 / (1 + comp_rank) + 1 / (1 + rel_rank)
            if score > best_score:
                best_score = score
                best_id = pid

        # Use this consistent point's vectors as targets
        consistent_point = comp_ids.get(best_id) or rel_ids.get(best_id)
        if consistent_point and consistent_point.vector:
            vec = consistent_point.vector
            if isinstance(vec, dict):
                if "components" in vec:
                    target = np.array(vec["components"], dtype=np.float32)
                    z_H = normalize(z_H + beta * (target - z_H))
                if "relationships" in vec:
                    target = np.array(vec["relationships"], dtype=np.float32)
                    z_L = normalize(z_L + beta * (target - z_L))
            return z_H, z_L

    # No overlap: fall back to best_match
    return _strategy_best_match(z_H, z_L, comp_results, rel_results, beta)


# --- Internal helpers ---


def _search_vector(
    client: QdrantClient,
    collection_name: str,
    vector: np.ndarray,
    vector_name: str,
    limit: int,
    with_vectors: bool = False,
    score_threshold: float | None = None,
) -> list[ScoredPoint]:
    """Search a specific named vector in the collection."""
    try:
        response = client.query_points(
            collection_name=collection_name,
            query=vector.tolist(),
            using=vector_name,
            limit=limit,
            with_vectors=with_vectors,
            with_payload=True,
            score_threshold=score_threshold,
        )
        return response.points
    except Exception as e:
        logger.error(f"Search failed on {vector_name}: {e}")
        return []


def _extract_named_vectors(
    points: list[ScoredPoint],
    vector_name: str,
) -> np.ndarray:
    """Extract a specific named vector from scored points.

    Returns shape (N, dim) or empty array if no vectors found.
    """
    vectors = []
    for p in points:
        if p.vector and isinstance(p.vector, dict) and vector_name in p.vector:
            vectors.append(np.array(p.vector[vector_name], dtype=np.float32))
    if vectors:
        return np.stack(vectors)
    return np.array([])


def _rrf_fuse(
    result_lists: list[list[ScoredPoint]],
    k: int = 60,
    limit: int = 10,
) -> tuple[dict[int, float], dict[int, dict]]:
    """Reciprocal Rank Fusion across multiple result lists.

    Returns:
        (rrf_scores, payloads) where rrf_scores maps point_id → score
        and payloads maps point_id → payload dict.
    """
    rrf_scores: dict[int, float] = {}
    payloads: dict[int, dict] = {}

    for results in result_lists:
        for rank, point in enumerate(results, start=1):
            pid = point.id
            rrf_scores[pid] = rrf_scores.get(pid, 0.0) + 1.0 / (k + rank)
            if pid not in payloads and point.payload:
                payloads[pid] = point.payload

    return rrf_scores, payloads
