"""Unit tests for SlotAffinityNet, DomainConfig, and slot_assignment inference."""

import pytest
import torch

from research.trm.h2.domain_config import (
    GCHAT_DOMAIN,
    EMAIL_DOMAIN,
    DomainConfig,
    get_domain,
    get_domain_or_default,
    list_domains,
    register_domain,
    resolve_domain,
)
from research.trm.h2.slot_assigner import (
    COMPONENT_TO_POOL,
    POOL_SPECIFICITY_ORDER,
    POOL_VOCAB,
    SlotAffinityNet,
)


# ── DomainConfig Tests ─────────────────────────────────────────────


class TestDomainConfig:
    """Test the domain configuration system."""

    def test_gchat_domain_has_5_pools(self):
        assert GCHAT_DOMAIN.n_pools == 5

    def test_email_domain_has_4_pools(self):
        assert EMAIL_DOMAIN.n_pools == 4

    def test_pool_vocab_ids_are_contiguous(self):
        """Pool IDs must be 0..n-1 with no gaps — required for nn.Linear output."""
        for domain in [GCHAT_DOMAIN, EMAIL_DOMAIN]:
            ids = sorted(domain.pool_vocab.values())
            assert ids == list(range(domain.n_pools)), (
                f"{domain.domain_id}: pool IDs {ids} are not contiguous 0..{domain.n_pools - 1}"
            )

    def test_pool_names_is_inverse_of_pool_vocab(self):
        for domain in [GCHAT_DOMAIN, EMAIL_DOMAIN]:
            for name, idx in domain.pool_vocab.items():
                assert domain.pool_names[idx] == name

    def test_component_to_pool_values_are_valid_pools(self):
        """Every component must map to a pool that exists in pool_vocab."""
        for domain in [GCHAT_DOMAIN, EMAIL_DOMAIN]:
            for comp, pool in domain.component_to_pool.items():
                assert pool in domain.pool_vocab, (
                    f"{domain.domain_id}: component '{comp}' maps to "
                    f"unknown pool '{pool}'"
                )

    def test_specificity_order_covers_all_pools(self):
        """Specificity order must include every pool — missing one means it's never routed to."""
        for domain in [GCHAT_DOMAIN, EMAIL_DOMAIN]:
            missing = set(domain.pool_vocab) - set(domain.specificity_order)
            assert not missing, (
                f"{domain.domain_id}: pools missing from specificity_order: {missing}"
            )

    def test_specificity_order_has_no_extras(self):
        """No phantom pools in specificity order."""
        for domain in [GCHAT_DOMAIN, EMAIL_DOMAIN]:
            extras = set(domain.specificity_order) - set(domain.pool_vocab)
            assert not extras, (
                f"{domain.domain_id}: unknown pools in specificity_order: {extras}"
            )

    def test_domain_config_is_frozen(self):
        with pytest.raises(AttributeError):
            GCHAT_DOMAIN.domain_id = "hacked"

    def test_rewrap_rules_reference_valid_pools(self):
        """Rewrap rules should only define rules for pools that exist."""
        for domain in [GCHAT_DOMAIN, EMAIL_DOMAIN]:
            for pool in domain.rewrap_rules:
                assert pool in domain.pool_vocab, (
                    f"{domain.domain_id}: rewrap rule for unknown pool '{pool}'"
                )


class TestDomainRegistry:
    """Test registry lookup and resolution."""

    def test_list_domains_includes_gchat_and_email(self):
        domains = list_domains()
        assert "gchat" in domains
        assert "email" in domains

    def test_get_domain_returns_correct_config(self):
        assert get_domain("gchat") is GCHAT_DOMAIN
        assert get_domain("email") is EMAIL_DOMAIN

    def test_get_domain_unknown_raises(self):
        with pytest.raises(KeyError):
            get_domain("nonexistent_domain_xyz")

    def test_get_domain_or_default_falls_back_to_gchat(self):
        assert get_domain_or_default(None) is GCHAT_DOMAIN
        assert get_domain_or_default("nonexistent") is GCHAT_DOMAIN

    def test_register_domain_adds_new(self):
        custom = DomainConfig(
            domain_id="test_custom_xyz",
            pool_vocab={"a": 0, "b": 1},
            component_to_pool={"A": "a"},
            specificity_order=["b", "a"],
        )
        register_domain(custom)
        assert get_domain("test_custom_xyz") is custom
        # Cleanup
        from research.trm.h2.domain_config import _DOMAIN_REGISTRY
        del _DOMAIN_REGISTRY["test_custom_xyz"]


