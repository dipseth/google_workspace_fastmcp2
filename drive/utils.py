"""Google Drive utility functions for file operations."""

import logging
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional
import asyncio
from io import BytesIO

from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class DriveUploadError(Exception):
    """Custom exception for Drive upload errors."""
    pass


def get_mime_type(file_path: Path) -> str:
    """
    Get MIME type for a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        MIME type string
    """
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or 'application/octet-stream'


def validate_file_path(file_path: Path) -> None:
    """
    Validate that a file path exists and is accessible.
    
    Args:
        file_path: Path to validate
        
    Raises:
        DriveUploadError: If file is invalid
    """
    if not file_path.exists():
        raise DriveUploadError(f"File not found: {file_path}")
    
    if not file_path.is_file():
        raise DriveUploadError(f"Path is not a file: {file_path}")
    
    if not file_path.stat().st_size:
        raise DriveUploadError(f"File is empty: {file_path}")
    
    try:
        # Test read access
        with open(file_path, 'rb') as f:
            f.read(1)
    except PermissionError:
        raise DriveUploadError(f"Permission denied reading file: {file_path}")
    except Exception as e:
        raise DriveUploadError(f"Error accessing file {file_path}: {e}")


async def upload_file_to_drive_api(
    service,
    file_path: Path,
    folder_id: str = "root",
    custom_filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upload a file to Google Drive.
    
    Args:
        service: Authenticated Google Drive service
        file_path: Path to the file to upload
        folder_id: Google Drive folder ID (default: root)
        custom_filename: Optional custom filename
        
    Returns:
        Dictionary with file metadata from Drive API
        
    Raises:
        DriveUploadError: If upload fails
    """
    logger.info(f"Starting upload: {file_path} -> folder {folder_id}")
    
    # Validate file
    validate_file_path(file_path)
    
    # Prepare file metadata
    filename = custom_filename or file_path.name
    mime_type = get_mime_type(file_path)
    
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    
    logger.debug(f"File metadata: {file_metadata}, MIME type: {mime_type}")
    
    try:
        # Create media upload object
        media = MediaFileUpload(
            str(file_path),
            mimetype=mime_type,
            resumable=True
        )
        
        # Execute upload in thread pool to avoid blocking
        def _execute_upload():
            return service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink,mimeType,size,createdTime'
            ).execute()
        
        result = await asyncio.to_thread(_execute_upload)
        
        logger.info(f"Upload successful: {result['name']} (ID: {result['id']})")
        return result
        
    except HttpError as e:
        error_msg = f"Google Drive API error: {e.status_code} - {e.error_details}"
        logger.error(error_msg)
        raise DriveUploadError(error_msg)
    except Exception as e:
        error_msg = f"Upload failed: {e}"
        logger.error(error_msg)
        raise DriveUploadError(error_msg)


async def upload_content_to_drive_api(
    service,
    content: bytes,
    filename: str,
    folder_id: str = "root",
    mime_type: str = "application/octet-stream"
) -> Dict[str, Any]:
    """
    Upload content directly to Google Drive.
    
    Args:
        service: Authenticated Google Drive service
        content: File content as bytes
        filename: Name for the file
        folder_id: Google Drive folder ID (default: root)
        mime_type: MIME type of the content
        
    Returns:
        Dictionary with file metadata from Drive API
        
    Raises:
        DriveUploadError: If upload fails
    """
    logger.info(f"Starting content upload: {filename} -> folder {folder_id}")
    
    if not content:
        raise DriveUploadError("Content cannot be empty")
    
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    
    try:
        # Create media upload from content
        media = MediaIoBaseUpload(
            BytesIO(content),
            mimetype=mime_type,
            resumable=True
        )
        
        # Execute upload in thread pool
        def _execute_upload():
            return service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink,mimeType,size,createdTime'
            ).execute()
        
        result = await asyncio.to_thread(_execute_upload)
        
        logger.info(f"Content upload successful: {result['name']} (ID: {result['id']})")
        return result
        
    except HttpError as e:
        error_msg = f"Google Drive API error: {e.status_code} - {e.error_details}"
        logger.error(error_msg)
        raise DriveUploadError(error_msg)
    except Exception as e:
        error_msg = f"Content upload failed: {e}"
        logger.error(error_msg)
        raise DriveUploadError(error_msg)


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"


def format_upload_result(result: Dict[str, Any], file_path: Optional[Path] = None) -> str:
    """
    Format upload result for user-friendly display.
    
    Args:
        result: Drive API response
        file_path: Original file path (optional)
        
    Returns:
        Formatted result string
    """
    file_size = ""
    if 'size' in result:
        file_size = f" ({format_file_size(int(result['size']))})"
    
    original_path = ""
    if file_path:
        original_path = f"\n📁 Original: {file_path}"
    
    return (
        f"✅ Successfully uploaded to Google Drive\n"
        f"📄 Name: {result['name']}{file_size}\n"
        f"🆔 File ID: {result['id']}\n"
        f"🔗 Link: {result['webViewLink']}"
        f"{original_path}"
    )