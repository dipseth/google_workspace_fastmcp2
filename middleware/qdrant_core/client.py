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
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from .lazy_imports import get_qdrant_imports, get_sentence_transformer
from .config import QdrantConfig

from config.enhanced_logging import setup_logger
logger = setup_logger()


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
        auto_discovery: bool = True
    ):
        """
        Initialize the Qdrant client manager.
        
        Args:
            config: QdrantConfig instance with connection settings
            qdrant_api_key: API key for cloud Qdrant authentication
            qdrant_url: Full Qdrant URL (overrides host/port if provided)
            auto_discovery: Whether to auto-discover Qdrant ports
        """
        self.config = config
        self.qdrant_api_key = qdrant_api_key
        self.auto_discovery = auto_discovery
        
        # Parse URL if provided
        if qdrant_url:
            from urllib.parse import urlparse
            parsed = urlparse(qdrant_url)
            self.qdrant_host = parsed.hostname or config.host
            self.qdrant_port = parsed.port or config.ports[0]
            self.qdrant_url = qdrant_url
            self.qdrant_use_https = parsed.scheme == 'https'
            logger.info(f"🔧 Parsed Qdrant URL: {qdrant_url} -> host={self.qdrant_host}, port={self.qdrant_port}, https={self.qdrant_use_https}")
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
        """Connect directly using configured host/port or URL."""
        QdrantClient, _ = get_qdrant_imports()
        
        # Use URL if provided, otherwise use host/port
        if self.qdrant_url:
            logger.info(f"🔗 Connecting to Qdrant using URL: {self.qdrant_url}")
            # Disable SSL verification for HTTPS URLs (common for cloud Qdrant)
            if self.qdrant_url.startswith('https://'):
                self.client = QdrantClient(
                    url=self.qdrant_url,
                    api_key=self.qdrant_api_key,
                    verify=False  # Disable SSL verification for cloud instances
                )
            else:
                self.client = QdrantClient(
                    url=self.qdrant_url,
                    api_key=self.qdrant_api_key
                )
        else:
            logger.info(f"🔗 Connecting to Qdrant at {self.config.host}:{self.config.ports[0]}")
            self.client = QdrantClient(
                host=self.config.host,
                port=self.config.ports[0],
                api_key=self.qdrant_api_key
            )
    
    async def _discover_qdrant(self):
        """Discover working Qdrant instance by trying multiple ports."""
        if self.discovered_url and self.client:
            return
            
        QdrantClient, _ = get_qdrant_imports()
        
        # If we have a full URL, try that first
        if self.qdrant_url:
            try:
                logger.info(f"🔍 Trying Qdrant at URL: {self.qdrant_url}")
                # Disable SSL verification for HTTPS URLs (common for cloud Qdrant)
                if self.qdrant_url.startswith('https://'):
                    client = QdrantClient(
                        url=self.qdrant_url,
                        api_key=self.qdrant_api_key,
                        timeout=self.config.connection_timeout/1000,
                        verify=False  # Disable SSL verification for cloud instances
                    )
                else:
                    client = QdrantClient(
                        url=self.qdrant_url,
                        api_key=self.qdrant_api_key,
                        timeout=self.config.connection_timeout/1000
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
                    timeout=self.config.connection_timeout/1000
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
        """Load the embedding model if not already loaded."""
        if self.embedder is None:
            try:
                logger.info(f"🤖 Loading embedding model: {self.config.embedding_model}")
                
                def load_model():
                    SentenceTransformer = get_sentence_transformer()
                    return SentenceTransformer(self.config.embedding_model)
                
                self.embedder = await asyncio.to_thread(load_model)
                self.embedding_dim = self.embedder.get_sentence_embedding_dimension()
                logger.info(f"✅ Embedding model loaded (dim: {self.embedding_dim})")
                
            except Exception as e:
                logger.error(f"❌ Failed to load embedding model: {e}")
                raise RuntimeError(f"Failed to load embedding model: {e}")
    
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
                vector_config = qdrant_models['VectorParams'](
                    size=self.embedding_dim,
                    distance=getattr(qdrant_models['Distance'], self.config.distance.upper()),
                    **optimization_params["vector_config"]
                )
                
                # HNSW configuration based on optimization profile
                hnsw_config = qdrant_models['HnswConfigDiff'](
                    **optimization_params["hnsw_config"]
                )
                
                # Optimizer configuration based on optimization profile
                optimizer_config = qdrant_models['OptimizersConfigDiff'](
                    **optimization_params["optimizer_config"]
                )
                
                await asyncio.to_thread(
                    self.client.create_collection,
                    collection_name=self.config.collection_name,
                    vectors_config=vector_config,
                    hnsw_config=hnsw_config,
                    optimizers_config=optimizer_config
                )
                
                profile_name = self.config.optimization_profile.value
                description = optimization_params["description"]
                logger.info(f"✅ Created Qdrant collection: {self.config.collection_name}")
                logger.info(f"🚀 Optimization Profile: {profile_name}")
                logger.info(f"📊 Profile Description: {description}")
                
                # Create keyword indexes for filterable fields
                filterable_fields = [
                    "tool_name",      # Tool name filtering
                    "user_email",     # User email filtering
                    "user_id",        # User ID filtering
                    "session_id",     # Session filtering
                    "payload_type"    # Payload type filtering
                ]
                
                for field in filterable_fields:
                    try:
                        await asyncio.to_thread(
                            self.client.create_payload_index,
                            collection_name=self.config.collection_name,
                            field_name=field,
                            field_schema=qdrant_models['PayloadSchemaType'].KEYWORD
                        )
                        logger.info(f"✅ Created keyword index for field: {field}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to create index for {field}: {e}")
                        
            else:
                logger.info(f"✅ Using existing collection: {self.config.collection_name}")
                # Check if indexes exist and create them if missing
                try:
                    collection_info = await asyncio.to_thread(
                        self.client.get_collection,
                        self.config.collection_name
                    )
                    
                    # Get existing payload indexes
                    existing_indexes = set()
                    if hasattr(collection_info, 'payload_schema') and collection_info.payload_schema:
                        existing_indexes = set(collection_info.payload_schema.keys())
                    
                    # Create missing indexes - comprehensive list
                    filterable_fields = [
                        # Core indexed fields
                        "tool_name", "user_email", "user_id", "session_id", "payload_type",
                        # Additional fields for comprehensive search support
                        "timestamp", "execution_time_ms", "compressed",
                        # Common search aliases
                        "user", "service", "tool", "email", "type"
                    ]
                    for field in filterable_fields:
                        if field not in existing_indexes:
                            try:
                                await asyncio.to_thread(
                                    self.client.create_payload_index,
                                    collection_name=self.config.collection_name,
                                    field_name=field,
                                    field_schema=qdrant_models['PayloadSchemaType'].KEYWORD
                                )
                                logger.info(f"✅ Created missing keyword index for field: {field}")
                            except Exception as e:
                                logger.warning(f"⚠️ Failed to create missing index for {field}: {e}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not check existing indexes: {e}")
                
        except Exception as e:
            logger.error(f"❌ Failed to ensure collection exists: {e}")
            raise
    
    def _should_compress(self, data: str) -> bool:
        """Check if data should be compressed based on size."""
        return len(data.encode('utf-8')) > self.config.compression_threshold
    
    def _compress_data(self, data: str) -> bytes:
        """Compress data using gzip."""
        return gzip.compress(data.encode('utf-8'))
    
    def _decompress_data(self, data: bytes) -> str:
        """Decompress gzip-compressed data."""
        return gzip.decompress(data).decode('utf-8')
    
    @property
    def is_initialized(self) -> bool:
        """Check if client manager is fully initialized."""
        return self._initialized and self.client is not None and self.embedder is not None
    
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
            logger.info(f"🧹 Starting background cleanup (retention: {self.config.cache_retention_days} days)")
            
            # Import here to avoid circular dependencies
            from .storage import QdrantStorageManager
            
            # Create storage manager and run cleanup
            storage_manager = QdrantStorageManager(self)
            result = await storage_manager.cleanup_stale_data()
            
            if result.get("status") == "completed":
                deleted_count = result.get("points_deleted", 0)
                if deleted_count > 0:
                    logger.info(f"✅ Background cleanup completed: removed {deleted_count} stale entries")
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
                self.client.get_collection,
                self.config.collection_name
            )
            
            optimization_results = {}
            
            # Step 1: Update collection optimization config
            try:
                optimization_params = self.config.get_optimization_params()
                
                # Update optimizer config
                await asyncio.to_thread(
                    self.client.update_collection,
                    collection_name=self.config.collection_name,
                    optimizer_config=qdrant_models['OptimizersConfigDiff'](
                        **optimization_params["optimizer_config"]
                    )
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
                if hasattr(self.client, 'optimize_vectors'):
                    await asyncio.to_thread(
                        self.client.optimize_vectors,
                        collection_name=self.config.collection_name
                    )
                    optimization_results["vectors_optimized"] = True
                    logger.info("✅ Triggered vector optimization")
                else:
                    optimization_results["vectors_optimized"] = False
                    optimization_results["vectors_note"] = "optimize_vectors method not available"
                
            except Exception as e:
                logger.warning(f"⚠️ Vector optimization failed: {e}")
                optimization_results["vectors_optimized"] = False
                optimization_results["vectors_error"] = str(e)
            
            # Step 3: Refresh collection statistics
            try:
                refreshed_info = await asyncio.to_thread(
                    self.client.get_collection,
                    self.config.collection_name
                )
                
                optimization_results["collection_stats"] = {
                    "points_count": getattr(refreshed_info, 'points_count', 0),
                    "indexed_vectors_count": getattr(refreshed_info, 'indexed_vectors_count', 0),
                    "vectors_count": getattr(refreshed_info, 'vectors_count', 0)
                }
                
            except Exception as e:
                logger.warning(f"⚠️ Could not refresh collection stats: {e}")
                optimization_results["stats_error"] = str(e)
            
            end_time = datetime.now(timezone.utc)
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            logger.info(f"✅ Collection performance optimization completed in {execution_time_ms}ms")
            
            return {
                "status": "completed",
                "execution_time_ms": execution_time_ms,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "optimization_profile": self.config.optimization_profile.value,
                "results": optimization_results,
                "collection_name": self.config.collection_name
            }
            
        except Exception as e:
            logger.error(f"❌ Collection performance optimization failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "collection_name": self.config.collection_name,
                "timestamp": datetime.now(timezone.utc).isoformat()
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
                self.client.get_collection,
                self.config.collection_name
            )
            
            old_stats = {
                "points_count": getattr(old_collection_info, 'points_count', 0),
                "indexed_vectors_count": getattr(old_collection_info, 'indexed_vectors_count', 0)
            }
            
            logger.info(f"📊 Current collection: {old_stats['points_count']} points, {old_stats['indexed_vectors_count']} indexed")
            
            # Step 1: Create new optimized collection configuration
            optimization_params = self.config.get_optimization_params()
            
            # Vector configuration
            vector_config = qdrant_models['VectorParams'](
                size=self.embedding_dim,
                distance=getattr(qdrant_models['Distance'], self.config.distance.upper()),
                **optimization_params["vector_config"]
            )
            
            # HNSW configuration
            hnsw_config = qdrant_models['HnswConfigDiff'](
                **optimization_params["hnsw_config"]
            )
            
            # Optimizer configuration
            optimizer_config = qdrant_models['OptimizersConfigDiff'](
                **optimization_params["optimizer_config"]
            )
            
            # Step 2: Update collection with new configuration
            try:
                await asyncio.to_thread(
                    self.client.update_collection,
                    collection_name=self.config.collection_name,
                    vectors_config=vector_config,
                    hnsw_config=hnsw_config,
                    optimizers_config=optimizer_config
                )
                
                logger.info("✅ Updated collection configuration")
                
            except Exception as e:
                logger.warning(f"⚠️ Could not update collection config (may not be supported): {e}")
            
            # Step 3: Rebuild all payload indexes with optimized configurations
            index_rebuild_results = []
            
            # Define optimized index configurations based on Qdrant best practices
            index_configs = {
                # Tenant-based indexes (for multi-user data)
                "user_email": {
                    "schema": qdrant_models['KeywordIndexParams'](
                        type=qdrant_models['KeywordIndexType'].KEYWORD,
                        is_tenant=True,  # Optimize for tenant-based searches
                        on_disk=False    # Keep in memory for fast access
                    ),
                    "description": "Tenant-optimized user email index"
                },
                "user_id": {
                    "schema": qdrant_models['KeywordIndexParams'](
                        type=qdrant_models['KeywordIndexType'].KEYWORD,
                        is_tenant=True,  # Also treat as tenant boundary
                        on_disk=False
                    ),
                    "description": "Tenant-optimized user ID index"
                },
                
                # Principal index for time-based data
                "timestamp_unix": {
                    "schema": qdrant_models['IntegerIndexParams'](
                        type=qdrant_models['IntegerIndexType'].INTEGER,
                        lookup=False,    # Only range queries for timestamps
                        range=True,      # Enable range filtering
                        is_principal=True # Optimize storage for time-based queries
                    ),
                    "description": "Principal time-based index for efficient range queries"
                },
                
                # Performance metrics with range support
                "execution_time_ms": {
                    "schema": qdrant_models['IntegerIndexParams'](
                        type=qdrant_models['IntegerIndexType'].INTEGER,
                        lookup=False,    # Unlikely to do exact matches
                        range=True,      # Enable range filtering for performance analysis
                        on_disk=True     # Less frequently accessed, save memory
                    ),
                    "description": "Range-optimized execution time index"
                },
                
                # Keyword indexes for exact matches
                "tool_name": {
                    "schema": qdrant_models['KeywordIndexParams'](
                        type=qdrant_models['KeywordIndexType'].KEYWORD,
                        on_disk=False    # Frequently accessed
                    ),
                    "description": "Tool name keyword index"
                },
                "payload_type": {
                    "schema": qdrant_models['KeywordIndexParams'](
                        type=qdrant_models['KeywordIndexType'].KEYWORD,
                        on_disk=True     # Limited values, less frequently filtered
                    ),
                    "description": "Payload type classification index"
                },
                "session_id": {
                    "schema": qdrant_models['KeywordIndexParams'](
                        type=qdrant_models['KeywordIndexType'].KEYWORD,
                        on_disk=True     # Session-based queries are less common
                    ),
                    "description": "Session identifier index"
                },
                
                # Boolean index for compression flag
                "compressed": {
                    "schema": qdrant_models['BoolIndexParams'](
                        type=qdrant_models['BoolIndexType'].BOOL,
                        on_disk=True     # Simple boolean, infrequent filtering
                    ),
                    "description": "Compression status boolean index"
                },
                
                # Datetime index for ISO timestamps
                "timestamp": {
                    "schema": qdrant_models['DatetimeIndexParams'](
                        type=qdrant_models['DatetimeIndexType'].DATETIME,
                        on_disk=True     # timestamp_unix is preferred for range queries
                    ),
                    "description": "ISO datetime index (secondary to timestamp_unix)"
                },
                
                # Additional service-based indexes for semantic search enhancement
                "service": {
                    "schema": qdrant_models['KeywordIndexParams'](
                        type=qdrant_models['KeywordIndexType'].KEYWORD,
                        on_disk=False    # Frequently used in service-specific searches
                    ),
                    "description": "Service classification index"
                },
                "tool": {
                    "schema": qdrant_models['KeywordIndexParams'](
                        type=qdrant_models['KeywordIndexType'].KEYWORD,
                        on_disk=False    # Alias for tool_name, frequently accessed
                    ),
                    "description": "Tool classification alias index"
                }
            }
            
            # Rebuild indexes with optimized configurations
            for field, config in index_configs.items():
                try:
                    # Delete existing index (if it exists)
                    try:
                        await asyncio.to_thread(
                            self.client.delete_payload_index,
                            collection_name=self.config.collection_name,
                            field_name=field
                        )
                        logger.debug(f"🗑️ Deleted existing index for field: {field}")
                    except Exception:
                        pass  # Index might not exist
                    
                    # Create new optimized index with specific schema
                    await asyncio.to_thread(
                        self.client.create_payload_index,
                        collection_name=self.config.collection_name,
                        field_name=field,
                        field_schema=config["schema"]
                    )
                    
                    index_rebuild_results.append({
                        "field": field,
                        "status": "success",
                        "description": config["description"],
                        "config": str(config["schema"])
                    })
                    logger.debug(f"✅ Rebuilt optimized index for field: {field} - {config['description']}")
                    
                except Exception as e:
                    index_rebuild_results.append({
                        "field": field,
                        "status": "failed",
                        "error": str(e),
                        "description": config["description"]
                    })
                    logger.warning(f"⚠️ Failed to rebuild index for {field}: {e}")
            
            # Step 4: Force complete optimization
            try:
                if hasattr(self.client, 'optimize_vectors'):
                    await asyncio.to_thread(
                        self.client.optimize_vectors,
                        collection_name=self.config.collection_name
                    )
                    vectors_optimized = True
                else:
                    vectors_optimized = False
                    
            except Exception as e:
                vectors_optimized = False
                logger.warning(f"⚠️ Vector optimization failed during rebuild: {e}")
            
            # Step 5: Get final statistics
            new_collection_info = await asyncio.to_thread(
                self.client.get_collection,
                self.config.collection_name
            )
            
            new_stats = {
                "points_count": getattr(new_collection_info, 'points_count', 0),
                "indexed_vectors_count": getattr(new_collection_info, 'indexed_vectors_count', 0)
            }
            
            end_time = datetime.now(timezone.utc)
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            successful_indexes = len([r for r in index_rebuild_results if r["status"] == "success"])
            
            logger.info(f"✅ Complete collection rebuild finished in {execution_time_ms}ms")
            logger.info(f"📊 Indexes rebuilt: {successful_indexes}/{len(index_fields)}")
            
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
                "total_indexes": len(index_fields),
                "vectors_optimized": vectors_optimized,
                "collection_name": self.config.collection_name
            }
            
        except Exception as e:
            logger.error(f"❌ Complete collection rebuild failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "collection_name": self.config.collection_name,
                "timestamp": datetime.now(timezone.utc).isoformat()
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
                "cache_retention_days": self.config.cache_retention_days
            },
            "embedding_dim": self.embedding_dim,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }