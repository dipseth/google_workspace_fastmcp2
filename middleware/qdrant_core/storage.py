"""
Qdrant Storage Management Module

This module contains storage functionality extracted from the main
Qdrant middleware, including:
- Tool response storage and persistence
- Response serialization and embedding generation
- Point creation and Qdrant upsert operations
- Compression and metadata handling
- Multiple calling pattern support

This focused module handles all aspects of data storage in Qdrant
while maintaining async patterns, error handling, and execution tracking.
"""

import json
import uuid
import asyncio
import logging
import base64
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Union
from fastmcp.server.middleware import MiddlewareContext

from .client import QdrantClientManager
from .config import QdrantConfig, PayloadType
from .lazy_imports import get_qdrant_imports

logger = logging.getLogger(__name__)


def sanitize_for_json(obj) -> Union[str, Dict, list, int, float, bool, None]:
    """
    Sanitize data to be JSON-serializable, handling binary data, invalid UTF-8, and complex objects.
    Uses Pydantic-inspired patterns for robust serialization.
    
    Args:
        obj: Object to sanitize
        
    Returns:
        JSON-serializable version of the object
    """
    # Try Pydantic-style serialization for complex objects first
    try:
        # Import here to avoid circular dependencies
        from pydantic import TypeAdapter
        
        # For complex objects, try using TypeAdapter for robust serialization
        if hasattr(obj, '__dict__') or isinstance(obj, (dict, list)) and len(str(obj)) > 100:
            try:
                # Use TypeAdapter's dump_python for safe serialization
                adapter = TypeAdapter(type(obj))
                return adapter.dump_python(obj, mode='json')
            except Exception:
                # Fall back to manual sanitization
                pass
    except ImportError:
        # Pydantic not available, use manual sanitization
        pass
    
    # Manual sanitization for simple and edge cases
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        # Handle strings that might have invalid UTF-8
        if isinstance(obj, str):
            try:
                # Try to encode/decode to validate UTF-8
                obj.encode('utf-8')
                return obj
            except UnicodeEncodeError:
                # Replace invalid characters with replacement character
                return obj.encode('utf-8', errors='replace').decode('utf-8')
        return obj
    elif isinstance(obj, bytes):
        # Convert bytes to base64 or UTF-8 string
        try:
            # First try to decode as UTF-8
            return obj.decode('utf-8')
        except UnicodeDecodeError:
            # If not valid UTF-8, encode as base64 with clear prefix
            return f"base64:{base64.b64encode(obj).decode('utf-8')}"
    elif isinstance(obj, (list, tuple)):
        # Recursively sanitize list/tuple elements
        try:
            return [sanitize_for_json(item) for item in obj]
        except Exception:
            # If list processing fails, convert to safe representation
            return f"[List with {len(obj)} items - serialization failed]"
    elif isinstance(obj, dict):
        # Recursively sanitize dictionary
        sanitized = {}
        for key, value in obj.items():
            try:
                # Sanitize both key and value
                clean_key = sanitize_for_json(key)
                clean_value = sanitize_for_json(value)
                # Ensure key is a string
                if not isinstance(clean_key, str):
                    clean_key = str(clean_key)
                sanitized[clean_key] = clean_value
            except Exception as e:
                # If individual key/value fails, add safe placeholder
                safe_key = str(key) if key is not None else "unknown_key"
                sanitized[safe_key] = f"[Sanitization failed: {str(e)}]"
        return sanitized
    elif hasattr(obj, 'model_dump'):
        # Pydantic model - use its built-in serialization
        try:
            return obj.model_dump(mode='json')
        except Exception:
            # Fall back to __dict__ if model_dump fails
            return sanitize_for_json(obj.__dict__)
    elif hasattr(obj, '__dict__'):
        # Handle objects with attributes
        try:
            return sanitize_for_json(obj.__dict__)
        except Exception:
            return f"[Object of type {type(obj).__name__} - serialization failed]"
    else:
        # Convert everything else to string and sanitize
        try:
            str_obj = str(obj)
            return sanitize_for_json(str_obj)
        except Exception:
            return f"[Unserializable {type(obj).__name__} object]"


