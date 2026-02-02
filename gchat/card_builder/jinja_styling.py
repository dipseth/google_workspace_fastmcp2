"""
Jinja styling and style metadata extraction utilities.
"""

import re
from typing import Any, Dict, List, Optional


def extract_style_metadata(text: str) -> Dict[str, List[str]]:
    """
    Extract style information from Jinja expressions in text.

    Analyzes text for Jinja filter usage, colors, semantic styles, and formatting
    to build a style metadata dictionary that can be stored with patterns and
    reapplied to new cards.

    Args:
        text: Text potentially containing Jinja expressions like {{ 'text' | filter }}

    Returns:
        Dict with keys:
        - jinja_filters: All filters used (e.g., ["success_text", "bold"])
        - colors: Hex colors found (e.g., ["#00FF00"])
        - semantic_styles: Semantic style names (e.g., ["success", "error"])
        - formatting: Formatting filters (e.g., ["bold", "italic"])
    """
    metadata: Dict[str, List[str]] = {
        "jinja_filters": [],
        "colors": [],
        "semantic_styles": [],
        "formatting": [],
    }

    if not text:
        return metadata

    # Extract Jinja filter chains: {{ 'text' | filter1 | filter2 }}
    # Matches everything after the first pipe until closing braces
    jinja_pattern = r"\{\{\s*[^|]+\|([^}]+)\}\}"
    for match in re.finditer(jinja_pattern, text):
        filters = [f.strip() for f in match.group(1).split("|")]
        metadata["jinja_filters"].extend(filters)

    # Extract colors: color('#HEX') or color('#hex') or color('success')
    color_pattern = r"color\(['\"]?(#[0-9A-Fa-f]{6})['\"]?\)"
    metadata["colors"] = re.findall(color_pattern, text)

    # Map filters to semantic styles
    SEMANTIC_MAP = {
        "success_text": "success",
        "error_text": "error",
        "warning_text": "warning",
        "info_text": "info",
    }
    for f in metadata["jinja_filters"]:
        if f in SEMANTIC_MAP:
            metadata["semantic_styles"].append(SEMANTIC_MAP[f])

    # Extract formatting filters
    FORMATTING = {"bold", "italic", "strike", "underline"}
    metadata["formatting"] = [f for f in metadata["jinja_filters"] if f in FORMATTING]

    # Deduplicate all lists
    for key in metadata:
        metadata[key] = list(set(metadata[key]))

    return metadata


# =============================================================================
# SEMANTIC COLORS (imported from middleware for consistency)
# =============================================================================

# Default semantic colors for Google Chat HTML
# These can be imported from middleware.filters.styling_filters.SEMANTIC_COLORS
# but we provide defaults here for standalone usage
DEFAULT_SEMANTIC_COLORS = {
    "success": "#34a853",
    "error": "#ea4335",
    "warning": "#fbbc05",
    "info": "#4285f4",
    "muted": "#9aa0a6",
    "primary": "#1a73e8",
}


def apply_styles(
    text: str,
    styles: List[str],
    semantic_colors: Dict[str, str] = None,
) -> str:
    """Apply Content DSL styles to text, generating Google Chat HTML.

    Args:
        text: The text to style
        styles: List of style names (e.g., ["bold", "success"])
        semantic_colors: Optional color mapping (uses defaults if not provided)

    Returns:
        HTML-formatted text for Google Chat

    Example:
        >>> apply_styles("Status", ["bold", "success"])
        '<font color="#34a853"><b>Status</b></font>'
    """
    if semantic_colors is None:
        # Try to import from middleware, fall back to defaults
        try:
            from middleware.filters.styling_filters import SEMANTIC_COLORS
            semantic_colors = SEMANTIC_COLORS
        except ImportError:
            semantic_colors = DEFAULT_SEMANTIC_COLORS

    result = text
    color = None
    is_bold = False
    is_italic = False
    is_strike = False

    for style in styles:
        style_lower = style.lower()

        # Check semantic colors
        if style_lower in semantic_colors:
            color = semantic_colors[style_lower]
        elif style_lower == "bold":
            is_bold = True
        elif style_lower == "italic":
            is_italic = True
        elif style_lower in ("strike", "strikethrough"):
            is_strike = True
        elif style_lower in ("success", "ok", "active"):
            color = semantic_colors.get("success", "#34a853")
        elif style_lower in ("error", "danger", "failed"):
            color = semantic_colors.get("error", "#ea4335")
        elif style_lower in ("warning", "caution", "pending"):
            color = semantic_colors.get("warning", "#fbbc05")
        elif style_lower in ("info", "note", "notice"):
            color = semantic_colors.get("info", "#4285f4")

    # Apply formatting (innermost first)
    if is_strike:
        result = f"<s>{result}</s>"
    if is_italic:
        result = f"<i>{result}</i>"
    if is_bold:
        result = f"<b>{result}</b>"
    if color:
        result = f'<font color="{color}">{result}</font>'

    return result


