"""
Google Slides MCP Tools for FastMCP2.

This module provides MCP tools for interacting with Google Slides API.
Migrated from decorator-based pattern to FastMCP2 architecture.
"""

import logging
import asyncio
import os
import re
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from googleapiclient.errors import HttpError
from fastmcp import FastMCP
import aiohttp
import aiofiles

from auth.service_helpers import get_service, request_service
from auth.context import get_injected_service

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

# Valid thumbnail sizes
VALID_THUMBNAIL_SIZES = {
    "LARGE",
    "MEDIUM", 
    "SMALL"
}

# Valid page types
VALID_PAGE_TYPES = {
    "SLIDE",
    "MASTER",
    "LAYOUT"
}

# Valid shape types for validation
VALID_SHAPE_TYPES = {
    "TEXT_BOX",
    "RECTANGLE",
    "ROUND_RECTANGLE",
    "ELLIPSE",
    "ARC",
    "BENT_ARROW",
    "BENT_UP_ARROW",
    "BEVEL",
    "BLOCK_ARC",
    "BRACE_PAIR",
    "BRACKET_PAIR",
    "CAN",
    "CHEVRON",
    "CHORD",
    "CLOUD",
    "CORNER",
    "CUBE",
    "CURVED_DOWN_ARROW",
    "CURVED_LEFT_ARROW",
    "CURVED_RIGHT_ARROW",
    "CURVED_UP_ARROW",
    "DECAGON",
    "DIAGONAL_STRIPE",
    "DIAMOND",
    "DODECAGON",
    "DONUT",
    "DOUBLE_WAVE",
    "DOWN_ARROW",
    "DOWN_ARROW_CALLOUT",
    "FOLDED_CORNER",
    "FRAME",
    "HALF_FRAME",
    "HEART",
    "HEPTAGON",
    "HEXAGON",
    "HOME_PLATE",
    "HORIZONTAL_SCROLL",
    "IRREGULAR_SEAL_1",
    "IRREGULAR_SEAL_2",
    "LEFT_ARROW",
    "LEFT_ARROW_CALLOUT",
    "LEFT_BRACE",
    "LEFT_BRACKET",
    "LEFT_RIGHT_ARROW",
    "LEFT_RIGHT_ARROW_CALLOUT",
    "LEFT_RIGHT_UP_ARROW",
    "LEFT_UP_ARROW",
    "LIGHTNING_BOLT",
    "MATH_DIVIDE",
    "MATH_EQUAL",
    "MATH_MINUS",
    "MATH_MULTIPLY",
    "MATH_NOT_EQUAL",
    "MATH_PLUS",
    "MOON",
    "NO_SMOKING",
    "NOTCHED_RIGHT_ARROW",
    "OCTAGON",
    "PARALLELOGRAM",
    "PENTAGON",
    "PIE",
    "PLAQUE",
    "PLUS",
    "QUAD_ARROW",
    "QUAD_ARROW_CALLOUT",
    "RIBBON",
    "RIBBON_2",
    "RIGHT_ARROW",
    "RIGHT_ARROW_CALLOUT",
    "RIGHT_BRACE",
    "RIGHT_BRACKET",
    "ROUND_1_RECTANGLE",
    "ROUND_2_DIAGONAL_RECTANGLE",
    "ROUND_2_SAME_RECTANGLE",
    "RIGHT_TRIANGLE",
    "SMILEY_FACE",
    "SNIP_1_RECTANGLE",
    "SNIP_2_DIAGONAL_RECTANGLE",
    "SNIP_2_SAME_RECTANGLE",
    "SNIP_ROUND_RECTANGLE",
    "STAR_10",
    "STAR_12",
    "STAR_16",
    "STAR_24",
    "STAR_32",
    "STAR_4",
    "STAR_5",
    "STAR_6",
    "STAR_7",
    "STAR_8",
    "STRIPED_RIGHT_ARROW",
    "SUN",
    "TRAPEZOID",
    "TRIANGLE",
    "UP_ARROW",
    "UP_ARROW_CALLOUT",
    "UP_DOWN_ARROW",
    "UTURN_ARROW",
    "VERTICAL_SCROLL",
    "WAVE",
    "WEDGE_ELLIPSE_CALLOUT",
    "WEDGE_RECTANGLE_CALLOUT",
    "WEDGE_ROUND_RECTANGLE_CALLOUT"
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_slide_details(slide: Dict[str, Any], index: int) -> str:
    """
    Format a single slide's details for display.
    
    Args:
        slide: Slide dict from Slides API
        index: 1-based index of the slide
        
    Returns:
        Formatted string describing the slide
    """
    slide_id = slide.get("objectId", "Unknown")
    page_elements = slide.get("pageElements", [])
    
    # Count different types of elements
    element_counts = {}
    for element in page_elements:
        if "shape" in element:
            element_counts["shapes"] = element_counts.get("shapes", 0) + 1
        elif "table" in element:
            element_counts["tables"] = element_counts.get("tables", 0) + 1
        elif "line" in element:
            element_counts["lines"] = element_counts.get("lines", 0) + 1
        elif "image" in element:
            element_counts["images"] = element_counts.get("images", 0) + 1
        else:
            element_counts["other"] = element_counts.get("other", 0) + 1
    
    # Build element summary
    element_summary = []
    for elem_type, count in element_counts.items():
        element_summary.append(f"{count} {elem_type}")
    
    element_text = ", ".join(element_summary) if element_summary else "no elements"
    
    return f"  Slide {index}: ID {slide_id}, {len(page_elements)} total elements ({element_text})"


def format_page_element_details(element: Dict[str, Any]) -> str:
    """
    Format a page element's details for display.
    
    Args:
        element: Page element dict from Slides API
        
    Returns:
        Formatted string describing the element
    """
    element_id = element.get("objectId", "Unknown")
    
    if "shape" in element:
        shape = element["shape"]
        shape_type = shape.get("shapeType", "Unknown")
        # Check if shape has text
        text_content = shape.get("text", {})
        has_text = bool(text_content.get("textElements", []))
        text_info = " (with text)" if has_text else ""
        return f"  Shape: ID {element_id}, Type: {shape_type}{text_info}"
    
    elif "table" in element:
        table = element["table"]
        rows = table.get("rows", 0)
        cols = table.get("columns", 0)
        return f"  Table: ID {element_id}, Size: {rows}x{cols}"
    
    elif "line" in element:
        line_type = element["line"].get("lineType", "Unknown")
        return f"  Line: ID {element_id}, Type: {line_type}"
    
    elif "image" in element:
        return f"  Image: ID {element_id}"
    
    elif "video" in element:
        return f"  Video: ID {element_id}"
    
    elif "wordArt" in element:
        return f"  WordArt: ID {element_id}"
    
    elif "sheetsChart" in element:
        return f"  Sheets Chart: ID {element_id}"
    
    else:
        return f"  Element: ID {element_id}, Type: Unknown"


def validate_thumbnail_size(size: str) -> bool:
    """
    Validate thumbnail size parameter.
    
    Args:
        size: Thumbnail size to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    return size in VALID_THUMBNAIL_SIZES


def build_create_slide_request(title: Optional[str] = None, 
                             layout_id: Optional[str] = None,
                             index: Optional[int] = None) -> Dict[str, Any]:
    """
    Build a create slide request for batch update.
    
    Args:
        title: Optional title for the slide
        layout_id: Optional layout ID to use
        index: Optional index to insert the slide at
        
    Returns:
        Create slide request dict
    """
    request = {"createSlide": {}}
    
    if index is not None:
        request["createSlide"]["insertionIndex"] = index
    
    if layout_id:
        request["createSlide"]["slideLayoutReference"] = {
            "layoutId": layout_id
        }
    
    # Note: Title is typically set after creation
    return request


def build_create_shape_request(slide_id: str,
                             shape_type: str = "TEXT_BOX",
                             element_properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Build a create shape request for batch update.
    
    Args:
        slide_id: ID of the slide to add shape to
        shape_type: Type of shape to create
        element_properties: Optional element properties
        
    Returns:
        Create shape request dict
    """
    request = {
        "createShape": {
            "shapeType": shape_type,
            "elementProperties": element_properties or {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": 300, "unit": "PT"},
                    "height": {"magnitude": 100, "unit": "PT"}
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": 100,
                    "translateY": 100,
                    "unit": "PT"
                }
            }
        }
    }
    
    return request


