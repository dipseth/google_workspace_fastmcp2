"""Google OAuth 2.0 authentication implementation for FastMCP2."""

import logging

from config.enhanced_logging import setup_logger
logger = setup_logger()
import secrets
import json
import os
from typing_extensions import Optional, Tuple, Any
from pathlib import Path
from datetime import datetime, UTC

# Allow insecure transport for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
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
    if not user_email:
        raise GoogleAuthError("Cannot get credentials path: user_email is required")
    safe_email = user_email.replace("@", "_at_").replace(".", "_")
    return Path(settings.credentials_dir) / f"{safe_email}_credentials.json"


def _save_credentials(user_email: str, credentials: Credentials) -> None:
    """Save credentials to disk with proper permissions and validation."""
    # Check if AuthMiddleware is available for encrypted storage
    try:
        from .context import get_auth_middleware
        auth_middleware = get_auth_middleware()
        if auth_middleware:
            logger.info(f"Using AuthMiddleware for credential storage (mode: {auth_middleware._storage_mode.value})")
            auth_middleware.save_credentials(user_email, credentials)
            return
    except Exception as e:
        logger.debug(f"AuthMiddleware not available, using fallback: {e}")
    
    # Fallback to plaintext storage if middleware not available
    creds_path = _get_credentials_path(user_email)
    
    # Ensure directory exists with proper permissions
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Set restrictive permissions on directory
        creds_path.parent.chmod(0o700)
    except (OSError, AttributeError) as e:
        logger.warning(f"Could not set restrictive permissions on credentials directory: {e}")
    
    # Validate credentials before saving
    if not credentials.token:
        logger.error(f"Cannot save credentials for {user_email}: Missing access token")
        raise GoogleAuthError("Invalid credentials: Missing access token")
    
    if not credentials.refresh_token:
        logger.warning(f"Saving credentials for {user_email} without refresh token - may not be able to refresh")
    
    # Save credentials
    creds_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        "saved_at": datetime.now().isoformat(),
        "user_email": user_email  # Store email for validation
    }
    
    try:
        with open(creds_path, "w") as f:
            json.dump(creds_data, f, indent=2)
        
        # Set restrictive permissions on the credential file (owner read/write only)
        try:
            creds_path.chmod(0o600)
            logger.debug(f"Set restrictive permissions (0o600) on {creds_path}")
        except (OSError, AttributeError) as e:
            logger.warning(f"Could not set restrictive permissions on credential file: {e}")
        
        logger.info(f"Successfully saved plaintext credentials for {user_email} to {creds_path}")
        
    except (IOError, OSError) as e:
        logger.error(f"Failed to save credentials for {user_email}: {e}")
        raise GoogleAuthError(f"Failed to save credentials: {e}")


