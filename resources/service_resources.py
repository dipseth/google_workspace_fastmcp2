import logging
import json
from datetime import datetime
from pathlib import Path
from typing_extensions import Any, Dict, List, Optional, Set, Annotated

from fastmcp import FastMCP, Context
from jsonschema import validate, ValidationError
from pydantic import Field

# Import our custom types for consistent parameter definitions
from tools.common_types import ServiceTypeAnnotated

# Import SupportedService type and validation utilities
from resources.service_list_resources import SupportedService, get_supported_services
from auth.scope_registry import ScopeRegistry

from config.enhanced_logging import setup_logger
logger = setup_logger()

def setup_service_resources(main_mcp: FastMCP):
    """Register service resources with the main FastMCP server using FastMCP 2.10.6+ API."""
    logger.info("🔧 Setting up Google service resources...")
    
    # Register resources directly with main MCP instance using FastMCP 2.10.6+ approach
    # This avoids the Context creation issues from using a separate local instance
    logger.info("✅ Service resources setup completed (FastMCP 2.10.6+ compatible)")

# Load the JSON schema for Google Service Configuration
_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "google_service_config_schema.json"
_SERVICE_CONFIG_SCHEMA: Optional[Dict[str, Any]] = None

def _load_schema():
    """Loads the JSON schema from file."""
    global _SERVICE_CONFIG_SCHEMA
    if _SERVICE_CONFIG_SCHEMA is None:
        try:
            with open(_SCHEMA_PATH, 'r') as f:
                _SERVICE_CONFIG_SCHEMA = json.load(f)
            logger.info(f"Successfully loaded schema from {_SCHEMA_PATH}")
        except FileNotFoundError:
            logger.error(f"Schema file not found at {_SCHEMA_PATH}")
            _SERVICE_CONFIG_SCHEMA = {} # Set to empty to avoid repeated attempts
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON schema from {_SCHEMA_PATH}: {e}")
            _SERVICE_CONFIG_SCHEMA = {}
    return _SERVICE_CONFIG_SCHEMA

def validate_service_config(config_data: Dict[str, Any]):
    """
    Validates a service configuration dictionary against the predefined JSON schema.

    Args:
        config_data: The dictionary containing service configuration.

    Raises:
        ValidationError: If the config_data does not conform to the schema.
    """
    schema = _load_schema()
    if not schema:
        logger.warning("Schema not loaded, skipping validation.")
        return
    
    try:
        validate(instance=config_data, schema=schema)
        logger.debug("Service configuration validated successfully.")
    except ValidationError as e:
        logger.error(f"Service configuration validation failed: {e.message} at {e.path}")
        raise

async def get_service_config(
    ctx: Context,
    service_type: ServiceTypeAnnotated,
    api_version: Annotated[Optional[str], Field(description="Optional specific API version (e.g., 'v1', 'v3')", pattern=r"^v\d+$")] = None
) -> Dict[str, Any]:
    """
    Retrieves the configuration for a specified Google service.

    Args:
        ctx: The FastMCP context.
        service_type: The type of Google service (validated against supported services).
        api_version: Optional. The specific API version to retrieve (e.g., 'v1', 'v3').
                     If not provided, the default or recommended version will be returned.

    Returns:
        A dictionary containing the service configuration details.
    """
    # Normalize service type to lowercase
    service_lower = service_type.lower()
    
    # Validate service is supported
    if service_lower not in get_supported_services():
        raise ValueError(f"Service '{service_type}' not supported. Available: {get_supported_services()}")
    
    # Get endpoint information dynamically
    endpoint = _get_service_endpoint(service_lower, api_version)
    
    # Get scopes from the scope registry
    try:
        basic_scopes = ScopeRegistry.get_service_scopes(service_lower, "basic")
        full_scopes = ScopeRegistry.get_service_scopes(service_lower, "full")
        readonly_scopes = ScopeRegistry.get_service_scopes(service_lower, "readonly")
    except ValueError:
        # Fallback if service not in scope registry
        basic_scopes = []
        full_scopes = []
        readonly_scopes = []
    
    # Example structure for a service configuration
    config_data = {
        "service": service_lower,
        "configuration": {
            "api_name": service_lower,
            "api_version": api_version if api_version else _get_default_api_version(service_lower),
            "base_url": endpoint,
            "discovery_url": f"{endpoint}$discovery/rest?version={api_version if api_version else _get_default_api_version(service_lower)}",
            "scopes": {
                "read": readonly_scopes,
                "basic": basic_scopes,
                "full": full_scopes
            },
            "features": {
                "batch_requests": True,
                "watch_notifications": False,
                "delegation": False
            },
            "limits": {
                "requests_per_minute": 1000,
                "requests_per_day": 100000
            }
        },
        "metadata": {
            "last_updated": datetime.now().isoformat(),
            "documentation_url": f"https://developers.google.com/{service_lower}/api",
            "authentication_required": True,
            "tags": ["google", "service", "config", "metadata", "api", service_lower]
        }
    }

    # Add service-specific details
    if service_lower == "gmail":
        config_data["configuration"]["features"]["watch_notifications"] = True
        config_data["configuration"]["limits"]["attachment_size_mb"] = 25
        config_data["metadata"]["tags"].extend(["email", "communication"])
    elif service_lower == "drive":
        config_data["configuration"]["features"]["delegation"] = True
        config_data["metadata"]["tags"].extend(["storage", "files"])
    elif service_lower == "photos":
        config_data["configuration"]["features"]["batch_uploads"] = True
        config_data["metadata"]["tags"].extend(["media", "images"])
    # Additional service-specific configurations are now handled via scope registry

    # Validate the generated configuration against the schema
    try:
        validate_service_config(config_data)
    except ValidationError as e:
        logger.error(f"Generated service config for {service_lower} failed validation: {e.message}")
        # Depending on severity, you might raise the error or return a partial/error response
        raise ValueError(f"Invalid service configuration generated for {service_lower}: {e.message}")

    return config_data

