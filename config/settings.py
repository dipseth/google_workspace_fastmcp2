"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing_extensions import Optional, List,Literal
import os
from pathlib import Path
import logging

from config.enhanced_logging import setup_logger
logger = setup_logger()
from urllib.parse import urlparse

# Lazy import for compatibility shim to avoid circular imports
_COMPATIBILITY_AVAILABLE = None  # Will be checked lazily


class Settings(BaseSettings):
    """Application configuration using Pydantic Settings"""
    
    # OAuth Configuration (either use JSON file OR individual credentials)
    google_client_secrets_file: str = ""  # Path to client_secret.json file
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uri: str = "http://localhost:8002/oauth2callback"
    
    # Server Configuration
    server_port: int = 8002
    server_host: str = "localhost"
    server_name: str = "Google Drive Upload Server"
    
    # HTTPS/SSL Configuration
    # Default to False for Docker compatibility - explicitly enable via .env when needed
    enable_https: bool = False
    ssl_cert_file: str = ""  # Path to SSL certificate (e.g., "./localhost+2.pem")
    ssl_key_file: str = ""  # Path to SSL private key (e.g., "./localhost+2-key.pem")
    ssl_ca_file: str = ""  # Optional CA file for client certificate verification
    
    # Storage Configuration
    credentials_dir: str = str(Path(__file__).parent.parent / "credentials")
    credential_storage_mode: str = "FILE_ENCRYPTED"
    chat_service_account_file: str = ""
    
    @property
    def is_cloud_deployment(self) -> bool:
        """Detect if running in FastMCP Cloud."""
        return os.getenv("FASTMCP_CLOUD", "false").lower() in ("true", "1", "yes", "on")
    
    # Qdrant Configuration
    qdrant_url: str = "http://localhost:6333"
    qdrant_key: str = "NONE"
    qdrant_host: Optional[str] = None  # Will be set from qdrant_url
    qdrant_port: Optional[int] = None  # Will be set from qdrant_url
    qdrant_api_key: Optional[str] = None  # Will be set from qdrant_key
    
    # Logging
    log_level: str = "INFO"
    
    # Security
    session_timeout_minutes: int = 60
    
    # Gmail Allow List Configuration
    gmail_allow_list: str = ""  # Comma-separated list of email addresses
    
    # Gmail Elicitation Configuration (for MCP client compatibility)
    gmail_enable_elicitation: bool = True  # Enable elicitation for untrusted recipients
    gmail_elicitation_fallback: str = "block"  # What to do if elicitation fails: "block", "allow", "draft"
    
    # Qdrant Tool Response Collection Cache Configuration
    mcp_tool_responses_collection_cache_days: int = 5  # Default to 14 days retention
    
    # Sampling Tools Configuration
    sampling_tools: bool = False  # Enable sampling middleware tools (default: False)
    
    # Phase 1 OAuth Migration Feature Flags
    enable_unified_auth: bool = True
    legacy_compat_mode: bool = True
    credential_migration: bool = True
    service_caching: bool = True
    enhanced_logging: bool = True
    
    # Security Configuration
    auth_security_level: str = Field(
        default="standard",
        env="AUTH_SECURITY_LEVEL",
        description="Authentication security level: 'standard', 'high', or 'custom'"
    )
    
    # Template Configuration
    jinja_template_strict_mode: bool = Field(
        default=True,
        env="JINJA_TEMPLATE_STRICT_MODE",
        description="When enabled, template processing errors will cause tool execution to fail instead of just logging the error"
    )
    
    # FastMCP 2.12.0 GoogleProvider Configuration
    fastmcp_server_auth: str = ""
    fastmcp_server_auth_google_client_id: str = ""
    fastmcp_server_auth_google_client_secret: str = ""
    fastmcp_server_auth_google_base_url: str = ""
    
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
        "https://www.googleapis.com/auth/calendar",
        # Google Photos Library API scopes
        "https://www.googleapis.com/auth/photoslibrary.readonly",
        "https://www.googleapis.com/auth/photoslibrary.appendonly",
        "https://www.googleapis.com/auth/photoslibrary",
        "https://www.googleapis.com/auth/photoslibrary.sharing",
        "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
        "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
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
        
        This property uses the centralized scope registry as the single source of truth,
        ensuring consistency across the application and avoiding problematic scopes.
        
        Returns:
            List of OAuth scope URLs from oauth_comprehensive group
        """
        try:
            # Use the scope registry directly as single source of truth
            from auth.scope_registry import ScopeRegistry
            scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
            logging.debug(f"SCOPE_DEBUG: Retrieved {len(scopes)} scopes from oauth_comprehensive group")
            
            # Verify no problematic scopes are included
            problematic_patterns = ['photoslibrary.sharing', 'cloud-platform', 'cloudfunctions', 'pubsub', 'iam']
            problematic_scopes = [scope for scope in scopes if any(bad in scope for bad in problematic_patterns)]
            
            if problematic_scopes:
                logging.error(f"SCOPE_DEBUG: Found {len(problematic_scopes)} problematic scopes in oauth_comprehensive")
                for scope in problematic_scopes:
                    logging.error(f"SCOPE_DEBUG: Problematic scope: {scope}")
            else:
                logging.debug("SCOPE_DEBUG: No problematic scopes found - using clean oauth_comprehensive group")
            
            # Check if Gmail settings scopes are included
            gmail_settings_basic = "https://www.googleapis.com/auth/gmail.settings.basic"
            gmail_settings_sharing = "https://www.googleapis.com/auth/gmail.settings.sharing"
            has_settings_basic = gmail_settings_basic in scopes
            has_settings_sharing = gmail_settings_sharing in scopes
            logging.debug(f"SCOPE_DEBUG: Gmail settings.basic included: {has_settings_basic}")
            logging.debug(f"SCOPE_DEBUG: Gmail settings.sharing included: {has_settings_sharing}")
            
            return scopes
            
        except Exception as e:
            logging.error(f"SCOPE_DEBUG: Error getting scopes from registry, using minimal fallback: {e}")
            # Use a minimal fallback that excludes problematic scopes
            minimal_scopes = [
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
                "openid",
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/documents",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/presentations"
            ]
            logging.warning(f"SCOPE_DEBUG: Using minimal fallback with {len(minimal_scopes)} scopes")
            return minimal_scopes
            return self._fallback_drive_scopes
    
    model_config = SettingsConfigDict(
        env_file= str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields like TEST_EMAIL_ADDRESS
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # DEBUG: Log environment variable loading
        import os
        env_qdrant_url = os.getenv("QDRANT_URL")
        env_qdrant_key = os.getenv("QDRANT_KEY")
        logging.debug(f"🔧 SETTINGS DEBUG - Environment variables: QDRANT_URL='{env_qdrant_url}', QDRANT_KEY={'***' if env_qdrant_key else 'None'}")
        logging.debug(f"🔧 SETTINGS DEBUG - Settings fields: qdrant_url='{self.qdrant_url}', qdrant_key={'***' if self.qdrant_key and self.qdrant_key != 'NONE' else 'None'}")
        
        # DEBUG: Log FastMCP GoogleProvider environment variable loading
        env_fastmcp_auth = os.getenv("FASTMCP_SERVER_AUTH")
        env_fastmcp_client_id = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID")
        env_fastmcp_client_secret = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET")
        env_fastmcp_base_url = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL")
        logging.debug(f"🔧 FASTMCP DEBUG - Environment variables:")
        logging.debug(f"🔧   FASTMCP_SERVER_AUTH='{env_fastmcp_auth}'")
        logging.debug(f"🔧   FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID={'***' if env_fastmcp_client_id else 'None'}")
        logging.debug(f"🔧   FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET={'***' if env_fastmcp_client_secret else 'None'}")
        logging.debug(f"🔧   FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL='{env_fastmcp_base_url}'")
        logging.debug(f"🔧 FASTMCP DEBUG - Settings fields:")
        logging.debug(f"🔧   fastmcp_server_auth='{self.fastmcp_server_auth}'")
        logging.debug(f"🔧   fastmcp_server_auth_google_client_id={'***' if self.fastmcp_server_auth_google_client_id else 'None'}")
        logging.debug(f"🔧   fastmcp_server_auth_google_client_secret={'***' if self.fastmcp_server_auth_google_client_secret else 'None'}")
        logging.debug(f"🔧   fastmcp_server_auth_google_base_url='{self.fastmcp_server_auth_google_base_url}'")
        
        # Cloud-aware configuration
        if self.is_cloud_deployment:
            # Use cloud-optimized settings
            self.credentials_dir = os.getenv("CREDENTIALS_DIR", "/tmp/credentials")
            if not self.credential_storage_mode or self.credential_storage_mode == "FILE_ENCRYPTED":
                self.credential_storage_mode = os.getenv("CREDENTIAL_STORAGE_MODE", "MEMORY_WITH_BACKUP")
            logging.debug(f"☁️ Cloud deployment detected - using credentials_dir='{self.credentials_dir}', storage_mode='{self.credential_storage_mode}'")
        else:
            # Use environment variable override if provided, otherwise keep current value
            self.credentials_dir = os.getenv("CREDENTIALS_DIR", self.credentials_dir)
            self.credential_storage_mode = os.getenv("CREDENTIAL_STORAGE_MODE", self.credential_storage_mode)
        
        # Ensure credentials directory exists
        Path(self.credentials_dir).mkdir(parents=True, exist_ok=True)
        
        # Parse Qdrant URL to get host and port
        parsed_url = urlparse(self.qdrant_url)
        self.qdrant_host = parsed_url.hostname or "localhost"
        self.qdrant_port = parsed_url.port or 6333
        # If QDRANT_KEY is "NONE" or empty, treat as no authentication
        self.qdrant_api_key = None if self.qdrant_key in ["NONE", "", None] else self.qdrant_key
        
        # DEBUG: Log final parsed values
        logging.debug(f"🔧 SETTINGS DEBUG - Parsed values: host='{self.qdrant_host}', port={self.qdrant_port}, api_key={'***' if self.qdrant_api_key else 'None'}")
    
    def get_gmail_allow_list(self) -> List[str]:
        """
        Parse and return the Gmail allow list from the configuration.
        
        Returns:
            List[str]: List of email addresses in the allow list.
                       Returns empty list if not configured or empty.
        """
        if not self.gmail_allow_list or self.gmail_allow_list.strip() == "":
            return []
        
        # Parse comma-separated list, strip whitespace, filter empty strings
        emails = [
            email.strip().lower()
            for email in self.gmail_allow_list.split(",")
            if email.strip()
        ]
        
        # Log the parsed allow list for debugging (without exposing full emails)
        if emails:
            masked_emails = [
                f"{email[:3]}...{email[-10:]}" if len(email) > 13 else email
                for email in emails
            ]
            logging.debug(f"Gmail allow list contains {len(emails)} email(s): {masked_emails}")
        
        return emails

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
        # For OAuth flows, always use localhost if OAUTH_REDIRECT_URI points to localhost
        # This is needed because FastMCP Cloud only hosts the MCP endpoint, not OAuth endpoints
        env_oauth_uri = os.getenv("OAUTH_REDIRECT_URI", self.oauth_redirect_uri)
        if env_oauth_uri and "localhost" in env_oauth_uri:
            # In cloud deployment, use HTTPS for client-facing URLs even if enable_https=false
            # (CloudFlare handles HTTPS, but clients need HTTPS URLs)
            protocol = "https" if self.is_cloud_deployment else self.protocol
            # Extract port from OAuth redirect URI for consistency
            if ":8002" in env_oauth_uri:
                return f"{protocol}://localhost:8002"
            elif ":8000" in env_oauth_uri:
                return f"{protocol}://localhost:8000"
            else:
                return f"{protocol}://localhost:{self.server_port}"
        
        # Check if we have an explicit BASE_URL environment variable for cloud MCP endpoint
        explicit_base_url = os.getenv("BASE_URL")
        if explicit_base_url:
            return explicit_base_url
        
        # In cloud deployment, use HTTPS for client-facing URLs even if enable_https=false
        protocol = "https" if self.is_cloud_deployment else self.protocol
        return f"{protocol}://{self.server_host}:{self.server_port}"
    
    @property
    def dynamic_oauth_redirect_uri(self) -> str:
        """Get the OAuth redirect URI that dynamically switches between HTTP and HTTPS."""
        # Always use explicit OAUTH_REDIRECT_URI if it's been set via environment variable
        env_oauth_uri = os.getenv("OAUTH_REDIRECT_URI")
        if env_oauth_uri:
            # CRITICAL FIX: Automatically adjust protocol to match server configuration
            if self.enable_https and env_oauth_uri.startswith("http://localhost"):
                # Convert HTTP to HTTPS for localhost when HTTPS is enabled
                https_uri = env_oauth_uri.replace("http://localhost", "https://localhost")
                logging.debug(f"🔧 PROTOCOL FIX: Converted OAuth redirect URI from HTTP to HTTPS: {env_oauth_uri} → {https_uri}")
                return https_uri
            elif not self.enable_https and env_oauth_uri.startswith("https://localhost"):
                # Convert HTTPS to HTTP for localhost when HTTPS is disabled
                http_uri = env_oauth_uri.replace("https://localhost", "http://localhost")
                logging.debug(f"🔧 PROTOCOL FIX: Converted OAuth redirect URI from HTTPS to HTTP: {env_oauth_uri} → {http_uri}")
                return http_uri
            else:
                # Use as-is for non-localhost or already correct protocol
                return env_oauth_uri
        # Otherwise, use the configured value or construct from base_url
        if self.oauth_redirect_uri:
            return self.oauth_redirect_uri
        return f"{self.base_url}/oauth2callback"
    
    def get_uvicorn_ssl_config(self) -> Optional[dict]:
        """Get uvicorn SSL configuration for FastMCP if HTTPS is enabled."""
        if self.is_cloud_deployment:
            # FastMCP Cloud handles SSL automatically
            logging.debug("☁️ Cloud deployment detected - SSL handled by FastMCP Cloud")
            return None
        
        if not self.enable_https:
            return None
        
        # Return uvicorn-compatible SSL configuration for local deployment
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