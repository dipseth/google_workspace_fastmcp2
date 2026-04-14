"""
FastMCP2 Server Management Tools.

This module provides server management and health monitoring tools for the
FastMCP2 Google Drive Upload Server, including health checks, server information,
and credential management.

Key Features:
- Server health monitoring with OAuth flow status
- Detailed server information and usage guide
- Credential management with storage mode migration
- Authentication status and session management
"""

import json
import os
from pathlib import Path

from fastmcp import Context, FastMCP
from fastmcp.apps import UI_EXTENSION_ID, AppConfig
from mcp.types import ToolListChangedNotification
from pydantic import Field
from typing_extensions import Annotated, Any, Dict, List, Literal, Optional, Union

from auth.context import (
    clear_session_disabled_tools,
    disable_tool_for_session,
    enable_tool_for_session,
    get_session_context,
    get_session_context_sync,
    get_session_disabled_tools,
    get_session_disabled_tools_sync,
)
from auth.middleware import CredentialStorageMode
from config.enhanced_logging import setup_logger
from config.settings import settings
from tools.common_types import GoogleServiceType, UserGoogleEmail
from tools.dynamic_instructions import refresh_instructions_for_session
from tools.server_types import (
    CredentialInfo,
    HealthCheckResponse,
    ManageCredentialsResponse,
    ManageToolsResponse,
    MemoryHealth,
    OAuthFlowStatus,
    SessionToolState,
    ToolInfo,
)

logger = setup_logger()


async def check_oauth_flows_health(google_auth_provider: Optional[Any] = None) -> str:
    """
    Check health of both OAuth flows during migration.

    Args:
        google_auth_provider: Optional GoogleProvider instance from server context

    Returns:
        str: Health status string for OAuth flows
    """
    status_lines = []

    # Import feature flags
    ENABLE_UNIFIED_AUTH = settings.enable_unified_auth
    LEGACY_COMPAT_MODE = settings.legacy_compat_mode
    CREDENTIAL_MIGRATION = settings.credential_migration
    SERVICE_CACHING = settings.service_caching
    ENHANCED_LOGGING = settings.enhanced_logging

    # Check unified auth status
    if ENABLE_UNIFIED_AUTH:
        status_lines.append(
            "  **Unified Auth (FastMCP 2.12.0 GoogleProvider):** ✅ ENABLED"
        )

        # Check if GoogleProvider is configured
        if google_auth_provider:
            status_lines.append(
                "    - GoogleProvider: ✅ Configured (Phase 1: not enforced)"
            )
        else:
            status_lines.append("    - GoogleProvider: ❌ Not configured")

        # Check environment variables
        env_vars = {
            "FASTMCP_SERVER_AUTH": settings.fastmcp_server_auth,
            "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID": bool(
                settings.fastmcp_server_auth_google_client_id
            ),
            "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET": bool(
                settings.fastmcp_server_auth_google_client_secret
            ),
            "FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL": settings.fastmcp_server_auth_google_base_url,
        }

        all_vars_set = all(
            [
                env_vars["FASTMCP_SERVER_AUTH"] == "GOOGLE",
                env_vars["FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID"],
                env_vars["FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET"],
                env_vars["FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL"],
            ]
        )

        if all_vars_set:
            status_lines.append("    - Environment Variables: ✅ All set")
        else:
            status_lines.append("    - Environment Variables: ⚠️ Missing required vars")
    else:
        status_lines.append(
            "  **Unified Auth (FastMCP 2.12.0 GoogleProvider):** ⭕ DISABLED"
        )

    # Check legacy flow status
    use_google_oauth = os.getenv("USE_GOOGLE_OAUTH", "true").lower() == "true"
    enable_jwt_auth = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"

    if LEGACY_COMPAT_MODE:
        status_lines.append(
            "  **Legacy OAuth Flow:** ✅ ACTIVE (backward compatibility)"
        )

        # Check legacy OAuth configuration
        if use_google_oauth:
            status_lines.append("    - Google OAuth: ✅ Enabled")
        elif enable_jwt_auth:
            status_lines.append("    - JWT Auth: ✅ Enabled (development)")
        else:
            status_lines.append("    - Authentication: ⚠️ Disabled")
    else:
        status_lines.append("  **Legacy OAuth Flow:** ⭕ DISABLED")

    # Check credential migration status
    if CREDENTIAL_MIGRATION:
        status_lines.append("  **Credential Migration:** ✅ ENABLED")

        # Check credential bridge
        try:
            from auth.credential_bridge import CredentialBridge

            bridge = CredentialBridge()
            migration_status = bridge.get_migration_status()

            status_lines.append(
                f"    - Total Credentials: {migration_status['total_credentials']}"
            )
            status_lines.append(
                f"    - Format Distribution: {migration_status['format_distribution']}"
            )
            status_lines.append(
                f"    - Successful Migrations: {migration_status['successful_migrations']}"
            )
            status_lines.append(
                f"    - Failed Migrations: {migration_status['failed_migrations']}"
            )
        except Exception as e:
            status_lines.append(f"    - Status: ❌ Error checking migration: {e}")
    else:
        status_lines.append("  **Credential Migration:** ⭕ DISABLED")

    # Check service caching
    if SERVICE_CACHING:
        status_lines.append("  **Service Caching:** ✅ ENABLED")
    else:
        status_lines.append("  **Service Caching:** ⭕ DISABLED")

    # Check enhanced logging
    if ENHANCED_LOGGING:
        status_lines.append(
            "  **Enhanced Logging:** ✅ ENABLED (verbose migration tracking)"
        )
    else:
        status_lines.append("  **Enhanced Logging:** ⭕ DISABLED")

    # Overall migration phase status
    status_lines.append(
        "\n  **Migration Phase:** Phase 1 - Environment Setup & Core Components"
    )

    if ENABLE_UNIFIED_AUTH and LEGACY_COMPAT_MODE:
        status_lines.append("  **Mode:** 🔄 Dual-flow operation (both flows active)")
    elif ENABLE_UNIFIED_AUTH:
        status_lines.append("  **Mode:** 🆕 Unified flow only (legacy disabled)")
    else:
        status_lines.append("  **Mode:** 🔙 Legacy flow only (unified not enabled)")

    return "\n".join(status_lines)


