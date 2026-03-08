"""
Card-specific field extractors for InputResolverMixin.

These functions know how to pull fields from resource dicts for each
Google Chat card component type. They are registered with the wrapper's
InputResolverMixin at setup time via register_input_resolution_batch().

Each extractor signature: (resource: dict, index: int) -> dict
"""

from typing import Callable, Dict, Set

# Type alias matching InputResolverMixin
FieldExtractor = Callable[[dict, int], dict]
OverflowHandler = Callable[[str, int], dict]


# =============================================================================
# FIELD EXTRACTORS
# =============================================================================


def extract_content_text_fields(resource: dict, index: int) -> dict:
    """Extract fields for DecoratedText / TextParagraph from context."""
    params = {}
    # Use 'styled' key (from Content DSL) or 'text' key (explicit)
    params["text"] = resource.get("styled") or resource.get("text", "")
    if resource.get("icon"):
        params["icon"] = resource["icon"]
    if resource.get("top_label"):
        params["top_label"] = resource["top_label"]
    if resource.get("bottom_label"):
        params["bottom_label"] = resource["bottom_label"]
    # Always include wrapText (default True for multi-line content)
    params["wrapText"] = resource.get("wrapText", True)
    return params


def extract_button_fields(resource: dict, index: int) -> dict:
    """Extract fields for Button from context."""
    params = {"text": resource.get("text", "Button")}
    if resource.get("url"):
        params["url"] = resource["url"]
    if resource.get("icon"):
        params["icon"] = resource["icon"]
    return params


def extract_chip_fields(resource: dict, index: int) -> dict:
    """Extract fields for Chip from context."""
    params = {"label": resource.get("label") or resource.get("text", "Chip")}
    if resource.get("url"):
        params["url"] = resource["url"]
    if resource.get("icon"):
        params["icon"] = resource["icon"]
    return params


def extract_carousel_card_fields(resource: dict, index: int) -> dict:
    """Extract fields for CarouselCard from context."""
    params = {"title": resource.get("title", f"Card {index + 1}")}
    if resource.get("subtitle"):
        params["subtitle"] = resource["subtitle"]
    img = resource.get("image_url") or resource.get("image")
    if img:
        params["image_url"] = img
    if resource.get("text"):
        params["text"] = resource["text"]
    if resource.get("buttons"):
        params["buttons"] = resource["buttons"]
    if resource.get("footer_buttons"):
        params["footer_buttons"] = resource["footer_buttons"]
    return params


def extract_grid_item_fields(resource: dict, index: int) -> dict:
    """Extract fields for GridItem from context."""
    params = {"title": resource.get("title", f"Item {index + 1}")}
    if resource.get("subtitle"):
        params["subtitle"] = resource["subtitle"]
    if resource.get("image_url"):
        params["image_url"] = resource["image_url"]
    if resource.get("image"):
        params["image"] = resource["image"]
    return params


# =============================================================================
# OVERFLOW HANDLERS (fallback when resources exhausted)
# =============================================================================


def _overflow_button(component_name: str, index: int) -> dict:
    return {"text": f"Button {index + 1}"}


def _overflow_chip(component_name: str, index: int) -> dict:
    return {"label": f"Chip {index + 1}"}


def _overflow_carousel_card(component_name: str, index: int) -> dict:
    return {"title": f"Card {index + 1}"}


def _overflow_grid_item(component_name: str, index: int) -> dict:
    return {"title": f"Item {index + 1}"}


# =============================================================================
# BATCH REGISTRATION CONSTANTS
# =============================================================================

CARD_FIELD_EXTRACTORS: Dict[str, FieldExtractor] = {
    "content_texts": extract_content_text_fields,
    "buttons": extract_button_fields,
    "chips": extract_chip_fields,
    "carousel_cards": extract_carousel_card_fields,
    "grid_items": extract_grid_item_fields,
}

CARD_OVERFLOW_HANDLERS: Dict[str, OverflowHandler] = {
    "Button": _overflow_button,
    "Chip": _overflow_chip,
    "CarouselCard": _overflow_carousel_card,
    "GridItem": _overflow_grid_item,
}

CARD_PARAM_KEY_OVERRIDES: Dict[str, str] = {
    "content_texts": "items",
    "carousel_cards": "cards",
    "grid_items": "grid_items",
}

CARD_SCALAR_PARAMS: Set[str] = {"image_url"}


__all__ = [
    "extract_content_text_fields",
    "extract_button_fields",
    "extract_chip_fields",
    "extract_carousel_card_fields",
    "extract_grid_item_fields",
    "CARD_FIELD_EXTRACTORS",
    "CARD_OVERFLOW_HANDLERS",
    "CARD_PARAM_KEY_OVERRIDES",
    "CARD_SCALAR_PARAMS",
]
