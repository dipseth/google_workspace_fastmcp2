"""Resources that expose cached tool outputs for FastMCP2 Google Workspace Platform.

This module provides resources that cache and expose the outputs of various tools,
making frequently accessed data available as resources for better performance.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import json

from fastmcp import FastMCP, Context
from resources.user_resources import get_current_user_email_simple
from auth.context import request_google_service, get_injected_service

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
    """Setup resources that expose cached tool outputs."""
    
    @mcp.resource(
        uri="spaces://list",
        name="Google Chat Spaces Cache",
        description="Cached list of Google Chat spaces for the current user with room details, member counts, and space types - automatically refreshed every 5 minutes for optimal performance",
        mime_type="application/json",
        tags={"google", "chat", "spaces", "cached", "rooms", "performance", "messaging"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False  # Results may vary due to caching
        }
    )
    async def get_chat_spaces_list(ctx: Context) -> dict:
        """Internal implementation for Google Chat spaces cache resource."""
        try:
            user_email = get_current_user_email_simple()
            cache_key = _get_cache_key(user_email, "list_spaces")
            
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
            chat_key = request_google_service("chat", ["chat_read"])
            chat_service = get_injected_service(chat_key)
            
            # Call the Chat API
            results = chat_service.spaces().list(pageSize=100).execute()
            spaces = results.get('spaces', [])
            
            # Format the output similar to list_spaces tool
            formatted_spaces = []
            for space in spaces:
                space_info = {
                    'name': space.get('name', ''),
                    'displayName': space.get('displayName', 'Unnamed Space'),
                    'type': space.get('type', 'UNKNOWN'),
                    'spaceType': space.get('spaceType', 'UNKNOWN'),
                    'memberCount': len(space.get('spaceDetails', {}).get('members', [])),
                    'threaded': space.get('spaceDetails', {}).get('guidelines', {}).get('threaded', False)
                }
                formatted_spaces.append(space_info)
            
            output_data = {
                "user_email": user_email,
                "total_spaces": len(formatted_spaces),
                "spaces": formatted_spaces,
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
            logger.error(f"Error fetching chat spaces: {e}")
            return {
                "error": f"Failed to fetch chat spaces: {str(e)}",
                "cached": False,
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="drive://files/recent",
        name="Recent Google Drive Files Cache",
        description="Cached list of recently modified Google Drive files with metadata including file names, sizes, modification times, and sharing links - updated every 5 minutes for quick access",
        mime_type="application/json",
        tags={"google", "drive", "files", "cached", "recent", "performance", "storage", "documents"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False  # Results may vary due to caching
        }
    )
    async def get_recent_drive_files(ctx: Context) -> dict:
        """Internal implementation for recent Google Drive files cache resource."""
        try:
            user_email = get_current_user_email_simple()
            cache_key = _get_cache_key(user_email, "recent_drive_files")
            
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
            drive_key = request_google_service("drive", ["drive_read"])
            drive_service = get_injected_service(drive_key)
            
            # Get recent files (modified in last 30 days)
            results = drive_service.files().list(
                q="modifiedTime > '2025-01-01T00:00:00Z'",
                pageSize=25,
                orderBy="modifiedTime desc",
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink, owners)"
            ).execute()
            
            files = results.get('files', [])
            
            output_data = {
                "user_email": user_email,
                "total_files": len(files),
                "files": files,
                "query": "Recent files (last 30 days)",
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
            logger.error(f"Error fetching recent drive files: {e}")
            return {
                "error": f"Failed to fetch recent drive files: {str(e)}",
                "cached": False,
                "timestamp": datetime.now().isoformat()
            }
    
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
            gmail_key = request_google_service("gmail", ["gmail_read"])
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
                        format='metadata',
                        metadataHeaders=['From', 'Subject', 'Date']
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
                        name = header['name'].lower()
                        if name in ['from', 'subject', 'date']:
                            msg_data[name] = header['value']
                    
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
            calendar_key = request_google_service("calendar", ["calendar_events"])
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
    
    @mcp.resource(
        uri="qdrant://collection/{collection}/info",
        name="Qdrant Collection Information by Name",
        description="Vector database collection metadata including schema, vector count, indexing configuration, and collection health status for a specific collection",
        mime_type="application/json",
        tags={"qdrant", "vector", "database", "metadata", "collection", "schema", "info", "semantic"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True  # Collection info queries are idempotent
        }
    )
    async def get_qdrant_collection_info_by_name(collection: str, ctx: Context) -> dict:
        """Internal implementation for Qdrant collection information resource."""
        try:
            # Use passed middleware or create new one if not available
            if qdrant_middleware and qdrant_middleware.client:
                middleware = qdrant_middleware
            else:
                # Fallback: Import Qdrant middleware to access collection info
                from middleware.qdrant_unified import QdrantUnifiedMiddleware, QdrantConfig

                # Try to get collection info
                config = QdrantConfig.from_file() if hasattr(QdrantConfig, 'from_file') else QdrantConfig()  # Use configuration loading</search>
# </search_and_replace>

                # Create a temporary middleware instance to access collection info
                middleware = QdrantUnifiedMiddleware()
                await middleware.initialize()
            
            if not middleware.client:
                return {
                    "error": "Qdrant not available",
                    "qdrant_enabled": False,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Get collection information for specific collection
            try:
                collections = await asyncio.to_thread(middleware.client.get_collections)
                collection_names = [c.name for c in collections.collections]

                collection_info = None
                if collection in collection_names:
                    collection_info = await asyncio.to_thread(
                        middleware.client.get_collection,
                        collection
                    )

                return {
                    "qdrant_enabled": True,
                    "qdrant_url": middleware.connection_manager.discovered_url,
                    "requested_collection": collection,
                    "collection_exists": collection in collection_names,
                    "total_collections": len(collection_names),
                    "all_collections": collection_names,
                    "collection_info": {
                        "vectors_count": collection_info.vectors_count if collection_info else 0,
                        "indexed_vectors_count": collection_info.indexed_vectors_count if collection_info else 0,
                        "points_count": collection_info.points_count if collection_info else 0,
                        "segments_count": collection_info.segments_count if collection_info else 0,
                        "status": str(collection_info.status) if collection_info else "unknown"
                    } if collection_info else None,
                    "config": {
                        "host": config.host,
                        "ports": config.ports,
                        "default_collection": config.collection_name,
                        "vector_size": config.vector_size,
                        "enabled": config.enabled
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
            except Exception as e:
                logger.error(f"Error getting Qdrant collection info: {e}")
                return {
                    "error": f"Failed to get collection info: {str(e)}",
                    "qdrant_enabled": True,
                    "qdrant_url": getattr(middleware.connection_manager, 'discovered_url', 'unknown'),
                    "timestamp": datetime.now().isoformat()
                }
            
        except Exception as e:
            logger.error(f"Error accessing Qdrant: {e}")
            return {
                "error": f"Qdrant access error: {str(e)}",
                "qdrant_enabled": False,
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="qdrant://collection/{collection}/responses/recent",
        name="Recent Tool Responses from Vector Database by Collection",
        description="Access recent tool execution responses stored in a specific Qdrant collection with semantic embeddings, response metadata, timestamps, and user context for analysis and debugging",
        mime_type="application/json",
        tags={"qdrant", "vector", "responses", "recent", "tool", "history", "semantic", "database", "debug", "collection"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": False  # Results may change as new responses are added
        }
    )
    async def get_qdrant_stored_responses_by_collection(collection: str, ctx: Context) -> dict:
        """Internal implementation for recent tool responses from vector database resource."""
        try:
            # Try to get user email, but allow access without authentication for debugging
            user_email = "anonymous"
            authenticated = False
            try:
                user_email = get_current_user_email_simple()
                authenticated = True
            except (ValueError, Exception):
                logger.info("Accessing Qdrant responses without user authentication")
            
            # Use passed middleware or create new one if not available
            if qdrant_middleware and qdrant_middleware.client:
                middleware = qdrant_middleware
            else:
                # Fallback: Import Qdrant middleware
                from middleware.qdrant_unified import QdrantUnifiedMiddleware
                
                # Create middleware instance to access stored data
                middleware = QdrantUnifiedMiddleware()
                await middleware.initialize()
            
            if not middleware.client:
                return {
                    "error": "Qdrant not available",
                    "user_email": user_email,
                    "qdrant_enabled": False,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Check if collection exists
            try:
                collections_response = await asyncio.to_thread(middleware.client.get_collections)
                available_collections = [c.name for c in collections_response.collections]

                if collection not in available_collections:
                    return {
                        "error": f"Collection '{collection}' not found",
                        "user_email": user_email,
                        "collection": collection,
                        "available_collections": available_collections,
                        "authenticated": authenticated,
                        "qdrant_enabled": True,
                        "timestamp": datetime.now().isoformat()
                    }

                # Search for recent responses (last 50) in specific collection
                search_result = await asyncio.to_thread(
                    middleware.client.scroll,
                    collection_name=collection,
                    limit=50,
                    with_payload=True,
                    with_vectors=False  # Don't need vectors, just metadata
                )

                points = search_result[0] if search_result else []

                # Filter and format responses
                user_responses = []
                all_responses = []

                for point in points:
                    payload = point.payload or {}

                    response_data = {
                        "id": str(point.id),
                        "tool_name": payload.get("tool_name", "unknown"),
                        "user_email": payload.get("user_email", "unknown"),
                        "timestamp": payload.get("timestamp", "unknown"),
                        "response_size": len(str(payload.get("response", ""))),
                        "session_id": payload.get("session_id", "unknown"),
                        "payload_type": payload.get("payload_type", "unknown"),
                        "has_error": "error" in payload.get("response", {}) if isinstance(payload.get("response"), dict) else False
                    }

                    all_responses.append(response_data)

                    # Filter for current user only if authenticated
                    if authenticated and payload.get("user_email") == user_email:
                        user_responses.append(response_data)

                # Sort by timestamp (most recent first)
                user_responses.sort(key=lambda x: x["timestamp"], reverse=True)
                all_responses.sort(key=lambda x: x["timestamp"], reverse=True)

                return {
                    "user_email": user_email,
                    "collection": collection,
                    "authenticated": authenticated,
                    "qdrant_enabled": True,
                    "total_responses": len(all_responses),
                    "user_responses_count": len(user_responses) if authenticated else 0,
                    "user_responses": user_responses[:20] if authenticated else [],  # Last 20 for current user
                    "recent_all_responses": all_responses[:10],  # Last 10 from all users
                    "timestamp": datetime.now().isoformat()
                }
                
            except Exception as e:
                logger.error(f"Error querying Qdrant responses: {e}")
                return {
                    "error": f"Failed to query responses: {str(e)}",
                    "user_email": user_email,
                    "authenticated": authenticated,
                    "qdrant_enabled": True,
                    "timestamp": datetime.now().isoformat()
                }
            
        except Exception as e:
            logger.error(f"Error accessing Qdrant responses: {e}")
            return {
                "error": f"Qdrant access error: {str(e)}",
                "qdrant_enabled": False,
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="qdrant://search/{collection}/{query}",
        name="Advanced Search Tool Responses by Collection",
        description="Advanced search across stored tool responses in a specific Qdrant collection with support for: ID lookup (id:xxxxx), filtered search (field:value), combined filters with semantic search (field1:value1 field2:value2 semantic query), and pure natural language queries",
        mime_type="application/json",
        tags={"qdrant", "search", "semantic", "vector", "similarity", "tool", "responses", "nlp", "context", "filters", "advanced", "collection"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True  # Same search query returns same results
        }
    )
    async def search_qdrant_responses_by_collection(collection: str, query: str, ctx: Context) -> dict:
        """Advanced search implementation using unified middleware with query parsing for specific collection."""
        try:
            # Try to get user email, but don't require it for search functionality
            user_email = "anonymous"
            try:
                user_email = get_current_user_email_simple()
            except (ValueError, Exception):
                # Search works without authentication - this is for debugging/analysis
                logger.info("Performing Qdrant search without user authentication")

            # Use passed middleware or create new one if not available
            if qdrant_middleware and qdrant_middleware.client:
                middleware = qdrant_middleware
            else:
                # Fallback: Import Qdrant middleware
                from middleware.qdrant_unified import QdrantUnifiedMiddleware

                # Create middleware instance for search
                middleware = QdrantUnifiedMiddleware()
                await middleware.initialize()

            if not middleware.client or not middleware.embedder:
                return {
                    "error": "Qdrant or embedding model not available",
                    "user_email": user_email,
                    "collection": collection,
                    "query": query,
                    "qdrant_enabled": False,
                    "timestamp": datetime.now().isoformat()
                }

            # Check if collection exists
            try:
                collections_response = await asyncio.to_thread(middleware.client.get_collections)
                available_collections = [c.name for c in collections_response.collections]

                if collection not in available_collections:
                    return {
                        "error": f"Collection '{collection}' not found",
                        "user_email": user_email,
                        "collection": collection,
                        "query": query,
                        "available_collections": available_collections,
                        "qdrant_enabled": True,
                        "timestamp": datetime.now().isoformat()
                    }

                # Use the enhanced search method from middleware with specific collection
                search_results = await middleware.search(
                    query=query,
                    collection_name=collection,
                    limit=10,
                    score_threshold=0.3
                )

                # Format results for resource response
                formatted_results = []
                for result in search_results:
                    result_data = {
                        "id": result.get("id", "unknown"),
                        "score": result.get("score", 0.0),
                        "tool_name": result.get("tool_name", "unknown"),
                        "user_email": result.get("user_email", "unknown"),
                        "timestamp": result.get("timestamp", "unknown"),
                        "session_id": result.get("session_id", "unknown"),
                        "response_preview": str(result.get("response_data", ""))[:200] + "..." if len(str(result.get("response_data", ""))) > 200 else str(result.get("response_data", "")),
                        "payload_type": result.get("payload_type", "unknown")
                    }

                    formatted_results.append(result_data)

                return {
                    "user_email": user_email,
                    "collection": collection,
                    "query": query,
                    "qdrant_enabled": True,
                    "total_results": len(formatted_results),
                    "results": formatted_results,
                    "search_timestamp": datetime.now().isoformat(),
                    "authenticated": user_email != "anonymous",
                    "query_examples": [
                        "id:6e05e913-fbe1-4e24-a205-16cb7fd53c9a",
                        "user_email:test@gmail.com",
                        "tool_name:get_tool_analytics",
                        "user_email:test@gmail.com documents for gardening",
                        "tool_name:search session_id:123 semantic query text"
                    ]
                }

            except Exception as e:
                logger.error(f"Error performing Qdrant search: {e}")
                return {
                    "error": f"Search failed: {str(e)}",
                    "user_email": user_email,
                    "collection": collection,
                    "query": query,
                    "qdrant_enabled": True,
                    "timestamp": datetime.now().isoformat()
                }

        except Exception as e:
            logger.error(f"Error accessing Qdrant for search: {e}")
            return {
                "error": f"Qdrant search error: {str(e)}",
                "collection": collection,
                "query": query,
                "qdrant_enabled": False,
                "timestamp": datetime.now().isoformat()
            }

    @mcp.resource(
        uri="qdrant://search/{query}",
        name="Advanced Search Tool Responses",
        description="Advanced search across stored tool responses with support for: ID lookup (id:xxxxx), filtered search (field:value), combined filters with semantic search (field1:value1 field2:value2 semantic query), and pure natural language queries",
        mime_type="application/json",
        tags={"qdrant", "search", "semantic", "vector", "similarity", "tool", "responses", "nlp", "context", "filters", "advanced"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True  # Same search query returns same results
        }
    )
    async def search_qdrant_responses(query: str, ctx: Context) -> dict:
        """Advanced search implementation using unified middleware with query parsing."""
        try:
            # Try to get user email, but don't require it for search functionality
            user_email = "anonymous"
            try:
                user_email = get_current_user_email_simple()
            except (ValueError, Exception):
                # Search works without authentication - this is for debugging/analysis
                logger.info("Performing Qdrant search without user authentication")
            
            # Use passed middleware or create new one if not available
            if qdrant_middleware and qdrant_middleware.client:
                middleware = qdrant_middleware
            else:
                # Fallback: Import Qdrant middleware
                from middleware.qdrant_unified import QdrantUnifiedMiddleware
                
                # Create middleware instance for search
                middleware = QdrantUnifiedMiddleware()
                await middleware.initialize()
            
            if not middleware.client or not middleware.embedder:
                return {
                    "error": "Qdrant or embedding model not available",
                    "user_email": user_email,
                    "query": query,
                    "qdrant_enabled": False,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Use the enhanced search method from middleware
            try:
                search_results = await middleware.search(
                    query=query,
                    limit=10,
                    score_threshold=0.3
                )
                
                # Format results for resource response
                formatted_results = []
                for result in search_results:
                    result_data = {
                        "id": result.get("id", "unknown"),
                        "score": result.get("score", 0.0),
                        "tool_name": result.get("tool_name", "unknown"),
                        "user_email": result.get("user_email", "unknown"),
                        "timestamp": result.get("timestamp", "unknown"),
                        "session_id": result.get("session_id", "unknown"),
                        "response_preview": str(result.get("response_data", ""))[:200] + "..." if len(str(result.get("response_data", ""))) > 200 else str(result.get("response_data", "")),
                        "payload_type": result.get("payload_type", "unknown")
                    }
                    
                    formatted_results.append(result_data)
                
                return {
                    "user_email": user_email,
                    "query": query,
                    "qdrant_enabled": True,
                    "collection_name": middleware.config.collection_name,
                    "total_results": len(formatted_results),
                    "results": formatted_results,
                    "search_timestamp": datetime.now().isoformat(),
                    "authenticated": user_email != "anonymous",
                    "query_examples": [
                        "id:6e05e913-fbe1-4e24-a205-16cb7fd53c9a",
                        "user_email:test@gmail.com",
                        "tool_name:get_tool_analytics",
                        "user_email:test@gmail.com documents for gardening",
                        "tool_name:search session_id:123 semantic query text"
                    ]
                }
                
            except Exception as e:
                logger.error(f"Error performing Qdrant search: {e}")
                return {
                    "error": f"Search failed: {str(e)}",
                    "user_email": user_email,
                    "query": query,
                    "qdrant_enabled": True,
                    "timestamp": datetime.now().isoformat()
                }
            
        except Exception as e:
            logger.error(f"Error accessing Qdrant for search: {e}")
            return {
                "error": f"Qdrant search error: {str(e)}",
                "query": query,
                "qdrant_enabled": False,
                "timestamp": datetime.now().isoformat()
            }
    
    @mcp.resource(
        uri="qdrant://collections/list",
        name="Qdrant Collections List",
        description="List all available Qdrant collections with metadata including vector counts, indexing status, and collection health information",
        mime_type="application/json",
        tags={"qdrant", "vector", "database", "collections", "metadata", "list", "semantic", "admin"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True  # Listing collections is idempotent
        }
    )
    async def list_qdrant_collections(ctx: Context) -> dict:
        """Internal implementation for listing all Qdrant collections."""
        try:
            # Use passed middleware or create new one if not available
            if qdrant_middleware and qdrant_middleware.client:
                middleware = qdrant_middleware
            else:
                # Fallback: Import Qdrant middleware
                from middleware.qdrant_unified import QdrantUnifiedMiddleware, QdrantConfig

                # Create middleware instance
                middleware = QdrantUnifiedMiddleware()
                await middleware.initialize()

            if not middleware.client:
                return {
                    "error": "Qdrant not available",
                    "qdrant_enabled": False,
                    "timestamp": datetime.now().isoformat()
                }

            # Get all collections
            try:
                collections_response = await asyncio.to_thread(middleware.client.get_collections)
                collections = collections_response.collections

                # Get detailed info for each collection
                collections_info = []
                for collection in collections:
                    try:
                        collection_info = await asyncio.to_thread(
                            middleware.client.get_collection,
                            collection.name
                        )

                        collection_data = {
                            "name": collection.name,
                            "vectors_count": collection_info.vectors_count,
                            "indexed_vectors_count": collection_info.indexed_vectors_count,
                            "points_count": collection_info.points_count,
                            "segments_count": collection_info.segments_count,
                            "status": str(collection_info.status),
                            "config": {
                                "vector_size": collection_info.config.params.vectors.size if hasattr(collection_info.config, 'params') and hasattr(collection_info.config.params, 'vectors') else None,
                                "distance": str(collection_info.config.params.vectors.distance) if hasattr(collection_info.config, 'params') and hasattr(collection_info.config.params, 'vectors') else None
                            } if hasattr(collection_info, 'config') else None
                        }
                        collections_info.append(collection_data)

                    except Exception as e:
                        logger.warning(f"Error getting info for collection {collection.name}: {e}")
                        collections_info.append({
                            "name": collection.name,
                            "error": f"Failed to get collection info: {str(e)}"
                        })

                return {
                    "qdrant_enabled": True,
                    "qdrant_url": middleware.connection_manager.discovered_url,
                    "total_collections": len(collections_info),
                    "collections": collections_info,
                    "timestamp": datetime.now().isoformat()
                }

            except Exception as e:
                logger.error(f"Error listing Qdrant collections: {e}")
                return {
                    "error": f"Failed to list collections: {str(e)}",
                    "qdrant_enabled": True,
                    "timestamp": datetime.now().isoformat()
                }

        except Exception as e:
            logger.error(f"Error accessing Qdrant: {e}")
            return {
                "error": f"Qdrant access error: {str(e)}",
                "qdrant_enabled": False,
                "timestamp": datetime.now().isoformat()
            }

    logger.info("✅ Tool output resources registered with caching and Qdrant integration")