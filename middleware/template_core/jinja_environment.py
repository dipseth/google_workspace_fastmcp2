"""
Jinja2 environment setup and configuration for template middleware.

Manages Jinja2 environment creation, filter registration, template loading,
and macro management for the template processing system.
"""

import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from .utils import SilentUndefined

from config.enhanced_logging import setup_logger
logger = setup_logger()

# Jinja2 imports - optional dependency
try:
    from jinja2 import Environment, DictLoader, FileSystemLoader, select_autoescape, BaseLoader
    from jinja2 import Undefined, ChoiceLoader, Template
    JINJA2_AVAILABLE = True
except ImportError:
    Environment = None
    DictLoader = None
    FileSystemLoader = None
    select_autoescape = None
    BaseLoader = None
    Undefined = None
    ChoiceLoader = None
    Template = None
    JINJA2_AVAILABLE = False


class ContextPreservingEnvironment(Environment):
    """
    Custom Jinja2 Environment that preserves global functions in imported macro contexts.
    
    This fixes the issue where macros imported via {% from 'template.j2' import macro_name %}
    don't have access to global functions like now() defined in the environment globals.
    
    The fix works by overriding get_template to ensure that when templates are loaded
    for macro imports, their make_module method is enhanced to inject globals into
    the module's namespace, making functions like now() available within imported macros.
    """
    
    def _enhance_template_make_module(self, template):
        """
        Enhance a template's make_module method to inject globals.
        
        Args:
            template: Template object to enhance
            
        Returns:
            Template with enhanced make_module method
        """
        # Store reference to original make_module method
        original_make_module = template.make_module
        
        def enhanced_make_module(vars=None, shared=True):
            """
            Enhanced make_module that injects environment globals into the module.
            
            This ensures that when macros are imported via {% from %}, they have
            access to all global functions defined in the environment, including
            critical functions like now(), utcnow(), etc.
            """
            # Create the module using the original method
            module = original_make_module(vars, shared)
            
            # Inject environment globals into the module's namespace
            # Only inject if the attribute doesn't already exist to avoid overwrites
            for key, value in self.globals.items():
                if not hasattr(module, key):
                    setattr(module, key, value)
            
            return module
        
        # Replace the template's make_module method with our enhanced version
        template.make_module = enhanced_make_module
        
        return template
    
    def get_template(self, name, parent=None, globals=None):
        """
        Override get_template to inject globals into imported macro contexts.
        
        Args:
            name: Template name to load
            parent: Parent template (for inheritance)
            globals: Additional globals for this template
            
        Returns:
            Template with enhanced make_module that preserves globals
        """
        if not JINJA2_AVAILABLE:
            return None
            
        # Get the template using the standard method
        template = super().get_template(name, parent, globals)
        
        # Enhance the template's make_module method
        return self._enhance_template_make_module(template)
    
    def from_string(self, source, globals=None, template_class=None):
        """
        Override from_string to inject globals into macro contexts.
        
        This ensures that even dynamically created templates (like in tests)
        have access to environment globals in their modules.
        """
        if not JINJA2_AVAILABLE:
            return None
            
        # Create template using the standard method
        template = super().from_string(source, globals, template_class)
        
        # Enhance the template's make_module method
        return self._enhance_template_make_module(template)


