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
_SYNTHETIC_GROUPS_V5 = _H2_DIR / "mw_synthetic_groups_v5.json"

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

FEATURE_NAMES_V5 = FEATURE_NAMES_V3 + [
    "sim_content",
    "content_density",
    "content_form_alignment",
]

# Active feature names (set when model loads)
FEATURE_NAMES = FEATURE_NAMES_V1
_feature_version = 1
_model_type = "single"  # "single" or "dual_head"

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
    """Load the scorer checkpoint (single-head or dual-head)."""
    global _model, _state_dict, FEATURE_NAMES, _feature_version, _model_type
    if _model is not None:
        return _model

    torch = _load_torch()
    import torch.nn as nn

    ckpt = torch.load(
        str(_CHECKPOINT_PATH), map_location="cpu", weights_only=False
    )
    hidden = ckpt.get("hidden_dim", 32)
    dropout = ckpt.get("dropout", 0.15)
    input_dim = ckpt.get("input_dim", 9)
    _feature_version = ckpt.get("feature_version", 1)
    _model_type = ckpt.get("model_type", "similarity_mw")

    if _feature_version >= 5:
        FEATURE_NAMES = FEATURE_NAMES_V5
    elif _feature_version in (3, 4):
        FEATURE_NAMES = FEATURE_NAMES_V3
    elif _feature_version == 2:
        FEATURE_NAMES = FEATURE_NAMES_V2
    else:
        FEATURE_NAMES = FEATURE_NAMES_V1

    if _model_type == "dual_head":
        head_dim = ckpt.get("head_dim", 24)

        class _DualHeadMLP(nn.Module):
            def __init__(self):
                super().__init__()
                self.backbone = nn.Sequential(
                    nn.Linear(input_dim, hidden),
                    nn.SiLU(), nn.Dropout(dropout),
                    nn.Linear(hidden, hidden),
                    nn.SiLU(), nn.Dropout(dropout),
                )
                self.form_head = nn.Sequential(
                    nn.Linear(hidden, head_dim),
                    nn.SiLU(),
                    nn.Linear(head_dim, 1),
                )
                self.content_head = nn.Sequential(
                    nn.Linear(hidden, head_dim),
                    nn.SiLU(),
                    nn.Linear(head_dim, 1),
                )
            def forward(self, x):
                shared = self.backbone(x)
                return self.form_head(shared), self.content_head(shared)

        model = _DualHeadMLP()
        model.load_state_dict(ckpt["model_state_dict"])
        model.eval()
        _model = model
        _state_dict = ckpt["model_state_dict"]
        return model

    # Single-head model
    mlp = nn.Sequential(
        nn.Linear(input_dim, hidden),
        nn.SiLU(),
        nn.Dropout(dropout),
        nn.Linear(hidden, hidden),
        nn.SiLU(),
        nn.Dropout(dropout),
        nn.Linear(hidden, 1),
    )
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

    if _feature_version >= 5:
        # V5: Dual-head with content features
        if _SYNTHETIC_GROUPS_V5.exists():
            with open(_SYNTHETIC_GROUPS_V5) as f:
                all_groups = json.load(f)
    elif _feature_version == 3:
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
    """Score candidates, return combined scores."""
    torch = _load_torch()
    features = [_candidate_features(c) for c in candidates]
    x = torch.tensor(features, dtype=torch.float32)
    with torch.no_grad():
        if _model_type == "dual_head":
            form_s, content_s = model(x)
            # Alpha blend (default 0.6 form)
            scores = 0.6 * form_s.squeeze(-1) + 0.4 * content_s.squeeze(-1)
            return scores.tolist()
        scores = model(x).squeeze(-1)
    return scores.tolist()


