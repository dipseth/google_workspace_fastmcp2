"""
Content Mapping Engine for Google Chat Card Creation

This module provides the ContentMappingEngine class, which parses natural language
content descriptions and maps them to card structures for Google Chat.
"""

import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
import yaml

from .models import ContentFormat, ContentElement, WidgetMapping

logger = logging.getLogger(__name__)


class ContentMappingEngine:
    """
    Engine for mapping content descriptions to card structures.
    
    The ContentMappingEngine parses natural language content descriptions and
    maps them to structured card components for Google Chat. It supports various
    content formats and provides intelligent mapping to appropriate widget types.
    """
    
    def __init__(self):
        """Initialize the ContentMappingEngine."""
        # Initialize widget mappings
        self.widget_mappings = {
            "heading": WidgetMapping(
                content_type="heading",
                widget_type="decoratedText",
                mapping_rules={"level": "topLabel", "style": "style"},
                default_parameters={"wrapText": True}
            ),
            "paragraph": WidgetMapping(
                content_type="paragraph",
                widget_type="textParagraph",
                default_parameters={}
            ),
            "list_item": WidgetMapping(
                content_type="list_item",
                widget_type="decoratedText",
                default_parameters={"startIcon": {"knownIcon": "BULLET"}}
            ),
            "image": WidgetMapping(
                content_type="image",
                widget_type="image",
                mapping_rules={"url": "imageUrl", "alt": "altText"}
            ),
            "button": WidgetMapping(
                content_type="button",
                widget_type="buttonList",
                mapping_rules={"url": "url", "text": "text"}
            ),
            "divider": WidgetMapping(
                content_type="divider",
                widget_type="divider",
                default_parameters={}
            )
        }
    
    def parse_content(self, content_spec: str) -> Dict[str, Any]:
        """
        Parse content specification into a structured card representation.
        
        Args:
            content_spec: Natural language content specification
            
        Returns:
            Dictionary representing the parsed content as a card structure
        """
        # Detect content format
        content_format = self.detect_content_format(content_spec)
        
        # Parse based on detected format
        if content_format == ContentFormat.STRUCTURED:
            return self.parse_structured_format(content_spec)
        elif content_format == ContentFormat.JSON:
            try:
                return json.loads(content_spec)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON content: {e}")
                # Fall back to structured format
                return self.parse_structured_format(content_spec)
        elif content_format == ContentFormat.YAML:
            try:
                return yaml.safe_load(content_spec)
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse YAML content: {e}")
                # Fall back to structured format
                return self.parse_structured_format(content_spec)
        elif content_format == ContentFormat.MARKDOWN:
            # Extract content elements from markdown
            elements = self.extract_content_elements(content_spec)
            # Map elements to card structure
            return self.map_elements_to_card(elements)
        elif content_format == ContentFormat.KEY_VALUE:
            # Parse key-value pairs
            return self.parse_key_value_pairs(content_spec)
        else:
            # Default to unstructured text parsing
            elements = self.extract_content_elements(content_spec)
            return self.map_elements_to_card(elements)
    
    def detect_content_format(self, content_spec: str) -> ContentFormat:
        """
        Detect the format of the content specification.
        
        Args:
            content_spec: Content specification to analyze
            
        Returns:
            Detected ContentFormat
        """
        # Check for JSON format
        if content_spec.strip().startswith('{') and content_spec.strip().endswith('}'):
            try:
                json.loads(content_spec)
                return ContentFormat.JSON
            except json.JSONDecodeError:
                pass
        
        # Check for YAML format
        if ':' in content_spec and '\n' in content_spec:
            try:
                yaml.safe_load(content_spec)
                return ContentFormat.YAML
            except yaml.YAMLError:
                pass
        
        # Check for Markdown format
        markdown_indicators = ['#', '##', '###', '```', '**', '*', '- ', '1. ', '> ']
        if any(content_spec.strip().startswith(indicator) for indicator in markdown_indicators):
            return ContentFormat.MARKDOWN
        
        # Check for key-value pairs
        if re.search(r'^[\w\s]+:\s*.+$', content_spec, re.MULTILINE):
            return ContentFormat.KEY_VALUE
        
        # Check for bullet list
        if re.search(r'^[\s]*[•\-\*]\s+.+$', content_spec, re.MULTILINE):
            return ContentFormat.BULLET_LIST
        
        # Check for numbered list
        if re.search(r'^[\s]*\d+\.\s+.+$', content_spec, re.MULTILINE):
            return ContentFormat.NUMBERED_LIST
        
        # Default to structured format (which handles plain text too)
        return ContentFormat.STRUCTURED
    
    def parse_structured_format(self, content_spec: str) -> Dict[str, Any]:
        """
        Parse content in a structured format into a card representation.
        
        This handles both structured formats and plain text by extracting
        meaningful elements and mapping them to card components.
        
        Args:
            content_spec: Content specification in structured format
            
        Returns:
            Dictionary representing the parsed content as a card structure
        """
        # Extract content elements
        elements = self.extract_content_elements(content_spec)
        
        # Map elements to card structure
        return self.map_elements_to_card(elements)
    
    def extract_content_elements(self, text: str) -> List[ContentElement]:
        """
        Extract content elements from text.
        
        Args:
            text: Text to extract elements from
            
        Returns:
            List of ContentElement objects
        """
        elements = []
        lines = text.split('\n')
        
        # Process each line
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check for headings
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                level = len(heading_match.group(1))
                content = heading_match.group(2)
                elements.append(ContentElement(
                    type="heading",
                    content=content,
                    attributes={"level": level}
                ))
                continue
            
            # Check for list items
            list_match = re.match(r'^[\s]*[•\-\*]\s+(.+)$', line)
            if list_match:
                content = list_match.group(1)
                elements.append(ContentElement(
                    type="list_item",
                    content=content
                ))
                continue
            
            # Check for numbered list items
            numbered_match = re.match(r'^[\s]*\d+\.\s+(.+)$', line)
            if numbered_match:
                content = numbered_match.group(1)
                elements.append(ContentElement(
                    type="list_item",
                    content=content,
                    attributes={"numbered": True}
                ))
                continue
            
            # Check for image references
            image_match = re.match(r'!\[(.*?)\]\((.*?)\)', line)
            if image_match:
                alt = image_match.group(1)
                url = image_match.group(2)
                elements.append(ContentElement(
                    type="image",
                    content="",
                    attributes={"url": url, "alt": alt}
                ))
                continue
            
            # Check for links/buttons
            link_match = re.match(r'\[(.*?)\]\((.*?)\)', line)
            if link_match:
                text = link_match.group(1)
                url = link_match.group(2)
                elements.append(ContentElement(
                    type="button",
                    content=text,
                    attributes={"url": url}
                ))
                continue
            
            # Check for dividers
            if re.match(r'^[\s]*[-_*]{3,}[\s]*$', line):
                elements.append(ContentElement(
                    type="divider",
                    content=""
                ))
                continue
            
            # Default to paragraph
            elements.append(ContentElement(
                type="paragraph",
                content=line
            ))
        
        return elements
    
    def map_elements_to_card(self, elements: List[ContentElement]) -> Dict[str, Any]:
        """
        Map content elements to a card structure.
        
        Args:
            elements: List of ContentElement objects
            
        Returns:
            Dictionary representing a card structure
        """
        # Initialize card structure
        card = {
            "sections": []
        }
        
        # Check for header elements
        header_elements = [e for e in elements if e.type == "heading" and e.attributes.get("level", 0) <= 2]
        if header_elements:
            header = header_elements[0]
            card["header"] = {
                "title": header.content
            }
            
            # If there's a second header, use it as subtitle
            if len(header_elements) > 1:
                card["header"]["subtitle"] = header_elements[1].content
            
            # Remove header elements from the list
            elements = [e for e in elements if e not in header_elements[:2]]
        
        # Group remaining elements into sections
        current_section = {"widgets": []}
        
        for element in elements:
            # Apply widget mapping
            widget_mapping = self.widget_mappings.get(element.type)
            if not widget_mapping:
                # Default to paragraph for unknown types
                widget_mapping = self.widget_mappings["paragraph"]
            
            widget_info = widget_mapping.apply_mapping(element)
            
            # Special handling for certain widget types
            if widget_info["type"] == "buttonList":
                # Create a button with onClick action
                button = {
                    "text": element.content,
                    "onClick": {
                        "openLink": {
                            "url": element.attributes.get("url", "")
                        }
                    }
                }
                
                # Check if we already have a buttonList widget
                button_list_exists = False
                for widget in current_section["widgets"]:
                    if "buttonList" in widget:
                        widget["buttonList"]["buttons"].append(button)
                        button_list_exists = True
                        break
                
                if not button_list_exists:
                    # Create a new buttonList widget
                    current_section["widgets"].append({
                        "buttonList": {
                            "buttons": [button]
                        }
                    })
            elif widget_info["type"] == "divider":
                # Add the current section if it has widgets
                if current_section["widgets"]:
                    card["sections"].append(current_section)
                    current_section = {"widgets": []}
                
                # Add a divider widget to a new section
                current_section["widgets"].append({"divider": {}})
                
                # Add the section with divider
                card["sections"].append(current_section)
                current_section = {"widgets": []}
            else:
                # Add the widget to the current section
                widget_key = widget_info["type"]
                current_section["widgets"].append({
                    widget_key: widget_info["parameters"]
                })
        
        # Add the final section if it has widgets
        if current_section["widgets"]:
            card["sections"].append(current_section)
        
        return card
    
    def parse_key_value_pairs(self, content_spec: str) -> Dict[str, Any]:
        """
        Parse key-value pairs into a card structure.
        
        Args:
            content_spec: Content specification with key-value pairs
            
        Returns:
            Dictionary representing a card structure
        """
        # Initialize card structure
        card = {
            "sections": [{"widgets": []}]
        }
        
        # Extract key-value pairs
        pairs = re.findall(r'^([\w\s]+):\s*(.+)$', content_spec, re.MULTILINE)
        
        for key, value in pairs:
            key = key.strip()
            value = value.strip()
            
            # Handle special keys
            if key.lower() in ["title", "header"]:
                if "header" not in card:
                    card["header"] = {}
                card["header"]["title"] = value
            elif key.lower() in ["subtitle", "subheader"]:
                if "header" not in card:
                    card["header"] = {}
                card["header"]["subtitle"] = value
            elif key.lower() in ["image", "image_url", "imageurl"]:
                card["sections"][0]["widgets"].append({
                    "image": {
                        "imageUrl": value
                    }
                })
            elif key.lower() in ["text", "content", "description"]:
                card["sections"][0]["widgets"].append({
                    "textParagraph": {
                        "text": value
                    }
                })
            else:
                # Default to decorated text for other key-value pairs
                card["sections"][0]["widgets"].append({
                    "decoratedText": {
                        "topLabel": key,
                        "text": value
                    }
                })
        
        return card