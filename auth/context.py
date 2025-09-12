"""Session context management for multi-user OAuth authentication using FastMCP Context."""

import logging
from typing_extensions import Optional, Dict, Any, Union, List
from datetime import datetime, timedelta
import threading

from fastmcp import Context
from fastmcp.server.dependencies import get_context

logger = logging.getLogger(__name__)

# Thread-safe storage for session data (this remains as it's not context-specific)
_session_store: Dict[str, Dict[str, Any]] = {}
_store_lock = threading.Lock()

# Global storage for middleware instances (this remains as it's not context-specific)
_auth_middleware: Optional[Any] = None
_middleware_lock = threading.Lock()


def set_session_context(session_id: str) -> None:
    """Set the current session ID in the FastMCP context."""
    try:
        ctx = get_context()
        ctx.set_state("session_id", session_id)
        logger.debug(f"Set session context: {session_id}")
    except RuntimeError:
        # This is expected when called outside FastMCP request context (e.g., OAuth endpoints)
        logger.debug("Cannot set session context - not in a FastMCP request context")


def get_session_context() -> Optional[str]:
    """Get the current session ID from the FastMCP context."""
    try:
        ctx = get_context()
        return ctx.get_state("session_id")
    except RuntimeError:
        logger.debug("Cannot get session context - not in a FastMCP request context")
        return None


def clear_session_context() -> None:
    """Clear the session context."""
    try:
        ctx = get_context()
        ctx.set_state("session_id", None)
        logger.debug("Cleared session context")
    except RuntimeError:
        logger.debug("Cannot clear session context - not in a FastMCP request context")


def set_user_email_context(user_email: str) -> None:
    """Set the current user email in the FastMCP context."""
    try:
        ctx = get_context()
        ctx.set_state("user_email", user_email)
        logger.debug(f"Set user email context: {user_email}")
    except RuntimeError:
        # This is expected when called outside FastMCP request context (e.g., OAuth endpoints)
        logger.debug("Cannot set user email context - not in a FastMCP request context")


def get_user_email_context() -> Optional[str]:
    """Get the current user email from the FastMCP context."""
    try:
        ctx = get_context()
        return ctx.get_state("user_email")
    except RuntimeError:
        logger.debug("Cannot get user email context - not in a FastMCP request context")
        return None


def clear_user_email_context() -> None:
    """Clear the user email context."""
    try:
        ctx = get_context()
        ctx.set_state("user_email", None)
        logger.debug("Cleared user email context")
    except RuntimeError:
        logger.debug("Cannot clear user email context - not in a FastMCP request context")


def request_google_service(
    service_type: str,
    scopes: Union[str, List[str]] = None,
    version: Optional[str] = None,
    cache_enabled: bool = True
) -> str:
    """
    Request a Google service to be injected by middleware.
    
    This function registers a service request that will be fulfilled by the
    ServiceInjectionMiddleware. It returns a context key that can be used
    to retrieve the service later.
    
    Args:
        service_type: Type of Google service ("drive", "gmail", "calendar", etc.)
        scopes: Required scopes (can be scope group names or actual URLs)
        version: Service version (defaults to standard version for service type)
        cache_enabled: Whether to use service caching (default: True)
    
    Returns:
        Context key to retrieve the service with get_injected_service()
    """
    try:
        ctx = get_context()
        
        # Get current service requests or create new dict
        current_requests = ctx.get_state("service_requests") or {}
        
        # Generate a unique key for this service request
        # Use just the service type as the key (middleware expects "drive", not "drive_v3")
        service_key = service_type
        
        # Store the service request
        service_data = {
            "service_type": service_type,
            "scopes": scopes,
            "version": version,
            "cache_enabled": cache_enabled,
            "requested": True,
            "fulfilled": False,
            "service": None,
            "error": None
        }
        
        current_requests[service_key] = service_data
        ctx.set_state("service_requests", current_requests)
        
        logger.debug(f"Requested Google service: {service_type} (key: {service_key})")
        return service_key
        
    except RuntimeError:
        logger.error("Cannot request service - not in a FastMCP request context")
        raise RuntimeError("Service request requires an active FastMCP request context")


