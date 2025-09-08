"""Helper functions and utilities for Google service management."""

import logging
from typing_extensions import Any, Optional, Union, List, Dict

from .service_manager import get_google_service, get_available_services, get_available_scope_groups
from .context import (
    request_google_service, get_injected_service, get_user_email_context,
    get_google_service_simple
)

# Import compatibility shim for OAuth scope management
try:
    from .compatibility_shim import CompatibilityShim
    _COMPATIBILITY_AVAILABLE = True
except ImportError:
    # Fallback for development/testing
    _COMPATIBILITY_AVAILABLE = False
    logging.warning("Compatibility shim not available, using fallback service defaults")

logger = logging.getLogger(__name__)

# Import centralized scope registry
from .scope_registry import ScopeRegistry

# Legacy fallback for compatibility - now redirects to scope_registry
_FALLBACK_SERVICE_DEFAULTS = {}  # Empty - now uses ScopeRegistry


def _get_service_defaults() -> Dict[str, Dict]:
    """
    Get service defaults dictionary from centralized registry.
    
    This function provides backward compatibility for legacy SERVICE_DEFAULTS usage
    while automatically redirecting to the new centralized scope registry.
    Falls back to the original hardcoded defaults if the registry is unavailable.
    
    Returns:
        Dictionary mapping service names to their default configurations
    """
    if _COMPATIBILITY_AVAILABLE:
        try:
            # Build service defaults from scope registry
            service_defaults = {}
            
            for service_name, service_metadata in ScopeRegistry.SERVICE_METADATA.items():
                service_defaults[service_name] = {
                    "default_scopes": ScopeRegistry.get_service_scopes(service_name, "basic"),
                    "version": service_metadata.version,
                    "description": service_metadata.description
                }
            
            return service_defaults
        except Exception as e:
            logger.warning(f"Error getting service defaults from registry, using fallback: {e}")
            return {}
    else:
        return {}


# Create a dynamic SERVICE_DEFAULTS that uses the compatibility shim
# This maintains the same interface for existing code
class ServiceDefaultsProxy:
    """Proxy class that provides dictionary-like access to service defaults via the registry"""
    
    def __getitem__(self, key: str) -> Dict:
        return _get_service_defaults()[key]
    
    def __contains__(self, key: str) -> bool:
        return key in _get_service_defaults()
    
    def get(self, key: str, default: Dict = None) -> Dict:
        return _get_service_defaults().get(key, default)
    
    def keys(self):
        return _get_service_defaults().keys()
    
    def values(self):
        return _get_service_defaults().values()
    
    def items(self):
        return _get_service_defaults().items()
    
    def copy(self) -> Dict[str, Dict]:
        return _get_service_defaults().copy()


# Create the proxy instance that behaves like the original SERVICE_DEFAULTS dictionary
SERVICE_DEFAULTS = ServiceDefaultsProxy()


async def get_service(
    service_type: str,
    user_email: str,
    scopes: Union[str, List[str]] = None,
    version: Optional[str] = None
) -> Any:
    """
    Universal function to get any Google service with smart defaults.
    
    This is the ONE function you need for all Google services. It automatically
    uses sensible defaults for each service type while allowing full customization.
    
    Args:
        service_type: Type of service ("drive", "gmail", "calendar", etc.)
        user_email: User's email address
        scopes: Custom scopes (uses service defaults if None)
        version: API version (uses service default if None)
    
    Returns:
        Authenticated Google service instance
        
    Examples:
        # Use defaults - most common case
        drive_service = await get_service("drive", user_email)
        gmail_service = await get_service("gmail", user_email)
        
        # Custom scopes
        drive_service = await get_service("drive", user_email, ["drive_full"])
        
        # Custom version
        old_gmail = await get_service("gmail", user_email, version="v1beta")
    """
    # Get defaults for this service type
    defaults = SERVICE_DEFAULTS.get(service_type)
    if not defaults:
        # If no defaults, let the underlying service_manager handle it
        logger.warning(f"No defaults found for service type: {service_type}")
        return await get_google_service(
            user_email=user_email,
            service_type=service_type,
            scopes=scopes,
            version=version
        )
    
    # Use defaults if not provided
    final_scopes = scopes if scopes is not None else defaults["default_scopes"]
    final_version = version if version is not None else defaults["version"]
    
    logger.debug(f"Getting {service_type} service for {user_email} with scopes: {final_scopes}")
    
    return await get_google_service(
        user_email=user_email,
        service_type=service_type,
        scopes=final_scopes,
        version=final_version
    )


def request_service(
    service_type: str,
    scopes: Union[str, List[str]] = None,
    version: Optional[str] = None,
    cache_enabled: bool = True
) -> str:
    """
    Universal function to request any Google service through middleware.
    
    Args:
        service_type: Type of service ("drive", "gmail", "calendar", etc.)
        scopes: Custom scopes (uses service defaults if None)
        version: API version (uses service default if None)
        cache_enabled: Whether to enable caching
    
    Returns:
        Service key for later retrieval with get_injected_service()
        
    Examples:
        # Use defaults
        drive_key = request_service("drive")
        gmail_key = request_service("gmail")
        
        # Custom scopes
        drive_key = request_service("drive", ["drive_full"])
    """
    # Get defaults for this service type
    defaults = SERVICE_DEFAULTS.get(service_type)
    if defaults:
        final_scopes = scopes if scopes is not None else defaults["default_scopes"]
        final_version = version if version is not None else defaults["version"]
    else:
        # No defaults available, use provided values or let service_manager handle
        final_scopes = scopes
        final_version = version
        logger.warning(f"No defaults found for service type: {service_type}")
    
    return request_google_service(
        service_type=service_type,
        scopes=final_scopes,
        version=final_version,
        cache_enabled=cache_enabled
    )


