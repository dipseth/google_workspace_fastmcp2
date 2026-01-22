"""Session context management for multi-user OAuth authentication using FastMCP Context."""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from fastmcp.server.dependencies import get_context
from typing_extensions import Any, Dict, List, Optional, Union

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Thread-safe storage for session data (this remains as it's not context-specific)
_session_store: Dict[str, Dict[str, Any]] = {}
_store_lock = threading.Lock()

# Global storage for middleware instances (this remains as it's not context-specific)
_auth_middleware: Optional[Any] = None
_middleware_lock = threading.Lock()

# In-memory cache for injected Google service instances
# Key format: "{session_id}:{service_key}" -> service instance
# This avoids storing non-serializable googleapiclient.discovery.Resource objects in FastMCP context
_service_instance_cache: Dict[str, Any] = {}
_service_cache_lock = threading.Lock()


async def set_session_context(session_id: str) -> None:
    """Set the current session ID in the FastMCP context."""
    try:
        ctx = get_context()
        await ctx.set_state("session_id", session_id)
        logger.debug(f"Set session context: {session_id}")
    except RuntimeError:
        # This is expected when called outside FastMCP request context (e.g., OAuth endpoints)
        logger.debug("Cannot set session context - not in a FastMCP request context")


def get_session_context_sync() -> Optional[str]:
    """Get the current session ID from the FastMCP context (synchronous version).

    This sync version only uses the native session_id property which doesn't require async.
    For full session context access including state, use async get_session_context().
    """
    try:
        ctx = get_context()
        # Use FastMCP's native session_id property (doesn't require await)
        if hasattr(ctx, "session_id"):
            native_session_id = ctx.session_id
            if native_session_id:
                logger.debug(
                    f"Using native FastMCP session_id (sync): {native_session_id[:8]}..."
                )
                return native_session_id
        return None
    except RuntimeError:
        logger.debug("Cannot get session context - not in a FastMCP request context")
        return None


async def get_session_context() -> Optional[str]:
    """Get the current session ID from the FastMCP context.

    Tries multiple sources in order:
    1. Explicitly set session_id via set_session_context()
    2. FastMCP's native session_id property from transport layer
    """
    try:
        ctx = get_context()
        # First try explicitly set session_id
        session_id = await ctx.get_state("session_id")
        if session_id:
            return session_id

        # Fall back to FastMCP's native session_id property
        if hasattr(ctx, "session_id"):
            native_session_id = ctx.session_id
            if native_session_id:
                logger.debug(
                    f"Using native FastMCP session_id: {native_session_id[:8]}..."
                )
                return native_session_id

        return None
    except RuntimeError:
        logger.debug("Cannot get session context - not in a FastMCP request context")
        return None


async def clear_session_context() -> None:
    """Clear the session context."""
    try:
        ctx = get_context()
        await ctx.set_state("session_id", None)
        logger.debug("Cleared session context")
    except RuntimeError:
        logger.debug("Cannot clear session context - not in a FastMCP request context")


async def set_effective_session_id(session_id: str) -> None:
    """
    Set the effective session ID for this request.

    This is used when the session ID differs from the transport's native session ID,
    such as when ?uuid= parameter is used to resume a specific session.

    Args:
        session_id: The effective session ID to use for tool filtering.
    """
    try:
        ctx = get_context()
        await ctx.set_state("effective_session_id", session_id)
        logger.debug(f"Set effective session ID: {session_id[:8]}...")
    except RuntimeError:
        logger.debug(
            "Cannot set effective session ID - not in a FastMCP request context"
        )


async def get_effective_session_id() -> Optional[str]:
    """
    Get the effective session ID for this request.

    Returns the effective session ID if set (e.g., from ?uuid= parameter),
    otherwise falls back to the transport's native session ID.

    This should be used for tool filtering decisions to ensure consistency
    between list_tools and call_tool operations.

    Returns:
        The effective session ID, or None if not available.
    """
    try:
        ctx = get_context()
        # First check for explicitly set effective session ID (from ?uuid= etc.)
        effective_id = await ctx.get_state("effective_session_id")
        if effective_id:
            return effective_id

        # Fall back to regular session context
        return await get_session_context()
    except RuntimeError:
        logger.debug(
            "Cannot get effective session ID - not in a FastMCP request context"
        )
        return None


async def set_user_email_context(user_email: str) -> None:
    """Set the current user email in the FastMCP context."""
    try:
        ctx = get_context()
        await ctx.set_state("user_email", user_email)
        logger.debug(f"Set user email context: {user_email}")
    except RuntimeError:
        # This is expected when called outside FastMCP request context (e.g., OAuth endpoints)
        logger.debug("Cannot set user email context - not in a FastMCP request context")


def set_user_email_context_in_session(user_email: str, session_id: str = None) -> None:
    """
    Set user email in session storage (sync version).

    This sync version stores the user email in session data storage, making it available
    for later retrieval via get_user_email_context_sync(). Use this when you cannot use
    the async set_user_email_context() function.

    Note: This does NOT set the FastMCP context state - it only stores in session data.
    For async callers, use set_user_email_context() instead.

    Args:
        user_email: Email to store
        session_id: Session ID (optional - if provided, stores in session data)
    """
    if session_id:
        store_session_data(session_id, "user_email", user_email)
        logger.debug(f"Set user email in session storage: {user_email}")
    else:
        # Fallback: store in OAuth auth file for persistence
        try:
            from config.settings import settings

            oauth_auth_file = (
                Path(settings.credentials_dir) / ".oauth_authentication.json"
            )
            with open(oauth_auth_file, "w") as f:
                json.dump({"authenticated_email": user_email}, f)
            logger.debug(f"Set user email in OAuth auth file: {user_email}")
        except Exception as e:
            logger.debug(f"Could not store user email in OAuth auth file: {e}")


def get_user_email_from_oauth() -> Optional[str]:
    """
    Get user email from OAuth credential files as a fallback when context is not available.

    CRITICAL FIX: Now searches for BOTH .json AND .enc credential files, plus .oauth_authentication.json.
    Prioritizes .oauth_authentication.json (most recent session marker) over credential files.

    This provides an alternative authentication strategy when AuthMiddleware or FastMCP context
    is not available (e.g., during MCP SDK 1.21.1+ incompatibilities).

    Returns:
        Optional[str]: User email from OAuth credentials, or None if not found
    """
    try:
        # Import settings to get credentials directory
        from config.settings import settings

        credentials_dir = Path(settings.credentials_dir)
        if not credentials_dir.exists():
            logger.debug(
                f"OAuth credentials directory does not exist: {credentials_dir}"
            )
            return None

        # PRIORITY 1: Check .oauth_authentication.json (most recent session marker)
        oauth_auth_file = credentials_dir / ".oauth_authentication.json"
        if oauth_auth_file.exists():
            try:
                with open(oauth_auth_file, "r") as f:
                    oauth_data = json.load(f)
                authenticated_email = oauth_data.get("authenticated_email")
                if authenticated_email:
                    logger.info(
                        f"✅ Retrieved user email from .oauth_authentication.json: {authenticated_email}"
                    )
                    return authenticated_email
            except Exception as e:
                logger.debug(f"Could not read .oauth_authentication.json: {e}")

        # PRIORITY 2: Check credential files (.json and .enc)
        credential_files = []
        for pattern in ["*_credentials.json", "*_credentials.enc"]:
            credential_files.extend(list(credentials_dir.glob(pattern)))

        if not credential_files:
            logger.debug(f"No OAuth credential files found in {credentials_dir}")
            return None

        # Use the most recently modified credential file
        latest_file = max(credential_files, key=lambda p: p.stat().st_mtime)

        logger.debug(f"Reading OAuth credentials from: {latest_file.name}")

        # For .enc files, we can't decrypt without AuthMiddleware, so extract from filename
        if latest_file.suffix == ".enc":
            safe_email = latest_file.stem.replace("_credentials", "")
            user_email = safe_email.replace("_at_", "@").replace("_", ".")
            logger.info(f"✅ Extracted user email from .enc filename: {user_email}")
            return user_email

        # For .json files, read the content
        with open(latest_file, "r") as f:
            creds_data = json.load(f)

        user_email = creds_data.get("user_email")
        if user_email:
            logger.info(f"✅ Retrieved user email from credential file: {user_email}")
            return user_email
        else:
            logger.warning(
                f"OAuth credential file {latest_file.name} does not contain user_email field"
            )
            return None

    except FileNotFoundError as e:
        logger.debug(f"OAuth credential file not found: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OAuth credential file: {e}")
        return None
    except Exception as e:
        logger.error(f"Error reading user email from OAuth credentials: {e}")
        return None


async def get_user_email_context() -> Optional[str]:
    """
    Get the current user email from the FastMCP context or OAuth files.

    This function first attempts to get the email from FastMCP context (if available),
    and falls back to reading from OAuth credential files if context is not available.
    This provides compatibility with MCP SDK 1.21.1+ where AuthMiddleware may not be available.

    Returns:
        Optional[str]: User email from context or OAuth files, or None if not found
    """
    try:
        ctx = get_context()
        email = await ctx.get_state("user_email")
        if email:
            logger.debug(f"Retrieved user email from FastMCP context: {email}")
            return email
    except RuntimeError:
        logger.debug("Cannot get user email context - not in a FastMCP request context")

    # Fallback to OAuth file-based authentication
    logger.debug("Attempting OAuth file-based authentication fallback")
    email = get_user_email_from_oauth()
    if email:
        logger.info(f"🔄 Using OAuth file-based authentication fallback for: {email}")
    return email


def get_user_email_context_sync() -> Optional[str]:
    """
    Get the current user email synchronously using OAuth file fallback.

    This sync version only uses the OAuth file-based fallback since FastMCP context
    state access requires async. For full context access, use async get_user_email_context().

    Returns:
        Optional[str]: User email from OAuth files, or None if not found
    """
    return get_user_email_from_oauth()


async def clear_user_email_context() -> None:
    """Clear the user email context."""
    try:
        ctx = get_context()
        await ctx.set_state("user_email", None)
        logger.debug("Cleared user email context")
    except RuntimeError:
        logger.debug(
            "Cannot clear user email context - not in a FastMCP request context"
        )


async def request_google_service(
    service_type: str,
    scopes: Union[str, List[str]] = None,
    version: Optional[str] = None,
    cache_enabled: bool = True,
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
        current_requests = await ctx.get_state("service_requests") or {}

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
            "error": None,
        }

        current_requests[service_key] = service_data
        await ctx.set_state("service_requests", current_requests)

        logger.debug(f"Requested Google service: {service_type} (key: {service_key})")
        return service_key

    except RuntimeError:
        logger.error("Cannot request service - not in a FastMCP request context")
        raise RuntimeError("Service request requires an active FastMCP request context")


async def get_injected_service(service_key: str) -> Any:
    """
    Get an injected Google service by its context key.

    Retrieves the service instance from the in-memory cache (since googleapiclient.discovery.Resource
    objects are not Pydantic-serializable and can't be stored in FastMCP context).

    Args:
        service_key: The key returned by request_google_service()

    Returns:
        The authenticated Google service instance

    Raises:
        RuntimeError: If service not found, not fulfilled, or error occurred
    """
    try:
        ctx = get_context()
        current_requests = await ctx.get_state("service_requests") or {}

        if service_key not in current_requests:
            raise RuntimeError(
                f"Service key '{service_key}' not found. Did you call request_google_service()?"
            )

        service_data = current_requests[service_key]

        if service_data.get("error"):
            raise RuntimeError(f"Service injection failed: {service_data['error']}")

        if not service_data.get("fulfilled"):
            raise RuntimeError(
                f"Service '{service_key}' not yet fulfilled by middleware"
            )

        # Get session ID for cache key
        session_id = await get_session_context() or "default"
        cache_key = f"{session_id}:{service_key}"

        # Retrieve the service from the in-memory cache
        with _service_cache_lock:
            service = _service_instance_cache.get(cache_key)

        if service is None:
            raise RuntimeError(
                f"Service '{service_key}' was fulfilled but no service instance found in cache"
            )

        logger.debug(
            f"Retrieved injected service: {service_key} (from cache {cache_key})"
        )
        return service

    except RuntimeError as e:
        if "not in a FastMCP request context" not in str(e):
            raise
        logger.error("Cannot get injected service - not in a FastMCP request context")
        raise RuntimeError(
            "Getting injected service requires an active FastMCP request context"
        )


async def get_google_service_simple(
    service_type: str,
    user_email: Optional[str] = None,
    scopes: Union[str, List[str]] = None,
    version: Optional[str] = None,
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
        user_email = await get_user_email_context()
        if not user_email:
            raise RuntimeError(
                "No user email provided and none found in context. "
                "Either pass user_email parameter or ensure middleware sets user context."
            )

    # Check if we already have this service in the current context
    service_key = f"{service_type}_{version or 'default'}"

    try:
        ctx = get_context()
        current_requests = await ctx.get_state("service_requests") or {}

        if service_key in current_requests and current_requests[service_key].get(
            "fulfilled"
        ):
            return await get_injected_service(service_key)
    except RuntimeError:
        pass

    # For now, fall back to direct service creation
    # In the future, this could be enhanced to work with middleware pre-injection
    raise RuntimeError(
        f"Cannot get Google service synchronously. "
        f'Use middleware injection or call \'await get_google_service("{service_type}", "{user_email}")\' from async context.'
    )


async def _set_injected_service(service_key: str, service: Any) -> None:
    """
    Internal function for middleware to set injected services.

    Stores the actual service instance in an in-memory cache (since googleapiclient.discovery.Resource
    objects are not Pydantic-serializable) and only stores metadata in FastMCP context.

    Args:
        service_key: The service key
        service: The authenticated service instance
    """
    try:
        ctx = get_context()
        current_requests = await ctx.get_state("service_requests") or {}

        if service_key in current_requests:
            # Get session ID for cache key
            session_id = await get_session_context() or "default"
            cache_key = f"{session_id}:{service_key}"

            # Store the actual service instance in the in-memory cache
            with _service_cache_lock:
                _service_instance_cache[cache_key] = service

            # Only store serializable metadata in the context state
            current_requests[service_key]["fulfilled"] = True
            current_requests[service_key]["error"] = None
            # Don't store the service object in context - it's not Pydantic-serializable
            current_requests[service_key].pop("service", None)
            await ctx.set_state("service_requests", current_requests)
            logger.debug(
                f"Middleware injected service: {service_key} (cached as {cache_key})"
            )
    except RuntimeError:
        logger.warning(
            f"Cannot inject service {service_key} - not in a FastMCP request context"
        )


async def _set_service_error(service_key: str, error: str) -> None:
    """
    Internal function for middleware to set service errors.

    Args:
        service_key: The service key
        error: The error message
    """
    try:
        ctx = get_context()
        current_requests = await ctx.get_state("service_requests") or {}

        if service_key in current_requests:
            current_requests[service_key]["error"] = error
            current_requests[service_key]["fulfilled"] = False
            await ctx.set_state("service_requests", current_requests)
            logger.debug(f"Middleware set error for service {service_key}: {error}")
    except RuntimeError:
        logger.warning(
            f"Cannot set service error for {service_key} - not in a FastMCP request context"
        )


async def _get_pending_service_requests() -> Dict[str, Dict[str, Any]]:
    """
    Internal function for middleware to get pending service requests.

    Returns:
        Dictionary of pending service requests
    """
    try:
        ctx = get_context()
        current_requests = await ctx.get_state("service_requests") or {}
        return {
            k: v
            for k, v in current_requests.items()
            if v.get("requested") and not v.get("fulfilled")
        }
    except RuntimeError:
        logger.debug(
            "Cannot get pending service requests - not in a FastMCP request context"
        )
        return {}


async def clear_all_context() -> None:
    """Clear all context variables and service cache for current session."""
    # Get session ID before clearing context
    session_id = await get_session_context() or "default"

    await clear_session_context()
    await clear_user_email_context()
    try:
        ctx = get_context()
        await ctx.set_state("service_requests", {})
    except RuntimeError:
        pass

    # Clear service cache for this session
    with _service_cache_lock:
        keys_to_remove = [
            k for k in _service_instance_cache if k.startswith(f"{session_id}:")
        ]
        for key in keys_to_remove:
            del _service_instance_cache[key]
        if keys_to_remove:
            logger.debug(
                f"Cleared {len(keys_to_remove)} cached services for session {session_id}"
            )

    logger.debug("Cleared all context variables")


def store_session_data(session_id: str, key: str, value: Any) -> None:
    """Store data for a specific session."""
    with _store_lock:
        if session_id not in _session_store:
            _session_store[session_id] = {
                "created_at": datetime.now(),
                "last_accessed": datetime.now(),
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


async def is_service_selection_needed(session_id: str = None) -> bool:
    """Check if service selection is needed for current session."""
    if not session_id:
        session_id = await get_session_context()

    if session_id:
        return get_session_data(session_id, "service_selection_needed", False)

    return False


# =============================================================================
# Session-Scoped Tool Management
# =============================================================================
# These functions manage per-session tool enable/disable state, allowing
# different clients to have different tool availability without affecting
# the global tool registry.


async def get_session_disabled_tools(session_id: str = None) -> set:
    """
    Get the set of tools disabled for a specific session.

    Args:
        session_id: Session identifier. If None, uses current FastMCP context.

    Returns:
        Set of tool names that are disabled for this session.
    """
    if not session_id:
        session_id = await get_session_context()

    if not session_id:
        return set()

    disabled = get_session_data(session_id, "session_disabled_tools", set())
    # Ensure we always return a set (in case None was stored)
    return (
        disabled if isinstance(disabled, set) else set(disabled) if disabled else set()
    )


def get_session_disabled_tools_sync(session_id: str) -> set:
    """
    Get the set of tools disabled for a specific session (synchronous version).

    This sync version REQUIRES session_id to be provided (cannot look up context).
    For automatic context lookup, use async get_session_disabled_tools().

    Args:
        session_id: Session identifier (required).

    Returns:
        Set of tool names that are disabled for this session.
    """
    if not session_id:
        return set()

    disabled = get_session_data(session_id, "session_disabled_tools", set())
    # Ensure we always return a set (in case None was stored)
    return (
        disabled if isinstance(disabled, set) else set(disabled) if disabled else set()
    )


async def disable_tool_for_session(
    tool_name: str, session_id: str = None, persist: bool = False
) -> bool:
    """
    Disable a tool for the current session only.

    This does not affect the global tool registry - other sessions will
    still see the tool as enabled.

    Args:
        tool_name: Name of the tool to disable.
        session_id: Session identifier. If None, uses current FastMCP context.
        persist: If True, immediately persist to disk for cross-client visibility.

    Returns:
        True if the tool was disabled, False if session not available.
    """
    if not session_id:
        session_id = await get_session_context()

    if not session_id:
        logger.warning("Cannot disable tool for session - no session context available")
        return False

    disabled = await get_session_disabled_tools(session_id)
    disabled.add(tool_name)
    store_session_data(session_id, "session_disabled_tools", disabled)
    logger.debug(f"Disabled tool '{tool_name}' for session {session_id}")

    if persist:
        # Also store user email for cross-session restoration
        user_email = await get_user_email_context()
        if user_email:
            store_session_data(session_id, "user_email", user_email)
        persist_session_tool_states()

    return True


def disable_tool_for_session_sync(tool_name: str, session_id: str) -> bool:
    """
    Disable a tool for a session (synchronous version).

    This sync version REQUIRES session_id to be provided (cannot look up context).
    For automatic context lookup, use async disable_tool_for_session().

    Note: This version does NOT support persist=True (no async user email lookup).

    Args:
        tool_name: Name of the tool to disable.
        session_id: Session identifier (required).

    Returns:
        True if the tool was disabled, False if session_id not provided.
    """
    if not session_id:
        logger.warning("Cannot disable tool for session - no session_id provided")
        return False

    disabled = get_session_disabled_tools_sync(session_id)
    disabled.add(tool_name)
    store_session_data(session_id, "session_disabled_tools", disabled)
    logger.debug(f"Disabled tool '{tool_name}' for session {session_id}")
    return True


async def enable_tool_for_session(
    tool_name: str, session_id: str = None, persist: bool = False
) -> bool:
    """
    Re-enable a tool for the current session.

    Removes the tool from the session's disabled list, restoring visibility.

    Args:
        tool_name: Name of the tool to enable.
        session_id: Session identifier. If None, uses current FastMCP context.
        persist: If True, immediately persist to disk for cross-client visibility.

    Returns:
        True if the tool was enabled, False if session not available.
    """
    if not session_id:
        session_id = await get_session_context()

    if not session_id:
        logger.warning("Cannot enable tool for session - no session context available")
        return False

    disabled = await get_session_disabled_tools(session_id)
    disabled.discard(tool_name)
    store_session_data(session_id, "session_disabled_tools", disabled)
    logger.debug(f"Enabled tool '{tool_name}' for session {session_id}")

    if persist:
        # Also store user email for cross-session restoration
        user_email = await get_user_email_context()
        if user_email:
            store_session_data(session_id, "user_email", user_email)
        persist_session_tool_states()

    return True


async def is_tool_enabled_for_session(tool_name: str, session_id: str = None) -> bool:
    """
    Check if a tool is enabled for the current session.

    A tool is enabled for a session if it's not in the session's disabled list.
    This does NOT check the global tool enabled state - that must be checked separately.

    Args:
        tool_name: Name of the tool to check.
        session_id: Session identifier. If None, uses current FastMCP context.

    Returns:
        True if the tool is NOT in the session's disabled list.
    """
    if not session_id:
        session_id = await get_session_context()

    if not session_id:
        # No session context = treat all tools as enabled (fall back to global state)
        return True

    disabled = await get_session_disabled_tools(session_id)
    return tool_name not in disabled


async def clear_session_disabled_tools(session_id: str = None) -> bool:
    """
    Clear all session-specific tool disables (re-enable all tools for session).

    Args:
        session_id: Session identifier. If None, uses current FastMCP context.

    Returns:
        True if cleared successfully, False if session not available.
    """
    if not session_id:
        session_id = await get_session_context()

    if not session_id:
        logger.warning(
            "Cannot clear session disabled tools - no session context available"
        )
        return False

    store_session_data(session_id, "session_disabled_tools", set())
    logger.debug(f"Cleared all session-disabled tools for session {session_id}")
    return True


def clear_session_disabled_tools_sync(session_id: str) -> bool:
    """
    Clear all session-specific tool disables synchronously.

    This sync version REQUIRES session_id to be provided (cannot look up context).
    For automatic context lookup, use async clear_session_disabled_tools().

    Args:
        session_id: Session identifier (required).

    Returns:
        True if cleared successfully, False if session_id is empty.
    """
    if not session_id:
        logger.warning(
            "Cannot clear session disabled tools - session_id is required for sync version"
        )
        return False

    store_session_data(session_id, "session_disabled_tools", set())
    logger.debug(f"Cleared all session-disabled tools for session {session_id} (sync)")
    return True


async def get_session_tool_state_summary(session_id: str = None) -> Dict[str, Any]:
    """
    Get a summary of session-specific tool state.

    Args:
        session_id: Session identifier. If None, uses current FastMCP context.

    Returns:
        Dictionary with session tool state information.
    """
    if not session_id:
        session_id = await get_session_context()

    if not session_id:
        return {
            "session_id": None,
            "session_available": False,
            "disabled_tools": [],
            "disabled_count": 0,
        }

    disabled = await get_session_disabled_tools(session_id)
    return {
        "session_id": session_id,
        "session_available": True,
        "disabled_tools": sorted(list(disabled)),
        "disabled_count": len(disabled),
    }


async def get_session_enabled_services(
    session_id: str = None, all_tools: list = None
) -> set:
    """
    Get the set of services that have at least one enabled tool for this session.

    This determines which Google Workspace services are actually usable
    based on which tools are enabled (not disabled) for the session.

    Args:
        session_id: Session identifier. If None, attempts to get from context.
        all_tools: List of all tool names. If None, returns empty set.

    Returns:
        Set of service names (e.g., {'gmail', 'drive', 'calendar'})
    """
    from middleware.qdrant_core.query_parser import extract_service_from_tool

    if not session_id:
        session_id = await get_session_context()

    if not session_id or not all_tools:
        return set()

    disabled_tools = await get_session_disabled_tools(session_id)
    enabled_services = set()

    for tool_name in all_tools:
        if tool_name not in disabled_tools:
            service = extract_service_from_tool(tool_name)
            if service and service != "unknown":
                enabled_services.add(service)

    return enabled_services


def get_session_enabled_services_sync(
    session_id: str, all_tools: list, disabled_tools: set = None
) -> set:
    """
    Get enabled services synchronously (requires session_id and disabled_tools).

    This sync version requires all data to be provided upfront.

    Args:
        session_id: Session identifier (required).
        all_tools: List of all tool names.
        disabled_tools: Set of disabled tool names. If None, fetches from session.

    Returns:
        Set of service names with at least one enabled tool.
    """
    from middleware.qdrant_core.query_parser import extract_service_from_tool

    if not session_id or not all_tools:
        return set()

    if disabled_tools is None:
        disabled_tools = get_session_disabled_tools_sync(session_id)

    enabled_services = set()

    for tool_name in all_tools:
        if tool_name not in disabled_tools:
            service = extract_service_from_tool(tool_name)
            if service and service != "unknown":
                enabled_services.add(service)

    return enabled_services


async def store_custom_oauth_credentials(
    state: str,
    custom_client_id: str,
    custom_client_secret: str = None,
    auth_method: str = None,
) -> None:
    """Store custom OAuth credentials in both state map and context for persistence."""
    try:
        ctx = get_context()
        # Store in FastMCP context for cross-request persistence
        await ctx.set_state(f"custom_client_id_{state}", custom_client_id)
        if custom_client_secret:
            await ctx.set_state(f"custom_client_secret_{state}", custom_client_secret)
        if auth_method:
            await ctx.set_state(f"auth_method_{state}", auth_method)

        logger.info(
            f"🔗 Stored custom OAuth credentials in FastMCP context for state: {state}"
        )
    except RuntimeError:
        logger.debug(
            "Cannot store custom credentials in context - not in FastMCP request"
        )


async def retrieve_custom_oauth_credentials(
    state: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Retrieve custom OAuth credentials from context."""
    try:
        ctx = get_context()
        custom_client_id = await ctx.get_state(f"custom_client_id_{state}")
        custom_client_secret = await ctx.get_state(f"custom_client_secret_{state}")
        auth_method = await ctx.get_state(f"auth_method_{state}")

        if custom_client_id:
            logger.info(
                f"🔗 Retrieved custom OAuth credentials from FastMCP context for state: {state}"
            )

        return custom_client_id, custom_client_secret, auth_method
    except RuntimeError:
        logger.debug(
            "Cannot retrieve custom credentials from context - not in FastMCP request"
        )
        return None, None, None


# =============================================================================
# Session Tool State Persistence
# =============================================================================
# These functions handle persisting and restoring session tool states across
# server restarts and client reconnections. This enables the "minimal startup"
# mode where new sessions start with bare minimum tools, but returning sessions
# restore their previously enabled tools.


def _get_session_tool_state_path() -> Path:
    """Get the path for session tool state persistence file."""
    try:
        from config.settings import settings

        return settings.session_tool_state_path
    except Exception as e:
        logger.warning(f"Could not get session tool state path from settings: {e}")
        return Path("session_tool_states.json")


def persist_session_tool_states() -> bool:
    """
    Persist all session tool states to a JSON file.

    This saves the enabled/disabled tool state for all active sessions,
    allowing sessions to restore their tool configuration after reconnection.

    Returns:
        True if persistence succeeded, False otherwise.
    """
    state_file = _get_session_tool_state_path()

    try:
        with _store_lock:
            # Collect all session tool states
            persisted_states = {}
            for session_id, session_data in _session_store.items():
                disabled_tools = session_data.get("session_disabled_tools", set())
                if disabled_tools or session_data.get("minimal_startup_applied"):
                    persisted_states[session_id] = {
                        "disabled_tools": (
                            list(disabled_tools) if disabled_tools else []
                        ),
                        "last_accessed": session_data.get(
                            "last_accessed", datetime.now()
                        ).isoformat(),
                        "minimal_startup_applied": session_data.get(
                            "minimal_startup_applied", False
                        ),
                        "user_email": session_data.get("user_email"),
                    }

        if not persisted_states:
            logger.debug("No session tool states to persist")
            return True

        # Write to file
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(persisted_states, f, indent=2)

        logger.info(
            f"✅ Persisted tool states for {len(persisted_states)} sessions to {state_file}"
        )
        return True

    except Exception as e:
        logger.error(f"❌ Failed to persist session tool states: {e}")
        return False


def load_persisted_session_tool_states() -> Dict[str, Dict[str, Any]]:
    """
    Load persisted session tool states from file.

    Returns:
        Dictionary mapping session_id to their persisted tool state.
    """
    state_file = _get_session_tool_state_path()

    if not state_file.exists():
        logger.debug(f"No persisted session tool states file found at {state_file}")
        return {}

    try:
        with open(state_file, "r") as f:
            persisted_states = json.load(f)

        # Convert disabled_tools lists back to sets
        for session_id, state in persisted_states.items():
            if "disabled_tools" in state:
                state["disabled_tools"] = set(state["disabled_tools"])

        logger.info(
            f"✅ Loaded persisted tool states for {len(persisted_states)} sessions from {state_file}"
        )
        return persisted_states

    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in session tool states file: {e}")
        return {}
    except Exception as e:
        logger.error(f"❌ Failed to load session tool states: {e}")
        return {}


def restore_session_tool_state(session_id: str) -> bool:
    """
    Restore a session's tool state from persisted storage.

    If the session has persisted tool state, it will be restored to the
    session store, effectively continuing where the session left off.

    Args:
        session_id: The session ID to restore.

    Returns:
        True if state was restored (session was known), False if new session.
    """
    persisted_states = load_persisted_session_tool_states()

    if session_id not in persisted_states:
        logger.debug(
            f"No persisted state found for session {session_id[:8]}... (new session)"
        )
        return False

    state = persisted_states[session_id]

    with _store_lock:
        if session_id not in _session_store:
            _session_store[session_id] = {
                "created_at": datetime.now(),
                "last_accessed": datetime.now(),
            }

        _session_store[session_id]["session_disabled_tools"] = state.get(
            "disabled_tools", set()
        )
        _session_store[session_id]["minimal_startup_applied"] = state.get(
            "minimal_startup_applied", False
        )
        _session_store[session_id]["last_accessed"] = datetime.now()

        if state.get("user_email"):
            _session_store[session_id]["user_email"] = state["user_email"]

    disabled_count = len(state.get("disabled_tools", set()))
    logger.info(
        f"✅ Restored session {session_id[:8]}... from persistence "
        f"({disabled_count} tools disabled, minimal_startup={state.get('minimal_startup_applied', False)})"
    )
    return True


def is_known_session(session_id: str) -> bool:
    """
    Check if a session ID is known (either in memory or persisted).

    Args:
        session_id: The session ID to check.

    Returns:
        True if session is known (has prior state), False if new.
    """
    # Check in-memory first
    with _store_lock:
        if session_id in _session_store:
            return True

    # Check persisted states
    persisted_states = load_persisted_session_tool_states()
    return session_id in persisted_states


def find_session_id_by_email(user_email: str) -> Optional[str]:
    """
    Find a persisted session ID by user email.

    This enables session continuity across MCP reconnections where the
    transport generates a new session ID but the user is the same.

    Args:
        user_email: The user's email address.

    Returns:
        The most recent session ID for this user, or None if not found.
    """
    if not user_email:
        return None

    persisted_states = load_persisted_session_tool_states()

    # Find all sessions for this email, sorted by last_accessed (most recent first)
    matching_sessions = []
    for session_id, state in persisted_states.items():
        if state.get("user_email") == user_email:
            try:
                last_accessed = datetime.fromisoformat(state.get("last_accessed", ""))
                matching_sessions.append((session_id, last_accessed))
            except (ValueError, TypeError):
                # Invalid date - still include but with old timestamp
                matching_sessions.append((session_id, datetime.min))

    if not matching_sessions:
        return None

    # Return the most recently accessed session for this user
    matching_sessions.sort(key=lambda x: x[1], reverse=True)
    return matching_sessions[0][0]


def restore_session_tool_state_by_email(new_session_id: str, user_email: str) -> bool:
    """
    Restore tool state from a previous session with the same user email.

    This allows session continuity when the transport generates a new session ID
    but the user is the same (common with STDIO transport reconnections).

    The tool state from the old session is copied to the new session ID.

    Args:
        new_session_id: The new session ID to restore state into.
        user_email: The user's email to search for previous sessions.

    Returns:
        True if state was restored from a previous session, False otherwise.
    """
    old_session_id = find_session_id_by_email(user_email)
    if not old_session_id:
        logger.debug(f"No previous session found for user {user_email} to restore from")
        return False

    if old_session_id == new_session_id:
        # Same session, use regular restore
        return restore_session_tool_state(new_session_id)

    # Load the old session's state
    persisted_states = load_persisted_session_tool_states()
    old_state = persisted_states.get(old_session_id)
    if not old_state:
        return False

    # Copy state to new session
    with _store_lock:
        if new_session_id not in _session_store:
            _session_store[new_session_id] = {
                "created_at": datetime.now(),
                "last_accessed": datetime.now(),
            }

        _session_store[new_session_id]["session_disabled_tools"] = old_state.get(
            "disabled_tools", set()
        )
        _session_store[new_session_id]["minimal_startup_applied"] = old_state.get(
            "minimal_startup_applied", False
        )
        _session_store[new_session_id]["user_email"] = user_email
        _session_store[new_session_id]["last_accessed"] = datetime.now()

    disabled_count = len(old_state.get("disabled_tools", set()))
    logger.info(
        f"✅ Restored session {new_session_id[:8]}... from previous session "
        f"{old_session_id[:8]}... for user {user_email} "
        f"({disabled_count} tools disabled)"
    )

    # Persist the new session state and optionally clean up old one
    persist_session_tool_states()

    return True


def mark_minimal_startup_applied(session_id: str) -> None:
    """
    Mark that minimal startup has been applied to a session.

    This prevents re-applying minimal startup if the session reconnects
    before tool state is modified.

    Args:
        session_id: The session ID to mark.
    """
    with _store_lock:
        if session_id not in _session_store:
            _session_store[session_id] = {
                "created_at": datetime.now(),
                "last_accessed": datetime.now(),
            }

        _session_store[session_id]["minimal_startup_applied"] = True
        _session_store[session_id]["last_accessed"] = datetime.now()

    # Persist immediately to ensure it's not lost
    persist_session_tool_states()


def was_minimal_startup_applied(session_id: str) -> bool:
    """
    Check if minimal startup was already applied to a session.

    Args:
        session_id: The session ID to check.

    Returns:
        True if minimal startup was already applied.
    """
    with _store_lock:
        if session_id in _session_store:
            return _session_store[session_id].get("minimal_startup_applied", False)

    # Check persisted state
    persisted_states = load_persisted_session_tool_states()
    if session_id in persisted_states:
        return persisted_states[session_id].get("minimal_startup_applied", False)

    return False


def clear_minimal_startup_applied(session_id: str) -> None:
    """
    Clear the minimal startup applied flag for a session.

    This allows the session to be reprocessed with a new service filter
    when reconnecting with ?service= URL parameter.

    Args:
        session_id: The session ID to clear the flag for.
    """
    with _store_lock:
        if session_id in _session_store:
            _session_store[session_id]["minimal_startup_applied"] = False
            _session_store[session_id]["last_accessed"] = datetime.now()

    # Also update persisted state
    persist_session_tool_states()


def cleanup_old_persisted_sessions(max_age_days: int = 7) -> int:
    """
    Clean up persisted sessions older than the specified age.

    Args:
        max_age_days: Maximum age in days for persisted sessions.

    Returns:
        Number of sessions cleaned up.
    """
    state_file = _get_session_tool_state_path()

    if not state_file.exists():
        return 0

    try:
        with open(state_file, "r") as f:
            persisted_states = json.load(f)

        cutoff = datetime.now() - timedelta(days=max_age_days)
        sessions_to_remove = []

        for session_id, state in persisted_states.items():
            try:
                last_accessed = datetime.fromisoformat(state.get("last_accessed", ""))
                if last_accessed < cutoff:
                    sessions_to_remove.append(session_id)
            except (ValueError, TypeError):
                # Invalid date format - remove the session
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            del persisted_states[session_id]

        if sessions_to_remove:
            with open(state_file, "w") as f:
                json.dump(persisted_states, f, indent=2)
            logger.info(
                f"🧹 Cleaned up {len(sessions_to_remove)} old persisted sessions"
            )

        return len(sessions_to_remove)

    except Exception as e:
        logger.error(f"❌ Failed to cleanup old persisted sessions: {e}")
        return 0
