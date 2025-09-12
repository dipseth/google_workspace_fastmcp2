"""
Pydantic models for Google authentication configuration.

This module defines structured data models for authentication parameters
that provide validation, documentation, and type safety.
"""

from pydantic import BaseModel, Field
from typing_extensions import Optional
from auth.service_types import GoogleServiceName, AuthenticationMethod

class GoogleAuthConfig(BaseModel):
    """Configuration for Google OAuth authentication flow."""
    
    user_google_email: str = Field(
        default="",
        description="Target Google email address for authentication"
    )
    
    service_name: str | list[GoogleServiceName] = Field(
        default="drive",
        description="Service name(s) for authentication. Can be a single display name like 'Google Services' or a list of specific services like ['drive', 'gmail', 'calendar']. Choose any combination from scope registry services."
    )
    
    auto_open_browser: bool = Field(
        default=True,
        description="Automatically open browser for authentication (default: True)"
    )
    
    use_pkce: bool = Field(
        default=True,
        description="Use PKCE (Proof Key for Code Exchange) for enhanced security (default: True)"
    )
    
    show_service_selection: bool = Field(
        default=True,
        description="Show service selection interface before authentication (default: True)"
    )

class ServiceAuthRequest(BaseModel):
    """Simplified authentication request for specific services."""
    
    services: list[GoogleServiceName] = Field(
        default=["drive"],
        description="List of Google services to authenticate for",
        min_length=1,
        max_length=10
    )
    
    auth_method: AuthenticationMethod = Field(
        default="pkce",
        description="Authentication method: 'pkce' for enhanced security or 'credentials' for persistent storage"
    )
    
    user_email: Optional[str] = Field(
        default=None,
        description="Optional user email (will use context if not provided)"
    )