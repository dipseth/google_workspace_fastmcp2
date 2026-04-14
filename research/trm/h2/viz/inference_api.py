"""Inference API for the TRPN visualization.

Runs a single inference query and returns detailed scoring data
for visualization: candidates, similarities, scores, rankings.

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.viz.inference_api
"""

from __future__ import annotations

import json
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import torch

# Allow imports from poc/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "poc"))

from games import Mancala  # noqa: E402
from recursive_search import (  # noqa: E402
    SearchResult,
    _cosine_sim,
    _search_vector,
    multi_dimensional_search,
    single_pass_search,
)
from ric_vectors import RICEmbedder  # noqa: E402

from ..evaluate import load_model  # noqa: E402
from ..lookahead_search import lookahead_search  # noqa: E402
from ..model import SimilarityScorer  # noqa: E402

# --- Global state (initialized once) ---
game = None
embedder = None
collection = None
model = None
all_states = None


def init(train_size: int = 500, checkpoint: str | None = None):
    """Initialize game, embedder, Qdrant collection, and model."""
    global game, embedder, collection, all_states, model

    game = Mancala(search_depth=6)
    embedder = RICEmbedder()
    collection = "trpn_viz"

    print("Generating states...")
    all_states = game.generate_states(train_size + 100)
    rng = np.random.RandomState(42)
    indices = rng.permutation(len(all_states))
    all_states = [all_states[i] for i in indices]

    train_states = all_states[:train_size]

    print(f"Indexing {len(train_states)} states...")
    embedder.create_collection(collection, force_recreate=True)
    embedder.index_states(game, train_states, collection)

    if checkpoint:
        model = load_model(checkpoint)
    else:
        ckpt_path = str(
            Path(__file__).resolve().parent.parent / "checkpoints" / "best_model.pt"
        )
        model = load_model(ckpt_path)

    print(f"Ready. {len(train_states)} indexed, model loaded.")


def run_inference(state_idx: int = 0) -> dict:
    """Run inference on a single state and return detailed results."""
    # Pick a test state (from the non-indexed portion)
    idx = min(state_idx, len(all_states) - 1)
    state, true_move = all_states[idx]

    # Board representation
    board = list(state.board)
    legal_moves = game.legal_moves(state)

    # Embed
    ric = embedder.embed_state(game, state)
    z_H, z_L, x = ric.components, ric.relationships, ric.inputs

    # Get RIC texts for display
    comp_text = game.component_text(state)
    inp_text = game.inputs_text(state)
    rel_text = game.relationships_text(state)

    # --- Retrieve candidates with vectors ---
    all_candidates = {}
    for vec, vec_name in [(z_H, "components"), (z_L, "relationships"), (x, "inputs")]:
        points = _search_vector(
            embedder.client,
            collection,
            vec,
            vec_name,
            limit=20,
            with_vectors=True,
        )
        for p in points:
            if p.id not in all_candidates and p.vector and isinstance(p.vector, dict):
                all_candidates[p.id] = {"vector": p.vector, "payload": p.payload}

    # --- Score each candidate with all methods ---
    candidates_detail = []
    for pid, data in all_candidates.items():
        vec = data["vector"]
        payload = data["payload"] or {}

        c_comp = np.array(vec.get("components", []), dtype=np.float32)
        c_inp = np.array(vec.get("inputs", []), dtype=np.float32)
        c_rel = np.array(vec.get("relationships", []), dtype=np.float32)

        if c_comp.size == 0 or c_inp.size == 0 or c_rel.size == 0:
            continue

        sim_c = float(_cosine_sim(z_H, c_comp))
        sim_i = float(_cosine_sim(x, c_inp))
        sim_r = float(_cosine_sim(z_L, c_rel))

        # Multi-dim score
        multi_score = max(0, sim_c) * max(0, sim_r) * max(0, sim_i)

        # Learned score
        device = next(model.parameters()).device
        with torch.no_grad():
            scores_t, _, _ = model(
                torch.from_numpy(z_H).unsqueeze(0).to(device),
                torch.from_numpy(x).unsqueeze(0).to(device),
                torch.from_numpy(z_L).unsqueeze(0).to(device),
                torch.from_numpy(c_comp).unsqueeze(0).to(device),
                torch.from_numpy(c_inp).unsqueeze(0).to(device),
                torch.from_numpy(c_rel).unsqueeze(0).to(device),
            )
            learned_score = float(scores_t.squeeze().cpu())

        cand_move = payload.get("optimal_move")
        is_correct = cand_move == true_move

        candidates_detail.append(
            {
                "id": pid,
                "optimal_move": cand_move,
                "is_correct": is_correct,
                "board": payload.get("board", ""),
                "sim_components": round(sim_c, 4),
                "sim_inputs": round(sim_i, 4),
                "sim_relationships": round(sim_r, 4),
                "multi_score": round(multi_score, 6),
                "learned_score": round(learned_score, 4),
            }
        )

    # Sort by each method
    by_multi = sorted(candidates_detail, key=lambda c: c["multi_score"], reverse=True)
    by_learned = sorted(
        candidates_detail, key=lambda c: c["learned_score"], reverse=True
    )

    # Assign ranks
    for rank, c in enumerate(by_multi):
        c["multi_rank"] = rank + 1
    for rank, c in enumerate(by_learned):
        c["learned_rank"] = rank + 1

    # Also run single-pass for comparison
    sp = single_pass_search(embedder.client, collection, z_H, z_L, x, top_k=5)
    sp_move = sp.top_payloads[0].get("optimal_move") if sp.top_payloads else None

    md = multi_dimensional_search(
        embedder.client, collection, z_H, z_L, x, top_k=5, candidate_pool=20
    )
    md_move = md.top_payloads[0].get("optimal_move") if md.top_payloads else None

    learned_move = by_learned[0]["optimal_move"] if by_learned else None

    return {
        "query": {
            "state_idx": idx,
            "board": board,
            "current_player": state.current_player,
            "legal_moves": legal_moves,
            "true_optimal_move": true_move,
            "component_text": comp_text[:200],
            "inputs_text": inp_text[:300],
            "relationships_text": rel_text[:200],
        },
        "predictions": {
            "single_pass": {"move": sp_move, "correct": sp_move == true_move},
            "multi_dimensional": {"move": md_move, "correct": md_move == true_move},
            "learned": {"move": learned_move, "correct": learned_move == true_move},
        },
        "candidates": by_learned[:15],  # top 15 by learned score
        "total_candidates": len(candidates_detail),
        "total_states": len(all_states),
        "train_size": len(all_states) - 100,  # test states start after train
    }


