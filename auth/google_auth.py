"""Google OAuth 2.0 authentication implementation for FastMCP2."""

import logging

from config.enhanced_logging import setup_logger
logger = setup_logger()
import secrets
import json
import os
from typing_extensions import Optional, Tuple, Any, Dict, List, Literal
from pathlib import Path
from datetime import datetime, UTC, timedelta

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
from .pkce_utils import generate_pkce_pair, pkce_manager

logger = logging.getLogger(__name__)

# OAuth state to user email mapping (since callback comes outside of FastMCP session)
_oauth_state_map: dict[str, dict[str, Any]] = {}

# Service selection cache for OAuth flows
_service_selection_cache: Dict[str, Dict[str, Any]] = {}


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


async def initiate_oauth_flow(
    user_email: str,
    service_name: str = "Google Drive",
    selected_services: Optional[List[str]] = None,
    show_service_selection: bool = True,
    use_pkce: bool = True,
    auth_method: Literal['file_credentials', 'pkce_file', 'pkce_memory'] = 'pkce_file',
    custom_client_id: Optional[str] = None,
    custom_client_secret: Optional[str] = None
) -> str:
    """
    Initiate OAuth flow for a user with optional service selection and PKCE support.
    
    Args:
        user_email: User's email address
        service_name: Service name for display purposes
        selected_services: Optional pre-selected services
        show_service_selection: Whether to show service selection page
        use_pkce: Whether to use PKCE (Proof Key for Code Exchange) for enhanced security
    
    Returns:
        Authorization URL or service selection URL
    """
    if not user_email:
        raise GoogleAuthError("Cannot initiate OAuth flow: user_email is required")
        
    logger.info(f"Initiating OAuth flow for {user_email} (auth_method: {auth_method}, PKCE: {'enabled' if use_pkce else 'disabled'})")
    
    # If no services selected and service selection is enabled, return selection URL
    if show_service_selection and not selected_services:
        return await _create_service_selection_url(user_email, "custom", use_pkce=use_pkce)
    
    # Use selected services or default to comprehensive
    if selected_services:
        from .scope_registry import ScopeRegistry
        oauth_scopes = ScopeRegistry.get_scopes_for_services(selected_services)
        logger.info(f"Using selected services: {selected_services}")
    else:
        from .scope_registry import ScopeRegistry
        oauth_scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
        logger.info(f"Using oauth_comprehensive scopes: {len(oauth_scopes)} scopes")
    
    # Get OAuth client configuration
    oauth_config = settings.get_oauth_client_config()
    if custom_client_id:
        oauth_config['client_id'] = custom_client_id
        if custom_client_secret:
            oauth_config['client_secret'] = custom_client_secret
    
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
    
    # Store user email and additional info with OAuth state
    _oauth_state_map[state] = {
        'user_email': user_email,
        'auth_method': auth_method,
        'custom_client_id': custom_client_id,
        'custom_client_secret': custom_client_secret
    }
    
    # Generate PKCE parameters if enabled
    pkce_params = {}
    if use_pkce:
        pkce_data = pkce_manager.create_pkce_session(state)
        pkce_params.update(pkce_data)
        logger.info(f"🔐 Generated PKCE parameters for state: {state}")
    
    # Generate authorization URL
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",  # Force consent to ensure refresh_token is granted
        **pkce_params  # Add PKCE parameters if enabled
    )
    
    logger.info(f"Generated OAuth URL for {user_email} (auth_method: {auth_method})")
    return auth_url


async def _create_service_selection_url(user_email: str, flow_type: str, use_pkce: bool = True) -> str:
    """Create URL for service selection page with PKCE support."""
    state = secrets.token_urlsafe(32)
    
    # Store flow information
    _service_selection_cache[state] = {
        "user_email": user_email,
        "flow_type": flow_type,
        "use_pkce": use_pkce,
        "timestamp": datetime.now().isoformat()
    }
    
    # Clean up old entries
    _cleanup_service_selection_cache()
    
    # Use base_url directly since our endpoint is /auth/services/select
    base_url = settings.base_url
    pkce_param = "&use_pkce=true" if use_pkce else "&use_pkce=false"
    return f"{base_url}/auth/services/select?state={state}&flow_type={flow_type}{pkce_param}"


def _cleanup_service_selection_cache():
    """Clean up expired cache entries."""
    cutoff = datetime.now() - timedelta(minutes=30)
    expired_keys = [
        key for key, value in _service_selection_cache.items()
        if datetime.fromisoformat(value["timestamp"]) < cutoff
    ]
    for key in expired_keys:
        _service_selection_cache.pop(key, None)


