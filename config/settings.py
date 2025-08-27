"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os
from pathlib import Path
import logging

# Lazy import for compatibility shim to avoid circular imports
_COMPATIBILITY_AVAILABLE = None  # Will be checked lazily


class Settings(BaseSettings):
    """Application configuration using Pydantic Settings"""
    
    # OAuth Configuration (either use JSON file OR individual credentials)
    google_client_secrets_file: str = ""  # Path to client_secret.json file
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uri: str = "http://localhost:8000/oauth2callback"
    
    # Server Configuration
    server_port: int = 8000
    server_host: str = "localhost"
    server_name: str = "Google Drive Upload Server"
    
    # HTTPS/SSL Configuration
    enable_https: bool = False
    ssl_cert_file: str = "cert.pem"
    ssl_key_file: str = "key.pem"
    ssl_ca_file: str = ""  # Optional CA file for client certificate verification
    
    # Storage Configuration
    credentials_dir: str = "./credentials"
    credential_storage_mode: str = "FILE_PLAINTEXT"
    chat_service_account_file: str = ""
    
    # Logging
    log_level: str = "INFO"
    
    # Security
    session_timeout_minutes: int = 60
    
    # Legacy OAuth scopes - maintained for backward compatibility
    # These are now managed through the centralized scope registry
    _fallback_drive_scopes: list[str] = [
        # Base OAuth scopes for user identification
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
        # Google Drive scopes
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
        # Google Docs scopes
        "https://www.googleapis.com/auth/documents.readonly",
        "https://www.googleapis.com/auth/documents",
        # Gmail API scopes
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.labels",
        # Gmail Settings scopes (CRITICAL for filters/forwarding)
        "https://www.googleapis.com/auth/gmail.settings.basic",
        "https://www.googleapis.com/auth/gmail.settings.sharing",
        # Google Chat API scopes
        "https://www.googleapis.com/auth/chat.messages.readonly",
        "https://www.googleapis.com/auth/chat.messages",
        "https://www.googleapis.com/auth/chat.spaces",
        # Google Sheets API scopes
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/spreadsheets",
        # Google Forms API scopes
        "https://www.googleapis.com/auth/forms.body",
        "https://www.googleapis.com/auth/forms.body.readonly",
        "https://www.googleapis.com/auth/forms.responses.readonly",
        # Google Slides API scopes
        "https://www.googleapis.com/auth/presentations",
        "https://www.googleapis.com/auth/presentations.readonly",
        # Calendar scopes
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
        # Cloud Platform scopes (for broader Google services)
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/cloudfunctions",
        "https://www.googleapis.com/auth/pubsub",
        "https://www.googleapis.com/auth/iam",
    ]
    
    @property
    def drive_scopes(self) -> list[str]:
        """
        Get OAuth scopes for Google services.
        
        This property now uses the centralized scope registry through the
        compatibility shim, ensuring consistency across the application.
        Falls back to the original hardcoded scopes if the registry is unavailable.
        
        Returns:
            List of OAuth scope URLs
        """
        global _COMPATIBILITY_AVAILABLE
        
        # Lazy import to avoid circular dependency issues
        if _COMPATIBILITY_AVAILABLE is None:
            try:
                from ..auth.compatibility_shim import CompatibilityShim
                _COMPATIBILITY_AVAILABLE = True
                logging.info("SCOPE_DEBUG: Successfully imported compatibility shim")
            except ImportError as e:
                _COMPATIBILITY_AVAILABLE = False
                logging.warning(f"SCOPE_DEBUG: Compatibility shim not available, using fallback scopes: {e}")
        
        if _COMPATIBILITY_AVAILABLE:
            try:
                from ..auth.compatibility_shim import CompatibilityShim
                scopes = CompatibilityShim.get_legacy_drive_scopes()
                logging.info(f"SCOPE_DEBUG: Retrieved {len(scopes)} scopes from compatibility shim")
                # Check if Gmail settings scopes are included
                gmail_settings_basic = "https://www.googleapis.com/auth/gmail.settings.basic"
                gmail_settings_sharing = "https://www.googleapis.com/auth/gmail.settings.sharing"
                has_settings_basic = gmail_settings_basic in scopes
                has_settings_sharing = gmail_settings_sharing in scopes
                logging.info(f"SCOPE_DEBUG: Gmail settings.basic included: {has_settings_basic}")
                logging.info(f"SCOPE_DEBUG: Gmail settings.sharing included: {has_settings_sharing}")
                return scopes
            except Exception as e:
                logging.error(f"SCOPE_DEBUG: Error getting scopes from registry, using fallback: {e}")
                return self._fallback_drive_scopes
        else:
            logging.info("SCOPE_DEBUG: Using fallback drive scopes (compatibility shim unavailable)")
            # Check if fallback includes Gmail settings scopes
            gmail_settings_basic = "https://www.googleapis.com/auth/gmail.settings.basic"
            gmail_settings_sharing = "https://www.googleapis.com/auth/gmail.settings.sharing"
            has_settings_basic = gmail_settings_basic in self._fallback_drive_scopes
            has_settings_sharing = gmail_settings_sharing in self._fallback_drive_scopes
            logging.warning(f"SCOPE_DEBUG: Fallback Gmail settings.basic included: {has_settings_basic}")
            logging.warning(f"SCOPE_DEBUG: Fallback Gmail settings.sharing included: {has_settings_sharing}")
            return self._fallback_drive_scopes
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields like TEST_EMAIL_ADDRESS
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure credentials directory exists
        Path(self.credentials_dir).mkdir(parents=True, exist_ok=True)

    def is_oauth_configured(self) -> bool:
        """Check if OAuth credentials are properly configured."""
        # Check if JSON file is provided and exists
        if self.google_client_secrets_file:
            return Path(self.google_client_secrets_file).exists()
        
        # Fallback to individual credentials
        return bool(self.google_client_id and self.google_client_secret)

    def validate_oauth_config(self) -> None:
        """Validate that OAuth configuration is complete."""
        if not self.is_oauth_configured():
            if self.google_client_secrets_file:
                raise ValueError(
                    f"OAuth client secrets file not found: {self.google_client_secrets_file}. "
                    "Please check the path to your Google OAuth JSON file."
                )
            else:
                raise ValueError(
                    "OAuth configuration is incomplete. Please either:\n"
                    "1. Set GOOGLE_CLIENT_SECRETS_FILE environment variable to point to your OAuth JSON file, OR\n"
                    "2. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables"
                )

    def get_oauth_client_config(self) -> dict:
        """Get OAuth client configuration from JSON file or environment variables."""
        if self.google_client_secrets_file:
            secrets_path = Path(self.google_client_secrets_file)
            if not secrets_path.exists():
                # Log the full path for debugging
                logging.error(f"OAuth client secrets file not found at: {secrets_path.absolute()}")
                raise FileNotFoundError(f"OAuth client secrets file not found: {self.google_client_secrets_file}")
            
            import json
            try:
                with open(secrets_path, 'r') as f:
                    config = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in OAuth client secrets file: {e}")
            except Exception as e:
                raise ValueError(f"Error reading OAuth client secrets file: {e}")
            
            # Extract from Google OAuth JSON format
            if 'web' in config:
                web_config = config['web']
                return {
                    'client_id': web_config.get('client_id'),
                    'client_secret': web_config.get('client_secret'),
                    'auth_uri': web_config.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
                    'token_uri': web_config.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'redirect_uris': web_config.get('redirect_uris', [self.dynamic_oauth_redirect_uri])
                }
            elif 'installed' in config:
                installed_config = config['installed']
                return {
                    'client_id': installed_config.get('client_id'),
                    'client_secret': installed_config.get('client_secret'),
                    'auth_uri': installed_config.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
                    'token_uri': installed_config.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'redirect_uris': installed_config.get('redirect_uris', [self.dynamic_oauth_redirect_uri])
                }
            else:
                raise ValueError("OAuth client secrets JSON must contain either 'web' or 'installed' configuration")
        
        # Fallback to environment variables
        if not self.google_client_id or not self.google_client_secret:
            raise ValueError("OAuth configuration incomplete: Please set either GOOGLE_CLIENT_SECRETS_FILE or both GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
        
        return {
            'client_id': self.google_client_id,
            'client_secret': self.google_client_secret,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': [self.dynamic_oauth_redirect_uri]
        }

    def get_credentials_path(self, user_email: str) -> Path:
        """Get the path to store credentials for a specific user."""
        creds_dir = Path(self.credentials_dir)
        creds_dir.mkdir(exist_ok=True)
        return creds_dir / f"{user_email}_credentials.json"
    
    @property
    def protocol(self) -> str:
        """Get the protocol (http or https) based on SSL configuration."""
        return "https" if self.enable_https else "http"
    
    @property
    def base_url(self) -> str:
        """Get the base URL for the server."""
        return f"{self.protocol}://{self.server_host}:{self.server_port}"
    
    @property
    def dynamic_oauth_redirect_uri(self) -> str:
        """Get the OAuth redirect URI that dynamically switches between HTTP and HTTPS."""
        return f"{self.base_url}/oauth2callback"
    
    def get_uvicorn_ssl_config(self) -> Optional[dict]:
        """Get uvicorn SSL configuration for FastMCP if HTTPS is enabled."""
        if not self.enable_https:
            return None
        
        # Return uvicorn-compatible SSL configuration
        uvicorn_config = {
            "ssl_keyfile": self.ssl_key_file,
            "ssl_certfile": self.ssl_cert_file,
        }
        
        if self.ssl_ca_file:
            uvicorn_config["ssl_ca_certs"] = self.ssl_ca_file
        
        return uvicorn_config
    
    def validate_ssl_config(self) -> None:
        """Validate that SSL certificate files exist if HTTPS is enabled."""
        if not self.enable_https:
            return
        
        cert_path = Path(self.ssl_cert_file)
        key_path = Path(self.ssl_key_file)
        
        if not cert_path.exists():
            raise ValueError(f"SSL certificate file not found: {self.ssl_cert_file}")
        
        if not key_path.exists():
            raise ValueError(f"SSL private key file not found: {self.ssl_key_file}")
        
        if self.ssl_ca_file:
            ca_path = Path(self.ssl_ca_file)
            if not ca_path.exists():
                raise ValueError(f"SSL CA file not found: {self.ssl_ca_file}")


# Global settings instance
settings = Settings()