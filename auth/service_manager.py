"""Generic Google service management for FastMCP2."""

import logging
from typing_extensions import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_auth import get_valid_credentials, GoogleAuthError
from .context import get_session_context, store_session_data, get_session_data

# Import compatibility shim for OAuth scope management
try:
    from .compatibility_shim import CompatibilityShim
    _COMPATIBILITY_AVAILABLE = True
except ImportError:
    # Fallback for development/testing
    _COMPATIBILITY_AVAILABLE = False
    logging.warning("Compatibility shim not available, using fallback scopes")

logger = logging.getLogger(__name__)

# Service configuration mapping - defines how to build each Google service
SERVICE_CONFIGS = {
    "drive": {"service": "drive", "version": "v3"},
    "gmail": {"service": "gmail", "version": "v1"},
    "calendar": {"service": "calendar", "version": "v3"},
    "docs": {"service": "docs", "version": "v1"},
    "sheets": {"service": "sheets", "version": "v4"},
    "chat": {"service": "chat", "version": "v1"},
    "forms": {"service": "forms", "version": "v1"},
    "slides": {"service": "slides", "version": "v1"},
    "photos": {"service": "photoslibrary", "version": "v1"},
    "oauth2": {"service": "oauth2", "version": "v2"},  # For user info
    "admin": {"service": "admin", "version": "directory_v1"},
    "classroom": {"service": "classroom", "version": "v1"},
    "people": {"service": "people", "version": "v1"},
    "youtube": {"service": "youtube", "version": "v3"},
    "tasks": {"service": "tasks", "version": "v1"},
    "script": {"service": "script", "version": "v1"}, # Google Apps Script
    "vault": {"service": "vault", "version": "v1"}, # Google Vault
    "groupssettings": {"service": "groupssettings", "version": "v1"}, # Google Groups Settings
    "siteVerification": {"service": "siteVerification", "version": "v1"}, # Google Site Verification
    "tagmanager": {"service": "tagmanager", "version": "v2"}, # Google Tag Manager
    "webmasters": {"service": "webmasters", "version": "v3"}, # Google Search Console
    "analytics": {"service": "analytics", "version": "v3"}, # Google Analytics
    "adsense": {"service": "adsense", "version": "v2"}, # Google AdSense
    "books": {"service": "books", "version": "v1"}, # Google Books
    "blogger": {"service": "blogger", "version": "v3"}, # Blogger
    "driveactivity": {"service": "driveactivity", "version": "v2"}, # Drive Activity API
    "fitness": {"service": "fitness", "version": "v1"}, # Google Fit
    "photoslibrary": {"service": "photoslibrary", "version": "v1"}, # Google Photos Library
    "plus": {"service": "plus", "version": "v1"}, # Google+ (deprecated)
    "sheets_v4": {"service": "sheets", "version": "v4"}, # Google Sheets (explicit v4)
    "drive_v3": {"service": "drive", "version": "v3"}, # Google Drive (explicit v3)
    "gmail_v1": {"service": "gmail", "version": "v1"}, # Gmail (explicit v1)
    "calendar_v3": {"service": "calendar", "version": "v3"}, # Calendar (explicit v3)
    "docs_v1": {"service": "docs", "version": "v1"}, # Docs (explicit v1)
    "forms_v1": {"service": "forms", "version": "v1"}, # Forms (explicit v1)
    "slides_v1": {"service": "slides", "version": "v1"} # Slides (explicit v1)
}

