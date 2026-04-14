"""Basic search methods: search, search_async, colbert_search, query_by_symbol."""

import asyncio
import importlib
import inspect
from typing import Any, Dict, List, Optional

from adapters.module_wrapper.types import (
    ComponentName,
    Payload,
    QueryText,
    Symbol,
)
from config.enhanced_logging import setup_logger

logger = setup_logger()


def search(
    self,
    query: QueryText,
    limit: int = 5,
    score_threshold: float = 0.3,
    vector_name: Optional[str] = None,
) -> List[Payload]:
    """
    Search for components in the module.

    Args:
        query: Search query
        limit: Maximum number of results
        score_threshold: Minimum similarity score
        vector_name: Explicit named vector to search. When None,
            auto-detects: ``"components"`` for named-vector collections,
            omitted for single-vector collections.

    Returns:
        List of matching components with their paths
    """
    if not self._initialized:
        raise RuntimeError("ModuleWrapper not initialized")

    # In degraded mode, fall back to in-memory component lookup
    if not self._require_qdrant("search"):
        return self._direct_component_lookup(query)

    try:
        # Try direct lookup first for exact component name matches
        direct_results = self._direct_component_lookup(query)
        if direct_results:
            logger.info(f"Found {len(direct_results)} direct matches for '{query}'")
            return direct_results

        # Generate embedding for the query
        embedding_list = list(self.embedder.embed([query]))
        query_embedding = embedding_list[0] if embedding_list else None

        if query_embedding is None:
            logger.error(f"Failed to generate embedding for query: {query}")
            return []

        # Convert embedding to list format
        if hasattr(query_embedding, "tolist"):
            query_vector = query_embedding.tolist()
        else:
            query_vector = list(query_embedding)

        # Search in Qdrant — resolve named vector for RIC collections
        using = self._resolve_using(preferred="relationships", vector_name=vector_name)
        kwargs = {
            "collection_name": self.collection_name,
            "query": query_vector,
            "limit": limit,
            "score_threshold": score_threshold,
        }
        if using:
            kwargs["using"] = using
        search_results = self.client.query_points(**kwargs)

        # Get the actual points from the QueryResponse
        points = []
        if hasattr(search_results, "points"):
            points = search_results.points
            logger.info(f"Found {len(points)} points in search results")
        else:
            try:
                points = list(search_results)
            except Exception as e:
                logger.warning(f"Could not extract points from search results: {e}")
                return []

        # Process results
        return self._process_search_results(points)

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise


async def search_async(
    self,
    query: QueryText,
    limit: int = 5,
    score_threshold: float = 0.3,
    vector_name: Optional[str] = None,
) -> List[Payload]:
    """
    Search for components in the module asynchronously.

    Args:
        query: Search query
        limit: Maximum number of results
        score_threshold: Minimum similarity score
        vector_name: Explicit named vector to search. When None,
            auto-detects: ``"components"`` for named-vector collections,
            omitted for single-vector collections.

    Returns:
        List of matching components with their paths
    """
    if not self._initialized:
        raise RuntimeError("ModuleWrapper not initialized")

    try:
        # Try direct lookup first
        direct_results = self._direct_component_lookup(query)
        if direct_results:
            logger.info(
                f"Found {len(direct_results)} direct matches for '{query}' (async)"
            )
            return direct_results

        # Generate embedding for the query
        embedding_list = await asyncio.to_thread(
            lambda q: list(self.embedder.embed([q])), query
        )
        query_embedding = embedding_list[0] if embedding_list else None

        if query_embedding is None:
            logger.error(f"Failed to generate embedding for query: {query}")
            return []

        # Convert embedding to list format
        if hasattr(query_embedding, "tolist"):
            query_vector = query_embedding.tolist()
        else:
            query_vector = list(query_embedding)

        # Search in Qdrant — resolve named vector for RIC collections
        using = self._resolve_using(preferred="relationships", vector_name=vector_name)
        kwargs = {
            "collection_name": self.collection_name,
            "query": query_vector,
            "limit": limit,
            "score_threshold": score_threshold,
        }
        if using:
            kwargs["using"] = using
        search_results = await asyncio.to_thread(
            self.client.query_points,
            **kwargs,
        )

        # Get the actual points
        points = []
        if hasattr(search_results, "points"):
            points = search_results.points
        else:
            try:
                points = list(search_results)
            except Exception as e:
                logger.warning(
                    f"Could not extract points from async search results: {e}"
                )
                return []

        return self._process_search_results(points)

    except Exception as e:
        logger.error(f"Async search failed: {e}", exc_info=True)
        raise