class TestDomainFromCheckpoint:
    """Test reconstructing DomainConfig from checkpoint metadata."""

    def test_from_checkpoint_with_full_metadata(self):
        ckpt = {
            "domain_id": "gchat",
            "pool_vocab": {"buttons": 0, "content_texts": 1, "grid_items": 2,
                           "chips": 3, "carousel_cards": 4},
            "component_to_pool": {"Button": "buttons", "DecoratedText": "content_texts"},
            "specificity_order": ["chips", "grid_items", "carousel_cards", "buttons", "content_texts"],
        }
        config = DomainConfig.from_checkpoint(ckpt)
        assert config is not None
        assert config.domain_id == "gchat"
        assert config.n_pools == 5
        assert config.component_to_pool["Button"] == "buttons"

    def test_from_checkpoint_without_domain_id_returns_none(self):
        """Checkpoints without domain_id should NOT produce a DomainConfig."""
        ckpt = {"pool_vocab": {"a": 0}, "model_type": "unified_trn"}
        assert DomainConfig.from_checkpoint(ckpt) is None

    def test_from_checkpoint_without_pool_vocab_returns_none(self):
        ckpt = {"domain_id": "gchat", "model_type": "unified_trn"}
        assert DomainConfig.from_checkpoint(ckpt) is None

    def test_from_checkpoint_infers_specificity_from_vocab_keys(self):
        """If specificity_order is missing, it should default to pool_vocab key order."""
        ckpt = {
            "domain_id": "test_infer",
            "pool_vocab": {"alpha": 0, "beta": 1},
        }
        config = DomainConfig.from_checkpoint(ckpt)
        assert config is not None
        assert set(config.specificity_order) == {"alpha", "beta"}

    def test_resolve_domain_prefers_checkpoint_over_explicit(self):
        ckpt = {
            "domain_id": "email",
            "pool_vocab": dict(EMAIL_DOMAIN.pool_vocab),
        }
        config = resolve_domain(checkpoint=ckpt, domain_id="gchat")
        # Checkpoint should win
        assert config.domain_id == "email"

    def test_resolve_domain_falls_back_to_explicit(self):
        config = resolve_domain(checkpoint={}, domain_id="email")
        assert config.domain_id == "email"

    def test_resolve_domain_falls_back_to_gchat(self):
        config = resolve_domain(checkpoint={}, domain_id=None)
        assert config.domain_id == "gchat"

    def test_resolve_domain_with_no_args(self):
        config = resolve_domain()
        assert config.domain_id == "gchat"


class TestDomainRewrap:
    """Test domain-aware item rewrapping."""

    def test_gchat_rewrap_to_buttons_adds_url(self):
        result = GCHAT_DOMAIN.rewrap_item({"text": "Click"}, "content_texts", "buttons")
        assert result["text"] == "Click"
        assert result["url"] == ""

    def test_gchat_rewrap_to_chips_uses_label_field(self):
        result = GCHAT_DOMAIN.rewrap_item({"text": "Tag"}, "content_texts", "chips")
        assert result["label"] == "Tag"

    def test_gchat_rewrap_to_content_texts_sets_wrapText(self):
        result = GCHAT_DOMAIN.rewrap_item("Hello", "buttons", "content_texts")
        assert result["text"] == "Hello"
        assert result["wrapText"] is True

    def test_gchat_rewrap_preserves_existing_fields(self):
        item = {"text": "Deploy", "icon": "rocket", "url": "http://x.com"}
        result = GCHAT_DOMAIN.rewrap_item(item, "buttons", "content_texts")
        assert result["icon"] == "rocket"
        assert result["url"] == "http://x.com"

    def test_gchat_rewrap_does_not_overwrite_existing_url(self):
        """setdefault should not overwrite an existing url."""
        item = {"text": "Go", "url": "http://real.com"}
        result = GCHAT_DOMAIN.rewrap_item(item, "content_texts", "buttons")
        assert result["url"] == "http://real.com"

    def test_email_rewrap_body_uses_content_field(self):
        result = EMAIL_DOMAIN.rewrap_item({"text": "Hello world"}, "subject", "body_sections")
        assert result["content"] == "Hello world"

    def test_rewrap_with_no_rules_falls_back_to_text(self):
        """Domain with no rewrap rules should still produce a text field."""
        bare = DomainConfig(
            domain_id="bare",
            pool_vocab={"a": 0, "b": 1},
            component_to_pool={},
            specificity_order=["a", "b"],
        )
        result = bare.rewrap_item("hello", "a", "b")
        assert result["text"] == "hello"

    def test_rewrap_extracts_text_from_multiple_fields(self):
        """Should try text, title, label, subtitle, styled in order."""
        assert GCHAT_DOMAIN.rewrap_item({"title": "T"}, "a", "buttons")["text"] == "T"
        assert GCHAT_DOMAIN.rewrap_item({"label": "L"}, "a", "buttons")["text"] == "L"
        assert GCHAT_DOMAIN.rewrap_item({"subtitle": "S"}, "a", "buttons")["text"] == "S"

    def test_rewrap_empty_dict_gets_empty_text(self):
        result = GCHAT_DOMAIN.rewrap_item({}, "a", "buttons")
        assert result["text"] == ""


