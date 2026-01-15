"""Resources that expose cached tool outputs for FastMCP2 Google Workspace Platform.

This module provides resources that cache and expose the outputs of various tools,
making frequently accessed data available as resources for better performance.

"""

import asyncio
from datetime import datetime, timedelta

from fastmcp import Context, FastMCP
from typing_extensions import Any, Dict, Optional

from auth.context import get_user_email_context
from config.enhanced_logging import setup_logger

logger = setup_logger()

# Simple cache for tool outputs with TTL
_tool_output_cache: Dict[str, Dict[str, Any]] = {}
_cache_ttl_minutes = 5  # Cache for 5 minutes


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
    async def get_recent_gmail_messages(ctx: Context) -> dict:
        """Internal implementation for recent Gmail messages cache resource."""
        try:
            # Get authenticated user from context
            user_email = get_user_email_context()
            if not user_email:
                return {
                    "error": "No authenticated user found in current session",
                    "suggestion": "Use start_google_auth tool to authenticate first",
                    "timestamp": datetime.now().isoformat(),
                }

            cache_key = _get_cache_key(user_email, "recent_gmail_messages")

            # Check cache first
            cached_result = _get_cached_output(cache_key)
            if cached_result:
                return {
                    "cached": True,
                    "user_email": user_email,
                    "data": cached_result,
                    "cache_timestamp": _tool_output_cache[cache_key]["timestamp"],
                    "ttl_minutes": _cache_ttl_minutes,
                }

            # Cache miss - fetch fresh data using FastMCP tool registry (following middleware pattern)
            if not hasattr(ctx, "fastmcp") or not ctx.fastmcp:
                return {
                    "error": "FastMCP context not available",
                    "cached": False,
                    "timestamp": datetime.now().isoformat(),
                }

            # Access the tool registry directly via _tool_manager (following middleware pattern)
            mcp_server = ctx.fastmcp
            if not hasattr(mcp_server, "_tool_manager") or not hasattr(
                mcp_server._tool_manager, "_tools"
            ):
                return {
                    "error": "Cannot access tool registry from FastMCP server",
                    "cached": False,
                    "timestamp": datetime.now().isoformat(),
                }

            tools_dict = mcp_server._tool_manager._tools
            tool_name = "search_gmail_messages"

            if tool_name not in tools_dict:
                return {
                    "error": f"Tool '{tool_name}' not found in registry",
                    "available_tools": list(tools_dict.keys()),
                    "cached": False,
                    "timestamp": datetime.now().isoformat(),
                }

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
                    "cached": False,
                    "timestamp": datetime.now().isoformat(),
                }

            # Call the tool with parameters
            tool_params = {
                "user_google_email": user_email,
                "query": "newer_than:7d",  # Last 7 days
                "page_size": 10,
            }

            if asyncio.iscoroutinefunction(tool_func):
                messages_result = await tool_func(**tool_params)
            else:
                messages_result = tool_func(**tool_params)

            # Handle the structured response from the Gmail tool
            if hasattr(messages_result, "error") and messages_result.error:
                return {
                    "error": f"Gmail tool error: {messages_result.error}",
                    "cached": False,
                    "timestamp": datetime.now().isoformat(),
                }

            # Extract messages from the structured response
            messages = (
                getattr(messages_result, "messages", [])
                if hasattr(messages_result, "messages")
                else []
            )

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

            return {
                "cached": False,
                "user_email": user_email,
                "data": output_data,
                "cache_timestamp": datetime.now().isoformat(),
                "ttl_minutes": _cache_ttl_minutes,
            }

        except Exception as e:
            logger.error(f"Error fetching recent Gmail messages: {e}")
            return {
                "error": f"Failed to fetch recent Gmail messages: {str(e)}",
                "cached": False,
                "timestamp": datetime.now().isoformat(),
            }

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
