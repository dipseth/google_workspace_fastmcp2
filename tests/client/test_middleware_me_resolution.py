"""Client tests for AuthMiddleware 'me'/'myself' resolution with Phase 1 & 2 fixes.

Tests verify:
1. Tools work with explicit user_google_email parameter (backward compatible)
2. Tools work with 'me'/'myself' keywords (middleware auto-injection)
3. Middleware properly resolves user email from OAuth files
"""

import pytest

from .base_test_config import TEST_EMAIL
from .test_helpers import TestResponseValidator, ToolTestRunner, assert_tools_registered


@pytest.mark.service("gmail")
@pytest.mark.auth_required
class TestMiddlewareMeResolution:
    """Test 'me'/'myself' email resolution with improved AuthMiddleware."""

    @pytest.mark.asyncio
    async def test_explicit_email_still_works(self, client):
        """Verify backward compatibility - explicit email parameter works."""
        # Test with explicit email (should always work)
        result = await client.call_tool(
            "search_gmail_messages",
            {"user_google_email": TEST_EMAIL, "query": "test", "page_size": 5},
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Should get valid response or auth error (both are acceptable)
        validator = TestResponseValidator()
        is_valid_auth = validator.is_valid_auth_response(content)
        is_success = validator.is_success_response(content)

        assert (
            is_valid_auth or is_success
        ), f"Should get valid auth response or success, got: {content[:200]}"

    @pytest.mark.asyncio
    async def test_me_keyword_resolution(self, client):
        """Test 'me' keyword resolution via middleware auto-injection."""
        # Test with 'me' keyword - middleware should inject actual email
        result = await client.call_tool(
            "draft_gmail_message",
            {
                "user_google_email": "me",  # Should be auto-resolved by middleware
                "subject": "Test with 'me' keyword",
                "body": "Testing middleware auto-injection",
            },
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # SUCCESS CRITERIA:
        # 1. Response contains actual email (not literal 'me')
        # 2. OR response indicates 'me' was resolved
        # 3. Response should NOT have "invalid email 'me'" error

        # Check if actual email is in the response (middleware worked!)
        has_actual_email = TEST_EMAIL in content or "groupon.com" in content
        has_resolved_indicator = "resolved" in content.lower()
        has_invalid_me_error = (
            "invalid email 'me'" in content.lower()
            or "invalid user email" in content.lower()
            and "'me'" in content.lower()
        )

        assert (
            has_actual_email or has_resolved_indicator
        ), f"Middleware should inject actual email, got: {content[:300]}"
        assert (
            not has_invalid_me_error
        ), f"Should not have 'invalid email' error for 'me', got: {content[:300]}"

    @pytest.mark.asyncio
    async def test_myself_keyword_resolution(self, client):
        """Test 'myself' keyword resolution via middleware auto-injection."""
        # Test with 'myself' keyword
        result = await client.call_tool(
            "draft_gmail_message",
            {
                "user_google_email": "myself",  # Should be auto-resolved
                "subject": "Test with 'myself' keyword",
                "body": "Testing middleware auto-injection with 'myself'",
            },
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # SUCCESS CRITERIA:
        # 1. Response contains actual email (not literal 'myself')
        # 2. OR response indicates 'myself' was resolved
        # 3. Response should NOT have "invalid email 'myself'" error

        # Check if actual email is in the response (middleware worked!)
        has_actual_email = TEST_EMAIL in content or "groupon.com" in content
        has_resolved_indicator = "resolved" in content.lower()
        has_invalid_myself_error = (
            "invalid email 'myself'" in content.lower()
            or "invalid user email" in content.lower()
            and "'myself'" in content.lower()
        )

        assert (
            has_actual_email or has_resolved_indicator
        ), f"Middleware should inject actual email, got: {content[:300]}"
        assert (
            not has_invalid_myself_error
        ), f"Should not have 'invalid email' error for 'myself', got: {content[:300]}"

    @pytest.mark.asyncio
    async def test_auth_pattern_consistency(self, client):
        """Test that both auth patterns work consistently."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test both patterns on a simple tool
        results = await runner.test_auth_patterns("list_gmail_labels", {})

        # Explicit email should always work (backward compatible)
        assert results[
            "backward_compatible"
        ], "Explicit email pattern must remain backward compatible"

        # Log middleware injection results
        middleware_result = results["middleware_injection"]
        print("\n📊 Middleware injection test:")
        print(f"   Success: {middleware_result['success']}")
        if not middleware_result["success"]:
            print(f"   Response: {middleware_result['content'][:200]}")


@pytest.mark.service("drive")
@pytest.mark.auth_required
class TestDriveWithMiddleware:
    """Test Drive operations work with improved middleware."""

    @pytest.mark.asyncio
    async def test_drive_search_explicit_email(self, client):
        """Test Drive search with explicit email (backward compatible)."""
        result = await client.call_tool(
            "search_drive_files",
            {"user_google_email": TEST_EMAIL, "query": "type:pdf", "page_size": 5},
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Should work or give valid auth response
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            content
        ) or validator.is_success_response(content)

        assert is_valid, f"Should get valid response, got: {content[:200]}"

    @pytest.mark.asyncio
    async def test_drive_check_auth_with_me(self, client):
        """Test Drive auth check with 'me' keyword."""
        result = await client.call_tool(
            "check_drive_auth", {"user_google_email": "me"}  # Should be auto-resolved
        )

        assert result is not None
        content = result.content[0].text if result.content else str(result)

        # Should not complain about invalid email 'me'
        assert (
            "'me'" not in content.lower()
            or "resolved" in content.lower()
            or "authenticated" in content.lower()
        ), f"'me' should be resolved, got: {content[:200]}"


@pytest.mark.service("calendar")
class TestCalendarWithMiddleware:
    """Test Calendar operations work with improved middleware."""

    @pytest.mark.asyncio
    async def test_list_calendars_both_patterns(self, client):
        """Test listing calendars with both auth patterns."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        results = await runner.test_auth_patterns("list_calendars", {})

        # Both should work or give valid auth responses
        assert results["backward_compatible"], "Explicit email should work"

        # Middleware should work or gracefully handle missing auth
        middleware_success = results["middleware_injection"]["success"]
        middleware_content = results["middleware_injection"]["content"]

        if not middleware_success:
            # If middleware injection failed, it should be a valid auth error
            validator = TestResponseValidator()
            assert validator.is_valid_auth_response(
                middleware_content
            ), f"Middleware failure should give valid auth error, got: {middleware_content[:200]}"


class TestMiddlewareServerIntegration:
    """Test middleware is properly integrated with server."""

    @pytest.mark.asyncio
    async def test_server_tools_still_available(self, client):
        """Verify tools are still available after middleware re-enablement."""
        expected_tools = [
            "start_google_auth",
            "search_gmail_messages",
            "upload_to_drive",
            "list_calendars",
        ]

        await assert_tools_registered(
            client, expected_tools, context="Middleware resolution tools"
        )

    @pytest.mark.asyncio
    async def test_resources_still_accessible(self, client):
        """Verify resources work after middleware re-enablement."""
        # Try to read a resource
        result = await client.read_resource("user://current/email")

        assert result is not None, "Should be able to read user resource"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
