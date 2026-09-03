"""Session context management for multi-user OAuth authentication using FastMCP Context."""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from fastmcp.server.dependencies import get_context
from typing_extensions import Any, Dict, List, Optional, Union

from config.enhanced_logging import redact_email, setup_logger

from .types import SessionKey

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


async def set_user_email_context(user_email: str) -> None:
    """Set the current user email in the FastMCP context."""
    try:
        ctx = get_context()
        await ctx.set_state("user_email", user_email)
        logger.debug(f"Set user email context: {redact_email(user_email)}")
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
        store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
        logger.debug(f"Set user email in session storage: {redact_email(user_email)}")
    else:
        # Fallback: store in OAuth auth file for persistence
        try:
            from config.settings import settings

            oauth_auth_file = (
                Path(settings.credentials_dir) / ".oauth_authentication.json"
            )
            with open(oauth_auth_file, "w") as f:
                json.dump({"authenticated_email": user_email}, f)
            logger.debug(
                f"Set user email in OAuth auth file: {redact_email(user_email)}"
            )
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
                        f"✅ Retrieved user email from .oauth_authentication.json: {redact_email(authenticated_email)}"
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
            logger.info(
                f"✅ Extracted user email from .enc filename: {redact_email(user_email)}"
            )
            return user_email

        # For .json files, read the content
        with open(latest_file, "r") as f:
            creds_data = json.load(f)

        user_email = creds_data.get("user_email")
        if user_email:
            logger.info(
                f"✅ Retrieved user email from credential file: {redact_email(user_email)}"
            )
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
            logger.debug(
                f"Retrieved user email from FastMCP context: {redact_email(email)}"
            )
            return email
    except RuntimeError:
        logger.debug("Cannot get user email context - not in a FastMCP request context")

    # Fallback to OAuth file-based authentication
    logger.debug("Attempting OAuth file-based authentication fallback")
    email = get_user_email_from_oauth()
    if email:
        logger.info(
            f"🔄 Using OAuth file-based authentication fallback for: {redact_email(email)}"
        )
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

        # Determine still-active sessions for vault cleanup
        active_ids = set(_session_store.keys())

    # Clean up privacy vaults for expired sessions
    try:
        from middleware.privacy.registry import cleanup_expired_vaults

        cleanup_expired_vaults(active_ids)
    except ImportError:
        pass  # Privacy middleware not installed

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
        return get_session_data(session_id, SessionKey.SERVICE_SELECTION_NEEDED, False)

    return False


# =============================================================================
# Session-Scoped Tool Management
# =============================================================================
# Per-user tool enable/disable state lives in the per-principal bucket
# (auth/user_state.py), keyed by the authenticated identity rather than the
# transport session. The ``session_id`` parameters below are accepted for
# call-site compatibility and ignored: the bucket is resolved from the current
# request's token, so one user's state is shared by every connection they open
# and survives the per-request sessions of MCP 2026-07-28.


async def get_session_disabled_tools(session_id: str = None) -> set:
    """The set of tools disabled for the current principal."""
    from .user_state import get_disabled_tools

    return await get_disabled_tools()


async def disable_tool_for_session(
    tool_name: str, session_id: str = None, persist: bool = False
) -> bool:
    """Disable a tool for the current principal (all of their connections)."""
    from .user_state import disable_tools

    ok = await disable_tools([tool_name])
    if ok:
        logger.debug(f"Disabled tool '{tool_name}' for current principal")
    return ok


async def enable_tool_for_session(
    tool_name: str, session_id: str = None, persist: bool = False
) -> bool:
    """Re-enable a tool for the current principal."""
    from .user_state import enable_tools

    ok = await enable_tools([tool_name])
    if ok:
        logger.debug(f"Enabled tool '{tool_name}' for current principal")
    return ok


async def is_tool_enabled_for_session(tool_name: str, session_id: str = None) -> bool:
    """True unless the tool is in the current principal's disabled set."""
    from .user_state import is_tool_disabled

    return not await is_tool_disabled(tool_name)


async def clear_session_disabled_tools(session_id: str = None) -> bool:
    """Re-enable every tool for the current principal."""
    from .user_state import clear_disabled_tools

    return await clear_disabled_tools()


async def get_session_tool_state_summary(session_id: str = None) -> Dict[str, Any]:
    """Summary of the current principal's disabled tools."""
    disabled = await get_session_disabled_tools()
    return {
        "session_id": session_id or await get_session_context(),
        "session_available": True,
        "disabled_tools": sorted(disabled),
        "disabled_count": len(disabled),
    }


async def get_session_enabled_services(
    session_id: str = None, all_tools: list = None
) -> set:
    """Services with at least one tool enabled for the current principal."""
    if not all_tools:
        return set()
    return enabled_services_for(all_tools, await get_session_disabled_tools())


def enabled_services_for(all_tools: list, disabled_tools: set) -> set:
    """Services (``gmail``, ``drive``, …) that still have an enabled tool."""
    from middleware.qdrant_core.query_parser import extract_service_from_tool

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
    """Keep custom OAuth client credentials for ``state`` until the callback.

    Stored in the server state store under the flow's ``state`` string with a
    ten-minute TTL. The OAuth callback is a Starlette route with no MCP
    session, so this was never per-session; keying it that way lost the
    credentials on every 2026-07-28 request.
    """
    from .user_state import oauth_state_set

    data = {"custom_client_id": custom_client_id}
    if custom_client_secret:
        data["custom_client_secret"] = custom_client_secret
    if auth_method:
        data["auth_method"] = auth_method
    await oauth_state_set(state, data)
    logger.info(f"🔗 Stored custom OAuth credentials for state: {state[:8]}...")


async def retrieve_custom_oauth_credentials(
    state: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Retrieve custom OAuth credentials stored for ``state``."""
    from .user_state import oauth_state_get

    data = await oauth_state_get(state) or {}
    if data.get("custom_client_id"):
        logger.info(f"🔗 Retrieved custom OAuth credentials for state: {state[:8]}...")
    return (
        data.get("custom_client_id"),
        data.get("custom_client_secret"),
        data.get("auth_method"),
    )


# =============================================================================
# Legacy session tool state file
# =============================================================================
# ``session_tool_states.json`` used to persist per-session disabled tools
# across restarts. The per-principal bucket replaced it; the file is now read
# once per user by ``auth.user_state.import_legacy_disabled_tools`` and never
# written.


def _get_session_tool_state_path() -> Path:
    """Path of the retired session tool state file (read-only, legacy import)."""
    try:
        from config.settings import settings

        return settings.session_tool_state_path
    except Exception as e:
        logger.warning(f"Could not get session tool state path from settings: {e}")
        return Path("session_tool_states.json")
