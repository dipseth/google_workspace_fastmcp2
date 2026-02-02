"""
FastMCP Compatibility Utilities

This module provides utilities to handle differences between FastMCP versions
and eliminate cascading hasattr/getattr patterns throughout the codebase.

Key goals:
1. Centralize version detection logic
2. Provide type-safe abstractions for common patterns
3. Replace cascading if/elif blocks with confident object handling
"""

from typing import Any, Dict, Optional, Protocol, Union
import logging

logger = logging.getLogger(__name__)


class ToolCallable(Protocol):
    """Protocol defining what a callable tool should have."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Tool is callable."""
        ...


class FastMCPToolRegistry:
    """
    Abstraction for accessing tool registries across FastMCP versions.
    
    Handles differences between:
    - FastMCP 2.x: tools in _tool_manager._tools
    - FastMCP 3.0.0b1+: tools in _local_provider._components
    """

    @staticmethod
    def get_tools_dict(mcp_server: Any) -> Dict[str, Any]:
        """
        Get the tools dictionary from a FastMCP server instance.
        
        Args:
            mcp_server: FastMCP server instance
            
        Returns:
            Dictionary mapping tool names to tool instances
            
        Raises:
            RuntimeError: If unable to access tool registry
        """
        # FastMCP 2.x path
        if hasattr(mcp_server, "_tool_manager") and hasattr(
            mcp_server._tool_manager, "_tools"
        ):
            return mcp_server._tool_manager._tools
        
        # FastMCP 3.0.0b1+ path - tools in _local_provider._components
        if hasattr(mcp_server, "_local_provider") and hasattr(
            mcp_server._local_provider, "_components"
        ):
            try:
                from fastmcp.tools.tool import Tool
                components = mcp_server._local_provider._components
                return {v.name: v for v in components.values() if isinstance(v, Tool)}
            except ImportError:
                pass
        
        raise RuntimeError(
            "Cannot access tool registry from FastMCP server. "
            "Unsupported FastMCP version or server structure."
        )

    @staticmethod
    def extract_callable(tool_instance: Any) -> ToolCallable:
        """
        Extract the actual callable function from a tool instance.
        
        Different middleware and FastMCP versions wrap tools differently.
        This method handles all known patterns.
        
        Args:
            tool_instance: Tool instance from the registry
            
        Returns:
            Callable function
            
        Raises:
            RuntimeError: If unable to extract a callable
        """
        # Priority order for finding the callable
        for attr_name in ["fn", "func", "__call__"]:
            if hasattr(tool_instance, attr_name):
                callable_attr = getattr(tool_instance, attr_name)
                if callable(callable_attr):
                    return callable_attr
        
        # If we get here, couldn't find a callable
        raise RuntimeError(
            f"Tool instance '{type(tool_instance).__name__}' is not callable. "
            f"Available attributes: {dir(tool_instance)}"
        )


class ResourceContentExtractor:
    """
    Extract content from various resource response types.
    
    Handles:
    - ReadResourceContents dataclass (MCP)
    - Standard MCP resource response structure
    - Dict-based responses
    - Pydantic models
    """

    @staticmethod
    def extract(resource_result: Any) -> Any:
        """
        Extract content from a resource result, handling multiple response types.
        
        Args:
            resource_result: Resource result from MCP or other source
            
        Returns:
            Extracted content (string, dict, list, or original object)
        """
        import json
        
        # Handle Pydantic models
        try:
            from pydantic import BaseModel
            if isinstance(resource_result, BaseModel):
                return resource_result.model_dump()
        except ImportError:
            pass
        
        # Handle ReadResourceContents dataclass
        if hasattr(resource_result, "content"):
            content = resource_result.content
            mime_type = getattr(resource_result, "mime_type", None)
            
            if isinstance(content, str):
                # Try to parse JSON content
                if (
                    mime_type == "application/json"
                    or content.strip().startswith("{")
                    or content.strip().startswith("[")
                ):
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return content
                return content
            return content
        
        # Handle standard MCP resource response structure
        if hasattr(resource_result, "contents") and resource_result.contents:
            content_item = resource_result.contents[0]
            
            if hasattr(content_item, "text") and content_item.text:
                try:
                    return json.loads(content_item.text)
                except json.JSONDecodeError:
                    return content_item.text
            
            if hasattr(content_item, "blob") and content_item.blob:
                return content_item.blob
            
            return content_item
        
        # Handle dict-based responses
        if isinstance(resource_result, dict):
            if "contents" in resource_result and resource_result["contents"]:
                content_item = resource_result["contents"][0]
                if "text" in content_item:
                    try:
                        return json.loads(content_item["text"])
                    except (json.JSONDecodeError, TypeError):
                        return content_item["text"]
                if "blob" in content_item:
                    return content_item["blob"]
                return content_item
            return resource_result
        
        # Return as-is if we can't extract
        return resource_result


