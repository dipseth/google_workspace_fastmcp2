"""Inference-time search using the trained TinyProjectionNetwork.

Plugs into the existing evaluation framework by returning the same
SearchResult type as single_pass_search / multi_dimensional_search.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import torch

# Allow imports from parent poc/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from recursive_search import SearchResult, _search_vector  # noqa: E402

from .model import TinyProjectionNetwork  # noqa: E402

logger = logging.getLogger(__name__)


def learned_recursive_search(
    client,
    collection_name: str,
    z_H: np.ndarray,
    z_L: np.ndarray,
    x: np.ndarray,
    model: TinyProjectionNetwork,
    top_k: int = 5,
    candidate_pool: int = 20,
) -> SearchResult:
    """Score candidates using the trained projection network.

    Steps:
      1. Retrieve candidate_pool candidates from Qdrant via 3 named-vector
         searches (same candidate expansion as multi_dimensional_search)
      2. Collect unique candidates with their stored RIC vectors
      3. Run model.forward(query, candidate) for each candidate → score
      4. Sort by score, return top_k as SearchResult

    Args:
        client: QdrantClient instance
        collection_name: Qdrant collection to search
        z_H: Query components vector [384]
        z_L: Query relationships vector [384]
        x: Query inputs vector [384]
        model: Trained TinyProjectionNetwork (should be in eval mode)
        top_k: Number of results to return
        candidate_pool: Number of candidates to retrieve per vector

    Returns:
        SearchResult compatible with evaluation framework's _tally()
    """
    # Expand candidate pool (same as multi_dimensional_search lines 116-127)
    all_candidates: dict[int, dict] = {}
    for vec, vec_name in [
        (z_H, "components"),
        (z_L, "relationships"),
        (x, "inputs"),
    ]:
        points = _search_vector(
            client,
            collection_name,
            vec,
            vec_name,
            limit=candidate_pool,
            with_vectors=True,
        )
        for p in points:
            if p.id not in all_candidates and p.vector and isinstance(p.vector, dict):
                all_candidates[p.id] = {
                    "vector": p.vector,
                    "payload": p.payload,
                }

    # Get cycle count from model (TinyProjectionNetwork vs SimilarityScorer)
    h_cycles = getattr(model, "H_cycles", None) or getattr(model.config, "H_cycles", 1)

    if not all_candidates:
        return SearchResult(
            top_ids=[],
            top_payloads=[],
            rrf_scores={},
            cycles_used=h_cycles,
            halted_early=False,
        )

    # Build batch tensors for model
    pids: list[int] = []
    cand_comps: list[np.ndarray] = []
    cand_inps: list[np.ndarray] = []
    cand_rels: list[np.ndarray] = []

    for pid, data in all_candidates.items():
        vec = data["vector"]
        c_comp = np.array(vec.get("components", []), dtype=np.float32)
        c_inp = np.array(vec.get("inputs", []), dtype=np.float32)
        c_rel = np.array(vec.get("relationships", []), dtype=np.float32)

        if c_comp.size == 0 or c_inp.size == 0 or c_rel.size == 0:
            continue

        pids.append(pid)
        cand_comps.append(c_comp)
        cand_inps.append(c_inp)
        cand_rels.append(c_rel)

    if not pids:
        return SearchResult(
            top_ids=[],
            top_payloads=[],
            rrf_scores={},
            cycles_used=h_cycles,
            halted_early=False,
        )

    K = len(pids)

    # Detect model device (CPU, MPS, or CUDA)
    device = next(model.parameters()).device

    # Expand query to batch size K (one copy per candidate)
    query_comp_t = torch.from_numpy(z_H).unsqueeze(0).expand(K, -1).to(device)
    query_inp_t = torch.from_numpy(x).unsqueeze(0).expand(K, -1).to(device)
    query_rel_t = torch.from_numpy(z_L).unsqueeze(0).expand(K, -1).to(device)

    cand_comp_t = torch.from_numpy(np.stack(cand_comps)).to(device)
    cand_inp_t = torch.from_numpy(np.stack(cand_inps)).to(device)
    cand_rel_t = torch.from_numpy(np.stack(cand_rels)).to(device)

    # Score all candidates in one forward pass
    with torch.no_grad():
        scores, halt_logits, _ = model(
            query_comp_t,
            query_inp_t,
            query_rel_t,
            cand_comp_t,
            cand_inp_t,
            cand_rel_t,
        )

    scores_np = scores.squeeze(-1).cpu().numpy()  # [K] — move back to CPU for sorting

    # Sort by score descending
    scored = {pid: float(scores_np[i]) for i, pid in enumerate(pids)}
    sorted_ids = sorted(scored.keys(), key=lambda i: scored[i], reverse=True)

    payloads = {
        pid: data["payload"] for pid, data in all_candidates.items() if data["payload"]
    }

    return SearchResult(
        top_ids=sorted_ids[:top_k],
        top_payloads=[payloads[pid] for pid in sorted_ids[:top_k] if pid in payloads],
        rrf_scores=scored,
        cycles_used=h_cycles,
        halted_early=False,
    )
