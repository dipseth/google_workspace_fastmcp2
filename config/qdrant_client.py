"""
Centralized Qdrant Client Singleton

This module provides a single, shared QdrantClient instance used across
the entire application. All modules should import from here instead of
creating their own QdrantClient instances.

Features:
- Auto-launches Qdrant via Docker if not reachable (when enabled)
- Seamless fallback for local development
- Persistent data storage

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
_docker_launch_attempted = False


def _ensure_qdrant_available() -> bool:
    """
    Ensure Qdrant is available, auto-launching via Docker if needed.

    Returns:
        bool: True if Qdrant is available
    """
    global _docker_launch_attempted

    # Only attempt Docker launch once
    if _docker_launch_attempted:
        return True

    _docker_launch_attempted = True

    try:
        from config.qdrant_docker import ensure_qdrant_running

        success, url = ensure_qdrant_running()
        if success:
            logger.info(f"Qdrant available at: {url}")
            return True
        else:
            logger.warning("Qdrant not available - features requiring vector storage will be disabled")
            return False
    except ImportError as e:
        logger.debug(f"Docker auto-launch module not available: {e}")
        return True  # Continue with normal initialization
    except Exception as e:
        logger.warning(f"Error checking Qdrant availability: {e}")
        return True  # Continue with normal initialization


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

    # Ensure Qdrant is available (auto-launch via Docker if needed)
    _ensure_qdrant_available()

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
    global _qdrant_client, _initialization_attempted, _docker_launch_attempted

    if _qdrant_client is not None:
        try:
            _qdrant_client.close()
            logger.info("🔒 Qdrant client closed")
        except Exception as e:
            logger.warning(f"⚠️ Error closing Qdrant client: {e}")

    _qdrant_client = None
    _initialization_attempted = False
    _docker_launch_attempted = False


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


def get_qdrant_status() -> dict:
    """
    Get comprehensive Qdrant status including Docker info.

    Returns:
        dict: Status information including connection state and Docker details
    """
    try:
        from config.settings import settings

        status = {
            "client_initialized": _qdrant_client is not None,
            "initialization_attempted": _initialization_attempted,
            "docker_launch_attempted": _docker_launch_attempted,
            "qdrant_url": settings.qdrant_url,
            "qdrant_host": settings.qdrant_host,
            "qdrant_port": settings.qdrant_port,
            "auto_launch_enabled": getattr(settings, 'qdrant_auto_launch', True),
        }

        # Check if actually connected
        if _qdrant_client is not None:
            try:
                collections = _qdrant_client.get_collections()
                status["connected"] = True
                status["collections_count"] = len(collections.collections)
            except Exception as e:
                status["connected"] = False
                status["connection_error"] = str(e)
        else:
            status["connected"] = False

        # Get Docker status if available
        try:
            from config.qdrant_docker import get_qdrant_status as get_docker_status
            status["docker"] = get_docker_status()
        except ImportError:
            status["docker"] = {"available": False, "reason": "module_not_found"}
        except Exception as e:
            status["docker"] = {"available": False, "error": str(e)}

        return status
    except Exception as e:
        return {"error": str(e)}
