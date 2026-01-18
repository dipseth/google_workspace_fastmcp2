"""
Module Wrapper with Qdrant Integration

This module provides a wrapper for Python modules that makes their components
searchable using Qdrant vector database. It allows for semantic search of module
components (classes, functions, variables) and retrieval by path.
"""

import hashlib
import importlib
import inspect
import logging
import sys

from config.enhanced_logging import setup_logger

logger = setup_logger()
import asyncio
import os
from datetime import UTC, datetime
from urllib.parse import urlparse

from typing_extensions import Any, Dict, List, Optional, Union

from config.enhanced_logging import setup_logger

logger = setup_logger()


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

        # Extract host (remove protocol prefix if it exists)
        host = (
            parsed.hostname or parsed.netloc.split(":")[0]
            if ":" in parsed.netloc
            else parsed.netloc
        )
        if not host and url.startswith(("http://", "https://")):
            # If parsing failed but URL has protocol, try to extract manually
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
            # Use parsed port or default
            port = parsed.port or 6333

        # Determine if HTTPS should be used
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
    Get Qdrant configuration from centralized settings (which reads environment variables).

    Returns:
        Dictionary with Qdrant configuration from centralized settings
    """
    try:
        # Import settings to get centralized configuration
        # Use try/except to avoid circular imports in some contexts
        from config.settings import settings

        config = {
            "host": settings.qdrant_host,
            "port": settings.qdrant_port,
            "use_https": settings.qdrant_url
            and settings.qdrant_url.startswith("https://"),
            "api_key": settings.qdrant_api_key,
            "url": settings.qdrant_url,
        }

        if settings.qdrant_url:
            logger.info(
                f"Using Qdrant config from settings (env): {settings.qdrant_url} (API Key: {'***' if settings.qdrant_api_key else 'None'})"
            )
        else:
            logger.info(
                f"Using Qdrant config from settings: {settings.qdrant_host}:{settings.qdrant_port} (HTTPS: {config['use_https']}, API Key: {'***' if settings.qdrant_api_key else 'None'})"
            )

        return config

    except ImportError:
        # Fallback to direct environment variable reading if settings can't be imported
        logger.warning(
            "Could not import settings, falling back to direct environment variable reading"
        )

        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_key = os.getenv("QDRANT_KEY") or os.getenv("QDRANT_API_KEY")

        if qdrant_url:
            # Parse URL for host, port, https
            config = parse_qdrant_url(qdrant_url)
            config["api_key"] = qdrant_key
            logger.info(
                f"Using Qdrant config from QDRANT_URL: {config['host']}:{config['port']} (HTTPS: {config['use_https']}, API Key: {'***' if qdrant_key else 'None'})"
            )
            return config
        else:
            # Fall back to individual environment variables or defaults
            host = os.getenv("QDRANT_HOST", "localhost")
            port = int(os.getenv("QDRANT_PORT", "6333"))
            use_https = os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true"

            config = {
                "host": host,
                "port": port,
                "use_https": use_https,
                "api_key": qdrant_key,
                "url": None,
            }
            logger.info(
                f"Using Qdrant config from individual env vars: {host}:{port} (HTTPS: {use_https}, API Key: {'***' if qdrant_key else 'None'})"
            )
            return config


# Global variables for lazy-loaded imports
_qdrant_client = None
_qdrant_models = None
_fastembed = None
_numpy = None


def _get_numpy():
    """Lazy load numpy to avoid import errors during startup."""
    global _numpy
    if _numpy is None:
        try:
            import numpy as np

            _numpy = np
            logger.debug("📦 NumPy loaded successfully")
        except ImportError as e:
            logger.warning(f"⚠️ NumPy not available: {e}")
            _numpy = False
    return _numpy if _numpy is not False else None


def _get_qdrant_imports():
    """Lazy load Qdrant imports when first needed."""
    global _qdrant_client, _qdrant_models
    if _qdrant_client is None:
        logger.info("🔗 Loading Qdrant client (first use)...")
        from qdrant_client import QdrantClient, models
        from qdrant_client.models import Distance, PointStruct, VectorParams

        _qdrant_client = QdrantClient
        _qdrant_models = {
            "models": models,
            "Distance": Distance,
            "VectorParams": VectorParams,
            "PointStruct": PointStruct,
        }
        logger.info("✅ Qdrant client loaded")
    return _qdrant_client, _qdrant_models


def _get_fastembed():
    """Lazy load FastEmbed when first needed."""
    global _fastembed
    if _fastembed is None:
        logger.info("🤖 Loading FastEmbed (first use)...")
        from fastembed import TextEmbedding

        _fastembed = TextEmbedding
        logger.info("✅ FastEmbed loaded")
    return _fastembed


# Global variable for ColBERT lazy loading
_colbert_embed = None


def _get_colbert_embed():
    """Lazy load ColBERT LateInteractionTextEmbedding when first needed."""
    global _colbert_embed
    if _colbert_embed is None:
        logger.info("🤖 Loading ColBERT LateInteractionTextEmbedding (first use)...")
        from fastembed import LateInteractionTextEmbedding

        _colbert_embed = LateInteractionTextEmbedding
        logger.info("✅ ColBERT LateInteractionTextEmbedding loaded")
    return _colbert_embed


class ModuleComponent:
    """
    Represents a component (class, function, variable) within a module.
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
        self.children = {}

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
            "source": self.source[:1000] if self.source else "",  # Limit source size
            "has_children": len(self.children) > 0,
            "child_names": list(self.children.keys()),
        }

    def __repr__(self) -> str:
        return f"<ModuleComponent {self.full_path} ({self.component_type})>"


