"""Generate synthetic training data for the learned scorer.

Uses DAGStructureGenerator to create random valid card structures,
embeds them with ColBERT + MiniLM, and builds query groups with
ground-truth labels based on known component_paths.

Usage:
    cd /path/to/repo
    PYTHONPATH=. uv run python research/trm/h2/generate_training_data.py \
        --count 500 --variations 3 --output research/trm/h2/mw_synthetic_groups.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# Ensure project root is on path
_project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

# Fix macOS SSL certificate issue
try:
    import certifi
    if not os.environ.get("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = certifi.where()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class SyntheticPattern:
    """A generated card pattern with embeddings and metadata."""

    pattern_id: str
    component_paths: List[str]  # ground truth: which components this card uses
    dsl: str
    description: str  # natural language description of the card

    # Embeddings (computed after generation)
    comp_vectors: Optional[np.ndarray] = None  # ColBERT [N, 128]
    inp_vectors: Optional[np.ndarray] = None  # ColBERT [N, 128]
    rel_vector: Optional[np.ndarray] = None  # MiniLM [384]


@dataclass
class SyntheticGroup:
    """A query group with ground-truth labels."""

    query: SyntheticPattern
    candidate_names: List[str]
    candidate_comp_vectors: List[Optional[np.ndarray]]
    candidate_inp_vectors: List[Optional[np.ndarray]]
    candidate_rel_vectors: List[Optional[np.ndarray]]
    labels: List[float]


# ---------------------------------------------------------------------------
# Natural language description templates
# ---------------------------------------------------------------------------

DESCRIPTION_TEMPLATES = [
    "A card with {components}",
    "Build a {adj} card using {components}",
    "{adj} card: {components}",
    "Create a card that has {components}",
    "Card with {components} layout",
    "Display {components}",
    "Show {components} in a card",
    "{components} card design",
]

ADJECTIVES = [
    "simple", "clean", "modern", "compact", "interactive",
    "rich", "detailed", "minimal", "dynamic", "responsive",
]

COMPONENT_DESCRIPTIONS = {
    "Section": "a section",
    "DecoratedText": "decorated text",
    "TextParagraph": "text paragraph",
    "Button": "a button",
    "ButtonList": "buttons",
    "Image": "an image",
    "Divider": "a divider",
    "Grid": "a grid",
    "GridItem": "grid items",
    "Columns": "columns",
    "Column": "a column",
    "Carousel": "a carousel",
    "CarouselCard": "carousel cards",
    "ChipList": "chips",
    "Chip": "a chip",
    "DateTimePicker": "a date picker",
    "SelectionInput": "selection input",
    "TextInput": "text input",
    "SwitchControl": "a toggle switch",
    "NestedWidget": "nested content",
}


def describe_components(components: List[str]) -> str:
    """Generate a natural language description from component list."""
    # Count components
    counts: Dict[str, int] = {}
    for c in components:
        counts[c] = counts.get(c, 0) + 1

    parts = []
    for comp, count in counts.items():
        desc = COMPONENT_DESCRIPTIONS.get(comp, comp.lower())
        if count > 1:
            parts.append(f"{count} {desc}")
        else:
            parts.append(desc)

    if len(parts) <= 2:
        comp_text = " and ".join(parts)
    else:
        comp_text = ", ".join(parts[:-1]) + f", and {parts[-1]}"

    template = random.choice(DESCRIPTION_TEMPLATES)
    adj = random.choice(ADJECTIVES)
    return template.format(components=comp_text, adj=adj)


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------


def generate_structures(count: int, seed: int = 42) -> List[dict]:
    """Generate random valid card structures using DAGStructureGenerator."""
    random.seed(seed)

    from gchat.testing.dag_structure_generator import DAGStructureGenerator, DAGGeneratorConfig

    config = DAGGeneratorConfig(
        max_depth=3,
        max_children_per_node=5,
        min_children_per_node=1,
    )
    generator = DAGStructureGenerator(config)

    structures = []
    roots = ["Section"] * 8 + ["Carousel"] * 2  # 80% Section, 20% Carousel

    # Also generate with required components for diversity
    required_sets = [
        None,  # random
        ["DecoratedText"],
        ["ButtonList"],
        ["Grid"],
        ["DecoratedText", "ButtonList"],
        ["Image"],
        ["TextParagraph"],
        ["Columns"],
        ["DecoratedText", "Divider", "ButtonList"],
        ["ChipList"],
    ]

    for i in range(count):
        root = random.choice(roots)
        required = random.choice(required_sets)

        try:
            structure = generator.generate_random_structure(
                root=root,
                required_components=required,
            )
            if structure.is_valid:
                desc = describe_components(structure.components)
                structures.append({
                    "components": structure.components,
                    "dsl": structure.dsl,
                    "description": desc,
                    "tree": structure.tree,
                    "depth": structure.depth,
                })
        except Exception as e:
            logger.debug(f"Structure generation failed: {e}")
            continue

        if (i + 1) % 100 == 0:
            logger.info(f"Generated {i + 1}/{count} structures ({len(structures)} valid)")

    logger.info(f"Generated {len(structures)} valid structures from {count} attempts")
    return structures


def generate_variations(
    structures: List[dict],
    n_struct_variations: int = 3,
    n_param_variations: int = 2,
) -> List[dict]:
    """Generate structural and parameter variations of existing structures."""
    from adapters.module_wrapper.instance_pattern_mixin import (
        StructureVariator,
        ParameterVariator,
    )

    variator = StructureVariator()
    param_variator = ParameterVariator()
    all_structures = list(structures)  # include originals

    for struct in structures:
        # Structural variations
        try:
            for _ in range(n_struct_variations):
                variation = variator.generate_variations(
                    component_paths=struct["components"],
                    count=1,
                )
                if variation:
                    var = variation[0]
                    desc = describe_components(var.component_paths)
                    all_structures.append({
                        "components": var.component_paths,
                        "dsl": var.dsl_notation or struct["dsl"],
                        "description": desc,
                        "tree": struct["tree"],  # approximate
                        "depth": struct["depth"],
                    })
        except Exception as e:
            logger.debug(f"Structure variation failed: {e}")

    logger.info(
        f"Expanded {len(structures)} structures to {len(all_structures)} "
        f"(+{len(all_structures) - len(structures)} variations)"
    )
    return all_structures


def embed_patterns(
    structures: List[dict],
) -> List[SyntheticPattern]:
    """Embed all structures using ColBERT + MiniLM via EmbeddingService."""
    from config.embedding_service import EmbeddingService

    service = EmbeddingService()
    patterns = []

    for i, struct in enumerate(structures):
        desc = struct["description"]
        dsl = struct["dsl"]
        embed_text = f"{desc} {dsl}"

        try:
            # ColBERT multi-vector (returns List[List[float]])
            comp_vecs = service.embed_multivector_sync([embed_text])
            inp_vecs = service.embed_multivector_sync([dsl if dsl else desc])

            # MiniLM dense (returns List[float])
            rel_vec = service.embed_dense_sync([desc])

            comp_np = np.array(comp_vecs, dtype=np.float32) if comp_vecs else None
            inp_np = np.array(inp_vecs, dtype=np.float32) if inp_vecs else None
            rel_np = np.array(rel_vec, dtype=np.float32).flatten() if rel_vec else None

            if comp_np is not None and comp_np.ndim == 1:
                comp_np = comp_np.reshape(1, -1)
            if inp_np is not None and inp_np.ndim == 1:
                inp_np = inp_np.reshape(1, -1)

            patterns.append(SyntheticPattern(
                pattern_id=f"synthetic_{i:04d}",
                component_paths=struct["components"],
                dsl=dsl,
                description=desc,
                comp_vectors=comp_np,
                inp_vectors=inp_np,
                rel_vector=rel_np,
            ))
        except Exception as e:
            logger.warning(f"Embedding failed for pattern {i}: {e}")

        if (i + 1) % 100 == 0:
            logger.info(f"Embedded {i + 1}/{len(structures)} patterns")

    logger.info(f"Embedded {len(patterns)} patterns")
    return patterns


# ---------------------------------------------------------------------------
# Query group building with ground-truth labels
# ---------------------------------------------------------------------------


def maxsim_score(query_multi: np.ndarray, doc_multi: np.ndarray) -> float:
    """ColBERT MaxSim."""
    if query_multi is None or doc_multi is None:
        return 0.0
    if query_multi.size == 0 or doc_multi.size == 0:
        return 0.0
    q_norm = query_multi / (np.linalg.norm(query_multi, axis=1, keepdims=True) + 1e-10)
    d_norm = doc_multi / (np.linalg.norm(doc_multi, axis=1, keepdims=True) + 1e-10)
    sim_matrix = q_norm @ d_norm.T
    return float(sim_matrix.max(axis=1).mean())


def maxsim_decomposed(
    query_multi: np.ndarray, doc_multi: np.ndarray,
    coverage_threshold: float = 0.4,
) -> tuple:
    """ColBERT MaxSim decomposed into (mean, max, std, coverage).

    Returns 4 statistics from the per-query-token max-similarity vector.
    """
    if query_multi is None or doc_multi is None:
        return (0.0, 0.0, 0.0, 0.0)
    if query_multi.size == 0 or doc_multi.size == 0:
        return (0.0, 0.0, 0.0, 0.0)
    q_norm = query_multi / (np.linalg.norm(query_multi, axis=1, keepdims=True) + 1e-10)
    d_norm = doc_multi / (np.linalg.norm(doc_multi, axis=1, keepdims=True) + 1e-10)
    sim_matrix = q_norm @ d_norm.T
    per_token_max = sim_matrix.max(axis=1)  # shape: (n_query_tokens,)

    mean_val = float(per_token_max.mean())
    max_val = float(per_token_max.max())
    std_val = float(per_token_max.std())
    coverage_val = float((per_token_max > coverage_threshold).mean())

    return (mean_val, max_val, std_val, coverage_val)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Dense cosine similarity."""
    if a is None or b is None:
        return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-10 or nb < 1e-10:
        return 0.0
    return float(np.dot(a.flatten(), b.flatten()) / (na * nb))


