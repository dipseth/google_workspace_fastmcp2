"""
Template Resources for FastMCP2 - Macro Discovery and Usage Examples

This module provides resources for discovering available Jinja2 macros in the
middleware/templates directory and retrieving their usage examples.

## Architecture

Similar to service_list_resources.py, this uses a middleware-based approach:
1. Resources are registered here for discoverability
2. EnhancedTemplateMiddleware intercepts template:// URIs 
3. Middleware scans templates and caches macro information
4. These handlers retrieve cached results from middleware

## Resource Hierarchy

1. template://macros - Returns all available macros with usage examples
2. template://macros/{macro_name} - Returns specific macro usage example

## Integration with EnhancedTemplateMiddleware

The middleware handles all the complex logic:
- Template file scanning for macro definitions
- Usage example extraction from comments
- Macro registry management
- Caching for performance

Examples:
- template://macros → List all macros with usage examples
- template://macros/render_gmail_labels_chips → Specific macro usage
"""

import logging
from typing import Dict, Any, Optional
from fastmcp import FastMCP, Context
from pydantic import Field, BaseModel
from typing_extensions import Annotated
from datetime import datetime

logger = logging.getLogger(__name__)


class MacroInfo(BaseModel):
    """Information about a specific macro."""
    name: str = Field(description="Name of the macro")
    template_file: str = Field(description="Template file containing the macro")
    template_path: str = Field(description="Full path to template file")
    usage_example: str = Field(description="Example of how to call the macro")
    description: str = Field(description="Description of the macro")
    discovered_at: str = Field(description="ISO timestamp when macro was discovered")


class AllMacrosResponse(BaseModel):
    """Response containing all available macros."""
    macros: Dict[str, MacroInfo] = Field(description="Dictionary of macro name to macro info")
    total_count: int = Field(description="Total number of macros found")
    templates_dir: str = Field(description="Path to templates directory")
    generated_at: str = Field(description="ISO timestamp when response was generated")
    
    @classmethod
    def from_middleware_data(cls, middleware_data: Dict[str, Any]) -> 'AllMacrosResponse':
        """Create response from middleware-processed data."""
        # Convert macro registry dict to MacroInfo objects
        macros_dict = {}
        for macro_name, macro_data in middleware_data.get("macros", {}).items():
            macros_dict[macro_name] = MacroInfo(**macro_data)
        
        return cls(
            macros=macros_dict,
            total_count=middleware_data.get("total_count", 0),
            templates_dir=middleware_data.get("templates_dir", ""),
            generated_at=middleware_data.get("generated_at", datetime.now().isoformat())
        )


class SpecificMacroResponse(BaseModel):
    """Response for a specific macro request."""
    macro: Optional[MacroInfo] = Field(description="Macro information if found")
    usage_example: str = Field(description="Example of how to call the macro")
    found: bool = Field(description="Whether the macro was found")
    error: Optional[str] = Field(description="Error message if macro not found")
    available_macros: Optional[list] = Field(description="List of available macro names if not found")
    
    @classmethod
    def from_middleware_data(cls, middleware_data: Dict[str, Any]) -> 'SpecificMacroResponse':
        """Create response from middleware-processed data."""
        if middleware_data.get("found", False):
            macro_data = middleware_data.get("macro", {})
            return cls(
                macro=MacroInfo(**macro_data) if macro_data else None,
                usage_example=middleware_data.get("usage_example", ""),
                found=True,
                error=None,
                available_macros=None
            )
        else:
            return cls(
                macro=None,
                usage_example="",
                found=False,
                error=middleware_data.get("error", "Macro not found"),
                available_macros=middleware_data.get("available_macros", [])
            )


