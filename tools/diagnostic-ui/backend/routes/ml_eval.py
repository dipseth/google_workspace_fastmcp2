"""ML evaluation endpoints for the learned scorer MLP diagnostic dashboard."""
import json
import math
from pathlib import Path
from typing import List, Optional

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["ml"])

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_H2_DIR = _PROJECT_ROOT / "research" / "trm" / "h2"
_CHECKPOINT_PATH = _H2_DIR / "checkpoints" / "best_model_mw.pt"
_QDRANT_GROUPS = _H2_DIR / "mw_groups.json"
_SYNTHETIC_GROUPS = _H2_DIR / "mw_synthetic_groups.json"
_SYNTHETIC_GROUPS_V2 = _H2_DIR / "mw_synthetic_groups_v2.json"
_SYNTHETIC_GROUPS_V3 = _H2_DIR / "mw_synthetic_groups_v3.json"

FEATURE_NAMES_V1 = [
    "sim_components", "sim_inputs", "sim_relationships",
    "q_comp_norm", "q_inp_norm", "q_rel_norm",
    "c_comp_norm", "c_inp_norm", "c_rel_norm",
]

FEATURE_NAMES_V2 = [
    "sim_components", "sim_inputs", "sim_relationships",
    "is_parent", "is_child", "is_sibling",
    "depth_ratio", "n_shared_ancestors",
]

FEATURE_NAMES_V3 = [
    "sim_c_mean", "sim_c_max", "sim_c_std", "sim_c_coverage",
    "sim_i_mean", "sim_i_max", "sim_i_std", "sim_i_coverage",
    "sim_relationships",
    "is_parent", "is_child", "is_sibling",
    "depth_ratio", "n_shared_ancestors",
]

# Active feature names (set when model loads)
FEATURE_NAMES = FEATURE_NAMES_V1
_feature_version = 1

# ---------------------------------------------------------------------------
# Lazy-loaded singletons
# ---------------------------------------------------------------------------
_model = None
_state_dict = None
_val_groups = None
_all_groups = None


def _load_torch():
    """Import torch lazily."""
    import torch
    return torch


def _load_model():
    """Load the SimilarityScorerMW checkpoint."""
    global _model, _state_dict, FEATURE_NAMES, _feature_version
    if _model is not None:
        return _model

    torch = _load_torch()
    import torch.nn as nn

    ckpt = torch.load(str(_CHECKPOINT_PATH), map_location="cpu", weights_only=False)
    hidden = ckpt.get("hidden_dim", 32)
    dropout = ckpt.get("dropout", 0.15)
    input_dim = ckpt.get("input_dim", 9)
    _feature_version = ckpt.get("feature_version", 1)
    if _feature_version == 3:
        FEATURE_NAMES = FEATURE_NAMES_V3
    elif _feature_version == 2:
        FEATURE_NAMES = FEATURE_NAMES_V2
    else:
        FEATURE_NAMES = FEATURE_NAMES_V1

    mlp = nn.Sequential(
        nn.Linear(input_dim, hidden),
        nn.SiLU(),
        nn.Dropout(dropout),
        nn.Linear(hidden, hidden),
        nn.SiLU(),
        nn.Dropout(dropout),
        nn.Linear(hidden, 1),
    )
    # Strip 'mlp.' prefix from state dict keys if present
    raw_sd = ckpt["model_state_dict"]
    sd = {}
    for k, v in raw_sd.items():
        sd[k.removeprefix("mlp.")] = v

    mlp.load_state_dict(sd)
    mlp.eval()

    _model = mlp
    _state_dict = sd
    return mlp


