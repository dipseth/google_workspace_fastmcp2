"""
WrapperRegistry — Thread-safe singleton registry for ModuleWrapper instances.

Replaces the duplicated _wrapper/_wrapper_lock/get_*_wrapper()/reset_wrapper()
patterns across gchat/wrapper_setup.py, gmail/email_wrapper_setup.py, and
middleware/qdrant_core/qdrant_models_wrapper.py.

Also provides shared DSL documentation helpers that replace duplicated
get_dsl_documentation() / get_dsl_field_description() patterns.

Usage:
    from adapters.module_wrapper.wrapper_factory import WrapperRegistry

    # Register a wrapper factory
    WrapperRegistry.register("card_framework", _create_wrapper)

    # Get the singleton wrapper
    wrapper = WrapperRegistry.get("card_framework")

    # Reset for testing
    WrapperRegistry.reset("card_framework")
"""

import threading
from typing import Any, Callable, Dict, List, Optional, Set

from config.enhanced_logging import setup_logger

logger = setup_logger()


class WrapperRegistry:
    """Thread-safe singleton registry for ModuleWrapper instances.

    Manages wrapper lifecycle: lazy creation via registered factories,
    thread-safe singleton access, and reset for testing.
    """

    _factories: Dict[str, Callable] = {}
    _instances: Dict[str, Any] = {}
    _locks: Dict[str, threading.Lock] = {}
    _global_lock = threading.Lock()

    @classmethod
    def register(cls, name: str, factory: Callable) -> None:
        """Register a wrapper factory.

        Args:
            name: Wrapper identifier (e.g. "card_framework", "email", "qdrant_models")
            factory: Zero-argument callable that creates and returns a ModuleWrapper
        """
        with cls._global_lock:
            cls._factories[name] = factory
            if name not in cls._locks:
                cls._locks[name] = threading.Lock()

    @classmethod
    def get(cls, name: str, force_reinitialize: bool = False) -> Any:
        """Get a singleton wrapper by name, creating it if needed.

        Args:
            name: Registered wrapper name
            force_reinitialize: If True, recreate even if one exists

        Returns:
            ModuleWrapper instance

        Raises:
            KeyError: If no factory registered for the given name
        """
        # Ensure lock exists
        with cls._global_lock:
            if name not in cls._locks:
                cls._locks[name] = threading.Lock()
            if name not in cls._factories:
                raise KeyError(
                    f"No wrapper factory registered for '{name}'. "
                    f"Available: {list(cls._factories.keys())}"
                )

        lock = cls._locks[name]
        with lock:
            if name not in cls._instances or force_reinitialize:
                factory = cls._factories[name]
                cls._instances[name] = factory()
                logger.info(f"WrapperRegistry: created wrapper '{name}'")

        return cls._instances[name]

    @classmethod
    def reset(cls, name: str) -> None:
        """Reset a singleton wrapper, removing the cached instance.

        Args:
            name: Wrapper name to reset
        """
        with cls._global_lock:
            if name not in cls._locks:
                cls._locks[name] = threading.Lock()

        lock = cls._locks[name]
        with lock:
            if name in cls._instances:
                logger.info(f"WrapperRegistry: resetting wrapper '{name}'")
                cls._instances.pop(name, None)

    @classmethod
    def reset_all(cls) -> None:
        """Reset all registered wrappers."""
        with cls._global_lock:
            names = list(cls._instances.keys())

        for name in names:
            cls.reset(name)

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a factory is registered for the given name."""
        return name in cls._factories

    @classmethod
    def registered_names(cls) -> List[str]:
        """Get list of registered wrapper names."""
        return list(cls._factories.keys())


# =============================================================================
# SHARED DSL HELPERS
# =============================================================================


def generate_dsl_quick_reference(
    wrapper,
    categories: Dict[str, List[str]],
    title: str = "DSL Quick Reference",
    examples: Optional[List[str]] = None,
    include_hierarchy: bool = True,
) -> str:
    """Generate a compact DSL quick-reference document from wrapper symbols.

    Replaces the duplicated get_dsl_documentation() pattern across
    gchat/wrapper_api.py and gmail/email_wrapper_api.py.

    Args:
        wrapper: ModuleWrapper with symbol_mapping
        categories: Dict of category_name -> list of component names
        title: Document title
        examples: Optional list of example DSL strings
        include_hierarchy: Whether to include containment rules

    Returns:
        Markdown-formatted quick reference
    """
    symbols = getattr(wrapper, "symbol_mapping", {})

    lines = [f"## {title}\n"]

    # Symbols by category
    lines.append("### Symbols")
    for category, components in categories.items():
        mappings = [f"{symbols.get(c, '?')}={c}" for c in components if c in symbols]
        if mappings:
            lines.append(f"**{category}:** {', '.join(mappings)}")

    if examples:
        lines.append("\n### Examples")
        for ex in examples:
            lines.append(f"- `{ex}`")

    lines.append(
        "\n### More Info\nRead associated skill:// resources for complete documentation."
    )

    return "\n".join(lines)


def generate_dsl_field_description(
    wrapper,
    key_components: List[str],
    skill_uri: str = "skill://",
) -> str:
    """Generate a compact field description for a DSL parameter.

    Replaces the duplicated get_dsl_field_description() pattern.

    Args:
        wrapper: ModuleWrapper with symbol_mapping
        key_components: List of component names to include in description
        skill_uri: URI for the skill resource reference

    Returns:
        Single-line description suitable for Field(description=...)
    """
    symbols = getattr(wrapper, "symbol_mapping", {})

    key_mappings = []
    for comp in key_components:
        if comp in symbols:
            key_mappings.append(f"{symbols[comp]}={comp}")

    return (
        f"DSL structure using symbols. "
        f"Symbols: {', '.join(key_mappings)}. "
        f"Read {skill_uri} for full reference."
    )


def get_skill_resources_safe(
    wrapper,
    skill_name: str,
    resource_hints: Dict[str, Dict[str, str]],
) -> List:
    """Safely get skill_resources annotation from a wrapper.

    Replaces the duplicated try/except get_skill_resources_annotation() pattern
    across gchat/card_tools.py, gmail/compose.py, and middleware/qdrant_core/tools.py.

    Args:
        wrapper: ModuleWrapper instance (may be None)
        skill_name: Skill name for resource lookup
        resource_hints: Dict of resource_name -> {purpose, when_to_read}

    Returns:
        List of skill resource annotations, or empty list on failure
    """
    if wrapper is None:
        return []

    try:
        if hasattr(wrapper, "get_skill_resources_annotation"):
            return wrapper.get_skill_resources_annotation(
                skill_name=skill_name,
                resource_hints=resource_hints,
            )
    except Exception:
        pass  # Non-fatal — skill_resources is optional

    return []
