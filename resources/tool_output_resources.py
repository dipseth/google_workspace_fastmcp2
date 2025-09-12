"""Resources that expose cached tool outputs for FastMCP2 Google Workspace Platform.

This module provides resources that cache and expose the outputs of various tools,
making frequently accessed data available as resources for better performance.

Note: Qdrant-specific resources (qdrant://*) are now handled directly by the
QdrantUnifiedMiddleware using the on_read_resource hook for better integration.
"""

import asyncio
import json
import logging
from typing_extensions import Dict, Any, Optional
from datetime import datetime, timedelta

from fastmcp import FastMCP, Context
from resources.user_resources import get_current_user_email_simple
from auth.context import get_injected_service
from auth.service_helpers import request_gmail_service, request_service

logger = logging.getLogger(__name__)

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
        "ttl_minutes": _cache_ttl_minutes
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
        tags={"google", "gmail", "email", "messages", "cached", "recent", "performance", "inbox"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False  # Results may vary due to caching
        }
    )
    async def get_recent_gmail_messages(ctx: Context) -> dict:
        """Internal implementation for recent Gmail messages cache resource."""
        try:
            user_email = get_current_user_email_simple()
            cache_key = _get_cache_key(user_email, "recent_gmail_messages")
            
            # Check cache first
            cached_result = _get_cached_output(cache_key)
            if cached_result:
                return {
                    "cached": True,
                    "user_email": user_email,
                    "data": cached_result,
                    "cache_timestamp": _tool_output_cache[cache_key]["timestamp"],
                    "ttl_minutes": _cache_ttl_minutes
                }
            
            # Cache miss - fetch fresh data
            gmail_key = request_gmail_service()  # Uses correct scopes from registry
            gmail_service = get_injected_service(gmail_key)
            
            # Get recent messages
            results = gmail_service.users().messages().list(
                userId='me',
                q='newer_than:7d',  # Last 7 days
                maxResults=10
            ).execute()
            
            messages = results.get('messages', [])
            
            # Get message details
            detailed_messages = []
            for msg in messages[:10]:  # Limit to 10 for performance
                try:
                    message = gmail_service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='metadata'
                    ).execute()
                    
                    # Extract headers
                    headers = message.get('payload', {}).get('headers', [])
                    msg_data = {
                        'id': message['id'],
                        'thread_id': message['threadId'],
                        'snippet': message.get('snippet', ''),
                    }
                    
                    # Parse headers
                    for header in headers:
                        if header['name'].lower() == 'subject':
                            msg_data['subject'] = header['value']
                        elif header['name'].lower() == 'from':
                            msg_data['from'] = header['value']
                        elif header['name'].lower() == 'date':
                            msg_data['date'] = header['value']
                    
                    detailed_messages.append(msg_data)
                    
                except Exception as e:
                    logger.warning(f"Error getting message details for {msg['id']}: {e}")
            
            output_data = {
                "user_email": user_email,
                "total_messages": len(detailed_messages),
                "messages": detailed_messages,
                "query": "Recent messages (last 7 days)",
                "timestamp": datetime.now().isoformat()
            }
            
            # Cache the result
            _cache_tool_output(cache_key, output_data)
            
            return {
                "cached": False,
                "user_email": user_email,
                "data": output_data,
                "cache_timestamp": datetime.now().isoformat(),
                "ttl_minutes": _cache_ttl_minutes
            }
            
        except ValueError as e:
            return {
                "error": f"Authentication error: {str(e)}",
                "cached": False,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error fetching recent Gmail messages: {e}")
            return {
                "error": f"Failed to fetch recent Gmail messages: {str(e)}",
                "cached": False,
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="calendar://events/today",
        name="Today's Calendar Events Cache",
        description="Cached list of today's calendar events with start/end times, attendees, locations, and meeting links - automatically updated every 5 minutes for current day schedule management",
        mime_type="application/json",
        tags={"google", "calendar", "events", "today", "cached", "schedule", "meetings", "performance"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False  # Results may vary due to caching
        }
    )
    async def get_todays_calendar_events(ctx: Context) -> dict:
        """Internal implementation for today's calendar events cache resource."""
        try:
            user_email = get_current_user_email_simple()
            cache_key = _get_cache_key(user_email, "todays_events")
            
            # Check cache first
            cached_result = _get_cached_output(cache_key)
            if cached_result:
                return {
                    "cached": True,
                    "user_email": user_email,
                    "data": cached_result,
                    "cache_timestamp": _tool_output_cache[cache_key]["timestamp"],
                    "ttl_minutes": _cache_ttl_minutes
                }
            
            # Cache miss - fetch fresh data
            calendar_key = request_service("calendar")  # Uses correct scopes from registry
            calendar_service = get_injected_service(calendar_key)
            
            # Get today's events
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start.replace(hour=23, minute=59, second=59)
            
            events_result = calendar_service.events().list(
                calendarId='primary',
                timeMin=today_start.isoformat(),
                timeMax=today_end.isoformat(),
                singleEvents=True,
                orderBy='startTime',
                maxResults=50
            ).execute()
            
            events = events_result.get('items', [])
            
            # Format events
            formatted_events = []
            for event in events:
                event_info = {
                    'id': event.get('id'),
                    'summary': event.get('summary', 'No Title'),
                    'start': event.get('start', {}),
                    'end': event.get('end', {}),
                    'description': event.get('description', ''),
                    'location': event.get('location', ''),
                    'attendees': [a.get('email') for a in event.get('attendees', [])],
                    'htmlLink': event.get('htmlLink')
                }
                formatted_events.append(event_info)
            
            output_data = {
                "user_email": user_email,
                "total_events": len(formatted_events),
                "events": formatted_events,
                "date": today_start.strftime("%Y-%m-%d"),
                "timestamp": datetime.now().isoformat()
            }
            
            # Cache the result
            _cache_tool_output(cache_key, output_data)
            
            return {
                "cached": False,
                "user_email": user_email,
                "data": output_data,
                "cache_timestamp": datetime.now().isoformat(),
                "ttl_minutes": _cache_ttl_minutes
            }
            
        except ValueError as e:
            return {
                "error": f"Authentication error: {str(e)}",
                "cached": False,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error fetching today's calendar events: {e}")
            return {
                "error": f"Failed to fetch today's calendar events: {str(e)}",
                "cached": False,
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="cache://status",
        name="Tool Output Cache Status",
        description="Comprehensive status of the tool output cache including total entries, valid/expired counts, TTL information, and detailed cache key analysis for performance monitoring",
        mime_type="application/json",
        tags={"cache", "status", "performance", "monitoring", "ttl", "analytics", "system"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True  # Status reporting is idempotent
        }
    )
    async def get_cache_status(ctx: Context) -> dict:
        """Internal implementation for tool output cache status resource."""
        try:
            user_email = get_current_user_email_simple()
            
            # Analyze cache entries
            cache_info = []
            total_entries = 0
            valid_entries = 0
            
            for cache_key, cache_entry in _tool_output_cache.items():
                total_entries += 1
                is_valid = _is_cache_valid(cache_entry)
                if is_valid:
                    valid_entries += 1
                
                # Extract user email and tool name from cache key
                parts = cache_key.split('_', 2)
                if len(parts) >= 2:
                    key_user_email = parts[0] + '@' + parts[1].split('@')[0] if '@' in parts[1] else 'unknown'
                    tool_name = parts[2] if len(parts) > 2 else 'unknown'
                else:
                    key_user_email = 'unknown'
                    tool_name = 'unknown'
                
                cache_info.append({
                    "cache_key": cache_key,
                    "user_email": key_user_email,
                    "tool_name": tool_name,
                    "timestamp": cache_entry.get("timestamp", "unknown"),
                    "valid": is_valid,
                    "ttl_minutes": cache_entry.get("ttl_minutes", _cache_ttl_minutes)
                })
            
            return {
                "user_email": user_email,
                "total_cache_entries": total_entries,
                "valid_cache_entries": valid_entries,
                "expired_cache_entries": total_entries - valid_entries,
                "default_ttl_minutes": _cache_ttl_minutes,
                "cache_entries": cache_info,
                "timestamp": datetime.now().isoformat()
            }
            
        except ValueError as e:
            return {
                "error": f"Authentication error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting cache status: {e}")
            return {
                "error": f"Failed to get cache status: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="cache://clear",
        name="Clear Tool Output Cache",
        description="Administrative resource to clear the tool output cache for the current user, forcing fresh API calls and removing stale cached data with detailed operation statistics",
        mime_type="application/json",
        tags={"cache", "clear", "admin", "reset", "performance", "maintenance", "system"},
        annotations={
            "readOnlyHint": False,  # This resource modifies state (clears cache)
            "idempotentHint": True  # Clearing an already empty cache is safe
        }
    )
    async def clear_cache(ctx: Context) -> dict:
        """Internal implementation for cache clearing resource."""
        try:
            user_email = get_current_user_email_simple()
            
            # Count entries before clearing
            entries_before = len(_tool_output_cache)
            
            # Clear cache entries for this user
            keys_to_remove = []
            for cache_key in _tool_output_cache.keys():
                if cache_key.startswith(user_email.replace('@', '_at_')):
                    keys_to_remove.append(cache_key)
            
            for key in keys_to_remove:
                del _tool_output_cache[key]
            
            entries_after = len(_tool_output_cache)
            entries_cleared = entries_before - entries_after
            
            return {
                "user_email": user_email,
                "entries_cleared": entries_cleared,
                "entries_before": entries_before,
                "entries_after": entries_after,
                "timestamp": datetime.now().isoformat(),
                "status": "Cache cleared successfully"
            }
            
        except ValueError as e:
            return {
                "error": f"Authentication error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return {
                "error": f"Failed to clear cache: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    logger.info("✅ Tool output resources registered with caching (Qdrant resources handled by middleware)")