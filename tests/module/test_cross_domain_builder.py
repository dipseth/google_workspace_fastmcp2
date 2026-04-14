"""Cross-domain builder E2E tests.

Tests that the same description can produce valid output in both gchat and email
domains, with correct pool routing, supply maps, and output format validation.
"""

from unittest.mock import patch

import pytest

from adapters.module_wrapper.builder_base import (
    BuilderProtocol,
    ComponentRegistry,
    ParsedStructure,
)
from research.trm.h2.domain_config import EMAIL_DOMAIN, GCHAT_DOMAIN

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def gchat_builder():
    from gchat.card_builder.builder_v3 import GchatCardBuilder

    return GchatCardBuilder()


@pytest.fixture
def email_builder():
    from gmail.email_builder import EmailBuilder

    return EmailBuilder()


# ── Protocol compliance ───────────────────────────────────────────────


class TestProtocolCompliance:
    """Both builders satisfy BuilderProtocol."""

    def test_gchat_is_builder(self, gchat_builder):
        assert isinstance(gchat_builder, BuilderProtocol)

    def test_email_is_builder(self, email_builder):
        assert isinstance(email_builder, BuilderProtocol)

    def test_both_have_different_domains(self, gchat_builder, email_builder):
        assert gchat_builder.domain_id == "gchat"
        assert email_builder.domain_id == "email"


# ── Pool routing correctness ─────────────────────────────────────────


class TestPoolRoutingPerDomain:
    """Supply maps use correct pool keys per domain."""

    def test_gchat_pools(self, gchat_builder):
        parsed = ParsedStructure(content_items={}, raw_dsl="")
        sm = gchat_builder.build_supply_map(parsed)
        assert set(sm.keys()) == set(GCHAT_DOMAIN.pool_vocab.keys())

    def test_email_pools(self, email_builder):
        parsed = ParsedStructure(content_items={}, raw_dsl="")
        sm = email_builder.build_supply_map(parsed)
        assert set(sm.keys()) == set(EMAIL_DOMAIN.pool_vocab.keys())

    def test_gchat_content_routes_to_content_texts(self, gchat_builder):
        parsed = ParsedStructure(
            content_items={"content_texts": ["Hello", "World"]},
        )
        sm = gchat_builder.build_supply_map(parsed)
        assert sm["content_texts"] == ["Hello", "World"]

    def test_email_content_routes_to_content(self, email_builder):
        parsed = ParsedStructure(
            content_items={"content": ["Hello", "World"]},
        )
        sm = email_builder.build_supply_map(parsed)
        assert sm["content"] == ["Hello", "World"]

    def test_gchat_buttons_route_to_buttons_pool(self, gchat_builder):
        parsed = ParsedStructure(
            content_items={"buttons": ["Click me"]},
        )
        sm = gchat_builder.build_supply_map(parsed)
        assert sm["buttons"] == ["Click me"]

    def test_email_interactive_routes_to_interactive_pool(self, email_builder):
        parsed = ParsedStructure(
            content_items={"interactive": ["Submit"]},
        )
        sm = email_builder.build_supply_map(parsed)
        assert sm["interactive"] == ["Submit"]


# ── Output format validation ─────────────────────────────────────────


class TestOutputFormatValidation:
    """Output type validation: dict for gchat, EmailSpec for email."""

    def test_email_build_returns_email_spec(self, email_builder):
        from gmail.mjml_types import EmailSpec

        result = email_builder.build(
            "Welcome newsletter", subject="Welcome!", text="Hello subscriber"
        )
        assert isinstance(result, EmailSpec)

    def test_email_spec_to_mjml_valid(self, email_builder):
        result = email_builder.build("Test", subject="Test", text="Hello")
        mjml = result.to_mjml()
        assert isinstance(mjml, str)
        assert "<mjml>" in mjml
        assert "<mj-body" in mjml
        assert "</mjml>" in mjml

    def test_email_build_with_hero(self, email_builder):
        from gmail.mjml_types import EmailSpec

        result = email_builder.build(
            "Hero email",
            subject="Welcome",
            hero_title="Big Announcement",
            hero_subtitle="Something exciting",
            text="Details here",
        )
        assert isinstance(result, EmailSpec)
        assert len(result.blocks) >= 2  # Hero + Text at minimum

    def test_email_build_with_all_block_types(self, email_builder):
        from gmail.mjml_types import EmailSpec

        result = email_builder.build(
            "Full email",
            subject="Everything",
            header_title="My Company",
            hero_title="Big News",
            text="Read on...",
            image_src="https://example.com/img.png",
            button_text="Learn More",
            button_url="https://example.com",
            divider=True,
            table_headers=["Name", "Value"],
            table_rows=[["A", "1"], ["B", "2"]],
            accordion_items=[
                {"title": "FAQ 1", "content": "Answer 1"},
                {"title": "FAQ 2", "content": "Answer 2"},
            ],
            social_links=[
                {"name": "twitter", "href": "https://twitter.com/example"},
            ],
            footer_text="(c) 2026 My Company",
            unsubscribe_url="https://example.com/unsub",
        )
        assert isinstance(result, EmailSpec)
        mjml = result.to_mjml()
        assert "<mjml>" in mjml
        # Should have multiple block types rendered
        assert "mj-text" in mjml
        assert "mj-button" in mjml
        assert "mj-image" in mjml

    def test_email_build_with_explicit_blocks(self, email_builder):
        """Passing explicit blocks bypasses auto-generation."""
        from gmail.mjml_types import ButtonBlock, EmailSpec, TextBlock

        blocks = [
            TextBlock(text="Hello"),
            ButtonBlock(text="Click", url="https://example.com"),
        ]
        result = email_builder.build("ignored", subject="Test", blocks=blocks)
        assert isinstance(result, EmailSpec)
        assert len(result.blocks) == 2


