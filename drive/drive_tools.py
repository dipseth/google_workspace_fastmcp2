"""
Google Drive comprehensive tools for FastMCP2.

This module provides complete Google Drive integration tools including search,
content retrieval, listing, and file creation capabilities using the new
middleware-based service injection pattern.

Key Features:
- Search files and folders with advanced query support
- Retrieve file content with multiple format support
- List directory contents with shared drive support
- Create files from content or URLs
- Comprehensive error handling with fallback patterns

Dependencies:
- google-api-python-client: Google Drive API integration
- fastmcp: FastMCP server framework
- auth.service_helpers: Service injection utilities
"""

import asyncio
import io
import re

import httpx
from fastmcp import FastMCP
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from pydantic import Field
from typing_extensions import Annotated, Any, Dict, List, Optional

from auth.service_helpers import get_injected_service, get_service, request_service
from config.enhanced_logging import setup_logger
from tools.common_types import UserGoogleEmail, UserGoogleEmailDrive

from .drive_enums import MimeTypeFilter
from .drive_search_types import DriveFileInfo, DriveSearchResponse
from .drive_types import (
    CreateDriveFileResponse,
    DriveItemInfo,
    DriveItemsResponse,
    MakeDriveFilesPublicResponse,
    PublicFileResult,
    ShareDriveFilesResponse,
    ShareFileResult,
)

logger = setup_logger()

# Precompiled regex patterns for Drive query detection
DRIVE_QUERY_PATTERNS = [
    re.compile(r'\b\w+\s*(=|!=|>|<)\s*[\'"].*?[\'"]', re.IGNORECASE),  # field = 'value'
    re.compile(r"\b\w+\s*(=|!=|>|<)\s*\d+", re.IGNORECASE),  # field = number
    re.compile(r"\bcontains\b", re.IGNORECASE),  # contains operator
    re.compile(r"\bin\s+parents\b", re.IGNORECASE),  # in parents
    re.compile(r"\bhas\s*\{", re.IGNORECASE),  # has {properties}
    re.compile(r"\btrashed\s*=\s*(true|false)\b", re.IGNORECASE),  # trashed=true/false
    re.compile(r"\bstarred\s*=\s*(true|false)\b", re.IGNORECASE),  # starred=true/false
    re.compile(
        r'[\'"][^\'"]+[\'"]\s+in\s+parents', re.IGNORECASE
    ),  # 'parentId' in parents
    re.compile(r"\bfullText\s+contains\b", re.IGNORECASE),  # fullText contains
    re.compile(r"\bname\s*(=|contains)\b", re.IGNORECASE),  # name = or name contains
    re.compile(r"\bmimeType\s*(=|!=)\b", re.IGNORECASE),  # mimeType operators
]


def _extract_office_xml_text(file_bytes: bytes, mime_type: str) -> Optional[str]:
    """
    Extract plain text from Office XML files (Word, Excel, PowerPoint).

    Args:
        file_bytes: Raw file content
        mime_type: MIME type of the file

    Returns:
        Extracted text or None if extraction fails
    """
    import xml.etree.ElementTree as ET
    import zipfile

    shared_strings: List[str] = []
    ns_excel_main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            targets: List[str] = []

            # Map MIME type to XML files to inspect
            if (
                mime_type
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ):
                targets = ["word/document.xml"]
            elif (
                mime_type
                == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ):
                targets = [n for n in zf.namelist() if n.startswith("ppt/slides/slide")]
            elif (
                mime_type
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ):
                targets = [
                    n
                    for n in zf.namelist()
                    if n.startswith("xl/worksheets/sheet") and "drawing" not in n
                ]

                # Parse sharedStrings.xml for Excel files
                try:
                    shared_strings_xml = zf.read("xl/sharedStrings.xml")
                    shared_strings_root = ET.fromstring(shared_strings_xml)
                    for si_element in shared_strings_root.findall(
                        f"{{{ns_excel_main}}}si"
                    ):
                        text_parts = []
                        for t_element in si_element.findall(f".//{{{ns_excel_main}}}t"):
                            if t_element.text:
                                text_parts.append(t_element.text)
                        shared_strings.append("".join(text_parts))
                except KeyError:
                    logger.info("No sharedStrings.xml found in Excel file (optional)")
                except ET.ParseError as e:
                    logger.error(f"Error parsing sharedStrings.xml: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error processing sharedStrings.xml: {e}")
            else:
                return None

            pieces: List[str] = []
            for member in targets:
                try:
                    xml_content = zf.read(member)
                    xml_root = ET.fromstring(xml_content)
                    member_texts: List[str] = []

                    if (
                        mime_type
                        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ):
                        for cell_element in xml_root.findall(
                            f".//{{{ns_excel_main}}}c"
                        ):
                            value_element = cell_element.find(f"{{{ns_excel_main}}}v")

                            if value_element is None or value_element.text is None:
                                continue

                            cell_type = cell_element.get("t")
                            if cell_type == "s":  # Shared string
                                try:
                                    ss_idx = int(value_element.text)
                                    if 0 <= ss_idx < len(shared_strings):
                                        member_texts.append(shared_strings[ss_idx])
                                except ValueError:
                                    logger.warning(
                                        f"Non-integer shared string index: '{value_element.text}'"
                                    )
                            else:  # Direct value
                                member_texts.append(value_element.text)
                    else:  # Word or PowerPoint
                        for elem in xml_root.iter():
                            if elem.tag.endswith("}t") and elem.text:
                                cleaned_text = elem.text.strip()
                                if cleaned_text:
                                    member_texts.append(cleaned_text)

                    if member_texts:
                        pieces.append(" ".join(member_texts))

                except ET.ParseError as e:
                    logger.warning(f"Could not parse XML in member '{member}': {e}")
                except Exception as e:
                    logger.error(f"Error processing member '{member}': {e}")

            if not pieces:
                return None

            text = "\n\n".join(pieces).strip()
            return text or None

    except zipfile.BadZipFile:
        logger.warning(f"File is not a valid ZIP archive (mime_type: {mime_type})")
        return None
    except Exception as e:
        logger.error(f"Failed to extract office XML text: {e}")
        return None


