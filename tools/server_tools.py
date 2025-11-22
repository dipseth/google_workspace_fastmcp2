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

import logging
import os
import json
from pathlib import Path
from typing_extensions import Optional, Literal, Annotated, Any, Dict, Union, List

from fastmcp import FastMCP
from pydantic import Field
from config.settings import settings
from auth.middleware import CredentialStorageMode
from tools.common_types import UserGoogleEmail

from config.enhanced_logging import setup_logger

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
) -> str:
    """
    Check server health and configuration.

    Args:
        google_auth_provider: Optional GoogleProvider instance from server context
        credential_storage_mode: Current credential storage mode from server context
        user_google_email: Optional user email for context-specific health checks

    Returns:
        str: Server health status
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

        # Phase 1 OAuth Migration Health Checks
        oauth_flow_status = await check_oauth_flows_health(google_auth_provider)

        status = (
            "✅ Healthy"
            if (creds_accessible and oauth_configured)
            else "⚠️ Configuration Issues"
        )

        return (
            f"🏥 **Google Drive Upload Server Health Check**\n\n"
            f"**Status:** {status}\n"
            f"**Server:** {settings.server_name} v1.0.0\n"
            f"**Host:** {settings.server_host}:{settings.server_port}\n"
            f"**OAuth Configured:** {'✅' if oauth_configured else '❌'}\n"
            f"**Credentials Directory:** {'✅' if creds_accessible else '❌'} ({settings.credentials_dir})\n"
            f"**Active Sessions:** {active_sessions}\n"
            f"**Log Level:** {settings.log_level}\n\n"
            f"**🔄 Phase 1 OAuth Migration Status:**\n"
            f"{oauth_flow_status}\n\n"
            f"**OAuth Callback URL:** {settings.dynamic_oauth_redirect_uri}"
        )

    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return f"❌ Health check failed: {e}"


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
) -> str:
    """
    Manage credential storage and security settings.

    Args:
        email: User's Google email address
        action: Action to perform ('status', 'migrate', 'summary', 'delete')
        new_storage_mode: Target storage mode for migration ('FILE_PLAINTEXT', 'FILE_ENCRYPTED', 'MEMORY_ONLY', 'MEMORY_WITH_BACKUP')

    Returns:
        str: Result of the credential management operation
    """
    try:
        from auth.context import get_auth_middleware

        # Get the AuthMiddleware instance
        auth_middleware = get_auth_middleware()
        if not auth_middleware:
            return "❌ AuthMiddleware not available"

        if action == "status":
            # Get credential status
            summary = await auth_middleware.get_credential_summary(email)
            if summary:
                return (
                    f"📊 **Credential Status for {email}**\n\n"
                    f"**Storage Mode:** {summary['storage_mode']}\n"
                    f"**File Path:** {summary['file_path']}\n"
                    f"**File Exists:** {'✅' if summary['file_exists'] else '❌'}\n"
                    f"**In Memory:** {'✅' if summary['in_memory'] else '❌'}\n"
                    f"**Is Encrypted:** {'✅' if summary['is_encrypted'] else '❌'}\n"
                    f"**Last Modified:** {summary.get('last_modified', 'Unknown')}\n"
                    f"**File Size:** {summary.get('file_size', 'Unknown')} bytes"
                )
            else:
                return f"❌ No credentials found for {email}"

        elif action == "migrate":
            if not new_storage_mode:
                return "❌ new_storage_mode is required for migration"

            try:
                target_mode = CredentialStorageMode[new_storage_mode.upper()]
            except KeyError:
                return f"❌ Invalid storage mode '{new_storage_mode}'. Valid options: FILE_PLAINTEXT, FILE_ENCRYPTED, MEMORY_ONLY, MEMORY_WITH_BACKUP"

            # Perform migration
            success = await auth_middleware.migrate_credentials(email, target_mode)
            if success:
                return f"✅ Successfully migrated credentials for {email} to {target_mode.value} mode"
            else:
                return f"❌ Failed to migrate credentials for {email} to {target_mode.value} mode"

        elif action == "summary":
            # Get summary of all credentials
            # This would require implementing a method to list all credential files
            return f"📋 **Credential Summary**\n\nCurrent storage mode: {auth_middleware.storage_mode.value}\n\nUse 'status' action with specific email for detailed information."

        elif action == "delete":
            # Delete credentials (this would need to be implemented in AuthMiddleware)
            return f"⚠️ Credential deletion not yet implemented. Please manually delete credential files if needed."

        else:
            return f"❌ Invalid action '{action}'. Valid actions: status, migrate, summary, delete"

    except Exception as e:
        logger.error(f"Credential management error: {e}", exc_info=True)
        return f"❌ Credential management failed: {e}"


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
    ) -> str:
        """
        Check server health and configuration.

        Args:
            user_google_email: The user's Google email address. If None, uses the current
                             authenticated user from FastMCP context (auto-injected by middleware).

        Returns:
            str: Server health status including OAuth migration status, active sessions, and configuration
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
    ) -> str:
        """
        Manage credential storage and security settings.

        Args:
            email: User's Google email address
            action: Action to perform - 'status', 'migrate', 'summary', or 'delete'
            new_storage_mode: Target storage mode for migration (required when action='migrate')

        Returns:
            str: Result of the credential management operation
        """
        return await manage_credentials(email, action, new_storage_mode)

    @mcp.tool(
        name="manage_tools",
        description=(
            "List, enable, or disable FastMCP tools at runtime using FastMCP 2.8.0 "
            "tool enable/disable support"
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
        include_internal: Annotated[
            bool,
            Field(
                description="If True, include internal/system tools (names starting with '_') in listing"
            ),
        ] = False,
        user_google_email: UserGoogleEmail = None,
    ) -> str:
        """
        Manage FastMCP tool availability using FastMCP 2.8.0 enable/disable support.
        
        Actions:
            - 'list':
                List all registered tools and their enabled/disabled state.
            - 'disable':
                Disable one or more tools by exact name. Disabled tools are hidden from
                list_tools and behave as unknown tools to clients.
            - 'enable':
                Re-enable one or more previously disabled tools by exact name.
            - 'disable_all_except':
                Disable every tool except a provided keep list and a built-in set of
                protected infra/management tools (e.g., manage_tools, health_check).
            - 'enable_all':
                Enable all tools in the registry (optionally excluding internal tools
                whose names start with '_', depending on include_internal).
        
        Args:
            action:
                One of: 'list', 'disable', 'enable', 'disable_all_except', 'enable_all'.
            tool_names:
                Tool name(s) to enable/disable. Supports:
                  - Single string: "tool_a"
                  - List: ["tool_a", "tool_b"]
                  - Comma-separated string: "tool_a,tool_b"
                  - JSON list string: '["tool_a", "tool_b"]'
            include_internal:
                If True, include internal/system tools (names starting with '_') in listing.

        Returns:
            Human-readable status string describing the result.
        """
        action_normalized = action.lower().strip()
        valid_actions = {"list", "disable", "enable", "disable_all_except", "enable_all"}

        if action_normalized not in valid_actions:
            return "❌ Invalid action. Valid actions are: " "list, disable, enable"

        # Discover current tool registry (does not interfere with middleware tests,
        # which rely on their own mock-based discovery logic).
        registry = _get_tool_registry(mcp)
        if not registry:
            return "❌ Unable to access FastMCP tool registry"

        # Protect critical tools from being disabled
        protected_tools = {
            "manage_tools",
            "manage_tools_by_analytics",
            "health_check",
            "start_google_auth",
            "check_drive_auth",
        }

        if action_normalized == "list":
            lines = [
                "🧰 **Registered FastMCP Tools**",
                "",
                "Name | Enabled | Protected",
                "---- | ------- | ---------",
            ]
            for name, tool in sorted(registry.items()):
                if not include_internal and name.startswith("_"):
                    continue
                enabled = _get_tool_enabled_state(tool)
                is_protected = name in protected_tools
                lines.append(
                    f"{name} | {'✅' if enabled else '⭕'} | "
                    f"{'🛡️' if is_protected else ''}"
                )
            return "\n".join(lines)

        def _normalize_tool_names(names_input):
            """
            Normalize tool name(s) into a de-duplicated list.

            Supports:
              - Single string: "tool_a"
              - List: ["tool_a", "tool_b"]
              - Comma-separated string: "tool_a,tool_b"
              - JSON list string: '["tool_a", "tool_b"]'
            """
            if not names_input:
                return []

            names = []

            # Handle different input types
            if isinstance(names_input, list):
                names.extend(str(n) for n in names_input)
            elif isinstance(names_input, str):
                # Try JSON parsing first
                try:
                    parsed = json.loads(names_input)
                    if isinstance(parsed, list):
                        names.extend(str(n) for n in parsed)
                    else:
                        names.append(str(parsed))
                except json.JSONDecodeError:
                    # Fallback: comma-separated or single string
                    if "," in names_input:
                        names.extend(
                            n.strip() for n in names_input.split(",") if n.strip()
                        )
                    else:
                        names.append(names_input.strip())
            else:
                names.append(str(names_input))

            # De-duplicate while preserving order
            seen = set()
            deduped = []
            for n in names:
                if n and n not in seen:
                    seen.add(n)
                    deduped.append(n)
            return deduped

        target_names = _normalize_tool_names(tool_names)
        
        # For some actions, we require at least one concrete tool name
        if action_normalized in {"disable", "enable", "disable_all_except"} and not target_names:
            return "❌ 'tool_names' parameter is required for disable/enable/disable_all_except actions"
        
        results = []
        
        if action_normalized == "disable":
            for name in target_names:
                target = registry.get(name)
                if not target:
                    results.append(f"❌ Tool '{name}' not found in registry")
                    continue
        
                if name in protected_tools:
                    results.append(
                        f"🛡️ Tool '{name}' is protected and cannot be disabled"
                    )
                    continue
        
                # Call FastMCP 2.8.0 tool disable API if available
                try:
                    if hasattr(target, "disable") and callable(target.disable):
                        target.disable()
                        results.append(
                            f"⭕ Tool '{name}' disabled. It will no longer appear in "
                            "list_tools and calls will return Unknown tool."
                        )
                    else:
                        results.append(
                            f"❌ Tool '{name}' does not support dynamic disable() "
                            "in this FastMCP version"
                        )
                except Exception as e:
                    logger.error(f"Error disabling tool {name}: {e}", exc_info=True)
                    results.append(f"❌ Failed to disable tool '{name}': {e}")
        
            header = "🧰 **Tool disable results**"
            return "\n".join([header, ""] + results)
        
        if action_normalized == "disable_all_except":
            # Keep list is explicit target_names plus always-protected infra tools
            keep_set = set(target_names) | protected_tools
            disabled = []
            skipped = []
            errors = []
        
            for name, target in registry.items():
                # Optionally skip internal/system tools
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
                    disabled.append(name)
                except Exception as e:
                    logger.error(f"Error disabling tool {name}: {e}", exc_info=True)
                    errors.append(f"{name}: {e}")
        
            header_lines = [
                "🧰 **Tool disable_all_except results**",
                "",
                f"Kept (explicit or protected): {len(keep_set)} tools",
                f"Disabled: {len(disabled)} tools",
                f"Skipped (internal/unsupported): {len(skipped)} tools",
                "",
            ]
            detail_lines = []
            if disabled:
                detail_lines.append("⭕ Disabled tools:")
                detail_lines.extend(f"  - {n}" for n in sorted(disabled))
                detail_lines.append("")
            if errors:
                detail_lines.append("⚠️ Errors:")
                detail_lines.extend(f"  - {e}" for e in errors)
        
            return "\n".join(header_lines + detail_lines)
        
        if action_normalized == "enable":
            for name in target_names:
                target = registry.get(name)
                if not target:
                    results.append(f"❌ Tool '{name}' not found in registry")
                    continue

                # Call FastMCP 2.8.0 tool enable API if available
                try:
                    if hasattr(target, "enable") and callable(target.enable):
                        target.enable()
                        results.append(
                            f"✅ Tool '{name}' enabled and available to clients."
                        )
                    else:
                        results.append(
                            f"❌ Tool '{name}' does not support dynamic enable() "
                            "in this FastMCP version"
                        )
                except Exception as e:
                    logger.error(f"Error enabling tool {name}: {e}", exc_info=True)
                    results.append(f"❌ Failed to enable tool '{name}': {e}")

            header = "🧰 **Tool enable results**"
            return "\n".join([header, ""] + results)

        if action_normalized == "enable_all":
            enabled = []
            skipped = []
            errors = []

            for name, target in registry.items():
                # Optionally skip internal/system tools
                if not include_internal and name.startswith("_"):
                    skipped.append(name)
                    continue

                if not hasattr(target, "enable") or not callable(target.enable):
                    skipped.append(name)
                    continue

                try:
                    target.enable()
                    enabled.append(name)
                except Exception as e:
                    logger.error(f"Error enabling tool {name}: {e}", exc_info=True)
                    errors.append(f"{name}: {e}")

            header_lines = [
                "🧰 **Tool enable_all results**",
                "",
                f"Enabled: {len(enabled)} tools",
                f"Skipped (internal/unsupported): {len(skipped)} tools",
                "",
            ]
            detail_lines = []
            if enabled:
                detail_lines.append("✅ Enabled tools:")
                detail_lines.extend(f"  - {n}" for n in sorted(enabled))
                detail_lines.append("")
            if errors:
                detail_lines.append("⚠️ Errors:")
                detail_lines.extend(f"  - {e}" for e in errors)

            return "\n".join(header_lines + detail_lines)

        # Should be unreachable due to earlier validation
        return "❌ Unknown error while managing tools"

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
    ) -> str:
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
            Human-readable summary of matched tools and actions taken
        """
        try:
            # Import Qdrant components
            from middleware.qdrant_core.search import QdrantSearchManager
            from middleware.qdrant_core.client import get_or_create_client_manager
            from middleware.qdrant_core.query_parser import extract_service_from_tool
            from middleware.qdrant_core.config import load_config_from_settings
             
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
                return "❌ Qdrant not available - cannot analyze tool usage data. Ensure Qdrant is running."
            
            # Get analytics grouped by tool_name
            logger.info(f"📊 Fetching Qdrant analytics for tool management...")
            analytics = await search_manager.get_analytics(group_by="tool_name")
            
            if "error" in analytics:
                return f"❌ Failed to get analytics: {analytics['error']}"
            
            if not analytics.get("groups"):
                return "⚠️ No tool usage data found in Qdrant. Analytics database may be empty."
            
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
                
                matched_tools.append({
                    "tool_name": tool_name,
                    "usage_count": usage_count,
                    "service": extract_service_from_tool(tool_name),
                    "unique_users": tool_data.get("unique_users", 0),
                    "error_rate": tool_data.get("error_rate", 0.0),
                    "recent_activity": tool_data.get("recent_activity", {}),
                    "sample_point_ids": tool_data.get("point_ids", [])[:3],  # First 3 point IDs
                })
            
            # Sort by usage count (descending) and limit
            matched_tools.sort(key=lambda x: x["usage_count"], reverse=True)
            matched_tools = matched_tools[:limit]
            
            if not matched_tools:
                filter_desc = f" matching service '{service_filter}'" if service_filter else ""
                return f"ℹ️ No tools found{filter_desc} with usage count >= {min_usage_count}"
            
            # Get current tool registry
            registry = _get_tool_registry(mcp)
            if not registry:
                return "❌ Unable to access FastMCP tool registry"
            
            # Build results based on action
            if action == "preview":
                lines = [
                    "🔍 **Analytics-Based Tool Management Preview**",
                    "",
                    f"**Filters Applied:**",
                    f"  - Service: {service_filter or 'All services'}",
                    f"  - Min Usage Count: {min_usage_count}",
                    f"  - Limit: Top {limit} tools",
                    "",
                    f"**Matched Tools:** {len(matched_tools)} tool(s)",
                    "",
                    "Rank | Tool Name | Service | Usage Count | Users | Error Rate | In Registry",
                    "---- | --------- | ------- | ----------- | ----- | ---------- | -----------",
                ]
                
                for idx, tool_info in enumerate(matched_tools, 1):
                    tool_name = tool_info["tool_name"]
                    in_registry = "✅" if tool_name in registry else "❌"
                    
                    lines.append(
                        f"{idx} | {tool_name} | {tool_info['service']} | "
                        f"{tool_info['usage_count']} | {tool_info['unique_users']} | "
                        f"{tool_info['error_rate']:.1%} | {in_registry}"
                    )
                
                lines.extend([
                    "",
                    "**Sample Point IDs for Investigation:**",
                ])
                
                for tool_info in matched_tools[:5]:  # Show point IDs for top 5
                    if tool_info["sample_point_ids"]:
                        lines.append(f"  - {tool_info['tool_name']}: {', '.join(tool_info['sample_point_ids'])}")
                
                lines.extend([
                    "",
                    "💡 **Next Steps:**",
                    f"  - Use action='disable' to disable these {len(matched_tools)} tools",
                    f"  - Use action='enable' to re-enable previously disabled tools",
                    "  - Adjust filters to refine tool selection",
                ])
                
                return "\n".join(lines)
            
            elif action in ["disable", "enable"]:
                # Extract tool names to manage
                target_names = [t["tool_name"] for t in matched_tools]
                
                # Filter out tools not in registry
                available_targets = [name for name in target_names if name in registry]
                missing_targets = [name for name in target_names if name not in registry]
                
                if not available_targets:
                    return f"❌ None of the matched tools are currently registered in FastMCP"
                
                # Check for protected tools
                protected_tools = {
                    "manage_tools",
                    "manage_tools_by_analytics",
                    "health_check",
                    "start_google_auth",
                    "check_drive_auth",
                }
                
                protected_in_targets = [name for name in available_targets if name in protected_tools]
                safe_targets = [name for name in available_targets if name not in protected_tools]
                
                results = []
                
                # Report protected tools
                if protected_in_targets and action == "disable":
                    results.append(f"🛡️ Skipped {len(protected_in_targets)} protected tool(s): {', '.join(protected_in_targets)}")
                
                # Execute action on safe targets
                if action == "disable":
                    for name in safe_targets:
                        target = registry[name]
                        try:
                            if hasattr(target, "disable") and callable(target.disable):
                                target.disable()
                                # Find usage info for this tool
                                tool_info = next((t for t in matched_tools if t["tool_name"] == name), {})
                                usage = tool_info.get("usage_count", "?")
                                results.append(f"⭕ Disabled '{name}' (usage: {usage})")
                            else:
                                results.append(f"❌ '{name}' doesn't support disable() in this FastMCP version")
                        except Exception as e:
                            logger.error(f"Error disabling tool {name}: {e}", exc_info=True)
                            results.append(f"❌ Failed to disable '{name}': {e}")
                
                elif action == "enable":
                    for name in safe_targets:
                        target = registry[name]
                        try:
                            if hasattr(target, "enable") and callable(target.enable):
                                target.enable()
                                # Find usage info for this tool
                                tool_info = next((t for t in matched_tools if t["tool_name"] == name), {})
                                usage = tool_info.get("usage_count", "?")
                                results.append(f"✅ Enabled '{name}' (usage: {usage})")
                            else:
                                results.append(f"❌ '{name}' doesn't support enable() in this FastMCP version")
                        except Exception as e:
                            logger.error(f"Error enabling tool {name}: {e}", exc_info=True)
                            results.append(f"❌ Failed to enable '{name}': {e}")
                
                # Report missing tools
                if missing_targets:
                    results.append(f"ℹ️ {len(missing_targets)} tool(s) not in registry: {', '.join(missing_targets[:5])}")
                
                # Build summary
                header_lines = [
                    f"🧰 **Analytics-Based Tool {action.title()} Results**",
                    "",
                    f"**Query Filters:**",
                    f"  - Service: {service_filter or 'All'}",
                    f"  - Min Usage: {min_usage_count}",
                    f"  - Top N: {limit}",
                    "",
                    f"**Matched:** {len(matched_tools)} tools from analytics",
                    f"**Affected:** {len(safe_targets)} tools {action}d",
                    f"**Protected:** {len(protected_in_targets)} tools skipped",
                    "",
                ]
                
                return "\n".join(header_lines + results)
            
            else:
                return f"❌ Invalid action '{action}'. Valid actions: preview, disable, enable"
            
        except Exception as e:
            logger.error(f"❌ Analytics-based tool management failed: {e}", exc_info=True)
            return f"❌ Tool management by analytics failed: {e}"

    logger.info(
        "✅ Server management tools registered: health_check, server_info, manage_credentials, manage_tools, manage_tools_by_analytics"
    )
