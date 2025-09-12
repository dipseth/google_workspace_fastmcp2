"""
Gmail label management tools for FastMCP2.

This module provides tools for:
- Listing Gmail labels
- Creating new labels with colors
- Updating existing labels
- Deleting labels
- Modifying message labels
"""

import logging
import asyncio
import json
import re
from typing_extensions import Optional, Literal, Any, List, Dict, Union, Annotated
from pydantic import Field
from functools import lru_cache


from fastmcp import FastMCP
from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest

from .service import _get_gmail_service_with_fallback
from .utils import _validate_gmail_color, _format_label_color_info, GMAIL_LABEL_COLORS
from .gmail_types import (
    GmailLabelInfo, GmailLabelsResponse, ManageGmailLabelResponse, 
    ModifyGmailMessageLabelsResponse
)
from tools.common_types import UserGoogleEmail


logger = logging.getLogger(__name__)

# Constants
MAX_BATCH_SIZE = 50

# Color name mappings - moved to module level for performance
COLOR_NAME_MAP = {
    # Basic colors
    "red": "#ff0000", "green": "#00ff00", "blue": "#0000ff",
    "yellow": "#ffff00", "cyan": "#00ffff", "magenta": "#ff00ff",
    "black": "#000000", "white": "#ffffff", "gray": "#808080", "grey": "#808080",
    
    # Extended colors
    "orange": "#ffa500", "pink": "#ffc0cb", "purple": "#800080", "brown": "#a52a2a",
    "navy": "#000080", "teal": "#008080", "olive": "#808000", "maroon": "#800000",
    "lime": "#00ff00", "aqua": "#00ffff", "fuchsia": "#ff00ff", "silver": "#c0c0c0",
    
    # Light colors
    "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3", "lightblue": "#add8e6",
    "lightgreen": "#90ee90", "lightpink": "#ffb6c1", "lightyellow": "#ffffe0",
    "lightcyan": "#e0ffff", "lightcoral": "#f08080",
    
    # Dark colors
    "darkgray": "#a9a9a9", "darkgrey": "#a9a9a9", "darkblue": "#00008b",
    "darkgreen": "#006400", "darkred": "#8b0000", "darkorange": "#ff8c00",
    "darkviolet": "#9400d3", "darkcyan": "#008b8b"
}

# Compiled regex for hex color validation (performance optimization)
HEX_COLOR_PATTERN = re.compile(r'^#?([A-Fa-f0-9]{3}|[A-Fa-f0-9]{6})$')

# Type aliases for complex types
LabelParam = Union[str, List[str]]
ColorParam = Union[str, List[Optional[str]], Dict[str, Optional[str]]]
VisibilityParam = Union[str, List[str], Dict[str, str]]


def _validate_json_structure(value: Any, expected_type: type, field_name: str) -> Any:
    """
    Validate JSON structure and return parsed value or raise ValidationError.

    Args:
        value: The value to validate
        expected_type: Expected type (list, dict, etc.)
        field_name: Name of the field for error messages

    Returns:
        Validated and parsed value

    Raises:
        ValueError: If validation fails
    """
    if value is None:
        return None

    # If the value is already the expected type, return it directly
    if isinstance(value, expected_type):
        return value

    # If it's a string and we expect string, check if it might be JSON
    if isinstance(value, str) and str in (expected_type if isinstance(expected_type, tuple) else (expected_type,)):
        # For simple strings that don't look like JSON, return as-is
        if not (value.startswith(('{', '[', '"')) or value in ('true', 'false', 'null')):
            return value
        
        # Try to parse as JSON if it looks like JSON
        try:
            parsed = json.loads(value)
            if isinstance(parsed, expected_type):
                return parsed
            else:
                # If JSON parsing succeeded but type doesn't match, fall back to original string
                return value
        except json.JSONDecodeError:
            # If JSON parsing fails, return the original string
            return value
    
    # If it's a string and we need to try parsing it as JSON for other types
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {field_name}: {e}. Expected valid JSON string.")
    else:
        parsed = value

    if not isinstance(parsed, expected_type):
        raise ValueError(f"Invalid type for {field_name}: expected {expected_type.__name__}, got {type(parsed).__name__}")

    return parsed


def _validate_batch_size(items: Union[List, Dict], operation: str) -> None:
    """
    Validate that batch size doesn't exceed maximum limit.

    Args:
        items: List or dict of items to process
        operation: Name of the operation for error messages

    Raises:
        ValueError: If batch size exceeds limit
    """
    size = len(items)
    if size > MAX_BATCH_SIZE:
        raise ValueError(f"Batch size for {operation} exceeds maximum limit of {MAX_BATCH_SIZE}. "
                        f"Requested: {size}, Maximum: {MAX_BATCH_SIZE}")


@lru_cache(maxsize=256)
def _normalize_color_input(color: str) -> str:
    """
    Normalize color input by converting common color names to hex codes.
    Cached for performance with repeated color lookups.
    
    Args:
        color: Color input (hex code, color name, etc.)
    
    Returns:
        str: Normalized hex color code
    
    Raises:
        ValueError: If color input is invalid after all normalization attempts
    """
    if not color or not isinstance(color, str):
        raise ValueError(f"Invalid color input: {color}")
    
    # Strip whitespace and convert to lowercase for lookup
    clean_color = color.strip().lower()
    
    # Check if it's a color name first (most common case)
    if clean_color in COLOR_NAME_MAP:
        return COLOR_NAME_MAP[clean_color]
    
    # Check if it matches hex pattern
    hex_match = HEX_COLOR_PATTERN.match(color.strip())
    if hex_match:
        hex_part = hex_match.group(1)
        
        # Convert 3-char hex to 6-char (#RGB -> #RRGGBB)
        if len(hex_part) == 3:
            hex_part = ''.join(c*2 for c in hex_part)
        
        return f"#{hex_part.lower()}"
    
    # If all normalization fails, raise an error for better debugging
    raise ValueError(f"Unable to normalize color '{color}' - not a valid color name or hex code")


