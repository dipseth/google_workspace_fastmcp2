# Enhanced Template Middleware - Modular Architecture

## Overview

The Enhanced Template Middleware has been refactored from a monolithic 2526-line file into a modular architecture with focused, maintainable components. This document describes the new architecture, components, and how to work with the refactored system.

## Architecture Benefits

- **Maintainability**: No single file exceeds 500 lines
- **Testability**: Components can be tested in isolation
- **Reusability**: Filters and utilities available for other uses
- **Modularity**: Easy to add new filters or modify components
- **Performance**: Maintained caching and optimization features
- **Backward Compatibility**: 100% compatible with existing code

## Directory Structure

```
middleware/
├── template_middleware.py              # Backward compatibility layer
├── template_middleware_refactored.py   # Main refactored middleware class
├── namespace_converter.py              # Utility for dot notation access
├── filters/                            # Custom Jinja2 filters
│   ├── __init__.py                    # Filter registration
│   ├── date_filters.py                # Date/time formatting filters
│   ├── data_filters.py                # Data manipulation filters
│   ├── json_filters.py                # JSON processing filters
│   └── drive_filters.py               # Google Drive URL filters
└── template_core/                      # Core template processing
    ├── __init__.py                    # Component exports
    ├── utils.py                       # Exception classes and utilities
    ├── cache_manager.py               # TTL-based resource caching
    ├── resource_handler.py            # Resource fetching and processing
    ├── jinja_environment.py           # Jinja2 environment management
    ├── template_processor.py          # Template detection and processing
    └── macro_manager.py               # Template macro discovery
```

## Core Components

### 1. Cache Manager (`template_core/cache_manager.py`)
**Purpose**: TTL-based caching system for resource data  
**Key Features**:
- Configurable TTL (time-to-live) for cached resources
- Cache statistics and monitoring
- Memory-efficient storage with automatic expiration
- Thread-safe operations

**Usage**:
```python
from middleware.template_core import CacheManager

cache = CacheManager(enable_caching=True, cache_ttl_seconds=300)
cache.cache_resource("user://current/email", {"email": "user@example.com"})
cached_data = cache.get_cached_resource("user://current/email")
stats = cache.get_cache_stats()
```

### 2. Resource Handler (`template_core/resource_handler.py`)
**Purpose**: Fetches and processes FastMCP resources  
**Key Features**:
- Resource URI resolution
- Property extraction with dot notation
- Error handling and fallbacks
- Integration with cache manager

**Usage**:
```python
from middleware.template_core import ResourceHandler, CacheManager

cache = CacheManager()
handler = ResourceHandler(cache, enable_debug_logging=True)

# Fetch resource
data = await handler.fetch_resource("user://current/profile", fastmcp_context)

# Extract nested properties
email = handler.extract_property(data, "user.email")
```

### 3. Jinja2 Environment Manager (`template_core/jinja_environment.py`)
**Purpose**: Manages Jinja2 template environment setup  
**Key Features**:
- Safe Jinja2 environment configuration
- Custom filter registration
- Global function setup
- Template macro loading

**Usage**:
```python
from middleware.template_core import JinjaEnvironmentManager
from middleware.filters import register_all_filters

manager = JinjaEnvironmentManager()
if manager.is_available():
    env = manager.setup_jinja2_environment()
    register_all_filters(env)  # Add custom filters
```

### 4. Template Processor (`template_core/template_processor.py`)
**Purpose**: Core template processing and routing logic  
**Key Features**:
- Automatic template type detection (simple vs Jinja2)
- Resource URI preprocessing
- Mixed template support
- Context building for template rendering

**Usage**:
```python
from middleware.template_core import TemplateProcessor

processor = TemplateProcessor(resource_handler, jinja_manager)
result = await processor.resolve_string_templates(
    "Hello {{user://current/email}}", 
    fastmcp_context, 
    "parameter_name"
)
```

### 5. Macro Manager (`template_core/macro_manager.py`)
**Purpose**: Template macro discovery and management  
**Key Features**:
- Scans template files for macro definitions
- Handles `template://macros` resource URIs
- Provides usage examples for discovered macros
- Caches macro information

### Template Loading and Service Process

The template system follows a structured initialization and service flow orchestrated by the main middleware:

#### 1. Initialization Flow ([`template_middleware.py`](../middleware/template_middleware.py#L110))

