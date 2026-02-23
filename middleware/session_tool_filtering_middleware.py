"""
Session-scoped tool filtering middleware for FastMCP.

This middleware enables per-session tool enable/disable functionality,
allowing different MCP clients to have different tool availability
without affecting the global tool registry.

Key Features:
- Per-session tool disable/enable tracking
- Filters tools in list_tools based on session state
- Blocks execution of session-disabled tools in call_tool
- Non-invasive (doesn't modify global tool state)
- Thread-safe using session storage from auth/context.py
- **Minimal Startup Mode**: New sessions start with only protected tools
- **Session Persistence**: Tool states persist across reconnections
"""

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from fastmcp.server.middleware import Middleware, MiddlewareContext

# Import HTTP request access for query parameter parsing
try:
    from fastmcp.server.dependencies import get_http_request

    HTTP_REQUEST_AVAILABLE = True
except ImportError:
    HTTP_REQUEST_AVAILABLE = False
    get_http_request = None

from auth.context import (
    clear_minimal_startup_applied,
    clear_session_disabled_tools,
    clear_session_disabled_tools_sync,
    disable_tool_for_session,
    disable_tool_for_session_sync,
    get_effective_session_id,
    get_session_context,
    get_session_disabled_tools,
    get_user_email_context,
    get_user_email_context_sync,
    is_known_session,
    is_tool_enabled_for_session,
    mark_minimal_startup_applied,
    persist_session_tool_states,
    restore_session_tool_state,
    restore_session_tool_state_by_email,
    set_effective_session_id,
    was_minimal_startup_applied,
)
from config.enhanced_logging import setup_logger

logger = setup_logger()


def get_service_for_tool(tool_name: str) -> str:
    """
    Get the service that a tool belongs to using the existing qdrant_core utility.

    This leverages the centralized extract_service_from_tool function which uses
    keyword matching to determine the service from tool names.

    Args:
        tool_name: Name of the tool.

    Returns:
        Service name (e.g., 'gmail', 'drive', 'calendar') or 'unknown'.
    """
    try:
        from middleware.qdrant_core.query_parser import extract_service_from_tool

        return extract_service_from_tool(tool_name)
    except ImportError:
        logger.warning("Could not import extract_service_from_tool, using fallback")
        # Fallback: basic keyword matching
        tool_lower = tool_name.lower()
        service_keywords = {
            "gmail": "gmail",
            "mail": "gmail",
            "email": "gmail",
            "drive": "drive",
            "file": "drive",
            "folder": "drive",
            "calendar": "calendar",
            "event": "calendar",
            "docs": "docs",
            "document": "docs",
            "sheets": "sheets",
            "spreadsheet": "sheets",
            "slides": "slides",
            "presentation": "slides",
            "photos": "photos",
            "photo": "photos",
            "chat": "chat",
            "message": "chat",
            "space": "chat",
            "forms": "forms",
            "form": "forms",
            "people": "people",
            "contact": "people",
        }
        for keyword, service in service_keywords.items():
            if keyword in tool_lower:
                return service
        return "unknown"


def get_tools_for_services(all_tools: List[str], services: List[str]) -> Set[str]:
    """
    Filter tools to get only those belonging to the specified services.

    Uses the centralized extract_service_from_tool function to determine
    which service each tool belongs to.

    Args:
        all_tools: List of all available tool names.
        services: List of service names from ScopeRegistry (e.g., ['drive', 'gmail']).

    Returns:
        Set of tool names belonging to those services.
    """
    services_lower = {s.lower() for s in services}
    matched_tools = set()

    for tool_name in all_tools:
        tool_service = get_service_for_tool(tool_name)
        if tool_service.lower() in services_lower:
            matched_tools.add(tool_name)

    return matched_tools


