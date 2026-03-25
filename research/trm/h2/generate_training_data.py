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

    # Content (V5+)
    content_text: str = ""  # generated content text for this pattern
    content_vector: Optional[np.ndarray] = None  # MiniLM [384] embedding of content_text


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
    generate_content: bool = False,
) -> List[SyntheticPattern]:
    """Embed all structures using ColBERT + MiniLM via EmbeddingService.

    Args:
        structures: List of generated structures with components, dsl, description.
        generate_content: If True, generate synthetic content text and embed it (V5+).
    """
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

            # Content text + embedding (V5+)
            content_text = ""
            content_np = None
            if generate_content:
                content_text = _generate_content_text_for_components(
                    struct["components"]
                )
                if content_text:
                    content_vec = service.embed_dense_sync([content_text])
                    content_np = (
                        np.array(content_vec, dtype=np.float32).flatten()
                        if content_vec
                        else None
                    )

            patterns.append(SyntheticPattern(
                pattern_id=f"synthetic_{i:04d}",
                component_paths=struct["components"],
                dsl=dsl,
                description=desc,
                comp_vectors=comp_np,
                inp_vectors=inp_np,
                rel_vector=rel_np,
                content_text=content_text,
                content_vector=content_np,
            ))
        except Exception as e:
            logger.warning(f"Embedding failed for pattern {i}: {e}")

        if (i + 1) % 100 == 0:
            logger.info(f"Embedded {i + 1}/{len(structures)} patterns")

    logger.info(f"Embedded {len(patterns)} patterns")
    if generate_content:
        n_with_content = sum(1 for p in patterns if p.content_text)
        logger.info(f"  {n_with_content}/{len(patterns)} patterns have content text")
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


# ---------------------------------------------------------------------------
# V5 features: V3 + content features (17D) for dual-head model
# ---------------------------------------------------------------------------

FEATURE_NAMES_V5 = FEATURE_NAMES_V3 + [
    "sim_content",
    "content_density",
    "content_form_alignment",
]

# Content affinity profiles: what kind of content each component naturally carries
CONTENT_AFFINITY: Dict[str, Dict[str, Any]] = {
    "ButtonList": {
        "patterns": ["submit", "deploy", "restart", "cancel", "approve", "reject",
                      "send", "save", "delete", "confirm", "run", "stop", "retry",
                      "update", "refresh", "download", "upload", "connect"],
        "type": "action",
    },
    "Button": {
        "patterns": ["submit", "deploy", "restart", "cancel", "approve", "reject",
                      "send", "save", "delete", "ok", "go", "start"],
        "type": "action",
    },
    "DecoratedText": {
        "patterns": ["status", "info", "details", "label", "name", "email",
                      "description", "version", "type", "state", "count",
                      "total", "last updated", "created", "owner"],
        "type": "display",
    },
    "TextParagraph": {
        "patterns": ["message", "description", "note", "warning", "error",
                      "summary", "explanation", "instructions", "help"],
        "type": "narrative",
    },
    "Grid": {
        "patterns": ["list", "items", "products", "results", "files", "users",
                      "servers", "services", "resources", "entries"],
        "type": "tabular",
    },
    "GridItem": {
        "patterns": ["item", "product", "file", "user", "server", "result"],
        "type": "tabular",
    },
    "Image": {
        "patterns": ["photo", "screenshot", "banner", "logo", "avatar",
                      "chart", "graph", "diagram", "icon"],
        "type": "media",
    },
    "ChipList": {
        "patterns": ["tag", "label", "category", "filter", "option",
                      "skill", "topic", "status"],
        "type": "categorical",
    },
    "Chip": {
        "patterns": ["tag", "label", "category", "filter", "option"],
        "type": "categorical",
    },
    "SelectionInput": {
        "patterns": ["choose", "select", "pick", "option", "preference",
                      "setting", "mode", "type"],
        "type": "input",
    },
    "TextInput": {
        "patterns": ["enter", "type", "search", "name", "email", "url",
                      "comment", "note", "message"],
        "type": "input",
    },
    "DateTimePicker": {
        "patterns": ["date", "time", "schedule", "deadline", "start",
                      "end", "due", "appointment"],
        "type": "temporal",
    },
    "SwitchControl": {
        "patterns": ["enable", "disable", "toggle", "on", "off",
                      "active", "notifications", "auto"],
        "type": "toggle",
    },
    "Columns": {
        "patterns": ["compare", "side by side", "left", "right",
                      "details", "summary"],
        "type": "layout",
    },
    "Carousel": {
        "patterns": ["slides", "gallery", "pages", "steps", "cards"],
        "type": "sequential",
    },
    "CarouselCard": {
        "patterns": ["slide", "page", "step", "card", "panel"],
        "type": "sequential",
    },
    "Divider": {
        "patterns": [],
        "type": "structural",
    },
    "Section": {
        "patterns": [],
        "type": "structural",
    },
}

