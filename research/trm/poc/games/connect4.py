"""Connect 4: 7x6 grid, solved (first player wins with center start).

Uses depth-limited negamax with alpha-beta pruning for move evaluation.
"""

from __future__ import annotations

import random
from typing import List, Optional

from .base import Game, GameState

ROWS = 6
COLS = 7
SYMBOLS = {0: ".", 1: "R", 2: "Y"}

# Precompute all possible 4-in-a-row positions
WIN_POSITIONS: list[list[tuple[int, int]]] = []
for r in range(ROWS):
    for c in range(COLS):
        # Horizontal
        if c + 3 < COLS:
            WIN_POSITIONS.append([(r, c + i) for i in range(4)])
        # Vertical
        if r + 3 < ROWS:
            WIN_POSITIONS.append([(r + i, c) for i in range(4)])
        # Diagonal down-right
        if r + 3 < ROWS and c + 3 < COLS:
            WIN_POSITIONS.append([(r + i, c + i) for i in range(4)])
        # Diagonal down-left
        if r + 3 < ROWS and c - 3 >= 0:
            WIN_POSITIONS.append([(r + i, c - i) for i in range(4)])


class Connect4(Game):
    def __init__(self, search_depth: int = 6):
        self._search_depth = search_depth

    @property
    def name(self) -> str:
        return "connect4"

    def initial_state(self) -> GameState:
        # Board: list of lists, board[row][col], row 0 = top
        board = tuple(tuple(0 for _ in range(COLS)) for _ in range(ROWS))
        return GameState(board=board, current_player=1)

    def legal_moves(self, state: GameState) -> List[int]:
        """Return columns that aren't full."""
        return [c for c in range(COLS) if state.board[0][c] == 0]

    def apply_move(self, state: GameState, move: int) -> GameState:
        board = [list(row) for row in state.board]
        # Drop piece to lowest empty row
        for r in range(ROWS - 1, -1, -1):
            if board[r][move] == 0:
                board[r][move] = state.current_player
                break
        return GameState(
            board=tuple(tuple(row) for row in board),
            current_player=3 - state.current_player,
            move_history=state.move_history + [move],
        )

    def is_terminal(self, state: GameState) -> bool:
        return self.winner(state) is not None or len(self.legal_moves(state)) == 0

    def winner(self, state: GameState) -> Optional[int]:
        return _check_winner(state.board)

    def optimal_move(self, state: GameState) -> Optional[int]:
        if self.is_terminal(state):
            return None
        _, move = _negamax_ab(
            state.board, state.current_player, self._search_depth, -100000, 100000
        )
        return move

    # --- RIC Text Generation ---

    def component_text(self, state: GameState) -> str:
        rows = []
        for r in range(ROWS):
            row_str = " ".join(SYMBOLS[state.board[r][c]] for c in range(COLS))
            rows.append(row_str)
        board_str = "\n".join(rows)

        r_count = sum(
            1 for r in range(ROWS) for c in range(COLS) if state.board[r][c] == 1
        )
        y_count = sum(
            1 for r in range(ROWS) for c in range(COLS) if state.board[r][c] == 2
        )
        player = "RED" if state.current_player == 1 else "YELLOW"

        return (
            f"Connect4 Board State\n"
            f"Current Player: {player}\n"
            f"Pieces: RED={r_count} YELLOW={y_count}\n"
            f"Turn: {r_count + y_count + 1}\n"
            f"Board (top to bottom):\n{board_str}"
        )

    def inputs_text(self, state: GameState) -> str:
        moves = self.legal_moves(state)
        player = "RED" if state.current_player == 1 else "YELLOW"
        parts = [f"Legal columns for {player}: {moves}"]

        for col in moves:
            next_s = self.apply_move(state, col)
            # Find the row where piece landed
            landing_row = _find_landing_row(state.board, col)
            desc = f"  Col {col} (lands row {landing_row}):"

            if self.winner(next_s) == state.current_player:
                desc += " WINS"
            else:
                threats = _count_threats(next_s.board, state.current_player)
                blocks = _count_threats(state.board, 3 - state.current_player)
                after_blocks = _count_threats(next_s.board, 3 - state.current_player)
                if after_blocks < blocks:
                    desc += f" blocks {blocks - after_blocks} threat(s),"
                if threats > 0:
                    desc += f" creates {threats} threat(s),"
                desc += f" center_dist={abs(col - 3)}"
            parts.append(desc)

        return "\n".join(parts)

    def relationships_text(self, state: GameState) -> str:
        b = state.board
        parts = []

        # Column heights
        heights = []
        for c in range(COLS):
            h = sum(1 for r in range(ROWS) if b[r][c] != 0)
            heights.append(h)
        parts.append(f"Column heights: {heights}")

        # Threats per player
        for player, name in [(1, "RED"), (2, "YELLOW")]:
            threats = _count_threats(b, player)
            lines_2 = _count_n_in_line(b, player, 2)
            lines_3 = _count_n_in_line(b, player, 3)
            parts.append(
                f"{name}: {threats} open threats, {lines_3} three-in-row, {lines_2} two-in-row"
            )

        # Vertical connectivity
        for c in range(COLS):
            streak = _vertical_streak(b, c)
            if streak[1] >= 2:
                name = "RED" if streak[0] == 1 else "YELLOW"
                parts.append(f"Col {c}: {name} vertical streak of {streak[1]}")

        # Center control
        center_r = sum(1 for r in range(ROWS) if b[r][3] == 1)
        center_y = sum(1 for r in range(ROWS) if b[r][3] == 2)
        parts.append(f"Center column: RED={center_r} YELLOW={center_y}")

        return "\n".join(parts)

    def _state_key(self, state: GameState) -> str:
        return str(state.board) + str(state.current_player)

    def generate_states(
        self, max_states: int = 5000, include_terminal: bool = False
    ) -> list[tuple[GameState, int]]:
        """Generate states via random self-play (BFS is too slow for Connect4)."""
        results = []
        seen = set()

        while len(results) < max_states:
            state = self.initial_state()
            # Play random game, collecting non-terminal states
            game_states = []
            while not self.is_terminal(state):
                game_states.append(state)
                moves = self.legal_moves(state)
                # Mix random and heuristic play
                if random.random() < 0.3:
                    move = self._quick_eval_move(state)
                else:
                    move = random.choice(moves)
                state = self.apply_move(state, move)

            # Now compute optimal moves for collected states
            for s in game_states:
                key = self._state_key(s)
                if key in seen:
                    continue
                seen.add(key)
                opt = self.optimal_move(s)
                if opt is not None:
                    results.append((s, opt))
                    if len(results) >= max_states:
                        break

        return results

    def _quick_eval_move(self, state: GameState) -> int:
        """Fast heuristic move (no full search)."""
        moves = self.legal_moves(state)
        # Check for immediate wins
        for m in moves:
            ns = self.apply_move(state, m)
            if self.winner(ns) == state.current_player:
                return m
        # Check for immediate blocks
        opp = 3 - state.current_player
        for m in moves:
            ns = self.apply_move(state, m)
            # Simulate opponent playing here
            board_if_opp = [list(row) for row in state.board]
            for r in range(ROWS - 1, -1, -1):
                if board_if_opp[r][m] == 0:
                    board_if_opp[r][m] = opp
                    break
            if _check_winner(tuple(tuple(row) for row in board_if_opp)) == opp:
                return m
        # Prefer center
        center_pref = sorted(moves, key=lambda m: abs(m - 3))
        return center_pref[0]


