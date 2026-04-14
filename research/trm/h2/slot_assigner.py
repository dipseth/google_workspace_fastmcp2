"""SlotAffinityNet — Tiny neural network for content-to-pool prediction.

Predicts which supply_map pool a content item belongs to.
Used by the card builder to reassign and reorder supply_map pools before
sequential consumption, fixing misrouted content items.

Architecture: Linear(384, hidden) → SiLU → Dropout → Linear(hidden, n_pools)
~25K parameters with hidden=64. Inference: <1ms for 50 pairs.

Pool vocabulary is domain-driven via DomainConfig (default: gchat with 5 pools).
"""

from __future__ import annotations

import torch
import torch.nn as nn

from .domain_config import GCHAT_DOMAIN, get_domain_or_default

# ── Domain-sourced constants (default: gchat) ──────────────────────
# These module-level constants exist for backward compatibility.
# New code should use DomainConfig directly.
_DEFAULT_DOMAIN = GCHAT_DOMAIN

POOL_VOCAB: dict[str, int] = dict(_DEFAULT_DOMAIN.pool_vocab)
POOL_NAMES: dict[int, str] = _DEFAULT_DOMAIN.pool_names
N_POOLS = _DEFAULT_DOMAIN.n_pools
COMPONENT_TO_POOL: dict[str, str] = dict(_DEFAULT_DOMAIN.component_to_pool)
POOL_SPECIFICITY_ORDER: list[str] = list(_DEFAULT_DOMAIN.specificity_order)

# Legacy compatibility aliases
SLOT_TYPE_VOCAB = POOL_VOCAB
SLOT_TO_POOL = {k: k for k in POOL_VOCAB}
SLOT_TYPE_NAMES = POOL_NAMES
SPECIFICITY_ORDER = POOL_SPECIFICITY_ORDER
N_SLOT_TYPES = N_POOLS


class SlotAffinityNet(nn.Module):
    """Direct content-to-pool classifier.

    Input: content embedding (384D MiniLM) → pool class logits.
    Simpler than pairwise scoring — directly predicts which pool.

    Architecture: Linear(384, hidden) → SiLU → Dropout → Linear(hidden, 5)
    ~25K parameters with hidden=64.
    """

    def __init__(
        self,
        content_dim: int = 384,
        slot_embed_dim: int = 16,  # kept for checkpoint compat, unused
        n_slot_types: int = N_POOLS,
        hidden: int = 64,
    ):
        super().__init__()
        self.content_dim = content_dim
        self.slot_embed_dim = slot_embed_dim
        self.n_slot_types = n_slot_types
        self.hidden = hidden

        self.classifier = nn.Sequential(
            nn.Linear(content_dim, hidden),
            nn.SiLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden, n_slot_types),
        )

    def forward(
        self, content_emb: torch.Tensor, slot_type_ids: torch.Tensor = None
    ) -> torch.Tensor:
        """Classify content items into pools.

        Args:
            content_emb: [B, content_dim] — MiniLM embeddings of content text
            slot_type_ids: ignored (kept for API compat)

        Returns:
            [B, n_pools] class logits
        """
        return self.classifier(content_emb)

    def score_all_slots(self, content_emb: torch.Tensor) -> torch.Tensor:
        """Score a batch of content items against ALL pools.

        Args:
            content_emb: [B, content_dim]

        Returns:
            [B, n_pools] class logits
        """
        return self.classifier(content_emb)
