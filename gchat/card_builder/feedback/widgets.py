"""
Feedback widget builders — extracted from SmartCardBuilderV2.

All functions accept a `builder` parameter (SmartCardBuilderV2 instance) where
they need access to _build_component, _get_wrapper, or _convert_to_camel_case.
Pure helper functions that don't need `builder` are standalone.
"""

import random
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger
from config.settings import settings as _settings

from gchat.card_builder.feedback.icons import (
    FEEDBACK_MATERIAL_ICONS,
    NEGATIVE_IMAGE_URLS,
    NEGATIVE_MATERIAL_ICONS,
    POSITIVE_IMAGE_URLS,
    POSITIVE_MATERIAL_ICONS,
)
from gchat.card_builder.feedback.prompts import (
    CONTENT_FEEDBACK_PROMPTS,
    FEEDBACK_COLORS,
    FEEDBACK_TEXT_STYLES,
    FORM_FEEDBACK_PROMPTS,
    NEGATIVE_LABELS,
    POSITIVE_LABELS,
)
from gchat.card_builder.feedback.registries import (
    CLICK_CONFIGS,
    LAYOUT_CONFIGS,
    TEXT_CONFIGS,
)
from gchat.card_builder.feedback.components import BUTTON_TYPES

logger = setup_logger()

# Icon list registry — maps config source names to actual lists for
# _resolve_config_icon (replaces the globals() lookup from builder_v2).
_ICON_LISTS: Dict[str, List[str]] = {
    "POSITIVE_MATERIAL_ICONS": POSITIVE_MATERIAL_ICONS,
    "NEGATIVE_MATERIAL_ICONS": NEGATIVE_MATERIAL_ICONS,
    "POSITIVE_IMAGE_URLS": POSITIVE_IMAGE_URLS,
    "NEGATIVE_IMAGE_URLS": NEGATIVE_IMAGE_URLS,
}


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def get_feedback_base_url() -> str:
    """Get the feedback base URL from settings.

    Uses the server's base_url with /card-feedback endpoint.
    Falls back to placeholder only if base_url is not configured.
    """
    base_url = getattr(_settings, "feedback_base_url", "") or getattr(
        _settings, "base_url", ""
    )
    if base_url:
        return f"{base_url}/card-feedback"
    return "https://feedback.example.com"


def make_callback_url(card_id: str, feedback_val: str, feedback_type: str) -> str:
    """Create feedback callback URL."""
    base_url = get_feedback_base_url()
    return f"{base_url}?card_id={card_id}&feedback={feedback_val}&feedback_type={feedback_type}"


# ---------------------------------------------------------------------------
# Generic feedback widget builder
# ---------------------------------------------------------------------------


