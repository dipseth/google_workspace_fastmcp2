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