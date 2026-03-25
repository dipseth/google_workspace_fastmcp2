"""
Smart Card Builder v2 - DSL + Embeddings Focused

A streamlined card builder that uses:
1. Structure DSL: symbol[child×N] for component hierarchy
2. Content DSL: symbol 'text' style for styled content
3. Qdrant ColBERT embeddings for semantic search
4. ModuleWrapper for component loading

NOTE: All DSL symbols are dynamically generated from ModuleWrapper.
Query wrapper.symbol_mapping for current symbol-to-component mappings.
Common examples (may vary): § (Section), δ (DecoratedText), Ƀ (ButtonList), ᵬ (Button)

This replaces the legacy NL parsing with a cleaner DSL-first approach.

Usage:
    builder = SmartCardBuilderV2()
    # Get current symbols from wrapper
    symbols = builder._get_wrapper().symbol_mapping
    card = builder.build(
        description="§[δ×3, Ƀ[ᵬ×2]] Dashboard",  # Use symbols from mapping
        title="My Card"
    )
"""

import json
from config.enhanced_logging import setup_logger
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

from dotenv import load_dotenv

from config.settings import settings as _settings
from middleware.filters import register_all_filters
from middleware.filters.styling_filters import SEMANTIC_COLORS
from middleware.template_core.jinja_environment import JinjaEnvironmentManager

# NOTE: Rendering utilities are imported lazily to avoid circular imports
# with gchat.card_builder.__init__.py. Use direct module import when needed:
#   from gchat.card_builder.rendering import get_json_key, etc.

load_dotenv()

logger = setup_logger()

# Feature flag for feedback buttons
ENABLE_FEEDBACK_BUTTONS = os.getenv("ENABLE_CARD_FEEDBACK", "true").lower() == "true"

# =============================================================================
# IMPORTS FROM card_builder PACKAGE (migrated modules)
# =============================================================================
# These were previously defined inline. Now imported from card_builder package.

# Fire-and-forget decorator
# Component params registry
# =============================================================================
# COMPONENT PATHS AND DETECTION PATTERNS - Imported from card_builder.constants
# =============================================================================
from gchat.card_builder.constants import (
    COMPONENT_PARAMS,
    COMPONENT_PATHS,
    FEEDBACK_DETECTION_PATTERNS,
)

# NOTE: COMPONENT_PARAMS is imported from card_builder.constants above
# =============================================================================
# DYNAMIC FEEDBACK BUILDER - Imported from card_builder.feedback
# =============================================================================
# The DynamicFeedbackBuilder class has been migrated to gchat.card_builder.feedback.dynamic
# Import it from there for full functionality.
# =============================================================================
# FEEDBACK CONSTANTS - Imported from card_builder.feedback package
# =============================================================================
# All feedback prompts, icons, components, and configs are now in card_builder.feedback
from gchat.card_builder.feedback import (
    BUTTON_TYPES,
    # Configs
    CLICK_CONFIGS,
    CLICKABLE_COMPONENTS,
    # Prompts
    CONTENT_FEEDBACK_PROMPTS,
    DUAL_COMPONENTS,
    FEEDBACK_COLORS,
    FEEDBACK_ICONS,
    FEEDBACK_MATERIAL_ICONS,
    FEEDBACK_TEXT_STYLES,
    FORM_FEEDBACK_PROMPTS,
    LAYOUT_CONFIGS,
    LAYOUT_WRAPPERS,
    NEGATIVE_ICONS,
    NEGATIVE_IMAGE_URLS,
    NEGATIVE_LABELS,
    NEGATIVE_MATERIAL_ICONS,
    POSITIVE_ICONS,
    POSITIVE_IMAGE_URLS,
    POSITIVE_LABELS,
    # Icons
    POSITIVE_MATERIAL_ICONS,
    SECTION_STYLES,
    # Component registries
    TEXT_COMPONENTS,
    TEXT_CONFIGS,
    DynamicFeedbackBuilder,
    get_dynamic_feedback_builder,
)

# =============================================================================
# PREPARED PATTERNS - Imported from card_builder.prepared_pattern
# =============================================================================
# InputMappingReport, PreparedPattern, prepare_pattern, prepare_pattern_from_dsl
# are now in gchat.card_builder.prepared_pattern
from gchat.card_builder.prepared_pattern import (
    InputMappingReport,
    PreparedPattern,
    prepare_pattern,
    prepare_pattern_from_dsl,
)
from gchat.card_builder.utils import fire_and_forget

