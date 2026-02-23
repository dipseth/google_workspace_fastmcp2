"""
FastMCP Server Lifespans - Composable Lifecycle Management.

This module provides individual lifespans for each middleware group that can be
composed together for the FastMCP server using the native | operator.

Each lifespan handles:
- Async initialization on startup
- Yielding context data for tools to access via ctx.lifespan_context
- Graceful cleanup on shutdown

Lifespan Composition Order:
Enter order (startup): left-to-right (nested context managers)
Exit order (shutdown): right-to-left (reverse)

Usage:
    from lifespans import combined_server_lifespan

    mcp = FastMCP(
        name="my-server",
        lifespan=combined_server_lifespan,
    )
"""

import gc
from typing import Any, Dict, Optional

from fastmcp.server.lifespan import ContextManagerLifespan, lifespan

from config.enhanced_logging import setup_logger

logger = setup_logger()


# Module-level references for cross-lifespan communication and middleware registration
# Middleware instances are registered here by server.py, then lifespans use them
_lifespan_state: Dict[str, Any] = {}


def register_qdrant_middleware(middleware: Any) -> None:
    """
    Register the Qdrant middleware instance created in server.py.

    This allows the lifespan to initialize and shutdown the SAME instance
    that's registered with FastMCP for intercepting tool calls.

    Args:
        middleware: QdrantUnifiedMiddleware instance from server.py
    """
    _lifespan_state["qdrant_middleware"] = middleware
    logger.debug("Registered Qdrant middleware for lifespan management")


@lifespan
async def qdrant_lifespan(server: Any):
    """
    Qdrant middleware lifecycle with proper async init and shutdown.

    IMPORTANT: This lifespan works with the middleware instance registered
    via register_qdrant_middleware() from server.py. It does NOT create
    a new instance - it initializes the existing one.

    Handles:
    - Async initialization of the registered middleware
    - Background reindexing scheduler startup
    - Graceful shutdown of background tasks

    Yields:
        Dict containing 'qdrant_middleware' instance
    """
    # Get the middleware registered by server.py
    qdrant_middleware = _lifespan_state.get("qdrant_middleware")

    if qdrant_middleware is None:
        logger.warning(
            "⚠️ Qdrant lifespan: No middleware registered, skipping initialization"
        )
        logger.warning(
            "   Call register_qdrant_middleware() from server.py before server starts"
        )
        yield {"qdrant_middleware": None}
        return

    logger.info("🚀 Qdrant lifespan: Starting async initialization...")

    # Async initialization with background reindexing
    await qdrant_middleware.initialize_middleware_and_reindexing()

    logger.info("✅ Qdrant lifespan: Initialization complete")

    try:
        yield {"qdrant_middleware": qdrant_middleware}
    finally:
        # Graceful shutdown — stop background tasks and release all resources
        logger.info("🔄 Qdrant lifespan: Starting shutdown...")
        await qdrant_middleware.stop_background_reindexing()

        # Close the Qdrant client connection, cancel tracked background tasks,
        # and release the embedding model memory
        from middleware.qdrant_core.client import close_global_client_manager

        await close_global_client_manager()
        logger.info(
            "✅ Qdrant lifespan shutdown complete (reindexing stopped, client closed, memory released)"
        )


@lifespan
async def colbert_lifespan(server: Any):
    """
    ColBERT wrapper lifecycle for multi-vector embeddings.

    Only initializes if COLBERT_EMBEDDING_DEV=true in settings.

    Yields:
        Dict containing 'colbert_wrapper' instance (or None if disabled)
    """
    from config.settings import settings

    colbert_wrapper = None

    if settings.colbert_embedding_dev:
        logger.info("🤖 ColBERT lifespan: Initializing wrapper...")
        try:
            from gchat.card_tools import _initialize_colbert_wrapper

            colbert_wrapper = _initialize_colbert_wrapper()
            logger.info("✅ ColBERT lifespan: Wrapper initialized")
        except Exception as e:
            logger.error(f"❌ ColBERT lifespan: Failed to initialize: {e}")
            logger.warning("   ColBERT mode will still work on-demand if called")
    else:
        logger.info("⏭️ ColBERT lifespan: Skipped (COLBERT_EMBEDDING_DEV=false)")

    try:
        yield {"colbert_wrapper": colbert_wrapper}
    finally:
        # ColBERT wrapper has no persistent state requiring cleanup
        if colbert_wrapper:
            logger.info("✅ ColBERT lifespan shutdown complete (no cleanup needed)")


