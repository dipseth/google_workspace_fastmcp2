"""
Type definitions for Google Drive upload tool responses.

These classes define the structure of data returned by Drive upload and auth tools,
enabling FastMCP to automatically generate JSON schemas for better MCP client integration.

Note: Auth response types (StartAuthResponse, CheckAuthResponse) use Pydantic BaseModel
for rich field descriptions in JSON schemas. Other types use TypedDict for simplicity.
"""

from pydantic import BaseModel, Field
from typing_extensions import List, Optional, TypedDict


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

    service: List[str]  # Changed from str to List[str] to match actual usage
    description: str


class StartAuthResponse(BaseModel):
    """Response structure for start_google_auth tool."""

    status: str = Field(
        ...,
        description="Authentication status: 'success' if auth URL generated, 'error' if failed",
    )
    message: str = Field(
        ..., description="Human-readable message describing the authentication status"
    )
    authUrl: Optional[str] = Field(
        None, description="OAuth2 authorization URL to open in browser for user consent"
    )
    clickableLink: Optional[str] = Field(
        None, description="Formatted clickable link for terminal/UI display"
    )
    userEmail: str = Field(..., description="Google email address being authenticated")
    sessionId: Optional[str] = Field(
        None,
        description="Session UUID for this connection. Save this to reconnect with same tool state using ?uuid= parameter",
    )
    serviceName: Optional[List[str]] = Field(
        None,
        description="List of Google services being authorized (e.g., ['drive', 'gmail', 'calendar'])",
    )
    instructions: Optional[List[str]] = Field(
        None, description="Step-by-step instructions for completing the OAuth flow"
    )
    scopesIncluded: Optional[List[str]] = Field(
        None,
        description="List of OAuth scopes being requested for the selected services",
    )
    note: Optional[str] = Field(
        None, description="Additional notes or warnings about the authentication"
    )
    error: Optional[str] = Field(
        None, description="Error message if authentication failed"
    )


class CheckAuthResponse(BaseModel):
    """Response structure for check_drive_auth tool."""

    authenticated: bool = Field(
        ...,
        description="Whether the user is currently authenticated with valid credentials",
    )
    userEmail: str = Field(
        ..., description="Google email address that was checked for authentication"
    )
    message: str = Field(
        ..., description="Human-readable message describing the authentication status"
    )
    sessionId: Optional[str] = Field(
        None,
        description="Session UUID for this connection. Save this to reconnect with same tool state using ?uuid= parameter",
    )
    error: Optional[str] = Field(
        None, description="Error message if authentication check failed"
    )
