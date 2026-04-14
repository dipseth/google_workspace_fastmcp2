"""V2 Training: Richer embeddings + persistent Qdrant + deeper solver.

Key differences from v1:
  - Board state vector (14D) as direct numerical features alongside cosine sims
  - Game-specific features (store diff, capture threats, extra turns)
  - Depth-12 solver with transposition table (cleaner labels)
  - Persistent Qdrant (cloud) so embeddings are inspectable
  - SimilarityScorer V2 with 25+ input features (vs 9 in v1)

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.train_v2 --game mancala
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset

# Allow imports from parent poc/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from games import Mancala  # noqa: E402
from games.base import GameState  # noqa: E402
from recursive_search import _cosine_sim, _search_vector  # noqa: E402
from ric_vectors import RICEmbedder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# V2 Feature extraction: numerical board features + cosine sims
# ---------------------------------------------------------------------------


def extract_board_features(board: tuple | list, current_player: int) -> np.ndarray:
    """Extract numerical features from a Mancala board state.

    Returns a feature vector capturing what text embeddings cannot:
    exact stone counts, capture/extra-turn opportunities, positional advantage.
    """
    b = list(board) if not isinstance(board, list) else board
    p1_pits = b[0:6]
    p2_pits = b[7:13]
    s1, s2 = b[6], b[13]

    own_pits = p1_pits if current_player == 1 else p2_pits
    opp_pits = p2_pits if current_player == 1 else p1_pits
    own_store = s1 if current_player == 1 else s2
    opp_store = s2 if current_player == 1 else s1

    # Normalize stone counts to [0, 1] range (max 48 stones total)
    norm = 48.0

    features = [
        # Per-pit stones (normalized) — 12 features
        *[p / norm for p in own_pits],
        *[p / norm for p in opp_pits],
        # Store difference (normalized)
        (own_store - opp_store) / norm,
        # Own/opp total pit stones
        sum(own_pits) / norm,
        sum(opp_pits) / norm,
        # Number of empty own pits (capture opportunity indicator)
        sum(1 for p in own_pits if p == 0) / 6.0,
        # Number of empty opp pits
        sum(1 for p in opp_pits if p == 0) / 6.0,
        # Extra turn opportunities: pits where stones == distance to store
        sum(1 for i, p in enumerate(own_pits) if p > 0 and p == 6 - i) / 6.0,
        # Capture value: sum of opponent stones capturable
        sum(
            opp_pits[5 - i]
            for i, p in enumerate(own_pits)
            if p == 0 and opp_pits[5 - i] > 0
        ) / norm,
        # Game phase: how many total stones are in stores (0=early, 1=late)
        (own_store + opp_store) / norm,
        # Store ratio (own / total+1)
        own_store / (own_store + opp_store + 1),
    ]

    return np.array(features, dtype=np.float32)


BOARD_FEATURE_DIM = 21  # must match extract_board_features output


# ---------------------------------------------------------------------------
# V2 Data pipeline: query groups with board features
# ---------------------------------------------------------------------------


@dataclass
class QueryGroupV2:
    """Query with candidates, cosine sims, AND board features."""

    # Query features
    query_board_features: np.ndarray  # [BOARD_FEATURE_DIM]
    query_comp: np.ndarray  # [384]
    query_inp: np.ndarray  # [384]
    query_rel: np.ndarray  # [384]

    # Candidate features (K of each)
    cand_board_features: list[np.ndarray]  # K × [BOARD_FEATURE_DIM]
    cand_comps: list[np.ndarray]  # K × [384]
    cand_inps: list[np.ndarray]  # K × [384]
    cand_rels: list[np.ndarray]  # K × [384]

    labels: list[float]  # K labels
    true_move: int


def generate_groups_v2(
    game, embedder, collection, states, top_k=20,
) -> list[QueryGroupV2]:
    """Generate query groups with board features."""
    groups = []
    for idx, (state, true_move) in enumerate(states):
        ric = embedder.embed_state(game, state)
        q_bf = extract_board_features(state.board, state.current_player)

        # Retrieve candidates
        all_candidates = {}
        for vec, vec_name in [
            (ric.components, "components"),
            (ric.inputs, "inputs"),
            (ric.relationships, "relationships"),
        ]:
            points = _search_vector(
                embedder.client, collection, vec, vec_name,
                limit=top_k, with_vectors=True,
            )
            for p in points:
                if p.id not in all_candidates and p.vector and isinstance(p.vector, dict):
                    all_candidates[p.id] = {"vector": p.vector, "payload": p.payload}

        cand_bfs, cand_cs, cand_is, cand_rs, labels = [], [], [], [], []
        has_positive = False

        for pid, data in all_candidates.items():
            vec = data["vector"]
            payload = data["payload"] or {}

            c_comp = np.array(vec.get("components", []), dtype=np.float32)
            c_inp = np.array(vec.get("inputs", []), dtype=np.float32)
            c_rel = np.array(vec.get("relationships", []), dtype=np.float32)
            if c_comp.size == 0 or c_inp.size == 0 or c_rel.size == 0:
                continue

            # Extract board features from candidate's stored board
            cand_board_str = payload.get("board", "")
            try:
                cand_board = eval(cand_board_str) if isinstance(cand_board_str, str) else cand_board_str
                cand_player = payload.get("current_player", 1)
                c_bf = extract_board_features(cand_board, cand_player)
            except Exception:
                c_bf = np.zeros(BOARD_FEATURE_DIM, dtype=np.float32)

            cand_bfs.append(c_bf)
            cand_cs.append(c_comp)
            cand_is.append(c_inp)
            cand_rs.append(c_rel)

            cand_move = payload.get("optimal_move")
            label = 1.0 if cand_move == true_move else 0.0
            labels.append(label)
            if label == 1.0:
                has_positive = True

        if has_positive and len(labels) >= 2:
            groups.append(QueryGroupV2(
                query_board_features=q_bf,
                query_comp=ric.components,
                query_inp=ric.inputs,
                query_rel=ric.relationships,
                cand_board_features=cand_bfs,
                cand_comps=cand_cs,
                cand_inps=cand_is,
                cand_rels=cand_rs,
                labels=labels,
                true_move=true_move,
            ))

        if (idx + 1) % 100 == 0:
            logger.info(f"  [{idx + 1}/{len(states)}] {len(groups)} groups")

    logger.info(f"Generated {len(groups)} query groups (v2)")
    return groups


class ListwiseDatasetV2(Dataset):
    def __init__(self, groups: list[QueryGroupV2], max_k: int = 0):
        self.groups = groups
        self.max_k = max_k or max(len(g.labels) for g in groups)

    def __len__(self):
        return len(self.groups)

    def __getitem__(self, idx):
        g = self.groups[idx]
        K = len(g.labels)
        pad = self.max_k - K

        def _pad_stack(arrays, dim):
            t = torch.from_numpy(np.stack(arrays))
            if pad > 0:
                t = torch.cat([t, torch.zeros(pad, dim)])
            return t

        return {
            "query_bf": torch.from_numpy(g.query_board_features),
            "query_comp": torch.from_numpy(g.query_comp),
            "query_inp": torch.from_numpy(g.query_inp),
            "query_rel": torch.from_numpy(g.query_rel),
            "cand_bf": _pad_stack(g.cand_board_features, BOARD_FEATURE_DIM),
            "cand_comp": _pad_stack(g.cand_comps, 384),
            "cand_inp": _pad_stack(g.cand_inps, 384),
            "cand_rel": _pad_stack(g.cand_rels, 384),
            "labels": torch.tensor(g.labels + [0.0] * pad, dtype=torch.float32),
            "mask": torch.cat([torch.ones(K), torch.zeros(pad)]),
        }


# ---------------------------------------------------------------------------
# V2 Model: SimilarityScorer with board features
# ---------------------------------------------------------------------------


class SimilarityScorerV2(nn.Module):
    """Learned scoring on cosine sims + board feature differences.

    Input features per (query, candidate) pair:
      - 3 cosine similarities (components, inputs, relationships)
      - 3 query vector norms + 3 candidate vector norms
      - Board feature difference (query - candidate): BOARD_FEATURE_DIM dims
      - Board feature product (query * candidate): BOARD_FEATURE_DIM dims
      Total: 9 + 2 * BOARD_FEATURE_DIM = 57 features
    """

    def __init__(self, hidden_dim: int = 64, num_layers: int = 3, dropout: float = 0.1):
        super().__init__()
        in_features = 9 + 2 * BOARD_FEATURE_DIM  # 57
        layers: list[nn.Module] = []
        prev = in_features
        for i in range(num_layers):
            layers.extend([
                nn.Linear(prev, hidden_dim),
                nn.SiLU(),
                nn.Dropout(dropout),
            ])
            prev = hidden_dim
        layers.append(nn.Linear(prev, 1))
        self.mlp = nn.Sequential(*layers)
        self.H_cycles = 1  # compatibility

    def forward(self, query_comp, query_inp, query_rel, cand_comp, cand_inp, cand_rel,
                query_bf=None, cand_bf=None):
        # Cosine similarities
        sim_c = F.cosine_similarity(query_comp, cand_comp, dim=-1, eps=1e-8).unsqueeze(-1)
        sim_i = F.cosine_similarity(query_inp, cand_inp, dim=-1, eps=1e-8).unsqueeze(-1)
        sim_r = F.cosine_similarity(query_rel, cand_rel, dim=-1, eps=1e-8).unsqueeze(-1)

        # Norms
        q_norms = torch.stack([
            query_comp.norm(dim=-1), query_inp.norm(dim=-1), query_rel.norm(dim=-1),
        ], dim=-1)
        c_norms = torch.stack([
            cand_comp.norm(dim=-1), cand_inp.norm(dim=-1), cand_rel.norm(dim=-1),
        ], dim=-1)

        parts = [sim_c, sim_i, sim_r, q_norms, c_norms]

        # Board features: difference and element-wise product
        if query_bf is not None and cand_bf is not None:
            bf_diff = query_bf - cand_bf  # what changed
            bf_prod = query_bf * cand_bf  # what's shared
            parts.extend([bf_diff, bf_prod])

        features = torch.cat(parts, dim=-1)
        scores = self.mlp(features)
        return scores, torch.zeros_like(scores), [scores]

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# Training loop (listwise, same as v1)
# ---------------------------------------------------------------------------


def get_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def compute_loss_v2(model, batch, device):
    B, K, D = batch["cand_comp"].shape
    BF = batch["cand_bf"].shape[-1]

    # Expand query: [B, ...] → [B*K, ...]
    q_comp = batch["query_comp"].unsqueeze(1).expand(B, K, D).reshape(B * K, D)
    q_inp = batch["query_inp"].unsqueeze(1).expand(B, K, D).reshape(B * K, D)
    q_rel = batch["query_rel"].unsqueeze(1).expand(B, K, D).reshape(B * K, D)
    q_bf = batch["query_bf"].unsqueeze(1).expand(B, K, BF).reshape(B * K, BF)

    c_comp = batch["cand_comp"].reshape(B * K, D)
    c_inp = batch["cand_inp"].reshape(B * K, D)
    c_rel = batch["cand_rel"].reshape(B * K, D)
    c_bf = batch["cand_bf"].reshape(B * K, BF)

    scores, _, _ = model(q_comp, q_inp, q_rel, c_comp, c_inp, c_rel, q_bf, c_bf)

    scores_2d = scores.squeeze(-1).reshape(B, K)
    labels = batch["labels"]
    mask = batch["mask"]

    scores_2d = scores_2d.masked_fill(mask == 0, -1e9)

    label_sums = labels.sum(dim=-1, keepdim=True).clamp(min=1.0)
    target_dist = labels / label_sums

    log_probs = F.log_softmax(scores_2d, dim=-1)
    loss = -(target_dist * log_probs).sum(dim=-1).mean()

    with torch.no_grad():
        top1 = scores_2d.argmax(dim=-1)
        correct = labels[torch.arange(B, device=device), top1]
        acc = correct.mean().item()

    return loss, {"loss": loss.item(), "accuracy": acc}


def main():
    parser = argparse.ArgumentParser(description="TRPN V2 Training")
    parser.add_argument("--game", default="mancala")
    parser.add_argument("--train-size", type=int, default=2000)
    parser.add_argument("--val-size", type=int, default=500)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--dropout", type=float, default=0.15)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--qdrant-url", type=str, default=None,
                        help="Qdrant URL for persistent storage (default: in-memory)")
    parser.add_argument("--qdrant-key", type=str, default=None)
    parser.add_argument("--checkpoint-dir", type=str,
                        default=str(Path(__file__).resolve().parent / "checkpoints"))
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # --- Game with deeper solver ---
    game = Mancala(search_depth=12)
    logger.info(f"Game: {game.name} (depth=12, transposition table)")

    # --- Generate states ---
    total = args.train_size + args.val_size
    logger.info(f"Generating {total} states with depth-12 solver...")
    t0 = time.time()
    all_states = game.generate_states(total)
    np.random.shuffle(all_states)
    train_states = all_states[:args.train_size]
    val_states = all_states[args.train_size:args.train_size + args.val_size]
    logger.info(f"Generated {len(train_states)} train + {len(val_states)} val in {time.time()-t0:.1f}s")

    # --- Qdrant setup (persistent or in-memory) ---
    qdrant_url = args.qdrant_url or os.environ.get("QDRANT_URL")
    qdrant_key = args.qdrant_key or os.environ.get("QDRANT_KEY")

    if qdrant_url:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=30)
        logger.info(f"Qdrant: persistent at {qdrant_url}")
    else:
        client = None
        logger.info("Qdrant: in-memory")

    embedder = RICEmbedder(client=client)
    collection = "trpn_mancala_v2"

    logger.info(f"Indexing {len(train_states)} states into '{collection}'...")
    t0 = time.time()
    embedder.create_collection(collection, force_recreate=True)
    embedder.index_states(game, train_states, collection)
    logger.info(f"Indexed in {time.time()-t0:.1f}s")

    # --- Generate query groups with board features ---
    logger.info("Generating v2 query groups...")
    t0 = time.time()
    train_groups = generate_groups_v2(game, embedder, collection, train_states, args.top_k)
    val_groups = generate_groups_v2(game, embedder, collection, val_states, args.top_k)
    logger.info(f"Generated {len(train_groups)} train + {len(val_groups)} val groups in {time.time()-t0:.1f}s")

    # --- Dataloaders ---
    max_k = max(
        max(len(g.labels) for g in train_groups),
        max(len(g.labels) for g in val_groups),
    )
    train_ds = ListwiseDatasetV2(train_groups, max_k)
    val_ds = ListwiseDatasetV2(val_groups, max_k)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    # --- Model ---
    device = get_device()
    model = SimilarityScorerV2(
        hidden_dim=args.hidden_dim, num_layers=3, dropout=args.dropout,
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
        # Train
        model.train()
        train_loss, train_acc, n = 0.0, 0.0, 0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            optimizer.zero_grad()
            loss, metrics = compute_loss_v2(model, batch, device)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            train_loss += metrics["loss"]
            train_acc += metrics["accuracy"]
            n += 1
        train_loss /= max(n, 1)
        train_acc /= max(n, 1)

        # Validate
        model.eval()
        val_loss, val_acc, nv = 0.0, 0.0, 0
        with torch.no_grad():
            for batch in val_loader:
                batch = {k: v.to(device) for k, v in batch.items()}
                loss, metrics = compute_loss_v2(model, batch, device)
                val_loss += metrics["loss"]
                val_acc += metrics["accuracy"]
                nv += 1
        val_loss /= max(nv, 1)
        val_acc /= max(nv, 1)

        logger.info(
            f"Epoch {epoch:3d}/{args.epochs} "
            f"| train_loss={train_loss:.4f} train_acc={train_acc:.3f} "
            f"| val_loss={val_loss:.4f} val_acc={val_acc:.3f}"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            patience_counter = 0
            ckpt = ckpt_dir / "best_model_v2.pt"
            torch.save({
                "model_state_dict": model.state_dict(),
                "model_type": "similarity_v2",
                "hidden_dim": args.hidden_dim,
                "dropout": args.dropout,
                "epoch": epoch,
                "val_accuracy": val_acc,
                "game": game.name,
            }, ckpt)
            logger.info(f"  New best val_acc={val_acc:.3f} → {ckpt}")
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                logger.info(f"Early stopping at epoch {epoch}")
                break

    logger.info(f"\nBest validation accuracy: {best_val_acc:.3f}")


if __name__ == "__main__":
    main()
