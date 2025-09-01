"""
Type definitions for Google Photos tool responses.

These TypedDict classes define the structure of data returned by Photos tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional, NotRequired


class AlbumInfo(TypedDict):
    """Structure for a single photo album."""
    id: str
    title: str
    productUrl: Optional[str]
    mediaItemsCount: Optional[str]
    coverPhotoBaseUrl: Optional[str]
    coverPhotoMediaItemId: Optional[str]


class PhotoInfo(TypedDict):
    """Structure for a single photo/media item."""
    id: str
    filename: str
    mimeType: str
    baseUrl: str
    productUrl: Optional[str]
    description: Optional[str]
    creationTime: str
    width: Optional[str]
    height: Optional[str]
    cameraMake: Optional[str]
    cameraModel: Optional[str]
    focalLength: Optional[float]
    apertureFNumber: Optional[float]
    isoEquivalent: Optional[int]
    exposureTime: Optional[str]


class AlbumListResponse(TypedDict):
    """Response structure for list_photos_albums tool."""
    albums: List[AlbumInfo]
    count: int
    excludeNonAppCreated: bool
    userEmail: str
    error: NotRequired[Optional[str]]   # Optional error message for error responses


class PhotoListResponse(TypedDict):
    """Response structure for list_album_photos tool."""
    photos: List[PhotoInfo]
    count: int
    albumId: str
    userEmail: str
    error: NotRequired[Optional[str]]   # Optional error message for error responses