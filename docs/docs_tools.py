"""
Google Docs tools for FastMCP2 with middleware-based service injection and fallback support.

This module provides comprehensive Google Docs integrationasync def get_doc_content(
    document_id: str,
    user_google_email: UserGoogleEmail = None
) -> str:ls for FastMCP2 servers,
using the new middleware-dependent pattern for Google service authentication with
fallback to direct service creation when middleware injection is unavailable.

    async def list_docs_in_folder_tool(
        folder_id: str = 'root',
        page_size: int = 100,
        user_google_email: UserGoogleEmail = None
    ) -> str:eatures:
- Search for Google Docs by name using Dasync def create_doc(
    title: str,
    content: str = "",
    user_google_email: UserGoogleEmail = None
) -> str:API
- R        ""List Google Docs within a specific Drive folder.""
        return await list_docs_in_folder(folder_id, page_size, user_google_email)rieve content from Google Docs and Drive files
- List Google Docs within specific folders
- Create new Google Docs with initial content
- Support for both native Google Docs and Office files
- Comprehensive error handling with user-friendly messages
- Fallback to direct service creation when middleware unavailable

Architecture:
- Primary: Uses middleware-based servic    async def create_doc_tool(
        title: str,
        content: str = "",
        user_google_email: UserGoogleEmail = None
    ) -> str:ection (no decorators)
- Fallback: Direct service creation when middleware unavailable
- Automatic Google service authentication and caching
- Consistent error handling and token refresh
- FastMCP2 framework integration

Dependencies:
- google-api-python-client: Google Docs and Drive API integration
- fastmcp: FastMCP server framework
- auth.service_helpers: Service injection utilities
"""

import logging
import asyncio
import io
import re
from typing_extensions import List, Optional, Union
from pathlib import Path
from googleapiclient.http import MediaIoBaseUpload

from fastmcp import FastMCP
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from auth.service_helpers import request_service, get_injected_service, get_service
from auth.context import get_user_email_context
from tools.common_types import UserGoogleEmail
from .utils import extract_office_xml_text
from .docs_types import DocsListResponse, DocInfo

logger = logging.getLogger(__name__)


async def search_docs(
    query: str,
    page_size: int = 10,
    user_google_email: UserGoogleEmail = None
) -> str:
    """
    Searches for Google Docs by name using Drive API (mimeType filter).

    Args:
        user_google_email: The user's Google email address
        query: Search query string to find docs
        page_size: Maximum number of results to return (default: 10)

    Returns:
        str: A formatted list of Google Docs matching the search query.
    """
    logger.info(f"[search_docs] Email={user_google_email}, Query='{query}'")

    # Request Drive service through middleware
    logger.debug(f"[search_docs] Requesting drive service for {user_google_email}")
    drive_key = request_service("drive")
    logger.debug(f"[search_docs] Got service key: {drive_key}")
    
    try:
        logger.debug(f"[search_docs] Attempting to get injected service with key: {drive_key}")
        drive_service = get_injected_service(drive_key)
        logger.info(f"[search_docs] Successfully retrieved injected Drive service for {user_google_email}")
    except RuntimeError as e:
        logger.warning(f"[search_docs] Middleware injection failed: {e}")
        if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
            logger.info("[search_docs] Falling back to direct service creation")
            try:
                drive_service = await get_service("drive", user_google_email)
                logger.info(f"[search_docs] Successfully created Drive service directly for {user_google_email}")
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(f"[search_docs] Direct service creation also failed: {direct_error}")
                
                # Check for specific credential errors and return user-friendly messages
                if "no valid credentials found" in error_str.lower():
                    return (
                        f"❌ **No Credentials Found**\n\n"
                        f"No authentication credentials found for {user_google_email}.\n\n"
                        f"**To authenticate:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Follow the authentication flow in your browser\n"
                        f"3. Grant Drive permissions when prompted\n"
                        f"4. Return here after seeing the success page"
                    )
                elif "credentials do not contain the necessary fields" in error_str.lower():
                    return (
                        f"❌ **Invalid or Corrupted Credentials**\n\n"
                        f"Your stored credentials for {user_google_email} are missing required OAuth fields.\n\n"
                        f"**To fix this:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Complete the authentication flow\n"
                        f"3. Try your Docs command again"
                    )
                else:
                    return f"❌ Authentication error: {error_str}"
        else:
            logger.error(f"[search_docs] Unexpected RuntimeError: {e}")
            raise

    try:
        escaped_query = query.replace("'", "\\'")

        response = await asyncio.to_thread(
            drive_service.files().list(
                q=f"name contains '{escaped_query}' and mimeType='application/vnd.google-apps.document' and trashed=false",
                pageSize=page_size,
                fields="files(id, name, createdTime, modifiedTime, webViewLink)"
            ).execute
        )
        files = response.get('files', [])
        if not files:
            return f"No Google Docs found matching '{query}'."

        output = [f"Found {len(files)} Google Docs matching '{query}':"]
        for f in files:
            output.append(
                f"- {f['name']} (ID: {f['id']}) Modified: {f.get('modifiedTime')} Link: {f.get('webViewLink')}"
            )
        return "\n".join(output)

    except HttpError as e:
        logger.error(f"Google API error in search_docs: {e}")
        if e.resp.status == 401:
            return "❌ Authentication failed. Please check your Google credentials."
        elif e.resp.status == 403:
            return "❌ Permission denied. Make sure you have access to Google Drive."
        else:
            return f"❌ Error searching docs: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in search_docs: {e}", exc_info=True)
        return f"❌ Unexpected error: {str(e)}"


