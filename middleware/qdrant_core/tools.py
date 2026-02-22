#!/usr/bin/env python3
"""
Qdrant MCP Tools Module

This module provides MCP tool setup and registration functionality for Qdrant vector database operations.
Extracted from middleware/qdrant_middleware.py to create focused, reusable tool definitions.

Key Features:
- Modern search tool with Pydantic types and intelligent query parsing
- Document fetch tool with comprehensive metadata
- Legacy tool support for backward compatibility
- Service-aware result formatting with icons and metadata
- Analytics and overview capabilities
- Integration with all qdrant_core managers for clean separation of concerns

Tools Provided:
- search: Advanced vector search with query parsing and service filtering
- fetch: Retrieve complete documents by point ID with structured metadata
- search_tool_history: Legacy search tool for backward compatibility
- get_tool_analytics: Analytics and usage reporting tool
- get_response_details: Legacy tool for fetching response details by ID

═══════════════════════════════════════════════════════════════════════════════
                      🧠 THE SEMANTIC MEMORY PALACE 🧠
═══════════════════════════════════════════════════════════════════════════════

    Not just storage, but understanding—
    vectors encode what words are handing.
    "Budget reports from last quarter"
    finds meaning, not just character order.

    Each tool response becomes a point,
    embedded where semantics anoint.
    Similarity scores float between
    zero and one, the space between.

    fetch() retrieves by point ID,
    the exact document, nothing hid.
    search() roams the vector field,
    returning what the queries yield.

    Legacy tools remain for those
    who learned the old API's prose.
    search_tool_history still speaks,
    backward compatibility it seeks.

    Analytics count what tools were called,
    which services stood, which nearly stalled.
    The memory palace keeps its logs,
    navigating semantic fogs.

    Managers separate concerns with grace:
    client, search, each in its place.
    The tools are clean, the edges clear—
    query the past, the answers appear.

                                        — Field Notes, Jan 2026

═══════════════════════════════════════════════════════════════════════════════
"""

import json
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Any, Dict, List, Optional

from pydantic import Field

from config.enhanced_logging import setup_logger

# Import types
from middleware.qdrant_types import (
    QdrantDocumentMetadata,
    QdrantFetchResponse,
    QdrantSearchResultItem,
    QdrantToolSearchResponse,
)
from tools.common_types import UserGoogleEmail

# Import qdrant_core modules
from . import (
    extract_service_from_tool,
    parse_unified_query,
)

if TYPE_CHECKING:
    from middleware.qdrant_core.dsl_executor import SearchV2Executor
    from middleware.qdrant_core.dsl_query_builder import QueryBuilder
    from middleware.qdrant_core.dsl_types import SearchV2Response

logger = setup_logger()


def _build_grammar_description(symbols: Dict[str, str]) -> str:
    """Build a human-readable grammar description for the DSL."""
    filter_symbols = {}
    query_symbols = {}
    for name, symbol in symbols.items():
        lower = name.lower()
        if any(
            k in lower
            for k in ("filter", "fieldcondition", "matchvalue", "matchtext", "range",
                       "matchany", "hasidcondition", "isnullcondition", "isemptycondition")
        ):
            filter_symbols[name] = symbol
        elif any(
            k in lower
            for k in ("recommend", "discover", "fusion", "prefetch", "orderby",
                       "context", "searchparams")
        ):
            query_symbols[name] = symbol

    lines = [
        "Parameterized DSL Grammar:",
        "  symbol{param1=value1, param2=value2}",
        "",
        "Values can be:",
        '  - Strings: "hello"',
        "  - Numbers: 42, 3.14",
        "  - Booleans: true, false",
        "  - Null: null",
        "  - Nested symbols: symbol{...}",
        "  - Lists: [item1, item2, ...]",
        "",
        "Key filter symbols (used in 'dsl' param):",
    ]
    for name, symbol in sorted(filter_symbols.items()):
        lines.append(f"  {symbol} = {name}")

    if query_symbols:
        lines.append("")
        lines.append("Advanced query symbols (used in 'query_dsl'/'prefetch_dsl' params):")
        lines.append("  (Types without Unicode symbols use full class names as identifiers)")
        for name, symbol in sorted(query_symbols.items()):
            lines.append(f"  {symbol} = {name}")

    return "\n".join(lines)


def _convert_v2_to_search_results(v2_response: "SearchV2Response") -> List[Dict[str, Any]]:
    """Convert SearchV2Response results to the dict format expected by the search tool."""
    raw_results = []
    for item in v2_response.results:
        raw_results.append({
            "id": item.id,
            "score": item.score if item.score is not None else 0.0,
            "tool_name": item.tool_name or item.payload.get("tool_name", "unknown_tool"),
            "timestamp": item.timestamp or item.payload.get("timestamp", "unknown"),
            "user_email": item.user_email or item.payload.get("user_email", "unknown"),
            "payload": item.payload,
        })
    return raw_results