```python
def _initialize_components(self, jinja2_options: Dict[str, Any]) -> None:
    # Component initialization in dependency order:
    
    # 1. Cache Manager (no dependencies)
    self.cache_manager = CacheManager(...)
    
    # 2. Resource Handler (depends on cache manager) 
    self.resource_handler = ResourceHandler(cache_manager=self.cache_manager, ...)
    
    # 3. Jinja Environment Manager (independent)
    self.jinja_env_manager = JinjaEnvironmentManager(templates_dir=self.templates_dir, ...)
    
    # 4. Register custom filters
    register_all_filters(jinja_env)
    
    # 5. Template Processor (depends on resource handler + jinja env)
    self.template_processor = TemplateProcessor(
        resource_handler=self.resource_handler,
        jinja_env_manager=self.jinja_env_manager, ...
    )
    
    # 6. Macro Manager (depends on jinja env manager)
    self.macro_manager = MacroManager(
        templates_dir=self.templates_dir,
        jinja_env_manager=self.jinja_env_manager, ...
    )
    
    # 7. Scan and register all macros
    self.macro_manager.scan_and_register_macros()
```

#### 2. Macro Discovery ([`macro_manager.py`](../middleware/template_core/macro_manager.py#L51))

```python
def scan_and_register_macros(self) -> None:
    # Regex patterns for macro detection
    macro_pattern = re.compile(r'{% macro (\w+)\s*\([^}]*?\) %?}', re.MULTILINE | re.DOTALL)
    usage_example_pattern = re.compile(r'{#[^#]*MACRO USAGE EXAMPLE:[^#]*{{ (\w+)\([^}]*\) }}[^#]*#}')
    
    # Scan all .j2 files in templates directory
    for template_file in self.templates_dir.glob('*.j2'):
        template_content = template_file.read_text(encoding='utf-8')
        
        # Find macro definitions and usage examples
        macro_matches = macro_pattern.findall(template_content)
        usage_matches = usage_example_pattern.findall(template_content)
        
        # Register each discovered macro in _macro_registry
        for macro_name in macro_matches:
            self._macro_registry[macro_name] = {
                "name": macro_name,
                "template_file": template_file.name,
                "usage_example": usage_examples.get(macro_name, f"{{{{ {macro_name}() }}}}"),
                # ... additional metadata
            }
```

#### 3. Template Service During Tool Calls ([`template_middleware.py`](../middleware/template_middleware.py#L160))

```python
async def on_call_tool(self, context: MiddlewareContext, call_next) -> Any:
    # 1. Intercept tool call and extract parameters
    original_args = getattr(context.message, 'arguments', {})
    
    # 2. Resolve template parameters using TemplateProcessor
    resolved_args = await self._resolve_parameters(original_args, context.fastmcp_context, tool_name)
    
    # 3. Update tool arguments with resolved templates
    if resolved_args != original_args:
        context.message.arguments = resolved_args
        
    # 4. Continue with original tool execution
    result = await call_next(context)
```

#### 4. Template Processing ([`template_processor.py`](../middleware/template_core/template_processor.py#L70))

```python
async def resolve_string_templates(self, text: str, fastmcp_context, param_path: str) -> Any:
    # 1. Detect template type
    has_jinja2 = self._has_jinja2_syntax(text)
    has_simple = bool(self.SIMPLE_TEMPLATE_PATTERN.search(text))
    
    # 2. Route to appropriate engine
    if has_jinja2 and self.jinja_env_manager.is_available():
        return await self._resolve_jinja2_template(text, fastmcp_context, param_path)
    elif has_simple:
        return await self._resolve_simple_template(text, fastmcp_context, param_path)
    else:
        return text
```

#### 5. Resource Resolution Integration

Templates access FastMCP resources through the [`ResourceHandler`](../middleware/template_core/resource_handler.py):

```python
# Simple template resolution
resource_data = await self.resource_handler.fetch_resource(resource_uri, fastmcp_context)

# Jinja2 template context building
context = await self._build_template_context(fastmcp_context)
template = jinja_env.from_string(processed_template_text)
result = template.render(**context)
```

#### 6. Template Resource URIs ([`macro_manager.py`](../middleware/template_core/macro_manager.py#L131))

The macro manager handles `template://macros` resource URIs:

```python
async def handle_template_resource(self, resource_uri: str, fastmcp_context) -> bool:
    if resource_uri == 'template://macros':
        # Return all available macros with usage examples
        await self._handle_all_macros(fastmcp_context)
        
    elif resource_uri.startswith('template://macros/'):
        # Return specific macro usage example
        macro_name = resource_uri.replace('template://macros/', '')
        await self._handle_specific_macro(macro_name, fastmcp_context)
```

#### 7. Error Handling and Fallbacks

The system implements graceful degradation:

