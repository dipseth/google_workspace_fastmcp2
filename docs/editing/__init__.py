"""
Google Docs editing operations module.

This module provides advanced document editing capabilities including:
- Line-based content insertion
- Regex search and replace operations
- Content appending
- Full document replacement

Organized into separate concerns for maintainability.
"""

from .line_parser import parse_document_lines, find_line_position
from .regex_operations import apply_regex_replacements
from .edit_applier import apply_edit_config

__all__ = [
    "parse_document_lines",
    "find_line_position",
    "apply_regex_replacements",
    "apply_edit_config",
]
