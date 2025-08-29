"""Google OAuth 2.0 authentication implementation for FastMCP2."""

import logging
import secrets
import json
import os
from typing import Optional, Tuple, Any
from pathlib import Path
from datetime import datetime

# Allow insecure transport for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import settings
from .context import store_session_data, get_session_data, get_session_context

logger = logging.getLogger(__name__)

# OAuth state to user email mapping (since callback comes outside of FastMCP session)
_oauth_state_map: dict[str, str] = {}


class GoogleAuthError(Exception):
    """Custom exception for Google authentication errors."""
    pass


def _get_credentials_path(user_email: str) -> Path:
    """Get the path to store credentials for a specific user."""
    safe_email = user_email.replace("@", "_at_").replace(".", "_")
    return Path(settings.credentials_dir) / f"{safe_email}_credentials.json"


def _save_credentials(user_email: str, credentials: Credentials) -> None:
    """Save credentials to disk."""
    creds_path = _get_credentials_path(user_email)
    
    # Ensure directory exists
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save credentials
    creds_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None
    }
    
    with open(creds_path, "w") as f:
        json.dump(creds_data, f, indent=2)
    
    logger.info(f"Saved credentials for {user_email}")


def _load_credentials(user_email: str) -> Optional[Credentials]:
    """Load credentials from disk."""
    creds_path = _get_credentials_path(user_email)
    
    if not creds_path.exists():
        logger.debug(f"No credentials file found for {user_email}")
        return None
    
    try:
        with open(creds_path, "r") as f:
            creds_data = json.load(f)
        
        # Get OAuth client configuration from settings
        oauth_config = settings.get_oauth_client_config()
        
        # Ensure we have client_id and client_secret
        client_id = creds_data.get("client_id") or oauth_config.get("client_id")
        client_secret = creds_data.get("client_secret") or oauth_config.get("client_secret")
        
        if not client_id or not client_secret:
            logger.error(f"Missing OAuth client configuration for {user_email}")
            return None
        
        credentials = Credentials(
            token=creds_data["token"],
            refresh_token=creds_data["refresh_token"],
            token_uri=creds_data.get("token_uri", oauth_config.get("token_uri", "https://oauth2.googleapis.com/token")),
            client_id=client_id,
            client_secret=client_secret,
            scopes=creds_data.get("scopes", settings.drive_scopes)
        )
        
        if creds_data.get("expiry"):
            credentials.expiry = datetime.fromisoformat(creds_data["expiry"])
        
        logger.debug(f"Loaded credentials for {user_email} with client_id: {client_id[:10]}...")
        return credentials
        
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Error loading credentials for {user_email}: {e}")
        return None


def _refresh_credentials(credentials: Credentials, user_email: str) -> Credentials:
    """Refresh expired credentials."""
    try:
        credentials.refresh(Request())
        _save_credentials(user_email, credentials)
        logger.info(f"Refreshed credentials for {user_email}")
        return credentials
    except Exception as e:
        logger.error(f"Failed to refresh credentials for {user_email}: {e}")
        raise GoogleAuthError(f"Failed to refresh credentials: {e}")


def get_valid_credentials(user_email: str) -> Optional[Credentials]:
    """Get valid credentials for a user, refreshing if necessary."""
    credentials = _load_credentials(user_email)
    
    if not credentials:
        return None
    
    # Check if credentials are expired and refresh if needed
    if credentials.expired and credentials.refresh_token:
        try:
            credentials = _refresh_credentials(credentials, user_email)
        except GoogleAuthError:
            # If refresh fails, credentials are invalid
            return None
    
    return credentials