def _parse_request_params(request) -> Dict[str, Any]:
    """
    Parse connection parameters directly from a request object.

    This is used when we have direct access to the request (e.g., from middleware context).
    """
    result = {
        "services": None,
        "uuid": None,
        "minimal_override": None,
        "raw_params": {},
    }

    try:
        if not hasattr(request, "query_params"):
            return result

        query_params = dict(request.query_params)
        result["raw_params"] = query_params

        # Parse service parameter: ?service=drive,gmail,chat
        if "service" in query_params:
            service_str = query_params["service"]
            services = [s.strip().lower() for s in service_str.split(",") if s.strip()]
            if services:
                result["services"] = services
                logger.info(f"🔗 Request param: services={services}")
        elif "services" in query_params:
            service_str = query_params["services"]
            services = [s.strip().lower() for s in service_str.split(",") if s.strip()]
            if services:
                result["services"] = services
                logger.info(f"🔗 Request param: services={services}")

        # Parse UUID parameter
        if "uuid" in query_params:
            uuid_value = query_params["uuid"].strip()
            if uuid_value:
                result["uuid"] = uuid_value
                logger.info(f"🔗 Request param: uuid={uuid_value[:8]}...")
        elif "session_id" in query_params:
            uuid_value = query_params["session_id"].strip()
            if uuid_value:
                result["uuid"] = uuid_value

        # Parse minimal override
        if "minimal" in query_params:
            minimal_value = query_params["minimal"].strip().lower()
            if minimal_value in ("true", "1", "yes"):
                result["minimal_override"] = True
            elif minimal_value in ("false", "0", "no"):
                result["minimal_override"] = False

        return result

    except Exception as e:
        logger.debug(f"Error parsing request params: {e}")
        return result


def parse_http_connection_params() -> Dict[str, Any]:
    """
    Parse HTTP connection parameters from the URL query string.

    Supports the following parameters:
    - service: Comma-separated list of services to enable (e.g., "drive,gmail,chat")
    - uuid: Session UUID to resume a previous session
    - minimal: Override minimal startup mode ("true"/"false")

    Returns:
        Dict with parsed parameters:
        {
            "services": List[str] or None,
            "uuid": str or None,
            "minimal_override": bool or None,
            "raw_params": dict  # All query params for debugging
        }
    """
    result = {
        "services": None,
        "uuid": None,
        "minimal_override": None,
        "raw_params": {},
    }

    if not HTTP_REQUEST_AVAILABLE:
        logger.debug("🔍 HTTP_REQUEST_AVAILABLE is False, skipping HTTP param parsing")
        return result

    try:
        request = get_http_request()
        logger.debug(f"🔍 get_http_request() returned: {type(request)}")
        if request is None:
            logger.debug("🔍 Request is None, skipping HTTP param parsing")
            return result

        # Get query parameters from the request
        query_params = dict(request.query_params)
        logger.info(f"🔍 Parsed query_params: {query_params}")
        result["raw_params"] = query_params

        # Parse service parameter: ?service=drive,gmail,chat
        if "service" in query_params:
            service_str = query_params["service"]
            services = [s.strip().lower() for s in service_str.split(",") if s.strip()]
            if services:
                result["services"] = services
                logger.info(f"🔗 HTTP connection parameter: services={services}")

        # Also support plural form: ?services=drive,gmail
        elif "services" in query_params:
            service_str = query_params["services"]
            services = [s.strip().lower() for s in service_str.split(",") if s.strip()]
            if services:
                result["services"] = services
                logger.info(f"🔗 HTTP connection parameter: services={services}")

        # Parse UUID parameter: ?uuid=xyz123
        if "uuid" in query_params:
            uuid_value = query_params["uuid"].strip()
            if uuid_value:
                result["uuid"] = uuid_value
                logger.info(f"🔗 HTTP connection parameter: uuid={uuid_value[:8]}...")

        # Also support session_id: ?session_id=xyz123
        elif "session_id" in query_params:
            uuid_value = query_params["session_id"].strip()
            if uuid_value:
                result["uuid"] = uuid_value
                logger.info(
                    f"🔗 HTTP connection parameter: session_id={uuid_value[:8]}..."
                )

        # Parse minimal override: ?minimal=false
        if "minimal" in query_params:
            minimal_value = query_params["minimal"].strip().lower()
            if minimal_value in ("true", "1", "yes"):
                result["minimal_override"] = True
                logger.info(
                    "🔗 HTTP connection parameter: minimal=true (force minimal startup)"
                )
            elif minimal_value in ("false", "0", "no"):
                result["minimal_override"] = False
                logger.info(
                    "🔗 HTTP connection parameter: minimal=false (disable minimal startup)"
                )

        return result

    except RuntimeError as e:
        # Expected when not in HTTP context (e.g., STDIO transport)
        logger.debug(f"🔍 RuntimeError in parse_http_connection_params: {e}")
        return result
    except Exception as e:
        logger.warning(f"🔍 Unexpected error in parse_http_connection_params: {e}")
        return result


