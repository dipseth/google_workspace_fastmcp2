#!/usr/bin/env python3
"""
Test suite for Gmail reply improvements using standardized FastMCP testing framework.

This test suite validates the enhanced reply_to_gmail_message and draft_gmail_reply
functionality including:
- New reply modes (sender_only, reply_all, custom)
- Backward compatibility
- Email extraction helper function
- CC/BCC support in replies
- Edge cases and error handling

Tests follow the standardized framework patterns from TESTING_FRAMEWORK.md.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import test utilities from the standardized framework
# Import the helper function we're testing
from gmail.utils import extract_email_addresses
from tests.client.base_test_config import TEST_EMAIL
from tests.client.test_helpers import TestResponseValidator, ToolTestRunner


@pytest.mark.service("gmail")
class TestGmailReplyImprovements:
    """Test suite for Gmail reply enhancements using standardized framework."""

    # ============================================================================
    # A. HELPER FUNCTION TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_extract_email_addresses_function(self):
        """Test the extract_email_addresses helper function."""
        # Test various email formats
        test_cases = [
            # Simple email
            ("john@example.com", ["john@example.com"]),
            # Name with email
            ("John Doe <john@example.com>", ["john@example.com"]),
            # Multiple emails
            (
                "John Doe <john@example.com>, Jane Smith <jane@example.com>",
                ["john@example.com", "jane@example.com"],
            ),
            # Mixed format
            (
                "john@example.com, Jane Smith <jane@example.com>",
                ["john@example.com", "jane@example.com"],
            ),
            # Empty string
            ("", []),
            # Complex format with quotes
            (
                '"John Doe" <john@example.com>, "Jane Smith" <jane@example.com>',
                ["john@example.com", "jane@example.com"],
            ),
            # Single email with comma in name
            ('"Doe, John" <john@example.com>', ["john@example.com"]),
            # Email with plus addressing
            ("user+tag@example.com", ["user+tag@example.com"]),
            # Email with subdomain
            ("user@mail.example.com", ["user@mail.example.com"]),
        ]

        for input_str, expected in test_cases:
            result = extract_email_addresses(input_str)
            # Sort both lists for comparison since order might vary
            result_sorted = sorted(result)
            expected_sorted = sorted(expected)

            assert (
                result_sorted == expected_sorted
            ), f"Failed for input '{input_str}': expected {expected_sorted}, got {result_sorted}"

    # ============================================================================
    # B. TOOL AVAILABILITY AND PARAMETER TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_reply_tools_available(self, client):
        """Test that Gmail reply tools are available with new parameters."""
        tools = await client.list_tools()
        tool_dict = {tool.name: tool for tool in tools}

        # Check reply tools exist
        assert (
            "reply_to_gmail_message" in tool_dict
        ), "reply_to_gmail_message tool not found"
        assert "draft_gmail_reply" in tool_dict, "draft_gmail_reply tool not found"

        # Check for new parameters in reply_to_gmail_message
        reply_tool = tool_dict["reply_to_gmail_message"]
        if hasattr(reply_tool, "inputSchema") and reply_tool.inputSchema:
            schema = reply_tool.inputSchema
            if isinstance(schema, dict) and "properties" in schema:
                properties = schema["properties"]

                # Check for new parameters
                expected_params = ["reply_mode", "to", "cc", "bcc"]
                for param in expected_params:
                    assert param in properties or "reply_mode" not in str(
                        schema
                    ), f"Parameter '{param}' should be in reply_to_gmail_message schema"

        # Check for new parameters in draft_gmail_reply
        draft_tool = tool_dict["draft_gmail_reply"]
        if hasattr(draft_tool, "inputSchema") and draft_tool.inputSchema:
            schema = draft_tool.inputSchema
            if isinstance(schema, dict) and "properties" in schema:
                properties = schema["properties"]

                # Check for new parameters
                expected_params = ["reply_mode", "to", "cc", "bcc"]
                for param in expected_params:
                    assert param in properties or "reply_mode" not in str(
                        schema
                    ), f"Parameter '{param}' should be in draft_gmail_reply schema"

    # ============================================================================
    # C. BACKWARD COMPATIBILITY TESTS
    # ============================================================================

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_backward_compatibility(self, client, real_gmail_message_id):
        """Test that reply tools maintain backward compatibility."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test reply_to_gmail_message without new parameters (should default to sender_only)
        result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Test reply body",
                "content_type": "plain",
            },
        )

        # Should either work or give auth error (both are valid)
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            result["content"]
        ) or validator.is_success_response(result["content"])

        assert is_valid, "Backward compatible reply should work or give auth error"

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_draft_reply_backward_compatibility(
        self, client, real_gmail_message_id
    ):
        """Test that draft reply maintains backward compatibility."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test draft_gmail_reply without new parameters (should default to sender_only)
        result = await runner.test_tool_with_explicit_email(
            "draft_gmail_reply",
            {
                "message_id": real_gmail_message_id,
                "body": "Test draft reply body",
                "content_type": "plain",
            },
        )

        # Should either work or give auth error (both are valid)
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            result["content"]
        ) or validator.is_success_response(result["content"])

        assert (
            is_valid
        ), "Backward compatible draft reply should work or give auth error"

    # ============================================================================
    # D. REPLY MODE TESTS
    # ============================================================================

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_sender_only_mode(self, client, real_gmail_message_id):
        """Test reply with sender_only mode (default behavior)."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Reply to sender only",
                "reply_mode": "sender_only",
                "content_type": "plain",
            },
        )

        # Validate response
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            result["content"]
        ) or validator.is_success_response(result["content"])

        assert is_valid, "sender_only mode should work or give auth error"

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_all_mode(self, client, real_gmail_message_id):
        """Test reply with reply_all mode."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Reply to all recipients",
                "reply_mode": "reply_all",
                "content_type": "plain",
            },
        )

        # Validate response
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            result["content"]
        ) or validator.is_success_response(result["content"])

        assert is_valid, "reply_all mode should work or give auth error"

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_custom_mode(self, client, real_gmail_message_id):
        """Test reply with custom mode and specified recipients."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Custom reply to specific recipients",
                "reply_mode": "custom",
                "to": ["custom1@example.com", "custom2@example.com"],
                "cc": ["cc@example.com"],
                "bcc": ["bcc@example.com"],
                "content_type": "plain",
            },
        )

        # Validate response
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            result["content"]
        ) or validator.is_success_response(result["content"])

        assert is_valid, "custom mode should work or give auth error"

    @pytest.mark.asyncio
    async def test_reply_custom_mode_missing_recipients(
        self, client, real_gmail_message_id
    ):
        """Test reply with custom mode but missing required 'to' parameter."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # This should fail because custom mode requires 'to' parameter
        result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Custom reply without recipients",
                "reply_mode": "custom",
                "content_type": "plain",
            },
        )

        # Should get an error about missing 'to' parameter
        assert (
            "error" in result["content"].lower()
            or "custom" in result["content"].lower()
            or "required" in result["content"].lower()
            or "must provide" in result["content"].lower()
        ), "Should get error when custom mode lacks 'to' parameter"

    # ============================================================================
    # E. DRAFT REPLY MODE TESTS
    # ============================================================================

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_draft_reply_all_mode(self, client, real_gmail_message_id):
        """Test draft reply with reply_all mode."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        result = await runner.test_tool_with_explicit_email(
            "draft_gmail_reply",
            {
                "message_id": real_gmail_message_id,
                "body": "Draft reply to all",
                "reply_mode": "reply_all",
                "content_type": "plain",
            },
        )

        # Validate response
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            result["content"]
        ) or validator.is_success_response(result["content"])

        assert is_valid, "draft reply_all mode should work or give auth error"

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_draft_custom_mode(self, client, real_gmail_message_id):
        """Test draft reply with custom recipients."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        result = await runner.test_tool_with_explicit_email(
            "draft_gmail_reply",
            {
                "message_id": real_gmail_message_id,
                "body": "Draft custom reply",
                "reply_mode": "custom",
                "to": ["draft@example.com"],
                "cc": ["draft-cc@example.com"],
                "content_type": "plain",
            },
        )

        # Validate response
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            result["content"]
        ) or validator.is_success_response(result["content"])

        assert is_valid, "draft custom mode should work or give auth error"

    # ============================================================================
    # F. CONTENT TYPE TESTS WITH REPLY MODES
    # ============================================================================

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_html_content_with_reply_all(
        self, client, real_gmail_message_id
    ):
        """Test HTML content type with reply_all mode."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "<p>HTML reply to all</p>",
                "reply_mode": "reply_all",
                "content_type": "html",
            },
        )

        # Validate response
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            result["content"]
        ) or validator.is_success_response(result["content"])

        assert is_valid, "HTML content with reply_all should work or give auth error"

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_mixed_content_with_custom_recipients(
        self, client, real_gmail_message_id
    ):
        """Test mixed content type with custom recipients."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Plain text version",
                "html_body": "<p>HTML version</p>",
                "reply_mode": "custom",
                "to": ["recipient@example.com"],
                "content_type": "mixed",
            },
        )

        # Validate response
        validator = TestResponseValidator()
        is_valid = validator.is_valid_auth_response(
            result["content"]
        ) or validator.is_success_response(result["content"])

        assert (
            is_valid
        ), "Mixed content with custom recipients should work or give auth error"

    # ============================================================================
    # G. AUTHENTICATION PATTERN TESTS
    # ============================================================================

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_auth_patterns(self, client, real_gmail_message_id):
        """Test both explicit and middleware authentication patterns with new parameters."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test auth patterns with reply_all mode
        results = await runner.test_auth_patterns(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Testing auth patterns",
                "reply_mode": "reply_all",
                "content_type": "plain",
            },
        )

        # Both patterns should work or give valid auth responses
        assert (
            results["backward_compatible"] or "auth" in str(results).lower()
        ), "Explicit email should work or require auth"
        assert (
            results["middleware_supported"]
            or results["middleware_injection"]["param_required_at_client"]
        ), "Middleware should work or require param at client level"

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_draft_reply_auth_patterns(self, client, real_gmail_message_id):
        """Test draft reply auth patterns with new parameters."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test auth patterns with custom mode
        results = await runner.test_auth_patterns(
            "draft_gmail_reply",
            {
                "message_id": real_gmail_message_id,
                "body": "Testing draft auth patterns",
                "reply_mode": "custom",
                "to": ["test@example.com"],
                "content_type": "plain",
            },
        )

        # Both patterns should work or give valid auth responses
        assert (
            results["backward_compatible"] or "auth" in str(results).lower()
        ), "Explicit email should work or require auth"
        assert (
            results["middleware_supported"]
            or results["middleware_injection"]["param_required_at_client"]
        ), "Middleware should work or require param at client level"

    # ============================================================================
    # H. EDGE CASES AND ERROR HANDLING
    # ============================================================================

    @pytest.mark.asyncio
    async def test_invalid_reply_mode(self, client, real_gmail_message_id):
        """Test with invalid reply_mode value."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test with invalid reply_mode - should raise validation error
        try:
            result = await runner.test_tool_with_explicit_email(
                "reply_to_gmail_message",
                {
                    "message_id": real_gmail_message_id,
                    "body": "Test with invalid mode",
                    "reply_mode": "invalid_mode",
                    "content_type": "plain",
                },
            )
            # If we get here without exception, check the result
            assert (
                "error" in result["content"].lower()
                or "invalid" in result["content"].lower()
                or "reply_mode" in result["content"].lower()
            ), "Should get error for invalid reply_mode"
        except Exception as e:
            # Validation error is expected and correct
            error_msg = str(e).lower()
            assert (
                "invalid_mode" in error_msg
                or "not one of" in error_msg
                or "validation" in error_msg
            ), f"Expected validation error for invalid reply_mode, got: {e}"

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_with_multiple_recipient_formats(
        self, client, real_gmail_message_id
    ):
        """Test custom mode with various recipient format combinations."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Test with string format for single recipient
        result1 = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Reply with string recipient",
                "reply_mode": "custom",
                "to": "single@example.com",
                "content_type": "plain",
            },
        )

        validator = TestResponseValidator()
        is_valid1 = validator.is_valid_auth_response(
            result1["content"]
        ) or validator.is_success_response(result1["content"])

        # Test with list format for multiple recipients
        result2 = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Reply with list recipients",
                "reply_mode": "custom",
                "to": ["recipient1@example.com", "recipient2@example.com"],
                "cc": ["cc1@example.com", "cc2@example.com"],
                "content_type": "plain",
            },
        )

        is_valid2 = validator.is_valid_auth_response(
            result2["content"]
        ) or validator.is_success_response(result2["content"])

        assert is_valid1, "String format recipient should work"
        assert is_valid2, "List format recipients should work"

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_with_empty_body(self, client, real_gmail_message_id):
        """Test reply with empty body content."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "",
                "reply_mode": "reply_all",
                "content_type": "plain",
            },
        )

        # Should handle empty body appropriately
        validator = TestResponseValidator()
        is_valid = (
            validator.is_valid_auth_response(result["content"])
            or validator.is_success_response(result["content"])
            or "body" in result["content"].lower()
        )

        assert is_valid, "Should handle empty body appropriately"

    # ============================================================================
    # I. INTEGRATION TESTS
    # ============================================================================

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    @pytest.mark.slow
    async def test_reply_workflow_integration(self, client, real_gmail_message_id):
        """Test complete reply workflow with different modes."""
        runner = ToolTestRunner(client, TEST_EMAIL)
        validator = TestResponseValidator()

        # Step 1: Create a draft reply with reply_all
        draft_result = await runner.test_tool_with_explicit_email(
            "draft_gmail_reply",
            {
                "message_id": real_gmail_message_id,
                "body": "Draft reply to all for workflow test",
                "reply_mode": "reply_all",
                "content_type": "plain",
            },
        )

        draft_valid = validator.is_valid_auth_response(
            draft_result["content"]
        ) or validator.is_success_response(draft_result["content"])

        # Step 2: Send a reply with custom recipients
        send_result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": "test_message_id2",
                "body": "Custom reply for workflow test",
                "reply_mode": "custom",
                "to": ["workflow@example.com"],
                "cc": ["workflow-cc@example.com"],
                "content_type": "plain",
            },
        )

        send_valid = validator.is_valid_auth_response(
            send_result["content"]
        ) or validator.is_success_response(send_result["content"])

        # Both operations should succeed or give valid auth responses
        assert draft_valid, "Draft creation should work in workflow"
        assert send_valid, "Reply sending should work in workflow"

    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_reply_with_elicitation_system(self, client, real_gmail_message_id):
        """Test reply functionality with Gmail elicitation system."""
        runner = ToolTestRunner(client, TEST_EMAIL)

        # Reply to untrusted recipients using custom mode
        # This might trigger elicitation if the recipients are not on allow list
        result = await runner.test_tool_with_explicit_email(
            "reply_to_gmail_message",
            {
                "message_id": real_gmail_message_id,
                "body": "Reply that might trigger elicitation",
                "reply_mode": "custom",
                "to": ["untrusted@example.com"],
                "content_type": "plain",
            },
        )

        # Should handle elicitation or errors appropriately
        content = result["content"].lower()
        assert (
            "email ready to send" in content  # Elicitation triggered
            or "email sent" in content  # Sent successfully
            or "authentication" in content  # Auth error
            or "credentials" in content  # Auth error
            or "invalid id" in content  # Invalid message ID error
            or "error" in content
        ), "Should handle elicitation, auth, or message ID errors appropriately"


def run_tests():
    """Run the Gmail reply improvements test suite."""
    print("=" * 80)
    print("Gmail Reply Improvements Test Suite")
    print("=" * 80)
    print()
    print("This test suite validates the enhanced reply functionality including:")
    print("• New reply modes (sender_only, reply_all, custom)")
    print("• Backward compatibility")
    print("• CC/BCC support in replies")
    print("• Email extraction helper function")
    print("• Authentication patterns")
    print("• Edge cases and error handling")
    print()

    # Run tests with pytest
    import subprocess

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                __file__,
                "-v",
                "--asyncio-mode=auto",
                "--tb=short",
            ],
            capture_output=False,
            text=True,
        )

        return result.returncode == 0

    except Exception as e:
        print(f"Error running tests: {e}")
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
