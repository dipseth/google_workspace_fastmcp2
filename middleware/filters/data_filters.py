"""
Data manipulation and property access filters for Jinja2 templates.

Provides filters for extracting properties, safely accessing data, and mapping
lists/attributes in template processing.
"""

import re
from typing import Any, List

from config.enhanced_logging import setup_logger

logger = setup_logger()


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


def safe_get_filter(data: Any, key: str, default: Any = "") -> Any:
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
                    result.append(item.get(attribute, ""))
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

    parts = property_path.split(".")
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


# =============================================================================
# Structural merge / placeholder filters (used by saved email templates)
# =============================================================================

PLACEHOLDER_PATTERN = re.compile(r"\[\[\s*([A-Za-z_][A-Za-z0-9_]*)\s*\]\]")


def deep_merge(base, override):
    """Recursively merge ``override`` into ``base`` without mutating either.

    - dict + dict → keys merged recursively
    - list + list → merged index-wise (extra override items appended), so a
      template's ``_items`` list can be patched one entry at a time
    - anything else → the override value wins
    - ``override`` of ``None`` → ``base`` returned unchanged
    """
    if override is None:
        return base
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(base.get(key), value) if key in base else value
        return merged
    if isinstance(base, list) and isinstance(override, list):
        merged = [deep_merge(b, o) for b, o in zip(base, override)]  # index-wise patch
        merged.extend(override[len(base) :])
        merged.extend(base[len(override) :])
        return merged
    return override


def find_placeholders(value) -> list:
    """Return the distinct ``[[placeholder]]`` names found anywhere in ``value``."""
    found: list = []

    def _walk(node):
        if isinstance(node, str):
            for match in PLACEHOLDER_PATTERN.finditer(node):
                name = match.group(1)
                if name not in found:
                    found.append(name)
        elif isinstance(node, dict):
            for item in node.values():
                _walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)

    _walk(value)
    return found


def fill_placeholders(value, values=None):
    """Substitute ``[[name]]`` markers in ``value`` (str/dict/list, recursively).

    Unknown names are left untouched so the caller can report them via
    :func:`find_placeholders`. Non-string replacement values are stringified.
    """
    if not values:
        return value
    if isinstance(value, str):

        def _sub(match):
            name = match.group(1)
            if name in values and values[name] is not None:
                return str(values[name])
            return match.group(0)

        return PLACEHOLDER_PATTERN.sub(_sub, value)
    if isinstance(value, dict):
        return {k: fill_placeholders(v, values) for k, v in value.items()}
    if isinstance(value, list):
        return [fill_placeholders(v, values) for v in value]
    return value
