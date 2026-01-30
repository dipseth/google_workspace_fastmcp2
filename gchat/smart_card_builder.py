"""
Smart Card Builder v2 - DSL + Embeddings Focused

A streamlined card builder that uses:
1. Structure DSL: §[δ×3, Ƀ[ᵬ×2]] for component hierarchy
2. Content DSL: δ 'text' success bold for styled content
3. Qdrant ColBERT embeddings for semantic search
4. ModuleWrapper for component loading

This replaces the legacy NL parsing with a cleaner DSL-first approach.

Usage:
    builder = SmartCardBuilderV2()
    card = builder.build(
        description="§[δ×3, Ƀ[ᵬ×2]] Dashboard\\n\\nδ 'Status: Online' success bold",
        title="My Card"
    )
"""

import json
import logging
import os
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from config.settings import settings as _settings
from middleware.filters.styling_filters import SEMANTIC_COLORS
from middleware.template_core.jinja_environment import JinjaEnvironmentManager
from middleware.filters import register_all_filters

load_dotenv()

logger = logging.getLogger(__name__)

# Feature flag for feedback buttons
ENABLE_FEEDBACK_BUTTONS = os.getenv("ENABLE_CARD_FEEDBACK", "true").lower() == "true"


# =============================================================================
# GENERIC COMPONENT CONFIGURATION (Mapping-Driven, No If/Else)
# =============================================================================
# These mappings replace hardcoded if/elif chains with dynamic configuration.
# They can be extended or derived from wrapper metadata.

# Context consumers: component_name -> (context_key, index_key)
# Defines which context resource each component type consumes from
CONTEXT_CONSUMERS: Dict[str, Tuple[str, str]] = {
    "Button": ("buttons", "_button_index"),
    "DecoratedText": ("content_texts", "_text_index"),
    "TextParagraph": ("content_texts", "_text_index"),
}

# Container components: component_name -> children_field
# Defines how container components store their children
CONTAINER_CHILDREN: Dict[str, str] = {
    "ButtonList": "buttons",
    "Grid": "items",
    "ChipList": "chips",
    "Columns": "columnItems",
    "Column": "widgets",
}

# Child component mapping for containers: what child type each container expects
CONTAINER_CHILD_TYPE: Dict[str, str] = {
    "ButtonList": "Button",
    "Grid": "GridItem",
    "ChipList": "Chip",
    "Columns": "Column",
}

# Form components that require a 'name' field
FORM_COMPONENTS: set = {"TextInput", "DateTimePicker", "SelectionInput", "SwitchControl"}

# Components with no content (just structure)
EMPTY_COMPONENTS: set = {"Divider"}

# =============================================================================
# COMPONENT PARAMS REGISTRY - Documents expected params for each component
# =============================================================================

COMPONENT_PARAMS: Dict[str, Dict[str, str]] = {
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
}


# =============================================================================
# INPUT MAPPING REPORT - Tracks how inputs are consumed during card building
# =============================================================================


@dataclass
class InputMappingReport:
    """Tracks how inputs are consumed during card building."""

    consumptions: List[Dict[str, str]] = field(default_factory=list)

    def record(
        self, input_type: str, index: int, value: str, component: str, field_name: str
    ):
        """Record a consumption event."""
        preview = value[:50] + "..." if len(value) > 50 else value
        self.consumptions.append(
            {
                "input": f"{input_type}[{index}]",
                "value_preview": preview,
                "component": component,
                "field": field_name,
            }
        )

    def to_dict(self, context: Dict) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        buttons_total = len(context.get("buttons", []))
        texts_total = len(context.get("content_texts", []))
        return {
            "mappings": self.consumptions,
            "unconsumed": {
                "buttons": buttons_total - context.get("_button_index", 0),
                "texts": texts_total - context.get("_text_index", 0),
            },
        }


# =============================================================================
# PREPARED PATTERN - Deferred Rendering Support
# =============================================================================


class PreparedPattern:
    """
    A pattern prepared for rendering with deferred parameter population.

    This class allows you to:
    1. Load component classes from the wrapper once
    2. Set/update parameters before rendering
    3. Render to Google Chat JSON when ready

    Usage:
        # Get a prepared pattern
        prepared = PreparedPattern.from_pattern(pattern, wrapper)

        # Set params (chainable)
        prepared.set_params(text="Hello", title="My Card")

        # Or set individual params
        prepared.set_param("buttons", [{"text": "Click", "url": "..."}])

        # Render when ready
        card_json = prepared.render()

        # Or get instances without rendering (for inspection/modification)
        instances = prepared.get_instances()
    """

    def __init__(self, component_paths: List[str], wrapper):
        """
        Initialize with component paths and wrapper.

        Args:
            component_paths: List of component names (e.g., ["Section", "DecoratedText", "ButtonList"])
            wrapper: ModuleWrapper instance for loading component classes
        """
        self.component_paths = component_paths
        self.wrapper = wrapper
        self.params: Dict[str, Any] = {}
        self._component_classes: Dict[str, Any] = {}
        self._load_component_classes()

    def _load_component_classes(self):
        """Load component classes from wrapper."""
        if not self.wrapper:
            return

        for comp_name in set(self.component_paths):
            if comp_name in ("Section",):  # Skip containers
                continue

            # Try common paths
            paths_to_try = [
                f"card_framework.v2.widgets.{comp_name.lower()}.{comp_name}",
                f"card_framework.v2.{comp_name.lower()}.{comp_name}",
            ]

            for path in paths_to_try:
                comp_class = self.wrapper.get_component_by_path(path)
                if comp_class:
                    self._component_classes[comp_name] = comp_class
                    break

    def set_params(self, **params) -> "PreparedPattern":
        """
        Set multiple parameters at once. Chainable.

        Args:
            **params: Parameter key-value pairs

        Returns:
            Self for chaining
        """
        self.params.update(params)
        return self

    def set_param(self, key: str, value: Any) -> "PreparedPattern":
        """
        Set a single parameter. Chainable.

        Args:
            key: Parameter name
            value: Parameter value

        Returns:
            Self for chaining
        """
        self.params[key] = value
        return self

    def get_instances(self) -> List[Dict[str, Any]]:
        """
        Get component instances without rendering.

        Useful for inspection or manual modification before rendering.

        Returns:
            List of dicts with 'name', 'class', 'instance' (or None if instantiation failed)
        """
        instances = []
        for comp_name in self.component_paths:
            if comp_name in ("Section",):
                continue

            comp_class = self._component_classes.get(comp_name)
            instance = None

            if comp_class:
                # Get params relevant to this component
                comp_params = self._get_params_for_component(comp_name)
                instance = self.wrapper.create_card_component(comp_class, comp_params)

            instances.append({
                "name": comp_name,
                "class": comp_class,
                "instance": instance,
            })

        return instances

    def _get_params_for_component(self, comp_name: str) -> Dict[str, Any]:
        """Get relevant params for a specific component type."""
        # Map common param names to component-specific ones
        # TODO REPLACE WITH DYNAMIC MAPPING FROM WRAPPER METADATA IF POSSIBLE
        param_mapping = {
            "DecoratedText": {"text": "text", "description": "text"},
            "TextParagraph": {"text": "text", "description": "text"},
            "TextInput": {"name": "name", "label": "label"},
            "DateTimePicker": {"name": "name", "label": "label"},
            "SelectionInput": {"name": "name", "label": "label"},
            "Image": {"image_url": "image_url"},
            "Button": {"text": "text", "url": "url"},
        }

        comp_params = {}
        mappings = param_mapping.get(comp_name, {})

        for param_key, comp_key in mappings.items():
            if param_key in self.params:
                comp_params[comp_key] = self.params[param_key]

        return comp_params

    def render(self, include_header: bool = True) -> Dict[str, Any]:
        """
        Render the pattern to Google Chat card JSON.

        Args:
            include_header: Whether to include card header if title is set

        Returns:
            Card dict in Google Chat format
        """
        widgets = []
        text_consumed = False
        buttons_consumed = False
        image_consumed = False

        for comp_name in self.component_paths:
            if comp_name in ("Section",):
                continue

            comp_class = self._component_classes.get(comp_name)

            if comp_class:
                # Try to use wrapper's create_card_component + render
                comp_params = self._get_params_for_component(comp_name)
                instance = self.wrapper.create_card_component(comp_class, comp_params)

                if instance and hasattr(instance, 'render'):
                    widget = instance.render()
                    if widget:
                        widgets.append(widget)
                        # Track consumption
                        # TODO REPLACE WITH DYNAMIC MAPPING FROM WRAPPER METADATA IF POSSIBLE

                        if comp_name in ("DecoratedText", "TextParagraph"):
                            text_consumed = True
                        elif comp_name == "ButtonList":
                            buttons_consumed = True
                        elif comp_name == "Image":
                            image_consumed = True
                    continue

            # Fallback: manual widget construction for components that failed
            widget = self._build_fallback_widget(
                comp_name, text_consumed, buttons_consumed, image_consumed
            )
            if widget:
                widgets.append(widget)
                # TODO REPLACE WITH DYNAMIC MAPPING FROM WRAPPER METADATA IF POSSIBLE
                if comp_name in ("DecoratedText", "TextParagraph"):
                    text_consumed = True
                elif comp_name == "ButtonList":
                    buttons_consumed = True
                elif comp_name == "Image":
                    image_consumed = True

        # Build card structure
        card = {"sections": [{"widgets": widgets}]} if widgets else {"sections": []}

        # Add header if requested and title exists
        if include_header and self.params.get("title"):
            card["header"] = {"title": self.params["title"]}
            if self.params.get("subtitle"):
                card["header"]["subtitle"] = self.params["subtitle"]

        return card

    def _build_fallback_widget(
        self, comp_name: str, text_consumed: bool, buttons_consumed: bool, image_consumed: bool
    ) -> Optional[Dict]:
        """Build widget manually when component class rendering fails."""
        if comp_name in ("DecoratedText",) and not text_consumed:
            text = self.params.get("text") or self.params.get("description", "")
            if text:
                return {"decoratedText": {"text": text, "wrapText": True}}

        elif comp_name in ("TextParagraph",) and not text_consumed:
            text = self.params.get("text") or self.params.get("description", "")
            if text:
                return {"textParagraph": {"text": text}}

        elif comp_name == "ButtonList" and not buttons_consumed:
            buttons = self.params.get("buttons", [])
            if buttons:
                btn_list = []
                for btn in buttons:
                    if isinstance(btn, dict):
                        btn_obj = {"text": btn.get("text", "Button")}
                        if btn.get("url"):
                            btn_obj["onClick"] = {"openLink": {"url": btn["url"]}}
                        btn_list.append(btn_obj)
                if btn_list:
                    return {"buttonList": {"buttons": btn_list}}

        elif comp_name == "Image" and not image_consumed:
            image_url = self.params.get("image_url")
            if image_url:
                return {"image": {"imageUrl": image_url}}

        elif comp_name == "Divider":
            return {"divider": {}}

        return None

    @classmethod
    def from_pattern(cls, pattern: Dict[str, Any], wrapper) -> "PreparedPattern":
        """
        Create a PreparedPattern from a pattern dict.

        Args:
            pattern: Dict with 'component_paths' and optionally 'instance_params'
            wrapper: ModuleWrapper instance

        Returns:
            PreparedPattern ready for param setting and rendering
        """
        component_paths = pattern.get("component_paths", [])
        instance_params = pattern.get("instance_params", {})

        prepared = cls(component_paths, wrapper)
        if instance_params:
            prepared.set_params(**instance_params)

        return prepared

    @classmethod
    def from_dsl(cls, dsl_string: str, wrapper) -> "PreparedPattern":
        """
        Create a PreparedPattern from DSL notation.

        Args:
            dsl_string: DSL like "§[δ×3, Ƀ[ᵬ×2]]"
            wrapper: ModuleWrapper instance

        Returns:
            PreparedPattern ready for param setting and rendering
        """
        from gchat.card_framework_wrapper import parse_dsl

        result = parse_dsl(dsl_string)
        if not result.is_valid:
            logger.warning(f"Invalid DSL: {result.issues}")
            return cls(["Section", "TextParagraph"], wrapper)

        return cls(result.component_paths, wrapper)


def prepare_pattern(
    pattern: Dict[str, Any],
    wrapper=None,
) -> PreparedPattern:
    """
    Convenience function to create a PreparedPattern.

    Args:
        pattern: Dict with 'component_paths' and optionally 'instance_params'
        wrapper: ModuleWrapper instance (uses singleton if not provided)

    Returns:
        PreparedPattern ready for param setting and rendering

    Example:
        from gchat.smart_card_builder import prepare_pattern

        pattern = {"component_paths": ["Section", "DecoratedText", "ButtonList"]}
        card = (
            prepare_pattern(pattern)
            .set_params(text="Hello World", buttons=[{"text": "Click"}])
            .render()
        )
    """
    if wrapper is None:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        wrapper = get_card_framework_wrapper()

    return PreparedPattern.from_pattern(pattern, wrapper)


def prepare_pattern_from_dsl(
    dsl_string: str,
    wrapper=None,
) -> PreparedPattern:
    """
    Convenience function to create a PreparedPattern from DSL.

    Args:
        dsl_string: DSL notation like "§[δ×3, Ƀ[ᵬ×2]]"
        wrapper: ModuleWrapper instance (uses singleton if not provided)

    Returns:
        PreparedPattern ready for param setting and rendering

    Example:
        from gchat.smart_card_builder import prepare_pattern_from_dsl

        card = (
            prepare_pattern_from_dsl("§[δ, Ƀ[ᵬ×2]]")
            .set_params(text="Status: OK", buttons=[{"text": "Refresh"}, {"text": "Close"}])
            .render()
        )
    """
    if wrapper is None:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        wrapper = get_card_framework_wrapper()

    return PreparedPattern.from_dsl(dsl_string, wrapper)


# =============================================================================
# FEEDBACK CONTENT POOLS
# =============================================================================

# Feedback prompts - use {keyword} placeholder for styled keyword insertion
CONTENT_FEEDBACK_PROMPTS = [
    ("Was the {keyword} correct?", "content"),
    ("Did the {keyword} look right?", "data"),
    ("Were the {keyword} accurate?", "values"),
    ("Was the {keyword} helpful?", "information"),
    ("Were the {keyword} correct?", "details"),
]

FORM_FEEDBACK_PROMPTS = [
    ("Was the {keyword} correct?", "layout"),
    ("Did the {keyword} look good?", "structure"),
    ("Was the {keyword} appropriate?", "formatting"),
    ("Did the {keyword} work well?", "arrangement"),
    ("Was the {keyword} suitable?", "design"),
]

# Text styling options for feedback keywords (rendered as HTML)
# These mirror the Jinja filters: success_text, warning_text, muted_text, color
FEEDBACK_TEXT_STYLES = [
    "bold",           # <b>keyword</b> (classic)
    "success",        # <font color="#34a853">keyword</font> (green)
    "warning",        # <font color="#fbbc05">keyword</font> (yellow)
    "info",           # <font color="#4285f4">keyword</font> (blue)
    "muted",          # <font color="#9e9e9e">keyword</font> (gray)
    "bold_success",   # <b><font color="#34a853">keyword</font></b>
    "bold_info",      # <b><font color="#4285f4">keyword</font></b>
]