def compute_features(query: SyntheticPattern, cand_comp, cand_inp, cand_rel) -> np.ndarray:
    """Compute 9 similarity features (legacy — kept for backward compat)."""
    sim_c = maxsim_score(query.comp_vectors, cand_comp)
    sim_i = maxsim_score(query.inp_vectors, cand_inp)
    sim_r = cosine_sim(query.rel_vector, cand_rel)

    q_c_norm = float(np.linalg.norm(query.comp_vectors)) if query.comp_vectors is not None else 0.0
    q_i_norm = float(np.linalg.norm(query.inp_vectors)) if query.inp_vectors is not None else 0.0
    q_r_norm = float(np.linalg.norm(query.rel_vector)) if query.rel_vector is not None else 0.0
    c_c_norm = float(np.linalg.norm(cand_comp)) if cand_comp is not None else 0.0
    c_i_norm = float(np.linalg.norm(cand_inp)) if cand_inp is not None else 0.0
    c_r_norm = float(np.linalg.norm(cand_rel)) if cand_rel is not None else 0.0

    return np.array([sim_c, sim_i, sim_r, q_c_norm, q_i_norm, q_r_norm, c_c_norm, c_i_norm, c_r_norm], dtype=np.float32)


# ---------------------------------------------------------------------------
# V2 features: structural hierarchy + similarities (no norms)
# ---------------------------------------------------------------------------

