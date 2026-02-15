#!/usr/bin/env python3
"""
Unified Qdrant Middleware for FastMCP (Refactored)

This module provides a comprehensive Qdrant middleware implementation that combines:
- Deferred initialization for non-blocking server startup
- Enhanced user email extraction with priority-based fallbacks
- Execution time tracking and performance monitoring
- Full vector search capabilities with semantic understanding
- Automatic compression for large payloads
- Auto-discovery of Qdrant instances across multiple ports
- Resource system integration for cached data access
- Analytics and reporting capabilities

The refactored approach delegates core functionality to specialized managers from
the qdrant_core package for better separation of concerns and maintainability.
"""

import asyncio
import time
from datetime import datetime, timezone

from fastmcp.server.middleware import Middleware, MiddlewareContext
from typing_extensions import Any, Dict, List, Optional

from auth.context import get_session_context
from config.enhanced_logging import setup_logger
from middleware.qdrant_core.client import get_or_create_client_manager

# Import qdrant_core modules
from middleware.qdrant_core.config import QdrantConfig
from middleware.qdrant_core.resource_handler import QdrantResourceHandler
from middleware.qdrant_core.resources import setup_qdrant_resources
from middleware.qdrant_core.search import QdrantSearchManager
from middleware.qdrant_core.storage import QdrantStorageManager

# Re-export tools and resources for backward compatibility
from middleware.qdrant_core.tools import setup_enhanced_qdrant_tools

logger = setup_logger()