def setup_enhanced_qdrant_tools(
    mcp, middleware=None, client_manager=None, search_manager=None
):
    """
    Setup enhanced Qdrant tools using FastMCP2 conventions with Pydantic models.

    This function can work with either:
    1. A unified middleware instance (legacy compatibility)
    2. Individual manager instances (preferred for new integrations)

    Args:
        mcp: FastMCP server instance for tool registration
        middleware: QdrantUnifiedMiddleware instance (legacy compatibility)
        client_manager: QdrantClientManager instance (preferred)
        search_manager: QdrantSearchManager instance (preferred)
    """
    # Determine which managers to use
    if client_manager and search_manager:
        # Use provided managers (preferred approach)
        _client_manager = client_manager
        _search_manager = search_manager
        logger.info("🔧 Using provided qdrant_core managers")
    elif middleware:
        # Use middleware methods (legacy compatibility)
        # Check if middleware has the new manager attributes
        if hasattr(middleware, "client_manager") and hasattr(
            middleware, "search_manager"
        ):
            _client_manager = middleware.client_manager
            _search_manager = middleware.search_manager
            logger.info("🔧 Using middleware's qdrant_core managers")
        else:
            # Fallback to direct middleware methods (legacy)
            _client_manager = middleware
            _search_manager = middleware
            logger.warning(
                "🔧 Using legacy middleware methods - consider updating to use qdrant_core managers"
            )
    else:
        raise ValueError(
            "Either middleware or both client_manager and search_manager must be provided"
        )

    # Lazy-init DSL executor and builder for DSL search mode
    _dsl_wrapper = None
    _dsl_builder: Optional["QueryBuilder"] = None
    _dsl_executor: Optional["SearchV2Executor"] = None

    def _get_dsl_builder() -> "QueryBuilder":
        nonlocal _dsl_wrapper, _dsl_builder
        if _dsl_builder is None:
            if _dsl_wrapper is None:
                from middleware.qdrant_core.qdrant_models_wrapper import (
                    get_qdrant_models_wrapper,
                )
                _dsl_wrapper = get_qdrant_models_wrapper()
            from middleware.qdrant_core.dsl_query_builder import QueryBuilder
            _dsl_builder = QueryBuilder(_dsl_wrapper)
        return _dsl_builder

    def _get_dsl_executor() -> "SearchV2Executor":
        nonlocal _dsl_executor
        if _dsl_executor is None:
            from middleware.qdrant_core.dsl_executor import SearchV2Executor
            _dsl_executor = SearchV2Executor(_client_manager, _get_dsl_builder())
        return _dsl_executor

    # Build DSL description dynamically from wrapper symbols at registration time
    def _get_dsl_description_suffix() -> str:
        """Build DSL grammar section for the search tool description."""
        try:
            builder = _get_dsl_builder()
            w = builder.wrapper
            symbols = dict(w.symbol_mapping) if w.symbol_mapping else {}
            grammar = _build_grammar_description(symbols)
            examples = (
                "Examples: "
                'ƒ{must=[ʄ{key="tool_name", match=☆{value="search"}}]} '
                "(filter by tool_name), "
                'ƒ{must=[ʄ{key="tool_name", match=ɱ{any=["send_dynamic_card", "send_gmail_message"]}}]} '
                "(match any of multiple values)."
            )
            return f"\n\n{grammar}\n\n{examples}"
        except Exception:
            # Fallback if wrapper isn't available yet
            return (
                "\n\nDSL Grammar: symbol{param=value}. "
                "Key filter symbols: ƒ=Filter, ʄ=FieldCondition, ☆=MatchValue, "
                "ɱ=MatchAny, ṁ=MatchText, ř=Range, ℏ=HasIdCondition. "
                "Advanced query symbols: φ=FusionQuery, R_4=RecommendQuery, "
                "D_2=DiscoverQuery, ¶=Prefetch, ø=OrderBy, ɵ=OrderByQuery."
            )

    _dsl_suffix = _get_dsl_description_suffix()

    @mcp.tool(
        name="search",
        description=(
            "Search through Qdrant vector database using natural language queries, "
            "filters, point IDs, or DSL filter notation. Supports semantic search, "
            "service-specific filtering, analytics queries, recommendation-style "
            "example search, direct point lookup, and advanced DSL queries. "
            "When filter_dsl is provided, routes to the DSL executor for precise "
            "filter-based search. "
            "Returns structured search results with relevance scores and metadata."
            + _dsl_suffix
        ),
        tags={
            "qdrant",
            "search",
            "vector",
            "semantic",
            "database",
            "analytics",
            "recommend",
            "dsl",
            "filter",
        },
        annotations={
            "title": "Qdrant Vector Search Tool",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def search(
        query: str,
        limit: int = 10,
        score_threshold: float = 0.3,
        positive_point_ids: Optional[List[str]] = None,
        negative_point_ids: Optional[List[str]] = None,
        filter_dsl: Optional[str] = None,
        query_dsl: Optional[str] = None,
        prefetch_dsl: Optional[str] = None,
        dry_run: bool = False,
        collection: Annotated[Optional[str], Field(default=None, description="Optional Qdrant collection name to search. If not provided, uses the server's default collection.")] = None,
        user_google_email: UserGoogleEmail = None,
    ) -> QdrantToolSearchResponse:
        """
        Search through Qdrant vector database with intelligent query parsing.

        Query Types Supported:
        - Semantic Search: "email collaboration documents"
        - Service History: "gmail last week", "service:drive"
        - Analytics: "overview", "analytics", "dashboard"
        - Point Lookup: "id:12345" or "point:abc-def-123"
        - Filtered Search: "user_email:test@gmail.com document creation"
        - Index Search: "tool_name:search_gmail_messages" or "service:gmail"
        - Example-based recommend: positive/negative point ID lists
        - DSL Filter: Set filter_dsl to a DSL string (grammar is in the tool description).
          query becomes the semantic text when filter_dsl is set.

        Args:
            query: Search query string (natural language, filters, or semantic text for DSL mode)
            limit: Maximum number of results to return (1-100)
            score_threshold: Minimum similarity score (0.0-1.0)
            positive_point_ids: Optional list of point IDs to use as positive examples
            negative_point_ids: Optional list of point IDs to use as negative examples
            filter_dsl: Optional DSL filter string (e.g., 'ƒ{must=[...]}')
            query_dsl: Optional advanced query DSL (RecommendQuery, FusionQuery, OrderByQuery)
            prefetch_dsl: Optional multi-stage Prefetch DSL
            dry_run: If True with filter_dsl, parse+build without executing
            collection: Optional collection name override
            user_google_email: User's Google email for access control

        Returns:
            QdrantToolSearchResponse: Structured search results with metadata
        """
        start_time = time.time()

        try:
            # Ensure client manager is initialized
            if not _client_manager.is_initialized:
                await _client_manager.initialize()

            if not _client_manager.is_available:
                return QdrantToolSearchResponse(
                    results=[],
                    query=query,
                    query_type="error",
                    total_results=0,
                    collection_name=_client_manager.config.collection_name,
                    error="Qdrant client not available - database may not be running",
                )

            target_collection = collection or _client_manager.config.collection_name
            raw_results: List[Dict[str, Any]] = []

            # 0) DSL filter mode — route to SearchV2Executor
            if filter_dsl is not None:
                query_type = "dsl"
                logger.info(
                    f"🔧 Qdrant DSL search: filter_dsl='{filter_dsl[:80]}...', "
                    f"query_text='{query}', dry_run={dry_run}"
                )
                executor = _get_dsl_executor()
                v2_response = await executor.execute_dsl(
                    dsl=filter_dsl,
                    collection=target_collection,
                    query_text=query if query.strip() else None,
                    query_dsl=query_dsl,
                    prefetch_dsl=prefetch_dsl,
                    limit=limit,
                    score_threshold=score_threshold,
                    dry_run=dry_run,
                )

                # Convert V2 results to unified format
                raw_results = _convert_v2_to_search_results(v2_response)
                dsl_input = v2_response.dsl_input
                built_filter_repr = v2_response.built_filter_repr

                if v2_response.error:
                    processing_time = (time.time() - start_time) * 1000
                    return QdrantToolSearchResponse(
                        results=[],
                        query=query,
                        query_type="dsl_error",
                        total_results=0,
                        processing_time_ms=processing_time,
                        collection_name=target_collection,
                        error=v2_response.error,
                        dsl_input=dsl_input,
                        built_filter_repr=built_filter_repr,
                    )

            # 1) Example-based recommendation mode (bypasses text query)
            elif positive_point_ids or negative_point_ids:
                query_type = "recommend"
                dsl_input = None
                built_filter_repr = None
                logger.info(
                    f"🧲 Qdrant recommend search: "
                    f"positive={positive_point_ids}, negative={negative_point_ids}"
                )
                raw_results = await _search_manager.search(
                    query="",
                    limit=limit,
                    score_threshold=score_threshold,
                    positive_point_ids=positive_point_ids,
                    negative_point_ids=negative_point_ids,
                    query_type="recommend",
                    collection=target_collection,
                )

            # 2) Query-based modes (overview / service_history / general)
            else:
                dsl_input = None
                built_filter_repr = None
                parsed_query = parse_unified_query(query)
                query_type = parsed_query["capability"]

                logger.info(
                    f"🔍 Qdrant search: query='{query}', "
                    f"type={query_type}, confidence={parsed_query['confidence']:.2f}"
                )

                if query_type == "overview":
                    # Get analytics/overview data and adapt to search result format
                    try:
                        analytics = await _search_manager.get_analytics()
                        if analytics and "groups" in analytics:
                            for group_name, group_data in list(
                                analytics["groups"].items()
                            )[:limit]:
                                raw_results.append(
                                    {
                                        "id": f"analytics_{group_name}",
                                        "score": 1.0,
                                        "tool_name": f"analytics_{group_name}",
                                        "timestamp": analytics.get("generated_at"),
                                        "user_email": "system",
                                    }
                                )
                    except Exception as e:
                        logger.error(f"❌ Overview analytics failed: {e}")

                elif query_type == "service_history":
                    # Build filtered query for service history
                    search_query = ""
                    if parsed_query.get("service_name"):
                        search_query += f"tool_name:{parsed_query['service_name']}"
                    if parsed_query.get("time_range"):
                        search_query += f" {parsed_query['time_range']}"
                    if parsed_query.get("semantic_query"):
                        search_query += f" {parsed_query['semantic_query']}"

                    search_query = search_query.strip() or query
                    raw_results = await _search_manager.search(
                        search_query,
                        limit=limit,
                        score_threshold=score_threshold,
                        query_type="service_history",
                        collection=target_collection,
                    )

                else:
                    # General search - use existing search functionality
                    raw_results = await _search_manager.search(
                        query,
                        limit=limit,
                        score_threshold=score_threshold,
                        query_type="general",
                        collection=target_collection,
                    )

            # 3) Format results with service metadata
            formatted_results: List[QdrantSearchResultItem] = []
            for result in raw_results:
                # search_manager.search returns dicts with normalized keys
                result_id = str(result.get("id", "unknown"))
                tool_name = result.get("tool_name") or "unknown_tool"
                timestamp = result.get("timestamp") or "unknown"
                user_email = result.get("user_email") or "unknown"
                score = float(result.get("score", 0.0))

                # Determine service from tool name
                service_name = extract_service_from_tool(tool_name)

                # Get service metadata
                try:
                    from auth.scope_registry import ScopeRegistry

                    service_meta = ScopeRegistry.SERVICE_METADATA.get(service_name, {})
                    service_icon = (
                        getattr(service_meta, "icon", "🔧") if service_meta else "🔧"
                    )
                    service_display = (
                        getattr(service_meta, "name", service_name.title())
                        if service_meta
                        else service_name.title()
                    )
                except ImportError:
                    service_icon = "🔧"
                    service_display = service_name.title()

                # Include raw payload for non-default collections where
                # the standard fields (tool_name, timestamp, etc.) won't exist
                is_non_default = target_collection != _client_manager.config.collection_name
                raw_payload = result.get("payload") if is_non_default else None

                formatted_results.append(
                    QdrantSearchResultItem(
                        id=result_id,
                        title=f"{service_icon} {service_display} - {tool_name}",
                        url=f"qdrant://{target_collection}?{result_id}",
                        score=score,
                        tool_name=tool_name,
                        service=service_name,
                        timestamp=timestamp,
                        user_email=user_email,
                        payload=raw_payload,
                    )
                )

            processing_time = (time.time() - start_time) * 1000

            return QdrantToolSearchResponse(
                results=formatted_results,
                query=query,
                query_type=query_type,
                total_results=len(formatted_results),
                processing_time_ms=processing_time,
                collection_name=target_collection,
                dsl_input=dsl_input,
                built_filter_repr=built_filter_repr,
            )

        except Exception as e:
            logger.error(f"❌ Qdrant search failed: {e}")
            processing_time = (time.time() - start_time) * 1000

            return QdrantToolSearchResponse(
                results=[],
                query=query,
                query_type="error",
                total_results=0,
                processing_time_ms=processing_time,
                collection_name=_client_manager.config.collection_name,
                error=str(e),
            )

    @mcp.tool(
        name="fetch",
        description="Retrieve complete document content from Qdrant by point ID. Supports single document fetch or batch fetch with optional client-side ordering by payload key.",
        tags={"qdrant", "fetch", "document", "vector", "database", "retrieval"},
        annotations={
            "title": "Qdrant Document Fetch Tool",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def fetch(
        point_id: str,
        point_ids: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        order_direction: str = "asc",
        user_google_email: UserGoogleEmail = None,
    ) -> QdrantFetchResponse:
        """
        Fetch complete document from Qdrant vector database by point ID, or
        optionally fetch a batch of documents and aggregate them into a single
        textual response.

        Args:
            point_id: Primary point identifier (UUID or string ID)
            point_ids: Optional additional point IDs to fetch in batch
            order_by: Optional payload key to sort batch results by (client-side)
            order_direction: "asc" (default) or "desc" for batch ordering
            user_google_email: User's Google email for access control

        Returns:
            QdrantFetchResponse: Complete document with metadata and content
        """
        try:
            # Ensure client manager is initialized
            if not _client_manager.is_initialized:
                await _client_manager.initialize()

            if not _client_manager.is_available:
                return QdrantFetchResponse(
                    id=point_id,
                    title="❌ Qdrant Not Available",
                    text="Qdrant client is not available. The vector database may not be running.",
                    url=f"qdrant://{_client_manager.config.collection_name}?{point_id}",
                    metadata=QdrantDocumentMetadata(
                        tool_name="error",
                        service="system",
                        service_display_name="System",
                        user_email="unknown",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        response_type="error",
                        arguments_count=0,
                        payload_type="error",
                        collection_name=_client_manager.config.collection_name,
                        point_id=point_id,
                    ),
                    found=False,
                    collection_name=_client_manager.config.collection_name,
                    error="no_client",
                )

            # Build list of IDs to fetch
            ids_to_fetch: List[str] = []
            if point_id:
                ids_to_fetch.append(str(point_id))
            if point_ids:
                ids_to_fetch.extend([str(pid) for pid in point_ids if pid])

            # De-duplicate while preserving order
            seen: set = set()
            ids_to_fetch = [i for i in ids_to_fetch if not (i in seen or seen.add(i))]

            if not ids_to_fetch:
                return QdrantFetchResponse(
                    id=point_id or "",
                    title="❌ No Point IDs Provided",
                    text="No point_ids or point_id were provided to fetch.",
                    url=f"qdrant://{_client_manager.config.collection_name}",
                    metadata=QdrantDocumentMetadata(
                        tool_name="error",
                        service="system",
                        service_display_name="System",
                        user_email="unknown",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        response_type="error",
                        arguments_count=0,
                        payload_type="error",
                        collection_name=_client_manager.config.collection_name,
                        point_id=point_id or "",
                    ),
                    found=False,
                    collection_name=_client_manager.config.collection_name,
                    error="no_ids",
                )

            # Single-ID fast path (backwards compatible behavior)
            if len(ids_to_fetch) == 1:
                single_id = ids_to_fetch[0]

                response_data = await _search_manager.get_response_by_id(single_id)

                if not response_data:
                    return QdrantFetchResponse(
                        id=single_id,
                        title="❌ Document Not Found",
                        text=f"No document found with point ID: {single_id}",
                        url=f"qdrant://{_client_manager.config.collection_name}?{single_id}",
                        metadata=QdrantDocumentMetadata(
                            tool_name="not_found",
                            service="system",
                            service_display_name="System",
                            user_email="unknown",
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            response_type="error",
                            arguments_count=0,
                            payload_type="not_found",
                            collection_name=_client_manager.config.collection_name,
                            point_id=single_id,
                        ),
                        found=False,
                        collection_name=_client_manager.config.collection_name,
                        error="not_found",
                    )

                # Extract information from response data
                tool_name = response_data.get("tool_name", "unknown_tool")
                timestamp = response_data.get("timestamp", "unknown")
                user_email = response_data.get("user_email", "unknown")
                arguments = response_data.get("arguments", {})
                response = response_data.get("response", {})
                payload_type = response_data.get("payload_type", "unknown")

                # Determine service and get metadata using qdrant_core function
                service_name = extract_service_from_tool(tool_name)
                try:
                    from auth.scope_registry import ScopeRegistry

                    service_meta = ScopeRegistry.SERVICE_METADATA.get(service_name, {})
                    service_icon = (
                        getattr(service_meta, "icon", "🔧") if service_meta else "🔧"
                    )
                    service_display_name = (
                        getattr(service_meta, "name", service_name.title())
                        if service_meta
                        else service_name.title()
                    )
                except ImportError:
                    service_icon = "🔧"
                    service_display_name = service_name.title()

                # Format title
                title = (
                    f"{service_icon} {service_display_name} - {tool_name} ({timestamp})"
                )

                # Format comprehensive text content
                text_sections = [
                    "=== QDRANT DOCUMENT ===",
                    f"Point ID: {single_id}",
                    f"Collection: {_client_manager.config.collection_name}",
                    f"Tool: {tool_name}",
                    f"Service: {service_display_name} ({service_name})",
                    f"User: {user_email}",
                    f"Timestamp: {timestamp}",
                    f"Type: {payload_type}",
                    "",
                    "=== TOOL ARGUMENTS ===",
                    json.dumps(arguments, indent=2) if arguments else "No arguments",
                    "",
                    "=== TOOL RESPONSE ===",
                    (
                        json.dumps(response, indent=2)
                        if isinstance(response, (dict, list))
                        else str(response)
                    ),
                    "",
                    "=== METADATA ===",
                    f"Arguments Count: {len(arguments) if isinstance(arguments, dict) else 0}",
                    f"Response Type: {type(response).__name__}",
                    f"Payload Type: {payload_type}",
                ]

                full_text = "\n".join(text_sections)

                # Create URL using specified format
                url = f"qdrant://{_client_manager.config.collection_name}?{single_id}"

                # Build structured metadata
                metadata = QdrantDocumentMetadata(
                    tool_name=tool_name,
                    service=service_name,
                    service_display_name=service_display_name,
                    user_email=user_email,
                    timestamp=timestamp,
                    response_type=type(response).__name__,
                    arguments_count=(
                        len(arguments) if isinstance(arguments, dict) else 0
                    ),
                    payload_type=payload_type,
                    collection_name=_client_manager.config.collection_name,
                    point_id=single_id,
                )

                return QdrantFetchResponse(
                    id=single_id,
                    title=title,
                    text=full_text,
                    url=url,
                    metadata=metadata,
                    found=True,
                    collection_name=_client_manager.config.collection_name,
                )

            # Batch path: fetch multiple IDs and aggregate
            responses_by_id = await _search_manager.get_responses_by_ids(ids_to_fetch)

            if not responses_by_id:
                return QdrantFetchResponse(
                    id=ids_to_fetch[0],
                    title="❌ Documents Not Found",
                    text=f"No documents found for point IDs: {', '.join(ids_to_fetch)}",
                    url=f"qdrant://{_client_manager.config.collection_name}",
                    metadata=QdrantDocumentMetadata(
                        tool_name="not_found",
                        service="system",
                        service_display_name="System",
                        user_email="unknown",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        response_type="error",
                        arguments_count=0,
                        payload_type="not_found",
                        collection_name=_client_manager.config.collection_name,
                        point_id=ids_to_fetch[0],
                    ),
                    found=False,
                    collection_name=_client_manager.config.collection_name,
                    error="not_found",
                )

            # Apply client-side ordering by payload key if requested
            ordered_ids = list(responses_by_id.keys())
            if order_by:

                def sort_key(pid: str):
                    data = responses_by_id.get(pid) or {}
                    val = data.get(order_by)
                    # Sort None values last
                    return (1, "") if val is None else (0, str(val))

                reverse = order_direction.lower() == "desc"
                ordered_ids.sort(key=sort_key, reverse=reverse)
            else:
                # Preserve original order (ids_to_fetch intersect found IDs)
                ordered_ids = [i for i in ids_to_fetch if i in responses_by_id]

            # Build aggregated text for all documents
            aggregated_sections: List[str] = []
            first_meta = None

            for idx, pid in enumerate(ordered_ids):
                response_data = responses_by_id[pid]

                tool_name = response_data.get("tool_name", "unknown_tool")
                timestamp = response_data.get("timestamp", "unknown")
                user_email = response_data.get("user_email", "unknown")
                arguments = response_data.get("arguments", {})
                response = response_data.get("response", {})
                payload_type = response_data.get("payload_type", "unknown")

                service_name = extract_service_from_tool(tool_name)
                try:
                    from auth.scope_registry import ScopeRegistry

                    service_meta = ScopeRegistry.SERVICE_METADATA.get(service_name, {})
                    service_icon = (
                        getattr(service_meta, "icon", "🔧") if service_meta else "🔧"
                    )
                    service_display_name = (
                        getattr(service_meta, "name", service_name.title())
                        if service_meta
                        else service_name.title()
                    )
                except ImportError:
                    service_icon = "🔧"
                    service_display_name = service_name.title()

                if idx == 0:
                    first_meta = {
                        "tool_name": tool_name,
                        "service_name": service_name,
                        "service_display_name": service_display_name,
                        "user_email": user_email,
                        "timestamp": timestamp,
                        "payload_type": payload_type,
                        "response_type": type(response).__name__,
                    }

                aggregated_sections.extend(
                    [
                        "=== QDRANT DOCUMENT ===",
                        f"Point ID: {pid}",
                        f"Collection: {_client_manager.config.collection_name}",
                        f"Tool: {tool_name}",
                        f"Service: {service_display_name} ({service_name})",
                        f"User: {user_email}",
                        f"Timestamp: {timestamp}",
                        f"Type: {payload_type}",
                        "",
                        "=== TOOL ARGUMENTS ===",
                        (
                            json.dumps(arguments, indent=2)
                            if arguments
                            else "No arguments"
                        ),
                        "",
                        "=== TOOL RESPONSE ===",
                        (
                            json.dumps(response, indent=2)
                            if isinstance(response, (dict, list))
                            else str(response)
                        ),
                        "",
                        "=== METADATA ===",
                        f"Arguments Count: {len(arguments) if isinstance(arguments, dict) else 0}",
                        f"Response Type: {type(response).__name__}",
                        f"Payload Type: {payload_type}",
                        "",
                    ]
                )

            aggregated_text = "\n".join(aggregated_sections)

            # Use first document's metadata as the primary metadata for the batch
            if first_meta is None:
                first_meta = {
                    "tool_name": "unknown_tool",
                    "service_name": "unknown",
                    "service_display_name": "Unknown",
                    "user_email": "unknown",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload_type": "unknown",
                    "response_type": "dict",
                }

            # Build title indicating batch
            title = (
                f"{first_meta['tool_name']} batch fetch "
                f"({len(ordered_ids)} documents, first at {first_meta['timestamp']})"
            )

            # URL cannot encode all IDs, so point to collection-level URI
            url = f"qdrant://{_client_manager.config.collection_name}"

            metadata = QdrantDocumentMetadata(
                tool_name=first_meta["tool_name"],
                service=first_meta["service_name"],
                service_display_name=first_meta["service_display_name"],
                user_email=first_meta["user_email"],
                timestamp=first_meta["timestamp"],
                response_type=first_meta["response_type"],
                arguments_count=0,  # ambiguous in batch context
                payload_type=first_meta["payload_type"],
                collection_name=_client_manager.config.collection_name,
                point_id=ordered_ids[0],
            )

            return QdrantFetchResponse(
                id=ordered_ids[0],
                title=title,
                text=aggregated_text,
                url=url,
                metadata=metadata,
                found=True,
                collection_name=_client_manager.config.collection_name,
            )

        except Exception as e:
            logger.error(f"❌ Qdrant fetch failed for {point_id}: {e}")

            return QdrantFetchResponse(
                id=point_id,
                title="❌ Fetch Error",
                text=f"Failed to retrieve document with point ID {point_id}: {str(e)}",
                url=f"qdrant://{_client_manager.config.collection_name}?{point_id}",
                metadata=QdrantDocumentMetadata(
                    tool_name="error",
                    service="system",
                    service_display_name="System",
                    user_email="unknown",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    response_type="error",
                    arguments_count=0,
                    payload_type="error",
                    collection_name=_client_manager.config.collection_name,
                    point_id=point_id,
                ),
                found=False,
                collection_name=_client_manager.config.collection_name,
                error=str(e),
            )

    # Keep existing legacy tools for backward compatibility
    @mcp.tool(
        name="search_tool_history",
        description="Advanced search through historical tool responses with support for: ID lookup (id:xxxxx), filtered search (user_email:test@gmail.com), combined filters with semantic search (user_email:test@gmail.com documents for gardening), and natural language queries",
        tags={
            "qdrant",
            "search",
            "history",
            "semantic",
            "vector",
            "filters",
            "advanced",
            "legacy",
        },
        annotations={
            "title": "Advanced Search Tool History (Legacy)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def search_tool_history(
        query: str,
        tool_name: Optional[str] = None,
        user_email: Optional[str] = None,
        limit: int = 10,
        user_google_email: Optional[str] = None,
    ) -> str:
        """
        Search through historical tool responses using natural language.

        Args:
            query: Natural language search query (e.g., "errors in the last hour", "slow responses")
            tool_name: Filter by specific tool name
            user_email: Filter by user email
            limit: Maximum number of results to return

        Returns:
            JSON string with search results
        """
        try:
            filters = {}
            if tool_name:
                filters["tool_name"] = tool_name
            if user_email:
                filters["user_email"] = user_email

            results = await _search_manager.search_responses(query, filters, limit)
            return json.dumps({"results": results, "count": len(results)}, indent=2)
        except Exception as e:
            return f"Search failed: {str(e)}"

    @mcp.tool(
        name="get_tool_analytics",
        description="Get comprehensive analytics on tool usage, performance metrics, and patterns. By default returns a concise summary with sample point IDs for fetching specific results - set summary_only=false for detailed data.",
        tags={"qdrant", "analytics", "metrics", "performance", "usage", "legacy"},
        annotations={
            "title": "Tool Analytics Dashboard (Legacy)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_tool_analytics(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: str = "tool_name",
        summary_only: bool = True,
        user_google_email: Optional[str] = None,
    ) -> str:
        """
        Get analytics on tool usage and performance.

        Args:
            start_date: ISO format start date (e.g., "2024-01-01T00:00:00")
            end_date: ISO format end date
            group_by: Field to group by (tool_name, user_email)
            summary_only: If True, return concise summary (default). If False, return full detailed analytics

        Returns:
            JSON string with analytics data (summarized by default to reduce token usage)
        """
        try:
            from datetime import datetime

            start_dt = datetime.fromisoformat(start_date) if start_date else None
            end_dt = datetime.fromisoformat(end_date) if end_date else None

            analytics = await _search_manager.get_analytics(start_dt, end_dt, group_by)

            if summary_only and isinstance(analytics, dict) and "groups" in analytics:
                # Create a summarized version to reduce token usage
                summarized = {
                    "total_responses": analytics.get("total_responses", 0),
                    "group_by": analytics.get("group_by", group_by),
                    "collection_name": analytics.get("collection_name", "unknown"),
                    "generated_at": analytics.get("generated_at"),
                    "date_range": analytics.get("date_range", {}),
                    "summary": analytics.get("summary", {}),
                    "groups_summary": {},
                }

                # Summarize each group with only key metrics and sample point IDs
                for group_name, group_data in analytics.get("groups", {}).items():
                    # Get a sample of recent point IDs (limit to 5 most recent)
                    point_ids = group_data.get("point_ids", [])
                    sample_point_ids = (
                        point_ids[-5:] if len(point_ids) > 5 else point_ids
                    )

                    summarized["groups_summary"][group_name] = {
                        "count": group_data.get("count", 0),
                        "unique_users": group_data.get("unique_users", 0),
                        "unique_sessions": group_data.get("unique_sessions", 0),
                        "error_rate": round(group_data.get("error_rate", 0), 3),
                        "compression_rate": round(
                            group_data.get("compression_rate", 0), 3
                        ),
                        "avg_response_size": round(
                            group_data.get("avg_response_size", 0), 1
                        ),
                        "recent_activity": group_data.get("recent_activity", {}),
                        "latest_timestamp": group_data.get("latest_timestamp"),
                        "earliest_timestamp": group_data.get("earliest_timestamp"),
                        "sample_point_ids": sample_point_ids,
                        "total_point_ids": len(point_ids),
                    }

                summarized["note"] = (
                    "This is a summarized view with sample point IDs for fetching specific results. Set summary_only=false for full details including all point IDs, timestamps arrays, etc."
                )
                return json.dumps(summarized, indent=2)
            else:
                # Return full analytics (existing behavior)
                return json.dumps(analytics, indent=2)
        except Exception as e:
            return f"Analytics failed: {str(e)}"

    @mcp.tool(
        name="get_response_details",
        description="Retrieve full details and metadata of a specific stored tool response by its unique ID. LEGACY TOOL - Use 'fetch' tool instead for better formatting and structured output.",
        tags={"qdrant", "details", "response", "lookup", "metadata", "legacy"},
        annotations={
            "title": "Get Response Details (Legacy - Use 'fetch' instead)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_response_details(
        point_id: str, user_google_email: Optional[str] = None
    ) -> str:
        """
        Get full details of a stored response by point ID.

        LEGACY TOOL: Use the 'fetch' tool instead for better formatting and structured output.

        Args:
            point_id: Qdrant point ID (UUID) - same identifier used in 'fetch' tool

        Returns:
            JSON string with full response details (raw format)
        """
        try:
            details = await _search_manager.get_response_by_id(point_id)
            if details:
                return json.dumps(details, indent=2)
            else:
                return f"Response with point ID {point_id} not found"
        except Exception as e:
            return f"Failed to get response details: {str(e)}"

    @mcp.tool(
        name="cleanup_qdrant_data",
        description="Manually trigger cleanup of stale data older than the configured retention period. This removes old tool responses and maintains database performance. The retention period is controlled by the MCP_TOOL_RESPONSES_COLLECTION_CACHE_DAYS environment variable (default: 14 days).",
        tags={"qdrant", "cleanup", "maintenance", "database", "retention"},
        annotations={
            "title": "Qdrant Data Cleanup Tool",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def cleanup_qdrant_data(user_google_email: Optional[str] = None) -> str:
        """
        Manually trigger cleanup of stale Qdrant data.

        This tool removes tool responses older than the configured retention period
        (default: 14 days, configurable via MCP_TOOL_RESPONSES_COLLECTION_CACHE_DAYS).

        Args:
            user_google_email: User's Google email for access control

        Returns:
            JSON string with cleanup results and statistics
        """
        try:
            # Import storage manager
            from .storage import QdrantStorageManager

            # Ensure client manager is initialized
            if not _client_manager.is_initialized:
                await _client_manager.initialize()

            if not _client_manager.is_available:
                return json.dumps(
                    {
                        "status": "failed",
                        "error": "Qdrant client not available - database may not be running",
                        "retention_days": _client_manager.config.cache_retention_days,
                    },
                    indent=2,
                )

            # Create storage manager and run cleanup
            storage_manager = QdrantStorageManager(_client_manager)
            result = await storage_manager.cleanup_stale_data()

            # Format result for display
            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"❌ Manual cleanup failed: {e}")
            return json.dumps(
                {
                    "status": "error",
                    "error": str(e),
                    "retention_days": getattr(
                        _client_manager.config, "cache_retention_days", 14
                    ),
                },
                indent=2,
            )

