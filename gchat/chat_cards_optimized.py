"""
Google Chat Card Manager - Optimized for Card Framework Integration
Provides rich card-based messaging capabilities for Google Chat with graceful fallback.
"""

import logging
from typing import Dict, Any, List, Optional, Union
import json

logger = logging.getLogger(__name__)

# Try to import Card Framework with graceful fallback
try:
    from card_framework.v2 import Card, Section, Widget, CardHeader, Message
    from card_framework.v2.card import CardWithId
    from card_framework.v2.widgets import (
        Button, TextInput, Image, Divider, SelectionInput, TextParagraph,
        DecoratedText, Icon, Column, Columns, OpenLink, OnClick, ButtonList
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
        
    def create_rich_card(self, title: str, subtitle: Optional[str] = None,
                        image_url: Optional[str] = None, sections: Optional[List[Dict[str, Any]]] = None):
        """Create a rich card with advanced formatting and sections."""
        if CARD_FRAMEWORK_AVAILABLE:
            return self._create_rich_card_with_framework(title, subtitle, image_url, sections)
        else:
            return self._create_rich_card_fallback(title, subtitle, image_url, sections)

    def create_simple_card(self, title: str, subtitle: Optional[str] = None,
                          text: str = "", image_url: Optional[str] = None):
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
            return self._create_simple_card_with_framework(title, subtitle, text, image_url)
        else:
            return self._create_simple_card_fallback(title, subtitle, text, image_url)
    
    def _create_simple_card_with_framework(self, title: str, subtitle: Optional[str] = None,
                                         text: str = "", image_url: Optional[str] = None) -> CardWithId:
        """Create simple card using Card Framework."""
        try:
            # Create card header
            header = CardHeader(
                title=title,
                subtitle=subtitle,
                image_url=image_url
            )
            
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
                sections=sections
            )
            card.card_id = f"simple_{hash(title + text)}"
            
            logger.debug(f"Card Framework simple card created: {card.card_id}")
            return card
            
        except Exception as e:
            logger.error(f"Error creating simple card with framework: {e}")
            # Return fallback as dictionary since we can't return CardWithId in fallback
            raise e

    def _create_rich_card_with_framework(self, title: str, subtitle: Optional[str] = None,
                                        image_url: Optional[str] = None, sections: Optional[List[Dict[str, Any]]] = None) -> CardWithId:
        """Create rich card using Card Framework with advanced widgets."""
        try:
            # Create card header
            header = CardHeader(
                title=title,
                subtitle=subtitle or "Rich Card with Advanced Features",
                image_url=image_url or "https://www.groupon.com/favicon.ico"
            )
            
            # Create the card with CardWithId
            card = CardWithId(
                name=f"rich_card_{title.lower().replace(' ', '_').replace('!', '').replace('🎉', 'celebration')}",
                header=header,
                sections=[]
            )
            card.card_id = f"rich_{hash(title + str(sections))}"
            
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
                        TextParagraph(text="<b>This is a rich card</b> with <i>advanced formatting</i> and <font color='#0066CC'>colored text</font>."),
                        Divider(),
                        DecoratedText(
                            start_icon=Icon(known_icon=Icon.KnownIcon.STAR),
                            text="<b>Enhanced with Card Framework v2</b><br>Supports rich widgets and interactions",
                            top_label="Card Framework v2",
                            bottom_label="Advanced Features Available",
                            wrap_text=True
                        )
                    ],
                    collapsible=False
                )
                card.sections.append(default_section)
            
            logger.debug(f"Card Framework rich card created: {card.card_id}")
            return card
        
        except Exception as e:
            logger.error(f"Error creating Card Framework rich card: {e}")
            # Fallback to simple card
            return self._create_simple_card_with_framework(title, subtitle, "Rich card fallback", image_url)

    def _create_section_from_config(self, section_config: Dict[str, Any]) -> Optional[Section]:
        """Create a Section from configuration dictionary."""
        try:
            widgets = []
            
            # Process widgets in the section
            for widget_config in section_config.get("widgets", []):
                widget = self._create_widget_from_config(widget_config)
                if widget:
                    widgets.append(widget)
            
            # Create section
            section = Section(
                header=section_config.get("header"),
                widgets=widgets,
                collapsible=section_config.get("collapsible", False)
            )
            
            return section
        
        except Exception as e:
            logger.error(f"Error creating section from config: {e}")
            return None

    def _create_widget_from_config(self, widget_config: Dict[str, Any]):
        """Create a widget from configuration dictionary."""
        try:
            widget_type = widget_config.get("type")
            
            if widget_type == "text_paragraph":
                return TextParagraph(text=widget_config.get("text", ""))
            
            elif widget_type == "decorated_text":
                icon = None
                if widget_config.get("start_icon"):
                    icon_name = widget_config["start_icon"]
                    if hasattr(Icon.KnownIcon, icon_name):
                        icon = Icon(known_icon=getattr(Icon.KnownIcon, icon_name))
                
                on_click = None
                if widget_config.get("clickable") and widget_config.get("url"):
                    on_click = OnClick(open_link=OpenLink(url=widget_config["url"]))
                
                return DecoratedText(
                    start_icon=icon,
                    text=widget_config.get("text", ""),
                    top_label=widget_config.get("top_label"),
                    bottom_label=widget_config.get("bottom_label"),
                    wrap_text=True,
                    on_click=on_click
                )
            
            elif widget_type == "button_list":
                buttons = []
                for button_config in widget_config.get("buttons", []):
                    button = Button(
                        text=button_config.get("text", "Button"),
                        on_click=OnClick(open_link=OpenLink(url=button_config.get("url", "https://example.com")))
                    )
                    buttons.append(button)
                return ButtonList(buttons=buttons)
            
            elif widget_type == "image":
                on_click = None
                if widget_config.get("clickable") and widget_config.get("url"):
                    on_click = OnClick(open_link=OpenLink(url=widget_config["url"]))
                
                return Image(
                    image_url=widget_config.get("image_url", ""),
                    alt_text=widget_config.get("alt_text", "Image"),
                    on_click=on_click
                )
            
            elif widget_type == "columns":
                column_items = []
                for column_config in widget_config.get("columns", []):
                    column_widgets = []
                    for col_widget_config in column_config.get("widgets", []):
                        col_widget = self._create_widget_from_config(col_widget_config)
                        if col_widget:
                            column_widgets.append(col_widget)
                    
                    alignment = column_config.get("alignment", "START")
                    if alignment == "START":
                        h_align = Column.HorizontalAlignment.START
                    elif alignment == "CENTER":
                        h_align = Column.HorizontalAlignment.CENTER
                    else:
                        h_align = Column.HorizontalAlignment.END
                    
                    column = Column(
                        horizontal_alignment=h_align,
                        widgets=column_widgets
                    )
                    column_items.append(column)
                
                return Columns(column_items=column_items)
            
            elif widget_type == "divider":
                return Divider()
            
            else:
                logger.warning(f"Unknown widget type: {widget_type}")
                return None
        
        except Exception as e:
            logger.error(f"Error creating widget from config: {e}")
            return None

    def _create_rich_card_fallback(self, title: str, subtitle: Optional[str] = None,
                                  image_url: Optional[str] = None, sections: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Create rich card using REST API format fallback."""
        # For fallback, create a simple card with enhanced formatting
        return self._create_simple_card_fallback(title, subtitle, "Rich card features not available in fallback mode", image_url)
    
    def _create_simple_card_fallback(self, title: str, subtitle: Optional[str] = None,
                                   text: str = "", image_url: Optional[str] = None) -> Dict[str, Any]:
        """Create simple card using REST API format fallback."""
        card = {
            "cardsV2": [{
                "cardId": "simple-card",
                "card": {
                    "sections": []
                }
            }]
        }
        
        # Header section
        if title or subtitle or image_url:
            header_section = {"widgets": []}
            
            if image_url:
                header_section["widgets"].append({
                    "image": {
                        "imageUrl": image_url,
                        "altText": title
                    }
                })
            
            if title:
                header_section["widgets"].append({
                    "textParagraph": {
                        "text": f"<b>{title}</b>"
                    }
                })
                
            if subtitle:
                header_section["widgets"].append({
                    "textParagraph": {
                        "text": subtitle
                    }
                })
            
            card["cardsV2"][0]["card"]["sections"].append(header_section)
        
        # Content section
        if text:
            content_section = {
                "widgets": [{
                    "textParagraph": {
                        "text": text
                    }
                }]
            }
            card["cardsV2"][0]["card"]["sections"].append(content_section)
        
        return card
    
    def create_interactive_card(self, title: str, text: str, 
                              buttons: List[Dict[str, Any]]) -> Dict[str, Any]:
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
    
    def _create_interactive_card_with_framework(self, title: str, text: str,
                                              buttons: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create interactive card using Card Framework."""
        try:
            sections = []
            
            # Header section
            if title:
                from card_framework.v2.widgets import TextParagraph
                header_section = Section(widgets=[
                    TextParagraph(text=f"<b>{title}</b>")
                ])
                sections.append(header_section)
            
            # Content section
            if text:
                from card_framework.v2.widgets import TextParagraph
                content_section = Section(widgets=[
                    TextParagraph(text=text)
                ])
                sections.append(content_section)
            
            # Button section
            if buttons:
                button_widgets = []
                for btn_config in buttons:
                    button = Button(
                        text=btn_config.get("text", "Button"),
                        on_click=btn_config.get("action", {})
                    )
                    button_widgets.append(button)
                
                button_section = Section(widgets=button_widgets)
                sections.append(button_section)
            
            card = Card(sections=sections)
            logger.debug(f"Card Framework interactive card created: {card.to_dict() if hasattr(card, 'to_dict') else 'N/A'}")
            return self._convert_card_to_google_format(card)
            
        except Exception as e:
            logger.error(f"Error creating interactive card with framework: {e}")
            return self._create_interactive_card_fallback(title, text, buttons)
    
    def _create_interactive_card_fallback(self, title: str, text: str,
                                         buttons: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create interactive card using REST API format fallback."""
        card = {
            "cardsV2": [{
                "cardId": "interactive-card",
                "card": {
                    "sections": []
                }
            }]
        }
        
        # Header section
        if title:
            header_section = {
                "widgets": [{
                    "textParagraph": {
                        "text": f"<b>{title}</b>"
                    }
                }]
            }
            card["cardsV2"][0]["card"]["sections"].append(header_section)
        
        # Content section
        if text:
            content_section = {
                "widgets": [{
                    "textParagraph": {
                        "text": text
                    }
                }]
            }
            card["cardsV2"][0]["card"]["sections"].append(content_section)
        
        # Button section
        if buttons:
            button_widgets = []
            for btn_config in buttons:
                button_widget = {
                    "buttonList": {
                        "buttons": [{
                            "text": btn_config.get("text", "Button"),
                            "onClick": btn_config.get("action", {})
                        }]
                    }
                }
                button_widgets.append(button_widget)
            
            button_section = {"widgets": button_widgets}
            card["cardsV2"][0]["card"]["sections"].append(button_section)
        
        return card
    
    def create_form_card(self, title: str, fields: List[Dict[str, Any]], 
                        submit_action: Dict[str, Any]) -> Dict[str, Any]:
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
    
    def _create_form_card_with_framework(self, title: str, fields: List[Dict[str, Any]],
                                       submit_action: Dict[str, Any]) -> Dict[str, Any]:
        """Create form card using Card Framework."""
        try:
            sections = []
            
            # Header section
            if title:
                from card_framework.v2.widgets import TextParagraph
                header_section = Section(widgets=[
                    TextParagraph(text=f"<b>{title}</b>")
                ])
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
                            hint_text=field.get("hint", "")
                        )
                        field_widgets.append(text_input)
                    elif field_type == "selection":
                        selection_input = SelectionInput(
                            name=field.get("name", ""),
                            label=field.get("label", ""),
                            items=field.get("options", [])
                        )
                        field_widgets.append(selection_input)
                
                form_section = Section(widgets=field_widgets)
                sections.append(form_section)
            
            # Submit button section
            submit_button = Button(
                text=submit_action.get("text", "Submit"),
                on_click=submit_action.get("action", {})
            )
            submit_section = Section(widgets=[submit_button])
            sections.append(submit_section)
            
            card = Card(sections=sections)
            logger.debug(f"Card Framework form card created: {card.to_dict() if hasattr(card, 'to_dict') else 'N/A'}")
            return self._convert_card_to_google_format(card)
            
        except Exception as e:
            logger.error(f"Error creating form card with framework: {e}")
            return self._create_form_card_fallback(title, fields, submit_action)
    
    def _create_form_card_fallback(self, title: str, fields: List[Dict[str, Any]],
                                  submit_action: Dict[str, Any]) -> Dict[str, Any]:
        """Create form card using REST API format fallback."""
        card = {
            "cardsV2": [{
                "cardId": "form-card",
                "card": {
                    "sections": []
                }
            }]
        }
        
        # Header section
        if title:
            header_section = {
                "widgets": [{
                    "textParagraph": {
                        "text": f"<b>{title}</b>"
                    }
                }]
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
                            "hintText": field.get("hint", "")
                        }
                    }
                    field_widgets.append(field_widget)
                elif field_type == "selection":
                    field_widget = {
                        "selectionInput": {
                            "name": field.get("name", ""),
                            "label": field.get("label", ""),
                            "items": field.get("options", [])
                        }
                    }
                    field_widgets.append(field_widget)
            
            form_section = {"widgets": field_widgets}
            card["cardsV2"][0]["card"]["sections"].append(form_section)
        
        # Submit button section
        submit_section = {
            "widgets": [{
                "buttonList": {
                    "buttons": [{
                        "text": submit_action.get("text", "Submit"),
                        "onClick": submit_action.get("action", {})
                    }]
                }
            }]
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
            # The Card Framework v2 `Card` object should have a `to_dict()` method
            # that produces the correct structure for a single Google Chat card.
            google_format_card = card.to_dict() if hasattr(card, 'to_dict') else {}
            
            # VALIDATION LOG: Check for field name issues
            logger.info("=== FIELD NAME VALIDATION START ===")
            self._validate_and_log_field_names(google_format_card)
            logger.info("=== FIELD NAME VALIDATION END ===")
            
            # VALIDATION LOG: Apply field name conversion if needed
            converted_card = self._convert_field_names_to_camel_case(google_format_card)
            
            # IMPORTANT: Return the card wrapped in the correct structure for cardsV2
            # The Google Chat API expects: cardsV2: [{ cardId: "...", card: {...} }]
            card_id = getattr(card, 'card_id', None) or f"card_{hash(str(converted_card))}"
            
            result = {
                "cardId": card_id,
                "card": converted_card
            }
            
            logger.debug(f"Converted card to Google format (cardId/card structure): {json.dumps(result, indent=2)}")
            return result
        except Exception as e:
            logger.error(f"Error converting card to Google format: {e}", exc_info=True)
            # In case of conversion error, return a fallback error card in the expected format
            return {
                "cardId": "error-card",
                "card": {
                    "sections": [{
                        "widgets": [{
                            "textParagraph": {
                                "text": f"Error creating card: {e}"
                            }
                        }]
                    }]
                }
            }

    def _validate_and_log_field_names(self, card_dict: Any, path: str = ""):
        """Validate and log field names to identify case conversion issues."""
        if isinstance(card_dict, dict):
            for key, value in card_dict.items():
                current_path = f"{path}.{key}" if path else key
                
                # Log snake_case field names that should be camelCase
                if "_" in key:
                    logger.warning(f"FIELD NAME ISSUE: Found snake_case field '{key}' at path '{current_path}' - should be camelCase")
                
                # Log specific problematic fields from the API error
                if key in ["text", "on_click"] and "widgets" in path:
                    logger.error(f"INVALID WIDGET FIELD: Found standalone '{key}' field at '{current_path}' - this should be wrapped in proper widget type")
                
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
        
        components = snake_str.split('_')
        return components[0] + ''.join(word.capitalize() for word in components[1:])
    
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
                logger.debug("Card validation failed: 'cardsV2' is not a non-empty list.")
                return False
                
            for card_item in cards_v2:
                if not isinstance(card_item, dict):
                    logger.debug("Card validation failed: Item in 'cardsV2' is not a dictionary.")
                    return False
                if "card" not in card_item:
                    logger.debug("Card validation failed: 'card' key missing in card item.")
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
            "version": "2.1.0" if self.framework_available else "fallback"
        }