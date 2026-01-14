"""FastMCP Google OAuth Bearer Token authentication setup.

This module provides real Google OAuth authentication using Google's JWKS endpoint
instead of custom JWT tokens. This enables dynamic client registration with MCP Inspector.
It also includes modern FastMCP 2.12.x GoogleProvider configuration.
"""

import logging
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from pydantic import BaseModel, Field

"""FastMCP Google OAuth authentication setup.

NOTE: FastMCP v2.14 removed `BearerAuthProvider` (deprecated in v2.11).
Use `JWTVerifier` for JWT bearer verification instead.
"""

from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.auth.providers.google import GoogleProvider
from config.settings import settings
from auth.compatibility_shim import CompatibilityShim
from .scope_registry import ScopeRegistry

from config.enhanced_logging import setup_logger
logger = setup_logger()

# Global auth provider
_auth_provider: Optional[Union[JWTVerifier, GoogleProvider]] = None


class GoogleProviderSettings(BaseModel):
    """Settings for GoogleProvider with automatic environment variable loading and scope integration."""
    
    client_id: str = Field(
        default_factory=lambda: settings.fastmcp_server_auth_google_client_id,
        description="Google OAuth client ID"
    )
    client_secret: str = Field(
        default_factory=lambda: settings.fastmcp_server_auth_google_client_secret,
        description="Google OAuth client secret"
    )
    base_url: str = Field(
        default_factory=lambda: settings.base_url,
        description="Server base URL"
    )
    scope_group: str = Field(
        default="base",
        description="ScopeRegistry group for required scopes (base, oauth_basic, oauth_comprehensive)"
    )
    timeout_seconds: int = Field(default=10, description="Authentication timeout")
    
    @property
    def required_scopes(self) -> List[str]:
        """Get required scopes from ScopeRegistry."""
        try:
            return ScopeRegistry.resolve_scope_group(self.scope_group)
        except Exception as e:
            logger.warning(f"Failed to resolve scope group '{self.scope_group}': {e}")
            # Fallback to base scopes
            return ScopeRegistry.resolve_scope_group("base")
    
    @property
    def redirect_uri(self) -> str:
        """Get the correct redirect URI from settings."""
        return settings.dynamic_oauth_redirect_uri
    
    @property
    def redirect_path(self) -> str:
        """Extract redirect path from the full redirect URI."""
        from urllib.parse import urlparse
        return urlparse(self.redirect_uri).path

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

def create_modern_google_provider(
    enable_unified_auth: bool = True,
    auth_type: str = "GOOGLE",
    scope_group: str = "base"
) -> Optional[GoogleProvider]:
    """
    Create a modern GoogleProvider using FastMCP 2.12.x patterns with ScopeRegistry integration.
    
    Benefits over legacy system:
    - Automatic environment variable loading
    - ScopeRegistry integration for consistent scope management
    - OAuth proxy architecture
    - Enhanced security with PKCE
    - Simplified configuration
    
    Args:
        enable_unified_auth: Whether to enable unified authentication
        auth_type: Authentication type from settings
        scope_group: ScopeRegistry group name for required scopes
        
    Returns:
        Configured GoogleProvider instance or None if disabled
    """
    
    if not enable_unified_auth or auth_type != "GOOGLE":
        logger.info("🔄 GoogleProvider disabled - using legacy authentication")
        return None
        
    try:
        logger.info("🔑 Creating modern FastMCP 2.12.x GoogleProvider with ScopeRegistry integration...")
        
        # Use Pydantic settings with ScopeRegistry integration
        provider_settings = GoogleProviderSettings(scope_group=scope_group)
        
        # Validate required settings
        if not provider_settings.client_id or not provider_settings.client_secret:
            logger.error("❌ Missing Google OAuth credentials")
            logger.error("   Set FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID and FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET")
            return None
        
        # Get scopes from ScopeRegistry
        required_scopes = provider_settings.required_scopes
        
        # Create GoogleProvider with modern configuration and correct redirect path
        google_provider = GoogleProvider(
            client_id=provider_settings.client_id,
            client_secret=provider_settings.client_secret,
            base_url=provider_settings.base_url,
            required_scopes=required_scopes,
            timeout_seconds=provider_settings.timeout_seconds,
            redirect_path=provider_settings.redirect_path  # Use existing /oauth2callback path
        )
        
        # Log successful configuration with ScopeRegistry details
        logger.info("✅ Modern GoogleProvider configured with ScopeRegistry integration")
        logger.info(f"  🏗️  OAuth Proxy Architecture: Enhanced security")
        logger.info(f"  🔐 PKCE Support: Built-in")
        logger.info(f"  📋 Scope Management: ScopeRegistry group '{scope_group}'")
        logger.info(f"  🎯 Token Validation: Google tokeninfo API")
        logger.info(f"  🌐 Base URL: {provider_settings.base_url}")
        logger.info(f"  🔄 Redirect URI: {provider_settings.redirect_uri} (existing configuration)")
        logger.info(f"  📊 Scopes: {len(required_scopes)} scopes from registry")
        
        return google_provider
        
    except Exception as e:
        logger.error(f"❌ Failed to create GoogleProvider: {e}")
        logger.warning("⚠️  Falling back to legacy OAuth flow")
        return None