# --- Solver: Negamax with Alpha-Beta ---


def _negamax_ab(
    board: tuple,
    player: int,
    depth: int,
    alpha: int,
    beta: int,
) -> tuple[int, Optional[int]]:
    """Returns (score, best_move) from current player's perspective."""
    w = _check_winner(board)
    if w is not None:
        return (10000 if w == player else -10000), None

    legal = [c for c in range(COLS) if board[0][c] == 0]
    if not legal:
        return 0, None
    if depth == 0:
        return _evaluate(board, player), None

    # Move ordering: center first
    legal.sort(key=lambda c: abs(c - 3))

    best_val = -100000
    best_move = legal[0]

    for col in legal:
        new_board = _drop_piece(board, col, player)
        val, _ = _negamax_ab(new_board, 3 - player, depth - 1, -beta, -alpha)
        val = -val

        if val > best_val:
            best_val = val
            best_move = col
        alpha = max(alpha, val)
        if alpha >= beta:
            break

    return best_val, best_move


def _evaluate(board: tuple, player: int) -> int:
    """Heuristic evaluation from player's perspective."""
    score = 0
    opp = 3 - player

    for positions in WIN_POSITIONS:
        cells = [board[r][c] for r, c in positions]
        p_count = cells.count(player)
        o_count = cells.count(opp)

        if o_count == 0:
            if p_count == 3:
                score += 50
            elif p_count == 2:
                score += 5
            elif p_count == 1:
                score += 1
        elif p_count == 0:
            if o_count == 3:
                score -= 50
            elif o_count == 2:
                score -= 5
            elif o_count == 1:
                score -= 1

    # Center column bonus
    for r in range(ROWS):
        if board[r][3] == player:
            score += 3
        elif board[r][3] == opp:
            score -= 3

    return score


def _drop_piece(board: tuple, col: int, player: int) -> tuple:
    board_list = [list(row) for row in board]
    for r in range(ROWS - 1, -1, -1):
        if board_list[r][col] == 0:
            board_list[r][col] = player
            break
    return tuple(tuple(row) for row in board_list)


def _check_winner(board: tuple) -> Optional[int]:
    for positions in WIN_POSITIONS:
        cells = [board[r][c] for r, c in positions]
        if cells[0] != 0 and cells[0] == cells[1] == cells[2] == cells[3]:
            return cells[0]
    return None


def _find_landing_row(board: tuple, col: int) -> int:
    for r in range(ROWS - 1, -1, -1):
        if board[r][col] == 0:
            return r
    return -1


def _count_threats(board: tuple, player: int) -> int:
    """Count lines where player has 3 and 1 empty (open threats)."""
    count = 0
    opp = 3 - player
    for positions in WIN_POSITIONS:
        cells = [board[r][c] for r, c in positions]
        if cells.count(player) == 3 and cells.count(0) == 1:
            # Check if the empty cell is playable (piece would land there)
            empty_idx = cells.index(0)
            er, ec = positions[empty_idx]
            if er == ROWS - 1 or board[er + 1][ec] != 0:
                count += 1
    return count


def _count_n_in_line(board: tuple, player: int, n: int) -> int:
    """Count lines where player has exactly n pieces and rest empty."""
    count = 0
    for positions in WIN_POSITIONS:
        cells = [board[r][c] for r, c in positions]
        if cells.count(player) == n and cells.count(0) == 4 - n:
            count += 1
    return count


def _vertical_streak(board: tuple, col: int) -> tuple[int, int]:
    """Return (player, streak_length) for the top streak in a column."""
    for r in range(ROWS):
        if board[r][col] != 0:
            player = board[r][col]
            streak = 0
            while r + streak < ROWS and board[r + streak][col] == player:
                streak += 1
            return player, streak
    return 0, 0