def validate_qdrant_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitize payload specifically for Qdrant compatibility.
    
    This function ensures that the payload can be serialized by Qdrant's HTTP client
    without encountering UTF-8 or JSON serialization errors.
    
    Args:
        payload: Dictionary payload to validate for Qdrant
        
    Returns:
        Validated and sanitized payload safe for Qdrant storage
        
    Raises:
        ValueError: If payload cannot be made Qdrant-compatible
    """
    try:
        # First sanitize all data
        sanitized_payload = sanitize_for_json(payload)
        
        # Ensure all keys are strings (Qdrant requirement)
        if not isinstance(sanitized_payload, dict):
            raise ValueError(f"Payload must be a dictionary, got {type(sanitized_payload)}")
        
        validated_payload = {}
        for key, value in sanitized_payload.items():
            # Ensure key is a valid string
            if not isinstance(key, str):
                key = str(key)
            
            # Validate key doesn't contain null bytes or other problematic characters
            if '\x00' in key:
                key = key.replace('\x00', '_NULL_')
            
            validated_payload[key] = value
        
        # Test JSON serialization to catch any remaining issues
        try:
            json.dumps(validated_payload, ensure_ascii=False)
        except (TypeError, ValueError, UnicodeDecodeError) as e:
            logger.warning(f"⚠️ Payload failed JSON serialization test, applying additional sanitization: {e}")
            # Apply more aggressive sanitization
            validated_payload = {
                str(k): str(v) if not isinstance(v, (dict, list, int, float, bool, type(None))) else v
                for k, v in validated_payload.items()
            }
            
            # Try again
            json.dumps(validated_payload, ensure_ascii=False)
        
        # Validate Qdrant-specific constraints
        payload_size = len(json.dumps(validated_payload))
        if payload_size > 1024 * 1024:  # 1MB limit
            logger.warning(f"⚠️ Large payload detected ({payload_size} bytes), consider compression")
        
        return validated_payload
        
    except Exception as e:
        logger.error(f"❌ Failed to validate payload for Qdrant: {e}")
        # Return a safe fallback payload
        return {
            "validation_error": str(e),
            "original_payload_type": str(type(payload)),
            "sanitization_timestamp": datetime.now(timezone.utc).isoformat()
        }


class QdrantStorageManager:
    """
    Manages storage operations for the Qdrant vector database.
    
    This class encapsulates all storage functionality including:
    - Tool response persistence with embeddings
    - Response serialization and compression
    - Point creation and Qdrant upsert operations
    - Multiple calling pattern support for flexibility
    - Execution time tracking and enhanced metadata
    """
    
    def __init__(self, client_manager: QdrantClientManager):
        """
        Initialize the Qdrant storage manager.
        
        Args:
            client_manager: QdrantClientManager instance for client operations
        """
        self.client_manager = client_manager
        self.config = client_manager.config
        
        logger.debug("🗃️ QdrantStorageManager initialized")
    
    async def store_response(self, context=None, response=None, **kwargs):
        """
        Store tool response in Qdrant with embedding.
        
        This method supports multiple calling patterns:
        1. With a MiddlewareContext object: store_response(context, response)
        2. With individual parameters as positional args: store_response("tool_name", response_data)
        3. With individual parameters as kwargs: store_response(tool_name="name", tool_args={...}, response=data, ...)
        
        Args:
            context: MiddlewareContext object, tool name string, or None
            response: Response data or None
            **kwargs: Additional parameters for flexible calling patterns
        """
        # Ensure client manager is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        if not self.client_manager.is_available:
            logger.warning("⚠️ Qdrant client not available, skipping storage")
            return
        
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
                # Extract tool information from context.message (following FastMCP pattern)
                tool_name = getattr(context.message, 'name', 'unknown_tool') if hasattr(context, 'message') else 'unknown_tool'
                arguments = getattr(context.message, 'arguments', {}) if hasattr(context, 'message') else {}
                
                # Extract user information from auth context
                from auth.context import get_user_email_context, get_session_context
                user_email = get_user_email_context() or 'unknown'
                session_id = get_session_context() or str(uuid.uuid4())
                
                # Properly serialize response (handle ToolResult objects)
                if hasattr(response, 'content'):
                    # FastMCP ToolResult object
                    serialized_response = response.content
                elif hasattr(response, 'to_dict'):
                    # Object with to_dict method
                    serialized_response = response.to_dict()
                elif hasattr(response, '__dict__'):
                    # Generic object with attributes
                    serialized_response = response.__dict__
                else:
                    # Convert to string as fallback
                    serialized_response = str(response)
                
                # Create response payload
                response_data = {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "response": serialized_response,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "user_id": user_email,
                    "user_email": user_email,
                    "session_id": session_id,
                    "payload_type": PayloadType.TOOL_RESPONSE.value
                }
                
                # Sanitize data for JSON serialization to prevent UTF-8 errors
                sanitized_data = sanitize_for_json(response_data)
                
                # Convert to JSON
                json_data = json.dumps(sanitized_data, default=str)
                
                # Generate text for embedding
                embed_text = f"Tool: {tool_name}\nArguments: {json.dumps(arguments)}\nResponse: {str(response)[:1000]}"
                
                # Generate embedding
                embedding = await asyncio.to_thread(self.client_manager.embedder.encode, embed_text)
                
                # Check if compression is needed
                compressed = self.client_manager._should_compress(json_data)
                if compressed:
                    stored_data = self.client_manager._compress_data(json_data)
                    logger.debug(f"📦 Compressed response: {len(json_data)} -> {len(stored_data)} bytes")
                else:
                    stored_data = json_data
                
                # Create point for Qdrant (use proper UUID format and validated payload)
                _, qdrant_models = get_qdrant_imports()
                point_id = str(uuid.uuid4())  # Generate UUID and convert to string
                
                # Create raw payload with Unix timestamp for efficient range queries
                raw_payload_data = {
                    "tool_name": tool_name,
                    "timestamp": sanitized_data["timestamp"],
                    "timestamp_unix": sanitized_data["timestamp_unix"],
                    "user_id": sanitized_data["user_id"],
                    "user_email": sanitized_data["user_email"],
                    "session_id": sanitized_data["session_id"],
                    "payload_type": PayloadType.TOOL_RESPONSE.value,
                    "compressed": compressed,
                    "data": stored_data if not compressed else None,
                    "compressed_data": stored_data if compressed else None
                }
                
                # Validate payload for Qdrant compatibility
                validated_payload_data = validate_qdrant_payload(raw_payload_data)
                
                point = qdrant_models['PointStruct'](
                    id=point_id,  # Use UUID string for Qdrant compatibility
                    vector=embedding.tolist(),
                    payload=validated_payload_data
                )
                
                # Store in Qdrant
                await asyncio.to_thread(
                    self.client_manager.client.upsert,
                    collection_name=self.config.collection_name,
                    points=[point]
                )
                
                logger.debug(f"✅ Stored response for tool: {tool_name} (ID: {point_id})")
                
            except Exception as e:
                logger.error(f"❌ Failed to store response: {e}")
                raise
        
        # If we get here, we don't know how to handle the input
        else:
            raise ValueError("Invalid parameters for store_response. Expected MiddlewareContext or keyword arguments.")
    
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
        This method incorporates execution time tracking and enhanced metadata.
        
        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool
            response: Response from the tool
            execution_time_ms: Execution time in milliseconds (enhanced metadata)
            session_id: Session ID
            user_email: User email
        """
        # Ensure client manager is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        if not self.client_manager.is_available:
            logger.warning("⚠️ Qdrant client not available, skipping storage")
            return
        
        # Check if embedder is available
        if self.client_manager.embedder is None:
            logger.warning("⚠️ Embedder not available, skipping storage")
            return
        
        try:
            # Properly serialize response (handle ToolResult objects)
            if hasattr(response, 'content'):
                # FastMCP ToolResult object
                serialized_response = response.content
            elif hasattr(response, 'to_dict'):
                # Object with to_dict method
                serialized_response = response.to_dict()
            elif hasattr(response, '__dict__'):
                # Generic object with attributes
                serialized_response = response.__dict__
            else:
                # Convert to string as fallback
                serialized_response = str(response)
            
            # Create response payload with execution time (enhanced metadata) and Unix timestamp
            now_dt = datetime.now(timezone.utc)
            response_data = {
                "tool_name": tool_name,
                "arguments": tool_args,
                "response": serialized_response,
                "timestamp": now_dt.isoformat(),
                "timestamp_unix": int(now_dt.timestamp()),  # Unix timestamp for efficient range queries
                "user_id": user_email or "unknown",
                "user_email": user_email or "unknown",
                "session_id": session_id or str(uuid.uuid4()),
                "payload_type": PayloadType.TOOL_RESPONSE.value,
                "execution_time_ms": execution_time_ms  # Enhanced metadata
            }
            
            # Sanitize data for JSON serialization to prevent UTF-8 errors
            sanitized_data = sanitize_for_json(response_data)
            
            # Convert to JSON
            json_data = json.dumps(sanitized_data, default=str)
            
            # Generate text for embedding
            embed_text = f"Tool: {tool_name}\nArguments: {json.dumps(tool_args)}\nResponse: {str(response)[:1000]}"
            
            # Check if embedder is available
            if self.client_manager.embedder is None:
                logger.warning("⚠️ Embedder not available, skipping storage")
                return
            
            # Generate embedding
            embedding = await asyncio.to_thread(self.client_manager.embedder.encode, embed_text)
            
            # Check if compression is needed
            compressed = self.client_manager._should_compress(json_data)
            if compressed:
                stored_data = self.client_manager._compress_data(json_data)
                logger.debug(f"📦 Compressed response: {len(json_data)} -> {len(stored_data)} bytes")
            else:
                stored_data = json_data
            
            # Create point for Qdrant (use proper UUID format and validated payload)
            _, qdrant_models = get_qdrant_imports()
            point_id = str(uuid.uuid4())  # Generate UUID and convert to string
            
            # Create payload with sanitized data including Unix timestamp
            raw_payload = {
                "tool_name": tool_name,
                "timestamp": sanitized_data["timestamp"],
                "timestamp_unix": sanitized_data["timestamp_unix"],
                "user_id": sanitized_data["user_id"],
                "user_email": sanitized_data["user_email"],
                "session_id": sanitized_data["session_id"],
                "payload_type": PayloadType.TOOL_RESPONSE.value,
                "execution_time_ms": execution_time_ms,  # Enhanced metadata
                "compressed": compressed,
                "data": stored_data if not compressed else None,
                "compressed_data": stored_data if compressed else None
            }
            
            # Validate payload specifically for Qdrant compatibility
            validated_payload = validate_qdrant_payload(raw_payload)
            
            point = qdrant_models['PointStruct'](
                id=point_id,  # Use UUID string for Qdrant compatibility
                vector=embedding.tolist(),
                payload=validated_payload
            )
            
            # Store in Qdrant
            await asyncio.to_thread(
                self.client_manager.client.upsert,
                collection_name=self.config.collection_name,
                points=[point]
            )
            
            logger.debug(f"✅ Stored response for tool: {tool_name} (ID: {point_id}, execution: {execution_time_ms}ms)")
            
        except Exception as e:
            logger.error(f"❌ Failed to store response with params: {e}")
            raise
    
    async def store_custom_payload(
        self,
        payload_type: PayloadType,
        data: Dict[str, Any],
        embedding_text: str,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store custom payload in Qdrant with embedding.
        
        Args:
            payload_type: Type of payload being stored
            data: Payload data to store
            embedding_text: Text to generate embedding from
            user_email: User email for attribution
            session_id: Session ID for tracking
            metadata: Additional metadata to store
            
        Returns:
            str: Point ID of the stored payload
        """
        # Ensure client manager is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        if not self.client_manager.is_available:
            raise RuntimeError("Qdrant client not available")
        
        try:
            # Create payload data
            payload_data = {
                "data": data,
                "payload_type": payload_type.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_email": user_email or "unknown",
                "session_id": session_id or str(uuid.uuid4()),
                "metadata": metadata or {}
            }
            
            # Sanitize and convert to JSON
            sanitized_payload = sanitize_for_json(payload_data)
            json_data = json.dumps(sanitized_payload, default=str)
            
            # Generate embedding
            embedding = await asyncio.to_thread(self.client_manager.embedder.encode, embedding_text)
            
            # Check if compression is needed
            compressed = self.client_manager._should_compress(json_data)
            if compressed:
                stored_data = self.client_manager._compress_data(json_data)
                logger.debug(f"📦 Compressed custom payload: {len(json_data)} -> {len(stored_data)} bytes")
            else:
                stored_data = json_data
            
            # Create point for Qdrant with validated payload
            _, qdrant_models = get_qdrant_imports()
            point_id = str(uuid.uuid4())
            
            # Create raw payload
            raw_point_payload = {
                "payload_type": payload_type.value,
                "timestamp": sanitized_payload["timestamp"],
                "user_email": sanitized_payload["user_email"],
                "session_id": sanitized_payload["session_id"],
                "compressed": compressed,
                "data": stored_data if not compressed else None,
                "compressed_data": stored_data if compressed else None
            }
            
            # Add metadata if provided
            if metadata:
                raw_point_payload.update(metadata)
            
            # Validate payload for Qdrant compatibility
            validated_point_payload = validate_qdrant_payload(raw_point_payload)
            
            point = qdrant_models['PointStruct'](
                id=point_id,
                vector=embedding.tolist(),
                payload=validated_point_payload
            )
            
            # Store in Qdrant
            await asyncio.to_thread(
                self.client_manager.client.upsert,
                collection_name=self.config.collection_name,
                points=[point]
            )
            
            logger.debug(f"✅ Stored custom payload: {payload_type.value} (ID: {point_id})")
            return point_id
            
        except Exception as e:
            logger.error(f"❌ Failed to store custom payload: {e}")
            raise
    
    async def bulk_store_responses(
        self,
        responses: list,
        batch_size: int = 10
    ) -> list:
        """
        Store multiple responses in batches for efficiency.
        
        Args:
            responses: List of response dictionaries with required fields
            batch_size: Number of responses to process in each batch
            
        Returns:
            list: Point IDs of stored responses
        """
        # Ensure client manager is initialized
        if not self.client_manager.is_initialized:
            await self.client_manager.initialize()
        
        if not self.client_manager.is_available:
            raise RuntimeError("Qdrant client not available")
        
        stored_ids = []
        
        for i in range(0, len(responses), batch_size):
            batch = responses[i:i + batch_size]
            batch_points = []
            
            for response_data in batch:
                try:
                    # Extract required fields
                    tool_name = response_data.get('tool_name', 'unknown')
                    tool_args = response_data.get('tool_args', {})
                    response = response_data.get('response', {})
                    user_email = response_data.get('user_email', 'unknown')
                    session_id = response_data.get('session_id', str(uuid.uuid4()))
                    execution_time_ms = response_data.get('execution_time_ms', 0)
                    
                    # Create payload
                    payload_data = {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "response": response,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "user_id": user_email,
                        "user_email": user_email,
                        "session_id": session_id,
                        "payload_type": PayloadType.TOOL_RESPONSE.value,
                        "execution_time_ms": execution_time_ms
                    }
                    
                    # Generate embedding text and embedding
                    embed_text = f"Tool: {tool_name}\nArguments: {json.dumps(tool_args)}\nResponse: {str(response)[:1000]}"
                    embedding = await asyncio.to_thread(self.client_manager.embedder.encode, embed_text)
                    
                    # Sanitize and handle compression
                    sanitized_payload = sanitize_for_json(payload_data)
                    json_data = json.dumps(sanitized_payload, default=str)
                    compressed = self.client_manager._should_compress(json_data)
                    stored_data = self.client_manager._compress_data(json_data) if compressed else json_data
                    
                    # Create point with validated payload data
                    _, qdrant_models = get_qdrant_imports()
                    point_id = str(uuid.uuid4())
                    
                    # Create raw payload
                    raw_bulk_payload = {
                        "tool_name": tool_name,
                        "timestamp": sanitized_payload["timestamp"],
                        "user_id": sanitized_payload["user_id"],
                        "user_email": sanitized_payload["user_email"],
                        "session_id": sanitized_payload["session_id"],
                        "payload_type": PayloadType.TOOL_RESPONSE.value,
                        "execution_time_ms": execution_time_ms,
                        "compressed": compressed,
                        "data": stored_data if not compressed else None,
                        "compressed_data": stored_data if compressed else None
                    }
                    
                    # Validate payload for Qdrant compatibility
                    validated_bulk_payload = validate_qdrant_payload(raw_bulk_payload)
                    
                    point = qdrant_models['PointStruct'](
                        id=point_id,
                        vector=embedding.tolist(),
                        payload=validated_bulk_payload
                    )
                    
                    batch_points.append(point)
                    stored_ids.append(point_id)
                    
                except Exception as e:
                    logger.error(f"❌ Failed to prepare response for bulk storage: {e}")
                    continue
            
            # Store batch in Qdrant
            if batch_points:
                try:
                    await asyncio.to_thread(
                        self.client_manager.client.upsert,
                        collection_name=self.config.collection_name,
                        points=batch_points
                    )
                    logger.debug(f"✅ Stored batch of {len(batch_points)} responses")
                except Exception as e:
                    logger.error(f"❌ Failed to store batch: {e}")
                    # Remove failed IDs from the list
                    for point in batch_points:
                        if point.id in stored_ids:
                            stored_ids.remove(point.id)
        
        logger.info(f"✅ Bulk storage completed: {len(stored_ids)} responses stored")
        return stored_ids
    
    async def cleanup_stale_data(self) -> Dict[str, Any]:
        """
        Clean up stale data older than the configured retention period.
        
        This method removes points from the Qdrant collection that are older than
        the configured cache_retention_days setting.
        
        Returns:
            Dict with cleanup results and statistics
        """
        if not self.client_manager.is_available:
            logger.warning("⚠️ Qdrant client not available, skipping cleanup")
            return {"status": "skipped", "reason": "client_unavailable"}
        
        try:
            # Calculate cutoff date
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.config.cache_retention_days)
            cutoff_iso = cutoff_date.isoformat()
            
            logger.info(f"🧹 Starting cleanup of data older than {cutoff_iso} ({self.config.cache_retention_days} days)")
            
            # Get Qdrant imports
            _, qdrant_models = get_qdrant_imports()
            
            # Create filter condition to find old points using string comparison
            # Since timestamps are stored as ISO strings, we use Match with range for strings
            filter_condition = qdrant_models['models'].Filter(
                must=[
                    qdrant_models['models'].FieldCondition(
                        key="timestamp",
                        match=qdrant_models['models'].MatchText(text=cutoff_iso),
                        # For datetime strings, we need to use match with less_than comparison
                        # But since MatchText doesn't support range, we'll use a different approach
                    )
                ]
            )
            
            # Alternative approach: Since we can't easily do range comparison on datetime strings,
            # let's search for all points and filter them in memory (less efficient but works)
            # For now, let's use a scroll through approach to find old points
            
            # First get all points with minimal payload
            search_result = await asyncio.to_thread(
                self.client_manager.client.scroll,
                collection_name=self.config.collection_name,
                limit=1000,  # Process in batches
                with_payload=["timestamp"]  # Only get timestamp for filtering
            )
            
            old_point_ids = []
            points = search_result[0] if search_result else []
            
            # Filter points by timestamp
            for point in points:
                if point.payload and "timestamp" in point.payload:
                    try:
                        point_timestamp_str = point.payload["timestamp"]
                        point_timestamp = datetime.fromisoformat(point_timestamp_str.replace('Z', '+00:00'))
                        if point_timestamp < cutoff_date:
                            old_point_ids.append(point.id)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"⚠️ Could not parse timestamp for point {point.id}: {e}")
                        continue
            
            points_to_delete = len(old_point_ids)
            logger.info(f"🗑️ Found {points_to_delete} points to clean up")
            
            if points_to_delete == 0:
                logger.info("✅ No stale data found, cleanup complete")
                return {
                    "status": "completed",
                    "points_deleted": 0,
                    "cutoff_date": cutoff_iso,
                    "retention_days": self.config.cache_retention_days
                }
            
            # First, count how many points will be deleted (for reporting)
            try:
                count_result = await asyncio.to_thread(
                    self.client_manager.client.count,
                    collection_name=self.config.collection_name,
                    count_filter=filter_condition
                )
                points_to_delete = count_result.count
                logger.info(f"🗑️ Found {points_to_delete} points to clean up")
                
                if points_to_delete == 0:
                    logger.info("✅ No stale data found, cleanup complete")
                    return {
                        "status": "completed",
                        "points_deleted": 0,
                        "cutoff_date": cutoff_iso,
                        "retention_days": self.config.cache_retention_days
                    }
                
            except Exception as e:
                logger.warning(f"⚠️ Could not count points for cleanup: {e}")
                points_to_delete = "unknown"
            
            # Delete the old points using the collected IDs
            if old_point_ids:
                try:
                    delete_result = await asyncio.to_thread(
                        self.client_manager.client.delete,
                        collection_name=self.config.collection_name,
                        points_selector=qdrant_models['models'].PointIdsList(
                            points=old_point_ids
                        )
                    )
                    
                    # Get actual count from delete operation if available
                    actual_deleted = len(old_point_ids)
                    
                    logger.info(f"✅ Cleanup completed: deleted {actual_deleted} stale points older than {cutoff_iso}")
                    
                    return {
                        "status": "completed",
                        "points_deleted": actual_deleted,
                        "cutoff_date": cutoff_iso,
                        "retention_days": self.config.cache_retention_days,
                        "collection_name": self.config.collection_name
                    }
                    
                except Exception as e:
                    logger.error(f"❌ Failed to delete stale points: {e}")
                    return {
                        "status": "failed",
                        "error": str(e),
                        "cutoff_date": cutoff_iso,
                        "retention_days": self.config.cache_retention_days
                    }
            else:
                logger.info("✅ No stale data found, cleanup complete")
                return {
                    "status": "completed",
                    "points_deleted": 0,
                    "cutoff_date": cutoff_iso,
                    "retention_days": self.config.cache_retention_days
                }
        
        except Exception as e:
            logger.error(f"❌ Cleanup operation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "retention_days": self.config.cache_retention_days
            }
    
    def get_storage_info(self) -> Dict[str, Any]:
        """
        Get information about the storage manager and its status.
        
        Returns:
            Dict with storage manager information and status
        """
        return {
            "client_manager_status": self.client_manager.get_connection_info(),
            "config": self.config.to_dict(),
            "available": self.client_manager.is_available,
            "initialized": self.client_manager.is_initialized,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }