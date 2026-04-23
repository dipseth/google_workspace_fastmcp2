"""Resources that expose cached tool outputs for FastMCP2 Google Workspace Platform.

This module provides resources that cache and expose the outputs of various tools,
making frequently accessed data available as resources for better performance.

"""

import asyncio
import inspect
from datetime import datetime, timedelta

from fastmcp import Context, FastMCP
from fastmcp.resources import ResourceContent
from typing_extensions import Any, Dict, List, NotRequired, Optional, TypedDict

from auth.context import get_user_email_context
from config.enhanced_logging import setup_logger
from tools.server_tools import _get_globally_disabled_tools

logger = setup_logger()

# Simple cache for tool outputs with TTL
_tool_output_cache: Dict[str, Dict[str, Any]] = {}
_cache_ttl_minutes = 5  # Cache for 5 minutes


# ============================================================================
# TYPED DICT RESPONSE MODELS FOR TOOLS DIRECTORY RESOURCES
# ============================================================================


class DetailedToolInfo(TypedDict):
    """Detailed tool information with comprehensive parameter descriptions.

    Comprehensive tool metadata for detailed tools that use automatic authentication
    via resource templating, eliminating the need for user_google_email parameters.
    """

    name: str  # Unique tool name identifier
    description: str  # Detailed description of the tool's functionality and use cases
    parameters: Dict[
        str, str
    ]  # Dictionary mapping parameter names to their descriptions
    example: str  # Complete usage example with realistic parameter values


class DetailedToolsResponse(TypedDict):
    """Response model for detailed tools collection resource (tools://detailed/list).

    Curated list of detailed tools that use automatic resource templating for seamless
    authentication through OAuth session context without requiring email parameters.
    """

    detailed_tools: List[
        DetailedToolInfo
    ]  # List of detailed tools with comprehensive information
    count: int  # Total number of detailed tools available
    benefit: str  # Explanation of the benefits of using detailed tools
    timestamp: str  # ISO 8601 timestamp when this response was generated


class ToolsDirectoryResponse(TypedDict):
    """Response model for complete tools directory resource (tools://list/all).

    Comprehensive catalog of all available FastMCP tools organized by category with
    detailed capability descriptions, authentication requirements, and migration status.
    """

    total_tools: int  # Total number of tools registered across all categories
    active_tools: int  # Number of tools currently enabled/visible to clients
    disabled_tools_count: int  # Number of tools globally disabled via manage_tools
    total_categories: int  # Number of tool categories with at least one tool
    detailed_tools_count: int  # Number of detailed tools (no email parameter required)
    tools_by_category: Dict[
        str, Any
    ]  # Dictionary mapping category names to ToolCategoryInfo objects
    timestamp: str  # ISO 8601 timestamp when this directory was generated
    resource_templating_available: (
        bool  # Whether resource templating is implemented and available
    )
    migration_status: str  # Status message about migration to detailed tools
    error: NotRequired[
        Optional[str]
    ]  # Error message if tool directory generation failed


def _get_cache_key(user_email: str, tool_name: str, **params) -> str:
    """Generate a cache key for tool output."""
    param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
    return f"{user_email}_{tool_name}_{param_str}"


def _is_cache_valid(cache_entry: Dict[str, Any]) -> bool:
    """Check if a cache entry is still valid."""
    if "timestamp" not in cache_entry:
        return False

    cached_time = datetime.fromisoformat(cache_entry["timestamp"])
    return datetime.now() - cached_time < timedelta(minutes=_cache_ttl_minutes)


def _cache_tool_output(cache_key: str, output: Any) -> None:
    """Cache tool output with timestamp."""
    _tool_output_cache[cache_key] = {
        "output": output,
        "timestamp": datetime.now().isoformat(),
        "ttl_minutes": _cache_ttl_minutes,
    }


def _get_cached_output(cache_key: str) -> Optional[Any]:
    """Get cached output if valid."""
    if cache_key not in _tool_output_cache:
        return None

    cache_entry = _tool_output_cache[cache_key]
    if not _is_cache_valid(cache_entry):
        del _tool_output_cache[cache_key]
        return None

    return cache_entry["output"]