def get_all_stored_users() -> list[str]:
    """Get a list of all users who have stored credentials.
    
    Returns:
        List of user email addresses with stored credentials
    """
    try:
        credentials_dir = Path(settings.credentials_dir)
        if not credentials_dir.exists():
            return []
        
        users = []
        for file_path in credentials_dir.glob("*_credentials.json"):
            # Convert safe filename back to email
            safe_email = file_path.stem.replace("_credentials", "")
            email = safe_email.replace("_at_", "@").replace("_", ".")
            users.append(email)
        
        logger.debug(f"Found {len(users)} stored users: {users}")
        return users
        
    except Exception as e:
        logger.error(f"Error getting stored users: {e}")
        return []


async def initiate_oauth_flow(user_email: str, service_name: str = "Google Drive") -> str:
    """
    Initiate OAuth flow for a user.
    
    Args:
        user_email: User's email address
        service_name: Service name for display purposes
    
    Returns:
        Authorization URL for the user to visit
    """
    logger.info(f"Initiating OAuth flow for {user_email}")
    
    # Get OAuth client configuration
    oauth_config = settings.get_oauth_client_config()
    
    # Create OAuth flow
    flow = Flow.from_client_config(
        {
            "web": oauth_config
        },
        scopes=settings.drive_scopes
    )
    
    flow.redirect_uri = settings.dynamic_oauth_redirect_uri
    
    # Generate state parameter
    state = secrets.token_urlsafe(32)
    
    # Store user email directly with OAuth state (callback comes outside FastMCP session)
    _oauth_state_map[state] = user_email
    
    # Generate authorization URL
    # The Flow object already has scopes configured, don't pass them again
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent"  # Force consent to ensure refresh_token is granted
    )
    
    logger.info(f"Generated OAuth URL for {user_email}")
    return auth_url


