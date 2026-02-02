"""
Tiered Component Cache for ModuleWrapper

Provides fast component retrieval with automatic spillover:
- L1: In-memory LRU cache (instant access, limited size)
- L2: Pickle files on disk (persistent, larger capacity)
- L3: Path-based reconstruction via wrapper (fallback)

Usage:
    from adapters.module_wrapper.component_cache import ComponentCache

    cache = ComponentCache(memory_limit=100, cache_dir=".component_cache")

    # Store a component reference
    cache.put("my_card_pattern", {
        "component_paths": ["Section", "DecoratedText"],
        "instance_params": {"text": "Hello"},
        "component_classes": {"Section": SectionClass, "DecoratedText": DTClass},
    })

    # Retrieve (checks L1 → L2 → L3 automatically)
    entry = cache.get("my_card_pattern")
    if entry:
        Section = entry["component_classes"]["Section"]
        widget = Section(...)

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                    ComponentCache                        │
    │  ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
    │  │ L1 Memory│ →  │ L2 Pickle│ →  │ L3 Reconstruction│  │
    │  │ LRU(100) │    │ .cache/  │    │ wrapper.get_*()  │  │
    │  └──────────┘    └──────────┘    └──────────────────┘  │
    └─────────────────────────────────────────────────────────┘
"""

import hashlib
import logging
import os
import pickle
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from adapters.module_wrapper.types import (
    CacheKey,
    ComponentPath,
    ComponentPaths,
    DSLNotation,
    EvictionCallback,
    Payload,
    Serializable,
    TimestampedMixin,
    WrapperGetter,
)

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """
    Cached component entry with metadata.

    Stores both serializable data (paths, params) and runtime references
    (component classes). Only serializable data goes to L2.
    """

    # Serializable (stored in L2 pickle)
    key: CacheKey
    component_paths: ComponentPaths
    instance_params: Dict[str, Any]
    dsl_notation: Optional[DSLNotation] = None
    structure_description: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0

    # Runtime only (not serialized)
    component_classes: Dict[str, Type] = field(default_factory=dict)
    _is_hydrated: bool = False

    def to_serializable(self) -> Payload:
        """Extract serializable data for pickle storage."""
        return {
            "key": self.key,
            "component_paths": self.component_paths,
            "instance_params": self.instance_params,
            "dsl_notation": self.dsl_notation,
            "structure_description": self.structure_description,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
        }

    @classmethod
    def from_serializable(cls, data: Dict[str, Any]) -> "CacheEntry":
        """Reconstruct from serialized data (needs hydration for classes)."""
        entry = cls(
            key=data["key"],
            component_paths=data["component_paths"],
            instance_params=data["instance_params"],
            dsl_notation=data.get("dsl_notation"),
            structure_description=data.get("structure_description"),
            created_at=data.get("created_at", time.time()),
            last_accessed=data.get("last_accessed", time.time()),
            access_count=data.get("access_count", 0),
        )
        entry._is_hydrated = False
        return entry

    def touch(self) -> None:
        """Update access timestamp and count."""
        self.last_accessed = time.time()
        self.access_count += 1


