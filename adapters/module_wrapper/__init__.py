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
import threading
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)

# =============================================================================
# TYPE DEFINITIONS (Import First for Use by Other Modules)
# =============================================================================

# =============================================================================
# RELATIONSHIP STRATEGIES & TOOL GRAPH
# =============================================================================
from adapters.module_wrapper.behavioral_relationships import (
    BehavioralRelationshipStrategy,
    RelationshipStrategy,
    StructuralRelationshipStrategy,
)
from adapters.module_wrapper.cache_mixin import CacheMixin

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
from adapters.module_wrapper.graph_mixin import (
    ComponentMetadataProvider,
    GraphMixin,
    _get_rustworkx,
)
from adapters.module_wrapper.indexing_mixin import (
    STD_LIB_PREFIXES,
    THIRD_PARTY_PREFIXES,
    IndexingMixin,
)
from adapters.module_wrapper.instance_pattern_mixin import (
    InstancePattern,
    InstancePatternMixin,
    ParameterVariator,
    PatternVariation,
    StructureVariator,
    VariationFamily,
)
from adapters.module_wrapper.mixin_meta import (
    MixinContract,
    check_runtime_dependencies,
    generate_mermaid_dependency_graph,
    generate_provides_requires_table,
    get_all_contracts,
    requires_deps,
    validate_mixin_dependencies,
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
from adapters.module_wrapper.relationships_mixin import RelationshipsMixin
from adapters.module_wrapper.ric_provider import IntrospectionProvider, RICTextProvider
from adapters.module_wrapper.search_mixin import (
    COLBERT_DIM,
    RELATIONSHIPS_DIM,
    SearchMixin,
)
from adapters.module_wrapper.skill_types import (
    SkillDocument,
    SkillGeneratorConfig,
    SkillInfo,
    SkillManifest,
)
from adapters.module_wrapper.skills_mixin import SkillsMixin

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
from adapters.module_wrapper.tool_relationship_graph import ToolRelationshipGraph
from adapters.module_wrapper.types import (
    # Constants (also available from core, but centralized here)
    COLBERT_DIM as TYPES_COLBERT_DIM,
)
from adapters.module_wrapper.types import (
    MINILM_DIM,
    CacheKey,
    ComponentInfo,
    ComponentName,
    ComponentPath,
    ComponentPaths,
    DSLNotation,
    Embeddable,
    EmbeddingConfig,
    EmbeddingDimension,
    EmbeddingVector,
    EvictionCallback,
    HasSymbol,
    IndexingStats,
    IssueList,
    JsonDict,
    MultiVector,
    # Type Aliases
    Payload,
    # Dataclasses
    QdrantConfig,
    QdrantFilter,
    QueryText,
    RelationshipDict,
    RelationshipInfo,
    RelationshipList,
    ReverseSymbolMapping,
    SearchResult,
    # Protocols
    Serializable,
    SuggestionList,
    Symbol,
    SymbolMapping,
    Timestamped,
    TimestampedMixin,
    Validatable,
    WrapperGetter,
)
from adapters.module_wrapper.types import (
    RELATIONSHIPS_DIM as TYPES_RELATIONSHIPS_DIM,
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
        priority_overrides: Optional[Dict[str, int]] = None,
        nl_relationship_patterns: Optional[Dict[tuple, str]] = None,
        use_v7_schema: bool = False,
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
            priority_overrides: Domain-specific priority score boosts for symbol generation
            nl_relationship_patterns: Domain-specific NL patterns for relationships
            use_v7_schema: Use v7 3-vector schema (components, inputs, relationships)
                instead of single-vector. Collection name defaults to mcp_{module}_v7.
        """
        self._use_v7_schema = use_v7_schema
        self._v7_pipeline_thread: Optional[threading.Thread] = None
        self._v7_pipeline_status: str = "idle"  # idle, running, completed, failed
        self._v7_pipeline_error: Optional[str] = None
        self._v7_post_pipeline_callbacks: List[callable] = []
        self._v7_pipeline_lock = threading.Lock()

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
            priority_overrides=priority_overrides,
            nl_relationship_patterns=nl_relationship_patterns,
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

            if self._use_v7_schema:
                # V7 path: 3 named vectors (components, inputs, relationships)
                self._initialize_v7()
            else:
                # Legacy path: single flat vector
                self._ensure_collection()
                self.ensure_symbol_index()
                self._index_module_components()

                if self.enable_colbert:
                    logger.info(
                        "ColBERT mode enabled - initializing ColBERT embedder..."
                    )
                    self._initialize_colbert_embedder()
                    self._ensure_colbert_collection()
                    self._index_components_colbert()

            self._initialized = True
            logger.info(f"ModuleWrapper initialized for {self.module_name}")

            # Optional strict-mode validation
            import os

            if os.environ.get("MODULE_WRAPPER_STRICT") == "1":
                self.validate_dependencies(strict=True)

        except Exception as e:
            logger.error(f"Failed to initialize ModuleWrapper: {e}", exc_info=True)
            raise

    def _initialize_v7(self):
        """Initialize using v7 3-vector schema via PipelineMixin.

        Fast path: If v7 collection exists with data, loads components from
        Qdrant synchronously. The wrapper is fully ready when this returns.

        Slow path: If collection needs (re)creation, does module introspection
        synchronously (populating self.components and symbols), then runs the
        v7 pipeline in a background thread. The wrapper is usable immediately
        for in-memory operations (DSL parsing, symbol lookup, etc.) while
        the pipeline indexes to Qdrant in the background.
        """
        v7_name = self.collection_name
        logger.info(f"Using v7 schema for collection: {v7_name}")

        # Check if v7 collection already exists with data
        try:
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if v7_name in collection_names:
                info = self.client.get_collection(v7_name)
                vectors_config = info.config.params.vectors

                # Verify it's actually a v7 schema (named vectors dict, not single)
                is_v7 = isinstance(vectors_config, dict)

                if is_v7 and info.points_count > 0 and not self.force_reindex:
                    logger.info(
                        f"V7 collection {v7_name} exists with {info.points_count} points "
                        f"and correct schema — loading existing components"
                    )
                    self._load_existing_components_v7(v7_name)
                    self._v7_pipeline_status = "completed"
                    return

                # Collection exists but needs recreation (wrong schema, empty, or force_reindex).
                # Delete it so the staging step can create a fresh single-vector collection.
                reason = (
                    "wrong schema (single vector)"
                    if not is_v7
                    else (
                        "force_reindex requested"
                        if self.force_reindex
                        else f"empty ({info.points_count} points)"
                    )
                )
                logger.warning(
                    f"Collection {v7_name} exists but {reason}. Deleting for recreation."
                )
                self.client.delete_collection(v7_name)
                logger.info(f"Deleted collection: {v7_name}")
        except Exception as e:
            logger.warning(f"Error checking existing collection: {e}")

        # === SYNC: Module introspection (populate self.components in memory) ===
        # Skip Qdrant storage — the pipeline will handle all writes to the v7 collection.
        self._v7_introspect_module()

        # === BACKGROUND: Run v7 pipeline (slow — ColBERT embeddings) ===
        logger.info(
            f"Starting v7 pipeline in background for {v7_name} "
            f"({len(self.components)} components)..."
        )
        self._v7_pipeline_status = "running"
        self._v7_pipeline_thread = threading.Thread(
            target=self._run_v7_pipeline_background,
            args=(v7_name,),
            name=f"v7-pipeline-{self.module_name}",
            daemon=True,
        )
        self._v7_pipeline_thread.start()

    def _v7_introspect_module(self):
        """Introspect module to populate self.components without writing to Qdrant.

        This is the sync-only part of v7 initialization: fast module walking
        that populates self.components and triggers symbol generation.
        """
        import inspect

        logger.info(
            f"Introspecting module {self.module_name} (max depth: {self.max_depth})..."
        )

        # Reset visited modules and depth counter
        self._visited_modules = set()
        self._current_depth = 0
        self._visited_modules.add(self.module.__name__)

        # Walk module hierarchy — same logic as _index_module_components but
        # without the _store_components_in_qdrant() call at the end.
        for name, obj in inspect.getmembers(self.module):
            if name.startswith("_") and not self.index_private:
                continue

            if (
                inspect.ismodule(obj)
                and hasattr(obj, "__name__")
                and not self._should_include_module(obj.__name__, 0)
            ):
                continue

            component = self._create_component(name, obj, self.module_name)
            self.root_components[name] = component
            self.components[component.full_path] = component

            if self.index_nested:
                self._index_nested_components(component)

                if (
                    inspect.ismodule(obj)
                    and obj.__name__ not in self._visited_modules
                    and self._current_depth < self.max_depth
                    and hasattr(obj, "__name__")
                    and self._should_include_module(obj.__name__, 1)
                ):
                    self._index_submodule(name, obj)

        # Special handling for widgets modules
        if hasattr(self.module, "widgets"):
            try:
                widgets_module = getattr(self.module, "widgets")
                if inspect.ismodule(widgets_module):
                    self._index_widgets_module(widgets_module)
            except Exception as e:
                logger.warning(f"Error accessing widgets module: {e}")

        logger.info(
            f"Introspected {len(self.components)} components from {self.module_name}"
        )

        # Trigger lazy symbol generation so symbols are ready immediately
        _ = self.symbol_mapping

    def _run_v7_pipeline_background(self, v7_name: str):
        """Run the v7 ingestion pipeline in a background thread.

        NOTE: force_recreate=False because _initialize_v7() already handles
        collection deletion when the schema is wrong or force_reindex is set.
        Using force_recreate=True here was causing a full re-index on every
        server restart, pegging CPU for several minutes while ColBERT embeds
        900+ components unnecessarily.
        """
        try:
            # Safety guard: re-check if collection already has data.
            # Between _initialize_v7() scheduling this thread and the thread
            # actually starting, Qdrant may have finished loading persisted data
            # (especially in Docker where depends_on: qdrant is used).
            try:
                collections = self.client.get_collections()
                collection_names = [c.name for c in collections.collections]
                if v7_name in collection_names:
                    info = self.client.get_collection(v7_name)
                    vectors_config = info.config.params.vectors
                    is_v7 = isinstance(vectors_config, dict)
                    if is_v7 and info.points_count > 0 and not self.force_reindex:
                        logger.info(
                            f"[BG] V7 collection {v7_name} already has "
                            f"{info.points_count} points — skipping expensive pipeline"
                        )
                        # Still load components into memory if not already loaded
                        if not self.components:
                            self._load_existing_components_v7(v7_name)
                        self._v7_pipeline_status = "completed"
                        return
            except Exception as e:
                logger.debug(
                    f"[BG] Pre-flight check failed (proceeding with pipeline): {e}"
                )

            logger.info(f"[BG] V7 pipeline starting for {v7_name}...")
            result = self.run_ingestion_pipeline(
                collection_name=v7_name,
                force_recreate=False,
                include_instance_patterns=False,
            )
            component_count = result.get("components", 0)
            logger.info(
                f"[BG] V7 pipeline complete for {v7_name}: "
                f"{component_count} components indexed"
            )

            # Run any queued post-pipeline callbacks (e.g. index_custom_components)
            with self._v7_pipeline_lock:
                callbacks = list(self._v7_post_pipeline_callbacks)
                self._v7_post_pipeline_callbacks.clear()

            for callback in callbacks:
                try:
                    callback_name = getattr(callback, "__name__", str(callback))
                    logger.info(f"[BG] Running post-pipeline callback: {callback_name}")
                    callback()
                except Exception as e:
                    logger.warning(f"[BG] Post-pipeline callback failed: {e}")

            self._v7_pipeline_status = "completed"
            logger.info(f"[BG] V7 initialization fully complete for {v7_name}")

        except Exception as e:
            self._v7_pipeline_error = str(e)
            self._v7_pipeline_status = "failed"
            logger.error(f"[BG] V7 pipeline failed for {v7_name}: {e}", exc_info=True)

    def queue_post_pipeline_callback(self, callback: callable):
        """Queue a callback to run after the v7 pipeline completes.

        If the pipeline has already completed, the callback is run immediately.
        Use this for Qdrant write operations that depend on the v7 collection
        being ready (e.g. index_custom_components, create_text_indices).

        Args:
            callback: Zero-argument callable to run after pipeline completion.
        """
        with self._v7_pipeline_lock:
            if self._v7_pipeline_status == "completed":
                # Pipeline already done — run immediately
                callback_name = getattr(callback, "__name__", str(callback))
                logger.info(
                    f"Pipeline already complete, running callback: {callback_name}"
                )
                callback()
            elif self._v7_pipeline_status == "failed":
                logger.warning(
                    "Pipeline failed — skipping callback. "
                    f"Error: {self._v7_pipeline_error}"
                )
            else:
                # Pipeline still running — queue for later
                self._v7_post_pipeline_callbacks.append(callback)
                logger.info(
                    f"Queued post-pipeline callback "
                    f"({len(self._v7_post_pipeline_callbacks)} pending)"
                )

    @property
    def v7_pipeline_status(self) -> str:
        """Status of the background v7 pipeline: idle, running, completed, failed."""
        return self._v7_pipeline_status

    @property
    def v7_pipeline_ready(self) -> bool:
        """Whether the v7 collection is fully indexed and ready for search."""
        return self._v7_pipeline_status in ("completed", "idle")

    def _ensure_collection_for_indexing(self):
        """Ensure a temporary collection for component indexing (v7 path).

        When using v7 schema, we still need _ensure_collection for the
        IndexingMixin to load/index components, but we don't want it to
        be the final collection. Use the legacy collection as a staging area.
        """
        self._ensure_collection()
        self.ensure_symbol_index()

    def _load_existing_components_v7(self, collection_name: str):
        """Load components from an existing v7 collection."""
        from adapters.module_wrapper.indexing_mixin import IndexingMixin

        # Use the same scroll-based loading as IndexingMixin
        logger.info(f"Loading components from v7 collection {collection_name}...")

        all_points = []
        offset = None

        while True:
            results = self.client.scroll(
                collection_name=collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points, next_offset = results
            all_points.extend(points)

            if next_offset is None:
                break
            offset = next_offset

        # Build components dict from payloads
        from adapters.module_wrapper.core import ModuleComponent

        for point in all_points:
            payload = point.payload or {}
            name = payload.get("name", "")
            if not name:
                continue

            full_path = payload.get("full_path", name)
            component = ModuleComponent(
                name=name,
                obj=self._resolve_obj_from_payload(payload),
                module_path=payload.get("module_path", ""),
                component_type=payload.get("type", "unknown"),
                docstring=payload.get("docstring", ""),
                source=payload.get("source", ""),
                parent=None,
            )
            self.components[full_path] = component

        logger.info(f"Loaded {len(all_points)} components from v7 collection")

        # Trigger lazy symbol generation from loaded components
        if self.components:
            _ = self.symbol_mapping

    def _resolve_obj_from_payload(self, payload: dict):
        """Try to resolve the actual class/object from a payload's module path."""
        import importlib

        name = payload.get("name", "")
        module_path = payload.get("module_path", "")

        if not module_path or not name:
            return None

        try:
            mod = importlib.import_module(module_path)
            return getattr(mod, name, None)
        except (ImportError, AttributeError):
            return None

    def validate_dependencies(self, strict: bool = False) -> list[str]:
        """Validate mixin dependency contracts.

        Args:
            strict: If True, raise RuntimeError on any issue.

        Returns:
            List of issue descriptions. Empty = all good.
        """
        from adapters.module_wrapper.mixin_meta import (
            check_runtime_dependencies,
            validate_mixin_dependencies,
        )

        # Static check (MRO-level)
        issues = validate_mixin_dependencies(type(self))

        # Runtime check (attribute-level)
        issues.extend(check_runtime_dependencies(self))

        if issues:
            msg = f"ModuleWrapper dependency issues:\n" + "\n".join(
                f"  - {i}" for i in issues
            )
            if strict:
                raise RuntimeError(msg)
            else:
                logger.warning(msg)

        return issues


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
    # RIC provider system
    "RICTextProvider",
    "IntrospectionProvider",
    # Relationship strategies & tool graph
    "RelationshipStrategy",
    "StructuralRelationshipStrategy",
    "BehavioralRelationshipStrategy",
    "ToolRelationshipGraph",
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
    "_get_rustworkx",
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
    # Mixin dependency contracts
    "MixinContract",
    "validate_mixin_dependencies",
    "check_runtime_dependencies",
    "generate_mermaid_dependency_graph",
    "generate_provides_requires_table",
    "get_all_contracts",
    "requires_deps",
]

__version__ = "2.0.0"