@lifespan
async def session_state_lifespan(server: Any):
    """
    Session tool filtering lifecycle with state persistence on shutdown.

    Note: The actual middleware setup is done in server.py before lifespan runs.
    This lifespan handles state persistence on shutdown.

    Yields:
        Dict containing 'session_state_persisted' flag
    """
    from auth.context import persist_session_tool_states

    logger.info("🔐 Session state lifespan: Ready for state management")

    try:
        yield {"session_state_managed": True}
    finally:
        # Persist session tool states on shutdown
        logger.info("🔄 Session state lifespan: Persisting session states...")
        try:
            success = persist_session_tool_states()
            if success:
                logger.info("✅ Session state persisted successfully")
            else:
                logger.warning("⚠️ Session state persistence returned False")
        except Exception as e:
            logger.error(f"❌ Failed to persist session states: {e}")


@lifespan
async def cache_middleware_lifespan(server: Any):
    """
    Template and profile middleware cache lifecycle.

    IMPORTANT: This lifespan works with middleware instances registered
    via register_template_middleware() and register_profile_middleware()
    from server.py. It does NOT create new instances.

    Yields:
        Dict with cache_middleware_refs containing registered middleware
    """
    logger.info("🎭 Cache middleware lifespan: Ready for cache management")

    # Get the refs dict that was populated by register_*_middleware() calls
    # If not populated yet, create an empty one
    if "cache_middleware_refs" not in _lifespan_state:
        _lifespan_state["cache_middleware_refs"] = {
            "template_middleware": None,
            "profile_middleware": None,
        }

    middleware_refs = _lifespan_state["cache_middleware_refs"]

    # Log what's registered
    template_registered = middleware_refs.get("template_middleware") is not None
    profile_registered = middleware_refs.get("profile_middleware") is not None
    logger.info(f"   Template middleware registered: {template_registered}")
    logger.info(f"   Profile middleware registered: {profile_registered}")

    try:
        yield {"cache_middleware_refs": middleware_refs}
    finally:
        # Clear caches on shutdown
        logger.info("🔄 Cache middleware lifespan: Clearing caches...")

        template_cleared = 0
        profile_cleared = 0

        if middleware_refs.get("template_middleware"):
            try:
                stats = middleware_refs["template_middleware"].get_cache_stats()
                template_cleared = stats.get("total_entries", 0)
                middleware_refs["template_middleware"].clear_cache()
            except Exception as e:
                logger.warning(f"⚠️ Failed to clear template cache: {e}")

        if middleware_refs.get("profile_middleware"):
            try:
                stats = middleware_refs["profile_middleware"].get_cache_stats()
                in_memory = stats.get("in_memory_cache", {})
                profile_cleared = in_memory.get("total_entries", 0)
                middleware_refs["profile_middleware"].clear_cache()
            except Exception as e:
                logger.warning(f"⚠️ Failed to clear profile cache: {e}")

        logger.info(
            f"✅ Cache cleanup complete (template: {template_cleared} entries, "
            f"profile: {profile_cleared} entries)"
        )


