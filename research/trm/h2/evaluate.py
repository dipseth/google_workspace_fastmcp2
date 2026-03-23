"""Evaluate the trained TRPN against all baseline search methods.

Extends poc/evaluation/accuracy.py by adding the learned_recursive method
to the comparison table.

Usage:
    cd research/trm/poc
    uv run python ../h2/evaluate.py --game mancala --checkpoint ../h2/checkpoints/best_model.pt
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import torch

# Allow imports from parent poc/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from games import Connect4, Mancala, TicTacToe  # noqa: E402
from recursive_search import (  # noqa: E402
    multi_dimensional_search,
    single_pass_search,
)
from ric_vectors import RICEmbedder  # noqa: E402

from .learned_search import learned_recursive_search  # noqa: E402
from .model import SimilarityScorer, TinyProjectionNetwork, TRPNConfig  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GAMES = {
    "tictactoe": TicTacToe,
    "connect4": lambda: Connect4(search_depth=4),
    "mancala": lambda: Mancala(search_depth=6),
}


def _extract_top_move(payloads: list[dict]) -> int | None:
    if payloads:
        return payloads[0].get("optimal_move")
    return None


def _extract_top_k_moves(payloads: list[dict], k: int) -> list[int]:
    moves = []
    for p in payloads[:k]:
        m = p.get("optimal_move")
        if m is not None:
            moves.append(m)
    return moves


def _tally(method_dict: dict, result, true_move: int, cycles: int = 1):
    move = _extract_top_move(result.top_payloads)
    top3 = _extract_top_k_moves(result.top_payloads, 3)
    if move == true_move:
        method_dict["top1"] += 1
    if true_move in top3:
        method_dict["top3"] += 1
    method_dict["cycles"].append(cycles)


def evaluate_with_learned(
    game,
    embedder: RICEmbedder,
    collection_name: str,
    test_states: list[tuple],
    model: TinyProjectionNetwork,
    top_k: int = 5,
) -> dict:
    """Run all methods (baselines + learned) on test states."""
    methods: dict[str, dict] = {
        "single_pass": {"top1": 0, "top3": 0, "cycles": []},
        "multi_multiply": {"top1": 0, "top3": 0, "cycles": []},
        "multi_harmonic": {"top1": 0, "top3": 0, "cycles": []},
        "learned_recursive": {"top1": 0, "top3": 0, "cycles": []},
    }

    total = 0
    model.eval()

    for i, (state, true_move) in enumerate(test_states):
        ric = embedder.embed_state(game, state)
        z_H = ric.components
        z_L = ric.relationships
        x = ric.inputs

        # Single-pass RRF
        sp = single_pass_search(embedder.client, collection_name, z_H, z_L, x, top_k=top_k)
        _tally(methods["single_pass"], sp, true_move)

        # Multi-dimensional scoring
        for scoring, key in [("multiplicative", "multi_multiply"), ("harmonic", "multi_harmonic")]:
            md = multi_dimensional_search(
                embedder.client, collection_name, z_H, z_L, x,
                top_k=top_k, candidate_pool=20, scoring=scoring,
            )
            _tally(methods[key], md, true_move)

        # Learned recursive
        lr = learned_recursive_search(
            embedder.client, collection_name, z_H, z_L, x,
            model=model, top_k=top_k, candidate_pool=20,
        )
        _tally(methods["learned_recursive"], lr, true_move, lr.cycles_used)

        total += 1

        if (i + 1) % 20 == 0:
            parts = [f"{k}={v['top1']}/{total}" for k, v in methods.items()]
            logger.info(f"  [{i + 1}/{len(test_states)}] " + " ".join(parts))

    result = {"total": total, "methods": {}}
    for name, m in methods.items():
        cycles = m["cycles"]
        result["methods"][name] = {
            "top1_correct": m["top1"],
            "top1_accuracy": m["top1"] / total if total else 0,
            "top3_correct": m["top3"],
            "top3_accuracy": m["top3"] / total if total else 0,
            "mean_cycles": float(np.mean(cycles)) if cycles else 0,
        }
    return result


def _get_device() -> torch.device:
    """Select best available device: MPS (Apple Silicon) > CUDA > CPU."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_model(checkpoint_path: str):
    """Load a trained model from checkpoint and move to best device."""
    device = _get_device()
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model_type = ckpt.get("model_type", "trpn")

    if model_type == "similarity":
        model = SimilarityScorer(
            hidden_dim=ckpt.get("hidden_dim", 32), num_layers=2
        )
    else:
        config = ckpt["config"]
        model = TinyProjectionNetwork(config)

    model.load_state_dict(ckpt["model_state_dict"])
    model = model.to(device)
    model.eval()
    logger.info(
        f"Loaded {model_type} model from {checkpoint_path} "
        f"(epoch {ckpt.get('epoch', '?')}, "
        f"val_acc={ckpt.get('val_accuracy', '?'):.3f}, "
        f"device={device})"
    )
    return model


