"""
Centralized Embedding Service — Thread-Safe Singleton.

Owns all FastEmbed model instances (MiniLM, ColBERT, BGE-small).
All consumers get model references from this service instead of
creating their own, eliminating ~1.5GB of redundant model memory.

Usage:
    from config.embedding_service import get_embedding_service

    service = get_embedding_service()
    model = await service.get_model("minilm")       # raw FastEmbed instance
    vecs = await service.embed_dense(["hello"])      # convenience wrapper
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Model slot definitions: slot_name -> (module_attr, default_model_name)
_SLOT_DEFAULTS = {
    "minilm": ("TextEmbedding", "sentence-transformers/all-MiniLM-L6-v2"),
    "colbert": ("LateInteractionTextEmbedding", "colbert-ir/colbertv2.0"),
    "bge-small": ("TextEmbedding", "BAAI/bge-small-en-v1.5"),
}


class EmbeddingService:
    """Centralized thread-safe embedding model manager.

    Manages 3 model slots: "minilm", "colbert", "bge-small".
    Each slot has one shared model instance, protected by asyncio.Lock.
    """

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._locks: Dict[str, asyncio.Lock] = {
            slot: asyncio.Lock() for slot in _SLOT_DEFAULTS
        }
        self._model_names: Dict[str, str] = {}
        self._dimensions: Dict[str, int] = {}
        self._load_config()

    def _load_config(self):
        """Load model names from settings (with safe fallbacks)."""
        try:
            from config.settings import settings

            self._model_names = {
                "minilm": getattr(
                    settings,
                    "embedding_minilm_model",
                    _SLOT_DEFAULTS["minilm"][1],
                ),
                "colbert": getattr(
                    settings,
                    "embedding_colbert_model",
                    _SLOT_DEFAULTS["colbert"][1],
                ),
                "bge-small": getattr(
                    settings,
                    "embedding_bge_model",
                    _SLOT_DEFAULTS["bge-small"][1],
                ),
            }
        except Exception:
            self._model_names = {
                slot: default[1] for slot, default in _SLOT_DEFAULTS.items()
            }

    def _clear_fastembed_cache(self, model_name: Optional[str] = None) -> bool:
        """Clear corrupted FastEmbed cache to allow re-download."""
        import os

        cleared = False
        cache_locations = [
            Path(tempfile.gettempdir()) / "fastembed_cache",
            Path.home() / ".cache" / "fastembed",
        ]

        try:
            actual_temp = Path(os.path.realpath(tempfile.gettempdir()))
            if actual_temp not in cache_locations:
                cache_locations.append(actual_temp / "fastembed_cache")
        except Exception:
            pass

        for cache_dir in cache_locations:
            if cache_dir.exists():
                try:
                    if model_name:
                        model_short = model_name.split("/")[-1]
                        for subdir in cache_dir.iterdir():
                            if model_short in subdir.name or "MiniLM" in subdir.name:
                                logger.info(f"Clearing corrupted cache: {subdir}")
                                shutil.rmtree(subdir)
                                cleared = True
                    else:
                        logger.info(f"Clearing entire FastEmbed cache: {cache_dir}")
                        shutil.rmtree(cache_dir)
                        cleared = True
                except Exception as e:
                    logger.warning(f"Could not clear cache {cache_dir}: {e}")

        return cleared

    def _load_model_sync(self, slot: str) -> Any:
        """Synchronously load a FastEmbed model with retry on cache corruption.

        Returns the raw model instance.
        """
        model_name = self._model_names.get(slot, _SLOT_DEFAULTS[slot][1])
        class_name = _SLOT_DEFAULTS[slot][0]

        max_retries = 2
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                if class_name == "LateInteractionTextEmbedding":
                    from fastembed import LateInteractionTextEmbedding

                    model = LateInteractionTextEmbedding(model_name=model_name)
                else:
                    from fastembed import TextEmbedding

                    model = TextEmbedding(model_name=model_name)

                logger.info(f"EmbeddingService: loaded {slot} model '{model_name}'")
                return model

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                is_recoverable = any(
                    kw in error_str
                    for kw in [
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
                        f"EmbeddingService: {slot} load failed "
                        f"(attempt {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    self._clear_fastembed_cache(model_name)
                    continue
                else:
                    break

        logger.error(
            f"EmbeddingService: failed to load {slot} after "
            f"{max_retries + 1} attempts: {last_error}"
        )
        raise last_error

    def _detect_dimension(self, model: Any, slot: str) -> int:
        """Detect embedding dimension from a model."""
        known_dims = {
            "minilm": 384,
            "colbert": 128,
            "bge-small": 384,
        }
        try:
            if slot == "colbert":
                # ColBERT: multi-vector, use known dim
                return known_dims.get(slot, 128)
            test = list(model.embed(["test"]))[0]
            return len(test) if hasattr(test, "__len__") else known_dims.get(slot, 384)
        except Exception:
            return known_dims.get(slot, 384)

    async def get_model(self, slot: str) -> Any:
        """Get or lazily load a FastEmbed model instance (async, thread-safe).

        Args:
            slot: One of "minilm", "colbert", "bge-small"

        Returns:
            The raw FastEmbed model instance (TextEmbedding or
            LateInteractionTextEmbedding). Callers can use .embed()
            / .query_embed() directly.
        """
        if slot not in _SLOT_DEFAULTS:
            raise ValueError(
                f"Unknown embedding slot '{slot}'. "
                f"Valid slots: {list(_SLOT_DEFAULTS.keys())}"
            )

        # Fast path: already loaded
        if slot in self._models:
            return self._models[slot]

        async with self._locks[slot]:
            # Double-check after lock
            if slot in self._models:
                return self._models[slot]

            logger.info(f"EmbeddingService: loading {slot} model...")
            loop = asyncio.get_running_loop()
            model = await loop.run_in_executor(None, self._load_model_sync, slot)

            self._dimensions[slot] = self._detect_dimension(model, slot)
            self._models[slot] = model
            return model

    def get_model_sync(self, slot: str) -> Any:
        """Get or lazily load a FastEmbed model instance (sync).

        For callers not in an async context. Uses a simple check-and-load
        pattern (the async lock handles concurrent async callers).
        """
        if slot in self._models:
            return self._models[slot]

        model = self._load_model_sync(slot)
        self._dimensions[slot] = self._detect_dimension(model, slot)
        self._models[slot] = model
        return model

    def get_dimension(self, slot: str) -> int:
        """Get the embedding dimension for a loaded slot."""
        return self._dimensions.get(
            slot, {"minilm": 384, "colbert": 128, "bge-small": 384}.get(slot, 384)
        )

    async def embed_dense(
        self, texts: List[str], model: str = "minilm"
    ) -> List[List[float]]:
        """Embed texts with MiniLM/BGE (returns 384-dim dense vectors)."""
        embedder = await self.get_model(model)
        loop = asyncio.get_running_loop()

        def _do():
            return [v.tolist() for v in embedder.embed(texts)]

        return await loop.run_in_executor(None, _do)

    async def embed_multivector(
        self, texts: List[str], model: str = "colbert"
    ) -> List[List[List[float]]]:
        """Embed texts with ColBERT (returns per-token 128-dim vectors)."""
        embedder = await self.get_model(model)
        loop = asyncio.get_running_loop()

        def _do():
            return [v.tolist() for v in embedder.embed(texts)]

        return await loop.run_in_executor(None, _do)

    def embed_dense_sync(
        self, texts: List[str], model: str = "minilm"
    ) -> List[List[float]]:
        """Sync wrapper for embed_dense."""
        embedder = self.get_model_sync(model)
        return [v.tolist() for v in embedder.embed(texts)]

    def embed_multivector_sync(
        self, texts: List[str], model: str = "colbert"
    ) -> List[List[List[float]]]:
        """Sync wrapper for embed_multivector."""
        embedder = self.get_model_sync(model)
        return [v.tolist() for v in embedder.embed(texts)]

    async def preload(self, *slots: str) -> None:
        """Eagerly load models (call from lifespan)."""
        for slot in slots:
            if slot and slot in _SLOT_DEFAULTS:
                await self.get_model(slot)

    async def shutdown(self) -> None:
        """Release all model instances."""
        count = len(self._models)
        self._models.clear()
        self._dimensions.clear()
        if count:
            logger.info(f"EmbeddingService: released {count} model(s)")

    def get_status(self) -> Dict[str, Any]:
        """Get status info for debugging."""
        return {
            "loaded_slots": list(self._models.keys()),
            "model_names": self._model_names,
            "dimensions": self._dimensions,
        }


# =====================================================================
# Module-level singleton
# =====================================================================

_instance: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the global EmbeddingService singleton."""
    global _instance
    if _instance is None:
        _instance = EmbeddingService()
    return _instance


async def close_embedding_service() -> None:
    """Shut down and release the global EmbeddingService."""
    global _instance
    if _instance is not None:
        await _instance.shutdown()
        _instance = None
