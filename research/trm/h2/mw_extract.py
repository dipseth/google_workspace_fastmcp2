"""Extract training data from Module Wrapper's Qdrant collections.

Connects to the production/cloud Qdrant, retrieves component points and
instance patterns with feedback, and builds training groups for the
SimilarityScorer adapted to MW's mixed-dimension RIC schema.

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.mw_extract --collection mcp_gchat_cards
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class MWPoint:
    """A point from the MW Qdrant collection with all vectors + metadata."""

    point_id: str
    point_type: str  # "class" or "instance_pattern"
    name: str
    full_path: str
    symbol: str

    # Vectors (as numpy arrays)
    comp_vectors: np.ndarray | None  # ColBERT multi-vector [N, 128]
    inp_vectors: np.ndarray | None  # ColBERT multi-vector [M, 128]
    rel_vector: np.ndarray | None  # MiniLM dense [384]
    content_vector: np.ndarray | None = (
        None  # MiniLM dense [384] (content embedding, V5+)
    )

    # Feedback (instance patterns only)
    content_feedback: str | None = None  # "positive", "negative", None
    form_feedback: str | None = None

    # Metadata
    docstring: str = ""
    parent_paths: list[str] = field(default_factory=list)
    card_description: str = ""
    dsl_notation: str = ""
    instance_params: dict = field(default_factory=dict)
    has_content_vector: bool = False  # True if content vector is non-zero


@dataclass
class MWQueryGroup:
    """A query point with K candidates for listwise training.

    Label: candidates with the same component type/path as the query
    (for class points) or positive feedback (for instance patterns).

    content_labels: optional dual-label for content-form affinity (V5+).
    """

    query: MWPoint
    candidates: list[MWPoint]
    labels: list[float]  # 1.0 = relevant, 0.0 = not (form labels)
    content_labels: list[float] = field(default_factory=list)


def connect_qdrant(url: str | None = None, key: str | None = None):
    """Connect to Qdrant (cloud or local)."""
    from qdrant_client import QdrantClient

    url = url or os.environ.get("QDRANT_URL")
    key = key or os.environ.get("QDRANT_KEY")

    if url:
        client = QdrantClient(url=url, api_key=key, timeout=30)
        logger.info(f"Connected to Qdrant: {url[:50]}...")
    else:
        client = QdrantClient(location=":memory:")
        logger.info("Qdrant: in-memory (no URL provided)")

    return client


def extract_all_points(client, collection: str, limit: int = 500) -> list[MWPoint]:
    """Scroll through collection and extract all points with vectors."""
    from qdrant_client.models import ScrollRequest

    points = []
    offset = None

    while True:
        result = client.scroll(
            collection_name=collection,
            limit=min(limit, 100),
            offset=offset,
            with_vectors=True,
            with_payload=True,
        )

        batch, next_offset = result

        for p in batch:
            payload = p.payload or {}
            vectors = p.vector or {}

            # Extract ColBERT multi-vectors and MiniLM dense vectors
            comp_raw = vectors.get("components")
            inp_raw = vectors.get("inputs")
            rel_raw = vectors.get("relationships")
            content_raw = vectors.get("content")

            comp_vec = (
                np.array(comp_raw, dtype=np.float32) if comp_raw is not None else None
            )
            inp_vec = (
                np.array(inp_raw, dtype=np.float32) if inp_raw is not None else None
            )
            rel_vec = (
                np.array(rel_raw, dtype=np.float32) if rel_raw is not None else None
            )
            content_vec = (
                np.array(content_raw, dtype=np.float32)
                if content_raw is not None
                else None
            )

            # Ensure comp/inp are 2D (multi-vector)
            if comp_vec is not None and comp_vec.ndim == 1:
                comp_vec = comp_vec.reshape(1, -1)
            if inp_vec is not None and inp_vec.ndim == 1:
                inp_vec = inp_vec.reshape(1, -1)

            # Detect non-zero content vector
            has_content = payload.get("has_content_vector", False) or (
                content_vec is not None and float(np.linalg.norm(content_vec)) > 1e-6
            )

            points.append(
                MWPoint(
                    point_id=str(p.id),
                    point_type=payload.get("type", "unknown"),
                    name=payload.get("name", ""),
                    full_path=payload.get("full_path", ""),
                    symbol=payload.get("symbol", ""),
                    comp_vectors=comp_vec,
                    inp_vectors=inp_vec,
                    rel_vector=rel_vec,
                    content_vector=content_vec,
                    content_feedback=payload.get("content_feedback"),
                    form_feedback=payload.get("form_feedback"),
                    docstring=payload.get("docstring", "")[:200],
                    parent_paths=payload.get("parent_paths", []),
                    card_description=payload.get("card_description", ""),
                    dsl_notation=payload.get(
                        "relationship_text", payload.get("dsl_notation", "")
                    ),
                    instance_params=payload.get("instance_params", {}),
                    has_content_vector=has_content,
                )
            )

        if next_offset is None or len(points) >= limit:
            break
        offset = next_offset

    logger.info(f"Extracted {len(points)} points from '{collection}'")

    # Summary
    types = {}
    for p in points:
        types[p.point_type] = types.get(p.point_type, 0) + 1
    n_with_content = sum(1 for p in points if p.has_content_vector)
    for t, n in sorted(types.items()):
        feedback_info = ""
        if t == "instance_pattern":
            pos = sum(
                1
                for p in points
                if p.point_type == t and p.content_feedback == "positive"
            )
            neg = sum(
                1
                for p in points
                if p.point_type == t and p.content_feedback == "negative"
            )
            t_content = sum(
                1 for p in points if p.point_type == t and p.has_content_vector
            )
            feedback_info = f" (content: {pos}+ / {neg}-, content_vec: {t_content})"
        logger.info(f"  {t}: {n}{feedback_info}")
    logger.info(f"  Points with content vector: {n_with_content}/{len(points)}")

    return points


def maxsim_score(query_multi: np.ndarray, doc_multi: np.ndarray) -> float:
    """ColBERT MaxSim: for each query token, max similarity to any doc token.

    query_multi: [Q, 128], doc_multi: [D, 128]
    Returns: mean of max similarities across query tokens.
    """
    if query_multi is None or doc_multi is None:
        return 0.0
    if query_multi.size == 0 or doc_multi.size == 0:
        return 0.0

    # Normalize
    q_norm = query_multi / (np.linalg.norm(query_multi, axis=1, keepdims=True) + 1e-10)
    d_norm = doc_multi / (np.linalg.norm(doc_multi, axis=1, keepdims=True) + 1e-10)

    # Similarity matrix: [Q, D]
    sim_matrix = q_norm @ d_norm.T

    # MaxSim: for each query token, take max over doc tokens, then mean
    return float(sim_matrix.max(axis=1).mean())


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Dense cosine similarity."""
    if a is None or b is None:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-10 or nb < 1e-10:
        return 0.0
    return float(np.dot(a.flatten(), b.flatten()) / (na * nb))


