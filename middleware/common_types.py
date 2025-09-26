"""
Common type definitions for middleware-injected fields.

This module provides base types and utilities for consistently adding
middleware-injected fields across all tool response types without
requiring manual TypedDict modifications.
"""

from typing_extensions import TypedDict, NotRequired, Optional


class TemplateError(Exception):
    """Exception raised when template processing fails in strict mode."""
    
    def __init__(self, message: str, template_name: Optional[str] = None, field_name: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.template_name = template_name
        self.field_name = field_name
        self.original_error = original_error
        
    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.template_name:
            parts.append(f"Template: {self.template_name}")
        if self.field_name:
            parts.append(f"Field: {self.field_name}")
        return " | ".join(parts)


class TemplateMiddlewareFields(TypedDict):
    """Fields that template middleware injects into all tool responses."""
    jinjaTemplateApplied: NotRequired[bool]
    jinjaTemplateError: NotRequired[Optional[str]]


class MiddlewareFields(TemplateMiddlewareFields):
    """Combined fields that all middleware can inject into tool responses."""
    # Future middleware can add their fields here
    pass


def add_middleware_fields_to_response(response_dict: dict,
                                    jinja_template_applied: bool = False,
                                    jinja_template_error: Optional[str] = None) -> dict:
    """
    Add middleware fields to any response dictionary.
    
    This function can be used to add middleware fields to any tool response
    without requiring TypedDict modifications.
    
    Args:
        response_dict: The original response dictionary
        jinja_template_applied: Whether Jinja2 templates were applied
        jinja_template_error: Any Jinja2 template error that occurred
        
    Returns:
        Response dictionary with middleware fields added
        
    Raises:
        TemplateError: If strict mode is enabled and template processing failed
    """
    from config.settings import settings
    
    # Check if strict mode is enabled and we have a template error
    if settings.jinja_template_strict_mode and jinja_template_error:
        raise TemplateError(
            message=f"Template processing failed in strict mode: {jinja_template_error}",
            template_name=None,
            field_name=None,
            original_error=None
        )
    
    enhanced_response = response_dict.copy()
    
    # Add template middleware fields
    enhanced_response["jinjaTemplateApplied"] = jinja_template_applied
    enhanced_response["jinjaTemplateError"] = jinja_template_error
    
    return enhanced_response