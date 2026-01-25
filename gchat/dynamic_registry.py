"""
Dynamic Registry Builder

Builds COMPONENT_PATHS and NL_RELATIONSHIP_PATTERNS dynamically from Qdrant,
replacing hardcoded static mappings with data-driven discovery.

Following the Manifesto: "The CONTENT_PATTERNS registry knows the way"
But now the registry is built from actual indexed data, not hardcoded rules.

Usage:
    from gchat.dynamic_registry import get_dynamic_component_paths, get_dynamic_relationship_patterns

    # These return dict that can replace the hardcoded versions
    paths = get_dynamic_component_paths()
    patterns = get_dynamic_relationship_patterns()

Architecture:
    - Queries Qdrant collection for class-type points
    - Extracts component paths and relationships
    - Generates NL descriptions from relationship structure
    - Caches results for performance
    - Falls back to hardcoded if Qdrant unavailable
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Cache for dynamic registries (built once, reused)
_component_paths_cache: Optional[Dict[str, str]] = None
_relationship_patterns_cache: Optional[Dict[Tuple[str, str], str]] = None

# Hardcoded fallbacks (minimal set for when Qdrant is unavailable)
FALLBACK_COMPONENT_PATHS = {
    "Section": "card_framework.v2.section.Section",
    "Card": "card_framework.v2.card.Card",
    "CardHeader": "card_framework.v2.card.CardHeader",
    "DecoratedText": "card_framework.v2.widgets.decorated_text.DecoratedText",
    "TextParagraph": "card_framework.v2.widgets.text_paragraph.TextParagraph",
    "Image": "card_framework.v2.widgets.image.Image",
    "Button": "card_framework.v2.widgets.decorated_text.Button",
    "ButtonList": "card_framework.v2.widgets.button_list.ButtonList",
    "Icon": "card_framework.v2.widgets.decorated_text.Icon",
    "OnClick": "card_framework.v2.widgets.decorated_text.OnClick",
    "TextInput": "card_framework.v2.widgets.text_input.TextInput",
    "Grid": "card_framework.v2.widgets.grid.Grid",
    "Columns": "card_framework.v2.widgets.columns.Columns",
    "Column": "card_framework.v2.widgets.columns.Column",
}

FALLBACK_RELATIONSHIP_PATTERNS = {
    ("Image", "OnClick"): "clickable image, image with click action",
    ("DecoratedText", "OnClick"): "clickable text, text with click action",
    ("DecoratedText", "Icon"): "text with icon, decorated text with icon",
    ("DecoratedText", "Button"): "text with button, decorated text with action button",
    ("Button", "OnClick"): "button click action, button that opens link",
    ("Grid", "OnClick"): "clickable grid, grid with click action",
}


def get_dynamic_component_paths(force_refresh: bool = False) -> Dict[str, str]:
    """
    Get component paths dynamically from Qdrant.

    Returns:
        Dict mapping short names to full paths, e.g.:
        {"DecoratedText": "card_framework.v2.widgets.decorated_text.DecoratedText"}
    """
    global _component_paths_cache

    if _component_paths_cache is not None and not force_refresh:
        return _component_paths_cache

    try:
        from config.qdrant_client import get_qdrant_client
        from config.settings import settings
        from qdrant_client import models

        client = get_qdrant_client()
        if not client:
            logger.warning("Qdrant unavailable, using fallback COMPONENT_PATHS")
            _component_paths_cache = FALLBACK_COMPONENT_PATHS
            return _component_paths_cache

        collection = settings.card_collection

        # Query for class-type points
        results, _ = client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="class"),
                    )
                ]
            ),
            limit=200,
            with_payload=True,
        )

        paths = {}
        for r in results:
            if not r.payload:
                continue

            full_path = r.payload.get("full_path") or r.payload.get("path")
            if not full_path:
                continue

            # Only include v2 widget/structure classes
            if not any(x in full_path for x in ["v2.widgets", "v2.section", "v2.card"]):
                continue

            # Extract short name
            short_name = full_path.rsplit(".", 1)[-1]

            # Skip internal/enum classes
            skip_names = {
                "Widget", "Renderable", "Type", "Layout", "AutoNumber",
                "LoadIndicator", "Interaction", "OpenAs", "Union"
            }
            if short_name in skip_names:
                continue

            # Prefer more specific paths
            if short_name in paths:
                existing = paths[short_name]
                if full_path.count(".") > existing.count("."):
                    paths[short_name] = full_path
            else:
                paths[short_name] = full_path

        # Merge with fallbacks (fallbacks take precedence for stability)
        merged = {**paths, **FALLBACK_COMPONENT_PATHS}

        logger.info(f"✅ Dynamic COMPONENT_PATHS loaded: {len(merged)} components ({len(paths)} from Qdrant)")
        _component_paths_cache = merged
        return _component_paths_cache

    except Exception as e:
        logger.warning(f"Failed to load dynamic COMPONENT_PATHS: {e}, using fallback")
        _component_paths_cache = FALLBACK_COMPONENT_PATHS
        return _component_paths_cache


def get_dynamic_relationship_patterns(force_refresh: bool = False) -> Dict[Tuple[str, str], str]:
    """
    Get NL relationship patterns dynamically from Qdrant.

    Returns:
        Dict mapping (parent, child) tuples to NL descriptions, e.g.:
        {("Image", "OnClick"): "clickable image, image with click action"}
    """
    global _relationship_patterns_cache

    if _relationship_patterns_cache is not None and not force_refresh:
        return _relationship_patterns_cache

    try:
        from config.qdrant_client import get_qdrant_client
        from config.settings import settings
        from qdrant_client import models

        client = get_qdrant_client()
        if not client:
            logger.warning("Qdrant unavailable, using fallback NL_RELATIONSHIP_PATTERNS")
            _relationship_patterns_cache = FALLBACK_RELATIONSHIP_PATTERNS
            return _relationship_patterns_cache

        collection = settings.card_collection

        # Query for class-type points with relationships
        results, _ = client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="class"),
                    )
                ]
            ),
            limit=100,
            with_payload=True,
        )

        patterns = {}
        for r in results:
            if not r.payload:
                continue

            parent_name = r.payload.get("name", "")
            relationships = r.payload.get("relationships", {})

            if not relationships or not parent_name:
                continue

            child_classes = relationships.get("child_classes", [])
            if not child_classes:
                continue

            # Generate NL descriptions for each relationship
            for child in child_classes:
                key = (parent_name, child)
                nl = _generate_relationship_nl(parent_name, child)
                patterns[key] = nl

        # Merge with fallbacks (fallbacks take precedence)
        merged = {**patterns, **FALLBACK_RELATIONSHIP_PATTERNS}

        logger.info(f"✅ Dynamic NL_RELATIONSHIP_PATTERNS loaded: {len(merged)} patterns ({len(patterns)} from Qdrant)")
        _relationship_patterns_cache = merged
        return _relationship_patterns_cache

    except Exception as e:
        logger.warning(f"Failed to load dynamic NL_RELATIONSHIP_PATTERNS: {e}, using fallback")
        _relationship_patterns_cache = FALLBACK_RELATIONSHIP_PATTERNS
        return _relationship_patterns_cache


def _generate_relationship_nl(parent: str, child: str) -> str:
    """
    Generate natural language description for a parent-child relationship.

    Uses semantic templates based on common relationship types:
    - OnClick: "clickable X"
    - Icon: "X with icon"
    - Button: "X with button"
    - SwitchControl: "toggle X"
    - Generic: "X containing Y"
    """
    parent_lower = parent.lower()
    child_lower = child.lower()

    # Semantic templates for common relationships
    if child == "OnClick":
        return f"clickable {parent_lower}, {parent_lower} with click action, {parent_lower} that opens link"
    elif child == "Icon":
        return f"{parent_lower} with icon, icon {parent_lower}, {parent_lower} with start icon"
    elif child == "Button":
        return f"{parent_lower} with button, {parent_lower} with action button, {parent_lower} with clickable button"
    elif child == "SwitchControl":
        return f"{parent_lower} with switch, toggle {parent_lower}, {parent_lower} with toggle control"
    elif child == "Action":
        return f"{parent_lower} with action, {parent_lower} action handler"
    elif child == "Widget":
        return f"{parent_lower} containing widget, {parent_lower} with widget"
    else:
        return f"{parent_lower} with {child_lower}, {parent_lower} containing {child_lower}"


def invalidate_caches():
    """Invalidate all dynamic registry caches. Call after Qdrant data changes."""
    global _component_paths_cache, _relationship_patterns_cache, _known_icons_cache
    _component_paths_cache = None
    _relationship_patterns_cache = None
    _known_icons_cache = None
    logger.info("🔄 Dynamic registry caches invalidated")


# Cache for known icons
_known_icons_cache: Optional[Dict[str, str]] = None

# Hardcoded NL mappings for icons (semantic aliases)
# These map natural language terms to icon enum values
ICON_NL_MAPPINGS = {
    # People
    "person": "PERSON", "user": "PERSON", "profile": "PERSON", "account": "PERSON",
    "people": "MULTIPLE_PEOPLE", "team": "MULTIPLE_PEOPLE", "group": "MULTIPLE_PEOPLE",
    # Communication
    "email": "EMAIL", "mail": "EMAIL", "message": "EMAIL",
    "phone": "PHONE", "call": "PHONE",
    # Status
    "star": "STAR", "favorite": "STAR", "rating": "STAR",
    "check": "CONFIRMATION_NUMBER_ICON", "complete": "CONFIRMATION_NUMBER_ICON",
    "done": "CONFIRMATION_NUMBER_ICON", "success": "CONFIRMATION_NUMBER_ICON",
    "info": "DESCRIPTION", "information": "DESCRIPTION", "details": "DESCRIPTION",
    # Business
    "dollar": "DOLLAR", "money": "DOLLAR", "price": "DOLLAR", "cost": "DOLLAR",
    "store": "STORE", "shop": "STORE",
    "cart": "SHOPPING_CART", "shopping": "SHOPPING_CART",
    "membership": "MEMBERSHIP", "subscription": "MEMBERSHIP",
    # Time
    "clock": "CLOCK", "time": "CLOCK", "schedule": "CLOCK",
    "calendar": "EVENT_SEAT", "date": "EVENT_SEAT", "event": "EVENT_SEAT",
    # Travel
    "plane": "AIRPLANE", "flight": "AIRPLANE", "travel": "AIRPLANE",
    "arrival": "FLIGHT_ARRIVAL", "arriving": "FLIGHT_ARRIVAL",
    "departure": "FLIGHT_DEPARTURE", "departing": "FLIGHT_DEPARTURE",
    "car": "CAR", "drive": "CAR", "vehicle": "CAR",
    "bus": "BUS", "transit": "BUS",
    "train": "TRAIN", "rail": "TRAIN",
    "hotel": "HOTEL", "lodging": "HOTEL", "stay": "HOTEL",
    "room": "HOTEL_ROOM_TYPE", "room type": "HOTEL_ROOM_TYPE",
    "location": "MAP_PIN", "map": "MAP_PIN", "place": "MAP_PIN", "pin": "MAP_PIN",
    # Content
    "bookmark": "BOOKMARK", "save": "BOOKMARK", "saved": "BOOKMARK",
    "description": "DESCRIPTION", "document": "DESCRIPTION", "file": "DESCRIPTION",
    "video": "VIDEO_CAMERA", "camera": "VIDEO_CAMERA", "meeting": "VIDEO_CAMERA",
    "play": "VIDEO_PLAY", "media": "VIDEO_PLAY",
    "ticket": "TICKET", "pass": "TICKET", "admission": "TICKET",
    "invite": "INVITE", "invitation": "INVITE",
    "restaurant": "RESTAURANT_ICON", "food": "RESTAURANT_ICON", "dining": "RESTAURANT_ICON",
}


def get_dynamic_known_icons(force_refresh: bool = False) -> Dict[str, str]:
    """
    Get KNOWN_ICONS dynamically from the Icon.KnownIcon enum.

    Returns:
        Dict mapping NL terms to icon enum values, e.g.:
        {"person": "PERSON", "email": "EMAIL", ...}

    The mapping combines:
    1. Actual enum values (e.g., "PERSON" -> "PERSON")
    2. NL aliases (e.g., "user" -> "PERSON", "profile" -> "PERSON")
    """
    global _known_icons_cache

    if _known_icons_cache is not None and not force_refresh:
        return _known_icons_cache

    try:
        from card_framework.v2.widgets.icon import Icon

        KnownIcon = Icon.KnownIcon
        actual_icons = set(KnownIcon.__members__.keys())

        # Start with NL mappings
        icons = dict(ICON_NL_MAPPINGS)

        # Add direct enum value mappings (lowercase -> uppercase)
        for icon_name in actual_icons:
            lower_name = icon_name.lower().replace("_", " ")
            icons[lower_name] = icon_name
            # Also add without underscores
            icons[icon_name.lower()] = icon_name

        # Validate all mappings point to real icons
        valid_icons = {}
        for nl_term, icon_value in icons.items():
            if icon_value in actual_icons:
                valid_icons[nl_term] = icon_value
            else:
                logger.warning(f"⚠️ Icon mapping '{nl_term}' -> '{icon_value}' invalid (not in enum)")

        logger.info(f"✅ Dynamic KNOWN_ICONS loaded: {len(valid_icons)} mappings ({len(actual_icons)} actual icons)")
        _known_icons_cache = valid_icons
        return _known_icons_cache

    except Exception as e:
        logger.warning(f"Failed to load dynamic KNOWN_ICONS: {e}, using fallback")
        _known_icons_cache = ICON_NL_MAPPINGS
        return _known_icons_cache


def get_registry_stats() -> Dict[str, int]:
    """Get statistics about loaded registries."""
    return {
        "component_paths_cached": _component_paths_cache is not None,
        "component_paths_count": len(_component_paths_cache) if _component_paths_cache else 0,
        "relationship_patterns_cached": _relationship_patterns_cache is not None,
        "relationship_patterns_count": len(_relationship_patterns_cache) if _relationship_patterns_cache else 0,
    }
