u"""Enhanced Qdrant middleware with features inspired by TypeScript implementation."""

import json
import gzip
import logging
import asyncio
import uuid
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

from fastmcp.server.middleware import Middleware, MiddlewareContext

# Defer heavy imports to avoid blocking server startup
# from qdrant_client import QdrantClient, models
# from qdrant_client.models import Distance, VectorParams, PointStruct
# Import SentenceTransformer only when needed to avoid 3.85s blocking import
# from sentence_transformers import SentenceTransformer
# import numpy as np  # Moved to lazy import below

logger = logging.getLogger(__name__)

# Global variables for lazy-loaded imports
_qdrant_client = None
_qdrant_models = None
_numpy = None

def _get_numpy():
    """Lazy load numpy to avoid import errors during server startup."""
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
        from qdrant_client.models import Distance, VectorParams, PointStruct
        _qdrant_client = QdrantClient
        _qdrant_models = {
            'models': models,
            'Distance': Distance,
            'VectorParams': VectorParams,
            'PointStruct': PointStruct
        }
        logger.info("✅ Qdrant client loaded")
    return _qdrant_client, _qdrant_models


class PayloadType(Enum):
    """Types of payloads we store in Qdrant."""
    TOOL_RESPONSE = "tool_response"
    CLUSTER = "cluster"
    JOB = "job"
    QUERY = "query"
    GENERIC = "generic"


@dataclass
class QdrantConfig:
    """Configuration for Qdrant middleware."""
    # Connection settings
    ports: List[int] = None
    host: str = "localhost"
    connection_timeout: int = 5000
    retry_attempts: int = 3
    
    # Collection settings
    collection_name: str = "mcp_tool_responses"
    vector_size: int = 384
    distance: str = "Cosine"
    
    # Storage settings
    compression_threshold: int = 5120  # 5KB
    compression_type: str = "gzip"
    
    # Search settings
    default_search_limit: int = 10
    score_threshold: float = 0.7
    
    # Middleware settings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    summary_max_tokens: int = 500
    verbose_param: str = "verbose"
    enabled: bool = True
    
    def __post_init__(self):
        if self.ports is None:
            self.ports = [6333, 6335, 6334]
    
    @classmethod
    def from_file(cls, config_path: str = "config/qdrant.json") -> "QdrantConfig":
        """Load configuration from file with defaults."""
        config_file = Path(config_path)
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                return cls(**data)
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
        return cls()


