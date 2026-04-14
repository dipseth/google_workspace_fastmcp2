"""Train SlotAffinityNet on content-to-slot-type prediction.

Trains the tiny neural network to predict which supply_map pool
a content item belongs to, enabling learned content-to-slot routing.

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.train_slot_assigner \
        --data ../h2/slot_training_data.json \
        --epochs 50 --lr 1e-3 --batch-size 64
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from .slot_assigner import SLOT_TYPE_NAMES, SLOT_TYPE_VOCAB, SlotAffinityNet

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class SlotDataset(Dataset):
    """Dataset of (content_embedding, target_slot_type_id) pairs.

    Each sample is a content item that should be classified into one of
    N_SLOT_TYPES slot types via softmax cross-entropy.
    """

    def __init__(self, pairs: list[dict], noise_std: float = 0.01):
        # Group by content_text to get one sample per unique content item
        # with the positive slot type as the target
        text_to_target: dict[str, dict] = {}
        for pair in pairs:
            text = pair["content_text"]
            if pair["label"] > 0.5:  # Positive pair
                text_to_target[text] = pair

        self.samples = list(text_to_target.values())
        self.noise_std = noise_std
        logger.info(f"SlotDataset: {len(self.samples)} unique content items")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sample = self.samples[idx]
        emb = torch.tensor(sample["content_embedding"], dtype=torch.float32)

        # Add Gaussian noise for augmentation
        if self.noise_std > 0:
            emb = emb + torch.randn_like(emb) * self.noise_std

        target = torch.tensor(sample["slot_type_id"], dtype=torch.long)
        return emb, target


def evaluate(
    model: SlotAffinityNet,
    loader: DataLoader,
    device: torch.device,
) -> dict:
    """Evaluate model on a dataset."""
    model.eval()
    correct = 0
    total = 0
    per_type_correct: dict[int, int] = {}
    per_type_total: dict[int, int] = {}

    with torch.no_grad():
        for emb_batch, target_batch in loader:
            emb_batch = emb_batch.to(device)
            target_batch = target_batch.to(device)

            # Score all slot types
            scores = model.score_all_slots(emb_batch)  # [B, n_slot_types]
            preds = scores.argmax(dim=-1)  # [B]

            correct += (preds == target_batch).sum().item()
            total += target_batch.shape[0]

            # Per-type accuracy
            for pred, target in zip(preds.cpu().numpy(), target_batch.cpu().numpy()):
                per_type_total[target] = per_type_total.get(target, 0) + 1
                if pred == target:
                    per_type_correct[target] = per_type_correct.get(target, 0) + 1

    acc = correct / total if total > 0 else 0.0

    # Per-type breakdown
    per_type_acc = {}
    for type_id in sorted(per_type_total.keys()):
        name = SLOT_TYPE_NAMES.get(type_id, f"type_{type_id}")
        t_correct = per_type_correct.get(type_id, 0)
        t_total = per_type_total[type_id]
        per_type_acc[name] = t_correct / t_total if t_total > 0 else 0.0

    return {
        "accuracy": acc,
        "correct": correct,
        "total": total,
        "per_type": per_type_acc,
    }


def get_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def main():
    parser = argparse.ArgumentParser(description="Train SlotAffinityNet")
    parser.add_argument("--data", type=str, required=True, help="Training data JSON")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=32)
    parser.add_argument("--slot-embed-dim", type=int, default=16)
    parser.add_argument("--noise-std", type=float, default=0.01)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--checkpoint-dir", type=str, default=str(Path(__file__).parent / "checkpoints")
    )
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = get_device()
    logger.info(f"Device: {device}")

    # Load data
    data_path = Path(args.data)
    if not data_path.exists():
        logger.error(f"Data file not found: {data_path}")
        return

    with open(data_path) as f:
        pairs = json.load(f)
    logger.info(f"Loaded {len(pairs)} pairs from {data_path}")

    # Check embeddings exist
    if not pairs or "content_embedding" not in pairs[0]:
        logger.error(
            "Pairs missing content_embedding — run generate_slot_training_data.py first"
        )
        return

    # Create dataset (deduplicates to unique positive items)
    full_dataset = SlotDataset(pairs, noise_std=args.noise_std)

    if len(full_dataset) < 10:
        logger.error(f"Only {len(full_dataset)} samples — need more data")
        return

    # Train/val split
    n_val = max(5, int(len(full_dataset) * args.val_split))
    n_train = len(full_dataset) - n_val
    train_ds, val_ds = torch.utils.data.random_split(
        full_dataset,
        [n_train, n_val],
        generator=torch.Generator().manual_seed(args.seed),
    )
    # Disable noise for validation
    val_ds_no_noise = SlotDataset.__new__(SlotDataset)
    val_ds_no_noise.samples = [full_dataset.samples[i] for i in val_ds.indices]
    val_ds_no_noise.noise_std = 0.0

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds_no_noise, batch_size=args.batch_size, shuffle=False)

    logger.info(f"Train: {n_train}, Val: {n_val}")

    # Build model
    content_dim = len(pairs[0]["content_embedding"])
    model = SlotAffinityNet(
        content_dim=content_dim,
        slot_embed_dim=args.slot_embed_dim,
        n_slot_types=len(SLOT_TYPE_VOCAB),
        hidden=args.hidden_dim,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters())
    logger.info(
        f"Model: {n_params:,} parameters (content_dim={content_dim}, "
        f"slot_embed_dim={args.slot_embed_dim}, hidden={args.hidden_dim})"
    )

    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs)

    # Training loop
    best_val_acc = 0.0
    patience_counter = 0
    checkpoint_dir = Path(args.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "best_model_slot.pt"

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        epoch_correct = 0
        epoch_total = 0

        for emb_batch, target_batch in train_loader:
            emb_batch = emb_batch.to(device)
            target_batch = target_batch.to(device)

            # Direct classification (softmax CE with label smoothing)
            scores = model(emb_batch)  # [B, n_pools]
            loss = F.cross_entropy(scores, target_batch, label_smoothing=0.1)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item() * emb_batch.shape[0]
            preds = scores.argmax(dim=-1)
            epoch_correct += (preds == target_batch).sum().item()
            epoch_total += emb_batch.shape[0]

        scheduler.step()

        train_loss = epoch_loss / epoch_total
        train_acc = epoch_correct / epoch_total

        # Validate
        val_metrics = evaluate(model, val_loader, device)
        val_acc = val_metrics["accuracy"]

        # Log
        if epoch % 5 == 0 or epoch == 1 or val_acc > best_val_acc:
            per_type_str = ", ".join(
                f"{k}={v:.1%}" for k, v in val_metrics["per_type"].items()
            )
            logger.info(
                f"Epoch {epoch:3d}: "
                f"train_loss={train_loss:.4f}, train_acc={train_acc:.1%}, "
                f"val_acc={val_acc:.1%} | {per_type_str}"
            )

        # Checkpoint
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            patience_counter = 0
            checkpoint = {
                "model_state_dict": model.state_dict(),
                "model_type": "slot_assigner",
                "content_dim": content_dim,
                "slot_embed_dim": args.slot_embed_dim,
                "n_slot_types": len(SLOT_TYPE_VOCAB),
                "hidden_dim": args.hidden_dim,
                "slot_type_vocab": SLOT_TYPE_VOCAB,
                "epoch": epoch,
                "val_accuracy": val_acc,
                "val_per_type": val_metrics["per_type"],
                "train_loss": train_loss,
                "train_acc": train_acc,
            }
            torch.save(checkpoint, checkpoint_path)
            logger.info(f"  → Saved checkpoint (val_acc={val_acc:.1%})")
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                logger.info(
                    f"Early stopping at epoch {epoch} (patience={args.patience})"
                )
                break

    # Final summary
    logger.info(f"\nBest val_acc: {best_val_acc:.1%}")
    logger.info(f"Checkpoint: {checkpoint_path}")

    # Load best and show final per-type breakdown
    best = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    logger.info(f"Best epoch: {best['epoch']}")
    if "val_per_type" in best:
        for name, acc in best["val_per_type"].items():
            logger.info(f"  {name}: {acc:.1%}")


if __name__ == "__main__":
    main()