def colbert_search(
    self, query: QueryText, limit: int = 5, score_threshold: float = 0.3
) -> List[Payload]:
    """
    Search for components using ColBERT multi-vector embeddings.

    Args:
        query: Natural language search query
        limit: Maximum number of results
        score_threshold: Minimum similarity score

    Returns:
        List of matching components with their paths and scores
    """
    if not self._initialized:
        raise RuntimeError("ModuleWrapper not initialized")

    if not self._require_qdrant("colbert_search"):
        return self._direct_component_lookup(query)

    if not self.enable_colbert or not getattr(self, "_colbert_initialized", False):
        logger.warning("ColBERT not enabled, falling back to standard search")
        return self.search(query, limit, score_threshold)

    try:
        logger.info(f"ColBERT search for: '{query}'")

        # Generate ColBERT query embedding
        query_embedding_result = list(self.colbert_embedder.query_embed([query]))
        if not query_embedding_result:
            logger.error(f"Failed to generate ColBERT query embedding for: {query}")
            return []

        query_multi_vector = query_embedding_result[0]

        # Convert to list format
        if hasattr(query_multi_vector, "tolist"):
            query_vector = query_multi_vector.tolist()
        else:
            query_vector = [list(v) for v in query_multi_vector]

        # Search using ColBERT multi-vector with MaxSim
        search_results = self.client.query_points(
            collection_name=self.colbert_collection_name,
            query=query_vector,
            using="colbert",
            limit=limit,
            score_threshold=score_threshold,
        )

        # Extract points from results
        points = []
        if hasattr(search_results, "points"):
            points = search_results.points
            logger.info(f"ColBERT search found {len(points)} results")

        # Process results
        results = []
        for result in points:
            try:
                score = float(getattr(result, "score", 0.0))
                payload = getattr(result, "payload", {})

                component_path = payload.get("full_path") or payload.get(
                    "name", "unknown"
                )

                results.append(
                    {
                        "name": payload.get("name"),
                        "path": component_path,
                        "type": payload.get("type"),
                        "score": score,
                        "docstring": payload.get("docstring", ""),
                        "component": self._get_component_from_path(component_path),
                        "embedding_type": "colbert",
                    }
                )

                logger.info(f"  - {payload.get('name')} (score: {score:.4f})")

            except Exception as e:
                logger.warning(f"Error processing ColBERT result: {e}")
                continue

        return results

    except Exception as e:
        logger.error(f"ColBERT search failed: {e}", exc_info=True)
        logger.info("Falling back to standard search")
        return self.search(query, limit, score_threshold)


def _direct_component_lookup(self, component_name: ComponentName) -> List[Payload]:
    """
    Direct lookup for components by name.

    Args:
        component_name: Name of the component to look up

    Returns:
        List of matching components
    """
    results = []

    # Check all components for exact name match
    for path, component in self.components.items():
        if component.name == component_name:
            logger.info(f"Direct match found: {path}")
            if component.obj is not None:
                results.append(
                    {
                        "score": 1.0,
                        "name": component.name,
                        "path": path,
                        "type": component.component_type,
                        "docstring": component.docstring,
                        "component": component.obj,
                    }
                )

    # If no exact matches, try case-insensitive match
    if not results:
        for path, component in self.components.items():
            if component.name.lower() == component_name.lower():
                logger.info(f"Case-insensitive match found: {path}")
                if component.obj is not None:
                    results.append(
                        {
                            "score": 0.9,
                            "name": component.name,
                            "path": path,
                            "type": component.component_type,
                            "docstring": component.docstring,
                            "component": component.obj,
                        }
                    )

    # Check for components in widgets module
    if not results and hasattr(self.module, "widgets"):
        widgets_path = f"{self.module_name}.widgets.{component_name}"
        component = self.components.get(widgets_path)
        if component and component.obj is not None:
            logger.info(f"Found component in widgets module: {widgets_path}")
            results.append(
                {
                    "score": 1.0,
                    "name": component.name,
                    "path": widgets_path,
                    "type": component.component_type,
                    "docstring": component.docstring,
                    "component": component.obj,
                }
            )

    return results


