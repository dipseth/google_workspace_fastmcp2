import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastmcp import FastMCP, Context
from jsonschema import validate, ValidationError

logger = logging.getLogger(__name__)

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
    service_type: str,
    api_version: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieves the configuration for a specified Google service.

    Args:
        ctx: The FastMCP context.
        service_type: The type of Google service (e.g., 'gmail', 'drive', 'calendar').
        api_version: Optional. The specific API version to retrieve (e.g., 'v1', 'v3').
                     If not provided, the default or recommended version will be returned.

    Returns:
        A dictionary containing the service configuration details.
    """
    # This is a placeholder. Actual implementation will fetch from a registry or config.
    # For now, we'll return a dummy structure based on the architectural plan.
    
    # Example structure for a service configuration
    config_data = {
        "service": service_type,
        "configuration": {
            "api_name": service_type,
            "api_version": api_version if api_version else "default_version",
            "base_url": f"https://{service_type}.googleapis.com",
            "discovery_url": f"https://{service_type}.googleapis.com/$discovery/rest?version={api_version if api_version else 'default_version'}",
            "scopes": {
                "read": [f"https://www.googleapis.com/auth/{service_type}.readonly"],
                "write": [f"https://www.googleapis.com/auth/{service_type}.write"],
                "full": [f"https://www.googleapis.com/auth/{service_type}"]
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
            "last_updated": datetime.now().isoformat(), # Use current time for last_updated
            "documentation_url": f"https://developers.google.com/{service_type}/api",
            "authentication_required": True,
            "tags": ["google", "service", "config", "metadata", "api"] # Use the base tags directly
        }
    }

    # Add specific details for known services (as per architectural plan)
    if service_type == "gmail":
        config_data["configuration"]["api_version"] = "v1"
        config_data["configuration"]["scopes"]["full"] = ["https://mail.google.com/"]
        config_data["configuration"]["features"]["watch_notifications"] = True
        config_data["configuration"]["limits"]["attachment_size_mb"] = 25
        config_data["metadata"]["tags"].extend(["email", "communication"])
    elif service_type == "drive":
        config_data["configuration"]["api_version"] = "v3"
        config_data["configuration"]["scopes"]["full"] = ["https://www.googleapis.com/auth/drive"]
        config_data["configuration"]["features"]["delegation"] = True
        config_data["metadata"]["tags"].extend(["storage", "files"])
    # Add more service-specific configurations as needed

    # Validate the generated configuration against the schema
    try:
        validate_service_config(config_data)
    except ValidationError as e:
        logger.error(f"Generated service config for {service_type} failed validation: {e.message}")
        # Depending on severity, you might raise the error or return a partial/error response
        raise ValueError(f"Invalid service configuration generated for {service_type}: {e.message}")

    return config_data

# Additional resource templates for scopes and versions (as per architectural plan)

async def get_service_scopes_by_group(
    ctx: Context,
    service_type: str,
    scope_group: str
) -> Dict[str, Any]:
    """
    Retrieves OAuth scopes for a specified Google service and scope group.
    """
    # Placeholder implementation
    all_scopes = {
        "gmail": {
            "read": ["https://www.googleapis.com/auth/gmail.readonly"],
            "write": ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.compose"],
            "full": ["https://mail.google.com/"]
        },
        "drive": {
            "read": ["https://www.googleapis.com/auth/drive.readonly"],
            "write": ["https://www.googleapis.com/auth/drive.file"],
            "full": ["https://www.googleapis.com/auth/drive"]
        }
    }
    
    scopes = all_scopes.get(service_type, {}).get(scope_group, [])
    return {
        "service_type": service_type,
        "scope_group": scope_group,
        "scopes": scopes,
        "description": f"Scopes for {service_type} {scope_group} access."
    }

async def get_service_versions(
    ctx: Context,
    service_type: str
) -> Dict[str, Any]:
    """
    Retrieves available API versions for a specified Google service.
    """
    # Placeholder implementation
    versions = {
        "gmail": ["v1"],
        "drive": ["v2", "v3"],
        "calendar": ["v3"],
        "docs": ["v1"],
        "sheets": ["v4"],
        "forms": ["v1"],
        "slides": ["v1"],
        "chat": ["v1"]
    }
    return {
        "service_type": service_type,
        "available_versions": versions.get(service_type, []),
        "description": f"Available API versions for {service_type}."
    }

async def get_service_quota(
    ctx: Context,
    service_type: str
) -> Dict[str, Any]:
    """
    Retrieves quota information for a specified Google service.
    """
    # Placeholder implementation
    quota_info = {
        "gmail": {
            "requests_per_minute": 1000,
            "requests_per_day": 1000000,
            "concurrent_requests": 100
        },
        "drive": {
            "requests_per_minute": 10000,
            "requests_per_day": 10000000,
            "concurrent_requests": 500
        }
    }
    return {
        "service_type": service_type,
        "quota_limits": quota_info.get(service_type, {}),
        "description": f"Quota limits for {service_type} API."
    }

async def get_service_endpoints(
    ctx: Context,
    service_type: str
) -> Dict[str, Any]:
    """
    Retrieves API endpoints for a specified Google service.
    """
    # Placeholder implementation
    endpoints = {
        "gmail": "https://gmail.googleapis.com/",
        "drive": "https://www.googleapis.com/drive/v3/",
        "calendar": "https://www.googleapis.com/calendar/v3/",
        "docs": "https://docs.googleapis.com/v1/",
        "sheets": "https://sheets.googleapis.com/v4/",
        "forms": "https://forms.googleapis.com/v1/",
        "slides": "https://slides.googleapis.com/v1/",
        "chat": "https://chat.googleapis.com/v1/"
    }
    return {
        "service_type": service_type,
        "base_endpoint": endpoints.get(service_type, "N/A"),
        "description": f"Base API endpoint for {service_type}."
    }