# Helper functions for dynamic service configuration
def _get_service_endpoint(service: str, api_version: Optional[str] = None) -> str:
    """
    Get the API endpoint for a service dynamically.
    
    Args:
        service: Service name (lowercase)
        api_version: Optional API version
        
    Returns:
        Base API endpoint URL
    """
    # Service-specific endpoint patterns
    endpoint_patterns = {
        "gmail": "https://gmail.googleapis.com/",
        "drive": f"https://www.googleapis.com/drive/{api_version or 'v3'}/",
        "calendar": f"https://www.googleapis.com/calendar/{api_version or 'v3'}/",
        "docs": f"https://docs.googleapis.com/{api_version or 'v1'}/",
        "sheets": f"https://sheets.googleapis.com/{api_version or 'v4'}/",
        "forms": f"https://forms.googleapis.com/{api_version or 'v1'}/",
        "slides": f"https://slides.googleapis.com/{api_version or 'v1'}/",
        "chat": f"https://chat.googleapis.com/{api_version or 'v1'}/",
        "photos": "https://photoslibrary.googleapis.com/",
        "photoslibrary": "https://photoslibrary.googleapis.com/",
        "admin": f"https://admin.googleapis.com/admin/directory/{api_version or 'v1'}/",
        "tasks": f"https://tasks.googleapis.com/tasks/{api_version or 'v1'}/",
        "youtube": f"https://www.googleapis.com/youtube/{api_version or 'v3'}/",
        "script": f"https://script.googleapis.com/{api_version or 'v1'}/"
    }
    
    # Return specific pattern or generate default
    if service in endpoint_patterns:
        return endpoint_patterns[service]
    else:
        # Default pattern for unknown services
        return f"https://www.googleapis.com/{service}/{api_version or 'v1'}/"

def _get_default_api_version(service: str) -> str:
    """
    Get the default API version for a service.
    
    Args:
        service: Service name (lowercase)
        
    Returns:
        Default API version string
    """
    default_versions = {
        "gmail": "v1",
        "drive": "v3",
        "calendar": "v3",
        "docs": "v1",
        "sheets": "v4",
        "forms": "v1",
        "slides": "v1",
        "chat": "v1",
        "photos": "v1",
        "photoslibrary": "v1",
        "admin": "v1",
        "tasks": "v1",
        "youtube": "v3",
        "script": "v1"
    }
    
    return default_versions.get(service, "v1")

# Additional resource templates for scopes and versions

async def get_service_scopes_by_group(
    ctx: Context,
    service_type: ServiceTypeAnnotated,
    scope_group: Annotated[str, Field(description="Scope group name (e.g., 'basic', 'full', 'readonly')")]
) -> Dict[str, Any]:
    """
    Retrieves OAuth scopes for a specified Google service and scope group.
    
    Args:
        ctx: The FastMCP context.
        service_type: The type of Google service (validated).
        scope_group: The scope group (e.g., 'basic', 'full', 'readonly').
        
    Returns:
        Dictionary with scope information.
    """
    # Normalize service type
    service_lower = service_type.lower()
    
    # Validate service is supported
    if service_lower not in get_supported_services():
        raise ValueError(f"Service '{service_type}' not supported. Available: {get_supported_services()}")
    
    # Get scopes from the scope registry
    try:
        scopes = ScopeRegistry.get_service_scopes(service_lower, scope_group)
    except ValueError as e:
        logger.warning(f"Could not get scopes for {service_lower}/{scope_group}: {e}")
        scopes = []
    
    return {
        "service_type": service_lower,
        "scope_group": scope_group,
        "scopes": scopes,
        "description": f"Scopes for {service_lower} {scope_group} access."
    }

