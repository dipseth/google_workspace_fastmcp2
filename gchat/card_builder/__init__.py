"""
Card Builder Package - Modular card building with DSL + Qdrant embeddings.

This package provides:
- SmartCardBuilderV2: Main card builder with DSL + embedding support
- PreparedPattern: Deferred rendering for card patterns
- DynamicFeedbackBuilder: DAG-aware feedback widget generation
- Metadata accessors: wrapper-first component metadata queries
- Style utilities: Jinja style extraction and processing

Usage:
    from gchat.card_builder import SmartCardBuilderV2

    builder = SmartCardBuilderV2()
    card = builder.build(
        description="§[δ×2, Ƀ[ᵬ×2]] Dashboard card",
        title="My Dashboard",
    )
"""

import os

# Feature flag for feedback buttons
ENABLE_FEEDBACK_BUTTONS = os.getenv("ENABLE_CARD_FEEDBACK", "true").lower() == "true"

# =============================================================================
# MAIN BUILDER
# =============================================================================
# SmartCardBuilderV2 is the main card builder class.
# All builder code now lives in card_builder/builder_v2.py.

from gchat.card_builder.builder_v2 import (
    SmartCardBuilderV2,
    build_card,
    get_smart_card_builder,
    reset_builder,
    suggest_dsl_for_params,
)

# Legacy alias
SmartCardBuilder = SmartCardBuilderV2

# =============================================================================
# PREPARED PATTERNS
# =============================================================================
from gchat.card_builder.constants import (
    COMPONENT_PARAMS,
    COMPONENT_PATHS,
    DEFAULT_COMPONENT_PARAMS,
    FEEDBACK_DETECTION_PATTERNS,
    FIELD_NAME_TO_JSON,
    get_default_params,
)
from gchat.card_builder.dsl import (
    WIDGET_JSON_KEYS,
    extract_component_paths,
    # Note: suggest_dsl_for_params is imported from smart_card_builder for backwards compatibility
    generate_dsl_notation,
)

# =============================================================================
# FEEDBACK
# =============================================================================
from gchat.card_builder.feedback import (
    BUTTON_TYPES,
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
# UTILITIES
# =============================================================================
from gchat.card_builder.jinja_styling import (
    DEFAULT_SEMANTIC_COLORS,
    ERROR_KEYWORDS,
    SUCCESS_KEYWORDS,
    WARNING_KEYWORDS,
    apply_pattern_styles,
    apply_style_to_text,
    apply_styles,
    apply_styles_recursively,
    extract_style_metadata,
    # Text formatting
    format_text_for_chat,
    get_style_for_text,
    # Style application
    has_explicit_styles,
    style_keyword,
)
from gchat.card_builder.metadata import (
    get_children_field,
    get_container_child_type,
    get_context_resource,
    is_empty_component,
    is_form_component,
)
from gchat.card_builder.prepared_pattern import (
    InputMappingReport,
    PreparedPattern,
    prepare_pattern,
    prepare_pattern_from_dsl,
)
from gchat.card_builder.rendering import (
    # Specialized component builders
    build_button_via_wrapper,
    build_icon_via_wrapper,
    # Icon building
    build_material_icon,
    build_onclick_via_wrapper,
    build_start_icon,
    build_switch_via_wrapper,
    convert_to_camel_case,
    # Key conversion utilities
    get_json_key,
    json_key_to_component_name,
    prepare_children_for_container,
    should_unwrap_children,
    # Array item handling
    unwrap_array_item,
    unwrap_array_items,
)
from gchat.card_builder.search import (
    extract_paths_from_pattern,
    extract_style_metadata_from_pattern,
    find_pattern_with_styles,
    has_style_metadata,
)
from gchat.card_builder.utils import fire_and_forget
from gchat.card_builder.validation import (
    clean_card_metadata,
    has_feedback,
    make_callback_url,
    validate_content,
)

# Note: SmartCardBuilderV2 and SmartCardBuilder are imported directly above
# gchat.smart_card_builder has been moved to gchat/delete_later/


__all__ = [
    # Main builder class (lazy loaded)
    "SmartCardBuilderV2",
    "SmartCardBuilder",  # Legacy alias (lazy loaded)
    # Factory functions
    "get_smart_card_builder",
    "reset_builder",
    "build_card",
    "suggest_dsl_for_params",
    # Feature flag
    "ENABLE_FEEDBACK_BUTTONS",
    # Prepared patterns
    "PreparedPattern",
    "InputMappingReport",
    "prepare_pattern",
    "prepare_pattern_from_dsl",
    # Feedback builder
    "DynamicFeedbackBuilder",
    "get_dynamic_feedback_builder",
    # Feedback prompts
    "CONTENT_FEEDBACK_PROMPTS",
    "FORM_FEEDBACK_PROMPTS",
    "FEEDBACK_TEXT_STYLES",
    "FEEDBACK_COLORS",
    "POSITIVE_LABELS",
    "NEGATIVE_LABELS",
    # Feedback icons
    "POSITIVE_MATERIAL_ICONS",
    "NEGATIVE_MATERIAL_ICONS",
    "FEEDBACK_MATERIAL_ICONS",
    "POSITIVE_ICONS",
    "NEGATIVE_ICONS",
    "FEEDBACK_ICONS",
    "POSITIVE_IMAGE_URLS",
    "NEGATIVE_IMAGE_URLS",
    # Feedback component registries
    "TEXT_COMPONENTS",
    "CLICKABLE_COMPONENTS",
    "DUAL_COMPONENTS",
    "LAYOUT_WRAPPERS",
    "BUTTON_TYPES",
    "SECTION_STYLES",
    "CLICK_CONFIGS",
    "TEXT_CONFIGS",
    "LAYOUT_CONFIGS",
    # Style utilities
    "extract_style_metadata",
    "apply_styles",
    "style_keyword",
    "DEFAULT_SEMANTIC_COLORS",
    # Style application
    "has_explicit_styles",
    "get_style_for_text",
    "apply_style_to_text",
    "apply_pattern_styles",
    "apply_styles_recursively",
    "SUCCESS_KEYWORDS",
    "ERROR_KEYWORDS",
    "WARNING_KEYWORDS",
    # Text formatting
    "format_text_for_chat",
    # Metadata accessors
    "get_context_resource",
    "get_children_field",
    "get_container_child_type",
    "is_form_component",
    "is_empty_component",
    # Constants
    "COMPONENT_PARAMS",
    "COMPONENT_PATHS",
    "FEEDBACK_DETECTION_PATTERNS",
    "DEFAULT_COMPONENT_PARAMS",
    "get_default_params",
    "FIELD_NAME_TO_JSON",
    # Decorator
    "fire_and_forget",
    # Rendering utilities - key conversion
    "get_json_key",
    "json_key_to_component_name",
    "convert_to_camel_case",
    # Rendering utilities - array handling
    "unwrap_array_item",
    "unwrap_array_items",
    "should_unwrap_children",
    "prepare_children_for_container",
    # Rendering utilities - icon building
    "build_material_icon",
    "build_start_icon",
    # Rendering utilities - specialized component builders
    "build_button_via_wrapper",
    "build_icon_via_wrapper",
    "build_switch_via_wrapper",
    "build_onclick_via_wrapper",
    # DSL utilities
    "WIDGET_JSON_KEYS",
    "extract_component_paths",
    "generate_dsl_notation",
    # Search utilities
    "extract_paths_from_pattern",
    "extract_style_metadata_from_pattern",
    "has_style_metadata",
    "find_pattern_with_styles",
    # Validation utilities
    "has_feedback",
    "clean_card_metadata",
    "validate_content",
    "make_callback_url",
]
