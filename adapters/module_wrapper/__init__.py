"""
Module Wrapper Package

A modular implementation of the ModuleWrapper system for Python module
introspection and Qdrant vector database integration.

This package provides:
- ModuleWrapper: Full-featured wrapper with Qdrant integration
- ModuleComponent: Represents a component within a module
- ModuleWrapperBase: Base class with essential module introspection
- Mixins: Modular functionality for Qdrant, embedding, indexing, search, relationships
- SymbolGenerator: Generates unique Unicode symbols for components
- StructureValidator: Validates DSL structures against component hierarchy
- DSLParser: Parses and converts DSL notation to Qdrant queries
- Text indexing helpers for full-text search

Usage:
    # Full ModuleWrapper with all functionality
    from adapters.module_wrapper import ModuleWrapper

    wrapper = ModuleWrapper("card_framework.v2", auto_initialize=True)
    results = wrapper.search("button with click")

    # Use individual components directly
    from adapters.module_wrapper import (
        ModuleComponent,
        ModuleWrapperBase,
        SymbolGenerator,
        StructureValidator,
        DSLParser,
    )
"""

import logging
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)

# =============================================================================
# CORE CLASSES
# =============================================================================

from adapters.module_wrapper.core import (
    BUILTIN_PREFIXES,
    DEFAULT_RELATIONSHIP_DEPTH,
    PRIMITIVE_TYPES,
    ModuleComponent,
    ModuleWrapperBase,
    get_qdrant_config_from_env,
    parse_qdrant_url,
)

# =============================================================================
# DSL PARSING
# =============================================================================
from adapters.module_wrapper.dsl_parser import (
    STYLE_MODIFIERS,
    ContentBlock,
    ContentDSLResult,
    ContentLine,
    DSLNode,
    # Structure DSL
    DSLParser,
    DSLParseResult,
    DSLToken,
    QdrantQuery,
    # Content DSL
    StyleModifier,
    add_style_modifier,
    content_dsl_to_jinja,
    create_parser_from_wrapper,
    extract_dsl_from_description,
    get_style_modifiers,
    parse_content_dsl,
    parse_dsl_to_qdrant_query,
    validate_dsl_structure,
)
from adapters.module_wrapper.embedding_mixin import (
    EmbeddingMixin,
    _get_colbert_embed,
    _get_fastembed,
)
from adapters.module_wrapper.indexing_mixin import (
    STD_LIB_PREFIXES,
    THIRD_PARTY_PREFIXES,
    IndexingMixin,
)
from adapters.module_wrapper.pipeline_mixin import PipelineMixin

# =============================================================================
# MIXINS
# =============================================================================
from adapters.module_wrapper.qdrant_mixin import (
    QdrantMixin,
    _get_numpy,
    _get_qdrant_imports,
)
from adapters.module_wrapper.graph_mixin import (
    GraphMixin,
    ComponentMetadataProvider,
    _get_networkx,
)
from adapters.module_wrapper.relationships_mixin import RelationshipsMixin
from adapters.module_wrapper.cache_mixin import CacheMixin
from adapters.module_wrapper.instance_pattern_mixin import (
    InstancePatternMixin,
    InstancePattern,
    PatternVariation,
    VariationFamily,
    StructureVariator,
    ParameterVariator,
)
from adapters.module_wrapper.search_mixin import (
    COLBERT_DIM,
    RELATIONSHIPS_DIM,
    SearchMixin,
)

# =============================================================================
# STRUCTURE VALIDATION
# =============================================================================
from adapters.module_wrapper.structure_validator import (
    INPUT_PATTERNS,
    NEEDS_WRAPPER,
    WIDGET_TYPES,
    ComponentSlot,
    StructureValidator,
    ValidationResult,
    create_validator,
)

# =============================================================================
# SYMBOL GENERATION
# =============================================================================
from adapters.module_wrapper.symbol_generator import (
    DEFAULT_STYLE_RULES,
    FALLBACK_SYMBOLS,
    LETTER_SYMBOLS,
    MODULE_PREFIX_SYMBOLS,
    StyleRule,
    StylingRegistry,
    SymbolGenerator,
    create_default_styling_registry,
    create_generator_for_module,
    extract_component_names_from_wrapper,
)
from adapters.module_wrapper.symbols_mixin import SymbolsMixin
from adapters.module_wrapper.skills_mixin import SkillsMixin
from adapters.module_wrapper.skill_types import (
    SkillDocument,
    SkillInfo,
    SkillManifest,
    SkillGeneratorConfig,
)

