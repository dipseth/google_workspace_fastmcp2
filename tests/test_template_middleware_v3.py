"""
Test suite for Enhanced Template Middleware v3 with Jinja2 support.

Tests both simple templating (v2 compatibility) and advanced Jinja2 features.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

# Test imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from middleware.template_middleware import (
    EnhancedTemplateMiddleware,
    setup_enhanced_template_middleware,
    JINJA2_AVAILABLE
)


class TestEnhancedTemplateMiddleware:
    """Test the enhanced template middleware functionality."""
    
    @pytest.fixture
    def middleware(self):
        """Create middleware instance for testing."""
        return EnhancedTemplateMiddleware(
            enable_caching=True,
            cache_ttl_seconds=300,
            enable_debug_logging=True
        )
    
    @pytest.fixture
    def mock_fastmcp_context(self):
        """Create a mock FastMCP context."""
        context = MagicMock()
        context.read_resource = AsyncMock()
        return context
    
    @pytest.fixture
    def sample_user_data(self):
        """Sample user resource data."""
        return {
            "email": "test@example.com",
            "session_id": "test-session-123",
            "authenticated": True,
            "timestamp": "2025-01-01T12:00:00Z"
        }
    
    @pytest.fixture
    def sample_gmail_data(self):
        """Sample Gmail labels resource data."""
        return {
            "service": "gmail",
            "count": 25,
            "items": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "SENT", "name": "SENT", "type": "system"},
                {"id": "DRAFT", "name": "DRAFT", "type": "system"},
                {"id": "Label_1", "name": "Work", "type": "user"},
                {"id": "Label_2", "name": "Personal", "type": "user"}
            ]
        }
    
    # ===== Template Detection Tests =====
    
    def test_simple_template_detection(self, middleware):
        """Test detection of simple templates."""
        simple_templates = [
            "{{user://current/email.email}}",
            "Hello {{user://current/email.email}}!",
            "{{service://gmail/labels.result.total_count}} labels"
        ]
        
        for template in simple_templates:
            has_simple = bool(middleware.SIMPLE_TEMPLATE_PATTERN.search(template))
            has_jinja2 = middleware._has_jinja2_syntax(template)
            assert has_simple, f"Should detect simple template: {template}"
            assert not has_jinja2, f"Should not detect Jinja2 in simple template: {template}"
    
    def test_jinja2_template_detection(self, middleware):
        """Test detection of Jinja2 templates."""
        jinja2_templates = [
            "{% if user.authenticated %}Welcome!{% endif %}",
            "{{ user.email | upper }}",
            "{{ range(5) | join(', ') }}",
            "{# This is a comment #}",
            "{{ user_email() }}"
        ]
        
        for template in jinja2_templates:
            has_jinja2 = middleware._has_jinja2_syntax(template)
            assert has_jinja2, f"Should detect Jinja2 syntax: {template}"
    
    # ===== Simple Template Tests (V2 Compatibility) =====
    
    @pytest.mark.asyncio
    async def test_simple_template_resolution(self, middleware, mock_fastmcp_context, sample_user_data):
        """Test simple template resolution (v2 compatibility)."""
        # Mock resource response
        from mcp.server.lowlevel.helper_types import ReadResourceContents
        mock_response = ReadResourceContents(
            content=json.dumps(sample_user_data),
            mime_type='application/json'
        )
        mock_fastmcp_context.read_resource.return_value = mock_response
        
        # Test single template resolution
        result = await middleware._resolve_simple_template(
            "{{user://current/email.email}}",
            mock_fastmcp_context,
            "test.param"
        )
        assert result == "test@example.com"
        
        # Test template in larger string
        result = await middleware._resolve_simple_template(
            "Hello {{user://current/email.email}}!",
            mock_fastmcp_context,
            "test.greeting"
        )
        assert result == "Hello test@example.com!"
    
    @pytest.mark.asyncio
    async def test_property_extraction(self, middleware, sample_gmail_data):
        """Test property extraction from nested data."""
        # Test simple property
        result = middleware._extract_property(sample_gmail_data, "service")
        assert result == "gmail"
        
        # Test array access
        result = middleware._extract_property(sample_gmail_data, "items.0.name")
        assert result == "INBOX"
        
        # Test deep nesting
        result = middleware._extract_property(sample_gmail_data, "items.3.type")
        assert result == "user"
        
        # Test missing property
        result = middleware._extract_property(sample_gmail_data, "nonexistent.property")
        assert result is None
    
    # ===== Jinja2 Template Tests =====
    
    @pytest.mark.skipif(not JINJA2_AVAILABLE, reason="Jinja2 not available")
    @pytest.mark.asyncio
    async def test_jinja2_basic_functionality(self, middleware, mock_fastmcp_context):
        """Test basic Jinja2 functionality."""
        # Test control structures
        template = "{% if true %}Hello World!{% endif %}"
        result = await middleware._resolve_jinja2_template(template, mock_fastmcp_context, "test")
        assert result == "Hello World!"
        
        # Test loops
        template = "{% for i in range(3) %}{{ i }}{% endfor %}"
        result = await middleware._resolve_jinja2_template(template, mock_fastmcp_context, "test")
        assert result == "012"
        
        # Test filters
        template = "{{ 'hello world' | title }}"
        result = await middleware._resolve_jinja2_template(template, mock_fastmcp_context, "test")
        assert result == "Hello World"
    
    @pytest.mark.skipif(not JINJA2_AVAILABLE, reason="Jinja2 not available")
    @pytest.mark.asyncio
    async def test_custom_filters(self, middleware, mock_fastmcp_context):
        """Test custom Jinja2 filters."""
        # Test json_pretty filter
        data = {"name": "test", "value": 123}
        template = f"{{{{ {data} | json_pretty }}}}"
        result = await middleware._resolve_jinja2_template(template, mock_fastmcp_context, "test")
        assert '"name": "test"' in result
        
        # Test format_date filter
        template = "{{ '2025-01-01T12:00:00Z' | format_date('%Y-%m-%d') }}"
        result = await middleware._resolve_jinja2_template(template, mock_fastmcp_context, "test")
        assert result == "2025-01-01"
    
    # ===== Resource Resolution Tests =====
    
    @pytest.mark.asyncio
    async def test_resource_caching(self, middleware, mock_fastmcp_context, sample_user_data):
        """Test resource caching functionality."""
        from mcp.server.lowlevel.helper_types import ReadResourceContents
        mock_response = ReadResourceContents(
            content=json.dumps(sample_user_data),
            mime_type='application/json'
        )
        mock_fastmcp_context.read_resource.return_value = mock_response
        
        # First call should fetch from context
        result1 = await middleware._fetch_resource("user://current/email", mock_fastmcp_context)
        assert result1 == sample_user_data
        assert mock_fastmcp_context.read_resource.call_count == 1
        
        # Second call should use cache
        result2 = await middleware._fetch_resource("user://current/email", mock_fastmcp_context)
        assert result2 == sample_user_data
        assert mock_fastmcp_context.read_resource.call_count == 1  # No additional calls
        
        # Verify cache stats
        stats = middleware.get_cache_stats()
        assert stats["total_entries"] == 1
        assert stats["valid_entries"] == 1
        assert "user://current/email" in stats["cached_uris"]
    
    @pytest.mark.asyncio
    async def test_complex_resource_structure_unwrapping(self, middleware):
        """Test unwrapping of complex nested resource structures."""
        # Test simple unwrapping - should unwrap 'data' wrapper
        nested_data = {"data": {"email": "test@example.com"}}
        result = middleware._extract_resource_data(nested_data)
        assert result == {"email": "test@example.com"}
        
        # Test deep unwrapping
        deeply_nested = {"response": {"data": {"user": {"email": "test@example.com"}}}}
        result = middleware._extract_resource_data(deeply_nested)
        # Should unwrap the response wrapper
        expected = {"data": {"user": {"email": "test@example.com"}}}
        assert result == expected
        
        # Test non-wrapper structure (should not unwrap)
        multi_key = {"email": "test@example.com", "name": "Test User"}
        result = middleware._extract_resource_data(multi_key)
        assert result == multi_key
        
        # Test that our current logic preserves single wrapper keys when they're not wrapper-like
        non_wrapper = {"user": {"email": "test@example.com"}}
        result = middleware._extract_resource_data(non_wrapper)
        # Should not unwrap 'user' since it's not in wrapper_keys
        assert result == non_wrapper
    
    # ===== Integration Tests =====
    
    @pytest.mark.asyncio
    async def test_mixed_template_resolution(self, middleware, mock_fastmcp_context, sample_user_data):
        """Test resolution of mixed simple and complex content."""
        from mcp.server.lowlevel.helper_types import ReadResourceContents
        mock_response = ReadResourceContents(
            content=json.dumps(sample_user_data),
            mime_type='application/json'
        )
        mock_fastmcp_context.read_resource.return_value = mock_response
        
        # Test parameters dictionary
        params = {
            "simple_template": "{{user://current/email.email}}",
            "complex_string": "User: {{user://current/email.email}}, Session: {{user://current/email.session_id}}",
            "nested_dict": {
                "user_info": "{{user://current/email.email}}",
                "metadata": {
                    "authenticated": "{{user://current/email.authenticated}}"
                }
            },
            "array_data": [
                "{{user://current/email.email}}",
                "{{user://current/email.session_id}}"
            ],
            "no_template": "plain text"
        }
        
        resolved = await middleware._resolve_parameters(
            params,
            mock_fastmcp_context,
            "test_tool"
        )
        
        assert resolved["simple_template"] == "test@example.com"
        assert resolved["complex_string"] == "User: test@example.com, Session: test-session-123"
        assert resolved["nested_dict"]["user_info"] == "test@example.com"
        assert resolved["nested_dict"]["metadata"]["authenticated"] == True
        assert resolved["array_data"][0] == "test@example.com"
        assert resolved["array_data"][1] == "test-session-123"
        assert resolved["no_template"] == "plain text"
    
    # ===== Error Handling Tests =====
    
    @pytest.mark.asyncio
    async def test_graceful_error_handling(self, middleware, mock_fastmcp_context):
        """Test graceful handling of errors."""
        # Mock resource resolution failure
        mock_fastmcp_context.read_resource.side_effect = Exception("Resource not found")
        
        # Should not raise exception, should return original template
        with pytest.raises(Exception):  # Template resolution error should be raised
            await middleware._fetch_resource("invalid://resource", mock_fastmcp_context)
    
    @pytest.mark.asyncio
    async def test_missing_property_handling(self, middleware, sample_user_data):
        """Test handling of missing properties."""
        # Test missing property returns None
        result = middleware._extract_property(sample_user_data, "nonexistent")
        assert result is None
        
        # Test missing nested property returns None
        result = middleware._extract_property(sample_user_data, "user.profile.name")
        assert result is None
        
        # Test invalid array index returns None
        result = middleware._extract_property({"items": [1, 2, 3]}, "items.10")
        assert result is None
    
    # ===== Performance Tests =====
    
    def test_cache_management(self, middleware):
        """Test cache management functionality."""
        # Test cache stats for empty cache
        stats = middleware.get_cache_stats()
        assert stats["total_entries"] == 0
        assert stats["valid_entries"] == 0
        
        # Add some test data to cache
        test_data = {"test": "data"}
        middleware._cache_resource("test://uri", test_data)
        
        # Verify cache stats
        stats = middleware.get_cache_stats()
        assert stats["total_entries"] == 1
        assert stats["valid_entries"] == 1
        assert "test://uri" in stats["cached_uris"]
        
        # Test cache clearing
        middleware.clear_cache()
        stats = middleware.get_cache_stats()
        assert stats["total_entries"] == 0


# ===== Integration Test for Real Usage =====

def test_setup_function():
    """Test the setup function."""
    from unittest.mock import MagicMock
    
    mock_mcp = MagicMock()
    middleware = setup_enhanced_template_middleware(
        mock_mcp,
        enable_caching=True,
        cache_ttl_seconds=600,
        enable_debug=True
    )
    
    assert isinstance(middleware, EnhancedTemplateMiddleware)
    assert middleware.enable_caching is True
    assert middleware.cache_ttl_seconds == 600
    assert middleware.enable_debug_logging is True
    mock_mcp.add_middleware.assert_called_once_with(middleware)


# ===== Example Usage Demonstration =====

class TestExampleUsage:
    """Demonstrate example usage patterns."""
    
    @pytest.mark.asyncio
    async def test_simple_email_template_example(self):
        """Example: Simple email template."""
        middleware = EnhancedTemplateMiddleware(enable_debug_logging=True)
        
        # Mock context and data
        mock_context = MagicMock()
        mock_context.read_resource = AsyncMock()
        
        from mcp.server.lowlevel.helper_types import ReadResourceContents
        user_data = {
            "email": "john.doe@company.com",
            "name": "John Doe",
            "department": "Engineering"
        }
        
        mock_context.read_resource.return_value = ReadResourceContents(
            content=json.dumps(user_data),
            mime_type='application/json'
        )
        
        # Simple template
        template = "Hello {{user://current/profile.name}}, your email is {{user://current/profile.email}}"
        
        result = await middleware._resolve_string_templates(
            template,
            mock_context,
            "email.body"
        )
        
        expected = "Hello John Doe, your email is john.doe@company.com"
        assert result == expected
    
    @pytest.mark.skipif(not JINJA2_AVAILABLE, reason="Jinja2 not available")
    @pytest.mark.asyncio
    async def test_advanced_jinja2_example(self):
        """Example: Advanced Jinja2 template with logic."""
        middleware = EnhancedTemplateMiddleware(enable_debug_logging=True)
        mock_context = MagicMock()
        
        # Advanced template with conditions and loops
        template = """
        {% if user.authenticated -%}
        Welcome back, {{ user.name | title }}!
        
        Your recent activity:
        {% for i in range(3) -%}
        - Activity {{ i + 1 }}: {{ now.strftime('%Y-%m-%d') }}
        {% endfor %}
        {%- else -%}
        Please log in to continue.
        {%- endif %}
        """
        
        result = await middleware._resolve_jinja2_template(
            template,
            mock_context,
            "dashboard.welcome"
        )
        
        # Should contain welcome message and activity list
        assert "Welcome back" in result or "Please log in" in result


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])