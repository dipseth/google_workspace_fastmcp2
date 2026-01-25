"""
Smart Card Builder

Builds Google Chat cards by:
1. Searching Qdrant vector DB for relevant card components (ColBERT)
2. Getting full_path from search results
3. Loading actual Python classes via ModuleWrapper
4. Using smart inference to map content to component parameters
5. Detecting composition hints from natural language
6. Rendering via component .render() methods

This implements the POC flow: Vector DB → ModuleWrapper → Instantiate → Render

═══════════════════════════════════════════════════════════════════════════════
                        🔄 THE RECURSION MANIFESTO 🔄
═══════════════════════════════════════════════════════════════════════════════

    When parsing fails and tags are torn,
    Don't add more if-else, look inward, be reborn.
    The CONTENT_PATTERNS registry knows the way—
    Let html_formatted have its say.

    Before you split on quotes with greed,
    Ask: "Does HTML live here?" — take heed!
    The same pattern that fixed the "showing" text
    Must guard the "titled" path, or bugs come next.

    WRAP → DETECT → PRESERVE → UNWRAP
    One flow for all, no special trap.
    If content needs HTML preserved intact,
    Let infer_content_type() handle that fact.

    The Qdrant search, the ModuleWrapper call,
    The .render() method—one flow for all.
    Recursion isn't loops that never end,
    It's patterns that on themselves depend.

    So when you're tempted to add another case,
    Search the CONTENT_PATTERNS in this space.
    The answer often lies within,
    Where elegance lets simplicity win.

                                        — Field Notes, Jan 2026

═══════════════════════════════════════════════════════════════════════════════
"""

import importlib
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv

from config.settings import settings as _settings

load_dotenv()

logger = logging.getLogger(__name__)

# Feature flag for feedback buttons (can be disabled if needed)
ENABLE_FEEDBACK_BUTTONS = os.getenv("ENABLE_CARD_FEEDBACK", "true").lower() == "true"