# Lazy-loaded DAG data
_dag_children: dict = {}
_dag_parents: dict = {}
_dag_depth: dict = {}
_dag_loaded = False


def _load_dag():
    """Load component DAG from the wrapper for structural features."""
    global _dag_children, _dag_parents, _dag_depth, _dag_loaded
    if _dag_loaded:
        return

    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        wrapper = get_card_framework_wrapper()

        # Build parent/child maps from the wrapper's graph
        # Use _name_to_idx keys (component_names may be empty for loaded collections)
        all_names = list(wrapper._name_to_idx.keys()) if hasattr(wrapper, '_name_to_idx') else []
        if not all_names:
            all_names = list(wrapper.component_names) if hasattr(wrapper, 'component_names') else []
        logger.info(f"Building DAG from {len(all_names)} components")
        for comp_name in all_names:
            _dag_children[comp_name] = set(wrapper.get_children(comp_name))
            _dag_parents[comp_name] = set(wrapper.get_parents(comp_name))

        # Compute depth for each node (BFS from roots)
        roots = [n for n in all_names if not _dag_parents.get(n)]
        if not roots:
            # Fallback: use nodes with fewest parents
            roots = [n for n in all_names if len(_dag_parents.get(n, set())) <= 1]
        visited = {}
        queue = [(r, 0) for r in roots]
        while queue:
            node, depth = queue.pop(0)
            if node in visited:
                continue
            visited[node] = depth
            for child in _dag_children.get(node, []):
                queue.append((child, depth + 1))
        _dag_depth = visited

        _dag_loaded = True
        logger.info(f"Loaded DAG: {len(_dag_children)} components, max depth={max(_dag_depth.values()) if _dag_depth else 0}")
    except Exception as e:
        logger.warning(f"Could not load DAG: {e}")
        _dag_loaded = True  # prevent retries