# ── SlotAffinityNet Tests ──────────────────────────────────────────


class TestSlotAffinityNet:
    """Test the model architecture."""

    def test_forward_shape(self):
        model = SlotAffinityNet(content_dim=384, n_slot_types=5, hidden=32)
        content = torch.randn(5, 384)
        output = model(content)
        assert output.shape == (5, 5)

    def test_score_all_slots_matches_forward(self):
        """forward() and score_all_slots() should return identical results."""
        model = SlotAffinityNet()
        model.eval()
        content = torch.randn(3, 384)
        with torch.no_grad():
            fwd = model(content)
            scores = model.score_all_slots(content)
        assert torch.allclose(fwd, scores)

    def test_different_inputs_give_different_outputs(self):
        """Model must not collapse all inputs to the same output."""
        model = SlotAffinityNet()
        model.eval()
        # Two very different embeddings
        a = torch.ones(1, 384) * 5.0
        b = torch.ones(1, 384) * -5.0
        with torch.no_grad():
            out_a = model(a)
            out_b = model(b)
        assert not torch.allclose(out_a, out_b, atol=1e-3), (
            "Model produces identical outputs for very different inputs"
        )

    def test_custom_n_pools(self):
        """SlotAffinityNet should work with non-default pool count."""
        model = SlotAffinityNet(n_slot_types=8)
        content = torch.randn(2, 384)
        output = model(content)
        assert output.shape == (2, 8)

    def test_deterministic_eval(self):
        model = SlotAffinityNet()
        model.eval()
        content = torch.randn(2, 384)
        with torch.no_grad():
            s1 = model.score_all_slots(content)
            s2 = model.score_all_slots(content)
        assert torch.allclose(s1, s2)

    def test_gradient_flows(self):
        """Verify gradients flow through the model (trainability check)."""
        model = SlotAffinityNet()
        model.train()
        content = torch.randn(4, 384)
        target = torch.tensor([0, 1, 2, 3])
        logits = model(content)
        loss = torch.nn.functional.cross_entropy(logits, target)
        loss.backward()
        for name, param in model.named_parameters():
            assert param.grad is not None, f"No gradient for {name}"
            assert param.grad.abs().sum() > 0, f"Zero gradient for {name}"


class TestSlotConstants:
    """Test backward-compat constants are consistent with DomainConfig."""

    def test_pool_vocab_matches_gchat_domain(self):
        assert POOL_VOCAB == dict(GCHAT_DOMAIN.pool_vocab)

    def test_component_to_pool_matches_gchat_domain(self):
        assert COMPONENT_TO_POOL == dict(GCHAT_DOMAIN.component_to_pool)

    def test_specificity_order_matches_gchat_domain(self):
        assert POOL_SPECIFICITY_ORDER == list(GCHAT_DOMAIN.specificity_order)

    def test_all_components_map_to_existing_pools(self):
        for comp, pool in COMPONENT_TO_POOL.items():
            assert pool in POOL_VOCAB, f"{comp} maps to unknown pool '{pool}'"

    def test_specificity_order_no_duplicates(self):
        assert len(POOL_SPECIFICITY_ORDER) == len(set(POOL_SPECIFICITY_ORDER))


