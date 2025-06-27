"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application configuration using Pydantic Settings"""
    
    # OAuth Configuration (either use JSON file OR individual credentials)
    google_client_secrets_file: str = ""  # Path to client_secret.json file
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uri: str = "http://localhost:8000/oauth/callback"
    
    # Server Configuration
    server_port: int = 8000
    server_host: str = "localhost"
    server_name: str = "Google Drive Upload Server"
    
    # Storage Configuration
    credentials_dir: str = "./credentials"
    credential_storage_mode: str = "FILE_PLAINTEXT"
    
    # Logging
    log_level: str = "INFO"
    
    # Security
    session_timeout_minutes: int = 60
    
    # Google Drive API scopes
    drive_scopes: list[str] = [
        # Base OAuth scopes for user identification
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
        # Google Drive scopes
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
        if self.google_client_secrets_file and Path(self.google_client_secrets_file).exists():
            import json
            with open(self.google_client_secrets_file, 'r') as f:
                config = json.load(f)
            
            # Extract from Google OAuth JSON format
            if 'web' in config:
                web_config = config['web']
                return {
                    'client_id': web_config['client_id'],
                    'client_secret': web_config['client_secret'],
                    'auth_uri': web_config['auth_uri'],
                    'token_uri': web_config['token_uri'],
                    'redirect_uris': web_config.get('redirect_uris', [self.oauth_redirect_uri])
                }
            elif 'installed' in config:
                installed_config = config['installed']
                return {
                    'client_id': installed_config['client_id'],
                    'client_secret': installed_config['client_secret'],
                    'auth_uri': installed_config['auth_uri'],
                    'token_uri': installed_config['token_uri'],
                    'redirect_uris': installed_config.get('redirect_uris', [self.oauth_redirect_uri])
                }
        
        # Fallback to environment variables
        return {
            'client_id': self.google_client_id,
            'client_secret': self.google_client_secret,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': [self.oauth_redirect_uri]
        }

    def get_credentials_path(self, user_email: str) -> Path:
        """Get the path to store credentials for a specific user."""
        creds_dir = Path(self.credentials_dir)
        creds_dir.mkdir(exist_ok=True)
        return creds_dir / f"{user_email}_credentials.json"


# Global settings instance
settings = Settings()