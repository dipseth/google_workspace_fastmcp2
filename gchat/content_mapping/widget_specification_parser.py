"""
Widget Specification Parser for Google Chat Card Creation

This module provides the WidgetSpecificationParser class, which parses natural language
descriptions of widgets and converts them into properly formatted widget objects.
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple
import json

from .models import ContentElement
from .parameter_inference_engine import ParameterInferenceEngine

logger = logging.getLogger(__name__)


class WidgetSpecificationParser:
    """
    Parser for natural language widget specifications.
    
    The WidgetSpecificationParser parses natural language descriptions of widgets
    and converts them into properly formatted widget objects for Google Chat cards.
    It supports common widget types (buttons, text, images, etc.) and integrates
    with the ContentMappingEngine.
    """
    
    def __init__(self, parameter_inference_engine: Optional[ParameterInferenceEngine] = None):
        """
        Initialize the WidgetSpecificationParser.
        
        Args:
            parameter_inference_engine: Optional ParameterInferenceEngine instance to reuse
        """
        self.parameter_inference_engine = parameter_inference_engine
        
        if self.parameter_inference_engine is None:
            self.parameter_inference_engine = ParameterInferenceEngine()
        
        # Define widget type patterns for identification
        self.widget_type_patterns = {
            "button": [
                r'(?:add|create|insert)?\s*(?:a|an)?\s*button\s+(?:labeled|with text|that says|saying|with label)?\s*[\'"]?([^\'"\n]+)[\'"]?',
                r'button\s+(?:that|which|to)?\s*(?:opens|links to|redirects to|goes to|navigates to)?\s*(?:the|a|an)?\s*(?:url|link|site|page|website)?\s*(?:at|of)?\s*([^\s]+)',
                r'(?:add|create|insert)?\s*(?:a|an)?\s*(?:clickable)?\s*button\s+(?:for|to)?\s*([^,\n]+)'
            ],
            "image": [
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*image\s+(?:from|at|with url|located at)?\s*([^\s,]+)',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:picture|photo|graphic|icon)\s+(?:from|at|with url|located at)?\s*([^\s,]+)',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*image\s+(?:of|showing|displaying|with)?\s*([^,\n]+)'
            ],
            "text": [
                r'(?:add|create|insert|include|show)?\s*(?:a|an|some)?\s*text\s+(?:saying|that says|with content|with message|with the message)?\s*[\'"]?([^\'"\n]+)[\'"]?',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:paragraph|text block|text section)\s+(?:with|containing|that says)?\s*[\'"]?([^\'"\n]+)[\'"]?'
            ],
            "decoratedText": [
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:decorated|styled|formatted)\s*text\s+(?:with|containing|that says)?\s*[\'"]?([^\'"\n]+)[\'"]?',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*text\s+(?:with|having)?\s*(?:an|a)?\s*icon\s+(?:of|showing|displaying)?\s*([^,\n]+)',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:labeled|with label)\s*text\s+(?:with label|labeled as)?\s*[\'"]?([^\'"\n]+)[\'"]?'
            ],
            "divider": [
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*divider',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:horizontal|vertical)?\s*(?:line|separator|hr|rule)',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:section|content)?\s*(?:divider|separator|break)'
            ],
            "textInput": [
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:text)?\s*input\s+(?:field|box|area)?\s*(?:for|to collect|to enter|to input)?\s*([^,\n]+)',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:field|form field|entry field)\s+(?:for|to collect|to enter|to input)?\s*([^,\n]+)'
            ],
            "selectionInput": [
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*dropdown\s+(?:for|to select|to choose|with options|containing options)?\s*([^,\n]+)',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:checkbox|check box|radio button|radio|toggle|switch)\s+(?:for|to select|to choose|with label)?\s*([^,\n]+)',
                r'(?:add|create|insert|include|show)?\s*(?:a|an)?\s*(?:selection|choice|option)\s+(?:field|input|menu|list)\s+(?:for|to select|to choose)?\s*([^,\n]+)'
            ]
        }
        
        # Define URL pattern for extraction
        self.url_pattern = r'https?://\S+|www\.\S+|\b[a-z0-9\-]+\.[a-z]{2,}\S*'
    
    def parse_widget_description(self, description: str) -> Dict[str, Any]:
        """
        Parse a natural language widget description into a widget object.
        
        Args:
            description: Natural language description of the widget
            
        Returns:
            Dictionary representing the widget object
        """
        # Identify widget type
        widget_type = self.identify_widget_type(description)
        
        # Extract widget parameters
        parameters = self.extract_widget_parameters(description, widget_type)
        
        # Convert to widget object
        widget_object = self.convert_to_widget_object(widget_type, parameters)
        
        return widget_object
    
    def identify_widget_type(self, description: str) -> str:
        """
        Identify the widget type from a natural language description.
        
        Args:
            description: Natural language description of the widget
            
        Returns:
            Identified widget type
        """
        description = description.lower()
        
        # Check each widget type pattern
        for widget_type, patterns in self.widget_type_patterns.items():
            for pattern in patterns:
                if re.search(pattern, description, re.IGNORECASE):
                    return widget_type
        
        # If no specific pattern matches, use parameter inference engine
        return self.parameter_inference_engine.infer_widget_type(description)
    
    def extract_widget_parameters(self, description: str, widget_type: str) -> Dict[str, Any]:
        """
        Extract parameters for a widget from a natural language description.
        
        Args:
            description: Natural language description of the widget
            widget_type: Type of widget
            
        Returns:
            Dictionary of extracted parameters
        """
        parameters = {}
        
        if widget_type == "button":
            # Extract button text
            for pattern in self.widget_type_patterns["button"]:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    parameters["text"] = match.group(1).strip()
                    break
            
            # Extract URL
            url_match = re.search(self.url_pattern, description)
            if url_match:
                parameters["url"] = url_match.group(0)
            
            # If no text was found, use a default
            if "text" not in parameters:
                parameters["text"] = "Click here"
        
        elif widget_type == "image":
            # Extract image URL
            url_match = re.search(self.url_pattern, description)
            if url_match:
                parameters["imageUrl"] = url_match.group(0)
            
            # Extract alt text
            alt_match = re.search(r'alt(?:\s*text)?[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if alt_match:
                parameters["altText"] = alt_match.group(1).strip()
            else:
                # Try to extract a description for alt text
                for pattern in self.widget_type_patterns["image"]:
                    match = re.search(pattern, description, re.IGNORECASE)
                    if match and not re.match(self.url_pattern, match.group(1)):
                        parameters["altText"] = match.group(1).strip()
                        break
        
        elif widget_type == "text":
            # Extract text content
            for pattern in self.widget_type_patterns["text"]:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    parameters["text"] = match.group(1).strip()
                    break
            
            # If no text was found, use the whole description
            if "text" not in parameters:
                parameters["text"] = description
        
        elif widget_type == "decoratedText":
            # Extract text content
            for pattern in self.widget_type_patterns["decoratedText"]:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    parameters["text"] = match.group(1).strip()
                    break
            
            # Extract top label
            label_match = re.search(r'(?:top\s*)?label[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if label_match:
                parameters["topLabel"] = label_match.group(1).strip()
            
            # Extract bottom label
            bottom_match = re.search(r'bottom\s*label[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if bottom_match:
                parameters["bottomLabel"] = bottom_match.group(1).strip()
            
            # Extract icon
            icon_match = re.search(r'icon[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if icon_match:
                icon_name = icon_match.group(1).strip().upper()
                parameters["startIcon"] = {"knownIcon": icon_name}
            
            # If no text was found, use the whole description
            if "text" not in parameters:
                parameters["text"] = description
        
        elif widget_type == "divider":
            # Divider doesn't need parameters
            pass
        
        elif widget_type == "textInput":
            # Extract name
            name_match = re.search(r'name[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if name_match:
                parameters["name"] = name_match.group(1).strip()
            else:
                # Generate a name from the description
                for pattern in self.widget_type_patterns["textInput"]:
                    match = re.search(pattern, description, re.IGNORECASE)
                    if match:
                        field_name = match.group(1).strip()
                        parameters["name"] = re.sub(r'\W+', '_', field_name.lower())
                        break
                
                # If still no name, use a default
                if "name" not in parameters:
                    parameters["name"] = "textInput"
            
            # Extract label
            label_match = re.search(r'label[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if label_match:
                parameters["label"] = label_match.group(1).strip()
            else:
                # Use field name as label
                for pattern in self.widget_type_patterns["textInput"]:
                    match = re.search(pattern, description, re.IGNORECASE)
                    if match:
                        parameters["label"] = match.group(1).strip()
                        break
                
                # If still no label, use a default
                if "label" not in parameters:
                    parameters["label"] = "Enter text"
            
            # Extract hint text
            hint_match = re.search(r'hint(?:\s*text)?[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if hint_match:
                parameters["hintText"] = hint_match.group(1).strip()
            
            # Determine if multi-line
            if "multiple" in description.lower() or "multi-line" in description.lower() or "multiline" in description.lower():
                parameters["type"] = "MULTIPLE_LINE"
            else:
                parameters["type"] = "SINGLE_LINE"
        
        elif widget_type == "selectionInput":
            # Extract name
            name_match = re.search(r'name[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if name_match:
                parameters["name"] = name_match.group(1).strip()
            else:
                # Generate a name from the description
                for pattern in self.widget_type_patterns["selectionInput"]:
                    match = re.search(pattern, description, re.IGNORECASE)
                    if match:
                        field_name = match.group(1).strip()
                        parameters["name"] = re.sub(r'\W+', '_', field_name.lower())
                        break
                
                # If still no name, use a default
                if "name" not in parameters:
                    parameters["name"] = "selectionInput"
            
            # Extract label
            label_match = re.search(r'label[:\s]+([^,\.]+)', description, re.IGNORECASE)
            if label_match:
                parameters["label"] = label_match.group(1).strip()
            else:
                # Use field name as label
                for pattern in self.widget_type_patterns["selectionInput"]:
                    match = re.search(pattern, description, re.IGNORECASE)
                    if match:
                        parameters["label"] = match.group(1).strip()
                        break
                
                # If still no label, use a default
                if "label" not in parameters:
                    parameters["label"] = "Select an option"
            
            # Determine type
            if "dropdown" in description.lower() or "select" in description.lower():
                parameters["type"] = "DROPDOWN"
            elif "checkbox" in description.lower() or "check box" in description.lower():
                parameters["type"] = "CHECK_BOX"
            elif "radio" in description.lower():
                parameters["type"] = "RADIO_BUTTON"
            elif "switch" in description.lower() or "toggle" in description.lower():
                parameters["type"] = "SWITCH"
            else:
                parameters["type"] = "DROPDOWN"  # Default
            
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
                if parameters["type"] == "CHECK_BOX" or parameters["type"] == "SWITCH":
                    items.append({"text": "Enabled", "value": "true"})
                elif parameters["type"] == "RADIO_BUTTON":
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
                parameters["items"] = items
        
        return parameters
    
    def convert_to_widget_object(self, widget_type: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert widget type and parameters to a widget object.
        
        Args:
            widget_type: Type of widget
            parameters: Widget parameters
            
        Returns:
            Dictionary representing the widget object
        """
        widget_object = {}
        
        if widget_type == "button":
            # Create a button with onClick action
            button = {
                "text": parameters.get("text", "Click here")
            }
            
            # Add URL if provided
            if "url" in parameters:
                button["onClick"] = {
                    "openLink": {
                        "url": parameters["url"]
                    }
                }
            
            # Create buttonList widget
            widget_object["buttonList"] = {
                "buttons": [button]
            }
        
        elif widget_type == "image":
            # Create image widget
            widget_object["image"] = {
                "imageUrl": parameters.get("imageUrl", "")
            }
            
            # Add alt text if provided
            if "altText" in parameters:
                widget_object["image"]["altText"] = parameters["altText"]
        
        elif widget_type == "text":
            # Create textParagraph widget
            widget_object["textParagraph"] = {
                "text": parameters.get("text", "")
            }
        
        elif widget_type == "decoratedText":
            # Create decoratedText widget
            widget_object["decoratedText"] = {
                "text": parameters.get("text", "")
            }
            
            # Add optional parameters
            if "topLabel" in parameters:
                widget_object["decoratedText"]["topLabel"] = parameters["topLabel"]
            
            if "bottomLabel" in parameters:
                widget_object["decoratedText"]["bottomLabel"] = parameters["bottomLabel"]
            
            if "startIcon" in parameters:
                widget_object["decoratedText"]["startIcon"] = parameters["startIcon"]
            
            # Add default wrapText
            widget_object["decoratedText"]["wrapText"] = True
        
        elif widget_type == "divider":
            # Create divider widget
            widget_object["divider"] = {}
        
        elif widget_type == "textInput":
            # Create textInput widget
            widget_object["textInput"] = {
                "name": parameters.get("name", "textInput"),
                "label": parameters.get("label", "Enter text")
            }
            
            # Add optional parameters
            if "hintText" in parameters:
                widget_object["textInput"]["hintText"] = parameters["hintText"]
            
            if "type" in parameters:
                widget_object["textInput"]["type"] = parameters["type"]
            
            if "value" in parameters:
                widget_object["textInput"]["value"] = parameters["value"]
        
        elif widget_type == "selectionInput":
            # Create selectionInput widget
            widget_object["selectionInput"] = {
                "name": parameters.get("name", "selectionInput"),
                "label": parameters.get("label", "Select an option"),
                "type": parameters.get("type", "DROPDOWN")
            }
            
            # Add items
            if "items" in parameters:
                widget_object["selectionInput"]["items"] = parameters["items"]
        
        return widget_object