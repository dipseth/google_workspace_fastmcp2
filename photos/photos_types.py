"""
Google Photos MCP Types

This module defines all data structures and types used in Google Photos MCP tools.
"""

from typing_extensions import Any, Dict, List, NotRequired, Optional, TypedDict


class AlbumInfo(TypedDict):
    """Structure for a single photo album."""

    id: str
    title: str
    productUrl: NotRequired[Optional[str]]
    mediaItemsCount: NotRequired[Optional[str]]
    coverPhotoBaseUrl: NotRequired[Optional[str]]
    coverPhotoMediaItemId: NotRequired[Optional[str]]


class PhotoInfo(TypedDict):
    """Structure for a single photo/media item."""

    id: str
    filename: str
    mimeType: str
    baseUrl: str
    productUrl: NotRequired[Optional[str]]
    description: NotRequired[Optional[str]]
    creationTime: str
    width: NotRequired[Optional[str]]
    height: NotRequired[Optional[str]]
    cameraMake: NotRequired[Optional[str]]
    cameraModel: NotRequired[Optional[str]]
    focalLength: NotRequired[Optional[float]]
    apertureFNumber: NotRequired[Optional[float]]
    isoEquivalent: NotRequired[Optional[int]]
    exposureTime: NotRequired[Optional[str]]


class AlbumListResponse(TypedDict):
    """Response structure for list_photos_albums tool."""

    albums: List[AlbumInfo]
    count: int
    excludeNonAppCreated: bool
    userEmail: str
    error: NotRequired[Optional[str]]  # Optional error message for error responses


class PhotoListResponse(TypedDict):
    """Response structure for photo list operations."""

    photos: List[PhotoInfo]
    count: int
    albumId: NotRequired[Optional[str]]
    userEmail: NotRequired[Optional[str]]
    error: NotRequired[Optional[str]]


class PhotoUploadResponse(TypedDict):
    """Response structure for photo upload operations."""

    successful: List[Dict[str, Any]]
    failed: List[Dict[str, Any]]
    total_count: int
    successful_count: int
    failed_count: int
    upload_time_seconds: float
    album_id: NotRequired[Optional[str]]
    created_album_name: NotRequired[Optional[str]]
    user_email: NotRequired[Optional[str]]
    text_summary: NotRequired[Optional[str]]
    error: NotRequired[Optional[str]]


class PhotosSmartSearchResponse(TypedDict):
    """Response structure for smart photo search operations."""

    media_items: List[PhotoInfo]
    total_found: int
    search_time_seconds: float
    cache_stats: Dict[str, Any]
    user_email: str
    filters_applied: Dict[str, Any]
    text_summary: str
    error: NotRequired[Optional[str]]


class PhotosBatchDetailsResponse(TypedDict):
    """Response structure for batch photo details operations."""

    successful_items: List[PhotoInfo]
    failed_items: List[Dict[str, str]]  # {"id": str, "error": str}
    total_requested: int
    successful_count: int
    failed_count: int
    processing_time_seconds: float
    cache_stats: Dict[str, Any]
    user_email: str
    text_summary: str
    error: NotRequired[Optional[str]]


class PhotosPerformanceStatsResponse(TypedDict):
    """Response structure for photos performance statistics."""

    cache_size: int
    max_cache_size: int
    cache_utilization_percent: float
    expired_cleaned: int
    burst_tokens: int
    daily_requests: Dict[str, int]
    user_email: str
    cache_cleared: bool
    text_summary: str
    error: NotRequired[Optional[str]]


class PhotosAlbumSyncResponse(TypedDict):
    """Response structure for optimized album sync operations."""

    album_id: str
    total_items: int
    photos_count: int
    videos_count: int
    years_span: List[int]
    file_types: List[str]
    cameras_detected: List[str]
    sync_time_seconds: float
    cache_stats: Dict[str, Any]
    user_email: str
    text_summary: str
    error: NotRequired[Optional[str]]


class PhotosFolderUploadResponse(TypedDict):
    """Response structure for folder photo upload operations."""

    successful: List[Dict[str, Any]]
    failed: List[Dict[str, Any]]
    total_found: int
    successful_count: int
    failed_count: int
    success_rate_percent: float
    upload_time_seconds: float
    folder_path: str
    recursive: bool
    user_email: str
    text_summary: str
    album_id: NotRequired[Optional[str]]
    created_album_name: NotRequired[Optional[str]]
    error: NotRequired[Optional[str]]