# Color mappings (matching SEMANTIC_COLORS from styling_filters.py)
FEEDBACK_COLORS = {
    "success": "#34a853",
    "warning": "#fbbc05",
    "info": "#4285f4",
    "muted": "#9e9e9e",
    "error": "#ea4335",
}

POSITIVE_LABELS = ["👍 Good", "👍 Yes", "👍 Correct", "✅ Looks good", "👍 Accurate"]
NEGATIVE_LABELS = ["👎 Bad", "👎 No", "👎 Wrong", "❌ Needs work", "👎 Not quite"]

# =============================================================================
# MATERIAL ICONS FOR FEEDBACK (using materialIcon, not knownIcon)
# =============================================================================
# These use the full Material Design icon set (2,209 icons) via wrapper's Icon.MaterialIcon
# Format: {"materialIcon": {"name": "icon_name"}} instead of {"knownIcon": "ICON"}

# Positive feedback icons - expressive approval indicators
POSITIVE_MATERIAL_ICONS = [
    "thumb_up",
    "check_circle",
    "favorite",
    "star",
    "verified",
    "sentiment_satisfied",
    "mood",
    "celebration",
    "done_all",
    "recommend",
]

# Negative feedback icons - constructive criticism indicators
NEGATIVE_MATERIAL_ICONS = [
    "thumb_down",
    "cancel",
    "error",
    "report",
    "sentiment_dissatisfied",
    "mood_bad",
    "do_not_disturb",
    "feedback",
    "rate_review",
    "edit_note",
]

# Neutral/general feedback icons - for decorated text prompts
FEEDBACK_MATERIAL_ICONS = [
    "rate_review",
    "feedback",
    "comment",
    "chat",
    "forum",
    "question_answer",
    "help",
    "lightbulb",
    "psychology",
    "tips_and_updates",
]

# Legacy knownIcon values (kept for backwards compatibility / fallback)
# POSITIVE_ICONS/NEGATIVE_ICONS: Verified working in buttons
POSITIVE_ICONS = ["STAR", "CONFIRMATION_NUMBER", "TICKET"]
NEGATIVE_ICONS = ["BOOKMARK", "DESCRIPTION", "EMAIL"]
# FEEDBACK_ICONS: Verified working in BOTH buttons AND decoratedText.startIcon
FEEDBACK_ICONS = ["STAR", "BOOKMARK", "DESCRIPTION", "EMAIL"]

# Validated URL images (tested and confirmed working in Google Chat)
POSITIVE_IMAGE_URLS = [
    "https://www.gstatic.com/images/icons/material/system/2x/check_circle_black_24dp.png",  # Checkmark
    "https://ui-avatars.com/api/?name=Y&background=4caf50&color=fff&size=24&bold=true",  # Green Y
    "https://placehold.co/24x24/4caf50/4caf50.png",  # Green square
]
NEGATIVE_IMAGE_URLS = [
    "https://www.gstatic.com/images/icons/material/system/2x/cancel_black_24dp.png",  # X mark
    "https://ui-avatars.com/api/?name=N&background=f44336&color=fff&size=24&bold=true",  # Red N
    "https://placehold.co/24x24/f44336/f44336.png",  # Red square
]


# =============================================================================
# MODULAR FEEDBACK COMPONENT REGISTRY
# =============================================================================
# Components are categorized by capability:
# - TEXT_COMPONENTS: Can display feedback prompt text
# - CLICKABLE_COMPONENTS: Can carry onClick callback URL
# - DUAL_COMPONENTS: Can do both (text + click in same widget)
# - LAYOUT_WRAPPERS: How to arrange the assembled widgets

TEXT_COMPONENTS = [
    "text_paragraph",  # Simple text block
    "decorated_text",  # Text with optional icon, top/bottom labels
    "decorated_text_icon",  # DecoratedText with startIcon
    "selection_label",  # SelectionInput used for its label display
    "chip_text",  # Chip used for text display
]

CLICKABLE_COMPONENTS = [
    "button_list",  # Standard button row (2 buttons: pos + neg)
    "chip_list",  # Clickable chips (2 chips: pos + neg)
    "icon_buttons",  # Buttons with random knownIcon (pos/neg themed)
    "icon_buttons_alt",  # Buttons with STAR/BOOKMARK knownIcon
    "url_image_buttons",  # Buttons with URL images (check/X, Y/N, colors)
]

# Components that can do both text AND click in one widget
DUAL_COMPONENTS = [
    "decorated_text_with_button",  # Text + inline button + separate neg button
    "decorated_inline_only",  # Text + single inline button (most compact - 1 widget)
    "chip_dual",  # Chip with text and onClick
    "columns_inline",  # Text left, buttons right in one widget
]

LAYOUT_WRAPPERS = [
    "sequential",  # Widgets one after another
    "with_divider",  # Divider between content and form feedback
    "columns_layout",  # Side-by-side columns
    "compact",  # Minimal spacing
]

# Button type styles (Google Chat Card v2)
# https://developers.google.com/workspace/chat/api/reference/rest/v1/cards#type_1
BUTTON_TYPES = [
    "OUTLINED",      # Medium-emphasis, default styling
    "FILLED",        # High-emphasis, solid color container
    "FILLED_TONAL",  # Middle ground between filled and outlined
    "BORDERLESS",    # Low-emphasis, no visible container (most compact)
]

# Section styles for feedback area
SECTION_STYLES = [
    "normal",           # Standard section (current behavior)
    "collapsible_0",    # Collapsible, 0 widgets visible by default (most compact)
    "collapsible_1",    # Collapsible, 1 widget visible by default
]


# =============================================================================
# COMPONENT PATHS REGISTRY
# =============================================================================

COMPONENT_PATHS = {
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
}

# Patterns that indicate a card ALREADY has feedback buttons
# (more specific to avoid false positives from titles like "Feedback Report")
FEEDBACK_DETECTION_PATTERNS = [
    "feedback_type=content",
    "feedback_type=form",
    "feedback=positive",
    "feedback=negative",
    "👍 Good",
    "👍 Yes",
    "👎 Bad",
    "👎 No",
]