def _get_ancestors(name: str) -> set:
    """Get all ancestors of a component in the DAG."""
    ancestors = set()
    queue = list(_dag_parents.get(name, []))
    while queue:
        p = queue.pop(0)
        if p not in ancestors:
            ancestors.add(p)
            queue.extend(_dag_parents.get(p, []))
    return ancestors


FEATURE_NAMES_V2 = [
    "sim_components", "sim_inputs", "sim_relationships",
    "is_parent", "is_child", "is_sibling",
    "depth_ratio", "n_shared_ancestors",
]


def compute_features_v2(
    query: SyntheticPattern,
    cand_comp, cand_inp, cand_rel,
    cand_name: str,
) -> np.ndarray:
    """Compute V2 features: 3 similarities + 5 structural (no norms).

    Replaces norm features with hierarchy-aware structural features
    to prevent shortcut learning via embedding magnitude fingerprinting.
    """
    _load_dag()

    # Similarities (same as V1)
    sim_c = maxsim_score(query.comp_vectors, cand_comp)
    sim_i = maxsim_score(query.inp_vectors, cand_inp)
    sim_r = cosine_sim(query.rel_vector, cand_rel)

    # Structural features from DAG
    query_components = set(query.component_paths)

    # Is candidate a parent container of any query component?
    is_parent = 0.0
    cand_children = _dag_children.get(cand_name, set())
    if cand_children & query_components:
        is_parent = 1.0

    # Is candidate a child of any query component?
    is_child = 0.0
    cand_parents = _dag_parents.get(cand_name, set())
    if cand_parents & query_components:
        is_child = 1.0

    # Does candidate share a parent with any query component? (sibling)
    is_sibling = 0.0
    for qc in query_components:
        qc_parents = _dag_parents.get(qc, set())
        if qc_parents & cand_parents:
            is_sibling = 1.0
            break

    # Depth ratio (0.0 = root, 1.0 = deepest leaf)
    max_depth = max(_dag_depth.values()) if _dag_depth else 1
    cand_depth = _dag_depth.get(cand_name, 0)
    depth_ratio = cand_depth / max_depth if max_depth > 0 else 0.0

    # Number of shared ancestors between candidate and query components
    cand_ancestors = _get_ancestors(cand_name)
    query_ancestors = set()
    for qc in query_components:
        query_ancestors.update(_get_ancestors(qc))
    n_shared = len(cand_ancestors & query_ancestors)
    # Normalize by total unique ancestors to keep in [0, 1]
    total_ancestors = len(cand_ancestors | query_ancestors) if (cand_ancestors or query_ancestors) else 1
    n_shared_ratio = n_shared / total_ancestors

    return np.array([
        sim_c, sim_i, sim_r,
        is_parent, is_child, is_sibling,
        depth_ratio, n_shared_ratio,
    ], dtype=np.float32)


