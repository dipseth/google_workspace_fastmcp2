"""
Email feedback subpackage — Dynamic email feedback button generation.

Mirrors gchat/card_builder/feedback/ but produces MJML-rendered email
blocks with signed redirect URLs instead of Google Chat widget dicts
with onClick callbacks.
"""

from gmail.email_feedback.components import (
    BUTTON_STYLES,
    CLICKABLE_COMPONENTS,
    DUAL_COMPONENTS,
    LAYOUT_WRAPPERS,
    TEXT_COMPONENTS,
)
from gmail.email_feedback.dynamic import (
    EmailFeedbackBuilder,
    get_email_feedback_builder,
)
from gmail.email_feedback.prompts import (
    CONTENT_FEEDBACK_PROMPTS,
    FEEDBACK_COLORS,
    FEEDBACK_TEXT_STYLES,
    FOOTER_FEEDBACK_TEMPLATES,
    LAYOUT_FEEDBACK_PROMPTS,
    NEGATIVE_EMOJI_LABELS,
    NEGATIVE_LABELS,
    POSITIVE_EMOJI_LABELS,
    POSITIVE_LABELS,
    style_keyword,
)
from gmail.email_feedback.urls import (
    DEFAULT_TTL_SECONDS,
    generate_feedback_url,
    reset_consumed_tokens,
    verify_feedback_url,
)

__all__ = [
    # Dynamic feedback builder
    "EmailFeedbackBuilder",
    "get_email_feedback_builder",
    # Prompts and labels
    "CONTENT_FEEDBACK_PROMPTS",
    "LAYOUT_FEEDBACK_PROMPTS",
    "FEEDBACK_TEXT_STYLES",
    "FEEDBACK_COLORS",
    "POSITIVE_LABELS",
    "NEGATIVE_LABELS",
    "POSITIVE_EMOJI_LABELS",
    "NEGATIVE_EMOJI_LABELS",
    "FOOTER_FEEDBACK_TEMPLATES",
    "style_keyword",
    # Component categories
    "TEXT_COMPONENTS",
    "CLICKABLE_COMPONENTS",
    "DUAL_COMPONENTS",
    "LAYOUT_WRAPPERS",
    "BUTTON_STYLES",
    # URL signing
    "generate_feedback_url",
    "verify_feedback_url",
    "reset_consumed_tokens",
    "DEFAULT_TTL_SECONDS",
]
