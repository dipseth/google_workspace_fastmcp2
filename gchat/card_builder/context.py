"""
Context consumption utilities for card building.

This module provides functions for consuming resources from a shared context
during card building (buttons, texts, chips, carousel cards).

Design rationale — why sequential consumption is correct
========================================================

Resources (buttons, texts, chips, grid items, carousel cards) are consumed
sequentially: the first Button widget in the DSL tree gets buttons[0], the
second gets buttons[1], and so on. Each consumption increments an index
counter (_button_index, _text_index, etc.) in the shared context dict.

This was a deliberate design choice. Alternatives were considered and
rejected:

1. **Semantic matching** (match button text to widget context via NLP or
   string similarity) — Ambiguous when multiple candidates score similarly.
   Impossible to debug when the wrong match is selected. Requires NLP
   infrastructure where none should be needed. A DSL that needs AI to
   interpret defeats the purpose of having a DSL.

2. **Named slots** (explicit mapping like ``button_0 -> widget_3``) —
   Adds syntax complexity to the DSL for minimal benefit. The structure
   tree already encodes the allocation: ``§[δ[ᵬ], Ƀ[ᵬ×2]]`` with 3
   buttons means the first goes to DecoratedText, the next two to
   ButtonList. The structure IS the allocation.

3. **Type-based dispatch** (route by param schema compatibility) —
   All buttons have the same schema, so this reduces to sequential anyway.
   For mixed types it introduces ordering ambiguity.

Sequential consumption is:
- **Deterministic**: same DSL + same params = same card, always.
- **Debuggable**: if button 2 is wrong, look at buttons[1] in card_params.
- **Composable**: nested components consume from the same pool without
  coordination. A Button inside a DecoratedText and a Button inside a
  ButtonList both just call consume_from_context("Button") and get the
  next available item.
- **Simple**: ~30 lines of code vs unbounded complexity.

If you're reading this and thinking about making consumption "smarter",
the answer is almost certainly to fix the DSL structure or card_params
ordering instead. The sequential model respects DSL author intent.
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
            # For grid items, extract title, subtitle, image
            elif context_key == "grid_items":
                params["title"] = resource.get("title", f"Item {current_index + 1}")
                if resource.get("subtitle"):
                    params["subtitle"] = resource["subtitle"]
                if resource.get("image_url"):
                    params["image_url"] = resource["image_url"]
                if resource.get("image"):
                    params["image"] = resource["image"]
                # Record the consumption in mapping report
                if mapping_report:
                    mapping_report.record(
                        input_type="grid_item",
                        index=current_index,
                        value=resource.get("title", ""),
                        component=component_name,
                        field_name="grid_item",
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
        elif component_name == "GridItem":
            params["title"] = f"Item {current_index + 1}"
        context[index_key] = current_index + 1

    return params


__all__ = [
    "consume_from_context",
]
