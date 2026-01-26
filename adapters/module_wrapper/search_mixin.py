"""
Search Functionality Mixin

Provides search capabilities including standard search, ColBERT search,
and component lookup for the ModuleWrapper system.
"""

import asyncio
import importlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    """

    def search(
        self, query: str, limit: int = 5, score_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
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
        self, query: str, limit: int = 5, score_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
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
                logger.info(f"Found {len(direct_results)} direct matches for '{query}' (async)")
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
                    logger.warning(f"Could not extract points from async search results: {e}")
                    return []

            return self._process_search_results(points)

        except Exception as e:
            logger.error(f"Async search failed: {e}", exc_info=True)
            raise

    def colbert_search(
        self, query: str, limit: int = 5, score_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
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

        if not self.enable_colbert or not getattr(self, '_colbert_initialized', False):
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

                    component_path = payload.get("full_path") or payload.get("name", "unknown")

                    results.append({
                        "name": payload.get("name"),
                        "path": component_path,
                        "type": payload.get("type"),
                        "score": score,
                        "docstring": payload.get("docstring", ""),
                        "component": self._get_component_from_path(component_path),
                        "embedding_type": "colbert",
                    })

                    logger.info(f"  - {payload.get('name')} (score: {score:.4f})")

                except Exception as e:
                    logger.warning(f"Error processing ColBERT result: {e}")
                    continue

            return results

        except Exception as e:
            logger.error(f"ColBERT search failed: {e}", exc_info=True)
            logger.info("Falling back to standard search")
            return self.search(query, limit, score_threshold)

    def _direct_component_lookup(self, component_name: str) -> List[Dict[str, Any]]:
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
                    results.append({
                        "score": 1.0,
                        "name": component.name,
                        "path": path,
                        "type": component.component_type,
                        "docstring": component.docstring,
                        "component": component.obj,
                    })

        # If no exact matches, try case-insensitive match
        if not results:
            for path, component in self.components.items():
                if component.name.lower() == component_name.lower():
                    logger.info(f"Case-insensitive match found: {path}")
                    if component.obj is not None:
                        results.append({
                            "score": 0.9,
                            "name": component.name,
                            "path": path,
                            "type": component.component_type,
                            "docstring": component.docstring,
                            "component": component.obj,
                        })

        # Check for components in widgets module
        if not results and hasattr(self.module, "widgets"):
            widgets_path = f"{self.module_name}.widgets.{component_name}"
            component = self.components.get(widgets_path)
            if component and component.obj is not None:
                logger.info(f"Found component in widgets module: {widgets_path}")
                results.append({
                    "score": 1.0,
                    "name": component.name,
                    "path": widgets_path,
                    "type": component.component_type,
                    "docstring": component.docstring,
                    "component": component.obj,
                })

        return results

    def _process_search_results(self, points: List) -> List[Dict[str, Any]]:
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

            results.append({
                "score": score,
                "name": name,
                "path": path,
                "full_path": full_path,
                "module_path": module_path if isinstance(payload, dict) else None,
                "type": type_info,
                "docstring": docstring,
                "component": component_obj,
            })

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
                    parts = parts[len(subparts):]

            # Start with the module
            obj = self.module

            # Traverse the path
            for part in parts:
                try:
                    obj = getattr(obj, part)
                except AttributeError:
                    module_candidate = f"{getattr(obj, '__name__', '')}.{part}".lstrip(".")
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
                path for path, comp in self.components.items()
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
                logger.info(f"Successfully created card component: {type(component).__name__}")
                return component

            except (ValueError, TypeError) as e:
                logger.warning(f"Error getting signature for {card_class}: {e}")
                try:
                    component = card_class(**params)
                    logger.info(f"Created card component with direct instantiation: {type(component).__name__}")
                    return component
                except Exception as e2:
                    logger.warning(f"Direct instantiation failed: {e2}")
                    return None

        except Exception as e:
            logger.warning(f"Failed to create card component: {e}")
            return None

    def query_by_symbol(
        self,
        symbol: str,
        include_relationships: bool = True,
        limit: int = 1,
    ) -> List[Dict[str, Any]]:
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


# Export for convenience
__all__ = [
    "SearchMixin",
]
