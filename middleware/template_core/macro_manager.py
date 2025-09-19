"""
Template macro discovery and management for Jinja2 templates.

Handles scanning template files for macro definitions, registering them,
and providing macro information through resource URIs.
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from .jinja_environment import JinjaEnvironmentManager

from config.enhanced_logging import setup_logger
logger = setup_logger()


class MacroManager:
    """
    Manages template macro discovery and resource handling.
    
    Provides functionality to:
    - Scan template files for macro definitions
    - Register macros with usage examples
    - Handle template://macros resource URIs
    - Provide macro information and usage examples
    """
    
    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        jinja_env_manager: Optional[JinjaEnvironmentManager] = None,
        enable_debug_logging: bool = False
    ):
        """
        Initialize the macro manager.
        
        Args:
            templates_dir: Path to directory containing .j2 template files
            jinja_env_manager: JinjaEnvironmentManager for template access
            enable_debug_logging: Enable detailed debug logging
        """
        self.templates_dir = templates_dir
        self.jinja_env_manager = jinja_env_manager
        self.enable_debug_logging = enable_debug_logging
        
        # Initialize macro registry for template://macros resources
        self._macro_registry: Dict[str, Dict[str, Any]] = {}
    
    def scan_and_register_macros(self) -> None:
        """
        Scan template files for macro definitions and register them for template://macros resources.
        
        This method:
        1. Scans all .j2 files in templates_dir
        2. Extracts macro definitions using regex
        3. Looks for usage examples in comments
        4. Stores macro information in _macro_registry
        
        Side Effects:
            - Populates self._macro_registry with discovered macros
            - Logs macro discovery progress when debug logging enabled
            
        Error Handling:
            - Individual template scanning failures don't stop the process
            - Invalid template files are logged and skipped
            - Missing templates directory is handled gracefully
        """
        if not self.jinja_env_manager or not self.jinja_env_manager.get_environment():
            return
            
        if not self.templates_dir or not self.templates_dir.exists():
            return
        
        # Find all .j2 template files
        template_files = list(self.templates_dir.glob('*.j2'))
        
        if self.enable_debug_logging:
            logger.debug(f"🔍 Scanning {len(template_files)} template files for macros")
        
        # Regex patterns for macro detection
        # macro_pattern = re.compile(r'{% macro (\w+)\([^%]*%}', re.MULTILINE)
        macro_pattern = re.compile(r'{% macro (\w+)\s*\([^}]*?\) %?}', re.MULTILINE | re.DOTALL)

        usage_example_pattern = re.compile(r'{#[^#]*MACRO USAGE EXAMPLE:[^#]*{{ (\w+)\([^}]*\) }}[^#]*#}', re.DOTALL)
        
        for template_file in template_files:
            try:
                template_content = template_file.read_text(encoding='utf-8')
                template_name = template_file.name
                
                # Find macro definitions
                macro_matches = macro_pattern.findall(template_content)
                
                # Find usage examples
                usage_matches = usage_example_pattern.findall(template_content)
                usage_examples = {}
                
                # Extract full usage examples from comments
                for usage_match in usage_matches:
                    # Find the full usage example line
                    usage_start = template_content.find(f'{{ {usage_match}(')
                    if usage_start != -1:
                        usage_end = template_content.find(' }}', usage_start)
                        if usage_end != -1:
                            full_usage = template_content[usage_start:usage_end + 3]
                            usage_examples[usage_match] = full_usage.strip()
                
                # Register each macro found
                for macro_name in macro_matches:
                    self._macro_registry[macro_name] = {
                        "name": macro_name,
                        "template_file": template_name,
                        "template_path": str(template_file.relative_to(self.templates_dir.parent)),
                        "usage_example": usage_examples.get(macro_name, f"{{{{ {macro_name}() }}}}"),
                        "description": f"Macro from {template_name}",
                        "discovered_at": datetime.now().isoformat()
                    }
                    
                    if self.enable_debug_logging:
                        logger.debug(f"📝 Registered macro '{macro_name}' from {template_name}")
                        if macro_name in usage_examples:
                            logger.debug(f"   Usage: {usage_examples[macro_name]}")
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to scan template {template_file.name} for macros: {e}")
        
        logger.info(f"📚 Discovered {len(self._macro_registry)} macros from {len(template_files)} template files")
    
    async def handle_template_resource(self, resource_uri: str, fastmcp_context) -> bool:
        """
        Handle template:// resource URIs for macro information.
        
        Args:
            resource_uri: The template:// URI to handle
            fastmcp_context: FastMCP context for setting resource state
            
        Returns:
            True if the URI was handled, False if not a template:// URI
            
        Supports:
            - template://macros - List all available macros with usage examples
            - template://macros/{macro_name} - Get specific macro usage example
        """
        if not resource_uri.startswith('template://'):
            return False
        
        if self.enable_debug_logging:
            logger.debug(f"🎯 Handling template resource URI: {resource_uri}")
        
        try:
            if resource_uri == 'template://macros':
                # Return all available macros
                await self._handle_all_macros(fastmcp_context)
                return True
            elif resource_uri.startswith('template://macros/'):
                # Return specific macro usage example
                macro_name = resource_uri.replace('template://macros/', '')
                await self._handle_specific_macro(macro_name, fastmcp_context)
                return True
            else:
                # Unknown template pattern
                error_data = {
                    "error": f"Unknown template resource pattern: {resource_uri}",
                    "supported_patterns": [
                        "template://macros - List all available macros",
                        "template://macros/{macro_name} - Get specific macro usage"
                    ]
                }
                fastmcp_context.set_state(f"template_resource_{resource_uri}", error_data)
                return True
                
        except Exception as e:
            logger.error(f"❌ Error handling template resource {resource_uri}: {e}")
            error_data = {"error": str(e), "timestamp": datetime.now().isoformat()}
            fastmcp_context.set_state(f"template_resource_{resource_uri}", error_data)
            return True
    
    async def _handle_all_macros(self, fastmcp_context) -> None:
        """
        Handle template://macros - return all available macros with usage examples.
        
        Args:
            fastmcp_context: FastMCP context for setting resource state
        """
        if not self._macro_registry:
            self.scan_and_register_macros()
        
        response_data = {
            "macros": self._macro_registry,
            "total_count": len(self._macro_registry),
            "templates_dir": str(self.templates_dir) if self.templates_dir else None,
            "generated_at": datetime.now().isoformat()
        }
        
        # Store in context state for resource handler
        fastmcp_context.set_state("template_resource_template://macros", response_data)
        logger.info(f"📚 Stored all macros data: {len(self._macro_registry)} macros")
    
    async def _handle_specific_macro(self, macro_name: str, fastmcp_context) -> None:
        """
        Handle template://macros/{macro_name} - return specific macro usage example.
        
        Args:
            macro_name: Name of the macro to retrieve
            fastmcp_context: FastMCP context for setting resource state
        """
        if not self._macro_registry:
            self.scan_and_register_macros()
        
        if macro_name in self._macro_registry:
            macro_info = self._macro_registry[macro_name]
            response_data = {
                "macro": macro_info,
                "usage_example": macro_info["usage_example"],
                "found": True
            }
        else:
            response_data = {
                "error": f"Macro '{macro_name}' not found",
                "available_macros": list(self._macro_registry.keys()),
                "found": False
            }
        
        # Store in context state for resource handler
        cache_key = f"template_resource_template://macros/{macro_name}"
        fastmcp_context.set_state(cache_key, response_data)
        logger.info(f"📝 Stored macro data for '{macro_name}': found={response_data.get('found', False)}")
    
    def get_macro_registry(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the current macro registry.
        
        Returns:
            Dictionary of macro_name -> macro_info mappings
        """
        return self._macro_registry.copy()
    
    def get_macro_count(self) -> int:
        """
        Get the number of registered macros.
        
        Returns:
            Number of macros in the registry
        """
        return len(self._macro_registry)
    
    def clear_registry(self) -> None:
        """
        Clear the macro registry.
        
        Side Effects:
            - Empties self._macro_registry
            - Forces re-scanning on next macro operation
        """
        self._macro_registry.clear()
        if self.enable_debug_logging:
            logger.debug("🧹 Macro registry cleared")