async def handle_oauth_callback(
    authorization_response: str,
    state: str
) -> Tuple[str, Credentials]:
    """
    Handle OAuth callback and exchange code for credentials.
    
    Args:
        authorization_response: Full authorization response URL
        state: OAuth state parameter
    
    Returns:
        Tuple of (user_email, credentials)
    """
    logger.info(f"Handling OAuth callback with state: {state}")
    
    # Get user email from state mapping
    user_email = _oauth_state_map.pop(state, None)
    if not user_email:
        logger.warning(f"OAuth state not found in current session: {state}")
        logger.info("This may happen if the server was restarted. Clearing all OAuth states.")
        _oauth_state_map.clear()
        raise GoogleAuthError(
            "OAuth session expired (possibly due to server restart). "
            "Please start the authentication process again by calling the start_google_auth tool."
        )
    
    # Create OAuth flow with same configuration used for authorization URL
    oauth_config = settings.get_oauth_client_config()
    
    # DIAGNOSTIC LOG: OAuth client_secret debugging - callback phase
    logger.info(f"🔍 CALLBACK_DEBUG: Creating OAuth flow for token exchange")
    logger.info(f"🔍 CALLBACK_DEBUG: - oauth_config keys: {list(oauth_config.keys())}")
    logger.info(f"🔍 CALLBACK_DEBUG: - client_id: {oauth_config.get('client_id', 'MISSING')[:20]}...")
    logger.info(f"🔍 CALLBACK_DEBUG: - client_secret: {'PRESENT' if oauth_config.get('client_secret') else 'MISSING'} (length: {len(oauth_config.get('client_secret', '')) if oauth_config.get('client_secret') else 0})")
    logger.info(f"🔍 CALLBACK_DEBUG: - token_uri: {oauth_config.get('token_uri')}")
    
    # DIAGNOSTIC LOG: OAuth scope inconsistency debugging
    logger.info(f"OAUTH_SCOPE_DEBUG: Starting OAuth flow with scopes: {settings.drive_scopes}")
    logger.info(f"OAUTH_SCOPE_DEBUG: Total scope count: {len(settings.drive_scopes)}")
    logger.info(f"OAUTH_SCOPE_DEBUG: Scopes sorted: {sorted(settings.drive_scopes)}")
    
    flow = Flow.from_client_config(
        {"web": oauth_config},
        scopes=settings.drive_scopes,
        state=state
    )
    
    flow.redirect_uri = settings.dynamic_oauth_redirect_uri
    
    # DIAGNOSTIC LOG: Verify flow has client credentials
    logger.info(f"🔍 CALLBACK_DEBUG: Flow configuration after creation:")
    logger.info(f"🔍 CALLBACK_DEBUG: - flow.client_config: {flow.client_config}")
    logger.info(f"🔍 CALLBACK_DEBUG: - flow.client_type: {getattr(flow, 'client_type', 'NOT_SET')}")
    logger.info(f"🔍 CALLBACK_DEBUG: - flow redirect_uri: {flow.redirect_uri}")
    
    # Exchange authorization code for credentials
    try:
        # DIAGNOSTIC LOG: OAuth scope inconsistency debugging - callback phase
        logger.info(f"OAUTH_SCOPE_DEBUG: Processing OAuth callback")
        logger.info(f"OAUTH_SCOPE_DEBUG: Authorization response: {authorization_response}")
        
        # Disable scope validation to handle Google adding extra scopes
        # Google sometimes adds scopes like script.external_request automatically
        import os
        old_relax = os.environ.get('OAUTHLIB_RELAX_TOKEN_SCOPE', '')
        os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
        
        try:
            flow.fetch_token(authorization_response=authorization_response)
            credentials = flow.credentials
        finally:
            # Restore original setting
            if old_relax:
                os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = old_relax
            else:
                os.environ.pop('OAUTHLIB_RELAX_TOKEN_SCOPE', None)
        
        # DIAGNOSTIC LOG: Check final granted scopes vs requested
        logger.info(f"OAUTH_SCOPE_DEBUG: OAuth callback successful")
        logger.info(f"OAUTH_SCOPE_DEBUG: Granted scopes: {getattr(credentials, 'scopes', 'Not available')}")
        logger.info(f"OAUTH_SCOPE_DEBUG: Expected scopes: {sorted(settings.drive_scopes)}")
        
        # Verify the authenticated user email matches expected
        userinfo_service = build("oauth2", "v2", credentials=credentials)
        user_info = userinfo_service.userinfo().get().execute()
        authenticated_email = user_info.get("email")
        
        if authenticated_email != user_email:
            raise GoogleAuthError(
                f"Authenticated email ({authenticated_email}) does not match expected ({user_email})"
            )
        
        # Save credentials
        _save_credentials(user_email, credentials)
        
        logger.info(f"Successfully authenticated {user_email}")
        return user_email, credentials
        
    except Exception as e:
        # DIAGNOSTIC LOG: OAuth scope inconsistency debugging - error capture
        logger.error(f"OAUTH_SCOPE_DEBUG: OAuth callback failed with error: {e}")
        logger.error(f"OAUTH_SCOPE_DEBUG: Error type: {type(e).__name__}")
        logger.error(f"OAUTH_SCOPE_DEBUG: Full error details: {str(e)}")
        
        # Check if this is the specific scope mismatch error
        if "Scope has changed" in str(e):
            logger.error(f"OAUTH_SCOPE_DEBUG: SCOPE MISMATCH DETECTED!")
            logger.error(f"OAUTH_SCOPE_DEBUG: This is the OAuth scope inconsistency error we're debugging")
        
        logger.error(f"OAuth callback failed: {e}")
        raise GoogleAuthError(f"Authentication failed: {e}")


async def get_drive_service(user_email: str):
    """
    Get an authenticated Google Drive service for a user.
    
    This function is maintained for backward compatibility.
    New code should use the service_manager.get_google_service() instead.
    
    Args:
        user_email: User's email address
    
    Returns:
        Authenticated Google Drive service
    """
    # Import here to avoid circular imports
    from .service_manager import get_google_service
    
    logger.info(f"Using legacy get_drive_service for {user_email} - consider upgrading to service_manager")
    return await get_google_service(
        user_email=user_email,
        service_type="drive",
        scopes=["drive_file", "drive_read"]
    )