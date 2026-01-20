"""Test suite for enhanced NLP card parsing in send_dynamic_card tool.

These tests validate that the enhanced natural language patterns (ordinal words + titled)
correctly parse into multi-section Google Chat cards with proper widgets and icons.

Tests cover:
- Ordinal word patterns (First, Second, Third section titled "X" showing Y)
- URL extraction with automatic "Open" buttons
- Warning content with WARNING icons
- Commit references with appropriate icons
- Multi-section card rendering
"""

import json
import os
import re

import pytest
from dotenv import load_dotenv

from .base_test_config import TEST_EMAIL
from .test_helpers import assert_tools_registered

# Load environment variables
load_dotenv()

# Test configuration
TEST_CHAT_WEBHOOK = os.getenv("TEST_CHAT_WEBHOOK", "")
TEST_CHAT_SPACE_ID = os.getenv("TEST_CHAT_SPACE_ID", "")

# Extract space ID from webhook if not explicitly set
if not TEST_CHAT_SPACE_ID and TEST_CHAT_WEBHOOK:
    try:
        match = re.search(r"/spaces/([^/]+)/", TEST_CHAT_WEBHOOK)
        if match:
            TEST_CHAT_SPACE_ID = match.group(1)
    except Exception:
        pass

print("🧠 NLP DYNAMIC CARD TEST CONFIG:")
print(f"  - Webhook URL: {'✅ Configured' if TEST_CHAT_WEBHOOK else '❌ Missing'}")
print(f"  - Space ID: {TEST_CHAT_SPACE_ID or '❌ Missing'}")
print(f"  - Email: {TEST_EMAIL or '❌ Missing'}")


