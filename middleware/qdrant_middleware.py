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

import json
import logging
import time
import asyncio
from datetime import datetime, timezone
from typing_extensions import Any, Dict, Optional, List
from fastmcp.server.middleware import Middleware, MiddlewareContext
from auth.context import get_session_context

# Import qdrant_core modules
from middleware.qdrant_core.config import QdrantConfig
from middleware.qdrant_core.client import QdrantClientManager
from middleware.qdrant_core.storage import QdrantStorageManager
from middleware.qdrant_core.search import QdrantSearchManager
from middleware.qdrant_core.resource_handler import QdrantResourceHandler

# Re-export tools and resources for backward compatibility
from middleware.qdrant_core.tools import setup_enhanced_qdrant_tools
from middleware.qdrant_core.resources import setup_qdrant_resources

from config.enhanced_logging import setup_logger

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
        ports: Optional[List[int]] = None
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
        self.config = QdrantConfig(
            host=qdrant_host,
            ports=ports or [qdrant_port, 6333, 6335, 6334],
            collection_name=collection_name,
            embedding_model=embedding_model,
            summary_max_tokens=summary_max_tokens,
            verbose_param=verbose_param,
            enabled=enabled,
            compression_threshold=compression_threshold
        )
        
        # Initialize managers
        self.client_manager = QdrantClientManager(
            config=self.config,
            qdrant_api_key=qdrant_api_key,
            qdrant_url=qdrant_url,
            auto_discovery=auto_discovery
        )
        
        self.storage_manager = QdrantStorageManager(self.client_manager)
        self.search_manager = QdrantSearchManager(self.client_manager)
        self.resource_handler = QdrantResourceHandler(self.client_manager, self.search_manager)
        
        # Store original parameters for compatibility
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.qdrant_api_key = qdrant_api_key
        self.qdrant_url = qdrant_url
        self.auto_discovery = auto_discovery
        
        # Legacy compatibility properties (delegate to managers)
        self._initialized = False
        
        logger.info("🚀 Qdrant Unified Middleware created (delegating to qdrant_core managers)")
        if not self.config.enabled:
            logger.warning("⚠️ Qdrant middleware disabled by configuration")
        else:
            # Track if we've attempted early background initialization
            self._early_init_started = False
    
    async def initialize(self):
        """
        Initialize async components (embedding model, auto-discovery).
        This method can be called explicitly or will be called on first tool use.
        """
        success = await self.client_manager.initialize()
        self._initialized = success
        return success
    
    async def _ensure_initialization(self, context_name: str = "unknown"):
        """
        Ensure Qdrant is initialized, starting background initialization if needed.
        This is called from various hooks to ensure initialization happens early.
        """
        if not self._early_init_started and self.config.enabled:
            self._early_init_started = True
            logger.info(f"🚀 Starting background Qdrant initialization from {context_name} (embedding model loading)")
            # Start initialization in background - don't wait for it
            asyncio.create_task(self.client_manager.initialize())
    
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
        # Initialize on first tool call if not already done
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        # If no client available, just pass through
        if not self.client_manager.is_available:
            return await call_next(context)
        
        # Extract tool information
        tool_name = getattr(context.message, 'name', 'unknown')
        tool_args = getattr(context.message, 'arguments', {})
        
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
                user_email = get_user_email_context()
                if user_email:
                    logger.debug(f"📧 User email from auth context: {user_email}")
            except Exception as e:
                logger.debug(f"Could not get user email from auth context: {e}")
            
            # Fallback to tool arguments if not found in auth context
            if not user_email:
                for param_name in ['user_email', 'user_google_email', 'email', 'google_email']:
                    if param_name in tool_args:
                        user_email = tool_args[param_name]
                        logger.debug(f"📧 User email from tool args ({param_name}): {user_email}")
                        break
            
            # Get session_id from context
            session_id = get_session_context()
            
            # Store response in Qdrant asynchronously (non-blocking via storage manager)
            logger.info(f"📝 Storing response for tool: {tool_name}")
            asyncio.create_task(self.storage_manager._store_response_with_params(
                tool_name=tool_name,
                tool_args=tool_args,
                response=response,
                execution_time_ms=execution_time_ms,
                session_id=session_id,
                user_email=user_email
            ))
            
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
        
        # Initialize synchronously for resource reads to ensure data availability
        if not self.client_manager.is_initialized:
            logger.info("🔄 Initializing Qdrant synchronously for resource access...")
            await self.client_manager.initialize()
        
        # Process Qdrant resources via resource handler and cache results
        try:
            result = await self.resource_handler.handle_qdrant_resource(uri, context)
            
            # Cache the result for the registered resource handlers to access
            cache_key = f"qdrant_resource_{uri}"
            if hasattr(context, 'set_state'):
                context.set_state(cache_key, result)
                logger.debug(f"🔍 Cached Qdrant resource result for key: {cache_key}")
            
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
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
            # Cache the error response for the resource handler
            cache_key = f"qdrant_resource_{uri}"
            if hasattr(context, 'set_state'):
                context.set_state(cache_key, error_response)
            
            # Let the registered resource handler process with cached error
            return await call_next(context)
    
    # Public API methods that delegate to managers
    async def search(self, query: str, limit: int = None, score_threshold: float = None) -> List[Dict]:
        """Advanced search with query parsing support (delegates to search manager)."""
        return await self.search_manager.search(query, limit, score_threshold)
    
    async def search_responses(self, query: str, filters: Dict = None, limit: int = 10) -> List[Dict]:
        """Search stored responses with optional filters (delegates to search manager)."""
        return await self.search_manager.search_responses(query, filters, limit)
    
    async def get_analytics(self, start_date=None, end_date=None, group_by="tool_name") -> Dict:
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
    
    async def _store_response_with_params(self, tool_name: str, tool_args: Dict[str, Any], response: Any, 
                                         execution_time_ms: int = 0, session_id: Optional[str] = None, 
                                         user_email: Optional[str] = None):
        """Store tool response with parameters (delegates to storage manager)."""
        return await self.storage_manager._store_response_with_params(
            tool_name, tool_args, response, execution_time_ms, session_id, user_email
        )


# Backward compatibility aliases
QdrantResponseMiddleware = QdrantUnifiedMiddleware
EnhancedQdrantResponseMiddleware = QdrantUnifiedMiddleware

# Re-export the tools and resources setup functions
__all__ = [
    'QdrantUnifiedMiddleware',
    'QdrantResponseMiddleware',
    'EnhancedQdrantResponseMiddleware',
    'setup_enhanced_qdrant_tools',
    'setup_qdrant_resources'
]