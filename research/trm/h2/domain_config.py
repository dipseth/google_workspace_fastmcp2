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
    # Maps component names to keyword patterns and semantic type.
    # Example: {"Button": {"patterns": ["submit", "deploy"], "type": "action"}}
    content_affinity: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Maps component names to lists of realistic content text examples.
    # Example: {"Button": ["Submit", "Deploy", "Cancel"]}
    content_templates: Dict[str, List[str]] = field(default_factory=dict)

    # Hard negative pairs: (content_text, wrong_pool) for confusion training.
    # Example: [("Status: Online", "chips"), ("Deploy", "content_texts")]
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

    @property
    def has_content_knowledge(self) -> bool:
        """Whether this domain has content affinity/templates for training."""
        return bool(self.content_affinity) or bool(self.content_templates)

    @classmethod
    def from_checkpoint(cls, checkpoint: dict) -> Optional["DomainConfig"]:
        """Reconstruct a DomainConfig from checkpoint metadata.

        Returns None if the checkpoint doesn't contain domain info.
        Content knowledge fields are restored if present in the checkpoint.
        """
        pool_vocab = checkpoint.get("pool_vocab")
        domain_id = checkpoint.get("domain_id")
        if not pool_vocab or not domain_id:
            return None

        component_to_pool = checkpoint.get("component_to_pool", {})
        specificity_order = checkpoint.get("specificity_order", list(pool_vocab.keys()))
        rewrap_rules = checkpoint.get("rewrap_rules", {})
        content_affinity = checkpoint.get("content_affinity", {})
        content_templates = checkpoint.get("content_templates", {})
        confusion_pairs = [tuple(p) for p in checkpoint.get("confusion_pairs", [])]

        return cls(
            domain_id=domain_id,
            pool_vocab=pool_vocab,
            component_to_pool=component_to_pool,
            specificity_order=specificity_order,
            rewrap_rules=rewrap_rules,
            content_affinity=content_affinity,
            content_templates=content_templates,
            confusion_pairs=confusion_pairs,
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
    content_affinity={
        "ButtonList": {
            "patterns": [
                "submit",
                "deploy",
                "restart",
                "cancel",
                "approve",
                "reject",
                "send",
                "save",
                "delete",
                "confirm",
                "run",
                "stop",
                "retry",
                "update",
                "refresh",
                "download",
                "upload",
                "connect",
            ],
            "type": "action",
        },
        "Button": {
            "patterns": [
                "submit",
                "deploy",
                "restart",
                "cancel",
                "approve",
                "reject",
                "send",
                "save",
                "delete",
                "ok",
                "go",
                "start",
            ],
            "type": "action",
        },
        "DecoratedText": {
            "patterns": [
                "status",
                "info",
                "details",
                "label",
                "name",
                "email",
                "description",
                "version",
                "type",
                "state",
                "count",
                "total",
                "last updated",
                "created",
                "owner",
            ],
            "type": "display",
        },
        "TextParagraph": {
            "patterns": [
                "message",
                "description",
                "note",
                "warning",
                "error",
                "summary",
                "explanation",
                "instructions",
                "help",
            ],
            "type": "narrative",
        },
        "Grid": {
            "patterns": [
                "list",
                "items",
                "products",
                "results",
                "files",
                "users",
                "servers",
                "services",
                "resources",
                "entries",
            ],
            "type": "tabular",
        },
        "GridItem": {
            "patterns": ["item", "product", "file", "user", "server", "result"],
            "type": "tabular",
        },
        "Image": {
            "patterns": [
                "photo",
                "screenshot",
                "banner",
                "logo",
                "avatar",
                "chart",
                "graph",
                "diagram",
                "icon",
            ],
            "type": "media",
        },
        "ChipList": {
            "patterns": [
                "tag",
                "label",
                "category",
                "filter",
                "option",
                "skill",
                "topic",
                "status",
            ],
            "type": "categorical",
        },
        "Chip": {
            "patterns": ["tag", "label", "category", "filter", "option"],
            "type": "categorical",
        },
        "SelectionInput": {
            "patterns": [
                "choose",
                "select",
                "pick",
                "option",
                "preference",
                "setting",
                "mode",
                "type",
            ],
            "type": "input",
        },
        "TextInput": {
            "patterns": [
                "enter",
                "type",
                "search",
                "name",
                "email",
                "url",
                "comment",
                "note",
                "message",
            ],
            "type": "input",
        },
        "DateTimePicker": {
            "patterns": [
                "date",
                "time",
                "schedule",
                "deadline",
                "start",
                "end",
                "due",
                "appointment",
            ],
            "type": "temporal",
        },
        "SwitchControl": {
            "patterns": [
                "enable",
                "disable",
                "toggle",
                "on",
                "off",
                "active",
                "notifications",
                "auto",
            ],
            "type": "toggle",
        },
        "Columns": {
            "patterns": [
                "compare",
                "side by side",
                "left",
                "right",
                "details",
                "summary",
            ],
            "type": "layout",
        },
        "Carousel": {
            "patterns": ["slides", "gallery", "pages", "steps", "cards"],
            "type": "sequential",
        },
        "CarouselCard": {
            "patterns": ["slide", "page", "step", "card", "panel"],
            "type": "sequential",
        },
        "Divider": {"patterns": [], "type": "structural"},
        "Section": {"patterns": [], "type": "structural"},
    },
    content_templates={
        "ButtonList": [
            "Deploy Service, Rollback, View Logs",
            "Approve Request, Deny Request",
            "Start Pipeline, Stop Pipeline, View Status",
            "Submit Form, Cancel",
            "Restart Server, Check Health, View Metrics",
            "Save Changes, Discard",
            "Connect, Disconnect, Refresh",
            "Download Report, Export CSV",
            "Run Tests, Deploy to Staging, Deploy to Production",
            "Enable Feature, Disable Feature",
        ],
        "Button": [
            "Submit",
            "Deploy",
            "Approve",
            "Cancel",
            "Restart",
            "Send",
            "Save",
            "Delete",
            "Confirm",
            "Retry",
        ],
        "DecoratedText": [
            "Status: Online, Version: 2.4.1, Last Updated: 2 hours ago",
            "Name: API Gateway, Type: Service, Region: us-west-2",
            "Owner: platform-team, Priority: High, State: Active",
            "CPU: 45%, Memory: 2.1GB, Uptime: 14 days",
            "Email: admin@company.com, Role: Administrator",
            "Total Requests: 1.2M, Error Rate: 0.03%",
            "Created: March 15, Modified: March 20",
            "Build: #1847, Branch: main, Commit: a3f2b1c",
            "Latency P99: 120ms, Throughput: 5K rps",
            "License: Enterprise, Seats: 50/100, Expires: 2027-01-01",
        ],
        "TextParagraph": [
            "The deployment completed successfully. All health checks passed.",
            "Warning: This action cannot be undone. Please confirm.",
            "Pipeline failed at stage 3: unit tests. See logs for details.",
            "Welcome to the dashboard. Select a service to view metrics.",
            "Note: Maintenance window scheduled for Saturday 2am-4am UTC.",
        ],
        "Grid": [
            "web-server-01, web-server-02, web-server-03, db-primary, db-replica",
            "index.html, styles.css, app.js, config.json, README.md",
            "Alice Johnson, Bob Smith, Carol Williams, David Brown",
            "US West, US East, EU Central, AP Southeast",
            "v1.0.0, v1.1.0, v1.2.0, v2.0.0-beta",
        ],
        "GridItem": [
            "web-server-01",
            "database-primary",
            "cache-node-1",
            "api-gateway",
            "load-balancer",
            "worker-queue",
        ],
        "Image": [
            "Architecture Diagram",
            "Performance Chart",
            "Team Photo",
            "System Dashboard Screenshot",
            "Logo",
            "Error Screenshot",
        ],
        "ChipList": [
            "Python, JavaScript, Go, Rust, TypeScript",
            "Bug, Feature, Enhancement, Documentation, Security",
            "High Priority, Medium Priority, Low Priority",
            "Active, Inactive, Pending, Archived",
            "Frontend, Backend, DevOps, QA, Design",
        ],
        "Chip": [
            "Python",
            "Bug",
            "High Priority",
            "Active",
            "Frontend",
        ],
        "SelectionInput": [
            "Select region: US West, US East, EU, APAC",
            "Choose environment: Development, Staging, Production",
            "Select priority: Critical, High, Medium, Low",
        ],
        "TextInput": [
            "Enter service name",
            "Search users",
            "Add comment",
            "Enter email address",
            "Type your message",
        ],
        "DateTimePicker": [
            "Schedule deployment",
            "Set deadline",
            "Pick start date",
            "Choose maintenance window",
            "Select meeting time",
        ],
        "SwitchControl": [
            "Enable notifications",
            "Auto-scaling",
            "Debug mode",
            "Maintenance mode",
            "Feature flag: dark-theme",
        ],
        "Columns": [
            "Current vs Previous, Before and After, Plan vs Actual",
        ],
        "Carousel": [
            "Step 1: Configure, Step 2: Deploy, Step 3: Verify",
            "Overview, Details, Metrics, Logs",
        ],
        "CarouselCard": [
            "Configuration Panel",
            "Deployment Status",
            "Metric Dashboard",
        ],
    },
    confusion_pairs=[
        ("Status: Online", "chips"),  # Status could be a chip filter
        ("Deploy", "content_texts"),  # Deploy verb as label
        ("High Priority", "buttons"),  # Priority as button
        ("API Gateway", "chips"),  # Service name as tag
        ("v2.0.0", "chips"),  # Version as tag
        ("Submit", "content_texts"),  # Action verb as label
        ("Active", "buttons"),  # Status as action
        ("web-server-01", "buttons"),  # Server name as button text
    ],
)

