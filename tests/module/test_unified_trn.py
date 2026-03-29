"""Unit tests for UnifiedTRN model and multi-domain support."""

import pytest
import torch

from research.trm.h2.domain_config import (
    EMAIL_DOMAIN,
    GCHAT_DOMAIN,
    DomainConfig,
)
from research.trm.h2.slot_assigner import POOL_VOCAB
from research.trm.h2.unified_trn import FEATURE_NAMES_V5, UnifiedTRN


class TestUnifiedTRNArchitecture:
    """Test the unified model architecture correctness."""

    def test_search_mode_returns_correct_keys(self):
        model = UnifiedTRN()
        out = model(torch.randn(5, 17), torch.randn(5, 384), mode="search")
        assert set(out.keys()) == {"form_score", "content_score", "halt_prob"}

    def test_build_mode_returns_correct_keys(self):
        model = UnifiedTRN()
        out = model(torch.zeros(3, 17), torch.randn(3, 384), mode="build")
        assert set(out.keys()) == {"pool_logits"}

    def test_all_mode_returns_all_keys(self):
        model = UnifiedTRN()
        out = model(torch.randn(2, 17), torch.randn(2, 384), mode="all")
        assert set(out.keys()) == {"form_score", "content_score", "halt_prob", "pool_logits"}

    def test_search_mode_shapes(self):
        model = UnifiedTRN()
        out = model(torch.randn(5, 17), torch.randn(5, 384), mode="search")
        assert out["form_score"].shape == (5, 1)
        assert out["content_score"].shape == (5, 1)
        assert out["halt_prob"].shape == (5, 1)

    def test_build_mode_shape_matches_n_pools(self):
        model = UnifiedTRN(n_pools=7)
        out = model(torch.zeros(3, 17), torch.randn(3, 384), mode="build")
        assert out["pool_logits"].shape == (3, 7)

    def test_halt_prob_bounded_0_1(self):
        model = UnifiedTRN()
        model.eval()
        # Test with extreme inputs
        for val in [-100.0, 0.0, 100.0]:
            structural = torch.full((10, 17), val)
            content = torch.full((10, 384), val)
            with torch.no_grad():
                out = model(structural, content, mode="search")
            probs = out["halt_prob"]
            assert (probs >= 0).all() and (probs <= 1).all(), (
                f"halt_prob out of [0,1] with input={val}: "
                f"min={probs.min():.4f}, max={probs.max():.4f}"
            )

    def test_parameter_count_reasonable(self):
        model = UnifiedTRN(hidden=64)
        n = model.count_parameters()
        assert 20000 < n < 40000, f"Expected ~28.7K params, got {n}"

    def test_deterministic_in_eval_mode(self):
        model = UnifiedTRN()
        model.eval()
        s = torch.randn(3, 17)
        c = torch.randn(3, 384)
        with torch.no_grad():
            out1 = model(s, c, mode="all")
            out2 = model(s, c, mode="all")
        for key in out1:
            assert torch.allclose(out1[key], out2[key]), f"{key} not deterministic in eval"

    def test_non_deterministic_in_train_mode(self):
        """Dropout should cause variation in train mode."""
        model = UnifiedTRN(dropout=0.5)  # high dropout for visibility
        model.train()
        s = torch.randn(20, 17)
        c = torch.randn(20, 384)
        results = []
        for _ in range(5):
            out = model(s, c, mode="search")
            results.append(out["form_score"].clone())
        # At least some runs should differ (extremely unlikely all 5 match with 50% dropout)
        all_same = all(torch.allclose(results[0], r) for r in results[1:])
        assert not all_same, "Dropout has no effect in train mode"


class TestUnifiedTRNMultiDomain:
    """Test that UnifiedTRN works with different domain configurations."""

    def test_custom_n_pools(self):
        """Model should accept arbitrary n_pools (not just 5)."""
        for n in [2, 4, 8, 12]:
            model = UnifiedTRN(n_pools=n)
            out = model(torch.zeros(2, 17), torch.randn(2, 384), mode="build")
            assert out["pool_logits"].shape == (2, n), f"Failed for n_pools={n}"

    def test_custom_structural_dim(self):
        """Model should accept different feature dimensions."""
        model = UnifiedTRN(structural_dim=10, content_dim=128, n_pools=3)
        out = model(torch.randn(2, 10), torch.randn(2, 128), mode="all")
        assert out["form_score"].shape == (2, 1)
        assert out["pool_logits"].shape == (2, 3)

    def test_email_domain_n_pools(self):
        """Model instantiated with email domain pool count should work."""
        model = UnifiedTRN(n_pools=EMAIL_DOMAIN.n_pools)
        out = model(torch.zeros(3, 17), torch.randn(3, 384), mode="build")
        assert out["pool_logits"].shape == (3, EMAIL_DOMAIN.n_pools)

    def test_n_pools_stored_on_model(self):
        model = UnifiedTRN(n_pools=7)
        assert model.n_pools == 7

    def test_pool_head_output_changes_with_n_pools(self):
        """Different n_pools must produce different output sizes, not silently truncate."""
        m5 = UnifiedTRN(n_pools=5)
        m8 = UnifiedTRN(n_pools=8)
        content = torch.randn(1, 384)
        struct = torch.zeros(1, 17)
        o5 = m5(struct, content, mode="build")["pool_logits"]
        o8 = m8(struct, content, mode="build")["pool_logits"]
        assert o5.shape[1] == 5
        assert o8.shape[1] == 8


