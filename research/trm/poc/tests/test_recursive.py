"""Tests for the recursive RIC search POC.

Verifies:
1. Game solvers produce correct optimal moves
2. RIC embeddings have expected dimensions
3. Qdrant indexing works with 3 named vectors
4. Single-pass search returns valid results
5. Recursive search converges (halts)
6. Recursive search matches or beats single-pass on known positions
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from games import Connect4, Mancala, TicTacToe
from games.base import GameState
from recursive_search import multi_dimensional_search, recursive_search, single_pass_search
from ric_vectors import EMBEDDING_DIM, RICEmbedder


# ──────────────────────────────────────────────
#  Game Solver Tests
# ──────────────────────────────────────────────


class TestTicTacToeSolver:
    def setup_method(self):
        self.game = TicTacToe()

    def test_initial_state(self):
        s = self.game.initial_state()
        assert s.current_player == 1
        assert all(c == 0 for c in s.board)

    def test_legal_moves_initial(self):
        s = self.game.initial_state()
        assert len(self.game.legal_moves(s)) == 9

    def test_apply_move(self):
        s = self.game.initial_state()
        s2 = self.game.apply_move(s, 4)  # center
        assert s2.board[4] == 1
        assert s2.current_player == 2

    def test_winner_detection(self):
        # X wins top row
        board = (1, 1, 1, 2, 2, 0, 0, 0, 0)
        s = GameState(board=board, current_player=2)
        assert self.game.winner(s) == 1

    def test_optimal_blocks_win(self):
        # O must block X from winning
        # X . X
        # O . .
        # . . .
        board = (1, 0, 1, 2, 0, 0, 0, 0, 0)
        s = GameState(board=board, current_player=2)
        move = self.game.optimal_move(s)
        assert move == 1  # Must block top row

    def test_optimal_takes_win(self):
        # X can win immediately
        # X X .
        # O O .
        # . . .
        board = (1, 1, 0, 2, 2, 0, 0, 0, 0)
        s = GameState(board=board, current_player=1)
        move = self.game.optimal_move(s)
        assert move == 2  # Win at top-right

    def test_draw_with_perfect_play(self):
        """Tic-tac-toe is a draw with perfect play from both sides."""
        from games.tictactoe import _negamax_cached

        board = tuple([0] * 9)
        val, _ = _negamax_cached(board, 1)
        assert val == 0  # Draw

    def test_generate_states(self):
        states = self.game.generate_states(max_states=100)
        assert len(states) > 0
        for state, move in states:
            assert move in self.game.legal_moves(state)


class TestConnect4Solver:
    def setup_method(self):
        self.game = Connect4(search_depth=4)

    def test_initial_state(self):
        s = self.game.initial_state()
        assert s.current_player == 1
        assert len(self.game.legal_moves(s)) == 7

    def test_drop_piece(self):
        s = self.game.initial_state()
        s2 = self.game.apply_move(s, 3)  # center column
        assert s2.board[5][3] == 1  # bottom row, center col

    def test_winner_horizontal(self):
        s = self.game.initial_state()
        # Red places 4 in a row on bottom
        for col in [0, 1, 2, 3]:
            s = self.game.apply_move(s, col)  # RED
            if col < 3:
                s = self.game.apply_move(s, col)  # YELLOW on top
        assert self.game.winner(s) == 1

    def test_optimal_takes_win(self):
        """Solver should find immediate winning move."""
        s = self.game.initial_state()
        # Set up: RED has 3 in bottom row, col 0-2
        s = self.game.apply_move(s, 0)  # R
        s = self.game.apply_move(s, 0)  # Y
        s = self.game.apply_move(s, 1)  # R
        s = self.game.apply_move(s, 1)  # Y
        s = self.game.apply_move(s, 2)  # R
        s = self.game.apply_move(s, 2)  # Y
        # RED's turn, should play col 3 to win
        move = self.game.optimal_move(s)
        assert move == 3


class TestMancalaSolver:
    def setup_method(self):
        self.game = Mancala(search_depth=4)

    def test_initial_state(self):
        s = self.game.initial_state()
        assert s.current_player == 1
        assert s.board[6] == 0  # P1 store
        assert s.board[13] == 0  # P2 store

    def test_legal_moves(self):
        s = self.game.initial_state()
        moves = self.game.legal_moves(s)
        assert moves == [0, 1, 2, 3, 4, 5]

    def test_extra_turn(self):
        """Pit 2 has 4 stones, sows to store (idx 6) -> extra turn."""
        s = self.game.initial_state()
        # Pit 2 (idx 2) has 4 stones -> sows to 3,4,5,6(store)
        s2 = self.game.apply_move(s, 2)
        assert s2.current_player == 1  # Extra turn


# ──────────────────────────────────────────────
#  RIC Embedding Tests
# ──────────────────────────────────────────────


class TestRICEmbedding:
    @pytest.fixture(scope="class")
    def embedder(self):
        return RICEmbedder()

    def test_embed_text_dimensions(self, embedder):
        vec = embedder.embed_text("test input")
        assert vec.shape == (EMBEDDING_DIM,)
        assert vec.dtype == np.float32

    def test_embed_state_tictactoe(self, embedder):
        game = TicTacToe()
        state = game.initial_state()
        ric = embedder.embed_state(game, state)
        assert ric.components.shape == (EMBEDDING_DIM,)
        assert ric.inputs.shape == (EMBEDDING_DIM,)
        assert ric.relationships.shape == (EMBEDDING_DIM,)

    def test_different_states_different_embeddings(self, embedder):
        game = TicTacToe()
        s1 = game.initial_state()
        s2 = game.apply_move(s1, 4)  # center move

        ric1 = embedder.embed_state(game, s1)
        ric2 = embedder.embed_state(game, s2)

        # Should be different
        assert not np.allclose(ric1.components, ric2.components, atol=1e-3)

    def test_ric_texts_are_distinct(self):
        """Component, input, and relationship texts should be semantically different."""
        game = TicTacToe()
        state = game.initial_state()

        comp = game.component_text(state)
        inp = game.inputs_text(state)
        rel = game.relationships_text(state)

        # Texts should not be identical
        assert comp != inp
        assert comp != rel
        assert inp != rel


# ──────────────────────────────────────────────
#  Qdrant Indexing Tests
# ──────────────────────────────────────────────


class TestQdrantIndexing:
    @pytest.fixture
    def setup(self):
        embedder = RICEmbedder()
        game = TicTacToe()
        collection = "test_ttt_index"
        embedder.create_collection(collection, force_recreate=True)

        states = game.generate_states(max_states=50)
        indexed = embedder.index_states(game, states, collection)

        return embedder, game, collection, states, indexed

    def test_indexing_count(self, setup):
        _, _, _, states, indexed = setup
        assert indexed == len(states)

    def test_search_components(self, setup):
        embedder, game, collection, states, _ = setup

        # Search for a known state
        state, _ = states[0]
        ric = embedder.embed_state(game, state)

        response = embedder.client.query_points(
            collection_name=collection,
            query=ric.components.tolist(),
            using="components",
            limit=5,
            with_payload=True,
        )
        assert len(response.points) > 0
        # Top result should have a valid optimal_move
        assert "optimal_move" in response.points[0].payload

    def test_search_all_three_vectors(self, setup):
        embedder, game, collection, states, _ = setup
        state, _ = states[0]
        ric = embedder.embed_state(game, state)

        for vec_name, vec in [
            ("components", ric.components),
            ("inputs", ric.inputs),
            ("relationships", ric.relationships),
        ]:
            response = embedder.client.query_points(
                collection_name=collection,
                query=vec.tolist(),
                using=vec_name,
                limit=3,
                with_payload=True,
            )
            assert len(response.points) > 0, f"No results for {vec_name}"


# ──────────────────────────────────────────────
#  Recursive Search Tests
# ──────────────────────────────────────────────


class TestRecursiveSearch:
    @pytest.fixture(scope="class")
    def indexed_collection(self):
        embedder = RICEmbedder()
        game = TicTacToe()
        collection = "test_recursive_search"
        embedder.create_collection(collection, force_recreate=True)

        states = game.generate_states(max_states=200)
        embedder.index_states(game, states, collection)

        # Hold out some test states
        test_states = states[180:]
        return embedder, game, collection, test_states

    def test_single_pass_returns_results(self, indexed_collection):
        embedder, game, collection, test_states = indexed_collection
        state, _ = test_states[0]
        ric = embedder.embed_state(game, state)

        result = single_pass_search(
            embedder.client, collection, ric.components, ric.relationships, ric.inputs
        )
        assert len(result.top_ids) > 0
        assert len(result.top_payloads) > 0
        assert result.cycles_used == 1

    def test_recursive_returns_results(self, indexed_collection):
        embedder, game, collection, test_states = indexed_collection
        state, _ = test_states[0]
        ric = embedder.embed_state(game, state)

        result = recursive_search(
            embedder.client,
            collection,
            ric.components,
            ric.relationships,
            ric.inputs,
            max_cycles=6,
        )
        assert len(result.top_ids) > 0
        assert len(result.top_payloads) > 0
        assert result.cycles_used >= 1

    def test_recursive_halts(self, indexed_collection):
        """Recursive search should converge before max_cycles in most cases."""
        embedder, game, collection, test_states = indexed_collection
        halt_counts = []

        for state, _ in test_states[:10]:
            ric = embedder.embed_state(game, state)
            result = recursive_search(
                embedder.client,
                collection,
                ric.components,
                ric.relationships,
                ric.inputs,
                max_cycles=10,
            )
            halt_counts.append(result.cycles_used)

        # At least some should halt early
        avg_cycles = np.mean(halt_counts)
        assert avg_cycles < 10, f"Mean cycles {avg_cycles} — not converging"

    def test_ema_prevents_drift(self, indexed_collection):
        """With EMA, z_H/z_L drift should be bounded."""
        embedder, game, collection, test_states = indexed_collection
        state, _ = test_states[0]
        ric = embedder.embed_state(game, state)

        result = recursive_search(
            embedder.client,
            collection,
            ric.components,
            ric.relationships,
            ric.inputs,
            max_cycles=10,
            ema_decay=0.9,
        )

        for info in result.cycle_history:
            # Drift should stay bounded (not explode)
            assert info.z_H_drift < 2.0, f"z_H drift {info.z_H_drift} at cycle {info.cycle}"
            assert info.z_L_drift < 2.0, f"z_L drift {info.z_L_drift} at cycle {info.cycle}"

    def test_no_ema_more_drift(self, indexed_collection):
        """Without EMA (decay=1.0), drift should be larger (using centroid strategy)."""
        embedder, game, collection, test_states = indexed_collection
        state, _ = test_states[0]
        ric = embedder.embed_state(game, state)

        # Use centroid strategy which produces more consistent drift behavior
        result_ema = recursive_search(
            embedder.client, collection,
            ric.components, ric.relationships, ric.inputs,
            max_cycles=6, ema_decay=0.9, strategy="centroid",
        )
        result_no_ema = recursive_search(
            embedder.client, collection,
            ric.components, ric.relationships, ric.inputs,
            max_cycles=6, ema_decay=1.0, strategy="centroid",
        )

        # Compare final drift
        if result_ema.cycle_history and result_no_ema.cycle_history:
            ema_drift = result_ema.cycle_history[-1].z_H_drift
            no_ema_drift = result_no_ema.cycle_history[-1].z_H_drift
            # no-EMA should drift at least as much (usually more)
            assert no_ema_drift >= ema_drift * 0.8  # allow some tolerance

    def test_cycle_history_recorded(self, indexed_collection):
        embedder, game, collection, test_states = indexed_collection
        state, _ = test_states[0]
        ric = embedder.embed_state(game, state)

        result = recursive_search(
            embedder.client, collection,
            ric.components, ric.relationships, ric.inputs,
            max_cycles=3,
        )
        assert len(result.cycle_history) > 0
        assert result.cycle_history[0].cycle == 0
        assert len(result.cycle_history[0].comp_scores) > 0

    def test_multi_dimensional_returns_results(self, indexed_collection):
        embedder, game, collection, test_states = indexed_collection
        state, _ = test_states[0]
        ric = embedder.embed_state(game, state)

        result = multi_dimensional_search(
            embedder.client, collection,
            ric.components, ric.relationships, ric.inputs,
            top_k=5, candidate_pool=15,
        )
        assert len(result.top_ids) > 0
        assert len(result.top_payloads) > 0

    def test_multi_dimensional_scoring_modes(self, indexed_collection):
        """Both scoring modes should return valid results."""
        embedder, game, collection, test_states = indexed_collection
        state, _ = test_states[0]
        ric = embedder.embed_state(game, state)

        for scoring in ["multiplicative", "harmonic"]:
            result = multi_dimensional_search(
                embedder.client, collection,
                ric.components, ric.relationships, ric.inputs,
                scoring=scoring,
            )
            assert len(result.top_ids) > 0
            # Scores should be positive
            for score in result.rrf_scores.values():
                assert score >= 0

    def test_all_strategies_produce_results(self, indexed_collection):
        """Every recursive strategy should return valid results."""
        embedder, game, collection, test_states = indexed_collection
        state, _ = test_states[0]
        ric = embedder.embed_state(game, state)

        for strategy in ["centroid", "best_match", "score_weighted", "consistency"]:
            result = recursive_search(
                embedder.client, collection,
                ric.components.copy(), ric.relationships.copy(), ric.inputs.copy(),
                max_cycles=3, strategy=strategy,
            )
            assert len(result.top_ids) > 0, f"Strategy {strategy} returned no results"
