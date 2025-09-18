"""
Core template processing components for FastMCP template middleware.

This module provides the core infrastructure components for template processing,
resource handling, caching, and Jinja2 environment management.

Components:
- utils: Exception classes and utility functions
- cache_manager: TTL-based resource caching
- resource_handler: Resource fetching and processing
- jinja_environment: Jinja2 environment setup and configuration  
- template_processor: Template detection and processing logic
- macro_manager: Template macro discovery and management

Usage:
    from middleware.template_core import (
        TemplateResolutionError,
        SilentUndefined,
        CacheManager,
        ResourceHandler,
        JinjaEnvironmentManager,
        TemplateProcessor,
        MacroManager
    )
"""

# Import all main classes for easy access
from .utils import TemplateResolutionError, SilentUndefined
from .cache_manager import CacheManager
from .resource_handler import ResourceHandler
from .jinja_environment import JinjaEnvironmentManager
from .template_processor import TemplateProcessor
from .macro_manager import MacroManager

__all__ = [
    'TemplateResolutionError',
    'SilentUndefined',
    'CacheManager',
    'ResourceHandler',
    'JinjaEnvironmentManager',
    'TemplateProcessor',
    'MacroManager'
]