"""
Service Recent Resources for FastMCP2 Google Workspace Platform.

This module provides resources for accessing recent files from Google Drive-based services
including Drive, Docs, Sheets, Slides, and Forms using a unified Drive query approach.

All Google Workspace documents are stored in Drive, so we use search_drive_files with
simple type: syntax queries to get recent items for each service.

Updated to use the newer, simpler Google Drive search syntax:
- type:docs (instead of complex MIME type filters)
- type:sheets
- type:slides
- type:forms
"""

import asyncio
from datetime import datetime, timedelta

from fastmcp import Context, FastMCP
from pydantic import Field
from typing_extensions import Annotated, Any, Dict, List, Literal, Optional

from auth.context import get_user_email_context

# Import centralized scope registry for dynamic service discovery
from auth.scope_registry import ScopeRegistry
from config.enhanced_logging import setup_logger
from drive.drive_enums import MimeTypeFilter
from drive.drive_search_types import DriveSearchResponse

# Import the search_drive_files tool function directly
# Resources call tools directly as async functions, not using forward()
# (forward() is only for creating transformed tools)
from drive.drive_tools import search_drive_files

logger = setup_logger()


# Dynamic type definition based on scope registry - builds supported services list
def _get_supported_services() -> List[str]:
    """Get list of supported services from scope registry."""
    # Include drive-based services and photos (which has its own list tools)
    drive_based_services = ["drive", "docs", "sheets", "slides", "forms"]

    # Add services from scope registry that have list tools
    registry_services = list(ScopeRegistry.SERVICE_METADATA.keys())

    # For now, focus on drive-based services + photos
    # Photos will need special handling since it's not drive-based
    supported = drive_based_services + ["photos"]

    return supported


# Dynamic supported service type
SupportedService = Literal["drive", "docs", "sheets", "slides", "forms", "photos"]


# Build service info dynamically from scope registry where possible
def _build_service_info() -> Dict[str, Dict[str, Any]]:
    """Build service info dynamically from scope registry and custom configs."""
    service_info = {}

    # Drive-based services with their MIME filters
    drive_services = {
        "drive": {
            "name": "Google Drive",
            "icon": "📁",
            "description": "Recent files from Google Drive (all types)",
            "mime_filter": None,  # No specific MIME filter for all files
            "exclude_folders": True,  # But we typically want to exclude folders
        },
        "docs": {
            "name": "Google Docs",
            "icon": "📄",
            "description": "Recent Google Docs documents",
            "mime_filter": MimeTypeFilter.GOOGLE_DOCS,
        },
        "sheets": {
            "name": "Google Sheets",
            "icon": "📊",
            "description": "Recent Google Sheets spreadsheets",
            "mime_filter": MimeTypeFilter.GOOGLE_SHEETS,
        },
        "slides": {
            "name": "Google Slides",
            "icon": "🎯",
            "description": "Recent Google Slides presentations",
            "mime_filter": MimeTypeFilter.GOOGLE_SLIDES,
        },
        "forms": {
            "name": "Google Forms",
            "icon": "📝",
            "description": "Recent Google Forms",
            "mime_filter": MimeTypeFilter.GOOGLE_FORMS,
        },
    }

    # Get metadata from scope registry where available
    for service_name, service_config in drive_services.items():
        if service_name in ScopeRegistry.SERVICE_METADATA:
            registry_meta = ScopeRegistry.SERVICE_METADATA[service_name]
            service_config["name"] = registry_meta.name
            service_config["icon"] = registry_meta.icon
            service_config["description"] = registry_meta.description

        service_info[service_name] = service_config

    # Add photos service - not drive-based, has its own list tools
    if "photos" in ScopeRegistry.SERVICE_METADATA:
        photos_meta = ScopeRegistry.SERVICE_METADATA["photos"]
        service_info["photos"] = {
            "name": photos_meta.name,
            "icon": photos_meta.icon,
            "description": f"Recent items from {photos_meta.name} (via photos tools)",
            "mime_filter": None,  # Photos uses its own APIs, not Drive
            "is_photos_service": True,  # Special flag for photos handling
        }

    return service_info


# Build service info dynamically
SERVICE_INFO = _build_service_info()


def _get_authenticated_user_email(ctx: Context) -> Optional[str]:
    """Get authenticated user email from context."""
    return get_user_email_context()


def _create_auth_error_response(service: str) -> Dict[str, Any]:
    """Create standardized auth error response."""
    return {
        "error": "No authenticated user found in current session",
        "service": service,
        "suggestion": "Use start_google_auth tool to authenticate first",
        "timestamp": datetime.now().isoformat(),
    }


