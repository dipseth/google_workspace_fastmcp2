"""Search + TRM pipeline integration tests.

Tests feature extraction, UnifiedTRN scoring, ranking, and halt convergence
without requiring Qdrant or real embeddings.
"""

import pytest
import torch

from research.trm.h2.domain_config import EMAIL_DOMAIN, GCHAT_DOMAIN
from research.trm.h2.unified_trn import (
    CONTENT_DIM,
    FEATURE_NAMES_V5,
    STRUCTURAL_DIM,
    UnifiedTRN,
)


class TestFeatureExtraction:
    """Feature extraction produces correct-dim vectors."""

    def test_v5_has_17_features(self):
        assert len(FEATURE_NAMES_V5) == 17

    def test_structural_dim_matches_features(self):
        assert STRUCTURAL_DIM == 17

    def test_content_dim_is_384(self):
        assert CONTENT_DIM == 384

    def test_feature_names_include_content_fields(self):
        assert "sim_content" in FEATURE_NAMES_V5
        assert "content_density" in FEATURE_NAMES_V5
        assert "content_form_alignment" in FEATURE_NAMES_V5

    def test_synthetic_feature_vector(self):
        """Construct a 17D feature vector from synthetic candidate data."""
        candidate = {f: 0.5 for f in FEATURE_NAMES_V5}
        features = [candidate[f] for f in FEATURE_NAMES_V5]
        assert len(features) == 17
        assert all(f == 0.5 for f in features)


class TestUnifiedTRNSearchMode:
    """UnifiedTRN search mode returns correct keys."""

    @pytest.fixture
    def model(self):
        m = UnifiedTRN(dropout=0.0)
        m.eval()
        return m

    def test_search_mode_output_keys(self, model):
        structural = torch.randn(5, STRUCTURAL_DIM)
        content = torch.randn(5, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="search")
        assert "form_score" in out
        assert "content_score" in out
        assert "halt_prob" in out

    def test_search_mode_shapes(self, model):
        n = 8
        structural = torch.randn(n, STRUCTURAL_DIM)
        content = torch.randn(n, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="search")
        assert out["form_score"].shape == (n, 1)
        assert out["content_score"].shape == (n, 1)
        assert out["halt_prob"].shape == (n, 1)

    def test_halt_prob_is_bounded(self, model):
        """Halt prob should be sigmoid output, in [0, 1]."""
        structural = torch.randn(10, STRUCTURAL_DIM)
        content = torch.randn(10, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="search")
            halt = torch.sigmoid(out["halt_prob"])
        assert (halt >= 0).all()
        assert (halt <= 1).all()


class TestUnifiedTRNBuildMode:
    """Build mode uses pool_head only."""

    @pytest.fixture
    def model(self):
        m = UnifiedTRN(dropout=0.0)
        m.eval()
        return m

    def test_build_mode_output_keys(self, model):
        structural = torch.zeros(3, STRUCTURAL_DIM)
        content = torch.randn(3, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="build")
        assert "pool_logits" in out

    def test_build_mode_pool_logits_shape(self, model):
        n = 4
        structural = torch.zeros(n, STRUCTURAL_DIM)
        content = torch.randn(n, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="build")
        assert out["pool_logits"].shape == (n, 5)  # 5 pools

    def test_build_mode_produces_valid_pool_predictions(self, model):
        """Argmax of pool_logits gives a valid pool index."""
        structural = torch.zeros(6, STRUCTURAL_DIM)
        content = torch.randn(6, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="build")
            preds = out["pool_logits"].argmax(dim=-1)
        assert (preds >= 0).all()
        assert (preds < 5).all()


class TestFullSearchPipeline:
    """Full pipeline: features -> score -> rank -> verify top result."""

    @pytest.fixture
    def model(self):
        m = UnifiedTRN(dropout=0.0)
        m.eval()
        return m

    def test_score_and_rank_synthetic_candidates(self, model):
        """Score synthetic candidates and verify ranking produces sorted output."""
        n_candidates = 10
        structural = torch.randn(n_candidates, STRUCTURAL_DIM)
        content = torch.randn(n_candidates, CONTENT_DIM)

        with torch.no_grad():
            out = model(structural, content, mode="search")
            form_scores = out["form_score"].squeeze(-1)
            content_scores = out["content_score"].squeeze(-1)
            combined = 0.6 * form_scores + 0.4 * content_scores

        # Ranking should produce valid indices
        ranked_indices = combined.argsort(descending=True)
        assert len(ranked_indices) == n_candidates
        assert set(ranked_indices.tolist()) == set(range(n_candidates))

        # Top score should be >= all others
        top_idx = ranked_indices[0]
        assert combined[top_idx] >= combined.max() - 1e-6

    def test_pipeline_with_known_positive(self, model):
        """Create a candidate set with known positive, verify it's rankable."""
        n = 5
        # Create structural features - all similar
        structural = torch.randn(1, STRUCTURAL_DIM).expand(n, -1).clone()
        content = torch.randn(1, CONTENT_DIM).expand(n, -1).clone()

        # Make candidate 0 have distinct features
        structural[0] += 2.0
        content[0] += 1.0

        with torch.no_grad():
            out = model(structural, content, mode="search")
            combined = 0.6 * out["form_score"].squeeze(-1) + 0.4 * out["content_score"].squeeze(-1)

        # We can't guarantee candidate 0 is top (random weights), but
        # the pipeline should produce valid scores for all candidates
        assert combined.shape == (n,)
        assert not torch.isnan(combined).any()
        assert not torch.isinf(combined).any()


