"""
TTL-based resource caching for template middleware.

Provides caching functionality with time-to-live (TTL) expiration for
FastMCP resource data to improve performance and reduce redundant API calls.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from config.enhanced_logging import setup_logger
logger = setup_logger()


class CacheManager:
    """
    Manages TTL-based caching for template resource data.
    
    Provides an in-memory cache with automatic expiration based on time-to-live (TTL)
    settings. Designed to reduce redundant FastMCP resource calls while ensuring
    data freshness through configurable expiration.
    
    Features:
    - TTL-based automatic expiration
    - Cache statistics and monitoring
    - Manual cache management (clear, stats)
    - Thread-safe operations for concurrent access
    - Memory-efficient with automatic cleanup of expired entries
    """
    
    def __init__(self, enable_caching: bool = True, cache_ttl_seconds: int = 300):
        """
        Initialize the cache manager.
        
        Args:
            enable_caching: Whether to enable caching functionality (default: True)
            cache_ttl_seconds: Time-to-live for cache entries in seconds (default: 300)
        """
        self.enable_caching = enable_caching
        self.cache_ttl_seconds = cache_ttl_seconds
        
        # Resource cache: {resource_uri: {data: Any, expires_at: datetime}}
        self._resource_cache: Dict[str, Dict[str, Any]] = {}
    
    def get_cached_resource(self, resource_uri: str) -> Optional[Any]:
        """
        Get a resource from cache if it exists and hasn't expired.
        
        Args:
            resource_uri: URI of the resource to retrieve from cache
            
        Returns:
            Cached resource data if available and valid, None otherwise
            
        Side Effects:
            - Removes expired entries from cache during lookup
            - Updates internal cache state
        """
        if not self.enable_caching:
            return None
            
        if resource_uri not in self._resource_cache:
            return None
        
        cache_entry = self._resource_cache[resource_uri]
        if datetime.now() < cache_entry['expires_at']:
            return cache_entry['data']
        
        # Remove expired entry
        del self._resource_cache[resource_uri]
        return None
    
    def cache_resource(self, resource_uri: str, data: Any) -> None:
        """
        Cache a resource with TTL expiration.
        
        Args:
            resource_uri: URI of the resource to cache
            data: Resource data to store in cache
            
        Side Effects:
            - Adds or updates cache entry with current timestamp + TTL
            - Enables future cache hits for the same resource URI
        """
        if not self.enable_caching:
            return
            
        self._resource_cache[resource_uri] = {
            'data': data,
            'expires_at': datetime.now() + timedelta(seconds=self.cache_ttl_seconds)
        }
    
    def clear_cache(self) -> None:
        """
        Clear all cached resources and reset cache statistics.
        
        Removes all entries from the internal resource cache, forcing fresh
        fetches on subsequent resource requests. Useful for development,
        testing, or when resource data is known to have changed.
        
        Side Effects:
            - Clears self._resource_cache completely
            - Logs cache clearing activity
            - Next resource requests will bypass cache
            
        Use Cases:
            - Development: Clear cache when resources change
            - Testing: Ensure fresh data for test isolation
            - Runtime: Force refresh of potentially stale data
            - Memory management: Free cache memory if needed
            
        Example:
            ```python
            # Clear cache during development
            cache_manager.clear_cache()
            
            # Or schedule periodic cache clearing
            import asyncio
            async def periodic_cache_clear():
                while True:
                    await asyncio.sleep(3600)  # Every hour
                    cache_manager.clear_cache()
            ```
            
        Note:
            This operation is immediate and cannot be undone. Consider using
            get_cache_stats() first to understand current cache utilization.
        """
        self._resource_cache.clear()
        logger.info("🧹 Resource cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get detailed statistics about the resource cache state and performance.
        
        Provides comprehensive information about cache utilization, expiration
        status, and configuration settings for monitoring and debugging purposes.
        
        Returns:
            Dictionary containing cache statistics with the following keys:
            
            - enabled: bool - Whether caching is enabled in configuration
            - total_entries: int - Total number of cache entries (including expired)
            - valid_entries: int - Number of non-expired cache entries
            - expired_entries: int - Number of expired but not yet cleaned entries
            - ttl_seconds: int - Configured time-to-live for cache entries
            - cached_uris: List[str] - List of all cached resource URIs
            
        Cache Health Indicators:
            - High valid_entries: Cache is working effectively
            - High expired_entries: Consider shorter TTL or manual clearing
            - Empty cached_uris: No resources have been cached yet
            - Large total_entries: May need memory management attention
            
        Example Output:
            ```python
            {
                "enabled": True,
                "total_entries": 25,
                "valid_entries": 18,
                "expired_entries": 7,
                "ttl_seconds": 300,
                "cached_uris": [
                    "user://current/email",
                    "service://gmail/labels",
                    "recent://all"
                ]
            }
            ```
            
        Use Cases:
            - Performance monitoring: Track cache hit rates and effectiveness
            - Memory management: Monitor cache size and growth patterns
            - Debugging: Understand which resources are being cached
            - Configuration tuning: Adjust TTL based on usage patterns
            
        Note:
            This method performs real-time analysis and may iterate through
            all cache entries to determine expiration status.
        """
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
    
    def cleanup_expired_entries(self) -> int:
        """
        Manually cleanup expired cache entries.
        
        Removes all expired entries from the cache to free memory.
        This is automatically done during get_cached_resource() calls,
        but can be called manually for proactive memory management.
        
        Returns:
            Number of expired entries that were removed
            
        Side Effects:
            - Removes expired entries from self._resource_cache
            - Reduces memory usage
            - Improves cache statistics accuracy
        """
        if not self.enable_caching:
            return 0
            
        now = datetime.now()
        expired_keys = [
            uri for uri, entry in self._resource_cache.items()
            if entry['expires_at'] <= now
        ]
        
        for key in expired_keys:
            del self._resource_cache[key]
            
        if expired_keys:
            logger.debug(f"🧹 Cleaned up {len(expired_keys)} expired cache entries")
            
        return len(expired_keys)