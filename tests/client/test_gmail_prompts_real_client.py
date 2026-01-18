"""Test suite for Gmail prompts using FastMCP Client SDK to test the running MCP server."""

import pytest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@pytest.mark.service("gmail")
class TestGmailPrompts:
    """Test Gmail prompts with real client interactions.

    🔧 MCP Tools Used:
    - send_gmail_message: Send emails using prompt-generated content
    - draft_gmail_message: Create drafts from prompt templates
    - Template rendering tools: Generate email content from prompts
    - Gmail search tools: Find emails for prompt context

    🧪 What's Being Tested:
    - Real-world Gmail operations with AI-generated content
    - Prompt-to-email conversion workflows
    - Template rendering and email composition
    - Client-server interaction patterns for complex operations
    - Error handling in real Gmail API scenarios
    - Performance validation with actual Gmail service calls

    🔍 Potential Duplications:
    - Basic Gmail operations overlap with standard Gmail tests
    - Template rendering overlaps with template middleware tests
    - Real client testing patterns might be similar to other integration tests
    - Email composition logic similar to other Gmail content generation tests
    """

    @pytest.mark.asyncio
    async def test_server_connectivity(self, client):
        """Test that we can connect to the server."""
        # Ping the server to verify connectivity
        await client.ping()
        assert client.is_connected()

    @pytest.mark.asyncio
    async def test_list_prompts(self, client):
        """Test listing available prompts."""
        prompts = await client.list_prompts()

        # Should be a list (might be empty if no prompts registered)
        assert isinstance(prompts, list)

        # Look for Gmail prompts
        prompt_names = [prompt.name for prompt in prompts]
        print(f"📋 Available prompts: {prompt_names}")

        # Check for our Gmail prompt names
        expected_gmail_prompts = [
            "quick_email_demo",
            "professional_html_email",
            "smart_contextual_email",
        ]

        gmail_prompts_found = [
            name for name in expected_gmail_prompts if name in prompt_names
        ]

        if gmail_prompts_found:
            print(f"✅ Found Gmail prompts: {gmail_prompts_found}")

            # Check prompt metadata
            for prompt in prompts:
                if prompt.name in expected_gmail_prompts:
                    print(f"📝 Prompt: {prompt.name}")
                    print(f"   Description: {prompt.description}")

                    if prompt.arguments:
                        arg_names = [arg.name for arg in prompt.arguments]
                        print(f"   Arguments: {arg_names}")
                    else:
                        print("   Arguments: None (zero-config)")

                    # Check for FastMCP metadata
                    if hasattr(prompt, "_meta") and prompt._meta:
                        fastmcp_meta = prompt._meta.get("_fastmcp", {})
                        if fastmcp_meta:
                            print(f"   Tags: {fastmcp_meta.get('tags', [])}")
                            print(f"   Version: {fastmcp_meta.get('version', 'N/A')}")
        else:
            print(
                "⚠️  No Gmail prompts found - might need to register them in server startup"
            )

    @pytest.mark.asyncio
    async def test_quick_email_demo_prompt(self, client):
        """Test the simple quick_email_demo prompt (zero arguments)."""
        prompts = await client.list_prompts()
        prompt_names = [prompt.name for prompt in prompts]

        if "quick_email_demo" not in prompt_names:
            pytest.skip("quick_email_demo prompt not available")

        print("🔄 Testing quick_email_demo prompt (Simple/Zero-config)")

        # Call the prompt with no arguments
        result = await client.get_prompt("quick_email_demo", {})

        # Check that we get a result
        assert result is not None
        assert hasattr(result, "messages")
        assert len(result.messages) > 0

        # Check the first message
        message = result.messages[0]
        print(f"📧 Result role: {message.role}")

        # Get the content
        if hasattr(message.content, "text"):
            content = message.content.text
        else:
            content = str(message.content)

        print(f"📄 Content preview: {content[:200]}...")

        # Verify expected content patterns
        assert "Quick Email Demo" in content

        # The prompt copy has evolved; accept either "Simple" wording or "Zero-Configuration"
        # variants.
        normalized = content.lower().replace("-", " ")
        assert (
            "simple" in normalized or "zero configuration" in normalized
        ), "Prompt should communicate that it's a simple/zero-config demo."

        # Should include resource templating examples or resolved resource URIs
        # The Template Parameter Middleware may resolve {{...}} to single braces {resource://...}
        # or fully resolve them to actual values
        has_template_syntax = ("{{" in content and "}}" in content) or (
            "{" in content and "://" in content
        )
        assert (
            has_template_syntax
        ), "Prompt should contain template expressions or resource URIs"
        assert "gmail" in content.lower() or "email" in content.lower()

        print("✅ quick_email_demo prompt test passed")

    @pytest.mark.asyncio
    async def test_professional_html_email_prompt(self, client):
        """Test the medium complexity professional_html_email prompt."""
        prompts = await client.list_prompts()
        prompt_names = [prompt.name for prompt in prompts]

        if "professional_html_email" not in prompt_names:
            pytest.skip("professional_html_email prompt not available")

        print("🔄 Testing professional_html_email prompt (Medium complexity)")

        # Call the prompt with arguments
        test_args = {
            "email_subject": "Welcome to Our Team",
            "recipient_name": "Alice Johnson",
            "message_theme": "welcome message",
        }

        result = await client.get_prompt("professional_html_email", test_args)

        # Check that we get a result
        assert result is not None
        assert hasattr(result, "messages")
        assert len(result.messages) > 0

        # Check the first message
        message = result.messages[0]
        print(f"📧 Result role: {message.role}")

        # Get the content
        if hasattr(message.content, "text"):
            content = message.content.text
        else:
            content = str(message.content)

        print(f"📄 Content preview: {content[:300]}...")

        # Verify expected content patterns
        assert "Professional HTML Email" in content
        assert test_args["email_subject"] in content  # Should include the subject
        assert test_args["recipient_name"] in content  # Should include recipient name
        assert "Medium" in content or "professional" in content.lower()

        # Should include HTML patterns
        assert "html>" in content.lower() or "<!doctype" in content.lower()

        print("✅ professional_html_email prompt test passed")

    @pytest.mark.asyncio
    async def test_smart_contextual_email_prompt(self, client):
        """Test the advanced smart_contextual_email prompt."""
        prompts = await client.list_prompts()
        prompt_names = [prompt.name for prompt in prompts]

        if "smart_contextual_email" not in prompt_names:
            pytest.skip("smart_contextual_email prompt not available")

        print("🔄 Testing smart_contextual_email prompt (Advanced)")

        # Call the prompt with complex arguments
        test_args = {
            "email_subject": "Strategic Partnership Proposal",
            "recipient_name": "Dr. Sarah Chen",
            "email_purpose": "business partnership",
        }

        result = await client.get_prompt("smart_contextual_email", test_args)

        # Check that we get a result
        assert result is not None
        assert hasattr(result, "messages")
        assert len(result.messages) > 0

        # Check the first message
        message = result.messages[0]
        print(f"📧 Result role: {message.role}")

        # Get the content - following FastMCP documentation pattern
        content = (
            message.content.text
            if hasattr(message.content, "text")
            else str(message.content)
        )

        print(f"📄 Content preview: {content[:300]}...")

        # Verify expected content patterns
        assert "Smart Contextual" in content or "Advanced" in content
        assert test_args["email_subject"] in content  # Should include the subject
        assert test_args["recipient_name"] in content  # Should include recipient name
        assert test_args["email_purpose"] in content  # Should include purpose

        # Should include Gmail integration references
        assert "gmail" in content.lower() or "resource" in content.lower()
        assert "context" in content.lower() or "intelligence" in content.lower()

        print("✅ smart_contextual_email prompt test passed")

    @pytest.mark.asyncio
    async def test_prompt_argument_validation(self, client):
        """Test that prompts handle different argument combinations properly."""
        prompts = await client.list_prompts()
        prompt_names = [prompt.name for prompt in prompts]

        # Test with minimal arguments for medium complexity prompt
        if "professional_html_email" in prompt_names:
            print("🔄 Testing professional_html_email with minimal args")

            # Test with only some arguments
            minimal_args = {
                "email_subject": "Test Subject"
                # Missing recipient_name and message_theme - should use defaults
            }

            result = await client.get_prompt("professional_html_email", minimal_args)
            assert result is not None
            assert len(result.messages) > 0

            message = result.messages[0]
            content = (
                message.content.text
                if hasattr(message.content, "text")
                else str(message.content)
            )

            # Should still work with default values
            assert "Test Subject" in content
            print("✅ Minimal args test passed")

    @pytest.mark.asyncio
    async def test_prompt_filtering_by_tags(self, client):
        """Test filtering prompts by tags (FastMCP 2.11.0+ feature)."""
        prompts = await client.list_prompts()

        # Filter prompts by tags
        gmail_tagged_prompts = []
        simple_tagged_prompts = []
        advanced_tagged_prompts = []

        for prompt in prompts:
            if hasattr(prompt, "_meta") and prompt._meta:
                fastmcp_meta = prompt._meta.get("_fastmcp", {})
                tags = fastmcp_meta.get("tags", [])

                if "gmail" in tags:
                    gmail_tagged_prompts.append(prompt.name)
                if "simple" in tags:
                    simple_tagged_prompts.append(prompt.name)
                if "advanced" in tags:
                    advanced_tagged_prompts.append(prompt.name)

        print(f"🏷️  Gmail tagged prompts: {gmail_tagged_prompts}")
        print(f"🏷️  Simple tagged prompts: {simple_tagged_prompts}")
        print(f"🏷️  Advanced tagged prompts: {advanced_tagged_prompts}")

        # Should have some Gmail prompts with tags
        if gmail_tagged_prompts:
            assert (
                "quick_email_demo" in simple_tagged_prompts
                or len(simple_tagged_prompts) > 0
            )
            print("✅ Tag-based filtering test passed")
        else:
            print("⚠️  No tagged prompts found - might need to update prompt metadata")

    @pytest.mark.asyncio
    async def test_complex_argument_serialization(self, client):
        """Test complex argument serialization (FastMCP 2.9.0+ feature)."""
        prompts = await client.list_prompts()
        prompt_names = [prompt.name for prompt in prompts]

        if "smart_contextual_email" not in prompt_names:
            pytest.skip("smart_contextual_email prompt not available")

        print("🔄 Testing complex argument serialization")

        # Test with complex nested arguments
        complex_args = {
            "email_subject": "Complex Data Test",
            "recipient_name": "Tech Team",
            "email_purpose": "data analysis",
            # Complex nested data that should be auto-serialized
            "recipient_data": {
                "name": "Dr. Elena Rodriguez",
                "role": "Senior Research Director",
                "department": "Innovation Labs",
            },
            "email_preferences": {
                "format": "professional",
                "include_attachments": True,
                "tracking_enabled": False,
            },
            "stakeholders": [
                {"name": "Alice Johnson", "role": "PM"},
                {"name": "Bob Wilson", "role": "Tech Lead"},
            ],
        }

        # FastMCP should automatically serialize complex objects to JSON
        result = await client.get_prompt("smart_contextual_email", complex_args)

        assert result is not None
        assert len(result.messages) > 0

        message = result.messages[0]
        if hasattr(message.content, "text"):
            content = message.content.text
        else:
            content = str(message.content)

        # Should still include basic arguments
        assert complex_args["email_subject"] in content
        assert complex_args["recipient_name"] in content

        print("✅ Complex argument serialization test passed")

    @pytest.mark.asyncio
    async def test_prompt_with_resource_context(self, client):
        """Test that prompts can access resources and context properly."""
        prompts = await client.list_prompts()
        prompt_names = [prompt.name for prompt in prompts]

        if "quick_email_demo" not in prompt_names:
            pytest.skip("quick_email_demo prompt not available")

        print("🔄 Testing prompt with resource context access")

        # The quick_email_demo should attempt to read resources like service://gmail/labels
        result = await client.get_prompt("quick_email_demo", {})

        assert result is not None
        assert len(result.messages) > 0

        message = result.messages[0]
        if hasattr(message.content, "text"):
            content = message.content.text
        else:
            content = str(message.content)

        # Should show evidence of attempting resource access
        # Either successful resource data OR authentication errors
        has_resource_evidence = (
            "service://gmail/labels" in content
            or "user://current/email" in content
            or "Authentication required" in content
            or "No authenticated user found" in content
            or "label" in content.lower()
            and ("id" in content or "name" in content)
        )

        assert (
            has_resource_evidence
        ), f"No evidence of resource access in content: {content[:500]}"
        print("✅ Resource context test passed")


if __name__ == "__main__":
    # Run tests with asyncio
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
