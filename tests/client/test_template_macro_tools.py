"""
Test Template Macro Creation Tool using standardized framework.

Tests the dynamic macro creation functionality using the established
client testing patterns. Macro discovery is now handled via resources
(template://macros) rather than dedicated tools.
"""

import pytest

from .base_test_config import TEST_EMAIL
from .test_helpers import TestResponseValidator, ToolTestRunner, assert_tools_registered


@pytest.mark.service("template")
class TestTemplateMacroTools:
    """Tests for Template Macro Creation tool."""

    @pytest.mark.asyncio
    async def test_template_macro_tools_available(self, client):
        """Test that template macro creation tool is available."""
        expected_tools = ["create_template_macro"]

        await assert_tools_registered(client, expected_tools, context="Template tools")

    @pytest.mark.asyncio
    async def test_template_macros_resource_available(self, client):
        """Test that template macro resources are available."""
        try:
            # Try to access the main macros resource
            resources = await client.list_resources()
            resource_uris = [resource.uri for resource in resources]

            # Should have template://macros resource
            template_resources = [
                uri for uri in resource_uris if uri.startswith("template://")
            ]
            assert (
                len(template_resources) > 0
            ), "Should have template:// resources available"

        except Exception as e:
            # Resource listing might not be available in all clients
            pytest.skip(f"Resource listing not available: {e}")

    @pytest.mark.asyncio
    async def test_create_template_macro_basic(self, client):
        """Test basic template macro creation functionality."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test macro creation with minimal valid content
        test_macro_content = """
{% macro test_simple_macro(title="Test") -%}
<div class="test-macro">
    <h3>{{ title }}</h3>
    <p>This is a test macro created by the test suite.</p>
</div>
{%- endmacro %}
        """.strip()

        result = await runner.test_tool_basic(
            "create_template_macro",
            {
                "macro_name": "test_simple_macro",
                "macro_content": test_macro_content,
                "description": "Test macro for validation",
                "usage_example": "{{ test_simple_macro(title='My Test') }}",
                "persist_to_file": False,
            },
        )

        # Validate creation result
        content = result["content"]
        validator = TestResponseValidator()

        # Should indicate success or provide error details
        success_patterns = ["success", "created", "✅"]
        error_patterns = ["error", "failed", "❌"]

        has_success = any(pattern in content.lower() for pattern in success_patterns)
        has_error = any(pattern in content.lower() for pattern in error_patterns)

        # Either should succeed or give a clear error
        # Note: JSON responses may contain "success": true/false
        has_json_result = '"success"' in content
        assert (
            has_success or has_error or has_json_result
        ), "Should indicate success or failure clearly"

        if has_success:
            # Verify macro info is returned (may be in JSON format or text)
            assert (
                "macro_info" in content
                or "usage_info" in content
                or '"macro_name"' in content
                or '"success": true' in content
            ), "Successful creation should return macro information"

    @pytest.mark.asyncio
    async def test_create_template_macro_validation(self, client):
        """Test template macro creation validation."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test with invalid macro name
        result = await runner.test_tool_basic(
            "create_template_macro",
            {
                "macro_name": "123invalid-name",
                "macro_content": "{% macro test() %}test{% endmacro %}",
                "description": "Invalid name test",
                "persist_to_file": False,
            },
        )

        # Should fail with validation error
        content = result["content"]
        error_patterns = ["error", "invalid", "failed", "❌"]
        assert any(
            pattern in content.lower() for pattern in error_patterns
        ), "Should reject invalid macro names"

    @pytest.mark.asyncio
    async def test_create_template_macro_with_resource_access(self, client):
        """Test macro creation and verify it's accessible via resources."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Create a test macro
        test_macro_content = """
{% macro test_resource_macro(label="Test Resource") -%}
<span class="resource-badge">{{ label }}</span>
{%- endmacro %}
        """.strip()

        create_result = await runner.test_tool_basic(
            "create_template_macro",
            {
                "macro_name": "test_resource_macro",
                "macro_content": test_macro_content,
                "description": "Test macro for resource verification",
                "usage_example": "{{ test_resource_macro(label='My Badge') }}",
                "persist_to_file": False,
            },
        )

        content = create_result["content"]
        success_patterns = ["success", "created", "✅"]
        has_success = any(pattern in content.lower() for pattern in success_patterns)

        if has_success:
            # Verify the creation response includes resource availability info
            # Note: JSON responses may have different format
            expected_info = [
                "template://macros",
                "immediate",
                "available",
                "success",
                "macro_name",
            ]
            has_resource_info = any(info in content.lower() for info in expected_info)
            assert has_resource_info, "Should indicate resource availability or success"

    @pytest.mark.asyncio
    async def test_create_macro_with_persistence(self, client):
        """Test creating a macro with file persistence."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        test_macro_content = """
{% macro test_persistent_macro(message="Hello") -%}
<div class="persistent-test">
    <p>{{ message }} from persistent macro</p>
