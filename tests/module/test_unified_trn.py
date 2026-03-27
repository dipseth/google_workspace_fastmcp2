"""Unit tests for UnifiedTRN model."""

import torch

from research.trm.h2.unified_trn import FEATURE_NAMES_V5, UnifiedTRN
from research.trm.h2.slot_assigner import POOL_VOCAB


class TestUnifiedTRN:
    """Test the unified model architecture."""

    def test_search_mode_shape(self):
        model = UnifiedTRN()
        structural = torch.randn(5, 17)
        content = torch.randn(5, 384)
        out = model(structural, content, mode="search")
        assert "form_score" in out
        assert "content_score" in out
        assert "halt_prob" in out
        assert "pool_logits" not in out
        assert out["form_score"].shape == (5, 1)
        assert out["content_score"].shape == (5, 1)
        assert out["halt_prob"].shape == (5, 1)

    def test_build_mode_shape(self):
        model = UnifiedTRN()
        structural = torch.zeros(3, 17)
        content = torch.randn(3, 384)
        out = model(structural, content, mode="build")
        assert "pool_logits" in out
        assert "form_score" not in out
        assert out["pool_logits"].shape == (3, 5)

    def test_all_mode_shape(self):
        model = UnifiedTRN()
        structural = torch.randn(2, 17)
        content = torch.randn(2, 384)
        out = model(structural, content, mode="all")
        assert "form_score" in out
        assert "content_score" in out
        assert "halt_prob" in out
        assert "pool_logits" in out

    def test_parameter_count(self):
        model = UnifiedTRN(hidden=64)
        n = model.count_parameters()
        # Expected ~28.7K
        assert 25000 < n < 35000, f"Expected ~28.7K params, got {n}"

    def test_halt_prob_bounded(self):
        model = UnifiedTRN()
        model.eval()
        structural = torch.randn(10, 17)
        content = torch.randn(10, 384)
        with torch.no_grad():
            out = model(structural, content, mode="search")
        probs = out["halt_prob"]
        assert (probs >= 0).all() and (probs <= 1).all(), "halt_prob must be in [0,1]"

    def test_deterministic_eval(self):
        model = UnifiedTRN()
        model.eval()
        s = torch.randn(3, 17)
        c = torch.randn(3, 384)
        with torch.no_grad():
            out1 = model(s, c, mode="search")
            out2 = model(s, c, mode="search")
        assert torch.allclose(out1["form_score"], out2["form_score"])
        assert torch.allclose(out1["halt_prob"], out2["halt_prob"])

    def test_single_item(self):
        model = UnifiedTRN()
        s = torch.randn(1, 17)
        c = torch.randn(1, 384)
        out = model(s, c, mode="all")
        assert out["form_score"].shape == (1, 1)
        assert out["pool_logits"].shape == (1, 5)

    def test_n_pools_matches_vocab(self):
        model = UnifiedTRN()
        assert model.n_pools == len(POOL_VOCAB)

    def test_structural_dim_matches_features(self):
        model = UnifiedTRN()
        assert model.structural_dim == len(FEATURE_NAMES_V5)

    def test_build_mode_zeros_structural(self):
        """Build mode with zeros structural should still produce valid pool logits."""
        model = UnifiedTRN()
        model.eval()
        zeros = torch.zeros(4, 17)
        content = torch.randn(4, 384)
        with torch.no_grad():
            out = model(zeros, content, mode="build")
        logits = out["pool_logits"]
        assert not torch.isnan(logits).any()
        assert not torch.isinf(logits).any()
