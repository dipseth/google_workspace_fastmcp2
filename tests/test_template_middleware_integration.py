"""
Integration tests for the refactored template middleware.

Tests the modular architecture to ensure all components work together
correctly and maintain backward compatibility.
"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, AsyncMock
from pathlib import Path

# Import the main middleware (backward compatibility test)
from middleware.template_middleware import (
    EnhancedTemplateMiddleware,
    setup_enhanced_template_middleware,
    TemplateResolutionError,
    SilentUndefined
)

# Import modular components for direct testing
from middleware.template_core import (
    CacheManager,
    ResourceHandler,
    JinjaEnvironmentManager,
    TemplateProcessor,
    MacroManager
)

# Import filters
from middleware.filters import register_all_filters
from middleware.filters.date_filters import format_date_filter, strftime_filter
from middleware.filters.data_filters import extract_filter, safe_get_filter, map_list_filter
from middleware.filters.json_filters import json_pretty_filter
from middleware.filters.drive_filters import format_drive_image_url_filter


class TestBackwardCompatibility:
    """Test that all existing imports and functionality still work."""
    
    def test_imports_work(self):
        """Test that all expected classes can be imported."""
        # These imports should work exactly as before
        assert EnhancedTemplateMiddleware is not None
        assert setup_enhanced_template_middleware is not None
        assert TemplateResolutionError is not None
        assert SilentUndefined is not None
    
    def test_middleware_initialization(self):
        """Test that the middleware can be initialized with default parameters."""
        middleware = EnhancedTemplateMiddleware()
        
        # Verify all modular components are initialized
        assert middleware.cache_manager is not None
        assert middleware.resource_handler is not None
        assert middleware.jinja_env_manager is not None
        assert middleware.template_processor is not None
        assert middleware.macro_manager is not None
        
        # Verify backward compatibility methods exist
        assert hasattr(middleware, 'clear_cache')
        assert hasattr(middleware, 'get_cache_stats')
    
    def test_setup_function_compatibility(self):
        """Test that the setup function works as expected."""
        mock_mcp = Mock()
        
        middleware = setup_enhanced_template_middleware(mock_mcp)
        
        # Verify middleware was added to mock MCP
        mock_mcp.add_middleware.assert_called_once_with(middleware)
        assert isinstance(middleware, EnhancedTemplateMiddleware)


class TestCacheManager:
    """Test the cache manager module."""
    
    def test_cache_manager_initialization(self):
        """Test cache manager initialization."""
        cache_manager = CacheManager(enable_caching=True, cache_ttl_seconds=300)
        
        assert cache_manager.enable_caching is True
        assert cache_manager.cache_ttl_seconds == 300
    
    def test_cache_operations(self):
        """Test basic cache operations."""
        cache_manager = CacheManager()
        
        # Test caching a resource
        cache_manager.cache_resource("test://uri", {"data": "value"})
        
        # Test retrieving cached resource
        cached = cache_manager.get_cached_resource("test://uri")
        assert cached == {"data": "value"}
        
        # Test cache miss
        missed = cache_manager.get_cached_resource("nonexistent://uri")
        assert missed is None
    
    def test_cache_stats(self):
        """Test cache statistics."""
        cache_manager = CacheManager()
        
        # Add some test data
        cache_manager.cache_resource("test1://uri", {"data": "value1"})
        cache_manager.cache_resource("test2://uri", {"data": "value2"})
        
        stats = cache_manager.get_cache_stats()
        
        assert stats["enabled"] is True
        assert stats["total_entries"] == 2
        assert stats["valid_entries"] == 2
        assert "test1://uri" in stats["cached_uris"]
        assert "test2://uri" in stats["cached_uris"]


class TestJinjaFilters:
    """Test all custom Jinja2 filters."""
    
    def test_date_filters(self):
        """Test date formatting filters."""
        test_date = datetime(2023, 12, 25, 10, 30, 45)
        
        # Test format_date_filter
        formatted = format_date_filter(test_date, '%Y-%m-%d')
        assert formatted == '2023-12-25'
        
        # Test strftime_filter
        formatted = strftime_filter(test_date, '%B %d, %Y')
        assert formatted == 'December 25, 2023'
    
    def test_data_filters(self):
        """Test data manipulation filters."""
        test_data = {
            'user': {
                'profile': {
                    'name': 'John Doe',
                    'email': 'john@example.com'
                }
            }
        }
        
        # Test extract_filter
        name = extract_filter(test_data, 'user.profile.name')
        assert name == 'John Doe'
        
        # Test safe_get_filter
        email = safe_get_filter(test_data['user']['profile'], 'email', 'default')
        assert email == 'john@example.com'
        
        missing = safe_get_filter(test_data, 'missing', 'default')
        assert missing == 'default'
        
        # Test map_list_filter
        items = [{'name': 'item1'}, {'name': 'item2'}]
        names = map_list_filter(items, 'name')
        assert names == ['item1', 'item2']
    
    def test_json_filter(self):
        """Test JSON formatting filter."""
        test_data = {'key': 'value', 'number': 42}
        
        formatted = json_pretty_filter(test_data, 2)
        expected = json.dumps(test_data, indent=2, default=str)
        assert formatted == expected
    
    def test_drive_filter(self):
        """Test Google Drive URL formatting filter."""
        # Test various Drive URL formats
        file_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        
        # Test /file/d/ format
        drive_url = f"https://drive.google.com/file/d/{file_id}/view"
        formatted = format_drive_image_url_filter(drive_url)
        expected = f"https://drive.google.com/uc?export=view&id={file_id}"
        assert formatted == expected
        
        # Test just file ID
        formatted = format_drive_image_url_filter(file_id)
        assert formatted == expected


class TestJinjaEnvironmentManager:
    """Test Jinja2 environment management."""
    
    def test_jinja_environment_setup(self):
        """Test Jinja2 environment initialization."""
        manager = JinjaEnvironmentManager()
        
        if manager.is_available():
            env = manager.setup_jinja2_environment()
            assert env is not None
            
            # Test that basic functions are available
            assert 'now' in env.globals
            assert 'len' in env.globals
    
    def test_filter_registration(self):
        """Test custom filter registration."""
        manager = JinjaEnvironmentManager()
        
        if manager.is_available():
            env = manager.setup_jinja2_environment()
            
            # Register our custom filters
            register_all_filters(env)
            
            # Verify filters are registered
            assert 'extract' in env.filters
            assert 'safe_get' in env.filters
            assert 'format_date' in env.filters
            assert 'json_pretty' in env.filters


@pytest.mark.asyncio
class TestResourceHandler:
    """Test resource handling functionality."""
    
    async def test_resource_handler_initialization(self):
        """Test resource handler initialization."""
        cache_manager = CacheManager()
        handler = ResourceHandler(cache_manager, enable_debug_logging=True)
        
        assert handler.cache_manager is cache_manager
        assert handler.enable_debug_logging is True
    
    async def test_property_extraction(self):
        """Test property extraction from data structures."""
        cache_manager = CacheManager()
        handler = ResourceHandler(cache_manager)
        
        test_data = {
            'user': {
                'profile': {
                    'name': 'John Doe',
                    'contacts': ['email1@example.com', 'email2@example.com']
                }
            }
        }
        
        # Test nested property extraction
        name = handler.extract_property(test_data, 'user.profile.name')
        assert name == 'John Doe'
        
        # Test array indexing
        email = handler.extract_property(test_data, 'user.profile.contacts.0')
        assert email == 'email1@example.com'
        
        # Test missing property
        missing = handler.extract_property(test_data, 'user.missing.property')
        assert missing is None


@pytest.mark.asyncio
class TestTemplateProcessor:
    """Test the main template processing logic."""
    
    async def test_template_processor_initialization(self):
        """Test template processor initialization."""
        cache_manager = CacheManager()
        resource_handler = ResourceHandler(cache_manager)
        jinja_manager = JinjaEnvironmentManager()
        
        processor = TemplateProcessor(
            resource_handler=resource_handler,
            jinja_env_manager=jinja_manager,
            enable_debug_logging=True
        )
        
        assert processor.resource_handler is resource_handler
        assert processor.jinja_env_manager is jinja_manager
        assert processor.enable_debug_logging is True
    
    def test_jinja2_syntax_detection(self):
        """Test Jinja2 syntax detection."""
        cache_manager = CacheManager()
        resource_handler = ResourceHandler(cache_manager)
        jinja_manager = JinjaEnvironmentManager()
        processor = TemplateProcessor(resource_handler, jinja_manager)
        
        # Test Jinja2 syntax detection
        assert processor._has_jinja2_syntax("{% if user %}")
        assert processor._has_jinja2_syntax("{{ name | upper }}")
        assert processor._has_jinja2_syntax("{# comment #}")
        
        # Test resource URI detection (these ARE detected as Jinja2 by design)
        assert processor._has_jinja2_syntax("{{user://current/email}}")
        assert processor._has_jinja2_syntax("{{service://gmail/labels}}")
        
        # Test plain text (should not trigger Jinja2)
        assert not processor._has_jinja2_syntax("Hello world")
        assert not processor._has_jinja2_syntax("No templates here")
        
        # Test property access (should trigger Jinja2)
        assert processor._has_jinja2_syntax("{{user://current/profile.name}}")


@pytest.mark.asyncio
class TestIntegration:
    """Test full integration scenarios."""
    
    async def test_full_middleware_initialization(self):
        """Test that the complete middleware initializes all components correctly."""
        middleware = EnhancedTemplateMiddleware(
            enable_caching=True,
            cache_ttl_seconds=300,
            enable_debug_logging=True
        )
        
        # Verify all components are properly initialized and connected
        assert middleware.cache_manager is not None
        assert middleware.resource_handler is not None
        assert middleware.jinja_env_manager is not None
        assert middleware.template_processor is not None
        assert middleware.macro_manager is not None
        
        # Verify components are properly wired together
        assert middleware.resource_handler.cache_manager is middleware.cache_manager
        assert middleware.template_processor.resource_handler is middleware.resource_handler
        assert middleware.template_processor.jinja_env_manager is middleware.jinja_env_manager
    
    @pytest.mark.asyncio
    async def test_backward_compatibility_methods(self):
        """Test that backward compatibility methods work correctly."""
        middleware = EnhancedTemplateMiddleware()
        
        # Test cache methods
        stats = middleware.get_cache_stats()
        assert isinstance(stats, dict)
        assert 'enabled' in stats
        assert 'total_entries' in stats
        
        # Test cache clearing
        middleware.clear_cache()  # Should not raise any errors
    
    def test_modular_file_structure(self):
        """Test that all expected files were created in the correct locations."""
        middleware_dir = Path(__file__).parent.parent / 'middleware'
        
        # Test core module files
        core_dir = middleware_dir / 'template_core'
        assert core_dir.exists()
        assert (core_dir / '__init__.py').exists()
        assert (core_dir / 'utils.py').exists()
        assert (core_dir / 'cache_manager.py').exists()
        assert (core_dir / 'resource_handler.py').exists()
        assert (core_dir / 'jinja_environment.py').exists()
        assert (core_dir / 'template_processor.py').exists()
        assert (core_dir / 'macro_manager.py').exists()
        
        # Test filter module files
        filters_dir = middleware_dir / 'filters'
        assert filters_dir.exists()
        assert (filters_dir / '__init__.py').exists()
        assert (filters_dir / 'date_filters.py').exists()
        assert (filters_dir / 'data_filters.py').exists()
        assert (filters_dir / 'json_filters.py').exists()
        assert (filters_dir / 'drive_filters.py').exists()
        
        # Test main middleware files
        assert (middleware_dir / 'template_middleware.py').exists()
        assert (middleware_dir / 'template_middleware_refactored.py').exists()


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])