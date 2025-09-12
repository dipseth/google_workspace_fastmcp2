"""
Namespace Converter Utility
Provides dot notation support for dictionary objects in Jinja2 templates.
"""

import types
from typing import Any


def convert_to_namespace(data: Any) -> Any:
    """
    Recursively convert dictionaries to SimpleNamespace for dot notation support.

    This function enables natural dot notation access to dictionary properties
    in Jinja2 templates, making templates more readable and intuitive.

    Args:
        data: The data structure to convert (dict, list, or primitive)

    Returns:
        Converted data with SimpleNamespace objects for dictionaries

    Examples:
        >>> data = {'user': {'name': 'John', 'email': 'john@example.com'}}
        >>> ns = convert_to_namespace(data)
        >>> ns.user.name  # 'John'
        >>> ns.user.email  # 'john@example.com'
    """
    if isinstance(data, dict):
        converted = {}
        for key, value in data.items():
            converted[key] = convert_to_namespace(value)
        return types.SimpleNamespace(**converted)
    elif isinstance(data, list):
        return [convert_to_namespace(item) for item in data]
    else:
        return data


class NamespaceConverter:
    """
    Class-based namespace converter for use in middleware contexts.

    Provides the same functionality as the module-level function but as a class method
    for integration with existing middleware patterns.
    """

    @staticmethod
    def convert(data: Any) -> Any:
        """Convert data to namespace format (static method)."""
        return convert_to_namespace(data)

    def __call__(self, data: Any) -> Any:
        """Convert data to namespace format (callable instance)."""
        return convert_to_namespace(data)