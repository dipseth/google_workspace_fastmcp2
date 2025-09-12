"""
Google Photos MCP Tools

This module provides MCP tools for interacting with Google Photos API using the universal service architecture.
Implements optimized patterns for Photos API including rate limiting, caching, and batch operations.
"""

import logging
import asyncio
from typing_extensions import List, Optional, Any, Dict, Union
from datetime import datetime, date

from fastmcp import FastMCP
from googleapiclient.errors import HttpError

from auth.service_helpers import request_service, get_injected_service, get_service
from tools.common_types import UserGoogleEmailPhotos
from .photos_types import AlbumListResponse, PhotoListResponse, AlbumInfo, PhotoInfo

# Configure module logger
logger = logging.getLogger(__name__)


async def _get_photos_service_with_fallback(user_google_email: str):
    """
    Get Photos service with fallback pattern.
    
    Args:
        user_google_email: User's Google email address
        
    Returns:
        Google Photos service instance
    """
    try:
        # Try to get service from middleware injection
        service_key = request_service("photos")
        service = get_injected_service(service_key)
        if service:
            logger.debug("Using middleware-injected Photos service")
            return service
    except Exception as e:
        logger.warning(f"Middleware service injection failed: {e}")
    
    # Fallback to direct service creation
    logger.info("Falling back to direct Photos service creation")
    from auth.service_manager import get_google_service
    from auth.compatibility_shim import CompatibilityShim
    
    # Get photos scopes - MUST include app-created data scopes for API to work
    try:
        shim = CompatibilityShim()
        scope_groups = shim.get_legacy_scope_groups()
        # Use both general and app-created data scopes for full access
        photos_scopes = [
            scope_groups.get("photoslibrary_read", "https://www.googleapis.com/auth/photoslibrary.readonly"),
            scope_groups.get("photoslibrary_full", "https://www.googleapis.com/auth/photoslibrary"),
            scope_groups.get("photoslibrary_append", "https://www.googleapis.com/auth/photoslibrary.appendonly"),
            # CRITICAL: App-created data scopes required for list/get operations
            scope_groups.get("photoslibrary_readonly_appcreated", "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata"),
            scope_groups.get("photoslibrary_edit_appcreated", "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata")
        ]
        logger.debug(f"Using Photos scopes from compatibility shim: {photos_scopes}")
    except Exception as e:
        logger.warning(f"Failed to get photos scopes from compatibility shim: {e}")
        # Fallback to hardcoded scopes - include app-created data scopes
        photos_scopes = [
            "https://www.googleapis.com/auth/photoslibrary.readonly",
            "https://www.googleapis.com/auth/photoslibrary",
            "https://www.googleapis.com/auth/photoslibrary.appendonly",
            # CRITICAL: App-created data scopes required for list/get operations
            "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
            "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata"
        ]
        logger.debug(f"Using fallback Photos scopes: {photos_scopes}")
    
    return await get_google_service(
        user_email=user_google_email,
        service_type="photos",
        version="v1",
        scopes=photos_scopes
    )


def _format_media_item(media_item: Dict) -> str:
    """Format a media item for display."""
    filename = media_item.get("filename", "Unknown")
    creation_time = media_item.get("mediaMetadata", {}).get("creationTime", "Unknown")
    width = media_item.get("mediaMetadata", {}).get("width", "Unknown")
    height = media_item.get("mediaMetadata", {}).get("height", "Unknown")
    mime_type = media_item.get("mimeType", "Unknown")
    
    return f"📷 \"{filename}\" | {width}x{height} | {mime_type} | Created: {creation_time}"


def _format_album(album: Dict) -> str:
    """Format an album for display."""
    title = album.get("title", "Untitled Album")
    media_count = album.get("mediaItemsCount", "Unknown")
    cover_photo_url = album.get("coverPhotoBaseUrl", "")
    
    return f"📁 \"{title}\" | Items: {media_count} | ID: {album.get('id', 'Unknown')}"


