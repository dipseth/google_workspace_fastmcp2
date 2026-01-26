"""
Core Module Wrapper Classes

This module contains the fundamental classes for the module wrapper system:
- ModuleComponent: Represents a component within a module
- ModuleWrapperBase: Base class with essential module introspection

The full ModuleWrapper is assembled by combining mixins from other modules
in this package.
"""

import importlib
import inspect
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Union
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default relationship extraction depth
DEFAULT_RELATIONSHIP_DEPTH = 5

# Primitive types to skip during relationship extraction
PRIMITIVE_TYPES = {str, int, float, bool, bytes, type(None)}

# Built-in module prefixes to skip
BUILTIN_PREFIXES = {"builtins", "typing", "collections", "abc"}


def parse_qdrant_url(url: str) -> Dict[str, Union[str, int, bool]]:
    """
    Parse a Qdrant URL into components.

    Args:
        url: Qdrant URL (e.g., "https://host:port" or "http://host:port")

    Returns:
        Dictionary with host, port, use_https, and url components
    """
    if not url:
        return {"host": "localhost", "port": 6333, "use_https": False, "url": None}

    try:
        parsed = urlparse(url)

        # Extract host
        host = (
            parsed.hostname or parsed.netloc.split(":")[0]
            if ":" in parsed.netloc
            else parsed.netloc
        )
        if not host and url.startswith(("http://", "https://")):
            no_protocol = url.split("://", 1)[1] if "://" in url else url
            if ":" in no_protocol:
                host, port_str = no_protocol.split(":", 1)
                try:
                    port = int(port_str)
                except ValueError:
                    port = 6333
            else:
                host = no_protocol
                port = 6333
        else:
            port = parsed.port or 6333

        use_https = parsed.scheme == "https" or (
            parsed.scheme == "" and "https://" in url
        )

        return {
            "host": host or "localhost",
            "port": port,
            "use_https": use_https,
            "url": url,
        }
    except Exception as e:
        logger.warning(f"Failed to parse Qdrant URL '{url}': {e}. Using defaults.")
        return {"host": "localhost", "port": 6333, "use_https": False, "url": url}


def get_qdrant_config_from_env() -> Dict[str, Union[str, int, bool, None]]:
    """
    Get Qdrant configuration from centralized settings.

    Returns:
        Dictionary with Qdrant configuration
    """
    try:
        from config.settings import settings

        config = {
            "host": settings.qdrant_host,
            "port": settings.qdrant_port,
            "use_https": settings.qdrant_url and settings.qdrant_url.startswith("https://"),
            "api_key": settings.qdrant_api_key,
            "url": settings.qdrant_url,
            "prefer_grpc": settings.qdrant_prefer_grpc,
        }
        return config

    except ImportError:
        # Fallback to direct environment variable reading
        logger.warning("Could not import settings, using direct env vars")

        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_key = os.getenv("QDRANT_KEY") or os.getenv("QDRANT_API_KEY")

        if qdrant_url:
            config = parse_qdrant_url(qdrant_url)
            config["api_key"] = qdrant_key
            return config
        else:
            return {
                "host": os.getenv("QDRANT_HOST", "localhost"),
                "port": int(os.getenv("QDRANT_PORT", "6333")),
                "use_https": os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true",
                "api_key": qdrant_key,
                "url": None,
            }


# =============================================================================
# MODULE COMPONENT
# =============================================================================