class LRUCache:
    """
    Thread-safe LRU cache with eviction callback.

    When items are evicted, the callback is invoked to allow
    spillover to L2 storage.
    """

    def __init__(
        self,
        maxsize: int = 100,
        on_evict: Optional[EvictionCallback] = None,
    ):
        self.maxsize = maxsize
        self.on_evict = on_evict
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: CacheKey) -> Optional[CacheEntry]:
        """Get item and move to end (most recently used)."""
        with self._lock:
            if key not in self._cache:
                return None
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry = self._cache[key]
            entry.touch()
            return entry

    def put(self, key: CacheKey, entry: CacheEntry) -> None:
        """Add item, evicting oldest if at capacity."""
        with self._lock:
            if key in self._cache:
                # Update existing and move to end
                self._cache[key] = entry
                self._cache.move_to_end(key)
                return

            # Check capacity before adding
            while len(self._cache) >= self.maxsize:
                # Evict oldest (first item)
                evicted_key, evicted_entry = self._cache.popitem(last=False)
                logger.debug(f"LRU evicting: {evicted_key}")
                if self.on_evict:
                    self.on_evict(evicted_key, evicted_entry)

            self._cache[key] = entry

    def remove(self, key: CacheKey) -> Optional[CacheEntry]:
        """Remove and return item without triggering eviction callback."""
        with self._lock:
            return self._cache.pop(key, None)

    def contains(self, key: CacheKey) -> bool:
        """Check if key exists without updating access time."""
        with self._lock:
            return key in self._cache

    def clear(self) -> int:
        """Clear all items, returning count cleared."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def keys(self) -> List[CacheKey]:
        """Get all keys (snapshot)."""
        with self._lock:
            return list(self._cache.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


class ComponentCache:
    """
    Tiered component cache with automatic spillover.

    L1 (Memory): Fast LRU cache for hot components
    L2 (Pickle): Persistent storage for evicted components
    L3 (Wrapper): Fallback reconstruction from paths

    Thread-safe for concurrent access.
    """

    def __init__(
        self,
        memory_limit: int = 100,
        cache_dir: Optional[str] = None,
        wrapper_getter: Optional[WrapperGetter] = None,
        auto_hydrate: bool = True,
    ):
        """
        Initialize the component cache.

        Args:
            memory_limit: Max items in L1 memory cache
            cache_dir: Directory for L2 pickle files (default: .component_cache)
            wrapper_getter: Callable that returns the ModuleWrapper (for L3 reconstruction)
            auto_hydrate: Automatically hydrate component_classes on get()
        """
        self.memory_limit = memory_limit
        self.cache_dir = Path(cache_dir or ".component_cache")
        self.wrapper_getter = wrapper_getter
        self.auto_hydrate = auto_hydrate

        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # L1: In-memory LRU with spillover callback
        self._l1 = LRUCache(maxsize=memory_limit, on_evict=self._spill_to_l2)

        # L2 index: tracks what's in pickle storage
        self._l2_index: Dict[str, str] = {}  # key → pickle filename
        self._l2_lock = threading.RLock()

        # Load L2 index from disk
        self._load_l2_index()

        # Stats
        self._stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_reconstructions": 0,
            "misses": 0,
        }

        logger.info(
            f"ComponentCache initialized: L1={memory_limit} items, "
            f"L2={self.cache_dir}, L2 entries={len(self._l2_index)}"
        )

    def _get_pickle_path(self, key: CacheKey) -> Path:
        """Get pickle file path for a cache key."""
        # Use hash to avoid filesystem issues with special characters
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{key_hash}.pkl"

    def _load_l2_index(self) -> None:
        """Load L2 index by scanning pickle files."""
        index_file = self.cache_dir / "_index.pkl"
        if index_file.exists():
            try:
                with open(index_file, "rb") as f:
                    self._l2_index = pickle.load(f)
                logger.debug(f"Loaded L2 index: {len(self._l2_index)} entries")
            except Exception as e:
                logger.warning(f"Failed to load L2 index: {e}")
                self._l2_index = {}
        else:
            # Rebuild index from pickle files
            self._rebuild_l2_index()

    def _save_l2_index(self) -> None:
        """Save L2 index to disk."""
        index_file = self.cache_dir / "_index.pkl"
        with self._l2_lock:
            try:
                with open(index_file, "wb") as f:
                    pickle.dump(self._l2_index, f)
            except Exception as e:
                logger.warning(f"Failed to save L2 index: {e}")

    def _rebuild_l2_index(self) -> None:
        """Rebuild L2 index by scanning pickle files."""
        with self._l2_lock:
            self._l2_index.clear()
            for pkl_file in self.cache_dir.glob("*.pkl"):
                if pkl_file.name == "_index.pkl":
                    continue
                try:
                    with open(pkl_file, "rb") as f:
                        data = pickle.load(f)
                        if isinstance(data, dict) and "key" in data:
                            self._l2_index[data["key"]] = pkl_file.name
                except Exception as e:
                    logger.warning(f"Failed to read {pkl_file}: {e}")

            logger.info(f"Rebuilt L2 index: {len(self._l2_index)} entries")
            self._save_l2_index()

    def _spill_to_l2(self, key: CacheKey, entry: CacheEntry) -> None:
        """Callback when L1 evicts an item - save to L2."""
        pkl_path = self._get_pickle_path(key)
        try:
            with open(pkl_path, "wb") as f:
                pickle.dump(entry.to_serializable(), f)

            with self._l2_lock:
                self._l2_index[key] = pkl_path.name
                self._save_l2_index()

            logger.debug(f"Spilled to L2: {key} → {pkl_path.name}")
        except Exception as e:
            logger.warning(f"Failed to spill {key} to L2: {e}")

    def _load_from_l2(self, key: CacheKey) -> Optional[CacheEntry]:
        """Load entry from L2 pickle storage."""
        with self._l2_lock:
            if key not in self._l2_index:
                return None

            pkl_name = self._l2_index[key]
            pkl_path = self.cache_dir / pkl_name

        if not pkl_path.exists():
            # File missing - remove from index
            with self._l2_lock:
                self._l2_index.pop(key, None)
                self._save_l2_index()
            return None

        try:
            with open(pkl_path, "rb") as f:
                data = pickle.load(f)
            return CacheEntry.from_serializable(data)
        except Exception as e:
            logger.warning(f"Failed to load {key} from L2: {e}")
            return None

    def _hydrate_entry(self, entry: CacheEntry) -> bool:
        """
        Hydrate a cache entry by resolving component_paths to classes.

        Uses the wrapper to look up actual component classes.
        """
        if entry._is_hydrated and entry.component_classes:
            return True

        if not self.wrapper_getter:
            logger.warning("Cannot hydrate: no wrapper_getter configured")
            return False

        try:
            wrapper = self.wrapper_getter()
            if not wrapper:
                return False

            classes = {}
            for path in entry.component_paths:
                # Extract component name from path
                name = path.split(".")[-1] if "." in path else path

                # Try to get the component class
                cls = wrapper.get_component_by_path(path)
                if not cls:
                    # Try by name only
                    cls = wrapper.get_component_by_path(f"{wrapper.module_name}.{name}")

                if cls:
                    classes[name] = cls
                else:
                    logger.debug(f"Could not resolve component: {path}")

            entry.component_classes = classes
            entry._is_hydrated = True
            return len(classes) > 0

        except Exception as e:
            logger.warning(f"Hydration failed: {e}")
            return False

    def _reconstruct_from_wrapper(
        self, key: CacheKey, component_paths: ComponentPaths
    ) -> Optional[CacheEntry]:
        """
        L3: Reconstruct entry from wrapper using component paths.

        This is the fallback when the entry isn't in L1 or L2.
        """
        if not self.wrapper_getter:
            return None

        try:
            wrapper = self.wrapper_getter()
            if not wrapper:
                return None

            # Build DSL notation if possible
            dsl_notation = None
            try:
                dsl_notation = wrapper.build_dsl_from_paths(component_paths)
            except Exception:
                pass

            # Create entry
            entry = CacheEntry(
                key=key,
                component_paths=component_paths,
                instance_params={},
                dsl_notation=dsl_notation,
            )

            # Hydrate with component classes
            self._hydrate_entry(entry)

            self._stats["l3_reconstructions"] += 1
            return entry

        except Exception as e:
            logger.warning(f"L3 reconstruction failed for {key}: {e}")
            return None

    def get(
        self,
        key: CacheKey,
        component_paths: Optional[ComponentPaths] = None,
    ) -> Optional[CacheEntry]:
        """
        Get a cached component entry.

        Checks L1 → L2 → L3 (reconstruction) in order.
        Automatically promotes L2 hits back to L1.

        Args:
            key: Cache key (e.g., pattern ID or description hash)
            component_paths: Optional paths for L3 reconstruction if not found

        Returns:
            CacheEntry with component_classes populated, or None
        """
        # L1: Check memory cache
        entry = self._l1.get(key)
        if entry:
            self._stats["l1_hits"] += 1
            if self.auto_hydrate and not entry._is_hydrated:
                self._hydrate_entry(entry)
            return entry

        # L2: Check pickle storage
        entry = self._load_from_l2(key)
        if entry:
            self._stats["l2_hits"] += 1
            # Hydrate and promote to L1
            if self.auto_hydrate:
                self._hydrate_entry(entry)
            self._l1.put(key, entry)
            return entry

        # L3: Reconstruct from paths if provided
        if component_paths:
            entry = self._reconstruct_from_wrapper(key, component_paths)
            if entry:
                # Cache the reconstructed entry
                self._l1.put(key, entry)
                return entry

        self._stats["misses"] += 1
        return None

    def put(
        self,
        key: CacheKey,
        component_paths: ComponentPaths,
        instance_params: Optional[Payload] = None,
        component_classes: Optional[Dict[str, Type]] = None,
        dsl_notation: Optional[DSLNotation] = None,
        structure_description: Optional[str] = None,
    ) -> CacheEntry:
        """
        Store a component entry in the cache.

        Args:
            key: Unique cache key
            component_paths: List of component paths
            instance_params: Parameters used to instantiate components
            component_classes: Pre-resolved component classes (optional)
            dsl_notation: DSL notation for the structure
            structure_description: Human-readable description

        Returns:
            The created CacheEntry
        """
        entry = CacheEntry(
            key=key,
            component_paths=component_paths,
            instance_params=instance_params or {},
            dsl_notation=dsl_notation,
            structure_description=structure_description,
        )

        if component_classes:
            entry.component_classes = component_classes
            entry._is_hydrated = True

        self._l1.put(key, entry)
        return entry

    def put_from_pattern(
        self,
        pattern: Payload,
        key: Optional[CacheKey] = None,
    ) -> CacheEntry:
        """
        Store a component entry from an instance_pattern dict.

        Convenience method for storing patterns retrieved from Qdrant.

        Args:
            pattern: Pattern dict with component_paths, instance_params, etc.
            key: Optional cache key (defaults to pattern's card_id or hash)

        Returns:
            The created CacheEntry
        """
        # Determine key
        if not key:
            key = pattern.get("card_id") or pattern.get("id")
            if not key:
                # Hash the description
                desc = pattern.get("card_description", "")
                key = hashlib.sha256(desc.encode()).hexdigest()[:16]

        # Extract component paths
        component_paths = pattern.get("component_paths") or pattern.get(
            "parent_paths", []
        )

        return self.put(
            key=key,
            component_paths=component_paths,
            instance_params=pattern.get("instance_params", {}),
            dsl_notation=pattern.get("relationship_text") or pattern.get("dsl_notation"),
            structure_description=pattern.get("structure_description"),
        )

    def remove(self, key: CacheKey) -> bool:
        """
        Remove an entry from all cache levels.

        Returns:
            True if entry was found and removed
        """
        removed = False

        # Remove from L1
        if self._l1.remove(key):
            removed = True

        # Remove from L2
        with self._l2_lock:
            if key in self._l2_index:
                pkl_name = self._l2_index.pop(key)
                pkl_path = self.cache_dir / pkl_name
                if pkl_path.exists():
                    pkl_path.unlink()
                self._save_l2_index()
                removed = True

        return removed

    def clear(self, l1_only: bool = False) -> Dict[str, int]:
        """
        Clear the cache.

        Args:
            l1_only: If True, only clear L1 (memory) cache

        Returns:
            Dict with counts of cleared entries per level
        """
        cleared = {"l1": self._l1.clear(), "l2": 0}

        if not l1_only:
            with self._l2_lock:
                for pkl_name in self._l2_index.values():
                    pkl_path = self.cache_dir / pkl_name
                    if pkl_path.exists():
                        pkl_path.unlink()
                        cleared["l2"] += 1
                self._l2_index.clear()
                self._save_l2_index()

        logger.info(f"Cache cleared: L1={cleared['l1']}, L2={cleared['l2']}")
        return cleared

    def warm_from_wrapper(self, limit: int = 50) -> int:
        """
        Pre-populate cache with frequently used components from wrapper.

        Args:
            limit: Max components to pre-cache

        Returns:
            Number of components cached
        """
        if not self.wrapper_getter:
            return 0

        try:
            wrapper = self.wrapper_getter()
            if not wrapper:
                return 0

            # Get commonly used components
            cached = 0
            for name, comp in list(wrapper.components.items())[:limit]:
                if comp.component_type != "class":
                    continue

                path = comp.full_path or f"{wrapper.module_name}.{name}"
                key = f"component:{name}"

                entry = CacheEntry(
                    key=key,
                    component_paths=[path],
                    instance_params={},
                    dsl_notation=wrapper.symbol_mapping.get(name, ""),
                )

                # Get the actual class
                cls = wrapper.get_component_by_path(path)
                if cls:
                    entry.component_classes = {name: cls}
                    entry._is_hydrated = True

                self._l1.put(key, entry)
                cached += 1

            logger.info(f"Warmed cache with {cached} components")
            return cached

        except Exception as e:
            logger.warning(f"Cache warming failed: {e}")
            return 0

    @property
    def stats(self) -> Payload:
        """Get cache statistics."""
        total_requests = sum(self._stats.values())
        hit_rate = (
            (self._stats["l1_hits"] + self._stats["l2_hits"]) / total_requests
            if total_requests > 0
            else 0
        )

        return {
            **self._stats,
            "l1_size": len(self._l1),
            "l2_size": len(self._l2_index),
            "hit_rate": hit_rate,
            "total_requests": total_requests,
        }

    def __repr__(self) -> str:
        stats = self.stats
        return (
            f"ComponentCache(L1={stats['l1_size']}/{self.memory_limit}, "
            f"L2={stats['l2_size']}, hit_rate={stats['hit_rate']:.1%})"
        )


# =============================================================================
# SINGLETON & INTEGRATION
# =============================================================================

_cache_instance: Optional[ComponentCache] = None
_cache_lock = threading.Lock()


def get_component_cache(
    memory_limit: int = 100,
    cache_dir: Optional[str] = None,
    reset: bool = False,
) -> ComponentCache:
    """
    Get the singleton ComponentCache instance.

    Args:
        memory_limit: Max L1 cache size (only used on first call)
        cache_dir: Cache directory (only used on first call)
        reset: Force create a new instance

    Returns:
        ComponentCache singleton
    """
    global _cache_instance

    with _cache_lock:
        if _cache_instance is None or reset:
            # Default wrapper getter
            def wrapper_getter():
                try:
                    from gchat.card_framework_wrapper import get_card_framework_wrapper

                    return get_card_framework_wrapper()
                except ImportError:
                    return None

            _cache_instance = ComponentCache(
                memory_limit=memory_limit,
                cache_dir=cache_dir,
                wrapper_getter=wrapper_getter,
            )

        return _cache_instance


def cache_pattern(pattern: Payload, key: Optional[CacheKey] = None) -> CacheEntry:
    """
    Convenience function to cache an instance pattern.

    Args:
        pattern: Pattern dict from Qdrant or SmartCardBuilder
        key: Optional cache key

    Returns:
        CacheEntry with hydrated component classes
    """
    cache = get_component_cache()
    return cache.put_from_pattern(pattern, key)


def get_cached_components(
    key: CacheKey,
    component_paths: Optional[ComponentPaths] = None,
) -> Optional[Dict[str, Type]]:
    """
    Convenience function to get cached component classes.

    Args:
        key: Cache key
        component_paths: Paths for L3 reconstruction if not cached

    Returns:
        Dict mapping component names to classes, or None
    """
    cache = get_component_cache()
    entry = cache.get(key, component_paths)
    if entry and entry.component_classes:
        return entry.component_classes
    return None
