"""
Service type definitions for Google OAuth authentication.

This module provides dynamic type definitions that align with the scope registry
and service helpers, ensuring type safety while maintaining flexibility.
"""

from typing_extensions import Literal


# Dynamic service name literal constructed from scope registry
# This will be populated at import time from the actual services
def _get_service_names_literal():
    """Get available service names from scope registry for dynamic Literal type."""
    try:
        from .scope_registry import ScopeRegistry

        service_names = list(ScopeRegistry.SERVICE_METADATA.keys())
        catalog = ScopeRegistry.get_service_catalog()
        catalog_keys = list(catalog.keys())

        # Combine both lists and remove duplicates while preserving order
        all_services = []
        seen = set()
        for service in service_names + catalog_keys + ["Google Services"]:
            if service not in seen:
                all_services.append(service)
                seen.add(service)

        return all_services
    except ImportError:
        # Fallback if scope registry not available
        return [
            "Google Services",
            "drive",
            "gmail",
            "calendar",
            "docs",
            "sheets",
            "chat",
            "forms",
            "slides",
            "photos",
            "tasks",
        ]


# Get the actual service names at import time
_AVAILABLE_SERVICES = _get_service_names_literal()

# Dynamic Literal type based on actual available services from scope registry
GoogleServiceName = Literal[
    "drive",
    "gmail",
    "calendar",
    "docs",
    "sheets",
    "chat",
    "forms",
    "slides",
    "photos",
    "tasks",
]

# Service display names dynamically constructed from scope registry metadata
GoogleServiceDisplayName = Literal[
    "Google Services",  # Default/comprehensive
    "Google Drive",  # drive service
    "Gmail",  # gmail service
    "Google Calendar",  # calendar service
    "Google Docs",  # docs service
    "Google Sheets",  # sheets service
    "Google Chat",  # chat service
    "Google Forms",  # forms service
    "Google Slides",  # slides service
    "Google Photos",  # photos service
    "Google Tasks",  # tasks service
    "Office Suite",  # Multi-service combination
    "Communication Suite",  # Multi-service combination
    "All Google Services",  # Comprehensive access
]

# Service categories from scope registry
ServiceCategory = Literal[
    "Core Services", "Storage & Files", "Communication", "Productivity", "Office Suite"
]

# Authentication methods
AuthenticationMethod = Literal[
    "pkce",  # PKCE flow (enhanced security, session-based)
    "credentials",  # Encrypted credentials (persistent, multi-account)
]

# Scope access levels
ScopeAccessLevel = Literal[
    "basic",  # Basic access (most common scopes)
    "full",  # Full access (all available scopes)
    "readonly",  # Read-only access
]
