"""
Centralized Qdrant Client Singleton

This module provides a single, shared QdrantClient instance used across
the entire application. All modules should import from here instead of
creating their own QdrantClient instances.

Features:
- Auto-launches Qdrant via Docker if not reachable (when enabled)
- Seamless fallback for local development
- Persistent data storage
- Graceful degradation: returns None when Qdrant is unreachable so
  callers short-circuit cleanly instead of hitting per-call gRPC errors

Usage:
    from config.qdrant_client import get_qdrant_client, is_qdrant_available

    if is_qdrant_available():
        client = get_qdrant_client()
        # ...
"""

import socket
from typing import Optional
from urllib.parse import urlparse

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Global singleton instance
_qdrant_client = None
_initialization_attempted = False
_docker_launch_attempted = False
# Cached availability result; None means "not yet probed"
_availability_cache: Optional[bool] = None


def _probe_tcp(host: str, port: int, timeout: float = 0.5) -> bool:
    """Quick TCP reachability probe — short timeout, no retries."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def is_qdrant_available(force_recheck: bool = False) -> bool:
    """Return True if Qdrant is reachable, False otherwise.

    Caches the result so repeated calls are cheap. Probes the gRPC port
    (default 6334) when prefer_grpc, falling back to HTTP (default 6333),
    so we detect the same unavailability the gRPC client would hit on
    its first real call.
    """
    global _availability_cache
    if _availability_cache is not None and not force_recheck:
        return _availability_cache

    try:
        from config.settings import settings

        url = settings.qdrant_url or "http://localhost:6333"
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        http_port = parsed.port or 6333
        grpc_port = settings.qdrant_docker_grpc_port or 6334

        # If gRPC preferred, probe both ports; gRPC is the load-bearing one
        if settings.qdrant_prefer_grpc:
            available = _probe_tcp(host, grpc_port) and _probe_tcp(host, http_port)
        else:
            available = _probe_tcp(host, http_port)
    except Exception as e:
        logger.debug(f"Qdrant TCP probe error: {e}")
        available = False

    _availability_cache = available
    return available


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
            logger.warning(
                "Qdrant not available - features requiring vector storage will be disabled"
            )
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

    # Fast TCP probe: if Qdrant ports aren't even listening, don't bother
    # creating a phantom client that fails on every gRPC call. This is the
    # common case in single-container sandbox environments (Glama, Cloud Run
    # without a Qdrant sidecar, etc.).
    if not is_qdrant_available():
        logger.warning(
            "⚠️ Qdrant not reachable at configured URL — vector-storage "
            "features will be disabled. Set QDRANT_URL or run a Qdrant "
            "sidecar to enable."
        )
        _qdrant_client = None
        return None

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

        # Test the connection. If it fails, drop the phantom client so
        # callers see None instead of hitting per-call gRPC errors that
        # bubble up as noisy tracebacks throughout startup.
        try:
            collections = _qdrant_client.get_collections()
            logger.info(
                f"✅ Qdrant connection verified - {len(collections.collections)} collections"
            )
        except Exception as test_err:
            logger.warning(
                f"⚠️ Qdrant connection test failed ({test_err}) — disabling "
                "vector-storage features for this process"
            )
            try:
                _qdrant_client.close()
            except Exception:
                pass
            _qdrant_client = None
            global _availability_cache
            _availability_cache = False
            return None

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
    global _availability_cache

    if _qdrant_client is not None:
        try:
            _qdrant_client.close()
            logger.info("🔒 Qdrant client closed")
        except Exception as e:
            logger.warning(f"⚠️ Error closing Qdrant client: {e}")

    _qdrant_client = None
    _initialization_attempted = False
    _docker_launch_attempted = False
    _availability_cache = None


def get_tenant_client(user_email: str) -> Optional["QdrantClient"]:
    """Return a QdrantClient authenticated with a per-user JWT (Layer 2 defence).

    When Qdrant JWT RBAC is enabled (``QDRANT_JWT_RBAC=true`` in env and a valid
    ``QDRANT_KEY`` is set), this generates a short-lived JWT scoped to
    *user_email* so Qdrant enforces isolation server-side.

    Falls back to the shared singleton when JWT RBAC is not configured.

    Args:
        user_email: Authenticated user's email address.

    Returns:
        A tenant-scoped QdrantClient, or the shared singleton.
    """
    import os

    jwt_rbac_enabled = os.getenv("QDRANT_JWT_RBAC", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    if not jwt_rbac_enabled:
        return get_qdrant_client()

    from config.settings import settings

    api_key = settings.qdrant_api_key
    if not api_key:
        logger.warning(
            "QDRANT_JWT_RBAC enabled but no QDRANT_KEY set — falling back to shared client"
        )
        return get_qdrant_client()

    try:
        from qdrant_client import QdrantClient

        from middleware.qdrant_core.tenant import generate_tenant_jwt

        collection = os.getenv("QDRANT_COLLECTION", "mcp_tool_responses")
        token = generate_tenant_jwt(user_email, api_key, collection)

        if settings.qdrant_url:
            return QdrantClient(
                url=settings.qdrant_url,
                api_key=token,
                prefer_grpc=settings.qdrant_prefer_grpc,
            )
        else:
            return QdrantClient(
                host=settings.qdrant_host or "localhost",
                port=settings.qdrant_port or 6333,
                api_key=token,
            )
    except Exception as e:
        logger.warning(
            f"Failed to create tenant client for {user_email}: {e} — falling back to shared client"
        )
        return get_qdrant_client()


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
            "auto_launch_enabled": getattr(settings, "qdrant_auto_launch", True),
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
