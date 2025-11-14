"""
Google Docs tools for FastMCP2 with middleware-based service injection and fallback support.

This module provides comprehensive Google Docs integration tools for FastMCP2 servers,
using the new middleware-dependent pattern for Google service authentication with
fallback to direct service creation when middleware injection is unavailable.

Features:
- Search for Google Docs by name using Drive API
- Retrieve content from Google Docs and Drive files
- List Google Docs within specific folders
- Create new Google Docs with initial content
- Support for both native Google Docs and Office files
- Comprehensive error handling with user-friendly messages
- Fallback to direct service creation when middleware unavailable

Architecture:
- Primary: Uses middleware-based service injection (no decorators)
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
from typing import List, Optional, Union, cast
from pathlib import Path
from googleapiclient.http import MediaIoBaseUpload

from fastmcp import FastMCP
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from auth.service_helpers import request_service, get_injected_service, get_service
from auth.context import get_user_email_context
from tools.common_types import UserGoogleEmail
from .utils import extract_office_xml_text
from .docs_types import DocsListResponse, DocInfo, CreateDocResponse, EditConfig
from .editing import apply_edit_config

from config.enhanced_logging import setup_logger

logger = setup_logger()


async def search_docs(
    query: str, page_size: int = 10, user_google_email: UserGoogleEmail = None
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
        logger.debug(
            f"[search_docs] Attempting to get injected service with key: {drive_key}"
        )
        drive_service = get_injected_service(drive_key)
        logger.info(
            f"[search_docs] Successfully retrieved injected Drive service for {user_google_email}"
        )
    except RuntimeError as e:
        logger.warning(f"[search_docs] Middleware injection failed: {e}")
        if (
            "not yet fulfilled" in str(e).lower()
            or "service injection" in str(e).lower()
        ):
            logger.info("[search_docs] Falling back to direct service creation")
            try:
                drive_service = await get_service("drive", user_google_email)
                logger.info(
                    f"[search_docs] Successfully created Drive service directly for {user_google_email}"
                )
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(
                    f"[search_docs] Direct service creation also failed: {direct_error}"
                )

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
                elif (
                    "credentials do not contain the necessary fields"
                    in error_str.lower()
                ):
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
            drive_service.files()
            .list(
                q=f"name contains '{escaped_query}' and mimeType='application/vnd.google-apps.document' and trashed=false",
                pageSize=page_size,
                fields="files(id, name, createdTime, modifiedTime, webViewLink)",
            )
            .execute
        )
        files = response.get("files", [])
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
    document_id: str,
    user_google_email: UserGoogleEmail = None,
) -> str:
    """
    Retrieves content of a Google Doc or a Drive file (like .docx) identified by document_id.
    - Native Google Docs: Fetches content via Docs API.
    - Office files (.docx, etc.) stored in Drive: Downloads via Drive API and extracts text.

    Args:
        document_id: The ID of the Google Doc or Drive file
        user_google_email: The user's Google email address

    Returns:
        str: The document content with metadata header.
    """
    logger.info(
        f"[get_doc_content] Document/File ID: '{document_id}' for user '{user_google_email}'"
    )

    # Request both Drive and Docs services through middleware
    drive_key = request_service("drive")
    docs_key = request_service("docs")

    # Get Drive service with fallback
    try:
        drive_service = get_injected_service(drive_key)
        logger.info(
            f"[get_doc_content] Successfully retrieved injected Drive service for {user_google_email}"
        )
    except RuntimeError as e:
        logger.warning(f"[get_doc_content] Drive middleware injection failed: {e}")
        if (
            "not yet fulfilled" in str(e).lower()
            or "service injection" in str(e).lower()
        ):
            logger.info(
                "[get_doc_content] Falling back to direct drive service creation"
            )
            try:
                drive_service = await get_service("drive", user_google_email)
                logger.info(
                    f"[get_doc_content] Successfully created Drive service directly for {user_google_email}"
                )
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(
                    f"[get_doc_content] Direct drive service creation also failed: {direct_error}"
                )

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
                elif (
                    "credentials do not contain the necessary fields"
                    in error_str.lower()
                ):
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
        logger.info(
            f"[get_doc_content] Successfully retrieved injected Docs service for {user_google_email}"
        )
    except RuntimeError as e:
        logger.warning(f"[get_doc_content] Docs middleware injection failed: {e}")
        if (
            "not yet fulfilled" in str(e).lower()
            or "service injection" in str(e).lower()
        ):
            logger.info(
                "[get_doc_content] Falling back to direct docs service creation"
            )
            try:
                docs_service = await get_service("docs", user_google_email)
                logger.info(
                    f"[get_doc_content] Successfully created Docs service directly for {user_google_email}"
                )
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(
                    f"[get_doc_content] Direct docs service creation also failed: {direct_error}"
                )

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
                elif (
                    "credentials do not contain the necessary fields"
                    in error_str.lower()
                ):
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
            drive_service.files()
            .get(fileId=document_id, fields="id, name, mimeType, webViewLink")
            .execute
        )
        mime_type = file_metadata.get("mimeType", "")
        file_name = file_metadata.get("name", "Unknown File")
        web_view_link = file_metadata.get("webViewLink", "#")

        logger.info(
            f"[get_doc_content] File '{file_name}' (ID: {document_id}) has mimeType: '{mime_type}'"
        )

        body_text = ""  # Initialize body_text

        # Process based on mimeType
        if mime_type == "application/vnd.google-apps.document":
            logger.info(f"[get_doc_content] Processing as native Google Doc.")
            doc_data = await asyncio.to_thread(
                docs_service.documents().get(documentId=document_id).execute
            )
            body_elements = doc_data.get("body", {}).get("content", [])

            processed_text_lines: List[str] = []
            for element in body_elements:
                if "paragraph" in element:
                    paragraph = element.get("paragraph", {})
                    para_elements = paragraph.get("elements", [])
                    current_line_text = ""
                    for pe in para_elements:
                        text_run = pe.get("textRun", {})
                        if text_run and "content" in text_run:
                            current_line_text += text_run["content"]
                    if current_line_text.strip():
                        processed_text_lines.append(current_line_text)
            body_text = "".join(processed_text_lines)
        else:
            logger.info(
                f"[get_doc_content] Processing as Drive file (e.g., .docx, other). MimeType: {mime_type}"
            )

            export_mime_type_map = {
                # Example: "application/vnd.google-apps.spreadsheet": "text/csv",
                # Native GSuite types that are not Docs would go here if this function
                # was intended to export them. For .docx, direct download is used.
            }
            effective_export_mime = export_mime_type_map.get(mime_type)

            request_obj = (
                drive_service.files().export_media(
                    fileId=document_id, mimeType=effective_export_mime
                )
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
            f"Link: {web_view_link}\n\n--- CONTENT ---\n"
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
    folder_id: str = "root",
    page_size: int = 100,
    user_google_email: UserGoogleEmail = None,
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
    logger.info(
        f"[list_docs_in_folder] Email: '{user_google_email}', Folder ID: '{folder_id}'"
    )

    # Request Drive service through middleware
    logger.debug(
        f"[list_docs_in_folder] Requesting drive service for {user_google_email}"
    )
    drive_key = request_service("drive")
    logger.debug(f"[list_docs_in_folder] Got service key: {drive_key}")

    try:
        logger.debug(
            f"[list_docs_in_folder] Attempting to get injected service with key: {drive_key}"
        )
        drive_service = get_injected_service(drive_key)
        logger.info(
            f"[list_docs_in_folder] Successfully retrieved injected Drive service for {user_google_email}"
        )
    except RuntimeError as e:
        logger.warning(f"[list_docs_in_folder] Middleware injection failed: {e}")
        if (
            "not yet fulfilled" in str(e).lower()
            or "service injection" in str(e).lower()
        ):
            logger.info("[list_docs_in_folder] Falling back to direct service creation")
            try:
                drive_service = await get_service("drive", user_google_email)
                logger.info(
                    f"[list_docs_in_folder] Successfully created Drive service directly for {user_google_email}"
                )
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(
                    f"[list_docs_in_folder] Direct service creation also failed: {direct_error}"
                )

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
                elif (
                    "credentials do not contain the necessary fields"
                    in error_str.lower()
                ):
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
                    userEmail=user_google_email or "",
                    error=error_msg,
                )
        else:
            logger.error(f"[list_docs_in_folder] Unexpected RuntimeError: {e}")
            raise

    try:
        rsp = await asyncio.to_thread(
            drive_service.files()
            .list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document' and trashed=false",
                pageSize=page_size,
                fields="files(id, name, modifiedTime, webViewLink)",
            )
            .execute
        )
        items = rsp.get("files", [])

        # Build structured response
        docs: List[DocInfo] = []
        for file in items:
            doc_info = DocInfo(
                id=file.get("id", ""),
                name=file.get("name", "Unknown"),
                modifiedTime=file.get("modifiedTime"),
                webViewLink=file.get("webViewLink"),
            )
            docs.append(doc_info)

        return DocsListResponse(
            docs=docs,
            count=len(docs),
            folderId=folder_id,
            folderName="root" if folder_id == "root" else None,
            userEmail=user_google_email or "",
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
            userEmail=user_google_email or "",
            error=error_msg,
        )
    except Exception as e:
        logger.error(f"Unexpected error in list_docs_in_folder: {e}", exc_info=True)
        return DocsListResponse(
            docs=[],
            count=0,
            folderId=folder_id,
            folderName=None,
            userEmail=user_google_email or "",
            error=f"Unexpected error: {str(e)}",
        )


def detect_content_type(content: Union[str, bytes]) -> tuple[str, str]:
    """
    Enhanced detection of content type based on content patterns and structure.

    Args:
        content: The content (string or bytes) to analyze

    Returns:
        tuple: (detected_type, suggested_mime_type)
            - detected_type: 'html', 'markdown', 'rtf', 'docx', 'plain', etc.
            - suggested_mime_type: The MIME type to use for upload
    """
    # Handle bytes content (binary files)
    if isinstance(content, bytes):
        # Check for DOCX (ZIP signature with specific structure)
        if content.startswith(b"PK\x03\x04"):
            return (
                "docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        # Check for RTF
        if content.startswith(b"{\\rtf"):
            return "rtf", "application/rtf"
        # Check for PDF
        if content.startswith(b"%PDF"):
            return "pdf", "application/pdf"
        # Try to decode as text
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            return "binary", "application/octet-stream"

    # Type guard: At this point, content must be str (bytes have been decoded or returned early)
    assert isinstance(content, str), "Content should be str at this point"

    # Check for HTML (more comprehensive patterns)
    if re.search(
        r"<!DOCTYPE\s+html|<html[\s>]|<head[\s>]|<body[\s>]|<h[1-6][\s>]|<p[\s>]|<div[\s>]|<span[\s>]|<table[\s>]|<strong[\s>]|<em[\s>]|<ul[\s>]|<ol[\s>]|<li[\s>]|<a\s+href=|<img\s+src=",
        content,
        re.IGNORECASE,
    ):
        return "html", "text/html"

    # Check for Markdown (comprehensive patterns)
    markdown_patterns = [
        r"^#{1,6}\s+",  # Headers
        r"\*\*[^*]+\*\*",  # Bold
        r"\*[^*]+\*",  # Italic
        r"!\[.*?\]\(.*?\)",  # Images
        r"\[.*?\]\(.*?\)",  # Links
        r"^[\*\-+]\s+",  # Unordered lists
        r"^\d+\.\s+",  # Ordered lists
        r"^>\s+",  # Blockquotes
        r"```[\s\S]*?```",  # Code blocks
        r"`[^`]+`",  # Inline code
        r"^\|.*\|.*\|",  # Tables
        r"^---+$",  # Horizontal rules
    ]

    if any(re.search(pattern, content, re.MULTILINE) for pattern in markdown_patterns):
        return "markdown", "text/markdown"

    # Check for RTF text format
    if content.startswith("{\\rtf"):
        return "rtf", "application/rtf"

    # Check for LaTeX
    if re.search(
        r"\\documentclass|\\begin\{document\}|\\section\{|\\subsection\{", content
    ):
        return "latex", "text/x-latex"

    # Default to plain text
    return "plain", "text/plain"


def markdown_to_html(markdown_content: str) -> str:
    """
    Enhanced Markdown to HTML converter with support for more markdown features.

    Args:
        markdown_content: Markdown content string

    Returns:
        str: HTML content with proper formatting
    """
    html = markdown_content

    # Convert code blocks first (to protect them from other conversions)
    code_blocks = []

    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f"<!--CODE_BLOCK_{len(code_blocks)-1}-->"

    html = re.sub(r"```[\s\S]*?```", save_code_block, html)
    html = re.sub(r"`[^`]+`", save_code_block, html)

    # Convert headers (h1-h6)
    for level in range(6, 0, -1):
        pattern = r"^" + "#" * level + r"\s+(.+)$"
        html = re.sub(pattern, f"<h{level}>\\1</h{level}>", html, flags=re.MULTILINE)

    # Convert bold and italic (handle nested cases)
    html = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", html)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(r"__(.+?)__", r"<strong>\1</strong>", html)
    html = re.sub(r"_(.+?)_", r"<em>\1</em>", html)

    # Convert links and images
    html = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1" />', html)
    html = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)

    # Convert blockquotes
    lines = html.split("\n")
    result_lines = []
    in_blockquote = False

    for line in lines:
        if line.startswith("> "):
            if not in_blockquote:
                result_lines.append("<blockquote>")
                in_blockquote = True
            result_lines.append(line[2:])
        else:
            if in_blockquote:
                result_lines.append("</blockquote>")
                in_blockquote = False
            result_lines.append(line)

    if in_blockquote:
        result_lines.append("</blockquote>")

    html = "\n".join(result_lines)

    # Convert lists (both ordered and unordered)
    lines = html.split("\n")
    result_lines = []
    in_ul = False
    in_ol = False

    for line in lines:
        # Unordered list
        if re.match(r"^[\*\-+]\s+", line):
            if not in_ul:
                if in_ol:
                    result_lines.append("</ol>")
                    in_ol = False
                result_lines.append("<ul>")
                in_ul = True
            item_text = re.sub(r"^[\*\-+]\s+", "", line)
            result_lines.append(f"<li>{item_text}</li>")
        # Ordered list
        elif re.match(r"^\d+\.\s+", line):
            if not in_ol:
                if in_ul:
                    result_lines.append("</ul>")
                    in_ul = False
                result_lines.append("<ol>")
                in_ol = True
            item_text = re.sub(r"^\d+\.\s+", "", line)
            result_lines.append(f"<li>{item_text}</li>")
        else:
            if in_ul:
                result_lines.append("</ul>")
                in_ul = False
            if in_ol:
                result_lines.append("</ol>")
                in_ol = False
            result_lines.append(line)

    if in_ul:
        result_lines.append("</ul>")
    if in_ol:
        result_lines.append("</ol>")

    html = "\n".join(result_lines)

    # Convert horizontal rules
    html = re.sub(r"^---+$", "<hr />", html, flags=re.MULTILINE)
    html = re.sub(r"^\*\*\*+$", "<hr />", html, flags=re.MULTILINE)

    # Restore code blocks
    for i, code_block in enumerate(code_blocks):
        if code_block.startswith("```"):
            # Fenced code block
            code_content = code_block[3:-3].strip()
            if "\n" in code_content:
                lang_line, code = code_content.split("\n", 1)
                html = html.replace(
                    f"<!--CODE_BLOCK_{i}-->", f"<pre><code>{code}</code></pre>"
                )
            else:
                html = html.replace(
                    f"<!--CODE_BLOCK_{i}-->", f"<pre><code>{code_content}</code></pre>"
                )
        else:
            # Inline code
            code_content = code_block[1:-1]
            html = html.replace(
                f"<!--CODE_BLOCK_{i}-->", f"<code>{code_content}</code>"
            )

    # Wrap non-HTML lines in paragraphs
    lines = html.split("\n")
    result_lines = []
    for line in lines:
        if line.strip() and not re.match(r"^<[^>]+>", line.strip()):
            result_lines.append(f"<p>{line}</p>")
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


async def create_doc(
    title: str,
    content: Union[str, bytes] = "",
    user_google_email: UserGoogleEmail = None,
    content_mime_type: Optional[str] = None,
    document_id: Optional[str] = None,
    edit_config: Optional[EditConfig] = None,
) -> CreateDocResponse:
    """
    Creates a new Google Doc or edits an existing one with support for multiple content formats and rich formatting.

    This enhanced function can either:
    1. Create a new Google Doc using Drive API's automatic conversion feature
    2. Edit an existing Google Doc with granular control via EditConfig

    Editing Modes (via edit_config parameter):
    - replace_all: Replace entire document content (default)
    - insert_at_line: Insert content at a specific line number
    - regex_replace: Apply regex search and replace operations
    - append: Append content to the end of the document

    Supported content formats:
    - Plain text: Direct conversion to Google Doc
    - Markdown: Converted to HTML then to Google Doc with formatting preserved
    - HTML: Direct upload with automatic conversion to Google Doc format
    - RTF: Rich Text Format documents converted to Google Docs
    - DOCX: Word documents converted to Google Docs
    - LaTeX: LaTeX documents converted via HTML to Google Docs
    - PDF: Uploaded as-is (not converted, but viewable in Drive)
    - Any other MIME type: Attempted conversion based on Drive's capabilities

    The function leverages Google's built-in conversion capabilities and MediaIoBaseUpload
    for flexible content handling. It automatically detects content type if not specified.

    Args:
        title: Title for the new document (or new title for existing document when editing)
        content: Content (string or bytes) to insert into the document
        user_google_email: The user's Google email address
        content_mime_type: Optional MIME type override. If not provided, auto-detected
        document_id: Optional document ID. If provided, edits the existing document instead of creating a new one
        edit_config: Optional EditConfig for granular editing control (insert_at_line, regex_replace, append)

    Returns:
        CreateDocResponse: Structured response with document details and metadata
    """
    logger.info(
        f"[create_doc] Email: '{user_google_email}', Title='{title}', Content size: {len(content) if content else 0}, Document ID: {document_id or 'None (creating new)'}"
    )

    # If editing an existing document, handle it differently
    if document_id:
        logger.info(f"[create_doc] Editing existing document: {document_id}")

        # Get both Docs and Drive services
        docs_key = request_service("docs")
        drive_key = request_service("drive")

        # Get Docs service
        try:
            docs_service = get_injected_service(docs_key)
            logger.info(f"[create_doc] Using injected Docs service for editing")
        except RuntimeError as e:
            logger.warning(f"[create_doc] Docs middleware injection failed: {e}")
            if (
                "not yet fulfilled" in str(e).lower()
                or "service injection" in str(e).lower()
            ):
                docs_service = await get_service("docs", user_google_email)
                logger.info(f"[create_doc] Using direct Docs service for editing")
            else:
                raise

        # Get Drive service
        try:
            drive_service = get_injected_service(drive_key)
            logger.info(f"[create_doc] Using injected Drive service for editing")
        except RuntimeError as e:
            logger.warning(f"[create_doc] Drive middleware injection failed: {e}")
            if (
                "not yet fulfilled" in str(e).lower()
                or "service injection" in str(e).lower()
            ):
                drive_service = await get_service("drive", user_google_email)
                logger.info(f"[create_doc] Using direct Drive service for editing")
            else:
                raise

        try:
            # Get document info first
            doc = await asyncio.to_thread(
                docs_service.documents().get(documentId=document_id).execute
            )
            current_title = doc.get("title", "Unknown")

            # Prepare content for insertion
            detected_type = "unknown"
            upload_mime_type = "text/plain"
            has_formatting = False
            edit_message = "No content changes"

            if content or edit_config:
                # Detect or use provided content type
                if content_mime_type:
                    detected_type = (
                        content_mime_type.split("/")[-1]
                        if "/" in content_mime_type
                        else content_mime_type
                    )
                    upload_mime_type = content_mime_type
                else:
                    detected_type, upload_mime_type = detect_content_type(content)

                # Process content based on type - convert to plain text for editing
                text_content = ""
                if detected_type == "markdown":
                    # Ensure string type
                    if isinstance(content, bytes):
                        content_text = content.decode("utf-8")
                    else:
                        content_text = cast(str, content)
                    # For editing, use plain text from markdown
                    text_content = content_text
                    has_formatting = True
                elif detected_type == "html":
                    # Strip HTML tags for plain text insertion
                    if isinstance(content, bytes):
                        content_text = content.decode("utf-8")
                    else:
                        content_text = cast(str, content)
                    text_content = re.sub(r"<[^>]+>", "", content_text)
                    has_formatting = True
                else:
                    # Plain text
                    if isinstance(content, bytes):
                        text_content = content.decode("utf-8", errors="replace")
                    else:
                        text_content = cast(str, content)

                # Use EditConfig if provided, otherwise default to replace_all
                if not edit_config:
                    edit_config = EditConfig(mode="replace_all")

                # Apply the edit configuration
                try:
                    requests, edit_message = await apply_edit_config(
                        docs_service, document_id, text_content, edit_config, doc
                    )
                except ValueError as ve:
                    logger.error(f"[create_doc] EditConfig validation error: {ve}")
                    return CreateDocResponse(
                        docId=document_id,
                        docName=title,
                        webViewLink="",
                        mimeType="",
                        sourceContentType=detected_type,
                        uploadMimeType=upload_mime_type,
                        userEmail=user_google_email or "",
                        success=False,
                        message="",
                        error=f"Invalid edit configuration: {str(ve)}",
                    )

                # Update the document
                await asyncio.to_thread(
                    docs_service.documents()
                    .batchUpdate(documentId=document_id, body={"requests": requests})
                    .execute
                )

                logger.info(
                    f"[create_doc] Successfully updated document: {edit_message}"
                )

            # Update title if different
            if title and title != current_title:
                await asyncio.to_thread(
                    drive_service.files()
                    .update(fileId=document_id, body={"name": title})
                    .execute
                )
                logger.info(f"[create_doc] Updated document title to: {title}")

            # Get updated file metadata
            file_metadata = await asyncio.to_thread(
                drive_service.files()
                .get(fileId=document_id, fields="id,name,webViewLink,mimeType")
                .execute
            )

            return CreateDocResponse(
                docId=document_id,
                docName=file_metadata.get("name", title),
                webViewLink=file_metadata.get(
                    "webViewLink",
                    f"https://docs.google.com/document/d/{document_id}/edit",
                ),
                mimeType=file_metadata.get(
                    "mimeType", "application/vnd.google-apps.document"
                ),
                sourceContentType=detected_type,
                uploadMimeType=upload_mime_type,
                userEmail=user_google_email or "",
                success=True,
                message=f"Successfully edited Google Doc '{file_metadata.get('name', title)}': {edit_message}",
                contentLength=len(content) if content else 0,
                hasFormatting=has_formatting,
            )

        except HttpError as e:
            logger.error(f"Google API error editing document: {e}")
            error_msg = ""
            if e.resp.status == 401:
                error_msg = (
                    "Authentication failed. Please check your Google credentials."
                )
            elif e.resp.status == 403:
                error_msg = "Permission denied. Make sure you have edit access to this document."
            elif e.resp.status == 404:
                error_msg = f"Document not found: {document_id}"
            else:
                error_msg = f"Error editing document: {str(e)}"

            return CreateDocResponse(
                docId=document_id,
                docName=title,
                webViewLink="",
                mimeType="",
                sourceContentType="unknown",
                uploadMimeType="",
                userEmail=user_google_email or "",
                success=False,
                message="",
                error=error_msg,
            )
        except Exception as e:
            logger.error(f"Unexpected error editing document: {e}", exc_info=True)
            return CreateDocResponse(
                docId=document_id,
                docName=title,
                webViewLink="",
                mimeType="",
                sourceContentType="unknown",
                uploadMimeType="",
                userEmail=user_google_email or "",
                success=False,
                message="",
                error=f"Unexpected error: {str(e)}",
            )

    # Handle empty content case for new documents
    if not content:
        docs_key = request_service("docs")

        try:
            docs_service = get_injected_service(docs_key)
            logger.info(f"[create_doc] Using injected Docs service for empty doc")
        except RuntimeError as e:
            logger.warning(f"[create_doc] Docs middleware injection failed: {e}")
            if (
                "not yet fulfilled" in str(e).lower()
                or "service injection" in str(e).lower()
            ):
                docs_service = await get_service("docs", user_google_email)
                logger.info(f"[create_doc] Using direct Docs service for empty doc")
            else:
                raise

        try:
            doc = await asyncio.to_thread(
                docs_service.documents().create(body={"title": title}).execute
            )
            doc_id = doc.get("documentId")
            link = f"https://docs.google.com/document/d/{doc_id}/edit"

            return CreateDocResponse(
                docId=doc_id,
                docName=title,
                webViewLink=link,
                mimeType="application/vnd.google-apps.document",
                sourceContentType="empty",
                uploadMimeType="none",
                userEmail=user_google_email or "",
                success=True,
                message=f"Created empty Google Doc '{title}'",
                contentLength=0,
                hasFormatting=False,
            )
        except HttpError as e:
            logger.error(f"Google API error creating empty doc: {e}")
            error_msg = (
                "Authentication failed"
                if e.resp.status == 401
                else (
                    "Permission denied"
                    if e.resp.status == 403
                    else f"Error creating document: {str(e)}"
                )
            )
            return CreateDocResponse(
                docId="",
                docName=title,
                webViewLink="",
                mimeType="",
                sourceContentType="empty",
                uploadMimeType="none",
                userEmail=user_google_email or "",
                success=False,
                message="",
                error=error_msg,
            )

    # Get Drive service for content upload
    drive_key = request_service("drive")

    try:
        drive_service = get_injected_service(drive_key)
        logger.info(f"[create_doc] Using injected Drive service for content conversion")
    except RuntimeError as e:
        logger.warning(f"[create_doc] Drive middleware injection failed: {e}")
        if (
            "not yet fulfilled" in str(e).lower()
            or "service injection" in str(e).lower()
        ):
            logger.info("[create_doc] Falling back to direct drive service creation")
            try:
                drive_service = await get_service("drive", user_google_email)
                logger.info(
                    f"[create_doc] Using direct Drive service for content conversion"
                )
            except Exception as direct_error:
                error_str = str(direct_error)
                logger.error(
                    f"[create_doc] Direct drive service creation failed: {direct_error}"
                )

                error_msg = ""
                if "no valid credentials found" in error_str.lower():
                    error_msg = (
                        f"No authentication credentials found for {user_google_email}"
                    )
                elif (
                    "credentials do not contain the necessary fields"
                    in error_str.lower()
                ):
                    error_msg = (
                        f"Invalid or corrupted credentials for {user_google_email}"
                    )
                else:
                    error_msg = f"Authentication error: {error_str}"

                return CreateDocResponse(
                    docId="",
                    docName=title,
                    webViewLink="",
                    mimeType="",
                    sourceContentType="unknown",
                    uploadMimeType="",
                    userEmail=user_google_email or "",
                    success=False,
                    message="",
                    error=error_msg,
                )
        else:
            logger.error(f"[create_doc] Unexpected RuntimeError: {e}")
            raise

    try:
        # Detect or use provided content type
        if content_mime_type:
            # Use provided MIME type
            detected_type = (
                content_mime_type.split("/")[-1]
                if "/" in content_mime_type
                else content_mime_type
            )
            upload_mime_type = content_mime_type
            logger.info(f"[create_doc] Using provided MIME type: {content_mime_type}")
        else:
            # Auto-detect content type
            detected_type, upload_mime_type = detect_content_type(content)
            logger.info(
                f"[create_doc] Detected content type: {detected_type}, MIME: {upload_mime_type}"
            )

        # Prepare content for upload
        content_bytes = None
        has_formatting = False

        if detected_type == "markdown":
            # Convert markdown to HTML for better formatting
            if isinstance(content, bytes):
                md_text = content.decode("utf-8")
            else:
                md_text = cast(str, content)
            html_content = markdown_to_html(md_text)
            content_bytes = html_content.encode("utf-8")
            upload_mime_type = "text/html"
            has_formatting = True
            logger.info("[create_doc] Converted markdown to HTML")

        elif detected_type == "html":
            # HTML content - use as-is
            if isinstance(content, str):
                content_bytes = content.encode("utf-8")
            else:
                content_bytes = content
            has_formatting = True

        elif detected_type == "latex":
            # Convert LaTeX to HTML (basic conversion)
            if isinstance(content, bytes):
                latex_text = content.decode("utf-8")
            else:
                latex_text = cast(str, content)
            # Basic LaTeX to HTML conversion (can be enhanced)
            html_content = latex_text.replace("\\section{", "<h2>").replace(
                "}", "</h2>"
            )
            html_content = html_content.replace("\\subsection{", "<h3>").replace(
                "}", "</h3>"
            )
            html_content = f"<html><body>{html_content}</body></html>"
            content_bytes = html_content.encode("utf-8")
            upload_mime_type = "text/html"
            has_formatting = True

        elif detected_type in ["docx", "rtf", "pdf", "binary"]:
            # Binary content - use as-is
            if isinstance(content, str):
                content_bytes = content.encode("utf-8")
            else:
                content_bytes = content
            has_formatting = detected_type != "binary"

        else:
            # Plain text or unknown - wrap in basic HTML for better display
            if isinstance(content, bytes):
                plain_text = content.decode("utf-8", errors="replace")
            else:
                plain_text = cast(str, content)
            # Escape HTML characters
            plain_text = (
                plain_text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            # Convert newlines to paragraphs
            paragraphs = plain_text.split("\n\n")
            html_content = "".join(
                f'<p>{p.replace(chr(10), "<br>")}</p>' for p in paragraphs if p.strip()
            )
            content_bytes = html_content.encode("utf-8")
            upload_mime_type = "text/html"

        # Create file metadata for Google Docs conversion
        file_metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",  # Target: Google Doc
        }

        # Create media upload object with the appropriate MIME type
        media_body = MediaIoBaseUpload(
            io.BytesIO(content_bytes),
            mimetype=upload_mime_type,
            resumable=len(content_bytes)
            > 5 * 1024 * 1024,  # Use resumable for files > 5MB
        )

        # Upload and convert to Google Doc
        logger.info(
            f"[create_doc] Uploading with MIME type: {upload_mime_type}, Size: {len(content_bytes)} bytes"
        )
        file = await asyncio.to_thread(
            drive_service.files()
            .create(
                body=file_metadata,
                media_body=media_body,
                fields="id,name,webViewLink,mimeType",
            )
            .execute
        )

        doc_id = file.get("id")
        doc_name = file.get("name")
        web_link = file.get("webViewLink")
        final_mime = file.get("mimeType", "application/vnd.google-apps.document")

        logger.info(
            f"Successfully created Google Doc: {doc_id} with {detected_type} content"
        )

        return CreateDocResponse(
            docId=doc_id,
            docName=doc_name,
            webViewLink=web_link,
            mimeType=final_mime,
            sourceContentType=detected_type,
            uploadMimeType=upload_mime_type,
            userEmail=user_google_email or "",
            success=True,
            message=f"Created Google Doc '{doc_name}' with {detected_type} formatting",
            contentLength=len(content_bytes),
            hasFormatting=has_formatting,
        )

    except HttpError as e:
        logger.error(f"Google API error in create_doc: {e}")
        error_msg = ""
        if e.resp.status == 401:
            error_msg = "Authentication failed. Please check your Google credentials."
        elif e.resp.status == 403:
            error_msg = (
                "Permission denied. Make sure you have permission to create documents."
            )
        elif e.resp.status == 400:
            error_msg = f"Invalid request. The content may not be supported for conversion: {str(e)}"
        else:
            error_msg = f"Error creating document: {str(e)}"

        return CreateDocResponse(
            docId="",
            docName=title,
            webViewLink="",
            mimeType="",
            sourceContentType="unknown",
            uploadMimeType="",
            userEmail=user_google_email or "",
            success=False,
            message="",
            error=error_msg,
        )

    except Exception as e:
        logger.error(f"Unexpected error in create_doc: {e}", exc_info=True)
        return CreateDocResponse(
            docId="",
            docName=title,
            webViewLink="",
            mimeType="",
            sourceContentType="unknown",
            uploadMimeType="",
            userEmail=user_google_email or "",
            success=False,
            message="",
            error=f"Unexpected error: {str(e)}",
        )


def setup_docs_tools(mcp: FastMCP):
    """
    Register all Google Docs tools with the FastMCP server.

    Args:
        mcp: The FastMCP server instance
    """

    @mcp.tool(
        name="search_docs", description="Search for Google Docs by name using Drive API"
    )
    async def search_docs_tool(
        query: str, page_size: int = 10, user_google_email: UserGoogleEmail = None
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
            "openWorldHint": True,
        },
    )
    async def get_doc_content_tool(
        document_id: str, user_google_email: UserGoogleEmail = None
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
            "openWorldHint": True,
        },
    )
    async def list_docs_in_folder_tool(
        folder_id: str = "root",
        page_size: int = 100,
        user_google_email: UserGoogleEmail = None,
    ) -> DocsListResponse:
        """List Google Docs within a specific folder."""
        return await list_docs_in_folder(folder_id, page_size, user_google_email)

    @mcp.tool(
        name="create_doc",
        description="Create a new Google Doc or edit an existing one with support for multiple content formats and advanced editing modes. Supports replace_all, insert_at_line, regex_replace, and append modes via edit_config parameter. Accepts plain text, Markdown, HTML, RTF, DOCX, LaTeX formats with automatic detection. Returns structured response with document metadata.",
        tags={
            "docs",
            "create",
            "edit",
            "update",
            "google",
            "markdown",
            "html",
            "formatting",
            "docx",
            "rtf",
            "convert",
            "regex",
            "advanced",
        },
        annotations={
            "title": "Create or Edit Google Doc with Advanced Editing Modes",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
            "supportsMultipleFormats": True,
            "supportsEdit": True,
            "supportsAdvancedEditing": True,
        },
    )
    async def create_doc_tool(
        title: str,
        content: Union[str, bytes] = "",
        user_google_email: UserGoogleEmail = None,
        content_mime_type: Optional[str] = None,
        document_id: Optional[str] = None,
        edit_config: Optional[EditConfig] = None,
    ) -> CreateDocResponse:
        """Create a new Google Doc or edit an existing one with advanced editing capabilities.

        Supports:
        - Plain text, Markdown, HTML for rich formatting
        - RTF, DOCX for document conversion
        - LaTeX for academic documents
        - Custom MIME types via content_mime_type parameter
        - Binary content as bytes
        - Advanced editing modes: replace_all, insert_at_line, regex_replace, append

        Edit Modes (via edit_config):
        - replace_all: Replace entire document (default)
        - insert_at_line: Insert at specific line number
        - regex_replace: Apply regex search/replace operations
        - append: Append to end of document

        Returns structured response with document ID, link, and metadata.
        """
        return await create_doc(
            title,
            content,
            user_google_email,
            content_mime_type,
            document_id,
            edit_config,
        )

    logger.info("Google Docs tools registered successfully")
