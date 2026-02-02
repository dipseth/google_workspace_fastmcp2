"""
DSL parsing and generation utilities for card components.

This module provides standalone functions for:
- Extracting DSL notation from card structures
- Generating DSL suggestions from parameters
- Converting between card JSON and component paths
"""

import logging
from typing import Any, Dict, List, Optional

from adapters.module_wrapper.types import (
    ComponentName,
    ComponentPaths,
    DSLNotation,
    JsonDict,
    SymbolMapping,
)
from gchat.card_builder.rendering import json_key_to_component_name

logger = logging.getLogger(__name__)


# =============================================================================
# WIDGET TYPE MAPPINGS
# =============================================================================

# JSON widget keys that can be identified in card structures
WIDGET_JSON_KEYS = frozenset(
    {
        "textParagraph",
        "decoratedText",
        "buttonList",
        "chipList",
        "image",
        "grid",
        "columns",
        "divider",
        "textInput",
        "selectionInput",
        "dateTimePicker",
        "carousel",
        "carouselCard",
    }
)


# =============================================================================
# COMPONENT PATH EXTRACTION
# =============================================================================


def extract_component_paths(card: JsonDict) -> ComponentPaths:
    """
    Extract component paths from a card structure.

    Walks through the card dict and identifies widget types used.

    Args:
        card: Card dict in Google Chat format (with sections/widgets)

    Returns:
        List of component names found (e.g., ["Section", "TextParagraph", "ButtonList"])

    Example:
        >>> card = {"sections": [{"widgets": [{"decoratedText": {"text": "Hi"}}]}]}
        >>> extract_component_paths(card)
        ["Section", "DecoratedText"]
    """
    paths: ComponentPaths = []

    def walk(obj: Any, depth: int = 0):
        if isinstance(obj, dict):
            for key, value in obj.items():
                # Identify widget types using the known keys
                if key in WIDGET_JSON_KEYS:
                    component_name = json_key_to_component_name(key)
                    paths.append(component_name)
                walk(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, depth)

    # Add Section for each section
    sections = card.get("sections", [])
    for _ in sections:
        paths.append("Section")

    # Walk through widgets
    for section in sections:
        walk(section.get("widgets", []))

    return paths


# =============================================================================
# DSL SUGGESTION
# =============================================================================


def suggest_dsl_for_params(
    card_params: JsonDict, symbols: SymbolMapping
) -> Optional[DSLNotation]:
    """
    Suggest DSL structure based on provided card_params.

    Args:
        card_params: Dictionary with parameters like text, buttons, image_url, etc.
        symbols: Symbol mapping from ModuleWrapper (e.g., wrapper.symbol_mapping)

    Returns:
        Suggested DSL string using symbols from the mapping, or None if no suggestion

    Example:
        >>> symbols = {"Section": "§", "DecoratedText": "δ", "ButtonList": "Ƀ", "Button": "ᵬ"}
        >>> suggest_dsl_for_params({"text": "Hello", "buttons": [{"text": "Click"}]}, symbols)
        "§[δ, Ƀ[ᵬ]]"
    """
    if not card_params:
        return None

    # Get symbols with defaults
    sec = symbols.get("Section", "§")
    dt = symbols.get("DecoratedText", "δ")
    bl = symbols.get("ButtonList", "Ƀ")
    btn = symbols.get("Button", "ᵬ")
    img = symbols.get("Image", "ι")
    grid = symbols.get("Grid", "ℊ")
    gi = symbols.get("GridItem", "ǵ")

    widgets = []

    # Add text widget if text or description provided
    if card_params.get("text") or card_params.get("description"):
        widgets.append(dt)

    # Add image widget if image_url provided
    if card_params.get("image_url"):
        widgets.append(img)

    # Add button list if buttons provided
    buttons = card_params.get("buttons", [])
    if buttons:
        n = len(buttons)
        if n == 1:
            widgets.append(f"{bl}[{btn}]")
        else:
            widgets.append(f"{bl}[{btn}×{n}]")

    # Add grid if grid_items or items provided
    items = card_params.get("grid_items") or card_params.get("items", [])
    if items:
        widgets.append(f"{grid}[{gi}×{len(items)}]")

    # Return None if no widgets to suggest
    if not widgets:
        return None

    return f"{sec}[{', '.join(widgets)}]"