def run_lookahead(state_idx: int = 0, depth: int = 3) -> dict:
    """Run lookahead search and return path data for visualization."""
    idx = min(state_idx, len(all_states) - 1)
    state, true_move = all_states[idx]

    result = lookahead_search(
        game,
        state,
        embedder,
        collection,
        model,
        depth=depth,
        candidate_pool=15,
    )

    # Build serializable path tree
    def _serialize_node(node, depth_remaining):
        children = []
        if depth_remaining > 0:
            for c in node.children:
                children.append(_serialize_node(c, depth_remaining - 1))
        return {
            "move": node.move,
            "board": list(node.state.board),
            "current_player": node.state.current_player,
            "score": round(node.score, 3),
            "predicted_move": node.top_candidate_move,
            "children": children,
        }

    paths_data = {}
    for move, node in result.paths.items():
        paths_data[str(move)] = _serialize_node(node, depth)

    return {
        "query": {
            "board": list(state.board),
            "current_player": state.current_player,
            "true_optimal_move": true_move,
            "legal_moves": game.legal_moves(state),
        },
        "move_scores": {
            str(k): round(v, 3) for k, v in result.root_move_scores.items()
        },
        "best_move": result.best_move,
        "best_avg_score": round(result.best_avg_score, 3),
        "is_correct": result.best_move == true_move,
        "depth": result.depth,
        "paths": paths_data,
    }


class VizHandler(SimpleHTTPRequestHandler):
    """HTTP handler: serves React app and /api endpoints."""

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/infer":
            params = parse_qs(parsed.query)
            state_idx = int(params.get("idx", [500])[0])
            self._json_response(run_inference(state_idx))

        elif parsed.path == "/api/lookahead":
            params = parse_qs(parsed.query)
            state_idx = int(params.get("idx", [500])[0])
            depth = int(params.get("depth", [3])[0])
            self._json_response(run_lookahead(state_idx, depth))

        elif parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html_path = Path(__file__).parent / "index.html"
            self.wfile.write(html_path.read_bytes())

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logs


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--train-size", type=int, default=500)
    parser.add_argument("--checkpoint", type=str, default=None)
    args = parser.parse_args()

    init(train_size=args.train_size, checkpoint=args.checkpoint)

    server = HTTPServer(("localhost", args.port), VizHandler)
    print(f"\nVisualization: http://localhost:{args.port}")
    print("API: http://localhost:{}/api/infer?idx=500\n".format(args.port))
    server.serve_forever()


if __name__ == "__main__":
    main()
