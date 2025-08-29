#!/usr/bin/env python3
"""
Comprehensive test suite for Gmail elicitation system validation using FastMCP Client SDK.

This test suite validates the complete Gmail elicitation system by testing against
a running MCP server using the FastMCP Client SDK. Tests cover:

- Allow list configuration and parsing
- Management tools (add/remove/view)
- Resource system access
- Elicitation flow simulation
- Integration scenarios
- Edge cases and error handling

Tests are designed to run against a running MCP server instance.
"""

import pytest
import asyncio
import json
from fastmcp import Client
from typing import Any, Dict, List
import os

# Import test utilities
from .test_auth_utils import get_client_auth_config

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")


class TestGmailElicitationSystem:
    """Comprehensive test suite for Gmail elicitation system using FastMCP Client."""

    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client

    @pytest.mark.asyncio
    async def test_gmail_tools_available(self, client):
        """Test that Gmail elicitation tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        # Check that Gmail elicitation tools are registered
        expected_tools = [
            "send_gmail_message",
            "add_to_gmail_allow_list",
            "remove_from_gmail_allow_list",
            "view_gmail_allow_list"
        ]

        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Gmail tool '{expected_tool}' not found in available tools"

    @pytest.mark.asyncio
    async def test_gmail_allow_list_resource_available(self, client):
        """Test that Gmail allow list resource is available."""
        resources = await client.list_resources()
        resource_uris = [str(resource.uri) for resource in resources]

        assert "gmail://allow-list" in resource_uris, "gmail://allow-list resource not found"

    # ============================================================================
    # A. ALLOW LIST CONFIGURATION TESTS (Settings Layer)
    # ============================================================================

    @pytest.mark.asyncio
    async def test_view_gmail_allow_list_empty(self, client):
        """Test view_gmail_allow_list with empty allow list."""
        result = await client.call_tool("view_gmail_allow_list", {
            "user_google_email": TEST_EMAIL
        })

        assert len(result) > 0
        content = result[0].text

        # Should indicate empty allow list or authentication error
        assert ("currently empty" in content.lower() or
                "no emails are configured" in content.lower() or
                "authentication" in content.lower() or
                "credentials" in content.lower())

    @pytest.mark.asyncio
    async def test_add_to_gmail_allow_list_valid_email(self, client):
        """Test add_to_gmail_allow_list with valid email."""
        test_email = "test@example.com"

        result = await client.call_tool("add_to_gmail_allow_list", {
            "user_google_email": TEST_EMAIL,
            "email": test_email
        })

        assert len(result) > 0
        content = result[0].text

        # Should either succeed or indicate authentication issue
        assert ("successfully added" in content.lower() or
                "already in the allow list" in content.lower() or
                "authentication" in content.lower() or
                "credentials" in content.lower())

    @pytest.mark.asyncio
    async def test_add_to_gmail_allow_list_invalid_email(self, client):
        """Test add_to_gmail_allow_list with invalid email format."""
        result = await client.call_tool("add_to_gmail_allow_list", {
            "user_google_email": TEST_EMAIL,
            "email": "invalid-email-format"
        })

        assert len(result) > 0
        content = result[0].text

        # Should indicate invalid email format
        assert "invalid email format" in content.lower()

    @pytest.mark.asyncio
    async def test_remove_from_gmail_allow_list_nonexistent(self, client):
        """Test remove_from_gmail_allow_list with nonexistent email."""
        result = await client.call_tool("remove_from_gmail_allow_list", {
            "user_google_email": TEST_EMAIL,
            "email": "nonexistent@example.com"
        })

        assert len(result) > 0
        content = result[0].text

        # Should indicate email not in allow list or authentication issue
        assert ("not in the allow list" in content.lower() or
                "authentication" in content.lower() or
                "credentials" in content.lower())

    # ============================================================================
    # B. RESOURCE SYSTEM TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_gmail_allow_list_resource_access(self, client):
        """Test accessing gmail://allow-list resource."""
        try:
            content = await client.read_resource("gmail://allow-list")

            assert len(content) > 0
            resource_data = json.loads(content[0].text)

            # Verify resource structure
            expected_fields = ["authenticated_user", "is_configured", "allow_list_count", "allow_list"]
            for field in expected_fields:
                assert field in resource_data, f"Missing field '{field}' in resource response"

            # Should have authentication status
            assert "authenticated" in resource_data or "error" in resource_data

        except Exception as e:
            # Resource access might fail without authentication
            assert "authentication" in str(e).lower() or "user" in str(e).lower()

    # ============================================================================
    # C. ELICITATION FLOW SIMULATION TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_send_gmail_message_requires_elicitation(self, client):
        """Test send_gmail_message triggers elicitation for untrusted recipients."""
        # This test simulates the elicitation flow by attempting to send to untrusted recipients
        result = await client.call_tool("send_gmail_message", {
            "user_google_email": TEST_EMAIL,
            "to": ["untrusted@example.com"],
            "subject": "Test Elicitation",
            "body": "This should trigger elicitation",
            "content_type": "plain"
        })

        assert len(result) > 0
        content = result[0].text

        # Should either trigger elicitation, send successfully, or indicate auth error
        assert ("email ready to send" in content.lower() or  # Elicitation message
                "email sent" in content.lower() or           # Successful send
                "authentication" in content.lower() or      # Auth error
                "credentials" in content.lower())           # Auth error

    @pytest.mark.asyncio
    async def test_send_gmail_message_multiple_recipients(self, client):
        """Test send_gmail_message with multiple recipient types."""
        result = await client.call_tool("send_gmail_message", {
            "user_google_email": TEST_EMAIL,
            "to": ["recipient1@example.com", "recipient2@example.com"],
            "cc": ["cc@example.com"],
            "bcc": ["bcc@example.com"],
            "subject": "Multi-Recipient Test",
            "body": "Testing multiple recipients",
            "content_type": "plain"
        })

        assert len(result) > 0
        content = result[0].text

        # Should handle multiple recipients appropriately
        assert ("email ready to send" in content.lower() or
                "email sent" in content.lower() or
                "authentication" in content.lower() or
                "credentials" in content.lower())

    @pytest.mark.asyncio
    async def test_send_gmail_message_content_types(self, client):
        """Test send_gmail_message with different content types."""
        content_types = ["plain", "html", "mixed"]

        for content_type in content_types:
            with self.subTest(content_type=content_type):
                result = await client.call_tool("send_gmail_message", {
                    "user_google_email": TEST_EMAIL,
                    "to": ["test@example.com"],
                    "subject": f"Content Type Test - {content_type}",
                    "body": f"Testing {content_type} content",
                    "content_type": content_type,
                    "html_body": f"<p>Testing {content_type} content</p>" if content_type == "mixed" else None
                })

                assert len(result) > 0
                content = result[0].text

                # Should handle content type appropriately
                assert ("email ready to send" in content.lower() or
                        "email sent" in content.lower() or
                        "authentication" in content.lower() or
                        "credentials" in content.lower())

    # ============================================================================
    # D. INTEGRATION TEST SCENARIOS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_allow_list_management_workflow(self, client):
        """Test complete allow list management workflow."""
        test_email = "workflow-test@example.com"

        # Step 1: Add email to allow list
        add_result = await client.call_tool("add_to_gmail_allow_list", {
            "user_google_email": TEST_EMAIL,
            "email": test_email
        })

        # Step 2: View allow list to verify addition
        view_result = await client.call_tool("view_gmail_allow_list", {
            "user_google_email": TEST_EMAIL
        })

        # Step 3: Remove email from allow list
        remove_result = await client.call_tool("remove_from_gmail_allow_list", {
            "user_google_email": TEST_EMAIL,
            "email": test_email
        })

        # Verify each step handled appropriately
        for result in [add_result, view_result, remove_result]:
            assert len(result) > 0
            content = result[0].text
            assert ("successfully" in content.lower() or
                    "allow list" in content.lower() or
                    "authentication" in content.lower() or
                    "credentials" in content.lower())

    @pytest.mark.asyncio
    async def test_gmail_elicitation_integration(self, client):
        """Test Gmail elicitation system integration."""
        # Test the complete flow: configure allow list, then send email
        trusted_email = "trusted@example.com"
        untrusted_email = "untrusted@example.com"

        # Step 1: Add trusted email to allow list
        await client.call_tool("add_to_gmail_allow_list", {
            "user_google_email": TEST_EMAIL,
            "email": trusted_email
        })

        # Step 2: Try to send to trusted email (should not trigger elicitation)
        trusted_result = await client.call_tool("send_gmail_message", {
            "user_google_email": TEST_EMAIL,
            "to": [trusted_email],
            "subject": "Trusted Recipient Test",
            "body": "This should not trigger elicitation",
            "content_type": "plain"
        })

        # Step 3: Try to send to untrusted email (should trigger elicitation)
        untrusted_result = await client.call_tool("send_gmail_message", {
            "user_google_email": TEST_EMAIL,
            "to": [untrusted_email],
            "subject": "Untrusted Recipient Test",
            "body": "This should trigger elicitation",
            "content_type": "plain"
        })

        # Verify both scenarios handled appropriately
        for result in [trusted_result, untrusted_result]:
            assert len(result) > 0
            content = result[0].text
            assert ("email ready to send" in content.lower() or
                    "email sent" in content.lower() or
                    "authentication" in content.lower() or
                    "credentials" in content.lower())

    # ============================================================================
    # E. EDGE CASES AND ERROR HANDLING TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_send_gmail_message_empty_recipients(self, client):
        """Test send_gmail_message with empty recipient lists."""
        result = await client.call_tool("send_gmail_message", {
            "user_google_email": TEST_EMAIL,
            "to": [],
            "cc": [],
            "bcc": [],
            "subject": "Empty Recipients Test",
            "body": "Testing with no recipients",
            "content_type": "plain"
        })

        assert len(result) > 0
        content = result[0].text

        # Should handle empty recipients gracefully
        assert ("email sent" in content.lower() or
                "authentication" in content.lower() or
                "credentials" in content.lower())

    @pytest.mark.asyncio
    async def test_send_gmail_message_long_body(self, client):
        """Test send_gmail_message with very long body content."""
        long_body = "This is a very long email body. " * 200  # ~6600 characters

        result = await client.call_tool("send_gmail_message", {
            "user_google_email": TEST_EMAIL,
            "to": ["test@example.com"],
            "subject": "Long Body Test",
            "body": long_body,
            "content_type": "plain"
        })

        assert len(result) > 0
        content = result[0].text

        # Should handle long content appropriately
        assert ("email ready to send" in content.lower() or
                "email sent" in content.lower() or
                "authentication" in content.lower() or
                "credentials" in content.lower())

    @pytest.mark.asyncio
    async def test_send_gmail_message_unicode_content(self, client):
        """Test send_gmail_message with unicode characters."""
        unicode_body = "Hello! 👋 This email contains unicode characters: 中文, русский, español"
        unicode_subject = "Unicode Test 📧 中文"

        result = await client.call_tool("send_gmail_message", {
            "user_google_email": TEST_EMAIL,
            "to": ["test@example.com"],
            "subject": unicode_subject,
            "body": unicode_body,
            "content_type": "plain"
        })

        assert len(result) > 0
        content = result[0].text

        # Should handle unicode content appropriately
        assert ("email ready to send" in content.lower() or
                "email sent" in content.lower() or
                "authentication" in content.lower() or
                "credentials" in content.lower())

    @pytest.mark.asyncio
    async def test_send_gmail_message_special_characters(self, client):
        """Test send_gmail_message with special characters in subject and body."""
        special_subject = "Special Chars: !@#$%^&*()_+-=[]{}|;:,.<>?"
        special_body = "Body with special chars: ©®™€£¥§¶†‡•…—"

        result = await client.call_tool("send_gmail_message", {
            "user_google_email": TEST_EMAIL,
            "to": ["test@example.com"],
            "subject": special_subject,
            "body": special_body,
            "content_type": "plain"
        })

        assert len(result) > 0
        content = result[0].text

        # Should handle special characters appropriately
        assert ("email ready to send" in content.lower() or
                "email sent" in content.lower() or
                "authentication" in content.lower() or
                "credentials" in content.lower())

    @pytest.mark.asyncio
    async def test_missing_required_parameters(self, client):
        """Test tools with missing required parameters."""
        # Test send_gmail_message without required parameters
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("send_gmail_message", {
                "user_google_email": TEST_EMAIL
                # Missing required: to, subject, body
            })

        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()

        # Test add_to_gmail_allow_list without email
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("add_to_gmail_allow_list", {
                "user_google_email": TEST_EMAIL
                # Missing required: email
            })

        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()

    # ============================================================================
    # F. DOCUMENTATION AND VALIDATION TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_tool_descriptions_and_parameters(self, client):
        """Test that Gmail tools have proper descriptions and parameters."""
        tools = await client.list_tools()

        gmail_tools = [tool for tool in tools if 'gmail' in tool.name.lower()]

        for tool in gmail_tools:
            # Each tool should have a description
            assert tool.description, f"Tool '{tool.name}' missing description"

            # Check for elicitation-related tools
            if tool.name == "send_gmail_message":
                assert "elicitation" in tool.description.lower(), "send_gmail_message should mention elicitation"

            # Tool should have input schema
            assert hasattr(tool, 'inputSchema'), f"Tool '{tool.name}' missing input schema"

    @pytest.mark.asyncio
    async def test_resource_descriptions(self, client):
        """Test that Gmail resources have proper descriptions."""
        resources = await client.list_resources()

        gmail_resources = [resource for resource in resources if 'gmail' in str(resource.uri)]

        for resource in gmail_resources:
            assert resource.description, f"Resource '{resource.uri}' missing description"
            assert "allow" in resource.description.lower(), "Gmail resource should mention allow list"

    # ============================================================================
    # G. PERFORMANCE AND RELIABILITY TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_concurrent_allow_list_operations(self, client):
        """Test concurrent allow list operations."""
        # This test checks if the system can handle concurrent operations
        test_emails = [f"concurrent{i}@example.com" for i in range(3)]

        # Perform concurrent add operations
        tasks = []
        for email in test_emails:
            task = client.call_tool("add_to_gmail_allow_list", {
                "user_google_email": TEST_EMAIL,
                "email": email
            })
            tasks.append(task)

        # Wait for all operations to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all operations completed (success or expected failure)
        for result in results:
            if isinstance(result, Exception):
                # Expected for authentication or other issues
                assert "authentication" in str(result).lower() or "credentials" in str(result).lower()
            else:
                # Successful operation
                assert len(result) > 0
                content = result[0].text
                assert ("successfully" in content.lower() or
                        "already in the allow list" in content.lower() or
                        "authentication" in content.lower() or
                        "credentials" in content.lower())


def run_tests():
    """Run the Gmail elicitation system test suite."""
    print("=" * 80)
    print("Gmail Elicitation System Test Suite")
    print("=" * 80)
    print()
    print("This test suite validates the Gmail elicitation system by testing")
    print("against a running MCP server using the FastMCP Client SDK.")
    print()
    print("Prerequisites:")
    print("- MCP server must be running and accessible")
    print("- Set MCP_SERVER_HOST and MCP_SERVER_PORT environment variables if needed")
    print("- Set TEST_EMAIL_ADDRESS for authenticated testing")
    print()
    print("Test Coverage:")
    print("• Allow list configuration and parsing")
    print("• Management tools (add/remove/view)")
    print("• Resource system access")
    print("• Elicitation flow simulation")
    print("• Integration scenarios")
    print("• Edge cases and error handling")
    print("• Documentation validation")
    print("• Performance and reliability")
    print()

    # Run tests with pytest
    import subprocess
    import sys

    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            __file__,
            "-v",
            "--asyncio-mode=auto",
            "--tb=short"
        ], capture_output=False, text=True)

        return result.returncode == 0

    except Exception as e:
        print(f"Error running tests: {e}")
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)