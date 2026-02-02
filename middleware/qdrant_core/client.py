"""
Qdrant Client Management Module

This module contains client connection and management functionality extracted from
the main Qdrant middleware, including:
- Client discovery and connection management
- Model loading and initialization
- Collection management
- Compression utilities

This focused module handles all aspects of Qdrant client lifecycle management
while maintaining async patterns and proper error handling.
"""

import asyncio
import gzip
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config.enhanced_logging import setup_logger

from .config import QdrantConfig
from .lazy_imports import get_fastembed, get_qdrant_imports

logger = setup_logger()

# Global singleton instance for shared Qdrant client usage
_global_client_manager = None  # type: Optional["QdrantClientManager"]


class QdrantClientManager:
    """
    Manages Qdrant client connection, discovery, and initialization.

    This class encapsulates all client management functionality including:
    - Auto-discovery of Qdrant instances across multiple ports
    - Embedding model loading and management
    - Collection creation and management
    - Connection state tracking and initialization
    - Data compression/decompression utilities
    """

    def __init__(
        self,
        config: QdrantConfig,
        qdrant_api_key: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        auto_discovery: bool = True,
        prefer_grpc: bool = True,  # Use gRPC to avoid SSL issues with cloud Qdrant
    ):
        """
        Initialize the Qdrant client manager.

        Args:
            config: QdrantConfig instance with connection settings
            qdrant_api_key: API key for cloud Qdrant authentication
            qdrant_url: Full Qdrant URL (overrides host/port if provided)
            auto_discovery: Whether to auto-discover Qdrant ports
            prefer_grpc: Use gRPC to avoid SSL certificate issues (default True)
        """
        self.config = config
        self.qdrant_api_key = qdrant_api_key
        self.auto_discovery = auto_discovery
        self.prefer_grpc = prefer_grpc

        # Parse URL if provided
        if qdrant_url:
            from urllib.parse import urlparse

            parsed = urlparse(qdrant_url)
            self.qdrant_host = parsed.hostname or config.host
            self.qdrant_port = parsed.port or config.ports[0]
            self.qdrant_url = qdrant_url
            self.qdrant_use_https = parsed.scheme == "https"
            logger.info(
                f"🔧 Parsed Qdrant URL: {qdrant_url} -> host={self.qdrant_host}, port={self.qdrant_port}, https={self.qdrant_use_https}"
            )
        else:
            self.qdrant_host = config.host
            self.qdrant_port = config.ports[0]
            self.qdrant_url = None
            self.qdrant_use_https = False

        # Initialize state
        self.client = None
        self.embedder = None
        self.embedding_dim = None
        self.discovered_url = None
        self._initialized = False

        # Deferred initialization state
        self._init_attempted = False
        self._init_complete = False

        logger.info("🚀 QdrantClientManager created (deferred initialization)")
        if not self.config.enabled:
            logger.warning("⚠️ Qdrant middleware disabled by configuration")

    async def _ensure_initialized(self) -> bool:
        """
        Ensure client manager is initialized on first use (deferred initialization pattern).

        Returns:
            bool: True if initialization succeeded, False otherwise
        """
        if self._init_attempted:
            return self._init_complete

        self._init_attempted = True

        if not self.config.enabled:
            logger.info("⚠️ Qdrant middleware disabled, skipping initialization")
            return False

        try:
            logger.info("🔄 Initializing Qdrant client manager on first use...")

            # Auto-discover Qdrant if enabled
            if self.auto_discovery and not self.client:
                await self._discover_qdrant()
            elif not self.client:
                # Direct connection mode
                await self._connect_direct()

            # Load embedding model
            await self._ensure_model_loaded()

            # Ensure collection exists
            if self.client and self.embedder:
                await self._ensure_collection()

                # Trigger automated cleanup in the background (non-blocking)
                if self.config.cache_retention_days > 0:
                    asyncio.create_task(self._background_cleanup())

                self._initialized = True
                self._init_complete = True
                logger.info("✅ Qdrant client manager initialized successfully")
                return True

        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize Qdrant client manager: {e}")
            self.config.enabled = False
            self.client = None
            self.embedder = None

        return False

    async def initialize(self) -> bool:
        """
        Initialize async components (embedding model, auto-discovery).
        This method can be called explicitly or will be called on first use.

        Returns:
            bool: True if initialization succeeded, False otherwise
        """
        return await self._ensure_initialized()

    async def _connect_direct(self):
        """Connect directly using centralized client or configured host/port/URL."""
        # First, try to use the centralized Qdrant client singleton
        try:
            from config.qdrant_client import get_qdrant_client

            central_client = get_qdrant_client()
            if central_client:
                self.client = central_client
                logger.info("🔗 QdrantClientManager using centralized Qdrant client")
                return
        except Exception as e:
            logger.debug(f"Centralized client not available, creating own: {e}")

        # Fallback: create own client
        QdrantClient, _ = get_qdrant_imports()

        # Use URL if provided, otherwise use host/port
        if self.qdrant_url:
            logger.info(
                f"🔗 Connecting to Qdrant using URL: {self.qdrant_url} (gRPC: {self.prefer_grpc})"
            )
            self.client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
                prefer_grpc=self.prefer_grpc,
            )
        else:
            logger.info(
                f"🔗 Connecting to Qdrant at {self.config.host}:{self.config.ports[0]}"
            )
            self.client = QdrantClient(
                host=self.config.host,
                port=self.config.ports[0],
                api_key=self.qdrant_api_key,
            )

    async def _discover_qdrant(self):
        """Discover working Qdrant instance by trying multiple ports."""
        if self.discovered_url and self.client:
            return

        # First, try to use the centralized Qdrant client singleton
        try:
            from config.qdrant_client import get_qdrant_client
            from config.settings import settings

            central_client = get_qdrant_client()
            if central_client:
                self.client = central_client
                self.discovered_url = (
                    settings.qdrant_url
                    or f"http://{settings.qdrant_host}:{settings.qdrant_port}"
                )
                logger.info(
                    f"✅ Using centralized Qdrant client at {self.discovered_url}"
                )
                return
        except Exception as e:
            logger.debug(f"Centralized client not available for discovery: {e}")

        QdrantClient, _ = get_qdrant_imports()

        # If we have a full URL, try that first
        if self.qdrant_url:
            try:
                logger.info(
                    f"🔍 Trying Qdrant at URL: {self.qdrant_url} (gRPC: {self.prefer_grpc})"
                )
                # Use gRPC to avoid SSL certificate verification issues with cloud instances
                client = QdrantClient(
                    url=self.qdrant_url,
                    api_key=self.qdrant_api_key,
                    timeout=self.config.connection_timeout / 1000,
                    prefer_grpc=self.prefer_grpc,
                )

                # Test connection
                await asyncio.to_thread(client.get_collections)

                self.client = client
                self.discovered_url = self.qdrant_url
                logger.info(f"✅ Connected to Qdrant at {self.discovered_url}")
                return

            except Exception as e:
                logger.warning(f"❌ Failed to connect to URL {self.qdrant_url}: {e}")
                # Fall through to try host/port discovery

        # Try different ports on the configured host
        for port in self.config.ports:
            try:
                logger.info(f"🔍 Trying Qdrant at {self.config.host}:{port}")
                client = QdrantClient(
                    host=self.config.host,
                    port=port,
                    api_key=self.qdrant_api_key,
                    timeout=self.config.connection_timeout / 1000,
                )

                # Test connection
                await asyncio.to_thread(client.get_collections)

                self.client = client
                protocol = "https" if self.qdrant_use_https else "http"
                self.discovered_url = f"{protocol}://{self.config.host}:{port}"
                logger.info(f"✅ Discovered Qdrant at {self.discovered_url}")
                return

            except Exception as e:
                logger.debug(f"❌ Failed to connect to {self.config.host}:{port}: {e}")
                continue

        logger.warning("❌ No working Qdrant instance found")
        self.config.enabled = False

    async def _ensure_model_loaded(self):
        """Load the FastEmbed embedding model if not already loaded."""
        if self.embedder is None:
            try:
                logger.info(
                    f"🤖 Loading FastEmbed model: {self.config.embedding_model}"
                )

                def load_model():
                    TextEmbedding = get_fastembed()
                    return TextEmbedding(model_name=self.config.embedding_model)

                self.embedder = await asyncio.to_thread(load_model)

                # Get embedding dimension by generating a test embedding
                try:
                    test_embedding_list = list(self.embedder.embed(["test"]))
                    test_embedding = (
                        test_embedding_list[0] if test_embedding_list else None
                    )
                    self.embedding_dim = len(test_embedding) if test_embedding else 384
                except Exception:
                    # Fallback to known dimensions for common models
                    model_dims = {
                        "sentence-transformers/all-MiniLM-L6-v2": 384,
                        "sentence-transformers/all-mpnet-base-v2": 768,
                    }
                    self.embedding_dim = model_dims.get(
                        self.config.embedding_model, 384
                    )

                logger.info(f"✅ FastEmbed model loaded (dim: {self.embedding_dim})")

            except Exception as e:
                logger.error(f"❌ Failed to load FastEmbed model: {e}")
                raise RuntimeError(f"Failed to load FastEmbed model: {e}")

    async def _ensure_collection(self):
        """Ensure the Qdrant collection exists with proper configuration and indexes."""
        if not self.client:
            return

        try:
            _, qdrant_models = get_qdrant_imports()

            # Check if collection exists
            collections = await asyncio.to_thread(self.client.get_collections)
            collection_names = [c.name for c in collections.collections]

            if self.config.collection_name not in collection_names:
                # Get optimization parameters based on profile
                optimization_params = self.config.get_optimization_params()

                # Vector configuration based on optimization profile
                vector_config = qdrant_models["VectorParams"](
                    size=self.embedding_dim,
                    distance=getattr(
                        qdrant_models["Distance"], self.config.distance.upper()
                    ),
                    **optimization_params["vector_config"],
                )

                # HNSW configuration based on optimization profile
                hnsw_config = qdrant_models["HnswConfigDiff"](
                    **optimization_params["hnsw_config"]
                )

                # Optimizer configuration based on optimization profile
                optimizer_config = qdrant_models["OptimizersConfigDiff"](
                    **optimization_params["optimizer_config"]
                )

                await asyncio.to_thread(
                    self.client.create_collection,
                    collection_name=self.config.collection_name,
                    vectors_config=vector_config,
                    hnsw_config=hnsw_config,
                    optimizers_config=optimizer_config,
                )

                profile_name = self.config.optimization_profile.value
                description = optimization_params["description"]
                logger.info(
                    f"✅ Created Qdrant collection: {self.config.collection_name}"
                )
                logger.info(f"🚀 Optimization Profile: {profile_name}")
                logger.info(f"📊 Profile Description: {description}")

                # Create keyword indexes for filterable fields using KeywordIndexParams
                filterable_fields = [
                    # Core indexed fields
                    "tool_name",
                    "user_email",
                    "user_id",
                    "session_id",
                    "payload_type",
                    "label",
                    # Additional fields for comprehensive search support
                    "timestamp",
                    "execution_time_ms",
                    "compressed",
                    # Common search aliases
                    "user",
                    "service",
                    "tool",
                    "email",
                    "type",
                ]

                # Create indexes in parallel for faster initialization
                await self._create_indexes_parallel(
                    filterable_fields, qdrant_models, log_prefix="Created"
                )

            else:
                logger.info(
                    f"✅ Using existing collection: {self.config.collection_name}"
                )
                # Check if indexes exist and create them if missing
                try:
                    collection_info = await asyncio.to_thread(
                        self.client.get_collection, self.config.collection_name
                    )

                    # Get existing payload indexes
                    existing_indexes = set()
                    if (
                        hasattr(collection_info, "payload_schema")
                        and collection_info.payload_schema
                    ):
                        existing_indexes = set(collection_info.payload_schema.keys())

                    # Create missing indexes - comprehensive list with KeywordIndexParams
                    filterable_fields = [
                        # Core indexed fields
                        "tool_name",
                        "user_email",
                        "user_id",
                        "session_id",
                        "payload_type",
                        "label",
                        # Additional fields for comprehensive search support
                        "timestamp",
                        "execution_time_ms",
                        "compressed",
                        # Common search aliases
                        "user",
                        "service",
                        "tool",
                        "email",
                        "type",
                    ]
                    # Filter to only missing fields and create in parallel
                    missing_fields = [
                        f for f in filterable_fields if f not in existing_indexes
                    ]
                    if missing_fields:
                        await self._create_indexes_parallel(
                            missing_fields, qdrant_models, log_prefix="Created missing"
                        )
                except Exception as e:
                    logger.warning(f"⚠️ Could not check existing indexes: {e}")

        except Exception as e:
            logger.error(f"❌ Failed to ensure collection exists: {e}")
            raise

    async def _create_indexes_parallel(
        self,
        fields: list,
        qdrant_models: dict,
        log_prefix: str = "Created",
        max_concurrent: int = 5,
    ) -> None:
        """
        Create payload indexes in parallel for faster initialization.

        Args:
            fields: List of field names to index
            qdrant_models: Qdrant models dict with KeywordIndexParams etc.
            log_prefix: Prefix for log messages (e.g., "Created" or "Created missing")
            max_concurrent: Maximum concurrent index creation operations
        """
        if not fields:
            return

        async def create_single_index(field: str) -> tuple[str, bool, str]:
            """Create a single index, return (field, success, error_msg)."""
            try:
                keyword_index = qdrant_models["KeywordIndexParams"](
                    type=qdrant_models["KeywordIndexType"].KEYWORD,
                    on_disk=False,  # Keep frequently accessed fields in memory
                )
                await asyncio.to_thread(
                    self.client.create_payload_index,
                    collection_name=self.config.collection_name,
                    field_name=field,
                    field_schema=keyword_index,
                )
                return (field, True, "")
            except Exception as e:
                return (field, False, str(e))

        # Process in batches to avoid overwhelming the server
        for i in range(0, len(fields), max_concurrent):
            batch = fields[i : i + max_concurrent]
            tasks = [create_single_index(field) for field in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"⚠️ Index creation error: {result}")
                elif isinstance(result, tuple):
                    field, success, error_msg = result
                    if success:
                        logger.info(f"✅ {log_prefix} keyword index for field: {field}")
                    else:
                        logger.warning(
                            f"⚠️ Failed to create index for {field}: {error_msg}"
                        )

    def _should_compress(self, data: str) -> bool:
        """Check if data should be compressed based on size."""
        return len(data.encode("utf-8")) > self.config.compression_threshold

    def _compress_data(self, data: str) -> bytes:
        """Compress data using gzip."""
        return gzip.compress(data.encode("utf-8"))

    def _decompress_data(self, data: bytes) -> str:
        """Decompress gzip-compressed data."""
        return gzip.decompress(data).decode("utf-8")

    def parse_tool_response_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and clean FastMCP tool response payloads by automatically extracting
        and parsing nested JSON strings in the response data.

        FastMCP tool responses have this structure:
        {
            "response_data": {
                "response": [{"type": "text", "text": "{...json_string...}"}]
            }
        }

        This method:
        1. Extracts the JSON string from the nested structure
        2. Parses it into a proper Python dict
        3. Flattens the structure for easier template access
        4. Handles both parsed and unparsed payloads gracefully

        Args:
            payload: Raw payload dict from Qdrant point

        Returns:
            Cleaned payload with parsed response_data
        """
        import json
        from copy import deepcopy

        # Work with a copy to avoid modifying the original
        cleaned_payload = deepcopy(payload)

        try:
            # Check if we have response_data with the FastMCP structure
            response_data = cleaned_payload.get("response_data")
            if not response_data or not isinstance(response_data, dict):
                return cleaned_payload

            # Look for the nested response array
            response_array = response_data.get("response")
            if not response_array or not isinstance(response_array, list):
                return cleaned_payload

            # Extract and parse the text content from the first response item
            for item in response_array:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_content = item.get("text")
                    if text_content and isinstance(text_content, str):
                        try:
                            # Parse the JSON string
                            parsed_content = json.loads(text_content)

                            # Replace the nested structure with the parsed content
                            # Keep the original in case needed for debugging
                            cleaned_payload["response_data_parsed"] = parsed_content
                            cleaned_payload["response_data_raw"] = response_data

                            # Make the parsed data the primary response_data for easy access
                            cleaned_payload["response_data"] = parsed_content

                            logger.debug(
                                f"✅ Parsed nested JSON in response_data for tool: {cleaned_payload.get('tool_name', 'unknown')}"
                            )
                            break

                        except json.JSONDecodeError as e:
                            logger.debug(f"⚠️ Could not parse text content as JSON: {e}")
                            # Keep original structure if parsing fails
                            pass

            return cleaned_payload

        except Exception as e:
            logger.warning(f"⚠️ Error parsing tool response payload: {e}")
            # Return original payload if any error occurs
            return payload

    @property
    def is_initialized(self) -> bool:
        """Check if client manager is fully initialized."""
        return (
            self._initialized and self.client is not None and self.embedder is not None
        )

    @property
    def is_available(self) -> bool:
        """Check if Qdrant client is available and ready."""
        return self.config.enabled and self.client is not None

    async def _background_cleanup(self):
        """
        Perform background cleanup of stale data.
        This runs asynchronously without blocking initialization.
        """
        try:
            logger.info(
                f"🧹 Starting background cleanup (retention: {self.config.cache_retention_days} days)"
            )

            # Import here to avoid circular dependencies
            from .storage import QdrantStorageManager

            # Create storage manager and run cleanup
            storage_manager = QdrantStorageManager(self)
            result = await storage_manager.cleanup_stale_data()

            if result.get("status") == "completed":
                deleted_count = result.get("points_deleted", 0)
                if deleted_count > 0:
                    logger.info(
                        f"✅ Background cleanup completed: removed {deleted_count} stale entries"
                    )
                else:
                    logger.debug("✅ Background cleanup completed: no stale data found")
            else:
                logger.warning(f"⚠️ Background cleanup result: {result}")

        except Exception as e:
            logger.warning(f"⚠️ Background cleanup failed (non-critical): {e}")

    async def optimize_collection_performance(self) -> Dict[str, Any]:
        """
        Optimize collection performance by rebuilding indexes and optimizing segments.

        Returns:
            Dict with optimization results
        """
        if not self.is_available:
            return {"status": "skipped", "reason": "client_unavailable"}

        try:
            start_time = datetime.now(timezone.utc)
            logger.info("🚀 Starting collection performance optimization...")

            _, qdrant_models = get_qdrant_imports()

            # Get collection info
            collection_info = await asyncio.to_thread(
                self.client.get_collection, self.config.collection_name
            )

            optimization_results = {}

            # Step 1: Update collection optimization config
            try:
                optimization_params = self.config.get_optimization_params()

                # Update optimizer config
                await asyncio.to_thread(
                    self.client.update_collection,
                    collection_name=self.config.collection_name,
                    optimizer_config=qdrant_models["OptimizersConfigDiff"](
                        **optimization_params["optimizer_config"]
                    ),
                )

                optimization_results["optimizer_config_updated"] = True
                logger.info("✅ Updated collection optimizer configuration")

            except Exception as e:
                logger.warning(f"⚠️ Could not update optimizer config: {e}")
                optimization_results["optimizer_config_updated"] = False
                optimization_results["optimizer_error"] = str(e)

            # Step 2: Trigger collection optimization
            try:
                # Force optimization of vectors (consolidates segments, rebuilds indexes)
                if hasattr(self.client, "optimize_vectors"):
                    await asyncio.to_thread(
                        self.client.optimize_vectors,
                        collection_name=self.config.collection_name,
                    )
                    optimization_results["vectors_optimized"] = True
                    logger.info("✅ Triggered vector optimization")
                else:
                    optimization_results["vectors_optimized"] = False
                    optimization_results["vectors_note"] = (
                        "optimize_vectors method not available"
                    )

            except Exception as e:
                logger.warning(f"⚠️ Vector optimization failed: {e}")
                optimization_results["vectors_optimized"] = False
                optimization_results["vectors_error"] = str(e)

            # Step 3: Refresh collection statistics
            try:
                refreshed_info = await asyncio.to_thread(
                    self.client.get_collection, self.config.collection_name
                )

                optimization_results["collection_stats"] = {
                    "points_count": refreshed_info.points_count or 0,
                    "indexed_vectors_count": refreshed_info.indexed_vectors_count or 0,
                    "vectors_count": refreshed_info.indexed_vectors_count or 0,
                }

            except Exception as e:
                logger.warning(f"⚠️ Could not refresh collection stats: {e}")
                optimization_results["stats_error"] = str(e)

            end_time = datetime.now(timezone.utc)
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.info(
                f"✅ Collection performance optimization completed in {execution_time_ms}ms"
            )

            return {
                "status": "completed",
                "execution_time_ms": execution_time_ms,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "optimization_profile": self.config.optimization_profile.value,
                "results": optimization_results,
                "collection_name": self.config.collection_name,
            }

        except Exception as e:
            logger.error(f"❌ Collection performance optimization failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "collection_name": self.config.collection_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def rebuild_collection_completely(self) -> Dict[str, Any]:
        """
        Completely rebuild collection with current optimization settings.
        This is a more aggressive operation that recreates indexes from scratch.

        WARNING: This can be time-intensive for large collections.

        Returns:
            Dict with rebuild results
        """
        if not self.is_available:
            return {"status": "skipped", "reason": "client_unavailable"}

        try:
            start_time = datetime.now(timezone.utc)
            logger.info("🏗️ Starting complete collection rebuild...")

            _, qdrant_models = get_qdrant_imports()

            # Get current collection statistics
            old_collection_info = await asyncio.to_thread(
                self.client.get_collection, self.config.collection_name
            )

            old_stats = {
                "points_count": old_collection_info.points_count or 0,
                "indexed_vectors_count": old_collection_info.indexed_vectors_count or 0,
            }

            logger.info(
                f"📊 Current collection: {old_stats['points_count']} points, {old_stats['indexed_vectors_count']} indexed"
            )

            # Step 1: Create optimized collection configuration
            # Note: Vector size/distance can't be changed after creation
            optimization_params = self.config.get_optimization_params()

            # HNSW configuration (can be updated)
            hnsw_config = qdrant_models["HnswConfigDiff"](
                **optimization_params["hnsw_config"]
            )

            # Optimizer configuration (can be updated)
            optimizer_config = qdrant_models["OptimizersConfigDiff"](
                **optimization_params["optimizer_config"]
            )

            # Step 2: Update collection with new configuration
            # Note: vectors_config requires VectorParamsDiff, not VectorParams
            # Vector size/distance are immutable, so we only update hnsw and optimizer
            try:
                await asyncio.to_thread(
                    self.client.update_collection,
                    collection_name=self.config.collection_name,
                    hnsw_config=hnsw_config,
                    optimizers_config=optimizer_config,
                )

                logger.info("✅ Updated collection configuration (hnsw + optimizer)")

            except Exception as e:
                logger.warning(
                    f"⚠️ Could not update collection config (may not be supported): {e}"
                )

            # Step 3: Rebuild all payload indexes with optimized configurations
            index_rebuild_results = []

            # Define optimized index configurations based on Qdrant best practices
            index_configs = {
                # Tenant-based indexes (for multi-user data)
                "user_email": {
                    "schema": qdrant_models["KeywordIndexParams"](
                        type=qdrant_models["KeywordIndexType"].KEYWORD,
                        is_tenant=True,  # Optimize for tenant-based searches
                        on_disk=False,  # Keep in memory for fast access
                    ),
                    "description": "Tenant-optimized user email index",
                },
                "user_id": {
                    "schema": qdrant_models["KeywordIndexParams"](
                        type=qdrant_models["KeywordIndexType"].KEYWORD,
                        is_tenant=True,  # Also treat as tenant boundary
                        on_disk=False,
                    ),
                    "description": "Tenant-optimized user ID index",
                },
                # Principal index for time-based data
                "timestamp_unix": {
                    "schema": qdrant_models["IntegerIndexParams"](
                        type=qdrant_models["IntegerIndexType"].INTEGER,
                        lookup=False,  # Only range queries for timestamps
                        range=True,  # Enable range filtering
                        is_principal=True,  # Optimize storage for time-based queries
                    ),
                    "description": "Principal time-based index for efficient range queries",
                },
                # Performance metrics with range support
                "execution_time_ms": {
                    "schema": qdrant_models["IntegerIndexParams"](
                        type=qdrant_models["IntegerIndexType"].INTEGER,
                        lookup=False,  # Unlikely to do exact matches
                        range=True,  # Enable range filtering for performance analysis
                        on_disk=True,  # Less frequently accessed, save memory
                    ),
                    "description": "Range-optimized execution time index",
                },
                # Keyword indexes for exact matches
                "tool_name": {
                    "schema": qdrant_models["KeywordIndexParams"](
                        type=qdrant_models["KeywordIndexType"].KEYWORD,
                        on_disk=False,  # Frequently accessed
                    ),
                    "description": "Tool name keyword index",
                },
                "payload_type": {
                    "schema": qdrant_models["KeywordIndexParams"](
                        type=qdrant_models["KeywordIndexType"].KEYWORD,
                        on_disk=True,  # Limited values, less frequently filtered
                    ),
                    "description": "Payload type classification index",
                },
                "session_id": {
                    "schema": qdrant_models["KeywordIndexParams"](
                        type=qdrant_models["KeywordIndexType"].KEYWORD,
                        on_disk=True,  # Session-based queries are less common
                    ),
                    "description": "Session identifier index",
                },
                "label": {
                    "schema": qdrant_models["KeywordIndexParams"](
                        type=qdrant_models["KeywordIndexType"].KEYWORD,
                        on_disk=False,  # Generic label/tag field for filters like label:sent
                    ),
                    "description": "Generic label/tag index",
                },
                # Boolean index for compression flag
                "compressed": {
                    "schema": qdrant_models["BoolIndexParams"](
                        type=qdrant_models["BoolIndexType"].BOOL,
                        on_disk=True,  # Simple boolean, infrequent filtering
                    ),
                    "description": "Compression status boolean index",
                },
                # Datetime index for ISO timestamps
                "timestamp": {
                    "schema": qdrant_models["DatetimeIndexParams"](
                        type=qdrant_models["DatetimeIndexType"].DATETIME,
                        on_disk=True,  # timestamp_unix is preferred for range queries
                    ),
                    "description": "ISO datetime index (secondary to timestamp_unix)",
                },
                # Additional service-based indexes for semantic search enhancement
                "service": {
                    "schema": qdrant_models["KeywordIndexParams"](
                        type=qdrant_models["KeywordIndexType"].KEYWORD,
                        on_disk=False,  # Frequently used in service-specific searches
                    ),
                    "description": "Service classification index",
                },
                "tool": {
                    "schema": qdrant_models["KeywordIndexParams"](
                        type=qdrant_models["KeywordIndexType"].KEYWORD,
                        on_disk=False,  # Alias for tool_name, frequently accessed
                    ),
                    "description": "Tool classification alias index",
                },
            }

            # Rebuild indexes with optimized configurations
            for field, config in index_configs.items():
                try:
                    # Delete existing index (if it exists)
                    try:
                        await asyncio.to_thread(
                            self.client.delete_payload_index,
                            collection_name=self.config.collection_name,
                            field_name=field,
                        )
                        logger.debug(f"🗑️ Deleted existing index for field: {field}")
                    except Exception:
                        pass  # Index might not exist

                    # Create new optimized index with specific schema
                    await asyncio.to_thread(
                        self.client.create_payload_index,
                        collection_name=self.config.collection_name,
                        field_name=field,
                        field_schema=config["schema"],
                    )

                    index_rebuild_results.append(
                        {
                            "field": field,
                            "status": "success",
                            "description": config["description"],
                            "config": str(config["schema"]),
                        }
                    )
                    logger.debug(
                        f"✅ Rebuilt optimized index for field: {field} - {config['description']}"
                    )

                except Exception as e:
                    index_rebuild_results.append(
                        {
                            "field": field,
                            "status": "failed",
                            "error": str(e),
                            "description": config["description"],
                        }
                    )
                    logger.warning(f"⚠️ Failed to rebuild index for {field}: {e}")

            # Step 4: Force complete optimization
            try:
                if hasattr(self.client, "optimize_vectors"):
                    await asyncio.to_thread(
                        self.client.optimize_vectors,
                        collection_name=self.config.collection_name,
                    )
                    vectors_optimized = True
                else:
                    vectors_optimized = False

            except Exception as e:
                vectors_optimized = False
                logger.warning(f"⚠️ Vector optimization failed during rebuild: {e}")

            # Step 5: Get final statistics
            new_collection_info = await asyncio.to_thread(
                self.client.get_collection, self.config.collection_name
            )

            new_stats = {
                "points_count": new_collection_info.points_count or 0,
                "indexed_vectors_count": new_collection_info.indexed_vectors_count or 0,
            }

            end_time = datetime.now(timezone.utc)
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

            successful_indexes = len(
                [r for r in index_rebuild_results if r["status"] == "success"]
            )

            logger.info(
                f"✅ Complete collection rebuild finished in {execution_time_ms}ms"
            )
            logger.info(
                f"📊 Indexes rebuilt: {successful_indexes}/{len(index_configs)}"
            )

            return {
                "status": "completed",
                "execution_time_ms": execution_time_ms,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "optimization_profile": self.config.optimization_profile.value,
                "old_stats": old_stats,
                "new_stats": new_stats,
                "index_results": index_rebuild_results,
                "indexes_rebuilt": successful_indexes,
                "total_indexes": len(index_configs),
                "vectors_optimized": vectors_optimized,
                "collection_name": self.config.collection_name,
            }

        except Exception as e:
            logger.error(f"❌ Complete collection rebuild failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "collection_name": self.config.collection_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get connection information and status.

        Returns:
            Dict with connection details and status
        """
        return {
            "enabled": self.config.enabled,
            "initialized": self._initialized,
            "init_attempted": self._init_attempted,
            "init_complete": self._init_complete,
            "client_available": self.client is not None,
            "embedder_available": self.embedder is not None,
            "discovered_url": self.discovered_url,
            "config": {
                "host": self.config.host,
                "ports": self.config.ports,
                "collection_name": self.config.collection_name,
                "vector_size": self.config.vector_size,
                "distance": self.config.distance,
                "embedding_model": self.config.embedding_model,
                "cache_retention_days": self.config.cache_retention_days,
            },
            "embedding_dim": self.embedding_dim,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def get_or_create_client_manager(
    config: Optional[QdrantConfig] = None,
    qdrant_api_key: Optional[str] = None,
    qdrant_url: Optional[str] = None,
    auto_discovery: bool = True,
    prefer_grpc: Optional[bool] = None,
) -> "QdrantClientManager":
    """
    Get a singleton QdrantClientManager instance.

    The first caller may optionally provide config/credentials; subsequent callers
    will receive the same instance regardless of arguments. This ensures a single
    shared Qdrant client is used across middleware, tools, and resources.
    """
    global _global_client_manager

    if _global_client_manager is not None:
        return _global_client_manager

    # Default to centralized settings-based config if none provided
    if config is None:
        from .config import load_config_from_settings

        config = load_config_from_settings()

    # Get defaults from centralized settings if not provided
    from config.settings import settings

    if qdrant_api_key is None:
        qdrant_api_key = settings.qdrant_api_key
    if qdrant_url is None:
        qdrant_url = settings.qdrant_url
    if prefer_grpc is None:
        prefer_grpc = settings.qdrant_prefer_grpc

    _global_client_manager = QdrantClientManager(
        config=config,
        qdrant_api_key=qdrant_api_key,
        qdrant_url=qdrant_url,
        auto_discovery=auto_discovery,
        prefer_grpc=prefer_grpc,
    )
    return _global_client_manager