def _score_candidates_dual(
    model, candidates: List[dict]
) -> tuple[List[float], List[float], List[float]]:
    """Score candidates with dual-head model.

    Returns (form_scores, content_scores, combined_scores).
    For single-head models, content_scores are all 0.0.
    """
    torch = _load_torch()
    features = [_candidate_features(c) for c in candidates]
    x = torch.tensor(features, dtype=torch.float32)
    with torch.no_grad():
        if _model_type == "dual_head":
            form_s, content_s = model(x)
            form_list = form_s.squeeze(-1).tolist()
            content_list = content_s.squeeze(-1).tolist()
            combined = [
                0.6 * f + 0.4 * c
                for f, c in zip(form_list, content_list)
            ]
            return form_list, content_list, combined
        scores = model(x).squeeze(-1).tolist()
        return scores, [0.0] * len(scores), scores


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
            label = c.get("form_label", c.get("label", 0.0))
            if label > 0.5:
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
    # Dual-head: backbone.0.weight, Single-head: 0.weight
    w1_key = "backbone.0.weight" if _model_type == "dual_head" else "0.weight"
    w1 = _state_dict.get(w1_key, next(iter(_state_dict.values())))
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
                if _model_type == "dual_head":
                    form_s, content_s = model(x)
                    scores = 0.6 * form_s.squeeze(-1) + 0.4 * content_s.squeeze(-1)
                else:
                    scores = model(x).squeeze(-1)
            top_idx = scores.argmax().item()
            labels = [c.get("form_label", c.get("label", 0.0)) for c in candidates]
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
# Endpoint 2b: Grouped Feature Ablation
# ---------------------------------------------------------------------------
_FEATURE_GROUPS_V3 = {
    "sim_c": {"indices": [0, 1, 2, 3], "label": "Components ColBERT (sim_c_*)"},
    "sim_i": {"indices": [4, 5, 6, 7], "label": "Inputs ColBERT (sim_i_*)"},
    "sim_r": {"indices": [8], "label": "Relationships MiniLM (sim_r)"},
    "structural": {"indices": [9, 10, 11, 12, 13], "label": "Structural DAG"},
}

_FEATURE_GROUPS_V5 = {
    "sim_c": {"indices": [0, 1, 2, 3], "label": "Components ColBERT (sim_c_*)"},
    "sim_i": {"indices": [4, 5, 6, 7], "label": "Inputs ColBERT (sim_i_*)"},
    "sim_r": {"indices": [8], "label": "Relationships MiniLM (sim_r)"},
    "structural": {"indices": [9, 10, 11, 12, 13], "label": "Structural DAG"},
    "content": {"indices": [14, 15, 16], "label": "Content (sim_content, density, alignment)"},
}

_FEATURE_GROUPS_V2 = {
    "similarities": {"indices": [0, 1, 2], "label": "Similarities"},
    "structural": {"indices": [3, 4, 5, 6, 7], "label": "Structural DAG"},
}

_FEATURE_GROUPS_V1 = {
    "similarities": {"indices": [0, 1, 2], "label": "Similarities"},
    "query_norms": {"indices": [3, 4, 5], "label": "Query norms"},
    "candidate_norms": {"indices": [6, 7, 8], "label": "Candidate norms"},
}