async def health_check(
    google_auth_provider: Optional[Any] = None,
    credential_storage_mode: Optional[CredentialStorageMode] = None,
    user_google_email: Optional[str] = None,
) -> HealthCheckResponse:
    """
    Check server health and configuration.

    Args:
        google_auth_provider: Optional GoogleProvider instance from server context
        credential_storage_mode: Current credential storage mode from server context
        user_google_email: Optional user email for context-specific health checks

    Returns:
        HealthCheckResponse: Structured server health status
    """
    try:
        # Check credentials directory
        creds_dir = Path(settings.credentials_dir)
        creds_accessible = creds_dir.exists() and os.access(
            creds_dir, os.R_OK | os.W_OK
        )

        # Check OAuth configuration
        oauth_configured = bool(
            settings.google_client_id and settings.google_client_secret
        )

        # Basic session info
        from auth.context import get_session_count

        active_sessions = get_session_count()

        # Default credential storage mode if not provided
        if credential_storage_mode is None:
            try:
                storage_mode_str = settings.credential_storage_mode.upper()
                credential_storage_mode = CredentialStorageMode[storage_mode_str]
            except KeyError:
                credential_storage_mode = CredentialStorageMode.FILE_PLAINTEXT

        # Determine OAuth flow status
        ENABLE_UNIFIED_AUTH = settings.enable_unified_auth
        LEGACY_COMPAT_MODE = settings.legacy_compat_mode

        if ENABLE_UNIFIED_AUTH and LEGACY_COMPAT_MODE:
            oauth_mode = "dual"
        elif ENABLE_UNIFIED_AUTH:
            oauth_mode = "unified"
        else:
            oauth_mode = "legacy"

        oauth_flow_status = OAuthFlowStatus(
            unified_flow_enabled=ENABLE_UNIFIED_AUTH,
            legacy_flow_enabled=LEGACY_COMPAT_MODE or not ENABLE_UNIFIED_AUTH,
            mode=oauth_mode,
        )

        healthy = creds_accessible and oauth_configured
        status = "healthy" if healthy else "degraded"

        # Memory health metrics
        memory_health = None
        try:
            from lifespans.server_lifespans import (
                _CRITICAL_THRESHOLD_MB,
                _MEMORY_LIMIT_MB,
                _WARN_THRESHOLD_MB,
                _get_process_health,
            )

            proc_health = _get_process_health()
            rss_mb = proc_health["rss_mb"]
            rss_pct = (
                round(rss_mb / _MEMORY_LIMIT_MB * 100, 1) if _MEMORY_LIMIT_MB > 0 else 0
            )

            if rss_mb > _CRITICAL_THRESHOLD_MB:
                mem_status = "critical"
            elif rss_mb > _WARN_THRESHOLD_MB:
                mem_status = "warning"
            else:
                mem_status = "ok"

            import gc as _gc

            gc_stats = _gc.get_stats()
            memory_health = MemoryHealth(
                rss_mb=rss_mb,
                vms_mb=proc_health["vms_mb"],
                rss_percent=rss_pct,
                memory_limit_mb=_MEMORY_LIMIT_MB,
                warn_threshold_mb=_WARN_THRESHOLD_MB,
                critical_threshold_mb=_CRITICAL_THRESHOLD_MB,
                memory_status=mem_status,
                cpu_percent=proc_health["cpu_pct"],
                num_fds=proc_health["num_fds"],
                num_threads=proc_health["num_threads"],
                asyncio_tasks=proc_health["asyncio_tasks"],
                gc_gen0_collections=gc_stats[0]["collections"],
                gc_gen1_collections=gc_stats[1]["collections"],
                gc_gen2_collections=gc_stats[2]["collections"],
                gc_uncollectable=sum(g["uncollectable"] for g in gc_stats),
            )

            # Degrade overall status based on memory pressure
            if mem_status == "critical":
                status = "unhealthy"
                healthy = False
            elif mem_status == "warning" and status == "healthy":
                status = "degraded"

        except Exception as e:
            logger.debug(f"Memory health check skipped: {e}")

        return HealthCheckResponse(
            status=status,
            healthy=healthy,
            serverName=settings.server_name,
            serverVersion="1.0.0",
            host=settings.server_host,
            port=settings.server_port,
            oauthConfigured=oauth_configured,
            credentialsDirectoryAccessible=creds_accessible,
            credentialsDirectory=str(settings.credentials_dir),
            activeSessions=active_sessions,
            logLevel=settings.log_level,
            oauthFlowStatus=oauth_flow_status,
            oauthCallbackUrl=settings.dynamic_oauth_redirect_uri,
            memoryHealth=memory_health,
        )

    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return HealthCheckResponse(
            status="unhealthy",
            healthy=False,
            serverName=settings.server_name,
            serverVersion="1.0.0",
            host=settings.server_host,
            port=settings.server_port,
            oauthConfigured=False,
            credentialsDirectoryAccessible=False,
            credentialsDirectory=str(settings.credentials_dir),
            activeSessions=0,
            logLevel=settings.log_level,
            oauthCallbackUrl=settings.dynamic_oauth_redirect_uri,
            error=str(e),
        )