class SmartCardBuilderV2:
    """
    Streamlined card builder using DSL + Qdrant embeddings.

    Flow:
    1. Parse Structure DSL from description (e.g., §[δ×3, Ƀ[ᵬ×2]])
    2. Parse Content DSL for styled content (e.g., δ 'text' success bold)
    3. Build card from parsed structure with styled content
    4. Add feedback section for learning loop
    """

    def __init__(self):
        """Initialize the builder."""
        self._wrapper = None
        self._qdrant_client = None
        self._embedder = None
        self._jinja_env = None
        self._jinja_applied = False  # Track if Jinja processing was applied

        # Performance optimization: LRU cache for Qdrant pattern queries
        # Cache entries expire after 5 minutes to balance freshness vs performance
        self._pattern_cache: Dict[str, Dict[str, Any]] = {}
        self._pattern_cache_timestamps: Dict[str, float] = {}
        self._pattern_cache_ttl = 300  # 5 minutes
        self._pattern_cache_max_size = 100

    # =========================================================================
    # INFRASTRUCTURE
    # =========================================================================

    def _get_wrapper(self):
        """Get or create the ModuleWrapper singleton."""
        if self._wrapper is None:
            try:
                from gchat.card_framework_wrapper import get_card_framework_wrapper

                self._wrapper = get_card_framework_wrapper()
            except Exception as e:
                logger.warning(f"Could not get ModuleWrapper: {e}")
        return self._wrapper

    def _build_material_icon(self, icon_name: str, fill: bool = None, weight: int = None) -> Dict[str, Any]:
        """Build a materialIcon dict using the wrapper's Icon.MaterialIcon class.

        This uses the card_framework wrapper components to ensure consistency
        and proper rendering of Material Design icons (2,209+ available icons).

        Args:
            icon_name: Material icon name (e.g., "thumb_up", "check_circle")
            fill: Optional fill style (True for filled, False for outlined)
            weight: Optional weight (100-700, default varies by icon)

        Returns:
            Dict in format: {"materialIcon": {"name": "icon_name", ...}}
        """
        try:
            from card_framework.v2.widgets.icon import Icon

            # Build MaterialIcon using wrapper component
            mi = Icon.MaterialIcon(name=icon_name, fill=fill, weight=weight)
            icon = Icon(material_icon=mi)

            # Use to_dict() for proper rendering
            icon_dict = icon.to_dict()

            # Convert to camelCase for Google Chat API
            if "material_icon" in icon_dict:
                icon_dict["materialIcon"] = icon_dict.pop("material_icon")

            return icon_dict

        except Exception as e:
            logger.debug(f"Wrapper MaterialIcon failed, using fallback: {e}")
            # Fallback to manual dict construction
            result = {"materialIcon": {"name": icon_name}}
            if fill is not None:
                result["materialIcon"]["fill"] = fill
            if weight is not None:
                result["materialIcon"]["weight"] = weight
            return result

    def _build_start_icon(self, icon_name: str) -> Dict[str, Any]:
        """Build a startIcon dict for decoratedText using materialIcon.

        Args:
            icon_name: Material icon name (e.g., "feedback", "rate_review")

        Returns:
            Dict in format: {"materialIcon": {"name": "icon_name"}}
        """
        return self._build_material_icon(icon_name)

    def _get_qdrant_client(self):
        """Get or create the Qdrant client."""
        if self._qdrant_client is None:
            try:
                from config.qdrant_client import get_qdrant_client

                self._qdrant_client = get_qdrant_client()
            except Exception as e:
                logger.warning(f"Could not get Qdrant client: {e}")
        return self._qdrant_client

    def _get_cache_key(self, description: str, card_params: Optional[Dict[str, Any]] = None) -> str:
        """Generate a cache key from description and params."""
        import hashlib
        params_str = str(sorted(card_params.items())) if card_params else ""
        key_str = f"{description}:{params_str}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cached_pattern(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get a cached pattern if valid (not expired)."""
        import time
        if cache_key in self._pattern_cache:
            timestamp = self._pattern_cache_timestamps.get(cache_key, 0)
            if time.time() - timestamp < self._pattern_cache_ttl:
                logger.debug(f"⚡ Cache hit for pattern query: {cache_key[:8]}...")
                return self._pattern_cache[cache_key]
            else:
                # Expired, remove from cache
                del self._pattern_cache[cache_key]
                del self._pattern_cache_timestamps[cache_key]
        return None

    def _cache_pattern(self, cache_key: str, pattern: Optional[Dict[str, Any]]) -> None:
        """Cache a pattern result with TTL."""
        import time
        # Evict oldest entries if cache is full
        if len(self._pattern_cache) >= self._pattern_cache_max_size:
            oldest_key = min(self._pattern_cache_timestamps, key=self._pattern_cache_timestamps.get)
            del self._pattern_cache[oldest_key]
            del self._pattern_cache_timestamps[oldest_key]

        self._pattern_cache[cache_key] = pattern
        self._pattern_cache_timestamps[cache_key] = time.time()

    def _get_dsl_parser(self):
        """Get the DSL parser from card_framework_wrapper."""
        try:
            from gchat.card_framework_wrapper import get_dsl_parser

            return get_dsl_parser()
        except Exception as e:
            logger.warning(f"Could not get DSL parser: {e}")
            return None

    def _get_jinja_env(self):
        """Get or create the Jinja2 environment with styling filters."""
        if self._jinja_env is None:
            try:
                manager = JinjaEnvironmentManager()
                self._jinja_env = manager.setup_jinja2_environment()
                if self._jinja_env:
                    # Register all styling filters
                    register_all_filters(self._jinja_env)
                    logger.debug("🎨 Jinja2 environment initialized with styling filters")
            except Exception as e:
                logger.warning(f"Could not initialize Jinja2 environment: {e}")
        return self._jinja_env

    def _process_text_with_jinja(self, text: str) -> str:
        """
        Process text through Jinja2 environment for styling.

        Handles both explicit Jinja syntax ({{ 'text' | filter }}) and
        raw HTML that needs to pass through unchanged.

        Args:
            text: Text content that may contain Jinja expressions or HTML

        Returns:
            Processed text with Jinja expressions rendered
        """
        if not text:
            return text

        jinja_env = self._get_jinja_env()
        if not jinja_env:
            return text

        try:
            # Create template from the text string
            template = jinja_env.from_string(text)
            # Render with empty context (filters work without context)
            result = template.render()
            # Only mark as applied if the text actually contained Jinja expressions
            # that were processed (i.e., the output differs from input)
            if result != text:
                self._jinja_applied = True
                logger.debug(f"🎨 Jinja template processed: '{text[:50]}...' -> '{result[:50]}...'")
            return result
        except Exception as e:
            logger.debug(f"Jinja2 processing skipped: {e}")
            return text  # Return original on error

    # =========================================================================
    # QDRANT PATTERN LOOKUP
    # =========================================================================

    def _extract_paths_from_pattern(self, pattern: Dict[str, Any]) -> List[str]:
        """
        Extract component paths from a Qdrant pattern result.

        Checks multiple fields in order of preference:
        1. component_paths - direct field
        2. parent_paths - alternate field name used in storage
        3. relationship_text - parse from DSL notation like "§[δ, Ƀ] | Section DecoratedText ButtonList"

        Args:
            pattern: Pattern dict from Qdrant query result

        Returns:
            List of component names (e.g., ["Section", "DecoratedText", "ButtonList"])
        """
        # Try component_paths first
        paths = pattern.get("component_paths", [])
        if paths:
            return paths

        # Try parent_paths (alternate storage field)
        paths = pattern.get("parent_paths", [])
        if paths:
            # Extract just the class name from full paths like "card_framework.v2.widgets.DecoratedText"
            return [p.split(".")[-1] if "." in p else p for p in paths]

        # Parse from relationship_text as fallback
        # Format: "§[δ, Ƀ] | Section DecoratedText ButtonList :: description"
        rel_text = pattern.get("relationship_text", "")
        if rel_text and "|" in rel_text:
            try:
                # Split on | and take the component names part
                parts = rel_text.split("|")
                if len(parts) >= 2:
                    # Take the part after the first |
                    # Handle both "| names" and "| names :: desc" formats
                    names_part = parts[1].split("::")[0].strip()
                    # Extract component names (words that look like class names)
                    # Filter out counts like "×3" and DSL symbols
                    import re
                    names = re.findall(r"\b([A-Z][a-zA-Z]+)\b", names_part)
                    if names:
                        logger.debug(f"Extracted paths from relationship_text: {names}")
                        return names
            except Exception as e:
                logger.debug(f"Failed to parse relationship_text: {e}")

        return []

    def _query_wrapper_patterns(
        self,
        description: str,
        card_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Query patterns using wrapper's SearchMixin methods (preferred).

        Uses DSL-aware search when DSL symbols are detected in the description,
        otherwise falls back to hybrid V7 search with positive feedback filters.

        Args:
            description: Card description (may include DSL symbols)
            card_params: Additional params to include in search context

        Returns:
            Dict with component_paths, instance_params from best match, or None
        """
        try:
            from gchat.card_framework_wrapper import get_card_framework_wrapper

            wrapper = get_card_framework_wrapper()

            # Check for DSL in description
            extracted = wrapper.extract_dsl_from_text(description)

            if extracted.get("has_dsl"):
                # Use DSL-aware search
                logger.info(f"🔤 DSL detected: {extracted['dsl']}")
                results = wrapper.search_by_dsl(
                    text=description,
                    limit=5,
                    score_threshold=0.3,
                    vector_name="inputs",  # Search for patterns
                    type_filter="instance_pattern",
                )

                if results:
                    best = results[0]
                    component_paths = self._extract_paths_from_pattern(best)
                    return {
                        "component_paths": component_paths,
                        "instance_params": best.get("instance_params", {}),
                        "structure_description": best.get("structure_description", ""),
                        "score": best.get("score", 0),
                        "source": "wrapper_dsl",
                    }
            else:
                # Use hybrid V7 search with positive feedback
                class_results, content_patterns, form_patterns = wrapper.search_v7_hybrid(
                    description=description,
                    component_paths=None,
                    limit=5,
                    token_ratio=1.0,
                    content_feedback="positive",
                    form_feedback="positive",
                    include_classes=False,  # Only want patterns
                )

                # Prefer content patterns (have positive content_feedback)
                if content_patterns:
                    best = content_patterns[0]
                    component_paths = self._extract_paths_from_pattern(best)
                    return {
                        "component_paths": component_paths,
                        "instance_params": best.get("instance_params", {}),
                        "structure_description": best.get("structure_description", ""),
                        "score": best.get("score", 0),
                        "source": "wrapper_hybrid",
                    }

            return None

        except Exception as e:
            logger.debug(f"Wrapper pattern search failed: {e}")
            return None

    def _query_qdrant_patterns(
        self,
        description: str,
        card_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Query Qdrant for matching instance patterns with caching.

        First tries wrapper's SearchMixin methods (search_by_dsl, search_v7_hybrid),
        then falls back to feedback_loop.query_with_feedback() for negative demotion.
        Results are cached for 5 minutes to improve performance.

        Args:
            description: Card description (may include DSL symbols)
            card_params: Additional params to include in search context

        Returns:
            Dict with component_paths, instance_params from best match, or None
        """
        # Check cache first
        cache_key = self._get_cache_key(description, card_params)
        cached_result = self._get_cached_pattern(cache_key)
        if cached_result is not None:
            return cached_result if cached_result else None  # Handle cached None as empty dict

        # Try wrapper-based search first (DSL-aware, cleaner)
        wrapper_result = self._query_wrapper_patterns(description, card_params)
        if wrapper_result:
            logger.info(f"✅ Wrapper pattern match (source: {wrapper_result.get('source', 'unknown')})")
            self._cache_pattern(cache_key, wrapper_result)
            return wrapper_result

        # Fall back to feedback_loop (has negative demotion support)
        try:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()

            # Query using description - symbols in description will match
            # symbol-enriched embeddings in Qdrant
            # component_query searches 'components' vector, description searches 'inputs' vector
            class_results, content_patterns, form_patterns = (
                feedback_loop.query_with_feedback(
                    component_query=description,  # Use description for component search too
                    description=description,
                    limit=5,
                )
            )

            # Use best matching content pattern (has positive content_feedback)
            if content_patterns:
                best_pattern = content_patterns[0]
                logger.info(
                    f"🎯 Found Qdrant pattern: {best_pattern.get('structure_description', '')[:50]}..."
                )
                # Extract component_paths from multiple possible fields
                component_paths = self._extract_paths_from_pattern(best_pattern)
                result = {
                    "component_paths": component_paths,
                    "instance_params": best_pattern.get("instance_params", {}),
                    "structure_description": best_pattern.get(
                        "structure_description", ""
                    ),
                    "score": best_pattern.get("score", 0),
                }
                self._cache_pattern(cache_key, result)
                return result

            # If no content patterns, try class results
            if class_results:
                # Extract component paths from class results
                component_paths = [r.get("name", "") for r in class_results[:5]]
                logger.info(f"🔍 Found class components: {component_paths}")
                result = {
                    "component_paths": component_paths,
                    "instance_params": {},
                    "structure_description": f"From classes: {', '.join(component_paths)}",
                    "score": class_results[0].get("score", 0) if class_results else 0,
                }
                self._cache_pattern(cache_key, result)
                return result

            # Cache the "no result" case too (as empty dict)
            self._cache_pattern(cache_key, {})
            return None
        except Exception as e:
            logger.warning(f"Qdrant pattern query failed: {e}")
            return None

    def _generate_pattern_from_wrapper(
        self,
        description: str,
        card_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a valid instance pattern using ModuleWrapper relationships.

        Similar to how feedback section and smoke_test_generator work -
        use ModuleWrapper's component hierarchy to create valid structures.

        Args:
            description: Original card description
            card_params: Parameters to determine component structure

        Returns:
            Dict with component_paths and instance_params
        """
        # Determine what components to use based on params
        component_paths = ["Section"]  # Always start with Section

        if card_params:
            # Add text component if we have text content
            if card_params.get("text") or card_params.get("description"):
                component_paths.append("DecoratedText")

            # Add button list if we have buttons
            if card_params.get("buttons"):
                component_paths.append("ButtonList")
                # Add individual buttons
                for _ in card_params["buttons"]:
                    component_paths.append("Button")

            # Add image if we have image URL
            if card_params.get("image_url"):
                component_paths.append("Image")

        # Default: Section with TextParagraph if nothing specified
        if len(component_paths) == 1:
            component_paths.append("TextParagraph")

        logger.info(f"🔧 Generated pattern: {component_paths}")

        return {
            "component_paths": component_paths,
            "instance_params": card_params or {},
            "structure_description": f"Generated from: {description[:100]}",
        }

    def _build_from_pattern(
        self,
        pattern: Dict[str, Any],
        card_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Build card from Qdrant pattern.

        Similar to how _create_feedback_section() builds widgets -
        we construct the Google Chat JSON structure directly based on
        the component_paths from the pattern.

        Args:
            pattern: Dict with component_paths and instance_params
            card_params: Additional params (title, subtitle, text, buttons, etc.)

        Returns:
            Card dict in Google Chat format
        """
        component_paths = pattern.get("component_paths", [])
        instance_params = pattern.get("instance_params", {})

        # Merge card_params into instance_params (card_params takes precedence)
        params = {**instance_params, **(card_params or {})}

        # Build widgets based on component paths
        widgets = []
        text_consumed = False
        buttons_consumed = False
        image_consumed = False

        for comp_name in component_paths:
            if comp_name in ("DecoratedText", "decoratedText") and not text_consumed:
                text = params.get("text") or params.get("description", "")
                if text:
                    widgets.append(
                        {
                            "decoratedText": {
                                "text": self._format_text_for_chat(text),
                                "wrapText": True,
                            }
                        }
                    )
                    text_consumed = True

            elif comp_name in ("TextParagraph", "textParagraph") and not text_consumed:
                text = params.get("text") or params.get("description", "")
                if text:
                    widgets.append(
                        {"textParagraph": {"text": self._format_text_for_chat(text)}}
                    )
                    text_consumed = True

            elif comp_name in ("ButtonList", "buttonList") and not buttons_consumed:
                buttons = params.get("buttons", [])
                if buttons:
                    btn_list = []
                    for btn in buttons:
                        if isinstance(btn, dict):
                            btn_obj = {"text": btn.get("text", "Button")}
                            if btn.get("url"):
                                btn_obj["onClick"] = {"openLink": {"url": btn["url"]}}
                            btn_list.append(btn_obj)
                    if btn_list:
                        widgets.append({"buttonList": {"buttons": btn_list}})
                        buttons_consumed = True

            elif comp_name in ("Image", "image") and not image_consumed:
                image_url = params.get("image_url")
                if image_url:
                    widgets.append({"image": {"imageUrl": image_url}})
                    image_consumed = True

            elif comp_name in ("Divider", "divider"):
                widgets.append({"divider": {}})

            elif comp_name == "Section":
                # Section is a container, not a widget - skip
                pass

            elif comp_name in ("Card", "CardHeader"):
                # Card and CardHeader are top-level containers, not widgets - skip
                pass

            elif comp_name == "Button":
                # Individual buttons are handled by ButtonList - skip
                pass

            elif comp_name in ("OnClick", "OpenLink", "onClick", "openLink"):
                # OnClick/OpenLink are nested inside buttons, not standalone widgets - skip
                pass

            # Dynamic fallback: Use generic widget builder
            else:
                # Create minimal context for generic builder
                context = {"buttons": [], "content_texts": [], "_button_index": 0, "_text_index": 0}
                widget = self._build_widget_generic(comp_name, [], context)
                if widget:
                    widgets.append(widget)

        # If we have text but no text widget was added, add one now
        if not text_consumed and (params.get("text") or params.get("description")):
            text = params.get("text") or params.get("description", "")
            widgets.insert(
                0,
                {
                    "decoratedText": {
                        "text": self._format_text_for_chat(text),
                        "wrapText": True,
                    }
                },
            )

        # If we have buttons but no button widget was added, add one now
        if not buttons_consumed and params.get("buttons"):
            buttons = params["buttons"]
            btn_list = []
            for btn in buttons:
                if isinstance(btn, dict):
                    btn_obj = {"text": btn.get("text", "Button")}
                    if btn.get("url"):
                        btn_obj["onClick"] = {"openLink": {"url": btn["url"]}}
                    btn_list.append(btn_obj)
            if btn_list:
                widgets.append({"buttonList": {"buttons": btn_list}})

        # Build card structure
        if not widgets:
            return None

        card = {"sections": [{"widgets": widgets}]}

        # Add header
        title = params.get("title")
        subtitle = params.get("subtitle")
        if title:
            card["header"] = {"title": title}
            if subtitle:
                card["header"]["subtitle"] = subtitle

        return card

    def _format_text_for_chat(self, text: str) -> str:
        """
        Format text with Jinja2 processing and markdown-to-HTML conversion for Google Chat.

        Processing order:
        1. Jinja2 template processing (styling filters like success_text, color, etc.)
        2. Markdown conversion (**bold**, *italic*)
        3. Bullet point formatting

        Handles:
        - Jinja filters: {{ 'text' | success_text }}, {{ text | color('success') }}
        - Raw HTML: <font color="#hex">text</font>
        - **bold** -> <b>bold</b>
        - *italic* -> <i>italic</i>
        - Bullet points (-, •, *) at line start -> proper formatting
        """
        import re

        if not text:
            return ""

        # Step 1: Process through Jinja2 for styling filters
        result = self._process_text_with_jinja(text)

        # Step 2: Convert **bold** to <b>bold</b>
        result = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", result)

        # Step 3: Convert *italic* to <i>italic</i> (but not bullet points)
        result = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", result)

        # Step 4: Convert markdown bullet points to HTML
        # Handle lines starting with -, •, or * followed by space
        lines = result.split("\n")
        formatted_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("- ", "• ", "* ")):
                # Convert to bullet point with proper formatting
                content = stripped[2:].strip()
                formatted_lines.append(f"• {content}")
            else:
                formatted_lines.append(line)

        return "\n".join(formatted_lines)

    # =========================================================================
    # DSL EXTRACTION
    # =========================================================================

    def _extract_structure_dsl(self, description: str) -> Optional[str]:
        """
        Extract Structure DSL notation from description.

        Example: "§[δ×3, Ƀ[ᵬ×2]] Dashboard" → "§[δ×3, Ƀ[ᵬ×2]]"
        """
        if not description:
            return None

        try:
            from gchat.card_framework_wrapper import extract_dsl_from_description

            return extract_dsl_from_description(description)
        except Exception as e:
            logger.debug(f"DSL extraction failed: {e}")
            return None

    def _parse_content_dsl(self, description: str) -> Optional[Dict[str, Any]]:
        """
        Parse Content DSL from description.

        Content DSL format:
            δ 'Status: Online' success bold
            ᵬ Click Here https://example.com

        Returns dict with styled texts and buttons.
        """
        if not description:
            return None

        try:
            parser = self._get_dsl_parser()
            if not parser:
                return None

            # Extract content after Structure DSL
            structure_dsl = self._extract_structure_dsl(description)
            if structure_dsl:
                content_text = description[len(structure_dsl) :].strip()
            else:
                content_text = description.strip()

            if not content_text:
                return None

            # Find Content DSL lines (starting with symbols)
            symbols = set(parser.reverse_symbols.keys())
            lines = content_text.split("\n")

            content_dsl_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped[0] in symbols:
                    content_dsl_lines.append(line)
                elif line.startswith(("  ", "\t")) and content_dsl_lines:
                    content_dsl_lines.append(line)

            if not content_dsl_lines:
                return None

            # Parse Content DSL
            content_dsl_text = "\n".join(content_dsl_lines)
            result = parser.parse_content_dsl(content_dsl_text)

            if not result.is_valid or not result.blocks:
                return None

            logger.info(f"🎨 Content DSL: Parsed {len(result.blocks)} blocks")

            # Build structured result
            parsed = {"blocks": [], "buttons": [], "texts": []}

            for block in result.blocks:
                block_info = {
                    "symbol": block.primary.symbol,
                    "component": block.primary.component_name,
                    "content": block.full_content,
                    "styles": [m.name for m in block.primary.modifiers],
                    "url": block.primary.url,
                }
                parsed["blocks"].append(block_info)

                if block.primary.component_name == "Button":
                    parsed["buttons"].append(
                        {
                            "text": block.full_content,
                            "url": block.primary.url,
                        }
                    )
                else:
                    styled = self._apply_styles(
                        block.full_content, [m.name for m in block.primary.modifiers]
                    )
                    parsed["texts"].append(
                        {
                            "content": block.full_content,
                            "styled": styled,
                            "component": block.primary.component_name,
                        }
                    )

            return parsed

        except Exception as e:
            logger.debug(f"Content DSL parsing failed: {e}")
            return None

    def _apply_styles(self, text: str, styles: List[str]) -> str:
        """Apply Content DSL styles to text, generating Google Chat HTML."""
        result = text
        color = None
        is_bold = False
        is_italic = False
        is_strike = False

        for style in styles:
            style_lower = style.lower()

            # Check semantic colors
            if style_lower in SEMANTIC_COLORS:
                color = SEMANTIC_COLORS[style_lower]
            elif style_lower == "bold":
                is_bold = True
            elif style_lower == "italic":
                is_italic = True
            elif style_lower in ("strike", "strikethrough"):
                is_strike = True
            elif style_lower in ("success", "ok", "active"):
                color = SEMANTIC_COLORS.get("success", "#34a853")
            elif style_lower in ("error", "danger", "failed"):
                color = SEMANTIC_COLORS.get("error", "#ea4335")
            elif style_lower in ("warning", "caution", "pending"):
                color = SEMANTIC_COLORS.get("warning", "#fbbc05")
            elif style_lower in ("info", "note", "notice"):
                color = SEMANTIC_COLORS.get("info", "#4285f4")

        # Apply formatting (innermost first)
        if is_strike:
            result = f"<s>{result}</s>"
        if is_italic:
            result = f"<i>{result}</i>"
        if is_bold:
            result = f"<b>{result}</b>"
        if color:
            result = f'<font color="{color}">{result}</font>'

        return result

    # =========================================================================
    # CARD BUILDING FROM DSL
    # =========================================================================

    def _build_from_dsl(
        self,
        structure_dsl: str,
        description: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        buttons: Optional[List[Dict]] = None,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        items: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build a card from parsed DSL structure."""
        wrapper = self._get_wrapper()
        if not wrapper:
            return None

        try:
            validator = wrapper.get_structure_validator()
            parsed = validator.parse_structure(structure_dsl)
            if not parsed:
                return None

            logger.info(f"📐 Parsed DSL into {len(parsed)} component(s)")

            # Parse Content DSL for styled content
            content_dsl = self._parse_content_dsl(description)

            # Override buttons with Content DSL buttons
            if content_dsl and content_dsl.get("buttons") and not buttons:
                buttons = content_dsl["buttons"]

            # Build sections from structure
            sections = []
            text_index = 0

            content_texts = content_dsl.get("texts", []) if content_dsl else []

            # If no Content DSL texts but explicit text provided, add it to content_texts
            # This ensures card_params.text flows through the component system properly
            if not content_texts and text:
                # Process text through Jinja for styling support
                styled_text = self._format_text_for_chat(text)
                content_texts = [{"text": text, "styled": styled_text}]
                logger.info(f"📝 Using explicit text param: {text[:50]}...")

            # If items array provided, convert to content_texts for DecoratedText widgets
            # Each item can have: text, icon, top_label, bottom_label
            if items:
                for item in items:
                    item_text = item.get("text", "")
                    styled_text = self._format_text_for_chat(item_text)
                    content_entry = {"text": item_text, "styled": styled_text}
                    # Pass through additional fields for DecoratedText
                    if item.get("icon"):
                        content_entry["icon"] = item["icon"]
                    if item.get("top_label"):
                        content_entry["top_label"] = item["top_label"]
                    if item.get("bottom_label"):
                        content_entry["bottom_label"] = item["bottom_label"]
                    content_texts.append(content_entry)
                logger.info(f"📝 Added {len(items)} items to content_texts")

            # Create shared context for unified resource consumption
            # This ensures buttons, texts, etc. are consumed sequentially across all components
            context = {
                "buttons": buttons or [],
                "image_url": image_url,
                "content_texts": content_texts,
                "_button_index": 0,  # Track button consumption
                "_text_index": 0,  # Track text consumption
                "_mapping_report": InputMappingReport(),  # Track input consumption
            }

            for component in parsed:
                comp_name = component.get("name", "")
                multiplier = component.get("multiplier", 1)
                children = component.get("children", [])

                # Section is special - it contains widgets, not a widget itself
                if comp_name == "Section":
                    widgets = self._build_widgets(
                        children, buttons, image_url, content_texts, context
                    )
                    if widgets:
                        sections.append({"widgets": widgets})
                else:
                    # GENERIC: All other top-level components use _build_widget_generic
                    for _ in range(multiplier):
                        widget = self._build_widget_generic(
                            comp_name, children, context
                        )
                        if widget:
                            sections.append({"widgets": [widget]})

            if not sections:
                return None

            # Build card
            card = {"sections": sections}

            if title:
                card["header"] = {"title": title}
                if subtitle:
                    card["header"]["subtitle"] = subtitle

            return card

        except Exception as e:
            logger.warning(f"DSL card building failed: {e}")
            return None

    # =========================================================================
    # GENERIC WIDGET BUILDING (Mapping-Driven, No If/Else)
    # =========================================================================

    def _get_json_key(self, component_name: str) -> str:
        """Get camelCase JSON key from component name.

        Derived directly from component name - no hardcoded mapping needed.
        E.g., "DecoratedText" -> "decoratedText", "ButtonList" -> "buttonList"
        """
        if not component_name:
            return ""
        return component_name[0].lower() + component_name[1:]

    def _consume_from_context(
        self,
        component_name: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Consume resource from context for a component type.

        Uses CONTEXT_CONSUMERS mapping to determine what to consume.
        Returns params populated from context, or empty dict.
        Also records consumption in InputMappingReport if present in context.
        """
        if component_name not in CONTEXT_CONSUMERS:
            return {}

        context_key, index_key = CONTEXT_CONSUMERS[component_name]
        resources = context.get(context_key, [])
        current_index = context.get(index_key, 0)

        params = {}
        mapping_report = context.get("_mapping_report")

        if current_index < len(resources):
            resource = resources[current_index]
            if isinstance(resource, dict):
                # For content_texts, use 'styled' key (from Content DSL) or 'text' key (explicit)
                if context_key == "content_texts":
                    params["text"] = resource.get("styled") or resource.get("text", "")
                    # Pass through icon, top_label, bottom_label for DecoratedText
                    if resource.get("icon"):
                        params["icon"] = resource["icon"]
                    if resource.get("top_label"):
                        params["top_label"] = resource["top_label"]
                    if resource.get("bottom_label"):
                        params["bottom_label"] = resource["bottom_label"]
                    # Record the consumption in mapping report
                    if mapping_report:
                        value = str(resource.get("styled", resource.get("content", "")))
                        mapping_report.record(
                            input_type="text",
                            index=current_index,
                            value=value,
                            component=component_name,
                            field_name="text",
                        )
                # For buttons, extract button-specific fields
                elif context_key == "buttons":
                    params["text"] = resource.get("text", "Button")
                    if resource.get("url"):
                        params["url"] = resource["url"]
                    # Pass through icon (material icon name like "add_circle")
                    if resource.get("icon"):
                        params["icon"] = resource["icon"]
                    # Record the consumption in mapping report
                    if mapping_report:
                        value = str(resource.get("text", "Button"))
                        mapping_report.record(
                            input_type="button",
                            index=current_index,
                            value=value,
                            component=component_name,
                            field_name="button",
                        )
            context[index_key] = current_index + 1
        else:
            # No more resources - don't use placeholder, let caller handle missing text
            # Button still needs a label for UX
            if component_name == "Button":
                params["text"] = f"Button {current_index + 1}"
            context[index_key] = current_index + 1

        return params

    def _build_widget_generic(
        self,
        component_name: str,
        grandchildren: List[Dict],
        context: Dict[str, Any],
        explicit_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generic widget builder - handles ANY component type.

        This replaces all the if/elif component_name == "X" chains with:
        1. Dynamic JSON key derivation
        2. Context-based resource consumption
        3. Generic container/child handling
        4. Wrapper-based rendering

        Args:
            component_name: Component type (e.g., "DecoratedText", "ButtonList")
            grandchildren: Nested children from DSL
            context: Shared context for resource consumption
            explicit_params: Any explicit params to include

        Returns:
            Widget dict in Google Chat format, or None if build fails
        """
        # Skip non-widget components (containers, top-level structures)
        # Components that are NOT standalone widgets - skip them
        NON_WIDGET_COMPONENTS = {
            "Card", "CardHeader", "Section",  # Top-level containers
            "OnClick", "OpenLink", "onClick", "openLink",  # Nested inside buttons
            "Button",  # Handled by ButtonList
            "Icon", "icon",  # Nested inside decoratedText.startIcon or buttons
        }
        if component_name in NON_WIDGET_COMPONENTS:
            return None

        json_key = self._get_json_key(component_name)
        params = explicit_params.copy() if explicit_params else {}

        # 1. Empty components (just structure, no content)
        if component_name in EMPTY_COMPONENTS:
            return {json_key: {}}

        # 2. Consume from context if this component type uses resources
        consumed = self._consume_from_context(component_name, context)
        # Consumed values are defaults, explicit_params override
        for k, v in consumed.items():
            params.setdefault(k, v)

        # 3. Container components - build children recursively
        if component_name in CONTAINER_CHILDREN:
            return self._build_container_generic(
                component_name, grandchildren, context, params
            )

        # 4. Components with nested children (like DecoratedText with Button)
        # Build children first - they come back as pre-built JSON dicts
        child_params = {}
        if grandchildren:
            child_params = self._map_children_to_params(
                component_name, grandchildren, context
            )

        # 5. Form components need a name field
        if component_name in FORM_COMPONENTS:
            input_index = context.get("_input_index", 0)
            params.setdefault("name", f"{component_name.lower()}_{input_index}")
            params.setdefault("label", component_name.replace("Input", " Input"))
            context["_input_index"] = input_index + 1

        # 5.5 Pre-process DecoratedText special fields (icon -> startIcon, labels)
        # Must happen BEFORE wrapper build so wrapper gets clean params
        decorated_text_extras = {}
        if component_name == "DecoratedText":
            if params.get("icon"):
                icon_name = params.pop("icon")
                decorated_text_extras["startIcon"] = {"materialIcon": {"name": icon_name}}
            if params.get("top_label"):
                decorated_text_extras["topLabel"] = params.pop("top_label")
            if params.get("bottom_label"):
                decorated_text_extras["bottomLabel"] = params.pop("bottom_label")

        # 6. Build via wrapper for proper type handling (only if no pre-built children)
        # When there are pre-built children (JSON dicts), wrapper can't use them directly
        if not child_params:
            wrapper = self._get_wrapper()
            if wrapper:
                built = self._build_via_wrapper_generic(wrapper, component_name, params)
                if built:
                    # Merge in DecoratedText extras (icon, labels) after wrapper build
                    if decorated_text_extras:
                        built.update(decorated_text_extras)
                    return {json_key: built}

        # 7. Build widget with merged children
        # For components with nested children, merge child_params into the base params
        widget_content = {}

        # Add base params (e.g., text for DecoratedText)
        if "text" in params:
            widget_content["text"] = params["text"]
        if component_name == "DecoratedText":
            widget_content.setdefault("wrapText", True)
            # Merge in pre-processed extras (icon -> startIcon, labels)
            widget_content.update(decorated_text_extras)

        # Add any other params
        for k, v in params.items():
            if k not in widget_content:
                widget_content[k] = v

        # Merge pre-built children
        widget_content.update(child_params)

        # Handle Image special case
        if component_name == "Image":
            img_url = params.get("imageUrl") or context.get("image_url") or "https://picsum.photos/400/200"
            return {json_key: {"imageUrl": img_url}}

        return {json_key: widget_content} if widget_content else {json_key: {"text": "Item"}}

    def _build_container_generic(
        self,
        component_name: str,
        children: List[Dict],
        context: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build container components (ButtonList, Grid, etc.) generically.

        Uses CONTAINER_CHILDREN and CONTAINER_CHILD_TYPE mappings.
        """
        json_key = self._get_json_key(component_name)
        children_field = CONTAINER_CHILDREN[component_name]
        expected_child_type = CONTAINER_CHILD_TYPE.get(component_name)

        # Count expected children from DSL
        if expected_child_type and children:
            expected_count = sum(
                c.get("multiplier", 1)
                for c in children
                if c.get("name") == expected_child_type
            )
        else:
            expected_count = 1

        # Special case: Columns has nested structure
        if component_name == "Columns":
            return self._build_columns_generic(children, context)

        # Build child items
        built_children = []
        for _ in range(expected_count):
            if expected_child_type == "Button":
                # Consume button from context
                btn_params = self._consume_from_context("Button", context)
                btn_obj = {"text": btn_params.get("text", "Button")}
                if btn_params.get("url"):
                    btn_obj["onClick"] = {"openLink": {"url": btn_params["url"]}}
                # Add Material Icon if provided (e.g., "add_circle", "share")
                if btn_params.get("icon"):
                    btn_obj["icon"] = {"materialIcon": {"name": btn_params["icon"]}}
                built_children.append(btn_obj)
            elif expected_child_type == "GridItem":
                idx = len(built_children)
                built_children.append({
                    "title": f"Item {idx + 1}",
                    "image": {"imageUri": f"https://picsum.photos/200/200?{idx}"},
                })
            elif expected_child_type == "Chip":
                idx = len(built_children)
                built_children.append({"label": f"Chip {idx + 1}"})
            else:
                # Generic child
                built_children.append({"text": f"Item {len(built_children) + 1}"})

        if not built_children:
            return None

        result = {children_field: built_children}

        # Grid has additional params
        if component_name == "Grid":
            result["columnCount"] = min(3, len(built_children))

        return {json_key: result}

    def _build_columns_generic(
        self,
        children: List[Dict],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build Columns component with nested column structure."""
        column_items = []

        for child in children:
            if child.get("name") != "Column":
                continue
            col_mult = child.get("multiplier", 1)
            col_grandchildren = child.get("children", [])

            for _ in range(col_mult):
                col_widgets = []
                for gc in col_grandchildren:
                    gc_name = gc.get("name", "")
                    gc_mult = gc.get("multiplier", 1)
                    gc_children = gc.get("children", [])

                    for _ in range(gc_mult):
                        widget = self._build_widget_generic(
                            gc_name, gc_children, context
                        )
                        if widget:
                            col_widgets.append(widget)

                if col_widgets:
                    column_items.append({"widgets": col_widgets})

        if not column_items:
            # Default columns
            column_items = [
                {"widgets": [{"textParagraph": {"text": "Column 1"}}]},
                {"widgets": [{"textParagraph": {"text": "Column 2"}}]},
            ]

        return {"columns": {"columnItems": column_items}}

    def _build_via_wrapper_generic(
        self,
        wrapper,
        component_name: str,
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build any component via wrapper generically.

        Tries to instantiate the component class and render it.
        Returns the inner dict (without the json_key wrapper).
        """
        # Try common paths
        paths = [
            f"card_framework.v2.widgets.{component_name.lower()}.{component_name}",
            f"card_framework.v2.widgets.decorated_text.{component_name}",
            f"card_framework.v2.{component_name.lower()}.{component_name}",
        ]

        comp_class = None
        for path in paths:
            comp_class = wrapper.get_component_by_path(path)
            if comp_class:
                break

        if not comp_class:
            return None

        try:
            instance = wrapper.create_card_component(comp_class, params)
            if instance and hasattr(instance, "to_dict"):
                rendered = instance.to_dict()
                return self._convert_to_camel_case(rendered)
        except Exception as e:
            logger.debug(f"Generic wrapper build failed for {component_name}: {e}")

        return None

    def _build_widgets(
        self,
        children: List[Dict],
        buttons: Optional[List[Dict]],
        image_url: Optional[str],
        content_texts: List[Dict],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        """Build widgets from DSL children using GENERIC mapping-driven approach.

        This method uses _build_widget_generic for ALL component types, avoiding
        if/elif chains. Component behavior is determined by:
        - CONTEXT_CONSUMERS: Which resources each component consumes
        - CONTAINER_CHILDREN: How container components store children
        - FORM_COMPONENTS: Components needing name fields
        - EMPTY_COMPONENTS: Structure-only components

        Supports nested DSL notation like δ[ᵬ] (DecoratedText with Button) via
        _map_children_to_params which uses wrapper relationship metadata.

        Args:
            children: Parsed child components from DSL
            buttons: List of button dicts from card_params
            image_url: Image URL for image widgets
            content_texts: Parsed content texts with styling
            context: Shared context for unified resource consumption

        Note: Resource consumption is tracked in context (_button_index, _text_index)
        so resources used in nested DSL (e.g., δ[ᵬ]) aren't reused elsewhere.
        """
        widgets = []

        # Use shared context or create local one
        if context is None:
            context = {
                "buttons": buttons or [],
                "image_url": image_url,
                "content_texts": content_texts,
                "_button_index": 0,
                "_text_index": 0,
                "_input_index": 0,
            }

        for child in children:
            child_name = child.get("name", "")
            multiplier = child.get("multiplier", 1)
            grandchildren = child.get("children", [])

            for _ in range(multiplier):
                # GENERIC: Build any widget using mapping-driven approach
                widget = self._build_widget_generic(
                    child_name, grandchildren, context
                )
                if widget:
                    widgets.append(widget)

        return widgets

    def _get_default_params(self, component_name: str, index: int = 0) -> Dict:
        """Get minimal default params for a component type."""
        defaults = {
            # Text display - no defaults, must be provided by caller
            "TextParagraph": {},
            "DecoratedText": {},
            # Form inputs (require 'name' field)
            "TextInput": {"name": f"text_input_{index}", "label": "Text Input"},
            "DateTimePicker": {"name": f"datetime_{index}", "label": "Select Date/Time"},
            "SelectionInput": {"name": f"selection_{index}", "label": "Select Option", "type": "DROPDOWN"},
            # Layout
            "Divider": {},
            "Image": {"image_url": f"https://picsum.photos/400/200?{index}"},
            "Grid": {"column_count": 2},
            "GridItem": {"title": f"Grid Item {index + 1}"},
            # Buttons and chips
            "Button": {"text": f"Button {index + 1}"},
            "ButtonList": {},
            "Chip": {"label": f"Chip {index + 1}"},
            "ChipList": {},
            # Columns
            "Columns": {},
            "Column": {},
        }
        return defaults.get(component_name, {})

    # =========================================================================
    # GENERIC CHILD MAPPING (Nested DSL Support)
    # =========================================================================
    # These methods use ModuleWrapper relationship metadata to generically
    # map DSL children to parent component parameters.

    # Mapping from Python field names to Google Chat JSON field names
    # (handles cases where the dataclass field name differs from API field name)
    FIELD_NAME_TO_JSON = {
        # DecoratedText children
        ("DecoratedText", "icon"): "startIcon",  # Python uses 'icon', API uses 'startIcon'
        # Add more mappings as needed
    }

    def _map_children_to_params(
        self,
        parent_name: str,
        children: List[Dict],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Map parsed DSL children to parent component parameters.

        Uses module_wrapper relationships to determine which field each
        child component should be assigned to in the parent.

        Args:
            parent_name: Parent component name (e.g., "DecoratedText")
            children: List of parsed child dicts from DSL (e.g., [{"name": "Button", ...}])
            context: Rendering context (buttons, content_texts, etc.)

        Returns:
            Dict of {field_name: built_child_widget} to merge into parent params

        Example:
            children = [{"name": "Button", "params": {}}, {"name": "Icon", "params": {}}]
            result = _map_children_to_params("DecoratedText", children, context)
            # Returns: {"button": {...button widget...}, "icon": {...icon widget...}}
        """
        wrapper = self._get_wrapper()
        if not wrapper:
            return {}

        params = {}
        for child in children:
            child_name = child.get("name", "")
            child_params = child.get("params", {})
            child_grandchildren = child.get("children", [])

            # Use wrapper relationship lookup to find the correct field
            field_info = wrapper.get_field_for_child(parent_name, child_name)
            if not field_info:
                logger.debug(
                    f"No field mapping for {parent_name} -> {child_name}, skipping"
                )
                continue

            field_name = field_info["field_name"]

            # Convert Python field name to Google Chat JSON field name if needed
            json_field_name = self.FIELD_NAME_TO_JSON.get(
                (parent_name, field_name), field_name
            )

            # Resolve child params from context and pattern lookup
            resolved_params = self._resolve_child_params(
                child_name, child_params, context
            )

            # Build the child widget
            child_widget = self._build_child_widget(
                child_name, resolved_params, child_grandchildren, context
            )

            if child_widget is not None:
                params[json_field_name] = child_widget
                logger.debug(
                    f"Mapped {child_name} to {parent_name}.{json_field_name}"
                )

        return params

    def _resolve_child_params(
        self,
        child_name: str,
        explicit_params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve parameters for a child component using MAPPING-DRIVEN approach.

        Uses CONTEXT_CONSUMERS mapping and component defaults mapping.
        No if/elif chains for specific component types.

        Args:
            child_name: Component name (e.g., "Button", "Icon")
            explicit_params: Params explicitly provided in DSL
            context: Rendering context with buttons, texts, etc.

        Returns:
            Merged params dict ready for component building
        """
        params = {}

        # Priority order (lowest to highest):
        # 1. Defaults from _get_default_params
        # 2. Component-specific defaults
        # 3. Context-consumed values (e.g., from buttons list)
        # 4. Explicit params from DSL

        # 1. Start with defaults for this component type
        defaults = self._get_default_params(child_name)
        params.update(defaults)

        # 2. Component-specific defaults (mapping-driven, not if/elif)
        component_defaults = {
            "Icon": {"known_icon": "STAR"},
            "SwitchControl": {"name": "switch", "selected": False},
        }
        if child_name in component_defaults:
            params.update(component_defaults[child_name])

        # 3. Context-consumed values OVERRIDE defaults
        consumed = self._consume_from_context(child_name, context)
        params.update(consumed)

        # 4. Explicit params override everything
        params.update(explicit_params)

        return params

    def _convert_to_camel_case(self, data: Any) -> Any:
        """
        Convert snake_case keys to camelCase for Google Chat API.

        The wrapper renders snake_case (e.g., start_icon, on_click) but
        Google Chat API expects camelCase (e.g., startIcon, onClick).
        """
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                # Convert snake_case to camelCase
                parts = key.split("_")
                camel_key = parts[0] + "".join(word.capitalize() for word in parts[1:])
                result[camel_key] = self._convert_to_camel_case(value)
            return result
        elif isinstance(data, list):
            return [self._convert_to_camel_case(item) for item in data]
        else:
            return data

    def _build_child_widget(
        self,
        child_name: str,
        params: Dict[str, Any],
        grandchildren: List[Dict],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Build a child widget using MAPPING-DRIVEN approach (no if/elif chains).

        Uses a builder registry to dispatch to specialized builders where needed,
        falling back to generic wrapper rendering for all other components.

        Args:
            child_name: Component name (e.g., "Button", "Icon")
            params: Resolved params for this component
            grandchildren: Any nested children (for recursive structures)
            context: Rendering context

        Returns:
            Widget dict in Google Chat camelCase format, or None if build fails
        """
        _ = grandchildren, context  # Reserved for future recursive use

        wrapper = self._get_wrapper()
        if not wrapper:
            logger.warning(f"No wrapper available for building {child_name}")
            return None

        # Mapping of component names to specialized builders
        # These handle components with special requirements (enums, nested objects)
        specialized_builders = {
            "Button": self._build_button_via_wrapper,
            "Icon": self._build_icon_via_wrapper,
            "SwitchControl": self._build_switch_via_wrapper,
            "OnClick": self._build_onclick_via_wrapper,
        }

        try:
            # Use specialized builder if available, otherwise generic
            builder = specialized_builders.get(child_name)
            if builder:
                return builder(wrapper, params)
            return self._build_via_wrapper_generic(wrapper, child_name, params)

        except Exception as e:
            logger.warning(f"Failed to build {child_name} via wrapper: {e}")
            return None

    def _build_button_via_wrapper(
        self, wrapper, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build a Button using wrapper component classes."""
        # Get component classes
        Button = wrapper.get_component_by_path("card_framework.v2.widgets.button.Button")
        OnClick = wrapper.get_component_by_path("card_framework.v2.widgets.on_click.OnClick")
        OpenLink = wrapper.get_component_by_path("card_framework.v2.widgets.open_link.OpenLink")

        if not all([Button, OnClick, OpenLink]):
            logger.debug("Could not get Button/OnClick/OpenLink classes")
            return None

        # Build OnClick with OpenLink
        url = params.get("url", "https://example.com")
        open_link = OpenLink(url=url)
        on_click = OnClick(open_link=open_link)

        # Build Button
        button = Button(
            text=params.get("text", "Button"),
            on_click=on_click,
        )

        # Render and convert to camelCase
        if hasattr(button, "to_dict"):
            rendered = button.to_dict()
            return self._convert_to_camel_case(rendered)

        return None

    def _build_icon_via_wrapper(
        self, wrapper, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build an Icon using wrapper component classes."""
        Icon = wrapper.get_component_by_path("card_framework.v2.widgets.icon.Icon")

        if not Icon:
            logger.debug("Could not get Icon class")
            return None

        # Get the KnownIcon enum
        if hasattr(Icon, "KnownIcon"):
            known_icon_name = params.get("known_icon", "STAR")
            try:
                # Try to get the enum value
                known_icon_enum = getattr(Icon.KnownIcon, known_icon_name, Icon.KnownIcon.STAR)
                icon = Icon(known_icon=known_icon_enum)

                if hasattr(icon, "to_dict"):
                    rendered = icon.to_dict()
                    return self._convert_to_camel_case(rendered)
            except Exception as e:
                logger.debug(f"Failed to create Icon with enum: {e}")

        # Fallback: try with icon_url if provided
        if params.get("icon_url"):
            try:
                icon = Icon(icon_url=params["icon_url"])
                if hasattr(icon, "to_dict"):
                    rendered = icon.to_dict()
                    return self._convert_to_camel_case(rendered)
            except Exception as e:
                logger.debug(f"Failed to create Icon with URL: {e}")

        return None

    def _build_switch_via_wrapper(
        self, wrapper, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build a SwitchControl using wrapper component classes."""
        SwitchControl = wrapper.get_component_by_path(
            "card_framework.v2.widgets.switch_control.SwitchControl"
        )

        if not SwitchControl:
            logger.debug("Could not get SwitchControl class")
            return None

        try:
            switch = SwitchControl(
                name=params.get("name", "switch"),
                selected=params.get("selected", False),
            )

            if hasattr(switch, "to_dict"):
                rendered = switch.to_dict()
                return self._convert_to_camel_case(rendered)
        except Exception as e:
            logger.debug(f"Failed to create SwitchControl: {e}")

        return None

    def _build_onclick_via_wrapper(
        self, wrapper, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build an OnClick using wrapper component classes."""
        OnClick = wrapper.get_component_by_path("card_framework.v2.widgets.on_click.OnClick")
        OpenLink = wrapper.get_component_by_path("card_framework.v2.widgets.open_link.OpenLink")

        if not all([OnClick, OpenLink]):
            logger.debug("Could not get OnClick/OpenLink classes")
            return None

        try:
            if params.get("url"):
                open_link = OpenLink(url=params["url"])
                on_click = OnClick(open_link=open_link)

                if hasattr(on_click, "to_dict"):
                    rendered = on_click.to_dict()
                    return self._convert_to_camel_case(rendered)
        except Exception as e:
            logger.debug(f"Failed to create OnClick: {e}")

        return None

    # =========================================================================
    # MODULAR FEEDBACK SECTION
    # =========================================================================
    # Dynamically assembles feedback widgets from component registries.
    # Each feedback widget needs: text (prompt) + clickable (callback)
    # Components are randomly selected and assembled per card.

    def _has_feedback(self, card: Dict) -> bool:
        """Check if card already has feedback content."""
        card_str = json.dumps(card).lower()
        return any(p.lower() in card_str for p in FEEDBACK_DETECTION_PATTERNS)

    def _clean_card_metadata(self, obj: Any) -> Any:
        """Remove underscore-prefixed keys (Google Chat rejects them)."""
        if isinstance(obj, dict):
            return {
                k: self._clean_card_metadata(v)
                for k, v in obj.items()
                if not k.startswith("_")
            }
        elif isinstance(obj, list):
            return [self._clean_card_metadata(item) for item in obj]
        return obj

    def validate_content(self, card_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate that a card has actual renderable content for Google Chat.

        Args:
            card_dict: The card dictionary to validate

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

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
                        issues.append(f"Section {section_idx}, widget {widget_idx} is not a dictionary")
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
                                if isinstance(button, dict) and button.get("text", "").strip():
                                    section_has_content = True
                                    break
                    elif any(key in widget for key in [
                        "decoratedText", "decorated_text", "selectionInput", "selection_input",
                        "textInput", "text_input", "divider", "columns", "grid", "chipList"
                    ]):
                        section_has_content = True

                if section_has_content:
                    sections_have_content = True
        else:
            issues.append("Card has no sections or sections is not a list")

        has_content = header_has_content or sections_have_content

        if not has_content:
            issues.append("Card has no renderable content (empty header and empty/missing sections)")

        return has_content, issues

    def generate_dsl_notation(self, card: Dict[str, Any]) -> Optional[str]:
        """
        Generate DSL notation from a rendered card structure.

        Reverse-engineers the card structure to produce DSL notation
        that could recreate the same structure.

        Args:
            card: Card dict in Google Chat format (with sections/widgets)

        Returns:
            DSL string like "§[δ×2, Ƀ[ᵬ×2]]" or None if unable to generate
        """
        try:
            wrapper = self._get_wrapper()
            if not wrapper:
                return None

            component_to_symbol = wrapper.symbol_mapping

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
                    symbol = component_to_symbol.get(component_name, component_name[0])

                    # Handle nested structures (ButtonList with buttons, Grid with items)
                    nested_dsl = None
                    if widget_type == "buttonList":
                        buttons = widget.get("buttonList", {}).get("buttons", [])
                        btn_count = len(buttons)
                        if btn_count > 0:
                            btn_symbol = component_to_symbol.get("Button", "ᵬ")
                            nested_dsl = f"{btn_symbol}×{btn_count}" if btn_count > 1 else btn_symbol
                    elif widget_type == "grid":
                        items = widget.get("grid", {}).get("items", [])
                        item_count = len(items)
                        if item_count > 0:
                            item_symbol = component_to_symbol.get("GridItem", "ǵ")
                            nested_dsl = f"{item_symbol}×{item_count}" if item_count > 1 else item_symbol
                    elif widget_type == "chipList":
                        chips = widget.get("chipList", {}).get("chips", [])
                        chip_count = len(chips)
                        if chip_count > 0:
                            chip_symbol = component_to_symbol.get("Chip", "ꞓ")
                            nested_dsl = f"{chip_symbol}×{chip_count}" if chip_count > 1 else chip_symbol

                    # Build symbol with optional nesting
                    full_symbol = f"{symbol}[{nested_dsl}]" if nested_dsl else symbol

                    # Collapse consecutive same symbols into ×N notation
                    if full_symbol == prev_symbol:
                        count += 1
                    else:
                        if prev_symbol:
                            widget_symbols.append(f"{prev_symbol}×{count}" if count > 1 else prev_symbol)
                        prev_symbol = full_symbol
                        count = 1

                # Don't forget the last symbol
                if prev_symbol:
                    widget_symbols.append(f"{prev_symbol}×{count}" if count > 1 else prev_symbol)

                if widget_symbols:
                    section_symbol = component_to_symbol.get("Section", "§")
                    section_dsl = f"{section_symbol}[{', '.join(widget_symbols)}]"
                    section_dsls.append(section_dsl)

            if not section_dsls:
                return None

            # Single section or multiple
            return section_dsls[0] if len(section_dsls) == 1 else " + ".join(section_dsls)

        except Exception as e:
            logger.debug(f"Failed to generate DSL from card: {e}")
            return None

    def _get_feedback_base_url(self) -> str:
        """Get the feedback base URL from settings.

        Uses the server's base_url with /card-feedback endpoint.
        Falls back to placeholder only if base_url is not configured.
        """
        # Use the server's base_url (e.g., https://localhost:8002)
        base_url = getattr(_settings, "base_url", "")
        if base_url:
            return f"{base_url}/card-feedback"
        return "https://feedback.example.com"

    def _make_callback_url(
        self, card_id: str, feedback_val: str, feedback_type: str
    ) -> str:
        """Create feedback callback URL."""
        base_url = self._get_feedback_base_url()
        return f"{base_url}?card_id={card_id}&feedback={feedback_val}&feedback_type={feedback_type}"

    def _store_card_pattern_sync(
        self,
        card_id: str,
        description: str,
        title: Optional[str],
        structure_dsl: Optional[str],
        card: Dict[str, Any],
    ) -> None:
        """
        Store the main card content pattern in Qdrant (synchronous).

        This stores ONLY the main card content (pattern_type="content"),
        NOT the feedback UI section which is stored separately.
        """
        if not ENABLE_FEEDBACK_BUTTONS:
            return  # Skip if feedback is disabled

        try:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()

            # Extract component paths from card structure
            component_paths = self._extract_component_paths(card)

            # Build instance params from card content
            instance_params = {
                "title": title,
                "description": description[:500] if description else "",
                "dsl": structure_dsl,
                "component_count": len(component_paths),
            }

            # Store the CONTENT pattern (main card, not feedback UI)
            point_id = feedback_loop.store_instance_pattern(
                card_description=description,
                component_paths=component_paths,
                instance_params=instance_params,
                card_id=card_id,
                structure_description=structure_dsl or "",
                pattern_type="content",  # Tag as main content
            )

            if point_id:
                logger.debug(
                    f"📦 Stored content pattern: {card_id[:8]}... -> {point_id[:8]}..."
                )

        except Exception as e:
            # Don't fail card generation if pattern storage fails
            logger.warning(f"⚠️ Failed to store card pattern: {e}")

    def _store_card_pattern(
        self,
        card_id: str,
        description: str,
        title: Optional[str],
        structure_dsl: Optional[str],
        card: Dict[str, Any],
    ) -> None:
        """
        Store the main card content pattern in Qdrant (fire-and-forget).

        This runs the storage operation in a background thread to avoid
        blocking the card building process.

        Args:
            card_id: Unique ID for this card
            description: Original card description
            title: Card title
            structure_dsl: DSL structure if parsed
            card: The built card dict (without feedback section)
        """
        import threading

        if not ENABLE_FEEDBACK_BUTTONS:
            return  # Skip if feedback is disabled

        # Make a copy of card to avoid mutation issues
        card_copy = dict(card) if card else {}

        def store_in_background():
            self._store_card_pattern_sync(card_id, description, title, structure_dsl, card_copy)

        thread = threading.Thread(target=store_in_background, daemon=True)
        thread.start()
        logger.debug(f"🚀 Pattern storage started in background for {card_id[:8]}...")

    def _store_feedback_ui_pattern_sync(
        self,
        card_id: str,
        feedback_section: Dict[str, Any],
    ) -> None:
        """
        Store the feedback UI section pattern in Qdrant (synchronous).

        This stores the randomly generated feedback UI (pattern_type="feedback_ui"),
        allowing learning of which feedback layouts work best.
        """
        if not ENABLE_FEEDBACK_BUTTONS:
            return

        try:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()

            # Get assembly metadata
            assembly = feedback_section.get("_feedback_assembly", {})
            if not assembly:
                return  # No metadata to store

            # Build description from assembly
            description = (
                f"Feedback UI: {assembly.get('content_text', '?')} + "
                f"{assembly.get('form_text', '?')} in {assembly.get('layout', '?')} layout"
            )

            # Extract component paths from feedback widgets
            component_paths = []
            for widget in feedback_section.get("widgets", []):
                for key in widget.keys():
                    if key == "textParagraph":
                        component_paths.append("TextParagraph")
                    elif key == "decoratedText":
                        component_paths.append("DecoratedText")
                    elif key == "buttonList":
                        component_paths.append("ButtonList")
                    elif key == "chipList":
                        component_paths.append("ChipList")
                    elif key == "columns":
                        component_paths.append("Columns")
                    elif key == "divider":
                        component_paths.append("Divider")

            # Store the FEEDBACK_UI pattern
            point_id = feedback_loop.store_instance_pattern(
                card_description=description,
                component_paths=component_paths,
                instance_params=assembly,  # Store the assembly metadata
                card_id=f"{card_id}_feedback",  # Link to parent card
                structure_description=description,
                pattern_type="feedback_ui",  # Tag as feedback UI
            )

            if point_id:
                logger.debug(
                    f"📦 Stored feedback_ui pattern: {card_id[:8]}... -> {point_id[:8]}..."
                )

        except Exception as e:
            logger.warning(f"⚠️ Failed to store feedback_ui pattern: {e}")

    def _store_feedback_ui_pattern(
        self,
        card_id: str,
        feedback_section: Dict[str, Any],
    ) -> None:
        """
        Store the feedback UI section pattern in Qdrant (fire-and-forget).

        This runs the storage operation in a background thread to avoid
        blocking the card building process.

        Args:
            card_id: Unique ID for this card (links content + feedback_ui patterns)
            feedback_section: The feedback section dict with _feedback_assembly metadata
        """
        import threading

        if not ENABLE_FEEDBACK_BUTTONS:
            return

        # Make a copy to avoid mutation issues
        feedback_copy = dict(feedback_section) if feedback_section else {}

        def store_in_background():
            self._store_feedback_ui_pattern_sync(card_id, feedback_copy)

        thread = threading.Thread(target=store_in_background, daemon=True)
        thread.start()
        logger.debug(f"🚀 Feedback UI pattern storage started in background for {card_id[:8]}...")
    # OPTIMIAED MAKE DYNMAIC NOT PREDEFINED DUAL COMPONENT BUILDERS (text + click in one widget)

    def _extract_component_paths(self, card: Dict[str, Any]) -> List[str]:
        """
        Extract component paths from a card structure.

        Walks through the card dict and identifies widget types used.

        Returns:
            List of component names found (e.g., ["Section", "TextParagraph", "ButtonList"])
        """
        paths = []

        def walk(obj: Any, depth: int = 0):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    # Identify widget types
                    if key in (
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
                    ):
                        # Convert to PascalCase component name
                        component_name = "".join(
                            word.capitalize() for word in key.split("_")
                        )
                        if key == "textParagraph":
                            component_name = "TextParagraph"
                        elif key == "decoratedText":
                            component_name = "DecoratedText"
                        elif key == "buttonList":
                            component_name = "ButtonList"
                        elif key == "chipList":
                            component_name = "ChipList"
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

    # -------------------------------------------------------------------------
    # GENERIC FEEDBACK WIDGET BUILDER (Config-Driven)
    # Uses wrapper components and .render() for all feedback widgets
    # -------------------------------------------------------------------------

    def _build_feedback_widget(
        self,
        component_name: str,
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Build a feedback widget using wrapper component and .render().

        This is the generic builder for all feedback widgets. It:
        1. Gets the component class from wrapper
        2. Instantiates with params
        3. Calls .render() or .to_dict() + camelCase conversion

        Args:
            component_name: Component type (e.g., "TextParagraph", "DecoratedText")
            params: Parameters for the component

        Returns:
            Widget dict in Google Chat format
        """
        wrapper = self._get_wrapper()
        if not wrapper:
            # Fallback to simple dict if no wrapper
            json_key = self._get_json_key(component_name)
            return {json_key: params}

        try:
            # Get component class
            paths = [
                f"card_framework.v2.widgets.{component_name.lower()}.{component_name}",
                f"card_framework.v2.widgets.text_paragraph.{component_name}",
                f"card_framework.v2.widgets.decorated_text.{component_name}",
                f"card_framework.v2.widgets.chip_list.{component_name}",
            ]

            comp_class = None
            for path in paths:
                comp_class = wrapper.get_component_by_path(path)
                if comp_class:
                    break

            if comp_class:
                instance = wrapper.create_card_component(comp_class, params)
                if instance:
                    if hasattr(instance, "render"):
                        rendered = instance.render()
                        # Convert to camelCase for Google Chat API
                        return self._convert_to_camel_case(rendered)
                    elif hasattr(instance, "to_dict"):
                        json_key = self._get_json_key(component_name)
                        rendered = instance.to_dict()
                        return {json_key: self._convert_to_camel_case(rendered)}

        except Exception as e:
            logger.debug(f"Wrapper build failed for {component_name}: {e}")

        # Fallback
        json_key = self._get_json_key(component_name)
        return {json_key: params}

    # -------------------------------------------------------------------------
    # TEXT COMPONENT BUILDERS
    # Each uses _build_feedback_widget with wrapper components
    # -------------------------------------------------------------------------

    def _style_feedback_keyword(self, keyword: str, style: str) -> str:
        """
        Apply styling to a feedback keyword using HTML (like Jinja filters render).

        Args:
            keyword: The word to style (e.g., "content", "layout")
            style: Style name from FEEDBACK_TEXT_STYLES

        Returns:
            Styled HTML string
        """
        if style == "bold":
            return f"<b>{keyword}</b>"
        elif style == "success":
            return f'<font color="{FEEDBACK_COLORS["success"]}">{keyword}</font>'
        elif style == "warning":
            return f'<font color="{FEEDBACK_COLORS["warning"]}">{keyword}</font>'
        elif style == "info":
            return f'<font color="{FEEDBACK_COLORS["info"]}">{keyword}</font>'
        elif style == "muted":
            return f'<font color="{FEEDBACK_COLORS["muted"]}">{keyword}</font>'
        elif style == "bold_success":
            return f'<b><font color="{FEEDBACK_COLORS["success"]}">{keyword}</font></b>'
        elif style == "bold_info":
            return f'<b><font color="{FEEDBACK_COLORS["info"]}">{keyword}</font></b>'
        else:
            return f"<b>{keyword}</b>"  # Default to bold

    def _build_styled_feedback_prompt(self, prompt_tuple: tuple) -> str:
        """
        Build a feedback prompt with randomly styled keyword.

        Args:
            prompt_tuple: (template, keyword) from CONTENT_FEEDBACK_PROMPTS or FORM_FEEDBACK_PROMPTS

        Returns:
            Formatted prompt string with styled keyword
        """
        template, keyword = prompt_tuple
        style = random.choice(FEEDBACK_TEXT_STYLES)
        styled_keyword = self._style_feedback_keyword(keyword, style)
        return template.format(keyword=styled_keyword)

    def _text_paragraph(self, text: str, **_kwargs) -> Dict:
        """Simple text paragraph - uses wrapper TextParagraph.render()."""
        formatted_text = f"<i>{text}</i>"
        return self._build_feedback_widget("TextParagraph", {"text": formatted_text})

    def _text_decorated(self, text: str, **_kwargs) -> Dict:
        """Decorated text - uses wrapper DecoratedText.render()."""
        return self._build_feedback_widget("DecoratedText", {"text": text, "wrap_text": True})

    def _text_decorated_icon(self, text: str, **_kwargs) -> Dict:
        """Decorated text with icon - uses wrapper with MaterialIcon.

        Uses the full Material Design icon set (2,209+ icons) for visual variety
        instead of the limited knownIcon set.
        """
        # Select from Material Icons for feedback prompts
        icon_name = random.choice(FEEDBACK_MATERIAL_ICONS)
        widget = self._build_feedback_widget("DecoratedText", {"text": text, "wrap_text": True})
        # Add materialIcon using wrapper helper
        if widget and "decoratedText" in widget:
            widget["decoratedText"]["startIcon"] = self._build_start_icon(icon_name)
        return widget

    def _text_decorated_labeled(
        self, text: str, label: str = "Feedback", **_kwargs
    ) -> Dict:
        """Decorated text with label - uses wrapper DecoratedText.render()."""
        return self._build_feedback_widget(
            "DecoratedText", {"text": text, "wrap_text": True, "top_label": label}
        )

    def _text_chip(self, text: str, **_kwargs) -> Dict:
        """Chip for text display - creates chipList directly (wrapper may produce invalid output)."""
        # Create chipList directly - wrapper's ChipList.render() can produce invalid selectionItem
        # Use 'enabled: false' to make chip non-clickable (not 'disabled' which isn't valid)
        return {"chipList": {"chips": [{"label": text, "enabled": False}]}}

    # -------------------------------------------------------------------------
    # CLICKABLE COMPONENT BUILDERS (Config-Driven)
    # Uses _build_feedback_button_item for individual buttons/chips
    # Business logic (labels, URLs) separated from widget structure
    # -------------------------------------------------------------------------

    def _build_feedback_button_item(
        self,
        text: str,
        url: str,
        icon: Optional[str] = None,
        icon_url: Optional[str] = None,
        material_icon: Optional[str] = None,
        button_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a single button item with onClick using wrapper.

        Separates business logic (text, url) from widget structure.

        Args:
            text: Button text label
            url: Callback URL for onClick
            icon: Known icon name (e.g., "STAR", "BOOKMARK") - legacy
            icon_url: URL for custom icon image
            material_icon: Material icon name (e.g., "thumb_up") - preferred
            button_type: Button style (OUTLINED, FILLED, FILLED_TONAL, BORDERLESS)
        """
        wrapper = self._get_wrapper()
        if wrapper:
            try:
                # Get Button and OnClick classes
                Button = wrapper.get_component_by_path("card_framework.v2.widgets.button.Button")
                OnClick = wrapper.get_component_by_path("card_framework.v2.widgets.on_click.OnClick")
                OpenLink = wrapper.get_component_by_path("card_framework.v2.widgets.open_link.OpenLink")

                if all([Button, OnClick, OpenLink]):
                    open_link = OpenLink(url=url)
                    on_click = OnClick(open_link=open_link)
                    button = Button(text=text, on_click=on_click)

                    if hasattr(button, "to_dict"):
                        btn_dict = self._convert_to_camel_case(button.to_dict())
                        # Add icon - prefer materialIcon, fallback to knownIcon/iconUrl
                        if material_icon:
                            btn_dict["icon"] = self._build_material_icon(material_icon)
                        elif icon:
                            btn_dict["icon"] = {"knownIcon": icon}
                        elif icon_url:
                            btn_dict["icon"] = {"iconUrl": icon_url}
                        # Add button type/style
                        if button_type:
                            btn_dict["type"] = button_type
                        return btn_dict
            except Exception as e:
                logger.debug(f"Wrapper button build failed: {e}")

        # Fallback to manual dict
        btn = {"text": text, "onClick": {"openLink": {"url": url}}}
        if material_icon:
            btn["icon"] = {"materialIcon": {"name": material_icon}}
        elif icon:
            btn["icon"] = {"knownIcon": icon}
        elif icon_url:
            btn["icon"] = {"iconUrl": icon_url}
        if button_type:
            btn["type"] = button_type
        return btn

    def _build_feedback_chip_item(
        self,
        label: str,
        url: str,
    ) -> Dict[str, Any]:
        """Build a single chip item with onClick using wrapper."""
        wrapper = self._get_wrapper()
        if wrapper:
            try:
                Chip = wrapper.get_component_by_path("card_framework.v2.widgets.chip.Chip")
                OnClick = wrapper.get_component_by_path("card_framework.v2.widgets.on_click.OnClick")
                OpenLink = wrapper.get_component_by_path("card_framework.v2.widgets.open_link.OpenLink")

                if all([Chip, OnClick, OpenLink]):
                    open_link = OpenLink(url=url)
                    on_click = OnClick(open_link=open_link)
                    chip = Chip(label=label, on_click=on_click)

                    if hasattr(chip, "to_dict"):
                        return self._convert_to_camel_case(chip.to_dict())
            except Exception as e:
                logger.debug(f"Wrapper chip build failed: {e}")

        # Fallback
        return {"label": label, "onClick": {"openLink": {"url": url}}}

    def _click_button_list(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        """Standard button list - uses wrapper Button.render()."""
        pos_label = random.choice(POSITIVE_LABELS)
        neg_label = random.choice(NEGATIVE_LABELS)
        pos_url = self._make_callback_url(card_id, "positive", feedback_type)
        neg_url = self._make_callback_url(card_id, "negative", feedback_type)
        # Randomly choose button type for visual variety
        btn_type = random.choice(BUTTON_TYPES)

        buttons = [
            self._build_feedback_button_item(pos_label, pos_url, button_type=btn_type),
            self._build_feedback_button_item(neg_label, neg_url, button_type=btn_type),
        ]
        return {"buttonList": {"buttons": buttons}}

    def _click_chip_list(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        """Clickable chip list - uses wrapper Chip.render()."""
        pos_label = random.choice(POSITIVE_LABELS)
        neg_label = random.choice(NEGATIVE_LABELS)
        pos_url = self._make_callback_url(card_id, "positive", feedback_type)
        neg_url = self._make_callback_url(card_id, "negative", feedback_type)

        chips = [
            self._build_feedback_chip_item(pos_label, pos_url),
            self._build_feedback_chip_item(neg_label, neg_url),
        ]
        return {"chipList": {"chips": chips}}

    def _click_icon_buttons(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        """Button list with Material Icons - uses wrapper Button.render().

        Uses the full Material Design icon set (2,209+ icons) for visual variety.
        """
        pos_label = random.choice(POSITIVE_LABELS)
        neg_label = random.choice(NEGATIVE_LABELS)
        pos_url = self._make_callback_url(card_id, "positive", feedback_type)
        neg_url = self._make_callback_url(card_id, "negative", feedback_type)
        btn_type = random.choice(BUTTON_TYPES)

        buttons = [
            self._build_feedback_button_item(
                pos_label, pos_url,
                material_icon=random.choice(POSITIVE_MATERIAL_ICONS),
                button_type=btn_type
            ),
            self._build_feedback_button_item(
                neg_label, neg_url,
                material_icon=random.choice(NEGATIVE_MATERIAL_ICONS),
                button_type=btn_type
            ),
        ]
        return {"buttonList": {"buttons": buttons}}

    def _click_icon_buttons_alt(
        self, card_id: str, feedback_type: str, **_kwargs
    ) -> Dict:
        """Alternative button list with semantic Material Icons.

        Uses thumb_up/thumb_down for clear positive/negative feedback indication.
        """
        pos_label = random.choice(POSITIVE_LABELS)
        neg_label = random.choice(NEGATIVE_LABELS)
        pos_url = self._make_callback_url(card_id, "positive", feedback_type)
        neg_url = self._make_callback_url(card_id, "negative", feedback_type)
        btn_type = random.choice(BUTTON_TYPES)

        buttons = [
            self._build_feedback_button_item(
                pos_label, pos_url,
                material_icon="thumb_up",  # Clear positive indicator
                button_type=btn_type
            ),
            self._build_feedback_button_item(
                neg_label, neg_url,
                material_icon="thumb_down",  # Clear negative indicator
                button_type=btn_type
            ),
        ]
        return {"buttonList": {"buttons": buttons}}

    def _click_url_image_buttons(
        self, card_id: str, feedback_type: str, **_kwargs
    ) -> Dict:
        """Button list with URL-based images - uses wrapper."""
        pos_label = random.choice(POSITIVE_LABELS)
        neg_label = random.choice(NEGATIVE_LABELS)
        pos_url = self._make_callback_url(card_id, "positive", feedback_type)
        neg_url = self._make_callback_url(card_id, "negative", feedback_type)
        btn_type = random.choice(BUTTON_TYPES)

        buttons = [
            self._build_feedback_button_item(
                pos_label, pos_url, icon_url=random.choice(POSITIVE_IMAGE_URLS), button_type=btn_type
            ),
            self._build_feedback_button_item(
                neg_label, neg_url, icon_url=random.choice(NEGATIVE_IMAGE_URLS), button_type=btn_type
            ),
        ]
        return {"buttonList": {"buttons": buttons}}

    def _click_star_rating(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        """Star rating buttons using Material Icons.

        Creates a 3-star rating system (bad/ok/great) using star_outline, star_half, star icons.
        This provides more nuanced feedback than binary positive/negative.
        """
        # Rating levels with corresponding icons and labels
        ratings = [
            ("star_outline", "👎 Not great", "negative"),
            ("star_half", "😐 OK", "neutral"),
            ("star", "👍 Great!", "positive"),
        ]

        buttons = []
        for icon_name, label, rating_value in ratings:
            url = self._make_callback_url(card_id, rating_value, feedback_type)
            btn = self._build_feedback_button_item(
                label, url,
                material_icon=icon_name,
                button_type="BORDERLESS"  # Cleaner look for ratings
            )
            buttons.append(btn)

        return {"buttonList": {"buttons": buttons}}

    def _click_emoji_rating(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        """Emoji-style rating buttons using sentiment Material Icons.

        Creates a 3-point sentiment scale using Material Design sentiment icons.
        """
        # Sentiment levels with corresponding icons
        sentiments = [
            ("sentiment_dissatisfied", "😞", "negative"),
            ("sentiment_neutral", "😐", "neutral"),
            ("sentiment_satisfied", "😊", "positive"),
        ]

        buttons = []
        for icon_name, label, rating_value in sentiments:
            url = self._make_callback_url(card_id, rating_value, feedback_type)
            btn = self._build_feedback_button_item(
                label, url,
                material_icon=icon_name,
                button_type="BORDERLESS"
            )
            buttons.append(btn)

        return {"buttonList": {"buttons": buttons}}

    # -------------------------------------------------------------------------
    # DUAL COMPONENT BUILDERS (text + click in one widget)
    # -------------------------------------------------------------------------

    def _dual_decorated_with_button(
        self, text: str, card_id: str, feedback_type: str, **_kwargs
    ) -> List[Dict]:
        """Decorated text with inline button + separate negative button - uses wrapper.

        Uses Material Icons for visual variety and consistency.
        """
        pos_label = random.choice(POSITIVE_LABELS)
        neg_label = random.choice(NEGATIVE_LABELS)
        pos_url = self._make_callback_url(card_id, "positive", feedback_type)
        neg_url = self._make_callback_url(card_id, "negative", feedback_type)
        icon_name = random.choice(FEEDBACK_MATERIAL_ICONS)
        btn_type = random.choice(BUTTON_TYPES)

        # Build decorated text with inline button using wrapper
        decorated_widget = self._build_feedback_widget(
            "DecoratedText", {"text": text, "wrap_text": True}
        )
        if decorated_widget and "decoratedText" in decorated_widget:
            decorated_widget["decoratedText"]["startIcon"] = self._build_start_icon(icon_name)
            decorated_widget["decoratedText"]["button"] = self._build_feedback_button_item(
                pos_label, pos_url, button_type=btn_type
            )

        # Build separate negative button list
        button_list_widget = {"buttonList": {"buttons": [
            self._build_feedback_button_item(neg_label, neg_url, button_type=btn_type)
        ]}}

        return [decorated_widget, button_list_widget]

    def _dual_decorated_inline_only(
        self, text: str, card_id: str, feedback_type: str, **_kwargs
    ) -> List[Dict]:
        """
        Most compact: DecoratedText with single inline button (1 widget total).

        Uses DecoratedText's built-in button property for maximum compactness.
        Only shows positive button inline - negative is implied by not clicking.
        """
        pos_label = random.choice(POSITIVE_LABELS)
        pos_url = self._make_callback_url(card_id, "positive", feedback_type)
        btn_type = random.choice(BUTTON_TYPES)

        # Build decorated text with inline button
        decorated_widget = self._build_feedback_widget(
            "DecoratedText", {"text": text, "wrap_text": True}
        )
        if decorated_widget and "decoratedText" in decorated_widget:
            decorated_widget["decoratedText"]["button"] = self._build_feedback_button_item(
                pos_label, pos_url, button_type=btn_type
            )

        return [decorated_widget]

    def _dual_columns_inline(
        self, text: str, card_id: str, feedback_type: str, **_kwargs
    ) -> List[Dict]:
        """Columns with text left, buttons right (all in one widget) - uses wrapper."""
        pos_label = random.choice(POSITIVE_LABELS)
        neg_label = random.choice(NEGATIVE_LABELS)
        pos_url = self._make_callback_url(card_id, "positive", feedback_type)
        neg_url = self._make_callback_url(card_id, "negative", feedback_type)
        btn_type = random.choice(BUTTON_TYPES)

        # Build decorated text widget using wrapper
        text_widget = self._build_feedback_widget(
            "DecoratedText", {"text": text, "wrap_text": True}
        )

        # Build buttons using helper
        buttons = [
            self._build_feedback_button_item(pos_label, pos_url, button_type=btn_type),
            self._build_feedback_button_item(neg_label, neg_url, button_type=btn_type),
        ]
        button_list_widget = {"buttonList": {"buttons": buttons}}

        # Build columns structure
        return [
            {
                "columns": {
                    "columnItems": [
                        {
                            "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                            "horizontalAlignment": "START",
                            "verticalAlignment": "CENTER",
                            "widgets": [text_widget],
                        },
                        {
                            "horizontalSizeStyle": "FILL_MINIMUM_SPACE",
                            "horizontalAlignment": "END",
                            "verticalAlignment": "CENTER",
                            "widgets": [button_list_widget],
                        },
                    ]
                }
            }
        ]

    # -------------------------------------------------------------------------
    # LAYOUT WRAPPERS
    # -------------------------------------------------------------------------

    def _layout_sequential(
        self, content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
    ) -> List[Dict]:
        """Sequential layout: content then form (or reversed)."""
        return (
            content_widgets + form_widgets
            if content_first
            else form_widgets + content_widgets
        )

    def _layout_with_divider(
        self, content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
    ) -> List[Dict]:
        """Layout with divider between content and form."""
        if content_first:
            return content_widgets + [{"divider": {}}] + form_widgets
        return form_widgets + [{"divider": {}}] + content_widgets

    def _layout_compact(
        self, content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
    ) -> List[Dict]:
        """Compact layout: all text first, then all buttons."""
        # Extract text and button widgets
        texts = [
            w
            for w in content_widgets + form_widgets
            if not any(k in w for k in ["buttonList", "chipList", "grid"])
        ]
        buttons = [
            w
            for w in content_widgets + form_widgets
            if any(k in w for k in ["buttonList", "chipList", "grid"])
        ]
        return texts + buttons if content_first else buttons + texts

    # -------------------------------------------------------------------------
    # MODULAR ASSEMBLY
    # -------------------------------------------------------------------------

    def _create_feedback_section(self, card_id: str) -> Dict:
        """
        Create feedback section by randomly assembling components.

        Assembly process:
        1. Select text component type for content feedback
        2. Select text component type for form feedback
        3. Select clickable component type for content feedback
        4. Select clickable component type for form feedback
        5. Select layout wrapper
        6. Select order (content first vs form first)

        This creates massive variety for training data collection.
        """
        # Component registries with builder methods
        text_builders = {
            "text_paragraph": self._text_paragraph,
            "decorated_text": self._text_decorated,
            "decorated_text_icon": self._text_decorated_icon,
            "decorated_text_labeled": self._text_decorated_labeled,
            "chip_text": self._text_chip,
        }

        click_builders = {
            "button_list": self._click_button_list,
            "chip_list": self._click_chip_list,
            "icon_buttons": self._click_icon_buttons,
            "icon_buttons_alt": self._click_icon_buttons_alt,
            "url_image_buttons": self._click_url_image_buttons,
            "star_rating": self._click_star_rating,  # 3-star rating with Material Icons
            "emoji_rating": self._click_emoji_rating,  # Sentiment icons (😞😐😊)
        }

        dual_builders = {
            "decorated_with_button": self._dual_decorated_with_button,
            "columns_inline": self._dual_columns_inline,
            "decorated_inline_only": self._dual_decorated_inline_only,  # Most compact
        }

        layout_builders = {
            "sequential": self._layout_sequential,
            "with_divider": self._layout_with_divider,
            "compact": self._layout_compact,
        }

        # Random selections
        content_text_type = random.choice(list(text_builders.keys()))
        form_text_type = random.choice(list(text_builders.keys()))
        content_click_type = random.choice(list(click_builders.keys()))
        form_click_type = random.choice(list(click_builders.keys()))
        layout_type = random.choice(list(layout_builders.keys()))
        content_first = random.choice([True, False])
        # Always use collapsible style for feedback section (cleaner UX)
        section_style = "collapsible_0"

        # Occasionally use dual components (30% chance)
        use_dual_content = random.random() < 0.3
        use_dual_form = random.random() < 0.3

        # Build content feedback widgets with styled prompt
        content_prompt_tuple = random.choice(CONTENT_FEEDBACK_PROMPTS)
        content_prompt = self._build_styled_feedback_prompt(content_prompt_tuple)
        content_style = content_prompt_tuple[1]  # Track keyword for metadata

        if use_dual_content:
            dual_type = random.choice(list(dual_builders.keys()))
            # Dual builders now return lists
            content_widgets = dual_builders[dual_type](
                content_prompt, card_id, "content"
            )
            content_text_type = f"dual:{dual_type}"
            content_click_type = f"dual:{dual_type}"
        else:
            content_widgets = [
                text_builders[content_text_type](content_prompt, label="Content"),
                click_builders[content_click_type](card_id, "content"),
            ]

        # Build form feedback widgets with styled prompt
        form_prompt_tuple = random.choice(FORM_FEEDBACK_PROMPTS)
        form_prompt = self._build_styled_feedback_prompt(form_prompt_tuple)
        form_style = form_prompt_tuple[1]  # Track keyword for metadata

        if use_dual_form:
            dual_type = random.choice(list(dual_builders.keys()))
            # Dual builders now return lists
            form_widgets = dual_builders[dual_type](form_prompt, card_id, "form")
            form_text_type = f"dual:{dual_type}"
            form_click_type = f"dual:{dual_type}"
        else:
            form_widgets = [
                text_builders[form_text_type](form_prompt, label="Layout"),
                click_builders[form_click_type](card_id, "form"),
            ]

        # Apply layout
        widgets = layout_builders[layout_type](
            content_widgets, form_widgets, content_first
        )

        # Build metadata for training
        assembly_metadata = {
            "content_text": content_text_type,
            "content_click": content_click_type,
            "content_keyword": content_style,  # e.g., "content", "data", "values"
            "form_text": form_text_type,
            "form_click": form_click_type,
            "form_keyword": form_style,  # e.g., "layout", "structure", "design"
            "layout": layout_type,
            "content_first": content_first,
            "section_style": section_style,
        }

        logger.debug(f"🎲 Feedback assembly: {assembly_metadata}")

        # Build section with collapsible style and custom expand/collapse buttons
        section = {
            "widgets": widgets,
            "collapsible": True,
            "uncollapsibleWidgetsCount": 0,  # All hidden by default (most compact)
            "collapseControl": {
                "horizontalAlignment": "START",
                "expandButton": {
                    "text": "Share Card Feedback",
                    "icon": {
                        "materialIcon": {"name": "arrow_cool_down"},
                    },
                    "type": "BORDERLESS",
                },
                "collapseButton": {
                    "text": "Hide Feedback",
                    "icon": {
                        "materialIcon": {"name": "keyboard_double_arrow_up"},
                    },
                    "type": "BORDERLESS",
                },
            },
            "_feedback_assembly": assembly_metadata,
        }

        return section

    # =========================================================================
    # MAIN BUILD METHOD
    # =========================================================================

    def build(
        self,
        description: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        buttons: Optional[List[Dict]] = None,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        items: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Build a card from DSL description.

        Args:
            description: Card description with optional DSL notation
                Structure DSL: §[δ×3, Ƀ[ᵬ×2]] Dashboard
                Content DSL:
                    δ 'Status: Online' success bold
                    ᵬ Refresh https://example.com
            title: Card header title
            subtitle: Card header subtitle
            buttons: Explicit button list (overrides Content DSL buttons)
            image_url: Image URL for image widgets
            text: Explicit text content for text widgets (used if no Content DSL texts)
            items: Array of decorated text items [{text, icon, top_label}, ...]

        Returns:
            Card dict in Google Chat format
        """
        card_id = str(uuid.uuid4())[:8]
        card = None
        # Reset Jinja tracking for this build
        self._jinja_applied = False

        # Try DSL-based building first
        structure_dsl = self._extract_structure_dsl(description)
        if structure_dsl:
            logger.info(f"🔣 Found Structure DSL: {structure_dsl}")
            card = self._build_from_dsl(
                structure_dsl=structure_dsl,
                description=description,
                title=title,
                subtitle=subtitle,
                buttons=buttons,
                image_url=image_url,
                text=text,
                items=items,
            )

        # Fallback: Try Content DSL only (no structure)
        if not card:
            content_dsl = self._parse_content_dsl(description)
            if content_dsl and content_dsl.get("texts"):
                logger.info("🎨 Building from Content DSL only")
                sections = []

                # Create context for generic builders
                context = {
                    "content_texts": content_dsl.get("texts", []),
                    "buttons": content_dsl.get("buttons", []),
                    "_text_index": 0,
                    "_button_index": 0,
                    "_input_index": 0,
                }

                # Build text widgets using generic builder
                for _ in content_dsl["texts"]:
                    widget = self._build_widget_generic("DecoratedText", [], context)
                    if widget:
                        sections.append({"widgets": [widget]})

                # Build buttons using generic builder
                if content_dsl.get("buttons"):
                    # Create ButtonList children spec for the number of buttons
                    button_children = [
                        {"name": "Button", "multiplier": len(content_dsl["buttons"])}
                    ]
                    widget = self._build_widget_generic("ButtonList", button_children, context)
                    if widget:
                        sections.append({"widgets": [widget]})

                if sections:
                    card = {"sections": sections}
                    if title:
                        card["header"] = {"title": title}
                        if subtitle:
                            card["header"]["subtitle"] = subtitle

        # Query Qdrant for matching instance patterns
        if not card:
            card_params = {
                "title": title,
                "subtitle": subtitle,
                "buttons": buttons,
                "image_url": image_url,
                "text": description,  # Include description as text for widget content
            }
            pattern = self._query_qdrant_patterns(description, card_params)
            if pattern:
                logger.info(
                    f"🎯 Found Qdrant pattern match: {pattern.get('structure_description', '')[:50]}..."
                )
                card = self._build_from_pattern(pattern, card_params)

        # Generate pattern on-the-fly if Qdrant has no match
        if not card:
            card_params = {
                "title": title,
                "subtitle": subtitle,
                "buttons": buttons,
                "image_url": image_url,
                "text": description,  # Include description as text for widget content
            }
            logger.info("🔧 Generating pattern from ModuleWrapper relationships")
            pattern = self._generate_pattern_from_wrapper(description, card_params)
            card = self._build_from_pattern(pattern, card_params)

        # Fallback: Simple card from description (last resort)
        if not card:
            logger.info("📝 Building simple card from description (fallback)")
            # Process text through Jinja for styling support
            processed_text = self._format_text_for_chat(description)
            card = {
                "sections": [{"widgets": [{"textParagraph": {"text": processed_text}}]}]
            }
            if title:
                card["header"] = {"title": title}
                if subtitle:
                    card["header"]["subtitle"] = subtitle

        # Store metadata for debugging (will be cleaned before return)
        card["_card_id"] = card_id
        if structure_dsl:
            card["_dsl_structure"] = structure_dsl
        # Track if Jinja template processing was applied
        if self._jinja_applied:
            card["_jinja_applied"] = True
            logger.info("🎨 Jinja template styling applied to card content")

        # IMPORTANT: Store instance pattern BEFORE adding feedback section
        # This keeps the main card pattern (from tool inference) separate from
        # the randomly generated feedback UI. Only the meaningful content is stored.
        self._store_card_pattern(
            card_id=card_id,
            description=description,
            title=title,
            structure_dsl=structure_dsl,
            card=card,  # Card WITHOUT feedback section
        )

        # Add feedback section AFTER storing content pattern
        # The feedback UI is stored SEPARATELY with pattern_type="feedback_ui"
        if ENABLE_FEEDBACK_BUTTONS and card and not self._has_feedback(card):
            feedback = self._create_feedback_section(card_id)

            # Store the feedback UI pattern separately (pattern_type="feedback_ui")
            self._store_feedback_ui_pattern(card_id, feedback)

            # Add a divider before feedback to visually separate content from feedback UI
            divider_section = {"widgets": [{"divider": {}}]}
            if "sections" in card:
                card["sections"].append(divider_section)
                card["sections"].append(feedback)
            else:
                card["sections"] = [divider_section, feedback]

        # Clean metadata before returning (Google Chat rejects underscore-prefixed keys)
        return self._clean_card_metadata(card)

    # =============================================================================
    # COMPATIBILITY METHODS
    # =============================================================================

    def build_card_from_description(
        self,
        description: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        buttons: Optional[List[Dict]] = None,
        fields: Optional[List[Dict]] = None,
        submit_action: Optional[Dict] = None,
        grid: Optional[Dict] = None,
        images: Optional[List[str]] = None,
        image_titles: Optional[List[str]] = None,
        column_count: int = 2,
        sections: Optional[List[Dict]] = None,
        items: Optional[List[Dict]] = None,
        strict_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Build a card from description - v1 compatible interface.

        This method provides compatibility with the v1 SmartCardBuilder interface.
        All parameters are accepted but DSL in description takes precedence.

        For explicit sections, grids, or forms - use DSL notation:
        - Forms: τ (TextInput), ► (SelectionInput), □ (DateTimePicker)
        - Grids: ℊ[ǵ×4] (Grid with 4 GridItems)
        - Sections: §[δ×3] (Section with 3 DecoratedText)

        Args:
            description: Card description with optional DSL notation
            title: Card header title
            subtitle: Card header subtitle
            image_url: Image URL for image widgets
            text: Explicit text content (merged with description)
            buttons: Button list [{text, url}]
            fields: Form fields (use DSL instead: τ, ►, □)
            submit_action: Form submit (use DSL for forms)
            grid: Grid structure (use DSL instead: ℊ[ǵ×N])
            images: Image URLs for grid (use DSL)
            image_titles: Titles for grid images
            column_count: Grid column count
            sections: Explicit sections (bypass DSL if provided)
            strict_mode: If True, minimal processing

        Returns:
            Card dict in Google Chat format
        """
        # Handle explicit sections passthrough
        if sections:
            logger.info(f"📋 Explicit sections provided: {len(sections)} section(s)")
            card = {"sections": sections}
            if title:
                card["header"] = {"title": title}
                if subtitle:
                    card["header"]["subtitle"] = subtitle
            # Add feedback section
            card_id = str(uuid.uuid4())[:8]
            if ENABLE_FEEDBACK_BUTTONS and not self._has_feedback(card):
                feedback = self._create_feedback_section(card_id)
                card["sections"].append(feedback)
            card["_card_id"] = card_id
            return card

        # Handle grid/images params
        if grid or images:
            logger.info(f"🔲 Grid params provided - building grid card")
            # Build grid section
            grid_items = []
            if images:
                for i, img_url in enumerate(images):
                    item = {
                        "image": {"imageUri": img_url},
                        "title": (
                            image_titles[i]
                            if image_titles and i < len(image_titles)
                            else f"Item {i + 1}"
                        ),
                    }
                    grid_items.append(item)
            elif grid and grid.get("items"):
                grid_items = grid["items"]

            if grid_items:
                grid_widget = {
                    "grid": {
                        "columnCount": (
                            grid.get("columnCount", column_count)
                            if grid
                            else column_count
                        ),
                        "items": grid_items,
                    }
                }
                sections_list = [{"widgets": [grid_widget]}]
                if buttons:
                    btn_list = [
                        {
                            "text": b.get("text", "Button"),
                            **(
                                {"onClick": {"openLink": {"url": b["url"]}}}
                                if b.get("url")
                                else {}
                            ),
                        }
                        for b in buttons
                    ]
                    sections_list.append(
                        {"widgets": [{"buttonList": {"buttons": btn_list}}]}
                    )

                card = {"sections": sections_list}
                if title:
                    card["header"] = {"title": title}
                    if subtitle:
                        card["header"]["subtitle"] = subtitle

                card_id = str(uuid.uuid4())[:8]
                if ENABLE_FEEDBACK_BUTTONS:
                    feedback = self._create_feedback_section(card_id)
                    card["sections"].append(feedback)
                card["_card_id"] = card_id
                return card

        # Delegate to main build method with explicit text parameter
        # Don't merge text into description - pass it separately so it flows through component system
        return self.build(
            description=description,
            title=title,
            subtitle=subtitle,
            buttons=buttons,
            image_url=image_url,
            text=text,
            items=items,
        )

    def initialize(self):
        """Initialize the builder (v1 compatibility)."""
        # V2 initializes lazily, this is a no-op for compatibility
        pass

    def build_card_v2(
        self,
        card_description: str,
        card_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a card and wrap in cardsV2 format ready for Google Chat API.

        This is the primary entry point for card building from card_tools.py.
        It extracts parameters from card_params and delegates to build_card_from_description,
        then wraps the result in the cardsV2 format with a generated cardId.

        Args:
            card_description: Natural language description or DSL notation
            card_params: Optional dict with title, subtitle, text, buttons, image_url,
                        fields, submit_action, grid, images, image_titles, column_count, sections

        Returns:
            Dict in cardsV2 format: {"cardId": "...", "card": {...}}
            Returns empty dict if card building fails.
        """
        import time

        if card_params is None:
            card_params = {}

        # Extract all params
        title = card_params.get("title")
        subtitle = card_params.get("subtitle")
        image_url = card_params.get("image_url")
        text = card_params.get("text")
        buttons = card_params.get("buttons")
        fields = card_params.get("fields")
        submit_action = card_params.get("submit_action")
        grid = card_params.get("grid")
        images = card_params.get("images")
        image_titles = card_params.get("image_titles")
        column_count = card_params.get("column_count", 2)
        sections = card_params.get("sections")
        items = card_params.get("items")  # Array of decorated text items

        logger.info(f"🔨 SmartCardBuilder.build_card_v2: {card_description[:80]}...")
        if fields:
            logger.info(f"📝 Form card mode: {len(fields)} field(s)")
        if grid or images:
            logger.info(f"🔲 Grid params provided: {len(images) if images else 'direct grid'}")
        if sections:
            logger.info(f"📋 Explicit sections provided: {len(sections)} section(s)")

        # Build card using build_card_from_description
        card_dict = self.build_card_from_description(
            description=card_description,
            title=title,
            subtitle=subtitle,
            image_url=image_url,
            text=text,
            buttons=buttons,
            fields=fields,
            submit_action=submit_action,
            grid=grid,
            images=images,
            image_titles=image_titles,
            column_count=column_count,
            sections=sections,
            items=items,
        )

        if not card_dict:
            logger.warning("⚠️ SmartCardBuilder.build_card_v2 returned empty card")
            return {}

        # Generate cardId and wrap in cardsV2 format
        card_id = f"smart_card_{int(time.time())}_{hash(str(card_params)) % 10000}"

        return {
            "cardId": card_id,
            "card": card_dict,
        }


# =============================================================================
# DSL SUGGESTION - Suggest DSL based on card_params
# =============================================================================


def suggest_dsl_for_params(
    card_params: Dict[str, Any], symbols: Dict[str, str]
) -> Optional[str]:
    """
    Suggest DSL structure based on provided card_params.

    Args:
        card_params: Dictionary with parameters like text, buttons, image_url, etc.
        symbols: Symbol mapping from get_gchat_symbols() (e.g., {'Section': '§'})

    Returns:
        Suggested DSL string like "§[δ, Ƀ[ᵬ×2]]" or None if no suggestion
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
# SINGLETON AND CONVENIENCE FUNCTIONS
# =============================================================================

_builder: Optional[SmartCardBuilderV2] = None


def get_smart_card_builder() -> SmartCardBuilderV2:
    """Get the global SmartCardBuilderV2 instance (v1 compatible)."""
    global _builder
    if _builder is None:
        _builder = SmartCardBuilderV2()
    return _builder


def reset_builder():
    """Reset the singleton builder."""
    global _builder
    _builder = None


def build_card(
    description: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Build a card using SmartCardBuilderV2."""
    builder = get_smart_card_builder()
    return builder.build(
        description=description, title=title, subtitle=subtitle, **kwargs
    )


# Backwards compatibility alias
SmartCardBuilder = SmartCardBuilderV2
