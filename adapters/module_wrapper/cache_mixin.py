"""
Cache Integration Mixin for ModuleWrapper

Provides seamless integration between ModuleWrapper and ComponentCache,
enabling fast component retrieval without path-based reconstruction.

Usage:
    # The mixin is automatically included in ModuleWrapper
    wrapper = get_card_framework_wrapper()

    # Cache a pattern with resolved classes
    entry = wrapper.cache_pattern(
        key="my_card",
        component_paths=["Section", "DecoratedText"],
        instance_params={"text": "Hello"},
    )

    # Retrieve cached components
    Section = wrapper.get_cached_class("Section")
    entry = wrapper.get_cached_entry("my_card")
"""

import logging
from typing import Any, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class CacheMixin:
    """
    Mixin that adds ComponentCache integration to ModuleWrapper.

    Expects the following attributes on self:
    - module_name: str
    - components: Dict[str, ModuleComponent]
    - get_component_by_path: Callable
    - symbol_mapping: Dict[str, str]
    - build_dsl_from_paths: Callable
    """

    _component_cache = None

    def _get_component_cache(self):
        """Get or create the ComponentCache instance."""
        if self._component_cache is None:
            from adapters.module_wrapper.component_cache import ComponentCache

            # Create cache with self as the wrapper getter
            self._component_cache = ComponentCache(
                memory_limit=100,
                cache_dir=".component_cache",
                wrapper_getter=lambda: self,
                auto_hydrate=True,
            )

            # Warm cache with commonly used components
            self._warm_component_cache()

        return self._component_cache

    def _warm_component_cache(self) -> int:
        """Pre-populate cache with frequently used components."""
        if not hasattr(self, "components"):
            return 0

        from adapters.module_wrapper.component_cache import CacheEntry

        cache = self._component_cache
        warmed = 0

        # Priority components (most commonly used in cards)
        priority_components = [
            "Section",
            "DecoratedText",
            "TextParagraph",
            "ButtonList",
            "Button",
            "Image",
            "Icon",
            "Card",
            "CardHeader",
            "OnClick",
            "OpenLink",
            "Color",
            "Divider",
            "Grid",
            "GridItem",
            "Columns",
            "Column",
            "Carousel",
            "CarouselCard",
        ]

        for name in priority_components:
            if name not in self.components:
                continue

            comp = self.components[name]
            path = comp.full_path or f"{self.module_name}.{name}"
            key = f"component:{name}"

            # Get actual class
            cls = self.get_component_by_path(path)
            if not cls:
                continue

            entry = CacheEntry(
                key=key,
                component_paths=[path],
                instance_params={},
                dsl_notation=self.symbol_mapping.get(name, ""),
            )
            entry.component_classes = {name: cls}
            entry._is_hydrated = True

            cache._l1.put(key, entry)
            warmed += 1

        logger.debug(f"Warmed component cache with {warmed} priority components")
        return warmed

    def cache_pattern(
        self,
        key: str,
        component_paths: List[str],
        instance_params: Optional[Dict[str, Any]] = None,
        resolve_classes: bool = True,
        dsl_notation: Optional[str] = None,
        structure_description: Optional[str] = None,
    ) -> "CacheEntry":
        """
        Cache a pattern with its component classes.

        This method resolves component paths to actual classes and caches
        them for fast retrieval later.

        Args:
            key: Unique cache key (e.g., card_id, pattern hash)
            component_paths: List of component paths or names
            instance_params: Parameters used to instantiate the components
            resolve_classes: Whether to resolve paths to classes now
            dsl_notation: Optional DSL notation (auto-generated if not provided)
            structure_description: Optional human description of the structure

        Returns:
            CacheEntry with component_classes populated

        Example:
            entry = wrapper.cache_pattern(
                key="status_card_v1",
                component_paths=["Section", "DecoratedText", "ButtonList"],
                instance_params={"text": "Status: Online", "buttons": [...]},
                dsl_notation="§[δ, Ƀ]",
            )

            # Later retrieval
            Section = wrapper.get_cached_class("Section")
        """
        from adapters.module_wrapper.component_cache import CacheEntry

        cache = self._get_component_cache()

        # Build DSL notation if not provided
        if dsl_notation is None:
            try:
                dsl_notation = self.build_dsl_from_paths(component_paths)
            except Exception:
                pass

        # Resolve component classes
        classes = {}
        if resolve_classes:
            for path in component_paths:
                name = path.split(".")[-1] if "." in path else path

                # Resolve the full path
                full_path = self._resolve_component_path(path)
                if not full_path:
                    full_path = self._resolve_component_path(name)

                cls = None
                if full_path:
                    cls = self.get_component_by_path(full_path)

                if cls:
                    classes[name] = cls

        entry = CacheEntry(
            key=key,
            component_paths=component_paths,
            instance_params=instance_params or {},
            dsl_notation=dsl_notation,
            structure_description=structure_description,
        )
        entry.component_classes = classes
        entry._is_hydrated = bool(classes)

        cache._l1.put(key, entry)
        return entry

    def get_cached_entry(
        self,
        key: str,
        component_paths: Optional[List[str]] = None,
    ) -> Optional["CacheEntry"]:
        """
        Get a cached pattern entry.

        Checks L1 (memory) → L2 (pickle) → L3 (reconstruction).

        Args:
            key: Cache key
            component_paths: Optional paths for L3 reconstruction

        Returns:
            CacheEntry with component_classes, or None
        """
        cache = self._get_component_cache()
        return cache.get(key, component_paths)

    def _resolve_component_path(self, component_name: str) -> Optional[str]:
        """
        Resolve a component name to its full importable path.

        Args:
            component_name: Simple name like "Button" or full path

        Returns:
            Full importable path like "card_framework.v2.widgets.button.Button"
        """
        # If already a full path, return it
        if "." in component_name and component_name.count(".") >= 2:
            return component_name

        # Collect all matching paths, then prefer v2 over v1
        matching_paths = []

        # Search in components dict by name suffix
        for comp_key, comp in self.components.items():
            # Check if key ends with the component name
            if comp_key.endswith(f".{component_name}") or comp_key == component_name:
                full_path = comp.full_path
                if full_path:
                    matching_paths.append(full_path)

            # Also check comp.name
            elif hasattr(comp, "name") and comp.name == component_name:
                if comp.full_path:
                    matching_paths.append(comp.full_path)

        # Prefer v2 paths over v1 paths (e.g., card_framework.v2.message.Message over card_framework.Message)
        if matching_paths:
            v2_paths = [p for p in matching_paths if ".v2." in p]
            if v2_paths:
                return v2_paths[0]
            return matching_paths[0]

        # Try common patterns for card_framework
        common_patterns = [
            f"card_framework.v2.widgets.{component_name.lower()}.{component_name}",
            f"card_framework.v2.{component_name.lower()}.{component_name}",
            f"card_framework.v2.widgets.{component_name}",
            f"card_framework.v2.{component_name}",
        ]

        for pattern in common_patterns:
            cls = self.get_component_by_path(pattern)
            if cls:
                return pattern

        return None

    def get_cached_class(self, component_name: str) -> Optional[Type]:
        """
        Get a cached component class by name.

        Fast path for retrieving individual component classes.

        Args:
            component_name: Component name (e.g., "Button", "Section")

        Returns:
            Component class or None
        """
        cache = self._get_component_cache()
        key = f"component:{component_name}"

        entry = cache.get(key)
        if entry and entry.component_classes:
            return entry.component_classes.get(component_name)

        # Not in cache - resolve path and get class
        path = self._resolve_component_path(component_name)
        if not path:
            logger.debug(f"Could not resolve path for: {component_name}")
            return None

        cls = self.get_component_by_path(path)
        if not cls:
            logger.debug(f"get_component_by_path returned None for: {path}")
            return None

        # Cache for future use
        from adapters.module_wrapper.component_cache import CacheEntry

        entry = CacheEntry(
            key=key,
            component_paths=[path],
            instance_params={},
            dsl_notation=self.symbol_mapping.get(component_name, ""),
        )
        entry.component_classes = {component_name: cls}
        entry._is_hydrated = True
        cache._l1.put(key, entry)

        return cls

    def get_cached_classes(
        self,
        component_names: List[str],
    ) -> Dict[str, Type]:
        """
        Get multiple cached component classes by name.

        Args:
            component_names: List of component names

        Returns:
            Dict mapping names to classes (only includes found classes)
        """
        result = {}
        for name in component_names:
            cls = self.get_cached_class(name)
            if cls:
                result[name] = cls
        return result

    def cache_from_qdrant_pattern(
        self,
        pattern: Dict[str, Any],
        key: Optional[str] = None,
    ) -> "CacheEntry":
        """
        Cache a pattern retrieved from Qdrant.

        Convenience method that extracts fields from a Qdrant pattern payload.

        Args:
            pattern: Pattern dict from Qdrant scroll/query
            key: Optional cache key (defaults to card_id or hash)

        Returns:
            CacheEntry with hydrated component classes
        """
        import hashlib

        # Determine key
        if not key:
            key = pattern.get("card_id") or pattern.get("id")
            if not key:
                desc = pattern.get("card_description", "")
                key = f"pattern:{hashlib.sha256(desc.encode()).hexdigest()[:12]}"

        # Extract paths (handle both field names)
        component_paths = pattern.get("component_paths") or pattern.get(
            "parent_paths", []
        )

        return self.cache_pattern(
            key=key,
            component_paths=component_paths,
            instance_params=pattern.get("instance_params", {}),
        )

    def invalidate_cache(self, key: Optional[str] = None) -> bool:
        """
        Invalidate cache entries.

        Args:
            key: Specific key to invalidate, or None for all

        Returns:
            True if something was invalidated
        """
        cache = self._get_component_cache()

        if key:
            return cache.remove(key)
        else:
            cleared = cache.clear()
            return cleared["l1"] > 0 or cleared["l2"] > 0

    @property
    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        cache = self._get_component_cache()
        return cache.stats


# Import CacheEntry for type hints
try:
    from adapters.module_wrapper.component_cache import CacheEntry
except ImportError:
    CacheEntry = None
