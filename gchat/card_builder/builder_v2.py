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
import logging
import os
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
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

logger = logging.getLogger(__name__)

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

# Style metadata extraction
from gchat.card_builder.jinja_styling import extract_style_metadata

# Metadata accessors (query wrapper or fall back to static dicts)
from gchat.card_builder.metadata import (
    get_children_field,
    get_container_child_type,
    get_context_resource,
    is_empty_component,
    is_form_component,
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
        """Generate a cache key from description and params."""
        import hashlib

        params_str = str(sorted(card_params.items())) if card_params else ""
        key_str = f"{description}:{params_str}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cached_pattern(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get a cached pattern if valid (not expired)."""
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
        # Evict oldest entries if cache is full
        if len(self._pattern_cache) >= self._pattern_cache_max_size:
            oldest_key = min(
                self._pattern_cache_timestamps, key=self._pattern_cache_timestamps.get
            )
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
        """
        Query patterns using wrapper's SearchMixin methods (preferred).

        Uses DSL-aware search when DSL symbols are detected in the description,
        otherwise falls back to hybrid V7 search with positive feedback filters.

        Searches are parallelized when DSL is detected for improved latency.

        Args:
            description: Card description (may include DSL symbols)
            card_params: Additional params to include in search context

        Returns:
            Dict with component_paths, instance_params from best match, or None
        """
        try:
            from gchat.card_framework_wrapper import get_card_framework_wrapper

            wrapper = get_card_framework_wrapper()

            # Check for DSL in description (fast, synchronous - determines search strategy)
            extracted = wrapper.extract_dsl_from_text(description)
            has_dsl = extracted.get("has_dsl")

            if has_dsl:
                logger.info(f"🔤 DSL detected: {extracted['dsl']}")

            # Run searches in parallel when DSL is detected (both searches are independent)
            with ThreadPoolExecutor(max_workers=2) as executor:
                # Always submit hybrid search for style_metadata extraction
                hybrid_future = executor.submit(
                    wrapper.search_v7_hybrid,
                    description=description,
                    component_paths=None,
                    limit=5,
                    token_ratio=1.0,
                    content_feedback="positive",
                    form_feedback="positive",
                    include_classes=False,  # Only want patterns
                )

                # Conditionally submit DSL search in parallel
                dsl_future = None
                if has_dsl:
                    dsl_future = executor.submit(
                        wrapper.search_by_dsl,
                        text=description,
                        limit=5,
                        score_threshold=0.3,
                        vector_name="inputs",  # Search for patterns
                        type_filter="instance_pattern",
                    )

                # Gather results (blocks until complete)
                class_results, content_patterns, form_patterns = hybrid_future.result()
                dsl_results = dsl_future.result() if dsl_future else None

            # Find patterns with actual style_metadata content (for auto-styling)
            styled_pattern = None
            for pattern in content_patterns:
                instance_params = pattern.get("instance_params", {})
                style_meta = instance_params.get("style_metadata", {})
                # Check for actual style content, not just empty dict
                if style_meta.get("semantic_styles") or style_meta.get("jinja_filters"):
                    styled_pattern = pattern
                    logger.info(f"🎨 Found pattern with style_metadata: {style_meta}")
                    break

            # Process DSL results if available
            if dsl_results:
                best = dsl_results[0]
                component_paths = self._extract_paths_from_pattern(best)
                instance_params = best.get("instance_params", {})

                # Check if DSL result has actual style content (not just empty dict)
                dsl_style = instance_params.get("style_metadata", {})
                dsl_has_styles = dsl_style.get("semantic_styles") or dsl_style.get(
                    "jinja_filters"
                )

                # Merge style_metadata from styled_pattern if DSL result lacks actual styles
                if styled_pattern and not dsl_has_styles:
                    styled_instance_params = styled_pattern.get("instance_params", {})
                    styled_style = styled_instance_params.get("style_metadata", {})
                    if styled_style.get("semantic_styles") or styled_style.get(
                        "jinja_filters"
                    ):
                        instance_params = {
                            **instance_params,
                            "style_metadata": styled_style,
                        }
                        logger.info(
                            f"🎨 Merged style_metadata from similar pattern: {styled_style}"
                        )

                return {
                    "component_paths": component_paths,
                    "instance_params": instance_params,
                    "structure_description": best.get("structure_description", ""),
                    "score": best.get("score", 0),
                    "source": "wrapper_dsl",
                }

            # No DSL results - use hybrid search results
            if content_patterns:
                # Prefer patterns with style_metadata
                best = styled_pattern if styled_pattern else content_patterns[0]
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
        then falls back to feedback_loop.query_with_discovery() using Qdrant's Discovery API.
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
            return (
                cached_result if cached_result else None
            )  # Handle cached None as empty dict

        # Try wrapper-based search first (DSL-aware, cleaner)
        wrapper_result = self._query_wrapper_patterns(description, card_params)
        if wrapper_result:
            logger.info(
                f"✅ Wrapper pattern match (source: {wrapper_result.get('source', 'unknown')})"
            )
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
                feedback_loop.query_with_discovery(
                    component_query=description,
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

    def _get_style_for_text(
        self, text: str, style_metadata: Dict[str, List[str]]
    ) -> Optional[str]:
        """Get style for text based on content. Delegates to card_builder.jinja_styling."""
        from gchat.card_builder.jinja_styling import get_style_for_text

        return get_style_for_text(text, style_metadata)

    def _apply_style_to_text(
        self, text: str, style_metadata: Dict[str, List[str]]
    ) -> str:
        """Apply style to text string. Delegates to card_builder.jinja_styling."""
        from gchat.card_builder.jinja_styling import apply_style_to_text

        return apply_style_to_text(text, style_metadata)

    def _apply_styles_recursively(
        self, obj: Any, style_metadata: Dict[str, List[str]], depth: int = 0
    ) -> Any:
        """Apply styles recursively. Delegates to card_builder.jinja_styling."""
        from gchat.card_builder.jinja_styling import apply_styles_recursively

        return apply_styles_recursively(obj, style_metadata, depth)

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
                        content_entry["top_label"] = self._format_text_for_chat(item["top_label"])
                    if item.get("bottom_label"):
                        content_entry["bottom_label"] = self._format_text_for_chat(item["bottom_label"])
                    # Always default wrapText to True for DecoratedText items
                    content_entry["wrapText"] = item.get("wrapText", True)
                    content_texts.append(content_entry)
                logger.info(f"📝 Added {len(items)} items to content_texts")

            # Create shared context for unified resource consumption
            # This ensures buttons, texts, chips, cards, etc. are consumed sequentially across all components
            context = {
                "buttons": buttons or [],
                "chips": chips or [],
                "carousel_cards": cards
                or [],  # For carousel DSL (symbols from ModuleWrapper)
                "grid_items": items or [],  # For grid DSL (GridItem consumption)
                "image_url": image_url,
                "content_texts": content_texts,
                "_button_index": 0,  # Track button consumption
                "_chip_index": 0,  # Track chip consumption
                "_carousel_card_index": 0,  # Track carousel card consumption
                "_grid_item_index": 0,  # Track grid item consumption
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

        Delegates to gchat.card_builder.rendering.get_json_key().
        E.g., "DecoratedText" -> "decoratedText", "ButtonList" -> "buttonList"
        """
        from gchat.card_builder.rendering import get_json_key

        return get_json_key(component_name)

    def _consume_from_context(
        self,
        component_name: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Consume resource from context. Delegates to card_builder.context."""
        from gchat.card_builder.context import consume_from_context

        return consume_from_context(component_name, context, self._get_wrapper())

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
            "Card",
            "CardHeader",
            "Section",  # Top-level containers
            "OnClick",
            "OpenLink",
            "onClick",
            "openLink",  # Nested inside buttons
            "Button",  # Handled by ButtonList
            "Icon",
            "icon",  # Nested inside decoratedText.startIcon or buttons
        }
        if component_name in NON_WIDGET_COMPONENTS:
            return None

        json_key = self._get_json_key(component_name)
        params = explicit_params.copy() if explicit_params else {}
        wrapper = self._get_wrapper()

        # 1. Empty components (just structure, no content)
        if is_empty_component(component_name, wrapper):
            return {json_key: {}}

        # 2. Consume from context if this component type uses resources
        consumed = self._consume_from_context(component_name, context)
        # Consumed values are defaults, explicit_params override
        for k, v in consumed.items():
            params.setdefault(k, v)

        # 3. Container components - build children recursively
        children_field = get_children_field(component_name, wrapper)
        if children_field:
            logger.debug(
                f"🎠 Container component: {component_name} "
                f"(children_field={children_field}, "
                f"children_count={len(grandchildren)})"
            )
            result = self._build_container_generic(
                component_name, grandchildren, context, params
            )
            logger.debug(
                f"🎠 Container result for {component_name}: "
                f"{result.keys() if result else 'None'}"
            )
            return result

        # 4. Components with nested children (like DecoratedText with Button)
        # Build children first - they come back as pre-built JSON dicts
        child_params = {}
        if grandchildren:
            child_params = self._map_children_to_params(
                component_name, grandchildren, context
            )

        # 5. Form components need a name field
        if is_form_component(component_name, wrapper):
            input_index = context.get("_input_index", 0)
            params.setdefault("name", f"{component_name.lower()}_{input_index}")
            params.setdefault("label", component_name.replace("Input", " Input"))
            context["_input_index"] = input_index + 1

        # 5.5 Pre-process DecoratedText special fields (icon -> startIcon, labels, wrapText)
        # Must happen BEFORE wrapper build so wrapper gets clean params
        decorated_text_extras = {}
        if component_name == "DecoratedText":
            if params.get("icon"):
                from gchat.material_icons import resolve_icon_name

                icon_name = resolve_icon_name(params.pop("icon"))
                decorated_text_extras["startIcon"] = {
                    "materialIcon": {"name": icon_name}
                }
            if params.get("top_label"):
                decorated_text_extras["topLabel"] = params.pop("top_label")
            if params.get("bottom_label"):
                decorated_text_extras["bottomLabel"] = params.pop("bottom_label")
            # Always ensure wrapText is set (default True for multi-line content)
            decorated_text_extras["wrapText"] = params.pop("wrapText", True)

        # 6. Build via wrapper for proper type handling (only if no pre-built children)
        # When there are pre-built children (JSON dicts), wrapper can't use them directly
        if not child_params:
            wrapper = self._get_wrapper()
            if wrapper:
                built = self._build_component(component_name, params, wrapper=wrapper)
                if built:
                    # Merge in DecoratedText extras (icon, labels) after wrapper build
                    if decorated_text_extras:
                        built.update(decorated_text_extras)
                    return {json_key: built}

        # 7. Build widget with merged children
        # For components with nested children, merge child_params into the base params
        widget_content = {}

        # Add base params (e.g., text for DecoratedText)
        # Process text through Jinja for consistent styling support
        if "text" in params:
            widget_content["text"] = self._format_text_for_chat(params["text"])
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
            img_url = params.get("imageUrl") or context.get("image_url")
            if not img_url:
                logger.debug("Image component has no URL, skipping")
                return None
            return {json_key: {"imageUrl": img_url}}

        # Return None instead of "Item" placeholder if no content
        # This ensures only explicitly provided content is rendered
        return {json_key: widget_content} if widget_content else None

    def _build_container_generic(
        self,
        component_name: str,
        children: List[Dict],
        context: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build container components (ButtonList, Grid, etc.) generically.

        Uses wrapper.get_children_field() and wrapper.get_container_child_type() (SSoT).
        """
        json_key = self._get_json_key(component_name)
        wrapper = self._get_wrapper()
        children_field = get_children_field(component_name, wrapper) or "widgets"
        expected_child_type = get_container_child_type(component_name, wrapper)

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
                grid_params = self._consume_from_context("GridItem", context)
                grid_item = {"title": grid_params.get("title", f"Item {len(built_children) + 1}")}
                if grid_params.get("subtitle"):
                    grid_item["subtitle"] = grid_params["subtitle"]
                if grid_params.get("image_url"):
                    grid_item["image"] = {"imageUri": grid_params["image_url"]}
                elif grid_params.get("image"):
                    grid_item["image"] = grid_params["image"]
                built_children.append(grid_item)
            elif expected_child_type == "Chip":
                # Consume chip from context (similar to Button)
                chip_params = self._consume_from_context("Chip", context)
                chip_obj = {
                    "label": chip_params.get("label")
                    or chip_params.get("text", f"Chip {len(built_children) + 1}")
                }
                if chip_params.get("url"):
                    chip_obj["onClick"] = {"openLink": {"url": chip_params["url"]}}
                # Add icon if provided
                if chip_params.get("icon"):
                    chip_obj["icon"] = {"materialIcon": {"name": chip_params["icon"]}}
                built_children.append(chip_obj)
            elif expected_child_type == "CarouselCard":
                # Consume carousel card from context and build via wrapper
                card_params = self._consume_from_context("CarouselCard", context)
                logger.debug(
                    f"🎠 CarouselCard #{len(built_children)}: "
                    f"params={list(card_params.keys())}"
                )
                # Use wrapper's component system for CarouselCard
                wrapper = self._get_wrapper()
                if wrapper:
                    # CRITICAL: CarouselCard only accepts 'widgets' array, not direct
                    # title/text fields. Transform title/text into TextParagraph widgets.
                    if (
                        "title" in card_params or "text" in card_params
                    ) and "widgets" not in card_params:
                        widgets = []
                        idx = len(built_children)

                        # Add title as bold text paragraph using wrapper
                        title = card_params.get("title", f"Card {idx + 1}")
                        if title:
                            formatted_title = self._format_text_for_chat(title)
                            title_widget = self._build_component(
                                "TextParagraph",
                                {"text": f"<b>{formatted_title}</b>"},
                                wrapper=wrapper,
                                wrap_with_key=True,
                            )
                            if title_widget:
                                widgets.append(title_widget)

                        # Add main text content using wrapper
                        text = card_params.get("text")
                        if text:
                            text_widget = self._build_component(
                                "TextParagraph",
                                {"text": text},
                                wrapper=wrapper,
                                wrap_with_key=True,
                            )
                            if text_widget:
                                widgets.append(text_widget)

                        # Add buttons using wrapper ButtonList
                        buttons = card_params.get("buttons", [])
                        if buttons:
                            btn_instances = []
                            for b in buttons:
                                btn = self._build_component(
                                    "Button",
                                    {
                                        "text": b.get("text", "Button"),
                                        "url": b.get("url"),
                                    },
                                    wrapper=wrapper,
                                    return_instance=True,
                                )
                                if btn:
                                    btn_instances.append(btn)
                            if btn_instances:
                                btn_list_widget = self._build_component(
                                    "ButtonList",
                                    {},
                                    wrapper=wrapper,
                                    wrap_with_key=True,
                                    child_instances=btn_instances,
                                )
                                if btn_list_widget:
                                    widgets.append(btn_list_widget)

                        # Add image if provided
                        image_url = card_params.get("image_url") or card_params.get(
                            "image"
                        )
                        if image_url:
                            image_widget = self._build_component(
                                "Image",
                                {"image_url": image_url},
                                wrapper=wrapper,
                                wrap_with_key=True,
                            )
                            if image_widget:
                                widgets.append(image_widget)

                        built_children.append({"widgets": widgets})
                        logger.debug(
                            f"🎠 Built CarouselCard with {len(widgets)} widget(s) "
                            f"(transformed from title/text)"
                        )
                    elif "widgets" in card_params:
                        # Already has widgets array - use as-is
                        built_children.append({"widgets": card_params["widgets"]})
                        logger.debug(f"🎠 CarouselCard using provided widgets array")
                    else:
                        # Empty card - create placeholder
                        logger.debug(f"🎠 CarouselCard with no content, skipping")
                        continue
            else:
                # Skip generic child fallback - don't create "Item N" placeholders
                # This ensures only explicitly provided content is rendered
                logger.debug(
                    f"🎠 Skipping fallback for unknown child type in {component_name}"
                )
                continue

        if not built_children:
            logger.debug(f"🎠 No children built for {component_name}")
            return None

        result = {children_field: built_children}

        # Grid has additional params
        if component_name == "Grid":
            result["columnCount"] = min(3, len(built_children))

        final_result = {json_key: result}
        logger.debug(
            f"🎠 _build_container_generic returning: "
            f"{{'{json_key}': {{{repr(children_field)}: [{len(built_children)} items]}}}}"
        )
        return final_result

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
            # Default columns using wrapper components
            wrapper = self._get_wrapper()
            col1_widget = self._build_component(
                "TextParagraph",
                {"text": "Column 1"},
                wrapper=wrapper,
                wrap_with_key=True,
            )
            col2_widget = self._build_component(
                "TextParagraph",
                {"text": "Column 2"},
                wrapper=wrapper,
                wrap_with_key=True,
            )
            column_items = [
                {"widgets": [col1_widget] if col1_widget else []},
                {"widgets": [col2_widget] if col2_widget else []},
            ]

        return {"columns": {"columnItems": column_items}}

    # =========================================================================
    # NOTE: Carousel is built via the generic DSL flow using symbols
    # dynamically generated from ModuleWrapper (e.g., ◦[▲×N]).
    # The wrapper's CarouselCard component handles the structure.
    # =========================================================================

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
        """Universal component builder leveraging ModuleWrapper DAG and metadata.

        This method can build ANY component type by:
        1. Using get_cached_class() for fast L1 cache lookup
        2. Falling back to wrapper.search() for discovery
        3. Using wrapper metadata to validate and enrich params
        4. Supporting nested children with DAG validation
        5. Using create_card_component() for proper param filtering
        6. Auto-wrapping components using DAG relationships (e.g., Button → ButtonList)

        Args:
            component_name: Component type (e.g., "TextParagraph", "DecoratedText")
            params: Parameters for the component
            wrapper: Optional ModuleWrapper instance. If None, uses self._get_wrapper()
            wrap_with_key: If True, returns {jsonKey: innerDict}. If False, returns innerDict only.
            children: Optional pre-built child widgets (JSON dicts) to nest inside this component
            validate: If True, validate children against DAG relationships
            return_instance: If True, return the component instance instead of rendered JSON.
                           Use this when building nested structures (e.g., Card with Sections).
            child_instances: Optional component instances (not JSON) to pass to container components.
                           Use with return_instance=True for building full component hierarchies.
            auto_wrap: If True, automatically wrap component in required container using DAG.
                      Example: Button with target_parent=Section → ButtonList containing Button.
            target_parent: Target parent component name for auto_wrap. Required if auto_wrap=True.
                          The DAG will determine if wrapping is needed to make component valid
                          as a child of target_parent.

        Returns:
            - If return_instance=True: Component instance (for nesting in parent components)
            - If return_instance=False: Widget dict (wrapped or inner based on wrap_with_key)
            - None/fallback dict if build fails
        """
        wrapper = wrapper or self._get_wrapper()
        json_key = self._get_json_key(component_name)

        if not wrapper:
            # Fallback to simple dict if no wrapper
            inner = params.copy()
            if children:
                inner["widgets"] = children  # Generic children field
            return {json_key: inner} if wrap_with_key else inner

        # 0. Auto-wrap using DAG if requested
        # Example: Button with target_parent=Section → ButtonList(buttons=[Button])
        if auto_wrap and target_parent:
            required_wrapper = self._find_required_wrapper_via_dag(
                component_name, target_parent, wrapper
            )
            if required_wrapper and required_wrapper != component_name:
                logger.debug(
                    f"DAG auto-wrap: {component_name} → {required_wrapper} for {target_parent}"
                )
                # Build the inner component first
                inner_component = self._build_component(
                    component_name=component_name,
                    params=params,
                    wrapper=wrapper,
                    wrap_with_key=False,
                    children=children,
                    validate=validate,
                    return_instance=return_instance,
                    child_instances=child_instances,
                    auto_wrap=False,  # Prevent infinite recursion
                )
                if inner_component is None:
                    return None

                # Build the wrapper container with the inner component as child
                if return_instance:
                    # Return wrapper instance with inner as child_instance
                    return self._build_component(
                        component_name=required_wrapper,
                        params={},
                        wrapper=wrapper,
                        wrap_with_key=wrap_with_key,
                        return_instance=True,
                        child_instances=[inner_component],
                        auto_wrap=False,
                    )
                else:
                    # Build wrapper with inner as JSON child
                    wrapped_inner = (
                        {json_key: inner_component}
                        if not isinstance(inner_component, dict)
                        or json_key not in inner_component
                        else inner_component
                    )
                    return self._build_component(
                        component_name=required_wrapper,
                        params={},
                        wrapper=wrapper,
                        wrap_with_key=wrap_with_key,
                        children=[wrapped_inner],
                        validate=validate,
                        auto_wrap=False,
                    )

        # 1. Query wrapper metadata for component info
        is_empty = is_empty_component(component_name, wrapper)
        children_field = get_children_field(component_name, wrapper)

        # 2. Validate children against DAG if requested
        if validate and children and hasattr(wrapper, "can_contain"):
            for child in children:
                # Extract child component name from the widget dict
                child_key = (
                    next(iter(child.keys()), None) if isinstance(child, dict) else None
                )
                if child_key:
                    child_name = self._json_key_to_component_name(child_key)
                    if not wrapper.can_contain(component_name, child_name):
                        logger.warning(
                            f"DAG validation: {component_name} cannot contain {child_name}"
                        )

        # 3. Try cached class first (fast L1 memory cache)
        comp_class = wrapper.get_cached_class(component_name)

        # 4. Fallback to wrapper search if not in cache
        if not comp_class and hasattr(wrapper, "search"):
            try:
                results = wrapper.search(component_name, limit=1)
                if results:
                    result = results[0]
                    path = result.get("path") or result.get("component_path")
                    if path:
                        comp_class = wrapper.get_component_by_path(path)
            except Exception as e:
                logger.debug(f"Wrapper search failed for {component_name}: {e}")

        # 5. Handle empty components (no params needed)
        if is_empty:
            if return_instance and comp_class:
                try:
                    instance = wrapper.create_card_component(comp_class, {})
                    if instance:
                        return instance
                except Exception:
                    pass
            result = {json_key: {}}
            if children and children_field:
                result[json_key][children_field] = children
            return result if wrap_with_key else result.get(json_key, {})

        # 6. Build via wrapper class if found
        if comp_class:
            try:
                # Merge child_instances into params for container components
                build_params = params.copy()

                # Pre-process: Convert shorthand params to proper nested structures
                # Button/Chip: url -> on_click.open_link.url
                if component_name in ("Button", "Chip") and "url" in build_params:
                    url = build_params.pop("url")
                    if url and "on_click" not in build_params:
                        # Build OnClick -> OpenLink structure
                        try:
                            from card_framework.v2.widgets.on_click import OnClick
                            from card_framework.v2.widgets.open_link import OpenLink

                            build_params["on_click"] = OnClick(
                                open_link=OpenLink(url=url)
                            )
                        except ImportError:
                            # Fallback: pass as dict (will be handled by create_card_component)
                            build_params["on_click"] = {"open_link": {"url": url}}

                if child_instances:
                    # Map child instances to appropriate param names based on component type
                    if component_name == "Card":
                        # Card expects: header (CardHeader), sections (List[Section])
                        headers = [
                            c
                            for c in child_instances
                            if type(c).__name__ == "CardHeader"
                        ]
                        sections = [
                            c for c in child_instances if type(c).__name__ == "Section"
                        ]
                        if headers:
                            build_params["header"] = headers[0]
                        if sections:
                            build_params["sections"] = sections
                    elif component_name == "Section":
                        # Section expects: widgets (List[Widget])
                        build_params["widgets"] = child_instances
                    elif component_name in ("ButtonList", "ChipList"):
                        # Container expects: buttons/chips list
                        build_params[children_field or "buttons"] = child_instances
                    elif component_name == "Columns":
                        # Columns expects: columnItems (List[Column])
                        build_params["column_items"] = child_instances
                    elif component_name == "Grid":
                        # Grid expects: items (List[GridItem])
                        build_params["items"] = child_instances
                    elif component_name == "Carousel":
                        # Carousel expects: carouselCards (List[CarouselCard])
                        build_params["carousel_cards"] = child_instances

                instance = wrapper.create_card_component(comp_class, build_params)
                if instance:
                    # Pre-process: Set fields on the instance that the wrapper class may not handle
                    if component_name == "DecoratedText":
                        # Ensure wrapText is set on the instance
                        if hasattr(instance, "wrap_text"):
                            # wrap_text is the Python attribute name (snake_case)
                            instance.wrap_text = params.get(
                                "wrapText", params.get("wrap_text", True)
                            )

                    # Return instance if requested (for nesting in parent components)
                    if return_instance:
                        return instance

                    # Prefer render() for full widget output, fallback to to_dict()
                    if hasattr(instance, "render"):
                        rendered = instance.render()
                        converted = self._convert_to_camel_case(rendered)
                    elif hasattr(instance, "to_dict"):
                        rendered = instance.to_dict()
                        converted = self._convert_to_camel_case(rendered)
                    else:
                        converted = None

                    if converted:
                        # Handle already-wrapped vs inner dict
                        if json_key in converted and len(converted) == 1:
                            inner = converted[json_key]
                        else:
                            inner = converted

                        # Post-process: Add fields the wrapper class doesn't support
                        # but Google Chat API needs
                        if component_name == "DecoratedText":
                            # wrapText defaults to True unless explicitly False
                            inner["wrapText"] = params.get("wrapText", True)
                            # Handle icon -> startIcon conversion
                            if params.get("icon") and "startIcon" not in inner:
                                inner["startIcon"] = {
                                    "materialIcon": {"name": params["icon"]}
                                }
                            # Handle label fields
                            if params.get("top_label") and "topLabel" not in inner:
                                inner["topLabel"] = params["top_label"]
                            if (
                                params.get("bottom_label")
                                and "bottomLabel" not in inner
                            ):
                                inner["bottomLabel"] = params["bottom_label"]

                        # Add children if provided (JSON dicts, not instances)
                        if children and children_field:
                            # Unwrap array items (e.g., CarouselCard in carouselCards)
                            from gchat.card_builder.rendering import (
                                prepare_children_for_container,
                            )

                            inner[children_field] = prepare_children_for_container(
                                component_name, children, children_field
                            )

                        return {json_key: inner} if wrap_with_key else inner
            except Exception as e:
                logger.debug(f"Component build failed for {component_name}: {e}")

        # 7. Fallback: build from params directly
        inner = params.copy()
        if children and children_field:
            # Unwrap array items (e.g., CarouselCard in carouselCards)
            from gchat.card_builder.rendering import prepare_children_for_container

            inner[children_field] = prepare_children_for_container(
                component_name, children, children_field
            )
        elif children:
            # Use default children field based on component type
            default_field = "widgets" if component_name in ("Section",) else "buttons"
            inner[default_field] = children

        return {json_key: inner} if wrap_with_key else inner

    def _find_required_wrapper_via_dag(
        self,
        component: str,
        target_parent: str,
        wrapper: Optional["ComponentMetadataProvider"] = None,
    ) -> Optional[str]:
        """Find the required wrapper for a component to be valid in target_parent.

        Uses the DAG and registered metadata to determine if wrapping is needed:
        1. Check if component is a valid direct child of target_parent
        2. If not, check for explicit wrapper requirement
        3. If not found, try common naming pattern (Button → ButtonList)
        4. Fall back to DAG path-finding

        Args:
            component: Component to potentially wrap (e.g., "Button")
            target_parent: Target container (e.g., "Section")
            wrapper: ModuleWrapper with DAG capabilities

        Returns:
            Required wrapper component name, or None if no wrapping needed

        Example:
            >>> _find_required_wrapper_via_dag("Button", "Section")
            "ButtonList"  # Button needs ButtonList wrapper to go in Section
            >>> _find_required_wrapper_via_dag("DecoratedText", "Section")
            None  # DecoratedText can go directly in Section
        """
        wrapper = wrapper or self._get_wrapper()
        if not wrapper:
            return None

        # Get valid children for target_parent (uses DAG + widget types registry)
        valid_children = []
        if hasattr(wrapper, "get_valid_children_for_parent"):
            valid_children = wrapper.get_valid_children_for_parent(target_parent)

        # 1. Check if component is already a valid direct child (no wrapper needed)
        if component in valid_children:
            return None

        # Also check can_contain for direct containment
        if hasattr(wrapper, "can_contain"):
            if wrapper.can_contain(target_parent, component, direct_only=True):
                return None

        # 2. Check for explicit wrapper requirement registration
        if hasattr(wrapper, "get_required_wrapper"):
            explicit_wrapper = wrapper.get_required_wrapper(component)
            if explicit_wrapper:
                # Verify the wrapper is a valid child of target_parent
                if explicit_wrapper in valid_children:
                    return explicit_wrapper
                # Also check via can_contain
                if hasattr(wrapper, "can_contain"):
                    if wrapper.can_contain(
                        target_parent, explicit_wrapper, direct_only=False
                    ):
                        return explicit_wrapper

        # 3. Try common naming pattern: Component → ComponentList
        wrapper_name = f"{component}List"
        if wrapper_name in valid_children:
            return wrapper_name

        # 4. Use DAG path-finding as fallback
        if hasattr(wrapper, "get_path"):
            path = wrapper.get_path(target_parent, component)
            if path and len(path) >= 3:
                # Path is [target_parent, ..., wrapper, component]
                # The wrapper is the component right before the target
                intermediate = path[-2]  # Second-to-last is the direct parent
                if intermediate != target_parent and intermediate in valid_children:
                    return intermediate

        return None

    def _json_key_to_component_name(self, json_key: str) -> str:
        """Convert JSON key to component name.

        Delegates to gchat.card_builder.rendering.json_key_to_component_name().
        E.g., 'decoratedText' -> 'DecoratedText'
        """
        from gchat.card_builder.rendering import json_key_to_component_name

        return json_key_to_component_name(json_key)

    def build_component_tree(
        self,
        tree: Dict[str, Any],
        validate: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Build a complete component tree from a nested structure.

        This method recursively builds a component hierarchy using the ModuleWrapper
        DAG for validation and metadata queries. It's the high-level entry point
        for building any component structure.

        Args:
            tree: Nested structure like:
                {
                    "component": "Section",
                    "params": {"header": "My Section"},
                    "children": [
                        {"component": "DecoratedText", "params": {"text": "Hello"}},
                        {"component": "ButtonList", "children": [
                            {"component": "Button", "params": {"text": "Click", "url": "..."}}
                        ]}
                    ]
                }
            validate: If True, validate parent-child relationships against DAG

        Returns:
            Built widget dict in Google Chat format, or None if build fails.

        Example:
            tree = {
                "component": "Section",
                "children": [
                    {"component": "DecoratedText", "params": {"text": "Status: OK", "wrapText": True}},
                    {"component": "ButtonList", "children": [
                        {"component": "Button", "params": {"text": "Refresh", "url": "https://..."}}
                    ]}
                ]
            }
            result = builder.build_component_tree(tree)
            # Returns: {"section": {"widgets": [{"decoratedText": {...}}, {"buttonList": {...}}]}}
        """
        wrapper = self._get_wrapper()
        component_name = tree.get("component")
        params = tree.get("params", {}).copy()
        child_trees = tree.get("children", [])

        if not component_name:
            logger.warning("build_component_tree: missing 'component' key")
            return None

        # Recursively build children first
        built_children = []
        if child_trees:
            for child_tree in child_trees:
                child_widget = self.build_component_tree(child_tree, validate=validate)
                if child_widget:
                    built_children.append(child_widget)

        # Build this component with its children
        # (_build_component queries children_field internally via get_children_field)
        return self._build_component(
            component_name=component_name,
            params=params,
            wrapper=wrapper,
            wrap_with_key=True,
            children=built_children if built_children else None,
            validate=validate,
        )

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

    def _get_default_params(self, component_name: str, index: int = 0) -> Dict:
        """Get minimal default params for a component type. Delegates to card_builder.constants."""
        from gchat.card_builder.constants import get_default_params

        return get_default_params(component_name, index)

    # =========================================================================
    # GENERIC CHILD MAPPING (Nested DSL Support)
    # =========================================================================
    # These methods use ModuleWrapper relationship metadata to generically
    # map DSL children to parent component parameters.

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
            from gchat.card_builder.constants import FIELD_NAME_TO_JSON

            json_field_name = FIELD_NAME_TO_JSON.get(
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
                logger.debug(f"Mapped {child_name} to {parent_name}.{json_field_name}")

        return params

    def _resolve_child_params(
        self,
        child_name: str,
        explicit_params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve parameters for a child component using MAPPING-DRIVEN approach.

        Uses wrapper.get_context_resource() and component defaults mapping.
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
        """Convert snake_case keys to camelCase for Google Chat API.

        Delegates to gchat.card_builder.rendering.convert_to_camel_case().

        The wrapper renders snake_case (e.g., start_icon, on_click) but
        Google Chat API expects camelCase (e.g., startIcon, onClick).
        """
        from gchat.card_builder.rendering import convert_to_camel_case

        return convert_to_camel_case(data)

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
            return self._build_component(child_name, params, wrapper=wrapper)

        except Exception as e:
            logger.warning(f"Failed to build {child_name} via wrapper: {e}")
            return None

    def _build_button_via_wrapper(
        self, wrapper, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build a Button using wrapper component classes. Delegates to card_builder.rendering."""
        from gchat.card_builder.rendering import build_button_via_wrapper

        return build_button_via_wrapper(wrapper, params)

    def _build_icon_via_wrapper(
        self, wrapper, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build an Icon using wrapper component classes. Delegates to card_builder.rendering."""
        from gchat.card_builder.rendering import build_icon_via_wrapper

        return build_icon_via_wrapper(wrapper, params)

    def _build_switch_via_wrapper(
        self, wrapper, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build a SwitchControl. Delegates to card_builder.rendering."""
        from gchat.card_builder.rendering import build_switch_via_wrapper

        return build_switch_via_wrapper(wrapper, params)

    def _build_onclick_via_wrapper(
        self, wrapper, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build an OnClick. Delegates to card_builder.rendering."""
        from gchat.card_builder.rendering import build_onclick_via_wrapper

        return build_onclick_via_wrapper(wrapper, params)

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

            return generate_dsl_notation(card, wrapper.symbol_mapping)

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
    ) -> None:
        """
        Store the main card content pattern in Qdrant (fire-and-forget).

        Runs in background thread to avoid blocking card building.
        Use _store_card_pattern.sync() for synchronous testing.

        This stores ONLY the main card content (pattern_type="content"),
        NOT the feedback UI section which is stored separately.

        Args:
            card_id: Unique ID for this card
            description: Original card description (RAW, before Jinja processing)
            title: Card title
            structure_dsl: DSL structure if parsed
            card: The built card dict (without feedback section)
            description_rendered: Jinja-processed description (if different from raw)
            jinja_applied: Whether Jinja template processing was applied
        """
        if not ENABLE_FEEDBACK_BUTTONS:
            return  # Skip if feedback is disabled

        try:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()

            # Extract component paths from card structure
            component_paths = self._extract_component_paths(card)

            # Build instance params from card content
            # Stores BOTH raw and processed text for pattern reuse
            instance_params = {
                "title": title,
                "description": description[:500] if description else "",
                "dsl": structure_dsl,
                "component_count": len(component_paths),
                # Store Jinja-processed output for analytics/debugging
                "description_rendered": (
                    description_rendered[:500] if description_rendered else None
                ),
                # Track whether Jinja actually transformed the text
                "jinja_applied": jinja_applied,
            }

            # Extract style metadata from rendered description (or raw if no rendering)
            style_metadata = extract_style_metadata(description_rendered or description)

            # Also scan instance_params for any text fields with Jinja
            for key, value in instance_params.items():
                if isinstance(value, str) and "{{" in value:
                    additional_styles = extract_style_metadata(value)
                    for style_field in [
                        "jinja_filters",
                        "colors",
                        "semantic_styles",
                        "formatting",
                    ]:
                        style_metadata[style_field].extend(
                            additional_styles.get(style_field, [])
                        )

            # Deduplicate after merging
            for key in style_metadata:
                style_metadata[key] = list(set(style_metadata[key]))

            # Store style metadata with instance params
            instance_params["style_metadata"] = style_metadata

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
                if jinja_applied:
                    logger.debug(
                        f"   🎨 Jinja rendered: '{description[:30]}...' -> '{description_rendered[:30] if description_rendered else ''}...'"
                    )
                if style_metadata.get("semantic_styles") or style_metadata.get(
                    "formatting"
                ):
                    logger.debug(f"   🎨 Style metadata: {style_metadata}")

        except Exception as e:
            # Don't fail card generation if pattern storage fails
            logger.warning(f"⚠️ Failed to store card pattern: {e}")

    @fire_and_forget
    def _store_feedback_ui_pattern(
        self,
        card_id: str,
        feedback_section: Dict[str, Any],
    ) -> None:
        """
        Store the feedback UI section pattern in Qdrant (fire-and-forget).

        Runs in background thread to avoid blocking card building.
        Use _store_feedback_ui_pattern.sync() for synchronous testing.

        This stores the randomly generated feedback UI (pattern_type="feedback_ui"),
        allowing learning of which feedback layouts work best.

        Args:
            card_id: Unique ID for this card (links content + feedback_ui patterns)
            feedback_section: The feedback section dict with _feedback_assembly metadata
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
            # Map camelCase JSON keys to PascalCase component names
            json_key_to_component = {
                "textParagraph": "TextParagraph",
                "decoratedText": "DecoratedText",
                "buttonList": "ButtonList",
                "chipList": "ChipList",
                "columns": "Columns",
                "divider": "Divider",
            }
            component_paths = []
            for widget in feedback_section.get("widgets", []):
                for key in widget.keys():
                    if key in json_key_to_component:
                        component_paths.append(json_key_to_component[key])

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
    # GENERIC FEEDBACK WIDGET BUILDER (Config-Driven)
    # Uses wrapper components and .render() for all feedback widgets
    # -------------------------------------------------------------------------

    def _build_feedback_widget(
        self,
        component_name: str,
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build a feedback widget using the unified _build_component method.

        Thin wrapper that ensures wrap_with_key=True for feedback widgets,
        which need the full {jsonKey: innerDict} format.

        Args:
            component_name: Component type (e.g., "TextParagraph", "DecoratedText")
            params: Parameters for the component

        Returns:
            Widget dict in Google Chat format: {jsonKey: innerDict}
        """
        return self._build_component(component_name, params, wrap_with_key=True)

    # -------------------------------------------------------------------------
    # TEXT COMPONENT BUILDERS
    # Each uses _build_feedback_widget with wrapper components
    # -------------------------------------------------------------------------

    def _style_feedback_keyword(self, keyword: str, style: str) -> str:
        """Apply styling to a feedback keyword using HTML.

        Delegates to gchat.card_builder.jinja_styling.style_keyword().
        """
        from gchat.card_builder.jinja_styling import style_keyword

        return style_keyword(keyword, style, FEEDBACK_COLORS)

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

    def _build_text_feedback(self, text_type: str, text: str, **kwargs) -> Dict:
        """Unified config-driven text builder - replaces 5 individual text methods.

        Uses TEXT_CONFIGS to determine component type and formatting.

        Args:
            text_type: Key in TEXT_CONFIGS (e.g., "text_paragraph", "decorated_text")
            text: Text content to display
            **kwargs: Additional params (e.g., label for decorated_text_labeled)

        Returns:
            Widget dict (e.g., {"textParagraph": {"text": "..."}})
        """
        config = TEXT_CONFIGS.get(text_type)
        if not config:
            # Fallback to simple text paragraph
            config = TEXT_CONFIGS["text_paragraph"]

        # Handle direct dict components (chip_text)
        if config.get("direct_dict"):
            return {"chipList": {"chips": [{"label": text, "enabled": False}]}}

        # Apply text formatting if configured
        format_fn = config.get("format_text")
        formatted_text = format_fn(text) if format_fn else text

        # Build params
        component_name = config["component"]
        params = {"text": formatted_text}
        if config.get("wrap_text"):
            params["wrap_text"] = True
        if config.get("top_label") or kwargs.get("label"):
            params["top_label"] = kwargs.get("label") or config.get("top_label")

        # Build widget
        widget = self._build_feedback_widget(component_name, params)

        # Add icon if configured
        if config.get("add_random_icon") and widget and "decoratedText" in widget:
            icon_name = random.choice(FEEDBACK_MATERIAL_ICONS)
            widget["decoratedText"]["startIcon"] = self._build_start_icon(icon_name)

        return widget

    # Convenience wrappers for backward compatibility with _create_feedback_section
    def _text_paragraph(self, text: str, **_kwargs) -> Dict:
        return self._build_text_feedback("text_paragraph", text)

    def _text_decorated(self, text: str, **_kwargs) -> Dict:
        return self._build_text_feedback("decorated_text", text)

    def _text_decorated_icon(self, text: str, **_kwargs) -> Dict:
        return self._build_text_feedback("decorated_text_icon", text)

    def _text_decorated_labeled(
        self, text: str, label: str = "Feedback", **_kwargs
    ) -> Dict:
        return self._build_text_feedback("decorated_text_labeled", text, label=label)

    def _text_chip(self, text: str, **_kwargs) -> Dict:
        return self._build_text_feedback("chip_text", text)

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
                # Get Button and OnClick classes via cache for fast retrieval
                Button = wrapper.get_cached_class("Button")
                OnClick = wrapper.get_cached_class("OnClick")
                OpenLink = wrapper.get_cached_class("OpenLink")

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
                # Get Chip and OnClick classes via cache for fast retrieval
                Chip = wrapper.get_cached_class("Chip")
                OnClick = wrapper.get_cached_class("OnClick")
                OpenLink = wrapper.get_cached_class("OpenLink")

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

    def _build_clickable_feedback(
        self, handler_type: str, card_id: str, feedback_type: str
    ) -> Dict:
        """Unified config-driven click handler - replaces 7 individual methods.

        Uses CLICK_CONFIGS to determine widget structure, icons, and behavior.

        Args:
            handler_type: Key in CLICK_CONFIGS (e.g., "button_list", "star_rating")
            card_id: Card ID for callback URL
            feedback_type: Feedback type for callback URL

        Returns:
            Widget dict (e.g., {"buttonList": {"buttons": [...]}})
        """
        config = CLICK_CONFIGS.get(handler_type)
        if not config:
            # Fallback to basic button list
            config = CLICK_CONFIGS["button_list"]

        widget_key = config["widget"]
        items_key = config["items_key"]
        use_chips = config.get("use_chips", False)
        btn_type = config.get("button_type") or random.choice(BUTTON_TYPES)

        items = []

        if config.get("binary", True):
            # Binary positive/negative feedback
            pos_label = random.choice(POSITIVE_LABELS)
            neg_label = random.choice(NEGATIVE_LABELS)
            pos_url = self._make_callback_url(card_id, "positive", feedback_type)
            neg_url = self._make_callback_url(card_id, "negative", feedback_type)

            # Determine icons
            pos_icon = config.get("pos_icon")
            neg_icon = config.get("neg_icon")
            pos_icon_url = None
            neg_icon_url = None

            if config.get("pos_icon_source"):
                # Random icon from list
                icon_list = globals().get(config["pos_icon_source"], [])
                pos_icon = random.choice(icon_list) if icon_list else None
            if config.get("neg_icon_source"):
                icon_list = globals().get(config["neg_icon_source"], [])
                neg_icon = random.choice(icon_list) if icon_list else None
            if config.get("pos_icon_url_source"):
                url_list = globals().get(config["pos_icon_url_source"], [])
                pos_icon_url = random.choice(url_list) if url_list else None
            if config.get("neg_icon_url_source"):
                url_list = globals().get(config["neg_icon_url_source"], [])
                neg_icon_url = random.choice(url_list) if url_list else None

            if use_chips:
                items = [
                    self._build_feedback_chip_item(pos_label, pos_url),
                    self._build_feedback_chip_item(neg_label, neg_url),
                ]
            else:
                items = [
                    self._build_feedback_button_item(
                        pos_label,
                        pos_url,
                        material_icon=pos_icon,
                        icon_url=pos_icon_url,
                        button_type=btn_type,
                    ),
                    self._build_feedback_button_item(
                        neg_label,
                        neg_url,
                        material_icon=neg_icon,
                        icon_url=neg_icon_url,
                        button_type=btn_type,
                    ),
                ]
        else:
            # Multi-option ratings (star, emoji, etc.)
            ratings = config.get("ratings", [])
            for icon_name, label, rating_value in ratings:
                url = self._make_callback_url(card_id, rating_value, feedback_type)
                btn = self._build_feedback_button_item(
                    label, url, material_icon=icon_name, button_type=btn_type
                )
                items.append(btn)

        return {widget_key: {items_key: items}}

    # Convenience wrappers for backward compatibility with _create_feedback_section
    def _click_button_list(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        return self._build_clickable_feedback("button_list", card_id, feedback_type)

    def _click_chip_list(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        return self._build_clickable_feedback("chip_list", card_id, feedback_type)

    def _click_icon_buttons(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        return self._build_clickable_feedback("icon_buttons", card_id, feedback_type)

    def _click_icon_buttons_alt(
        self, card_id: str, feedback_type: str, **_kwargs
    ) -> Dict:
        return self._build_clickable_feedback(
            "icon_buttons_alt", card_id, feedback_type
        )

    def _click_url_image_buttons(
        self, card_id: str, feedback_type: str, **_kwargs
    ) -> Dict:
        return self._build_clickable_feedback(
            "url_image_buttons", card_id, feedback_type
        )

    def _click_star_rating(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        return self._build_clickable_feedback("star_rating", card_id, feedback_type)

    def _click_emoji_rating(self, card_id: str, feedback_type: str, **_kwargs) -> Dict:
        return self._build_clickable_feedback("emoji_rating", card_id, feedback_type)

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
            decorated_widget["decoratedText"]["startIcon"] = self._build_start_icon(
                icon_name
            )
            decorated_widget["decoratedText"]["button"] = (
                self._build_feedback_button_item(
                    pos_label, pos_url, button_type=btn_type
                )
            )

        # Build separate negative button list using wrapper
        neg_button = self._build_feedback_button_item(
            neg_label, neg_url, button_type=btn_type
        )
        wrapper = self._get_wrapper()
        button_list_widget = self._build_component(
            "ButtonList",
            {},
            wrapper=wrapper,
            wrap_with_key=True,
        )
        # Fallback if wrapper build fails or need to insert button
        if button_list_widget and "buttonList" in button_list_widget:
            button_list_widget["buttonList"]["buttons"] = [neg_button]
        else:
            button_list_widget = {"buttonList": {"buttons": [neg_button]}}

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
            decorated_widget["decoratedText"]["button"] = (
                self._build_feedback_button_item(
                    pos_label, pos_url, button_type=btn_type
                )
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

        # Build buttons using helper and wrapper
        buttons = [
            self._build_feedback_button_item(pos_label, pos_url, button_type=btn_type),
            self._build_feedback_button_item(neg_label, neg_url, button_type=btn_type),
        ]
        wrapper = self._get_wrapper()
        button_list_widget = self._build_component(
            "ButtonList",
            {},
            wrapper=wrapper,
            wrap_with_key=True,
        )
        # Insert buttons into the widget
        if button_list_widget and "buttonList" in button_list_widget:
            button_list_widget["buttonList"]["buttons"] = buttons
        else:
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

    def _build_feedback_layout(
        self,
        layout_type: str,
        content_widgets: List[Dict],
        form_widgets: List[Dict],
        content_first: bool,
    ) -> List[Dict]:
        """Unified config-driven layout builder - replaces 3 individual layout methods.

        Uses LAYOUT_CONFIGS to determine layout behavior.

        Args:
            layout_type: Key in LAYOUT_CONFIGS (e.g., "sequential", "with_divider")
            content_widgets: Content feedback widgets
            form_widgets: Form/action feedback widgets
            content_first: Whether content should appear first

        Returns:
            Combined list of widgets in the specified layout
        """
        config = LAYOUT_CONFIGS.get(layout_type, {})

        # Handle compact layout (groups by type)
        if config.get("group_by_type"):
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

        # Standard sequential layout with optional divider
        first, second = (
            (content_widgets, form_widgets)
            if content_first
            else (form_widgets, content_widgets)
        )

        if config.get("add_divider"):
            return first + [{"divider": {}}] + second
        return first + second

    # Convenience wrappers for backward compatibility
    def _layout_sequential(
        self, content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
    ) -> List[Dict]:
        return self._build_feedback_layout(
            "sequential", content_widgets, form_widgets, content_first
        )

    def _layout_with_divider(
        self, content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
    ) -> List[Dict]:
        return self._build_feedback_layout(
            "with_divider", content_widgets, form_widgets, content_first
        )

    def _layout_compact(
        self, content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
    ) -> List[Dict]:
        return self._build_feedback_layout(
            "compact", content_widgets, form_widgets, content_first
        )

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
        chips: Optional[List[Dict]] = None,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        items: Optional[List[Dict]] = None,
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

        # Clean metadata before returning (Google Chat rejects underscore-prefixed keys)
        return self._clean_card_metadata(card)

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