# Legacy scope group definitions - now managed through centralized registry
# Maintained for backward compatibility through compatibility shim
_FALLBACK_SCOPE_GROUPS = {
    # Base scopes
    "userinfo": "https://www.googleapis.com/auth/userinfo.email",
    "openid": "openid",
    
    # Drive scopes
    "drive_read": "https://www.googleapis.com/auth/drive.readonly",
    "drive_file": "https://www.googleapis.com/auth/drive.file",
    # "drive_full": "https://www.googleapis.com/auth/drive",
    "drive_appdata": "https://www.googleapis.com/auth/drive.appdata",
    "drive_metadata": "https://www.googleapis.com/auth/drive.metadata",
    "drive_metadata_readonly": "https://www.googleapis.com/auth/drive.metadata.readonly",
    "drive_photos_readonly": "https://www.googleapis.com/auth/drive.photos.readonly",
    "drive_scripts": "https://www.googleapis.com/auth/drive.scripts",
    
    # Gmail scopes
    "gmail_read": "https://www.googleapis.com/auth/gmail.readonly",
    "gmail_send": "https://www.googleapis.com/auth/gmail.send",
    "gmail_compose": "https://www.googleapis.com/auth/gmail.compose",
    "gmail_modify": "https://www.googleapis.com/auth/gmail.modify",
    "gmail_labels": "https://www.googleapis.com/auth/gmail.labels",
    "gmail_full": "https://mail.google.com/",
    "gmail_insert": "https://www.googleapis.com/auth/gmail.insert",
    "gmail_metadata": "https://www.googleapis.com/auth/gmail.metadata",
    "gmail_settings_basic": "https://www.googleapis.com/auth/gmail.settings.basic",
    "gmail_settings_sharing": "https://www.googleapis.com/auth/gmail.settings.sharing",
    
    # Docs scopes
    "docs_read": "https://www.googleapis.com/auth/documents.readonly",
    "docs_write": "https://www.googleapis.com/auth/documents",
    
    # Calendar scopes
    "calendar_read": "https://www.googleapis.com/auth/calendar.readonly",
    "calendar_events": "https://www.googleapis.com/auth/calendar.events",
    "calendar_full": "https://www.googleapis.com/auth/calendar",
    "calendar_settings_read": "https://www.googleapis.com/auth/calendar.settings.readonly",
    
    # Sheets scopes
    "sheets_read": "https://www.googleapis.com/auth/spreadsheets.readonly",
    "sheets_write": "https://www.googleapis.com/auth/spreadsheets",
    "sheets_full": "https://www.googleapis.com/auth/spreadsheets",
    
    # Chat scopes
    "chat_read": "https://www.googleapis.com/auth/chat.messages.readonly",
    "chat_write": "https://www.googleapis.com/auth/chat.messages",
    "chat_spaces": "https://www.googleapis.com/auth/chat.spaces",
    "chat_memberships_readonly": "https://www.googleapis.com/auth/chat.memberships.readonly",
    "chat_memberships": "https://www.googleapis.com/auth/chat.memberships",
    
    # Forms scopes
    "forms": "https://www.googleapis.com/auth/forms.body",
    "forms_read": "https://www.googleapis.com/auth/forms.body.readonly",
    "forms_responses_read": "https://www.googleapis.com/auth/forms.responses.readonly",
    "forms_body": "https://www.googleapis.com/auth/forms.body",
    "forms_body_readonly": "https://www.googleapis.com/auth/forms.body.readonly",
    "forms_responses_readonly": "https://www.googleapis.com/auth/forms.responses.readonly",
    
    # Slides scopes
    "slides": "https://www.googleapis.com/auth/presentations",
    "slides_read": "https://www.googleapis.com/auth/presentations.readonly",
    
    # Admin scopes
    "admin_users": "https://www.googleapis.com/auth/admin.directory.user",
    "admin_groups": "https://www.googleapis.com/auth/admin.directory.group",
    "admin_roles": "https://www.googleapis.com/auth/admin.directory.rolemanagement",
    "admin_orgunit": "https://www.googleapis.com/auth/admin.directory.orgunit",
    
    # Cloud Platform scopes
    "cloud_platform": "https://www.googleapis.com/auth/cloud-platform",
    "cloud_platform_read_only": "https://www.googleapis.com/auth/cloud-platform.read-only",
    
    # Other common scopes
    "userinfo_profile": "https://www.googleapis.com/auth/userinfo.profile",
    "userinfo_email": "https://www.googleapis.com/auth/userinfo.email",
    "openid": "openid",
    "tasks_read": "https://www.googleapis.com/auth/tasks.readonly",
    "tasks_full": "https://www.googleapis.com/auth/tasks",
    "youtube_read": "https://www.googleapis.com/auth/youtube.readonly",
    "youtube_upload": "https://www.googleapis.com/auth/youtube.upload",
    "youtube_full": "https://www.googleapis.com/auth/youtube",
    "script_projects": "https://www.googleapis.com/auth/script.projects",
    "script_deployments": "https://www.googleapis.com/auth/script.deployments",
    "vault_read": "https://www.googleapis.com/auth/vault.readonly",
    "vault_full": "https://www.googleapis.com/auth/vault",
    "groupssettings_read": "https://www.googleapis.com/auth/apps.groups.settings",
    "siteverification_read": "https://www.googleapis.com/auth/siteverification.readonly",
    "siteverification_full": "https://www.googleapis.com/auth/siteverification",
    "tagmanager_read": "https://www.googleapis.com/auth/tagmanager.readonly",
    "tagmanager_full": "https://www.googleapis.com/auth/tagmanager.manage.containers",
    "webmasters_read": "https://www.googleapis.com/auth/webmasters.readonly",
    "webmasters_full": "https://www.googleapis.com/auth/webmasters",
    "analytics_read": "https://www.googleapis.com/auth/analytics.readonly",
    "analytics_full": "https://www.googleapis.com/auth/analytics",
    "adsense_read": "https://www.googleapis.com/auth/adsense.readonly",
    "adsense_full": "https://www.googleapis.com/auth/adsense",
    "books_read": "https://www.googleapis.com/auth/books",
    "blogger_read": "https://www.googleapis.com/auth/blogger.readonly",
    "blogger_full": "https://www.googleapis.com/auth/blogger",
    "driveactivity_read": "https://www.googleapis.com/auth/drive.activity.readonly",
    "fitness_activity_read": "https://www.googleapis.com/auth/fitness.activity.read",
    "photoslibrary_read": "https://www.googleapis.com/auth/photoslibrary.readonly",
    "photoslibrary_append": "https://www.googleapis.com/auth/photoslibrary.appendonly",
    "photoslibrary_full": "https://www.googleapis.com/auth/photoslibrary",
    "plus_me": "https://www.googleapis.com/auth/plus.me"
}


