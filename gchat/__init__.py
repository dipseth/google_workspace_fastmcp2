"""
Google Chat MCP Tools Package
"""

import logging

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Material Icons - complete set of valid Google Material Design icon names
from gchat.material_icons import (
    MATERIAL_ICONS,
    is_valid_icon,
    get_icons_by_prefix,
    get_icons_containing,
    ARROW_ICONS,
    KEYBOARD_ICONS,
    CHECK_ICONS,
    ADD_ICONS,
    REMOVE_ICONS,
    EDIT_ICONS,
    DELETE_ICONS,
    STAR_ICONS,
    SETTINGS_ICONS,
    # Semantic mappings
    SEMANTIC_ICONS,
    get_semantic_icon,
    # Utilities
    suggest_icons,
    create_material_icon,
    create_icon_widget,
    # Color utilities
    ICON_COLORS,
    hex_to_color,
    get_icon_color,
    create_icon_button,
    create_icon_button_list,
)

# Main exports - lazy imports to avoid circular dependencies
__all__ = [
    # SmartCardBuilder
    "SmartCardBuilder",
    "get_smart_card_builder",
    # Material Icons - Core
    "MATERIAL_ICONS",
    "is_valid_icon",
    "get_icons_by_prefix",
    "get_icons_containing",
    # Material Icons - Categories
    "ARROW_ICONS",
    "KEYBOARD_ICONS",
    "CHECK_ICONS",
    "ADD_ICONS",
    "REMOVE_ICONS",
    "EDIT_ICONS",
    "DELETE_ICONS",
    "STAR_ICONS",
    "SETTINGS_ICONS",
    # Material Icons - Semantic
    "SEMANTIC_ICONS",
    "get_semantic_icon",
    # Material Icons - Utilities
    "suggest_icons",
    "create_material_icon",
    "create_icon_widget",
    # Material Icons - Colors
    "ICON_COLORS",
    "hex_to_color",
    "get_icon_color",
    "create_icon_button",
    "create_icon_button_list",
]
