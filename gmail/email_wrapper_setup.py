"""
Singleton ModuleWrapper for email_blocks — setup, constants, and initialization.

Mirrors the pattern from gchat/wrapper_setup.py using DomainConfig.

Usage:
    from gmail.email_wrapper_setup import get_email_wrapper

    wrapper = get_email_wrapper()
    symbols = wrapper.symbol_mapping
"""

import logging
import threading
from typing import Dict, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger(__name__)

# Thread-safe singleton
_wrapper: Optional["ModuleWrapper"] = None
_wrapper_lock = threading.Lock()

# =============================================================================
# EMAIL-SPECIFIC CONFIGURATION
# =============================================================================

# Container components: JSON field name for children
EMAIL_CONTAINERS = {
    "EmailSpec": ("blocks", None),  # Heterogeneous — holds any EmailBlock
    "ColumnsBlock": ("columns", "Column"),
    "Column": ("blocks", None),  # Heterogeneous
}

# Components that require a wrapper parent
EMAIL_WRAPPER_REQUIREMENTS = {
    "Column": "ColumnsBlock",
}

# Valid block types (top-level within EmailSpec)
EMAIL_WIDGET_TYPES = {
    "HeroBlock",
    "TextBlock",
    "ButtonBlock",
    "ImageBlock",
    "ColumnsBlock",
    "SpacerBlock",
    "DividerBlock",
    "FooterBlock",
    "HeaderBlock",
    "SocialBlock",
    "TableBlock",
    "AccordionBlock",
    "CarouselBlock",
}

EMAIL_HETEROGENEOUS_CONTAINERS = {"EmailSpec", "Column"}

EMAIL_EMPTY_COMPONENTS = {"SpacerBlock", "DividerBlock"}

# Priority overrides for symbol generation
EMAIL_PRIORITY_OVERRIDES = {
    "EmailSpec": 100,
    "ColumnsBlock": 100,
    "HeaderBlock": 80,
    "FooterBlock": 80,
}

# Natural language relationship patterns
EMAIL_NL_RELATIONSHIP_PATTERNS = {
    ("EmailSpec", "HeroBlock"): "email with hero banner",
    ("EmailSpec", "TextBlock"): "email with text content",
    ("EmailSpec", "ButtonBlock"): "email with call-to-action button",
    ("EmailSpec", "ImageBlock"): "email with image",
    ("EmailSpec", "ColumnsBlock"): "email with multi-column layout",
    ("EmailSpec", "SpacerBlock"): "email with spacing",
    ("EmailSpec", "DividerBlock"): "email with divider",
    ("EmailSpec", "FooterBlock"): "email with footer",
    ("EmailSpec", "HeaderBlock"): "email with header",
    ("EmailSpec", "SocialBlock"): "email with social links",
    ("EmailSpec", "TableBlock"): "email with data table",
    ("ColumnsBlock", "Column"): "multi-column email layout",
    ("Column", "TextBlock"): "column with text",
    ("Column", "ButtonBlock"): "column with button",
    ("Column", "ImageBlock"): "column with image",
}


# =============================================================================
# COMPONENT METADATA REGISTRATION
# =============================================================================


def _register_email_component_metadata(wrapper) -> None:
    """Register email-specific component metadata with the ModuleWrapper."""
    wrapper.register_component_metadata_batch(
        containers=EMAIL_CONTAINERS,
        wrapper_requirements=EMAIL_WRAPPER_REQUIREMENTS,
        widget_types=EMAIL_WIDGET_TYPES,
        heterogeneous_containers=EMAIL_HETEROGENEOUS_CONTAINERS,
        empty_components=EMAIL_EMPTY_COMPONENTS,
    )
    logger.info(
        f"Registered email component metadata: "
        f"{len(EMAIL_CONTAINERS)} containers, "
        f"{len(EMAIL_WIDGET_TYPES)} widget types"
    )


# =============================================================================
# SINGLETON ACCESS
# =============================================================================


def get_email_wrapper(
    force_reinitialize: bool = False,
) -> "ModuleWrapper":
    """Get the singleton ModuleWrapper for gmail.mjml_types.

    Returns:
        Shared ModuleWrapper instance configured for email blocks
    """
    global _wrapper

    with _wrapper_lock:
        if _wrapper is None or force_reinitialize:
            _wrapper = _create_email_wrapper()

    return _wrapper


def _create_email_wrapper() -> "ModuleWrapper":
    """Create and configure the ModuleWrapper instance using DomainConfig."""
    from adapters.module_wrapper import DomainConfig, ModuleWrapper
    from config.settings import settings

    logger.info("Creating singleton ModuleWrapper for gmail.mjml_types...")

    domain_config = DomainConfig(
        module_name="gmail.mjml_types",
        auto_install=False,
        priority_overrides=EMAIL_PRIORITY_OVERRIDES,
        nl_relationship_patterns=EMAIL_NL_RELATIONSHIP_PATTERNS,
        post_init_hooks=[
            _register_email_component_metadata,
        ],
        post_pipeline_hooks=[],
        domain_label="Email Blocks (MJML)",
    )

    wrapper = ModuleWrapper(
        module_or_name=domain_config.module_name,
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=getattr(settings, "email_collection", "email_blocks"),
        auto_initialize=False,
        index_nested=True,
        index_private=False,
        max_depth=3,
        skip_standard_library=True,
        domain_config=domain_config,
    )

    wrapper.initialize()

    # Filter symbol_mapping to only email-relevant types
    # The wrapper introspects gmail.mjml_types and generates symbols for ALL classes,
    # including utility types (BaseModel, Annotated, Tag, etc.) that shouldn't be user-facing.
    RELEVANT_TYPES = EMAIL_WIDGET_TYPES | {"EmailSpec", "Column"}
    raw_symbols = wrapper.symbol_mapping  # triggers lazy generation
    wrapper._symbol_mapping = {
        name: sym for name, sym in raw_symbols.items() if name in RELEVANT_TYPES
    }
    wrapper._reverse_symbol_mapping = {v: k for k, v in wrapper._symbol_mapping.items()}

    component_count = len(wrapper.components) if wrapper.components else 0
    symbol_count = len(wrapper._symbol_mapping)
    logger.info(
        f"Email ModuleWrapper ready: {component_count} components, "
        f"{symbol_count} symbols (filtered from {len(raw_symbols)})"
    )

    wrapper.run_domain_hooks("post_init")

    return wrapper


def reset_wrapper():
    """Reset the singleton wrapper."""
    global _wrapper

    with _wrapper_lock:
        if _wrapper is not None:
            logger.info("Resetting email ModuleWrapper")
            _wrapper = None
