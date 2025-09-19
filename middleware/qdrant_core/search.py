"""
Qdrant Search and Analytics Module

This module contains search and analytics functionality extracted from the main
Qdrant middleware, including:
- Semantic search operations using embeddings
- Advanced query parsing and filtering
- Analytics and reporting on stored data
- Response retrieval and data access
- Unified search with intelligent query routing

This focused module handles all aspects of searching and analyzing data stored
in Qdrant while maintaining async patterns, error handling, and integration
with client management and query parsing modules.
"""

import json
import uuid
import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .client import QdrantClientManager
from .query_parser import (
    parse_search_query, 
    parse_unified_query, 
    format_search_results,
    extract_service_from_tool
)
from .config import QdrantConfig
from .lazy_imports import get_qdrant_imports

from config.enhanced_logging import setup_logger
logger = setup_logger()


class QdrantSearchManager:
    """
    Manages search and analytics operations for the Qdrant vector database.
    
    This class encapsulates all search functionality including:
    - Semantic search with query parsing support
    - Advanced filtering and ID lookup capabilities
    - Analytics and reporting on stored tool responses
    - Response retrieval and data access operations
    - Unified search with intelligent query routing
    - Integration with client management and query parsing
    """
    
    def __init__(self, client_manager: QdrantClientManager):
        """
        Initialize the Qdrant search manager.
        
        Args:
            client_manager: QdrantClientManager instance for client operations
        """
        self.client_manager = client_manager
        self.config = client_manager.config
        
        logger.debug("🔍 QdrantSearchManager initialized")
    
    @property
    def is_initialized(self) -> bool:
        """Check if search manager is fully initialized."""
        return self.client_manager.is_initialized
    
    async def _execute_semantic_search(
        self, 
        query_embedding, 
        qdrant_filter=None, 
        limit=None, 
        score_threshold=None
    ):
        """
        Execute semantic search using query_points (new Qdrant API).
        
        Args:
            query_embedding: The embedding vector for the query
            qdrant_filter: Optional Qdrant filter
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            
        Returns:
            List of ScoredPoint objects from Qdrant
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        if not self.client_manager.is_available:
            raise RuntimeError("Qdrant client not available")
        
        search_response = await asyncio.to_thread(
            self.client_manager.client.query_points,
            collection_name=self.config.collection_name,
            query=query_embedding.tolist(),
            query_filter=qdrant_filter,
            limit=limit or self.config.default_search_limit,
            score_threshold=score_threshold or self.config.score_threshold,
            with_payload=True
        )
        return search_response.points  # Extract points from response

    async def search(self, query: str, limit: int = None, score_threshold: float = None) -> List[Dict]:
        """
        Advanced search with query parsing support.
        
        Supports:
        - Direct ID lookup: "id:12345"
        - Filtered search: "user_email:test@gmail.com semantic query"
        - Multiple filters: "tool_name:search user_email:test@gmail.com documents"
        - Pure semantic search: "natural language query"
        
        Args:
            query: Search query (supports filters and semantic search)
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            
        Returns:
            List of matching responses with scores and metadata
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
            
        if not self.client_manager.client or not self.client_manager.embedder:
            raise RuntimeError("Qdrant client or embedding model not available")
        
        try:
            # Parse the query to extract filters and semantic components
            parsed_query = parse_search_query(query)
            logger.debug(f"🔍 Parsed query: {parsed_query}")
            
            search_results = []
            
            # Handle direct ID lookup
            if parsed_query["query_type"] == "id_lookup":
                target_id = parsed_query["id"]
                logger.debug(f"🎯 Looking up point by ID: {target_id}")
                
                try:
                    # Handle both string and UUID formats - always use string for Qdrant
                    try:
                        # Try to parse as UUID first to validate, but keep as string
                        uuid.UUID(target_id)
                        search_id = target_id  # Keep as string
                    except ValueError:
                        # If not a valid UUID, use as string anyway
                        search_id = target_id
                    
                    points = await asyncio.to_thread(
                        self.client_manager.client.retrieve,
                        collection_name=self.config.collection_name,
                        ids=[search_id],
                        with_payload=True
                    )
                    
                    if points:
                        point = points[0]
                        search_results = [{
                            'id': str(point.id),
                            'score': 1.0,  # Perfect match for direct lookup
                            'payload': point.payload
                        }]
                    logger.debug(f"📍 ID lookup found {len(search_results)} results")
                        
                except Exception as e:
                    logger.error(f"❌ ID lookup failed: {e}")
                    raise
            
            # Handle filtered search (with or without semantic component)
            else:
                qdrant_filter = None
                
                # Build Qdrant filter from parsed filters
                if parsed_query["filters"]:
                    try:
                        # Import Qdrant models for filtering
                        _, qdrant_models = get_qdrant_imports()
                        Filter = qdrant_models['models'].Filter
                        FieldCondition = qdrant_models['models'].FieldCondition
                        MatchValue = qdrant_models['models'].MatchValue
                        
                        conditions = []
                        for filter_key, filter_value in parsed_query["filters"].items():
                            logger.debug(f"🏷️  Adding filter: {filter_key}={filter_value}")
                            conditions.append(
                                FieldCondition(
                                    key=filter_key,
                                    match=MatchValue(value=filter_value)
                                )
                            )
                        
                        if conditions:
                            qdrant_filter = Filter(must=conditions)
                            logger.debug(f"🔧 Built filter with {len(conditions)} conditions")
                    
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to build filter, falling back to simple search: {e}")
                        qdrant_filter = None
                
                # Perform semantic search if there's a semantic query
                if parsed_query["semantic_query"]:
                    logger.debug(f"🧠 Performing semantic search: '{parsed_query['semantic_query']}'")
                    
                    # Generate embedding for the semantic query
                    query_embedding = await asyncio.to_thread(
                        self.client_manager.embedder.encode,
                        parsed_query["semantic_query"]
                    )
                    
                    # Use helper method for consistent query_points usage
                    search_results = await self._execute_semantic_search(
                        query_embedding=query_embedding,
                        qdrant_filter=qdrant_filter,
                        limit=limit,
                        score_threshold=score_threshold
                    )
                    
                    logger.debug(f"🎯 Semantic search found {len(search_results)} results")
                
                # If no semantic query, just filter and return results
                elif parsed_query["filters"]:
                    logger.debug("📋 Performing filter-only search")
                    
                    # Scroll with filter to get filtered results
                    scroll_result = await asyncio.to_thread(
                        self.client_manager.client.scroll,
                        collection_name=self.config.collection_name,
                        scroll_filter=qdrant_filter,
                        limit=limit or self.config.default_search_limit,
                        with_payload=True
                    )
                    
                    # Convert scroll results to search result format
                    search_results = [{
                        'id': str(point.id),
                        'score': 1.0,  # Equal relevance for filter-only results
                        'payload': point.payload
                    } for point in scroll_result[0]]  # scroll returns (points, next_page_offset)
                    
                    logger.debug(f"📋 Filter search found {len(search_results)} results")
                
                # Default behavior for plain semantic search
                else:
                    logger.debug(f"🧠 Pure semantic search: '{query}'")
                    
                    # Generate embedding for the entire query
                    query_embedding = await asyncio.to_thread(self.client_manager.embedder.encode, query)
                    
                    # Use helper method for consistent query_points usage
                    search_results = await self._execute_semantic_search(
                        query_embedding=query_embedding,
                        limit=limit,
                        score_threshold=score_threshold
                    )
                    
                    logger.debug(f"🧠 Pure semantic search found {len(search_results)} results")
            
            # Process and format results
            results = []
            for result in search_results:
                # Handle different result formats
                if hasattr(result, 'payload'):
                    # Standard Qdrant search result
                    payload = result.payload or {}
                    result_id = str(result.id)
                    score = result.score
                else:
                    # Custom format from our query parsing
                    payload = result.get('payload', {})
                    result_id = str(result.get('id', 'unknown'))
                    score = result.get('score', 0.0)
                
                # Decompress data if needed
                if payload.get("compressed", False):
                    compressed_data = payload["compressed_data"]
                    # Ensure compressed_data is bytes (handle string encoding if necessary)
                    if isinstance(compressed_data, str):
                        # If it's a string, it might be base64 encoded or need to be encoded as bytes
                        import base64
                        try:
                            # Try base64 decode first (common for binary data stored as string)
                            compressed_data = base64.b64decode(compressed_data)
                        except:
                            # Fallback to encoding as UTF-8 bytes
                            compressed_data = compressed_data.encode('utf-8')
                    data = self.client_manager._decompress_data(compressed_data)
                else:
                    data = payload.get("data", "{}")
                
                # Parse response data
                try:
                    response_data = json.loads(data)
                except json.JSONDecodeError:
                    response_data = {"error": "Failed to parse stored data"}
               
                results.append({
                   "id": result_id,
                   "score": score,
                   "tool_name": payload.get("tool_name"),
                   "timestamp": payload.get("timestamp"),
                   "user_id": payload.get("user_id"),
                   "user_email": payload.get("user_email"),
                   "session_id": payload.get("session_id"),
                   "response_data": response_data,
                   "payload_type": payload.get("payload_type", "unknown")
                })
           
            logger.info(f"✅ Search completed: {len(results)} results for query '{query}'")
            return results
           
        except Exception as e:
           logger.error(f"❌ Search failed: {e}")
           raise

    async def search_responses(self, query: str, filters: Dict = None, limit: int = 10) -> List[Dict]:
        """
        Search stored responses with optional filters.
        
        Args:
            query: Natural language search query
            filters: Dictionary of filter criteria
            limit: Maximum number of results
            
        Returns:
            List of matching responses
        """
        try:
            # Use the existing search method and apply filters
            results = await self.search(query, limit=limit)
            
            if filters:
                filtered_results = []
                for result in results:
                    match = True
                    if "tool_name" in filters and result.get("tool_name") != filters["tool_name"]:
                        match = False
                    if "user_email" in filters and result.get("user_email") != filters["user_email"]:
                        match = False
                    if match:
                        filtered_results.append(result)
                return filtered_results
            
            return results
        except Exception as e:
            logger.error(f"❌ Search responses failed: {e}")
            # Return empty list instead of raising to prevent tool failures
            return []

    async def get_analytics(self, start_date=None, end_date=None, group_by="tool_name") -> Dict:
        """
        Get analytics on stored tool responses.
        
        Args:
            start_date: Start date filter
            end_date: End date filter
            group_by: Field to group results by
            
        Returns:
            Analytics data dictionary
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        if not self.client_manager.client:
            return {"error": "Qdrant client not available"}
        
        try:
            # Get all points from the collection
            _, qdrant_models = get_qdrant_imports()
            
            # Scroll through all points in the collection
            points = await asyncio.to_thread(
                self.client_manager.client.scroll,
                collection_name=self.config.collection_name,
                limit=1000  # Adjust as needed
            )
            
            analytics = {
                "total_responses": len(points[0]),
                "group_by": group_by,
                "groups": {}
            }
            
            for point in points[0]:
                payload = point.payload
                group_key = payload.get(group_by, "unknown")
                
                if group_key not in analytics["groups"]:
                    analytics["groups"][group_key] = {
                        "count": 0,
                        "timestamps": []
                    }
                
                analytics["groups"][group_key]["count"] += 1
                if "timestamp" in payload:
                    analytics["groups"][group_key]["timestamps"].append(payload["timestamp"])
            
            return analytics
            
        except Exception as e:
            logger.error(f"❌ Failed to get analytics: {e}")
            return {"error": str(e)}

    async def get_response_by_id(self, response_id: str) -> Optional[Dict]:
        """
        Get a specific response by its ID.
        
        Args:
            response_id: UUID of the stored response
            
        Returns:
            Response data or None if not found
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        if not self.client_manager.client:
            return None
        
        try:
            # Handle both string and UUID formats - always use string for Qdrant
            try:
                # Try to parse as UUID first to validate, but keep as string
                uuid.UUID(response_id)
                search_id = response_id  # Keep as string
            except ValueError:
                # If not a valid UUID, use as string anyway
                search_id = response_id
            
            # Retrieve the specific point by ID
            point = await asyncio.to_thread(
                self.client_manager.client.retrieve,
                collection_name=self.config.collection_name,
                ids=[search_id]
            )
            
            if not point:
                return None
            
            payload = point[0].payload
            
            # Decompress data if needed
            if payload.get("compressed", False):
                compressed_data = payload["compressed_data"]
                # Ensure compressed_data is bytes (handle string encoding if necessary)
                if isinstance(compressed_data, str):
                    # If it's a string, it might be base64 encoded or need to be encoded as bytes
                    import base64
                    try:
                        # Try base64 decode first (common for binary data stored as string)
                        compressed_data = base64.b64decode(compressed_data)
                    except:
                        # Fallback to encoding as UTF-8 bytes
                        compressed_data = compressed_data.encode('utf-8')
                data = self.client_manager._decompress_data(compressed_data)
            else:
                data = payload.get("data", "{}")
            
            # Parse and return response data
            try:
                response_data = json.loads(data)
                return response_data
            except json.JSONDecodeError:
                return {"error": "Failed to parse stored data", "raw_data": data}
                
        except Exception as e:
            logger.error(f"❌ Failed to get response by ID: {e}")
            return {"error": str(e)}

    async def unified_search_core(self, query: str, limit: int = 10) -> Dict:
        """
        Core unified search function with intelligent query routing.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            Dictionary in OpenAI MCP format with 'results' array
        """
        # Parse query using enhanced parser
        parsed_query = parse_unified_query(query)
        logger.info(f"🔍 Unified search: capability={parsed_query['capability']}, confidence={parsed_query['confidence']}")
        
        # Route to appropriate search strategy based on capability
        if parsed_query["capability"] == "overview":
            # Get analytics/overview data
            try:
                analytics = await self.get_analytics()
                if analytics and "groups" in analytics:
                    # Convert analytics to search result format
                    results = []
                    for group_name, group_data in analytics["groups"].items():
                        results.append({
                            "id": f"analytics_{group_name}",
                            "tool_name": f"analytics_{group_name}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "user_email": "system",
                            "score": 1.0,
                            "response_data": {
                                "summary": f"{group_name}: {group_data.get('count', 0)} responses",
                                "analytics": group_data
                            }
                        })
                    return await format_search_results(self, results[:limit], parsed_query)
                else:
                    return {"results": []}
            except Exception as e:
                logger.error(f"❌ Overview search failed: {e}")
                return {"results": []}
        
        elif parsed_query["capability"] == "service_history":
            # Build filtered query for service history
            search_query = ""
            if parsed_query.get("service_name"):
                search_query += f"tool_name:{parsed_query['service_name']}"
            if parsed_query.get("time_range"):
                search_query += f" {parsed_query['time_range']}"
            if parsed_query.get("semantic_query"):
                search_query += f" {parsed_query['semantic_query']}"
            
            search_query = search_query.strip() or query
            
            try:
                results = await self.search(search_query, limit=limit)
                return await format_search_results(self, results, parsed_query)
            except Exception as e:
                logger.error(f"❌ Service history search failed: {e}")
                return {"results": []}
        
        else:
            # General search - use existing search functionality
            try:
                results = await self.search(query, limit=limit)
                return await format_search_results(self, results, parsed_query)
            except Exception as e:
                logger.error(f"❌ General search failed: {e}")
                return {"results": []}

    async def get_search_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the search collection and performance.
        
        Returns:
            Dict with collection statistics and search metrics
        """
        # Ensure client is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        if not self.client_manager.client:
            return {"error": "Qdrant client not available"}
        
        try:
            # Get collection info
            collection_info = await asyncio.to_thread(
                self.client_manager.client.get_collection,
                self.config.collection_name
            )
            
            # Get analytics for additional metrics
            analytics = await self.get_analytics()
            
            stats = {
                "collection_name": self.config.collection_name,
                "total_points": collection_info.points_count,
                "vectors_count": getattr(collection_info, 'vectors_count', 0),
                "indexed_vectors_count": getattr(collection_info, 'indexed_vectors_count', 0),
                "segments_count": getattr(collection_info, 'segments_count', 0),
                "status": str(collection_info.status) if hasattr(collection_info, 'status') else 'unknown',
                "config": {
                    "vector_size": self.config.vector_size,
                    "distance": self.config.distance,
                    "embedding_model": self.config.embedding_model,
                    "default_search_limit": self.config.default_search_limit,
                    "score_threshold": self.config.score_threshold
                },
                "analytics_summary": {
                    "total_responses": analytics.get("total_responses", 0),
                    "unique_tools": len(analytics.get("groups", {})),
                    "group_counts": {k: v.get("count", 0) for k, v in analytics.get("groups", {}).items()}
                },
                "client_info": self.client_manager.get_connection_info(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Failed to get search statistics: {e}")
            return {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}

    def get_search_info(self) -> Dict[str, Any]:
        """
        Get information about the search manager and its status.
        
        Returns:
            Dict with search manager information and status
        """
        return {
            "client_manager_status": self.client_manager.get_connection_info(),
            "config": self.config.to_dict(),
            "available": self.client_manager.is_available,
            "initialized": self.client_manager.is_initialized,
            "search_capabilities": [
                "semantic_search",
                "filtered_search", 
                "id_lookup",
                "analytics",
                "unified_search",
                "response_retrieval"
            ],
            "query_parsers": [
                "parse_search_query",
                "parse_unified_query"
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# Legacy function for backward compatibility with the main middleware
async def _unified_search_core(middleware, query: str, limit: int = 10) -> Dict:
    """
    Legacy wrapper function for unified search to maintain compatibility.
    
    Args:
        middleware: QdrantUnifiedMiddleware instance (for compatibility)
        query: Search query string
        limit: Maximum number of results
        
    Returns:
        Dictionary in OpenAI MCP format with 'results' array
    """
    # Check if middleware has a search_manager attribute
    if hasattr(middleware, 'search_manager'):
        return await middleware.search_manager.unified_search_core(query, limit)
    
    # Fallback: create a temporary search manager
    logger.warning("Using fallback search manager creation - consider updating middleware integration")
    search_manager = QdrantSearchManager(middleware.client_manager if hasattr(middleware, 'client_manager') else middleware)
    return await search_manager.unified_search_core(query, limit)