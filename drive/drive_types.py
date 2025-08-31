"""
Type definitions for Google Drive tool responses.

These TypedDict classes define the structure of data returned by Drive tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional


class DriveItemInfo(TypedDict):
    """Structure for a single Drive item (file or folder) entry."""
    id: str
    name: str
    mimeType: str
    webViewLink: str
    iconLink: Optional[str]
    modifiedTime: str
    size: Optional[str]  # Size in bytes as string (may be None for folders)
    isFolder: bool  # True if mimeType is 'application/vnd.google-apps.folder'


class DriveItemsResponse(TypedDict):
    """Response structure for list_drive_items tool."""
    items: List[DriveItemInfo]
    count: int
    folderId: str
    folderName: Optional[str]  # Name of the folder being listed
    userEmail: str
    driveId: Optional[str]  # If listing from a shared drive
    error: Optional[str]  # Optional error message for error responses