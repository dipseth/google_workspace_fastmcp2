"""
Card validation and cleanup utilities.

This module provides functions for validating Google Chat card structures
and cleaning metadata before sending to the API.

Structural validation uses the same container/child metadata from
wrapper_setup.py that the builder uses, keeping rules in one place.
"""

import json
from typing import Any, Dict, List, Optional, Set, Tuple

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
            k: clean_card_metadata(v) for k, v in obj.items() if not k.startswith("_")
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
                    issues.append(
                        f"Section {section_idx}, widget {widget_idx} is not a dictionary"
                    )
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
                            if (
                                isinstance(button, dict)
                                and button.get("text", "").strip()
                            ):
                                section_has_content = True
                                break
                elif any(
                    key in widget
                    for key in [
                        "decoratedText",
                        "decorated_text",
                        "selectionInput",
                        "selection_input",
                        "textInput",
                        "text_input",
                        "divider",
                        "columns",
                        "grid",
                        "chipList",
                    ]
                ):
                    section_has_content = True

            if section_has_content:
                sections_have_content = True
    else:
        issues.append("Card has no sections or sections is not a list")

    has_content = header_has_content or sections_have_content

    if not has_content:
        issues.append(
            "Card has no renderable content (empty header and empty/missing sections)"
        )

    return has_content, issues


# =============================================================================
# STRUCTURAL VALIDATION — Data-driven via container/child metadata
# =============================================================================
#
# Google Chat webhooks return 200 for structurally invalid cards but silently
# drop them. These rules define required fields per child component type,
# using the same container→children_field→child_type model as wrapper_setup.py.
#
# Each rule: (children_field, required_fields, any_of_fields)
#   - children_field: JSON key holding the child array (from CARD_CONTAINERS)
#   - required_fields: every child MUST have ALL of these
#   - any_of_fields: every child MUST have AT LEAST ONE of these
#
# When a child fails validation, the entire card is silently dropped by Google.

# Container JSON key → (children_field, required_fields, any_of_fields)
_CHILD_RULES: Dict[str, Tuple[str, Set[str], Set[str]]] = {
    "buttonList": (
        "buttons",
        set(),  # no universally required fields
        {"onClick", "on_click", "action"},  # must have at least one click handler
    ),
    "chipList": (
        "chips",
        set(),
        {"onClick", "on_click", "action"},
    ),
}

# Components that can appear as inline children (not in a list container)
# and also need onClick validation. Key = parent widget key, value = child key.
_INLINE_CHILD_RULES: Dict[str, Tuple[str, Set[str], Set[str]]] = {
    "decoratedText": (
        "button",  # decoratedText can have an inline button accessory
        set(),
        {"onClick", "on_click", "action"},
    ),
}


def _check_child(
    child: Dict,
    required: Set[str],
    any_of: Set[str],
) -> Optional[str]:
    """Check a single child dict against required/any_of field rules.

    Returns an error string if invalid, None if valid.
    """
    for field in required:
        if not child.get(field):
            return f"missing required field '{field}'"

    if any_of and not any(child.get(f) for f in any_of):
        return f"missing one of {sorted(any_of)}"

    return None


