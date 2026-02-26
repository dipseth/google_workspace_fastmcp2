"""
Search Functionality Mixin

Provides search capabilities including standard search, ColBERT search,
text index search, DSL-aware search, and V7 multi-vector search
for the ModuleWrapper system.

This is the canonical location for all search methods in the ModuleWrapper.

Search Strategy Overview:
    EMBEDDING HELPERS (Private)
        _embed_with_colbert(text, token_ratio)
        _embed_with_minilm(text)
        _get_colbert_embedder()
        _get_minilm_embedder()

    SIMPLE SEARCHES (Single Vector)
        search()              - MiniLM semantic search
        search_async()        - Async MiniLM
        colbert_search()      - ColBERT multi-vector
        query_by_symbol()     - Exact symbol match

    TEXT INDEX SEARCHES
        search_by_text()              - Field text search
        search_by_relationship_text() - Relationship search
        search_within_module()        - Module-scoped

    DSL-AWARE SEARCHES
        extract_dsl_from_text()  - DSL extraction utility
        search_by_dsl()          - DSL + ColBERT
        search_by_dsl_hybrid()   - DSL + multi-vector

    V7 MULTI-VECTOR SEARCHES
        search_v7()         - Named vector search
        search_v7_hybrid()  - 3-vector with RRF fusion

    RESULT PROCESSING
        _process_search_results()
        _merge_results_rrf()
"""

import asyncio
import importlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from adapters.module_wrapper.types import (
    # Constants
    COLBERT_DIM as _COLBERT_DIM,
)
from adapters.module_wrapper.types import (
    RELATIONSHIPS_DIM as _RELATIONSHIPS_DIM,
)
from adapters.module_wrapper.types import (
    ComponentName,
    ComponentPath,
    EmbeddingVector,
    MultiVector,
    # Type Aliases
    Payload,
    QdrantFilter,
    QueryText,
    RelationshipDict,
    ReverseSymbolMapping,
    # Dataclasses
    SearchResult,
    Symbol,
    SymbolMapping,
)

logger = logging.getLogger(__name__)

# Re-export constants for backwards compatibility
COLBERT_DIM = _COLBERT_DIM  # ColBERT embedding dimension
RELATIONSHIPS_DIM = _RELATIONSHIPS_DIM  # MiniLM embedding dimension for relationships


# =============================================================================
# SEARCH MIXIN
# =============================================================================