def _get_scope_groups() -> Dict[str, str]:
    """
    Get scope groups dictionary from centralized registry.
    
    This function provides backward compatibility for legacy SCOPE_GROUPS usage
    while automatically redirecting to the new centralized scope registry.
    Falls back to the original hardcoded scopes if the registry is unavailable.
    
    Returns:
        Dictionary mapping scope names to scope URLs
    """
    if _COMPATIBILITY_AVAILABLE:
        try:
            return CompatibilityShim.get_legacy_scope_groups()
        except Exception as e:
            logger.warning(f"Error getting scope groups from registry, using fallback: {e}")
            return _FALLBACK_SCOPE_GROUPS
    else:
        return _FALLBACK_SCOPE_GROUPS


# Create a dynamic SCOPE_GROUPS that uses the compatibility shim
# This maintains the same interface for existing code
class ScopeGroupsProxy:
    """Proxy class that provides dictionary-like access to scope groups via the registry"""
    
    def __getitem__(self, key: str) -> str:
        return _get_scope_groups()[key]
    
    def __contains__(self, key: str) -> bool:
        return key in _get_scope_groups()
    
    def get(self, key: str, default: str = None) -> str:
        return _get_scope_groups().get(key, default)
    
    def keys(self):
        return _get_scope_groups().keys()
    
    def values(self):
        return _get_scope_groups().values()
    
    def items(self):
        return _get_scope_groups().items()
    
    def copy(self) -> Dict[str, str]:
        return _get_scope_groups().copy()


