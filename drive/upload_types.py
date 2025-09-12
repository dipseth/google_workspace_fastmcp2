"""
Type definitions for Google Drive upload tool responses.

These TypedDict classes define the structure of data returned by Drive upload tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.
"""

from typing_extensions import TypedDict, List, Optional


class FileUploadInfo(TypedDict):
    """Structure for uploaded file information."""
    fileId: str
    fileName: str
    filePath: str
    fileSize: int
    mimeType: str
    folderId: str
    driveUrl: str
    webViewLink: str


class FolderUploadSummary(TypedDict):
    """Summary statistics for folder upload operation."""
    totalFiles: int
    successfulUploads: int
    failedUploads: int
    totalSize: int
    uploadDuration: float


class UploadFileResponse(TypedDict, total=False):
    """Response structure for upload_file_to_drive and upload_file_to_drive_unified tools."""
    success: bool
    userEmail: str
    fileInfo: Optional[FileUploadInfo]  # For single file upload
    filesUploaded: Optional[List[FileUploadInfo]]  # For folder upload
    folderSummary: Optional[FolderUploadSummary]  # For folder upload
    message: str
    error: Optional[str]
    warnings: Optional[List[str]]  # For partial failures in folder upload


class OAuthInstruction(TypedDict):
    """Structure for OAuth instruction step."""
    step: int
    instruction: str


class OAuthScope(TypedDict):
    """Structure for OAuth scope information."""
    service: str
    description: str


class StartAuthResponse(TypedDict, total=False):
    """Response structure for start_google_auth tool."""
    status: str  # "success" or "error"
    message: str
    authUrl: Optional[str]
    clickableLink: Optional[str]
    userEmail: str
    serviceName: Optional[str]
    instructions: Optional[List[str]]
    scopesIncluded: Optional[List[str]]
    note: Optional[str]
    error: Optional[str]


class CheckAuthResponse(TypedDict, total=False):
    """Response structure for check_drive_auth tool."""
    authenticated: bool
    userEmail: str
    message: str
    error: Optional[str]