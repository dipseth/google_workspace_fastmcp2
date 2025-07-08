"""
Models for Content Mapping and Parameter Inference

This module defines the data models used by the content mapping and parameter inference
engines for Google Chat card creation.
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field


class ContentFormat(Enum):
    """Enum representing different content format types that can be parsed."""
    UNSTRUCTURED = "unstructured"
    STRUCTURED = "structured"
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"
    KEY_VALUE = "key_value"
    BULLET_LIST = "bullet_list"
    NUMBERED_LIST = "numbered_list"


@dataclass
class ContentElement:
    """Represents a parsed content element from natural language input."""
    type: str
    content: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    children: List['ContentElement'] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the content element to a dictionary."""
        return {
            "type": self.type,
            "content": self.content,
            "attributes": self.attributes,
            "children": [child.to_dict() for child in self.children]
        }


@dataclass
class WidgetMapping:
    """Mapping between content elements and card widgets."""
    content_type: str
    widget_type: str
    mapping_rules: Dict[str, str] = field(default_factory=dict)
    default_parameters: Dict[str, Any] = field(default_factory=dict)
    
    def apply_mapping(self, content_element: ContentElement) -> Dict[str, Any]:
        """
        Apply mapping rules to convert a content element to widget parameters.
        
        Args:
            content_element: The content element to map
            
        Returns:
            Dictionary of widget parameters
        """
        params = self.default_parameters.copy()
        
        # Apply mapping rules
        for attr_name, param_name in self.mapping_rules.items():
            if attr_name in content_element.attributes:
                params[param_name] = content_element.attributes[attr_name]
        
        # Always map content to the primary content field
        if not params and content_element.content:
            if self.widget_type == "textParagraph":
                params["text"] = content_element.content
            elif self.widget_type == "decoratedText":
                params["text"] = content_element.content
            elif self.widget_type == "button":
                params["text"] = content_element.content
        
        return {
            "type": self.widget_type,
            "parameters": params
        }


@dataclass
class Template:
    """Template for card creation."""
    template_id: str
    name: str
    description: str
    template: Dict[str, Any]
    placeholders: Dict[str, str] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def apply(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply content to the template.
        
        Args:
            content: Content to apply to the template
            
        Returns:
            Populated template as a dictionary
        """
        result = self.template.copy()
        
        # Replace placeholders in the template
        for placeholder, path in self.placeholders.items():
            if placeholder in content:
                # Parse the path and set the value
                parts = path.split('.')
                target = result
                
                # Navigate to the target location
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        # Set the value at the final location
                        target[part] = content[placeholder]
                    else:
                        # Create nested dictionaries if they don't exist
                        if part not in target:
                            target[part] = {}
                        target = target[part]
        
        return result


@dataclass
class ParameterDefinition:
    """Definition of a parameter for a widget or card."""
    name: str
    type: str
    description: str
    required: bool = False
    default_value: Any = None
    possible_values: List[Any] = field(default_factory=list)
    
    def validate(self, value: Any) -> bool:
        """
        Validate a value against this parameter definition.
        
        Args:
            value: The value to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check if value is required but not provided
        if self.required and value is None:
            return False
            
        # If value is None and not required, it's valid
        if value is None:
            return True
            
        # Check type
        if self.type == "string" and not isinstance(value, str):
            return False
        elif self.type == "number" and not isinstance(value, (int, float)):
            return False
        elif self.type == "boolean" and not isinstance(value, bool):
            return False
        elif self.type == "array" and not isinstance(value, list):
            return False
        elif self.type == "object" and not isinstance(value, dict):
            return False
            
        # Check possible values if defined
        if self.possible_values and value not in self.possible_values:
            return False
            
        return True