@lru_cache(maxsize=128)
def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """
    Convert hex color to RGB tuple. Cached for performance.
    
    Args:
        hex_color: Hex color string (with or without #)
    
    Returns:
        RGB tuple (r, g, b)
    """
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c*2 for c in hex_color)
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=64)
def _color_distance(color1_rgb: tuple[int, int, int], color2_rgb: tuple[int, int, int]) -> float:
    """
    Calculate Euclidean distance between two RGB colors. Cached for performance.
    
    Args:
        color1_rgb: First RGB color tuple
        color2_rgb: Second RGB color tuple
    
    Returns:
        Euclidean distance between colors
    """
    return sum((c1 - c2) ** 2 for c1, c2 in zip(color1_rgb, color2_rgb)) ** 0.5


def _find_closest_gmail_color(color: str, color_type: str) -> str:
    """
    Find the closest matching Gmail color from the supported color palette.
    
    Args:
        color: Color input (hex code, color name, etc.)
        color_type: Either "text" or "background"
    
    Returns:
        str: Closest matching Gmail color hex code
    
    Raises:
        ValueError: If color_type is invalid
    """
    # Validate color_type early
    if color_type not in ("text", "background"):
        raise ValueError(f"Invalid color_type '{color_type}'. Must be 'text' or 'background'")
    
    # Default fallback colors
    default_color = "#000000" if color_type == "text" else "#ffffff"
    
    try:
        # Normalize the input color first
        normalized_color = _normalize_color_input(color)
        target_rgb = _hex_to_rgb(normalized_color)
        color_key = f"{color_type}_colors"
        
        if color_key not in GMAIL_LABEL_COLORS:
            logger.warning(f"Gmail color palette missing key '{color_key}', using default")
            return default_color
        
        gmail_colors = GMAIL_LABEL_COLORS[color_key]
        if not gmail_colors:
            logger.warning(f"Empty Gmail color palette for '{color_key}', using default")
            return default_color
        
        closest_color = None
        min_distance = float('inf')
        
        for gmail_color in gmail_colors:
            try:
                gmail_rgb = _hex_to_rgb(gmail_color)
                distance = _color_distance(target_rgb, gmail_rgb)
                if distance < min_distance:
                    min_distance = distance
                    closest_color = gmail_color
                    # Early exit for exact match
                    if distance == 0:
                        break
            except (ValueError, TypeError) as e:
                # Log but skip invalid colors in the palette
                logger.debug(f"Skipping invalid Gmail color '{gmail_color}': {e}")
                continue
        
        if closest_color is None:
            logger.warning(f"No valid Gmail colors found in palette for '{color_type}', using default")
            return default_color
            
        return closest_color
    
    except (ValueError, TypeError) as e:
        logger.debug(f"Error finding closest Gmail color for '{color}': {e}")
        return default_color


def _validate_or_fix_gmail_color(color: str, color_type: str) -> tuple[str, bool]:
    """
    Validate Gmail color and return closest match if invalid.
    Optimized with early validation and better error handling.
    
    Args:
        color: Color input to validate (hex code, color name, etc.)
        color_type: Either "text" or "background"
    
    Returns:
        tuple: (corrected_color, was_changed)
            corrected_color: Valid Gmail color (original or closest match)
            was_changed: True if color was changed, False if original was valid
    """
    if not color:
        return ("#000000" if color_type == "text" else "#ffffff"), True
    
    try:
        # Try to normalize first to get consistent format
        normalized_color = _normalize_color_input(color)
        
        # Check if the normalized color is already valid for Gmail
        if _validate_gmail_color(normalized_color, color_type):
            # Return normalized version even if input was valid but not normalized
            return normalized_color, (normalized_color != color)
        else:
            closest_color = _find_closest_gmail_color(color, color_type)
            return closest_color, True
            
    except (ValueError, TypeError) as e:
        logger.debug(f"Color validation error for '{color}': {e}")
        closest_color = _find_closest_gmail_color(color, color_type)
        return closest_color, True


def _safe_get_value_for_index(param: Union[str, List, Dict, None],
                             index: int,
                             dict_key: Any = None) -> Any:
    """
    Safely get value for index from various parameter formats.

    Args:
        param: Parameter value (string, list, dict, or None)
        index: Index for list access or fallback for dict
        dict_key: Key to use for dict access (defaults to index)

    Returns:
        Value for the given index/key or None if not found
    """
    if param is None:
        return None
    elif isinstance(param, dict):
        # Use dict_key if provided, otherwise use index as key
        key = dict_key if dict_key is not None else index
        return param.get(key)
    elif isinstance(param, list):
        # Return item at index if within bounds, otherwise None
        return param[index] if 0 <= index < len(param) else None
    else:
        # Single value applies to all
        return param


