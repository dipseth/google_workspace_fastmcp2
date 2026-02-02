"""
Rendering utilities for card components.

This module provides helpers for building and rendering card components,
including proper handling of array items and nested structures, as well as
key conversion utilities for the Google Chat API.
"""

from typing import Any, Dict, List, Optional

from adapters.module_wrapper.types import ComponentName, JsonDict

# =============================================================================
# KEY CONVERSION UTILITIES
# =============================================================================


def get_json_key(component_name: ComponentName) -> str:
    """Get camelCase JSON key from component name.

    Derived directly from component name - no hardcoded mapping needed.

    Args:
        component_name: PascalCase component name (e.g., "DecoratedText")

    Returns:
        camelCase JSON key (e.g., "decoratedText")

    Examples:
        >>> get_json_key("DecoratedText")
        "decoratedText"
        >>> get_json_key("ButtonList")
        "buttonList"
    """
    if not component_name:
        return ""
    return component_name[0].lower() + component_name[1:]


# Mapping from JSON keys to component names for reverse lookup
_JSON_KEY_TO_COMPONENT = {
    "decoratedText": "DecoratedText",
    "textParagraph": "TextParagraph",
    "buttonList": "ButtonList",
    "chipList": "ChipList",
    "image": "Image",
    "divider": "Divider",
    "grid": "Grid",
    "columns": "Columns",
    "carousel": "Carousel",
    "carouselCard": "CarouselCard",
    "textInput": "TextInput",
    "selectionInput": "SelectionInput",
    "dateTimePicker": "DateTimePicker",
    "gridItem": "GridItem",
    "column": "Column",
    "button": "Button",
    "chip": "Chip",
}


def json_key_to_component_name(json_key: str) -> ComponentName:
    """Convert JSON key to component name.

    Args:
        json_key: camelCase JSON key (e.g., "decoratedText")

    Returns:
        PascalCase component name (e.g., "DecoratedText")

    Examples:
        >>> json_key_to_component_name("decoratedText")
        "DecoratedText"
        >>> json_key_to_component_name("buttonList")
        "ButtonList"
    """
    return _JSON_KEY_TO_COMPONENT.get(json_key, json_key.title().replace("_", ""))


