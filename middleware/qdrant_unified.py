"""Unified Qdrant Response Middleware combining proven architecture with enhanced features."""

import json
import gzip
import logging
import hashlib
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from typing_extensions import Any, Dict, Optional, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = logging.getLogger(__name__)

# Global variables for lazy-loaded imports
_qdrant_client = None
_qdrant_models = None
_sentence_transformer = None
_numpy = None

def _parse_search_query(query: str) -> Dict[str, Any]:
    """
    Parse search query to extract filters and semantic search terms.
    
    Supports formats:
    - "id:12345" -> Direct ID lookup
    - "field:value semantic query" -> Filtered semantic search
    - "field1:value1 field2:value2 semantic query" -> Multiple filters + semantic search
    - "plain text" -> Pure semantic search
    
    Args:
        query: Search query string
        
    Returns:
        Dict with parsed components: {
            "query_type": "id_lookup" | "filtered_search" | "semantic_search",
            "filters": {"field": "value", ...},
            "semantic_query": "remaining text for semantic search",
            "id": "target_id" (only for id_lookup)
        }
    """
    import re
    
    # Initialize result
    result = {
        "query_type": "semantic_search",
        "filters": {},
        "semantic_query": "",
        "id": None
    }
    
    # Check for direct ID lookup
    if query.startswith("id:"):
        result["query_type"] = "id_lookup"
        result["id"] = query[3:].strip()
        return result
    
    # Parse field:value patterns
    filter_pattern = r'(\w+):([^\s]+)'
    filters = {}
    remaining_text = query
    
    # Extract all field:value pairs
    for match in re.finditer(filter_pattern, query):
        field = match.group(1)
        value = match.group(2)
        filters[field] = value
        # Remove this filter from the remaining text
        remaining_text = remaining_text.replace(match.group(0), '', 1)
    
    # Clean up remaining text for semantic search
    semantic_query = remaining_text.strip()
    
    # Update result based on what we found
    if filters:
        result["query_type"] = "filtered_search"
        result["filters"] = filters
        result["semantic_query"] = semantic_query
    else:
        result["query_type"] = "semantic_search"
        result["semantic_query"] = query
    
    return result

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

def _get_sentence_transformer():
    """Lazy load SentenceTransformer when first needed."""
    global _sentence_transformer
    if _sentence_transformer is None:
        logger.info("🤖 Loading SentenceTransformer (first use)...")
        from sentence_transformers import SentenceTransformer
        _sentence_transformer = SentenceTransformer
        logger.info("✅ SentenceTransformer loaded")
    return _sentence_transformer


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