async def get_service_versions(
    ctx: Context,
    service_type: ServiceTypeAnnotated
) -> Dict[str, Any]:
    """
    Retrieves available API versions for a specified Google service.
    
    Args:
        ctx: The FastMCP context.
        service_type: The type of Google service (validated).
        
    Returns:
        Dictionary with version information.
    """
    # Normalize service type
    service_lower = service_type.lower()
    
    # Validate service is supported
    if service_lower not in get_supported_services():
        raise ValueError(f"Service '{service_type}' not supported. Available: {get_supported_services()}")
    
    # Known API versions for each service
    versions = {
        "gmail": ["v1"],
        "drive": ["v2", "v3"],
        "calendar": ["v3"],
        "docs": ["v1"],
        "sheets": ["v4"],
        "forms": ["v1"],
        "slides": ["v1"],
        "chat": ["v1"],
        "photos": ["v1"],
        "photoslibrary": ["v1"],
        "admin": ["v1"],
        "tasks": ["v1"],
        "youtube": ["v3"],
        "script": ["v1"]
    }
    
    return {
        "service_type": service_lower,
        "available_versions": versions.get(service_lower, ["v1"]),
        "default_version": _get_default_api_version(service_lower),
        "description": f"Available API versions for {service_lower}."
    }

async def get_service_quota(
    ctx: Context,
    service_type: ServiceTypeAnnotated
) -> Dict[str, Any]:
    """
    Retrieves quota information for a specified Google service.
    
    Args:
        ctx: The FastMCP context.
        service_type: The type of Google service (validated).
        
    Returns:
        Dictionary with quota information.
    """
    # Normalize service type
    service_lower = service_type.lower()
    
    # Validate service is supported
    if service_lower not in get_supported_services():
        raise ValueError(f"Service '{service_type}' not supported. Available: {get_supported_services()}")
    
    # Quota information (these are typical values, actual quotas may vary by project)
    quota_info = {
        "gmail": {
            "requests_per_minute": 1000,
            "requests_per_day": 1000000,
            "concurrent_requests": 100,
            "quota_units": "per-user"
        },
        "drive": {
            "requests_per_minute": 10000,
            "requests_per_day": 10000000,
            "concurrent_requests": 500,
            "quota_units": "per-project"
        },
        "calendar": {
            "requests_per_minute": 2000,
            "requests_per_day": 1000000,
            "concurrent_requests": 200,
            "quota_units": "per-user"
        },
        "sheets": {
            "requests_per_minute": 300,
            "requests_per_100_seconds": 500,
            "concurrent_requests": 100,
            "quota_units": "per-project"
        },
        "docs": {
            "requests_per_minute": 300,
            "requests_per_100_seconds": 500,
            "concurrent_requests": 100,
            "quota_units": "per-project"
        },
        "photos": {
            "requests_per_minute": 1000,
            "requests_per_day": 50000,
            "concurrent_requests": 50,
            "quota_units": "per-user"
        }
    }
    
    # Default quota for services not explicitly listed
    default_quota = {
        "requests_per_minute": 500,
        "requests_per_day": 100000,
        "concurrent_requests": 50,
        "quota_units": "per-project"
    }
    
    return {
        "service_type": service_lower,
        "quota_limits": quota_info.get(service_lower, default_quota),
        "description": f"Quota limits for {service_lower} API.",
        "note": "Actual quotas may vary based on your Google Cloud project settings."
    }

async def get_service_endpoints(
    ctx: Context,
    service_type: ServiceTypeAnnotated
) -> Dict[str, Any]:
    """
    Retrieves API endpoints for a specified Google service.
    
    This function dynamically generates endpoints based on the service type
    and integrates with the scope registry for comprehensive service information.
    
    Args:
        ctx: The FastMCP context.
        service_type: The type of Google service (validated).
        
    Returns:
        Dictionary with endpoint information.
    """
    # Normalize service type
    service_lower = service_type.lower()
    
    # Validate service is supported
    if service_lower not in get_supported_services():
        raise ValueError(f"Service '{service_type}' not supported. Available: {get_supported_services()}")
    
    # Get the base endpoint
    base_endpoint = _get_service_endpoint(service_lower)
    default_version = _get_default_api_version(service_lower)
    
    # Check if service exists in scope registry for additional info
    has_scope_info = service_lower in ScopeRegistry.GOOGLE_API_SCOPES
    
    return {
        "service_type": service_lower,
        "base_endpoint": base_endpoint,
        "default_version": default_version,
        "discovery_url": f"{base_endpoint}$discovery/rest?version={default_version}",
        "oauth_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "has_scope_registry": has_scope_info,
        "description": f"API endpoints for {service_lower} service.",
        "documentation": f"https://developers.google.com/{service_lower}/api"
    }