@lifespan
async def dynamic_instructions_lifespan(server: Any):
    """
    Dynamic MCP instructions lifecycle.

    Updates MCP instructions with Qdrant analytics after Qdrant is initialized.
    Accesses qdrant_middleware from module-level _lifespan_state since FastMCP
    lifespans don't share context during execution.

    Yields:
        Dict with 'instructions_updated' flag
    """
    logger.info("📋 Dynamic instructions lifespan: Updating instructions...")

    # Get qdrant from module-level state (set by qdrant_lifespan)
    qdrant_middleware = _lifespan_state.get("qdrant_middleware")

    instructions_updated = False
    try:
        from tools.dynamic_instructions import update_mcp_instructions

        success = await update_mcp_instructions(server, qdrant_middleware)
        if success:
            logger.info("✅ Dynamic instructions updated from Qdrant analytics")
            instructions_updated = True
        else:
            logger.warning("⚠️ Dynamic instructions update returned False")
    except Exception as e:
        logger.warning(f"⚠️ Could not update dynamic instructions: {e}")
        logger.info("   Using static base instructions as fallback")

    try:
        yield {"instructions_updated": instructions_updated}
    finally:
        # Clear module-level lifespan state to break reference cycles.
        # This lifespan exits first (rightmost in composition), so clearing here
        # ensures middleware references don't pin objects in memory after shutdown.
        logger.info("🧹 Clearing module-level lifespan state...")
        _lifespan_state.clear()

        # Force a garbage collection cycle to reclaim any reference cycles
        # that were broken by clearing the state above (e.g., middleware objects
        # holding references to each other via _lifespan_state).
        collected = gc.collect()
        if collected:
            logger.info(
                f"🗑️ GC collected {collected} unreachable objects during shutdown"
            )


def register_profile_middleware(middleware: Any) -> None:
    """
    Register the profile middleware instance for cache cleanup.

    Call this from server.py after creating ProfileEnrichmentMiddleware
    to enable cache cleanup on shutdown.

    Args:
        middleware: ProfileEnrichmentMiddleware instance
    """
    # Initialize cache_middleware_refs if not set yet (registration happens before lifespan runs)
    if "cache_middleware_refs" not in _lifespan_state:
        _lifespan_state["cache_middleware_refs"] = {
            "template_middleware": None,
            "profile_middleware": None,
        }
    _lifespan_state["cache_middleware_refs"]["profile_middleware"] = middleware
    logger.debug("Registered profile middleware for lifespan cache cleanup")


def register_template_middleware(middleware: Any) -> None:
    """
    Register the template middleware instance for cache cleanup.

    Call this from server.py after creating EnhancedTemplateMiddleware
    to enable cache cleanup on shutdown.

    Args:
        middleware: EnhancedTemplateMiddleware instance
    """
    # Initialize cache_middleware_refs if not set yet (registration happens before lifespan runs)
    if "cache_middleware_refs" not in _lifespan_state:
        _lifespan_state["cache_middleware_refs"] = {
            "template_middleware": None,
            "profile_middleware": None,
        }
    _lifespan_state["cache_middleware_refs"]["template_middleware"] = middleware
    logger.debug("Registered template middleware for lifespan cache cleanup")


def get_lifespan_state() -> Dict[str, Any]:
    """
    Get the current lifespan state for debugging/testing.

    Returns:
        Current module-level lifespan state dict
    """
    return _lifespan_state.copy()


# Pre-composed lifespan for the full server lifecycle using FastMCP's | operator
# Composition order: enter left-to-right, exit right-to-left
combined_server_lifespan = (
    qdrant_lifespan
    | colbert_lifespan
    | session_state_lifespan
    | cache_middleware_lifespan
    | dynamic_instructions_lifespan
)


# Export for use in server.py
__all__ = [
    "qdrant_lifespan",
    "colbert_lifespan",
    "session_state_lifespan",
    "cache_middleware_lifespan",
    "dynamic_instructions_lifespan",
    "combined_server_lifespan",
    "register_profile_middleware",
    "register_template_middleware",
    "get_lifespan_state",
]
