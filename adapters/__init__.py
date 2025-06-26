"""
Adapter system for Google Workspace MCP
Provides dynamic module loading and API adaptation capabilities
"""

from .adapter_factory import AdapterFactory
from .adapter_registry import AdapterRegistry
from .adapters import APIAdapter, create_api_adapter
from .base_api import BaseAPI, APIMetadata
from .discovery_manager import DiscoveryManager

__all__ = [
    'AdapterFactory',
    'AdapterRegistry', 
    'APIAdapter',
    'create_api_adapter',
    'BaseAPI',
    'APIMetadata',
    'DiscoveryManager'
]