def _process_search_results(self, points: List[Any]) -> List[Payload]:
    """
    Process Qdrant search results into a standard format.

    Args:
        points: List of Qdrant ScoredPoint objects

    Returns:
        List of result dictionaries
    """
    results = []

    for result in points:
        try:
            score = float(getattr(result, "score", 0.9))
            payload = getattr(result, "payload", {})

        except (AttributeError, ValueError, TypeError) as e:
            logger.warning(f"Error processing ScoredPoint object: {e}")
            if isinstance(result, tuple):
                score_value = None
                payload_value = None
                for item in result:
                    if isinstance(item, (int, float)):
                        score_value = item
                    elif isinstance(item, dict):
                        payload_value = item
                score = float(score_value) if score_value is not None else 0.9
                payload = payload_value if payload_value is not None else {}
            else:
                score = 0.9
                payload = {}

        # Handle different payload structures
        if isinstance(payload, dict):
            module_path = payload.get("module_path")
            name = payload.get("name")

            canonical_path = None
            if module_path and name:
                canonical_path = f"{module_path}.{name}"

            path = canonical_path or payload.get("full_path")
            type_info = payload.get("type")
            docstring = payload.get("docstring")
        elif isinstance(payload, list) and len(payload) > 0:
            path = str(payload[0]) if len(payload) > 0 else ""
            name = str(payload[1]) if len(payload) > 1 else ""
            type_info = str(payload[2]) if len(payload) > 2 else ""
            docstring = str(payload[3]) if len(payload) > 3 else ""
            module_path = None
        else:
            path = str(payload) if payload else ""
            name = ""
            type_info = ""
            docstring = ""
            module_path = None

        # Get the actual component
        full_path = payload.get("full_path") if isinstance(payload, dict) else None
        component_obj = None

        if full_path:
            component = self.components.get(full_path)
            if component and component.obj is not None:
                component_obj = component.obj

        if component_obj is None and path:
            component = self.components.get(path)
            if component and component.obj is not None:
                component_obj = component.obj

        if component_obj is None and full_path:
            component_obj = self.get_component_by_path(full_path)

        results.append(
            {
                "score": score,
                "name": name,
                "path": path,
                "full_path": full_path,
                "module_path": module_path if isinstance(payload, dict) else None,
                "type": type_info,
                "docstring": docstring,
                "component": component_obj,
            }
        )

    return results


def _get_component_from_path(self, path: str) -> Any:
    """Get component object from its path."""
    if path in self.components:
        component = self.components[path]
        return component.obj if hasattr(component, "obj") else None
    return None


def query_by_symbol(
    self,
    symbol: Symbol,
    include_relationships: bool = True,
    limit: int = 1,
) -> List[Payload]:
    """
    Query components by their DSL symbol.

    Args:
        symbol: The DSL symbol (e.g., 'delta' for DecoratedText)
        include_relationships: Whether to include relationship info
        limit: Maximum number of results

    Returns:
        List of matching components
    """
    # In degraded mode, resolve symbol from in-memory mapping
    if not self._require_qdrant("query_by_symbol"):
        component_name = self.reverse_symbol_mapping.get(symbol)
        if component_name:
            return self._direct_component_lookup(component_name)
        return []

    from adapters.module_wrapper.qdrant_mixin import _get_qdrant_imports

    try:
        _, qdrant_models = _get_qdrant_imports()

        # Search by symbol field
        search_results = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=qdrant_models["Filter"](
                must=[
                    qdrant_models["FieldCondition"](
                        key="symbol",
                        match=qdrant_models["MatchValue"](value=symbol),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        points, _ = search_results

        results = []
        for point in points:
            payload = point.payload
            if not payload:
                continue

            result = {
                "name": payload.get("name"),
                "path": payload.get("full_path"),
                "type": payload.get("type"),
                "symbol": symbol,
                "docstring": payload.get("docstring", ""),
            }

            # Include relationships if requested
            if include_relationships and hasattr(self, "relationships"):
                name = payload.get("name")
                if name and name in self.relationships:
                    result["children"] = self.relationships[name]

            results.append(result)

        return results

    except Exception as e:
        logger.warning(f"Symbol query failed: {e}")
        return []