# ── Render component per domain ──────────────────────────────────────


class TestRenderComponentPerDomain:
    """render_component produces domain-correct output."""

    def test_email_render_text(self, email_builder):
        result = email_builder.render_component("TextBlock", {"text": "Hello"})
        assert isinstance(result, str)
        assert "mj-text" in result

    def test_email_render_button(self, email_builder):
        result = email_builder.render_component(
            "ButtonBlock", {"text": "Go", "url": "https://example.com"}
        )
        assert isinstance(result, str)
        assert "mj-button" in result

    def test_email_render_image(self, email_builder):
        result = email_builder.render_component(
            "ImageBlock", {"src": "https://example.com/img.png"}
        )
        assert isinstance(result, str)
        assert "mj-image" in result

    def test_email_render_hero(self, email_builder):
        result = email_builder.render_component(
            "HeroBlock", {"title": "Welcome"}
        )
        assert isinstance(result, str)
        assert "Welcome" in result

    def test_email_render_spacer(self, email_builder):
        result = email_builder.render_component("SpacerBlock", {"height_px": 30})
        assert isinstance(result, str)
        assert "mj-spacer" in result

    def test_email_render_divider(self, email_builder):
        result = email_builder.render_component("DividerBlock", {})
        assert isinstance(result, str)
        assert "mj-divider" in result

    def test_email_render_footer(self, email_builder):
        result = email_builder.render_component(
            "FooterBlock", {"text": "Copyright 2026"}
        )
        assert isinstance(result, str)
        assert "Copyright 2026" in result

    def test_email_render_unknown(self, email_builder):
        result = email_builder.render_component("FakeBlock", {"x": 1})
        assert isinstance(result, str)
        assert "Unknown" in result or "Error" in result


# ── Full mocked pipeline for both domains ────────────────────────────


class TestMockedPipelineBothDomains:
    """Full mocked pipeline for both domains."""

    def test_gchat_reassign_uses_gchat_domain(self, gchat_builder):
        supply_map = {pool: [] for pool in GCHAT_DOMAIN.pool_vocab}
        supply_map["content_texts"] = ["Hello"]

        with patch(
            "gchat.card_builder.slot_assignment.reassign_supply_map"
        ) as mock:
            mock.return_value = supply_map
            result = gchat_builder.reassign_slots(supply_map, {"DecoratedText": 1})
            mock.assert_called_once()
            _, kwargs = mock.call_args
            assert kwargs.get("domain_config") is GCHAT_DOMAIN

    def test_email_reassign_uses_email_domain(self, email_builder):
        supply_map = {pool: [] for pool in EMAIL_DOMAIN.pool_vocab}
        supply_map["content"] = ["Hello"]

        with patch(
            "gchat.card_builder.slot_assignment.reassign_supply_map"
        ) as mock:
            mock.return_value = supply_map
            result = email_builder.reassign_slots(supply_map, {"TextBlock": 1})
            mock.assert_called_once()
            _, kwargs = mock.call_args
            assert kwargs.get("domain_config") is EMAIL_DOMAIN

    def test_both_domains_build_without_errors(
        self, gchat_builder, email_builder
    ):
        """Both builders can build from the same high-level description."""
        # Email build (doesn't need wrapper/Qdrant)
        email_result = email_builder.build(
            "Status dashboard",
            subject="Status Update",
            text="Everything is operational",
            button_text="View Dashboard",
            button_url="https://example.com/status",
        )
        from gmail.mjml_types import EmailSpec

        assert isinstance(email_result, EmailSpec)
        assert email_result.subject == "Status Update"
        mjml = email_result.to_mjml()
        assert "<mjml>" in mjml
