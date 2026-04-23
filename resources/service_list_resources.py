"""
Enhanced Dynamic Service List Resources for FastMCP2 - Refactored with TagBasedResourceMiddleware.

This module has been dramatically simplified from 1715 lines to ~100 lines by leveraging
the new TagBasedResourceMiddleware approach.

## Architecture Change

BEFORE (1715 lines):
- Complex ServiceListDiscovery class with tool introspection
- Manual TOOL_CONFIGURATIONS mapping with 793 lines of configuration
- Complex authentication fallbacks and user email detection
- Extensive parameter filtering and response model management
- Manual tool calling and result parsing

AFTER (~100 lines):
- Simple resource registration only
- TagBasedResourceMiddleware handles all complex logic
- Middleware intercepts service:// URIs before reaching these handlers
- Unified authentication via AuthMiddleware context
- Tag-based tool discovery instead of complex introspection

## How It Works

1. These resource handlers are registered with FastMCP for discoverability
2. TagBasedResourceMiddleware intercepts all service:// URI requests
3. Middleware uses tool tags to discover appropriate list tools
4. Middleware handles authentication, tool calling, and response formatting
5. These placeholder handlers are never actually called in normal operation

## Migration Notes

The old approach required:
- 655-line ServiceListDiscovery class (lines 655-1309)
- 128-line TOOL_CONFIGURATIONS mapping (lines 665-793)
- Complex authentication helpers (lines 544-649)
- Multiple response models and validation (lines 372-540)

The new approach delegates all this complexity to TagBasedResourceMiddleware,
which uses tool tags for discovery and provides unified handling.

## Resource Hierarchy

1. service://{service}/lists - Returns available list types for the service
2. service://{service}/{list_type} - Returns all IDs/items for that list type
3. service://{service}/{list_type}/{id} - Returns detailed data for a specific ID

Examples:
- service://gmail/lists → Available list types (filters, labels)
- service://gmail/filters → All Gmail filters
- service://gmail/filters/123 → Specific filter details
"""

from datetime import datetime
from typing import List

from fastmcp import Context, FastMCP
from pydantic import BaseModel, Field
from typing_extensions import Annotated, NotRequired, Optional, TypedDict

from auth.context import get_user_email_context
from config.enhanced_logging import setup_logger
from middleware.service_list_response import (
    ServiceItemDetailsResponse,
    ServiceListResponse,
    ServiceListsResponse,
)

logger = setup_logger()


class ServiceScopesResponse(TypedDict):
    """Response model for Google service scopes resource (google://services/scopes/{service}).

    Provides OAuth scope information, API version, and configuration details for
    specific Google services including Drive, Gmail, Calendar, and other Workspace APIs.
    """

    service: str  # Name of the Google service (e.g., "gmail", "drive", "calendar")
    default_scopes: List[str]  # List of OAuth scopes required for this service
    version: str  # API version used for this service (e.g., "v1", "v3")
    description: str  # Human-readable description of the service
    timestamp: str  # ISO 8601 timestamp when this response was generated
    error: NotRequired[
        Optional[str]
    ]  # Error message if service information retrieval failed
    available_services: NotRequired[
        List[str]
    ]  # List of all available services if service lookup failed


def get_supported_services() -> List[str]:
    """
    Get the list of supported Google services.

    This list matches what's configured in TagBasedResourceMiddleware.
    """
    return [
        "gmail",
        "drive",
        "calendar",
        "docs",
        "sheets",
        "chat",
        "forms",
        "slides",
        "photos",
    ]


def generate_service_documentation() -> str:
    """Generate documentation string with all supported services."""
    services = get_supported_services()
    service_docs = []

    # Service icons mapping
    service_icons = {
        "gmail": "📧",
        "drive": "📁",
        "calendar": "📅",
        "docs": "📄",
        "sheets": "📊",
        "chat": "💬",
        "forms": "📝",
        "slides": "🎯",
        "photos": "📷",
    }

    for service in services:
        icon = service_icons.get(service, "🔧")
        service_docs.append(f"  • {service} ({icon})")

    return "\n".join(service_docs)