# Create the proxy instance that behaves like the original SCOPE_GROUPS dictionary
SCOPE_GROUPS = ScopeGroupsProxy()

# Service cache: {cache_key: (service, cached_time, user_email)}
_service_cache: Dict[str, tuple[Any, datetime, str]] = {}
_cache_ttl = timedelta(minutes=30)  # Cache services for 30 minutes


class GoogleServiceError(Exception):
    """Custom exception for Google service errors."""
    pass


def _get_cache_key(user_email: str, service_name: str, version: str, scopes: List[str]) -> str:
    """Generate a cache key for service instances."""
    sorted_scopes = sorted(scopes)
    return f"{user_email}:{service_name}:{version}:{':'.join(sorted_scopes)}"


def _is_cache_valid(cached_time: datetime) -> bool:
    """Check if cached service is still valid."""
    return datetime.now() - cached_time < _cache_ttl


def _get_cached_service(cache_key: str) -> Optional[tuple[Any, str]]:
    """Retrieve cached service if valid."""
    if cache_key in _service_cache:
        service, cached_time, user_email = _service_cache[cache_key]
        if _is_cache_valid(cached_time):
            logger.debug(f"Using cached service for key: {cache_key}")
            return service, user_email
        else:
            # Remove expired cache entry
            del _service_cache[cache_key]
            logger.debug(f"Removed expired cache entry: {cache_key}")
    return None


def _cache_service(cache_key: str, service: Any, user_email: str) -> None:
    """Cache a service instance."""
    _service_cache[cache_key] = (service, datetime.now(), user_email)
    logger.debug(f"Cached service for key: {cache_key}")


def _resolve_scopes(scopes: Union[str, List[str]]) -> List[str]:
    """Resolve scope names to actual scope URLs."""
    # DIAGNOSTIC LOG: OAuth scope inconsistency debugging - scope resolution
    logger.info(f"OAUTH_SCOPE_DEBUG: _resolve_scopes called with input: {scopes}")
    
    if isinstance(scopes, str):
        if scopes in SCOPE_GROUPS:
            resolved = [SCOPE_GROUPS[scopes]]
            logger.info(f"OAUTH_SCOPE_DEBUG: Single string scope '{scopes}' resolved to: {resolved}")
            return resolved
        else:
            logger.info(f"OAUTH_SCOPE_DEBUG: Single string scope '{scopes}' used as-is (not in SCOPE_GROUPS)")
            return [scopes]

    resolved = []
    for scope in scopes:
        if scope in SCOPE_GROUPS:
            resolved_scope = SCOPE_GROUPS[scope]
            logger.info(f"OAUTH_SCOPE_DEBUG: Scope '{scope}' resolved to '{resolved_scope}'")
            resolved.append(resolved_scope)
        else:
            logger.info(f"OAUTH_SCOPE_DEBUG: Scope '{scope}' used as-is (not in SCOPE_GROUPS)")
            resolved.append(scope)
    
    logger.info(f"OAUTH_SCOPE_DEBUG: Final resolved scopes: {resolved}")
    return resolved


def _validate_service_scopes(credentials: Credentials, required_scopes: List[str]) -> bool:
    """
    Validate that the credentials have the required scopes.
    
    Note: This is a basic check. Google credentials don't always expose 
    the exact granted scopes, so this may not catch all scope mismatches.
    """
    if not credentials.scopes:
        logger.warning("Credentials do not expose granted scopes - assuming valid")
        return True
    
    granted_scopes = set(credentials.scopes)
    required_scopes_set = set(required_scopes)
    
    if not required_scopes_set.issubset(granted_scopes):
        missing_scopes = required_scopes_set - granted_scopes
        logger.warning(f"Missing required scopes: {missing_scopes}")
        return False
    
    return True


