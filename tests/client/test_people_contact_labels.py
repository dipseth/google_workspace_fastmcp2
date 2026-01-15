"""Tests for Google People contact label tools."""

import pytest

from .base_test_config import TEST_EMAIL
from .test_helpers import ToolTestRunner, print_test_result


@pytest.mark.service("people")
class TestPeopleContactLabelTools:
    """Comprehensive tests for People contact label management tools."""

    @pytest.mark.asyncio
    async def test_people_label_tools_available(self, client):
        """Ensure People contact label tools are registered."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        has_list_tool = "list_people_contact_labels" in tool_names
        has_manage_tool = "manage_people_contact_labels" in tool_names

        if not has_list_tool and not has_manage_tool:
            pytest.skip("People contact label tools not available in this server")

    @pytest.mark.asyncio
    async def test_list_people_contact_labels_explicit_email(self, client):
        """Test list_people_contact_labels with explicit email."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("list_people_contact_labels"):
            pytest.skip("list_people_contact_labels tool not available")

        result = await runner.test_tool_with_explicit_email(
            "list_people_contact_labels", {}
        )
        print_test_result("list_people_contact_labels explicit email", result)

        # Should either succeed or give a clear auth-related response
        assert (
            result["success"] or result["is_auth_related"]
        ), "list_people_contact_labels should succeed or produce an auth-related error"

        # If successful, validate response structure
        if result["success"]:
            # Response may be in 'content' or parsed from text
            import json

            response_data = result.get("content") or result.get("response")
            if isinstance(response_data, str):
                try:
                    response = json.loads(response_data)
                except (json.JSONDecodeError, TypeError):
                    pytest.skip(f"Could not parse response as JSON: {response_data}")
            else:
                response = response_data or {}

            assert "labels" in response, "Response should contain 'labels' field"
            assert (
                "total_count" in response
            ), "Response should contain 'total_count' field"
            assert isinstance(response["labels"], list), "'labels' should be a list"

    @pytest.mark.asyncio
    async def test_list_people_contact_labels_response_structure(self, client):
        """Validate the structure of list_people_contact_labels response."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("list_people_contact_labels"):
            pytest.skip("list_people_contact_labels tool not available")

        result = await runner.test_tool_with_explicit_email(
            "list_people_contact_labels", {}
        )

        if not result["success"]:
            pytest.skip("Could not test response structure - auth or API error")

        # Parse response data
        import json

        response_data = result.get("content") or result.get("response")
        if isinstance(response_data, str):
            try:
                response = json.loads(response_data)
            except (json.JSONDecodeError, TypeError):
                pytest.skip(f"Could not parse response as JSON: {response_data}")
        else:
            response = response_data or {}

        # Verify top-level structure
        assert "labels" in response
        assert "total_count" in response
        assert "user_email" in response

        # Verify each label has required fields
        for label in response["labels"]:
            assert "resourceName" in label, "Each label should have resourceName"
            assert "name" in label, "Each label should have name"
            assert "memberCount" in label, "Each label should have memberCount"
            assert "groupType" in label, "Each label should have groupType"

    @pytest.mark.asyncio
    async def test_manage_people_contact_labels_auth_patterns_label_add(self, client):
        """Test auth patterns for manage_people_contact_labels(label_add)."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("manage_people_contact_labels"):
            pytest.skip("manage_people_contact_labels tool not available")

        label_name = "MCP Test Label"

        auth_results = await runner.test_auth_patterns(
            "manage_people_contact_labels",
            {
                "action": "label_add",
                "email": TEST_EMAIL,
                "label": label_name,
            },
        )

        explicit = auth_results["explicit_email"]
        middleware = auth_results["middleware_injection"]

        print_test_result("manage_people_contact_labels explicit (label_add)", explicit)
        print_test_result(
            "manage_people_contact_labels middleware (label_add)", middleware
        )

        explicit_valid = explicit["success"] or explicit["is_auth_related"]
        middleware_valid = middleware.get("success", False) or middleware.get(
            "param_required_at_client", False
        )

        assert explicit_valid, "Explicit auth pattern should work or give auth error"
        assert middleware_valid, (
            "Middleware auth pattern should work, be auth-related, "
            "or clearly require user_google_email at client"
        )

    @pytest.mark.asyncio
    async def test_manage_people_contact_labels_label_remove(self, client):
        """Test manage_people_contact_labels with label_remove action."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("manage_people_contact_labels"):
            pytest.skip("manage_people_contact_labels tool not available")

        label_name = "MCP Test Label Remove"

        result = await runner.test_tool_with_explicit_email(
            "manage_people_contact_labels",
            {
                "action": "label_remove",
                "email": TEST_EMAIL,
                "label": label_name,
            },
        )
        print_test_result("manage_people_contact_labels (label_remove)", result)

        # Should succeed or be auth-related
        assert (
            result["success"] or result["is_auth_related"]
        ), "label_remove should succeed or produce auth-related error"

    @pytest.mark.asyncio
    async def test_manage_people_contact_labels_multiple_emails(self, client):
        """Test manage_people_contact_labels with multiple emails."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("manage_people_contact_labels"):
            pytest.skip("manage_people_contact_labels tool not available")

        label_name = "MCP Multi Email Test"
        # Use comma-separated emails
        multi_emails = f"{TEST_EMAIL},test2@example.com"

        result = await runner.test_tool_with_explicit_email(
            "manage_people_contact_labels",
            {
                "action": "label_add",
                "email": multi_emails,
                "label": label_name,
            },
        )
        print_test_result("manage_people_contact_labels (multiple emails)", result)

        # Should succeed or be auth-related
        assert (
            result["success"] or result["is_auth_related"]
        ), "Multiple email handling should succeed or produce auth-related error"

    @pytest.mark.asyncio
    async def test_manage_people_contact_labels_invalid_action(self, client):
        """Test manage_people_contact_labels with invalid action."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("manage_people_contact_labels"):
            pytest.skip("manage_people_contact_labels tool not available")

        result = await runner.test_tool_with_explicit_email(
            "manage_people_contact_labels",
            {
                "action": "invalid_action",
                "email": TEST_EMAIL,
                "label": "Test Label",
            },
        )
        print_test_result("manage_people_contact_labels (invalid action)", result)

        # Should fail with error message about unsupported action
        if result["success"]:
            response_text = str(result.get("content") or result.get("response", ""))
            assert (
                "unsupported" in response_text.lower()
                or "invalid" in response_text.lower()
            ), "Invalid action should be rejected with appropriate error message"

    @pytest.mark.asyncio
    async def test_manage_people_contact_labels_missing_label(self, client):
        """Test manage_people_contact_labels without label parameter."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("manage_people_contact_labels"):
            pytest.skip("manage_people_contact_labels tool not available")

        result = await runner.test_tool_with_explicit_email(
            "manage_people_contact_labels",
            {
                "action": "label_add",
                "email": TEST_EMAIL,
                # No label parameter
            },
        )
        print_test_result("manage_people_contact_labels (missing label)", result)

        # Should fail with error about missing label
        if result["success"]:
            response_text = str(result.get("content") or result.get("response", ""))
            assert (
                "required" in response_text.lower() or "label" in response_text.lower()
            ), "Missing label should be rejected with appropriate error message"

    @pytest.mark.asyncio
    async def test_manage_people_contact_labels_empty_email(self, client):
        """Test manage_people_contact_labels with empty email."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("manage_people_contact_labels"):
            pytest.skip("manage_people_contact_labels tool not available")

        result = await runner.test_tool_with_explicit_email(
            "manage_people_contact_labels",
            {
                "action": "label_add",
                "email": "",
                "label": "Test Label",
            },
        )
        print_test_result("manage_people_contact_labels (empty email)", result)

        # Should fail with error about missing/invalid email
        if result["success"]:
            response_text = str(result.get("content") or result.get("response", ""))
            assert (
                "email" in response_text.lower() or "required" in response_text.lower()
            ), "Empty email should be rejected with appropriate error message"

    @pytest.mark.asyncio
    async def test_manage_people_contact_labels_scope_verification(self, client):
        """Verify that proper scopes are required for contact group management."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        if not await runner.test_tool_availability("manage_people_contact_labels"):
            pytest.skip("manage_people_contact_labels tool not available")

        label_name = "MCP Scope Test Label"

        result = await runner.test_tool_with_explicit_email(
            "manage_people_contact_labels",
            {
                "action": "label_add",
                "email": TEST_EMAIL,
                "label": label_name,
            },
        )

        # If it fails with auth error, check that it mentions scopes
        if not result["success"] and result.get("is_auth_related"):
            error_text = str(result.get("error", "")).lower()
            # Should mention scopes or permissions
            assert (
                "scope" in error_text or "permission" in error_text
            ), "Auth errors should clearly indicate scope/permission issues"
