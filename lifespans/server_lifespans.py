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

import asyncio
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


# =========================================================================
# Memory monitoring & watchdog configuration
# =========================================================================
# Docker limit is 2G; trigger graceful shutdown at 75% to capture diagnostics
# before an opaque OOM kill. Configurable via env vars.
import os

_MEMORY_LIMIT_MB = int(os.getenv("MEMORY_LIMIT_MB", "2048"))
_MEMORY_WARN_PCT = float(os.getenv("MEMORY_WARN_PCT", "0.65"))
_MEMORY_CRITICAL_PCT = float(os.getenv("MEMORY_CRITICAL_PCT", "0.75"))
_CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "300"))

_WARN_THRESHOLD_MB = int(_MEMORY_LIMIT_MB * _MEMORY_WARN_PCT)
_CRITICAL_THRESHOLD_MB = int(_MEMORY_LIMIT_MB * _MEMORY_CRITICAL_PCT)


def _has_running_loop() -> bool:
    """Check if there's a running asyncio event loop."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _get_rss_mb() -> float:
    """Current process RSS in MB."""
    import psutil

    return psutil.Process().memory_info().rss / (1024 * 1024)


def _get_process_health() -> Dict[str, Any]:
    """Snapshot of process-level health metrics."""
    import psutil

    proc = psutil.Process()
    with proc.oneshot():
        mem = proc.memory_info()
        return {
            "rss_mb": round(mem.rss / (1024 * 1024), 1),
            "vms_mb": round(mem.vms / (1024 * 1024), 1),
            "cpu_pct": proc.cpu_percent(interval=None),
            "num_fds": proc.num_fds() if hasattr(proc, "num_fds") else -1,
            "num_threads": proc.num_threads(),
            "asyncio_tasks": len(asyncio.all_tasks()) if _has_running_loop() else -1,
        }


def _dump_diagnostics(reason: str) -> None:
    """Dump memory diagnostics to logs for post-mortem analysis."""
    import tracemalloc

    import objgraph

    logger.warning(f"=== MEMORY DIAGNOSTICS ({reason}) ===")

    # objgraph: what object types are growing
    growth = objgraph.growth(limit=20)
    if growth:
        logger.warning("Top growing object types:")
        for type_name, count, delta in growth:
            logger.warning(f"  {type_name}: {count} (+{delta})")

    # tracemalloc: top allocating code locations
    if tracemalloc.is_tracing():
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")[:15]
        logger.warning("Top memory allocations by line:")
        for stat in top_stats:
            logger.warning(f"  {stat}")

    # GC stats
    gc_stats = gc.get_stats()
    logger.warning(f"GC stats: {gc_stats}")

    # Process health
    health = _get_process_health()
    logger.warning(f"Process health: {health}")
    logger.warning(f"=== END DIAGNOSTICS ===")


def _gc_callback(phase: str, info: Dict[str, Any]) -> None:
    """GC callback to detect uncollectable reference cycles."""
    if phase == "stop" and info.get("uncollectable", 0) > 0:
        logger.warning(
            f"GC found {info['uncollectable']} uncollectable objects "
            f"(generation {info['generation']}) — possible reference cycle leak"
        )


async def _periodic_memory_cleanup(
    interval_seconds: float = _CLEANUP_INTERVAL,
    shutdown_event: Optional[asyncio.Event] = None,
) -> None:
    """Background task: cleans stale data, monitors RSS, triggers watchdog."""
    import objgraph

    # Prime objgraph baseline (first call returns everything, subsequent calls show deltas)
    objgraph.growth(limit=0)

    cycle_count = 0

    while True:
        await asyncio.sleep(interval_seconds)
        cycle_count += 1
        try:
            cleaned_items = 0

            # --- Cache & session cleanup (from Fix 1-3) ---

            # 1. Tool relationship graph — stale sessions
            qdrant_mw = _lifespan_state.get("qdrant_middleware")
            if qdrant_mw is not None:
                graph = getattr(qdrant_mw, "_tool_relationship_graph", None)
                if graph is not None:
                    cleaned_items += graph.cleanup_stale_sessions(max_age_seconds=3600)

            # 2. Template cache — expired entries
            cache_refs = _lifespan_state.get("cache_middleware_refs", {})
            template_mw = cache_refs.get("template_middleware")
            if template_mw is not None:
                try:
                    cm = getattr(template_mw, "cache_manager", None)
                    if cm is not None:
                        cleaned_items += cm.cleanup_expired_entries()
                except Exception:
                    pass

            # 3. Profile cache — expired entries
            profile_mw = cache_refs.get("profile_middleware")
            if profile_mw is not None:
                try:
                    cleaned_items += profile_mw.cleanup_expired_entries()
                except Exception:
                    pass

            if cleaned_items > 0:
                logger.info(f"Periodic cleanup: {cleaned_items} items removed")

            # --- Tier 1: Process health & RSS monitoring ---

            rss_mb = _get_rss_mb()

            # Log health every 6th cycle (~30 min at 5min interval) or when elevated
            if cycle_count % 6 == 0 or rss_mb > _WARN_THRESHOLD_MB:
                health = _get_process_health()
                logger.info(f"Process health: {health}")

            # objgraph growth check every 3rd cycle (~15 min)
            if cycle_count % 3 == 0:
                growth = objgraph.growth(limit=10)
                if growth:
                    notable = [(t, c, d) for t, c, d in growth if d > 100]
                    if notable:
                        logger.warning(
                            f"Object growth: "
                            + ", ".join(f"{t}(+{d})" for t, _, d in notable)
                        )

            # --- Watchdog: memory threshold checks ---

            if rss_mb > _CRITICAL_THRESHOLD_MB:
                _dump_diagnostics(
                    f"RSS {rss_mb:.0f}MB exceeds critical threshold "
                    f"{_CRITICAL_THRESHOLD_MB}MB ({_MEMORY_CRITICAL_PCT:.0%} of {_MEMORY_LIMIT_MB}MB)"
                )
                logger.error(
                    f"RSS {rss_mb:.0f}MB exceeds critical threshold — "
                    f"signaling graceful shutdown"
                )
                if shutdown_event:
                    shutdown_event.set()
                    return

            elif rss_mb > _WARN_THRESHOLD_MB:
                logger.warning(
                    f"RSS {rss_mb:.0f}MB exceeds warning threshold "
                    f"{_WARN_THRESHOLD_MB}MB ({_MEMORY_WARN_PCT:.0%} of {_MEMORY_LIMIT_MB}MB)"
                )

        except Exception as e:
            logger.warning(f"Periodic memory cleanup error: {e}")


@lifespan
async def memory_cleanup_lifespan(server: Any):
    """
    Periodic memory cleanup & monitoring lifecycle.

    Integrates:
    - Cache/session cleanup (every 5 min)
    - psutil RSS/FD/CPU tracking (every 30 min, or when elevated)
    - objgraph.growth() leak detection (every 15 min)
    - gc.callbacks for uncollectable reference cycles
    - aiodebug slow event-loop callback detection
    - aiomonitor async task inspector (localhost:20101)
    - Watchdog: at 75% of MEMORY_LIMIT_MB, dump diagnostics + graceful shutdown

    Yields:
        Dict with 'memory_cleanup_active' flag
    """
    import tracemalloc

    # --- Tier 1: tracemalloc (1-frame, low overhead) ---
    if not tracemalloc.is_tracing():
        tracemalloc.start(1)
        logger.info(f"Memory monitoring: tracemalloc started (nframe=1)")

    # --- Tier 1: GC callback for uncollectable cycles ---
    gc.callbacks.append(_gc_callback)

    # --- Tier 2: aiodebug slow callback detection ---
    aiomonitor_ctx = None
    try:
        import aiodebug.log_slow_callbacks

        aiodebug.log_slow_callbacks.enable(0.1)  # warn if callback takes >100ms
        logger.info(
            "Memory monitoring: aiodebug slow callback detection enabled (>100ms)"
        )
    except Exception as e:
        logger.warning(f"aiodebug setup skipped: {e}")

    # --- Tier 2: aiomonitor task inspector ---
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Importing 'parser.split_arg_string'",
                category=DeprecationWarning,
            )
            import aiomonitor

        loop = asyncio.get_running_loop()
        aiomonitor_ctx = aiomonitor.start_monitor(loop, host="127.0.0.1", port=20101)
        monitor = aiomonitor_ctx.__enter__()
        logger.info("Memory monitoring: aiomonitor started on 127.0.0.1:20101")
    except Exception as e:
        logger.warning(f"aiomonitor setup skipped: {e}")
        aiomonitor_ctx = None

    # --- Shutdown event for watchdog ---
    shutdown_event = asyncio.Event()

    # --- Start the periodic cleanup + monitoring task ---
    cleanup_task = asyncio.create_task(
        _periodic_memory_cleanup(shutdown_event=shutdown_event)
    )

    rss_mb = _get_rss_mb()
    logger.info(
        f"Memory monitoring active: RSS={rss_mb:.0f}MB, "
        f"warn={_WARN_THRESHOLD_MB}MB, critical={_CRITICAL_THRESHOLD_MB}MB, "
        f"limit={_MEMORY_LIMIT_MB}MB"
    )

    # --- Watchdog shutdown listener ---
    async def _watchdog_shutdown():
        await shutdown_event.wait()
        logger.error("Watchdog triggered — initiating server shutdown")
        # Raise SystemExit to trigger lifespan cleanup chain
        os._exit(1)

    watchdog_task = asyncio.create_task(_watchdog_shutdown())

    try:
        yield {"memory_cleanup_active": True}
    finally:
        # Cancel background tasks
        cleanup_task.cancel()
        watchdog_task.cancel()
        for t in (cleanup_task, watchdog_task):
            try:
                await t
            except asyncio.CancelledError:
                pass

        # Cleanup aiomonitor
        if aiomonitor_ctx is not None:
            try:
                aiomonitor_ctx.__exit__(None, None, None)
            except Exception:
                pass

        # Remove GC callback
        try:
            gc.callbacks.remove(_gc_callback)
        except ValueError:
            pass

        # Stop tracemalloc
        if tracemalloc.is_tracing():
            tracemalloc.stop()

        logger.info("Memory monitoring stopped")


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
    | memory_cleanup_lifespan
    | dynamic_instructions_lifespan
)


# Export for use in server.py
__all__ = [
    "qdrant_lifespan",
    "colbert_lifespan",
    "session_state_lifespan",
    "cache_middleware_lifespan",
    "memory_cleanup_lifespan",
    "dynamic_instructions_lifespan",
    "combined_server_lifespan",
    "register_profile_middleware",
    "register_template_middleware",
    "get_lifespan_state",
]