class ModuleComponent:
    """
    Represents a component (class, function, variable) within a module.

    This is the fundamental unit that gets indexed and searched.
    """

    def __init__(
        self,
        name: str,
        obj: Any,
        module_path: str,
        component_type: str,
        docstring: str = "",
        source: str = "",
        parent: Optional["ModuleComponent"] = None,
    ):
        """
        Initialize a module component.

        Args:
            name: Name of the component
            obj: The actual object
            module_path: Full import path of the module
            component_type: Type of component (class, function, variable)
            docstring: Component's docstring
            source: Source code of the component
            parent: Parent component (for nested components)
        """
        self.name = name
        self.obj = obj
        self.module_path = module_path
        self.component_type = component_type
        self.docstring = docstring
        self.source = source
        self.parent = parent
        self.children: Dict[str, "ModuleComponent"] = {}

    @property
    def full_path(self) -> str:
        """Get the full import path to this component."""
        if self.parent:
            return f"{self.parent.full_path}.{self.name}"
        return f"{self.module_path}.{self.name}"

    def add_child(self, child: "ModuleComponent"):
        """Add a child component."""
        self.children[child.name] = child

    def get_child(self, name: str) -> Optional["ModuleComponent"]:
        """Get a child component by name."""
        return self.children.get(name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "name": self.name,
            "type": self.component_type,
            "module_path": self.module_path,
            "full_path": self.full_path,
            "docstring": self.docstring,
            "source": self.source[:1000] if self.source else "",
            "has_children": len(self.children) > 0,
            "child_names": list(self.children.keys()),
        }

    def __repr__(self) -> str:
        return f"<ModuleComponent {self.full_path} ({self.component_type})>"


# =============================================================================
# MODULE WRAPPER BASE
# =============================================================================

