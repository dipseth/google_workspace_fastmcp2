#!/usr/bin/env python3
"""
Qdrant Resource Registration for FastMCP

This module registers qdrant:// resources with FastMCP so they can be properly
discovered and accessed through the standard resource system.
"""

from datetime import datetime, timezone

from fastmcp import Context, FastMCP
from fastmcp.resources import ResourceContent

from config.enhanced_logging import setup_logger

logger = setup_logger()


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
            "requires_client": True,
        },
    )
    async def list_qdrant_collections(ctx: Context) -> list[ResourceContent]:
        """List all Qdrant collections with detailed information.

        This resource provides comprehensive information about all collections
        in the connected Qdrant instance, including point counts, vector statistics,
        indexing status, and collection health metrics.

        Returns:
            list[ResourceContent]: JSON content with collections data
        """
        from middleware.qdrant_types import (
            QdrantCollectionsListResponse,
            QdrantErrorResponse,
        )

        # Try to get cached result from middleware context
        cache_key = "qdrant_resource_qdrant://collections/list"
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(
                "No cached Qdrant collections data found - middleware may not have processed this request"
            )
            response = QdrantErrorResponse(
                error="Qdrant collections data not available - middleware not initialized",
                uri="qdrant://collections/list",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False,
            )
            return [
                ResourceContent(response.model_dump(), mime_type="application/json")
            ]

        # Return cached result as ResourceContent
        if hasattr(cached_result, "model_dump"):
            return [
                ResourceContent(
                    cached_result.model_dump(), mime_type="application/json"
                )
            ]
        elif isinstance(cached_result, dict):
            return [ResourceContent(cached_result, mime_type="application/json")]
        else:
            return [
                ResourceContent(
                    {"result": str(cached_result)}, mime_type="application/json"
                )
            ]

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
            "supports_parameters": True,
        },
    )
    async def get_qdrant_collection_info(
        collection_name: str, ctx: Context
    ) -> list[ResourceContent]:
        """Get detailed information about a specific Qdrant collection.

        Args:
            collection_name: Name of the collection to get info for

        Returns:
            list[ResourceContent]: JSON content with collection info
        """
        from middleware.qdrant_types import (
            QdrantCollectionDetailsResponse,
            QdrantErrorResponse,
        )

        # Try to get cached result from middleware context
        cache_key = f"qdrant_resource_qdrant://collection/{collection_name}/info"
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(
                f"No cached Qdrant collection info found for '{collection_name}' - middleware may not have processed this request"
            )
            response = QdrantErrorResponse(
                error=f"Collection info for '{collection_name}' not available - middleware not initialized",
                uri=f"qdrant://collection/{collection_name}/info",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False,
            )
            return [
                ResourceContent(response.model_dump(), mime_type="application/json")
            ]

        # Return cached result as ResourceContent
        if hasattr(cached_result, "model_dump"):
            return [
                ResourceContent(
                    cached_result.model_dump(), mime_type="application/json"
                )
            ]
        elif isinstance(cached_result, dict):
            return [ResourceContent(cached_result, mime_type="application/json")]
        else:
            return [
                ResourceContent(
                    {"result": str(cached_result)}, mime_type="application/json"
                )
            ]

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
            "supports_parameters": True,
        },
    )
    async def get_recent_collection_responses(
        collection_name: str, ctx: Context
    ) -> list[ResourceContent]:
        """Get recent tool responses from a specific collection.

        Args:
            collection_name: Name of the collection to get responses from

        Returns:
            list[ResourceContent]: JSON content with recent responses
        """
        from middleware.qdrant_types import (
            QdrantErrorResponse,
            QdrantRecentResponsesResponse,
        )

        # Try to get cached result from middleware context
        cache_key = (
            f"qdrant_resource_qdrant://collection/{collection_name}/responses/recent"
        )
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(
                f"No cached Qdrant responses found for '{collection_name}' - middleware may not have processed this request"
            )
            response = QdrantErrorResponse(
                error=f"Recent responses for '{collection_name}' not available - middleware not initialized",
                uri=f"qdrant://collection/{collection_name}/responses/recent",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False,
            )
            return [
                ResourceContent(response.model_dump(), mime_type="application/json")
            ]

        # Return cached result as ResourceContent
        if hasattr(cached_result, "model_dump"):
            return [
                ResourceContent(
                    cached_result.model_dump(), mime_type="application/json"
                )
            ]
        elif isinstance(cached_result, dict):
            return [ResourceContent(cached_result, mime_type="application/json")]
        else:
            return [
                ResourceContent(
                    {"result": str(cached_result)}, mime_type="application/json"
                )
            ]

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
            "search_type": "global",
        },
    )
    async def search_qdrant_global(query: str, ctx: Context) -> list[ResourceContent]:
        """Perform global semantic search across all stored responses.

        Args:
            query: Natural language search query

        Returns:
            list[ResourceContent]: JSON content with search results
        """
        from middleware.qdrant_types import QdrantErrorResponse, QdrantSearchResponse

        # Try to get cached result from middleware context
        cache_key = f"qdrant_resource_qdrant://search/{query}"
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(
                f"No cached Qdrant search results found for '{query}' - middleware may not have processed this request"
            )
            response = QdrantErrorResponse(
                error=f"Search results for '{query}' not available - middleware not initialized",
                uri=f"qdrant://search/{query}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False,
            )
            return [
                ResourceContent(response.model_dump(), mime_type="application/json")
            ]

        # Return cached result as ResourceContent
        if hasattr(cached_result, "model_dump"):
            return [
                ResourceContent(
                    cached_result.model_dump(), mime_type="application/json"
                )
            ]
        elif isinstance(cached_result, dict):
            return [ResourceContent(cached_result, mime_type="application/json")]
        else:
            return [
                ResourceContent(
                    {"result": str(cached_result)}, mime_type="application/json"
                )
            ]

    @mcp.resource(
        uri="qdrant://search/{collection_name}/{query}",
        name="Qdrant Collection Search",
        description="Perform semantic search within a specific Qdrant collection using natural language queries",
        mime_type="application/json",
        tags={
            "qdrant",
            "search",
            "semantic",
            "collection",
            "filtered",
            "vector-search",
        },
        meta={
            "handler": "QdrantResourceHandler",
            "middleware_delegated": True,
            "requires_client": True,
            "supports_parameters": True,
            "search_type": "collection",
        },
    )
    async def search_qdrant_collection(
        collection_name: str, query: str, ctx: Context
    ) -> list[ResourceContent]:
        """Perform semantic search within a specific collection.

        Args:
            collection_name: Name of the collection to search within
            query: Natural language search query

        Returns:
            list[ResourceContent]: JSON content with search results
        """
        from middleware.qdrant_types import QdrantErrorResponse, QdrantSearchResponse

        # Try to get cached result from middleware context
        cache_key = f"qdrant_resource_qdrant://search/{collection_name}/{query}"
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(
                f"No cached Qdrant search results found for '{collection_name}/{query}' - middleware may not have processed this request"
            )
            response = QdrantErrorResponse(
                error=f"Search results for '{collection_name}/{query}' not available - middleware not initialized",
                uri=f"qdrant://search/{collection_name}/{query}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False,
            )
            return [
                ResourceContent(response.model_dump(), mime_type="application/json")
            ]

        # Return cached result as ResourceContent
        if hasattr(cached_result, "model_dump"):
            return [
                ResourceContent(
                    cached_result.model_dump(), mime_type="application/json"
                )
            ]
        elif isinstance(cached_result, dict):
            return [ResourceContent(cached_result, mime_type="application/json")]
        else:
            return [
                ResourceContent(
                    {"result": str(cached_result)}, mime_type="application/json"
                )
            ]

    @mcp.resource(
        uri="qdrant://cache",
        name="Qdrant Tool Response Cache",
        description="Get cached tool responses from Qdrant organized by tool name with point metadata including IDs, timestamps, and user emails",
        mime_type="application/json",
        tags={"qdrant", "cache", "tool-responses", "metadata", "analytics"},
        meta={
            "handler": "QdrantResourceHandler",
            "middleware_delegated": True,
            "requires_client": True,
        },
    )
    async def get_qdrant_cache(ctx: Context) -> list[ResourceContent]:
        """Get tool response cache from Qdrant organized by tool name.

        Returns a dictionary where keys are tool names and values are arrays of
        point metadata objects containing point_id, timestamp, and user_email.

        Returns:
            list[ResourceContent]: JSON content with {tool_name: [{point_id, timestamp, user_email}, ...], ...}
        """
        from middleware.qdrant_types import QdrantErrorResponse

        # Try to get cached result from middleware context
        cache_key = "qdrant_resource_qdrant://cache"
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(
                "No cached Qdrant cache data found - middleware may not have processed this request"
            )
            response = QdrantErrorResponse(
                error="Qdrant cache data not available - middleware not initialized",
                uri="qdrant://cache",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False,
            )
            return [
                ResourceContent(response.model_dump(), mime_type="application/json")
            ]

        # Return cached result as ResourceContent
        if hasattr(cached_result, "model_dump"):
            return [
                ResourceContent(
                    cached_result.model_dump(), mime_type="application/json"
                )
            ]
        elif isinstance(cached_result, dict):
            return [ResourceContent(cached_result, mime_type="application/json")]
        else:
            return [
                ResourceContent(
                    {"result": str(cached_result)}, mime_type="application/json"
                )
            ]

    @mcp.resource(
        uri="qdrant://collection/{collection_name}/{point_id}",
        name="Qdrant Point Details",
        description="Retrieve complete point data including payload, metadata, and decompressed tool response content from a Qdrant collection by UUID point ID",
        mime_type="application/json",
        tags={"qdrant", "collection", "point", "details", "metadata", "tool-response"},
        meta={
            "handler": "QdrantResourceHandler",
            "middleware_delegated": True,
            "requires_client": True,
            "supports_parameters": True,
            "note": "Processed by QdrantUnifiedMiddleware.on_read_resource with automatic cache coordination",
        },
    )
    async def get_qdrant_point_details(
        collection_name: str, point_id: str, ctx: Context
    ) -> list[ResourceContent]:
        """Retrieve detailed information about a specific stored tool response point.

        This resource fetches a complete point from Qdrant including all metadata,
        payload data, and automatically decompressed response content. The middleware
        handles caching through FastMCP's context state management.

        Args:
            collection_name: Name of the Qdrant collection (e.g., 'mcp_tool_responses')
            point_id: UUID identifier of the point to retrieve (e.g., '378d763e-39ac-409a-a616-769bad39e71c')
            ctx: FastMCP Context with state management for caching

        Returns:
            list[ResourceContent]: JSON content containing:
                - point_exists: Whether the point was found
                - payload: Complete point metadata and tool response data
                - tool_name: Extracted tool name for convenience
                - user_email: Associated user email
                - timestamp: When the response was stored
                - response_data: Decompressed tool response content
                - compressed: Whether original data was compressed

        Example URI:
            qdrant://collection/mcp_tool_responses/378d763e-39ac-409a-a616-769bad39e71c

        Note:
            The middleware caches results in FastMCP context state using the pattern:
            `qdrant_resource_qdrant://collection/{collection_name}/{point_id}`
        """
        from middleware.qdrant_types import QdrantErrorResponse

        # Try to get cached result from middleware context using FastMCP context pattern
        cache_key = f"qdrant_resource_qdrant://collection/{collection_name}/{point_id}"
        logger.info(f"🔍 Resource handler looking up cache key: {cache_key}")

        # IMPORTANT: Must use ctx directly (Context object is the FastMCP context)
        # Context has get_state/set_state methods - this is different from MiddlewareContext!
        cached_result = await ctx.get_state(cache_key)
        logger.info(
            f"📦 Cache lookup result: {type(cached_result).__name__ if cached_result else 'None'}"
        )

        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(
                f"⚠️ No cached Qdrant point details found for '{collection_name}/{point_id}' - middleware may not have processed this request"
            )
            response = QdrantErrorResponse(
                error=f"Point details for '{collection_name}/{point_id}' not available - middleware not initialized",
                uri=f"qdrant://collection/{collection_name}/{point_id}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False,
            )
            return [
                ResourceContent(response.model_dump(), mime_type="application/json")
            ]

        logger.info("✅ Returning cached result from resource handler")
        # Return cached result as ResourceContent
        if hasattr(cached_result, "model_dump"):
            return [
                ResourceContent(
                    cached_result.model_dump(), mime_type="application/json"
                )
            ]
        elif isinstance(cached_result, dict):
            return [ResourceContent(cached_result, mime_type="application/json")]
        else:
            return [
                ResourceContent(
                    {"result": str(cached_result)}, mime_type="application/json"
                )
            ]

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
            "diagnostic": True,
        },
    )
    async def get_qdrant_status(ctx: Context) -> list[ResourceContent]:
        """Get comprehensive status of Qdrant middleware and resources.

        Returns:
            list[ResourceContent]: JSON content with middleware status
        """
        from middleware.qdrant_types import QdrantErrorResponse, QdrantStatusResponse

        # Try to get cached result from middleware context
        cache_key = "qdrant_resource_qdrant://status"
        cached_result = await ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't process this request
            logger.warning(
                "No cached Qdrant status found - middleware may not have processed this request"
            )
            response = QdrantErrorResponse(
                error="Qdrant status not available - middleware not initialized",
                uri="qdrant://status",
                timestamp=datetime.now(timezone.utc).isoformat(),
                qdrant_enabled=False,
            )
            return [
                ResourceContent(response.model_dump(), mime_type="application/json")
            ]

        # Return cached result as ResourceContent
        if isinstance(cached_result, (QdrantStatusResponse, QdrantErrorResponse)):
            return [
                ResourceContent(
                    cached_result.model_dump(), mime_type="application/json"
                )
            ]
        elif isinstance(cached_result, dict):
            return [ResourceContent(cached_result, mime_type="application/json")]
        elif hasattr(cached_result, "model_dump"):
            return [
                ResourceContent(
                    cached_result.model_dump(), mime_type="application/json"
                )
            ]
        else:
            return [
                ResourceContent(
                    {"result": str(cached_result)}, mime_type="application/json"
                )
            ]

    logger.info(
        "✅ Qdrant resources registered with FastMCP (handled by QdrantUnifiedMiddleware)"
    )

    # Log resource registration summary
    resource_count = 8
    logger.info(f"📊 Registered {resource_count} qdrant:// resources:")
    logger.info("   • qdrant://collections/list - List all collections")
    logger.info("   • qdrant://collection/{name}/info - Collection details")
    logger.info("   • qdrant://collection/{name}/responses/recent - Recent responses")
    logger.info("   • qdrant://collection/{name}/{point_id} - Point details by UUID")
    logger.info("   • qdrant://search/{query} - Global semantic search")
    logger.info("   • qdrant://search/{collection}/{query} - Collection search")
    logger.info("   • qdrant://cache - Tool response cache metadata")
    logger.info("   • qdrant://status - Middleware status and health")
