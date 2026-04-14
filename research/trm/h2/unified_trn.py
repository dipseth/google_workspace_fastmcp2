"""UnifiedTRN — Tiny Recursive Network replacing DualHeadScorerMW + SlotAffinityNet.

Single model with shared backbone, 4 task heads:
  - form_head: component ranking (search mode)
  - content_head: content ranking (search mode)
  - pool_head: content-to-pool classification (build mode)
  - halt_head: learned convergence detector (search mode)

Two operating modes:
  - search: structural=17D per candidate, content=384D query. Uses form/content/halt heads.
  - build: structural=zeros(17), content=384D per item. Uses pool_head only.

Architecture:
  structural_enc: Linear(17,32) → SiLU
  content_enc: Linear(384,32) → SiLU
  backbone: [64] → Linear(64,64) → SiLU → Dropout → Linear(64,64) → SiLU → Dropout
  form_head: Linear(64,32) → SiLU → Linear(32,1)
  content_head: Linear(64,32) → SiLU → Linear(32,1)
  pool_head: Linear(64,32) → SiLU → Linear(32,5)
  halt_head: Linear(64,16) → SiLU → Linear(16,1) → Sigmoid

~28.7K parameters total.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from .domain_config import get_domain, get_domain_or_default

# V5 feature names (17D) — domain-agnostic structural + content features
FEATURE_NAMES_V5 = [
    "sim_c_mean",
    "sim_c_max",
    "sim_c_std",
    "sim_c_coverage",
    "sim_i_mean",
    "sim_i_max",
    "sim_i_std",
    "sim_i_coverage",
    "sim_relationships",
    "is_parent",
    "is_child",
    "is_sibling",
    "depth_ratio",
    "n_shared_ancestors",
    "sim_content",
    "content_density",
    "content_form_alignment",
]

STRUCTURAL_DIM = len(FEATURE_NAMES_V5)  # 17
CONTENT_DIM = 384  # MiniLM
DEFAULT_N_POOLS = 5  # Override via constructor or DomainConfig


def get_domain_defaults(domain_id: str = "gchat") -> dict:
    """Get pool vocab and component-to-pool mapping for a domain.

    Returns dict with keys: pool_vocab, component_to_pool, n_pools.
    Falls back to gchat defaults if domain not found.
    """
    domain = get_domain_or_default(domain_id)
    return {
        "pool_vocab": dict(domain.pool_vocab),
        "component_to_pool": dict(domain.component_to_pool),
        "n_pools": domain.n_pools,
    }


class UnifiedTRN(nn.Module):
    """Unified Tiny Recursive Network.

    Replaces DualHeadScorerMW + SlotAffinityNet with a single model.
    Two operating modes: search (candidate scoring) and build (content routing).
    """

    def __init__(
        self,
        structural_dim: int = STRUCTURAL_DIM,
        content_dim: int = CONTENT_DIM,
        hidden: int = 64,
        n_pools: int = DEFAULT_N_POOLS,
        dropout: float = 0.15,
    ):
        super().__init__()
        self.structural_dim = structural_dim
        self.content_dim = content_dim
        self.hidden = hidden
        self.n_pools = n_pools

        enc_dim = 32

        # Separate input encoders (different scales/semantics)
        self.structural_enc = nn.Sequential(
            nn.Linear(structural_dim, enc_dim),
            nn.SiLU(),
        )
        self.content_enc = nn.Sequential(
            nn.Linear(content_dim, enc_dim),
            nn.SiLU(),
        )

        # Shared backbone
        self.backbone = nn.Sequential(
            nn.Linear(enc_dim * 2, hidden),
            nn.SiLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, hidden),
            nn.SiLU(),
            nn.Dropout(dropout),
        )

        head_dim = hidden // 2  # 32 when hidden=64

        # Search-mode heads
        self.form_head = nn.Sequential(
            nn.Linear(hidden, head_dim),
            nn.SiLU(),
            nn.Linear(head_dim, 1),
        )
        self.content_head = nn.Sequential(
            nn.Linear(hidden, head_dim),
            nn.SiLU(),
            nn.Linear(head_dim, 1),
        )

        # Build-mode head
        self.pool_head = nn.Sequential(
            nn.Linear(hidden, head_dim),
            nn.SiLU(),
            nn.Linear(head_dim, n_pools),
        )

        # Halt head (learned convergence)
        # LayerNorm(16) before final projection stabilizes train/eval
        # scale shift caused by Dropout in the backbone.
        # NOTE: LayerNorm(1) would kill gradients (single-element norm → always 0).
        self.halt_head = nn.Sequential(
            nn.Linear(hidden, 16),
            nn.LayerNorm(16),
            nn.SiLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(
        self,
        structural_features: torch.Tensor,
        content_embedding: torch.Tensor,
        mode: str = "search",
    ) -> dict[str, torch.Tensor]:
        """Forward pass.

        Args:
            structural_features: [B, structural_dim] — hand-crafted features
            content_embedding: [B, content_dim] — MiniLM embedding
            mode: "search", "build", or "all"

        Returns:
            dict with keys depending on mode:
              search: form_score [B,1], content_score [B,1], halt_prob [B,1]
              build: pool_logits [B, n_pools]
              all: all of the above
        """
        s_enc = self.structural_enc(structural_features)  # [B, 32]
        c_enc = self.content_enc(content_embedding)  # [B, 32]

        combined = torch.cat([s_enc, c_enc], dim=-1)  # [B, 64]
        shared = self.backbone(combined)  # [B, hidden]

        if mode == "build":
            return {"pool_logits": self.pool_head(shared)}

        result = {
            "form_score": self.form_head(shared),
            "content_score": self.content_head(shared),
            "halt_prob": self.halt_head(shared),
        }

        if mode == "all":
            result["pool_logits"] = self.pool_head(shared)

        return result

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
