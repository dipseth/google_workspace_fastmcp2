"""Tiny Recursive Projection Network for RIC embedding reranking.

Adapts TRM's recursive refinement pattern (H_cycles × L_cycles with shared
weights) to operate on RIC 3-vector embeddings. Scores (query, candidate)
pairs via learned projections into a shared latent space.

Architecture mirrors:
  - SwiGLU + RMSNorm from official-repo/models/layers.py
  - H/L cycle recursion from official-repo/models/recursive_reasoning/trm.py
  - Learned initial states (z_H_init, z_L_init) frozen at inference
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# Building blocks (adapted from TRM layers.py)
# ---------------------------------------------------------------------------


def rms_norm(x: torch.Tensor, eps: float = 1e-5) -> torch.Tensor:
    """RMSNorm without learnable parameters. (layers.py:163-169)"""
    dtype = x.dtype
    x = x.float()
    variance = x.square().mean(-1, keepdim=True)
    x = x * torch.rsqrt(variance + eps)
    return x.to(dtype)


class SwiGLU(nn.Module):
    """Gated MLP with SiLU activation. (layers.py:151-161)

    Uses standard nn.Linear instead of TRM's CastedLinear.
    """

    def __init__(self, hidden_size: int, expansion: float = 2.0):
        super().__init__()
        inter = round(expansion * hidden_size * 2 / 3)
        # Round up to next multiple of 8 for efficiency
        inter = ((inter + 7) // 8) * 8
        self.gate_up_proj = nn.Linear(hidden_size, inter * 2, bias=False)
        self.down_proj = nn.Linear(inter, hidden_size, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gate, up = self.gate_up_proj(x).chunk(2, dim=-1)
        return self.down_proj(F.silu(gate) * up)


# ---------------------------------------------------------------------------
# Projection and recursion
# ---------------------------------------------------------------------------


class ProjectionHead(nn.Module):
    """Projects 3×RIC vectors (comp, inp, rel) into shared D-space.

    Each vector gets its own linear projection, then all three are
    concatenated and fused to hidden_dim.
    """

    def __init__(self, ric_dim: int = 384, hidden_dim: int = 128):
        super().__init__()
        self.proj_comp = nn.Linear(ric_dim, hidden_dim, bias=False)
        self.proj_inp = nn.Linear(ric_dim, hidden_dim, bias=False)
        self.proj_rel = nn.Linear(ric_dim, hidden_dim, bias=False)
        self.fuse = nn.Linear(hidden_dim * 3, hidden_dim, bias=False)

    def forward(
        self,
        components: torch.Tensor,
        inputs: torch.Tensor,
        relationships: torch.Tensor,
    ) -> torch.Tensor:
        c = self.proj_comp(components)
        i = self.proj_inp(inputs)
        r = self.proj_rel(relationships)
        return self.fuse(torch.cat([c, i, r], dim=-1))


class RecursiveBlock(nn.Module):
    """One reasoning module: input injection + SwiGLU layers + residual.

    Mirrors TRM's ReasoningModule (trm.py:106-115):
        hidden = hidden + injection
        for layer in layers: hidden = layer(hidden)
    With post-norm RMSNorm and residual (trm.py:90-104).
    """

    def __init__(
        self,
        hidden_dim: int = 128,
        num_layers: int = 2,
        expansion: float = 2.0,
        eps: float = 1e-5,
    ):
        super().__init__()
        self.eps = eps
        self.layers = nn.ModuleList(
            [SwiGLU(hidden_dim, expansion) for _ in range(num_layers)]
        )

    def forward(self, hidden: torch.Tensor, injection: torch.Tensor) -> torch.Tensor:
        # Input injection (trm.py:112)
        hidden = hidden + injection
        # Layer stack with residual + post-norm (trm.py:100-104)
        for layer in self.layers:
            hidden = rms_norm(hidden + layer(hidden), self.eps)
        return hidden


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------


@dataclass
class TRPNConfig:
    """Configuration for TinyProjectionNetwork."""

    ric_dim: int = 384
    hidden_dim: int = 128
    H_cycles: int = 3
    L_cycles: int = 4
    num_layers: int = 2
    expansion: float = 2.0
    eps: float = 1e-5
    # TRM detaches early H_cycles (trm.py:208). For small models this
    # kills gradient signal. Set False to allow gradients on all cycles.
    detach_early_cycles: bool = False


class TinyProjectionNetwork(nn.Module):
    """Scores (query, candidate) pairs via recursive refinement.

    Forward pass:
        1. Project query and candidate RIC vectors into shared D-space
        2. Initialize z_H (answer state) and z_L (reasoning state) from
           learned parameters (random init, trained, frozen at inference)
        3. x = query_proj + candidate_proj (input injection, constant)
        4. Recursive loop (trm.py:206-216):
             H_cycles-1 without grad:
               for L in L_cycles: z_L = block(z_L, z_H + x)
               z_H = block(z_H, z_L)
             1 with grad:
               for L in L_cycles: z_L = block(z_L, z_H + x)
               z_H = block(z_H, z_L)
        5. score_head(z_H) → relevance score
        6. halt_head(z_H) → halt logit

    Returns:
        scores: [B, 1] — candidate relevance
        halt_logits: [B, 1] — halt confidence
        per_cycle_scores: list of [B, 1] — score at each H_cycle (deep supervision)
    """

    def __init__(self, config: TRPNConfig | None = None):
        super().__init__()
        cfg = config or TRPNConfig()
        self.config = cfg

        # Projections (separate weights for query and candidate)
        self.query_proj = ProjectionHead(cfg.ric_dim, cfg.hidden_dim)
        self.candidate_proj = ProjectionHead(cfg.ric_dim, cfg.hidden_dim)

        # Interaction layer: captures query-candidate similarity signal
        self.interaction = nn.Sequential(
            nn.Linear(cfg.hidden_dim * 3, cfg.hidden_dim, bias=False),
            nn.SiLU(),
        )

        # Single recursive block, shared for z_H and z_L updates
        self.refinement = RecursiveBlock(
            cfg.hidden_dim, cfg.num_layers, cfg.expansion, cfg.eps
        )

        # Output heads
        self.score_head = nn.Linear(cfg.hidden_dim, 1)
        self.halt_head = nn.Linear(cfg.hidden_dim, 1)

        # Init halt head bias to -5 (bias toward continuing, trm.py:160)
        with torch.no_grad():
            self.halt_head.bias.fill_(-5.0)

    def forward(
        self,
        query_comp: torch.Tensor,  # [B, ric_dim]
        query_inp: torch.Tensor,  # [B, ric_dim]
        query_rel: torch.Tensor,  # [B, ric_dim]
        cand_comp: torch.Tensor,  # [B, ric_dim]
        cand_inp: torch.Tensor,  # [B, ric_dim]
        cand_rel: torch.Tensor,  # [B, ric_dim]
    ) -> tuple[torch.Tensor, torch.Tensor, list[torch.Tensor]]:
        # Project into shared space
        q = self.query_proj(query_comp, query_inp, query_rel)  # [B, D]
        c = self.candidate_proj(cand_comp, cand_inp, cand_rel)  # [B, D]

        # TRM role mapping:
        #   x  (input injection) = query context (constant, injected every cycle)
        #   z_H (answer state)   = candidate projection (the thing being judged)
        #   z_L (reasoning state) = query-candidate interaction (similarity signal)
        x = q  # [B, D] — constant input context

        # Initialize z_H from candidate, z_L from interaction features
        z_H = c  # [B, D] — answer starts as "this candidate"
        z_L = self.interaction(
            torch.cat([q * c, q - c, q + c], dim=-1)
        )  # [B, D] — reasoning starts from similarity/difference signals
        B = q.shape[0]

        per_cycle_scores: list[torch.Tensor] = []
        H = self.config.H_cycles

        if self.config.detach_early_cycles and H > 1:
            # TRM pattern: H_cycles-1 without grad (trm.py:208-212)
            with torch.no_grad():
                for _h in range(H - 1):
                    for _l in range(self.config.L_cycles):
                        z_L = self.refinement(z_L, z_H + x)
                    z_H = self.refinement(z_H, z_L)
                    per_cycle_scores.append(self.score_head(z_H))

            # Last H_cycle with grad (trm.py:214-216)
            for _l in range(self.config.L_cycles):
                z_L = self.refinement(z_L, z_H + x)
            z_H = self.refinement(z_H, z_L)
            per_cycle_scores.append(self.score_head(z_H))
        else:
            # Full gradient through all cycles (better for small models)
            for _h in range(H):
                for _l in range(self.config.L_cycles):
                    z_L = self.refinement(z_L, z_H + x)
                z_H = self.refinement(z_H, z_L)
                per_cycle_scores.append(self.score_head(z_H))

        scores = per_cycle_scores[-1]  # [B, 1]
        halt_logits = self.halt_head(z_H)  # [B, 1]

        return scores, halt_logits, per_cycle_scores

    def count_parameters(self) -> int:
        """Return total trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# Similarity-based scorer (lightweight, works on raw embedding geometry)