def main():
    parser = argparse.ArgumentParser(description="TRPN Evaluation")
    parser.add_argument(
        "--game", choices=list(GAMES.keys()), default="mancala", help="Game"
    )
    parser.add_argument("--train-size", type=int, default=2000)
    parser.add_argument("--test-size", type=int, default=500)
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=str(Path(__file__).resolve().parent / "checkpoints" / "best_model.pt"),
        help="Path to trained model checkpoint",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # Create game
    game_factory = GAMES[args.game]
    game = game_factory() if callable(game_factory) and not isinstance(game_factory, type) else game_factory()
    collection_name = f"trpn_{game.name}_eval"

    logger.info(f"=== TRPN Evaluation: {game.name} ===")

    # Generate states
    logger.info("Generating game states...")
    t0 = time.time()
    total_needed = args.train_size + args.test_size
    all_states = game.generate_states(total_needed)

    rng = np.random.RandomState(args.seed)
    indices = rng.permutation(len(all_states))
    all_states = [all_states[i] for i in indices]

    train_states = all_states[: args.train_size]
    test_states = all_states[args.train_size : args.train_size + args.test_size]
    logger.info(
        f"Generated {len(train_states)} train + {len(test_states)} test "
        f"in {time.time() - t0:.1f}s"
    )

    # Index training states
    embedder = RICEmbedder()
    embedder.create_collection(collection_name, force_recreate=True)
    logger.info("Indexing training states...")
    t0 = time.time()
    embedder.index_states(game, train_states, collection_name)
    logger.info(f"Indexed in {time.time() - t0:.1f}s")

    # Load model
    model = load_model(args.checkpoint)

    # Evaluate
    logger.info("Running evaluation...")
    t0 = time.time()
    results = evaluate_with_learned(
        game, embedder, collection_name, test_states, model
    )
    eval_time = time.time() - t0

    # Print results (same format as accuracy.py)
    baseline_acc = results["methods"]["single_pass"]["top1_accuracy"]

    print("\n" + "=" * 80)
    print(f"RESULTS: {game.name} (TRPN H2 Evaluation)")
    print(f"Train: {len(train_states)}, Test: {results['total']}")
    print(f"Evaluation time: {eval_time:.1f}s")
    print("=" * 80)

    print(
        f"\n{'Method':<20} {'Top-1':>8} {'Top-1%':>8} "
        f"{'Top-3':>8} {'Top-3%':>8} {'Cycles':>8} {'Delta':>8}"
    )
    print("-" * 80)
    for name, m in results["methods"].items():
        delta_str = (
            "baseline"
            if name == "single_pass"
            else f"{m['top1_accuracy'] - baseline_acc:>+7.1%}"
        )
        cyc_str = f"{m['mean_cycles']:.1f}" if m["mean_cycles"] > 1 else "1"
        print(
            f"{name:<20} "
            f"{m['top1_correct']:>5}/{results['total']:>2} "
            f"{m['top1_accuracy']:>7.1%} "
            f"{m['top3_correct']:>5}/{results['total']:>2} "
            f"{m['top3_accuracy']:>7.1%} "
            f"{cyc_str:>8} "
            f"{delta_str:>8}"
        )
    print("=" * 80)


if __name__ == "__main__":
    main()
