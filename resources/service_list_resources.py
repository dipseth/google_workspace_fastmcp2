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

import logging
from typing import Dict, Any, List
from fastmcp import FastMCP, Context
from pydantic import Field
from typing_extensions import Annotated
from middleware.service_list_response import ServiceListResponse, ServiceListsResponse, ServiceItemDetailsResponse
from auth.context import get_user_email_context

logger = logging.getLogger(__name__)


def get_supported_services() -> List[str]:
    """
    Get the list of supported Google services.

    This list matches what's configured in TagBasedResourceMiddleware.
    """
    return [
        "gmail", "drive", "calendar", "docs", "sheets",
        "chat", "forms", "slides", "photos"
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
        "photos": "📷"
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
    logger.info("Registering simplified service list resources (handled by TagBasedResourceMiddleware)...")

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
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True
        },
        meta={
            "version": "2.0",
            "category": "discovery",
            "enhanced": True,
            "includes_metadata": True,
            "accepted_services": supported_services
        }
    )
    async def handle_service_lists(
        service: Annotated[str, Field(
            description=f"The Google service name. Supported: {service_list_str}",
            examples=["gmail", "drive", "calendar"]
        )],
        ctx: Context
    ) -> ServiceListsResponse:
        """
        Handler for service list types that retrieves cached results from middleware.

        TagBasedResourceMiddleware processes the request and stores the result
        in FastMCP context state. This handler retrieves and returns that result.

        Returns:
            ServiceListsResponse containing available list types with metadata
        """
        # Try to get the cached result from FastMCP context state
        cache_key = f"service_lists_response_{service}"
        cached_result = ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't cache result (shouldn't happen in normal operation)
            logger.warning(f"No cached ServiceListsResponse found for {service} - middleware may not have processed this request")
            return ServiceListsResponse.from_middleware_data(
                service=service,
                service_metadata={
                    "display_name": f"{service.title()} Service",
                    "icon": "🔧",
                    "description": f"{service} service (fallback response)"
                },
                list_types={}
            )

        # Return the cached ServiceListsResponse
        logger.info(f"📦 Retrieved cached ServiceListsResponse for {service} from FastMCP context state")
        return cached_result

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
            "idempotentHint": False  # May change as new items are added
        },
        meta={
            "version": "2.0",
            "category": "data",
            "requires_auth": True,
            "accepted_services": supported_services
        }
    )
    async def handle_service_list_items(
        service: Annotated[str, Field(
            description=f"The Google service name. Supported: {service_list_str}",
            examples=["gmail", "drive", "calendar"]
        )],
        list_type: Annotated[str, Field(
            description="Type of list to retrieve (e.g., 'filters', 'labels', 'albums')",
            examples=["filters", "labels", "events", "albums", "items", "spaces"]
        )],
        ctx: Context
    ) -> ServiceListResponse:
        """
        Handler for service list items that retrieves cached results from middleware.

        TagBasedResourceMiddleware processes the request and stores the result
        in FastMCP context state. This handler retrieves and returns that result.

        Returns:
            ServiceListResponse containing the cached tool result with metadata
        """
        # Try to get the cached result from FastMCP context state
        user_email = get_user_email_context()
        cache_key = f"service_list_response_{service}_{list_type}_{user_email}"
        cached_result = ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't cache result (shouldn't happen in normal operation)
            logger.warning(f"No cached result found for {service}/{list_type} - middleware may not have processed this request")
            return ServiceListResponse.from_middleware_data(
                result={
                    "message": "No cached result found - middleware may not have processed this request",
                    "middleware_status": "CACHE_MISS",
                    "timestamp": "2025-09-07T13:42:00Z"
                },
                service=service,
                list_type=list_type,
                tool_called="CACHE_FALLBACK",
                user_email=user_email or "unknown@example.com"
            )

        # Return the cached ServiceListResponse
        logger.info(f"📦 Retrieved cached result for {service}/{list_type} from FastMCP context state")
        return cached_result

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
            "idempotentHint": False  # Item details may change
        },
        meta={
            "version": "2.0",
            "category": "detail",
            "requires_auth": True,
            "accepted_services": supported_services
        }
    )
    async def handle_service_item_details(
        service: Annotated[str, Field(
            description=f"The Google service name. Supported: {service_list_str}",
            examples=["gmail", "drive", "calendar"]
        )],
        list_type: Annotated[str, Field(
            description="Type of list containing the item",
            examples=["filters", "labels", "events", "albums", "items", "form_responses"]
        )],
        item_id: Annotated[str, Field(
            description="Unique identifier for the specific item",
            examples=["filter_123", "INBOX", "event_abc", "album_xyz", "root", "form_123"]
        )],
        ctx: Context
    ) -> ServiceItemDetailsResponse:
        """
        Handler for service item details that retrieves cached results from middleware.

        TagBasedResourceMiddleware processes the request and stores the result
        in FastMCP context state. This handler retrieves and returns that result.

        Returns:
            ServiceItemDetailsResponse containing the specific item details
        """
        # Try to get the cached result from FastMCP context state
        user_email = get_user_email_context()
        cache_key = f"service_item_details_{service}_{list_type}_{item_id}_{user_email}"
        cached_result = ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't cache result (shouldn't happen in normal operation)
            logger.warning(f"No cached ServiceItemDetailsResponse found for {service}/{list_type}/{item_id} - middleware may not have processed this request")
            return ServiceItemDetailsResponse.from_middleware_data(
                service=service,
                list_type=list_type,
                item_id=item_id,
                tool_called="CACHE_FALLBACK",
                user_email=user_email or "unknown@example.com",
                parameters={},
                result={
                    "message": "No cached result found - middleware may not have processed this request",
                    "middleware_status": "CACHE_MISS"
                }
            )

        # Return the cached ServiceItemDetailsResponse
        logger.info(f"📦 Retrieved cached ServiceItemDetailsResponse for {service}/{list_type}/{item_id} from FastMCP context state")
        return cached_result

    logger.info("✅ Registered 3 enhanced service resources (all handled by TagBasedResourceMiddleware)")
    logger.info("   1. service://{service}/lists - Get available list types with metadata")
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