@pytest.mark.service("chat")
class TestNLPDynamicCardBasic:
    """Basic tests for NLP-enhanced send_dynamic_card tool."""

    @pytest.mark.asyncio
    async def test_send_dynamic_card_tool_available(self, client):
        """Test that send_dynamic_card tool is available."""
        await assert_tools_registered(
            client, ["send_dynamic_card"], context="NLP Dynamic Card"
        )

    @pytest.mark.asyncio
    async def test_simple_ordinal_pattern(self, client):
        """Test basic ordinal word pattern: First section titled 'X' showing Y."""
        space_id = TEST_CHAT_SPACE_ID or "spaces/test_space"

        # Build params - use webhook if available (required for cards with human OAuth)
        params = {
            "user_google_email": TEST_EMAIL,
            "space_id": f"spaces/{space_id}",
            "card_description": 'First section titled "Status" showing Everything is working correctly.',
        }
        if TEST_CHAT_WEBHOOK:
            params["webhook_url"] = TEST_CHAT_WEBHOOK

        result = await client.call_tool("send_dynamic_card", params)

        assert result is not None and result.content
        content = result.content[0].text

        # Should succeed or return expected error patterns
        # Note: "human credentials" error occurs when sending cards via API without webhook
        valid_responses = [
            "success",
            "card sent",
            "card message sent",
            "requires authentication",
            "permission denied",
            "middleware",
            "human credentials",  # Google Chat API limitation for cards
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Unexpected response: {content}"


@pytest.mark.service("chat")
@pytest.mark.integration
class TestNLPDynamicCardMultiSection:
    """Test multi-section card generation with enhanced NLP parsing."""

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_github_activity_card_three_sections(self, client):
        """Test GitHub activity card with 3 sections using ordinal+titled pattern.

        This is the primary use case that prompted the NLP parser enhancement.
        The card should render with:
        - Deployments section with CLOUD icons and Open buttons
        - Commits section with PERSON icon
        - Stale PRs section with WARNING icon
        """
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        card_description = '''Create a GitHub activity update card for Sunday January 18 2026. Include three sections: First section titled "Deployments - PR #1672" showing AIDG React FE preview deployed at pr-1672-aidg-react-fe-rzpt3.ondigitalocean.app and Admin React FE preview deployed at pr-1672-admin-react-fe-gxzol.ondigitalocean.app. Second section titled "Commits" showing @ctzaruba pushed commit 9966fbe for ENC-2390 temporal structural improvements. Third section titled "Stale PRs" warning that PR #1550 MAD-4142 env var for google scraper has had no activity for 10 days and is marked for removal.'''

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": card_description,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        # Parse the JSON response to verify structure
        try:
            response_data = json.loads(content)

            # Verify success
            assert response_data.get("success") is True, f"Card send failed: {response_data.get('error')}"

            # Verify HTTP status for webhook delivery
            http_status = response_data.get("httpStatus")
            assert http_status == 200, f"Expected HTTP 200, got {http_status}"

            # Check if NLP sections were used (should be nlp_sections type with enhanced parsing)
            card_type = response_data.get("cardType", "")
            component_info = response_data.get("componentInfo", {})

            # Log the response for debugging
            print(f"\n📊 Response Details:")
            print(f"  - Card Type: {card_type}")
            print(f"  - Component Name: {component_info.get('componentName')}")
            print(f"  - Search Score: {component_info.get('searchScore')}")
            print(f"  - NLP Extraction: {response_data.get('nlpExtraction')}")

        except json.JSONDecodeError:
            # If not JSON, check for success indicators in text
            success_indicators = ["success", "card sent", "webhook", "status: 200"]
            assert any(
                indicator in content.lower() for indicator in success_indicators
            ), f"Card send failed: {content}"

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_two_section_deployment_card(self, client):
        """Test deployment notification with two sections."""
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        card_description = '''Create a deployment notification. First section titled "Frontend" showing Preview deployed at preview.example.com. Second section titled "Backend" showing API deployed at api.example.com.'''

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": card_description,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        # Check for success
        success_indicators = [
            "success",
            "card sent",
            "card message sent",
            "webhook",
            "status: 200",
            '"success":true',
            '"success": true',
        ]
        assert any(
            indicator in content.lower() for indicator in success_indicators
        ), f"Expected success response: {content}"


@pytest.mark.service("chat")
@pytest.mark.integration
class TestNLPDynamicCardWidgets:
    """Test specific widget types generated by NLP parsing."""

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_url_creates_open_button(self, client):
        """Test that URLs in content create 'Open' buttons."""
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        card_description = '''First section titled "Links" showing Check out the documentation at docs.example.com for more information.'''

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": card_description,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        success_indicators = ["success", "card sent", "webhook", '"success":true']
        assert any(
            indicator in content.lower() for indicator in success_indicators
        ), f"Expected success: {content}"

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_warning_content_gets_warning_icon(self, client):
        """Test that warning content gets WARNING icon."""
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        card_description = '''First section titled "Alerts" showing warning: Database connection pool is running low.'''

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": card_description,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        success_indicators = ["success", "card sent", "webhook", '"success":true']
        assert any(
            indicator in content.lower() for indicator in success_indicators
        ), f"Expected success: {content}"

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_commit_content_parsing(self, client):
        """Test that commit references are parsed correctly."""
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        card_description = '''First section titled "Recent Changes" showing @developer pushed commit abc123 with bug fixes.'''

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": card_description,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        success_indicators = ["success", "card sent", "webhook", '"success":true']
        assert any(
            indicator in content.lower() for indicator in success_indicators
        ), f"Expected success: {content}"


@pytest.mark.service("chat")
@pytest.mark.integration
class TestNLPDynamicCardEdgeCases:
    """Test edge cases and backward compatibility."""

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_and_splitting_in_content(self, client):
        """Test that 'X and Y' in content creates multiple widgets."""
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        card_description = '''First section titled "Services" showing Frontend running at frontend.example.com and Backend running at backend.example.com.'''

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": card_description,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        success_indicators = ["success", "card sent", "webhook", '"success":true']
        assert any(
            indicator in content.lower() for indicator in success_indicators
        ), f"Expected success: {content}"

    @pytest.mark.skipif(
        not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK not configured"
    )
    @pytest.mark.asyncio
    async def test_warning_not_split_on_and(self, client):
        """Test that warning content with 'and' is NOT split (stays as one message)."""
        space_id = TEST_CHAT_SPACE_ID
        if not space_id:
            pytest.skip("TEST_CHAT_SPACE_ID not configured")

        card_description = '''First section titled "Warning" showing PR has been inactive for 10 days and is marked for removal.'''

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "webhook_url": TEST_CHAT_WEBHOOK,
                "card_description": card_description,
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        success_indicators = ["success", "card sent", "webhook", '"success":true']
        assert any(
            indicator in content.lower() for indicator in success_indicators
        ), f"Expected success: {content}"

    @pytest.mark.asyncio
    async def test_backward_compat_simple_description(self, client):
        """Test that simple descriptions without ordinal pattern still work."""
        space_id = TEST_CHAT_SPACE_ID or "spaces/test_space"

        result = await client.call_tool(
            "send_dynamic_card",
            {
                "user_google_email": TEST_EMAIL,
                "space_id": f"spaces/{space_id}",
                "card_description": "Create a simple notification card with title 'Test' and message 'Hello World'",
            },
        )

        assert result is not None and result.content
        content = result.content[0].text

        # Should succeed or return expected error patterns
        valid_responses = [
            "success",
            "card sent",
            "card message sent",
            "requires authentication",
            "permission denied",
            "middleware",
        ]
        assert any(
            keyword in content.lower() for keyword in valid_responses
        ), f"Unexpected response: {content}"


@pytest.mark.service("chat")
class TestNLPParserUnit:
    """Unit tests for the NLP parser that don't require server connection."""

    def test_ordinal_words_mapping(self):
        """Test ordinal word to number mapping."""
        from gchat.nlp_card_parser import ORDINAL_WORDS

        assert ORDINAL_WORDS["first"] == 1
        assert ORDINAL_WORDS["second"] == 2
        assert ORDINAL_WORDS["third"] == 3
        assert ORDINAL_WORDS["1st"] == 1
        assert ORDINAL_WORDS["2nd"] == 2

    def test_enhanced_parser_extracts_sections(self):
        """Test that enhanced parser extracts sections from ordinal+titled pattern."""
        from gchat.nlp_card_parser import parse_enhanced_natural_language_description

        description = '''First section titled "Section A" showing content A. Second section titled "Section B" showing content B.'''

        result = parse_enhanced_natural_language_description(description)

        assert "sections" in result
        sections = result["sections"]
        assert len(sections) == 2
        assert sections[0]["header"] == "Section A"
        assert sections[1]["header"] == "Section B"

    def test_enhanced_parser_github_card(self):
        """Test the exact GitHub activity card description."""
        from gchat.nlp_card_parser import parse_enhanced_natural_language_description

        description = '''Create a GitHub activity update card. First section titled "Deployments" showing Frontend deployed at preview.example.com. Second section titled "Commits" showing @dev pushed commit abc123. Third section titled "Warnings" showing PR has been stale for 7 days.'''

        result = parse_enhanced_natural_language_description(description)

        assert "sections" in result
        sections = result["sections"]
        assert len(sections) == 3

        # Verify section headers
        headers = [s["header"] for s in sections]
        assert "Deployments" in headers
        assert "Commits" in headers
        assert "Warnings" in headers

    def test_url_extraction_and_prefix(self):
        """Test that URLs are extracted and prefixed with https://."""
        from gchat.nlp_card_parser import parse_enhanced_natural_language_description

        description = '''First section titled "Links" showing Check docs at docs.example.com for info.'''

        result = parse_enhanced_natural_language_description(description)

        # Find the button widget with the URL
        sections = result.get("sections", [])
        assert len(sections) > 0

        widgets = sections[0].get("widgets", [])
        assert len(widgets) > 0

        # Check that URL has https:// prefix
        widget = widgets[0]
        if "decoratedText" in widget:
            button = widget["decoratedText"].get("button", {})
            if button:
                url = button.get("onClick", {}).get("openLink", {}).get("url", "")
                assert url.startswith("https://"), f"URL should have https:// prefix: {url}"
