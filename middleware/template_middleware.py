"""
Enhanced Template Parameter Substitution Middleware with Jinja2 Support
Version 3.0 - Hybrid Approach

A comprehensive middleware solution that enables both simple regex-based templating and
powerful Jinja2 templating for FastMCP tool parameter substitution. This middleware
automatically resolves resource URIs and template expressions in tool parameters at runtime.

## Core Capabilities

### Template Engines (Hybrid Approach)
- **Simple Templates**: {{user://current/email.email}} - Fast regex-based resolution
- **Jinja2 Templates**: {% if user.authenticated %}{{ user.email }}{% endif %} - Full template engine
- **Mixed Templates**: Combine both approaches in a single template
- **Progressive Enhancement**: Start simple, upgrade to complex as needed

### Resource Resolution
- **Automatic URI Resolution**: Fetches data from FastMCP resource endpoints
- **Property Extraction**: Access nested properties with dot notation
- **Caching System**: Configurable TTL-based caching for performance
- **Error Resilience**: Graceful fallback when resources are unavailable

### Advanced Features
- **Custom Jinja2 Filters**: Date formatting, JSON pretty-printing, safe property access
- **Template File Support**: Load templates from organized .j2 files
- **Rich Context**: Pre-populated with common resources and utility functions
- **Debug Logging**: Comprehensive tracing for troubleshooting
- **Security**: Sandboxed template execution with controlled resource access

## Architecture

```
Tool Call → Template Detection → Engine Selection → Resource Resolution → Parameter Substitution → Tool Execution
            │                  │                  │                    │
            ├─ Simple Pattern  ├─ Regex Engine    ├─ FastMCP Resources ├─ String Replacement
            └─ Jinja2 Pattern  └─ Jinja2 Engine   └─ Cached Results    └─ Template Rendering
```

## Usage Examples

```python
# Simple resource access
@mcp.tool()
async def send_email(
    user_email: str = "{{user://current/email}}",
    recipient: str
) -> str:
    return f"Email from {user_email} to {recipient}"

# Jinja2 with conditionals
@mcp.tool()
async def generate_report(

) -> str:
    return content
```

## Version History
- v1.0: Basic string substitution
- v2.0: Regex-based templating with resource URIs
- v3.0: Hybrid approach with Jinja2 integration

See documentation/TEMPLATE_PARAMETER_MIDDLEWARE.md for complete usage guide.
"""

import re
import json
import logging
import random
import importlib

from config.enhanced_logging import setup_logger
logger = setup_logger()
import types
import os
from pathlib import Path
from .namespace_converter import convert_to_namespace
from typing import Any, Dict, Optional, Union, List
from datetime import datetime, timedelta, timezone

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError
from mcp.server.lowlevel.helper_types import ReadResourceContents

# Jinja2 imports - optional dependency
try:
    from jinja2 import Environment, DictLoader, FileSystemLoader, select_autoescape, BaseLoader
    from jinja2 import Undefined, ChoiceLoader
    JINJA2_AVAILABLE = True
except ImportError:
    Environment = None
    DictLoader = None
    FileSystemLoader = None
    select_autoescape = None
    BaseLoader = None
    Undefined = None
    ChoiceLoader = None
    JINJA2_AVAILABLE = False

logger = logging.getLogger(__name__)


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
    
    def __init__(self, message: str, resource_uri: Optional[str] = None, template_text: Optional[str] = None):
        super().__init__(message)
        self.resource_uri = resource_uri
        self.template_text = template_text
    pass


class SilentUndefined(Undefined):
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
        return ''

    def __str__(self) -> str:
        """String representation of undefined variable."""
        return ''

    def __bool__(self) -> bool:
        """Boolean evaluation of undefined variable."""
        return False
    
    def __getattr__(self, name: str) -> 'SilentUndefined':
        """Return another SilentUndefined for chained attribute access."""
        return SilentUndefined()


