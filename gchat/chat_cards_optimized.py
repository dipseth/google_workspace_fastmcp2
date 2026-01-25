"""
Google Chat Card Manager - Optimized for Card Framework Integration
Provides rich card-based messaging capabilities for Google Chat with graceful fallback.
"""

import json

from typing_extensions import Any, Dict, List, Optional, Tuple, Union

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Try to import Card Framework with graceful fallback
try:
    from card_framework.v2 import Card, CardHeader, Message, Section, Widget
    from card_framework.v2.card import CardWithId
    from card_framework.v2.widgets import (
        Button,
        ButtonList,
        Column,
        Columns,
        DecoratedText,
        Divider,
        Icon,
        Image,
        OnClick,
        OpenLink,
        SelectionInput,
        TextInput,
        TextParagraph,
    )

    CARD_FRAMEWORK_AVAILABLE = True
    logger.info("Card Framework v2 is available for rich card creation")
except ImportError:
    CARD_FRAMEWORK_AVAILABLE = False
    logger.warning("Card Framework v2 not available. Falling back to REST API format.")

    # Define placeholder classes for type hints when Card Framework is not available
    class Card:
        pass

    class Section:
        pass

    class Widget:
        pass


class GoogleChatCardManager:
    """
    Manages creation and formatting of Google Chat cards with Card Framework integration.
    Provides graceful fallback to REST API format when Card Framework is not available.
    """

    def __init__(self):
        """Initialize the card manager."""
        self.framework_available = CARD_FRAMEWORK_AVAILABLE

    def create_rich_card(
        self,
        title: str,
        subtitle: Optional[str] = None,
        image_url: Optional[str] = None,
        sections: Optional[List[Union[Dict[str, Any], str]]] = None,
    ):
        """
        Create a rich card with advanced formatting and sections.

        This method creates a rich card using the Card Framework with support for
        multiple section formats. It handles both dictionary-based section configurations
        and simple string sections, converting them to the appropriate Card Framework objects.

        Args:
            title: Card title
            subtitle: Optional subtitle
            image_url: Optional image URL
            sections: Optional list of sections, which can be dictionaries or strings

        Returns:
            CardWithId or Dict: A Card Framework card object if framework is available,
                               or a dictionary in the fallback format
        """
        if CARD_FRAMEWORK_AVAILABLE:
            return self._create_rich_card_with_framework(
                title, subtitle, image_url, sections
            )
        else:
            return self._create_rich_card_fallback(title, subtitle, image_url, sections)

    def create_simple_card(
        self,
        title: str,
        subtitle: Optional[str] = None,
        text: str = "",
        image_url: Optional[str] = None,
    ):
        """
        Create a simple card with title, subtitle, text, and optional image.

        Args:
            title: Card title
            subtitle: Optional subtitle
            text: Main text content
            image_url: Optional image URL

        Returns:
            CardWithId object if framework available, Dict otherwise
        """
        if self.framework_available:
            return self._create_simple_card_with_framework(
                title, subtitle, text, image_url
            )
        else:
            return self._create_simple_card_fallback(title, subtitle, text, image_url)

    def _create_simple_card_with_framework(
        self,
        title: str,
        subtitle: Optional[str] = None,
        text: str = "",
        image_url: Optional[str] = None,
    ) -> CardWithId:
        """Create simple card using Card Framework."""
        try:
            # Create card header
            header = CardHeader(title=title, subtitle=subtitle, image_url=image_url)

            # Create sections
            sections = []

            # Add content section if text is provided
            if text:
                content_widgets = [TextParagraph(text=text)]
                content_section = Section(widgets=content_widgets)
                sections.append(content_section)

            # Create the card with CardWithId
            card = CardWithId(
                name=f"simple_card_{title.lower().replace(' ', '_')}",
                header=header,
                sections=sections,
            )
            card.card_id = f"simple_{hash(title + text)}"

            logger.debug(f"Card Framework simple card created: {card.card_id}")
            return card

        except Exception as e:
            logger.error(f"Error creating simple card with framework: {e}")
            # Return fallback as dictionary since we can't return CardWithId in fallback
            raise e

    def _create_rich_card_with_framework(
        self,
        title: str,
        subtitle: Optional[str] = None,
        image_url: Optional[str] = None,
        sections: Optional[List[Union[Dict[str, Any], str]]] = None,
    ) -> CardWithId:
        """Create rich card using Card Framework with advanced widgets."""
        try:
            # Log the image URL for debugging
            logger.debug(f"Creating rich card with image_url: {image_url}")

            # Create card header
            header = CardHeader(
                title=title,
                subtitle=subtitle or "Rich Card with Advanced Features",
                image_url=image_url,  # Explicitly pass the image_url parameter, which might be None
            )

            # Log the header for debugging
            logger.debug(f"Created header with image_url: {header.image_url}")

            # Create the card with CardWithId
            card = CardWithId(
                name=f"rich_card_{title.lower().replace(' ', '_').replace('!', '').replace('🎉', 'celebration')}",
                header=header,
                sections=[],
            )
            card.card_id = f"rich_{hash(title + str(sections))}"

            # Log the card header after creation
            logger.debug(f"Card created with header image_url: {card.header.image_url}")

            # Process sections if provided
            if sections:
                for section_config in sections:
                    section = self._create_section_from_config(section_config)
                    if section:
                        card.sections.append(section)
            else:
                # Default section with rich content
                default_section = Section(
                    header="Rich Card Features",
                    widgets=[
                        TextParagraph(
                            text="<b>This is a rich card</b> with <i>advanced formatting</i> and <font color='#0066CC'>colored text</font>."
                        ),
                        Divider(),
                        DecoratedText(
                            start_icon=Icon(known_icon=Icon.KnownIcon.STAR),
                            text="<b>Enhanced with Card Framework v2</b><br>Supports rich widgets and interactions",
                            top_label="Card Framework v2",
                            bottom_label="Advanced Features Available",
                            wrap_text=True,
                        ),
                    ],
                    collapsible=False,
                )
                card.sections.append(default_section)

            logger.debug(f"Card Framework rich card created: {card.card_id}")
            return card

        except Exception as e:
            logger.error(f"Error creating Card Framework rich card: {e}")
            # Fallback to simple card
            return self._create_simple_card_with_framework(
                title, subtitle, "Rich card fallback", image_url
            )

    def _create_section_from_string(self, section_text: str) -> Section:
        """
        Create a Section from a string.

        This method converts a simple string into a properly formatted Section object
        with a TextParagraph widget containing the string text. This allows for simple
        string sections to be used alongside more complex dictionary-based section configs.

        Args:
            section_text: The string text to convert into a section

        Returns:
            Section: A Card Framework Section object with a TextParagraph widget
        """
        logger.debug(f"Creating section from string: {section_text}")
        text_widget = TextParagraph(text=section_text)
        return Section(widgets=[text_widget])

    def _create_section_from_config(
        self, section_config: Union[Dict[str, Any], str]
    ) -> Optional[Section]:
        """
        Create a Section from configuration dictionary or string.

        This method handles multiple section formats:
        1. String sections - Converted to sections with TextParagraph widgets
        2. Dictionary with widgets array - Direct section configuration
        3. Dictionary with title and content - Creates a section with TextParagraph
        4. Dictionary with text field - Creates a section with TextParagraph

        The method includes enhanced error handling with fallback sections for errors.

        Args:
            section_config: Either a string or dictionary configuration for the section

        Returns:
            Section: A Card Framework Section object, or None if creation fails
        """
        try:
            # Handle string sections
            if isinstance(section_config, str):
                return self._create_section_from_string(section_config)

            # Log the incoming section config for debugging
            logger.debug(
                f"Creating section from config: {json.dumps(section_config, indent=2)}"
            )

            widgets = []

            # Handle different section formats
            # Format 1: Direct section config with widgets array
            if "widgets" in section_config:
                logger.debug(
                    f"Processing section with widgets array, found {len(section_config.get('widgets', []))} widgets"
                )
                for widget_config in section_config.get("widgets", []):
                    widget = self._create_widget_from_config(widget_config)
                    if widget:
                        widgets.append(widget)
                    else:
                        logger.warning(
                            f"Failed to create widget from config: {json.dumps(widget_config, indent=2)}"
                        )
            # Format 2: Section with title and content
            elif "title" in section_config and "content" in section_config:
                logger.debug("Processing section with title and content")
                # Create a text paragraph widget from content
                text_widget = TextParagraph(text=section_config.get("content", ""))
                widgets.append(text_widget)
            # Format 3: Section with just text content as string
            elif isinstance(section_config.get("text"), str):
                logger.debug("Processing section with text field")
                text_widget = TextParagraph(text=section_config.get("text", ""))
                widgets.append(text_widget)

            # Get header from either header or title field
            header = section_config.get("header", section_config.get("title"))
            logger.debug(f"Section header: {header}")

            # Create section
            section = Section(
                header=header,
                widgets=widgets,
                collapsible=section_config.get("collapsible", False),
            )

            logger.debug(f"Created section with {len(widgets)} widgets")
            return section

        except Exception as e:
            if isinstance(section_config, dict):
                logger.error(f"Error creating section from config: {e}")
                logger.debug(
                    f"Section config that caused error: {json.dumps(section_config, indent=2)}"
                )
            else:
                logger.error(f"Error creating section from {type(section_config)}: {e}")
                logger.debug(f"Section content that caused error: {section_config}")

            # Try to create a fallback section with error information
            try:
                error_text = f"Error creating section: {str(e)}"
                logger.info("Creating fallback section with error information")
                return Section(widgets=[TextParagraph(text=error_text)])
            except Exception as fallback_error:
                logger.error(f"Failed to create fallback section: {fallback_error}")
                return None

    # =========================================================================
    # WIDGET TYPE REGISTRY - Maps keys to normalized types and nested keys
    # This enables recursive self-discovery of widget types at any depth
    # =========================================================================
    WIDGET_TYPE_REGISTRY = {
        # camelCase keys (from Google Chat API / JSON)
        "buttonList": {"normalized": "button_list", "nested_key": "buttonList"},
        "selectionInput": {"normalized": "selection_input", "nested_key": "selectionInput"},
        "textParagraph": {"normalized": "text_paragraph", "nested_key": "textParagraph"},
        "decoratedText": {"normalized": "decorated_text", "nested_key": "decoratedText"},
        "image": {"normalized": "image", "nested_key": "image"},
        "columns": {"normalized": "columns", "nested_key": "columns"},
        "divider": {"normalized": "divider", "nested_key": "divider"},
        "grid": {"normalized": "grid", "nested_key": "grid"},
        "textInput": {"normalized": "text_input", "nested_key": "textInput"},
        "dateTimePicker": {"normalized": "date_time_picker", "nested_key": "dateTimePicker"},
        # snake_case keys (from Python code)
        "button_list": {"normalized": "button_list", "nested_key": "buttonList"},
        "selection_input": {"normalized": "selection_input", "nested_key": "selectionInput"},
        "text_paragraph": {"normalized": "text_paragraph", "nested_key": "textParagraph"},
        "decorated_text": {"normalized": "decorated_text", "nested_key": "decoratedText"},
        "text_input": {"normalized": "text_input", "nested_key": "textInput"},
        "date_time_picker": {"normalized": "date_time_picker", "nested_key": "dateTimePicker"},
    }

    def _discover_widget_type(
        self,
        config: Dict[str, Any],
        path: str = "root",
        depth: int = 0,
        max_depth: int = 5,
    ) -> Tuple[Optional[str], Dict[str, Any], str]:
        """
        Recursively discover widget type from a config dict at any nesting level.

        This is the core self-discovery function that:
        1. Checks for explicit 'type' field
        2. Scans keys for known widget types
        3. Recursively searches nested dicts if not found at current level

        Args:
            config: Configuration dictionary to search
            path: Current path for debugging (e.g., "root.widgets[0]")
            depth: Current recursion depth
            max_depth: Maximum recursion depth to prevent infinite loops

        Returns:
            Tuple of (normalized_type, unwrapped_config, discovery_path)
            - normalized_type: The snake_case widget type (e.g., "button_list")
            - unwrapped_config: The innermost config dict for this widget
            - discovery_path: Path where the type was discovered
        """
        if depth > max_depth:
            logger.warning(f"Max depth {max_depth} reached at {path}, stopping discovery")
            return None, config, path

        # 1. Check for explicit 'type' field
        if "type" in config:
            type_value = config["type"]
            if type_value in self.WIDGET_TYPE_REGISTRY:
                normalized = self.WIDGET_TYPE_REGISTRY[type_value]["normalized"]
                logger.debug(f"🔍 [{path}] Found type field: {type_value} → {normalized}")
                return normalized, config, path

        # 2. Scan keys for known widget types
        for key in config.keys():
            if key in self.WIDGET_TYPE_REGISTRY:
                registry_entry = self.WIDGET_TYPE_REGISTRY[key]
                normalized = registry_entry["normalized"]
                nested_key = registry_entry["nested_key"]

                # Unwrap nested config if present
                if nested_key in config and isinstance(config[nested_key], dict):
                    unwrapped = config[nested_key]
                    logger.debug(f"🔍 [{path}] Found key '{key}' with nested config → {normalized}")
                    return normalized, unwrapped, f"{path}.{nested_key}"
                else:
                    logger.debug(f"🔍 [{path}] Found key '{key}' → {normalized}")
                    return normalized, config, path

        # 3. Recursively search nested dicts (for deeply nested structures)
        for key, value in config.items():
            if isinstance(value, dict) and key not in ("onClick", "on_click", "openLink", "open_link"):
                nested_path = f"{path}.{key}"
                result_type, result_config, result_path = self._discover_widget_type(
                    value, nested_path, depth + 1, max_depth
                )
                if result_type:
                    logger.debug(f"🔍 [{path}] Found nested widget at {result_path}")
                    return result_type, result_config, result_path

        # 4. Not found at any level
        logger.debug(f"🔍 [{path}] No widget type discovered (keys: {list(config.keys())})")
        return None, config, path

    def _extract_nested_value(
        self,
        config: Dict[str, Any],
        *keys: str,
        default: Any = None,
    ) -> Any:
        """
        Recursively extract a value from nested dict, trying multiple key variations.

        Args:
            config: Dict to search
            *keys: Key names to try (e.g., "image_url", "imageUrl")
            default: Default value if not found

        Returns:
            The found value or default
        """
        for key in keys:
            if key in config:
                return config[key]
            # Try nested one level (for unwrapped configs)
            for nested_key in config:
                if isinstance(config[nested_key], dict) and key in config[nested_key]:
                    return config[nested_key][key]
        return default

    def _create_widget_from_config(
        self,
        widget_config: Dict[str, Any],
        path: str = "root",
        depth: int = 0,
    ) -> Optional[Any]:
        """
        Create a widget from configuration dictionary using recursive self-discovery.

        This method:
        1. Discovers widget type at any nesting level
        2. Unwraps nested configs automatically
        3. Recursively processes nested widgets (columns, grids, etc.)
        4. Tracks discovery path for debugging

        Args:
            widget_config: Configuration dictionary (any nesting level)
            path: Current path for debugging
            depth: Current recursion depth

        Returns:
            Instantiated widget or None if creation fails
        """
        try:
            logger.debug(f"📦 [{path}] Creating widget (depth={depth})")

            # STEP 1: Discover widget type using recursive self-discovery
            widget_type, unwrapped_config, discovery_path = self._discover_widget_type(
                widget_config, path, depth
            )

            if not widget_type:
                logger.warning(f"⚠️ [{path}] Could not discover widget type")
                logger.debug(f"Config keys: {list(widget_config.keys())}")
                return TextParagraph(text=f"Unknown widget at {path}")

            logger.debug(f"✅ [{discovery_path}] Discovered: {widget_type}")

            # STEP 2: Create widget based on discovered type
            # Each handler uses unwrapped_config which is already at the right level

            if widget_type == "text_paragraph":
                text = self._extract_nested_value(unwrapped_config, "text", default="")
                return TextParagraph(text=text)

            elif widget_type == "decorated_text":
                icon = None
                icon_name = self._extract_nested_value(
                    unwrapped_config, "start_icon", "startIcon"
                )
                if icon_name and hasattr(Icon.KnownIcon, icon_name):
                    icon = Icon(known_icon=getattr(Icon.KnownIcon, icon_name))

                on_click = None
                if unwrapped_config.get("clickable") and unwrapped_config.get("url"):
                    on_click = OnClick(
                        open_link=OpenLink(url=unwrapped_config["url"])
                    )

                return DecoratedText(
                    start_icon=icon,
                    text=self._extract_nested_value(unwrapped_config, "text", default=""),
                    top_label=self._extract_nested_value(unwrapped_config, "top_label", "topLabel"),
                    bottom_label=self._extract_nested_value(unwrapped_config, "bottom_label", "bottomLabel"),
                    wrap_text=self._extract_nested_value(unwrapped_config, "wrap_text", "wrapText", default=True),
                    on_click=on_click,
                )

            elif widget_type == "button_list":
                buttons = []
                buttons_config = self._extract_nested_value(
                    unwrapped_config, "buttons", default=[]
                )

                for idx, button_config in enumerate(buttons_config):
                    # Recursive URL extraction from nested structures
                    url = self._extract_nested_value(button_config, "url")
                    if not url:
                        # Try onClick.openLink.url path
                        on_click_data = self._extract_nested_value(
                            button_config, "onClick", "on_click", default={}
                        )
                        if isinstance(on_click_data, dict):
                            open_link_data = self._extract_nested_value(
                                on_click_data, "openLink", "open_link", default={}
                            )
                            if isinstance(open_link_data, dict):
                                url = open_link_data.get("url")

                    if not url:
                        url = "https://example.com"
                        logger.warning(f"⚠️ [{path}.buttons[{idx}]] No URL found, using fallback")

                    button = Button(
                        text=button_config.get("text", "Button"),
                        on_click=OnClick(open_link=OpenLink(url=url)),
                    )
                    buttons.append(button)

                return ButtonList(buttons=buttons)

            elif widget_type == "selection_input":
                return SelectionInput(
                    name=self._extract_nested_value(unwrapped_config, "name", default="selection"),
                    label=self._extract_nested_value(unwrapped_config, "label", default="Select an option"),
                    items=self._extract_nested_value(unwrapped_config, "items", default=[]),
                )

            elif widget_type == "image":
                on_click = None
                if unwrapped_config.get("clickable") and unwrapped_config.get("url"):
                    on_click = OnClick(open_link=OpenLink(url=unwrapped_config["url"]))

                return Image(
                    image_url=self._extract_nested_value(
                        unwrapped_config, "image_url", "imageUrl", default=""
                    ),
                    alt_text=self._extract_nested_value(
                        unwrapped_config, "alt_text", "altText", default="Image"
                    ),
                    on_click=on_click,
                )

            elif widget_type == "columns":
                # RECURSIVE: Process nested column widgets
                column_items = []
                columns_config = self._extract_nested_value(
                    unwrapped_config, "columns", "column_items", default=[]
                )

                for col_idx, column_config in enumerate(columns_config):
                    column_widgets = []
                    widgets_config = self._extract_nested_value(
                        column_config, "widgets", default=[]
                    )

                    for widget_idx, col_widget_config in enumerate(widgets_config):
                        # RECURSE with updated path
                        nested_path = f"{path}.columns[{col_idx}].widgets[{widget_idx}]"
                        col_widget = self._create_widget_from_config(
                            col_widget_config, nested_path, depth + 1
                        )
                        if col_widget:
                            column_widgets.append(col_widget)

                    alignment = column_config.get("alignment", "START")
                    h_align = {
                        "START": Column.HorizontalAlignment.START,
                        "CENTER": Column.HorizontalAlignment.CENTER,
                        "END": Column.HorizontalAlignment.END,
                    }.get(alignment, Column.HorizontalAlignment.START)

                    column = Column(horizontal_alignment=h_align, widgets=column_widgets)
                    column_items.append(column)

                return Columns(column_items=column_items)

            elif widget_type == "divider":
                return Divider()

            elif widget_type == "grid":
                # RECURSIVE: Process grid items
                logger.debug(f"🔲 [{path}] Processing grid widget")
                # Grid handling would go here - similar recursive pattern
                return TextParagraph(text="[Grid widget - not yet implemented]")

            else:
                logger.warning(f"⚠️ [{path}] Unhandled widget type: {widget_type}")
                return TextParagraph(text=f"Unhandled: {widget_type}")

        except Exception as e:
            logger.error(f"❌ [{path}] Error creating widget: {e}")
            logger.debug(f"Config: {json.dumps(widget_config, indent=2)}")
            try:
                return TextParagraph(text=f"Error at {path}: {str(e)}")
            except Exception:
                return None

    def _create_rich_card_fallback(
        self,
        title: str,
        subtitle: Optional[str] = None,
        image_url: Optional[str] = None,
        sections: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create rich card using REST API format fallback."""
        # For fallback, create a simple card with enhanced formatting
        return self._create_simple_card_fallback(
            title,
            subtitle,
            "Rich card features not available in fallback mode",
            image_url,
        )

    def _create_simple_card_fallback(
        self,
        title: str,
        subtitle: Optional[str] = None,
        text: str = "",
        image_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create simple card using REST API format fallback."""
        card = {"cardsV2": [{"cardId": "simple-card", "card": {"sections": []}}]}

        # Header section
        if title or subtitle or image_url:
            header_section = {"widgets": []}

            if image_url:
                header_section["widgets"].append(
                    {"image": {"imageUrl": image_url, "altText": title}}
                )

            if title:
                header_section["widgets"].append(
                    {"textParagraph": {"text": f"<b>{title}</b>"}}
                )

            if subtitle:
                header_section["widgets"].append({"textParagraph": {"text": subtitle}})

            card["cardsV2"][0]["card"]["sections"].append(header_section)

        # Content section
        if text:
            content_section = {"widgets": [{"textParagraph": {"text": text}}]}
            card["cardsV2"][0]["card"]["sections"].append(content_section)

        return card

    def create_interactive_card(
        self, title: str, text: str, buttons: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create an interactive card with buttons.

        Args:
            title: Card title
            text: Main text content
            buttons: List of button configurations

        Returns:
            Dict representing the interactive card
        """
        if self.framework_available:
            return self._create_interactive_card_with_framework(title, text, buttons)
        else:
            return self._create_interactive_card_fallback(title, text, buttons)

    def _create_interactive_card_with_framework(
        self, title: str, text: str, buttons: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create interactive card using Card Framework."""
        try:
            sections = []

            # Header section
            if title:
                from card_framework.v2.widgets import TextParagraph

                header_section = Section(
                    widgets=[TextParagraph(text=f"<b>{title}</b>")]
                )
                sections.append(header_section)

            # Content section
            if text:
                from card_framework.v2.widgets import TextParagraph

                content_section = Section(widgets=[TextParagraph(text=text)])
                sections.append(content_section)

            # Button section
            if buttons:
                button_widgets = []
                for btn_config in buttons:
                    button = Button(
                        text=btn_config.get("text", "Button"),
                        on_click=btn_config.get("action", {}),
                    )
                    button_widgets.append(button)

                button_section = Section(widgets=button_widgets)
                sections.append(button_section)

            card = Card(sections=sections)
            logger.debug(
                f"Card Framework interactive card created: {card.to_dict() if hasattr(card, 'to_dict') else 'N/A'}"
            )
            return self._convert_card_to_google_format(card)

        except Exception as e:
            logger.error(f"Error creating interactive card with framework: {e}")
            return self._create_interactive_card_fallback(title, text, buttons)

    def _create_interactive_card_fallback(
        self, title: str, text: str, buttons: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create interactive card using REST API format fallback."""
        card = {"cardsV2": [{"cardId": "interactive-card", "card": {"sections": []}}]}

        # Header section
        if title:
            header_section = {
                "widgets": [{"textParagraph": {"text": f"<b>{title}</b>"}}]
            }
            card["cardsV2"][0]["card"]["sections"].append(header_section)

        # Content section
        if text:
            content_section = {"widgets": [{"textParagraph": {"text": text}}]}
            card["cardsV2"][0]["card"]["sections"].append(content_section)

        # Button section
        if buttons:
            button_widgets = []
            for btn_config in buttons:
                button_widget = {
                    "buttonList": {
                        "buttons": [
                            {
                                "text": btn_config.get("text", "Button"),
                                "onClick": btn_config.get("action", {}),
                            }
                        ]
                    }
                }
                button_widgets.append(button_widget)

            button_section = {"widgets": button_widgets}
            card["cardsV2"][0]["card"]["sections"].append(button_section)

        return card

    def create_form_card(
        self, title: str, fields: List[Dict[str, Any]], submit_action: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a form card with input fields.

        Args:
            title: Form title
            fields: List of form field configurations
            submit_action: Submit button action configuration

        Returns:
            Dict representing the form card
        """
        if self.framework_available:
            return self._create_form_card_with_framework(title, fields, submit_action)
        else:
            return self._create_form_card_fallback(title, fields, submit_action)

    def _create_form_card_with_framework(
        self, title: str, fields: List[Dict[str, Any]], submit_action: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create form card using Card Framework."""
        try:
            sections = []

            # Header section
            if title:
                from card_framework.v2.widgets import TextParagraph

                header_section = Section(
                    widgets=[TextParagraph(text=f"<b>{title}</b>")]
                )
                sections.append(header_section)

            # Form fields section
            if fields:
                field_widgets = []
                for field in fields:
                    field_type = field.get("type", "text")

                    if field_type == "text":
                        text_input = TextInput(
                            name=field.get("name", ""),
                            label=field.get("label", ""),
                            hint_text=field.get("hint", ""),
                        )
                        field_widgets.append(text_input)
                    elif field_type == "selection":
                        selection_input = SelectionInput(
                            name=field.get("name", ""),
                            label=field.get("label", ""),
                            items=field.get("options", []),
                        )
                        field_widgets.append(selection_input)

                form_section = Section(widgets=field_widgets)
                sections.append(form_section)

            # Submit button section
            submit_button = Button(
                text=submit_action.get("text", "Submit"),
                on_click=submit_action.get("action", {}),
            )
            submit_section = Section(widgets=[submit_button])
            sections.append(submit_section)

            card = Card(sections=sections)
            logger.debug(
                f"Card Framework form card created: {card.to_dict() if hasattr(card, 'to_dict') else 'N/A'}"
            )
            return self._convert_card_to_google_format(card)

        except Exception as e:
            logger.error(f"Error creating form card with framework: {e}")
            return self._create_form_card_fallback(title, fields, submit_action)

    def _create_form_card_fallback(
        self, title: str, fields: List[Dict[str, Any]], submit_action: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create form card using REST API format fallback."""
        card = {"cardsV2": [{"cardId": "form-card", "card": {"sections": []}}]}

        # Header section
        if title:
            header_section = {
                "widgets": [{"textParagraph": {"text": f"<b>{title}</b>"}}]
            }
            card["cardsV2"][0]["card"]["sections"].append(header_section)

        # Form fields section
        if fields:
            field_widgets = []
            for field in fields:
                field_type = field.get("type", "text")

                if field_type == "text":
                    field_widget = {
                        "textInput": {
                            "name": field.get("name", ""),
                            "label": field.get("label", ""),
                            "hintText": field.get("hint", ""),
                        }
                    }
                    field_widgets.append(field_widget)
                elif field_type == "selection":
                    field_widget = {
                        "selectionInput": {
                            "name": field.get("name", ""),
                            "label": field.get("label", ""),
                            "items": field.get("options", []),
                        }
                    }
                    field_widgets.append(field_widget)

            form_section = {"widgets": field_widgets}
            card["cardsV2"][0]["card"]["sections"].append(form_section)

        # Submit button section
        submit_section = {
            "widgets": [
                {
                    "buttonList": {
                        "buttons": [
                            {
                                "text": submit_action.get("text", "Submit"),
                                "onClick": submit_action.get("action", {}),
                            }
                        ]
                    }
                }
            ]
        }
        card["cardsV2"][0]["card"]["sections"].append(submit_section)

        return card

    def _convert_card_to_google_format(self, card: Any) -> Dict[str, Any]:
        """
        Convert Card Framework card to Google Chat format with field name validation.

        Args:
            card: Card Framework card object

        Returns:
            Dict in Google Chat card format with proper cardId/card structure
        """
        try:
            logger.debug(f"Attempting to convert card: {card}")

            # Handle FunctionTool objects that are not directly callable
            if hasattr(card, "__class__") and "FunctionTool" in str(card.__class__):
                logger.warning(
                    "Detected FunctionTool object - using adapter-safe conversion"
                )
                # Extract card data using a safe method
                if hasattr(card, "get_data"):
                    google_format_card = card.get_data()
                elif hasattr(card, "data"):
                    google_format_card = card.data
                else:
                    # Fallback to string representation
                    google_format_card = {
                        "error": "Unable to extract card data from FunctionTool"
                    }
                    logger.error("Unable to extract card data from FunctionTool object")
            else:
                # The Card Framework v2 `Card` object should have a `to_dict()` method
                # that produces the correct structure for a single Google Chat card.
                google_format_card = card.to_dict() if hasattr(card, "to_dict") else {}

            # VALIDATION LOG: Check for field name issues
            logger.info("=== FIELD NAME VALIDATION START ===")
            self._validate_and_log_field_names(google_format_card)
            logger.info("=== FIELD NAME VALIDATION END ===")

            # VALIDATION LOG: Apply field name conversion if needed
            converted_card = self._convert_field_names_to_camel_case(google_format_card)

            # IMPORTANT: Return the card wrapped in the correct structure for cardsV2
            # The Google Chat API expects: cardsV2: [{ cardId: "...", card: {...} }]
            card_id = (
                getattr(card, "card_id", None) or f"card_{hash(str(converted_card))}"
            )

            result = {"cardId": card_id, "card": converted_card}

            logger.debug(
                f"Converted card to Google format (cardId/card structure): {json.dumps(result, indent=2)}"
            )
            return result
        except Exception as e:
            logger.error(f"Error converting card to Google format: {e}", exc_info=True)
            # In case of conversion error, return a fallback error card in the expected format
            return {
                "cardId": "error-card",
                "card": {
                    "sections": [
                        {
                            "widgets": [
                                {"textParagraph": {"text": f"Error creating card: {e}"}}
                            ]
                        }
                    ]
                },
            }

    def _validate_and_log_field_names(self, card_dict: Any, path: str = ""):
        """Validate and log field names to identify case conversion issues."""
        if isinstance(card_dict, dict):
            for key, value in card_dict.items():
                current_path = f"{path}.{key}" if path else key

                # Log snake_case field names that should be camelCase
                if "_" in key:
                    logger.warning(
                        f"FIELD NAME ISSUE: Found snake_case field '{key}' at path '{current_path}' - should be camelCase"
                    )

                # Log specific problematic fields from the API error
                if key in ["text", "on_click"] and "widgets" in path:
                    logger.error(
                        f"INVALID WIDGET FIELD: Found standalone '{key}' field at '{current_path}' - this should be wrapped in proper widget type"
                    )

                # Recursively check nested structures
                if isinstance(value, (dict, list)):
                    self._validate_and_log_field_names(value, current_path)
        elif isinstance(card_dict, list):
            for i, item in enumerate(card_dict):
                current_path = f"{path}[{i}]"
                self._validate_and_log_field_names(item, current_path)

    def _convert_field_names_to_camel_case(self, obj: Any) -> Any:
        """Convert snake_case field names to camelCase recursively."""
        if isinstance(obj, dict):
            converted = {}
            for key, value in obj.items():
                # Convert snake_case to camelCase
                camel_key = self._snake_to_camel(key)
                if camel_key != key:
                    logger.info(f"FIELD CONVERSION: {key} -> {camel_key}")
                converted[camel_key] = self._convert_field_names_to_camel_case(value)
            return converted
        elif isinstance(obj, list):
            return [self._convert_field_names_to_camel_case(item) for item in obj]
        else:
            return obj

    def _snake_to_camel(self, snake_str: str) -> str:
        """Convert snake_case string to camelCase."""
        if "_" not in snake_str:
            return snake_str

        components = snake_str.split("_")
        return components[0] + "".join(word.capitalize() for word in components[1:])

    def validate_card(self, card: Dict[str, Any]) -> bool:
        """
        Validate a card structure for Google Chat compatibility.

        Args:
            card: Card dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            logger.debug(f"Validating card: {json.dumps(card, indent=2)}")
            # Basic validation for Google Chat card structure
            if not isinstance(card, dict):
                logger.debug("Card validation failed: Not a dictionary.")
                return False

            if "cardsV2" not in card:
                logger.debug("Card validation failed: 'cardsV2' key missing.")
                return False

            cards_v2 = card["cardsV2"]
            if not isinstance(cards_v2, list) or len(cards_v2) == 0:
                logger.debug(
                    "Card validation failed: 'cardsV2' is not a non-empty list."
                )
                return False

            for card_item in cards_v2:
                if not isinstance(card_item, dict):
                    logger.debug(
                        "Card validation failed: Item in 'cardsV2' is not a dictionary."
                    )
                    return False
                if "card" not in card_item:
                    logger.debug(
                        "Card validation failed: 'card' key missing in card item."
                    )
                    return False

            logger.debug("Card validation successful.")
            return True

        except Exception as e:
            logger.error(f"Error validating card: {e}", exc_info=True)
            return False

    def get_framework_status(self) -> Dict[str, Any]:
        """
        Get the status of Card Framework availability.

        Returns:
            Dict with framework status information
        """
        return {
            "framework_available": self.framework_available,
            "fallback_mode": not self.framework_available,
            "version": "2.1.0" if self.framework_available else "fallback",
        }