class SmartCardBuilderV2:
    """
    Streamlined card builder using DSL + Qdrant embeddings.

    Flow:
    1. Parse Structure DSL from description (symbols from ModuleWrapper)
    2. Parse Content DSL for styled content (symbol 'text' style)
    3. Build card from parsed structure with styled content
    4. Add feedback section for learning loop

    NOTE: All DSL symbols are dynamically generated from ModuleWrapper.
    Query wrapper.symbol_mapping for current symbol-to-component mappings.
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

    def _build_material_icon(
        self, icon_name: str, fill: bool = None, weight: int = None
    ) -> Dict[str, Any]:
        """Build a materialIcon dict. Delegates to card_builder.rendering.build_material_icon()."""
        from gchat.card_builder.rendering import build_material_icon

        return build_material_icon(icon_name, fill, weight)

    def _build_start_icon(self, icon_name: str) -> Dict[str, Any]:
        """Build a startIcon dict. Delegates to card_builder.rendering.build_start_icon()."""
        from gchat.card_builder.rendering import build_start_icon

        return build_start_icon(icon_name)

    def _get_qdrant_client(self):
        """Get or create the Qdrant client."""
        if self._qdrant_client is None:
            try:
                from config.qdrant_client import get_qdrant_client

                self._qdrant_client = get_qdrant_client()
            except Exception as e:
                logger.warning(f"Could not get Qdrant client: {e}")
        return self._qdrant_client

    def _get_cache_key(
        self, description: str, card_params: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a cache key. Delegates to search.get_cache_key()."""
        from gchat.card_builder.search import get_cache_key

        return get_cache_key(description, card_params)

    def _get_cached_pattern(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get a cached pattern. Delegates to search.get_cached_pattern()."""
        from gchat.card_builder.search import get_cached_pattern

        return get_cached_pattern(
            cache_key, self._pattern_cache,
            self._pattern_cache_timestamps, self._pattern_cache_ttl,
        )

    def _cache_pattern(self, cache_key: str, pattern: Optional[Dict[str, Any]]) -> None:
        """Cache a pattern result. Delegates to search.cache_pattern()."""
        from gchat.card_builder.search import cache_pattern

        cache_pattern(
            cache_key, pattern, self._pattern_cache,
            self._pattern_cache_timestamps, self._pattern_cache_max_size,
        )

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
                    logger.debug(
                        "🎨 Jinja2 environment initialized with styling filters"
                    )
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
                logger.debug(
                    f"🎨 Jinja template processed: '{text[:50]}...' -> '{result[:50]}...'"
                )
            return result
        except Exception as e:
            logger.debug(f"Jinja2 processing skipped: {e}")
            return text  # Return original on error

    # =========================================================================
    # QDRANT PATTERN LOOKUP
    # =========================================================================

    def _extract_paths_from_pattern(self, pattern: Dict[str, Any]) -> List[str]:
        """Extract component paths from pattern. Delegates to card_builder.search."""
        from gchat.card_builder.search import extract_paths_from_pattern

        return extract_paths_from_pattern(pattern)

    def _query_wrapper_patterns(
        self,
        description: str,
        card_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Query patterns via wrapper. Delegates to search.query_wrapper_patterns()."""
        from gchat.card_builder.search import query_wrapper_patterns

        return query_wrapper_patterns(description, card_params)

    def _query_qdrant_patterns(
        self,
        description: str,
        card_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Query Qdrant for patterns with caching. Delegates to search.query_qdrant_patterns()."""
        from gchat.card_builder.search import query_qdrant_patterns

        return query_qdrant_patterns(
            description, card_params,
            pattern_cache=self._pattern_cache,
            pattern_cache_timestamps=self._pattern_cache_timestamps,
            pattern_cache_ttl=self._pattern_cache_ttl,
            pattern_cache_max_size=self._pattern_cache_max_size,
        )

    def _generate_pattern_from_wrapper(
        self,
        description: str,
        card_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a fallback pattern. Delegates to search.generate_pattern_from_wrapper()."""
        from gchat.card_builder.search import generate_pattern_from_wrapper

        return generate_pattern_from_wrapper(description, card_params)

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

        # Get style metadata from matched pattern
        style_metadata = instance_params.get("style_metadata", {})

        # Merge card_params into instance_params (card_params takes precedence)
        params = {**instance_params, **(card_params or {})}

        # Auto-apply styles from matched pattern if not already styled
        if style_metadata and not self._has_explicit_styles(params):
            params = self._apply_pattern_styles(params, style_metadata)

        # Build widgets based on component paths
        widgets = []
        text_consumed = False
        buttons_consumed = False
        image_consumed = False

        wrapper = self._get_wrapper()

        for comp_name in component_paths:
            if comp_name in ("DecoratedText", "decoratedText") and not text_consumed:
                text = params.get("text") or params.get("description", "")
                if text:
                    widget = self._build_component(
                        "DecoratedText",
                        {"text": text, "wrap_text": True},
                        wrapper=wrapper,
                        wrap_with_key=True,
                    )
                    if widget:
                        widgets.append(widget)
                        text_consumed = True

            elif comp_name in ("TextParagraph", "textParagraph") and not text_consumed:
                text = params.get("text") or params.get("description", "")
                if text:
                    widget = self._build_component(
                        "TextParagraph",
                        {"text": text},
                        wrapper=wrapper,
                        wrap_with_key=True,
                    )
                    if widget:
                        widgets.append(widget)
                        text_consumed = True

            elif comp_name in ("ButtonList", "buttonList") and not buttons_consumed:
                buttons = params.get("buttons", [])
                if buttons:
                    # Build button instances via wrapper
                    btn_instances = []
                    for btn in buttons:
                        if isinstance(btn, dict):
                            btn_instance = self._build_component(
                                "Button",
                                {
                                    "text": btn.get("text", "Button"),
                                    "url": btn.get("url"),
                                },
                                wrapper=wrapper,
                                return_instance=True,
                            )
                            if btn_instance:
                                btn_instances.append(btn_instance)
                    # Build ButtonList with button instances
                    if btn_instances:
                        widget = self._build_component(
                            "ButtonList",
                            {},
                            wrapper=wrapper,
                            wrap_with_key=True,
                            child_instances=btn_instances,
                        )
                        if widget:
                            widgets.append(widget)
                            buttons_consumed = True

            elif comp_name in ("Image", "image") and not image_consumed:
                image_url = params.get("image_url")
                if image_url:
                    widget = self._build_component(
                        "Image",
                        {"imageUrl": image_url},
                        wrapper=wrapper,
                        wrap_with_key=True,
                    )
                    if widget:
                        widgets.append(widget)
                        image_consumed = True

            elif comp_name in ("Divider", "divider"):
                widget = self._build_component(
                    "Divider",
                    {},
                    wrapper=wrapper,
                    wrap_with_key=True,
                )
                if widget:
                    widgets.append(widget)

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
                context = {
                    "buttons": [],
                    "chips": [],
                    "content_texts": [],
                    "_button_index": 0,
                    "_chip_index": 0,
                    "_text_index": 0,
                }
                widget = self._build_widget_generic(comp_name, [], context)
                if widget:
                    widgets.append(widget)

        # If we have text but no text widget was added, add one now
        if not text_consumed and (params.get("text") or params.get("description")):
            text = params.get("text") or params.get("description", "")
            widget = self._build_component(
                "DecoratedText",
                {"text": text, "wrap_text": True},
                wrapper=wrapper,
                wrap_with_key=True,
            )
            if widget:
                widgets.insert(0, widget)

        # If we have buttons but no button widget was added, add one now
        if not buttons_consumed and params.get("buttons"):
            buttons = params["buttons"]
            btn_instances = []
            for btn in buttons:
                if isinstance(btn, dict):
                    btn_instance = self._build_component(
                        "Button",
                        {"text": btn.get("text", "Button"), "url": btn.get("url")},
                        wrapper=wrapper,
                        return_instance=True,
                    )
                    if btn_instance:
                        btn_instances.append(btn_instance)
            if btn_instances:
                widget = self._build_component(
                    "ButtonList",
                    {},
                    wrapper=wrapper,
                    wrap_with_key=True,
                    child_instances=btn_instances,
                )
                if widget:
                    widgets.append(widget)

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

    def _has_explicit_styles(self, params: Dict[str, Any]) -> bool:
        """Check if params have explicit Jinja styles. Delegates to card_builder.jinja_styling."""
        from gchat.card_builder.jinja_styling import has_explicit_styles

        return has_explicit_styles(params)

    def _apply_pattern_styles(
        self, params: Dict[str, Any], style_metadata: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """Apply pattern styles to text fields. Delegates to card_builder.jinja_styling."""
        from gchat.card_builder.jinja_styling import apply_pattern_styles

        return apply_pattern_styles(params, style_metadata)

    def _apply_style_to_text(
        self, text: str, style_metadata: Dict[str, List[str]]
    ) -> str:
        """Apply style to text string. Delegates to card_builder.jinja_styling."""
        from gchat.card_builder.jinja_styling import apply_style_to_text

        return apply_style_to_text(text, style_metadata)

    def _format_text_for_chat(self, text: str) -> str:
        """Format text for Google Chat. Delegates to card_builder.jinja_styling."""
        from gchat.card_builder.jinja_styling import format_text_for_chat

        return format_text_for_chat(text, self._get_jinja_env())

    # =========================================================================
    # DSL EXTRACTION
    # =========================================================================

    def _extract_structure_dsl(self, description: str) -> Optional[str]:
        """
        Extract Structure DSL notation from description.

        Extracts symbol patterns like "Symbol[Child×N]" from start of description.
        Symbols are dynamically mapped via ModuleWrapper.
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

        Content DSL format (symbols from ModuleWrapper):
            <symbol> 'text content' style_modifier
            <symbol> Label https://url.com

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
        """Apply Content DSL styles to text, generating Google Chat HTML.

        Delegates to gchat.card_builder.jinja_styling.apply_styles().
        """
        from gchat.card_builder.jinja_styling import apply_styles

        return apply_styles(text, styles, SEMANTIC_COLORS)

    # =========================================================================
    # CARD BUILDING FROM DSL
    # =========================================================================

    @staticmethod
    def _extract_demands(parsed_components) -> Dict[str, int]:
        """Extract component demands (multipliers) from a parsed DSL tree.

        Recursively walks the component tree and sums up multipliers per
        component type, skipping containers (Section, ButtonList, etc.)
        to focus on leaf components that consume params.
        """
        demands: Dict[str, int] = {}
        for comp in parsed_components:
            name = comp.get("name", "") if isinstance(comp, dict) else getattr(comp, "component", "")
            mult = comp.get("multiplier", 1) if isinstance(comp, dict) else getattr(comp, "multiplier", 1)
            children = comp.get("children", []) if isinstance(comp, dict) else getattr(comp, "children", [])

            # Only count leaf-ish components that consume from context
            # (not containers like Section, ButtonList, Grid, Carousel, Columns)
            if name not in ("Section", "ButtonList", "ChipList", "Grid", "Carousel", "Columns", "Column"):
                demands[name] = demands.get(name, 0) + mult

            if children:
                child_demands = SmartCardBuilderV2._extract_demands(children)
                for k, v in child_demands.items():
                    demands[k] = demands.get(k, 0) + v
        return demands

    def _build_from_dsl(
        self,
        structure_dsl: str,
        description: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        buttons: Optional[List[Dict]] = None,
        chips: Optional[List[Dict]] = None,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        items: Optional[List[Dict]] = None,
        grid_items: Optional[List[Dict]] = None,
        cards: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build a card from parsed DSL structure.

        Handles both regular card DSL and carousel DSL (symbols from ModuleWrapper).
        """
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
            # Each item can have: text, icon, top_label, bottom_label, wrapText
            if items:
                for item in items:
                    item_text = item.get("text", "")
                    styled_text = self._format_text_for_chat(item_text)
                    content_entry = {"text": item_text, "styled": styled_text}
                    # Pass through additional fields for DecoratedText
                    if item.get("icon"):
                        content_entry["icon"] = item["icon"]
                    if item.get("top_label"):
                        content_entry["top_label"] = self._format_text_for_chat(
                            item["top_label"]
                        )
                    if item.get("bottom_label"):
                        content_entry["bottom_label"] = self._format_text_for_chat(
                            item["bottom_label"]
                        )
                    # Always default wrapText to True for DecoratedText items
                    content_entry["wrapText"] = item.get("wrapText", True)
                    content_texts.append(content_entry)
                logger.info(f"📝 Added {len(items)} items to content_texts")

            # Build supply map for mismatch detection
            supply_map = {
                "buttons": buttons or [],
                "content_texts": content_texts,
                "chips": chips or [],
                "carousel_cards": cards or [],
                "grid_items": grid_items or items or [],
            }

            # Detect DSL-to-param mismatches (corrections applied via placeholder skip logic)
            demands = {}
            corrections = {}
            if wrapper and hasattr(wrapper, "detect_param_mismatches"):
                demands = self._extract_demands(parsed)
                mismatch_result = wrapper.detect_param_mismatches(
                    demands, supply_map
                )
                corrections = mismatch_result.get("corrections", {})
                for warning in mismatch_result.get("warnings", []):
                    logger.info(f"🔧 {warning}")

            # Create shared context for unified resource consumption
            context = {
                "buttons": buttons or [],
                "chips": chips or [],
                "carousel_cards": cards or [],
                "grid_items": grid_items or items or [],
                "image_url": image_url,
                "content_texts": content_texts,
                "_button_index": 0,
                "_chip_index": 0,
                "_carousel_card_index": 0,
                "_grid_item_index": 0,
                "_text_index": 0,
                "_mapping_report": InputMappingReport(
                    supplies={k: len(v) if isinstance(v, list) else (1 if v else 0)
                              for k, v in supply_map.items()},
                    demands=demands,
                    corrections=corrections,
                ),
            }

            logger.info(
                f"📦 Context pools: grid_items={len(context.get('grid_items', []))}, "
                f"content_texts={len(context.get('content_texts', []))}, "
                f"buttons={len(context.get('buttons', []))}"
            )
            if context.get("grid_items"):
                logger.debug(f"Grid items sample: {context['grid_items'][0]}")

            # Split pipe-separated sections and parse each independently
            section_dsls = [s.strip() for s in structure_dsl.split("|")]
            for section_dsl in section_dsls:
                if not section_dsl:
                    continue
                # Reset resource indices so each pipe-separated section
                # gets the same content pool (variations show different
                # structures with the same content, not leftover placeholders)
                for idx_key in list(context.keys()):
                    if idx_key.startswith("_") and idx_key.endswith("_index"):
                        context[idx_key] = 0
                section_parsed = validator.parse_structure(section_dsl)
                for component in section_parsed:
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

            # Attach mapping report as serializable dict (not the dataclass)
            mapping_report = context.get("_mapping_report")
            if mapping_report and hasattr(mapping_report, "to_dict"):
                card["_mapping_report"] = mapping_report.to_dict()

            return card

        except Exception as e:
            logger.warning(f"DSL card building failed: {e}")
            return None

    # =========================================================================
    # GENERIC WIDGET BUILDING (Mapping-Driven, No If/Else)
    # =========================================================================

    def _get_json_key(self, component_name: str) -> str:
        """Get camelCase JSON key from component name.

        Delegates to gchat.card_builder.rendering.get_json_key().
        E.g., "DecoratedText" -> "decoratedText", "ButtonList" -> "buttonList"
        """
        from gchat.card_builder.rendering import get_json_key

        return get_json_key(component_name)

    # =========================================================================
    # COMPONENT BUILDING — Delegated to ComponentBuilder
    # =========================================================================

    def _get_component_builder(self):
        """Get or create a ComponentBuilder instance."""
        if not hasattr(self, "_component_builder_instance") or self._component_builder_instance is None:
            from gchat.card_builder.component_builder import ComponentBuilder

            self._component_builder_instance = ComponentBuilder(
                wrapper=self._get_wrapper(),
                format_text_fn=self._format_text_for_chat,
            )
        return self._component_builder_instance

    def _build_widget_generic(
        self,
        component_name: str,
        grandchildren: List[Dict],
        context: Dict[str, Any],
        explicit_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generic widget builder. Delegates to ComponentBuilder.build_widget_generic()."""
        return self._get_component_builder().build_widget_generic(
            component_name, grandchildren, context, explicit_params
        )

    def _build_container_generic(
        self,
        component_name: str,
        children: List[Dict],
        context: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Container builder. Delegates to ComponentBuilder.build_container_generic()."""
        return self._get_component_builder().build_container_generic(
            component_name, children, context, params
        )

    def _build_columns_generic(
        self,
        children: List[Dict],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Columns builder. Delegates to ComponentBuilder.build_columns_generic()."""
        return self._get_component_builder().build_columns_generic(children, context)

    def _build_component(
        self,
        component_name: str,
        params: Dict[str, Any],
        wrapper: Optional["ComponentMetadataProvider"] = None,
        wrap_with_key: bool = False,
        children: Optional[List[Dict[str, Any]]] = None,
        validate: bool = False,
        return_instance: bool = False,
        child_instances: Optional[List[Any]] = None,
        auto_wrap: bool = False,
        target_parent: Optional[str] = None,
    ) -> Optional[Union[Dict[str, Any], Any]]:
        """Universal component builder. Delegates to ComponentBuilder.build_component()."""
        return self._get_component_builder().build_component(
            component_name=component_name,
            params=params,
            wrapper=wrapper,
            wrap_with_key=wrap_with_key,
            children=children,
            validate=validate,
            return_instance=return_instance,
            child_instances=child_instances,
            auto_wrap=auto_wrap,
            target_parent=target_parent,
        )

    def _find_required_wrapper_via_dag(
        self,
        component: str,
        target_parent: str,
        wrapper: Optional["ComponentMetadataProvider"] = None,
    ) -> Optional[str]:
        """Find required wrapper via DAG. Delegates to wrapper.find_required_wrapper()."""
        wrapper = wrapper or self._get_wrapper()
        if not wrapper or not hasattr(wrapper, "find_required_wrapper"):
            return None
        return wrapper.find_required_wrapper(component, target_parent)

    def _json_key_to_component_name(self, json_key: str) -> str:
        """Convert JSON key to component name.

        Delegates to gchat.card_builder.rendering.json_key_to_component_name().
        E.g., 'decoratedText' -> 'DecoratedText'
        """
        from gchat.card_builder.rendering import json_key_to_component_name

        return json_key_to_component_name(json_key)

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
        if/elif chains. Component behavior is determined by querying the ModuleWrapper:
        - get_context_resource(): Which resources each component consumes
        - get_children_field(): How container components store children
        - is_form_component(): Components needing name fields
        - is_empty_component(): Structure-only components

        Supports nested DSL notation (e.g., DecoratedText[Button]) via
        _map_children_to_params which uses wrapper relationship metadata.

        Args:
            children: Parsed child components from DSL
            buttons: List of button dicts from card_params
            image_url: Image URL for image widgets
            content_texts: Parsed content texts with styling
            context: Shared context for unified resource consumption

        Note: Resource consumption is tracked in context (_button_index, _text_index)
        so resources used in nested DSL aren't reused elsewhere.
        """
        widgets = []

        # Use shared context or create local one
        if context is None:
            context = {
                "buttons": buttons or [],
                "chips": [],  # Chips should come from shared context
                "image_url": image_url,
                "content_texts": content_texts,
                "_button_index": 0,
                "_chip_index": 0,
                "_text_index": 0,
                "_input_index": 0,
            }

        for child in children:
            child_name = child.get("name", "")
            multiplier = child.get("multiplier", 1)
            grandchildren = child.get("children", [])

            for _ in range(multiplier):
                # GENERIC: Build any widget using mapping-driven approach
                widget = self._build_widget_generic(child_name, grandchildren, context)
                if widget:
                    widgets.append(widget)

        return widgets

    def _build_child_widget(
        self,
        child_name: str,
        params: Dict[str, Any],
        grandchildren: List[Dict],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build a child widget. Delegates to rendering.build_child_widget()."""
        _ = grandchildren, context  # Reserved for future recursive use
        from gchat.card_builder.rendering import build_child_widget

        return build_child_widget(
            self._get_wrapper(), child_name, params,
            build_component_fn=self._build_component,
        )

    # =========================================================================
    # MODULAR FEEDBACK SECTION
    # =========================================================================
    # Dynamically assembles feedback widgets from component registries.
    # Each feedback widget needs: text (prompt) + clickable (callback)
    # Components are randomly selected and assembled per card.

    def _has_feedback(self, card: Dict) -> bool:
        """Check if card already has feedback content. Delegates to card_builder.validation."""
        from gchat.card_builder.validation import has_feedback

        return has_feedback(card)

    def _clean_card_metadata(self, obj: Any) -> Any:
        """Remove underscore-prefixed keys. Delegates to card_builder.validation."""
        from gchat.card_builder.validation import clean_card_metadata

        return clean_card_metadata(obj)

    def validate_content(self, card_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate card content. Delegates to card_builder.validation."""
        from gchat.card_builder.validation import validate_content

        return validate_content(card_dict)

    def validate_and_repair_card(
        self, google_format_card: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], List[str]]:
        """Validate card content and structure, auto-repair if needed.

        Runs content validation, then structural validation with auto-repair.
        Generates DSL notation once after all repairs are applied.

        Args:
            google_format_card: Card dict with cardId + card structure

        Returns:
            Tuple of (is_valid, rendered_dsl, issues_list)
        """
        from gchat.card_builder.validation import fix_structure, validate_structure

        final_card = (
            google_format_card.get("card", {})
            if isinstance(google_format_card, dict)
            else {}
        )

        # Content validation
        is_valid_content, content_issues = self.validate_content(final_card)
        if not is_valid_content:
            return False, None, content_issues

        # Structural validation + auto-repair
        is_valid_structure, structure_issues = validate_structure(final_card)
        if not is_valid_structure:
            logger.warning(
                f"⚠️ Structural issues detected ({len(structure_issues)}), auto-repairing..."
            )
            fixed_card, fixes_applied = fix_structure(final_card)
            for fix in fixes_applied:
                logger.info(f"  🔧 {fix}")

            # Replace the card in google_format_card
            if isinstance(google_format_card, dict) and "card" in google_format_card:
                google_format_card["card"] = fixed_card

            content_issues = (content_issues or []) + [
                f"[auto-fixed] {f}" for f in fixes_applied
            ]

        # Generate DSL notation once (after all repairs)
        rendered_dsl = self.generate_dsl_notation(google_format_card)
        return True, rendered_dsl, content_issues or []

    def generate_dsl_notation(self, card: Dict[str, Any]) -> Optional[str]:
        """Generate DSL notation from a rendered card structure.

        Delegates to gchat.card_builder.dsl.generate_dsl_notation().

        Args:
            card: Card dict in Google Chat format (with sections/widgets)

        Returns:
            DSL string using symbols from ModuleWrapper, or None if unable to generate
        """
        try:
            wrapper = self._get_wrapper()
            if not wrapper:
                return None

            from gchat.card_builder.dsl import generate_dsl_notation

            return generate_dsl_notation(card, wrapper.symbol_mapping, wrapper=wrapper)

        except Exception as e:
            logger.debug(f"Failed to generate DSL from card: {e}")
            return None

    def _get_feedback_base_url(self) -> str:
        """Get the feedback base URL from settings. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import get_feedback_base_url

        return get_feedback_base_url()

    def _make_callback_url(
        self, card_id: str, feedback_val: str, feedback_type: str
    ) -> str:
        """Create feedback callback URL. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import make_callback_url

        return make_callback_url(card_id, feedback_val, feedback_type)

    @fire_and_forget
    def _store_card_pattern(
        self,
        card_id: str,
        description: str,
        title: Optional[str],
        structure_dsl: Optional[str],
        card: Dict[str, Any],
        description_rendered: Optional[str] = None,
        jinja_applied: bool = False,
        supply_map: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store card content pattern in Qdrant (fire-and-forget).

        Delegates to search.store_card_pattern(). Runs in background thread.
        Use _store_card_pattern.sync() for synchronous testing.
        """
        from gchat.card_builder.search import store_card_pattern

        store_card_pattern(
            card_id=card_id,
            description=description,
            title=title,
            structure_dsl=structure_dsl,
            card=card,
            description_rendered=description_rendered,
            jinja_applied=jinja_applied,
            enable_feedback=ENABLE_FEEDBACK_BUTTONS,
            supply_map=supply_map,
        )

    @fire_and_forget
    def _store_feedback_ui_pattern(
        self,
        card_id: str,
        feedback_section: Dict[str, Any],
    ) -> None:
        """Store feedback UI pattern in Qdrant (fire-and-forget).

        Delegates to search.store_feedback_ui_pattern(). Runs in background thread.
        Use _store_feedback_ui_pattern.sync() for synchronous testing.
        """
        from gchat.card_builder.search import store_feedback_ui_pattern

        store_feedback_ui_pattern(
            card_id=card_id,
            feedback_section=feedback_section,
            enable_feedback=ENABLE_FEEDBACK_BUTTONS,
        )

    # OPTIMIAED MAKE DYNMAIC NOT PREDEFINED DUAL COMPONENT BUILDERS (text + click in one widget)

    def _extract_component_paths(self, card: Dict[str, Any]) -> List[str]:
        """Extract component paths from a card structure.

        Delegates to gchat.card_builder.dsl.extract_component_paths().

        Returns:
            List of component names found (e.g., ["Section", "TextParagraph", "ButtonList"])
        """
        from gchat.card_builder.dsl import extract_component_paths

        return extract_component_paths(card)

    # -------------------------------------------------------------------------
    # FEEDBACK WIDGET BUILDERS — Delegated to feedback.widgets module
    # -------------------------------------------------------------------------

    def _build_feedback_widget(
        self, component_name: str, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build a feedback widget. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import build_feedback_widget

        return build_feedback_widget(self, component_name, params)

    def _style_feedback_keyword(self, keyword: str, style: str) -> str:
        """Apply styling to a feedback keyword. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import style_feedback_keyword

        return style_feedback_keyword(keyword, style)

    def _build_styled_feedback_prompt(self, prompt_tuple: tuple) -> str:
        """Build a feedback prompt with styled keyword. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import build_styled_feedback_prompt

        return build_styled_feedback_prompt(prompt_tuple)

    def _build_text_feedback(self, text_type: str, text: str, **kwargs) -> Dict:
        """Config-driven text builder. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import build_text_feedback

        return build_text_feedback(self, text_type, text, **kwargs)

    def _text_paragraph(self, text: str, **_kwargs) -> Dict:
        from gchat.card_builder.feedback.widgets import text_paragraph

        return text_paragraph(self, text, **_kwargs)

    def _text_decorated(self, text: str, **_kwargs) -> Dict:
        from gchat.card_builder.feedback.widgets import text_decorated

        return text_decorated(self, text, **_kwargs)

    def _text_decorated_icon(self, text: str, **_kwargs) -> Dict:
        from gchat.card_builder.feedback.widgets import text_decorated_icon

        return text_decorated_icon(self, text, **_kwargs)

    def _text_decorated_labeled(
        self, text: str, label: str = "Feedback", **_kwargs
    ) -> Dict:
        from gchat.card_builder.feedback.widgets import text_decorated_labeled

        return text_decorated_labeled(self, text, label=label, **_kwargs)

    def _text_chip(self, text: str, **_kwargs) -> Dict:
        from gchat.card_builder.feedback.widgets import text_chip

        return text_chip(self, text, **_kwargs)

    def _build_clickable_item(
        self,
        component_name: str,
        label: str,
        url: str,
        *,
        icon: Optional[str] = None,
        icon_url: Optional[str] = None,
        material_icon: Optional[str] = None,
        button_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a clickable item. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import build_clickable_item

        return build_clickable_item(
            self, component_name, label, url,
            icon=icon, icon_url=icon_url,
            material_icon=material_icon, button_type=button_type,
        )

    @staticmethod
    def _apply_button_icon(
        btn: Dict[str, Any],
        material_icon: Optional[str],
        icon: Optional[str],
        icon_url: Optional[str],
    ) -> None:
        """Apply icon to a button dict. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import apply_button_icon

        apply_button_icon(btn, material_icon, icon, icon_url)

    def _build_feedback_button_item(
        self,
        text: str,
        url: str,
        icon: Optional[str] = None,
        icon_url: Optional[str] = None,
        material_icon: Optional[str] = None,
        button_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a button item. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import build_feedback_button_item

        return build_feedback_button_item(
            self, text, url, icon=icon, icon_url=icon_url,
            material_icon=material_icon, button_type=button_type,
        )

    def _build_feedback_chip_item(self, label: str, url: str) -> Dict[str, Any]:
        """Build a chip item. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import build_feedback_chip_item

        return build_feedback_chip_item(self, label, url)

    @staticmethod
    def _resolve_config_icon(
        config: Dict, static_key: Optional[str], source_key: str
    ) -> Optional[str]:
        """Resolve icon from config. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import resolve_config_icon

        return resolve_config_icon(config, static_key, source_key)

    def _build_clickable_feedback(
        self, handler_type: str, card_id: str, feedback_type: str
    ) -> Dict:
        """Config-driven click handler. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import build_clickable_feedback

        return build_clickable_feedback(self, handler_type, card_id, feedback_type)

    def _click_button_list(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        from gchat.card_builder.feedback.widgets import click_button_list

        return click_button_list(self, card_id, feedback_type, **_kwargs)

    def _click_chip_list(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        from gchat.card_builder.feedback.widgets import click_chip_list

        return click_chip_list(self, card_id, feedback_type, **_kwargs)

    def _click_icon_buttons(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        from gchat.card_builder.feedback.widgets import click_icon_buttons

        return click_icon_buttons(self, card_id, feedback_type, **_kwargs)

    def _click_icon_buttons_alt(
        self, card_id: str, feedback_type: str, **_kwargs
    ) -> Dict:
        from gchat.card_builder.feedback.widgets import click_icon_buttons_alt

        return click_icon_buttons_alt(self, card_id, feedback_type, **_kwargs)

    def _click_url_image_buttons(
        self, card_id: str, feedback_type: str, **_kwargs
    ) -> Dict:
        from gchat.card_builder.feedback.widgets import click_url_image_buttons

        return click_url_image_buttons(self, card_id, feedback_type, **_kwargs)

    def _click_star_rating(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        from gchat.card_builder.feedback.widgets import click_star_rating

        return click_star_rating(self, card_id, feedback_type, **_kwargs)

    def _click_emoji_rating(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        from gchat.card_builder.feedback.widgets import click_emoji_rating

        return click_emoji_rating(self, card_id, feedback_type, **_kwargs)

    def _dual_decorated_with_button(
        self, text: str, card_id: str, feedback_type: str, **_kwargs
    ) -> List[Dict]:
        """Decorated text with inline button. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import dual_decorated_with_button

        return dual_decorated_with_button(self, text, card_id, feedback_type, **_kwargs)

    def _dual_decorated_inline_only(
        self, text: str, card_id: str, feedback_type: str, **_kwargs
    ) -> List[Dict]:
        """Most compact inline button. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import dual_decorated_inline_only

        return dual_decorated_inline_only(self, text, card_id, feedback_type, **_kwargs)

    def _dual_columns_inline(
        self, text: str, card_id: str, feedback_type: str, **_kwargs
    ) -> List[Dict]:
        """Columns layout. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import dual_columns_inline

        return dual_columns_inline(self, text, card_id, feedback_type, **_kwargs)

    def _build_feedback_layout(
        self,
        layout_type: str,
        content_widgets: List[Dict],
        form_widgets: List[Dict],
        content_first: bool,
    ) -> List[Dict]:
        """Config-driven layout builder. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import build_feedback_layout

        return build_feedback_layout(
            layout_type, content_widgets, form_widgets, content_first
        )

    def _layout_sequential(
        self, content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
    ) -> List[Dict]:
        from gchat.card_builder.feedback.widgets import layout_sequential

        return layout_sequential(content_widgets, form_widgets, content_first)

    def _layout_with_divider(
        self, content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
    ) -> List[Dict]:
        from gchat.card_builder.feedback.widgets import layout_with_divider

        return layout_with_divider(content_widgets, form_widgets, content_first)

    def _layout_compact(
        self, content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
    ) -> List[Dict]:
        from gchat.card_builder.feedback.widgets import layout_compact

        return layout_compact(content_widgets, form_widgets, content_first)

    def _create_feedback_section(self, card_id: str) -> Dict:
        """Create feedback section by randomly assembling components. Delegates to feedback.widgets."""
        from gchat.card_builder.feedback.widgets import create_feedback_section

        return create_feedback_section(self, card_id)

    # =========================================================================
    # PARAM-DRIVEN BUILD ENTRY POINT
    # =========================================================================

    def build_from_params(
        self,
        description: str,
        card_params: Dict[str, Any],
        suggested_dsl: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build a card from description and a flat card_params dict.

        Extracts and normalizes individual params from card_params (title,
        subtitle, buttons, grid_items, etc.) and delegates to build().
        Handles grid/image transformation and pre-built sections passthrough.

        Args:
            description: Card description with optional DSL notation
            card_params: Flat dict of card parameters from MCP tool call
            suggested_dsl: Optional suggested DSL to use when description has no DSL

        Returns:
            Card dict in Google Chat cardsV2 format (with cardId + card),
            or None if building failed.
        """
        import time

        # Resolve symbol-keyed params (e.g., "ᵬ": [...] → "buttons": [...])
        # This enables Format A/B/C documented in the card-params skill
        wrapper = self._get_wrapper()
        if wrapper and hasattr(wrapper, "symbol_mapping"):
            from gchat.card_builder.symbol_params import resolve_symbol_params

            reverse_symbols = {v: k for k, v in wrapper.symbol_mapping.items()}
            card_params = resolve_symbol_params(card_params, reverse_symbols, wrapper)

        # Extract params from flat dict
        title = card_params.get("title")
        subtitle = card_params.get("subtitle")
        image_url = card_params.get("image_url") or card_params.get("header_image_url")
        text = card_params.get("text")
        buttons = card_params.get("buttons")
        chips = card_params.get("chips")
        grid = card_params.get("grid")
        images = card_params.get("images")
        image_titles = card_params.get("image_titles")
        items = card_params.get("items")
        grid_items = card_params.get("grid_items")
        cards = card_params.get("cards") or card_params.get("carousel_cards")
        sections = card_params.get("sections")

        # Map decorated_texts → items for DecoratedText widget consumption
        # decorated_texts is a common param shape: [{top_label, text, bottom_label}, ...]
        decorated_texts = card_params.get("decorated_texts")
        if decorated_texts and not items:
            items = decorated_texts
            logger.info(f"📝 Mapped {len(decorated_texts)} decorated_texts → items")

        # Pre-built sections passthrough
        card_dict = None
        if sections and isinstance(sections, list) and len(sections) > 0:
            has_widgets = any(
                isinstance(s, dict) and s.get("widgets") for s in sections
            )
            if has_widgets:
                logger.info(
                    f"📋 Using pre-built sections passthrough: {len(sections)} section(s)"
                )
                card_dict = {"sections": sections}
                if title:
                    header = {"title": title}
                    if subtitle:
                        header["subtitle"] = subtitle
                    card_dict["header"] = header

        # Convert grid images to items (only if grid_items not already set)
        if not grid_items:
            if images:
                logger.info(f"🔲 Grid images: {len(images)}")
                grid_items = [
                    {
                        "title": (
                            image_titles[i]
                            if image_titles and i < len(image_titles)
                            else f"Item {i + 1}"
                        ),
                        "image_url": img_url,
                    }
                    for i, img_url in enumerate(images)
                ]
            elif grid and grid.get("items"):
                logger.info(f"🔲 Grid items: {len(grid.get('items', []))}")
                grid_items = grid["items"]

        if cards:
            logger.info(f"🎠 Carousel: {len(cards)} card(s)")

        # Build via unified DSL/DAG pipeline (skip if pre-built)
        if not card_dict:
            build_description = description
            if suggested_dsl and not self._extract_structure_dsl(description):
                build_description = suggested_dsl
                logger.info(
                    f"💡 Using suggested DSL as build description: {suggested_dsl}"
                )

            card_dict = self.build(
                description=build_description,
                title=title,
                subtitle=subtitle,
                buttons=buttons,
                chips=chips,
                image_url=image_url,
                text=text,
                items=items,
                grid_items=grid_items,
                cards=cards,
            )

        if card_dict:
            card_id = f"smart_card_{int(time.time())}_{hash(str(card_params)) % 10000}"
            return {
                "cardId": card_id,
                "card": card_dict,
            }
        return None

    # =========================================================================
    # MAIN BUILD METHOD
    # =========================================================================

    def build(
        self,
        description: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        buttons: Optional[List[Dict]] = None,
        chips: Optional[List[Dict]] = None,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        items: Optional[List[Dict]] = None,
        grid_items: Optional[List[Dict]] = None,
        cards: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Build a card from DSL description.

        Args:
            description: Card description with optional DSL notation
                Structure DSL: Symbol[Child×N] pattern (symbols from ModuleWrapper)
                Carousel DSL: Use symbols from ModuleWrapper (query wrapper for current mappings)
                Content DSL: <symbol> 'text' style_modifier
            title: Card header title
            subtitle: Card header subtitle
            buttons: Explicit button list (overrides Content DSL buttons)
            chips: Explicit chip list [{label, url, icon}, ...]
            image_url: Image URL for image widgets
            text: Explicit text content for text widgets (used if no Content DSL texts)
            items: Array of decorated text items [{text, icon, top_label}, ...]
            cards: Carousel cards list [{title, subtitle, image_url, text, buttons}, ...]

        Returns:
            Card dict in Google Chat format
        """
        card_id = str(uuid.uuid4())[:8]
        card = None
        supply_map = None
        # Reset Jinja tracking for this build
        self._jinja_applied = False
        # Track the Jinja-rendered description (if different from raw)
        self._description_rendered: Optional[str] = None

        # Pre-process description through Jinja to capture rendered version
        # This allows us to store both raw and processed text in the pattern
        if description:
            processed_desc = self._format_text_for_chat(description)
            if processed_desc != description:
                self._description_rendered = processed_desc

        # Collect all params for pattern detection
        all_params = {
            "title": title,
            "subtitle": subtitle,
            "buttons": buttons,
            "chips": chips,
            "image_url": image_url,
            "text": text,
            "items": items,
            "cards": cards,  # Carousel cards
        }

        # Try DSL-based building first (handles both regular cards and carousels)
        # DSL symbols are dynamically generated from ModuleWrapper
        structure_dsl = self._extract_structure_dsl(description)
        if structure_dsl:
            logger.info(f"🔣 Found Structure DSL: {structure_dsl}")

            # Auto-apply styles from similar patterns (before DSL build)
            # This allows DSL cards to inherit styles from previously successful cards
            styled_text = text
            styled_items = items

            # Query pattern for style_metadata
            pattern = self._query_qdrant_patterns(description, all_params)
            style_metadata = {}
            if pattern:
                style_metadata = pattern.get("instance_params", {}).get(
                    "style_metadata", {}
                )

            if style_metadata.get("semantic_styles") or style_metadata.get(
                "jinja_filters"
            ):
                logger.info(
                    f"🎨 Found style_metadata for auto-styling: {style_metadata}"
                )

                # Apply styles to text
                if text and not self._has_explicit_styles({"text": text}):
                    styled_text = self._apply_style_to_text(text, style_metadata)
                    if styled_text != text:
                        logger.info(
                            f"🎨 Styled text: {text[:30]}... -> {styled_text[:50]}..."
                        )

                # Apply styles to each item in items array
                if items:
                    styled_items = []
                    for item in items:
                        styled_item = dict(item)  # Copy to avoid mutation
                        if item.get("text") and not self._has_explicit_styles(
                            {"text": item["text"]}
                        ):
                            styled_item["text"] = self._apply_style_to_text(
                                item["text"], style_metadata
                            )
                        if item.get("top_label") and not self._has_explicit_styles(
                            {"text": item["top_label"]}
                        ):
                            styled_item["top_label"] = self._apply_style_to_text(
                                item["top_label"], style_metadata
                            )
                        if item.get("bottom_label") and not self._has_explicit_styles(
                            {"text": item["bottom_label"]}
                        ):
                            styled_item["bottom_label"] = self._apply_style_to_text(
                                item["bottom_label"], style_metadata
                            )
                        styled_items.append(styled_item)
                    logger.info(f"🎨 Styled {len(items)} items")

            card = self._build_from_dsl(
                structure_dsl=structure_dsl,
                description=description,
                title=title,
                subtitle=subtitle,
                buttons=buttons,
                chips=chips,
                image_url=image_url,
                text=styled_text,
                items=styled_items,
                grid_items=grid_items,
                cards=cards,
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
                    "chips": chips or [],
                    "_text_index": 0,
                    "_button_index": 0,
                    "_chip_index": 0,
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
                    widget = self._build_widget_generic(
                        "ButtonList", button_children, context
                    )
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
            # Build text widget using wrapper for consistency
            wrapper = self._get_wrapper()
            text_widget = self._build_component(
                "TextParagraph",
                {"text": description},
                wrapper=wrapper,
                wrap_with_key=True,
            )
            if text_widget:
                card = {"sections": [{"widgets": [text_widget]}]}
            else:
                # Ultimate fallback if wrapper fails
                processed_text = self._format_text_for_chat(description)
                card = {
                    "sections": [
                        {"widgets": [{"textParagraph": {"text": processed_text}}]}
                    ]
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
        # Stores BOTH raw description and Jinja-rendered version for analytics
        # Note: Pass copies and captured state since this runs in background thread
        self._store_card_pattern(
            card_id=card_id,
            description=description,
            title=title,
            structure_dsl=structure_dsl,
            card=dict(card) if card else {},  # Copy to avoid mutation issues
            description_rendered=self._description_rendered,
            jinja_applied=self._jinja_applied,
            supply_map=dict(supply_map) if supply_map else None,
        )

        # Add feedback section AFTER storing content pattern
        # The feedback UI is stored SEPARATELY with pattern_type="feedback_ui"
        if ENABLE_FEEDBACK_BUTTONS and card and not self._has_feedback(card):
            feedback = self._create_feedback_section(card_id)

            # Store the feedback UI pattern separately (pattern_type="feedback_ui")
            # Note: Pass copy since this runs in background thread
            self._store_feedback_ui_pattern(card_id, dict(feedback) if feedback else {})

            # Add a divider before feedback to visually separate content from feedback UI
            divider_section = {"widgets": [{"divider": {}}]}
            if "sections" in card:
                card["sections"].append(divider_section)
                card["sections"].append(feedback)
            else:
                card["sections"] = [divider_section, feedback]

        # Extract mapping report before cleanup (underscore keys get removed)
        mapping_report = card.pop("_mapping_report", None)

        # Clean metadata before returning (Google Chat rejects underscore-prefixed keys)
        cleaned = self._clean_card_metadata(card)

        # Re-attach report dict for upstream extraction (card_tools.py)
        if mapping_report and isinstance(cleaned, dict):
            cleaned["_mapping_report"] = mapping_report

        return cleaned

    def initialize(self):
        """Initialize the builder (v1 compatibility)."""
        # V2 initializes lazily, this is a no-op for compatibility
        pass

# =============================================================================
# DSL SUGGESTION - Suggest DSL based on card_params
# =============================================================================

def suggest_dsl_for_params(
    card_params: Dict[str, Any], symbols: Dict[str, str]
) -> Optional[str]:
    """Suggest DSL structure based on provided card_params.

    Delegates to gchat.card_builder.dsl.suggest_dsl_for_params().

    Args:
        card_params: Dictionary with parameters like text, buttons, image_url, etc.
        symbols: Symbol mapping from ModuleWrapper (e.g., wrapper.symbol_mapping)

    Returns:
        Suggested DSL string using symbols from the mapping, or None if no suggestion
    """
    from gchat.card_builder.dsl import suggest_dsl_for_params as _suggest_dsl

    return _suggest_dsl(card_params, symbols)

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
