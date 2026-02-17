"""
TagBasedResourceMiddleware for handling service list resources.

This middleware provides a simplified approach to service list resource handling by:
- Intercepting resource reads for service:// URIs
- Using direct tool registry access for tool discovery
- Automatically injecting user_email from AuthMiddleware context
- Providing consistent response formatting

URI Patterns:
- service://{service}/lists → Return available list types with metadata
- service://{service}/{list_type} → Call the appropriate list tool
- service://{service}/{list_type}/{id} → Get specific item details
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set

from fastmcp.server.middleware import Middleware, MiddlewareContext

from auth.context import get_user_email_context

# Import centralized scope registry for dynamic service metadata
from auth.scope_registry import ScopeRegistry

from .service_list_response import (
    ServiceErrorResponse,
    ServiceItemDetailsResponse,
    ServiceListResponse,
    ServiceListsResponse,
)


@dataclass
class CacheEntry:
    """Cache entry with TTL support."""

    data: Any
    timestamp: datetime
    ttl_seconds: int

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return datetime.now() - self.timestamp > timedelta(seconds=self.ttl_seconds)


from config.enhanced_logging import setup_logger

logger = setup_logger()


class TagBasedResourceMiddleware(Middleware):
    """
    Lightweight middleware for handling service:// resource URIs using tag-based tool discovery.

    This middleware simplifies service list resource handling by using tool tags to identify
    list tools and automatically injecting authentication context. It reduces complexity
    from the original 1715-line implementation to approximately 400 lines.

    Key Features:
    - URI pattern matching for service://{service}/{list_type?}/{id?}
    - Tag-based tool discovery using ["list", "service", "resource_type"] tags
    - Automatic user_email injection from AuthMiddleware context
    - Consistent response formatting with metadata
    - Graceful error handling
    - Caching mechanism to avoid redundant tool calls

    Supported URI Patterns:
    1. service://{service}/lists - Returns available list types for the service
    2. service://{service}/{list_type} - Returns all items for that list type
    3. service://{service}/{list_type}/{id} - Returns specific item details

    Examples:
    - service://gmail/lists → {"list_types": ["filters", "labels"], "metadata": {...}}
    - service://gmail/filters → Call list_gmail_filters with auto-injected user_email
    - service://gmail/filters/filter123 → Call get_gmail_filter with filter_id and user_email
    """

    # Regex pattern for parsing service:// URIs
    SERVICE_URI_PATTERN = re.compile(
        r"^service://(?P<service>[^/]+)(?:/(?P<list_type>[^/]+))?(?:/(?P<id>.+))?$"
    )

    # Service name mappings to handle both singular and plural forms
    SERVICE_NAME_MAPPINGS = {
        "photo": "photos",  # Handle photo -> photos
        "doc": "docs",  # Handle doc -> docs
        "sheet": "sheets",  # Handle sheet -> sheets
        "slide": "slides",  # Handle slide -> slides
        "form": "forms",  # Handle form -> forms
    }

    @classmethod
    def _build_service_metadata_from_registry(
        cls, available_tools: Set[str] = None
    ) -> Dict[str, Any]:
        """
        Build service metadata dynamically from the centralized scope registry.

        Args:
            available_tools: Set of available tool names to filter by

        Returns:
            Dictionary of service metadata built from ScopeRegistry
        """
        service_metadata = {}

        # Get all services from the centralized registry
        for service_name, service_meta in ScopeRegistry.SERVICE_METADATA.items():
            service_config = {
                "display_name": service_meta.name,
                "icon": service_meta.icon,
                "description": service_meta.description,
                "list_types": {},
            }

            # Build list_types based on available tools and known patterns
            if service_name == "gmail":
                service_config["list_types"] = {
                    "filters": {
                        "display_name": "Email Filters",
                        "description": "Automatic email filtering rules",
                        "list_tool": "list_gmail_filters",
                        "get_tool": "get_gmail_filter",
                        "id_field": "filter_id",
                    },
                    "labels": {
                        "display_name": "Email Labels",
                        "description": "Organizational labels and categories",
                        "list_tool": "list_gmail_labels",
                        "get_tool": None,
                        "id_field": "label_id",
                    },
                    "messages": {
                        "display_name": "Gmail Messages",
                        "description": "Email messages and conversations",
                        "list_tool": "search_gmail_messages",
                        "get_tool": "get_gmail_message_content",
                        "id_field": "message_id",
                    },
                }
            elif service_name == "drive":
                service_config["list_types"] = {
                    "items": {
                        "display_name": "Drive Files",
                        "description": "Files and folders in Google Drive",
                        "list_tool": "list_drive_items",
                        "get_tool": "get_drive_file_content",
                        "id_field": "file_id",
                    }
                }
            elif service_name == "calendar":
                service_config["list_types"] = {
                    "calendars": {
                        "display_name": "Calendars",
                        "description": "Available calendars",
                        "list_tool": "list_calendars",
                        "get_tool": None,
                        "id_field": "calendar_id",
                    },
                    "events": {
                        "display_name": "Calendar Events",
                        "description": "Events in calendars",
                        "list_tool": "list_events",
                        "get_tool": "get_event",
                        "id_field": "event_id",
                    },
                }
            elif service_name == "docs":
                service_config["list_types"] = {
                    "documents": {
                        "display_name": "Documents",
                        "description": "Google Docs documents",
                        "list_tool": "search_docs",
                        "get_tool": "get_doc_content",
                        "id_field": "document_id",
                    }
                }
            elif service_name == "sheets":
                service_config["list_types"] = {
                    "spreadsheets": {
                        "display_name": "Spreadsheets",
                        "description": "Google Sheets spreadsheets",
                        "list_tool": "list_spreadsheets",
                        "get_tool": "get_spreadsheet_info",
                        "id_field": "spreadsheet_id",
                    }
                }
            elif service_name == "chat":
                service_config["list_types"] = {
                    "spaces": {
                        "display_name": "Chat Spaces",
                        "description": "Chat rooms and direct messages",
                        "list_tool": "list_spaces",
                        "get_tool": None,
                        "id_field": "space_id",
                    }
                }
            elif service_name == "forms":
                service_config["list_types"] = {
                    "form_responses": {
                        "display_name": "Form Responses",
                        "description": "Responses to Google Forms",
                        "list_tool": "list_form_responses",
                        "get_tool": "get_form_response",
                        "id_field": "response_id",
                    }
                }
            elif service_name == "slides":
                service_config["list_types"] = {
                    "presentations": {
                        "display_name": "Presentations",
                        "description": "Google Slides presentations",
                        "list_tool": None,  # No dedicated list tool yet
                        "get_tool": "get_presentation_info",
                        "id_field": "presentation_id",
                    }
                }
            elif service_name == "photos":
                service_config["list_types"] = {
                    "albums": {
                        "display_name": "Photo Albums",
                        "description": "Photo albums and collections",
                        "list_tool": "list_photos_albums",
                        "get_tool": "list_album_photos",
                        "id_field": "album_id",
                    }
                }
            elif service_name == "people":
                service_config["list_types"] = {
                    "labels": {
                        "display_name": "Contact Labels",
                        "description": "Google People contact groups / labels",
                        "list_tool": "list_people_contact_labels",
                        "get_tool": "get_people_contact_group_members",  # ✅ Label-to-emails resolution
                        "id_field": "label",  # Changed from resourceName to match the tool parameter
                    }
                }
            elif service_name == "tasks":
                service_config["list_types"] = {
                    "task_lists": {
                        "display_name": "Task Lists",
                        "description": "Task lists and todo items",
                        "list_tool": "list_task_lists",
                        "get_tool": "get_task_list",
                        "id_field": "task_list_id",
                    }
                }

            # Filter based on available tools if provided
            if available_tools:
                filtered_list_types = {}
                for list_type_name, list_type_info in service_config[
                    "list_types"
                ].items():
                    list_tool = list_type_info.get("list_tool")
                    if list_tool and list_tool in available_tools:
                        filtered_list_types[list_type_name] = list_type_info
                service_config["list_types"] = filtered_list_types

            service_metadata[service_name] = service_config

        return service_metadata

    def _get_service_metadata(self, available_tools: Set[str] = None) -> Dict[str, Any]:
        """Get service metadata, building it dynamically if not cached."""
        if self._cached_service_metadata is None:
            self._cached_service_metadata = self._build_service_metadata_from_registry(
                available_tools
            )
        return self._cached_service_metadata

    def _normalize_service_name(self, service: str) -> str:
        """Normalize service name to handle singular/plural variants."""
        return self.SERVICE_NAME_MAPPINGS.get(service, service)

    def __init__(
        self, enable_debug_logging: bool = False, cache_ttl_seconds: int = 300
    ):
        """
        Initialize the TagBasedResourceMiddleware.

        Args:
            enable_debug_logging: Enable detailed debug logging for troubleshooting
            cache_ttl_seconds: Default TTL for cache entries in seconds (default: 5 minutes)
        """
        self.enable_debug_logging = enable_debug_logging
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache = {}  # In-memory cache storage
        self._cached_service_metadata = None  # Will be built dynamically

        logger.debug("✨ TagBasedResourceMiddleware initialized")
        logger.debug("   Building service metadata dynamically from ScopeRegistry...")

        # Get initial metadata to show supported services
        try:
            metadata = self._get_service_metadata()
            supported_services = list(metadata.keys())
            logger.debug(f"   Supported services: {', '.join(supported_services)}")
        except Exception as e:
            logger.warning(f"   Could not build initial service metadata: {e}")
            logger.debug("   Service metadata will be built on first request")

        logger.debug(f"   Cache TTL: {cache_ttl_seconds} seconds")
        if enable_debug_logging:
            logger.debug("🔧 Debug logging enabled for TagBasedResourceMiddleware")

    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """
        Intercept resource reads and handle service:// URIs.

        This method is called for every resource read. It checks if the URI matches
        the service:// pattern and handles it accordingly, otherwise passes through
        to the next middleware.

        Args:
            context: MiddlewareContext containing the resource read request
            call_next: Continuation function to proceed with normal resource handling

        Returns:
            Resource content or passes through to next middleware
        """
        # Get the resource URI from the message - for resource reads, context.message contains ReadResourceRequestParams
        resource_uri = str(context.message.uri) if context.message.uri else ""

        if self.enable_debug_logging:
            logger.debug(f"🔍 Checking resource URI: {resource_uri}")

        # Check if this is a service:// URI that we should handle
        if not resource_uri.startswith("service://"):
            # Not our URI pattern, pass through to next middleware
            if self.enable_debug_logging:
                logger.debug(f"🔄 Passing through non-service URI: {resource_uri}")
            # result = await call_next(context)
            # if self.enable_debug_logging:
            #     logger.debug(f"🔄 Call next returned type: {type(result)}")
            return await call_next(context)

        logger.debug(f"🎯 Attempting to match service URI pattern: {resource_uri}")

        # Parse the service URI
        match = self.SERVICE_URI_PATTERN.match(resource_uri)
        if not match:
            logger.error(f"❌ Service URI pattern does not match: {resource_uri}")
            return await self._create_error_response(
                context=context,
                call_next=call_next,
                error_message=f"Invalid service URI format: {resource_uri}",
                help_message="Expected format: service://{service}/{list_type?}/{id?}",
                uri=resource_uri,
            )

        service = match.group("service")
        list_type = match.group("list_type")
        item_id = match.group("id")

        # Normalize service name to handle singular/plural variants
        normalized_service = self._normalize_service_name(service)
        if normalized_service != service:
            logger.debug(
                f"🔄 Normalized service name: {service} -> {normalized_service}"
            )
            service = normalized_service

        logger.debug(
            f"🎯 Parsed service URI: service={service}, list_type={list_type}, item_id={item_id}"
        )

        try:
            # Handle the different URI patterns
            if list_type is None:
                # service://{service} - return service info (not implemented yet)
                logger.debug("📝 Service root access not implemented")
                return await self._create_error_response(
                    context=context,
                    call_next=call_next,
                    error_message=f"Service root access not implemented: {resource_uri}",
                    help_message="Use service://{service}/lists to see available list types",
                    uri=resource_uri,
                )
            elif list_type == "lists":
                # service://{service}/lists - return available list types
                logger.debug(f"📋 Handling service lists for: {service}")
                await self._handle_service_lists(service, context)
                logger.debug("✅ Service lists stored in context state")
                return await call_next(context)
            elif item_id is None:
                # service://{service}/{list_type} - return all items for list type
                logger.debug(f"📋 Handling list items for: {service}/{list_type}")
                await self._handle_list_items(service, list_type, context)
                logger.debug("✅ Service list items stored in context state")
                return await call_next(context)
            else:
                # service://{service}/{list_type}/{id} - return specific item
                logger.debug(
                    f"🎯 Handling specific item: {service}/{list_type}/{item_id}"
                )
                await self._handle_specific_item(service, list_type, item_id, context)
                logger.debug("✅ Specific item stored in context state")
                return await call_next(context)

        except Exception as e:
            logger.error(
                f"❌ Error handling service resource {resource_uri}: {e}", exc_info=True
            )
            return await self._create_error_response(
                context=context,
                call_next=call_next,
                error_message=f"Error processing service resource: {str(e)}",
                help_message="Check logs for detailed error information",
                uri=resource_uri,
            )

    async def on_tool_call(self, context: MiddlewareContext, call_next):
        """
        Hook to update cache when tools are called directly.

        This method is called for every tool call and allows us to update our cache
        when tools are called outside of the resource middleware.

        Args:
            context: MiddlewareContext containing the tool call request
            call_next: Continuation function to proceed with normal tool handling

        Returns:
            Tool result
        """
        # Extract tool information
        tool_name = context.message.name
        params = context.message.arguments or {}

        # Call the tool first
        result = await call_next(context)

        # Check if this is a list tool we should cache
        if tool_name and self._is_list_tool(tool_name):
            user_email = params.get("user_google_email")
            if user_email:
                service, list_type = self._get_service_from_tool(tool_name)
                if service and list_type:
                    # Generate cache key (matches resource handler expectations)
                    cache_key = (
                        f"service_list_response_{service}_{list_type}_{user_email}"
                    )

                    # Convert result to serializable format (same logic as _handle_list_items)
                    serializable_result = self._convert_result_to_serializable(result)

                    # Cache the result
                    self.cache[cache_key] = CacheEntry(
                        data=serializable_result,
                        timestamp=datetime.now(),
                        ttl_seconds=self.cache_ttl_seconds,
                    )
                    logger.debug(f"📦 Cached result from direct tool call: {tool_name}")

        return result

    def _is_list_tool(self, tool_name: str) -> bool:
        """Check if a tool is a list tool that should be cached."""
        service_metadata = self._get_service_metadata()
        for service_meta in service_metadata.values():
            for list_type_info in service_meta.get("list_types", {}).values():
                if list_type_info.get("list_tool") == tool_name:
                    return True
        return False

    def _get_service_from_tool(self, tool_name: str) -> tuple:
        """Get service and list_type from tool name."""
        service_metadata = self._get_service_metadata()
        for service_name, service_meta in service_metadata.items():
            for list_type_name, list_type_info in service_meta.get(
                "list_types", {}
            ).items():
                if list_type_info.get("list_tool") == tool_name:
                    return service_name, list_type_name
        return None, None

    def _convert_result_to_serializable(self, result: Any) -> Any:
        """Convert a tool result to a JSON-serializable Python object.

        FastMCP v3 types:
        - CallToolResult: .content is list[TextContent | ImageContent | ...]
          where TextContent has .text (str)
        - ResourceResult: .contents is list[ResourceContent]
          where ResourceContent has .content (str) and .mime_type
        """
        import json as json_module

        from pydantic import BaseModel

        # CallToolResult — .content is a list of TextContent items
        if hasattr(result, "content") and isinstance(result.content, list):
            texts = [item.text for item in result.content if hasattr(item, "text")]
            if len(texts) == 1:
                try:
                    return json_module.loads(texts[0])
                except (json_module.JSONDecodeError, TypeError, ValueError):
                    return texts[0]
            return texts if texts else result.content

        # ResourceResult — .contents is a list of ResourceContent items
        if hasattr(result, "contents") and isinstance(result.contents, list):
            payloads = [item.content for item in result.contents]
            if len(payloads) == 1 and isinstance(payloads[0], str):
                try:
                    return json_module.loads(payloads[0])
                except (json_module.JSONDecodeError, TypeError, ValueError):
                    return payloads[0]
            return payloads

        # Generic Pydantic fallback
        if isinstance(result, BaseModel):
            return result.model_dump()

        return result

    async def _handle_service_lists(
        self, service: str, context: MiddlewareContext
    ) -> None:
        """
        Handle service://{service}/lists pattern - return available list types with metadata.

        Args:
            service: Service name (e.g., "gmail", "drive")
            context: MiddlewareContext for accessing FastMCP tools

        Returns:
            JSON string with available list types and metadata
        """
        if self.enable_debug_logging:
            logger.debug(f"📋 Handling service lists for: {service}")

        # Get available tools to build dynamic metadata
        available_tools = await self._get_available_tools(context)
        service_metadata = self._get_service_metadata(available_tools)

        # Check if service is supported
        if service not in service_metadata:
            return self._create_error_response(
                f"Unsupported service: {service}",
                f"Supported services: {', '.join(service_metadata.keys())}",
            )

        service_meta = service_metadata[service]

        # Get available tools to verify which list types are actually available
        available_tools = await self._get_available_tools(context)

        # Filter list types based on available tools
        available_list_types = {}
        for list_type_name, list_type_info in service_meta.get(
            "list_types", {}
        ).items():
            list_tool_name = list_type_info.get("list_tool")
            if list_tool_name and list_tool_name in available_tools:
                available_list_types[list_type_name] = {
                    "display_name": list_type_info.get("display_name", list_type_name),
                    "description": list_type_info.get("description", ""),
                    "tool_name": list_tool_name,
                    "supports_get": list_type_info.get("get_tool") is not None,
                    "id_field": list_type_info.get("id_field", "id"),
                }

        # Create ServiceListsResponse and store in context state
        response_model = ServiceListsResponse.from_middleware_data(
            service=service,
            service_metadata={
                "display_name": service_meta["display_name"],
                "icon": service_meta["icon"],
                "description": service_meta["description"],
            },
            list_types=available_list_types,
        )

        cache_key = f"service_lists_response_{service}"
        await context.fastmcp_context.set_state(cache_key, response_model)
        logger.debug(
            f"📦 Stored ServiceListsResponse in context state with key: {cache_key}"
        )

    async def _handle_list_items(
        self, service: str, list_type: str, context: MiddlewareContext
    ) -> None:
        """
        Handle service://{service}/{list_type} pattern - call the appropriate list tool.

        Args:
            service: Service name (e.g., "gmail", "drive")
            list_type: List type name (e.g., "filters", "labels")
            context: MiddlewareContext for accessing FastMCP tools and user context

        Stores ServiceListResponse in FastMCP context state for resource handler retrieval.
        Also caches the raw result for use by specific item requests.
        """
        if self.enable_debug_logging:
            logger.debug(f"📋 Handling list items for: {service}/{list_type}")

        # Get available tools to build dynamic metadata
        available_tools = await self._get_available_tools(context)
        service_metadata = self._get_service_metadata(available_tools)

        # Check if service and list type are supported
        if service not in service_metadata:
            logger.error(f"Unsupported service: {service}")
            return

        service_meta = service_metadata[service]
        list_type_info = service_meta.get("list_types", {}).get(list_type)

        if not list_type_info:
            available_types = list(service_meta.get("list_types", {}).keys())
            logger.error(
                f"Unsupported list type '{list_type}' for service '{service}'. Available: {', '.join(available_types)}"
            )
            return

        list_tool_name = list_type_info.get("list_tool")
        if not list_tool_name:
            logger.error(f"No list tool configured for {service}/{list_type}")
            return

        # Get user email from context (with OAuth file fallback)
        user_email = await get_user_email_context()
        if not user_email:
            logger.error("❌ User email not found in context or OAuth files")
            logger.error(
                "   Please authenticate using start_google_auth or ensure OAuth credentials exist"
            )
            return

        # Log authentication source for debugging
        logger.debug(f"🔐 Using authentication for user: {user_email}")

        # Generate cache key (matches resource handler expectations)
        cache_key = f"service_list_response_{service}_{list_type}_{user_email}"

        # Check cache first
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if not cache_entry.is_expired():
                logger.debug(f"✅ Using cached data for {service}/{list_type}")
                # Get the cached response model
                cached_response = cache_entry.data
                serializable_result = cached_response.result
            else:
                logger.debug(
                    f"🔄 Cache expired for {service}/{list_type}, removing entry"
                )
                del self.cache[cache_key]
                cached_response = None
                serializable_result = None
        else:
            logger.debug(f"🔄 No cached data found for {service}/{list_type}")
            cached_response = None
            serializable_result = None

        # If no valid cached data, call the tool
        if cached_response is None:
            try:
                result = await self._call_tool_with_context(
                    context, list_tool_name, {"user_google_email": user_email}
                )

                # Convert result to serializable format
                serializable_result = self._convert_result_to_serializable(result)

                # Create structured response using ServiceListResponse BaseModel
                cached_response = ServiceListResponse.from_middleware_data(
                    result=serializable_result,
                    service=service,
                    list_type=list_type,
                    tool_called=list_tool_name,
                    user_email=user_email,
                )

                # Cache the response model
                self.cache[cache_key] = CacheEntry(
                    data=cached_response,
                    timestamp=datetime.now(),
                    ttl_seconds=self.cache_ttl_seconds,
                )
                logger.debug(f"📦 Cached ServiceListResponse for {service}/{list_type}")

            except Exception as e:
                logger.error(f"❌ Error calling tool {list_tool_name}: {e}")
                return

        # Store in FastMCP context state for resource handler (matches resource handler expectations)
        await context.fastmcp_context.set_state(cache_key, cached_response)
        logger.debug(
            f"📦 Stored ServiceListResponse in FastMCP context state with key: {cache_key}"
        )

        # ALSO cache the raw result for specific item extraction
        raw_cache_key = f"service_list_raw_{service}_{list_type}_{user_email}"
        await context.fastmcp_context.set_state(raw_cache_key, serializable_result)
        logger.debug(
            f"📦 Cached raw list data for item extraction with key: {raw_cache_key}"
        )

    async def _handle_specific_item(
        self, service: str, list_type: str, item_id: str, context: MiddlewareContext
    ) -> None:
        """
        Handle service://{service}/{list_type}/{id} pattern - get specific item details.

        Uses a smart strategy:
        1. If there's a dedicated get_tool, use it directly
        2. If no get_tool (like Gmail labels), extract the item from cached list data
        3. If no cached list data, fetch the list and extract the item

        Args:
            service: Service name (e.g., "gmail", "drive")
            list_type: List type name (e.g., "filters", "labels")
            item_id: Specific item ID
            context: MiddlewareContext for accessing FastMCP tools and user context

        Stores ServiceItemDetailsResponse in FastMCP context state for resource handler retrieval.
        """
        if self.enable_debug_logging:
            logger.debug(f"🎯 Handling specific item: {service}/{list_type}/{item_id}")

        # Get available tools to build dynamic metadata
        available_tools = await self._get_available_tools(context)
        service_metadata = self._get_service_metadata(available_tools)

        # Check if service and list type are supported
        if service not in service_metadata:
            logger.error(f"Unsupported service: {service}")
            return

        service_meta = service_metadata[service]
        list_type_info = service_meta.get("list_types", {}).get(list_type)

        if not list_type_info:
            available_types = list(service_meta.get("list_types", {}).keys())
            logger.error(
                f"Unsupported list type '{list_type}' for service '{service}'. Available: {', '.join(available_types)}"
            )
            return

        # Get user email from context (with OAuth file fallback)
        user_email = await get_user_email_context()
        if not user_email:
            logger.error("❌ User email not found in context or OAuth files")
            logger.error(
                "   Please authenticate using start_google_auth or ensure OAuth credentials exist"
            )
            return

        # Log authentication source for debugging
        logger.debug(f"🔐 Using authentication for user: {user_email}")

        get_tool_name = list_type_info.get("get_tool")

        if get_tool_name:
            # Strategy 1: Use dedicated get tool
            logger.debug(f"🔧 Using dedicated get tool: {get_tool_name}")
            await self._handle_specific_item_with_get_tool(
                service,
                list_type,
                item_id,
                context,
                get_tool_name,
                list_type_info,
                user_email,
            )
        else:
            # Strategy 2: Extract from list data (for Gmail labels, etc.)
            logger.debug(
                f"📋 Extracting from list data (no dedicated get tool for {service}/{list_type})"
            )
            await self._handle_specific_item_from_list(
                service, list_type, item_id, context, list_type_info, user_email
            )

    async def _handle_specific_item_with_get_tool(
        self,
        service: str,
        list_type: str,
        item_id: str,
        context: MiddlewareContext,
        get_tool_name: str,
        list_type_info: dict,
        user_email: str,
    ) -> None:
        """Handle specific item using a dedicated get tool."""
        # Generate cache key for get tool results (matches resource handler expectations)
        cache_key = f"service_item_details_{service}_{list_type}_{item_id}_{user_email}"

        # Check cache first
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if not cache_entry.is_expired():
                logger.debug(
                    f"✅ Using cached data for {service}/{list_type}/{item_id}"
                )
                serializable_result = cache_entry.data
            else:
                logger.debug(
                    f"🔄 Cache expired for {service}/{list_type}/{item_id}, removing entry"
                )
                del self.cache[cache_key]
                serializable_result = None
        else:
            logger.debug(f"🔄 No cached data found for {service}/{list_type}/{item_id}")
            serializable_result = None

        # If no valid cached data, call the tool
        if serializable_result is None:
            # Prepare parameters for the get tool
            id_field = list_type_info.get("id_field", "id")
            tool_params = {"user_google_email": user_email, id_field: item_id}

            # Call the tool with auto-injected parameters
            try:
                result = await self._call_tool_with_context(
                    context, get_tool_name, tool_params
                )

                # Convert result to serializable format
                serializable_result = self._convert_result_to_serializable(result)

                # Cache the result
                self.cache[cache_key] = CacheEntry(
                    data=serializable_result,
                    timestamp=datetime.now(),
                    ttl_seconds=self.cache_ttl_seconds,
                )
                logger.debug(f"📦 Cached result for {service}/{list_type}/{item_id}")

            except Exception as e:
                logger.error(f"❌ Error calling get tool {get_tool_name}: {e}")
                return

        # Create ServiceItemDetailsResponse and store in context state
        response_model = ServiceItemDetailsResponse.from_middleware_data(
            service=service,
            list_type=list_type,
            item_id=item_id,
            tool_called=get_tool_name,
            user_email=user_email,
            parameters={
                "user_google_email": user_email,
                list_type_info.get("id_field", "id"): item_id,
            },
            result=serializable_result,
        )

        context_cache_key = (
            f"service_item_details_{service}_{list_type}_{item_id}_{user_email}"
        )
        await context.fastmcp_context.set_state(context_cache_key, response_model)
        logger.debug(
            f"📦 Stored ServiceItemDetailsResponse (via get tool) with key: {context_cache_key}"
        )

    async def _handle_specific_item_from_list(
        self,
        service: str,
        list_type: str,
        item_id: str,
        context: MiddlewareContext,
        list_type_info: dict,
        user_email: str,
    ) -> None:
        """Handle specific item by extracting from cached or fresh list data."""
        raw_cache_key = f"service_list_raw_{service}_{list_type}_{user_email}"

        # Try to get cached raw list data
        cached_list_data = await context.fastmcp_context.get_state(raw_cache_key)

        if not cached_list_data:
            # No cached data, fetch fresh list data
            logger.debug(
                f"🔄 No cached list data found, fetching fresh data for {service}/{list_type}"
            )

            list_tool_name = list_type_info.get("list_tool")
            if not list_tool_name:
                logger.error(f"No list tool configured for {service}/{list_type}")
                return

            try:
                # Call the list tool to get fresh data
                result = await self._call_tool_with_context(
                    context, list_tool_name, {"user_google_email": user_email}
                )

                # Convert result to serializable format (same logic as _handle_list_items)
                cached_list_data = self._convert_result_to_serializable(result)

                # Cache the fresh data
                await context.fastmcp_context.set_state(raw_cache_key, cached_list_data)
                logger.debug(f"📦 Cached fresh list data with key: {raw_cache_key}")

            except Exception as e:
                logger.error(f"❌ Error fetching fresh list data: {e}")
                return
        else:
            logger.debug(f"✅ Using cached list data for {service}/{list_type}")

        # Extract the specific item from the list data
        specific_item = self._extract_item_from_list(
            cached_list_data, item_id, list_type_info
        )

        if specific_item is None:
            logger.error(f"❌ Item '{item_id}' not found in {service}/{list_type} list")
            # Create error response
            error_result = {
                "error": f"Item '{item_id}' not found",
                "available_ids": self._get_available_ids_from_list(
                    cached_list_data, list_type_info
                ),
            }
        else:
            logger.debug(f"✅ Found item '{item_id}' in {service}/{list_type} list")
            error_result = specific_item

        # Create ServiceItemDetailsResponse and store in context state
        response_model = ServiceItemDetailsResponse.from_middleware_data(
            service=service,
            list_type=list_type,
            item_id=item_id,
            tool_called=f"{list_type_info.get('list_tool')}_extract",
            user_email=user_email,
            parameters={"extracted_from_list": True, "item_id": item_id},
            result=error_result,
        )

        cache_key = f"service_item_details_{service}_{list_type}_{item_id}_{user_email}"
        await context.fastmcp_context.set_state(cache_key, response_model)
        logger.debug(
            f"📦 Stored ServiceItemDetailsResponse (via list extraction) with key: {cache_key}"
        )

    def _extract_item_from_list(
        self, list_data: Any, item_id: str, list_type_info: dict
    ) -> Any:
        """Extract a specific item from list data by ID."""
        try:
            # Handle different list data structures
            if isinstance(list_data, dict):
                # For Gmail labels, look in different possible locations
                if "labels" in list_data:
                    items = list_data["labels"]
                elif "items" in list_data:
                    items = list_data["items"]
                elif (
                    "result" in list_data
                    and isinstance(list_data["result"], dict)
                    and "labels" in list_data["result"]
                ):
                    items = list_data["result"]["labels"]
                else:
                    # Try treating the dict itself as the item collection
                    items = [list_data]
            elif isinstance(list_data, list):
                items = list_data
            else:
                logger.warning(f"⚠️ Unknown list data structure: {type(list_data)}")
                return None

            # Search for item by ID
            id_field = list_type_info.get("id_field", "id")
            for item in items:
                if isinstance(item, dict):
                    if item.get(id_field) == item_id or item.get("id") == item_id:
                        return item
                elif hasattr(item, id_field):
                    if getattr(item, id_field) == item_id:
                        return item

            return None

        except Exception as e:
            logger.error(f"❌ Error extracting item from list: {e}")
            return None

    def _get_available_ids_from_list(
        self, list_data: Any, list_type_info: dict
    ) -> List[str]:
        """Get list of available IDs from list data for error reporting."""
        try:
            ids = []

            # Handle different list data structures
            if isinstance(list_data, dict):
                if "labels" in list_data:
                    items = list_data["labels"]
                elif "items" in list_data:
                    items = list_data["items"]
                elif (
                    "result" in list_data
                    and isinstance(list_data["result"], dict)
                    and "labels" in list_data["result"]
                ):
                    items = list_data["result"]["labels"]
                else:
                    items = [list_data]
            elif isinstance(list_data, list):
                items = list_data
            else:
                return ["unknown_structure"]

            # Extract IDs
            id_field = list_type_info.get("id_field", "id")
            for item in items[:10]:  # Limit to first 10 for error message
                if isinstance(item, dict):
                    item_id = item.get(id_field) or item.get("id")
                    if item_id:
                        ids.append(str(item_id))
                elif hasattr(item, id_field):
                    ids.append(str(getattr(item, id_field)))

            return ids

        except Exception as e:
            logger.error(f"❌ Error getting available IDs: {e}")
            return ["error_extracting_ids"]

    async def _get_available_tools(self, context: MiddlewareContext) -> Set[str]:
        """
        Get available tools from FastMCP context.

        Args:
            context: MiddlewareContext for accessing FastMCP tools

        Returns:
            Set of available tool names
        """
        try:
            if context.fastmcp_context:
                mcp_server = context.fastmcp_context.fastmcp
                from fastmcp.tools.tool import Tool

                components = mcp_server.local_provider._components
                tools_dict = {
                    v.name: v for v in components.values() if isinstance(v, Tool)
                }

                if tools_dict:
                    tool_names = set(tools_dict.keys())

                    if self.enable_debug_logging:
                        logger.debug(f"🔧 Found {len(tool_names)} available tools")

                    return tool_names
                else:
                    logger.warning("⚠️ Cannot access tool registry from FastMCP server")
                    return set()
            else:
                logger.warning("⚠️ No FastMCP context available for tool discovery")
                return set()

        except Exception as e:
            logger.error(f"❌ Error getting available tools: {e}")
            return set()

    async def _call_tool_with_context(
        self, context: MiddlewareContext, tool_name: str, parameters: Dict[str, Any]
    ) -> Any:
        """
        Call a tool using the FastMCP context with proper parameter injection.

        Args:
            context: MiddlewareContext for accessing FastMCP tools
            tool_name: Name of the tool to call
            parameters: Parameters to pass to the tool

        Returns:
            Result from the tool call

        Raises:
            RuntimeError: If FastMCP context is not available or tool call fails
        """
        if not context.fastmcp_context:
            raise RuntimeError("FastMCP context not available for tool calling")

        # Special handling for search_gmail_messages: inject default query if not provided
        if tool_name == "search_gmail_messages" and "query" not in parameters:
            from datetime import datetime, timedelta

            # Default to recent messages from last 7 days
            seven_days_ago = datetime.now() - timedelta(days=7)
            default_query = f"after:{seven_days_ago.strftime('%Y/%m/%d')}"
            parameters["query"] = default_query
            logger.debug(
                f"🔧 Injecting default query for Gmail messages: {default_query}"
            )

        if self.enable_debug_logging:
            logger.debug(f"🔧 Calling tool {tool_name} with parameters: {parameters}")

        mcp_server = context.fastmcp_context.fastmcp
        from fastmcp.tools.tool import Tool

        components = mcp_server.local_provider._components
        tools_dict = {v.name: v for v in components.values() if isinstance(v, Tool)}

        if not tools_dict:
            raise RuntimeError("Cannot access tool registry from FastMCP server")

        if tool_name not in tools_dict:
            raise RuntimeError(f"Tool '{tool_name}' not found in registry")

        tool_instance = tools_dict[tool_name]

        tool_func = tool_instance.fn

        # Call the tool's function with parameters
        try:
            # Check if the function is async
            import asyncio

            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**parameters)
            else:
                # Some tools might be sync functions
                result = tool_func(**parameters)

            if self.enable_debug_logging:
                logger.debug(f"✅ Tool {tool_name} call successful")
                logger.debug(f"🔍 Tool result type: {type(result)}")
                if hasattr(result, "__dict__"):
                    logger.debug(
                        f"🔍 Tool result attributes: {list(result.__dict__.keys())}"
                    )

            return result

        except Exception as e:
            logger.error(f"❌ Tool {tool_name} call failed: {e}")
            raise

    async def _create_error_response(
        self,
        context: MiddlewareContext,
        call_next,
        error_message: str,
        help_message: str = "",
        uri: str = None,
    ):
        """
        Create a standardized error response and store in context.

        Args:
            context: MiddlewareContext for storing the error response
            call_next: Continuation function to proceed with middleware chain
            error_message: Main error description
            help_message: Optional help or suggestion message
            uri: Optional URI that caused the error

        Returns:
            Result from call_next after storing error response in context
        """
        error_response = ServiceErrorResponse.from_error(
            message=error_message,
            help_message=help_message if help_message else None,
            uri=uri,
        )

        # Store error response in context state with a unique key
        # Use timestamp to ensure uniqueness for multiple errors
        error_key = f"service_error_response_{datetime.now().timestamp()}"
        await context.fastmcp_context.set_state(error_key, error_response)
        logger.debug(
            f"📦 Stored ServiceErrorResponse in context state with key: {error_key}"
        )

        # Let the resource handler convert it to proper MCP response
        return await call_next(context)

    def clear_cache(self):
        """Clear all cached entries."""
        self.cache.clear()
        logger.debug("🧹 Cache cleared")

    def invalidate_cache(self, pattern: str = None):
        """Invalidate cache entries matching pattern."""
        if pattern:
            keys_to_delete = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self.cache[key]
            logger.debug(f"🧹 Invalidated {len(keys_to_delete)} cache entries")
        else:
            self.clear_cache()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self.cache)
        expired_entries = sum(1 for entry in self.cache.values() if entry.is_expired())
        valid_entries = total_entries - expired_entries

        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "cache_ttl_seconds": self.cache_ttl_seconds,
        }
