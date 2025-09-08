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

import json
import re
import logging
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from fastmcp.server.middleware import Middleware, MiddlewareContext
from auth.context import get_user_email_context
from mcp.server.lowlevel.helper_types import ReadResourceContents
from .service_list_response import ServiceListResponse, ServiceListsResponse, ServiceItemDetailsResponse

logger = logging.getLogger(__name__)


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
    SERVICE_URI_PATTERN = re.compile(r'^service://(?P<service>[^/]+)(?:/(?P<list_type>[^/]+))?(?:/(?P<id>.+))?$')
    
    # Service metadata for documentation and defaults
    SERVICE_METADATA = {
        "gmail": {
            "display_name": "Gmail",
            "icon": "📧",
            "description": "Email service with powerful search, filtering, and organization features",
            "list_types": {
                "filters": {
                    "display_name": "Email Filters",
                    "description": "Automatic email filtering rules",
                    "list_tool": "list_gmail_filters",
                    "get_tool": "get_gmail_filter",
                    "id_field": "filter_id"
                },
                "labels": {
                    "display_name": "Email Labels", 
                    "description": "Organizational labels and categories",
                    "list_tool": "list_gmail_labels",
                    "get_tool": None,  # No individual get tool
                    "id_field": "label_id"
                }
            }
        },
        "drive": {
            "display_name": "Google Drive",
            "icon": "📁",
            "description": "Cloud storage and file synchronization service",
            "list_types": {
                "items": {
                    "display_name": "Drive Files",
                    "description": "Files and folders in Google Drive",
                    "list_tool": "list_drive_items",
                    "get_tool": "get_drive_file_content",
                    "id_field": "file_id"
                }
            }
        },
        "calendar": {
            "display_name": "Google Calendar",
            "icon": "📅", 
            "description": "Time management and scheduling service",
            "list_types": {
                "calendars": {
                    "display_name": "Calendars",
                    "description": "Available calendars",
                    "list_tool": "list_calendars",
                    "get_tool": None,
                    "id_field": "calendar_id"
                },
                "events": {
                    "display_name": "Calendar Events",
                    "description": "Events in calendars",
                    "list_tool": "list_events",
                    "get_tool": "get_event",
                    "id_field": "event_id"
                }
            }
        },
        "docs": {
            "display_name": "Google Docs",
            "icon": "📄",
            "description": "Document creation and collaboration service",
            "list_types": {
                "documents": {
                    "display_name": "Documents",
                    "description": "Google Docs documents",
                    "list_tool": "search_docs",
                    "get_tool": "get_doc_content",
                    "id_field": "document_id"
                }
            }
        },
        "sheets": {
            "display_name": "Google Sheets",
            "icon": "📊",
            "description": "Spreadsheet and data analysis service",
            "list_types": {
                "spreadsheets": {
                    "display_name": "Spreadsheets",
                    "description": "Google Sheets spreadsheets",
                    "list_tool": "list_spreadsheets",
                    "get_tool": "get_spreadsheet_info",
                    "id_field": "spreadsheet_id"
                }
            }
        },
        "chat": {
            "display_name": "Google Chat",
            "icon": "💬",
            "description": "Team messaging and collaboration platform",
            "list_types": {
                "spaces": {
                    "display_name": "Chat Spaces",
                    "description": "Chat rooms and direct messages",
                    "list_tool": "list_spaces",
                    "get_tool": None,
                    "id_field": "space_id"
                }
            }
        },
        "forms": {
            "display_name": "Google Forms",
            "icon": "📝",
            "description": "Survey and form creation service",
            "list_types": {
                "form_responses": {
                    "display_name": "Form Responses",
                    "description": "Responses to Google Forms",
                    "list_tool": "list_form_responses",
                    "get_tool": "get_form_response",
                    "id_field": "response_id"
                }
            }
        },
        "slides": {
            "display_name": "Google Slides",
            "icon": "🎯",
            "description": "Presentation creation and sharing service",
            "list_types": {
                "presentations": {
                    "display_name": "Presentations",
                    "description": "Google Slides presentations",
                    "list_tool": None,  # No dedicated list tool yet
                    "get_tool": "get_presentation_info",
                    "id_field": "presentation_id"
                }
            }
        },
        "photos": {
            "display_name": "Google Photos",
            "icon": "📷",
            "description": "Photo and video storage service",
            "list_types": {
                "albums": {
                    "display_name": "Photo Albums",
                    "description": "Photo albums and collections",
                    "list_tool": "list_photos_albums",
                    "get_tool": "list_album_photos",
                    "id_field": "album_id"
                }
            }
        }
    }
    
    def __init__(self, enable_debug_logging: bool = False):
        """
        Initialize the TagBasedResourceMiddleware.
        
        Args:
            enable_debug_logging: Enable detailed debug logging for troubleshooting
        """
        self.enable_debug_logging = enable_debug_logging
        logger.info("✨ TagBasedResourceMiddleware initialized")
        logger.info("   Supported services: " + ", ".join(self.SERVICE_METADATA.keys()))
        if enable_debug_logging:
            logger.info("🔧 Debug logging enabled for TagBasedResourceMiddleware")
    
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
        resource_uri = str(context.message.uri) if hasattr(context.message, 'uri') and context.message.uri else ''
        
        if self.enable_debug_logging:
            logger.debug(f"🔍 Checking resource URI: {resource_uri}")
        
        # Check if this is a service:// URI that we should handle
        if not resource_uri.startswith('service://'):
            # Not our URI pattern, pass through to next middleware
            if self.enable_debug_logging:
                logger.debug(f"🔄 Passing through non-service URI: {resource_uri}")
            # result = await call_next(context)
            # if self.enable_debug_logging:
            #     logger.debug(f"🔄 Call next returned type: {type(result)}")
            return await call_next(context)
        
        logger.info(f"🎯 Attempting to match service URI pattern: {resource_uri}")
        
        # Parse the service URI
        match = self.SERVICE_URI_PATTERN.match(resource_uri)
        service = match.group('service')
        list_type = match.group('list_type')
        item_id = match.group('id')
        
        logger.info(f"🎯 Parsed service URI: service={service}, list_type={list_type}, item_id={item_id}")
        
        try:
            # Handle the different URI patterns
            if list_type is None:
                # service://{service} - return service info (not implemented yet)
                logger.info("📝 Service root access not implemented")
                error_response = self._create_error_response(
                    f"Service root access not implemented: {resource_uri}",
                    "Use service://{service}/lists to see available list types"
                )
                logger.info(f"🔍 Error response type: {type(error_response)}")
                return error_response
            elif list_type == 'lists':
                # service://{service}/lists - return available list types
                logger.info(f"📋 Handling service lists for: {service}")
                await self._handle_service_lists(service, context)
                logger.info(f"✅ Service lists stored in context state")
                return await call_next(context)
            elif item_id is None:
                # service://{service}/{list_type} - return all items for list type
                logger.info(f"📋 Handling list items for: {service}/{list_type}")
                await self._handle_list_items(service, list_type, context)
                logger.info(f"✅ Service list items stored in context state")
                return await call_next(context)
            else:
                # service://{service}/{list_type}/{id} - return specific item
                logger.info(f"🎯 Handling specific item: {service}/{list_type}/{item_id}")
                await self._handle_specific_item(service, list_type, item_id, context)
                logger.info(f"✅ Specific item stored in context state")
                return await call_next(context)
                
        except Exception as e:
            logger.error(f"❌ Error handling service resource {resource_uri}: {e}", exc_info=True)
            error_response = self._create_error_response(
                f"Error processing service resource: {str(e)}",
                "Check logs for detailed error information"
            )
            logger.info(f"🔍 Exception error response type: {type(error_response)}")
            return error_response
    
    async def _handle_service_lists(self, service: str, context: MiddlewareContext) -> None:
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
        
        # Check if service is supported
        if service not in self.SERVICE_METADATA:
            return self._create_error_response(
                f"Unsupported service: {service}",
                f"Supported services: {', '.join(self.SERVICE_METADATA.keys())}"
            )
        
        service_meta = self.SERVICE_METADATA[service]
        
        # Get available tools to verify which list types are actually available
        available_tools = await self._get_available_tools(context)
        
        # Filter list types based on available tools
        available_list_types = {}
        for list_type_name, list_type_info in service_meta.get("list_types", {}).items():
            list_tool_name = list_type_info.get("list_tool")
            if list_tool_name and list_tool_name in available_tools:
                available_list_types[list_type_name] = {
                    "display_name": list_type_info.get("display_name", list_type_name),
                    "description": list_type_info.get("description", ""),
                    "tool_name": list_tool_name,
                    "supports_get": list_type_info.get("get_tool") is not None,
                    "id_field": list_type_info.get("id_field", "id")
                }
        
        # Create ServiceListsResponse and store in context state
        response_model = ServiceListsResponse.from_middleware_data(
            service=service,
            service_metadata={
                "display_name": service_meta["display_name"],
                "icon": service_meta["icon"],
                "description": service_meta["description"]
            },
            list_types=available_list_types
        )
        
        cache_key = f"service_lists_response_{service}"
        context.fastmcp_context.set_state(cache_key, response_model)
        logger.info(f"📦 Stored ServiceListsResponse in context state with key: {cache_key}")
    
    async def _handle_list_items(self, service: str, list_type: str, context: MiddlewareContext) -> None:
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
        
        # Check if service and list type are supported
        if service not in self.SERVICE_METADATA:
            logger.error(f"Unsupported service: {service}")
            return
        
        service_meta = self.SERVICE_METADATA[service]
        list_type_info = service_meta.get("list_types", {}).get(list_type)
        
        if not list_type_info:
            available_types = list(service_meta.get("list_types", {}).keys())
            logger.error(f"Unsupported list type '{list_type}' for service '{service}'. Available: {', '.join(available_types)}")
            return
        
        list_tool_name = list_type_info.get("list_tool")
        if not list_tool_name:
            logger.error(f"No list tool configured for {service}/{list_type}")
            return
        
        # Get user email from context
        user_email = get_user_email_context()
        if not user_email:
            logger.error("User email not found in context")
            return
        
        # Call the tool with auto-injected user_email
        try:
            result = await self._call_tool_with_context(
                context,
                list_tool_name,
                {"user_google_email": user_email}
            )
            
            # Convert result to serializable format
            if hasattr(result, 'content'):
                # ToolResult object - extract content
                content = result.content
                # Check if content is also an object that needs extraction
                if hasattr(content, 'text'):
                    # TextContent object - extract text
                    serializable_result = content.text
                elif hasattr(content, '__iter__') and not isinstance(content, (str, bytes)):
                    # Content is iterable (like a list of TextContent objects)
                    extracted_content = []
                    for item in content:
                        if hasattr(item, 'text'):
                            extracted_content.append(item.text)
                        else:
                            extracted_content.append(item)
                    # If it's a single item list with a string, return just the string
                    if len(extracted_content) == 1 and isinstance(extracted_content[0], str):
                        try:
                            # Try to parse as JSON if it looks like JSON
                            import json as json_module
                            serializable_result = json_module.loads(extracted_content[0])
                        except:
                            # Not JSON, just use the string
                            serializable_result = extracted_content[0]
                    else:
                        serializable_result = extracted_content
                elif hasattr(content, 'model_dump'):
                    serializable_result = content.model_dump()
                elif hasattr(content, 'dict'):
                    serializable_result = content.dict()
                else:
                    serializable_result = content
            elif hasattr(result, 'model_dump'):
                # Pydantic model - convert to dict
                serializable_result = result.model_dump()
            elif hasattr(result, 'dict'):
                # Pydantic v1 model - convert to dict
                serializable_result = result.dict()
            else:
                # Already serializable or string
                serializable_result = result
            
            # Create structured response using ServiceListResponse BaseModel
            response_model = ServiceListResponse.from_middleware_data(
                result=serializable_result,
                service=service,
                list_type=list_type,
                tool_called=list_tool_name,
                user_email=user_email
            )
            
            # Store in FastMCP context state for resource handler
            cache_key = f"service_list_response_{service}_{list_type}"
            context.fastmcp_context.set_state(cache_key, response_model)
            logger.info(f"📦 Stored ServiceListResponse in FastMCP context state with key: {cache_key}")
            
            # ALSO cache the raw result for specific item extraction
            raw_cache_key = f"service_list_raw_{service}_{list_type}_{user_email}"
            context.fastmcp_context.set_state(raw_cache_key, serializable_result)
            logger.info(f"📦 Cached raw list data for item extraction with key: {raw_cache_key}")
            
        except Exception as e:
            logger.error(f"❌ Error calling tool {list_tool_name}: {e}")
    
    async def _handle_specific_item(self, service: str, list_type: str, item_id: str, context: MiddlewareContext) -> None:
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
        
        # Check if service and list type are supported
        if service not in self.SERVICE_METADATA:
            logger.error(f"Unsupported service: {service}")
            return
        
        service_meta = self.SERVICE_METADATA[service]
        list_type_info = service_meta.get("list_types", {}).get(list_type)
        
        if not list_type_info:
            available_types = list(service_meta.get("list_types", {}).keys())
            logger.error(f"Unsupported list type '{list_type}' for service '{service}'. Available: {', '.join(available_types)}")
            return
        
        # Get user email from context
        user_email = get_user_email_context()
        if not user_email:
            logger.error("User email not found in context")
            return
        
        get_tool_name = list_type_info.get("get_tool")
        
        if get_tool_name:
            # Strategy 1: Use dedicated get tool
            logger.info(f"🔧 Using dedicated get tool: {get_tool_name}")
            await self._handle_specific_item_with_get_tool(service, list_type, item_id, context, get_tool_name, list_type_info, user_email)
        else:
            # Strategy 2: Extract from list data (for Gmail labels, etc.)
            logger.info(f"📋 Extracting from list data (no dedicated get tool for {service}/{list_type})")
            await self._handle_specific_item_from_list(service, list_type, item_id, context, list_type_info, user_email)
    
    async def _handle_specific_item_with_get_tool(self, service: str, list_type: str, item_id: str,
                                                  context: MiddlewareContext, get_tool_name: str,
                                                  list_type_info: dict, user_email: str) -> None:
        """Handle specific item using a dedicated get tool."""
        # Prepare parameters for the get tool
        id_field = list_type_info.get("id_field", "id")
        tool_params = {
            "user_google_email": user_email,
            id_field: item_id
        }
        
        # Call the tool with auto-injected parameters
        try:
            result = await self._call_tool_with_context(context, get_tool_name, tool_params)
            
            # Convert result to serializable format
            if hasattr(result, 'model_dump'):
                # Pydantic model - convert to dict
                serializable_result = result.model_dump()
            elif hasattr(result, 'dict'):
                # Pydantic v1 model - convert to dict
                serializable_result = result.dict()
            else:
                # Already serializable or string
                serializable_result = result
            
            # Create ServiceItemDetailsResponse and store in context state
            response_model = ServiceItemDetailsResponse.from_middleware_data(
                service=service,
                list_type=list_type,
                item_id=item_id,
                tool_called=get_tool_name,
                user_email=user_email,
                parameters=tool_params,
                result=serializable_result
            )
            
            cache_key = f"service_item_details_{service}_{list_type}_{item_id}"
            context.fastmcp_context.set_state(cache_key, response_model)
            logger.info(f"📦 Stored ServiceItemDetailsResponse (via get tool) with key: {cache_key}")
            
        except Exception as e:
            logger.error(f"❌ Error calling get tool {get_tool_name}: {e}")
    
    async def _handle_specific_item_from_list(self, service: str, list_type: str, item_id: str,
                                              context: MiddlewareContext, list_type_info: dict, user_email: str) -> None:
        """Handle specific item by extracting from cached or fresh list data."""
        raw_cache_key = f"service_list_raw_{service}_{list_type}_{user_email}"
        
        # Try to get cached raw list data
        cached_list_data = context.fastmcp_context.get_state(raw_cache_key)
        
        if not cached_list_data:
            # No cached data, fetch fresh list data
            logger.info(f"🔄 No cached list data found, fetching fresh data for {service}/{list_type}")
            
            list_tool_name = list_type_info.get("list_tool")
            if not list_tool_name:
                logger.error(f"No list tool configured for {service}/{list_type}")
                return
            
            try:
                # Call the list tool to get fresh data
                result = await self._call_tool_with_context(
                    context,
                    list_tool_name,
                    {"user_google_email": user_email}
                )
                
                # Convert result to serializable format (same logic as _handle_list_items)
                if hasattr(result, 'content'):
                    content = result.content
                    if hasattr(content, 'text'):
                        cached_list_data = content.text
                    elif hasattr(content, '__iter__') and not isinstance(content, (str, bytes)):
                        extracted_content = []
                        for item in content:
                            if hasattr(item, 'text'):
                                extracted_content.append(item.text)
                            else:
                                extracted_content.append(item)
                        if len(extracted_content) == 1 and isinstance(extracted_content[0], str):
                            try:
                                import json as json_module
                                cached_list_data = json_module.loads(extracted_content[0])
                            except:
                                cached_list_data = extracted_content[0]
                        else:
                            cached_list_data = extracted_content
                    elif hasattr(content, 'model_dump'):
                        cached_list_data = content.model_dump()
                    elif hasattr(content, 'dict'):
                        cached_list_data = content.dict()
                    else:
                        cached_list_data = content
                elif hasattr(result, 'model_dump'):
                    cached_list_data = result.model_dump()
                elif hasattr(result, 'dict'):
                    cached_list_data = result.dict()
                else:
                    cached_list_data = result
                
                # Cache the fresh data
                context.fastmcp_context.set_state(raw_cache_key, cached_list_data)
                logger.info(f"📦 Cached fresh list data with key: {raw_cache_key}")
                
            except Exception as e:
                logger.error(f"❌ Error fetching fresh list data: {e}")
                return
        else:
            logger.info(f"✅ Using cached list data for {service}/{list_type}")
        
        # Extract the specific item from the list data
        specific_item = self._extract_item_from_list(cached_list_data, item_id, list_type_info)
        
        if specific_item is None:
            logger.error(f"❌ Item '{item_id}' not found in {service}/{list_type} list")
            # Create error response
            error_result = {
                "error": f"Item '{item_id}' not found",
                "available_ids": self._get_available_ids_from_list(cached_list_data, list_type_info)
            }
        else:
            logger.info(f"✅ Found item '{item_id}' in {service}/{list_type} list")
            error_result = specific_item
        
        # Create ServiceItemDetailsResponse and store in context state
        response_model = ServiceItemDetailsResponse.from_middleware_data(
            service=service,
            list_type=list_type,
            item_id=item_id,
            tool_called=f"{list_type_info.get('list_tool')}_extract",
            user_email=user_email,
            parameters={"extracted_from_list": True, "item_id": item_id},
            result=error_result
        )
        
        cache_key = f"service_item_details_{service}_{list_type}_{item_id}"
        context.fastmcp_context.set_state(cache_key, response_model)
        logger.info(f"📦 Stored ServiceItemDetailsResponse (via list extraction) with key: {cache_key}")
    
    def _extract_item_from_list(self, list_data: Any, item_id: str, list_type_info: dict) -> Any:
        """Extract a specific item from list data by ID."""
        try:
            # Handle different list data structures
            if isinstance(list_data, dict):
                # For Gmail labels, look in different possible locations
                if "labels" in list_data:
                    items = list_data["labels"]
                elif "items" in list_data:
                    items = list_data["items"]
                elif "result" in list_data and isinstance(list_data["result"], dict) and "labels" in list_data["result"]:
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
    
    def _get_available_ids_from_list(self, list_data: Any, list_type_info: dict) -> List[str]:
        """Get list of available IDs from list data for error reporting."""
        try:
            ids = []
            
            # Handle different list data structures
            if isinstance(list_data, dict):
                if "labels" in list_data:
                    items = list_data["labels"]
                elif "items" in list_data:
                    items = list_data["items"]
                elif "result" in list_data and isinstance(list_data["result"], dict) and "labels" in list_data["result"]:
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
            if hasattr(context, 'fastmcp_context') and context.fastmcp_context:
                # Access the tool registry directly via _tool_manager
                mcp_server = context.fastmcp_context.fastmcp
                if hasattr(mcp_server, '_tool_manager') and hasattr(mcp_server._tool_manager, '_tools'):
                    tools_dict = mcp_server._tool_manager._tools
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
    
    async def _call_tool_with_context(self, context: MiddlewareContext, tool_name: str, parameters: Dict[str, Any]) -> Any:
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
        if not hasattr(context, 'fastmcp_context') or not context.fastmcp_context:
            raise RuntimeError("FastMCP context not available for tool calling")
        
        if self.enable_debug_logging:
            logger.debug(f"🔧 Calling tool {tool_name} with parameters: {parameters}")
        
        # Get the tool from the registry
        mcp_server = context.fastmcp_context.fastmcp
        if not hasattr(mcp_server, '_tool_manager') or not hasattr(mcp_server._tool_manager, '_tools'):
            raise RuntimeError("Cannot access tool registry from FastMCP server")
        
        tools_dict = mcp_server._tool_manager._tools
        
        if tool_name not in tools_dict:
            raise RuntimeError(f"Tool '{tool_name}' not found in registry")
        
        tool_instance = tools_dict[tool_name]
        
        # Get the actual callable function from the tool
        # Tools might be wrapped in different ways depending on middleware processing
        if hasattr(tool_instance, 'fn'):
            # Tool has a fn attribute that contains the actual function
            tool_func = tool_instance.fn
        elif hasattr(tool_instance, 'func'):
            # Tool has a func attribute
            tool_func = tool_instance.func
        elif hasattr(tool_instance, '__call__'):
            # Tool is directly callable
            tool_func = tool_instance
        else:
            # Try to find the actual function
            logger.error(f"Tool structure: {type(tool_instance)}, attributes: {dir(tool_instance)}")
            raise RuntimeError(f"Tool '{tool_name}' is not callable - unable to find callable function")
        
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
                if hasattr(result, '__dict__'):
                    logger.debug(f"🔍 Tool result attributes: {list(result.__dict__.keys())}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Tool {tool_name} call failed: {e}")
            raise
    
    def _create_error_response(self, error_message: str, help_message: str = "") -> str:
        """
        Create a standardized error response as JSON string.
        
        Args:
            error_message: Main error description
            help_message: Optional help or suggestion message
            
        Returns:
            JSON string with error information
        """
        response_data = {
            "error": True,
            "message": error_message,
            "timestamp": datetime.now().isoformat()
        }
        
        if help_message:
            response_data["help"] = help_message
        
        return json.dumps(response_data, indent=2)
    
