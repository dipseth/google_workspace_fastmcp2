"""
DSL Executor — Runs built qdrant_client.models queries against Qdrant.

Takes objects produced by QueryBuilder and executes them via QdrantClientManager.
Supports multiple query modes:
  - Semantic + filter: query_text provided → embed + query_points with filter
  - Filter-only: no query_text → scroll with filter
  - Advanced query: query_dsl builds a query object (RecommendQuery, DiscoverQuery,
    FusionQuery, etc.) passed directly to query_points
  - Prefetch: prefetch_dsl builds Prefetch objects for multi-stage queries

Usage:
    from middleware.qdrant_core.dsl_executor import SearchV2Executor

    executor = SearchV2Executor(client_manager, query_builder)

    # Filter + semantic search
    response = await executor.execute_dsl(
        dsl='ƒ{must=[ʄ{key="tool_name", match=☆{value="search"}}]}',
        query_text="gmail messages",
        collection="mcp_tool_responses",
    )

    # Advanced: RecommendQuery with filter
    response = await executor.execute_dsl(
        dsl='ƒ{must=[ʄ{key="service", match=☆{value="gmail"}}]}',
        query_dsl='RecommendQuery{recommend=RecommendInput{positive=[1, 2], strategy=RecommendStrategy{...}}}',
        collection="mcp_tool_responses",
    )
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from middleware.qdrant_core.dsl_types import (
    SearchV2Response,
    SearchV2ResultItem,
)

if TYPE_CHECKING:
    from middleware.qdrant_core.client import QdrantClientManager
    from middleware.qdrant_core.dsl_query_builder import QueryBuilder

logger = logging.getLogger(__name__)


class SearchV2Executor:
    """Executes DSL-built queries against Qdrant."""

    def __init__(
        self,
        client_manager: "QdrantClientManager",
        query_builder: "QueryBuilder",
    ):
        self.client_manager = client_manager
        self.query_builder = query_builder

    async def execute_dsl(
        self,
        dsl: str,
        collection: str = "mcp_tool_responses",
        query_text: Optional[str] = None,
        query_dsl: Optional[str] = None,
        prefetch_dsl: Optional[str] = None,
        limit: int = 10,
        score_threshold: float = 0.3,
        dry_run: bool = False,
    ) -> SearchV2Response:
        """Parse DSL, build filter, execute query, return results.

        Query mode is determined by which params are provided:
        - query_dsl → builds a query object (RecommendQuery, DiscoverQuery,
          FusionQuery, etc.) and passes to query_points as `query`
        - query_text → embeds text to vector and passes to query_points as `query`
        - neither → filter-only scroll (no vectors needed)

        prefetch_dsl can be combined with any mode to add multi-stage Prefetch.

        Args:
            dsl: Parameterized DSL filter string
            collection: Qdrant collection to search
            query_text: Optional text for semantic search (embeds to vector)
            query_dsl: Optional DSL for query object (RecommendQuery, FusionQuery, etc.)
            prefetch_dsl: Optional DSL for Prefetch object(s) for multi-stage queries
            limit: Maximum results
            score_threshold: Minimum similarity score (semantic mode only)
            dry_run: If True, parse and build but don't execute

        Returns:
            SearchV2Response with results or error
        """
        start = time.monotonic()
        all_dsl_inputs = [dsl]

        # 1. Parse and build the filter DSL
        parse_result = self.query_builder.parse_dsl(dsl)
        if not parse_result.is_valid:
            return SearchV2Response(
                dsl_input=dsl,
                error=f"Invalid DSL: {'; '.join(parse_result.issues)}",
                processing_time_ms=_elapsed_ms(start),
            )

        if not parse_result.root_nodes:
            return SearchV2Response(
                dsl_input=dsl,
                error="DSL parsed but produced no root nodes",
                processing_time_ms=_elapsed_ms(start),
            )

        try:
            qdrant_filter = self.query_builder.build(parse_result.root_nodes[0])
        except ValueError as e:
            return SearchV2Response(
                dsl_input=dsl,
                error=f"Build error: {e}",
                processing_time_ms=_elapsed_ms(start),
            )

        filter_repr = repr(qdrant_filter)

        # 2. Parse and build query_dsl (if provided)
        query_object = None
        if query_dsl:
            all_dsl_inputs.append(f"query_dsl: {query_dsl}")
            try:
                query_object = self.query_builder.parse_and_build(query_dsl)
            except ValueError as e:
                return SearchV2Response(
                    dsl_input=" | ".join(all_dsl_inputs),
                    error=f"query_dsl build error: {e}",
                    built_filter_repr=filter_repr,
                    processing_time_ms=_elapsed_ms(start),
                )

        # 3. Parse and build prefetch_dsl (if provided)
        prefetch_objects = None
        if prefetch_dsl:
            all_dsl_inputs.append(f"prefetch_dsl: {prefetch_dsl}")
            try:
                prefetch_result = self.query_builder.parse_dsl(prefetch_dsl)
                if not prefetch_result.is_valid:
                    return SearchV2Response(
                        dsl_input=" | ".join(all_dsl_inputs),
                        error=f"prefetch_dsl parse error: {'; '.join(prefetch_result.issues)}",
                        built_filter_repr=filter_repr,
                        processing_time_ms=_elapsed_ms(start),
                    )
                # Build all root nodes (might be multiple Prefetch objects)
                prefetch_objects = self.query_builder.build_all(
                    prefetch_result.root_nodes
                )
            except ValueError as e:
                return SearchV2Response(
                    dsl_input=" | ".join(all_dsl_inputs),
                    error=f"prefetch_dsl build error: {e}",
                    built_filter_repr=filter_repr,
                    processing_time_ms=_elapsed_ms(start),
                )

        combined_dsl = " | ".join(all_dsl_inputs)

        # 4. Dry run — return early with built objects info
        if dry_run:
            dry_repr_parts = [f"filter: {filter_repr}"]
            if query_object:
                dry_repr_parts.append(f"query: {repr(query_object)}")
            if prefetch_objects:
                dry_repr_parts.append(f"prefetch: {repr(prefetch_objects)}")
            return SearchV2Response(
                dsl_input=combined_dsl,
                query_type="dry_run",
                collection_name=collection,
                built_filter_repr=" | ".join(dry_repr_parts),
                processing_time_ms=_elapsed_ms(start),
            )

        # 5. Ensure client is ready
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()

        if not self.client_manager.is_available:
            return SearchV2Response(
                dsl_input=combined_dsl,
                error="Qdrant client not available",
                processing_time_ms=_elapsed_ms(start),
            )

        # 6. Execute query — mode determined by what's provided
        try:
            if query_dsl and query_object:
                # Advanced query mode: pass built query object directly
                results, query_type = await self._execute_query_object(
                    query_object,
                    qdrant_filter,
                    collection,
                    limit,
                    score_threshold,
                    prefetch_objects,
                )
            elif query_text:
                results, query_type = await self._execute_semantic(
                    qdrant_filter,
                    query_text,
                    collection,
                    limit,
                    score_threshold,
                    prefetch_objects,
                )
            elif prefetch_objects:
                # Prefetch-only mode (no query object or text — use None query
                # with prefetch, common with FusionQuery as query_dsl)
                results, query_type = await self._execute_query_object(
                    None,
                    qdrant_filter,
                    collection,
                    limit,
                    score_threshold,
                    prefetch_objects,
                )
            else:
                results, query_type = await self._execute_scroll(
                    qdrant_filter, collection, limit
                )
        except Exception as e:
            return SearchV2Response(
                dsl_input=combined_dsl,
                error=f"Execution error: {e}",
                built_filter_repr=filter_repr,
                processing_time_ms=_elapsed_ms(start),
            )

        # 7. Format response
        items = self._format_results(results, query_type)

        return SearchV2Response(
            results=items,
            dsl_input=combined_dsl,
            query_type=query_type,
            collection_name=collection,
            total_results=len(items),
            processing_time_ms=_elapsed_ms(start),
            built_filter_repr=filter_repr,
        )

    async def execute_semantic_only(
        self,
        query_text: str,
        collection: str = "mcp_tool_responses",
        limit: int = 10,
        score_threshold: float = 0.3,
        qdrant_filter: Any = None,
    ) -> SearchV2Response:
        """Execute a pure semantic search (no DSL parsing).

        Used by the natural language bridge tool when no structured
        filters are detected.
        """
        start = time.monotonic()

        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()

        if not self.client_manager.is_available:
            return SearchV2Response(
                dsl_input="",
                error="Qdrant client not available",
                processing_time_ms=_elapsed_ms(start),
            )

        try:
            results, query_type = await self._execute_semantic(
                qdrant_filter, query_text, collection, limit, score_threshold
            )
        except Exception as e:
            return SearchV2Response(
                dsl_input="",
                error=f"Semantic search error: {e}",
                processing_time_ms=_elapsed_ms(start),
            )

        items = self._format_results(results, query_type)

        return SearchV2Response(
            results=items,
            dsl_input=f"semantic: {query_text}",
            query_type=query_type,
            collection_name=collection,
            total_results=len(items),
            processing_time_ms=_elapsed_ms(start),
        )

    # -------------------------------------------------------------------------
    # Internal execution methods
    # -------------------------------------------------------------------------

    async def _execute_query_object(
        self,
        query_object: Any,
        qdrant_filter: Any,
        collection: str,
        limit: int,
        score_threshold: float,
        prefetch: Optional[List[Any]] = None,
    ) -> tuple:
        """Run query_points with a pre-built query object (RecommendQuery, etc.)."""
        kwargs: Dict[str, Any] = {
            "collection_name": collection,
            "query_filter": qdrant_filter,
            "limit": limit,
            "with_payload": True,
        }
        if query_object is not None:
            kwargs["query"] = query_object
        if score_threshold:
            kwargs["score_threshold"] = score_threshold
        if prefetch:
            kwargs["prefetch"] = prefetch if len(prefetch) > 1 else prefetch[0]

        response = await asyncio.to_thread(
            self.client_manager.client.query_points,
            **kwargs,
        )
        return response.points, "query_points_advanced"

    async def _execute_semantic(
        self,
        qdrant_filter: Any,
        query_text: str,
        collection: str,
        limit: int,
        score_threshold: float,
        prefetch: Optional[List[Any]] = None,
    ) -> tuple:
        """Embed query text and run query_points with optional filter."""
        embedding = await self._embed(query_text)
        if embedding is None:
            raise RuntimeError("Failed to generate embedding for query text")

        kwargs: Dict[str, Any] = {
            "collection_name": collection,
            "query": embedding.tolist(),
            "query_filter": qdrant_filter,
            "limit": limit,
            "score_threshold": score_threshold,
            "with_payload": True,
        }
        if prefetch:
            kwargs["prefetch"] = prefetch if len(prefetch) > 1 else prefetch[0]

        response = await asyncio.to_thread(
            self.client_manager.client.query_points,
            **kwargs,
        )
        return response.points, "query_points"

    async def _execute_scroll(
        self,
        qdrant_filter: Any,
        collection: str,
        limit: int,
    ) -> tuple:
        """Run filter-only scroll (no vectors needed)."""
        points, _next_offset = await asyncio.to_thread(
            self.client_manager.client.scroll,
            collection_name=collection,
            scroll_filter=qdrant_filter,
            limit=limit,
            with_payload=True,
        )
        return points, "scroll"

    async def _embed(self, text: str):
        """Generate embedding using client_manager's embedder."""
        if not self.client_manager.embedder:
            await self.client_manager._ensure_model_loaded()

        embedding_list = await asyncio.to_thread(
            lambda: list(self.client_manager.embedder.embed([text]))
        )
        return embedding_list[0] if embedding_list else None

    # -------------------------------------------------------------------------
    # Result formatting
    # -------------------------------------------------------------------------

    @staticmethod
    def _format_results(points: List[Any], query_type: str) -> List[SearchV2ResultItem]:
        """Convert Qdrant ScoredPoint/Record objects to response items."""
        items = []
        for point in points:
            payload = getattr(point, "payload", {}) or {}
            score = getattr(point, "score", None)
            items.append(
                SearchV2ResultItem(
                    id=str(point.id),
                    score=score,
                    payload=payload,
                    tool_name=payload.get("tool_name"),
                    user_email=payload.get("user_email"),
                    timestamp=payload.get("timestamp"),
                )
            )
        return items


def _elapsed_ms(start: float) -> float:
    """Calculate elapsed milliseconds since start."""
    return round((time.monotonic() - start) * 1000, 2)
