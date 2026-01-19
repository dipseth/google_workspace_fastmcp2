"""
Centralized Qdrant Client Singleton

This module provides a single, shared QdrantClient instance used across
the entire application. All modules should import from here instead of
creating their own QdrantClient instances.

Usage:
    from config.qdrant_client import get_qdrant_client

    client = get_qdrant_client()
    if client:
        collections = client.get_collections()
"""

from typing import Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Global singleton instance
_qdrant_client = None
_initialization_attempted = False


def get_qdrant_client(force_reinit: bool = False) -> Optional["QdrantClient"]:
    """
    Get the shared QdrantClient singleton instance.

    Uses centralized settings from config/settings.py for:
    - qdrant_url: The Qdrant server URL
    - qdrant_api_key: API key for authentication
    - qdrant_prefer_grpc: Whether to use gRPC (avoids SSL issues)

    Args:
        force_reinit: Force re-initialization even if already initialized

    Returns:
        QdrantClient instance or None if initialization failed
    """
    global _qdrant_client, _initialization_attempted

    if _qdrant_client is not None and not force_reinit:
        return _qdrant_client

    if _initialization_attempted and not force_reinit:
        return _qdrant_client  # Return cached result (even if None)

    _initialization_attempted = True

    try:
        from qdrant_client import QdrantClient
        from config.settings import settings

        logger.info("🔗 Initializing centralized Qdrant client...")
        logger.debug(
            f"📊 Qdrant config: URL={settings.qdrant_url}, "
            f"API Key={'***' if settings.qdrant_api_key else 'None'}, "
            f"gRPC={settings.qdrant_prefer_grpc}"
        )

        if settings.qdrant_url:
            # URL-based initialization (cloud or remote)
            _qdrant_client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                prefer_grpc=settings.qdrant_prefer_grpc,
            )
            logger.info(
                f"✅ Qdrant client connected: {settings.qdrant_url} "
                f"(gRPC: {settings.qdrant_prefer_grpc})"
            )
        else:
            # Host/port-based initialization (local)
            _qdrant_client = QdrantClient(
                host=settings.qdrant_host or "localhost",
                port=settings.qdrant_port or 6333,
                api_key=settings.qdrant_api_key,
            )
            logger.info(
                f"✅ Qdrant client connected: {settings.qdrant_host}:{settings.qdrant_port}"
            )

        # Test the connection
        try:
            collections = _qdrant_client.get_collections()
            logger.info(f"✅ Qdrant connection verified - {len(collections.collections)} collections")
        except Exception as test_err:
            logger.warning(f"⚠️ Qdrant connection test failed: {test_err}")
            # Don't fail completely - client might still work for some operations

    except ImportError as e:
        logger.warning(f"⚠️ qdrant-client not installed: {e}")
        _qdrant_client = None
    except Exception as e:
        logger.error(f"❌ Failed to initialize Qdrant client: {e}")
        _qdrant_client = None

    return _qdrant_client


def close_qdrant_client():
    """Close and reset the Qdrant client singleton."""
    global _qdrant_client, _initialization_attempted

    if _qdrant_client is not None:
        try:
            _qdrant_client.close()
            logger.info("🔒 Qdrant client closed")
        except Exception as e:
            logger.warning(f"⚠️ Error closing Qdrant client: {e}")

    _qdrant_client = None
    _initialization_attempted = False


def is_qdrant_available() -> bool:
    """Check if Qdrant client is available and connected."""
    client = get_qdrant_client()
    if client is None:
        return False

    try:
        client.get_collections()
        return True
    except Exception:
        return False
