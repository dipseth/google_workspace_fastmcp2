"""
Type definitions for Google Photos API tool responses.

These Pydantic BaseModel classes define the structure of data returned by Photos API
tools, enabling FastMCP to automatically generate JSON schemas with rich field descriptions
for better MCP client integration.
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


# =============================================================================
# Album and Photo Info Types
# =============================================================================


class AlbumInfo(BaseModel):
    """Information about a single photo album."""

    id: str = Field(..., description="Unique identifier for the album")
    title: str = Field(..., description="Title/name of the album")
    productUrl: Optional[str] = Field(
        None, description="URL to view the album in Google Photos"
    )
    mediaItemsCount: Optional[str] = Field(
        None, description="Number of media items in the album"
    )
    coverPhotoBaseUrl: Optional[str] = Field(
        None, description="Base URL for the album's cover photo"
    )
    coverPhotoMediaItemId: Optional[str] = Field(
        None, description="Media item ID of the album's cover photo"
    )


class PhotoInfo(BaseModel):
    """Information about a single photo/media item."""

    id: str = Field(..., description="Unique identifier for the photo")
    filename: str = Field(..., description="Original filename of the photo")
    mimeType: str = Field(..., description="MIME type of the photo (e.g., 'image/jpeg')")
    baseUrl: str = Field(..., description="Base URL for accessing the photo")
    productUrl: Optional[str] = Field(
        None, description="URL to view the photo in Google Photos"
    )
    description: Optional[str] = Field(
        None, description="User-provided description of the photo"
    )
    creationTime: str = Field(
        ..., description="ISO 8601 timestamp when the photo was created"
    )
    width: Optional[str] = Field(None, description="Width of the photo in pixels")
    height: Optional[str] = Field(None, description="Height of the photo in pixels")
    cameraMake: Optional[str] = Field(
        None, description="Make/brand of the camera used"
    )
    cameraModel: Optional[str] = Field(
        None, description="Model of the camera used"
    )
    focalLength: Optional[float] = Field(
        None, description="Focal length in millimeters"
    )
    apertureFNumber: Optional[float] = Field(
        None, description="Aperture f-number (e.g., 2.8)"
    )
    isoEquivalent: Optional[int] = Field(
        None, description="ISO sensitivity value"
    )
    exposureTime: Optional[str] = Field(
        None, description="Exposure time (e.g., '1/125s')"
    )


# =============================================================================
# Album List Response
# =============================================================================


class AlbumListResponse(BaseModel):
    """Response structure for list_photos_albums tool."""

    success: bool = Field(
        True, description="Whether the operation completed successfully"
    )
    albums: List[AlbumInfo] = Field(
        default_factory=list, description="List of photo albums with their metadata"
    )
    count: int = Field(0, description="Number of albums returned")
    excludeNonAppCreated: bool = Field(
        False, description="Whether non-app-created albums were excluded"
    )
    userEmail: str = Field(
        "", description="Email address of the user whose albums were listed"
    )
    error: Optional[str] = Field(
        None, description="Error message if operation failed"
    )


# =============================================================================
# Photo List Response
# =============================================================================


class PhotoListResponse(BaseModel):
    """Response structure for photo list operations."""

    success: bool = Field(
        True, description="Whether the operation completed successfully"
    )
    photos: List[PhotoInfo] = Field(
        default_factory=list, description="List of photos with their metadata"
    )
    count: int = Field(0, description="Number of photos returned")
    albumId: Optional[str] = Field(
        None, description="Album ID if photos were retrieved from a specific album"
    )
    userEmail: Optional[str] = Field(
        None, description="Email address of the user whose photos were listed"
    )
    error: Optional[str] = Field(
        None, description="Error message if operation failed"
    )


# =============================================================================
# Photo Upload Response
# =============================================================================


class UploadedPhotoInfo(BaseModel):
    """Information about a successfully uploaded photo."""

    file: str = Field(..., description="Local file path that was uploaded")
    media_item_id: Optional[str] = Field(
        None, description="Google Photos media item ID of the uploaded photo"
    )
    filename: Optional[str] = Field(
        None, description="Filename in Google Photos"
    )


class FailedUploadInfo(BaseModel):
    """Information about a failed photo upload."""

    file: str = Field(..., description="Local file path that failed to upload")
    error: str = Field(..., description="Error message describing the failure")


class PhotoUploadResponse(BaseModel):
    """Response structure for photo upload operations."""

    success: bool = Field(
        True, description="Whether the overall upload operation succeeded"
    )
    successful: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of successfully uploaded photos with their details"
    )
    failed: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of failed uploads with error information"
    )
    total_count: int = Field(0, description="Total number of files processed")
    successful_count: int = Field(0, description="Number of successfully uploaded files")
    failed_count: int = Field(0, description="Number of failed uploads")
    upload_time_seconds: float = Field(
        0.0, description="Total time taken for the upload operation in seconds"
    )
    album_id: Optional[str] = Field(
        None, description="Album ID where photos were uploaded (if specified)"
    )
    created_album_name: Optional[str] = Field(
        None, description="Name of newly created album (if a new album was created)"
    )
    user_email: Optional[str] = Field(
        None, description="Email address of the user who uploaded the photos"
    )
    text_summary: Optional[str] = Field(
        None, description="Human-readable summary of the upload operation"
    )
    error: Optional[str] = Field(
        None, description="Error message if operation failed"
    )


# =============================================================================
# Smart Search Response
# =============================================================================


class PhotosSmartSearchResponse(BaseModel):
    """Response structure for smart photo search operations."""

    success: bool = Field(
        True, description="Whether the search operation succeeded"
    )
    media_items: List[PhotoInfo] = Field(
        default_factory=list,
        description="List of photos matching the search criteria"
    )
    total_found: int = Field(0, description="Total number of matching photos found")
    search_time_seconds: float = Field(
        0.0, description="Time taken for the search operation in seconds"
    )
    cache_stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Cache statistics including size, hits, and performance metrics"
    )
    user_email: str = Field(
        "", description="Email address of the user who performed the search"
    )
    filters_applied: Dict[str, Any] = Field(
        default_factory=dict,
        description="Search filters that were applied (categories, dates, media types)"
    )
    text_summary: str = Field(
        "", description="Human-readable summary of search results"
    )
    error: Optional[str] = Field(
        None, description="Error message if search failed"
    )


# =============================================================================
# Batch Details Response
# =============================================================================


class FailedBatchItem(BaseModel):
    """Information about a failed batch detail request."""

    id: str = Field(..., description="Media item ID that failed")
    error: str = Field(..., description="Error message describing the failure")


class PhotosBatchDetailsResponse(BaseModel):
    """Response structure for batch photo details operations."""

    success: bool = Field(
        True, description="Whether the batch details operation succeeded"
    )
    successful_items: List[PhotoInfo] = Field(
        default_factory=list,
        description="List of photos with successfully retrieved details"
    )
    failed_items: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of items that failed to retrieve with error info"
    )
    total_requested: int = Field(
        0, description="Total number of photo IDs requested"
    )
    successful_count: int = Field(
        0, description="Number of photos with successfully retrieved details"
    )
    failed_count: int = Field(
        0, description="Number of photos that failed to retrieve details"
    )
    processing_time_seconds: float = Field(
        0.0, description="Time taken for the batch operation in seconds"
    )
    cache_stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Cache statistics for the batch operation"
    )
    user_email: str = Field(
        "", description="Email address of the user"
    )
    text_summary: str = Field(
        "", description="Human-readable summary of batch results"
    )
    error: Optional[str] = Field(
        None, description="Error message if operation failed"
    )


# =============================================================================
# Performance Stats Response
# =============================================================================


class PhotosPerformanceStatsResponse(BaseModel):
    """Response structure for photos performance statistics."""

    success: bool = Field(
        True, description="Whether the stats retrieval succeeded"
    )
    cache_size: int = Field(
        0, description="Current number of items in the cache"
    )
    max_cache_size: int = Field(
        0, description="Maximum cache size limit"
    )
    cache_utilization_percent: float = Field(
        0.0, description="Percentage of cache capacity currently in use"
    )
    expired_cleaned: int = Field(
        0, description="Number of expired items cleaned from cache"
    )
    burst_tokens: int = Field(
        0, description="Remaining burst tokens for rate limiting"
    )
    daily_requests: Dict[str, int] = Field(
        default_factory=dict,
        description="Daily API request counts by endpoint"
    )
    user_email: str = Field(
        "", description="Email address of the user"
    )
    cache_cleared: bool = Field(
        False, description="Whether the cache was cleared during this operation"
    )
    text_summary: str = Field(
        "", description="Human-readable performance summary"
    )
    error: Optional[str] = Field(
        None, description="Error message if stats retrieval failed"
    )


# =============================================================================
# Album Sync Response
# =============================================================================


class PhotosAlbumSyncResponse(BaseModel):
    """Response structure for optimized album sync operations."""

    success: bool = Field(
        True, description="Whether the album sync operation succeeded"
    )
    album_id: str = Field(..., description="ID of the synced album")
    total_items: int = Field(
        0, description="Total number of items in the album"
    )
    photos_count: int = Field(
        0, description="Number of photos in the album"
    )
    videos_count: int = Field(
        0, description="Number of videos in the album"
    )
    years_span: List[int] = Field(
        default_factory=list,
        description="List of years represented in the album content"
    )
    file_types: List[str] = Field(
        default_factory=list,
        description="List of unique file types found in the album"
    )
    cameras_detected: List[str] = Field(
        default_factory=list,
        description="List of unique cameras used to capture album content"
    )
    sync_time_seconds: float = Field(
        0.0, description="Time taken for the sync operation in seconds"
    )
    cache_stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Cache statistics for the sync operation"
    )
    user_email: str = Field(
        "", description="Email address of the user"
    )
    text_summary: str = Field(
        "", description="Human-readable sync summary"
    )
    error: Optional[str] = Field(
        None, description="Error message if sync failed"
    )


# =============================================================================
# Folder Upload Response
# =============================================================================


class PhotosFolderUploadResponse(BaseModel):
    """Response structure for folder photo upload operations."""

    success: bool = Field(
        True, description="Whether the folder upload operation succeeded"
    )
    successful: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of successfully uploaded photos with details"
    )
    failed: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of failed uploads with error information"
    )
    total_found: int = Field(
        0, description="Total number of photo files found in the folder"
    )
    successful_count: int = Field(
        0, description="Number of successfully uploaded files"
    )
    failed_count: int = Field(
        0, description="Number of failed uploads"
    )
    success_rate_percent: float = Field(
        0.0, description="Percentage of successful uploads"
    )
    upload_time_seconds: float = Field(
        0.0, description="Total time taken for the upload operation in seconds"
    )
    folder_path: str = Field(
        ..., description="Local folder path that was uploaded"
    )
    recursive: bool = Field(
        True, description="Whether subfolders were included"
    )
    user_email: str = Field(
        "", description="Email address of the user"
    )
    text_summary: str = Field(
        "", description="Human-readable upload summary"
    )
    album_id: Optional[str] = Field(
        None, description="Album ID where photos were uploaded (if specified)"
    )
    created_album_name: Optional[str] = Field(
        None, description="Name of newly created album (if a new album was created)"
    )
    error: Optional[str] = Field(
        None, description="Error message if operation failed"
    )


# =============================================================================
# Photo Details Response (for get_photo_details tool)
# =============================================================================


class PhotoDetailsResponse(BaseModel):
    """Response structure for get_photo_details tool."""

    success: bool = Field(
        True, description="Whether the details retrieval succeeded"
    )
    photo: Optional[PhotoInfo] = Field(
        None, description="Detailed photo information"
    )
    media_item_id: str = Field(
        "", description="The media item ID that was queried"
    )
    user_email: str = Field(
        "", description="Email address of the user"
    )
    text_summary: str = Field(
        "", description="Human-readable photo details summary"
    )
    error: Optional[str] = Field(
        None, description="Error message if retrieval failed"
    )


# =============================================================================
# Create Album Response
# =============================================================================


class CreateAlbumResponse(BaseModel):
    """Response structure for create_photos_album tool."""

    success: bool = Field(
        True, description="Whether the album creation succeeded"
    )
    album_id: Optional[str] = Field(
        None, description="ID of the newly created album"
    )
    album_title: str = Field(
        "", description="Title of the created album"
    )
    product_url: Optional[str] = Field(
        None, description="URL to view the album in Google Photos"
    )
    user_email: str = Field(
        "", description="Email address of the user who created the album"
    )
    message: str = Field(
        "", description="Human-readable creation message"
    )
    error: Optional[str] = Field(
        None, description="Error message if creation failed"
    )


# =============================================================================
# Library Info Response
# =============================================================================


class LibraryInfoResponse(BaseModel):
    """Response structure for get_photos_library_info tool."""

    success: bool = Field(
        True, description="Whether the library info retrieval succeeded"
    )
    album_count: int = Field(
        0, description="Number of albums in the library"
    )
    recent_photos_count: int = Field(
        0, description="Number of recent photos accessed"
    )
    recent_albums: List[AlbumInfo] = Field(
        default_factory=list,
        description="List of recent albums"
    )
    user_email: str = Field(
        "", description="Email address of the user"
    )
    text_summary: str = Field(
        "", description="Human-readable library summary"
    )
    error: Optional[str] = Field(
        None, description="Error message if retrieval failed"
    )


# =============================================================================
# Search Photos Response
# =============================================================================


class SearchPhotosResponse(BaseModel):
    """Response structure for search_photos tool."""

    success: bool = Field(
        True, description="Whether the search succeeded"
    )
    photos: List[PhotoInfo] = Field(
        default_factory=list,
        description="List of photos matching the search criteria"
    )
    count: int = Field(0, description="Number of photos found")
    filters_applied: Dict[str, Any] = Field(
        default_factory=dict,
        description="Search filters that were applied"
    )
    user_email: str = Field(
        "", description="Email address of the user"
    )
    text_summary: str = Field(
        "", description="Human-readable search summary"
    )
    error: Optional[str] = Field(
        None, description="Error message if search failed"
    )
