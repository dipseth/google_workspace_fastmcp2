"""
Tests for the email feedback system.

Covers:
- URL signing (generate + verify round-trip, expiry, tampering, one-time use)
- EmailFeedbackBuilder (block generation, prompt selection, layouts)
- Feedback block rendering via MJML
- Integration with _render_email_spec
"""

import os
import time

import pytest

# ---------------------------------------------------------------------------
# URL signing tests
# ---------------------------------------------------------------------------


class TestFeedbackUrlSigning:
    """Test HMAC-based signed redirect URL generation and verification."""

    def setup_method(self):
        """Reset consumed tokens before each test."""
        from gmail.email_feedback.urls import reset_consumed_tokens

        reset_consumed_tokens()

    def test_generate_url_structure(self):
        """Generated URL contains all required query params."""
        from gmail.email_feedback.urls import generate_feedback_url

        url = generate_feedback_url(
            base_url="https://example.com",
            email_id="test_email_123",
            action="positive",
            feedback_type="content",
        )

        assert url.startswith("https://example.com/email-feedback?")
        assert "eid=test_email_123" in url
        assert "action=positive" in url
        assert "type=content" in url
        assert "exp=" in url
        assert "sig=" in url

    def test_generate_verify_roundtrip(self):
        """A generated URL can be successfully verified."""
        from urllib.parse import parse_qs, urlparse

        from gmail.email_feedback.urls import (
            generate_feedback_url,
            verify_feedback_url,
        )

        url = generate_feedback_url(
            base_url="https://example.com",
            email_id="roundtrip_test",
            action="negative",
            feedback_type="layout",
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        is_valid, error = verify_feedback_url(
            email_id=params["eid"][0],
            action=params["action"][0],
            feedback_type=params["type"][0],
            exp=params["exp"][0],
            sig=params["sig"][0],
        )

        assert is_valid, f"Verification failed: {error}"
        assert error == ""

    def test_tampered_signature_rejected(self):
        """A URL with a modified signature is rejected."""
        from urllib.parse import parse_qs, urlparse

        from gmail.email_feedback.urls import (
            generate_feedback_url,
            verify_feedback_url,
        )

        url = generate_feedback_url(
            base_url="https://example.com",
            email_id="tamper_test",
            action="positive",
            feedback_type="content",
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        is_valid, error = verify_feedback_url(
            email_id=params["eid"][0],
            action=params["action"][0],
            feedback_type=params["type"][0],
            exp=params["exp"][0],
            sig="0000" + params["sig"][0][4:],  # tamper with signature
        )

        assert not is_valid
        assert "signature" in error.lower()

    def test_tampered_action_rejected(self):
        """Changing the action param invalidates the signature."""
        from urllib.parse import parse_qs, urlparse

        from gmail.email_feedback.urls import (
            generate_feedback_url,
            verify_feedback_url,
        )

        url = generate_feedback_url(
            base_url="https://example.com",
            email_id="action_tamper",
            action="positive",
            feedback_type="content",
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Flip action from positive to negative
        is_valid, error = verify_feedback_url(
            email_id=params["eid"][0],
            action="negative",  # tampered
            feedback_type=params["type"][0],
            exp=params["exp"][0],
            sig=params["sig"][0],
        )

        assert not is_valid

    def test_expired_token_rejected(self):
        """An expired token is rejected."""
        from urllib.parse import parse_qs, urlparse

        from gmail.email_feedback.urls import (
            generate_feedback_url,
            verify_feedback_url,
        )

        url = generate_feedback_url(
            base_url="https://example.com",
            email_id="expiry_test",
            action="positive",
            feedback_type="content",
            ttl_seconds=-1,  # Already expired
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        is_valid, error = verify_feedback_url(
            email_id=params["eid"][0],
            action=params["action"][0],
            feedback_type=params["type"][0],
            exp=params["exp"][0],
            sig=params["sig"][0],
        )

        assert not is_valid
        assert "expired" in error.lower()

    def test_one_time_use(self):
        """A token can only be used once."""
        from urllib.parse import parse_qs, urlparse

        from gmail.email_feedback.urls import (
            generate_feedback_url,
            verify_feedback_url,
        )

        url = generate_feedback_url(
            base_url="https://example.com",
            email_id="oneuse_test",
            action="positive",
            feedback_type="content",
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        kwargs = {
            "email_id": params["eid"][0],
            "action": params["action"][0],
            "feedback_type": params["type"][0],
            "exp": params["exp"][0],
            "sig": params["sig"][0],
        }

        # First use should succeed
        is_valid, _ = verify_feedback_url(**kwargs)
        assert is_valid

        # Second use should fail
        is_valid, error = verify_feedback_url(**kwargs)
        assert not is_valid
        assert "already" in error.lower()

    def test_no_consume_mode(self):
        """verify with consume=False does not consume the token."""
        from urllib.parse import parse_qs, urlparse

        from gmail.email_feedback.urls import (
            generate_feedback_url,
            verify_feedback_url,
        )

        url = generate_feedback_url(
            base_url="https://example.com",
            email_id="noconsume_test",
            action="positive",
            feedback_type="content",
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        kwargs = {
            "email_id": params["eid"][0],
            "action": params["action"][0],
            "feedback_type": params["type"][0],
            "exp": params["exp"][0],
            "sig": params["sig"][0],
        }

        # Verify without consuming
        is_valid, _ = verify_feedback_url(**kwargs, consume=False)
        assert is_valid

        # Should still be usable
        is_valid, _ = verify_feedback_url(**kwargs, consume=True)
        assert is_valid


# ---------------------------------------------------------------------------
# EmailFeedbackBuilder tests
# ---------------------------------------------------------------------------


class TestEmailFeedbackBuilder:
    """Test the EmailFeedbackBuilder block generation."""

    def test_build_feedback_blocks_returns_blocks(self):
        """build_feedback_blocks returns a list of EmailBlock instances."""
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import EmailBlock

        builder = EmailFeedbackBuilder()
        blocks = builder.build_feedback_blocks(
            email_id="test_email",
            base_url="https://example.com",
            feedback_type="content",
            layout="with_divider",
            button_style="standard",
        )

        assert isinstance(blocks, list)
        assert len(blocks) >= 3  # DividerBlock + TextBlock + 2 ButtonBlocks
        for block in blocks:
            assert isinstance(block, EmailBlock)

    def test_build_feedback_blocks_compact_layout(self):
        """Compact layout skips the divider block."""
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import DividerBlock

        builder = EmailFeedbackBuilder()
        blocks = builder.build_feedback_blocks(
            email_id="test_compact",
            base_url="https://example.com",
            feedback_type="content",
            layout="compact",
            button_style="standard",
        )

        # Compact should not have a divider
        dividers = [b for b in blocks if isinstance(b, DividerBlock)]
        assert len(dividers) == 0

    def test_build_feedback_blocks_with_divider(self):
        """with_divider layout includes a DividerBlock."""
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import DividerBlock

        builder = EmailFeedbackBuilder()
        blocks = builder.build_feedback_blocks(
            email_id="test_divider",
            base_url="https://example.com",
            feedback_type="content",
            layout="with_divider",
            button_style="standard",
        )

        dividers = [b for b in blocks if isinstance(b, DividerBlock)]
        assert len(dividers) == 1

    def test_button_blocks_have_signed_urls(self):
        """ButtonBlocks contain signed redirect URLs."""
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import ButtonBlock

        builder = EmailFeedbackBuilder()
        blocks = builder.build_feedback_blocks(
            email_id="test_urls",
            base_url="https://example.com",
            feedback_type="content",
            layout="compact",
            button_style="standard",
        )

        buttons = [b for b in blocks if isinstance(b, ButtonBlock)]
        assert len(buttons) == 2  # positive + negative

        for btn in buttons:
            assert "https://example.com/email-feedback?" in btn.url
            assert "sig=" in btn.url
            assert "eid=test_urls" in btn.url

        # One should be positive, one negative
        urls = [btn.url for btn in buttons]
        assert any("action=positive" in u for u in urls)
        assert any("action=negative" in u for u in urls)

    def test_button_styles_applied(self):
        """Button style colors are applied from BUTTON_STYLES registry."""
        from gmail.email_feedback.components import BUTTON_STYLES
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import ButtonBlock

        builder = EmailFeedbackBuilder()
        blocks = builder.build_feedback_blocks(
            email_id="test_style",
            base_url="https://example.com",
            feedback_type="content",
            layout="compact",
            button_style="standard",
        )

        buttons = [b for b in blocks if isinstance(b, ButtonBlock)]
        style = BUTTON_STYLES["standard"]

        # First button (positive) should have positive color
        assert buttons[0].background_color == style["positive_bg"]
        assert buttons[1].background_color == style["negative_bg"]

    def test_dual_feedback_blocks(self):
        """build_dual_feedback_blocks produces content + layout feedback."""
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import ButtonBlock

        builder = EmailFeedbackBuilder()
        blocks = builder.build_dual_feedback_blocks(
            email_id="test_dual",
            base_url="https://example.com",
        )

        # Should have buttons for both content and layout
        buttons = [b for b in blocks if isinstance(b, ButtonBlock)]
        urls = [btn.url for btn in buttons]

        content_urls = [u for u in urls if "type=content" in u]
        layout_urls = [u for u in urls if "type=layout" in u]

        assert len(content_urls) >= 2  # pos + neg for content
        assert len(layout_urls) >= 2  # pos + neg for layout

    def test_emoji_labels(self):
        """use_emoji=True produces emoji labels on buttons."""
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import ButtonBlock

        builder = EmailFeedbackBuilder()
        blocks = builder.build_feedback_blocks(
            email_id="test_emoji",
            base_url="https://example.com",
            feedback_type="content",
            layout="compact",
            button_style="standard",
            use_emoji=True,
        )

        buttons = [b for b in blocks if isinstance(b, ButtonBlock)]
        # At least one button should have an emoji character
        texts = [btn.text for btn in buttons]
        has_emoji = any(any(ord(c) > 127 for c in t) for t in texts)
        assert has_emoji, f"Expected emoji in labels, got: {texts}"


# ---------------------------------------------------------------------------
# MJML rendering tests
# ---------------------------------------------------------------------------


class TestEmailFeedbackRendering:
    """Test that feedback blocks render correctly to MJML/HTML."""

    def test_feedback_blocks_render_to_mjml(self):
        """Feedback blocks produce valid MJML via to_mjml()."""
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import EmailTheme

        builder = EmailFeedbackBuilder()
        blocks = builder.build_feedback_blocks(
            email_id="render_test",
            base_url="https://example.com",
            feedback_type="content",
            layout="with_divider",
            button_style="standard",
        )

        theme = EmailTheme()
        for block in blocks:
            mjml = block.to_mjml(theme)
            assert isinstance(mjml, str)
            assert len(mjml) > 0

    def test_button_blocks_render_with_href(self):
        """ButtonBlocks render to <mj-button> with signed href."""
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import ButtonBlock, EmailTheme

        builder = EmailFeedbackBuilder()
        blocks = builder.build_feedback_blocks(
            email_id="href_test",
            base_url="https://example.com",
            feedback_type="content",
            layout="compact",
            button_style="standard",
        )

        theme = EmailTheme()
        buttons = [b for b in blocks if isinstance(b, ButtonBlock)]

        for btn in buttons:
            mjml = btn.to_mjml(theme)
            assert "<mj-button" in mjml
            assert 'href="https://example.com/email-feedback?' in mjml
            assert "sig=" in mjml

    def test_email_spec_with_feedback_blocks(self):
        """An EmailSpec with feedback blocks renders to valid MJML."""
        from gmail.email_feedback.dynamic import EmailFeedbackBuilder
        from gmail.mjml_types import EmailSpec, TextBlock

        builder = EmailFeedbackBuilder()
        feedback_blocks = builder.build_feedback_blocks(
            email_id="spec_test",
            base_url="https://example.com",
            feedback_type="content",
            layout="with_divider",
            button_style="standard",
        )

        spec = EmailSpec(
            subject="Test Email",
            blocks=[
                TextBlock(text="Hello, world!"),
                *feedback_blocks,
            ],
        )

        mjml = spec.to_mjml()
        assert "<mjml>" in mjml
        assert "<mj-button" in mjml
        assert "email-feedback" in mjml
        assert "Hello, world!" in mjml


# ---------------------------------------------------------------------------
# Prompt and style tests
# ---------------------------------------------------------------------------


class TestPrompts:
    """Test prompt selection and styling."""

    def test_style_keyword_all_styles(self):
        """style_keyword produces HTML for all defined styles."""
        from gmail.email_feedback.prompts import FEEDBACK_TEXT_STYLES, style_keyword

        for style in FEEDBACK_TEXT_STYLES:
            result = style_keyword("test", style)
            assert "test" in result
            assert isinstance(result, str)

    def test_style_keyword_bold(self):
        from gmail.email_feedback.prompts import style_keyword

        assert style_keyword("word", "bold") == "<b>word</b>"

    def test_style_keyword_color_blue(self):
        from gmail.email_feedback.prompts import style_keyword

        result = style_keyword("word", "color_blue")
        assert "#4285f4" in result
        assert "word" in result

    def test_prompt_templates_have_keyword_placeholder(self):
        """All prompt templates contain {keyword} placeholder."""
        from gmail.email_feedback.prompts import (
            CONTENT_FEEDBACK_PROMPTS,
            LAYOUT_FEEDBACK_PROMPTS,
        )

        for template, keyword in CONTENT_FEEDBACK_PROMPTS:
            assert "{keyword}" in template
            assert isinstance(keyword, str)

        for template, keyword in LAYOUT_FEEDBACK_PROMPTS:
            assert "{keyword}" in template
            assert isinstance(keyword, str)


# ---------------------------------------------------------------------------
# Component registry tests
# ---------------------------------------------------------------------------


class TestComponents:
    """Test component registries are well-formed."""

    def test_button_styles_have_required_keys(self):
        from gmail.email_feedback.components import BUTTON_STYLES

        for name, style in BUTTON_STYLES.items():
            assert "positive_bg" in style, f"{name} missing positive_bg"
            assert "negative_bg" in style, f"{name} missing negative_bg"
            assert "text_color" in style, f"{name} missing text_color"

    def test_layout_wrappers_non_empty(self):
        from gmail.email_feedback.components import LAYOUT_WRAPPERS

        assert len(LAYOUT_WRAPPERS) >= 2

    def test_text_components_non_empty(self):
        from gmail.email_feedback.components import TEXT_COMPONENTS

        assert len(TEXT_COMPONENTS) >= 1

    def test_clickable_components_non_empty(self):
        from gmail.email_feedback.components import CLICKABLE_COMPONENTS

        assert len(CLICKABLE_COMPONENTS) >= 1