@router.get("/ml/group-ablation")
async def group_ablation():
    """Grouped feature ablation — zero entire feature groups and pairwise combos."""
    torch = _load_torch()
    model = _load_model()
    val_groups, _ = _load_groups()

    if _feature_version >= 5:
        groups = _FEATURE_GROUPS_V5
    elif _feature_version in (3, 4):
        groups = _FEATURE_GROUPS_V3
    elif _feature_version == 2:
        groups = _FEATURE_GROUPS_V2
    else:
        groups = _FEATURE_GROUPS_V1

    def compute_accuracy_masked(mask_indices):
        correct = 0
        total_g = 0
        for group in val_groups:
            candidates = group.get("candidates", [])
            if not candidates:
                continue
            features = [_candidate_features(c) for c in candidates]
            x = torch.tensor(features, dtype=torch.float32)
            if mask_indices:
                x[:, mask_indices] = 0.0
            with torch.no_grad():
                if _model_type == "dual_head":
                    form_s, content_s = model(x)
                    scores = 0.6 * form_s.squeeze(-1) + 0.4 * content_s.squeeze(-1)
                else:
                    scores = model(x).squeeze(-1)
            top_idx = scores.argmax().item()
            labels = [c.get("form_label", c.get("label", 0.0)) for c in candidates]
            if labels[top_idx] > 0.5:
                correct += 1
            total_g += 1
        return correct / total_g if total_g > 0 else 0.0

    baseline = compute_accuracy_masked([])

    # Single-group ablation
    single_results = []
    for name, info in groups.items():
        acc = compute_accuracy_masked(info["indices"])
        single_results.append({
            "group": name,
            "label": info["label"],
            "indices": info["indices"],
            "features_zeroed": [FEATURE_NAMES[i] for i in info["indices"]],
            "accuracy": round(acc, 4),
            "accuracy_drop": round(baseline - acc, 4),
        })

    # Pairwise group ablation
    group_names = list(groups.keys())
    pairwise_results = []
    for i in range(len(group_names)):
        for j in range(i + 1, len(group_names)):
            g1, g2 = group_names[i], group_names[j]
            combined = groups[g1]["indices"] + groups[g2]["indices"]
            acc = compute_accuracy_masked(combined)
            pairwise_results.append({
                "groups": [g1, g2],
                "labels": [groups[g1]["label"], groups[g2]["label"]],
                "indices": combined,
                "accuracy": round(acc, 4),
                "accuracy_drop": round(baseline - acc, 4),
            })

    # "Only this group" ablation — zero everything EXCEPT this group
    only_results = []
    all_indices = list(range(len(FEATURE_NAMES)))
    for name, info in groups.items():
        keep = set(info["indices"])
        mask = [i for i in all_indices if i not in keep]
        acc = compute_accuracy_masked(mask)
        only_results.append({
            "group": name,
            "label": info["label"],
            "accuracy_with_only_this_group": round(acc, 4),
        })

    return {
        "feature_version": _feature_version,
        "baseline_accuracy": round(baseline, 4),
        "n_features": len(FEATURE_NAMES),
        "n_groups": len(groups),
        "single_group_ablation": single_results,
        "pairwise_group_ablation": pairwise_results,
        "only_group_ablation": only_results,
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
            if _model_type == "dual_head":
                form_s, content_s = model(x)
                scores = 0.6 * form_s.squeeze(-1) + 0.4 * content_s.squeeze(-1)
            else:
                scores = model(x).squeeze(-1)

        score_list = scores.tolist()
        labels = [c.get("form_label", c.get("label", 0.0)) for c in candidates]

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
            "expected": next((c.get("name", "?") for c in candidates if c.get("form_label", c.get("label", 0)) > 0.5), "?"),
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
    total_params = sum(w.numel() for w in _state_dict.values())

    if _model_type == "dual_head":
        # Dual-head: backbone.0/backbone.3 + form_head.0/form_head.2 + content_head.0/content_head.2
        hidden = _state_dict["backbone.0.weight"].shape[0]
        head_dim = _state_dict["form_head.0.weight"].shape[0]
        backbone_specs = [
            (f"backbone.layer1 ({n_in}→{hidden})", "backbone.0", FEATURE_NAMES, hidden),
            (f"backbone.layer2 ({hidden}→{hidden})", "backbone.3", None, hidden),
        ]
        head_specs = [
            (f"form_head.layer1 ({hidden}→{head_dim})", "form_head.0", None, head_dim),
            (f"form_head.output ({head_dim}→1)", "form_head.2", None, 1),
            (f"content_head.layer1 ({hidden}→{head_dim})", "content_head.0", None, head_dim),
            (f"content_head.output ({head_dim}→1)", "content_head.2", None, 1),
        ]
        layer_specs = backbone_specs + head_specs
    else:
        # Single-head: Sequential layers 0, 3, 6
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
            if _model_type == "dual_head":
                # Backbone
                h1_pre = model.backbone[0](x)       # Linear in→hidden
                h1_post = model.backbone[1](h1_pre)  # SiLU
                # skip dropout [2] in eval mode
                h2_pre = model.backbone[3](h1_post)  # Linear hidden→hidden
                h2_post = model.backbone[4](h2_pre)  # SiLU
                # Form head
                fh1 = model.form_head[0](h2_post)    # Linear hidden→head_dim
                fh2 = model.form_head[1](fh1)        # SiLU
                form_out = model.form_head[2](fh2)    # Linear head_dim→1
                # Content head
                ch1 = model.content_head[0](h2_post)  # Linear hidden→head_dim
                ch2 = model.content_head[1](ch1)      # SiLU
                content_out = model.content_head[2](ch2)  # Linear head_dim→1
                # Combined
                output = 0.6 * form_out + 0.4 * content_out
                extra_activations = {
                    "form_head_hidden": [round(float(v), 4) for v in fh2.squeeze().tolist()] if fh2.dim() > 1 else [round(float(fh2.item()), 4)],
                    "form_score": round(float(form_out.item()), 4),
                    "content_head_hidden": [round(float(v), 4) for v in ch2.squeeze().tolist()] if ch2.dim() > 1 else [round(float(ch2.item()), 4)],
                    "content_score": round(float(content_out.item()), 4),
                }
            else:
                h1_pre = model[0](x)          # Linear in→hidden
                h1_post = model[1](h1_pre)    # SiLU
                # skip dropout [2] in eval mode
                h2_pre = model[3](h1_post)    # Linear hidden→hidden
                h2_post = model[4](h2_pre)    # SiLU
                output = model[6](h2_post)    # Linear hidden→1
                extra_activations = {}

        activations = {
            "hidden1_pre": [round(float(v), 4) for v in h1_pre.squeeze().tolist()],
            "hidden1_post": [round(float(v), 4) for v in h1_post.squeeze().tolist()],
            "hidden2_pre": [round(float(v), 4) for v in h2_pre.squeeze().tolist()],
            "hidden2_post": [round(float(v), 4) for v in h2_post.squeeze().tolist()],
            "output": round(float(output.item()), 4),
            **extra_activations,
        }

        candidates_out.append({
            "name": r.get("name", "?"),
            "type": r.get("type", "?"),
            "symbol": r.get("symbol", "?"),
            "score": round(float(output.item()), 4),
            "features": {k: round(float(v), 4) for k, v in features.items()},
            "activations": activations,
        })

    # Sort by score descending
    candidates_out.sort(key=lambda c: c["score"], reverse=True)

    return {
        "query": req.description,
        "candidates": candidates_out,
        "n_results": len(candidates_out),
    }


# ---------------------------------------------------------------------------
# Endpoint 6: Model Info (architecture, version, type)
# ---------------------------------------------------------------------------
@router.get("/ml/model-info")
async def model_info():
    """Model metadata: type, version, feature names, architecture."""
    _load_model()
    torch = _load_torch()

    n_params = sum(
        p.numel()
        for p in _model.parameters()
    )

    ckpt_meta = {}
    if _CHECKPOINT_PATH.exists():
        ckpt = torch.load(
            str(_CHECKPOINT_PATH),
            map_location="cpu",
            weights_only=False,
        )
        for k in (
            "model_type", "feature_version", "input_dim",
            "hidden_dim", "head_dim", "dropout",
            "epoch", "val_accuracy", "domain",
            "form_weight", "content_weight",
            "val_form_top1", "val_content_top1",
        ):
            if k in ckpt:
                ckpt_meta[k] = ckpt[k]

    return {
        "model_type": _model_type,
        "feature_version": _feature_version,
        "feature_names": FEATURE_NAMES,
        "n_features": len(FEATURE_NAMES),
        "n_params": n_params,
        "is_dual_head": _model_type == "dual_head",
        "checkpoint": str(_CHECKPOINT_PATH),
        "checkpoint_exists": _CHECKPOINT_PATH.exists(),
        "checkpoint_meta": ckpt_meta,
    }


# ---------------------------------------------------------------------------
# Endpoint 7: Dual-Score Breakdown (form vs content per candidate)
# ---------------------------------------------------------------------------
class DualScoreRequest(BaseModel):
    description: str
    content_text: Optional[str] = None
    limit: int = 10


@router.post("/ml/dual-score-breakdown")
async def dual_score_breakdown(req: DualScoreRequest):
    """Run a live query and return form_score + content_score per candidate.

    Shows how form and content heads independently rank candidates,
    enabling diagnosis of content-form alignment quality.
    """
    torch = _load_torch()
    model = _load_model()

    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        wrapper = get_card_framework_wrapper()

        results = wrapper.search_hybrid_dispatch(
            description=req.description,
            component_paths=None,
            limit=req.limit,
            token_ratio=1.0,
            content_feedback="positive",
            form_feedback="positive",
            include_classes=True,
            content_text=req.content_text,
        )
        class_results, content_patterns, form_patterns = results

        all_results = (
            list(class_results or [])
            + list(content_patterns or [])
            + list(form_patterns or [])
        )

        # Deduplicate
        seen = set()
        deduped = []
        for r in all_results:
            rid = r.get("id", id(r))
            if rid not in seen:
                seen.add(rid)
                deduped.append(r)

    except Exception as e:
        return {"error": f"Search failed: {e}", "candidates": []}

    candidates_out = []
    for r in deduped[:req.limit]:
        entry = {
            "name": r.get("name", "?"),
            "type": r.get("type", "?"),
            "symbol": r.get("symbol", ""),
            "combined_score": round(r.get("score", 0.0), 4),
            "sim_components": round(
                r.get("sim_components", 0.0), 4
            ),
            "sim_relationships": round(
                r.get("sim_relationships", 0.0), 4
            ),
            "sim_inputs": round(
                r.get("sim_inputs", 0.0), 4
            ),
            "sim_content": round(
                r.get("sim_content", 0.0), 4
            ),
        }

        # If dual-head, compute per-head scores
        if _model_type == "dual_head":
            feat_vec = [
                r.get(f, 0.0) for f in FEATURE_NAMES
            ]
            x = torch.tensor([feat_vec], dtype=torch.float32)
            with torch.no_grad():
                form_s, content_s = model(x)
            entry["form_score"] = round(
                float(form_s.item()), 4
            )
            entry["content_score"] = round(
                float(content_s.item()), 4
            )
            entry["content_drives_form"] = (
                entry["content_score"] > entry["form_score"]
            )
        else:
            entry["form_score"] = entry["combined_score"]
            entry["content_score"] = 0.0
            entry["content_drives_form"] = False

        candidates_out.append(entry)

    # Sort by combined score
    candidates_out.sort(
        key=lambda c: c["combined_score"], reverse=True
    )

    # Compute rank correlation between form and content heads
    form_ranks = sorted(
        range(len(candidates_out)),
        key=lambda i: candidates_out[i]["form_score"],
        reverse=True,
    )
    content_ranks = sorted(
        range(len(candidates_out)),
        key=lambda i: candidates_out[i]["content_score"],
        reverse=True,
    )

    # Rank agreement: how many of top-3 by form are also top-3 by content
    form_top3 = set(form_ranks[:3])
    content_top3 = set(content_ranks[:3])
    top3_overlap = len(form_top3 & content_top3)

    return {
        "query": req.description,
        "content_text": req.content_text,
        "model_type": _model_type,
        "is_dual_head": _model_type == "dual_head",
        "candidates": candidates_out,
        "n_results": len(candidates_out),
        "diagnostics": {
            "top3_form_content_overlap": top3_overlap,
            "form_top1": (
                candidates_out[form_ranks[0]]["name"]
                if form_ranks else "?"
            ),
            "content_top1": (
                candidates_out[content_ranks[0]]["name"]
                if content_ranks else "?"
            ),
            "heads_agree_on_top1": (
                form_ranks[0] == content_ranks[0]
                if form_ranks and content_ranks
                else False
            ),
        },
    }


# ---------------------------------------------------------------------------
# Endpoint 8: Content-Form Alignment Matrix
# ---------------------------------------------------------------------------
@router.get("/ml/content-form-matrix")
async def content_form_matrix():
    """Show content-form alignment scores: which content types
    map to which component forms based on the dual-head scorer.

    Returns a matrix of (content_type, component) → content_score.
    """
    model = _load_model()
    if _model_type != "dual_head":
        return {
            "error": "Requires dual-head model (V5+)",
            "model_type": _model_type,
        }

    torch = _load_torch()
    val_groups, _ = _load_groups()

    # Collect per-candidate form and content scores
    matrix_data = []
    for group in val_groups:
        candidates = group.get("candidates", [])
        if not candidates:
            continue
        features = [_candidate_features(c) for c in candidates]
        x = torch.tensor(features, dtype=torch.float32)
        with torch.no_grad():
            form_s, content_s = model(x)
        form_list = form_s.squeeze(-1).tolist()
        content_list = content_s.squeeze(-1).tolist()

        for c, fs, cs in zip(candidates, form_list, content_list):
            matrix_data.append({
                "name": c.get("name", "?"),
                "form_label": c.get("form_label", c.get("label", 0)),
                "content_label": c.get("content_label", 0),
                "form_score": round(fs, 4),
                "content_score": round(cs, 4),
            })

    # Aggregate by component name
    from collections import defaultdict
    by_component = defaultdict(
        lambda: {
            "form_scores": [], "content_scores": [],
            "form_correct": 0, "content_correct": 0, "total": 0,
        }
    )
    for d in matrix_data:
        entry = by_component[d["name"]]
        entry["form_scores"].append(d["form_score"])
        entry["content_scores"].append(d["content_score"])
        if d["form_label"] > 0.5:
            entry["form_correct"] += 1
        if d["content_label"] > 0.5:
            entry["content_correct"] += 1
        entry["total"] += 1

    summary = []
    for name, data in sorted(by_component.items()):
        fs = data["form_scores"]
        cs = data["content_scores"]
        summary.append({
            "component": name,
            "mean_form_score": round(np.mean(fs), 4),
            "mean_content_score": round(np.mean(cs), 4),
            "form_accuracy": round(
                data["form_correct"] / max(data["total"], 1), 3
            ),
            "content_accuracy": round(
                data["content_correct"] / max(data["total"], 1), 3
            ),
            "n_samples": data["total"],
        })

    return {
        "model_type": _model_type,
        "n_candidates_scored": len(matrix_data),
        "components": summary,
    }


# ---------------------------------------------------------------------------
# Endpoint 9: Content-Specific Ablation (per-head accuracy)
# ---------------------------------------------------------------------------
@router.get("/ml/content-ablation")
async def content_ablation():
    """Per-head ablation: zero each feature and measure form/content/combined top1 independently."""
    torch = _load_torch()
    model = _load_model()
    val_groups, _ = _load_groups()

    def compute_per_head_accuracy(feature_mask=None):
        form_ok = content_ok = combined_ok = total = 0
        content_total = 0
        for group in val_groups:
            candidates = group.get("candidates", [])
            if not candidates:
                continue
            features = [_candidate_features(c) for c in candidates]
            x = torch.tensor(features, dtype=torch.float32)
            if feature_mask is not None:
                x[:, feature_mask] = 0.0
            with torch.no_grad():
                if _model_type == "dual_head":
                    form_s, content_s = model(x)
                    form_scores = form_s.squeeze(-1)
                    content_scores = content_s.squeeze(-1)
                    combined = 0.6 * form_scores + 0.4 * content_scores
                else:
                    combined = model(x).squeeze(-1)
                    form_scores = combined
                    content_scores = combined

            form_labels = [c.get("form_label", c.get("label", 0.0)) for c in candidates]
            content_labels = [c.get("content_label", 0.0) for c in candidates]

            # Form top1
            top_combined = combined.argmax().item()
            if form_labels[top_combined] > 0.5:
                combined_ok += 1
            top_form = form_scores.argmax().item()
            if form_labels[top_form] > 0.5:
                form_ok += 1
            total += 1

            # Content top1 (only if group has content labels)
            if any(cl > 0.5 for cl in content_labels):
                top_content = content_scores.argmax().item()
                if content_labels[top_content] > 0.5:
                    content_ok += 1
                content_total += 1

        return (
            form_ok / max(total, 1),
            content_ok / max(content_total, 1),
            combined_ok / max(total, 1),
        )

    base_form, base_content, base_combined = compute_per_head_accuracy()
    n_features = len(FEATURE_NAMES)
    form_abl, content_abl, combined_abl = [], [], []
    for i in range(n_features):
        f, c, cb = compute_per_head_accuracy(feature_mask=i)
        form_abl.append(round(base_form - f, 4))
        content_abl.append(round(base_content - c, 4))
        combined_abl.append(round(base_combined - cb, 4))

    return {
        "feature_names": FEATURE_NAMES,
        "form_ablation": form_abl,
        "content_ablation": content_abl,
        "combined_ablation": combined_abl,
        "baseline_form": round(base_form, 4),
        "baseline_content": round(base_content, 4),
        "baseline_combined": round(base_combined, 4),
    }


# ---------------------------------------------------------------------------
# Endpoint 10: Alpha Sensitivity Sweep
# ---------------------------------------------------------------------------
@router.get("/ml/alpha-sweep")
async def alpha_sweep():
    """Sweep alpha from 0 to 1 and measure combined accuracy at each value."""
    torch = _load_torch()
    model = _load_model()
    val_groups, _ = _load_groups()

    if _model_type != "dual_head":
        return {"error": "Requires dual-head model", "model_type": _model_type}

    # Pre-compute all form/content scores once
    group_data = []
    for group in val_groups:
        candidates = group.get("candidates", [])
        if not candidates:
            continue
        features = [_candidate_features(c) for c in candidates]
        x = torch.tensor(features, dtype=torch.float32)
        with torch.no_grad():
            form_s, content_s = model(x)
        form_labels = [c.get("form_label", c.get("label", 0.0)) for c in candidates]
        content_labels = [c.get("content_label", 0.0) for c in candidates]
        group_data.append({
            "form_scores": form_s.squeeze(-1),
            "content_scores": content_s.squeeze(-1),
            "form_labels": form_labels,
            "content_labels": content_labels,
        })

    alphas = [round(a * 0.05, 2) for a in range(21)]  # 0.0..1.0
    combined_accs = []
    for alpha in alphas:
        correct = 0
        for gd in group_data:
            combined = alpha * gd["form_scores"] + (1 - alpha) * gd["content_scores"]
            top_idx = combined.argmax().item()
            if gd["form_labels"][top_idx] > 0.5:
                correct += 1
        combined_accs.append(round(correct / max(len(group_data), 1), 4))

    # Form-only and content-only accuracy (constant across alpha)
    form_correct = sum(
        1 for gd in group_data
        if gd["form_labels"][gd["form_scores"].argmax().item()] > 0.5
    )
    content_total = 0
    content_correct = 0
    for gd in group_data:
        if any(cl > 0.5 for cl in gd["content_labels"]):
            top_c = gd["content_scores"].argmax().item()
            if gd["content_labels"][top_c] > 0.5:
                content_correct += 1
            content_total += 1

    optimal_idx = max(range(len(combined_accs)), key=lambda i: combined_accs[i])

    return {
        "alphas": alphas,
        "combined_accuracy": combined_accs,
        "form_accuracy": round(form_correct / max(len(group_data), 1), 4),
        "content_accuracy": round(content_correct / max(content_total, 1), 4),
        "optimal_alpha": alphas[optimal_idx],
        "optimal_accuracy": combined_accs[optimal_idx],
        "current_alpha": 0.6,
        "n_groups": len(group_data),
    }


# ---------------------------------------------------------------------------
# Endpoint 11: Per-Head Confusion Matrix
# ---------------------------------------------------------------------------
@router.get("/ml/head-confusion")
async def head_confusion():
    """Confusion matrices for form and content heads independently."""
    torch = _load_torch()
    model = _load_model()
    val_groups, _ = _load_groups()

    from collections import defaultdict

    form_confusion = defaultdict(lambda: defaultdict(int))
    content_confusion = defaultdict(lambda: defaultdict(int))
    form_correct = 0
    content_correct = 0
    form_total = 0
    content_total = 0

    for group in val_groups:
        candidates = group.get("candidates", [])
        if not candidates:
            continue
        features = [_candidate_features(c) for c in candidates]
        x = torch.tensor(features, dtype=torch.float32)
        with torch.no_grad():
            if _model_type == "dual_head":
                form_s, content_s = model(x)
                form_scores = form_s.squeeze(-1)
                content_scores = content_s.squeeze(-1)
            else:
                scores = model(x).squeeze(-1)
                form_scores = scores
                content_scores = scores

        form_labels = [c.get("form_label", c.get("label", 0.0)) for c in candidates]
        content_labels = [c.get("content_label", 0.0) for c in candidates]

        # Form head: predicted vs expected
        form_predicted_idx = form_scores.argmax().item()
        form_expected_idx = next(
            (i for i, l in enumerate(form_labels) if l > 0.5), None
        )
        if form_expected_idx is not None:
            predicted_name = candidates[form_predicted_idx].get("name", "?")
            expected_name = candidates[form_expected_idx].get("name", "?")
            form_confusion[predicted_name][expected_name] += 1
            # Correct if the predicted candidate has a positive label
            if form_labels[form_predicted_idx] > 0.5:
                form_correct += 1
            form_total += 1

        # Content head: predicted vs expected
        if any(cl > 0.5 for cl in content_labels):
            content_predicted_idx = content_scores.argmax().item()
            content_expected_idx = next(
                (i for i, l in enumerate(content_labels) if l > 0.5), None
            )
            if content_expected_idx is not None:
                predicted_name = candidates[content_predicted_idx].get("name", "?")
                expected_name = candidates[content_expected_idx].get("name", "?")
                content_confusion[predicted_name][expected_name] += 1
                if content_labels[content_predicted_idx] > 0.5:
                    content_correct += 1
                content_total += 1

    def build_matrix(confusion_dict):
        labels = sorted(set(
            list(confusion_dict.keys())
            + [e for row in confusion_dict.values() for e in row.keys()]
        ))
        label_idx = {l: i for i, l in enumerate(labels)}
        matrix = [[0] * len(labels) for _ in labels]
        for predicted, expecteds in confusion_dict.items():
            for expected, count in expecteds.items():
                matrix[label_idx[predicted]][label_idx[expected]] = count
        return labels, matrix

    form_labels_list, form_matrix = build_matrix(form_confusion)
    content_labels_list, content_matrix = build_matrix(content_confusion)

    return {
        "form_head": {
            "labels": form_labels_list,
            "matrix": form_matrix,
            "accuracy": round(form_correct / max(form_total, 1), 4),
            "n_groups": form_total,
        },
        "content_head": {
            "labels": content_labels_list,
            "matrix": content_matrix,
            "accuracy": round(content_correct / max(content_total, 1), 4),
            "n_groups": content_total,
        },
    }


# ---------------------------------------------------------------------------
# Endpoint 12: Content Accuracy Detail (per-group rank histogram)
# ---------------------------------------------------------------------------
@router.get("/ml/content-accuracy-detail")
async def content_accuracy_detail():
    """Per-group form and content rank detail with histograms."""
    torch = _load_torch()
    model = _load_model()
    val_groups, _ = _load_groups()

    groups_out = []
    form_ranks = []
    content_ranks = []

    for group in val_groups:
        candidates = group.get("candidates", [])
        if not candidates:
            continue
        features = [_candidate_features(c) for c in candidates]
        x = torch.tensor(features, dtype=torch.float32)
        with torch.no_grad():
            if _model_type == "dual_head":
                form_s, content_s = model(x)
                form_scores = form_s.squeeze(-1).tolist()
                content_scores = content_s.squeeze(-1).tolist()
            else:
                scores = model(x).squeeze(-1).tolist()
                form_scores = scores
                content_scores = scores

        form_labels = [c.get("form_label", c.get("label", 0.0)) for c in candidates]
        content_labels = [c.get("content_label", 0.0) for c in candidates]

        # Form rank of first positive
        form_sorted = sorted(range(len(form_scores)), key=lambda i: form_scores[i], reverse=True)
        form_rank = next(
            (rank + 1 for rank, idx in enumerate(form_sorted) if form_labels[idx] > 0.5),
            len(candidates),
        )
        form_margin = 0.0
        form_pos = [s for s, l in zip(form_scores, form_labels) if l > 0.5]
        form_neg = [s for s, l in zip(form_scores, form_labels) if l <= 0.5]
        if form_pos and form_neg:
            form_margin = max(form_pos) - max(form_neg)
        form_ranks.append(form_rank)

        # Content rank of first positive (only if content labels exist)
        has_content = any(cl > 0.5 for cl in content_labels)
        content_rank = 0
        content_margin = 0.0
        if has_content:
            content_sorted = sorted(range(len(content_scores)), key=lambda i: content_scores[i], reverse=True)
            content_rank = next(
                (rank + 1 for rank, idx in enumerate(content_sorted) if content_labels[idx] > 0.5),
                len(candidates),
            )
            content_pos = [s for s, l in zip(content_scores, content_labels) if l > 0.5]
            content_neg = [s for s, l in zip(content_scores, content_labels) if l <= 0.5]
            if content_pos and content_neg:
                content_margin = max(content_pos) - max(content_neg)
            content_ranks.append(content_rank)

        group_name = group.get("query_name") or group.get("query_id", "unknown")
        groups_out.append({
            "name": group_name,
            "form_rank": form_rank,
            "form_margin": round(form_margin, 4),
            "content_rank": content_rank if has_content else None,
            "content_margin": round(content_margin, 4) if has_content else None,
            "has_content_labels": has_content,
            "n_candidates": len(candidates),
        })

    # Build rank histograms (rank 1..max)
    max_rank = max(max(form_ranks, default=1), max(content_ranks, default=1))
    form_hist = [0] * max_rank
    content_hist = [0] * max_rank
    for r in form_ranks:
        form_hist[r - 1] += 1
    for r in content_ranks:
        content_hist[r - 1] += 1

    # MRR
    form_mrr = sum(1.0 / r for r in form_ranks) / max(len(form_ranks), 1)
    content_mrr = sum(1.0 / r for r in content_ranks) / max(len(content_ranks), 1)

    return {
        "groups": groups_out,
        "form_rank_histogram": form_hist,
        "content_rank_histogram": content_hist,
        "form_top1": round(sum(1 for r in form_ranks if r == 1) / max(len(form_ranks), 1), 4),
        "content_top1": round(sum(1 for r in content_ranks if r == 1) / max(len(content_ranks), 1), 4),
        "form_mrr": round(form_mrr, 4),
        "content_mrr": round(content_mrr, 4),
        "n_groups": len(groups_out),
        "n_groups_with_content": len(content_ranks),
    }
