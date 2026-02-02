"""
Prepared patterns for deferred rendering.

This module provides PreparedPattern for deferred card rendering,
using the card_builder package utilities for metadata and rendering.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from adapters.module_wrapper.types import (
    ComponentName,
    ComponentPaths,
    JsonDict,
    Payload,
    Serializable,
)
from gchat.card_builder.constants import COMPONENT_PARAMS
from gchat.card_builder.metadata import (
    get_children_field,
    is_empty_component,
)

logger = logging.getLogger(__name__)


# =============================================================================
# INPUT MAPPING REPORT - Tracks how inputs are consumed during card building
# =============================================================================


@dataclass
class InputMappingReport:
    """Tracks how inputs are consumed during card building.

    Implements Serializable protocol for consistent JSON serialization.
    """

    consumptions: List[JsonDict] = field(default_factory=list)

    def record(
        self,
        input_type: str,
        index: int,
        value: str,
        component: ComponentName,
        field_name: str,
    ) -> None:
        """Record a consumption event."""
        preview = value[:50] + "..." if len(value) > 50 else value
        self.consumptions.append(
            {
                "input": f"{input_type}[{index}]",
                "value_preview": preview,
                "component": component,
                "field": field_name,
            }
        )

    def to_dict(self, context: Optional[JsonDict] = None) -> JsonDict:
        """Convert to dictionary for API response.

        Args:
            context: Optional build context for unconsumed counts

        Returns:
            JSON-serializable dictionary with mappings and unconsumed counts
        """
        result: JsonDict = {"mappings": self.consumptions}
        if context:
            buttons_total = len(context.get("buttons", []))
            texts_total = len(context.get("content_texts", []))
            result["unconsumed"] = {
                "buttons": buttons_total - context.get("_button_index", 0),
                "texts": texts_total - context.get("_text_index", 0),
            }
        return result


# =============================================================================
# PREPARED PATTERN - Deferred Rendering Support
# =============================================================================


class PreparedPattern:
    """
    A pattern prepared for rendering with deferred parameter population.

    This class allows you to:
    1. Load component classes from the wrapper once
    2. Set/update parameters before rendering
    3. Render to Google Chat JSON when ready

    Usage:
        # Get a prepared pattern
        prepared = PreparedPattern.from_pattern(pattern, wrapper)

        # Set params (chainable)
        prepared.set_params(text="Hello", title="My Card")

        # Or set individual params
        prepared.set_param("buttons", [{"text": "Click", "url": "..."}])

        # Render when ready
        card_json = prepared.render()

        # Or get instances without rendering (for inspection/modification)
        instances = prepared.get_instances()
    """

    def __init__(self, component_paths: ComponentPaths, wrapper):
        """
        Initialize with component paths and wrapper.

        Args:
            component_paths: List of component names (e.g., ["Section", "DecoratedText", "ButtonList"])
            wrapper: ModuleWrapper instance for loading component classes
        """
        self.component_paths: ComponentPaths = component_paths
        self.wrapper = wrapper
        self.params: JsonDict = {}
        self._component_classes: Dict[ComponentName, Any] = {}
        self._load_component_classes()

    def _load_component_classes(self):
        """Load component classes from wrapper using cached class retrieval."""
        if not self.wrapper:
            return

        for comp_name in set(self.component_paths):
            if comp_name in ("Section",):  # Skip containers
                continue

            # Use cached class retrieval for fast L1 memory access
            comp_class = self.wrapper.get_cached_class(comp_name)

            # Fallback to path-based lookup if not in cache
            if not comp_class:
                paths_to_try = [
                    f"card_framework.v2.widgets.{comp_name.lower()}.{comp_name}",
                    f"card_framework.v2.{comp_name.lower()}.{comp_name}",
                ]
                for path in paths_to_try:
                    comp_class = self.wrapper.get_component_by_path(path)
                    if comp_class:
                        break

            if comp_class:
                self._component_classes[comp_name] = comp_class

    def set_params(self, **params) -> "PreparedPattern":
        """
        Set multiple parameters at once. Chainable.

        Args:
            **params: Parameter key-value pairs

        Returns:
            Self for chaining
        """
        self.params.update(params)
        return self

    def set_param(self, key: str, value: Any) -> "PreparedPattern":
        """
        Set a single parameter. Chainable.

        Args:
            key: Parameter name
            value: Parameter value

        Returns:
            Self for chaining
        """
        self.params[key] = value
        return self

    def get_instances(self) -> List[JsonDict]:
        """
        Get component instances without rendering.

        Useful for inspection or manual modification before rendering.

        Returns:
            List of dicts with 'name', 'class', 'instance' (or None if instantiation failed)
        """
        instances: List[JsonDict] = []
        for comp_name in self.component_paths:
            if comp_name in ("Section",):
                continue

            comp_class = self._component_classes.get(comp_name)
            instance = None

            if comp_class:
                # Get params relevant to this component
                comp_params = self._get_params_for_component(comp_name)
                instance = self.wrapper.create_card_component(comp_class, comp_params)

            instances.append({
                "name": comp_name,
                "class": comp_class,
                "instance": instance,
            })

        return instances

    def _get_params_for_component(self, comp_name: ComponentName) -> JsonDict:
        """Get relevant params for a specific component type.

        Uses COMPONENT_PARAMS from card_builder.constants for dynamic mapping.
        """
        # Get expected params from COMPONENT_PARAMS registry
        expected_params = COMPONENT_PARAMS.get(comp_name, {})

        comp_params: JsonDict = {}

        # Map input params to component params based on COMPONENT_PARAMS keys
        for param_key in expected_params.keys():
            # Check both exact match and common aliases
            if param_key in self.params:
                comp_params[param_key] = self.params[param_key]
            # Handle common aliases
            elif param_key == "text" and "description" in self.params:
                comp_params["text"] = self.params["description"]
            elif param_key == "image_url" and "imageUrl" in self.params:
                comp_params["image_url"] = self.params["imageUrl"]

        # Also pass through any params that match directly
        for key, value in self.params.items():
            if key not in comp_params and key in expected_params:
                comp_params[key] = value

        return comp_params

    def render(self, include_header: bool = True) -> JsonDict:
        """
        Render the pattern to Google Chat card JSON.

        Args:
            include_header: Whether to include card header if title is set

        Returns:
            Card dict in Google Chat format
        """
        widgets: List[JsonDict] = []
        text_consumed = False
        buttons_consumed = False
        image_consumed = False

        for comp_name in self.component_paths:
            if comp_name in ("Section",):
                continue

            # Check if this is an empty component (like Divider)
            if is_empty_component(comp_name, self.wrapper):
                widgets.append(self._build_empty_widget(comp_name))
                continue

            comp_class = self._component_classes.get(comp_name)

            if comp_class:
                # Try to use wrapper's create_card_component + render
                comp_params = self._get_params_for_component(comp_name)
                instance = self.wrapper.create_card_component(comp_class, comp_params)

                if instance and hasattr(instance, 'render'):
                    widget = instance.render()
                    if widget:
                        widgets.append(widget)
                        # Track consumption based on component type
                        if comp_name in ("DecoratedText", "TextParagraph"):
                            text_consumed = True
                        elif comp_name == "ButtonList":
                            buttons_consumed = True
                        elif comp_name == "Image":
                            image_consumed = True
                        continue

            # Fallback: manual widget construction for components that failed
            widget = self._build_fallback_widget(
                comp_name, text_consumed, buttons_consumed, image_consumed
            )
            if widget:
                widgets.append(widget)
                if comp_name in ("DecoratedText", "TextParagraph"):
                    text_consumed = True
                elif comp_name == "ButtonList":
                    buttons_consumed = True
                elif comp_name == "Image":
                    image_consumed = True

        # Build card structure
        card = {"sections": [{"widgets": widgets}]} if widgets else {"sections": []}

        # Add header if requested and title exists
        if include_header and self.params.get("title"):
            card["header"] = {"title": self.params["title"]}
            if self.params.get("subtitle"):
                card["header"]["subtitle"] = self.params["subtitle"]

        return card

    def _build_empty_widget(self, comp_name: ComponentName) -> JsonDict:
        """Build an empty widget (like Divider)."""
        json_key = comp_name[0].lower() + comp_name[1:]  # camelCase
        return {json_key: {}}

    def _build_fallback_widget(
        self,
        comp_name: ComponentName,
        text_consumed: bool,
        buttons_consumed: bool,
        image_consumed: bool,
    ) -> Optional[JsonDict]:
        """Build widget manually when component class rendering fails.

        Uses COMPONENT_PARAMS to understand expected fields.
        """
        if comp_name == "DecoratedText" and not text_consumed:
            text = self.params.get("text") or self.params.get("description", "")
            if text:
                return {"decoratedText": {"text": text, "wrapText": True}}

        elif comp_name == "TextParagraph" and not text_consumed:
            text = self.params.get("text") or self.params.get("description", "")
            if text:
                return {"textParagraph": {"text": text}}

        elif comp_name == "ButtonList" and not buttons_consumed:
            buttons = self.params.get("buttons", [])
            if buttons:
                btn_list = []
                for btn in buttons:
                    if isinstance(btn, dict):
                        btn_obj = {"text": btn.get("text", "Button")}
                        if btn.get("url"):
                            btn_obj["onClick"] = {"openLink": {"url": btn["url"]}}
                        btn_list.append(btn_obj)
                if btn_list:
                    return {"buttonList": {"buttons": btn_list}}

        elif comp_name == "Image" and not image_consumed:
            image_url = self.params.get("image_url") or self.params.get("imageUrl")
            if image_url:
                return {"image": {"imageUrl": image_url}}

        elif comp_name == "Divider":
            return {"divider": {}}

        return None

    @classmethod
    def from_pattern(cls, pattern: Payload, wrapper) -> "PreparedPattern":
        """
        Create a PreparedPattern from a pattern dict.

        Args:
            pattern: Dict with 'component_paths' and optionally 'instance_params'
            wrapper: ModuleWrapper instance

        Returns:
            PreparedPattern ready for param setting and rendering
        """
        component_paths: ComponentPaths = pattern.get("component_paths", [])
        instance_params: JsonDict = pattern.get("instance_params", {})

        prepared = cls(component_paths, wrapper)
        if instance_params:
            prepared.set_params(**instance_params)

        return prepared

    @classmethod
    def from_dsl(cls, dsl_string: str, wrapper) -> "PreparedPattern":
        """
        Create a PreparedPattern from DSL notation.

        Args:
            dsl_string: DSL notation (symbols from wrapper.symbol_mapping)
            wrapper: ModuleWrapper instance

        Returns:
            PreparedPattern ready for param setting and rendering
        """
        from gchat.card_framework_wrapper import parse_dsl

        result = parse_dsl(dsl_string)
        if not result.is_valid:
            logger.warning(f"Invalid DSL: {result.issues}")
            return cls(["Section", "TextParagraph"], wrapper)

        return cls(result.component_paths, wrapper)


def prepare_pattern(
    pattern: Dict[str, Any],
    wrapper=None,
) -> PreparedPattern:
    """
    Convenience function to create a PreparedPattern.

    Args:
        pattern: Dict with 'component_paths' and optionally 'instance_params'
        wrapper: ModuleWrapper instance (uses singleton if not provided)

    Returns:
        PreparedPattern ready for param setting and rendering

    Example:
        from gchat.card_builder import prepare_pattern

        pattern = {"component_paths": ["Section", "DecoratedText", "ButtonList"]}
        card = (
            prepare_pattern(pattern)
            .set_params(text="Hello World", buttons=[{"text": "Click"}])
            .render()
        )
    """
    if wrapper is None:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        wrapper = get_card_framework_wrapper()

    return PreparedPattern.from_pattern(pattern, wrapper)


def prepare_pattern_from_dsl(
    dsl_string: str,
    wrapper=None,
) -> PreparedPattern:
    """
    Convenience function to create a PreparedPattern from DSL.

    Args:
        dsl_string: DSL notation (symbols from ModuleWrapper.symbol_mapping)
        wrapper: ModuleWrapper instance (uses singleton if not provided)

    Returns:
        PreparedPattern ready for param setting and rendering

    Example:
        from gchat.card_builder import prepare_pattern_from_dsl
        # Get symbols from wrapper.symbol_mapping for current mappings
        card = (
            prepare_pattern_from_dsl("§[δ, Ƀ[ᵬ×2]]")
            .set_params(text="Status: OK", buttons=[{"text": "Refresh"}, {"text": "Close"}])
            .render()
        )
    """
    if wrapper is None:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        wrapper = get_card_framework_wrapper()

    return PreparedPattern.from_dsl(dsl_string, wrapper)


__all__ = [
    "InputMappingReport",
    "PreparedPattern",
    "prepare_pattern",
    "prepare_pattern_from_dsl",
]