def convert_to_camel_case(data: Any) -> Any:
    """Convert snake_case keys to camelCase for Google Chat API.

    The wrapper renders snake_case (e.g., start_icon, on_click) but
    Google Chat API expects camelCase (e.g., startIcon, onClick).

    Keys starting with underscore (e.g., _card_id, _feedback_assembly) are
    internal metadata and are stripped from the output.

    Args:
        data: Dict, list, or primitive value

    Returns:
        Same structure with snake_case keys converted to camelCase

    Examples:
        >>> convert_to_camel_case({"start_icon": {"known_icon": "STAR"}})
        {"startIcon": {"knownIcon": "STAR"}}

        >>> convert_to_camel_case({"_internal": "skip", "text": "keep"})
        {"text": "keep"}
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # Skip internal metadata keys (start with underscore)
            if key.startswith("_"):
                continue
            # Convert snake_case to camelCase
            parts = key.split("_")
            camel_key = parts[0] + "".join(word.capitalize() for word in parts[1:])
            result[camel_key] = convert_to_camel_case(value)
        return result
    elif isinstance(data, list):
        return [convert_to_camel_case(item) for item in data]
    else:
        return data


# JSON keys for components that are array items (should NOT have wrapper key)
# When these components appear as children of a container, they should be unwrapped
_ARRAY_ITEM_JSON_KEYS = {
    "carouselCard",  # Items in Carousel.carouselCards
    "gridItem",  # Items in Grid.items
    "column",  # Items in Columns.columnItems
    "button",  # Items in ButtonList.buttons
    "chip",  # Items in ChipList.chips
}


def unwrap_array_item(item: JsonDict) -> JsonDict:
    """
    Unwrap an array item that was built with wrap_with_key=True.

    When building component trees, child components are built with wrapper keys
    like {"carouselCard": {"widgets": [...]}}, but when placed in array fields
    (like carouselCards), they should be just {"widgets": [...]}.

    Args:
        item: Widget dict possibly wrapped with JSON key

    Returns:
        Unwrapped item if it was wrapped with an array item key, otherwise unchanged

    Example:
        >>> unwrap_array_item({"carouselCard": {"widgets": [...]}})
        {"widgets": [...]}

        >>> unwrap_array_item({"decoratedText": {"text": "..."}})
        {"decoratedText": {"text": "..."}}  # Not an array item, unchanged
    """
    if not isinstance(item, dict):
        return item

    # Check if item has exactly one key that's an array item key
    if len(item) == 1:
        key = next(iter(item.keys()))
        if key in _ARRAY_ITEM_JSON_KEYS:
            return item[key]

    return item


def unwrap_array_items(items: List[JsonDict]) -> List[JsonDict]:
    """
    Unwrap multiple array items.

    Args:
        items: List of widget dicts

    Returns:
        List with array items unwrapped
    """
    return [unwrap_array_item(item) for item in items]


def should_unwrap_children(container: ComponentName, children_field: str) -> bool:
    """
    Determine if children should be unwrapped for a given container.

    Array fields contain items that should NOT have wrapper keys.

    Args:
        container: Container component name (e.g., "Carousel")
        children_field: The field name for children (e.g., "carouselCards")

    Returns:
        True if children should be unwrapped
    """
    # Fields that contain array items (not widgets)
    array_fields = {
        "carouselCards",  # Carousel -> CarouselCard[]
        "items",  # Grid -> GridItem[]
        "columnItems",  # Columns -> Column[]
        "buttons",  # ButtonList -> Button[]
        "chips",  # ChipList -> Chip[]
    }
    return children_field in array_fields


def prepare_children_for_container(
    container: ComponentName,
    children: List[JsonDict],
    children_field: str,
) -> List[JsonDict]:
    """
    Prepare children for insertion into a container's children field.

    This handles unwrapping array items so they don't have redundant
    wrapper keys when placed in array fields.

    Args:
        container: Container component name
        children: List of built child widgets
        children_field: The field name where children will be placed

    Returns:
        Children list ready for the container

    Example:
        >>> children = [{"carouselCard": {"widgets": [...]}}, ...]
        >>> prepare_children_for_container("Carousel", children, "carouselCards")
        [{"widgets": [...]}, ...]  # Wrapper keys stripped
    """
    if should_unwrap_children(container, children_field):
        return unwrap_array_items(children)
    return children


# =============================================================================
# ICON BUILDING
# =============================================================================

import logging

logger = logging.getLogger(__name__)


def build_material_icon(
    icon_name: str,
    fill: bool = None,
    weight: int = None,
) -> JsonDict:
    """Build a materialIcon dict using the wrapper's Icon.MaterialIcon class.

    This uses the card_framework wrapper components to ensure consistency
    and proper rendering of Material Design icons (2,209+ available icons).

    Args:
        icon_name: Material icon name (e.g., "thumb_up", "check_circle")
        fill: Optional fill style (True for filled, False for outlined)
        weight: Optional weight (100-700, default varies by icon)

    Returns:
        Dict in format: {"materialIcon": {"name": "icon_name", ...}}

    Example:
        >>> build_material_icon("thumb_up")
        {"materialIcon": {"name": "thumb_up"}}
        >>> build_material_icon("check_circle", fill=True, weight=400)
        {"materialIcon": {"name": "check_circle", "fill": True, "weight": 400}}
    """
    try:
        from card_framework.v2.widgets.icon import Icon

        # Build MaterialIcon using wrapper component
        mi = Icon.MaterialIcon(name=icon_name, fill=fill, weight=weight)
        icon = Icon(material_icon=mi)

        # Use to_dict() for proper rendering
        icon_dict = icon.to_dict()

        # Convert to camelCase for Google Chat API
        if "material_icon" in icon_dict:
            icon_dict["materialIcon"] = icon_dict.pop("material_icon")

        return icon_dict

    except Exception as e:
        logger.debug(f"Wrapper MaterialIcon failed, using fallback: {e}")
        # Fallback to manual dict construction
        result: Dict[str, Any] = {"materialIcon": {"name": icon_name}}
        if fill is not None:
            result["materialIcon"]["fill"] = fill
        if weight is not None:
            result["materialIcon"]["weight"] = weight
        return result


def build_start_icon(icon_name: str) -> JsonDict:
    """Build a startIcon dict for decoratedText using materialIcon.

    Args:
        icon_name: Material icon name (e.g., "feedback", "rate_review")

    Returns:
        Dict in format: {"materialIcon": {"name": "icon_name"}}

    Example:
        >>> build_start_icon("feedback")
        {"materialIcon": {"name": "feedback"}}
    """
    return build_material_icon(icon_name)


# =============================================================================
# SPECIALIZED COMPONENT BUILDERS (via wrapper)
# =============================================================================
# These builders handle components with special requirements (enums, nested objects)
# They take wrapper as parameter for proper component class access.


def build_button_via_wrapper(wrapper, params: JsonDict) -> Optional[JsonDict]:
    """Build a Button using wrapper component classes.

    Args:
        wrapper: ModuleWrapper instance for component access
        params: Button parameters (text, url)

    Returns:
        Button dict in Google Chat format, or None if build fails
    """
    # Get component classes via cache for fast retrieval
    Button = wrapper.get_cached_class("Button")
    OnClick = wrapper.get_cached_class("OnClick")
    OpenLink = wrapper.get_cached_class("OpenLink")

    if not all([Button, OnClick, OpenLink]):
        logger.debug("Could not get Button/OnClick/OpenLink classes from cache")
        return None

    try:
        # Build OnClick with OpenLink
        url = params.get("url", "https://example.com")
        open_link = OpenLink(url=url)
        on_click = OnClick(open_link=open_link)

        # Build Button
        button = Button(
            text=params.get("text", "Button"),
            on_click=on_click,
        )

        # Render and convert to camelCase
        if hasattr(button, "to_dict"):
            rendered = button.to_dict()
            return convert_to_camel_case(rendered)

    except Exception as e:
        logger.debug(f"build_button_via_wrapper failed: {e}")

    return None


def build_icon_via_wrapper(wrapper, params: JsonDict) -> Optional[JsonDict]:
    """Build an Icon using wrapper component classes.

    Args:
        wrapper: ModuleWrapper instance for component access
        params: Icon parameters (known_icon or icon_url)

    Returns:
        Icon dict in Google Chat format, or None if build fails
    """
    # Use cached class for fast retrieval
    Icon = wrapper.get_cached_class("Icon")

    if not Icon:
        logger.debug("Could not get Icon class from cache")
        return None

    try:
        # Get the KnownIcon enum
        if hasattr(Icon, "KnownIcon"):
            known_icon_name = params.get("known_icon", "STAR")
            # Try to get the enum value
            known_icon_enum = getattr(
                Icon.KnownIcon, known_icon_name, Icon.KnownIcon.STAR
            )
            icon = Icon(known_icon=known_icon_enum)

            if hasattr(icon, "to_dict"):
                rendered = icon.to_dict()
                return convert_to_camel_case(rendered)
    except Exception as e:
        logger.debug(f"Failed to create Icon with enum: {e}")

    # Fallback: try with icon_url if provided
    if params.get("icon_url"):
        try:
            icon = Icon(icon_url=params["icon_url"])
            if hasattr(icon, "to_dict"):
                rendered = icon.to_dict()
                return convert_to_camel_case(rendered)
        except Exception as e:
            logger.debug(f"Failed to create Icon with URL: {e}")

    return None


def build_switch_via_wrapper(wrapper, params: JsonDict) -> Optional[JsonDict]:
    """Build a SwitchControl using wrapper component classes.

    Args:
        wrapper: ModuleWrapper instance for component access
        params: SwitchControl parameters (name, selected)

    Returns:
        SwitchControl dict in Google Chat format, or None if build fails
    """
    # Use cached class for fast retrieval
    SwitchControl = wrapper.get_cached_class("SwitchControl")

    if not SwitchControl:
        logger.debug("Could not get SwitchControl class")
        return None

    try:
        switch = SwitchControl(
            name=params.get("name", "switch"),
            selected=params.get("selected", False),
        )

        if hasattr(switch, "to_dict"):
            rendered = switch.to_dict()
            return convert_to_camel_case(rendered)
    except Exception as e:
        logger.debug(f"Failed to create SwitchControl: {e}")

    return None


def build_onclick_via_wrapper(wrapper, params: JsonDict) -> Optional[JsonDict]:
    """Build an OnClick using wrapper component classes.

    Args:
        wrapper: ModuleWrapper instance for component access
        params: OnClick parameters (url)

    Returns:
        OnClick dict in Google Chat format, or None if build fails
    """
    # Use cached classes for fast retrieval
    OnClick = wrapper.get_cached_class("OnClick")
    OpenLink = wrapper.get_cached_class("OpenLink")

    if not all([OnClick, OpenLink]):
        logger.debug("Could not get OnClick/OpenLink classes from cache")
        return None

    try:
        if params.get("url"):
            open_link = OpenLink(url=params["url"])
            on_click = OnClick(open_link=open_link)

            if hasattr(on_click, "to_dict"):
                rendered = on_click.to_dict()
                return convert_to_camel_case(rendered)
    except Exception as e:
        logger.debug(f"Failed to create OnClick: {e}")

    return None


__all__ = [
    # Key conversion utilities
    "get_json_key",
    "json_key_to_component_name",
    "convert_to_camel_case",
    # Array item handling
    "unwrap_array_item",
    "unwrap_array_items",
    "should_unwrap_children",
    "prepare_children_for_container",
    # Icon building
    "build_material_icon",
    "build_start_icon",
    # Specialized component builders
    "build_button_via_wrapper",
    "build_icon_via_wrapper",
    "build_switch_via_wrapper",
    "build_onclick_via_wrapper",
]