def setup_photos_tools(mcp: FastMCP) -> None:
    """
    Setup and register all Google Photos tools with the MCP server.
    
    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up Google Photos tools")
    
    @mcp.tool(
        name="list_photos_albums",
        description="List photo albums from Google Photos that the user has access to",
        tags={"photos", "albums", "list", "google"},
        annotations={
            "title": "List Google Photos Albums",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_photos_albums(
        user_google_email: UserGoogleEmailPhotos = None,
        max_results: int = 25,
        exclude_non_app_created: bool = False
    ) -> AlbumListResponse:
        """
        Lists photo albums from Google Photos that the user has access to.

        Args:
            user_google_email (str): The user's Google email address. Required.
            max_results (int): Maximum number of albums to return. Defaults to 25.
            exclude_non_app_created (bool): Exclude albums not created by the app. Defaults to False.

        Returns:
            AlbumListResponse: Structured list of photo albums with metadata.
        """
        logger.info(f"[list_photos_albums] Invoked. Email: '{user_google_email}'")

        try:
            photos_service = await _get_photos_service_with_fallback(user_google_email)

            # Use asyncio.to_thread for the blocking API call
            albums_request = photos_service.albums().list(
                pageSize=min(max_results, 50),  # Photos API max is 50
                excludeNonAppCreatedData=exclude_non_app_created
            )
            albums_response = await asyncio.to_thread(albums_request.execute)

            items = albums_response.get("albums", [])
            
            # Convert to structured format
            albums: List[AlbumInfo] = []
            for album in items:
                album_info: AlbumInfo = {
                    "id": album.get("id", ""),
                    "title": album.get("title", "Untitled Album"),
                    "productUrl": album.get("productUrl"),
                    "mediaItemsCount": album.get("mediaItemsCount"),
                    "coverPhotoBaseUrl": album.get("coverPhotoBaseUrl"),
                    "coverPhotoMediaItemId": album.get("coverPhotoMediaItemId")
                }
                albums.append(album_info)

            logger.info(f"Successfully listed {len(albums)} albums for {user_google_email}.")
            
            return AlbumListResponse(
                albums=albums,
                count=len(albums),
                excludeNonAppCreated=exclude_non_app_created,
                userEmail=user_google_email,
                error=None
            )
        
        except HttpError as e:
            error_msg = f"Failed to list photo albums: {e}"
            logger.error(error_msg)
            return AlbumListResponse(
                albums=[],
                count=0,
                excludeNonAppCreated=exclude_non_app_created,
                userEmail=user_google_email,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error listing photo albums: {str(e)}"
            logger.error(error_msg)
            return AlbumListResponse(
                albums=[],
                count=0,
                excludeNonAppCreated=exclude_non_app_created,
                userEmail=user_google_email,
                error=error_msg
            )

    @mcp.tool(
        name="search_photos",
        description="Search for photos in Google Photos using filters",
        tags={"photos", "search", "filter", "google"},
        annotations={
            "title": "Search Google Photos",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def search_photos(
        user_google_email: UserGoogleEmailPhotos = None,
        album_id: Optional[str] = None,
        content_categories: Optional[List[str]] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        max_results: int = 25
    ) -> str:
        """
        Search for photos in Google Photos using various filters.

        Args:
            user_google_email (str): The user's Google email address. Required.
            album_id (str, optional): ID of album to search within.
            content_categories (List[str], optional): Content categories to filter by (e.g., PEOPLE, ANIMALS, FOOD).
            date_start (str, optional): Start date in YYYY-MM-DD format.
            date_end (str, optional): End date in YYYY-MM-DD format.
            max_results (int): Maximum number of photos to return. Defaults to 25.

        Returns:
            str: A formatted list of matching photos.
        """
        logger.info(f"[search_photos] Invoked. Email: '{user_google_email}'")

        try:
            photos_service = await _get_photos_service_with_fallback(user_google_email)

            # Build filters
            filters = {}
            
            if content_categories:
                filters["contentFilter"] = {
                    "includedContentCategories": [cat.upper() for cat in content_categories]
                }
            
            if date_start or date_end:
                date_filter = {"ranges": [{}]}
                if date_start:
                    start_date = datetime.strptime(date_start, "%Y-%m-%d").date()
                    date_filter["ranges"][0]["startDate"] = {
                        "year": start_date.year,
                        "month": start_date.month,
                        "day": start_date.day
                    }
                if date_end:
                    end_date = datetime.strptime(date_end, "%Y-%m-%d").date()
                    date_filter["ranges"][0]["endDate"] = {
                        "year": end_date.year,
                        "month": end_date.month,
                        "day": end_date.day
                    }
                filters["dateFilter"] = date_filter

            # Build search request
            search_body = {
                "pageSize": min(max_results, 100),  # Photos API max is 100
            }
            
            if album_id:
                search_body["albumId"] = album_id
            
            if filters:
                search_body["filters"] = filters

            search_request = photos_service.mediaItems().search(body=search_body)
            search_response = await asyncio.to_thread(search_request.execute)

            media_items = search_response.get("mediaItems", [])
            if not media_items:
                return f"No photos found matching the criteria for {user_google_email}."

            media_list = [_format_media_item(item) for item in media_items]

            text_output = (
                f"Successfully found {len(media_items)} photos for {user_google_email}:\n"
                + "\n".join(media_list)
            )

            logger.info(f"Successfully found {len(media_items)} photos for {user_google_email}.")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Failed to search photos: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error searching photos: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool(
        name="list_album_photos",
        description="List all photos from a specific album",
        tags={"photos", "album", "list", "google"},
        annotations={
            "title": "List Album Photos",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_album_photos(
        user_google_email: str,
        album_id: str,
        max_results: int = 50
    ) -> PhotoListResponse:
        """
        Get all photos from a specific album.

        Args:
            user_google_email (str): The user's Google email address. Required.
            album_id (str): The ID of the album. Required.
            max_results (int): Maximum number of photos to return. Defaults to 50.

        Returns:
            PhotoListResponse: Structured list of photos with metadata.
        """
        logger.info(f"[list_album_photos] Invoked. Email: '{user_google_email}', Album: {album_id}")

        try:
            photos_service = await _get_photos_service_with_fallback(user_google_email)

            search_body = {
                "albumId": album_id,
                "pageSize": min(max_results, 100)
            }

            search_request = photos_service.mediaItems().search(body=search_body)
            search_response = await asyncio.to_thread(search_request.execute)

            items = search_response.get("mediaItems", [])
            
            # Convert to structured format
            photos: List[PhotoInfo] = []
            for item in items:
                metadata = item.get("mediaMetadata", {})
                photo_metadata = metadata.get("photo", {})
                
                photo_info: PhotoInfo = {
                    "id": item.get("id", ""),
                    "filename": item.get("filename", "Unknown"),
                    "mimeType": item.get("mimeType", "Unknown"),
                    "baseUrl": item.get("baseUrl", ""),
                    "productUrl": item.get("productUrl"),
                    "description": item.get("description"),
                    "creationTime": metadata.get("creationTime", "Unknown"),
                    "width": metadata.get("width"),
                    "height": metadata.get("height"),
                    "cameraMake": photo_metadata.get("cameraMake"),
                    "cameraModel": photo_metadata.get("cameraModel"),
                    "focalLength": photo_metadata.get("focalLength"),
                    "apertureFNumber": photo_metadata.get("apertureFNumber"),
                    "isoEquivalent": photo_metadata.get("isoEquivalent"),
                    "exposureTime": photo_metadata.get("exposureTime")
                }
                photos.append(photo_info)

            logger.info(f"Successfully retrieved {len(photos)} photos for {user_google_email}.")
            
            return PhotoListResponse(
                photos=photos,
                count=len(photos),
                albumId=album_id,
                userEmail=user_google_email,
                error=None
            )
        
        except HttpError as e:
            error_msg = f"Failed to get album photos: {e}"
            logger.error(error_msg)
            return PhotoListResponse(
                photos=[],
                count=0,
                albumId=album_id,
                userEmail=user_google_email,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error getting album photos: {str(e)}"
            logger.error(error_msg)
            return PhotoListResponse(
                photos=[],
                count=0,
                albumId=album_id,
                userEmail=user_google_email,
                error=error_msg
            )

    @mcp.tool(
        name="get_photo_details",
        description="Get detailed information about a specific photo",
        tags={"photos", "details", "metadata", "google"},
        annotations={
            "title": "Get Photo Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_photo_details(
        user_google_email: str,
        media_item_id: str
    ) -> str:
        """
        Get detailed information about a specific photo.

        Args:
            user_google_email (str): The user's Google email address. Required.
            media_item_id (str): The ID of the media item. Required.

        Returns:
            str: Detailed information about the photo including metadata.
        """
        logger.info(f"[get_photo_details] Invoked. Email: '{user_google_email}', Media ID: {media_item_id}")

        try:
            photos_service = await _get_photos_service_with_fallback(user_google_email)

            get_request = photos_service.mediaItems().get(mediaItemId=media_item_id)
            media_item = await asyncio.to_thread(get_request.execute)

            # Extract detailed metadata
            filename = media_item.get("filename", "Unknown")
            mime_type = media_item.get("mimeType", "Unknown")
            base_url = media_item.get("baseUrl", "")
            
            metadata = media_item.get("mediaMetadata", {})
            creation_time = metadata.get("creationTime", "Unknown")
            width = metadata.get("width", "Unknown")
            height = metadata.get("height", "Unknown")
            
            # Photo-specific metadata
            photo_metadata = metadata.get("photo", {})
            camera_make = photo_metadata.get("cameraMake", "Unknown")
            camera_model = photo_metadata.get("cameraModel", "Unknown")
            focal_length = photo_metadata.get("focalLength", "Unknown")
            aperture = photo_metadata.get("apertureFNumber", "Unknown")
            iso = photo_metadata.get("isoEquivalent", "Unknown")
            exposure_time = photo_metadata.get("exposureTime", "Unknown")

            text_output = (
                f"📷 **Photo Details for {media_item_id}**\n\n"
                f"**Basic Information:**\n"
                f"- Filename: {filename}\n"
                f"- Type: {mime_type}\n"
                f"- Dimensions: {width}x{height}\n"
                f"- Created: {creation_time}\n"
                f"- Base URL: {base_url[:50]}{'...' if len(base_url) > 50 else ''}\n\n"
                f"**Camera Information:**\n"
                f"- Make: {camera_make}\n"
                f"- Model: {camera_model}\n"
                f"- Focal Length: {focal_length}\n"
                f"- Aperture: f/{aperture}\n"
                f"- ISO: {iso}\n"
                f"- Exposure: {exposure_time}s"
            )

            logger.info(f"Successfully retrieved photo details for {user_google_email}.")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Failed to get photo details: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error getting photo details: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool(
        name="create_photos_album",
        description="Create a new album in Google Photos",
        tags={"photos", "album", "create", "google"},
        annotations={
            "title": "Create Photos Album",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_photos_album(
        user_google_email: str,
        title: str
    ) -> str:
        """
        Create a new album in Google Photos.

        Args:
            user_google_email (str): The user's Google email address. Required.
            title (str): The title of the new album. Required.

        Returns:
            str: Information about the newly created album including ID and URL.
        """
        logger.info(f"[create_photos_album] Invoked. Email: '{user_google_email}', Title: {title}")

        try:
            photos_service = await _get_photos_service_with_fallback(user_google_email)

            album_body = {
                "album": {
                    "title": title
                }
            }

            create_request = photos_service.albums().create(body=album_body)
            album = await asyncio.to_thread(create_request.execute)

            album_id = album.get("id")
            album_url = album.get("productUrl")

            text_output = (
                f"✅ Successfully created album '{title}' for {user_google_email}. "
                f"ID: {album_id} | URL: {album_url}"
            )

            logger.info(f"Successfully created album for {user_google_email}. ID: {album_id}")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Failed to create album: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error creating album: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool(
        name="get_photos_library_info",
        description="Get information about the user's Google Photos library",
        tags={"photos", "library", "info", "google"},
        annotations={
            "title": "Get Photos Library Info",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_photos_library_info(
        user_google_email: str
    ) -> str:
        """
        Get summary information about the user's Google Photos library.

        Args:
            user_google_email (str): The user's Google email address. Required.

        Returns:
            str: Summary of the Photos library including album and photo counts.
        """
        logger.info(f"[get_photos_library_info] Invoked. Email: '{user_google_email}'")

        try:
            photos_service = await _get_photos_service_with_fallback(user_google_email)

            # Get albums count
            albums_request = photos_service.albums().list(pageSize=50)
            albums_response = await asyncio.to_thread(albums_request.execute)
            albums = albums_response.get("albums", [])
            album_count = len(albums)

            # Get recent photos to estimate library size
            search_body = {"pageSize": 100}
            search_request = photos_service.mediaItems().search(body=search_body)
            search_response = await asyncio.to_thread(search_request.execute)
            recent_photos = search_response.get("mediaItems", [])
            
            text_output = (
                f"📚 **Google Photos Library Summary for {user_google_email}**\n\n"
                f"**Library Statistics:**\n"
                f"- Albums: {album_count}\n"
                f"- Recent photos accessed: {len(recent_photos)}\n"
                f"- Total library size: Use search filters for accurate counts\n\n"
                f"**Recent Albums:**\n"
            )

            # Show recent albums
            for album in albums[:5]:
                text_output += f"- {_format_album(album)}\n"
            
            if album_count > 5:
                text_output += f"... and {album_count - 5} more albums\n"

            logger.info(f"Successfully retrieved library info for {user_google_email}.")
            return text_output
        
        except HttpError as e:
            error_msg = f"❌ Failed to get library info: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error getting library info: {str(e)}"
            logger.error(error_msg)
            return error_msg

    logger.info("✅ Google Photos tools setup complete")