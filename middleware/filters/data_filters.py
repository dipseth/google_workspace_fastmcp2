"""
Data manipulation and property access filters for Jinja2 templates.

Provides filters for extracting properties, safely accessing data, and mapping
lists/attributes in template processing.
"""

from typing import Any, List
import logging

logger = logging.getLogger(__name__)


def extract_filter(data: Any, path: str) -> Any:
    """
    Extract property from data using dot notation.
    
    Safely navigates nested data structures using dot-separated property paths.
    Handles both dictionary keys and object attributes.
    
    Args:
        data: Source data object or dictionary
        path: Dot-separated property path (e.g., 'user.profile.email')
        
    Returns:
        Extracted property value or None if path not found
        
    Usage in templates:
        {{ data | extract('user.profile.email') }}
        {{ response | extract('results.0.title') }}
        {{ settings | extract('theme.colors.primary') }}
    """
    return _extract_property(data, path)


def safe_get_filter(data: Any, key: str, default: Any = '') -> Any:
    """
    Safely get a value from data.
    
    Attempts to retrieve a value using dictionary access or attribute access,
    returning a default value if the key/attribute is not found.
    
    Args:
        data: Source data (dict, object, etc.)
        key: Key or attribute name to retrieve
        default: Default value to return if key not found (default: '')
        
    Returns:
        Retrieved value or default if not found
        
    Usage in templates:
        {{ user | safe_get('name', 'Anonymous') }}
        {{ config | safe_get('timeout', 30) }}
        {{ response | safe_get('status') }}  # Returns '' if not found
    """
    if isinstance(data, dict):
        return data.get(key, default)
    elif hasattr(data, key):
        return getattr(data, key, default)
    return default


def map_list_filter(items: Any, attribute: str = None) -> List[Any]:
    """
    Map items to attribute values and return as list.
    
    Extracts a specific attribute from each item in a collection,
    handling both dictionary and object attribute access.
    
    Args:
        items: Iterable of items to map
        attribute: Attribute name to extract from each item (optional)
        
    Returns:
        List of extracted attribute values
        
    Usage in templates:
        {{ users | map_list('name') }}  # Extract name from each user
        {{ products | map_list('price') }}  # Extract price from each product  
        {{ items | map_list }}  # Convert to list without extraction
    """
    try:
        if not items:
            return []

        if attribute:
            # Handle both dict/list access and SimpleNamespace attribute access
            result = []
            for item in items:
                if hasattr(item, attribute):
                    result.append(getattr(item, attribute))
                elif isinstance(item, dict):
                    result.append(item.get(attribute, ''))
                else:
                    result.append(str(item))
            return result
        else:
            return list(items)
    except Exception as e:
        logger.debug(f"⚠️ map_list filter error: {e}")
        return []


def map_attribute_filter(items: Any, attribute: str) -> List[Any]:
    """
    Map items to attribute values (alias for map_list).
    
    This is an alias for map_list_filter with a required attribute parameter.
    Provides a more explicit name when the intention is specifically to map attributes.
    
    Args:
        items: Iterable of items to map
        attribute: Attribute name to extract from each item
        
    Returns:
        List of extracted attribute values
        
    Usage in templates:
        {{ users | map_attr('email') }}
        {{ documents | map_attr('title') }}
        {{ results | map_attr('score') }}
    """
    return map_list_filter(items, attribute)


def _extract_property(data: Any, property_path: str) -> Any:
    """
    Internal helper to extract a property from data using dot-notation path.
    
    Args:
        data: Source data object or dictionary
        property_path: Dot-separated property path
        
    Returns:
        Extracted property value or None if path not found
    """
    if data is None:
        return None
    
    parts = property_path.split('.')
    current = data
    
    for part in parts:
        try:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
        except (KeyError, IndexError, AttributeError, TypeError):
            return None
    
    return current