def _load_credentials(user_email: str) -> Optional[Credentials]:
    """Load credentials from disk with validation and error recovery."""
    # Check if AuthMiddleware is available for encrypted storage
    try:
        from .context import get_auth_middleware
        auth_middleware = get_auth_middleware()
        if auth_middleware:
            creds = auth_middleware.load_credentials(user_email)
            if creds:
                logger.info(f"Successfully loaded credentials via AuthMiddleware for {user_email}")
                return creds
    except Exception as e:
        logger.debug(f"AuthMiddleware not available for loading, using fallback: {e}")
    
    # Fallback to plaintext storage if middleware not available or has no credentials
    creds_path = _get_credentials_path(user_email)
    
    if not creds_path.exists():
        logger.debug(f"No plaintext credentials file found for {user_email} at {creds_path}")
        return None
    
    try:
        # Check file permissions
        file_stat = creds_path.stat()
        file_mode = oct(file_stat.st_mode)[-3:]
        if file_mode != '600':
            logger.warning(f"Credential file {creds_path} has loose permissions: {file_mode} (expected 600)")
        
        with open(creds_path, "r") as f:
            creds_data = json.load(f)
        
        # Validate stored email matches requested email
        stored_email = creds_data.get("user_email")
        if stored_email and stored_email != user_email:
            logger.error(f"Credential file mismatch: requested {user_email}, but file contains {stored_email}")
            return None
        
        # Validate required fields
        required_fields = ["token", "refresh_token"]
        missing_fields = [field for field in required_fields if not creds_data.get(field)]
        if missing_fields:
            logger.error(f"Credential file for {user_email} missing required fields: {missing_fields}")
            # Try to continue without refresh_token if only that's missing
            if "token" in missing_fields:
                logger.error(f"Cannot load credentials without access token for {user_email}")
                return None
            else:
                logger.warning(f"Loading credentials without refresh_token for {user_email} - refresh may fail")
        
        # Get OAuth client configuration from settings
        oauth_config = settings.get_oauth_client_config()
        
        # Ensure we have client_id and client_secret
        client_id = creds_data.get("client_id") or oauth_config.get("client_id")
        client_secret = creds_data.get("client_secret") or oauth_config.get("client_secret")
        
        if not client_id or not client_secret:
            logger.error(f"Missing OAuth client configuration for {user_email}")
            logger.debug(f"Credential file has client_id: {bool(creds_data.get('client_id'))}, "
                        f"client_secret: {bool(creds_data.get('client_secret'))}")
            logger.debug(f"OAuth config has client_id: {bool(oauth_config.get('client_id'))}, "
                        f"client_secret: {bool(oauth_config.get('client_secret'))}")
            return None
        
        credentials = Credentials(
            token=creds_data["token"],
            refresh_token=creds_data.get("refresh_token"),  # Make refresh_token optional
            token_uri=creds_data.get("token_uri", oauth_config.get("token_uri", "https://oauth2.googleapis.com/token")),
            client_id=client_id,
            client_secret=client_secret,
            scopes=creds_data.get("scopes", settings.drive_scopes)
        )
        
        if creds_data.get("expiry"):
            try:
                credentials.expiry = datetime.fromisoformat(creds_data["expiry"])
                logger.debug(f"Credential expiry for {user_email}: {credentials.expiry}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid expiry format in credentials for {user_email}: {e}")
                # Continue without expiry - will be treated as expired
        
        # Log credential age if saved_at is available
        if creds_data.get("saved_at"):
            try:
                saved_at = datetime.fromisoformat(creds_data["saved_at"])
                age = datetime.now() - saved_at
                logger.debug(f"Credentials for {user_email} are {age.days} days old")
            except (ValueError, TypeError):
                pass
        
        logger.info(f"Successfully loaded credentials for {user_email}")
        return credentials
        
    except json.JSONDecodeError as e:
        logger.error(f"Corrupt credential file for {user_email}: Invalid JSON - {e}")
        # Optionally backup the corrupt file
        try:
            backup_path = creds_path.with_suffix('.json.corrupt')
            creds_path.rename(backup_path)
            logger.info(f"Backed up corrupt credential file to {backup_path}")
        except Exception as backup_error:
            logger.error(f"Failed to backup corrupt file: {backup_error}")
        return None
        
    except (KeyError, ValueError) as e:
        logger.error(f"Invalid credential file structure for {user_email}: {e}")
        return None
        
    except (IOError, OSError) as e:
        logger.error(f"Failed to read credential file for {user_email}: {e}")
        return None
        
    except Exception as e:
        logger.error(f"Unexpected error loading credentials for {user_email}: {e}")
        return None


def _refresh_credentials(credentials: Credentials, user_email: str) -> Credentials:
    """Refresh expired credentials with enhanced error handling."""
    if not credentials.refresh_token:
        logger.error(f"Cannot refresh credentials for {user_email}: No refresh token available")
        raise GoogleAuthError(
            f"Authentication required: No refresh token available for {user_email}. "
            f"Please re-authenticate using the start_google_auth tool."
        )
    
    logger.info(f"Attempting to refresh credentials for {user_email}")
    
    try:
        # Log token details for debugging
        logger.debug(f"Token refresh attempt for {user_email}:")
        logger.debug(f"  - Has refresh_token: {bool(credentials.refresh_token)}")
        logger.debug(f"  - Token URI: {credentials.token_uri}")
        logger.debug(f"  - Client ID: {credentials.client_id[:10] if credentials.client_id else 'None'}...")
        logger.debug(f"  - Expiry: {credentials.expiry}")
        
        credentials.refresh(Request())
        
        # Verify refresh was successful
        if not credentials.token:
            raise GoogleAuthError("Token refresh succeeded but no new access token received")
        
        # Save the refreshed credentials
        _save_credentials(user_email, credentials)
        
        logger.info(f"Successfully refreshed credentials for {user_email}")
        logger.debug(f"New token expiry: {credentials.expiry}")
        
        return credentials
        
    except RefreshError as e:
        error_str = str(e)
        logger.error(f"Token refresh failed for {user_email}: {error_str}")
        
        if 'invalid_grant' in error_str.lower():
            raise GoogleAuthError(
                f"Refresh token is invalid or expired for {user_email}. "
                f"Please re-authenticate using the start_google_auth tool."
            )
        elif 'invalid_client' in error_str.lower():
            raise GoogleAuthError(
                f"OAuth client configuration is invalid. "
                f"Please check your GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET settings."
            )
        else:
            raise GoogleAuthError(f"Failed to refresh credentials: {e}")
            
    except Exception as e:
        logger.error(f"Unexpected error refreshing credentials for {user_email}: {e}")
        raise GoogleAuthError(f"Failed to refresh credentials: {e}")


