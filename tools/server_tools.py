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
from typing import Optional

from fastmcp import FastMCP
from config.settings import settings
from auth.middleware import CredentialStorageMode
from tools.common_types import UserGoogleEmail

logger = logging.getLogger(__name__)


async def check_oauth_flows_health(google_auth_provider=None) -> str:
    """Check health of both OAuth flows during migration.
    
    Args:
        google_auth_provider: Optional GoogleProvider instance from server context
    
    Returns:
        Health status string for OAuth flows
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
        status_lines.append("  **Unified Auth (FastMCP 2.12.0 GoogleProvider):** ✅ ENABLED")
        
        # Check if GoogleProvider is configured
        if google_auth_provider:
            status_lines.append("    - GoogleProvider: ✅ Configured (Phase 1: not enforced)")
        else:
            status_lines.append("    - GoogleProvider: ❌ Not configured")
        
        # Check environment variables
        env_vars = {
            "FASTMCP_SERVER_AUTH": settings.fastmcp_server_auth,
            "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID": bool(settings.fastmcp_server_auth_google_client_id),
            "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET": bool(settings.fastmcp_server_auth_google_client_secret),
            "FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL": settings.fastmcp_server_auth_google_base_url
        }
        
        all_vars_set = all([
            env_vars["FASTMCP_SERVER_AUTH"] == "GOOGLE",
            env_vars["FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID"],
            env_vars["FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET"],
            env_vars["FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL"]
        ])
        
        if all_vars_set:
            status_lines.append("    - Environment Variables: ✅ All set")
        else:
            status_lines.append("    - Environment Variables: ⚠️ Missing required vars")
    else:
        status_lines.append("  **Unified Auth (FastMCP 2.12.0 GoogleProvider):** ⭕ DISABLED")
    
    # Check legacy flow status
    use_google_oauth = os.getenv("USE_GOOGLE_OAUTH", "true").lower() == "true"
    enable_jwt_auth = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"
    
    if LEGACY_COMPAT_MODE:
        status_lines.append("  **Legacy OAuth Flow:** ✅ ACTIVE (backward compatibility)")
        
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
            
            status_lines.append(f"    - Total Credentials: {migration_status['total_credentials']}")
            status_lines.append(f"    - Format Distribution: {migration_status['format_distribution']}")
            status_lines.append(f"    - Successful Migrations: {migration_status['successful_migrations']}")
            status_lines.append(f"    - Failed Migrations: {migration_status['failed_migrations']}")
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
        status_lines.append("  **Enhanced Logging:** ✅ ENABLED (verbose migration tracking)")
    else:
        status_lines.append("  **Enhanced Logging:** ⭕ DISABLED")
    
    # Overall migration phase status
    status_lines.append("\n  **Migration Phase:** Phase 1 - Environment Setup & Core Components")
    
    if ENABLE_UNIFIED_AUTH and LEGACY_COMPAT_MODE:
        status_lines.append("  **Mode:** 🔄 Dual-flow operation (both flows active)")
    elif ENABLE_UNIFIED_AUTH:
        status_lines.append("  **Mode:** 🆕 Unified flow only (legacy disabled)")
    else:
        status_lines.append("  **Mode:** 🔙 Legacy flow only (unified not enabled)")
    
    return "\n".join(status_lines)


async def health_check(google_auth_provider=None, credential_storage_mode=None, user_google_email=None) -> str:
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
        creds_accessible = creds_dir.exists() and os.access(creds_dir, os.R_OK | os.W_OK)
        
        # Check OAuth configuration
        oauth_configured = bool(settings.google_client_id and settings.google_client_secret)
        
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
        
        status = "✅ Healthy" if (creds_accessible and oauth_configured) else "⚠️ Configuration Issues"
        
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
    email: str,
    action: str,
    new_storage_mode: Optional[str] = None
) -> str:
    """
    Manage credential storage and security settings.
    
    Args:
        email: User's Google email address
        action: Action to perform ('status', 'migrate', 'summary', 'delete')
        new_storage_mode: Target storage mode for migration ('PLAINTEXT', 'ENCRYPTED', 'MEMORY_ONLY', 'HYBRID')
    
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
            "openWorldHint": False
        }
    )
    async def health_check_tool(user_google_email: UserGoogleEmail = None) -> str:
        """
        Check server health and configuration.
        
        Args:
            user_google_email: The user's Google email address (auto-injected by middleware)
        
        Returns:
            str: Server health status
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
            "openWorldHint": False
        }
    )
    async def manage_credentials_tool(
        email: str,
        action: str,
        new_storage_mode: Optional[str] = None
    ) -> str:
        """
        Manage credential storage and security settings.
        
        Args:
            email: User's Google email address
            action: Action to perform ('status', 'migrate', 'summary', 'delete')
            new_storage_mode: Target storage mode for migration ('PLAINTEXT', 'ENCRYPTED', 'MEMORY_ONLY', 'HYBRID')
        
        Returns:
            str: Result of the credential management operation
        """
        return await manage_credentials(email, action, new_storage_mode)
    
    logger.info("✅ Server management tools registered: health_check, server_info, manage_credentials")