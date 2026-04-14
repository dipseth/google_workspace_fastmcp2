"""Cross-domain builder protocol tests.

Both GchatCardBuilder and EmailBuilder must satisfy BuilderProtocol
and produce domain-correct output.
"""

import pytest

from adapters.module_wrapper.builder_base import (
    BuilderProtocol,
    ComponentRegistry,
    ParsedStructure,
)


class TestBuilderProtocolCompliance:
    """Both builders satisfy BuilderProtocol (structural check)."""

    def test_gchat_builder_isinstance_check(self):
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        assert isinstance(GchatCardBuilder(), BuilderProtocol)

    def test_email_builder_isinstance_check(self):
        from gmail.email_builder import EmailBuilder

        assert isinstance(EmailBuilder(), BuilderProtocol)

    def test_protocol_has_required_methods(self):
        """BuilderProtocol defines the expected interface."""
        import inspect

        members = {name for name, _ in inspect.getmembers(BuilderProtocol)}
        assert "parse_dsl" in members
        assert "build_supply_map" in members
        assert "reassign_slots" in members
        assert "render_component" in members
        assert "build" in members


class TestRegistryPerDomain:
    """Each domain's registry has correct pool assignments."""

    def test_gchat_registry_nonempty(self):
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        assert len(builder.registry) > 0

    def test_email_registry_nonempty(self):
        from gmail.email_builder import EmailBuilder

        builder = EmailBuilder()
        assert len(builder.registry) > 0

    def test_gchat_registry_pools_are_gchat_pools(self):
        from adapters.domain_config import GCHAT_DOMAIN
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        valid_pools = set(GCHAT_DOMAIN.pool_vocab.keys())
        for comp in builder.registry.list_components():
            pool = builder.registry.get_pool(comp)
            assert pool in valid_pools, (
                f"gchat component '{comp}' has invalid pool '{pool}'"
            )

    def test_email_registry_pools_are_email_pools(self):
        from adapters.domain_config import EMAIL_DOMAIN
        from gmail.email_builder import EmailBuilder

        builder = EmailBuilder()
        valid_pools = set(EMAIL_DOMAIN.pool_vocab.keys())
        for comp in builder.registry.list_components():
            pool = builder.registry.get_pool(comp)
            assert pool in valid_pools, (
                f"email component '{comp}' has invalid pool '{pool}'"
            )

    def test_gchat_and_email_have_different_domain_ids(self):
        from gchat.card_builder.builder_v3 import GchatCardBuilder
        from gmail.email_builder import EmailBuilder

        assert GchatCardBuilder().domain_id != EmailBuilder().domain_id

    def test_gchat_has_button_component(self):
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        assert "Button" in GchatCardBuilder().registry

    def test_email_has_textblock_component(self):
        from gmail.email_builder import EmailBuilder

        assert "TextBlock" in EmailBuilder().registry

    def test_email_has_buttonblock_component(self):
        from gmail.email_builder import EmailBuilder

        assert "ButtonBlock" in EmailBuilder().registry


class TestSupplyMapPerDomain:
    """Supply maps use correct pool keys per domain."""

    def test_gchat_supply_map_keys(self):
        from adapters.domain_config import GCHAT_DOMAIN
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        parsed = ParsedStructure(content_items={}, raw_dsl="")
        supply_map = builder.build_supply_map(parsed)
        assert set(supply_map.keys()) == set(GCHAT_DOMAIN.pool_vocab.keys())

    def test_email_supply_map_keys(self):
        from adapters.domain_config import EMAIL_DOMAIN
        from gmail.email_builder import EmailBuilder

        builder = EmailBuilder()
        parsed = ParsedStructure(content_items={}, raw_dsl="")
        supply_map = builder.build_supply_map(parsed)
        assert set(supply_map.keys()) == set(EMAIL_DOMAIN.pool_vocab.keys())

    def test_gchat_supply_map_content_merging(self):
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        parsed = ParsedStructure(
            content_items={"content_texts": ["A", "B"], "buttons": ["C"]},
        )
        sm = builder.build_supply_map(parsed)
        assert sm["content_texts"] == ["A", "B"]
        assert sm["buttons"] == ["C"]

    def test_email_supply_map_content_merging(self):
        from gmail.email_builder import EmailBuilder

        builder = EmailBuilder()
        parsed = ParsedStructure(
            content_items={"content": ["A"], "layout": ["B"]},
        )
        sm = builder.build_supply_map(parsed)
        assert sm["content"] == ["A"]
        assert sm["layout"] == ["B"]


