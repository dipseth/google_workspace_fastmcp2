"""
Config-driven factories for feedback widget construction.
"""

from typing import Any, Dict


# =============================================================================
# CLICK HANDLER CONFIGURATIONS
# =============================================================================
# Config-driven factory for feedback click handlers.
# Each config defines how to build the clickable feedback widget.

CLICK_CONFIGS: Dict[str, Dict[str, Any]] = {
    # Binary positive/negative handlers
    "button_list": {
        "widget": "buttonList",
        "items_key": "buttons",
        "binary": True,  # Uses pos/neg labels
        "use_chips": False,
    },
    "chip_list": {
        "widget": "chipList",
        "items_key": "chips",
        "binary": True,
        "use_chips": True,
    },
    "icon_buttons": {
        "widget": "buttonList",
        "items_key": "buttons",
        "binary": True,
        "use_chips": False,
        "pos_icon_source": "POSITIVE_MATERIAL_ICONS",  # Random from list
        "neg_icon_source": "NEGATIVE_MATERIAL_ICONS",
    },
    "icon_buttons_alt": {
        "widget": "buttonList",
        "items_key": "buttons",
        "binary": True,
        "use_chips": False,
        "pos_icon": "thumb_up",  # Fixed icon
        "neg_icon": "thumb_down",
    },
    "url_image_buttons": {
        "widget": "buttonList",
        "items_key": "buttons",
        "binary": True,
        "use_chips": False,
        "pos_icon_url_source": "POSITIVE_IMAGE_URLS",
        "neg_icon_url_source": "NEGATIVE_IMAGE_URLS",
    },
    # Multi-option rating handlers (not binary)
    "star_rating": {
        "widget": "buttonList",
        "items_key": "buttons",
        "binary": False,
        "button_type": "BORDERLESS",
        "ratings": [
            ("star_outline", "👎 Not great", "negative"),
            ("star_half", "😐 OK", "neutral"),
            ("star", "👍 Great!", "positive"),
        ],
    },
    "emoji_rating": {
        "widget": "buttonList",
        "items_key": "buttons",
        "binary": False,
        "button_type": "BORDERLESS",
        "ratings": [
            ("sentiment_dissatisfied", "😞", "negative"),
            ("sentiment_neutral", "😐", "neutral"),
            ("sentiment_satisfied", "😊", "positive"),
        ],
    },
}


# =============================================================================
# TEXT COMPONENT CONFIGURATIONS
# =============================================================================
# Config-driven factory for feedback text components.

TEXT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "text_paragraph": {
        "component": "TextParagraph",
        "format_text": lambda t: f"<i>{t}</i>",  # Italic wrapper
    },
    "decorated_text": {
        "component": "DecoratedText",
        "wrap_text": True,
    },
    "decorated_text_icon": {
        "component": "DecoratedText",
        "wrap_text": True,
        "add_random_icon": True,  # Uses FEEDBACK_MATERIAL_ICONS
    },
    "decorated_text_labeled": {
        "component": "DecoratedText",
        "wrap_text": True,
        "top_label": "Feedback",
    },
    "chip_text": {
        "component": "chipList",  # Direct dict, not via wrapper
        "direct_dict": True,  # Skip wrapper, return dict directly
    },
}


# =============================================================================
# LAYOUT CONFIGURATIONS
# =============================================================================
# Config for feedback layout options.

LAYOUT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "sequential": {"add_divider": False},
    "with_divider": {"add_divider": True},
    "compact": {"group_by_type": True},  # Groups text and buttons separately
}


__all__ = [
    "CLICK_CONFIGS",
    "TEXT_CONFIGS",
    "LAYOUT_CONFIGS",
]