async def get_google_service(
    user_email: str,
    service_type: str,
    scopes: Union[str, List[str]] = None,
    version: Optional[str] = None,
    cache_enabled: bool = True
) -> Any:
    """
    Get an authenticated Google service for a user.
    
    This is the generic replacement for get_drive_service that can handle
    any Google service type.
    
    Args:
        user_email: User's email address
        service_type: Type of Google service ("drive", "gmail", "calendar", etc.)
        scopes: Required scopes (can be scope group names or actual URLs)
        version: Service version (defaults to standard version for service type)
        cache_enabled: Whether to use service caching (default: True)
    
    Returns:
        Authenticated Google service instance
        
    Raises:
        GoogleServiceError: If authentication fails or service cannot be created
    """
    # Validate service type
    if service_type not in SERVICE_CONFIGS:
        available_services = ", ".join(SERVICE_CONFIGS.keys())
        raise GoogleServiceError(
            f"Unknown service type: {service_type}. "
            f"Available services: {available_services}"
        )
    
    # Get service configuration
    config = SERVICE_CONFIGS[service_type]
    service_name = config["service"]
    service_version = version or config["version"]
    
    # Resolve scopes - use minimal default if not specified
    if scopes is None:
        # Use basic userinfo scope as default
        resolved_scopes = ["https://www.googleapis.com/auth/userinfo.email", "openid"]
    else:
        resolved_scopes = _resolve_scopes(scopes)
    
    # Check cache first if enabled
    if cache_enabled:
        cache_key = _get_cache_key(user_email, service_name, service_version, resolved_scopes)
        cached_result = _get_cached_service(cache_key)
        if cached_result:
            service, cached_user_email = cached_result
            logger.debug(f"Using cached {service_type} service for {user_email}")
            return service
    
    # Try to get from session cache first
    session_id = get_session_context()
    if session_id:
        session_key = f"service_{user_email}_{service_type}_{service_version}"
        cached_service = get_session_data(session_id, session_key)
        if cached_service:
            logger.debug(f"Using session-cached {service_type} service for {user_email}")
            return cached_service
    
    # Get valid credentials
    credentials = get_valid_credentials(user_email)
    if not credentials:
        raise GoogleServiceError(
            f"No valid credentials found for {user_email}. "
            f"Please authenticate first using the start_google_auth tool."
        )
    
    # Validate scopes (basic check)
    if not _validate_service_scopes(credentials, resolved_scopes):
        logger.warning(
            f"Credentials for {user_email} may not have all required scopes for {service_type}. "
            f"Required: {resolved_scopes}, Granted: {credentials.scopes}"
        )
    
    # Build the service
    try:
        # Special handling for Photos Library API which uses a custom discovery URL
        if service_name == "photoslibrary":
            from googleapiclient.discovery import build_from_document
            import requests
            
            # Photos Library API uses a custom discovery document
            discovery_url = f"https://photoslibrary.googleapis.com/$discovery/rest?version={service_version}"
            discovery_doc = requests.get(discovery_url).json()
            service = build_from_document(discovery_doc, credentials=credentials)
            logger.info(f"Created Photos Library service (v{service_version}) for {user_email} using custom discovery")
        else:
            service = build(service_name, service_version, credentials=credentials)
            logger.info(f"Created {service_type} service (v{service_version}) for {user_email}")
        
        # Cache the service
        if cache_enabled:
            cache_key = _get_cache_key(user_email, service_name, service_version, resolved_scopes)
            _cache_service(cache_key, service, user_email)
        
        # Store in session cache as well
        if session_id:
            session_key = f"service_{user_email}_{service_type}_{service_version}"
            store_session_data(session_id, session_key, service)
        
        return service
        
    except RefreshError as e:
        error_msg = _handle_token_refresh_error(e, user_email, service_type)
        raise GoogleServiceError(error_msg)
    except Exception as e:
        logger.error(f"Failed to create {service_type} service for {user_email}: {e}")
        raise GoogleServiceError(f"Failed to create {service_type} service: {e}")


