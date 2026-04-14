"""
Component building engine for card construction.

Provides ComponentBuilder — a class that builds Google Chat card components
using ModuleWrapper metadata, DAG relationships, and context-driven resource
consumption. Handles containers, widgets, auto-wrapping, and nested structures.

Extracted from SmartCardBuilderV2 (Phase 4 of migration plan).
"""

import re
from typing import Any, Dict, List, Optional, Union

from adapters.module_wrapper.strict import warn_strict
from config.enhanced_logging import setup_logger
from gchat.card_builder.constants import FIELD_NAME_TO_JSON, get_default_params
from gchat.card_builder.context import consume_from_context
from gchat.card_builder.metadata import (
    get_children_field,
    get_container_child_type,
    is_empty_component,
    is_form_component,
)
from gchat.card_builder.rendering import (
    build_child_widget,
    convert_to_camel_case,
    get_json_key,
    json_key_to_component_name,
    prepare_children_for_container,
)

logger = setup_logger()

# Components that are NOT standalone widgets — skip in generic builder
NON_WIDGET_COMPONENTS = {
    "Card",
    "CardHeader",
    "Section",  # Top-level containers
    "OnClick",
    "OpenLink",
    "onClick",
    "openLink",  # Nested inside buttons
    "Button",  # Handled by ButtonList
    "Icon",
    "icon",  # Nested inside decoratedText.startIcon or buttons
}


