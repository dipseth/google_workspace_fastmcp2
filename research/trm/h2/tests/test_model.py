"""Unit tests for TinyProjectionNetwork.

Run from poc directory:
    cd research/trm/poc
    uv run pytest ../h2/tests/test_model.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch

# Allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "poc"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from h2.model import (
    ProjectionHead,
    RecursiveBlock,
    SwiGLU,
    TinyProjectionNetwork,
    TRPNConfig,
    rms_norm,
)


class TestRMSNorm:
    def test_output_shape(self):
        x = torch.randn(4, 128)
        out = rms_norm(x)
        assert out.shape == (4, 128)

    def test_approximate_unit_norm(self):
        x = torch.randn(4, 128)
        out = rms_norm(x)
        # RMS of each row should be approximately 1
        rms = out.float().square().mean(-1).sqrt()
        assert torch.allclose(rms, torch.ones(4), atol=0.1)


class TestSwiGLU:
    def test_output_shape(self):
        mlp = SwiGLU(128, expansion=2.0)
        x = torch.randn(4, 128)
        out = mlp(x)
        assert out.shape == (4, 128)


class TestProjectionHead:
    def test_output_shape(self):
        head = ProjectionHead(ric_dim=384, hidden_dim=128)
        comp = torch.randn(4, 384)
        inp = torch.randn(4, 384)
        rel = torch.randn(4, 384)
        out = head(comp, inp, rel)
        assert out.shape == (4, 128)


class TestRecursiveBlock:
    def test_output_shape(self):
        block = RecursiveBlock(hidden_dim=128, num_layers=2)
        hidden = torch.randn(4, 128)
        injection = torch.randn(4, 128)
        out = block(hidden, injection)
        assert out.shape == (4, 128)


class TestTinyProjectionNetwork:
    def setup_method(self):
        self.config = TRPNConfig(
            ric_dim=384,
            hidden_dim=128,
            H_cycles=3,
            L_cycles=4,
            num_layers=2,
            expansion=2.0,
        )
        self.model = TinyProjectionNetwork(self.config)

    def _random_batch(self, B: int = 8):
        return (
            torch.randn(B, 384),  # query_comp
            torch.randn(B, 384),  # query_inp
            torch.randn(B, 384),  # query_rel
            torch.randn(B, 384),  # cand_comp
            torch.randn(B, 384),  # cand_inp
            torch.randn(B, 384),  # cand_rel
        )

    def test_forward_shapes(self):
        B = 8
        scores, halt_logits, per_cycle = self.model(*self._random_batch(B))
        assert scores.shape == (B, 1)
        assert halt_logits.shape == (B, 1)
        assert len(per_cycle) == self.config.H_cycles

    def test_per_cycle_scores_shapes(self):
        B = 4
        _, _, per_cycle = self.model(*self._random_batch(B))
        for s in per_cycle:
            assert s.shape == (B, 1)

    def test_parameter_count_in_range(self):
        n = self.model.count_parameters()
        # Should be between 100K and 750K (tiny vs TRM's 7M)
        assert 100_000 <= n <= 750_000, f"Parameter count {n:,} out of range"

    def test_gradient_flows(self):
        batch = self._random_batch(4)
        scores, _, _ = self.model(*batch)
        loss = scores.mean()
        loss.backward()

        # At least some parameters should have non-zero gradients
        grads = [
            p.grad for p in self.model.parameters()
            if p.grad is not None and p.grad.abs().sum() > 0
        ]
        assert len(grads) > 0, "No gradients flowed"

    def test_deterministic(self):
        torch.manual_seed(42)
        batch = self._random_batch(4)

        self.model.eval()
        with torch.no_grad():
            s1, h1, _ = self.model(*batch)
            s2, h2, _ = self.model(*batch)

        assert torch.allclose(s1, s2), "Forward pass not deterministic"
        assert torch.allclose(h1, h2), "Forward pass not deterministic"

    def test_halt_head_bias_initialized(self):
        """Halt head bias should start at -5 (bias toward continuing)."""
        bias = self.model.halt_head.bias.item()
        assert bias == -5.0

    def test_different_candidates_different_scores(self):
        """Different candidates should produce different scores."""
        self.model.eval()
        q = tuple(torch.randn(1, 384) for _ in range(3))

        with torch.no_grad():
            s1, _, _ = self.model(*q, torch.randn(1, 384), torch.randn(1, 384), torch.randn(1, 384))
            s2, _, _ = self.model(*q, torch.randn(1, 384), torch.randn(1, 384), torch.randn(1, 384))

        # Very unlikely to be exactly equal with random inputs
        assert not torch.allclose(s1, s2, atol=1e-6)

    def test_small_config(self):
        """Verify a minimal config works."""
        config = TRPNConfig(
            ric_dim=384,
            hidden_dim=64,
            H_cycles=2,
            L_cycles=2,
            num_layers=1,
            expansion=2.0,
        )
        model = TinyProjectionNetwork(config)
        scores, halt, per_cycle = model(*self._random_batch(2))
        assert scores.shape == (2, 1)
        assert len(per_cycle) == 2