class SearchMixin:
    """
    Mixin providing search functionality.

    Expects the following attributes on self:
    - _initialized: bool
    - client: Qdrant client
    - embedder: Embedding model
    - collection_name: str
    - components: Dict[str, ModuleComponent]
    - module: The wrapped module
    - module_name, _module_name: Module name properties
    - enable_colbert, _colbert_initialized: bool
    - colbert_embedder: ColBERT embedding model
    - colbert_collection_name: str
    - symbol_mapping: Dict[str, str] (component → symbol)
    - reverse_symbol_mapping: Dict[str, str] (symbol → component)
    - relationships: Dict[str, List[str]]
    """

    # --- Mixin dependency contract ---
    _MIXIN_PROVIDES = frozenset(
        {
            "search",
            "search_async",
            "colbert_search",
            "search_v7",
            "search_v7_hybrid",
            "get_component_info",
            "list_components",
            "get_component_source",
            "create_card_component",
            "query_by_symbol",
            "search_by_text",
            "search_by_dsl",
            "extract_dsl_from_text",
        }
    )
    _MIXIN_REQUIRES = frozenset(
        {
            "client",
            "embedder",
            "collection_name",
            "components",
            "module",
            "symbol_mapping",
            "reverse_symbol_mapping",
            "relationships",
        }
    )
    _MIXIN_INIT_ORDER = 40

    # =========================================================================
    # EMBEDDING HELPERS (Private)
    # =========================================================================

    def _get_colbert_embedder(self):
        """
        Get ColBERT embedder for search operations.

        Tries multiple sources: pipeline mixin, core attribute, or creates new.

        Returns:
            ColBERT embedder instance or None if unavailable
        """
        # Try pipeline mixin's embedder
        if hasattr(self, "_colbert_embedder") and self._colbert_embedder is not None:
            return self._colbert_embedder

        # Try core attribute
        if hasattr(self, "colbert_embedder") and self.colbert_embedder is not None:
            return self.colbert_embedder

        # Create new embedder if needed
        try:
            from fastembed import LateInteractionTextEmbedding

            logger.info("Initializing ColBERT embedder for search...")
            embedder = LateInteractionTextEmbedding(model_name="colbert-ir/colbertv2.0")

            # Cache it
            if hasattr(self, "_colbert_embedder"):
                self._colbert_embedder = embedder
            else:
                self.colbert_embedder = embedder

            return embedder
        except Exception as e:
            logger.error(f"Failed to initialize ColBERT embedder: {e}")
            return None

    def _get_minilm_embedder(self):
        """
        Get MiniLM embedder for search operations.

        Returns:
            MiniLM embedder instance or None if unavailable
        """
        # Try core attribute
        if hasattr(self, "embedder") and self.embedder is not None:
            return self.embedder

        # Create new embedder if needed
        try:
            from fastembed import TextEmbedding

            logger.info("Initializing MiniLM embedder for search...")
            embedder = TextEmbedding(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
            self.embedder = embedder
            return embedder
        except Exception as e:
            logger.error(f"Failed to initialize MiniLM embedder: {e}")
            return None

    def _embed_with_colbert(
        self, text: QueryText, token_ratio: float = 1.0
    ) -> Optional[MultiVector]:
        """
        Generate ColBERT multi-vector embedding for text.

        Args:
            text: Text to embed
            token_ratio: Fraction of ColBERT tokens to use (0.0-1.0).
                         Lower values = faster search but potentially less accurate.

        Returns:
            List of token embedding vectors, or None if embedding fails
        """
        embedder = self._get_colbert_embedder()
        if not embedder:
            return None

        try:
            vectors_raw = list(embedder.query_embed(text))[0]
            vectors = [vec.tolist() for vec in vectors_raw]

            # Apply token truncation if requested
            if token_ratio < 1.0:
                cutoff = max(1, int(len(vectors) * token_ratio))
                vectors = vectors[:cutoff]
                logger.debug(f"Truncated to {cutoff}/{len(vectors_raw)} tokens")

            return vectors
        except Exception as e:
            logger.error(f"ColBERT embedding failed: {e}")
            return None

    def _embed_with_minilm(self, text: QueryText) -> Optional[EmbeddingVector]:
        """
        Generate MiniLM single-vector embedding for text.

        Args:
            text: Text to embed

        Returns:
            384-dimensional embedding vector, or None if embedding fails
        """
        embedder = self._get_minilm_embedder()
        if not embedder:
            return None

        try:
            embedding_list = list(embedder.embed([text]))
            if not embedding_list:
                return None

            embedding = embedding_list[0]
            if hasattr(embedding, "tolist"):
                return embedding.tolist()
            return list(embedding)
        except Exception as e:
            logger.error(f"MiniLM embedding failed: {e}")
            return None

    # =========================================================================
    # SIMPLE SEARCHES (Single Vector)
    # =========================================================================

    def search(
        self, query: QueryText, limit: int = 5, score_threshold: float = 0.3
    ) -> List[Payload]:
        """
        Search for components in the module.

        Args:
            query: Search query
            limit: Maximum number of results
            score_threshold: Minimum similarity score

        Returns:
            List of matching components with their paths
        """
        if not self._initialized:
            raise RuntimeError("ModuleWrapper not initialized")

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

            # Search in Qdrant
            search_results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
            )

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
        self, query: QueryText, limit: int = 5, score_threshold: float = 0.3
    ) -> List[Payload]:
        """
        Search for components in the module asynchronously.

        Args:
            query: Search query
            limit: Maximum number of results
            score_threshold: Minimum similarity score

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

            # Search in Qdrant
            search_results = await asyncio.to_thread(
                self.client.query_points,
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
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

    def get_component_by_path(self, path: str) -> Optional[Any]:
        """
        Get a component by its path.

        Args:
            path: Path to the component (e.g., "module.submodule.Class")

        Returns:
            The component if found, None otherwise
        """
        # Check for template paths
        if ".templates." in path or ".patterns." in path:
            return self._get_template_component(path)

        # Check if path is in components
        component = self.components.get(path)
        if component and component.obj is not None:
            return component.obj

        # Try to resolve path
        try:
            parts = path.split(".")

            # Normalize paths
            if parts and parts[0] == self.module_name:
                parts = parts[1:]

            if (
                self._module_name
                and parts
                and self._module_name.startswith(self.module_name + ".")
            ):
                subparts = self._module_name.split(".")[1:]
                if parts[: len(subparts)] == subparts:
                    parts = parts[len(subparts) :]

            # Start with the module
            obj = self.module

            # Traverse the path
            for part in parts:
                try:
                    obj = getattr(obj, part)
                except AttributeError:
                    module_candidate = f"{getattr(obj, '__name__', '')}.{part}".lstrip(
                        "."
                    )
                    try:
                        obj = importlib.import_module(module_candidate)
                    except (ImportError, ModuleNotFoundError):
                        return None

            return obj

        except Exception as e:
            logger.warning(f"Could not resolve path {path}: {e}")
            return None

    def _get_template_component(self, path: str) -> Optional[Any]:
        """
        Get a template or pattern component by path.

        Args:
            path: Template path like "card_framework.templates.my_template"

        Returns:
            The template component if found
        """
        # Extract template name from path
        parts = path.split(".")
        template_name = parts[-1] if parts else None

        if not template_name:
            return None

        # Try to find in local templates
        try:
            if hasattr(self.module, "templates"):
                templates = getattr(self.module, "templates")
                if hasattr(templates, template_name):
                    return getattr(templates, template_name)

            if hasattr(self.module, "patterns"):
                patterns = getattr(self.module, "patterns")
                if hasattr(patterns, template_name):
                    return getattr(patterns, template_name)
        except Exception as e:
            logger.debug(f"Error getting template component: {e}")

        return None

    def get_component_info(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a component.

        Args:
            path: Path to the component

        Returns:
            Component information dict or None
        """
        component = self.components.get(path)
        if component:
            return component.to_dict()
        return None

    def list_components(self, component_type: Optional[str] = None) -> List[str]:
        """
        List all components, optionally filtered by type.

        Args:
            component_type: Filter by type ('class', 'function', etc.)

        Returns:
            List of component paths
        """
        if component_type:
            return [
                path
                for path, comp in self.components.items()
                if comp.component_type == component_type
            ]
        return list(self.components.keys())

    def get_component_source(self, path: str) -> Optional[str]:
        """
        Get the source code of a component.

        Args:
            path: Path to the component

        Returns:
            Source code or None
        """
        component = self.components.get(path)
        if component:
            return component.source
        return None

    def create_card_component(self, card_class, params):
        """
        Helper method to create a card component with proper error handling.

        Args:
            card_class: The card class to instantiate
            params: Parameters to pass to the constructor

        Returns:
            The created card component or None if creation failed
        """
        import inspect

        if card_class is None:
            logger.warning("Cannot create card: card_class is None")
            return None

        try:
            if not callable(card_class):
                logger.warning(f"Card class {card_class} is not callable")
                return None

            try:
                if inspect.isclass(card_class):
                    sig = inspect.signature(card_class.__init__)
                else:
                    sig = inspect.signature(card_class)

                valid_params = {}
                for param_name, param in sig.parameters.items():
                    if param_name in params and param_name != "self":
                        valid_params[param_name] = params[param_name]

                component = card_class(**valid_params)
                logger.info(
                    f"Successfully created card component: {type(component).__name__}"
                )
                return component

            except (ValueError, TypeError) as e:
                logger.warning(f"Error getting signature for {card_class}: {e}")
                try:
                    component = card_class(**params)
                    logger.info(
                        f"Created card component with direct instantiation: {type(component).__name__}"
                    )
                    return component
                except Exception as e2:
                    logger.warning(f"Direct instantiation failed: {e2}")
                    return None

        except Exception as e:
            logger.warning(f"Failed to create card component: {e}")
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
            symbol: The DSL symbol (e.g., 'δ' for DecoratedText)
            include_relationships: Whether to include relationship info
            limit: Maximum number of results

        Returns:
            List of matching components
        """
        from .qdrant_mixin import _get_qdrant_imports

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

    # =========================================================================
    # TEXT INDEX SEARCHES
    # =========================================================================

    def search_by_text(
        self,
        field: str,
        query: QueryText,
        limit: int = 10,
        is_phrase: bool = False,
    ) -> List[Payload]:
        """
        Search collection using Qdrant text index.

        Args:
            field: Field to search on (e.g., "name", "docstring")
            query: Search query
            limit: Max results
            is_phrase: If True, treat query as exact phrase

        Returns:
            List of matching points with payloads
        """
        if not self.client:
            logger.warning("Cannot search: Qdrant client not available")
            return []

        try:
            from qdrant_client import models

            # Wrap in quotes for phrase search
            search_text = f'"{query}"' if is_phrase else query

            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key=field,
                            match=models.MatchText(text=search_text),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
            )

            # Convert to standard result format
            return [
                {
                    "id": point.id,
                    "name": point.payload.get("name"),
                    "type": point.payload.get("type"),
                    "full_path": point.payload.get("full_path"),
                    "symbol": point.payload.get("symbol"),
                    "docstring": point.payload.get("docstring", "")[:200],
                    "score": 1.0,  # Text matches don't have scores
                }
                for point in results
            ]

        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return []

    def search_by_relationship_text(
        self,
        query: QueryText,
        limit: int = 10,
    ) -> List[Payload]:
        """
        Search components by their relationship descriptions.

        Uses the stemmed text index for fuzzy NL matching.

        Args:
            query: NL query like "button with icon"
            limit: Max results

        Returns:
            List of matching component points
        """
        return self.search_by_text(
            field="relationships.nl_descriptions",
            query=query,
            limit=limit,
        )

    def search_within_module(
        self,
        module_name: str,
        text_query: str,
        field: str = "name",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search within a specific module.

        Args:
            module_name: Module to filter by (e.g., "card_framework", "gmail")
            text_query: Text to search for
            field: Field to search in
            limit: Max results

        Returns:
            List of matching points
        """
        if not self.client:
            logger.warning("Cannot search: Qdrant client not available")
            return []

        try:
            from qdrant_client import models

            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="module",
                            match=models.MatchValue(value=module_name),
                        ),
                        models.FieldCondition(
                            key=field,
                            match=models.MatchText(text=text_query),
                        ),
                    ]
                ),
                limit=limit,
                with_payload=True,
            )

            return [
                {
                    "id": point.id,
                    "name": point.payload.get("name"),
                    "type": point.payload.get("type"),
                    "full_path": point.payload.get("full_path"),
                    "symbol": point.payload.get("symbol"),
                    "docstring": point.payload.get("docstring", "")[:200],
                    "score": 1.0,
                }
                for point in results
            ]

        except Exception as e:
            logger.error(f"Module-scoped search failed: {e}")
            return []

    # =========================================================================
    # DSL-AWARE SEARCHES
    # =========================================================================

    def extract_dsl_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extract DSL notation from arbitrary text.

        Finds DSL patterns like "§[δ, Ƀ[ᵬ×2]]" within natural language text
        and separates the DSL from the description.

        Args:
            text: Any text that may contain DSL notation

        Returns:
            Dict with:
                - dsl: Extracted DSL string (or None if not found)
                - description: Remaining text after DSL extraction
                - has_dsl: Whether DSL was found
                - components: Parsed component info (if DSL found)

        Examples:
            >>> extract_dsl_from_text("§[δ, Ƀ[ᵬ×2]] Build a status card")
            {"dsl": "§[δ, Ƀ[ᵬ×2]]", "description": "Build a status card", ...}

            >>> extract_dsl_from_text("Build a card with buttons")
            {"dsl": None, "description": "Build a card with buttons", "has_dsl": False}
        """
        # Get all known symbols for pattern matching
        all_symbols = set()
        if hasattr(self, "symbol_mapping"):
            all_symbols.update(self.symbol_mapping.values())
        if hasattr(self, "reverse_symbol_mapping"):
            all_symbols.update(self.reverse_symbol_mapping.keys())

        text = text.strip()
        if not text:
            return {
                "dsl": None,
                "description": text,
                "has_dsl": False,
                "inline_symbols": [],
                "components": [],
                "component_paths": [],
                "is_valid": False,
            }

        # Check if text starts with a known symbol
        first_char = text[0] if text else ""
        if first_char not in all_symbols:
            # No DSL at start - check for inline symbols
            inline_symbols = []
            for symbol in all_symbols:
                if symbol in text:
                    comp_name = (
                        self.reverse_symbol_mapping.get(symbol)
                        if hasattr(self, "reverse_symbol_mapping")
                        else None
                    )
                    if comp_name:
                        inline_symbols.append({"symbol": symbol, "name": comp_name})

            return {
                "dsl": None,
                "description": text,
                "has_dsl": False,
                "inline_symbols": inline_symbols,
                "components": [],
                "component_paths": [],
                "is_valid": False,
            }

        # Extract DSL using bracket counting (handles nested brackets correctly)
        def extract_balanced_dsl(s: str) -> tuple:
            """Extract DSL with balanced brackets from start of string."""
            if not s:
                return "", s

            # Start with first symbol
            i = 1
            if i >= len(s) or s[i] != "[":
                # Symbol without brackets - just the symbol
                return s[0], s[1:].strip()

            # Count brackets to find end of DSL
            bracket_count = 0
            for i, char in enumerate(s):
                if char == "[":
                    bracket_count += 1
                elif char == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        # Found the end of DSL
                        dsl_part = s[: i + 1]
                        remaining = s[i + 1 :].strip()
                        return dsl_part, remaining

            # Unbalanced brackets - take up to first space or end
            space_idx = s.find(" ")
            if space_idx > 0:
                return s[:space_idx], s[space_idx:].strip()
            return s, ""

        dsl_part, remaining = extract_balanced_dsl(text)

        if dsl_part:
            # Clean up remaining text - remove leading separators (| and ::)
            remaining = re.sub(r"^[\s\|:]+", "", remaining).strip()

            # Parse the DSL to get component info if parse_dsl_to_components exists
            parsed = {}
            if hasattr(self, "parse_dsl_to_components"):
                parsed = self.parse_dsl_to_components(dsl_part)

            return {
                "dsl": dsl_part,
                "description": remaining if remaining else text,
                "has_dsl": True,
                "full_match": dsl_part,
                "components": parsed.get("components", []),
                "component_paths": parsed.get("component_paths", []),
                "is_valid": parsed.get("is_valid", False),
            }

        # Fallback - no DSL found
        return {
            "dsl": None,
            "description": text,
            "has_dsl": False,
            "inline_symbols": [],
            "components": [],
            "component_paths": [],
            "is_valid": False,
        }

    def search_by_dsl(
        self,
        text: str,
        limit: int = 10,
        score_threshold: float = 0.3,
        vector_name: str = "components",
        token_ratio: float = 1.0,
        type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search Qdrant using DSL symbols extracted from text.

        Extracts DSL notation from the input text, embeds it using ColBERT,
        and searches against the specified vector (components/inputs).

        This method is optimized for queries that contain DSL symbols at the
        start, which provide strong semantic signal for matching.

        Args:
            text: Text containing DSL notation (e.g., "§[δ, Ƀ[ᵬ×2]] status card")
            limit: Maximum results to return
            score_threshold: Minimum similarity score
            vector_name: Which vector to search ("components" or "inputs")
            token_ratio: Fraction of ColBERT tokens to use (0.0-1.0).
                         Lower values = faster but potentially less accurate.
            type_filter: Optional filter for point type ("class", "instance_pattern")

        Returns:
            List of matching results with scores and payloads

        Example:
            >>> results = wrapper.search_by_dsl("§[δ, Ƀ[ᵬ×2]] Build a card")
            >>> results[0]["name"]  # "DecoratedText" or similar
        """
        if not self.client:
            logger.warning("Cannot search: Qdrant client not available")
            return []

        # Extract DSL from text
        extracted = self.extract_dsl_from_text(text)

        # Build the search query - prioritize DSL if found
        if extracted["has_dsl"]:
            # Use DSL + description for search (DSL symbols at start)
            search_query = f"{extracted['dsl']} {extracted['description']}"
            logger.info(
                f"DSL search: '{extracted['dsl']}' + '{extracted['description'][:30]}...'"
            )
        else:
            # No DSL found - use full text
            search_query = text
            logger.info(f"Text search (no DSL): '{text[:50]}...'")

        # Generate ColBERT embedding
        vectors = self._embed_with_colbert(search_query, token_ratio)
        if not vectors:
            logger.warning("ColBERT embedding failed for DSL search")
            return []

        try:
            from qdrant_client import models

            # Build filter
            filter_conditions = []
            if type_filter:
                filter_conditions.append(
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value=type_filter),
                    )
                )

            query_filter = (
                models.Filter(must=filter_conditions) if filter_conditions else None
            )

            # Search against the specified vector
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=vectors,
                using=vector_name,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )

            # Process results
            processed = []
            for point in results.points:
                payload = point.payload or {}
                processed.append(
                    {
                        "id": point.id,
                        "score": point.score,
                        "name": payload.get("name"),
                        "type": payload.get("type"),
                        "full_path": payload.get("full_path"),
                        "symbol": payload.get("symbol"),
                        "docstring": payload.get("docstring", "")[:200],
                        "parent_paths": payload.get("parent_paths", []),
                        "card_description": payload.get("card_description", ""),
                        "relationship_text": payload.get("relationship_text", ""),
                    }
                )

            logger.info(
                f"DSL search found {len(processed)} results "
                f"(vector={vector_name}, tokens={len(vectors)})"
            )
            return processed

        except Exception as e:
            logger.error(f"DSL search failed: {e}")
            return []

    def search_by_dsl_hybrid(
        self,
        text: str,
        limit: int = 10,
        score_threshold: float = 0.3,
        token_ratio: float = 1.0,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Hybrid search using both components and inputs vectors.

        Searches against both ColBERT vectors and returns categorized results.
        Useful for finding both class definitions and usage patterns.

        Args:
            text: Text containing DSL notation
            limit: Maximum results per category
            score_threshold: Minimum similarity score
            token_ratio: Fraction of ColBERT tokens to use

        Returns:
            Dict with "classes" and "patterns" result lists
        """
        # Search for class definitions
        class_results = self.search_by_dsl(
            text=text,
            limit=limit,
            score_threshold=score_threshold,
            vector_name="components",
            token_ratio=token_ratio,
            type_filter="class",
        )

        # Search for usage patterns
        pattern_results = self.search_by_dsl(
            text=text,
            limit=limit,
            score_threshold=score_threshold,
            vector_name="inputs",
            token_ratio=token_ratio,
            type_filter="instance_pattern",
        )

        return {
            "classes": class_results,
            "patterns": pattern_results,
            "query_info": self.extract_dsl_from_text(text),
        }

    # =========================================================================
    # V7 MULTI-VECTOR SEARCHES
    # =========================================================================

    def search_v7(
        self,
        query: str,
        vector_name: str = "components",
        limit: int = 10,
        score_threshold: float = 0.3,
        token_ratio: float = 1.0,
        type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search V7 collection using a specific named vector.

        The V7 collection has three named vectors:
        - components: ColBERT multi-vector for component identity
        - inputs: ColBERT multi-vector for parameter values
        - relationships: MiniLM single-vector for graph connections

        Args:
            query: Search query
            vector_name: Which vector to search ("components", "inputs", "relationships")
            limit: Maximum results
            score_threshold: Minimum similarity score
            token_ratio: Fraction of ColBERT tokens to use (for ColBERT vectors)
            type_filter: Optional filter for point type

        Returns:
            List of matching results
        """
        if not self.client:
            logger.warning("Cannot search: Qdrant client not available")
            return []

        try:
            from qdrant_client import models

            # Generate appropriate embedding based on vector type
            if vector_name == "relationships":
                # Use MiniLM for relationships vector
                query_vector = self._embed_with_minilm(query)
                if not query_vector:
                    logger.warning("MiniLM embedding failed for V7 search")
                    return []
            else:
                # Use ColBERT for components/inputs vectors
                query_vector = self._embed_with_colbert(query, token_ratio)
                if not query_vector:
                    logger.warning("ColBERT embedding failed for V7 search")
                    return []

            # Build filter
            filter_conditions = []
            if type_filter:
                filter_conditions.append(
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value=type_filter),
                    )
                )

            query_filter = (
                models.Filter(must=filter_conditions) if filter_conditions else None
            )

            # Search
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                using=vector_name,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )

            # Process results
            processed = []
            for point in results.points:
                payload = point.payload or {}
                processed.append(
                    {
                        "id": point.id,
                        "score": point.score,
                        "name": payload.get("name"),
                        "type": payload.get("type"),
                        "full_path": payload.get("full_path"),
                        "symbol": payload.get("symbol"),
                        "docstring": payload.get("docstring", "")[:200],
                        "parent_paths": payload.get("parent_paths", []),
                        "vector_name": vector_name,
                    }
                )

            logger.info(
                f"V7 search found {len(processed)} results (vector={vector_name})"
            )
            return processed

        except Exception as e:
            logger.error(f"V7 search failed: {e}")
            return []

    def search_v7_hybrid(
        self,
        description: str,
        component_paths: Optional[List[str]] = None,
        limit: int = 10,
        token_ratio: float = 1.0,
        content_feedback: Optional[str] = None,
        form_feedback: Optional[str] = None,
        include_classes: bool = True,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Hybrid V7 search using all three vectors with RRF fusion.

        Searches against:
        1. components vector - for component classes
        2. inputs vector - for usage patterns matching description
        3. relationships vector - for structural patterns

        Results are fused using Reciprocal Rank Fusion (RRF).

        Args:
            description: Natural language description of what to find
            component_paths: Optional list of component paths for relationship context
            limit: Maximum results
            token_ratio: Fraction of ColBERT tokens to use
            content_feedback: Filter for content_feedback field ("positive", "negative", None)
            form_feedback: Filter for form_feedback field ("positive", "negative", None)
            include_classes: Whether to include class results (default True)

        Returns:
            Tuple of (class_results, pattern_results, relationship_results)
        """
        if not self.client:
            logger.warning("Cannot search: Qdrant client not available")
            return [], [], []

        try:
            from qdrant_client import models

            # Generate embeddings
            component_vectors = self._embed_with_colbert(description, token_ratio)
            description_vectors = self._embed_with_colbert(description, token_ratio)

            if not component_vectors or not description_vectors:
                logger.warning("Embedding failed for V7 hybrid search")
                return [], [], []

            # Generate relationship vector
            relationship_text = description
            if component_paths:
                # Enrich with component names
                comp_names = [p.split(".")[-1] for p in component_paths]
                relationship_text = f"{description} | {' '.join(comp_names)}"

            relationship_vector = self._embed_with_minilm(relationship_text)
            if not relationship_vector:
                relationship_vector = [0.0] * RELATIONSHIPS_DIM

            # Build prefetch list
            prefetch_list = []

            # Prefetch 1: Component classes (if requested)
            if include_classes:
                prefetch_list.append(
                    models.Prefetch(
                        query=component_vectors,
                        using="components",
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="type",
                                    match=models.MatchValue(value="class"),
                                )
                            ]
                        ),
                        limit=limit * 2,
                    )
                )

            # Prefetch 2: Instance patterns by inputs (with optional content_feedback filter)
            inputs_filter_conditions = [
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value="instance_pattern"),
                )
            ]
            if content_feedback:
                inputs_filter_conditions.append(
                    models.FieldCondition(
                        key="content_feedback",
                        match=models.MatchValue(value=content_feedback),
                    )
                )

            prefetch_list.append(
                models.Prefetch(
                    query=description_vectors,
                    using="inputs",
                    filter=models.Filter(must=inputs_filter_conditions),
                    limit=limit,
                )
            )

            # Prefetch 3: Patterns by relationships (with optional form_feedback filter)
            if relationship_vector and relationship_vector != [0.0] * RELATIONSHIPS_DIM:
                rel_filter_conditions = [
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="instance_pattern"),
                    )
                ]
                if form_feedback:
                    rel_filter_conditions.append(
                        models.FieldCondition(
                            key="form_feedback",
                            match=models.MatchValue(value=form_feedback),
                        )
                    )

                prefetch_list.append(
                    models.Prefetch(
                        query=relationship_vector,
                        using="relationships",
                        filter=models.Filter(must=rel_filter_conditions),
                        limit=limit,
                    )
                )

            # Hybrid query with prefetch + RRF
            results = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=prefetch_list,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit * 3,
                with_payload=True,
            )

            # Separate results by type and feedback
            class_results = []
            pattern_results = []
            relationship_results = []

            for point in results.points:
                payload = point.payload or {}
                result = {
                    "id": point.id,
                    "score": point.score,
                    "name": payload.get("name"),
                    "type": payload.get("type"),
                    "full_path": payload.get("full_path"),
                    "symbol": payload.get("symbol"),
                    "docstring": payload.get("docstring", "")[:200],
                    "content_feedback": payload.get("content_feedback"),
                    "form_feedback": payload.get("form_feedback"),
                    "parent_paths": payload.get("parent_paths", []),
                    "structure_description": payload.get("structure_description", ""),
                    "card_description": payload.get("card_description", ""),
                    "relationship_text": payload.get("relationship_text", ""),
                    "instance_params": payload.get("instance_params", {}),
                }

                point_type = payload.get("type")
                if point_type == "instance_pattern":
                    # Categorize by feedback
                    if payload.get("content_feedback") == "positive":
                        pattern_results.append(result)
                    if payload.get("form_feedback") == "positive":
                        relationship_results.append(result)
                    # If neither explicitly positive but is a pattern, add to patterns
                    if not pattern_results or result not in pattern_results:
                        if payload.get("feedback") == "positive" or (
                            payload.get("content_feedback") != "positive"
                            and payload.get("form_feedback") != "positive"
                        ):
                            pattern_results.append(result)
                else:
                    class_results.append(result)

            # Log with feedback filter info
            filter_info = []
            if content_feedback:
                filter_info.append(f"content={content_feedback}")
            if form_feedback:
                filter_info.append(f"form={form_feedback}")
            filter_str = f" [{', '.join(filter_info)}]" if filter_info else ""

            logger.info(
                f"V7 hybrid search{filter_str}: {len(class_results)} classes, "
                f"{len(pattern_results)} patterns, {len(relationship_results)} relationships"
            )

            return (
                class_results[:limit],
                pattern_results[:limit],
                relationship_results[:limit],
            )

        except Exception as e:
            logger.error(f"V7 hybrid search failed: {e}")
            return [], [], []

    # =========================================================================
    # RESULT PROCESSING
    # =========================================================================

    def _merge_results_rrf(
        self,
        result_lists: List[List[Dict[str, Any]]],
        k: int = 60,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Merge multiple result lists using Reciprocal Rank Fusion.

        RRF formula: score = sum(1 / (k + rank)) across all lists

        This is useful when combining results from different search strategies
        (e.g., vector search + text search + symbol lookup).

        Args:
            result_lists: List of result lists to merge
            k: RRF constant (default 60, higher = more weight to lower ranks)
            limit: Maximum results to return

        Returns:
            Merged and re-ranked results
        """
        # Track RRF scores by result ID
        rrf_scores: Dict[str, float] = {}
        result_by_id: Dict[str, Dict[str, Any]] = {}

        for results in result_lists:
            for rank, result in enumerate(results, start=1):
                # Use id or full_path as unique identifier
                result_id = str(result.get("id") or result.get("full_path") or rank)

                # Calculate RRF contribution
                rrf_scores[result_id] = rrf_scores.get(result_id, 0) + 1 / (k + rank)

                # Store the result (keep first occurrence)
                if result_id not in result_by_id:
                    result_by_id[result_id] = result

        # Sort by RRF score descending
        sorted_ids = sorted(
            rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True
        )

        # Build final results
        merged = []
        for result_id in sorted_ids[:limit]:
            result = result_by_id[result_id].copy()
            result["rrf_score"] = rrf_scores[result_id]
            merged.append(result)

        logger.debug(
            f"RRF merged {sum(len(r) for r in result_lists)} results into {len(merged)}"
        )
        return merged


# Export for convenience
__all__ = [
    "SearchMixin",
    "COLBERT_DIM",
    "RELATIONSHIPS_DIM",
]
