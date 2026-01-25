"""
Singleton ModuleWrapper for card_framework.

This provides a single shared ModuleWrapper instance for all gchat modules
that need to access card_framework components. Avoids redundant wrapper
creation and ensures consistent configuration.

Usage:
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()
    component = wrapper.get_component_by_path("card_framework.v2.widgets.Button")
"""

import logging
import os
import threading
from typing import Optional

from config.enhanced_logging import setup_logger

logger = setup_logger(__name__)

# Thread-safe singleton
_wrapper: Optional["ModuleWrapper"] = None
_wrapper_lock = threading.Lock()


def get_card_framework_wrapper(force_reinitialize: bool = False) -> "ModuleWrapper":
    """
    Get the singleton ModuleWrapper for card_framework.

    This wrapper is shared across:
        - SmartCardBuilder
        - TemplateComponent
        - unified_card_tool
        - Any other gchat modules needing card_framework access

    Args:
        force_reinitialize: If True, recreate the wrapper even if one exists.
                           Use sparingly (e.g., after collection schema changes).

    Returns:
        Shared ModuleWrapper instance configured for card_framework
    """
    global _wrapper

    with _wrapper_lock:
        if _wrapper is None or force_reinitialize:
            _wrapper = _create_wrapper()

    return _wrapper


def _create_wrapper() -> "ModuleWrapper":
    """Create and configure the ModuleWrapper instance."""
    from adapters.module_wrapper import ModuleWrapper
    from config.settings import settings

    logger.info("🔧 Creating singleton ModuleWrapper for card_framework...")

    wrapper = ModuleWrapper(
        module_or_name="card_framework",
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=settings.card_collection,  # mcp_gchat_cards_v7
        auto_initialize=False,  # Don't re-index, collection already populated
        index_nested=True,
        index_private=False,
        max_depth=5,  # Capture full component hierarchy
        skip_standard_library=True,
    )

    component_count = len(wrapper.components) if wrapper.components else 0
    logger.info(f"✅ Singleton ModuleWrapper ready: {component_count} components loaded")

    return wrapper


def reset_wrapper():
    """
    Reset the singleton wrapper.

    Use this when you need to force reinitialization, such as:
        - After updating the Qdrant collection schema
        - During testing
        - After configuration changes
    """
    global _wrapper

    with _wrapper_lock:
        if _wrapper is not None:
            logger.info("🔄 Resetting singleton ModuleWrapper")
            _wrapper = None


# Google Chat Card API Limits (for reference by gchat modules)
# These are documented here since this is the central card_framework access point
GCHAT_CARD_MAX_BYTES = 20_000  # Maximum card payload size
GCHAT_TEXT_MAX_CHARS = 18_000  # Maximum text message length
GCHAT_SAFE_LIMIT_RATIO = 0.75  # Recommended operating ratio (75% of max)
GCHAT_SAFE_CARD_BYTES = int(GCHAT_CARD_MAX_BYTES * GCHAT_SAFE_LIMIT_RATIO)  # ~15KB