def get_current_user_email() -> Optional[str]:
    """Get the current user email from context."""
    return get_user_email_context()


def get_service_defaults(service_type: str) -> Optional[Dict]:
    """
    Get default configuration for a service type.
    
    Args:
        service_type: Type of service
        
    Returns:
        Default configuration dict or None if not found
    """
    return SERVICE_DEFAULTS.get(service_type)


def list_supported_services() -> List[str]:
    """
    Get list of services with configured defaults.
    
    Returns:
        List of service type names with defaults
    """
    return list(SERVICE_DEFAULTS.keys())


def create_service_info_summary() -> str:
    """
    Create a summary of available services with their defaults.
    
    Returns:
        Formatted string with service information
    """
    summary = "📋 **Supported Google Services**\n\n"
    
    summary += "**🔧 Services with Smart Defaults:**\n"
    for service_type, config in SERVICE_DEFAULTS.items():
        summary += f"- **`{service_type}`** (v{config['version']}): {config['description']}\n"
        summary += f"  Default scopes: `{', '.join(config['default_scopes'])}`\n\n"
    
    # Also show all available services from service_manager
    all_services = get_available_services()
    additional_services = {k: v for k, v in all_services.items() if k not in SERVICE_DEFAULTS}
    
    if additional_services:
        summary += "**⚙️ Additional Available Services:**\n"
        for service_type, config in additional_services.items():
            summary += f"- `{service_type}`: {config['service']} v{config['version']}\n"
        summary += "\n"
    
    summary += "**💡 Usage Examples:**\n"
    summary += "```python\n"
    summary += "# Simple - uses smart defaults\n"
    summary += "drive_service = await get_service('drive', user_email)\n"
    summary += "gmail_service = await get_service('gmail', user_email)\n\n"
    summary += "# Custom scopes\n"
    summary += "drive_service = await get_service('drive', user_email, ['drive_full'])\n\n"
    summary += "# Middleware injection\n"
    summary += "service_key = request_service('gmail')\n"
    summary += "gmail_service = get_injected_service(service_key)\n"
    summary += "```"
    
    return summary


async def create_multi_service_session(
    user_email: str,
    service_types: Union[List[str], List[dict]]
) -> Dict[str, Any]:
    """
    Create multiple Google services in one call with smart defaults.
    
    Args:
        user_email: User's email address
        service_types: Either:
                      - List of service type strings (uses defaults)
                      - List of service config dicts for custom settings
    
    Returns:
        Dictionary mapping service types to service instances
    
    Examples:
        # Simple - uses defaults for all services
        session = await create_multi_service_session(user_email,
            ["drive", "gmail", "calendar"])
        
        # Mixed - some with defaults, some with custom config
        session = await create_multi_service_session(user_email, [
            "gmail",  # Uses defaults
            {"service_type": "drive", "scopes": ["drive_full"]},  # Custom
            "calendar"  # Uses defaults
        ])
    """
    result = {}
    
    for service_spec in service_types:
        if isinstance(service_spec, str):
            # Simple service type string - use defaults
            service_type = service_spec
            try:
                service = await get_service(service_type, user_email)
                result[service_type] = service
                logger.info(f"Created {service_type} service with defaults")
            except Exception as e:
                logger.error(f"Failed to create {service_type} service: {e}")
                result[service_type] = None
            
        elif isinstance(service_spec, dict):
            # Custom service configuration
            service_type = service_spec["service_type"]
            scopes = service_spec.get("scopes")
            version = service_spec.get("version")
            
            try:
                service = await get_service(service_type, user_email, scopes, version)
                result[service_type] = service
                logger.info(f"Created {service_type} service with custom config")
                
            except Exception as e:
                logger.error(f"Failed to create {service_type} service: {e}")
                result[service_type] = None
        else:
            logger.error(f"Invalid service specification: {service_spec}")
            result[str(service_spec)] = None
    
    return result


# Convenience aliases for backward compatibility and ease of use
async def get_drive_service(user_email: str, scopes: Union[str, List[str]] = None) -> Any:
    """Get Drive service - convenience alias."""
    return await get_service("drive", user_email, scopes)


async def get_gmail_service(user_email: str, scopes: Union[str, List[str]] = None) -> Any:
    """Get Gmail service - convenience alias."""
    return await get_service("gmail", user_email, scopes)


async def get_calendar_service(user_email: str, scopes: Union[str, List[str]] = None) -> Any:
    """Get Calendar service - convenience alias."""
    return await get_service("calendar", user_email, scopes)


def request_drive_service(scopes: Union[str, List[str]] = None) -> str:
    """Request Drive service through middleware - convenience alias."""
    return request_service("drive", scopes)


def request_gmail_service(scopes: Union[str, List[str]] = None) -> str:
    """Request Gmail service through middleware - convenience alias."""
    return request_service("gmail", scopes)


async def get_photos_service(user_email: str, scopes: Union[str, List[str]] = None) -> Any:
    """Get Photos service - convenience alias."""
    return await get_service("photos", user_email, scopes)


def request_photos_service(scopes: Union[str, List[str]] = None) -> str:
    """Request Photos service through middleware - convenience alias."""
    return request_service("photos", scopes)



async def get_tasks_service(user_email: str, scopes: Union[str, List[str]] = None) -> Any:
    """Get Tasks service - convenience alias."""
    return await get_service("tasks", user_email, scopes)


def request_tasks_service(scopes: Union[str, List[str]] = None) -> str:
    """Request Tasks service through middleware - convenience alias."""
    return request_service("tasks", scopes)