def _load_groups():
    """Load and split training data, reproducing the exact train/val split."""
    global _val_groups, _all_groups
    if _val_groups is not None:
        return _val_groups, _all_groups

    all_groups = []

    if _feature_version == 3:
        # V3: Decomposed MaxSim + structural features
        if _SYNTHETIC_GROUPS_V3.exists():
            with open(_SYNTHETIC_GROUPS_V3) as f:
                all_groups = json.load(f)
    elif _feature_version == 2:
        # V2: Use structural features data only
        if _SYNTHETIC_GROUPS_V2.exists():
            with open(_SYNTHETIC_GROUPS_V2) as f:
                all_groups = json.load(f)
    else:
        # V1: Qdrant groups (only 3 features — pad norms to 0.0)
        if _QDRANT_GROUPS.exists():
            with open(_QDRANT_GROUPS) as f:
                qdrant = json.load(f)
            for g in qdrant:
                for c in g.get("candidates", []):
                    for norm_key in ["q_comp_norm", "q_inp_norm", "q_rel_norm",
                                     "c_comp_norm", "c_inp_norm", "c_rel_norm"]:
                        c.setdefault(norm_key, 0.0)
                all_groups.append(g)

        # Synthetic groups (all 9 features)
        if _SYNTHETIC_GROUPS.exists():
            with open(_SYNTHETIC_GROUPS) as f:
                synthetic = json.load(f)
            all_groups.extend(synthetic)

    # Reproduce train/val split: seed=42, 80/20
    np.random.seed(42)
    indices = np.random.permutation(len(all_groups))
    n_val = max(1, int(len(all_groups) * 0.2))
    val_indices = set(indices[-n_val:].tolist())

    val_groups = [all_groups[i] for i in range(len(all_groups)) if i in val_indices]

    _val_groups = val_groups
    _all_groups = all_groups
    return val_groups, all_groups


def _candidate_features(c: dict) -> List[float]:
    """Extract 9-feature vector from a candidate dict."""
    return [c.get(f, 0.0) for f in FEATURE_NAMES]


def _score_candidates(model, candidates: List[dict]) -> List[float]:
    """Score a list of candidates through the MLP, return scores."""
    torch = _load_torch()
    features = [_candidate_features(c) for c in candidates]
    x = torch.tensor(features, dtype=torch.float32)
    with torch.no_grad():
        scores = model(x).squeeze(-1)
    return scores.tolist()


# ---------------------------------------------------------------------------
# Endpoint 1: Score Distribution
# ---------------------------------------------------------------------------
@router.get("/ml/score-distribution")
async def score_distribution():
    """Score distribution for positive vs negative candidates on validation data."""
    model = _load_model()
    val_groups, _ = _load_groups()

    positive_scores = []
    negative_scores = []

    for group in val_groups:
        candidates = group.get("candidates", [])
        if not candidates:
            continue
        scores = _score_candidates(model, candidates)
        for c, s in zip(candidates, scores):
            if c.get("label", 0.0) > 0.5:
                positive_scores.append(s)
            else:
                negative_scores.append(s)

    pos = np.array(positive_scores) if positive_scores else np.array([0.0])
    neg = np.array(negative_scores) if negative_scores else np.array([0.0])

    return {
        "positive_scores": [round(float(x), 4) for x in pos],
        "negative_scores": [round(float(x), 4) for x in neg],
        "n_val_groups": len(val_groups),
        "n_positive": len(positive_scores),
        "n_negative": len(negative_scores),
        "mean_positive": round(float(pos.mean()), 4),
        "mean_negative": round(float(neg.mean()), 4),
        "std_positive": round(float(pos.std()), 4),
        "std_negative": round(float(neg.std()), 4),
        "separation_margin": round(float(pos.mean() - neg.mean()), 4),
        "suggested_threshold": round(float((pos.mean() + neg.mean()) / 2), 4),
    }


# ---------------------------------------------------------------------------
# Endpoint 2: Feature Importance
# ---------------------------------------------------------------------------
@router.get("/ml/feature-importance")
async def feature_importance():
    """Feature importance via weight magnitude and zero-out ablation."""
    torch = _load_torch()
    model = _load_model()
    val_groups, _ = _load_groups()

    # Method A: Weight magnitude (L2 norm of each input column in layer 1)
    w1 = _state_dict["0.weight"]  # [hidden, 9]
    col_norms = torch.norm(w1, dim=0).tolist()  # L2 norm per input feature
    total = sum(col_norms)
    weight_magnitude = [round(n / total, 4) for n in col_norms]

    # Method B: Zero-out ablation on val set
    # First compute baseline accuracy
    def compute_accuracy(feature_mask=None):
        correct = 0
        total_groups = 0
        for group in val_groups:
            candidates = group.get("candidates", [])
            if not candidates:
                continue
            features = [_candidate_features(c) for c in candidates]
            x = torch.tensor(features, dtype=torch.float32)
            if feature_mask is not None:
                x[:, feature_mask] = 0.0
            with torch.no_grad():
                scores = model(x).squeeze(-1)
            top_idx = scores.argmax().item()
            labels = [c.get("label", 0.0) for c in candidates]
            if labels[top_idx] > 0.5:
                correct += 1
            total_groups += 1
        return correct / total_groups if total_groups > 0 else 0.0

    baseline = compute_accuracy()
    n_features = len(FEATURE_NAMES)
    ablation_impact = []
    for i in range(n_features):
        ablated = compute_accuracy(feature_mask=i)
        ablation_impact.append(round(baseline - ablated, 4))

    return {
        "feature_names": FEATURE_NAMES,
        "weight_magnitude": weight_magnitude,
        "ablation_impact": ablation_impact,
        "baseline_accuracy": round(baseline, 4),
    }


