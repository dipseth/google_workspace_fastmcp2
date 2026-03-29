"""Training script for the Tiny Recursive Projection Network.

Usage:
    cd research/trm/poc
    uv run python ../h2/train.py --game mancala --train-size 2000 --val-size 500
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR

# Allow imports from parent poc/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from games import Connect4, Mancala, TicTacToe  # noqa: E402
from ric_vectors import RICEmbedder  # noqa: E402

from .data_pipeline import (  # noqa: E402
    create_listwise_dataloaders,
    generate_query_groups,
)
from .model import SimilarityScorer, TinyProjectionNetwork, TRPNConfig  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GAMES = {
    "tictactoe": TicTacToe,
    "connect4": lambda: Connect4(search_depth=4),
    "mancala": lambda: Mancala(search_depth=6),
}


def get_device() -> torch.device:
    """Select best available device: MPS (Apple Silicon) > CUDA > CPU."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _batch_to_device(batch: dict[str, torch.Tensor], device: torch.device) -> dict[str, torch.Tensor]:
    """Move all tensors in a batch dict to the target device."""
    return {k: v.to(device) for k, v in batch.items()}


def compute_listwise_loss(
    model: TinyProjectionNetwork,
    batch: dict[str, torch.Tensor],
) -> tuple[torch.Tensor, dict[str, float]]:
    """Listwise contrastive loss: softmax cross-entropy over K candidates per query.

    For each query, the model scores K candidates. The target is a distribution
    where correct candidates get equal probability mass. This directly teaches
    ranking — the correct candidate must score HIGHER than incorrect ones.

    batch shapes:
        query_comp/inp/rel: [B, 384]
        cand_comp/inp/rel:  [B, K, 384]
        labels:             [B, K]  (1.0 for correct, 0.0 for incorrect)
        mask:               [B, K]  (1.0 for real candidate, 0.0 for padding)
    """
    B, K, D = batch["cand_comp"].shape

    # Expand query to match candidates: [B, 384] → [B*K, 384]
    q_comp = batch["query_comp"].unsqueeze(1).expand(B, K, D).reshape(B * K, D)
    q_inp = batch["query_inp"].unsqueeze(1).expand(B, K, D).reshape(B * K, D)
    q_rel = batch["query_rel"].unsqueeze(1).expand(B, K, D).reshape(B * K, D)

    # Flatten candidates: [B, K, 384] → [B*K, 384]
    c_comp = batch["cand_comp"].reshape(B * K, D)
    c_inp = batch["cand_inp"].reshape(B * K, D)
    c_rel = batch["cand_rel"].reshape(B * K, D)

    # Score all (query, candidate) pairs
    scores, halt_logits, per_cycle_scores = model(
        q_comp, q_inp, q_rel, c_comp, c_inp, c_rel,
    )

    # Reshape scores back to [B, K]
    scores_2d = scores.squeeze(-1).reshape(B, K)

    labels = batch["labels"]  # [B, K]
    mask = batch["mask"]      # [B, K]

    # Mask out padding with large negative value
    scores_2d = scores_2d.masked_fill(mask == 0, -1e9)

    # Normalize labels to probability distribution per query
    # (handles multiple correct candidates per query)
    label_sums = labels.sum(dim=-1, keepdim=True).clamp(min=1.0)
    target_dist = labels / label_sums  # [B, K]

    # Cross-entropy loss: softmax over candidates, compare to target distribution
    log_probs = F.log_softmax(scores_2d, dim=-1)
    ranking_loss = -(target_dist * log_probs).sum(dim=-1).mean()

    # Deep supervision on intermediate cycles
    deep_sup_loss = torch.tensor(0.0, device=scores.device)
    if len(per_cycle_scores) > 1:
        for cs in per_cycle_scores[:-1]:
            cs_2d = cs.squeeze(-1).reshape(B, K).masked_fill(mask == 0, -1e9)
            lp = F.log_softmax(cs_2d, dim=-1)
            deep_sup_loss = deep_sup_loss - (target_dist * lp).sum(dim=-1).mean()
        deep_sup_loss = deep_sup_loss / (len(per_cycle_scores) - 1)

    total_loss = ranking_loss + 0.3 * deep_sup_loss

    # Metrics: top-1 accuracy (does highest-scored candidate have label=1?)
    with torch.no_grad():
        top1_preds = scores_2d.argmax(dim=-1)  # [B]
        top1_correct = labels[torch.arange(B), top1_preds]  # [B]
        accuracy = top1_correct.mean().item()

    return total_loss, {
        "loss": total_loss.item(),
        "ranking_loss": ranking_loss.item(),
        "deep_sup_loss": deep_sup_loss.item() if isinstance(deep_sup_loss, torch.Tensor) and deep_sup_loss.dim() == 0 else 0.0,
        "accuracy": accuracy,
    }