async def manage_credentials(
    email: Annotated[str, Field(description="User's Google email address")],
    action: Annotated[
        Literal["status", "migrate", "summary", "delete"],
        Field(
            description="Action to perform: 'status', 'migrate', 'summary', or 'delete'"
        ),
    ],
    new_storage_mode: Annotated[
        Optional[str],
        Field(
            description="Target storage mode for migration: 'FILE_PLAINTEXT', 'FILE_ENCRYPTED', 'MEMORY_ONLY', 'MEMORY_WITH_BACKUP'"
        ),
    ] = None,
) -> ManageCredentialsResponse:
    """
    Manage credential storage and security settings.

    Args:
        email: User's Google email address
        action: Action to perform ('status', 'migrate', 'summary', 'delete')
        new_storage_mode: Target storage mode for migration ('FILE_PLAINTEXT', 'FILE_ENCRYPTED', 'MEMORY_ONLY', 'MEMORY_WITH_BACKUP')

    Returns:
        ManageCredentialsResponse: Structured result of the credential management operation
    """
    try:
        from auth.context import get_auth_middleware

        # Get the AuthMiddleware instance
        auth_middleware = get_auth_middleware()
        if not auth_middleware:
            return ManageCredentialsResponse(
                success=False,
                action=action,
                email=email,
                message="AuthMiddleware not available",
                error="AuthMiddleware not initialized",
            )

        if action == "status":
            # Get credential status
            summary = await auth_middleware.get_credential_summary(email)
            if summary:
                credential_info = CredentialInfo(
                    storageMode=summary.get("storage_mode", "unknown"),
                    filePath=summary.get("file_path"),
                    fileExists=summary.get("file_exists", False),
                    inMemory=summary.get("in_memory", False),
                    isEncrypted=summary.get("is_encrypted", False),
                    lastModified=summary.get("last_modified"),
                    fileSize=summary.get("file_size"),
                )
                return ManageCredentialsResponse(
                    success=True,
                    action=action,
                    email=email,
                    credentialInfo=credential_info,
                    message=f"Credential status retrieved for {email}",
                )
            else:
                return ManageCredentialsResponse(
                    success=False,
                    action=action,
                    email=email,
                    message=f"No credentials found for {email}",
                    error="Credentials not found",
                )

        elif action == "migrate":
            if not new_storage_mode:
                return ManageCredentialsResponse(
                    success=False,
                    action=action,
                    email=email,
                    message="new_storage_mode parameter is required for migration",
                    error="Missing required parameter: new_storage_mode",
                )

            try:
                target_mode = CredentialStorageMode[new_storage_mode.upper()]
            except KeyError:
                return ManageCredentialsResponse(
                    success=False,
                    action=action,
                    email=email,
                    message=f"Invalid storage mode '{new_storage_mode}'",
                    error=f"Valid options: FILE_PLAINTEXT, FILE_ENCRYPTED, MEMORY_ONLY, MEMORY_WITH_BACKUP",
                )

            # Get current storage mode before migration
            current_summary = await auth_middleware.get_credential_summary(email)
            previous_mode = (
                current_summary.get("storage_mode") if current_summary else None
            )

            # Perform migration
            success = await auth_middleware.migrate_credentials(email, target_mode)
            if success:
                return ManageCredentialsResponse(
                    success=True,
                    action=action,
                    email=email,
                    previousStorageMode=previous_mode,
                    newStorageMode=target_mode.value,
                    message=f"Successfully migrated credentials to {target_mode.value} mode",
                )
            else:
                return ManageCredentialsResponse(
                    success=False,
                    action=action,
                    email=email,
                    previousStorageMode=previous_mode,
                    newStorageMode=target_mode.value,
                    message=f"Failed to migrate credentials to {target_mode.value} mode",
                    error="Migration operation failed",
                )

        elif action == "summary":
            return ManageCredentialsResponse(
                success=True,
                action=action,
                email=email,
                message=f"Current storage mode: {auth_middleware.storage_mode.value}. Use 'status' action with specific email for detailed information.",
            )

        elif action == "delete":
            return ManageCredentialsResponse(
                success=False,
                action=action,
                email=email,
                message="Credential deletion not yet implemented",
                error="Please manually delete credential files if needed",
            )

        else:
            return ManageCredentialsResponse(
                success=False,
                action=action,
                email=email,
                message=f"Invalid action '{action}'",
                error="Valid actions: status, migrate, summary, delete",
            )

    except Exception as e:
        logger.error(f"Credential management error: {e}", exc_info=True)
        return ManageCredentialsResponse(
            success=False,
            action=action,
            email=email,
            message="Credential management failed",
            error=str(e),
        )


def _get_tool_registry(mcp: FastMCP) -> Dict[str, Any]:
    """
    Internal helper to access the FastMCP tool registry.

    Uses FastMCP v3 local_provider._components, filtered to Tool instances.

    Args:
        mcp: FastMCP server instance

    Returns:
        Dict[str, Any]: Dictionary mapping tool names to tool instances
    """
    from fastmcp.tools import Tool

    components = mcp.local_provider._components
    return {v.name: v for v in components.values() if isinstance(v, Tool)}


def _get_globally_disabled_tools(mcp: FastMCP) -> set:
    """
    Get the set of globally disabled tool names from FastMCP transforms.

    In FastMCP 3.0+, visibility is managed through Visibility transforms
    stored in mcp._transforms. This function extracts disabled tool names.

    Args:
        mcp: FastMCP server instance

    Returns:
        set: Set of tool names that are globally disabled
    """
    disabled_names = set()
    try:
        for transform in mcp._transforms:
            transform_repr = repr(transform)
            if "Visibility(disable" in transform_repr:
                if transform.names:
                    disabled_names.update(transform.names)
    except Exception as e:
        logger.debug(f"Error checking global disabled tools: {e}")
    return disabled_names


def _get_tool_enabled_state(tool_instance: Any, mcp: FastMCP = None) -> bool:
    """
    Best-effort check of a tool's enabled/disabled state.

    In FastMCP 3.0+, individual tools don't have an 'enabled' attribute.
    Instead, visibility is managed through server-level transforms.
    If mcp is provided, checks the global disabled set.

    Args:
        tool_instance: Tool instance to check
        mcp: Optional FastMCP server instance for checking global state

    Returns:
        bool: True if enabled or state unknown, False if explicitly disabled
    """
    try:
        # Check global transforms if mcp provided
        if mcp is not None:
            disabled_tools = _get_globally_disabled_tools(mcp)
            if tool_instance.name in disabled_tools:
                return False

        # Check meta dict for explicit enabled state
        if isinstance(tool_instance.meta, dict) and "enabled" in tool_instance.meta:
            return bool(tool_instance.meta["enabled"])
    except Exception:
        pass
    return True