def build_query_groups(
    points: list[MWPoint],
    top_k: int = 20,
) -> list[MWQueryGroup]:
    """Build training groups by using each point as a query and finding candidates.

    For class points: candidates are other class points, label = same full_path
    For instance patterns: candidates are class points, label = path in parent_paths
    """
    class_points = [
        p for p in points if p.point_type == "class" and p.comp_vectors is not None
    ]
    pattern_points = [
        p
        for p in points
        if p.point_type == "instance_pattern" and p.comp_vectors is not None
    ]

    logger.info(
        f"Building groups: {len(class_points)} classes, {len(pattern_points)} patterns"
    )

    groups = []

    # Strategy 1: Instance patterns as queries, class points as candidates
    # Label: does the class appear in the pattern's parent_paths?
    for query in pattern_points:
        if not query.parent_paths:
            continue

        # Score all class points against this query
        scored = []
        for cand in class_points:
            sim_c = maxsim_score(query.comp_vectors, cand.comp_vectors)
            scored.append((cand, sim_c))

        # Take top-K by component similarity
        scored.sort(key=lambda x: x[1], reverse=True)
        candidates = [c for c, _ in scored[:top_k]]

        # Label: is this class in the pattern's parent_paths?
        labels = []
        has_positive = False
        for cand in candidates:
            if cand.full_path in query.parent_paths or cand.name in [
                pp.split(".")[-1] for pp in query.parent_paths
            ]:
                labels.append(1.0)
                has_positive = True
            else:
                labels.append(0.0)

        if has_positive and len(candidates) >= 2:
            groups.append(
                MWQueryGroup(query=query, candidates=candidates, labels=labels)
            )

    # Strategy 2: Class points as queries, other class points as candidates
    # Label: same component name (for augmentation)
    for i, query in enumerate(class_points):
        scored = []
        for j, cand in enumerate(class_points):
            if i == j:
                continue
            sim_c = maxsim_score(query.comp_vectors, cand.comp_vectors)
            scored.append((cand, sim_c))

        scored.sort(key=lambda x: x[1], reverse=True)
        candidates = [c for c, _ in scored[:top_k]]

        labels = [1.0 if c.name == query.name else 0.0 for c in candidates]
        has_positive = any(v == 1.0 for v in labels)

        if has_positive and len(candidates) >= 2:
            groups.append(
                MWQueryGroup(query=query, candidates=candidates, labels=labels)
            )

    logger.info(f"Built {len(groups)} query groups")
    pos_rates = [sum(g.labels) / len(g.labels) for g in groups]
    if pos_rates:
        logger.info(
            f"  Positive rate: mean={np.mean(pos_rates):.3f}, median={np.median(pos_rates):.3f}"
        )

    return groups


