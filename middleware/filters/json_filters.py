"""
JSON processing filters for Jinja2 templates.

Provides filters for JSON formatting, pretty-printing, and data serialization
in template processing.
"""

import json
from typing import Any


def json_pretty_filter(data: Any, indent: int = 2) -> str:
    """
    Pretty print JSON data.
    
    Converts Python data structures to formatted JSON strings with configurable
    indentation. Handles serialization of complex objects gracefully.
    
    Args:
        data: Data to serialize to JSON
        indent: Number of spaces for indentation (default: 2)
        
    Returns:
        Pretty-formatted JSON string, or string representation if serialization fails
        
    Usage in templates:
        {{ response_data | json_pretty }}
        {{ config | json_pretty(4) }}
        {{ user_data | json_pretty(0) }}  # Compact JSON
    """
    try:
        return json.dumps(data, indent=indent, default=str)
    except Exception:
        return str(data)