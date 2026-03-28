"""Domain configuration registry for multi-domain TRN support.

Each domain (gchat, email, etc.) defines its own pool vocabulary,
component-to-pool mapping, specificity order, and item rewrap rules.
Domain configs can be:
  1. Looked up by name from the registry
  2. Loaded from checkpoint metadata (pool_vocab, domain_id)
  3. Passed explicitly to model constructors and slot assignment

This decouples the model architecture from any single domain's vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class DomainConfig:
    """Configuration for a single domain's pool/slot vocabulary."""

    domain_id: str
    pool_vocab: Dict[str, int]
    component_to_pool: Dict[str, str]
    specificity_order: List[str]
    rewrap_rules: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def pool_names(self) -> Dict[int, str]:
        return {v: k for k, v in self.pool_vocab.items()}

    @property
    def n_pools(self) -> int:
        return len(self.pool_vocab)

    def rewrap_item(self, item: Any, source_pool: str, target_pool: str) -> dict:
        """Re-wrap an item for a different pool's expected schema."""
        if isinstance(item, dict):
            result = dict(item)
        else:
            result = {}

        # Extract text from original item
        text = ""
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            for key in ("text", "title", "label", "subtitle", "styled"):
                val = item.get(key)
                if val and isinstance(val, str):
                    text = val
                    break

        rules = self.rewrap_rules.get(target_pool, {})
        if rules:
            text_field = rules.get("text_field", "text")
            result[text_field] = text
            for k, v in rules.get("defaults", {}).items():
                result.setdefault(k, v)
        else:
            result["text"] = text

        return result

    @classmethod
    def from_checkpoint(cls, checkpoint: dict) -> Optional["DomainConfig"]:
        """Reconstruct a DomainConfig from checkpoint metadata.

        Returns None if the checkpoint doesn't contain domain info.
        """
        pool_vocab = checkpoint.get("pool_vocab")
        domain_id = checkpoint.get("domain_id")
        if not pool_vocab or not domain_id:
            return None

        component_to_pool = checkpoint.get("component_to_pool", {})
        specificity_order = checkpoint.get("specificity_order", list(pool_vocab.keys()))
        rewrap_rules = checkpoint.get("rewrap_rules", {})

        return cls(
            domain_id=domain_id,
            pool_vocab=pool_vocab,
            component_to_pool=component_to_pool,
            specificity_order=specificity_order,
            rewrap_rules=rewrap_rules,
        )


# ── Domain Definitions ─────────────────────────────────────────────

GCHAT_DOMAIN = DomainConfig(
    domain_id="gchat",
    pool_vocab={
        "buttons": 0,
        "content_texts": 1,
        "grid_items": 2,
        "chips": 3,
        "carousel_cards": 4,
    },
    component_to_pool={
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
    },
    specificity_order=[
        "chips",
        "grid_items",
        "carousel_cards",
        "buttons",
        "content_texts",  # catch-all last
    ],
    rewrap_rules={
        "buttons": {"text_field": "text", "defaults": {"url": ""}},
        "chips": {"text_field": "label", "defaults": {"url": ""}},
        "content_texts": {"text_field": "text", "defaults": {"wrapText": True}},
        "grid_items": {"text_field": "title", "defaults": {}},
        "carousel_cards": {"text_field": "title", "defaults": {}},
    },
)

EMAIL_DOMAIN = DomainConfig(
    domain_id="email",
    pool_vocab={
        "subject": 0,
        "body_sections": 1,
        "attachments": 2,
        "recipients": 3,
    },
    component_to_pool={
        "Subject": "subject",
        "BodySection": "body_sections",
        "Paragraph": "body_sections",
        "Heading": "body_sections",
        "Attachment": "attachments",
        "Recipient": "recipients",
        "CC": "recipients",
    },
    specificity_order=[
        "subject",
        "attachments",
        "recipients",
        "body_sections",
    ],
    rewrap_rules={
        "subject": {"text_field": "text", "defaults": {}},
        "body_sections": {"text_field": "content", "defaults": {}},
        "attachments": {"text_field": "filename", "defaults": {}},
        "recipients": {"text_field": "email", "defaults": {}},
    },
)

# ── Registry ────────────────────────────────────────────────────────

_DOMAIN_REGISTRY: Dict[str, DomainConfig] = {
    "gchat": GCHAT_DOMAIN,
    "email": EMAIL_DOMAIN,
}


def register_domain(config: DomainConfig) -> None:
    """Register a new domain configuration."""
    _DOMAIN_REGISTRY[config.domain_id] = config


def get_domain(domain_id: str) -> DomainConfig:
    """Get domain config by ID. Raises KeyError if not found."""
    return _DOMAIN_REGISTRY[domain_id]


def get_domain_or_default(domain_id: Optional[str] = None) -> DomainConfig:
    """Get domain config, falling back to gchat if not specified."""
    if domain_id and domain_id in _DOMAIN_REGISTRY:
        return _DOMAIN_REGISTRY[domain_id]
    return GCHAT_DOMAIN


def list_domains() -> List[str]:
    """List all registered domain IDs."""
    return list(_DOMAIN_REGISTRY.keys())


def resolve_domain(
    checkpoint: Optional[dict] = None,
    domain_id: Optional[str] = None,
) -> DomainConfig:
    """Resolve domain config from checkpoint metadata or explicit ID.

    Priority:
      1. Checkpoint metadata (if it contains domain info)
      2. Explicit domain_id
      3. Default (gchat)
    """
    if checkpoint:
        config = DomainConfig.from_checkpoint(checkpoint)
        if config:
            # Register it if new (e.g., from a checkpoint trained on a new domain)
            if config.domain_id not in _DOMAIN_REGISTRY:
                register_domain(config)
            return config

    return get_domain_or_default(domain_id)
