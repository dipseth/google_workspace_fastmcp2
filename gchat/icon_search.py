"""
Semantic icon resolver using FastEmbed vector search.

When a bad/unknown icon name comes in (e.g., "CONFIRMATION_NUMBER_ICON",
"TREND_UP", "CLOCK"), this module finds the closest valid Material Design
icon by semantic similarity over the full 2,209 icon set.

Architecture:
    - On first use, embeds all icon names with FastEmbed (cached in memory)
    - Uses numpy dot product for instant nearest-neighbor search
    - No Qdrant dependency — pure in-memory, ~50ms cold start

Usage:
    from gchat.icon_search import semantic_icon_search

    # Returns "trending_up" for "TREND_UP"
    result = semantic_icon_search("TREND_UP")
"""

import threading
from typing import List, Optional, Tuple

import numpy as np

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Lazy-loaded singletons (guarded by _init_lock)
_embedder = None
_icon_names: Optional[List[str]] = None
_icon_embeddings: Optional[np.ndarray] = None
_init_lock = threading.Lock()


def _ensure_index():
    """Build the in-memory icon embedding index on first use."""
    global _embedder, _icon_names, _icon_embeddings

    if _icon_embeddings is not None:
        return

    with _init_lock:
        # Double-check after acquiring lock
        if _icon_embeddings is not None:
            return

        from config.embedding_service import get_embedding_service
        from gchat.material_icons import MATERIAL_ICONS

        logger.info(f"Building icon search index ({len(MATERIAL_ICONS)} icons)...")

        _embedder = get_embedding_service().get_model_sync("bge-small")

        # Prepare icon names with readable descriptions for better embeddings
        # "trending_up" -> "trending up" (underscores to spaces for semantic meaning)
        _icon_names = sorted(MATERIAL_ICONS)
        texts = [name.replace("_", " ") for name in _icon_names]

        # Embed all icons in one batch
        embeddings = list(_embedder.embed(texts))
        _icon_embeddings = np.array(embeddings, dtype=np.float32)

        # L2-normalize for cosine similarity via dot product
        norms = np.linalg.norm(_icon_embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        _icon_embeddings = _icon_embeddings / norms

    logger.info(f"Icon search index ready: {_icon_embeddings.shape}")


def semantic_icon_search(
    query: str,
    top_k: int = 1,
    min_score: float = 0.3,
) -> Optional[str]:
    """Find the best matching material icon for a query string.

    Args:
        query: Icon name, description, or concept (e.g., "TREND_UP", "clock",
               "confirmation number", "ticket")
        top_k: Number of candidates to return (only best is returned)
        min_score: Minimum cosine similarity threshold

    Returns:
        Best matching icon name, or None if below threshold
    """
    _ensure_index()

    # Normalize query: underscores to spaces, lowercase
    query_text = query.strip().replace("_", " ").lower()

    # Embed the query
    query_emb = list(_embedder.embed([query_text]))[0]
    query_emb = np.array(query_emb, dtype=np.float32)
    query_emb = query_emb / (np.linalg.norm(query_emb) or 1)

    # Cosine similarity via dot product (both are L2-normalized)
    scores = _icon_embeddings @ query_emb

    # Get top-k indices
    top_indices = np.argsort(scores)[-top_k:][::-1]

    best_idx = top_indices[0]
    best_score = scores[best_idx]

    if best_score < min_score:
        logger.debug(
            f"Icon search for '{query}': best='{_icon_names[best_idx]}' "
            f"score={best_score:.3f} < threshold={min_score}"
        )
        return None

    result = _icon_names[best_idx]
    logger.debug(f"Icon search: '{query}' -> '{result}' (score={best_score:.3f})")
    return result


def semantic_icon_search_top_k(
    query: str,
    top_k: int = 5,
    min_score: float = 0.3,
) -> List[Tuple[str, float]]:
    """Find top-k matching icons with scores.

    Args:
        query: Search query
        top_k: Number of results
        min_score: Minimum similarity threshold

    Returns:
        List of (icon_name, score) tuples, sorted by score descending
    """
    _ensure_index()

    query_text = query.strip().replace("_", " ").lower()
    query_emb = list(_embedder.embed([query_text]))[0]
    query_emb = np.array(query_emb, dtype=np.float32)
    query_emb = query_emb / (np.linalg.norm(query_emb) or 1)

    scores = _icon_embeddings @ query_emb
    top_indices = np.argsort(scores)[-top_k:][::-1]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score >= min_score:
            results.append((_icon_names[idx], score))

    return results
