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

import logging
import asyncio
import re
import io
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastmcp import FastMCP
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import httpx

from auth.service_helpers import request_service, get_injected_service, get_service
from auth.context import get_user_email_context

logger = logging.getLogger(__name__)

# Precompiled regex patterns for Drive query detection
DRIVE_QUERY_PATTERNS = [
    re.compile(r'\b\w+\s*(=|!=|>|<)\s*[\'"].*?[\'"]', re.IGNORECASE),  # field = 'value'
    re.compile(r'\b\w+\s*(=|!=|>|<)\s*\d+', re.IGNORECASE),            # field = number
    re.compile(r'\bcontains\b', re.IGNORECASE),                         # contains operator
    re.compile(r'\bin\s+parents\b', re.IGNORECASE),                     # in parents
    re.compile(r'\bhas\s*\{', re.IGNORECASE),                          # has {properties}
    re.compile(r'\btrashed\s*=\s*(true|false)\b', re.IGNORECASE),      # trashed=true/false
    re.compile(r'\bstarred\s*=\s*(true|false)\b', re.IGNORECASE),      # starred=true/false
    re.compile(r'[\'"][^\'"]+[\'"]\s+in\s+parents', re.IGNORECASE),    # 'parentId' in parents
    re.compile(r'\bfullText\s+contains\b', re.IGNORECASE),             # fullText contains
    re.compile(r'\bname\s*(=|contains)\b', re.IGNORECASE),             # name = or name contains
    re.compile(r'\bmimeType\s*(=|!=)\b', re.IGNORECASE),               # mimeType operators
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
    import zipfile
    import xml.etree.ElementTree as ET
    
    shared_strings: List[str] = []
    ns_excel_main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            targets: List[str] = []
            
            # Map MIME type to XML files to inspect
            if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                targets = ["word/document.xml"]
            elif mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
                targets = [n for n in zf.namelist() if n.startswith("ppt/slides/slide")]
            elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                targets = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and "drawing" not in n]
                
                # Parse sharedStrings.xml for Excel files
                try:
                    shared_strings_xml = zf.read("xl/sharedStrings.xml")
                    shared_strings_root = ET.fromstring(shared_strings_xml)
                    for si_element in shared_strings_root.findall(f"{{{ns_excel_main}}}si"):
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

                    if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                        for cell_element in xml_root.findall(f".//{{{ns_excel_main}}}c"):
                            value_element = cell_element.find(f"{{{ns_excel_main}}}v")
                            
                            if value_element is None or value_element.text is None:
                                continue

                            cell_type = cell_element.get('t')
                            if cell_type == 's':  # Shared string
                                try:
                                    ss_idx = int(value_element.text)
                                    if 0 <= ss_idx < len(shared_strings):
                                        member_texts.append(shared_strings[ss_idx])
                                except ValueError:
                                    logger.warning(f"Non-integer shared string index: '{value_element.text}'")
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
    service_key = request_service("drive")
    
    try:
        # Try to get the injected service from middleware
        drive_service = get_injected_service(service_key)
        logger.info(f"Successfully retrieved injected Drive service for {user_google_email}")
        return drive_service
        
    except RuntimeError as e:
        if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
            # Middleware injection failed, fall back to direct service creation
            logger.warning(f"Middleware injection unavailable, falling back to direct service creation for {user_google_email}")
            
            try:
                # Use the helper function that handles smart defaults
                drive_service = await get_service("drive", user_google_email)
                logger.info(f"Successfully created Drive service directly for {user_google_email}")
                return drive_service
                
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(f"Direct service creation also failed: {direct_error}")
                
                # Check for specific credential errors
                if "credentials do not contain the necessary fields" in error_str.lower():
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