def setup_tool_output_resources(mcp: FastMCP, qdrant_middleware=None) -> None:
    """Setup resources that expose cached tool outputs.

    Note: The qdrant_middleware parameter is kept for backward compatibility
    but Qdrant resources are now handled directly by QdrantUnifiedMiddleware.
    """

    # REMOVED: spaces://list resource - use service://chat/spaces instead for same functionality

    # REMOVED: drive://files/recent resource - use recent://drive instead for same functionality

    @mcp.resource(
        uri="gmail://messages/recent",
        name="Recent Gmail Messages Cache",
        description="Cached list of recent Gmail messages from the last 7 days with sender information, subjects, snippets, and thread IDs - refreshed every 5 minutes for efficient email monitoring",
        mime_type="application/json",
        tags={
            "google",
            "gmail",
            "email",
            "messages",
            "cached",
            "recent",
            "performance",
            "inbox",
        },
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False,  # Results may vary due to caching
        },
    )
    async def get_recent_gmail_messages(ctx: Context) -> str:
        """Internal implementation for recent Gmail messages cache resource."""
        import json

        try:
            # Get authenticated user from context
            user_email = await get_user_email_context()
            if not user_email:
                return json.dumps(
                    {
                        "error": "No authenticated user found in current session",
                        "suggestion": "Use start_google_auth tool to authenticate first",
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            cache_key = _get_cache_key(user_email, "recent_gmail_messages")

            # Check cache first
            cached_result = _get_cached_output(cache_key)
            if cached_result:
                return json.dumps(
                    {
                        "cached": True,
                        "user_email": user_email,
                        "data": cached_result,
                        "cache_timestamp": _tool_output_cache[cache_key]["timestamp"],
                        "ttl_minutes": _cache_ttl_minutes,
                    },
                    default=str,
                )

            # Cache miss - fetch fresh data using FastMCP tool registry (following middleware pattern)
            if not ctx.fastmcp:
                return json.dumps(
                    {
                        "error": "FastMCP context not available",
                        "cached": False,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            mcp_server = ctx.fastmcp
            from fastmcp.tools import Tool

            components = mcp_server.local_provider._components
            tools_dict = {v.name: v for v in components.values() if isinstance(v, Tool)}

            if not tools_dict:
                return json.dumps(
                    {
                        "error": "Cannot access tool registry from FastMCP server",
                        "cached": False,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            tool_name = "search_gmail_messages"

            if tool_name not in tools_dict:
                return json.dumps(
                    {
                        "error": f"Tool '{tool_name}' not found in registry",
                        "available_tools": list(tools_dict.keys()),
                        "cached": False,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            # Get the tool and call it (following middleware pattern)
            tool_instance = tools_dict[tool_name]

            tool_func = tool_instance.fn

            # Call the tool with parameters
            tool_params = {
                "user_google_email": user_email,
                "query": "newer_than:7d",  # Last 7 days
                "page_size": 10,
            }

            if inspect.iscoroutinefunction(tool_func):
                messages_result = await tool_func(**tool_params)
            else:
                messages_result = tool_func(**tool_params)

            # Handle the structured response from the Gmail tool
            if getattr(messages_result, "error", None):
                return json.dumps(
                    {
                        "error": f"Gmail tool error: {messages_result.error}",
                        "cached": False,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            # Extract messages from the structured response
            messages = getattr(messages_result, "messages", [])

            # Format for the resource response
            formatted_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    formatted_msg = {
                        "id": msg.get("id"),
                        "thread_id": msg.get("threadId"),
                        "snippet": msg.get("snippet", ""),
                        "subject": msg.get("subject", "No Subject"),
                        "from": msg.get("sender", "Unknown Sender"),
                        "date": msg.get("date", "Unknown Date"),
                        "labels": msg.get("labelIds", []),
                    }
                    formatted_messages.append(formatted_msg)

            output_data = {
                "user_email": user_email,
                "total_messages": len(formatted_messages),
                "messages": formatted_messages,
                "query": "Recent messages (last 7 days)",
                "tool_used": "search_gmail_messages",
                "timestamp": datetime.now().isoformat(),
            }

            # Cache the result
            _cache_tool_output(cache_key, output_data)

            return json.dumps(
                {
                    "cached": False,
                    "user_email": user_email,
                    "data": output_data,
                    "cache_timestamp": datetime.now().isoformat(),
                    "ttl_minutes": _cache_ttl_minutes,
                },
                default=str,
            )

        except Exception as e:
            logger.error(f"Error fetching recent Gmail messages: {e}")
            return json.dumps(
                {
                    "error": f"Failed to fetch recent Gmail messages: {str(e)}",
                    "cached": False,
                    "timestamp": datetime.now().isoformat(),
                }
            )

    @mcp.resource(
        uri="tools://list/all",
        name="Complete Tools Directory",
        description="Comprehensive catalog of all available tools organized by category including Drive, Gmail, Calendar, Chat, Forms, Docs, Sheets, and authentication tools with detailed capability descriptions",
        mime_type="application/json",
        tags={
            "tools",
            "directory",
            "catalog",
            "discovery",
            "google",
            "workspace",
            "detailed",
            "legacy",
        },
        meta={
            "response_model": "ToolsDirectoryResponse",
            "detailed": True,
            "comprehensive": True,
            "dynamic": True,
        },
    )
    async def get_all_tools_list(ctx: Context) -> list[ResourceContent]:
        """Get comprehensive catalog of all available FastMCP tools organized by category.

        Dynamically discovers and categorizes all registered FastMCP tools including Drive,
        Gmail, Calendar, Chat, Forms, Docs, Sheets, authentication tools, and utility tools.
        Provides detailed capability descriptions, authentication requirements, and migration
        status for both detailed and legacy tools.

        This resource performs real-time tool discovery by introspecting the FastMCP server
        instance, analyzing tool schemas, and categorizing tools by service type and
        authentication requirements.

        Args:
            ctx: FastMCP Context object providing access to server state, tool registry,
                and logging capabilities for dynamic tool discovery

        Returns:
            ToolsDirectoryResponse: Complete tools catalog including:
            - Total tool count across all categories and services
            - Tools organized by category (Gmail, Drive, Calendar, etc.)
            - Detailed vs legacy tool counts and migration status
            - Tool metadata including parameters and descriptions
            - Resource templating availability status
            - Error details if tool discovery fails

        Tool Categories:
            - Detailed Tools: Use automatic authentication (no email params)
            - Service Tools: Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Chat, Photos
            - System Tools: Authentication, Qdrant search, module wrappers
            - Utility Tools: Other helper and system tools

        Example Response:
            {
                "total_tools": 65,
                "total_categories": 12,
                "detailed_tools_count": 8,
                "tools_by_category": {
                    "gmail_tools": {
                        "description": "Gmail email management tools",
                        "tool_count": 11,
                        "requires_email": true,
                        "tools": [...]
                    },
                    "detailed_tools": {
                        "description": "New tools that use resource templating",
                        "tool_count": 8,
                        "requires_email": false,
                        "tools": [...]
                    }
                },
                "resource_templating_available": true,
                "migration_status": "✅ Resource templating implemented - detailed tools available!",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        try:
            # Access the FastMCP server instance through context
            fastmcp_server = ctx.fastmcp

            # Log FastMCP server structure for debugging
            await ctx.debug(f"FastMCP server type: {type(fastmcp_server)}")
            await ctx.debug(f"FastMCP server attributes: {dir(fastmcp_server)}")

            from fastmcp.tools import Tool

            components = fastmcp_server.local_provider._components
            registered_tools = {
                v.name: v for v in components.values() if isinstance(v, Tool)
            }
            await ctx.info(f"🔍 Found {len(registered_tools)} tools via local_provider")

            # Categorize tools dynamically based on their names and tags
            categories = {
                "detailed_tools": {
                    "description": "New tools that use resource templating (no email params needed)",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": False,
                },
                "drive_tools": {
                    "description": "Google Drive file management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "gmail_tools": {
                    "description": "Gmail email management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "docs_tools": {
                    "description": "Google Docs document management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "forms_tools": {
                    "description": "Google Forms creation and management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "calendar_tools": {
                    "description": "Google Calendar event management tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "slides_tools": {
                    "description": "Google Slides presentation tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "sheets_tools": {
                    "description": "Google Sheets spreadsheet tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "chat_tools": {
                    "description": "Google Chat messaging tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "photos_tools": {
                    "description": "Google Photos tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": True,
                },
                "auth_tools": {
                    "description": "Authentication and system tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": "mixed",
                },
                "qdrant_tools": {
                    "description": "Qdrant search and analytics tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": False,
                },
                "module_tools": {
                    "description": "Module wrapper and introspection tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": False,
                },
                "other_tools": {
                    "description": "Other utility and system tools",
                    "tools": [],
                    "tool_count": 0,
                    "requires_email": "mixed",
                },
            }

            # Categorize each tool
            for tool_name, tool_instance in registered_tools.items():
                await ctx.debug(f"Processing tool: {tool_name}")

                # Get tool metadata - be more defensive about accessing attributes
                tool_info = {
                    "name": tool_name,
                    "description": "No description available",
                    "tags": [],
                    "parameters": [],
                    "detailed": False,
                }

                if tool_instance.description:
                    tool_info["description"] = tool_instance.description

                if tool_instance.tags:
                    tool_info["tags"] = list(tool_instance.tags)

                # Extract parameter names from the tool's parameters schema
                parameter_names = []
                params_schema = tool_instance.parameters
                if isinstance(params_schema, dict) and "properties" in params_schema:
                    parameter_names = list(params_schema["properties"].keys())
                    tool_info["parameters"] = parameter_names

                # Check if it's an detailed tool (no user_google_email parameter)
                is_detailed = "user_google_email" not in parameter_names
                tool_info["detailed"] = is_detailed

                # Categorize based on name patterns and tags
                categorized = False

                # Detailed tools (no email parameter)
                if is_detailed and any(
                    keyword in tool_name for keyword in ["my_", "_my", "get_my_"]
                ):
                    categories["detailed_tools"]["tools"].append(tool_info)
                    categories["detailed_tools"]["tool_count"] += 1
                    categorized = True

                # Service-specific tools
                elif any(keyword in tool_name for keyword in ["drive", "file"]):
                    categories["drive_tools"]["tools"].append(tool_info)
                    categories["drive_tools"]["tool_count"] += 1
                    categorized = True
                elif any(
                    keyword in tool_name
                    for keyword in ["gmail", "email", "message", "draft"]
                ):
                    categories["gmail_tools"]["tools"].append(tool_info)
                    categories["gmail_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["doc", "document"]):
                    categories["docs_tools"]["tools"].append(tool_info)
                    categories["docs_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["form", "response"]):
                    categories["forms_tools"]["tools"].append(tool_info)
                    categories["forms_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["calendar", "event"]):
                    categories["calendar_tools"]["tools"].append(tool_info)
                    categories["calendar_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["slide", "presentation"]):
                    categories["slides_tools"]["tools"].append(tool_info)
                    categories["slides_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["sheet", "spreadsheet"]):
                    categories["sheets_tools"]["tools"].append(tool_info)
                    categories["sheets_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["chat", "space", "card"]):
                    categories["chat_tools"]["tools"].append(tool_info)
                    categories["chat_tools"]["tool_count"] += 1
                    categorized = True
                elif any(keyword in tool_name for keyword in ["photo", "album"]):
                    categories["photos_tools"]["tools"].append(tool_info)
                    categories["photos_tools"]["tool_count"] += 1
                    categorized = True
                elif any(
                    keyword in tool_name
                    for keyword in ["auth", "credential", "session", "oauth"]
                ):
                    categories["auth_tools"]["tools"].append(tool_info)
                    categories["auth_tools"]["tool_count"] += 1
                    categorized = True
                elif any(
                    keyword in tool_name
                    for keyword in ["qdrant", "search", "vector", "embed"]
                ):
                    categories["qdrant_tools"]["tools"].append(tool_info)
                    categories["qdrant_tools"]["tool_count"] += 1
                    categorized = True
                elif any(
                    keyword in tool_name for keyword in ["module", "wrap", "component"]
                ):
                    categories["module_tools"]["tools"].append(tool_info)
                    categories["module_tools"]["tool_count"] += 1
                    categorized = True

                # Uncategorized tools go to "other"
                if not categorized:
                    categories["other_tools"]["tools"].append(tool_info)
                    categories["other_tools"]["tool_count"] += 1

            # Calculate totals
            total_tools = len(registered_tools)
            detailed_tools_count = categories["detailed_tools"]["tool_count"]

            # Get globally disabled tools to calculate active count
            disabled_tools = _get_globally_disabled_tools(fastmcp_server)
            disabled_tools_count = len(disabled_tools)
            active_tools = total_tools - disabled_tools_count

            # Log discovery results
            await ctx.info(
                f"🔍 Dynamic tool discovery: Found {total_tools} tools, {active_tools} active, {disabled_tools_count} disabled"
            )

            response = ToolsDirectoryResponse(
                total_tools=total_tools,
                active_tools=active_tools,
                disabled_tools_count=disabled_tools_count,
                total_categories=len(
                    [cat for cat in categories.values() if cat["tool_count"] > 0]
                ),
                detailed_tools_count=detailed_tools_count,
                tools_by_category=categories,
                timestamp=datetime.now().isoformat(),
                resource_templating_available=True,
                migration_status="✅ Resource templating implemented - detailed tools available!",
            )
            return [ResourceContent(response, mime_type="application/json")]

        except Exception as e:
            await ctx.error(f"Error during dynamic tool discovery: {e}")
            # Fallback to minimal response
            response = ToolsDirectoryResponse(
                total_tools=0,
                active_tools=0,
                disabled_tools_count=0,
                total_categories=0,
                detailed_tools_count=0,
                tools_by_category={},
                timestamp=datetime.now().isoformat(),
                resource_templating_available=False,
                migration_status="❌ Error during tool discovery",
                error=str(e),
            )
            return [ResourceContent(response, mime_type="application/json")]

    @mcp.resource(
        uri="tools://detailed/list",
        name="Detailed Tools Collection",
        description="Curated list of detailed tools that use automatic resource templating - no user_google_email parameters required, seamless authentication through OAuth session context",
        mime_type="application/json",
        tags={
            "tools",
            "detailed",
            "templating",
            "oauth",
            "seamless",
            "modern",
            "no-email",
        },
        meta={
            "response_model": "DetailedToolsResponse",
            "detailed": True,
            "oauth_enabled": True,
        },
    )
    async def get_detailed_tools_only(ctx: Context) -> list[ResourceContent]:
        """Get curated list of detailed tools that use automatic resource templating.

        Dynamically discovers and returns only detailed tools that utilize automatic
        authentication through OAuth session context, eliminating the need for
        user_google_email parameters. These tools provide seamless authentication
        and improved developer experience.

        Detailed tools are identified by the absence of user_google_email parameters
        in their schema, indicating they use the newer resource templating approach
        for authentication injection.

        Args:
            ctx: FastMCP Context object providing access to server state and tool
                registry for dynamic detailed tool discovery

        Returns:
            DetailedToolsResponse: Curated detailed tools collection including:
            - List of detailed tools with comprehensive parameter descriptions
            - Complete usage examples with realistic parameter values
            - Benefits explanation of detailed authentication approach
            - Total count of available detailed tools
            - Error details if detailed tool discovery fails

        Benefits of Detailed Tools:
            - No user_google_email parameter required
            - Automatic OAuth session context injection
            - Cleaner API with fewer required parameters
            - Seamless authentication through middleware
            - Modern resource templating architecture

        Example Response:
            {
                "detailed_tools": [
                    {
                        "name": "get_my_recent_files",
                        "description": "Get recent files for the authenticated user",
                        "parameters": {
                            "days": "Number of days back to search (default: 7)",
                            "file_type": "Type of files to return (optional)"
                        },
                        "example": "get_my_recent_files(days=14, file_type=\"document\")"
                    }
                ],
                "count": 8,
                "benefit": "No user_google_email parameter required - uses OAuth session automatically",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        """
        try:
            # Access the FastMCP server instance through context
            fastmcp_server = ctx.fastmcp

            from fastmcp.tools import Tool

            components = fastmcp_server.local_provider._components
            registered_tools = {
                v.name: v for v in components.values() if isinstance(v, Tool)
            }

            if not registered_tools:
                await ctx.warning("Could not access tools from FastMCP server")
                return [
                    ResourceContent(
                        DetailedToolsResponse(
                            detailed_tools=[],
                            count=0,
                            benefit="No user_google_email parameter required - uses OAuth session automatically",
                            timestamp=datetime.now().isoformat(),
                        ),
                        mime_type="application/json",
                    )
                ]

            # Find detailed tools (tools without user_google_email parameter)
            detailed_tools = []

            for tool_name, tool_instance in registered_tools.items():
                # Get tool parameters from the parameters schema
                parameters = {}
                parameter_names = []

                params_schema = tool_instance.parameters
                if isinstance(params_schema, dict) and "properties" in params_schema:
                    parameter_names = list(params_schema["properties"].keys())
                    for param_name, param_info in params_schema["properties"].items():
                        if isinstance(param_info, dict):
                            parameters[param_name] = param_info.get(
                                "description", f"{param_name} parameter"
                            )
                        else:
                            parameters[param_name] = f"{param_name} parameter"

                # Check if it's a detailed tool (no user_google_email parameter)
                is_detailed = "user_google_email" not in parameter_names

                # Include tools that are clearly "detailed" based on naming or characteristics
                if is_detailed and (
                    any(keyword in tool_name for keyword in ["my_", "_my", "get_my_"])
                    or "template" in tool_instance.tags
                    or "detailed" in tool_instance.tags
                ):
                    description = (
                        tool_instance.description
                        or "Detailed tool with automatic authentication"
                    )

                    # Create a more meaningful example
                    example = f"{tool_name}()"
                    if parameters:
                        # Create a basic example with parameter names
                        param_examples = []
                        for param_name in list(parameters.keys())[:3]:  # First 3 params
                            if "query" in param_name:
                                param_examples.append(f'{param_name}="search term"')
                            elif "summary" in param_name or "title" in param_name:
                                param_examples.append(f'{param_name}="Example Title"')
                            elif "time" in param_name:
                                param_examples.append(
                                    f'{param_name}="2025-02-01T10:00:00Z"'
                                )
                            else:
                                param_examples.append(f'{param_name}="value"')

                        if param_examples:
                            example = f"{tool_name}({', '.join(param_examples)})"

                    detailed_tool = DetailedToolInfo(
                        name=tool_name,
                        description=description,
                        parameters=parameters,
                        example=example,
                    )
                    detailed_tools.append(detailed_tool)

            # Log discovery results
            await ctx.info(
                f"🔍 Detailed tool discovery: Found {len(detailed_tools)} detailed tools out of {len(registered_tools)} total"
            )

            return [
                ResourceContent(
                    DetailedToolsResponse(
                        detailed_tools=detailed_tools,
                        count=len(detailed_tools),
                        benefit="No user_google_email parameter required - uses OAuth session automatically",
                        timestamp=datetime.now().isoformat(),
                    ),
                    mime_type="application/json",
                )
            ]

        except Exception as e:
            await ctx.error(f"Error during detailed tool discovery: {e}")
            # Fallback to empty response
            return [
                ResourceContent(
                    DetailedToolsResponse(
                        detailed_tools=[],
                        count=0,
                        benefit="No user_google_email parameter required - uses OAuth session automatically",
                        timestamp=datetime.now().isoformat(),
                    ),
                    mime_type="application/json",
                )
            ]

    # COMMENTED OUT: Original cache://status resource - replaced with qdrant://cache
    # @mcp.resource(
    #     uri="cache://status",
    #     name="Tool Output Cache Status",
    #     description="Comprehensive status of the tool output cache including total entries, valid/expired counts, TTL information, and detailed cache key analysis for performance monitoring",
    #     mime_type="application/json",
    #     tags={"cache", "status", "performance", "monitoring", "ttl", "analytics", "system"},
    #     annotations={
    #         "readOnlyHint": True,
    #         "idempotentHint": True  # Status reporting is idempotent
    #     }
    # )
    # async def get_cache_status(ctx: Context) -> dict:
    #     """Internal implementation for tool output cache status resource."""
    #     try:
    #         user_email = get_current_user_email_simple()
    #
    #         # Analyze cache entries
    #         cache_info = []
    #         total_entries = 0
    #         valid_entries = 0
    #
    #         for cache_key, cache_entry in _tool_output_cache.items():
    #             total_entries += 1
    #             is_valid = _is_cache_valid(cache_entry)
    #             if is_valid:
    #                 valid_entries += 1
    #
    #             # Extract user email and tool name from cache key
    #             parts = cache_key.split('_', 2)
    #             if len(parts) >= 2:
    #                 key_user_email = parts[0] + '@' + parts[1].split('@')[0] if '@' in parts[1] else 'unknown'
    #                 tool_name = parts[2] if len(parts) > 2 else 'unknown'
    #             else:
    #                 key_user_email = 'unknown'
    #                 tool_name = 'unknown'
    #
    #         cache_info.append({
    #             "cache_key": cache_key,
    #             "user_email": key_user_email,
    #             "tool_name": tool_name,
    #             "timestamp": cache_entry.get("timestamp", "unknown"),
    #             "valid": is_valid,
    #             "ttl_minutes": cache_entry.get("ttl_minutes", _cache_ttl_minutes)
    #         })
    #
    #         return {
    #             "user_email": user_email,
    #             "total_cache_entries": total_entries,
    #             "valid_cache_entries": valid_entries,
    #             "expired_cache_entries": total_entries - valid_entries,
    #             "default_ttl_minutes": _cache_ttl_minutes,
    #             "cache_entries": cache_info,
    #             "timestamp": datetime.now().isoformat()
    #         }
    #
    #     except ValueError as e:
    #         return {
    #             "error": f"Authentication error: {str(e)}",
    #             "timestamp": datetime.now().isoformat()
    #         }
    #     except Exception as e:
    #         logger.error(f"Error getting cache status: {e}")
    #         return {
    #             "error": f"Failed to get cache status: {str(e)}",
    #             "timestamp": datetime.now().isoformat()
    #         }

    # @mcp.resource(
    #     uri="cache://clear",
    #     name="Clear Tool Output Cache",
    #     description="Administrative resource to clear the tool output cache for the current user, forcing fresh API calls and removing stale cached data with detailed operation statistics",
    #     mime_type="application/json",
    #     tags={"cache", "clear", "admin", "reset", "performance", "maintenance", "system"},
    #     annotations={
    #         "readOnlyHint": False,  # This resource modifies state (clears cache)
    #         "idempotentHint": True  # Clearing an already empty cache is safe
    #     }
    # )
    # async def clear_cache(ctx: Context) -> dict:
    #     """Internal implementation for cache clearing resource."""
    #     try:
    #         user_email = get_current_user_email_simple()

    #         # Count entries before clearing
    #         entries_before = len(_tool_output_cache)

    #         # Clear cache entries for this user
    #         keys_to_remove = []
    #         for cache_key in _tool_output_cache.keys():
    #             if cache_key.startswith(user_email.replace('@', '_at_')):
    #                 keys_to_remove.append(cache_key)

    #         for key in keys_to_remove:
    #             del _tool_output_cache[key]

    #         entries_after = len(_tool_output_cache)
    #         entries_cleared = entries_before - entries_after

    #         return {
    #             "user_email": user_email,
    #             "entries_cleared": entries_cleared,
    #             "entries_before": entries_before,
    #             "entries_after": entries_after,
    #             "timestamp": datetime.now().isoformat(),
    #             "status": "Cache cleared successfully"
    #         }

    #     except ValueError as e:
    #         return {
    #             "error": f"Authentication error: {str(e)}",
    #             "timestamp": datetime.now().isoformat()
    #         }
    #     except Exception as e:
    #         logger.error(f"Error clearing cache: {e}")
    #         return {
    #             "error": f"Failed to clear cache: {str(e)}",
    #             "timestamp": datetime.now().isoformat()
    #         }

    # logger.info("✅ Tool output resources registered with caching (Qdrant resources handled by middleware)")
