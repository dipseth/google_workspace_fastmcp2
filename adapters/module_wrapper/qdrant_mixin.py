"""
Qdrant Client Management Mixin

Provides Qdrant client initialization, collection management, and lazy imports
for the ModuleWrapper system.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# =============================================================================
# LAZY-LOADED IMPORTS
# =============================================================================

_qdrant_client = None
_qdrant_models = None
_numpy = None


def _get_numpy():
    """Lazy load numpy to avoid import errors during startup."""
    global _numpy
    if _numpy is None:
        try:
            import numpy as np
            _numpy = np
            logger.debug("NumPy loaded successfully")
        except ImportError as e:
            logger.warning(f"NumPy not available: {e}")
            _numpy = False
    return _numpy if _numpy is not False else None


def _get_qdrant_imports():
    """Lazy load Qdrant imports when first needed."""
    global _qdrant_client, _qdrant_models
    if _qdrant_client is None:
        logger.info("Loading Qdrant client (first use)...")
        from qdrant_client import QdrantClient, models
        from qdrant_client.models import (
            Distance,
            FieldCondition,
            Filter,
            MatchValue,
            PointStruct,
            VectorParams,
        )

        _qdrant_client = QdrantClient
        _qdrant_models = {
            "models": models,
            "Distance": Distance,
            "VectorParams": VectorParams,
            "PointStruct": PointStruct,
            "Filter": Filter,
            "FieldCondition": FieldCondition,
            "MatchValue": MatchValue,
        }
        logger.info("Qdrant client loaded")
    return _qdrant_client, _qdrant_models


# =============================================================================
# QDRANT MIXIN
# =============================================================================

class QdrantMixin:
    """
    Mixin providing Qdrant client and collection management.

    Expects the following attributes on self:
    - qdrant_host, qdrant_port, qdrant_url, qdrant_api_key
    - qdrant_use_https, qdrant_prefer_grpc
    - collection_name, embedding_dim
    - force_reindex, clear_collection
    - enable_colbert, colbert_collection_name, colbert_embedding_dim
    """

    # Attributes to be set by __init__ in the composed class
    client: Any = None
    collection_needs_indexing: bool = True

    def _initialize_qdrant(self):
        """Initialize Qdrant client using centralized singleton."""
        try:
            # Use centralized Qdrant client singleton
            from config.qdrant_client import get_qdrant_client
            self.client = get_qdrant_client()

            if self.client is None:
                raise RuntimeError("Centralized Qdrant client not available")

            logger.info("ModuleWrapper using centralized Qdrant client")

        except Exception as e:
            logger.error(f"Failed to get Qdrant client: {e}")
            raise

    def _ensure_collection(self):
        """Ensure the Qdrant collection exists and check if it needs indexing."""
        try:
            _, qdrant_models = _get_qdrant_imports()

            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            self.collection_needs_indexing = True  # Default to needing indexing

            # Handle clear_collection flag
            if self.clear_collection and self.collection_name in collection_names:
                logger.warning(f"Clearing collection {self.collection_name} as requested...")
                self.client.delete_collection(collection_name=self.collection_name)
                collection_names.remove(self.collection_name)
                logger.info(f"Collection {self.collection_name} cleared")

            if self.collection_name not in collection_names:
                # Create collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qdrant_models["VectorParams"](
                        size=self.embedding_dim,
                        distance=qdrant_models["Distance"].COSINE,
                    ),
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
                self.collection_needs_indexing = True
            else:
                # Check if collection has data
                collection_info = self.client.get_collection(self.collection_name)
                point_count = collection_info.points_count

                if self.force_reindex:
                    logger.info(
                        f"Using existing collection: {self.collection_name} "
                        f"({point_count} points) - Force re-indexing enabled"
                    )
                    self.collection_needs_indexing = True
                elif point_count > 0:
                    logger.info(
                        f"Using existing collection: {self.collection_name} "
                        f"({point_count} points) - Skipping indexing"
                    )
                    self.collection_needs_indexing = False
                else:
                    logger.info(f"Using existing collection: {self.collection_name} (empty)")
                    self.collection_needs_indexing = True

        except Exception as e:
            logger.error(f"Failed to ensure collection exists: {e}")
            raise

    def _ensure_colbert_collection(self):
        """Ensure the Qdrant collection for ColBERT multi-vectors exists."""
        if not self.enable_colbert or not getattr(self, '_colbert_initialized', False):
            return

        try:
            _, qdrant_models = _get_qdrant_imports()

            # Check if ColBERT collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.colbert_collection_name in collection_names:
                logger.info(f"ColBERT collection '{self.colbert_collection_name}' exists")
                # Check if it has data
                collection_info = self.client.get_collection(self.colbert_collection_name)
                if collection_info.points_count > 0:
                    logger.info(
                        f"ColBERT collection has {collection_info.points_count} points"
                    )
                return

            # Create ColBERT collection with multi-vector configuration
            logger.info(f"Creating ColBERT collection: {self.colbert_collection_name}")

            # For ColBERT, we use multi-vector storage
            self.client.create_collection(
                collection_name=self.colbert_collection_name,
                vectors_config={
                    "colbert": qdrant_models["VectorParams"](
                        size=self.colbert_embedding_dim,
                        distance=qdrant_models["Distance"].COSINE,
                        multivector_config=qdrant_models["models"].MultiVectorConfig(
                            comparator=qdrant_models["models"].MultiVectorComparator.MAX_SIM
                        ),
                    )
                },
            )
            logger.info(f"ColBERT collection created: {self.colbert_collection_name}")

        except Exception as e:
            logger.error(f"Failed to ensure ColBERT collection: {e}")
            raise

    def ensure_symbol_index(self) -> bool:
        """
        Ensure a payload index exists on the 'symbol' field for fast lookups.

        Returns:
            True if index was created or already exists, False on error
        """
        try:
            _, qdrant_models = _get_qdrant_imports()

            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.collection_name not in collection_names:
                logger.warning(f"Collection {self.collection_name} does not exist yet")
                return False

            # Get collection info to check existing indexes
            collection_info = self.client.get_collection(self.collection_name)

            # Check if symbol index already exists
            existing_indexes = collection_info.payload_schema or {}
            if "symbol" in existing_indexes:
                logger.debug(f"Symbol index already exists in {self.collection_name}")
                return True

            # Create keyword index on symbol field
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="symbol",
                field_schema=qdrant_models["models"].PayloadSchemaType.KEYWORD,
            )

            logger.info(f"Created symbol index in {self.collection_name}")
            return True

        except Exception as e:
            logger.warning(f"Could not ensure symbol index: {e}")
            return False

    @property
    def collection_metadata(self) -> Dict[str, Any]:
        """Get metadata about the Qdrant collection."""
        if not getattr(self, '_initialized', False):
            return {"error": "Not initialized"}

        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "points_count": collection_info.points_count,
                "vectors_count": getattr(collection_info, 'vectors_count', None),
                "status": str(collection_info.status),
                "config": {
                    "embedding_model": getattr(self, 'embedding_model_name', None),
                    "embedding_dim": self.embedding_dim,
                },
            }
        except Exception as e:
            logger.warning(f"Could not get collection metadata: {e}")
            return {"error": str(e)}


# Export for convenience
__all__ = [
    "QdrantMixin",
    "_get_qdrant_imports",
    "_get_numpy",
]
