"""
Singleton ModuleWrapper for qdrant_client.models.

Follows the same pattern as gchat/card_framework_wrapper.py but wraps
qdrant_client.models — the public API surface for Qdrant search primitives.

The ModuleWrapper automatically:
- Indexes all classes in qdrant_client.models as ModuleComponents
- Generates Unicode symbols via SymbolGenerator
- Extracts relationships from Pydantic model fields (via Phase 1f support)
- Builds DSL metadata from relationships

Usage:
    from middleware.qdrant_core.qdrant_models_wrapper import get_qdrant_models_wrapper

    wrapper = get_qdrant_models_wrapper()
    symbols = wrapper.symbol_mapping
    parser = wrapper.get_dsl_parser()
"""

import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Thread-safe singleton
_wrapper: Optional["ModuleWrapper"] = None
_wrapper_lock = threading.Lock()


def get_qdrant_models_wrapper(
    force_reinitialize: bool = False,
) -> "ModuleWrapper":
    """
    Get the singleton ModuleWrapper for qdrant_client.models.

    Args:
        force_reinitialize: If True, recreate the wrapper even if one exists.

    Returns:
        Shared ModuleWrapper instance configured for qdrant_client.models
    """
    global _wrapper

    with _wrapper_lock:
        if _wrapper is None or force_reinitialize:
            _wrapper = _create_wrapper()

    return _wrapper


def _create_wrapper() -> "ModuleWrapper":
    """Create and configure the ModuleWrapper for qdrant_client.models."""
    from adapters.module_wrapper import ModuleWrapper
    from config.settings import settings

    logger.info("Creating ModuleWrapper for qdrant_client.models...")

    wrapper = ModuleWrapper(
        module_or_name="qdrant_client.models",
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name="mcp_qdrant_client_models",
        auto_initialize=True,
        index_nested=True,
        index_private=False,
        max_depth=2,
        skip_standard_library=True,
        include_modules=["qdrant_client"],
    )

    component_count = len(wrapper.components) if wrapper.components else 0
    class_count = sum(
        1 for c in wrapper.components.values() if c.component_type == "class"
    )
    logger.info(
        f"ModuleWrapper ready for qdrant_client.models: "
        f"{component_count} components, {class_count} classes"
    )

    return wrapper


def reset_wrapper():
    """Reset the singleton wrapper."""
    global _wrapper
    with _wrapper_lock:
        if _wrapper is not None:
            logger.info("Resetting qdrant_client.models ModuleWrapper")
            _wrapper = None