# ---------------------------------------------------------------------------
# V3 features: decomposed MaxSim + structural (no norms)
# ---------------------------------------------------------------------------

FEATURE_NAMES_V3 = [
    "sim_c_mean", "sim_c_max", "sim_c_std", "sim_c_coverage",
    "sim_i_mean", "sim_i_max", "sim_i_std", "sim_i_coverage",
    "sim_relationships",
    "is_parent", "is_child", "is_sibling",
    "depth_ratio", "n_shared_ancestors",
]


def compute_features_v3(
    query: SyntheticPattern,
    cand_comp, cand_inp, cand_rel,
    cand_name: str,
) -> np.ndarray:
    """Compute V3 features: decomposed ColBERT MaxSim (4 stats each) + structural.

    Decomposes MaxSim into (mean, max, std, coverage) per ColBERT vector,
    giving the model distributional information about token-level matching.
    - std distinguishes peaked structural matches from broad semantic alignment
    - coverage measures what fraction of query tokens found a good match
    """
    _load_dag()

    # Decomposed ColBERT similarities
    sim_c_mean, sim_c_max, sim_c_std, sim_c_cov = maxsim_decomposed(
        query.comp_vectors, cand_comp
    )
    sim_i_mean, sim_i_max, sim_i_std, sim_i_cov = maxsim_decomposed(
        query.inp_vectors, cand_inp
    )

    # Dense semantic similarity (unchanged)
    sim_r = cosine_sim(query.rel_vector, cand_rel)

    # Structural features (identical to V2)
    query_components = set(query.component_paths)

    is_parent = 0.0
    cand_children = _dag_children.get(cand_name, set())
    if cand_children & query_components:
        is_parent = 1.0

    is_child = 0.0
    cand_parents = _dag_parents.get(cand_name, set())
    if cand_parents & query_components:
        is_child = 1.0

    is_sibling = 0.0
    for qc in query_components:
        qc_parents = _dag_parents.get(qc, set())
        if qc_parents & cand_parents:
            is_sibling = 1.0
            break

    max_depth = max(_dag_depth.values()) if _dag_depth else 1
    cand_depth = _dag_depth.get(cand_name, 0)
    depth_ratio = cand_depth / max_depth if max_depth > 0 else 0.0

    cand_ancestors = _get_ancestors(cand_name)
    query_ancestors = set()
    for qc in query_components:
        query_ancestors.update(_get_ancestors(qc))
    n_shared = len(cand_ancestors & query_ancestors)
    total_ancestors = len(cand_ancestors | query_ancestors) if (cand_ancestors or query_ancestors) else 1
    n_shared_ratio = n_shared / total_ancestors

    return np.array([
        sim_c_mean, sim_c_max, sim_c_std, sim_c_cov,
        sim_i_mean, sim_i_max, sim_i_std, sim_i_cov,
        sim_r,
        is_parent, is_child, is_sibling,
        depth_ratio, n_shared_ratio,
    ], dtype=np.float32)


