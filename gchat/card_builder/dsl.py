"""
DSL parsing and generation utilities for card components.

This module provides standalone functions for:
- Extracting DSL notation from card structures
- Generating DSL suggestions from parameters
- Converting between card JSON and component paths
"""

from typing import Any, Dict, List, Optional

from adapters.module_wrapper.types import (
    ComponentName,
    ComponentPaths,
    DSLNotation,
    JsonDict,
    SymbolMapping,
)
from config.enhanced_logging import setup_logger
from gchat.card_builder.metadata import get_children_field, get_container_child_type
from gchat.card_builder.rendering import json_key_to_component_name

logger = setup_logger()

# =============================================================================
# WIDGET TYPE MAPPINGS
# =============================================================================

# JSON widget keys that can be identified in card structures.
# Derived from rendering.py's _JSON_KEY_TO_COMPONENT (single source of truth).
from gchat.card_builder.rendering import _JSON_KEY_TO_COMPONENT

WIDGET_JSON_KEYS = frozenset(_JSON_KEY_TO_COMPONENT.keys())

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
    if not card_params or not symbols:
        return None

    # All symbols come from the mapping — no hardcoded fallbacks.
    # If Section symbol is missing, we can't produce valid DSL.
    sec = symbols.get("Section")
    if not sec:
        return None

    widgets = []

    # Add text widget if text or description provided
    if card_params.get("text") or card_params.get("description"):
        dt = symbols.get("DecoratedText")
        if dt:
            widgets.append(dt)

    # Add image widget if image_url provided
    if card_params.get("image_url"):
        img = symbols.get("Image")
        if img:
            widgets.append(img)

    # Add button list if buttons provided
    buttons = card_params.get("buttons", [])
    if buttons:
        bl = symbols.get("ButtonList")
        btn = symbols.get("Button")
        if bl and btn:
            n = len(buttons)
            widgets.append(f"{bl}[{btn}]" if n == 1 else f"{bl}[{btn}×{n}]")

    # Add grid if grid_items or items provided
    items = card_params.get("grid_items") or card_params.get("items", [])
    if items:
        grid = symbols.get("Grid")
        gi = symbols.get("GridItem")
        if grid and gi:
            widgets.append(f"{grid}[{gi}×{len(items)}]")

    # Add carousel if cards provided
    cards = card_params.get("cards") or card_params.get("carousel_cards", [])
    if cards:
        carousel = symbols.get("Carousel")
        cc = symbols.get("CarouselCard")
        if carousel and cc:
            n = len(cards)
            widgets.append(f"{carousel}[{cc}]" if n == 1 else f"{carousel}[{cc}×{n}]")
            # Carousel is a top-level widget, return directly
            return f"{sec}[{', '.join(widgets)}]" if widgets else None

    # Return None if no widgets to suggest
    if not widgets:
        return None

    return f"{sec}[{', '.join(widgets)}]"

# =============================================================================
# DSL GENERATION FROM CARD
# =============================================================================

def _count_children(
    widget_data: JsonDict,
    component_name: ComponentName,
    wrapper: Optional[Any] = None,
) -> int:
    """Count children of a container widget using metadata-driven field lookup.

    Uses get_children_field() from metadata.py (wrapper SSoT, fallback to dict)
    to discover which JSON field holds children, then counts them.

    Args:
        widget_data: The inner dict of the widget (e.g., the value of "buttonList")
        component_name: Component type (e.g., "ButtonList", "Carousel")
        wrapper: Optional ModuleWrapper for dynamic metadata lookups

    Returns:
        Number of children found, or 0 if not a container
    """
    children_field = get_children_field(component_name, wrapper)
    if not children_field:
        return 0
    return len(widget_data.get(children_field, []))

def _widget_to_dsl(
    widget: JsonDict,
    symbol_mapping: SymbolMapping,
    wrapper: Optional[Any] = None,
) -> Optional[str]:
    """Convert a single widget dict to its DSL symbol notation.

    Uses rendering.json_key_to_component_name() for reverse lookup and
    metadata.get_children_field()/get_container_child_type() for nested structures.

    Args:
        widget: Widget dict (e.g., {"buttonList": {"buttons": [...]}})
        symbol_mapping: Component-to-symbol mapping from ModuleWrapper
        wrapper: Optional ModuleWrapper for dynamic metadata lookups

    Returns:
        DSL symbol string (e.g., "Ƀ[ᵬ×3]"), or None if widget type is unrecognized
    """
    # Find the widget type key — skip internal keys
    json_key = None
    for key in widget:
        if not key.startswith("_"):
            component = json_key_to_component_name(key)
            if component in symbol_mapping:
                json_key = key
                break

    if json_key is None:
        return None

    component_name = json_key_to_component_name(json_key)
    symbol = symbol_mapping.get(component_name)
    if not symbol:
        return None

    # Check for nested children via metadata
    widget_data = widget.get(json_key, {})
    child_count = _count_children(widget_data, component_name, wrapper)
    if child_count > 0:
        child_type = get_container_child_type(component_name, wrapper)
        child_symbol = symbol_mapping.get(child_type, "") if child_type else ""
        if child_symbol:
            nested = (
                f"{child_symbol}×{child_count}" if child_count > 1 else child_symbol
            )
            return f"{symbol}[{nested}]"

    return symbol

def generate_dsl_notation(
    card: JsonDict,
    symbol_mapping: SymbolMapping,
    wrapper: Optional[Any] = None,
) -> Optional[DSLNotation]:
    """
    Generate DSL notation from a rendered card structure.

    Reverse-engineers the card structure to produce DSL notation
    that could recreate the same structure. Uses the metadata module
    (wrapper SSoT with static fallbacks) to discover container/child
    relationships instead of hardcoded if/elif chains.

    Args:
        card: Card dict in Google Chat format (with sections/widgets)
        symbol_mapping: Component-to-symbol mapping from ModuleWrapper
        wrapper: Optional ModuleWrapper for dynamic metadata lookups

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

    section_dsls = []

    for section in sections:
        widgets = section.get("widgets", [])
        if not widgets:
            continue

        widget_symbols: List[str] = []
        prev_symbol: Optional[str] = None
        count = 0

        for widget in widgets:
            full_symbol = _widget_to_dsl(widget, symbol_mapping, wrapper)
            if not full_symbol:
                continue

            # Collapse consecutive same symbols into ×N notation
            if full_symbol == prev_symbol:
                count += 1
            else:
                if prev_symbol:
                    widget_symbols.append(
                        f"{prev_symbol}×{count}" if count > 1 else prev_symbol
                    )
                prev_symbol = full_symbol
                count = 1

        # Add final symbol
        if prev_symbol:
            widget_symbols.append(
                f"{prev_symbol}×{count}" if count > 1 else prev_symbol
            )

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
