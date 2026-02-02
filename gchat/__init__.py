"""
Google Chat MCP Tools Package
"""

import logging

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Material Icons - complete set of valid Google Material Design icon names
from gchat.material_icons import (
    ADD_ICONS,
    ARROW_ICONS,
    CHECK_ICONS,
    DELETE_ICONS,
    EDIT_ICONS,
    # Color utilities
    ICON_COLORS,
    KEYBOARD_ICONS,
    MATERIAL_ICONS,
    REMOVE_ICONS,
    # Semantic mappings
    SEMANTIC_ICONS,
    SETTINGS_ICONS,
    STAR_ICONS,
    create_icon_button,
    create_icon_button_list,
    create_icon_widget,
    create_material_icon,
    get_icon_color,
    get_icons_by_prefix,
    get_icons_containing,
    get_semantic_icon,
    hex_to_color,
    is_valid_icon,
    # Utilities
    suggest_icons,
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