def extract_class_points(client, collection: str, limit: int = 500):
    """Extract class points from Qdrant for use as candidates."""
    points = []
    offset = None

    while True:
        from qdrant_client import models
        batch, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="type", match=models.MatchValue(value="class"))]
            ),
            limit=min(limit, 100),
            offset=offset,
            with_vectors=True,
            with_payload=True,
        )

        for p in batch:
            payload = p.payload or {}
            vectors = p.vector or {}
            comp_raw = vectors.get("components")
            inp_raw = vectors.get("inputs")
            rel_raw = vectors.get("relationships")

            comp_vec = np.array(comp_raw, dtype=np.float32) if comp_raw else None
            inp_vec = np.array(inp_raw, dtype=np.float32) if inp_raw else None
            rel_vec = np.array(rel_raw, dtype=np.float32) if rel_raw else None

            if comp_vec is not None and comp_vec.ndim == 1:
                comp_vec = comp_vec.reshape(1, -1)
            if inp_vec is not None and inp_vec.ndim == 1:
                inp_vec = inp_vec.reshape(1, -1)

            points.append({
                "name": payload.get("name", ""),
                "full_path": payload.get("full_path", ""),
                "comp_vectors": comp_vec,
                "inp_vectors": inp_vec,
                "rel_vector": rel_vec,
            })

        if next_offset is None or len(points) >= limit:
            break
        offset = next_offset

    logger.info(f"Extracted {len(points)} class points from Qdrant")
    return points