EMAIL_DOMAIN = DomainConfig(
    domain_id="email",
    # Pool vocabulary mirrors DSL categories from email_wrapper_setup.py
    pool_vocab={
        "content": 0,  # HeroBlock, TextBlock, ButtonBlock, ImageBlock
        "layout": 1,  # ColumnsBlock, Column
        "chrome": 2,  # HeaderBlock, FooterBlock, SocialBlock, TableBlock
        "structure": 3,  # SpacerBlock, DividerBlock
        "interactive": 4,  # AccordionBlock, CarouselBlock
    },
    # Real MJML component names from gmail.mjml_types
    component_to_pool={
        "EmailSpec": "content",  # Root container — catch-all
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
        "interactive",  # Most specific (accordion, carousel)
        "chrome",  # Headers, footers, social
        "structure",  # Spacers, dividers
        "layout",  # Columns
        "content",  # Catch-all last
    ],
    rewrap_rules={
        "content": {"text_field": "text", "defaults": {}},
        "layout": {"text_field": "text", "defaults": {}},
        "chrome": {"text_field": "text", "defaults": {}},
        "structure": {"text_field": "text", "defaults": {}},
        "interactive": {"text_field": "title", "defaults": {}},
    },
    content_affinity={
        "HeroBlock": {
            "patterns": [
                "welcome",
                "announcement",
                "launch",
                "introducing",
                "hero",
                "headline",
                "banner",
                "promo",
                "sale",
                "event",
                "invite",
            ],
            "type": "hero",
        },
        "TextBlock": {
            "patterns": [
                "paragraph",
                "description",
                "details",
                "body",
                "content",
                "message",
                "info",
                "update",
                "summary",
                "note",
            ],
            "type": "narrative",
        },
        "ButtonBlock": {
            "patterns": [
                "click",
                "cta",
                "action",
                "subscribe",
                "download",
                "buy",
                "register",
                "sign up",
                "get started",
                "learn more",
                "shop",
                "book",
                "try",
                "explore",
                "view",
                "open",
            ],
            "type": "action",
        },
        "ImageBlock": {
            "patterns": [
                "photo",
                "screenshot",
                "banner",
                "logo",
                "product",
                "chart",
                "diagram",
                "illustration",
                "thumbnail",
            ],
            "type": "media",
        },
        "ColumnsBlock": {
            "patterns": ["compare", "side by side", "features", "pricing"],
            "type": "layout",
        },
        "Column": {"patterns": [], "type": "layout"},
        "HeaderBlock": {
            "patterns": ["brand", "logo", "company", "header", "masthead"],
            "type": "chrome",
        },
        "FooterBlock": {
            "patterns": [
                "unsubscribe",
                "footer",
                "legal",
                "address",
                "copyright",
                "privacy",
                "terms",
                "contact",
            ],
            "type": "chrome",
        },
        "SocialBlock": {
            "patterns": [
                "twitter",
                "facebook",
                "linkedin",
                "instagram",
                "youtube",
                "social",
                "follow",
                "share",
                "connect",
            ],
            "type": "social",
        },
        "TableBlock": {
            "patterns": [
                "table",
                "data",
                "row",
                "column",
                "comparison",
                "specs",
                "pricing",
                "schedule",
                "results",
                "inventory",
            ],
            "type": "tabular",
        },
        "SpacerBlock": {"patterns": [], "type": "structural"},
        "DividerBlock": {"patterns": [], "type": "structural"},
        "AccordionBlock": {
            "patterns": [
                "faq",
                "question",
                "expand",
                "collapse",
                "details",
                "sections",
                "topics",
                "help",
            ],
            "type": "interactive",
        },
        "CarouselBlock": {
            "patterns": [
                "gallery",
                "slides",
                "images",
                "showcase",
                "portfolio",
                "products",
                "carousel",
            ],
            "type": "interactive",
        },
        "EmailSpec": {"patterns": [], "type": "structural"},
    },
    content_templates={
        "HeroBlock": [
            "Welcome to Acme! Your account is ready, Get Started",
            "Introducing Our New Product Line, Shop Now",
            "You're Invited: Annual Conference 2026, Register Today",
            "Flash Sale: 50% Off Everything, Limited Time",
            "Important Security Update for Your Account",
            "Happy Holidays from the Team, See What's New",
        ],
        "TextBlock": [
            "Thanks for signing up! Here's what you can do with your new account.",
            "We're excited to share some important updates with you.",
            "Your order #12345 has been confirmed and is being processed.",
            "Please review the following changes to your subscription.",
            "This week's highlights include new features and improvements.",
            "Reminder: Your trial expires in 3 days. Upgrade to keep access.",
        ],
        "ButtonBlock": [
            "Get Started",
            "Shop Now",
            "Learn More",
            "Download",
            "Subscribe",
            "View Dashboard",
            "Confirm Email",
            "Reset Password",
            "Upgrade Plan",
            "Book a Demo",
        ],
        "ImageBlock": [
            "Product Screenshot",
            "Team Photo",
            "Infographic",
            "Feature Illustration",
            "Event Banner",
            "Logo",
        ],
        "HeaderBlock": [
            "Acme Corp, Monthly Newsletter",
            "TechStartup, Product Update",
            "Your Company, Weekly Digest",
        ],
        "FooterBlock": [
            "123 Main St, San Francisco CA, Unsubscribe, Privacy Policy",
            "© 2026 Acme Corp. All rights reserved. Update preferences.",
            "Questions? Contact support@example.com, Manage notifications",
        ],
        "SocialBlock": [
            "Twitter, LinkedIn, Facebook, Instagram",
            "Follow us: GitHub, YouTube, Discord",
            "Connect: Twitter, LinkedIn",
        ],
        "TableBlock": [
            "Plan, Price, Features: Starter $9/mo Basic, Pro $29/mo Advanced, Enterprise $99/mo Full",
            "Item, Quantity, Price: Widget A 2 $19.98, Widget B 1 $24.99, Shipping $5.00",
            "Date, Event, Location: Mar 15 Keynote Hall A, Mar 16 Workshop Room B",
        ],
        "AccordionBlock": [
            "How do I reset my password?, What payment methods accepted?, How to cancel?",
            "Getting Started, Advanced Features, Troubleshooting, Contact Support",
        ],
        "CarouselBlock": [
            "Product Front View, Product Side View, Product Detail, Product In Use",
            "Office Tour, Team Event, Product Launch, Customer Spotlight",
        ],
    },
    confusion_pairs=[
        ("Get Started", "chrome"),  # CTA button text as header
        ("Unsubscribe", "content"),  # Footer text as content
        ("Product Screenshot", "interactive"),  # Image as carousel
        ("FAQ", "content"),  # Accordion keyword as text
        ("Follow us", "content"),  # Social as text
        ("$29/mo", "content"),  # Table data as text
    ],
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
