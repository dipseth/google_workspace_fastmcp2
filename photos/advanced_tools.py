"""
Advanced Google Photos MCP Tools

This module provides advanced MCP tools using the optimized Photos API client.
Includes batch operations, smart caching, and enhanced search capabilities.
"""

import logging
import asyncio
from typing_extensions import List, Optional, Any, Dict, Union
from datetime import datetime, date

from fastmcp import FastMCP
from googleapiclient.errors import HttpError

from auth.service_helpers import request_service, get_injected_service, get_service
from .optimized_client import (
    OptimizedPhotosClient, PhotosSearchBuilder, RateLimitConfig,
    create_optimized_photos_client
)

# Configure module logger
logger = logging.getLogger(__name__)

# Global client cache to reuse optimized clients across tools
_client_cache: Dict[str, OptimizedPhotosClient] = {}


async def _get_optimized_photos_client(user_google_email: str) -> OptimizedPhotosClient:
    """Get or create an optimized photos client for the user."""
    if user_google_email in _client_cache:
        return _client_cache[user_google_email]
    
    # Get the base photos service
    try:
        service_key = request_service("photos")
        photos_service = get_injected_service(service_key)
        if not photos_service:
            raise RuntimeError("Service not available")
    except Exception:
        # Fallback to direct service creation
        photos_service = await get_service("photos", user_google_email)
    
    # Create optimized client
    rate_config = RateLimitConfig(
        requests_per_second=8,  # Conservative rate to avoid issues
        requests_per_day=8000,  # Leave buffer for other operations
        burst_allowance=15
    )
    
    client = await create_optimized_photos_client(
        photos_service=photos_service,
        rate_config=rate_config,
        cache_size=1500  # Larger cache for power users
    )
    
    _client_cache[user_google_email] = client
    logger.info(f"Created optimized Photos client for {user_google_email}")
    return client