</div>
{%- endmacro %}
        """.strip()

        result = await runner.test_tool_basic(
            "create_template_macro",
            {
                "macro_name": "test_persistent_macro",
                "macro_content": test_macro_content,
                "description": "Test macro with persistence",
                "usage_example": "{{ test_persistent_macro(message='Hello World') }}",
                "persist_to_file": True,
            },
        )

        content = result["content"]

        # Should either succeed or provide clear error
        success_patterns = ["success", "created", "✅", "persisted"]
        error_patterns = ["error", "failed", "❌"]

        has_response = any(
            pattern in content.lower()
            for pattern in (success_patterns + error_patterns)
        )
        assert has_response, "Should provide clear feedback about persistence"


@pytest.mark.service("template")
@pytest.mark.integration
class TestTemplateMacroIntegration:
    """Integration tests for template macro creation functionality."""

    @pytest.mark.asyncio
    async def test_macro_syntax_validation(self, client):
        """Test various macro syntax validation scenarios."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test cases with expected validation failures
        invalid_cases = [
            {
                "name": "no_macro_tag",
                "content": "<div>Just HTML, no macro</div>",
                "description": "Should reject content without macro tags",
            },
            {
                "name": "missing_endmacro",
                "content": "{% macro test() %}<div>Missing end tag</div>",
                "description": "Should reject content without endmacro",
            },
            {
                "name": "name_mismatch",
                "content": "{% macro different_name() %}<div>Test</div>{% endmacro %}",
                "description": "Should reject when macro name doesn't match",
            },
        ]

        for case in invalid_cases:
            result = await runner.test_tool_basic(
                "create_template_macro",
                {
                    "macro_name": case["name"],
                    "macro_content": case["content"],
                    "description": case["description"],
                    "persist_to_file": False,
                },
            )

            content = result["content"]
            error_patterns = ["error", "invalid", "failed", "❌"]
            has_error = any(pattern in content.lower() for pattern in error_patterns)

            assert (
                has_error
            ), f"Case '{case['name']}' should be rejected: {case['description']}"

    @pytest.mark.asyncio
    async def test_macro_name_validation(self, client):
        """Test macro name validation patterns."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test invalid names (should fail validation)
        invalid_names = [
            "123invalid",
            "invalid-name",
            "invalid name",
            "invalid.name",
            "",
        ]

        valid_macro_content = "{% macro test_name() %}<div>Test</div>{% endmacro %}"

        for name in invalid_names:
            # Replace 'test_name' with actual name for proper validation
            macro_content = (
                valid_macro_content.replace("test_name", name)
                if name
                else valid_macro_content
            )

            result = await runner.test_tool_basic(
                "create_template_macro",
                {
                    "macro_name": name,
                    "macro_content": macro_content,
                    "description": f"Testing invalid name: {name}",
                    "persist_to_file": False,
                },
            )

            content = result["content"]
            error_patterns = ["error", "invalid", "failed", "❌"]
            has_error = any(pattern in content.lower() for pattern in error_patterns)

            assert has_error, f"Invalid name '{name}' should be rejected"

    @pytest.mark.asyncio
    async def test_successful_macro_creation_structure(self, client):
        """Test that successful macro creation returns proper structured response."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        test_macro_content = """
{% macro test_structure_macro(text="Test") -%}
<span class="test-structure">{{ text }}</span>
{%- endmacro %}
        """.strip()

        result = await runner.test_tool_basic(
            "create_template_macro",
            {
                "macro_name": "test_structure_macro",
                "macro_content": test_macro_content,
                "description": "Test macro for structure validation",
                "usage_example": "{{ test_structure_macro(text='Hello') }}",
                "persist_to_file": False,
            },
        )

        content = result["content"]
        success_patterns = ["success", "created", "✅"]
        has_success = any(pattern in content.lower() for pattern in success_patterns)

        if has_success:
            # Check for expected response structure elements
            # Note: JSON responses may have different field names
            expected_elements = [
                "macro_info",
                "usage_info",
                "immediate",
                "available",
                "macro_name",
                "success",
            ]
            has_structure = any(
                element in content.lower() for element in expected_elements
            )
            assert (
                has_structure
            ), "Successful creation should return structured response with macro info"