class SessionToolFilteringMiddleware(Middleware):
    """
    Middleware that filters tools based on per-session enabled/disabled state.

    This middleware intercepts list_tools and call_tool operations to enforce
    session-specific tool availability. Tools disabled via session-scoped
    manage_tools calls will be hidden from listing and blocked from execution
    for that session only.

    Features:
    - **Minimal Startup Mode**: When enabled, new sessions start with only
      protected tools. Tools are enabled on-demand based on usage.
    - **Session Persistence**: Tool states are persisted to disk, allowing
      returning sessions (reconnects) to restore their previous tool state.

    Usage:
        # In server.py
        session_filter_middleware = SessionToolFilteringMiddleware(
            minimal_startup=True,  # Enable minimal startup mode
        )
        mcp.add_middleware(session_filter_middleware)

        # Then in manage_tools with scope="session"
        # Tools are disabled in session state, and this middleware filters them
    """

    def __init__(
        self,
        protected_tools: Optional[Set[str]] = None,
        enable_debug: bool = False,
        minimal_startup: bool = False,
        get_all_tools_callback: Optional[Callable[[], List[str]]] = None,
        default_enabled_services: Optional[List[str]] = None,
        mcp_instance: Optional[Any] = None,
    ):
        """
        Initialize the session tool filtering middleware.

        Args:
            protected_tools: Set of tool names that should never be filtered
                            (always visible regardless of session state).
                            Defaults to core management tools.
            enable_debug: If True, enables verbose debug logging.
            minimal_startup: If True, new sessions start with only protected
                            tools enabled. Returning sessions restore their
                            previous tool state.
            get_all_tools_callback: Optional callback to get all registered tool
                                   names. Used for minimal startup mode to know
                                   which tools to disable for new sessions.
            default_enabled_services: List of service names (from ScopeRegistry)
                                     whose tools should be enabled by default
                                     for new sessions in minimal startup mode.
            mcp_instance: Optional FastMCP server instance for updating instructions.
        """
        self.protected_tools = protected_tools or {
            "manage_tools",
            "search",
            "health_check",
            "start_google_auth",
            "check_drive_auth",
        }
        self.enable_debug = enable_debug
        self.minimal_startup = minimal_startup
        self.get_all_tools_callback = get_all_tools_callback
        self.default_enabled_services = default_enabled_services or []
        self.mcp_instance = mcp_instance

        # Track sessions we've already processed for minimal startup
        self._processed_sessions: Set[str] = set()

        if self.minimal_startup:
            logger.info(
                "🚀 SessionToolFilteringMiddleware: Minimal startup mode ENABLED"
            )
            logger.info(
                f"   Protected tools (always available): {sorted(self.protected_tools)}"
            )
            if self.default_enabled_services:
                logger.info(
                    f"   Default enabled services: {self.default_enabled_services}"
                )
                logger.info(
                    "   (Service tools will be computed dynamically using extract_service_from_tool)"
                )

    def set_all_tools_callback(self, callback: Callable[[], List[str]]) -> None:
        """
        Set the callback to get all registered tool names.

        This is typically called from server.py after tools are registered,
        since tools may not all be registered at middleware init time.

        Args:
            callback: Function that returns list of all tool names.
        """
        self.get_all_tools_callback = callback
        if self.enable_debug:
            logger.debug(
                "SessionToolFilteringMiddleware: Tool list callback registered"
            )

    async def _refresh_instructions_for_session(
        self, session_id: str, tool_names: List[str]
    ) -> None:
        """
        Refresh MCP instructions to reflect session-enabled services only.

        This updates the instructions to show only the services that have
        at least one enabled tool for this session, providing accurate
        guidance to the client about available functionality.

        Args:
            session_id: The session ID to refresh instructions for.
            tool_names: List of all tool names (for computing enabled services).
        """
        if not self.mcp_instance:
            if self.enable_debug:
                logger.debug("Cannot refresh instructions - no MCP instance available")
            return

        try:
            from tools.dynamic_instructions import refresh_instructions_for_session

            success = await refresh_instructions_for_session(
                self.mcp_instance, session_id, tool_names
            )
            if success:
                logger.info(
                    f"📋 Instructions refreshed for session {session_id[:8]}... "
                    f"with session-enabled services only"
                )
            else:
                logger.warning(
                    f"⚠️ Failed to refresh instructions for session {session_id[:8]}..."
                )
        except Exception as e:
            logger.warning(f"⚠️ Error refreshing instructions: {e}")

    def _get_all_tool_names(self) -> List[str]:
        """Get all registered tool names using the callback."""
        if self.get_all_tools_callback:
            return self.get_all_tools_callback()
        return []

    def _apply_minimal_startup_for_session(
        self,
        session_id: str,
        custom_services: Optional[List[str]] = None,
        tool_names: Optional[List[str]] = None,
    ) -> None:
        """
        Apply minimal startup restrictions for a new session.

        Disables all tools except:
        - Protected infrastructure tools
        - Tools belonging to enabled services (custom_services or default_enabled_services)

        Args:
            session_id: The session ID to apply restrictions to.
            custom_services: Optional list of services from HTTP ?service= parameter.
                           If provided, overrides default_enabled_services.
            tool_names: Optional list of tool names (from on_list_tools).
                       If provided, used instead of callback.
        """
        if not self.minimal_startup:
            return

        # Check if already applied (in-memory or persisted)
        if session_id in self._processed_sessions:
            if self.enable_debug:
                logger.debug(
                    f"Minimal startup already applied for session {session_id[:8]}... (in-memory)"
                )
            return

        if was_minimal_startup_applied(session_id):
            self._processed_sessions.add(session_id)
            if self.enable_debug:
                logger.debug(
                    f"Minimal startup already applied for session {session_id[:8]}... (persisted)"
                )
            return

        # Get all tool names - prefer passed parameter, fall back to callback
        all_tools = tool_names if tool_names else self._get_all_tool_names()
        if not all_tools:
            logger.warning(
                "SessionToolFilteringMiddleware: No tools available for minimal startup"
            )
            return

        # Determine which services to enable (HTTP params override default)
        enabled_services = (
            custom_services if custom_services else self.default_enabled_services
        )
        from_http = custom_services is not None

        # Compute tools for enabled services dynamically
        # This uses extract_service_from_tool from qdrant_core to determine service membership
        service_tools = set()
        if enabled_services:
            service_tools = get_tools_for_services(all_tools, enabled_services)
            if self.enable_debug:
                logger.debug(
                    f"Tools for services {enabled_services}: {sorted(service_tools)}"
                )

        # Combine protected tools with enabled service tools
        keep_enabled = set(self.protected_tools) | service_tools

        # Disable all non-protected, non-service tools
        disabled_count = 0
        for tool_name in all_tools:
            if tool_name not in keep_enabled:
                disable_tool_for_session_sync(tool_name, session_id)
                disabled_count += 1

        enabled_count = len(all_tools) - disabled_count

        # Mark as applied
        mark_minimal_startup_applied(session_id)
        self._processed_sessions.add(session_id)

        # Build log message
        if from_http:
            source_msg = f" (from ?service= URL param)"
        else:
            source_msg = ""
        services_msg = (
            f", services: {enabled_services}{source_msg}" if enabled_services else ""
        )

        logger.info(
            f"🔒 Minimal startup applied for NEW session {session_id[:8]}... "
            f"({disabled_count} tools disabled, {enabled_count} enabled{services_msg})"
        )

    def _handle_session_connection(
        self,
        session_id: str,
        http_params: Optional[Dict[str, Any]] = None,
        tool_names: Optional[List[str]] = None,
    ) -> Tuple[str, bool]:
        """
        Handle a session connection - restore state for known sessions,
        or apply minimal startup for new sessions.

        Supports HTTP connection parameters:
        - ?uuid=xyz123: Resume a specific persisted session
        - ?service=drive,gmail: Enable only specific services (ALWAYS applies, even on reconnect)
        - ?minimal=false: Override minimal startup mode

        IMPORTANT: ?service= parameter ALWAYS takes precedence over session restoration.
        This ensures that connecting with ?service=gmail,drive will always filter to those
        services, even if the session was previously known with different tool states.

        Args:
            session_id: The session ID that just connected.
            http_params: Optional HTTP connection parameters from URL query string.
            tool_names: Optional list of tool names (from on_list_tools).
                       If provided, used instead of callback for service filtering.

        Returns:
            Tuple of (effective_session_id, was_restored)
        """
        if not session_id:
            return session_id, False

        http_params = http_params or {}
        effective_session_id = session_id
        was_restored = False

        # IMPORTANT: Extract custom_services FIRST - it takes precedence over session restoration
        # If ?service= is provided, we should NOT restore old session state, but apply the new filter
        custom_services = http_params.get("services")
        has_explicit_service_filter = (
            custom_services is not None and len(custom_services) > 0
        )

        # Check for UUID parameter to resume a specific session
        requested_uuid = http_params.get("uuid")
        if requested_uuid:
            # If both ?uuid= and ?service= are provided, ?service= takes precedence
            # The UUID is still used as the session identifier, but we apply fresh service filtering
            if has_explicit_service_filter:
                logger.info(
                    f"🔗 Using UUID {requested_uuid[:8]}... with fresh service filter "
                    f"(services={custom_services})"
                )
                effective_session_id = requested_uuid
                # Don't restore - will apply service filter below
            elif is_known_session(requested_uuid):
                # No ?service= provided, try to restore the requested session
                restored = restore_session_tool_state(requested_uuid)
                if restored:
                    self._processed_sessions.add(requested_uuid)
                    logger.info(
                        f"🔄 Resumed session {requested_uuid[:8]}... via ?uuid= parameter"
                    )
                    return requested_uuid, True
                else:
                    logger.warning(
                        f"⚠️ Could not restore session {requested_uuid[:8]}... "
                        f"(not found in persistence), using new session"
                    )
                    effective_session_id = requested_uuid
            else:
                # UUID provided but session not found - create new session with this UUID
                logger.info(
                    f"🆕 Creating new session with requested UUID: {requested_uuid[:8]}..."
                )
                effective_session_id = requested_uuid

        # If ?service= is provided, skip session restoration entirely
        # This ensures the service filter is always applied fresh
        if not has_explicit_service_filter:
            # Skip restoration for sessions already processed in this server lifetime.
            # Once a session is known in-memory (e.g. manage_tools cleared its disabled
            # set), re-restoring from disk would overwrite those changes.
            if effective_session_id in self._processed_sessions:
                if self.enable_debug:
                    logger.debug(
                        f"Session {effective_session_id[:8]}... already processed, "
                        f"using in-memory state (skipping persistence restore)"
                    )
                return effective_session_id, False

            # Check if this is a known session (returning client)
            if is_known_session(effective_session_id):
                # Try to restore persisted state
                restored = restore_session_tool_state(effective_session_id)
                if restored:
                    self._processed_sessions.add(effective_session_id)
                    if self.enable_debug:
                        logger.debug(
                            f"Session {effective_session_id[:8]}... restored from persistence"
                        )
                    return effective_session_id, True

            # Session ID not known - try to restore by user email
            # This handles STDIO transport reconnections where session ID changes but user is same
            user_email = get_user_email_context_sync()
            if user_email:
                restored_by_email = restore_session_tool_state_by_email(
                    effective_session_id, user_email
                )
                if restored_by_email:
                    self._processed_sessions.add(effective_session_id)
                    logger.info(
                        f"🔄 Restored session {effective_session_id[:8]}... from previous "
                        f"session for user {user_email}"
                    )
                    return effective_session_id, True

        # New session OR explicit service filter provided - determine startup mode
        minimal_override = http_params.get("minimal_override")
        should_apply_minimal = self.minimal_startup

        if minimal_override is not None:
            should_apply_minimal = minimal_override
            if minimal_override:
                logger.info(
                    f"🔗 Minimal startup FORCED via ?minimal=true for session {effective_session_id[:8]}..."
                )
            else:
                logger.info(
                    f"🔗 Minimal startup DISABLED via ?minimal=false for session {effective_session_id[:8]}..."
                )

        # If explicit ?service= is provided, apply filter ONLY for NEW sessions
        # Once a session is processed, don't clear/reapply - this preserves manual tool enables
        # This must happen AFTER effective_session_id is finalized (e.g., after UUID processing)
        session_already_processed = effective_session_id in self._processed_sessions

        if has_explicit_service_filter and not session_already_processed:
            # First time seeing this session with a service filter - apply it
            if self.enable_debug:
                logger.debug(
                    f"Applying service filter for NEW session {effective_session_id[:8]}... "
                    f"(services={custom_services})"
                )
        elif has_explicit_service_filter and session_already_processed:
            # Session already processed - preserve existing tool state, don't reapply filter
            if self.enable_debug:
                logger.debug(
                    f"Session {effective_session_id[:8]}... already processed, "
                    f"preserving tool state (not reapplying ?service= filter)"
                )
            return effective_session_id, True  # Treat as restored to skip reapplication

        # Apply minimal startup if enabled (uses custom_services if provided)
        if should_apply_minimal:
            self._apply_minimal_startup_for_session(
                effective_session_id,
                custom_services=custom_services,
                tool_names=tool_names,
            )
        elif has_explicit_service_filter:
            # Explicit ?service= parameter always applies the service filter
            logger.info(
                f"🔗 Applying explicit service filter for session {effective_session_id[:8]}...: "
                f"services={custom_services}"
            )
            self._apply_service_filter_for_session(
                effective_session_id, custom_services, tool_names=tool_names
            )

        return effective_session_id, was_restored

    def _apply_service_filter_for_session(
        self,
        session_id: str,
        services: List[str],
        tool_names: Optional[List[str]] = None,
    ) -> None:
        """
        Apply a service filter to enable only specific services for a session.

        This is used when ?service=drive,gmail is provided but minimal startup is disabled.
        It disables all tools except those belonging to the specified services.

        Args:
            session_id: The session ID to apply the filter to.
            services: List of service names to enable.
            tool_names: Optional list of tool names (from on_list_tools).
                       If provided, used instead of callback.
        """
        # Get all tool names - prefer passed parameter, fall back to callback
        all_tools = tool_names if tool_names else self._get_all_tool_names()
        if not all_tools:
            logger.warning(
                "SessionToolFilteringMiddleware: No tools available for service filter"
            )
            return

        # Get tools for the specified services
        service_tools = get_tools_for_services(all_tools, services)

        # Combine protected tools with service tools
        keep_enabled = set(self.protected_tools) | service_tools

        # Disable all non-protected, non-service tools
        disabled_count = 0
        for tool_name in all_tools:
            if tool_name not in keep_enabled:
                disable_tool_for_session_sync(tool_name, session_id)
                disabled_count += 1

        enabled_count = len(all_tools) - disabled_count

        # Mark as processed
        self._processed_sessions.add(session_id)

        logger.info(
            f"🔗 Service filter applied for session {session_id[:8]}...: "
            f"services={services}, {disabled_count} disabled, {enabled_count} enabled"
        )

    async def on_list_tools(self, context: MiddlewareContext, call_next) -> List[Any]:
        """
        Filter the tool list based on session-specific disabled tools.

        This hook runs when a client requests the list of available tools.
        It removes any tools that have been disabled for the current session.

        For minimal startup mode, this also handles:
        - Detecting new vs returning sessions
        - Restoring tool state for returning sessions
        - Applying minimal restrictions for new sessions
        - Parsing HTTP connection parameters (?service=, ?uuid=, ?minimal=)

        Args:
            context: The middleware context containing request information.
            call_next: Callable to invoke the next middleware or handler.

        Returns:
            Filtered list of tools visible to this session.
        """
        # Get the full list of tools from downstream
        all_tools = await call_next(context)

        # Get current session ID
        session_id = await get_session_context()

        if not session_id:
            # No session context - return all tools (global state only)
            if self.enable_debug:
                logger.debug(
                    "SessionToolFilteringMiddleware: No session context, returning all tools"
                )
            return all_tools

        # Parse HTTP connection parameters (for HTTP/SSE transport)
        # Supports: ?service=drive,gmail, ?uuid=xyz123, ?minimal=false
        # Try to get request from middleware context first (FastMCP v3 pattern)
        http_params = None
        if context.fastmcp_context:
            ctx = context.fastmcp_context
            logger.debug(
                f"🔍 fastmcp_context available, request_context: {ctx.request_context}"
            )
            if ctx.request_context and ctx.request_context.request:
                request = ctx.request_context.request
                if hasattr(request, "query_params"):
                    logger.info(
                        f"🔍 Got request from fastmcp_context, query_params: {dict(request.query_params)}"
                    )
                    http_params = _parse_request_params(request)

        # Fallback to global get_http_request() if context method failed
        if http_params is None:
            http_params = parse_http_connection_params()
        logger.info(f"🔍 on_list_tools: http_params={http_params}")

        # Extract tool names from the tools list (FastMCP v3 compatible)
        # This avoids relying on internal _tool_manager which changed in v3
        tool_names = [getattr(tool, "name", None) for tool in all_tools]
        tool_names = [name for name in tool_names if name]  # Filter out None values

        # Handle session connection (restore or apply minimal startup)
        # This is idempotent - won't re-apply if already processed
        # Returns the effective session ID (may be different if ?uuid= was provided)
        effective_session_id, was_restored = self._handle_session_connection(
            session_id, http_params, tool_names=tool_names
        )

        # Store the effective session ID in context for use by on_call_tool
        # This ensures consistency between list_tools and call_tool operations
        if effective_session_id != session_id:
            await set_effective_session_id(effective_session_id)
            if self.enable_debug:
                logger.debug(
                    f"Stored effective session ID {effective_session_id[:8]}... "
                    f"(differs from transport session {session_id[:8]}...)"
                )

        # Use the effective session ID for filtering
        session_id = effective_session_id

        # Refresh instructions to reflect session-enabled services
        # This ensures the instructions shown to the client match the available tools
        # Only refresh if we have an MCP instance and service filter was applied
        has_service_filter = http_params.get("services") is not None
        if has_service_filter or (self.minimal_startup and not was_restored):
            await self._refresh_instructions_for_session(session_id, tool_names)

        # Get session-specific disabled tools (may have just been set by minimal startup)
        session_disabled = await get_session_disabled_tools(session_id)

        if not session_disabled:
            # No session-specific disables - return all tools
            if self.enable_debug:
                logger.debug(
                    f"SessionToolFilteringMiddleware: Session {session_id[:8]}... has no disabled tools"
                )
            return all_tools

        # Filter out session-disabled tools (except protected ones)
        filtered_tools = []
        hidden_count = 0

        for tool in all_tools:
            tool_name = getattr(tool, "name", None)

            if not tool_name:
                # Tool without name - include it
                filtered_tools.append(tool)
                continue

            # Protected tools are always visible
            if tool_name in self.protected_tools:
                filtered_tools.append(tool)
                continue

            # Check if tool is disabled for this session
            if tool_name in session_disabled:
                hidden_count += 1
                if self.enable_debug:
                    logger.debug(
                        f"SessionToolFilteringMiddleware: Hiding tool '{tool_name}' for session {session_id[:8]}..."
                    )
                continue

            # Tool is enabled for this session
            filtered_tools.append(tool)

        if hidden_count > 0:
            logger.info(
                f"SessionToolFilteringMiddleware: Filtered {hidden_count} tools for session {session_id[:8]}... "
                f"({len(filtered_tools)} visible, {len(session_disabled)} session-disabled)"
            )

        return filtered_tools

    async def on_call_tool(self, context: MiddlewareContext, call_next) -> Any:
        """
        Block execution of session-disabled tools.

        This hook ensures consistency between listing and execution -
        if a tool is hidden from listing, it should also fail if called directly.

        IMPORTANT: Uses get_effective_session_id() to ensure consistency with
        on_list_tools when ?uuid= parameter is used to resume a session.

        Args:
            context: The middleware context containing the tool call request.
            call_next: Callable to invoke the next middleware or handler.

        Returns:
            Tool execution result if allowed, or error if tool is session-disabled.

        Raises:
            ValueError: If the tool is disabled for this session.
        """
        # Extract tool name from the request (context.message is CallToolRequestParams in v3)
        tool_name = context.message.name

        if not tool_name:
            # Can't determine tool name - let it through
            return await call_next(context)

        # Protected tools always execute
        if tool_name in self.protected_tools:
            return await call_next(context)

        # Check session state using EFFECTIVE session ID
        # This ensures consistency with on_list_tools when ?uuid= is used
        session_id = await get_effective_session_id()

        if session_id and not await is_tool_enabled_for_session(tool_name, session_id):
            logger.warning(
                f"SessionToolFilteringMiddleware: Blocked execution of session-disabled tool "
                f"'{tool_name}' for session {session_id[:8]}..."
            )
            raise ValueError(
                f"Tool '{tool_name}' is disabled for this session. "
                f"Use manage_tools with scope='session' and action='enable' to re-enable it."
            )

        # Tool is enabled - proceed with execution
        return await call_next(context)


