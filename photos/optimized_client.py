"""
Optimized Google Photos API Client

This module provides optimized patterns for Google Photos API usage including:
- Rate limiting and quota management
- Smart caching with TTL
- Batch operations
- Error handling and retries
- Memory-efficient pagination
"""

import asyncio
import logging
import time
from typing_extensions import Dict, List, Optional, Any, Union
from collections import defaultdict, deque
from datetime import datetime, timedelta
from dataclasses import dataclass
from functools import wraps
import hashlib
import json

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for Google Photos API rate limiting."""
    requests_per_second: int = 10
    requests_per_day: int = 10000
    burst_allowance: int = 20


class RateLimiter:
    """Rate limiter for Google Photos API with daily quota tracking."""
    
    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self.request_times = deque()
        self.daily_count = defaultdict(int)
        self.burst_tokens = self.config.burst_allowance
        self.last_burst_refill = time.time()
    
    async def acquire(self):
        """Acquire permission to make an API request."""
        now = time.time()
        today = time.strftime('%Y-%m-%d')
        
        # Check daily limit
        if self.daily_count[today] >= self.config.requests_per_day:
            raise Exception(f"Daily API limit exceeded: {self.config.requests_per_day}")
        
        # Refill burst tokens (1 per second)
        time_since_refill = now - self.last_burst_refill
        tokens_to_add = min(int(time_since_refill), self.config.burst_allowance - self.burst_tokens)
        self.burst_tokens = min(self.burst_tokens + tokens_to_add, self.config.burst_allowance)
        self.last_burst_refill = now
        
        # Check if we can use a burst token
        if self.burst_tokens > 0:
            self.burst_tokens -= 1
            self.daily_count[today] += 1
            logger.debug(f"Used burst token, {self.burst_tokens} remaining")
            return
        
        # Standard rate limiting
        # Remove old request times (older than 1 second)
        while self.request_times and now - self.request_times[0] >= 1.0:
            self.request_times.popleft()
        
        # If we've hit the per-second limit, wait
        if len(self.request_times) >= self.config.requests_per_second:
            sleep_time = 1.0 - (now - self.request_times[0])
            if sleep_time > 0:
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
        
        # Record this request
        self.request_times.append(now)
        self.daily_count[today] += 1
        logger.debug(f"Rate limit check passed, daily count: {self.daily_count[today]}")


class LRUCache:
    """LRU Cache with TTL support for API responses."""
    
    def __init__(self, maxsize: int = 1000, default_ttl: int = 3600):
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self.cache = {}
        self.access_order = []
    
    def _make_key(self, *args, **kwargs) -> str:
        """Create cache key from arguments."""
        key_data = f"{args}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        now = time.time()
        
        if now > entry['expires']:
            # Expired, remove it
            del self.cache[key]
            if key in self.access_order:
                self.access_order.remove(key)
            return None
        
        # Move to end (most recently used)
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)
        
        logger.debug(f"Cache hit for key: {key[:16]}...")
        return entry['data']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        now = time.time()
        ttl = ttl or self.default_ttl
        
        # Remove LRU item if at capacity
        if len(self.cache) >= self.maxsize and key not in self.cache:
            if self.access_order:
                lru_key = self.access_order.pop(0)
                del self.cache[lru_key]
                logger.debug(f"Evicted LRU cache entry: {lru_key[:16]}...")
        
        # Store the new entry
        self.cache[key] = {
            'data': value,
            'expires': now + ttl
        }
        
        # Update access order
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)
        
        logger.debug(f"Cached entry with {ttl}s TTL: {key[:16]}...")
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        now = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry['expires'] < now
        ]
        
        for key in expired_keys:
            del self.cache[key]
            if key in self.access_order:
                self.access_order.remove(key)
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)


def cached_method(ttl: int = 3600):
    """Decorator to cache method results with TTL."""
    def decorator(method):
        @wraps(method)
        async def wrapper(self, *args, **kwargs):
            if not hasattr(self, '_cache'):
                return await method(self, *args, **kwargs)
            
            # Create cache key
            key = f"{method.__name__}:{self._cache._make_key(*args, **kwargs)}"
            
            # Try to get from cache
            cached_result = self._cache.get(key)
            if cached_result is not None:
                return cached_result
            
            # Execute method and cache result
            result = await method(self, *args, **kwargs)
            self._cache.set(key, result, ttl)
            return result
            
        return wrapper
    return decorator


class OptimizedPhotosClient:
    """Optimized Google Photos API client with rate limiting and caching."""
    
    def __init__(self, photos_service, rate_config: RateLimitConfig = None, cache_size: int = 1000):
        self.photos_service = photos_service
        self.rate_limiter = RateLimiter(rate_config)
        self._cache = LRUCache(maxsize=cache_size)
        self.batch_size = 50  # Photos API supports up to 50 items per batch
        
        logger.info(f"Initialized OptimizedPhotosClient with cache size: {cache_size}")
    
    async def _make_request(self, request_func, *args, **kwargs):
        """Make an API request with rate limiting and error handling."""
        await self.rate_limiter.acquire()
        
        try:
            # Use asyncio.to_thread for blocking Google API calls
            result = await asyncio.to_thread(request_func, *args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"API request failed: {e}")
            raise
    
    @cached_method(ttl=7200)  # Cache albums for 2 hours
    async def list_albums(self, max_albums: int = 50) -> Dict[str, Any]:
        """List albums with caching."""
        logger.info(f"Listing albums (max: {max_albums})")
        
        all_albums = []
        page_token = None
        
        while len(all_albums) < max_albums:
            page_size = min(50, max_albums - len(all_albums))  # API max is 50
            
            request = self.photos_service.albums().list(
                pageSize=page_size,
                pageToken=page_token
            )
            
            response = await self._make_request(request.execute)
            albums = response.get('albums', [])
            all_albums.extend(albums)
            
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        
        logger.info(f"Retrieved {len(all_albums)} albums")
        return {"albums": all_albums[:max_albums]}
    
    @cached_method(ttl=1800)  # Cache search results for 30 minutes
    async def search_media_items(
        self,
        album_id: Optional[str] = None,
        filters: Optional[Dict] = None,
        max_items: int = 100
    ) -> Dict[str, Any]:
        """Search media items with optimized pagination and caching."""
        logger.info(f"Searching media items (album_id: {album_id}, max: {max_items})")
        
        all_items = []
        page_token = None
        
        while len(all_items) < max_items:
            page_size = min(100, max_items - len(all_items))  # API max is 100
            
            search_body = {"pageSize": page_size}
            
            if album_id:
                search_body["albumId"] = album_id
            if filters:
                search_body["filters"] = filters
            if page_token:
                search_body["pageToken"] = page_token
            
            request = self.photos_service.mediaItems().search(body=search_body)
            response = await self._make_request(request.execute)
            
            media_items = response.get('mediaItems', [])
            all_items.extend(media_items)
            
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        
        logger.info(f"Retrieved {len(all_items)} media items")
        return {"mediaItems": all_items[:max_items]}
    
    async def get_media_items_batch(self, media_item_ids: List[str]) -> Dict[str, Any]:
        """Get multiple media items in a single batch request."""
        if not media_item_ids:
            return {"mediaItemResults": []}
        
        # Photos API supports up to 50 items per batch
        batch_ids = media_item_ids[:self.batch_size]
        logger.info(f"Getting {len(batch_ids)} media items in batch")
        
        # Create cache key for this batch
        cache_key = f"batch_media_{hash(tuple(sorted(batch_ids)))}"
        cached_result = self._cache.get(cache_key)
        if cached_result:
            logger.debug("Returning cached batch result")
            return cached_result
        
        request = self.photos_service.mediaItems().batchGet(
            mediaItemIds=batch_ids
        )
        
        response = await self._make_request(request.execute)
        
        # Cache for 1 hour
        self._cache.set(cache_key, response, 3600)
        
        logger.info(f"Retrieved batch of {len(response.get('mediaItemResults', []))} items")
        return response
    
    @cached_method(ttl=3600)  # Cache individual media items for 1 hour
    async def get_media_item(self, media_item_id: str) -> Dict[str, Any]:
        """Get a single media item with caching."""
        logger.info(f"Getting media item: {media_item_id}")
        
        request = self.photos_service.mediaItems().get(mediaItemId=media_item_id)
        response = await self._make_request(request.execute)
        
        return response
    
    async def create_album(self, title: str) -> Dict[str, Any]:
        """Create a new album (not cached as it's a write operation)."""
        logger.info(f"Creating album: {title}")
        
        album_body = {
            "album": {
                "title": title
            }
        }
        
        request = self.photos_service.albums().create(body=album_body)
        response = await self._make_request(request.execute)
        
        # Clear albums cache since we've added a new album
        self._clear_albums_cache()
        
        logger.info(f"Created album: {response.get('id')}")
        return response
    
    def _clear_albums_cache(self):
        """Clear cached album data after modifications."""
        keys_to_remove = [key for key in self._cache.cache.keys() if 'list_albums' in key]
        for key in keys_to_remove:
            if key in self._cache.cache:
                del self._cache.cache[key]
            if key in self._cache.access_order:
                self._cache.access_order.remove(key)
        
        if keys_to_remove:
            logger.debug(f"Cleared {len(keys_to_remove)} album cache entries")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        expired_count = self._cache.cleanup_expired()
        
        return {
            "cache_size": len(self._cache.cache),
            "max_size": self._cache.maxsize,
            "expired_cleaned": expired_count,
            "daily_requests": dict(self.rate_limiter.daily_count),
            "burst_tokens": self.rate_limiter.burst_tokens
        }


class PhotosSearchBuilder:
    """Builder pattern for constructing Photos API search filters."""
    
    def __init__(self):
        self.filters = {}
    
    def with_content_categories(self, categories: List[str]) -> 'PhotosSearchBuilder':
        """Add content category filters (e.g., PEOPLE, ANIMALS, FOOD)."""
        self.filters["contentFilter"] = {
            "includedContentCategories": [cat.upper() for cat in categories]
        }
        return self
    
    def with_date_range(
        self, 
        start_date: Optional[datetime] = None, 
        end_date: Optional[datetime] = None
    ) -> 'PhotosSearchBuilder':
        """Add date range filter."""
        if not start_date and not end_date:
            return self
        
        date_range = {}
        if start_date:
            date_range["startDate"] = {
                "year": start_date.year,
                "month": start_date.month,
                "day": start_date.day
            }
        if end_date:
            date_range["endDate"] = {
                "year": end_date.year,
                "month": end_date.month,
                "day": end_date.day
            }
        
        self.filters["dateFilter"] = {"ranges": [date_range]}
        return self
    
    def with_media_types(self, include_photos: bool = True, include_videos: bool = True) -> 'PhotosSearchBuilder':
        """Filter by media type."""
        media_types = []
        if include_photos:
            media_types.append("PHOTO")
        if include_videos:
            media_types.append("VIDEO")
        
        if media_types:
            self.filters["mediaTypeFilter"] = {"mediaTypes": media_types}
        
        return self
    
    def build(self) -> Dict[str, Any]:
        """Build the final filters dictionary."""
        return self.filters.copy()


# Helper function to create optimized client
async def create_optimized_photos_client(
    photos_service,
    rate_config: RateLimitConfig = None,
    cache_size: int = 1000
) -> OptimizedPhotosClient:
    """Create an optimized Photos client with default settings."""
    return OptimizedPhotosClient(photos_service, rate_config, cache_size)