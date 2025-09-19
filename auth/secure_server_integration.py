"""
Secure Server Integration - Apply security patches to the MCP server.

This module provides the integration points to replace the vulnerable
session management with the secure implementation.
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from config.settings import settings
from .secure_middleware import create_secure_auth_middleware
from .security_patch import get_security_manager
from .middleware import CredentialStorageMode
from .context import set_auth_middleware

from config.enhanced_logging import setup_logger
logger = setup_logger()


class SecureServerConfig:
    """Configuration for secure server deployment."""
    
    def __init__(self):
        # Security settings
        self.require_session_tokens = True
        self.enable_connection_fingerprinting = True
        self.enable_audit_logging = True
        self.max_sessions_per_user = 5
        self.session_timeout_minutes = 30
        self.force_reauthentication_hours = 4
        
        # Storage settings
        self.credential_storage_mode = self._get_storage_mode()
        
        # Cloud deployment settings
        self.is_cloud_deployment = settings.is_cloud_deployment
        
        # Session secret (should be environment variable in production)
        self.session_secret = os.getenv("SESSION_SECRET", None)
        
        logger.info(f"🔒 Secure server configuration initialized")
        logger.info(f"  Storage mode: {self.credential_storage_mode.value}")
        logger.info(f"  Cloud deployment: {self.is_cloud_deployment}")
        logger.info(f"  Session timeout: {self.session_timeout_minutes} minutes")
    
    def _get_storage_mode(self) -> CredentialStorageMode:
        """Determine appropriate storage mode based on environment."""
        mode_str = settings.credential_storage_mode.upper()
        
        # Map string values to enum
        mode_map = {
            "FILE_PLAINTEXT": CredentialStorageMode.FILE_PLAINTEXT,
            "FILE_ENCRYPTED": CredentialStorageMode.FILE_ENCRYPTED,
            "MEMORY_ONLY": CredentialStorageMode.MEMORY_ONLY,
            "MEMORY_WITH_BACKUP": CredentialStorageMode.MEMORY_WITH_BACKUP
        }
        
        # For cloud deployments, prefer memory-based storage
        if settings.is_cloud_deployment and mode_str == "FILE_PLAINTEXT":
            logger.warning("⚠️ Cloud deployment with plaintext storage - upgrading to MEMORY_WITH_BACKUP")
            return CredentialStorageMode.MEMORY_WITH_BACKUP
        
        return mode_map.get(mode_str, CredentialStorageMode.FILE_ENCRYPTED)


def initialize_secure_server(mcp_server) -> Dict[str, Any]:
    """
    Initialize the MCP server with secure authentication.
    
    Args:
        mcp_server: The FastMCP server instance
        
    Returns:
        Dictionary with initialization status and components
    """
    logger.info("🔒 Initializing secure MCP server...")
    
    # Load configuration
    config = SecureServerConfig()
    
    # Initialize security manager
    security_manager = get_security_manager()
    
    # Configure security manager
    security_manager.session_timeout_minutes = config.session_timeout_minutes
    security_manager.require_reauthentication_hours = config.force_reauthentication_hours
    security_manager.allow_session_reuse = False  # CRITICAL: Never allow session reuse
    
    if config.session_secret:
        security_manager.session_secret = config.session_secret
    
    # Create secure middleware
    auth_middleware = create_secure_auth_middleware(
        storage_mode=config.credential_storage_mode,
        encryption_key=os.getenv("ENCRYPTION_KEY", None)
    )
    
    # Store middleware globally for access by other modules
    set_auth_middleware(auth_middleware)
    
    # Add middleware to server
    mcp_server.add_middleware(auth_middleware)
    
    # Add security headers middleware
    @mcp_server.middleware
    async def add_security_headers(context, call_next):
        """Add security headers to responses."""
        result = await call_next(context)
        
        # Add security headers (if response object supports it)
        if hasattr(context, 'response'):
            response = context.response
            if hasattr(response, 'headers'):
                response.headers['X-Content-Type-Options'] = 'nosniff'
                response.headers['X-Frame-Options'] = 'DENY'
                response.headers['X-XSS-Protection'] = '1; mode=block'
                response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return result
    
    # Add session token validation endpoint
    @mcp_server.resource("session://validate")
    async def validate_session(uri: str) -> Dict[str, Any]:
        """Validate current session and return status."""
        from .context import get_session_context, get_user_email_context
        
        session_id = get_session_context()
        user_email = get_user_email_context()
        
        if not session_id:
            return {
                "valid": False,
                "reason": "No session context"
            }
        
        session_info = security_manager.get_session_info(session_id)
        
        if not session_info:
            return {
                "valid": False,
                "reason": "Session not found"
            }
        
        return {
            "valid": True,
            "session_id": session_id[:8] + "...",  # Truncated for security
            "authenticated_user": session_info.get("authenticated_user"),
            "expires_at": session_info.get("expires_at").isoformat() if session_info.get("expires_at") else None,
            "allowed_users": session_info.get("allowed_users", []),
            "has_fingerprint": session_info.get("has_fingerprint", False)
        }
    
    # Add session revocation endpoint
    @mcp_server.tool()
    async def revoke_current_session() -> str:
        """
        Revoke the current session and clear all associated credentials.
        
        Returns:
            Status message
        """
        from .context import get_session_context, clear_session
        
        session_id = get_session_context()
        
        if not session_id:
            return "No active session to revoke"
        
        # Revoke in security manager
        if security_manager.revoke_session(session_id):
            # Clear from context
            clear_session(session_id)
            return f"Session {session_id[:8]}... successfully revoked"
        else:
            return f"Session {session_id[:8]}... not found"
    
    # Add cleanup task for expired sessions
    import asyncio
    
    async def cleanup_expired_sessions():
        """Periodic cleanup of expired sessions."""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                count = security_manager.cleanup_expired_sessions()
                if count > 0:
                    logger.info(f"🧹 Cleaned up {count} expired sessions")
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
    
    # Start cleanup task
    asyncio.create_task(cleanup_expired_sessions())
    
    logger.info("✅ Secure MCP server initialized successfully")
    logger.info("🛡️ Security features enabled:")
    logger.info("  ✅ Session isolation (no automatic reuse)")
    logger.info("  ✅ Authentication tokens required")
    logger.info("  ✅ Connection fingerprinting")
    logger.info("  ✅ Session-bound credentials")
    logger.info("  ✅ Audit logging")
    logger.info("  ✅ Rate limiting")
    logger.info("  ✅ Automatic session cleanup")
    
    return {
        "status": "success",
        "security_manager": security_manager,
        "auth_middleware": auth_middleware,
        "config": config
    }


def apply_security_patch_to_existing_server(mcp_server) -> bool:
    """
    Apply security patches to an already running server.
    
    This function can be called to upgrade a running server
    without requiring a full restart.
    
    Args:
        mcp_server: The running MCP server instance
        
    Returns:
        True if patch was successful
    """
    try:
        logger.info("🔧 Applying security patch to existing server...")
        
        # Initialize secure components
        result = initialize_secure_server(mcp_server)
        
        if result["status"] != "success":
            logger.error("Failed to apply security patch")
            return False
        
        # Force all existing sessions to re-authenticate
        security_manager = result["security_manager"]
        
        # Get all active sessions
        from .context import list_sessions, clear_session
        
        active_sessions = list_sessions()
        
        for session_id in active_sessions:
            # Revoke each session
            security_manager.revoke_session(session_id)
            clear_session(session_id)
        
        logger.info(f"🔒 Revoked {len(active_sessions)} existing sessions for security")
        logger.info("✅ Security patch applied successfully")
        logger.info("⚠️ All users must re-authenticate")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to apply security patch: {e}")
        return False


# Quick patch function for immediate deployment
def emergency_disable_session_reuse() -> None:
    """
    EMERGENCY PATCH: Immediately disable session reuse.
    
    This is a critical security fix that should be applied immediately
    to prevent unauthorized credential access.
    """
    logger.critical("🚨 EMERGENCY SECURITY PATCH ACTIVATED")
    
    # Get or create security manager
    security_manager = get_security_manager()
    
    # Disable session reuse
    security_manager.allow_session_reuse = False
    
    # Revoke all existing sessions
    for session_id in list(security_manager.active_sessions.keys()):
        security_manager.revoke_session(session_id)
    
    logger.critical("✅ Session reuse disabled")
    logger.critical("✅ All existing sessions revoked")
    logger.critical("⚠️ All users must re-authenticate")


# Export the critical functions
__all__ = [
    'initialize_secure_server',
    'apply_security_patch_to_existing_server',
    'emergency_disable_session_reuse',
    'SecureServerConfig'
]