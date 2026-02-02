"""
Context consumption utilities for card building.

This module provides functions for consuming resources from a shared context
during card building (buttons, texts, chips, carousel cards).
"""

from typing import Any, Dict, Optional, Tuple

from adapters.module_wrapper.types import ComponentName, JsonDict
from gchat.card_builder.metadata import get_context_resource


def consume_from_context(
    component_name: ComponentName,
    context: JsonDict,
    wrapper: Optional[Any] = None,
) -> JsonDict:
    """Consume resource from context for a component type.

    Uses wrapper.get_context_resource() (SSoT) or fallback dict.
    Returns params populated from context, or empty dict.
    Also records consumption in InputMappingReport if present in context.

    Args:
        component_name: Component type (e.g., "Button", "DecoratedText")
        context: Shared context with resources and indices
        wrapper: Optional ModuleWrapper for metadata lookups

    Returns:
        Dict with params consumed from context
    """
    # Query wrapper (SSoT) or fallback to dict
    resource_info = get_context_resource(component_name, wrapper)
    if not resource_info:
        return {}

    context_key, index_key = resource_info
    resources = context.get(context_key, [])
    current_index = context.get(index_key, 0)

    params: JsonDict = {}
    mapping_report = context.get("_mapping_report")

    if current_index < len(resources):
        resource = resources[current_index]
        if isinstance(resource, dict):
            # For content_texts, use 'styled' key (from Content DSL) or 'text' key (explicit)
            if context_key == "content_texts":
                params["text"] = resource.get("styled") or resource.get("text", "")
                # Pass through icon, top_label, bottom_label, wrapText for DecoratedText
                if resource.get("icon"):
                    params["icon"] = resource["icon"]
                if resource.get("top_label"):
                    params["top_label"] = resource["top_label"]
                if resource.get("bottom_label"):
                    params["bottom_label"] = resource["bottom_label"]
                # Always include wrapText (default True for multi-line content)
                params["wrapText"] = resource.get("wrapText", True)
                # Record the consumption in mapping report
                if mapping_report:
                    value = str(resource.get("styled", resource.get("content", "")))
                    mapping_report.record(
                        input_type="text",
                        index=current_index,
                        value=value,
                        component=component_name,
                        field_name="text",
                    )
            # For buttons, extract button-specific fields
            elif context_key == "buttons":
                params["text"] = resource.get("text", "Button")
                if resource.get("url"):
                    params["url"] = resource["url"]
                # Pass through icon (material icon name like "add_circle")
                if resource.get("icon"):
                    params["icon"] = resource["icon"]
                # Record the consumption in mapping report
                if mapping_report:
                    value = str(resource.get("text", "Button"))
                    mapping_report.record(
                        input_type="button",
                        index=current_index,
                        value=value,
                        component=component_name,
                        field_name="button",
                    )
            # For chips, extract chip-specific fields (label, url, icon)
            elif context_key == "chips":
                # Chips use 'label' but accept 'text' as alias
                params["label"] = resource.get("label") or resource.get("text", "Chip")
                if resource.get("url"):
                    params["url"] = resource["url"]
                # Pass through icon (material icon name)
                if resource.get("icon"):
                    params["icon"] = resource["icon"]
                # Record the consumption in mapping report
                if mapping_report:
                    value = str(resource.get("label") or resource.get("text", "Chip"))
                    mapping_report.record(
                        input_type="chip",
                        index=current_index,
                        value=value,
                        component=component_name,
                        field_name="chip",
                    )
            # For carousel cards, extract card-specific fields
            elif context_key == "carousel_cards":
                # Pass through all carousel card fields
                params["title"] = resource.get("title", f"Card {current_index + 1}")
                if resource.get("subtitle"):
                    params["subtitle"] = resource["subtitle"]
                if resource.get("image_url"):
                    params["image_url"] = resource["image_url"]
                if resource.get("text"):
                    params["text"] = resource["text"]
                if resource.get("buttons"):
                    params["buttons"] = resource["buttons"]
                if resource.get("footer_buttons"):
                    params["footer_buttons"] = resource["footer_buttons"]
                # Record the consumption in mapping report
                if mapping_report:
                    mapping_report.record(
                        input_type="carousel_card",
                        index=current_index,
                        value=resource.get("title", ""),
                        component=component_name,
                        field_name="carousel_card",
                    )
        context[index_key] = current_index + 1
    else:
        # No more resources - don't use placeholder, let caller handle missing text
        # Button and Chip still need labels for UX
        if component_name == "Button":
            params["text"] = f"Button {current_index + 1}"
        elif component_name == "Chip":
            params["label"] = f"Chip {current_index + 1}"
        elif component_name == "CarouselCard":
            params["title"] = f"Card {current_index + 1}"
        context[index_key] = current_index + 1

    return params


__all__ = [
    "consume_from_context",
]