def register_template_resources(mcp: FastMCP) -> None:
    """
    Register template macro resources that will be handled by EnhancedTemplateMiddleware.

    Args:
        mcp: FastMCP instance to register resources with
    """
    logger.info("Registering template macro resources (handled by EnhancedTemplateMiddleware)...")

    @mcp.resource(
        uri="template://macros",
        name="Available Template Macros",
        description="""Get all available Jinja2 macros with usage examples.

The EnhancedTemplateMiddleware scans middleware/templates/*.j2 files and extracts:
- Macro definitions using {% macro name(...) %}
- Usage examples from {# MACRO USAGE EXAMPLE: ... #} comments
- Template file paths and descriptions

Returns comprehensive macro information including:
- Macro names and parameters
- Template file locations
- Ready-to-use usage examples
- Discovery timestamps

This enables easy discovery and correct usage of available template macros.

Example response:
{
  "macros": {
    "render_gmail_labels_chips": {
      "name": "render_gmail_labels_chips",
      "template_file": "email_card.j2",
      "usage_example": "{{ render_gmail_labels_chips(service://gmail/labels, 'Label summary') }}"
    }
  },
  "total_count": 5
}

This resource is handled by EnhancedTemplateMiddleware.""",
        mime_type="application/json",
        tags={"template", "macros", "discovery", "jinja2"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True
        },
        meta={
            "version": "1.0",
            "category": "template-discovery",
            "middleware_handler": "EnhancedTemplateMiddleware"
        }
    )
    async def handle_all_macros(ctx: Context) -> AllMacrosResponse:
        """
        Handler for template://macros that retrieves cached results from middleware.

        Returns:
            AllMacrosResponse containing all discovered macros with usage examples
        """
        # Try to get the cached result from FastMCP context state
        cache_key = "template_resource_template://macros"
        cached_result = ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't cache result
            logger.warning("No cached template macros found - middleware may not have processed this request")
            return AllMacrosResponse(
                macros={},
                total_count=0,
                templates_dir="unknown",
                generated_at=datetime.now().isoformat()
            )

        # Return the cached result as structured response
        logger.info(f"📚 Retrieved cached macros data from context state")
        return AllMacrosResponse.from_middleware_data(cached_result)

    @mcp.resource(
        uri="template://macros/{macro_name}",
        name="Specific Template Macro",
        description="""Get usage example for a specific template macro.

The EnhancedTemplateMiddleware extracts macro information from template files
and provides ready-to-use examples showing the correct syntax and parameters.

Returns macro information including:
- Complete usage example with proper syntax
- Template file location
- Parameter information
- Error details if macro not found

Example for render_gmail_labels_chips:
{
  "macro": {
    "name": "render_gmail_labels_chips",
    "template_file": "email_card.j2",
    "usage_example": "{{ render_gmail_labels_chips(service://gmail/labels, 'Label summary') }}"
  },
  "found": true
}

This resource is handled by EnhancedTemplateMiddleware.""",
        mime_type="application/json",
        tags={"template", "macros", "usage", "jinja2"},
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True
        },
        meta={
            "version": "1.0",
            "category": "template-usage",
            "middleware_handler": "EnhancedTemplateMiddleware"
        }
    )
    async def handle_specific_macro(
        macro_name: Annotated[str, Field(
            description="Name of the macro to get usage example for",
            examples=["render_gmail_labels_chips", "render_calendar_dashboard", "render_beautiful_email"]
        )],
        ctx: Context
    ) -> SpecificMacroResponse:
        """
        Handler for template://macros/{macro_name} that retrieves cached results from middleware.

        Returns:
            SpecificMacroResponse containing the macro usage example or error information
        """
        # Try to get the cached result from FastMCP context state
        cache_key = f"template_resource_template://macros/{macro_name}"
        cached_result = ctx.get_state(cache_key)

        if cached_result is None:
            # Fallback - middleware didn't cache result
            logger.warning(f"No cached template macro found for '{macro_name}' - middleware may not have processed this request")
            return SpecificMacroResponse(
                macro=None,
                usage_example="",
                found=False,
                error=f"Macro '{macro_name}' not found - no cached data available",
                available_macros=[]
            )

        # Return the cached result as structured response
        logger.info(f"📝 Retrieved cached macro data for '{macro_name}' from context state")
        return SpecificMacroResponse.from_middleware_data(cached_result)

    logger.info("✅ Registered 2 template macro resources (all handled by EnhancedTemplateMiddleware)")
    logger.info("   1. template://macros - Get all available macros with usage examples")
    logger.info("   2. template://macros/{macro_name} - Get specific macro usage example")
    logger.info("")
    logger.info("📌 EnhancedTemplateMiddleware handles the complex logic:")
    logger.info("   • Template file scanning for macro definitions")
    logger.info("   • Usage example extraction from comments")
    logger.info("   • Macro registry management and caching")
    logger.info("   • Automatic resource creation for discovered macros")