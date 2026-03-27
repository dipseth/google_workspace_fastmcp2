"""Unit tests for SlotAffinityNet and slot_assignment inference glue."""

import pytest
import torch

from research.trm.h2.slot_assigner import (
    COMPONENT_TO_POOL,
    POOL_SPECIFICITY_ORDER,
    POOL_VOCAB,
    SlotAffinityNet,
)


class TestSlotAffinityNet:
    """Test the model architecture."""

    def test_forward_shape(self):
        model = SlotAffinityNet(content_dim=384, slot_embed_dim=16, n_slot_types=5, hidden=32)
        content = torch.randn(5, 384)
        output = model(content)
        assert output.shape == (5, 5)

    def test_score_all_slots_shape(self):
        model = SlotAffinityNet(content_dim=384, slot_embed_dim=16, n_slot_types=5, hidden=32)
        content = torch.randn(3, 384)
        output = model.score_all_slots(content)
        assert output.shape == (3, 5)

    def test_single_item(self):
        model = SlotAffinityNet()
        content = torch.randn(1, 384)
        scores = model.score_all_slots(content)
        assert scores.shape == (1, 5)
        # Should produce different scores for different pools
        assert not torch.allclose(scores[0, 0], scores[0, 1])

    def test_parameter_count(self):
        model = SlotAffinityNet(content_dim=384, slot_embed_dim=16, n_slot_types=5, hidden=32)
        n_params = sum(p.numel() for p in model.parameters())
        # Embedding: 5 * 16 = 80
        # Linear(400, 32): 400*32 + 32 = 12832
        # Linear(32, 1): 32 + 1 = 33
        # Total: ~12945
        assert 10000 < n_params < 20000, f"Expected ~13K params, got {n_params}"

    def test_deterministic_eval(self):
        model = SlotAffinityNet()
        model.eval()
        content = torch.randn(2, 384)
        with torch.no_grad():
            s1 = model.score_all_slots(content)
            s2 = model.score_all_slots(content)
        assert torch.allclose(s1, s2)


class TestSlotConstants:
    """Test the vocabulary and mapping constants."""

    def test_vocab_completeness(self):
        assert len(POOL_VOCAB) == 5
        assert all(isinstance(v, int) for v in POOL_VOCAB.values())
        assert set(POOL_VOCAB.values()) == set(range(5))

    def test_component_to_pool_mapping(self):
        # Key components should map to pools
        assert COMPONENT_TO_POOL["Button"] == "buttons"
        assert COMPONENT_TO_POOL["DecoratedText"] == "content_texts"
        assert COMPONENT_TO_POOL["Chip"] == "chips"
        assert COMPONENT_TO_POOL["GridItem"] == "grid_items"
        assert COMPONENT_TO_POOL["CarouselCard"] == "carousel_cards"

    def test_specificity_order(self):
        # All pool keys should appear in specificity order
        for pool_key in POOL_VOCAB:
            assert pool_key in POOL_SPECIFICITY_ORDER

    def test_pool_keys_valid(self):
        valid_pools = {"buttons", "content_texts", "chips", "grid_items", "carousel_cards"}
        for pool in COMPONENT_TO_POOL.values():
            assert pool in valid_pools, f"Invalid pool: {pool}"


class TestSlotAssignment:
    """Test the inference glue functions."""

    def test_extract_item_text_string(self):
        from gchat.card_builder.slot_assignment import _extract_item_text
        assert _extract_item_text("hello") == "hello"

    def test_extract_item_text_dict(self):
        from gchat.card_builder.slot_assignment import _extract_item_text
        assert _extract_item_text({"text": "Deploy"}) == "Deploy"
        assert _extract_item_text({"title": "Server 1"}) == "Server 1"
        assert _extract_item_text({"label": "Bug"}) == "Bug"

    def test_extract_item_text_empty(self):
        from gchat.card_builder.slot_assignment import _extract_item_text
        assert _extract_item_text({}) == ""
        assert _extract_item_text(42) == ""

    def test_rewrap_to_buttons(self):
        from gchat.card_builder.slot_assignment import _rewrap_item
        result = _rewrap_item({"text": "Deploy", "icon": "rocket"}, "content_texts", "buttons")
        assert result["text"] == "Deploy"
        assert result["icon"] == "rocket"
        assert "url" in result

    def test_rewrap_to_chips(self):
        from gchat.card_builder.slot_assignment import _rewrap_item
        result = _rewrap_item({"text": "Bug"}, "content_texts", "chips")
        assert result["label"] == "Bug"
        assert "url" in result

    def test_rewrap_to_content_texts(self):
        from gchat.card_builder.slot_assignment import _rewrap_item
        result = _rewrap_item({"text": "Deploy", "url": "http://example.com"}, "buttons", "content_texts")
        assert result["text"] == "Deploy"
        assert result["wrapText"] is True

    def test_rewrap_preserves_fields(self):
        from gchat.card_builder.slot_assignment import _rewrap_item
        original = {"text": "Deploy", "url": "http://deploy.com", "icon": "rocket"}
        result = _rewrap_item(original, "buttons", "content_texts")
        assert result["url"] == "http://deploy.com"
        assert result["icon"] == "rocket"

    def test_reassign_no_model_returns_original(self):
        """Without a model checkpoint, reassign should return original."""
        from gchat.card_builder.slot_assignment import reassign_supply_map

        supply_map = {
            "buttons": [{"text": "Deploy"}],
            "content_texts": [{"text": "Status: Online"}],
            "chips": [],
            "grid_items": [],
            "carousel_cards": [],
        }
        demands = {"Button": 1, "DecoratedText": 1}

        # Reset the cached model state for this test
        import gchat.card_builder.slot_assignment as sa
        old_attempted = sa._model_load_attempted
        old_model = sa._cached_model
        sa._model_load_attempted = False
        sa._cached_model = None

        try:
            result = reassign_supply_map(supply_map, demands)
            # Without a model, should return original supply_map
            assert result is supply_map or result == supply_map
        finally:
            sa._model_load_attempted = old_attempted
            sa._cached_model = old_model

    def test_reassign_single_item_pool(self):
        """Pools with 0-1 items should not change."""
        from gchat.card_builder.slot_assignment import reassign_supply_map
        import gchat.card_builder.slot_assignment as sa

        # Force model to be "not available"
        old_attempted = sa._model_load_attempted
        old_model = sa._cached_model
        sa._model_load_attempted = True
        sa._cached_model = None

        try:
            supply_map = {
                "buttons": [{"text": "Deploy"}],
                "content_texts": [],
                "chips": [],
                "grid_items": [],
                "carousel_cards": [],
            }
            result = reassign_supply_map(supply_map, {"Button": 1})
            assert result is supply_map
        finally:
            sa._model_load_attempted = old_attempted
            sa._cached_model = old_model
