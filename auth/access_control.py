"""Access control for MCP server with Tailscale Funnel support.

This module enforces email-based access control to ensure only authorized
users can authenticate and use the MCP server, even when exposed via Tailscale Funnel.
"""

import logging
import os
from typing import Optional, List, Set
from pathlib import Path

from config.enhanced_logging import setup_logger
logger = setup_logger()

from config.settings import settings


class AccessControl:
    """Email-based access control for MCP authentication."""
    
    def __init__(self, 
                 allowlist_file: Optional[str] = None,
                 require_existing_credentials: bool = True):
        """
        Initialize access control.
        
        Args:
            allowlist_file: Path to file containing allowed emails (one per line)
            require_existing_credentials: Require users to have stored credentials
        """
        self.allowlist_file = allowlist_file
        self.require_existing_credentials = require_existing_credentials
        self._allowed_emails: Set[str] = set()
        self._load_allowlist()
    
    def _load_allowlist(self):
        """Load allowed emails from file."""
        if not self.allowlist_file:
            logger.debug("No allowlist file configured - using existing credentials only")
            return
        
        allowlist_path = Path(self.allowlist_file)
        if not allowlist_path.exists():
            logger.warning(f"Allowlist file not found: {self.allowlist_file}")
            return
        
        try:
            with open(allowlist_path, 'r') as f:
                for line in f:
                    email = line.strip().lower()
                    if email and not email.startswith('#'):
                        self._allowed_emails.add(email)
            
            logger.info(f"✅ Loaded {len(self._allowed_emails)} emails from allowlist")
        except Exception as e:
            logger.error(f"Failed to load allowlist: {e}")
    
    def is_email_allowed(self, email: str) -> bool:
        """
        Check if an email is allowed to access the MCP server.
        
        Args:
            email: Email address to check
        
        Returns:
            True if email is allowed, False otherwise
        """
        if not email:
            logger.warning("Email validation failed: No email provided")
            return False
        
        email_lower = email.lower()
        
        # Check 1: Explicit allowlist (if configured)
        if self._allowed_emails and email_lower in self._allowed_emails:
            logger.info(f"✅ Email allowed (in allowlist): {email}")
            return True
        
        # Check 2: Existing credentials (if required)
        if self.require_existing_credentials:
            if self._has_existing_credentials(email_lower):
                logger.info(f"✅ Email allowed (has credentials): {email}")
                return True
            else:
                logger.warning(f"❌ Email denied (no credentials): {email}")
                return False
        
        # Check 3: If allowlist is configured but email not in it
        if self._allowed_emails:
            logger.warning(f"❌ Email denied (not in allowlist): {email}")
            return False
        
        # Default: Allow if no restrictions configured
        logger.warning(f"⚠️ No access restrictions configured - allowing {email}")
        return True
    
    def _has_existing_credentials(self, email: str) -> bool:
        """
        Check if user has existing stored credentials OR was previously authenticated.
        
        This prevents the catch-22 where deleting credentials to update scopes
        blocks re-authentication. If we find evidence of previous authentication
        (in .oauth_authentication.json), we allow re-auth.
        """
        try:
            from auth.google_auth import get_all_stored_users
            import json
            from pathlib import Path
            
            # Check 1: Current stored credentials
            stored_users = [u.lower() for u in get_all_stored_users()]
            if email.lower() in stored_users:
                return True
            
            # Check 2: Previous authentication evidence in .oauth_authentication.json
            # This allows re-authentication even after credentials are deleted
            oauth_data_path = Path(settings.credentials_dir) / ".oauth_authentication.json"
            if oauth_data_path.exists():
                try:
                    with open(oauth_data_path, "r") as f:
                        oauth_data = json.load(f)
                    previous_email = oauth_data.get("authenticated_email", "").lower()
                    if previous_email == email.lower():
                        logger.info(f"✅ Allowing re-authentication for previously authenticated user: {email}")
                        return True
                except Exception as e:
                    logger.debug(f"Could not read previous auth data: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check stored credentials: {e}")
            return False
    
    def add_allowed_email(self, email: str) -> bool:
        """
        Add an email to the allowlist.
        
        Args:
            email: Email to add
        
        Returns:
            True if added successfully
        """
        email_lower = email.lower()
        self._allowed_emails.add(email_lower)
        logger.info(f"➕ Added to allowlist: {email}")
        
        # Persist to file if configured
        if self.allowlist_file:
            return self._save_allowlist()
        return True
    
    def remove_allowed_email(self, email: str) -> bool:
        """
        Remove an email from the allowlist.
        
        Args:
            email: Email to remove
        
        Returns:
            True if removed successfully
        """
        email_lower = email.lower()
        if email_lower in self._allowed_emails:
            self._allowed_emails.remove(email_lower)
            logger.info(f"➖ Removed from allowlist: {email}")
            
            # Persist to file if configured
            if self.allowlist_file:
                return self._save_allowlist()
            return True
        return False
    
    def _save_allowlist(self) -> bool:
        """Save allowlist to file."""
        if not self.allowlist_file:
            return False
        
        try:
            allowlist_path = Path(self.allowlist_file)
            allowlist_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(allowlist_path, 'w') as f:
                f.write("# MCP Server Email Allowlist\n")
                f.write("# One email per line, lines starting with # are ignored\n\n")
                for email in sorted(self._allowed_emails):
                    f.write(f"{email}\n")
            
            logger.info(f"💾 Saved allowlist to {self.allowlist_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save allowlist: {e}")
            return False
    
    def get_allowed_emails(self) -> List[str]:
        """Get list of allowed emails."""
        return sorted(list(self._allowed_emails))
    
    def get_stats(self) -> dict:
        """Get access control statistics."""
        from auth.google_auth import get_all_stored_users
        
        return {
            "allowlist_configured": bool(self._allowed_emails),
            "allowlist_count": len(self._allowed_emails),
            "require_existing_credentials": self.require_existing_credentials,
            "stored_credentials_count": len(get_all_stored_users()),
            "mode": "strict" if (self._allowed_emails or self.require_existing_credentials) else "open"
        }


# Global access control instance
_access_control: Optional[AccessControl] = None


def get_access_control() -> AccessControl:
    """Get or create the global access control instance."""
    global _access_control
    if _access_control is None:
        # Check for allowlist configuration
        allowlist_file = os.getenv("MCP_EMAIL_ALLOWLIST_FILE", "")
        require_creds = os.getenv("MCP_REQUIRE_EXISTING_CREDENTIALS", "true").lower() == "true"
        
        _access_control = AccessControl(
            allowlist_file=allowlist_file if allowlist_file else None,
            require_existing_credentials=require_creds
        )
        
        logger.info("🔒 Access control initialized:")
        logger.info(f"  Allowlist file: {allowlist_file or 'Not configured'}")
        logger.info(f"  Require existing credentials: {require_creds}")
    
    return _access_control


def validate_user_access(email: str) -> bool:
    """
    Validate that a user is allowed to access the MCP server.
    
    This is the main entry point for access validation that should be
    called during OAuth callback and token exchange.
    
    Args:
        email: User's email address
    
    Returns:
        True if access is allowed, False otherwise
    """
    access_control = get_access_control()
    return access_control.is_email_allowed(email)