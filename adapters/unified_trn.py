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

This is the *inference* definition and is the source of truth for production.
Training scripts live in the internal `research/trm/h2/` tree, which is NOT part
of the published repo -- production must never import from it. If you change the
architecture here, mirror it there (and vice versa) or checkpoints stop loading.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from .domain_config import get_domain_or_default

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

# Feature normalization modes. Stored in the checkpoint as ``feature_norm`` so
# inference applies exactly what training saw. Absent key == "none" (legacy).
FEATURE_NORM_NONE = "none"
FEATURE_NORM_GROUP_ZSCORE = "group_zscore"
FEATURE_NORMS = (FEATURE_NORM_NONE, FEATURE_NORM_GROUP_ZSCORE)
_ZSCORE_EPS = 1e-6


def normalize_feature_group(
    features: torch.Tensor | list[list[float]],
    norm: str = FEATURE_NORM_NONE,
    mask: torch.Tensor | None = None,
) -> torch.Tensor:
    """Normalize one query's candidate feature matrix ``[K, D]``.

    ``group_zscore`` z-scores every feature *within the candidate group*, so the
    model sees "how does this candidate compare to its competitors" instead of
    absolute magnitudes. Absolute magnitudes shift between wrapped modules (a
    −3σ shift saturated every logit on qdrant_client.models — see
    docs/TRM_TRANSFER_HANDOFF_2026-07-25.md), relative ones do not. A feature
    that is constant across the group carries no ranking signal and becomes 0.

    ``mask`` (``[K]``, 1 = real candidate) excludes padding rows from the
    statistics; padded rows are zeroed in the output.

    Training (research/trm/h2/train_unified.py) and inference (search_mixin)
    both call this function — never reimplement it on one side.
    """
    x = torch.as_tensor(features, dtype=torch.float32)
    if norm == FEATURE_NORM_NONE or x.numel() == 0:
        return x
    if norm != FEATURE_NORM_GROUP_ZSCORE:
        raise ValueError(
            f"unknown feature_norm {norm!r}; expected one of {FEATURE_NORMS}"
        )
    if x.dim() != 2:
        raise ValueError(f"expected [K, D] feature matrix, got shape {tuple(x.shape)}")
    if mask is None:
        m = torch.ones(x.shape[0], dtype=torch.float32)
    else:
        m = torch.as_tensor(mask, dtype=torch.float32)
    n = m.sum().clamp(min=1.0)
    w = m.unsqueeze(-1)
    mean = (x * w).sum(0, keepdim=True) / n
    var = (((x - mean) ** 2) * w).sum(0, keepdim=True) / n
    std = var.sqrt()
    z = torch.where(
        std > _ZSCORE_EPS, (x - mean) / std.clamp(min=_ZSCORE_EPS), torch.zeros_like(x)
    )
    return z * w


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
        mode_flag: bool = False,
    ):
        super().__init__()
        self.structural_dim = structural_dim
        self.content_dim = content_dim
        self.hidden = hidden
        self.n_pools = n_pools
        # With raw features, build mode's all-zero structural vector sat outside
        # the search distribution (sims ~0.5) and implicitly told the backbone
        # which mode it was in. Group z-scoring centres search features on 0,
        # so the modes collide and pool accuracy collapses (97% -> 68%). The
        # flag appends an explicit build/search bit to the structural input.
        # Checkpoint key: ``mode_flag`` (absent == False, legacy shapes).
        self.mode_flag = mode_flag

        enc_dim = 32

        # Separate input encoders (different scales/semantics)
        self.structural_enc = nn.Sequential(
            nn.Linear(structural_dim + (1 if mode_flag else 0), enc_dim),
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
        if self.mode_flag:
            flag = structural_features.new_full(
                (*structural_features.shape[:-1], 1), 1.0 if mode == "build" else 0.0
            )
            structural_features = torch.cat([structural_features, flag], dim=-1)
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
