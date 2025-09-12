"""
Adapter system for Google Workspace MCP
Provides module wrapping and type definitions for MCP integration
"""

from .module_wrapper import ModuleWrapper
from .module_wrapper_mcp import setup_module_wrapper_middleware, ModuleWrapperMiddleware
from .adapter_types import (
    ModuleComponentInfo,
    ModuleComponentsResponse,
    WrappedModuleInfo,
    WrappedModulesResponse
)

__all__ = [
    'ModuleWrapper',
    'setup_module_wrapper_middleware',
    'ModuleWrapperMiddleware',
    'ModuleComponentInfo',
    'ModuleComponentsResponse',
    'WrappedModuleInfo',
    'WrappedModulesResponse'
]