def _handle_gmail_api_error(error: Exception, operation: str) -> str:
    """
    Handle Gmail API errors with specific error messages.

    Args:
        error: The exception that occurred
        operation: Name of the operation being performed

    Returns:
        Formatted error message
    """
    if isinstance(error, HttpError):
        status_code = error.resp.status
        error_details = error._get_reason()

        if status_code == 400:
            return f"❌ Bad Request in {operation}: {error_details}. Please check your parameters."
        elif status_code == 401:
            return f"❌ Authentication Error in {operation}: {error_details}. Please check your credentials."
        elif status_code == 403:
            return f"❌ Permission Denied in {operation}: {error_details}. Please check your Gmail API permissions."
        elif status_code == 404:
            return f"❌ Not Found in {operation}: {error_details}. The requested resource may not exist."
        elif status_code == 409:
            return f"❌ Conflict in {operation}: {error_details}. The resource may already exist or be in use."
        elif status_code >= 500:
            return f"❌ Gmail API Server Error in {operation}: {error_details}. Please try again later."
        else:
            return f"❌ Gmail API Error in {operation} (Status {status_code}): {error_details}"
    else:
        logger.error(f"Unexpected error in {operation}: {error}")
        return f"❌ Unexpected error in {operation}: {error}"

# user_google_email: UserGoogleEmail = None,,

async def list_gmail_labels( user_google_email: UserGoogleEmail = None,) -> GmailLabelsResponse:
    """
    Lists all labels in the user's Gmail account with structured output.

    Args:
        user_google_email: The user's Google email address. If None, uses the current
                          authenticated user from FastMCP context (auto-injected by middleware).

    Returns:
        GmailLabelsResponse: Structured response containing all labels with metadata

    Example:
        >>> # Use current authenticated user (auto-resolved by middleware)
        >>> result = await list_gmail_labels()
        >>> print(f"Found {result['total_count']} labels")
        
        >>> # Specify a particular user
        >>> result = await list_gmail_labels("user@example.com")
        >>> for label in result['system_labels']:
        ...     print(f"System: {label['name']} (ID: {label['id']})")
        >>> for label in result['user_labels']:
        ...     print(f"User: {label['name']} (ID: {label['id']})")
    """
    # The middleware should have auto-injected user_google_email if not provided
    if user_google_email is None:
        error_msg = (
            "❌ No user email provided and middleware did not auto-inject user context. "
            "Please ensure you're authenticated via FastMCP GoogleProvider, JWT token, "
            "or have valid stored credentials."
        )
        logger.error(error_msg)
        return GmailLabelsResponse(
            labels=[],
            total_count=0,
            system_labels=[],
            user_labels=[],
            error=error_msg
        )
    
    logger.info(f"[list_gmail_labels] Email: '{user_google_email}'")

    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        # First, get the basic list of labels
        response = await asyncio.to_thread(
            gmail_service.users().labels().list(userId="me").execute
        )
        labels_data = response.get("labels", [])

        # Use batch requests to efficiently get detailed info for all labels
        # Reduced batch size to avoid rate limiting (Gmail has concurrent request limits)
        BATCH_SIZE = 50  # Reduced from 100 to avoid rate limits
        
        # Store label details indexed by ID for fast lookup
        label_details = {}
        failed_count = 0
        
        # Helper function to handle batch responses
        def batch_callback(request_id, response, exception):
            """Callback for batch request responses."""
            nonlocal failed_count
            if exception is not None:
                logger.warning(f"Failed to get details for label {request_id}: {exception}")
                failed_count += 1
            elif isinstance(response, dict):
                # Only store valid dictionary responses
                label_details[request_id] = response
            else:
                # Log unexpected response type but don't store it
                logger.warning(f"Unexpected response type for label {request_id}: {type(response)} - {response}")
                failed_count += 1
        
        # Process labels in batches with delays to avoid rate limiting
        for i in range(0, len(labels_data), BATCH_SIZE):
            batch = gmail_service.new_batch_http_request()
            batch_labels = labels_data[i:i + BATCH_SIZE]
            
            # Reset failed count for this batch
            failed_count = 0
            
            for label_data in batch_labels:
                label_id = label_data.get("id", "")
                if label_id:
                    # Add label get request to batch
                    request = gmail_service.users().labels().get(userId="me", id=label_id)
                    batch.add(request, callback=batch_callback, request_id=label_id)
            
            # Execute the batch request
            try:
                await asyncio.to_thread(batch.execute)
                logger.info(f"Batch request completed for {len(batch_labels)} labels ({failed_count} failed)")
                
                # Add delay between batches to avoid rate limiting
                # Use adaptive delay: longer if we had failures, shorter if all succeeded
                if i + BATCH_SIZE < len(labels_data):  # Don't delay after the last batch
                    if failed_count > 0:
                        # Longer delay if we had failures (100ms per failure, max 500ms)
                        delay = min(0.1 * failed_count, 0.5)
                        logger.debug(f"Adding {delay:.3f}s delay due to {failed_count} failures")
                    else:
                        # Standard 50ms delay between successful batches
                        delay = 0.05
                        logger.debug(f"Adding standard {delay:.3f}s delay between batches")
                    await asyncio.sleep(delay)
                    
            except Exception as batch_error:
                logger.error(f"Batch request error: {batch_error}")
                # Continue processing even if batch partially fails
                # Add longer delay after error
                if i + BATCH_SIZE < len(labels_data):
                    await asyncio.sleep(0.5)  # 500ms delay after error
        
        # Convert to structured format with detailed info from batch responses
        all_labels: List[GmailLabelInfo] = []
        system_labels: List[GmailLabelInfo] = []
        user_labels: List[GmailLabelInfo] = []

        for label_data in labels_data:
            label_id = label_data.get("id", "")
            
            # Use detailed data from batch response if available, otherwise use basic data
            if label_id in label_details:
                detailed_label = label_details[label_id]
                # Additional safety check to ensure it's a dictionary (should be guaranteed by batch_callback fix)
                if isinstance(detailed_label, dict):
                    label_info: GmailLabelInfo = {
                        "id": detailed_label.get("id", ""),
                        "name": detailed_label.get("name", ""),
                        "type": detailed_label.get("type", "user"),
                        "messageListVisibility": detailed_label.get("messageListVisibility"),
                        "labelListVisibility": detailed_label.get("labelListVisibility"),
                        "color": detailed_label.get("color"),
                        "messagesTotal": detailed_label.get("messagesTotal"),
                        "messagesUnread": detailed_label.get("messagesUnread"),
                        "threadsTotal": detailed_label.get("threadsTotal"),
                        "threadsUnread": detailed_label.get("threadsUnread")
                    }
                else:
                    # This should not happen anymore due to batch_callback fix, but adding as extra safety
                    logger.warning(f"Invalid detailed_label type for {label_id}: {type(detailed_label)}, falling back to basic info")
                    # Fallback to basic info if detailed response is not a dict
                    label_info: GmailLabelInfo = {
                        "id": label_id,
                        "name": label_data.get("name", ""),
                        "type": label_data.get("type", "user"),
                        "messageListVisibility": label_data.get("messageListVisibility"),
                        "labelListVisibility": label_data.get("labelListVisibility"),
                        "color": label_data.get("color"),
                        "messagesTotal": None,  # Not available without detailed info
                        "messagesUnread": None,  # Not available without detailed info
                        "threadsTotal": None,  # Not available without detailed info
                        "threadsUnread": None  # Not available without detailed info
                    }
            else:
                # Fallback to basic info if batch request failed for this label
                label_info: GmailLabelInfo = {
                    "id": label_id,
                    "name": label_data.get("name", ""),
                    "type": label_data.get("type", "user"),
                    "messageListVisibility": label_data.get("messageListVisibility"),
                    "labelListVisibility": label_data.get("labelListVisibility"),
                    "color": label_data.get("color"),
                    "messagesTotal": None,  # Not available without detailed info
                    "messagesUnread": None,  # Not available without detailed info
                    "threadsTotal": None,  # Not available without detailed info
                    "threadsUnread": None  # Not available without detailed info
                }
            
            all_labels.append(label_info)
            
            if label_info["type"] == "system":
                system_labels.append(label_info)
            else:
                user_labels.append(label_info)

        logger.info(f"Found {len(all_labels)} labels for {user_google_email} (with unread counts for {len(label_details)} labels)")

        return GmailLabelsResponse(
            labels=all_labels,
            total_count=len(all_labels),
            system_labels=system_labels,
            user_labels=user_labels,
            error=None  # Explicitly set to None when no error
        )

    except Exception as e:
        # Log the error but return an empty structured response with error message
        logger.error(f"Error in list_gmail_labels: {e}")
        error_msg = _handle_gmail_api_error(e, "list_gmail_labels")
        logger.error(error_msg)
        
        # Return empty structured response with error message
        return GmailLabelsResponse(
            labels=[],
            total_count=0,
            system_labels=[],
            user_labels=[],
            error=error_msg  # Include the error message
        )


