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
- State lives in the per-principal bucket (auth/user_state.py), so it is
  shared by every connection a user opens and survives the per-request
  sessions of MCP 2026-07-28
- **Minimal Startup Mode**: a user's first connection starts with only
  protected tools; later connections keep whatever they enabled
"""

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.types import ToolListChangedNotification

# Import HTTP request access for query parameter parsing
try:
    from fastmcp.server.dependencies import get_http_request

    HTTP_REQUEST_AVAILABLE = True
except ImportError:
    HTTP_REQUEST_AVAILABLE = False
    get_http_request = None

from auth.context import get_session_context
from auth.user_state import (
    DISABLED_TOOLS_KEY,
    STARTUP_APPLIED_KEY,
    STARTUP_SERVICES_KEY,
    UserBucket,
    disabled_tools_from_state,
    get_disabled_tools,
    principal_email,
    user_bucket,
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
            "qdrant_search",
            "health_check",
            "start_google_auth",
            "check_drive_auth",
            # CodeMode meta-tools (FastMCP 3.1.0+)
            "tags",
            "search",
            "get_schema",
            "execute",
            "fetch_document",
            "semantic_search",
            "tool_activity",
        }
        self.enable_debug = enable_debug
        self.minimal_startup = minimal_startup
        self.get_all_tools_callback = get_all_tools_callback
        self.default_enabled_services = default_enabled_services or []
        self.mcp_instance = mcp_instance

        # Principals that have already received a tool list changed notification
        # (keyed by the bucket's hashed principal segment). Prevents notification
        # spam on repeated list_tools calls.
        self._notified_principals: Set[str] = set()

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

    def _startup_disabled_set(
        self, all_tools: List[str], services: Optional[List[str]]
    ) -> Set[str]:
        """Tools to disable so only protected tools and ``services`` remain.

        ``services`` is the explicit ``?service=`` filter when given, else the
        configured default services for minimal startup. Membership comes
        from ``extract_service_from_tool``.
        """
        enabled_services = services if services else self.default_enabled_services
        service_tools: Set[str] = set()
        if enabled_services:
            service_tools = get_tools_for_services(all_tools, enabled_services)
            if self.enable_debug:
                logger.debug(
                    f"Tools for services {enabled_services}: {sorted(service_tools)}"
                )
        keep_enabled = set(self.protected_tools) | service_tools
        return {name for name in all_tools if name not in keep_enabled}

    async def _resolve_disabled_tools(
        self,
        bucket: UserBucket,
        http_params: Dict[str, Any],
        tool_names: List[str],
    ) -> Tuple[Set[str], bool]:
        """Load the principal's disabled set, applying startup rules on first sight.

        One bucket read, at most one write. Rules, in order:

        1. ``?service=a,b`` applies a fresh service filter the first time that
           exact filter is seen for this principal. Reconnecting with the same
           filter keeps whatever the user enabled since; a different filter
           re-applies.
        2. Minimal startup (setting, or ``?minimal=`` override) disables all but
           protected and default-service tools once, for a principal with no
           recorded state. A returning user is never re-restricted.
        3. A principal with no record yet gets one written — importing the
           retired ``session_tool_states.json`` entry for their email when one
           exists — so later reads are one store lookup.

        Returns ``(disabled_tools, filter_applied)``.
        """
        state = await bucket.load()
        email = principal_email()
        has_record = DISABLED_TOOLS_KEY in state
        disabled = disabled_tools_from_state(state, email)

        services = http_params.get("services") or None
        minimal_override = http_params.get("minimal_override")
        apply_minimal = (
            self.minimal_startup if minimal_override is None else bool(minimal_override)
        )
        if minimal_override is not None:
            logger.info(
                f"🔗 Minimal startup {'FORCED' if minimal_override else 'DISABLED'} "
                f"via ?minimal= for principal {bucket.segment[:8]}..."
            )

        changes: Dict[str, Any] = {}
        applied = False
        if services and services != state.get(STARTUP_SERVICES_KEY):
            disabled = self._startup_disabled_set(tool_names, services)
            changes = {
                DISABLED_TOOLS_KEY: sorted(disabled),
                STARTUP_APPLIED_KEY: True,
                STARTUP_SERVICES_KEY: list(services),
            }
            applied = True
            logger.info(
                f"🔗 Service filter applied for principal {bucket.segment[:8]}...: "
                f"services={services}, {len(disabled)} disabled, "
                f"{len(tool_names) - len(disabled)} enabled"
            )
        elif apply_minimal and not has_record and not state.get(STARTUP_APPLIED_KEY):
            if not tool_names:
                logger.warning(
                    "SessionToolFilteringMiddleware: No tools available for minimal startup"
                )
            else:
                disabled = self._startup_disabled_set(tool_names, None)
                changes = {
                    DISABLED_TOOLS_KEY: sorted(disabled),
                    STARTUP_APPLIED_KEY: True,
                }
                applied = True
                services_msg = (
                    f", services: {self.default_enabled_services}"
                    if self.default_enabled_services
                    else ""
                )
                logger.info(
                    f"🔒 Minimal startup applied for NEW principal {bucket.segment[:8]}... "
                    f"({len(disabled)} tools disabled, "
                    f"{len(tool_names) - len(disabled)} enabled{services_msg})"
                )
        elif not has_record:
            changes = {DISABLED_TOOLS_KEY: sorted(disabled)}

        if changes:
            await bucket.update(changes)
        return disabled, applied

    async def on_list_tools(self, context: MiddlewareContext, call_next) -> List[Any]:
        """
        Filter the tool list based on the principal's disabled tools.

        Also applies the startup rules for a principal seen for the first time
        (minimal startup, ``?service=`` filter, ``?minimal=`` override) and
        imports any state left in the retired per-session JSON file.

        Args:
            context: The middleware context containing request information.
            call_next: Callable to invoke the next middleware or handler.

        Returns:
            Filtered list of tools visible to this principal.
        """
        all_tools = await call_next(context)

        # Parse HTTP connection parameters (for HTTP/SSE transport)
        # Supports: ?service=drive,gmail, ?minimal=false
        http_params = None
        if context.fastmcp_context:
            ctx = context.fastmcp_context
            if ctx.request_context and ctx.request_context.request:
                request = ctx.request_context.request
                if hasattr(request, "query_params"):
                    http_params = _parse_request_params(request)
        if http_params is None:
            http_params = parse_http_connection_params()

        tool_names = [getattr(tool, "name", None) for tool in all_tools]
        tool_names = [name for name in tool_names if name]

        bucket = user_bucket()
        try:
            session_disabled, applied = await self._resolve_disabled_tools(
                bucket, http_params, tool_names
            )
        except Exception as exc:
            # A state-store outage must not hide the catalog.
            logger.warning(
                f"SessionToolFilteringMiddleware: could not read user state "
                f"({exc}); returning the unfiltered tool list"
            )
            return all_tools

        if applied and self.mcp_instance:
            session_id = await get_session_context() or "-"
            await self._refresh_instructions_for_session(session_id, tool_names)

        if not session_disabled:
            if self.enable_debug:
                logger.debug(
                    f"SessionToolFilteringMiddleware: principal {bucket.segment[:8]}... "
                    f"has no disabled tools"
                )
            return all_tools

        filtered_tools = []
        hidden_count = 0
        for tool in all_tools:
            tool_name = getattr(tool, "name", None)
            if not tool_name or tool_name in self.protected_tools:
                filtered_tools.append(tool)
                continue
            if tool_name in session_disabled:
                hidden_count += 1
                if self.enable_debug:
                    logger.debug(
                        f"SessionToolFilteringMiddleware: Hiding tool '{tool_name}' "
                        f"for principal {bucket.segment[:8]}..."
                    )
                continue
            filtered_tools.append(tool)

        if hidden_count > 0:
            logger.info(
                f"SessionToolFilteringMiddleware: Filtered {hidden_count} tools for "
                f"principal {bucket.segment[:8]}... ({len(filtered_tools)} visible, "
                f"{len(session_disabled)} disabled)"
            )
            # Tell clients that support it that the list differs from the full
            # server catalog. Once per principal per process to avoid spam.
            if bucket.segment not in self._notified_principals:
                self._notified_principals.add(bucket.segment)
                if context.fastmcp_context:
                    try:
                        await context.fastmcp_context.send_notification(
                            ToolListChangedNotification()
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to send ToolListChangedNotification: {e}"
                        )

        return filtered_tools

    async def on_call_tool(self, context: MiddlewareContext, call_next) -> Any:
        """
        Block execution of tools disabled for the calling principal.

        Keeps listing and execution consistent: a tool hidden from
        ``tools/list`` also fails when called directly. Because the check is
        keyed by principal, it holds for 2026-07-28 clients whose every request
        is a fresh transport session.

        Raises:
            ToolError: If the tool is disabled for this principal.
        """
        tool_name = context.message.name
        if not tool_name or tool_name in self.protected_tools:
            return await call_next(context)

        if tool_name in await get_disabled_tools():
            logger.warning(
                f"SessionToolFilteringMiddleware: Blocked execution of disabled tool "
                f"'{tool_name}'"
            )
            # ToolError keeps its message on the wire; a bare ValueError is
            # masked to "Internal server error" by the 2026-07-28 runner.
            raise ToolError(
                f"Tool '{tool_name}' is disabled for this session. "
                f"Use manage_tools with scope='session' and action='enable' to re-enable it."
            )

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
            from fastmcp.tools import Tool

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
