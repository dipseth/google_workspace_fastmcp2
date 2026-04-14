"""
Embedding Model Management Mixin

Provides FastEmbed and ColBERT embedding initialization and management
for the ModuleWrapper system. Delegates to the centralized EmbeddingService
for model instances (thread-safe, deduplicated).
"""

from typing import Any, Dict, Optional

from adapters.module_wrapper.types import (
    COLBERT_DIM,
    MINILM_DIM,
    EmbeddingConfig,
    EmbeddingDimension,
    EmbeddingVector,
    MultiVector,
)
from config.enhanced_logging import setup_logger

logger = setup_logger()

# =============================================================================
# LEGACY COMPAT — lazy class loaders (kept for any remaining direct callers)
# =============================================================================

_fastembed = None
_colbert_embed = None

def _get_fastembed():
    """Lazy load FastEmbed TextEmbedding class (legacy compat)."""
    global _fastembed
    if _fastembed is None:
        from fastembed import TextEmbedding

        _fastembed = TextEmbedding
    return _fastembed

def _get_colbert_embed():
    """Lazy load ColBERT LateInteractionTextEmbedding class (legacy compat)."""
    global _colbert_embed
    if _colbert_embed is None:
        from fastembed import LateInteractionTextEmbedding

        _colbert_embed = LateInteractionTextEmbedding
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

    # --- Mixin dependency contract ---
    _MIXIN_PROVIDES = frozenset(
        {
            "embedder",
            "embedding_dim",
            "colbert_embedder",
            "colbert_embedding_dim",
            "_colbert_initialized",
            "_initialize_embedder",
            "_initialize_colbert_embedder",
            "embedding_metadata",
        }
    )
    _MIXIN_REQUIRES = frozenset(
        {
            "embedding_model_name",
            "enable_colbert",
            "colbert_model_name",
        }
    )
    _MIXIN_INIT_ORDER = 20

    # Attributes to be set by __init__ in the composed class
    embedder: Any = None
    embedding_dim: Optional[EmbeddingDimension] = None
    colbert_embedder: Any = None
    colbert_embedding_dim: EmbeddingDimension = COLBERT_DIM
    _colbert_initialized: bool = False

    def _initialize_embedder(self):
        """Initialize the MiniLM embedding model via centralized EmbeddingService."""
        try:
            from config.embedding_service import get_embedding_service

            service = get_embedding_service()
            self.embedder = service.get_model_sync("minilm")
            self.embedding_dim = service.get_dimension("minilm")

            logger.info(
                f"Embedding model loaded via EmbeddingService: "
                f"{self.embedding_model_name} (dim: {self.embedding_dim})"
            )
        except Exception as e:
            self.embedder = None
            self.embedding_dim = 384  # known MiniLM default
            logger.error(f"Failed to initialize embedder: {e}")
            raise

    def _initialize_colbert_embedder(self):
        """Initialize the ColBERT embedding model via centralized EmbeddingService."""
        if not self.enable_colbert:
            return

        try:
            from config.embedding_service import get_embedding_service

            service = get_embedding_service()
            self.colbert_embedder = service.get_model_sync("colbert")
            self.colbert_embedding_dim = service.get_dimension("colbert")

            logger.info(
                f"ColBERT model loaded via EmbeddingService: "
                f"{self.colbert_model_name} (dim: {self.colbert_embedding_dim})"
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
