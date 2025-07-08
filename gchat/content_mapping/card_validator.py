"""
Card Validator for Google Chat Card Creation

This module provides the CardValidator class, which validates card structures against
Google Chat API requirements and automatically fixes common formatting issues.
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple, Set

logger = logging.getLogger(__name__)


class CardValidator:
    """
    Validator for Google Chat card structures.
    
    The CardValidator validates card structures against Google Chat API requirements,
    automatically fixes common formatting issues, and suggests improvements for better
    user experience.
    """
    
    def __init__(self):
        """Initialize the CardValidator."""
        # Define card structure requirements
        self.required_card_fields = set()  # No strictly required fields at the top level
        self.optional_card_fields = {"header", "sections", "cardActions", "name", "fixedFooter"}
        
        # Define header requirements
        self.required_header_fields = {"title"}
        self.optional_header_fields = {"subtitle", "imageUrl", "imageType", "imageAltText", "imageStyle"}
        
        # Define section requirements
        self.required_section_fields = {"widgets"}  # Each section must have widgets
        self.optional_section_fields = {"header", "collapsible", "uncollapsibleWidgetsCount"}
        
        # Define widget types and their required fields
        self.widget_types = {
            "textParagraph": {
                "required": {"text"},
                "optional": {"wrapText"}
            },
            "image": {
                "required": {"imageUrl"},
                "optional": {"altText", "onClick"}
            },
            "decoratedText": {
                "required": {"text"},
                "optional": {"topLabel", "bottomLabel", "startIcon", "endIcon", "wrapText", "onClick", "button"}
            },
            "buttonList": {
                "required": {"buttons"},
                "optional": set()
            },
            "divider": {
                "required": set(),
                "optional": set()
            },
            "textInput": {
                "required": {"name", "label"},
                "optional": {"hintText", "value", "type", "required", "multiline", "onChangeAction"}
            },
            "selectionInput": {
                "required": {"name", "label", "items", "type"},
                "optional": {"onChangeAction"}
            },
            "dateTimePicker": {
                "required": {"name", "label"},
                "optional": {"type", "valueMsEpoch", "onChangeAction", "timezoneOffsetDate"}
            },
            "columns": {
                "required": {"columnItems"},
                "optional": {"border", "padding"}
            },
            "grid": {
                "required": {"title", "items"},
                "optional": {"borderStyle", "columnCount", "onClick", "gridItemLayout"}
            }
        }
        
        # Define common issues and fixes
        self.common_issues = {
            "missing_text": {
                "pattern": lambda widget: "text" in widget and not widget["text"],
                "fix": lambda widget: {"text": "No text provided"}
            },
            "missing_alt_text": {
                "pattern": lambda widget: "imageUrl" in widget and "altText" not in widget,
                "fix": lambda widget: {"altText": "Image"}
            },
            "invalid_url": {
                "pattern": lambda widget: "imageUrl" in widget and not re.match(r'^https?://', widget["imageUrl"]),
                "fix": lambda widget: {"imageUrl": f"https://{widget['imageUrl']}" if not widget["imageUrl"].startswith("http") else widget["imageUrl"]}
            },
            "missing_button_text": {
                "pattern": lambda button: "text" not in button or not button["text"],
                "fix": lambda button: {"text": "Click here"}
            },
            "missing_button_action": {
                "pattern": lambda button: "onClick" not in button,
                "fix": lambda button: {"onClick": {"action": {"actionMethodName": "buttonClicked"}}}
            },
            "empty_button_list": {
                "pattern": lambda widget: "buttons" in widget and (not widget["buttons"] or len(widget["buttons"]) == 0),
                "fix": lambda widget: {"buttons": [{"text": "Click here", "onClick": {"action": {"actionMethodName": "buttonClicked"}}}]}
            },
            "missing_selection_items": {
                "pattern": lambda widget: "items" in widget and (not widget["items"] or len(widget["items"]) == 0),
                "fix": lambda widget: {"items": [{"text": "Option 1", "value": "option1"}, {"text": "Option 2", "value": "option2"}]}
            }
        }
    
    def validate_card_structure(self, card: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a card structure against Google Chat API requirements.
        
        Args:
            card: Card structure to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Check card fields
        card_fields = set(card.keys())
        unknown_fields = card_fields - self.required_card_fields - self.optional_card_fields
        if unknown_fields:
            issues.append(f"Unknown card fields: {', '.join(unknown_fields)}")
        
        # Check header if present
        if "header" in card:
            header_issues = self._validate_header(card["header"])
            issues.extend(header_issues)
        
        # Check sections if present
        if "sections" in card:
            if not isinstance(card["sections"], list):
                issues.append("Sections must be a list")
            else:
                for i, section in enumerate(card["sections"]):
                    section_issues = self._validate_section(section, i)
                    issues.extend(section_issues)
        
        # Check if card has either header or sections
        if "header" not in card and "sections" not in card:
            issues.append("Card must have either header or sections")
        
        return len(issues) == 0, issues
    
    def _validate_header(self, header: Dict[str, Any]) -> List[str]:
        """
        Validate a card header.
        
        Args:
            header: Header structure to validate
            
        Returns:
            List of issues
        """
        issues = []
        
        # Check required fields
        for field in self.required_header_fields:
            if field not in header:
                issues.append(f"Missing required header field: {field}")
        
        # Check for unknown fields
        header_fields = set(header.keys())
        unknown_fields = header_fields - self.required_header_fields - self.optional_header_fields
        if unknown_fields:
            issues.append(f"Unknown header fields: {', '.join(unknown_fields)}")
        
        return issues
    
    def _validate_section(self, section: Dict[str, Any], index: int) -> List[str]:
        """
        Validate a card section.
        
        Args:
            section: Section structure to validate
            index: Section index for error reporting
            
        Returns:
            List of issues
        """
        issues = []
        
        # Check required fields
        for field in self.required_section_fields:
            if field not in section:
                issues.append(f"Missing required field in section {index}: {field}")
        
        # Check for unknown fields
        section_fields = set(section.keys())
        unknown_fields = section_fields - self.required_section_fields - self.optional_section_fields
        if unknown_fields:
            issues.append(f"Unknown fields in section {index}: {', '.join(unknown_fields)}")
        
        # Check widgets if present
        if "widgets" in section:
            if not isinstance(section["widgets"], list):
                issues.append(f"Widgets in section {index} must be a list")
            else:
                for i, widget in enumerate(section["widgets"]):
                    widget_issues = self._validate_widget(widget, index, i)
                    issues.extend(widget_issues)
        
        return issues
    
    def _validate_widget(self, widget: Dict[str, Any], section_index: int, widget_index: int) -> List[str]:
        """
        Validate a widget.
        
        Args:
            widget: Widget structure to validate
            section_index: Section index for error reporting
            widget_index: Widget index for error reporting
            
        Returns:
            List of issues
        """
        issues = []
        
        # Check widget type
        widget_type = None
        for key in widget:
            if key in self.widget_types:
                widget_type = key
                break
        
        if widget_type is None:
            issues.append(f"Unknown widget type in section {section_index}, widget {widget_index}")
            return issues
        
        # Check required fields for this widget type
        widget_content = widget[widget_type]
        required_fields = self.widget_types[widget_type]["required"]
        optional_fields = self.widget_types[widget_type]["optional"]
        
        for field in required_fields:
            if field not in widget_content:
                issues.append(f"Missing required field '{field}' in {widget_type} widget (section {section_index}, widget {widget_index})")
        
        # Check for unknown fields
        widget_fields = set(widget_content.keys())
        unknown_fields = widget_fields - required_fields - optional_fields
        if unknown_fields:
            issues.append(f"Unknown fields in {widget_type} widget (section {section_index}, widget {widget_index}): {', '.join(unknown_fields)}")
        
        # Special validation for specific widget types
        if widget_type == "buttonList" and "buttons" in widget_content:
            for i, button in enumerate(widget_content["buttons"]):
                if "text" not in button:
                    issues.append(f"Missing 'text' in button {i} (section {section_index}, widget {widget_index})")
        
        elif widget_type == "selectionInput" and "items" in widget_content:
            for i, item in enumerate(widget_content["items"]):
                if "text" not in item:
                    issues.append(f"Missing 'text' in selection item {i} (section {section_index}, widget {widget_index})")
                if "value" not in item:
                    issues.append(f"Missing 'value' in selection item {i} (section {section_index}, widget {widget_index})")
        
        return issues
    
    def auto_fix_common_issues(self, card: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automatically fix common issues in a card structure.
        
        Args:
            card: Card structure to fix
            
        Returns:
            Fixed card structure
        """
        # Make a deep copy of the card to avoid modifying the original
        import copy
        fixed_card = copy.deepcopy(card)
        
        # Fix header issues if present
        if "header" in fixed_card:
            fixed_card["header"] = self._fix_header(fixed_card["header"])
        
        # Fix section issues if present
        if "sections" in fixed_card:
            if not isinstance(fixed_card["sections"], list):
                fixed_card["sections"] = []
            else:
                for i in range(len(fixed_card["sections"])):
                    fixed_card["sections"][i] = self._fix_section(fixed_card["sections"][i])
        
        # Ensure card has at least one section if no header
        if "header" not in fixed_card and ("sections" not in fixed_card or len(fixed_card["sections"]) == 0):
            fixed_card["sections"] = [{
                "widgets": [{
                    "textParagraph": {
                        "text": "No content provided"
                    }
                }]
            }]
        
        return fixed_card
    
    def _fix_header(self, header: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fix common issues in a header.
        
        Args:
            header: Header structure to fix
            
        Returns:
            Fixed header structure
        """
        fixed_header = header.copy()
        
        # Ensure required fields
        if "title" not in fixed_header or not fixed_header["title"]:
            fixed_header["title"] = "Untitled Card"
        
        return fixed_header
    
    def _fix_section(self, section: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fix common issues in a section.
        
        Args:
            section: Section structure to fix
            
        Returns:
            Fixed section structure
        """
        fixed_section = section.copy()
        
        # Ensure required fields
        if "widgets" not in fixed_section or not fixed_section["widgets"]:
            fixed_section["widgets"] = [{
                "textParagraph": {
                    "text": "No content provided"
                }
            }]
        else:
            # Fix each widget
            for i in range(len(fixed_section["widgets"])):
                fixed_section["widgets"][i] = self._fix_widget(fixed_section["widgets"][i])
        
        return fixed_section
    
    def _fix_widget(self, widget: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fix common issues in a widget.
        
        Args:
            widget: Widget structure to fix
            
        Returns:
            Fixed widget structure
        """
        fixed_widget = widget.copy()
        
        # Identify widget type
        widget_type = None
        for key in fixed_widget:
            if key in self.widget_types:
                widget_type = key
                break
        
        if widget_type is None:
            # Unknown widget type, replace with a text paragraph
            return {
                "textParagraph": {
                    "text": "Invalid widget"
                }
            }
        
        # Apply fixes for common issues
        widget_content = fixed_widget[widget_type]
        
        # Apply specific fixes based on widget type
        if widget_type == "textParagraph":
            if "text" not in widget_content or not widget_content["text"]:
                widget_content["text"] = "No text provided"
        
        elif widget_type == "image":
            if "imageUrl" not in widget_content or not widget_content["imageUrl"]:
                widget_content["imageUrl"] = "https://via.placeholder.com/300x200?text=No+Image"
            elif not re.match(r'^https?://', widget_content["imageUrl"]):
                widget_content["imageUrl"] = f"https://{widget_content['imageUrl']}"
            
            if "altText" not in widget_content:
                widget_content["altText"] = "Image"
        
        elif widget_type == "decoratedText":
            if "text" not in widget_content or not widget_content["text"]:
                widget_content["text"] = "No text provided"
            
            # Ensure wrapText is set
            if "wrapText" not in widget_content:
                widget_content["wrapText"] = True
        
        elif widget_type == "buttonList":
            if "buttons" not in widget_content or not widget_content["buttons"]:
                widget_content["buttons"] = [{
                    "text": "Click here",
                    "onClick": {
                        "action": {
                            "actionMethodName": "buttonClicked"
                        }
                    }
                }]
            else:
                # Fix each button
                for i in range(len(widget_content["buttons"])):
                    button = widget_content["buttons"][i]
                    
                    if "text" not in button or not button["text"]:
                        button["text"] = "Click here"
                    
                    if "onClick" not in button:
                        button["onClick"] = {
                            "action": {
                                "actionMethodName": "buttonClicked"
                            }
                        }
        
        elif widget_type == "textInput":
            if "name" not in widget_content or not widget_content["name"]:
                widget_content["name"] = "textInput"
            
            if "label" not in widget_content or not widget_content["label"]:
                widget_content["label"] = "Enter text"
        
        elif widget_type == "selectionInput":
            if "name" not in widget_content or not widget_content["name"]:
                widget_content["name"] = "selectionInput"
            
            if "label" not in widget_content or not widget_content["label"]:
                widget_content["label"] = "Select an option"
            
            if "type" not in widget_content:
                widget_content["type"] = "DROPDOWN"
            
            if "items" not in widget_content or not widget_content["items"]:
                widget_content["items"] = [
                    {"text": "Option 1", "value": "option1"},
                    {"text": "Option 2", "value": "option2"}
                ]
            else:
                # Fix each item
                for i in range(len(widget_content["items"])):
                    item = widget_content["items"][i]
                    
                    if "text" not in item or not item["text"]:
                        item["text"] = f"Option {i+1}"
                    
                    if "value" not in item or not item["value"]:
                        item["value"] = f"option{i+1}"
        
        # Update the widget with fixed content
        fixed_widget[widget_type] = widget_content
        
        return fixed_widget
    
    def suggest_improvements(self, card: Dict[str, Any]) -> List[str]:
        """
        Suggest improvements for a card structure.
        
        Args:
            card: Card structure to analyze
            
        Returns:
            List of improvement suggestions
        """
        suggestions = []
        
        # Check for header
        if "header" not in card:
            suggestions.append("Add a header with a title to improve card appearance")
        elif "header" in card and "subtitle" not in card["header"]:
            suggestions.append("Consider adding a subtitle to provide additional context")
        
        # Check for sections
        if "sections" not in card or len(card["sections"]) == 0:
            suggestions.append("Add at least one section with widgets to display content")
        
        # Check for interactive elements
        has_interactive = False
        if "sections" in card:
            for section in card["sections"]:
                if "widgets" in section:
                    for widget in section["widgets"]:
                        if any(key in ["buttonList", "textInput", "selectionInput", "dateTimePicker"] for key in widget):
                            has_interactive = True
                            break
        
        if not has_interactive:
            suggestions.append("Consider adding interactive elements like buttons or inputs for better user engagement")
        
        # Check for images
        has_image = False
        if "header" in card and "imageUrl" in card["header"]:
            has_image = True
        
        if "sections" in card and not has_image:
            for section in card["sections"]:
                if "widgets" in section:
                    for widget in section["widgets"]:
                        if "image" in widget:
                            has_image = True
                            break
        
        if not has_image:
            suggestions.append("Consider adding images to make the card more visually appealing")
        
        # Check for dividers
        has_divider = False
        if "sections" in card:
            for section in card["sections"]:
                if "widgets" in section:
                    for widget in section["widgets"]:
                        if "divider" in widget:
                            has_divider = True
                            break
        
        if len(card.get("sections", [])) > 1 and not has_divider:
            suggestions.append("Consider using dividers to separate different sections of content")
        
        # Check for consistent styling
        if "sections" in card:
            text_widgets = []
            for section in card["sections"]:
                if "widgets" in section:
                    for widget in section["widgets"]:
                        if "textParagraph" in widget or "decoratedText" in widget:
                            text_widgets.append(widget)
            
            if len(text_widgets) > 2:
                # Check for inconsistent use of decoratedText vs textParagraph
                has_text_paragraph = any("textParagraph" in w for w in text_widgets)
                has_decorated_text = any("decoratedText" in w for w in text_widgets)
                
                if has_text_paragraph and has_decorated_text:
                    suggestions.append("Consider using consistent text widget types (either textParagraph or decoratedText) for better visual consistency")
        
        return suggestions
    
    def validate_widget(self, widget: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a single widget.
        
        Args:
            widget: Widget structure to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Check widget type
        widget_type = None
        for key in widget:
            if key in self.widget_types:
                widget_type = key
                break
        
        if widget_type is None:
            issues.append("Unknown widget type")
            return False, issues
        
        # Check required fields for this widget type
        widget_content = widget[widget_type]
        required_fields = self.widget_types[widget_type]["required"]
        optional_fields = self.widget_types[widget_type]["optional"]
        
        for field in required_fields:
            if field not in widget_content:
                issues.append(f"Missing required field '{field}' in {widget_type} widget")
        
        # Check for unknown fields
        widget_fields = set(widget_content.keys())
        unknown_fields = widget_fields - required_fields - optional_fields
        if unknown_fields:
            issues.append(f"Unknown fields in {widget_type} widget: {', '.join(unknown_fields)}")
        
        # Special validation for specific widget types
        if widget_type == "buttonList" and "buttons" in widget_content:
            for i, button in enumerate(widget_content["buttons"]):
                if "text" not in button:
                    issues.append(f"Missing 'text' in button {i}")
        
        elif widget_type == "selectionInput" and "items" in widget_content:
            for i, item in enumerate(widget_content["items"]):
                if "text" not in item:
                    issues.append(f"Missing 'text' in selection item {i}")
                if "value" not in item:
                    issues.append(f"Missing 'value' in selection item {i}")
        
        return len(issues) == 0, issues