def setup_advanced_photos_tools(mcp: FastMCP) -> None:
    """
    Setup advanced Google Photos tools with optimization features.
    
    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up advanced Google Photos tools")
    
    @mcp.tool(
        name="photos_smart_search",
        description="Advanced photo search with smart filtering and optimization",
        tags={"photos", "search", "advanced", "optimized", "google"},
        annotations={
            "title": "Smart Photo Search",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def photos_smart_search(
        user_google_email: str,
        content_categories: Optional[List[str]] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        include_photos: bool = True,
        include_videos: bool = False,
        max_results: int = 50
    ) -> str:
        """
        Advanced photo search with smart filtering and caching.

        Args:
            user_google_email (str): User's Google email address. Required.
            content_categories (List[str], optional): Content categories (PEOPLE, ANIMALS, FOOD, etc.).
            date_start (str, optional): Start date in YYYY-MM-DD format.
            date_end (str, optional): End date in YYYY-MM-DD format.
            include_photos (bool): Include photos in results. Defaults to True.
            include_videos (bool): Include videos in results. Defaults to False.
            max_results (int): Maximum results to return. Defaults to 50.

        Returns:
            str: Formatted search results with performance metrics.
        """
        start_time = datetime.now()
        logger.info(f"[photos_smart_search] User: {user_google_email}, Categories: {content_categories}")

        try:
            client = await _get_optimized_photos_client(user_google_email)
            
            # Build search filters using the builder pattern
            search_builder = PhotosSearchBuilder()
            
            if content_categories:
                search_builder.with_content_categories(content_categories)
            
            if date_start or date_end:
                start_dt = datetime.strptime(date_start, "%Y-%m-%d") if date_start else None
                end_dt = datetime.strptime(date_end, "%Y-%m-%d") if date_end else None
                search_builder.with_date_range(start_dt, end_dt)
            
            search_builder.with_media_types(include_photos, include_videos)
            
            filters = search_builder.build()
            
            # Execute search
            result = await client.search_media_items(
                filters=filters,
                max_items=max_results
            )
            
            media_items = result.get("mediaItems", [])
            
            # Get cache stats for performance info
            cache_stats = await client.get_cache_stats()
            elapsed_time = (datetime.now() - start_time).total_seconds()
            
            if not media_items:
                return (
                    f"🔍 No photos found matching criteria for {user_google_email}.\n"
                    f"⚡ Search completed in {elapsed_time:.2f}s (cached: {cache_stats['cache_size']} items)"
                )
            
            # Format results
            formatted_items = []
            for item in media_items:
                filename = item.get("filename", "Unknown")
                creation_time = item.get("mediaMetadata", {}).get("creationTime", "Unknown")
                dimensions = item.get("mediaMetadata", {})
                width = dimensions.get("width", "?")
                height = dimensions.get("height", "?")
                
                formatted_items.append(
                    f"📸 {filename} | {width}x{height} | {creation_time}"
                )
            
            # Create summary
            text_output = (
                f"🔍 **Smart Search Results for {user_google_email}**\n\n"
                f"**Found {len(media_items)} items matching criteria:**\n"
                + "\n".join(formatted_items[:20])  # Show first 20
            )
            
            if len(media_items) > 20:
                text_output += f"\n... and {len(media_items) - 20} more items"
            
            text_output += (
                f"\n\n⚡ **Performance:**\n"
                f"- Search time: {elapsed_time:.2f}s\n"
                f"- Cache hits: {cache_stats['cache_size']} items cached\n"
                f"- Daily API calls: {sum(cache_stats['daily_requests'].values())}\n"
                f"- Burst tokens remaining: {cache_stats['burst_tokens']}"
            )
            
            logger.info(f"Smart search completed in {elapsed_time:.2f}s, {len(media_items)} results")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Photos API error: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error in smart search: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool(
        name="photos_batch_details",
        description="Get detailed information for multiple photos in a single optimized request",
        tags={"photos", "batch", "details", "optimized", "google"},
        annotations={
            "title": "Batch Photo Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def photos_batch_details(
        user_google_email: str,
        media_item_ids: List[str]
    ) -> str:
        """
        Get detailed information for multiple photos using optimized batch requests.

        Args:
            user_google_email (str): User's Google email address. Required.
            media_item_ids (List[str]): List of media item IDs to get details for. Required.

        Returns:
            str: Detailed information for all requested photos.
        """
        start_time = datetime.now()
        logger.info(f"[photos_batch_details] User: {user_google_email}, Items: {len(media_item_ids)}")

        try:
            client = await _get_optimized_photos_client(user_google_email)
            
            # Process in batches (Photos API supports up to 50 per batch)
            all_results = []
            batch_size = 50
            
            for i in range(0, len(media_item_ids), batch_size):
                batch_ids = media_item_ids[i:i + batch_size]
                batch_result = await client.get_media_items_batch(batch_ids)
                
                media_items = batch_result.get("mediaItemResults", [])
                all_results.extend(media_items)
            
            elapsed_time = (datetime.now() - start_time).total_seconds()
            cache_stats = await client.get_cache_stats()
            
            # Format detailed results
            formatted_results = []
            successful_items = 0
            
            for result in all_results:
                if "mediaItem" in result:
                    item = result["mediaItem"]
                    successful_items += 1
                    
                    filename = item.get("filename", "Unknown")
                    metadata = item.get("mediaMetadata", {})
                    creation_time = metadata.get("creationTime", "Unknown")
                    dimensions = f"{metadata.get('width', '?')}x{metadata.get('height', '?')}"
                    
                    # Camera info if available
                    photo_metadata = metadata.get("photo", {})
                    camera_info = ""
                    if photo_metadata:
                        make = photo_metadata.get("cameraMake", "")
                        model = photo_metadata.get("cameraModel", "")
                        if make or model:
                            camera_info = f" | 📷 {make} {model}".strip()
                    
                    formatted_results.append(
                        f"✅ **{filename}**\n"
                        f"   📏 {dimensions} | ⏰ {creation_time}{camera_info}\n"
                        f"   🆔 {item.get('id', 'Unknown')[:20]}..."
                    )
                else:
                    # Handle errors in batch
                    status = result.get("status", {})
                    formatted_results.append(
                        f"❌ **Error**: {status.get('message', 'Unknown error')}"
                    )
            
            text_output = (
                f"📋 **Batch Photo Details for {user_google_email}**\n\n"
                f"**Processing Summary:**\n"
                f"- Requested: {len(media_item_ids)} items\n"
                f"- Successful: {successful_items} items\n"
                f"- Processing time: {elapsed_time:.2f}s\n"
                f"- Cache efficiency: {cache_stats['cache_size']} cached items\n\n"
                f"**Detailed Results:**\n"
                + "\n".join(formatted_results)
            )
            
            logger.info(f"Batch details completed: {successful_items}/{len(media_item_ids)} successful")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Photos API error: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error in batch details: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool(
        name="photos_performance_stats",
        description="Get performance statistics and cache information for Photos API usage",
        tags={"photos", "performance", "stats", "cache", "google"},
        annotations={
            "title": "Photos Performance Stats",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def photos_performance_stats(
        user_google_email: str,
        clear_cache: bool = False
    ) -> str:
        """
        Get performance statistics and cache information for Photos API usage.

        Args:
            user_google_email (str): User's Google email address. Required.
            clear_cache (bool): Whether to clear the cache after getting stats. Defaults to False.

        Returns:
            str: Performance statistics and cache information.
        """
        logger.info(f"[photos_performance_stats] User: {user_google_email}, Clear: {clear_cache}")

        try:
            if user_google_email not in _client_cache:
                return f"No optimized Photos client found for {user_google_email}. Make some API calls first."
            
            client = _client_cache[user_google_email]
            stats = await client.get_cache_stats()
            
            # Calculate cache efficiency
            cache_hit_rate = (stats['cache_size'] / max(stats['cache_size'] + 1, 1)) * 100
            
            text_output = (
                f"📊 **Photos API Performance Stats for {user_google_email}**\n\n"
                f"**Cache Information:**\n"
                f"- Current cache size: {stats['cache_size']} items\n"
                f"- Maximum cache size: {stats['max_size']} items\n"
                f"- Cache utilization: {(stats['cache_size'] / stats['max_size'] * 100):.1f}%\n"
                f"- Expired items cleaned: {stats['expired_cleaned']}\n\n"
                f"**Rate Limiting:**\n"
                f"- Burst tokens available: {stats['burst_tokens']}\n"
                f"- Daily API usage: {dict(stats['daily_requests'])}\n\n"
                f"**Optimization Impact:**\n"
                f"- Estimated cache hit benefit: Reduced API calls by caching\n"
                f"- Rate limiting active: Prevents quota exhaustion\n"
                f"- Batch operations: Up to 50x efficiency for multi-item requests"
            )
            
            if clear_cache:
                # Clear the client cache
                client._cache.cache.clear()
                client._cache.access_order.clear()
                text_output += "\n\n✅ Cache cleared successfully."
                logger.info(f"Cleared cache for {user_google_email}")
            
            return text_output
        
        except Exception as e:
            error_msg = f"❌ Unexpected error getting performance stats: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool(
        name="photos_optimized_album_sync",
        description="Efficiently sync and analyze album contents with smart caching",
        tags={"photos", "album", "sync", "optimized", "google"},
        annotations={
            "title": "Optimized Album Sync",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def photos_optimized_album_sync(
        user_google_email: str,
        album_id: str,
        analyze_metadata: bool = True,
        max_items: int = 200
    ) -> str:
        """
        Efficiently sync and analyze album contents using optimized caching.

        Args:
            user_google_email (str): User's Google email address. Required.
            album_id (str): ID of the album to sync. Required.
            analyze_metadata (bool): Whether to analyze photo metadata. Defaults to True.
            max_items (int): Maximum items to process. Defaults to 200.

        Returns:
            str: Album analysis with optimization statistics.
        """
        start_time = datetime.now()
        logger.info(f"[photos_optimized_album_sync] User: {user_google_email}, Album: {album_id}")

        try:
            client = await _get_optimized_photos_client(user_google_email)
            
            # Get album contents using optimized search
            result = await client.search_media_items(
                album_id=album_id,
                max_items=max_items
            )
            
            media_items = result.get("mediaItems", [])
            
            # Initialize analysis counters
            analysis = {
                "total_items": len(media_items),
                "photos": 0,
                "videos": 0,
                "years": set(),
                "cameras": set(),
                "file_types": set(),
            }
            
            # Analyze metadata if requested
            if analyze_metadata and media_items:
                for item in media_items:
                    mime_type = item.get("mimeType", "")
                    if mime_type.startswith("image/"):
                        analysis["photos"] += 1
                    elif mime_type.startswith("video/"):
                        analysis["videos"] += 1
                    
                    analysis["file_types"].add(mime_type.split("/")[-1].upper())
                    
                    # Extract year from creation time
                    creation_time = item.get("mediaMetadata", {}).get("creationTime")
                    if creation_time:
                        try:
                            year = datetime.fromisoformat(creation_time.replace('Z', '+00:00')).year
                            analysis["years"].add(year)
                        except:
                            pass
                    
                    # Camera info
                    photo_metadata = item.get("mediaMetadata", {}).get("photo", {})
                    camera_make = photo_metadata.get("cameraMake")
                    camera_model = photo_metadata.get("cameraModel")
                    if camera_make and camera_model:
                        analysis["cameras"].add(f"{camera_make} {camera_model}")
            
            elapsed_time = (datetime.now() - start_time).total_seconds()
            cache_stats = await client.get_cache_stats()
            
            # Format results
            years_range = f"{min(analysis['years'])} - {max(analysis['years'])}" if analysis["years"] else "Unknown"
            
            text_output = (
                f"📁 **Optimized Album Sync Results**\n\n"
                f"**Album: {album_id}**\n"
                f"- Total items: {analysis['total_items']}\n"
                f"- Photos: {analysis['photos']}\n"
                f"- Videos: {analysis['videos']}\n"
                f"- Years span: {years_range}\n"
                f"- File types: {', '.join(sorted(analysis['file_types']))}\n"
                f"- Unique cameras: {len(analysis['cameras'])}\n\n"
                f"**Performance:**\n"
                f"- Sync time: {elapsed_time:.2f}s\n"
                f"- Cache utilization: {cache_stats['cache_size']} items\n"
                f"- Rate limit status: {cache_stats['burst_tokens']} burst tokens remaining\n"
                f"- Optimization benefit: ~{analysis['total_items'] // 50}x fewer API calls via batching"
            )
            
            if analysis["cameras"]:
                text_output += f"\n\n📷 **Cameras detected:**\n"
                for camera in sorted(analysis["cameras"]):
                    text_output += f"- {camera}\n"
            
            logger.info(f"Album sync completed in {elapsed_time:.2f}s, {analysis['total_items']} items")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Photos API error: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error in album sync: {str(e)}"
            logger.error(error_msg)
            return error_msg

    logger.info("✅ Advanced Google Photos tools setup complete")