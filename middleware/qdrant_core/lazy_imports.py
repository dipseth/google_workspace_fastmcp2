"""
Lazy Import Utilities for Qdrant Middleware

This module provides lazy loading functionality for heavy dependencies
to avoid import errors and delays during server startup. Dependencies
are loaded only when first needed.
"""

import logging
from typing import Dict

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Global variables for lazy-loaded imports
_qdrant_client = None
_qdrant_models = None
_fastembed = None
_numpy = None


def get_numpy():
    """
    Lazy load numpy to avoid import errors during server startup.

    Returns:
        numpy module or None if not available
    """
    global _numpy
    if _numpy is None:
        try:
            import numpy as np

            _numpy = np
            logger.debug("📦 NumPy loaded successfully")
        except ImportError as e:
            logger.warning(f"⚠️ NumPy not available: {e}")
            _numpy = False
    return _numpy if _numpy is not False else None


def get_qdrant_imports():
    """
    Lazy load Qdrant imports when first needed.

    Returns:
        Tuple of (QdrantClient class, qdrant_models dict)
    """
    global _qdrant_client, _qdrant_models
    if _qdrant_client is None:
        logger.info("🔗 Loading Qdrant client (first use)...")
        from qdrant_client import QdrantClient, models
        from qdrant_client.models import (
            BoolIndexParams,
            BoolIndexType,
            DatetimeIndexParams,
            DatetimeIndexType,
            Distance,
            HnswConfigDiff,
            IntegerIndexParams,
            IntegerIndexType,
            KeywordIndexParams,
            KeywordIndexType,
            OptimizersConfigDiff,
            PayloadSchemaType,
            PointStruct,
            VectorParams,
        )

        _qdrant_client = QdrantClient
        _qdrant_models = {
            "models": models,
            "Distance": Distance,
            "VectorParams": VectorParams,
            "PointStruct": PointStruct,
            "PayloadSchemaType": PayloadSchemaType,
            # Index parameter classes
            "KeywordIndexParams": KeywordIndexParams,
            "KeywordIndexType": KeywordIndexType,
            "IntegerIndexParams": IntegerIndexParams,
            "IntegerIndexType": IntegerIndexType,
            "BoolIndexParams": BoolIndexParams,
            "BoolIndexType": BoolIndexType,
            "DatetimeIndexParams": DatetimeIndexParams,
            "DatetimeIndexType": DatetimeIndexType,
            # Configuration classes
            "HnswConfigDiff": HnswConfigDiff,
            "OptimizersConfigDiff": OptimizersConfigDiff,
        }
        logger.info("✅ Qdrant client loaded with enhanced indexing support")

    return _qdrant_client, _qdrant_models


def get_fastembed():
    """
    Lazy load FastEmbed when first needed.

    Returns:
        TextEmbedding class from FastEmbed
    """
    global _fastembed
    if _fastembed is None:
        logger.info("🤖 Loading FastEmbed (first use)...")
        from fastembed import TextEmbedding

        _fastembed = TextEmbedding
        logger.info("✅ FastEmbed loaded")
    return _fastembed


def reset_imports():
    """Reset all lazy imports. Useful for testing or reinitialization."""
    global _qdrant_client, _qdrant_models, _fastembed, _numpy
    _qdrant_client = None
    _qdrant_models = None
    _fastembed = None
    _numpy = None
    logger.debug("🔄 All lazy imports reset")


def get_import_status() -> Dict[str, bool]:
    """Get the current status of lazy imports."""
    return {
        "numpy": _numpy is not None and _numpy is not False,
        "qdrant_client": _qdrant_client is not None,
        "fastembed": _fastembed is not None,
    }


# Legacy aliases for backward compatibility
_get_numpy = get_numpy
_get_qdrant_imports = get_qdrant_imports
_get_fastembed = get_fastembed