# ---------------------------------------------------------------------------
# Endpoint 3: Per-Group Performance
# ---------------------------------------------------------------------------
@router.get("/ml/per-group-performance")
async def per_group_performance():
    """Per-group accuracy breakdown showing which groups the model gets right/wrong."""
    torch = _load_torch()
    model = _load_model()
    val_groups, _ = _load_groups()

    groups_detail = []
    correct_count = 0
    total_count = 0
    all_margins = []

    for group in val_groups:
        candidates = group.get("candidates", [])
        if not candidates:
            continue

        features = [_candidate_features(c) for c in candidates]
        x = torch.tensor(features, dtype=torch.float32)
        with torch.no_grad():
            scores = model(x).squeeze(-1)

        score_list = scores.tolist()
        labels = [c.get("label", 0.0) for c in candidates]

        # Find rank of first correct candidate
        sorted_indices = sorted(range(len(score_list)), key=lambda i: score_list[i], reverse=True)
        predicted_rank = None
        for rank, idx in enumerate(sorted_indices, 1):
            if labels[idx] > 0.5:
                predicted_rank = rank
                break

        if predicted_rank is None:
            predicted_rank = len(candidates)

        # Score margin: gap between highest positive and highest negative
        pos_scores = [s for s, l in zip(score_list, labels) if l > 0.5]
        neg_scores = [s for s, l in zip(score_list, labels) if l <= 0.5]
        margin = (max(pos_scores) - max(neg_scores)) if pos_scores and neg_scores else 0.0

        is_correct = predicted_rank == 1
        if is_correct:
            correct_count += 1
        total_count += 1
        all_margins.append(margin)

        group_name = group.get("query_name") or group.get("query_id", "unknown")
        n_positive = sum(1 for l in labels if l > 0.5)

        groups_detail.append({
            "group_name": group_name,
            "query_dsl": group.get("query_dsl", ""),
            "n_candidates": len(candidates),
            "n_positive": n_positive,
            "predicted_rank": predicted_rank,
            "score_margin": round(margin, 4),
            "correct": is_correct,
            "top_predicted": candidates[sorted_indices[0]].get("name", "?"),
            "expected": next((c.get("name", "?") for c in candidates if c.get("label", 0) > 0.5), "?"),
            "top_score": round(score_list[sorted_indices[0]], 4),
        })

    return {
        "groups": groups_detail,
        "total_groups": total_count,
        "correct_count": correct_count,
        "failure_count": total_count - correct_count,
        "accuracy": round(correct_count / total_count, 4) if total_count else 0,
        "mean_rank": round(sum(g["predicted_rank"] for g in groups_detail) / len(groups_detail), 3) if groups_detail else 0,
        "mean_margin": round(float(np.mean(all_margins)), 4) if all_margins else 0,
    }


# ---------------------------------------------------------------------------
# Endpoint 4: Weight Visualization
# ---------------------------------------------------------------------------
@router.get("/ml/weight-visualization")
async def weight_visualization():
    """Return model weight matrices and biases for heatmap rendering."""
    _load_model()  # ensure state_dict loaded

    layers = []
    n_in = len(FEATURE_NAMES)
    hidden = _state_dict["0.weight"].shape[0]
    layer_specs = [
        (f"layer1 ({n_in}→{hidden})", "0", FEATURE_NAMES, hidden),
        (f"layer2 ({hidden}→{hidden})", "3", None, hidden),
        (f"output ({hidden}→1)", "6", None, 1),
    ]

    for name, prefix, input_names, out_dim in layer_specs:
        w = _state_dict[f"{prefix}.weight"]
        b = _state_dict[f"{prefix}.bias"]
        layers.append({
            "name": name,
            "weight": [[round(float(v), 5) for v in row] for row in w.tolist()],
            "bias": [round(float(v), 5) for v in b.tolist()],
            "input_names": input_names,
            "shape": list(w.shape),
        })

    total_params = sum(
        w.numel() for w in _state_dict.values()
    )

    return {
        "layers": layers,
        "total_params": int(total_params),
    }