class ComponentBuilder:
    """Builds Google Chat card components using ModuleWrapper.

    Encapsulates the component building pipeline:
    - Universal component builder (any type via DAG + metadata)
    - Generic widget builder (mapping-driven, no if/elif chains)
    - Generic container builder (ButtonList, Grid, Carousel, Columns)
    - Child-to-parent parameter mapping (DSL nested structures)

    Args:
        wrapper: ModuleWrapper instance with DAG and metadata capabilities
        format_text_fn: Optional text formatter (e.g., Jinja processor).
            If None, text passes through unchanged.
    """

    def __init__(self, wrapper, format_text_fn=None):
        self._wrapper = wrapper
        self._format_text = format_text_fn or (lambda t: t)

    def build_component(
        self,
        component_name: str,
        params: Dict[str, Any],
        wrapper=None,
        wrap_with_key: bool = False,
        children: Optional[List[Dict[str, Any]]] = None,
        validate: bool = False,
        return_instance: bool = False,
        child_instances: Optional[List[Any]] = None,
        auto_wrap: bool = False,
        target_parent: Optional[str] = None,
    ) -> Optional[Union[Dict[str, Any], Any]]:
        """Universal component builder leveraging ModuleWrapper DAG and metadata.

        Builds ANY component type by:
        1. Using get_cached_class() for fast L1 cache lookup
        2. Falling back to wrapper.search() for discovery
        3. Using wrapper metadata to validate and enrich params
        4. Supporting nested children with DAG validation
        5. Using create_card_component() for proper param filtering
        6. Auto-wrapping components using DAG relationships (e.g., Button -> ButtonList)

        Args:
            component_name: Component type (e.g., "TextParagraph", "DecoratedText")
            params: Parameters for the component
            wrapper: Optional override wrapper. If None, uses self._wrapper.
            wrap_with_key: If True, returns {jsonKey: innerDict}
            children: Optional pre-built child widgets (JSON dicts)
            validate: If True, validate children against DAG relationships
            return_instance: If True, return component instance instead of JSON
            child_instances: Optional component instances for container building
            auto_wrap: If True, auto-wrap in required container using DAG
            target_parent: Target parent for auto_wrap

        Returns:
            Widget dict, component instance, or None if build fails
        """
        wrapper = wrapper or self._wrapper
        json_key = get_json_key(component_name)

        if not wrapper:
            # Fallback to simple dict if no wrapper
            inner = params.copy()
            if children:
                inner["widgets"] = children
            return {json_key: inner} if wrap_with_key else inner

        # 0. Auto-wrap using DAG if requested
        if auto_wrap and target_parent:
            required_wrapper = None
            if hasattr(wrapper, "find_required_wrapper"):
                required_wrapper = wrapper.find_required_wrapper(
                    component_name, target_parent
                )
            if required_wrapper and required_wrapper != component_name:
                logger.debug(
                    f"DAG auto-wrap: {component_name} → {required_wrapper} for {target_parent}"
                )
                # Build the inner component first
                inner_component = self.build_component(
                    component_name=component_name,
                    params=params,
                    wrapper=wrapper,
                    wrap_with_key=False,
                    children=children,
                    validate=validate,
                    return_instance=return_instance,
                    child_instances=child_instances,
                    auto_wrap=False,  # Prevent infinite recursion
                )
                if inner_component is None:
                    return None

                # Build the wrapper container with the inner component as child
                if return_instance:
                    return self.build_component(
                        component_name=required_wrapper,
                        params={},
                        wrapper=wrapper,
                        wrap_with_key=wrap_with_key,
                        return_instance=True,
                        child_instances=[inner_component],
                        auto_wrap=False,
                    )
                else:
                    wrapped_inner = (
                        {json_key: inner_component}
                        if not isinstance(inner_component, dict)
                        or json_key not in inner_component
                        else inner_component
                    )
                    return self.build_component(
                        component_name=required_wrapper,
                        params={},
                        wrapper=wrapper,
                        wrap_with_key=wrap_with_key,
                        children=[wrapped_inner],
                        validate=validate,
                        auto_wrap=False,
                    )

        # 1. Query wrapper metadata for component info
        is_empty = is_empty_component(component_name, wrapper)
        children_field = get_children_field(component_name, wrapper)

        # 2. Validate children against DAG if requested
        if validate and children and hasattr(wrapper, "can_contain"):
            for child in children:
                child_key = (
                    next(iter(child.keys()), None) if isinstance(child, dict) else None
                )
                if child_key:
                    child_name = json_key_to_component_name(child_key)
                    if not wrapper.can_contain(component_name, child_name):
                        logger.warning(
                            f"DAG validation: {component_name} cannot contain {child_name}"
                        )

        # 3. Try cached class first (fast L1 memory cache)
        comp_class = wrapper.get_cached_class(component_name)

        # 4. Fallback to wrapper search if not in cache
        if not comp_class and hasattr(wrapper, "search"):
            try:
                results = wrapper.search(component_name, limit=1)
                if results:
                    result = results[0]
                    path = result.get("path") or result.get("component_path")
                    if path:
                        comp_class = wrapper.get_component_by_path(path)
            except Exception as e:
                logger.debug(f"Wrapper search failed for {component_name}: {e}")

        # 5. Handle empty components (no params needed)
        if is_empty:
            if return_instance and comp_class:
                try:
                    instance = wrapper.create_card_component(comp_class, {})
                    if instance:
                        return instance
                except Exception:
                    pass
            result = {json_key: {}}
            if children and children_field:
                result[json_key][children_field] = children
            return result if wrap_with_key else result.get(json_key, {})

        # 6. Build via wrapper class if found
        if comp_class:
            try:
                build_params = params.copy()

                # Pre-process: Convert shorthand params to proper nested structures
                if component_name in ("Button", "Chip") and "url" in build_params:
                    url = build_params.pop("url")
                    if url and "on_click" not in build_params:
                        try:
                            from card_framework.v2.widgets.on_click import OnClick
                            from card_framework.v2.widgets.open_link import OpenLink

                            build_params["on_click"] = OnClick(
                                open_link=OpenLink(url=url)
                            )
                        except ImportError:
                            build_params["on_click"] = {"open_link": {"url": url}}

                if child_instances:
                    if component_name == "Card":
                        headers = [
                            c
                            for c in child_instances
                            if type(c).__name__ == "CardHeader"
                        ]
                        sections = [
                            c for c in child_instances if type(c).__name__ == "Section"
                        ]
                        if headers:
                            build_params["header"] = headers[0]
                        if sections:
                            build_params["sections"] = sections
                    elif children_field:
                        snake_field = re.sub(
                            r"([a-z])([A-Z])", r"\1_\2", children_field
                        ).lower()
                        build_params[snake_field] = child_instances

                instance = wrapper.create_card_component(comp_class, build_params)
                if instance:
                    if component_name == "DecoratedText":
                        if hasattr(instance, "wrap_text"):
                            instance.wrap_text = params.get(
                                "wrapText", params.get("wrap_text", True)
                            )

                    if return_instance:
                        return instance

                    if hasattr(instance, "render"):
                        rendered = instance.render()
                        converted = convert_to_camel_case(rendered)
                    elif hasattr(instance, "to_dict"):
                        rendered = instance.to_dict()
                        converted = convert_to_camel_case(rendered)
                    else:
                        converted = None

                    if converted:
                        if json_key in converted and len(converted) == 1:
                            inner = converted[json_key]
                        else:
                            inner = converted

                        if component_name == "DecoratedText":
                            inner["wrapText"] = params.get("wrapText", True)
                            if params.get("icon") and "startIcon" not in inner:
                                inner["startIcon"] = {
                                    "materialIcon": {"name": params["icon"]}
                                }
                            if params.get("top_label") and "topLabel" not in inner:
                                inner["topLabel"] = params["top_label"]
                            if (
                                params.get("bottom_label")
                                and "bottomLabel" not in inner
                            ):
                                inner["bottomLabel"] = params["bottom_label"]

                        if children and children_field:
                            inner[children_field] = prepare_children_for_container(
                                component_name, children, children_field
                            )

                        return {json_key: inner} if wrap_with_key else inner
            except Exception as e:
                logger.debug(f"Component build failed for {component_name}: {e}")

        # 7. Fallback: build from params directly
        inner = params.copy()
        if children and children_field:
            inner[children_field] = prepare_children_for_container(
                component_name, children, children_field
            )
        elif children:
            default_field = get_children_field(component_name, wrapper) or "widgets"
            inner[default_field] = children

        return {json_key: inner} if wrap_with_key else inner

    def build_widget_generic(
        self,
        component_name: str,
        grandchildren: List[Dict],
        context: Dict[str, Any],
        explicit_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generic widget builder — handles ANY component type.

        Replaces if/elif component_name chains with:
        1. Dynamic JSON key derivation
        2. Context-based resource consumption
        3. Generic container/child handling
        4. Wrapper-based rendering

        Args:
            component_name: Component type (e.g., "DecoratedText", "ButtonList")
            grandchildren: Nested children from DSL
            context: Shared context for resource consumption
            explicit_params: Any explicit params to include

        Returns:
            Widget dict in Google Chat format, or None if build fails
        """
        if component_name in NON_WIDGET_COMPONENTS:
            return None

        json_key = get_json_key(component_name)
        params = explicit_params.copy() if explicit_params else {}
        wrapper = self._wrapper

        # 1. Empty components (just structure, no content)
        if is_empty_component(component_name, wrapper):
            return {json_key: {}}

        # 2. Consume from context if this component type uses resources
        consumed = consume_from_context(component_name, context, wrapper)
        for k, v in consumed.items():
            params.setdefault(k, v)

        # 2.3 Image context injection
        if component_name == "Image" and "imageUrl" not in params:
            img_url = context.get("image_url")
            if img_url:
                params["imageUrl"] = img_url
            else:
                logger.debug("Image component has no URL in context, skipping")
                return None

        # 2.5 Ensure text-bearing components have a text field
        if (
            component_name in ("DecoratedText", "TextParagraph")
            and "text" not in params
        ):
            if consumed.get("_placeholder"):
                logger.debug(f"Skipping placeholder {component_name} (no real content)")
                return None
            params["text"] = "\u00a0"  # non-breaking space

        # 3. Container components - build children recursively
        children_field = get_children_field(component_name, wrapper)
        if children_field:
            logger.debug(
                f"🎠 Container component: {component_name} "
                f"(children_field={children_field}, "
                f"children_count={len(grandchildren)})"
            )
            result = self.build_container_generic(
                component_name, grandchildren, context, params
            )
            logger.debug(
                f"🎠 Container result for {component_name}: "
                f"{result.keys() if result else 'None'}"
            )
            return result

        # 4. Components with nested children (like DecoratedText with Button)
        child_params = {}
        if grandchildren:
            child_params = self._map_children_to_params(
                component_name, grandchildren, context
            )

        # 5. Form components need a name field
        if is_form_component(component_name, wrapper):
            input_index = context.get("_input_index", 0)
            params.setdefault("name", f"{component_name.lower()}_{input_index}")
            params.setdefault("label", component_name.replace("Input", " Input"))
            context["_input_index"] = input_index + 1

        # 5.5 Pre-process DecoratedText special fields
        decorated_text_extras = {}
        if component_name == "DecoratedText":
            if params.get("icon"):
                from gchat.material_icons import resolve_icon_name

                icon_name = resolve_icon_name(params.pop("icon"))
                decorated_text_extras["startIcon"] = {
                    "materialIcon": {"name": icon_name}
                }
            if params.get("top_label"):
                decorated_text_extras["topLabel"] = params.pop("top_label")
            if params.get("bottom_label"):
                decorated_text_extras["bottomLabel"] = params.pop("bottom_label")
            decorated_text_extras["wrapText"] = params.pop("wrapText", True)

        # 6. Build via wrapper (only if no pre-built children)
        if not child_params:
            if wrapper:
                built = self.build_component(component_name, params, wrapper=wrapper)
                if built:
                    if decorated_text_extras:
                        built.update(decorated_text_extras)
                    return {json_key: built}

        # 7. Build widget with merged children
        widget_content = {}
        if "text" in params:
            widget_content["text"] = self._format_text(params["text"])
        if component_name == "DecoratedText":
            widget_content.setdefault("wrapText", True)
            widget_content.update(decorated_text_extras)

        for k, v in params.items():
            if k not in widget_content:
                widget_content[k] = v

        widget_content.update(child_params)

        if component_name == "Image":
            img_url = params.get("imageUrl") or context.get("image_url")
            if not img_url:
                logger.debug("Image component has no URL, skipping")
                return None
            return {json_key: {"imageUrl": img_url}}

        if not widget_content:
            warn_strict(
                f"build_widget_generic('{component_name}'): widget_content is empty. "
                f"Widget will be omitted from the card."
            )
            return None
        return {json_key: widget_content}

    def build_container_generic(
        self,
        component_name: str,
        children: List[Dict],
        context: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build container components (ButtonList, Grid, etc.) generically.

        Uses wrapper metadata (children_field, child_type) as SSoT.
        """
        json_key = get_json_key(component_name)
        wrapper = self._wrapper
        children_field = get_children_field(component_name, wrapper) or "widgets"
        expected_child_type = get_container_child_type(component_name, wrapper)

        # Count expected children from DSL
        if expected_child_type and children:
            expected_count = sum(
                c.get("multiplier", 1)
                for c in children
                if c.get("name") == expected_child_type
            )
        else:
            expected_count = 1

        # Special case: Columns has nested structure
        if component_name == "Columns":
            return self.build_columns_generic(children, context)

        # Build child items using build_component() universal builder
        built_children = []

        for _ in range(expected_count):
            if expected_child_type in ("Button", "Chip", "GridItem"):
                child_params = consume_from_context(
                    expected_child_type, context, wrapper
                )
                # Skip placeholder children that lack required fields
                if child_params.get("_placeholder"):
                    if expected_child_type in ("Button", "Chip") and not child_params.get("url"):
                        logger.debug(
                            f"Skipping placeholder {expected_child_type} (no URL)"
                        )
                        continue
                if expected_child_type == "Chip":
                    if "text" in child_params and "label" not in child_params:
                        child_params["label"] = child_params.pop("text")
                    # Convert icon string to proper materialIcon dict
                    if "icon" in child_params and isinstance(child_params["icon"], str):
                        from gchat.material_icons import resolve_icon_name, create_material_icon
                        resolved_name = resolve_icon_name(child_params["icon"])
                        child_params["icon"] = create_material_icon(resolved_name)
                    # Chips require onClick — auto-generate action if no URL
                    if not child_params.get("url") and "on_click" not in child_params:
                        label = child_params.get("label", f"chip_{len(built_children)}")
                        try:
                            from card_framework.v2.widgets.on_click import OnClick
                            from card_framework.v2.widgets.action import Action, ActionParameter
                            child_params["on_click"] = OnClick(
                                action=Action(
                                    function="chip_select",
                                    parameters=[
                                        ActionParameter(key="label", value=str(label))
                                    ],
                                )
                            )
                        except ImportError:
                            child_params["on_click"] = {
                                "action": {
                                    "function": "chip_select",
                                    "parameters": [
                                        {"key": "label", "value": str(label)}
                                    ],
                                }
                            }
                    if not child_params.get("label"):
                        continue
                elif expected_child_type == "GridItem":
                    child_params.setdefault("title", f"Item {len(built_children) + 1}")
                    if "image_url" in child_params and "image" not in child_params:
                        child_params["image"] = {
                            "imageUri": child_params.pop("image_url")
                        }
                child = self.build_component(
                    expected_child_type,
                    child_params,
                    wrap_with_key=False,
                )
                if child is not None:
                    built_children.append(child)
            elif expected_child_type == "CarouselCard":
                card_params = consume_from_context("CarouselCard", context, wrapper)
                logger.debug(
                    f"🎠 CarouselCard #{len(built_children)}: "
                    f"params={list(card_params.keys())}"
                )
                if wrapper:
                    if (
                        "title" in card_params or "text" in card_params
                    ) and "widgets" not in card_params:
                        widgets = []
                        idx = len(built_children)

                        # Add image FIRST if provided
                        image_url = card_params.get("image_url") or card_params.get(
                            "image"
                        )
                        if image_url:
                            image_widget = self.build_component(
                                "Image",
                                {"image_url": image_url},
                                wrapper=wrapper,
                                wrap_with_key=True,
                            )
                            if image_widget:
                                widgets.append(image_widget)

                        title = card_params.get("title", f"Card {idx + 1}")
                        if title:
                            formatted_title = self._format_text(title)
                            title_widget = self.build_component(
                                "TextParagraph",
                                {"text": f"<b>{formatted_title}</b>"},
                                wrapper=wrapper,
                                wrap_with_key=True,
                            )
                            if title_widget:
                                widgets.append(title_widget)

                        text = card_params.get("text")
                        if text:
                            text_widget = self.build_component(
                                "TextParagraph",
                                {"text": text},
                                wrapper=wrapper,
                                wrap_with_key=True,
                            )
                            if text_widget:
                                widgets.append(text_widget)

                        buttons = card_params.get("buttons", [])
                        if buttons:
                            btn_instances = []
                            for b in buttons:
                                btn = self.build_component(
                                    "Button",
                                    {
                                        "text": b.get("text", "Button"),
                                        "url": b.get("url"),
                                    },
                                    wrapper=wrapper,
                                    return_instance=True,
                                )
                                if btn:
                                    btn_instances.append(btn)
                            if btn_instances:
                                btn_list_widget = self.build_component(
                                    "ButtonList",
                                    {},
                                    wrapper=wrapper,
                                    wrap_with_key=True,
                                    child_instances=btn_instances,
                                )
                                if btn_list_widget:
                                    widgets.append(btn_list_widget)

                        built_children.append({"widgets": widgets})
                        logger.debug(
                            f"🎠 Built CarouselCard with {len(widgets)} widget(s) "
                            f"(transformed from title/text)"
                        )
                    elif "widgets" in card_params:
                        built_children.append({"widgets": card_params["widgets"]})
                        logger.debug("🎠 CarouselCard using provided widgets array")
                    else:
                        logger.debug("🎠 CarouselCard with no content, skipping")
                        continue
            else:
                logger.debug(
                    f"🎠 Skipping fallback for unknown child type in {component_name}"
                )
                continue

        if not built_children:
            warn_strict(
                f"build_container_generic('{component_name}'): no children built. "
                f"Container will be omitted from the card."
            )
            logger.debug(f"🎠 No children built for {component_name}")
            return None

        result = {children_field: built_children}
        if component_name == "Grid":
            result["columnCount"] = min(3, len(built_children))

        final_result = {json_key: result}
        logger.debug(
            f"🎠 build_container_generic returning: "
            f"{{'{json_key}': {{{repr(children_field)}: [{len(built_children)} items]}}}}"
        )
        return final_result

    def build_columns_generic(
        self,
        children: List[Dict],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build Columns component with nested column structure."""
        wrapper = self._wrapper
        column_items = []

        for child in children:
            if child.get("name") != "Column":
                continue
            col_mult = child.get("multiplier", 1)
            col_grandchildren = child.get("children", [])

            for _ in range(col_mult):
                col_widgets = []
                if col_grandchildren:
                    # Column has explicit nested widgets in DSL — build them
                    for gc in col_grandchildren:
                        gc_name = gc.get("name", "")
                        gc_mult = gc.get("multiplier", 1)
                        gc_children = gc.get("children", [])

                        for _ in range(gc_mult):
                            widget = self.build_widget_generic(
                                gc_name, gc_children, context
                            )
                            if widget:
                                col_widgets.append(widget)
                else:
                    # Column has no DSL children — consume content from context
                    col_params = consume_from_context("Column", context, wrapper)
                    if col_params:
                        # Column params can contain a 'widgets' list or text content
                        nested_widgets = col_params.get("widgets", [])
                        if nested_widgets:
                            for nw in nested_widgets:
                                nw_type = nw.get("type", "decorated_text")
                                nw_name = {
                                    "decorated_text": "DecoratedText",
                                    "text_paragraph": "TextParagraph",
                                    "image": "Image",
                                    "button_list": "ButtonList",
                                }.get(nw_type, "TextParagraph")
                                nw_params = {
                                    k: v
                                    for k, v in nw.items()
                                    if k != "type"
                                }
                                built = self.build_component(
                                    nw_name,
                                    nw_params,
                                    wrapper=wrapper,
                                    wrap_with_key=True,
                                )
                                if built:
                                    col_widgets.append(built)
                        elif "text" in col_params:
                            # Simple text content for this column
                            built = self.build_component(
                                "TextParagraph",
                                {"text": col_params["text"]},
                                wrapper=wrapper,
                                wrap_with_key=True,
                            )
                            if built:
                                col_widgets.append(built)

                if col_widgets:
                    column_items.append({"widgets": col_widgets})

        if not column_items:
            wrapper = self._wrapper
            col1_widget = self.build_component(
                "TextParagraph",
                {"text": "Column 1"},
                wrapper=wrapper,
                wrap_with_key=True,
            )
            col2_widget = self.build_component(
                "TextParagraph",
                {"text": "Column 2"},
                wrapper=wrapper,
                wrap_with_key=True,
            )
            column_items = [
                {"widgets": [col1_widget] if col1_widget else []},
                {"widgets": [col2_widget] if col2_widget else []},
            ]

        return {"columns": {"columnItems": column_items}}

    # =========================================================================
    # CHILD MAPPING (DSL nested structures)
    # =========================================================================

    def _map_children_to_params(
        self,
        parent_name: str,
        children: List[Dict],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Map parsed DSL children to parent component parameters.

        Uses module_wrapper relationships to determine which field each
        child component should be assigned to in the parent.
        """
        wrapper = self._wrapper
        if not wrapper:
            return {}

        params = {}
        for child in children:
            child_name = child.get("name", "")
            child_params = child.get("params", {})
            child_grandchildren = child.get("children", [])

            field_info = wrapper.get_field_for_child(parent_name, child_name)
            if not field_info:
                logger.debug(
                    f"No field mapping for {parent_name} -> {child_name}, skipping"
                )
                continue

            field_name = field_info["field_name"]
            json_field_name = FIELD_NAME_TO_JSON.get(
                (parent_name, field_name), field_name
            )

            resolved_params = self._resolve_child_params(
                child_name, child_params, context
            )

            child_widget = build_child_widget(
                wrapper, child_name, resolved_params,
                build_component_fn=self.build_component,
            )

            if child_widget is not None:
                params[json_field_name] = child_widget
                logger.debug(f"Mapped {child_name} to {parent_name}.{json_field_name}")
            else:
                warn_strict(
                    f"_map_children_to_params('{parent_name}'): child '{child_name}' "
                    f"built to None, skipped in parent params."
                )

        return params

    def _resolve_child_params(
        self,
        child_name: str,
        explicit_params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resolve parameters for a child component using mapping-driven approach."""
        params = {}

        # 1. Start with defaults
        defaults = get_default_params(child_name)
        params.update(defaults)

        # 2. Component-specific defaults
        component_defaults = {
            "Icon": {"known_icon": "STAR"},
            "SwitchControl": {"name": "switch", "selected": False},
        }
        if child_name in component_defaults:
            params.update(component_defaults[child_name])

        # 3. Context-consumed values OVERRIDE defaults
        consumed = consume_from_context(child_name, context, self._wrapper)
        params.update(consumed)

        # 4. Explicit params override everything
        params.update(explicit_params)

        return params


__all__ = [
    "ComponentBuilder",
    "NON_WIDGET_COMPONENTS",
]