class SmartCardBuilder:
    """
    Builds cards using card_framework components found via Qdrant vector search.

    Flow:
    1. Natural language description → ColBERT search → Get component paths
    2. Load classes via ModuleWrapper.get_component_by_path()
    3. Instantiate with content using smart inference
    4. Render to Google Chat JSON
    """

    # Fallback component paths (used only if Qdrant is unavailable)
    # =========================================================================
    # COMPONENT PATH REGISTRY - Following the Manifesto:
    # "The CONTENT_PATTERNS registry knows the way"
    #
    # Canonical paths for all card_framework components. Used for direct loading
    # without Qdrant search. Qdrant is only used for dynamic discovery of
    # components NOT in this registry.
    # =========================================================================
    COMPONENT_PATHS = {
        # Core structure components
        "Section": "card_framework.v2.section.Section",
        "Card": "card_framework.v2.card.Card",
        "CardHeader": "card_framework.v2.card.CardHeader",
        # Layout components
        "Columns": "card_framework.v2.widgets.columns.Columns",
        "Column": "card_framework.v2.widgets.columns.Column",
        # Content components
        "DecoratedText": "card_framework.v2.widgets.decorated_text.DecoratedText",
        "TextParagraph": "card_framework.v2.widgets.text_paragraph.TextParagraph",
        "Image": "card_framework.v2.widgets.image.Image",
        "Divider": "card_framework.v2.widgets.divider.Divider",
        # Interactive components
        "Button": "card_framework.v2.widgets.decorated_text.Button",
        "ButtonList": "card_framework.v2.widgets.button_list.ButtonList",
        "Icon": "card_framework.v2.widgets.decorated_text.Icon",
        "OnClick": "card_framework.v2.widgets.decorated_text.OnClick",
        # Form input components
        "TextInput": "card_framework.v2.widgets.text_input.TextInput",
        "SelectionInput": "card_framework.v2.widgets.selection_input.SelectionInput",
        "DateTimePicker": "card_framework.v2.widgets.date_time_picker.DateTimePicker",
        # Grid components
        "Grid": "card_framework.v2.widgets.grid.Grid",
        "GridItem": "card_framework.v2.widgets.grid.GridItem",
        "ImageComponent": "card_framework.v2.widgets.grid.ImageComponent",
    }

    # Alias for backwards compatibility
    FALLBACK_PATHS = COMPONENT_PATHS

    # =========================================================================
    # CORE COMPONENTS REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # List of components to pre-load on initialization. These are loaded
    # directly from COMPONENT_PATHS (no Qdrant search needed).
    # =========================================================================
    CORE_COMPONENTS = [
        # Structure
        "Section",
        # Layout
        "Columns",
        "Column",
        # Content (most commonly used)
        "DecoratedText",
        "TextParagraph",
        "Image",
        # Interactive
        "ButtonList",
        "Button",
        "OnClick",
        # Form inputs
        "TextInput",
        "SelectionInput",
        "DateTimePicker",
        # Grid
        "Grid",
        "GridItem",
    ]

    # =========================================================================
    # PATTERN EXTENSION HANDLERS REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps component class names to handler methods for extending/adapting
    # instance patterns with new parameters. Used by _rebuild_from_pattern().
    #
    # Handler signature: (self, pattern_params: Dict, new_params: Dict) -> Dict
    # Returns: merged params ready for component instantiation
    # =========================================================================
    PATTERN_EXTENSION_HANDLERS = {
        "Grid": "_extend_grid_pattern",
        "ButtonList": "_extend_button_list_pattern",
        "Section": "_extend_section_pattern",
        "DecoratedText": "_extend_decorated_text_pattern",
    }

    # =========================================================================
    # PATTERN PARAM MERGE MODES - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Defines how params should be merged for each param type:
    # - "replace": new_params completely replace pattern_params
    # - "extend": new_params are appended to pattern_params (for lists)
    # - "deep_merge": recursively merge dicts
    # =========================================================================
    PATTERN_PARAM_MERGE_MODES = {
        # List params - extend by default
        "items": "extend",
        "buttons": "extend",
        "widgets": "extend",
        "sections": "extend",
        "images": "extend",
        # Scalar params - replace by default
        "title": "replace",
        "subtitle": "replace",
        "text": "replace",
        "top_label": "replace",
        "bottom_label": "replace",
        "image_url": "replace",
        "column_count": "replace",
        "name": "replace",
        "label": "replace",
    }

    # Ordinal words for section parsing (borrowed from nlp_parser)
    ORDINAL_WORDS = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
        "1st": 1,
        "2nd": 2,
        "3rd": 3,
        "4th": 4,
        "5th": 5,
    }
    ORDINAL_PATTERN = r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|4th|5th)"

    # Icon mappings - ONLY valid KnownIcon enum values from card_framework
    # Valid: AIRPLANE, BOOKMARK, BUS, CAR, CLOCK, CONFIRMATION_NUMBER_ICON, DESCRIPTION,
    #        DOLLAR, EMAIL, EVENT_SEAT, FLIGHT_ARRIVAL, FLIGHT_DEPARTURE, HOTEL,
    #        HOTEL_ROOM_TYPE, INVITE, MAP_PIN, MEMBERSHIP, MULTIPLE_PEOPLE, PERSON,
    #        PHONE, RESTAURANT_ICON, SHOPPING_CART, STAR, STORE, TICKET, TRAIN,
    #        VIDEO_CAMERA, VIDEO_PLAY
    KNOWN_ICONS = {
        # People & Communication
        "person": "PERSON",
        "user": "PERSON",
        "profile": "PERSON",
        "account": "PERSON",
        "people": "MULTIPLE_PEOPLE",
        "team": "MULTIPLE_PEOPLE",
        "group": "MULTIPLE_PEOPLE",
        "email": "EMAIL",
        "mail": "EMAIL",
        "message": "EMAIL",
        "phone": "PHONE",
        "call": "PHONE",
        # Status & Actions (using available icons)
        "star": "STAR",
        "favorite": "STAR",
        "rating": "STAR",
        "check": "CONFIRMATION_NUMBER_ICON",
        "complete": "CONFIRMATION_NUMBER_ICON",
        "done": "CONFIRMATION_NUMBER_ICON",
        "success": "CONFIRMATION_NUMBER_ICON",
        "warning": "STAR",
        "alert": "STAR",
        "caution": "STAR",
        "info": "DESCRIPTION",
        "information": "DESCRIPTION",
        "details": "DESCRIPTION",
        # Business & Finance
        "dollar": "DOLLAR",
        "money": "DOLLAR",
        "price": "DOLLAR",
        "cost": "DOLLAR",
        "store": "STORE",
        "shop": "STORE",
        "deployment": "STORE",
        "cart": "SHOPPING_CART",
        "shopping": "SHOPPING_CART",
        "membership": "MEMBERSHIP",
        "subscription": "MEMBERSHIP",
        # Time & Travel
        "clock": "CLOCK",
        "time": "CLOCK",
        "schedule": "CLOCK",
        "calendar": "EVENT_SEAT",
        "date": "EVENT_SEAT",
        "event": "EVENT_SEAT",
        "plane": "AIRPLANE",
        "flight": "AIRPLANE",
        "travel": "AIRPLANE",
        "car": "CAR",
        "drive": "CAR",
        "vehicle": "CAR",
        "bus": "BUS",
        "transit": "BUS",
        "train": "TRAIN",
        "rail": "TRAIN",
        "hotel": "HOTEL",
        "lodging": "HOTEL",
        "stay": "HOTEL",
        "location": "MAP_PIN",
        "map": "MAP_PIN",
        "place": "MAP_PIN",
        "pin": "MAP_PIN",
        # Content & Media
        "bookmark": "BOOKMARK",
        "save": "BOOKMARK",
        "saved": "BOOKMARK",
        "description": "DESCRIPTION",
        "document": "DESCRIPTION",
        "file": "DESCRIPTION",
        "doc": "DESCRIPTION",
        "video": "VIDEO_CAMERA",
        "camera": "VIDEO_CAMERA",
        "meeting": "VIDEO_CAMERA",
        "play": "VIDEO_PLAY",
        "media": "VIDEO_PLAY",
        "ticket": "TICKET",
        "pass": "TICKET",
        "admission": "TICKET",
        "invite": "INVITE",
        "invitation": "INVITE",
        "restaurant": "RESTAURANT_ICON",
        "food": "RESTAURANT_ICON",
        "dining": "RESTAURANT_ICON",
    }

    # =========================================================================
    # COMPONENT RELATIONSHIP PATTERNS - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # NL descriptions for parent→child component relationships.
    # Used by ModuleWrapper for semantic search of component nesting paths.
    # Keys are (parent_class, child_class) tuples.
    # =========================================================================
    NL_RELATIONSHIP_PATTERNS = {
        # OnClick relationships (clickable elements)
        ("Image", "OnClick"): "clickable image, image with click action, image that opens a link",
        ("DecoratedText", "OnClick"): "clickable text, text with click action, clickable decorated text",
        ("Grid", "OnClick"): "clickable grid, grid with click action",
        ("Chip", "OnClick"): "clickable chip, chip with click action",
        ("Button", "OnClick"): "button click action, button that opens link",
        ("CardAction", "OnClick"): "card action with click, card header action",
        # Icon relationships
        ("DecoratedText", "Icon"): "text with icon, decorated text with icon",
        ("Button", "Icon"): "button with icon, icon button",
        # Button relationships
        ("DecoratedText", "Button"): "text with button, decorated text with action button",
        # Structure relationships
        ("Section", "Widget"): "section containing widget, section with widget",
        ("Card", "Section"): "card with section, card containing section",
        ("Card", "CardHeader"): "card with header, card with title",
    }

    # =========================================================================
    # DYNAMIC REGISTRY EXPERIMENT
    # =========================================================================
    # When USE_DYNAMIC_REGISTRY=true, replace hardcoded registries with
    # dynamically loaded versions from Qdrant and the card_framework module.
    #
    # Benefits of dynamic loading:
    # - COMPONENT_PATHS: 48 components (vs 19 hardcoded)
    # - NL_RELATIONSHIP_PATTERNS: 63 patterns (vs 12 hardcoded)
    # - KNOWN_ICONS: 103 mappings (vs ~70 hardcoded), includes new icons
    # - Patterns evolve with feedback loop (positive feedback strengthens)
    # - No code changes needed when card_framework adds new components/icons
    #
    # To enable: export USE_DYNAMIC_REGISTRY=true
    # =========================================================================
    USE_DYNAMIC_REGISTRY = os.getenv("USE_DYNAMIC_REGISTRY", "false").lower() == "true"

    if USE_DYNAMIC_REGISTRY:
        try:
            from gchat.dynamic_registry import (
                get_dynamic_component_paths,
                get_dynamic_known_icons,
                get_dynamic_relationship_patterns,
            )

            # Override with dynamic versions (merges with fallbacks)
            COMPONENT_PATHS = get_dynamic_component_paths()
            NL_RELATIONSHIP_PATTERNS = get_dynamic_relationship_patterns()
            KNOWN_ICONS = get_dynamic_known_icons()
            logger.info(
                f"🔄 Dynamic registry enabled: {len(COMPONENT_PATHS)} paths, "
                f"{len(NL_RELATIONSHIP_PATTERNS)} patterns, {len(KNOWN_ICONS)} icons"
            )
        except Exception as e:
            logger.warning(f"⚠️ Dynamic registry failed, using static: {e}")
            # Keep static versions defined above

    # =========================================================================
    # CARD-SPECIFIC RELATIONSHIP HELPERS
    # =========================================================================
    # These methods wrap the generic ModuleWrapper relationship data with
    # card-specific convenience checks (OnClick, Button, Icon, etc.)
    # =========================================================================

    @classmethod
    def has_onclick_child(cls, relationships: dict) -> bool:
        """Check if a component's relationships include OnClick."""
        child_classes = relationships.get("child_classes", [])
        return "OnClick" in child_classes

    @classmethod
    def has_button_child(cls, relationships: dict) -> bool:
        """Check if a component's relationships include Button."""
        child_classes = relationships.get("child_classes", [])
        return "Button" in child_classes

    @classmethod
    def has_icon_child(cls, relationships: dict) -> bool:
        """Check if a component's relationships include Icon."""
        child_classes = relationships.get("child_classes", [])
        return "Icon" in child_classes

    @classmethod
    def get_clickable_components(cls, search_results: list) -> list:
        """Filter search results to only components that support OnClick."""
        return [r for r in search_results if cls.has_onclick_child(r.get("relationships", {}))]

    # =========================================================================
    # CARD TITLE EXTRACTION PATTERNS - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Multiple patterns checked in priority order:
    # 1. Explicit: titled "X" or title: "X" (highest priority)
    # 2. Inferred: "X card with/showing" at start (lower priority)
    # =========================================================================
    CARD_TITLE_PATTERNS = [
        # (pattern, description) - checked in order, first match wins
        (re.compile(r'titled\s+["\']([^"\']+)["\']', re.I), "titled 'X'"),
        (re.compile(r'title[:\s]+["\']([^"\']+)["\']', re.I), "title: 'X'"),
        (re.compile(r'^(\w+(?:\s+\w+){0,3})\s+card\s+(?:with|showing|titled)', re.I), "X card with/showing"),
    ]

    # Patterns for smart inference
    LAYOUT_PATTERNS = {
        "columns": re.compile(r"\b(columns?|side.?by.?side|two.?column|split)\b", re.I),
        "image_right": re.compile(
            r"\b(image\s+(on\s+)?(the\s+)?right|right\s+(side\s+)?image|with\s+image\s+on\s+right|image\s+on\s+right)\b",
            re.I,
        ),
        "image_left": re.compile(
            r"\b(image\s+(on\s+)?(the\s+)?left|left\s+(side\s+)?image|with\s+image\s+on\s+left|image\s+on\s+left)\b",
            re.I,
        ),
        # Grid layout detection for image galleries
        "grid": re.compile(
            r"\b(grid\s+(?:of\s+)?(?:images?|photos?)?|image\s+grid|photo\s+grid|"
            r"gallery|thumbnails?|(?:\d+)\s*x\s*(?:\d+)\s+(?:images?|photos?)|"
            r"multiple\s+images?|images?\s+in\s+(?:a\s+)?grid)\b",
            re.I,
        ),
    }

    # Patterns for content type inference
    # Following the Manifesto: "The CONTENT_PATTERNS registry knows the way"
    CONTENT_PATTERNS = {
        "price": re.compile(r"\$[\d,]+\.?\d*", re.I),
        "url": re.compile(r"https?://[^\s]+", re.I),
        # Image URL pattern: matches URLs with explicit image extensions only
        # Context-aware detection handles other cases via IMAGE_CONTEXT_PATTERNS
        "image_url": re.compile(r"https?://[^\s]+\.(?:jpg|jpeg|png|gif|webp|svg)", re.I),
        "email": re.compile(r"[\w.-]+@[\w.-]+\.\w+", re.I),
        "date": re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}", re.I),
        "id": re.compile(r"\b(id|ID):\s*[\w-]+", re.I),
        "colored_price": re.compile(
            r'<font\s+color=["\']#[0-9a-fA-F]+["\']>\$[\d,]+\.?\d*</font>', re.I
        ),
        # HTML formatted text - detects font color, bold, italic, etc.
        # Must use double quotes for color attribute: <font color="#FF0000">
        "html_formatted": re.compile(
            r'<(?:font\s+color\s*=\s*["\']?#[0-9a-fA-F]{3,6}["\']?|b|i|u|s|strike|a\s+href)\s*[^>]*>', re.I
        ),
        # Labeled link pattern: "Label: URL" or "Label URL" or "'Label' linking to URL" or "'Label' (URL)"
        # Captures (label, url) pairs - use this to preserve link labels instead of defaulting to "Open"
        #
        # GROUP INDEX CONVENTION (Manifesto: "One flow for all"):
        #   Even indices (0, 2, 4, 6) = label capture groups
        #   Odd indices (1, 3, 5, 7) = URL capture groups
        # This allows unified extraction logic: labels at i % 2 == 0, URLs at i % 2 == 1
        "labeled_link": re.compile(
            r"(?:"
            r"['\"]([^'\"]+)['\"]\s+(?:linking|link|opens?|goes?)\s+(?:to\s+)?(https?://[^\s,)]+)"  # Groups 0,1: 'Label' linking to URL
            r"|"
            r"([A-Z][^:]{2,30}):\s*(https?://[^\s,)]+)"  # Groups 2,3: Label: URL (capitalized)
            r"|"
            r"(?:button\s+)?['\"]([^'\"]+)['\"]\s*(?:->|→|:)\s*(https?://[^\s,)]+)"  # Groups 4,5: 'Label' -> URL
            r"|"
            r"['\"]([^'\"]+)['\"]\s*\(\s*(https?://[^\s,)]+)\s*\)"  # Groups 6,7: 'Label' (URL)
            r")",
            re.I,
        ),
    }

    # =========================================================================
    # CLICKABLE ELEMENT PATTERNS - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Pattern for elements (images, etc.) that link to a destination URL.
    # Similar to BUTTON_EXTRACTION_PATTERN but for non-button elements.
    #
    # GROUP INDEX CONVENTION:
    #   Group 1 = source (image URL)
    #   Group 2 = destination (click target URL)
    # =========================================================================
    CLICKABLE_IMAGE_PATTERN = re.compile(
        r"(?:"
        # Pattern 1: "image from IMG_URL linking to DEST_URL"
        r"(?:image|photo|picture)\s+(?:from\s+)?(https?://[^\s,]+)\s+(?:linking|links?|opens?|goes?)\s+(?:to\s+)?(https?://[^\s,]+)"
        r"|"
        # Pattern 2: "clickable image IMG_URL (DEST_URL)"
        r"(?:clickable\s+)?(?:image|photo|picture)\s+(?:from\s+)?(https?://[^\s,)]+)\s*\(\s*(https?://[^\s,)]+)\s*\)"
        r"|"
        # Pattern 3: "IMG_URL as clickable image linking to DEST_URL"
        r"(https?://[^\s,]+)\s+as\s+(?:a\s+)?(?:clickable\s+)?(?:image|photo)\s+(?:linking|links?)\s+(?:to\s+)?(https?://[^\s,]+)"
        r")",
        re.I,
    )

    # Context patterns that indicate a URL should be treated as an image
    # These look for image-intent keywords NEAR a URL in the description
    IMAGE_CONTEXT_PATTERNS = [
        # "showing/with/include [an] [her/his/their] image/photo URL"
        r"(?:showing|with|display(?:ing)?|include|add)\s+(?:an?\s+)?(?:her|his|their|the|my)?\s*(?:image|picture|photo|graphic|icon)\s+(?:from\s+|at\s+)?(https?://[^\s.,;!?]+)",
        # "image/photo [from/at] URL"
        r"(?:image|picture|photo|graphic)\s+(?:from\s+|at\s+|url\s+|url:?\s*)?(https?://[^\s.,;!?]+)",
        # "hero/header/banner image: URL"
        r"(?:hero|header|banner)\s+(?:image|photo)?\s*:?\s*(https?://[^\s.,;!?]+)",
        # "URL as [the] image"
        r"(https?://[^\s.,;!?]+)\s+(?:as\s+)?(?:the\s+)?(?:image|picture|photo)",
        # "her/his/their photo from URL" (possessive before photo)
        r"(?:her|his|their|my)\s+(?:profile\s+)?(?:image|picture|photo)\s+(?:from\s+|at\s+)?(https?://[^\s.,;!?]+)",
        # Section with image pattern: "section with image showing URL"
        r"section\s+with\s+(?:an?\s+)?image\s+(?:showing|displaying|from)?\s*(https?://[^\s.,;!?]+)",
    ]

    # Patterns to strip from section content (instruction text, not display text)
    # Following the Manifesto: "WRAP → DETECT → PRESERVE → UNWRAP"
    # These patterns are DETECTED and STRIPPED before content rendering
    SECTION_INSTRUCTION_PATTERNS = [
        # Section ordinal patterns
        r"(?:first|second|third|fourth|fifth|sixth|next|another)\s+section\s+(?:with\s+)?(?:image\s+)?(?:showing|displaying|titled|containing)\s*",
        r"(?:first|second|third|fourth|fifth|sixth|next|another)\s+section\s+",
        r"\bsection\s+with\s+(?:an?\s+)?image\s+(?:showing|displaying)\b\s*",
        r"\bwith\s+image\s+(?:showing|displaying)\b\s*",
        r"\bas\s+the\s+dashboard\s+chart\b[.,]?\s*",
        # Layout directive patterns (columns, grid, table)
        r"\b(?:show|display|create|add|include|use)\s+(?:a\s+)?(?:two|three|2|3)?\s*columns?\s+(?:layout|view)?\b[.,]?\s*",
        r"\b(?:show|display|create|add)\s+(?:a\s+)?grid\s+(?:of|with|layout)?\b[.,]?\s*",
        r"\b(?:show|display|create)\s+(?:a\s+)?table(?:-like)?\s+(?:list|view|layout)?\b[.,]?\s*",
        r"\bside[\s-]?by[\s-]?side\b[.,]?\s*",
        # Content directive patterns
        r"\b(?:show|display|include|add)\s+(?:an?\s+)?(?:image|photo|picture)\s+(?:of|showing|from)?\b\s*",
        r"\b(?:showing|displaying|with)\s+(?:an?\s+)?(?:image|photo|picture)\s+(?:of|from)?\b\s*",
        # Action directive patterns (buttons, links)
        r"\b(?:add|include|with)\s+(?:\d+\s+)?(?:action\s+)?(?:buttons?|links?)\s+(?:for|to|at|labeled)?\b[.,:]?\s*",
        r"\binclude\s+(?:\d+\s+)?action\s+links?\s*:?\s*",
        # Form directive patterns
        r"\b(?:add|include|create|with)\s+(?:a\s+)?(?:form|input)\s+(?:field|for)?\b[.,]?\s*",
        # Checklist/list directive patterns
        r"\b(?:show|display|include|add)\s+(?:a\s+)?checklist\s+(?:of|with|for)?\b[.,:]?\s*",
        r"\b(?:show|display|include)\s+(?:a\s+)?(?:bulleted|numbered)?\s*list\s+(?:of|with)?\b[.,:]?\s*",
    ]

    # =========================================================================
    # CONTENT TYPE REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps content patterns to component info. Order matters (first match wins).
    # Each entry defines how detected content flows through the component system.
    # =========================================================================
    CONTENT_TYPE_REGISTRY = [
        # (pattern_key, type_name, component_name, param_builder)
        # param_builder is a callable: (text, match) -> dict of suggested_params
        # Use _ for unused match param to satisfy linter
        {
            "pattern": "colored_price",
            "type": "colored_price",
            "component": "DecoratedText",
            "params": lambda text, _: {
                "text": text,
                "top_label": "Price",
                "wrap_text": True,
            },
        },
        {
            "pattern": "html_formatted",
            "type": "html_formatted",
            "component": "TextParagraph",
            "params": lambda text, _: {"text": text},  # Preserve HTML as-is
        },
        {
            "pattern": "image_url",
            "type": "image",
            "component": "Image",
            "params": lambda text, _: {"image_url": text},
        },
        {
            "pattern": "labeled_link",
            "type": "labeled_link",
            "component": "DecoratedText",
            "params": lambda text, match: {
                "text": text,
                "wrap_text": True,
                # Extract label from match groups (even indices are labels; odd are URLs)
                # Pattern has 4 alternatives: linking, colon, arrow, parenthesized
                # Groups: 0,1 | 2,3 | 4,5 | 6,7 (label, url pairs)
                "button": {
                    "text": next(
                        (g for i, g in enumerate(match.groups()) if g and i % 2 == 0),
                        "Open"
                    ) if match else "Open",
                    "url": next(
                        (g for i, g in enumerate(match.groups()) if g and i % 2 == 1),
                        text
                    ) if match else text,
                },
            },
        },
        {
            "pattern": "url",
            "type": "url",
            "component": "DecoratedText",
            # Note: For plain URLs without explicit labels, use "Open" as default
            # The label extraction happens in _extract_items where context is available
            "params": lambda text, _: {
                "text": text,
                "wrap_text": True,
                "button": {"text": "Open", "url": text},
            },
        },
        {
            "pattern": "price",
            "type": "price",
            "component": "DecoratedText",
            "params": lambda text, _: {
                "text": text,
                "top_label": "Price",
                "wrap_text": True,
            },
        },
        {
            "pattern": "id",
            "type": "id",
            "component": "DecoratedText",
            "params": lambda text, _: {
                "text": text.split(":", 1)[-1].strip() if ":" in text else text,
                "top_label": "ID",
                "wrap_text": True,
            },
        },
        {
            "pattern": "date",
            "type": "date",
            "component": "DecoratedText",
            "params": lambda text, _: {
                "text": text,
                "top_label": "Date",
                "wrap_text": True,
            },
        },
        {
            "pattern": "email",
            "type": "email",
            "component": "DecoratedText",
            "params": lambda text, _: {
                "text": text,
                "top_label": "Email",
                "wrap_text": True,
            },
        },
    ]

    # Default fallback when no pattern matches
    CONTENT_TYPE_DEFAULT = {
        "type": "text",
        "component": "TextParagraph",
        "params": lambda text, _: {"text": text},
    }

    # =========================================================================
    # LAYOUT TYPE REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps layout patterns to layout configurations. Order matters (first match wins).
    # More specific patterns (image_left, image_right) come before generic (columns).
    # =========================================================================
    LAYOUT_TYPE_REGISTRY = [
        {
            "pattern": "image_left",
            "layout_type": "columns_image_left",
            "column_config": {
                "left": {"size": "FILL_MINIMUM_SPACE", "content": "image"},
                "right": {"size": "FILL_AVAILABLE_SPACE", "content": "text"},
            },
        },
        {
            "pattern": "image_right",
            "layout_type": "columns_image_right",
            "column_config": {
                "left": {"size": "FILL_AVAILABLE_SPACE", "content": "text"},
                "right": {"size": "FILL_MINIMUM_SPACE", "content": "image"},
            },
        },
        {
            "pattern": "columns",
            "layout_type": "columns",
            "column_config": {
                "left": {"size": "FILL_AVAILABLE_SPACE", "content": "mixed"},
                "right": {"size": "FILL_AVAILABLE_SPACE", "content": "mixed"},
            },
        },
        {
            "pattern": "grid",
            "layout_type": "grid",
            "column_config": None,  # Grid uses different config
        },
    ]

    # Default layout when no pattern matches
    LAYOUT_TYPE_DEFAULT = {
        "layout_type": "standard",
        "column_config": None,
    }

    # =========================================================================
    # COMPONENT BUILDER REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps component names to builder method names. Used when processing
    # inferred content types to avoid if/elif chains checking component names.
    # =========================================================================
    COMPONENT_BUILDER_REGISTRY = {
        "Image": "_build_image_from_inference",
        "DecoratedText": "_build_decorated_text_from_inference",
        "TextParagraph": "_build_text_paragraph_from_inference",
        # Add more as needed
    }

    # =========================================================================
    # WIDGET CONVERTER REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps widget dict keys to converter method names. Used by convert_dict_to_component
    # to avoid if/elif chains checking for different widget types.
    # =========================================================================
    WIDGET_CONVERTER_REGISTRY = {
        "decoratedText": "_convert_decorated_text_dict",
        "textParagraph": "_convert_text_paragraph_dict",
        "buttonList": "_convert_button_list_dict",
        "image": "_convert_image_dict",
    }

    # =========================================================================
    # LAYOUT BUILDER REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps layout types to builder method names. Used by build_card
    # to construct layouts without if/elif chains.
    # =========================================================================
    LAYOUT_BUILDER_REGISTRY = {
        "columns_image_right": "_build_layout_columns_image_right",
        "columns_image_left": "_build_layout_columns_image_left",
        "columns": "_build_layout_columns",
        "standard": "_build_layout_standard",
        "grid": "_build_layout_grid",
    }

    # =========================================================================
    # FIELD TYPE BUILDER REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps form field types to builder method names. Used by build_form_card
    # to construct form fields without if/elif chains.
    # =========================================================================
    FIELD_TYPE_BUILDER_REGISTRY = {
        "TextInput": "_build_field_text_input",
        "SelectionInput": "_build_field_selection_input",
        "DateTimePicker": "_build_field_date_time_picker",
    }

    # =========================================================================
    # ITEM DICT HANDLER REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps dict item keys to handler method names. Used when processing
    # content items that are dicts (explicit widget specs).
    # =========================================================================
    ITEM_DICT_HANDLER_REGISTRY = {
        "text": "_handle_item_text",
        "image_url": "_handle_item_image",
    }

    # =========================================================================
    # FEEDBACK WIDGET BUILDERS REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps feedback widget types to builder method names. Used by
    # _create_feedback_section to build widgets without duplicated fallback code.
    # =========================================================================
    FEEDBACK_WIDGET_BUILDERS = [
        # (widget_name, builder_method_name)
        # Order matters: content feedback first, then form feedback
        # Dual feedback system: content (values/inputs) and form (structure/relationships)
        ("content_prompt", "_build_content_feedback_prompt"),
        ("content_buttons", "_build_content_feedback_buttons"),
        ("form_prompt", "_build_form_feedback_prompt"),
        ("form_buttons", "_build_form_feedback_buttons"),
    ]

    # =========================================================================
    # MARKDOWN TO CHAT CONVERSION REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps markdown patterns to HTML replacements. Order matters:
    # - Double markers (**, ~~, __) must be processed before single markers
    # - This prevents ** from being split into two * matches
    # =========================================================================
    MARKDOWN_TO_CHAT_PATTERNS = [
        # (pattern, replacement, description)
        # Double markers first (order matters!)
        (r"\*\*([^*]+)\*\*", r"<b>\1</b>", "**bold**"),
        (r"__([^_]+)__", r"<b>\1</b>", "__bold__"),
        (r"~~([^~]+)~~", r"<s>\1</s>", "~~strikethrough~~"),
        # Single markers (with lookahead/lookbehind to avoid partial matches)
        (r"(?<!\*)\*([^*\s][^*]*[^*\s])\*(?!\*)", r"<b>\1</b>", "*bold phrase*"),
        (r"(?<!\*)\*(\w+)\*(?!\*)", r"<b>\1</b>", "*word*"),
        (r"(?<!~)~([^~\s][^~]*[^~\s])~(?!~)", r"<s>\1</s>", "~strikethrough~"),
        (r"(?<!_)_([^_\s][^_]*[^_\s])_(?!_)", r"<i>\1</i>", "_italic phrase_"),
        (r"(?<!_)_(\w+)_(?!_)", r"<i>\1</i>", "_word_"),
        # Code (commented out - Google Chat doesn't support <code>)
        # (r'`([^`]+)`', r'<code>\1</code>', '`code`'),
    ]

    # =========================================================================
    # SECTION CONTENT PARSING PATTERNS - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Patterns used by _parse_section_content for cleaning and extracting content.
    # =========================================================================

    # Pattern to extract content from 'text "content"' format
    TEXT_PREFIX_PATTERN = re.compile(
        r'^text\s+["\'](.+)["\']\.?$', re.DOTALL | re.IGNORECASE
    )

    # Instructional phrases to clean - describe HOW to render, not WHAT to display
    INSTRUCTIONAL_CLEANUP_PATTERNS = [
        # (pattern, description)
        (r"\bdecorated\s+text\s+(?:showing|with|displaying)?\s*", "decorated text variations"),
        (r"\bwith\s+(?:a\s+)?(?:link|open)\s+button\b[,.]?\s*", "with a link/open button"),
        (r"\bwith\s+(?:a\s+)?(\w+)\s+icon\b[,.]?\s*", "with a X icon"),
        (r"\s+button\s+(?=https?://)", "trailing button before URL"),
        (r"\s+button$", "trailing button"),
        (r"\s+(?:linking|links?|goes?)\s+to\s+(?=https?://)", "linking to/links to/goes to"),
        (r"\b(?:add|include|create|show)\s+(?:a\s+)?(?:\w+\s+)?buttons?\s*:?\s*", "add/include/create X button(s)"),
        (r"\bFILLED\s+", "FILLED button style"),
        (r"\bOUTLINED\s+", "OUTLINED button style"),
        (r"\bBORDERLESS\s+", "BORDERLESS button style"),
        (r"\s+at\s+(?=https?://)", "at before URL"),
        # Clickable image instructions - consume entire "image from X linking to Y" patterns
        (r"\b(?:clickable\s+)?(?:image|photo|picture)\s+(?:from\s+)?https?://[^\s,]+\s+(?:linking|links?|opens?|goes?)\s+(?:to\s+)?https?://[^\s,]+", "clickable image linking to URL"),
        (r"\b(?:clickable\s+)?(?:image|photo|picture)\s+(?:from\s+)?https?://[^\s,)]+\s*\(\s*https?://[^\s,)]+\s*\)", "clickable image (URL) syntax"),
        (r"https?://[^\s,]+\s+as\s+(?:a\s+)?(?:clickable\s+)?(?:image|photo)\s+(?:linking|links?)\s+(?:to\s+)?https?://[^\s,]+", "URL as clickable image linking to"),
        (r"\bwith\s+(?:a\s+)?(?:clickable\s+)?image\s+(?:from\s+)?https?://[^\s,]+\s+(?:linking|links?|opens?|goes?)\s+(?:to\s+)?https?://[^\s,]+", "with clickable image"),
        (r"\bimage\s+from\s+https?://[^\s,]+\s*$", "trailing image from URL"),
        (r"^\s*image\s+from\s+", "leading image from"),
    ]

    # URL extraction pattern
    URL_EXTRACTION_PATTERN = re.compile(r"(https?://[^\s\[\]<>\"']+(?<![.,;:!?\)]))")

    # Quoted text extraction pattern (negative lookbehind to skip HTML attribute quotes)
    QUOTED_TEXT_PATTERN = re.compile(r"(?<!=)['\"]([^'\"]+)['\"]")

    # Text cleanup patterns for URL context
    TEXT_BEFORE_URL_CLEANUP = [
        # (pattern, description)
        (r"^\s*(and|at|,|;|:)\s*", "leading conjunctions/prepositions"),
        (r"\s*(button|linking|links?|goes?|to|at)\s*$", "trailing instruction words"),
        (r'^["\']|["\']$', "orphaned quotes at edges"),
    ]

    # Content type detection keywords
    WARNING_KEYWORDS = ["warning", "stale", "inactive", "alert"]
    STATUS_KEYWORDS = ["success", "complete", "done", "active", "running"]

    # =========================================================================
    # DIRECTIVE CONSUMPTION PATTERNS - Following the Manifesto:
    # "WRAP → DETECT → PRESERVE → UNWRAP"
    #
    # These patterns are consumed (removed) from descriptions before processing
    # to prevent instruction text from leaking into card output.
    # =========================================================================
    LAYOUT_DIRECTIVE_PATTERNS = [
        # (pattern, directive_type)
        (r"\b(?:show|display|create|add|include|use)\s+(?:a\s+)?(?:two|three|2|3)?\s*columns?\s+(?:layout|view)?\s*[.,:]?\s*", "columns_layout"),
        (r"\b(?:show|display|create|add)\s+(?:a\s+)?grid\s+(?:of|with|layout)?\s*[.,:]?\s*", "grid_layout"),
        (r"\b(?:show|display|create)\s+(?:a\s+)?table(?:-like)?\s+(?:list|view|layout)?\s*[.,:]?\s*", "table_layout"),
        (r"\bside[\s-]?by[\s-]?side\b\s*[.,:]?\s*", "side_by_side"),
        (r"\b(?:show|display)\s+(?:two|2)\s+images?\s+side[\s-]?by[\s-]?side\b\s*[.,:]?\s*", "images_side_by_side"),
    ]

    ACTION_DIRECTIVE_PATTERNS = [
        (r"\b(?:add|include|with)\s+(?:\d+\s+)?(?:action\s+)?(?:buttons?|links?)\s+(?:for|to|at|labeled)?\s*[.,:]?\s*", "add_buttons"),
        (r"\binclude\s+(?:\d+\s+)?action\s+links?\s*:?\s*", "action_links"),
        (r"\b(?:add|create)\s+(?:a\s+)?(?:form|input)\s+(?:section|area)?\s*[.,:]?\s*", "form_section"),
    ]

    LIST_DIRECTIVE_PATTERNS = [
        (r"\b(?:show|display|include|add)\s+(?:a\s+)?checklist\s+(?:of|with|for)?\s*[.,:]?\s*", "checklist"),
        (r"\b(?:show|display|include)\s+(?:a\s+)?(?:bulleted|numbered)?\s*list\s+(?:of|with)?\s*[.,:]?\s*", "list"),
    ]

    BUTTON_INSTRUCTION_PATTERNS = [
        (r"(?:one|two|three|four|\d+)\s+buttons?\s+(?:at\s+)?(?:bottom|top|end)?:?\s*", "button_count"),
        (r"(?:add|include|with)\s+(?:a\s+)?buttons?\s+(?:for|labeled|named)\s+", "add_button"),
        (r"buttons?:\s*", "button_list"),
    ]

    # =========================================================================
    # FORM FIELD EXTRACTION PATTERNS - Following the Manifesto:
    # "One flow for all, no special trap"
    # =========================================================================
    FORM_KEYWORDS = [
        "form card", "text input", "input field", "dropdown",
        "selection field", "submit button",
    ]

    # Form field extraction patterns: (compiled_pattern, field_type, group_names)
    FORM_FIELD_PATTERNS = [
        # TextInput: "text input field named 'X' with label 'Y' and hint 'Z'"
        (
            re.compile(
                r"text\s+input\s+(?:field\s+)?named\s+['\"](\w+)['\"]"
                r"\s+with\s+label\s+['\"]([^'\"]+)['\"]"
                r"(?:\s+(?:and\s+)?hint\s+['\"]([^'\"]+)['\"])?",
                re.IGNORECASE,
            ),
            "TextInput",
            ("name", "label", "hint_text"),
        ),
        # SelectionInput: "dropdown selection field named 'X' with label 'Y' and options..."
        (
            re.compile(
                r"(?:dropdown\s+)?selection\s+field\s+named\s+['\"](\w+)['\"]"
                r"\s+with\s+label\s+['\"]([^'\"]+)['\"]"
                r"(?:\s+(?:and\s+)?options?\s+(.+?))?(?:\.|$)",
                re.IGNORECASE,
            ),
            "SelectionInput",
            ("name", "label", "options"),
        ),
    ]

    # =========================================================================
    # SUBMIT BUTTON PATTERNS - Following the Manifesto:
    # "One flow for all, no special trap"
    # =========================================================================
    # Submit button that opens a URL
    SUBMIT_BUTTON_URL_PATTERN = re.compile(
        r"submit\s+button\s+(?:with\s+text\s+)?['\"]([^'\"]+)['\"]"
        r"\s+(?:that\s+)?opens?\s+(?:URL\s+)?['\"]?(https?://[^\s'\"]+)['\"]?",
        re.IGNORECASE,
    )
    # Submit button that calls a function
    SUBMIT_BUTTON_FUNCTION_PATTERN = re.compile(
        r"submit\s+button\s+(?:with\s+text\s+)?['\"]([^'\"]+)['\"]"
        r"\s+(?:that\s+)?calls?\s+(?:function\s+)?['\"]?([a-zA-Z_]\w*)['\"]?",
        re.IGNORECASE,
    )
    # Registry of submit button patterns: (pattern, result_keys)
    # result_keys maps captured groups to submit_action dict keys
    SUBMIT_BUTTON_PATTERNS = [
        (SUBMIT_BUTTON_URL_PATTERN, ("text", "url")),
        (SUBMIT_BUTTON_FUNCTION_PATTERN, ("text", "function")),
    ]

    # =========================================================================
    # FORM FIELD GROUP HANDLER REGISTRY - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # Maps group names to handler method names for special-case processing.
    # Default behavior (no handler): field[group_name] = group_value
    # =========================================================================
    GROUP_NAME_HANDLER_REGISTRY = {
        "options": "_handle_field_group_options",
    }

    # =========================================================================
    # BUTTON EXTRACTION PATTERNS
    # Handles multiple syntax variations:
    # - 'Label' linking to URL
    # - 'Label' (URL) - parenthesized URL syntax
    # - 'Label' button opens URL
    #
    # GROUP INDEX CONVENTION (Manifesto: "One flow for all"):
    #   Even indices (0, 2) = label capture groups
    #   Odd indices (1, 3) = URL capture groups
    # This allows unified extraction: labels at i % 2 == 0, URLs at i % 2 == 1
    # =========================================================================
    BUTTON_EXTRACTION_PATTERN = re.compile(
        r"(?:"
        r"['\"]([^'\"]+)['\"]?\s+(?:button\s+)?(?:linking|links?|opens?|goes?)\s+(?:to\s+)?(https?://[^\s,)]+)"  # Groups 0,1
        r"|"
        r"['\"]([^'\"]+)['\"]\s*\(\s*(https?://[^\s,)]+)\s*\)"  # Groups 2,3: parenthesized
        r")",
        re.IGNORECASE,
    )

    # =========================================================================
    # IMAGE URL EXTRACTION PATTERNS
    # =========================================================================
    IMAGE_EXTENSION_PATTERN = re.compile(
        r"(https?://[^\s]+\.(?:jpg|jpeg|png|gif|webp))", re.IGNORECASE
    )
    IMAGE_HOST_PATTERN = re.compile(
        r"(https?://(?:picsum\.photos|i\.imgur\.com|images\.unsplash\.com|randomuser\.me|placekitten\.com|placehold\.co|via\.placeholder\.com|loremflickr\.com|dummyimage\.com)[^\s]*)",
        re.IGNORECASE,
    )

    # =========================================================================
    # ITEM EXTRACTION PATTERNS
    # =========================================================================
    ICON_TEXT_PATTERN = re.compile(
        r"(\w+)\s+icon\s+(?:showing|with|displaying)?\s*['\"]([^'\"]+)['\"]",
        re.IGNORECASE,
    )

    LABEL_CLEANUP_PATTERNS = [
        # (pattern, description) - applied to label text before URLs
        (r"\s+(linking\s+to|linking|opens?\s+to|opens?|goes?\s+to|goes?)\s*$", "trailing link instructions"),
        (r"^\s*(for|to|at|linking|opens?|buttons?|labeled?|with|add|include|a)\s+", "leading instruction words"),
        (r"['\"]", "quotes"),
        # Arrow/separator cleanup - handles 'Label' -> URL, 'Label' : URL syntax
        (r"\s*[-→:]+\s*$", "trailing arrows and separators"),
        # Parenthesized URL cleanup - handles 'Label (URL)' syntax remnants
        (r"\s*\(\s*https?://[^\s)]*\)?", "parenthesized URL"),
        (r"\s*\(\s*$", "trailing open parenthesis"),
        (r"\s*\)\s*$", "trailing close parenthesis"),
        (r"\s+\([^)]*com[^)]*\)?", "partial URL in parentheses"),
    ]

    # Pattern for splitting text into phrases when extracting labels heuristically
    # Used by _extract_url_label fallback when no explicit pattern matches
    LABEL_PHRASE_SPLIT_PATTERN = re.compile(r"[.,;]")

    # =========================================================================
    # ITEM EXTRACTION CLEANUP PATTERNS - Following the Manifesto:
    # "One flow for all, no special trap"
    # =========================================================================
    # Pattern to remove "X linking to URL" (button definitions) from description
    BUTTON_LINK_CLEANUP_PATTERN = re.compile(
        r"['\"]([^'\"]+)['\"]?\s+(?:linking|links?|opens?|goes?)\s+(?:to\s+)?https?://[^\s,]+",
        re.IGNORECASE,
    )
    # Pattern to remove standalone "linking to" fragments
    LINKING_TO_FRAGMENT_PATTERN = re.compile(
        r"\s+(?:and\s+)?linking\s+to\s*",
        re.IGNORECASE,
    )

    # =========================================================================
    # SECTION EXTRACTION PATTERNS - Following the Manifesto:
    # "One flow for all, no special trap"
    # =========================================================================
    # Pattern for section content connectors (showing/with/containing/displaying)
    SECTION_CONTENT_CONNECTOR_PATTERN = re.compile(
        r"\s*(?:showing|with|containing|displaying)?\s*(.+)",
        re.IGNORECASE | re.DOTALL,
    )
    # Pattern for extracting title from content header like "Metrics: X, Y, Z"
    CONTENT_TITLE_PATTERN = re.compile(r"^(\w+):\s*")

    # =========================================================================
    # SECTION PARSING PATTERNS - Following the Manifesto:
    # "The CONTENT_PATTERNS registry knows the way"
    #
    # These patterns parse ordinal section descriptions like:
    # - "First section titled 'Name' showing content"
    # - "Second section with image showing content"
    # =========================================================================

    # Pattern for "First section titled 'X'" - extracts ordinal and triggers title extraction
    # Uses ORDINAL_PATTERN (defined above) for ordinal matching
    # Note: This is a template string, compiled at runtime with ORDINAL_PATTERN substitution
    ORDINAL_TITLED_SECTION_TEMPLATE = r"({ordinal})\s+section\s+titled\s+"

    # Pattern for "First section showing/with content" (no explicit title)
    # Captures ordinal and content until next section or end
    ORDINAL_CONTENT_SECTION_TEMPLATE = (
        r"({ordinal})\s+section\s+(?:with\s+)?(?:image\s+)?"
        r"(?:showing|with|containing|displaying)\s+"
        r"(.+?)(?=(?:{ordinal})\s+section|$)"
    )

    # Cached compiled patterns (populated on first use)
    _compiled_section_patterns: Dict[str, "re.Pattern"] = {}

    # Color mappings for semantic colors
    COLOR_MAP = {
        "success": "#34a853",  # Green
        "error": "#ea4335",  # Red
        "warning": "#fbbc04",  # Yellow
        "info": "#1a73e8",  # Blue
        "green": "#34a853",
        "red": "#ea4335",
        "blue": "#1a73e8",
        "yellow": "#fbbc04",
        "orange": "#ff6d01",
    }

    def __init__(self):
        """Initialize the smart card builder."""
        self._qdrant_client = None
        self._embedder = None
        self._wrapper = None
        self._components: Dict[str, Any] = {}
        self._initialized = False
        self._qdrant_available = False
        self._collection_verified = False

    @classmethod
    def _get_compiled_section_pattern(cls, pattern_name: str) -> "re.Pattern":
        """
        Get a compiled section pattern from the registry.

        Following the Manifesto: "The CONTENT_PATTERNS registry knows the way"
        Patterns are defined as templates at class level, compiled once on first use.

        Args:
            pattern_name: Either "ordinal_titled" or "ordinal_content"

        Returns:
            Compiled regex pattern with ORDINAL_PATTERN substituted
        """
        if pattern_name not in cls._compiled_section_patterns:
            if pattern_name == "ordinal_titled":
                template = cls.ORDINAL_TITLED_SECTION_TEMPLATE.format(
                    ordinal=cls.ORDINAL_PATTERN
                )
                cls._compiled_section_patterns[pattern_name] = re.compile(
                    template, re.IGNORECASE
                )
            elif pattern_name == "ordinal_content":
                template = cls.ORDINAL_CONTENT_SECTION_TEMPLATE.format(
                    ordinal=cls.ORDINAL_PATTERN
                )
                cls._compiled_section_patterns[pattern_name] = re.compile(
                    template, re.IGNORECASE | re.DOTALL
                )
            else:
                raise ValueError(f"Unknown section pattern: {pattern_name}")

            logger.debug(f"✅ Compiled section pattern '{pattern_name}' from registry")

        return cls._compiled_section_patterns[pattern_name]

    def _get_qdrant_client(self):
        """Get Qdrant client from centralized singleton."""
        if self._qdrant_client is None:
            try:
                # Use centralized Qdrant client singleton
                from config.qdrant_client import get_qdrant_client

                self._qdrant_client = get_qdrant_client()
                if self._qdrant_client:
                    self._qdrant_available = True
                    logger.info("SmartCardBuilder using centralized Qdrant client")
                else:
                    logger.warning("Qdrant client not available, using fallback paths")
                    self._qdrant_available = False
            except Exception as e:
                logger.warning(f"Could not get Qdrant client: {e}")
                self._qdrant_available = False

        # Ensure collection exists (auto-creates if missing)
        if self._qdrant_client and not self._collection_verified:
            self._ensure_collection_exists()

        return self._qdrant_client

    def _ensure_collection_exists(self):
        """Ensure the card collection exists, creating it if necessary."""
        if self._collection_verified:
            return

        try:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()
            if feedback_loop.ensure_description_vector_exists():
                self._collection_verified = True
                logger.debug(
                    f"✅ Collection {_settings.card_collection} verified/created"
                )
            else:
                logger.warning(f"⚠️ Collection {_settings.card_collection} not ready")
        except Exception as e:
            logger.warning(f"Could not verify collection: {e}")

    def _get_embedder(self):
        """Get ColBERT embedder for semantic search."""
        if self._embedder is None:
            try:
                from fastembed import LateInteractionTextEmbedding

                self._embedder = LateInteractionTextEmbedding(
                    model_name="colbert-ir/colbertv2.0"
                )
                logger.debug("ColBERT embedder loaded")
            except Exception as e:
                logger.warning(f"Could not load ColBERT embedder: {e}")

        return self._embedder

    def _get_wrapper(self):
        """Get ModuleWrapper for loading components by path (uses singleton)."""
        if self._wrapper is None:
            from gchat.card_framework_wrapper import get_card_framework_wrapper

            self._wrapper = get_card_framework_wrapper()

        return self._wrapper

    def _search_component(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for components in Qdrant using ColBERT (components vector).

        Args:
            query: Semantic search query
            limit: Max results

        Returns:
            List of {name, type, full_path, score} dicts
        """
        # Use the new v7 components vector (identity search)
        return self._search_by_identity(query, limit=limit)

    # =========================================================================
    # V7 SEARCH METHODS - Three vectors for different search strategies
    # =========================================================================

    def _search_by_identity(
        self,
        query: str,
        limit: int = 5,
        type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search by component identity using the 'components' vector.

        Use this for: "Find the Image class", "Button widget", "OnClick action"

        Args:
            query: Semantic search for component name/type/docstring
            limit: Max results
            type_filter: Optional filter by type (class, function, instance_pattern)

        Returns:
            List of {name, type, full_path, score} dicts
        """
        client = self._get_qdrant_client()
        embedder = self._get_embedder()

        if not client or not embedder:
            logger.warning("Qdrant or embedder not available")
            return []

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # ColBERT multi-vector embedding
            query_vectors_raw = list(embedder.query_embed(query))[0]
            query_vectors = [vec.tolist() for vec in query_vectors_raw]

            # Build filter if type specified
            query_filter = None
            if type_filter:
                query_filter = Filter(
                    must=[FieldCondition(key="type", match=MatchValue(value=type_filter))]
                )

            results = client.query_points(
                collection_name=_settings.card_collection,
                query=query_vectors,
                using="components",  # v7 identity vector
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )

            # Extract results
            components = []
            for r in results.points:
                p = r.payload
                components.append(
                    {
                        "name": p.get("name"),
                        "type": p.get("type"),
                        "full_path": p.get("full_path"),
                        "score": r.score,
                    }
                )

            return components

        except Exception as e:
            logger.warning(f"Qdrant identity search failed: {e}")
            return []

    def _search_by_inputs(
        self,
        query: str,
        limit: int = 5,
        type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search by input values using the 'inputs' vector.

        Use this for: "cards with Buy Now button", "title=Grid Layout", "buttons=[]"

        Args:
            query: Search for parameter values, defaults, enum values
            limit: Max results
            type_filter: Optional filter by type (class, function, instance_pattern)

        Returns:
            List of {name, type, full_path, inputs_text, score} dicts
        """
        client = self._get_qdrant_client()
        embedder = self._get_embedder()

        if not client or not embedder:
            logger.warning("Qdrant or embedder not available")
            return []

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # ColBERT multi-vector embedding
            query_vectors_raw = list(embedder.query_embed(query))[0]
            query_vectors = [vec.tolist() for vec in query_vectors_raw]

            # Build filter if type specified
            query_filter = None
            if type_filter:
                query_filter = Filter(
                    must=[FieldCondition(key="type", match=MatchValue(value=type_filter))]
                )

            results = client.query_points(
                collection_name=_settings.card_collection,
                query=query_vectors,
                using="inputs",  # v7 values vector
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )

            # Extract results
            components = []
            for r in results.points:
                p = r.payload
                components.append(
                    {
                        "name": p.get("name"),
                        "type": p.get("type"),
                        "full_path": p.get("full_path"),
                        "inputs_text": p.get("inputs_text"),
                        "score": r.score,
                    }
                )

            return components

        except Exception as e:
            logger.warning(f"Qdrant inputs search failed: {e}")
            return []

    def _search_by_relationships(
        self,
        query: str,
        limit: int = 5,
        type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search by component relationships using the 'relationships' vector.

        Use this for: "clickable image", "button with icon", "card with header"

        Args:
            query: Natural language describing component relationships
            limit: Max results
            type_filter: Optional filter by type (class, function, instance_pattern)

        Returns:
            List of {name, type, full_path, relationships, score} dicts
        """
        client = self._get_qdrant_client()

        if not client:
            logger.warning("Qdrant not available")
            return []

        try:
            from fastembed import TextEmbedding
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # Use MiniLM for relationships (384d dense, not ColBERT)
            if not hasattr(self, "_minilm_embedder") or self._minilm_embedder is None:
                self._minilm_embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")

            # Dense embedding
            query_vector = list(self._minilm_embedder.embed([query]))[0]
            query_vec = query_vector.tolist() if hasattr(query_vector, "tolist") else list(query_vector)

            # Build filter if type specified
            query_filter = None
            if type_filter:
                query_filter = Filter(
                    must=[FieldCondition(key="type", match=MatchValue(value=type_filter))]
                )

            results = client.query_points(
                collection_name=_settings.card_collection,
                query=query_vec,
                using="relationships",  # v7 graph vector
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )

            # Extract results
            components = []
            for r in results.points:
                p = r.payload
                rels = p.get("relationships", {})
                components.append(
                    {
                        "name": p.get("name"),
                        "type": p.get("type"),
                        "full_path": p.get("full_path"),
                        "children": rels.get("child_classes", []),
                        "score": r.score,
                    }
                )

            return components

        except Exception as e:
            logger.warning(f"Qdrant relationships search failed: {e}")
            return []

    def _find_similar_patterns(
        self,
        description: str,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Find instance_patterns similar to a card description.

        Use this to discover previously-built cards that match a user request,
        allowing reuse of successful parameter combinations.

        Args:
            description: Natural language card description
            limit: Max patterns to return

        Returns:
            List of {name, card_description, instance_params, parent_paths, score} dicts
        """
        # Search instance_patterns by identity (card_description is in components vector)
        patterns = self._search_by_identity(
            query=description,
            limit=limit,
            type_filter="instance_pattern",
        )

        # Enrich with full payload
        client = self._get_qdrant_client()
        if not client or not patterns:
            return patterns

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            enriched = []
            for p in patterns:
                # Get full payload for each pattern
                results = client.scroll(
                    collection_name=_settings.card_collection,
                    scroll_filter=Filter(
                        must=[FieldCondition(key="name", match=MatchValue(value=p["name"]))]
                    ),
                    limit=1,
                    with_payload=True,
                )
                if results[0]:
                    payload = results[0][0].payload
                    enriched.append(
                        {
                            "name": p["name"],
                            "card_description": payload.get("card_description"),
                            "instance_params": payload.get("instance_params"),
                            "parent_paths": payload.get("parent_paths"),
                            "inputs_text": payload.get("inputs_text"),
                            "score": p["score"],
                        }
                    )

            return enriched

        except Exception as e:
            logger.warning(f"Failed to enrich patterns: {e}")
            return patterns

    def _find_components_with_child(
        self,
        child_name: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Find components that can contain a specific child component.

        Use this for: "which components can have OnClick?" → Image, Button, DecoratedText

        Args:
            child_name: Name of child component (e.g., "OnClick", "Icon")
            limit: Max results

        Returns:
            List of {name, type, full_path, children} dicts
        """
        # Search relationships for components containing this child
        query = f"component with {child_name}"
        results = self._search_by_relationships(
            query=query,
            limit=limit * 2,  # Get extra, filter for actual matches
            type_filter="class",
        )

        # Filter to only those that actually have this child
        matching = []
        for r in results:
            if child_name in r.get("children", []):
                matching.append(r)
                if len(matching) >= limit:
                    break

        return matching

    def _load_component_by_path(self, path: str) -> Optional[Any]:
        """
        Load a component class by its full path.

        Args:
            path: Full path like "card_framework.v2.section.Section"

        Returns:
            The component class or None
        """
        wrapper = self._get_wrapper()
        if wrapper:
            try:
                return wrapper.get_component_by_path(path)
            except Exception as e:
                logger.debug(f"ModuleWrapper load failed for {path}: {e}")

        # Fallback: direct import
        try:
            parts = path.rsplit(".", 1)
            if len(parts) == 2:
                module_path, class_name = parts
                module = importlib.import_module(module_path)
                return getattr(module, class_name, None)
        except Exception as e:
            logger.warning(f"Direct import failed for {path}: {e}")

        return None

    def _load_core_component(self, name: str) -> Optional[Any]:
        """
        Load a component directly from COMPONENT_PATHS registry.

        🔄 RECURSION PATTERN: Uses COMPONENT_PATHS registry for direct loading
        without Qdrant search. This is the primary path for known components.

        Args:
            name: Component name from CORE_COMPONENTS registry

        Returns:
            The loaded component class or None
        """
        # Check cache first
        if name in self._components:
            return self._components[name]

        # Load directly from COMPONENT_PATHS registry (no Qdrant search)
        if name in self.COMPONENT_PATHS:
            cls = self._load_component_by_path(self.COMPONENT_PATHS[name])
            if cls:
                self._components[name] = cls
                logger.debug(f"Loaded {name} from COMPONENT_PATHS registry")
                return cls

        logger.warning(f"Component {name} not found in COMPONENT_PATHS registry")
        return None

    def _find_and_load_component(self, name: str, query: str) -> Optional[Any]:
        """
        Search Qdrant for a component and load it.

        This is used for DYNAMIC component discovery when the component
        is NOT in the COMPONENT_PATHS registry. For known components,
        use _load_core_component instead.

        Args:
            name: Component name (e.g., "Columns")
            query: Search query (e.g., "v2.widgets.columns.Columns class")

        Returns:
            The loaded component class or None
        """
        # Check cache first
        if name in self._components:
            return self._components[name]

        # For known components, skip Qdrant and load directly
        if name in self.COMPONENT_PATHS:
            return self._load_core_component(name)

        # Search Qdrant for unknown components
        if self._qdrant_available:
            results = self._search_component(query, limit=10)
            for r in results:
                # Handle template types
                if r["type"] == "template":
                    template = self._load_component_by_path(r["full_path"])
                    if template:
                        self._components[r["name"]] = template
                        logger.info(f"🎯 Loaded template from Qdrant: {r['name']}")
                        return template

                # Handle class types
                if (
                    r["name"] == name
                    and r["type"] == "class"
                    and "v2" in r["full_path"]
                ):
                    cls = self._load_component_by_path(r["full_path"])
                    if cls:
                        self._components[name] = cls
                        logger.debug(f"Loaded {name} from Qdrant: {r['full_path']}")
                        return cls

        # Fallback to COMPONENT_PATHS (alias for FALLBACK_PATHS)
        if name in self.FALLBACK_PATHS:
            cls = self._load_component_by_path(self.FALLBACK_PATHS[name])
            if cls:
                self._components[name] = cls
                logger.debug(f"Loaded {name} from fallback path")
                return cls

        return None

    def _find_matching_template(self, description: str) -> Optional[Any]:
        """
        Search for a matching template by description similarity.

        This is used to find promoted templates that match the user's description.
        Templates are prioritized over building from scratch when available.

        Args:
            description: Card description to match

        Returns:
            TemplateComponent instance or None
        """
        if not self._qdrant_available:
            return None

        try:
            from qdrant_client import models

            # Embed the description
            embedder = self._get_embedder()
            if not embedder:
                return None

            description_vectors_raw = list(embedder.query_embed(description))[0]
            description_vectors = [vec.tolist() for vec in description_vectors_raw]

            # Search for templates by description similarity
            client = self._get_qdrant_client()
            results = client.query_points(
                collection_name=_settings.card_collection,
                query=description_vectors,
                using="description_colbert",
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="template"),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                score_threshold=0.7,  # Higher threshold for template matching
            )

            if results.points:
                best = results.points[0]
                template_name = best.payload.get("name")
                full_path = best.payload.get("full_path")

                logger.info(
                    f"🎯 Found matching template: {template_name} "
                    f"(score={best.score:.3f})"
                )

                # Load via ModuleWrapper (which handles templates)
                return self._load_component_by_path(full_path)

            return None

        except Exception as e:
            logger.debug(f"Template search failed: {e}")
            return None

    def initialize(self):
        """
        Initialize Qdrant connection and load core components.

        🔄 RECURSION PATTERN: Uses CORE_COMPONENTS and COMPONENT_PATHS registries
        to load components directly without Qdrant search. Qdrant is only used
        for dynamic discovery of components NOT in the registry.
        """
        if self._initialized:
            return

        # Test Qdrant connection (for dynamic component discovery)
        self._get_qdrant_client()
        self._get_embedder()

        # =====================================================================
        # DIRECT COMPONENT LOADING - Following the Manifesto:
        # "One flow for all, no special trap"
        #
        # Load core components directly from COMPONENT_PATHS registry.
        # No Qdrant search needed for known components - paths are canonical.
        # =====================================================================
        for name in self.CORE_COMPONENTS:
            self._load_core_component(name)

        self._initialized = True
        logger.info(
            f"SmartCardBuilder initialized with {len(self._components)} components (Qdrant: {self._qdrant_available})"
        )

    def get_component(self, name: str) -> Optional[Any]:
        """Get a loaded component class by name."""
        if not self._initialized:
            self.initialize()

        # Return cached or search for it
        if name in self._components:
            return self._components[name]

        # Try to find via Qdrant
        query = (
            f"v2.widgets.{name.lower()}.{name} class"
            if name not in ["Section", "Card", "CardHeader"]
            else f"v2.{name.lower()}.{name} class"
        )
        return self._find_and_load_component(name, query)

    # =========================================================================
    # SMART INFERENCE - Maps content to component parameters
    # =========================================================================

    def _extract_image_urls_by_context(self, description: str) -> List[str]:
        """
        Extract URLs that should be treated as images based on CONTEXTUAL hints.

        Instead of hardcoding image hosts, this looks for image-intent keywords
        near URLs in the description, such as:
        - "showing image https://..."
        - "with picture https://..."
        - "image https://..."

        This is more robust than host-based detection because it relies on
        the user's expressed intent in the natural language description.

        Args:
            description: The card description text

        Returns:
            List of URLs that should be rendered as images
        """
        image_urls = []

        # First, get URLs with explicit image extensions (always images)
        extension_match = self.CONTENT_PATTERNS["image_url"].findall(description)
        image_urls.extend(extension_match)

        # Then, look for URLs in image-intent contexts
        for pattern in self.IMAGE_CONTEXT_PATTERNS:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for url in matches:
                if url not in image_urls:
                    image_urls.append(url)
                    logger.debug(f"📷 Context-detected image URL: {url[:50]}...")

        return image_urls

    def _is_image_url_by_context(self, url: str, description: str) -> bool:
        """
        Check if a URL should be treated as an image based on context.

        Args:
            url: The URL to check
            description: The full description text for context

        Returns:
            True if the URL appears in an image context
        """
        # Check for explicit image extension
        if self.CONTENT_PATTERNS["image_url"].search(url):
            return True

        # Check if URL appears in image-intent context
        for pattern in self.IMAGE_CONTEXT_PATTERNS:
            if re.search(pattern, description, re.IGNORECASE):
                # Check if this specific URL is in the match
                matches = re.findall(pattern, description, re.IGNORECASE)
                if url in matches:
                    return True

        return False

    def infer_content_type(self, text: str) -> Dict[str, Any]:
        """
        Smart inference: Analyze text to determine what type of content it is.

        Following the Manifesto: "One flow for all, no special trap"
        Uses CONTENT_TYPE_REGISTRY instead of if/else chains.

        Returns dict with:
            - type: 'price', 'id', 'date', 'email', 'url', 'image', 'text', etc.
            - suggested_component: Component name to use (loaded via wrapper)
            - suggested_params: Parameters for the component
        """
        # =====================================================================
        # REGISTRY-BASED DETECTION: Iterate through CONTENT_TYPE_REGISTRY
        # Order matters - first match wins (most specific patterns first)
        # =====================================================================
        for entry in self.CONTENT_TYPE_REGISTRY:
            pattern_key = entry["pattern"]
            pattern = self.CONTENT_PATTERNS.get(pattern_key)

            if pattern and pattern.search(text):
                match = pattern.search(text)
                return {
                    "type": entry["type"],
                    "suggested_component": entry["component"],
                    "suggested_params": entry["params"](text, match),
                }

        # Default fallback when no pattern matches
        return {
            "type": self.CONTENT_TYPE_DEFAULT["type"],
            "suggested_component": self.CONTENT_TYPE_DEFAULT["component"],
            "suggested_params": self.CONTENT_TYPE_DEFAULT["params"](text, None),
        }

    # =========================================================================
    # LAYOUT INFERENCE - Detects composition hints from natural language
    # =========================================================================

    def infer_layout(self, description: str) -> Dict[str, Any]:
        """
        Infer layout from natural language description.

        Following the Manifesto: "One flow for all, no special trap"
        Uses LAYOUT_TYPE_REGISTRY instead of if/else chains.

        Returns dict with:
            - layout_type: 'standard', 'columns', 'columns_image_right', 'columns_image_left', 'grid'
            - column_config: Column configuration if applicable
        """
        # =====================================================================
        # REGISTRY-BASED DETECTION: Iterate through LAYOUT_TYPE_REGISTRY
        # Order matters - first match wins (more specific patterns first)
        # =====================================================================
        for entry in self.LAYOUT_TYPE_REGISTRY:
            pattern_key = entry["pattern"]
            pattern = self.LAYOUT_PATTERNS.get(pattern_key)

            if pattern and pattern.search(description):
                return {
                    "layout_type": entry["layout_type"],
                    "column_config": entry["column_config"],
                }

        # Default fallback when no pattern matches
        return self.LAYOUT_TYPE_DEFAULT.copy()

    # =========================================================================
    # COMPONENT BUILDING - Create actual card_framework instances
    # =========================================================================

    def build_decorated_text(
        self,
        text: str,
        top_label: str = None,
        bottom_label: str = None,
        icon: str = None,
        button_url: str = None,
        button_text: str = None,
        wrap_text: bool = True,
    ) -> Optional[Any]:
        """Build a DecoratedText component."""
        DecoratedText = self.get_component("DecoratedText")
        if not DecoratedText:
            return None

        kwargs = {"text": text, "wrap_text": wrap_text}
        if top_label:
            kwargs["top_label"] = top_label
        if bottom_label:
            kwargs["bottom_label"] = bottom_label

        # Handle icon (use KNOWN_ICONS mapping)
        if icon:
            Icon = self.get_component("Icon")
            if Icon:
                # Map semantic icon name to KnownIcon enum value
                icon_value = self.KNOWN_ICONS.get(icon.lower(), icon.upper())
                kwargs["start_icon"] = Icon(known_icon=icon_value)

        # Handle button
        if button_url:
            Button = self.get_component("Button")
            OnClick = self.get_component("OnClick")
            if Button and OnClick:
                on_click = OnClick(open_link={"url": button_url})
                kwargs["button"] = Button(text=button_text or "Open", on_click=on_click)

        return DecoratedText(**kwargs)

    def build_image(
        self,
        image_url: str,
        alt_text: str = None,
        on_click_url: str = None,
    ) -> Optional[Any]:
        """
        Build an Image component with optional click action.

        Args:
            image_url: URL of the image to display
            alt_text: Alternative text for accessibility
            on_click_url: Optional URL to open when image is clicked

        Returns:
            Rendered Image component with optional onClick
        """
        Image = self.get_component("Image")
        if not Image:
            return None

        kwargs = {"image_url": image_url}
        if alt_text:
            kwargs["alt_text"] = alt_text

        # Add onClick if URL provided - makes image clickable
        if on_click_url:
            OnClick = self.get_component("OnClick")
            if OnClick:
                kwargs["on_click"] = OnClick(open_link={"url": on_click_url})

        return Image(**kwargs)

    # =========================================================================
    # INFERENCE-BASED BUILDERS - Used by COMPONENT_BUILDER_REGISTRY
    # Following the Manifesto: "One flow for all, no special trap"
    # =========================================================================

    def _build_image_from_inference(
        self, item: str, inference: Dict[str, Any]
    ) -> Optional[Any]:
        """Build Image from inferred content type."""
        params = inference["suggested_params"]
        return self.build_image(params.get("image_url", item))

    def _build_decorated_text_from_inference(
        self, item: str, inference: Dict[str, Any]
    ) -> Optional[Any]:
        """Build DecoratedText from inferred content type."""
        params = inference["suggested_params"]
        return self.build_decorated_text(
            text=params.get("text", item),
            top_label=params.get("top_label"),
            wrap_text=params.get("wrap_text", True),
        )

    def _build_text_paragraph_from_inference(
        self, item: str, inference: Dict[str, Any]
    ) -> Optional[Any]:
        """Build TextParagraph from inferred content type."""
        TextParagraph = self.get_component("TextParagraph")
        if TextParagraph:
            return TextParagraph(text=item)
        return None

    def build_widget_from_inference(
        self, item: str, inference: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Build a widget from inferred content type using COMPONENT_BUILDER_REGISTRY.

        Following the Manifesto: "One flow for all, no special trap"
        Uses registry lookup instead of if/elif chains.
        """
        component_name = inference["suggested_component"]
        builder_method_name = self.COMPONENT_BUILDER_REGISTRY.get(component_name)

        if builder_method_name:
            builder_method = getattr(self, builder_method_name, None)
            if builder_method:
                return builder_method(item, inference)

        # Fallback to TextParagraph if component not in registry
        return self._build_text_paragraph_from_inference(item, inference)

    def build_columns(
        self,
        left_widgets: List[Any],
        right_widgets: List[Any],
        left_size: str = "FILL_AVAILABLE_SPACE",
        right_size: str = "FILL_AVAILABLE_SPACE",
    ) -> Optional[Any]:
        """Build a Columns component with two columns."""
        Columns = self.get_component("Columns")
        Column = self.get_component("Column")

        if not Columns or not Column:
            return None

        try:
            left_col = Column(
                horizontal_size_style=getattr(Column.HorizontalSizeStyle, left_size),
                widgets=left_widgets,
            )
            right_col = Column(
                horizontal_size_style=getattr(Column.HorizontalSizeStyle, right_size),
                widgets=right_widgets,
            )

            return Columns(column_items=[left_col, right_col])
        except Exception as e:
            logger.warning(f"Error building columns: {e}")
            return None

    def build_section(
        self,
        header: str = None,
        widgets: List[Any] = None,
    ) -> Optional[Any]:
        """Build a Section component."""
        Section = self.get_component("Section")
        if not Section:
            return None

        kwargs = {}
        if header:
            kwargs["header"] = header
        if widgets:
            kwargs["widgets"] = widgets

        return Section(**kwargs)

    # =========================================================================
    # FORM COMPONENT BUILDING
    # =========================================================================

    def build_text_input(
        self,
        name: str,
        label: str = None,
        hint_text: str = None,
        value: str = None,
        type_: str = "SINGLE_LINE",
    ) -> Optional[Any]:
        """
        Build a TextInput component for form cards.

        Args:
            name: Input field name (required for form submission)
            label: Display label above the input
            hint_text: Placeholder/hint text inside the input
            value: Pre-filled value
            type_: Input type - "SINGLE_LINE" or "MULTIPLE_LINE"

        Returns:
            TextInput component or None
        """
        TextInput = self.get_component("TextInput")
        if not TextInput:
            logger.warning("TextInput component not available")
            return None

        kwargs = {"name": name}
        if label:
            kwargs["label"] = label
        if hint_text:
            kwargs["hint_text"] = hint_text
        if value:
            kwargs["value"] = value

        # Handle type enum
        try:
            if hasattr(TextInput, "Type"):
                kwargs["type"] = getattr(
                    TextInput.Type, type_, TextInput.Type.SINGLE_LINE
                )
        except Exception as e:
            logger.debug(f"Could not set TextInput type: {e}")

        return TextInput(**kwargs)

    def build_selection_input(
        self,
        name: str,
        label: str = None,
        type_: str = "DROPDOWN",
        items: List[Dict[str, str]] = None,
    ) -> Optional[Any]:
        """
        Build a SelectionInput component for form cards.

        Args:
            name: Input field name (required for form submission)
            label: Display label above the selection
            type_: Selection type - "DROPDOWN", "RADIO_BUTTON", "CHECK_BOX", "SWITCH"
            items: List of {text, value, selected} dicts for options

        Returns:
            SelectionInput component or None
        """
        SelectionInput = self.get_component("SelectionInput")
        if not SelectionInput:
            logger.warning("SelectionInput component not available")
            return None

        kwargs = {"name": name}
        if label:
            kwargs["label"] = label

        # Handle type enum
        try:
            if hasattr(SelectionInput, "Type"):
                kwargs["type"] = getattr(
                    SelectionInput.Type, type_, SelectionInput.Type.DROPDOWN
                )
        except Exception as e:
            logger.debug(f"Could not set SelectionInput type: {e}")

        # Handle items - need to convert to SelectionItem objects if available
        if items:
            try:
                if hasattr(SelectionInput, "SelectionItem"):
                    selection_items = []
                    for item in items:
                        si = SelectionInput.SelectionItem(
                            text=item.get("text", ""),
                            value=item.get("value", ""),
                            selected=item.get("selected", False),
                        )
                        selection_items.append(si)
                    kwargs["items"] = selection_items
                else:
                    # Fallback to raw dict format
                    kwargs["items"] = items
            except Exception as e:
                logger.debug(f"Could not create SelectionItems: {e}")
                kwargs["items"] = items

        return SelectionInput(**kwargs)

    def build_date_time_picker(
        self,
        name: str,
        label: str = None,
        type_: str = "DATE_AND_TIME",
        value_ms_epoch: int = None,
    ) -> Optional[Any]:
        """
        Build a DateTimePicker component for form cards.

        Args:
            name: Input field name (required for form submission)
            label: Display label above the picker
            type_: Picker type - "DATE_AND_TIME", "DATE_ONLY", "TIME_ONLY"
            value_ms_epoch: Pre-selected value in milliseconds since epoch

        Returns:
            DateTimePicker component or None
        """
        DateTimePicker = self.get_component("DateTimePicker")
        if not DateTimePicker:
            logger.warning("DateTimePicker component not available")
            return None

        kwargs = {"name": name}
        if label:
            kwargs["label"] = label
        if value_ms_epoch:
            kwargs["value_ms_epoch"] = value_ms_epoch

        # Handle type enum (DateTimePicker uses type_ as the Python kwarg)
        try:
            if hasattr(DateTimePicker, "Type"):
                kwargs["type_"] = getattr(
                    DateTimePicker.Type, type_, DateTimePicker.Type.DATE_AND_TIME
                )
        except Exception as e:
            logger.debug(f"Could not set DateTimePicker type: {e}")

        return DateTimePicker(**kwargs)

    # =========================================================================
    # GRID COMPONENT BUILDING
    # =========================================================================

    def build_grid(
        self,
        items: List[Dict[str, Any]],
        title: str = None,
        column_count: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a Grid widget for displaying items in a grid layout.

        Args:
            items: List of grid item dicts with {title, subtitle, image_url}
            title: Optional grid title
            column_count: Number of columns (default 2)

        Returns:
            Grid widget dict in Google Chat format
        """
        if not items:
            logger.warning("No items provided for grid")
            return None

        grid_items = []
        for i, item in enumerate(items):
            grid_item = {
                "id": item.get("id", f"item_{i}"),
                "title": item.get("title", ""),
            }
            if item.get("subtitle"):
                grid_item["subtitle"] = item["subtitle"]

            if item.get("image_url"):
                grid_item["image"] = {
                    "imageUri": item["image_url"],
                    "altText": item.get("alt_text", item.get("title", "")),
                }

            # NOTE: Google Chat GridItem does NOT support individual onClick.
            # The Grid widget has ONE onClick for the entire grid, not per-item.
            # For individually clickable images, use Image widgets or ButtonList instead.
            if item.get("url"):
                grid_item["layout"] = "TEXT_BELOW"
                # Store URL in subtitle for reference (onClick not supported on GridItem)
                logger.debug(f"Grid item URL {item['url']} - GridItem doesn't support onClick")

            grid_items.append(grid_item)

        grid_widget = {
            "grid": {
                "columnCount": column_count,
                "items": grid_items,
            }
        }

        if title:
            grid_widget["grid"]["title"] = title

        logger.info(
            f"✅ Built grid with {len(grid_items)} items, {column_count} columns"
        )
        return grid_widget

    def build_grid_from_images(
        self,
        image_urls: List[str],
        titles: List[str] = None,
        click_urls: List[str] = None,
        column_count: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a Grid widget from a list of image URLs.

        Args:
            image_urls: List of image URLs
            titles: Optional list of titles for each image
            click_urls: Optional list of click destination URLs for each image
            column_count: Number of columns (default 2)

        Returns:
            Grid widget dict in Google Chat format
        """
        items = []
        for i, url in enumerate(image_urls):
            item = {
                "image_url": url,
                "title": titles[i] if titles and i < len(titles) else f"Image {i + 1}",
            }
            # Add click URL if provided
            if click_urls and i < len(click_urls) and click_urls[i]:
                item["url"] = click_urls[i]
            items.append(item)

        return self.build_grid(items, column_count=column_count)

    # =========================================================================
    # NATURAL LANGUAGE DESCRIPTION PARSING
    # =========================================================================

    def _consume_directives(
        self, description: str
    ) -> Tuple[str, List[Dict[str, str]]]:
        """
        Consume directive patterns from description using registries.

        Uses LAYOUT_DIRECTIVE_PATTERNS, ACTION_DIRECTIVE_PATTERNS,
        and LIST_DIRECTIVE_PATTERNS instead of inline pattern definitions.

        Args:
            description: Raw description text

        Returns:
            Tuple of (cleaned_description, consumed_directives)
        """
        cleaned = description
        consumed = []

        # All directive pattern registries to process
        all_directive_patterns = [
            self.LAYOUT_DIRECTIVE_PATTERNS,
            self.ACTION_DIRECTIVE_PATTERNS,
            self.LIST_DIRECTIVE_PATTERNS,
        ]

        # Process each registry
        for pattern_list in all_directive_patterns:
            for pattern, directive_type in pattern_list:
                match = re.search(pattern, cleaned, re.IGNORECASE)
                if match:
                    consumed.append({"type": directive_type, "text": match.group()})
                    cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

        # Clean up multiple spaces
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

        return cleaned, consumed

    def parse_description(self, description: str) -> Dict[str, Any]:
        """
        Parse a natural language description into structured content.

        Extracts sections, items, buttons, icons, AND form fields from patterns like:
        - "First section titled 'X' showing Y. Second section titled 'Z' showing W."
        - "A status card with check icon showing 'Success' and warning showing 'Alert'"
        - "Include buttons for 'View' linking to https://..."
        - "A form card with text input field named 'name' with label 'Your Name'..."

        Args:
            description: Natural language card description

        Returns:
            Dict with: sections, items, buttons, fields, submit_action ready for build_card()
        """
        logger.info(f"📝 Parsing description: {description[:100]}...")

        result: Dict[str, Any] = {
            "sections": [],
            "items": [],
            "buttons": [],
            "fields": [],
            "submit_action": None,
            "grid_images": [],
            "layout_type": None,
            "image_url": None,  # Primary image URL extracted from description
            "clickable_images": [],  # Images with click destinations [{image_url, click_url}]
            "title": None,  # Card header title extracted from description
            "subtitle": None,  # Card header subtitle extracted from description
            "consumed_directives": [],  # Track what directives were stripped
        }

        # =====================================================================
        # DIRECTIVE CONSUMPTION PASS - Following the Manifesto:
        # "WRAP → DETECT → PRESERVE → UNWRAP"
        # Strip instruction text BEFORE it can leak into output
        # Uses registry patterns instead of inline definitions
        # =====================================================================
        cleaned_description, consumed = self._consume_directives(description)

        if consumed:
            result["consumed_directives"] = consumed
            logger.info(f"🧹 Consumed {len(consumed)} directive(s): {[d['type'] for d in consumed]}")
            description = cleaned_description

        # =====================================================================
        # EXTRACT CARD TITLE - Using CARD_TITLE_PATTERNS registry
        # Patterns checked in priority order: titled 'X' > title: 'X' > X card
        # =====================================================================
        for pattern, _desc in self.CARD_TITLE_PATTERNS:
            title_match = pattern.search(description)
            if title_match:
                title = title_match.group(1)
                if title:
                    result["title"] = title.strip()
                    logger.info(f"📛 Extracted card title: {result['title']}")
                    break  # First match wins (priority order)

        # =====================================================================
        # EXTRACT IMAGE URLs FIRST - for use in ANY card type (not just grids)
        # =====================================================================
        all_image_urls = self._extract_image_urls(description)
        if all_image_urls:
            result["image_url"] = all_image_urls[0]  # Primary image for header/hero
            logger.info(f"📸 Extracted primary image_url from description: {all_image_urls[0]}")
            if len(all_image_urls) > 1:
                result["additional_images"] = all_image_urls[1:]
                logger.info(f"📸 Found {len(all_image_urls) - 1} additional image(s)")

        # =====================================================================
        # EXTRACT CLICKABLE IMAGES - Images with click destinations
        # Uses CLICKABLE_IMAGE_PATTERN registry following GROUP INDEX CONVENTION
        # Consume pattern early to prevent instruction text in subsequent extractions
        # =====================================================================
        clickable_images = self._extract_clickable_images(description)
        if clickable_images:
            result["clickable_images"] = clickable_images
            logger.info(f"🖼️ Extracted {len(clickable_images)} clickable image(s)")
            # Remove clickable image patterns from description for subsequent extractions
            description = self.CLICKABLE_IMAGE_PATTERN.sub("", description).strip()

        # Check for grid intent - if detected, use all extracted image URLs for grid
        if self.LAYOUT_PATTERNS["grid"].search(description):
            # Prefer clickable images if available (they have both image_url and click_url)
            if clickable_images:
                result["grid_images"] = [ci["image_url"] for ci in clickable_images]
                result["grid_click_urls"] = [ci["click_url"] for ci in clickable_images]
                result["layout_type"] = "grid"
                logger.info(f"🔲 Grid layout detected with {len(clickable_images)} clickable image(s)")
                return result
            elif all_image_urls:
                result["grid_images"] = all_image_urls  # Use already-extracted URLs
                result["layout_type"] = "grid"
                logger.info(f"🔲 Grid layout detected with {len(all_image_urls)} image(s)")
                return result

        # Check for form intent - if detected, extract form fields
        form_fields, submit_action = self._extract_form_fields(description)
        if form_fields:
            result["fields"] = form_fields
            result["submit_action"] = submit_action
            logger.info(f"✅ Extracted {len(form_fields)} form field(s)")
            return result

        # Try to extract sections first (most structured format)
        sections = self._extract_sections(description)
        if sections:
            result["sections"] = sections
            logger.info(f"✅ Extracted {len(sections)} section(s)")
            return result

        # If no sections, extract items from the description
        items = self._extract_items(description)
        if items:
            result["items"] = items
            logger.info(f"✅ Extracted {len(items)} item(s)")

        # Extract buttons
        buttons = self._extract_buttons(description)
        if buttons:
            result["buttons"] = buttons
            logger.info(f"✅ Extracted {len(buttons)} button(s)")

        return result

    def _extract_form_fields(
        self, description: str
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Extract form fields from a natural language description.

        🔄 RECURSION PATTERN: Uses multiple registries:
        - FORM_KEYWORDS for intent detection
        - FORM_FIELD_PATTERNS for field extraction
        - GROUP_NAME_HANDLER_REGISTRY for group-specific dispatch
        - SUBMIT_BUTTON_PATTERNS for submit button extraction

        Returns:
            Tuple of (fields list, submit_action dict)
        """
        description_lower = description.lower()

        # Check for form intent using registry keywords
        has_form_intent = any(kw in description_lower for kw in self.FORM_KEYWORDS)

        if not has_form_intent:
            return [], None

        logger.info("📝 Form intent detected, extracting form fields...")
        fields = []

        # =====================================================================
        # FIELD EXTRACTION - "One flow for all, no special trap"
        # Uses FORM_FIELD_PATTERNS registry with GROUP_NAME_HANDLER_REGISTRY dispatch
        # =====================================================================
        for pattern, field_type, group_names in self.FORM_FIELD_PATTERNS:
            for match in pattern.finditer(description):
                groups = match.groups()
                field = {"type": field_type}

                # Map groups to field keys using registry dispatch
                for group_name, group_value in zip(group_names, groups):
                    if group_value:
                        # Check GROUP_NAME_HANDLER_REGISTRY for special handling
                        handler_name = self.GROUP_NAME_HANDLER_REGISTRY.get(group_name)
                        if handler_name:
                            # Dispatch to handler method
                            handler = getattr(self, handler_name)
                            handler(field, field_type, group_value)
                        else:
                            # Default: direct assignment
                            field[group_name] = group_value

                fields.append(field)
                logger.info(f"  📝 {field_type}: name={field.get('name')}, label={field.get('label')}")

        # =====================================================================
        # SUBMIT BUTTON EXTRACTION - "One flow for all, no special trap"
        # Uses SUBMIT_BUTTON_PATTERNS registry instead of inline patterns
        # =====================================================================
        submit_action = self._extract_submit_button(description)

        return fields, submit_action

    def _handle_field_group_options(
        self, field: Dict[str, Any], field_type: str, group_value: str
    ) -> None:
        """
        Handle 'options' group for form fields using QUOTED_TEXT_PATTERN registry.

        🔄 RECURSION PATTERN: Handler method dispatched via GROUP_NAME_HANDLER_REGISTRY

        Args:
            field: The field dict to populate
            field_type: The type of field (e.g., "SelectionInput")
            group_value: The raw options string from regex match
        """
        # Parse quoted strings using QUOTED_TEXT_PATTERN registry
        options = self.QUOTED_TEXT_PATTERN.findall(group_value)
        if options:
            field["items"] = [
                {
                    "text": opt,
                    "value": opt.lower().replace(" ", "_"),
                    "selected": i == 0,
                }
                for i, opt in enumerate(options)
            ]
        # Set default selection_type for SelectionInput
        if field_type == "SelectionInput":
            field["selection_type"] = "DROPDOWN"

    def _extract_submit_button(self, description: str) -> Optional[Dict[str, Any]]:
        """
        Extract submit button from description using SUBMIT_BUTTON_PATTERNS registry.

        🔄 RECURSION PATTERN: Uses registry-based pattern iteration
        instead of inline pattern definitions.

        Args:
            description: The natural language description

        Returns:
            Submit action dict or None
        """
        # Iterate through SUBMIT_BUTTON_PATTERNS registry
        for pattern, result_keys in self.SUBMIT_BUTTON_PATTERNS:
            match = pattern.search(description)
            if match:
                groups = match.groups()
                submit_action = {
                    key: groups[i] for i, key in enumerate(result_keys) if i < len(groups)
                }
                logger.info(f"  📝 Submit button: {submit_action}")
                return submit_action

        return None

    def _extract_html_aware_quoted(self, text: str, start_pos: int = 0) -> Optional[Tuple[str, int]]:
        """
        Extract quoted content while preserving HTML tags inside.

        The standard regex ['\"]([^'\"]+)['\"] breaks when HTML attributes
        contain quotes like <font color="#FF0000">. This helper handles that
        by tracking HTML tag depth.

        🔄 RECURSION PATTERN: Same detection used in CONTENT_PATTERNS["html_formatted"]
        is applied here to decide whether to use HTML-aware extraction.

        Args:
            text: Text to extract from
            start_pos: Position to start searching

        Returns:
            Tuple of (extracted_content, end_position) or None if no match
        """
        # Find the opening quote
        quote_match = re.search(r'["\']', text[start_pos:])
        if not quote_match:
            return None

        quote_char = quote_match.group(0)
        content_start = start_pos + quote_match.end()

        # Check if content contains HTML - if so, use balanced extraction
        # Otherwise use simple extraction (faster for non-HTML content)
        remaining = text[content_start:]

        # Quick check: does this look like it might have HTML?
        if '<' not in remaining[:200]:  # Check first 200 chars
            # No HTML, use simple extraction
            simple_end = remaining.find(quote_char)
            if simple_end != -1:
                return (remaining[:simple_end], content_start + simple_end + 1)
            return None

        # HTML might be present - use balanced extraction
        # Track angle brackets to handle <font color="..."> properly
        depth = 0
        i = 0
        while i < len(remaining):
            char = remaining[i]

            if char == '<':
                depth += 1
            elif char == '>':
                depth -= 1
            elif char == quote_char and depth == 0:
                # Found closing quote outside of HTML tags
                return (remaining[:i], content_start + i + 1)

            i += 1

        return None

    def _extract_sections(self, description: str) -> List[Dict[str, Any]]:
        """
        Extract sections from natural language using ordinal patterns.

        Handles patterns like:
        - "First section titled 'X' showing Y"
        - "Second section titled 'Z' with W"
        - "First section showing metrics: X, Y, Z"
        - "Second section with image showing URL"

        🔄 RECURSION PATTERN: Uses multiple registries:
        - ORDINAL_PATTERN for section numbering
        - SECTION_CONTENT_CONNECTOR_PATTERN for content extraction
        - CONTENT_TITLE_PATTERN for implicit title detection
        - _extract_html_aware_quoted() for HTML-safe title extraction
        """
        sections = []

        # =======================================================================
        # PATTERN 1: "First section titled 'Name' showing/with content"
        # Uses HTML-aware extraction for titles that may contain <font color=...>
        # Following the Manifesto: patterns from registry, not inline compilation
        # =======================================================================

        # Get compiled pattern from registry (ORDINAL_TITLED_SECTION_TEMPLATE)
        ordinal_titled_pattern = self._get_compiled_section_pattern("ordinal_titled")

        markers = list(ordinal_titled_pattern.finditer(description))
        if markers:
            for i, marker in enumerate(markers):
                ordinal_word = marker.group(1)
                title_start = marker.end()

                # Extract title using HTML-aware method
                title_result = self._extract_html_aware_quoted(description, title_start)
                if not title_result:
                    continue

                section_name, content_start = title_result

                # Find where content ends (at next section or end of string)
                if i + 1 < len(markers):
                    content_end = markers[i + 1].start()
                else:
                    content_end = len(description)

                # Extract content using SECTION_CONTENT_CONNECTOR_PATTERN registry
                raw_content = description[content_start:content_end]
                content_match = self.SECTION_CONTENT_CONNECTOR_PATTERN.match(raw_content)
                section_content = content_match.group(1).strip() if content_match else raw_content.strip()

                logger.info(f"  📋 Section '{section_name[:50]}...' (ordinal: {ordinal_word})")

                # Parse section content into widgets
                widgets = self._parse_section_content(section_content.strip())

                sections.append(
                    {
                        "header": section_name.strip(),
                        "widgets": widgets,
                    }
                )
            return sections

        # Pattern 2: "First section showing/with content" (no titled)
        # Used for simpler section descriptions without explicit titles
        # Following the Manifesto: patterns from registry, not inline compilation
        # Get compiled pattern from registry (ORDINAL_CONTENT_SECTION_TEMPLATE)
        ordinal_content_pattern = self._get_compiled_section_pattern("ordinal_content")

        matches = ordinal_content_pattern.findall(description)
        if matches:
            for idx, (ordinal_word, section_content) in enumerate(matches):
                # Generate a header from the content if none provided
                content_preview = section_content.strip()[:30].split(".")[0].strip()
                header = f"Section {idx + 1}"

                # Try to extract a title using CONTENT_TITLE_PATTERN registry
                title_match = self.CONTENT_TITLE_PATTERN.match(content_preview)
                if title_match:
                    header = title_match.group(1).title()

                logger.info(f"  📋 Section '{header}' (ordinal: {ordinal_word})")

                # Parse section content into widgets
                widgets = self._parse_section_content(section_content.strip())

                sections.append(
                    {
                        "header": header,
                        "widgets": widgets,
                    }
                )

        return sections

    def _extract_items(self, description: str) -> List[Dict[str, Any]]:
        """
        Extract content items from description when no explicit sections.

        Looks for:
        - Icon + text patterns: "check icon showing 'Success'"
        - Quoted text: "showing 'X'"
        - URLs
        - Status messages

        🔄 RECURSION PATTERN: Uses multiple registries:
        - BUTTON_INSTRUCTION_PATTERNS for stripping button instructions
        - ICON_TEXT_PATTERN for icon+text extraction
        - QUOTED_TEXT_PATTERN for quoted content
        - URL_EXTRACTION_PATTERN for URLs
        - LABEL_CLEANUP_PATTERNS for cleaning label text
        """
        items = []

        # =====================================================================
        # STRIP CLICKABLE IMAGE PATTERNS FIRST - before any other extraction
        # (Manifesto: clickable images are handled separately, must be consumed early)
        # =====================================================================
        cleaned_description = self.CLICKABLE_IMAGE_PATTERN.sub("", description)

        # =====================================================================
        # EXTRACT BUTTONS from cleaned description (after clickable images removed)
        # =====================================================================
        extracted_buttons = self._extract_buttons(cleaned_description)
        button_labels = {btn["text"].lower() for btn in extracted_buttons}
        button_urls = {btn["url"] for btn in extracted_buttons}
        logger.debug(f"Pre-extracted {len(extracted_buttons)} buttons to avoid duplicates")

        # =====================================================================
        # STRIP REMAINING INSTRUCTION PATTERNS
        # Uses SECTION_INSTRUCTION_PATTERNS, BUTTON_INSTRUCTION_PATTERNS registries
        # =====================================================================

        # Remove section instruction patterns
        for pattern in self.SECTION_INSTRUCTION_PATTERNS:
            cleaned_description = re.sub(pattern, "", cleaned_description, flags=re.IGNORECASE)

        # Remove button instruction patterns using BUTTON_INSTRUCTION_PATTERNS registry
        for pattern, _directive_type in self.BUTTON_INSTRUCTION_PATTERNS:
            cleaned_description = re.sub(pattern, "", cleaned_description, flags=re.IGNORECASE)

        # Remove "X linking to URL" patterns using BUTTON_LINK_CLEANUP_PATTERN registry
        cleaned_description = self.BUTTON_LINK_CLEANUP_PATTERN.sub("", cleaned_description)

        # Remove standalone "linking to" fragments using LINKING_TO_FRAGMENT_PATTERN registry
        cleaned_description = self.LINKING_TO_FRAGMENT_PATTERN.sub(" ", cleaned_description)

        # Extract icon + text using ICON_TEXT_PATTERN registry
        for icon_name, text in self.ICON_TEXT_PATTERN.findall(cleaned_description):
            icon_key = icon_name.lower()
            known_icon = self.KNOWN_ICONS.get(icon_key)
            items.append(
                {
                    "text": text,
                    "icon": known_icon,
                    "top_label": icon_name.capitalize() if not known_icon else None,
                }
            )

        # Pattern: labeled content ("Status: Active", "Memory usage at 78%")
        # Uses QUOTED_TEXT_PATTERN registry with negative lookbehind for HTML attribute quotes
        # Skip quote extraction entirely if HTML formatting is present (preserves HTML as-is)
        if self.CONTENT_PATTERNS["html_formatted"].search(cleaned_description):
            # HTML detected - preserve as-is, flows through infer_content_type → TextParagraph
            logger.debug(f"📝 HTML formatting detected, preserving content as-is")
            items.append(cleaned_description)
        else:
            # Use QUOTED_TEXT_PATTERN registry for quoted content extraction
            for quoted_text in self.QUOTED_TEXT_PATTERN.findall(cleaned_description):
                # Skip if already captured by icon pattern
                if any(item.get("text") == quoted_text for item in items):
                    continue
                # Skip if this is a button label (will be rendered as button)
                if quoted_text.lower() in button_labels:
                    logger.debug(f"⏭️ Skipping quoted text '{quoted_text}' - it's a button label")
                    continue
                items.append({"text": quoted_text})

        # Extract URLs using URL_EXTRACTION_PATTERN registry
        # Image URLs are added as items (will go through infer_content_type → Image component)
        # Non-image URLs are added as button items

        # Use CONTEXT-AWARE image detection instead of hardcoded hosts
        # This looks for image-intent keywords near URLs (e.g., "showing image URL")
        context_image_urls = set(self._extract_image_urls_by_context(description))

        for url in self.URL_EXTRACTION_PATTERN.findall(cleaned_description):
            # Skip URLs that are part of button patterns (will be rendered as buttons)
            if url in button_urls:
                logger.debug(f"⏭️ Skipping URL '{url[:50]}...' - it's a button URL")
                continue

            # Check if this is an image URL using CONTEXT-AWARE detection
            # This checks both extension-based and context-based (e.g., "showing image URL")
            is_image_url = url in context_image_urls
            if is_image_url:
                # Add image URL as an item - it will flow through infer_content_type()
                # which will detect it as an image and use the Image component
                logger.debug(f"📷 Context-detected image URL, adding as item: {url[:50]}...")
                items.append(url)  # String item → infer_content_type() → Image component
                continue

            # =====================================================================
            # LABELED LINK EXTRACTION - Following the Manifesto:
            # "The CONTENT_PATTERNS registry knows the way"
            # First try to extract label using labeled_link pattern, then fall back
            # =====================================================================
            label = self._extract_url_label(cleaned_description, url)

            # Use label for button text, fall back to "Open" only if no label
            button_text = label if label and len(label) >= 3 and len(label) <= 40 else "Open"

            items.append(
                {
                    "text": label if label and len(label) >= 3 else "Link",
                    "button_url": url,
                    "button_text": button_text,  # Use extracted label, not hardcoded "Open"
                }
            )
            if button_text != "Open":
                logger.debug(f"🔗 Preserved link label: '{button_text}' for {url[:40]}...")

        return items

    def _extract_url_label(self, text: str, url: str) -> str:
        """
        Extract label for a URL using CONTENT_PATTERNS and LABEL_CLEANUP_PATTERNS registries.

        🔄 RECURSION PATTERN: Uses LABEL_CLEANUP_PATTERNS registry for text cleanup
        """
        label = None

        # Search for labeled link pattern around this URL
        # Pattern captures 4 alternatives: linking, colon, arrow, parenthesized
        # Even indices (0, 2, 4, 6) are labels; odd indices (1, 3, 5, 7) are URLs
        labeled_match = self.CONTENT_PATTERNS["labeled_link"].search(text)
        if labeled_match:
            groups = labeled_match.groups()
            # Check which capture group matched
            for i, group in enumerate(groups):
                if group and url in text[labeled_match.start():labeled_match.end() + 100]:
                    # This group's URL is our URL - use the label (even indices)
                    if i % 2 == 0:  # Label groups are at even indices
                        label = group.strip()
                        logger.debug(f"🏷️ Extracted label '{label}' for URL via CONTENT_PATTERNS")
                        break

        # Fall back to heuristic extraction if pattern didn't match
        # Uses LABEL_PHRASE_SPLIT_PATTERN and LABEL_CLEANUP_PATTERNS registries
        if not label:
            url_pos = text.find(url)
            text_before = text[:url_pos].strip()
            # Get last phrase before URL using LABEL_PHRASE_SPLIT_PATTERN registry
            phrases = self.LABEL_PHRASE_SPLIT_PATTERN.split(text_before)
            label = phrases[-1].strip() if phrases else ""

            # Clean label using LABEL_CLEANUP_PATTERNS registry
            for pattern, _desc in self.LABEL_CLEANUP_PATTERNS:
                label = re.sub(pattern, "", label, flags=re.IGNORECASE)
            label = label.strip()

        return label

    def _extract_image_urls(self, description: str) -> List[str]:
        """
        Extract image URLs from description text using IMAGE_*_PATTERN registries.

        Handles patterns like:
        - "https://example.com/image.jpg"
        - "https://example.com/image.png"
        - URLs ending in common image extensions
        - Common image hosting services (picsum.photos, imgur, etc.)

        🔄 RECURSION PATTERN: Uses IMAGE_EXTENSION_PATTERN and IMAGE_HOST_PATTERN registries
        """
        image_urls = []

        # Use IMAGE_EXTENSION_PATTERN registry for URLs with explicit image extensions
        image_urls.extend(self.IMAGE_EXTENSION_PATTERN.findall(description))

        # Use IMAGE_HOST_PATTERN registry for known image hosting services
        image_urls.extend(self.IMAGE_HOST_PATTERN.findall(description))

        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in image_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        return unique_urls

    def _extract_clickable_images(self, description: str) -> List[Dict[str, str]]:
        """
        Extract clickable image definitions using CLICKABLE_IMAGE_PATTERN registry.

        Handles patterns like:
        - "image from IMG_URL linking to DEST_URL"
        - "clickable image IMG_URL (DEST_URL)"
        - "IMG_URL as clickable image linking to DEST_URL"

        Returns:
            List of dicts: [{"image_url": "...", "click_url": "..."}, ...]

        🔄 RECURSION PATTERN: Uses CLICKABLE_IMAGE_PATTERN registry
        """
        clickable_images = []

        # CLICKABLE_IMAGE_PATTERN has 3 alternatives, each with 2 groups (image_url, click_url)
        # Groups are at indices: (0,1), (2,3), (4,5)
        for match in self.CLICKABLE_IMAGE_PATTERN.finditer(description):
            groups = match.groups()
            # Find non-empty pairs (image_url at even index, click_url at odd index)
            image_url = next((g for i, g in enumerate(groups) if g and i % 2 == 0), None)
            click_url = next((g for i, g in enumerate(groups) if g and i % 2 == 1), None)
            if image_url and click_url:
                clickable_images.append({
                    "image_url": image_url.strip(),
                    "click_url": click_url.strip(),
                })
                logger.debug(f"🖼️ Found clickable image: {image_url[:40]}... → {click_url[:40]}...")

        return clickable_images

    def _extract_buttons(self, description: str) -> List[Dict[str, str]]:
        """
        Extract button definitions from description using BUTTON_EXTRACTION_PATTERN.

        Handles patterns like:
        - "button for 'View' linking to https://..."
        - "buttons: 'Join Meeting' -> https://..., 'View Agenda' -> https://..."
        - "'Label' (https://...)" - parenthesized URL syntax

        🔄 RECURSION PATTERN: Uses BUTTON_EXTRACTION_PATTERN registry
        """
        buttons = []

        # BUTTON_EXTRACTION_PATTERN has multiple alternatives with different capture groups:
        # Pattern 1 (linking/opens): groups 0, 1 -> (text, url)
        # Pattern 2 (parenthesized): groups 2, 3 -> (text, url)
        for match in self.BUTTON_EXTRACTION_PATTERN.finditer(description):
            groups = match.groups()
            # Find the non-empty text and url from the groups
            text = next((g for g in groups[::2] if g), None)  # Even indices: text groups
            url = next((g for g in groups[1::2] if g), None)  # Odd indices: url groups
            if text and url:
                buttons.append({"text": text.strip(), "url": url.strip()})

        return buttons

    def _extract_text_prefix_content(self, content: str) -> str:
        """
        Extract content from 'text "content"' format using TEXT_PREFIX_PATTERN.

        Args:
            content: Raw content string

        Returns:
            Extracted content with quotes unescaped, or original content
        """
        text_match = self.TEXT_PREFIX_PATTERN.match(content)
        if text_match:
            content = text_match.group(1)
            # Unescape any escaped quotes (\" -> ") for proper HTML rendering
            content = content.replace('\\"', '"').replace("\\'", "'")
        return content

    def _clean_instructional_phrases(self, content: str) -> Tuple[str, List[str]]:
        """
        Clean instructional phrases using INSTRUCTIONAL_CLEANUP_PATTERNS.

        Args:
            content: Content to clean

        Returns:
            Tuple of (cleaned_content, mentioned_icons)
        """
        mentioned_icons = []

        # Apply instructional cleanup patterns from registry
        for pattern, _description in self.INSTRUCTIONAL_CLEANUP_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                if match.lastindex and match.group(1):
                    mentioned_icons.append(match.group(1).lower())
            content = re.sub(pattern, "", content, flags=re.IGNORECASE)

        # Strip section instruction patterns
        for pattern in self.SECTION_INSTRUCTION_PATTERNS:
            content = re.sub(pattern, "", content, flags=re.IGNORECASE)

        # Clean up whitespace
        content = re.sub(r"\s+", " ", content).strip()

        return content, mentioned_icons

    def _clean_text_before_url(self, text_before: str) -> str:
        """
        Clean text before URL using TEXT_BEFORE_URL_CLEANUP patterns.

        Args:
            text_before: Text found before URL

        Returns:
            Cleaned text
        """
        for pattern, _description in self.TEXT_BEFORE_URL_CLEANUP:
            text_before = re.sub(pattern, "", text_before, flags=re.IGNORECASE).strip()
        return text_before

    def _detect_content_type(self, content: str) -> Tuple[bool, bool]:
        """
        Detect if content is warning or status type using keyword registries.

        Args:
            content: Content to analyze

        Returns:
            Tuple of (is_warning, is_status)
        """
        content_lower = content.lower()
        is_warning = any(w in content_lower for w in self.WARNING_KEYWORDS)
        is_status = any(w in content_lower for w in self.STATUS_KEYWORDS)
        return is_warning, is_status

    def _parse_section_content(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse section content into widget dictionaries.

        Uses registry-based patterns instead of hardcoded patterns.
        Following the Manifesto: "One flow for all, no special trap"

        Args:
            content: Raw text content for a section

        Returns:
            List of widget dicts ready for rendering
        """
        widgets = []
        content = content.strip()

        # Extract content from 'text "..."' format using registry pattern
        content = self._extract_text_prefix_content(content)

        # Preserve original content for label extraction BEFORE cleaning
        # (Manifesto: "linking to" pattern needs original text to extract labels)
        original_content = content

        # =====================================================================
        # CLICKABLE IMAGES: Extract and consume BEFORE other processing
        # Uses CLICKABLE_IMAGE_PATTERN following GROUP INDEX CONVENTION
        # Reuses _extract_clickable_images() which uses the registered pattern
        # =====================================================================
        clickable_images = self._extract_clickable_images(content)
        clickable_image_map = {}  # image_url -> click_url
        if clickable_images:
            for ci in clickable_images:
                clickable_image_map[ci["image_url"]] = ci["click_url"]
                # Build clickable image widget immediately
                logger.debug(f"📷 Building clickable image: {ci['image_url'][:40]}... -> {ci['click_url'][:40]}...")
                widgets.append({
                    "image": {
                        "imageUrl": ci["image_url"],
                        "altText": "Image",
                        "onClick": {"openLink": {"url": ci["click_url"]}},
                    }
                })
            # Remove clickable image patterns using CLICKABLE_IMAGE_PATTERN registry
            # (Manifesto: reuse registered patterns, don't duplicate)
            content = self.CLICKABLE_IMAGE_PATTERN.sub("", content).strip()
            original_content = content  # Update original_content too

        # Clean instructional phrases using registry patterns
        content, mentioned_icons = self._clean_instructional_phrases(content)

        # Extract URLs using registry pattern
        urls = self.URL_EXTRACTION_PATTERN.findall(content)

        # Get image URLs using context-aware detection
        context_image_urls = set(self._extract_image_urls_by_context(content))

        # Detect content type using registry keywords
        is_warning, is_status = self._detect_content_type(content)

        # Build set of URLs to skip (already handled as clickable images - both source and destination)
        clickable_urls_to_skip = set(clickable_image_map.keys()) | set(clickable_image_map.values())

        if urls:
            for url in urls:
                # Skip URLs already handled as clickable images (source or destination)
                if url in clickable_urls_to_skip:
                    content = content.replace(url, "").strip()
                    continue

                # Check if this is an IMAGE URL - render as Image widget, not button
                if url in context_image_urls:
                    logger.debug(f"📷 Section content: rendering image widget for {url[:50]}...")
                    widgets.append({
                        "image": {
                            "imageUrl": url,
                            "altText": "Image",
                        }
                    })
                    # Remove the URL from content for text display
                    content = content.replace(url, "").strip()
                    continue

                # Non-image URL - create decoratedText with button
                url_pos = content.find(url)
                text_before = content[:url_pos].strip() if url_pos > 0 else ""

                # Clean text before URL using registry patterns
                text_before = self._clean_text_before_url(text_before)

                display_text = text_before if len(text_before) > 3 else url

                # Extract button label from ORIGINAL content (before "linking to" was stripped)
                # Manifesto: reuse _extract_url_label, don't duplicate pattern logic
                button_label = self._extract_url_label(original_content, url)
                # Use extracted label if valid, otherwise fall back to "Open"
                button_text = button_label if button_label and 3 <= len(button_label) <= 40 else "Open"

                widget = {
                    "decoratedText": {
                        "text": display_text,
                        "wrapText": True,
                        "button": {
                            "text": button_text,
                            "onClick": {"openLink": {"url": url}},
                        },
                    }
                }

                # Add icon if mentioned
                if mentioned_icons:
                    icon_key = mentioned_icons[0]
                    if icon_key in self.KNOWN_ICONS:
                        widget["decoratedText"]["startIcon"] = {
                            "knownIcon": self.KNOWN_ICONS[icon_key]
                        }

                widgets.append(widget)
                # Update content to process remaining
                content = content[url_pos + len(url) :].strip()

        elif is_warning or is_status:
            # Status/warning content (use valid KnownIcon enum values)
            icon = "CONFIRMATION_NUMBER_ICON" if is_status else "STAR"
            widgets.append(
                {
                    "decoratedText": {
                        "text": content,
                        "wrapText": True,
                        "startIcon": {"knownIcon": icon},
                    }
                }
            )

        elif content:
            # Check for HTML formatting using existing CONTENT_PATTERNS - preserves HTML as-is
            if self.CONTENT_PATTERNS["html_formatted"].search(content):
                widgets.append({"textParagraph": {"text": content}})
            else:
                # Plain text - check for quoted segments using registry pattern
                quoted_matches = self.QUOTED_TEXT_PATTERN.findall(content)

                if quoted_matches:
                    for text in quoted_matches:
                        widget = {"decoratedText": {"text": text, "wrapText": True}}
                        if mentioned_icons and mentioned_icons[0] in self.KNOWN_ICONS:
                            widget["decoratedText"]["startIcon"] = {
                                "knownIcon": self.KNOWN_ICONS[mentioned_icons[0]]
                            }
                        widgets.append(widget)
                else:
                    # Just use the whole content as text
                    widgets.append({"textParagraph": {"text": content}})

        return widgets

    def build_card_from_description(
        self,
        description: str,
        title: str = None,
        subtitle: str = None,
        image_url: str = None,
        text: str = None,
        buttons: List[Dict[str, Any]] = None,
        fields: List[Dict[str, Any]] = None,
        submit_action: Dict[str, Any] = None,
        grid: Dict[str, Any] = None,
        images: List[str] = None,
        image_titles: List[str] = None,
        column_count: int = 2,
        sections: List[Dict[str, Any]] = None,
        strict_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Build a complete card by parsing natural language description.

        This is the main entry point that:
        1. Parses description into sections/items
        2. Uses Qdrant to find/load components
        3. Infers layout from description (columns, image positioning)
        4. Renders using component .render() methods

        Args:
            description: Natural language description of card content
            title: Optional card header title
            subtitle: Optional card header subtitle
            image_url: Optional image URL
            text: Optional explicit text content (used in layout inference)
            buttons: Optional list of button dicts [{text, url/onclick_action, type}]
            fields: Optional list of form field dicts for form cards
                    [{type: "TextInput"/"SelectionInput"/"DateTimePicker", name, label, ...}]
            submit_action: Optional submit action for form cards
                    {function: "functionName", parameters: {...}}
            grid: Optional direct grid widget structure {columnCount, items: [{image, title}, ...]}
            images: Optional list of image URLs to build into a grid
            image_titles: Optional list of titles for images (used with images param)
            column_count: Number of columns for grid (default 2, used with images param)
            sections: Optional explicit sections with pre-built widgets (pass-through mode)
            strict_mode: If True, bypass NL parsing and use only explicit params.
                         Use this for deterministic output when you have all params.

        Returns:
            Rendered card JSON in Google Chat API format
        """
        if not self._initialized:
            self.initialize()

        # =====================================================================
        # PARAM PROVENANCE TRACKING - Track where each param came from
        # Priority: explicit > nl_extracted > proven_pattern > default
        # =====================================================================
        provenance: Dict[str, str] = {}

        def track(param_name: str, value: Any, source: str) -> Any:
            """Track where a param value came from."""
            if value is not None:
                provenance[param_name] = source
            return value

        # Track explicit params (highest priority)
        if title:
            track("title", title, "explicit")
        if subtitle:
            track("subtitle", subtitle, "explicit")
        if image_url:
            track("image_url", image_url, "explicit")
        if text:
            track("text", text, "explicit")
        if buttons:
            track("buttons", buttons, "explicit")
        if fields:
            track("fields", fields, "explicit")

        # Initialize image click URL (for clickable images via CLICKABLE_IMAGE_PATTERN)
        image_click_url: Optional[str] = None

        # =====================================================================
        # STRICT MODE: Bypass NL parsing for deterministic output
        # =====================================================================
        if strict_mode:
            logger.info("🔒 Strict mode enabled - bypassing NL parsing, using only explicit params")
            # Build directly from explicit params only
            card = self._build_card_from_explicit_params(
                title=title,
                subtitle=subtitle,
                image_url=image_url,
                text=text,
                buttons=buttons,
                fields=fields,
                submit_action=submit_action,
            )
            card["_provenance"] = provenance
            card["_strict_mode"] = True
            return self._validate_and_finalize_card(card, provenance)

        # =====================================================================
        # GRID CARDS: Handle grid/images params using build_grid_from_images
        # Uses Grid component loaded via Qdrant search
        # =====================================================================
        if grid or images:
            logger.info(f"🔲 Grid card mode detected")
            card = self._build_grid_card(
                title=title,
                subtitle=subtitle,
                text=text,
                grid=grid,
                images=images,
                image_titles=image_titles,
                column_count=column_count,
                buttons=buttons,
            )
            card["_provenance"] = provenance
            return card

        # =====================================================================
        # EXPLICIT SECTIONS: Pass-through mode for pre-built widget structures
        # When explicit sections are provided, use them directly but still
        # process through SmartCardBuilder for feedback buttons, validation, etc.
        # =====================================================================
        if sections:
            logger.info(f"📋 Explicit sections provided: {len(sections)} section(s)")
            card = self._build_card_from_explicit_sections(
                title=title,
                subtitle=subtitle,
                sections=sections,
            )
            card["_provenance"] = provenance
            card["_explicit_sections"] = True
            return card

        # =====================================================================
        # FEEDBACK LOOP: Check for proven patterns from similar successful cards
        # Priority: explicit > nl_extracted > proven_pattern
        # =====================================================================
        proven_params = self._get_proven_params(description)
        if proven_params:
            logger.info(
                f"🎯 Found proven pattern for similar description, merging params"
            )
            # Merge proven params ONLY for params not already set (explicit takes priority)
            # NOTE: We merge text/styling params but NOT buttons - buttons are too
            # context-specific and often pollute cards with irrelevant actions
            if not title and proven_params.get("title"):
                title = track("title", proven_params.get("title"), "proven_pattern")
            if not subtitle and proven_params.get("subtitle"):
                subtitle = track("subtitle", proven_params.get("subtitle"), "proven_pattern")
            if not image_url and proven_params.get("image_url"):
                image_url = track("image_url", proven_params.get("image_url"), "proven_pattern")
            if not text and proven_params.get("text"):
                text = track("text", proven_params.get("text"), "proven_pattern")
            # DO NOT merge buttons from proven_params - they're too context-specific
            # Merge fields for form cards (these are structural, so OK to merge)
            if not fields and proven_params.get("fields"):
                fields = track("fields", proven_params.get("fields"), "proven_pattern")
            if not submit_action and proven_params.get("submit_action"):
                submit_action = track("submit_action", proven_params.get("submit_action"), "proven_pattern")

        # =====================================================================
        # TEMPLATE SYSTEM: Check for highly-matched promoted templates
        # =====================================================================
        # Templates are patterns that have received many positive feedbacks
        # and have been "promoted" to first-class components.
        # Using a template is faster and more reliable than building from scratch.
        matching_template = self._find_matching_template(description)
        if matching_template:
            try:
                logger.info(f"🎯 Using promoted template for card generation")
                # Render the template with any override params
                rendered = matching_template.render()

                # Apply explicit overrides if provided
                if title and "header" not in rendered:
                    rendered["header"] = {"title": title, "subtitle": subtitle or ""}
                elif title and "header" in rendered:
                    rendered["header"]["title"] = title
                    if subtitle:
                        rendered["header"]["subtitle"] = subtitle

                # Add feedback section
                if ENABLE_FEEDBACK_BUTTONS:
                    card_id = str(uuid.uuid4())
                    feedback_section = self._create_feedback_section(card_id)
                    if "sections" in rendered:
                        rendered["sections"].append(feedback_section)
                    else:
                        rendered["sections"] = [feedback_section]
                    rendered["_card_id"] = card_id

                return rendered
            except Exception as e:
                logger.warning(
                    f"Template rendering failed, falling back to normal build: {e}"
                )

        # If fields are provided, build a form card
        if fields:
            return self._build_form_card(
                title=title,
                subtitle=subtitle,
                text=text,
                fields=fields,
                submit_action=submit_action,
            )

        # Parse description into structured content
        parsed = self.parse_description(description)

        # =====================================================================
        # MERGE NL-EXTRACTED PARAMS: Priority: explicit > nl_extracted > proven
        # =====================================================================
        if not title and parsed.get("title"):
            title = track("title", parsed["title"], "nl_extracted")
            logger.info(f"📛 Using title extracted from description: {title}")

        if not subtitle and parsed.get("subtitle"):
            subtitle = track("subtitle", parsed["subtitle"], "nl_extracted")
            logger.info(f"📝 Using subtitle extracted from description: {subtitle}")

        if not image_url and parsed.get("image_url"):
            image_url = track("image_url", parsed["image_url"], "nl_extracted")
            logger.info(f"📸 Using image_url extracted from description: {image_url}")

        # Check for clickable image destination (image with onClick)
        # Uses CLICKABLE_IMAGE_PATTERN via parse_description
        # PRIORITY: Clickable images take precedence over regular image extraction
        image_click_url = None
        if parsed.get("clickable_images"):
            clickable_images = parsed["clickable_images"]

            # If multiple clickable images (and not already handled as grid), build multi-image card
            if len(clickable_images) > 1 and not parsed.get("grid_images"):
                logger.info(f"🖼️ Building card with {len(clickable_images)} clickable images")
                return self._build_clickable_images_card(
                    title=title,
                    subtitle=subtitle,
                    clickable_images=clickable_images,
                    buttons=buttons,
                )

            # Single clickable image - use it for the card's main image
            first_ci = clickable_images[0]
            # Override image_url with the clickable image's source URL
            image_url = track("image_url", first_ci["image_url"], "nl_extracted")
            image_click_url = first_ci.get("click_url")
            logger.info(f"🖼️ Using clickable image: {image_url} -> {image_click_url}")

        # If form fields were extracted from description, build form card
        # This uses the same Qdrant → ModuleWrapper flow via build_text_input(), etc.
        if parsed.get("fields"):
            logger.info(f"📝 Form fields detected in description, building form card")
            return self._build_form_card(
                title=title,
                subtitle=subtitle,
                text=text,
                fields=parsed["fields"],
                submit_action=parsed.get("submit_action"),
            )

        # If grid images were extracted from description, build grid card
        # This uses the Grid component loaded via Qdrant search
        if parsed.get("grid_images"):
            logger.info(
                f"🔲 Grid layout detected via NLP, building grid with {len(parsed['grid_images'])} images"
            )
            return self._build_grid_card(
                title=title,
                subtitle=subtitle,
                text=text,
                images=parsed["grid_images"],
                click_urls=parsed.get("grid_click_urls"),  # Pass click URLs for clickable grid items
                column_count=2,  # Default, could be extracted from description
                buttons=buttons,
            )

        # If we have sections from NLP parsing, build multi-section card
        if parsed.get("sections"):
            return self._build_multi_section_card(
                sections=parsed["sections"],
                title=title,
                subtitle=subtitle,
                image_url=image_url,
                image_click_url=image_click_url,
                text=text,
                buttons=buttons,
            )

        # Otherwise, build single-section card with items
        # Include explicit text as an item so it participates in layout inference
        items = parsed.get("items", [])
        if text:
            # Convert markdown and add text as first item so it becomes part of text_widgets in build_card()
            converted_text = self.convert_markdown_to_chat(text)
            items.insert(0, converted_text)

        # Merge parsed buttons with explicit buttons
        all_buttons = parsed.get("buttons", [])
        if buttons:
            # Convert button format from card_params to internal format
            for btn in buttons:
                if isinstance(btn, dict):
                    btn_entry = {
                        "text": btn.get("text", "Button"),
                        "url": btn.get("onclick_action")
                        or btn.get("url")
                        or btn.get("action", "#"),
                    }
                    all_buttons.append(btn_entry)

        content = {
            "title": title,
            "subtitle": subtitle,
            "image_url": image_url,
            "image_click_url": image_click_url,  # For clickable images
            "items": items,
            "buttons": all_buttons,
        }

        card = self.build_card(description, content)

        # Add provenance tracking to final card
        if provenance:
            card["_provenance"] = provenance
            logger.debug(f"📊 Param provenance: {provenance}")

        return card

    def _build_multi_section_card(
        self,
        sections: List[Dict[str, Any]],
        title: str = None,
        subtitle: str = None,
        image_url: str = None,
        image_click_url: str = None,
        text: str = None,
        buttons: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a card with multiple sections.

        Args:
            sections: List of section dicts with 'header' and 'widgets'
            title: Card header title
            subtitle: Card header subtitle
            image_url: Optional image URL (added as widget, NOT in header)
            image_click_url: Optional click destination URL for image (makes image clickable)
            text: Optional explicit text content (added to first section)
            buttons: Optional list of button dicts (added to last section)

        Returns:
            Rendered card JSON in Google Chat API format (camelCase)

        Note:
            Google Chat does NOT render images in header.imageUrl.
            Images must be placed as widgets in sections.
        """
        rendered_sections = []

        for section_data in sections:
            header = section_data.get("header", "")
            widgets_data = section_data.get("widgets", [])

            # Use the widget dicts directly - they're already in camelCase format
            # Don't convert to component instances as Section.render() outputs snake_case
            if widgets_data:
                section_dict = {"widgets": widgets_data}
                if header:
                    section_dict["header"] = header
                rendered_sections.append(section_dict)

        # Build card structure
        card = {}

        if title:
            card["header"] = {
                "title": title,
                "subtitle": subtitle or "",
            }
            # NOTE: Do NOT put image_url in header - Google Chat doesn't render it there

        # Ensure we have at least one section
        if not rendered_sections:
            rendered_sections = [{"widgets": []}]

        # Add explicit text to first section if provided
        if text:
            # Convert markdown to Google Chat format
            converted_text = self.convert_markdown_to_chat(text)
            text_widget = {"textParagraph": {"text": converted_text}}
            if rendered_sections[0].get("widgets"):
                rendered_sections[0]["widgets"].insert(0, text_widget)
            else:
                rendered_sections[0]["widgets"] = [text_widget]
            logger.info(
                f"✅ Added text widget to first section: {converted_text[:50]}..."
            )

        # Add image as widget in first section (Google Chat requires images as widgets, not in header)
        # Supports clickable images with onClick via CLICKABLE_IMAGE_PATTERN
        if image_url:
            image_widget = {"image": {"imageUrl": image_url}}
            # Add onClick if image has a click destination
            if image_click_url:
                image_widget["image"]["onClick"] = {"openLink": {"url": image_click_url}}
                logger.info(f"🔗 Image is clickable, links to: {image_click_url}")
            # Insert after text if text was added, otherwise at beginning
            insert_pos = 1 if text else 0
            if rendered_sections[0].get("widgets"):
                rendered_sections[0]["widgets"].insert(insert_pos, image_widget)
            else:
                rendered_sections[0]["widgets"] = [image_widget]
            logger.info(f"✅ Added image widget to first section: {image_url}")

        # Add buttons to last section if provided
        if buttons and isinstance(buttons, list):
            button_widgets = []
            for btn in buttons:
                if isinstance(btn, dict):
                    btn_widget = {"text": btn.get("text", "Button")}
                    onclick = (
                        btn.get("onclick_action") or btn.get("url") or btn.get("action")
                    )
                    if onclick:
                        btn_widget["onClick"] = {"openLink": {"url": onclick}}
                    btn_type = btn.get("type")
                    if btn_type in ["FILLED", "FILLED_TONAL", "OUTLINED", "BORDERLESS"]:
                        btn_widget["type"] = btn_type
                    button_widgets.append(btn_widget)

            if button_widgets:
                last_section = rendered_sections[-1]
                if "widgets" not in last_section:
                    last_section["widgets"] = []
                last_section["widgets"].append(
                    {"buttonList": {"buttons": button_widgets}}
                )
                logger.info(f"✅ Added {len(button_widgets)} button(s) to last section")

        # Add feedback section if enabled
        card_id = None
        if ENABLE_FEEDBACK_BUTTONS:
            card_id = str(uuid.uuid4())
            feedback_section = self._create_feedback_section(card_id)
            rendered_sections.append(feedback_section)

            # Store pattern for feedback collection
            try:
                self._store_card_pattern(
                    card_id=card_id,
                    description=f"multi-section card: {title or 'untitled'}",
                    component_paths=["Section", "DecoratedText"],  # Common components
                    instance_params={
                        "title": title,
                        "subtitle": subtitle,
                        "sections": len(sections),
                    },
                )
            except Exception as e:
                logger.debug(f"Could not store card pattern: {e}")

        card["sections"] = rendered_sections
        card["_card_id"] = card_id  # Internal: for tracking

        return card

    def _build_clickable_images_card(
        self,
        title: str = None,
        subtitle: str = None,
        clickable_images: List[Dict[str, str]] = None,
        buttons: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a card with multiple clickable Image widgets.

        NOTE: Google Chat Grid items do NOT support per-item onClick (verified via
        Qdrant relationships data). For individually clickable images, we use
        separate Image widgets instead of a Grid.

        Args:
            title: Optional card header title
            subtitle: Optional card header subtitle
            clickable_images: List of {"image_url": "...", "click_url": "..."} dicts
            buttons: Optional list of button dicts

        Returns:
            Rendered card JSON in Google Chat API format
        """
        card = {}
        card_id = str(uuid.uuid4())

        # Build header if title/subtitle provided
        if title or subtitle:
            header = {}
            if title:
                header["title"] = title
            if subtitle:
                header["subtitle"] = subtitle
            card["header"] = header

        # Build widgets list with clickable images
        widgets = []
        for i, ci in enumerate(clickable_images or []):
            image_widget = {
                "image": {
                    "imageUrl": ci["image_url"],
                    "altText": f"Image {i + 1}",
                    "onClick": {"openLink": {"url": ci["click_url"]}},
                }
            }
            widgets.append(image_widget)
            logger.debug(f"🖼️ Added clickable image {i + 1}: {ci['image_url'][:40]}...")

        # Add buttons if provided
        if buttons:
            button_list = []
            for btn in buttons:
                button = {
                    "text": btn.get("text", "Button"),
                    "onClick": {
                        "openLink": {"url": btn.get("onclick_action") or btn.get("url", "#")}
                    }
                }
                button_list.append(button)
            widgets.append({"buttonList": {"buttons": button_list}})

        # Build single section with all image widgets
        card["sections"] = [{"widgets": widgets}]
        card["_card_id"] = card_id

        logger.info(f"✅ Built clickable images card with {len(clickable_images or [])} images")
        return card

    def _build_card_from_explicit_sections(
        self,
        title: str = None,
        subtitle: str = None,
        sections: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a card from explicit pre-built sections.

        This is the pass-through mode for complex widget structures that are
        already in Google Chat JSON format. The sections are used directly,
        with feedback buttons added via the standard SmartCardBuilder flow.

        Args:
            title: Optional card header title
            subtitle: Optional card header subtitle
            sections: Pre-built sections with widgets in Google Chat JSON format

        Returns:
            Rendered card JSON in Google Chat API format
        """
        card = {}
        card_id = str(uuid.uuid4())

        # Build header if title/subtitle provided
        if title or subtitle:
            header = {}
            if title:
                header["title"] = title
            if subtitle:
                header["subtitle"] = subtitle
            card["header"] = header

        # Use explicit sections directly
        card["sections"] = sections or []
        card["_card_id"] = card_id

        # Add feedback section (uses standard SmartCardBuilder flow)
        feedback_section = self._build_feedback_section(card_id)
        if feedback_section:
            card["sections"].append(feedback_section)

        logger.info(f"✅ Built card from {len(sections or [])} explicit section(s)")
        return card

    def _build_grid_card(
        self,
        title: str = None,
        subtitle: str = None,
        text: str = None,
        grid: Dict[str, Any] = None,
        images: List[str] = None,
        image_titles: List[str] = None,
        click_urls: List[str] = None,
        column_count: int = 2,
        buttons: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a grid card using the Grid component loaded via Qdrant.

        Uses self.build_grid_from_images() which uses the Grid component
        that was loaded during initialization via Qdrant search.

        Args:
            title: Optional card header title
            subtitle: Optional card header subtitle
            text: Optional text to display above the grid
            grid: Direct grid widget structure {columnCount, items: [{image, title}, ...]}
            images: List of image URLs to build into a grid
            image_titles: Optional list of titles for each image
            click_urls: Optional list of click destination URLs for each image
            column_count: Number of columns (default 2)
            buttons: Optional list of button dicts

        Returns:
            Rendered card JSON in Google Chat API format
        """
        card = {}
        card_id = str(uuid.uuid4())

        # Build header if title/subtitle provided
        if title or subtitle:
            header = {}
            if title:
                header["title"] = title
            if subtitle:
                header["subtitle"] = subtitle
            card["header"] = header

        # Build widgets list
        widgets = []

        # Add text paragraph if text provided
        if text:
            widgets.append({"textParagraph": {"text": text}})

        # Build grid widget
        if grid:
            # Direct grid structure provided - use as-is
            grid_widget = {"grid": grid}
            logger.info(f"✅ Using direct grid structure with {len(grid.get('items', []))} items")
        elif images:
            # Build grid from image URLs using build_grid_from_images
            # This uses the Grid component loaded via Qdrant
            grid_widget = self.build_grid_from_images(
                image_urls=images,
                titles=image_titles,
                click_urls=click_urls,
                column_count=column_count,
            )
            logger.info(f"✅ Built grid from {len(images)} images, {column_count} columns, click_urls={bool(click_urls)}")
        else:
            grid_widget = None

        if grid_widget:
            widgets.append(grid_widget)

        # Add buttons if provided
        if buttons:
            button_list = []
            for btn in buttons:
                button = {
                    "text": btn.get("text", "Button"),
                    "onClick": {
                        "openLink": {"url": btn.get("onclick_action") or btn.get("url", "#")}
                    }
                }
                button_list.append(button)  # No wrapper - API expects button directly
            if button_list:
                widgets.append({"buttonList": {"buttons": button_list}})

        # Add feedback section
        if ENABLE_FEEDBACK_BUTTONS:
            feedback_section = self._create_feedback_section(card_id)
            card["sections"] = [{"widgets": widgets}, feedback_section]

            # Store pattern for feedback collection
            try:
                self._store_card_pattern(
                    card_id=card_id,
                    description=f"grid card: {title or 'untitled'}",
                    component_paths=[
                        "card_framework.v2.widgets.grid.Grid",
                        "card_framework.v2.widgets.grid.GridItem",
                    ],
                    instance_params={
                        "title": title,
                        "subtitle": subtitle,
                        "layout_type": "grid",
                        "column_count": column_count,
                        "image_count": len(images) if images else 0,
                    },
                )
            except Exception as e:
                logger.debug(f"Could not store grid card pattern: {e}")
        else:
            card["sections"] = [{"widgets": widgets}]

        card["_card_id"] = card_id

        logger.info(f"✅ Built grid card with {len(widgets)} widgets")
        return card

    # =========================================================================
    # FIELD TYPE BUILDER METHODS - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # These methods are called via FIELD_TYPE_BUILDER_REGISTRY.
    # Each method handles one form field type's construction with fallback logic.
    # =========================================================================

    def _build_field_text_input(
        self, field: Dict[str, Any], widgets: List[Dict[str, Any]]
    ) -> None:
        """Build TextInput field widget with fallback."""
        field_name = field.get("name", "unnamed_field")
        field_label = field.get("label", "")
        input_type = "MULTIPLE_LINE" if field.get("multiline") else "SINGLE_LINE"

        component = self.build_text_input(
            name=field_name,
            label=field_label,
            hint_text=field.get("hint_text") or field.get("hint"),
            value=field.get("value"),
            type_=input_type,
        )

        if component:
            try:
                rendered = component.render()
                widgets.append(rendered)
                logger.info(f"✅ Added TextInput field via ModuleWrapper: {field_name}")
                return
            except Exception as e:
                logger.warning(f"⚠️ Failed to render TextInput: {e}, using fallback")

        # Fallback to direct JSON
        widgets.append(
            {
                "textInput": {
                    "name": field_name,
                    "label": field_label,
                    "type": input_type,
                }
            }
        )

    def _build_field_selection_input(
        self, field: Dict[str, Any], widgets: List[Dict[str, Any]]
    ) -> None:
        """Build SelectionInput field widget with fallback."""
        field_name = field.get("name", "unnamed_field")
        field_label = field.get("label", "")
        selection_type = field.get("selection_type", "DROPDOWN")
        items = field.get("items", [])

        component = self.build_selection_input(
            name=field_name,
            label=field_label,
            type_=selection_type,
            items=items,
        )

        if component:
            try:
                rendered = component.render()
                widgets.append(rendered)
                logger.info(
                    f"✅ Added SelectionInput field via ModuleWrapper: {field_name}"
                )
                return
            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to render SelectionInput: {e}, using fallback"
                )

        # Fallback to direct JSON
        widgets.append(
            {
                "selectionInput": {
                    "name": field_name,
                    "label": field_label,
                    "type": selection_type,
                    "items": (
                        [
                            {
                                "text": item.get("text", ""),
                                "value": item.get("value", ""),
                                "selected": item.get("selected", False),
                            }
                            for item in items
                        ]
                        if items
                        else []
                    ),
                }
            }
        )

    def _build_field_date_time_picker(
        self, field: Dict[str, Any], widgets: List[Dict[str, Any]]
    ) -> None:
        """Build DateTimePicker field widget with fallback."""
        field_name = field.get("name", "unnamed_field")
        field_label = field.get("label", "")
        picker_type = field.get("picker_type", "DATE_AND_TIME")

        component = self.build_date_time_picker(
            name=field_name,
            label=field_label,
            type_=picker_type,
            value_ms_epoch=field.get("value_ms"),
        )

        if component:
            try:
                rendered = component.render()
                widgets.append(rendered)
                logger.info(
                    f"✅ Added DateTimePicker field via ModuleWrapper: {field_name}"
                )
                return
            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to render DateTimePicker: {e}, using fallback"
                )

        # Fallback to direct JSON
        widgets.append(
            {
                "dateTimePicker": {
                    "name": field_name,
                    "label": field_label,
                    "type": picker_type,
                }
            }
        )

    def _build_form_field(
        self, field: Dict[str, Any], widgets: List[Dict[str, Any]]
    ) -> None:
        """
        Build a form field using FIELD_TYPE_BUILDER_REGISTRY.

        Uses registry-based dispatch instead of if/elif chains.
        """
        field_type = field.get("type", "TextInput")
        method_name = self.FIELD_TYPE_BUILDER_REGISTRY.get(field_type)

        if method_name:
            method = getattr(self, method_name, None)
            if method:
                method(field, widgets)
                return

        # Unknown field type
        logger.warning(f"⚠️ Unknown field type: {field_type}")

    def _build_form_card(
        self,
        title: str = None,
        subtitle: str = None,
        text: str = None,
        fields: List[Dict[str, Any]] = None,
        submit_action: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Build a form card with input fields using ModuleWrapper components.

        Uses self.build_text_input(), self.build_selection_input(), etc. which
        load components via Qdrant/ModuleWrapper and render them properly.

        Args:
            title: Card header title
            subtitle: Card header subtitle
            text: Optional descriptive text above the form
            fields: List of field definitions:
                - TextInput: {type: "TextInput", name: "field_name", label: "Label", hint: "Hint text"}
                - SelectionInput: {type: "SelectionInput", name: "field_name", label: "Label",
                                   selection_type: "DROPDOWN"/"RADIO_BUTTON"/"CHECK_BOX"/"SWITCH",
                                   items: [{text: "Option 1", value: "opt1", selected: false}, ...]}
                - DateTimePicker: {type: "DateTimePicker", name: "field_name", label: "Label",
                                   picker_type: "DATE_AND_TIME"/"DATE_ONLY"/"TIME_ONLY"}
            submit_action: Submit button configuration:
                - {text: "Submit", function: "handleSubmit", parameters: {...}}
                - or {text: "Submit", url: "https://..."} for URL action

        Returns:
            Form card JSON in Google Chat API format
        """
        widgets = []

        # Add descriptive text if provided
        if text:
            converted_text = self.convert_markdown_to_chat(text)
            widgets.append({"textParagraph": {"text": converted_text}})

        # Build form field widgets using FIELD_TYPE_BUILDER_REGISTRY
        # Following the Manifesto: "One flow for all, no special trap"
        if fields:
            for field in fields:
                self._build_form_field(field, widgets)

        # Add submit button using ButtonList component
        if submit_action:
            submit_text = submit_action.get("text", "Submit")

            # Try to use Button/ButtonList components via ModuleWrapper
            Button = self.get_component("Button")
            ButtonList = self.get_component("ButtonList")
            OnClick = self.get_component("OnClick")

            if Button and ButtonList and OnClick:
                try:
                    # Build onClick based on action type
                    if submit_action.get("function"):
                        # Function action for Apps Script/Cloud Function callbacks
                        # OnClick doesn't directly support action, use dict
                        on_click_dict = {
                            "action": {
                                "function": submit_action["function"],
                            }
                        }
                        if submit_action.get("parameters"):
                            params = submit_action["parameters"]
                            if isinstance(params, dict):
                                on_click_dict["action"]["parameters"] = [
                                    {"key": k, "value": str(v)}
                                    for k, v in params.items()
                                ]
                        # Fallback to dict for action-based onClick
                        widgets.append(
                            {
                                "buttonList": {
                                    "buttons": [
                                        {
                                            "text": submit_text,
                                            "type": "FILLED",
                                            "onClick": on_click_dict,
                                        }
                                    ]
                                }
                            }
                        )
                    elif submit_action.get("url"):
                        on_click = OnClick(open_link={"url": submit_action["url"]})
                        button = Button(text=submit_text, on_click=on_click)
                        button_list = ButtonList(buttons=[button])
                        rendered = button_list.render()
                        widgets.append(rendered)
                    else:
                        # No action, just a button
                        button = Button(text=submit_text)
                        button_list = ButtonList(buttons=[button])
                        rendered = button_list.render()
                        widgets.append(rendered)
                    logger.info(
                        f"✅ Added submit button via ModuleWrapper: {submit_text}"
                    )
                except Exception as e:
                    logger.warning(
                        f"⚠️ Failed to render submit button via ModuleWrapper: {e}, using fallback"
                    )
                    self._add_submit_button_fallback(
                        widgets, submit_text, submit_action
                    )
            else:
                self._add_submit_button_fallback(widgets, submit_text, submit_action)

        # Build card structure
        card = {}
        card_id = str(uuid.uuid4())

        if title:
            card["header"] = {"title": title}
            if subtitle:
                card["header"]["subtitle"] = subtitle

        # Add feedback section if enabled (matching _build_grid_card behavior)
        if ENABLE_FEEDBACK_BUTTONS:
            feedback_section = self._create_feedback_section(card_id)
            card["sections"] = [{"widgets": widgets}, feedback_section]
            card["_card_id"] = card_id

            # Store pattern for feedback collection
            try:
                self._store_card_pattern(
                    card_id=card_id,
                    description=f"form card: {title or 'untitled'}",
                    component_paths=[
                        "card_framework.v2.widgets.text_input.TextInput",
                        "card_framework.v2.widgets.button.Button",
                    ],
                    instance_params={
                        "title": title,
                        "subtitle": subtitle,
                        "fields": [f.get("name") for f in (fields or [])],
                    },
                )
            except Exception as e:
                logger.debug(f"Could not store form card pattern: {e}")
        else:
            card["sections"] = [{"widgets": widgets}]

        logger.info(f"✅ Built form card with {len(fields or [])} fields")
        return card

    def _add_submit_button_fallback(
        self,
        widgets: List[Dict[str, Any]],
        submit_text: str,
        submit_action: Dict[str, Any],
    ) -> None:
        """
        Add a submit button using direct JSON fallback when ModuleWrapper components unavailable.

        Args:
            widgets: List to append the button widget to
            submit_text: Text to display on the button
            submit_action: Dict with 'function', 'url', or 'parameters' keys
        """
        button_dict = {
            "text": submit_text,
            "type": "FILLED",
        }

        if submit_action.get("function"):
            on_click = {
                "action": {
                    "function": submit_action["function"],
                }
            }
            if submit_action.get("parameters"):
                params = submit_action["parameters"]
                if isinstance(params, dict):
                    on_click["action"]["parameters"] = [
                        {"key": k, "value": str(v)} for k, v in params.items()
                    ]
            button_dict["onClick"] = on_click
        elif submit_action.get("url"):
            button_dict["onClick"] = {"openLink": {"url": submit_action["url"]}}

        widgets.append({"buttonList": {"buttons": [button_dict]}})
        logger.info(f"✅ Added submit button via fallback: {submit_text}")

    # =========================================================================
    # WIDGET CONVERTER METHODS - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # These methods are called by _dict_to_widget via WIDGET_CONVERTER_REGISTRY.
    # Each method handles one widget type's conversion from dict to component.
    # =========================================================================

    def _convert_decorated_text_dict(self, data: Dict[str, Any]) -> Optional[Any]:
        """Convert decoratedText dict to DecoratedText component."""
        DecoratedText = self.get_component("DecoratedText")
        if not DecoratedText:
            return None

        kwargs = {
            "text": data.get("text", ""),
            "wrap_text": data.get("wrapText", True),
        }

        if data.get("topLabel"):
            kwargs["top_label"] = data["topLabel"]

        if data.get("startIcon"):
            # Convert icon dict to Icon component with enum value
            icon_data = data["startIcon"]
            if "knownIcon" in icon_data:
                try:
                    Icon = self.get_component("Icon")
                    if Icon and hasattr(Icon, "KnownIcon"):
                        # Convert string to KnownIcon enum value
                        icon_name = icon_data["knownIcon"]
                        known_icon_enum = getattr(Icon.KnownIcon, icon_name, None)
                        if known_icon_enum:
                            kwargs["start_icon"] = Icon(known_icon=known_icon_enum)
                except Exception as e:
                    logger.debug(f"Could not create icon: {e}")

        if data.get("button"):
            btn_data = data["button"]
            Button = self.get_component("Button")
            OnClick = self.get_component("OnClick")
            if (
                Button
                and OnClick
                and btn_data.get("onClick", {}).get("openLink", {}).get("url")
            ):
                url = btn_data["onClick"]["openLink"]["url"]
                on_click = OnClick(open_link={"url": url})
                kwargs["button"] = Button(
                    text=btn_data.get("text", "Open"), on_click=on_click
                )

        return DecoratedText(**kwargs)

    def _convert_text_paragraph_dict(self, data: Dict[str, Any]) -> Optional[Any]:
        """Convert textParagraph dict to TextParagraph component."""
        TextParagraph = self.get_component("TextParagraph")
        if TextParagraph:
            return TextParagraph(text=data.get("text", ""))
        return None

    def _convert_button_list_dict(self, data: Dict[str, Any]) -> Optional[Any]:
        """Convert buttonList dict to ButtonList component."""
        ButtonList = self.get_component("ButtonList")
        Button = self.get_component("Button")
        OnClick = self.get_component("OnClick")

        if ButtonList and Button and OnClick:
            buttons = []
            for btn_data in data.get("buttons", []):
                url = (
                    btn_data.get("onClick", {}).get("openLink", {}).get("url", "#")
                )
                on_click = OnClick(open_link={"url": url})
                buttons.append(
                    Button(text=btn_data.get("text", "Click"), on_click=on_click)
                )
            if buttons:
                return ButtonList(buttons=buttons)
        return None

    def _convert_image_dict(self, data: Dict[str, Any]) -> Optional[Any]:
        """Convert image dict to Image component."""
        Image = self.get_component("Image")
        if Image:
            return Image(
                image_url=data.get("imageUrl", data.get("url", "")),
                alt_text=data.get("altText", ""),
            )
        return None

    def _dict_to_widget(self, widget_dict: Dict[str, Any]) -> Optional[Any]:
        """
        Convert a widget dictionary to an actual component instance.

        Uses WIDGET_CONVERTER_REGISTRY instead of if/elif chains.

        Args:
            widget_dict: Dict like {"decoratedText": {...}} or {"textParagraph": {...}}

        Returns:
            Instantiated widget component
        """
        # REGISTRY-BASED DETECTION: Iterate through WIDGET_CONVERTER_REGISTRY
        for widget_key, method_name in self.WIDGET_CONVERTER_REGISTRY.items():
            if widget_key in widget_dict:
                data = widget_dict[widget_key]
                method = getattr(self, method_name, None)
                if method:
                    return method(data)
                break

        return None

    # =========================================================================
    # LAYOUT BUILDER METHODS - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # These methods are called via LAYOUT_BUILDER_REGISTRY.
    # Each method handles one layout type's construction.
    # =========================================================================

    def _build_layout_columns_image_right(
        self,
        text_widgets: List[Any],
        image_widget: Optional[Any],
        widgets: List[Any],
    ) -> None:
        """Build columns layout with text on left, image on right."""
        if not image_widget:
            # Fallback to standard if no image
            self._build_layout_standard(text_widgets, image_widget, widgets)
            return

        columns = self.build_columns(
            left_widgets=text_widgets,
            right_widgets=[image_widget],
            left_size="FILL_AVAILABLE_SPACE",
            right_size="FILL_MINIMUM_SPACE",
        )
        if columns:
            widgets.append(columns)
        else:
            widgets.extend(text_widgets)
            widgets.append(image_widget)

    def _build_layout_columns_image_left(
        self,
        text_widgets: List[Any],
        image_widget: Optional[Any],
        widgets: List[Any],
    ) -> None:
        """Build columns layout with image on left, text on right."""
        if not image_widget:
            # Fallback to standard if no image
            self._build_layout_standard(text_widgets, image_widget, widgets)
            return

        columns = self.build_columns(
            left_widgets=[image_widget],
            right_widgets=text_widgets,
            left_size="FILL_MINIMUM_SPACE",
            right_size="FILL_AVAILABLE_SPACE",
        )
        if columns:
            widgets.append(columns)
        else:
            widgets.append(image_widget)
            widgets.extend(text_widgets)

    def _build_layout_columns(
        self,
        text_widgets: List[Any],
        image_widget: Optional[Any],
        widgets: List[Any],
    ) -> None:
        """Build generic two-column layout - split widgets evenly."""
        mid = len(text_widgets) // 2
        columns = self.build_columns(
            left_widgets=text_widgets[:mid] or text_widgets,
            right_widgets=text_widgets[mid:] if mid > 0 else [],
        )
        if columns:
            widgets.append(columns)
            if image_widget:
                widgets.append(image_widget)
        else:
            widgets.extend(text_widgets)
            if image_widget:
                widgets.append(image_widget)

    def _build_layout_standard(
        self,
        text_widgets: List[Any],
        image_widget: Optional[Any],
        widgets: List[Any],
    ) -> None:
        """Build standard layout - widgets stacked vertically."""
        widgets.extend(text_widgets)
        if image_widget:
            widgets.append(image_widget)

    def _build_layout_grid(
        self,
        text_widgets: List[Any],
        image_widget: Optional[Any],
        widgets: List[Any],
    ) -> None:
        """Build grid layout (delegates to standard for now)."""
        # Grid layout is handled separately in build_grid_card
        # For build_card, treat as standard
        self._build_layout_standard(text_widgets, image_widget, widgets)

    def _apply_layout(
        self,
        layout_type: str,
        text_widgets: List[Any],
        image_widget: Optional[Any],
        widgets: List[Any],
    ) -> None:
        """
        Apply layout using LAYOUT_BUILDER_REGISTRY.

        Uses registry-based dispatch instead of if/elif chains.
        """
        method_name = self.LAYOUT_BUILDER_REGISTRY.get(layout_type, "_build_layout_standard")
        method = getattr(self, method_name, self._build_layout_standard)
        method(text_widgets, image_widget, widgets)

    # =========================================================================
    # ITEM DICT HANDLER METHODS - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # These methods handle dict items in content["items"] via ITEM_DICT_HANDLER_REGISTRY.
    # =========================================================================

    def _handle_item_text(self, item: Dict[str, Any]) -> Tuple[Optional[Any], str]:
        """
        Handle dict item with 'text' key.

        Returns:
            Tuple of (widget, widget_type) where widget_type is 'text' or 'image'
        """
        widget = self.build_decorated_text(
            text=item["text"],
            top_label=item.get("top_label") or item.get("label"),
            bottom_label=item.get("bottom_label"),
            button_url=item.get("button_url") or item.get("url"),
            button_text=item.get("button_text"),
            icon=item.get("icon"),
        )
        return (widget, "text")

    def _handle_item_image(self, item: Dict[str, Any]) -> Tuple[Optional[Any], str]:
        """
        Handle dict item with 'image_url' key.

        Returns:
            Tuple of (widget, widget_type) where widget_type is 'text' or 'image'
        """
        widget = self.build_image(
            item["image_url"],
            item.get("alt_text"),
        )
        return (widget, "image")

    def _process_dict_item(self, item: Dict[str, Any]) -> Tuple[Optional[Any], str]:
        """
        Process a dict item using ITEM_DICT_HANDLER_REGISTRY.

        Uses registry-based dispatch instead of if/elif chains.

        Returns:
            Tuple of (widget, widget_type) where widget_type is 'text' or 'image'
        """
        for key, method_name in self.ITEM_DICT_HANDLER_REGISTRY.items():
            if key in item:
                method = getattr(self, method_name, None)
                if method:
                    return method(item)
                break
        return (None, "unknown")

    # =========================================================================
    # MAIN CARD BUILDING
    # =========================================================================

    def build_card(
        self,
        description: str,
        content: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build a complete card from description and content.

        Args:
            description: Natural language description (used for layout inference)
            content: Dict with card content:
                - title: Card title
                - subtitle: Card subtitle
                - section_header: Section header
                - items: List of content items (text, prices, etc.)
                - image_url: Optional image URL
                - buttons: Optional list of {text, url} dicts

        Returns:
            Rendered card JSON ready for Google Chat API
        """
        if not self._initialized:
            self.initialize()

        # Infer layout from description
        layout = self.infer_layout(description)
        logger.info(f"Inferred layout: {layout['layout_type']}")

        # Build widgets based on content
        widgets = []
        text_widgets = []
        image_widget = None

        # Process items with smart inference
        # Following the Manifesto: "One flow for all, no special trap"
        # Uses build_widget_from_inference() with COMPONENT_BUILDER_REGISTRY
        for item in content.get("items", []):
            if isinstance(item, str):
                inference = self.infer_content_type(item)
                logger.debug(f"Inferred '{item[:30]}...' as {inference['type']}")

                # Use registry-based builder instead of if/elif chain
                widget = self.build_widget_from_inference(item, inference)

                if widget:
                    # Route to appropriate list based on component type
                    if inference["suggested_component"] == "Image":
                        image_widget = widget
                    else:
                        text_widgets.append(widget)

            elif isinstance(item, dict):
                # Explicit widget specification - use registry-based handler
                widget, widget_type = self._process_dict_item(item)
                if widget:
                    if widget_type == "image":
                        image_widget = widget
                    else:
                        text_widgets.append(widget)

        # Handle explicit image_url in content (with optional click destination)
        if content.get("image_url") and not image_widget:
            image_widget = self.build_image(
                content["image_url"],
                on_click_url=content.get("image_click_url"),
            )

        # Build layout based on inference - using LAYOUT_BUILDER_REGISTRY
        # Following the Manifesto: "One flow for all, no special trap"
        self._apply_layout(layout["layout_type"], text_widgets, image_widget, widgets)

        # Add buttons if provided
        if content.get("buttons"):
            ButtonList = self.get_component("ButtonList")
            Button = self.get_component("Button")
            OnClick = self.get_component("OnClick")

            if ButtonList and Button and OnClick:
                buttons = []
                for btn in content["buttons"]:
                    on_click = OnClick(open_link={"url": btn.get("url", "#")})
                    buttons.append(
                        Button(text=btn.get("text", "Click"), on_click=on_click)
                    )

                if buttons:
                    widgets.append(ButtonList(buttons=buttons))

        # Build section
        section = self.build_section(
            header=content.get("section_header", ""),
            widgets=widgets,
        )

        if not section:
            logger.error("Failed to build section")
            return {}

        # Render to JSON
        rendered = section.render()

        # Build sections list
        sections = [rendered]

        # Add feedback section if enabled
        card_id = None
        if ENABLE_FEEDBACK_BUTTONS:
            card_id = str(uuid.uuid4())
            feedback_section = self._create_feedback_section(card_id)
            sections.append(feedback_section)

            # Store pattern for feedback collection (async-safe, non-blocking)
            try:
                component_paths = list(self._components.keys())  # Components used
                self._store_card_pattern(
                    card_id=card_id,
                    description=description,
                    component_paths=[
                        self.FALLBACK_PATHS.get(p, p) for p in component_paths
                    ],
                    instance_params=content,
                )
            except Exception as e:
                logger.debug(f"Could not store card pattern: {e}")

        # Wrap in card structure if title provided
        if content.get("title"):
            return {
                "header": {
                    "title": content["title"],
                    "subtitle": content.get("subtitle", ""),
                },
                "sections": sections,
                "_card_id": card_id,  # Internal: for tracking
            }

        # If no title, return just the section(s)
        if len(sections) == 1:
            return rendered
        return {"sections": sections, "_card_id": card_id}

    # =========================================================================
    # HELPER: Format colored price
    # =========================================================================

    def format_price(
        self,
        original_price: str,
        sale_price: str,
        _original_color: str = "red",  # Reserved for future: style strikethrough
        sale_color: str = "green",
    ) -> str:
        """
        Format a price with colors for display.

        Example:
            format_price("$199.00", "$99.00")
            Returns: '<font color="#34a853">$99.00</font> <s>$199.00</s>'
        """
        sale_hex = self.COLOR_MAP.get(sale_color, sale_color)

        return f'<font color="{sale_hex}">{sale_price}</font> <s>{original_price}</s>'

    def format_colored_text(self, text: str, color: str) -> str:
        """
        Wrap text in font color tag.

        Example:
            format_colored_text("Success!", "green")
            Returns: '<font color="#34a853">Success!</font>'
        """
        hex_color = self.COLOR_MAP.get(color, color)
        return f'<font color="{hex_color}">{text}</font>'

    # =========================================================================
    # HELPER: Markdown conversion for Google Chat
    # =========================================================================

    @classmethod
    def convert_markdown_to_chat(cls, text: str) -> str:
        """
        Convert standard markdown to Google Chat HTML format.

        Uses MARKDOWN_TO_CHAT_PATTERNS registry instead of hardcoded re.sub calls.
        Following the Manifesto: "One flow for all, no special trap"

        Google Chat textParagraph supports HTML tags:
        - <b>bold</b>
        - <i>italic</i>
        - <s>strikethrough</s>
        - <u>underline</u>
        - <font color="#hex">colored text</font>
        - <a href="url">link</a>

        Args:
            text: Text with standard markdown

        Returns:
            Text converted to HTML for Google Chat
        """
        if not text:
            return text

        # Apply all patterns from registry
        for pattern, replacement, _description in cls.MARKDOWN_TO_CHAT_PATTERNS:
            text = re.sub(pattern, replacement, text)

        return text

    # =========================================================================
    # FEEDBACK LOOP INTEGRATION
    # =========================================================================

    # =========================================================================
    # FEEDBACK WIDGET BUILDER METHODS - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # These methods are called via FEEDBACK_WIDGET_BUILDERS registry.
    # Each method tries the component path first, then falls back to JSON.
    # =========================================================================

    def _get_feedback_base_url(self, feedback_webhook_url: str = None) -> str:
        """
        Get the base URL for feedback webhooks.

        Priority: parameter → env var → settings → fallback
        """
        if feedback_webhook_url:
            return feedback_webhook_url

        base_url = os.getenv("CARD_FEEDBACK_WEBHOOK")
        if base_url:
            return base_url

        try:
            from config.settings import settings
            return f"{settings.base_url}/card-feedback"
        except Exception:
            return "https://example.com/card-feedback"

    def _build_feedback_prompt(
        self, _card_id: str, _base_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Build the feedback prompt widget ("Was this card helpful?").

        Tries component path first, falls back to JSON.

        Args:
            _card_id: Unused, kept for consistent builder signature
            _base_url: Unused, kept for consistent builder signature
        """
        # Try component path
        prompt_widget = self.build_decorated_text(
            text="<i>Was this card helpful?</i>",
            wrap_text=True,
        )
        if prompt_widget:
            try:
                return prompt_widget.render()
            except Exception as e:
                logger.debug(f"Prompt widget render failed: {e}")

        # Fallback to JSON
        return {
            "decoratedText": {
                "text": "<i>Was this card helpful?</i>",
                "wrapText": True,
            }
        }

    def _build_feedback_buttons(
        self, card_id: str, base_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Build the feedback buttons widget (👍 Good / 👎 Bad).

        Tries component path first, falls back to JSON.
        """
        # Define button configs (single source of truth)
        button_configs = [
            {"text": "👍 Good", "feedback": "positive"},
            {"text": "👎 Bad", "feedback": "negative"},
        ]

        # Try component path
        ButtonList = self.get_component("ButtonList")
        Button = self.get_component("Button")
        OnClick = self.get_component("OnClick")

        if ButtonList and Button and OnClick:
            try:
                buttons = []
                for config in button_configs:
                    on_click = OnClick(
                        open_link={
                            "url": f"{base_url}?card_id={card_id}&feedback={config['feedback']}"
                        }
                    )
                    buttons.append(Button(text=config["text"], on_click=on_click))

                button_list = ButtonList(buttons=buttons)
                logger.debug(
                    f"✅ Built feedback buttons via ModuleWrapper for card {card_id[:8]}..."
                )
                return button_list.render()
            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to build feedback buttons via ModuleWrapper: {e}, using fallback"
                )

        # Fallback to JSON (using same button_configs for consistency)
        return {
            "buttonList": {
                "buttons": [
                    {
                        "text": config["text"],
                        "onClick": {
                            "openLink": {
                                "url": f"{base_url}?card_id={card_id}&feedback={config['feedback']}"
                            }
                        },
                    }
                    for config in button_configs
                ]
            }
        }

    # =========================================================================
    # DUAL FEEDBACK BUILDERS - Content (values/inputs) and Form (structure)
    # These support the feedback loop's hybrid query system that separately
    # boosts content-good patterns and form-good patterns.
    # =========================================================================

    def _build_content_feedback_prompt(
        self, _card_id: str, _base_url: str
    ) -> Optional[Dict[str, Any]]:
        """Build the content feedback prompt ("Was the content correct?")."""
        prompt_widget = self.build_decorated_text(
            text="<i>Was the <b>content</b> correct?</i>",
            wrap_text=True,
        )
        if prompt_widget:
            try:
                return prompt_widget.render()
            except Exception as e:
                logger.debug(f"Content prompt widget render failed: {e}")

        return {
            "decoratedText": {
                "text": "<i>Was the <b>content</b> correct?</i>",
                "wrapText": True,
            }
        }

    def _build_content_feedback_buttons(
        self, card_id: str, base_url: str
    ) -> Optional[Dict[str, Any]]:
        """Build content feedback buttons (affects inputs vector searches)."""
        button_configs = [
            {"text": "👍 Good", "feedback": "positive", "type": "content"},
            {"text": "👎 Bad", "feedback": "negative", "type": "content"},
        ]
        return self._build_typed_feedback_buttons(card_id, base_url, button_configs)

    def _build_form_feedback_prompt(
        self, _card_id: str, _base_url: str
    ) -> Optional[Dict[str, Any]]:
        """Build the form feedback prompt ("Was the layout correct?")."""
        prompt_widget = self.build_decorated_text(
            text="<i>Was the <b>layout</b> correct?</i>",
            wrap_text=True,
        )
        if prompt_widget:
            try:
                return prompt_widget.render()
            except Exception as e:
                logger.debug(f"Form prompt widget render failed: {e}")

        return {
            "decoratedText": {
                "text": "<i>Was the <b>layout</b> correct?</i>",
                "wrapText": True,
            }
        }

    def _build_form_feedback_buttons(
        self, card_id: str, base_url: str
    ) -> Optional[Dict[str, Any]]:
        """Build form feedback buttons (affects relationships vector searches)."""
        button_configs = [
            {"text": "👍 Good", "feedback": "positive", "type": "form"},
            {"text": "👎 Bad", "feedback": "negative", "type": "form"},
        ]
        return self._build_typed_feedback_buttons(card_id, base_url, button_configs)

    def _build_typed_feedback_buttons(
        self, card_id: str, base_url: str, button_configs: List[Dict[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Build feedback buttons with feedback_type parameter.

        The feedback_type (content vs form) determines which vector is boosted:
        - content: Boosts inputs vector (parameter values, defaults)
        - form: Boosts relationships vector (card structure, nesting)
        """
        ButtonList = self.get_component("ButtonList")
        Button = self.get_component("Button")
        OnClick = self.get_component("OnClick")

        if ButtonList and Button and OnClick:
            try:
                buttons = []
                for config in button_configs:
                    url = f"{base_url}?card_id={card_id}&feedback={config['feedback']}&feedback_type={config['type']}"
                    on_click = OnClick(open_link={"url": url})
                    buttons.append(Button(text=config["text"], on_click=on_click))

                button_list = ButtonList(buttons=buttons)
                logger.debug(
                    f"✅ Built {config['type']} feedback buttons for card {card_id[:8]}..."
                )
                return button_list.render()
            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to build typed feedback buttons via ModuleWrapper: {e}, using fallback"
                )

        # Fallback to JSON
        return {
            "buttonList": {
                "buttons": [
                    {
                        "text": config["text"],
                        "onClick": {
                            "openLink": {
                                "url": f"{base_url}?card_id={card_id}&feedback={config['feedback']}&feedback_type={config['type']}"
                            }
                        },
                    }
                    for config in button_configs
                ]
            }
        }

    def _create_feedback_section(
        self, card_id: str, feedback_webhook_url: str = None
    ) -> Dict[str, Any]:
        """
        Create a feedback section with dual 👍/👎 buttons using the component system.

        Creates TWO feedback prompts:
        1. Content feedback - rates the values/inputs (affects inputs vector)
        2. Form feedback - rates the layout/structure (affects relationships vector)

        Uses FEEDBACK_WIDGET_BUILDERS registry instead of duplicated if/else chains.
        Following the Manifesto: "One flow for all, no special trap"

        Args:
            card_id: Unique ID for this card (used to link feedback)
            feedback_webhook_url: Optional custom webhook URL for feedback

        Returns:
            Section dict with feedback widgets
        """
        base_url = self._get_feedback_base_url(feedback_webhook_url)
        widgets = []

        # Build widgets using registry
        for _widget_name, method_name in self.FEEDBACK_WIDGET_BUILDERS:
            method = getattr(self, method_name, None)
            if method:
                widget = method(card_id, base_url)
                if widget:
                    widgets.append(widget)
            else:
                logger.warning(f"⚠️ Feedback widget builder not found: {method_name}")

        return {"widgets": widgets}

    def _store_card_pattern(
        self,
        card_id: str,
        description: str,
        component_paths: List[str],
        instance_params: Dict[str, Any],
        user_email: str = None,
    ) -> bool:
        """
        Store a card usage pattern for feedback collection.

        Args:
            card_id: Unique ID for this card
            description: Original card description
            component_paths: List of component paths used
            instance_params: Parameters used to build the card
            user_email: User who created the card

        Returns:
            True if stored successfully
        """
        try:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()
            point_id = feedback_loop.store_instance_pattern(
                card_description=description,
                component_paths=component_paths,
                instance_params=instance_params,
                feedback=None,  # Will be updated when user clicks 👍/👎
                user_email=user_email,
                card_id=card_id,
            )

            if point_id:
                logger.info(f"📝 Stored card pattern for feedback: {card_id}")
                return True
            return False

        except Exception as e:
            logger.warning(f"Failed to store card pattern: {e}")
            return False

    def _build_card_from_explicit_params(
        self,
        title: str = None,
        subtitle: str = None,
        image_url: str = None,
        text: str = None,
        buttons: List[Dict[str, Any]] = None,
        fields: List[Dict[str, Any]] = None,
        submit_action: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Build a card using ONLY explicit params (strict mode).

        This bypasses all NL parsing and proven pattern merging.
        Use this for deterministic output when you have all required params.

        Args:
            title: Card header title
            subtitle: Card header subtitle
            image_url: Image URL
            text: Text content
            buttons: List of button dicts
            fields: Form fields (if form card)
            submit_action: Form submit action

        Returns:
            Rendered card JSON
        """
        logger.info("🔒 Building card from explicit params only (strict mode)")

        # Form card path
        if fields:
            return self._build_form_card(
                title=title,
                subtitle=subtitle,
                text=text,
                fields=fields,
                submit_action=submit_action,
            )

        # Build standard card structure
        card = {}

        if title:
            card["header"] = {
                "title": title,
                "subtitle": subtitle or "",
            }

        sections = [{"widgets": []}]

        # Add text widget
        if text:
            converted_text = self.convert_markdown_to_chat(text)
            sections[0]["widgets"].append({"textParagraph": {"text": converted_text}})

        # Add image widget
        if image_url:
            sections[0]["widgets"].append({"image": {"imageUrl": image_url}})

        # Add buttons
        if buttons:
            button_widgets = []
            for btn in buttons:
                if isinstance(btn, dict):
                    btn_widget = {
                        "text": btn.get("text", "Button"),
                        "onClick": {"openLink": {"url": btn.get("url") or btn.get("onclick_action", "#")}},
                    }
                    button_widgets.append(btn_widget)
            if button_widgets:
                sections[0]["widgets"].append({"buttonList": {"buttons": button_widgets}})

        card["sections"] = sections

        # Add feedback buttons
        if ENABLE_FEEDBACK_BUTTONS:
            card_id = str(uuid.uuid4())
            feedback_section = self._create_feedback_section(card_id)
            card["sections"].append(feedback_section)
            card["_card_id"] = card_id

        return card

    def _validate_and_finalize_card(
        self,
        card: Dict[str, Any],
        provenance: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        """
        Validate card structure and add metadata before return.

        This is the pre-flight validation recommended in the architecture doc.
        Catches schema issues BEFORE sending to webhook.

        Args:
            card: Card dict to validate
            provenance: Param provenance tracking dict

        Returns:
            Validated card with _provenance and _validation metadata
        """
        validation_issues = []

        # =====================================================================
        # SCHEMA VALIDATION: Check for common issues before webhook POST
        # =====================================================================

        # 1. Check sections exist
        if "sections" not in card or not card["sections"]:
            validation_issues.append("Card has no sections")

        # 2. Check for internal fields that should be stripped before API call
        internal_fields = [k for k in card.keys() if k.startswith("_")]
        if internal_fields:
            # These are OK - they'll be stripped by _strip_internal_fields() before delivery
            pass

        # 3. Check button structure (common failure point)
        for section in card.get("sections", []):
            for widget in section.get("widgets", []):
                if "buttonList" in widget:
                    buttons = widget["buttonList"].get("buttons", [])
                    for i, btn in enumerate(buttons):
                        # Check for invalid "button" wrapper (should be direct button object)
                        if "button" in btn:
                            validation_issues.append(
                                f"Button {i} has invalid 'button' wrapper - should be direct button object"
                            )
                        # Check for required fields
                        if "text" not in btn and "icon" not in btn:
                            validation_issues.append(f"Button {i} missing 'text' or 'icon'")

        # 4. Check header structure
        if "header" in card:
            header = card["header"]
            if "title" not in header:
                validation_issues.append("Header missing 'title' field")

        # Add validation metadata
        card["_validation"] = {
            "passed": len(validation_issues) == 0,
            "issues": validation_issues if validation_issues else None,
        }

        if provenance:
            card["_provenance"] = provenance

        if validation_issues:
            logger.warning(f"⚠️ Card validation issues: {validation_issues}")
        else:
            logger.debug("✅ Card passed pre-flight validation")

        return card

    # =========================================================================
    # PATTERN-DRIVEN COMPONENT INSTANTIATION - Following the Manifesto:
    # "One flow for all, no special trap"
    #
    # These methods enable rebuilding/extending instance patterns with new
    # parameters, using PATTERN_EXTENSION_HANDLERS for component-specific logic.
    # =========================================================================

    def _rebuild_from_pattern(
        self,
        pattern: Dict[str, Any],
        new_params: Dict[str, Any],
        render: bool = True,
    ) -> Union[List[Dict[str, Any]], List[Any]]:
        """
        Rebuild a card by extending an existing pattern's component_paths.

        🔄 RECURSION PATTERN: Uses PATTERN_EXTENSION_HANDLERS registry
        for component-specific extension logic.

        Args:
            pattern: Instance pattern dict with parent_paths and instance_params
            new_params: New parameters to merge/extend with
            render: If True, return rendered JSON; if False, return component instances

        Returns:
            List of rendered widget dicts (if render=True) or component instances
        """
        widgets = []
        parent_paths = pattern.get("parent_paths", [])
        pattern_params = pattern.get("instance_params", {})

        logger.info(f"🔄 Rebuilding from pattern with {len(parent_paths)} component(s)")

        for path in parent_paths:
            # Load the component class
            cls = self._load_component_by_path(path)
            if not cls:
                logger.warning(f"⚠️ Could not load component: {path}")
                continue

            class_name = cls.__name__

            # Check PATTERN_EXTENSION_HANDLERS for component-specific logic
            handler_name = self.PATTERN_EXTENSION_HANDLERS.get(class_name)
            if handler_name:
                # Use component-specific handler
                handler = getattr(self, handler_name, None)
                if handler:
                    merged_params = handler(pattern_params, new_params)
                    logger.debug(f"📦 Using {handler_name} for {class_name}")
                else:
                    merged_params = self._merge_pattern_params(pattern_params, new_params)
            else:
                # Default: use generic merge
                merged_params = self._merge_pattern_params(pattern_params, new_params)

            # Filter params to only those accepted by the component
            try:
                # Try to instantiate with merged params
                instance = cls(**merged_params)
                if render:
                    widgets.append(instance.render())
                else:
                    widgets.append(instance)
                logger.debug(f"✅ Instantiated {class_name} from pattern")
            except TypeError as e:
                # Some params may not be accepted - try with filtered params
                logger.debug(f"⚠️ {class_name} instantiation failed: {e}, trying filtered params")
                filtered = self._filter_params_for_component(cls, merged_params)
                try:
                    instance = cls(**filtered)
                    if render:
                        widgets.append(instance.render())
                    else:
                        widgets.append(instance)
                    logger.debug(f"✅ Instantiated {class_name} with filtered params")
                except Exception as e2:
                    logger.warning(f"❌ Could not instantiate {class_name}: {e2}")

        return widgets

    def _merge_pattern_params(
        self,
        pattern_params: Dict[str, Any],
        new_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge pattern params with new params using PATTERN_PARAM_MERGE_MODES registry.

        🔄 RECURSION PATTERN: Uses PATTERN_PARAM_MERGE_MODES for param-specific merge logic.

        Args:
            pattern_params: Parameters from the stored pattern
            new_params: New parameters to merge in

        Returns:
            Merged parameters dict
        """
        merged = dict(pattern_params)  # Start with pattern

        for key, new_value in new_params.items():
            if new_value is None:
                continue

            mode = self.PATTERN_PARAM_MERGE_MODES.get(key, "replace")

            if mode == "extend" and key in merged:
                # Extend lists
                old_value = merged[key]
                if isinstance(old_value, list) and isinstance(new_value, list):
                    merged[key] = old_value + new_value
                else:
                    merged[key] = new_value
            elif mode == "deep_merge" and key in merged:
                # Deep merge dicts
                old_value = merged[key]
                if isinstance(old_value, dict) and isinstance(new_value, dict):
                    merged[key] = {**old_value, **new_value}
                else:
                    merged[key] = new_value
            else:
                # Replace (new takes priority)
                merged[key] = new_value

        return merged

    def _filter_params_for_component(
        self,
        cls: type,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Filter params to only those accepted by a component's __init__.

        Args:
            cls: Component class
            params: Parameters to filter

        Returns:
            Filtered parameters dict
        """
        import inspect

        try:
            sig = inspect.signature(cls.__init__)
            valid_params = set(sig.parameters.keys()) - {"self"}
            return {k: v for k, v in params.items() if k in valid_params}
        except (ValueError, TypeError):
            # Can't inspect - return original
            return params

    def _extend_grid_pattern(
        self,
        pattern_params: Dict[str, Any],
        new_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handler for extending Grid component patterns.

        Handles:
        - Adding new images to existing grid items
        - Changing column_count
        - Replacing vs extending items list

        Args:
            pattern_params: Parameters from the stored pattern
            new_params: New parameters to merge in

        Returns:
            Merged parameters ready for Grid instantiation
        """
        merged = dict(pattern_params)

        # Handle column_count (replace)
        if "column_count" in new_params:
            merged["column_count"] = new_params["column_count"]

        # Handle images → convert to items
        if "images" in new_params:
            new_images = new_params["images"]
            image_titles = new_params.get("image_titles", [])

            # Build GridItem-style items from images
            new_items = []
            for i, img_url in enumerate(new_images):
                item = {"image": {"imageUrl": img_url}}
                if i < len(image_titles):
                    item["title"] = image_titles[i]
                new_items.append(item)

            # Extend or replace items based on mode
            if new_params.get("extend_items", False):
                old_items = merged.get("items", [])
                merged["items"] = old_items + new_items
            else:
                merged["items"] = new_items

        # Handle explicit items
        if "items" in new_params and "images" not in new_params:
            if new_params.get("extend_items", False):
                old_items = merged.get("items", [])
                merged["items"] = old_items + new_params["items"]
            else:
                merged["items"] = new_params["items"]

        logger.debug(f"🔲 Grid pattern: {len(merged.get('items', []))} items, "
                    f"{merged.get('column_count', 2)} columns")
        return merged

    def _extend_button_list_pattern(
        self,
        pattern_params: Dict[str, Any],
        new_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handler for extending ButtonList component patterns.

        Handles:
        - Adding new buttons to existing list
        - Replacing all buttons

        Args:
            pattern_params: Parameters from the stored pattern
            new_params: New parameters to merge in

        Returns:
            Merged parameters ready for ButtonList instantiation
        """
        merged = dict(pattern_params)

        if "buttons" in new_params:
            if new_params.get("extend_buttons", False):
                old_buttons = merged.get("buttons", [])
                merged["buttons"] = old_buttons + new_params["buttons"]
            else:
                merged["buttons"] = new_params["buttons"]

        logger.debug(f"🔘 ButtonList pattern: {len(merged.get('buttons', []))} buttons")
        return merged

    def _extend_section_pattern(
        self,
        pattern_params: Dict[str, Any],
        new_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handler for extending Section component patterns.

        Handles:
        - Adding new widgets to section
        - Changing section header

        Args:
            pattern_params: Parameters from the stored pattern
            new_params: New parameters to merge in

        Returns:
            Merged parameters ready for Section instantiation
        """
        merged = dict(pattern_params)

        # Header is replaced
        if "header" in new_params:
            merged["header"] = new_params["header"]

        # Widgets can be extended or replaced
        if "widgets" in new_params:
            if new_params.get("extend_widgets", False):
                old_widgets = merged.get("widgets", [])
                merged["widgets"] = old_widgets + new_params["widgets"]
            else:
                merged["widgets"] = new_params["widgets"]

        logger.debug(f"📋 Section pattern: {len(merged.get('widgets', []))} widgets")
        return merged

    def _extend_decorated_text_pattern(
        self,
        pattern_params: Dict[str, Any],
        new_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handler for extending DecoratedText component patterns.

        This is mostly a "replace" operation since DecoratedText
        doesn't have list-type params. But we preserve structure.

        Args:
            pattern_params: Parameters from the stored pattern
            new_params: New parameters to merge in

        Returns:
            Merged parameters ready for DecoratedText instantiation
        """
        merged = dict(pattern_params)

        # All DecoratedText params are replace-mode
        for key in ["text", "top_label", "bottom_label", "icon", "button", "switch_control"]:
            if key in new_params and new_params[key] is not None:
                merged[key] = new_params[key]

        logger.debug(f"📝 DecoratedText pattern: text='{merged.get('text', '')[:30]}...'")
        return merged

    def rebuild_card_from_pattern(
        self,
        description: str,
        new_params: Dict[str, Any] = None,
        min_score: float = 0.5,
    ) -> Optional[Dict[str, Any]]:
        """
        High-level method to find a matching pattern and rebuild with new params.

        This is the main entry point for pattern-driven card generation.

        Args:
            description: Description to match against stored patterns
            new_params: New parameters to merge/extend
            min_score: Minimum similarity score for pattern match

        Returns:
            Rendered card dict or None if no matching pattern found
        """
        try:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()

            # Query for matching patterns using Qdrant's recommend API
            # This uses point IDs as positive/negative examples for native similarity
            content_patterns, form_patterns = feedback_loop.query_patterns_with_recommend(
                description=description,
                limit=5,
                strategy="best_score",  # More diverse results
            )

            # Combine content and form patterns, prefer content (higher weight on values)
            pattern_results = content_patterns + form_patterns

            # Find best pattern above threshold
            # With recommend API, results are already ranked by similarity to positives
            # and dissimilarity to negatives, so we just need to check score threshold
            best_pattern = None
            for result in pattern_results:
                if result.get("score", 0) >= min_score:
                    best_pattern = result
                    break

            if not best_pattern:
                logger.debug(f"No matching pattern found (min_score={min_score})")
                return None

            logger.info(f"🎯 Found pattern to rebuild: {best_pattern.get('name')} "
                       f"(score={best_pattern.get('score', 0):.3f})")

            # Build pattern dict from result
            pattern = {
                "parent_paths": best_pattern.get("parent_paths", []),
                "instance_params": best_pattern.get("instance_params", {}),
            }

            # Rebuild with new params
            widgets = self._rebuild_from_pattern(pattern, new_params or {})

            if not widgets:
                logger.warning("Pattern rebuild produced no widgets")
                return None

            # Wrap in card structure
            card = {
                "sections": [{"widgets": widgets}],
                "_rebuilt_from_pattern": best_pattern.get("name"),
                "_pattern_score": best_pattern.get("score"),
            }

            # Add header if in new_params
            if new_params and (new_params.get("title") or new_params.get("subtitle")):
                card["header"] = {
                    "title": new_params.get("title", ""),
                    "subtitle": new_params.get("subtitle", ""),
                }

            return card

        except Exception as e:
            logger.warning(f"Pattern rebuild failed: {e}")
            return None

    def _get_proven_params(self, description: str) -> Optional[Dict[str, Any]]:
        """
        Get proven parameters from similar successful cards.

        Args:
            description: Card description to match

        Returns:
            instance_params from best matching positive pattern, or None
        """
        try:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()
            return feedback_loop.get_proven_params_for_description(description)

        except Exception as e:
            logger.debug(f"Could not get proven params: {e}")
            return None


# Global instance for convenience
_builder: Optional[SmartCardBuilder] = None


def get_smart_card_builder() -> SmartCardBuilder:
    """Get the global SmartCardBuilder instance."""
    global _builder
    if _builder is None:
        _builder = SmartCardBuilder()
        _builder.initialize()
    return _builder


def build_card(description: str, content: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to build a card."""
    builder = get_smart_card_builder()
    return builder.build_card(description, content)
