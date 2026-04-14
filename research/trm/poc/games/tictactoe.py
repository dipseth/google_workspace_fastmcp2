"""Tic-Tac-Toe: trivially solved, perfect for baseline / sanity checks."""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from .base import Game, GameState

# Board is a tuple of 9 ints: 0=empty, 1=X, 2=O
# Positions:
#  0 | 1 | 2
#  ---------
#  3 | 4 | 5
#  ---------
#  6 | 7 | 8

WIN_LINES = [
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),  # rows
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),  # cols
    (0, 4, 8),
    (2, 4, 6),  # diags
]

SYMBOLS = {0: ".", 1: "X", 2: "O"}


class TicTacToe(Game):
    @property
    def name(self) -> str:
        return "tictactoe"

    def initial_state(self) -> GameState:
        return GameState(board=tuple([0] * 9), current_player=1)

    def legal_moves(self, state: GameState) -> List[int]:
        return [i for i in range(9) if state.board[i] == 0]

    def apply_move(self, state: GameState, move: int) -> GameState:
        board = list(state.board)
        board[move] = state.current_player
        return GameState(
            board=tuple(board),
            current_player=3 - state.current_player,
            move_history=state.move_history + [move],
        )

    def is_terminal(self, state: GameState) -> bool:
        return self.winner(state) is not None or all(c != 0 for c in state.board)

    def winner(self, state: GameState) -> Optional[int]:
        for a, b, c in WIN_LINES:
            if state.board[a] == state.board[b] == state.board[c] != 0:
                return state.board[a]
        return None

    def optimal_move(self, state: GameState) -> Optional[int]:
        if self.is_terminal(state):
            return None
        _, move = self._negamax(state.board, state.current_player)
        return move

    def _negamax(self, board: tuple, player: int) -> tuple[int, Optional[int]]:
        return _negamax_cached(board, player)

    # --- RIC Text Generation ---

    def component_text(self, state: GameState) -> str:
        b = state.board
        rows = []
        for r in range(3):
            row = " ".join(SYMBOLS[b[r * 3 + c]] for c in range(3))
            rows.append(row)
        board_str = "\n".join(rows)

        x_count = sum(1 for c in b if c == 1)
        o_count = sum(1 for c in b if c == 2)
        empty = sum(1 for c in b if c == 0)
        player = "X" if state.current_player == 1 else "O"

        return (
            f"TicTacToe Board State\n"
            f"Current Player: {player}\n"
            f"Pieces: X={x_count} O={o_count} Empty={empty}\n"
            f"Turn: {x_count + o_count + 1}\n"
            f"Board:\n{board_str}"
        )

    def inputs_text(self, state: GameState) -> str:
        moves = self.legal_moves(state)
        player = "X" if state.current_player == 1 else "O"
        parts = [f"Legal moves for {player}: {moves}"]

        for m in moves:
            next_s = self.apply_move(state, m)
            row, col = m // 3, m % 3
            pos_name = _position_name(m)
            if self.winner(next_s) == state.current_player:
                parts.append(f"  Move {m} ({pos_name}): WINS the game")
            elif self.is_terminal(next_s):
                parts.append(f"  Move {m} ({pos_name}): results in draw")
            else:
                # Check if move blocks opponent win
                opp = 3 - state.current_player
                blocks = _blocks_win(state.board, m, opp)
                threat = _creates_threat(next_s.board, state.current_player)
                desc = f"  Move {m} ({pos_name}):"
                if blocks:
                    desc += " blocks opponent win,"
                if threat:
                    desc += f" creates {threat}-in-a-row threat,"
                desc += f" row={row} col={col}"
                parts.append(desc)

        return "\n".join(parts)

    def relationships_text(self, state: GameState) -> str:
        b = state.board
        parts = []

        # Describe line occupancy
        for line in WIN_LINES:
            cells = [b[i] for i in line]
            x_in = cells.count(1)
            o_in = cells.count(2)
            empty_in = cells.count(0)
            line_name = _line_name(line)

            if x_in > 0 and o_in > 0:
                parts.append(f"{line_name}: contested (X={x_in}, O={o_in})")
            elif x_in > 0:
                parts.append(
                    f"{line_name}: X controls ({x_in}/3, {empty_in} open)"
                )
            elif o_in > 0:
                parts.append(
                    f"{line_name}: O controls ({o_in}/3, {empty_in} open)"
                )
            else:
                parts.append(f"{line_name}: empty")

        # Center control
        center = b[4]
        if center != 0:
            parts.append(f"Center: controlled by {SYMBOLS[center]}")
        else:
            parts.append("Center: open")

        # Corner control
        corners = [b[i] for i in [0, 2, 6, 8]]
        x_corners = corners.count(1)
        o_corners = corners.count(2)
        parts.append(f"Corners: X={x_corners} O={o_corners}")

        return "\n".join(parts)

    def _state_key(self, state: GameState) -> str:
        return str(state.board) + str(state.current_player)


# --- Cached negamax solver ---


@lru_cache(maxsize=None)
def _negamax_cached(board: tuple, player: int) -> tuple[int, Optional[int]]:
    """Returns (value_for_player, best_move). Value: +1=win, 0=draw, -1=loss."""
    # Check terminal
    for a, b, c in WIN_LINES:
        if board[a] == board[b] == board[c] != 0:
            # Someone won. If it's the current player, +1; else -1
            return (1 if board[a] == player else -1), None
    if all(cell != 0 for cell in board):
        return 0, None

    best_val = -2
    best_move = None
    for i in range(9):
        if board[i] != 0:
            continue
        new_board = list(board)
        new_board[i] = player
        child_val, _ = _negamax_cached(tuple(new_board), 3 - player)
        val = -child_val
        if val > best_val:
            best_val = val
            best_move = i

    return best_val, best_move


def _position_name(pos: int) -> str:
    names = [
        "top-left",
        "top-center",
        "top-right",
        "mid-left",
        "center",
        "mid-right",
        "bot-left",
        "bot-center",
        "bot-right",
    ]
    return names[pos]


def _line_name(line: tuple[int, int, int]) -> str:
    mapping = {
        (0, 1, 2): "Top row",
        (3, 4, 5): "Mid row",
        (6, 7, 8): "Bot row",
        (0, 3, 6): "Left col",
        (1, 4, 7): "Center col",
        (2, 5, 8): "Right col",
        (0, 4, 8): "Main diag",
        (2, 4, 6): "Anti diag",
    }
    return mapping.get(line, str(line))


def _blocks_win(board: tuple, move: int, opponent: int) -> bool:
    """Check if placing at `move` blocks opponent from winning on next turn."""
    for line in WIN_LINES:
        if move not in line:
            continue
        cells = [board[i] for i in line]
        if cells.count(opponent) == 2 and cells.count(0) == 1:
            return True
    return False


def _creates_threat(board: tuple, player: int) -> int:
    """Return max pieces-in-a-row for player across all open lines."""
    best = 0
    for line in WIN_LINES:
        cells = [board[i] for i in line]
        if cells.count(3 - player) == 0:
            best = max(best, cells.count(player))
    return best
