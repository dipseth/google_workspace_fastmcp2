"""Training data generation for the Tiny Recursive Projection Network.

Generates (query, candidate, label) triples by:
1. Embedding game states as RIC vectors
2. Retrieving top-K candidates from Qdrant
3. Labeling: 1.0 if candidate's optimal_move == query's true move, else 0.0
4. Augmenting with Gaussian noise on query vectors
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

# Allow imports from parent poc/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from games.base import Game, GameState  # noqa: E402
from recursive_search import _search_vector  # noqa: E402
from ric_vectors import RICEmbedder  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class TrainingSample:
    """One (query, candidate, label) triple."""

    query_comp: np.ndarray  # [384]
    query_inp: np.ndarray  # [384]
    query_rel: np.ndarray  # [384]
    cand_comp: np.ndarray  # [384]
    cand_inp: np.ndarray  # [384]
    cand_rel: np.ndarray  # [384]
    label: float  # 1.0 if correct move, 0.0 otherwise
    true_move: int  # ground truth optimal move for query


def generate_training_data(
    game: Game,
    embedder: RICEmbedder,
    collection_name: str,
    states: list[tuple[GameState, int]],
    top_k: int = 20,
    noise_augments: int = 2,
    noise_sigma: float = 0.01,
) -> list[TrainingSample]:
    """Generate training triples from indexed game states.

    For each query state:
      1. Embed as 3 RIC vectors
      2. Retrieve top_k candidates from Qdrant (with vectors)
      3. Label each candidate: 1.0 if optimal_move matches, 0.0 otherwise
      4. Augment: add Gaussian noise to query vectors, re-pair with same candidates
    """
    samples: list[TrainingSample] = []
    total = len(states)

    for idx, (state, true_move) in enumerate(states):
        ric = embedder.embed_state(game, state)
        q_comp = ric.components
        q_inp = ric.inputs
        q_rel = ric.relationships

        # Retrieve candidates with vectors from all 3 named vectors
        all_candidates: dict[int, dict] = {}
        for vec, vec_name in [
            (q_comp, "components"),
            (q_inp, "inputs"),
            (q_rel, "relationships"),
        ]:
            points = _search_vector(
                embedder.client,
                collection_name,
                vec,
                vec_name,
                limit=top_k,
                with_vectors=True,
            )
            for p in points:
                if (
                    p.id not in all_candidates
                    and p.vector
                    and isinstance(p.vector, dict)
                ):
                    all_candidates[p.id] = {
                        "vector": p.vector,
                        "payload": p.payload,
                    }

        # Create samples from candidates
        for pid, data in all_candidates.items():
            vec = data["vector"]
            payload = data["payload"] or {}

            c_comp = np.array(vec.get("components", []), dtype=np.float32)
            c_inp = np.array(vec.get("inputs", []), dtype=np.float32)
            c_rel = np.array(vec.get("relationships", []), dtype=np.float32)

            if c_comp.size == 0 or c_inp.size == 0 or c_rel.size == 0:
                continue

            cand_move = payload.get("optimal_move")
            label = 1.0 if cand_move == true_move else 0.0

            # Original sample
            samples.append(
                TrainingSample(
                    query_comp=q_comp,
                    query_inp=q_inp,
                    query_rel=q_rel,
                    cand_comp=c_comp,
                    cand_inp=c_inp,
                    cand_rel=c_rel,
                    label=label,
                    true_move=true_move,
                )
            )

            # Noise-augmented samples
            rng = np.random.default_rng(seed=pid + idx)
            for _ in range(noise_augments):
                samples.append(
                    TrainingSample(
                        query_comp=q_comp
                        + rng.normal(0, noise_sigma, q_comp.shape).astype(np.float32),
                        query_inp=q_inp
                        + rng.normal(0, noise_sigma, q_inp.shape).astype(np.float32),
                        query_rel=q_rel
                        + rng.normal(0, noise_sigma, q_rel.shape).astype(np.float32),
                        cand_comp=c_comp,
                        cand_inp=c_inp,
                        cand_rel=c_rel,
                        label=label,
                        true_move=true_move,
                    )
                )

        if (idx + 1) % 50 == 0:
            pos = sum(1 for s in samples if s.label == 1.0)
            logger.info(
                f"  [{idx + 1}/{total}] {len(samples)} samples "
                f"({pos} positive, {len(samples) - pos} negative)"
            )

    pos_total = sum(1 for s in samples if s.label == 1.0)
    logger.info(
        f"Generated {len(samples)} total samples "
        f"({pos_total} positive, {len(samples) - pos_total} negative)"
    )
    return samples


class RICDataset(Dataset):
    """PyTorch Dataset wrapping TrainingSamples (pair-centric)."""

    def __init__(self, samples: list[TrainingSample]):
        self.samples = samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        s = self.samples[idx]
        return {
            "query_comp": torch.from_numpy(s.query_comp),
            "query_inp": torch.from_numpy(s.query_inp),
            "query_rel": torch.from_numpy(s.query_rel),
            "cand_comp": torch.from_numpy(s.cand_comp),
            "cand_inp": torch.from_numpy(s.cand_inp),
            "cand_rel": torch.from_numpy(s.cand_rel),
            "label": torch.tensor(s.label, dtype=torch.float32),
        }


@dataclass
class QueryGroup:
    """One query with all its candidate vectors and labels.

    For listwise/contrastive training: the model scores all K candidates
    together and learns to rank the correct one(s) highest.
    """

    query_comp: np.ndarray  # [384]
    query_inp: np.ndarray  # [384]
    query_rel: np.ndarray  # [384]
    cand_comps: list[np.ndarray]  # K × [384]
    cand_inps: list[np.ndarray]  # K × [384]
    cand_rels: list[np.ndarray]  # K × [384]
    labels: list[float]  # K labels (1.0 if correct move, else 0.0)
    true_move: int


def generate_query_groups(
    game: Game,
    embedder: RICEmbedder,
    collection_name: str,
    states: list[tuple[GameState, int]],
    top_k: int = 20,
) -> list[QueryGroup]:
    """Generate query-centric groups for listwise training.

    Each group: one query + K candidates with labels.
    No noise augmentation (handled by shuffle + multiple epochs).
    """
    groups: list[QueryGroup] = []
    total = len(states)

    for idx, (state, true_move) in enumerate(states):
        ric = embedder.embed_state(game, state)

        # Retrieve candidates with vectors
        all_candidates: dict[int, dict] = {}
        for vec, vec_name in [
            (ric.components, "components"),
            (ric.inputs, "inputs"),
            (ric.relationships, "relationships"),
        ]:
            points = _search_vector(
                embedder.client,
                collection_name,
                vec,
                vec_name,
                limit=top_k,
                with_vectors=True,
            )
            for p in points:
                if (
                    p.id not in all_candidates
                    and p.vector
                    and isinstance(p.vector, dict)
                ):
                    all_candidates[p.id] = {
                        "vector": p.vector,
                        "payload": p.payload,
                    }

        cand_comps, cand_inps, cand_rels, labels = [], [], [], []
        has_positive = False
        for pid, data in all_candidates.items():
            vec = data["vector"]
            c_comp = np.array(vec.get("components", []), dtype=np.float32)
            c_inp = np.array(vec.get("inputs", []), dtype=np.float32)
            c_rel = np.array(vec.get("relationships", []), dtype=np.float32)
            if c_comp.size == 0 or c_inp.size == 0 or c_rel.size == 0:
                continue
            cand_comps.append(c_comp)
            cand_inps.append(c_inp)
            cand_rels.append(c_rel)
            cand_move = (data["payload"] or {}).get("optimal_move")
            label = 1.0 if cand_move == true_move else 0.0
            labels.append(label)
            if label == 1.0:
                has_positive = True

        # Only include groups that have at least one positive candidate
        if has_positive and len(cand_comps) >= 2:
            groups.append(
                QueryGroup(
                    query_comp=ric.components,
                    query_inp=ric.inputs,
                    query_rel=ric.relationships,
                    cand_comps=cand_comps,
                    cand_inps=cand_inps,
                    cand_rels=cand_rels,
                    labels=labels,
                    true_move=true_move,
                )
            )

        if (idx + 1) % 100 == 0:
            logger.info(f"  [{idx + 1}/{total}] {len(groups)} groups")

    logger.info(f"Generated {len(groups)} query groups")
    return groups


class ListwiseDataset(Dataset):
    """Dataset for listwise training: each item is a query with K candidates.

    Returns padded tensors so all groups have the same K dimension.
    """

    def __init__(self, groups: list[QueryGroup], max_candidates: int = 0):
        self.groups = groups
        # Determine max K across all groups (or use provided max)
        self.max_k = max_candidates or max(len(g.labels) for g in groups)

    def __len__(self) -> int:
        return len(self.groups)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        g = self.groups[idx]
        K = len(g.labels)
        pad = self.max_k - K

        # Stack candidate vectors [K, 384] then pad to [max_k, 384]
        cand_comp = torch.from_numpy(np.stack(g.cand_comps))
        cand_inp = torch.from_numpy(np.stack(g.cand_inps))
        cand_rel = torch.from_numpy(np.stack(g.cand_rels))

        if pad > 0:
            z = torch.zeros(pad, cand_comp.shape[1])
            cand_comp = torch.cat([cand_comp, z])
            cand_inp = torch.cat([cand_inp, z])
            cand_rel = torch.cat([cand_rel, z])

        labels = torch.tensor(g.labels + [0.0] * pad, dtype=torch.float32)
        mask = torch.cat([torch.ones(K), torch.zeros(pad)])  # 1 = real, 0 = pad

        return {
            "query_comp": torch.from_numpy(g.query_comp),  # [384]
            "query_inp": torch.from_numpy(g.query_inp),  # [384]
            "query_rel": torch.from_numpy(g.query_rel),  # [384]
            "cand_comp": cand_comp,  # [max_k, 384]
            "cand_inp": cand_inp,  # [max_k, 384]
            "cand_rel": cand_rel,  # [max_k, 384]
            "labels": labels,  # [max_k]
            "mask": mask,  # [max_k]
        }


def create_listwise_dataloaders(
    train_groups: list[QueryGroup],
    val_groups: list[QueryGroup],
    batch_size: int = 32,
) -> tuple[DataLoader, DataLoader]:
    """Create dataloaders for listwise training."""
    max_k = max(
        max(len(g.labels) for g in train_groups),
        max(len(g.labels) for g in val_groups),
    )
    train_ds = ListwiseDataset(train_groups, max_candidates=max_k)
    val_ds = ListwiseDataset(val_groups, max_candidates=max_k)
    return (
        DataLoader(train_ds, batch_size=batch_size, shuffle=True),
        DataLoader(val_ds, batch_size=batch_size, shuffle=False),
    )


def create_dataloaders(
    train_samples: list[TrainingSample],
    val_samples: list[TrainingSample],
    batch_size: int = 64,
) -> tuple[DataLoader, DataLoader]:
    """Create train and validation DataLoaders."""
    train_ds = RICDataset(train_samples)
    val_ds = RICDataset(val_samples)
    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, drop_last=False
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, drop_last=False
    )
    return train_loader, val_loader