async def get_doc_content(
    user_google_email: UserGoogleEmail,
    document_id: str,
) -> str:
    """
    Retrieves content of a Google Doc or a Drive file (like .docx) identified by document_id.
    - Native Google Docs: Fetches content via Docs API.
    - Office files (.docx, etc.) stored in Drive: Downloads via Drive API and extracts text.

    Args:
        user_google_email: The user's Google email address
        document_id: The ID of the Google Doc or Drive file

    Returns:
        str: The document content with metadata header.
    """
    logger.info(f"[get_doc_content] Document/File ID: '{document_id}' for user '{user_google_email}'")

    # Request both Drive and Docs services through middleware
    drive_key = request_service("drive")
    docs_key = request_service("docs")
    
    # Get Drive service with fallback
    try:
        drive_service = get_injected_service(drive_key)
        logger.info(f"[get_doc_content] Successfully retrieved injected Drive service for {user_google_email}")
    except RuntimeError as e:
        logger.warning(f"[get_doc_content] Drive middleware injection failed: {e}")
        if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
            logger.info("[get_doc_content] Falling back to direct drive service creation")
            try:
                drive_service = await get_service("drive", user_google_email)
                logger.info(f"[get_doc_content] Successfully created Drive service directly for {user_google_email}")
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(f"[get_doc_content] Direct drive service creation also failed: {direct_error}")
                
                # Check for specific credential errors and return user-friendly messages
                if "no valid credentials found" in error_str.lower():
                    return (
                        f"❌ **No Credentials Found**\n\n"
                        f"No authentication credentials found for {user_google_email}.\n\n"
                        f"**To authenticate:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Follow the authentication flow in your browser\n"
                        f"3. Grant Drive permissions when prompted\n"
                        f"4. Return here after seeing the success page"
                    )
                elif "credentials do not contain the necessary fields" in error_str.lower():
                    return (
                        f"❌ **Invalid or Corrupted Credentials**\n\n"
                        f"Your stored credentials for {user_google_email} are missing required OAuth fields.\n\n"
                        f"**To fix this:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Complete the authentication flow\n"
                        f"3. Try your Docs command again"
                    )
                else:
                    return f"❌ Authentication error: {error_str}"
        else:
            logger.error(f"[get_doc_content] Unexpected RuntimeError: {e}")
            raise
    
    # Get Docs service with fallback
    try:
        docs_service = get_injected_service(docs_key)
        logger.info(f"[get_doc_content] Successfully retrieved injected Docs service for {user_google_email}")
    except RuntimeError as e:
        logger.warning(f"[get_doc_content] Docs middleware injection failed: {e}")
        if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
            logger.info("[get_doc_content] Falling back to direct docs service creation")
            try:
                docs_service = await get_service("docs", user_google_email)
                logger.info(f"[get_doc_content] Successfully created Docs service directly for {user_google_email}")
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(f"[get_doc_content] Direct docs service creation also failed: {direct_error}")
                
                # Check for specific credential errors and return user-friendly messages
                if "no valid credentials found" in error_str.lower():
                    return (
                        f"❌ **No Credentials Found**\n\n"
                        f"No authentication credentials found for {user_google_email}.\n\n"
                        f"**To authenticate:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Follow the authentication flow in your browser\n"
                        f"3. Grant Docs permissions when prompted\n"
                        f"4. Return here after seeing the success page"
                    )
                elif "credentials do not contain the necessary fields" in error_str.lower():
                    return (
                        f"❌ **Invalid or Corrupted Credentials**\n\n"
                        f"Your stored credentials for {user_google_email} are missing required OAuth fields.\n\n"
                        f"**To fix this:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Complete the authentication flow\n"
                        f"3. Try your Docs command again"
                    )
                else:
                    return f"❌ Authentication error: {error_str}"
        else:
            logger.error(f"[get_doc_content] Unexpected RuntimeError: {e}")
            raise

    try:
        # Get file metadata from Drive
        file_metadata = await asyncio.to_thread(
            drive_service.files().get(
                fileId=document_id, fields="id, name, mimeType, webViewLink"
            ).execute
        )
        mime_type = file_metadata.get("mimeType", "")
        file_name = file_metadata.get("name", "Unknown File")
        web_view_link = file_metadata.get("webViewLink", "#")

        logger.info(f"[get_doc_content] File '{file_name}' (ID: {document_id}) has mimeType: '{mime_type}'")

        body_text = ""  # Initialize body_text

        # Process based on mimeType
        if mime_type == "application/vnd.google-apps.document":
            logger.info(f"[get_doc_content] Processing as native Google Doc.")
            doc_data = await asyncio.to_thread(
                docs_service.documents().get(documentId=document_id).execute
            )
            body_elements = doc_data.get('body', {}).get('content', [])

            processed_text_lines: List[str] = []
            for element in body_elements:
                if 'paragraph' in element:
                    paragraph = element.get('paragraph', {})
                    para_elements = paragraph.get('elements', [])
                    current_line_text = ""
                    for pe in para_elements:
                        text_run = pe.get('textRun', {})
                        if text_run and 'content' in text_run:
                            current_line_text += text_run['content']
                    if current_line_text.strip():
                        processed_text_lines.append(current_line_text)
            body_text = "".join(processed_text_lines)
        else:
            logger.info(f"[get_doc_content] Processing as Drive file (e.g., .docx, other). MimeType: {mime_type}")

            export_mime_type_map = {
                # Example: "application/vnd.google-apps.spreadsheet": "text/csv",
                # Native GSuite types that are not Docs would go here if this function
                # was intended to export them. For .docx, direct download is used.
            }
            effective_export_mime = export_mime_type_map.get(mime_type)

            request_obj = (
                drive_service.files().export_media(fileId=document_id, mimeType=effective_export_mime)
                if effective_export_mime
                else drive_service.files().get_media(fileId=document_id)
            )

            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request_obj)
            loop = asyncio.get_event_loop()
            done = False
            while not done:
                status, done = await loop.run_in_executor(None, downloader.next_chunk)

            file_content_bytes = fh.getvalue()

            office_text = extract_office_xml_text(file_content_bytes, mime_type)
            if office_text:
                body_text = office_text
            else:
                try:
                    body_text = file_content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    body_text = (
                        f"[Binary or unsupported text encoding for mimeType '{mime_type}' - "
                        f"{len(file_content_bytes)} bytes]"
                    )

        header = (
            f'File: "{file_name}" (ID: {document_id}, Type: {mime_type})\n'
            f'Link: {web_view_link}\n\n--- CONTENT ---\n'
        )
        return header + body_text

    except HttpError as e:
        logger.error(f"Google API error in get_doc_content: {e}")
        if e.resp.status == 401:
            return "❌ Authentication failed. Please check your Google credentials."
        elif e.resp.status == 403:
            return "❌ Permission denied. Make sure you have access to this document."
        elif e.resp.status == 404:
            return f"❌ Document not found: {document_id}"
        else:
            return f"❌ Error retrieving document: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in get_doc_content: {e}", exc_info=True)
        return f"❌ Unexpected error: {str(e)}"