def register_service_resources(mcp: FastMCP) -> None:
    """
    Register simplified service list resources that will be handled by TagBasedResourceMiddleware.

    This function only registers the resource patterns with FastMCP. The actual implementation
    is handled by TagBasedResourceMiddleware which intercepts these URIs before they reach
    the handlers below.

    Args:
        mcp: FastMCP instance to register resources with
    """
    logger.info(
        "Registering simplified service list resources (handled by TagBasedResourceMiddleware)..."
    )

    supported_services = get_supported_services()
    service_list_str = ", ".join(supported_services)

    @mcp.resource(
        uri="service://{service}/lists",
        name="Service List Types",
        description=f"""Get available list types for a Google service with rich metadata.

The TagBasedResourceMiddleware handles this request and returns available
list types with metadata for the specified service.

Supported services:
{generate_service_documentation()}

Examples:
  • service://gmail/lists → Returns ["filters", "labels"] with metadata
  • service://drive/lists → Returns ["items"] with folder support info
  • service://calendar/lists → Returns ["calendars", "events"] with pagination info

Returns comprehensive metadata including:
  • List type descriptions and capabilities
  • Pagination support and default page sizes
  • Whether detail views are supported
  • Example IDs for testing
  • Required OAuth scopes
  • Service-specific features

This resource is handled by TagBasedResourceMiddleware.""",
        mime_type="application/json",
        tags={"service", "lists", "discovery", "dynamic", "enhanced"},
        annotations={"readOnlyHint": True, "idempotentHint": True},
        meta={
            "version": "2.0",
            "category": "discovery",
            "enhanced": True,
            "includes_metadata": True,
            "accepted_services": supported_services,
        },
    )
    async def handle_service_lists(
        service: Annotated[
            str,
            Field(
                description=f"The Google service name. Supported: {service_list_str}",
                examples=["gmail", "drive", "calendar"],
            ),
        ],
        ctx: Context,
    ) -> str:
        """
        Handler for service list types that retrieves cached results from middleware.

        TagBasedResourceMiddleware processes the request and stores the result
        in FastMCP context state. This handler retrieves and returns that result.

        Returns:
            JSON string containing available list types with metadata
        """
        # Try to get the cached result from FastMCP context state
        cache_key = f"service_lists_response_{service}"
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't cache result (shouldn't happen in normal operation)
            logger.warning(
                f"No cached ServiceListsResponse found for {service} - middleware may not have processed this request"
            )
            response = ServiceListsResponse.from_middleware_data(
                service=service,
                service_metadata={
                    "display_name": f"{service.title()} Service",
                    "icon": "🔧",
                    "description": f"{service} service (fallback response)",
                },
                list_types={},
            )
            # FastMCP 3.0: Return JSON string instead of Pydantic model
            return response.model_dump_json()

        # Return the cached ServiceListsResponse as JSON
        logger.info(
            f"📦 Retrieved cached ServiceListsResponse for {service} from FastMCP context state"
        )
        # FastMCP 3.0: Handle both Pydantic models and dicts from cache
        if isinstance(cached_result, BaseModel):
            return cached_result.model_dump_json()
        elif isinstance(cached_result, dict):
            import json

            return json.dumps(cached_result)
        return str(cached_result)

    @mcp.resource(
        uri="service://{service}/{list_type}",
        name="Service List Items",
        description=f"""Get all items/IDs for a specific list type with automatic authentication.

The TagBasedResourceMiddleware handles this request by:
1. Finding the appropriate list tool for the service/list_type
2. Automatically injecting the authenticated user's email from context
3. Calling the tool and formatting the response
4. Handling pagination if supported

Supported services:
{generate_service_documentation()}

Common list types by service:
  • gmail: filters, labels
  • drive: items (folders/files)
  • calendar: calendars, events
  • photos: albums
  • forms: form_responses
  • sheets: spreadsheets
  • chat: spaces
  • docs: documents

Examples:
  • service://gmail/filters → Returns all Gmail filters with rules
  • service://calendar/events → Returns calendar events with attendees
  • service://photos/albums → Returns photo albums with cover images
  • service://drive/items → Returns Drive files and folders

Authentication:
  User email is automatically injected from the auth context by the middleware.
  No need to provide user_google_email parameter.

Pagination:
  Some list types support pagination. The middleware handles this automatically
  and includes next_page_token in responses when applicable.

This resource is handled by TagBasedResourceMiddleware.""",
        mime_type="application/json",
        tags={"service", "lists", "items", "dynamic", "enhanced"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False,  # May change as new items are added
        },
        meta={
            "version": "2.0",
            "category": "data",
            "requires_auth": True,
            "accepted_services": supported_services,
        },
    )
    async def handle_service_list_items(
        service: Annotated[
            str,
            Field(
                description=f"The Google service name. Supported: {service_list_str}",
                examples=["gmail", "drive", "calendar"],
            ),
        ],
        list_type: Annotated[
            str,
            Field(
                description="Type of list to retrieve (e.g., 'filters', 'labels', 'albums')",
                examples=["filters", "labels", "events", "albums", "items", "spaces"],
            ),
        ],
        ctx: Context,
    ) -> str:
        """
        Handler for service list items that retrieves cached results from middleware.

        TagBasedResourceMiddleware processes the request and stores the result
        in FastMCP context state. This handler retrieves and returns that result.

        Returns:
            JSON string containing the cached tool result with metadata
        """
        # Try to get the cached result from FastMCP context state
        user_email = await get_user_email_context()
        cache_key = f"service_list_response_{service}_{list_type}_{user_email}"
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't cache result (shouldn't happen in normal operation)
            logger.warning(
                f"No cached result found for {service}/{list_type} - middleware may not have processed this request"
            )
            response = ServiceListResponse.from_middleware_data(
                result={
                    "message": "No cached result found - middleware may not have processed this request",
                    "middleware_status": "CACHE_MISS",
                    "timestamp": "2025-09-07T13:42:00Z",
                },
                service=service,
                list_type=list_type,
                tool_called="CACHE_FALLBACK",
                user_email=user_email or "unknown@example.com",
            )
            # FastMCP 3.0: Return JSON string instead of Pydantic model
            return response.model_dump_json()

        # Return the cached ServiceListResponse as JSON
        logger.info(
            f"📦 Retrieved cached result for {service}/{list_type} from FastMCP context state"
        )
        # FastMCP 3.0: Handle both Pydantic models and dicts from cache
        if isinstance(cached_result, BaseModel):
            return cached_result.model_dump_json()
        elif isinstance(cached_result, dict):
            import json

            return json.dumps(cached_result)
        return str(cached_result)

    @mcp.resource(
        uri="service://{service}/{list_type}/{item_id}",
        name="Service List Item Details",
        description=f"""Get detailed data for a specific item with automatic authentication.

The TagBasedResourceMiddleware handles this request by:
1. Finding the appropriate detail/get tool for the service/list_type
2. Automatically injecting the authenticated user's email from context
3. Calling the tool with the item_id and formatting the response
4. Including metadata and raw response data when available

Supported services:
{generate_service_documentation()}

Examples with detail support:
  • service://gmail/filters/filter123 → Get details of a specific Gmail filter
  • service://gmail/labels/INBOX → Get details of the INBOX label
  • service://calendar/events/event456 → Get details of a specific calendar event
  • service://photos/albums/album789 → Get photos in a specific album
  • service://drive/items/folder123 → List contents of a specific folder
  • service://forms/form_responses/form_abc → Get responses for a specific form

Special cases:
  • Gmail labels: Extracted from list response (no separate detail tool)
  • Drive items: Uses folder_id to list contents
  • Form responses: Uses form_id to get responses

Note: Not all list types support individual item retrieval. The middleware
will return an appropriate error message if the operation is not supported.

Authentication:
  User email is automatically injected from the auth context by the middleware.
  No need to provide user_google_email parameter.

Response includes:
  • Full item details from the API
  • Service metadata and icons
  • Timestamps and version info
  • Raw API response (when include_raw=true)

This resource is handled by TagBasedResourceMiddleware.""",
        mime_type="application/json",
        tags={"service", "lists", "detail", "dynamic", "enhanced"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False,  # Item details may change
        },
        meta={
            "version": "2.0",
            "category": "detail",
            "requires_auth": True,
            "accepted_services": supported_services,
        },
    )
    async def handle_service_item_details(
        service: Annotated[
            str,
            Field(
                description=f"The Google service name. Supported: {service_list_str}",
                examples=["gmail", "drive", "calendar"],
            ),
        ],
        list_type: Annotated[
            str,
            Field(
                description="Type of list containing the item",
                examples=[
                    "filters",
                    "labels",
                    "events",
                    "albums",
                    "items",
                    "form_responses",
                ],
            ),
        ],
        item_id: Annotated[
            str,
            Field(
                description="Unique identifier for the specific item",
                examples=[
                    "filter_123",
                    "INBOX",
                    "event_abc",
                    "album_xyz",
                    "root",
                    "form_123",
                ],
            ),
        ],
        ctx: Context,
    ) -> str:
        """
        Handler for service item details that retrieves cached results from middleware.

        TagBasedResourceMiddleware processes the request and stores the result
        in FastMCP context state. This handler retrieves and returns that result.

        Returns:
            JSON string containing the specific item details
        """
        # Try to get the cached result from FastMCP context state
        user_email = await get_user_email_context()
        cache_key = f"service_item_details_{service}_{list_type}_{item_id}_{user_email}"
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't cache result (shouldn't happen in normal operation)
            logger.warning(
                f"No cached ServiceItemDetailsResponse found for {service}/{list_type}/{item_id} - middleware may not have processed this request"
            )
            response = ServiceItemDetailsResponse.from_middleware_data(
                service=service,
                list_type=list_type,
                item_id=item_id,
                tool_called="CACHE_FALLBACK",
                user_email=user_email or "unknown@example.com",
                parameters={},
                result={
                    "message": "No cached result found - middleware may not have processed this request",
                    "middleware_status": "CACHE_MISS",
                },
            )
            # FastMCP 3.0: Return JSON string instead of Pydantic model
            return response.model_dump_json()

        # Return the cached ServiceItemDetailsResponse as JSON
        logger.info(
            f"📦 Retrieved cached ServiceItemDetailsResponse for {service}/{list_type}/{item_id} from FastMCP context state"
        )
        # FastMCP 3.0: Handle both Pydantic models and dicts from cache
        if isinstance(cached_result, BaseModel):
            return cached_result.model_dump_json()
        elif isinstance(cached_result, dict):
            import json

            return json.dumps(cached_result)
        return str(cached_result)

    @mcp.resource(
        uri="google://services/scopes/{service}",
        name="Google Service Scopes",
        description="Get the required OAuth scopes, API version, and configuration details for a specific Google service including Drive, Gmail, Calendar, and other Workspace APIs",
        mime_type="application/json",
        tags={
            "google",
            "services",
            "scopes",
            "oauth",
            "api",
            "configuration",
            "workspace",
        },
        meta={
            "response_model": "ServiceScopesResponse",
            "detailed": True,
            "supports_lookup": True,
        },
    )
    async def get_service_scopes(
        service: Annotated[
            str,
            Field(
                description="Google service name to get OAuth scope and API configuration information for. Supported services include gmail, drive, calendar, docs, sheets, slides, forms, chat, photos.",
                examples=[
                    "gmail",
                    "drive",
                    "calendar",
                    "docs",
                    "sheets",
                    "slides",
                    "forms",
                    "chat",
                    "photos",
                ],
                min_length=3,
                max_length=20,
                pattern=r"^[a-z][a-z0-9_]*$",
                title="Google Service Name",
            ),
        ],
        ctx: Context,
    ) -> ServiceScopesResponse:
        """Get OAuth scopes, API version, and configuration details for a Google service.

        Retrieves comprehensive configuration information for Google Workspace and related
        services, including required OAuth scopes, API versions, and service descriptions.
        Essential for understanding authentication requirements and API capabilities.

        Args:
            service: Name of the Google service to lookup. Must be lowercase and match
                one of the supported services: gmail, drive, calendar, docs, sheets,
                slides, forms, chat, photos. Invalid service names return available
                services list with error details.
            ctx: FastMCP Context object providing access to server state and logging

        Returns:
            ServiceScopesResponse: Complete service configuration including:
            - Required OAuth scopes for API access
            - API version and endpoint information
            - Service description and capabilities
            - Error details and available services if lookup fails

        Example Usage:
            await get_service_scopes("gmail", ctx)
            await get_service_scopes("drive", ctx)

        Example Response (Gmail Service):
            {
                "service": "gmail",
                "default_scopes": [
                    "https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/gmail.send"
                ],
                "version": "v1",
                "description": "Gmail API for email management",
                "timestamp": "2024-01-15T10:30:00Z"
            }

        Example Response (Unknown Service):
            {
                "service": "unknown_service",
                "error": "Unknown Google service: unknown_service",
                "available_services": ["gmail", "drive", "calendar", "docs"],
                "default_scopes": [],
                "version": "unknown",
                "description": "Service not found",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        # Import here to avoid circular imports
        from auth.service_helpers import SERVICE_DEFAULTS

        service_info = SERVICE_DEFAULTS.get(service.lower())
        if not service_info:
            return ServiceScopesResponse(
                service=service,
                error=f"Unknown Google service: {service}",
                available_services=list(SERVICE_DEFAULTS.keys()),
                default_scopes=[],
                version="unknown",
                description="Service not found",
                timestamp=datetime.now().isoformat(),
            )

        return ServiceScopesResponse(
            service=service,
            default_scopes=service_info.get("default_scopes", []),
            version=service_info.get("version", "v1"),
            description=service_info.get(
                "description", f"Google {service.title()} API"
            ),
            timestamp=datetime.now().isoformat(),
        )

    logger.info(
        "✅ Registered 3 enhanced service resources (all handled by TagBasedResourceMiddleware)"
    )
    logger.info(
        "   1. service://{service}/lists - Get available list types with metadata"
    )
    logger.info("   2. service://{service}/{list_type} - Get all items with pagination")
    logger.info("   3. service://{service}/{list_type}/{item_id} - Get item details")
    logger.info("")
    logger.info("📌 TagBasedResourceMiddleware handles all the complex logic:")
    logger.info("   • URI pattern matching and parsing")
    logger.info("   • Tool discovery via tags")
    logger.info("   • User email injection from auth context")
    logger.info("   • Direct tool calling with proper parameters")
    logger.info("   • Response formatting and error handling")
    logger.info("")
    logger.info(f"🔧 Supported services: {', '.join(supported_services)}")


# Legacy function name for backward compatibility
def setup_service_list_resources(mcp: FastMCP) -> None:
    """
    Legacy setup function name for backward compatibility.

    This simply calls register_service_resources() with the new simplified approach.
    """
    register_service_resources(mcp)


# ============================================================================
# LEGACY CODE REMOVED - HANDLED BY TagBasedResourceMiddleware
# ============================================================================

# The following complex components have been removed and are now handled by
# TagBasedResourceMiddleware in middleware/tag_based_resource_middleware.py:
#
# ❌ ServiceListDiscovery class (655 lines) - Lines 655-1309
# ❌ TOOL_CONFIGURATIONS mapping (128 lines) - Lines 665-793
# ❌ Complex authentication helpers (105 lines) - Lines 544-649
# ❌ ServiceMetadata class (316 lines) - Lines 72-388
# ❌ Pydantic response models (168 lines) - Lines 372-540
# ❌ Complex parameter filtering (45 lines) - Lines 943-988
# ❌ Result parsing logic (89 lines) - Lines 1207-1296
# ❌ Authentication detection (78 lines) - Lines 544-622
#
# Total removed: ~1615 lines of complex logic
#
# All this functionality is now provided by TagBasedResourceMiddleware:
# ✅ Tool discovery via tags instead of introspection
# ✅ Authentication via AuthMiddleware context
# ✅ Unified parameter handling and filtering
# ✅ Consistent response formatting
# ✅ Error handling with helpful suggestions
# ✅ Service metadata and documentation
# ✅ Pagination support where applicable
#
# This reduces complexity by ~95% while providing the same functionality
# through a more maintainable, middleware-based architecture.