def setup_drive_comprehensive_tools(mcp: FastMCP) -> None:
    """
    Register comprehensive Google Drive tools with the FastMCP server.
    
    This function registers the missing Drive tools:
    1. search_drive_files: Advanced file/folder search
    2. get_drive_file_content: File content retrieval
    3. list_drive_items: Directory listing
    4. create_drive_file: File creation
    
    Args:
        mcp: FastMCP server instance to register tools with
        
    Returns:
        None: Tools are registered as side effects
    """
    
    @mcp.tool(
        name="search_drive_files",
        description="Search for files and folders in Google Drive with advanced query support",
        tags={"drive", "search", "files", "folders", "query"},
        annotations={
            "title": "Search Google Drive",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def search_drive_files(
        user_google_email: str,
        query: str,
        page_size: int = 10,
        drive_id: Optional[str] = None,
        include_items_from_all_drives: bool = True,
        corpora: Optional[str] = None,
    ) -> str:
        """
        Search for files and folders within Google Drive, including shared drives.
        
        Args:
            user_google_email: User's Google email address
            query: Search query string (supports Google Drive search operators)
            page_size: Maximum number of files to return (default: 10)
            drive_id: ID of shared drive to search (optional)
            include_items_from_all_drives: Include shared drive items (default: True)
            corpora: Bodies of items to query ('user', 'domain', 'drive', 'allDrives')
            
        Returns:
            str: Formatted list of found files/folders with details
        """
        logger.info(f"[search_drive_files] Email: '{user_google_email}', Query: '{query}'")
        
        try:
            # Get Drive service with fallback support
            drive_service = await _get_drive_service_with_fallback(user_google_email)
            
            # Check if query is structured or free text
            is_structured_query = any(pattern.search(query) for pattern in DRIVE_QUERY_PATTERNS)
            
            if is_structured_query:
                final_query = query
                logger.info(f"[search_drive_files] Using structured query: '{final_query}'")
            else:
                # For free text queries, wrap in fullText contains
                escaped_query = query.replace("'", "\\'")
                final_query = f"fullText contains '{escaped_query}'"
                logger.info(f"[search_drive_files] Reformatting to: '{final_query}'")
            
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
            files = results.get('files', [])
            
            if not files:
                return f"No files found for '{query}'."
            
            formatted_parts = [f"Found {len(files)} files for {user_google_email} matching '{query}':"]
            for item in files:
                size_str = f", Size: {item.get('size', 'N/A')}" if 'size' in item else ""
                formatted_parts.append(
                    f"- Name: \"{item['name']}\" (ID: {item['id']}, Type: {item['mimeType']}{size_str}, "
                    f"Modified: {item.get('modifiedTime', 'N/A')}) Link: {item.get('webViewLink', '#')}"
                )
            
            return "\n".join(formatted_parts)
                
        except HttpError as e:
            logger.error(f"Drive API error in search_drive_files: {e}")
            return f"❌ Drive API error: {e}"
            
        except Exception as e:
            logger.error(f"Unexpected error in search_drive_files: {e}")
            return f"❌ Unexpected error: {e}"
    
    @mcp.tool(
        name="get_drive_file_content", 
        description="Retrieve the content of a Google Drive file by ID, supporting multiple formats",
        tags={"drive", "file", "content", "download", "read"},
        annotations={
            "title": "Get Drive File Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_drive_file_content(
        user_google_email: str,
        file_id: str,
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
                drive_service.files().get(
                    fileId=file_id, 
                    fields="id, name, mimeType, webViewLink", 
                    supportsAllDrives=True
                ).execute
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
                drive_service.files().export_media(fileId=file_id, mimeType=export_mime_type)
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
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
                f'Link: {file_metadata.get("webViewLink", "#")}\n\n--- CONTENT ---\n'
            )
            return header + body_text
                
        except HttpError as e:
            logger.error(f"Drive API error in get_drive_file_content: {e}")
            return f"❌ Drive API error: {e}"
            
        except Exception as e:
            logger.error(f"Unexpected error in get_drive_file_content: {e}")
            return f"❌ Unexpected error: {e}"
    
    @mcp.tool(
        name="list_drive_items",
        description="List files and folders in a Google Drive directory, including shared drives",
        tags={"drive", "list", "directory", "folder", "files"},
        annotations={
            "title": "List Drive Items",
            "readOnlyHint": True,
            "destructiveHint": False, 
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_drive_items(
        user_google_email: str,
        folder_id: str = 'root',
        page_size: int = 100,
        drive_id: Optional[str] = None,
        include_items_from_all_drives: bool = True,
        corpora: Optional[str] = None,
    ) -> str:
        """
        List files and folders in a Drive directory, supporting shared drives.
        
        Args:
            user_google_email: User's Google email address
            folder_id: Folder ID to list (default: 'root')
            page_size: Maximum number of items to return (default: 100)
            drive_id: ID of shared drive (optional)
            include_items_from_all_drives: Include shared drive items (default: True)
            corpora: Corpus to query ('user', 'drive', 'allDrives')
            
        Returns:
            str: Formatted list of files/folders in the specified directory
        """
        logger.info(f"[list_drive_items] Email: '{user_google_email}', Folder ID: '{folder_id}'")
        
        try:
            drive_service = await _get_drive_service_with_fallback(user_google_email)
            
            # Build query for items in folder
            final_query = f"'{folder_id}' in parents and trashed=false"
            
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
            files = results.get('files', [])
            
            if not files:
                return f"No items found in folder '{folder_id}'."
            
            formatted_parts = [f"Found {len(files)} items in folder '{folder_id}' for {user_google_email}:"]
            for item in files:
                size_str = f", Size: {item.get('size', 'N/A')}" if 'size' in item else ""
                formatted_parts.append(
                    f"- Name: \"{item['name']}\" (ID: {item['id']}, Type: {item['mimeType']}{size_str}, "
                    f"Modified: {item.get('modifiedTime', 'N/A')}) Link: {item.get('webViewLink', '#')}"
                )
            
            return "\n".join(formatted_parts)
                
        except HttpError as e:
            logger.error(f"Drive API error in list_drive_items: {e}")
            return f"❌ Drive API error: {e}"
            
        except Exception as e:
            logger.error(f"Unexpected error in list_drive_items: {e}")
            return f"❌ Unexpected error: {e}"
    
    @mcp.tool(
        name="create_drive_file",
        description="Create a new file in Google Drive from content or URL",
        tags={"drive", "create", "file", "upload", "new"},
        annotations={
            "title": "Create Drive File",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_drive_file(
        user_google_email: str,
        file_name: str,
        content: Optional[str] = None,
        folder_id: str = 'root',
        mime_type: str = 'text/plain',
        fileUrl: Optional[str] = None,
    ) -> str:
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
            str: Confirmation message with created file details and link
        """
        logger.info(f"[create_drive_file] Email: '{user_google_email}', File: '{file_name}'")
        
        if not content and not fileUrl:
            return "❌ You must provide either 'content' or 'fileUrl'."
        
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
                file_data = content.encode('utf-8')
            
            # Prepare file metadata
            file_metadata = {
                'name': file_name,
                'parents': [folder_id],
                'mimeType': mime_type
            }
            
            # Create media upload
            media = io.BytesIO(file_data)
            media_upload = MediaIoBaseUpload(media, mimetype=mime_type, resumable=True)
            
            # Create the file
            created_file = await asyncio.to_thread(
                drive_service.files().create(
                    body=file_metadata,
                    media_body=media_upload,
                    fields='id, name, webViewLink',
                    supportsAllDrives=True
                ).execute
            )
            
            link = created_file.get('webViewLink', 'No link available')
            return (
                f"✅ Successfully created file '{created_file.get('name', file_name)}' "
                f"(ID: {created_file.get('id', 'N/A')}) in folder '{folder_id}' "
                f"for {user_google_email}.\nLink: {link}"
            )
                
        except HttpError as e:
            logger.error(f"Drive API error in create_drive_file: {e}")
            return f"❌ Drive API error: {e}"
            
        except Exception as e:
            logger.error(f"Unexpected error in create_drive_file: {e}")
            return f"❌ Unexpected error: {e}"