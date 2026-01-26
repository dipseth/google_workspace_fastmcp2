"""
Custom Jinja2 filters for FastMCP template processing.

This module provides a collection of custom Jinja2 filters specifically designed
for working with FastMCP resources, data manipulation, and template processing.

Available filter categories:
- Date filters: Date and time formatting
- Data filters: Property extraction and data manipulation
- JSON filters: JSON processing and pretty-printing
- Drive filters: Google Drive URL formatting
- Styling filters: Universal color, formatting, badges (Jinja2/Nunjucks compatible)

Usage:
    from middleware.filters import register_all_filters

    # Register all filters with a Jinja2 environment
    register_all_filters(jinja_env)

Styling filters work in both Jinja2 (Python) and Nunjucks (JavaScript):
    {{ "Success!" | color('success') }}
    {{ sale_price | price(original_price) }}
    {{ "NEW" | badge('info') }}
"""

from .data_filters import (
    extract_filter,
    map_attribute_filter,
    map_list_filter,
    safe_get_filter,
)
from .date_filters import format_date_filter, strftime_filter
from .drive_filters import format_drive_image_url_filter
from .json_filters import json_pretty_filter
from .styling_filters import (
    COLOR_SCHEMES,
    SEMANTIC_COLORS,
    # Filter registry
    STYLING_FILTERS,
    # Color cycling/component styling
    ColorCycler,
    ComponentStyler,
    alternating_color_filter,
    badge_filter,
    bold_filter,
    # Core filters
    color_filter,
    create_styler_for_template,
    get_color,
    italic_filter,
    link_filter,
    price_filter,
    status_icon_filter,
    strike_filter,
)


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
    jinja_env.filters.update(
        {
            # Data filters
            "extract": extract_filter,
            "safe_get": safe_get_filter,
            "map_list": map_list_filter,
            "map_attr": map_attribute_filter,
            # Date filters
            "format_date": format_date_filter,
            "strftime": strftime_filter,
            # JSON filters
            "json_pretty": json_pretty_filter,
            # Drive filters
            "format_drive_image_url": format_drive_image_url_filter,
            # Styling filters (Jinja2/Nunjucks compatible)
            **STYLING_FILTERS,
        }
    )


__all__ = [
    # Registration
    "register_all_filters",
    # Date filters
    "format_date_filter",
    "strftime_filter",
    # Data filters
    "extract_filter",
    "safe_get_filter",
    "map_list_filter",
    "map_attribute_filter",
    # JSON filters
    "json_pretty_filter",
    # Drive filters
    "format_drive_image_url_filter",
    # Styling filters (Jinja2/Nunjucks compatible)
    "STYLING_FILTERS",
    "SEMANTIC_COLORS",
    "COLOR_SCHEMES",
    "color_filter",
    "price_filter",
    "badge_filter",
    "status_icon_filter",
    "bold_filter",
    "italic_filter",
    "strike_filter",
    "link_filter",
    "get_color",
    # Color cycling/component styling
    "ColorCycler",
    "ComponentStyler",
    "create_styler_for_template",
    "alternating_color_filter",
]
