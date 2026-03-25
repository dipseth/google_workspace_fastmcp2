"""Train SimilarityScorer on Module Wrapper data from Qdrant.

Uses the extracted MW query groups (ColBERT MaxSim + MiniLM cosine)
with listwise contrastive loss.

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.train_mw
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from .mw_extract import (  # noqa: E402
    MWPoint,
    MWQueryGroup,
    build_query_groups,
    compute_similarity_features,
    connect_qdrant,
    extract_all_points,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataset: precompute similarity features per (query, candidate) pair
# ---------------------------------------------------------------------------


def load_synthetic_groups(path: str, feature_version: int = 1) -> list[MWQueryGroup]:
    """Load synthetic groups from JSON and convert to MWQueryGroup format.

    Args:
        path: Path to synthetic groups JSON
        feature_version: 1-4 = single label, 5 = dual labels (form + content)
    """
    import json
    from research.trm.h2.generate_training_data import (
        FEATURE_NAMES_V2,
        FEATURE_NAMES_V3,
        FEATURE_NAMES_V5,
    )

    data = json.loads(Path(path).read_text())
    logger.info(
        f"Loading {len(data)} synthetic groups from {path} "
        f"(feature_version={feature_version})"
    )

    groups = []
    for g in data:
        query = MWPoint(
            point_id=g["query_id"],
            point_type="synthetic",
            name=g.get("query_description", ""),
            full_path="",
            symbol="",
            comp_vectors=None, inp_vectors=None, rel_vector=None,
            content_feedback="positive",
            form_feedback="positive",
            docstring=g.get("query_dsl", ""),
            parent_paths=g.get("query_components", []),
        )

        candidates = []
        form_labels = []
        content_labels = []
        for c in g["candidates"]:
            cand = MWPoint(
                point_id="", point_type="class",
                name=c["name"], full_path=c.get("full_path", ""),
                symbol="",
                comp_vectors=None, inp_vectors=None, rel_vector=None,
                content_feedback=None, form_feedback=None,
                docstring="",
            )

            if feature_version >= 5:
                cand._precomputed_features = np.array([
                    c.get(f, 0.0) for f in FEATURE_NAMES_V5
                ], dtype=np.float32)
            elif feature_version == 3 or feature_version == 4:
                cand._precomputed_features = np.array([
                    c.get(f, 0.0) for f in FEATURE_NAMES_V3
                ], dtype=np.float32)
            elif feature_version == 2:
                cand._precomputed_features = np.array([
                    c.get(f, 0.0) for f in FEATURE_NAMES_V2
                ], dtype=np.float32)
            else:
                cand._precomputed_features = np.array([
                    c["sim_components"], c["sim_inputs"],
                    c["sim_relationships"],
                    c.get("q_comp_norm", 0),
                    c.get("q_inp_norm", 0),
                    c.get("q_rel_norm", 0),
                    c.get("c_comp_norm", 0),
                    c.get("c_inp_norm", 0),
                    c.get("c_rel_norm", 0),
                ], dtype=np.float32)
            candidates.append(cand)

            # Form label (backward compat: "label" or "form_label")
            form_labels.append(
                c.get("form_label", c.get("label", 0.0))
            )
            # Content label (V5+, defaults to 0.0 for older data)
            content_labels.append(c.get("content_label", 0.0))

        if any(l == 1.0 for l in form_labels) and len(candidates) >= 2:
            groups.append(MWQueryGroup(
                query=query,
                candidates=candidates,
                labels=form_labels,
                content_labels=content_labels,
            ))

    logger.info(f"Loaded {len(groups)} valid synthetic groups")
    return groups


class MWListwiseDataset(Dataset):
    """Listwise dataset for MW query groups with precomputed features.

    Supports single-label (V1-V4) and dual-label (V5+) modes.
    Gaussian noise augmentation and feature dropout during training.
    """

    def __init__(
        self,
        groups: list[MWQueryGroup],
        max_k: int = 0,
        noise_std: float = 0.0,
        feature_dropout: float = 0.0,
        training: bool = False,
        dual_labels: bool = False,
    ):
        self.max_k = max_k or max(len(g.labels) for g in groups)
        self.noise_std = noise_std
        self.feature_dropout = feature_dropout
        self.training = training
        self.dual_labels = dual_labels

        # Precompute all features
        self.features = []
        self.form_labels = []
        self.content_labels = []
        self.masks = []

        for g in groups:
            K = len(g.labels)
            pad = self.max_k - K

            feats = []
            for cand in g.candidates:
                # Use precomputed features if available (synthetic data)
                if hasattr(cand, '_precomputed_features'):
                    feats.append(cand._precomputed_features)
                else:
                    f = compute_similarity_features(g.query, cand)
                    feats.append(f)

            feat_tensor = torch.from_numpy(np.stack(feats))
            feat_dim = feat_tensor.shape[1]
            if pad > 0:
                feat_tensor = torch.cat([feat_tensor, torch.zeros(pad, feat_dim)])

            # Form labels (always present — backward compat with "labels")
            form_labels = g.labels
            form_tensor = torch.tensor(
                form_labels + [0.0] * pad, dtype=torch.float32
            )

            # Content labels (optional — from content_labels attr or zeros)
            if dual_labels and hasattr(g, 'content_labels') and g.content_labels:
                c_labels = g.content_labels
            else:
                c_labels = [0.0] * K
            content_tensor = torch.tensor(
                c_labels + [0.0] * pad, dtype=torch.float32
            )

            mask_tensor = torch.cat([torch.ones(K), torch.zeros(pad)])

            self.features.append(feat_tensor)
            self.form_labels.append(form_tensor)
            self.content_labels.append(content_tensor)
            self.masks.append(mask_tensor)

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        feats = self.features[idx].clone()
        form_labels = self.form_labels[idx]
        content_labels = self.content_labels[idx]
        mask = self.masks[idx]

        if self.training:
            # Gaussian noise augmentation
            if self.noise_std > 0:
                noise = torch.randn_like(feats) * self.noise_std
                feats = feats + noise * mask.unsqueeze(-1)

            # Feature dropout: randomly zero 1 feature
            if self.feature_dropout > 0 and torch.rand(1).item() < self.feature_dropout:
                feat_dim = feats.shape[1]
                drop_idx = torch.randint(0, feat_dim, (1,)).item()
                feats[:, drop_idx] = 0.0

            # Random candidate shuffle (preserves label alignment)
            valid_k = int(mask.sum().item())
            if valid_k > 1:
                perm = torch.randperm(valid_k)
                feats[:valid_k] = feats[perm]
                form_labels = form_labels.clone()
                form_labels[:valid_k] = form_labels[perm]
                content_labels = content_labels.clone()
                content_labels[:valid_k] = content_labels[perm]

        if self.dual_labels:
            return {
                "features": feats,
                "form_labels": form_labels,
                "content_labels": content_labels,
                "mask": mask,
            }
        # Backward compat: single-label mode
        return {"features": feats, "labels": form_labels, "mask": mask}


# ---------------------------------------------------------------------------
# Model: SimilarityScorer for MW (same 9 features as game POC)
# ---------------------------------------------------------------------------


class SimilarityScorerMW(nn.Module):
    """Learned scoring on MW similarity + structural features.

    V1 (9 features): 3 similarities + 6 norms
    V2 (8 features): 3 similarities + 5 structural (parent/child/sibling/depth/ancestors)
    V3 (14 features): 8 decomposed ColBERT MaxSim + 1 dense cosine + 5 structural
    """

    def __init__(self, input_dim: int = 9, hidden_dim: int = 32, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.input_dim = input_dim
        layers: list[nn.Module] = []
        prev = input_dim
        for _ in range(num_layers):
            layers.extend([nn.Linear(prev, hidden_dim), nn.SiLU(), nn.Dropout(dropout)])
            prev = hidden_dim
        layers.append(nn.Linear(prev, 1))
        self.mlp = nn.Sequential(*layers)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        """features: [B, input_dim] → scores: [B, 1]"""
        return self.mlp(features)

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class DualHeadScorerMW(nn.Module):
    """Dual-head scorer: form_score + content_score.

    Shared backbone learns joint representations, then two heads
    specialize: form_head predicts structural match, content_head
    predicts content-form affinity.

    V5 (17 features): V3 decomposed MaxSim (8) + relationships (1)
        + structural (5) + sim_content (1) + content_density (1)
        + content_form_alignment (1)
    """

    def __init__(
        self,
        input_dim: int = 17,
        hidden_dim: int = 48,
        head_dim: int = 24,
        dropout: float = 0.15,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.head_dim = head_dim

        # Shared backbone
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.SiLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Dropout(dropout),
        )

        # Form head: structural match scoring
        self.form_head = nn.Sequential(
            nn.Linear(hidden_dim, head_dim),
            nn.SiLU(),
            nn.Linear(head_dim, 1),
        )

        # Content head: content-form affinity scoring
        self.content_head = nn.Sequential(
            nn.Linear(hidden_dim, head_dim),
            nn.SiLU(),
            nn.Linear(head_dim, 1),
        )

    def forward(
        self, features: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """features: [B, input_dim] → (form_scores: [B, 1], content_scores: [B, 1])"""
        shared = self.backbone(features)
        form_scores = self.form_head(shared)
        content_scores = self.content_head(shared)
        return form_scores, content_scores

    def count_parameters(self):
        return sum(
            p.numel() for p in self.parameters() if p.requires_grad
        )


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def compute_loss(model, batch, device):
    features = batch["features"].to(device)  # [B, K, 9]
    labels = batch["labels"].to(device)  # [B, K]
    mask = batch["mask"].to(device)  # [B, K]

    B, K, Fd = features.shape

    # Score all candidates: [B, K, 9] → [B*K, 9] → [B*K, 1] → [B, K]
    scores = model(features.reshape(B * K, Fd)).squeeze(-1).reshape(B, K)
    scores = scores.masked_fill(mask == 0, -1e9)

    # Listwise cross-entropy
    label_sums = labels.sum(dim=-1, keepdim=True).clamp(min=1.0)
    target_dist = labels / label_sums
    log_probs = F.log_softmax(scores, dim=-1)
    loss = -(target_dist * log_probs).sum(dim=-1).mean()

    with torch.no_grad():
        # Top-1 accuracy
        top1 = scores.argmax(dim=-1)
        correct1 = labels[torch.arange(B, device=device), top1]
        acc1 = correct1.mean().item()

        # Top-3 accuracy
        top3 = scores.topk(min(3, K), dim=-1).indices
        correct3 = torch.zeros(B, device=device)
        for i in range(top3.shape[1]):
            correct3 += labels[torch.arange(B, device=device), top3[:, i]]
        acc3 = (correct3 > 0).float().mean().item()

        # MRR (Mean Reciprocal Rank)
        sorted_indices = scores.argsort(dim=-1, descending=True)
        mrr = torch.zeros(B, device=device)
        for i in range(B):
            for rank, idx in enumerate(sorted_indices[i]):
                if labels[i, idx] > 0:
                    mrr[i] = 1.0 / (rank + 1)
                    break
        mrr_val = mrr.mean().item()

    return loss, {"loss": loss.item(), "accuracy": acc1, "top3": acc3, "mrr": mrr_val}


def _listwise_ce(scores, labels, mask):
    """Listwise cross-entropy for a single head."""
    scores = scores.masked_fill(mask == 0, -1e9)
    label_sums = labels.sum(dim=-1, keepdim=True).clamp(min=1.0)
    target_dist = labels / label_sums
    log_probs = F.log_softmax(scores, dim=-1)
    return -(target_dist * log_probs).sum(dim=-1)


def _head_metrics(scores, labels, device):
    """Compute top-1, top-3, MRR for a single head."""
    B, K = scores.shape
    top1 = scores.argmax(dim=-1)
    correct1 = labels[torch.arange(B, device=device), top1]
    acc1 = correct1.mean().item()

    top3 = scores.topk(min(3, K), dim=-1).indices
    correct3 = torch.zeros(B, device=device)
    for i in range(top3.shape[1]):
        correct3 += labels[torch.arange(B, device=device), top3[:, i]]
    acc3 = (correct3 > 0).float().mean().item()

    sorted_idx = scores.argsort(dim=-1, descending=True)
    mrr = torch.zeros(B, device=device)
    for i in range(B):
        for rank, idx in enumerate(sorted_idx[i]):
            if labels[i, idx] > 0:
                mrr[i] = 1.0 / (rank + 1)
                break

    return acc1, acc3, mrr.mean().item()


def compute_dual_loss(
    model,
    batch,
    device,
    form_weight: float = 0.6,
    content_weight: float = 0.4,
):
    """Dual-head loss: form + content listwise cross-entropy.

    Args:
        model: DualHeadScorerMW instance
        batch: dict with features, form_labels, content_labels, mask
        device: torch device
        form_weight: weight for form loss (default 0.6)
        content_weight: weight for content loss (default 0.4)

    Returns:
        (total_loss, metrics_dict)
    """
    features = batch["features"].to(device)
    form_labels = batch["form_labels"].to(device)
    content_labels = batch["content_labels"].to(device)
    mask = batch["mask"].to(device)

    B, K, Fd = features.shape

    # Forward: dual outputs
    form_scores, content_scores = model(
        features.reshape(B * K, Fd)
    )
    form_scores = form_scores.squeeze(-1).reshape(B, K)
    content_scores = content_scores.squeeze(-1).reshape(B, K)

    # Form loss: always computed
    form_loss = _listwise_ce(form_scores, form_labels, mask).mean()

    # Content loss: masked for groups with no content labels
    has_content = (content_labels.sum(dim=-1) > 0).float()
    content_loss_per_group = _listwise_ce(
        content_scores, content_labels, mask
    )
    if has_content.sum() > 0:
        content_loss = (
            (content_loss_per_group * has_content).sum()
            / has_content.sum()
        )
    else:
        content_loss = torch.tensor(0.0, device=device)

    total_loss = form_weight * form_loss + content_weight * content_loss

    with torch.no_grad():
        # Mask scores for metrics
        fm = form_scores.masked_fill(mask == 0, -1e9)
        cm = content_scores.masked_fill(mask == 0, -1e9)

        # Per-head metrics
        f_acc1, f_acc3, f_mrr = _head_metrics(
            fm, form_labels, device
        )
        c_acc1, c_acc3, c_mrr = _head_metrics(
            cm, content_labels, device
        )

        # Combined score (alpha=form_weight)
        combined = form_weight * fm + content_weight * cm
        comb_acc1, comb_acc3, comb_mrr = _head_metrics(
            combined, form_labels, device
        )

    return total_loss, {
        "loss": total_loss.item(),
        "form_loss": form_loss.item(),
        "content_loss": content_loss.item(),
        "form_top1": f_acc1,
        "form_top3": f_acc3,
        "form_mrr": f_mrr,
        "content_top1": c_acc1,
        "content_top3": c_acc3,
        "content_mrr": c_mrr,
        "combined_top1": comb_acc1,
        "combined_top3": comb_acc3,
        "combined_mrr": comb_mrr,
    }


def get_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def main():
    parser = argparse.ArgumentParser(description="Train SimilarityScorer on MW data")
    parser.add_argument("--collection", default="mcp_gchat_cards_v8")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--lr", type=float, default=5e-3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--hidden-dim", type=int, default=32)
    parser.add_argument("--dropout", type=float, default=0.15)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--checkpoint-dir", type=str,
                        default=str(Path(__file__).parent / "checkpoints"))
    parser.add_argument("--synthetic-data", type=str, default=None,
                        help="Path to synthetic groups JSON from generate_training_data.py")
    parser.add_argument("--noise-std", type=float, default=0.01,
                        help="Gaussian noise std for feature augmentation")
    parser.add_argument("--feature-dropout", type=float, default=0.1,
                        help="Probability of zeroing a feature during training")
    parser.add_argument("--domain", type=str, default="card", choices=["card", "email", "combined"],
                        help="Domain label saved in checkpoint and used for naming")
    parser.add_argument("--feature-version", type=int, default=1, choices=[1, 2, 3, 4, 5],
                        help="Feature version: 1=9D, 2=8D, 3=14D, 4=15D, 5=17D dual-head")
    parser.add_argument("--model-type", type=str, default="single", choices=["single", "dual"],
                        help="Model type: single (SimilarityScorerMW) or dual (DualHeadScorerMW)")
    parser.add_argument("--form-weight", type=float, default=0.6,
                        help="Weight for form loss in dual-head training")
    parser.add_argument("--content-weight", type=float, default=0.4,
                        help="Weight for content loss in dual-head training")
    parser.add_argument("--head-dim", type=int, default=24,
                        help="Hidden dim for each head in dual-head model")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # --- Load data: Qdrant + optional synthetic ---
    groups = []

    # Qdrant groups (original pipeline) — skip for V2/V3 since they lack structural features
    if args.feature_version == 1:
        try:
            client = connect_qdrant()
            points = extract_all_points(client, args.collection, args.limit)
            if points:
                qdrant_groups = build_query_groups(points, args.top_k)
                logger.info(f"Qdrant groups: {len(qdrant_groups)}")
                groups.extend(qdrant_groups)
        except Exception as e:
            logger.warning(f"Qdrant groups unavailable: {e}")
    else:
        logger.info(f"Skipping Qdrant groups for V{args.feature_version} (no structural features)")

    # Synthetic groups (from generate_training_data.py)
    if args.synthetic_data:
        synthetic_groups = load_synthetic_groups(args.synthetic_data, feature_version=args.feature_version)
        logger.info(f"Synthetic groups: {len(synthetic_groups)}")
        groups.extend(synthetic_groups)

    # Determine input dimension from data
    input_dim_map = {1: 9, 2: 8, 3: 14, 4: 15, 5: 17}
    input_dim = input_dim_map.get(args.feature_version, 9)
    if groups:
        sample_cand = groups[0].candidates[0]
        if hasattr(sample_cand, '_precomputed_features'):
            input_dim = len(sample_cand._precomputed_features)
    is_dual = args.model_type == "dual"
    logger.info(
        f"Feature version: V{args.feature_version}, "
        f"input_dim: {input_dim}, model: {args.model_type}"
    )

    if len(groups) < 5:
        logger.error(f"Only {len(groups)} groups — need more data")
        return

    # --- Train/val split ---
    np.random.shuffle(groups)
    split = int(len(groups) * (1 - args.val_split))
    train_groups = groups[:split]
    val_groups = groups[split:]
    logger.info(f"Split: {len(train_groups)} train / {len(val_groups)} val groups")

    # --- Datasets ---
    max_k = max(max(len(g.labels) for g in train_groups), max(len(g.labels) for g in val_groups))
    train_ds = MWListwiseDataset(
        train_groups, max_k,
        noise_std=args.noise_std,
        feature_dropout=args.feature_dropout,
        training=True,
        dual_labels=is_dual,
    )
    val_ds = MWListwiseDataset(val_groups, max_k, dual_labels=is_dual)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    # --- Model ---
    device = get_device()
    if is_dual:
        model = DualHeadScorerMW(
            input_dim=input_dim,
            hidden_dim=args.hidden_dim,
            head_dim=args.head_dim,
            dropout=args.dropout,
        ).to(device)
    else:
        model = SimilarityScorerMW(
            input_dim=input_dim,
            hidden_dim=args.hidden_dim,
            num_layers=2,
            dropout=args.dropout,
        ).to(device)
    logger.info(f"Device: {device}, Model params: {model.count_parameters():,}")

    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs * len(train_loader), eta_min=1e-6)

    # --- Training ---
    ckpt_dir = Path(args.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0
    best_content_top1 = 0.0
    patience_counter = 0

    # Select loss function based on model type
    _loss_fn = (
        lambda m, b, d: compute_dual_loss(
            m, b, d, args.form_weight, args.content_weight
        )
        if is_dual
        else compute_loss
    )

    logger.info(f"Training for {args.epochs} epochs...")
    for epoch in range(1, args.epochs + 1):
        model.train()
        t_metrics: dict[str, float] = {}
        n = 0
        for batch in train_loader:
            optimizer.zero_grad()
            loss, metrics = _loss_fn(model, batch, device)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            for k, v in metrics.items():
                t_metrics[k] = t_metrics.get(k, 0.0) + v
            n += 1
        for k in t_metrics:
            t_metrics[k] /= max(n, 1)

        model.eval()
        v_metrics: dict[str, float] = {}
        nv = 0
        with torch.no_grad():
            for batch in val_loader:
                _, metrics = _loss_fn(model, batch, device)
                for k, v in metrics.items():
                    v_metrics[k] = v_metrics.get(k, 0.0) + v
                nv += 1
        for k in v_metrics:
            v_metrics[k] /= max(nv, 1)

        # Logging
        if is_dual:
            logger.info(
                f"Epoch {epoch:3d}/{args.epochs} "
                f"| train: loss={t_metrics['loss']:.4f} "
                f"form_top1={t_metrics['form_top1']:.3f} "
                f"content_top1={t_metrics['content_top1']:.3f} "
                f"combined={t_metrics['combined_top1']:.3f} "
                f"| val: loss={v_metrics['loss']:.4f} "
                f"form_top1={v_metrics['form_top1']:.3f} "
                f"content_top1={v_metrics['content_top1']:.3f} "
                f"combined={v_metrics['combined_top1']:.3f}"
            )
            val_acc = v_metrics["combined_top1"]
        else:
            logger.info(
                f"Epoch {epoch:3d}/{args.epochs} "
                f"| train: loss={t_metrics['loss']:.4f} "
                f"top1={t_metrics['accuracy']:.3f} "
                f"top3={t_metrics['top3']:.3f} "
                f"mrr={t_metrics['mrr']:.3f} "
                f"| val: loss={v_metrics['loss']:.4f} "
                f"top1={v_metrics['accuracy']:.3f} "
                f"top3={v_metrics['top3']:.3f} "
                f"mrr={v_metrics['mrr']:.3f}"
            )
            val_acc = v_metrics["accuracy"]

        # For dual-head: track content_top1 independently so that
        # training continues while the content head is still improving,
        # even if combined accuracy has plateaued (form saturates early).
        improved = False
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            improved = True

        if is_dual:
            ct1 = v_metrics.get("content_top1", 0.0)
            if ct1 > best_content_top1:
                best_content_top1 = ct1
                improved = True

        if improved:
            patience_counter = 0
            domain = getattr(args, "domain", "card")
            ckpt_name = (
                f"best_model_{domain}.pt"
                if domain != "card"
                else "best_model_mw.pt"
            )
            ckpt = ckpt_dir / ckpt_name
            ckpt_data = {
                "model_state_dict": model.state_dict(),
                "model_type": "dual_head" if is_dual else "similarity_mw",
                "input_dim": input_dim,
                "feature_version": args.feature_version,
                "hidden_dim": args.hidden_dim,
                "dropout": args.dropout,
                "epoch": epoch,
                "val_accuracy": val_acc,
                "collection": args.collection,
                "domain": domain,
            }
            if is_dual:
                ckpt_data["head_dim"] = args.head_dim
                ckpt_data["form_weight"] = args.form_weight
                ckpt_data["content_weight"] = args.content_weight
                ckpt_data["val_form_top1"] = v_metrics["form_top1"]
                ckpt_data["val_content_top1"] = v_metrics["content_top1"]
            torch.save(ckpt_data, ckpt)
            if is_dual:
                logger.info(
                    f"  New best → combined={val_acc:.3f} "
                    f"content_top1={best_content_top1:.3f} → {ckpt}"
                )
            else:
                logger.info(f"  New best val_acc={val_acc:.3f} → {ckpt}")
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                logger.info(f"Early stopping at epoch {epoch}")
                break

    logger.info(f"\nBest validation accuracy: {best_val_acc:.3f}")
    logger.info(f"(Random baseline for K={max_k}: {1/max_k:.3f})")


if __name__ == "__main__":
    main()
