"""
Custom Jinja2 filters for FastMCP template processing.

This module provides a collection of custom Jinja2 filters specifically designed
for working with FastMCP resources, data manipulation, and template processing.

Available filter categories:
- Date filters: Date and time formatting
- Data filters: Property extraction and data manipulation  
- JSON filters: JSON processing and pretty-printing
- Drive filters: Google Drive URL formatting

Usage:
    from middleware.filters import register_all_filters
    
    # Register all filters with a Jinja2 environment
    register_all_filters(jinja_env)
"""

from .date_filters import format_date_filter, strftime_filter
from .data_filters import extract_filter, safe_get_filter, map_list_filter, map_attribute_filter
from .json_filters import json_pretty_filter
from .drive_filters import format_drive_image_url_filter


def register_all_filters(jinja_env):
    """
    Register all custom filters with a Jinja2 environment.
    
    Args:
        jinja_env: Jinja2 Environment instance to register filters with
        
    Side Effects:
        - Adds custom filters to jinja_env.filters dictionary
        - Filters become available in all templates rendered by the environment
    """
    if not jinja_env:
        return
        
    # Register all custom filters
    jinja_env.filters.update({
        'extract': extract_filter,
        'safe_get': safe_get_filter,
        'format_date': format_date_filter,
        'json_pretty': json_pretty_filter,
        'strftime': strftime_filter,
        'map_list': map_list_filter,
        'map_attr': map_attribute_filter,
        'format_drive_image_url': format_drive_image_url_filter,
    })


__all__ = [
    'register_all_filters',
    'format_date_filter',
    'strftime_filter',
    'extract_filter',
    'safe_get_filter', 
    'map_list_filter',
    'map_attribute_filter',
    'json_pretty_filter',
    'format_drive_image_url_filter'
]