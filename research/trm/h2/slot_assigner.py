"""SlotAffinityNet — Tiny neural network for content-to-pool prediction.

Predicts which supply_map pool a content item belongs to.
Used by the card builder to reassign and reorder supply_map pools before
sequential consumption, fixing misrouted content items.

Architecture: [content_embedding(384D) || pool_embedding(16D)] → 400D → 32 → 1
~6.5K parameters. Inference: <1ms for 50 pairs (10 items × 5 pools).

Pool-based vocabulary (5 classes, not 8 slot types):
  DecoratedText/TextParagraph/Image/Column all share `content_texts` pool,
  so merging them into one class makes the task learnable.
"""

from __future__ import annotations

import torch
import torch.nn as nn

# Pool vocabulary — maps pool keys to integer IDs.
# This is what the model predicts: which pool an item belongs to.
POOL_VOCAB: dict[str, int] = {
    "buttons": 0,
    "content_texts": 1,
    "grid_items": 2,
    "chips": 3,
    "carousel_cards": 4,
}

# Reverse mapping: ID → pool key
POOL_NAMES: dict[int, str] = {v: k for k, v in POOL_VOCAB.items()}

N_POOLS = len(POOL_VOCAB)

# Component name → pool key (for training data label generation)
COMPONENT_TO_POOL: dict[str, str] = {
    "Button": "buttons",
    "ButtonList": "buttons",
    "DecoratedText": "content_texts",
    "TextParagraph": "content_texts",
    "Image": "content_texts",
    "Column": "content_texts",
    "Columns": "content_texts",
    "Grid": "grid_items",
    "GridItem": "grid_items",
    "Chip": "chips",
    "ChipList": "chips",
    "Carousel": "carousel_cards",
    "CarouselCard": "carousel_cards",
}

# Specificity order for greedy assignment — most specific pools first
# Prevents broad pools (content_texts) from stealing specific items
POOL_SPECIFICITY_ORDER: list[str] = [
    "chips",
    "grid_items",
    "carousel_cards",
    "buttons",
    "content_texts",  # catch-all last
]

# Legacy compatibility: keep SLOT_TYPE_VOCAB as alias
SLOT_TYPE_VOCAB = POOL_VOCAB
SLOT_TO_POOL = {k: k for k in POOL_VOCAB}  # identity mapping (pool → pool)
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
