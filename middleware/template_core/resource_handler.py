"""
Resource fetching and processing for template middleware.

Handles fetching resources from FastMCP context, extracting data from responses,
and providing fallback mechanisms for common resource types.

FastMCP v3 types:
- Context.read_resource() → ResourceResult (Pydantic model)
  - .contents: list[ResourceContent]
    - .content: str | bytes
    - .mime_type: str | None
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from config.enhanced_logging import setup_logger

from .cache_manager import CacheManager
from .utils import TemplateResolutionError

logger = setup_logger()


def _parse_json_content(text: str) -> Any:
    """Parse a string as JSON, returning the original string on failure."""
    if text.strip().startswith(("{", "[")):
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
    return text


class ResourceHandler:
    """
    Handles resource fetching, caching, and data extraction for template processing.

    Provides a comprehensive resource management system that:
    - Fetches resources from FastMCP context
    - Implements fallback strategies for common resource types
    - Extracts data from complex response structures
    - Navigates nested properties using dot notation
    - Integrates with caching layer for performance
    """

    def __init__(self, cache_manager: CacheManager, enable_debug_logging: bool = False):
        """
        Initialize the resource handler.

        Args:
            cache_manager: CacheManager instance for resource caching
            enable_debug_logging: Enable detailed debug logging
        """
        self.cache_manager = cache_manager
        self.enable_debug_logging = enable_debug_logging

    async def fetch_resource(self, resource_uri: str, fastmcp_context) -> Any:
        """
        Fetch a resource using FastMCP resource system with comprehensive fallback support.

        Args:
            resource_uri: URI of the resource to fetch
            fastmcp_context: FastMCP context for resource access

        Returns:
            Resource data from FastMCP, fallback sources, or cache

        Raises:
            TemplateResolutionError: When resource cannot be fetched from any source
        """
        # Ensure URI doesn't include property path (strip after first dot)
        if "://" in resource_uri:
            scheme_end = resource_uri.index("://")
            first_dot_after_scheme = resource_uri.find(".", scheme_end)
            if first_dot_after_scheme != -1:
                resource_uri = resource_uri[:first_dot_after_scheme]
                if self.enable_debug_logging:
                    logger.debug(f"🔧 Stripped property path from URI: {resource_uri}")

        # Check cache first
        cached = self.cache_manager.get_cached_resource(resource_uri)
        if cached is not None:
            if self.enable_debug_logging:
                logger.debug(f"📦 Using cached resource: {resource_uri}")
            return cached

        # Check if resource is already resolved in context state
        state_key = f"resource_cache_{resource_uri}"
        cached_data = await fastmcp_context.get_state(state_key)
        if cached_data:
            if self.enable_debug_logging:
                logger.debug(f"📦 Found resource in context state: {resource_uri}")
            self.cache_manager.cache_resource(resource_uri, cached_data)
            return cached_data

        # Try common URI fallbacks FIRST for reliability
        resource_data = await self._try_fallback_sources(resource_uri)

        # If we resolved via fallback, cache and return
        if resource_data is not None:
            # Store in context state
            await fastmcp_context.set_state(state_key, resource_data)
            # Cache locally
            self.cache_manager.cache_resource(resource_uri, resource_data)
            return resource_data

        # Otherwise, try the FastMCP resource system
        try:
            if self.enable_debug_logging:
                logger.debug(f"🔍 Fetching resource via FastMCP: {resource_uri}")

            # Context.read_resource() returns ResourceResult with .contents: list[ResourceContent]
            result = await fastmcp_context.read_resource(resource_uri)
            resource_content = result.contents[0]

            if self.enable_debug_logging:
                logger.debug(
                    f"📦 Raw resource type: {type(resource_content).__name__}"
                )

            resource_data = self.extract_resource_data(resource_content)

            if self.enable_debug_logging:
                logger.debug(
                    f"📄 Extracted data type: {type(resource_data).__name__}"
                )

            # Store in context state and cache
            await fastmcp_context.set_state(state_key, resource_data)
            self.cache_manager.cache_resource(resource_uri, resource_data)

            return resource_data

        except Exception as e:
            logger.error(f"❌ Failed to fetch resource '{resource_uri}': {e}")
            raise TemplateResolutionError(
                f"Failed to fetch resource '{resource_uri}': {e}"
            )

    async def _try_fallback_sources(self, resource_uri: str) -> Optional[Any]:
        """
        Try to resolve resource from fallback sources.

        Args:
            resource_uri: URI to resolve

        Returns:
            Resource data if resolved from fallback, None otherwise
        """
        resource_data = None

        if resource_uri == "user://current/email":
            try:
                from auth.context import get_user_email_context

                user_email = await get_user_email_context()
                resource_data = {"email": user_email or ""}
                if self.enable_debug_logging:
                    logger.debug(
                        f"✅ Resolved user email from auth context: {user_email}"
                    )
            except ImportError:
                if self.enable_debug_logging:
                    logger.debug("⚠️ auth.context not available for user email fallback")

        elif resource_uri == "user://current/profile":
            try:
                from auth.context import get_user_email_context

                user_email = await get_user_email_context()
                resource_data = {
                    "email": user_email or "",
                    "name": "",
                    "authenticated": bool(user_email),
                }
            except ImportError:
                if self.enable_debug_logging:
                    logger.debug(
                        "⚠️ auth.context not available for user profile fallback"
                    )

        elif resource_uri == "auth://session/current":
            try:
                from auth.context import get_user_email_context

                user_email = await get_user_email_context()
                resource_data = {
                    "authenticated": bool(user_email),
                    "user_email": user_email or "",
                    "session_active": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            except ImportError:
                if self.enable_debug_logging:
                    logger.debug("⚠️ auth.context not available for session fallback")

        return resource_data

    def extract_resource_data(self, resource_result: Any, depth: int = 0) -> Any:
        """
        Extract the actual data from a resource response.

        The primary path: ResourceContent (Pydantic) → model_dump() →
        {"content": "{JSON}", "mime_type": "application/json"} → parsed JSON dict.

        Args:
            resource_result: Raw resource result (ResourceContent, dict, str, etc.)
            depth: Current recursion depth (for safety)

        Returns:
            Extracted resource data as plain dict/list/primitive for template safety
        """
        MAX_DEPTH = 10
        if depth > MAX_DEPTH:
            logger.warning(
                f"⚠️ Maximum recursion depth ({MAX_DEPTH}) reached, returning as-is"
            )
            return resource_result

        try:
            extracted = None

            # Pydantic models (ResourceContent, etc.) → convert to dict first
            try:
                from pydantic import BaseModel

                if isinstance(resource_result, BaseModel):
                    if self.enable_debug_logging:
                        logger.debug(
                            f"🔄 Converting Pydantic model to dict: {type(resource_result).__name__}"
                        )
                    return self.extract_resource_data(
                        resource_result.model_dump(), depth + 1
                    )
            except ImportError:
                pass

            if isinstance(resource_result, dict):
                # ResourceContent.model_dump() → {"content": str, "mime_type": str, "meta": ...}
                if "content" in resource_result and "mime_type" in resource_result:
                    content_val = resource_result["content"]
                    mime = resource_result["mime_type"]
                    if isinstance(content_val, str):
                        if mime == "application/json" or content_val.strip().startswith(("{", "[")):
                            try:
                                extracted = json.loads(content_val)
                            except (json.JSONDecodeError, TypeError):
                                extracted = content_val
                        else:
                            extracted = content_val
                    else:
                        extracted = content_val

                # TextResourceContents.model_dump() → {"text": str, "mimeType": str, "uri": ...}
                elif "text" in resource_result and "uri" in resource_result:
                    text_val = resource_result["text"]
                    mime = resource_result.get("mimeType", "")
                    if isinstance(text_val, str):
                        if mime == "application/json" or text_val.strip().startswith(("{", "[")):
                            try:
                                extracted = json.loads(text_val)
                            except (json.JSONDecodeError, TypeError):
                                extracted = text_val
                        else:
                            extracted = text_val
                    else:
                        extracted = text_val

                # ReadResourceResult.model_dump() → {"contents": [{"text": ...}, ...]}
                elif "contents" in resource_result and resource_result["contents"]:
                    content_item = resource_result["contents"][0]
                    if "text" in content_item:
                        extracted = _parse_json_content(content_item["text"])
                    else:
                        extracted = content_item
                else:
                    # Plain dict - check if single-key wrapper to unwrap
                    if self._should_unwrap_dict(resource_result, depth):
                        if self.enable_debug_logging:
                            logger.debug(f"🔄 Unwrapping plain dict at depth {depth}")
                        key = next(iter(resource_result.keys()))
                        extracted = resource_result[key]
                    else:
                        extracted = resource_result

            elif isinstance(resource_result, str):
                extracted = _parse_json_content(resource_result)

            else:
                extracted = resource_result

            # Recursive unwrapping if needed (for nested structures)
            if isinstance(extracted, dict) and self._should_unwrap_dict(
                extracted, depth
            ):
                if self.enable_debug_logging:
                    logger.debug(
                        f"🔄 Attempting recursive unwrapping at depth {depth + 1}"
                    )
                return self.extract_resource_data(extracted, depth + 1)

            return extracted

        except (IndexError, KeyError, AttributeError) as e:
            logger.warning(f"⚠️ Unexpected resource structure at depth {depth}: {e}")
            return resource_result

    def _should_unwrap_dict(self, data: dict, depth: int) -> bool:
        """
        Determine if a dictionary should be recursively unwrapped.

        Args:
            data: Dictionary to check for unwrapping
            depth: Current recursion depth

        Returns:
            True if dictionary should be unwrapped, False otherwise
        """
        if depth >= 8 or len(data) != 1:
            return False

        key = next(iter(data.keys()))
        value = data[key]

        wrapper_keys = {
            "data",
            "result",
            "response",
            "content",
            "payload",
            "body",
            "value",
            "item",
            "object",
            "resource",
            "entity",
            "record",
        }

        key_lower = key.lower()
        is_wrapper_key = key_lower in wrapper_keys
        has_structured_value = isinstance(value, (dict, list)) and value

        if is_wrapper_key and has_structured_value:
            if self.enable_debug_logging:
                logger.debug(
                    f"🎯 Unwrapping detected: '{key}' -> {type(value).__name__}"
                )
            return True

        return False

    def extract_property(self, data: Any, property_path: str) -> Any:
        """
        Extract a property from data using dot-notation path.

        Args:
            data: Source data object or dictionary
            property_path: Dot-separated property path (e.g., 'user.profile.email')

        Returns:
            Extracted property value or None if path not found
        """
        if data is None:
            return None

        parts = property_path.split(".")
        current = data

        for part in parts:
            try:
                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list) and part.isdigit():
                    current = current[int(part)]
                elif hasattr(current, part):
                    current = getattr(current, part)
                else:
                    return None
            except (KeyError, IndexError, AttributeError, TypeError):
                return None

        return current
