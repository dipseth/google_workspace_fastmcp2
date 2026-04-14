"""Lookahead search: use the learned scorer as a position evaluator.

Instead of recursion in embedding space (TRM-style, which failed for small
models), recurse in game-tree space: apply moves, score resulting positions,
and pick the move whose path yields the highest average score over N steps.

This bridges H2 (learned scoring) with TRM's recursive refinement idea —
the "recursion" happens over game states, not embedding vectors.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch

# Allow imports from parent poc/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from games.base import Game, GameState  # noqa: E402
from recursive_search import _cosine_sim, _search_vector  # noqa: E402
from ric_vectors import RICEmbedder  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class PathNode:
    """One node in a lookahead path."""

    move: int  # move taken to reach this state
    state: GameState
    score: float  # learned scorer's evaluation of this position
    top_candidate_move: int | None  # what the scorer thinks the best move is
    children: list[PathNode] = field(default_factory=list)


@dataclass
class LookaheadResult:
    """Result of a lookahead search from one root state."""

    root_move_scores: dict[int, float]  # move → average path score
    best_move: int
    best_avg_score: float
    paths: dict[int, PathNode]  # move → full path tree
    depth: int


def _score_state(
    game: Game,
    state: GameState,
    embedder: RICEmbedder,
    collection: str,
    model,
    candidate_pool: int = 20,
) -> tuple[float, int | None]:
    """Score a game state using the learned model.

    Returns (best_learned_score, predicted_move) for this position.
    The score represents how "recognizable" this state is — higher means
    the model found a strong match in the training set.
    """
    ric = embedder.embed_state(game, state)
    z_H, z_L, x = ric.components, ric.relationships, ric.inputs

    # Retrieve candidates
    all_candidates = {}
    for vec, vec_name in [(z_H, "components"), (z_L, "relationships"), (x, "inputs")]:
        points = _search_vector(
            embedder.client, collection, vec, vec_name,
            limit=candidate_pool, with_vectors=True,
        )
        for p in points:
            if p.id not in all_candidates and p.vector and isinstance(p.vector, dict):
                all_candidates[p.id] = {"vector": p.vector, "payload": p.payload}

    if not all_candidates:
        return 0.0, None

    # Score each candidate
    device = next(model.parameters()).device
    best_score = float("-inf")
    best_move = None

    for pid, data in all_candidates.items():
        vec = data["vector"]
        c_comp = np.array(vec.get("components", []), dtype=np.float32)
        c_inp = np.array(vec.get("inputs", []), dtype=np.float32)
        c_rel = np.array(vec.get("relationships", []), dtype=np.float32)

        if c_comp.size == 0 or c_inp.size == 0 or c_rel.size == 0:
            continue

        with torch.no_grad():
            scores_t, _, _ = model(
                torch.from_numpy(z_H).unsqueeze(0).to(device),
                torch.from_numpy(x).unsqueeze(0).to(device),
                torch.from_numpy(z_L).unsqueeze(0).to(device),
                torch.from_numpy(c_comp).unsqueeze(0).to(device),
                torch.from_numpy(c_inp).unsqueeze(0).to(device),
                torch.from_numpy(c_rel).unsqueeze(0).to(device),
            )
            score = float(scores_t.squeeze().cpu())

        if score > best_score:
            best_score = score
            best_move = (data["payload"] or {}).get("optimal_move")

    return best_score, best_move


def lookahead_search(
    game: Game,
    state: GameState,
    embedder: RICEmbedder,
    collection: str,
    model,
    depth: int = 3,
    candidate_pool: int = 15,
) -> LookaheadResult:
    """Evaluate each legal move by looking ahead `depth` steps.

    For each legal move:
      1. Apply the move → next state
      2. Score the next state with the model
      3. Recurse: for each of the opponent's responses, score again
      4. Average scores across the path

    Returns the move with the highest average path score.
    """
    legal_moves = game.legal_moves(state)
    if not legal_moves:
        return LookaheadResult(
            root_move_scores={}, best_move=-1,
            best_avg_score=0.0, paths={}, depth=depth,
        )

    move_scores: dict[int, list[float]] = {m: [] for m in legal_moves}
    paths: dict[int, PathNode] = {}

    def _explore(s: GameState, remaining: int) -> PathNode:
        """Recursively score a state and its children."""
        score, pred_move = _score_state(
            game, s, embedder, collection, model, candidate_pool,
        )
        node = PathNode(
            move=-1, state=s, score=score, top_candidate_move=pred_move,
        )

        if remaining > 0 and not game.is_terminal(s):
            child_moves = game.legal_moves(s)
            # Limit branching to top 3 moves to keep it tractable
            for cm in child_moves[:3]:
                next_state = game.apply_move(s, cm)
                child = _explore(next_state, remaining - 1)
                child.move = cm
                node.children.append(child)

        return node

    for move in legal_moves:
        next_state = game.apply_move(state, move)
        root_node = _explore(next_state, depth - 1)
        root_node.move = move
        paths[move] = root_node

        # Collect all scores along this path
        def _collect_scores(node: PathNode, scores: list[float]):
            scores.append(node.score)
            for child in node.children:
                _collect_scores(child, scores)

        path_scores: list[float] = []
        _collect_scores(root_node, path_scores)
        move_scores[move] = path_scores

    # Average score per initial move
    avg_scores = {}
    for move, scores in move_scores.items():
        avg_scores[move] = float(np.mean(scores)) if scores else 0.0

    best_move = max(avg_scores, key=lambda m: avg_scores[m])

    return LookaheadResult(
        root_move_scores=avg_scores,
        best_move=best_move,
        best_avg_score=avg_scores[best_move],
        paths=paths,
        depth=depth,
    )
