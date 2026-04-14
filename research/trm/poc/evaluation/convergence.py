"""Track convergence behavior of recursive RIC search.

Measures:
- How many cycles until ranking stabilizes
- z_H and z_L drift over cycles
- Score improvement per cycle
- Effect of alpha/beta/ema parameters

Usage:
    cd research/trm/poc
    uv run python evaluation/convergence.py [--game tictactoe|connect4|mancala]
                                             [--num-queries 50]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from games import Connect4, Game, Mancala, TicTacToe
from recursive_search import CycleInfo, recursive_search
from ric_vectors import RICEmbedder

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GAMES = {
    "tictactoe": TicTacToe,
    "connect4": lambda: Connect4(search_depth=4),
    "mancala": lambda: Mancala(search_depth=6),
}


def analyze_convergence(
    game: Game,
    embedder: RICEmbedder,
    collection_name: str,
    query_states: list[tuple],
    max_cycles: int = 10,
    alpha: float = 0.3,
    beta: float = 0.3,
    ema_decay: float = 0.9,
) -> dict:
    """Analyze convergence patterns across multiple queries."""
    all_cycle_counts = []
    all_z_H_drift = []  # drift per cycle, aggregated
    all_z_L_drift = []
    all_score_improvement = []
    halted_early_count = 0

    for i, (state, _) in enumerate(query_states):
        ric = embedder.embed_state(game, state)

        result = recursive_search(
            embedder.client,
            collection_name,
            ric.components,
            ric.relationships,
            ric.inputs,
            max_cycles=max_cycles,
            alpha=alpha,
            beta=beta,
            ema_decay=ema_decay,
        )

        all_cycle_counts.append(result.cycles_used)
        if result.halted_early:
            halted_early_count += 1

        # Track per-cycle metrics
        for info in result.cycle_history:
            while len(all_z_H_drift) <= info.cycle:
                all_z_H_drift.append([])
                all_z_L_drift.append([])
                all_score_improvement.append([])

            all_z_H_drift[info.cycle].append(info.z_H_drift)
            all_z_L_drift[info.cycle].append(info.z_L_drift)
            if info.comp_scores:
                all_score_improvement[info.cycle].append(info.comp_scores[0])

    return {
        "num_queries": len(query_states),
        "cycle_distribution": {
            "mean": float(np.mean(all_cycle_counts)),
            "median": float(np.median(all_cycle_counts)),
            "std": float(np.std(all_cycle_counts)),
            "min": int(np.min(all_cycle_counts)),
            "max": int(np.max(all_cycle_counts)),
        },
        "halted_early_pct": halted_early_count / len(query_states)
        if query_states
        else 0,
        "per_cycle": {
            "z_H_drift": [float(np.mean(d)) if d else 0.0 for d in all_z_H_drift],
            "z_L_drift": [float(np.mean(d)) if d else 0.0 for d in all_z_L_drift],
            "mean_top1_score": [
                float(np.mean(s)) if s else 0.0 for s in all_score_improvement
            ],
        },
    }


def sweep_parameters(
    game: Game,
    embedder: RICEmbedder,
    collection_name: str,
    query_states: list[tuple],
) -> list[dict]:
    """Sweep alpha, beta, ema_decay to find best convergence."""
    configs = [
        {"alpha": 0.1, "beta": 0.1, "ema_decay": 0.95},
        {"alpha": 0.3, "beta": 0.3, "ema_decay": 0.9},
        {"alpha": 0.5, "beta": 0.5, "ema_decay": 0.9},
        {"alpha": 0.3, "beta": 0.3, "ema_decay": 0.8},
        {"alpha": 0.3, "beta": 0.3, "ema_decay": 0.95},
        {"alpha": 0.5, "beta": 0.1, "ema_decay": 0.9},
        {"alpha": 0.1, "beta": 0.5, "ema_decay": 0.9},
    ]

    results = []
    for cfg in configs:
        logger.info(
            f"  Sweep: alpha={cfg['alpha']}, beta={cfg['beta']}, ema={cfg['ema_decay']}"
        )
        analysis = analyze_convergence(
            game,
            embedder,
            collection_name,
            query_states,
            max_cycles=10,
            **cfg,
        )
        results.append({**cfg, **analysis})

    return results


def main():
    parser = argparse.ArgumentParser(description="RIC-TRM Convergence Analysis")
    parser.add_argument(
        "--game",
        choices=list(GAMES.keys()),
        default="tictactoe",
    )
    parser.add_argument("--train-size", type=int, default=500)
    parser.add_argument("--num-queries", type=int, default=50)
    parser.add_argument("--sweep", action="store_true", help="Run parameter sweep")
    args = parser.parse_args()

    game_factory = GAMES[args.game]
    game = game_factory() if callable(game_factory) else game_factory
    collection_name = f"ric_trm_{game.name}_conv"

    logger.info(f"=== Convergence Analysis: {game.name} ===")

    # Generate and index states
    logger.info("Generating states...")
    all_states = game.generate_states(max_states=args.train_size + args.num_queries)

    rng = np.random.RandomState(42)
    indices = rng.permutation(len(all_states))
    all_states = [all_states[i] for i in indices]

    train_states = all_states[: args.train_size]
    query_states = all_states[args.train_size : args.train_size + args.num_queries]

    embedder = RICEmbedder()
    embedder.create_collection(collection_name, force_recreate=True)

    logger.info(f"Indexing {len(train_states)} training states...")
    embedder.index_states(game, train_states, collection_name)

    if args.sweep:
        logger.info("Running parameter sweep...")
        sweep_results = sweep_parameters(game, embedder, collection_name, query_states)

        print("\n" + "=" * 80)
        print("PARAMETER SWEEP RESULTS")
        print("=" * 80)
        print(
            f"{'Alpha':>6} {'Beta':>6} {'EMA':>6} {'MeanCyc':>8} "
            f"{'Halted%':>8} {'MeanScore':>10}"
        )
        print("-" * 80)

        for r in sweep_results:
            cyc = r["cycle_distribution"]
            scores = r["per_cycle"]["mean_top1_score"]
            last_score = scores[-1] if scores else 0
            print(
                f"{r['alpha']:>6.2f} {r['beta']:>6.2f} {r['ema_decay']:>6.2f} "
                f"{cyc['mean']:>8.1f} {r['halted_early_pct']:>7.0%} "
                f"{last_score:>10.4f}"
            )
    else:
        logger.info("Analyzing convergence (default params)...")
        analysis = analyze_convergence(
            game,
            embedder,
            collection_name,
            query_states,
            max_cycles=10,
        )

        print("\n" + "=" * 60)
        print(f"CONVERGENCE ANALYSIS: {game.name}")
        print(f"Queries: {analysis['num_queries']}")
        print("=" * 60)

        cyc = analysis["cycle_distribution"]
        print(f"\nCycles to stabilize:")
        print(f"  Mean: {cyc['mean']:.1f}")
        print(f"  Median: {cyc['median']:.0f}")
        print(f"  Std: {cyc['std']:.1f}")
        print(f"  Range: [{cyc['min']}, {cyc['max']}]")
        print(f"  Halted early: {analysis['halted_early_pct']:.0%}")

        per_cycle = analysis["per_cycle"]
        print(f"\nPer-cycle metrics:")
        print(f"  {'Cycle':>5} {'z_H drift':>10} {'z_L drift':>10} {'Top-1 score':>12}")
        print(f"  {'-' * 40}")
        for i in range(len(per_cycle["z_H_drift"])):
            print(
                f"  {i:>5} {per_cycle['z_H_drift'][i]:>10.4f} "
                f"{per_cycle['z_L_drift'][i]:>10.4f} "
                f"{per_cycle['mean_top1_score'][i]:>12.4f}"
            )

    return analysis if not args.sweep else sweep_results


if __name__ == "__main__":
    main()
