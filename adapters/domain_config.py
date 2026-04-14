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
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class DomainConfig:
    """Configuration for a single domain's pool/slot vocabulary and training content.

    Required fields define the pool structure. Optional fields provide domain-specific
    content knowledge used for training data generation (content-aware features, templates,
    and hard negatives). Domains without content fields still work — they just skip
    content-aware training features.
    """

    # ── Required: pool structure ──────────────────────────────────────
    domain_id: str
    pool_vocab: Dict[str, int]
    component_to_pool: Dict[str, str]
    specificity_order: List[str]
    rewrap_rules: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # ── Optional: content knowledge for training ──────────────────────
    content_affinity: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    content_templates: Dict[str, List[str]] = field(default_factory=dict)
    confusion_pairs: List[tuple] = field(default_factory=list)

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

    @property
    def has_content_knowledge(self) -> bool:
        """Whether this domain has content affinity/templates for training."""
        return bool(self.content_affinity) or bool(self.content_templates)

    @classmethod
    def from_checkpoint(cls, checkpoint: dict) -> Optional["DomainConfig"]:
        """Reconstruct a DomainConfig from checkpoint metadata."""
        pool_vocab = checkpoint.get("pool_vocab")
        domain_id = checkpoint.get("domain_id")
        if not pool_vocab or not domain_id:
            return None

        return cls(
            domain_id=domain_id,
            pool_vocab=pool_vocab,
            component_to_pool=checkpoint.get("component_to_pool", {}),
            specificity_order=checkpoint.get(
                "specificity_order", list(pool_vocab.keys())
            ),
            rewrap_rules=checkpoint.get("rewrap_rules", {}),
            content_affinity=checkpoint.get("content_affinity", {}),
            content_templates=checkpoint.get("content_templates", {}),
            confusion_pairs=[tuple(p) for p in checkpoint.get("confusion_pairs", [])],
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
        "content_texts",
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
        "content": 0,
        "layout": 1,
        "chrome": 2,
        "structure": 3,
        "interactive": 4,
    },
    component_to_pool={
        "EmailSpec": "content",
        "HeroBlock": "content",
        "TextBlock": "content",
        "ButtonBlock": "content",
        "ImageBlock": "content",
        "ColumnsBlock": "layout",
        "Column": "layout",
        "HeaderBlock": "chrome",
        "FooterBlock": "chrome",
        "SocialBlock": "chrome",
        "TableBlock": "chrome",
        "SpacerBlock": "structure",
        "DividerBlock": "structure",
        "AccordionBlock": "interactive",
        "CarouselBlock": "interactive",
    },
    specificity_order=[
        "interactive",
        "chrome",
        "structure",
        "layout",
        "content",
    ],
    rewrap_rules={
        "content": {"text_field": "text", "defaults": {}},
        "layout": {"text_field": "text", "defaults": {}},
        "chrome": {"text_field": "text", "defaults": {}},
        "structure": {"text_field": "text", "defaults": {}},
        "interactive": {"text_field": "title", "defaults": {}},
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
    """Resolve domain config from checkpoint metadata or explicit ID."""
    if checkpoint:
        config = DomainConfig.from_checkpoint(checkpoint)
        if config:
            if config.domain_id not in _DOMAIN_REGISTRY:
                register_domain(config)
            return config

    return get_domain_or_default(domain_id)
