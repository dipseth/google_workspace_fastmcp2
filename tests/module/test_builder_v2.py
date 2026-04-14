"""Unit tests for SmartCardBuilderV2."""

from unittest.mock import MagicMock, patch

import pytest


class TestSmartCardBuilderV2Init:
    """Test builder initialization and infrastructure."""

    def test_builder_creates_without_errors(self):
        from gchat.card_builder.builder_v2 import SmartCardBuilderV2

        builder = SmartCardBuilderV2()
        assert builder._wrapper is None
        assert builder._qdrant_client is None

    def test_builder_wrapper_returns_none_gracefully(self):
        from gchat.card_builder.builder_v2 import SmartCardBuilderV2

        builder = SmartCardBuilderV2()
        with patch(
            "gchat.card_framework_wrapper.get_card_framework_wrapper",
            side_effect=ImportError,
        ):
            result = builder._get_wrapper()
            # Should not raise, returns None
            assert result is None


class TestComponentParams:
    """Test COMPONENT_PARAMS constant is well-formed."""

    def test_component_params_is_nonempty_dict(self):
        from gchat.card_builder.constants import COMPONENT_PARAMS

        assert isinstance(COMPONENT_PARAMS, dict)
        assert len(COMPONENT_PARAMS) > 0

    def test_each_component_has_field_dict(self):
        from gchat.card_builder.constants import COMPONENT_PARAMS

        for comp_name, fields in COMPONENT_PARAMS.items():
            assert isinstance(fields, dict), f"{comp_name} fields should be dict"

    def test_key_components_present(self):
        from gchat.card_builder.constants import COMPONENT_PARAMS

        expected = ["Button", "DecoratedText", "TextParagraph", "Image"]
        for comp in expected:
            assert comp in COMPONENT_PARAMS, f"Missing component: {comp}"


class TestSupplyMapConstruction:
    """Test supply map building and slot assignment integration."""

    def test_gchat_domain_pools_are_valid(self):
        from adapters.domain_config import GCHAT_DOMAIN

        expected_pools = {
            "buttons",
            "content_texts",
            "grid_items",
            "chips",
            "carousel_cards",
        }
        assert set(GCHAT_DOMAIN.pool_vocab.keys()) == expected_pools

    def test_supply_map_has_all_pools(self):
        """A supply map should have entries for all GCHAT pools."""
        from adapters.domain_config import GCHAT_DOMAIN

        supply_map = {pool: [] for pool in GCHAT_DOMAIN.pool_vocab}
        assert len(supply_map) == 5
        for pool in GCHAT_DOMAIN.pool_vocab:
            assert pool in supply_map


class TestSlotAssignmentFallback:
    """Test that slot assignment gracefully handles missing model."""

    def test_reassign_returns_original_on_no_model(self):
        """When no model is available, reassign_supply_map returns original."""
        from gchat.card_builder.slot_assignment import reassign_supply_map

        supply_map = {
            "buttons": ["Click me"],
            "content_texts": ["Hello world"],
            "grid_items": [],
            "chips": [],
            "carousel_cards": [],
        }
        demands = {"Button": 1, "DecoratedText": 1}

        # With no model loaded, should return original supply_map
        with patch(
            "gchat.card_builder.slot_assignment._load_slot_model", return_value=None
        ):
            result = reassign_supply_map(supply_map, demands)
            # Should not crash, returns a dict
            assert isinstance(result, dict)
            # Should preserve existing content
            assert "buttons" in result
            assert "content_texts" in result


class TestGchatCardBuilder:
    """Test the GchatCardBuilder protocol wrapper."""

    def test_gchat_builder_satisfies_protocol(self):
        from adapters.module_wrapper.builder_base import BuilderProtocol
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        assert isinstance(builder, BuilderProtocol)

    def test_gchat_builder_domain_id(self):
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        assert builder.domain_id == "gchat"

    def test_gchat_builder_registry_has_components(self):
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        assert len(builder.registry) > 0
        assert "Button" in builder.registry

    def test_gchat_builder_registry_pools_match_domain(self):
        from adapters.domain_config import GCHAT_DOMAIN
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        for comp_name in builder.registry.list_components():
            pool = builder.registry.get_pool(comp_name)
            assert pool in GCHAT_DOMAIN.pool_vocab, (
                f"{comp_name} pool '{pool}' not in domain"
            )

    def test_gchat_builder_build_supply_map(self):
        from adapters.module_wrapper.builder_base import ParsedStructure
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        parsed = ParsedStructure(
            content_items={"content_texts": ["Hello"], "buttons": ["Click"]},
            raw_dsl="§[δ, ᵬ]",
        )
        supply_map = builder.build_supply_map(parsed)
        assert "content_texts" in supply_map
        assert "buttons" in supply_map
        assert "Hello" in supply_map["content_texts"]
        assert "Click" in supply_map["buttons"]

    def test_gchat_builder_reassign_slots_with_domain(self):
        """reassign_slots passes GCHAT_DOMAIN to slot_assignment."""
        from adapters.domain_config import GCHAT_DOMAIN
        from gchat.card_builder.builder_v3 import GchatCardBuilder

        builder = GchatCardBuilder()
        supply_map = {pool: [] for pool in GCHAT_DOMAIN.pool_vocab}
        supply_map["content_texts"] = ["Hello"]

        with patch(
            "gchat.card_builder.slot_assignment.reassign_supply_map"
        ) as mock_reassign:
            mock_reassign.return_value = supply_map
            result = builder.reassign_slots(supply_map, {"DecoratedText": 1})
            # Verify domain_config was passed
            mock_reassign.assert_called_once()
            call_kwargs = mock_reassign.call_args
            assert call_kwargs.kwargs.get("domain_config") is GCHAT_DOMAIN
