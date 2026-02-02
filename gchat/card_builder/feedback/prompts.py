"""
Feedback prompts, labels, and text styling constants.
"""

from typing import Dict, List, Tuple


# Feedback prompts - use {keyword} placeholder for styled keyword insertion
CONTENT_FEEDBACK_PROMPTS: List[Tuple[str, str]] = [
    ("Was the {keyword} correct?", "content"),
    ("Did the {keyword} look right?", "data"),
    ("Were the {keyword} accurate?", "values"),
    ("Was the {keyword} helpful?", "information"),
    ("Were the {keyword} correct?", "details"),
]

FORM_FEEDBACK_PROMPTS: List[Tuple[str, str]] = [
    ("Was the {keyword} correct?", "layout"),
    ("Did the {keyword} look good?", "structure"),
    ("Was the {keyword} appropriate?", "formatting"),
    ("Did the {keyword} work well?", "arrangement"),
    ("Was the {keyword} suitable?", "design"),
]

# Text styling options for feedback keywords (rendered as HTML)
# These mirror the Jinja filters: success_text, warning_text, muted_text, color
FEEDBACK_TEXT_STYLES: List[str] = [
    "bold",           # <b>keyword</b> (classic)
    "success",        # <font color="#34a853">keyword</font> (green)
    "warning",        # <font color="#fbbc05">keyword</font> (yellow)
    "info",           # <font color="#4285f4">keyword</font> (blue)
    "muted",          # <font color="#9e9e9e">keyword</font> (gray)
    "bold_success",   # <b><font color="#34a853">keyword</font></b>
    "bold_info",      # <b><font color="#4285f4">keyword</font></b>
]

# Color mappings (matching SEMANTIC_COLORS from styling_filters.py)
FEEDBACK_COLORS: Dict[str, str] = {
    "success": "#34a853",
    "warning": "#fbbc05",
    "info": "#4285f4",
    "muted": "#9e9e9e",
    "error": "#ea4335",
}

POSITIVE_LABELS: List[str] = ["👍 Good", "👍 Yes", "👍 Correct", "✅ Looks good", "👍 Accurate"]
NEGATIVE_LABELS: List[str] = ["👎 Bad", "👎 No", "👎 Wrong", "❌ Needs work", "👎 Not quite"]


__all__ = [
    "CONTENT_FEEDBACK_PROMPTS",
    "FORM_FEEDBACK_PROMPTS",
    "FEEDBACK_TEXT_STYLES",
    "FEEDBACK_COLORS",
    "POSITIVE_LABELS",
    "NEGATIVE_LABELS",
]
