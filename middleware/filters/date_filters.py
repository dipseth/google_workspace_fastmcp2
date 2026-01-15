"""
Date and time formatting filters for Jinja2 templates.

Provides custom filters for formatting dates, timestamps, and handling various
date string formats in template processing.
"""

from datetime import datetime
from typing import Any


def format_date_filter(date_input: Any, format_str: str = "%Y-%m-%d %H:%M") -> str:
    """
    Format a date string or datetime object.

    Handles both datetime objects and ISO format date strings, converting
    them to the specified format string.

    Args:
        date_input: Date to format (datetime object or ISO string)
        format_str: Python strftime format string (default: '%Y-%m-%d %H:%M')

    Returns:
        Formatted date string, or original input if formatting fails

    Usage in templates:
        {{ timestamp | format_date }}
        {{ created_at | format_date('%B %d, %Y') }}
        {{ user.last_login | format_date('%Y-%m-%d at %I:%M %p') }}
    """
    try:
        # Handle datetime objects directly
        if isinstance(date_input, datetime):
            return date_input.strftime(format_str)
        elif isinstance(date_input, str):
            # Try to parse ISO format first
            try:
                dt = datetime.fromisoformat(date_input.replace("Z", "+00:00"))
                return dt.strftime(format_str)
            except ValueError:
                return date_input
        return str(date_input)
    except Exception:
        return str(date_input)


def strftime_filter(date_input: Any, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format a date using strftime (Jinja2 filter).

    Similar to format_date_filter but with a different default format and
    support for callable date inputs (like the now() function).

    Args:
        date_input: Date to format (datetime, string, or callable)
        format_str: Python strftime format string (default: '%Y-%m-%d %H:%M:%S')

    Returns:
        Formatted date string, or original input if formatting fails

    Usage in templates:
        {{ now() | strftime }}
        {{ timestamp | strftime('%A, %B %d, %Y') }}
        {{ user_created | strftime('%m/%d/%y') }}
    """
    try:
        # Handle datetime objects directly
        if isinstance(date_input, datetime):
            return date_input.strftime(format_str)
        elif isinstance(date_input, str):
            # Try to parse ISO format first
            try:
                dt = datetime.fromisoformat(date_input.replace("Z", "+00:00"))
                return dt.strftime(format_str)
            except ValueError:
                return date_input
        elif callable(date_input):
            # Handle function calls like now()
            result = date_input()
            if isinstance(result, datetime):
                return result.strftime(format_str)
            return str(result)
        return str(date_input)
    except Exception:
        return str(date_input)
