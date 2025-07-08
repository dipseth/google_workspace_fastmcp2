"""
Parameter Inference Engine for Google Chat Card Creation

This module provides the ParameterInferenceEngine class, which infers parameter names
and widget types from natural language descriptions for Google Chat cards.
"""

import re
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
import json

from .models import ParameterDefinition

logger = logging.getLogger(__name__)


class ParameterInferenceEngine:
    """
    Engine for inferring parameters from natural language descriptions.
    
    The ParameterInferenceEngine analyzes natural language descriptions to infer
    appropriate parameter names, widget types, and parameter values for Google Chat
    card components.
    """
    
    def __init__(self):
        """Initialize the ParameterInferenceEngine."""
        # Define known card types
        self.card_types = {
            "simple": ["title", "text", "subtitle"],
            "header": ["title", "subtitle", "imageUrl", "imageType", "imageAltText"],
            "section": ["header", "collapsible", "uncollapsibleWidgetsCount"],
            "interactive": ["buttons", "inputs", "selectionInput"],
            "form": ["formAction", "textInput", "selectionInput", "dateTimePicker"],
            "rich": ["header", "sections", "cardActions"]
        }
        
        # Define known widget types
        self.widget_types = {
            "textParagraph": {
                "description": "Simple text paragraph",
                "parameters": {
                    "text": ParameterDefinition(
                        name="text",
                        type="string",
                        description="The text content of the paragraph",
                        required=True
                    )
                }
            },
            "image": {
                "description": "Image widget",
                "parameters": {
                    "imageUrl": ParameterDefinition(
                        name="imageUrl",
                        type="string",
                        description="URL of the image",
                        required=True
                    ),
                    "altText": ParameterDefinition(
                        name="altText",
                        type="string",
                        description="Alternative text for the image",
                        required=False
                    )
                }
            },
            "decoratedText": {
                "description": "Text with optional icon, label, and button",
                "parameters": {
                    "text": ParameterDefinition(
                        name="text",
                        type="string",
                        description="The main text content",
                        required=True
                    ),
                    "topLabel": ParameterDefinition(
                        name="topLabel",
                        type="string",
                        description="Label displayed above the text",
                        required=False
                    ),
                    "bottomLabel": ParameterDefinition(
                        name="bottomLabel",
                        type="string",
                        description="Label displayed below the text",
                        required=False
                    ),
                    "startIcon": ParameterDefinition(
                        name="startIcon",
                        type="object",
                        description="Icon displayed at the start of the text",
                        required=False
                    ),
                    "wrapText": ParameterDefinition(
                        name="wrapText",
                        type="boolean",
                        description="Whether to wrap the text",
                        required=False,
                        default_value=True
                    )
                }
            },
            "buttonList": {
                "description": "List of buttons",
                "parameters": {
                    "buttons": ParameterDefinition(
                        name="buttons",
                        type="array",
                        description="Array of button objects",
                        required=True
                    )
                }
            },
            "divider": {
                "description": "Horizontal divider line",
                "parameters": {}
            },
            "textInput": {
                "description": "Text input field",
                "parameters": {
                    "name": ParameterDefinition(
                        name="name",
                        type="string",
                        description="Identifier for the input field",
                        required=True
                    ),
                    "label": ParameterDefinition(
                        name="label",
                        type="string",
                        description="Label for the input field",
                        required=True
                    ),
                    "hintText": ParameterDefinition(
                        name="hintText",
                        type="string",
                        description="Hint text displayed when the field is empty",
                        required=False
                    ),
                    "value": ParameterDefinition(
                        name="value",
                        type="string",
                        description="Initial value for the input field",
                        required=False
                    ),
                    "type": ParameterDefinition(
                        name="type",
                        type="string",
                        description="Type of input field",
                        required=False,
                        possible_values=["SINGLE_LINE", "MULTIPLE_LINE"]
                    )
                }
            },
            "selectionInput": {
                "description": "Selection input (dropdown, checkbox, radio)",
                "parameters": {
                    "name": ParameterDefinition(
                        name="name",
                        type="string",
                        description="Identifier for the selection input",
                        required=True
                    ),
                    "label": ParameterDefinition(
                        name="label",
                        type="string",
                        description="Label for the selection input",
                        required=True
                    ),
                    "type": ParameterDefinition(
                        name="type",
                        type="string",
                        description="Type of selection input",
                        required=True,
                        possible_values=["DROPDOWN", "CHECK_BOX", "RADIO_BUTTON", "SWITCH"]
                    ),
                    "items": ParameterDefinition(
                        name="items",
                        type="array",
                        description="Array of selection items",
                        required=True
                    )
                }
            }
        }
        
        # Define parameter type patterns
        self.parameter_patterns = {
            "url": r'https?://\S+|www\.\S+|\b[a-z0-9\-]+\.[a-z]{2,}\S*',
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "date": r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}',
            "time": r'\d{1,2}:\d{2}(:\d{2})?(\s*[AP]M)?',
            "number": r'\b\d+(\.\d+)?\b',
            "boolean": r'\b(true|false|yes|no|on|off)\b',
            "color": r'#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{3}|\b(red|green|blue|yellow|black|white|orange|purple|pink|brown|gray|grey)\b'
        }
    
    def infer_card_type(self, description: str) -> str:
        """
        Infer the card type from a natural language description.
        
        Args:
            description: Natural language description of the card
            
        Returns:
            Inferred card type
        """
        description = description.lower()
        
        # Check for explicit card type mentions
        for card_type in self.card_types:
            if card_type in description:
                return card_type
        
        # Check for feature-based inference
        if any(word in description for word in ["button", "click", "tap", "action", "interactive"]):
            return "interactive"
        
        if any(word in description for word in ["input", "form", "submit", "field", "enter"]):
            return "form"
        
        if any(word in description for word in ["section", "divide", "segment", "part"]):
            return "rich"
        
        if any(word in description for word in ["header", "title", "heading"]):
            return "header"
        
        # Default to simple card
        return "simple"
    
    def infer_widget_type(self, description: str) -> str:
        """
        Infer the widget type from a natural language description.
        
        Args:
            description: Natural language description of the widget
            
        Returns:
            Inferred widget type
        """
        description = description.lower()
        
        # Check for explicit widget type mentions
        widget_keywords = {
            "textParagraph": ["paragraph", "text", "content", "description"],
            "image": ["image", "picture", "photo", "icon", "graphic"],
            "decoratedText": ["decorated", "label", "icon", "styled text"],
            "buttonList": ["button", "action", "click", "tap", "link"],
            "divider": ["divider", "separator", "line", "hr", "horizontal rule"],
            "textInput": ["input", "field", "enter", "type", "text box"],
            "selectionInput": ["select", "dropdown", "checkbox", "radio", "choice", "option"]
        }
        
        for widget_type, keywords in widget_keywords.items():
            if any(keyword in description for keyword in keywords):
                return widget_type
        
        # Check for URL patterns that might indicate an image or button
        if re.search(self.parameter_patterns["url"], description):
            if any(word in description for word in ["image", "picture", "photo"]):
                return "image"
            elif any(word in description for word in ["button", "link", "click"]):
                return "buttonList"
        
        # Default to textParagraph for general text content
        return "textParagraph"
    
    def infer_parameters(self, widget_type: str, description: str) -> Dict[str, Any]:
        """
        Infer parameters for a widget from a natural language description.
        
        Args:
            widget_type: Type of widget
            description: Natural language description
            
        Returns:
            Dictionary of inferred parameters
        """
        # Get parameter definitions for this widget type
        widget_info = self.widget_types.get(widget_type, {"parameters": {}})
        param_defs = widget_info["parameters"]
        
        # Initialize parameters with defaults
        params = {}
        for param_name, param_def in param_defs.items():
            if param_def.default_value is not None:
                params[param_name] = param_def.default_value
        
        # Extract parameters from description
        if widget_type == "textParagraph":
            # For text paragraphs, use the entire description as the text
            params["text"] = description
            
        elif widget_type == "image":
            # Extract image URL
            url_match = re.search(self.parameter_patterns["url"], description)
            if url_match:
                params["imageUrl"] = url_match.group(0)
            
            # Extract alt text (anything after "alt:" or "alt text:" or similar)
            alt_match = re.search(r'alt(?:\s*text)?[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if alt_match:
                params["altText"] = alt_match.group(1).strip()
            
        elif widget_type == "decoratedText":
            # Extract main text (everything not matching other patterns)
            text = description
            
            # Extract top label (anything after "label:" or before "text:")
            label_match = re.search(r'(?:top\s*)?label[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if label_match:
                params["topLabel"] = label_match.group(1).strip()
                # Remove from text
                text = text.replace(label_match.group(0), "")
            
            # Extract bottom label
            bottom_match = re.search(r'bottom\s*label[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if bottom_match:
                params["bottomLabel"] = bottom_match.group(1).strip()
                # Remove from text
                text = text.replace(bottom_match.group(0), "")
            
            # Extract icon
            icon_match = re.search(r'icon[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if icon_match:
                icon_name = icon_match.group(1).strip().upper()
                params["startIcon"] = {"knownIcon": icon_name}
                # Remove from text
                text = text.replace(icon_match.group(0), "")
            
            # Clean up text
            text = re.sub(r'\s+', ' ', text).strip()
            if text:
                params["text"] = text
            
        elif widget_type == "buttonList":
            # Extract button information
            buttons = []
            
            # Look for explicit button definitions
            button_matches = re.finditer(r'button[:\s]+([^,\.]+)(?:\s+url[:\s]+([^,\.]+))?', description, re.IGNORECASE)
            for match in button_matches:
                button_text = match.group(1).strip()
                button_url = None
                if match.group(2):
                    button_url = match.group(2).strip()
                else:
                    # Look for URL in the description
                    url_match = re.search(self.parameter_patterns["url"], description)
                    if url_match:
                        button_url = url_match.group(0)
                
                if button_url:
                    buttons.append({
                        "text": button_text,
                        "onClick": {
                            "openLink": {
                                "url": button_url
                            }
                        }
                    })
            
            # If no explicit buttons found, create one from the description
            if not buttons:
                # Extract URL
                url_match = re.search(self.parameter_patterns["url"], description)
                if url_match:
                    url = url_match.group(0)
                    # Use text before or after URL as button text
                    parts = description.split(url)
                    button_text = parts[0].strip() if parts[0].strip() else "Click here"
                    if not button_text:
                        button_text = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "Click here"
                    
                    buttons.append({
                        "text": button_text,
                        "onClick": {
                            "openLink": {
                                "url": url
                            }
                        }
                    })
            
            if buttons:
                params["buttons"] = buttons
            
        elif widget_type == "textInput":
            # Extract name
            name_match = re.search(r'name[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if name_match:
                params["name"] = name_match.group(1).strip()
            else:
                # Generate a name from the description
                words = re.findall(r'\w+', description.lower())
                if words:
                    params["name"] = words[0] + "Input"
            
            # Extract label
            label_match = re.search(r'label[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if label_match:
                params["label"] = label_match.group(1).strip()
            else:
                # Use first sentence as label
                sentences = description.split('.')
                if sentences:
                    params["label"] = sentences[0].strip()
            
            # Extract hint text
            hint_match = re.search(r'hint(?:\s*text)?[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if hint_match:
                params["hintText"] = hint_match.group(1).strip()
            
            # Extract type
            if "multiple" in description.lower() or "multi-line" in description.lower() or "multiline" in description.lower():
                params["type"] = "MULTIPLE_LINE"
            else:
                params["type"] = "SINGLE_LINE"
            
        elif widget_type == "selectionInput":
            # Extract name
            name_match = re.search(r'name[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if name_match:
                params["name"] = name_match.group(1).strip()
            else:
                # Generate a name from the description
                words = re.findall(r'\w+', description.lower())
                if words:
                    params["name"] = words[0] + "Selection"
            
            # Extract label
            label_match = re.search(r'label[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if label_match:
                params["label"] = label_match.group(1).strip()
            else:
                # Use first sentence as label
                sentences = description.split('.')
                if sentences:
                    params["label"] = sentences[0].strip()
            
            # Determine type
            if "dropdown" in description.lower() or "select" in description.lower():
                params["type"] = "DROPDOWN"
            elif "checkbox" in description.lower() or "check box" in description.lower():
                params["type"] = "CHECK_BOX"
            elif "radio" in description.lower():
                params["type"] = "RADIO_BUTTON"
            elif "switch" in description.lower() or "toggle" in description.lower():
                params["type"] = "SWITCH"
            else:
                params["type"] = "DROPDOWN"  # Default
            
            # Extract items
            items = []
            
            # Look for explicit item definitions
            item_matches = re.finditer(r'(?:item|option)[:\s]+([^,\.]+)(?:\s+value[:\s]+([^,\.]+))?', description, re.IGNORECASE)
            for match in item_matches:
                item_text = match.group(1).strip()
                item_value = match.group(2).strip() if match.group(2) else item_text
                items.append({
                    "text": item_text,
                    "value": item_value
                })
            
            # If no explicit items found, look for lists
            if not items:
                # Look for comma-separated lists
                list_match = re.search(r'(?:items|options)[:\s]+(.+)', description, re.IGNORECASE)
                if list_match:
                    list_text = list_match.group(1).strip()
                    item_texts = [item.strip() for item in list_text.split(',')]
                    for item_text in item_texts:
                        if item_text:
                            items.append({
                                "text": item_text,
                                "value": item_text
                            })
            
            # If still no items, create some defaults
            if not items:
                if params["type"] == "CHECK_BOX" or params["type"] == "SWITCH":
                    items.append({"text": "Enabled", "value": "true"})
                elif params["type"] == "RADIO_BUTTON":
                    items.extend([
                        {"text": "Option 1", "value": "option1"},
                        {"text": "Option 2", "value": "option2"}
                    ])
                else:  # DROPDOWN
                    items.extend([
                        {"text": "Option 1", "value": "option1"},
                        {"text": "Option 2", "value": "option2"},
                        {"text": "Option 3", "value": "option3"}
                    ])
            
            if items:
                params["items"] = items
        
        return params
    
    def validate_parameters(self, widget_type: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clean up parameters for a widget.
        
        Args:
            widget_type: Type of widget
            parameters: Parameters to validate
            
        Returns:
            Validated and cleaned parameters
        """
        # Get parameter definitions for this widget type
        widget_info = self.widget_types.get(widget_type, {"parameters": {}})
        param_defs = widget_info["parameters"]
        
        # Initialize validated parameters
        validated = {}
        
        # Check each parameter
        for param_name, param_value in parameters.items():
            # Skip if parameter is not defined for this widget type
            if param_name not in param_defs:
                continue
            
            # Get parameter definition
            param_def = param_defs[param_name]
            
            # Validate parameter
            if param_def.validate(param_value):
                validated[param_name] = param_value
        
        # Check for required parameters
        for param_name, param_def in param_defs.items():
            if param_def.required and param_name not in validated:
                # If a required parameter is missing, use default value if available
                if param_def.default_value is not None:
                    validated[param_name] = param_def.default_value
        
        return validated