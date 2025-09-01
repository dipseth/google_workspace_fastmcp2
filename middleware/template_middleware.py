"""
Template Parameter Substitution Middleware for FastMCP2 with Jinja2 Integration

This middleware provides automatic template parameter substitution using resource URIs with
full Jinja2 templating capabilities. It supports both simple parameter substitution and
complex template rendering for rich content generation using professional templating.

Key Features:
- Professional Jinja2 templating engine integration
- Resource URI resolution with property access: {{uri.property}}
- Complex template logic: {% if %}, {% for %}, {{ variable | filter }}
- Template inheritance and includes
- Automatic HTML/CSS escaping (no more f-string parsing errors!)
- Template file organization and caching
- Debug mode with clear error messages

Enhanced URI + Property Access Examples:
- {{user://current/email.email}} → "sethrivers@gmail.com" (direct property access)
- {{workspace://content/recent.content_summary.total_files}} → 42 (nested property)
- {{service://gmail/labels.0.name}} → "Important" (array access)

Traditional Examples:
- {{user://current/email}} → {"email": "sethrivers@gmail.com"} (full object)
- {% if authenticated %}Welcome {{user.name}}{% endif %} → conditional rendering
- {% for label in labels %}{{label.name}}{% endfor %} → clean loops
- {{resource://gmail/labels | length}} → Jinja2 filters

Alternative Function Syntax:
- {{resource('user://current/email', 'email')}} → same as {{user://current/email.email}}
"""

import logging
import re
import json
import ast
from typing_extensions import Any, Dict, Optional, Union, List, Tuple
from datetime import datetime
from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    DictLoader,
    Template,
    TemplateError,
    TemplateSyntaxError,
    TemplateNotFound,
    select_autoescape,
    ChainableUndefined
)

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)


class TemplateParsingError(Exception):
    """Raised when template parsing fails."""
    pass


class ResourceResolutionError(Exception):
    """Raised when resource resolution fails."""
    pass


