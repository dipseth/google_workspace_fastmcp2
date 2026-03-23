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


class MWListwiseDataset(Dataset):
    """Listwise dataset for MW query groups with precomputed features."""

    def __init__(self, groups: list[MWQueryGroup], max_k: int = 0):
        self.max_k = max_k or max(len(g.labels) for g in groups)

        # Precompute all features
        self.features = []  # list of [K, 9] feature tensors
        self.labels = []  # list of [K] label tensors
        self.masks = []  # list of [K] mask tensors

        for g in groups:
            K = len(g.labels)
            pad = self.max_k - K

            feats = []
            for cand in g.candidates:
                f = compute_similarity_features(g.query, cand)
                feats.append(f)

            feat_tensor = torch.from_numpy(np.stack(feats))
            if pad > 0:
                feat_tensor = torch.cat([feat_tensor, torch.zeros(pad, 9)])

            label_tensor = torch.tensor(g.labels + [0.0] * pad, dtype=torch.float32)
            mask_tensor = torch.cat([torch.ones(K), torch.zeros(pad)])

            self.features.append(feat_tensor)
            self.labels.append(label_tensor)
            self.masks.append(mask_tensor)

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        return {
            "features": self.features[idx],  # [max_k, 9]
            "labels": self.labels[idx],  # [max_k]
            "mask": self.masks[idx],  # [max_k]
        }


# ---------------------------------------------------------------------------
# Model: SimilarityScorer for MW (same 9 features as game POC)
# ---------------------------------------------------------------------------


class SimilarityScorerMW(nn.Module):
    """Learned scoring on MW RIC similarity features.

    Input: 9 features per (query, candidate):
      - MaxSim(components): ColBERT 128D late interaction
      - MaxSim(inputs): ColBERT 128D late interaction
      - cosine(relationships): MiniLM 384D dense
      - 3 query norms + 3 candidate norms
    """

    def __init__(self, hidden_dim: int = 32, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        layers: list[nn.Module] = []
        prev = 9
        for _ in range(num_layers):
            layers.extend([nn.Linear(prev, hidden_dim), nn.SiLU(), nn.Dropout(dropout)])
            prev = hidden_dim
        layers.append(nn.Linear(prev, 1))
        self.mlp = nn.Sequential(*layers)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        """features: [B, 9] → scores: [B, 1]"""
        return self.mlp(features)

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


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
        top1 = scores.argmax(dim=-1)
        correct = labels[torch.arange(B, device=device), top1]
        acc = correct.mean().item()

    return loss, {"loss": loss.item(), "accuracy": acc}


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
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # --- Extract data from Qdrant ---
    client = connect_qdrant()
    points = extract_all_points(client, args.collection, args.limit)

    if not points:
        logger.error("No points found")
        return

    groups = build_query_groups(points, args.top_k)
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
    train_ds = MWListwiseDataset(train_groups, max_k)
    val_ds = MWListwiseDataset(val_groups, max_k)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    # --- Model ---
    device = get_device()
    model = SimilarityScorerMW(
        hidden_dim=args.hidden_dim, num_layers=2, dropout=args.dropout,
    ).to(device)
    logger.info(f"Device: {device}, Model params: {model.count_parameters():,}")

    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs * len(train_loader), eta_min=1e-6)

    # --- Training ---
    ckpt_dir = Path(args.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0
    patience_counter = 0

    logger.info(f"Training for {args.epochs} epochs...")
    for epoch in range(1, args.epochs + 1):
        model.train()
        t_loss, t_acc, n = 0.0, 0.0, 0
        for batch in train_loader:
            optimizer.zero_grad()
            loss, metrics = compute_loss(model, batch, device)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            t_loss += metrics["loss"]
            t_acc += metrics["accuracy"]
            n += 1
        t_loss /= max(n, 1)
        t_acc /= max(n, 1)

        model.eval()
        v_loss, v_acc, nv = 0.0, 0.0, 0
        with torch.no_grad():
            for batch in val_loader:
                loss, metrics = compute_loss(model, batch, device)
                v_loss += metrics["loss"]
                v_acc += metrics["accuracy"]
                nv += 1
        v_loss /= max(nv, 1)
        v_acc /= max(nv, 1)

        logger.info(
            f"Epoch {epoch:3d}/{args.epochs} "
            f"| train_loss={t_loss:.4f} train_acc={t_acc:.3f} "
            f"| val_loss={v_loss:.4f} val_acc={v_acc:.3f}"
        )

        if v_acc > best_val_acc:
            best_val_acc = v_acc
            patience_counter = 0
            ckpt = ckpt_dir / "best_model_mw.pt"
            torch.save({
                "model_state_dict": model.state_dict(),
                "model_type": "similarity_mw",
                "hidden_dim": args.hidden_dim,
                "dropout": args.dropout,
                "epoch": epoch,
                "val_accuracy": v_acc,
                "collection": args.collection,
            }, ckpt)
            logger.info(f"  New best val_acc={v_acc:.3f} → {ckpt}")
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                logger.info(f"Early stopping at epoch {epoch}")
                break

    logger.info(f"\nBest validation accuracy: {best_val_acc:.3f}")
    logger.info(f"(Random baseline for K={max_k}: {1/max_k:.3f})")


if __name__ == "__main__":
    main()
