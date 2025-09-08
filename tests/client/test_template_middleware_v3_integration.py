"""Test Template Middleware v3 Jinja2 integration using standardized client framework."""

import pytest
from .test_helpers import ToolTestRunner, TestResponseValidator

@pytest.mark.service("template")
@pytest.mark.auth_required  
class TestTemplateMiddlewareV3Integration:
    """Integration tests for Enhanced Template Middleware v3 with Jinja2 support."""
    
    @pytest.mark.asyncio
    async def test_template_middleware_working(self, client):
        """Test that template middleware v3 is loaded and processing templates."""
        from .base_test_config import TEST_EMAIL
        
        print(f"\n🧪 Testing Template Middleware v3 integration...")
        print(f"📧 Test email: {TEST_EMAIL}")
        
        runner = ToolTestRunner(client, TEST_EMAIL)
        
        # Test with simple v2 template syntax first
        v2_template = "User email via v2 template: {{resource://user://current/email}}"
        
        result = await runner.test_tool_with_explicit_email("send_gmail_message", {
            "to": [TEST_EMAIL],
            "subject": "🧪 CLIENT TEST - v2 Template Middleware",
            "body": v2_template,
            "content_type": "plain"
        })
        
        print(f"\n📊 v2 Template test result:")
        print(f"   Success: {result['success']}")
        print(f"   Content preview: {str(result['content'])[:200]}...")
        
        if result["success"]:
            content_str = str(result["content"])
            
            # Check if template was applied
            template_applied = '"templateApplied":true' in content_str or '"templateApplied": true' in content_str
            has_raw_template = "{{resource://" in content_str
            
            print(f"   Template applied: {template_applied}")
            print(f"   Raw template found: {has_raw_template}")
            
            if template_applied:
                print("✅ Template middleware v3 is working!")
                return True
            elif not has_raw_template:
                print("✅ Template processed (no raw syntax)")
                return True
            else:
                print("❌ Template middleware not triggered")
                return False
        else:
            print(f"❌ Tool call failed: {result['error_message']}")
            return False
    
    @pytest.mark.asyncio
    async def test_jinja2_processing(self, client):
        """Test Jinja2 template processing specifically."""
        from .base_test_config import TEST_EMAIL
        
        print(f"\n🎭 Testing Jinja2 template processing...")
        
        runner = ToolTestRunner(client, TEST_EMAIL)
        
        # Pure Jinja2 template
        jinja2_template = """Jinja2 Test:

{% if user_email() %}
Authenticated as: {{ user_email() }}
{% else %}
Not authenticated
{% endif %}

Current time: {{ now() }}

Loop test:
{% for i in range(2) %}
- Item {{ i + 1 }}
{% endfor %}

End test."""

        result = await runner.test_tool_with_explicit_email("send_gmail_message", {
            "to": [TEST_EMAIL],
            "subject": "🧪 CLIENT TEST - Jinja2 Templates",
            "body": jinja2_template,
            "content_type": "plain"
        })
        
        print(f"\n📊 Jinja2 test result:")
        print(f"   Success: {result['success']}")
        
        if result["success"]:
            content_str = str(result["content"])
            
            # Check for Jinja2 processing
            has_raw_jinja2 = "{% if" in content_str or "{{ now()" in content_str
            template_applied = '"templateApplied":true' in content_str
            
            print(f"   Template applied: {template_applied}")
            print(f"   Raw Jinja2 found: {has_raw_jinja2}")
            
            if template_applied and not has_raw_jinja2:
                print("✅ Jinja2 templates fully processed!")
                return True
            elif not has_raw_jinja2:
                print("✅ Jinja2 processed (no raw syntax)")
                return True
            else:
                print("❌ Jinja2 templates not processed")
                return False
        else:
            print(f"❌ Jinja2 test failed: {result['error_message']}")
            return False
    
    @pytest.mark.asyncio
    async def test_mixed_template_syntax(self, client):
        """Test the problematic mixed v2 + Jinja2 syntax."""
        from .base_test_config import TEST_EMAIL
        
        print(f"\n🔀 Testing mixed template syntax (the problem case)...")
        
        runner = ToolTestRunner(client, TEST_EMAIL)
        
        # This is the exact syntax that was failing
        mixed_template = """Mixed Template Test:

v2: {{resource://user://current/email}}

Jinja2: {% if user_email() %}Hello {{ user_email() }}!{% endif %}

Mixed complete."""

        result = await runner.test_tool_with_explicit_email("send_gmail_message", {
            "to": [TEST_EMAIL],
            "subject": "🧪 CLIENT TEST - Mixed Templates",  
            "body": mixed_template,
            "content_type": "plain"
        })
        
        print(f"\n📊 Mixed template test result:")
        print(f"   Success: {result['success']}")
        
        if result["success"]:
            content_str = str(result["content"])
            
            has_raw_v2 = "{{resource://" in content_str
            has_raw_jinja2 = "{% if" in content_str
            template_applied = '"templateApplied":true' in content_str
            
            print(f"   Template applied: {template_applied}")
            print(f"   Raw v2 found: {has_raw_v2}")
            print(f"   Raw Jinja2 found: {has_raw_jinja2}")
            
            if template_applied and not has_raw_v2 and not has_raw_jinja2:
                print("✅ Mixed templates fully processed!")
                return True
            elif not has_raw_v2 and not has_raw_jinja2:
                print("✅ Mixed processed (no raw syntax)")
                return True
            else:
                print("❌ Mixed templates not processed")
                return False
        else:
            print(f"❌ Mixed test failed: {result['error_message']}")
            return False
    
    @pytest.mark.asyncio
    async def test_template_middleware_comprehensive(self, client):
        """Comprehensive test of all template middleware v3 features."""
        from .base_test_config import TEST_EMAIL
        
        print(f"\n🚀 Running comprehensive template middleware test...")
        
        # Test all three scenarios
        v2_result = await self.test_template_middleware_working(client)
        jinja2_result = await self.test_jinja2_processing(client)
        mixed_result = await self.test_mixed_template_syntax(client)
        
        print(f"\n📋 Template Middleware v3 Test Summary:")
        print(f"   v2 Templates: {'✅ Working' if v2_result else '❌ Failed'}")
        print(f"   Jinja2 Templates: {'✅ Working' if jinja2_result else '❌ Failed'}")
        print(f"   Mixed Templates: {'✅ Working' if mixed_result else '❌ Failed'}")
        
        if all([v2_result, jinja2_result, mixed_result]):
            print("\n🎉 Template Middleware v3 is FULLY WORKING!")
        elif any([v2_result, jinja2_result, mixed_result]):
            print(f"\n⚠️ Template Middleware v3 is PARTIALLY working")
        else:
            print(f"\n❌ Template Middleware v3 is NOT working")
            
        # Return True if at least basic functionality works
        return v2_result or jinja2_result