"""
Utility classes and exceptions for template processing.

This module provides common utility classes and exception types used throughout
the template middleware system.
"""

from typing import Optional

# Jinja2 imports - optional dependency
try:
    from jinja2 import Undefined

    JINJA2_AVAILABLE = True
except ImportError:
    Undefined = None
    JINJA2_AVAILABLE = False


class TemplateResolutionError(Exception):
    """
    Exception raised when template parameter resolution fails.

    This exception is raised when:
    - Resource URI cannot be fetched from FastMCP context
    - Template syntax is invalid (for Jinja2 templates)
    - Property extraction fails due to invalid paths
    - Authentication issues prevent resource access

    Attributes:
        message: Human-readable error description
        resource_uri: The resource URI that failed (if applicable)
        template_text: The template text that caused the error (if applicable)

    Example:
        ```python
        try:
            resolved = await middleware._resolve_template(template_text, context)
        except TemplateResolutionError as e:
            logger.error(f"Template resolution failed: {e}")
            # Handle gracefully or fall back to original value
        ```
    """

    def __init__(
        self,
        message: str,
        resource_uri: Optional[str] = None,
        template_text: Optional[str] = None,
    ):
        super().__init__(message)
        self.resource_uri = resource_uri
        self.template_text = template_text


class SilentUndefined(Undefined if JINJA2_AVAILABLE else object):
    """
    Custom Jinja2 Undefined class for graceful template variable handling.

    Instead of raising UndefinedError exceptions when variables are missing,
    this class returns empty strings, making templates more forgiving and
    preventing template rendering failures due to missing context variables.

    This is particularly useful for:
    - Optional template variables that may not always be available
    - Resource resolution that might fail for some URIs
    - Progressive template enhancement where not all context is guaranteed

    Behavior:
    - Missing variables resolve to empty string ('')
    - Boolean evaluation returns False
    - String conversion returns empty string
    - Attribute access on undefined returns new SilentUndefined instance

    Example:
        ```jinja2
        {# These won't raise errors even if variables are missing #}
        Hello {{ user.name }}!  {# Returns 'Hello !' if user.name undefined #}
        {% if user.authenticated %}Welcome!{% endif %}  {# Safe boolean check #}
        ```
    """

    def _fail_with_undefined_error(self, *args, **kwargs) -> str:
        """Override to return empty string instead of raising UndefinedError."""
        return ""

    def __str__(self) -> str:
        """String representation of undefined variable."""
        return ""

    def __bool__(self) -> bool:
        """Boolean evaluation of undefined variable."""
        return False

    def __getattr__(self, name: str) -> "SilentUndefined":
        """Return another SilentUndefined for chained attribute access."""
        return SilentUndefined()


# Fallback SilentUndefined for when Jinja2 is not available
if not JINJA2_AVAILABLE:

    class SilentUndefined:
        """Fallback SilentUndefined when Jinja2 is not available."""

        def __str__(self) -> str:
            return ""

        def __bool__(self) -> bool:
            return False

        def __getattr__(self, name: str) -> "SilentUndefined":
            return SilentUndefined()