async def manage_gmail_label(
    action: Literal["create", "update", "delete"],
    user_google_email: Optional[str] = None,
    name: Optional[LabelParam] = None,
    label_id: Optional[LabelParam] = None,
    label_list_visibility: VisibilityParam = "labelShow",
    message_list_visibility: VisibilityParam = "show",
    text_color: Optional[ColorParam] = None,
    background_color: Optional[ColorParam] = None
) -> str:
    """
    Manages Gmail labels: create, update, or delete labels. Can handle single or multiple labels.
    
    📋 PARAMETER REQUIREMENTS BY ACTION:
    • CREATE: Requires 'name' parameter (label_id optional)
    • UPDATE: Requires 'label_id' parameter (name optional, other fields optional)
    • DELETE: Requires 'label_id' parameter (all other fields ignored)

    Args:
        user_google_email: The user's Google email address
        action: Action to perform - "create", "update", or "delete"
        name: Label name(s) - REQUIRED for CREATE, optional for UPDATE/DELETE
            Single: "My Label"
            Multiple: ["Label1", "Label2"] or '["Label1", "Label2"]'
        label_id: Label ID(s) - REQUIRED for UPDATE/DELETE, optional for CREATE
            Single: "Label_123"
            Multiple: ["Label_1", "Label_2"] or '["Label_1", "Label_2"]'
        label_list_visibility: Label visibility in Gmail sidebar ("labelShow"/"labelHide")
        message_list_visibility: Message visibility in conversations ("show"/"hide")
        text_color: Text color(s) - hex codes, auto-corrected to closest Gmail color
            Single: "#ff0000" (applied to all)
            Multiple: ["#ff0000", "#00ff00"] or {"Label_1": "#ff0000"}
        background_color: Background color(s) - hex codes, auto-corrected to closest Gmail color
            Single: "#ffffff" (applied to all)
            Multiple: ["#ffffff", "#000000"] or {"Label_1": "#ffffff"}

    Returns:
        str: Confirmation message with operation results and any color adjustments

    Examples:
        # CREATE - Single label with auto color correction
        >>> manage_gmail_label("user@example.com", "create", name="Work", text_color="#00ff00")
        # Result: Creates label + shows "⚠️ Text color '#00ff00' adjusted to '#16a766'"
        
        # CREATE - Multiple labels
        >>> manage_gmail_label("user@example.com", "create",
        ...     name=["Work", "Personal", "Projects"])
        
        # UPDATE - Single label (label_id required)
        >>> manage_gmail_label("user@example.com", "update",
        ...     label_id="Label_123", name="Updated Work", text_color="#ff0000")
        
        # UPDATE - Multiple labels with different colors
        >>> manage_gmail_label("user@example.com", "update",
        ...     label_id=["Label_1", "Label_2"],
        ...     text_color=["#ff0000", "#00ff00"])  # Per-label colors
        
        # DELETE - Single label (only label_id needed)
        >>> manage_gmail_label("user@example.com", "delete", label_id="Label_123")
        
        # DELETE - Multiple labels
        >>> manage_gmail_label("user@example.com", "delete",
        ...     label_id=["Label_1", "Label_2", "Label_3"])

    Note: Invalid colors are automatically corrected to the nearest Gmail color with a warning.
    """
    # The middleware should have auto-injected user_google_email if not provided
    if user_google_email is None:
        error_msg = (
            "❌ No user email provided and middleware did not auto-inject user context. "
            "Please ensure you're authenticated via FastMCP GoogleProvider, JWT token, "
            "or have valid stored credentials."
        )
        logger.error(error_msg)
        return error_msg
    
    logger.info(f"[manage_gmail_label] Email: '{user_google_email}', Action: '{action}'")

    try:
        # Parse and validate parameters with improved error handling
        parsed_name = _validate_json_structure(name, (str, list), "name") if name else None
        parsed_label_id = _validate_json_structure(label_id, (str, list), "label_id") if label_id else None
        parsed_label_list_visibility = _validate_json_structure(label_list_visibility, (str, list, dict), "label_list_visibility") if label_list_visibility != "labelShow" else "labelShow"
        parsed_message_list_visibility = _validate_json_structure(message_list_visibility, (str, list, dict), "message_list_visibility") if message_list_visibility != "show" else "show"
        parsed_text_color = _validate_json_structure(text_color, (str, list, dict), "text_color") if text_color else None
        parsed_background_color = _validate_json_structure(background_color, (str, list, dict), "background_color") if background_color else None

        # Determine if we're handling multiple labels
        # For create: check if name is a list
        # For update/delete: check if label_id is a list
        if action == "create":
            is_multiple = isinstance(parsed_name, list)
        else:
            is_multiple = isinstance(parsed_label_id, list)

        if is_multiple:
            # Validate batch size based on the primary parameter
            if action == "create":
                _validate_batch_size(parsed_name, f"manage_gmail_label ({action})")
                primary_list = parsed_name
            else:
                _validate_batch_size(parsed_label_id, f"manage_gmail_label ({action})")
                primary_list = parsed_label_id

            results = []

            for i, primary_item in enumerate(primary_list):
                # Get parameters for this specific label using safe helper
                current_name = _safe_get_value_for_index(parsed_name, i, primary_item)
                current_label_id = _safe_get_value_for_index(parsed_label_id, i, primary_item)
                current_label_list_vis = _safe_get_value_for_index(parsed_label_list_visibility, i, primary_item) or "labelShow"
                current_message_list_vis = _safe_get_value_for_index(parsed_message_list_visibility, i, primary_item) or "show"
                current_text_color = _safe_get_value_for_index(parsed_text_color, i, primary_item)
                current_bg_color = _safe_get_value_for_index(parsed_background_color, i, primary_item)

                # Validate requirements for this label
                if action == "create" and not current_name:
                    results.append(f"❌ Label name is required for create action (index {i}).")
                    continue

                if action in ["update", "delete"] and not current_label_id:
                    results.append(f"❌ Label ID is required for {action} action (index {i}).")
                    continue

                # Validate and fix colors if provided - with enhanced error handling
                color_warnings = []
                if current_text_color:
                    try:
                        corrected_color, was_changed = _validate_or_fix_gmail_color(current_text_color, "text")
                        if was_changed:
                            color_warnings.append(f"⚠️  Text color '{current_text_color}' was adjusted to closest Gmail color '{corrected_color}'")
                        current_text_color = corrected_color
                    except Exception as e:
                        logger.warning(f"Text color validation failed for '{current_text_color}': {e}")
                        current_text_color = "#000000"  # Safe fallback
                        color_warnings.append(f"⚠️  Text color '{current_text_color}' was invalid, using default black")

                if current_bg_color:
                    try:
                        corrected_color, was_changed = _validate_or_fix_gmail_color(current_bg_color, "background")
                        if was_changed:
                            color_warnings.append(f"⚠️  Background color '{current_bg_color}' was adjusted to closest Gmail color '{corrected_color}'")
                        current_bg_color = corrected_color
                    except Exception as e:
                        logger.warning(f"Background color validation failed for '{current_bg_color}': {e}")
                        current_bg_color = "#ffffff"  # Safe fallback
                        color_warnings.append(f"⚠️  Background color '{current_bg_color}' was invalid, using default white")

                # Process this individual label
                try:
                    result = await _process_single_label(
                        user_google_email, action, current_name, current_label_id,
                        current_label_list_vis, current_message_list_vis,
                        current_text_color, current_bg_color, primary_item
                    )
                    
                    # Add color warnings if any
                    if color_warnings:
                        result = result + "\n" + "\n".join(color_warnings)
                    
                    results.append(result)
                except Exception as e:
                    error_msg = _handle_gmail_api_error(e, f"process label '{current_name or current_label_id}'")
                    results.append(error_msg)

            return "\n\n".join(results)

        else:
            # Handle single label (original logic)
            if action == "create" and not parsed_name:
                return "❌ Label name is required for create action."

            if action in ["update", "delete"] and not parsed_label_id:
                return f"❌ Label ID is required for {action} action. Please specify which label to {action}."

            # Validate and fix colors if provided - with enhanced error handling
            color_warnings = []
            if parsed_text_color:
                try:
                    corrected_color, was_changed = _validate_or_fix_gmail_color(parsed_text_color, "text")
                    if was_changed:
                        color_warnings.append(f"⚠️  Text color '{parsed_text_color}' was adjusted to closest Gmail color '{corrected_color}'")
                    parsed_text_color = corrected_color
                except Exception as e:
                    logger.warning(f"Text color validation failed for '{parsed_text_color}': {e}")
                    parsed_text_color = "#000000"  # Safe fallback
                    color_warnings.append(f"⚠️  Text color '{parsed_text_color}' was invalid, using default black")

            if parsed_background_color:
                try:
                    corrected_color, was_changed = _validate_or_fix_gmail_color(parsed_background_color, "background")
                    if was_changed:
                        color_warnings.append(f"⚠️  Background color '{parsed_background_color}' was adjusted to closest Gmail color '{corrected_color}'")
                    parsed_background_color = corrected_color
                except Exception as e:
                    logger.warning(f"Background color validation failed for '{parsed_background_color}': {e}")
                    parsed_background_color = "#ffffff"  # Safe fallback
                    color_warnings.append(f"⚠️  Background color '{parsed_background_color}' was invalid, using default white")

            result_message = await _process_single_label(
                user_google_email, action, parsed_name, parsed_label_id,
                parsed_label_list_visibility, parsed_message_list_visibility,
                parsed_text_color, parsed_background_color
            )
            
            # Add color warnings to the result message if any
            if color_warnings:
                result_message = result_message + "\n" + "\n".join(color_warnings)
            
            return result_message

    except ValueError as e:
        # Handle validation errors
        logger.error(f"Validation error in manage_gmail_label: {e}")
        return f"❌ Validation error in manage_gmail_label: {str(e)}"
    except Exception as e:
        error_msg = _handle_gmail_api_error(e, "manage_gmail_label")
        return error_msg