class ModuleWrapperBase:
    """
    Base class for module wrapping with essential module introspection.

    This class handles:
    - Module resolution and loading
    - Component extraction
    - Basic Qdrant client initialization

    Subclasses or mixins add:
    - Symbol generation
    - DSL parsing
    - Relationship extraction
    - Search capabilities
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
        auto_initialize: bool = False,
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
        Initialize the module wrapper base.

        Args:
            module_or_name: The module object or its name
            qdrant_host: Qdrant server hostname
            qdrant_port: Qdrant server port
            qdrant_url: Full Qdrant URL
            qdrant_api_key: API key for Qdrant
            collection_name: Name of the Qdrant collection
            embedding_model: Model for generating embeddings
            index_nested: Whether to index nested components
            index_private: Whether to index private components
            max_depth: Maximum recursion depth for submodules
            auto_initialize: Whether to auto-initialize on construction
            skip_standard_library: Whether to skip stdlib modules
            include_modules: Whitelist of module prefixes to include
            exclude_modules: Blacklist of module prefixes to exclude
            force_reindex: Force re-indexing even if data exists
            clear_collection: Clear collection before indexing
            enable_colbert: Enable ColBERT multi-vector embeddings
            colbert_model: ColBERT model to use
            colbert_collection_name: Separate collection for ColBERT
        """
        # Get Qdrant configuration
        env_config = get_qdrant_config_from_env()

        # Override with explicit parameters
        if qdrant_url:
            url_config = parse_qdrant_url(qdrant_url)
            self.qdrant_host = url_config["host"]
            self.qdrant_port = url_config["port"]
            self.qdrant_use_https = url_config["use_https"]
            self.qdrant_url = qdrant_url
        else:
            self.qdrant_host = qdrant_host if qdrant_host is not None else env_config["host"]
            self.qdrant_port = qdrant_port if qdrant_port is not None else env_config["port"]
            self.qdrant_use_https = env_config.get("use_https", False)
            self.qdrant_url = env_config.get("url")

        self.qdrant_prefer_grpc = env_config.get("prefer_grpc", True)
        self.qdrant_api_key = qdrant_api_key if qdrant_api_key is not None else env_config.get("api_key")

        # Store configuration
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model
        self.index_nested = index_nested
        self.index_private = index_private
        self.max_depth = max_depth
        self.skip_standard_library = skip_standard_library
        self.include_modules = include_modules or []
        self.exclude_modules = exclude_modules or []
        self.force_reindex = force_reindex
        self.clear_collection = clear_collection

        # ColBERT configuration
        self.enable_colbert = enable_colbert
        self.colbert_model_name = colbert_model
        self.colbert_collection_name = colbert_collection_name or f"{collection_name}_colbert"
        self.colbert_embedder = None
        self.colbert_embedding_dim = 128
        self._colbert_initialized = False

        # v7 schema detection
        self.use_v7_schema = collection_name.endswith("_v7") or collection_name.endswith("v7")
        self.relationships_embedder = None
        self.relationships_embedding_dim = 384

        # Initialize state
        self.module = self._resolve_module(module_or_name)
        self._module_name = self.module.__name__
        self.components: Dict[str, ModuleComponent] = {}
        self.root_components: Dict[str, ModuleComponent] = {}
        self.client = None
        self.embedder = None
        self.embedding_dim = None
        self._initialized = False
        self._visited_modules: Set[str] = set()
        self._current_depth = 0
        self.collection_needs_indexing = True

        # Symbol mappings (lazy-loaded)
        self._symbol_mapping: Optional[Dict[str, str]] = None
        self._reverse_symbol_mapping: Optional[Dict[str, str]] = None

        # Relationship cache (lazy-loaded)
        self._cached_relationships: Optional[Dict[str, List[str]]] = None

        # DSL metadata cache
        self._dsl_metadata_cache: Optional[Dict[str, Any]] = None

        if auto_initialize:
            self.initialize()

    @property
    def module_name(self) -> str:
        """Get the base module name without version suffix."""
        import re
        base_name = re.sub(r"\.v\d+$", "", self._module_name)
        return base_name

    def _resolve_module(self, module_or_name: Union[str, Any]) -> Any:
        """Resolve a module from its name or object."""
        if isinstance(module_or_name, str):
            try:
                return importlib.import_module(module_or_name)
            except ImportError as e:
                raise ValueError(f"Could not import module {module_or_name}: {e}")
        else:
            return module_or_name

    def initialize(self):
        """Initialize the wrapper. Override in subclass for full initialization."""
        logger.info(f"Initializing ModuleWrapperBase for {self.module_name}...")
        self._initialized = True

    # =========================================================================
    # SYMBOL MAPPING PROPERTIES
    # =========================================================================

    @property
    def symbol_mapping(self) -> Dict[str, str]:
        """Get the persistent symbol mapping: component → symbol."""
        if self._symbol_mapping is None:
            self._symbol_mapping = self.generate_component_symbols(use_prefix=False)
        return self._symbol_mapping

    @property
    def reverse_symbol_mapping(self) -> Dict[str, str]:
        """Get reverse symbol mapping: symbol → component."""
        if self._reverse_symbol_mapping is None:
            self._reverse_symbol_mapping = {v: k for k, v in self.symbol_mapping.items()}
        return self._reverse_symbol_mapping

    def generate_component_symbols(
        self,
        module_prefix: Optional[str] = None,
        custom_overrides: Optional[Dict[str, str]] = None,
        use_prefix: bool = False,
    ) -> Dict[str, str]:
        """
        Generate unique Unicode symbols for all class components.

        Args:
            module_prefix: Optional module identifier for multi-module support
            custom_overrides: Optional dict of component_name → symbol overrides
            use_prefix: If True, adds module prefix to symbols

        Returns:
            Dict mapping component names to their symbols
        """
        from adapters.module_wrapper.symbol_generator import SymbolGenerator

        prefix = (module_prefix or self.module_name) if use_prefix else None

        component_names = [
            comp.name for comp in self.components.values()
            if comp.component_type == "class"
        ]

        priority_scores = self._calculate_symbol_priority_scores()

        generator = SymbolGenerator(
            module_prefix=prefix,
            custom_symbols=custom_overrides,
        )
        symbols = generator.generate_symbols(
            component_names,
            priority_scores=priority_scores,
        )

        logger.info(f"Generated {len(symbols)} symbols for {self.module_name}")
        return symbols

    def _calculate_symbol_priority_scores(self) -> Dict[str, int]:
        """Calculate symbol priority scores based on hierarchy."""
        priority_scores: Dict[str, int] = {}

        try:
            relationships = self.extract_relationships_by_parent(max_depth=3)

            for parent_name, children in relationships.items():
                unique_children = set(c.get("child_class", "") for c in children if c.get("child_class"))
                max_depth = max((c.get("depth", 1) for c in children), default=1)

                score = len(unique_children) * 10 + max_depth

                if parent_name in {"Section", "Card", "ButtonList", "Grid", "Columns", "ChipList"}:
                    score += 100

                priority_scores[parent_name] = score

        except Exception as e:
            logger.debug(f"Could not calculate priority scores: {e}")

        return priority_scores

    # =========================================================================
    # RELATIONSHIP PROPERTIES
    # =========================================================================

    @property
    def relationships(self) -> Dict[str, List[str]]:
        """Get cached relationships grouped by parent component."""
        if self._cached_relationships is None:
            raw_rels = self.extract_relationships_by_parent(max_depth=5)
            self._cached_relationships = {
                parent: [r["child_class"] for r in children]
                for parent, children in raw_rels.items()
            }
        return self._cached_relationships

    def extract_relationships_by_parent(
        self,
        max_depth: int = DEFAULT_RELATIONSHIP_DEPTH,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract parent-child relationships for all components.

        Override in subclass for full implementation.

        Args:
            max_depth: Maximum depth to traverse

        Returns:
            Dict mapping parent_name → [child_info dicts]
        """
        # Base implementation returns empty - override in full ModuleWrapper
        return {}

    # =========================================================================
    # COMPONENT ACCESS
    # =========================================================================

    def get_component_by_path(self, path: str) -> Optional[Any]:
        """
        Get a component's object by its full path.

        Args:
            path: Full path like "module.submodule.ClassName"

        Returns:
            The component object or None
        """
        if path in self.components:
            return self.components[path].obj

        # Try to resolve from module
        parts = path.split(".")
        obj = self.module

        try:
            for part in parts:
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                else:
                    return None
            return obj
        except Exception:
            return None

    def get_symbol_for_component(self, component_name: str) -> Optional[str]:
        """Get the symbol for a component."""
        return self.symbol_mapping.get(component_name)

    def get_component_for_symbol(self, symbol: str) -> Optional[str]:
        """Get the component name for a symbol."""
        return self.reverse_symbol_mapping.get(symbol)

    # =========================================================================
    # DSL SUPPORT
    # =========================================================================

    def get_structure_validator(self):
        """Get a StructureValidator for this module."""
        from adapters.module_wrapper.structure_validator import StructureValidator
        return StructureValidator(self)

    def validate_structure(self, structure: str):
        """Validate a DSL structure string."""
        validator = self.get_structure_validator()
        return validator.validate_structure(structure)

    def get_dsl_parser(self):
        """Get a DSL parser configured for this module."""
        from adapters.module_wrapper.dsl_parser import DSLParser
        return DSLParser(wrapper=self)

    def parse_dsl(self, dsl_string: str):
        """Parse a DSL string and return structured result."""
        parser = self.get_dsl_parser()
        return parser.parse(dsl_string)

    @property
    def dsl_metadata(self) -> Dict[str, Any]:
        """Get complete DSL metadata."""
        if self._dsl_metadata_cache is None:
            self._dsl_metadata_cache = self._derive_dsl_metadata()
        return self._dsl_metadata_cache

    def _derive_dsl_metadata(self) -> Dict[str, Any]:
        """Derive DSL metadata from relationships."""
        rels = self.relationships
        symbols = self.symbol_mapping

        containers = set(rels.keys())

        child_to_parents: Dict[str, List[str]] = {}
        for parent, children in rels.items():
            for child in children:
                if child not in child_to_parents:
                    child_to_parents[child] = []
                child_to_parents[child].append(parent)

        items = set()
        item_to_container: Dict[str, str] = {}

        wrapper_patterns = [
            ("ButtonList", "Button"),
            ("ChipList", "Chip"),
            ("SelectionInput", "SelectionItem"),
            ("Grid", "GridItem"),
            ("Columns", "Column"),
        ]

        for container, item in wrapper_patterns:
            if container in containers:
                items.add(item)
                item_to_container[item] = container

        return {
            "symbols": symbols,
            "reverse_symbols": self.reverse_symbol_mapping,
            "grammar": {
                "section": "§[widgets...]",
                "container": "ContainerSymbol[items...]",
                "repeat": "symbol×count",
                "nesting": "Parent[Child[...]]",
            },
            "containers": containers,
            "items": items,
            "item_to_container": item_to_container,
            "symbol_count": len(symbols),
            "module": self.module_name,
        }

    # =========================================================================
    # CACHE INVALIDATION
    # =========================================================================

    def invalidate_caches(self):
        """Invalidate all cached data."""
        self._symbol_mapping = None
        self._reverse_symbol_mapping = None
        self._cached_relationships = None
        self._dsl_metadata_cache = None
        logger.info("Caches invalidated")
