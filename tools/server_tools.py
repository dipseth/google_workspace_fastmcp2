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

from fastmcp import FastMCP
from pydantic import Field
from typing_extensions import Annotated, Any, Dict, List, Literal, Optional, Union

from auth.context import (
    clear_session_disabled_tools,
    disable_tool_for_session,
    enable_tool_for_session,
    get_session_context,
    get_session_disabled_tools,
)
from auth.middleware import CredentialStorageMode
from config.enhanced_logging import setup_logger
from config.settings import settings
from tools.common_types import UserGoogleEmail
from tools.server_types import (
    CredentialInfo,
    HealthCheckResponse,
    ManageCredentialsResponse,
    ManageToolsByAnalyticsResponse,
    ManageToolsResponse,
    OAuthFlowStatus,
    SessionToolState,
    ToolInfo,
    ToolUsageInfo,
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

    Follows the same pattern as TagBasedResourceMiddleware._get_available_tools
    and resources/extraction_utilities.get_tools_for_service: use the internal
    FastMCP tool manager registry.

    Args:
        mcp: FastMCP server instance

    Returns:
        Dict[str, Any]: Dictionary mapping tool names to tool instances
    """
    if not hasattr(mcp, "_tool_manager") or not hasattr(mcp._tool_manager, "_tools"):
        logger.error("❌ Cannot access FastMCP tool manager; tool registry unavailable")
        return {}
    return mcp._tool_manager._tools


def _get_tool_enabled_state(tool_instance: Any) -> bool:
    """
    Best-effort check of a tool's enabled/disabled state.

    Tries common FastMCP attributes; defaults to True if unknown.

    Args:
        tool_instance: Tool instance to check

    Returns:
        bool: True if enabled or state unknown, False if explicitly disabled
    """
    try:
        if hasattr(tool_instance, "enabled"):
            return bool(getattr(tool_instance, "enabled"))
        # Some implementations may expose state via meta/annotations
        if hasattr(tool_instance, "meta") and isinstance(tool_instance.meta, dict):
            if "enabled" in tool_instance.meta:
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
            "(affects all clients) and session scope (affects only current session)."
        ),
        tags={"server", "tools", "feature_flag", "management"},
        annotations={
            "title": "Tool Enable/Disable Management",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def manage_tools_tool(
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
            "manage_tools_by_analytics",
            "health_check",
            "start_google_auth",
            "check_drive_auth",
        }

        # Helper to get current session state
        def _get_session_state() -> SessionToolState:
            session_id = get_session_context()
            if session_id:
                disabled = get_session_disabled_tools(session_id)
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

        # Count enabled/disabled tools
        total_tools = len(registry)
        enabled_count = sum(1 for t in registry.values() if _get_tool_enabled_state(t))
        disabled_count = total_tools - enabled_count

        if action_normalized == "list":
            tool_list = []
            session_state = _get_session_state()
            session_disabled = set(session_state.sessionDisabledTools)

            for name, tool in sorted(registry.items()):
                if not include_internal and name.startswith("_"):
                    continue
                enabled = _get_tool_enabled_state(tool)
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
                session_id = get_session_context()
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
                    if disable_tool_for_session(name, session_id, persist=True):
                        affected.append(name)
                    else:
                        skipped.append(name)
                        errors.append(f"Failed to disable tool '{name}' for session")

                session_state = _get_session_state()
                return ManageToolsResponse(
                    success=len(affected) > 0,
                    action=action,
                    scope=scope_normalized,
                    totalTools=total_tools,
                    enabledCount=enabled_count,  # Global state unchanged
                    disabledCount=disabled_count,  # Global state unchanged
                    toolsAffected=affected if affected else None,
                    toolsSkipped=skipped if skipped else None,
                    protectedTools=list(protected_tools_set),
                    sessionState=session_state,
                    message=f"Disabled {len(affected)} tools for this session"
                    + (f", skipped {len(skipped)}" if skipped else ""),
                    errors=errors if errors else None,
                )

            # Global scope disable (original behavior)
            for name in target_names:
                target = registry.get(name)
                if not target:
                    skipped.append(name)
                    errors.append(f"Tool '{name}' not found in registry")
                    continue
                if name in protected_tools_set:
                    skipped.append(name)
                    errors.append(f"Tool '{name}' is protected and cannot be disabled")
                    continue
                try:
                    if hasattr(target, "disable") and callable(target.disable):
                        target.disable()
                        affected.append(name)
                    else:
                        skipped.append(name)
                        errors.append(
                            f"Tool '{name}' does not support dynamic disable()"
                        )
                except Exception as e:
                    logger.error(f"Error disabling tool {name}: {e}", exc_info=True)
                    errors.append(f"Failed to disable tool '{name}': {e}")

            return ManageToolsResponse(
                success=len(affected) > 0,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=enabled_count - len(affected),
                disabledCount=disabled_count + len(affected),
                toolsAffected=affected if affected else None,
                toolsSkipped=skipped if skipped else None,
                protectedTools=list(protected_tools_set),
                message=f"Disabled {len(affected)} tools globally"
                + (f", skipped {len(skipped)}" if skipped else ""),
                errors=errors if errors else None,
            )

        if action_normalized == "disable_all_except":
            keep_set = set(target_names) | protected_tools_set

            # Session-scoped disable_all_except
            if scope_normalized == "session":
                session_id = get_session_context()
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
                    if disable_tool_for_session(name, session_id, persist=True):
                        affected.append(name)
                    else:
                        errors.append(f"Failed to disable tool '{name}' for session")

                session_state = _get_session_state()
                return ManageToolsResponse(
                    success=True,
                    action=action,
                    scope=scope_normalized,
                    totalTools=total_tools,
                    enabledCount=enabled_count,  # Global state unchanged
                    disabledCount=disabled_count,  # Global state unchanged
                    toolsAffected=affected if affected else None,
                    toolsSkipped=skipped if skipped else None,
                    protectedTools=list(protected_tools_set),
                    sessionState=session_state,
                    message=f"Kept {len(keep_set)} tools, disabled {len(affected)} tools for this session",
                    errors=errors if errors else None,
                )

            # Global scope (original behavior)
            for name, target in registry.items():
                if not include_internal and name.startswith("_"):
                    skipped.append(name)
                    continue
                if name in keep_set:
                    skipped.append(name)
                    continue
                if not hasattr(target, "disable") or not callable(target.disable):
                    skipped.append(name)
                    continue
                try:
                    target.disable()
                    affected.append(name)
                except Exception as e:
                    logger.error(f"Error disabling tool {name}: {e}", exc_info=True)
                    errors.append(f"{name}: {e}")

            return ManageToolsResponse(
                success=True,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=len(keep_set),
                disabledCount=len(affected),
                toolsAffected=affected if affected else None,
                toolsSkipped=skipped if skipped else None,
                protectedTools=list(protected_tools_set),
                message=f"Kept {len(keep_set)} tools, disabled {len(affected)} tools globally",
                errors=errors if errors else None,
            )

        if action_normalized == "enable":
            # Session-scoped enable
            if scope_normalized == "session":
                session_id = get_session_context()
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
                    if enable_tool_for_session(name, session_id, persist=True):
                        affected.append(name)
                    else:
                        skipped.append(name)
                        errors.append(f"Failed to enable tool '{name}' for session")

                session_state = _get_session_state()
                return ManageToolsResponse(
                    success=len(affected) > 0,
                    action=action,
                    scope=scope_normalized,
                    totalTools=total_tools,
                    enabledCount=enabled_count,  # Global state unchanged
                    disabledCount=disabled_count,  # Global state unchanged
                    toolsAffected=affected if affected else None,
                    toolsSkipped=skipped if skipped else None,
                    protectedTools=list(protected_tools_set),
                    sessionState=session_state,
                    message=f"Enabled {len(affected)} tools for this session"
                    + (f", skipped {len(skipped)}" if skipped else ""),
                    errors=errors if errors else None,
                )

            # Global scope (original behavior)
            for name in target_names:
                target = registry.get(name)
                if not target:
                    skipped.append(name)
                    errors.append(f"Tool '{name}' not found in registry")
                    continue
                try:
                    if hasattr(target, "enable") and callable(target.enable):
                        target.enable()
                        affected.append(name)
                    else:
                        skipped.append(name)
                        errors.append(
                            f"Tool '{name}' does not support dynamic enable()"
                        )
                except Exception as e:
                    logger.error(f"Error enabling tool {name}: {e}", exc_info=True)
                    errors.append(f"Failed to enable tool '{name}': {e}")

            return ManageToolsResponse(
                success=len(affected) > 0,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=enabled_count + len(affected),
                disabledCount=disabled_count - len(affected),
                toolsAffected=affected if affected else None,
                toolsSkipped=skipped if skipped else None,
                protectedTools=list(protected_tools_set),
                message=f"Enabled {len(affected)} tools globally"
                + (f", skipped {len(skipped)}" if skipped else ""),
                errors=errors if errors else None,
            )

        if action_normalized == "enable_all":
            # Session-scoped enable_all (clears session disabled list)
            if scope_normalized == "session":
                session_id = get_session_context()
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
                session_disabled_before = get_session_disabled_tools(session_id)
                affected = list(session_disabled_before)

                # Clear all session disables
                if clear_session_disabled_tools(session_id):
                    session_state = _get_session_state()
                    return ManageToolsResponse(
                        success=True,
                        action=action,
                        scope=scope_normalized,
                        totalTools=total_tools,
                        enabledCount=enabled_count,  # Global state unchanged
                        disabledCount=disabled_count,  # Global state unchanged
                        toolsAffected=affected if affected else None,
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

            # Global scope (original behavior)
            for name, target in registry.items():
                if not include_internal and name.startswith("_"):
                    skipped.append(name)
                    continue
                if not hasattr(target, "enable") or not callable(target.enable):
                    skipped.append(name)
                    continue
                try:
                    target.enable()
                    affected.append(name)
                except Exception as e:
                    logger.error(f"Error enabling tool {name}: {e}", exc_info=True)
                    errors.append(f"{name}: {e}")

            return ManageToolsResponse(
                success=True,
                action=action,
                scope=scope_normalized,
                totalTools=total_tools,
                enabledCount=len(affected),
                disabledCount=len(skipped),
                toolsAffected=affected if affected else None,
                toolsSkipped=skipped if skipped else None,
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
        name="manage_tools_by_analytics",
        description=(
            "Intelligently disable tools based on Qdrant usage analytics. Query historical "
            "tool usage data and selectively disable tools matching service filters (e.g., 'gmail', 'chat') "
            "with configurable usage thresholds. Supports dry-run preview mode before making changes."
        ),
        tags={"server", "tools", "qdrant", "analytics", "automation", "management"},
        annotations={
            "title": "Qdrant Analytics-Based Tool Management",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def manage_tools_by_analytics_tool(
        action: Annotated[
            Literal["preview", "disable", "enable"],
            Field(
                description="Action: 'preview' (show what would be affected), 'disable' (disable matched tools), 'enable' (re-enable matched tools)"
            ),
        ],
        service_filter: Annotated[
            Optional[str],
            Field(
                description="Filter tools by service name (e.g., 'gmail', 'chat', 'drive'). Uses extract_service_from_tool() for matching. Leave empty for all services."
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                description="Maximum number of tools to affect (top N by usage count). Default: 10"
            ),
        ] = 10,
        min_usage_count: Annotated[
            int,
            Field(
                description="Minimum usage count threshold - only affect tools with at least this many historical uses. Default: 1"
            ),
        ] = 1,
        min_score: Annotated[
            Optional[float],
            Field(
                description="Minimum relevance score (0.0-1.0) for semantic filtering. Only used with semantic queries. Default: 0.3"
            ),
        ] = None,
        user_google_email: UserGoogleEmail = None,
    ) -> ManageToolsByAnalyticsResponse:
        """
        Manage tools based on Qdrant usage analytics with intelligent filtering.

        This tool leverages Qdrant's historical tool response data to identify
        and manage tools based on actual usage patterns. Supports service-based
        filtering and usage thresholds.

        Args:
            action: Operation to perform - 'preview', 'disable', or 'enable'
            service_filter: Optional service name filter (gmail, chat, drive, etc.)
            limit: Maximum number of tools to affect (top N by usage)
            min_usage_count: Minimum historical usage count threshold
            min_score: Minimum semantic search relevance score (optional)
            user_google_email: User's email for access control

        Returns:
            ManageToolsByAnalyticsResponse with operation results and usage analytics
        """
        try:
            # Import Qdrant components
            from middleware.qdrant_core.client import get_or_create_client_manager
            from middleware.qdrant_core.config import load_config_from_settings
            from middleware.qdrant_core.query_parser import extract_service_from_tool
            from middleware.qdrant_core.search import QdrantSearchManager

            # Initialize or reuse a shared Qdrant client manager using the same URL/API key
            config = load_config_from_settings()
            client_manager = get_or_create_client_manager(
                config=config,
                qdrant_api_key=settings.qdrant_api_key,
                qdrant_url=settings.qdrant_url,
                auto_discovery=True,
            )
            search_manager = QdrantSearchManager(client_manager)

            # Ensure Qdrant is initialized
            if not client_manager.is_initialized:
                await client_manager.initialize()

            if not client_manager.is_available:
                return ManageToolsByAnalyticsResponse(
                    success=False,
                    action=action,
                    serviceFilter=service_filter,
                    minUsageCount=min_usage_count,
                    limit=limit,
                    toolsMatched=0,
                    message="Qdrant not available - cannot analyze tool usage data",
                    error="Qdrant is not running or not accessible",
                )

            # Get analytics grouped by tool_name
            logger.info("📊 Fetching Qdrant analytics for tool management...")
            analytics = await search_manager.get_analytics(group_by="tool_name")

            if "error" in analytics:
                return ManageToolsByAnalyticsResponse(
                    success=False,
                    action=action,
                    serviceFilter=service_filter,
                    minUsageCount=min_usage_count,
                    limit=limit,
                    toolsMatched=0,
                    message="Failed to retrieve analytics data",
                    error=str(analytics["error"]),
                )

            if not analytics.get("groups"):
                return ManageToolsByAnalyticsResponse(
                    success=True,
                    action=action,
                    serviceFilter=service_filter,
                    minUsageCount=min_usage_count,
                    limit=limit,
                    toolsMatched=0,
                    message="No tool usage data found in Qdrant. Analytics database may be empty.",
                )

            # Filter and rank tools based on criteria
            matched_tools = []

            for tool_name, tool_data in analytics["groups"].items():
                usage_count = tool_data.get("count", 0)

                # Skip if below usage threshold
                if usage_count < min_usage_count:
                    continue

                # Apply service filter if specified
                if service_filter:
                    tool_service = extract_service_from_tool(tool_name)
                    if tool_service.lower() != service_filter.lower():
                        continue

                matched_tools.append(
                    {
                        "tool_name": tool_name,
                        "usage_count": usage_count,
                        "service": extract_service_from_tool(tool_name),
                        "unique_users": tool_data.get("unique_users", 0),
                        "error_rate": tool_data.get("error_rate", 0.0),
                        "recent_activity": tool_data.get("recent_activity", {}),
                        "sample_point_ids": tool_data.get("point_ids", [])[
                            :3
                        ],  # First 3 point IDs
                    }
                )

            # Sort by usage count (descending) and limit
            matched_tools.sort(key=lambda x: x["usage_count"], reverse=True)
            matched_tools = matched_tools[:limit]

            if not matched_tools:
                filter_desc = (
                    f" matching service '{service_filter}'" if service_filter else ""
                )
                return ManageToolsByAnalyticsResponse(
                    success=True,
                    action=action,
                    serviceFilter=service_filter,
                    minUsageCount=min_usage_count,
                    limit=limit,
                    toolsMatched=0,
                    message=f"No tools found{filter_desc} with usage count >= {min_usage_count}",
                )

            # Get current tool registry
            registry = _get_tool_registry(mcp)
            if not registry:
                return ManageToolsByAnalyticsResponse(
                    success=False,
                    action=action,
                    serviceFilter=service_filter,
                    minUsageCount=min_usage_count,
                    limit=limit,
                    toolsMatched=len(matched_tools),
                    message="Unable to access FastMCP tool registry",
                    error="Tool registry not available",
                )

            # Build ToolUsageInfo objects for all matched tools
            usage_analytics = [
                ToolUsageInfo(
                    name=t["tool_name"],
                    usageCount=t["usage_count"],
                    service=t["service"],
                    lastUsed=(
                        t["recent_activity"].get("last_used")
                        if t["recent_activity"]
                        else None
                    ),
                    currentlyEnabled=t["tool_name"] in registry,
                )
                for t in matched_tools
            ]

            # Build results based on action
            if action == "preview":
                return ManageToolsByAnalyticsResponse(
                    success=True,
                    action=action,
                    serviceFilter=service_filter,
                    minUsageCount=min_usage_count,
                    limit=limit,
                    toolsMatched=len(matched_tools),
                    usageAnalytics=usage_analytics,
                    message=f"Preview: Found {len(matched_tools)} tool(s) matching criteria. Use action='disable' or 'enable' to modify.",
                )

            elif action in ["disable", "enable"]:
                # Extract tool names to manage
                target_names = [t["tool_name"] for t in matched_tools]

                # Filter out tools not in registry
                available_targets = [name for name in target_names if name in registry]
                missing_targets = [
                    name for name in target_names if name not in registry
                ]

                if not available_targets:
                    return ManageToolsByAnalyticsResponse(
                        success=False,
                        action=action,
                        serviceFilter=service_filter,
                        minUsageCount=min_usage_count,
                        limit=limit,
                        toolsMatched=len(matched_tools),
                        usageAnalytics=usage_analytics,
                        message="None of the matched tools are currently registered in FastMCP",
                        error="No available targets in registry",
                    )

                # Check for protected tools
                protected_tools = {
                    "manage_tools",
                    "manage_tools_by_analytics",
                    "health_check",
                    "start_google_auth",
                    "check_drive_auth",
                }

                protected_in_targets = [
                    name for name in available_targets if name in protected_tools
                ]
                safe_targets = [
                    name for name in available_targets if name not in protected_tools
                ]

                affected_tools: List[str] = []
                skipped_tools: List[str] = list(protected_in_targets)
                errors: List[str] = []

                # Execute action on safe targets
                if action == "disable":
                    for name in safe_targets:
                        target = registry[name]
                        try:
                            if hasattr(target, "disable") and callable(target.disable):
                                target.disable()
                                affected_tools.append(name)
                            else:
                                errors.append(
                                    f"'{name}' doesn't support disable() in this FastMCP version"
                                )
                        except Exception as e:
                            logger.error(
                                f"Error disabling tool {name}: {e}", exc_info=True
                            )
                            errors.append(f"Failed to disable '{name}': {e}")

                elif action == "enable":
                    for name in safe_targets:
                        target = registry[name]
                        try:
                            if hasattr(target, "enable") and callable(target.enable):
                                target.enable()
                                affected_tools.append(name)
                            else:
                                errors.append(
                                    f"'{name}' doesn't support enable() in this FastMCP version"
                                )
                        except Exception as e:
                            logger.error(
                                f"Error enabling tool {name}: {e}", exc_info=True
                            )
                            errors.append(f"Failed to enable '{name}': {e}")

                # Add missing targets to skipped
                skipped_tools.extend(missing_targets)

                return ManageToolsByAnalyticsResponse(
                    success=len(errors) == 0,
                    action=action,
                    serviceFilter=service_filter,
                    minUsageCount=min_usage_count,
                    limit=limit,
                    toolsMatched=len(matched_tools),
                    toolsAffected=affected_tools if affected_tools else None,
                    toolsSkipped=skipped_tools if skipped_tools else None,
                    usageAnalytics=usage_analytics,
                    message=f"Successfully {action}d {len(affected_tools)} tool(s). {len(skipped_tools)} skipped (protected or missing).",
                    errors=errors if errors else None,
                )

            else:
                return ManageToolsByAnalyticsResponse(
                    success=False,
                    action=action,
                    serviceFilter=service_filter,
                    minUsageCount=min_usage_count,
                    limit=limit,
                    toolsMatched=0,
                    message=f"Invalid action '{action}'",
                    error="Valid actions are: preview, disable, enable",
                )

        except Exception as e:
            logger.error(
                f"❌ Analytics-based tool management failed: {e}", exc_info=True
            )
            return ManageToolsByAnalyticsResponse(
                success=False,
                action=action,
                serviceFilter=service_filter,
                minUsageCount=min_usage_count,
                limit=limit,
                toolsMatched=0,
                message="Tool management by analytics failed",
                error=str(e),
            )

    logger.info(
        "✅ Server management tools registered: health_check, server_info, manage_credentials, manage_tools, manage_tools_by_analytics"
    )
