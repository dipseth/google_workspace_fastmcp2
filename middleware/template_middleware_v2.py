"""
Streamlined Template Parameter Substitution Middleware for FastMCP2

This middleware provides automatic template parameter substitution by resolving
resource URIs during tool call execution. It transforms template expressions
like {{user://current/email.email}} into actual values by:

1. Intercepting tool calls
2. Finding template expressions in parameters
3. Resolving resources via FastMCP context
4. Extracting values from resource response structure
5. Substituting the resolved values

Key Features:
- Simple and focused implementation
- Direct resource resolution via middleware hooks
- Property path extraction (e.g., .email from user://current/email)
- Minimal dependencies (no Jinja2)
- Efficient caching of resolved resources
"""

import re
import json
import logging
from typing import Any, Dict, Optional, Union, List
from datetime import datetime, timedelta

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError
from mcp.server.lowlevel.helper_types import ReadResourceContents

logger = logging.getLogger(__name__)


class TemplateResolutionError(Exception):
    """Raised when template resolution fails."""
    pass


class StreamlinedTemplateMiddleware(Middleware):
    """
    Streamlined template parameter substitution middleware.
    
    This middleware intercepts tool calls and resolves template expressions
    in parameters by fetching resources and extracting values from their
    response structure.
    """
    
    # Pattern to match template expressions like {{user://current/email.email}}
    TEMPLATE_PATTERN = re.compile(r'\{\{([a-zA-Z][a-zA-Z0-9]*://[^}]+)\}\}')
    
    def __init__(
        self,
        enable_caching: bool = True,
        cache_ttl_seconds: int = 300,
        enable_debug_logging: bool = False
    ):
        """
        Initialize the streamlined template middleware.
        
        Args:
            enable_caching: Enable caching of resolved resources
            cache_ttl_seconds: Cache time-to-live in seconds
            enable_debug_logging: Enable detailed debug logging
        """
        self.enable_caching = enable_caching
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enable_debug_logging = enable_debug_logging
        
        # Resource cache: {resource_uri: {data: Any, expires_at: datetime}}
        self._resource_cache: Dict[str, Dict[str, Any]] = {}
        
        logger.info("✨ StreamlinedTemplateMiddleware initialized")
        logger.info(f"   Caching: {'enabled' if enable_caching else 'disabled'}")
        logger.info(f"   Cache TTL: {cache_ttl_seconds} seconds")
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Intercept tool calls and resolve template parameters.
        
        This hook is called when a tool is being executed. We:
        1. Extract the tool arguments
        2. Find and resolve any template expressions
        3. Replace them with resolved values
        4. Continue with the tool execution
        """
        tool_name = getattr(context.message, 'name', 'unknown')
        
        if self.enable_debug_logging:
            logger.debug(f"🔧 Processing tool call: {tool_name}")
        
        # Check if we have FastMCP context for resource resolution
        if not hasattr(context, 'fastmcp_context') or not context.fastmcp_context:
            # No context available, continue without template resolution
            if self.enable_debug_logging:
                logger.debug(f"⚠️ No FastMCP context available for tool: {tool_name}")
            return await call_next(context)
        
        try:
            # Get the tool arguments
            original_args = getattr(context.message, 'arguments', {})
            
            if original_args:
                # Resolve template parameters
                resolved_args = await self._resolve_parameters(
                    original_args,
                    context.fastmcp_context,
                    tool_name
                )
                
                # Update the message arguments if anything was resolved
                if resolved_args != original_args:
                    context.message.arguments = resolved_args
                    if self.enable_debug_logging:
                        logger.debug(f"✅ Resolved templates for tool: {tool_name}")
            
            # Continue with the tool execution
            return await call_next(context)
            
        except Exception as e:
            logger.error(f"❌ Template resolution failed for tool {tool_name}: {e}")
            # Continue without template resolution on error
            return await call_next(context)
    
    async def _resolve_parameters(
        self,
        parameters: Dict[str, Any],
        fastmcp_context,
        tool_name: str
    ) -> Dict[str, Any]:
        """
        Recursively resolve template expressions in parameters.
        
        Args:
            parameters: Dictionary of parameters to resolve
            fastmcp_context: FastMCP context for resource access
            tool_name: Name of the tool being executed
            
        Returns:
            Dictionary with resolved parameters
        """
        resolved = {}
        
        for key, value in parameters.items():
            resolved[key] = await self._resolve_value(
                value,
                fastmcp_context,
                f"{tool_name}.{key}"
            )
        
        return resolved
    
    async def _resolve_value(
        self,
        value: Any,
        fastmcp_context,
        param_path: str
    ) -> Any:
        """
        Resolve a single value, which might contain template expressions.
        
        Args:
            value: The value to resolve (can be string, dict, list, etc.)
            fastmcp_context: FastMCP context for resource access
            param_path: Path to this parameter for debugging
            
        Returns:
            The resolved value
        """
        if isinstance(value, str):
            # Check for template expressions in strings
            return await self._resolve_string_templates(value, fastmcp_context, param_path)
            
        elif isinstance(value, dict):
            # Recursively resolve dictionary values
            resolved_dict = {}
            for k, v in value.items():
                resolved_dict[k] = await self._resolve_value(
                    v,
                    fastmcp_context,
                    f"{param_path}.{k}"
                )
            return resolved_dict
            
        elif isinstance(value, list):
            # Recursively resolve list items
            resolved_list = []
            for i, item in enumerate(value):
                resolved_item = await self._resolve_value(
                    item,
                    fastmcp_context,
                    f"{param_path}[{i}]"
                )
                resolved_list.append(resolved_item)
            return resolved_list
            
        else:
            # Return other types as-is
            return value
    
    async def _resolve_string_templates(
        self,
        text: str,
        fastmcp_context,
        param_path: str
    ) -> Any:
        """
        Resolve template expressions in a string.
        
        Args:
            text: String that might contain template expressions
            fastmcp_context: FastMCP context for resource access
            param_path: Path to this parameter for debugging
            
        Returns:
            The string with templates resolved, or parsed JSON if the entire
            string was a single template that resolved to a JSON object
        """
        # Find all template expressions
        matches = list(self.TEMPLATE_PATTERN.finditer(text))
        
        if not matches:
            # No templates found
            return text
        
        # Special case: if the entire string is a single template, 
        # we might return a non-string value
        if len(matches) == 1 and matches[0].group(0) == text.strip():
            # The entire string is a single template
            template_expr = matches[0].group(1)
            resolved = await self._resolve_template_expression(
                template_expr,
                fastmcp_context,
                param_path
            )
            return resolved  # Could be string, dict, list, etc.
        
        # Multiple templates or template is part of a larger string
        # Replace each template with its string representation
        result = text
        for match in reversed(matches):  # Process in reverse to maintain positions
            template_expr = match.group(1)
            resolved = await self._resolve_template_expression(
                template_expr,
                fastmcp_context,
                param_path
            )
            
            # Convert to string for replacement
            if isinstance(resolved, str):
                replacement = resolved
            else:
                replacement = json.dumps(resolved)
            
            # Replace the template expression
            result = result[:match.start()] + replacement + result[match.end():]
        
        return result
    
    async def _resolve_template_expression(
        self,
        expression: str,
        fastmcp_context,
        param_path: str
    ) -> Any:
        """
        Resolve a single template expression like "user://current/email.email".
        
        Args:
            expression: The template expression (without {{ }})
            fastmcp_context: FastMCP context for resource access
            param_path: Path to this parameter for debugging
            
        Returns:
            The resolved value from the resource
        """
        # Split expression into resource URI and property path
        # e.g., "user://current/email.email" -> ("user://current/email", "email")
        if '.' in expression and '://' in expression:
            # Find the first dot after the URI scheme
            scheme_end = expression.index('://')
            first_dot_after_scheme = expression.find('.', scheme_end)
            
            if first_dot_after_scheme != -1:
                resource_uri = expression[:first_dot_after_scheme]
                property_path = expression[first_dot_after_scheme + 1:]
            else:
                resource_uri = expression
                property_path = None
        else:
            resource_uri = expression
            property_path = None
        
        if self.enable_debug_logging:
            logger.debug(f"📍 Resolving: {resource_uri}")
            if property_path:
                logger.debug(f"   Property path: {property_path}")
        
        # Fetch the resource
        resource_data = await self._fetch_resource(resource_uri, fastmcp_context)
        
        # Extract property if specified
        if property_path:
            result = self._extract_property(resource_data, property_path)
            if self.enable_debug_logging:
                logger.debug(f"   Extracted value: {repr(result)}")
        else:
            result = resource_data
        
        return result
    
    async def _fetch_resource(self, resource_uri: str, fastmcp_context) -> Any:
        """
        Fetch a resource, with caching support.
        
        Args:
            resource_uri: The resource URI to fetch
            fastmcp_context: FastMCP context for resource access
            
        Returns:
            The resource data extracted from the response structure
        """
        # Check cache first
        if self.enable_caching:
            cached = self._get_cached_resource(resource_uri)
            if cached is not None:
                if self.enable_debug_logging:
                    logger.debug(f"📦 Using cached resource: {resource_uri}")
                return cached
        
        try:
            # Read the resource using FastMCP context
            if self.enable_debug_logging:
                logger.debug(f"🔍 Fetching resource: {resource_uri}")
            
            # Try different methods to access the resource
            if hasattr(fastmcp_context, 'read_resource'):
                resource_result = await fastmcp_context.read_resource(resource_uri)
            elif hasattr(fastmcp_context, 'fastmcp') and hasattr(fastmcp_context.fastmcp, 'read_resource'):
                # Access via FastMCP instance
                from fastmcp.server.dependencies import get_context
                try:
                    active_ctx = get_context()
                    resource_result = await fastmcp_context.fastmcp.read_resource(resource_uri, active_ctx)
                except RuntimeError:
                    # Try without active context
                    resource_result = await fastmcp_context.fastmcp.read_resource(resource_uri, fastmcp_context)
            else:
                raise TemplateResolutionError(f"Cannot access resources via FastMCP context")
            
            # Handle case where result is a list of ReadResourceContents
            if isinstance(resource_result, list) and len(resource_result) > 0:
                # Take the first item if it's a list
                resource_result = resource_result[0]
            
            # Extract data from the resource response structure
            # Expected structure: ReadResourceContents or {"contents": [...]}
            if self.enable_debug_logging:
                logger.debug(f"📦 Raw resource type: {type(resource_result).__name__}")
                if isinstance(resource_result, list):
                    logger.debug(f"📦 List length: {len(resource_result)}")
                    if resource_result:
                        logger.debug(f"📦 First item type: {type(resource_result[0]).__name__}")
            
            resource_data = self._extract_resource_data(resource_result)
            
            if self.enable_debug_logging:
                logger.debug(f"📄 Extracted data type: {type(resource_data).__name__}")
                if isinstance(resource_data, (dict, list)):
                    logger.debug(f"📊 Extracted data preview: {str(resource_data)[:100]}...")
            
            # Cache the result
            if self.enable_caching:
                self._cache_resource(resource_uri, resource_data)
            
            if self.enable_debug_logging:
                logger.debug(f"✅ Fetched resource: {resource_uri}")
            
            return resource_data
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch resource '{resource_uri}': {e}")
            raise TemplateResolutionError(f"Failed to fetch resource '{resource_uri}': {e}")
    
    def _extract_resource_data(self, resource_result: Any, depth: int = 0) -> Any:
        """
        Recursively extract the actual data from the resource response structure.
        
        The response can be one of:
        1. ReadResourceContents dataclass with 'content' and 'mime_type' attributes
        2. Standard MCP resource response with 'contents' list
        3. Already parsed dictionary (potentially nested)
        4. Wrapper dictionaries that need recursive unwrapping
        
        Args:
            resource_result: The resource response to extract from
            depth: Current recursion depth (prevents infinite loops)
        """
        # Prevent infinite recursion
        MAX_DEPTH = 10
        if depth > MAX_DEPTH:
            logger.warning(f"⚠️ Maximum recursion depth ({MAX_DEPTH}) reached, returning as-is")
            return resource_result
        
        try:
            extracted = None
            
            # First check if it's a ReadResourceContents object from FastMCP
            if hasattr(resource_result, 'content'):
                # This is a ReadResourceContents dataclass
                content = resource_result.content
                mime_type = getattr(resource_result, 'mime_type', None)
                
                # Try to parse as JSON if it's a string and looks like JSON
                if isinstance(content, str):
                    # Check mime type or try to detect JSON
                    if mime_type == 'application/json' or content.strip().startswith('{') or content.strip().startswith('['):
                        try:
                            extracted = json.loads(content)
                        except json.JSONDecodeError:
                            # Not valid JSON, return as string
                            extracted = content
                    else:
                        extracted = content
                else:
                    # Binary content
                    extracted = content
                    
            # Handle standard MCP resource response structure
            elif hasattr(resource_result, 'contents') and resource_result.contents:
                # Standard MCP resource response
                content_item = resource_result.contents[0]
                
                if hasattr(content_item, 'text') and content_item.text:
                    # Try to parse as JSON
                    try:
                        extracted = json.loads(content_item.text)
                    except json.JSONDecodeError:
                        # Return as plain text
                        extracted = content_item.text
                elif hasattr(content_item, 'blob') and content_item.blob:
                    # Binary data
                    extracted = content_item.blob
                else:
                    # Return the content item itself
                    extracted = content_item
                    
            elif isinstance(resource_result, dict):
                # Already a dictionary
                if 'contents' in resource_result and resource_result['contents']:
                    content_item = resource_result['contents'][0]
                    if 'text' in content_item:
                        try:
                            extracted = json.loads(content_item['text'])
                        except (json.JSONDecodeError, TypeError):
                            extracted = content_item['text']
                    else:
                        extracted = content_item
                else:
                    extracted = resource_result
                    
            else:
                # Return as-is
                extracted = resource_result
            
            # Now try recursive unwrapping if we have a dictionary that looks like a wrapper
            if isinstance(extracted, dict) and self._should_unwrap_dict(extracted, depth):
                if self.enable_debug_logging:
                    logger.debug(f"🔄 Attempting recursive unwrapping at depth {depth + 1}")
                return self._extract_resource_data(extracted, depth + 1)
            
            return extracted
                
        except (IndexError, KeyError, AttributeError) as e:
            logger.warning(f"⚠️ Unexpected resource structure at depth {depth}: {e}")
            return resource_result
    
    def _should_unwrap_dict(self, data: dict, depth: int) -> bool:
        """
        Safely determine if a dictionary should be recursively unwrapped.
        
        Args:
            data: Dictionary to check for unwrapping
            depth: Current recursion depth
            
        Returns:
            True if the dictionary looks like a wrapper that should be unwrapped
        """
        # Don't unwrap if we're too deep or if it's not a single-key dictionary
        if depth >= 8 or len(data) != 1:
            return False
        
        # Get the single key
        key = next(iter(data.keys()))
        value = data[key]
        
        # Only unwrap if:
        # 1. The key looks like a wrapper key (common API response patterns)
        # 2. The value is a dict or list (contains structured data)
        # 3. The value isn't empty
        wrapper_keys = {
            'data', 'result', 'response', 'content', 'payload', 'body',
            'value', 'item', 'object', 'resource', 'entity', 'record'
        }
        
        key_lower = key.lower()
        is_wrapper_key = key_lower in wrapper_keys
        has_structured_value = isinstance(value, (dict, list)) and value
        
        if is_wrapper_key and has_structured_value:
            if self.enable_debug_logging:
                logger.debug(f"🎯 Unwrapping detected: '{key}' -> {type(value).__name__}")
            return True
        
        return False
    
    def _extract_property(self, data: Any, property_path: str) -> Any:
        """
        Extract a property from data using a dot-notation path.
        
        Args:
            data: The data object to extract from
            property_path: Dot-notation path like "email" or "user.profile.name"
            
        Returns:
            The extracted value, or None if not found
        """
        if data is None:
            return None
        
        parts = property_path.split('.')
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
    
    def _get_cached_resource(self, resource_uri: str) -> Optional[Any]:
        """Get a resource from cache if it exists and hasn't expired."""
        if resource_uri not in self._resource_cache:
            return None
        
        cache_entry = self._resource_cache[resource_uri]
        if datetime.now() < cache_entry['expires_at']:
            return cache_entry['data']
        
        # Expired, remove from cache
        del self._resource_cache[resource_uri]
        return None
    
    def _cache_resource(self, resource_uri: str, data: Any):
        """Cache a resource with expiration."""
        self._resource_cache[resource_uri] = {
            'data': data,
            'expires_at': datetime.now() + timedelta(seconds=self.cache_ttl_seconds)
        }
    
    def clear_cache(self):
        """Clear all cached resources."""
        self._resource_cache.clear()
        logger.info("🧹 Resource cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = datetime.now()
        valid_entries = sum(
            1 for entry in self._resource_cache.values()
            if entry['expires_at'] > now
        )
        
        return {
            "enabled": self.enable_caching,
            "total_entries": len(self._resource_cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._resource_cache) - valid_entries,
            "ttl_seconds": self.cache_ttl_seconds,
            "cached_uris": list(self._resource_cache.keys())
        }


def setup_streamlined_template_middleware(
    mcp,
    enable_caching: bool = True,
    cache_ttl_seconds: int = 300,
    enable_debug: bool = False
) -> StreamlinedTemplateMiddleware:
    """
    Set up the streamlined template parameter middleware.
    
    Args:
        mcp: FastMCP server instance
        enable_caching: Enable resource caching
        cache_ttl_seconds: Cache TTL in seconds
        enable_debug: Enable debug logging
        
    Returns:
        The middleware instance
    """
    middleware = StreamlinedTemplateMiddleware(
        enable_caching=enable_caching,
        cache_ttl_seconds=cache_ttl_seconds,
        enable_debug_logging=enable_debug
    )
    
    mcp.add_middleware(middleware)
    logger.info("✅ Streamlined template middleware added to FastMCP server")
    
    return middleware