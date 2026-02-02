"""
Feedback subpackage - Dynamic feedback widget generation.
"""

from gchat.card_builder.feedback.dynamic import (
    DynamicFeedbackBuilder,
    get_dynamic_feedback_builder,
)

from gchat.card_builder.feedback.prompts import (
    CONTENT_FEEDBACK_PROMPTS,
    FORM_FEEDBACK_PROMPTS,
    FEEDBACK_TEXT_STYLES,
    FEEDBACK_COLORS,
    POSITIVE_LABELS,
    NEGATIVE_LABELS,
)

from gchat.card_builder.feedback.icons import (
    POSITIVE_MATERIAL_ICONS,
    NEGATIVE_MATERIAL_ICONS,
    FEEDBACK_MATERIAL_ICONS,
    POSITIVE_ICONS,
    NEGATIVE_ICONS,
    FEEDBACK_ICONS,
    POSITIVE_IMAGE_URLS,
    NEGATIVE_IMAGE_URLS,
)

from gchat.card_builder.feedback.components import (
    TEXT_COMPONENTS,
    CLICKABLE_COMPONENTS,
    DUAL_COMPONENTS,
    LAYOUT_WRAPPERS,
    BUTTON_TYPES,
    SECTION_STYLES,
)

from gchat.card_builder.feedback.registries import (
    CLICK_CONFIGS,
    TEXT_CONFIGS,
    LAYOUT_CONFIGS,
)


__all__ = [
    # Dynamic feedback builder
    "DynamicFeedbackBuilder",
    "get_dynamic_feedback_builder",
    # Prompts and labels
    "CONTENT_FEEDBACK_PROMPTS",
    "FORM_FEEDBACK_PROMPTS",
    "FEEDBACK_TEXT_STYLES",
    "FEEDBACK_COLORS",
    "POSITIVE_LABELS",
    "NEGATIVE_LABELS",
    # Icons
    "POSITIVE_MATERIAL_ICONS",
    "NEGATIVE_MATERIAL_ICONS",
    "FEEDBACK_MATERIAL_ICONS",
    "POSITIVE_ICONS",
    "NEGATIVE_ICONS",
    "FEEDBACK_ICONS",
    "POSITIVE_IMAGE_URLS",
    "NEGATIVE_IMAGE_URLS",
    # Component categories
    "TEXT_COMPONENTS",
    "CLICKABLE_COMPONENTS",
    "DUAL_COMPONENTS",
    "LAYOUT_WRAPPERS",
    "BUTTON_TYPES",
    "SECTION_STYLES",
    # Config registries
    "CLICK_CONFIGS",
    "TEXT_CONFIGS",
    "LAYOUT_CONFIGS",
]