class QdrantUnifiedMiddleware(Middleware):
    """
    Unified Qdrant middleware that combines proven working architecture
    with enhanced features like auto-discovery, compression, and lazy loading.
    
    This middleware intercepts all tool responses, stores them in a Qdrant
    vector database with embeddings, and provides search capabilities.
    """
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        qdrant_api_key: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        collection_name: str = "mcp_tool_responses",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        summary_max_tokens: int = 500,
        verbose_param: str = "verbose",
        enabled: bool = True,
        compression_threshold: int = 5120,
        auto_discovery: bool = True,
        ports: Optional[List[int]] = None
    ):
        """
        Initialize the unified Qdrant middleware.
        
        Args:
            qdrant_host: Qdrant server hostname
            qdrant_port: Primary Qdrant server port
            qdrant_api_key: API key for cloud Qdrant authentication
            qdrant_url: Full Qdrant URL (if provided, overrides host/port)
            collection_name: Name of the collection to store responses
            embedding_model: Model to use for generating embeddings
            summary_max_tokens: Maximum tokens in summarized response
            verbose_param: Parameter name to check for verbose mode
            enabled: Whether the middleware is enabled
            compression_threshold: Minimum size (bytes) to compress payloads
            auto_discovery: Whether to auto-discover Qdrant ports
            ports: List of ports to try for auto-discovery
        """
        # Parse URL if provided
        if qdrant_url:
            from urllib.parse import urlparse
            parsed = urlparse(qdrant_url)
            self.qdrant_host = parsed.hostname or qdrant_host
            self.qdrant_port = parsed.port or qdrant_port
            self.qdrant_url = qdrant_url
            self.qdrant_use_https = parsed.scheme == 'https'
            logger.info(f"🔧 Parsed Qdrant URL: {qdrant_url} -> host={self.qdrant_host}, port={self.qdrant_port}, https={self.qdrant_use_https}")
        else:
            self.qdrant_host = qdrant_host
            self.qdrant_port = qdrant_port
            self.qdrant_url = None
            self.qdrant_use_https = False
        
        self.qdrant_api_key = qdrant_api_key
        
        # Create configuration
        self.config = QdrantConfig(
            host=self.qdrant_host,
            ports=ports or [self.qdrant_port, 6333, 6335, 6334],
            collection_name=collection_name,
            embedding_model=embedding_model,
            summary_max_tokens=summary_max_tokens,
            verbose_param=verbose_param,
            enabled=enabled,
            compression_threshold=compression_threshold
        )
        
        # Initialize state
        self.client = None
        self.embedder = None
        self.embedding_dim = None
        self.discovered_url = None
        self._initialized = False
        self.auto_discovery = auto_discovery
        
        # Initialize if enabled
        if self.config.enabled:
            self._initialize_sync()
    
    def _initialize_sync(self):
        """Initialize lightweight components synchronously."""
        try:
            logger.info("🚀 Initializing Qdrant Unified Middleware...")
            
            if self.auto_discovery:
                # Auto-discovery will be done async in initialize()
                logger.info("✅ Auto-discovery mode enabled")
            else:
                # Direct connection mode
                QdrantClient, _ = _get_qdrant_imports()
                
                # Use URL if provided, otherwise use host/port
                if self.qdrant_url:
                    logger.info(f"🔗 Connecting to Qdrant using URL: {self.qdrant_url}")
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
                logger.info(f"✅ Connected to Qdrant")
                
            self._initialized = True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Qdrant middleware: {e}")
            self.config.enabled = False
    
    async def initialize(self):
        """Initialize async components (embedding model, auto-discovery)."""
        if not self.config.enabled:
            return
            
        try:
            # Auto-discover Qdrant if enabled
            if self.auto_discovery and not self.client:
                await self._discover_qdrant()
            
            # Load embedding model
            await self._ensure_model_loaded()
            
            # Ensure collection exists
            if self.client and self.embedder:
                await self._ensure_collection()
                logger.info("✅ Qdrant Unified Middleware fully initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to complete async initialization: {e}")
            self.config.enabled = False
    
    async def _discover_qdrant(self):
        """Discover working Qdrant instance by trying multiple ports."""
        if self.discovered_url and self.client:
            return
            
        QdrantClient, _ = _get_qdrant_imports()
        
        # If we have a full URL, try that first
        if self.qdrant_url:
            try:
                logger.info(f"🔍 Trying Qdrant at URL: {self.qdrant_url}")
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
                    SentenceTransformer = _get_sentence_transformer()
                    return SentenceTransformer(self.config.embedding_model)
                
                self.embedder = await asyncio.to_thread(load_model)
                self.embedding_dim = self.embedder.get_sentence_embedding_dimension()
                logger.info(f"✅ Embedding model loaded (dim: {self.embedding_dim})")
                
            except Exception as e:
                logger.error(f"❌ Failed to load embedding model: {e}")
                raise RuntimeError(f"Failed to load embedding model: {e}")
    
    async def _ensure_collection(self):
        """Ensure the Qdrant collection exists with proper configuration."""
        if not self.client:
            return
            
        try:
            _, qdrant_models = _get_qdrant_imports()
            
            # Check if collection exists
            collections = await asyncio.to_thread(self.client.get_collections)
            collection_names = [c.name for c in collections.collections]
            
            if self.config.collection_name not in collection_names:
                # Create collection
                await asyncio.to_thread(
                    self.client.create_collection,
                    collection_name=self.config.collection_name,
                    vectors_config=qdrant_models['VectorParams'](
                        size=self.embedding_dim,
                        distance=getattr(qdrant_models['Distance'], self.config.distance.upper())
                    )
                )
                logger.info(f"✅ Created Qdrant collection: {self.config.collection_name}")
            else:
                logger.info(f"✅ Using existing collection: {self.config.collection_name}")
                
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
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        FastMCP2 middleware hook for intercepting tool calls.
        Store responses in Qdrant for search and analysis.
        """
        # Call the next middleware/tool
        response = await call_next(context)
        
        # Store response if enabled
        if self.config.enabled and self.client and self.embedder:
            try:
                await self._store_response(context, response)
            except Exception as e:
                logger.error(f"❌ Failed to store response in Qdrant: {e}")
        
        return response
    
    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """
        FastMCP2 middleware hook for intercepting resource reads.
        Handle Qdrant-specific resources directly in the middleware.
        """
        # Check if this is a Qdrant resource
        # Convert AnyUrl to string before using string methods
        uri = str(context.message.uri) if context.message.uri else ""
        
        if not uri.startswith("qdrant://"):
            # Not a Qdrant resource, let other handlers deal with it
            return await call_next(context)
        
        # Handle Qdrant resources directly
        try:
            return await self._handle_qdrant_resource(uri, context)
        except Exception as e:
            logger.error(f"❌ Failed to handle Qdrant resource {uri}: {e}")
            # Return error response in proper format
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps({
                        "error": f"Failed to handle Qdrant resource: {str(e)}",
                        "uri": uri,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                }]
            }
    
    async def _handle_qdrant_resource(self, uri: str, context: MiddlewareContext):
        """Handle Qdrant-specific resource requests."""
        # Ensure middleware is initialized
        if not self.client or not self.embedder:
            await self.initialize()
        
        if not self.client:
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json", 
                    "text": json.dumps({
                        "error": "Qdrant not available - client not initialized",
                        "qdrant_enabled": False,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                }]
            }
        
        # Parse the URI to determine the resource type
        parts = uri.replace("qdrant://", "").split("/")
        
        if not parts:
            return self._error_response(uri, "Invalid Qdrant URI format")
        
        resource_type = parts[0]
        
        if resource_type == "collections" and len(parts) == 2 and parts[1] == "list":
            # qdrant://collections/list
            return await self._handle_collections_list(uri)
            
        elif resource_type == "collection" and len(parts) >= 3:
            collection_name = parts[1]
            
            if parts[2] == "info":
                # qdrant://collection/{collection}/info
                return await self._handle_collection_info(uri, collection_name)
                
            elif parts[2] == "responses" and len(parts) == 4 and parts[3] == "recent":
                # qdrant://collection/{collection}/responses/recent
                return await self._handle_collection_responses(uri, collection_name)
                
        elif resource_type == "search":
            if len(parts) == 3:
                # qdrant://search/{collection}/{query}
                collection_name = parts[1]
                query = parts[2]
                return await self._handle_collection_search(uri, collection_name, query)
            elif len(parts) == 2:
                # qdrant://search/{query}
                query = parts[1]
                return await self._handle_global_search(uri, query)
        
        return self._error_response(uri, f"Unknown Qdrant resource type: {resource_type}")
    
    def _error_response(self, uri: str, error_message: str):
        """Create a standard error response for resources."""
        return {
            "contents": [{
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps({
                    "error": error_message,
                    "uri": uri,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            }]
        }
    
    async def _handle_collections_list(self, uri: str):
        """Handle qdrant://collections/list resource."""
        try:
            collections = await asyncio.to_thread(self.client.get_collections)
            
            collections_info = []
            for collection in collections.collections:
                try:
                    info = await asyncio.to_thread(self.client.get_collection, collection.name)
                    collections_info.append({
                        "name": collection.name,
                        "points_count": info.points_count,
                        "vectors_count": getattr(info, 'vectors_count', 0),
                        "indexed_vectors_count": getattr(info, 'indexed_vectors_count', 0),
                        "segments_count": getattr(info, 'segments_count', 0),
                        "status": str(info.status) if hasattr(info, 'status') else 'unknown'
                    })
                except Exception as e:
                    logger.warning(f"Failed to get info for collection {collection.name}: {e}")
                    collections_info.append({
                        "name": collection.name,
                        "error": str(e)
                    })
            
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps({
                        "qdrant_enabled": True,
                        "qdrant_url": self.discovered_url,
                        "total_collections": len(collections_info),
                        "collections": collections_info,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, indent=2)
                }]
            }
            
        except Exception as e:
            logger.error(f"Error listing Qdrant collections: {e}")
            return self._error_response(uri, f"Failed to list collections: {str(e)}")
    
    async def _handle_collection_info(self, uri: str, collection_name: str):
        """Handle qdrant://collection/{collection}/info resource."""
        try:
            collections = await asyncio.to_thread(self.client.get_collections)
            collection_names = [c.name for c in collections.collections]
            
            collection_info = None
            if collection_name in collection_names:
                collection_info = await asyncio.to_thread(
                    self.client.get_collection,
                    collection_name
                )
            
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps({
                        "qdrant_enabled": True,
                        "qdrant_url": self.discovered_url,
                        "requested_collection": collection_name,
                        "collection_exists": collection_name in collection_names,
                        "total_collections": len(collection_names),
                        "all_collections": collection_names,
                        "collection_info": {
                            "vectors_count": getattr(collection_info, 'vectors_count', 0),
                            "indexed_vectors_count": getattr(collection_info, 'indexed_vectors_count', 0),
                            "points_count": collection_info.points_count if collection_info else 0,
                            "segments_count": getattr(collection_info, 'segments_count', 0),
                            "status": str(collection_info.status) if collection_info and hasattr(collection_info, 'status') else "unknown"
                        } if collection_info else None,
                        "config": {
                            "host": self.config.host,
                            "ports": self.config.ports,
                            "default_collection": self.config.collection_name,
                            "vector_size": self.config.vector_size,
                            "enabled": self.config.enabled
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, indent=2)
                }]
            }
            
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return self._error_response(uri, f"Failed to get collection info: {str(e)}")
    
    async def _handle_collection_responses(self, uri: str, collection_name: str):
        """Handle qdrant://collection/{collection}/responses/recent resource."""
        try:
            # Check if collection exists
            collections_response = await asyncio.to_thread(self.client.get_collections)
            available_collections = [c.name for c in collections_response.collections]
            
            if collection_name not in available_collections:
                return {
                    "contents": [{
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps({
                            "error": f"Collection '{collection_name}' not found",
                            "available_collections": available_collections,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    }]
                }
            
            # Get recent responses from the collection
            scroll_result = await asyncio.to_thread(
                self.client.scroll,
                collection_name=collection_name,
                limit=50,
                with_payload=True,
                with_vector=False
            )
            
            points = scroll_result[0] if scroll_result else []
            
            responses = []
            for point in points[:20]:  # Limit to 20 most recent
                payload = point.payload or {}
                
                # Decompress data if needed
                data = payload.get("data", "{}")
                if payload.get("compressed", False) and payload.get("compressed_data"):
                    try:
                        data = self._decompress_data(payload["compressed_data"])
                    except Exception as e:
                        logger.warning(f"Failed to decompress data for point {point.id}: {e}")
                
                # Parse response data
                try:
                    response_data = json.loads(data)
                except json.JSONDecodeError:
                    response_data = {"error": "Failed to parse stored data", "raw_data": data}
                
                responses.append({
                    "id": str(point.id),
                    "tool_name": payload.get("tool_name", "unknown"),
                    "timestamp": payload.get("timestamp", "unknown"),
                    "user_id": payload.get("user_id", "unknown"),
                    "user_email": payload.get("user_email", "unknown"),
                    "session_id": payload.get("session_id", "unknown"),
                    "payload_type": payload.get("payload_type", "unknown"),
                    "compressed": payload.get("compressed", False),
                    "response_data": response_data
                })
            
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps({
                        "qdrant_enabled": True,
                        "collection_name": collection_name,
                        "total_points": len(points),
                        "responses_shown": len(responses),
                        "responses": responses,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, indent=2)
                }]
            }
            
        except Exception as e:
            logger.error(f"Error getting collection responses: {e}")
            return self._error_response(uri, f"Failed to get collection responses: {str(e)}")
    
    async def _handle_collection_search(self, uri: str, collection_name: str, query: str):
        """Handle qdrant://search/{collection}/{query} resource."""
        try:
            # Use the existing search method but limit to specific collection
            results = await self.search(query, limit=10)
            
            # Filter results to only include those from the specified collection
            # Note: This is a simplified approach - ideally we'd search within the collection directly
            filtered_results = []
            for result in results:
                # Check if result is from the correct collection (this would need collection tracking)
                filtered_results.append(result)
            
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps({
                        "qdrant_enabled": True,
                        "collection": collection_name,
                        "query": query,
                        "total_results": len(filtered_results),
                        "results": filtered_results,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, indent=2)
                }]
            }
            
        except Exception as e:
            logger.error(f"Error searching collection: {e}")
            return self._error_response(uri, f"Failed to search collection: {str(e)}")
    
    async def _handle_global_search(self, uri: str, query: str):
        """Handle qdrant://search/{query} resource."""
        try:
            results = await self.search(query, limit=10)
            
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps({
                        "qdrant_enabled": True,
                        "query": query,
                        "total_results": len(results),
                        "results": results,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, indent=2)
                }]
            }
            
        except Exception as e:
            logger.error(f"Error in global search: {e}")
            return self._error_response(uri, f"Failed to search: {str(e)}")
    
    async def _store_response(self, context=None, response=None, **kwargs):
        """
        Store tool response in Qdrant with embedding.
        
        This method supports multiple calling patterns:
        1. With a MiddlewareContext object: _store_response(context, response)
        2. With individual parameters as positional args: _store_response("tool_name", response_data)
        3. With individual parameters as kwargs: _store_response(tool_name="name", tool_args={...}, response=data, ...)
        """
        # Check if called with all keyword arguments (template_manager.py style)
        if 'tool_name' in kwargs and 'response' in kwargs:
            # Called with all keyword arguments
            return await self._store_response_with_params(
                tool_name=kwargs.get('tool_name'),
                tool_args=kwargs.get('tool_args', {}),
                response=kwargs.get('response'),
                execution_time_ms=kwargs.get('execution_time_ms', 0),
                session_id=kwargs.get('session_id'),
                user_email=kwargs.get('user_email')
            )
        
        # Check if context is a string (tool_name) - positional args style
        elif isinstance(context, str):
            # Called with individual parameters as positional args
            return await self._store_response_with_params(
                tool_name=context,
                tool_args={},
                response=response,
                execution_time_ms=0,
                session_id=None,
                user_email=None
            )
        
        # Default case: context is a MiddlewareContext object
        elif context is not None and response is not None:
            # Called with MiddlewareContext object
            try:
                # Extract tool information from context safely
                tool_name = getattr(context, 'tool_name', None) or getattr(context, 'name', 'unknown_tool')
                arguments = getattr(context, 'arguments', None) or getattr(context, 'params', {})
                
                # Create response payload
                response_data = {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "response": response,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "user_id": getattr(context, 'user_id', 'unknown'),
                    "user_email": getattr(context, 'user_email', getattr(context, 'user_id', 'unknown')),
                    "session_id": str(uuid.uuid4()),
                    "payload_type": PayloadType.TOOL_RESPONSE.value
                }
                
                # Convert to JSON
                json_data = json.dumps(response_data, default=str)
                
                # Generate text for embedding
                embed_text = f"Tool: {tool_name}\nArguments: {json.dumps(arguments)}\nResponse: {str(response)[:1000]}"
                
                # Generate embedding
                embedding = await asyncio.to_thread(self.embedder.encode, embed_text)
                
                # Check if compression is needed
                compressed = self._should_compress(json_data)
                if compressed:
                    stored_data = self._compress_data(json_data)
                    logger.debug(f"📦 Compressed response: {len(json_data)} -> {len(stored_data)} bytes")
                else:
                    stored_data = json_data
                
                # Create point for Qdrant (use proper UUID format)
                _, qdrant_models = _get_qdrant_imports()
                point_id = str(uuid.uuid4())  # Generate UUID and convert to string
                point = qdrant_models['PointStruct'](
                    id=point_id,  # Use UUID string for Qdrant compatibility
                    vector=embedding.tolist(),
                    payload={
                        "tool_name": tool_name,
                        "timestamp": response_data["timestamp"],
                        "user_id": response_data["user_id"],
                        "user_email": response_data["user_email"],
                        "session_id": response_data["session_id"],
                        "payload_type": PayloadType.TOOL_RESPONSE.value,
                        "compressed": compressed,
                        "data": stored_data if not compressed else None,
                        "compressed_data": stored_data if compressed else None
                    }
                )
                
                # Store in Qdrant
                await asyncio.to_thread(
                    self.client.upsert,
                    collection_name=self.config.collection_name,
                    points=[point]
                )
                
                logger.debug(f"✅ Stored response for tool: {tool_name} (ID: {point_id})")
                
            except Exception as e:
                logger.error(f"❌ Failed to store response: {e}")
                raise
        
        # If we get here, we don't know how to handle the input
        else:
            raise ValueError("Invalid parameters for _store_response. Expected MiddlewareContext or keyword arguments.")
    
    async def _store_response_with_params(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        response: Any,
        execution_time_ms: int = 0,
        session_id: Optional[str] = None,
        user_email: Optional[str] = None
    ):
        """
        Store tool response in Qdrant with embedding using individual parameters.
        This method is called by _store_response when it's called with individual parameters
        instead of a MiddlewareContext object.
        
        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool
            response: Response from the tool
            execution_time_ms: Execution time in milliseconds
            session_id: Session ID
            user_email: User email
        """
        try:
            # Create response payload
            response_data = {
                "tool_name": tool_name,
                "arguments": tool_args,
                "response": response,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": user_email or "unknown",
                "user_email": user_email or "unknown",
                "session_id": session_id or str(uuid.uuid4()),
                "payload_type": PayloadType.TOOL_RESPONSE.value
            }
            
            # Convert to JSON
            json_data = json.dumps(response_data, default=str)
            
            # Generate text for embedding
            embed_text = f"Tool: {tool_name}\nArguments: {json.dumps(tool_args)}\nResponse: {str(response)[:1000]}"
            
            # Generate embedding
            embedding = await asyncio.to_thread(self.embedder.encode, embed_text)
            
            # Check if compression is needed
            compressed = self._should_compress(json_data)
            if compressed:
                stored_data = self._compress_data(json_data)
                logger.debug(f"📦 Compressed response: {len(json_data)} -> {len(stored_data)} bytes")
            else:
                stored_data = json_data
            
            # Create point for Qdrant (use proper UUID format)
            _, qdrant_models = _get_qdrant_imports()
            point_id = str(uuid.uuid4())  # Generate UUID and convert to string
            point = qdrant_models['PointStruct'](
                id=point_id,  # Use UUID string for Qdrant compatibility
                vector=embedding.tolist(),
                payload={
                    "tool_name": tool_name,
                    "timestamp": response_data["timestamp"],
                    "user_id": response_data["user_id"],
                    "user_email": response_data["user_email"],
                    "session_id": response_data["session_id"],
                    "payload_type": PayloadType.TOOL_RESPONSE.value,
                    "compressed": compressed,
                    "data": stored_data if not compressed else None,
                    "compressed_data": stored_data if compressed else None
                }
            )
            
            # Store in Qdrant
            await asyncio.to_thread(
                self.client.upsert,
                collection_name=self.config.collection_name,
                points=[point]
            )
            
            logger.debug(f"✅ Stored response for tool: {tool_name} (ID: {point_id})")
            
        except Exception as e:
            logger.error(f"❌ Failed to store response with params: {e}")
            raise
    
    async def _execute_semantic_search(
        self, 
        query_embedding, 
        qdrant_filter=None, 
        limit=None, 
        score_threshold=None
    ):
        """
        Execute semantic search using query_points (new Qdrant API).
        
        Args:
            query_embedding: The embedding vector for the query
            qdrant_filter: Optional Qdrant filter
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            
        Returns:
            List of ScoredPoint objects from Qdrant
        """
        search_response = await asyncio.to_thread(
            self.client.query_points,
            collection_name=self.config.collection_name,
            query=query_embedding.tolist(),
            query_filter=qdrant_filter,
            limit=limit or self.config.default_search_limit,
            score_threshold=score_threshold or self.config.score_threshold,
            with_payload=True
        )
        return search_response.points  # Extract points from response

    async def search(self, query: str, limit: int = None, score_threshold: float = None) -> List[Dict]:
        """
        Advanced search with query parsing support.
        
        Supports:
        - Direct ID lookup: "id:12345"
        - Filtered search: "user_email:test@gmail.com semantic query"
        - Multiple filters: "tool_name:search user_email:test@gmail.com documents"
        - Pure semantic search: "natural language query"
        
        Args:
            query: Search query (supports filters and semantic search)
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            
        Returns:
            List of matching responses with scores and metadata
        """
        if not self.client or not self.embedder:
            await self.initialize()
            
        if not self.client or not self.embedder:
            raise RuntimeError("Qdrant client or embedding model not available")
        
        try:
            # Parse the query to extract filters and semantic components
            parsed_query = _parse_search_query(query)
            logger.debug(f"🔍 Parsed query: {parsed_query}")
            
            search_results = []
            
            # Handle direct ID lookup
            if parsed_query["query_type"] == "id_lookup":
                target_id = parsed_query["id"]
                logger.debug(f"🎯 Looking up point by ID: {target_id}")
                
                try:
                    # Handle both string and UUID formats
                    try:
                        # Try to parse as UUID first
                        uuid_id = uuid.UUID(target_id)
                        search_id = uuid_id
                    except ValueError:
                        # If not a valid UUID, use as string
                        search_id = target_id
                    
                    points = await asyncio.to_thread(
                        self.client.retrieve,
                        collection_name=self.config.collection_name,
                        ids=[search_id],
                        with_payload=True
                    )
                    
                    if points:
                        point = points[0]
                        search_results = [{
                            'id': str(point.id),
                            'score': 1.0,  # Perfect match for direct lookup
                            'payload': point.payload
                        }]
                    logger.debug(f"📍 ID lookup found {len(search_results)} results")
                        
                except Exception as e:
                    logger.error(f"❌ ID lookup failed: {e}")
                    raise
            
            # Handle filtered search (with or without semantic component)
            else:
                qdrant_filter = None
                
                # Build Qdrant filter from parsed filters
                if parsed_query["filters"]:
                    try:
                        # Import Qdrant models for filtering
                        _, qdrant_models = _get_qdrant_imports()
                        Filter = qdrant_models['models'].Filter
                        FieldCondition = qdrant_models['models'].FieldCondition
                        MatchValue = qdrant_models['models'].MatchValue
                        
                        conditions = []
                        for filter_key, filter_value in parsed_query["filters"].items():
                            logger.debug(f"🏷️  Adding filter: {filter_key}={filter_value}")
                            conditions.append(
                                FieldCondition(
                                    key=filter_key,
                                    match=MatchValue(value=filter_value)
                                )
                            )
                        
                        if conditions:
                            qdrant_filter = Filter(must=conditions)
                            logger.debug(f"🔧 Built filter with {len(conditions)} conditions")
                    
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to build filter, falling back to simple search: {e}")
                        qdrant_filter = None
                
                # Perform semantic search if there's a semantic query
                if parsed_query["semantic_query"]:
                    logger.debug(f"🧠 Performing semantic search: '{parsed_query['semantic_query']}'")
                    
                    # Generate embedding for the semantic query
                    query_embedding = await asyncio.to_thread(
                        self.embedder.encode,
                        parsed_query["semantic_query"]
                    )
                    
                    # Use helper method for consistent query_points usage
                    search_results = await self._execute_semantic_search(
                        query_embedding=query_embedding,
                        qdrant_filter=qdrant_filter,
                        limit=limit,
                        score_threshold=score_threshold
                    )
                    
                    logger.debug(f"🎯 Semantic search found {len(search_results)} results")
                
                # If no semantic query, just filter and return results
                elif parsed_query["filters"]:
                    logger.debug("📋 Performing filter-only search")
                    
                    # Scroll with filter to get filtered results
                    scroll_result = await asyncio.to_thread(
                        self.client.scroll,
                        collection_name=self.config.collection_name,
                        scroll_filter=qdrant_filter,
                        limit=limit or self.config.default_search_limit,
                        with_payload=True
                    )
                    
                    # Convert scroll results to search result format
                    search_results = [{
                        'id': str(point.id),
                        'score': 1.0,  # Equal relevance for filter-only results
                        'payload': point.payload
                    } for point in scroll_result[0]]  # scroll returns (points, next_page_offset)
                    
                    logger.debug(f"📋 Filter search found {len(search_results)} results")
                
                # Default behavior for plain semantic search
                else:
                    logger.debug(f"🧠 Pure semantic search: '{query}'")
                    
                    # Generate embedding for the entire query
                    query_embedding = await asyncio.to_thread(self.embedder.encode, query)
                    
                    # Use helper method for consistent query_points usage
                    search_results = await self._execute_semantic_search(
                        query_embedding=query_embedding,
                        limit=limit,
                        score_threshold=score_threshold
                    )
                    
                    logger.debug(f"🧠 Pure semantic search found {len(search_results)} results")
            
            # Process and format results
            results = []
            for result in search_results:
                # Handle different result formats
                if hasattr(result, 'payload'):
                    # Standard Qdrant search result
                    payload = result.payload or {}
                    result_id = str(result.id)
                    score = result.score
                else:
                    # Custom format from our query parsing
                    payload = result.get('payload', {})
                    result_id = str(result.get('id', 'unknown'))
                    score = result.get('score', 0.0)
                
                # Decompress data if needed
                if payload.get("compressed", False):
                    data = self._decompress_data(payload["compressed_data"])
                else:
                    data = payload.get("data", "{}")
                
                # Parse response data
                try:
                    response_data = json.loads(data)
                except json.JSONDecodeError:
                    response_data = {"error": "Failed to parse stored data"}
                
                results.append({
                    "id": result_id,
                    "score": score,
                    "tool_name": payload.get("tool_name"),
                    "timestamp": payload.get("timestamp"),
                    "user_id": payload.get("user_id"),
                    "user_email": payload.get("user_email"),
                    "session_id": payload.get("session_id"),
                    "response_data": response_data,
                    "payload_type": payload.get("payload_type", "unknown")
                })
            
            logger.info(f"✅ Search completed: {len(results)} results for query '{query}'")
            return results
            
        except Exception as e:
            logger.error(f"❌ Search failed: {e}")
            raise
    
    @property
    def is_initialized(self) -> bool:
        """Check if middleware is fully initialized."""
        return self._initialized and self.client is not None and self.embedder is not None
    
    async def search_responses(self, query: str, filters: Dict = None, limit: int = 10) -> List[Dict]:
        """
        Search stored responses with optional filters.
        
        Args:
            query: Natural language search query
            filters: Dictionary of filter criteria
            limit: Maximum number of results
            
        Returns:
            List of matching responses
        """
        try:
            # Use the existing search method and apply filters
            results = await self.search(query, limit=limit)
            
            if filters:
                filtered_results = []
                for result in results:
                    match = True
                    if "tool_name" in filters and result.get("tool_name") != filters["tool_name"]:
                        match = False
                    if "user_email" in filters and result.get("user_email") != filters["user_email"]:
                        match = False
                    if match:
                        filtered_results.append(result)
                return filtered_results
            
            return results
        except Exception as e:
            logger.error(f"❌ Search responses failed: {e}")
            # Return empty list instead of raising to prevent tool failures
            return []
    
    async def get_analytics(self, start_date=None, end_date=None, group_by="tool_name") -> Dict:
        """
        Get analytics on stored tool responses.
        
        Args:
            start_date: Start date filter
            end_date: End date filter
            group_by: Field to group results by
            
        Returns:
            Analytics data dictionary
        """
        if not self.client:
            return {"error": "Qdrant client not available"}
        
        try:
            # Get all points from the collection
            _, qdrant_models = _get_qdrant_imports()
            
            # Scroll through all points in the collection
            points = await asyncio.to_thread(
                self.client.scroll,
                collection_name=self.config.collection_name,
                limit=1000  # Adjust as needed
            )
            
            analytics = {
                "total_responses": len(points[0]),
                "group_by": group_by,
                "groups": {}
            }
            
            for point in points[0]:
                payload = point.payload
                group_key = payload.get(group_by, "unknown")
                
                if group_key not in analytics["groups"]:
                    analytics["groups"][group_key] = {
                        "count": 0,
                        "timestamps": []
                    }
                
                analytics["groups"][group_key]["count"] += 1
                if "timestamp" in payload:
                    analytics["groups"][group_key]["timestamps"].append(payload["timestamp"])
            
            return analytics
            
        except Exception as e:
            logger.error(f"❌ Failed to get analytics: {e}")
            return {"error": str(e)}
    
    async def get_response_by_id(self, response_id: str) -> Optional[Dict]:
        """
        Get a specific response by its ID.
        
        Args:
            response_id: UUID of the stored response
            
        Returns:
            Response data or None if not found
        """
        if not self.client:
            return None
        
        try:
            # Handle both string and UUID formats
            try:
                # Try to parse as UUID first
                uuid_id = uuid.UUID(response_id)
                search_id = uuid_id
            except ValueError:
                # If not a valid UUID, use as string
                search_id = response_id
            
            # Retrieve the specific point by ID
            point = await asyncio.to_thread(
                self.client.retrieve,
                collection_name=self.config.collection_name,
                ids=[search_id]
            )
            
            if not point:
                return None
            
            payload = point[0].payload
            
            # Decompress data if needed
            if payload.get("compressed", False):
                data = self._decompress_data(payload["compressed_data"])
            else:
                data = payload.get("data", "{}")
            
            # Parse and return response data
            try:
                response_data = json.loads(data)
                return response_data
            except json.JSONDecodeError:
                return {"error": "Failed to parse stored data", "raw_data": data}
                
        except Exception as e:
            logger.error(f"❌ Failed to get response by ID: {e}")
            return {"error": str(e)}


