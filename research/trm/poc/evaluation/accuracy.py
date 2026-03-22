"""Compare recursive vs. single-pass search accuracy on solved games.

Metric: Does the top-1 retrieved state's optimal move match the
test state's true optimal move?

Usage:
    cd research/trm/poc
    uv run python evaluation/accuracy.py [--game tictactoe|connect4|mancala]
                                          [--train-size 500]
                                          [--test-size 100]
                                          [--max-cycles 6]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np

# Allow imports from parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from games import Connect4, Game, Mancala, TicTacToe
from ric_vectors import RICEmbedder
from recursive_search import (
    multi_dimensional_search,
    recursive_search,
    single_pass_search,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GAMES = {
    "tictactoe": TicTacToe,
    "connect4": lambda: Connect4(search_depth=4),
    "mancala": lambda: Mancala(search_depth=6),
}


STRATEGIES = ["centroid", "best_match", "score_weighted", "consistency"]


def evaluate_accuracy(
    game: Game,
    embedder: RICEmbedder,
    collection_name: str,
    test_states: list[tuple],
    max_cycles: int = 6,
    alpha: float = 0.3,
    beta: float = 0.3,
    ema_decay: float = 0.9,
    top_k: int = 5,
    strategies: list[str] | None = None,
) -> dict:
    """Run single-pass and recursive search (multiple strategies) on test states.

    Returns dict with accuracy metrics per strategy.
    """
    strategies = strategies or STRATEGIES

    # All methods: single_pass, multi-dimensional, recursive strategies
    methods: dict[str, dict] = {
        "single_pass": {"top1": 0, "top3": 0, "cycles": []},
        "multi_multiply": {"top1": 0, "top3": 0, "cycles": []},
        "multi_harmonic": {"top1": 0, "top3": 0, "cycles": []},
    }
    for strat in strategies:
        methods[f"rec_{strat}"] = {"top1": 0, "top3": 0, "cycles": []}

    total = 0

    for i, (state, true_move) in enumerate(test_states):
        ric = embedder.embed_state(game, state)
        z_H = ric.components
        z_L = ric.relationships
        x = ric.inputs

        # --- Single-pass RRF ---
        sp_result = single_pass_search(
            embedder.client, collection_name, z_H, z_L, x, top_k=top_k
        )
        _tally(methods["single_pass"], sp_result, true_move)

        # --- Multi-dimensional scoring ---
        for scoring, key in [("multiplicative", "multi_multiply"), ("harmonic", "multi_harmonic")]:
            md_result = multi_dimensional_search(
                embedder.client, collection_name, z_H, z_L, x,
                top_k=top_k, candidate_pool=20, scoring=scoring,
            )
            _tally(methods[key], md_result, true_move)

        # --- Recursive strategies ---
        for strat in strategies:
            rec_result = recursive_search(
                embedder.client, collection_name,
                z_H.copy(), z_L.copy(), x.copy(),
                max_cycles=max_cycles, alpha=alpha, beta=beta,
                ema_decay=ema_decay, top_k=top_k, strategy=strat,
            )
            _tally(methods[f"rec_{strat}"], rec_result, true_move, rec_result.cycles_used)

        total += 1

        if (i + 1) % 20 == 0:
            parts = [f"{k}={v['top1']}/{total}" for k, v in methods.items()]
            logger.info(f"  [{i + 1}/{len(test_states)}] " + " ".join(parts[:4]))

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


def _tally(method_dict: dict, result, true_move: int, cycles: int = 1):
    """Update accuracy counters for a method."""
    move = _extract_top_move(result.top_payloads)
    top3 = _extract_top_k_moves(result.top_payloads, 3)
    if move == true_move:
        method_dict["top1"] += 1
    if true_move in top3:
        method_dict["top3"] += 1
    method_dict["cycles"].append(cycles)


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


def main():
    parser = argparse.ArgumentParser(description="RIC-TRM Accuracy Evaluation")
    parser.add_argument(
        "--game",
        choices=list(GAMES.keys()),
        default="tictactoe",
        help="Game to evaluate",
    )
    parser.add_argument("--train-size", type=int, default=500)
    parser.add_argument("--test-size", type=int, default=100)
    parser.add_argument("--max-cycles", type=int, default=6)
    parser.add_argument("--alpha", type=float, default=0.3)
    parser.add_argument("--beta", type=float, default=0.3)
    parser.add_argument("--ema-decay", type=float, default=0.9)
    args = parser.parse_args()

    # Create game
    game_factory = GAMES[args.game]
    game = game_factory() if callable(game_factory) else game_factory

    collection_name = f"ric_trm_{game.name}"

    logger.info(f"=== RIC-TRM Accuracy: {game.name} ===")
    logger.info(f"Train: {args.train_size}, Test: {args.test_size}")

    # Generate states
    logger.info("Generating game states...")
    t0 = time.time()
    total_needed = args.train_size + args.test_size
    all_states = game.generate_states(max_states=total_needed)
    logger.info(f"Generated {len(all_states)} states in {time.time() - t0:.1f}s")

    if len(all_states) < args.train_size + args.test_size:
        logger.warning(
            f"Only {len(all_states)} states available, adjusting split"
        )
        split = int(len(all_states) * 0.8)
    else:
        split = args.train_size

    # Shuffle deterministically
    rng = np.random.RandomState(42)
    indices = rng.permutation(len(all_states))
    all_states = [all_states[i] for i in indices]

    train_states = all_states[:split]
    test_states = all_states[split : split + args.test_size]

    logger.info(f"Train: {len(train_states)}, Test: {len(test_states)}")

    # Index training states
    logger.info("Embedding and indexing training states...")
    embedder = RICEmbedder()
    embedder.create_collection(collection_name, force_recreate=True)
    t0 = time.time()
    indexed = embedder.index_states(game, train_states, collection_name)
    logger.info(f"Indexed {indexed} states in {time.time() - t0:.1f}s")

    # Evaluate
    logger.info("Running evaluation...")
    t0 = time.time()
    results = evaluate_accuracy(
        game,
        embedder,
        collection_name,
        test_states,
        max_cycles=args.max_cycles,
        alpha=args.alpha,
        beta=args.beta,
        ema_decay=args.ema_decay,
    )
    eval_time = time.time() - t0

    # Print results
    print("\n" + "=" * 80)
    print(f"RESULTS: {game.name}")
    print(f"Train size: {len(train_states)}, Test size: {results['total']}")
    print(f"Evaluation time: {eval_time:.1f}s")
    print("=" * 80)

    baseline_acc = results["methods"]["single_pass"]["top1_accuracy"]

    print(f"\n{'Method':<20} {'Top-1':>8} {'Top-1%':>8} {'Top-3':>8} {'Top-3%':>8} {'Cycles':>8} {'Delta':>8}")
    print("-" * 80)
    for name, m in results["methods"].items():
        delta_str = "baseline" if name == "single_pass" else f"{m['top1_accuracy'] - baseline_acc:>+7.1%}"
        cyc_str = f"{m['mean_cycles']:.1f}" if m['mean_cycles'] > 1 else "1"
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

    return results


if __name__ == "__main__":
    main()
