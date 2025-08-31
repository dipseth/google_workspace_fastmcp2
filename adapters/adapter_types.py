"""
Type definitions for adapter tool responses.

These TypedDict classes define the structure of data returned by adapter tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional, Any


class ModuleComponentInfo(TypedDict):
    """Structure for a single module component entry."""
    name: str
    path: str
    type: str  # 'function', 'class', 'method', etc.
    score: Optional[float]  # Relevance score from semantic search
    docstring: str
    source: Optional[str]  # Optional source code


class ModuleComponentsResponse(TypedDict):
    """Response structure for list_module_components tool."""
    components: List[ModuleComponentInfo]
    count: int
    module: str
    error: Optional[str]  # Optional error message for error responses


class WrappedModuleInfo(TypedDict):
    """Structure for a single wrapped module entry."""
    name: str
    indexed: bool  # Whether the module has been indexed for semantic search
    component_count: Optional[int]  # Number of components in the module


class WrappedModulesResponse(TypedDict):
    """Response structure for list_wrapped_modules tool."""
    modules: List[WrappedModuleInfo]
    count: int
    error: Optional[str]  # Optional error message for error responses