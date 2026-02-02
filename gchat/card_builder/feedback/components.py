"""
Component registries for modular feedback widget assembly.
"""

from typing import List

# =============================================================================
# MODULAR FEEDBACK COMPONENT REGISTRY
# =============================================================================
# Components are categorized by capability:
# - TEXT_COMPONENTS: Can display feedback prompt text
# - CLICKABLE_COMPONENTS: Can carry onClick callback URL
# - DUAL_COMPONENTS: Can do both (text + click in same widget)
# - LAYOUT_WRAPPERS: How to arrange the assembled widgets

TEXT_COMPONENTS: List[str] = [
    "text_paragraph",  # Simple text block
    "decorated_text",  # Text with optional icon, top/bottom labels
    "decorated_text_icon",  # DecoratedText with startIcon
    "selection_label",  # SelectionInput used for its label display
    "chip_text",  # Chip used for text display
]

CLICKABLE_COMPONENTS: List[str] = [
    "button_list",  # Standard button row (2 buttons: pos + neg)
    "chip_list",  # Clickable chips (2 chips: pos + neg)
    "icon_buttons",  # Buttons with random knownIcon (pos/neg themed)
    "icon_buttons_alt",  # Buttons with STAR/BOOKMARK knownIcon
    "url_image_buttons",  # Buttons with URL images (check/X, Y/N, colors)
]

# Components that can do both text AND click in one widget
DUAL_COMPONENTS: List[str] = [
    "decorated_text_with_button",  # Text + inline button + separate neg button
    "decorated_inline_only",  # Text + single inline button (most compact - 1 widget)
    "chip_dual",  # Chip with text and onClick
    "columns_inline",  # Text left, buttons right in one widget
]

LAYOUT_WRAPPERS: List[str] = [
    "sequential",  # Widgets one after another
    "with_divider",  # Divider between content and form feedback
    "columns_layout",  # Side-by-side columns
    "compact",  # Minimal spacing
]

# Button type styles (Google Chat Card v2)
# https://developers.google.com/workspace/chat/api/reference/rest/v1/cards#type_1
BUTTON_TYPES: List[str] = [
    "OUTLINED",  # Medium-emphasis, default styling
    "FILLED",  # High-emphasis, solid color container
    "FILLED_TONAL",  # Middle ground between filled and outlined
    "BORDERLESS",  # Low-emphasis, no visible container (most compact)
]

# Section styles for feedback area
SECTION_STYLES: List[str] = [
    "normal",  # Standard section (current behavior)
    "collapsible_0",  # Collapsible, 0 widgets visible by default (most compact)
    "collapsible_1",  # Collapsible, 1 widget visible by default
]


__all__ = [
    "TEXT_COMPONENTS",
    "CLICKABLE_COMPONENTS",
    "DUAL_COMPONENTS",
    "LAYOUT_WRAPPERS",
    "BUTTON_TYPES",
    "SECTION_STYLES",
]
