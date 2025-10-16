"""
Google Drive file management tools for FastMCP2.

This module provides a unified file management tool that handles:
- Move files between folders (batch support)
- Copy/duplicate files (batch support)
- Rename files
- Delete/trash files (batch support)

All operations use the unified OAuth architecture with middleware injection.
"""

import logging
import asyncio
from typing_extensions import List, Optional, Annotated, Any, Union, Literal
from pathlib import Path
from pydantic import Field

from fastmcp import FastMCP
from googleapiclient.errors import HttpError

from auth.service_helpers import get_service
from auth.context import get_user_email_context
from .file_management_types import (
    MoveDriveFilesResponse,
    MoveFileResult,
    CopyDriveFilesResponse,
    CopyFileResult,
    RenameFileResponse,
    DeleteDriveFilesResponse,
    DeleteFileResult,
)
from tools.common_types import UserGoogleEmail, UserGoogleEmailDrive

from config.enhanced_logging import setup_logger

logger = setup_logger()


async def _get_drive_service_with_fallback(user_google_email: str) -> Any:
    """
    Get Drive service with fallback to direct creation if middleware injection fails.

    Args:
        user_google_email: User's Google email address

    Returns:
        Authenticated Drive service instance

    Raises:
        RuntimeError: If service creation fails
    """
    from auth.service_helpers import request_service, get_injected_service

    # First, try middleware injection
    service_key = request_service("drive")

    try:
        # Try to get the injected service from middleware
        drive_service = get_injected_service(service_key)
        logger.info(
            f"Successfully retrieved injected Drive service for {user_google_email}"
        )
        return drive_service

    except RuntimeError as e:
        if (
            "not yet fulfilled" in str(e).lower()
            or "service injection" in str(e).lower()
        ):
            # Middleware injection failed, fall back to direct service creation
            logger.warning(
                f"Middleware injection unavailable, falling back to direct service creation for {user_google_email}"
            )

            try:
                # Use the helper function that handles smart defaults
                drive_service = await get_service("drive", user_google_email)
                logger.info(
                    f"Successfully created Drive service directly for {user_google_email}"
                )
                return drive_service

            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(f"Direct service creation also failed: {direct_error}")

                # Check for specific credential errors
                if (
                    "credentials do not contain the necessary fields"
                    in error_str.lower()
                ):
                    raise RuntimeError(
                        f"❌ **Invalid or Corrupted Credentials**\n\n"
                        f"Your stored credentials for {user_google_email} are missing required OAuth fields.\n\n"
                        f"**To fix this:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Complete the authentication flow\n"
                        f"3. Try your Drive command again"
                    )
                elif "no valid credentials found" in error_str.lower():
                    raise RuntimeError(
                        f"❌ **No Credentials Found**\n\n"
                        f"No authentication credentials found for {user_google_email}.\n\n"
                        f"**To authenticate:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Follow the authentication flow\n"
                        f"3. Return here after seeing the success page"
                    )
                else:
                    raise RuntimeError(
                        f"Failed to get Drive service through both middleware and direct creation.\n"
                        f"Middleware error: {e}\n"
                        f"Direct creation error: {direct_error}\n\n"
                        f"Please run `start_google_auth` with your email ({user_google_email})"
                    )
        else:
            # Re-raise unexpected RuntimeErrors
            raise


