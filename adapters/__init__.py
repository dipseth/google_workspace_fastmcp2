"""
Adapter system for Google Workspace MCP
Provides module wrapping and type definitions for MCP integration
"""

from .adapter_types import (
    ModuleComponentInfo,
    ModuleComponentsResponse,
    WrappedModuleInfo,
    WrappedModulesResponse,
)
from .module_wrapper import ModuleWrapper
from .module_wrapper_mcp import ModuleWrapperMiddleware, setup_module_wrapper_middleware

__all__ = [
    "ModuleWrapper",
    "setup_module_wrapper_middleware",
    "ModuleWrapperMiddleware",
    "ModuleComponentInfo",
    "ModuleComponentsResponse",
    "WrappedModuleInfo",
    "WrappedModulesResponse",
]