# =============================================================================
# DSL GENERATION FROM CARD
# =============================================================================


def generate_dsl_notation(
    card: JsonDict,
    symbol_mapping: SymbolMapping,
) -> Optional[DSLNotation]:
    """
    Generate DSL notation from a rendered card structure.

    Reverse-engineers the card structure to produce DSL notation
    that could recreate the same structure.

    Args:
        card: Card dict in Google Chat format (with sections/widgets)
        symbol_mapping: Component-to-symbol mapping from ModuleWrapper

    Returns:
        DSL string using symbols from the mapping, or None if unable to generate

    Example:
        >>> card = {"sections": [{"widgets": [{"decoratedText": {"text": "Hi"}}]}]}
        >>> symbols = {"Section": "§", "DecoratedText": "δ"}
        >>> generate_dsl_notation(card, symbols)
        "§[δ]"
    """
    if not symbol_mapping:
        return None

    # Get the inner card structure
    inner_card = card.get("card", card)
    sections = inner_card.get("sections", [])

    if not sections:
        return None

    # Map widget keys to component names
    widget_to_component = {
        "textParagraph": "TextParagraph",
        "decoratedText": "DecoratedText",
        "buttonList": "ButtonList",
        "chipList": "ChipList",
        "image": "Image",
        "grid": "Grid",
        "columns": "Columns",
        "divider": "Divider",
        "textInput": "TextInput",
        "selectionInput": "SelectionInput",
        "dateTimePicker": "DateTimePicker",
    }

    section_dsls = []

    for section in sections:
        widgets = section.get("widgets", [])
        if not widgets:
            continue

        widget_symbols = []
        prev_symbol = None
        count = 0

        for widget in widgets:
            # Find the widget type
            widget_type = None
            for key in widget.keys():
                if key in widget_to_component:
                    widget_type = key
                    break

            if not widget_type:
                continue

            component_name = widget_to_component[widget_type]
            symbol = symbol_mapping.get(component_name, component_name[0])

            # Handle nested structures (ButtonList with buttons, Grid with items)
            nested_dsl = None
            if widget_type == "buttonList":
                buttons = widget.get("buttonList", {}).get("buttons", [])
                btn_count = len(buttons)
                if btn_count > 0:
                    btn_symbol = symbol_mapping.get("Button", "ᵬ")
                    nested_dsl = (
                        f"{btn_symbol}×{btn_count}" if btn_count > 1 else btn_symbol
                    )
            elif widget_type == "grid":
                items = widget.get("grid", {}).get("items", [])
                item_count = len(items)
                if item_count > 0:
                    item_symbol = symbol_mapping.get("GridItem", "ǵ")
                    nested_dsl = (
                        f"{item_symbol}×{item_count}" if item_count > 1 else item_symbol
                    )
            elif widget_type == "chipList":
                chips = widget.get("chipList", {}).get("chips", [])
                chip_count = len(chips)
                if chip_count > 0:
                    chip_symbol = symbol_mapping.get("Chip", "ꞓ")
                    nested_dsl = (
                        f"{chip_symbol}×{chip_count}" if chip_count > 1 else chip_symbol
                    )

            # Build symbol with optional nesting
            full_symbol = f"{symbol}[{nested_dsl}]" if nested_dsl else symbol

            # Collapse consecutive same symbols into ×N notation
            if full_symbol == prev_symbol:
                count += 1
            else:
                if prev_symbol:
                    if count > 1:
                        widget_symbols.append(f"{prev_symbol}×{count}")
                    else:
                        widget_symbols.append(prev_symbol)
                prev_symbol = full_symbol
                count = 1

        # Add final symbol
        if prev_symbol:
            if count > 1:
                widget_symbols.append(f"{prev_symbol}×{count}")
            else:
                widget_symbols.append(prev_symbol)

        if widget_symbols:
            section_symbol = symbol_mapping.get("Section", "§")
            section_dsls.append(f"{section_symbol}[{', '.join(widget_symbols)}]")

    if not section_dsls:
        return None

    # For single section, return just the section DSL
    if len(section_dsls) == 1:
        return section_dsls[0]

    # For multiple sections, join with separator
    return " | ".join(section_dsls)


__all__ = [
    "WIDGET_JSON_KEYS",
    "extract_component_paths",
    "suggest_dsl_for_params",
    "generate_dsl_notation",
]