def get_valid_credentials(user_email: str) -> Optional[Credentials]:
    """Get valid credentials for a user, refreshing if necessary."""
    if not user_email:
        raise GoogleAuthError("Cannot get credentials: user_email is required")
        
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
    if not user_email:
        raise GoogleAuthError("Cannot initiate OAuth flow: user_email is required")
        
    logger.info(f"Initiating OAuth flow for {user_email}")
    
    # Get OAuth client configuration
    oauth_config = settings.get_oauth_client_config()
    
    # Use centralized scope registry as single source of truth
    from .scope_registry import ScopeRegistry
    oauth_scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
    logger.info(f"Using oauth_comprehensive scopes: {len(oauth_scopes)} scopes")
    
    # Verify no problematic scopes are included
    problematic_patterns = ['photoslibrary.sharing', 'cloud-platform', 'cloudfunctions', 'pubsub', 'iam']
    problematic_scopes = [scope for scope in oauth_scopes if any(bad in scope for bad in problematic_patterns)]
    
    if problematic_scopes:
        logger.error(f"Found {len(problematic_scopes)} problematic scopes in oauth_comprehensive")
        for scope in problematic_scopes:
            logger.error(f"Problematic scope: {scope}")
    else:
        logger.info("✅ No problematic scopes found in oauth_comprehensive")
    
    # Create OAuth flow
    flow = Flow.from_client_config(
        {
            "web": oauth_config
        },
        scopes=oauth_scopes  # Use centralized scopes instead of settings.drive_scopes
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
    
    # Use centralized scope registry as single source of truth (same as initiate_oauth_flow)
    from .scope_registry import ScopeRegistry
    oauth_scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
    
    # DIAGNOSTIC LOG: OAuth client_secret debugging - callback phase
    logger.info(f"🔍 CALLBACK_DEBUG: Creating OAuth flow for token exchange")
    logger.info(f"🔍 CALLBACK_DEBUG: - oauth_config keys: {list(oauth_config.keys())}")
    logger.info(f"🔍 CALLBACK_DEBUG: - client_id: {oauth_config.get('client_id', 'MISSING')[:20]}...")
    logger.info(f"🔍 CALLBACK_DEBUG: - client_secret: {'PRESENT' if oauth_config.get('client_secret') else 'MISSING'} (length: {len(oauth_config.get('client_secret', '')) if oauth_config.get('client_secret') else 0})")
    logger.info(f"🔍 CALLBACK_DEBUG: - token_uri: {oauth_config.get('token_uri')}")
    
    # DIAGNOSTIC LOG: OAuth scope consistency debugging
    logger.info(f"OAUTH_SCOPE_DEBUG: Starting OAuth callback with oauth_comprehensive scopes: {len(oauth_scopes)} total")

    flow = Flow.from_client_config(
        {"web": oauth_config},
        scopes=oauth_scopes,  # Use centralized scopes instead of settings.drive_scopes
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
        logger.info(f"OAUTH_SCOPE_DEBUG: Expected scopes: {sorted(oauth_scopes)}")  # Use centralized scopes
        
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
    if not user_email:
        raise GoogleAuthError("Cannot get drive service: user_email is required")
        
    # Import here to avoid circular imports
    from .service_manager import get_google_service
    
    logger.info(f"Using legacy get_drive_service for {user_email} - consider upgrading to service_manager")
    return await get_google_service(
        user_email=user_email,
        service_type="drive",
        scopes=["drive_file", "drive_read"]
    )