class TestUnifiedTRNGradients:
    """Test that all heads receive gradients during training."""

    def test_form_head_gradients(self):
        model = UnifiedTRN()
        model.train()
        out = model(torch.randn(4, 17), torch.randn(4, 384), mode="search")
        loss = out["form_score"].sum()
        loss.backward()
        # form_head params should have gradients
        for name, p in model.form_head.named_parameters():
            assert p.grad is not None and p.grad.abs().sum() > 0, (
                f"form_head.{name} has no gradient"
            )

    def test_content_head_gradients(self):
        model = UnifiedTRN()
        model.train()
        out = model(torch.randn(4, 17), torch.randn(4, 384), mode="search")
        loss = out["content_score"].sum()
        loss.backward()
        for name, p in model.content_head.named_parameters():
            assert p.grad is not None and p.grad.abs().sum() > 0, (
                f"content_head.{name} has no gradient"
            )

    def test_pool_head_gradients(self):
        model = UnifiedTRN()
        model.train()
        out = model(torch.zeros(4, 17), torch.randn(4, 384), mode="build")
        target = torch.tensor([0, 1, 2, 3])
        loss = torch.nn.functional.cross_entropy(out["pool_logits"], target)
        loss.backward()
        for name, p in model.pool_head.named_parameters():
            assert p.grad is not None and p.grad.abs().sum() > 0, (
                f"pool_head.{name} has no gradient"
            )

    def test_halt_head_gradients(self):
        model = UnifiedTRN()
        model.train()
        out = model(torch.randn(4, 17), torch.randn(4, 384), mode="search")
        loss = out["halt_prob"].sum()
        loss.backward()
        for name, p in model.halt_head.named_parameters():
            assert p.grad is not None and p.grad.abs().sum() > 0, (
                f"halt_head.{name} has no gradient"
            )

    def test_backbone_receives_gradients_from_all_heads(self):
        """Backbone should get gradients whether loss comes from form, content, pool, or halt."""
        for mode, key in [("search", "form_score"), ("search", "content_score"),
                          ("build", "pool_logits"), ("search", "halt_prob")]:
            model = UnifiedTRN()
            model.train()
            model.zero_grad()
            out = model(torch.randn(4, 17), torch.randn(4, 384), mode=mode)
            if key == "pool_logits":
                loss = torch.nn.functional.cross_entropy(out[key], torch.tensor([0, 1, 2, 3]))
            else:
                loss = out[key].sum()
            loss.backward()
            backbone_grads = sum(
                p.grad.abs().sum().item()
                for p in model.backbone.parameters()
                if p.grad is not None
            )
            assert backbone_grads > 0, f"Backbone has no gradients from {key}"


class TestUnifiedTRNEdgeCases:
    """Test edge cases and potential failure modes."""

    def test_single_item_batch(self):
        model = UnifiedTRN()
        model.eval()
        with torch.no_grad():
            out = model(torch.randn(1, 17), torch.randn(1, 384), mode="all")
        assert out["form_score"].shape == (1, 1)
        assert out["pool_logits"].shape == (1, 5)

    def test_large_batch(self):
        model = UnifiedTRN()
        model.eval()
        with torch.no_grad():
            out = model(torch.randn(256, 17), torch.randn(256, 384), mode="all")
        assert out["form_score"].shape == (256, 1)

    def test_zero_structural_features(self):
        """Build mode uses zeros for structural — must not produce NaN."""
        model = UnifiedTRN()
        model.eval()
        with torch.no_grad():
            out = model(torch.zeros(10, 17), torch.randn(10, 384), mode="build")
        assert not torch.isnan(out["pool_logits"]).any()
        assert not torch.isinf(out["pool_logits"]).any()

    def test_extreme_input_values(self):
        """Model should not NaN with extreme inputs."""
        model = UnifiedTRN()
        model.eval()
        for val in [1e6, -1e6, 1e-8]:
            s = torch.full((2, 17), val)
            c = torch.full((2, 384), val)
            with torch.no_grad():
                out = model(s, c, mode="all")
            for key, tensor in out.items():
                assert not torch.isnan(tensor).any(), f"NaN in {key} with input={val}"

    def test_no_output_collapse(self):
        """Different inputs should produce different outputs — model must not collapse."""
        model = UnifiedTRN()
        model.eval()
        torch.manual_seed(42)
        inputs = [torch.randn(1, 384) for _ in range(5)]
        struct = torch.randn(1, 17)
        scores = []
        with torch.no_grad():
            for c in inputs:
                out = model(struct, c, mode="build")
                scores.append(out["pool_logits"])
        # At least some pairs should differ
        n_different = sum(
            1 for i in range(len(scores))
            for j in range(i + 1, len(scores))
            if not torch.allclose(scores[i], scores[j], atol=1e-3)
        )
        assert n_different > 0, "Model collapses all different content inputs to same output"


class TestBackwardCompatibility:
    """Verify backward compatibility with existing constants."""

    def test_pool_vocab_re_export_matches_gchat(self):
        from research.trm.h2.unified_trn import POOL_VOCAB as TRN_VOCAB
        assert TRN_VOCAB == dict(GCHAT_DOMAIN.pool_vocab)

    def test_component_to_pool_re_export_matches_gchat(self):
        from research.trm.h2.unified_trn import COMPONENT_TO_POOL as TRN_C2P
        assert TRN_C2P == dict(GCHAT_DOMAIN.component_to_pool)

    def test_feature_names_v5_has_17_features(self):
        assert len(FEATURE_NAMES_V5) == 17

    def test_n_pools_matches_gchat(self):
        model = UnifiedTRN()
        assert model.n_pools == GCHAT_DOMAIN.n_pools

    def test_structural_dim_matches_features(self):
        model = UnifiedTRN()
        assert model.structural_dim == len(FEATURE_NAMES_V5)