def _generate_date_query(days_back: int = 30) -> str:
    """Generate date string for Drive queries."""
    cutoff_date = datetime.now() - timedelta(days=days_back)
    return cutoff_date.strftime("%Y-%m-%dT%H:%M:%S")


async def _get_recent_items(
    service: str,
    user_email: str,
    days_back: int = 30,
    page_size: int = 20,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Unified function to get recent items for any service (Drive-based or Photos).

    This function calls the appropriate tools directly and processes their structured responses.
    Note: Resources call tools as regular async functions - forward() is only used when creating
    transformed tools, not when resources need to use existing tools.

    Args:
        service: Service name (drive, docs, sheets, slides, forms, photos)
        user_email: Authenticated user email
        days_back: Number of days back to search (default: 30)
        page_size: Number of items to return (default: 20)
        ctx: FastMCP Context for tool access

    Returns:
        Dictionary with recent items and metadata from the tool's structured response
    """
    if service not in SERVICE_INFO:
        return {
            "error": f"Unsupported service: {service}",
            "supported_services": list(SERVICE_INFO.keys()),
        }

    service_info = SERVICE_INFO[service]

    # Special handling for photos service (not Drive-based)
    if service_info.get("is_photos_service"):
        return await _get_recent_photos_items(
            service, service_info, user_email, page_size, ctx
        )

    # Drive-based services handling
    date_str = _generate_date_query(days_back)
    date_query = f"modifiedTime > '{date_str}'"

    # Get the MIME type filter for the service
    mime_filter = service_info.get("mime_filter")

    # Special handling for drive service
    if service == "drive" and service_info.get("exclude_folders"):
        mime_filter = MimeTypeFilter.EXCLUDE_FOLDERS

    logger.debug(
        f"📊 Searching {service} with MIME filter: {mime_filter}, date query: {date_query}"
    )

    try:
        # Call the search_drive_files tool with the new enum-based approach
        # Using both mime_type parameter for type filtering and query for date filtering
        result: DriveSearchResponse = await search_drive_files(
            user_google_email=user_email,
            query=date_query,  # Just the date filter, no complex MIME type strings
            mime_type=mime_filter,  # Clean enum-based type filtering
            page_size=page_size,
        )

        # Handle the structured response - it's a TypedDict (returns dict, not object)
        logger.debug(
            f"✅ Tool returned {result.get('resultCount', 0)} results for {service}"
        )

        # Check for errors in the structured response
        if result.get("error"):
            return {
                "error": result["error"],
                "service": service,
                "query_used": date_query,
                "mime_filter_used": mime_filter.value if mime_filter else None,
                "timestamp": datetime.now().isoformat(),
            }

        # Extract files from the structured response
        files = result.get("results", [])

        # Enhance each file with service metadata
        enhanced_files = []
        for file_info in files:
            # Convert from DriveFileInfo to our enhanced format
            enhanced_file = {
                "id": file_info.get("id"),
                "name": file_info.get("name"),
                "mimeType": file_info.get("mimeType"),
                "size": file_info.get("size"),
                "webViewLink": file_info.get("webViewLink"),
                "modifiedTime": file_info.get("modifiedTime"),
                "createdTime": file_info.get("createdTime"),
                "service": service,
                "service_name": service_info["name"],
                "service_icon": service_info["icon"],
                "retrieved_at": datetime.now().isoformat(),
            }
            enhanced_files.append(enhanced_file)

        return {
            "service": service,
            "service_name": service_info["name"],
            "service_icon": service_info["icon"],
            "description": service_info["description"],
            "query_used": result.get("processedQuery", date_query),
            "query_type": result.get("queryType", "structured"),
            "mime_filter": mime_filter.value if mime_filter else None,
            "days_back": days_back,
            "total_count": len(enhanced_files),
            "files": enhanced_files,
            "metadata": {
                "user_email": user_email,
                "search_date_from": date_str,
                "search_date_to": datetime.now().isoformat(),
                "type_filter": service,
                "search_scope": result.get("searchScope", "user"),
                "next_page_token": result.get("nextPageToken"),
            },
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting recent {service} items: {e}")
        return {
            "error": f"Failed to retrieve recent {service} items: {str(e)}",
            "service": service,
            "query_used": date_query,
            "mime_filter": mime_filter.value if mime_filter else None,
            "timestamp": datetime.now().isoformat(),
        }


async def _get_recent_photos_items(
    service: str,
    service_info: Dict[str, Any],
    user_email: str,
    page_size: int = 20,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Get recent photos items using photos-specific tools via FastMCP context.

    Args:
        service: Service name ("photos")
        service_info: Service metadata dict
        user_email: Authenticated user email
        page_size: Number of items to return
        ctx: FastMCP Context for tool access

    Returns:
        Dictionary with recent photos items and metadata
    """
    try:
        # Use FastMCP context to find tools dynamically (following middleware pattern)
        if not ctx or not hasattr(ctx, "fastmcp") or not ctx.fastmcp:
            return {
                "error": "FastMCP context not available for photos tool discovery",
                "service": service,
                "timestamp": datetime.now().isoformat(),
            }

        # Access the tool registry directly via _tool_manager (following middleware pattern)
        mcp_server = ctx.fastmcp
        if not hasattr(mcp_server, "_tool_manager") or not hasattr(
            mcp_server._tool_manager, "_tools"
        ):
            return {
                "error": "Cannot access tool registry from FastMCP server",
                "service": service,
                "timestamp": datetime.now().isoformat(),
            }

        tools_dict = mcp_server._tool_manager._tools
        tool_name = "list_photos_albums"

        if tool_name not in tools_dict:
            return {
                "error": f"Tool '{tool_name}' not found in registry",
                "available_tools": [
                    name for name in tools_dict.keys() if "photos" in name.lower()
                ],
                "service": service,
                "timestamp": datetime.now().isoformat(),
            }

        logger.debug(
            f"📷 Getting recent {service} albums via {tool_name} from tool registry"
        )

        # Get the tool and call it (following middleware pattern)
        tool_instance = tools_dict[tool_name]

        # Get the actual callable function from the tool
        if hasattr(tool_instance, "fn"):
            tool_func = tool_instance.fn
        elif hasattr(tool_instance, "func"):
            tool_func = tool_instance.func
        elif hasattr(tool_instance, "__call__"):
            tool_func = tool_instance
        else:
            return {
                "error": f"Tool '{tool_name}' is not callable",
                "service": service,
                "timestamp": datetime.now().isoformat(),
            }

        # Call the tool with parameters
        tool_params = {
            "user_google_email": user_email,
            "max_results": min(page_size, 50),  # Photos API max is 50
        }

        if asyncio.iscoroutinefunction(tool_func):
            albums_result = await tool_func(**tool_params)
        else:
            albums_result = tool_func(**tool_params)

        # Handle the structured response
        if hasattr(albums_result, "error") and albums_result.error:
            return {
                "error": albums_result.error,
                "service": service,
                "tool_used": tool_name,
                "timestamp": datetime.now().isoformat(),
            }

        # Extract albums from the structured response
        albums = (
            getattr(albums_result, "albums", [])
            if hasattr(albums_result, "albums")
            else []
        )

        # Convert albums to enhanced format similar to files
        enhanced_items = []
        for album in albums:
            if isinstance(album, dict):
                enhanced_item = {
                    "id": album.get("id"),
                    "name": album.get("title", "Untitled Album"),
                    "type": "album",
                    "itemCount": album.get("mediaItemsCount", 0),
                    "webViewLink": album.get("productUrl"),
                    "coverPhotoUrl": album.get("coverPhotoBaseUrl"),
                    "service": service,
                    "service_name": service_info["name"],
                    "service_icon": service_info["icon"],
                    "retrieved_at": datetime.now().isoformat(),
                }
                enhanced_items.append(enhanced_item)

        return {
            "service": service,
            "service_name": service_info["name"],
            "service_icon": service_info["icon"],
            "description": service_info["description"],
            "tool_used": tool_name,
            "query_type": "photos_api",
            "total_count": len(enhanced_items),
            "files": enhanced_items,  # Keep same key name for consistency
            "metadata": {
                "user_email": user_email,
                "type_filter": service,
                "search_scope": "photos_library",
                "item_type": "albums",
            },
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting recent {service} items: {e}")
        return {
            "error": f"Failed to retrieve recent {service} items: {str(e)}",
            "service": service,
            "tool_used": tool_name if "tool_name" in locals() else "unknown",
            "timestamp": datetime.now().isoformat(),
        }


def setup_service_recent_resources(mcp: FastMCP) -> None:
    """
    Setup service recent resources for all Drive-based services.

    These resources call the search_drive_files tool directly to get recent items.
    Resources are data providers that USE tools - they don't transform them.
    """

    logger.debug(
        "🔧 SETUP: Setting up service recent resources that call search_drive_files tool"
    )

    @mcp.resource(
        uri="recent://{service}",
        name="Recent Service Items",
        description="""Get recent items from Google Workspace services.

Supported services:
  • drive (📁): All recent Drive files
  • docs (📄): Recent Google Docs documents
  • sheets (📊): Recent Google Sheets spreadsheets
  • slides (🎯): Recent Google Slides presentations
  • forms (📝): Recent Google Forms
  • photos (📷): Recent Google Photos albums

Drive-based services use Google Drive search with MIME type filters.
Photos service uses Google Photos API to list recent albums.
Returns items modified within the last 30 days by default.""",
        mime_type="application/json",
        tags={"service", "recent", "drive", "photos", "dynamic", "unified"},
    )
    async def get_service_recent_items(
        ctx: Context,
        service: Annotated[
            SupportedService,
            Field(
                description="Service name: drive, docs, sheets, slides, forms, or photos"
            ),
        ],
    ) -> Dict[str, Any]:
        """Get recent items for a specific Drive-based service."""

        # Validate service parameter
        if service.lower() not in SERVICE_INFO:
            return {
                "error": f"Unsupported service: {service}",
                "supported_services": list(SERVICE_INFO.keys()),
                "suggestion": "Use one of: drive, docs, sheets, slides, forms, photos",
                "timestamp": datetime.now().isoformat(),
            }

        # Get authenticated user
        user_email = _get_authenticated_user_email(ctx)
        if not user_email:
            return _create_auth_error_response(service.lower())

        # Get recent items using unified function
        return await _get_recent_items(service.lower(), user_email, ctx=ctx)

    @mcp.resource(
        uri="recent://{service}/{days}",
        name="Recent Service Items (Custom Days)",
        description="""Get recent items from Google Workspace services with custom day range.

Supported services: drive, docs, sheets, slides, forms, photos

Specify number of days back to search (1-90 days).
Note: Photos service returns albums (day range affects Drive services only).""",
        mime_type="application/json",
        tags={"service", "recent", "drive", "photos", "dynamic", "custom-range"},
    )
    async def get_service_recent_items_custom_days(
        ctx: Context,
        service: Annotated[
            SupportedService,
            Field(
                description="Service name: drive, docs, sheets, slides, forms, or photos"
            ),
        ],
        days: Annotated[
            int, Field(description="Number of days back to search (1-90)", ge=1, le=90)
        ],
    ) -> Dict[str, Any]:
        """Get recent items for a specific service with custom day range."""

        # Validate service parameter
        if service.lower() not in SERVICE_INFO:
            return {
                "error": f"Unsupported service: {service}",
                "supported_services": list(SERVICE_INFO.keys()),
                "suggestion": "Use one of: drive, docs, sheets, slides, forms, photos",
                "timestamp": datetime.now().isoformat(),
            }

        # Get authenticated user
        user_email = _get_authenticated_user_email(ctx)
        if not user_email:
            return _create_auth_error_response(service.lower())

        # Get recent items with custom day range
        return await _get_recent_items(
            service.lower(), user_email, days_back=days, ctx=ctx
        )

    @mcp.resource(
        uri="recent://all",
        name="All Recent Workspace Items",
        description="Get recent items from all Google Workspace services (Drive, Docs, Sheets, Slides, Forms, Photos) in a unified view.",
        mime_type="application/json",
        tags={"service", "recent", "all", "workspace", "unified"},
    )
    async def get_all_recent_workspace_items(ctx: Context) -> Dict[str, Any]:
        """Get recent items from all supported Drive-based services."""

        # Get authenticated user
        user_email = _get_authenticated_user_email(ctx)
        if not user_email:
            return _create_auth_error_response("all")

        # Get recent items from all services
        all_results = {}
        total_items = 0

        for service in SERVICE_INFO.keys():
            try:
                service_result = await _get_recent_items(
                    service, user_email, days_back=30, page_size=10, ctx=ctx
                )
                all_results[service] = service_result
                if "files" in service_result:
                    total_items += len(service_result["files"])
            except Exception as e:
                logger.error(f"Error getting recent items for {service}: {e}")
                all_results[service] = {
                    "error": f"Failed to get {service} items: {str(e)}",
                    "service": service,
                }

        return {
            "user_email": user_email,
            "total_items_across_services": total_items,
            "services": all_results,
            "summary": {
                service: {
                    "count": len(result.get("files", [])),
                    "service_name": result.get("service_name", service.title()),
                    "icon": result.get("service_icon", "📁"),
                }
                for service, result in all_results.items()
                if not result.get("error")
            },
            "timestamp": datetime.now().isoformat(),
        }

    logger.debug("✅ Service recent resources registered for Drive-based services")
    logger.debug(f"  Available services: {', '.join(SERVICE_INFO.keys())}")
    logger.debug(
        "  Resources call search_drive_files tool directly and return structured results"
    )