# ---------------------------------------------------------------------------
# Endpoint 5: Inference Inspector
# ---------------------------------------------------------------------------
class InferenceRequest(BaseModel):
    description: str
    limit: int = 10


@router.post("/ml/inference-inspector")
async def inference_inspector(req: InferenceRequest):
    """Run a live query and return all 9 features + layer activations for each candidate."""
    torch = _load_torch()
    model = _load_model()

    # Run search through the wrapper
    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        wrapper = get_card_framework_wrapper()

        class_results, content_patterns, form_patterns = wrapper.search_hybrid_dispatch(
            description=req.description,
            component_paths=None,
            limit=req.limit,
            token_ratio=1.0,
            content_feedback="positive",
            form_feedback="positive",
            include_classes=True,
        )

        all_results = list(class_results or []) + list(content_patterns or []) + list(form_patterns or [])

        # Deduplicate by id
        seen = set()
        deduped = []
        for r in all_results:
            rid = r.get("id", id(r))
            if rid not in seen:
                seen.add(rid)
                deduped.append(r)

    except Exception as e:
        return {"error": f"Search failed: {e}", "candidates": []}

    # For each result, build features from FEATURE_NAMES and run manual forward pass.
    # Search results carry sim_components/sim_inputs/sim_relationships plus
    # any structural or decomposed fields the search pipeline exposes.
    candidates_out = []
    for r in deduped[:req.limit]:
        features = {f: r.get(f, 0.0) for f in FEATURE_NAMES}
        # Fallback: map V3 decomposed names to scalar search results
        if _feature_version == 3:
            sim_c = r.get("sim_components", 0.0)
            sim_i = r.get("sim_inputs", 0.0)
            features.setdefault("sim_c_mean", sim_c)
            features.setdefault("sim_c_max", sim_c)
            features.setdefault("sim_c_std", 0.0)
            features.setdefault("sim_c_coverage", 1.0 if sim_c > 0.4 else 0.0)
            features.setdefault("sim_i_mean", sim_i)
            features.setdefault("sim_i_max", sim_i)
            features.setdefault("sim_i_std", 0.0)
            features.setdefault("sim_i_coverage", 1.0 if sim_i > 0.4 else 0.0)
            features.setdefault("sim_relationships", r.get("sim_relationships", 0.0))

        feat_vec = [features.get(f, 0.0) for f in FEATURE_NAMES]
        x = torch.tensor([feat_vec], dtype=torch.float32)

        # Manual layer-by-layer forward pass
        with torch.no_grad():
            h1_pre = model[0](x)          # Linear 9->32
            h1_post = model[1](h1_pre)    # SiLU
            # skip dropout [2] in eval mode
            h2_pre = model[3](h1_post)    # Linear 32->32
            h2_post = model[4](h2_pre)    # SiLU
            output = model[6](h2_post)    # Linear 32->1

        candidates_out.append({
            "name": r.get("name", "?"),
            "type": r.get("type", "?"),
            "symbol": r.get("symbol", "?"),
            "score": round(float(output.item()), 4),
            "features": {k: round(float(v), 4) for k, v in features.items()},
            "activations": {
                "hidden1_pre": [round(float(v), 4) for v in h1_pre.squeeze().tolist()],
                "hidden1_post": [round(float(v), 4) for v in h1_post.squeeze().tolist()],
                "hidden2_pre": [round(float(v), 4) for v in h2_pre.squeeze().tolist()],
                "hidden2_post": [round(float(v), 4) for v in h2_post.squeeze().tolist()],
                "output": round(float(output.item()), 4),
            },
        })

    # Sort by score descending
    candidates_out.sort(key=lambda c: c["score"], reverse=True)

    return {
        "query": req.description,
        "candidates": candidates_out,
        "n_results": len(candidates_out),
    }