class QdrantUnifiedMiddleware(Middleware):
    """
    Unified Qdrant middleware that combines deferred initialization, enhanced user context
    extraction, execution time tracking, and comprehensive vector database functionality.

    This refactored version delegates core functionality to specialized managers:
    - QdrantClientManager: Connection management and model loading
    - QdrantStorageManager: Data storage and persistence
    - QdrantSearchManager: Search operations and analytics
    - QdrantResourceHandler: qdrant:// URI processing

    Key Features:
    - Non-blocking deferred initialization (prevents server startup delays)
    - Enhanced user email extraction with priority-based fallbacks
    - Automatic execution time tracking and performance monitoring
    - Comprehensive vector search capabilities with semantic understanding
    - Auto-discovery of Qdrant instances across multiple ports
    - Automatic compression for large payloads
    - Resource system integration for cached data access
    - Analytics and reporting capabilities

    This middleware intercepts all tool responses, stores them in a Qdrant
    vector database with embeddings, and provides advanced search capabilities.
    """

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        qdrant_api_key: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        collection_name: str = "mcp_tool_responses",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        summary_max_tokens: int = 500,
        verbose_param: str = "verbose",
        enabled: bool = True,
        compression_threshold: int = 5120,
        auto_discovery: bool = True,
        ports: Optional[List[int]] = None,
    ):
        """
        Initialize the unified Qdrant middleware with deferred initialization.

        Args:
            qdrant_host: Qdrant server hostname
            qdrant_port: Primary Qdrant server port
            qdrant_api_key: API key for cloud Qdrant authentication
            qdrant_url: Full Qdrant URL (if provided, overrides host/port)
            collection_name: Name of the collection to store responses
            embedding_model: Model to use for generating embeddings
            summary_max_tokens: Maximum tokens in summarized response
            verbose_param: Parameter name to check for verbose mode
            enabled: Whether the middleware is enabled
            compression_threshold: Minimum size (bytes) to compress payloads
            auto_discovery: Whether to auto-discover Qdrant ports
            ports: List of ports to try for auto-discovery
        """
        # Create configuration
        # Use centralized configuration from settings
        try:
            from middleware.qdrant_core.config import load_config_from_settings

            self.config = load_config_from_settings()
        except ImportError:
            # Fallback to direct creation if settings not available
            self.config = QdrantConfig()

        # Override with explicitly provided parameters
        if qdrant_host:
            self.config.host = qdrant_host
        if ports:
            self.config.ports = ports
        elif qdrant_port:
            self.config.ports = [qdrant_port, 6333, 6335, 6334]
        if collection_name:
            self.config.collection_name = collection_name
        if embedding_model:
            self.config.embedding_model = embedding_model
        if summary_max_tokens:
            self.config.summary_max_tokens = summary_max_tokens
        if verbose_param:
            self.config.verbose_param = verbose_param
        if enabled is not None:
            self.config.enabled = enabled
        if compression_threshold:
            self.config.compression_threshold = compression_threshold

        # Initialize managers using a shared singleton client manager
        self.client_manager = get_or_create_client_manager(
            config=self.config,
            qdrant_api_key=qdrant_api_key,
            qdrant_url=qdrant_url,
            auto_discovery=auto_discovery,
        )

        self.storage_manager = QdrantStorageManager(self.client_manager)
        self.search_manager = QdrantSearchManager(self.client_manager)
        self.resource_handler = QdrantResourceHandler(
            self.client_manager, self.search_manager
        )

        # Store original parameters for compatibility
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.qdrant_api_key = qdrant_api_key
        self.qdrant_url = qdrant_url
        self.auto_discovery = auto_discovery

        # Legacy compatibility properties (delegate to managers)
        self._initialized = False

        logger.info(
            "🚀 Qdrant Unified Middleware created (delegating to qdrant_core managers)"
        )
        logger.debug(f"📊 Initialization state - enabled: {self.config.enabled}")
        if not self.config.enabled:
            logger.warning("⚠️ Qdrant middleware disabled by configuration")
        else:
            logger.debug(
                "✅ Qdrant middleware enabled - initializing control variables"
            )
            # Track if we've attempted early background initialization
            self._early_init_started = False
            logger.debug(f"📊 Set _early_init_started = {self._early_init_started}")

            # Background reindexing control
            self._reindexing_task = None
            self._reindexing_enabled = True
            logger.debug(
                f"📊 Reindexing controls initialized - enabled: {self._reindexing_enabled}, task: {self._reindexing_task}"
            )

    async def initialize_middleware_and_reindexing(self):
        """
        Initialize middleware with full async components (embedding model, auto-discovery, reindexing).
        This method performs complete middleware initialization including background reindexing scheduler.
        Should be called on first tool use to ensure all middleware features are active.
        """
        logger.info(
            "🔄 Middleware initialization called - starting full async component initialization"
        )
        success = await self.client_manager.initialize()
        self._initialized = success
        logger.debug(f"📊 Client manager initialization result: {success}")

        # Start background reindexing scheduler if initialization successful
        if success and self._reindexing_enabled:
            logger.info("✅ Starting background reindexing scheduler...")
            await self._start_background_reindexing()
        else:
            logger.debug(
                f"⏹️ Background reindexing not started - success: {success}, enabled: {getattr(self, '_reindexing_enabled', False)}"
            )

        return success

    async def initialize(self):
        """
        Backward compatibility method - delegates to the more specific initialization method.
        Use initialize_middleware_and_reindexing() for clarity in new code.
        """
        logger.debug(
            "🔄 Legacy initialize() called - delegating to initialize_middleware_and_reindexing()"
        )
        return await self.initialize_middleware_and_reindexing()

    async def _ensure_initialization(self, context_name: str = "unknown"):
        """
        Ensure Qdrant is initialized, starting background initialization if needed.
        This is called from various hooks to ensure initialization happens early.
        """
        if not self._early_init_started and self.config.enabled:
            self._early_init_started = True
            logger.info(
                f"🚀 Starting background middleware initialization from {context_name} (embedding model and reindexing)"
            )
            # Start full middleware initialization in background - don't wait for it
            asyncio.create_task(self.initialize_middleware_and_reindexing())

    async def on_list_tools(self, context, call_next):
        """
        FastMCP hook for tool listing - triggers background initialization.
        This ensures embedding model loads early without blocking the response.
        """
        await self._ensure_initialization("on_list_tools")
        return await call_next(context)

    async def on_list_resources(self, context, call_next):
        """
        FastMCP hook for resource listing - triggers background initialization.
        This ensures Qdrant is ready when resources are listed.
        """
        await self._ensure_initialization("on_list_resources")
        return await call_next(context)

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        FastMCP2 middleware hook for intercepting tool calls.

        This method incorporates enhanced functionality:
        - Deferred initialization on first tool call
        - Enhanced user email extraction with priority fallbacks
        - Execution time tracking
        - Non-blocking async response storage via storage manager
        """
        # Initialize middleware and reindexing on first tool call if not already done
        if not self.client_manager.is_initialized:
            await self.initialize_middleware_and_reindexing()

        # If no client available, just pass through
        if not self.client_manager.is_available:
            return await call_next(context)

        # Extract tool information
        tool_name = context.message.name
        tool_args = context.message.arguments or {}

        # Record start time for execution tracking
        start_time = time.time()

        try:
            # Execute the tool
            response = await call_next(context)

            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Enhanced user email extraction with priority order
            user_email = None

            # Try to get from auth context first (most reliable)
            try:
                from auth.context import get_user_email_context

                user_email = await get_user_email_context()
                if user_email:
                    logger.debug(f"📧 User email from auth context: {user_email}")
            except Exception as e:
                logger.debug(f"Could not get user email from auth context: {e}")

            # Fallback to tool arguments if not found in auth context
            if not user_email:
                for param_name in [
                    "user_email",
                    "user_google_email",
                    "email",
                    "google_email",
                ]:
                    if param_name in tool_args:
                        user_email = tool_args[param_name]
                        logger.debug(
                            f"📧 User email from tool args ({param_name}): {user_email}"
                        )
                        break

            # Get session_id from context
            session_id = await get_session_context()

            # Store response in Qdrant asynchronously (non-blocking via storage manager)
            logger.info(f"📝 Storing response for tool: {tool_name}")
            asyncio.create_task(
                self.storage_manager._store_response_with_params(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    response=response,
                    execution_time_ms=execution_time_ms,
                    session_id=session_id,
                    user_email=user_email,
                )
            )

            return response

        except Exception as e:
            logger.error(f"Error in tool execution: {e}")
            raise

    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """
        FastMCP2 middleware hook for intercepting resource reads.
        Process Qdrant resources and cache results for registered resource handlers.
        """
        # Check if this is a Qdrant resource
        # Convert AnyUrl to string before using string methods
        uri = str(context.message.uri) if context.message.uri else ""

        if not uri.startswith("qdrant://"):
            # Not a Qdrant resource, let other handlers deal with it
            return await call_next(context)

        # Ensure initialization for Qdrant resources
        await self._ensure_initialization("on_read_resource")

        # Initialize middleware synchronously for resource reads to ensure data availability
        if not self.client_manager.is_initialized:
            logger.info(
                "🔄 Initializing middleware synchronously for resource access..."
            )
            await self.initialize_middleware_and_reindexing()

        # Process Qdrant resources via resource handler and cache results
        try:
            result = await self.resource_handler.handle_qdrant_resource(uri, context)

            # Cache the result for the registered resource handlers to access
            # Use FastMCP context pattern (same as TagBasedResourceMiddleware)
            cache_key = f"qdrant_resource_{uri}"
            if context.fastmcp_context:
                await context.fastmcp_context.set_state(cache_key, result)
                logger.info(f"✅ Cached Qdrant resource result for key: {cache_key}")
                logger.debug(f"📦 Cached result type: {type(result).__name__}")

                # Verify the cache was set
                verify = await context.fastmcp_context.get_state(cache_key)
                if verify is None:
                    logger.error(
                        "❌ Cache verification FAILED - value not found immediately after set_state!"
                    )
                else:
                    logger.debug(
                        f"✓ Cache verification SUCCESS - value found: {type(verify).__name__}"
                    )
            else:
                logger.warning("⚠️ Context does not have fastmcp_context!")

            # Let the registered resource handlers process the request with cached data
            return await call_next(context)

        except Exception as e:
            logger.error(f"❌ Failed to process Qdrant resource {uri}: {e}")
            # Import the error response type
            from middleware.qdrant_types import QdrantErrorResponse

            # Create error response
            error_response = QdrantErrorResponse(
                error=f"Failed to process Qdrant resource: {str(e)}",
                uri=uri,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            # Cache the error response for the resource handler
            cache_key = f"qdrant_resource_{uri}"
            if hasattr(context, "set_state"):
                await context.set_state(cache_key, error_response)

            # Let the registered resource handler process with cached error
            return await call_next(context)

    # Public API methods that delegate to managers
    async def search(
        self, query: str, limit: int = None, score_threshold: float = None
    ) -> List[Dict]:
        """Advanced search with query parsing support (delegates to search manager)."""
        return await self.search_manager.search(query, limit, score_threshold)

    async def search_responses(
        self, query: str, filters: Dict = None, limit: int = 10
    ) -> List[Dict]:
        """Search stored responses with optional filters (delegates to search manager)."""
        return await self.search_manager.search_responses(query, filters, limit)

    async def get_analytics(
        self, start_date=None, end_date=None, group_by="tool_name"
    ) -> Dict:
        """Get analytics on stored tool responses (delegates to search manager)."""
        return await self.search_manager.get_analytics(start_date, end_date, group_by)

    async def get_response_by_id(self, response_id: str) -> Optional[Dict]:
        """Get a specific response by its ID (delegates to search manager)."""
        return await self.search_manager.get_response_by_id(response_id)

    # Legacy compatibility properties
    @property
    def is_initialized(self) -> bool:
        """Check if middleware is fully initialized."""
        return self.client_manager.is_initialized

    @property
    def client(self):
        """Access to Qdrant client (delegates to client manager)."""
        return self.client_manager.client

    @property
    def embedder(self):
        """Access to embedding model (delegates to client manager)."""
        return self.client_manager.embedder

    @property
    def discovered_url(self):
        """Access to discovered Qdrant URL (delegates to client manager)."""
        return self.client_manager.discovered_url

    # Storage methods that delegate to storage manager
    async def _store_response(self, context=None, response=None, **kwargs):
        """Store tool response (delegates to storage manager)."""
        return await self.storage_manager.store_response(context, response, **kwargs)

    async def _store_response_with_params(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        response: Any,
        execution_time_ms: int = 0,
        session_id: Optional[str] = None,
        user_email: Optional[str] = None,
    ):
        """Store tool response with parameters (delegates to storage manager)."""
        return await self.storage_manager._store_response_with_params(
            tool_name, tool_args, response, execution_time_ms, session_id, user_email
        )

    async def _start_background_reindexing(self):
        """
        Start the background reindexing scheduler with intelligent frequency adjustment.

        This scheduler:
        - Monitors collection health every 6 hours
        - Performs automatic reindexing when needed
        - Adjusts reindexing frequency based on collection size and activity
        - Runs collection optimization during low-activity periods
        """
        if not self.config.enabled or not self.client_manager.is_available:
            logger.info("⏰ Background reindexing disabled (Qdrant not available)")
            return

        logger.info("⏰ Starting intelligent background reindexing scheduler...")

        async def background_reindexing_loop():
            """Main background reindexing loop with adaptive scheduling."""

            # Initial delay to let the system stabilize
            await asyncio.sleep(300)  # 5 minutes

            # Adaptive scheduling parameters
            base_interval_hours = 6  # Base check interval
            min_interval_hours = 2  # Minimum interval (high activity)
            max_interval_hours = 24  # Maximum interval (low activity)

            consecutive_healthy_checks = 0
            last_reindex_timestamp = None

            while True:
                try:
                    # Calculate adaptive interval based on collection health history
                    current_interval = base_interval_hours

                    if consecutive_healthy_checks > 5:
                        # Collection has been healthy for a while, reduce frequency
                        current_interval = min(
                            max_interval_hours, base_interval_hours * 2
                        )
                    elif consecutive_healthy_checks < 2:
                        # Collection needs frequent monitoring
                        current_interval = max(
                            min_interval_hours, base_interval_hours // 2
                        )

                    logger.debug(
                        f"🔄 Next reindexing check in {current_interval} hours (healthy checks: {consecutive_healthy_checks})"
                    )
                    await asyncio.sleep(current_interval * 3600)  # Convert to seconds

                    logger.info("🏥 Running scheduled collection health check...")

                    # Analyze collection health via storage manager
                    health_stats = (
                        await self.storage_manager._analyze_collection_health()
                    )

                    if health_stats.get("needs_reindex", False):
                        reindex_reasons = health_stats.get("reindex_reasons", [])
                        logger.info(
                            f"🔧 Collection health check indicates reindexing needed: {reindex_reasons}"
                        )

                        # Determine reindexing strategy based on reasons
                        force_complete_rebuild = any(
                            reason.startswith("collection_growth")
                            or reason.startswith("high_fragmentation")
                            for reason in reindex_reasons
                        )

                        if force_complete_rebuild:
                            logger.info(
                                "🏗️ Performing complete collection rebuild due to significant changes"
                            )
                            result = (
                                await self.client_manager.rebuild_collection_completely()
                            )
                        else:
                            logger.info("🔧 Performing standard collection reindexing")
                            result = await self.storage_manager.reindex_collection(
                                force=False
                            )

                        if result.get("status") == "completed":
                            logger.info(
                                "✅ Scheduled reindexing completed successfully"
                            )
                            last_reindex_timestamp = datetime.now(timezone.utc)
                            consecutive_healthy_checks = (
                                0  # Reset counter after successful reindex
                            )

                            # Start background scheduler for storage manager periodic reindexing
                            await self.storage_manager.schedule_background_reindexing(
                                interval_hours=12
                            )

                        else:
                            logger.warning(f"⚠️ Scheduled reindexing result: {result}")
                            consecutive_healthy_checks = 0  # Reset on issues
                    else:
                        logger.debug("✅ Collection healthy, no reindexing needed")
                        consecutive_healthy_checks += 1

                        # Even for healthy collections, run light optimization periodically
                        hours_since_last_reindex = 48  # Default assumption
                        if last_reindex_timestamp:
                            hours_since_last_reindex = (
                                datetime.now(timezone.utc) - last_reindex_timestamp
                            ).total_seconds() / 3600

                        if (
                            hours_since_last_reindex > 72
                        ):  # 3 days since last optimization
                            logger.info(
                                "🚀 Running periodic collection optimization (preventive maintenance)"
                            )
                            result = (
                                await self.client_manager.optimize_collection_performance()
                            )

                            if result.get("status") == "completed":
                                logger.info("✅ Periodic optimization completed")
                                last_reindex_timestamp = datetime.now(timezone.utc)

                except asyncio.CancelledError:
                    logger.info("⏹️ Background reindexing scheduler cancelled")
                    break
                except Exception as e:
                    logger.warning(f"⚠️ Background reindexing error (will retry): {e}")
                    consecutive_healthy_checks = 0  # Reset on errors
                    # Continue the loop despite errors, with a short backoff
                    await asyncio.sleep(600)  # 10 minute backoff on errors

        # Start the background task
        self._reindexing_task = asyncio.create_task(background_reindexing_loop())
        logger.info("✅ Background reindexing scheduler started")

    async def stop_background_reindexing(self):
        """Stop the background reindexing scheduler gracefully."""
        if self._reindexing_task and not self._reindexing_task.done():
            logger.info("⏹️ Stopping background reindexing scheduler...")
            self._reindexing_task.cancel()
            try:
                await self._reindexing_task
            except asyncio.CancelledError:
                pass
            logger.info("✅ Background reindexing scheduler stopped")

    # Reindexing control methods
    async def trigger_immediate_reindexing(
        self, force_complete_rebuild: bool = False
    ) -> Dict[str, Any]:
        """
        Trigger immediate collection reindexing.

        Args:
            force_complete_rebuild: If True, perform complete collection rebuild

        Returns:
            Dict with reindexing results
        """
        if not self.client_manager.is_available:
            return {"status": "skipped", "reason": "client_unavailable"}

        logger.info("🚀 Triggering immediate collection reindexing...")

        if force_complete_rebuild:
            result = await self.client_manager.rebuild_collection_completely()
        else:
            result = await self.storage_manager.reindex_collection(force=True)

        logger.info(f"✅ Immediate reindexing result: {result.get('status')}")
        return result

    async def get_collection_health_status(self) -> Dict[str, Any]:
        """
        Get current collection health status and reindexing recommendations.

        Returns:
            Dict with health statistics and recommendations
        """
        if not self.client_manager.is_available:
            return {"status": "unavailable", "reason": "client_unavailable"}

        return await self.storage_manager._analyze_collection_health()


# Backward compatibility aliases
QdrantResponseMiddleware = QdrantUnifiedMiddleware
EnhancedQdrantResponseMiddleware = QdrantUnifiedMiddleware

# Re-export the tools and resources setup functions
__all__ = [
    "QdrantUnifiedMiddleware",
    "QdrantResponseMiddleware",
    "EnhancedQdrantResponseMiddleware",
    "setup_enhanced_qdrant_tools",
    "setup_qdrant_resources",
]
