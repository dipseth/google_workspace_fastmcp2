#!/usr/bin/env python3
"""
Qdrant Resource Registration for FastMCP

This module registers qdrant:// resources with FastMCP so they can be properly
discovered and accessed through the standard resource system.
"""

import logging
from typing_extensions import Dict, Any
from datetime import datetime, timezone

from fastmcp import FastMCP, Context

logger = logging.getLogger(__name__)


def setup_qdrant_resources(mcp: FastMCP, qdrant_middleware=None) -> None:
    """
    Setup Qdrant resources for FastMCP resource discovery.
    
    Args:
        mcp: FastMCP instance to register resources with
        qdrant_middleware: QdrantUnifiedMiddleware instance (optional, for validation)
    """
    
    @mcp.resource(
        uri="qdrant://collections/list",
        name="Qdrant Collections List",
        description="List all available Qdrant collections with detailed information including point counts, vector statistics, and status",
        mime_type="application/json",
        tags={"qdrant", "collections", "list", "vector-database", "analytics", "admin"},
        meta={
            "handler": "QdrantResourceHandler",
            "middleware_delegated": True,
            "requires_client": True
        }
    )
    async def list_qdrant_collections(ctx: Context):
        """List all Qdrant collections with detailed information.
        
        This resource provides comprehensive information about all collections
        in the connected Qdrant instance, including point counts, vector statistics,
        indexing status, and collection health metrics.
        
        Returns:
            QdrantCollectionsListResponse: Pydantic model with collections data
        """
        from middleware.qdrant_types import QdrantCollectionsListResponse, QdrantErrorResponse
        
        # Try to get cached result from middleware context
        cache_key = "qdrant_resource_qdrant://collections/list"
        cached_result = ctx.get_state(cache_key)
        
        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning("No cached Qdrant collections data found - middleware may not have processed this request")
            return QdrantErrorResponse(
                error="Qdrant collections data not available - middleware not initialized",
                uri="qdrant://collections/list",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False
            )
        
        # Return cached result as proper Pydantic model
        if isinstance(cached_result, QdrantCollectionsListResponse):
            return cached_result
        elif isinstance(cached_result, dict):
            # Convert dict to Pydantic model if needed
            return QdrantCollectionsListResponse(**cached_result)
        else:
            return cached_result
    
    @mcp.resource(
        uri="qdrant://collection/{collection_name}/info",
        name="Qdrant Collection Information",
        description="Get detailed information about a specific Qdrant collection including configuration, statistics, and health metrics",
        mime_type="application/json",
        tags={"qdrant", "collection", "info", "statistics", "admin"},
        meta={
            "handler": "QdrantResourceHandler",
            "middleware_delegated": True,
            "requires_client": True,
            "supports_parameters": True
        }
    )
    async def get_qdrant_collection_info(collection_name: str, ctx: Context):
        """Get detailed information about a specific Qdrant collection.
        
        Args:
            collection_name: Name of the collection to get info for
            
        Returns:
            QdrantCollectionDetailsResponse: Pydantic model with collection info
        """
        from middleware.qdrant_types import QdrantCollectionDetailsResponse, QdrantErrorResponse
        
        # Try to get cached result from middleware context
        cache_key = f"qdrant_resource_qdrant://collection/{collection_name}/info"
        cached_result = ctx.get_state(cache_key)
        
        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(f"No cached Qdrant collection info found for '{collection_name}' - middleware may not have processed this request")
            return QdrantErrorResponse(
                error=f"Collection info for '{collection_name}' not available - middleware not initialized",
                uri=f"qdrant://collection/{collection_name}/info",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False
            )
        
        # Return cached result as proper Pydantic model
        if isinstance(cached_result, QdrantCollectionDetailsResponse):
            return cached_result
        elif isinstance(cached_result, dict):
            # Convert dict to Pydantic model if needed
            return QdrantCollectionDetailsResponse(**cached_result)
        else:
            return cached_result
    
    @mcp.resource(
        uri="qdrant://collection/{collection_name}/responses/recent",
        name="Recent Qdrant Collection Responses",
        description="Get recent tool responses stored in a specific Qdrant collection with decompression and parsing",
        mime_type="application/json",
        tags={"qdrant", "collection", "responses", "recent", "tool-history"},
        meta={
            "handler": "QdrantResourceHandler",
            "middleware_delegated": True,
            "requires_client": True,
            "supports_parameters": True
        }
    )
    async def get_recent_collection_responses(collection_name: str, ctx: Context):
        """Get recent tool responses from a specific collection.
        
        Args:
            collection_name: Name of the collection to get responses from
            
        Returns:
            QdrantRecentResponsesResponse: Pydantic model with recent responses
        """
        from middleware.qdrant_types import QdrantRecentResponsesResponse, QdrantErrorResponse
        
        # Try to get cached result from middleware context
        cache_key = f"qdrant_resource_qdrant://collection/{collection_name}/responses/recent"
        cached_result = ctx.get_state(cache_key)
        
        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(f"No cached Qdrant responses found for '{collection_name}' - middleware may not have processed this request")
            return QdrantErrorResponse(
                error=f"Recent responses for '{collection_name}' not available - middleware not initialized",
                uri=f"qdrant://collection/{collection_name}/responses/recent",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False
            )
        
        # Return cached result as proper Pydantic model
        if isinstance(cached_result, QdrantRecentResponsesResponse):
            return cached_result
        elif isinstance(cached_result, dict):
            # Convert dict to Pydantic model if needed
            return QdrantRecentResponsesResponse(**cached_result)
        else:
            return cached_result
    
    @mcp.resource(
        uri="qdrant://search/{query}",
        name="Qdrant Global Search",
        description="Perform semantic search across all stored tool responses using natural language queries with relevance scoring",
        mime_type="application/json",
        tags={"qdrant", "search", "semantic", "global", "nlp", "vector-search"},
        meta={
            "handler": "QdrantResourceHandler", 
            "middleware_delegated": True,
            "requires_client": True,
            "supports_parameters": True,
            "search_type": "global"
        }
    )
    async def search_qdrant_global(query: str, ctx: Context):
        """Perform global semantic search across all stored responses.
        
        Args:
            query: Natural language search query
            
        Returns:
            QdrantSearchResponse: Pydantic model with search results
        """
        from middleware.qdrant_types import QdrantSearchResponse, QdrantErrorResponse
        
        # Try to get cached result from middleware context
        cache_key = f"qdrant_resource_qdrant://search/{query}"
        cached_result = ctx.get_state(cache_key)
        
        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(f"No cached Qdrant search results found for '{query}' - middleware may not have processed this request")
            return QdrantErrorResponse(
                error=f"Search results for '{query}' not available - middleware not initialized",
                uri=f"qdrant://search/{query}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False
            )
        
        # Return cached result as proper Pydantic model
        if isinstance(cached_result, QdrantSearchResponse):
            return cached_result
        elif isinstance(cached_result, dict):
            # Convert dict to Pydantic model if needed
            return QdrantSearchResponse(**cached_result)
        else:
            return cached_result
    
    @mcp.resource(
        uri="qdrant://search/{collection_name}/{query}",
        name="Qdrant Collection Search", 
        description="Perform semantic search within a specific Qdrant collection using natural language queries",
        mime_type="application/json",
        tags={"qdrant", "search", "semantic", "collection", "filtered", "vector-search"},
        meta={
            "handler": "QdrantResourceHandler",
            "middleware_delegated": True, 
            "requires_client": True,
            "supports_parameters": True,
            "search_type": "collection"
        }
    )
    async def search_qdrant_collection(collection_name: str, query: str, ctx: Context):
        """Perform semantic search within a specific collection.
        
        Args:
            collection_name: Name of the collection to search within
            query: Natural language search query
            
        Returns:
            QdrantSearchResponse: Pydantic model with search results
        """
        from middleware.qdrant_types import QdrantSearchResponse, QdrantErrorResponse
        
        # Try to get cached result from middleware context
        cache_key = f"qdrant_resource_qdrant://search/{collection_name}/{query}"
        cached_result = ctx.get_state(cache_key)
        
        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(f"No cached Qdrant search results found for '{collection_name}/{query}' - middleware may not have processed this request")
            return QdrantErrorResponse(
                error=f"Search results for '{collection_name}/{query}' not available - middleware not initialized",
                uri=f"qdrant://search/{collection_name}/{query}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False
            )
        
        # Return cached result as proper Pydantic model
        if isinstance(cached_result, QdrantSearchResponse):
            return cached_result
        elif isinstance(cached_result, dict):
            # Convert dict to Pydantic model if needed
            return QdrantSearchResponse(**cached_result)
        else:
            return cached_result
    
    # Register validation resource for testing middleware integration
    @mcp.resource(
        uri="qdrant://status",
        name="Qdrant Middleware Status",
        description="Check the status of Qdrant middleware integration including client availability, initialization state, and resource handler status",
        mime_type="application/json",
        tags={"qdrant", "status", "health", "middleware", "diagnostics"},
        meta={
            "handler": "QdrantResourceHandler",
            "middleware_delegated": True,
            "diagnostic": True
        }
    )
    async def get_qdrant_status(ctx: Context):
        """Get comprehensive status of Qdrant middleware and resources.
        
        Returns:
            QdrantStatusResponse: Pydantic model with middleware status
        """
        from middleware.qdrant_types import QdrantStatusResponse, QdrantErrorResponse
        
        # Try to get cached result from middleware context
        cache_key = "qdrant_resource_qdrant://status"
        cached_result = ctx.get_state(cache_key)
        
        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning("No cached Qdrant status found - middleware may not have processed this request")
            return QdrantErrorResponse(
                error="Qdrant status not available - middleware not initialized",
                uri="qdrant://status",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False
            )
        
        # Return cached result as proper Pydantic model
        if isinstance(cached_result, QdrantStatusResponse):
            return cached_result
        elif isinstance(cached_result, dict):
            # Convert dict to Pydantic model if needed
            return QdrantStatusResponse(**cached_result)
        else:
            return cached_result
    
    logger.info("✅ Qdrant resources registered with FastMCP (handled by QdrantUnifiedMiddleware)")
    
    # Log resource registration summary
    resource_count = 6
    logger.info(f"📊 Registered {resource_count} qdrant:// resources:")
    logger.info("   • qdrant://collections/list - List all collections")
    logger.info("   • qdrant://collection/{name}/info - Collection details")
    logger.info("   • qdrant://collection/{name}/responses/recent - Recent responses")
    logger.info("   • qdrant://search/{query} - Global semantic search")
    logger.info("   • qdrant://search/{collection}/{query} - Collection search")
    logger.info("   • qdrant://status - Middleware status and health")