def setup_enhanced_qdrant_tools(mcp, middleware):
    """Setup enhanced Qdrant tools using the correct FastMCP pattern."""
    
    @mcp.tool(
        name="search_tool_history",
        description="Advanced search through historical tool responses with support for: ID lookup (id:xxxxx), filtered search (user_email:test@gmail.com), combined filters with semantic search (user_email:test@gmail.com documents for gardening), and natural language queries",
        tags={"qdrant", "search", "history", "semantic", "vector", "filters", "advanced"},
        annotations={
            "title": "Advanced Search Tool History",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def search_tool_history(
        query: str,
        tool_name: Optional[str] = None,
        user_email: Optional[str] = None,
        limit: int = 10,
        user_google_email: Optional[str] = None
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

    @mcp.tool(
        name="get_tool_analytics",
        description="Get comprehensive analytics on tool usage, performance metrics, and patterns",
        tags={"qdrant", "analytics", "metrics", "performance", "usage"},
        annotations={
            "title": "Tool Analytics Dashboard",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def get_tool_analytics(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: str = "tool_name",
        user_google_email: Optional[str] = None
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
            from datetime import datetime
            start_dt = datetime.fromisoformat(start_date) if start_date else None
            end_dt = datetime.fromisoformat(end_date) if end_date else None
            
            analytics = await middleware.get_analytics(start_dt, end_dt, group_by)
            return json.dumps(analytics, indent=2)
        except Exception as e:
            return f"Analytics failed: {str(e)}"

    @mcp.tool(
        name="get_response_details",
        description="Retrieve full details and metadata of a specific stored tool response by its unique ID",
        tags={"qdrant", "details", "response", "lookup", "metadata"},
        annotations={
            "title": "Get Response Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def get_response_details(response_id: str, user_google_email: Optional[str] = None) -> str:
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


# Backward compatibility aliases
QdrantResponseMiddleware = QdrantUnifiedMiddleware
EnhancedQdrantResponseMiddleware = QdrantUnifiedMiddleware