def setup_file_management_tools(mcp: FastMCP) -> None:
    """
    Register unified Google Drive file management tool with the FastMCP server.

    This function registers a single tool that handles all file management operations:
    - move: Move files to different folders
    - copy: Duplicate files
    - rename: Rename a file
    - delete: Delete or trash files

    Args:
        mcp: FastMCP server instance to register tools with

    Returns:
        None: Tools are registered as side effects
    """

    @mcp.tool(
        name="manage_drive_files",
        description="Unified tool for Google Drive file management: move, copy, rename, or delete files",
        tags={"drive", "files", "management", "organize", "batch"},
        annotations={
            "title": "Manage Drive Files",
            "readOnlyHint": False,
            "destructiveHint": False,  # Set dynamically based on operation
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def manage_drive_files(
        operation: Annotated[
            Literal["move", "copy", "rename", "delete"],
            Field(
                description="Operation to perform: 'move', 'copy', 'rename', or 'delete'"
            ),
        ],
        file_ids: Annotated[
            Optional[List[str]],
            Field(
                description="List of file IDs (for move/copy/delete) or single file ID as list (for rename). Required for all operations."
            ),
        ] = None,
        user_google_email: UserGoogleEmail = None,
        # Move-specific parameters
        target_folder_id: Annotated[
            Optional[str],
            Field(
                description="[MOVE/COPY] Target folder ID (use 'root' for root folder). Required for move."
            ),
        ] = None,
        remove_from_all_parents: Annotated[
            bool,
            Field(
                description="[MOVE] If True, removes file from ALL current parent folders. If False, only removes from immediate parent"
            ),
        ] = True,
        # Copy-specific parameters
        name_prefix: Annotated[
            Optional[str],
            Field(
                description="[COPY] Prefix to add to copied file names (e.g., 'Copy of ')"
            ),
        ] = "Copy of ",
        # Rename-specific parameters
        new_name: Annotated[
            Optional[str],
            Field(description="[RENAME] New name for the file. Required for rename."),
        ] = None,
        # Delete-specific parameters
        permanent: Annotated[
            bool,
            Field(
                description="[DELETE] If True, permanently deletes files. If False, moves to trash (can be restored)"
            ),
        ] = False,
    ) -> Union[
        MoveDriveFilesResponse,
        CopyDriveFilesResponse,
        RenameFileResponse,
        DeleteDriveFilesResponse,
    ]:
        """
        Unified tool for Google Drive file management operations.

        **Operations:**
        - **move**: Move files to a different folder (batch support)
        - **copy**: Duplicate files (batch support)
        - **rename**: Rename a single file
        - **delete**: Delete or trash files (batch support)

        **Examples:**
        - Move files: operation="move", file_ids=["id1", "id2"], target_folder_id="folder_id"
        - Copy files: operation="copy", file_ids=["id1", "id2"], target_folder_id="folder_id", name_prefix="Copy of "
        - Rename file: operation="rename", file_ids=["id1"], new_name="new_name.txt"
        - Delete files: operation="delete", file_ids=["id1", "id2"], permanent=False

        Args:
            operation: Operation to perform ('move', 'copy', 'rename', 'delete')
            file_ids: List of file IDs to operate on (required for all operations)
            user_google_email: User's Google email address
            target_folder_id: Target folder for move/copy operations
            remove_from_all_parents: Remove from all parents during move (default: True)
            name_prefix: Prefix for copied file names (default: "Copy of ")
            new_name: New name for rename operation
            permanent: Permanently delete files (default: False - moves to trash)

        Returns:
            Operation-specific response with detailed results
        """
        logger.info(
            f"[manage_drive_files] Operation: '{operation}', Email: '{user_google_email}', Files: {len(file_ids) if file_ids else 0}"
        )

        # Validate required parameters for each operation
        if not file_ids:
            error_msg = "file_ids parameter is required for all operations"
            if operation == "move":
                return MoveDriveFilesResponse(
                    success=False,
                    totalFiles=0,
                    successfulMoves=0,
                    failedMoves=0,
                    targetFolderId=target_folder_id,
                    targetFolderName=None,
                    results=[],
                    userEmail=user_google_email,
                    message=error_msg,
                    error=error_msg,
                )
            elif operation == "copy":
                return CopyDriveFilesResponse(
                    success=False,
                    totalFiles=0,
                    successfulCopies=0,
                    failedCopies=0,
                    targetFolderId=target_folder_id,
                    results=[],
                    userEmail=user_google_email,
                    message=error_msg,
                    error=error_msg,
                )
            elif operation == "rename":
                return RenameFileResponse(
                    success=False,
                    fileId="",
                    oldName="",
                    newName="",
                    webViewLink="",
                    userEmail=user_google_email,
                    message=error_msg,
                    error=error_msg,
                )
            else:  # delete
                return DeleteDriveFilesResponse(
                    success=False,
                    totalFiles=0,
                    successfulDeletes=0,
                    failedDeletes=0,
                    permanent=permanent,
                    results=[],
                    userEmail=user_google_email,
                    message=error_msg,
                    error=error_msg,
                )

        if operation == "move" and not target_folder_id:
            return MoveDriveFilesResponse(
                success=False,
                totalFiles=len(file_ids),
                successfulMoves=0,
                failedMoves=len(file_ids),
                targetFolderId=None,
                targetFolderName=None,
                results=[],
                userEmail=user_google_email,
                message="target_folder_id is required for move operation",
                error="target_folder_id is required for move operation",
            )

        if operation == "rename":
            if len(file_ids) != 1:
                return RenameFileResponse(
                    success=False,
                    fileId=file_ids[0] if file_ids else "",
                    oldName="",
                    newName=new_name or "",
                    webViewLink="",
                    userEmail=user_google_email,
                    message="Rename operation requires exactly one file_id",
                    error="Rename operation requires exactly one file_id",
                )
            if not new_name:
                return RenameFileResponse(
                    success=False,
                    fileId=file_ids[0],
                    oldName="",
                    newName="",
                    webViewLink="",
                    userEmail=user_google_email,
                    message="new_name is required for rename operation",
                    error="new_name is required for rename operation",
                )

        # Route to appropriate operation handler
        try:
            drive_service = await _get_drive_service_with_fallback(user_google_email)

            if operation == "move":
                return await _handle_move_operation(
                    drive_service,
                    file_ids,
                    target_folder_id,
                    remove_from_all_parents,
                    user_google_email,
                )
            elif operation == "copy":
                return await _handle_copy_operation(
                    drive_service,
                    file_ids,
                    target_folder_id,
                    name_prefix,
                    user_google_email,
                )
            elif operation == "rename":
                return await _handle_rename_operation(
                    drive_service, file_ids[0], new_name, user_google_email
                )
            else:  # delete
                return await _handle_delete_operation(
                    drive_service, file_ids, permanent, user_google_email
                )

        except Exception as e:
            logger.error(f"Error in manage_drive_files: {e}")
            error_msg = str(e)

            # Return operation-specific error response
            if operation == "move":
                return MoveDriveFilesResponse(
                    success=False,
                    totalFiles=len(file_ids),
                    successfulMoves=0,
                    failedMoves=len(file_ids),
                    targetFolderId=target_folder_id,
                    targetFolderName=None,
                    results=[],
                    userEmail=user_google_email,
                    message=f"Error: {error_msg}",
                    error=error_msg,
                )
            elif operation == "copy":
                return CopyDriveFilesResponse(
                    success=False,
                    totalFiles=len(file_ids),
                    successfulCopies=0,
                    failedCopies=len(file_ids),
                    targetFolderId=target_folder_id,
                    results=[],
                    userEmail=user_google_email,
                    message=f"Error: {error_msg}",
                    error=error_msg,
                )
            elif operation == "rename":
                return RenameFileResponse(
                    success=False,
                    fileId=file_ids[0],
                    oldName="",
                    newName=new_name or "",
                    webViewLink="",
                    userEmail=user_google_email,
                    message=f"Error: {error_msg}",
                    error=error_msg,
                )
            else:  # delete
                return DeleteDriveFilesResponse(
                    success=False,
                    totalFiles=len(file_ids),
                    successfulDeletes=0,
                    failedDeletes=len(file_ids),
                    permanent=permanent,
                    results=[],
                    userEmail=user_google_email,
                    message=f"Error: {error_msg}",
                    error=error_msg,
                )


async def _handle_move_operation(
    drive_service: Any,
    file_ids: List[str],
    target_folder_id: str,
    remove_from_all_parents: bool,
    user_google_email: str,
) -> MoveDriveFilesResponse:
    """Handle move operation logic."""
    # Get target folder name for better reporting
    target_folder_name = "My Drive (Root)"
    if target_folder_id != "root":
        try:
            target_meta = await asyncio.to_thread(
                drive_service.files()
                .get(fileId=target_folder_id, fields="name", supportsAllDrives=True)
                .execute
            )
            target_folder_name = target_meta.get("name", "Unknown Folder")
        except Exception as e:
            logger.warning(f"Could not fetch target folder metadata: {e}")
            target_folder_name = f"Folder {target_folder_id}"

    move_results: List[MoveFileResult] = []
    successful_moves = 0
    failed_moves = 0

    for file_id in file_ids:
        # Get file metadata including current parents
        try:
            file_metadata = await asyncio.to_thread(
                drive_service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, parents, webViewLink",
                    supportsAllDrives=True,
                )
                .execute
            )
            file_name = file_metadata.get("name", "Unknown File")
            file_link = file_metadata.get("webViewLink", "#")
            current_parents = file_metadata.get("parents", [])
        except Exception as e:
            file_name = f"File ID: {file_id}"
            file_link = "#"
            current_parents = []
            logger.warning(f"Could not fetch metadata for file {file_id}: {e}")

        file_result = MoveFileResult(
            fileId=file_id,
            fileName=file_name,
            webViewLink=file_link,
            oldParents=current_parents,
            newParents=[],
            status="",
            error=None,
        )

        try:
            # Check if file is already in target folder
            if target_folder_id in current_parents:
                file_result["status"] = "already_in_folder"
                file_result["newParents"] = current_parents
                successful_moves += 1
                move_results.append(file_result)
                continue

            # Determine which parents to remove
            if remove_from_all_parents:
                parents_to_remove = (
                    ",".join(current_parents) if current_parents else None
                )
            else:
                # Only remove first parent (immediate parent)
                parents_to_remove = current_parents[0] if current_parents else None

            # Move the file by updating parents
            updated_file = await asyncio.to_thread(
                drive_service.files()
                .update(
                    fileId=file_id,
                    addParents=target_folder_id,
                    removeParents=parents_to_remove,
                    fields="id, parents",
                    supportsAllDrives=True,
                )
                .execute
            )

            file_result["status"] = "moved"
            file_result["newParents"] = updated_file.get("parents", [target_folder_id])
            successful_moves += 1

        except HttpError as e:
            error_msg = str(e)
            file_result["status"] = "failed"
            file_result["error"] = error_msg
            failed_moves += 1
        except Exception as e:
            file_result["status"] = "failed"
            file_result["error"] = str(e)
            failed_moves += 1

        move_results.append(file_result)

    return MoveDriveFilesResponse(
        success=failed_moves == 0,
        totalFiles=len(file_ids),
        successfulMoves=successful_moves,
        failedMoves=failed_moves,
        targetFolderId=target_folder_id,
        targetFolderName=target_folder_name,
        results=move_results,
        userEmail=user_google_email,
        message=f"Move operation completed. Files processed: {len(file_ids)}, Successfully moved: {successful_moves}, Failed: {failed_moves}",
        error=None,
    )


async def _handle_copy_operation(
    drive_service: Any,
    file_ids: List[str],
    target_folder_id: Optional[str],
    name_prefix: str,
    user_google_email: str,
) -> CopyDriveFilesResponse:
    """Handle copy operation logic."""
    copy_results: List[CopyFileResult] = []
    successful_copies = 0
    failed_copies = 0

    for file_id in file_ids:
        # Get original file metadata
        try:
            file_metadata = await asyncio.to_thread(
                drive_service.files()
                .get(fileId=file_id, fields="id, name, parents", supportsAllDrives=True)
                .execute
            )
            original_name = file_metadata.get("name", "Unknown File")
            original_parents = file_metadata.get("parents", [])
        except Exception as e:
            original_name = f"File ID: {file_id}"
            original_parents = []
            logger.warning(f"Could not fetch metadata for file {file_id}: {e}")

        file_result = CopyFileResult(
            originalFileId=file_id,
            originalFileName=original_name,
            copiedFileId=None,
            copiedFileName=None,
            webViewLink=None,
            status="",
            error=None,
        )

        try:
            # Prepare copy metadata
            copy_name = (
                f"{name_prefix}{original_name}" if name_prefix else original_name
            )
            copy_body = {"name": copy_name}

            # Set parents for the copy
            if target_folder_id:
                copy_body["parents"] = [target_folder_id]
            elif original_parents:
                # Keep in same folder as original
                copy_body["parents"] = original_parents

            # Perform the copy
            copied_file = await asyncio.to_thread(
                drive_service.files()
                .copy(
                    fileId=file_id,
                    body=copy_body,
                    fields="id, name, webViewLink",
                    supportsAllDrives=True,
                )
                .execute
            )

            file_result["status"] = "copied"
            file_result["copiedFileId"] = copied_file.get("id")
            file_result["copiedFileName"] = copied_file.get("name", copy_name)
            file_result["webViewLink"] = copied_file.get("webViewLink")
            successful_copies += 1

        except HttpError as e:
            error_msg = str(e)
            file_result["status"] = "failed"
            file_result["error"] = error_msg
            failed_copies += 1
        except Exception as e:
            file_result["status"] = "failed"
            file_result["error"] = str(e)
            failed_copies += 1

        copy_results.append(file_result)

    return CopyDriveFilesResponse(
        success=failed_copies == 0,
        totalFiles=len(file_ids),
        successfulCopies=successful_copies,
        failedCopies=failed_copies,
        targetFolderId=target_folder_id,
        results=copy_results,
        userEmail=user_google_email,
        message=f"Copy operation completed. Files processed: {len(file_ids)}, Successfully copied: {successful_copies}, Failed: {failed_copies}",
        error=None,
    )


async def _handle_rename_operation(
    drive_service: Any, file_id: str, new_name: str, user_google_email: str
) -> RenameFileResponse:
    """Handle rename operation logic."""
    # Get current file metadata
    try:
        file_metadata = await asyncio.to_thread(
            drive_service.files()
            .get(fileId=file_id, fields="id, name, webViewLink", supportsAllDrives=True)
            .execute
        )
        old_name = file_metadata.get("name", "Unknown File")
        file_link = file_metadata.get("webViewLink", "#")
    except Exception as e:
        return RenameFileResponse(
            success=False,
            fileId=file_id,
            oldName="Unknown",
            newName=new_name,
            webViewLink="#",
            userEmail=user_google_email,
            message=f"Failed to get file metadata: {e}",
            error=str(e),
        )

    # Perform the rename
    try:
        updated_file = await asyncio.to_thread(
            drive_service.files()
            .update(
                fileId=file_id,
                body={"name": new_name},
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            )
            .execute
        )

        return RenameFileResponse(
            success=True,
            fileId=file_id,
            oldName=old_name,
            newName=updated_file.get("name", new_name),
            webViewLink=updated_file.get("webViewLink", file_link),
            userEmail=user_google_email,
            message=f"Successfully renamed '{old_name}' to '{new_name}'",
            error=None,
        )
    except Exception as e:
        return RenameFileResponse(
            success=False,
            fileId=file_id,
            oldName=old_name,
            newName=new_name,
            webViewLink=file_link,
            userEmail=user_google_email,
            message=f"Failed to rename file: {e}",
            error=str(e),
        )


async def _handle_delete_operation(
    drive_service: Any, file_ids: List[str], permanent: bool, user_google_email: str
) -> DeleteDriveFilesResponse:
    """Handle delete operation logic."""
    delete_results: List[DeleteFileResult] = []
    successful_deletes = 0
    failed_deletes = 0

    for file_id in file_ids:
        # Get file metadata
        try:
            file_metadata = await asyncio.to_thread(
                drive_service.files()
                .get(fileId=file_id, fields="id, name, trashed", supportsAllDrives=True)
                .execute
            )
            file_name = file_metadata.get("name", "Unknown File")
            already_trashed = file_metadata.get("trashed", False)
        except Exception as e:
            file_name = f"File ID: {file_id}"
            already_trashed = False
            logger.warning(f"Could not fetch metadata for file {file_id}: {e}")

        file_result = DeleteFileResult(
            fileId=file_id, fileName=file_name, status="", error=None
        )

        try:
            if permanent:
                # Permanently delete the file
                await asyncio.to_thread(
                    drive_service.files()
                    .delete(fileId=file_id, supportsAllDrives=True)
                    .execute
                )
                file_result["status"] = "permanently_deleted"
                successful_deletes += 1
            else:
                # Move to trash
                if already_trashed:
                    file_result["status"] = "already_trashed"
                    successful_deletes += 1
                else:
                    await asyncio.to_thread(
                        drive_service.files()
                        .update(
                            fileId=file_id,
                            body={"trashed": True},
                            supportsAllDrives=True,
                        )
                        .execute
                    )
                    file_result["status"] = "trashed"
                    successful_deletes += 1

        except HttpError as e:
            error_msg = str(e)
            file_result["status"] = "failed"
            file_result["error"] = error_msg
            failed_deletes += 1
        except Exception as e:
            file_result["status"] = "failed"
            file_result["error"] = str(e)
            failed_deletes += 1

        delete_results.append(file_result)

    action = "permanently deleted" if permanent else "moved to trash"
    return DeleteDriveFilesResponse(
        success=failed_deletes == 0,
        totalFiles=len(file_ids),
        successfulDeletes=successful_deletes,
        failedDeletes=failed_deletes,
        permanent=permanent,
        results=delete_results,
        userEmail=user_google_email,
        message=f"Delete operation completed. Files processed: {len(file_ids)}, Successfully {action}: {successful_deletes}, Failed: {failed_deletes}",
        error=None,
    )
