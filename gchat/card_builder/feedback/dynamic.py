"""
Dynamic feedback builder using ModuleWrapper's DAG and variation system.
"""

import logging
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

from gchat.card_builder.feedback.prompts import (
    CONTENT_FEEDBACK_PROMPTS,
    FEEDBACK_TEXT_STYLES,
    FORM_FEEDBACK_PROMPTS,
)

logger = logging.getLogger(__name__)


class DynamicFeedbackBuilder:
    """
    Builds feedback widgets dynamically using ModuleWrapper's DAG and variation system.

    This replaces hardcoded feedback widget construction with a system that:
    1. Uses the DAG to understand valid widget containment for any container type
    2. Creates feedback patterns using InstancePattern
    3. Generates variations using StructureVariator and ParameterVariator
    4. Renders using get_cached_class() and .render()

    Supports:
    - Section (widgets[] field)
    - CarouselCard (widgets[] + footerWidgets[] fields)
    - Any future container type with widget children

    Usage:
        builder = DynamicFeedbackBuilder(wrapper)
        feedback = builder.build_feedback_for_container(
            container_type="CarouselCard",
            card_id="my_card_123",
            variation_type="structure",  # or "parameter", "random"
        )
        # Returns dict with widgets to append to container
    """

    # Container type -> (content_field, action_field)
    # content_field: where text prompts go
    # action_field: where buttons/chips go (None = same as content)
    CONTAINER_FIELDS = {
        "Section": ("widgets", None),  # Both go in widgets
        "CarouselCard": (
            "widgets",
            "footerWidgets",
        ),  # Prompts in widgets, buttons in footer
        "NestedWidget": ("widgets", None),
        "Column": ("widgets", None),
    }

    # Valid widget types for feedback by container
    # These should ideally come from the DAG, but we define defaults
    FEEDBACK_WIDGET_TYPES = {
        "text_prompt": ["TextParagraph", "DecoratedText"],
        "action_button": ["ButtonList", "ChipList"],
    }

    # Feedback icons for content and form/layout
    # Note: prompts are loaded at runtime to avoid circular reference
    FEEDBACK_ICONS = {
        "content": {"positive": "thumb_up", "negative": "thumb_down"},
        "form": {"positive": "check_circle", "negative": "cancel"},
    }

    def __init__(self, wrapper=None):
        """
        Initialize the dynamic feedback builder.

        Args:
            wrapper: ModuleWrapper instance (optional, fetched lazily)
        """
        self._wrapper = wrapper
        self._structure_variator = None
        self._param_variator = None
        self._feedback_patterns_cache = {}

    def _get_wrapper(self):
        """Get or create the wrapper instance."""
        if self._wrapper is None:
            try:
                from gchat.card_framework_wrapper import get_card_framework_wrapper

                self._wrapper = get_card_framework_wrapper()
            except ImportError:
                logger.warning("Could not get card_framework_wrapper")
        return self._wrapper

    def _get_structure_variator(self):
        """Get or create the structure variator from wrapper's relationships."""
        if self._structure_variator is None:
            wrapper = self._get_wrapper()
            if wrapper:
                from adapters.module_wrapper.instance_pattern_mixin import (
                    StructureVariator,
                )

                relationships = getattr(wrapper, "relationships", {})
                # Augment with feedback-specific relationships
                feedback_relationships = self._get_feedback_relationships()
                relationships = {**relationships, **feedback_relationships}
                self._structure_variator = StructureVariator(relationships)
        return self._structure_variator

    def _get_param_variator(self):
        """Get or create the parameter variator."""
        if self._param_variator is None:
            from adapters.module_wrapper.instance_pattern_mixin import ParameterVariator

            # Custom variators for feedback-specific params
            custom_variators = {
                "prompt": self._vary_prompt,
                "icon": self._vary_icon,
            }
            self._param_variator = ParameterVariator(custom_variators)
        return self._param_variator

    def _get_feedback_relationships(self) -> Dict[str, List[str]]:
        """
        Define feedback widget containment relationships.

        These augment the wrapper's DAG for feedback-specific structures.
        """
        return {
            # Feedback containers can hold these widgets
            "FeedbackSection": [
                "TextParagraph",
                "DecoratedText",
                "ButtonList",
                "ChipList",
                "Divider",
            ],
            "FeedbackPrompt": ["TextParagraph", "DecoratedText"],
            "FeedbackAction": ["ButtonList", "ChipList", "Button", "Chip"],
            # Widget types for variation
            "TextParagraph": [],  # Leaf
            "DecoratedText": ["Icon", "Button"],
            "ButtonList": ["Button"],
            "ChipList": ["Chip"],
            "Button": ["Icon"],
            "Chip": ["Icon"],
        }

    def _vary_prompt(self, value: str) -> str:
        """Custom variator for feedback prompts."""
        # Apply random styling
        style = random.choice(FEEDBACK_TEXT_STYLES)
        # Extract keyword from template if present
        if "{keyword}" in str(value):
            return value  # Template, don't modify
        return f"<b>{value}</b>" if style == "bold" else value

    def _vary_icon(self, value: str) -> str:
        """Custom variator for feedback icons."""
        positive_icons = ["thumb_up", "check_circle", "sentiment_satisfied", "star"]
        negative_icons = ["thumb_down", "cancel", "sentiment_dissatisfied", "close"]
        if value in positive_icons:
            return random.choice(positive_icons)
        if value in negative_icons:
            return random.choice(negative_icons)
        return value

    def _get_valid_children_for_container(self, container_type: str) -> List[str]:
        """
        Get valid widget children for a container type using the DAG.

        Args:
            container_type: "Section", "CarouselCard", etc.

        Returns:
            List of valid child widget type names
        """
        wrapper = self._get_wrapper()
        if wrapper and hasattr(wrapper, "get_children"):
            try:
                return wrapper.get_children(container_type)
            except Exception:
                pass

        # Fallback: use static mapping
        fallback_children = {
            "Section": [
                "TextParagraph",
                "DecoratedText",
                "ButtonList",
                "ChipList",
                "Image",
                "Divider",
                "Grid",
            ],
            "CarouselCard": [
                "TextParagraph",
                "DecoratedText",
                "ButtonList",
                "Image",
            ],  # via NestedWidget
            "NestedWidget": ["TextParagraph", "DecoratedText", "ButtonList", "Image"],
            "Column": ["TextParagraph", "DecoratedText", "ButtonList", "Image"],
        }
        return fallback_children.get(container_type, ["TextParagraph", "ButtonList"])

    def _build_widget_via_wrapper(
        self,
        widget_type: str,
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Build a widget using wrapper's get_cached_class() and .render().

        Args:
            widget_type: "TextParagraph", "ButtonList", etc.
            params: Parameters for the widget

        Returns:
            Widget dict in Google Chat format, or None on error
        """
        wrapper = self._get_wrapper()
        if not wrapper:
            return self._build_widget_fallback(widget_type, params)

        try:
            # Get cached class
            component_class = wrapper.get_cached_class(widget_type)
            if not component_class:
                return self._build_widget_fallback(widget_type, params)

            # Instantiate and render
            instance = component_class(**params)
            if hasattr(instance, "render"):
                rendered = instance.render()
                # Convert to dict if needed
                if hasattr(rendered, "to_dict"):
                    return rendered.to_dict()
                elif isinstance(rendered, dict):
                    return rendered
                else:
                    return {"error": f"Unknown render result type: {type(rendered)}"}

            return self._build_widget_fallback(widget_type, params)

        except Exception as e:
            logger.warning(f"Failed to build {widget_type} via wrapper: {e}")
            return self._build_widget_fallback(widget_type, params)

    def _build_widget_fallback(
        self,
        widget_type: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Fallback widget builder when wrapper is unavailable.

        Args:
            widget_type: Widget type name
            params: Widget parameters

        Returns:
            Widget dict in Google Chat format
        """
        widget_key = {
            "TextParagraph": "textParagraph",
            "DecoratedText": "decoratedText",
            "ButtonList": "buttonList",
            "ChipList": "chipList",
            "Button": "button",
            "Chip": "chip",
            "Image": "image",
            "Icon": "icon",
            "Divider": "divider",
        }.get(widget_type, widget_type.lower())

        if widget_type == "TextParagraph":
            return {"textParagraph": {"text": params.get("text", "")}}

        elif widget_type == "DecoratedText":
            widget = {
                "text": params.get("text", ""),
                "wrapText": params.get("wrap_text", True),
            }
            if params.get("icon"):
                widget["startIcon"] = {"materialIcon": {"name": params["icon"]}}
            if params.get("button"):
                widget["button"] = params["button"]
            return {"decoratedText": widget}

        elif widget_type == "ButtonList":
            return {"buttonList": {"buttons": params.get("buttons", [])}}

        elif widget_type == "ChipList":
            return {"chipList": {"chips": params.get("chips", [])}}

        elif widget_type == "Divider":
            return {"divider": {}}

        else:
            return {widget_key: params}

    def _get_feedback_prompts(self, feedback_type: str) -> List[Tuple[str, str]]:
        """Get feedback prompts for a feedback type (loaded at runtime)."""
        if feedback_type == "content":
            return CONTENT_FEEDBACK_PROMPTS
        else:
            return FORM_FEEDBACK_PROMPTS

    def _create_feedback_pattern(
        self,
        feedback_type: str,
        container_type: str,
        card_id: str,
    ) -> Dict[str, Any]:
        """
        Create a feedback pattern for the given feedback type and container.

        Uses InstancePattern to define the structure.

        Args:
            feedback_type: "content" or "form"
            container_type: "Section", "CarouselCard", etc.
            card_id: Unique card identifier for callback URLs

        Returns:
            Pattern dict with component_paths and instance_params
        """
        # Load prompts at runtime to avoid circular reference
        prompts = self._get_feedback_prompts(feedback_type)
        icons = self.FEEDBACK_ICONS.get(feedback_type, self.FEEDBACK_ICONS["content"])

        prompt_tuple = random.choice(prompts)
        template, keyword = prompt_tuple

        # Apply styling to keyword
        style = random.choice(FEEDBACK_TEXT_STYLES)
        styled_keyword = self._style_keyword(keyword, style)
        prompt_text = f"<i>{template.format(keyword=styled_keyword)}</i>"

        # Get valid children for this container
        valid_children = self._get_valid_children_for_container(container_type)

        # Choose text widget type based on valid children
        text_types = [
            t for t in ["DecoratedText", "TextParagraph"] if t in valid_children
        ]
        text_type = random.choice(text_types) if text_types else "TextParagraph"

        # Choose action widget type
        action_types = [t for t in ["ButtonList", "ChipList"] if t in valid_children]
        action_type = random.choice(action_types) if action_types else "ButtonList"

        # Build component paths
        component_paths = [text_type, action_type]

        # Build instance params
        instance_params = {
            "prompt_text": prompt_text,
            "feedback_type": feedback_type,
            "card_id": card_id,
            "positive_icon": icons["positive"],
            "negative_icon": icons["negative"],
            "keyword": keyword,
            "style": style,
        }

        return {
            "component_paths": component_paths,
            "instance_params": instance_params,
            "text_type": text_type,
            "action_type": action_type,
        }

    def _style_keyword(self, keyword: str, style: str) -> str:
        """Apply HTML styling to a feedback keyword."""
        colors = {
            "success": "#34a853",
            "warning": "#fbbc05",
            "info": "#4285f4",
            "muted": "#9e9e9e",
        }

        if style == "bold":
            return f"<b>{keyword}</b>"
        elif style == "success":
            return f'<font color="{colors["success"]}">{keyword}</font>'
        elif style == "warning":
            return f'<font color="{colors["warning"]}">{keyword}</font>'
        elif style == "info":
            return f'<font color="{colors["info"]}">{keyword}</font>'
        elif style == "muted":
            return f'<font color="{colors["muted"]}">{keyword}</font>'
        elif style == "bold_success":
            return f'<b><font color="{colors["success"]}">{keyword}</font></b>'
        elif style == "bold_info":
            return f'<b><font color="{colors["info"]}">{keyword}</font></b>'
        else:
            return f"<b>{keyword}</b>"

    def _render_pattern_to_widgets(
        self,
        pattern: Dict[str, Any],
        card_id: str,
        feedback_type: str,
        make_callback_url: Callable,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Render a feedback pattern to actual widgets.

        Args:
            pattern: Pattern dict with component_paths and instance_params
            card_id: Card ID for callback URLs
            feedback_type: "content" or "form"
            make_callback_url: Callback URL builder function

        Returns:
            Dict with 'text_widgets' and 'action_widgets' lists
        """
        params = pattern["instance_params"]
        text_type = pattern["text_type"]
        action_type = pattern["action_type"]

        # Build text prompt widget
        text_params = {"text": params["prompt_text"]}
        if text_type == "DecoratedText":
            text_params["wrap_text"] = True
        text_widget = self._build_widget_via_wrapper(text_type, text_params)

        # Build action buttons widget
        pos_url = make_callback_url(card_id, "positive", feedback_type)
        neg_url = make_callback_url(card_id, "negative", feedback_type)

        if action_type == "ButtonList":
            action_params = {
                "buttons": [
                    {
                        "icon": {"materialIcon": {"name": params["positive_icon"]}},
                        "onClick": {"openLink": {"url": pos_url}},
                        "altText": f"{feedback_type.title()} helpful",
                    },
                    {
                        "icon": {"materialIcon": {"name": params["negative_icon"]}},
                        "onClick": {"openLink": {"url": neg_url}},
                        "altText": f"{feedback_type.title()} not helpful",
                    },
                ]
            }
        else:  # ChipList
            action_params = {
                "chips": [
                    {
                        "icon": {"materialIcon": {"name": params["positive_icon"]}},
                        "onClick": {"openLink": {"url": pos_url}},
                        "altText": f"{feedback_type.title()} helpful",
                    },
                    {
                        "icon": {"materialIcon": {"name": params["negative_icon"]}},
                        "onClick": {"openLink": {"url": neg_url}},
                        "altText": f"{feedback_type.title()} not helpful",
                    },
                ]
            }

        action_widget = self._build_widget_via_wrapper(action_type, action_params)

        return {
            "text_widgets": [text_widget] if text_widget else [],
            "action_widgets": [action_widget] if action_widget else [],
        }

    def build_feedback_for_container(
        self,
        container_type: str,
        card_id: str,
        make_callback_url: Callable,
        include_content: bool = True,
        include_form: bool = True,
        variation_type: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build feedback widgets adapted for a specific container type.

        This is the main entry point for dynamic feedback generation.

        Args:
            container_type: "Section", "CarouselCard", etc.
            card_id: Unique card identifier
            make_callback_url: Function to create callback URLs
            include_content: Include content feedback
            include_form: Include form/layout feedback
            variation_type: "structure", "parameter", or None for random

        Returns:
            Dict with keys based on container type:
            - Section: {"widgets": [...]}
            - CarouselCard: {"widgets": [...], "footerWidgets": [...]}
        """
        content_field, action_field = self.CONTAINER_FIELDS.get(
            container_type, ("widgets", None)
        )

        result = {content_field: []}
        if action_field and action_field != content_field:
            result[action_field] = []

        # Generate variations if variator available
        variator = self._get_structure_variator()

        # Build content feedback
        if include_content:
            content_pattern = self._create_feedback_pattern(
                "content", container_type, card_id
            )

            # Apply structural variation if requested
            if variation_type == "structure" and variator:
                variations = variator.generate_variations(
                    content_pattern["component_paths"], 1
                )
                if variations:
                    content_pattern["component_paths"] = variations[0]
                    # Update types based on variation
                    if len(content_pattern["component_paths"]) >= 2:
                        content_pattern["text_type"] = content_pattern[
                            "component_paths"
                        ][0]
                        content_pattern["action_type"] = content_pattern[
                            "component_paths"
                        ][1]

            # Apply parameter variation if requested
            if variation_type == "parameter":
                param_variator = self._get_param_variator()
                if param_variator:
                    content_pattern["instance_params"] = param_variator.vary_params(
                        content_pattern["instance_params"]
                    )

            rendered = self._render_pattern_to_widgets(
                content_pattern, card_id, "content", make_callback_url
            )

            # Add to appropriate fields
            result[content_field].extend(rendered["text_widgets"])
            target_field = action_field if action_field else content_field
            if target_field not in result:
                result[target_field] = []
            result[target_field].extend(rendered["action_widgets"])

        # Build form/layout feedback
        if include_form:
            form_pattern = self._create_feedback_pattern(
                "form", container_type, card_id
            )

            if variation_type == "structure" and variator:
                variations = variator.generate_variations(
                    form_pattern["component_paths"], 1
                )
                if variations:
                    form_pattern["component_paths"] = variations[0]
                    if len(form_pattern["component_paths"]) >= 2:
                        form_pattern["text_type"] = form_pattern["component_paths"][0]
                        form_pattern["action_type"] = form_pattern["component_paths"][1]

            if variation_type == "parameter":
                param_variator = self._get_param_variator()
                if param_variator:
                    form_pattern["instance_params"] = param_variator.vary_params(
                        form_pattern["instance_params"]
                    )

            rendered = self._render_pattern_to_widgets(
                form_pattern, card_id, "form", make_callback_url
            )

            result[content_field].extend(rendered["text_widgets"])
            target_field = action_field if action_field else content_field
            result[target_field].extend(rendered["action_widgets"])

        return result

    def store_feedback_pattern(
        self,
        container_type: str,
        card_id: str,
        feedback: str = "positive",
    ) -> Optional[str]:
        """
        Store a successful feedback pattern for learning.

        Args:
            container_type: Container type used
            card_id: Card identifier
            feedback: "positive" or "negative"

        Returns:
            Pattern ID if stored, None otherwise
        """
        wrapper = self._get_wrapper()
        if not wrapper or not hasattr(wrapper, "store_instance_pattern"):
            return None

        # Create pattern for both content and form feedback
        content_pattern = self._create_feedback_pattern(
            "content", container_type, card_id
        )
        form_pattern = self._create_feedback_pattern("form", container_type, card_id)

        component_paths = (
            content_pattern["component_paths"] + form_pattern["component_paths"]
        )
        instance_params = {
            "container_type": container_type,
            "content_text_type": content_pattern["text_type"],
            "content_action_type": content_pattern["action_type"],
            "form_text_type": form_pattern["text_type"],
            "form_action_type": form_pattern["action_type"],
        }

        try:
            return wrapper.store_instance_pattern(
                component_paths=component_paths,
                instance_params=instance_params,
                description=f"Feedback pattern for {container_type}",
                feedback=feedback,
                generate_variations=feedback == "positive",
            )
        except Exception as e:
            logger.warning(f"Failed to store feedback pattern: {e}")
            return None


# Global instance for convenience
_dynamic_feedback_builder: Optional[DynamicFeedbackBuilder] = None


def get_dynamic_feedback_builder() -> DynamicFeedbackBuilder:
    """Get the singleton DynamicFeedbackBuilder instance."""
    global _dynamic_feedback_builder
    if _dynamic_feedback_builder is None:
        _dynamic_feedback_builder = DynamicFeedbackBuilder()
    return _dynamic_feedback_builder


__all__ = [
    "DynamicFeedbackBuilder",
    "get_dynamic_feedback_builder",
]