# Content text templates per component type — realistic user content
CONTENT_TEXT_TEMPLATES: Dict[str, List[str]] = {
    "ButtonList": [
        "Deploy Service, Rollback, View Logs",
        "Approve Request, Deny Request",
        "Start Pipeline, Stop Pipeline, View Status",
        "Submit Form, Cancel",
        "Restart Server, Check Health, View Metrics",
        "Save Changes, Discard",
        "Connect, Disconnect, Refresh",
        "Download Report, Export CSV",
        "Run Tests, Deploy to Staging, Deploy to Production",
        "Enable Feature, Disable Feature",
    ],
    "Button": [
        "Submit", "Deploy", "Approve", "Cancel", "Restart",
        "Send", "Save", "Delete", "Confirm", "Retry",
    ],
    "DecoratedText": [
        "Status: Online, Version: 2.4.1, Last Updated: 2 hours ago",
        "Name: API Gateway, Type: Service, Region: us-west-2",
        "Owner: platform-team, Priority: High, State: Active",
        "CPU: 45%, Memory: 2.1GB, Uptime: 14 days",
        "Email: admin@company.com, Role: Administrator",
        "Total Requests: 1.2M, Error Rate: 0.03%",
        "Created: March 15, Modified: March 20",
        "Build: #1847, Branch: main, Commit: a3f2b1c",
        "Latency P99: 120ms, Throughput: 5K rps",
        "License: Enterprise, Seats: 50/100, Expires: 2027-01-01",
    ],
    "TextParagraph": [
        "The deployment completed successfully. All health checks passed.",
        "Warning: This action cannot be undone. Please confirm.",
        "Pipeline failed at stage 3: unit tests. See logs for details.",
        "Welcome to the dashboard. Select a service to view metrics.",
        "Note: Maintenance window scheduled for Saturday 2am-4am UTC.",
    ],
    "Grid": [
        "web-server-01, web-server-02, web-server-03, db-primary, db-replica",
        "index.html, styles.css, app.js, config.json, README.md",
        "Alice Johnson, Bob Smith, Carol Williams, David Brown",
        "US West, US East, EU Central, AP Southeast",
        "v1.0.0, v1.1.0, v1.2.0, v2.0.0-beta",
    ],
    "GridItem": [
        "web-server-01", "database-primary", "cache-node-1",
        "api-gateway", "load-balancer", "worker-queue",
    ],
    "Image": [
        "Architecture Diagram", "Performance Chart", "Team Photo",
        "System Dashboard Screenshot", "Logo", "Error Screenshot",
    ],
    "ChipList": [
        "Python, JavaScript, Go, Rust, TypeScript",
        "Bug, Feature, Enhancement, Documentation, Security",
        "High Priority, Medium Priority, Low Priority",
        "Active, Inactive, Pending, Archived",
        "Frontend, Backend, DevOps, QA, Design",
    ],
    "Chip": [
        "Python", "Bug", "High Priority", "Active", "Frontend",
    ],
    "SelectionInput": [
        "Select region: US West, US East, EU, APAC",
        "Choose environment: Development, Staging, Production",
        "Select priority: Critical, High, Medium, Low",
    ],
    "TextInput": [
        "Enter service name", "Search users", "Add comment",
        "Enter email address", "Type your message",
    ],
    "DateTimePicker": [
        "Schedule deployment", "Set deadline", "Pick start date",
        "Choose maintenance window", "Select meeting time",
    ],
    "SwitchControl": [
        "Enable notifications", "Auto-scaling", "Debug mode",
        "Maintenance mode", "Feature flag: dark-theme",
    ],
    "Columns": [
        "Current vs Previous, Before and After, Plan vs Actual",
    ],
    "Carousel": [
        "Step 1: Configure, Step 2: Deploy, Step 3: Verify",
        "Overview, Details, Metrics, Logs",
    ],
    "CarouselCard": [
        "Configuration Panel", "Deployment Status", "Metric Dashboard",
    ],
}


def _generate_content_text_for_components(component_paths: List[str]) -> str:
    """Generate realistic content text for a set of components.

    Picks content templates matching the component types present
    in the pattern and concatenates them.
    """
    texts = []
    seen_types = set()

    for comp in component_paths:
        if comp in seen_types:
            continue
        seen_types.add(comp)

        templates = CONTENT_TEXT_TEMPLATES.get(comp, [])
        if templates:
            texts.append(random.choice(templates))

    return ", ".join(texts) if texts else ""


def compute_content_label(
    content_text: str,
    candidate_name: str,
    min_matches: int = 1,
) -> float:
    """Compute content affinity label for a candidate component.

    Returns 1.0 if the query's content text contains patterns that match
    the candidate component's content affinity profile (at least min_matches).

    Args:
        content_text: The query's content text (generated or real).
        candidate_name: Component name (e.g., "ButtonList").
        min_matches: Minimum number of affinity patterns that must match.
    """
    if not content_text:
        return 0.0

    affinity = CONTENT_AFFINITY.get(candidate_name)
    if not affinity or not affinity["patterns"]:
        return 0.0

    content_lower = content_text.lower()
    patterns = affinity["patterns"]
    matches = sum(1 for p in patterns if p in content_lower)

    return 1.0 if matches >= min_matches else 0.0


