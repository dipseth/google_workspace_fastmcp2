"""Search Mixin Package -- split from monolithic search_mixin.py for readability.

Public API (unchanged):
    from adapters.module_wrapper.search_mixin import SearchMixin, COLBERT_DIM, RELATIONSHIPS_DIM
"""

from adapters.module_wrapper.types import (
    COLBERT_DIM as _COLBERT_DIM,
)
from adapters.module_wrapper.types import (
    RELATIONSHIPS_DIM as _RELATIONSHIPS_DIM,
)

# Re-export constants for backwards compatibility
COLBERT_DIM = _COLBERT_DIM
RELATIONSHIPS_DIM = _RELATIONSHIPS_DIM

# --- Import base class (mixin contract, _resolve_using, class-level state) ---
from ._base import SearchMixin

# --- Import all method implementations ---
from ._basic import (
    _direct_component_lookup,
    _get_component_from_path,
    _process_search_results,
    colbert_search,
    query_by_symbol,
    search,
    search_async,
)
from ._component_lookup import (
    _get_template_component,
    create_card_component,
    get_component_by_path,
    get_component_children,
    get_component_fields,
    get_component_hierarchy,
    get_component_info,
    get_component_source,
    list_components,
)
from ._dsl_search import (
    extract_dsl_from_text,
    search_by_dsl,
    search_by_dsl_hybrid,
)
from ._embedding import (
    _embed_with_colbert,
    _embed_with_minilm,
    _get_colbert_embedder,
    _get_minilm_embedder,
)
from ._hybrid_dispatch import (
    _run_shadow_scoring,
    search_hybrid_dispatch,
)
from ._hybrid_helpers import (
    _build_prefetch_list,
    _categorize_scored_results,
    _compute_content_density,
    _compute_learned_features,
    _compute_structural_features,
    _infer_component_paths,
    _query_grouped_candidates,
)
from ._hybrid_learned import search_hybrid_learned
from ._hybrid_multidim import search_hybrid_multidim
from ._hybrid_recursive import search_hybrid_recursive
from ._learned_model import (
    _collection_has_content_vector,
    _ensure_learned_dag,
    _load_learned_model,
    _resolve_checkpoint_path,
)
from ._named_vector import search_hybrid, search_named_vector
from ._result_processing import _merge_results_rrf
from ._scoring import _cosine_similarity, _maxsim, _maxsim_decomposed
from ._text_search import (
    search_by_relationship_text,
    search_by_text,
    search_within_module,
)

# --- Attach methods to SearchMixin ---

# Embedding helpers
SearchMixin._get_colbert_embedder = _get_colbert_embedder
SearchMixin._get_minilm_embedder = _get_minilm_embedder
SearchMixin._embed_with_colbert = _embed_with_colbert
SearchMixin._embed_with_minilm = _embed_with_minilm

# Basic search
SearchMixin.search = search
SearchMixin.search_async = search_async
SearchMixin.colbert_search = colbert_search
SearchMixin._direct_component_lookup = _direct_component_lookup
SearchMixin._process_search_results = _process_search_results
SearchMixin._get_component_from_path = _get_component_from_path
SearchMixin.query_by_symbol = query_by_symbol

# Component lookup
SearchMixin.get_component_by_path = get_component_by_path
SearchMixin._get_template_component = _get_template_component
SearchMixin.get_component_info = get_component_info
SearchMixin.list_components = list_components
SearchMixin.get_component_source = get_component_source
SearchMixin.create_card_component = create_card_component
SearchMixin.get_component_fields = get_component_fields
SearchMixin.get_component_children = get_component_children
SearchMixin.get_component_hierarchy = get_component_hierarchy

# Text search
SearchMixin.search_by_text = search_by_text
SearchMixin.search_by_relationship_text = search_by_relationship_text
SearchMixin.search_within_module = search_within_module

# DSL search
SearchMixin.extract_dsl_from_text = extract_dsl_from_text
SearchMixin.search_by_dsl = search_by_dsl
SearchMixin.search_by_dsl_hybrid = search_by_dsl_hybrid

# Named vector / hybrid
SearchMixin.search_named_vector = search_named_vector
SearchMixin.search_hybrid = search_hybrid

# Hybrid helpers
SearchMixin._build_prefetch_list = _build_prefetch_list
SearchMixin._query_grouped_candidates = _query_grouped_candidates
SearchMixin._infer_component_paths = _infer_component_paths
SearchMixin._compute_structural_features = _compute_structural_features
SearchMixin._compute_content_density = staticmethod(_compute_content_density)
SearchMixin._compute_learned_features = _compute_learned_features
SearchMixin._categorize_scored_results = _categorize_scored_results

# Hybrid dispatch
SearchMixin.search_hybrid_dispatch = search_hybrid_dispatch
SearchMixin._run_shadow_scoring = _run_shadow_scoring

# Scoring (static methods)
SearchMixin._maxsim = staticmethod(_maxsim)
SearchMixin._maxsim_decomposed = staticmethod(_maxsim_decomposed)
SearchMixin._cosine_similarity = staticmethod(_cosine_similarity)

# Hybrid multidim
SearchMixin.search_hybrid_multidim = search_hybrid_multidim

# Learned model
SearchMixin._resolve_checkpoint_path = _resolve_checkpoint_path
SearchMixin._load_learned_model = _load_learned_model
SearchMixin._ensure_learned_dag = _ensure_learned_dag
SearchMixin._collection_has_content_vector = _collection_has_content_vector

# Hybrid learned
SearchMixin.search_hybrid_learned = search_hybrid_learned

# Hybrid recursive
SearchMixin.search_hybrid_recursive = search_hybrid_recursive

# Result processing
SearchMixin._merge_results_rrf = _merge_results_rrf


__all__ = [
    "SearchMixin",
    "COLBERT_DIM",
    "RELATIONSHIPS_DIM",
]
