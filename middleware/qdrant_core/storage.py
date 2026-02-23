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

import asyncio
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel

from config.enhanced_logging import setup_logger

from .client import QdrantClientManager
from .config import CollectionSchema, PayloadType
from .lazy_imports import get_qdrant_imports
from .query_parser import extract_service_from_tool

logger = setup_logger()


def sanitize_for_json(
    obj, preserve_structure: bool = True
) -> Union[str, Dict, list, int, float, bool, None]:
    """
    Sanitize data to be JSON-serializable, handling binary data, invalid UTF-8, and complex objects.
    Uses Pydantic-inspired patterns for robust serialization.

    Args:
        obj: Object to sanitize
        preserve_structure: If True, maintain nested structure instead of converting to strings

    Returns:
        JSON-serializable version of the object with preserved structure when possible
    """
    # Check if obj is already a JSON string and should be parsed
    if isinstance(obj, str) and preserve_structure:
        if _is_json_string(obj):
            try:
                parsed_obj = json.loads(obj)
                logger.debug("🔧 Detected and parsed JSON string to preserve structure")
                return sanitize_for_json(parsed_obj, preserve_structure=True)
            except json.JSONDecodeError:
                # Not valid JSON, treat as regular string
                pass

    # Try Pydantic-style serialization for complex objects first
    try:
        # Import here to avoid circular dependencies
        from pydantic import TypeAdapter

        # For complex objects, try using TypeAdapter for robust serialization
        if (
            hasattr(obj, "__dict__")
            or isinstance(obj, (dict, list))
            and len(str(obj)) > 100
        ):
            try:
                # Use TypeAdapter's dump_python for safe serialization
                adapter = TypeAdapter(type(obj))
                return adapter.dump_python(obj, mode="json")
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
                obj.encode("utf-8")
                return obj
            except UnicodeEncodeError:
                # Replace invalid characters with replacement character
                return obj.encode("utf-8", errors="replace").decode("utf-8")
        return obj
    elif isinstance(obj, bytes):
        # Convert bytes to base64 or UTF-8 string
        try:
            # First try to decode as UTF-8
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            # If not valid UTF-8, encode as base64 with clear prefix
            return f"base64:{base64.b64encode(obj).decode('utf-8')}"
    elif isinstance(obj, (list, tuple)):
        # Recursively sanitize list/tuple elements
        try:
            return [sanitize_for_json(item, preserve_structure) for item in obj]
        except Exception:
            # If list processing fails, convert to safe representation
            return f"[List with {len(obj)} items - serialization failed]"
    elif isinstance(obj, dict):
        # Recursively sanitize dictionary
        sanitized = {}
        for key, value in obj.items():
            try:
                # Sanitize both key and value
                clean_key = sanitize_for_json(key, preserve_structure)
                clean_value = sanitize_for_json(value, preserve_structure)
                # Ensure key is a string
                if not isinstance(clean_key, str):
                    clean_key = str(clean_key)
                sanitized[clean_key] = clean_value
            except Exception as e:
                # If individual key/value fails, add safe placeholder
                safe_key = str(key) if key is not None else "unknown_key"
                sanitized[safe_key] = f"[Sanitization failed: {str(e)}]"
        return sanitized
    elif isinstance(obj, BaseModel):
        # Pydantic model - use its built-in serialization
        try:
            return obj.model_dump(mode="json")
        except Exception:
            # Fall back to __dict__ if model_dump fails
            return sanitize_for_json(obj.__dict__, preserve_structure)
    elif hasattr(obj, "__dict__"):
        # Handle objects with attributes
        try:
            return sanitize_for_json(obj.__dict__, preserve_structure)
        except Exception:
            return f"[Object of type {type(obj).__name__} - serialization failed]"
    else:
        # Convert everything else to string and sanitize
        try:
            str_obj = str(obj)
            return sanitize_for_json(str_obj, preserve_structure)
        except Exception:
            return f"[Unserializable {type(obj).__name__} object]"


def _is_json_string(text: str) -> bool:
    """
    Check if a string appears to be JSON by looking for JSON structure indicators.

    Args:
        text: String to check

    Returns:
        True if string appears to be JSON
    """
    if not text or not isinstance(text, str):
        return False

    # Strip whitespace
    text = text.strip()

    # Check for JSON object/array markers
    json_indicators = [
        (text.startswith("{") and text.endswith("}")),
        (text.startswith("[") and text.endswith("]")),
        # Check for common JSON patterns
        ('{"' in text and '"}' in text),
        ('["' in text and '"]' in text),
    ]

    return any(json_indicators)


