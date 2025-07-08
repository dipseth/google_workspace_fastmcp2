"""
Content Mapping Package for Google Chat Card Creation

This package provides enhanced content mapping and parameter inference capabilities
for the Google Chat card creation system, making it easier for LLMs to map content
to card formatting.

Components:
- ContentMappingEngine: Parses natural language content descriptions and maps them to card structures
- ParameterInferenceEngine: Infers parameter names and widget types from natural language
- TemplateManager: Manages card templates for reuse and customization
"""

from .content_mapping_engine import ContentMappingEngine
from .parameter_inference_engine import ParameterInferenceEngine
from .template_manager import TemplateManager
from .models import ContentFormat, ContentElement, Template