def style_keyword(
    keyword: str,
    style: str,
    colors: Dict[str, str] = None,
) -> str:
    """Apply HTML styling to a keyword.

    Args:
        keyword: The word to style (e.g., "content", "layout")
        style: Style name (e.g., "bold", "success", "warning", "info", "muted",
               "bold_success", "bold_info")
        colors: Optional color mapping (uses DEFAULT_SEMANTIC_COLORS if not provided)

    Returns:
        Styled HTML string

    Example:
        >>> style_keyword("content", "success")
        '<font color="#34a853">content</font>'
        >>> style_keyword("important", "bold_success")
        '<b><font color="#34a853">important</font></b>'
    """
    if colors is None:
        colors = DEFAULT_SEMANTIC_COLORS

    if style == "bold":
        return f"<b>{keyword}</b>"
    elif style == "success":
        return f'<font color="{colors.get("success", "#34a853")}">{keyword}</font>'
    elif style == "warning":
        return f'<font color="{colors.get("warning", "#fbbc05")}">{keyword}</font>'
    elif style == "info":
        return f'<font color="{colors.get("info", "#4285f4")}">{keyword}</font>'
    elif style == "muted":
        return f'<font color="{colors.get("muted", "#9aa0a6")}">{keyword}</font>'
    elif style == "bold_success":
        return f'<b><font color="{colors.get("success", "#34a853")}">{keyword}</font></b>'
    elif style == "bold_info":
        return f'<b><font color="{colors.get("info", "#4285f4")}">{keyword}</font></b>'
    else:
        return f"<b>{keyword}</b>"  # Default to bold


# =============================================================================
# STYLE APPLICATION (Content-Aware)
# =============================================================================

# Keywords that indicate success status
SUCCESS_KEYWORDS = frozenset([
    "online", "success", "ok", "active", "running", "healthy", "ready", "up",
    "connected", "enabled", "available", "complete", "done"
])

# Keywords that indicate error status
ERROR_KEYWORDS = frozenset([
    "error", "fail", "offline", "down", "unhealthy", "critical", "dead",
    "disconnected", "disabled", "unavailable", "stopped"
])

# Keywords that indicate warning status
WARNING_KEYWORDS = frozenset([
    "warning", "pending", "slow", "degraded", "unknown", "wait", "timeout",
    "retry", "limited"
])


def has_explicit_styles(params: Dict[str, Any]) -> bool:
    """Check if params already have explicit Jinja styles defined.

    Returns True if the 'text' field contains Jinja filter expressions,
    indicating the user has explicitly specified styles for the content.
    """
    text = params.get("text", "")
    if isinstance(text, str) and "{{" in text and "|" in text:
        return True
    return False


def get_style_for_text(
    text: str,
    style_metadata: Dict[str, List[str]],
) -> Optional[str]:
    """Determine which style to apply based on text content and available styles.

    If ANY semantic style is present in the pattern, we enable full semantic
    styling based on content keywords. This allows a single "success" pattern
    to also style "error" and "warning" content appropriately.

    Args:
        text: Text content to analyze
        style_metadata: Style metadata with keys:
            - semantic_styles: ["success", "error", "warning", "info"]

    Returns:
        The Jinja filter name (e.g., "success_text") or None if no match.
    """
    if not text or not isinstance(text, str):
        return None

    semantic_styles = style_metadata.get("semantic_styles", [])
    if not semantic_styles:
        return None

    text_lower = text.lower()

    # If ANY semantic style is present, enable full semantic styling
    enable_all_semantic = len(semantic_styles) > 0

    # Check for success keywords
    if enable_all_semantic or "success" in semantic_styles:
        if any(word in text_lower for word in SUCCESS_KEYWORDS):
            return "success_text"

    # Check for error keywords
    if enable_all_semantic or "error" in semantic_styles:
        if any(word in text_lower for word in ERROR_KEYWORDS):
            return "error_text"

    # Check for warning keywords
    if enable_all_semantic or "warning" in semantic_styles:
        if any(word in text_lower for word in WARNING_KEYWORDS):
            return "warning_text"

    # Info is fallback only if explicitly in semantic_styles
    if "info" in semantic_styles:
        return "info_text"

    return None


def apply_style_to_text(
    text: str,
    style_metadata: Dict[str, List[str]],
) -> str:
    """Apply style to a single text string based on its content.

    Returns styled text with Jinja template if applicable, otherwise original text.
    """
    # Skip if already has Jinja styling
    if "{{" in text and "|" in text:
        return text

    style_to_apply = get_style_for_text(text, style_metadata)
    if not style_to_apply:
        return text

    # Escape single quotes for Jinja template
    escaped_text = text.replace("'", "\\'")
    styled_text = f"{{{{ '{escaped_text}' | {style_to_apply} }}}}"

    # Add formatting filters if present
    formatting = style_metadata.get("formatting", [])
    for fmt in formatting:
        styled_text = styled_text[:-3] + f" | {fmt} }}}}"

    return styled_text