async def list_docs_in_folder(
    folder_id: str = 'root',
    page_size: int = 100,
    user_google_email: UserGoogleEmail = None
) -> DocsListResponse:
    """
    Lists Google Docs within a specific Drive folder.

    Args:
        user_google_email: The user's Google email address
        folder_id: The ID of the folder to list docs from (default: 'root')
        page_size: Maximum number of results to return (default: 100)

    Returns:
        DocsListResponse: Structured response with list of Google Docs in the specified folder.
    """
    logger.info(f"[list_docs_in_folder] Email: '{user_google_email}', Folder ID: '{folder_id}'")

    # Request Drive service through middleware
    logger.debug(f"[list_docs_in_folder] Requesting drive service for {user_google_email}")
    drive_key = request_service("drive")
    logger.debug(f"[list_docs_in_folder] Got service key: {drive_key}")
    
    try:
        logger.debug(f"[list_docs_in_folder] Attempting to get injected service with key: {drive_key}")
        drive_service = get_injected_service(drive_key)
        logger.info(f"[list_docs_in_folder] Successfully retrieved injected Drive service for {user_google_email}")
    except RuntimeError as e:
        logger.warning(f"[list_docs_in_folder] Middleware injection failed: {e}")
        if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
            logger.info("[list_docs_in_folder] Falling back to direct service creation")
            try:
                drive_service = await get_service("drive", user_google_email)
                logger.info(f"[list_docs_in_folder] Successfully created Drive service directly for {user_google_email}")
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(f"[list_docs_in_folder] Direct service creation also failed: {direct_error}")
                
                # Check for specific credential errors and return user-friendly messages
                if "no valid credentials found" in error_str.lower():
                    error_msg = (
                        f"❌ **No Credentials Found**\n\n"
                        f"No authentication credentials found for {user_google_email}.\n\n"
                        f"**To authenticate:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Follow the authentication flow in your browser\n"
                        f"3. Grant Drive permissions when prompted\n"
                        f"4. Return here after seeing the success page"
                    )
                elif "credentials do not contain the necessary fields" in error_str.lower():
                    error_msg = (
                        f"❌ **Invalid or Corrupted Credentials**\n\n"
                        f"Your stored credentials for {user_google_email} are missing required OAuth fields.\n\n"
                        f"**To fix this:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Complete the authentication flow\n"
                        f"3. Try your Docs command again"
                    )
                else:
                    error_msg = f"❌ Authentication error: {error_str}"
                
                return DocsListResponse(
                    docs=[],
                    count=0,
                    folderId=folder_id,
                    folderName=None,
                    userEmail=user_google_email,
                    error=error_msg
                )
        else:
            logger.error(f"[list_docs_in_folder] Unexpected RuntimeError: {e}")
            raise

    try:
        rsp = await asyncio.to_thread(
            drive_service.files().list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document' and trashed=false",
                pageSize=page_size,
                fields="files(id, name, modifiedTime, webViewLink)"
            ).execute
        )
        items = rsp.get('files', [])
        
        # Build structured response
        docs: List[DocInfo] = []
        for file in items:
            doc_info = DocInfo(
                id=file.get('id', ''),
                name=file.get('name', 'Unknown'),
                modifiedTime=file.get('modifiedTime'),
                webViewLink=file.get('webViewLink')
            )
            docs.append(doc_info)
        
        return DocsListResponse(
            docs=docs,
            count=len(docs),
            folderId=folder_id,
            folderName="root" if folder_id == "root" else None,
            userEmail=user_google_email
        )

    except HttpError as e:
        logger.error(f"Google API error in list_docs_in_folder: {e}")
        error_msg = ""
        if e.resp.status == 401:
            error_msg = "Authentication failed. Please check your Google credentials."
        elif e.resp.status == 403:
            error_msg = "Permission denied. Make sure you have access to this folder."
        elif e.resp.status == 404:
            error_msg = f"Folder not found: {folder_id}"
        else:
            error_msg = f"Error listing docs: {str(e)}"
        
        return DocsListResponse(
            docs=[],
            count=0,
            folderId=folder_id,
            folderName=None,
            userEmail=user_google_email,
            error=error_msg
        )
    except Exception as e:
        logger.error(f"Unexpected error in list_docs_in_folder: {e}", exc_info=True)
        return DocsListResponse(
            docs=[],
            count=0,
            folderId=folder_id,
            folderName=None,
            userEmail=user_google_email,
            error=f"Unexpected error: {str(e)}"
        )


