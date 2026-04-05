"""SearchMixin base class definition with mixin contract and schema detection."""

import importlib
from typing import Any, Dict, List, Optional

from adapters.module_wrapper.types import (
    ComponentName,
    ComponentPath,
    Payload,
)
from config.enhanced_logging import setup_logger

logger = setup_logger()


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
            "search_named_vector",
            "search_hybrid",
            "search_hybrid_dispatch",
            "search_hybrid_multidim",
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

    # --- Learned model class-level state ---
    _learned_model = None  # class-level cache for the trained model
    _learned_feature_version = 1  # 1=9D, 2=8D, 3=14D, 4=15D, 5=17D
    _learned_model_type = "single"  # "single" or "dual_head"
    _learned_model_domain = None  # domain_id from checkpoint
    _learned_dag_children: dict = {}
    _learned_dag_parents: dict = {}
    _learned_dag_depth: dict = {}
    _learned_dag_loaded = False

    # Per-domain model registry: {domain_id: (model, feature_version, model_type)}
    _learned_model_registry: dict = {}

    _has_content_vector: Optional[bool] = None  # Cached result

    # =========================================================================
    # COLLECTION SCHEMA DETECTION
    # =========================================================================

    def _resolve_using(
        self, preferred: str = "components", vector_name: Optional[str] = None
    ) -> Optional[str]:
        """Return the named vector to search, or None for single-vector collections.

        For named-vector collections (RIC schema with components/inputs/relationships),
        Qdrant requires ``using=<name>`` - omitting it causes
        "Not existing vector name error".

        For single-vector (V1) collections, ``using`` must be omitted.

        Args:
            preferred: Default named vector when the collection uses named vectors.
            vector_name: Explicit override - returned as-is when provided.

        Returns:
            The vector name string for named-vector collections, or None for V1.
        """
        # Explicit caller override
        if vector_name is not None:
            return vector_name

        # Use cached result if available
        if hasattr(self, "_named_vectors_cache"):
            cached = self._named_vectors_cache
            if cached is not None:
                return preferred if cached else None

        # Detect schema from collection config
        try:
            collection_info = self.client.get_collection(self.collection_name)
            vectors_config = collection_info.config.params.vectors
            has_named = isinstance(vectors_config, dict)
            self._named_vectors_cache = has_named
            if has_named:
                logger.debug(
                    f"Collection {self.collection_name} uses named vectors: "
                    f"{list(vectors_config.keys())}"
                )
            return preferred if has_named else None
        except Exception as e:
            logger.warning(f"Could not detect collection schema: {e}")
            self._named_vectors_cache = False
            return None