class ResourceUndefined(ChainableUndefined):
    """
    Simple ResourceUndefined class that resolves resources from template context.
    
    When a template uses an undefined variable, this class checks if there's a
    corresponding resource in the template context and returns it.
    """
    
    def __init__(self, hint=None, obj=None, name=None, exc=None, template_context=None):
        super().__init__(hint, obj, name, exc)
        self.template_context = template_context or {}
        
    def __str__(self):
        """Return the resource if it exists in context, otherwise empty string."""
        if self.template_context and 'resources' in self.template_context:
            resources = self.template_context['resources']
            
            # Check if this is a preprocessed resource name (contains ___)
            if self._undefined_name and '___' in self._undefined_name:
                # Convert preprocessed name back to resource URI
                resource_uri, property_path = self._parse_preprocessed_name(self._undefined_name)
                
                # Try to find the resource by URI
                resource_data = None
                for context_name, data in resources.items():
                    # Check if this resource matches our URI
                    if self._context_name_matches_uri(context_name, resource_uri):
                        resource_data = data
                        break
                
                if resource_data is not None:
                    # Extract property if specified
                    if property_path:
                        result = self._extract_property_path(resource_data, property_path)
                        return str(result) if result is not None else ""
                    else:
                        # Return the resource immediately without trying to extract properties
                        # The LLM will handle indexing into objects if needed
                        if isinstance(resource_data, str):
                            return resource_data
                        elif isinstance(resource_data, (dict, list)):
                            return json.dumps(resource_data)
                        else:
                            return str(resource_data) if resource_data is not None else ""
            
            # Check direct resource match (fallback)
            if self._undefined_name in resources:
                data = resources[self._undefined_name]
                # Return the resource immediately without trying to extract properties
                if isinstance(data, str):
                    return data
                elif isinstance(data, (dict, list)):
                    return json.dumps(data)
                else:
                    return str(data) if data is not None else ""
        
        return ""
    
    def _parse_preprocessed_name(self, preprocessed_name: str) -> tuple:
        """
        Parse a preprocessed name back to resource URI and property path.
        
        Examples:
        - user___current__SLASH__email → ('user://current/email', None)
        - user___current__SLASH__email_dot_email → ('user://current/email', 'email')
        - workspace___content__SLASH__recent_dot_total_files → ('workspace://content/recent', 'total_files')
        - template___user_email → ('template://user_email', None) - preserves underscores in original URI
        """
        # Check if this has property access (_dot_ pattern)
        if '_dot_' in preprocessed_name:
            # Split on the first _dot_ occurrence
            parts = preprocessed_name.split('_dot_', 1)
            uri_part = parts[0]
            property_part = parts[1]
            
            # Convert URI part: user___current__SLASH__email → user://current/email
            # First restore the :// separator, then convert __SLASH__ back to /
            resource_uri = uri_part.replace('___', '://', 1).replace('__SLASH__', '/')
            
            # Convert property part: nested_property → nested.property
            property_path = property_part.replace('_', '.')
            
            return resource_uri, property_path
        else:
            # Simple URI without property: user___current__SLASH__email → user://current/email
            # Only convert the special delimiters, preserve original underscores
            resource_uri = preprocessed_name.replace('___', '://', 1).replace('__SLASH__', '/')
            return resource_uri, None
    
    def _context_name_matches_uri(self, context_name: str, resource_uri: str) -> bool:
        """Check if a context variable name matches a resource URI."""
        # Convert URI to expected context name and compare
        expected_name = self._uri_to_context_name(resource_uri)
        return context_name == expected_name
    
    def _uri_to_context_name(self, uri: str) -> str:
        """Convert a resource URI to a context variable name (EXACTLY matches parent class logic)."""
        # This MUST match the parent class _uri_to_context_name method exactly
        # Remove scheme and convert to valid Python identifier
        if '://' in uri:
            name = uri.split('://', 1)[1]  # Remove scheme: user://current/email → current/email
        else:
            name = uri
        
        # Replace invalid characters
        import re
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)  # current/email → current_email
        
        # Ensure it starts with letter or underscore
        if name and name[0].isdigit():
            name = f"resource_{name}"
        
        return name or "resource"
    
    def _extract_property_path(self, data: any, property_path: str) -> any:
        """Extract a property path from data object like 'email' or 'nested.deep.property'."""
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
    
    def __getattr__(self, name):
        """Support property access for chaining."""
        # Try to get the property from the resolved resource
        if self.template_context and 'resources' in self.template_context:
            resources = self.template_context['resources']
            if self._undefined_name in resources:
                data = resources[self._undefined_name]
                try:
                    if isinstance(data, dict) and name in data:
                        result = data[name]
                        return str(result) if result is not None else ""
                    elif isinstance(data, list) and name.isdigit():
                        idx = int(name)
                        if 0 <= idx < len(data):
                            result = data[idx]
                            return str(result) if result is not None else ""
                except (KeyError, IndexError, ValueError, TypeError):
                    pass
        
        # Return chainable undefined for further chaining
        return ResourceUndefined(
            name=f"{self._undefined_name}.{name}" if self._undefined_name else name,
            template_context=self.template_context
        )


