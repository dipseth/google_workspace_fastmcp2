"""
Email feedback prompts, labels, and text styling constants.

Mirrors gchat/card_builder/feedback/prompts.py but adapted for
email context — shorter prompts, email-appropriate styling.
"""

from typing import Dict, List, Tuple

# =============================================================================
# EMAIL FEEDBACK PROMPTS
# =============================================================================
# Use {keyword} placeholder for styled keyword insertion.
# Prompts are shorter than card prompts since email real estate is limited.

CONTENT_FEEDBACK_PROMPTS: List[Tuple[str, str]] = [
    ("Was this {keyword} helpful?", "email"),
    ("Did the {keyword} look right?", "content"),
    ("Were the {keyword} accurate?", "details"),
    ("Was this {keyword} useful?", "information"),
    ("Did this {keyword} answer your question?", "response"),
]

LAYOUT_FEEDBACK_PROMPTS: List[Tuple[str, str]] = [
    ("Was the {keyword} easy to read?", "formatting"),
    ("Did the {keyword} look good?", "layout"),
    ("Was the {keyword} clear?", "structure"),
    ("Did the {keyword} work well?", "design"),
]

# =============================================================================
# TEXT STYLING
# =============================================================================
# Email-safe styling — uses inline CSS since email clients strip <style> tags.
# These are simpler than card styles since email HTML support is more limited.

FEEDBACK_TEXT_STYLES: List[str] = [
    "bold",  # <b>keyword</b>
    "italic",  # <i>keyword</i>
    "underline",  # <u>keyword</u>
    "color_blue",  # <span style="color:#4285f4">keyword</span>
    "color_green",  # <span style="color:#34a853">keyword</span>
    "bold_blue",  # <b><span style="color:#4285f4">keyword</span></b>
]

FEEDBACK_COLORS: Dict[str, str] = {
    "success": "#34a853",
    "warning": "#fbbc05",
    "info": "#4285f4",
    "muted": "#9e9e9e",
    "error": "#ea4335",
}

# =============================================================================
# BUTTON LABELS
# =============================================================================

POSITIVE_LABELS: List[str] = [
    "Yes, helpful",
    "Looks good",
    "Thumbs up",
    "Accurate",
    "Yes",
]

NEGATIVE_LABELS: List[str] = [
    "Not helpful",
    "Needs work",
    "Thumbs down",
    "Inaccurate",
    "No",
]

# Emoji variants (used when button style supports unicode)
POSITIVE_EMOJI_LABELS: List[str] = [
    "\U0001f44d Yes",
    "\U0001f44d Helpful",
    "\u2705 Looks good",
    "\U0001f44d Accurate",
]

NEGATIVE_EMOJI_LABELS: List[str] = [
    "\U0001f44e No",
    "\U0001f44e Not helpful",
    "\u274c Needs work",
    "\U0001f44e Inaccurate",
]

# =============================================================================
# FOOTER-STYLE FEEDBACK TEXT
# =============================================================================
# For compact footer integration — plain text with links.

FOOTER_FEEDBACK_TEMPLATES: List[str] = [
    "Was this helpful? {positive_link} | {negative_link}",
    "Rate this email: {positive_link} or {negative_link}",
    "Feedback: {positive_link} / {negative_link}",
]


def style_keyword(keyword: str, style: str) -> str:
    """Apply inline styling to a keyword for email HTML.

    Args:
        keyword: The word to style.
        style: One of FEEDBACK_TEXT_STYLES.

    Returns:
        HTML-styled keyword string.
    """
    if style == "bold":
        return f"<b>{keyword}</b>"
    elif style == "italic":
        return f"<i>{keyword}</i>"
    elif style == "underline":
        return f"<u>{keyword}</u>"
    elif style == "color_blue":
        return f'<span style="color:#4285f4">{keyword}</span>'
    elif style == "color_green":
        return f'<span style="color:#34a853">{keyword}</span>'
    elif style == "bold_blue":
        return f'<b><span style="color:#4285f4">{keyword}</span></b>'
    return keyword


__all__ = [
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
]