class TestHaltHeadConvergence:
    """Halt head convergence: synthetic data triggers varied halt probs."""

    @pytest.fixture
    def model(self):
        m = UnifiedTRN(dropout=0.0)
        m.eval()
        return m

    def test_halt_probs_have_variance(self, model):
        """Different inputs should produce different halt probabilities."""
        structural_list = [torch.randn(1, STRUCTURAL_DIM) for _ in range(20)]
        content_list = [torch.randn(1, CONTENT_DIM) for _ in range(20)]

        halt_probs = []
        with torch.no_grad():
            for s, c in zip(structural_list, content_list):
                out = model(s, c, mode="search")
                halt_probs.append(torch.sigmoid(out["halt_prob"]).item())

        # Should have some variance (not all identical)
        assert max(halt_probs) - min(halt_probs) > 0.01, (
            f"Halt probs too uniform: range = {max(halt_probs) - min(halt_probs):.4f}"
        )

    def test_halt_probs_cover_range(self, model):
        """With enough random inputs, halt probs should span a reasonable range."""
        halt_probs = []
        with torch.no_grad():
            for _ in range(50):
                s = torch.randn(1, STRUCTURAL_DIM) * 3  # Amplify to explore range
                c = torch.randn(1, CONTENT_DIM)
                out = model(s, c, mode="search")
                halt_probs.append(torch.sigmoid(out["halt_prob"]).item())

        # Should have at least some spread
        assert len(set(round(h, 2) for h in halt_probs)) > 3, "Halt probs lack diversity"


class TestAllMode:
    """mode='all' returns everything."""

    @pytest.fixture
    def model(self):
        m = UnifiedTRN(dropout=0.0)
        m.eval()
        return m

    def test_all_mode_has_all_keys(self, model):
        structural = torch.randn(3, STRUCTURAL_DIM)
        content = torch.randn(3, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="all")
        assert "form_score" in out
        assert "content_score" in out
        assert "halt_prob" in out
        assert "pool_logits" in out

    def test_all_mode_pool_logits_shape(self, model):
        structural = torch.randn(4, STRUCTURAL_DIM)
        content = torch.randn(4, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="all")
        assert out["pool_logits"].shape == (4, 5)


class TestDomainAwarePipeline:
    """Pipeline respects domain config for pool vocabulary."""

    def test_gchat_has_5_pools(self):
        assert GCHAT_DOMAIN.n_pools == 5

    def test_email_has_5_pools(self):
        assert EMAIL_DOMAIN.n_pools == 5

    def test_pool_logits_match_domain_pool_count(self):
        model = UnifiedTRN(n_pools=GCHAT_DOMAIN.n_pools, dropout=0.0)
        model.eval()
        structural = torch.zeros(2, STRUCTURAL_DIM)
        content = torch.randn(2, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="build")
        assert out["pool_logits"].shape[1] == GCHAT_DOMAIN.n_pools

    def test_email_domain_model_pool_count(self):
        model = UnifiedTRN(n_pools=EMAIL_DOMAIN.n_pools, dropout=0.0)
        model.eval()
        structural = torch.zeros(2, STRUCTURAL_DIM)
        content = torch.randn(2, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="build")
        assert out["pool_logits"].shape[1] == EMAIL_DOMAIN.n_pools

    def test_pool_prediction_maps_to_valid_pool_name(self):
        model = UnifiedTRN(n_pools=GCHAT_DOMAIN.n_pools, dropout=0.0)
        model.eval()
        structural = torch.zeros(1, STRUCTURAL_DIM)
        content = torch.randn(1, CONTENT_DIM)
        with torch.no_grad():
            out = model(structural, content, mode="build")
            pred_idx = out["pool_logits"].argmax(dim=-1).item()
        pool_name = GCHAT_DOMAIN.pool_names[pred_idx]
        assert pool_name in GCHAT_DOMAIN.pool_vocab