class TemplateParameterMiddleware(Middleware):
    """
    Template Parameter Substitution Middleware with Jinja2 Integration.
    
    This middleware provides automatic template parameter substitution using resource URIs
    with full Jinja2 templating capabilities. It combines the power of resource resolution
    with professional templating for rich content generation.
    
    Features:
    - Resource URI resolution: {{scheme://uri}} (supports all URI schemes)
    - Full Jinja2 templating: {% if %}, {% for %}, {{ variable | filter }}
    - Automatic HTML/CSS escaping (no f-string parsing errors!)
    - Template file organization and caching
    - Professional template inheritance and includes
    """
    
    def __init__(
        self,
        # Template discovery and loading
        template_dirs: Optional[List[str]] = None,
        template_string_cache: bool = True,
        
        # Resource URI patterns  
        resource_pattern: str = r'\{\{([a-zA-Z][a-zA-Z0-9]*://[^}]+)\}\}',
        template_pattern: str = r'\{\{([^}]+)\}\}',
        
        # Jinja2 configuration
        autoescape: bool = True,
        trim_blocks: bool = True,
        lstrip_blocks: bool = True,
        
        # Caching and performance
        enable_caching: bool = True,
        cache_ttl_seconds: int = 300,
        template_cache_size: int = 400,
        
        # Security and validation
        allowed_resource_schemes: Optional[List[str]] = None,
        max_recursion_depth: int = 3,
        sandbox_mode: bool = True,
        
        # Debugging
        enable_debug_logging: bool = False,
        debug_template_source: bool = False
    ):
        """
        Initialize the Jinja2 template parameter middleware.
        
        Args:
            template_dirs: List of directories to search for template files
            template_string_cache: Enable caching of template strings
            resource_pattern: Regex for URI expressions (matches all schemes like user://, workspace://, etc.)
            template_pattern: Regex for general template expressions  
            autoescape: Enable automatic HTML/XML escaping
            trim_blocks: Remove first newline after block
            lstrip_blocks: Strip leading spaces/tabs from line start
            enable_caching: Enable resource result caching
            cache_ttl_seconds: Cache TTL in seconds
            template_cache_size: Max templates to cache
            allowed_resource_schemes: Allowed resource URI schemes
            max_recursion_depth: Max template nesting depth
            sandbox_mode: Enable Jinja2 sandboxed execution
            enable_debug_logging: Enable detailed debug logging
            debug_template_source: Log template source code
        """
        # Template loading setup
        self.template_dirs = template_dirs or [
            "templates",
            "templates/prompts", 
            "templates/tools",
            "prompts/templates"
        ]
        
        # Store Jinja2 configuration (will setup environment per-request with context)
        self.jinja_env = None
        self._jinja_config = {
            'autoescape': autoescape,
            'trim_blocks': trim_blocks,
            'lstrip_blocks': lstrip_blocks,
            'cache_size': template_cache_size,
            'sandbox_mode': sandbox_mode
        }
        
        # Pattern matching
        self.resource_pattern = re.compile(resource_pattern)
        self.template_pattern = re.compile(template_pattern)
        
        # Caching configuration
        self.enable_caching = enable_caching
        self.cache_ttl_seconds = cache_ttl_seconds
        self.template_string_cache = template_string_cache
        
        # Security settings
        self.allowed_resource_schemes = allowed_resource_schemes or [
            "user", "auth", "template", "google", "tools", "workspace", 
            "gmail", "gchat", "gsheets", "service", "drive", "calendar"
        ]
        self.max_recursion_depth = max_recursion_depth
        
        # Debug settings
        self.enable_debug_logging = enable_debug_logging
        self.debug_template_source = debug_template_source
        
        # Caches
        self._resource_cache: Dict[str, Dict[str, Any]] = {}
        self._template_string_cache: Dict[str, Template] = {}
        
        logger.info(f"🎭 TemplateParameterMiddleware with Jinja2 support initialized")
        logger.info(f"   Template directories: {self.template_dirs}")
        logger.info(f"   Autoescape: {autoescape}")
        logger.info(f"   Caching: {'enabled' if enable_caching else 'disabled'}")
        logger.info(f"   Allowed schemes: {self.allowed_resource_schemes}")
        logger.info(f"   Sandbox mode: {sandbox_mode}")
    
    def _setup_jinja2_environment_with_context(self, fastmcp_context):
        """
        Setup the Jinja2 environment with FastMCP context for resource resolution.
        
        This method creates a fresh Jinja2 environment for each request with the
        appropriate FastMCP context injected into the ResourceUndefined class.
        
        Args:
            fastmcp_context: FastMCP context for resource resolution
            
        Returns:
            Configured Jinja2 Environment instance
        """
        config = self._jinja_config
        
        # Create loaders for template discovery
        loaders = []
        
        # File system loader for template directories
        for template_dir in self.template_dirs:
            template_path = Path(template_dir)
            if template_path.exists():
                loaders.append(FileSystemLoader(str(template_path)))
        
        # Create the Jinja2 environment
        if config['sandbox_mode']:
            from jinja2.sandbox import SandboxedEnvironment
            env_class = SandboxedEnvironment
        else:
            env_class = Environment
        
        # Configure loader
        if loaders:
            from jinja2 import ChoiceLoader
            loader = ChoiceLoader(loaders)
        else:
            # Fallback to DictLoader for string templates only
            loader = DictLoader({})
        
        # Create environment with our ResourceUndefined class
        jinja_env = env_class(
            loader=loader,
            autoescape=select_autoescape(['html', 'xml']) if config['autoescape'] else False,
            trim_blocks=config['trim_blocks'],
            lstrip_blocks=config['lstrip_blocks'],
            cache_size=config['cache_size'],
            auto_reload=True,  # Reload templates when they change
            undefined=ResourceUndefined  # Use our ResourceUndefined class directly
        )
        
        # Add custom filters for FastMCP
        self._add_fastmcp_filters_to_env(jinja_env)
        
        # Add custom globals including resource function
        self._add_fastmcp_globals_to_env(jinja_env, fastmcp_context)
        
        return jinja_env
    
    def _add_fastmcp_filters_to_env(self, jinja_env):
        """Add FastMCP-specific Jinja2 filters to the provided environment."""
        
        def resource_filter(uri: str) -> str:
            """Filter to create resource URI expressions."""
            return f"{{{{resource://{uri}}}}}"
        
        def json_extract(data: Any, path: str) -> Any:
            """Filter to extract JSON data using path."""
            try:
                keys = path.strip().split('.')
                result = data
                for key in keys:
                    if isinstance(result, dict):
                        result = result.get(key)
                    elif isinstance(result, list) and key.isdigit():
                        result = result[int(key)]
                    else:
                        return None
                return result
            except Exception:
                return None
        
        def format_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
            """Filter to format datetime objects."""
            if isinstance(dt, str):
                # Try to parse string datetime
                try:
                    dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                except ValueError:
                    return dt
            return dt.strftime(format_str)
        
        def truncate_text(text: str, length: int = 100, suffix: str = "...") -> str:
            """Filter to truncate text with suffix."""
            if len(text) <= length:
                return text
            return text[:length - len(suffix)] + suffix
        
        # Register filters
        jinja_env.filters.update({
            'resource': resource_filter,
            'json_extract': json_extract,
            'format_datetime': format_datetime,
            'truncate_text': truncate_text,
        })
        
        logger.debug("🎭 Added FastMCP custom filters to Jinja2 environment")
    
    def _add_fastmcp_globals_to_env(self, jinja_env, fastmcp_context):
        """Add FastMCP-specific global variables and functions to the provided environment."""
        
        def now() -> datetime:
            """Get current datetime."""
            return datetime.now()
        
        def utc_now() -> datetime:
            """Get current UTC datetime."""
            return datetime.utcnow()
        
        def resource(uri: str, property_path: str = None):
            """
            Simple function to resolve FastMCP resources.
            
            Usage:
            - {{resource('user://current/email')}} → full resource data
            - {{resource('user://current/email', 'email')}} → just the email property
            """
            try:
                # This is a placeholder - we'll need to handle the async call differently
                # For now, return the URI as a placeholder that ResourceUndefined can handle
                if property_path:
                    return f"__resource_call__{uri}.{property_path}"
                else:
                    # Return preprocessed name that ResourceUndefined can handle
                    preprocessed = uri.replace('://', '___').replace('/', '_')
                    if property_path:
                        preprocessed += f"_dot_{property_path.replace('.', '_')}"
                    return f"{{{{{preprocessed}}}}}"
            except Exception as e:
                logger.warning(f"⚠️ Failed to resolve resource {uri}: {e}")
                return ""
        
        # Register globals
        jinja_env.globals.update({
            'now': now,
            'utc_now': utc_now,
            'datetime': datetime,
            'resource': resource,
        })
        
        logger.debug("🎭 Added FastMCP global functions to Jinja2 environment")
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Intercept tool calls and resolve template parameters using Jinja2.
        
        Args:
            context: MiddlewareContext containing tool call information
            call_next: Function to continue the middleware chain
        """
        tool_name = getattr(context.message, 'name', 'unknown')
        
        if self.enable_debug_logging:
            logger.debug(f"🎭 Processing tool call with Jinja2: {tool_name}")
        
        # Check if we have FastMCP context for resource resolution
        if not hasattr(context, 'fastmcp_context') or not context.fastmcp_context:
            logger.warning(f"⚠️ No FastMCP context available for template resolution in tool: {tool_name}")
            return await call_next(context)
        
        try:
            # Resolve template parameters if they exist
            original_args = getattr(context.message, 'arguments', {})
            if original_args:
                resolved_args = await self._resolve_template_parameters_jinja2(
                    original_args,
                    context.fastmcp_context,
                    tool_name
                )
                
                # Update the message arguments
                if resolved_args != original_args:
                    context.message.arguments = resolved_args
                    if self.enable_debug_logging:
                        logger.debug(f"🎭 Updated arguments for tool {tool_name} using Jinja2")
            
            # Continue with the tool execution
            return await call_next(context)
            
        except Exception as e:
            logger.error(f"❌ Jinja2 template resolution failed for tool {tool_name}: {e}")
            # Continue without template resolution for backwards compatibility
            logger.info(f"🎭 Continuing tool execution without Jinja2 template resolution: {tool_name}")
            return await call_next(context)
    
    async def _resolve_template_parameters_jinja2(
        self,
        parameters: Dict[str, Any],
        fastmcp_context,
        tool_name: str,
        recursion_depth: int = 0
    ) -> Dict[str, Any]:
        """
        Resolve template expressions in parameters using Jinja2.
        
        Args:
            parameters: Dictionary of parameters to resolve
            fastmcp_context: FastMCP context for resource access
            tool_name: Name of the tool being executed
            recursion_depth: Current recursion depth
            
        Returns:
            Dictionary with resolved parameters
        """
        if recursion_depth > self.max_recursion_depth:
            raise TemplateParsingError(f"Maximum recursion depth ({self.max_recursion_depth}) exceeded")
        
        # First, collect all resources needed for this template context
        template_context = await self._build_template_context(parameters, fastmcp_context, tool_name)
        
        resolved_params = {}
        
        for key, value in parameters.items():
            try:
                resolved_value = await self._resolve_parameter_value_jinja2(
                    value,
                    template_context,
                    tool_name,
                    f"{key}",
                    recursion_depth
                )
                resolved_params[key] = resolved_value
                
                if self.enable_debug_logging and resolved_value != value:
                    logger.debug(f"🎭 Jinja2 resolved parameter '{key}' in {tool_name}")
                    if self.debug_template_source:
                        logger.debug(f"   Original: {repr(value)}")
                        logger.debug(f"   Resolved: {repr(resolved_value)}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Failed to resolve parameter '{key}' in {tool_name} with Jinja2: {e}")
                # Keep original value if resolution fails
                resolved_params[key] = value
        
        return resolved_params
    
    async def _build_template_context(
        self, 
        parameters: Dict[str, Any], 
        fastmcp_context, 
        tool_name: str
    ) -> Dict[str, Any]:
        """
        Build the Jinja2 template context by pre-resolving all resources.
        
        This method scans all parameters to find resource URIs and pre-fetches
        them to build a complete context for Jinja2 template rendering.
        """
        template_context = {
            # Standard context variables
            'tool_name': tool_name,
            'timestamp': datetime.now(),
            'utc_timestamp': datetime.utcnow(),
            # Pass FastMCP context for resource resolution
            '_fastmcp_context': fastmcp_context,
        }
        
        # Find all resource URIs in the parameters
        resource_uris = set()
        self._collect_resource_uris(parameters, resource_uris)
        
        if self.enable_debug_logging:
            logger.debug(f"🎭 Found {len(resource_uris)} unique resource URIs to resolve")
        
        # Resolve all resources and add to context
        resources = {}
        for uri in resource_uris:
            try:
                resource_data = await self._get_resource_data(uri, fastmcp_context)
                
                # Add resource to context using a clean name
                resource_name = self._uri_to_context_name(uri)
                resources[resource_name] = resource_data
                
                if self.enable_debug_logging:
                    logger.debug(f"🎭 Added resource to context: {resource_name} (from {uri})")
                    
            except Exception as e:
                logger.warning(f"⚠️ Failed to resolve resource {uri}: {e}")
                # Add empty placeholder to prevent template errors
                resource_name = self._uri_to_context_name(uri)
                resources[resource_name] = None
        
        template_context['resources'] = resources
        
        # Add direct resource access for common patterns
        if 'user_current_email' in resources:
            template_context['user_email'] = resources['user_current_email']
        if 'service_gmail_labels' in resources:
            template_context['gmail_labels'] = resources['service_gmail_labels']
        if 'service_gchat_spaces' in resources:
            template_context['chat_spaces'] = resources['service_gchat_spaces']
        
        return template_context
    
    def _collect_resource_uris(self, obj: Any, resource_uris: set, visited: set = None):
        """Recursively collect all resource URIs from a data structure."""
        if visited is None:
            visited = set()
        
        # Prevent infinite recursion
        obj_id = id(obj)
        if obj_id in visited:
            return
        visited.add(obj_id)
        
        if isinstance(obj, str):
            # Find resource URI patterns
            matches = self.resource_pattern.findall(obj)
            for match in matches:
                # Extract base URI only (remove property path after first dot)
                if '.' in match and '://' in match:
                    # Split on first dot after ://
                    scheme_and_path = match.split('.', 1)[0]  # user://current/email.email -> user://current/email
                    resource_uris.add(scheme_and_path)
                else:
                    resource_uris.add(match)
                
        elif isinstance(obj, dict):
            for value in obj.values():
                self._collect_resource_uris(value, resource_uris, visited)
                
        elif isinstance(obj, list):
            for item in obj:
                self._collect_resource_uris(item, resource_uris, visited)
    
    
    def _simple_preprocess(self, template_string: str) -> str:
        """
        Simple preprocessing: convert user://current/email.email to user___current__SLASH__email_dot_email
        
        This converts resource URI syntax to valid Jinja2 variable names that ResourceUndefined can handle.
        Uses __SLASH__ delimiter to preserve underscores in the original URI.
        
        Examples:
        - {{user://current/email}} → {{user___current__SLASH__email}}
        - {{user://current/email.email}} → {{user___current__SLASH__email_dot_email}}
        - {{workspace://content/recent.total_files}} → {{workspace___content__SLASH__recent_dot_total_files}}
        - {{template://user_email}} → {{template___user_email}} (preserves underscore)
        """
        # Pattern to match resource URIs: {{scheme://path}} or {{scheme://path.property}}
        resource_pattern = r'\{\{([a-zA-Z][a-zA-Z0-9]*://[^}]+)\}\}'
        
        def replace_uri(match):
            """Convert a single resource URI to a valid variable name."""
            full_expression = match.group(1)  # Extract the full expression from {{expression}}
            
            # Convert :// to ___
            processed = full_expression.replace('://', '___')
            
            # Convert / to __SLASH__ (unique delimiter that preserves original underscores)
            processed = processed.replace('/', '__SLASH__')
            
            # Convert . to _dot_ for property access
            processed = processed.replace('.', '_dot_')
            
            return f"{{{{{processed}}}}}"
        
        # Replace all resource URI patterns
        processed = re.sub(resource_pattern, replace_uri, template_string)
        
        if self.enable_debug_logging and processed != template_string:
            logger.debug(f"🎭 Simple preprocessing applied:")
            logger.debug(f"   Original: {repr(template_string[:200])}")
            logger.debug(f"   Processed: {repr(processed[:200])}")
        
        return processed

    
    async def _resolve_parameter_value_jinja2(
        self,
        value: Any,
        template_context: Dict[str, Any],
        tool_name: str,
        param_path: str,
        recursion_depth: int
    ) -> Any:
        """
        Resolve a parameter value using Jinja2 templating.
        
        Args:
            value: The parameter value to resolve
            template_context: Pre-built context with all resources
            tool_name: Name of the tool being executed
            param_path: Path to this parameter
            recursion_depth: Current recursion depth
            
        Returns:
            The resolved parameter value
        """
        if isinstance(value, str):
            # Check if this looks like a Jinja2 template
            if self._has_template_syntax(value):
                return await self._render_jinja2_template(
                    value, template_context, tool_name, param_path
                )
            else:
                return value
                
        elif isinstance(value, dict):
            # For nested dict resolution, we need to pass the fastmcp_context from template_context
            fastmcp_context = template_context.get('_fastmcp_context')
            return await self._resolve_template_parameters_jinja2(
                value, fastmcp_context, tool_name, recursion_depth + 1
            )
            
        elif isinstance(value, list):
            resolved_list = []
            for i, item in enumerate(value):
                resolved_item = await self._resolve_parameter_value_jinja2(
                    item, template_context, tool_name, f"{param_path}[{i}]", recursion_depth
                )
                resolved_list.append(resolved_item)
            return resolved_list
            
        else:
            # Return non-string values as-is
            return value
    
    def _has_template_syntax(self, text: str) -> bool:
        """Check if a string contains Jinja2 template syntax."""
        jinja2_patterns = [
            r'\{\{.*?\}\}',      # Variables: {{ var }}
            r'\{%.*?%\}',        # Statements: {% if %}, {% for %}
            r'\{#.*?#\}',        # Comments: {# comment #}
            r'\{\{[a-zA-Z][a-zA-Z0-9]*://',   # URI patterns: {{scheme://...}}
        ]
        
        for pattern in jinja2_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    async def _render_jinja2_template(
        self,
        template_string: str,
        template_context: Dict[str, Any],
        tool_name: str,
        param_path: str
    ) -> Any:
        """
        Render a Jinja2 template string with the given context.
        
        Args:
            template_string: The template string to render
            template_context: Context data for rendering
            tool_name: Tool name for logging
            param_path: Parameter path for logging
            
        Returns:
            Rendered template result
        """
        try:
            # Create Jinja2 environment with FastMCP context for ResourceUndefined
            fastmcp_context = template_context.get('_fastmcp_context')
            jinja_env = self._setup_jinja2_environment_with_context(fastmcp_context)
            
            if self.enable_debug_logging and self.debug_template_source:
                logger.debug(f"🎭 Rendering Jinja2 template for {tool_name}.{param_path}")
                logger.debug(f"   Template: {repr(template_string[:200])}")
                logger.debug(f"   Context keys: {list(template_context.keys())}")
            
            # Simple preprocessing: convert user://current/email.email to user___current_email_dot_email
            processed_template = self._simple_preprocess(template_string)
            
            # Create template from processed string using context-aware environment
            template = self._get_template_from_env(processed_template, jinja_env)
            
            # Update template context with debug flag
            template_context['_debug_logging'] = self.enable_debug_logging
            
            # Create a custom undefined class with the current template context
            class ContextAwareResourceUndefined(ResourceUndefined):
                def __init__(self, hint=None, obj=None, name=None, exc=None):
                    super().__init__(hint, obj, name, exc, template_context)
            
            # Temporarily set the undefined class for this render
            original_undefined = jinja_env.undefined
            jinja_env.undefined = ContextAwareResourceUndefined
            
            # Render the template with ResourceUndefined handling everything
            resolved_rendered = template.render(**template_context)
            
            # Restore original undefined class
            jinja_env.undefined = original_undefined
            
            # Try to parse as JSON if it looks like JSON
            if resolved_rendered.strip().startswith(('{', '[')):
                try:
                    return json.loads(resolved_rendered)
                except json.JSONDecodeError:
                    pass  # Return as string
            
            if self.enable_debug_logging:
                logger.debug(f"🎭 Successfully rendered Jinja2 template: {len(resolved_rendered)} characters")
            
            return resolved_rendered
            
        except TemplateError as e:
            logger.error(f"❌ Jinja2 template error in {tool_name}.{param_path}: {e}")
            logger.error(f"   Template: {repr(template_string[:200])}")
            raise TemplateParsingError(f"Jinja2 template error: {e}")
            
        except Exception as e:
            logger.error(f"❌ Unexpected error rendering Jinja2 template: {e}")
            raise TemplateParsingError(f"Template rendering failed: {e}")
    
    def _get_template_from_env(self, template_string: str, jinja_env) -> Template:
        """Get a Jinja2 template from a string using the provided environment, with caching."""
        if not self.template_string_cache:
            return jinja_env.from_string(template_string)
        
        # Use template string as cache key (hashed for memory efficiency)
        import hashlib
        cache_key = hashlib.md5(template_string.encode()).hexdigest()
        
        if cache_key not in self._template_string_cache:
            template = jinja_env.from_string(template_string)
            self._template_string_cache[cache_key] = template
            
            if self.enable_debug_logging:
                logger.debug(f"🎭 Cached new Jinja2 template: {cache_key}")
        
        return self._template_string_cache[cache_key]
    
    
    # Inherit resource resolution methods from parent class
    async def _get_resource_data(self, resource_uri: str, fastmcp_context) -> Any:
        """
        Get resource data, with optional caching.
        Inherits the implementation from the base middleware.
        """
        cache_key = resource_uri
        
        # Check cache first
        if self.enable_caching and cache_key in self._resource_cache:
            cache_entry = self._resource_cache[cache_key]
            cached_time = cache_entry.get('timestamp', 0)
            if (datetime.now().timestamp() - cached_time) < self.cache_ttl_seconds:
                if self.enable_debug_logging:
                    logger.debug(f"🎭 Using cached resource: {resource_uri}")
                return cache_entry['data']
        
        try:
            # Read the resource using FastMCP context system
            if self.enable_debug_logging:
                logger.debug(f"🎭 Fetching resource: {resource_uri}")
            
            # Use the FastMCP context to read the resource
            if hasattr(fastmcp_context, 'read_resource'):
                resource_result = await fastmcp_context.read_resource(resource_uri)
            elif hasattr(fastmcp_context, 'fastmcp') and hasattr(fastmcp_context.fastmcp, 'read_resource'):
                # Access via FastMCP instance
                from fastmcp.server.dependencies import get_context
                try:
                    active_ctx = get_context()
                    resource_result = await fastmcp_context.fastmcp.read_resource(resource_uri, active_ctx)
                except RuntimeError:
                    logger.warning(f"⚠️ No active context available for resource {resource_uri}")
                    raise ResourceResolutionError(f"No active context available: {resource_uri}")
            else:
                raise ResourceResolutionError(f"FastMCP context does not provide resource access")
            
            # Extract the actual data from the resource result
            if hasattr(resource_result, 'contents') and resource_result.contents:
                content_item = resource_result.contents[0]
                
                if hasattr(content_item, 'text') and content_item.text:
                    try:
                        resource_data = json.loads(content_item.text)
                    except json.JSONDecodeError:
                        resource_data = content_item.text
                elif hasattr(content_item, 'blob') and content_item.blob:
                    resource_data = content_item.blob
                else:
                    resource_data = content_item
            else:
                resource_data = resource_result
            
            # Cache the result
            if self.enable_caching:
                self._resource_cache[cache_key] = {
                    'data': resource_data,
                    'timestamp': datetime.now().timestamp()
                }
            
            if self.enable_debug_logging:
                logger.debug(f"🎭 Successfully fetched resource: {resource_uri}")
            
            return resource_data
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch resource '{resource_uri}': {e}")
            raise ResourceResolutionError(f"Failed to fetch resource '{resource_uri}': {e}")
    
    
    # Utility methods
    def clear_cache(self):
        """Clear all caches."""
        self._resource_cache.clear()
        self._template_string_cache.clear()
        logger.info("🎭 All caches cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "resource_cache": {
                "enabled": self.enable_caching,
                "entries": len(self._resource_cache),
                "ttl_seconds": self.cache_ttl_seconds,
                "cached_resources": list(self._resource_cache.keys())
            },
            "template_cache": {
                "enabled": self.template_string_cache,
                "entries": len(self._template_string_cache),
                "templates": list(self._template_string_cache.keys())
            }
        }
    
    def add_custom_filter(self, name: str, func):
        """Add a custom Jinja2 filter (will be added to future environments)."""
        # Store for future environment setup since we create per-request environments
        if not hasattr(self, '_custom_filters'):
            self._custom_filters = {}
        self._custom_filters[name] = func
        logger.info(f"🎭 Registered custom Jinja2 filter: {name}")
    
    def add_custom_global(self, name: str, value):
        """Add a custom Jinja2 global variable (will be added to future environments)."""
        # Store for future environment setup since we create per-request environments
        if not hasattr(self, '_custom_globals'):
            self._custom_globals = {}
        self._custom_globals[name] = value
        logger.info(f"🎭 Registered custom Jinja2 global: {name}")


# Convenience function for setting up the enhanced middleware
def setup_template_middleware(
    mcp: FastMCP,
    template_dirs: Optional[List[str]] = None,
    enable_debug: bool = False,
    enable_caching: bool = True,
    cache_ttl_seconds: int = 300,
    sandbox_mode: bool = True
) -> TemplateParameterMiddleware:
    """
    Set up the Jinja2 template parameter middleware.
    
    Args:
        mcp: FastMCP server instance
        template_dirs: List of template directories to search
        enable_debug: Enable debug logging
        enable_caching: Enable resource caching
        cache_ttl_seconds: Cache TTL in seconds
        sandbox_mode: Use sandboxed Jinja2 environment
        
    Returns:
        The middleware instance
    """
    middleware = TemplateParameterMiddleware(
        template_dirs=template_dirs,
        enable_debug_logging=enable_debug,
        enable_caching=enable_caching,
        cache_ttl_seconds=cache_ttl_seconds,
        sandbox_mode=sandbox_mode
    )
    
    mcp.add_middleware(middleware)
    logger.info("✅ Template parameter middleware with Jinja2 support added to FastMCP server")
    
    return middleware