def detect_content_type(content: str) -> str:
    """
    Simple detection of content type based on common patterns.
    
    Args:
        content: The content string to analyze
        
    Returns:
        str: 'markdown', 'html', or 'plain'
    """
    # Check for HTML tags
    if re.search(r'<h[1-6]>|<p>|<div>|<strong>|<em>|<ul>|<ol>|<li>|<table>', content, re.IGNORECASE):
        return 'html'
    
    # Check for markdown patterns
    if re.search(r'^#{1,6}\s+|\*\*.*?\*\*|\*.*?\*|^-\s+|^\d+\.\s+|\[.*?\]\(.*?\)', content, re.MULTILINE):
        return 'markdown'
    
    return 'plain'


def markdown_to_html(markdown_content: str) -> str:
    """
    Convert basic markdown to HTML.
    This is a simple converter for common markdown patterns.
    
    Args:
        markdown_content: Markdown content string
        
    Returns:
        str: HTML content
    """
    html = markdown_content
    
    # Convert headers
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    
    # Convert bold and italic
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    
    # Convert links
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
    
    # Convert bullet lists
    lines = html.split('\n')
    in_list = False
    result_lines = []
    
    for line in lines:
        if re.match(r'^-\s+', line):
            if not in_list:
                result_lines.append('<ul>')
                in_list = True
            item_text = re.sub(r'^-\s+', '', line)
            result_lines.append(f'<li>{item_text}</li>')
        else:
            if in_list:
                result_lines.append('</ul>')
                in_list = False
            if line.strip():
                result_lines.append(f'<p>{line}</p>')
            else:
                result_lines.append('')
    
    if in_list:
        result_lines.append('</ul>')
    
    return '\n'.join(result_lines)


