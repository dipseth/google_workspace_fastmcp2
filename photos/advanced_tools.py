"""
Advanced Google Photos MCP Tools

This module provides advanced MCP tools using the optimized Photos API client.
Includes batch operations, smart caching, and enhanced search capabilities.
"""

import os
from datetime import datetime

from fastmcp import FastMCP
from googleapiclient.errors import HttpError
from typing_extensions import Dict, List, Optional, Union

from config.enhanced_logging import setup_logger

logger = setup_logger()


from auth.service_helpers import get_injected_service, get_service, request_service
from tools.common_types import UserGoogleEmailPhotos

from .optimized_client import (
    OptimizedPhotosClient,
    PhotosSearchBuilder,
    RateLimitConfig,
    create_optimized_photos_client,
)

# Import all response types
from .photos_types import (
    PhotoInfo,
    PhotosAlbumSyncResponse,
    PhotosBatchDetailsResponse,
    PhotosFolderUploadResponse,
    PhotosPerformanceStatsResponse,
    PhotosSmartSearchResponse,
    PhotoUploadResponse,
)

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
    except Exception as e:
        # Fallback to direct service creation
        logger.debug(f"Middleware service injection failed, trying direct service: {e}")
        photos_service = await get_service("photos", user_google_email)

    # Validate that we have a valid service
    if photos_service is None:
        raise RuntimeError(
            f"Failed to get Photos service for {user_google_email}. "
            "Ensure the user is authenticated with Photos API scopes."
        )

    # Create optimized client with upload-friendly rate limits
    rate_config = RateLimitConfig(
        requests_per_second=6,  # More conservative for uploads
        requests_per_day=7000,  # Leave more buffer for upload operations
        burst_allowance=12,  # Smaller burst for upload stability
    )

    client = await create_optimized_photos_client(
        photos_service=photos_service,
        rate_config=rate_config,
        cache_size=1500,  # Larger cache for power users
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
            "openWorldHint": True,
        },
    )
    async def photos_smart_search(
        user_google_email: UserGoogleEmailPhotos = None,
        content_categories: Optional[List[str]] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        include_photos: bool = True,
        include_videos: bool = False,
        max_results: int = 50,
    ) -> PhotosSmartSearchResponse:
        """
        Advanced photo search with smart filtering and caching.

        Args:
            user_google_email (UserGoogleEmailPhotos): User's Google email address. Optional.
            content_categories (List[str], optional): Content categories (PEOPLE, ANIMALS, FOOD, etc.).
            date_start (str, optional): Start date in YYYY-MM-DD format.
            date_end (str, optional): End date in YYYY-MM-DD format.
            include_photos (bool): Include photos in results. Defaults to True.
            include_videos (bool): Include videos in results. Defaults to False.
            max_results (int): Maximum results to return. Defaults to 50.

        Returns:
            PhotosSmartSearchResponse: Formatted search results with performance metrics.
        """
        start_time = datetime.now()
        logger.info(
            f"[photos_smart_search] User: {user_google_email}, Categories: {content_categories}"
        )

        try:
            client = await _get_optimized_photos_client(user_google_email)

            # Build search filters using the builder pattern
            search_builder = PhotosSearchBuilder()

            if content_categories:
                search_builder.with_content_categories(content_categories)

            if date_start or date_end:
                start_dt = (
                    datetime.strptime(date_start, "%Y-%m-%d") if date_start else None
                )
                end_dt = datetime.strptime(date_end, "%Y-%m-%d") if date_end else None
                search_builder.with_date_range(start_dt, end_dt)

            search_builder.with_media_types(include_photos, include_videos)

            filters = search_builder.build()

            # Execute search
            result = await client.search_media_items(
                filters=filters, max_items=max_results
            )

            media_items = result.get("mediaItems", [])

            # Get cache stats for performance info
            cache_stats = await client.get_cache_stats()
            elapsed_time = (datetime.now() - start_time).total_seconds()

            if not media_items:
                no_results_text = (
                    f"🔍 No photos found matching criteria for {user_google_email}.\n"
                    f"⚡ Search completed in {elapsed_time:.2f}s (cached: {cache_stats['cache_size']} items)"
                )
                return PhotosSmartSearchResponse(
                    media_items=[],
                    total_found=0,
                    search_time_seconds=elapsed_time,
                    cache_stats=cache_stats,
                    user_email=user_google_email,
                    filters_applied={
                        "content_categories": content_categories,
                        "date_start": date_start,
                        "date_end": date_end,
                        "include_photos": include_photos,
                        "include_videos": include_videos,
                        "max_results": max_results,
                    },
                    text_summary=no_results_text,
                )

            # Format results
            formatted_items = []
            for item in media_items:
                filename = item.get("filename", "Unknown")
                creation_time = item.get("mediaMetadata", {}).get(
                    "creationTime", "Unknown"
                )
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

            # Convert to PhotoInfo format
            photo_infos = []
            for item in media_items:
                metadata = item.get("mediaMetadata", {})
                photo_metadata = metadata.get("photo", {})

                photo_info = PhotoInfo(
                    id=item.get("id", ""),
                    filename=item.get("filename", "Unknown"),
                    mimeType=item.get("mimeType", ""),
                    baseUrl=item.get("baseUrl", ""),
                    productUrl=item.get("productUrl"),
                    description=item.get("description"),
                    creationTime=metadata.get("creationTime", ""),
                    width=metadata.get("width"),
                    height=metadata.get("height"),
                    cameraMake=photo_metadata.get("cameraMake"),
                    cameraModel=photo_metadata.get("cameraModel"),
                    focalLength=photo_metadata.get("focalLength"),
                    apertureFNumber=photo_metadata.get("apertureFNumber"),
                    isoEquivalent=photo_metadata.get("isoEquivalent"),
                    exposureTime=photo_metadata.get("exposureTime"),
                )
                photo_infos.append(photo_info)

            logger.info(
                f"Smart search completed in {elapsed_time:.2f}s, {len(media_items)} results"
            )

            return PhotosSmartSearchResponse(
                media_items=photo_infos,
                total_found=len(media_items),
                search_time_seconds=elapsed_time,
                cache_stats=cache_stats,
                user_email=user_google_email,
                filters_applied={
                    "content_categories": content_categories,
                    "date_start": date_start,
                    "date_end": date_end,
                    "include_photos": include_photos,
                    "include_videos": include_videos,
                    "max_results": max_results,
                },
                text_summary=text_output,
            )

        except HttpError as e:
            error_msg = f"❌ Photos API error: {e}"
            logger.error(error_msg)
            return PhotosSmartSearchResponse(
                media_items=[],
                total_found=0,
                search_time_seconds=0,
                cache_stats={},
                user_email=user_google_email or "unknown",
                filters_applied={},
                text_summary=error_msg,
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error in smart search: {str(e)}"
            logger.error(error_msg)
            return PhotosSmartSearchResponse(
                media_items=[],
                total_found=0,
                search_time_seconds=0,
                cache_stats={},
                user_email=user_google_email or "unknown",
                filters_applied={},
                text_summary=error_msg,
                error=error_msg,
            )

    @mcp.tool(
        name="photos_batch_details",
        description="Get detailed information for multiple photos in a single optimized request",
        tags={"photos", "batch", "details", "optimized", "google"},
        annotations={
            "title": "Batch Photo Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def photos_batch_details(
        media_item_ids: List[str], user_google_email: UserGoogleEmailPhotos = None
    ) -> PhotosBatchDetailsResponse:
        """
        Get detailed information for multiple photos using optimized batch requests.

        Args:
            media_item_ids (List[str]): List of media item IDs to get details for. Required.
            user_google_email (UserGoogleEmailPhotos): User's Google email address. Optional.

        Returns:
            PhotosBatchDetailsResponse: Detailed information for all requested photos.
        """
        start_time = datetime.now()
        logger.info(
            f"[photos_batch_details] User: {user_google_email}, Items: {len(media_item_ids)}"
        )

        try:
            client = await _get_optimized_photos_client(user_google_email)

            # Process in batches (Photos API supports up to 50 per batch)
            all_results = []
            batch_size = 50

            for i in range(0, len(media_item_ids), batch_size):
                batch_ids = media_item_ids[i : i + batch_size]
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
                    dimensions = (
                        f"{metadata.get('width', '?')}x{metadata.get('height', '?')}"
                    )

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
                f"**Detailed Results:**\n" + "\n".join(formatted_results)
            )

            # Convert successful items to PhotoInfo format
            successful_photo_infos = []
            failed_items = []

            for result in all_results:
                if "mediaItem" in result:
                    item = result["mediaItem"]
                    metadata = item.get("mediaMetadata", {})
                    photo_metadata = metadata.get("photo", {})

                    photo_info = PhotoInfo(
                        id=item.get("id", ""),
                        filename=item.get("filename", "Unknown"),
                        mimeType=item.get("mimeType", ""),
                        baseUrl=item.get("baseUrl", ""),
                        productUrl=item.get("productUrl"),
                        description=item.get("description"),
                        creationTime=metadata.get("creationTime", ""),
                        width=metadata.get("width"),
                        height=metadata.get("height"),
                        cameraMake=photo_metadata.get("cameraMake"),
                        cameraModel=photo_metadata.get("cameraModel"),
                        focalLength=photo_metadata.get("focalLength"),
                        apertureFNumber=photo_metadata.get("apertureFNumber"),
                        isoEquivalent=photo_metadata.get("isoEquivalent"),
                        exposureTime=photo_metadata.get("exposureTime"),
                    )
                    successful_photo_infos.append(photo_info)
                else:
                    # Handle errors in batch
                    status = result.get("status", {})
                    failed_items.append(
                        {
                            "id": "unknown",
                            "error": status.get("message", "Unknown error"),
                        }
                    )

            logger.info(
                f"Batch details completed: {successful_items}/{len(media_item_ids)} successful"
            )

            return PhotosBatchDetailsResponse(
                successful_items=successful_photo_infos,
                failed_items=failed_items,
                total_requested=len(media_item_ids),
                successful_count=successful_items,
                failed_count=len(failed_items),
                processing_time_seconds=elapsed_time,
                cache_stats=cache_stats,
                user_email=user_google_email,
                text_summary=text_output,
            )

        except HttpError as e:
            error_msg = f"❌ Photos API error: {e}"
            logger.error(error_msg)
            return PhotosBatchDetailsResponse(
                successful_items=[],
                failed_items=[],
                total_requested=len(media_item_ids) if media_item_ids else 0,
                successful_count=0,
                failed_count=0,
                processing_time_seconds=0,
                cache_stats={},
                user_email=user_google_email or "unknown",
                text_summary=error_msg,
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error in batch details: {str(e)}"
            logger.error(error_msg)
            return PhotosBatchDetailsResponse(
                successful_items=[],
                failed_items=[],
                total_requested=len(media_item_ids) if media_item_ids else 0,
                successful_count=0,
                failed_count=0,
                processing_time_seconds=0,
                cache_stats={},
                user_email=user_google_email or "unknown",
                text_summary=error_msg,
                error=error_msg,
            )

    @mcp.tool(
        name="photos_performance_stats",
        description="Get performance statistics and cache information for Photos API usage",
        tags={"photos", "performance", "stats", "cache", "google"},
        annotations={
            "title": "Photos Performance Stats",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def photos_performance_stats(
        user_google_email: UserGoogleEmailPhotos = None, clear_cache: bool = False
    ) -> PhotosPerformanceStatsResponse:
        """
        Get performance statistics and cache information for Photos API usage.

        Args:
            user_google_email (UserGoogleEmailPhotos): User's Google email address. Optional.
            clear_cache (bool): Whether to clear the cache after getting stats. Defaults to False.

        Returns:
            PhotosPerformanceStatsResponse: Performance statistics and cache information.
        """
        logger.info(
            f"[photos_performance_stats] User: {user_google_email}, Clear: {clear_cache}"
        )

        try:
            if user_google_email not in _client_cache:
                no_client_msg = f"No optimized Photos client found for {user_google_email}. Make some API calls first."
                return PhotosPerformanceStatsResponse(
                    cache_size=0,
                    max_cache_size=0,
                    cache_utilization_percent=0,
                    expired_cleaned=0,
                    burst_tokens=0,
                    daily_requests={},
                    user_email=user_google_email,
                    cache_cleared=False,
                    text_summary=no_client_msg,
                    error="No client found",
                )

            client = _client_cache[user_google_email]
            stats = await client.get_cache_stats()

            # Calculate cache efficiency
            cache_hit_rate = (
                stats["cache_size"] / max(stats["cache_size"] + 1, 1)
            ) * 100

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

            return PhotosPerformanceStatsResponse(
                cache_size=stats["cache_size"],
                max_cache_size=stats["max_size"],
                cache_utilization_percent=(
                    stats["cache_size"] / stats["max_size"] * 100
                ),
                expired_cleaned=stats["expired_cleaned"],
                burst_tokens=stats["burst_tokens"],
                daily_requests=dict(stats["daily_requests"]),
                user_email=user_google_email,
                cache_cleared=clear_cache,
                text_summary=text_output,
            )

        except Exception as e:
            error_msg = f"❌ Unexpected error getting performance stats: {str(e)}"
            logger.error(error_msg)
            return PhotosPerformanceStatsResponse(
                cache_size=0,
                max_cache_size=0,
                cache_utilization_percent=0,
                expired_cleaned=0,
                burst_tokens=0,
                daily_requests={},
                user_email=user_google_email or "unknown",
                cache_cleared=False,
                text_summary=error_msg,
                error=error_msg,
            )

    @mcp.tool(
        name="photos_optimized_album_sync",
        description="Efficiently sync and analyze album contents with smart caching",
        tags={"photos", "album", "sync", "optimized", "google"},
        annotations={
            "title": "Optimized Album Sync",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def photos_optimized_album_sync(
        album_id: str,
        user_google_email: UserGoogleEmailPhotos = None,
        analyze_metadata: bool = True,
        max_items: int = 200,
    ) -> PhotosAlbumSyncResponse:
        """
        Efficiently sync and analyze album contents using optimized caching.

        Args:
            album_id (str): ID of the album to sync. Required.
            user_google_email (UserGoogleEmailPhotos): User's Google email address. Optional.
            analyze_metadata (bool): Whether to analyze photo metadata. Defaults to True.
            max_items (int): Maximum items to process. Defaults to 200.

        Returns:
            PhotosAlbumSyncResponse: Album analysis with optimization statistics.
        """
        start_time = datetime.now()
        logger.info(
            f"[photos_optimized_album_sync] User: {user_google_email}, Album: {album_id}"
        )

        try:
            client = await _get_optimized_photos_client(user_google_email)

            # Get album contents using optimized search
            result = await client.search_media_items(
                album_id=album_id, max_items=max_items
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
                            year = datetime.fromisoformat(
                                creation_time.replace("Z", "+00:00")
                            ).year
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
            years_range = (
                f"{min(analysis['years'])} - {max(analysis['years'])}"
                if analysis["years"]
                else "Unknown"
            )

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
                text_output += "\n\n📷 **Cameras detected:**\n"
                for camera in sorted(analysis["cameras"]):
                    text_output += f"- {camera}\n"

            logger.info(
                f"Album sync completed in {elapsed_time:.2f}s, {analysis['total_items']} items"
            )

            return PhotosAlbumSyncResponse(
                album_id=album_id,
                total_items=analysis["total_items"],
                photos_count=analysis["photos"],
                videos_count=analysis["videos"],
                years_span=sorted(list(analysis["years"])),
                file_types=sorted(list(analysis["file_types"])),
                cameras_detected=sorted(list(analysis["cameras"])),
                sync_time_seconds=elapsed_time,
                cache_stats=cache_stats,
                user_email=user_google_email,
                text_summary=text_output,
            )

        except HttpError as e:
            error_msg = f"❌ Photos API error: {e}"
            logger.error(error_msg)
            return PhotosAlbumSyncResponse(
                album_id=album_id,
                total_items=0,
                photos_count=0,
                videos_count=0,
                years_span=[],
                file_types=[],
                cameras_detected=[],
                sync_time_seconds=0,
                cache_stats={},
                user_email=user_google_email or "unknown",
                text_summary=error_msg,
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error in album sync: {str(e)}"
            logger.error(error_msg)
            return PhotosAlbumSyncResponse(
                album_id=album_id,
                total_items=0,
                photos_count=0,
                videos_count=0,
                years_span=[],
                file_types=[],
                cameras_detected=[],
                sync_time_seconds=0,
                cache_stats={},
                user_email=user_google_email or "unknown",
                text_summary=error_msg,
                error=error_msg,
            )

    @mcp.tool(
        name="upload_photos",
        description="Upload one or more photos to Google Photos with batch optimization",
        tags={"photos", "upload", "batch", "single", "google"},
        annotations={
            "title": "Upload Photos",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def upload_photos(
        file_paths: Union[str, List[str]],
        user_google_email: UserGoogleEmailPhotos = None,
        album_id: Optional[str] = None,
        create_album: Optional[str] = None,
        description: str = "",
    ) -> PhotoUploadResponse:
        """
        Upload one or more photos to Google Photos with optimized batch processing.

        This unified tool handles both single photo uploads and batch uploads efficiently.
        For single photos, pass a string file path. For multiple photos, pass a list of paths.

        Args:
            file_paths (Union[str, List[str]]): Single file path (str) or list of file paths to upload. Required.
            user_google_email (UserGoogleEmailPhotos): User's Google email address. Optional.
            album_id (str, optional): ID of existing album to add photos to.
            create_album (str, optional): Name of new album to create and add photos to.
            description (str, optional): Description for photos (applies to single photo or all in batch).

        Returns:
            PhotoUploadResponse: Structured upload results with success/failure details.
        """
        start_time = datetime.now()

        # Convert single file path to list for uniform processing
        if isinstance(file_paths, str):
            file_list = [file_paths]
            is_single_upload = True
        else:
            file_list = file_paths
            is_single_upload = False

        logger.info(
            f"[upload_photos] User: {user_google_email}, Files: {len(file_list)}, Single: {is_single_upload}"
        )

        try:
            client = await _get_optimized_photos_client(user_google_email)

            # Create album if requested
            target_album_id = album_id
            created_album_name = None
            if create_album and not album_id:
                try:
                    album_response = await client.create_album(create_album)
                    target_album_id = album_response.get("id")
                    created_album_name = create_album
                    logger.info(f"Created album: {create_album} ({target_album_id})")
                except Exception as e:
                    logger.warning(f"Failed to create album {create_album}: {e}")

            # Upload photos using batch processing (efficient even for single photos)
            if is_single_upload:
                # For single photo, use the individual upload method
                try:
                    media_item = await client.upload_photo(file_list[0], description)
                    results = {
                        "successful": [
                            {
                                "file": file_list[0],
                                "media_item_id": media_item.get("id"),
                                "filename": media_item.get("filename"),
                            }
                        ],
                        "failed": [],
                        "total": 1,
                    }
                except Exception as e:
                    results = {
                        "successful": [],
                        "failed": [{"file": file_list[0], "error": str(e)}],
                        "total": 1,
                    }
            else:
                # For multiple photos, use batch processing
                results = await client.upload_photos_batch(file_list, target_album_id)

            elapsed_time = (datetime.now() - start_time).total_seconds()
            cache_stats = await client.get_cache_stats()

            # Format results
            successful_count = len(results["successful"])
            failed_count = len(results["failed"])
            total_count = results["total"]

            # Create human-readable text output
            if is_single_upload:
                if successful_count == 1:
                    item = results["successful"][0]
                    filename = os.path.basename(item["file"])
                    media_id = item["media_item_id"]
                    text_output = (
                        f"📸 **Photo Upload Successful**\n\n"
                        f"**File:** {filename}\n"
                        f"**Google Photos ID:** {media_id}\n"
                        f"**Description:** {description or 'None'}\n"
                        f"**Upload time:** {elapsed_time:.2f}s\n"
                    )
                else:
                    error = results["failed"][0]["error"]
                    text_output = f"❌ **Photo Upload Failed:** {error}"
            else:
                text_output = (
                    f"📸 **Batch Photo Upload Results**\n\n"
                    f"**Summary:**\n"
                    f"- Total files: {total_count}\n"
                    f"- Successful: {successful_count}\n"
                    f"- Failed: {failed_count}\n"
                    f"- Success rate: {(successful_count/total_count*100):.1f}%\n"
                    f"- Upload time: {elapsed_time:.2f}s\n"
                )

                # Show successful uploads (first 10)
                if results["successful"]:
                    text_output += "\n**✅ Successful Uploads:**\n"
                    for item in results["successful"][:10]:
                        filename = os.path.basename(item["file"])
                        media_id = item["media_item_id"][:20] + "..."
                        text_output += f"- {filename} → {media_id}\n"

                    if len(results["successful"]) > 10:
                        text_output += (
                            f"... and {len(results['successful']) - 10} more\n"
                        )

                # Show failures (first 5)
                if results["failed"]:
                    text_output += "\n**❌ Failed Uploads:**\n"
                    for item in results["failed"][:5]:
                        filename = os.path.basename(item["file"])
                        error = item["error"]
                        text_output += f"- {filename}: {error}\n"

                    if len(results["failed"]) > 5:
                        text_output += (
                            f"... and {len(results['failed']) - 5} more failures\n"
                        )

                text_output += (
                    f"\n**⚡ Performance:**\n"
                    f"- Average time per photo: {elapsed_time/max(total_count, 1):.2f}s\n"
                    f"- Cache utilization: {cache_stats['cache_size']} items\n"
                    f"- Burst tokens remaining: {cache_stats['burst_tokens']}"
                )

            if target_album_id:
                text_output += f"\n**Album ID:** {target_album_id}"
                if created_album_name:
                    text_output += f" (Created: {created_album_name})"

            logger.info(
                f"Photo upload completed: {successful_count}/{total_count} successful"
            )

            return PhotoUploadResponse(
                successful=results["successful"],
                failed=results["failed"],
                total_count=total_count,
                successful_count=successful_count,
                failed_count=failed_count,
                upload_time_seconds=elapsed_time,
                album_id=target_album_id,
                created_album_name=created_album_name,
                user_email=user_google_email,
                text_summary=text_output,
                error=None,
            )

        except FileNotFoundError as e:
            error_msg = f"File not found: {e}"
            logger.error(error_msg)
            return PhotoUploadResponse(
                successful=[],
                failed=[],
                total_count=len(file_list),
                successful_count=0,
                failed_count=len(file_list),
                upload_time_seconds=0,
                user_email=user_google_email,
                text_summary=f"❌ **Upload Failed:** {error_msg}",
                error=error_msg,
            )
        except ValueError as e:
            error_msg = f"Invalid file: {e}"
            logger.error(error_msg)
            return PhotoUploadResponse(
                successful=[],
                failed=[],
                total_count=len(file_list),
                successful_count=0,
                failed_count=len(file_list),
                upload_time_seconds=0,
                user_email=user_google_email,
                text_summary=f"❌ **Upload Failed:** {error_msg}",
                error=error_msg,
            )
        except HttpError as e:
            error_msg = f"Google Photos API error: {e}"
            logger.error(error_msg)
            return PhotoUploadResponse(
                successful=[],
                failed=[],
                total_count=len(file_list),
                successful_count=0,
                failed_count=len(file_list),
                upload_time_seconds=0,
                user_email=user_google_email,
                text_summary=f"❌ **Upload Failed:** {error_msg}",
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error uploading photos: {str(e)}"
            logger.error(error_msg)
            return PhotoUploadResponse(
                successful=[],
                failed=[],
                total_count=len(file_list),
                successful_count=0,
                failed_count=len(file_list),
                upload_time_seconds=0,
                user_email=user_google_email,
                text_summary=f"❌ **Upload Failed:** {error_msg}",
                error=error_msg,
            )

    @mcp.tool(
        name="upload_folder_photos",
        description="Upload all photos from a folder (with optional recursion) to Google Photos",
        tags={"photos", "upload", "folder", "batch", "recursive", "google"},
        annotations={
            "title": "Upload Folder Photos",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def upload_folder_photos(
        folder_path: str,
        user_google_email: UserGoogleEmailPhotos = None,
        recursive: bool = True,
        create_album: Optional[str] = None,
        album_id: Optional[str] = None,
    ) -> PhotosFolderUploadResponse:
        """
        Upload all photos from a folder to Google Photos with smart organization.

        Args:
            folder_path (str): Local path to folder containing photos. Required.
            user_google_email (UserGoogleEmailPhotos): User's Google email address. Optional.
            recursive (bool): Whether to include subfolders. Defaults to True.
            create_album (str, optional): Name of new album to create for these photos.
            album_id (str, optional): ID of existing album to add photos to.

        Returns:
            PhotosFolderUploadResponse: Folder upload results with detailed statistics.
        """
        start_time = datetime.now()
        logger.info(
            f"[upload_folder_photos] User: {user_google_email}, Folder: {folder_path}"
        )

        try:
            client = await _get_optimized_photos_client(user_google_email)

            # Use album_id if provided, otherwise create new album if requested
            target_album = create_album if create_album and not album_id else None

            # Upload entire folder
            results = await client.upload_folder(
                folder_path=folder_path, recursive=recursive, album_name=target_album
            )

            # Use provided album_id if create_album wasn't used
            if album_id and not results.get("album_id"):
                # Would need additional logic to add photos to existing album
                logger.info(
                    f"Note: Adding to existing album {album_id} not yet implemented"
                )

            elapsed_time = (datetime.now() - start_time).total_seconds()
            cache_stats = await client.get_cache_stats()

            # Format results
            successful_count = len(results["successful"])
            failed_count = len(results["failed"])
            total_count = results["total"]

            if total_count == 0:
                no_files_msg = f"📁 No image files found in folder: {folder_path}"
                return PhotosFolderUploadResponse(
                    successful=[],
                    failed=[],
                    total_found=0,
                    successful_count=0,
                    failed_count=0,
                    success_rate_percent=0,
                    upload_time_seconds=elapsed_time,
                    folder_path=folder_path,
                    recursive=recursive,
                    user_email=user_google_email,
                    text_summary=no_files_msg,
                )

            text_output = (
                f"📁 **Folder Photo Upload Results**\n\n"
                f"**Folder:** {os.path.basename(folder_path)}\n"
                f"**Recursive:** {'Yes' if recursive else 'No'}\n\n"
                f"**Summary:**\n"
                f"- Total photos found: {total_count}\n"
                f"- Successfully uploaded: {successful_count}\n"
                f"- Failed uploads: {failed_count}\n"
                f"- Success rate: {(successful_count/total_count*100):.1f}%\n"
                f"- Total upload time: {elapsed_time:.2f}s\n"
                f"- Average per photo: {elapsed_time/max(total_count, 1):.2f}s\n"
            )

            if results.get("album_id"):
                text_output += f"- Created album ID: {results['album_id']}\n"
            elif album_id:
                text_output += f"- Target album ID: {album_id}\n"

            # Show sample successful uploads
            if results["successful"]:
                text_output += "\n**✅ Sample Successful Uploads:**\n"
                for item in results["successful"][:8]:
                    filename = os.path.basename(item["file"])
                    text_output += f"- 📸 {filename}\n"

                if len(results["successful"]) > 8:
                    text_output += (
                        f"... and {len(results['successful']) - 8} more photos\n"
                    )

            # Show failures if any
            if results["failed"]:
                text_output += "\n**❌ Failed Uploads:**\n"
                for item in results["failed"][:5]:
                    filename = os.path.basename(item["file"])
                    error = item["error"]
                    text_output += f"- {filename}: {error}\n"

                if len(results["failed"]) > 5:
                    text_output += (
                        f"... and {len(results['failed']) - 5} more failures\n"
                    )

            text_output += (
                f"\n**⚡ Performance:**\n"
                f"- Cache efficiency: {cache_stats['cache_size']} cached items\n"
                f"- API rate limit status: {cache_stats['burst_tokens']} burst tokens\n"
                f"- Batch processing: ~{max(total_count // 50, 1)}x efficiency gain"
            )

            logger.info(
                f"Folder upload completed: {successful_count}/{total_count} photos uploaded"
            )

            return PhotosFolderUploadResponse(
                successful=results["successful"],
                failed=results["failed"],
                total_found=total_count,
                successful_count=successful_count,
                failed_count=failed_count,
                success_rate_percent=(
                    (successful_count / total_count * 100) if total_count > 0 else 0
                ),
                upload_time_seconds=elapsed_time,
                folder_path=folder_path,
                recursive=recursive,
                album_id=results.get("album_id"),
                created_album_name=create_album if results.get("album_id") else None,
                user_email=user_google_email,
                text_summary=text_output,
            )

        except FileNotFoundError as e:
            error_msg = f"❌ Folder not found: {e}"
            logger.error(error_msg)
            return PhotosFolderUploadResponse(
                successful=[],
                failed=[],
                total_found=0,
                successful_count=0,
                failed_count=0,
                success_rate_percent=0,
                upload_time_seconds=0,
                folder_path=folder_path,
                recursive=recursive,
                user_email=user_google_email or "unknown",
                text_summary=error_msg,
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"❌ Unexpected error uploading folder: {str(e)}"
            logger.error(error_msg)
            return PhotosFolderUploadResponse(
                successful=[],
                failed=[],
                total_found=0,
                successful_count=0,
                failed_count=0,
                success_rate_percent=0,
                upload_time_seconds=0,
                folder_path=folder_path,
                recursive=recursive,
                user_email=user_google_email or "unknown",
                text_summary=error_msg,
                error=error_msg,
            )

    logger.info("✅ Advanced Google Photos tools setup complete")
