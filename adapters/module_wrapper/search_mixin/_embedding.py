"""Embedding helper functions for ColBERT and MiniLM models."""

from typing import List, Optional

from adapters.module_wrapper.types import (
    EmbeddingVector,
    MultiVector,
    QueryText,
)
from config.enhanced_logging import setup_logger

logger = setup_logger()


def _get_colbert_embedder(self):
    """
    Get ColBERT embedder for search operations.

    Tries multiple sources: pipeline mixin, core attribute, or EmbeddingService.

    Returns:
        ColBERT embedder instance or None if unavailable
    """
    # Try pipeline mixin's embedder
    if hasattr(self, "_colbert_embedder") and self._colbert_embedder is not None:
        return self._colbert_embedder

    # Try core attribute
    if hasattr(self, "colbert_embedder") and self.colbert_embedder is not None:
        return self.colbert_embedder

    # Get from centralized service
    try:
        from config.embedding_service import get_embedding_service

        logger.info("Getting ColBERT embedder from EmbeddingService...")
        embedder = get_embedding_service().get_model_sync("colbert")

        # Cache it
        if hasattr(self, "_colbert_embedder"):
            self._colbert_embedder = embedder
        else:
            self.colbert_embedder = embedder

        return embedder
    except Exception as e:
        logger.error(f"Failed to get ColBERT embedder: {e}")
        return None


def _get_minilm_embedder(self):
    """
    Get MiniLM embedder for search operations.

    Returns:
        MiniLM embedder instance or None if unavailable
    """
    # Try core attribute
    if hasattr(self, "embedder") and self.embedder is not None:
        return self.embedder

    # Get from centralized service
    try:
        from config.embedding_service import get_embedding_service

        logger.info("Getting MiniLM embedder from EmbeddingService...")
        embedder = get_embedding_service().get_model_sync("minilm")
        self.embedder = embedder
        return embedder
    except Exception as e:
        logger.error(f"Failed to get MiniLM embedder: {e}")
        return None


def _embed_with_colbert(
    self, text: QueryText, token_ratio: float = 1.0
) -> Optional[MultiVector]:
    """
    Generate ColBERT multi-vector embedding for text.

    Args:
        text: Text to embed
        token_ratio: Fraction of ColBERT tokens to use (0.0-1.0).
                     Lower values = faster search but potentially less accurate.

    Returns:
        List of token embedding vectors, or None if embedding fails
    """
    embedder = self._get_colbert_embedder()
    if not embedder:
        return None

    try:
        vectors_raw = list(embedder.query_embed(text))[0]
        vectors = [vec.tolist() for vec in vectors_raw]

        # Apply token truncation if requested
        if token_ratio < 1.0:
            cutoff = max(1, int(len(vectors) * token_ratio))
            vectors = vectors[:cutoff]
            logger.debug(f"Truncated to {cutoff}/{len(vectors_raw)} tokens")

        return vectors
    except Exception as e:
        logger.error(f"ColBERT embedding failed: {e}")
        return None


def _embed_with_minilm(self, text: QueryText) -> Optional[EmbeddingVector]:
    """
    Generate MiniLM single-vector embedding for text.

    Args:
        text: Text to embed

    Returns:
        384-dimensional embedding vector, or None if embedding fails
    """
    embedder = self._get_minilm_embedder()
    if not embedder:
        return None

    try:
        embedding_list = list(embedder.embed([text]))
        if not embedding_list:
            return None

        embedding = embedding_list[0]
        if hasattr(embedding, "tolist"):
            return embedding.tolist()
        return list(embedding)
    except Exception as e:
        logger.error(f"MiniLM embedding failed: {e}")
        return None