async def create_doc(
    user_google_email: UserGoogleEmail,
    title: str,
    content: str = '',
) -> str:
    """
    Creates a new Google Doc and optionally inserts initial content with rich formatting.
    
    This function uses Google Drive API's automatic conversion feature to create properly
    formatted Google Docs from HTML content. It supports:
    - Plain text: Inserted directly using Docs API
    - Markdown: Converted to HTML and then uploaded to Drive for conversion
    - HTML: Uploaded to Drive for automatic conversion to Google Doc format
    
    The conversion approach leverages Google's built-in HTML-to-Docs conversion,
    which properly handles headings, formatting, lists, tables, and other rich content.

    Args:
        user_google_email: The user's Google email address
        title: Title for the new document
        content: Initial content to insert into the document (optional)

    Returns:
        str: Confirmation message with document ID and link.
    """
    logger.info(f"[create_doc] Email: '{user_google_email}', Title='{title}'")

    if not content:
        # For empty documents, create a simple doc using Docs API
        docs_key = request_service("docs")
        
        try:
            docs_service = get_injected_service(docs_key)
            logger.info(f"[create_doc] Using injected Docs service for empty doc")
        except RuntimeError as e:
            logger.warning(f"[create_doc] Docs middleware injection failed: {e}")
            if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
                docs_service = await get_service("docs", user_google_email)
                logger.info(f"[create_doc] Using direct Docs service for empty doc")
            else:
                raise

        try:
            doc = await asyncio.to_thread(
                docs_service.documents().create(body={'title': title}).execute
            )
            doc_id = doc.get('documentId')
            link = f"https://docs.google.com/document/d/{doc_id}/edit"
            return f"Created empty Google Doc '{title}' (ID: {doc_id}) for {user_google_email}. Link: {link}"
        except HttpError as e:
            logger.error(f"Google API error creating empty doc: {e}")
            if e.resp.status == 401:
                return "❌ Authentication failed. Please check your Google credentials."
            elif e.resp.status == 403:
                return "❌ Permission denied. Make sure you have permission to create documents."
            else:
                return f"❌ Error creating document: {str(e)}"

    # For content, use Drive API with conversion
    drive_key = request_service("drive")
    
    try:
        drive_service = get_injected_service(drive_key)
        logger.info(f"[create_doc] Using injected Drive service for content conversion")
    except RuntimeError as e:
        logger.warning(f"[create_doc] Drive middleware injection failed: {e}")
        if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
            logger.info("[create_doc] Falling back to direct drive service creation")
            try:
                drive_service = await get_service("drive", user_google_email)
                logger.info(f"[create_doc] Using direct Drive service for content conversion")
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(f"[create_doc] Direct drive service creation failed: {direct_error}")
                
                if "no valid credentials found" in error_str.lower():
                    return (
                        f"❌ **No Credentials Found**\n\n"
                        f"No authentication credentials found for {user_google_email}.\n\n"
                        f"**To authenticate:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Follow the authentication flow in your browser\n"
                        f"3. Grant Drive permissions when prompted\n"
                        f"4. Return here after seeing the success page"
                    )
                elif "credentials do not contain the necessary fields" in error_str.lower():
                    return (
                        f"❌ **Invalid or Corrupted Credentials**\n\n"
                        f"Your stored credentials for {user_google_email} are missing required OAuth fields.\n\n"
                        f"**To fix this:**\n"
                        f"1. Run `start_google_auth` with your email: {user_google_email}\n"
                        f"2. Complete the authentication flow\n"
                        f"3. Try your Docs command again"
                    )
                else:
                    return f"❌ Authentication error: {error_str}"
        else:
            logger.error(f"[create_doc] Unexpected RuntimeError: {e}")
            raise

    try:
        # Detect content type and prepare for conversion
        content_type = detect_content_type(content)
        logger.info(f"[create_doc] Detected content type: {content_type}")
        
        if content_type == 'markdown':
            # Convert markdown to HTML
            html_content = markdown_to_html(content)
            logger.info(f"[create_doc] Converted markdown to HTML")
        elif content_type == 'html':
            html_content = content
        else:
            # For plain text, wrap in basic HTML
            html_content = f"<p>{content.replace(chr(10), '</p><p>')}</p>"
        
        # Create file metadata for Google Docs conversion
        file_metadata = {
            'name': title,
            'mimeType': 'application/vnd.google-apps.document'  # Target: Google Doc
        }
        
        # Create media upload from HTML content
        html_bytes = html_content.encode('utf-8')
        media_body = MediaIoBaseUpload(
            io.BytesIO(html_bytes),
            mimetype='text/html',  # Source: HTML
            resumable=False
        )
        
        # Upload and convert to Google Doc
        file = await asyncio.to_thread(
            drive_service.files().create(
                body=file_metadata,
                media_body=media_body,
                fields='id,name,webViewLink'
            ).execute
        )
        
        doc_id = file.get('id')
        doc_name = file.get('name')
        web_link = file.get('webViewLink')
        
        content_info = f" with {content_type} formatting"
        msg = f"Created Google Doc '{doc_name}' (ID: {doc_id}) for {user_google_email}{content_info}. Link: {web_link}"
        logger.info(f"Successfully created formatted Google Doc using Drive API conversion: {doc_id}")
        return msg

    except HttpError as e:
        logger.error(f"Google API error in create_doc: {e}")
        if e.resp.status == 401:
            return "❌ Authentication failed. Please check your Google credentials."
        elif e.resp.status == 403:
            return "❌ Permission denied. Make sure you have permission to create documents."
        else:
            return f"❌ Error creating document: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in create_doc: {e}", exc_info=True)
        return f"❌ Unexpected error: {str(e)}"


