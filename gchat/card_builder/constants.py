"""
Constants and registries for the card builder.
"""

from typing import Dict, List

from adapters.module_wrapper.types import ComponentName, ComponentPath, JsonDict


# =============================================================================
# COMPONENT PARAMS REGISTRY - Documents expected params for each component
# =============================================================================

COMPONENT_PARAMS: Dict[ComponentName, Dict[str, str]] = {
    # ==========================================================================
    # MESSAGE-LEVEL COMPONENTS (above Card level)
    # These can be passed in card_params and will be applied to the Message
    # ==========================================================================
    "Message": {
        "fallback_text": "Text shown in notifications and for accessibility (optional)",
        "notification_text": "Alias for fallback_text",
        "accessory_widgets": "List of AccessoryWidget dicts for buttons at message bottom",
        "thread_key": "Thread key for reply threading (custom key or existing thread ID)",
        "thread": "Alias for thread_key",
        "text_content": "Plain text to appear with the card",
        "message_text": "Alias for text_content",
        "quoted_message_metadata": "Quote a message: {name: 'spaces/X/messages/Y'}",
        "quote": "Alias for quoted_message_metadata",
        "annotations": "List of annotation dicts for rich text (mentions, etc.)",
    },
    "AccessoryWidget": {
        "button_list": "ButtonList dict with buttons array: {buttons: [{text, url}, ...]}",
    },
    "Thread": {
        "name": "Full thread resource name (spaces/X/threads/Y)",
        "thread_key": "Custom thread key for creating/replying to threads",
    },
    # ==========================================================================
    # WIDGET COMPONENTS
    # ==========================================================================
    "DecoratedText": {
        "text": "Main text content to display",
        "top_label": "Small label above the text",
        "bottom_label": "Small label below the text",
    },
    "TextParagraph": {"text": "Text content to display"},
    "Button": {
        "text": "Button label",
        "url": "URL to open when clicked",
    },
    "ButtonList": {"buttons": "List of button dicts: [{text, url}, ...]"},
    "Image": {
        "image_url": "URL of image to display",
        "alt_text": "Accessibility text",
    },
    "Icon": {
        "known_icon": "Google Material icon name (STAR, BOOKMARK, etc.)",
        "icon_url": "Custom icon URL (alternative to known_icon)",
    },
    "Grid": {
        "column_count": "Number of columns (default: 2)",
        "items": "List of GridItem dicts",
    },
    "GridItem": {"title": "Item title", "subtitle": "Item subtitle"},
    "TextInput": {"name": "Form field name", "label": "Input label", "hint": "Placeholder"},
    "SelectionInput": {
        "name": "Form field name",
        "label": "Selection label",
        "type": "DROPDOWN, RADIO_BUTTON, CHECKBOX, SWITCH",
    },
    "DateTimePicker": {
        "name": "Form field name",
        "label": "Picker label",
        "type": "DATE_ONLY, DATE_AND_TIME, TIME_ONLY",
    },
    "ChipList": {"chips": "List of Chip dicts"},
    "Chip": {"label": "Chip text", "icon": "Optional Icon dict"},
    "Columns": {"columnItems": "List of Column dicts"},
    "Column": {"widgets": "List of widget dicts for this column"},
    "Divider": {},
    "Section": {"header": "Optional section header text", "widgets": "List of widgets"},
    # Carousel components (Google Chat API specific)
    # Note: CarouselCard has NO header field - use textParagraph for titles
    # Widgets are direct (textParagraph, buttonList, image) - NOT wrapped in nestedWidget
    "Carousel": {"carouselCards": "List of CarouselCard dicts"},
    "CarouselCard": {
        "widgets": "List of widget dicts (textParagraph, buttonList, image)",
        "footerWidgets": "Optional list of widget dicts for actions",
    },
}


# =============================================================================
# COMPONENT PATHS REGISTRY
# =============================================================================

