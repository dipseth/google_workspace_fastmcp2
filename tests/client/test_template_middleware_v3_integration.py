"""Test Template Middleware v3 Jinja2 integration using standardized client framework."""

import pytest  # noqa: E402

pytest.skip(
    "Subset of test_template_middleware_integration (see TEST_CLEANUP_AUDIT.md)",
    allow_module_level=True,
)

import pytest

from .test_helpers import ToolTestRunner


@pytest.mark.service("template")
@pytest.mark.auth_required
class TestTemplateMiddlewareV3Integration:
    """Integration tests for Enhanced Template Middleware v3 with Jinja2 support."""

    @pytest.mark.asyncio
    async def test_template_middleware_working(self, client):
        """Test that template middleware v3 is loaded and processing templates."""
        from .base_test_config import TEST_EMAIL

        print("\n🧪 Testing Template Middleware v3 integration...")
        print(f"📧 Test email: {TEST_EMAIL}")

        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test with simple v2 template syntax first
        v2_template = "User email via v2 template: {{user://current/email}}"

        result = await runner.test_tool_with_explicit_email(
            "send_gmail_message",
            {
                "to": [TEST_EMAIL],
                "subject": "🧪 CLIENT TEST - v2 Template Middleware",
                "body": v2_template,
                "content_type": "plain",
            },
        )

        print("\n📊 v2 Template test result:")
        print(f"   Success: {result['success']}")
        print(f"   Content preview: {str(result['content'])[:200]}...")

        if result["success"]:
            content_str = str(result["content"])

            # Check if template was applied
            template_applied = (
                '"templateApplied":true' in content_str
                or '"templateApplied": true' in content_str
            )
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

        print("\n🎭 Testing Jinja2 template processing...")

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

        result = await runner.test_tool_with_explicit_email(
            "send_gmail_message",
            {
                "to": [TEST_EMAIL],
                "subject": "🧪 CLIENT TEST - Jinja2 Templates",
                "body": jinja2_template,
                "content_type": "plain",
            },
        )

        print("\n📊 Jinja2 test result:")
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

        print("\n🔀 Testing mixed template syntax (the problem case)...")

        runner = ToolTestRunner(client, TEST_EMAIL)

        # This is the exact syntax that was failing
        mixed_template = """Mixed Template Test:

v2: {{user://current/email}}

Jinja2: {% if user_email() %}Hello {{ user_email() }}!{% endif %}

Mixed complete."""

        result = await runner.test_tool_with_explicit_email(
            "send_gmail_message",
            {
                "to": [TEST_EMAIL],
                "subject": "🧪 CLIENT TEST - Mixed Templates",
                "body": mixed_template,
                "content_type": "plain",
            },
        )

        print("\n📊 Mixed template test result:")
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
    async def test_template_tracking_flag(self, client):
        """Test that templateApplied flag is correctly set to true when templates are processed."""
        from .base_test_config import TEST_EMAIL

        print("\n🏷️ Testing template tracking flag functionality...")

        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test with templates in multiple places (matching your exact working example)
        result = await runner.test_tool_with_explicit_email(
            "send_gmail_message",
            {
                "to": TEST_EMAIL,
                "subject": "{{service://gmail/labels.result.total_count}} labels",
                "body": "ok where\n{{service://gmail/labels.result.total_count}} labels\n\n\n\n\n\n\n\n\n\n\n\n\n",
                "html_body": "{{ render_calendar_dashboard(service://calendar/calendars, service://calendar/events, 'Test Dashboard') }}",
                "content_type": "mixed",
            },
        )

        print("\n📊 Template tracking flag test result:")
        print(f"   Success: {result['success']}")

        if result["success"]:
            content = result.get("content")

            # Parse JSON string response
            if isinstance(content, str):
                try:
                    import json

                    structured_content = json.loads(content)
                except json.JSONDecodeError:
                    print(f"❌ Failed to parse JSON: {content[:200]}...")
                    return False
            elif isinstance(content, dict):
                structured_content = content
            else:
                print(f"❌ Unexpected content type: {type(content)}")
                return False

            template_applied = structured_content.get("templateApplied", False)
            template_name = structured_content.get("templateName", None)

            print(f"   templateApplied: {template_applied}")
            print(f"   templateName: {template_name}")
            print(f"   Content type: {type(content)}")

            if template_applied:
                print("✅ Template tracking flag is working correctly!")
                if template_name:
                    print(f"✅ Template name is properly set: {template_name}")
                return True
            else:
                print("❌ templateApplied flag is false")
                return False
        else:
            print(f"❌ Template tracking test failed: {result['error_message']}")
            return False

    @pytest.mark.asyncio
    async def test_template_middleware_comprehensive(self, client):
        """Comprehensive test of all template middleware v3 features."""

        print("\n🚀 Running comprehensive template middleware test...")

        # Test all four scenarios now
        v2_result = await self.test_template_middleware_working(client)
        jinja2_result = await self.test_jinja2_processing(client)
        mixed_result = await self.test_mixed_template_syntax(client)
        tracking_result = await self.test_template_tracking_flag(client)

        print("\n📋 Template Middleware v3 Test Summary:")
        print(f"   v2 Templates: {'✅ Working' if v2_result else '❌ Failed'}")
        print(f"   Jinja2 Templates: {'✅ Working' if jinja2_result else '❌ Failed'}")
        print(f"   Mixed Templates: {'✅ Working' if mixed_result else '❌ Failed'}")
        print(
            f"   Template Tracking: {'✅ Working' if tracking_result else '❌ Failed'}"
        )

        if all([v2_result, jinja2_result, mixed_result, tracking_result]):
            print("\n🎉 Template Middleware v3 is FULLY WORKING!")
        elif any([v2_result, jinja2_result, mixed_result, tracking_result]):
            print("\n⚠️ Template Middleware v3 is PARTIALLY working")
        else:
            print("\n❌ Template Middleware v3 is NOT working")

        # Return True if at least basic functionality works
        return v2_result or jinja2_result
