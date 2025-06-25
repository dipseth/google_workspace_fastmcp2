"""Authentication middleware for session management and service injection."""

import logging
from datetime import datetime, timedelta
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from .context import (
    set_session_context,
    clear_session_context,
    clear_all_context,
    cleanup_expired_sessions,
    get_session_context,
    set_user_email_context,
    get_user_email_context,
    _get_pending_service_requests,
    _set_injected_service,
    _set_service_error
)
from .service_manager import get_google_service, GoogleServiceError
from config.settings import settings

logger = logging.getLogger(__name__)


class AuthMiddleware(Middleware):
    """Middleware for managing session context, cleanup, and service injection."""
    
    def __init__(self):
        self._last_cleanup = datetime.now()
        self._cleanup_interval_minutes = 30
        self._service_injection_enabled = True
    
    async def on_request(self, context: MiddlewareContext, call_next):
        """Handle incoming requests and set session context."""
        # Try to extract session ID from various possible locations
        session_id = None
        
        # Try FastMCP context first
        if hasattr(context, 'fastmcp_context') and context.fastmcp_context:
            session_id = getattr(context.fastmcp_context, 'session_id', None)
        
        # Try to get from headers or other context
        if not session_id and hasattr(context, 'request'):
            # Try to extract from request headers or similar
            session_id = getattr(context.request, 'session_id', None)
        
        # Generate a default session ID if none found
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            logger.debug(f"Generated default session ID: {session_id}")
        
        set_session_context(session_id)
        logger.debug(f"Set session context: {session_id}")
        
        # Periodic cleanup of expired sessions
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() > (self._cleanup_interval_minutes * 60):
            try:
                cleanup_expired_sessions(settings.session_timeout_minutes)
                self._last_cleanup = now
                logger.debug("Performed periodic session cleanup")
            except Exception as e:
                logger.error(f"Error during session cleanup: {e}")
        
        try:
            result = await call_next(context)
            return result
        except Exception as e:
            logger.error(f"Error in request processing: {e}")
            raise
        finally:
            # Always clear all context when done
            clear_all_context()
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Handle tool execution with session context and service injection.
        
        Args:
            context: MiddlewareContext containing tool call information
            call_next: Function to continue the middleware chain
        """
        tool_name = getattr(context.message, 'name', 'unknown')
        logger.debug(f"Processing tool call: {tool_name}")
        
        # Session context should already be set by on_request
        session_id = get_session_context()
        if not session_id:
            # Generate a session ID if missing
            import uuid
            session_id = str(uuid.uuid4())
            set_session_context(session_id)
            logger.debug(f"Generated session context for tool {tool_name}: {session_id}")
        
        # Extract user email from tool arguments for service injection
        user_email = self._extract_user_email(context)
        if user_email:
            set_user_email_context(user_email)
            logger.debug(f"Set user email context for tool {tool_name}: {user_email}")
        
        # Handle service injection if enabled
        if self._service_injection_enabled:
            await self._inject_services(tool_name, user_email)
        
        try:
            result = await call_next(context)
            logger.debug(f"Tool {tool_name} executed successfully")
            return result
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            raise
    
    def _extract_user_email(self, context: MiddlewareContext) -> str:
        """
        Extract user email from tool arguments.
        
        Common parameter names: user_email, user_google_email, email
        """
        try:
            # Get arguments from the message
            if hasattr(context.message, 'arguments') and context.message.arguments:
                args = context.message.arguments
                
                # Try common user email parameter names
                for param_name in ['user_email', 'user_google_email', 'email', 'google_email']:
                    if param_name in args and args[param_name]:
                        return args[param_name]
            
            logger.debug("No user email found in tool arguments")
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting user email from tool arguments: {e}")
            return None
    
    async def _inject_services(self, tool_name: str, user_email: str):
        """
        Inject requested Google services into the context.
        
        Args:
            tool_name: Name of the tool being executed
            user_email: User's email address for service authentication
        """
        if not user_email:
            logger.debug(f"No user email available for service injection in tool: {tool_name}")
            return
        
        # Get pending service requests
        pending_requests = _get_pending_service_requests()
        
        if not pending_requests:
            logger.debug(f"No pending service requests for tool: {tool_name}")
            return
        
        logger.info(f"Injecting {len(pending_requests)} Google services for tool: {tool_name}")
        
        # Fulfill each service request
        for service_key, service_data in pending_requests.items():
            try:
                service_type = service_data["service_type"]
                scopes = service_data["scopes"]
                version = service_data["version"]
                cache_enabled = service_data["cache_enabled"]
                
                logger.debug(f"Creating {service_type} service for {user_email}")
                
                # Create the Google service
                service = await get_google_service(
                    user_email=user_email,
                    service_type=service_type,
                    scopes=scopes,
                    version=version,
                    cache_enabled=cache_enabled
                )
                
                # Inject the service into context
                _set_injected_service(service_key, service)
                
                logger.info(
                    f"Successfully injected {service_type} service "
                    f"for {user_email} in tool {tool_name}"
                )
                
            except GoogleServiceError as e:
                error_msg = f"Failed to create {service_data['service_type']} service: {str(e)}"
                logger.error(f"Service injection error for {tool_name}: {error_msg}")
                _set_service_error(service_key, error_msg)
                
            except Exception as e:
                error_msg = f"Unexpected error creating {service_data['service_type']} service: {str(e)}"
                logger.error(f"Service injection error for {tool_name}: {error_msg}")
                _set_service_error(service_key, error_msg)
    
    def enable_service_injection(self, enabled: bool = True):
        """Enable or disable automatic service injection."""
        self._service_injection_enabled = enabled
        logger.info(f"Service injection {'enabled' if enabled else 'disabled'}")
    
    def is_service_injection_enabled(self) -> bool:
        """Check if service injection is enabled."""
        return self._service_injection_enabled