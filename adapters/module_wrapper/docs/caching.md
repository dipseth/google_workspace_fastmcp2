# Caching

> **Status:** Coming soon

This document will cover the tiered caching system for fast component retrieval.

## Planned Topics

### Cache Architecture

```
Request → L1 (Memory) → L2 (Pickle) → L3 (Resolve)
                ↑            ↑            ↓
                └────────────┴── populate ┘
```

### L1: Memory Cache

- LRU eviction policy
- Default 100 entry limit
- CacheEntry storage format
- Thread safety considerations

### L2: Pickle Cache

- File-based persistence
- `.component_cache/` directory
- Entry serialization format
- Cache invalidation

### L3: Resolution

- ModuleWrapper path resolution
- `get_component_by_path()` integration
- Class hydration
- Error handling

### CacheEntry Format

```python
@dataclass
class CacheEntry:
    key: str
    component_paths: List[str]
    instance_params: Dict[str, Any]
    dsl_notation: Optional[str]
    component_classes: Dict[str, Type]  # Hydrated classes
```

### Cache Operations

- `cache_pattern()` - Store pattern with classes
- `get_cached_entry()` - Retrieve with auto-hydration
- `get_cached_class()` - Fast single class lookup
- `invalidate_cache()` - Clear entries

### Cache Warming

- Priority component preloading
- Common widget classes
- Module initialization integration

### Performance

- Hit rate tracking
- Memory usage monitoring
- Pickle file cleanup

## Related Files

- `cache_mixin.py` - CacheMixin implementation
- `component_cache.py` - ComponentCache class