async def handle_service_selection_callback(
    state: str,
    selected_services: List[str],
    use_pkce: Optional[bool] = None,
    auth_method: Optional[Literal['file_credentials', 'pkce_file', 'pkce_memory']] = None,
    custom_client_id: Optional[str] = None,
    custom_client_secret: Optional[str] = None
) -> str:
    """Handle service selection and return OAuth URL with PKCE and custom credentials support."""
    flow_info = _service_selection_cache.pop(state, None)
    if not flow_info:
        raise GoogleAuthError("Invalid or expired service selection state")
    
    user_email = flow_info["user_email"]
    
    # Use explicit use_pkce parameter if provided, otherwise fall back to cached value
    if use_pkce is not None:
        final_use_pkce = use_pkce
        logger.info(f"🔐 Using explicit PKCE setting from form: {final_use_pkce}")
    else:
        final_use_pkce = flow_info.get("use_pkce", True)  # Default to PKCE enabled
        logger.info(f"🔐 Using cached PKCE setting: {final_use_pkce}")
    
    # Determine auth method: explicit parameter > PKCE setting > default
    if auth_method is not None:
        final_auth_method = auth_method
        logger.info(f"🔑 Using explicit auth_method from form: {final_auth_method}")
    elif final_use_pkce:
        final_auth_method = 'pkce_file'  # Default PKCE method
        logger.info(f"🔑 Using default PKCE auth_method: {final_auth_method}")
    else:
        final_auth_method = 'file_credentials'  # Legacy method
        logger.info(f"🔑 Using legacy auth_method: {final_auth_method}")
    
    logger.info(f"🎯 Service selection callback for {user_email} (PKCE: {'enabled' if final_use_pkce else 'disabled'}, auth_method: {final_auth_method})")
    logger.info(f"📋 Selected services: {selected_services}")
    
    if custom_client_id:
        logger.info(f"🔑 Using custom client credentials: {custom_client_id[:10]}...")
    
    # Now call the regular OAuth flow with selected services and custom credentials
    return await initiate_oauth_flow(
        user_email=user_email,
        selected_services=selected_services,
        show_service_selection=False,  # Don't show selection again
        use_pkce=final_use_pkce,  # Pass PKCE setting through
        auth_method=final_auth_method,  # Pass auth method through
        custom_client_id=custom_client_id,  # Pass custom client credentials
        custom_client_secret=custom_client_secret
    )


async def handle_oauth_callback(
    authorization_response: str,
    state: str,
    code_verifier: Optional[str] = None
) -> Tuple[str, Credentials]:
    """
    Handle OAuth callback and exchange code for credentials with PKCE support.
    
    Args:
        authorization_response: Full authorization response URL
        state: OAuth state parameter
        code_verifier: PKCE code verifier (if PKCE was used)
    
    Returns:
        Tuple of (user_email, credentials)
    """
    logger.info(f"Handling OAuth callback with state: {state} (PKCE: {'enabled' if code_verifier else 'disabled'})")
    
    # Get state info - if not found, use defaults for resilience
    state_info = _oauth_state_map.pop(state, None)
    if not state_info:
        logger.warning(f"OAuth state not found in current session: {state}")
        logger.info("This may happen if the server was restarted. Using fallback configuration.")
        
        # Extract email from authorization response as fallback
        from urllib.parse import urlparse, parse_qs
        try:
            parsed_url = urlparse(authorization_response)
            query_params = parse_qs(parsed_url.query)
            
            # Look for email hint in the OAuth callback (some flows include this)
            email_hint = None
            
            # Fallback: Use a default configuration for resilient OAuth handling
            state_info = {
                'user_email': email_hint or 'unknown@gmail.com',  # Will be corrected from userinfo
                'auth_method': 'pkce_file',  # Default to PKCE file storage
                'custom_client_id': None,
                'custom_client_secret': None
            }
            logger.info(f"🔄 Using fallback state info for resilient OAuth: {state_info}")
            
        except Exception as fallback_error:
            logger.error(f"❌ Could not create fallback state info: {fallback_error}")
            raise GoogleAuthError(
                "OAuth session expired (possibly due to server restart). "
                "Please start the authentication process again by calling the start_google_auth tool."
            )
    
    user_email = state_info['user_email']
    auth_method = state_info['auth_method']
    custom_client_id = state_info.get('custom_client_id')
    custom_client_secret = state_info.get('custom_client_secret')
    
    # Validate PKCE if code_verifier is provided
    if code_verifier:
        try:
            # The PKCE manager validates the session and returns the code verifier
            stored_verifier = pkce_manager.get_code_verifier(state)
            if stored_verifier != code_verifier:
                logger.error(f"🔐 PKCE verification failed for state: {state}")
                raise GoogleAuthError("PKCE verification failed")
            logger.info(f"🔐 PKCE verification successful for state: {state}")
        except KeyError:
            logger.error(f"🔐 PKCE session not found for state: {state}")
            raise GoogleAuthError("PKCE session not found or expired")
    
    # Create OAuth flow with same configuration used for authorization URL
    oauth_config = settings.get_oauth_client_config()
    if custom_client_id:
        oauth_config['client_id'] = custom_client_id
        if custom_client_secret:
            oauth_config['client_secret'] = custom_client_secret
    
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
            # Add PKCE code verifier if provided - pass it directly to fetch_token
            token_kwargs = {}
            if code_verifier:
                token_kwargs['code_verifier'] = code_verifier
                logger.info(f"🔐 Added PKCE code verifier to token exchange")
            
            flow.fetch_token(authorization_response=authorization_response, **token_kwargs)
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
        
        # Verify the authenticated user email - use actual email from Google
        userinfo_service = build("oauth2", "v2", credentials=credentials)
        user_info = userinfo_service.userinfo().get().execute()
        authenticated_email = user_info.get("email")
        
        # If we used fallback user_email, update it with the actual authenticated email
        if user_email == 'unknown@gmail.com' or not user_email:
            user_email = authenticated_email
            logger.info(f"✅ Updated user_email from fallback to actual: {authenticated_email}")
        elif authenticated_email != user_email:
            logger.warning(f"⚠️ Email mismatch: expected {user_email}, got {authenticated_email} - using actual email")
            user_email = authenticated_email  # Use the actual authenticated email
        
        # Conditional storage based on auth_method
        if auth_method == 'pkce_memory':
            # Store in session memory only
            session_id = get_session_context()
            if session_id:
                store_session_data(session_id, "credentials", credentials.to_json())
                logger.info(f"Stored credentials in session memory for {user_email}")
            else:
                logger.warning(f"No session context available - falling back to file storage for {user_email}")
                _save_credentials(user_email, credentials)
        else:
            # File storage for 'file_credentials' and 'pkce_file'
            _save_credentials(user_email, credentials)
        
        logger.info(f"Successfully authenticated {user_email} (auth_method: {auth_method})")
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