def compute_similarity_features(query: MWPoint, candidate: MWPoint) -> np.ndarray:
    """Compute similarity features between query and candidate for MW schema.

    Returns feature vector matching what SimilarityScorerMW expects:
      - MaxSim(components): ColBERT late interaction
      - MaxSim(inputs): ColBERT late interaction
      - cosine(relationships): MiniLM dense similarity
      - query/candidate vector norms (6 features)
      Total: 9 features
    """
    sim_c = maxsim_score(query.comp_vectors, candidate.comp_vectors)
    sim_i = maxsim_score(query.inp_vectors, candidate.inp_vectors)
    sim_r = cosine_sim(query.rel_vector, candidate.rel_vector)

    # Norms
    q_comp_norm = (
        float(np.linalg.norm(query.comp_vectors))
        if query.comp_vectors is not None
        else 0.0
    )
    q_inp_norm = (
        float(np.linalg.norm(query.inp_vectors))
        if query.inp_vectors is not None
        else 0.0
    )
    q_rel_norm = (
        float(np.linalg.norm(query.rel_vector)) if query.rel_vector is not None else 0.0
    )
    c_comp_norm = (
        float(np.linalg.norm(candidate.comp_vectors))
        if candidate.comp_vectors is not None
        else 0.0
    )
    c_inp_norm = (
        float(np.linalg.norm(candidate.inp_vectors))
        if candidate.inp_vectors is not None
        else 0.0
    )
    c_rel_norm = (
        float(np.linalg.norm(candidate.rel_vector))
        if candidate.rel_vector is not None
        else 0.0
    )

    return np.array(
        [
            sim_c,
            sim_i,
            sim_r,
            q_comp_norm,
            q_inp_norm,
            q_rel_norm,
            c_comp_norm,
            c_inp_norm,
            c_rel_norm,
        ],
        dtype=np.float32,
    )


def groups_to_json(groups: list[MWQueryGroup], output_path: str):
    """Save groups with precomputed features to JSON for inspection."""
    data = []
    for g in groups:
        cands = []
        for c, label in zip(g.candidates, g.labels):
            feats = compute_similarity_features(g.query, c)
            cands.append(
                {
                    "name": c.name,
                    "full_path": c.full_path,
                    "symbol": c.symbol,
                    "label": label,
                    "sim_components": round(float(feats[0]), 4),
                    "sim_inputs": round(float(feats[1]), 4),
                    "sim_relationships": round(float(feats[2]), 4),
                }
            )
        data.append(
            {
                "query_name": g.query.name,
                "query_type": g.query.point_type,
                "query_path": g.query.full_path,
                "query_dsl": g.query.dsl_notation[:100] if g.query.dsl_notation else "",
                "n_candidates": len(cands),
                "n_positive": sum(1 for c in cands if c["label"] == 1.0),
                "candidates": cands,
            }
        )

    Path(output_path).write_text(json.dumps(data, indent=2))
    logger.info(f"Saved {len(data)} groups to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Extract MW training data from Qdrant")
    parser.add_argument("--collection", default="mcp_gchat_cards")
    parser.add_argument("--limit", type=int, default=500, help="Max points to extract")
    parser.add_argument("--top-k", type=int, default=20, help="Candidates per query")
    parser.add_argument(
        "--output", default=str(Path(__file__).parent / "mw_groups.json")
    )
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--qdrant-key", default=None)
    args = parser.parse_args()

    client = connect_qdrant(args.qdrant_url, args.qdrant_key)

    # List collections
    collections = client.get_collections().collections
    logger.info(f"Available collections: {[c.name for c in collections]}")

    # Extract points
    points = extract_all_points(client, args.collection, args.limit)

    if not points:
        logger.error(f"No points found in '{args.collection}'")
        return

    # Show similarity distribution (this is what we want to be wider than Mancala's 0.99+)
    class_points = [
        p for p in points if p.point_type == "class" and p.comp_vectors is not None
    ]
    if len(class_points) >= 2:
        sims = []
        import random

        random.seed(42)
        sample = random.sample(class_points, min(50, len(class_points)))
        for i, a in enumerate(sample):
            for b in sample[i + 1 :]:
                sims.append(maxsim_score(a.comp_vectors, b.comp_vectors))
        logger.info(f"\nComponent similarity distribution ({len(sims)} pairs):")
        logger.info(f"  Mean: {np.mean(sims):.4f}")
        logger.info(f"  Std:  {np.std(sims):.4f}")
        logger.info(f"  Min:  {np.min(sims):.4f}, Max: {np.max(sims):.4f}")
        logger.info(f"  (Mancala was 0.99+ — we want wider spread here)")

    # Build query groups
    groups = build_query_groups(points, args.top_k)

    # Save for inspection
    if groups:
        groups_to_json(groups, args.output)

    # Summary
    logger.info(f"\n{'=' * 60}")
    logger.info(f"EXTRACTION SUMMARY")
    logger.info(f"{'=' * 60}")
    logger.info(f"Collection: {args.collection}")
    logger.info(f"Total points: {len(points)}")
    logger.info(f"Query groups: {len(groups)}")
    if groups:
        logger.info(f"Ready for training with SimilarityScorerMW")
    else:
        logger.info(f"No groups — collection may be empty or lack instance patterns")


if __name__ == "__main__":
    main()