def setup_server_tools(mcp: FastMCP) -> None:
    """
    Register server management tools with the FastMCP server.

    This function registers the server management tools:
    1. health_check: Server health monitoring and status
    2. server_info: Detailed server information and usage guide
    3. manage_credentials: Credential storage and security management

    Args:
        mcp: FastMCP server instance to register tools with

    Returns:
        None: Tools are registered as side effects
    """

    @mcp.tool(
        name="health_check",
        description="Check server health and configuration",
        tags={"server", "health", "monitoring", "status", "system"},
        annotations={
            "title": "Server Health Check",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def health_check_tool(
        user_google_email: Annotated[
            UserGoogleEmail,
            Field(
                description="The user's Google email address for Drive access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
            ),
        ] = None,
    ) -> HealthCheckResponse:
        """
        Check server health and configuration.

        Args:
            user_google_email: The user's Google email address. If None, uses the current
                             authenticated user from FastMCP context (auto-injected by middleware).

        Returns:
            HealthCheckResponse: Structured server health status including OAuth migration status, active sessions, and configuration
        """
        return await health_check(user_google_email=user_google_email)

    @mcp.tool(
        name="manage_credentials",
        description="Manage credential storage and security settings",
        tags={"credentials", "security", "migration", "management", "storage"},
        annotations={
            "title": "Credential Management",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def manage_credentials_tool(
        email: Annotated[str, Field(description="User's Google email address")],
        action: Annotated[
            Literal["status", "migrate", "summary", "delete"],
            Field(
                description="Action to perform: 'status' (check status), 'migrate' (migrate storage mode), 'summary' (get summary), 'delete' (delete credentials)"
            ),
        ],
        new_storage_mode: Annotated[
            Optional[str],
            Field(
                description="Target storage mode for migration: 'FILE_PLAINTEXT', 'FILE_ENCRYPTED', 'MEMORY_ONLY', 'MEMORY_WITH_BACKUP'. Required when action='migrate'"
            ),
        ] = None,
    ) -> ManageCredentialsResponse:
        """
        Manage credential storage and security settings.

        Args:
            email: User's Google email address
            action: Action to perform - 'status', 'migrate', 'summary', or 'delete'
            new_storage_mode: Target storage mode for migration (required when action='migrate')

        Returns:
            ManageCredentialsResponse: Structured result of the credential management operation
        """
        return await manage_credentials(email, action, new_storage_mode)

    @mcp.tool(
        name="manage_tools",
        description=(
            "List, enable, or disable FastMCP tools at runtime. Supports both global scope "
            "(affects all clients) and session scope (affects only current session). "
            "Use service_filter to target all tools for a service (e.g., 'gmail', 'chat', 'drive') "
            "without needing to know individual tool names."
        ),
        tags={"server", "tools", "feature_flag", "management"},
        annotations={
            "title": "Tool Enable/Disable Management",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        app=AppConfig(
            resource_uri="ui://manage-tools-dashboard",
            visibility=["app", "model"],
        ),
    )
    async def manage_tools_tool(
        ctx: Context,
        action: Annotated[
            Literal["list", "disable", "enable", "disable_all_except", "enable_all"],
            Field(
                description=(
                    "Action to perform: "
                    "'list' (show all tools), "
                    "'disable' (disable specific tools), "
                    "'enable' (enable specific tools), "
                    "'disable_all_except' (disable every tool except a kept list and protected infra tools), "
                    "'enable_all' (enable all tools in the registry)."
                )
            ),
        ],
        tool_names: Annotated[
            Optional[Union[str, List[str]]],
            Field(
                description="Tool name(s) to enable/disable. Single string ('tool_a'), list (['tool_a', 'tool_b']), comma-separated ('tool_a,tool_b'), or JSON ('[\"tool_a\",\"tool_b\"]'). Required for enable/disable actions."
            ),
        ] = None,
        scope: Annotated[
            Literal["global", "session"],
            Field(
                description=(
                    "Scope of the operation: "
                    "'global' (default) - affects all MCP clients connected to this server, "
                    "'session' - affects only the current client session (other clients unaffected). "
                    "Session scope requires SessionToolFilteringMiddleware to be enabled."
                )
            ),
        ] = "global",
        service_filter: Annotated[
            Optional[GoogleServiceType],
            Field(
                description=(
                    "Filter tools by service name (e.g., 'gmail', 'chat', 'drive'). "
                    "When provided, automatically resolves matching tool names from the registry "
                    "using extract_service_from_tool(). Can be used instead of tool_names."
                )
            ),
        ] = None,
        include_internal: Annotated[
            bool,
            Field(
                description="If True, include internal/system tools (names starting with '_') in listing"
            ),
        ] = False,
        user_google_email: UserGoogleEmail = None,
    ) -> ManageToolsResponse:
        """
        Manage FastMCP tool availability with global or session scope.

        Scope:
            - 'global' (default): Changes affect ALL MCP clients connected to this server.
              Uses FastMCP's built-in tool.enable()/disable() methods.
            - 'session': Changes affect ONLY the current client session.
              Other clients continue to see all tools. Requires SessionToolFilteringMiddleware.

        Actions:
            - 'list':
                List all registered tools and their enabled/disabled state.
                Includes session-specific state when scope='session'.
            - 'disable':
                Disable one or more tools by exact name. With scope='global', disabled tools
                are hidden from all clients. With scope='session', only this session is affected.
            - 'enable':
                Re-enable one or more previously disabled tools by exact name.
            - 'disable_all_except':
                Disable every tool except a provided keep list and a built-in set of
                protected infra/management tools (e.g., manage_tools, health_check).
            - 'enable_all':
                Enable all tools (optionally excluding internal tools whose names start with '_').

        Args:
            action:
                One of: 'list', 'disable', 'enable', 'disable_all_except', 'enable_all'.
            tool_names:
                Tool name(s) to enable/disable. Supports:
                  - Single string: "tool_a"
                  - List: ["tool_a", "tool_b"]
                  - Comma-separated string: "tool_a,tool_b"
                  - JSON list string: '["tool_a", "tool_b"]'
            scope:
                'global' affects all clients, 'session' affects only current session.
            include_internal:
                If True, include internal/system tools (names starting with '_') in listing.

        Returns:
            ManageToolsResponse: Structured result including scope and session state information.
        """
        action_normalized = action.lower().strip()
        scope_normalized = scope.lower().strip() if scope else "global"
        valid_actions = {
            "list",
            "disable",
            "enable",
            "disable_all_except",
            "enable_all",
        }

        # Protect critical tools from being disabled
        protected_tools_set = {
            "manage_tools",
            "qdrant_search",
            "health_check",
            "start_google_auth",
            "check_drive_auth",
            "set_privacy_mode",
            # CodeMode meta-tools (FastMCP 3.1.0+)
            "tags",
            "search",
            "get_schema",
            "execute",
        }

        # Helper to get current session state (uses sync versions to avoid async in sync helper)
        def _get_session_state() -> SessionToolState:
            session_id = get_session_context_sync()
            if session_id:
                disabled = get_session_disabled_tools_sync(session_id)
                return SessionToolState(
                    sessionId=(
                        session_id[:8] + "..." if len(session_id) > 8 else session_id
                    ),
                    sessionAvailable=True,
                    sessionDisabledTools=sorted(list(disabled)),
                    sessionDisabledCount=len(disabled),
                )
            return SessionToolState(
                sessionId=None,
                sessionAvailable=False,
                sessionDisabledTools=[],
                sessionDisabledCount=0,
            )

        # Helper to get list of enabled tool names for this session
        # This allows clients to update their tool list without notifications
        def _get_enabled_tool_names(reg: Dict[str, Any]) -> List[str]:
            """Get list of tool names currently enabled for this session."""
            session_id = get_session_context_sync()
            session_disabled = (
                get_session_disabled_tools_sync(session_id) if session_id else set()
            )
            enabled_names = []
            for name, tool in sorted(reg.items()):
                # Skip internal tools
                if name.startswith("_"):
                    continue
                # Check global enabled state (FastMCP 3.0+ uses transforms)
                if not _get_tool_enabled_state(tool, mcp):
                    continue
                # Check session-disabled state
                if name in session_disabled:
                    continue
                enabled_names.append(name)
            return enabled_names

        # Helper to send notification and refresh instructions
        async def _notify_and_refresh_instructions(
            ctx: Context, session_id: str, all_tool_names: List[str]
        ) -> None:
            """Send ToolListChangedNotification and refresh session-aware instructions."""
            # Send immediate notification to client
            await ctx.send_notification(ToolListChangedNotification())

            # Refresh instructions to reflect enabled services
            try:
                await refresh_instructions_for_session(mcp, session_id, all_tool_names)
            except Exception as e:
                logger.warning(f"Failed to refresh instructions after tool change: {e}")

        if action_normalized not in valid_actions:
            return ManageToolsResponse(
                success=False,
                action=action,
                scope=scope_normalized,
                totalTools=0,
                enabledCount=0,
                disabledCount=0,
                protectedTools=list(protected_tools_set),
                sessionState=(
                    _get_session_state() if scope_normalized == "session" else None
                ),
                message=f"Invalid action '{action}'",
                error="Valid actions: list, disable, enable, disable_all_except, enable_all",
            )

        # Discover current tool registry
        registry = _get_tool_registry(mcp)
        if not registry:
            return ManageToolsResponse(
                success=False,
                action=action,
                scope=scope_normalized,
                totalTools=0,
                enabledCount=0,
                disabledCount=0,
                protectedTools=list(protected_tools_set),
                sessionState=(
                    _get_session_state() if scope_normalized == "session" else None
                ),
                message="Unable to access FastMCP tool registry",
                error="Tool registry not available",
            )

        # Count enabled/disabled tools (FastMCP 3.0+ uses transforms for visibility)
        total_tools = len(registry)
        enabled_count = sum(
            1 for t in registry.values() if _get_tool_enabled_state(t, mcp)
        )
        disabled_count = total_tools - enabled_count

        if action_normalized == "list":
            tool_list = []
            session_state = _get_session_state()
            session_disabled = set(session_state.sessionDisabledTools)

            for name, tool in sorted(registry.items()):
                if not include_internal and name.startswith("_"):
                    continue
                enabled = _get_tool_enabled_state(tool, mcp)
                is_protected = name in protected_tools_set
                tool_list.append(
                    ToolInfo(
                        name=name,
                        enabled=enabled,
                        isProtected=is_protected,
                        description=getattr(tool, "description", None),
                    )
                )

            # Include session state info in list response
            session_info = ""
            if (
                session_state.sessionAvailable
                and session_state.sessionDisabledCount > 0
            ):
                session_info = (
                    f", {session_state.sessionDisabledCount} session-disabled"
                )

            # Detect if client supports MCP Apps UI extension
            try:
                client_supports_ui = ctx.client_supports_extension(UI_EXTENSION_ID)
            except Exception:
                client_supports_ui = False

            return ManageToolsResponse(
                success=True,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=enabled_count,
                disabledCount=disabled_count,
                toolList=tool_list,
                protectedTools=list(protected_tools_set),
                sessionState=session_state,
                clientSupportsUI=client_supports_ui,
                message=f"Listed {len(tool_list)} tools ({enabled_count} enabled, {disabled_count} disabled{session_info})",
            )

        def _normalize_tool_names(names_input):
            """Normalize tool name(s) into a de-duplicated list."""
            if not names_input:
                return []
            names = []
            if isinstance(names_input, list):
                names.extend(str(n) for n in names_input)
            elif isinstance(names_input, str):
                try:
                    parsed = json.loads(names_input)
                    if isinstance(parsed, list):
                        names.extend(str(n) for n in parsed)
                    else:
                        names.append(str(parsed))
                except json.JSONDecodeError:
                    if "," in names_input:
                        names.extend(
                            n.strip() for n in names_input.split(",") if n.strip()
                        )
                    else:
                        names.append(names_input.strip())
            else:
                names.append(str(names_input))
            seen = set()
            deduped = []
            for n in names:
                if n and n not in seen:
                    seen.add(n)
                    deduped.append(n)
            return deduped

        target_names = _normalize_tool_names(tool_names)

        # Resolve tool names from service_filter if provided and no explicit tool_names
        if service_filter and not target_names:
            from middleware.qdrant_core import extract_service_from_tool

            svc = service_filter.lower().strip()
            target_names = [
                name
                for name in registry.keys()
                if extract_service_from_tool(name).lower() == svc
                and name not in protected_tools_set
                and not name.startswith("_")
            ]
            if not target_names:
                return ManageToolsResponse(
                    success=False,
                    action=action,
                    scope=scope_normalized,
                    totalTools=total_tools,
                    enabledCount=enabled_count,
                    disabledCount=disabled_count,
                    protectedTools=list(protected_tools_set),
                    sessionState=(
                        _get_session_state() if scope_normalized == "session" else None
                    ),
                    message=f"No tools found matching service '{service_filter}'",
                    error=f"No registered tools belong to service '{service_filter}'",
                )

        # For some actions, we require at least one concrete tool name
        if (
            action_normalized in {"disable", "enable", "disable_all_except"}
            and not target_names
        ):
            return ManageToolsResponse(
                success=False,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=enabled_count,
                disabledCount=disabled_count,
                protectedTools=list(protected_tools_set),
                sessionState=(
                    _get_session_state() if scope_normalized == "session" else None
                ),
                message="'tool_names' parameter is required for this action",
                error="Missing required parameter: tool_names",
            )

        affected = []
        skipped = []
        errors = []

        if action_normalized == "disable":
            # Session-scoped disable
            if scope_normalized == "session":
                session_id = await get_session_context()
                if not session_id:
                    return ManageToolsResponse(
                        success=False,
                        action=action,
                        scope=scope_normalized,
                        totalTools=total_tools,
                        enabledCount=enabled_count,
                        disabledCount=disabled_count,
                        protectedTools=list(protected_tools_set),
                        sessionState=_get_session_state(),
                        message="Session scope requires active session context",
                        error="No session context available. Ensure SessionToolFilteringMiddleware is enabled.",
                    )

                for name in target_names:
                    # Verify tool exists in registry
                    if name not in registry:
                        skipped.append(name)
                        errors.append(f"Tool '{name}' not found in registry")
                        continue
                    if name in protected_tools_set:
                        skipped.append(name)
                        errors.append(
                            f"Tool '{name}' is protected and cannot be disabled"
                        )
                        continue
                    # Disable for session only (persist=True for cross-client visibility)
                    if await disable_tool_for_session(name, session_id, persist=True):
                        affected.append(name)
                    else:
                        skipped.append(name)
                        errors.append(f"Failed to disable tool '{name}' for session")

                session_state = _get_session_state()
                # Notify MCP client and refresh session-aware instructions
                if affected:
                    await _notify_and_refresh_instructions(
                        ctx, session_id, list(registry.keys())
                    )
                return ManageToolsResponse(
                    success=len(affected) > 0,
                    action=action,
                    scope=scope_normalized,
                    totalTools=total_tools,
                    enabledCount=enabled_count,  # Global state unchanged
                    disabledCount=disabled_count,  # Global state unchanged
                    toolsAffected=affected if affected else None,
                    toolsSkipped=skipped if skipped else None,
                    enabledToolNames=_get_enabled_tool_names(registry),
                    protectedTools=list(protected_tools_set),
                    sessionState=session_state,
                    message=f"Disabled {len(affected)} tools for this session"
                    + (f", skipped {len(skipped)}" if skipped else ""),
                    errors=errors if errors else None,
                )

            # Global scope disable (FastMCP 3.0+ API)
            for name in target_names:
                if name not in registry:
                    skipped.append(name)
                    errors.append(f"Tool '{name}' not found in registry")
                    continue
                if name in protected_tools_set:
                    skipped.append(name)
                    errors.append(f"Tool '{name}' is protected and cannot be disabled")
                    continue
                try:
                    # FastMCP 3.0: Use server-level disable with names parameter
                    mcp.disable(names={name})
                    affected.append(name)
                except Exception as e:
                    logger.error(f"Error disabling tool {name}: {e}", exc_info=True)
                    errors.append(f"Failed to disable tool '{name}': {e}")

            # Notify MCP client of tool list change
            if affected:
                await ctx.send_notification(ToolListChangedNotification())
            return ManageToolsResponse(
                success=len(affected) > 0,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=enabled_count - len(affected),
                disabledCount=disabled_count + len(affected),
                toolsAffected=affected if affected else None,
                toolsSkipped=skipped if skipped else None,
                enabledToolNames=_get_enabled_tool_names(registry),
                protectedTools=list(protected_tools_set),
                message=f"Disabled {len(affected)} tools globally"
                + (f", skipped {len(skipped)}" if skipped else ""),
                errors=errors if errors else None,
            )

        if action_normalized == "disable_all_except":
            keep_set = set(target_names) | protected_tools_set

            # Session-scoped disable_all_except
            if scope_normalized == "session":
                session_id = await get_session_context()
                if not session_id:
                    return ManageToolsResponse(
                        success=False,
                        action=action,
                        scope=scope_normalized,
                        totalTools=total_tools,
                        enabledCount=enabled_count,
                        disabledCount=disabled_count,
                        protectedTools=list(protected_tools_set),
                        sessionState=_get_session_state(),
                        message="Session scope requires active session context",
                        error="No session context available. Ensure SessionToolFilteringMiddleware is enabled.",
                    )

                for name in registry.keys():
                    if not include_internal and name.startswith("_"):
                        skipped.append(name)
                        continue
                    if name in keep_set:
                        skipped.append(name)
                        continue
                    # Disable for session only (persist=True for cross-client visibility)
                    if await disable_tool_for_session(name, session_id, persist=True):
                        affected.append(name)
                    else:
                        errors.append(f"Failed to disable tool '{name}' for session")

                session_state = _get_session_state()
                # Notify MCP client and refresh session-aware instructions
                if affected:
                    await _notify_and_refresh_instructions(
                        ctx, session_id, list(registry.keys())
                    )
                return ManageToolsResponse(
                    success=True,
                    action=action,
                    scope=scope_normalized,
                    totalTools=total_tools,
                    enabledCount=enabled_count,  # Global state unchanged
                    disabledCount=disabled_count,  # Global state unchanged
                    toolsAffected=affected if affected else None,
                    toolsSkipped=skipped if skipped else None,
                    enabledToolNames=_get_enabled_tool_names(registry),
                    protectedTools=list(protected_tools_set),
                    sessionState=session_state,
                    message=f"Kept {len(keep_set)} tools, disabled {len(affected)} tools for this session",
                    errors=errors if errors else None,
                )

            # Global scope (FastMCP 3.0+ API)
            for name in registry.keys():
                if not include_internal and name.startswith("_"):
                    skipped.append(name)
                    continue
                if name in keep_set:
                    skipped.append(name)
                    continue
                try:
                    # FastMCP 3.0: Use server-level disable with names parameter
                    mcp.disable(names={name})
                    affected.append(name)
                except Exception as e:
                    logger.error(f"Error disabling tool {name}: {e}", exc_info=True)
                    errors.append(f"{name}: {e}")

            # Notify MCP client of tool list change
            if affected:
                await ctx.send_notification(ToolListChangedNotification())
            return ManageToolsResponse(
                success=True,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=len(keep_set),
                disabledCount=len(affected),
                toolsAffected=affected if affected else None,
                toolsSkipped=skipped if skipped else None,
                enabledToolNames=_get_enabled_tool_names(registry),
                protectedTools=list(protected_tools_set),
                message=f"Kept {len(keep_set)} tools, disabled {len(affected)} tools globally",
                errors=errors if errors else None,
            )

        if action_normalized == "enable":
            # Session-scoped enable
            if scope_normalized == "session":
                session_id = await get_session_context()
                if not session_id:
                    return ManageToolsResponse(
                        success=False,
                        action=action,
                        scope=scope_normalized,
                        totalTools=total_tools,
                        enabledCount=enabled_count,
                        disabledCount=disabled_count,
                        protectedTools=list(protected_tools_set),
                        sessionState=_get_session_state(),
                        message="Session scope requires active session context",
                        error="No session context available. Ensure SessionToolFilteringMiddleware is enabled.",
                    )

                for name in target_names:
                    # Verify tool exists in registry
                    if name not in registry:
                        skipped.append(name)
                        errors.append(f"Tool '{name}' not found in registry")
                        continue
                    # Enable for session (persist=True for cross-client visibility)
                    if await enable_tool_for_session(name, session_id, persist=True):
                        affected.append(name)
                    else:
                        skipped.append(name)
                        errors.append(f"Failed to enable tool '{name}' for session")

                session_state = _get_session_state()
                # Notify MCP client and refresh session-aware instructions
                if affected:
                    await _notify_and_refresh_instructions(
                        ctx, session_id, list(registry.keys())
                    )
                return ManageToolsResponse(
                    success=len(affected) > 0,
                    action=action,
                    scope=scope_normalized,
                    totalTools=total_tools,
                    enabledCount=enabled_count,  # Global state unchanged
                    disabledCount=disabled_count,  # Global state unchanged
                    toolsAffected=affected if affected else None,
                    toolsSkipped=skipped if skipped else None,
                    enabledToolNames=_get_enabled_tool_names(registry),
                    protectedTools=list(protected_tools_set),
                    sessionState=session_state,
                    message=f"Enabled {len(affected)} tools for this session"
                    + (f", skipped {len(skipped)}" if skipped else ""),
                    errors=errors if errors else None,
                )

            # Global scope (FastMCP 3.0+ API)
            for name in target_names:
                if name not in registry:
                    skipped.append(name)
                    errors.append(f"Tool '{name}' not found in registry")
                    continue
                try:
                    # FastMCP 3.0: Use server-level enable with names parameter
                    mcp.enable(names={name})
                    affected.append(name)
                except Exception as e:
                    logger.error(f"Error enabling tool {name}: {e}", exc_info=True)
                    errors.append(f"Failed to enable tool '{name}': {e}")

            # Notify MCP client of tool list change
            if affected:
                await ctx.send_notification(ToolListChangedNotification())
            return ManageToolsResponse(
                success=len(affected) > 0,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=enabled_count + len(affected),
                disabledCount=disabled_count - len(affected),
                toolsAffected=affected if affected else None,
                toolsSkipped=skipped if skipped else None,
                enabledToolNames=_get_enabled_tool_names(registry),
                protectedTools=list(protected_tools_set),
                message=f"Enabled {len(affected)} tools globally"
                + (f", skipped {len(skipped)}" if skipped else ""),
                errors=errors if errors else None,
            )

        if action_normalized == "enable_all":
            # Session-scoped enable_all (clears session disabled list)
            if scope_normalized == "session":
                session_id = await get_session_context()
                if not session_id:
                    return ManageToolsResponse(
                        success=False,
                        action=action,
                        scope=scope_normalized,
                        totalTools=total_tools,
                        enabledCount=enabled_count,
                        disabledCount=disabled_count,
                        protectedTools=list(protected_tools_set),
                        sessionState=_get_session_state(),
                        message="Session scope requires active session context",
                        error="No session context available. Ensure SessionToolFilteringMiddleware is enabled.",
                    )

                # Get currently disabled tools for this session before clearing
                session_disabled_before = await get_session_disabled_tools(session_id)
                affected = list(session_disabled_before)

                # Clear all session disables
                if await clear_session_disabled_tools(session_id):
                    session_state = _get_session_state()
                    # Notify MCP client and refresh session-aware instructions
                    if affected:
                        await _notify_and_refresh_instructions(
                            ctx, session_id, list(registry.keys())
                        )
                    return ManageToolsResponse(
                        success=True,
                        action=action,
                        scope=scope_normalized,
                        totalTools=total_tools,
                        enabledCount=enabled_count,  # Global state unchanged
                        disabledCount=disabled_count,  # Global state unchanged
                        toolsAffected=affected if affected else None,
                        enabledToolNames=_get_enabled_tool_names(registry),
                        protectedTools=list(protected_tools_set),
                        sessionState=session_state,
                        message=f"Enabled {len(affected)} session-disabled tools for this session",
                    )
                else:
                    return ManageToolsResponse(
                        success=False,
                        action=action,
                        scope=scope_normalized,
                        totalTools=total_tools,
                        enabledCount=enabled_count,
                        disabledCount=disabled_count,
                        protectedTools=list(protected_tools_set),
                        sessionState=_get_session_state(),
                        message="Failed to clear session disabled tools",
                        error="Could not clear session state",
                    )

            # Global scope (FastMCP 3.0+ API)
            for name in registry.keys():
                if not include_internal and name.startswith("_"):
                    skipped.append(name)
                    continue
                try:
                    # FastMCP 3.0: Use server-level enable with names parameter
                    mcp.enable(names={name})
                    affected.append(name)
                except Exception as e:
                    logger.error(f"Error enabling tool {name}: {e}", exc_info=True)
                    errors.append(f"{name}: {e}")

            # Notify MCP client of tool list change
            if affected:
                await ctx.send_notification(ToolListChangedNotification())
            return ManageToolsResponse(
                success=True,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=len(affected),
                disabledCount=len(skipped),
                toolsAffected=affected if affected else None,
                toolsSkipped=skipped if skipped else None,
                enabledToolNames=_get_enabled_tool_names(registry),
                protectedTools=list(protected_tools_set),
                message=f"Enabled {len(affected)} tools globally, skipped {len(skipped)}",
                errors=errors if errors else None,
            )

        # Should be unreachable due to earlier validation
        return ManageToolsResponse(
            success=False,
            action=action,
            scope=scope_normalized,
            totalTools=total_tools,
            enabledCount=enabled_count,
            disabledCount=disabled_count,
            protectedTools=list(protected_tools_set),
            sessionState=(
                _get_session_state() if scope_normalized == "session" else None
            ),
            message="Unknown error while managing tools",
            error="Unexpected code path reached",
        )

    @mcp.tool(
        name="set_privacy_mode",
        description=(
            "Toggle per-session PII privacy mode. When enabled, tool responses "
            "have sensitive values (emails, names, phone numbers) replaced with "
            "[PRIVATE:token_N] tokens. Requires authenticated session (OAuth or per-user API key)."
        ),
        tags={"server", "privacy", "security", "session"},
        annotations={
            "title": "Set Privacy Mode",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def set_privacy_mode_tool(
        mode: Annotated[
            Literal["disabled", "auto", "strict"],
            Field(
                description=(
                    "Privacy mode to set for this session: "
                    "'disabled' (no masking), "
                    "'auto' (mask PII identity fields + email patterns), "
                    "'strict' (mask all string values)."
                )
            ),
        ],
        mask_content: Annotated[
            Optional[bool],
            Field(
                description=(
                    "When true, also mask content fields (snippet, subject, body, "
                    "text, description, summary, web_url, attendees, location). "
                    "Default true when mode is 'auto'. Has no effect when mode is "
                    "'strict' (everything is already masked) or 'disabled'."
                )
            ),
        ] = None,
        additional_fields: Annotated[
            Optional[str],
            Field(
                description=(
                    "Comma-separated extra field names to treat as PII for this "
                    "session (e.g. 'customField1,notes'). Merged with built-in "
                    "patterns."
                )
            ),
        ] = None,
        user_google_email: Annotated[
            UserGoogleEmail,
            Field(description="Auto-injected by middleware. Not used by this tool."),
        ] = None,
    ) -> Dict[str, Any]:
        """Toggle per-session privacy mode.

        Security: requires an authenticated session (OAuth or per-user API key)
        so that the vault key is crypto-derived from identity material.
        Shared API key sessions are rejected because they use a random vault
        seed with no identity binding.
        """
        from auth.context import (
            get_session_context,
            get_session_data,
            store_session_data,
        )
        from auth.types import AuthProvenance, SessionKey

        session_id = await get_session_context()
        if not session_id:
            return {
                "success": False,
                "error": "No active session — cannot set privacy mode",
            }

        # Security: reject shared API key sessions (random vault seed, no identity binding).
        provenance = get_session_data(
            session_id, SessionKey.AUTH_PROVENANCE, default=None
        )
        if provenance == AuthProvenance.API_KEY:
            return {
                "success": False,
                "error": (
                    "Privacy mode requires authenticated session "
                    "(OAuth or per-user API key), not shared API key"
                ),
                "auth_provenance": str(provenance),
            }

        # Get previous state
        previous_mode = get_session_data(
            session_id, SessionKey.PRIVACY_MODE, default=None
        )
        effective_previous = (
            previous_mode if previous_mode is not None else settings.privacy_mode
        )

        # Store the new mode
        store_session_data(session_id, SessionKey.PRIVACY_MODE, mode)

        # Build session-level additional fields set
        # Default: mask_content=True when mode is "auto"
        effective_mask_content = (
            mask_content if mask_content is not None else (mode == "auto")
        )

        session_fields: set[str] = set()
        if effective_mask_content and mode != "disabled":
            session_fields.add(
                "__content__"
            )  # sentinel that expands to PRIVACY_CONTENT_FIELDS
        if additional_fields:
            for f in additional_fields.split(","):
                f = f.strip()
                if f:
                    session_fields.add(f)

        if session_fields:
            store_session_data(
                session_id,
                SessionKey.PRIVACY_ADDITIONAL_FIELDS,
                frozenset(session_fields),
            )
        else:
            store_session_data(session_id, SessionKey.PRIVACY_ADDITIONAL_FIELDS, None)

        logger.info(
            "Privacy mode changed for session %s: %s -> %s (mask_content=%s, extra_fields=%s)",
            session_id[:8] + "..." if len(session_id) > 8 else session_id,
            effective_previous,
            mode,
            effective_mask_content,
            additional_fields or "none",
        )

        return {
            "success": True,
            "previous_mode": effective_previous,
            "current_mode": mode,
            "mask_content": effective_mask_content,
            "additional_fields": sorted(session_fields) if session_fields else None,
            "auth_provenance": str(provenance),
            "message": f"Privacy mode set to '{mode}' for this session",
        }

    @mcp.tool(
        name="verify_payment",
        description="Verify a blockchain payment to unlock tool access (x402 protocol)",
        tags={"payment", "x402", "verification"},
        annotations={
            "title": "Verify Payment",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def verify_payment(
        tx_hash: Annotated[
            str,
            Field(
                default="",
                description="Transaction hash to verify (legacy Path C)",
            ),
        ] = "",
        payment_payload_b64: Annotated[
            str,
            Field(
                default="",
                description="Base64-encoded x402 payment payload (x402-native Path A/B)",
            ),
        ] = "",
        chain_id: Annotated[
            int, Field(description="Chain ID of the transaction")
        ] = 84532,
        user_google_email: Annotated[
            str,
            Field(
                default="",
                description="Injected by auth middleware",
            ),
        ] = "",
        ctx: Context = None,
    ) -> dict:
        """Verify a blockchain payment transaction to unlock tool access.

        Supports two verification paths:
        - x402-native: provide payment_payload_b64 (signed EIP-3009 payload)
        - Legacy: provide tx_hash (on-chain USDC transfer)
        """
        import time as _time

        from middleware.payment.verifier import X402Verifier

        # Get the x402 resource server if available
        resource_server = None
        try:
            from middleware.payment.x402_server import get_resource_server

            resource_server = get_resource_server(settings)
        except Exception:
            pass

        verifier = X402Verifier(
            chain_id=chain_id,
            rpc_url=settings.payment_rpc_url,
            verification_url=settings.payment_facilitator_url
            or settings.payment_verification_url,
            resource_server=resource_server,
        )

        # Choose verification path
        if payment_payload_b64:
            result = await verifier.verify_payment_payload(
                payload_b64=payment_payload_b64,
                expected_amount=settings.payment_usdc_amount,
                recipient_wallet=settings.payment_recipient_wallet,
            )
            verified_hash = result.settlement_tx_hash or result.tx_hash
        elif tx_hash:
            result = await verifier.verify_payment(
                tx_hash=tx_hash,
                expected_amount=settings.payment_usdc_amount,
                recipient_wallet=settings.payment_recipient_wallet,
            )
            verified_hash = tx_hash
        else:
            return {
                "success": False,
                "error": "Provide either tx_hash or payment_payload_b64",
                "message": "No payment proof provided.",
            }

        if result.verified and ctx:
            # Store payment verification + HMAC-signed receipt in session
            try:
                from auth.context import store_session_data
                from auth.types import SessionKey
                from middleware.payment.receipt import (
                    build_payer_identity,
                    create_payment_receipt,
                )

                session_id = ctx.session_id
                ttl_seconds = settings.payment_session_ttl_minutes * 60

                store_session_data(session_id, SessionKey.PAYMENT_VERIFIED, True)
                store_session_data(
                    session_id, SessionKey.PAYMENT_TX_HASH, verified_hash
                )
                store_session_data(
                    session_id, SessionKey.PAYMENT_VERIFIED_AT, _time.time()
                )
                store_session_data(
                    session_id, SessionKey.PAYMENT_AMOUNT, result.amount or ""
                )
                store_session_data(
                    session_id, SessionKey.PAYMENT_NETWORK, settings.payment_network
                )
                if result.settlement_tx_hash:
                    store_session_data(
                        session_id,
                        SessionKey.PAYMENT_SETTLE_TX_HASH,
                        result.settlement_tx_hash,
                    )

                # Build HMAC-signed receipt binding payment to identity
                payer = build_payer_identity(
                    session_id, result.payer_address or verified_hash
                )
                receipt = create_payment_receipt(
                    payer=payer,
                    tool_name="verify_payment",
                    amount=result.amount or "",
                    network=settings.payment_network,
                    tx_hash=verified_hash,
                    ttl_seconds=ttl_seconds,
                )
                store_session_data(
                    session_id, SessionKey.PAYMENT_PAYER_ADDRESS, payer.wallet_address
                )
                store_session_data(
                    session_id, SessionKey.PAYMENT_RECEIPT, receipt.model_dump()
                )
                store_session_data(
                    session_id, SessionKey.PAYMENT_RECEIPT_HMAC, receipt.hmac
                )

                expires_at = _time.time() + ttl_seconds
                logger.info(
                    "Payment verified and stored for session %s (payer=%s)",
                    session_id,
                    payer.wallet_address[:12] + "..."
                    if payer.wallet_address
                    else "unknown",
                )
            except Exception as e:
                logger.warning("Could not store payment in session: %s", e)
                expires_at = 0

            return {
                "success": True,
                "tx_hash": verified_hash,
                "amount": result.amount,
                "settlement_tx_hash": result.settlement_tx_hash,
                "network": settings.payment_network,
                "expires_at": expires_at,
                "message": (
                    f"Payment verified! Tool access unlocked for "
                    f"{settings.payment_session_ttl_minutes} minutes."
                ),
            }
        elif result.verified:
            return {
                "success": True,
                "tx_hash": verified_hash,
                "amount": result.amount,
                "settlement_tx_hash": result.settlement_tx_hash,
                "message": "Payment verified but session context unavailable -- may need to re-verify.",
            }
        else:
            return {
                "success": False,
                "tx_hash": verified_hash,
                "error": result.error,
                "message": f"Payment verification failed: {result.error}",
            }

    logger.info(
        "Server management tools registered: health_check, server_info, manage_credentials, manage_tools, set_privacy_mode, verify_payment"
    )
