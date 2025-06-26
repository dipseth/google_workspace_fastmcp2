"""
Adapter Registry for Google Workspace MCP
Centralized registry for managing adapter instances
"""

import logging
from typing import Dict, Any, Optional, List
from .base_api import BaseAPI, APIMetadata
from .adapters import APIAdapter
from .adapter_factory import AdapterFactory

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """
    Centralized registry for managing adapter instances.
    Provides metadata tracking, usage statistics, and category/keyword-based filtering.
    """
    
    def __init__(self, adapter_factory: AdapterFactory):
        """
        Initialize the adapter registry.
        
        Args:
            adapter_factory: Factory for creating adapters
        """
        self.adapter_factory = adapter_factory
        self._adapters = {}
        self._metadata_cache = {}
        self._usage_stats = {}
    
    def register(self, name: str, api_class_or_instance, 
                metadata: Optional[Dict[str, Any]] = None) -> APIAdapter:
        """
        Register an adapter with the registry.
        
        Args:
            name: Name to register the adapter under
            api_class_or_instance: API class or instance to adapt
            metadata: Optional metadata to override defaults
            
        Returns:
            The registered adapter
        """
        adapter = self.adapter_factory.create_adapter(api_class_or_instance, metadata)
        self._adapters[name] = adapter
        self._metadata_cache[name] = adapter.get_metadata()
        self._usage_stats[name] = 0
        
        logger.info(f"Registered adapter: {name}")
        return adapter
    
    def register_google_workspace_adapter(self, name: str, service_name: str, 
                                        service_instance, metadata: Optional[Dict[str, Any]] = None) -> APIAdapter:
        """
        Register a Google Workspace service adapter.
        
        Args:
            name: Name to register the adapter under
            service_name: Name of the Google Workspace service
            service_instance: Instance of the service
            metadata: Optional metadata to override defaults
            
        Returns:
            The registered adapter
        """
        adapter = self.adapter_factory.create_google_workspace_adapter(
            service_name, service_instance, metadata
        )
        self._adapters[name] = adapter
        self._metadata_cache[name] = adapter.get_metadata()
        self._usage_stats[name] = 0
        
        logger.info(f"Registered Google Workspace adapter: {name}")
        return adapter
    
    def get_adapter(self, name: str) -> Optional[APIAdapter]:
        """
        Get an adapter by name.
        
        Args:
            name: Name of the adapter
            
        Returns:
            The adapter or None if not found
        """
        adapter = self._adapters.get(name)
        if adapter:
            self._usage_stats[name] += 1
        return adapter
    
    def list_adapters(self) -> Dict[str, APIAdapter]:
        """
        Get all registered adapters.
        
        Returns:
            Dictionary of all adapters
        """
        return self._adapters.copy()
    
    def list_adapter_names(self) -> List[str]:
        """
        Get names of all registered adapters.
        
        Returns:
            List of adapter names
        """
        return list(self._adapters.keys())
    
    def get_metadata(self, name: str) -> Optional[APIMetadata]:
        """
        Get metadata for an adapter.
        
        Args:
            name: Name of the adapter
            
        Returns:
            Adapter metadata or None if not found
        """
        return self._metadata_cache.get(name)
    
    def list_metadata(self) -> Dict[str, APIMetadata]:
        """
        Get metadata for all adapters.
        
        Returns:
            Dictionary of adapter metadata
        """
        return self._metadata_cache.copy()
    
    def get_usage_stats(self, name: str) -> int:
        """
        Get usage statistics for an adapter.
        
        Args:
            name: Name of the adapter
            
        Returns:
            Usage count
        """
        return self._usage_stats.get(name, 0)
    
    def list_usage_stats(self) -> Dict[str, int]:
        """
        Get usage statistics for all adapters.
        
        Returns:
            Dictionary of usage statistics
        """
        return self._usage_stats.copy()
    
    def filter_by_category(self, category: str) -> Dict[str, APIAdapter]:
        """
        Filter adapters by category.
        
        Args:
            category: Category to filter by
            
        Returns:
            Dictionary of matching adapters
        """
        filtered = {}
        for name, metadata in self._metadata_cache.items():
            if metadata.category == category:
                filtered[name] = self._adapters[name]
        return filtered
    
    def filter_by_keywords(self, keywords: List[str]) -> Dict[str, APIAdapter]:
        """
        Filter adapters by keywords.
        
        Args:
            keywords: Keywords to filter by
            
        Returns:
            Dictionary of matching adapters
        """
        filtered = {}
        for name, metadata in self._metadata_cache.items():
            if any(keyword in metadata.keywords for keyword in keywords):
                filtered[name] = self._adapters[name]
        return filtered
    
    def unregister(self, name: str) -> bool:
        """
        Unregister an adapter.
        
        Args:
            name: Name of the adapter to unregister
            
        Returns:
            True if adapter was unregistered, False if not found
        """
        if name in self._adapters:
            del self._adapters[name]
            del self._metadata_cache[name]
            del self._usage_stats[name]
            logger.info(f"Unregistered adapter: {name}")
            return True
        return False
    
    def clear(self):
        """Clear all registered adapters."""
        self._adapters.clear()
        self._metadata_cache.clear()
        self._usage_stats.clear()
        logger.info("Cleared all registered adapters")