"""Abstract base class for solved games with RIC text generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class GameState:
    """A game state with board representation and metadata."""

    board: Any
    current_player: int  # 1 or 2
    move_history: list = field(default_factory=list)

    def copy(self) -> GameState:
        import copy

        return GameState(
            board=copy.deepcopy(self.board),
            current_player=self.current_player,
            move_history=list(self.move_history),
        )


class Game(ABC):
    """Abstract base for solved games with RIC text generation."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Game name identifier."""
        ...

    @abstractmethod
    def initial_state(self) -> GameState:
        """Return the starting state."""
        ...

    @abstractmethod
    def legal_moves(self, state: GameState) -> List[int]:
        """Return list of legal move identifiers."""
        ...

    @abstractmethod
    def apply_move(self, state: GameState, move: int) -> GameState:
        """Return new state after applying move (does not mutate input)."""
        ...

    @abstractmethod
    def is_terminal(self, state: GameState) -> bool:
        """True if the game is over."""
        ...

    @abstractmethod
    def winner(self, state: GameState) -> Optional[int]:
        """Winning player (1 or 2), or None for draw / ongoing."""
        ...

    @abstractmethod
    def optimal_move(self, state: GameState) -> Optional[int]:
        """Return the optimal move for current player, or None if terminal."""
        ...

    # --- RIC Text Generation ---

    @abstractmethod
    def component_text(self, state: GameState) -> str:
        """RIC Components: 'What IS this state?' — identity, board snapshot."""
        ...

    @abstractmethod
    def inputs_text(self, state: GameState) -> str:
        """RIC Inputs: 'What moves are available?' — legal actions + consequences."""
        ...

    @abstractmethod
    def relationships_text(self, state: GameState) -> str:
        """RIC Relationships: 'How do pieces connect?' — threats, patterns, structure."""
        ...

    # --- Utility ---

    def generate_states(
        self, max_states: int = 5000, include_terminal: bool = False
    ) -> List[tuple[GameState, int]]:
        """Generate (state, optimal_move) pairs via BFS/DFS.

        Returns non-terminal states by default, each paired with its optimal move.
        """
        from collections import deque

        queue: deque[GameState] = deque([self.initial_state()])
        seen: set[str] = set()
        results: list[tuple[GameState, int]] = []

        while queue and len(results) < max_states:
            state = queue.popleft()
            key = self._state_key(state)
            if key in seen:
                continue
            seen.add(key)

            if self.is_terminal(state):
                if include_terminal:
                    results.append((state, -1))
                continue

            move = self.optimal_move(state)
            if move is not None:
                results.append((state, move))

            for m in self.legal_moves(state):
                next_state = self.apply_move(state, m)
                next_key = self._state_key(next_state)
                if next_key not in seen:
                    queue.append(next_state)

        return results

    def _state_key(self, state: GameState) -> str:
        """Hashable key for deduplication. Override for efficiency."""
        return str(state.board) + str(state.current_player)