def apply_pattern_styles(
    params: Dict[str, Any],
    style_metadata: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Apply proven styles from a matched pattern to text fields.

    Uses content-aware style selection to determine which semantic style
    to apply based on the text content.

    Args:
        params: Card parameters containing text fields
        style_metadata: Style metadata from matched pattern with keys:
            - semantic_styles: ["success", "error", "warning", "info"]
            - formatting: ["bold", "italic", "strike", "underline"]

    Returns:
        Updated params dict with Jinja styling applied to text field
    """
    semantic_styles = style_metadata.get("semantic_styles", [])
    formatting = style_metadata.get("formatting", [])

    # If no styles to apply, return unchanged
    if not semantic_styles and not formatting:
        return params

    # Get text content for content-aware style selection
    text = params.get("text", "") or params.get("description", "")
    if not text or not isinstance(text, str):
        return params

    style_to_apply = get_style_for_text(text, style_metadata)

    # Apply style to text field
    if style_to_apply and "text" in params:
        # Escape single quotes in text for Jinja template
        escaped_text = params["text"].replace("'", "\\'")
        styled_text = f"{{{{ '{escaped_text}' | {style_to_apply} }}}}"

        # Add formatting filters if present
        for fmt in formatting:
            styled_text = styled_text[:-3] + f" | {fmt} }}}}"

        params = {**params, "text": styled_text}

    return params


def apply_styles_recursively(
    obj: Any,
    style_metadata: Dict[str, List[str]],
    depth: int = 0,
) -> Any:
    """Recursively walk a card structure and apply styles to all text fields.

    Handles:
    - decoratedText.text
    - textParagraph.text
    - button.text
    - chip.label
    - header.title, header.subtitle
    - Any nested structures

    Args:
        obj: Card dict, list, or value to process
        style_metadata: Style metadata with semantic_styles and formatting
        depth: Current recursion depth

    Returns:
        Modified object with styles applied to text fields
    """
    if not style_metadata.get("semantic_styles"):
        return obj

    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            # Text fields that should be styled
            if key == "text" and isinstance(value, str):
                result[key] = apply_style_to_text(value, style_metadata)
            elif key == "title" and isinstance(value, str) and depth > 0:
                # Style titles in widgets (not card header)
                result[key] = apply_style_to_text(value, style_metadata)
            elif key == "label" and isinstance(value, str):
                # Chip labels
                result[key] = apply_style_to_text(value, style_metadata)
            elif key == "topLabel" and isinstance(value, str):
                result[key] = apply_style_to_text(value, style_metadata)
            elif key == "bottomLabel" and isinstance(value, str):
                result[key] = apply_style_to_text(value, style_metadata)
            else:
                # Recurse into nested structures
                result[key] = apply_styles_recursively(value, style_metadata, depth + 1)
        return result

    elif isinstance(obj, list):
        return [apply_styles_recursively(item, style_metadata, depth) for item in obj]

    else:
        return obj


# =============================================================================
# TEXT FORMATTING FOR GOOGLE CHAT
# =============================================================================


def format_text_for_chat(text: str, jinja_env=None) -> str:
    """
    Format text with Jinja2 processing and markdown-to-HTML conversion for Google Chat.

    Processing order:
    1. Jinja2 template processing (styling filters like success_text, color, etc.)
    2. Markdown conversion (**bold**, *italic*)
    3. Bullet point formatting

    Handles:
    - Jinja filters: {{ 'text' | success_text }}, {{ text | color('success') }}
    - Raw HTML: <font color="#hex">text</font>
    - **bold** -> <b>bold</b>
    - *italic* -> <i>italic</i>
    - Bullet points (-, •, *) at line start -> proper formatting

    Args:
        text: Text to format
        jinja_env: Optional Jinja2 environment for template processing

    Returns:
        Formatted text suitable for Google Chat
    """
    if not text:
        return ""

    result = text

    # Step 1: Process through Jinja2 for styling filters (if env provided)
    if jinja_env and "{{" in text:
        try:
            template = jinja_env.from_string(text)
            result = template.render()
        except Exception:
            pass  # Keep original on error

    # Step 2: Convert **bold** to <b>bold</b>
    result = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", result)

    # Step 3: Convert *italic* to <i>italic</i> (but not bullet points)
    result = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", result)

    # Step 4: Convert markdown bullet points to HTML
    # Handle lines starting with -, •, or * followed by space
    lines = result.split("\n")
    formatted_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("- ", "• ", "* ")):
            # Convert to bullet point with proper formatting
            content = stripped[2:].strip()
            formatted_lines.append(f"• {content}")
        else:
            formatted_lines.append(line)

    return "\n".join(formatted_lines)


__all__ = [
    "extract_style_metadata",
    "apply_styles",
    "style_keyword",
    "DEFAULT_SEMANTIC_COLORS",
    # Style application
    "has_explicit_styles",
    "get_style_for_text",
    "apply_style_to_text",
    "apply_pattern_styles",
    "apply_styles_recursively",
    # Keyword sets
    "SUCCESS_KEYWORDS",
    "ERROR_KEYWORDS",
    "WARNING_KEYWORDS",
    # Text formatting
    "format_text_for_chat",
]