def compute_features_v5(
    query: "SyntheticPattern",
    cand_comp,
    cand_inp,
    cand_rel,
    cand_name: str,
    query_content_vector: Optional[np.ndarray] = None,
    cand_content_vector: Optional[np.ndarray] = None,
    cand_has_content: bool = False,
    cand_n_content_fields: int = 0,
    cand_total_content_fields: int = 5,
) -> np.ndarray:
    """Compute V5 features: V3 (14D) + 3 content features = 17D.

    New features:
      - sim_content: cosine(query_content, candidate_content) — 0.0 if candidate has no content
      - content_density: ratio of non-empty content fields in candidate
      - content_form_alignment: cosine(query_content, candidate_relationship_vector)
    """
    # V3 base features (14D)
    v3_feats = compute_features_v3(query, cand_comp, cand_inp, cand_rel, cand_name)

    # sim_content: query content vs candidate content
    sim_content = cosine_sim(query_content_vector, cand_content_vector) if cand_has_content else 0.0

    # content_density: fraction of content fields populated
    content_density = (
        cand_n_content_fields / cand_total_content_fields
        if cand_total_content_fields > 0
        else 0.0
    )

    # content_form_alignment: query content vs candidate relationship vector
    content_form_alignment = cosine_sim(query_content_vector, cand_rel) if query_content_vector is not None else 0.0

    return np.concatenate([
        v3_feats,
        np.array([sim_content, content_density, content_form_alignment], dtype=np.float32),
    ])


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
            content_raw = vectors.get("content")

            comp_vec = np.array(comp_raw, dtype=np.float32) if comp_raw else None
            inp_vec = np.array(inp_raw, dtype=np.float32) if inp_raw else None
            rel_vec = np.array(rel_raw, dtype=np.float32) if rel_raw else None
            content_vec = np.array(content_raw, dtype=np.float32) if content_raw else None

            if comp_vec is not None and comp_vec.ndim == 1:
                comp_vec = comp_vec.reshape(1, -1)
            if inp_vec is not None and inp_vec.ndim == 1:
                inp_vec = inp_vec.reshape(1, -1)

            has_content = (
                payload.get("has_content_vector", False)
                or (content_vec is not None and float(np.linalg.norm(content_vec)) > 1e-6)
            )

            points.append({
                "name": payload.get("name", ""),
                "full_path": payload.get("full_path", ""),
                "comp_vectors": comp_vec,
                "inp_vectors": inp_vec,
                "rel_vector": rel_vec,
                "content_vector": content_vec,
                "has_content_vector": has_content,
            })

        if next_offset is None or len(points) >= limit:
            break
        offset = next_offset

    n_with_content = sum(1 for p in points if p["has_content_vector"])
    logger.info(f"Extracted {len(points)} class points from Qdrant ({n_with_content} with content)")
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
            if feature_version == 5:
                feat_names = FEATURE_NAMES_V5
            elif feature_version == 3 or feature_version == 4:
                feat_names = FEATURE_NAMES_V3
            else:
                feat_names = FEATURE_NAMES_V2

            candidates_data = []
            for cand, label in zip(top_candidates, labels):
                if feature_version == 5:
                    # V5: compute content-aware features
                    cand_content_vec = cand.get("content_vector")
                    cand_has_content = cand.get("has_content_vector", False)
                    feats = compute_features_v5(
                        query, cand["comp_vectors"], cand["inp_vectors"],
                        cand["rel_vector"], cand["name"],
                        query_content_vector=query.content_vector,
                        cand_content_vector=cand_content_vec,
                        cand_has_content=cand_has_content,
                        # Class points have no content fields
                        cand_n_content_fields=0,
                        cand_total_content_fields=5,
                    )
                elif feature_version == 3 or feature_version == 4:
                    feats = compute_features_v3(
                        query, cand["comp_vectors"], cand["inp_vectors"],
                        cand["rel_vector"], cand["name"],
                    )
                else:
                    feats = compute_features_v2(
                        query, cand["comp_vectors"], cand["inp_vectors"],
                        cand["rel_vector"], cand["name"],
                    )

                cand_data = {
                    "name": cand["name"],
                    "full_path": cand["full_path"],
                }

                if feature_version == 5:
                    # Dual labels: form_label + content_label
                    cand_data["form_label"] = label
                    cand_data["content_label"] = compute_content_label(
                        query.content_text, cand["name"]
                    )
                else:
                    cand_data["label"] = label

                for fname, fval in zip(feat_names, feats):
                    cand_data[fname] = round(float(fval), 4)
                candidates_data.append(cand_data)

            group_data = {
                "query_id": query.pattern_id,
                "query_description": query.description,
                "query_dsl": query.dsl,
                "query_components": query.component_paths,
                "n_candidates": len(candidates_data),
                "n_positive": sum(
                    1 for c in candidates_data
                    if c.get("form_label", c.get("label", 0.0)) == 1.0
                ),
                "candidates": candidates_data,
            }
            if feature_version == 5:
                group_data["content_text"] = query.content_text
                group_data["n_content_positive"] = sum(
                    1 for c in candidates_data if c.get("content_label", 0.0) == 1.0
                )
            groups.append(group_data)

        if (i + 1) % 100 == 0:
            logger.info(f"Built groups for {i + 1}/{len(patterns)} patterns ({len(groups)} groups)")

    logger.info(f"Built {len(groups)} synthetic groups")
    if groups:
        pos_rates = [g["n_positive"] / g["n_candidates"] for g in groups]
        logger.info(f"  Positive rate: mean={np.mean(pos_rates):.3f}, median={np.median(pos_rates):.3f}")

    return groups