# ============================================================================
# SERVICE HELPER FUNCTIONS  
# ============================================================================

async def _get_slides_service_with_fallback(user_google_email: str):
    """Get Slides service with fallback to direct creation."""
    try:
        return await get_service("slides", user_google_email)
    except Exception as e:
        logger.warning(f"Failed to get Slides service via middleware: {e}")
        logger.info("Falling back to direct service creation")
        return await get_service("slides", user_google_email)


# ============================================================================
# MAIN TOOL FUNCTIONS
# ============================================================================


def setup_slides_tools(mcp: FastMCP) -> None:
    """
    Setup and register all Google Slides tools with the MCP server.
    
    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up Google Slides tools")
    
    @mcp.tool(
        name="create_presentation",
        description="Create a new Google Slides presentation",
        tags={"slides", "create", "google", "presentation"},
        annotations={
            "title": "Create Google Slides Presentation",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_presentation(
        user_google_email: str,
        title: str = "Untitled Presentation"
    ) -> str:
        """
        Create a new Google Slides presentation.

        Args:
            user_google_email (str): The user's Google email address. Required.
            title (str): The title for the new presentation. Defaults to "Untitled Presentation".

        Returns:
            str: Details about the created presentation including ID and URL.
        """
        logger.info(f"[create_presentation] Invoked. Email: '{user_google_email}', Title: '{title}'")

        try:
            # Get the Slides service via middleware injection
            slides_service = await _get_slides_service_with_fallback(user_google_email)
            
            # Build the presentation data
            body = {
                'title': title
            }
            
            # Create the presentation via the API
            result = await asyncio.to_thread(
                slides_service.presentations().create(body=body).execute
            )
            
            presentation_id = result.get('presentationId')
            presentation_url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"
            
            success_msg = (
                f"✅ Presentation Created Successfully for {user_google_email}:\n"
                f"- Title: {title}\n"
                f"- Presentation ID: {presentation_id}\n"
                f"- URL: {presentation_url}\n"
                f"- Slides: {len(result.get('slides', []))} slide(s) created"
            )
            
            logger.info(f"Presentation created successfully for {user_google_email}")
            return success_msg
            
        except HttpError as e:
            error_msg = f"❌ Failed to create presentation: {e}"
            logger.error(f"[create_presentation] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error creating presentation: {str(e)}"
            logger.error(f"[create_presentation] Unexpected error: {e}")
            return error_msg

    @mcp.tool(
        name="get_presentation_info",
        description="Get details about a Google Slides presentation including title, slides count, and metadata",
        tags={"slides", "read", "google", "get", "info"},
        annotations={
            "title": "Get Presentation Information",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_presentation_info(
        user_google_email: str,
        presentation_id: str
    ) -> str:
        """
        Get details about a Google Slides presentation.

        Args:
            user_google_email (str): The user's Google email address. Required.
            presentation_id (str): The ID of the presentation to retrieve.

        Returns:
            str: Details about the presentation including title, slides count, and metadata.
        """
        logger.info(f"[get_presentation_info] Invoked. Email: '{user_google_email}', ID: '{presentation_id}'")

        try:
            slides_service = await _get_slides_service_with_fallback(user_google_email)
            
            # Get the presentation
            result = await asyncio.to_thread(
                slides_service.presentations().get(presentationId=presentation_id).execute
            )
            
            title = result.get('title', 'Untitled')
            slides = result.get('slides', [])
            page_size = result.get('pageSize', {})
            
            # Format slide details
            slides_info = []
            for i, slide in enumerate(slides, 1):
                slides_info.append(format_slide_details(slide, i))
            
            # Build response
            response_parts = [
                f"📊 Presentation Details for {user_google_email}:",
                f"- Title: {title}",
                f"- Presentation ID: {presentation_id}",
                f"- URL: https://docs.google.com/presentation/d/{presentation_id}/edit",
                f"- Total Slides: {len(slides)}",
                f"- Page Size: {page_size.get('width', {}).get('magnitude', 'Unknown')} x {page_size.get('height', {}).get('magnitude', 'Unknown')} {page_size.get('width', {}).get('unit', '')}",
                "",
                "Slides Breakdown:"
            ]
            
            if slides_info:
                response_parts.extend(slides_info)
            else:
                response_parts.append("  No slides found")
            
            return "\n".join(response_parts)
            
        except HttpError as e:
            error_msg = f"❌ Failed to get presentation: {e}"
            logger.error(f"[get_presentation_info] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[get_presentation_info] {error_msg}")
            return error_msg

    @mcp.tool(
        name="add_slide",
        description="Add a new slide to an existing Google Slides presentation",
        tags={"slides", "update", "google", "add"},
        annotations={
            "title": "Add Slide to Presentation",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def add_slide(
        user_google_email: str,
        presentation_id: str,
        layout_id: Optional[str] = None,
        index: Optional[int] = None
    ) -> str:
        """
        Add a new slide to an existing presentation using batch update.

        Args:
            user_google_email (str): The user's Google email address. Required.
            presentation_id (str): The ID of the presentation.
            layout_id (Optional[str]): ID of the layout to use for the new slide.
            index (Optional[int]): Position to insert the slide (0-based). If not specified, appends to end.

        Returns:
            str: Details about the added slide.
        """
        logger.info(f"[add_slide] Invoked. Email: '{user_google_email}', Presentation: '{presentation_id}'")

        try:
            slides_service = await _get_slides_service_with_fallback(user_google_email)
            
            # Build the create slide request
            create_slide_request = build_create_slide_request(
                layout_id=layout_id,
                index=index
            )
            
            # Execute batch update
            body = {
                'requests': [create_slide_request]
            }
            
            result = await asyncio.to_thread(
                slides_service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body=body
                ).execute
            )
            
            # Extract the created slide ID
            replies = result.get('replies', [])
            slide_id = None
            if replies and 'createSlide' in replies[0]:
                slide_id = replies[0]['createSlide'].get('objectId', 'Unknown')
            
            success_msg = (
                f"✅ Successfully added slide to presentation\n"
                f"- Presentation ID: {presentation_id}\n"
                f"- New Slide ID: {slide_id}\n"
                f"- Insertion Index: {index if index is not None else 'End of presentation'}\n"
                f"- Layout ID: {layout_id or 'Default layout'}\n"
                f"- Edit URL: https://docs.google.com/presentation/d/{presentation_id}/edit"
            )
            
            logger.info(f"Slide added successfully for {user_google_email}")
            return success_msg
            
        except HttpError as e:
            error_msg = f"❌ Failed to add slide: {e}"
            logger.error(f"[add_slide] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[add_slide] {error_msg}")
            return error_msg

    @mcp.tool(
        name="update_slide_content",
        description="Update content on a specific slide using batch update operations",
        tags={"slides", "update", "google", "content"},
        annotations={
            "title": "Update Slide Content",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def update_slide_content(
        user_google_email: str,
        presentation_id: str,
        requests: List[Dict[str, Any]]
    ) -> str:
        """
        Apply batch updates to a Google Slides presentation.

        This is a flexible tool that can handle various update operations including:
        - Creating shapes, text boxes, tables, etc.
        - Updating text content
        - Modifying element properties
        - Deleting elements

        Args:
            user_google_email (str): The user's Google email address. Required.
            presentation_id (str): The ID of the presentation to update.
            requests (List[Dict[str, Any]]): List of update requests to apply.

        Returns:
            str: Details about the batch update operation results.
        """
        logger.info(f"[update_slide_content] Invoked. Email: '{user_google_email}', ID: '{presentation_id}', Requests: {len(requests)}")

        try:
            slides_service = await _get_slides_service_with_fallback(user_google_email)
            
            body = {
                'requests': requests
            }
            
            result = await asyncio.to_thread(
                slides_service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body=body
                ).execute
            )
            
            replies = result.get('replies', [])
            
            # Build response message
            response_parts = [
                f"✅ Batch Update Completed for {user_google_email}:",
                f"- Presentation ID: {presentation_id}",
                f"- URL: https://docs.google.com/presentation/d/{presentation_id}/edit",
                f"- Requests Applied: {len(requests)}",
                f"- Replies Received: {len(replies)}"
            ]
            
            if replies:
                response_parts.append("\nUpdate Results:")
                for i, reply in enumerate(replies, 1):
                    if 'createSlide' in reply:
                        slide_id = reply['createSlide'].get('objectId', 'Unknown')
                        response_parts.append(f"  Request {i}: Created slide with ID {slide_id}")
                    elif 'createShape' in reply:
                        shape_id = reply['createShape'].get('objectId', 'Unknown')
                        response_parts.append(f"  Request {i}: Created shape with ID {shape_id}")
                    elif 'createTable' in reply:
                        table_id = reply['createTable'].get('objectId', 'Unknown')
                        response_parts.append(f"  Request {i}: Created table with ID {table_id}")
                    elif 'createImage' in reply:
                        image_id = reply['createImage'].get('objectId', 'Unknown')
                        response_parts.append(f"  Request {i}: Created image with ID {image_id}")
                    else:
                        response_parts.append(f"  Request {i}: Operation completed")
            
            return "\n".join(response_parts)
            
        except HttpError as e:
            error_msg = f"❌ Failed to update slide content: {e}"
            logger.error(f"[update_slide_content] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[update_slide_content] {error_msg}")
            return error_msg

    @mcp.tool(
        name="export_presentation",
        description="Export a Google Slides presentation to various formats (PDF, PPTX, etc.)",
        tags={"slides", "export", "google", "download"},
        annotations={
            "title": "Export Presentation",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def export_presentation(
        user_google_email: str,
        presentation_id: str,
        export_format: str = "PDF"
    ) -> str:
        """
        Export a Google Slides presentation to various formats.

        Note: This generates export URLs. The actual file download would need
        to be handled separately through Drive API or direct download.

        Args:
            user_google_email (str): The user's Google email address. Required.
            presentation_id (str): The ID of the presentation to export.
            export_format (str): Export format - "PDF", "PPTX", "ODP", "TXT", "PNG", "JPEG", "SVG".

        Returns:
            str: Export URL and instructions.
        """
        logger.info(f"[export_presentation] Invoked. Email: '{user_google_email}', ID: '{presentation_id}', Format: '{export_format}'")

        try:
            # Map format strings to export MIME types
            format_mapping = {
                "PDF": "application/pdf",
                "PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "ODP": "application/vnd.oasis.opendocument.presentation",
                "TXT": "text/plain",
                "PNG": "image/png",
                "JPEG": "image/jpeg",
                "SVG": "image/svg+xml"
            }
            
            export_format_upper = export_format.upper()
            if export_format_upper not in format_mapping:
                return f"❌ Invalid export format. Supported formats: {', '.join(format_mapping.keys())}"
            
            # For image formats, we export the first slide
            if export_format_upper in ["PNG", "JPEG", "SVG"]:
                export_url = f"https://docs.google.com/presentation/d/{presentation_id}/export/{export_format_upper.lower()}"
            else:
                mime_type = format_mapping[export_format_upper]
                export_url = f"https://docs.google.com/presentation/d/{presentation_id}/export/{export_format_upper.lower()}"
            
            success_msg = (
                f"✅ Export URL Generated for {user_google_email}:\n"
                f"- Presentation ID: {presentation_id}\n"
                f"- Export Format: {export_format_upper}\n"
                f"- Export URL: {export_url}\n"
                f"- Edit URL: https://docs.google.com/presentation/d/{presentation_id}/edit\n\n"
                f"Note: Use the export URL to download the presentation in {export_format_upper} format."
            )
            
            if export_format_upper in ["PNG", "JPEG", "SVG"]:
                success_msg += f"\n⚠️ For image formats, only the first slide is exported. To export all slides as images, use the get_page_thumbnail tool for each slide."
            
            logger.info(f"Export URL generated successfully for {user_google_email}")
            return success_msg
            
        except Exception as e:
            error_msg = f"❌ Unexpected error generating export URL: {str(e)}"
            logger.error(f"[export_presentation] {error_msg}")
            return error_msg

    @mcp.tool(
        name="get_presentation_file",
        description="Download a Google Slides presentation file to local storage in various formats",
        tags={"slides", "download", "google", "file", "local"},
        annotations={
            "title": "Download Presentation File",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def get_presentation_file(
        user_google_email: str,
        presentation_id: str,
        export_format: str = "PDF",
        download_directory: str = "./downloads/presentations"
    ) -> str:
        """
        Download a Google Slides presentation file to local storage.

        This tool actually downloads presentation files to a local directory instead of
        just providing links, making it usable for working with presentation content locally.

        Args:
            user_google_email (str): The user's Google email address. Required.
            presentation_id (str): The ID of the presentation to download.
            export_format (str): Export format - "PDF", "PPTX", "ODP", "TXT", "PNG", "JPEG", "SVG".
            download_directory (str): Local directory to save the file. Defaults to "./downloads/presentations".

        Returns:
            str: Details about the downloaded file including local path, size, and metadata.
        """
        logger.info(f"[get_presentation_file] Invoked. Email: '{user_google_email}', ID: '{presentation_id}', Format: '{export_format}'")

        try:
            # Validate export format
            format_mapping = {
                "PDF": "application/pdf",
                "PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "ODP": "application/vnd.oasis.opendocument.presentation",
                "TXT": "text/plain",
                "PNG": "image/png",
                "JPEG": "image/jpeg",
                "SVG": "image/svg+xml"
            }
            
            export_format_upper = export_format.upper()
            if export_format_upper not in format_mapping:
                return f"❌ Invalid export format. Supported formats: {', '.join(format_mapping.keys())}"

            # Get the Slides service to fetch presentation info
            slides_service = await _get_slides_service_with_fallback(user_google_email)
            
            # Get presentation details for filename
            presentation_info = await asyncio.to_thread(
                slides_service.presentations().get(presentationId=presentation_id).execute
            )
            
            presentation_title = presentation_info.get('title', 'Untitled_Presentation')
            
            # Get Drive service for file export/download
            drive_service = await get_service("drive", user_google_email)
            
            # Create download directory if it doesn't exist
            os.makedirs(download_directory, exist_ok=True)
            
            # Sanitize filename for filesystem safety
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', presentation_title)
            safe_title = re.sub(r'[^\w\s\-_.]', '_', safe_title)
            safe_title = re.sub(r'\s+', '_', safe_title.strip())
            
            # Generate timestamp for unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Build filename with proper extension
            file_extension = export_format_upper.lower()
            if file_extension == 'jpeg':
                file_extension = 'jpg'
            filename = f"{safe_title}_{timestamp}.{file_extension}"
            local_file_path = os.path.join(download_directory, filename)
            
            # Get the export URL based on format
            if export_format_upper in ["PNG", "JPEG", "SVG"]:
                export_url = f"https://docs.google.com/presentation/d/{presentation_id}/export/{export_format_upper.lower()}"
            else:
                mime_type = format_mapping[export_format_upper]
                export_url = f"https://docs.google.com/presentation/d/{presentation_id}/export/{export_format_upper.lower()}"
            
            # Download the file using Drive API export
            download_start_time = datetime.now()
            
            try:
                # Use Drive API to export and get file content
                if export_format_upper in ["PDF", "PPTX", "ODP", "TXT"]:
                    # Use Drive API export for document formats
                    mime_type = format_mapping[export_format_upper]
                    file_content = await asyncio.to_thread(
                        drive_service.files().export(
                            fileId=presentation_id,
                            mimeType=mime_type
                        ).execute
                    )
                else:
                    # For image formats, use direct download approach
                    async with aiohttp.ClientSession() as session:
                        # Get credentials for authorization
                        credentials = drive_service._http.credentials
                        credentials.refresh(drive_service._http.http.request)
                        
                        headers = {
                            'Authorization': f'Bearer {credentials.token}'
                        }
                        
                        async with session.get(export_url, headers=headers) as response:
                            if response.status == 200:
                                file_content = await response.read()
                            else:
                                raise Exception(f"Failed to download file: HTTP {response.status}")
                
                # Save file to local storage
                async with aiofiles.open(local_file_path, 'wb') as f:
                    if isinstance(file_content, str):
                        await f.write(file_content.encode('utf-8'))
                    else:
                        await f.write(file_content)
                
                download_end_time = datetime.now()
                download_duration = (download_end_time - download_start_time).total_seconds()
                
                # Get file size
                file_size = os.path.getsize(local_file_path)
                file_size_mb = file_size / (1024 * 1024)
                
                # Build success message with comprehensive information
                success_msg = (
                    f"✅ Presentation File Downloaded Successfully for {user_google_email}:\n"
                    f"- Original Title: {presentation_title}\n"
                    f"- Presentation ID: {presentation_id}\n"
                    f"- Export Format: {export_format_upper}\n"
                    f"- Local File Path: {local_file_path}\n"
                    f"- File Size: {file_size:,} bytes ({file_size_mb:.2f} MB)\n"
                    f"- Download Duration: {download_duration:.2f} seconds\n"
                    f"- Download Timestamp: {download_end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"- Edit URL: https://docs.google.com/presentation/d/{presentation_id}/edit\n\n"
                    f"📁 File saved to: {os.path.abspath(local_file_path)}"
                )
                
                if export_format_upper in ["PNG", "JPEG", "SVG"]:
                    success_msg += f"\n⚠️ For image formats, only the first slide is exported. To export all slides as images, use the get_page_thumbnail tool for each slide."
                
                logger.info(f"[get_presentation_file] File downloaded successfully: {local_file_path}")
                return success_msg
                
            except Exception as download_error:
                # Clean up partial file if it exists
                if os.path.exists(local_file_path):
                    try:
                        os.remove(local_file_path)
                    except:
                        pass
                
                error_msg = f"❌ Failed to download presentation file: {str(download_error)}"
                logger.error(f"[get_presentation_file] Download error: {download_error}")
                return error_msg
                
        except HttpError as e:
            error_msg = f"❌ HTTP error accessing presentation: {e}"
            logger.error(f"[get_presentation_file] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error downloading presentation file: {str(e)}"
            logger.error(f"[get_presentation_file] {error_msg}")
            return error_msg
    
    # Log successful setup
    tool_count = 6  # Updated total number of Slides tools
    logger.info(f"Successfully registered {tool_count} Google Slides tools")