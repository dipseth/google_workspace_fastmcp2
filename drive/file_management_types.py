"""
Type definitions for Google Drive file management tool responses.

These TypedDict classes define structured responses for file operations like
moving, copying, renaming, and deleting files.
"""

from typing_extensions import TypedDict, List, Optional, NotRequired


class MoveFileResult(TypedDict):
    """Structure for individual file move result."""
    fileId: str
    fileName: str
    webViewLink: str
    oldParents: List[str]
    newParents: List[str]
    status: str  # 'moved', 'failed', 'already_in_folder'
    error: NotRequired[Optional[str]]


class MoveDriveFilesResponse(TypedDict):
    """Response structure for move_drive_files tool."""
    success: bool
    totalFiles: int
    successfulMoves: int
    failedMoves: int
    targetFolderId: str
    targetFolderName: Optional[str]
    results: List[MoveFileResult]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class CopyFileResult(TypedDict):
    """Structure for individual file copy result."""
    originalFileId: str
    originalFileName: str
    copiedFileId: Optional[str]
    copiedFileName: Optional[str]
    webViewLink: Optional[str]
    status: str  # 'copied', 'failed'
    error: NotRequired[Optional[str]]


class CopyDriveFilesResponse(TypedDict):
    """Response structure for copy_drive_files tool."""
    success: bool
    totalFiles: int
    successfulCopies: int
    failedCopies: int
    targetFolderId: Optional[str]
    results: List[CopyFileResult]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class RenameFileResponse(TypedDict):
    """Response structure for rename_drive_file tool."""
    success: bool
    fileId: str
    oldName: str
    newName: str
    webViewLink: str
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]


class DeleteFileResult(TypedDict):
    """Structure for individual file delete result."""
    fileId: str
    fileName: str
    status: str  # 'trashed', 'permanently_deleted', 'failed', 'already_trashed'
    error: NotRequired[Optional[str]]


class DeleteDriveFilesResponse(TypedDict):
    """Response structure for delete_drive_files tool."""
    success: bool
    totalFiles: int
    successfulDeletes: int
    failedDeletes: int
    permanent: bool  # True if permanently deleted, False if moved to trash
    results: List[DeleteFileResult]
    userEmail: str
    message: str
    error: NotRequired[Optional[str]]