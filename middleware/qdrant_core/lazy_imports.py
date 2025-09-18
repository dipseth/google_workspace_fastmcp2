"""
Lazy Import Utilities for Qdrant Middleware

This module provides lazy loading functionality for heavy dependencies
to avoid import errors and delays during server startup. Dependencies
are loaded only when first needed.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Global variables for lazy-loaded imports
_qdrant_client = None
_qdrant_models = None
_sentence_transformer = None
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
        from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
        _qdrant_client = QdrantClient
        _qdrant_models = {
            'models': models,
            'Distance': Distance,
            'VectorParams': VectorParams,
            'PointStruct': PointStruct,
            'PayloadSchemaType': PayloadSchemaType
        }
        logger.info("✅ Qdrant client loaded")
    return _qdrant_client, _qdrant_models


def get_sentence_transformer():
    """
    Lazy load SentenceTransformer when first needed.
    
    Returns:
        SentenceTransformer class
    """
    global _sentence_transformer
    if _sentence_transformer is None:
        logger.info("🤖 Loading SentenceTransformer (first use)...")
        from sentence_transformers import SentenceTransformer
        _sentence_transformer = SentenceTransformer
        logger.info("✅ SentenceTransformer loaded")
    return _sentence_transformer


def reset_imports():
    """
    Reset all lazy imports. Useful for testing or reinitialization.
    """
    global _qdrant_client, _qdrant_models, _sentence_transformer, _numpy
    _qdrant_client = None
    _qdrant_models = None
    _sentence_transformer = None
    _numpy = None
    logger.debug("🔄 All lazy imports reset")


def get_import_status() -> Dict[str, bool]:
    """
    Get the current status of lazy imports.
    
    Returns:
        Dict with import status for each module
    """
    return {
        "numpy": _numpy is not None and _numpy is not False,
        "qdrant_client": _qdrant_client is not None,
        "sentence_transformer": _sentence_transformer is not None
    }


# Legacy aliases for backward compatibility
_get_numpy = get_numpy
_get_qdrant_imports = get_qdrant_imports
_get_sentence_transformer = get_sentence_transformer