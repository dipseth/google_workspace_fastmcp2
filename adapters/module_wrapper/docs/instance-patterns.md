# Instance Patterns

This document covers instance pattern storage, variation generation, and retrieval.

## What Are Instance Patterns?

Instance patterns represent successful usages of module components with specific parameter values. They capture:

- Component paths used (e.g., `["Section", "DecoratedText", "Button"]`)
- Parameter values (e.g., `{"text": "Hello", "buttons": [...]}`)
- Feedback signals (positive/negative)
- DSL notation
- **Style metadata** for auto-applying proven styles to new cards

## Data Classes

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

## Style Metadata

When patterns are stored, style information is automatically extracted from Jinja expressions and stored in `instance_params.style_metadata`. This enables auto-styling of new cards based on proven patterns.

### Style Metadata Structure

```python
{
    "jinja_filters": ["success_text", "bold"],  # All filters used
    "colors": ["#00FF00"],                       # Hex colors found
    "semantic_styles": ["success"],              # Semantic style names
    "formatting": ["bold"]                       # Formatting filters
}
```

### Extraction

The `extract_style_metadata()` function analyzes text for:

1. **Jinja filter chains**: `{{ 'text' | filter1 | filter2 }}`
2. **Color functions**: `color('#HEX')` or `color('success')`
3. **Semantic styles**: Maps `success_text` → `success`, `error_text` → `error`, etc.
4. **Formatting**: `bold`, `italic`, `strike`, `underline`

### Auto-Application

When building cards from matched patterns:

1. Style metadata is retrieved from `instance_params.style_metadata`
2. If the new card has no explicit styles (`_has_explicit_styles()` returns False)
3. Content-aware style selection applies appropriate styles based on text content
4. For example, text containing "online" gets `success_text` if the pattern used success styling

### Content-Aware Style Keywords

| Style | Trigger Keywords |
|-------|-----------------|
| `success_text` | online, success, ok, active, running, healthy, ready, up |
| `error_text` | error, fail, offline, down, unhealthy, critical, dead |
| `warning_text` | warning, pending, slow, degraded, unknown, wait |
| `info_text` | (fallback when no specific keywords match) |

### Pattern Payload Example

```python
{
    "type": "instance_pattern",
    "pattern_type": "content",
    "card_id": "abc123",
    "card_description": "Server status dashboard",
    "parent_paths": ["Section", "DecoratedText", "ButtonList"],
    "instance_params": {
        "title": "Server Status",
        "description": "Server status dashboard",
        "text": "{{ 'Online' | success_text | bold }}",
        "buttons": [...],
        "style_metadata": {
            "jinja_filters": ["success_text", "bold"],
            "colors": [],
            "semantic_styles": ["success"],
            "formatting": ["bold"]
        }
    },
    "content_feedback": "positive",
    "timestamp": "2026-01-31T..."
}
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

- `search_hybrid()` with feedback filters
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