class ResponseSerializer:
    """
    Serialize responses for storage or transmission.
    
    Handles:
    - FastMCP ToolResult objects
    - Objects with to_dict method
    - Objects with __dict__
    - Pydantic models
    """

    @staticmethod
    def serialize(response: Any) -> Any:
        """
        Serialize a response object to a JSON-compatible format.
        
        Args:
            response: Response object to serialize
            
        Returns:
            Serialized response (dict, list, or primitive)
        """
        # Handle FastMCP ToolResult objects with content attribute
        if hasattr(response, "content"):
            return response.content
        
        # Handle Pydantic models
        if hasattr(response, "model_dump"):
            try:
                return response.model_dump(mode="json")
            except Exception:
                # Fall back to __dict__ if model_dump fails
                if hasattr(response, "__dict__"):
                    return response.__dict__
        
        # Handle objects with to_dict method
        if hasattr(response, "to_dict"):
            return response.to_dict()
        
        # Handle generic objects with attributes
        if hasattr(response, "__dict__"):
            return response.__dict__
        
        # Return as-is for primitives and already-structured data
        return response


class ToolsListAccessor:
    """
    Access tools list from FastMCP server with fallback patterns.
    
    This handles the multiple ways tools can be exposed in different FastMCP versions.
    """

    @staticmethod
    def get_tools_dict(fastmcp_server: Any) -> Dict[str, Any]:
        """
        Get tools dictionary from FastMCP server with comprehensive fallback.
        
        Args:
            fastmcp_server: FastMCP server instance
            
        Returns:
            Dictionary mapping tool names to tool instances
        """
        # Try the public tools attribute first
        if hasattr(fastmcp_server, "tools"):
            tools_list = fastmcp_server.tools
            
            # Convert list to dict if needed
            if isinstance(tools_list, list):
                return {
                    tool.name: tool 
                    for tool in tools_list 
                    if hasattr(tool, "name")
                }
            
            # Already a dict-like object
            if hasattr(tools_list, "items"):
                return dict(tools_list.items())
        
        # Fallback to _tool_manager (FastMCP 2.x)
        if hasattr(fastmcp_server, "_tool_manager"):
            if hasattr(fastmcp_server._tool_manager, "_tools"):
                return fastmcp_server._tool_manager._tools
            if hasattr(fastmcp_server._tool_manager, "tools"):
                return fastmcp_server._tool_manager.tools
        
        # FastMCP 3.0.0b1+ path - tools in _local_provider._components
        if hasattr(fastmcp_server, "_local_provider"):
            if hasattr(fastmcp_server._local_provider, "_components"):
                try:
                    from fastmcp.tools.tool import Tool
                    components = fastmcp_server._local_provider._components
                    return {
                        v.name: v 
                        for v in components.values() 
                        if isinstance(v, Tool)
                    }
                except ImportError:
                    pass
        
        # Last resort: try common attribute names
        for attr_name in ["_tools", "tool_registry", "registry"]:
            if hasattr(fastmcp_server, attr_name):
                attr_value = getattr(fastmcp_server, attr_name)
                if isinstance(attr_value, dict):
                    return attr_value
        
        raise RuntimeError(
            "Cannot access tools from FastMCP server. "
            "No recognized tool registry attribute found."
        )


class ContextExtractor:
    """Extract values from context objects safely."""

    @staticmethod
    def get_tool_name(context: Any, default: str = "unknown_tool") -> str:
        """
        Extract tool name from context.
        
        Args:
            context: Context object (typically from middleware)
            default: Default value if tool name cannot be extracted
            
        Returns:
            Tool name or default value
        """
        if hasattr(context, "message") and hasattr(context.message, "name"):
            return context.message.name
        return default

    @staticmethod
    def get_arguments(context: Any, default: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Extract arguments from context.
        
        Args:
            context: Context object (typically from middleware)
            default: Default value if arguments cannot be extracted
            
        Returns:
            Arguments dictionary or default value
        """
        if default is None:
            default = {}
        
        if hasattr(context, "message") and hasattr(context.message, "arguments"):
            return context.message.arguments
        return default