# ---------------------------------------------------------------------------
# Email domain support
# ---------------------------------------------------------------------------

# Email component hierarchy (from gmail/email_wrapper_setup.py)
EMAIL_CONTAINERS = {
    "EmailSpec": ["HeroBlock", "TextBlock", "ButtonBlock", "ImageBlock",
                  "ColumnsBlock", "SpacerBlock", "DividerBlock", "FooterBlock",
                  "HeaderBlock", "SocialBlock", "TableBlock", "AccordionBlock",
                  "CarouselBlock"],
    "ColumnsBlock": ["Column"],
    "Column": ["TextBlock", "ButtonBlock", "ImageBlock", "SpacerBlock", "DividerBlock"],
}

EMAIL_COMPONENT_DESCRIPTIONS = {
    "EmailSpec": "an email",
    "HeroBlock": "a hero banner",
    "TextBlock": "text content",
    "ButtonBlock": "a call-to-action button",
    "ImageBlock": "an image",
    "ColumnsBlock": "multi-column layout",
    "Column": "a column",
    "SpacerBlock": "spacing",
    "DividerBlock": "a divider",
    "FooterBlock": "a footer",
    "HeaderBlock": "a header",
    "SocialBlock": "social links",
    "TableBlock": "a data table",
    "AccordionBlock": "expandable sections",
    "CarouselBlock": "an image carousel",
}

EMAIL_DESCRIPTION_TEMPLATES = [
    "An email with {components}",
    "Build a {adj} email using {components}",
    "{adj} email: {components}",
    "Create an email that has {components}",
    "Email with {components} layout",
    "Email newsletter with {components}",
    "Send {components} in an email",
    "{components} email design",
]


def describe_email_components(components: List[str]) -> str:
    """Generate a natural language description from email component list."""
    counts: Dict[str, int] = {}
    for c in components:
        if c == "EmailSpec":
            continue  # Skip root
        counts[c] = counts.get(c, 0) + 1

    parts = []
    for comp, count in counts.items():
        desc = EMAIL_COMPONENT_DESCRIPTIONS.get(comp, comp.lower())
        if count > 1:
            parts.append(f"{count} {desc}")
        else:
            parts.append(desc)

    if not parts:
        parts = ["content"]

    if len(parts) <= 2:
        comp_text = " and ".join(parts)
    else:
        comp_text = ", ".join(parts[:-1]) + f", and {parts[-1]}"

    template = random.choice(EMAIL_DESCRIPTION_TEMPLATES)
    adj = random.choice(ADJECTIVES)
    return template.format(components=comp_text, adj=adj)


def generate_email_structures(count: int, seed: int = 42) -> List[dict]:
    """Generate random valid email structures using the email hierarchy.

    Email structure is simpler than cards: EmailSpec → blocks → (optional columns).
    Max depth is 3 (EmailSpec → ColumnsBlock → Column → content).
    """
    random.seed(seed)

    top_level_blocks = EMAIL_CONTAINERS["EmailSpec"]
    column_content = EMAIL_CONTAINERS["Column"]

    structures = []
    for i in range(count):
        # Random number of blocks (1-6)
        n_blocks = random.randint(1, 6)
        components = ["EmailSpec"]
        block_choices = random.choices(top_level_blocks, k=n_blocks)

        for block in block_choices:
            components.append(block)

            # If ColumnsBlock, add 2-3 columns with content
            if block == "ColumnsBlock":
                n_cols = random.randint(2, 3)
                for _ in range(n_cols):
                    components.append("Column")
                    # Each column gets 1-3 content blocks
                    n_col_content = random.randint(1, 3)
                    col_blocks = random.choices(column_content, k=n_col_content)
                    components.extend(col_blocks)

        # Build a simple DSL representation
        block_parts = []
        for c in components[1:]:  # skip EmailSpec
            sym = c[0].lower()  # simplified symbol
            block_parts.append(c)

        desc = describe_email_components(components)
        dsl = f"ε[{', '.join(block_parts)}]"

        structures.append({
            "components": components,
            "dsl": dsl,
            "description": desc,
            "tree": {"root": "EmailSpec", "children": block_parts},
            "depth": 3 if "ColumnsBlock" in components else 2,
        })

        if (i + 1) % 100 == 0:
            logger.info(f"Generated {i + 1}/{count} email structures")

    logger.info(f"Generated {len(structures)} email structures")
    return structures