def build_feedback_widget(
    builder,
    component_name: str,
    params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Build a feedback widget using the unified _build_component method.

    Thin wrapper that ensures wrap_with_key=True for feedback widgets,
    which need the full {jsonKey: innerDict} format.

    Args:
        builder: SmartCardBuilderV2 instance
        component_name: Component type (e.g., "TextParagraph", "DecoratedText")
        params: Parameters for the component

    Returns:
        Widget dict in Google Chat format: {jsonKey: innerDict}
    """
    return builder._build_component(component_name, params, wrap_with_key=True)


# ---------------------------------------------------------------------------
# Styling helpers
# ---------------------------------------------------------------------------


def style_feedback_keyword(keyword: str, style: str) -> str:
    """Apply styling to a feedback keyword using HTML.

    Delegates to gchat.card_builder.jinja_styling.style_keyword().
    """
    from gchat.card_builder.jinja_styling import style_keyword

    return style_keyword(keyword, style, FEEDBACK_COLORS)


def build_styled_feedback_prompt(prompt_tuple: tuple) -> str:
    """Build a feedback prompt with randomly styled keyword.

    Args:
        prompt_tuple: (template, keyword) from CONTENT_FEEDBACK_PROMPTS or FORM_FEEDBACK_PROMPTS

    Returns:
        Formatted prompt string with styled keyword
    """
    template, keyword = prompt_tuple
    style = random.choice(FEEDBACK_TEXT_STYLES)
    styled_keyword = style_feedback_keyword(keyword, style)
    return template.format(keyword=styled_keyword)


# ---------------------------------------------------------------------------
# Text component builders
# ---------------------------------------------------------------------------


def build_text_feedback(builder, text_type: str, text: str, **kwargs) -> Dict:
    """Unified config-driven text builder — replaces 5 individual text methods.

    Uses TEXT_CONFIGS to determine component type and formatting.

    Args:
        builder: SmartCardBuilderV2 instance
        text_type: Key in TEXT_CONFIGS (e.g., "text_paragraph", "decorated_text")
        text: Text content to display
        **kwargs: Additional params (e.g., label for decorated_text_labeled)

    Returns:
        Widget dict (e.g., {"textParagraph": {"text": "..."}})
    """
    config = TEXT_CONFIGS.get(text_type)
    if not config:
        config = TEXT_CONFIGS["text_paragraph"]

    # Handle direct dict components (chip_text — display-only prompt chip)
    if config.get("direct_dict"):
        chip_item = build_feedback_chip_item(builder, text, "")
        chip_item["onClick"] = {"action": {"function": "noop"}}
        chip_item["enabled"] = False
        return {"chipList": {"chips": [chip_item]}}

    # Apply text formatting if configured
    format_fn = config.get("format_text")
    formatted_text = format_fn(text) if format_fn else text

    # Build params
    component_name = config["component"]
    params = {"text": formatted_text}
    if config.get("wrap_text"):
        params["wrap_text"] = True
    if config.get("top_label") or kwargs.get("label"):
        params["top_label"] = kwargs.get("label") or config.get("top_label")

    # Build widget
    widget = build_feedback_widget(builder, component_name, params)

    # Add icon if configured
    if config.get("add_random_icon") and widget and "decoratedText" in widget:
        from gchat.card_builder.rendering import build_start_icon

        icon_name = random.choice(FEEDBACK_MATERIAL_ICONS)
        widget["decoratedText"]["startIcon"] = build_start_icon(icon_name)

    return widget


# Convenience wrappers
def text_paragraph(builder, text: str, **_kwargs) -> Dict:
    return build_text_feedback(builder, "text_paragraph", text)


def text_decorated(builder, text: str, **_kwargs) -> Dict:
    return build_text_feedback(builder, "decorated_text", text)


def text_decorated_icon(builder, text: str, **_kwargs) -> Dict:
    return build_text_feedback(builder, "decorated_text_icon", text)


def text_decorated_labeled(builder, text: str, label: str = "Feedback", **_kwargs) -> Dict:
    return build_text_feedback(builder, "decorated_text_labeled", text, label=label)


def text_chip(builder, text: str, **_kwargs) -> Dict:
    return build_text_feedback(builder, "chip_text", text)


# ---------------------------------------------------------------------------
# Clickable component builders
# ---------------------------------------------------------------------------


def build_clickable_item(
    builder,
    component_name: str,
    label: str,
    url: str,
    *,
    icon: Optional[str] = None,
    icon_url: Optional[str] = None,
    material_icon: Optional[str] = None,
    button_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a single clickable item (Button or Chip) with onClick via wrapper.

    Args:
        builder: SmartCardBuilderV2 instance
        component_name: "Button" or "Chip"
        label: Display text (Button.text or Chip.label)
        url: Callback URL for onClick
        icon: Known icon name (legacy)
        icon_url: URL for custom icon image
        material_icon: Material icon name (preferred)
        button_type: Button style (only for Button)
    """
    is_button = component_name == "Button"
    wrapper = builder._get_wrapper()
    if wrapper:
        try:
            Cls = wrapper.get_cached_class(component_name)
            OnClick = wrapper.get_cached_class("OnClick")
            OpenLink = wrapper.get_cached_class("OpenLink")

            if all([Cls, OnClick, OpenLink]):
                open_link = OpenLink(url=url)
                on_click = OnClick(open_link=open_link)
                kwargs = {"text": label} if is_button else {"label": label}
                instance = Cls(on_click=on_click, **kwargs)

                if hasattr(instance, "to_dict"):
                    item_dict = builder._convert_to_camel_case(instance.to_dict())
                    if is_button:
                        apply_button_icon(
                            item_dict, material_icon, icon, icon_url
                        )
                        if button_type:
                            item_dict["type"] = button_type
                    return item_dict
        except Exception as e:
            logger.debug(f"Wrapper {component_name} build failed: {e}")

    # Fallback to manual dict
    label_key = "text" if is_button else "label"
    item = {label_key: label, "onClick": {"openLink": {"url": url}}}
    if is_button:
        apply_button_icon(item, material_icon, icon, icon_url)
        if button_type:
            item["type"] = button_type
    return item


def apply_button_icon(
    btn: Dict[str, Any],
    material_icon: Optional[str],
    icon: Optional[str],
    icon_url: Optional[str],
) -> None:
    """Apply the best-available icon to a button dict (mutates in place)."""
    if material_icon:
        btn["icon"] = {"materialIcon": {"name": material_icon}}
    elif icon:
        btn["icon"] = {"knownIcon": icon}
    elif icon_url:
        btn["icon"] = {"iconUrl": icon_url}


def build_feedback_button_item(
    builder,
    text: str,
    url: str,
    icon: Optional[str] = None,
    icon_url: Optional[str] = None,
    material_icon: Optional[str] = None,
    button_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a single button item — delegates to build_clickable_item."""
    return build_clickable_item(
        builder,
        "Button",
        text,
        url,
        icon=icon,
        icon_url=icon_url,
        material_icon=material_icon,
        button_type=button_type,
    )


def build_feedback_chip_item(builder, label: str, url: str) -> Dict[str, Any]:
    """Build a single chip item — delegates to build_clickable_item."""
    return build_clickable_item(builder, "Chip", label, url)


def resolve_config_icon(
    config: Dict, static_key: Optional[str], source_key: str
) -> Optional[str]:
    """Resolve an icon from a config dict — returns a static value or random choice from a named list."""
    if source_key and config.get(source_key):
        icon_list = _ICON_LISTS.get(config[source_key], [])
        return random.choice(icon_list) if icon_list else None
    if static_key:
        return config.get(static_key)
    return None


def build_clickable_feedback(
    builder, handler_type: str, card_id: str, feedback_type: str
) -> Dict:
    """Unified config-driven click handler — replaces 7 individual methods.

    Uses CLICK_CONFIGS to determine widget structure, icons, and behavior.

    Args:
        builder: SmartCardBuilderV2 instance
        handler_type: Key in CLICK_CONFIGS (e.g., "button_list", "star_rating")
        card_id: Card ID for callback URL
        feedback_type: Feedback type for callback URL

    Returns:
        Widget dict (e.g., {"buttonList": {"buttons": [...]}})
    """
    config = CLICK_CONFIGS.get(handler_type)
    if not config:
        config = CLICK_CONFIGS["button_list"]

    widget_key = config["widget"]
    items_key = config["items_key"]
    use_chips = config.get("use_chips", False)
    btn_type = config.get("button_type") or random.choice(BUTTON_TYPES)

    items = []

    if config.get("binary", True):
        pos_label = random.choice(POSITIVE_LABELS)
        neg_label = random.choice(NEGATIVE_LABELS)
        pos_url = make_callback_url(card_id, "positive", feedback_type)
        neg_url = make_callback_url(card_id, "negative", feedback_type)

        pos_icon = resolve_config_icon(config, "pos_icon", "pos_icon_source")
        neg_icon = resolve_config_icon(config, "neg_icon", "neg_icon_source")
        pos_icon_url = resolve_config_icon(config, None, "pos_icon_url_source")
        neg_icon_url = resolve_config_icon(config, None, "neg_icon_url_source")

        if use_chips:
            items = [
                build_feedback_chip_item(builder, pos_label, pos_url),
                build_feedback_chip_item(builder, neg_label, neg_url),
            ]
        else:
            items = [
                build_feedback_button_item(
                    builder,
                    pos_label,
                    pos_url,
                    material_icon=pos_icon,
                    icon_url=pos_icon_url,
                    button_type=btn_type,
                ),
                build_feedback_button_item(
                    builder,
                    neg_label,
                    neg_url,
                    material_icon=neg_icon,
                    icon_url=neg_icon_url,
                    button_type=btn_type,
                ),
            ]
    else:
        ratings = config.get("ratings", [])
        for icon_name, label, rating_value in ratings:
            url = make_callback_url(card_id, rating_value, feedback_type)
            btn = build_feedback_button_item(
                builder, label, url, material_icon=icon_name, button_type=btn_type
            )
            items.append(btn)

    return {widget_key: {items_key: items}}


# Click convenience wrappers
def click_button_list(builder, card_id: str, feedback_type: str, **_kwargs) -> Dict:
    return build_clickable_feedback(builder, "button_list", card_id, feedback_type)


def click_chip_list(builder, card_id: str, feedback_type: str, **_kwargs) -> Dict:
    return build_clickable_feedback(builder, "chip_list", card_id, feedback_type)


def click_icon_buttons(builder, card_id: str, feedback_type: str, **_kwargs) -> Dict:
    return build_clickable_feedback(builder, "icon_buttons", card_id, feedback_type)


def click_icon_buttons_alt(builder, card_id: str, feedback_type: str, **_kwargs) -> Dict:
    return build_clickable_feedback(builder, "icon_buttons_alt", card_id, feedback_type)


def click_url_image_buttons(builder, card_id: str, feedback_type: str, **_kwargs) -> Dict:
    return build_clickable_feedback(builder, "url_image_buttons", card_id, feedback_type)


def click_star_rating(builder, card_id: str, feedback_type: str, **_kwargs) -> Dict:
    return build_clickable_feedback(builder, "star_rating", card_id, feedback_type)


def click_emoji_rating(builder, card_id: str, feedback_type: str, **_kwargs) -> Dict:
    return build_clickable_feedback(builder, "emoji_rating", card_id, feedback_type)


# ---------------------------------------------------------------------------
# Dual component builders (text + click in one widget)
# ---------------------------------------------------------------------------


def dual_decorated_with_button(
    builder, text: str, card_id: str, feedback_type: str, **_kwargs
) -> List[Dict]:
    """Decorated text with inline positive button + inline negative button.

    Uses short icon-only labels for inline buttons to avoid truncation.
    Both buttons are placed in the decoratedText.button slot (positive) and
    a compact ButtonList (both pos + neg) to avoid orphaned single-button rows.
    """
    from gchat.card_builder.rendering import build_start_icon

    pos_url = make_callback_url(card_id, "positive", feedback_type)
    neg_url = make_callback_url(card_id, "negative", feedback_type)
    icon_name = random.choice(FEEDBACK_MATERIAL_ICONS)
    btn_type = random.choice(BUTTON_TYPES)

    # Build decorated text with short inline positive button
    decorated_widget = build_feedback_widget(
        builder, "DecoratedText", {"text": text, "wrap_text": True}
    )
    if decorated_widget and "decoratedText" in decorated_widget:
        decorated_widget["decoratedText"]["startIcon"] = build_start_icon(icon_name)
        decorated_widget["decoratedText"]["button"] = build_feedback_button_item(
            builder, "\U0001f44d", pos_url, button_type=btn_type
        )

    # Build compact ButtonList with both buttons
    pos_button = build_feedback_button_item(
        builder, "\U0001f44d Yes", pos_url, button_type=btn_type
    )
    neg_button = build_feedback_button_item(
        builder, "\U0001f44e No", neg_url, button_type=btn_type
    )
    wrapper = builder._get_wrapper()
    button_list_widget = builder._build_component(
        "ButtonList",
        {},
        wrapper=wrapper,
        wrap_with_key=True,
    )
    if button_list_widget and "buttonList" in button_list_widget:
        button_list_widget["buttonList"]["buttons"] = [pos_button, neg_button]
    else:
        button_list_widget = {"buttonList": {"buttons": [pos_button, neg_button]}}

    return [decorated_widget, button_list_widget]


def dual_decorated_inline_only(
    builder, text: str, card_id: str, feedback_type: str, **_kwargs
) -> List[Dict]:
    """Most compact: DecoratedText with single inline button (1 widget total).

    Uses DecoratedText's built-in button property for maximum compactness.
    Only shows positive button inline — negative is implied by not clicking.
    Uses short label to avoid truncation in the inline button slot.
    """
    pos_url = make_callback_url(card_id, "positive", feedback_type)
    btn_type = random.choice(BUTTON_TYPES)

    decorated_widget = build_feedback_widget(
        builder, "DecoratedText", {"text": text, "wrap_text": True}
    )
    if decorated_widget and "decoratedText" in decorated_widget:
        decorated_widget["decoratedText"]["button"] = build_feedback_button_item(
            builder, "\U0001f44d", pos_url, button_type=btn_type
        )

    return [decorated_widget]


def dual_columns_inline(
    builder, text: str, card_id: str, feedback_type: str, **_kwargs
) -> List[Dict]:
    """Columns with text left, buttons right (all in one widget) — uses wrapper."""
    pos_label = random.choice(POSITIVE_LABELS)
    neg_label = random.choice(NEGATIVE_LABELS)
    pos_url = make_callback_url(card_id, "positive", feedback_type)
    neg_url = make_callback_url(card_id, "negative", feedback_type)
    btn_type = random.choice(BUTTON_TYPES)

    text_widget = build_feedback_widget(
        builder, "DecoratedText", {"text": text, "wrap_text": True}
    )

    buttons = [
        build_feedback_button_item(builder, pos_label, pos_url, button_type=btn_type),
        build_feedback_button_item(builder, neg_label, neg_url, button_type=btn_type),
    ]
    wrapper = builder._get_wrapper()
    button_list_widget = builder._build_component(
        "ButtonList",
        {},
        wrapper=wrapper,
        wrap_with_key=True,
    )
    if button_list_widget and "buttonList" in button_list_widget:
        button_list_widget["buttonList"]["buttons"] = buttons
    else:
        button_list_widget = {"buttonList": {"buttons": buttons}}

    return [
        {
            "columns": {
                "columnItems": [
                    {
                        "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                        "horizontalAlignment": "START",
                        "verticalAlignment": "CENTER",
                        "widgets": [text_widget],
                    },
                    {
                        "horizontalSizeStyle": "FILL_MINIMUM_SPACE",
                        "horizontalAlignment": "END",
                        "verticalAlignment": "CENTER",
                        "widgets": [button_list_widget],
                    },
                ]
            }
        }
    ]


# ---------------------------------------------------------------------------
# Layout wrappers
# ---------------------------------------------------------------------------


def build_feedback_layout(
    layout_type: str,
    content_widgets: List[Dict],
    form_widgets: List[Dict],
    content_first: bool,
) -> List[Dict]:
    """Unified config-driven layout builder — replaces 3 individual layout methods.

    Args:
        layout_type: Key in LAYOUT_CONFIGS (e.g., "sequential", "with_divider")
        content_widgets: Content feedback widgets
        form_widgets: Form/action feedback widgets
        content_first: Whether content should appear first

    Returns:
        Combined list of widgets in the specified layout
    """
    config = LAYOUT_CONFIGS.get(layout_type, {})

    if config.get("group_by_type"):
        texts = [
            w
            for w in content_widgets + form_widgets
            if not any(k in w for k in ["buttonList", "chipList", "grid"])
        ]
        buttons = [
            w
            for w in content_widgets + form_widgets
            if any(k in w for k in ["buttonList", "chipList", "grid"])
        ]
        return texts + buttons if content_first else buttons + texts

    first, second = (
        (content_widgets, form_widgets)
        if content_first
        else (form_widgets, content_widgets)
    )

    if config.get("add_divider"):
        return first + [{"divider": {}}] + second
    return first + second


def layout_sequential(
    content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
) -> List[Dict]:
    return build_feedback_layout("sequential", content_widgets, form_widgets, content_first)


def layout_with_divider(
    content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
) -> List[Dict]:
    return build_feedback_layout("with_divider", content_widgets, form_widgets, content_first)


def layout_compact(
    content_widgets: List[Dict], form_widgets: List[Dict], content_first: bool
) -> List[Dict]:
    return build_feedback_layout("compact", content_widgets, form_widgets, content_first)


# ---------------------------------------------------------------------------
# Modular assembly — main entry point
# ---------------------------------------------------------------------------


def create_feedback_section(builder, card_id: str) -> Dict:
    """Create feedback section by randomly assembling components.

    Assembly process:
    1. Select text component type for content feedback
    2. Select text component type for form feedback
    3. Select clickable component type for content feedback
    4. Select clickable component type for form feedback
    5. Select layout wrapper
    6. Select order (content first vs form first)

    This creates massive variety for training data collection.

    Args:
        builder: SmartCardBuilderV2 instance
        card_id: Unique card identifier
    """
    from gchat.card_builder.rendering import build_material_icon

    # Component registries with builder methods (partial-apply builder)
    text_builders = {
        "text_paragraph": lambda t, **kw: text_paragraph(builder, t, **kw),
        "decorated_text": lambda t, **kw: text_decorated(builder, t, **kw),
        "decorated_text_icon": lambda t, **kw: text_decorated_icon(builder, t, **kw),
        "decorated_text_labeled": lambda t, **kw: text_decorated_labeled(builder, t, **kw),
        "chip_text": lambda t, **kw: text_chip(builder, t, **kw),
    }

    click_builders = {
        "button_list": lambda cid, ft, **kw: click_button_list(builder, cid, ft, **kw),
        "chip_list": lambda cid, ft, **kw: click_chip_list(builder, cid, ft, **kw),
        "icon_buttons": lambda cid, ft, **kw: click_icon_buttons(builder, cid, ft, **kw),
        "icon_buttons_alt": lambda cid, ft, **kw: click_icon_buttons_alt(builder, cid, ft, **kw),
        "url_image_buttons": lambda cid, ft, **kw: click_url_image_buttons(builder, cid, ft, **kw),
        "star_rating": lambda cid, ft, **kw: click_star_rating(builder, cid, ft, **kw),
        "emoji_rating": lambda cid, ft, **kw: click_emoji_rating(builder, cid, ft, **kw),
    }

    dual_builders = {
        "decorated_with_button": lambda t, cid, ft, **kw: dual_decorated_with_button(builder, t, cid, ft, **kw),
        "columns_inline": lambda t, cid, ft, **kw: dual_columns_inline(builder, t, cid, ft, **kw),
        "decorated_inline_only": lambda t, cid, ft, **kw: dual_decorated_inline_only(builder, t, cid, ft, **kw),
    }

    layout_builders = {
        "sequential": layout_sequential,
        "with_divider": layout_with_divider,
        "compact": layout_compact,
    }

    # Random selections
    content_text_type = random.choice(list(text_builders.keys()))
    form_text_type = random.choice(list(text_builders.keys()))
    content_click_type = random.choice(list(click_builders.keys()))
    form_click_type = random.choice(list(click_builders.keys()))
    layout_type = random.choice(list(layout_builders.keys()))
    content_first = random.choice([True, False])
    section_style = "collapsible_0"

    # Occasionally use dual components (30% chance)
    use_dual_content = random.random() < 0.3
    use_dual_form = random.random() < 0.3

    # Build content feedback widgets with styled prompt
    content_prompt_tuple = random.choice(CONTENT_FEEDBACK_PROMPTS)
    content_prompt = build_styled_feedback_prompt(content_prompt_tuple)
    content_style = content_prompt_tuple[1]

    if use_dual_content:
        dual_type = random.choice(list(dual_builders.keys()))
        content_widgets = dual_builders[dual_type](content_prompt, card_id, "content")
        content_text_type = f"dual:{dual_type}"
        content_click_type = f"dual:{dual_type}"
    else:
        content_widgets = [
            text_builders[content_text_type](content_prompt, label="Content"),
            click_builders[content_click_type](card_id, "content"),
        ]

    # Build form feedback widgets with styled prompt
    form_prompt_tuple = random.choice(FORM_FEEDBACK_PROMPTS)
    form_prompt = build_styled_feedback_prompt(form_prompt_tuple)
    form_style = form_prompt_tuple[1]

    if use_dual_form:
        dual_type = random.choice(list(dual_builders.keys()))
        form_widgets = dual_builders[dual_type](form_prompt, card_id, "form")
        form_text_type = f"dual:{dual_type}"
        form_click_type = f"dual:{dual_type}"
    else:
        form_widgets = [
            text_builders[form_text_type](form_prompt, label="Layout"),
            click_builders[form_click_type](card_id, "form"),
        ]

    # Apply layout
    widgets = layout_builders[layout_type](
        content_widgets, form_widgets, content_first
    )

    # Build metadata for training
    assembly_metadata = {
        "content_text": content_text_type,
        "content_click": content_click_type,
        "content_keyword": content_style,
        "form_text": form_text_type,
        "form_click": form_click_type,
        "form_keyword": form_style,
        "layout": layout_type,
        "content_first": content_first,
        "section_style": section_style,
    }

    logger.debug(f"\U0001f3b2 Feedback assembly: {assembly_metadata}")

    section = {
        "widgets": widgets,
        "collapsible": True,
        "uncollapsibleWidgetsCount": 0,
        "collapseControl": {
            "horizontalAlignment": "START",
            "expandButton": {
                "text": "Share Card Feedback",
                "icon": build_material_icon("arrow_cool_down"),
                "type": "BORDERLESS",
            },
            "collapseButton": {
                "text": "Hide Feedback",
                "icon": build_material_icon("keyboard_double_arrow_up"),
                "type": "BORDERLESS",
            },
        },
        "_feedback_assembly": assembly_metadata,
    }

    return section


__all__ = [
    # URL helpers
    "get_feedback_base_url",
    "make_callback_url",
    # Generic builder
    "build_feedback_widget",
    # Styling
    "style_feedback_keyword",
    "build_styled_feedback_prompt",
    # Text builders
    "build_text_feedback",
    "text_paragraph",
    "text_decorated",
    "text_decorated_icon",
    "text_decorated_labeled",
    "text_chip",
    # Clickable builders
    "build_clickable_item",
    "apply_button_icon",
    "build_feedback_button_item",
    "build_feedback_chip_item",
    "resolve_config_icon",
    "build_clickable_feedback",
    "click_button_list",
    "click_chip_list",
    "click_icon_buttons",
    "click_icon_buttons_alt",
    "click_url_image_buttons",
    "click_star_rating",
    "click_emoji_rating",
    # Dual builders
    "dual_decorated_with_button",
    "dual_decorated_inline_only",
    "dual_columns_inline",
    # Layout builders
    "build_feedback_layout",
    "layout_sequential",
    "layout_with_divider",
    "layout_compact",
    # Assembly
    "create_feedback_section",
]