# =============================================================================
# TEXT INDEXING
# =============================================================================
from adapters.module_wrapper.text_indexing import (
    create_component_text_indices,
    create_module_field_index,
    search_by_text,
    search_components_by_relationship,
    search_within_module,
)

# =============================================================================
# FULL MODULE WRAPPER - COMPOSED FROM MIXINS
# =============================================================================


class ModuleWrapper(
    QdrantMixin,
    EmbeddingMixin,
    IndexingMixin,
    SearchMixin,
    RelationshipsMixin,
    SymbolsMixin,
    SkillsMixin,
    PipelineMixin,
    GraphMixin,
    CacheMixin,
    InstancePatternMixin,
    ModuleWrapperBase,
):
    """
    Full-featured ModuleWrapper with Qdrant integration.

    Combines all mixins to provide:
    - Qdrant client management (QdrantMixin)
    - Embedding model initialization (EmbeddingMixin)
    - Component indexing (IndexingMixin)
    - Search functionality (SearchMixin)
    - Relationship extraction (RelationshipsMixin)
    - Symbol generation and DSL (SymbolsMixin)
    - V7 ingestion pipeline (PipelineMixin)
    - Graph-based relationship DAG (GraphMixin)
    - Tiered component caching (CacheMixin)
    - Instance pattern storage and variation (InstancePatternMixin)
    - Skill document generation (SkillsMixin)
    - Base module introspection (ModuleWrapperBase)

    Usage:
        wrapper = ModuleWrapper("card_framework.v2", auto_initialize=True)
        results = wrapper.search("button with click action")
        component = wrapper.get_component_by_path("card_framework.v2.widgets.button_list.ButtonList")

        # Graph-based traversal
        wrapper.build_relationship_graph()
        descendants = wrapper.get_descendants("Section", depth=2)
        paths = wrapper.get_all_paths("Card", "Icon")

        # Component caching (fast retrieval without path reconstruction)
        entry = wrapper.cache_pattern("my_card", ["Section", "DecoratedText"])
        Section = wrapper.get_cached_class("Section")

        # Instance pattern storage and variation generation
        wrapper.store_instance_pattern(
            component_paths=["Section", "DecoratedText"],
            instance_params={"text": "Hello"},
            description="A simple text card",
            generate_variations=True,
        )
        variation = wrapper.get_cached_variation(pattern_id, "structure")
    """

    def __init__(
        self,
        module_or_name: Union[str, Any],
        qdrant_host: Optional[str] = None,
        qdrant_port: Optional[int] = None,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        collection_name: str = "module_components",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        index_nested: bool = True,
        index_private: bool = False,
        max_depth: int = 2,
        auto_initialize: bool = True,
        skip_standard_library: bool = True,
        include_modules: Optional[List[str]] = None,
        exclude_modules: Optional[List[str]] = None,
        force_reindex: bool = False,
        clear_collection: bool = False,
        enable_colbert: bool = False,
        colbert_model: str = "colbert-ir/colbertv2.0",
        colbert_collection_name: Optional[str] = None,
    ):
        """
        Initialize the ModuleWrapper.

        Args:
            module_or_name: The module object or its name (string)
            qdrant_host: Qdrant server hostname
            qdrant_port: Qdrant server port
            qdrant_url: Full Qdrant URL (overrides host/port)
            qdrant_api_key: API key for Qdrant authentication
            collection_name: Name of the Qdrant collection
            embedding_model: Model for generating embeddings
            index_nested: Whether to index nested components
            index_private: Whether to index private components
            max_depth: Maximum recursion depth for submodules
            auto_initialize: Whether to automatically initialize and index
            skip_standard_library: Whether to skip standard library modules
            include_modules: Whitelist of module prefixes to include
            exclude_modules: Blacklist of module prefixes to exclude
            force_reindex: Force re-indexing even if collection has data
            clear_collection: Clear collection before indexing
            enable_colbert: Enable ColBERT multi-vector embeddings
            colbert_model: ColBERT model to use
            colbert_collection_name: Separate collection for ColBERT
        """
        # Initialize base class (sets up all configuration)
        super().__init__(
            module_or_name=module_or_name,
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
            collection_name=collection_name,
            embedding_model=embedding_model,
            index_nested=index_nested,
            index_private=index_private,
            max_depth=max_depth,
            auto_initialize=False,  # We'll handle this ourselves
            skip_standard_library=skip_standard_library,
            include_modules=include_modules,
            exclude_modules=exclude_modules,
            force_reindex=force_reindex,
            clear_collection=clear_collection,
            enable_colbert=enable_colbert,
            colbert_model=colbert_model,
            colbert_collection_name=colbert_collection_name,
        )

        # Auto-initialize if requested
        if auto_initialize:
            self.initialize()

    def initialize(self):
        """Initialize the wrapper and index the module components."""
        try:
            logger.info(f"Initializing ModuleWrapper for {self.module_name}...")

            # Initialize Qdrant client (from QdrantMixin)
            self._initialize_qdrant()

            # Initialize embedding model (from EmbeddingMixin)
            self._initialize_embedder()

            # Ensure collection exists (from QdrantMixin)
            self._ensure_collection()

            # Ensure symbol index exists for fast lookups (from QdrantMixin)
            self.ensure_symbol_index()

            # Index module components (from IndexingMixin)
            self._index_module_components()

            # Initialize ColBERT if enabled
            if self.enable_colbert:
                logger.info("ColBERT mode enabled - initializing ColBERT embedder...")
                self._initialize_colbert_embedder()
                self._ensure_colbert_collection()
                self._index_components_colbert()

            self._initialized = True
            logger.info(f"ModuleWrapper initialized for {self.module_name}")

        except Exception as e:
            logger.error(f"Failed to initialize ModuleWrapper: {e}", exc_info=True)
            raise


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Main class
    "ModuleWrapper",
    # Core
    "ModuleComponent",
    "ModuleWrapperBase",
    "parse_qdrant_url",
    "get_qdrant_config_from_env",
    "DEFAULT_RELATIONSHIP_DEPTH",
    "PRIMITIVE_TYPES",
    "BUILTIN_PREFIXES",
    # Mixins
    "QdrantMixin",
    "EmbeddingMixin",
    "IndexingMixin",
    "SearchMixin",
    "RelationshipsMixin",
    "SymbolsMixin",
    "SkillsMixin",
    "PipelineMixin",
    "GraphMixin",
    "ComponentMetadataProvider",
    "CacheMixin",
    "InstancePatternMixin",
    # Instance pattern classes
    "InstancePattern",
    "PatternVariation",
    "VariationFamily",
    "StructureVariator",
    "ParameterVariator",
    # Skill types
    "SkillDocument",
    "SkillInfo",
    "SkillManifest",
    "SkillGeneratorConfig",
    # Lazy imports
    "_get_qdrant_imports",
    "_get_numpy",
    "_get_fastembed",
    "_get_colbert_embed",
    "_get_networkx",
    # Symbol generation
    "SymbolGenerator",
    "StyleRule",
    "StylingRegistry",
    "LETTER_SYMBOLS",
    "FALLBACK_SYMBOLS",
    "MODULE_PREFIX_SYMBOLS",
    "DEFAULT_STYLE_RULES",
    "create_generator_for_module",
    "create_default_styling_registry",
    "extract_component_names_from_wrapper",
    # Structure validation
    "StructureValidator",
    "ValidationResult",
    "ComponentSlot",
    "INPUT_PATTERNS",
    "WIDGET_TYPES",
    "NEEDS_WRAPPER",
    "create_validator",
    # Structure DSL parsing
    "DSLParser",
    "DSLToken",
    "DSLNode",
    "DSLParseResult",
    "QdrantQuery",
    "parse_dsl_to_qdrant_query",
    "extract_dsl_from_description",
    "validate_dsl_structure",
    "create_parser_from_wrapper",
    # Content DSL parsing
    "StyleModifier",
    "ContentLine",
    "ContentBlock",
    "ContentDSLResult",
    "STYLE_MODIFIERS",
    "parse_content_dsl",
    "content_dsl_to_jinja",
    "get_style_modifiers",
    "add_style_modifier",
    # Text indexing (standalone functions)
    "create_component_text_indices",
    "search_by_text",
    "search_components_by_relationship",
    "create_module_field_index",
    "search_within_module",
    # Search constants
    "COLBERT_DIM",
    "RELATIONSHIPS_DIM",
]

__version__ = "2.0.0"
