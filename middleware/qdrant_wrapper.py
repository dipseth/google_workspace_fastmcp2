"""
Simple wrapper for Qdrant middleware to ensure it doesn't block server startup.
"""

import asyncio
import logging
import time
from typing_extensions import Any, Dict, Optional
from datetime import datetime

from fastmcp.server.middleware import Middleware, MiddlewareContext
from auth.context import get_session_context

logger = logging.getLogger(__name__)


class QdrantMiddlewareWrapper(Middleware):
    """
    Wrapper that ensures Qdrant middleware doesn't block server startup.
    All initialization is deferred to first use.
    """
    
    def __init__(self):
        self._inner_middleware = None
        self._init_task = None
        self._init_complete = False
        self._init_attempted = False
        
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Intercept tool calls to store responses in Qdrant.
        
        Args:
            context: Middleware context containing tool information
            call_next: Function to call the next middleware/handler
        """
        # Initialize on first tool call if not already done
        if not self._init_attempted:
            await self._ensure_initialized()
        
        # If no middleware available, just pass through
        if self._inner_middleware is None:
            return await call_next(context)
        
        # Extract tool information
        tool_name = getattr(context.message, 'name', 'unknown')
        tool_args = getattr(context.message, 'arguments', {})
        
        # Record start time
        start_time = time.time()
        
        try:
            # Execute the tool
            result = await call_next(context)
            
            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Extract user email from args if available
            user_email = None
            for param_name in ['user_email', 'user_google_email', 'email', 'google_email']:
                if param_name in tool_args:
                    user_email = tool_args[param_name]
                    break
            
            # Get session_id from context
            session_id = get_session_context()
            
            # Store response in Qdrant asynchronously
            logger.info(f"📝 Storing response for tool: {tool_name}")
            asyncio.create_task(self._store_response(
                tool_name=tool_name,
                tool_args=tool_args,
                response=result,
                execution_time_ms=execution_time_ms,
                session_id=session_id,
                user_email=user_email
            ))
            
            return result
            
        except Exception as e:
            logger.error(f"Error in tool execution: {e}")
            raise
    
    async def _ensure_initialized(self):
        """Initialize the inner middleware on first use."""
        if self._init_attempted:
            return
        
        self._init_attempted = True
        
        try:
            logger.info("🔄 Initializing Qdrant middleware on first tool call...")
            from .qdrant_unified import QdrantUnifiedMiddleware as EnhancedQdrantResponseMiddleware
            
            # Create the middleware
            self._inner_middleware = EnhancedQdrantResponseMiddleware()
            
            # Initialize it
            await self._inner_middleware.initialize()
            
            logger.info("✅ Qdrant middleware initialized successfully")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize Qdrant middleware: {e}")
            self._inner_middleware = None
    
    async def _store_response(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        response: Any,
        execution_time_ms: int,
        session_id: Optional[str] = None,
        user_email: Optional[str] = None
    ):
        """Store the tool response in Qdrant."""
        if self._inner_middleware is None:
            return
        
        try:
            # Use the inner middleware's storage method
            await self._inner_middleware._store_response(
                tool_name=tool_name,
                tool_args=tool_args,
                response=response,
                execution_time_ms=execution_time_ms,
                session_id=session_id,
                user_email=user_email
            )
            logger.info(f"✅ Successfully stored response for {tool_name} in Qdrant")
        except Exception as e:
            logger.error(f"❌ Failed to store response in Qdrant: {e}")