COMPONENT_PATHS: Dict[ComponentName, ComponentPath] = {
    "Section": "card_framework.v2.section.Section",
    "Card": "card_framework.v2.card.Card",
    "CardHeader": "card_framework.v2.card.CardHeader",
    "Columns": "card_framework.v2.widgets.columns.Columns",
    "Column": "card_framework.v2.widgets.columns.Column",
    "DecoratedText": "card_framework.v2.widgets.decorated_text.DecoratedText",
    "TextParagraph": "card_framework.v2.widgets.text_paragraph.TextParagraph",
    "Image": "card_framework.v2.widgets.image.Image",
    "Divider": "card_framework.v2.widgets.divider.Divider",
    "Button": "card_framework.v2.widgets.decorated_text.Button",
    "ButtonList": "card_framework.v2.widgets.button_list.ButtonList",
    "Icon": "card_framework.v2.widgets.decorated_text.Icon",
    "OnClick": "card_framework.v2.widgets.decorated_text.OnClick",
    "TextInput": "card_framework.v2.widgets.text_input.TextInput",
    "SelectionInput": "card_framework.v2.widgets.selection_input.SelectionInput",
    "DateTimePicker": "card_framework.v2.widgets.date_time_picker.DateTimePicker",
    "Grid": "card_framework.v2.widgets.grid.Grid",
    "GridItem": "card_framework.v2.widgets.grid.GridItem",
    "ImageComponent": "card_framework.v2.widgets.grid.ImageComponent",
    # Carousel components (Google Chat API specific - custom registered)
    "Carousel": "card_framework.v2.Carousel",  # Custom component via wrapper
    "CarouselCard": "card_framework.v2.CarouselCard",  # Custom component via wrapper
    "NestedWidget": "card_framework.v2.NestedWidget",  # Custom component via wrapper
}


# Patterns that indicate a card ALREADY has feedback buttons
# (more specific to avoid false positives from titles like "Feedback Report")
FEEDBACK_DETECTION_PATTERNS: List[str] = [
    "feedback_type=content",
    "feedback_type=form",
    "feedback=positive",
    "feedback=negative",
    "👍 Good",
    "👍 Yes",
    "👎 Bad",
    "👎 No",
]


# =============================================================================
# DEFAULT PARAMS FOR COMPONENTS
# =============================================================================

DEFAULT_COMPONENT_PARAMS: Dict[ComponentName, JsonDict] = {
    # Text display - no defaults, must be provided by caller
    "TextParagraph": {},
    "DecoratedText": {},
    # Form inputs (require 'name' field)
    "TextInput": {"name": "text_input_0", "label": "Text Input"},
    "DateTimePicker": {"name": "datetime_0", "label": "Select Date/Time"},
    "SelectionInput": {"name": "selection_0", "label": "Select Option", "type": "DROPDOWN"},
    # Layout
    "Divider": {},
    "Image": {"image_url": "https://picsum.photos/400/200"},
    "Grid": {"column_count": 2},
    "GridItem": {"title": "Grid Item"},
    # Buttons and chips
    "Button": {"text": "Button"},
    "ButtonList": {},
    "Chip": {"label": "Chip"},
    "ChipList": {},
    # Columns
    "Columns": {},
    "Column": {},
}


def get_default_params(component_name: ComponentName, index: int = 0) -> JsonDict:
    """Get default params for a component type.

    Args:
        component_name: Component type (e.g., "DecoratedText")
        index: Optional index for unique field names

    Returns:
        Dict of default params, or empty dict if no defaults
    """
    defaults = DEFAULT_COMPONENT_PARAMS.get(component_name, {}).copy()

    # Add index to fields that need unique names
    if defaults:
        for key in ["name", "title", "label"]:
            if key in defaults and isinstance(defaults[key], str):
                # Replace trailing number or add index suffix
                base = defaults[key].rstrip("0123456789_")
                if base != defaults[key]:
                    defaults[key] = f"{base}{index}"
                elif index > 0:
                    defaults[key] = f"{defaults[key]}_{index}"
        # Handle image_url with index
        if "image_url" in defaults:
            defaults["image_url"] = f"{defaults['image_url']}?{index}"

    return defaults


# =============================================================================
# FIELD NAME MAPPINGS (Python to Google Chat JSON)
# =============================================================================

# Mapping from (parent_component, python_field_name) to Google Chat JSON field name
# Used when wrapper renders snake_case but API needs camelCase with different names
FIELD_NAME_TO_JSON = {
    # DecoratedText children
    ("DecoratedText", "icon"): "startIcon",  # Python uses 'icon', API uses 'startIcon'
    # Add more mappings as needed
}


__all__ = [
    "COMPONENT_PARAMS",
    "COMPONENT_PATHS",
    "FEEDBACK_DETECTION_PATTERNS",
    "DEFAULT_COMPONENT_PARAMS",
    "get_default_params",
    "FIELD_NAME_TO_JSON",
]
