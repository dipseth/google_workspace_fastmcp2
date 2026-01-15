"""
Type definitions for Google Drive tool responses.

These TypedDict classes define the structure of data returned by Drive tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import List, NotRequired, Optional, TypedDict


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


class CreateDriveFileResponse(TypedDict):
    """Response structure for create_drive_file tool."""

    success: bool
    fileId: Optional[str]
    fileName: Optional[str]
    mimeType: str
    folderId: str
    webViewLink: Optional[str]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class ShareFileResult(TypedDict):
    """Structure for individual file sharing result."""

    fileId: str
    fileName: str
    webViewLink: str
    recipientsProcessed: List[str]
    recipientsFailed: List[str]
    recipientsAlreadyHadAccess: List[str]


class ShareDriveFilesResponse(TypedDict):
    """Response structure for share_drive_files tool."""

    success: bool
    totalFiles: int
    totalRecipients: int
    totalOperations: int
    successfulOperations: int
    failedOperations: int
    role: str
    sendNotification: bool
    results: List[ShareFileResult]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class PublicFileResult(TypedDict):
    """Structure for individual file public sharing result."""

    fileId: str
    fileName: str
    webViewLink: str
    status: str  # 'made_public', 'removed_public', 'already_public', 'was_not_public', 'failed'
    error: NotRequired[Optional[str]]


class MakeDriveFilesPublicResponse(TypedDict):
    """Response structure for make_drive_files_public tool."""

    success: bool
    totalFiles: int
    successfulOperations: int
    failedOperations: int
    public: bool  # True if making public, False if removing public access
    role: Optional[str]  # Role used for public access (reader, commenter)
    results: List[PublicFileResult]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]
