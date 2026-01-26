"""
Embedding Model Management Mixin

Provides FastEmbed and ColBERT embedding initialization and management
for the ModuleWrapper system.
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# LAZY-LOADED IMPORTS
# =============================================================================

_fastembed = None
_colbert_embed = None


def _get_fastembed():
    """Lazy load FastEmbed when first needed."""
    global _fastembed
    if _fastembed is None:
        logger.info("Loading FastEmbed (first use)...")
        from fastembed import TextEmbedding

        _fastembed = TextEmbedding
        logger.info("FastEmbed loaded")
    return _fastembed


def _get_colbert_embed():
    """Lazy load ColBERT LateInteractionTextEmbedding when first needed."""
    global _colbert_embed
    if _colbert_embed is None:
        logger.info("Loading ColBERT LateInteractionTextEmbedding (first use)...")
        from fastembed import LateInteractionTextEmbedding

        _colbert_embed = LateInteractionTextEmbedding
        logger.info("ColBERT LateInteractionTextEmbedding loaded")
    return _colbert_embed


# =============================================================================
# EMBEDDING MIXIN
# =============================================================================


class EmbeddingMixin:
    """
    Mixin providing embedding model initialization and management.

    Expects the following attributes on self:
    - embedding_model_name: str
    - enable_colbert: bool
    - colbert_model_name: str
    """

    # Attributes to be set by __init__ in the composed class
    embedder: Any = None
    embedding_dim: Optional[int] = None
    colbert_embedder: Any = None
    colbert_embedding_dim: int = 128
    _colbert_initialized: bool = False

    def _clear_fastembed_cache(self, model_name: Optional[str] = None) -> bool:
        """
        Clear corrupted FastEmbed cache to allow re-download.

        Args:
            model_name: Optional specific model name to clear (clears all if None)

        Returns:
            bool: True if cache was cleared successfully
        """
        import os

        cleared = False
        cache_locations = [
            Path(tempfile.gettempdir()) / "fastembed_cache",
            Path.home() / ".cache" / "fastembed",
        ]

        # Also check macOS-specific temp locations
        try:
            # Get the actual temp directory which may be in /var/folders on macOS
            actual_temp = Path(os.path.realpath(tempfile.gettempdir()))
            if actual_temp not in cache_locations:
                cache_locations.append(actual_temp / "fastembed_cache")
        except Exception:
            pass

        for cache_dir in cache_locations:
            if cache_dir.exists():
                try:
                    if model_name:
                        # Clear specific model cache
                        model_short = model_name.split("/")[-1]
                        for subdir in cache_dir.iterdir():
                            if model_short in subdir.name or "MiniLM" in subdir.name:
                                logger.info(f"Clearing corrupted cache: {subdir}")
                                shutil.rmtree(subdir)
                                cleared = True
                    else:
                        # Clear entire cache
                        logger.info(f"Clearing entire FastEmbed cache: {cache_dir}")
                        shutil.rmtree(cache_dir)
                        cleared = True
                except Exception as clear_error:
                    logger.warning(f"Could not clear cache {cache_dir}: {clear_error}")

        return cleared

    def _initialize_embedder(self):
        """Initialize the embedding model with retry logic for corrupted cache."""
        global _fastembed

        max_retries = 2
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                TextEmbedding = _get_fastembed()
                self.embedder = TextEmbedding(model_name=self.embedding_model_name)

                # Try to get embedding dimension dynamically
                try:
                    # Generate a test embedding to get the dimension
                    test_embedding = list(self.embedder.embed(["test"]))[0]
                    self.embedding_dim = (
                        len(test_embedding)
                        if hasattr(test_embedding, "__len__")
                        else 384
                    )
                except Exception:
                    # Fallback to known dimensions for common models
                    model_dims = {
                        "sentence-transformers/all-MiniLM-L6-v2": 384,
                        "sentence-transformers/all-mpnet-base-v2": 768,
                    }
                    self.embedding_dim = model_dims.get(self.embedding_model_name, 384)

                logger.info(
                    f"Embedding model loaded: {self.embedding_model_name} (dim: {self.embedding_dim})"
                )
                return  # Success!

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check if this is a cache/file corruption error that we can recover from
                is_recoverable = any(
                    keyword in error_str
                    for keyword in [
                        "no_suchfile",
                        "file doesn't exist",
                        "corrupted",
                        "model.onnx",
                        "failed to load",
                        "invalid model",
                    ]
                )

                if is_recoverable and attempt < max_retries:
                    logger.warning(
                        f"Embedding model load failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    logger.info(
                        "Attempting to clear corrupted cache and re-download model..."
                    )

                    # Clear the cache and retry
                    if self._clear_fastembed_cache(self.embedding_model_name):
                        logger.info("Cache cleared, retrying model download...")
                        # Reset the global fastembed reference to force reload
                        _fastembed = None
                        continue
                    else:
                        logger.warning("Could not clear cache, retrying anyway...")
                        continue
                else:
                    # Non-recoverable error or out of retries
                    break

        # All retries exhausted
        logger.error(
            f"Failed to initialize embedding model after {max_retries + 1} attempts: {last_error}"
        )
        raise last_error

    def _initialize_colbert_embedder(self):
        """Initialize the ColBERT late interaction embedding model."""
        if not self.enable_colbert:
            return

        try:
            LateInteractionTextEmbedding = _get_colbert_embed()
            logger.info(f"Initializing ColBERT model: {self.colbert_model_name}")
            self.colbert_embedder = LateInteractionTextEmbedding(
                model_name=self.colbert_model_name
            )

            # Get embedding dimension from model
            colbert_dims = {
                "colbert-ir/colbertv2.0": 128,
                "answerdotai/answerai-colbert-small-v1": 96,
            }
            self.colbert_embedding_dim = colbert_dims.get(self.colbert_model_name, 128)

            logger.info(
                f"ColBERT model loaded: {self.colbert_model_name} (dim: {self.colbert_embedding_dim})"
            )
            self._colbert_initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize ColBERT embedder: {e}")
            self.enable_colbert = False
            raise

    @property
    def embedding_metadata(self) -> Dict[str, Any]:
        """Get metadata about the embedding configuration."""
        return {
            "embedding_model": getattr(self, "embedding_model_name", None),
            "embedding_dim": self.embedding_dim,
            "colbert_enabled": getattr(self, "enable_colbert", False),
            "colbert_model": (
                getattr(self, "colbert_model_name", None)
                if getattr(self, "enable_colbert", False)
                else None
            ),
            "colbert_dim": (
                self.colbert_embedding_dim
                if getattr(self, "_colbert_initialized", False)
                else None
            ),
        }


# Export for convenience
__all__ = [
    "EmbeddingMixin",
    "_get_fastembed",
    "_get_colbert_embed",
]
