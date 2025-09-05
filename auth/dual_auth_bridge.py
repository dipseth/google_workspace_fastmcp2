"""
Dual Authentication Bridge for FastMCP2.

This module bridges the gap between:
1. Main Flow: Memory-based auth via GoogleProvider (JWT tokens kept in memory)
2. Secondary Flow: File-based auth via initiate_oauth_flow (for secondary accounts)

The bridge ensures both flows work seamlessly together and credentials can be
shared between authentication methods when needed.
"""

import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import json
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config.settings import settings
from .context import (
    get_user_email_context,
    set_user_email_context,
    store_session_data,
    get_session_data
)

logger = logging.getLogger(__name__)


class DualAuthBridge:
    """
    Bridges memory-based (GoogleProvider) and file-based OAuth authentication.
    
    This class ensures that:
    - Primary accounts authenticated via GoogleProvider can work with legacy tools
    - Secondary accounts authenticated via file-based OAuth can work alongside primary
    - Credentials can be bridged between flows when needed
    - Both flows coexist without conflicts
    """
    
    def __init__(self):
        """Initialize the dual auth bridge."""
        self._memory_credentials: Dict[str, Credentials] = {}
        self._primary_account: Optional[str] = None
        self._secondary_accounts: set[str] = set()
        logger.info("🌉 DualAuthBridge initialized")
    
    def set_primary_account(self, user_email: str, credentials: Optional[Credentials] = None) -> None:
        """
        Set the primary account (authenticated via GoogleProvider).
        
        Args:
            user_email: Primary account email
            credentials: Optional credentials from GoogleProvider
        """
        self._primary_account = user_email
        if credentials:
            self._memory_credentials[user_email] = credentials
        logger.info(f"✅ Set primary account: {user_email}")
    
    def add_secondary_account(self, user_email: str) -> None:
        """
        Register a secondary account (authenticated via file-based OAuth).
        
        Args:
            user_email: Secondary account email
        """
        self._secondary_accounts.add(user_email)
        logger.info(f"➕ Added secondary account: {user_email}")
    
    def is_primary_account(self, user_email: str) -> bool:
        """Check if an email is the primary account."""
        return self._primary_account == user_email
    
    def is_secondary_account(self, user_email: str) -> bool:
        """Check if an email is a secondary account."""
        return user_email in self._secondary_accounts
    
    def get_active_account(self) -> Optional[str]:
        """
        Get the currently active account.
        
        Priority:
        1. User email from context
        2. Primary account
        3. Most recent secondary account
        
        Returns:
            Active account email or None
        """
        # Check context first
        context_email = get_user_email_context()
        if context_email:
            logger.debug(f"Active account from context: {context_email}")
            return context_email
        
        # Fallback to primary account
        if self._primary_account:
            logger.debug(f"Active account is primary: {self._primary_account}")
            return self._primary_account
        
        # Fallback to most recent secondary
        if self._secondary_accounts:
            # In a real implementation, track access time
            recent = list(self._secondary_accounts)[0]
            logger.debug(f"Active account is secondary: {recent}")
            return recent
        
        return None
    
    def bridge_credentials(
        self,
        user_email: str,
        source: str = "memory"
    ) -> Optional[Credentials]:
        """
        Bridge credentials between memory and file storage.
        
        Args:
            user_email: User email to bridge credentials for
            source: Source of credentials ("memory" or "file")
        
        Returns:
            Bridged credentials or None
        """
        try:
            if source == "memory":
                # Bridge from memory to file
                if user_email in self._memory_credentials:
                    credentials = self._memory_credentials[user_email]
                    logger.info(f"🔄 Bridging credentials from memory to file for {user_email}")
                    
                    # Save to file using existing mechanism
                    from .google_auth import _save_credentials
                    _save_credentials(user_email, credentials)
                    
                    return credentials
            
            elif source == "file":
                # Bridge from file to memory
                from .google_auth import get_valid_credentials
                credentials = get_valid_credentials(user_email)
                
                if credentials:
                    logger.info(f"🔄 Bridging credentials from file to memory for {user_email}")
                    self._memory_credentials[user_email] = credentials
                    return credentials
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to bridge credentials for {user_email}: {e}")
            return None
    
    def validate_dual_flow(self) -> Dict[str, Any]:
        """
        Validate the dual authentication flow configuration.
        
        Returns:
            Validation results with status and recommendations
        """
        results = {
            "status": "healthy",
            "primary_flow": {
                "enabled": settings.enable_unified_auth,
                "provider_configured": bool(settings.fastmcp_server_auth == "GOOGLE"),
                "primary_account": self._primary_account
            },
            "secondary_flow": {
                "enabled": True,
                "oauth_configured": settings.is_oauth_configured(),
                "secondary_accounts": list(self._secondary_accounts)
            },
            "bridging": {
                "enabled": settings.credential_migration,
                "memory_credentials": list(self._memory_credentials.keys())
            },
            "recommendations": []
        }
        
        # Check primary flow
        if not results["primary_flow"]["enabled"]:
            results["recommendations"].append(
                "Enable unified auth (ENABLE_UNIFIED_AUTH=true) for GoogleProvider support"
            )
        
        if not results["primary_flow"]["provider_configured"]:
            results["recommendations"].append(
                "Configure GoogleProvider (FASTMCP_SERVER_AUTH=GOOGLE) for JWT-based auth"
            )
        
        # Check secondary flow
        if not results["secondary_flow"]["oauth_configured"]:
            results["recommendations"].append(
                "Configure OAuth credentials for file-based secondary account auth"
            )
            results["status"] = "partial"
        
        # Check bridging
        if not results["bridging"]["enabled"]:
            results["recommendations"].append(
                "Enable credential migration (CREDENTIAL_MIGRATION=true) for seamless bridging"
            )
        
        # Overall status
        if results["recommendations"]:
            results["status"] = "needs_configuration" if len(results["recommendations"]) > 2 else "partial"
        
        return results
    
    def get_credentials_for_tool(
        self,
        user_email: Optional[str] = None,
        prefer_source: str = "auto"
    ) -> Tuple[Optional[str], Optional[Credentials]]:
        """
        Get credentials for a tool, handling both auth flows.
        
        Args:
            user_email: Optional specific user email
            prefer_source: Preferred source ("memory", "file", "auto")
        
        Returns:
            Tuple of (user_email, credentials) or (None, None)
        """
        # Determine which user to authenticate
        target_email = user_email or self.get_active_account()
        
        if not target_email:
            logger.warning("No active account found")
            return None, None
        
        # Try to get credentials based on preference
        credentials = None
        
        if prefer_source == "auto":
            # Auto-detect based on account type
            if self.is_primary_account(target_email):
                prefer_source = "memory"
            elif self.is_secondary_account(target_email):
                prefer_source = "file"
            else:
                # Unknown account, try both
                credentials = self._try_both_sources(target_email)
        
        if not credentials:
            if prefer_source == "memory":
                credentials = self._memory_credentials.get(target_email)
                if not credentials:
                    # Try bridging from file
                    credentials = self.bridge_credentials(target_email, "file")
            
            elif prefer_source == "file":
                from .google_auth import get_valid_credentials
                credentials = get_valid_credentials(target_email)
                if not credentials:
                    # Try bridging from memory
                    credentials = self.bridge_credentials(target_email, "memory")
        
        if credentials:
            logger.info(f"✅ Got credentials for {target_email} from {prefer_source}")
            return target_email, credentials
        
        logger.warning(f"❌ No credentials found for {target_email}")
        return None, None
    
    def _try_both_sources(self, user_email: str) -> Optional[Credentials]:
        """Try to get credentials from both sources."""
        # Try memory first (faster)
        credentials = self._memory_credentials.get(user_email)
        if credentials:
            logger.debug(f"Found credentials in memory for {user_email}")
            return credentials
        
        # Try file storage
        from .google_auth import get_valid_credentials
        credentials = get_valid_credentials(user_email)
        if credentials:
            logger.debug(f"Found credentials in file for {user_email}")
            # Cache in memory for faster access
            self._memory_credentials[user_email] = credentials
            return credentials
        
        return None
    
    def switch_account(self, user_email: str) -> bool:
        """
        Switch the active account.
        
        Args:
            user_email: Email to switch to
        
        Returns:
            True if switch was successful
        """
        # Check if account exists
        if not (self.is_primary_account(user_email) or self.is_secondary_account(user_email)):
            # Try to load from file
            from .google_auth import get_valid_credentials
            if not get_valid_credentials(user_email):
                logger.error(f"Cannot switch to {user_email} - no credentials found")
                return False
            
            # Register as secondary account
            self.add_secondary_account(user_email)
        
        # Set in context
        set_user_email_context(user_email)
        logger.info(f"🔄 Switched active account to: {user_email}")
        return True
    
    def get_all_accounts(self) -> Dict[str, str]:
        """
        Get all available accounts with their types.
        
        Returns:
            Dict mapping email to account type
        """
        accounts = {}
        
        if self._primary_account:
            accounts[self._primary_account] = "primary"
        
        for email in self._secondary_accounts:
            accounts[email] = "secondary"
        
        # Also check for file-based accounts not yet registered
        from .google_auth import get_all_stored_users
        for email in get_all_stored_users():
            if email not in accounts:
                accounts[email] = "file-based"
        
        return accounts


# Global bridge instance
_dual_auth_bridge: Optional[DualAuthBridge] = None


def get_dual_auth_bridge() -> DualAuthBridge:
    """Get or create the global dual auth bridge instance."""
    global _dual_auth_bridge
    if _dual_auth_bridge is None:
        _dual_auth_bridge = DualAuthBridge()
    return _dual_auth_bridge


def validate_dual_auth_setup() -> Dict[str, Any]:
    """
    Validate the complete dual authentication setup.
    
    Returns:
        Detailed validation results
    """
    bridge = get_dual_auth_bridge()
    results = bridge.validate_dual_flow()
    
    # Add middleware validation
    from .context import get_auth_middleware
    middleware = get_auth_middleware()
    
    if middleware:
        results["middleware"] = {
            "configured": True,
            "unified_auth_enabled": middleware.is_unified_auth_enabled(),
            "service_injection_enabled": middleware.is_service_injection_enabled(),
            "storage_mode": middleware.get_storage_mode().value
        }
    else:
        results["middleware"] = {
            "configured": False,
            "error": "AuthMiddleware not initialized"
        }
        results["status"] = "error"
        results["recommendations"].append(
            "Initialize AuthMiddleware in server.py"
        )
    
    return results