class TestOutputTypeValidation:
    """Output type validation (dict for gchat, MJML for email)."""

    def test_email_build_returns_email_spec(self):
        from gmail.email_builder import EmailBuilder
        from gmail.mjml_types import EmailSpec

        builder = EmailBuilder()
        result = builder.build("Welcome email", subject="Hello")
        assert isinstance(result, EmailSpec)

    def test_email_spec_has_subject(self):
        from gmail.email_builder import EmailBuilder

        builder = EmailBuilder()
        result = builder.build("Test", subject="My Subject")
        assert result.subject == "My Subject"

    def test_email_spec_to_mjml_produces_string(self):
        from gmail.email_builder import EmailBuilder

        builder = EmailBuilder()
        result = builder.build("Test email content", subject="Test")
        mjml = result.to_mjml()
        assert isinstance(mjml, str)
        assert "<mjml>" in mjml

    def test_email_render_component_textblock(self):
        from gmail.email_builder import EmailBuilder

        builder = EmailBuilder()
        result = builder.render_component("TextBlock", {"text": "Hello"})
        assert isinstance(result, str)
        assert "mj-text" in result
        assert "Hello" in result

    def test_email_render_component_buttonblock(self):
        from gmail.email_builder import EmailBuilder

        builder = EmailBuilder()
        result = builder.render_component(
            "ButtonBlock", {"text": "Click", "url": "https://example.com"}
        )
        assert isinstance(result, str)
        assert "mj-button" in result

    def test_email_render_unknown_component(self):
        from gmail.email_builder import EmailBuilder

        builder = EmailBuilder()
        result = builder.render_component("NonExistent", {"text": "test"})
        assert isinstance(result, str)
        assert "Unknown" in result or "Error" in result


class TestComponentRegistryUnit:
    """Unit tests for the ComponentRegistry class."""

    def test_registry_register_and_get(self):
        from adapters.module_wrapper.builder_base import ComponentInfo

        registry = ComponentRegistry(domain_id="test")
        info = ComponentInfo(name="Widget", pool="content", fields={"text": "str"})
        registry.register(info)
        assert registry.get("Widget") is info

    def test_registry_list_components(self):
        from adapters.module_wrapper.builder_base import ComponentInfo

        registry = ComponentRegistry(domain_id="test")
        registry.register(ComponentInfo(name="A", pool="p1"))
        registry.register(ComponentInfo(name="B", pool="p2"))
        assert sorted(registry.list_components()) == ["A", "B"]

    def test_registry_components_for_pool(self):
        from adapters.module_wrapper.builder_base import ComponentInfo

        registry = ComponentRegistry(domain_id="test")
        registry.register(ComponentInfo(name="A", pool="p1"))
        registry.register(ComponentInfo(name="B", pool="p1"))
        registry.register(ComponentInfo(name="C", pool="p2"))
        assert sorted(registry.components_for_pool("p1")) == ["A", "B"]
        assert registry.components_for_pool("p2") == ["C"]

    def test_registry_len_and_contains(self):
        from adapters.module_wrapper.builder_base import ComponentInfo

        registry = ComponentRegistry(domain_id="test")
        registry.register(ComponentInfo(name="X", pool="p"))
        assert len(registry) == 1
        assert "X" in registry
        assert "Y" not in registry

    def test_registry_get_pool(self):
        from adapters.module_wrapper.builder_base import ComponentInfo

        registry = ComponentRegistry(domain_id="test")
        registry.register(ComponentInfo(name="W", pool="mypool"))
        assert registry.get_pool("W") == "mypool"
        assert registry.get_pool("missing") is None