async def _process_single_label(
    user_google_email: str,
    action: str,
    name: Optional[str],
    label_id: Optional[str],
    label_list_visibility: str,
    message_list_visibility: str,
    text_color: Optional[str],
    background_color: Optional[str],
    index: Optional[Any] = None
) -> str:
    """
    Helper function to process a single label operation.

    Args:
        user_google_email: User's email address
        action: Action to perform ("create", "update", "delete")
        name: Label name
        label_id: Label ID
        label_list_visibility: Label list visibility setting
        message_list_visibility: Message list visibility setting
        text_color: Text color (optional)
        background_color: Background color (optional)
        index: Index or label ID for batch operations (optional)

    Returns:
        str: Formatted result message
    """
    try:
        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        index_prefix = f"[Label {index}] " if index is not None else ""

        if action == "create":
            label_object = {
                "name": name,
                "labelListVisibility": label_list_visibility,
                "messageListVisibility": message_list_visibility,
            }

            # Add color information if provided
            if text_color or background_color:
                color_obj = {}
                if text_color:
                    color_obj["textColor"] = text_color
                if background_color:
                    color_obj["backgroundColor"] = background_color
                label_object["color"] = color_obj

            created_label = await asyncio.to_thread(
                gmail_service.users().labels().create(userId="me", body=label_object).execute
            )

            # Format response with color information
            response_lines = [
                f"✅ {index_prefix}Label created successfully!",
                f"Name: {created_label['name']}",
                f"ID: {created_label['id']}"
            ]

            if created_label.get("color"):
                color_info = _format_label_color_info(created_label["color"])
                response_lines.append(f"Colors: {color_info}")

            return "\n".join(response_lines)

        elif action == "update":
            current_label = await asyncio.to_thread(
                gmail_service.users().labels().get(userId="me", id=label_id).execute
            )

            label_object = {
                "id": label_id,
                "name": name if name is not None else current_label["name"],
                "labelListVisibility": label_list_visibility,
                "messageListVisibility": message_list_visibility,
            }

            # Handle color updates
            if text_color or background_color:
                # Get existing colors or create new color object
                existing_color = current_label.get("color", {})
                color_obj = {}

                # Use provided colors or keep existing ones
                if text_color:
                    color_obj["textColor"] = text_color
                elif existing_color.get("textColor"):
                    color_obj["textColor"] = existing_color["textColor"]

                if background_color:
                    color_obj["backgroundColor"] = background_color
                elif existing_color.get("backgroundColor"):
                    color_obj["backgroundColor"] = existing_color["backgroundColor"]

                label_object["color"] = color_obj

            updated_label = await asyncio.to_thread(
                gmail_service.users().labels().update(userId="me", id=label_id, body=label_object).execute
            )

            # Format response with color information
            response_lines = [
                f"✅ {index_prefix}Label updated successfully!",
                f"Name: {updated_label['name']}",
                f"ID: {updated_label['id']}"
            ]

            if updated_label.get("color"):
                color_info = _format_label_color_info(updated_label["color"])
                response_lines.append(f"Colors: {color_info}")

            return "\n".join(response_lines)

        elif action == "delete":
            label = await asyncio.to_thread(
                gmail_service.users().labels().get(userId="me", id=label_id).execute
            )
            label_name = label["name"]

            await asyncio.to_thread(
                gmail_service.users().labels().delete(userId="me", id=label_id).execute
            )
            return f"✅ {index_prefix}Label '{label_name}' (ID: {label_id}) deleted successfully!"

        else:
            raise ValueError(f"Unsupported action: {action}")

    except Exception as e:
        raise  # Re-raise to be handled by caller