def _load_email_dag():
    """Load component DAG from the email wrapper for structural features."""
    global _dag_children, _dag_parents, _dag_depth, _dag_loaded
    if _dag_loaded:
        return

    try:
        from gmail.email_wrapper_setup import get_email_wrapper
        wrapper = get_email_wrapper()

        all_names = list(wrapper._name_to_idx.keys()) if hasattr(wrapper, '_name_to_idx') else []
        if not all_names:
            all_names = list(wrapper.component_names) if hasattr(wrapper, 'component_names') else []

        # If wrapper doesn't have components indexed yet, use hardcoded hierarchy
        if not all_names:
            logger.info("Email wrapper has no indexed components, using hardcoded hierarchy")
            for parent, children in EMAIL_CONTAINERS.items():
                _dag_children[parent] = set(children)
                for child in children:
                    _dag_parents.setdefault(child, set()).add(parent)
            all_names = list(set(list(_dag_children.keys()) + [c for cs in _dag_children.values() for c in cs]))
        else:
            logger.info(f"Building email DAG from {len(all_names)} components")
            for comp_name in all_names:
                _dag_children[comp_name] = set(wrapper.get_children(comp_name))
                _dag_parents[comp_name] = set(wrapper.get_parents(comp_name))

        # Compute depth (BFS from roots)
        roots = [n for n in all_names if not _dag_parents.get(n)]
        if not roots:
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
        logger.info(f"Loaded email DAG: {len(_dag_children)} components, max depth={max(_dag_depth.values()) if _dag_depth else 0}")
    except Exception as e:
        logger.warning(f"Could not load email DAG: {e}")
        _dag_loaded = True


# ---------------------------------------------------------------------------
# Real user training data extraction (from mcp_tool_responses)
# ---------------------------------------------------------------------------


def extract_real_user_groups(
    client,
    collection: str = "mcp_tool_responses",
    class_points: List[dict] = None,
    feature_version: int = 3,
) -> List[dict]:
    """Extract training data from real send_dynamic_card invocations.

    Queries the tool_responses collection for send_dynamic_card calls,
    extracts the card_description (query) and component info (ground truth),
    then builds query groups against the class candidates.
    """
    from qdrant_client import models as qmodels

    # Fetch send_dynamic_card responses
    points = []
    offset = None
    while True:
        batch, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="tool_name",
                        match=qmodels.MatchValue(value="send_dynamic_card"),
                    ),
                ]
            ),
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(batch)
        if next_offset is None:
            break
        offset = next_offset

    logger.info(f"Found {len(points)} send_dynamic_card responses in {collection}")

    if not points or not class_points:
        return []

    # Extract unique (description → components) pairs
    desc_to_components: Dict[str, set] = {}
    for pt in points:
        payload = pt.payload or {}
        rd = payload.get("response_data", {})
        args = rd.get("arguments", {}) if isinstance(rd, dict) else {}
        if not isinstance(args, dict):
            args = {}

        desc = args.get("card_description", "")
        if not desc or len(desc) < 5:
            continue

        # Parse response — it's a list of content blocks with JSON text
        resp = rd.get("response") if isinstance(rd, dict) else None
        resp_data = {}
        if isinstance(resp, list):
            for item in resp:
                if isinstance(item, dict) and item.get("type") == "text":
                    try:
                        resp_data = json.loads(item.get("text", "{}"))
                        break
                    except (json.JSONDecodeError, TypeError):
                        pass
        elif isinstance(resp, dict):
            resp_data = resp

        # Only use successful card sends
        if not resp_data.get("success"):
            continue

        # Extract component info
        comp_info = resp_data.get("componentInfo") or {}
        comp_name = comp_info.get("componentName") or comp_info.get("component_name")

        components = set()
        if comp_name and comp_name != "SmartCardBuilder":
            components.add(comp_name)

        # Extract from DSL validation
        dsl_val = resp_data.get("dslValidation") or {}
        comp_counts = dsl_val.get("component_counts") or {}
        for cname in comp_counts:
            components.add(cname)

        # Extract from input mapping
        input_map = resp_data.get("inputMapping") or {}
        for mapping in (input_map.get("mappings") or []):
            c = mapping.get("component")
            if c:
                components.add(c)

        if components:
            key = desc[:200]
            if key not in desc_to_components:
                desc_to_components[key] = set()
            desc_to_components[key].update(components)

    logger.info(f"Extracted {len(desc_to_components)} unique description→component mappings")

    # Build query groups from real data
    from config.embedding_service import EmbeddingService
    service = EmbeddingService()

    groups = []
    for desc, components in desc_to_components.items():
        try:
            # Embed the real description
            comp_vecs = service.embed_multivector_sync([desc])
            inp_vecs = service.embed_multivector_sync([desc])
            rel_vec = service.embed_dense_sync([desc])

            comp_np = np.array(comp_vecs, dtype=np.float32) if comp_vecs else None
            inp_np = np.array(inp_vecs, dtype=np.float32) if inp_vecs else None
            rel_np = np.array(rel_vec, dtype=np.float32).flatten() if rel_vec else None

            if comp_np is not None and comp_np.ndim == 1:
                comp_np = comp_np.reshape(1, -1)
            if inp_np is not None and inp_np.ndim == 1:
                inp_np = inp_np.reshape(1, -1)

            query = SyntheticPattern(
                pattern_id=f"real_{len(groups):04d}",
                component_paths=list(components),
                dsl="",
                description=desc,
                comp_vectors=comp_np,
                inp_vectors=inp_np,
                rel_vector=rel_np,
            )

            # Score against all class points
            scored = []
            for cp in class_points:
                if cp["comp_vectors"] is None:
                    continue
                sim = maxsim_score(query.comp_vectors, cp["comp_vectors"])
                scored.append((cp, sim))

            scored.sort(key=lambda x: x[1], reverse=True)
            top_candidates = [c for c, _ in scored[:20]]
            remaining = [c for c, _ in scored[20:]]
            if remaining:
                top_candidates.extend(random.sample(remaining, min(5, len(remaining))))

            # Label: 1.0 if class name is in the real components used
            if feature_version == 3:
                feat_fn = compute_features_v3
                feat_names = FEATURE_NAMES_V3
            else:
                feat_fn = compute_features_v2
                feat_names = FEATURE_NAMES_V2

            candidates_data = []
            has_positive = False
            for cand in top_candidates:
                label = 1.0 if cand["name"] in components else 0.0
                if label > 0.5:
                    has_positive = True
                feats = feat_fn(
                    query, cand["comp_vectors"], cand["inp_vectors"],
                    cand["rel_vector"], cand["name"],
                )
                cand_data = {"name": cand["name"], "full_path": cand["full_path"], "label": label}
                for fname, fval in zip(feat_names, feats):
                    cand_data[fname] = round(float(fval), 4)
                candidates_data.append(cand_data)

            if has_positive and len(candidates_data) >= 2:
                groups.append({
                    "query_id": query.pattern_id,
                    "query_description": desc[:200],
                    "query_dsl": "",
                    "query_components": list(components),
                    "n_candidates": len(candidates_data),
                    "n_positive": sum(1 for c in candidates_data if c["label"] == 1.0),
                    "candidates": candidates_data,
                    "source": "real_user",
                })

        except Exception as e:
            logger.debug(f"Failed to build group for real desc: {e}")
            continue

    logger.info(f"Built {len(groups)} real user training groups")
    return groups