def build_synthetic_groups(
    patterns: List[SyntheticPattern],
    class_points: List[dict],
    top_k: int = 20,
    n_random: int = 5,
    feature_version: int = 2,
) -> List[dict]:
    """Build query groups with ground-truth labels.

    For each synthetic pattern:
    - Score against all class points by component similarity
    - Take top-K + N random (hard + easy negatives)
    - Label = 1.0 if class name is in pattern's component_paths
    """
    groups = []
    unique_components = set()
    for p in patterns:
        unique_components.update(p.component_paths)

    for i, query in enumerate(patterns):
        if not query.comp_vectors is not None:
            continue

        # Score all class points
        scored = []
        for cp in class_points:
            if cp["comp_vectors"] is None:
                continue
            sim_c = maxsim_score(query.comp_vectors, cp["comp_vectors"])
            scored.append((cp, sim_c))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Top-K by similarity (hard negatives + true positives)
        top_candidates = [c for c, _ in scored[:top_k]]

        # Add random candidates (easy negatives)
        remaining = [c for c, _ in scored[top_k:]]
        if remaining:
            n_rand = min(n_random, len(remaining))
            random_cands = random.sample(remaining, n_rand)
            top_candidates.extend(random_cands)

        # Ground-truth labels
        query_components = set(query.component_paths)
        labels = []
        has_positive = False
        for cand in top_candidates:
            cand_name = cand["name"]
            # Label is positive if this class is used in the card
            if cand_name in query_components:
                labels.append(1.0)
                has_positive = True
            else:
                labels.append(0.0)

        if has_positive and len(top_candidates) >= 2:
            # Compute features for JSON export
            if feature_version == 3:
                feat_fn = compute_features_v3
                feat_names = FEATURE_NAMES_V3
            else:
                feat_fn = compute_features_v2
                feat_names = FEATURE_NAMES_V2

            candidates_data = []
            for cand, label in zip(top_candidates, labels):
                feats = feat_fn(
                    query, cand["comp_vectors"], cand["inp_vectors"],
                    cand["rel_vector"], cand["name"],
                )
                cand_data = {
                    "name": cand["name"],
                    "full_path": cand["full_path"],
                    "label": label,
                }
                for fname, fval in zip(feat_names, feats):
                    cand_data[fname] = round(float(fval), 4)
                candidates_data.append(cand_data)

            groups.append({
                "query_id": query.pattern_id,
                "query_description": query.description,
                "query_dsl": query.dsl,
                "query_components": query.component_paths,
                "n_candidates": len(candidates_data),
                "n_positive": sum(1 for c in candidates_data if c["label"] == 1.0),
                "candidates": candidates_data,
            })

        if (i + 1) % 100 == 0:
            logger.info(f"Built groups for {i + 1}/{len(patterns)} patterns ({len(groups)} groups)")

    logger.info(f"Built {len(groups)} synthetic groups")
    if groups:
        pos_rates = [g["n_positive"] / g["n_candidates"] for g in groups]
        logger.info(f"  Positive rate: mean={np.mean(pos_rates):.3f}, median={np.median(pos_rates):.3f}")

    return groups


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic training data for learned scorer")
    parser.add_argument("--count", type=int, default=500, help="Number of random structures to generate")
    parser.add_argument("--variations", type=int, default=3, help="Structural variations per pattern")
    parser.add_argument("--top-k", type=int, default=20, help="Top-K candidates per query")
    parser.add_argument("--n-random", type=int, default=5, help="Random negatives per query")
    parser.add_argument("--collection", default="mcp_gchat_cards_v8", help="Qdrant collection for class points")
    parser.add_argument("--output", default=str(Path(__file__).parent / "mw_synthetic_groups.json"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-variations", action="store_true", help="Skip variation generation")
    parser.add_argument("--skip-embed", action="store_true", help="Skip embedding (use pre-computed)")
    parser.add_argument("--feature-version", type=int, default=2, choices=[2, 3],
                        help="Feature version: 2=V2 (8 features), 3=V3 (14 decomposed)")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    # Step 1: Generate random valid structures
    logger.info(f"=== Step 1: Generating {args.count} random card structures ===")
    structures = generate_structures(args.count, args.seed)

    if not structures:
        logger.error("No valid structures generated")
        return

    # Step 2: Generate variations
    if not args.skip_variations:
        logger.info(f"\n=== Step 2: Generating {args.variations} variations per structure ===")
        try:
            structures = generate_variations(structures, n_struct_variations=args.variations)
        except Exception as e:
            logger.warning(f"Variation generation failed (continuing with originals): {e}")

    # Step 3: Embed all patterns
    logger.info(f"\n=== Step 3: Embedding {len(structures)} patterns ===")
    patterns = embed_patterns(structures)

    if not patterns:
        logger.error("No patterns embedded successfully")
        return

    # Step 4: Extract class points from Qdrant
    logger.info(f"\n=== Step 4: Extracting class points from Qdrant ===")
    from research.trm.h2.mw_extract import connect_qdrant
    client = connect_qdrant()
    class_points = extract_class_points(client, args.collection)

    if not class_points:
        logger.error("No class points found in Qdrant")
        return

    # Step 5: Build query groups with ground-truth labels
    fv = args.feature_version
    logger.info(f"\n=== Step 5: Building query groups (feature_version={fv}) ===")
    groups = build_synthetic_groups(patterns, class_points, args.top_k, args.n_random, feature_version=fv)

    # Override output path for V3
    if fv == 3 and args.output == str(Path(__file__).parent / "mw_synthetic_groups.json"):
        args.output = str(Path(__file__).parent / "mw_synthetic_groups_v3.json")

    if not groups:
        logger.error("No groups built")
        return

    # Save
    output_path = Path(args.output)
    output_path.write_text(json.dumps(groups, indent=2))
    logger.info(f"\nSaved {len(groups)} groups to {output_path}")

    # Summary
    total_candidates = sum(g["n_candidates"] for g in groups)
    total_positive = sum(g["n_positive"] for g in groups)
    unique_queries = len(set(g["query_dsl"] for g in groups))
    logger.info(f"\n{'='*60}")
    logger.info(f"SYNTHETIC DATA SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Structures generated: {len(structures)}")
    logger.info(f"Patterns embedded:    {len(patterns)}")
    logger.info(f"Query groups:         {len(groups)}")
    logger.info(f"Unique DSL patterns:  {unique_queries}")
    logger.info(f"Total candidates:     {total_candidates}")
    logger.info(f"Total positives:      {total_positive}")
    logger.info(f"Positive rate:        {total_positive/total_candidates:.1%}")
    logger.info(f"Output:               {output_path}")


if __name__ == "__main__":
    main()
