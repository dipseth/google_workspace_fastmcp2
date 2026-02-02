"""
Material icons and image URLs for feedback widgets.
"""

from typing import List


# =============================================================================
# MATERIAL ICONS FOR FEEDBACK (using materialIcon, not knownIcon)
# =============================================================================
# These use the full Material Design icon set (2,209 icons) via wrapper's Icon.MaterialIcon
# Format: {"materialIcon": {"name": "icon_name"}} instead of {"knownIcon": "ICON"}

# Positive feedback icons - expressive approval indicators
POSITIVE_MATERIAL_ICONS: List[str] = [
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
NEGATIVE_MATERIAL_ICONS: List[str] = [
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
FEEDBACK_MATERIAL_ICONS: List[str] = [
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
POSITIVE_ICONS: List[str] = ["STAR", "CONFIRMATION_NUMBER", "TICKET"]
NEGATIVE_ICONS: List[str] = ["BOOKMARK", "DESCRIPTION", "EMAIL"]
# FEEDBACK_ICONS: Verified working in BOTH buttons AND decoratedText.startIcon
FEEDBACK_ICONS: List[str] = ["STAR", "BOOKMARK", "DESCRIPTION", "EMAIL"]

# Validated URL images (tested and confirmed working in Google Chat)
POSITIVE_IMAGE_URLS: List[str] = [
    "https://www.gstatic.com/images/icons/material/system/2x/check_circle_black_24dp.png",  # Checkmark
    "https://ui-avatars.com/api/?name=Y&background=4caf50&color=fff&size=24&bold=true",  # Green Y
    "https://placehold.co/24x24/4caf50/4caf50.png",  # Green square
]
NEGATIVE_IMAGE_URLS: List[str] = [
    "https://www.gstatic.com/images/icons/material/system/2x/cancel_black_24dp.png",  # X mark
    "https://ui-avatars.com/api/?name=N&background=f44336&color=fff&size=24&bold=true",  # Red N
    "https://placehold.co/24x24/f44336/f44336.png",  # Red square
]


__all__ = [
    "POSITIVE_MATERIAL_ICONS",
    "NEGATIVE_MATERIAL_ICONS",
    "FEEDBACK_MATERIAL_ICONS",
    "POSITIVE_ICONS",
    "NEGATIVE_ICONS",
    "FEEDBACK_ICONS",
    "POSITIVE_IMAGE_URLS",
    "NEGATIVE_IMAGE_URLS",
]