def extract_instance_pattern_groups(
    client,
    collection: str = "mcp_gchat_cards_v7",
    class_points: List[dict] = None,
    feature_version: int = 5,
    top_k: int = 20,
    n_random: int = 5,
) -> List[dict]:
    """Extract training groups from real instance_pattern points in Qdrant.

    Pulls content-type instance patterns (real user card builds), extracts
    their component_paths as ground-truth form labels, builds content text
    from instance_params, and creates V5-compatible query groups.

    This provides higher-quality training signal than pure synthetic data
    because it uses actual user description→component choices.

    Args:
        client: Qdrant client (already connected).
        collection: Collection to pull instance patterns from.
        class_points: Pre-extracted class points (candidates).
        feature_version: Feature version (5 for dual-head).
        top_k: Top-K candidates per query.
        n_random: Random negatives per query.
    """
    from qdrant_client import models as qmodels

    # Paginate through all instance patterns
    all_points = []
    offset = None
    while True:
        batch, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="type", match=qmodels.MatchValue(value="instance_pattern"),
                    ),
                ]
            ),
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        all_points.extend(batch)
        if next_offset is None:
            break
        offset = next_offset

    # Filter to content patterns (not feedback_ui) client-side
    content_points = [
        p for p in all_points
        if p.payload.get("pattern_type") == "content"
    ]
    logger.info(
        f"Found {len(all_points)} instance_patterns in {collection}, "
        f"{len(content_points)} are content patterns"
    )

    if not content_points or not class_points:
        return []

    # Import embedding service for patterns without vectors
    from config.embedding_service import EmbeddingService
    service = EmbeddingService()

    # Import content text extractor
    from adapters.module_wrapper.pipeline_mixin import extract_content_text_from_params

    groups = []
    skipped = 0

    for pt in content_points:
        payload = pt.payload or {}
        vectors = pt.vector or {}

        # Extract component paths (ground truth)
        parent_paths = payload.get("parent_paths", [])
        if not parent_paths:
            skipped += 1
            continue

        # Normalize to short names (strip module prefix)
        component_names = list(set(
            p.split(".")[-1] for p in parent_paths
        ))

        desc = payload.get("card_description", "")
        if not desc or len(desc) < 3:
            skipped += 1
            continue

        instance_params = payload.get("instance_params", {})

        # Build content text from instance params
        content_text = extract_content_text_from_params(
            instance_params, desc
        )
        # Fallback: use title + description if no structured content
        if not content_text:
            parts = []
            title = instance_params.get("title")
            if title and isinstance(title, str):
                parts.append(title)
            ip_desc = instance_params.get("description", "")
            if ip_desc and isinstance(ip_desc, str) and ip_desc != desc:
                parts.append(ip_desc[:100])
            content_text = " ".join(parts)

        try:
            # Use existing vectors from Qdrant if available
            comp_raw = vectors.get("components") if isinstance(vectors, dict) else None
            inp_raw = vectors.get("inputs") if isinstance(vectors, dict) else None
            rel_raw = vectors.get("relationships") if isinstance(vectors, dict) else None

            if comp_raw:
                comp_np = np.array(comp_raw, dtype=np.float32)
                if comp_np.ndim == 1:
                    comp_np = comp_np.reshape(1, -1)
            else:
                # Embed description with ColBERT
                vecs = service.embed_multivector_sync([desc])
                comp_np = np.array(vecs, dtype=np.float32) if vecs else None
                if comp_np is not None and comp_np.ndim == 1:
                    comp_np = comp_np.reshape(1, -1)

            if inp_raw:
                inp_np = np.array(inp_raw, dtype=np.float32)
                if inp_np.ndim == 1:
                    inp_np = inp_np.reshape(1, -1)
            else:
                vecs = service.embed_multivector_sync([desc])
                inp_np = np.array(vecs, dtype=np.float32) if vecs else None
                if inp_np is not None and inp_np.ndim == 1:
                    inp_np = inp_np.reshape(1, -1)

            if rel_raw:
                rel_np = np.array(rel_raw, dtype=np.float32).flatten()
            else:
                vecs = service.embed_dense_sync([desc])
                rel_np = np.array(vecs, dtype=np.float32).flatten() if vecs else None

            # Content vector: embed content_text if available
            content_np = None
            if content_text:
                vecs = service.embed_dense_sync([content_text])
                content_np = np.array(vecs, dtype=np.float32).flatten() if vecs else None

            if comp_np is None:
                skipped += 1
                continue

            query = SyntheticPattern(
                pattern_id=f"real_ip_{len(groups):04d}",
                component_paths=component_names,
                dsl=instance_params.get("dsl", ""),
                description=desc,
                comp_vectors=comp_np,
                inp_vectors=inp_np,
                rel_vector=rel_np,
                content_text=content_text,
                content_vector=content_np,
            )

            # Score against all class points
            scored = []
            for cp in class_points:
                if cp["comp_vectors"] is None:
                    continue
                sim = maxsim_score(query.comp_vectors, cp["comp_vectors"])
                scored.append((cp, sim))

            scored.sort(key=lambda x: x[1], reverse=True)
            top_candidates = [c for c, _ in scored[:top_k]]
            remaining = [c for c, _ in scored[top_k:]]
            if remaining:
                top_candidates.extend(
                    random.sample(remaining, min(n_random, len(remaining)))
                )

            # Build candidate data with labels
            if feature_version == 5:
                feat_names = FEATURE_NAMES_V5
            elif feature_version in (3, 4):
                feat_names = FEATURE_NAMES_V3
            else:
                feat_names = FEATURE_NAMES_V2

            candidates_data = []
            has_positive = False
            for cand in top_candidates:
                form_label = 1.0 if cand["name"] in component_names else 0.0
                if form_label > 0.5:
                    has_positive = True

                if feature_version == 5:
                    feats = compute_features_v5(
                        query, cand["comp_vectors"], cand["inp_vectors"],
                        cand["rel_vector"], cand["name"],
                        query_content_vector=query.content_vector,
                        cand_content_vector=cand.get("content_vector"),
                        cand_has_content=cand.get("has_content_vector", False),
                        cand_n_content_fields=0,
                        cand_total_content_fields=5,
                    )
                    content_label = compute_content_label(
                        content_text, cand["name"]
                    )
                    cand_data = {
                        "name": cand["name"],
                        "full_path": cand["full_path"],
                        "form_label": form_label,
                        "content_label": content_label,
                    }
                elif feature_version in (3, 4):
                    feats = compute_features_v3(
                        query, cand["comp_vectors"], cand["inp_vectors"],
                        cand["rel_vector"], cand["name"],
                    )
                    cand_data = {
                        "name": cand["name"],
                        "full_path": cand["full_path"],
                        "label": form_label,
                    }
                else:
                    feats = compute_features_v2(
                        query, cand["comp_vectors"], cand["inp_vectors"],
                        cand["rel_vector"], cand["name"],
                    )
                    cand_data = {
                        "name": cand["name"],
                        "full_path": cand["full_path"],
                        "label": form_label,
                    }

                for fname, fval in zip(feat_names, feats):
                    cand_data[fname] = round(float(fval), 4)
                candidates_data.append(cand_data)

            if has_positive and len(candidates_data) >= 2:
                group_data = {
                    "query_id": query.pattern_id,
                    "query_description": desc[:200],
                    "query_dsl": query.dsl,
                    "query_components": component_names,
                    "n_candidates": len(candidates_data),
                    "n_positive": sum(
                        1 for c in candidates_data
                        if c.get("form_label", c.get("label", 0.0)) == 1.0
                    ),
                    "candidates": candidates_data,
                    "source": "instance_pattern",
                    "source_collection": collection,
                }
                if feature_version == 5:
                    group_data["content_text"] = content_text
                    group_data["n_content_positive"] = sum(
                        1 for c in candidates_data
                        if c.get("content_label", 0.0) == 1.0
                    )
                groups.append(group_data)

        except Exception as e:
            logger.debug(f"Failed to build group for instance pattern: {e}")
            skipped += 1
            continue

    logger.info(
        f"Built {len(groups)} instance pattern training groups "
        f"from {collection} (skipped {skipped})"
    )
    if groups and feature_version == 5:
        n_with_content = sum(1 for g in groups if g.get("content_text"))
        total_content_pos = sum(g.get("n_content_positive", 0) for g in groups)
        logger.info(
            f"  With content text: {n_with_content}/{len(groups)}, "
            f"content positives: {total_content_pos}"
        )

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
    parser.add_argument("--collection", default=None, help="Qdrant collection for class points (auto-detected per domain)")
    parser.add_argument("--output", default=None, help="Output path (auto-detected per domain/version)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-variations", action="store_true", help="Skip variation generation")
    parser.add_argument("--skip-embed", action="store_true", help="Skip embedding (use pre-computed)")
    parser.add_argument("--feature-version", type=int, default=3, choices=[2, 3, 5],
                        help="Feature version: 2=V2 (8D), 3=V3 (14D decomposed), 5=V5 (17D dual-head)")
    parser.add_argument("--domain", default="card", choices=["card", "email"],
                        help="Domain: 'card' (gchat cards) or 'email' (MJML email)")
    parser.add_argument("--include-real", action="store_true",
                        help="Also extract real user training data from mcp_tool_responses")
    parser.add_argument("--include-instance-patterns", action="store_true",
                        help="Extract real instance patterns from Qdrant (v7/v8)")
    parser.add_argument("--instance-pattern-collection", default=None,
                        help="Collection for instance patterns (default: mcp_gchat_cards_v7 for card)")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    # Auto-detect collection and output based on domain
    if args.collection is None:
        args.collection = "email_blocks" if args.domain == "email" else "mcp_gchat_cards_v8"
    if args.output is None:
        fv = args.feature_version
        domain = args.domain
        suffix = f"_v{fv}" if fv >= 2 else ""
        prefix = f"email_" if domain == "email" else "mw_"
        args.output = str(Path(__file__).parent / f"{prefix}synthetic_groups{suffix}.json")

    # For email domain, load the email DAG instead of card DAG
    if args.domain == "email":
        global _dag_loaded
        _dag_loaded = False  # Force reload
        _load_email_dag()

    # Step 1: Generate random valid structures
    if args.domain == "email":
        logger.info(f"=== Step 1: Generating {args.count} random email structures ===")
        structures = generate_email_structures(args.count, args.seed)
    else:
        logger.info(f"=== Step 1: Generating {args.count} random card structures ===")
        structures = generate_structures(args.count, args.seed)

    if not structures:
        logger.error("No valid structures generated")
        return

    # Step 2: Generate variations (cards only — email structures are simple enough)
    if not args.skip_variations and args.domain == "card":
        logger.info(f"\n=== Step 2: Generating {args.variations} variations per structure ===")
        try:
            structures = generate_variations(structures, n_struct_variations=args.variations)
        except Exception as e:
            logger.warning(f"Variation generation failed (continuing with originals): {e}")

    # Step 3: Embed all patterns
    generate_content = args.feature_version >= 5
    logger.info(f"\n=== Step 3: Embedding {len(structures)} patterns (content={generate_content}) ===")
    patterns = embed_patterns(structures, generate_content=generate_content)

    if not patterns:
        logger.error("No patterns embedded successfully")
        return

    # Step 4: Extract class points from Qdrant
    logger.info(f"\n=== Step 4: Extracting class points from Qdrant ({args.collection}) ===")
    from research.trm.h2.mw_extract import connect_qdrant
    client = connect_qdrant()
    class_points = extract_class_points(client, args.collection)

    if not class_points:
        logger.error("No class points found in Qdrant")
        return

    # Step 5: Build query groups with ground-truth labels
    fv = args.feature_version
    logger.info(f"\n=== Step 5: Building query groups (domain={args.domain}, feature_version={fv}) ===")
    groups = build_synthetic_groups(patterns, class_points, args.top_k, args.n_random, feature_version=fv)

    # Step 5b: Extract real user training data if requested
    if args.include_real and args.domain == "card":
        logger.info(f"\n=== Step 5b: Extracting real user training data ===")
        real_groups = extract_real_user_groups(
            client, collection="mcp_tool_responses",
            class_points=class_points, feature_version=fv,
        )
        if real_groups:
            logger.info(f"Adding {len(real_groups)} real user groups to {len(groups)} synthetic groups")
            groups.extend(real_groups)

    # Step 5c: Extract instance pattern groups if requested
    if args.include_instance_patterns and args.domain == "card":
        ip_collection = args.instance_pattern_collection or "mcp_gchat_cards_v7"
        logger.info(
            f"\n=== Step 5c: Extracting instance pattern groups from {ip_collection} ==="
        )
        ip_groups = extract_instance_pattern_groups(
            client,
            collection=ip_collection,
            class_points=class_points,
            feature_version=fv,
            top_k=args.top_k,
            n_random=args.n_random,
        )
        if ip_groups:
            logger.info(
                f"Adding {len(ip_groups)} instance pattern groups "
                f"to {len(groups)} existing groups"
            )
            groups.extend(ip_groups)

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
    logger.info(f"Feature version:      V{fv}")
    logger.info(f"Structures generated: {len(structures)}")
    logger.info(f"Patterns embedded:    {len(patterns)}")
    logger.info(f"Query groups:         {len(groups)}")
    logger.info(f"Unique DSL patterns:  {unique_queries}")
    logger.info(f"Total candidates:     {total_candidates}")
    logger.info(f"Total form positives: {total_positive}")
    logger.info(f"Form positive rate:   {total_positive/total_candidates:.1%}")
    if fv >= 5:
        total_content_pos = sum(g.get("n_content_positive", 0) for g in groups)
        n_with_content = sum(1 for g in groups if g.get("content_text"))
        logger.info(f"Content positives:    {total_content_pos}")
        logger.info(f"Content pos rate:     {total_content_pos/total_candidates:.1%}")
        logger.info(f"Queries with content: {n_with_content}/{len(groups)}")
    logger.info(f"Output:               {output_path}")


if __name__ == "__main__":
    main()