# ---------------------------------------------------------------------------


class SimilarityScorer(nn.Module):
    """Learns a scoring function on top of raw cross-dimensional similarities.

    Instead of projecting 384D vectors through random linear layers (which
    destroys embedding geometry), this model:
    1. Computes 3 cosine similarities between query and candidate
       (components, inputs, relationships) — preserving geometry
    2. Adds per-vector norms and dot products as features (9 total)
    3. Feeds these features through a small MLP to produce a score

    This is a "learnable multi-dimensional scoring" — generalizing the
    hand-tuned multiplicative fusion from search_hybrid_multidim.

    Can serve as:
    - Standalone scorer (no recursion)
    - Future: features fed into TinyProjectionNetwork's z_L initialization
    """

    def __init__(self, hidden_dim: int = 32, num_layers: int = 2):
        super().__init__()
        # 9 input features: 3 cosine sims + 3 query norms + 3 candidate norms
        in_features = 9
        layers: list[nn.Module] = []
        prev = in_features
        for _ in range(num_layers):
            layers.extend([nn.Linear(prev, hidden_dim), nn.SiLU()])
            prev = hidden_dim
        layers.append(nn.Linear(prev, 1))
        self.mlp = nn.Sequential(*layers)

        # Config-like attributes for compatibility with train.py/evaluate.py
        self.H_cycles = 1

    def _cosine_sim(self, a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        """Batch cosine similarity: [B, D] × [B, D] → [B, 1]."""
        a_norm = F.normalize(a, dim=-1)
        b_norm = F.normalize(b, dim=-1)
        return (a_norm * b_norm).sum(dim=-1, keepdim=True)

    def forward(
        self,
        query_comp: torch.Tensor,
        query_inp: torch.Tensor,
        query_rel: torch.Tensor,
        cand_comp: torch.Tensor,
        cand_inp: torch.Tensor,
        cand_rel: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, list[torch.Tensor]]:
        # Cosine similarities (preserves embedding geometry)
        sim_c = self._cosine_sim(query_comp, cand_comp)  # [B, 1]
        sim_i = self._cosine_sim(query_inp, cand_inp)  # [B, 1]
        sim_r = self._cosine_sim(query_rel, cand_rel)  # [B, 1]

        # Norms as additional features (captures magnitude information)
        q_norms = torch.cat(
            [
                query_comp.norm(dim=-1, keepdim=True),
                query_inp.norm(dim=-1, keepdim=True),
                query_rel.norm(dim=-1, keepdim=True),
            ],
            dim=-1,
        )  # [B, 3]
        c_norms = torch.cat(
            [
                cand_comp.norm(dim=-1, keepdim=True),
                cand_inp.norm(dim=-1, keepdim=True),
                cand_rel.norm(dim=-1, keepdim=True),
            ],
            dim=-1,
        )  # [B, 3]

        features = torch.cat([sim_c, sim_i, sim_r, q_norms, c_norms], dim=-1)  # [B, 9]
        scores = self.mlp(features)  # [B, 1]

        # Dummy halt logit for API compatibility
        halt_logits = torch.zeros_like(scores)

        return scores, halt_logits, [scores]

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
