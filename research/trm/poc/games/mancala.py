"""Mancala (Kalah): 2x6 pits + 2 stores, depth-limited solver.

Standard Kalah rules:
- 6 pits per side, 4 stones each initially
- Sow counter-clockwise, skip opponent's store
- Landing in own store: extra turn
- Landing in empty own pit: capture opposite pit's stones
"""

from __future__ import annotations

from typing import List, Optional

from .base import Game, GameState

PITS_PER_SIDE = 6
INITIAL_STONES = 4
# Board layout (indices):
#   P2: [12] [11] [10] [9]  [8]  [7]
# Store2[13]                        Store1[6]
#   P1: [0]  [1]  [2]  [3]  [4]  [5]


class Mancala(Game):
    def __init__(self, search_depth: int = 12):
        self._search_depth = search_depth
        # Transposition table: (board, player) → (depth, value, move, flag)
        # flag: 'exact', 'lower', 'upper' for alpha-beta bounds
        self._tt: dict[tuple, tuple] = {}

    @property
    def name(self) -> str:
        return "mancala"

    def initial_state(self) -> GameState:
        # 14 cells: pits 0-5 (P1), store 6 (P1), pits 7-12 (P2), store 13 (P2)
        board = tuple([INITIAL_STONES] * 6 + [0] + [INITIAL_STONES] * 6 + [0])
        return GameState(board=board, current_player=1)

    def _player_pits(self, player: int) -> range:
        return range(0, 6) if player == 1 else range(7, 13)

    def _player_store(self, player: int) -> int:
        return 6 if player == 1 else 13

    def legal_moves(self, state: GameState) -> List[int]:
        """Return pit indices that have stones."""
        pits = self._player_pits(state.current_player)
        return [i for i in pits if state.board[i] > 0]

    def apply_move(self, state: GameState, move: int) -> GameState:
        board = list(state.board)
        player = state.current_player
        opp_store = self._player_store(3 - player)
        own_store = self._player_store(player)
        own_pits = self._player_pits(player)

        stones = board[move]
        board[move] = 0
        pos = move

        # Sow
        while stones > 0:
            pos = (pos + 1) % 14
            if pos == opp_store:
                continue
            board[pos] += 1
            stones -= 1

        # Extra turn if last stone lands in own store
        next_player = state.current_player
        extra_turn = pos == own_store

        # Capture: last stone in empty own pit
        if not extra_turn and pos in own_pits and board[pos] == 1:
            opposite = 12 - pos
            if board[opposite] > 0:
                board[own_store] += board[opposite] + 1
                board[opposite] = 0
                board[pos] = 0

        if not extra_turn:
            next_player = 3 - player

        # Check if one side is empty — collect remaining
        p1_empty = all(board[i] == 0 for i in range(6))
        p2_empty = all(board[i] == 0 for i in range(7, 13))

        if p1_empty:
            for i in range(7, 13):
                board[13] += board[i]
                board[i] = 0
        elif p2_empty:
            for i in range(6):
                board[6] += board[i]
                board[i] = 0

        return GameState(
            board=tuple(board),
            current_player=next_player,
            move_history=state.move_history + [move],
        )

    def is_terminal(self, state: GameState) -> bool:
        p1_empty = all(state.board[i] == 0 for i in range(6))
        p2_empty = all(state.board[i] == 0 for i in range(7, 13))
        return p1_empty or p2_empty

    def winner(self, state: GameState) -> Optional[int]:
        if not self.is_terminal(state):
            return None
        s1, s2 = state.board[6], state.board[13]
        if s1 > s2:
            return 1
        elif s2 > s1:
            return 2
        return None  # draw

    def optimal_move(self, state: GameState) -> Optional[int]:
        if self.is_terminal(state):
            return None
        moves = self.legal_moves(state)
        if not moves:
            return None
        # Iterative deepening: search progressively deeper, TT carries forward
        best_move = moves[0]
        for d in range(2, self._search_depth + 1, 2):
            _, m = self._negamax(state, d, -100000, 100000)
            if m is not None:
                best_move = m
        return best_move

    def _tt_key(self, state: GameState) -> tuple:
        return (state.board, state.current_player)

    def _negamax(
        self, state: GameState, depth: int, alpha: int, beta: int
    ) -> tuple[int, Optional[int]]:
        if self.is_terminal(state) or depth == 0:
            return self._evaluate(state), None

        moves = self.legal_moves(state)
        if not moves:
            return self._evaluate(state), None

        # Transposition table lookup
        tt_key = self._tt_key(state)
        if tt_key in self._tt:
            tt_depth, tt_val, tt_move, tt_flag = self._tt[tt_key]
            if tt_depth >= depth:
                if tt_flag == "exact":
                    return tt_val, tt_move
                elif tt_flag == "lower":
                    alpha = max(alpha, tt_val)
                elif tt_flag == "upper":
                    beta = min(beta, tt_val)
                if alpha >= beta:
                    return tt_val, tt_move

        # Move ordering: try TT best move first (huge speedup)
        if tt_key in self._tt:
            tt_best = self._tt[tt_key][2]
            if tt_best in moves:
                moves = [tt_best] + [m for m in moves if m != tt_best]

        orig_alpha = alpha
        best_val = -100000
        best_move = moves[0]

        for move in moves:
            next_state = self.apply_move(state, move)
            # If extra turn (same player), don't negate
            if next_state.current_player == state.current_player:
                val, _ = self._negamax(next_state, depth - 1, alpha, beta)
            else:
                val, _ = self._negamax(next_state, depth - 1, -beta, -alpha)
                val = -val

            if val > best_val:
                best_val = val
                best_move = move
            alpha = max(alpha, val)
            if alpha >= beta:
                break

        # Store in transposition table
        if best_val <= orig_alpha:
            flag = "upper"
        elif best_val >= beta:
            flag = "lower"
        else:
            flag = "exact"
        self._tt[tt_key] = (depth, best_val, best_move, flag)

        return best_val, best_move

    def _evaluate(self, state: GameState) -> int:
        """Score from current player's perspective."""
        own_store = self._player_store(state.current_player)
        opp_store = self._player_store(3 - state.current_player)
        own_pits = self._player_pits(state.current_player)
        opp_pits = self._player_pits(3 - state.current_player)

        score = state.board[own_store] - state.board[opp_store]
        score += sum(state.board[i] for i in own_pits) // 3
        score -= sum(state.board[i] for i in opp_pits) // 3
        return score

    # --- RIC Text Generation ---

    def component_text(self, state: GameState) -> str:
        b = state.board
        player = f"Player {state.current_player}"
        total_stones = sum(b)
        p1_side = sum(b[i] for i in range(6))
        p2_side = sum(b[i] for i in range(7, 13))

        p2_pits = " ".join(f"{b[12 - i]:2d}" for i in range(6))
        p1_pits = " ".join(f"{b[i]:2d}" for i in range(6))

        board_str = (
            f"P2: {p2_pits}\nS2={b[13]:2d}            S1={b[6]:2d}\nP1: {p1_pits}"
        )

        return (
            f"Mancala Board State\n"
            f"Current Player: {player}\n"
            f"Stores: P1={b[6]} P2={b[13]}\n"
            f"Pit stones: P1-side={p1_side} P2-side={p2_side}\n"
            f"Total stones: {total_stones}\n"
            f"Turn: {len(state.move_history) + 1}\n"
            f"Board:\n{board_str}"
        )

    def inputs_text(self, state: GameState) -> str:
        moves = self.legal_moves(state)
        player = state.current_player
        parts = [f"Legal pits for Player {player}: {moves}"]

        for m in moves:
            stones = state.board[m]
            next_s = self.apply_move(state, m)
            pit_idx = m if player == 1 else m - 7
            desc = f"  Pit {pit_idx} (idx={m}, stones={stones}):"

            # Check for extra turn
            if next_s.current_player == player:
                desc += " EXTRA TURN,"

            # Check for capture
            own_store = self._player_store(player)
            store_gain = next_s.board[own_store] - state.board[own_store]
            if store_gain > stones:
                desc += f" captures {store_gain - 1} stones,"
            elif store_gain > 0:
                desc += f" scores {store_gain},"

            # Distance to store
            store_dist = self._player_store(player) - m
            desc += f" sow_distance={stones} store_dist={store_dist}"
            parts.append(desc)

        return "\n".join(parts)

    def relationships_text(self, state: GameState) -> str:
        b = state.board
        parts = []

        # Store advantage
        diff = b[6] - b[13]
        if diff > 0:
            parts.append(f"Store advantage: P1 leads by {diff}")
        elif diff < 0:
            parts.append(f"Store advantage: P2 leads by {-diff}")
        else:
            parts.append("Stores tied")

        # Pit distribution per side
        for player, name in [(1, "P1"), (2, "P2")]:
            pits = self._player_pits(player)
            stones = [b[i] for i in pits]
            empty = stones.count(0)
            heavy = sum(1 for s in stones if s >= 8)
            parts.append(f"{name} pits: {stones} (empty={empty}, heavy={heavy})")

        # Capture opportunities
        for player in [1, 2]:
            pits = self._player_pits(player)
            captures = []
            for i in pits:
                if b[i] == 0:
                    opposite = 12 - i
                    if b[opposite] > 0:
                        captures.append((i, b[opposite]))
            if captures:
                parts.append(f"P{player} capture targets: {captures}")

        # Extra turn opportunities
        for player in [1, 2]:
            pits = self._player_pits(player)
            store = self._player_store(player)
            extra = []
            for i in pits:
                if b[i] > 0 and (i + b[i]) % 14 == store:
                    extra.append(i)
            if extra:
                parts.append(f"P{player} extra-turn pits: {extra}")

        return "\n".join(parts)

    def generate_states(
        self, max_states: int = 5000, include_terminal: bool = False
    ) -> list[tuple[GameState, int]]:
        """Generate states via random self-play."""
        import random as rng

        results = []
        seen = set()

        while len(results) < max_states:
            state = self.initial_state()
            game_states = []

            while not self.is_terminal(state):
                game_states.append(state)
                moves = self.legal_moves(state)
                if not moves:
                    break
                move = rng.choice(moves)
                state = self.apply_move(state, move)

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
