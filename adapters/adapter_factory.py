"""
Adapter Factory for Google Workspace MCP
Creates adapter instances from API classes or modules
"""

import logging
import importlib
from typing import Dict, Any, Optional, Type
from .base_api import BaseAPI, APIMetadata
from .adapters import APIAdapter, create_api_adapter
from .discovery_manager import DiscoveryManager

logger = logging.getLogger(__name__)


class AdapterFactory:
    """
    Factory for creating adapter instances from API classes or modules.
    Supports configuration-driven instantiation and Google Workspace service-specific adaptations.
    """
    
    def __init__(self, discovery_manager: DiscoveryManager):
        """
        Initialize the adapter factory.
        
        Args:
            discovery_manager: Discovery manager for finding APIs and configurations
        """
        self.discovery_manager = discovery_manager
        self._adapters_cache = {}
    
    def create_adapter(self, api_class_or_instance, metadata: Optional[Dict[str, Any]] = None) -> APIAdapter:
        """
        Create an adapter for an API class or instance.
        
        Args:
            api_class_or_instance: API class or instance to adapt
            metadata: Optional metadata to override defaults
            
        Returns:
            APIAdapter instance wrapping the API
        """
        return create_api_adapter(api_class_or_instance, metadata)
    
    def create_google_workspace_adapter(self, service_name: str, service_instance, 
                                      metadata: Optional[Dict[str, Any]] = None) -> APIAdapter:
        """
        Create an adapter specifically for Google Workspace services.
        
        Args:
            service_name: Name of the Google Workspace service (e.g., 'chat', 'gmail')
            service_instance: Instance of the service
            metadata: Optional metadata to override defaults
            
        Returns:
            APIAdapter instance for the Google Workspace service
        """
        # Default metadata for Google Workspace services
        default_metadata = {
            "name": f"google_{service_name}",
            "description": f"Google Workspace {service_name.title()} API",
            "category": "google_workspace",
            "keywords": ["google", "workspace", service_name],
            "requires_auth": True,
            "version": "1.0.0"
        }
        
        # Merge with provided metadata
        if metadata:
            default_metadata.update(metadata)
        
        return self.create_adapter(service_instance, default_metadata)
    
    def get_cached_adapter(self, adapter_name: str) -> Optional[APIAdapter]:
        """
        Get a cached adapter by name.
        
        Args:
            adapter_name: Name of the adapter
            
        Returns:
            Cached adapter or None if not found
        """
        return self._adapters_cache.get(adapter_name)
    
    def cache_adapter(self, adapter_name: str, adapter: APIAdapter):
        """
        Cache an adapter for later retrieval.
        
        Args:
            adapter_name: Name to cache the adapter under
            adapter: Adapter instance to cache
        """
        self._adapters_cache[adapter_name] = adapter
        logger.info(f"Cached adapter: {adapter_name}")
    
    def clear_cache(self):
        """Clear the adapter cache."""
        self._adapters_cache.clear()
        logger.info("Adapter cache cleared")
    
    def list_cached_adapters(self) -> Dict[str, APIAdapter]:
        """
        Get all cached adapters.
        
        Returns:
            Dictionary of cached adapters
        """
        return self._adapters_cache.copy()