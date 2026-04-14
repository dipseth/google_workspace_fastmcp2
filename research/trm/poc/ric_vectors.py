"""RIC (Relationships-Inputs-Components) embedding generation for game states.

Mirrors the module wrapper's 3-vector schema but uses a single dense embedding
model (MiniLM 384D) for all vectors. The semantic distinction comes from the
TEXT being embedded (identity vs actions vs structure), not the model.

For the POC, we skip ColBERT multi-vectors to keep vector arithmetic simple.
ColBERT support can be layered on later.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from fastembed import TextEmbedding
from games.base import Game, GameState
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

# Use MiniLM for all 3 vectors (384D dense)
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


@dataclass
class RICEmbedding:
    """Three-vector embedding for a game state."""

    components: np.ndarray  # 384D — "What IS this state?"
    inputs: np.ndarray  # 384D — "What moves are available?"
    relationships: np.ndarray  # 384D — "How do pieces connect?"


class RICEmbedder:
    """Generates and manages RIC embeddings for game states."""

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        client: Optional[QdrantClient] = None,
    ):
        self._model_name = model_name
        self._model: Optional[TextEmbedding] = None
        self.client = client or QdrantClient(location=":memory:")
        self.dim = EMBEDDING_DIM

    @property
    def model(self) -> TextEmbedding:
        if self._model is None:
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text string to a dense vector."""
        result = list(self.model.embed([text]))
        return np.array(result[0], dtype=np.float32)

    def embed_state(self, game: Game, state: GameState) -> RICEmbedding:
        """Generate all 3 RIC vectors for a game state."""
        comp_text = game.component_text(state)
        inp_text = game.inputs_text(state)
        rel_text = game.relationships_text(state)

        # Batch embed for efficiency
        texts = [comp_text, inp_text, rel_text]
        embeddings = list(self.model.embed(texts))

        return RICEmbedding(
            components=np.array(embeddings[0], dtype=np.float32),
            inputs=np.array(embeddings[1], dtype=np.float32),
            relationships=np.array(embeddings[2], dtype=np.float32),
        )

    def create_collection(
        self, collection_name: str, force_recreate: bool = False
    ) -> None:
        """Create a Qdrant collection with 3 named vectors."""
        if force_recreate:
            try:
                self.client.delete_collection(collection_name)
            except Exception:
                pass

        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "components": VectorParams(
                    size=self.dim,
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
                ),
                "inputs": VectorParams(
                    size=self.dim,
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
                ),
                "relationships": VectorParams(
                    size=self.dim,
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(m=32, ef_construct=200),
                ),
            },
        )

    def index_states(
        self,
        game: Game,
        states: list[tuple[GameState, int]],
        collection_name: str,
        batch_size: int = 50,
    ) -> int:
        """Index game states into Qdrant with RIC embeddings.

        Args:
            game: Game instance for text generation
            states: List of (state, optimal_move) pairs
            collection_name: Target Qdrant collection
            batch_size: Points per upsert batch

        Returns:
            Number of points indexed
        """
        points = []
        indexed = 0

        for i, (state, optimal_move) in enumerate(states):
            try:
                ric = self.embed_state(game, state)
                point_id = _deterministic_id(game, state)

                point = PointStruct(
                    id=point_id,
                    vector={
                        "components": ric.components.tolist(),
                        "inputs": ric.inputs.tolist(),
                        "relationships": ric.relationships.tolist(),
                    },
                    payload={
                        "game": game.name,
                        "optimal_move": optimal_move,
                        "current_player": state.current_player,
                        "board": str(state.board),
                        "move_history": state.move_history,
                        "component_text": game.component_text(state),
                        "inputs_text": game.inputs_text(state),
                        "relationships_text": game.relationships_text(state),
                    },
                )
                points.append(point)

                if len(points) >= batch_size:
                    self.client.upsert(collection_name=collection_name, points=points)
                    indexed += len(points)
                    points = []
                    logger.info(f"Indexed {indexed}/{len(states)} states")

            except Exception as e:
                logger.warning(f"Failed to index state {i}: {e}")

        # Final batch
        if points:
            self.client.upsert(collection_name=collection_name, points=points)
            indexed += len(points)

        logger.info(f"Indexed {indexed} total states into {collection_name}")
        return indexed


def _deterministic_id(game: Game, state: GameState) -> int:
    """Generate a deterministic point ID from game state."""
    key = f"{game.name}:{state.board}:{state.current_player}"
    h = hashlib.sha256(key.encode()).hexdigest()
    # Qdrant accepts positive integers; take first 15 hex chars
    return int(h[:15], 16)
