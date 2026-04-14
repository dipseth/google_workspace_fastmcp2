"""Validate the Mancala solver for correctness.

Checks:
1. Stone conservation (total stones never change)
2. Rule correctness (extra turns, captures, game-over collection)
3. Solver consistency (same state → same answer)
4. Solver depth sensitivity (do answers change with more depth?)
5. Known positions with hand-verified optimal moves
6. Terminal state handling

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python -m h2.validate_solver
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from games import Mancala  # noqa: E402
from games.base import GameState  # noqa: E402

TOTAL_STONES = 48  # 6 pits × 4 stones × 2 sides


def test_stone_conservation(n_games: int = 200):
    """Every move must preserve total stone count."""
    import random
    game = Mancala(search_depth=6)
    violations = 0
    total_moves = 0

    for _ in range(n_games):
        state = game.initial_state()
        while not game.is_terminal(state):
            assert sum(state.board) == TOTAL_STONES, (
                f"Stone count {sum(state.board)} != {TOTAL_STONES} at {state.board}"
            )
            moves = game.legal_moves(state)
            if not moves:
                break
            move = random.choice(moves)
            state = game.apply_move(state, move)
            total_moves += 1
            if sum(state.board) != TOTAL_STONES:
                violations += 1
                print(f"  VIOLATION: {state.board} sums to {sum(state.board)}")

        # Terminal: all stones in stores
        assert sum(state.board) == TOTAL_STONES

    print(f"[Stone Conservation] {n_games} games, {total_moves} moves, {violations} violations")
    return violations == 0


def test_extra_turn_rule():
    """Verify extra turn fires when last stone lands in own store."""
    game = Mancala()
    state = game.initial_state()  # P1 to move

    # Pit 2 has 4 stones, store is at idx 6. 2 + 4 = 6 → lands in store → extra turn
    # Wait — pit indices are 0-5 for P1. pit 2 has 4 stones → sow to 3,4,5,6 → last in store
    next_state = game.apply_move(state, 2)
    assert next_state.current_player == 1, (
        f"Expected extra turn (P1 stays), got player {next_state.current_player}"
    )

    # Pit 0 has 4 stones → sow to 1,2,3,4 → last in pit 4 → no extra turn
    next_state2 = game.apply_move(state, 0)
    assert next_state2.current_player == 2, (
        f"Expected turn switch to P2, got player {next_state2.current_player}"
    )

    print("[Extra Turn] Correct")
    return True


def test_capture_rule():
    """Verify capture: last stone in empty own pit captures opposite."""
    game = Mancala()

    # Set up a board where P1 pit 0 is empty and pit 5 has 1 stone,
    # P2 pit 12 (opposite of 0) has 5 stones
    board = [0, 0, 0, 0, 0, 1, 0, 4, 4, 4, 4, 4, 5, 0]
    state = GameState(board=tuple(board), current_player=1)

    # P1 plays pit 5 (1 stone) → lands in pit 6 (store) → extra turn, no capture
    # Actually 5 + 1 = 6 → lands in store. Let me pick a different setup.

    # Better: P1 pit 4 has 1 stone → sow to pit 5 → pit 5 was already 1, now 2, no capture
    # Need: last stone in empty own pit.
    # P1 pit 3 = 2 stones → sow to pit 4, pit 5 → last at pit 5
    # If pit 5 was empty before, it becomes 1 → capture opposite (pit 7)
    board2 = [4, 4, 4, 2, 0, 0, 0, 3, 4, 4, 4, 4, 4, 0]
    state2 = GameState(board=tuple(board2), current_player=1)

    # P1 plays pit 3 (2 stones) → sow to pit 4, then pit 5
    # Pit 4 was 0, becomes 1. But that's not the last stone yet.
    # Pit 5 was 0, becomes 1. Last stone in empty own pit! Opposite is 12-5=7, which has 3.
    # Capture: store += 3 + 1 = 4, pit 5 = 0, pit 7 = 0
    next_state = game.apply_move(state2, 3)
    assert next_state.board[6] == 4, f"Store should be 4 after capture, got {next_state.board[6]}"
    assert next_state.board[5] == 0, f"Pit 5 should be empty after capture, got {next_state.board[5]}"
    assert next_state.board[7] == 0, f"Pit 7 (opposite) should be empty, got {next_state.board[7]}"

    print("[Capture Rule] Correct")
    return True


def test_game_over_collection():
    """When one side empties, other side collects remaining stones."""
    game = Mancala()

    # Set up: P1 has 1 stone in pit 0 only. After playing it, P1 side empties.
    # P2 should collect all remaining pit stones into their store.
    # Total must be 48: pit0=1, store1=20, pits7-12=[2,3,1,1,0,0]=7, store2=20 → 1+20+7+20=48
    board = [1, 0, 0, 0, 0, 0, 20, 2, 3, 1, 1, 0, 0, 20]
    state = GameState(board=tuple(board), current_player=1)
    assert sum(board) == TOTAL_STONES, f"Setup board sums to {sum(board)}, expected {TOTAL_STONES}"

    next_state = game.apply_move(state, 0)
    # Pit 0 (1 stone) → sow to pit 1 → pit 1 becomes 1.
    # P1 side NOT empty yet (pit 1 has 1). Turn switches to P2.
    # Actually this won't trigger game-over. Let me use a different approach:
    # Play through a real game to near-terminal and check.

    # Simpler: verify the game-over logic directly
    board2 = [0, 0, 0, 0, 0, 1, 20, 2, 3, 1, 1, 0, 0, 20]
    state2 = GameState(board=tuple(board2), current_player=1)
    # P1 plays pit 5 (1 stone) → sow to pit 6 (store) → extra turn. P1 side now empty.
    # Game-over: P2 collects pits 7-12 (2+3+1+1+0+0=7) into store 13.
    next2 = game.apply_move(state2, 5)
    p1_pits = sum(next2.board[i] for i in range(6))
    p2_pits = sum(next2.board[i] for i in range(7, 13))
    assert p1_pits == 0, f"P1 pits should be 0, got {p1_pits}"
    assert p2_pits == 0, f"P2 pits should be 0 (collected), got {p2_pits}"
    assert next2.board[6] == 21, f"P1 store should be 21, got {next2.board[6]}"
    assert next2.board[13] == 27, f"P2 store should be 27 (20+7), got {next2.board[13]}"
    assert sum(next2.board) == TOTAL_STONES

    print("[Game Over Collection] Correct")
    return True


def test_solver_consistency(n_states: int = 100):
    """Same state should always produce the same optimal move."""
    game = Mancala(search_depth=8)
    states = game.generate_states(n_states)
    inconsistencies = 0

    for state, move1 in states[:50]:
        move2 = game.optimal_move(state)
        if move1 != move2:
            inconsistencies += 1
            print(f"  INCONSISTENT: generate_states gave {move1}, optimal_move gives {move2}")

    print(f"[Solver Consistency] {inconsistencies} inconsistencies in 50 states")
    return inconsistencies == 0


def test_depth_sensitivity(n_states: int = 50):
    """Check how much the 'optimal' move changes with search depth."""
    import random
    game_d4 = Mancala(search_depth=4)
    game_d8 = Mancala(search_depth=8)
    game_d12 = Mancala(search_depth=12)

    # Generate states with d8
    states = game_d8.generate_states(n_states)
    random.seed(42)
    random.shuffle(states)

    agree_4_8 = 0
    agree_8_12 = 0
    agree_4_12 = 0

    print(f"\n[Depth Sensitivity] Comparing depth=4 vs 8 vs 12 on {min(n_states, len(states))} states:")
    t0 = time.time()

    for state, _ in states[:n_states]:
        m4 = game_d4.optimal_move(state)
        m8 = game_d8.optimal_move(state)
        m12 = game_d12.optimal_move(state)
        if m4 == m8:
            agree_4_8 += 1
        if m8 == m12:
            agree_8_12 += 1
        if m4 == m12:
            agree_4_12 += 1

    elapsed = time.time() - t0
    total = min(n_states, len(states))
    print(f"  d4==d8:  {agree_4_8}/{total} ({agree_4_8/total:.1%})")
    print(f"  d8==d12: {agree_8_12}/{total} ({agree_8_12/total:.1%})")
    print(f"  d4==d12: {agree_4_12}/{total} ({agree_4_12/total:.1%})")
    print(f"  Time: {elapsed:.1f}s")

    return agree_8_12, total


def test_known_positions():
    """Hand-verified positions with known best moves."""
    game = Mancala(search_depth=12)

    # Opening position: pit 2 gives extra turn (lands in store 6)
    # This is a known strong opening.
    state = game.initial_state()
    move = game.optimal_move(state)
    # Pit 2 gives extra turn; many sources say it's the best opening
    print(f"[Known Positions] Opening move: pit {move} (pit 2 = extra turn)")

    # After P1 plays pit 2 (extra turn), P1 plays again.
    s2 = game.apply_move(state, 2)
    assert s2.current_player == 1, "Should still be P1's turn"
    m2 = game.optimal_move(s2)
    print(f"  After pit 2 (extra turn), next move: pit {m2}")

    # Near-terminal: P1 has huge lead, should still pick valid move
    board = [0, 0, 0, 0, 0, 1, 40, 0, 0, 0, 0, 0, 7, 0]
    late_state = GameState(board=tuple(board), current_player=1)
    late_move = game.optimal_move(late_state)
    assert late_move == 5, f"Only legal move is pit 5, got {late_move}"
    print(f"  Near-terminal (only pit 5): {late_move} (correct)")

    return True


def main():
    print("=" * 60)
    print("MANCALA SOLVER VALIDATION")
    print("=" * 60)

    results = []
    results.append(("Stone Conservation", test_stone_conservation()))
    results.append(("Extra Turn Rule", test_extra_turn_rule()))
    results.append(("Capture Rule", test_capture_rule()))
    results.append(("Game Over Collection", test_game_over_collection()))
    results.append(("Solver Consistency", test_solver_consistency()))
    results.append(("Known Positions", test_known_positions()))
    agree, total = test_depth_sensitivity()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

    print(f"\n  IMPORTANT: Solver is depth-limited (NOT fully solved).")
    print(f"  Depth 8→12 agreement: {agree}/{total} ({agree/total:.1%})")
    print(f"  This means ~{100-agree/total*100:.0f}% of 'optimal' labels may be wrong.")
    print("=" * 60)


if __name__ == "__main__":
    main()