class ModuleWrapper:
    """
    Wraps a module and makes its components searchable via Qdrant.
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
        max_depth: int = 2,  # Maximum recursion depth for submodules
        auto_initialize: bool = True,
        skip_standard_library: bool = True,  # Whether to skip standard library modules
        include_modules: Optional[
            List[str]
        ] = None,  # List of module prefixes to include (whitelist)
        exclude_modules: Optional[
            List[str]
        ] = None,  # List of module prefixes to exclude (blacklist)
        force_reindex: bool = False,  # Force re-indexing even if collection has data
        clear_collection: bool = False,  # Clear collection before indexing to ensure clean state
        enable_colbert: bool = False,  # Enable ColBERT multi-vector embeddings
        colbert_model: str = "colbert-ir/colbertv2.0",  # ColBERT model to use
        colbert_collection_name: Optional[
            str
        ] = None,  # Separate collection for ColBERT (default: {collection_name}_colbert)
    ):
        """
        Initialize the module wrapper.

        Args:
            module_or_name: The module object or its name (string)
            qdrant_host: Qdrant server hostname (overrides environment variables)
            qdrant_port: Qdrant server port (overrides environment variables)
            qdrant_url: Full Qdrant URL (e.g., https://cluster-url:6333) - if provided, overrides host/port
            qdrant_api_key: API key for Qdrant authentication (for cloud instances)
            collection_name: Name of the Qdrant collection to use
            embedding_model: Model to use for generating embeddings
            index_nested: Whether to index nested components (e.g., methods in classes)
            index_private: Whether to index private components (starting with _)
            max_depth: Maximum recursion depth for submodules (0 = no recursion, 1 = direct submodules only, etc.)
            auto_initialize: Whether to automatically initialize and index
            skip_standard_library: Whether to skip standard library modules during indexing
            include_modules: List of module prefixes to include (whitelist). If provided, only modules with these
                             prefixes will be indexed. For example, ['card_framework', 'gchat'] would only index
                             modules that start with 'card_framework.' or 'gchat.'.
            exclude_modules: List of module prefixes to exclude (blacklist). If provided, modules with these
                             prefixes will be skipped. For example, ['numpy', 'pandas'] would skip all modules
                             that start with 'numpy.' or 'pandas.'.
            force_reindex: If True, force re-indexing even if the collection already has data. Useful for
                          updating the index after module changes. Default is False for performance.
            clear_collection: If True, delete and recreate the collection before indexing. This ensures
                            a completely clean state and removes all duplicates. Use with caution.
            enable_colbert: If True, enable ColBERT multi-vector embeddings for more accurate semantic search.
                           ColBERT creates token-level embeddings instead of a single document vector.
            colbert_model: ColBERT model to use. Options: 'colbert-ir/colbertv2.0' (128-dim),
                          'answerdotai/answerai-colbert-small-v1' (96-dim, multilingual).
            colbert_collection_name: Name of the Qdrant collection for ColBERT multi-vectors.
                                    Defaults to '{collection_name}_colbert' if not specified.
        """
        # Get Qdrant configuration from environment variables first
        env_config = get_qdrant_config_from_env()

        # Override with any explicitly provided parameters
        if qdrant_url:
            # Parse provided URL
            url_config = parse_qdrant_url(qdrant_url)
            self.qdrant_host = url_config["host"]
            self.qdrant_port = url_config["port"]
            self.qdrant_use_https = url_config["use_https"]
            self.qdrant_url = qdrant_url
        else:
            # Use explicit host/port if provided, otherwise use environment config
            self.qdrant_host = (
                qdrant_host if qdrant_host is not None else env_config["host"]
            )
            self.qdrant_port = (
                qdrant_port if qdrant_port is not None else env_config["port"]
            )
            self.qdrant_use_https = env_config.get("use_https", False)
            self.qdrant_url = env_config.get("url")

        # API key: use explicit parameter first, then environment
        self.qdrant_api_key = (
            qdrant_api_key if qdrant_api_key is not None else env_config.get("api_key")
        )

        # Store other configuration
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
        self.colbert_collection_name = (
            colbert_collection_name or f"{collection_name}_colbert"
        )
        self.colbert_embedder = None
        self.colbert_embedding_dim = 128  # Default for colbert-ir/colbertv2.0
        self._colbert_initialized = False

        # Initialize state
        self.module = self._resolve_module(module_or_name)
        self._module_name = self.module.__name__
        self.components = {}
        self.root_components = {}
        self.client = None
        self.embedder = None
        self.embedding_dim = None
        self._initialized = False
        self._visited_modules = set()  # Track visited modules to prevent recursion
        self._current_depth = 0  # Track current recursion depth
        self.collection_needs_indexing = (
            True  # Flag to track if collection needs indexing
        )

        # Auto-initialize if requested
        if auto_initialize:
            self.initialize()

    @property
    def module_name(self) -> str:
        """
        Get the base module name without version suffix.

        This property extracts the base module name from any module name with a version suffix
        like ".v1", ".v2", etc. For example, "module.v2" becomes "module".

        Returns:
            The base module name
        """
        # Extract base module name using regex to match version patterns
        import re

        base_name = re.sub(r"\.v\d+$", "", self._module_name)
        return base_name

    def _resolve_module(self, module_or_name: Union[str, Any]) -> Any:
        """
        Resolve a module from its name or object.

        Args:
            module_or_name: Module object or name

        Returns:
            The module object
        """
        if isinstance(module_or_name, str):
            try:
                return importlib.import_module(module_or_name)
            except ImportError as e:
                raise ValueError(f"Could not import module {module_or_name}: {e}")
        else:
            # Assume it's already a module
            return module_or_name

    def initialize(self):
        """Initialize the wrapper and index the module components."""
        try:
            logger.info(f"🚀 Initializing ModuleWrapper for {self.module_name}...")

            # Initialize Qdrant client
            self._initialize_qdrant()

            # Initialize embedding model
            self._initialize_embedder()

            # Ensure collection exists
            self._ensure_collection()

            # Index module components
            self._index_module_components()

            # Initialize ColBERT if enabled
            if self.enable_colbert:
                logger.info(
                    "🤖 ColBERT mode enabled - initializing ColBERT embedder..."
                )
                self._initialize_colbert_embedder()
                self._ensure_colbert_collection()
                self._index_components_colbert()

            self._initialized = True
            logger.info(f"✅ ModuleWrapper initialized for {self.module_name}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize ModuleWrapper: {e}", exc_info=True)
            raise

    def _initialize_qdrant(self):
        """Initialize Qdrant client with support for HTTPS and API key authentication."""
        try:
            QdrantClient, _ = _get_qdrant_imports()

            # Prepare client arguments
            client_args = {}

            if self.qdrant_url:
                # Use URL-based initialization for cloud instances
                client_args["url"] = self.qdrant_url
                if self.qdrant_api_key:
                    client_args["api_key"] = self.qdrant_api_key

                logger.info(
                    f"🌐 Connecting to Qdrant using URL: {self.qdrant_url} (API Key: {'***' if self.qdrant_api_key else 'None'})"
                )
            else:
                # Use host/port initialization for local instances or when URL is not available
                client_args["host"] = self.qdrant_host
                client_args["port"] = self.qdrant_port

                # Add HTTPS support
                if self.qdrant_use_https:
                    client_args["https"] = True

                # Add API key if provided
                if self.qdrant_api_key:
                    client_args["api_key"] = self.qdrant_api_key

                protocol = "https" if self.qdrant_use_https else "http"
                logger.info(
                    f"🌐 Connecting to Qdrant at {protocol}://{self.qdrant_host}:{self.qdrant_port} (API Key: {'***' if self.qdrant_api_key else 'None'})"
                )

            # Create the client
            self.client = QdrantClient(**client_args)

            # Test the connection
            try:
                collections = self.client.get_collections()
                logger.info(
                    f"✅ Connected to Qdrant successfully - found {len(collections.collections)} collections"
                )
            except Exception as test_e:
                logger.warning(
                    f"⚠️ Qdrant connection established but test failed: {test_e}"
                )

        except Exception as e:
            logger.error(f"❌ Failed to initialize Qdrant client: {e}")
            raise

    def _clear_fastembed_cache(self, model_name: str = None) -> bool:
        """
        Clear corrupted FastEmbed cache to allow re-download.

        Args:
            model_name: Optional specific model name to clear (clears all if None)

        Returns:
            bool: True if cache was cleared successfully
        """
        import shutil
        import tempfile
        from pathlib import Path

        cleared = False
        cache_locations = [
            Path(tempfile.gettempdir()) / "fastembed_cache",
            Path.home() / ".cache" / "fastembed",
        ]

        # Also check macOS-specific temp locations
        try:
            import os

            # Get the actual temp directory which may be in /var/folders on macOS
            actual_temp = Path(os.path.realpath(tempfile.gettempdir()))
            if actual_temp not in cache_locations:
                cache_locations.append(actual_temp / "fastembed_cache")
        except Exception:
            pass

        for cache_dir in cache_locations:
            if cache_dir.exists():
                try:
                    if model_name:
                        # Clear specific model cache
                        # Model names like "sentence-transformers/all-MiniLM-L6-v2"
                        # are stored as "models--qdrant--all-MiniLM-L6-v2-onnx"
                        model_short = model_name.split("/")[-1]
                        for subdir in cache_dir.iterdir():
                            if model_short in subdir.name or "MiniLM" in subdir.name:
                                logger.info(f"🗑️ Clearing corrupted cache: {subdir}")
                                shutil.rmtree(subdir)
                                cleared = True
                    else:
                        # Clear entire cache
                        logger.info(f"🗑️ Clearing entire FastEmbed cache: {cache_dir}")
                        shutil.rmtree(cache_dir)
                        cleared = True
                except Exception as clear_error:
                    logger.warning(
                        f"⚠️ Could not clear cache {cache_dir}: {clear_error}"
                    )

        return cleared

    def _initialize_embedder(self):
        """Initialize the embedding model with retry logic for corrupted cache."""
        max_retries = 2
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                TextEmbedding = _get_fastembed()
                self.embedder = TextEmbedding(model_name=self.embedding_model_name)

                # Try to get embedding dimension dynamically
                try:
                    # Generate a test embedding to get the dimension
                    test_embedding = list(self.embedder.embed(["test"]))[0]
                    self.embedding_dim = (
                        len(test_embedding)
                        if hasattr(test_embedding, "__len__")
                        else 384
                    )
                except Exception:
                    # Fallback to known dimensions for common models
                    model_dims = {
                        "sentence-transformers/all-MiniLM-L6-v2": 384,
                        "sentence-transformers/all-mpnet-base-v2": 768,
                    }
                    self.embedding_dim = model_dims.get(self.embedding_model_name, 384)

                logger.info(
                    f"✅ Embedding model loaded: {self.embedding_model_name} (dim: {self.embedding_dim})"
                )
                return  # Success!

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check if this is a cache/file corruption error that we can recover from
                is_recoverable = any(
                    keyword in error_str
                    for keyword in [
                        "no_suchfile",
                        "file doesn't exist",
                        "corrupted",
                        "model.onnx",
                        "failed to load",
                        "invalid model",
                    ]
                )

                if is_recoverable and attempt < max_retries:
                    logger.warning(
                        f"⚠️ Embedding model load failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    logger.info(
                        "🔄 Attempting to clear corrupted cache and re-download model..."
                    )

                    # Clear the cache and retry
                    if self._clear_fastembed_cache(self.embedding_model_name):
                        logger.info("✅ Cache cleared, retrying model download...")
                        # Reset the global fastembed reference to force reload
                        global _fastembed
                        _fastembed = None
                        continue
                    else:
                        logger.warning("⚠️ Could not clear cache, retrying anyway...")
                        continue
                else:
                    # Non-recoverable error or out of retries
                    break

        # All retries exhausted
        logger.error(
            f"❌ Failed to initialize embedding model after {max_retries + 1} attempts: {last_error}"
        )
        raise last_error

    def _initialize_colbert_embedder(self):
        """Initialize the ColBERT late interaction embedding model."""
        if not self.enable_colbert:
            return

        try:
            LateInteractionTextEmbedding = _get_colbert_embed()
            logger.info(f"🤖 Initializing ColBERT model: {self.colbert_model_name}")
            self.colbert_embedder = LateInteractionTextEmbedding(
                model_name=self.colbert_model_name
            )

            # Get embedding dimension from model
            colbert_dims = {
                "colbert-ir/colbertv2.0": 128,
                "answerdotai/answerai-colbert-small-v1": 96,
            }
            self.colbert_embedding_dim = colbert_dims.get(self.colbert_model_name, 128)

            logger.info(
                f"✅ ColBERT model loaded: {self.colbert_model_name} (dim: {self.colbert_embedding_dim})"
            )
            self._colbert_initialized = True

        except Exception as e:
            logger.error(f"❌ Failed to initialize ColBERT embedder: {e}")
            self.enable_colbert = False
            raise

    def _ensure_colbert_collection(self):
        """Ensure the Qdrant collection for ColBERT multi-vectors exists."""
        if not self.enable_colbert or not self._colbert_initialized:
            return

        try:
            _, qdrant_models = _get_qdrant_imports()

            # Check if ColBERT collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.colbert_collection_name in collection_names:
                logger.info(
                    f"✅ ColBERT collection '{self.colbert_collection_name}' exists"
                )
                # Check if it has data
                collection_info = self.client.get_collection(
                    self.colbert_collection_name
                )
                if collection_info.points_count > 0:
                    logger.info(
                        f"📊 ColBERT collection has {collection_info.points_count} points"
                    )
                return

            # Create ColBERT collection with multi-vector configuration
            logger.info(
                f"📦 Creating ColBERT collection: {self.colbert_collection_name}"
            )

            # For ColBERT, we use multi-vector storage
            # Each document produces multiple vectors (one per token)
            self.client.create_collection(
                collection_name=self.colbert_collection_name,
                vectors_config={
                    "colbert": qdrant_models["VectorParams"](
                        size=self.colbert_embedding_dim,
                        distance=qdrant_models["Distance"].COSINE,
                        multivector_config=qdrant_models["models"].MultiVectorConfig(
                            comparator=qdrant_models[
                                "models"
                            ].MultiVectorComparator.MAX_SIM
                        ),
                    )
                },
            )
            logger.info(
                f"✅ ColBERT collection created: {self.colbert_collection_name}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to ensure ColBERT collection: {e}")
            raise

    def _ensure_collection(self):
        """Ensure the Qdrant collection exists and check if it needs indexing."""
        try:
            _, qdrant_models = _get_qdrant_imports()

            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            self.collection_needs_indexing = True  # Default to needing indexing

            # Handle clear_collection flag
            if self.clear_collection and self.collection_name in collection_names:
                logger.warning(
                    f"🗑️ Clearing collection {self.collection_name} as requested..."
                )
                self.client.delete_collection(collection_name=self.collection_name)
                collection_names.remove(self.collection_name)
                logger.info(f"✅ Collection {self.collection_name} cleared")

            if self.collection_name not in collection_names:
                # Create collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qdrant_models["VectorParams"](
                        size=self.embedding_dim,
                        distance=qdrant_models["Distance"].COSINE,
                    ),
                )
                logger.info(f"✅ Created Qdrant collection: {self.collection_name}")
                self.collection_needs_indexing = True
            else:
                # Check if collection has data
                collection_info = self.client.get_collection(self.collection_name)
                point_count = collection_info.points_count

                if self.force_reindex:
                    logger.info(
                        f"✅ Using existing collection: {self.collection_name} ({point_count} points) - Force re-indexing enabled"
                    )
                    self.collection_needs_indexing = True
                elif point_count > 0:
                    logger.info(
                        f"✅ Using existing collection: {self.collection_name} ({point_count} points) - Skipping indexing"
                    )
                    self.collection_needs_indexing = False
                else:
                    logger.info(
                        f"✅ Using existing collection: {self.collection_name} (empty)"
                    )
                    self.collection_needs_indexing = True

        except Exception as e:
            logger.error(f"❌ Failed to ensure collection exists: {e}")
            raise

    def _load_components_from_collection(self):
        """Load components from existing Qdrant collection into memory."""
        try:
            logger.info(
                f"📥 Loading existing components from collection {self.collection_name}..."
            )

            # Scroll through all points in the collection
            offset = None
            loaded_count = 0

            while True:
                # Fetch a batch of points
                scroll_result = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,  # We don't need vectors for loading
                )

                points, next_offset = scroll_result

                if not points:
                    break

                # Process each point
                for point in points:
                    payload = point.payload
                    if not payload:
                        continue

                    # Extract component information
                    path = payload.get("full_path")
                    if not path:
                        continue

                    name = payload.get("name", "")
                    module_path = payload.get("module_path", self.module_name)
                    component_type = payload.get("type", "variable")
                    docstring = payload.get("docstring", "")
                    source = payload.get("source", "")

                    # Try to resolve the actual object from the path
                    obj = None
                    try:
                        # Split path and traverse to get the actual object
                        parts = path.split(".")

                        # Qdrant stores `full_path` like:
                        #   card_framework.v2.card.CardWithId
                        # but this wrapper's `self.module` is *root* `card_framework`.
                        # So we must drop the root module name and traverse the remainder.
                        if parts and parts[0] == self.module_name:
                            parts = parts[1:]

                        # Handle when wrapper was constructed for a submodule (e.g. `card_framework.v2`)
                        # but `self.module` is already that submodule. In that case, drop the submodule
                        # prefix from parts too.
                        if self._module_name and self._module_name.startswith(
                            self.module_name + "."
                        ):
                            subparts = self._module_name.split(".")[1:]
                            if parts[: len(subparts)] == subparts:
                                parts = parts[len(subparts) :]

                        # Start with the module
                        obj = self.module

                        # Traverse the path, handling lazy-loaded submodules
                        for part in parts:
                            try:
                                obj = getattr(obj, part)
                            except AttributeError:
                                # Some packages don't eagerly expose submodules on the parent
                                # (e.g. `card_framework` doesn't have `v2` until imported).
                                module_candidate = (
                                    f"{getattr(obj, '__name__', '')}.{part}".lstrip(".")
                                )
                                try:
                                    obj = importlib.import_module(module_candidate)
                                except (ImportError, ModuleNotFoundError):
                                    # Not a module, re-raise the original AttributeError
                                    raise AttributeError(
                                        f"'{type(obj).__name__}' has no attribute '{part}'"
                                    )

                    except (AttributeError, IndexError) as e:
                        # Could not resolve object, it will remain None
                        logger.debug(f"Could not resolve object for path: {path} ({e})")
                        obj = None

                    # Create component object
                    component = ModuleComponent(
                        name=name,
                        obj=obj,  # May be None if couldn't resolve
                        module_path=module_path,
                        component_type=component_type,
                        docstring=docstring,
                        source=source,
                        parent=None,  # We don't reconstruct parent relationships
                    )

                    # Store in components dictionary
                    self.components[path] = component
                    loaded_count += 1

                # Move to next batch
                offset = next_offset
                if offset is None:
                    break

            logger.info(f"✅ Loaded {loaded_count} components from collection")

        except Exception as e:
            logger.error(
                f"❌ Failed to load components from collection: {e}", exc_info=True
            )
            # Don't raise - continue with empty components if loading fails

    def _index_module_components(self):
        """Index all components in the module."""
        try:
            # Check if indexing is needed
            if not getattr(self, "collection_needs_indexing", True):
                logger.info(
                    f"⏩ Skipping indexing for module {self.module_name} - collection already has data"
                )
                # Load existing components from collection instead
                self._load_components_from_collection()
                return

            logger.info(
                f"🔍 Indexing components in module {self.module_name} (max depth: {self.max_depth})..."
            )

            # Reset visited modules and depth counter
            self._visited_modules = set()
            self._current_depth = 0

            # Add the main module to visited modules
            self._visited_modules.add(self.module.__name__)

            # Get all module components
            for name, obj in inspect.getmembers(self.module):
                # Skip private members if not indexing them
                if name.startswith("_") and not self.index_private:
                    continue

                # Skip standard library modules at root level if configured
                if (
                    inspect.ismodule(obj)
                    and hasattr(obj, "__name__")
                    and not self._should_include_module(obj.__name__, 0)
                ):
                    logger.debug(
                        f"Skipping module {obj.__name__} at root level based on configuration"
                    )
                    continue

                # Create component
                component = self._create_component(name, obj, self.module_name)

                # Store in root components
                self.root_components[name] = component

                # Store in flat components dictionary
                self.components[component.full_path] = component

                # Index nested components if requested
                if self.index_nested:
                    self._index_nested_components(component)

                    # If this is a module and we haven't reached max depth, recursively index its components
                    if (
                        inspect.ismodule(obj)
                        and obj.__name__ not in self._visited_modules
                        and self._current_depth < self.max_depth
                    ):
                        # Only index modules that should be included based on configuration
                        if hasattr(obj, "__name__") and self._should_include_module(
                            obj.__name__, 1
                        ):
                            self._index_submodule(name, obj)

            # Special handling for widgets modules (generalized)
            if hasattr(self.module, "widgets"):
                logger.info(
                    f"🔍 Special handling for {self.module_name}.widgets module..."
                )
                try:
                    # Try to directly access the widgets module
                    widgets_module = getattr(self.module, "widgets")
                    if inspect.ismodule(widgets_module):
                        logger.info(f"Found widgets module: {widgets_module.__name__}")
                        # Index the widgets module directly
                        self._index_widgets_module(widgets_module)
                except Exception as e:
                    logger.warning(f"Error accessing widgets module: {e}")

            # Store components in Qdrant
            self._store_components_in_qdrant()

            logger.info(
                f"✅ Indexed {len(self.components)} components in module {self.module_name}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to index module components: {e}", exc_info=True)
            raise

    def _index_widgets_module(self, widgets_module):
        """
        Special indexing for widgets modules.

        Args:
            widgets_module: The widgets module to index
        """
        logger.info(f"🔍 Indexing widgets module: {widgets_module.__name__}")
        try:
            # Get all widget components
            for name, obj in inspect.getmembers(widgets_module):
                # Skip private members if not indexing them
                if name.startswith("_") and not self.index_private:
                    continue

                # Skip objects that should be skipped
                if self._should_skip_object(name, obj):
                    continue

                # Create component
                component = self._create_component(name, obj, self.module_name)

                # Store in flat components dictionary with special path
                # Use module_name.widgets.name to ensure it's found by search
                component_path = f"{self.module_name}.widgets.{name}"
                self.components[component_path] = component

                logger.info(f"Added widget component: {component_path}")

                # Index nested components if requested
                if self.index_nested and component.component_type == "class":
                    try:
                        self._index_nested_components(component)
                    except Exception as e:
                        logger.debug(
                            f"Error indexing nested components for widget {name}: {e}"
                        )
        except Exception as e:
            logger.warning(f"Error indexing widgets module: {e}")

    def _is_standard_library(self, module_name: str) -> bool:
        """
        Check if a module is part of the Python standard library.

        Args:
            module_name: Name of the module

        Returns:
            True if the module is part of the standard library, False otherwise
        """
        # Common standard library modules to skip
        std_lib_prefixes = [
            "builtins",
            "collections",
            "typing",
            "types",
            "functools",
            "itertools",
            "operator",
            "re",
            "os",
            "sys",
            "json",
            "datetime",
            "time",
            "random",
            "math",
            "inspect",
            "ast",
            "copy",
            "abc",
            "enum",
            "importlib",
            "pathlib",
            "io",
            "warnings",
            "uuid",
            "logging",
            "email",
            "zipfile",
            "textwrap",
            "posixpath",
            "token",
            "tokenize",
            "keyword",
            "linecache",
            "dis",
            "socket",
            "selectors",
            "select",
            "ssl",
            "http",
            "urllib",
            "base64",
            "struct",
            "bisect",
            "contextlib",
            "hashlib",
            "tempfile",
            "quopri",
            "binascii",
            "stat",
            "ipaddress",
            "copyreg",
            "errno",
            "array",
            "codecs",
            "decimal",
            "numbers",
            "uuid",
            "threading",
            "zlib",
            "bz2",
            "lzma",
            "shutil",
            "fnmatch",
            "posix",
            "string",
        ]

        # Check if module name starts with any standard library prefix
        for prefix in std_lib_prefixes:
            if module_name == prefix or module_name.startswith(f"{prefix}."):
                return True

        # Check if it's a third-party library (not card_framework)
        third_party_prefixes = [
            "numpy",
            "pandas",
            "matplotlib",
            "scipy",
            "sklearn",
            "tensorflow",
            "torch",
            "keras",
            "django",
            "flask",
            "requests",
            "bs4",
            "selenium",
            "sqlalchemy",
            "pytest",
            "unittest",
            "nose",
            "marshmallow",
            "dataclasses_json",
            "stringcase",
            "qdrant_client",
            "sentence_transformers",
        ]

        for prefix in third_party_prefixes:
            if module_name == prefix or module_name.startswith(f"{prefix}."):
                return True

        return False

    def _should_include_module(self, module_name: str, current_depth: int) -> bool:
        """
        Determine if a module should be included in indexing based on configuration.

        Args:
            module_name: Name of the module
            current_depth: Current recursion depth

        Returns:
            True if the module should be included, False otherwise
        """
        # Skip standard library modules if configured
        if self.skip_standard_library and self._is_standard_library(module_name):
            logger.debug(f"Skipping standard library module {module_name}")
            return False

        # If include_modules is provided, only include modules with these prefixes
        if self.include_modules:
            for prefix in self.include_modules:
                if module_name == prefix or module_name.startswith(f"{prefix}."):
                    # Module is in the whitelist
                    break
            else:
                # Module is not in the whitelist
                logger.debug(f"Skipping module {module_name} (not in include list)")
                return False

        # If exclude_modules is provided, skip modules with these prefixes
        if self.exclude_modules:
            for prefix in self.exclude_modules:
                if module_name == prefix or module_name.startswith(f"{prefix}."):
                    # Module is in the blacklist
                    logger.debug(f"Skipping module {module_name} (in exclude list)")
                    return False

        return True

    def _index_submodule(self, name: str, submodule: Any):
        """
        Recursively index a submodule's components.

        Args:
            name: Name of the submodule
            submodule: The submodule object
        """
        try:
            # Skip if already visited to prevent infinite recursion
            try:
                if (
                    not hasattr(submodule, "__name__")
                    or submodule.__name__ in self._visited_modules
                ):
                    return
            except Exception as e:
                logger.warning(f"Error checking submodule name: {e}")
                return

            # Mark as visited
            try:
                self._visited_modules.add(submodule.__name__)
            except Exception as e:
                logger.warning(f"Error adding submodule to visited set: {e}")
                return

            # Increment depth counter
            self._current_depth += 1
            current_depth = self._current_depth

            # Ensure we don't exceed max depth
            if current_depth > self.max_depth:
                logger.debug(
                    f"Maximum depth reached ({current_depth} > {self.max_depth}), skipping submodule {name}"
                )
                self._current_depth -= 1
                return

            # Check if module should be included based on configuration
            try:
                if hasattr(submodule, "__name__"):
                    module_name = submodule.__name__

                    if not self._should_include_module(module_name, current_depth):
                        logger.debug(
                            f"Skipping module {module_name} at depth {current_depth} based on configuration"
                        )
                        self._current_depth -= 1
                        return
            except Exception as e:
                logger.debug(f"Error checking if module should be included: {e}")

            try:
                logger.info(
                    f"🔍 Recursively indexing submodule {submodule.__name__} (depth: {current_depth}/{self.max_depth})..."
                )
            except Exception:
                logger.info(
                    f"🔍 Recursively indexing unnamed submodule (depth: {current_depth}/{self.max_depth})..."
                )

            # Get all submodule components safely
            try:
                members = inspect.getmembers(submodule)
            except Exception as e:
                logger.warning(f"Error getting members of submodule: {e}")
                members = []

            # Process each member
            for sub_name, sub_obj in members:
                try:
                    # Skip private members if not indexing them
                    if sub_name.startswith("_") and not self.index_private:
                        continue

                    # Skip problematic objects
                    if self._should_skip_object(sub_name, sub_obj):
                        continue

                    # Create component
                    component = self._create_component(
                        sub_name, sub_obj, getattr(submodule, "__name__", name)
                    )

                    # Store in flat components dictionary
                    self.components[component.full_path] = component

                    # Index nested components if requested
                    if self.index_nested:
                        try:
                            self._index_nested_components(component)
                        except Exception as e:
                            logger.debug(
                                f"Error indexing nested components for {sub_name}: {e}"
                            )

                        # Recursively index submodules if we haven't reached max depth
                        try:
                            is_module = inspect.ismodule(sub_obj)
                            not_visited = (
                                hasattr(sub_obj, "__name__")
                                and sub_obj.__name__ not in self._visited_modules
                            )
                            within_depth = current_depth < self.max_depth

                            # Check if submodule should be included
                            should_include = True
                            if hasattr(sub_obj, "__name__"):
                                should_include = self._should_include_module(
                                    sub_obj.__name__, current_depth + 1
                                )

                            should_recurse = (
                                is_module
                                and not_visited
                                and within_depth
                                and should_include
                            )

                            if should_recurse:
                                self._index_submodule(sub_name, sub_obj)
                        except Exception as e:
                            logger.debug(
                                f"Error checking if {sub_name} is a module: {e}"
                            )
                except Exception as e:
                    logger.debug(f"Error processing submodule member {sub_name}: {e}")

        except Exception as e:
            logger.warning(f"Error indexing submodule {name}: {e}")
        finally:
            # Always decrement depth counter when returning from recursion
            self._current_depth -= 1

    def _should_skip_object(self, name: str, obj: Any) -> bool:
        """
        Determine if an object should be skipped during indexing.

        Args:
            name: Name of the object
            obj: The actual object

        Returns:
            True if the object should be skipped, False otherwise
        """
        try:
            # Skip typing module generics
            if str(type(obj)).startswith("<class 'typing."):
                return True

            # Skip built-in types
            if isinstance(obj, type) and obj.__module__ == "builtins":
                return True

            # Skip method descriptors and built-in functions
            if type(obj).__name__ in (
                "method_descriptor",
                "builtin_function_or_method",
                "getset_descriptor",
                "wrapper_descriptor",
            ):
                return True

            # Skip objects with problematic __repr__ methods
            if hasattr(obj, "__repr__"):
                try:
                    repr(obj)
                except Exception:
                    return True

            # Skip objects with problematic __str__ methods
            if hasattr(obj, "__str__"):
                try:
                    str(obj)
                except Exception:
                    return True

            # Skip objects with problematic __dict__ attributes
            if hasattr(obj, "__dict__"):
                try:
                    obj.__dict__
                except Exception:
                    return True

            # Skip objects with problematic __dir__ methods
            if hasattr(obj, "__dir__"):
                try:
                    dir(obj)
                except Exception:
                    return True

            # Skip objects with problematic __module__ attributes
            if hasattr(obj, "__module__"):
                try:
                    obj.__module__
                except Exception:
                    return True

            # Skip objects with problematic __name__ attributes
            if hasattr(obj, "__name__"):
                try:
                    obj.__name__
                except Exception:
                    return True

            # Skip objects with problematic __class__ attributes
            if hasattr(obj, "__class__"):
                try:
                    obj.__class__
                except Exception:
                    return True

            # Skip objects with problematic __call__ methods
            if hasattr(obj, "__call__"):
                try:
                    callable(obj)
                except Exception:
                    return True

            return False

        except Exception:
            # If any error occurs during the checks, skip the object
            return True

    def _create_component(
        self,
        name: str,
        obj: Any,
        module_path: str,
        parent: Optional[ModuleComponent] = None,
    ) -> ModuleComponent:
        """
        Create a component object.

        Args:
            name: Name of the component
            obj: The actual object
            module_path: Module path
            parent: Parent component

        Returns:
            ModuleComponent object
        """
        try:
            # Skip objects that should be skipped
            if self._should_skip_object(name, obj):
                logger.debug(f"Skipping object {name} of type {type(obj)}")
                # Return a minimal component for skipped objects
                return ModuleComponent(
                    name=name,
                    obj=None,  # Don't store the actual object to avoid issues
                    module_path=module_path,
                    component_type="skipped",
                    docstring="",
                    source="",
                    parent=parent,
                )

            # Determine component type safely
            component_type = "variable"  # Default type
            try:
                if inspect.isclass(obj):
                    component_type = "class"
                elif inspect.isfunction(obj):
                    component_type = "function"
                elif inspect.ismethod(obj):
                    component_type = "method"
                elif inspect.ismodule(obj):
                    component_type = "module"
            except Exception as e:
                logger.debug(f"Error determining component type for {name}: {e}")
                # Keep the default "variable" type

            # Get docstring safely
            docstring = ""
            try:
                docstring = inspect.getdoc(obj) or ""
            except Exception as e:
                logger.debug(f"Error getting docstring for {name}: {e}")

            # Get source code if possible
            source = ""
            try:
                if callable(obj) or inspect.isclass(obj):
                    source = inspect.getsource(obj)
            except Exception as e:
                # Can't get source for some objects
                logger.debug(f"Could not get source for {name}: {e}")

            # Create component
            component = ModuleComponent(
                name=name,
                obj=obj,
                module_path=module_path,
                component_type=component_type,
                docstring=docstring,
                source=source,
                parent=parent,
            )

            return component

        except Exception as e:
            # If any error occurs, return a minimal component
            logger.warning(f"Error creating component for {name}: {e}")
            return ModuleComponent(
                name=name,
                obj=None,  # Don't store the actual object to avoid issues
                module_path=module_path,
                component_type="error",
                docstring=f"Error: {str(e)}",
                source="",
                parent=parent,
            )

    def _index_nested_components(self, parent: ModuleComponent):
        """
        Index nested components (methods, attributes) of a class.

        Args:
            parent: Parent component (usually a class)
        """
        try:
            # Only index nested components for classes
            if parent.component_type != "class":
                return

            # Skip if parent object is None (was skipped during creation)
            if parent.obj is None:
                return

            # Get all members of the class safely
            try:
                members = inspect.getmembers(parent.obj)
            except Exception as e:
                logger.debug(f"Error getting members of class {parent.name}: {e}")
                return

            # Process each member
            for name, obj in members:
                try:
                    # Skip private members if not indexing them
                    if name.startswith("_") and not self.index_private:
                        continue

                    # Skip problematic objects
                    if self._should_skip_object(name, obj):
                        continue

                    # Create component
                    component = self._create_component(
                        name=name,
                        obj=obj,
                        module_path=parent.module_path,
                        parent=parent,
                    )

                    # Add to parent
                    parent.add_child(component)

                    # Store in flat components dictionary
                    self.components[component.full_path] = component
                except Exception as e:
                    logger.debug(f"Error processing class member {name}: {e}")
        except Exception as e:
            logger.warning(f"Error indexing nested components for {parent.name}: {e}")

    def _store_components_in_qdrant(self):
        """Store all components in Qdrant with deterministic IDs to prevent duplicates."""
        try:
            component_count = len(self.components)
            logger.info(f"💾 Storing {component_count} components in Qdrant...")

            # Get Qdrant imports
            _, qdrant_models = _get_qdrant_imports()

            # Generate a version identifier for this indexing run
            # This helps track when components were last indexed
            index_version = datetime.now(UTC).isoformat()

            # Use smaller batch size for better performance
            batch_size = 50

            # Process components in smaller batches to avoid memory issues
            processed = 0
            for batch_idx, batch_items in enumerate(
                self._batch_items(self.components.items(), batch_size)
            ):
                # Create points for this batch
                points = []
                for path, component in batch_items:
                    # Generate text for embedding
                    embed_text = self._generate_embedding_text(component)

                    # Generate embedding using FastEmbed
                    embedding_list = list(self.embedder.embed([embed_text]))
                    embedding = embedding_list[0] if embedding_list else None

                    if embedding is None:
                        logger.warning(
                            f"Failed to generate embedding for component: {path}"
                        )
                        continue

                    # Create deterministic ID based on collection name and component path
                    # This ensures the same component always gets the same ID
                    # Format as a valid UUID v4 (8-4-4-4-12 format with dashes)
                    id_string = f"{self.collection_name}:{path}"
                    hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
                    # Format as UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
                    component_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

                    # Create point with minimal payload and version info
                    # Convert numpy array to list if needed
                    if hasattr(embedding, "tolist"):
                        vector_list = embedding.tolist()
                    else:
                        vector_list = list(embedding)

                    # Add version info to payload
                    payload = component.to_dict()
                    payload["indexed_at"] = index_version
                    payload["module_version"] = getattr(
                        self.module, "__version__", "unknown"
                    )

                    point = qdrant_models["PointStruct"](
                        id=component_id,  # Use deterministic ID
                        vector=vector_list,
                        payload=payload,
                    )

                    points.append(point)

                # Store this batch in Qdrant (upsert will replace existing points with same ID)
                self.client.upsert(collection_name=self.collection_name, points=points)

                processed += len(points)
                logger.info(
                    f"📦 Stored batch {batch_idx+1} ({processed}/{component_count} components)"
                )

            logger.info(
                f"✅ Stored {processed} components in Qdrant (duplicates replaced)"
            )

        except Exception as e:
            logger.error(f"❌ Failed to store components in Qdrant: {e}", exc_info=True)
            raise

    def _batch_items(self, items, batch_size):
        """Helper method to batch items for processing."""
        batch = []
        for item in items:
            batch.append(item)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _generate_embedding_text(self, component: ModuleComponent) -> str:
        """
        Generate minimal text for embedding a component.

        Args:
            component: The component to generate text for

        Returns:
            Text for embedding
        """
        # Build minimal text with only essential component information
        text_parts = [
            f"Name: {component.name}",
            f"Type: {component.component_type}",
            f"Path: {component.full_path}",
        ]

        # Add only the first line of the docstring if available
        if component.docstring:
            first_line = component.docstring.split("\n")[0]
            text_parts.append(f"Documentation: {first_line}")

        # Skip source code and child information to reduce embedding size

        return "\n".join(text_parts)

    def _index_components_colbert(self):
        """Index components using ColBERT multi-vector embeddings."""
        if not self.enable_colbert or not self._colbert_initialized:
            logger.warning(
                "⚠️ ColBERT not enabled or initialized, skipping ColBERT indexing"
            )
            return

        try:
            _, qdrant_models = _get_qdrant_imports()

            # Check if collection already has data
            collection_info = self.client.get_collection(self.colbert_collection_name)
            if collection_info.points_count > 0 and not self.force_reindex:
                logger.info(
                    f"📊 ColBERT collection already has {collection_info.points_count} points, skipping indexing"
                )
                return

            logger.info(
                f"🔄 Indexing {len(self.components)} components with ColBERT embeddings..."
            )

            # Index version for tracking
            index_version = datetime.now(UTC).isoformat()

            # Process components in batches
            batch_size = 10  # Smaller batches for ColBERT (more memory intensive)
            processed = 0

            for batch_idx, batch_items in enumerate(
                self._batch_items(list(self.components.items()), batch_size)
            ):
                points = []
                for path, component in batch_items:
                    # Generate text for embedding
                    embed_text = self._generate_embedding_text(component)

                    # Generate ColBERT multi-vector embedding
                    # ColBERT returns a list of vectors (one per token)
                    try:
                        embedding_result = list(
                            self.colbert_embedder.embed([embed_text])
                        )
                        if not embedding_result:
                            logger.warning(
                                f"Failed to generate ColBERT embedding for: {path}"
                            )
                            continue

                        # ColBERT returns a matrix (num_tokens x embedding_dim)
                        multi_vector = embedding_result[0]

                        # Convert to list format if needed
                        if hasattr(multi_vector, "tolist"):
                            vector_list = multi_vector.tolist()
                        else:
                            vector_list = [list(v) for v in multi_vector]

                    except Exception as embed_error:
                        logger.warning(
                            f"ColBERT embedding failed for {path}: {embed_error}"
                        )
                        continue

                    # Create deterministic ID
                    id_string = f"{self.colbert_collection_name}:{path}"
                    hash_hex = hashlib.sha256(id_string.encode()).hexdigest()
                    component_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

                    # Add payload
                    payload = component.to_dict()
                    payload["indexed_at"] = index_version
                    payload["module_version"] = getattr(
                        self.module, "__version__", "unknown"
                    )
                    payload["embedding_type"] = "colbert"

                    point = qdrant_models["PointStruct"](
                        id=component_id,
                        vector={"colbert": vector_list},
                        payload=payload,
                    )
                    points.append(point)

                # Store batch in Qdrant
                if points:
                    self.client.upsert(
                        collection_name=self.colbert_collection_name, points=points
                    )
                    processed += len(points)
                    logger.info(
                        f"📦 ColBERT batch {batch_idx+1}: stored {len(points)} components ({processed} total)"
                    )

            logger.info(f"✅ ColBERT indexing complete: {processed} components indexed")

        except Exception as e:
            logger.error(
                f"❌ Failed to index components with ColBERT: {e}", exc_info=True
            )
            raise

    def colbert_search(
        self, query: str, limit: int = 5, score_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Search for components using ColBERT multi-vector embeddings.

        ColBERT uses late interaction (MaxSim) for more accurate semantic matching.
        The query is embedded as multiple vectors (one per token) and compared
        against document vectors using maximum similarity scoring.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            score_threshold: Minimum similarity score

        Returns:
            List of matching components with their paths and scores
        """
        if not self._initialized:
            raise RuntimeError("ModuleWrapper not initialized")

        if not self.enable_colbert or not self._colbert_initialized:
            logger.warning("⚠️ ColBERT not enabled, falling back to standard search")
            return self.search(query, limit, score_threshold)

        try:
            logger.info(f"🔍 ColBERT search for: '{query}'")

            # Generate ColBERT query embedding using query_embed (optimized for queries)
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
                logger.info(f"✅ ColBERT search found {len(points)} results")

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
            logger.error(f"❌ ColBERT search failed: {e}", exc_info=True)
            # Fall back to standard search
            logger.info("⚠️ Falling back to standard search")
            return self.search(query, limit, score_threshold)

    def _get_component_from_path(self, path: str) -> Any:
        """Get component object from its path."""
        if path in self.components:
            component = self.components[path]
            return component.obj if hasattr(component, "obj") else None
        return None

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
            # Try direct lookup first for exact component name matches
            direct_results = self._direct_component_lookup(query)
            if direct_results:
                logger.info(
                    f"Found {len(direct_results)} direct matches for '{query}' (async)"
                )
                return direct_results

            # Generate embedding for the query using FastEmbed
            embedding_list = await asyncio.to_thread(
                lambda q: list(self.embedder.embed([q])), query
            )
            query_embedding = embedding_list[0] if embedding_list else None

            if query_embedding is None:
                logger.error(f"Failed to generate embedding for query: {query}")
                return []

            # Search in Qdrant (prefer the newer `query_points` API)
            # Convert embedding to list format
            if hasattr(query_embedding, "tolist"):
                query_vector = query_embedding.tolist()
            else:
                query_vector = list(query_embedding)

            # Search in Qdrant using the modern API (qdrant-client >= 1.16)
            # NOTE: This repo currently uses qdrant-client 1.16.2 where `QdrantClient.search` does not exist.
            search_results = await asyncio.to_thread(
                self.client.query_points,
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
            )

            # Log the search results structure for debugging
            logger.info(f"Async query points result type: {type(search_results)}")
            # QueryResponse object doesn't have len(), so we need to check its attributes
            logger.info(f"Async QueryResponse attributes: {dir(search_results)}")

            # Get the actual points from the QueryResponse
            points = []
            if hasattr(search_results, "points"):
                points = search_results.points
                logger.info(f"Found {len(points)} points in async search results")
            else:
                # Fallback: try to iterate over search_results directly
                try:
                    points = list(search_results)
                    logger.info(
                        f"Async fallback: Found {len(points)} results by direct iteration"
                    )
                except Exception as e:
                    logger.warning(
                        f"Could not extract points from async search results: {e}"
                    )
                    return []

            # Process results - properly handle Qdrant ScoredPoint objects (async)
            results = []
            for result in points:
                # Handle Qdrant ScoredPoint objects (the correct structure)
                try:
                    # Try to get score and payload from ScoredPoint object
                    score = float(getattr(result, "score", 0.9))
                    payload = getattr(result, "payload", {})

                    # Log for debugging
                    logger.info(
                        f"Async ScoredPoint - Score: {score}, Payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'not dict'}"
                    )

                except (AttributeError, ValueError, TypeError) as e:
                    logger.warning(f"Error processing async ScoredPoint object: {e}")
                    # Fall back to tuple handling if needed
                    if isinstance(result, tuple):
                        logger.info(
                            f"Async falling back to tuple handling for: {result}"
                        )
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
                        # Default values if we can't extract anything
                        logger.warning(
                            f"Async could not extract score/payload from result: {type(result)}"
                        )
                        score = 0.9
                        payload = {}

                # Handle different payload structures
                if isinstance(payload, dict):
                    # Prefer module_path + name as canonical identifier when present.
                    # This is more reliable than legacy/bad full_path values stored in Qdrant.
                    module_path = payload.get("module_path")
                    name = payload.get("name")

                    canonical_path = None
                    if module_path and name:
                        canonical_path = f"{module_path}.{name}"

                    path = canonical_path or payload.get("full_path")
                    type_info = payload.get("type")
                    docstring = payload.get("docstring")
                elif isinstance(payload, list) and len(payload) > 0:
                    # If payload is a list, try to use the first item or create empty values
                    path = str(payload[0]) if len(payload) > 0 else ""
                    name = str(payload[1]) if len(payload) > 1 else ""
                    type_info = str(payload[2]) if len(payload) > 2 else ""
                    docstring = str(payload[3]) if len(payload) > 3 else ""
                    module_path = None
                else:
                    # Default values if payload is neither dict nor list
                    path = str(payload) if payload else ""
                    name = ""
                    type_info = ""
                    docstring = ""
                    module_path = None

                # Get the actual component - try full_path first (what's stored in components dict),
                # then fall back to canonical path, then try runtime resolution
                full_path = (
                    payload.get("full_path") if isinstance(payload, dict) else None
                )
                component = None
                component_obj = None

                # Strategy 1: Look up by full_path (the key used in self.components)
                if full_path:
                    component = self.components.get(full_path)
                    if component and component.obj is not None:
                        component_obj = component.obj

                # Strategy 2: Look up by canonical path
                if component_obj is None and path:
                    component = self.components.get(path)
                    if component and component.obj is not None:
                        component_obj = component.obj

                # Strategy 3: Runtime resolution using get_component_by_path
                if component_obj is None and full_path:
                    component_obj = self.get_component_by_path(full_path)

                results.append(
                    {
                        "score": score,
                        "name": name,
                        "path": path,
                        "full_path": full_path,
                        "module_path": (
                            module_path if isinstance(payload, dict) else None
                        ),
                        "type": type_info,
                        "docstring": docstring,
                        "component": component_obj,
                    }
                )

            return results

        except Exception as e:
            logger.error(f"❌ Search failed: {e}", exc_info=True)
            raise

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

            # Generate embedding for the query using FastEmbed
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

            # Search in Qdrant using query_points (new API)
            search_results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
            )

            # Log the search results structure for debugging
            logger.info(f"Query points result type: {type(search_results)}")
            # QueryResponse object doesn't have len(), so we need to check its attributes
            logger.info(f"QueryResponse attributes: {dir(search_results)}")

            # Get the actual points from the QueryResponse
            points = []
            if hasattr(search_results, "points"):
                points = search_results.points
                logger.info(f"Found {len(points)} points in search results")
            else:
                # Fallback: try to iterate over search_results directly
                try:
                    points = list(search_results)
                    logger.info(
                        f"Fallback: Found {len(points)} results by direct iteration"
                    )
                except Exception as e:
                    logger.warning(f"Could not extract points from search results: {e}")
                    return []

            # Process results - properly handle Qdrant ScoredPoint objects
            results = []
            for result in points:
                # Handle Qdrant ScoredPoint objects (the correct structure)
                try:
                    # Try to get score and payload from ScoredPoint object
                    score = float(getattr(result, "score", 0.9))
                    payload = getattr(result, "payload", {})

                    # Log for debugging
                    logger.info(
                        f"ScoredPoint - Score: {score}, Payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'not dict'}"
                    )

                except (AttributeError, ValueError, TypeError) as e:
                    logger.warning(f"Error processing ScoredPoint object: {e}")
                    # Fall back to tuple handling if needed
                    if isinstance(result, tuple):
                        logger.info(f"Falling back to tuple handling for: {result}")
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
                        # Default values if we can't extract anything
                        logger.warning(
                            f"Could not extract score/payload from result: {type(result)}"
                        )
                        score = 0.9
                        payload = {}

                # Handle different payload structures
                if isinstance(payload, dict):
                    # Prefer module_path + name as canonical identifier when present.
                    # This is more reliable than legacy/bad full_path values stored in Qdrant.
                    module_path = payload.get("module_path")
                    name = payload.get("name")

                    canonical_path = None
                    if module_path and name:
                        canonical_path = f"{module_path}.{name}"

                    path = canonical_path or payload.get("full_path")
                    type_info = payload.get("type")
                    docstring = payload.get("docstring")
                elif isinstance(payload, list) and len(payload) > 0:
                    # If payload is a list, try to use the first item or create empty values
                    path = str(payload[0]) if len(payload) > 0 else ""
                    name = str(payload[1]) if len(payload) > 1 else ""
                    type_info = str(payload[2]) if len(payload) > 2 else ""
                    docstring = str(payload[3]) if len(payload) > 3 else ""
                    module_path = None
                else:
                    # Default values if payload is neither dict nor list
                    path = str(payload) if payload else ""
                    name = ""
                    type_info = ""
                    docstring = ""
                    module_path = None

                # Get the actual component - try full_path first (what's stored in components dict),
                # then fall back to canonical path, then try runtime resolution
                full_path = (
                    payload.get("full_path") if isinstance(payload, dict) else None
                )
                component = None
                component_obj = None

                # Strategy 1: Look up by full_path (the key used in self.components)
                if full_path:
                    component = self.components.get(full_path)
                    if component and component.obj is not None:
                        component_obj = component.obj

                # Strategy 2: Look up by canonical path
                if component_obj is None and path:
                    component = self.components.get(path)
                    if component and component.obj is not None:
                        component_obj = component.obj

                # Strategy 3: Runtime resolution using get_component_by_path
                if component_obj is None and full_path:
                    component_obj = self.get_component_by_path(full_path)

                results.append(
                    {
                        "score": score,
                        "name": name,
                        "path": path,
                        "full_path": full_path,
                        "module_path": (
                            module_path if isinstance(payload, dict) else None
                        ),
                        "type": type_info,
                        "docstring": docstring,
                        "component": component_obj,
                    }
                )

            return results

        except Exception as e:
            logger.error(f"❌ Search failed: {e}", exc_info=True)
            raise

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
                # Ensure the component object is valid
                if component.obj is not None:
                    results.append(
                        {
                            "score": 1.0,  # Perfect match
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
                    # Ensure the component object is valid
                    if component.obj is not None:
                        results.append(
                            {
                                "score": 0.9,  # High score for case-insensitive match
                                "name": component.name,
                                "path": path,
                                "type": component.component_type,
                                "docstring": component.docstring,
                                "component": component.obj,
                            }
                        )

        # Check for components in widgets module (generalized for any module)
        if not results and hasattr(self.module, "widgets"):
            # Try to find the component in the widgets module
            widgets_path = f"{self.module_name}.widgets.{component_name}"
            component = self.components.get(widgets_path)
            if component and component.obj is not None:
                logger.info(f"Found component in widgets module: {widgets_path}")
                results.append(
                    {
                        "score": 1.0,  # Perfect match
                        "name": component.name,
                        "path": widgets_path,
                        "type": component.component_type,
                        "docstring": component.docstring,
                        "component": component.obj,
                    }
                )

        return results

    def create_card_component(self, card_class, params):
        """
        Helper method to create a card component with proper error handling.

        Args:
            card_class: The card class to instantiate
            params: Parameters to pass to the constructor

        Returns:
            The created card component or None if creation failed
        """
        if card_class is None:
            logger.warning("Cannot create card: card_class is None")
            return None

        try:
            # Check if the class is callable
            if not callable(card_class):
                logger.warning(f"Card class {card_class} is not callable")
                return None

            # Get the signature to filter parameters
            import inspect

            try:
                if inspect.isclass(card_class):
                    sig = inspect.signature(card_class.__init__)
                else:
                    sig = inspect.signature(card_class)

                # Filter parameters to match signature
                valid_params = {}
                for param_name, param in sig.parameters.items():
                    if param_name in params and param_name != "self":
                        valid_params[param_name] = params[param_name]

                # Create the component
                if inspect.isclass(card_class):
                    component = card_class(**valid_params)
                else:
                    component = card_class(**valid_params)

                logger.info(
                    f"Successfully created card component: {type(component).__name__}"
                )
                return component

            except (ValueError, TypeError) as e:
                logger.warning(f"Error getting signature for {card_class}: {e}")
                # Try direct instantiation as fallback
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

    def get_component_by_path(self, path: str) -> Optional[Any]:
        """
        Get a component by its path.

        Args:
            path: Path to the component (e.g., "module.submodule.function")

        Returns:
            The component if found, None otherwise
        """
        # Check if path is in components
        component = self.components.get(path)
        if component and component.obj is not None:
            return component.obj

        # Try to resolve path
        try:
            # Split path into parts
            parts = path.split(".")

            # Normalize paths coming from Qdrant payloads.
            # Example payload full_path: `card_framework.v2.card.CardWithId`
            # But `self.module` is `card_framework`, so drop the root and traverse.
            if parts and parts[0] == self.module_name:
                parts = parts[1:]

            # Some indexes store paths relative to a submodule (e.g. wrapper constructed for
            # `card_framework.v2` but `self.module` is `card_framework`). In that case,
            # drop the explicit submodule prefix too.
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
                    # Some packages don't eagerly expose submodules on the parent package
                    # (e.g. `card_framework` doesn't have attribute `v2` until imported).
                    module_candidate = f"{getattr(obj, '__name__', '')}.{part}".lstrip(
                        "."
                    )
                    try:
                        obj = importlib.import_module(module_candidate)
                    except (ImportError, ModuleNotFoundError):
                        # Not a module, re-raise as AttributeError so outer handler catches it
                        raise AttributeError(
                            f"'{type(obj).__name__}' has no attribute '{part}'"
                        )

            return obj

        except (AttributeError, IndexError):
            logger.warning(f"⚠️ Could not resolve path: {path}")
            return None

    def get_component_info(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a component by its path.

        Args:
            path: Path to the component

        Returns:
            Dictionary with component information
        """
        component = self.components.get(path)
        if component:
            return component.to_dict()
        return None

    def list_components(self, component_type: Optional[str] = None) -> List[str]:
        """
        List all components in the module.

        Args:
            component_type: Optional filter by component type

        Returns:
            List of component paths
        """
        if component_type:
            return [
                path
                for path, component in self.components.items()
                if component.component_type == component_type
            ]
        return list(self.components.keys())

    def get_component_source(self, path: str) -> Optional[str]:
        """
        Get the source code of a component.

        Args:
            path: Path to the component

        Returns:
            Source code if available, None otherwise
        """
        component = self.components.get(path)
        if component and component.source:
            return component.source

        # Try to get source directly
        obj = self.get_component_by_path(path)
        if obj:
            try:
                return inspect.getsource(obj)
            except (TypeError, OSError):
                pass

        return None

    def force_reindex_components(self):
        """
        Force re-indexing of all module components regardless of collection state.

        This method can be used to update the index after module changes or to
        rebuild the index from scratch.
        """
        logger.info(f"🔄 Force re-indexing module {self.module_name}...")

        # Clear existing components
        self.components.clear()
        self.root_components.clear()

        # Force indexing even if collection has data
        self.collection_needs_indexing = True

        # Re-index all components
        self._index_module_components()

        logger.info(f"✅ Force re-indexing completed for {self.module_name}")


# Example usage
if __name__ == "__main__":
    import sys

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Check arguments
    if len(sys.argv) < 2:
        print("Usage: python module_wrapper.py <module_name> [query]")
        sys.exit(1)

    # Get module name from arguments
    module_name = sys.argv[1]

    # Create wrapper
    wrapper = ModuleWrapper(module_name)

    # If query is provided, search for it
    if len(sys.argv) > 2:
        query = sys.argv[2]
        print(f"Searching for: {query}")

        results = wrapper.search(query)

        print(f"Found {len(results)} results:")
        for i, result in enumerate(results):
            print(
                f"{i+1}. {result['path']} ({result['type']}) - Score: {result['score']:.4f}"
            )
            if result["docstring"]:
                print(f"   {result['docstring'][:100]}...")
            print()
    else:
        # List all components
        components = wrapper.list_components()
        print(f"Found {len(components)} components in {module_name}:")
        for i, path in enumerate(sorted(components)):
            component = wrapper.get_component_info(path)
            print(f"{i+1}. {path} ({component['type']})")