def _handle_token_refresh_error(error: RefreshError, user_email: str, service_type: str) -> str:
    """
    Handle token refresh errors gracefully, particularly expired/revoked tokens.
    
    Args:
        error: The RefreshError that occurred
        user_email: User's email address
        service_type: Type of the Google service
    
    Returns:
        A user-friendly error message with instructions for reauthentication
    """
    error_str = str(error)
    
    if 'invalid_grant' in error_str.lower() or 'expired or revoked' in error_str.lower():
        logger.warning(f"Token expired or revoked for user {user_email} accessing {service_type}")
        
        # Clear any cached service for this user to force fresh authentication
        clear_service_cache(user_email)
        
        service_display_name = f"Google {service_type.title()}"
        
        return (
            f"**Authentication Required: Token Expired/Revoked for {service_display_name}**\n\n"
            f"Your Google authentication token for {user_email} has expired or been revoked. "
            f"This commonly happens when:\n"
            f"- The token has been unused for an extended period\n"
            f"- You've changed your Google account password\n"
            f"- You've revoked access to the application\n\n"
            f"**To resolve this, please:**\n"
            f"1. Run `start_google_auth` with your email ({user_email}) and service_name='{service_display_name}'\n"
            f"2. Complete the authentication flow in your browser\n"
            f"3. Retry your original command\n\n"
            f"The application will automatically use the new credentials once authentication is complete."
        )
    else:
        # Handle other types of refresh errors
        logger.error(f"Unexpected refresh error for user {user_email}: {error}")
        return (
            f"Authentication error occurred for {user_email}. "
            f"Please try running `start_google_auth` with your email and the appropriate service name to reauthenticate."
        )


def clear_service_cache(user_email: Optional[str] = None) -> int:
    """
    Clear service cache entries.
    
    Args:
        user_email: If provided, only clear cache for this user. If None, clear all.
    
    Returns:
        Number of cache entries cleared.
    """
    global _service_cache
    
    if user_email is None:
        count = len(_service_cache)
        _service_cache.clear()
        logger.info(f"Cleared all {count} service cache entries")
        return count
    
    keys_to_remove = [key for key in _service_cache.keys() if key.startswith(f"{user_email}:")]
    for key in keys_to_remove:
        del _service_cache[key]
    
    logger.info(f"Cleared {len(keys_to_remove)} service cache entries for user {user_email}")
    return len(keys_to_remove)


def get_cache_stats() -> Dict[str, Any]:
    """Get service cache statistics."""
    now = datetime.now()
    valid_entries = 0
    expired_entries = 0
    
    for _, (_, cached_time, _) in _service_cache.items():
        if _is_cache_valid(cached_time):
            valid_entries += 1
        else:
            expired_entries += 1
    
    return {
        "total_entries": len(_service_cache),
        "valid_entries": valid_entries,
        "expired_entries": expired_entries,
        "cache_ttl_minutes": _cache_ttl.total_seconds() / 60
    }


def get_available_services() -> Dict[str, Dict[str, str]]:
    """Get list of available Google services and their configurations."""
    return SERVICE_CONFIGS.copy()


def get_available_scope_groups() -> Dict[str, str]:
    """Get list of available scope groups and their URLs."""
    return SCOPE_GROUPS.copy()


# Maintain backward compatibility - keep the original get_drive_service function
# but implement it using the new generic system
async def get_drive_service(user_email: str):
    """
    Get an authenticated Google Drive service for a user.
    
    This function is maintained for backward compatibility.
    New code should use get_google_service("drive", ...) instead.
    
    Args:
        user_email: User's email address
    
    Returns:
        Authenticated Google Drive service
    """
    logger.info(f"Using legacy get_drive_service for {user_email} - consider upgrading to get_google_service")
    return await get_google_service(
        user_email=user_email,
        service_type="drive",
        scopes=["drive_file", "drive_read"]
    )