def setup_session_tool_filtering_middleware(
    mcp,
    protected_tools: Optional[Set[str]] = None,
    enable_debug: bool = False,
    minimal_startup: bool = None,
    default_enabled_services: Optional[List[str]] = None,
) -> SessionToolFilteringMiddleware:
    """
    Create and register the session tool filtering middleware.

    Args:
        mcp: The FastMCP server instance.
        protected_tools: Set of tool names that should never be filtered.
        enable_debug: If True, enables verbose debug logging.
        minimal_startup: If True, new sessions start with minimal tools.
                        If None, reads from settings.minimal_tools_startup.
        default_enabled_services: List of services whose tools should be
                                 enabled by default. If None, reads from
                                 settings.get_minimal_startup_services().

    Returns:
        The configured SessionToolFilteringMiddleware instance.
    """
    # Load settings if not explicitly provided
    try:
        from config.settings import settings

        if minimal_startup is None:
            minimal_startup = settings.minimal_tools_startup
        if default_enabled_services is None:
            default_enabled_services = settings.get_minimal_startup_services()
    except Exception:
        if minimal_startup is None:
            minimal_startup = False
        if default_enabled_services is None:
            default_enabled_services = []

    # Create callback to get all tool names from the MCP server
    def get_all_tools() -> List[str]:
        """Get all registered tool names from the MCP server."""
        try:
            from fastmcp.tools.tool import Tool

            components = mcp.local_provider._components
            return [v.name for v in components.values() if isinstance(v, Tool)]
        except Exception as e:
            logger.error(f"Error getting tool names: {e}")
            return []

    middleware = SessionToolFilteringMiddleware(
        protected_tools=protected_tools,
        enable_debug=enable_debug,
        minimal_startup=minimal_startup,
        get_all_tools_callback=get_all_tools,
        default_enabled_services=default_enabled_services,
        mcp_instance=mcp,
    )

    mcp.add_middleware(middleware)

    if minimal_startup:
        logger.info(
            "✅ SessionToolFilteringMiddleware enabled with MINIMAL STARTUP mode"
        )
        logger.info("   • New sessions start with only protected tools")
        if default_enabled_services:
            logger.info(f"   • Default enabled services: {default_enabled_services}")
            logger.info(
                "   • Service-to-tool mapping via extract_service_from_tool (qdrant_core)"
            )
        logger.info("   • Returning sessions restore their previous tool state")
        logger.info("   • Tool states persist across server restarts")
    else:
        logger.info(
            "✅ SessionToolFilteringMiddleware enabled for per-session tool management"
        )

    return middleware


# Export helper functions for use by other modules
__all__ = [
    "SessionToolFilteringMiddleware",
    "setup_session_tool_filtering_middleware",
    "get_service_for_tool",
    "get_tools_for_services",
    "parse_http_connection_params",
]
