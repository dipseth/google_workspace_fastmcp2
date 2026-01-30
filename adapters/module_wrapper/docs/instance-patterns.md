# Instance Patterns

> **Status:** Coming soon

This document will cover instance pattern storage, variation generation, and retrieval.

## Planned Topics

### What Are Instance Patterns?

Instance patterns represent successful usages of module components with specific parameter values. They capture:

- Component paths used (e.g., `["Section", "DecoratedText", "Button"]`)
- Parameter values (e.g., `{"text": "Hello", "buttons": [...]}`)
- Feedback signals (positive/negative)
- DSL notation

### Data Classes

```python
@dataclass
class InstancePattern:
    pattern_id: str
    component_paths: List[str]
    instance_params: Dict[str, Any]
    description: str
    dsl_notation: Optional[str]
    feedback: Optional[str]  # "positive", "negative"

@dataclass
class PatternVariation:
    variation_id: str
    variation_type: str  # "structure", "parameter", "combined"
    component_paths: List[str]
    instance_params: Dict[str, Any]
    parent_id: str

@dataclass
class VariationFamily:
    parent_id: str
    source_pattern: InstancePattern
    variations: List[PatternVariation]
```

### Storing Patterns

- `store_instance_pattern()` - Store with optional variation generation
- Qdrant payload format
- V7 vector embedding
- Feedback field usage

### Variation Generation

- **Structure Variations** - Swap sibling components
- **Parameter Variations** - Modify parameter values
- **Combined Variations** - Both structure and parameters

### Variation Strategies

- `StructureVariator` - Uses relationship DAG for valid swaps
- `ParameterVariator` - Type-aware parameter mutations
- Variation family management

### Retrieval

- `search_v7_hybrid()` with feedback filters
- `get_cached_variation()` - Fast variation lookup
- Pattern similarity scoring

### Integration with Cache

- Variation caching in L1/L2
- Cache key generation
- Batch variation retrieval

## Related Files

- `instance_pattern_mixin.py` - InstancePatternMixin implementation
- `variation_generator.py` - Variation generation strategies
- `cache_mixin.py` - Cache integration
