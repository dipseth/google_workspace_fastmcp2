"""FastMCP Google OAuth Bearer Token authentication setup.

This module provides real Google OAuth authentication using Google's JWKS endpoint
instead of custom JWT tokens. This enables dynamic client registration with MCP Inspector.
"""

import logging
from typing_extensions import Optional, Dict, Any
from pathlib import Path

from fastmcp.server.auth import BearerAuthProvider
from config.settings import settings
from auth.compatibility_shim import CompatibilityShim

from config.enhanced_logging import setup_logger
logger = setup_logger()

# Global auth provider
_auth_provider: Optional[BearerAuthProvider] = None

def _get_oauth_metadata_scopes() -> list[str]:
    """Get OAuth metadata scopes using compatibility shim."""
    try:
        shim = CompatibilityShim()
        return shim.get_legacy_oauth_endpoint_scopes()
    except Exception as e:
        logger.warning(f"Failed to get OAuth scopes from compatibility shim: {e}")
        # Fallback to hardcoded scopes
        return [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/chat.messages.readonly"
        ]

def setup_google_oauth_auth() -> BearerAuthProvider:
    """Setup Google OAuth authentication for MCP.
    
    Uses Google's real OAuth endpoints and JWKS for token validation.
    This enables dynamic client registration with MCP Inspector.
    
    Returns:
        Configured BearerAuthProvider instance using Google OAuth
    """
    global _auth_provider
    
    if _auth_provider is not None:
        return _auth_provider
    
    # Configure the auth provider with Google's real OAuth endpoints
    _auth_provider = BearerAuthProvider(
        # Use Google's JWKS endpoint for token validation
        jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
        # Use Google's real issuer
        issuer="https://accounts.google.com",
        # Our server audience
        audience=None,  # Google OAuth tokens don't always have specific audience
        required_scopes=["openid", "email"]  # Basic Google OAuth scopes
    )
    
    logger.info("✅ Google OAuth Bearer Token authentication configured")
    logger.info("🔑 Using Google's JWKS endpoint for token validation")
    logger.info("🌐 OAuth issuer: https://accounts.google.com")
    
    return _auth_provider


def get_google_oauth_metadata() -> Dict[str, Any]:
    """Get Google OAuth metadata for dynamic client registration.
    
    Returns:
        OAuth metadata compatible with MCP Inspector
    """
    oauth_config = settings.get_oauth_client_config()
    
    return {
        "issuer": "https://accounts.google.com",
        "authorization_endpoint": oauth_config.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
        "token_endpoint": oauth_config.get("token_uri", "https://oauth2.googleapis.com/token"),
        "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
        # Point to our local Dynamic Client Registration endpoint
        "registration_endpoint": f"{settings.base_url}/oauth/register",
        "scopes_supported": _get_oauth_metadata_scopes()
    }


# For backward compatibility during transition
def generate_user_token(
    user_email: str,
    scopes: Optional[list[str]] = None,
    expires_in_seconds: int = 3600
) -> str:
    """DEPRECATED: This function is deprecated.
    
    Use real Google OAuth tokens instead of custom JWT tokens.
    This function is kept for backward compatibility during transition.
    """
    logger.warning(
        "⚠️ generate_user_token() is deprecated. "
        "Use real Google OAuth tokens instead of custom JWT tokens."
    )
    
    # Return a placeholder - real tokens should come from Google OAuth flow
    return f"google_oauth_token_for_{user_email}"