def setup_docs_tools(mcp: FastMCP):
    """
    Register all Google Docs tools with the FastMCP server.
    
    Args:
        mcp: The FastMCP server instance
    """
    
    @mcp.tool(
        name="search_docs",
        description="Search for Google Docs by name using Drive API"
    )
    async def search_docs_tool(
        query: str,
        page_size: int = 10,
        user_google_email: UserGoogleEmail = None
    ) -> str:
        """Search for Google Docs by name."""
        return await search_docs(query, page_size, user_google_email)
    
    @mcp.tool(
        name="get_doc_content",
        description="Get content of a Google Doc or Drive file (like .docx)",
        tags={"docs", "content", "read", "google"},
        annotations={
            "title": "Get Google Doc Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_doc_content_tool(
        document_id: str,
        user_google_email: UserGoogleEmail = None
    ) -> str:
        """Get content of a Google Doc or Drive file."""
        return await get_doc_content(document_id, user_google_email)
    
    @mcp.tool(
        name="list_docs_in_folder",
        description="List Google Docs within a specific Drive folder",
        tags={"docs", "list", "folder", "google"},
        annotations={
            "title": "List Google Docs in Folder",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_docs_in_folder_tool(
        folder_id: str = 'root',
        page_size: int = 100,
        user_google_email: UserGoogleEmail = None
    ) -> DocsListResponse:
        """List Google Docs within a specific folder."""
        return await list_docs_in_folder(folder_id, page_size, user_google_email)
    
    @mcp.tool(
        name="create_doc",
        description="Create a new Google Doc with optional initial content. Supports plain text, Markdown, and HTML formatting. Content type is automatically detected and converted to proper Google Doc formatting.",
        tags={"docs", "create", "google", "markdown", "html", "formatting"},
        annotations={
            "title": "Create Google Doc with Rich Formatting",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_doc_tool(
        title: str,
        content: str = '',
        user_google_email: UserGoogleEmail = None
    ) -> str:
        """Create a new Google Doc with optional initial content."""
        return await create_doc(title, content, user_google_email)
        """Create a new Google Doc with automatic rich content formatting (supports Markdown and HTML)."""
        return await create_doc(user_google_email, title, content)
    
    logger.info("Google Docs tools registered successfully")