def get_injected_service(service_key: str) -> Any:
    """
    Get an injected Google service by its context key.
    
    Args:
        service_key: The key returned by request_google_service()
    
    Returns:
        The authenticated Google service instance
        
    Raises:
        RuntimeError: If service not found, not fulfilled, or error occurred
    """
    try:
        ctx = get_context()
        current_requests = ctx.get_state("service_requests") or {}
        
        if service_key not in current_requests:
            raise RuntimeError(f"Service key '{service_key}' not found. Did you call request_google_service()?")
        
        service_data = current_requests[service_key]
        
        if service_data.get("error"):
            raise RuntimeError(f"Service injection failed: {service_data['error']}")
        
        if not service_data.get("fulfilled"):
            raise RuntimeError(f"Service '{service_key}' not yet fulfilled by middleware")
        
        service = service_data.get("service")
        if service is None:
            raise RuntimeError(f"Service '{service_key}' was fulfilled but no service instance found")
        
        logger.debug(f"Retrieved injected service: {service_key}")
        return service
        
    except RuntimeError as e:
        if "not in a FastMCP request context" not in str(e):
            raise
        logger.error("Cannot get injected service - not in a FastMCP request context")
        raise RuntimeError("Getting injected service requires an active FastMCP request context")


def get_google_service_simple(
    service_type: str,
    user_email: Optional[str] = None,
    scopes: Union[str, List[str]] = None,
    version: Optional[str] = None
) -> Any:
    """
    Simplified function to get a Google service through middleware injection.
    
    This is a convenience function that handles the request/get pattern automatically.
    It uses the current user email from context if not provided.
    
    Args:
        service_type: Type of Google service ("drive", "gmail", "calendar", etc.)
        user_email: User's email (uses context if not provided)
        scopes: Required scopes (can be scope group names or actual URLs)
        version: Service version (defaults to standard version for service type)
    
    Returns:
        The authenticated Google service instance
        
    Raises:
        RuntimeError: If user email not available or service injection fails
    """
    # Use provided user email or get from context
    if not user_email:
        user_email = get_user_email_context()
        if not user_email:
            raise RuntimeError(
                "No user email provided and none found in context. "
                "Either pass user_email parameter or ensure middleware sets user context."
            )
    
    # Check if we already have this service in the current context
    service_key = f"{service_type}_{version or 'default'}"
    
    try:
        ctx = get_context()
        current_requests = ctx.get_state("service_requests") or {}
        
        if service_key in current_requests and current_requests[service_key].get("fulfilled"):
            return get_injected_service(service_key)
    except RuntimeError:
        pass
    
    # For now, fall back to direct service creation
    # In the future, this could be enhanced to work with middleware pre-injection
    from .service_manager import get_google_service
    import asyncio
    
    # Check if we're in an async context
    try:
        # Try to get the current event loop
        loop = asyncio.get_running_loop()
        # If we're in an async context, we need to handle this differently
        # For now, raise an error suggesting the proper async usage
        raise RuntimeError(
            f"get_google_service_simple() called from async context. "
            f"Use 'await get_google_service(\"{service_type}\", \"{user_email}\", {scopes})' instead."
        )
    except RuntimeError as e:
        if "no running event loop" not in str(e).lower():
            raise e
        
        # We're not in an async context, but get_google_service is async
        # This shouldn't happen in normal FastMCP usage, but handle gracefully
        raise RuntimeError(
            f"Cannot get Google service synchronously. "
            f"Use middleware injection or call 'await get_google_service(\"{service_type}\", \"{user_email}\")' from async context."
        )


def _set_injected_service(service_key: str, service: Any) -> None:
    """
    Internal function for middleware to set injected services.
    
    Args:
        service_key: The service key
        service: The authenticated service instance
    """
    try:
        ctx = get_context()
        current_requests = ctx.get_state("service_requests") or {}
        
        if service_key in current_requests:
            current_requests[service_key]["service"] = service
            current_requests[service_key]["fulfilled"] = True
            current_requests[service_key]["error"] = None
            ctx.set_state("service_requests", current_requests)
            logger.debug(f"Middleware injected service: {service_key}")
    except RuntimeError:
        logger.warning(f"Cannot inject service {service_key} - not in a FastMCP request context")


