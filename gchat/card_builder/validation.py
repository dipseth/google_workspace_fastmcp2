"""
Card validation and cleanup utilities.

This module provides functions for validating Google Chat card structures
and cleaning metadata before sending to the API.
"""

import json
from typing import Any, Dict, List, Tuple

from adapters.module_wrapper.types import IssueList, JsonDict
from gchat.card_builder.constants import FEEDBACK_DETECTION_PATTERNS


def has_feedback(card: JsonDict) -> bool:
    """Check if card already has feedback content.

    Args:
        card: Card dict to check

    Returns:
        True if card contains feedback patterns
    """
    card_str = json.dumps(card).lower()
    return any(p.lower() in card_str for p in FEEDBACK_DETECTION_PATTERNS)


def clean_card_metadata(obj: Any) -> Any:
    """Remove underscore-prefixed keys (Google Chat rejects them).

    Recursively walks the card structure and removes any keys starting
    with underscore (e.g., _card_id, _feedback_assembly).

    Args:
        obj: Card dict, list, or primitive value

    Returns:
        Cleaned object with metadata keys removed
    """
    if isinstance(obj, dict):
        return {
            k: clean_card_metadata(v)
            for k, v in obj.items()
            if not k.startswith("_")
        }
    elif isinstance(obj, list):
        return [clean_card_metadata(item) for item in obj]
    return obj


def validate_content(card_dict: JsonDict) -> Tuple[bool, IssueList]:
    """
    Validate that a card has actual renderable content for Google Chat.

    Checks for:
    - Non-empty card dictionary
    - Header with title or subtitle
    - Sections with widgets containing actual content

    Args:
        card_dict: The card dictionary to validate

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues: IssueList = []

    if not card_dict:
        issues.append("Card dictionary is empty")
        return False, issues

    # Check header content
    header_has_content = False
    if "header" in card_dict and isinstance(card_dict["header"], dict):
        header = card_dict["header"]
        if header.get("title") and header["title"].strip():
            header_has_content = True
        elif header.get("subtitle") and header["subtitle"].strip():
            header_has_content = True

    # Check sections content
    sections_have_content = False
    if "sections" in card_dict and isinstance(card_dict["sections"], list):
        for section_idx, section in enumerate(card_dict["sections"]):
            if not isinstance(section, dict):
                issues.append(f"Section {section_idx} is not a dictionary")
                continue

            if "widgets" not in section:
                issues.append(f"Section {section_idx} has no widgets")
                continue

            widgets = section["widgets"]
            if not isinstance(widgets, list):
                issues.append(f"Section {section_idx} widgets is not a list")
                continue

            if len(widgets) == 0:
                issues.append(f"Section {section_idx} has empty widgets list")
                continue

            # Check each widget for actual content
            section_has_content = False
            for widget_idx, widget in enumerate(widgets):
                if not isinstance(widget, dict):
                    issues.append(f"Section {section_idx}, widget {widget_idx} is not a dictionary")
                    continue

                # Check for various widget types with content
                if "textParagraph" in widget:
                    text_content = widget["textParagraph"].get("text", "").strip()
                    if text_content:
                        section_has_content = True
                elif "image" in widget:
                    image_url = widget["image"].get("imageUrl", "").strip()
                    if image_url:
                        section_has_content = True
                elif "buttonList" in widget:
                    buttons = widget["buttonList"].get("buttons", [])
                    if isinstance(buttons, list) and len(buttons) > 0:
                        for button in buttons:
                            if isinstance(button, dict) and button.get("text", "").strip():
                                section_has_content = True
                                break
                elif any(key in widget for key in [
                    "decoratedText", "decorated_text", "selectionInput", "selection_input",
                    "textInput", "text_input", "divider", "columns", "grid", "chipList"
                ]):
                    section_has_content = True

            if section_has_content:
                sections_have_content = True
    else:
        issues.append("Card has no sections or sections is not a list")

    has_content = header_has_content or sections_have_content

    if not has_content:
        issues.append("Card has no renderable content (empty header and empty/missing sections)")

    return has_content, issues


def make_callback_url(
    base_url: str,
    card_id: str,
    feedback_val: str,
    feedback_type: str,
) -> str:
    """Create feedback callback URL.

    Args:
        base_url: Base URL for feedback endpoint
        card_id: Unique card identifier
        feedback_val: Feedback value (positive/negative)
        feedback_type: Type of feedback (content/form)

    Returns:
        Complete callback URL with query parameters
    """
    return f"{base_url}?card_id={card_id}&feedback={feedback_val}&feedback_type={feedback_type}"


__all__ = [
    "has_feedback",
    "clean_card_metadata",
    "validate_content",
    "make_callback_url",
]
