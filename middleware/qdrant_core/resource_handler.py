#!/usr/bin/env python3
"""
Qdrant Resource Handler Module

This module handles qdrant:// URI processing and resource access for the FastMCP middleware.
Extracted from the unified middleware for focused resource management.

Supported URI patterns:
- qdrant://collections/list
- qdrant://collection/{name}/info  
- qdrant://collection/{name}/responses/recent
- qdrant://search/{collection}/{query}
- qdrant://search/{query}
"""

import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from .client import QdrantClientManager
from .search import QdrantSearchManager

# Import Pydantic response models
from middleware.qdrant_types import (
    QdrantCollectionsListResponse,
    QdrantCollectionDetailsResponse,
    QdrantRecentResponsesResponse,
    QdrantSearchResponse,
    QdrantErrorResponse,
    QdrantStatusResponse,
    QdrantPointDetailsResponse,
    QdrantCollectionInfo,
    QdrantStoredResponse,
    QdrantSearchResult,
    QdrantNearbyPoint
)

from config.enhanced_logging import setup_logger
logger = setup_logger()


class QdrantResourceHandler:
    """
    Handles qdrant:// URI requests and provides resource access.
    
    This class encapsulates all resource handling functionality including:
    - URI parsing and routing for different resource types
    - Collections listing and information retrieval
    - Recent responses access for collections
    - Collection-specific and global search operations
    - JSON response formatting for MCP resources
    - Integration with client and search managers
    """
    
    def __init__(
        self, 
        client_manager: QdrantClientManager, 
        search_manager: QdrantSearchManager
    ):
        """
        Initialize the Qdrant resource handler.
        
        Args:
            client_manager: QdrantClientManager instance for client operations
            search_manager: QdrantSearchManager instance for search operations
        """
        self.client_manager = client_manager
        self.search_manager = search_manager
        self.config = client_manager.config
        
        logger.debug("🔗 QdrantResourceHandler initialized")
    
    async def handle_qdrant_resource(self, uri: str, context=None):
        """
        Handle Qdrant-specific resource requests.
        
        Args:
            uri: The qdrant:// URI to process
            context: Optional middleware context (for compatibility)
            
        Returns:
            Pydantic model instance for FastMCP compatibility
        """
        # Ensure client manager is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        if not self.client_manager.client:
            return QdrantErrorResponse(
                error="Qdrant not available - client not initialized",
                uri=uri,
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False
            )
        
        # Parse the URI to determine the resource type
        parts = uri.replace("qdrant://", "").split("/")
        
        if not parts:
            return self._error_response(uri, "Invalid Qdrant URI format")
        
        resource_type = parts[0]
        
        if resource_type == "collections" and len(parts) == 2 and parts[1] == "list":
            # qdrant://collections/list
            return await self._handle_collections_list(uri)
            
        elif resource_type == "collection" and len(parts) >= 3:
            collection_name = parts[1]
            
            if parts[2] == "info":
                # qdrant://collection/{collection}/info
                return await self._handle_collection_info(uri, collection_name)
                
            elif parts[2] == "responses" and len(parts) == 4 and parts[3] == "recent":
                # qdrant://collection/{collection}/responses/recent
                return await self._handle_collection_responses(uri, collection_name)
            
            elif len(parts) == 3:
                # qdrant://collection/{collection}/{point_id}
                point_id = parts[2]
                return await self._handle_point_details(uri, collection_name, point_id)
                
        elif resource_type == "search":
            if len(parts) == 3:
                # qdrant://search/{collection}/{query}
                collection_name = parts[1]
                query = parts[2]
                return await self._handle_collection_search(uri, collection_name, query)
            elif len(parts) == 2:
                # qdrant://search/{query}
                query = parts[1]
                return await self._handle_global_search(uri, query)
                
        elif resource_type == "status":
            # qdrant://status
            return await self._handle_status(uri)

        elif resource_type == "cache":
            # qdrant://cache
            return await self._handle_cache(uri)

        return self._error_response(uri, f"Unknown Qdrant resource type: {resource_type}")
    
    def _error_response(self, uri: str, error_message: str):
        """
        Create a standard error response for resources.
        
        Args:
            uri: The original URI that caused the error
            error_message: Human-readable error message
            
        Returns:
            QdrantErrorResponse: Pydantic error response
        """
        return QdrantErrorResponse(
            error=error_message,
            uri=uri,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    
    async def _handle_collections_list(self, uri: str):
        """
        Handle qdrant://collections/list resource.
        
        Args:
            uri: The original URI
            
        Returns:
            QdrantCollectionsListResponse: Pydantic response with collections list
        """
        try:
            collections = await asyncio.to_thread(self.client_manager.client.get_collections)
            
            collections_info = []
            for collection in collections.collections:
                try:
                    info = await asyncio.to_thread(self.client_manager.client.get_collection, collection.name)
                    
                    # Qdrant collection info structure - handle None values properly
                    collections_info.append(QdrantCollectionInfo(
                        name=collection.name,
                        points_count=info.points_count if info.points_count is not None else 0,
                        vectors_count=info.vectors_count if info.vectors_count is not None else 0,
                        indexed_vectors_count=info.indexed_vectors_count if info.indexed_vectors_count is not None else 0,
                        segments_count=info.segments_count if info.segments_count is not None else 0,
                        status=str(info.status) if info.status is not None else 'unknown'
                    ))
                except Exception as e:
                    logger.warning(f"Failed to get info for collection {collection.name}: {e}")
                    collections_info.append(QdrantCollectionInfo(
                        name=collection.name,
                        points_count=0,
                        vectors_count=0,
                        indexed_vectors_count=0,
                        segments_count=0,
                        status='error',
                        error=str(e)
                    ))
            
            return QdrantCollectionsListResponse(
                qdrant_enabled=True,
                qdrant_url=self.client_manager.discovered_url,
                total_collections=len(collections_info),
                collections=collections_info,
                config=self.config.to_dict(),
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error listing Qdrant collections: {e}")
            return self._error_response(uri, f"Failed to list collections: {str(e)}")
    
    async def _handle_collection_info(self, uri: str, collection_name: str):
        """
        Handle qdrant://collection/{collection}/info resource.
        
        Args:
            uri: The original URI
            collection_name: Name of the collection to get info for
            
        Returns:
            QdrantCollectionDetailsResponse: Pydantic response with collection information
        """
        try:
            collections = await asyncio.to_thread(self.client_manager.client.get_collections)
            collection_names = [c.name for c in collections.collections]
            
            collection_info = None
            if collection_name in collection_names:
                collection_info = await asyncio.to_thread(
                    self.client_manager.client.get_collection,
                    collection_name
                )
            
            collection_info_dict = None
            if collection_info:
                collection_info_dict = {
                    "vectors_count": collection_info.vectors_count if collection_info.vectors_count is not None else 0,
                    "indexed_vectors_count": collection_info.indexed_vectors_count if collection_info.indexed_vectors_count is not None else 0,
                    "points_count": collection_info.points_count if collection_info.points_count is not None else 0,
                    "segments_count": collection_info.segments_count if collection_info.segments_count is not None else 0,
                    "status": str(collection_info.status) if collection_info.status is not None else "unknown"
                }
            
            return QdrantCollectionDetailsResponse(
                qdrant_enabled=True,
                qdrant_url=self.client_manager.discovered_url,
                requested_collection=collection_name,
                collection_exists=collection_name in collection_names,
                total_collections=len(collection_names),
                all_collections=collection_names,
                collection_info=collection_info_dict,
                config=self.config.to_dict(),
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return self._error_response(uri, f"Failed to get collection info: {str(e)}")
    
    async def _handle_collection_responses(self, uri: str, collection_name: str):
        """
        Handle qdrant://collection/{collection}/responses/recent resource.
        
        Args:
            uri: The original URI
            collection_name: Name of the collection to get responses from
            
        Returns:
            QdrantRecentResponsesResponse: Pydantic response with recent responses from the collection
        """
        try:
            # Check if collection exists
            collections_response = await asyncio.to_thread(self.client_manager.client.get_collections)
            available_collections = [c.name for c in collections_response.collections]
            
            if collection_name not in available_collections:
                return self._error_response(
                    uri,
                    f"Collection '{collection_name}' not found. Available: {', '.join(available_collections)}"
                )
            
            # Get recent responses from the collection
            scroll_result = await asyncio.to_thread(
                self.client_manager.client.scroll,
                collection_name=collection_name,
                limit=50,
                with_payload=True,
                with_vectors=False
            )
            
            points = scroll_result[0] if scroll_result else []
            
            responses = []
            for point in points[:20]:  # Limit to 20 most recent
                payload = point.payload or {}
                
                # Decompress data if needed
                data = payload.get("data", "{}")
                if payload.get("compressed", False) and payload.get("compressed_data"):
                    try:
                        decompressed = self.client_manager._decompress_data(payload["compressed_data"])
                        if decompressed is not None:
                            data = decompressed
                    except Exception as e:
                        logger.warning(f"Failed to decompress data for point {point.id}: {e}")
                
                # Parse response data - ensure data is not None
                if data is None or data == "":
                    response_data = {"error": "No data available"}
                else:
                    try:
                        response_data = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        response_data = {"error": "Failed to parse stored data", "raw_data": str(data)}
                
                responses.append(QdrantStoredResponse(
                    id=str(point.id),
                    tool_name=payload.get("tool_name", "unknown"),
                    timestamp=payload.get("timestamp", "unknown"),
                    user_id=payload.get("user_id", "unknown"),
                    user_email=payload.get("user_email", "unknown"),
                    session_id=payload.get("session_id", "unknown"),
                    payload_type=payload.get("payload_type", "unknown"),
                    compressed=payload.get("compressed", False),
                    response_data=response_data
                ))
            
            return QdrantRecentResponsesResponse(
                qdrant_enabled=True,
                collection_name=collection_name,
                total_points=len(points),
                responses_shown=len(responses),
                responses=responses,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error getting collection responses: {e}")
            return self._error_response(uri, f"Failed to get collection responses: {str(e)}")
    
    async def _handle_point_details(self, uri: str, collection_name: str, point_id: str):
        """
        Handle qdrant://collection/{collection}/{point_id} resource.
        
        Args:
            uri: The original URI
            collection_name: Name of the collection
            point_id: ID of the point to retrieve
            
        Returns:
            QdrantPointDetailsResponse: Pydantic response with point details
        """
        
        
        try:
            # Check if collection exists
            collections_response = await asyncio.to_thread(self.client_manager.client.get_collections)
            available_collections = [c.name for c in collections_response.collections]
            
            if collection_name not in available_collections:
                return self._error_response(
                    uri,
                    f"Collection '{collection_name}' not found. Available: {', '.join(available_collections)}"
                )
            
            # Retrieve the specific point
            try:
                points = await asyncio.to_thread(
                    self.client_manager.client.retrieve,
                    collection_name=collection_name,
                    ids=[point_id],
                    with_payload=True,
                    with_vectors=False
                )
                
                if not points or len(points) == 0:
                    return QdrantPointDetailsResponse(
                        qdrant_enabled=True,
                        collection_name=collection_name,
                        point_id=point_id,
                        point_exists=False,
                        retrieved_at=datetime.now(timezone.utc).isoformat()
                    )
                
                point = points[0]
                payload = point.payload or {}
                
                # Parse and clean the payload using the client manager's parser
                # This automatically extracts nested JSON from FastMCP tool responses
                parsed_payload = self.client_manager.parse_tool_response_payload(payload)
                
                # Extract common fields from parsed payload
                tool_name = parsed_payload.get("tool_name")
                user_email = parsed_payload.get("user_email")
                timestamp = parsed_payload.get("timestamp")
                session_id = parsed_payload.get("session_id")
                payload_type = parsed_payload.get("payload_type")
                compressed = parsed_payload.get("compressed", False)
                
                # Decompress data if needed
                response_data = None
                if compressed and parsed_payload.get("compressed_data"):
                    try:
                        decompressed = self.client_manager._decompress_data(parsed_payload["compressed_data"])
                        try:
                            response_data = json.loads(decompressed)
                        except json.JSONDecodeError:
                            response_data = decompressed
                    except Exception as e:
                        logger.warning(f"Failed to decompress data for point {point_id}: {e}")
                        response_data = {"error": "Failed to decompress data", "details": str(e)}
                elif parsed_payload.get("data"):
                    try:
                        response_data = json.loads(parsed_payload["data"])
                    except json.JSONDecodeError:
                        response_data = parsed_payload["data"]
                
                # If we have response_data in the parsed payload (from the parser), use that
                if parsed_payload.get("response_data") and not response_data:
                    response_data = parsed_payload.get("response_data")
                
                # Find nearby points for context
                nearby_points = await self._find_nearby_points(
                    collection_name,
                    timestamp,
                    session_id,
                    str(point.id)
                )
                
                # Return as dict for MCP resource format
                # Return Pydantic model directly - middleware will handle it
                return QdrantPointDetailsResponse(
                    qdrant_enabled=True,
                    collection_name=collection_name,
                    point_id=str(point.id),
                    point_exists=True,
                    payload=payload,
                    vector_available=False,
                    tool_name=tool_name,
                    user_email=user_email,
                    timestamp=timestamp,
                    session_id=session_id,
                    payload_type=payload_type,
                    compressed=compressed,
                    response_data=response_data,
                    nearby_points=nearby_points,
                    retrieved_at=datetime.now(timezone.utc).isoformat()
                )
                
            except Exception as e:
                logger.error(f"Error retrieving point {point_id}: {e}")
                return QdrantPointDetailsResponse(
                    qdrant_enabled=True,
                    collection_name=collection_name,
                    point_id=point_id,
                    point_exists=False,
                    retrieved_at=datetime.now(timezone.utc).isoformat()
                )
                
        except Exception as e:
            logger.error(f"Error in _handle_point_details: {e}")
            return self._error_response(uri, f"Failed to retrieve point details: {str(e)}")
    
    async def _handle_collection_search(self, uri: str, collection_name: str, query: str):
        """
        Handle qdrant://search/{collection}/{query} resource.
        
        Args:
            uri: The original URI
            collection_name: Name of the collection to search within
            query: Search query string
            
        Returns:
            QdrantSearchResponse: Pydantic response with search results from the specified collection
        """
        try:
            # Use the search manager to perform the search
            # Note: This is a simplified approach - ideally we'd search within the collection directly
            results = await self.search_manager.search(query, limit=10)
            
            # Convert results to Pydantic models
            search_results = []
            for result in results:
                search_results.append(QdrantSearchResult(
                    id=str(result.get("id", "")),
                    score=float(result.get("score", 0.0)),
                    tool_name=result.get("tool_name"),
                    timestamp=result.get("timestamp"),
                    user_email=result.get("user_email"),
                    payload=result
                ))
            
            return QdrantSearchResponse(
                qdrant_enabled=True,
                query=query,
                collection=collection_name,
                total_results=len(search_results),
                results=search_results,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error searching collection: {e}")
            return self._error_response(uri, f"Failed to search collection: {str(e)}")
    
    async def _handle_global_search(self, uri: str, query: str):
        """
        Handle qdrant://search/{query} resource.
        
        Args:
            uri: The original URI
            query: Search query string
            
        Returns:
            QdrantSearchResponse: Pydantic response with global search results
        """
        try:
            # Use the search manager for global search
            results = await self.search_manager.search(query, limit=10)
            
            # Convert results to Pydantic models
            search_results = []
            for result in results:
                search_results.append(QdrantSearchResult(
                    id=str(result.get("id", "")),
                    score=float(result.get("score", 0.0)),
                    tool_name=result.get("tool_name"),
                    timestamp=result.get("timestamp"),
                    user_email=result.get("user_email"),
                    payload=result
                ))
            
            return QdrantSearchResponse(
                qdrant_enabled=True,
                query=query,
                total_results=len(search_results),
                results=search_results,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error in global search: {e}")
            return self._error_response(uri, f"Failed to search: {str(e)}")
    
    def get_supported_uris(self) -> List[str]:
        """
        Get list of supported URI patterns.

        Returns:
            List of supported URI pattern descriptions
        """
        return [
            "qdrant://collections/list",
            "qdrant://collection/{name}/info",
            "qdrant://collection/{name}/responses/recent",
            "qdrant://search/{collection}/{query}",
            "qdrant://search/{query}",
            "qdrant://cache",
            "qdrant://status"
        ]
    
    async def _handle_cache(self, uri: str):
        """
        Handle qdrant://cache resource.

        Returns a dictionary organized by tool name with arrays of point metadata
        containing point_id, timestamp, and user_email.

        Args:
            uri: The original URI

        Returns:
            dict: {tool_name: [{point_id, timestamp, user_email}, ...], ...}
        """
        try:
            # Get the main collection name from config
            collection_name = self.config.collection_name

            # Check if collection exists
            collections_response = await asyncio.to_thread(self.client_manager.client.get_collections)
            available_collections = [c.name for c in collections_response.collections]

            if collection_name not in available_collections:
                return {
                    "error": f"Collection '{collection_name}' not found",
                    "available_collections": available_collections,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            # Scroll through all points in the collection
            all_points = []
            next_page_offset = None

            while True:
                scroll_result = await asyncio.to_thread(
                    self.client_manager.client.scroll,
                    collection_name=collection_name,
                    limit=100,  # Get points in batches
                    offset=next_page_offset,
                    with_payload=True,
                    with_vectors=False
                )

                points, next_page_offset = scroll_result
                all_points.extend(points)

                # Break if no more points or we've collected enough
                if next_page_offset is None or len(all_points) >= 1000:
                    break

            # Group points by tool_name
            cache_by_tool = {}

            for point in all_points:
                payload = point.payload or {}

                tool_name = payload.get("tool_name", "unknown")
                timestamp = payload.get("timestamp", "unknown")
                user_email = payload.get("user_email", "unknown")

                # Initialize tool array if not exists
                if tool_name not in cache_by_tool:
                    cache_by_tool[tool_name] = []

                # Add point metadata
                cache_by_tool[tool_name].append({
                    "point_id": str(point.id),
                    "timestamp": timestamp,
                    "user_email": user_email
                })

            # Sort each tool's points by timestamp (most recent first)
            for tool_name in cache_by_tool:
                cache_by_tool[tool_name].sort(
                    key=lambda x: x["timestamp"] if x["timestamp"] != "unknown" else "",
                    reverse=True
                )

            return {
                "collection_name": collection_name,
                "total_points": len(all_points),
                "tools_count": len(cache_by_tool),
                "cache_data": cache_by_tool,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting cache data: {e}")
            return self._error_response(uri, f"Failed to get cache data: {str(e)}")

    async def _handle_status(self, uri: str):
        """
        Handle qdrant://status resource.

        Args:
            uri: The original URI

        Returns:
            QdrantStatusResponse: Pydantic response with middleware status
        """
        try:
            # Get collections count if available
            collections_count = 0
            if self.client_manager.is_available:
                try:
                    collections = await asyncio.to_thread(self.client_manager.client.get_collections)
                    collections_count = len(collections.collections)
                except Exception:
                    collections_count = 0

            return QdrantStatusResponse(
                qdrant_enabled=self.client_manager.config.enabled,
                qdrant_url=self.client_manager.discovered_url,
                client_available=self.client_manager.is_available,
                embedder_available=self.client_manager.embedder is not None,
                initialized=self.client_manager.is_initialized,
                collections_count=collections_count,
                config=self.config.to_dict(),
                supported_uris=self.get_supported_uris(),
                handler_info=self.get_handler_info(),
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return self._error_response(uri, f"Failed to get status: {str(e)}")

    async def _find_nearby_points(
        self,
        collection_name: str,
        target_timestamp: Optional[str],
        target_session_id: Optional[str],
        exclude_point_id: str
    ) -> List[QdrantNearbyPoint]:
        """
        Find the two nearest points by timestamp for context.
        
        Args:
            collection_name: Collection to search in
            target_timestamp: Timestamp of the main point
            target_session_id: Session ID of the main point
            exclude_point_id: Point ID to exclude (the main point itself)
            
        Returns:
            List of up to 2 nearby points
        """
        if not target_timestamp:
            return []
        
        try:
            # Parse the target timestamp using built-in datetime
            # Assuming ISO 8601 format: "2025-10-01T03:54:21.994071+00:00"
            target_dt = datetime.fromisoformat(target_timestamp)
            
            # Scroll through collection to find nearby points
            scroll_result = await asyncio.to_thread(
                self.client_manager.client.scroll,
                collection_name=collection_name,
                limit=100,  # Get more points to find closest matches
                with_payload=True,
                with_vectors=False
            )
            
            points = scroll_result[0] if scroll_result else []
            
            # Calculate time differences and filter
            candidates = []
            for point in points:
                if str(point.id) == exclude_point_id:
                    continue
                
                payload = point.payload or {}
                point_timestamp = payload.get("timestamp")
                
                if not point_timestamp:
                    continue
                
                try:
                    point_dt = datetime.fromisoformat(point_timestamp)
                    time_diff = (point_dt - target_dt).total_seconds()
                    
                    candidates.append({
                        "point_id": str(point.id),
                        "timestamp": point_timestamp,
                        "time_diff": time_diff,
                        "abs_time_diff": abs(time_diff),
                        "tool_name": payload.get("tool_name"),
                        "user_email": payload.get("user_email"),
                        "session_id": payload.get("session_id")
                    })
                except Exception as e:
                    logger.debug(f"Failed to parse timestamp for point {point.id}: {e}")
                    continue
            
            # Sort by absolute time difference
            candidates.sort(key=lambda x: x["abs_time_diff"])
            
            # Take the 2 closest points
            nearby = []
            for candidate in candidates[:2]:
                nearby.append(QdrantNearbyPoint(
                    point_id=candidate["point_id"],
                    tool_name=candidate["tool_name"],
                    timestamp=candidate["timestamp"],
                    time_offset_seconds=candidate["time_diff"],
                    user_email=candidate["user_email"],
                    session_id=candidate["session_id"],
                    same_session=(candidate["session_id"] == target_session_id)
                ))
            
            return nearby
            
        except Exception as e:
            logger.warning(f"Failed to find nearby points: {e}")
            return []
    
    def get_handler_info(self) -> Dict[str, Any]:
        """
        Get information about the resource handler and its status.
        
        Returns:
            Dict with handler information and status
        """
        return {
            "handler_type": "QdrantResourceHandler",
            "client_manager_status": self.client_manager.get_connection_info(),
            "search_manager_available": self.search_manager.is_initialized,
            "config": self.config.to_dict(),
            "supported_uris": self.get_supported_uris(),
            "available": self.client_manager.is_available,
            "initialized": self.client_manager.is_initialized,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# Backward compatibility function for middleware integration
async def handle_qdrant_resource_legacy(middleware, uri: str, context=None):
    """
    Legacy wrapper function for resource handling to maintain compatibility.
    
    Args:
        middleware: QdrantUnifiedMiddleware instance (for compatibility)
        uri: The qdrant:// URI to process
        context: Optional middleware context
        
    Returns:
        Dict: MCP resource response
    """
    # Check if middleware has resource_handler attribute
    if hasattr(middleware, 'resource_handler'):
        return await middleware.resource_handler.handle_qdrant_resource(uri, context)
    
    # Fallback: create a temporary resource handler if client_manager and search_manager exist
    if hasattr(middleware, 'client_manager') and hasattr(middleware, 'search_manager'):
        logger.warning("Using fallback resource handler creation - consider updating middleware integration")
        resource_handler = QdrantResourceHandler(middleware.client_manager, middleware.search_manager)
        return await resource_handler.handle_qdrant_resource(uri, context)
    
    # Final fallback - create managers from middleware attributes
    logger.warning("Creating resource handler with legacy middleware compatibility")
    from .client import QdrantClientManager
    from .search import QdrantSearchManager
    
    client_manager = QdrantClientManager(
        config=middleware.config,
        qdrant_api_key=getattr(middleware, 'qdrant_api_key', None),
        qdrant_url=getattr(middleware, 'qdrant_url', None),
        auto_discovery=getattr(middleware, 'auto_discovery', True)
    )
    search_manager = QdrantSearchManager(client_manager)
    resource_handler = QdrantResourceHandler(client_manager, search_manager)
    
    return await resource_handler.handle_qdrant_resource(uri, context)