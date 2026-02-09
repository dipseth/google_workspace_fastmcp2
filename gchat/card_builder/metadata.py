"""
Component metadata accessors - query wrapper or fall back to static dicts.

These functions query the ModuleWrapper (via ComponentMetadataProvider protocol)
for component metadata. If wrapper is None, fall back to static dicts.
"""

from typing import Dict, Optional, Set, Tuple

from adapters.module_wrapper.types import ComponentName

# =============================================================================
# GENERIC COMPONENT CONFIGURATION (Fallback Defaults)
# =============================================================================
# These mappings are FALLBACKS when ModuleWrapper is not available.
# When wrapper is available, use wrapper.get_context_resource(), etc.
# The wrapper's metadata is the SSoT (set in card_framework_wrapper.py).

# Context consumers: component_name -> (context_key, index_key)
# FALLBACK - Use wrapper.get_context_resource() when available
_CONTEXT_CONSUMERS_FALLBACK: Dict[ComponentName, Tuple[str, str]] = {
    "Button": ("buttons", "_button_index"),
    "Chip": ("chips", "_chip_index"),
    "DecoratedText": ("content_texts", "_text_index"),
    "TextParagraph": ("content_texts", "_text_index"),
    "CarouselCard": ("carousel_cards", "_carousel_card_index"),
    "GridItem": ("grid_items", "_grid_item_index"),
}

# Container components: component_name -> children_field
# FALLBACK - Use wrapper.get_children_field() when available
_CONTAINER_CHILDREN_FALLBACK: Dict[ComponentName, str] = {
    "ButtonList": "buttons",
    "Grid": "items",
    "ChipList": "chips",
    "Columns": "columnItems",
    "Column": "widgets",
    "Section": "widgets",
    # Carousel hierarchy (Google Chat API specific)
    "Carousel": "carouselCards",
    "CarouselCard": "widgets",  # via NestedWidget
    "NestedWidget": "widgets",
}

# Child component mapping for containers: what child type each container expects
# FALLBACK - Use wrapper.get_container_child_type() when available
_CONTAINER_CHILD_TYPE_FALLBACK: Dict[ComponentName, ComponentName] = {
    "ButtonList": "Button",
    "Grid": "GridItem",
    "ChipList": "Chip",
    "Columns": "Column",
    # Carousel hierarchy
    "Carousel": "CarouselCard",
    "CarouselCard": "NestedWidget",
    "NestedWidget": "TextParagraph",  # NestedWidget supports TextParagraph, ButtonList, Image
}

# Form components that require a 'name' field
# FALLBACK - Use wrapper.is_form_component() when available
_FORM_COMPONENTS_FALLBACK: Set[ComponentName] = {
    "TextInput",
    "DateTimePicker",
    "SelectionInput",
    "SwitchControl",
}

# Components with no content (just structure)
# FALLBACK - Use wrapper.is_empty_component() when available
_EMPTY_COMPONENTS_FALLBACK: Set[ComponentName] = {"Divider", "CollapseControl"}


# =============================================================================
# COMPONENT METADATA ACCESSORS (Query Wrapper or Fall Back)
# =============================================================================

# Import the protocol for type checking
try:
    from adapters.module_wrapper import ComponentMetadataProvider
except ImportError:
    ComponentMetadataProvider = None  # type: ignore


def get_context_resource(
    component: ComponentName, wrapper: Optional["ComponentMetadataProvider"] = None
) -> Optional[Tuple[str, str]]:
    """Get context resource for a component (wrapper SSoT, fallback to dict)."""
    if wrapper is not None:
        result = wrapper.get_context_resource(component)
        if result:
            return result
    return _CONTEXT_CONSUMERS_FALLBACK.get(component)


def get_children_field(
    container: ComponentName, wrapper: Optional["ComponentMetadataProvider"] = None
) -> Optional[str]:
    """Get children field for a container (wrapper SSoT, fallback to dict)."""
    if wrapper is not None:
        result = wrapper.get_children_field(container)
        if result:
            return result
    return _CONTAINER_CHILDREN_FALLBACK.get(container)


def get_container_child_type(
    container: ComponentName, wrapper: Optional["ComponentMetadataProvider"] = None
) -> Optional[ComponentName]:
    """Get expected child type for a container (wrapper SSoT, fallback to dict)."""
    if wrapper is not None:
        result = wrapper.get_container_child_type(container)
        if result:
            return result
    return _CONTAINER_CHILD_TYPE_FALLBACK.get(container)


def is_form_component(
    component: ComponentName, wrapper: Optional["ComponentMetadataProvider"] = None
) -> bool:
    """Check if component is a form component (wrapper SSoT, fallback to set)."""
    if wrapper is not None:
        return wrapper.is_form_component(component)
    return component in _FORM_COMPONENTS_FALLBACK


def is_empty_component(
    component: ComponentName, wrapper: Optional["ComponentMetadataProvider"] = None
) -> bool:
    """Check if component is empty (wrapper SSoT, fallback to set)."""
    if wrapper is not None:
        return wrapper.is_empty_component(component)
    return component in _EMPTY_COMPONENTS_FALLBACK


__all__ = [
    # Accessor functions
    "get_context_resource",
    "get_children_field",
    "get_container_child_type",
    "is_form_component",
    "is_empty_component",
    # Fallback dicts (for testing/debugging)
    "_CONTEXT_CONSUMERS_FALLBACK",
    "_CONTAINER_CHILDREN_FALLBACK",
    "_CONTAINER_CHILD_TYPE_FALLBACK",
    "_FORM_COMPONENTS_FALLBACK",
    "_EMPTY_COMPONENTS_FALLBACK",
]