def _build_drive_list_params(
    query: str,
    page_size: int,
    drive_id: Optional[str] = None,
    include_items_from_all_drives: bool = True,
    corpora: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build common list parameters for Drive API calls.

    Args:
        query: Search query string
        page_size: Maximum number of items to return
        drive_id: Optional shared drive ID
        include_items_from_all_drives: Whether to include items from all drives
        corpora: Optional corpus specification

    Returns:
        Dictionary of parameters for Drive API list calls
    """
    list_params = {
        "q": query,
        "pageSize": page_size,
        "fields": "nextPageToken, files(id, name, mimeType, webViewLink, iconLink, modifiedTime, size)",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": include_items_from_all_drives,
    }

    if drive_id:
        list_params["driveId"] = drive_id
        if corpora:
            list_params["corpora"] = corpora
        else:
            list_params["corpora"] = "drive"
    elif corpora:
        list_params["corpora"] = corpora

    return list_params


async def _get_drive_service_with_fallback(user_google_email: str) -> Any:
    """
    Get Drive service with fallback to direct creation if middleware injection fails.

    Args:
        user_google_email: User's Google email address

    Returns:
        Authenticated Drive service instance

    Raises:
        RuntimeError: If both middleware injection and direct creation fail
    """
    # First, try middleware injection
    service_key = await request_service("drive")

    try:
        # Try to get the injected service from middleware
        drive_service = await get_injected_service(service_key)
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


# Define search_drive_files at module level so it can be imported
async def search_drive_files(
    query: Annotated[
        str,
        Field(
            description="Search query - can be free text (e.g. 'quarterly report') or Google Drive query syntax (e.g. 'name contains \"budget\"'). Leave empty to search all files when using mime_type filter."
        ),
    ] = "",
    mime_type: Annotated[
        Optional[MimeTypeFilter],
        Field(
            description="Filter by file type (e.g., PDF, GOOGLE_DOCS, EXCEL, ALL_SPREADSHEETS). This provides an easy way to filter without writing MIME type queries."
        ),
    ] = None,
    page_size: Annotated[
        int,
        Field(description="Maximum number of results to return (1-100)", ge=1, le=100),
    ] = 10,
    drive_id: Annotated[
        Optional[str],
        Field(description="Optional ID of a specific shared drive to search within"),
    ] = None,
    include_items_from_all_drives: Annotated[
        bool,
        Field(
            description="Include items from all shared drives the user has access to"
        ),
    ] = True,
    corpora: Annotated[
        Optional[str],
        Field(
            description="Bodies of items to query: 'user' (personal drive), 'domain' (domain shared), 'drive' (specific drive), 'allDrives' (all accessible drives)"
        ),
    ] = None,
    user_google_email: UserGoogleEmailDrive = None,
) -> DriveSearchResponse:
    """
    Search for files in Google Drive with easy file type filtering.

    ## Usage Examples:

    **Simple file type search:**
    - `mime_type=MimeTypeFilter.PDF` - Find all PDFs
    - `mime_type=MimeTypeFilter.GOOGLE_DOCS` - Find all Google Docs
    - `mime_type=MimeTypeFilter.ALL_SPREADSHEETS` - Find all spreadsheets (Sheets + Excel)

    **Combined with text search:**
    - `mime_type=MimeTypeFilter.PDF, query="quarterly report"` - PDFs containing "quarterly report"
    - `mime_type=MimeTypeFilter.GOOGLE_DOCS, query="meeting"` - Google Docs about meetings

    **Advanced query syntax (in query parameter):**
    - `query="name contains 'report' and modifiedTime > '2024-01-01'"` - Complex filtering
    - `query="'folderID' in parents"` - Files in specific folder
    - `query="sharedWithMe = true"` - Files shared with you

    The function automatically detects whether you're using simple text search or
    Google Drive Query Language based on the query structure.

    Args:
        user_google_email: User's Google email address for authentication
        query: Search query - either free text or Google Drive query syntax
        page_size: Max results to return (1-100, default: 10)
        drive_id: Optional shared drive ID to search within
        include_items_from_all_drives: Include shared drive items (default: True)
        corpora: Search scope - 'user', 'domain', 'drive', or 'allDrives'

    Returns:
        DriveSearchResponse: Structured response containing:
            - query: Original query string
            - queryType: "structured" or "free-text"
            - processedQuery: Actual query sent to API
            - results: List of matching files with metadata
            - resultCount: Number of results returned
            - nextPageToken: Token for pagination (if more results)
            - searchScope: Scope of the search
            - error: Error message if search failed

    Raises:
        HttpError: If Drive API returns an error
        RuntimeError: If authentication fails or service unavailable
    """
    logger.debug(
        f"[search_drive_files] Email: '{user_google_email}', Query: '{query}', MimeType: '{mime_type}'"
    )

    try:
        # Get Drive service with fallback support
        drive_service = await _get_drive_service_with_fallback(user_google_email)

        # Build query parts
        query_parts = []

        # Add MIME type filter if provided
        if mime_type:
            mime_filter = mime_type.to_query_filter()
            if mime_filter:
                query_parts.append(mime_filter)

        # Handle user query
        if query:
            # Check if query is structured or free text
            is_structured_query = any(
                pattern.search(query) for pattern in DRIVE_QUERY_PATTERNS
            )

            if is_structured_query:
                query_parts.append(f"({query})")
                query_type = "structured"
            else:
                # For free text queries, wrap in fullText contains
                escaped_query = query.replace("'", "\\'")
                query_parts.append(f"fullText contains '{escaped_query}'")
                query_type = "free-text"
        else:
            query_type = "mime-filter" if mime_type else "all"

        # Always exclude trashed files unless explicitly included in query
        if not any("trashed" in part for part in query_parts):
            query_parts.append("trashed = false")

        # Combine query parts
        final_query = " and ".join(query_parts) if query_parts else "trashed = false"

        logger.info(f"[search_drive_files] Final query: '{final_query}'")

        # Build parameters and execute query (for both structured and free-text)
        list_params = _build_drive_list_params(
            query=final_query,
            page_size=page_size,
            drive_id=drive_id,
            include_items_from_all_drives=include_items_from_all_drives,
            corpora=corpora,
        )

        results = await asyncio.to_thread(
            drive_service.files().list(**list_params).execute
        )
        files = results.get("files", [])

        # Convert to structured file info
        structured_results: List[DriveFileInfo] = []
        for item in files:
            file_info: DriveFileInfo = {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "mimeType": item.get("mimeType", ""),
                "size": item.get("size"),
                "webViewLink": item.get("webViewLink"),
                "iconLink": item.get("iconLink"),
                "createdTime": item.get("createdTime"),
                "modifiedTime": item.get("modifiedTime"),
                "parents": item.get("parents"),
                "owners": item.get("owners"),
                "shared": item.get("shared"),
                "starred": item.get("starred"),
                "trashed": item.get("trashed", False),
                "isFolder": item.get("mimeType")
                == "application/vnd.google-apps.folder",
            }
            structured_results.append(file_info)

        # Determine search scope
        if corpora:
            search_scope = corpora
        elif drive_id:
            search_scope = "drive"
        elif include_items_from_all_drives:
            search_scope = "allDrives"
        else:
            search_scope = "user"

        return DriveSearchResponse(
            query=query,
            queryType=query_type,
            processedQuery=final_query,
            results=structured_results,
            resultCount=len(structured_results),
            totalResults=None,  # Unknown unless we get total from API
            nextPageToken=results.get("nextPageToken"),
            userEmail=user_google_email,
            driveId=drive_id,
            corpora=corpora,
            searchScope=search_scope,
            error=None,
        )

    except HttpError as e:
        logger.error(f"Drive API error in search_drive_files: {e}")
        error_msg = str(e)

        # Provide helpful suggestions based on error
        suggestions = []
        if "invalid" in error_msg.lower() and "query" in error_msg.lower():
            suggestions = [
                "Check query syntax - use single quotes for string values",
                "Verify field names (e.g., 'mimeType' not 'mimetype')",
                "Ensure operators are valid (=, !=, contains, <, >)",
            ]
        elif "401" in error_msg or "403" in error_msg:
            suggestions = [
                "Re-authenticate using start_google_auth",
                "Check if you have access to the requested drive/files",
            ]

        return DriveSearchResponse(
            query=query,
            queryType=(
                "structured"
                if any(pattern.search(query) for pattern in DRIVE_QUERY_PATTERNS)
                else "free-text"
            ),
            processedQuery=query,
            results=[],
            resultCount=0,
            totalResults=None,
            nextPageToken=None,
            userEmail=user_google_email,
            driveId=drive_id,
            corpora=corpora,
            searchScope=corpora or "user",
            error=f"Drive API error: {error_msg}",
        )

    except Exception as e:
        logger.error(f"Unexpected error in search_drive_files: {e}")
        return DriveSearchResponse(
            query=query,
            queryType=(
                "structured"
                if any(pattern.search(query) for pattern in DRIVE_QUERY_PATTERNS)
                else "free-text"
            ),
            processedQuery=query,
            results=[],
            resultCount=0,
            totalResults=None,
            nextPageToken=None,
            userEmail=user_google_email,
            driveId=drive_id,
            corpora=corpora,
            searchScope=corpora or "user",
            error=f"Unexpected error: {str(e)}",
        )


def setup_drive_comprehensive_tools(mcp: FastMCP) -> None:
    """
    Register comprehensive Google Drive tools with the FastMCP server.

    This function registers the Drive tools:
    1. search_drive_files: Advanced file/folder search
    2. get_drive_file_content: File content retrieval
    3. list_drive_items: Directory listing
    4. create_drive_file: File creation
    5. share_drive_files: Share files with specific people
    6. make_drive_files_public: Make files publicly accessible

    Args:
        mcp: FastMCP server instance to register tools with

    Returns:
        None: Tools are registered as side effects
    """

    # Register the search_drive_files tool (module-level function)
    mcp.tool(
        name="search_drive_files",
        description="Search Google Drive files with easy file type filtering. Use mime_type parameter for simple filtering (PDF, GOOGLE_DOCS, EXCEL, etc.) or query parameter for advanced Google Drive Query Language searches.",
        tags={
            "drive",
            "search",
            "files",
            "folders",
            "query",
            "structured",
            "mime",
            "gdrive",
        },
        annotations={
            "title": "Search Google Drive",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )(search_drive_files)

    @mcp.tool(
        name="get_drive_file_content",
        description="Retrieve the content of a Google Drive file by ID, supporting multiple formats",
        tags={"drive", "file", "content", "download", "read"},
        annotations={
            "title": "Get Drive File Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_drive_file_content(
        file_id: str, user_google_email: UserGoogleEmail = None
    ) -> str:
        """
        Retrieve the content of a specific Google Drive file by ID.

        Supports:
        • Native Google Docs, Sheets, Slides → exported as text/CSV
        • Office files (.docx, .xlsx, .pptx) → extracted text
        • Any other file → UTF-8 decode or binary notation

        Args:
            user_google_email: User's Google email address
            file_id: Google Drive file ID

        Returns:
            str: File content as plain text with metadata header
        """
        logger.info(f"[get_drive_file_content] File ID: '{file_id}'")

        try:
            drive_service = await _get_drive_service_with_fallback(user_google_email)

            # Get file metadata
            file_metadata = await asyncio.to_thread(
                drive_service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, mimeType, webViewLink",
                    supportsAllDrives=True,
                )
                .execute
            )

            mime_type = file_metadata.get("mimeType", "")
            file_name = file_metadata.get("name", "Unknown File")

            # Determine export format for Google native files
            export_mime_type = {
                "application/vnd.google-apps.document": "text/plain",
                "application/vnd.google-apps.spreadsheet": "text/csv",
                "application/vnd.google-apps.presentation": "text/plain",
            }.get(mime_type)

            # Create request for file content
            request_obj = (
                drive_service.files().export_media(
                    fileId=file_id, mimeType=export_mime_type
                )
                if export_mime_type
                else drive_service.files().get_media(fileId=file_id)
            )

            # Download file content
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request_obj)
            done = False
            while not done:
                status, done = await asyncio.to_thread(downloader.next_chunk)

            file_content_bytes = fh.getvalue()

            # Extract text based on file type
            office_mime_types = {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }

            if mime_type in office_mime_types:
                # Try to extract text from Office files
                body_text = _extract_office_xml_text(file_content_bytes, mime_type)
                if not body_text:
                    # Fallback to UTF-8 decode
                    try:
                        body_text = file_content_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        body_text = f"[Binary or unsupported text encoding - {len(file_content_bytes)} bytes]"
            else:
                # For non-Office files, try UTF-8 decode
                try:
                    body_text = file_content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    body_text = f"[Binary or unsupported text encoding - {len(file_content_bytes)} bytes]"

            # Format response
            header = (
                f'File: "{file_name}" (ID: {file_id}, Type: {mime_type})\n'
                f"Link: {file_metadata.get('webViewLink', '#')}\n\n--- CONTENT ---\n"
            )
            return header + body_text

        except HttpError as e:
            logger.error(f"Drive API error in get_drive_file_content: {e}")
            return f"❌ Drive API error: {e}"

        except Exception as e:
            logger.error(f"Unexpected error in get_drive_file_content: {e}")
            return f"❌ Unexpected error: {e}"

    # user_google_email: UserGoogleEmail = None,
    @mcp.tool(
        name="list_drive_items",
        description="List files and folders in a specific Google Drive folder with structured output",
        tags={"drive", "list", "folder", "files", "directories", "structured"},
        annotations={
            "title": "List Drive Items",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def list_drive_items(
        user_google_email: UserGoogleEmail = None,
        folder_id: Annotated[
            str,
            Field(
                description="Google Drive folder ID to list contents from (use 'root' for root folder)"
            ),
        ] = "root",
        page_size: Annotated[
            int,
            Field(
                description="Maximum number of items to return (1-100)", ge=1, le=100
            ),
        ] = 20,
        include_subfolders: Annotated[
            bool, Field(description="Include subfolders in the listing")
        ] = True,
        include_files: Annotated[
            bool, Field(description="Include files in the listing")
        ] = True,
    ) -> DriveItemsResponse:
        """
        List all items (files and folders) in a specific Google Drive folder.

        Returns a structured response with categorized items for easy processing.
        Supports filtering by item type (files vs folders) and pagination control.

        Args:
            user_google_email: User's Google email address for authentication
            folder_id: Target folder ID (default: 'root' for root folder)
            page_size: Max items to return (1-100, default: 20)
            include_subfolders: Whether to include folders in results (default: True)
            include_files: Whether to include files in results (default: True)

        Returns:
            DriveItemsResponse: Structured response containing:
                - folderId: The queried folder ID
                - folderName: Name of the queried folder
                - items: List of items with metadata
                - itemCount: Total items returned
                - hasMore: Whether more items are available
                - nextPageToken: Token for pagination
                - error: Error message if listing failed

        Raises:
            HttpError: If Drive API returns an error
            RuntimeError: If authentication fails
        """
        logger.info(
            f"[list_drive_items] Email: '{user_google_email}', Folder: '{folder_id}'"
        )

        try:
            # Get Drive service with fallback support
            drive_service = await _get_drive_service_with_fallback(user_google_email)

            # Get folder metadata first (if not root)
            folder_name = "My Drive (Root)"
            if folder_id != "root":
                try:
                    folder_meta = await asyncio.to_thread(
                        drive_service.files()
                        .get(fileId=folder_id, fields="name", supportsAllDrives=True)
                        .execute
                    )
                    folder_name = folder_meta.get("name", "Unknown Folder")
                except Exception as e:
                    logger.warning(f"Could not fetch folder metadata: {e}")
                    folder_name = f"Folder {folder_id}"

            # Build query based on filters
            query_parts = [f"'{folder_id}' in parents", "trashed = false"]

            if not include_subfolders and not include_files:
                # If both are false, return empty result
                return DriveItemsResponse(
                    folderId=folder_id,
                    folderName=folder_name,
                    items=[],
                    count=0,
                    userEmail=user_google_email,
                    driveId=None,
                    error=None,
                )
            elif not include_subfolders:
                # Only files
                query_parts.append("mimeType != 'application/vnd.google-apps.folder'")
            elif not include_files:
                # Only folders
                query_parts.append("mimeType = 'application/vnd.google-apps.folder'")
            # else: include both (no additional filter needed)

            query = " and ".join(query_parts)

            # List items
            list_params = {
                "q": query,
                "pageSize": page_size,
                "fields": "nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink, iconLink, parents, owners, shared)",
                "orderBy": "folder,name",  # Folders first, then alphabetical
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }

            results = await asyncio.to_thread(
                drive_service.files().list(**list_params).execute
            )

            files = results.get("files", [])

            # Convert to structured items
            structured_items: List[DriveItemInfo] = []
            for item in files:
                is_folder = item.get("mimeType") == "application/vnd.google-apps.folder"

                item_info: DriveItemInfo = {
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "mimeType": item.get("mimeType", ""),
                    "size": item.get("size"),
                    "webViewLink": item.get("webViewLink"),
                    "iconLink": item.get("iconLink"),
                    "createdTime": item.get("createdTime"),
                    "modifiedTime": item.get("modifiedTime"),
                    "parents": item.get("parents"),
                    "owners": item.get("owners"),
                    "shared": item.get("shared"),
                    "starred": item.get("starred"),
                    "trashed": False,  # We filter out trashed items
                    "isFolder": is_folder,
                }
                structured_items.append(item_info)

            return DriveItemsResponse(
                folderId=folder_id,
                folderName=folder_name,
                items=structured_items,
                count=len(structured_items),
                userEmail=user_google_email,
                driveId=None,
                error=None,
            )

        except HttpError as e:
            logger.error(f"Drive API error in list_drive_items: {e}")
            return DriveItemsResponse(
                folderId=folder_id,
                folderName="Unknown",
                items=[],
                count=0,
                userEmail=user_google_email,
                driveId=None,
                error=f"Drive API error: {str(e)}",
            )

        except Exception as e:
            logger.error(f"Unexpected error in list_drive_items: {e}")
            return DriveItemsResponse(
                folderId=folder_id,
                folderName="Unknown",
                items=[],
                count=0,
                userEmail=user_google_email,
                driveId=None,
                error=f"Unexpected error: {str(e)}",
            )

    @mcp.tool(
        name="create_drive_file",
        description="Create a new file in Google Drive from content or URL",
        tags={"drive", "create", "file", "upload", "new"},
        annotations={
            "title": "Create Drive File",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def create_drive_file(
        file_name: str,
        content: Optional[str] = None,
        folder_id: str = "root",
        mime_type: str = "text/plain",
        fileUrl: Optional[str] = None,
        user_google_email: UserGoogleEmail = None,
    ) -> CreateDriveFileResponse:
        """
        Create a new file in Google Drive, supporting creation within shared drives.
        Accepts either direct content or a fileUrl to fetch content from.

        Args:
            user_google_email: User's Google email address
            file_name: Name for the new file
            content: Direct content for the file (optional)
            folder_id: Parent folder ID (default: 'root')
            mime_type: MIME type of the file (default: 'text/plain')
            fileUrl: URL to fetch file content from (optional)

        Returns:
            CreateDriveFileResponse: Structured response with created file details
        """
        logger.info(
            f"[create_drive_file] Email: '{user_google_email}', File: '{file_name}'"
        )

        if not content and not fileUrl:
            return CreateDriveFileResponse(
                success=False,
                fileId=None,
                fileName=file_name,
                mimeType=mime_type,
                folderId=folder_id,
                webViewLink=None,
                userEmail=user_google_email,
                message="You must provide either 'content' or 'fileUrl'.",
                error="Missing required content or fileUrl parameter",
            )

        try:
            drive_service = await _get_drive_service_with_fallback(user_google_email)

            file_data = None
            # Prefer fileUrl if both are provided
            if fileUrl:
                logger.info(f"[create_drive_file] Fetching file from URL: {fileUrl}")
                async with httpx.AsyncClient() as client:
                    resp = await client.get(fileUrl)
                    if resp.status_code != 200:
                        return f"❌ Failed to fetch file from URL: {fileUrl} (status {resp.status_code})"
                    file_data = resp.content

                    # Try to get MIME type from Content-Type header
                    content_type = resp.headers.get("Content-Type")
                    if content_type and content_type != "application/octet-stream":
                        mime_type = content_type
                        logger.info(f"Using MIME type from Content-Type: {mime_type}")
            elif content:
                file_data = content.encode("utf-8")

            # Prepare file metadata
            file_metadata = {
                "name": file_name,
                "parents": [folder_id],
                "mimeType": mime_type,
            }

            # Create media upload
            media = io.BytesIO(file_data)
            media_upload = MediaIoBaseUpload(media, mimetype=mime_type, resumable=True)

            # Create the file
            created_file = await asyncio.to_thread(
                drive_service.files()
                .create(
                    body=file_metadata,
                    media_body=media_upload,
                    fields="id, name, webViewLink",
                    supportsAllDrives=True,
                )
                .execute
            )

            link = created_file.get("webViewLink", "No link available")
            return CreateDriveFileResponse(
                success=True,
                fileId=created_file.get("id"),
                fileName=created_file.get("name", file_name),
                mimeType=mime_type,
                folderId=folder_id,
                webViewLink=created_file.get("webViewLink"),
                userEmail=user_google_email,
                message=f"Successfully created file '{created_file.get('name', file_name)}' (ID: {created_file.get('id', 'N/A')}) in folder '{folder_id}' for {user_google_email}.",
                error=None,
            )

        except HttpError as e:
            logger.error(f"Drive API error in create_drive_file: {e}")
            return CreateDriveFileResponse(
                success=False,
                fileId=None,
                fileName=file_name,
                mimeType=mime_type,
                folderId=folder_id,
                webViewLink=None,
                userEmail=user_google_email,
                message=f"Drive API error: {e}",
                error=str(e),
            )

        except Exception as e:
            logger.error(f"Unexpected error in create_drive_file: {e}")
            return CreateDriveFileResponse(
                success=False,
                fileId=None,
                fileName=file_name,
                mimeType=mime_type,
                folderId=folder_id,
                webViewLink=None,
                userEmail=user_google_email,
                message=f"Unexpected error: {e}",
                error=str(e),
            )

    @mcp.tool(
        name="share_drive_files",
        description="Share Google Drive files with specific people via email addresses",
        tags={"drive", "share", "permissions", "collaborate", "batch"},
        annotations={
            "title": "Share Drive Files",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def share_drive_files(
        file_ids: Annotated[
            List[str], Field(description="List of Google Drive file IDs to share")
        ],
        email_addresses: Annotated[
            List[str], Field(description="List of email addresses to share files with")
        ],
        role: Annotated[
            str,
            Field(
                description="Permission role: 'reader' (view only), 'writer' (edit), 'commenter' (comment only)"
            ),
        ] = "reader",
        send_notification: Annotated[
            bool,
            Field(description="Whether to send email notifications to shared users"),
        ] = True,
        message: Annotated[
            Optional[str],
            Field(
                description="Optional message to include in the sharing notification email"
            ),
        ] = None,
        user_google_email: UserGoogleEmail = None,
    ) -> ShareDriveFilesResponse:
        """
        Share Google Drive files with specific people via email addresses.
        Supports batch operations for multiple files and multiple recipients.

        Args:
            user_google_email: User's Google email address
            file_ids: List of Google Drive file IDs to share
            email_addresses: List of email addresses to share files with
            role: Permission role ('reader', 'writer', 'commenter') (default: 'reader')
            send_notification: Whether to send email notification (default: True)
            message: Optional message to include in sharing notification

        Returns:
            ShareDriveFilesResponse: Structured response with sharing operation results
        """
        logger.info(
            f"[share_drive_files] Email: '{user_google_email}', Files: {len(file_ids)}, Recipients: {len(email_addresses)}"
        )

        if not file_ids:
            return ShareDriveFilesResponse(
                success=False,
                totalFiles=0,
                totalRecipients=len(email_addresses),
                totalOperations=0,
                successfulOperations=0,
                failedOperations=0,
                role=role,
                sendNotification=send_notification,
                results=[],
                userEmail=user_google_email,
                message="No file IDs provided.",
                error="No file IDs provided",
            )

        if not email_addresses:
            return ShareDriveFilesResponse(
                success=False,
                totalFiles=len(file_ids),
                totalRecipients=0,
                totalOperations=0,
                successfulOperations=0,
                failedOperations=0,
                role=role,
                sendNotification=send_notification,
                results=[],
                userEmail=user_google_email,
                message="No email addresses provided.",
                error="No email addresses provided",
            )

        valid_roles = ["reader", "writer", "commenter"]
        if role not in valid_roles:
            return ShareDriveFilesResponse(
                success=False,
                totalFiles=len(file_ids),
                totalRecipients=len(email_addresses),
                totalOperations=0,
                successfulOperations=0,
                failedOperations=0,
                role=role,
                sendNotification=send_notification,
                results=[],
                userEmail=user_google_email,
                message=f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}",
                error=f"Invalid role: {role}",
            )

        try:
            drive_service = await _get_drive_service_with_fallback(user_google_email)

            share_results: List[ShareFileResult] = []
            total_operations = len(file_ids) * len(email_addresses)
            successful_operations = 0
            failed_operations = 0

            for file_id in file_ids:
                # Get file metadata for better reporting
                try:
                    file_metadata = await asyncio.to_thread(
                        drive_service.files()
                        .get(
                            fileId=file_id,
                            fields="id, name, webViewLink",
                            supportsAllDrives=True,
                        )
                        .execute
                    )
                    file_name = file_metadata.get("name", "Unknown File")
                    file_link = file_metadata.get("webViewLink", "#")
                except Exception as e:
                    file_name = f"File ID: {file_id}"
                    file_link = "#"
                    logger.warning(f"Could not fetch metadata for file {file_id}: {e}")

                recipients_processed = []
                recipients_failed = []
                recipients_already_had_access = []

                for email in email_addresses:
                    try:
                        permission_body = {
                            "role": role,
                            "type": "user",
                            "emailAddress": email,
                        }

                        if send_notification and message:
                            permission_body["message"] = message

                        await asyncio.to_thread(
                            drive_service.permissions()
                            .create(
                                fileId=file_id,
                                body=permission_body,
                                sendNotificationEmail=send_notification,
                                supportsAllDrives=True,
                            )
                            .execute
                        )

                        recipients_processed.append(email)
                        successful_operations += 1

                    except HttpError as e:
                        error_msg = str(e)
                        if "already has access" in error_msg.lower():
                            recipients_already_had_access.append(email)
                            successful_operations += 1
                        else:
                            recipients_failed.append(email)
                            failed_operations += 1
                    except Exception:
                        recipients_failed.append(email)
                        failed_operations += 1

                # Create result for this file
                file_result = ShareFileResult(
                    fileId=file_id,
                    fileName=file_name,
                    webViewLink=file_link,
                    recipientsProcessed=recipients_processed,
                    recipientsFailed=recipients_failed,
                    recipientsAlreadyHadAccess=recipients_already_had_access,
                )
                share_results.append(file_result)

            return ShareDriveFilesResponse(
                success=failed_operations == 0,
                totalFiles=len(file_ids),
                totalRecipients=len(email_addresses),
                totalOperations=total_operations,
                successfulOperations=successful_operations,
                failedOperations=failed_operations,
                role=role,
                sendNotification=send_notification,
                results=share_results,
                userEmail=user_google_email,
                message=f"Sharing completed. Files processed: {len(file_ids)}, Recipients: {len(email_addresses)}, Successful: {successful_operations}, Failed: {failed_operations}",
                error=None,
            )

        except HttpError as e:
            logger.error(f"Drive API error in share_drive_files: {e}")
            return ShareDriveFilesResponse(
                success=False,
                totalFiles=len(file_ids),
                totalRecipients=len(email_addresses),
                totalOperations=0,
                successfulOperations=0,
                failedOperations=len(file_ids) * len(email_addresses),
                role=role,
                sendNotification=send_notification,
                results=[],
                userEmail=user_google_email,
                message=f"Drive API error: {e}",
                error=str(e),
            )

        except Exception as e:
            logger.error(f"Unexpected error in share_drive_files: {e}")
            return ShareDriveFilesResponse(
                success=False,
                totalFiles=len(file_ids),
                totalRecipients=len(email_addresses),
                totalOperations=0,
                successfulOperations=0,
                failedOperations=len(file_ids) * len(email_addresses),
                role=role,
                sendNotification=send_notification,
                results=[],
                userEmail=user_google_email,
                message=f"Unexpected error: {e}",
                error=str(e),
            )

    @mcp.tool(
        name="make_drive_files_public",
        description="Make Google Drive files publicly accessible (anyone with the link can view)",
        tags={"drive", "public", "share", "permissions", "batch", "publish"},
        annotations={
            "title": "Make Drive Files Public",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def make_drive_files_public(
        file_ids: List[str],
        public: bool = True,
        role: str = "reader",
        user_google_email: UserGoogleEmail = None,
    ) -> MakeDriveFilesPublicResponse:
        """
        Make Google Drive files publicly accessible or remove public access.
        Supports batch operations for multiple files.

        Args:
            user_google_email: User's Google email address
            file_ids: List of Google Drive file IDs to make public/private
            public: If True, makes files publicly viewable. If False, removes public access (default: True)
            role: Permission role for public access ('reader', 'commenter') (default: 'reader')

        Returns:
            MakeDriveFilesPublicResponse: Structured response with public sharing operation results
        """
        logger.info(
            f"[make_drive_files_public] Email: '{user_google_email}', Files: {len(file_ids)}, Public: {public}"
        )

        if not file_ids:
            return MakeDriveFilesPublicResponse(
                success=False,
                totalFiles=0,
                successfulOperations=0,
                failedOperations=0,
                public=public,
                role=role if public else None,
                results=[],
                userEmail=user_google_email,
                message="No file IDs provided.",
                error="No file IDs provided",
            )

        valid_public_roles = ["reader", "commenter"]
        if public and role not in valid_public_roles:
            return MakeDriveFilesPublicResponse(
                success=False,
                totalFiles=len(file_ids),
                successfulOperations=0,
                failedOperations=len(file_ids),
                public=public,
                role=role,
                results=[],
                userEmail=user_google_email,
                message=f"Invalid public role '{role}'. Must be one of: {', '.join(valid_public_roles)}",
                error=f"Invalid role: {role}",
            )

        try:
            drive_service = await _get_drive_service_with_fallback(user_google_email)

            public_results: List[PublicFileResult] = []
            successful_operations = 0
            failed_operations = 0

            for file_id in file_ids:
                # Get file metadata for better reporting
                try:
                    file_metadata = await asyncio.to_thread(
                        drive_service.files()
                        .get(
                            fileId=file_id,
                            fields="id, name, webViewLink",
                            supportsAllDrives=True,
                        )
                        .execute
                    )
                    file_name = file_metadata.get("name", "Unknown File")
                    file_link = file_metadata.get("webViewLink", "#")
                except Exception as e:
                    file_name = f"File ID: {file_id}"
                    file_link = "#"
                    logger.warning(f"Could not fetch metadata for file {file_id}: {e}")

                file_result = PublicFileResult(
                    fileId=file_id,
                    fileName=file_name,
                    webViewLink=file_link,
                    status="",
                    error=None,
                )

                try:
                    if public:
                        # Make file publicly accessible
                        permission_body = {"role": role, "type": "anyone"}

                        await asyncio.to_thread(
                            drive_service.permissions()
                            .create(
                                fileId=file_id,
                                body=permission_body,
                                supportsAllDrives=True,
                            )
                            .execute
                        )

                        file_result["status"] = "made_public"
                        successful_operations += 1

                    else:
                        # Remove public access - find and delete 'anyone' permission
                        permissions_list = await asyncio.to_thread(
                            drive_service.permissions()
                            .list(fileId=file_id, supportsAllDrives=True)
                            .execute
                        )

                        anyone_permission_id = None
                        for perm in permissions_list.get("permissions", []):
                            if perm.get("type") == "anyone":
                                anyone_permission_id = perm["id"]
                                break

                        if anyone_permission_id:
                            await asyncio.to_thread(
                                drive_service.permissions()
                                .delete(
                                    fileId=file_id,
                                    permissionId=anyone_permission_id,
                                    supportsAllDrives=True,
                                )
                                .execute
                            )
                            file_result["status"] = "removed_public"
                        else:
                            file_result["status"] = "was_not_public"

                        successful_operations += 1

                except HttpError as e:
                    error_msg = str(e)
                    if public and "already exists" in error_msg.lower():
                        file_result["status"] = "already_public"
                        successful_operations += 1
                    else:
                        file_result["status"] = "failed"
                        file_result["error"] = str(e)
                        failed_operations += 1
                except Exception as e:
                    file_result["status"] = "failed"
                    file_result["error"] = str(e)
                    failed_operations += 1

                public_results.append(file_result)

            action = "made public" if public else "made private"
            return MakeDriveFilesPublicResponse(
                success=failed_operations == 0,
                totalFiles=len(file_ids),
                successfulOperations=successful_operations,
                failedOperations=failed_operations,
                public=public,
                role=role if public else None,
                results=public_results,
                userEmail=user_google_email,
                message=f"Public sharing completed. Files processed: {len(file_ids)}, Successfully {action}: {successful_operations}, Failed: {failed_operations}",
                error=None,
            )

        except HttpError as e:
            logger.error(f"Drive API error in make_drive_files_public: {e}")
            return MakeDriveFilesPublicResponse(
                success=False,
                totalFiles=len(file_ids),
                successfulOperations=0,
                failedOperations=len(file_ids),
                public=public,
                role=role if public else None,
                results=[],
                userEmail=user_google_email,
                message=f"Drive API error: {e}",
                error=str(e),
            )

        except Exception as e:
            logger.error(f"Unexpected error in make_drive_files_public: {e}")
            return MakeDriveFilesPublicResponse(
                success=False,
                totalFiles=len(file_ids),
                successfulOperations=0,
                failedOperations=len(file_ids),
                public=public,
                role=role if public else None,
                results=[],
                userEmail=user_google_email,
                message=f"Unexpected error: {e}",
                error=str(e),
            )