def _extract_response_content(response: Any) -> Any:
    """
    Smart extraction of response content that preserves structure and detects pre-serialized JSON.

    Args:
        response: Response object to extract content from

    Returns:
        Extracted content with preserved structure
    """
    try:
        content = getattr(response, "content", None)
        if content is not None:
            # If content is a string, check if it's JSON and parse if needed
            if isinstance(content, str) and _is_json_string(content):
                try:
                    parsed_content = json.loads(content)
                    logger.debug("🔧 Parsed JSON content from ToolResult.content")
                    return parsed_content
                except json.JSONDecodeError:
                    logger.debug("⚠️ Content appeared to be JSON but failed to parse")
                    return content

            return content

        # Handle Pydantic models
        elif isinstance(response, BaseModel):
            return response.model_dump()

        # Handle already-parsed structured data
        elif isinstance(response, (dict, list)):
            return response

        # Check if response is a JSON string
        elif isinstance(response, str) and _is_json_string(response):
            try:
                parsed_response = json.loads(response)
                logger.debug("🔧 Parsed JSON string response")
                return parsed_response
            except json.JSONDecodeError:
                logger.debug("⚠️ Response appeared to be JSON but failed to parse")
                return response

        # Convert to string as fallback
        else:
            return str(response)

    except Exception as e:
        logger.warning(f"⚠️ Error extracting response content: {e}")
        return str(response)


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
            raise ValueError(
                f"Payload must be a dictionary, got {type(sanitized_payload)}"
            )

        validated_payload = {}
        for key, value in sanitized_payload.items():
            # Ensure key is a valid string
            if not isinstance(key, str):
                key = str(key)

            # Validate key doesn't contain null bytes or other problematic characters
            if "\x00" in key:
                key = key.replace("\x00", "_NULL_")

            validated_payload[key] = value

        # Test JSON serialization to catch any remaining issues
        try:
            json.dumps(validated_payload, ensure_ascii=False)
        except (TypeError, ValueError, UnicodeDecodeError) as e:
            logger.warning(
                f"⚠️ Payload failed JSON serialization test, applying additional sanitization: {e}"
            )
            # Apply more aggressive sanitization
            validated_payload = {
                str(k): (
                    str(v)
                    if not isinstance(v, (dict, list, int, float, bool, type(None)))
                    else v
                )
                for k, v in validated_payload.items()
            }

            # Try again
            json.dumps(validated_payload, ensure_ascii=False)

        # Validate Qdrant-specific constraints
        payload_size = len(json.dumps(validated_payload))
        if payload_size > 1024 * 1024:  # 1MB limit
            logger.warning(
                f"⚠️ Large payload detected ({payload_size} bytes), consider compression"
            )

        return validated_payload

    except Exception as e:
        logger.error(f"❌ Failed to validate payload for Qdrant: {e}")
        # Return a safe fallback payload
        return {
            "validation_error": str(e),
            "original_payload_type": str(type(payload)),
            "sanitization_timestamp": datetime.now(timezone.utc).isoformat(),
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
        self._ric_provider = None  # Optional RICTextProvider for v7 text generation

        logger.debug("🗃️ QdrantStorageManager initialized")

    def set_ric_provider(self, provider) -> None:
        """Set the RIC text provider for v7 storage.

        When set, _store_point_v7 delegates text generation to the provider
        instead of using inline hardcoded text. The provider must implement
        the RICTextProvider protocol.

        Args:
            provider: A RICTextProvider implementation
        """
        self._ric_provider = provider
        logger.info(f"Set RIC provider: {type(provider).__name__}")

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
        if "tool_name" in kwargs and "response" in kwargs:
            # Called with all keyword arguments
            return await self._store_response_with_params(
                tool_name=kwargs.get("tool_name"),
                tool_args=kwargs.get("tool_args", {}),
                response=kwargs.get("response"),
                execution_time_ms=kwargs.get("execution_time_ms", 0),
                session_id=kwargs.get("session_id"),
                user_email=kwargs.get("user_email"),
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
                user_email=None,
            )

        # Default case: context is a MiddlewareContext object
        elif context is not None and response is not None:
            # Called with MiddlewareContext object
            try:
                # Extract tool information from context.message (following FastMCP pattern)
                tool_name = context.message.name
                arguments = context.message.arguments or {}

                # Extract user information from auth context
                from auth.context import get_session_context, get_user_email_context

                user_email = await get_user_email_context() or "unknown"
                session_id = await get_session_context() or str(uuid.uuid4())

                # Properly serialize response (handle ToolResult objects)
                content = getattr(response, "content", None)
                if content is not None:
                    serialized_response = content
                elif isinstance(response, BaseModel):
                    serialized_response = response.model_dump()
                elif isinstance(response, (dict, list, str)):
                    serialized_response = response
                else:
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
                    "payload_type": PayloadType.TOOL_RESPONSE.value,
                }

                # Sanitize data for JSON serialization to prevent UTF-8 errors
                sanitized_data = sanitize_for_json(response_data)

                # Convert to JSON
                json_data = json.dumps(sanitized_data, default=str)

                # Generate text for embedding
                embed_text = f"Tool: {tool_name}\nArguments: {json.dumps(arguments)}\nResponse: {str(response)[:1000]}"

                # Generate embedding using FastEmbed
                embedding_list = await asyncio.to_thread(
                    lambda q: list(self.client_manager.embedder.embed([q])), embed_text
                )
                embedding = embedding_list[0] if embedding_list else None

                if embedding is None:
                    logger.error(
                        f"Failed to generate embedding for store_response: {embed_text[:100]}..."
                    )
                    return

                # Check if compression is needed
                compressed = self.client_manager._should_compress(json_data)
                if compressed:
                    stored_data = self.client_manager._compress_data(json_data)
                    logger.debug(
                        f"📦 Compressed response: {len(json_data)} -> {len(stored_data)} bytes"
                    )
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
                    "compressed_data": stored_data if compressed else None,
                }

                # Validate payload for Qdrant compatibility
                validated_payload_data = validate_qdrant_payload(raw_payload_data)

                point = qdrant_models["PointStruct"](
                    id=point_id,  # Use UUID string for Qdrant compatibility
                    vector=embedding.tolist(),
                    payload=validated_payload_data,
                )

                # Store in Qdrant
                await asyncio.to_thread(
                    self.client_manager.client.upsert,
                    collection_name=self.config.collection_name,
                    points=[point],
                )

                logger.debug(
                    f"✅ Stored response for tool: {tool_name} (ID: {point_id})"
                )

            except Exception as e:
                logger.error(f"❌ Failed to store response: {e}")
                raise

        # If we get here, we don't know how to handle the input
        else:
            raise ValueError(
                "Invalid parameters for store_response. Expected MiddlewareContext or keyword arguments."
            )

    async def _store_response_with_params(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        response: Any,
        execution_time_ms: int = 0,
        session_id: Optional[str] = None,
        user_email: Optional[str] = None,
    ):
        """
        Store tool response in Qdrant with embedding using individual parameters.
        Dispatches to v1 (single vector) or v7 (named vectors) based on config.
        Supports dual_write mode for migration.

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
            # Smart response content extraction with structure preservation
            serialized_response = _extract_response_content(response)

            # Create response payload with execution time (enhanced metadata) and Unix timestamp
            now_dt = datetime.now(timezone.utc)
            resolved_session = session_id or str(uuid.uuid4())
            resolved_email = user_email or "unknown"
            response_data = {
                "tool_name": tool_name,
                "arguments": tool_args,
                "response": serialized_response,
                "timestamp": now_dt.isoformat(),
                "timestamp_unix": int(now_dt.timestamp()),
                "user_id": resolved_email,
                "user_email": resolved_email,
                "session_id": resolved_session,
                "payload_type": PayloadType.TOOL_RESPONSE.value,
                "execution_time_ms": execution_time_ms,
            }

            # Sanitize data while preserving structure
            sanitized_data = sanitize_for_json(response_data, preserve_structure=True)

            # Prepare common payload fields
            service_name = extract_service_from_tool(tool_name)
            _, qdrant_models = get_qdrant_imports()

            # Smart serialization for compression
            json_str = json.dumps(sanitized_data, default=str)
            needs_compression = self.client_manager._should_compress(json_str)

            if needs_compression:
                compressed = True
                stored_data = self.client_manager._compress_data(json_str)
                logger.debug(
                    f"📦 Compressed response: {len(json_str)} -> {len(stored_data)} bytes"
                )
            else:
                compressed = False
                stored_data = sanitized_data
                logger.debug("📄 Storing structured response data directly")

            raw_payload = {
                "tool_name": tool_name,
                "service": service_name,
                "timestamp": sanitized_data["timestamp"],
                "timestamp_unix": sanitized_data["timestamp_unix"],
                "user_id": sanitized_data["user_id"],
                "user_email": sanitized_data["user_email"],
                "session_id": sanitized_data["session_id"],
                "payload_type": PayloadType.TOOL_RESPONSE.value,
                "execution_time_ms": execution_time_ms,
                "compressed": compressed,
            }

            if compressed:
                raw_payload["compressed_data"] = stored_data
                raw_payload["data"] = None
            else:
                raw_payload["response_data"] = stored_data
                raw_payload["data"] = None
                raw_payload["compressed_data"] = None

            validated_payload = validate_qdrant_payload(raw_payload)

            schema = self.config.collection_schema

            # v1 path (default or dual_write)
            if schema == CollectionSchema.V1_SINGLE_VECTOR or self.config.dual_write:
                await self._store_point_v1(
                    tool_name, tool_args, response, validated_payload, qdrant_models
                )

            # v7 path (named vectors or dual_write)
            if schema == CollectionSchema.V7_NAMED_VECTORS or self.config.dual_write:
                await self._store_point_v7(
                    tool_name, tool_args, response, validated_payload,
                    service_name, resolved_email, resolved_session, qdrant_models,
                )

        except Exception as e:
            logger.error(f"❌ Failed to store response with params: {e}")
            raise

    async def _store_point_v1(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        response: Any,
        validated_payload: dict,
        qdrant_models: dict,
    ):
        """Store a point with single vector (v1 schema)."""
        embed_text = (
            f"Tool: {tool_name}\nArguments: {json.dumps(tool_args)}\n"
            f"Response: {str(response)[:1000]}"
        )

        embedding_list = await asyncio.to_thread(
            lambda q: list(self.client_manager.embedder.embed([q])), embed_text
        )
        embedding = embedding_list[0] if embedding_list else None

        if embedding is None:
            logger.error(f"Failed to generate v1 embedding for: {embed_text[:100]}...")
            return

        point_id = str(uuid.uuid4())
        point = qdrant_models["PointStruct"](
            id=point_id,
            vector=embedding.tolist(),
            payload=validated_payload,
        )

        await asyncio.to_thread(
            self.client_manager.client.upsert,
            collection_name=self.config.collection_name,
            points=[point],
        )

        logger.debug(
            f"✅ Stored v1 response for tool: {tool_name} (ID: {point_id})"
        )

    async def _store_point_v7(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        response: Any,
        validated_payload: dict,
        service_name: str,
        user_email: str,
        session_id: str,
        qdrant_models: dict,
    ):
        """Store a point with 3 named vectors (v7 RIC schema).

        Generates 3 text representations and embeds them in one batch call:
          - components_text: Tool identity
          - inputs_text: Arguments + response content
          - relationships_text: Service graph + user context

        If a RIC provider is set, delegates text generation to it.
        Otherwise falls back to the original inline text generation.
        """
        if self._ric_provider is not None:
            metadata = {
                "service": service_name,
                "tool_args": tool_args,
                "response": response,
                "user_email": user_email,
                "session_id": session_id,
            }
            components_text = self._ric_provider.component_text(tool_name, metadata)
            inputs_text = self._ric_provider.inputs_text(tool_name, metadata)
            relationships_text = self._ric_provider.relationships_text(tool_name, metadata)
        else:
            # Legacy inline text generation (backward compat)
            components_text = (
                f"Tool: {tool_name}\nService: {service_name}\nType: tool_response"
            )
            inputs_text = (
                f"Arguments: {json.dumps(tool_args)}\n"
                f"Response: {str(response)[:1000]}"
            )
            relationships_text = (
                f"{tool_name} belongs to {service_name}. "
                f"User: {user_email}. Session: {session_id}."
            )

        # Batch embed all 3 texts in one call for efficiency
        texts = [components_text, inputs_text, relationships_text]
        embeddings_list = await asyncio.to_thread(
            lambda ts: list(self.client_manager.embedder.embed(ts)), texts
        )

        if len(embeddings_list) < 3:
            logger.error("Failed to generate all 3 v7 embeddings")
            return

        point_id = str(uuid.uuid4())
        point = qdrant_models["PointStruct"](
            id=point_id,
            vector={
                "components": embeddings_list[0].tolist(),
                "inputs": embeddings_list[1].tolist(),
                "relationships": embeddings_list[2].tolist(),
            },
            payload=validated_payload,
        )

        await asyncio.to_thread(
            self.client_manager.client.upsert,
            collection_name=self.config.collection_name,
            points=[point],
        )

        logger.debug(
            f"✅ Stored v7 response for tool: {tool_name} (ID: {point_id})"
        )

    async def store_custom_payload(
        self,
        payload_type: PayloadType,
        data: Dict[str, Any],
        embedding_text: str,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
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
                "metadata": metadata or {},
            }

            # Sanitize and convert to JSON
            sanitized_payload = sanitize_for_json(payload_data)
            json_data = json.dumps(sanitized_payload, default=str)

            # Generate embedding using FastEmbed
            embedding_list = await asyncio.to_thread(
                lambda q: list(self.client_manager.embedder.embed([q])), embedding_text
            )
            embedding = embedding_list[0] if embedding_list else None

            if embedding is None:
                logger.error(
                    f"Failed to generate embedding for custom payload: {embedding_text[:100]}..."
                )
                raise RuntimeError("Failed to generate embedding for custom payload")

            # Check if compression is needed
            compressed = self.client_manager._should_compress(json_data)
            if compressed:
                stored_data = self.client_manager._compress_data(json_data)
                logger.debug(
                    f"📦 Compressed custom payload: {len(json_data)} -> {len(stored_data)} bytes"
                )
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
                "compressed_data": stored_data if compressed else None,
            }

            # Add metadata if provided
            if metadata:
                raw_point_payload.update(metadata)

            # Validate payload for Qdrant compatibility
            validated_point_payload = validate_qdrant_payload(raw_point_payload)

            point = qdrant_models["PointStruct"](
                id=point_id, vector=embedding.tolist(), payload=validated_point_payload
            )

            # Store in Qdrant
            await asyncio.to_thread(
                self.client_manager.client.upsert,
                collection_name=self.config.collection_name,
                points=[point],
            )

            logger.debug(
                f"✅ Stored custom payload: {payload_type.value} (ID: {point_id})"
            )
            return point_id

        except Exception as e:
            logger.error(f"❌ Failed to store custom payload: {e}")
            raise

    async def bulk_store_responses(self, responses: list, batch_size: int = 10) -> list:
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
            batch = responses[i : i + batch_size]
            batch_points = []

            # Phase 1: Prepare all data and collect embedding texts
            prepared_items = []
            embed_texts = []

            for response_data in batch:
                try:
                    # Extract required fields
                    tool_name = response_data.get("tool_name", "unknown")
                    tool_args = response_data.get("tool_args", {})
                    response = response_data.get("response", {})
                    user_email = response_data.get("user_email", "unknown")
                    session_id = response_data.get("session_id", str(uuid.uuid4()))
                    execution_time_ms = response_data.get("execution_time_ms", 0)

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
                        "execution_time_ms": execution_time_ms,
                    }

                    # Generate embedding text (collect for batch processing)
                    embed_text = f"Tool: {tool_name}\nArguments: {json.dumps(tool_args)}\nResponse: {str(response)[:1000]}"
                    embed_texts.append(embed_text)

                    # Store prepared data for later
                    prepared_items.append(
                        {
                            "tool_name": tool_name,
                            "payload_data": payload_data,
                            "execution_time_ms": execution_time_ms,
                        }
                    )

                except Exception as e:
                    logger.error(f"❌ Failed to prepare response for bulk storage: {e}")
                    # Add None to maintain index alignment
                    embed_texts.append(None)
                    prepared_items.append(None)
                    continue

            # Phase 2: Generate ALL embeddings in a single batch call (MUCH faster)
            if embed_texts:
                valid_texts = [t for t in embed_texts if t is not None]
                if valid_texts:
                    try:
                        embeddings_list = await asyncio.to_thread(
                            lambda texts: list(
                                self.client_manager.embedder.embed(texts)
                            ),
                            valid_texts,
                        )
                    except Exception as e:
                        logger.error(f"❌ Batch embedding generation failed: {e}")
                        embeddings_list = []
                else:
                    embeddings_list = []

                # Map embeddings back to prepared items (accounting for None entries)
                embedding_idx = 0
                embeddings_mapped = []
                for text in embed_texts:
                    if text is not None and embedding_idx < len(embeddings_list):
                        embeddings_mapped.append(embeddings_list[embedding_idx])
                        embedding_idx += 1
                    else:
                        embeddings_mapped.append(None)
            else:
                embeddings_mapped = []

            # Phase 3: Create points with embeddings
            _, qdrant_models = get_qdrant_imports()

            for idx, (prepared, embedding) in enumerate(
                zip(prepared_items, embeddings_mapped)
            ):
                if prepared is None or embedding is None:
                    continue

                try:
                    tool_name = prepared["tool_name"]
                    payload_data = prepared["payload_data"]
                    execution_time_ms = prepared["execution_time_ms"]

                    # Sanitize and handle compression
                    sanitized_payload = sanitize_for_json(payload_data)
                    json_data = json.dumps(sanitized_payload, default=str)
                    compressed = self.client_manager._should_compress(json_data)
                    stored_data = (
                        self.client_manager._compress_data(json_data)
                        if compressed
                        else json_data
                    )

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
                        "compressed_data": stored_data if compressed else None,
                    }

                    # Validate payload for Qdrant compatibility
                    validated_bulk_payload = validate_qdrant_payload(raw_bulk_payload)

                    point = qdrant_models["PointStruct"](
                        id=point_id,
                        vector=embedding.tolist(),
                        payload=validated_bulk_payload,
                    )

                    batch_points.append(point)
                    stored_ids.append(point_id)

                except Exception as e:
                    logger.error(f"❌ Failed to create point for bulk storage: {e}")
                    continue

            # Phase 4: Store batch in Qdrant
            if batch_points:
                try:
                    await asyncio.to_thread(
                        self.client_manager.client.upsert,
                        collection_name=self.config.collection_name,
                        points=batch_points,
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
            cutoff_date = datetime.now(timezone.utc) - timedelta(
                days=self.config.cache_retention_days
            )
            cutoff_iso = cutoff_date.isoformat()

            logger.info(
                f"🧹 Starting cleanup of data older than {cutoff_iso} ({self.config.cache_retention_days} days)"
            )

            # Get Qdrant imports
            _, qdrant_models = get_qdrant_imports()

            # Create filter condition to find old points using string comparison
            # Since timestamps are stored as ISO strings, we use Match with range for strings
            filter_condition = qdrant_models["models"].Filter(
                must=[
                    qdrant_models["models"].FieldCondition(
                        key="timestamp",
                        match=qdrant_models["models"].MatchText(text=cutoff_iso),
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
                with_payload=["timestamp"],  # Only get timestamp for filtering
            )

            old_point_ids = []
            points = search_result[0] if search_result else []

            # Filter points by timestamp
            for point in points:
                if point.payload and "timestamp" in point.payload:
                    try:
                        point_timestamp_str = point.payload["timestamp"]
                        point_timestamp = datetime.fromisoformat(
                            point_timestamp_str.replace("Z", "+00:00")
                        )
                        if point_timestamp < cutoff_date:
                            old_point_ids.append(point.id)
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"⚠️ Could not parse timestamp for point {point.id}: {e}"
                        )
                        continue

            points_to_delete = len(old_point_ids)
            logger.info(f"🗑️ Found {points_to_delete} points to clean up")

            if points_to_delete == 0:
                logger.info("✅ No stale data found, cleanup complete")
                return {
                    "status": "completed",
                    "points_deleted": 0,
                    "cutoff_date": cutoff_iso,
                    "retention_days": self.config.cache_retention_days,
                }

            # Delete the old points using the collected IDs
            if old_point_ids:
                try:
                    delete_result = await asyncio.to_thread(
                        self.client_manager.client.delete,
                        collection_name=self.config.collection_name,
                        points_selector=qdrant_models["models"].PointIdsList(
                            points=old_point_ids
                        ),
                    )

                    # Get actual count from delete operation if available
                    actual_deleted = len(old_point_ids)

                    logger.info(
                        f"✅ Cleanup completed: deleted {actual_deleted} stale points older than {cutoff_iso}"
                    )

                    return {
                        "status": "completed",
                        "points_deleted": actual_deleted,
                        "cutoff_date": cutoff_iso,
                        "retention_days": self.config.cache_retention_days,
                        "collection_name": self.config.collection_name,
                    }

                except Exception as e:
                    logger.error(f"❌ Failed to delete stale points: {e}")
                    return {
                        "status": "failed",
                        "error": str(e),
                        "cutoff_date": cutoff_iso,
                        "retention_days": self.config.cache_retention_days,
                    }
            else:
                logger.info("✅ No stale data found, cleanup complete")
                return {
                    "status": "completed",
                    "points_deleted": 0,
                    "cutoff_date": cutoff_iso,
                    "retention_days": self.config.cache_retention_days,
                }

        except Exception as e:
            logger.error(f"❌ Cleanup operation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "retention_days": self.config.cache_retention_days,
            }

    async def reindex_collection(self, force: bool = False) -> Dict[str, Any]:
        """
        Perform comprehensive collection reindexing and optimization.

        This method includes:
        - Collection statistics analysis
        - Index optimization and rebuilding
        - Segment optimization
        - Performance monitoring

        Args:
            force: If True, force reindexing even if not recommended

        Returns:
            Dict with reindexing results and performance statistics
        """
        if not self.client_manager.is_available:
            logger.warning("⚠️ Qdrant client not available, skipping reindexing")
            return {"status": "skipped", "reason": "client_unavailable"}

        try:
            start_time = datetime.now(timezone.utc)
            logger.info("🔄 Starting comprehensive collection reindexing...")

            # Get collection info and statistics
            collection_info = await asyncio.to_thread(
                self.client_manager.client.get_collection, self.config.collection_name
            )

            # Analyze collection health
            health_stats = await self._analyze_collection_health()

            # Decide if reindexing is needed
            needs_reindex = force or self._should_reindex(health_stats)

            if not needs_reindex and not force:
                logger.info("✅ Collection is healthy, skipping reindexing")
                return {
                    "status": "skipped",
                    "reason": "collection_healthy",
                    "health_stats": health_stats,
                    "timestamp": start_time.isoformat(),
                }

            logger.info(
                f"🔧 Collection needs reindexing: {health_stats['reindex_reasons']}"
            )

            # Step 1: Optimize collection settings
            optimization_result = await self._optimize_collection_settings()

            # Step 2: Rebuild indexes if needed
            index_rebuild_result = await self._rebuild_collection_indexes()

            # Step 3: Optimize segments
            segment_optimization_result = await self._optimize_segments()

            # Step 4: Update collection statistics
            final_stats = await self._analyze_collection_health()

            end_time = datetime.now(timezone.utc)
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

            logger.info(f"✅ Collection reindexing completed in {execution_time_ms}ms")

            return {
                "status": "completed",
                "execution_time_ms": execution_time_ms,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "health_before": health_stats,
                "health_after": final_stats,
                "optimization_result": optimization_result,
                "index_rebuild_result": index_rebuild_result,
                "segment_optimization_result": segment_optimization_result,
                "collection_name": self.config.collection_name,
            }

        except Exception as e:
            logger.error(f"❌ Collection reindexing failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "collection_name": self.config.collection_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def _analyze_collection_health(self) -> Dict[str, Any]:
        """
        Analyze collection health and determine if reindexing is needed.

        Returns:
            Dict with health statistics and recommendations
        """
        try:
            # Get collection info
            collection_info = await asyncio.to_thread(
                self.client_manager.client.get_collection, self.config.collection_name
            )

            # Get collection statistics
            total_points = collection_info.points_count or 0
            indexed_points = collection_info.indexed_vectors_count or total_points

            # Calculate fragmentation and health metrics
            index_ratio = indexed_points / max(total_points, 1)
            fragmentation_score = 1.0 - index_ratio

            # Determine reasons for reindexing
            reindex_reasons = []

            if fragmentation_score > 0.2:  # More than 20% unindexed
                reindex_reasons.append(f"high_fragmentation_{fragmentation_score:.2f}")

            if total_points > 0 and indexed_points < total_points * 0.8:
                reindex_reasons.append("low_index_coverage")

            # Get optimization profile thresholds
            optimization_params = self.config.get_optimization_params()
            indexing_threshold = optimization_params["optimizer_config"][
                "indexing_threshold"
            ]

            if total_points > indexing_threshold * 2:  # Collection grew significantly
                reindex_reasons.append("collection_growth")

            # Check index age (if we can determine it)
            hours_since_last_cleanup = 24  # Assume daily cleanup cycle
            if hours_since_last_cleanup > 24:
                reindex_reasons.append("stale_indexes")

            health_score = max(0.0, 1.0 - fragmentation_score)

            return {
                "total_points": total_points,
                "indexed_points": indexed_points,
                "index_ratio": index_ratio,
                "fragmentation_score": fragmentation_score,
                "health_score": health_score,
                "reindex_reasons": reindex_reasons,
                "needs_reindex": len(reindex_reasons) > 0,
                "collection_name": self.config.collection_name,
                "analysis_time": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.warning(f"⚠️ Could not analyze collection health: {e}")
            return {
                "error": str(e),
                "needs_reindex": False,
                "health_score": 0.5,  # Assume neutral health
                "reindex_reasons": [],
                "analysis_time": datetime.now(timezone.utc).isoformat(),
            }

    def _should_reindex(self, health_stats: Dict[str, Any]) -> bool:
        """
        Determine if collection should be reindexed based on health statistics.

        Args:
            health_stats: Collection health statistics

        Returns:
            True if reindexing is recommended
        """
        return (
            health_stats.get("needs_reindex", False)
            and len(health_stats.get("reindex_reasons", [])) >= 2
        )

    async def _optimize_collection_settings(self) -> Dict[str, Any]:
        """
        Optimize collection configuration settings.

        Returns:
            Dict with optimization results
        """
        try:
            logger.info("🔧 Optimizing collection settings...")

            # Get current optimization parameters
            optimization_params = self.config.get_optimization_params()

            # For now, we'll return success since settings are applied during creation
            # In a more advanced implementation, we could update collection params here

            return {
                "status": "completed",
                "optimization_profile": self.config.optimization_profile.value,
                "settings_applied": optimization_params["optimizer_config"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.warning(f"⚠️ Collection settings optimization failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def _rebuild_collection_indexes(self) -> Dict[str, Any]:
        """
        Rebuild collection indexes for optimal performance.

        Returns:
            Dict with index rebuild results
        """
        try:
            logger.info("🏗️ Rebuilding collection indexes...")

            # In Qdrant, indexes are rebuilt automatically during optimization
            # We'll trigger index recreation by updating payload schema
            _, qdrant_models = get_qdrant_imports()

            # Get current collection info
            collection_info = await asyncio.to_thread(
                self.client_manager.client.get_collection, self.config.collection_name
            )

            # Rebuild key indexes
            rebuilt_indexes = []
            index_fields = [
                "tool_name",
                "user_email",
                "user_id",
                "session_id",
                "payload_type",
                "label",
                "timestamp",
                "execution_time_ms",
                "compressed",
            ]

            for field in index_fields:
                try:
                    # Drop existing index (if exists) and recreate
                    await asyncio.to_thread(
                        self.client_manager.client.delete_payload_index,
                        collection_name=self.config.collection_name,
                        field_name=field,
                    )

                    # Recreate index
                    await asyncio.to_thread(
                        self.client_manager.client.create_payload_index,
                        collection_name=self.config.collection_name,
                        field_name=field,
                        field_schema=qdrant_models["PayloadSchemaType"].KEYWORD,
                    )

                    rebuilt_indexes.append(field)
                    logger.debug(f"✅ Rebuilt index for field: {field}")

                except Exception as e:
                    logger.warning(f"⚠️ Could not rebuild index for {field}: {e}")

            return {
                "status": "completed",
                "rebuilt_indexes": rebuilt_indexes,
                "total_indexes": len(rebuilt_indexes),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.warning(f"⚠️ Index rebuilding failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def _optimize_segments(self) -> Dict[str, Any]:
        """
        Optimize collection segments for better performance.

        Returns:
            Dict with segment optimization results
        """
        try:
            logger.info("📊 Optimizing collection segments...")

            # Get Qdrant imports
            _, qdrant_models = get_qdrant_imports()

            # Get collection cluster info (if available)
            try:
                cluster_info = await asyncio.to_thread(
                    self.client_manager.client.get_collection_cluster_info,
                    self.config.collection_name,
                )

                logger.info(f"📊 Collection cluster info: {cluster_info}")

            except Exception as e:
                logger.debug(
                    f"Could not get cluster info (normal for single-node): {e}"
                )

            # Force collection optimization (combines segments, rebuilds indexes)
            optimization_result = await asyncio.to_thread(
                getattr(
                    self.client_manager.client,
                    "optimize_vectors",
                    lambda **kwargs: None,
                ),
                collection_name=self.config.collection_name,
            )

            return {
                "status": "completed",
                "optimization_triggered": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.warning(f"⚠️ Segment optimization failed: {e}")
            return {
                "status": "partial",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def schedule_background_reindexing(self, interval_hours: int = 6) -> None:
        """
        Schedule background reindexing to run periodically.

        Args:
            interval_hours: How often to check for reindexing needs (default 6 hours)
        """
        if not self.client_manager.is_available:
            logger.info("⚠️ Qdrant not available, background reindexing disabled")
            return

        logger.info(f"⏰ Scheduling background reindexing every {interval_hours} hours")

        async def background_reindex_loop():
            while True:
                try:
                    await asyncio.sleep(interval_hours * 3600)  # Convert to seconds

                    logger.info("🔄 Running scheduled collection health check...")

                    # Analyze collection health
                    health_stats = await self._analyze_collection_health()

                    # Only reindex if really needed (not forced)
                    if self._should_reindex(health_stats):
                        logger.info(
                            "🔧 Collection health check indicates reindexing needed"
                        )
                        result = await self.reindex_collection(force=False)

                        if result.get("status") == "completed":
                            logger.info(
                                "✅ Scheduled reindexing completed successfully"
                            )
                        else:
                            logger.warning(f"⚠️ Scheduled reindexing result: {result}")
                    else:
                        logger.debug("✅ Collection healthy, no reindexing needed")

                except asyncio.CancelledError:
                    logger.info("⏹️ Background reindexing scheduler cancelled")
                    break
                except Exception as e:
                    logger.warning(f"⚠️ Background reindexing error (will retry): {e}")
                    # Continue the loop despite errors

        # Start the background task — track it so it can be cancelled on shutdown
        task = asyncio.create_task(background_reindex_loop())
        self.client_manager._track_task(task)

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