class QdrantConnectionManager:
    """Manages Qdrant connections with auto-discovery and health checks."""
    
    def __init__(self, config: QdrantConfig):
        self.config = config
        self.discovered_url: Optional[str] = None
        self.client: Optional[Any] = None  # QdrantClient (lazy loaded)
        self._connection_tested = False
    
    async def discover_qdrant(self) -> Optional[str]:
        """Discover working Qdrant instance by trying multiple ports."""
        if self._connection_tested and self.discovered_url:
            return self.discovered_url
        
        # Try each port in order
        for port in self.config.ports:
            url = f"http://{self.config.host}:{port}"
            if await self._test_connection(url):
                self.discovered_url = url
                self._connection_tested = True
                logger.info(f"✅ Discovered Qdrant at {url}")
                await self._log_qdrant_info(url, port)
                return url
        
        self._connection_tested = True
        logger.warning("❌ No working Qdrant instance found")
        return None
    
    async def _test_connection(self, url: str) -> bool:
        """Test if Qdrant is accessible at given URL."""
        try:
            QdrantClient, _ = _get_qdrant_imports()
            client = QdrantClient(url=url, timeout=self.config.connection_timeout/1000)
            # Test basic connectivity
            await asyncio.wait_for(
                asyncio.to_thread(client.get_collections),
                timeout=self.config.connection_timeout/1000
            )
            return True
        except Exception as e:
            logger.debug(f"Connection test failed for {url}: {e}")
            return False
    
    async def _log_qdrant_info(self, url: str, port: int):
        """Log information about the Qdrant instance."""
        try:
            QdrantClient, _ = _get_qdrant_imports()
            client = QdrantClient(url=url)
            collections = await asyncio.to_thread(client.get_collections)
            
            logger.info(f"🎯 Qdrant Instance: {url}")
            logger.info(f"🎯 Dashboard URL: http://{self.config.host}:{port}/dashboard")
            
            if collections.collections:
                logger.info("📊 Available Collections:")
                for col in collections.collections:
                    logger.info(f"   📁 {col.name}")
                    logger.info(f"      🌐 Dashboard: http://{self.config.host}:{port}/dashboard#/collections/{col.name}")
            else:
                logger.info("📊 No collections found - will be created as needed")
        except Exception as e:
            logger.error(f"Failed to retrieve Qdrant info: {e}")
    
    async def get_client(self) -> Optional[Any]:  # QdrantClient (lazy loaded)
        """Get a working Qdrant client."""
        if self.client:
            return self.client
        
        url = await self.discover_qdrant()
        if url:
            QdrantClient, _ = _get_qdrant_imports()
            self.client = QdrantClient(url=url)
            return self.client
        return None
    
    def _try_connect(self, port: int) -> Optional[Any]:  # QdrantClient (lazy loaded)
        """Try to connect to Qdrant on a specific port synchronously."""
        try:
            url = f"http://{self.config.host}:{port}"
            QdrantClient, _ = _get_qdrant_imports()
            client = QdrantClient(url=url, timeout=self.config.connection_timeout/1000)
            # Test basic connectivity
            client.get_collections()
            logger.debug(f"Connected to Qdrant at {url}")
            return client
        except Exception as e:
            logger.debug(f"Failed to connect to Qdrant on port {port}: {e}")
            return None
    
    def _try_connect_sync(self) -> Optional[Any]:  # QdrantClient (lazy loaded)
        """Try to connect to Qdrant synchronously on any available port."""
        for port in self.config.ports:
            client = self._try_connect(port)
            if client:
                self.discovered_url = f"http://{self.config.host}:{port}"
                self._connection_tested = True
                logger.info(f"✅ Connected to Qdrant at {self.discovered_url}")
                return client
        return None


class CompressionService:
    """Handles data compression and decompression."""
    
    def __init__(self, compression_type: str = "gzip", threshold: int = 5120):
        self.compression_type = compression_type
        self.threshold = threshold
    
    def compress_if_needed(self, data: Any) -> Dict[str, Any]:
        """Compress data if it exceeds threshold."""
        # Serialize to JSON first
        if isinstance(data, str):
            serialized = data
        else:
            serialized = json.dumps(data, default=str)
        
        if len(serialized) <= self.threshold:
            return {
                "data": data,
                "is_compressed": False,
                "original_size": len(serialized)
            }
        
        # Compress the data
        if self.compression_type == "gzip":
            compressed = gzip.compress(serialized.encode('utf-8'))
            compressed_b64 = compressed.hex()  # Store as hex string
        else:
            raise ValueError(f"Unsupported compression type: {self.compression_type}")
        
        return {
            "data": compressed_b64,
            "is_compressed": True,
            "compression_type": self.compression_type,
            "original_size": len(serialized),
            "compressed_size": len(compressed)
        }
    
    def decompress_if_needed(self, data: Dict[str, Any]) -> Any:
        """Decompress data if it was compressed."""
        if not data.get("is_compressed", False):
            return data.get("data")
        
        compressed_data = data["data"]
        compression_type = data.get("compression_type", "gzip")
        
        if compression_type == "gzip":
            # Convert from hex string back to bytes
            compressed_bytes = bytes.fromhex(compressed_data)
            decompressed = gzip.decompress(compressed_bytes).decode('utf-8')
            # Parse JSON if it was serialized
            try:
                return json.loads(decompressed)
            except json.JSONDecodeError:
                return decompressed
        else:
            raise ValueError(f"Unsupported compression type: {compression_type}")


@dataclass
class StructuredPayload:
    """Structured payload for storing in Qdrant."""
    # Required fields
    id: str
    type: PayloadType
    tool_name: str
    timestamp: str
    
    # Response data
    response_data: Dict[str, Any]
    response_summary: str
    
    # Metadata
    execution_time_ms: int
    session_id: Optional[str] = None
    user_email: Optional[str] = None
    
    # Tool arguments
    tool_args: Dict[str, Any] = None
    
    # Compression info
    is_compressed: bool = False
    compression_type: Optional[str] = None
    original_size: Optional[int] = None
    compressed_size: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)


