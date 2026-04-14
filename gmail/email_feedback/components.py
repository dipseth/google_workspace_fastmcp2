"""
Component registries for modular email feedback block assembly.

Mirrors gchat/card_builder/feedback/components.py but adapted for
MJML email blocks (ButtonBlock, TextBlock, DividerBlock, FooterBlock).
"""

from typing import List

# =============================================================================
# MODULAR EMAIL FEEDBACK COMPONENT REGISTRY
# =============================================================================
# Components categorized by capability within email blocks:
# - TEXT_COMPONENTS: Can display feedback prompt text
# - CLICKABLE_COMPONENTS: Can carry redirect URL (href)
# - DUAL_COMPONENTS: Combined text + clickable in one visual group
# - LAYOUT_WRAPPERS: How to arrange feedback blocks within the email

TEXT_COMPONENTS: List[str] = [
    "text_block",  # Standard TextBlock for prompt display
    "footer_text",  # FooterBlock used for compact footer-style prompt
]

CLICKABLE_COMPONENTS: List[str] = [
    "button_pair",  # Two ButtonBlocks side-by-side (positive + negative)
    "button_single_positive",  # Single positive ButtonBlock only
    "text_link_pair",  # TextBlock with inline HTML <a> links (most compact)
]

DUAL_COMPONENTS: List[str] = [
    "footer_with_links",  # FooterBlock with embedded feedback links
]

LAYOUT_WRAPPERS: List[str] = [
    "with_divider",  # DividerBlock separator before feedback
    "compact",  # No divider, minimal padding
    "footer_style",  # Rendered as part of email footer
]

# Button color schemes for positive/negative feedback
BUTTON_STYLES = {
    "standard": {
        "positive_bg": "#34a853",  # Google green
        "negative_bg": "#ea4335",  # Google red
        "text_color": "#ffffff",
    },
    "subtle": {
        "positive_bg": "#e8f5e9",  # Light green
        "negative_bg": "#fce4ec",  # Light red
        "text_color": "#333333",
    },
    "outline": {
        "positive_bg": "#ffffff",
        "negative_bg": "#ffffff",
        "text_color": "#333333",
    },
    "brand": {
        "positive_bg": "#4285f4",  # Google blue
        "negative_bg": "#9e9e9e",  # Gray
        "text_color": "#ffffff",
    },
}


__all__ = [
    "TEXT_COMPONENTS",
    "CLICKABLE_COMPONENTS",
    "DUAL_COMPONENTS",
    "LAYOUT_WRAPPERS",
    "BUTTON_STYLES",
]