def validate_structure(card_dict: JsonDict) -> Tuple[bool, IssueList]:
    """
    Validate card structure against Google Chat silent-failure patterns.

    Walks the card's section→widget tree and checks each container's
    children against _CHILD_RULES. Uses the same container model as the
    card builder (wrapper_setup.py CARD_CONTAINERS).

    Args:
        card_dict: The card dictionary to validate (inner card, not wrapper)

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues: IssueList = []

    if not card_dict or not isinstance(card_dict, dict):
        return True, issues

    sections = card_dict.get("sections", [])
    if not isinstance(sections, list):
        return True, issues

    for s_idx, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        widgets = section.get("widgets", [])
        if not isinstance(widgets, list):
            continue

        for w_idx, widget in enumerate(widgets):
            if not isinstance(widget, dict):
                continue
            path = f"section[{s_idx}].widget[{w_idx}]"

            # Check container rules (buttonList, chipList)
            for widget_key, (children_field, required, any_of) in _CHILD_RULES.items():
                container = widget.get(widget_key)
                if not isinstance(container, dict):
                    continue
                children = container.get(children_field, [])
                if not isinstance(children, list):
                    continue
                for i, child in enumerate(children):
                    if not isinstance(child, dict):
                        continue
                    error = _check_child(child, required, any_of)
                    if error:
                        label = child.get("text") or child.get("label") or "?"
                        issues.append(
                            f"{path}.{widget_key}.{children_field}[{i}] "
                            f"('{label}'): {error} — card will be silently dropped"
                        )

            # Check inline child rules (decoratedText.button)
            for widget_key, (
                child_key,
                required,
                any_of,
            ) in _INLINE_CHILD_RULES.items():
                parent = widget.get(widget_key)
                if not isinstance(parent, dict):
                    continue
                child = parent.get(child_key)
                if not isinstance(child, dict):
                    continue
                error = _check_child(child, required, any_of)
                if error:
                    label = child.get("text") or "?"
                    issues.append(
                        f"{path}.{widget_key}.{child_key} "
                        f"('{label}'): {error} — card will be silently dropped"
                    )

    return len(issues) == 0, issues


def _fix_child_in_place(child: Dict, any_of: Set[str]) -> Optional[str]:
    """Try to fix a child in-place by adding missing required fields.

    For buttons/chips missing onClick, adds a no-op onClick with a '#' URL
    so the component still renders rather than killing the entire card.

    Returns a fix description if fixed, None if no fix was needed or possible.
    """
    # onClick-family fix: add placeholder onClick so the button renders
    if any_of & {"onClick", "on_click", "action"}:
        if not any(child.get(f) for f in any_of):
            label = child.get("text") or child.get("label") or "?"
            child["disabled"] = True
            child["onClick"] = {"action": {"function": "noop"}}
            return (
                f"Disabled '{label}' — no click handler provided. "
                f"Supply a 'url' param to make it functional."
            )
    return None


def _make_error_widget(message: str) -> Dict:
    """Create a decoratedText widget that displays a validation error inline."""
    return {
        "decoratedText": {
            "topLabel": "Validation Fix",
            "text": f'<font color="#CC0000">{message}</font>',
            "startIcon": {"knownIcon": "TICKET"},
        }
    }


def fix_structure(card_dict: JsonDict) -> Tuple[JsonDict, IssueList]:
    """
    Auto-repair known silent-failure patterns in a card.

    Strategy (in priority order):
    1. Fix in-place — e.g. add placeholder onClick to buttons missing it
    2. Replace with error widget — if in-place fix isn't possible, swap the
       broken widget for a visible error decoratedText so the LLM can see
       what went wrong and retry

    Args:
        card_dict: The card dictionary to fix (inner card, not wrapper)

    Returns:
        Tuple of (fixed_card_dict, list_of_fixes_applied)
    """
    fixes: IssueList = []

    if not card_dict or not isinstance(card_dict, dict):
        return card_dict, fixes

    sections = card_dict.get("sections", [])
    if not isinstance(sections, list):
        return card_dict, fixes

    fixed_sections = []
    for s_idx, section in enumerate(sections):
        if not isinstance(section, dict):
            fixed_sections.append(section)
            continue
        widgets = section.get("widgets", [])
        if not isinstance(widgets, list):
            fixed_sections.append(section)
            continue

        fixed_widgets = []
        for w_idx, widget in enumerate(widgets):
            if not isinstance(widget, dict):
                fixed_widgets.append(widget)
                continue

            path = f"section[{s_idx}].widget[{w_idx}]"
            widget_fixed = False

            # Fix container children in-place (buttonList, chipList)
            for widget_key, (children_field, required, any_of) in _CHILD_RULES.items():
                container = widget.get(widget_key)
                if not isinstance(container, dict):
                    continue
                children = container.get(children_field, [])
                if not isinstance(children, list):
                    continue

                for child in children:
                    if not isinstance(child, dict):
                        continue
                    error = _check_child(child, required, any_of)
                    if error:
                        fix_desc = _fix_child_in_place(child, any_of)
                        if fix_desc:
                            fixes.append(f"{path}.{widget_key}: {fix_desc}")
                            widget_fixed = True

            # Fix inline children in-place (decoratedText.button)
            for widget_key, (
                child_key,
                required,
                any_of,
            ) in _INLINE_CHILD_RULES.items():
                parent = widget.get(widget_key)
                if not isinstance(parent, dict):
                    continue
                child = parent.get(child_key)
                if not isinstance(child, dict):
                    continue
                error = _check_child(child, required, any_of)
                if error:
                    fix_desc = _fix_child_in_place(child, any_of)
                    if fix_desc:
                        fixes.append(f"{path}.{widget_key}.{child_key}: {fix_desc}")
                        widget_fixed = True

            # Re-validate after in-place fixes — if still broken, replace with error widget
            still_broken = False
            for widget_key, (children_field, required, any_of) in _CHILD_RULES.items():
                container = widget.get(widget_key)
                if not isinstance(container, dict):
                    continue
                children = container.get(children_field, [])
                if not isinstance(children, list):
                    continue
                for child in children:
                    if isinstance(child, dict) and _check_child(
                        child, required, any_of
                    ):
                        still_broken = True
                        break

            if still_broken:
                error_msg = f"Widget at {path} could not be auto-fixed and was replaced"
                fixes.append(error_msg)
                fixed_widgets.append(_make_error_widget(error_msg))
            else:
                fixed_widgets.append(widget)

        fixed_sections.append({**section, "widgets": fixed_widgets})

    return {**card_dict, "sections": fixed_sections}, fixes


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
    "validate_structure",
    "fix_structure",
    "make_callback_url",
]