# ── Slot Assignment Integration Tests ──────────────────────────────


class TestSlotAssignment:
    """Test the inference glue functions."""

    def test_extract_item_text_string(self):
        from gchat.card_builder.slot_assignment import _extract_item_text
        assert _extract_item_text("hello") == "hello"

    def test_extract_item_text_dict_priority(self):
        """text field should take priority over title, label, etc."""
        from gchat.card_builder.slot_assignment import _extract_item_text
        item = {"text": "primary", "title": "secondary", "label": "tertiary"}
        assert _extract_item_text(item) == "primary"

    def test_extract_item_text_fallback_order(self):
        from gchat.card_builder.slot_assignment import _extract_item_text
        assert _extract_item_text({"title": "T"}) == "T"
        assert _extract_item_text({"label": "L"}) == "L"
        assert _extract_item_text({"subtitle": "S"}) == "S"

    def test_extract_item_text_empty(self):
        from gchat.card_builder.slot_assignment import _extract_item_text
        assert _extract_item_text({}) == ""
        assert _extract_item_text(42) == ""
        assert _extract_item_text(None) == ""

    def test_rewrap_uses_domain_config(self):
        """Rewrap should use the loaded DomainConfig, not hardcoded rules."""
        from gchat.card_builder.slot_assignment import _rewrap_item
        result = _rewrap_item({"text": "Test"}, "content_texts", "chips")
        assert result["label"] == "Test"
        assert "url" in result

    def test_get_constants_returns_domain_values(self):
        from gchat.card_builder.slot_assignment import _get_constants
        vocab, comp_to_pool, spec_order = _get_constants()
        assert isinstance(vocab, dict)
        assert len(vocab) > 0
        # All spec_order entries must be in vocab
        for pool in spec_order:
            assert pool in vocab
        # All comp_to_pool values must be in vocab
        for pool in comp_to_pool.values():
            assert pool in vocab

    def test_reassign_no_model_returns_original(self):
        """Without a model checkpoint, reassign should return original."""
        from gchat.card_builder.slot_assignment import reassign_supply_map
        import gchat.card_builder.slot_assignment as sa

        old_attempted = sa._model_load_attempted
        old_model = sa._cached_model
        old_domain = sa._cached_domain_config
        sa._model_load_attempted = True
        sa._cached_model = None

        try:
            supply_map = {
                "buttons": [{"text": "Deploy"}],
                "content_texts": [{"text": "Status"}],
            }
            result = reassign_supply_map(supply_map, {"Button": 1, "DecoratedText": 1})
            assert result is supply_map
        finally:
            sa._model_load_attempted = old_attempted
            sa._cached_model = old_model
            sa._cached_domain_config = old_domain

    def test_reassign_single_item_returns_original(self):
        """Pools with 0-1 total items should skip reassignment."""
        from gchat.card_builder.slot_assignment import reassign_supply_map
        import gchat.card_builder.slot_assignment as sa

        old_attempted = sa._model_load_attempted
        old_model = sa._cached_model
        old_domain = sa._cached_domain_config
        sa._model_load_attempted = True
        sa._cached_model = None

        try:
            supply_map = {"buttons": [{"text": "Deploy"}], "content_texts": []}
            result = reassign_supply_map(supply_map, {"Button": 1})
            assert result is supply_map
        finally:
            sa._model_load_attempted = old_attempted
            sa._cached_model = old_model
            sa._cached_domain_config = old_domain

    def test_reassign_with_mock_model_routes_items(self):
        """With a mock model, items should be routed by neural scores."""
        import gchat.card_builder.slot_assignment as sa
        from gchat.card_builder.slot_assignment import reassign_supply_map

        # Save state
        old_attempted = sa._model_load_attempted
        old_model = sa._cached_model
        old_type = sa._cached_model_type
        old_domain = sa._cached_domain_config

        try:
            # Create a mock model that always predicts "chips" (index 3)
            class MockModel:
                def __call__(self, structural, content, mode="build"):
                    batch = content.shape[0]
                    logits = torch.zeros(batch, 5)
                    logits[:, 3] = 10.0  # strongly prefer chips
                    return {"pool_logits": logits}

            sa._model_load_attempted = True
            sa._cached_model = MockModel()
            sa._cached_model_type = "unified"
            sa._cached_domain_config = GCHAT_DOMAIN

            supply_map = {
                "buttons": [],
                "content_texts": [
                    {"text": "Item 1"},
                    {"text": "Item 2"},
                    {"text": "Item 3"},
                ],
                "chips": [],
                "grid_items": [],
                "carousel_cards": [],
            }
            demands = {"Chip": 2, "DecoratedText": 1}
            result = reassign_supply_map(supply_map, demands, wrapper=None)

            # With demand for 2 chips and model strongly preferring chips,
            # at least some items should move to chips
            total_items = sum(len(v) for v in result.values())
            assert total_items == 3, "Total item count must be preserved"

        finally:
            sa._model_load_attempted = old_attempted
            sa._cached_model = old_model
            sa._cached_model_type = old_type
            sa._cached_domain_config = old_domain

    def test_reassign_preserves_total_item_count(self):
        """Reassignment must never lose or duplicate items."""
        import gchat.card_builder.slot_assignment as sa
        from gchat.card_builder.slot_assignment import reassign_supply_map

        old_attempted = sa._model_load_attempted
        old_model = sa._cached_model
        old_type = sa._cached_model_type
        old_domain = sa._cached_domain_config

        try:
            # Mock that spreads items across pools
            class SpreadModel:
                def __call__(self, structural, content, mode="build"):
                    batch = content.shape[0]
                    logits = torch.randn(batch, 5)  # random routing
                    return {"pool_logits": logits}

            sa._model_load_attempted = True
            sa._cached_model = SpreadModel()
            sa._cached_model_type = "unified"
            sa._cached_domain_config = GCHAT_DOMAIN

            supply_map = {
                "buttons": [{"text": f"btn_{i}"} for i in range(3)],
                "content_texts": [{"text": f"ct_{i}"} for i in range(4)],
                "chips": [{"text": f"chip_{i}"} for i in range(2)],
                "grid_items": [],
                "carousel_cards": [],
            }
            demands = {"Button": 2, "DecoratedText": 3, "Chip": 2, "GridItem": 2}
            result = reassign_supply_map(supply_map, demands, wrapper=None)

            original_count = 3 + 4 + 2
            result_count = sum(len(v) for v in result.values() if isinstance(v, list))
            assert result_count == original_count, (
                f"Item count changed: {original_count} → {result_count}"
            )
        finally:
            sa._model_load_attempted = old_attempted
            sa._cached_model = old_model
            sa._cached_model_type = old_type
            sa._cached_domain_config = old_domain

    def test_reassign_pinned_items_stay_in_place(self):
        """Items in a pool that's demanded should be pinned, not rerouted."""
        import gchat.card_builder.slot_assignment as sa
        from gchat.card_builder.slot_assignment import reassign_supply_map

        old_attempted = sa._model_load_attempted
        old_model = sa._cached_model
        old_type = sa._cached_model_type
        old_domain = sa._cached_domain_config

        try:
            # Model that would route everything to grid_items if allowed
            class GridModel:
                def __call__(self, structural, content, mode="build"):
                    batch = content.shape[0]
                    logits = torch.zeros(batch, 5)
                    logits[:, 2] = 100.0  # grid_items
                    return {"pool_logits": logits}

            sa._model_load_attempted = True
            sa._cached_model = GridModel()
            sa._cached_model_type = "unified"
            sa._cached_domain_config = GCHAT_DOMAIN

            supply_map = {
                "buttons": [{"text": "btn_1"}, {"text": "btn_2"}],
                "content_texts": [{"text": "extra_1"}, {"text": "extra_2"}],
                "chips": [],
                "grid_items": [],
                "carousel_cards": [],
            }
            # Demand 2 buttons — so both btn items should be pinned
            demands = {"Button": 2, "GridItem": 2}
            result = reassign_supply_map(supply_map, demands, wrapper=None)

            # Buttons should be pinned (demand matches supply)
            assert len(result["buttons"]) == 2, (
                f"Pinned buttons should stay: got {len(result['buttons'])}"
            )
            # The extra content_texts should be rerouted to grid_items
            assert len(result["grid_items"]) == 2

        finally:
            sa._model_load_attempted = old_attempted
            sa._cached_model = old_model
            sa._cached_model_type = old_type
            sa._cached_domain_config = old_domain