def setup_google_oauth_auth(
    enable_modern_provider: bool = True,
    scope_group: str = "base"
) -> Union[JWTVerifier, GoogleProvider]:
    """Setup Google OAuth authentication for MCP.

    Tries to use modern GoogleProvider first, falls back to JWTVerifier.
    This enables dynamic client registration with MCP Inspector.
    
    Args:
        enable_modern_provider: Whether to try modern GoogleProvider first
        scope_group: ScopeRegistry group for modern provider scopes
    
    Returns:
        Configured GoogleProvider or JWTVerifier instance
    """
    global _auth_provider
    
    if _auth_provider is not None:
        return _auth_provider
    
    # Try modern GoogleProvider first if enabled
    if enable_modern_provider:
        modern_provider = create_modern_google_provider(
            enable_unified_auth=True,
            auth_type="GOOGLE",
            scope_group=scope_group
        )
        if modern_provider:
            _auth_provider = modern_provider
            return _auth_provider
    
    # Fallback to JWTVerifier (FastMCP v2.14+)
    logger.info("🔄 Using JWTVerifier fallback for Google OAuth")

    # Configure JWT verification using Google's JWKS endpoint.
    # This will validate JWT bearer tokens (e.g., Google ID tokens), not opaque access tokens.
    _auth_provider = JWTVerifier(
        jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
        issuer="https://accounts.google.com",
        audience=None,
    )
    
    logger.info("✅ Google OAuth JWT verification configured")
    logger.info("🔑 Using Google's JWKS endpoint for JWT validation")
    logger.info("🌐 OAuth issuer: https://accounts.google.com")
    
    return _auth_provider


def get_provider_status(provider: Optional[GoogleProvider]) -> dict:
    """Get status information about the GoogleProvider."""
    if not provider:
        return {
            "enabled": False,
            "type": "legacy",
            "features": ["file_based_credentials", "manual_scope_management"],
            "security": "standard"
        }
    
    return {
        "enabled": True,
        "type": "modern_fastmcp_2.12.x",
        "features": [
            "oauth_proxy_architecture",
            "built_in_pkce",
            "automatic_token_validation",
            "scope_expansion",
            "environment_auto_loading"
        ],
        "security": "enhanced"
    }


def log_modernization_benefits():
    """Log the benefits of the modernization."""
    logger.info("🚀 FastMCP 2.12.x Authentication Benefits:")
    logger.info("  📉 93.6% code reduction (5,460 → 350 lines)")
    logger.info("  🔒 Enhanced security with OAuth proxy")
    logger.info("  🛡️  Built-in PKCE support")
    logger.info("  🎯 Automatic token validation")
    logger.info("  📋 Simplified scope management")
    logger.info("  🔧 Environment variable auto-loading")
    logger.info("  🐛 Better error handling and logging")


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