async def modify_gmail_message_labels(
    message_id: str,
    user_google_email: Optional[str] = None,
    add_label_ids: Optional[Any] = None,
    remove_label_ids: Optional[Any] = None
) -> ModifyGmailMessageLabelsResponse:
    """
    Adds or removes labels from a Gmail message.

    Args:
        user_google_email: The user's Google email address
        message_id: The ID of the message to modify
        add_label_ids: List of label IDs to add to the message (can be list or JSON string)
            Examples: ["Label_1", "Label_2"] or '["Label_1", "Label_2"]' or "Label_1"
        remove_label_ids: List of label IDs to remove from the message (can be list or JSON string)
            Examples: ["Label_3"] or '["Label_3"]' or "Label_3"

    Returns:
        str: Confirmation message of the label changes applied to the message

    Examples:
        # Add labels using list
        >>> await modify_gmail_message_labels("user@example.com", "msg123",
        ...     add_label_ids=["Label_1", "Label_2"])

        # Add labels using JSON string
        >>> await modify_gmail_message_labels("user@example.com", "msg123",
        ...     add_label_ids='["Label_1", "Label_2"]')

        # Remove labels and add new ones
        >>> await modify_gmail_message_labels("user@example.com", "msg123",
        ...     add_label_ids=["Important"], remove_label_ids=["Spam"])
    """
    # The middleware should have auto-injected user_google_email if not provided
    if user_google_email is None:
        error_msg = (
            "❌ No user email provided and middleware did not auto-inject user context. "
            "Please ensure you're authenticated via FastMCP GoogleProvider, JWT token, "
            "or have valid stored credentials."
        )
        logger.error(error_msg)
        return ModifyGmailMessageLabelsResponse(
            success=False,
            message_id=message_id,
            labels_added=[],
            labels_removed=[],
            userEmail="unknown",
            error=error_msg
        )
    
    logger.info(f"[modify_gmail_message_labels] Email: '{user_google_email}', Message ID: '{message_id}'")
    logger.info(f"[modify_gmail_message_labels] Raw add_label_ids: {add_label_ids} (type: {type(add_label_ids)})")
    logger.info(f"[modify_gmail_message_labels] Raw remove_label_ids: {remove_label_ids} (type: {type(remove_label_ids)})")

    try:
        # Helper function to parse label IDs (handles both list and JSON string formats)
        def parse_label_ids(label_ids: Any) -> Optional[List[str]]:
            if not label_ids:
                return None

            # If it's already a list, validate and return it
            if isinstance(label_ids, list):
                if not all(isinstance(item, str) for item in label_ids):
                    raise ValueError("All label IDs in list must be strings")
                return label_ids

            # If it's a string, try to parse as JSON
            if isinstance(label_ids, str):
                try:
                    parsed = json.loads(label_ids)
                    if isinstance(parsed, list):
                        if not all(isinstance(item, str) for item in parsed):
                            raise ValueError("All parsed label IDs must be strings")
                        return parsed
                    elif isinstance(parsed, str):
                        # Single string wrapped in quotes
                        return [parsed]
                    else:
                        raise ValueError(f"Invalid JSON structure for label_ids: expected string or list, got {type(parsed).__name__}")
                except json.JSONDecodeError as e:
                    # Not valid JSON, treat as single label ID
                    return [label_ids]

            raise ValueError(f"Invalid type for label_ids: expected string or list, got {type(label_ids).__name__}")

        # Parse the label ID parameters
        parsed_add_label_ids = parse_label_ids(add_label_ids)
        parsed_remove_label_ids = parse_label_ids(remove_label_ids)

        logger.info(f"[modify_gmail_message_labels] Parsed add_label_ids: {parsed_add_label_ids}")
        logger.info(f"[modify_gmail_message_labels] Parsed remove_label_ids: {parsed_remove_label_ids}")

        if not parsed_add_label_ids and not parsed_remove_label_ids:
            return ModifyGmailMessageLabelsResponse(
                success=False,
                message_id=message_id,
                labels_added=[],
                labels_removed=[],
                userEmail=user_google_email,
                error="At least one of add_label_ids or remove_label_ids must be provided."
            )

        # Validate batch size for label operations
        if parsed_add_label_ids:
            _validate_batch_size(parsed_add_label_ids, "add message labels")
        if parsed_remove_label_ids:
            _validate_batch_size(parsed_remove_label_ids, "remove message labels")

        gmail_service = await _get_gmail_service_with_fallback(user_google_email)

        body = {}
        if parsed_add_label_ids:
            body["addLabelIds"] = parsed_add_label_ids
        if parsed_remove_label_ids:
            body["removeLabelIds"] = parsed_remove_label_ids

        await asyncio.to_thread(
            gmail_service.users().messages().modify(userId="me", id=message_id, body=body).execute
        )

        actions = []
        if parsed_add_label_ids:
            actions.append(f"Added labels: {', '.join(parsed_add_label_ids)}")
        if parsed_remove_label_ids:
            actions.append(f"Removed labels: {', '.join(parsed_remove_label_ids)}")

        return ModifyGmailMessageLabelsResponse(
            success=True,
            message_id=message_id,
            labels_added=parsed_add_label_ids or [],
            labels_removed=parsed_remove_label_ids or [],
            userEmail=user_google_email
        )

    except ValueError as e:
        logger.error(f"Validation error in modify_gmail_message_labels: {e}")
        return ModifyGmailMessageLabelsResponse(
            success=False,
            message_id=message_id,
            labels_added=[],
            labels_removed=[],
            userEmail=user_google_email or "unknown",
            error=str(e)
        )
    except Exception as e:
        error_msg = _handle_gmail_api_error(e, "modify_gmail_message_labels")
        return ModifyGmailMessageLabelsResponse(
            success=False,
            message_id=message_id,
            labels_added=[],
            labels_removed=[],
            userEmail=user_google_email or "unknown",
            error=error_msg
        )