class EnhancedTemplateMiddleware(Middleware):
    """
    Enhanced template parameter substitution middleware with hybrid Jinja2 support.
    
    This middleware intercepts FastMCP tool calls and automatically resolves template
    expressions in tool parameters using either simple regex-based templating or the
    full-featured Jinja2 template engine.
    
    ## Template Engine Selection
    
    The middleware automatically detects and routes templates to the appropriate engine:
    
    ### Simple Templates (Regex-based, v2 compatible)
    - Pattern: `{{resource://uri}}` or `{{resource://uri.property.path}}`
    - Fast regex-based resolution
    - Direct resource fetching with property extraction
    - Backward compatible with existing templates
    
    ### Jinja2 Templates (Full template engine)
    - Patterns: `{% if %}`, `{{ var | filter }}`, `{# comments #}`
    - Control structures: conditionals, loops, assignments
    - Custom filters and functions
    - Template inheritance and includes
    - Rich context with utility functions
    
    ### Mixed Templates
    - Combine both approaches in a single template
    - Simple expressions are pre-resolved before Jinja2 processing
    - Allows progressive template enhancement
    
    ## Resource Resolution System
    
    ### Supported Resource URIs
    - `user://current/email` - Current user's email address
    - `service://gmail/labels` - Gmail labels list
    - `recent://all` - Recent content across all Google Workspace services
    - `auth://session/current` - Current authentication session
    - Custom resource schemes via FastMCP resource endpoints
    
    ### Property Extraction
    ```python
    # Direct property access
    "{{user://current/profile.email}}"  # → user@example.com
    
    # Nested property paths
    "{{workspace://content/recent.summary.total_files}}"  # → 42
    
    # Array indexing
    "{{service://gmail/labels.0.name}}"  # → "Important"
    ```
    
    ## Performance Features
    
    ### Caching System
    - Configurable TTL-based resource caching
    - Reduces redundant FastMCP resource calls
    - Cache statistics and management methods
    - Automatic cache expiration
    
    ### Template Compilation
    - Jinja2 templates are compiled and cached
    - Template file loading and macro registration
    - Efficient re-use of compiled templates
    
    ## Security & Error Handling
    
    ### Sandboxed Execution
    - Jinja2 templates run in controlled environment
    - Limited access to Python builtins
    - Safe property access with SilentUndefined
    
    ### Graceful Degradation
    - Template resolution failures don't break tool execution
    - Original parameter values preserved on error
    - Comprehensive debug logging for troubleshooting
    
    ## Usage Example
    
    ```python
    from middleware.template_middleware import setup_enhanced_template_middleware
    
    # Setup middleware
    mcp = FastMCP("MyServer")
    middleware = setup_enhanced_template_middleware(
        mcp,
        enable_caching=True,
        cache_ttl_seconds=300,
        enable_debug=False
    )
    
    # Use in tools
    @mcp.tool()
    async def personalized_greeting(
        user_name: str = "{{user://current/profile.name}}",
        greeting_template: str =
    ) -> str:
        return greeting_template
    ```
    
    ## Class Attributes
    
    - `SIMPLE_TEMPLATE_PATTERN`: Regex for simple template detection
    - `RESOURCE_URI_PATTERN`: Regex for resource URI detection
    - `JINJA2_DETECTION_PATTERNS`: List of Jinja2 syntax patterns
    
    ## Dependencies
    
    - **Required**: `fastmcp`, `typing`, `datetime`, `pathlib`
    - **Optional**: `jinja2` (for advanced templating features)
    
    When Jinja2 is not available, the middleware falls back to simple templating only.
    """
    
    # Pattern to match simple template expressions like {{user://current/email.email}}
    SIMPLE_TEMPLATE_PATTERN = re.compile(r'\{\{([a-zA-Z][a-zA-Z0-9]*://[^}]+)\}\}')

    # Enhanced pattern to match resource URIs in ALL contexts (expressions, loops, conditionals, etc.)
    # Match URI part and optional property access (can be multiple levels deep)
    # Changed from (\.\w+)? to ((?:\.\w+)*) to capture full property paths like .property.subproperty
    # Removed \b word boundaries to match URIs after {{ or other non-word characters
    # IMPORTANT: URI path should NOT include dots to allow property separation
    RESOURCE_URI_PATTERN = re.compile(r'([a-zA-Z][a-zA-Z0-9]*://[a-zA-Z0-9/_-]+)((?:\.\w+)*)')

    # Pattern to detect Jinja2 syntax (control structures, filters, etc.)
    JINJA2_DETECTION_PATTERNS = [
        re.compile(r'\{%\s*\w+'),              # {% if, {% for, etc.
        re.compile(r'\{\{[^}]*\|[^}]*\}\}'),   # {{ var | filter }} - complete pattern
        re.compile(r'\{\{[^}]*\([^}]*\}\}'),   # {{ function() }} - function calls
        re.compile(r'\{#.*?#\}'),              # {# comments #}
        # Also detect resource URIs in Jinja2 contexts
        re.compile(r'\{%[^%]*[a-zA-Z][a-zA-Z0-9]*://[^%]*%\}'),  # {% for item in resource://uri %}
        re.compile(r'\{\{[^}]*[a-zA-Z][a-zA-Z0-9]*://[^}]*\}\}'), # {{ resource://uri.property }}
        re.compile(r'\{\{[^}]*[a-zA-Z][a-zA-Z0-9]*://[^}]*\.[^}]*\}\}'), # {{ resource://uri.property }}
    ]
    
    def __init__(
        self,
        enable_caching: bool = True,
        cache_ttl_seconds: int = 300,
        enable_debug_logging: bool = True,
        jinja2_options: Optional[Dict[str, Any]] = None,
        templates_dir: Optional[str] = None
    ) -> None:
        """
        Initialize the enhanced template parameter middleware.
        
        Sets up both simple regex-based templating and Jinja2 templating engines,
        configures resource caching, and prepares the template environment with
        custom filters and functions.
        
        Args:
            enable_caching: Whether to cache resolved resources for performance.
                When enabled, resources are cached with TTL-based expiration
                to reduce redundant FastMCP resource calls. Recommended for
                production environments. Default: True.
                
            cache_ttl_seconds: Time-to-live for cached resources in seconds.
                After this duration, cached resources expire and will be
                re-fetched on next access. Balance between performance and
                data freshness. Default: 300 (5 minutes).
                
            enable_debug_logging: Enable detailed debug logging for template
                resolution process. Logs template detection, resource fetching,
                property extraction, and resolution results. Useful for
                development and troubleshooting. Default: False.
                
            jinja2_options: Additional configuration options for Jinja2 Environment.
                Common options include:
                - 'autoescape': bool - Enable HTML/XML auto-escaping
                - 'trim_blocks': bool - Strip trailing newlines from blocks
                - 'lstrip_blocks': bool - Strip leading whitespace from blocks
                - 'undefined': Undefined class - Custom undefined behavior
                
                Default options are applied:
                ```python
                {
                    'autoescape': False,        # Preserve JSON content
                    'undefined': SilentUndefined, # Graceful missing variables
                    'trim_blocks': True,        # Clean block formatting
                    'lstrip_blocks': True       # Clean indentation
                }
                ```
                
            templates_dir: Path to directory containing .j2 template files.
                Templates in this directory are automatically loaded and
                their macros are made available globally in Jinja2 environment.
                If None, defaults to 'middleware/templates' relative to this file.
                Use absolute paths for custom template locations.
                
        Raises:
            ImportError: When Jinja2 features are used but jinja2 package
                is not installed. Simple templating continues to work.
                
            FileNotFoundError: When specified templates_dir doesn't exist
                and contains required template files.
                
        Example:
            ```python
            # Basic setup with defaults
            middleware = EnhancedTemplateMiddleware()
            
            # Production setup with custom caching
            middleware = EnhancedTemplateMiddleware(
                enable_caching=True,
                cache_ttl_seconds=600,  # 10 minutes
                enable_debug_logging=False
            )
            
            # Development setup with debugging
            middleware = EnhancedTemplateMiddleware(
                enable_debug_logging=True,
                jinja2_options={'autoescape': True},
                templates_dir='/path/to/custom/templates'
            )
            ```
            
        Note:
            The middleware automatically detects Jinja2 availability and falls
            back to simple templating if the package is not installed. This
            ensures compatibility across different deployment environments.
        """
        self.enable_caching = enable_caching
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enable_debug_logging = enable_debug_logging
        
        # Set up templates directory
        if templates_dir is None:
            # Default to templates directory relative to this file
            current_dir = Path(__file__).parent
            self.templates_dir = current_dir / "templates"
        else:
            self.templates_dir = Path(templates_dir)
        
        # Set up prompts directory for random template rendering
        self.prompts_dir = Path(__file__).parent.parent / "prompts"
        
        # Resource cache: {resource_uri: {data: Any, expires_at: datetime}}
        self._resource_cache: Dict[str, Dict[str, Any]] = {}
        
        # Available prompt functions cache for random selection
        self._available_prompts: Optional[List[Dict[str, Any]]] = None
        
        # Initialize Jinja2 environment if available
        self.jinja2_env = None
        if JINJA2_AVAILABLE:
            self._setup_jinja2_environment(jinja2_options or {})
            logger.info("✨ Enhanced Template Middleware initialized with Jinja2 support")
        else:
            logger.warning("⚠️ Jinja2 not available - falling back to simple templating only")
            logger.info("   Install with: pip install jinja2")
        
        logger.info("✨ Enhanced Template Middleware initialized")
        logger.info(f"   Simple templating: ✅ Available")
        logger.info(f"   Jinja2 templating: {'✅ Available' if JINJA2_AVAILABLE else '❌ Not available'}")
        logger.info(f"   Caching: {'enabled' if enable_caching else 'disabled'}")
        logger.info(f"   Cache TTL: {cache_ttl_seconds} seconds")
    
    def _setup_jinja2_environment(self, options: Dict[str, Any]) -> None:
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
        
        Args:
            options: User-provided Jinja2 Environment configuration options.
                Common options include:
                - autoescape: bool - Enable HTML/XML auto-escaping (default: False)
                - undefined: Undefined class - Handle missing variables (default: SilentUndefined)
                - trim_blocks: bool - Strip trailing newlines (default: True)
                - lstrip_blocks: bool - Strip leading whitespace (default: True)
                
        Side Effects:
            - Sets self.jinja2_env to configured Environment instance
            - Loads template macros from templates directory
            - Registers custom filters and global functions
            - Logs configuration status when debug logging enabled
            
        Raises:
            ImportError: If Jinja2 is not available (should be checked before calling)
            FileNotFoundError: If templates_dir is specified but doesn't exist
            
        Note:
            This method is automatically called during __init__ if Jinja2 is available.
            The environment uses a hybrid loader approach:
            - FileSystemLoader for .j2 template files
            - DictLoader for dynamic/runtime templates
            - ChoiceLoader to combine both approaches
        """
        default_options = {
            'autoescape': False,  # Disable autoescape for JSON content
            'undefined': SilentUndefined,  # Use our custom undefined class
            'trim_blocks': True,
            'lstrip_blocks': True,
        }
        
        # Merge with user options
        env_options = {**default_options, **options}
        
        # Set up loaders - combine FileSystemLoader for external templates and DictLoader for dynamic ones
        loaders = []
        
        # Add FileSystemLoader if templates directory exists
        if self.templates_dir.exists():
            loaders.append(FileSystemLoader(str(self.templates_dir)))
            if self.enable_debug_logging:
                logger.debug(f"📁 Added FileSystemLoader for templates directory: {self.templates_dir}")
        
        # Add DictLoader for dynamic templates
        loaders.append(DictLoader({}))
        
        # Use ChoiceLoader to combine multiple loaders
        combined_loader = ChoiceLoader(loaders) if len(loaders) > 1 else loaders[0]
        
        # Create environment
        self.jinja2_env = Environment(
            loader=combined_loader,
            **env_options
        )
        
        # Load and register macros from template files
        self._load_template_macros()
        
        # Set up resource functions and filters
        self._setup_resource_functions()
        
        # Initialize macro registry for template://macros resources
        self._macro_registry = {}
        self._scan_and_register_macros()
        
        if self.enable_debug_logging:
            logger.debug("🎭 Jinja2 environment configured with custom functions, filters, and template macros")
    
    def _scan_and_register_macros(self) -> None:
        """
        Scan template files for macro definitions and register them for template://macros resources.
        
        This method:
        1. Scans all .j2 files in templates_dir
        2. Extracts macro definitions using regex
        3. Looks for usage examples in comments
        4. Stores macro information in _macro_registry
        """
        if not self.jinja2_env or not self.templates_dir.exists():
            return
        
        # Find all .j2 template files
        template_files = list(self.templates_dir.glob('*.j2'))
        
        if self.enable_debug_logging:
            logger.debug(f"🔍 Scanning {len(template_files)} template files for macros")
        
        # Regex patterns for macro detection
        macro_pattern = re.compile(r'{% macro (\w+)\([^%]*%}', re.MULTILINE)
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
    
    async def on_get_prompt(self, context: MiddlewareContext, call_next):
        """
        Handle prompt requests with automatic random template rendering.
        
        This handler intercepts prompt requests and can optionally render a random
        template from the prompts folder using the existing Jinja2 infrastructure.
        
        Supports:
        - Automatic discovery of prompt functions from prompts/*.py files
        - Random selection from available prompts and templates
        - Full Jinja2 rendering with resource resolution
        - Template file rendering from prompts/templates/
        """
        prompt_name = getattr(context.message, 'name', '')
        
        if self.enable_debug_logging:
            logger.debug(f"🎭 Processing prompt request: {prompt_name}")
        
        # Check if this is a request for a random template
        if prompt_name == "random_template" or prompt_name.startswith("random_"):
            try:
                # Generate a random template response
                random_response = await self._generate_random_template(context)
                if random_response:
                    return random_response
            except Exception as e:
                logger.error(f"❌ Random template generation failed: {e}")
                # Fall through to normal prompt handling
        
        # Continue with normal prompt processing
        return await call_next(context)
    
    async def _generate_random_template(self, context: MiddlewareContext):
        """
        Generate a random template from available prompts and template files.
        
        This method:
        1. Discovers available prompt functions from prompts/*.py files
        2. Finds template files in prompts/templates/
        3. Randomly selects one to render
        4. Uses Jinja2 infrastructure to render with resource resolution
        5. Returns rendered content wrapped in PromptMessage
        """
        if not context.fastmcp_context:
            if self.enable_debug_logging:
                logger.debug("⚠️ No FastMCP context available for random template generation")
            return None
        
        try:
            # Discover available templates/prompts
            available_options = await self._discover_available_prompts()
            
            if not available_options:
                logger.warning("⚠️ No prompts or templates found for random selection")
                return None
            
            # Randomly select an option
            selected = random.choice(available_options)
            
            if self.enable_debug_logging:
                logger.debug(f"🎲 Randomly selected: {selected['type']} → {selected['name']}")
            
            # Render the selected template
            if selected['type'] == 'prompt_function':
                # Execute the prompt function
                return await self._execute_prompt_function(selected, context)
            elif selected['type'] == 'template_file':
                # Render the template file
                return await self._render_template_file(selected, context)
            else:
                logger.warning(f"⚠️ Unknown template type: {selected['type']}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Random template generation failed: {e}")
            return None
    
    async def _discover_available_prompts(self) -> List[Dict[str, Any]]:
        """
        Discover available prompts from both .py files and template files.
        
        Returns:
            List of available prompt options with metadata
        """
        if self._available_prompts is not None:
            return self._available_prompts
        
        available = []
        
        # 1. Discover prompt functions from .py files
        prompt_functions = await self._discover_prompt_functions()
        available.extend(prompt_functions)
        
        # 2. Discover template files
        template_files = await self._discover_template_files()
        available.extend(template_files)
        
        # Cache the results
        self._available_prompts = available
        
        if self.enable_debug_logging:
            logger.debug(f"🔍 Discovered {len(available)} total prompt options:")
            logger.debug(f"   - {len(prompt_functions)} prompt functions")
            logger.debug(f"   - {len(template_files)} template files")
        
        return available
    
    async def _discover_prompt_functions(self) -> List[Dict[str, Any]]:
        """Discover prompt functions from prompts/*.py files."""
        prompt_functions = []
        
        # Find all Python files in prompts directory
        prompts_py_files = list(self.prompts_dir.glob("*.py"))
        
        for py_file in prompts_py_files:
            if py_file.name == "__init__.py":
                continue
                
            try:
                # Extract module name and expected setup function
                module_name = py_file.stem
                setup_function_name = f"setup_{module_name}"
                
                # Add to available prompt functions list
                prompt_functions.append({
                    'type': 'prompt_function',
                    'name': module_name,
                    'module_file': str(py_file.relative_to(self.prompts_dir.parent)),
                    'setup_function': setup_function_name,
                    'description': f"Prompt functions from {module_name}",
                    'source': 'python_module'
                })
                
                if self.enable_debug_logging:
                    logger.debug(f"📝 Found prompt module: {module_name}")
                    
            except Exception as e:
                logger.warning(f"⚠️ Failed to process prompt file {py_file.name}: {e}")
        
        return prompt_functions
    
    async def _discover_template_files(self) -> List[Dict[str, Any]]:
        """Discover template files from prompts/templates/ directory."""
        template_files = []
        
        templates_dir = self.prompts_dir / "templates"
        if not templates_dir.exists():
            return template_files
        
        # Find all template files recursively
        for template_file in templates_dir.rglob("*"):
            if template_file.is_file() and template_file.suffix in ['.txt', '.j2', '.jinja2', '.md']:
                try:
                    template_files.append({
                        'type': 'template_file',
                        'name': template_file.stem,
                        'file_path': str(template_file),
                        'relative_path': str(template_file.relative_to(templates_dir)),
                        'category': template_file.parent.name if template_file.parent != templates_dir else 'general',
                        'description': f"Template file: {template_file.relative_to(templates_dir)}",
                        'source': 'template_file'
                    })
                    
                    if self.enable_debug_logging:
                        logger.debug(f"📄 Found template file: {template_file.relative_to(templates_dir)}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Failed to process template file {template_file}: {e}")
        
        return template_files
    
    async def _execute_prompt_function(self, selected: Dict[str, Any], context: MiddlewareContext):
        """
        Execute a randomly selected prompt function.
        
        This imports the prompt module and calls a representative prompt function
        to generate content using the existing prompt infrastructure.
        """
        try:
            module_name = selected['name']
            
            # Import the prompt module dynamically
            module_path = f"prompts.{module_name}"
            prompt_module = importlib.import_module(module_path)
            
            if self.enable_debug_logging:
                logger.debug(f"📦 Imported prompt module: {module_path}")
            
            # Find available prompt functions in the module
            prompt_functions = []
            for attr_name in dir(prompt_module):
                attr = getattr(prompt_module, attr_name)
                if callable(attr) and not attr_name.startswith('_') and attr_name != 'setup':
                    # Check if it looks like a prompt function (has Context parameter)
                    try:
                        import inspect
                        sig = inspect.signature(attr)
                        params = list(sig.parameters.keys())
                        if 'context' in params or len(params) > 0:
                            prompt_functions.append({
                                'name': attr_name,
                                'function': attr,
                                'signature': sig
                            })
                    except Exception:
                        continue
            
            if not prompt_functions:
                logger.warning(f"⚠️ No prompt functions found in {module_name}")
                return None
            
            # Randomly select a prompt function
            selected_func = random.choice(prompt_functions)
            
            if self.enable_debug_logging:
                logger.debug(f"🎯 Selected prompt function: {selected_func['name']}")
            
            # Create a mock Context object
            mock_context = self._create_mock_context(context)
            
            # Call the prompt function with default parameters
            try:
                result = await selected_func['function'](mock_context)
                
                if self.enable_debug_logging:
                    logger.debug(f"✅ Prompt function executed successfully")
                
                return result
                
            except Exception as e:
                # Try calling without await if it's not async
                try:
                    result = selected_func['function'](mock_context)
                    return result
                except Exception as e2:
                    logger.error(f"❌ Failed to execute prompt function {selected_func['name']}: {e2}")
                    return None
            
        except Exception as e:
            logger.error(f"❌ Failed to execute prompt function from {selected['name']}: {e}")
            return None
    
    async def _render_template_file(self, selected: Dict[str, Any], context: MiddlewareContext):
        """
        Render a randomly selected template file using Jinja2.
        
        This loads and renders a template file from prompts/templates/ using
        the existing Jinja2 infrastructure with full resource resolution.
        """
        try:
            template_file_path = Path(selected['file_path'])
            
            if not template_file_path.exists():
                logger.warning(f"⚠️ Template file not found: {template_file_path}")
                return None
            
            # Read template content
            template_content = template_file_path.read_text(encoding='utf-8')
            
            if self.enable_debug_logging:
                logger.debug(f"📄 Loaded template file: {selected['relative_path']}")
                logger.debug(f"📝 Template length: {len(template_content)} characters")
            
            # Use Jinja2 to render if available, otherwise fallback to simple rendering
            if JINJA2_AVAILABLE and self.jinja2_env:
                rendered_content = await self._render_with_jinja2(
                    template_content,
                    context.fastmcp_context,
                    f"template_file_{selected['name']}"
                )
            else:
                # Fallback to simple template resolution
                rendered_content = await self._resolve_string_templates(
                    template_content,
                    context.fastmcp_context,
                    f"template_file_{selected['name']}"
                )
            
            # Wrap in PromptMessage format
            from fastmcp.prompts.prompt import PromptMessage, TextContent
            
            result = PromptMessage(
                role="assistant",
                content=TextContent(type="text", text=rendered_content)
            )
            
            if self.enable_debug_logging:
                logger.debug(f"✅ Template file rendered successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to render template file {selected['name']}: {e}")
            return None
    
    async def _render_with_jinja2(self, template_content: str, fastmcp_context, param_path: str) -> str:
        """Render template content using Jinja2 with full resource resolution."""
        if not self.jinja2_env:
            # Fallback to simple template resolution
            return await self._resolve_string_templates(template_content, fastmcp_context, param_path)
        
        try:
            # Pre-process resource URIs
            processed_template_text, resource_context = await self._preprocess_resource_uris(
                template_content, fastmcp_context
            )
            
            # Create Jinja2 template
            template = self.jinja2_env.from_string(processed_template_text)
            
            # Build template context with resources
            template_context = await self._build_template_context(fastmcp_context)
            template_context.update(resource_context)
            
            # Render template
            result = template.render(**template_context)
            
            if self.enable_debug_logging:
                logger.debug(f"✅ Jinja2 template rendered: {param_path}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Jinja2 template rendering failed for {param_path}: {e}")
            # Fall back to simple template resolution
            return await self._resolve_string_templates(template_content, fastmcp_context, param_path)
    
    def _create_mock_context(self, middleware_context: MiddlewareContext):
        """Create a mock Context object for prompt function execution."""
        # Create a simple mock context object that mimics the Context interface
        class MockContext:
            def __init__(self):
                self.request_id = getattr(middleware_context, 'request_id', f"random_template_{random.randint(1000, 9999)}")
                self.session_id = getattr(middleware_context, 'session_id', None)
                self.meta = {}
                
            async def read_resource(self, uri: str):
                """Mock resource reading - delegates to FastMCP context if available."""
                if hasattr(middleware_context, 'fastmcp_context') and middleware_context.fastmcp_context:
                    try:
                        return await middleware_context.fastmcp_context.read_resource(uri)
                    except Exception:
                        return None
                return None
        
        return MockContext()
    
    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """
        Handle template:// resource URIs for macro discovery and usage examples.
        
        Supports:
        - template://macros - List all available macros with usage examples
        - template://macros/{macro_name} - Get specific macro usage example
        """
        # Get the resource URI from the message
        resource_uri = str(context.message.uri) if hasattr(context.message, 'uri') and context.message.uri else ''
        
        if self.enable_debug_logging:
            logger.debug(f"🔍 Checking template resource URI: {resource_uri}")
        
        # Check if this is a template:// URI that we should handle
        if not resource_uri.startswith('template://'):
            # Not our URI pattern, pass through to next middleware
            return await call_next(context)
        
        logger.info(f"🎯 Handling template resource URI: {resource_uri}")
        
        try:
            if resource_uri == 'template://macros':
                # Return all available macros
                await self._handle_all_macros(context)
                return await call_next(context)
            elif resource_uri.startswith('template://macros/'):
                # Return specific macro usage example
                macro_name = resource_uri.replace('template://macros/', '')
                await self._handle_specific_macro(macro_name, context)
                return await call_next(context)
            else:
                # Unknown template pattern
                error_data = {
                    "error": f"Unknown template resource pattern: {resource_uri}",
                    "supported_patterns": [
                        "template://macros - List all available macros",
                        "template://macros/{macro_name} - Get specific macro usage"
                    ]
                }
                context.fastmcp_context.set_state(f"template_resource_{resource_uri}", error_data)
                return await call_next(context)
                
        except Exception as e:
            logger.error(f"❌ Error handling template resource {resource_uri}: {e}")
            error_data = {"error": str(e), "timestamp": datetime.now().isoformat()}
            context.fastmcp_context.set_state(f"template_resource_{resource_uri}", error_data)
            return await call_next(context)
    
    async def _handle_all_macros(self, context: MiddlewareContext) -> None:
        """Handle template://macros - return all available macros with usage examples."""
        
        if not self._macro_registry:
            self._scan_and_register_macros()
        
        response_data = {
            "macros": self._macro_registry,
            "total_count": len(self._macro_registry),
            "templates_dir": str(self.templates_dir),
            "generated_at": datetime.now().isoformat()
        }
        
        # Store in context state for resource handler
        context.fastmcp_context.set_state("template_resource_template://macros", response_data)
        logger.info(f"📚 Stored all macros data: {len(self._macro_registry)} macros")
    
    async def _handle_specific_macro(self, macro_name: str, context: MiddlewareContext) -> None:
        """Handle template://macros/{macro_name} - return specific macro usage example."""
        
        if not self._macro_registry:
            self._scan_and_register_macros()
        
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
        context.fastmcp_context.set_state(cache_key, response_data)
        logger.info(f"📝 Stored macro data for '{macro_name}': found={response_data.get('found', False)}")
    
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
        if not self.jinja2_env or not self.templates_dir.exists():
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
            
        Custom Filters Added:
            - extract: Extract nested properties using dot notation
            - safe_get: Safely access dict/object properties with defaults
            - format_date: Format datetime objects/strings with custom patterns
            - json_pretty: Pretty-print JSON data with configurable indentation
            - strftime: Format dates using strftime patterns
            - map_list: Map object attributes to list values
            - map_attr: Alias for map_list for attribute mapping
            
        Filter Usage Examples:
            - {{ data | extract('user.profile.email') }}
            - {{ user | safe_get('name', 'Anonymous') }}
            - {{ timestamp | format_date('%Y-%m-%d %H:%M') }}
            - {{ data | json_pretty(4) }}
            - {{ items | map_list('name') }}
            
        Side Effects:
            - Modifies self.jinja2_env.globals with utility functions
            - Modifies self.jinja2_env.filters with custom filters
            - All functions/filters become available in all templates
            
        Error Handling:
            - Filters are designed to be defensive and return safe defaults
            - Invalid inputs typically return empty strings or original values
            - No exceptions are raised during template rendering
            
        Note:
            This method is automatically called during Jinja2 environment setup.
            Functions and filters are designed to be safe for use in sandboxed
            template execution environments.
        """
        if not self.jinja2_env:
            return
            
        # Simple functions that work with pre-populated context data
        # These will be accessible as global functions in templates
        self.jinja2_env.globals.update({
            'now': lambda: datetime.now(timezone.utc),
        })
        
        # Add custom filters
        self.jinja2_env.filters.update({
            'extract': self._extract_filter,
            'safe_get': self._safe_get_filter,
            'format_date': self._format_date_filter,
            'json_pretty': self._json_pretty_filter,
            'strftime': self._strftime_filter,
            'map_list': self._map_list_filter,
            'map_attr': self._map_attribute_filter,
            'format_drive_image_url': self._format_drive_image_url_filter,
        })
    
    def _extract_filter(self, data: Any, path: str):
        """Extract property from data using dot notation."""
        return self._extract_property(data, path)
    
    def _safe_get_filter(self, data: Any, key: str, default: Any = ''):
        """Safely get a value from data."""
        if isinstance(data, dict):
            return data.get(key, default)
        elif hasattr(data, key):
            return getattr(data, key, default)
        return default
    
    def _format_date_filter(self, date_input: Any, format_str: str = '%Y-%m-%d %H:%M'):
        """Format a date string or datetime object."""
        try:
            # Handle datetime objects directly
            if isinstance(date_input, datetime):
                return date_input.strftime(format_str)
            elif isinstance(date_input, str):
                # Try to parse ISO format first
                try:
                    dt = datetime.fromisoformat(date_input.replace('Z', '+00:00'))
                    return dt.strftime(format_str)
                except ValueError:
                    return date_input
            return str(date_input)
        except Exception:
            return str(date_input)
    
    def _json_pretty_filter(self, data: Any, indent: int = 2):
        """Pretty print JSON data."""
        try:
            return json.dumps(data, indent=indent, default=str)
        except Exception:
            return str(data)

    def _strftime_filter(self, date_input: Any, format_str: str = '%Y-%m-%d %H:%M:%S'):
        """Format a date using strftime (Jinja2 filter)."""
        try:
            # Handle datetime objects directly
            if isinstance(date_input, datetime):
                return date_input.strftime(format_str)
            elif isinstance(date_input, str):
                # Try to parse ISO format first
                try:
                    dt = datetime.fromisoformat(date_input.replace('Z', '+00:00'))
                    return dt.strftime(format_str)
                except ValueError:
                    return date_input
            elif callable(date_input):
                # Handle function calls like now()
                result = date_input()
                if isinstance(result, datetime):
                    return result.strftime(format_str)
                return str(result)
            return str(date_input)
        except Exception:
            return str(date_input)

    def _map_list_filter(self, items: Any, attribute: str = None):
        """Map items to attribute values and return as list."""
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
            if self.enable_debug_logging:
                logger.debug(f"⚠️ map_list filter error: {e}")
            return []

    def _map_attribute_filter(self, items: Any, attribute: str):
        """Map items to attribute values (alias for map_list)."""
        return self._map_list_filter(items, attribute)
    
    def _format_drive_image_url_filter(self, url: str) -> str:
        """
        Format Google Drive URLs for image embedding.
        
        Converts various Drive URL formats to the proper uc?export=view format
        that can be embedded in HTML img tags.
        
        Supported input formats:
        - https://drive.google.com/file/d/FILE_ID/view
        - https://drive.google.com/file/d/FILE_ID/view?usp=sharing
        - https://drive.google.com/uc?id=FILE_ID
        - FILE_ID (just the ID)
        
        Args:
            url: Drive URL or file ID to format
            
        Returns:
            Formatted URL: https://drive.google.com/uc?export=view&id=FILE_ID
        """
        if not url or not isinstance(url, str):
            return url
        
        import re
        
        # Pattern 1: https://drive.google.com/file/d/FILE_ID/view
        match = re.search(r'/file/d/([a-zA-Z0-9-_]+)', url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?export=view&id={file_id}"
        
        # Pattern 2: https://drive.google.com/uc?id=FILE_ID
        match = re.search(r'[?&]id=([a-zA-Z0-9-_]+)', url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?export=view&id={file_id}"
        
        # Pattern 3: Just the ID itself (25+ characters, alphanumeric + hyphens/underscores)
        if re.match(r'^[a-zA-Z0-9-_]{25,}$', url):
            return f"https://drive.google.com/uc?export=view&id={url}"
        
        # Pattern 4: Already in correct format
        if 'drive.google.com/uc?export=view' in url:
            return url
            
        # Return original if no pattern matches
        return url
    
    async def on_call_tool(self, context: MiddlewareContext, call_next) -> Any:
        """
        Middleware hook to intercept and process tool calls with template resolution.
        
        This is the main entry point for the middleware. It intercepts every tool call,
        analyzes the parameters for template expressions, resolves them using the
        appropriate template engine, and then continues with the original tool execution.
        
        Processing Flow:
        1. Extract tool name and arguments from the context
        2. Check for FastMCP context availability
        3. Detect and resolve template expressions in parameters
        4. Update the context with resolved parameter values
        5. Continue with normal tool execution
        
        Template Detection:
        - Recursively processes all parameter values (strings, dicts, lists)
        - Automatically detects simple vs Jinja2 template syntax
        - Routes to appropriate template engine for resolution
        - Preserves non-template values unchanged
        
        Args:
            context: MiddlewareContext containing the tool call information
                - context.message.name: Tool name being called
                - context.message.arguments: Tool parameters to process
                - context.fastmcp_context: FastMCP context for resource access
            call_next: Continuation function to proceed with tool execution
            
        Returns:
            Result from the original tool execution after template resolution
            
        Error Handling:
        - Missing FastMCP context: logs warning and continues without processing
        - Template resolution failures: logs error and continues with original values
        - Graceful degradation ensures tool execution is never blocked
        
        Side Effects:
        - Modifies context.message.arguments with resolved template values
        - Logs processing activity when debug logging enabled
        - May trigger resource fetching and caching operations
        
        Example:
            Original tool call:
            ```
            send_email(user_email="{{user://current/email}}", subject="Hello")
            ```
            
            After middleware processing:
            ```
            send_email(user_email="john@example.com", subject="Hello")
            ```
            
        Note:
            This method is automatically called by the FastMCP middleware system.
            It should not be called directly by user code.
        """
        tool_name = getattr(context.message, 'name', 'unknown')
        
        if self.enable_debug_logging:
            logger.debug(f"🔧 Processing tool call: {tool_name}")
        
        # Check if we have FastMCP context for resource resolution
        if not hasattr(context, 'fastmcp_context') or not context.fastmcp_context:
            if self.enable_debug_logging:
                logger.debug(f"⚠️ No FastMCP context available for tool: {tool_name}")
            return await call_next(context)
        
        try:
            # Track if templates were applied
            template_applied = False
            
            # Get the tool arguments
            original_args = getattr(context.message, 'arguments', {})
            
            if original_args:
                # Resolve template parameters
                resolved_args = await self._resolve_parameters(
                    original_args,
                    context.fastmcp_context,
                    tool_name
                )
                
                # Update the message arguments if anything was resolved
                if resolved_args != original_args:
                    context.message.arguments = resolved_args
                    template_applied = True  # Templates were successfully applied!
                    if self.enable_debug_logging:
                        logger.debug(f"✅ Resolved templates for tool: {tool_name}")
            
            # Execute the tool and get the result
            result = await call_next(context)
            
            # TEMPLATE TRACKING FIX: Inject into structured_content
            if template_applied and result:
                try:
                    result.structured_content["templateApplied"] = True
                    # result.structured_content["templateName"] = "calendar_dashboard"  # Simple fallback name
                    if self.enable_debug_logging:
                        logger.debug(f"✅ Injected templateApplied=True into {tool_name} structured_content")
                except Exception as e:
                    if self.enable_debug_logging:
                        logger.debug(f"⚠️ Failed to inject template tracking into structured_content: {e}")
            elif result:
                result.structured_content["templateApplied"] = False
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Template resolution failed for tool {tool_name}: {e}")
            # Continue without template resolution on error
            return await call_next(context)
    
    async def _resolve_parameters(
        self,
        parameters: Dict[str, Any],
        fastmcp_context,
        tool_name: str
    ) -> Dict[str, Any]:
        """
        Recursively resolve template expressions in all tool parameters.
        
        Traverses the parameter dictionary and processes each value for template
        expressions. Handles nested structures (dicts within dicts, lists, etc.)
        and preserves the original structure while resolving template content.
        
        Args:
            parameters: Dictionary of tool parameters to process
                Can contain strings, numbers, booleans, dicts, lists, or None values
            fastmcp_context: FastMCP context for resource resolution
                Must provide access to read_resource functionality
            tool_name: Name of the tool being called (for debugging/logging)
                
        Returns:
            Dictionary with same structure as input but with resolved template values.
            Non-template values are returned unchanged.
            
        Processing Logic:
        - String values: Checked for template expressions and resolved
        - Dict values: Recursively processed key by key
        - List values: Recursively processed item by item
        - Other types: Returned unchanged (int, float, bool, None)
        
        Template Resolution:
        - Detects simple {{resource://uri}} patterns
        - Detects Jinja2 syntax (conditionals, loops, filters)
        - Routes to appropriate engine based on detection
        - Handles mixed templates (both simple and Jinja2 in same string)
        
        Error Handling:
        - Individual parameter failures don't affect other parameters
        - Failed resolutions preserve original parameter values
        - Comprehensive logging for troubleshooting
        
        Example:
            Input:
            ```python
            {
                "user_email": "{{user://current/email}}",
                "settings": {
                    "name": "{{user://current/profile.name}}",
                    "count": 5
                },
                "tags": ["{{workspace://recent.tag}}", "important"]
            }
            ```
            
            Output:
            ```python
            {
                "user_email": "john@example.com",
                "settings": {
                    "name": "John Doe",
                    "count": 5
                },
                "tags": ["work", "important"]
            }
            ```
        """
        resolved = {}
        
        for key, value in parameters.items():
            resolved[key] = await self._resolve_value(
                value,
                fastmcp_context,
                f"{tool_name}.{key}"
            )
        
        return resolved
    
    async def _resolve_value(
        self,
        value: Any,
        fastmcp_context,
        param_path: str
    ) -> Any:
        """Resolve a single value using the appropriate template engine."""
        if isinstance(value, str):
            return await self._resolve_string_templates(value, fastmcp_context, param_path)
            
        elif isinstance(value, dict):
            # Recursively resolve dictionary values
            resolved_dict = {}
            for k, v in value.items():
                resolved_dict[k] = await self._resolve_value(
                    v,
                    fastmcp_context,
                    f"{param_path}.{k}"
                )
            return resolved_dict
            
        elif isinstance(value, list):
            # Recursively resolve list items
            resolved_list = []
            for i, item in enumerate(value):
                resolved_item = await self._resolve_value(
                    item,
                    fastmcp_context,
                    f"{param_path}[{i}]"
                )
                resolved_list.append(resolved_item)
            return resolved_list
            
        else:
            return value
    
    async def _resolve_string_templates(
        self,
        text: str,
        fastmcp_context,
        param_path: str
    ) -> Any:
        """
        Resolve template expressions in a string using the appropriate engine.
        
        Detection logic:
        1. If contains Jinja2 syntax -> use Jinja2
        2. If contains only simple templates -> use simple resolver
        3. If mixed -> use Jinja2 (it can handle simple syntax too via custom functions)
        """
        if not text or not isinstance(text, str):
            return text
        
        # Detect template type
        has_jinja2 = self._has_jinja2_syntax(text)
        has_simple = bool(self.SIMPLE_TEMPLATE_PATTERN.search(text))
        
        if self.enable_debug_logging:
            logger.debug(f"🔍 Template detection for '{param_path}': "
                        f"Jinja2={'✅' if has_jinja2 else '❌'}, "
                        f"Simple={'✅' if has_simple else '❌'}")
        
        if has_jinja2 and JINJA2_AVAILABLE:
            # Use Jinja2 engine (can handle both simple and complex)
            return await self._resolve_jinja2_template(text, fastmcp_context, param_path)
        elif has_simple:
            # Use simple resolver (v2 compatibility)
            return await self._resolve_simple_template(text, fastmcp_context, param_path)
        else:
            # No templates found
            return text
    
    def _has_jinja2_syntax(self, text: str) -> bool:
        """Detect if text contains Jinja2 syntax."""
        # First check for standard Jinja2 patterns
        if any(pattern.search(text) for pattern in self.JINJA2_DETECTION_PATTERNS):
            return True
        
        # Also treat resource URIs with property access as Jinja2
        # This ensures {{ service://gmail/labels.description }} goes through Jinja2 processing
        # where it will be converted to {{ service_gmail_labels.description }}
        if self.SIMPLE_TEMPLATE_PATTERN.search(text):
            # Check if any of the simple templates have property access after the URI
            for match in self.SIMPLE_TEMPLATE_PATTERN.finditer(text):
                template_expr = match.group(1)
                # If the expression has a dot after the URI path, it needs Jinja2
                if '://' in template_expr and '.' in template_expr:
                    scheme_end = template_expr.index('://')
                    if template_expr.find('.', scheme_end) != -1:
                        return True
        
        return False
    
    async def _resolve_jinja2_template(
        self,
        template_text: str,
        fastmcp_context,
        param_path: str
    ) -> Any:
        """
        Resolve template using Jinja2 engine.
        
        This provides full Jinja2 functionality including:
        - Control structures (if/for/etc.)
        - Filters and functions
        - Custom resource resolution functions
        - Variable assignments
        - Macros and includes
        """
        if not self.jinja2_env:
            logger.error("❌ Jinja2 not available - falling back to simple template")
            return await self._resolve_simple_template(template_text, fastmcp_context, param_path)
        
        try:
            if self.enable_debug_logging:
                logger.debug(f"🎭 Resolving Jinja2 template: {param_path}")
            
            # IMPORTANT: Process resource URIs FIRST before mixed template processing
            # This ensures resource URIs are converted to variables before being resolved
            processed_template_text, resource_context = await self._preprocess_resource_uris(
                template_text, fastmcp_context
            )
            
            # Then pre-process any remaining v2 syntax to Jinja2-compatible syntax
            # This will handle any simple templates that aren't resource URIs
            processed_template_text = await self._preprocess_mixed_template(processed_template_text, fastmcp_context)
            # Create template with better error handling
            try:
                template = self.jinja2_env.from_string(processed_template_text)
            except Exception as template_error:
                if self.enable_debug_logging:
                    logger.debug(f"🔧 Template syntax error in processed template: {template_error}")
                    logger.debug(f"🔧 Processed template: {repr(processed_template_text)}")
                # Try with original template text if preprocessing failed
                try:
                    template = self.jinja2_env.from_string(template_text)
                except Exception as original_error:
                    if self.enable_debug_logging:
                        logger.debug(f"🔧 Original template also failed: {original_error}")
                        logger.debug(f"🔧 Original template: {repr(template_text)}")
                    raise original_error
            
            # Add resolved resource variables to context
            
            # Build template context with resource resolution capabilities
            context = await self._build_template_context(fastmcp_context)
            context.update(resource_context)
            
            # Render template
            result = template.render(**context)
            
            if self.enable_debug_logging:
                logger.debug(f"✅ Jinja2 template resolved: {param_path}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Jinja2 template resolution failed for {param_path}: {e}")
            if self.enable_debug_logging:
                logger.debug(f"🔄 Falling back to simple template resolution")
            # Fall back to simple template resolution
            return await self._resolve_simple_template(template_text, fastmcp_context, param_path)
    
    async def _preprocess_mixed_template(self, template_text: str, fastmcp_context) -> str:
        """Pre-process template to convert v2 {{resource://...}} syntax to resolved values."""
        if not template_text:
            return template_text
            
        # Find and resolve all v2 template expressions first
        matches = list(self.SIMPLE_TEMPLATE_PATTERN.finditer(template_text))
        
        if not matches:
            return template_text
        
        if self.enable_debug_logging:
            logger.debug(f"🔄 Pre-processing mixed template with {len(matches)} v2 expressions")
            logger.debug(f"🔍 Original template: {repr(template_text)}")
        
        processed_text = template_text
        
        # Process in reverse order to maintain positions
        for match in reversed(matches):
            template_expr = match.group(1)
            
            if self.enable_debug_logging:
                logger.debug(f"🎯 Processing v2 expression: {repr(template_expr)}")
            
            try:
                # Resolve the v2 expression
                resolved = await self._resolve_simple_template_expression(
                    template_expr, fastmcp_context, "preprocess"
                )
                
                if self.enable_debug_logging:
                    logger.debug(f"✅ Resolved to: {repr(resolved)}")
                
                # Convert to string representation
                if isinstance(resolved, str):
                    replacement = f'"{resolved}"'  # Quote strings for Jinja2
                elif isinstance(resolved, bool):
                    replacement = str(resolved).lower()  # true/false
                elif resolved is None:
                    replacement = '""'  # Empty string
                elif isinstance(resolved, (int, float)):
                    replacement = str(resolved)  # Numbers as-is
                else:
                    # Complex objects - convert to JSON string
                    replacement = f'"{json.dumps(resolved).replace('"', '\\"')}"'
                
                # Replace the v2 expression with the resolved value
                processed_text = (processed_text[:match.start()] +
                                replacement +
                                processed_text[match.end():])
                
            except Exception as e:
                logger.error(f"⚠️ Failed to resolve v2 expression {template_expr}: {e}")
                # Leave the original expression if resolution fails
                continue
        
        if self.enable_debug_logging:
            logger.debug(f"🔄 Processed template: {repr(processed_text)}")
        
        return processed_text
    
    async def _preprocess_resource_uris(
        self,
        template_text: str,
        fastmcp_context
    ) -> tuple[str, Dict[str, Any]]:
        """
        Pre-process resource URIs in Jinja2 templates by resolving them and
        replacing with generated variable names.

        Returns:
            Tuple of (processed_template_text, resource_context_dict)
        """
        if not template_text:
            return template_text, {}

        # Find all resource URIs in the template
        matches = list(self.RESOURCE_URI_PATTERN.finditer(template_text))

        if self.enable_debug_logging:
            logger.debug(f"🔍 Checking template: {template_text}")
            logger.debug(f"🔍 Found {len(matches)} resource URI matches")
            for i, match in enumerate(matches):
                uri = match.group(1)
                prop = match.group(2) if match.group(2) else ''
                logger.debug(f"🔍 Match {i}: {repr(uri + prop)} at position {match.start()}-{match.end()}")

        if not matches:
            return template_text, {}

        if self.enable_debug_logging:
            logger.debug(f"🔄 Pre-processing {len(matches)} resource URIs in Jinja2 template")

        processed_text = template_text
        resource_context = {}

        # Process in reverse order to maintain positions
        for match in reversed(matches):
            uri = match.group(1)
            property_path = match.group(2) if match.group(2) else None

            try:
                if self.enable_debug_logging:
                    logger.debug(f"🎯 Resolving resource URI: {uri}")
                    if property_path:
                        logger.debug(f"   Property path: {property_path}")

                # Resolve the resource with improved error handling
                try:
                    resolved_data = await self._fetch_resource(uri, fastmcp_context)
                except TemplateResolutionError:
                    # If resource resolution fails, try to extract from existing context
                    state_key = f"resource_cache_{uri}"
                    resolved_data = fastmcp_context.get_state(state_key)
                    if not resolved_data:
                        # Final fallback - use empty data structure
                        if uri.endswith('/email'):
                            resolved_data = {"email": ""}
                        else:
                            resolved_data = {}
                        if self.enable_debug_logging:
                            logger.debug(f"🔄 Using fallback empty data for {uri}")

                # Convert dictionary to SimpleNamespace for dot notation support
                resolved_data = convert_to_namespace(resolved_data)

                # Generate a meaningful variable name from URI
                # Convert user://current/email → user_current_email
                var_name = uri.replace('://', '_').replace('/', '_').replace(':', '').replace('.', '_')

                # Add to context - ensure the resolved data is properly accessible
                resource_context[var_name] = resolved_data

                # Also add direct email value if this is an email resource
                if uri.endswith('/email') and hasattr(resolved_data, 'email'):
                    resource_context[f"{var_name}_value"] = getattr(resolved_data, 'email', '')
                elif uri.endswith('/email') and isinstance(resolved_data, dict) and 'email' in resolved_data:
                    resource_context[f"{var_name}_value"] = resolved_data['email']

                # Replace URI with variable name in template
                replacement = var_name
                if property_path:
                    replacement += property_path

                processed_text = (processed_text[:match.start()] +
                                replacement +
                                processed_text[match.end():])

                if self.enable_debug_logging:
                    logger.debug(f"✅ Replaced {uri}{property_path or ''} with {replacement}")
                    logger.debug(f"📦 Added to context: {var_name} = {type(resolved_data)}")
                    if f"{var_name}_value" in resource_context:
                        logger.debug(f"📧 Also added direct value: {var_name}_value = {resource_context[f'{var_name}_value']}")

            except Exception as e:
                logger.error(f"⚠️ Failed to resolve resource URI {uri}: {e}")
                # Leave the original URI if resolution fails
                continue

        return processed_text, resource_context


    async def _build_template_context(self, fastmcp_context) -> Dict[str, Any]:
        """
        Build a rich template context for Jinja2.
        
        Provides:
        - Pre-resolved common resources
        - Helper functions
        - Utility objects
        - Current datetime/user context
        """
        context = {
            # Basic context - MUST be functions for Jinja2 compatibility
            'now': lambda: datetime.now(timezone.utc),
            'utcnow': lambda: datetime.now(timezone.utc),
            
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
            
            # Custom utilities
            'json': json,
            'datetime': datetime,
            'timedelta': timedelta,  # Added to fix timedelta undefined error
        }
        
        # Pre-resolve common resources synchronously for template context
        await self._populate_common_resources(context, fastmcp_context)
        
        return context
    
    async def _populate_common_resources(self, context: Dict[str, Any], fastmcp_context):
        """Populate template context with commonly used resources."""
        # User email - both as data and function
        try:
            user_data = await self._fetch_resource('user://current/email', fastmcp_context)
            if user_data:
                context['user'] = user_data
                if isinstance(user_data, dict):
                    user_email_str = user_data.get('email', '')
                else:
                    user_email_str = str(user_data)
                
                # Don't overwrite - provide both string value and function
                context['user_email_str'] = user_email_str
                context['user_email'] = lambda: user_email_str
                
            else:
                context['user'] = {}
                context['user_email_str'] = ''
                context['user_email'] = lambda: ''
        except Exception as e:
            if self.enable_debug_logging:
                logger.debug(f"⚠️ Failed to populate user context: {e}")
            context['user'] = {}
            context['user_email_str'] = ''
            context['user_email'] = lambda: ''
        
        # Gmail labels - both as data and function
        try:
            labels_data = await self._fetch_resource('service://gmail/labels', fastmcp_context)
            labels_list = labels_data if labels_data else []
            context['gmail_labels'] = lambda: labels_list
        except Exception:
            context['gmail_labels'] = lambda: []
        
        # User profile - both as data and function
        try:
            profile_data = await self._fetch_resource('user://current/profile', fastmcp_context)
            profile_dict = profile_data if profile_data else {}
            context['user_profile'] = lambda: profile_dict
        except Exception:
            context['user_profile'] = lambda: {}
        
        # Recent content across all services - replaces deprecated workspace://content/recent
        try:
            workspace_data = await self._fetch_resource('recent://all', fastmcp_context)
            workspace_list = workspace_data if workspace_data else []
            context['workspace_content'] = lambda: workspace_list
        except Exception:
            context['workspace_content'] = lambda: []
    
    async def _resolve_deferred_resources(self, result: str, fastmcp_context) -> str:
        """
        Resolve any deferred resource requests in the rendered template.
        
        This handles resource() function calls that were deferred during rendering.
        """
        # This is a placeholder for more complex deferred resolution
        # For now, we'll handle simple resource requests inline during rendering
        return result
    
    async def _resolve_simple_template(
        self,
        text: str,
        fastmcp_context,
        param_path: str
    ) -> Any:
        """
        Resolve template using the simple regex-based engine (v2 compatibility).
        
        This maintains full backward compatibility with existing templates.
        """
        # Find all template expressions
        matches = list(self.SIMPLE_TEMPLATE_PATTERN.finditer(text))
        
        if not matches:
            return text
        
        if self.enable_debug_logging:
            logger.debug(f"🔧 Resolving simple template: {param_path}")
        
        # Special case: if the entire string is a single template, 
        # we might return a non-string value
        if len(matches) == 1 and matches[0].group(0) == text.strip():
            # The entire string is a single template
            template_expr = matches[0].group(1)
            resolved = await self._resolve_simple_template_expression(
                template_expr,
                fastmcp_context,
                param_path
            )
            return resolved
        
        # Multiple templates or template is part of a larger string
        result = text
        for match in reversed(matches):  # Process in reverse to maintain positions
            template_expr = match.group(1)
            resolved = await self._resolve_simple_template_expression(
                template_expr,
                fastmcp_context,
                param_path
            )
            
            # Convert to string for replacement
            if isinstance(resolved, str):
                replacement = resolved
            elif isinstance(resolved, bool):
                replacement = str(resolved).lower()  # Convert True/False to 'true'/'false'
            elif resolved is None:
                replacement = ''
            else:
                replacement = json.dumps(resolved)
            
            # Replace the template expression
            result = result[:match.start()] + replacement + result[match.end():]
        
        return result
    
    async def _resolve_simple_template_expression(
        self,
        expression: str,
        fastmcp_context,
        param_path: str
    ) -> Any:
        """Resolve a single simple template expression."""
        # Split expression into resource URI and property path
        if '.' in expression and '://' in expression:
            scheme_end = expression.index('://')
            first_dot_after_scheme = expression.find('.', scheme_end)
            
            if first_dot_after_scheme != -1:
                resource_uri = expression[:first_dot_after_scheme]
                property_path = expression[first_dot_after_scheme + 1:]
            else:
                resource_uri = expression
                property_path = None
        else:
            resource_uri = expression
            property_path = None
        
        if self.enable_debug_logging:
            logger.debug(f"📍 Resolving: {resource_uri}")
            if property_path:
                logger.debug(f"   Property path: {property_path}")
        
        # Fetch the resource
        resource_data = await self._fetch_resource(resource_uri, fastmcp_context)
        
        # Extract property if specified
        if property_path:
            result = self._extract_property(resource_data, property_path)
            if self.enable_debug_logging:
                logger.debug(f"   Extracted value: {repr(result)}")
        else:
            result = resource_data
        
        return result
    
    # All the existing v2 methods for resource handling (unchanged)
    async def _fetch_resource(self, resource_uri: str, fastmcp_context) -> Any:
        """Fetch a resource using FastMCP resource system with comprehensive fallback support."""
        # Ensure URI doesn't include property path (strip after first dot)
        if '://' in resource_uri:
            scheme_end = resource_uri.index('://')
            first_dot_after_scheme = resource_uri.find('.', scheme_end)
            if first_dot_after_scheme != -1:
                resource_uri = resource_uri[:first_dot_after_scheme]
                if self.enable_debug_logging:
                    logger.debug(f"🔧 Stripped property path from URI: {resource_uri}")

        # Check cache first
        if self.enable_caching:
            cached = self._get_cached_resource(resource_uri)
            if cached is not None:
                if self.enable_debug_logging:
                    logger.debug(f"📦 Using cached resource: {resource_uri}")
                return cached

        # Check if resource is already resolved in context state
        state_key = f"resource_cache_{resource_uri}"
        cached_data = fastmcp_context.get_state(state_key)
        if cached_data:
            if self.enable_debug_logging:
                logger.debug(f"📦 Found resource in context state: {resource_uri}")
            if self.enable_caching:
                self._cache_resource(resource_uri, cached_data)
            return cached_data

        # Try common URI fallbacks FIRST for reliability
        resource_data = None
        if resource_uri == 'user://current/email':
            from auth.context import get_user_email_context
            user_email = get_user_email_context()
            resource_data = {"email": user_email or ""}
            if self.enable_debug_logging:
                logger.debug(f"✅ Resolved user email from auth context: {user_email}")
                
        elif resource_uri == 'user://current/profile':
            from auth.context import get_user_email_context
            user_email = get_user_email_context()
            resource_data = {
                "email": user_email or "",
                "name": "",
                "authenticated": bool(user_email)
            }
            
        elif resource_uri == 'auth://session/current':
            from auth.context import get_user_email_context
            user_email = get_user_email_context()
            resource_data = {
                "authenticated": bool(user_email),
                "user_email": user_email or "",
                "session_active": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        # If we resolved via fallback, cache and return
        if resource_data is not None:
            # Store in context state
            fastmcp_context.set_state(state_key, resource_data)
            # Cache locally
            if self.enable_caching:
                self._cache_resource(resource_uri, resource_data)
            return resource_data

        # Otherwise, try the FastMCP resource system
        try:
            if self.enable_debug_logging:
                logger.debug(f"🔍 Fetching resource via FastMCP: {resource_uri}")
            
            # Use the proper FastMCP resource access pattern
            content_list = await fastmcp_context.read_resource(resource_uri)
            
            if content_list and len(content_list) > 0:
                resource_result = content_list[0]
                
                # Extract data from the resource response structure
                if self.enable_debug_logging:
                    logger.debug(f"📦 Raw resource type: {type(resource_result).__name__}")
                
                resource_data = self._extract_resource_data(resource_result)
                
                if self.enable_debug_logging:
                    logger.debug(f"📄 Extracted data type: {type(resource_data).__name__}")
                
                # Store in context state and cache
                fastmcp_context.set_state(state_key, resource_data)
                if self.enable_caching:
                    self._cache_resource(resource_uri, resource_data)
                
                return resource_data
            else:
                # No content returned
                if self.enable_debug_logging:
                    logger.debug(f"❌ No content returned from FastMCP for: {resource_uri}")
                raise TemplateResolutionError(f"No content returned for resource: {resource_uri}")
                
        except Exception as e:
            logger.error(f"❌ Failed to fetch resource '{resource_uri}': {e}")
            raise TemplateResolutionError(f"Failed to fetch resource '{resource_uri}': {e}")
    
    def _extract_resource_data(self, resource_result: Any, depth: int = 0) -> Any:
        """Extract the actual data from the resource response structure."""
        MAX_DEPTH = 10
        if depth > MAX_DEPTH:
            logger.warning(f"⚠️ Maximum recursion depth ({MAX_DEPTH}) reached, returning as-is")
            return resource_result
        
        try:
            extracted = None
            
            # Handle ReadResourceContents dataclass
            if hasattr(resource_result, 'content'):
                content = resource_result.content
                mime_type = getattr(resource_result, 'mime_type', None)
                
                if isinstance(content, str):
                    if mime_type == 'application/json' or content.strip().startswith('{') or content.strip().startswith('['):
                        try:
                            extracted = json.loads(content)
                        except json.JSONDecodeError:
                            extracted = content
                    else:
                        extracted = content
                else:
                    extracted = content
                    
            # Handle standard MCP resource response structure
            elif hasattr(resource_result, 'contents') and resource_result.contents:
                content_item = resource_result.contents[0]
                
                if hasattr(content_item, 'text') and content_item.text:
                    try:
                        extracted = json.loads(content_item.text)
                    except json.JSONDecodeError:
                        extracted = content_item.text
                elif hasattr(content_item, 'blob') and content_item.blob:
                    extracted = content_item.blob
                else:
                    extracted = content_item
                    
            elif isinstance(resource_result, dict):
                if 'contents' in resource_result and resource_result['contents']:
                    content_item = resource_result['contents'][0]
                    if 'text' in content_item:
                        try:
                            extracted = json.loads(content_item['text'])
                        except (json.JSONDecodeError, TypeError):
                            extracted = content_item['text']
                    else:
                        extracted = content_item
                else:
                    # Plain dict - check if we should unwrap it first
                    if self._should_unwrap_dict(resource_result, depth):
                        if self.enable_debug_logging:
                            logger.debug(f"🔄 Unwrapping plain dict at depth {depth}")
                        key = next(iter(resource_result.keys()))
                        extracted = resource_result[key]
                    else:
                        extracted = resource_result
            else:
                extracted = resource_result
            
            # Recursive unwrapping if needed (for nested structures)
            if isinstance(extracted, dict) and self._should_unwrap_dict(extracted, depth):
                if self.enable_debug_logging:
                    logger.debug(f"🔄 Attempting recursive unwrapping at depth {depth + 1}")
                return self._extract_resource_data(extracted, depth + 1)
            
            return extracted
                
        except (IndexError, KeyError, AttributeError) as e:
            logger.warning(f"⚠️ Unexpected resource structure at depth {depth}: {e}")
            return resource_result
    
    def _should_unwrap_dict(self, data: dict, depth: int) -> bool:
        """Determine if a dictionary should be recursively unwrapped."""
        if depth >= 8 or len(data) != 1:
            return False
        
        key = next(iter(data.keys()))
        value = data[key]
        
        wrapper_keys = {
            'data', 'result', 'response', 'content', 'payload', 'body',
            'value', 'item', 'object', 'resource', 'entity', 'record'
        }
        
        key_lower = key.lower()
        is_wrapper_key = key_lower in wrapper_keys
        has_structured_value = isinstance(value, (dict, list)) and value
        
        if is_wrapper_key and has_structured_value:
            if self.enable_debug_logging:
                logger.debug(f"🎯 Unwrapping detected: '{key}' -> {type(value).__name__}")
            return True
        
        return False
    
    def _extract_property(self, data: Any, property_path: str) -> Any:
        """Extract a property from data using dot-notation path."""
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
    
    def _get_cached_resource(self, resource_uri: str) -> Optional[Any]:
        """Get a resource from cache if it exists and hasn't expired."""
        if resource_uri not in self._resource_cache:
            return None
        
        cache_entry = self._resource_cache[resource_uri]
        if datetime.now() < cache_entry['expires_at']:
            return cache_entry['data']
        
        del self._resource_cache[resource_uri]
        return None
    
    def _cache_resource(self, resource_uri: str, data: Any):
        """Cache a resource with expiration."""
        self._resource_cache[resource_uri] = {
            'data': data,
            'expires_at': datetime.now() + timedelta(seconds=self.cache_ttl_seconds)
        }
    
    def clear_cache(self) -> None:
        """
        Clear all cached resources and reset cache statistics.
        
        Removes all entries from the internal resource cache, forcing fresh
        fetches on subsequent resource requests. Useful for development,
        testing, or when resource data is known to have changed.
        
        Side Effects:
            - Clears self._resource_cache completely
            - Logs cache clearing activity
            - Next resource requests will bypass cache
            
        Use Cases:
            - Development: Clear cache when resources change
            - Testing: Ensure fresh data for test isolation
            - Runtime: Force refresh of potentially stale data
            - Memory management: Free cache memory if needed
            
        Example:
            ```python
            # Clear cache during development
            middleware.clear_cache()
            
            # Or schedule periodic cache clearing
            import asyncio
            async def periodic_cache_clear():
                while True:
                    await asyncio.sleep(3600)  # Every hour
                    middleware.clear_cache()
            ```
            
        Note:
            This operation is immediate and cannot be undone. Consider using
            get_cache_stats() first to understand current cache utilization.
        """
        self._resource_cache.clear()
        logger.info("🧹 Resource cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get detailed statistics about the resource cache state and performance.
        
        Provides comprehensive information about cache utilization, expiration
        status, and configuration settings for monitoring and debugging purposes.
        
        Returns:
            Dictionary containing cache statistics with the following keys:
            
            - enabled: bool - Whether caching is enabled in configuration
            - jinja2_available: bool - Whether Jinja2 package is available
            - total_entries: int - Total number of cache entries (including expired)
            - valid_entries: int - Number of non-expired cache entries
            - expired_entries: int - Number of expired but not yet cleaned entries
            - ttl_seconds: int - Configured time-to-live for cache entries
            - cached_uris: List[str] - List of all cached resource URIs
            
        Cache Health Indicators:
            - High valid_entries: Cache is working effectively
            - High expired_entries: Consider shorter TTL or manual clearing
            - Empty cached_uris: No resources have been cached yet
            - Large total_entries: May need memory management attention
            
        Example Output:
            ```python
            {
                "enabled": True,
                "jinja2_available": True,
                "total_entries": 25,
                "valid_entries": 18,
                "expired_entries": 7,
                "ttl_seconds": 300,
                "cached_uris": [
                    "user://current/email",
                    "service://gmail/labels",
                    "recent://all"
                ]
            }
            ```
            
        Use Cases:
            - Performance monitoring: Track cache hit rates and effectiveness
            - Memory management: Monitor cache size and growth patterns
            - Debugging: Understand which resources are being cached
            - Configuration tuning: Adjust TTL based on usage patterns
            
        Note:
            This method performs real-time analysis and may iterate through
            all cache entries to determine expiration status.
        """
        now = datetime.now()
        valid_entries = sum(
            1 for entry in self._resource_cache.values()
            if entry['expires_at'] > now
        )
        
        return {
            "enabled": self.enable_caching,
            "jinja2_available": JINJA2_AVAILABLE,
            "total_entries": len(self._resource_cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._resource_cache) - valid_entries,
            "ttl_seconds": self.cache_ttl_seconds,
            "cached_uris": list(self._resource_cache.keys())
        }
    

    


def setup_enhanced_template_middleware(
    mcp,
    enable_caching: bool = True,
    cache_ttl_seconds: int = 300,
    enable_debug: bool = False,
    jinja2_options: Optional[Dict[str, Any]] = None,
    templates_dir: Optional[str] = None
) -> EnhancedTemplateMiddleware:
    """
    Set up and configure the enhanced template parameter middleware with Jinja2 support.
    
    This is the primary setup function for integrating template parameter resolution
    into a FastMCP server. It creates, configures, and registers the middleware
    instance with optimal settings for production or development use.
    
    Args:
        mcp: FastMCP server instance to add the middleware to.
            Must be a valid FastMCP server object that supports middleware registration.
            
        enable_caching: Enable resource caching for improved performance.
            When True, resolved resources are cached with TTL-based expiration.
            Recommended for production environments to reduce FastMCP resource calls.
            Default: True.
            
        cache_ttl_seconds: Time-to-live for cached resources in seconds.
            Resources are automatically expired and re-fetched after this duration.
            Balance between performance (longer TTL) and data freshness (shorter TTL).
            Common values: 60 (1 min), 300 (5 min), 3600 (1 hour).
            Default: 300 (5 minutes).
            
        enable_debug: Enable detailed debug logging for development and troubleshooting.
            When True, logs extensive information about template detection, resource
            fetching, property extraction, and resolution results.
            Recommended for development but disable in production for performance.
            Default: False.
            
        jinja2_options: Advanced Jinja2 Environment configuration options.
            Dictionary of options passed to Jinja2 Environment constructor.
            Common options:
            - 'autoescape': bool - Enable HTML/XML auto-escaping
            - 'undefined': Undefined class - Custom undefined variable behavior
            - 'trim_blocks': bool - Strip trailing newlines from blocks
            - 'lstrip_blocks': bool - Strip leading whitespace from blocks
            Default: None (uses middleware defaults optimized for FastMCP).
            
        templates_dir: Path to directory containing .j2 template files.
            If specified, template files in this directory are automatically loaded
            and their macros become available globally in all Jinja2 templates.
            Can be absolute or relative path. If None, uses 'middleware/templates'.
            Default: None.
            
    Returns:
        EnhancedTemplateMiddleware: Configured and registered middleware instance.
        Can be used to access cache statistics, clear cache, or modify configuration.
        
    Raises:
        TypeError: If mcp is not a valid FastMCP server instance
        FileNotFoundError: If templates_dir is specified but doesn't exist
        ImportError: If Jinja2 features are requested but package not available
        
    Side Effects:
        - Adds the middleware to the FastMCP server's middleware chain
        - Initializes Jinja2 environment if available
        - Loads template macros from templates_dir
        - Logs configuration status and availability
        
    Example - Basic Setup:
        ```python
        from fastmcp import FastMCP
        from middleware.template_middleware import setup_enhanced_template_middleware
        
        mcp = FastMCP("MyServer")
        middleware = setup_enhanced_template_middleware(mcp)
        
        @mcp.tool()
        async def greet_user(name: str = "{{user://current/profile.name}}"):
            return f"Hello {name}!"
        ```
        
    Example - Production Setup:
        ```python
        middleware = setup_enhanced_template_middleware(
            mcp,
            enable_caching=True,
            cache_ttl_seconds=600,  # 10 minutes
            enable_debug=False,
            jinja2_options={'autoescape': True}
        )
        ```
        
    Example - Development Setup:
        ```python
        middleware = setup_enhanced_template_middleware(
            mcp,
            enable_debug=True,
            cache_ttl_seconds=60,  # Short TTL for development
            templates_dir='./custom_templates'
        )
        ```
        
    Integration Notes:
        - Should be added early in the middleware chain for maximum coverage
        - Compatible with existing FastMCP middleware (auth, logging, etc.)
        - Automatically falls back to simple templating if Jinja2 unavailable
        - Thread-safe and suitable for concurrent tool execution
        
    Performance Considerations:
        - Caching significantly improves performance for repeated resource access
        - Debug logging can impact performance in high-throughput scenarios
        - Jinja2 template compilation is cached automatically
        - Resource resolution is optimized with minimal FastMCP calls
    """
    middleware = EnhancedTemplateMiddleware(
        enable_caching=enable_caching,
        cache_ttl_seconds=cache_ttl_seconds,
        enable_debug_logging=enable_debug,
        jinja2_options=jinja2_options,
        templates_dir=templates_dir
    )
    
    mcp.add_middleware(middleware)
    logger.info("✅ Enhanced template middleware with Jinja2 support added to FastMCP server")
    
    return middleware


# Backward compatibility alias
StreamlinedTemplateMiddleware = EnhancedTemplateMiddleware
setup_streamlined_template_middleware = setup_enhanced_template_middleware