def train_epoch(
    model: TinyProjectionNetwork,
    loader,
    optimizer,
    device: torch.device,
    scheduler=None,
) -> dict[str, float]:
    """One training epoch."""
    model.train()
    total_metrics: dict[str, float] = {}
    n_batches = 0

    for batch in loader:
        batch = _batch_to_device(batch, device)
        optimizer.zero_grad()
        loss, metrics = compute_listwise_loss(model, batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        if scheduler:
            scheduler.step()

        for k, v in metrics.items():
            total_metrics[k] = total_metrics.get(k, 0.0) + v
        n_batches += 1

    return {k: v / n_batches for k, v in total_metrics.items()} if n_batches else {}


@torch.no_grad()
def validate(
    model: TinyProjectionNetwork,
    loader,
    device: torch.device,
) -> dict[str, float]:
    """Validation pass."""
    model.eval()
    total_metrics: dict[str, float] = {}
    n_batches = 0

    for batch in loader:
        batch = _batch_to_device(batch, device)
        _, metrics = compute_listwise_loss(model, batch)
        for k, v in metrics.items():
            total_metrics[k] = total_metrics.get(k, 0.0) + v
        n_batches += 1

    return {k: v / n_batches for k, v in total_metrics.items()} if n_batches else {}


def main():
    parser = argparse.ArgumentParser(description="Train TRPN on game states")
    parser.add_argument(
        "--game", choices=list(GAMES.keys()), default="mancala", help="Game to train on"
    )
    parser.add_argument("--train-size", type=int, default=2000, help="Training states")
    parser.add_argument("--val-size", type=int, default=500, help="Validation states")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size")
    parser.add_argument("--hidden-dim", type=int, default=128, help="Hidden dimension")
    parser.add_argument("--H-cycles", type=int, default=3, help="Outer recursion cycles")
    parser.add_argument("--L-cycles", type=int, default=4, help="Inner recursion cycles")
    parser.add_argument("--top-k", type=int, default=20, help="Candidates per query")
    parser.add_argument(
        "--model-type", choices=["trpn", "similarity"], default="similarity",
        help="Model type: 'trpn' (full recursive) or 'similarity' (learned scoring on cosine sims)",
    )
    parser.add_argument("--patience", type=int, default=10, help="Early stopping patience")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default=str(Path(__file__).resolve().parent / "checkpoints"),
        help="Checkpoint directory",
    )
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # --- Game setup ---
    game_factory = GAMES[args.game]
    game = game_factory() if callable(game_factory) and not isinstance(game_factory, type) else game_factory()
    logger.info(f"Game: {game.name}")

    # --- Generate states ---
    total_needed = args.train_size + args.val_size
    logger.info(f"Generating {total_needed} game states...")
    t0 = time.time()
    all_states = game.generate_states(total_needed)
    np.random.shuffle(all_states)
    train_states = all_states[: args.train_size]
    val_states = all_states[args.train_size : args.train_size + args.val_size]
    logger.info(
        f"Generated {len(train_states)} train + {len(val_states)} val states "
        f"in {time.time() - t0:.1f}s"
    )

    # --- Embed and index ---
    collection = f"trpn_{game.name}_train"
    embedder = RICEmbedder()
    logger.info(f"Indexing {len(train_states)} states into '{collection}'...")
    t0 = time.time()
    embedder.create_collection(collection, force_recreate=True)
    embedder.index_states(game, train_states, collection)
    logger.info(f"Indexed in {time.time() - t0:.1f}s")

    # --- Generate query groups (listwise training data) ---
    logger.info("Generating query groups...")
    t0 = time.time()
    train_groups = generate_query_groups(
        game, embedder, collection, train_states, top_k=args.top_k
    )
    val_groups = generate_query_groups(
        game, embedder, collection, val_states, top_k=args.top_k
    )
    logger.info(
        f"Generated {len(train_groups)} train + {len(val_groups)} val groups "
        f"in {time.time() - t0:.1f}s"
    )

    # --- Create dataloaders ---
    train_loader, val_loader = create_listwise_dataloaders(
        train_groups, val_groups, batch_size=args.batch_size
    )

    # --- Device selection ---
    device = get_device()
    logger.info(f"Device: {device}")

    # --- Create model ---
    if args.model_type == "similarity":
        model = SimilarityScorer(hidden_dim=args.hidden_dim, num_layers=2).to(device)
    else:
        config = TRPNConfig(
            hidden_dim=args.hidden_dim,
            H_cycles=args.H_cycles,
            L_cycles=args.L_cycles,
        )
        model = TinyProjectionNetwork(config).to(device)
    n_params = model.count_parameters()
    logger.info(f"Model: {args.model_type}, parameters: {n_params:,}")

    # --- Optimizer and scheduler ---
    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = CosineAnnealingLR(
        optimizer, T_max=args.epochs * len(train_loader), eta_min=1e-6
    )

    # --- Training loop ---
    checkpoint_dir = Path(args.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0
    patience_counter = 0

    logger.info(f"Training for {args.epochs} epochs...")
    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_metrics = train_epoch(model, train_loader, optimizer, device, scheduler)
        val_metrics = validate(model, val_loader, device)
        elapsed = time.time() - t0

        logger.info(
            f"Epoch {epoch:3d}/{args.epochs} "
            f"| train_loss={train_metrics.get('loss', 0):.4f} "
            f"train_acc={train_metrics.get('accuracy', 0):.3f} "
            f"| val_loss={val_metrics.get('loss', 0):.4f} "
            f"val_acc={val_metrics.get('accuracy', 0):.3f} "
            f"| {elapsed:.1f}s"
        )

        # Checkpoint best model
        val_acc = val_metrics.get("accuracy", 0)
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            patience_counter = 0
            ckpt_path = checkpoint_dir / "best_model.pt"
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "model_type": args.model_type,
                    "hidden_dim": args.hidden_dim,
                    "config": config if args.model_type == "trpn" else None,
                    "epoch": epoch,
                    "val_accuracy": val_acc,
                    "game": game.name,
                },
                ckpt_path,
            )
            logger.info(f"  ✓ New best val_acc={val_acc:.3f} → saved to {ckpt_path}")
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                logger.info(
                    f"Early stopping at epoch {epoch} "
                    f"(no improvement for {args.patience} epochs)"
                )
                break

    logger.info(f"\nBest validation accuracy: {best_val_acc:.3f}")
    logger.info(f"Checkpoint: {checkpoint_dir / 'best_model.pt'}")


if __name__ == "__main__":
    main()
