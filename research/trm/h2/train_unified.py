"""Train UnifiedTRN with multi-task learning.

Alternating batches: search (listwise form/content/halt) + build (pool classification).
Joint loss: w_form * form_CE + w_content * content_CE + w_pool * pool_CE + w_halt * halt_BCE.

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.train_unified \
        --search-data ../h2/mw_synthetic_groups_v5_hard2.json \
        --build-data ../h2/slot_training_data.json \
        --epochs 150 --lr 3e-3 --batch-size 16 --patience 25
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset

from .slot_assigner import POOL_NAMES, POOL_VOCAB
from .unified_trn import FEATURE_NAMES_V5, UnifiedTRN

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


class UnifiedSearchDataset(Dataset):
    """Listwise dataset for search-mode training.

    Each sample = a query group with K candidates.
    Includes content embedding broadcast to all candidates.
    """

    def __init__(
        self,
        groups: list[dict],
        max_k: int = 0,
        noise_std: float = 0.01,
        feature_dropout: float = 0.1,
        structural_mask_prob: float = 0.0,
        training: bool = False,
    ):
        self.noise_std = noise_std
        self.feature_dropout = feature_dropout
        self.structural_mask_prob = structural_mask_prob
        self.training = training
        self._structural_indices = [9, 10, 11, 12, 13]

        # Precompute
        self.features = []
        self.form_labels = []
        self.content_labels = []
        self.content_embeddings = []
        self.masks = []

        max_k = max_k or max(len(g["candidates"]) for g in groups)
        self.max_k = max_k

        for g in groups:
            cands = g["candidates"]
            K = len(cands)
            pad = max_k - K

            # Extract 17D features per candidate
            feats = []
            for c in cands:
                f = [c.get(name, 0.0) for name in FEATURE_NAMES_V5]
                feats.append(f)
            feat_tensor = torch.tensor(feats, dtype=torch.float32)
            if pad > 0:
                feat_tensor = torch.cat([feat_tensor, torch.zeros(pad, len(FEATURE_NAMES_V5))])

            # Labels
            form_labels = [c.get("form_label", 0.0) for c in cands]
            content_labels = [c.get("content_label", 0.0) for c in cands]
            form_tensor = torch.tensor(form_labels + [0.0] * pad, dtype=torch.float32)
            content_tensor = torch.tensor(content_labels + [0.0] * pad, dtype=torch.float32)

            # Content embedding (384D, same for all candidates in group)
            content_emb = g.get("content_embedding")
            if content_emb:
                ce_tensor = torch.tensor(content_emb, dtype=torch.float32)
            else:
                ce_tensor = torch.zeros(384)

            mask_tensor = torch.cat([torch.ones(K), torch.zeros(pad)])

            self.features.append(feat_tensor)
            self.form_labels.append(form_tensor)
            self.content_labels.append(content_tensor)
            self.content_embeddings.append(ce_tensor)
            self.masks.append(mask_tensor)

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        feats = self.features[idx].clone()
        form_labels = self.form_labels[idx]
        content_labels = self.content_labels[idx]
        content_emb = self.content_embeddings[idx]
        mask = self.masks[idx]

        if self.training:
            # Gaussian noise
            if self.noise_std > 0:
                noise = torch.randn_like(feats) * self.noise_std
                feats = feats + noise * mask.unsqueeze(-1)

            # Feature dropout
            if self.feature_dropout > 0 and torch.rand(1).item() < self.feature_dropout:
                drop_idx = torch.randint(0, feats.shape[1], (1,)).item()
                feats[:, drop_idx] = 0.0

            # Structural masking
            if self.structural_mask_prob > 0 and torch.rand(1).item() < self.structural_mask_prob:
                feats[:, self._structural_indices] = 0.0

            # Candidate shuffle
            valid_k = int(mask.sum().item())
            if valid_k > 1:
                perm = torch.randperm(valid_k)
                feats[:valid_k] = feats[perm]
                form_labels = form_labels.clone()
                form_labels[:valid_k] = form_labels[perm]
                content_labels = content_labels.clone()
                content_labels[:valid_k] = content_labels[perm]

        # Broadcast content embedding to all K candidates
        K = feats.shape[0]
        content_emb_broadcast = content_emb.unsqueeze(0).expand(K, -1)

        return {
            "structural_features": feats,             # [K, 17]
            "content_embedding": content_emb_broadcast, # [K, 384]
            "form_labels": form_labels,                # [K]
            "content_labels": content_labels,          # [K]
            "mask": mask,                              # [K]
        }


class UnifiedBuildDataset(Dataset):
    """Pointwise dataset for build-mode pool classification."""

    def __init__(self, pairs: list[dict], noise_std: float = 0.01):
        # Deduplicate: keep one positive per content_text
        seen = set()
        self.samples = []
        for p in pairs:
            if p.get("label", 0) > 0.5 and p["content_text"] not in seen:
                seen.add(p["content_text"])
                self.samples.append(p)
        self.noise_std = noise_std
        logger.info(f"UnifiedBuildDataset: {len(self.samples)} unique items")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        s = self.samples[idx]
        content_emb = torch.tensor(s["content_embedding"], dtype=torch.float32)
        if self.noise_std > 0:
            content_emb = content_emb + torch.randn_like(content_emb) * self.noise_std
        pool_id = torch.tensor(s["slot_type_id"], dtype=torch.long)
        structural = torch.zeros(len(FEATURE_NAMES_V5))  # No structural context in build mode
        return {
            "structural_features": structural,  # [17]
            "content_embedding": content_emb,   # [384]
            "pool_id": pool_id,
        }


# ---------------------------------------------------------------------------
# Loss functions
# ---------------------------------------------------------------------------


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


def compute_search_loss(model, batch, device, weights):
    """Search-mode loss: form + content listwise CE + halt BCE."""
    structural = batch["structural_features"].to(device)   # [B, K, 17]
    content_emb = batch["content_embedding"].to(device)    # [B, K, 384]
    form_labels = batch["form_labels"].to(device)          # [B, K]
    content_labels = batch["content_labels"].to(device)    # [B, K]
    mask = batch["mask"].to(device)                        # [B, K]

    B, K, Fs = structural.shape

    # Forward all candidates
    out = model(
        structural.reshape(B * K, Fs),
        content_emb.reshape(B * K, -1),
        mode="search",
    )
    form_scores = out["form_score"].squeeze(-1).reshape(B, K)
    content_scores = out["content_score"].squeeze(-1).reshape(B, K)
    halt_probs = out["halt_prob"].squeeze(-1).reshape(B, K)

    # Form loss
    form_loss = _listwise_ce(form_scores, form_labels, mask).mean()

    # Content loss (masked for groups with no content labels)
    has_content = (content_labels.sum(dim=-1) > 0).float()
    content_loss_per_group = _listwise_ce(content_scores, content_labels, mask)
    if has_content.sum() > 0:
        content_loss = (content_loss_per_group * has_content).sum() / has_content.sum()
    else:
        content_loss = torch.tensor(0.0, device=device)

    # Halt loss (margin-based approach)
    # halt_target = soft signal based on score margin (not just binary correct/wrong)
    # High margin + correct → halt=1.0, low margin or wrong → halt=0.0
    with torch.no_grad():
        gt_top1 = form_labels.argmax(dim=-1)  # [B]
        fm = form_scores.masked_fill(mask == 0, -1e9)
        pred_top1 = fm.argmax(dim=-1)  # [B]
        is_correct = (pred_top1 == gt_top1).float()  # [B]

        # Compute margin: top1_score - top2_score (normalized)
        sorted_scores, _ = fm.sort(dim=-1, descending=True)
        margin = (sorted_scores[:, 0] - sorted_scores[:, 1]).clamp(min=0)
        # Normalize margin to [0, 1] via sigmoid with scale
        margin_signal = torch.sigmoid(margin * 2.0)

        # halt_target = correct * margin_signal (0.0 if wrong, 0-1 if correct)
        halt_target = is_correct * margin_signal

    # Use halt_prob of the predicted top-1 candidate
    halt_pred = halt_probs[torch.arange(B, device=device), pred_top1]  # [B]
    halt_loss = F.binary_cross_entropy(halt_pred, halt_target)

    total = (
        weights["w_form"] * form_loss
        + weights["w_content"] * content_loss
        + weights["w_halt"] * halt_loss
    )

    with torch.no_grad():
        fm = form_scores.masked_fill(mask == 0, -1e9)
        cm = content_scores.masked_fill(mask == 0, -1e9)
        f_acc1, f_acc3, f_mrr = _head_metrics(fm, form_labels, device)
        c_acc1, _, _ = _head_metrics(cm, content_labels, device)
        combined = weights["w_form"] * fm + weights["w_content"] * cm
        comb_acc1, _, _ = _head_metrics(combined, form_labels, device)
        halt_acc = ((halt_pred > 0.5) == (halt_target > 0.5)).float().mean().item()
        # Also track correlation between halt_pred and halt_target
        halt_corr = torch.corrcoef(torch.stack([halt_pred, halt_target]))[0, 1].item()
        if not (halt_corr == halt_corr):  # NaN check
            halt_corr = 0.0

    return total, {
        "form_loss": form_loss.item(),
        "content_loss": content_loss.item(),
        "halt_loss": halt_loss.item(),
        "form_top1": f_acc1,
        "content_top1": c_acc1,
        "combined_top1": comb_acc1,
        "halt_acc": halt_acc,
        "halt_corr": halt_corr,
    }


def compute_build_loss(model, batch, device):
    """Build-mode loss: softmax CE for pool classification."""
    structural = batch["structural_features"].to(device)  # [B, 17]
    content_emb = batch["content_embedding"].to(device)   # [B, 384]
    pool_targets = batch["pool_id"].to(device)             # [B]

    out = model(structural, content_emb, mode="build")
    pool_logits = out["pool_logits"]  # [B, 5]

    pool_loss = F.cross_entropy(pool_logits, pool_targets, label_smoothing=0.1)

    with torch.no_grad():
        preds = pool_logits.argmax(dim=-1)
        pool_acc = (preds == pool_targets).float().mean().item()

    return pool_loss, {"pool_loss": pool_loss.item(), "pool_acc": pool_acc}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate(model, search_loader, build_loader, device, weights):
    """Evaluate on both search and build tasks."""
    model.eval()
    search_metrics_sum = {}
    build_metrics_sum = {}
    n_search = 0
    n_build = 0

    with torch.no_grad():
        for batch in search_loader:
            _, metrics = compute_search_loss(model, batch, device, weights)
            for k, v in metrics.items():
                search_metrics_sum[k] = search_metrics_sum.get(k, 0) + v
            n_search += 1

        for batch in build_loader:
            _, metrics = compute_build_loss(model, batch, device)
            for k, v in metrics.items():
                build_metrics_sum[k] = build_metrics_sum.get(k, 0) + v
            n_build += 1

    search_avg = {k: v / max(n_search, 1) for k, v in search_metrics_sum.items()}
    build_avg = {k: v / max(n_build, 1) for k, v in build_metrics_sum.items()}

    return {**search_avg, **build_avg}


def get_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Train UnifiedTRN")
    parser.add_argument("--search-data", type=str, required=True,
                        help="MWQueryGroups JSON or unified JSON")
    parser.add_argument("--build-data", type=str, default=None,
                        help="Slot training data JSON (optional if unified format)")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--dropout", type=float, default=0.15)
    parser.add_argument("--noise-std", type=float, default=0.01)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--w-form", type=float, default=0.4)
    parser.add_argument("--w-content", type=float, default=0.2)
    parser.add_argument("--w-pool", type=float, default=0.3)
    parser.add_argument("--w-halt", type=float, default=0.1)
    parser.add_argument("--checkpoint-dir", type=str,
                        default=str(Path(__file__).parent / "checkpoints"))
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)

    device = get_device()
    logger.info(f"Device: {device}")

    weights = {
        "w_form": args.w_form,
        "w_content": args.w_content,
        "w_pool": args.w_pool,
        "w_halt": args.w_halt,
    }
    logger.info(f"Loss weights: {weights}")

    # Load data — support both unified format and separate files
    search_path = Path(args.search_data)
    with open(search_path) as f:
        raw = json.load(f)

    if "search_groups" in raw:
        # Unified format
        search_groups = raw["search_groups"]
        build_pairs = raw.get("build_pairs", [])
        logger.info(f"Unified format: {len(search_groups)} search, {len(build_pairs)} build")
    else:
        # Separate files
        search_groups = raw
        build_pairs = []
        if args.build_data:
            with open(args.build_data) as f:
                build_pairs = json.load(f)
        logger.info(f"Separate files: {len(search_groups)} search, {len(build_pairs)} build")

    # Train/val split (search)
    random.shuffle(search_groups)
    n_val_search = max(5, int(len(search_groups) * args.val_split))
    val_search = search_groups[:n_val_search]
    train_search = search_groups[n_val_search:]

    # Train/val split (build — if available)
    has_build = len(build_pairs) > 0 and "content_embedding" in build_pairs[0]
    if has_build:
        random.shuffle(build_pairs)
        # Build dataset deduplicates, so split before dedup
        n_val_build = max(5, int(len(build_pairs) * args.val_split))
        val_build_pairs = build_pairs[:n_val_build]
        train_build_pairs = build_pairs[n_val_build:]
    else:
        logger.warning("No build data — pool_head will not be trained")
        val_build_pairs = []
        train_build_pairs = []

    # Create datasets
    train_search_ds = UnifiedSearchDataset(
        train_search, noise_std=args.noise_std,
        feature_dropout=0.1, structural_mask_prob=0.0, training=True,
    )
    val_search_ds = UnifiedSearchDataset(val_search, training=False)

    train_search_loader = DataLoader(train_search_ds, batch_size=args.batch_size, shuffle=True)
    val_search_loader = DataLoader(val_search_ds, batch_size=args.batch_size, shuffle=False)

    if has_build:
        train_build_ds = UnifiedBuildDataset(train_build_pairs, noise_std=args.noise_std)
        val_build_ds = UnifiedBuildDataset(val_build_pairs, noise_std=0.0)
        train_build_loader = DataLoader(train_build_ds, batch_size=args.batch_size * 4, shuffle=True)
        val_build_loader = DataLoader(val_build_ds, batch_size=args.batch_size * 4, shuffle=False)
    else:
        train_build_loader = None
        val_build_loader = DataLoader([], batch_size=1)

    logger.info(f"Train: {len(train_search_ds)} search groups, "
                f"{len(train_build_ds) if has_build else 0} build items")
    logger.info(f"Val: {len(val_search_ds)} search groups, "
                f"{len(val_build_ds) if has_build else 0} build items")

    # Build model
    model = UnifiedTRN(
        structural_dim=len(FEATURE_NAMES_V5),
        content_dim=384,
        hidden=args.hidden,
        n_pools=len(POOL_VOCAB),
        dropout=args.dropout,
    ).to(device)

    logger.info(f"Model: {model.count_parameters():,} parameters")

    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs)

    # Training loop
    best_form_top1 = 0.0  # Actually stores combined_score (0.6*form + 0.4*pool)
    patience_counter = 0
    checkpoint_dir = Path(args.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "best_model_unified.pt"

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_search_loss = 0.0
        epoch_build_loss = 0.0
        epoch_form_top1 = 0.0
        epoch_pool_acc = 0.0
        n_search_batches = 0
        n_build_batches = 0

        # Alternating batches
        search_iter = iter(train_search_loader)
        build_iter = iter(train_build_loader) if train_build_loader else None

        for search_batch in search_iter:
            # Search step
            search_loss, s_metrics = compute_search_loss(model, search_batch, device, weights)
            epoch_search_loss += s_metrics["form_loss"]
            epoch_form_top1 += s_metrics["form_top1"]
            n_search_batches += 1

            # Build step (if available)
            build_loss = torch.tensor(0.0, device=device)
            if build_iter is not None:
                try:
                    build_batch = next(build_iter)
                except StopIteration:
                    build_iter = iter(train_build_loader)
                    build_batch = next(build_iter)
                b_loss, b_metrics = compute_build_loss(model, build_batch, device)
                build_loss = b_loss
                epoch_build_loss += b_metrics["pool_loss"]
                epoch_pool_acc += b_metrics["pool_acc"]
                n_build_batches += 1

            # Combined backward
            total_loss = search_loss + weights["w_pool"] * build_loss
            optimizer.zero_grad()
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        scheduler.step()

        # Epoch averages
        avg_form_top1 = epoch_form_top1 / max(n_search_batches, 1)
        avg_pool_acc = epoch_pool_acc / max(n_build_batches, 1)

        # Validate
        val_metrics = evaluate(model, val_search_loader, val_build_loader, device, weights)
        val_form_top1 = val_metrics.get("form_top1", 0)
        val_content_top1 = val_metrics.get("content_top1", 0)
        val_pool_acc = val_metrics.get("pool_acc", 0)
        val_halt_acc = val_metrics.get("halt_acc", 0)

        # Log
        if epoch % 5 == 0 or epoch == 1 or val_form_top1 > best_form_top1:
            logger.info(
                f"Epoch {epoch:3d}: "
                f"train_form={avg_form_top1:.1%} train_pool={avg_pool_acc:.1%} | "
                f"val_form={val_form_top1:.1%} val_content={val_content_top1:.1%} "
                f"val_pool={val_pool_acc:.1%} val_halt={val_halt_acc:.1%}"
            )

        # Checkpoint (combined score: form + pool must both be good)
        combined_score = 0.6 * val_form_top1 + 0.4 * val_pool_acc
        if combined_score > best_form_top1:
            patience_counter = 0
            checkpoint = {
                "model_state_dict": model.state_dict(),
                "model_type": "unified_trn",
                "structural_dim": len(FEATURE_NAMES_V5),
                "content_dim": 384,
                "hidden": args.hidden,
                "n_pools": len(POOL_VOCAB),
                "dropout": args.dropout,
                "feature_version": 5,
                "epoch": epoch,
                "val_form_top1": val_form_top1,
                "val_content_top1": val_content_top1,
                "val_pool_acc": val_pool_acc,
                "val_halt_acc": val_halt_acc,
                "val_combined_top1": val_metrics.get("combined_top1", 0),
                "loss_weights": weights,
                "pool_vocab": POOL_VOCAB,
                "best_pool_acc": val_pool_acc,
                "best_content_top1": val_content_top1,
            }
            torch.save(checkpoint, checkpoint_path)
            logger.info(f"  → Saved checkpoint (val_form={val_form_top1:.1%}, "
                        f"val_pool={val_pool_acc:.1%})")
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                logger.info(f"Early stopping at epoch {epoch}")
                break

    # Final summary
    best = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    logger.info(f"\n{'='*60}")
    logger.info(f"Best epoch: {best['epoch']}")
    logger.info(f"  form_top1:     {best['val_form_top1']:.1%}")
    logger.info(f"  content_top1:  {best['val_content_top1']:.1%}")
    logger.info(f"  combined_top1: {best['val_combined_top1']:.1%}")
    logger.info(f"  pool_acc:      {best['val_pool_acc']:.1%}")
    logger.info(f"  halt_acc:      {best['val_halt_acc']:.1%}")
    logger.info(f"  params:        {model.count_parameters():,}")
    logger.info(f"Checkpoint: {checkpoint_path}")


if __name__ == "__main__":
    main()