- **Template Loading Errors**: Invalid templates are logged and skipped ([`macro_manager.py:127`](../middleware/template_core/macro_manager.py#L127))
- **Jinja2 Unavailable**: Falls back to simple template processing ([`template_processor.py:167`](../middleware/template_core/template_processor.py#L167))
- **Resource Resolution Fails**: Uses cached data or empty fallbacks ([`template_processor.py:342`](../middleware/template_core/template_processor.py#L342))
- **Syntax Errors**: Detailed logging with fallback to original values ([`template_processor.py:212`](../middleware/template_core/template_processor.py#L212))

#### 8. Component Dependencies

```
template_middleware.py (Main Orchestrator)
├── macro_manager.py (Template Discovery)
│   └── jinja_environment.py (Jinja2 Setup)
├── template_processor.py (Template Resolution)
│   ├── resource_handler.py (Resource Fetching)
│   │   └── cache_manager.py (Caching)
│   └── jinja_environment.py (Jinja2 Setup)
└── filters/ (Custom Jinja2 Filters)
```

### Template Loading Process

1. **Discovery**: [`MacroManager.scan_and_register_macros()`](../middleware/template_core/macro_manager.py#L51) scans `middleware/templates/*.j2`
2. **Loading**: [`JinjaEnvironmentManager._load_template_macros()`](../middleware/template_core/jinja_environment.py) loads template files
3. **Registration**: Macros are registered in `jinja_env.globals` for use
4. **Validation**: Templates with syntax errors are logged and skipped
5. **Caching**: Macro information cached for `template://macros` resources
## Custom Filters

### Date Filters (`filters/date_filters.py`)
- `format_date(date, format)`: Format date with strftime
- `strftime(date, format)`: Alias for format_date

### Data Filters (`filters/data_filters.py`)
- `extract(data, path)`: Extract nested properties (e.g., "user.profile.name")
- `safe_get(dict, key, default)`: Safe dictionary access with fallback
- `map_list(list, property)`: Extract property from list of objects

### JSON Filters (`filters/json_filters.py`)
- `json_pretty(data, indent=2)`: Pretty-print JSON with indentation

### Drive Filters (`filters/drive_filters.py`)
- `format_drive_image_url(url)`: Convert Drive URLs to direct image URLs

## Template Usage and Construction

### Template File Organization

Templates are stored in the `middleware/templates/` directory and automatically discovered by the [`MacroManager`](../middleware/template_core/macro_manager.py). The system supports two types of templates:

```
middleware/templates/
├── beautiful_email.j2         # Email template with themes and styling
├── email_card.j2              # Gmail labels visualization template
├── document_templates.j2       # Professional document templates
├── photo_album_email.j2        # Photo gallery email templates
└── *.j2                       # Additional Jinja2 template files
```

### Template Macro Definition

Templates must define macros using proper Jinja2 syntax. The [`JinjaEnvironmentManager`](../middleware/template_core/jinja_environment.py) loads these templates and registers macros globally.

**✅ Correct Macro Definition**:
```jinja2
{% macro render_beautiful_email(title="Hello World") -%}
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title>
</head>
<body>
    <h1>{{ title }}</h1>
    <p>This is a simple email template.</p>
</body>
</html>
{%- endmacro %}
```

**❌ Common Mistakes**:
```jinja2
{# DON'T: Single-line macro definitions cause parsing errors #}
{% macro broken_macro() %}<!DOCTYPE html><html>...</html>{% endmacro %}

{# DON'T: Using undefined functions or filters #}
{% macro broken_dates() %}{{ now().strftime('%Y-%m-%d') }}{% endmacro %}

{# DON'T: Using custom filters that aren't registered #}
{% macro broken_filter() %}{{ image.url | format_drive_image_url }}{% endmacro %}
```

### Template Syntax Requirements

Based on fixes applied to [`beautiful_email.j2`](../middleware/templates/beautiful_email.j2) and [`document_templates.j2`](../middleware/templates/document_templates.j2):

**Safe Jinja2 Features** (Always work):
- Basic control structures: `{% if %}`, `{% for %}`, `{% set %}`
- Built-in filters: `default`, `upper`, `lower`, `length`, `defined`
- Python operators: `%` for string formatting
- Simple variable access: `{{ variable.property }}`

**Avoid These Patterns** (Cause undefined errors):
- `now()` function - Use static dates instead
- `strftime` filter - Use static date strings
- Custom filters without registration - Only use registered filters
- Python methods in templates - `{{ string.endswith('x') }}`
- Complex calculations - Pre-compute in Python

### Macro Discovery and Registration

The [`MacroManager`](../middleware/template_core/macro_manager.py) automatically scans template files using regex patterns:

```python
# Regex pattern used for macro detection
macro_pattern = re.compile(r'{% macro (\w+)\s*\([^}]*?\) %?}', re.MULTILINE | re.DOTALL)
usage_example_pattern = re.compile(r'{#[^#]*MACRO USAGE EXAMPLE:[^#]*{{ (\w+)\([^}]*\) }}[^#]*#}', re.DOTALL)
```

**Adding Usage Examples**:
```jinja2
{% macro my_template(title="Default") -%}
<!-- template content -->
{%- endmacro %}

{# MACRO USAGE EXAMPLE: {{ my_template(title="Custom Title") }} #}
```

### Working Template Examples

#### Email Template ([`email_card.j2`](../middleware/templates/email_card.j2))
```jinja2
{% macro render_gmail_labels_chips(labels_data, title="Gmail Labels") %}
<!-- Handles nested data structures safely -->
{% if labels_data and labels_data.result %}
  {% set all_labels = labels_data.result.labels or [] %}
{% endif %}

<!-- Uses only built-in filters -->
{% for label in all_labels | sort(attribute='name') %}
  <div class="label-chip">{{ label.name }}</div>
{% endfor %}
{% endmacro %}
```

#### Document Template ([`document_templates.j2`](../middleware/templates/document_templates.j2))
```jinja2
{% macro generate_invoice_doc(invoice_number="", total=0) %}
<!DOCTYPE html>
<html>
<body>
  <!-- Uses safe string formatting -->
  <p>Invoice #: {{ invoice_number }}</p>
  <p>Total: ${{ "%.2f" % total }}</p>
  
  <!-- Uses static dates instead of now() -->
  <p>Date: {{ invoice_date or '2024-12-19' }}</p>
</body>
</html>
{% endmacro %}
```

### Template Construction Best Practices

1. **Keep Macros Simple**: Avoid complex logic, use Python for data preparation
2. **Use Static Fallbacks**: Replace dynamic functions with static defaults
3. **Test Incrementally**: Start simple, add complexity gradually
4. **Document Parameters**: Include clear usage examples in comments
5. **Validate Syntax**: Ensure templates load without Jinja2 errors

### Integration with Resource System

Templates can access FastMCP resources using the established URI patterns:

```jinja2
{% macro user_dashboard() %}
<!-- Access user information -->
<h1>Welcome {{ user://current/profile.name | default('User') }}!</h1>

<!-- Access service data -->
{% for label in service://gmail/labels %}
  <span class="label">{{ label.name }}</span>
{% endfor %}

<!-- Access recent items -->
{% for file in recent://drive/5 %}
  <div class="file">{{ file.name }}</div>
{% endfor %}
{% endmacro %}
```

### Template Loading Process

1. **Discovery**: [`MacroManager.scan_and_register_macros()`](../middleware/template_core/macro_manager.py#L51) scans `middleware/templates/*.j2`
2. **Loading**: [`JinjaEnvironmentManager._load_template_macros()`](../middleware/template_core/jinja_environment.py) loads template files
3. **Registration**: Macros are registered in `jinja_env.globals` for use
4. **Validation**: Templates with syntax errors are logged and skipped
5. **Caching**: Macro information cached for `template://macros` resources

### Debugging Template Issues

**Enable Debug Logging**:
```python
middleware = EnhancedTemplateMiddleware(enable_debug_logging=True)
```

**Check Template Loading**:
```bash
# Look for these log messages during startup
⚠️ Failed to load template beautiful_email.j2: [error details]
📚 Discovered X macros from Y template files
```

**Test Template Syntax**:
```python
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('middleware/templates'))
try:
    template = env.get_template('your_template.j2')
    module = template.make_module()
    print("✅ Template loaded successfully")
except Exception as e:
    print(f"❌ Template error: {e}")
```

## Usage Examples

### Basic Template Processing
```python
from middleware.template_middleware import EnhancedTemplateMiddleware

# Initialize with default settings
middleware = EnhancedTemplateMiddleware()

# Or with custom configuration
middleware = EnhancedTemplateMiddleware(
    enable_caching=True,
    cache_ttl_seconds=600,
    enable_debug_logging=True
)
```

### Adding Custom Filters
```python
# Create a new filter file: middleware/filters/my_filters.py
def my_custom_filter(value, param=None):
    """My custom filter implementation."""
    return value.upper() if param == 'upper' else value.lower()

# Register in middleware/filters/__init__.py
def register_all_filters(jinja_env):
    """Register all custom filters with the Jinja2 environment."""
    # Existing registrations...
    
    # Add your custom filter
    from .my_filters import my_custom_filter
    jinja_env.filters['my_custom'] = my_custom_filter
```

### Template Syntax Examples

**Simple Templates (v2 compatibility)**:
```
Hello {{user://current/email}}
Your labels: {{service://gmail/labels}}
```

**Jinja2 Templates**:
```jinja2
{% if user://current/profile.name %}
Hello {{ user://current/profile.name | title }}!
{% else %}
Hello there!
{% endif %}

{% for label in service://gmail/labels %}
- {{ label.name }} ({{ label.messagesTotal }} messages)
{% endfor %}
```

**Mixed Templates**:
```jinja2
User: {{user://current/email}}
Recent files: {% for file in recent://drive %}{{ file.name }}{% endfor %}
```

## Migration Guide

### From Monolithic to Modular

**Before** (importing from monolithic file):
```python
from middleware.template_middleware import EnhancedTemplateMiddleware
```

**After** (same import still works):
```python
from middleware.template_middleware import EnhancedTemplateMiddleware  # ✅ Still works!
```

### Accessing Individual Components

**New capability** (access modular components):
```python
from middleware.template_core import (
    CacheManager,
    ResourceHandler,
    JinjaEnvironmentManager,
    TemplateProcessor,
    MacroManager
)

from middleware.filters import register_all_filters
from middleware.filters.data_filters import extract_filter
```

### Testing Individual Components

```python
# Test individual components in isolation
def test_cache_manager():
    cache = CacheManager()
    cache.cache_resource("test://uri", {"data": "value"})
    assert cache.get_cached_resource("test://uri") == {"data": "value"}

def test_custom_filter():
    from middleware.filters.data_filters import extract_filter
    data = {"user": {"name": "John"}}
    assert extract_filter(data, "user.name") == "John"
```

## Performance Considerations

### Caching
- Resource data is cached with configurable TTL (default: 300 seconds)
- Cache statistics available via `get_cache_stats()`
- Memory usage optimized with automatic cleanup

### Template Processing
- Automatic routing between simple and Jinja2 engines
- Resource URI preprocessing reduces redundant API calls
- Context building optimized for common use cases

### Debug Logging
- Detailed logging available with `enable_debug_logging=True`
- Performance metrics included in cache statistics
- Template processing steps logged for troubleshooting

## Error Handling

### Graceful Degradation
- Jinja2 unavailable → falls back to simple templates
- Resource resolution fails → uses cached data or empty fallbacks
- Template syntax errors → detailed logging with fallback processing

### Custom Exceptions
- `TemplateResolutionError`: Resource fetching failures
- `SilentUndefined`: Jinja2 undefined variable handling
- All exceptions preserve original error context

## Development Guidelines

### Adding New Filters
1. Create filter function in appropriate `filters/*.py` file
2. Add registration in `filters/__init__.py`
3. Add tests in `tests/test_template_middleware_integration.py`
4. Update documentation

### Adding New Components
1. Create module in `template_core/`
2. Add exports to `template_core/__init__.py`
3. Integrate with main middleware class
4. Add comprehensive tests
5. Update documentation

### Testing
- Run integration tests: `uv run python -m pytest tests/test_template_middleware_integration.py -v`
- Test individual components in isolation
- Verify backward compatibility with existing templates

## Troubleshooting

### Common Issues

**Import Errors**:
- Ensure all `__init__.py` files are present
- Check Python path and module structure

**Template Processing Issues**:
- Enable debug logging: `enable_debug_logging=True`
- Check cache statistics for resource resolution issues
- Verify template syntax with simple test cases

**Performance Issues**:
- Review cache TTL settings
- Monitor cache hit rates via `get_cache_stats()`
- Consider disabling debug logging in production

### Debug Information

```python
# Get detailed system information
middleware = EnhancedTemplateMiddleware(enable_debug_logging=True)
stats = middleware.get_cache_stats()
print(f"Cache enabled: {stats['enabled']}")
print(f"Total entries: {stats['total_entries']}")
print(f"Valid entries: {stats['valid_entries']}")
```

## Future Enhancements

### Planned Features
- Additional filter categories (string, math, formatting)
- Plugin system for external filter registration
- Template compilation caching
- Advanced macro system with parameters

### Extension Points
- Custom resource handlers
- Additional template engines
- Custom caching backends
- Filter parameter validation

---

*This architecture documentation covers the modular Enhanced Template Middleware system. For implementation details, see the individual component files and integration tests.*