def _set_service_error(service_key: str, error: str) -> None:
    """
    Internal function for middleware to set service errors.
    
    Args:
        service_key: The service key
        error: The error message
    """
    try:
        ctx = get_context()
        current_requests = ctx.get_state("service_requests") or {}
        
        if service_key in current_requests:
            current_requests[service_key]["error"] = error
            current_requests[service_key]["fulfilled"] = False
            ctx.set_state("service_requests", current_requests)
            logger.debug(f"Middleware set error for service {service_key}: {error}")
    except RuntimeError:
        logger.warning(f"Cannot set service error for {service_key} - not in a FastMCP request context")


def _get_pending_service_requests() -> Dict[str, Dict[str, Any]]:
    """
    Internal function for middleware to get pending service requests.
    
    Returns:
        Dictionary of pending service requests
    """
    try:
        ctx = get_context()
        current_requests = ctx.get_state("service_requests") or {}
        return {k: v for k, v in current_requests.items() if v.get("requested") and not v.get("fulfilled")}
    except RuntimeError:
        logger.debug("Cannot get pending service requests - not in a FastMCP request context")
        return {}


def clear_all_context() -> None:
    """Clear all context variables."""
    clear_session_context()
    clear_user_email_context()
    try:
        ctx = get_context()
        ctx.set_state("service_requests", {})
    except RuntimeError:
        pass
    logger.debug("Cleared all context variables")


def store_session_data(session_id: str, key: str, value: Any) -> None:
    """Store data for a specific session."""
    with _store_lock:
        if session_id not in _session_store:
            _session_store[session_id] = {
                "created_at": datetime.now(),
                "last_accessed": datetime.now()
            }
        
        _session_store[session_id][key] = value
        _session_store[session_id]["last_accessed"] = datetime.now()
        
    logger.debug(f"Stored session data for {session_id}: {key}")


def get_session_data(session_id: str, key: str, default: Any = None) -> Any:
    """Retrieve data for a specific session."""
    with _store_lock:
        session_data = _session_store.get(session_id, {})
        if session_data:
            session_data["last_accessed"] = datetime.now()
        
        value = session_data.get(key, default)
    
    logger.debug(f"Retrieved session data for {session_id}: {key}")
    return value


def delete_session_data(session_id: str, key: str) -> bool:
    """Delete specific data for a session."""
    with _store_lock:
        if session_id in _session_store and key in _session_store[session_id]:
            del _session_store[session_id][key]
            logger.debug(f"Deleted session data for {session_id}: {key}")
            return True
    
    return False


def clear_session(session_id: str) -> bool:
    """Clear all data for a specific session."""
    with _store_lock:
        if session_id in _session_store:
            del _session_store[session_id]
            logger.info(f"Cleared all data for session: {session_id}")
            return True
    
    return False


def cleanup_expired_sessions(timeout_minutes: int = 60) -> int:
    """Clean up sessions that haven't been accessed recently."""
    cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)
    expired_sessions = []
    
    with _store_lock:
        for session_id, session_data in _session_store.items():
            last_accessed = session_data.get("last_accessed", datetime.min)
            if last_accessed < cutoff_time:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del _session_store[session_id]
    
    if expired_sessions:
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    return len(expired_sessions)


def get_session_count() -> int:
    """Get the current number of active sessions."""
    with _store_lock:
        return len(_session_store)


def list_sessions() -> list[str]:
    """Get a list of all active session IDs."""
    with _store_lock:
        return list(_session_store.keys())


def set_auth_middleware(middleware: Any) -> None:
    """Set the AuthMiddleware instance for global access."""
    global _auth_middleware
    with _middleware_lock:
        _auth_middleware = middleware
        logger.debug("Set AuthMiddleware instance in context")


def get_auth_middleware() -> Optional[Any]:
    """Get the AuthMiddleware instance."""
    with _middleware_lock:
        return _auth_middleware


# Google Provider management for service selection
_google_provider_instance = None

def set_google_provider(provider):
    """Store GoogleProvider instance for global access."""
    global _google_provider_instance
    _google_provider_instance = provider
    logger.debug("Set GoogleProvider instance in context")

def get_google_provider():
    """Get GoogleProvider instance."""
    return _google_provider_instance

def is_service_selection_needed(session_id: str = None) -> bool:
    """Check if service selection is needed for current session."""
    if not session_id:
        session_id = get_session_context()
    
    if session_id:
        return get_session_data(session_id, "service_selection_needed", False)
    
    return False