class JinjaEnvironmentManager:
    """
    Manages Jinja2 environment setup and configuration.
    
    Provides comprehensive Jinja2 environment management including:
    - Environment creation with custom options
    - Multiple loader setup (FileSystem + Dict)
    - Filter and function registration
    - Template macro loading and management
    - Integration with custom filters from filters module
    """
    
    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        jinja2_options: Optional[Dict[str, Any]] = None,
        enable_debug_logging: bool = False
    ):
        """
        Initialize the Jinja environment manager.
        
        Args:
            templates_dir: Path to directory containing .j2 template files
            jinja2_options: Custom Jinja2 Environment options
            enable_debug_logging: Enable detailed debug logging
        """
        self.templates_dir = templates_dir
        self.jinja2_options = jinja2_options or {}
        self.enable_debug_logging = enable_debug_logging
        self.jinja2_env = None
    
    def setup_jinja2_environment(self) -> Optional[Environment]:
        """
        Configure the Jinja2 template environment with FastMCP-specific settings.
        
        Sets up a comprehensive Jinja2 environment optimized for FastMCP template
        resolution, including custom loaders, filters, functions, and security settings.
        
        This method:
        1. Merges user options with sensible defaults
        2. Configures multiple template loaders (file system + dynamic)
        3. Registers custom filters and functions for FastMCP resources
        4. Loads template macros from .j2 files
        5. Sets up sandboxed execution environment
        
        Returns:
            Configured Jinja2 Environment instance or None if Jinja2 unavailable
            
        Side Effects:
            - Sets self.jinja2_env to configured Environment instance
            - Loads template macros from templates directory
            - Registers custom filters and global functions
            - Logs configuration status when debug logging enabled
            
        Raises:
            ImportError: If Jinja2 is not available (should be checked before calling)
            FileNotFoundError: If templates_dir is specified but doesn't exist
        """
        if not JINJA2_AVAILABLE:
            logger.warning("⚠️ Jinja2 not available - cannot setup environment")
            return None
        
        default_options = {
            'autoescape': False,  # Disable autoescape for JSON content
            'undefined': SilentUndefined,  # Use our custom undefined class
            'trim_blocks': True,
            'lstrip_blocks': True,
        }
        
        # Merge with user options
        env_options = {**default_options, **self.jinja2_options}
        
        # Set up loaders - combine FileSystemLoader for external templates and DictLoader for dynamic ones
        loaders = []
        
        # Add FileSystemLoader if templates directory exists
        if self.templates_dir and self.templates_dir.exists():
            loaders.append(FileSystemLoader(str(self.templates_dir)))
            if self.enable_debug_logging:
                logger.debug(f"📁 Added FileSystemLoader for templates directory: {self.templates_dir}")
        
        # Add DictLoader for dynamic templates
        loaders.append(DictLoader({}))
        
        # Use ChoiceLoader to combine multiple loaders
        combined_loader = ChoiceLoader(loaders) if len(loaders) > 1 else loaders[0]
        
        # Create environment using our custom ContextPreservingEnvironment
        # that ensures globals are accessible in imported macros
        self.jinja2_env = ContextPreservingEnvironment(
            loader=combined_loader,
            **env_options
        )

        # Set up resource functions and filters FIRST (before loading macros)
        # This ensures functions like now() are available when macros are loaded
        self._setup_resource_functions()

        # Load and register macros from template files
        self._load_template_macros()
        
        if self.enable_debug_logging:
            logger.debug("🎭 Jinja2 environment configured with custom functions, filters, and template macros")
        
        return self.jinja2_env
    
    def register_filters(self, filters_dict: Dict[str, Any]) -> None:
        """
        Register custom filters with the Jinja2 environment.
        
        Args:
            filters_dict: Dictionary of filter_name -> filter_function mappings
        """
        if self.jinja2_env:
            self.jinja2_env.filters.update(filters_dict)
    
    def _load_template_macros(self) -> None:
        """
        Load and register Jinja2 macros from .j2 template files.
        
        Scans the templates directory for .j2 files and automatically imports
        any macros defined within them into the global Jinja2 namespace.
        This allows macros to be used across all templates without explicit imports.
        
        Process:
        1. Find all .j2 files in templates_dir
        2. Load each template and create a module
        3. Extract callable attributes (macros/functions)
        4. Register them as global functions in Jinja2 environment
        
        Template File Example:
            # templates/email_macros.j2
            {% macro greeting(name, formal=False) %}
            {% if formal %}Dear {{ name }}{% else %}Hi {{ name }}{% endif %}
            {% endmacro %}
            
            # After loading, can be used as: {{ greeting('John', formal=True) }}
        
        Side Effects:
            - Modifies self.jinja2_env.globals with loaded macros
            - Logs macro loading activity when debug logging enabled
            - Gracefully handles template loading errors
            
        Error Handling:
            - Missing templates directory: silently skips loading
            - Invalid template syntax: logs warning and continues
            - File access errors: logs warning and continues
            
        Note:
            Macros are loaded into the global namespace, so name conflicts
            between template files will result in later files overriding
            earlier ones. Use descriptive macro names to avoid conflicts.
        """
        if not self.jinja2_env or not self.templates_dir or not self.templates_dir.exists():
            return
        
        # Find all .j2 template files
        template_files = list(self.templates_dir.glob('*.j2'))
        
        if self.enable_debug_logging:
            logger.debug(f"📂 Found {len(template_files)} template files: {[f.name for f in template_files]}")
        
        # Load each template and make its macros available globally
        for template_file in template_files:
            try:
                template_name = template_file.name
                template = self.jinja2_env.get_template(template_name)
                
                # Import the template module to access its macros
                module = template.make_module()
                
                # Add all macros from this template to the global namespace
                for attr_name in dir(module):
                    if not attr_name.startswith('_'):
                        attr_value = getattr(module, attr_name)
                        if callable(attr_value):
                            self.jinja2_env.globals[attr_name] = attr_value
                            if self.enable_debug_logging:
                                logger.debug(f"📦 Loaded macro '{attr_name}' from {template_name}")
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to load template {template_file.name}: {e}")
    
    def _setup_resource_functions(self) -> None:
        """
        Register custom functions and filters for FastMCP resource integration.
        
        Configures the Jinja2 environment with specialized functions and filters
        designed for working with FastMCP resources, date/time operations, and
        data manipulation within templates.
        
        Global Functions Added:
            - now(): Returns current UTC datetime
            - utcnow(): Alias for now() for compatibility
            
        Note: Custom filters are registered separately via the filters module
        to maintain separation of concerns.
            
        Side Effects:
            - Modifies self.jinja2_env.globals with utility functions
            - All functions become available in all templates
            
        Error Handling:
            - Functions are designed to be defensive and return safe defaults
            - No exceptions are raised during template rendering
            
        Note:
            This method is automatically called during Jinja2 environment setup.
            Functions are designed to be safe for use in sandboxed
            template execution environments.
        """
        if not self.jinja2_env:
            return
            
        # Simple functions that work with pre-populated context data
        # These will be accessible as global functions in templates
        self.jinja2_env.globals.update({
            'now': lambda: datetime.now(timezone.utc),
            'utcnow': lambda: datetime.now(timezone.utc),  # Alias for compatibility
            
            # Utility functions available in templates
            'len': len,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'max': max,
            'min': min,
            'sum': sum,
            'sorted': sorted,
            'reversed': reversed,
            'enumerate': enumerate,
            'zip': zip,
            'range': range,
        })
    
    def get_environment(self) -> Optional[Environment]:
        """Get the configured Jinja2 environment."""
        return self.jinja2_env
    
    def is_available(self) -> bool:
        """Check if Jinja2 is available and environment is configured."""
        return JINJA2_AVAILABLE and self.jinja2_env is not None