class SemanticQueryService:
    """Provides natural language query capabilities."""
    
    def __init__(self, client: Any, embedder: Any, collection_name: str):  # client is QdrantClient (lazy loaded)
        self.client = client
        self.embedder = embedder
        self.collection_name = collection_name
    
    async def query_natural_language(
        self, 
        query: str, 
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Perform natural language search on stored responses.
        
        Args:
            query: Natural language query
            filters: Optional filters (e.g., tool_name, user_email)
            limit: Maximum number of results
            
        Returns:
            List of matching responses with relevance scores
        """
        # Ensure model is loaded
        if self.embedder is None:
            raise RuntimeError("Embedding model not loaded. Call _ensure_model_loaded() first.")
        
        # Detect query intent
        query_type = self._detect_query_type(query)
        
        # Generate embedding
        embedding = self.embedder.encode(query).tolist()
        
        # Build filter conditions
        filter_conditions = []
        if filters:
            for key, value in filters.items():
                filter_conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value)
                    )
                )
        
        # Search
        results = await asyncio.to_thread(
            self.client.search,
            collection_name=self.collection_name,
            query_vector=embedding,
            query_filter=models.Filter(must=filter_conditions) if filter_conditions else None,
            limit=limit,
            with_payload=True
        )
        
        # Process results based on query type
        processed_results = []
        for result in results:
            processed = {
                "score": result.score,
                "id": result.id,
                "tool_name": result.payload.get("tool_name"),
                "timestamp": result.payload.get("timestamp"),
                "summary": result.payload.get("response_summary"),
                "matched_content": self._extract_relevant_content(
                    result.payload, 
                    query, 
                    query_type
                )
            }
            processed_results.append(processed)
        
        return processed_results
    
    def _detect_query_type(self, query: str) -> str:
        """Detect the type of query for specialized handling."""
        query_lower = query.lower()
        
        if any(term in query_lower for term in ["error", "exception", "failed", "failure"]):
            return "error_search"
        elif any(term in query_lower for term in ["slow", "performance", "time", "duration"]):
            return "performance_search"
        elif any(term in query_lower for term in ["user", "email", "who"]):
            return "user_search"
        elif any(term in query_lower for term in ["tool", "function", "api"]):
            return "tool_search"
        else:
            return "general_search"
    
    def _extract_relevant_content(
        self, 
        payload: Dict[str, Any], 
        query: str, 
        query_type: str
    ) -> str:
        """Extract content most relevant to the query."""
        response_data = payload.get("response_data", {})
        
        if query_type == "error_search":
            # Look for error-related fields
            if isinstance(response_data, dict):
                error_fields = ["error", "message", "exception", "traceback"]
                for field in error_fields:
                    if field in response_data:
                        return str(response_data[field])
        
        elif query_type == "performance_search":
            # Include execution time
            exec_time = payload.get("execution_time_ms", "N/A")
            summary = payload.get("response_summary", "")
            return f"Execution time: {exec_time}ms. {summary}"
        
        elif query_type == "user_search":
            # Include user information
            user = payload.get("user_email", "Unknown")
            tool = payload.get("tool_name", "Unknown")
            return f"User: {user}, Tool: {tool}"
        
        # Default: return summary
        return payload.get("response_summary", "No summary available")


class EnhancedQdrantResponseMiddleware(Middleware):
    """
    Enhanced Qdrant middleware with features from TypeScript implementation.
    
    Features:
    - Auto-discovery of Qdrant instances
    - Compression for large payloads
    - Natural language search
    - Structured payloads
    - Configuration management
    - Proper FastMCP2 middleware inheritance
    """
    
    def __init__(self, config: Optional[QdrantConfig] = None):
        """Initialize enhanced middleware with configuration."""
        self.config = config or QdrantConfig.from_file()
        self.connection_manager = QdrantConnectionManager(self.config)
        self.compression_service = CompressionService(
            compression_type=self.config.compression_type,
            threshold=self.config.compression_threshold
        )
        self.embedder = None
        self.client = None
        self.semantic_query_service = None
        self._initialized = False
        # REMOVED: self._initialize_sync() - This was causing the hang!
    
    @property
    def is_connected(self) -> bool:
        """Check if the middleware is connected to Qdrant."""
        return self._initialized and self.client is not None
    
    async def _ensure_model_loaded(self):
        """Load the embedding model if not already loaded."""
        if self.embedder is None:
            try:
                logger.info(f"🤖 Loading embedding model: {self.config.embedding_model}")
                # Import and load model in thread pool to avoid blocking
                def load_model():
                    from sentence_transformers import SentenceTransformer
                    return SentenceTransformer(self.config.embedding_model)
                
                self.embedder = await asyncio.to_thread(load_model)
                logger.info("✅ Embedding model loaded successfully")
            except Exception as e:
                logger.error(f"❌ Failed to load embedding model: {e}")
                raise RuntimeError(f"Failed to load embedding model: {e}")
    
    def _initialize_sync(self):
        """Initialize lightweight components synchronously."""
        try:
            # Only test Qdrant connection, defer model loading
            self.client = self.connection_manager._try_connect_sync()
            if self.client:
                # Test connection
                try:
                    self.client.get_collections()
                    self._initialized = True
                    logger.info("✅ Enhanced Qdrant middleware connected (model loading deferred)")
                except Exception:
                    self.client = None
                    self._initialized = False
            else:
                logger.info("⚠️ Qdrant not found, middleware disabled")
                self._initialized = False
        except Exception as e:
            logger.warning(f"Failed to connect to Qdrant: {e}")
            self._initialized = False
    
    async def initialize(self):
        """Initialize the middleware components asynchronously if not already done."""
        # Try to connect if not connected
        if not self._initialized or not self.client:
            self.client = await self.connection_manager.get_client()
            if self.client:
                self._initialized = True
            else:
                logger.warning("Qdrant middleware could not connect")
                return
        
        # Ensure collection exists
        await self._ensure_collection()
        
        # Load embedding model if needed
        await self._ensure_model_loaded()
        
        # Initialize semantic query service if needed
        if not self.semantic_query_service:
            self.semantic_query_service = SemanticQueryService(
                self.client,
                self.embedder,
                self.config.collection_name
            )
        
        logger.info("✅ Enhanced Qdrant middleware fully initialized")
    
    async def _ensure_collection(self):
        """Ensure the collection exists with proper configuration."""
        try:
            _, qdrant_models = _get_qdrant_imports()
            collections = await asyncio.to_thread(self.client.get_collections)
            exists = any(col.name == self.config.collection_name for col in collections.collections)
            
            if not exists:
                await asyncio.to_thread(
                    self.client.create_collection,
                    collection_name=self.config.collection_name,
                    vectors_config=qdrant_models['VectorParams'](
                        size=self.config.vector_size,
                        distance=getattr(qdrant_models['Distance'], self.config.distance.upper())
                    )
                )
                logger.info(f"✅ Created collection: {self.config.collection_name}")
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            raise
    
    async def process_tool_response(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        response: Any,
        execution_time_ms: int,
        session_id: Optional[str] = None,
        user_email: Optional[str] = None,
        return_full: bool = False
    ) -> Any:
        """
        Process a tool response - store in Qdrant and return summary.
        
        Args:
            tool_name: Name of the tool
            tool_args: Arguments passed to the tool
            response: The tool's response
            execution_time_ms: Execution time in milliseconds
            session_id: Session ID
            user_email: User email
            return_full: Whether to return full response or summary
            
        Returns:
            Processed response (summary or full)
        """
        # If not enabled or not connected, just return the response
        if not self.config.enabled or not self.is_connected:
            return response
        
        try:
            # Initialize if needed
            if not self._initialized:
                await self.initialize()
            
            # Store response asynchronously without blocking
            asyncio.create_task(self._store_response(
                tool_name=tool_name,
                tool_args=tool_args,
                response=response,
                execution_time_ms=execution_time_ms,
                session_id=session_id,
                user_email=user_email
            ))
            
            # Return full response if requested
            if return_full or tool_args.get(self.config.verbose_param, False):
                return response
            
            # Generate and return summary
            return self._generate_enhanced_summary(tool_name, response)
        except Exception as e:
            logger.error(f"Failed to process tool response: {e}")
            return response
    
    async def _store_response(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        response: Any,
        execution_time_ms: int,
        session_id: Optional[str] = None,
        user_email: Optional[str] = None
    ):
        """Store response in Qdrant with compression and structured payload."""
        try:
            # Ensure we have a client connection first
            if not self.client:
                self.client = await self.connection_manager.get_client()
                if not self.client:
                    logger.error(f"Failed to connect to Qdrant for storing {tool_name} response")
                    return
            
            # Ensure model is loaded
            await self._ensure_model_loaded()
            
            _, qdrant_models = _get_qdrant_imports()
            # Convert response to serializable format
            response_data = self._serialize_response(response)
            
            # Compress if needed
            compressed_result = self.compression_service.compress_if_needed(response_data)
            
            # Generate summary
            summary = self._generate_enhanced_summary(tool_name, response)
            
            # Create structured payload
            payload = StructuredPayload(
                id=str(uuid.uuid4()),
                type=self._detect_payload_type(tool_name, response),
                tool_name=tool_name,
                timestamp=datetime.now(timezone.utc).isoformat(),
                response_data=compressed_result["data"],
                response_summary=summary,
                execution_time_ms=execution_time_ms,
                session_id=session_id,
                user_email=user_email,
                tool_args=tool_args,
                is_compressed=compressed_result["is_compressed"],
                compression_type=compressed_result.get("compression_type"),
                original_size=compressed_result.get("original_size"),
                compressed_size=compressed_result.get("compressed_size")
            )
            
            # Generate embedding from summary + tool info
            embedding_text = f"{tool_name} {summary}"
            embedding = self.embedder.encode(embedding_text).tolist()
            
            # Store in Qdrant
            await asyncio.to_thread(
                self.client.upsert,
                collection_name=self.config.collection_name,
                points=[
                    qdrant_models['PointStruct'](
                        id=payload.id,
                        vector=embedding,
                        payload=payload.to_dict()
                    )
                ]
            )
            
            logger.debug(f"✅ Stored response for {tool_name} (ID: {payload.id})")
            
        except Exception as e:
            logger.error(f"Failed to store response for {tool_name}: {e}")
    
    def _serialize_response(self, response: Any) -> Dict[str, Any]:
        """Convert response to serializable format."""
        if hasattr(response, '__dict__'):
            return response.__dict__
        elif isinstance(response, (dict, list, str, int, float, bool, type(None))):
            return response
        else:
            return {"content": str(response), "type": type(response).__name__}
    
    def _detect_payload_type(self, tool_name: str, response: Any) -> PayloadType:
        """Detect the type of payload based on tool name and response."""
        tool_lower = tool_name.lower()
        
        if "cluster" in tool_lower:
            return PayloadType.CLUSTER
        elif "job" in tool_lower or "query" in tool_lower:
            return PayloadType.JOB
        elif "search" in tool_lower or "find" in tool_lower:
            return PayloadType.QUERY
        else:
            return PayloadType.TOOL_RESPONSE
    
    def _generate_enhanced_summary(self, tool_name: str, response: Any) -> str:
        """Generate an intelligent summary of the response."""
        try:
            # Handle different response types
            if isinstance(response, str):
                # For string responses, truncate if too long
                if len(response) > 200:
                    return f"{response[:200]}... (truncated)"
                return response
            
            elif isinstance(response, dict):
                # For dict responses, extract key information
                summary_parts = [f"{tool_name} response:"]
                
                # Look for common summary fields
                for key in ["status", "result", "message", "error", "count", "total"]:
                    if key in response:
                        summary_parts.append(f"{key}: {response[key]}")
                
                # Add counts for lists
                for key, value in response.items():
                    if isinstance(value, list):
                        summary_parts.append(f"{key}: {len(value)} items")
                
                return " ".join(summary_parts[:5])  # Limit to 5 parts
            
            elif isinstance(response, list):
                # For list responses
                return f"{tool_name} returned {len(response)} items"
            
            else:
                # For other types
                return f"{tool_name} completed successfully"
                
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return f"{tool_name} response (summary generation failed)"
    
    async def search_responses(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Search stored responses using natural language.
        
        Args:
            query: Natural language search query
            filters: Optional filters (tool_name, user_email, etc.)
            limit: Maximum number of results
            
        Returns:
            List of matching responses
        """
        if not self._initialized:
            await self.initialize()
        
        if not self.semantic_query_service:
            return []
        
        limit = limit or self.config.default_search_limit
        return await self.semantic_query_service.query_natural_language(query, filters, limit)
    
    async def get_response_by_id(self, response_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific response by ID."""
        if not self._initialized:
            await self.initialize()
        
        try:
            result = await asyncio.to_thread(
                self.client.retrieve,
                collection_name=self.config.collection_name,
                ids=[response_id]
            )
            
            if result:
                payload = result[0].payload
                # Decompress if needed
                if payload.get("is_compressed"):
                    response_data = self.compression_service.decompress_if_needed({
                        "data": payload["response_data"],
                        "is_compressed": payload["is_compressed"],
                        "compression_type": payload.get("compression_type")
                    })
                    payload["response_data"] = response_data
                
                return payload
            
        except Exception as e:
            logger.error(f"Failed to retrieve response {response_id}: {e}")
        
        return None
    
    async def get_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        group_by: str = "tool_name"
    ) -> Dict[str, Any]:
        """
        Get analytics on stored responses.
        
        Args:
            start_date: Start date for filtering
            end_date: End date for filtering
            group_by: Field to group by (tool_name, user_email, etc.)
            
        Returns:
            Analytics data
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Build filter
            conditions = []
            if start_date:
                conditions.append(
                    models.FieldCondition(
                        key="timestamp",
                        range=models.Range(gte=start_date.isoformat())
                    )
                )
            if end_date:
                conditions.append(
                    models.FieldCondition(
                        key="timestamp",
                        range=models.Range(lte=end_date.isoformat())
                    )
                )
            
            # Scroll through all matching records
            records = []
            offset = None
            
            while True:
                result = await asyncio.to_thread(
                    self.client.scroll,
                    collection_name=self.config.collection_name,
                    scroll_filter=models.Filter(must=conditions) if conditions else None,
                    limit=100,
                    offset=offset
                )
                
                records.extend(result[0])
                offset = result[1]
                
                if offset is None:
                    break
            
            # Process analytics
            analytics = {
                "total_responses": len(records),
                "date_range": {
                    "start": start_date.isoformat() if start_date else "all",
                    "end": end_date.isoformat() if end_date else "all"
                },
                "by_" + group_by: {},
                "performance": {
                    "avg_execution_time_ms": 0,
                    "min_execution_time_ms": float('inf'),
                    "max_execution_time_ms": 0
                },
                "compression": {
                    "compressed_count": 0,
                    "total_original_size": 0,
                    "total_compressed_size": 0
                }
            }
            
            # Aggregate data
            total_exec_time = 0
            for record in records:
                payload = record.payload
                
                # Group by field
                group_value = payload.get(group_by, "unknown")
                if group_value not in analytics["by_" + group_by]:
                    analytics["by_" + group_by][group_value] = {
                        "count": 0,
                        "avg_execution_time_ms": 0
                    }
                analytics["by_" + group_by][group_value]["count"] += 1
                
                # Performance metrics
                exec_time = payload.get("execution_time_ms", 0)
                total_exec_time += exec_time
                analytics["performance"]["min_execution_time_ms"] = min(
                    analytics["performance"]["min_execution_time_ms"],
                    exec_time
                )
                analytics["performance"]["max_execution_time_ms"] = max(
                    analytics["performance"]["max_execution_time_ms"],
                    exec_time
                )
                
                # Compression metrics
                if payload.get("is_compressed"):
                    analytics["compression"]["compressed_count"] += 1
                    analytics["compression"]["total_original_size"] += payload.get("original_size", 0)
                    analytics["compression"]["total_compressed_size"] += payload.get("compressed_size", 0)
            
            # Calculate averages
            if records:
                analytics["performance"]["avg_execution_time_ms"] = total_exec_time / len(records)
            
            # Calculate compression ratio
            if analytics["compression"]["total_original_size"] > 0:
                analytics["compression"]["compression_ratio"] = (
                    analytics["compression"]["total_compressed_size"] /
                    analytics["compression"]["total_original_size"]
                )
            
            return analytics
            
        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        FastMCP2 middleware hook - intercept tool calls to store responses in Qdrant.
        
        Args:
            context: Middleware context containing tool information
            call_next: Function to call the next middleware/handler
        """
        if not self.config.enabled:
            return await call_next(context)
        
        # Extract tool information
        tool_name = getattr(context.message, 'name', 'unknown')
        tool_args = getattr(context.message, 'arguments', {})
        
        # Check if verbose mode is requested
        is_verbose = tool_args.get(self.config.verbose_param, False)
        
        # Record start time
        start_time = datetime.utcnow()
        
        try:
            # Execute the tool
            result = await call_next(context)
            
            # Calculate execution time
            execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Extract session and user info
            session_id = None
            user_email = None
            
            if context.fastmcp_context:
                session_id = context.fastmcp_context.session_id
                # Try to extract user email from args
                for key in ['user_email', 'user_google_email', 'email']:
                    if key in tool_args:
                        user_email = tool_args[key]
                        break
            
            # Process response (store + return summary/full)
            processed_result = await self.process_tool_response(
                tool_name=tool_name,
                tool_args=tool_args,
                response=result,
                execution_time_ms=execution_time_ms,
                session_id=session_id,
                user_email=user_email,
                return_full=is_verbose
            )
            
            return processed_result
            
        except Exception as e:
            # Log error but don't break tool execution
            logger.error(f"Error in EnhancedQdrantResponseMiddleware for {tool_name}: {e}")
            # Re-raise the original error
            raise
            return {"error": str(e)}


# FastMCP Tool Setup Function

def setup_enhanced_qdrant_tools(mcp, middleware: EnhancedQdrantResponseMiddleware):
    """Setup enhanced Qdrant tools using the correct FastMCP pattern."""
    
    @mcp.tool
    async def search_tool_history(
        query: str,
        tool_name: Optional[str] = None,
        user_email: Optional[str] = None,
        limit: int = 10
    ) -> str:
        """
        Search through historical tool responses using natural language.
        
        Args:
            query: Natural language search query (e.g., "errors in the last hour", "slow responses")
            tool_name: Filter by specific tool name
            user_email: Filter by user email
            limit: Maximum number of results to return
            
        Returns:
            JSON string with search results
        """
        try:
            filters = {}
            if tool_name:
                filters["tool_name"] = tool_name
            if user_email:
                filters["user_email"] = user_email
            
            results = await middleware.search_responses(query, filters, limit)
            return json.dumps({"results": results, "count": len(results)}, indent=2)
        except Exception as e:
            return f"Search failed: {str(e)}"

    @mcp.tool
    async def get_tool_analytics(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: str = "tool_name"
    ) -> str:
        """
        Get analytics on tool usage and performance.
        
        Args:
            start_date: ISO format start date (e.g., "2024-01-01T00:00:00")
            end_date: ISO format end date
            group_by: Field to group by (tool_name, user_email)
            
        Returns:
            JSON string with analytics data
        """
        try:
            start_dt = datetime.fromisoformat(start_date) if start_date else None
            end_dt = datetime.fromisoformat(end_date) if end_date else None
            
            analytics = await middleware.get_analytics(start_dt, end_dt, group_by)
            return json.dumps(analytics, indent=2)
        except Exception as e:
            return f"Analytics failed: {str(e)}"

    @mcp.tool
    async def get_response_details(response_id: str) -> str:
        """
        Get full details of a stored response by ID.
        
        Args:
            response_id: UUID of the stored response
            
        Returns:
            JSON string with full response details
        """
        try:
            details = await middleware.get_response_by_id(response_id)
            if details:
                return json.dumps(details, indent=2)
            else:
                return f"Response with ID {response_id} not found"
        except Exception as e:
            return f"Failed to get response details: {str(e)}"

# Backward compatibility alias
QdrantEnhancedMiddleware = EnhancedQdrantResponseMiddleware

# Backward compatibility alias
QdrantEnhancedMiddleware = EnhancedQdrantResponseMiddleware
# Backward compatibility alias - moved to end of file
QdrantEnhancedMiddleware = EnhancedQdrantResponseMiddleware