def setup_label_tools(mcp: FastMCP) -> None:
    """Register Gmail label tools with the FastMCP server."""

    @mcp.tool(
        name="list_gmail_labels",
        description="List all labels in the user's Gmail account with structured output (system and user-created)",
        tags={"gmail", "labels", "list", "organize", "structured"},
        annotations={
            "title": "List Gmail Labels",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_gmail_labels_tool(user_google_email: UserGoogleEmail = None,) -> GmailLabelsResponse:
        """
        Lists all Gmail labels with structured output.
        
        Returns both:
        - Traditional content: Human-readable formatted text (automatic via FastMCP)
        - Structured content: Machine-readable JSON with full label details
        
        Args:
            user_google_email: The user's Google email address. If None, uses the current
                             authenticated user from FastMCP context (auto-injected by middleware).
            
        Returns:
            GmailLabelsResponse: Structured response containing all labels with metadata
        """
        return await list_gmail_labels(user_google_email)

    @mcp.tool(
        name="manage_gmail_label",
        description="Manage Gmail labels: create, update, or delete labels. Supports single or multiple label operations using lists or JSON strings.",
        tags={"gmail", "labels", "manage", "create", "update", "delete", "batch", "multiple"},
        annotations={
            "title": "Manage Gmail Label",
            "readOnlyHint": False,
            "destructiveHint": True,  # Can delete labels
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def manage_gmail_label_tool(
        action: Annotated[Literal["create", "update", "delete"], Field(description="Action to perform: 'create' (requires name), 'update' (requires label_id), 'delete' (requires label_id)")],
        user_google_email: UserGoogleEmail = None,
        name: Annotated[Optional[Union[str, List[str]]], Field(description="Label name(s) - REQUIRED for CREATE. Single: 'My Label' or Multiple: ['Label1', 'Label2'] or JSON string")] = None,
        label_id: Annotated[Optional[Union[str, List[str]]], Field(description="Label ID(s) - REQUIRED for UPDATE/DELETE. Single: 'Label_123' or Multiple: ['Label_1', 'Label_2'] or JSON string")] = None,
        label_list_visibility: Annotated[Union[str, List[str]], Field(description="Label visibility in Gmail sidebar: 'labelShow' or 'labelHide'. Can be single value or list for multiple labels")] = "labelShow",
        message_list_visibility: Annotated[Union[str, List[str]], Field(description="Message visibility in conversations: 'show' or 'hide'. Can be single value or list for multiple labels")] = "show",
        text_color: Annotated[Optional[Union[str, List[str], Dict[str, str]]], Field(description="Text color(s) - hex codes (e.g., '#ff0000'), color names (e.g., 'red'), auto-corrected to closest Gmail color. Single value, list, or dict mapping")] = None,
        background_color: Annotated[Optional[Union[str, List[str], Dict[str, str]]], Field(description="Background color(s) - hex codes (e.g., '#ffffff'), color names (e.g., 'white'), auto-corrected to closest Gmail color. Single value, list, or dict mapping")] = None
    ) -> ManageGmailLabelResponse:
        """
        Manage Gmail labels with structured output.
        
        Returns both:
        - Traditional content: Human-readable formatted text with operation results (automatic via FastMCP)
        - Structured content: Machine-readable JSON with detailed label management results
        
        Args:
            action: Action to perform - 'create', 'update', or 'delete'
            user_google_email: The user's Google email address. If None, uses the current
                             authenticated user from FastMCP context (auto-injected by middleware).
            name: Label name(s) for creation or updates
            label_id: Label ID(s) for updates or deletions
            label_list_visibility: Visibility in Gmail label list
            message_list_visibility: Visibility in message conversations
            text_color: Text color(s) with auto-correction to valid Gmail colors
            background_color: Background color(s) with auto-correction to valid Gmail colors
            
        Returns:
            ManageGmailLabelResponse: Structured response with operation results and color adjustments
        """
        return await manage_gmail_label(
            action, user_google_email, name, label_id,
            label_list_visibility, message_list_visibility,
            text_color, background_color
        )

    @mcp.tool(
        name="modify_gmail_message_labels",
        description="Add or remove labels from a Gmail message",
        tags={"gmail", "labels", "modify", "organize", "messages"},
        annotations={
            "title": "Modify Gmail Message Labels",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def modify_gmail_message_labels_tool(
        message_id: Annotated[str, Field(description="The ID of the Gmail message to modify labels for")],
        user_google_email: UserGoogleEmail = None,
        add_label_ids: Annotated[Optional[Union[str, List[str]]], Field(description="Label IDs to add to the message. Single ID: 'Label_123', List: ['Label_1', 'Label_2'], or JSON string")] = None,
        remove_label_ids: Annotated[Optional[Union[str, List[str]]], Field(description="Label IDs to remove from the message. Single ID: 'Label_123', List: ['Label_1', 'Label_2'], or JSON string")] = None
    ) -> ModifyGmailMessageLabelsResponse:
        """
        Modify Gmail message labels with structured output.
        
        Returns both:
        - Traditional content: Human-readable formatted text with label changes (automatic via FastMCP)
        - Structured content: Machine-readable JSON with detailed modification results
        
        Args:
            message_id: The ID of the Gmail message to modify
            user_google_email: The user's Google email address. If None, uses the current
                             authenticated user from FastMCP context (auto-injected by middleware).
            add_label_ids: Label IDs to add (supports single ID, list, or JSON string)
            remove_label_ids: Label IDs to remove (supports single ID, list, or JSON string)
            
        Returns:
            ModifyGmailMessageLabelsResponse: Structured response with detailed modification results
        """
        return await modify_gmail_message_labels(message_id, user_google_email, add_label_ids, remove_label_ids)